"""Report U-BICL từ snapshot đã kiểm: tài khoản engine, support và repeat tách riêng."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

from core.historical_signals import digest
from core.paired_candidate_report import _metric
from core.research_cohort import read_envelope, save_envelope
from core.research_metrics import http_telemetry
from core.unified_bayes_contracts import MATRIX, SYMBOLS, REPORT_VERSION, validate
from core.unified_bayes_decision import LLM_BRANCHES

PAIRS = (("U_full", "Original"), ("U_full", "A_reference"), ("U_full", "U_stats"),
         ("U_full", "U_examples"), ("U_full", "Numeric_only"))


def support(rows: list[dict[str, Any]], names: tuple[str, ...]) -> dict[str, Any]:
    """Không loại mất mẫu âm thầm; complete chưa có evaluation cũng giữ reason riêng."""
    selected, excluded = [], []
    for row in rows:
        reasons = {name: row["branches"][name]["status"] for name in names if row["branches"][name]["status"] != "complete"}
        if row["evaluation"] is None:
            reasons["evaluation"] = "PENDING_ALL_LLM"
        if reasons:
            excluded.append({"point_id": row["point_id"], "repeat_id": row["repeat_id"], "reasons": reasons})
        else:
            selected.append(row["point_id"])
    return {"planned": len(rows), "count": len(selected), "point_ids": selected, "excluded": excluded}


def delta(rows: list[dict[str, Any]], a: str, b: str) -> dict[str, Any]:
    """Hai tài khoản được dựng lại trên đúng cùng support và thứ tự ngày."""
    common = support(rows, (a, b))
    subset = [row for row in rows if row["point_id"] in set(common["point_ids"])]
    am, bm = _metric(subset, a), _metric(subset, b)
    aa, ba = am["account_metrics"], bm["account_metrics"]
    return {**common, "a": a, "b": b, "metrics_a": am, "metrics_b": bm,
        "delta_return_pp": float(aa["total_return_pct"]-ba["total_return_pct"]) if subset else None,
        "delta_mdd_pp": float(aa["max_drawdown_pct"]-ba["max_drawdown_pct"]) if subset else None,
        "disagreements": sum(row["branches"][a]["decision"]["action"] != row["branches"][b]["decision"]["action"] for row in subset)}


def group(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Coverage và cặp đối chứng luôn giữ cả prior-off và các điểm chưa có kết quả."""
    common = support(rows, MATRIX)
    subset = [row for row in rows if row["point_id"] in set(common["point_ids"])]
    return {"global_common_support": common, "metrics": {name: _metric(subset, name) for name in MATRIX},
        "coverage": {name: {"planned": len(rows), **{status: sum(row["branches"][name]["status"] == status for row in rows)
            for status in ("planned", "unknown", "complete")},
            "shared_original": sum(row["branches"][name]["decision_origin"] == "shared_original" for row in rows),
            "visible": sum(row["branches"][name]["prior_visible"] for row in rows)} for name in MATRIX},
        "pairs": {a + "__" + b: delta(rows, a, b) for a, b in PAIRS}}


def build_report(plan: dict[str, Any], rows: list[dict[str, Any]], binding: dict[str, Any], ledger: dict[str, Any]) -> dict[str, Any]:
    """Primary dùng rid=0; repeat/duplicate không bổ sung mẫu hoặc thay primary."""
    expected = [(slot["point_id"], slot["repeat_id"]) for slot in plan["schedule"]]
    if ([(row["point_id"], row["repeat_id"]) for row in rows] != expected or binding["plan_sha256"] != digest(plan)
            or any(set(row["branches"]) != set(MATRIX) | ({"Original_duplicate"} if row["repeat_id"] else set()) for row in rows)):
        raise ValueError("Snapshot report khác lịch/nhánh/primary-repeat đã khóa")
    primary = [row for row in rows if row["repeat_id"] == 0]
    stocks = {}
    for symbol in SYMBOLS:
        selected = [row for row in primary if row["point_id"].startswith(symbol + "-")]
        stock = group(selected)
        stock["regimes"] = {regime: group([row for row in selected if row["regime"] == regime])
                            for regime in ("BULL", "BEAR", "CHOPPY", "CONSOLIDATION")}
        stock["time_groups"] = {q: group([row for row in selected if row["context"]["as_of_date"][5:7] in months])
            for q, months in (("Q1", ("01", "02", "03")), ("Q2", ("04", "05", "06")),
                              ("Q3", ("07", "08", "09")), ("Q4", ("10", "11", "12")),
                              ("H1", ("01", "02", "03", "04", "05", "06")),
                              ("H2", ("07", "08", "09", "10", "11", "12")))}
        stock["ablation_both_ready"] = {a + "__" + b: delta([row for row in selected if row["readiness"]["stats"] and row["readiness"]["examples"]], a, b)
                                        for a, b in PAIRS[2:4]}
        stock["prior_off"] = {name: delta([row for row in selected if not row["branches"][name]["prior_visible"]], name, "Original")
                              for name in LLM_BRANCHES[1:]}
        stocks[symbol] = stock
    complete = bool(primary) and all(row["evaluation"] is not None for row in primary)
    d = {key: float(sum(stocks[s]["pairs"][key]["delta_return_pp"] for s in SYMBOLS)/4)
         if complete and all(stocks[s]["pairs"][key]["count"] for s in SYMBOLS) else None for key in (a+"__"+b for a, b in PAIRS)}
    repeated = [row for row in rows if row["repeat_id"]]
    per_repeat = {str(r): {s: group([row for row in repeated if row["repeat_id"] == r and row["point_id"].startswith(s+"-")]) for s in SYMBOLS} for r in (1, 2, 3)}
    by_slot = {(row["point_id"], row["repeat_id"]): row for row in repeated}
    disagreement = {}
    for name in (*LLM_BRANCHES, "Original_duplicate"):
        values = [(by_slot[(pid, a)]["branches"][name], by_slot[(pid, b)]["branches"][name])
                  for pid in plan["repeat_sample"] for a, b in ((1, 2), (1, 3), (2, 3))]
        valid = [(a, b) for a, b in values if a["status"] == b["status"] == "complete"]
        disagreement[name] = {"planned_pairs": len(values), "observed_pairs": len(valid),
            "disagreements": sum(a["decision"]["action"] != b["decision"]["action"] for a, b in valid)}
    duplicates = {}
    for r in (1, 2, 3):
        selected = [row for row in repeated if row["repeat_id"] == r]
        valid = [row for row in selected if all(row["branches"][name]["status"] == "complete" for name in ("Original", "Original_duplicate"))]
        duplicates[str(r)] = {"planned": len(selected), "observed": len(valid),
            "disagreements": sum(row["branches"]["Original"]["decision"]["action"] != row["branches"]["Original_duplicate"]["decision"]["action"] for row in valid),
            "by_symbol": {s: delta([row for row in selected if row["point_id"].startswith(s+"-")], "Original_duplicate", "Original") for s in SYMBOLS}}
    return validate({"report_version": REPORT_VERSION, "metric_version": "cycle_risk_metrics_v2", "split": plan["split"],
        "binding": binding, "status": "COMPLETE" if complete and repeated and all(row["evaluation"] is not None for row in repeated) else "INCOMPLETE", "matrix": list(MATRIX),
        "primary": {"repeat_id": 0, "stocks": stocks, "equal_weight_delta_return_pp": d,
            "leave_one_symbol_out": {key: {s: float(sum(stocks[other]["pairs"][key]["delta_return_pp"] for other in SYMBOLS if other != s)/3)
                if value is not None else None for s in SYMBOLS} for key, value in d.items()},
            "status": "COMPLETE" if complete else "INCOMPLETE"},
        "repeats": {"in_primary": False, "repeat_ids": [1, 2, 3], "sample": plan["repeat_sample"],
            "status": "COMPLETE" if repeated and all(row["evaluation"] is not None and row["branches"]["Original_duplicate"]["status"] == "complete" for row in repeated) else "INCOMPLETE",
            "per_repeat": per_repeat, "disagreement": disagreement, "original_duplicate": duplicates},
        "telemetry": http_telemetry(ledger["requests"], [binding["run_signature"]], ledger.get("invocations", {})),
        "context_modes": dict(sorted(Counter(plan["requests"][row["point_id"]]["u_evidence"]["context_mode"] for row in primary).items())),
        "points": rows, "confirmation_allowed": False, "nomination_allowed": False,
        "limitations": ["Development exploratory; fixture chỉ kiểm kỹ thuật, không là bằng chứng hiệu quả.",
            "Repeat và duplicate không vào primary; cặp lặp phụ thuộc, không vote/chọn lượt tốt nhất.",
            "Trace ID chỉ telemetry; không báo bootstrap/nomination hoặc release từ report này.",
            "Điểm chưa đủ năm LLM chưa được đánh giá; support provisional giữ reason, không đổi lỗi thành CASH."]}, "report")


def read_report(path: Path, expected: dict[str, Any]) -> dict[str, Any]:
    """Consumer so toàn report với snapshot mới; không tin seal hay số liệu tự khai."""
    saved = validate(read_envelope(path), "report")
    if digest(saved) != digest(expected):
        raise ValueError("Report khác source/journal/usage/support/metric đã tái dựng")
    return saved


def write_report(path: Path, expected: dict[str, Any]) -> None:
    """Refresh report dẫn xuất bằng lệnh rõ ràng; không đè report của plan khác."""
    expected = validate(expected, "report")
    if path.exists():
        old = validate(read_envelope(path), "report")
        if old["binding"]["plan_sha256"] != expected["binding"]["plan_sha256"]:
            raise ValueError("Report đích thuộc plan khác")
    save_envelope(path, expected)
