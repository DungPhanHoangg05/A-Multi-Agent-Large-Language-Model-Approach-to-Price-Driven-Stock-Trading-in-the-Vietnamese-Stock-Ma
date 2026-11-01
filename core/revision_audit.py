"""Đối soát R1 từ kết quả legacy, không gọi LLM hoặc tải dữ liệu mới."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from utils.statistical_tests import binary_classification_metrics


VARIANTS = ("full", "base_reports_legacy", "constant_down_cash", "constant_up_cycles")
GROUP_FIELDS = ("fold", "regime", "repeat_id")
DEFAULT_SYMBOLS = ("BHN", "CMG", "FPT", "HVN", "MBB", "MWG", "VCB", "VJC", "VNM")


def sha256_file(path: Path) -> str:
    """Hash nguyên byte, không chuẩn hóa line ending hoặc JSON."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _positive(value: object, name: str) -> float:
    """Từ chối giá hoặc vốn thiếu, không hữu hạn hay không dương."""
    parsed = float(value)
    if not np.isfinite(parsed) or parsed <= 0.0:
        raise ValueError(f"{name} phải là số dương hữu hạn")
    return parsed


def _costs(fee: float, slippage: float) -> tuple[float, float]:
    """Kiểm tra chi phí trước khi tái tính công thức tài khoản legacy."""
    fee, slippage = float(fee), float(slippage)
    if not all(np.isfinite(x) and 0.0 <= x < 1.0 for x in (fee, slippage)):
        raise ValueError("fee/slippage phải hữu hạn, không âm và nhỏ hơn 1")
    if fee + slippage >= 1.0:
        raise ValueError("Tổng fee + slippage phải nhỏ hơn 1")
    return fee, slippage


def round_trip_net_return(entry_open: float, exit_close: float, fee: float, slippage: float) -> float:
    """Replay công thức phí hai chiều độc lập với engine đang được kiểm toán."""
    fee, slippage = _costs(fee, slippage)
    entry = _positive(entry_open, "entry_open")
    exit_price = _positive(exit_close, "exit_close")
    return float(exit_price / entry * (1 - fee) * (1 - slippage) / ((1 + fee) * (1 + slippage)) - 1)


def cycle_account_metrics(
    points: Sequence[dict[str, Any]], predictions: Sequence[str], fee: float, slippage: float,
    initial_capital_vnd: float,
) -> dict[str, Any]:
    """Replay tài khoản độc lập, fractional shares và tiền tái dùng ngay như legacy.

    Không gọi cycle-end drawdown là daily drawdown; thiếu một prediction hợp lệ
    thì không công bố return trên support bị cắt hoặc tự thay lỗi bằng CASH.
    """
    if len(points) != len(predictions):
        raise ValueError("Số point và prediction phải bằng nhau")
    fee, slippage = _costs(fee, slippage)
    capital = _positive(initial_capital_vnd, "initial_capital_vnd")
    missing = sum(pred not in ("LONG", "SHORT") for pred in predictions)
    if missing or not points:
        return {"status": "unavailable", "n_invalid_predictions": missing, "net_return_pct": None}
    long_mask = np.asarray([pred == "LONG" for pred in predictions])
    entries = np.asarray([_positive(p["entry_open"], "entry_open") for p in points])
    exits = np.asarray([_positive(p["exit_close"], "exit_close") for p in points])
    factors = exits / entries * (1 - fee) * (1 - slippage) / ((1 + fee) * (1 + slippage))
    multipliers = np.where(long_mask, factors, 1.0)
    equity = np.concatenate(([1.0], np.cumprod(multipliers)))
    before = capital * equity[:-1]
    buy_notional = np.where(long_mask, before / (1 + fee), 0.0)
    quoted_buy = buy_notional / (1 + slippage)
    quoted_sell = quoted_buy * exits / entries
    sell_notional = quoted_sell * (1 - slippage)
    fees = fee * (buy_notional + sell_notional)
    slippage_cost = slippage * (quoted_buy + quoted_sell)
    drawdown = 1.0 - equity / np.maximum.accumulate(equity)
    long_cycles = int(np.sum(long_mask))
    return {
        "status": "legacy_idealized_replay",
        "n_cycles": len(points),
        "long_cycles": long_cycles,
        "order_count": 2 * long_cycles,
        "long_cycle_fraction": float(long_cycles / len(points)),
        "net_return_pct": float((equity[-1] - 1) * 100),
        "initial_capital_vnd": capital,
        "final_equity_vnd": float(capital * equity[-1]),
        "cycle_end_drawdown_pct": float(np.max(drawdown) * 100),
        "brokerage_fee_vnd": float(np.sum(fees)),
        "slippage_cost_vnd": float(np.sum(slippage_cost)),
        "gross_traded_notional_vnd": float(np.sum(quoted_buy + quoted_sell)),
        "traded_notional_over_initial_capital": float(np.sum(quoted_buy + quoted_sell) / capital),
        "daily_exposure": None,
        "daily_drawdown_pct": None,
        "daily_turnover": None,
        "equity_curve": [float(x) for x in equity],
    }


def _predictions(points: Sequence[dict[str, Any]], variant: str) -> list[str]:
    """Giữ nguyên control legacy, chỉ đổi tên hiển thị cho đúng thông tin bị bỏ."""
    if variant == "constant_down_cash":
        return ["SHORT"] * len(points)
    if variant == "constant_up_cycles":
        return ["LONG"] * len(points)
    key = "pred_full" if variant == "full" else "pred_no_alpha"
    return [str(p[key]).strip().upper() for p in points]


def _classification(points: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Báo cùng support cho so sánh chính và support riêng để thấy failure rate."""
    actuals = [p["actual_direction"] for p in points]
    own_support = {
        v: binary_classification_metrics(actuals, _predictions(points, v)) for v in VARIANTS
    }
    paired = [p for p in points if p["pred_full"] in ("LONG", "SHORT")
              and p["pred_no_alpha"] in ("LONG", "SHORT")]
    common_support = {
        v: binary_classification_metrics([p["actual_direction"] for p in paired], _predictions(paired, v))
        for v in VARIANTS
    }
    return {"n_input": len(points), "n_common_support": len(paired),
            "own_support": own_support, "common_support": common_support}


def _bar_date(value: str) -> date:
    """Chỉ dùng ngày của timestamp daily bar; không suy đây là giờ khớp lệnh."""
    return datetime.fromisoformat(value).date()


def _validate_points(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Từ chối chu kỳ thiếu giá chuẩn, trùng cutoff, sai thứ tự hoặc chồng lấn."""
    points = payload["test_points"]
    if not points or payload["n_tests"] != len(points):
        raise ValueError("n_tests phải khớp tập test_points không rỗng")
    seen_ids, seen_dates = set(), set()
    previous_exit = None
    for point in points:
        if point["actual_direction"] not in ("UP", "DOWN"):
            raise ValueError("Nhãn legacy phải là UP hoặc DOWN đã trưởng thành")
        for field in ("pred_full", "pred_no_alpha"):
            if point[field] not in ("LONG", "SHORT", "UNKNOWN", ""):
                raise ValueError(f"Prediction legacy không hợp lệ: {point[field]!r}")
        decision = _bar_date(point["window_end"])
        entry, exit_day = _bar_date(point["entry_time"]), _bar_date(point["exit_time"])
        if not decision < entry <= exit_day or (previous_exit is not None and entry <= previous_exit):
            raise ValueError("Thứ tự decision/entry/exit hoặc chu kỳ không hợp lệ")
        if point["test_id"] in seen_ids or decision in seen_dates:
            raise ValueError("Trùng test_id hoặc cutoff trong một artifact")
        seen_ids.add(point["test_id"])
        seen_dates.add(decision)
        previous_exit = exit_day
        _positive(point["entry_open"], "entry_open")
        _positive(point["exit_close"], "exit_close")
    return points


def build_legacy_report(
    paths: Sequence[Path], root: Path, fee: float = 0.0025, slippage: float = 0.001,
) -> dict[str, Any]:
    """Tái tính phân loại/kinh tế và groups thực có; không tạo folds/regimes giả."""
    fee, slippage = _costs(fee, slippage)
    per_symbol, source_records, all_points, notes = {}, [], [], []
    reported_returns: dict[str, list[float | None]] = {"full": [], "base_reports_legacy": []}
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for path in sorted(paths):
        raw = path.read_bytes()
        payload = json.loads(raw)
        symbol = payload["symbol"]
        if symbol in per_symbol:
            raise ValueError(f"Nhiều artifact cho {symbol}; phải chọn rõ release, không chọn file mới nhất")
        points = _validate_points(payload)
        mismatches = []
        for point in points:
            value = round_trip_net_return(point["entry_open"], point["exit_close"], fee, slippage)
            if point["actual_direction"] != ("UP" if value > 0 else "DOWN"):
                raise ValueError(f"{symbol}/{point['test_id']}: nhãn không khớp giá chuẩn và chi phí đã khai báo")
            for variant, field in (("full", "pred_full"), ("no_alpha", "pred_no_alpha")):
                pred = point[field]
                correct = (pred == "LONG" and point["actual_direction"] == "UP") or (
                    pred == "SHORT" and point["actual_direction"] == "DOWN")
                stored = point.get(f"correct_{variant}")
                if stored is not None and stored != correct:
                    mismatches.append({"test_id": point["test_id"], "field": f"correct_{variant}"})
            for field in GROUP_FIELDS:
                value_group = point.get(field, payload.get(field))
                if value_group is not None:
                    groups[(symbol, field, str(value_group))].append(point)
        classification = _classification(points)
        economics = {
            v: cycle_account_metrics(points, _predictions(points, v), fee, slippage,
                                     payload["initial_capital_vnd"])
            for v in VARIANTS
        }
        # Bảng cũ làm tròn đến 0,01%; không lấy trung bình số đã làm tròn thay replay.
        for v, stored_key in (("full", "pnl_full"), ("base_reports_legacy", "pnl_no_alpha")):
            replay = economics[v]["net_return_pct"]
            stored_return = payload.get(stored_key)
            reported_returns[v].append(stored_return)
            if replay is not None and stored_return is not None and abs(replay - stored_return) > 0.0051:
                notes.append({"symbol": symbol, "field": stored_key,
                              "stored": stored_return, "recomputed": replay})
        if mismatches:
            notes.append({"symbol": symbol, "stored_correct_mismatches": mismatches})
        per_symbol[symbol] = {"classification": classification, "economics": economics,
                              "api_error_flag_counts": {
                                  "full": sum(bool(p.get("error_full")) for p in points),
                                  "base_reports_legacy": sum(bool(p.get("error_no_alpha")) for p in points)},
                              "decision_dates": [p["window_end"] for p in points]}
        all_points.extend(points)
        source_records.append({"path": path.resolve().relative_to(root.resolve()).as_posix(),
                               "sha256": hashlib.sha256(raw).hexdigest(), "n_points": len(points)})
    if not per_symbol:
        raise ValueError("Không có artifact benchmark để đối soát")
    macro = {}
    for v in VARIANTS:
        macro[v] = {}
        for metric in ("accuracy", "balanced_accuracy", "mcc", "macro_f1", "long_rate"):
            values = [r["classification"]["common_support"][v][metric] for r in per_symbol.values()]
            defined = [x for x in values if x is not None]
            macro[v][metric] = {"mean": float(np.mean(defined)) if len(defined) == len(values) else None,
                                "n_defined_symbols": len(defined), "n_symbols": len(values)}
    means = {}
    for v in VARIANTS:
        values = [r["economics"][v]["net_return_pct"] for r in per_symbol.values()]
        means[v] = float(np.mean(values)) if all(x is not None for x in values) else None
    return {
        "schema_version": "r1_legacy_audit_v1",
        "evidence_status": "exploratory_legacy_replay_not_confirmatory",
        "target": "net_next_open_to_horizon_close_positive",
        "metric_rate_unit": "fraction_0_1",
        "undefined_policy": "null; macro mean requires all symbols defined",
        "cost_assumptions": {"fee_each_side": fee, "slippage_each_side": slippage,
                             "provenance": "explicit_replay_assumptions_not_historical_request_logs"},
        "sources": source_records,
        "n_symbols": len(per_symbol), "n_points": len(all_points),
        "n_distinct_decision_dates": len({p["window_end"] for p in all_points}),
        "missing_group_fields": [f for f in GROUP_FIELDS if not any(k[1] == f for k in groups)],
        "group_metadata_coverage": {
            f: {"n_assigned": sum(len(ps) for k, ps in groups.items() if k[1] == f),
                "n_total": len(all_points)} for f in GROUP_FIELDS},
        "pooled_classification": _classification(all_points),
        "macro_over_symbols": macro,
        "mean_independent_account_return_pct": means,
        "mean_stored_rounded_account_return_pct": {
            v: float(np.mean(values)) if all(x is not None for x in values) else None
            for v, values in reported_returns.items()},
        "per_symbol": per_symbol,
        "groups": [{"symbol": s, "dimension": f, "value": g, "classification": _classification(ps)}
                   for (s, f, g), ps in sorted(groups.items())],
        "legacy_discrepancies": notes,
        "pending": ["train_fitted_majority", "true_buy_and_hold_daily_ledger", "fixed_momentum",
                    "logistic_price_only", "logistic_matched_information", "factor_only_non_llm",
                    "train_fitted_exposure_control", "daily_exposure_turnover_drawdown",
                    "fold_regime_repeat_evaluation", "manuscript_and_response_after_new_evidence"],
    }
