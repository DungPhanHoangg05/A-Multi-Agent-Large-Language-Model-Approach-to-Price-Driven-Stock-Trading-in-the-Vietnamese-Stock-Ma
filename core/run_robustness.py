"""Chạy Robustness Sweep A20 bằng giao thức paired shared reports."""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict, fields
from datetime import datetime
import hashlib
import json
from pathlib import Path
import random
import sys
import time
from typing import Any, Dict, List, Sequence

import numpy as np
import pandas as pd
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from core.backtest_engine import (
    BacktestEngine,
    TestPoint,
    build_walk_forward_end_indices,
    required_backtest_rows,
)
from core.realtime_loader import fetch_realtime_ohlcv
from utils import static_util
from utils.graph_setup import ABLATION_CONFIGS
from utils.static_util import get_forecast_horizon


DEFAULT_OUTPUT_DIR = Path("outputs/robustness/clean_a20")
DEFAULT_N_TESTS = 20
DEFAULT_STEP = 3
DEFAULT_WINDOW = 45
SEED = 42

WINDOW_SCENARIOS = (("w30", 30), ("w45", 45), ("w60", 60))
NORM_SCENARIOS = (
    ("zscore_tanh", "zscore_tanh"),
    ("minmax", "minmax"),
    ("rank", "rank"),
)
WEIGHT_SCENARIOS = (
    ("default", {"ic": 0.40, "acc": 0.35, "sharpe": 0.25}),
    ("equal_weight", {"ic": 1 / 3, "acc": 1 / 3, "sharpe": 1 / 3}),
    ("ic_heavy", {"ic": 0.60, "acc": 0.20, "sharpe": 0.20}),
)


def _point_value(point: Any, name: str, default: Any = None) -> Any:
    if isinstance(point, dict):
        return point.get(name, default)
    return getattr(point, name, default)


def _prediction_signature(predictions: Sequence[str]) -> str:
    payload = json.dumps(list(predictions), ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def load_market_data(
    symbol: str,
    *,
    n_tests: int,
    max_window_size: int,
    step: int = DEFAULT_STEP,
    timeframe: str = "1d",
    data_cutoff: str | None = None,
) -> pd.DataFrame:
    """Tải dữ liệu thật đủ dài; tuyệt đối không rơi về dữ liệu tổng hợp."""

    lookahead = int(get_forecast_horizon(timeframe)["lookahead_candles"])
    required_rows = required_backtest_rows(
        n_tests=n_tests,
        window_size=max_window_size,
        step=step,
        lookahead=lookahead,
    )
    requested_rows = required_rows + 60
    lookback_days = max(1_200, requested_rows * 2)
    frame, error = fetch_realtime_ohlcv(
        symbol=symbol,
        interval=timeframe,
        lookback_days=lookback_days,
        tail=requested_rows,
    )
    if error:
        raise RuntimeError(f"Không tải được dữ liệu thật cho {symbol}: {error}")
    if frame is None or frame.empty:
        raise RuntimeError(f"Dữ liệu thật của {symbol} rỗng")

    clean = frame.copy()
    clean["Datetime"] = pd.to_datetime(clean["Datetime"], errors="coerce")
    clean = clean.dropna(subset=["Datetime"]).sort_values("Datetime")
    clean = clean.drop_duplicates(subset=["Datetime"], keep="last")
    if data_cutoff:
        cutoff = pd.Timestamp(data_cutoff).normalize()
        clean = clean.loc[clean["Datetime"].dt.normalize() <= cutoff]
    clean = clean.reset_index(drop=True)

    if len(clean) < required_rows:
        raise ValueError(
            f"{symbol} chỉ có {len(clean)} nến đến cutoff; A20 cần ít nhất "
            f"{required_rows} nến cho W={max_window_size}, S={step}."
        )
    return clean


def _summary_to_result(summary: Any, n_tests: int) -> Dict[str, Any]:
    points = list(summary.test_points)
    if len(points) != n_tests:
        raise RuntimeError(
            f"{summary.symbol} W={summary.window_size}: chỉ hoàn thành "
            f"{len(points)}/{n_tests} điểm."
        )

    invalid = [
        index
        for index, point in enumerate(points, start=1)
        if _point_value(point, "pred_full") not in ("LONG", "SHORT")
        or _point_value(point, "pred_no_alpha") not in ("LONG", "SHORT")
        or bool(_point_value(point, "error_full", ""))
        or bool(_point_value(point, "error_no_alpha", ""))
    ]
    if invalid:
        raise RuntimeError(f"Kết quả chứa điểm lỗi/không nhị phân: {invalid}")

    baseline_predictions = [
        str(_point_value(point, "pred_no_alpha")) for point in points
    ]
    actual_directions = [
        str(_point_value(point, "actual_direction")) for point in points
    ]
    return {
        "n_tests": len(points),
        "window_size": summary.window_size,
        "step": summary.step,
        "data_start": summary.data_start,
        "data_end": summary.data_end,
        "acc_full": summary.acc_full,
        "acc_no_alpha": summary.acc_no_alpha,
        "alpha_lift": summary.alpha_lift,
        "pnl_full": summary.pnl_full,
        "sharpe_full": summary.sharpe_full,
        "mdd_full": summary.mdd_full,
        "pnl_no_alpha": summary.pnl_no_alpha,
        "sharpe_no_alpha": summary.sharpe_no_alpha,
        "mdd_no_alpha": summary.mdd_no_alpha,
        "mcnemar_p_value": summary.mcnemar_p_value,
        "alpha_lift_ci_95": json.dumps(summary.alpha_lift_ci_95),
        "newey_west_p_value": summary.newey_west_p_value,
        "baseline_signature": _prediction_signature(baseline_predictions),
        "_baseline_predictions": baseline_predictions,
        "_actual_directions": actual_directions,
    }


def run_experiment(
    symbol: str,
    timeframe: str,
    config: Dict[str, Any],
    *,
    df: pd.DataFrame,
    n_tests: int,
    window_size: int,
    step: int,
    result_path: Path,
) -> Dict[str, Any]:
    """Chạy đúng một cấu hình và trả về metrics cùng dấu vân tay đối chứng."""

    engine = BacktestEngine(config=deepcopy(config))
    summary = engine.run(
        df=df.copy(),
        symbol=symbol,
        timeframe=timeframe,
        n_tests=n_tests,
        window_size=window_size,
        step=step,
        result_path=str(result_path),
    )
    return _summary_to_result(summary, n_tests)


def _load_checkpoint_points(
    path: Path,
    *,
    symbol: str,
    data_start: str,
    data_end: str,
    n_tests: int,
) -> List[TestPoint]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as checkpoint_file:
        payload = json.load(checkpoint_file)
    if str(payload.get("symbol", "")).upper() != symbol.upper():
        raise RuntimeError(f"Checkpoint sai mã cổ phiếu: {path}")
    if payload.get("data_start") not in (None, data_start) or payload.get(
        "data_end"
    ) not in (None, data_end):
        raise RuntimeError(
            f"Checkpoint {path.name} dùng snapshot dữ liệu khác; "
            "hãy truyền cùng --data-cutoff hoặc di chuyển checkpoint cũ."
        )

    allowed = {item.name for item in fields(TestPoint)}
    restored: List[TestPoint] = []
    for raw in list(payload.get("test_points", []))[:n_tests]:
        values = {key: value for key, value in raw.items() if key in allowed}
        point = TestPoint(**values)
        if (
            point.test_id != len(restored) + 1
            or point.pred_full not in ("LONG", "SHORT")
            or point.pred_no_alpha not in ("LONG", "SHORT")
            or point.error_full
            or point.error_no_alpha
        ):
            break
        restored.append(point)
    return restored


def run_shared_alpha_sweep(
    symbol: str,
    timeframe: str,
    base_config: Dict[str, Any],
    scenarios: Sequence[tuple[str, Dict[str, Any]]],
    *,
    df: pd.DataFrame,
    n_tests: int,
    window_size: int,
    step: int,
    output_dir: Path,
    mode: str,
    protocol: str = "shared_upstream_across_alpha_configs",
    shared_across_alpha_configs: bool = True,
) -> List[Dict[str, Any]]:
    """Chạy một upstream và một baseline cho các cấu hình tại mỗi điểm."""

    engine = BacktestEngine(config=deepcopy(base_config))
    engine._started_at = datetime.now().isoformat()
    engine._init_graphs()
    if engine._use_historical_sentiment:
        engine._init_sentiment_store(symbol, force_recrawl=False)

    lookahead = int(get_forecast_horizon(timeframe)["lookahead_candles"])
    end_indices = build_walk_forward_end_indices(
        total=len(df),
        n_tests=n_tests,
        window_size=window_size,
        step=step,
        lookahead=lookahead,
    )
    checkpoint_paths = {
        name: output_dir / f"checkpoint_{mode}_{symbol}_{name}.json"
        for name, _ in scenarios
    }
    data_start = df["Datetime"].iloc[0].strftime("%Y-%m-%d")
    data_end = df["Datetime"].iloc[-1].strftime("%Y-%m-%d")
    points_by_scenario = {
        name: _load_checkpoint_points(
            checkpoint_paths[name],
            symbol=symbol,
            data_start=data_start,
            data_end=data_end,
            n_tests=n_tests,
        )
        for name, _ in scenarios
    }
    completed_counts = [len(points) for points in points_by_scenario.values()]
    resume_count = min(completed_counts, default=0)
    if completed_counts and max(completed_counts) != resume_count:
        print(
            "[Checkpoint] Một điểm dở dang sẽ được chạy lại; giữ common prefix "
            f"{resume_count}/{n_tests}."
        )
    for scenario in points_by_scenario:
        points_by_scenario[scenario] = points_by_scenario[scenario][:resume_count]
    if resume_count:
        reference = points_by_scenario[scenarios[0][0]]
        for scenario, _ in scenarios[1:]:
            candidate = points_by_scenario[scenario]
            for index in range(resume_count):
                if (
                    candidate[index].window_end != reference[index].window_end
                    or candidate[index].actual_direction
                    != reference[index].actual_direction
                    or candidate[index].pred_no_alpha
                    != reference[index].pred_no_alpha
                ):
                    raise RuntimeError(
                        f"Checkpoint {scenario} không cùng shared control tại "
                        f"test {index + 1}."
                    )
        print(f"[Checkpoint] Tiếp tục từ {resume_count}/{n_tests} điểm chung.")

    for test_index, end_idx in enumerate(
        end_indices[resume_count:], start=resume_count + 1
    ):
        print(f"\n--- {mode}: shared test {test_index}/{n_tests} ---")
        ohlcv, window_start, window_end = engine._prepare_window(
            df, end_idx, window_size
        )
        point_in_time_df = df.iloc[:end_idx].copy()
        actual, prev_close, exit_close, pct_change, entry_open = (
            engine._get_actual_direction(df, end_idx, lookahead)
        )

        pattern_image = trend_image = ""
        try:
            pattern_image = static_util.generate_kline_image(ohlcv).get(
                "pattern_image", ""
            )
            trend_image = static_util.generate_trend_image(ohlcv).get(
                "trend_image", ""
            )
        except Exception as exc:
            print(f"[WARN] Không tạo được ảnh tại test {test_index}: {exc}")

        initial_state = {
            "kline_data": ohlcv,
            "analysis_results": None,
            "messages": [],
            "time_frame": timeframe,
            "stock_name": symbol,
            "pattern_image": pattern_image,
            "trend_image": trend_image,
            "is_backtest": True,
            "sentiment_store": (
                engine._sentiment_store if engine._use_historical_sentiment else None
            ),
            "window_end_date": window_end,
            "point_in_time_df": point_in_time_df,
            "as_of_date": point_in_time_df["Datetime"].iloc[-1],
            "language": engine.config.get("language", "vi"),
        }

        upstream_started = time.time()
        upstream_state = engine._graph_upstream.invoke(initial_state)
        upstream_seconds = time.time() - upstream_started

        baseline_input = deepcopy(upstream_state)
        baseline_input["ablation_config"] = dict(ABLATION_CONFIGS["baseline"])
        baseline_started = time.time()
        baseline_state = engine._graph_decision_variants["baseline"].invoke(
            baseline_input
        )
        baseline_seconds = upstream_seconds + (time.time() - baseline_started)
        pred_baseline, conf_baseline, rr_baseline, source_baseline, reason_baseline = (
            engine._parse_prediction(baseline_state)
        )
        correct_baseline = (
            (pred_baseline == "LONG" and actual == "UP")
            or (pred_baseline == "SHORT" and actual == "DOWN")
        )
        if engine.DELAY_BETWEEN_VARIANTS > 0:
            time.sleep(engine.DELAY_BETWEEN_VARIANTS)

        for scenario_index, (scenario, overrides) in enumerate(scenarios):
            scenario_config = deepcopy(base_config)
            scenario_config.update(deepcopy(overrides))
            full_input = deepcopy(upstream_state)
            full_input["ablation_config"] = dict(ABLATION_CONFIGS["full"])
            full_input["alpha_norm_method"] = scenario_config[
                "alpha_norm_method"
            ]
            full_input["alpha_weights"] = scenario_config["alpha_weights"]

            full_started = time.time()
            full_state = engine._graph_decision_variants["full"].invoke(full_input)
            full_seconds = upstream_seconds + (time.time() - full_started)
            pred_full, conf_full, rr_full, source_full, reason_full = (
                engine._parse_prediction(full_state)
            )
            correct_full = (
                (pred_full == "LONG" and actual == "UP")
                or (pred_full == "SHORT" and actual == "DOWN")
            )
            point = TestPoint(
                test_id=test_index,
                window_start=window_start,
                window_end=window_end,
                actual_prev_close=prev_close,
                actual_next_close=exit_close,
                actual_direction=actual,
                actual_pct_change=pct_change,
                pred_full=pred_full,
                correct_full=correct_full,
                confidence_full=conf_full,
                rr_full=rr_full,
                pred_no_alpha=pred_baseline,
                correct_no_alpha=correct_baseline,
                confidence_no_alpha=conf_baseline,
                rr_no_alpha=rr_baseline,
                time_full_sec=round(full_seconds, 1),
                time_no_alpha_sec=round(baseline_seconds, 1),
                entry_open=entry_open,
                exit_close=exit_close,
                entry_time=pd.Timestamp(df["Datetime"].iloc[end_idx]).isoformat(),
                exit_time=pd.Timestamp(
                    df["Datetime"].iloc[end_idx + lookahead - 1]
                ).isoformat(),
                decision_source_full=source_full,
                decision_source_no_alpha=source_baseline,
                decision_fallback_reason_full=reason_full,
                decision_fallback_reason_no_alpha=reason_baseline,
            )
            points_by_scenario[scenario].append(point)
            partial = engine._compute_partial(points_by_scenario[scenario])
            engine._save(
                str(checkpoint_paths[scenario]),
                {
                    "symbol": symbol,
                    "panel": mode,
                    "scenario": scenario,
                    "protocol": protocol,
                    "n_tests": n_tests,
                    "window_size": window_size,
                    "step": step,
                    "data_start": data_start,
                    "data_end": data_end,
                    "partial": asdict(partial),
                    "test_points": [
                        asdict(item) for item in points_by_scenario[scenario]
                    ],
                },
            )
            if (
                scenario_index < len(scenarios) - 1
                and engine.DELAY_BETWEEN_VARIANTS > 0
            ):
                time.sleep(engine.DELAY_BETWEEN_VARIANTS)

        if test_index < n_tests and engine.DELAY_BETWEEN_TESTS > 0:
            time.sleep(engine.DELAY_BETWEEN_TESTS)

    results: List[Dict[str, Any]] = []
    for scenario, overrides in scenarios:
        summary = engine._build_summary(
            symbol,
            timeframe,
            n_tests,
            window_size,
            step,
            points_by_scenario[scenario],
            data_start,
            data_end,
        )
        engine._save(
            str(checkpoint_paths[scenario]),
            {
                **asdict(summary),
                "panel": mode,
                "scenario": scenario,
                "protocol": protocol,
            },
        )
        row = _summary_to_result(summary, n_tests)
        row["upstream_invocations"] = n_tests
        row["baseline_invocations"] = n_tests
        row["shared_across_alpha_configs"] = shared_across_alpha_configs
        results.append(row)
    return results


def validate_sweep_results(
    results: Sequence[Dict[str, Any]],
    *,
    n_tests: int,
    require_invariant_control: bool,
) -> None:
    """Nghiệm thu N và common-support; Panel B/C phải có control giống hệt."""

    if len(results) != 3:
        raise RuntimeError(f"Sweep phải có đúng 3 cấu hình, hiện có {len(results)}.")
    incomplete = [row.get("scenario") for row in results if row.get("n_tests") != n_tests]
    if incomplete:
        raise RuntimeError(f"Các cấu hình không đạt N={n_tests}: {incomplete}")
    if not require_invariant_control:
        return

    reference_actual = results[0]["_actual_directions"]
    reference_control = results[0]["_baseline_predictions"]
    for row in results[1:]:
        if row["_actual_directions"] != reference_actual:
            raise RuntimeError(
                f"{row['scenario']} không dùng cùng common support với cấu hình chuẩn."
            )
        if row["_baseline_predictions"] != reference_control:
            raise RuntimeError(
                "No-Alpha không bất biến tuyệt đối; dừng xuất CSV thay vì che giấu "
                f"control instability ở cấu hình {row['scenario']}."
            )

    accuracies = {float(row["acc_no_alpha"]) for row in results}
    if len(accuracies) != 1:
        raise RuntimeError(f"Acc No-Alpha không bất biến: {sorted(accuracies)}")


def save_results(
    results: Sequence[Dict[str, Any]],
    out_dir: Path,
    prefix: str,
    symbol: str,
) -> Path:
    """Lưu CSV sạch, không ghi các mảng nội bộ dùng để nghiệm thu."""

    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = out_dir / f"{prefix}_{symbol}_{timestamp}.csv"
    public_rows = [
        {key: value for key, value in row.items() if not key.startswith("_")}
        for row in results
    ]
    pd.DataFrame(public_rows).to_csv(out_file, index=False)
    print(f"\n[OK] Robustness sweep đã lưu tại: {out_file}")
    return out_file


def run_sweep(
    mode: str,
    symbol: str,
    *,
    n_tests: int = DEFAULT_N_TESTS,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    data_cutoff: str | None = None,
) -> Path:
    """Chạy một panel robustness trên một mã với đúng ba cấu hình A20."""

    if n_tests != DEFAULT_N_TESTS:
        raise ValueError("TASK-09 yêu cầu cố định n_tests=20 cho mọi cấu hình.")
    if mode not in {"hyperparams", "norm", "weights"}:
        raise ValueError(f"Mode không hợp lệ: {mode}")

    random.seed(SEED)
    np.random.seed(SEED)
    symbol = symbol.upper()
    timeframe = "1d"
    max_window = 60 if mode == "hyperparams" else DEFAULT_WINDOW
    market_data = load_market_data(
        symbol,
        n_tests=n_tests,
        max_window_size=max_window,
        step=DEFAULT_STEP,
        timeframe=timeframe,
        data_cutoff=data_cutoff,
    )

    base_config: Dict[str, Any] = {
        "allow_shorting": False,
        "tx_cost": 0.0025,
        "slippage": 0.001,
        "alpha_norm_method": "zscore_tanh",
        "alpha_weights": {"ic": 0.40, "acc": 0.35, "sharpe": 0.25},
        "agent_llm_temperature": 0.0,
        "graph_llm_temperature": 0.0,
    }
    results: List[Dict[str, Any]] = []
    output_dir.mkdir(parents=True, exist_ok=True)
    if mode == "hyperparams":
        for scenario, window_size in WINDOW_SCENARIOS:
            print(f"\n--- {mode}: {scenario}, N={n_tests}, W={window_size} ---")
            row = run_shared_alpha_sweep(
                symbol,
                timeframe,
                base_config,
                [(scenario, {})],
                df=market_data,
                n_tests=n_tests,
                window_size=window_size,
                step=DEFAULT_STEP,
                output_dir=output_dir,
                mode=mode,
                protocol="paired_shared_reports",
                shared_across_alpha_configs=False,
            )[0]
            row.update(
                {
                    "symbol": symbol,
                    "panel": mode,
                    "scenario": scenario,
                    "norm_method": base_config["alpha_norm_method"],
                    "alpha_weights": json.dumps(
                        base_config["alpha_weights"], sort_keys=True
                    ),
                    "protocol": "paired_shared_reports",
                    "seed": SEED,
                }
            )
            results.append(row)
    else:
        if mode == "norm":
            alpha_scenarios = [
                (name, {"alpha_norm_method": norm})
                for name, norm in NORM_SCENARIOS
            ]
        else:
            alpha_scenarios = [
                (name, {"alpha_weights": weights})
                for name, weights in WEIGHT_SCENARIOS
            ]
        results = run_shared_alpha_sweep(
            symbol,
            timeframe,
            base_config,
            alpha_scenarios,
            df=market_data,
            n_tests=n_tests,
            window_size=DEFAULT_WINDOW,
            step=DEFAULT_STEP,
            output_dir=output_dir,
            mode=mode,
        )
        for row, (scenario, overrides) in zip(results, alpha_scenarios):
            config = deepcopy(base_config)
            config.update(deepcopy(overrides))
            row.update({
                "symbol": symbol,
                "panel": mode,
                "scenario": scenario,
                "norm_method": config["alpha_norm_method"],
                "alpha_weights": json.dumps(config["alpha_weights"], sort_keys=True),
                "protocol": "shared_upstream_across_alpha_configs",
                "seed": SEED,
            })

    validate_sweep_results(
        results,
        n_tests=n_tests,
        require_invariant_control=mode in {"norm", "weights"},
    )
    return save_results(results, output_dir, f"sweep_{mode}", symbol)


def main() -> None:
    load_dotenv(REPO_ROOT / ".env", override=False)
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="Chạy Robustness Sweep A20 theo paired shared-reports."
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=["hyperparams", "norm", "weights"],
        help="Panel A=hyperparams, Panel B=norm, Panel C=weights.",
    )
    parser.add_argument("--symbol", default="FPT")
    parser.add_argument("--n_tests", type=int, default=DEFAULT_N_TESTS)
    parser.add_argument("--data-cutoff", help="Ngày dữ liệu cuối YYYY-MM-DD.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    arguments = parser.parse_args()

    print("=" * 64)
    print(
        f"TASK-09: {arguments.mode.upper()} | {arguments.symbol.upper()} | "
        f"N={arguments.n_tests}"
    )
    print("=" * 64)
    run_sweep(
        arguments.mode,
        arguments.symbol,
        n_tests=arguments.n_tests,
        output_dir=Path(arguments.output_dir),
        data_cutoff=arguments.data_cutoff,
    )


if __name__ == "__main__":
    main()
