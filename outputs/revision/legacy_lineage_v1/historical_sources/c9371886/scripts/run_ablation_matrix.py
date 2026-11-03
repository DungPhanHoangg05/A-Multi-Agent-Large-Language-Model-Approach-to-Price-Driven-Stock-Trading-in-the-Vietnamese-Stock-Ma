"""Chạy ma trận ablation 4 biến thể trên cùng shared upstream snapshot."""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime
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

from core.backtest_engine import (  # noqa: E402
    BacktestEngine,
    TestPoint,
    build_walk_forward_end_indices,
    compute_account_metrics,
)
from core.run_robustness import load_market_data  # noqa: E402
from utils.graph_setup import ABLATION_CONFIGS  # noqa: E402
from utils.statistical_tests import calculate_metrics_with_significance  # noqa: E402
from utils.static_util import get_forecast_horizon  # noqa: E402


VARIANTS = ("full", "alpha_only", "sentiment_only", "baseline")
DEFAULT_SYMBOLS = ("FPT", "VNM", "VCB")
DEFAULT_OUTPUT_DIR = Path("outputs/ablation/clean_a20")
DEFAULT_N_TESTS = 20
DEFAULT_WINDOW = 45
DEFAULT_STEP = 3
SEED = 42


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as output_file:
        json.dump(payload, output_file, ensure_ascii=False, indent=2)
    temporary.replace(path)


def _valid_completed_point(point: Dict[str, Any], expected_id: int) -> bool:
    if int(point.get("test_id", -1)) != expected_id:
        return False
    variants = point.get("variants")
    if not isinstance(variants, dict) or set(variants) != set(VARIANTS):
        return False
    for variant in VARIANTS:
        result = variants[variant]
        if result.get("prediction") not in ("LONG", "SHORT"):
            return False
        if result.get("error"):
            return False
    return point.get("actual_direction") in ("UP", "DOWN")


def load_checkpoint(
    path: Path,
    *,
    symbol: str,
    n_tests: int,
    window_size: int,
    step: int,
    data_start: str,
    data_end: str,
) -> List[Dict[str, Any]]:
    """Khôi phục tiền tố checkpoint hợp lệ trên đúng snapshot dữ liệu."""

    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as checkpoint_file:
        payload = json.load(checkpoint_file)

    expected = {
        "symbol": symbol,
        "n_tests": n_tests,
        "window_size": window_size,
        "step": step,
        "data_start": data_start,
        "data_end": data_end,
    }
    mismatches = {
        key: (payload.get(key), value)
        for key, value in expected.items()
        if payload.get(key) != value
    }
    if mismatches:
        raise RuntimeError(
            f"Checkpoint {path.name} không khớp cấu hình/snapshot: {mismatches}"
        )

    restored: List[Dict[str, Any]] = []
    for raw_point in list(payload.get("test_points", []))[:n_tests]:
        if not _valid_completed_point(raw_point, len(restored) + 1):
            break
        restored.append(raw_point)
    return restored


def _checkpoint_payload(
    *,
    symbol: str,
    n_tests: int,
    window_size: int,
    step: int,
    data_start: str,
    data_end: str,
    points: Sequence[Dict[str, Any]],
    summary: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    return {
        "symbol": symbol,
        "timeframe": "1d",
        "n_tests": n_tests,
        "window_size": window_size,
        "step": step,
        "data_start": data_start,
        "data_end": data_end,
        "seed": SEED,
        "protocol": "four_way_shared_upstream",
        "variants": list(VARIANTS),
        "updated_at": datetime.now().isoformat(),
        "status": "complete" if len(points) == n_tests else "partial",
        "completed": len(points),
        "summary": summary,
        "test_points": list(points),
    }


def _variant_test_points(
    points: Sequence[Dict[str, Any]], variant: str
) -> List[TestPoint]:
    converted: List[TestPoint] = []
    for point in points:
        result = point["variants"][variant]
        prediction = result["prediction"]
        converted.append(
            TestPoint(
                test_id=int(point["test_id"]),
                window_start=point["window_start"],
                window_end=point["window_end"],
                actual_prev_close=float(point["actual_prev_close"]),
                actual_next_close=float(point["actual_next_close"]),
                actual_direction=point["actual_direction"],
                actual_pct_change=float(point["actual_pct_change"]),
                pred_full=prediction,
                correct_full=bool(result["correct"]),
                confidence_full=str(result.get("confidence", "N/A")),
                rr_full=str(result.get("risk_reward_ratio", "N/A")),
                pred_no_alpha=prediction,
                correct_no_alpha=bool(result["correct"]),
                confidence_no_alpha=str(result.get("confidence", "N/A")),
                rr_no_alpha=str(result.get("risk_reward_ratio", "N/A")),
                time_full_sec=float(result.get("time_sec", 0.0)),
                time_no_alpha_sec=float(result.get("time_sec", 0.0)),
                entry_open=float(point["entry_open"]),
                exit_close=float(point["exit_close"]),
                entry_time=point["entry_time"],
                exit_time=point["exit_time"],
                decision_source_full=str(result.get("decision_source", "")),
                decision_source_no_alpha=str(result.get("decision_source", "")),
            )
        )
    return converted


def summarize_symbol(
    symbol: str,
    points: Sequence[Dict[str, Any]],
    *,
    config: Dict[str, Any],
    data_start: str,
    data_end: str,
) -> Dict[str, Any]:
    """Tính accuracy, kiểm định và P&L cho từng biến thể trên common support."""

    if len(points) != DEFAULT_N_TESTS:
        raise RuntimeError(f"{symbol}: chỉ có {len(points)}/{DEFAULT_N_TESTS} điểm")
    actuals = [point["actual_direction"] for point in points]
    predictions = {
        variant: [point["variants"][variant]["prediction"] for point in points]
        for variant in VARIANTS
    }
    baseline_predictions = predictions["baseline"]
    rows: List[Dict[str, Any]] = []

    for variant in VARIANTS:
        variant_points = _variant_test_points(points, variant)
        account = compute_account_metrics(
            variant_points,
            fee=config["tx_cost"],
            slippage=config["slippage"],
            initial_capital_vnd=config.get("initial_capital_vnd", 50_000_000.0),
            price_multiplier=config.get("price_multiplier", 1_000.0),
        )["full"]
        correct = [
            (prediction == "LONG" and actual == "UP")
            or (prediction == "SHORT" and actual == "DOWN")
            for actual, prediction in zip(actuals, predictions[variant])
        ]
        accuracy = sum(correct) / len(correct) * 100.0
        significance = calculate_metrics_with_significance(
            actuals,
            predictions[variant],
            baseline_predictions,
            random_seed=SEED,
        )
        long_correct = sum(
            is_correct
            for is_correct, prediction in zip(correct, predictions[variant])
            if prediction == "LONG"
        )
        short_correct = sum(
            is_correct
            for is_correct, prediction in zip(correct, predictions[variant])
            if prediction == "SHORT"
        )
        n_long = predictions[variant].count("LONG")
        n_short = predictions[variant].count("SHORT")
        rows.append(
            {
                "symbol": symbol,
                "variant": variant,
                "enable_alpha_factors": ABLATION_CONFIGS[variant][
                    "enable_alpha_factors"
                ],
                "enable_sentiment": ABLATION_CONFIGS[variant]["enable_sentiment"],
                "n_tests": len(points),
                "accuracy": round(accuracy, 1),
                "baseline_accuracy": None,
                "delta_vs_baseline_pp": None,
                "n_long": n_long,
                "n_short": n_short,
                "long_win_rate": round(long_correct / n_long * 100.0, 1)
                if n_long
                else 0.0,
                "short_win_rate": round(short_correct / n_short * 100.0, 1)
                if n_short
                else 0.0,
                "account_return_pct": round(account.total_return_pct, 2),
                "sharpe_ratio": round(account.sharpe_ratio, 2),
                "sortino_ratio": round(account.sortino_ratio, 2),
                "max_drawdown_pct": round(account.max_drawdown_pct, 2),
                "hit_rate_pct": round(account.hit_rate_pct, 1),
                "mcnemar_p_value_vs_baseline": significance["mcnemar_p_value"],
                "lift_ci_95_vs_baseline": significance["alpha_lift_ci_95"],
                "newey_west_p_value_vs_baseline": significance[
                    "newey_west_p_value"
                ],
                "data_start": data_start,
                "data_end": data_end,
                "window_size": DEFAULT_WINDOW,
                "step": DEFAULT_STEP,
                "protocol": "four_way_shared_upstream",
                "seed": SEED,
            }
        )

    accuracy_by_variant = {row["variant"]: row["accuracy"] for row in rows}
    baseline_accuracy = accuracy_by_variant["baseline"]
    contributions = {
        "alpha_contribution_pp": round(
            accuracy_by_variant["alpha_only"] - baseline_accuracy, 1
        ),
        "sentiment_contribution_pp": round(
            accuracy_by_variant["sentiment_only"] - baseline_accuracy, 1
        ),
        "synergy_pp": round(
            accuracy_by_variant["full"]
            - max(
                accuracy_by_variant["alpha_only"],
                accuracy_by_variant["sentiment_only"],
            ),
            1,
        ),
        "full_lift_pp": round(accuracy_by_variant["full"] - baseline_accuracy, 1),
    }
    for row in rows:
        row["baseline_accuracy"] = baseline_accuracy
        row["delta_vs_baseline_pp"] = round(row["accuracy"] - baseline_accuracy, 1)
        row.update(contributions)

    return {
        "symbol": symbol,
        "n_tests": len(points),
        "data_start": data_start,
        "data_end": data_end,
        "contributions": contributions,
        "rows": rows,
    }


def run_symbol(
    symbol: str,
    *,
    df: pd.DataFrame,
    output_dir: Path,
    n_tests: int = DEFAULT_N_TESTS,
    window_size: int = DEFAULT_WINDOW,
    step: int = DEFAULT_STEP,
    timeframe: str = "1d",
    config: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Chạy/resume một mã, chỉ checkpoint sau khi đủ cả bốn biến thể."""

    if n_tests != DEFAULT_N_TESTS:
        raise ValueError("TASK-10 yêu cầu cố định n_tests=20")
    config = deepcopy(
        config
        or {
            "allow_shorting": False,
            "tx_cost": 0.0025,
            "slippage": 0.001,
            "alpha_norm_method": "zscore_tanh",
            "alpha_weights": {"ic": 0.40, "acc": 0.35, "sharpe": 0.25},
            "agent_llm_temperature": 0.0,
            "graph_llm_temperature": 0.0,
        }
    )
    symbol = symbol.upper()
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = output_dir / f"checkpoint_ablation_{symbol}.json"
    data_start = df["Datetime"].iloc[0].strftime("%Y-%m-%d")
    data_end = df["Datetime"].iloc[-1].strftime("%Y-%m-%d")

    points = load_checkpoint(
        checkpoint,
        symbol=symbol,
        n_tests=n_tests,
        window_size=window_size,
        step=step,
        data_start=data_start,
        data_end=data_end,
    )
    if points:
        print(f"[Checkpoint] {symbol}: tiếp tục từ {len(points)}/{n_tests} điểm.")

    engine = BacktestEngine(config=config)
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

    for test_index, end_idx in enumerate(
        end_indices[len(points) :], start=len(points) + 1
    ):
        print(f"\n--- {symbol}: ablation test {test_index}/{n_tests} ---")
        ohlcv, window_start, window_end = engine._prepare_window(
            df, end_idx, window_size
        )
        point_in_time_df = df.iloc[:end_idx].copy()
        actual, prev_close, exit_close, pct_change, entry_open = (
            engine._get_actual_direction(df, end_idx, lookahead)
        )
        states = engine._run_ablation_variants(
            ohlcv,
            symbol,
            timeframe,
            window_end_date=window_end,
            point_in_time_df=point_in_time_df,
            variants=VARIANTS,
        )

        variant_results: Dict[str, Dict[str, Any]] = {}
        for variant in VARIANTS:
            state, elapsed = states[variant]
            prediction, confidence, risk_reward, source, fallback_reason = (
                engine._parse_prediction(state)
            )
            error = str(state.get("decision_error", ""))[:200]
            if error:
                raise RuntimeError(f"{symbol} test {test_index} {variant}: {error}")
            correct = (prediction == "LONG" and actual == "UP") or (
                prediction == "SHORT" and actual == "DOWN"
            )
            variant_results[variant] = {
                "prediction": prediction,
                "correct": bool(correct),
                "confidence": confidence,
                "risk_reward_ratio": risk_reward,
                "time_sec": round(float(elapsed), 1),
                "decision_source": source,
                "fallback_reason": fallback_reason,
                "error": "",
            }

        point = {
            "test_id": test_index,
            "window_start": window_start,
            "window_end": window_end,
            "actual_prev_close": prev_close,
            "actual_next_close": exit_close,
            "actual_direction": actual,
            "actual_pct_change": pct_change,
            "entry_open": entry_open,
            "exit_close": exit_close,
            "entry_time": pd.Timestamp(df["Datetime"].iloc[end_idx]).isoformat(),
            "exit_time": pd.Timestamp(
                df["Datetime"].iloc[end_idx + lookahead - 1]
            ).isoformat(),
            "variants": variant_results,
        }
        if not _valid_completed_point(point, test_index):
            raise RuntimeError(f"{symbol} test {test_index}: điểm ablation không hợp lệ")
        points.append(point)
        _atomic_write_json(
            checkpoint,
            _checkpoint_payload(
                symbol=symbol,
                n_tests=n_tests,
                window_size=window_size,
                step=step,
                data_start=data_start,
                data_end=data_end,
                points=points,
            ),
        )
        if test_index < n_tests and engine.DELAY_BETWEEN_TESTS > 0:
            time.sleep(engine.DELAY_BETWEEN_TESTS)

    summary = summarize_symbol(
        symbol,
        points,
        config=config,
        data_start=data_start,
        data_end=data_end,
    )
    _atomic_write_json(
        checkpoint,
        _checkpoint_payload(
            symbol=symbol,
            n_tests=n_tests,
            window_size=window_size,
            step=step,
            data_start=data_start,
            data_end=data_end,
            points=points,
            summary=summary,
        ),
    )
    return summary


def save_aggregate(
    summaries: Sequence[Dict[str, Any]], output_dir: Path
) -> tuple[Path, Path]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = output_dir / f"ablation_matrix_{timestamp}.csv"
    json_path = output_dir / f"ablation_matrix_{timestamp}.json"
    rows = [row for summary in summaries for row in summary["rows"]]
    csv_rows = []
    for row in rows:
        csv_row = dict(row)
        csv_row["lift_ci_95_vs_baseline"] = json.dumps(
            csv_row["lift_ci_95_vs_baseline"]
        )
        csv_rows.append(csv_row)
    pd.DataFrame(csv_rows).to_csv(csv_path, index=False)
    _atomic_write_json(
        json_path,
        {
            "generated_at": datetime.now().isoformat(),
            "protocol": "four_way_shared_upstream",
            "seed": SEED,
            "symbols": [summary["symbol"] for summary in summaries],
            "summaries": list(summaries),
        },
    )
    return csv_path, json_path


def run_matrix(
    symbols: Sequence[str],
    *,
    n_tests: int = DEFAULT_N_TESTS,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    data_cutoff: str | None = None,
) -> tuple[Path, Path]:
    if n_tests != DEFAULT_N_TESTS:
        raise ValueError("TASK-10 yêu cầu --n_tests 20")
    normalized_symbols = tuple(symbol.strip().upper() for symbol in symbols if symbol.strip())
    if normalized_symbols != DEFAULT_SYMBOLS:
        raise ValueError("TASK-10 yêu cầu đúng ba mã theo thứ tự FPT,VNM,VCB")

    random.seed(SEED)
    np.random.seed(SEED)
    summaries = []
    for symbol in normalized_symbols:
        print("=" * 64)
        print(f"TASK-10 | {symbol} | 4-WAY ABLATION | N={n_tests}")
        print("=" * 64)
        market_data = load_market_data(
            symbol,
            n_tests=n_tests,
            max_window_size=DEFAULT_WINDOW,
            step=DEFAULT_STEP,
            timeframe="1d",
            data_cutoff=data_cutoff,
        )
        summaries.append(
            run_symbol(
                symbol,
                df=market_data,
                output_dir=output_dir,
                n_tests=n_tests,
            )
        )

    csv_path, json_path = save_aggregate(summaries, output_dir)
    mean_alpha_contribution = float(
        np.mean(
            [
                summary["contributions"]["alpha_contribution_pp"]
                for summary in summaries
            ]
        )
    )
    print(f"\n[OK] CSV: {csv_path}")
    print(f"[OK] JSON: {json_path}")
    print(f"[INFO] Mean Alpha-only contribution: {mean_alpha_contribution:+.2f} pp")
    if mean_alpha_contribution <= 0.0:
        print("[WARN] Dữ liệu thực nghiệm không đạt tiêu chí ΔAcc_alpha trung bình > 0.")
    return csv_path, json_path


def main() -> None:
    load_dotenv(REPO_ROOT / ".env", override=False)
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Chạy TASK-10 4-way ablation matrix.")
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--n_tests", type=int, default=DEFAULT_N_TESTS)
    parser.add_argument("--data-cutoff", help="Ngày dữ liệu cuối YYYY-MM-DD.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    arguments = parser.parse_args()
    run_matrix(
        arguments.symbols.split(","),
        n_tests=arguments.n_tests,
        output_dir=Path(arguments.output_dir),
        data_cutoff=arguments.data_cutoff,
    )


if __name__ == "__main__":
    main()
