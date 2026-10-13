"""Báo cáo ghép cặp từ checkpoint đã kiểm; không chọn ứng viên hoặc gọi LLM."""

from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

from core.backtest_engine import PRIOR_BRANCH_MODES
from core.bayesian_memory import REGIMES
from core.prior_backtest import canonical_hash
from core.prior_config import copy_prior_json

VERSION = "research_report_v4"


def comparison_pairs(names: list[str]) -> list[tuple[str, str]]:
    """Giữ chiều A−B và thứ tự cặp đã đăng ký, không lặp cặp C1−C0."""
    pairs = [(name, "original") for name in [*PRIOR_BRANCH_MODES, *names] if name != "original"]
    pairs += [(name, "C0") for name in names if name != "C0"]
    pairs += [("C2", "C1"), ("C3", "C2"), ("C3", "C3_stats_only"), ("C3", "C3_examples_only")]
    return list(dict.fromkeys(pairs))


def branch_status(branch: dict[str, Any]) -> str:
    """Trạng thái hiện tại; attempt lỗi cũ không làm tăng count của point."""
    status = branch["status"]
    if status in ("running", "unknown"):
        return "unknown"
    if status in ("planned", "pending"):
        return "pending"
    if status not in ("complete", "failed"):
        raise ValueError("Trạng thái nhánh ngoài hợp đồng report")
    return status


def _ratio(numerator: int, denominator: int) -> dict[str, Any]:
    """Luôn công bố mẫu số; không coi nhóm không planned là tỷ lệ bằng 0."""
    return {"numerator": numerator, "denominator": denominator,
            "value": float(numerator / denominator) if denominator else None,
            "reason": None if denominator else "NO_PLANNED"}


def _coverage(rows: list[dict[str, Any]], name: str) -> dict[str, Any]:
    """Coverage planned/complete và readiness khác visibility của Decision."""
    status = Counter(branch_status(p["branches"][name]) for p in rows)
    views = [p["report_context"]["prior"][name] for p in rows]
    complete = [p for p in rows if branch_status(p["branches"][name]) == "complete"]
    visible = sum(bool(p["report_context"]["prior"][name]["visible_metric_ids"] or
                       p["report_context"]["prior"][name]["visible_example_ids"]) for p in complete)
    features = Counter(p["report_context"]["feature_status"] for p in rows)
    return {"planned": len(rows), **{k: int(status[k]) for k in ("complete", "pending", "failed", "unknown")},
        "missing_result": len(rows)-status["complete"], "fallback_count": sum(
            p["report_context"]["prior"][name]["fallback"] is True for p in complete),
        "completion_coverage": _ratio(status["complete"], len(rows)),
        "feature_available": int(features["AVAILABLE"]), "feature_unavailable": int(features["UNAVAILABLE"]),
        "feature_unknown": int(features["UNKNOWN"]),
        "feature_reason_counts": dict(sorted(Counter(reason for p in rows for reason in
            p["report_context"]["feature_reasons"]).items())),
        "stats_ready": sum(v["stats_ready"] is True for v in views),
        "examples_ready": sum(v["examples_ready"] is True for v in views),
        "readiness_unknown": sum(v["stats_ready"] is None or v["examples_ready"] is None for v in views),
        "prior_visible_count": int(visible), "prior_off_count": len(complete)-visible,
        "visibility_coverage": _ratio(visible, len(rows)),
        "visibility_on_complete": {**_ratio(visible, len(complete)),
            "reason": None if complete else "NO_COMPLETE"},
        "reason_counts": dict(sorted(Counter(reason for v in views for reason in v["reason_codes"]).items())),
        "error_counts": dict(sorted(Counter(p["branches"][name].get("error", {}).get("code", "UNKNOWN_DECISION")
            if p["branches"][name].get("error") else "UNKNOWN_DECISION" for p in rows
            if branch_status(p["branches"][name]) in ("failed", "unknown")).items()))}


def _metric(rows: list[dict[str, Any]], name: str) -> dict[str, Any]:
    """Chiếu một nhánh lên API engine cũ, không yêu cầu nhánh khác complete."""
    from core.research_metrics import action_attribution, branch_metrics
    action_attribution(rows, [name])
    projected = deepcopy(rows)
    for row in projected:
        row["status"] = "complete"
        row["branches"] = {key: deepcopy(row["branches"][name]) for key in PRIOR_BRANCH_MODES}
        row["evaluation"]["branches"] = {key: deepcopy(row["evaluation"]["branches"][name]) for key in PRIOR_BRANCH_MODES}
    metric = branch_metrics(projected, "original")
    n = len(rows)
    confusion = {"UP_LONG": 0, "UP_CASH": 0, "DOWN_LONG": 0, "DOWN_CASH": 0}
    for row in rows:
        action = "LONG" if row["branches"][name]["decision"]["action"] == "LONG" else "CASH"
        confusion[f"{row['evaluation']['actual_direction']}_{action}"] += 1
    long_count = confusion["UP_LONG"] + confusion["DOWN_LONG"]
    metric.update(confusion_counts=confusion, long_count=long_count, cash_count=n-long_count,
        support_reason=None if n else "NO_SUPPORT")
    if not n:
        metric.update(balanced_accuracy_reason="NO_SUPPORT", hit_rate_reason="NO_SUPPORT")
    return metric


def paired_candidate_report(plan: dict[str, Any], points: dict[str, list[dict[str, Any]]],
                            binding: dict[str, Any]) -> dict[str, Any]:
    """Tái dựng tài khoản trên G/S và nhóm regime; chỉ nhận snapshot đã verify."""
    from core.research_metrics import action_attribution
    plan, points, binding = (copy_prior_json(value) for value in (plan, points, binding))
    names = plan["candidate_registry"]["order"]
    matrix = [*PRIOR_BRANCH_MODES, *names]
    if plan["split"] not in ("fixture", "development_2023"):
        raise ValueError("Report ứng viên chưa mở holdout; cần protocol có selection binding")
    if (set(binding) != {"run_signature", "execution_mode", "plan_sha256", "registry_sha256", "code_sha256",
                        "runtime", "sources", "price_index", "model", "checkpoint_sha256"}
            or binding["execution_mode"] not in ("research", "offline_fixture")
            or binding["code_sha256"] != plan["code_sha256"] or binding["runtime"] != plan["runtime"]
            or binding["price_index"] != plan["price_index"] or binding["model"] != plan["inputs"].get("model")
            or names != ["C0", "C1", "C2", "C3", "C3_stats_only", "C3_examples_only"]
            or plan["candidate_registry"]["risk_policy"] != "OFF"
            or binding["plan_sha256"] != canonical_hash(plan)
            or binding["registry_sha256"] != canonical_hash(plan["candidate_registry"])):
        raise ValueError("Report khác registry, plan hoặc risk OFF")
    if set(points) != set(plan["symbol_cutoffs"]):
        raise ValueError("Report thiếu/thừa mã trong plan")
    pairs, stocks, all_complete = comparison_pairs(names), {}, True
    for symbol, cutoffs in plan["symbol_cutoffs"].items():
        supplied = points[symbol]
        days = [p["context"]["as_of_date"] for p in supplied]
        if len(set(days)) != len(days) or set(days) != set(cutoffs):
            raise ValueError("Report thiếu point, trùng hoặc ngoài plan")
        rows = sorted(supplied, key=lambda p:p["context"]["as_of_date"])
        for p in rows:
            if (p["context"]["symbol"] != symbol or p["point_id"] != f"{symbol}-{p['context']['as_of_date']}"
                    or set(p["branches"]) != set(matrix) or set(p["report_context"]["prior"]) != set(matrix)
                    or p["report_context"]["regime"] not in REGIMES
                    or p["report_context"]["feature_status"] not in ("AVAILABLE", "UNAVAILABLE", "UNKNOWN")):
                raise ValueError("Projection point/nhánh/regime không hợp lệ")
            complete_names = [name for name in matrix if branch_status(p["branches"][name]) == "complete"]
            if complete_names:
                action_attribution([p], complete_names)
        cache: dict[tuple[str, tuple[str, ...]], dict[str, Any]] = {}
        def metrics(subset: list[dict[str, Any]], name: str) -> dict[str, Any]:
            key = (name, tuple(p["point_id"] for p in subset))
            if key not in cache:
                cache[key] = _metric(subset, name)
            return deepcopy(cache[key])
        def support(subset: list[dict[str, Any]], required: list[str]) -> dict[str, Any]:
            selected = [p for p in subset if all(branch_status(p["branches"][name]) == "complete" for name in required)]
            selected_ids = {p["point_id"] for p in selected}
            excluded = [{"point_id": p["point_id"], "reasons": {name: branch_status(p["branches"][name])
                for name in required if branch_status(p["branches"][name]) != "complete"}}
                for p in subset if p["point_id"] not in selected_ids]
            return {"point_ids": [p["point_id"] for p in selected],
                "dates": [p["context"]["as_of_date"] for p in selected], "count": len(selected), "excluded": excluded}
        def group(subset: list[dict[str, Any]]) -> dict[str, Any]:
            common = support(subset, matrix)
            selected = [p for p in subset if p["point_id"] in set(common["point_ids"])]
            result = {"global_common_support": common, "coverage": {name:_coverage(subset, name) for name in matrix},
                "metrics": {name:metrics(selected, name) for name in matrix}, "pairwise_support": {}}
            cash = deepcopy(selected)
            for p in cash:
                p["branches"]["original"]["decision"]["action"] = "SHORT"
                p["evaluation"]["branches"]["original"] = {"correct": p["evaluation"]["actual_direction"] == "DOWN",
                    "executed_action": "CASH", "cycle_net_return": 0.}
            result["cash_reference"] = _metric(cash, "original")
            for a, b in pairs:
                paired = support(subset, [a, b])
                observed = [p for p in subset if p["point_id"] in set(paired["point_ids"])]
                am, bm = metrics(observed, a), metrics(observed, b)
                delta_r = None if not observed else float(am["account_metrics"]["total_return_pct"]-bm["account_metrics"]["total_return_pct"])
                delta_m = None if not observed else float(am["account_metrics"]["max_drawdown_pct"]-bm["account_metrics"]["max_drawdown_pct"])
                result["pairwise_support"][f"{a}__{b}"] = {**paired, "a": a, "b": b,
                    "metrics_a": am, "metrics_b": bm, "delta_return_pp": delta_r, "delta_mdd_pp": delta_m,
                    "status": "COMPLETE" if len(observed) == len(subset) and observed else "PROVISIONAL" if observed else "NO_SUPPORT"}
            return result
        global_group = group(rows)
        common = global_group["global_common_support"]
        full = common["count"] == len(cutoffs)
        all_complete = all_complete and full
        deltas, mdd_deltas = {}, {}
        for name in names:
            a, b = (global_group["metrics"][key]["account_metrics"] for key in (name, "original"))
            deltas[name] = float(a["total_return_pct"]-b["total_return_pct"]) if full else None
            mdd_deltas[name] = float(a["max_drawdown_pct"]-b["max_drawdown_pct"]) if full else None
        selected = [p for p in rows if p["point_id"] in set(common["point_ids"])]
        stocks[symbol] = {**global_group, "completed": common["count"], "common_support": common["dates"],
            "pending": [day for day in cutoffs if day not in common["dates"]],
            "candidate_delta_return_pp": deltas, "candidate_delta_mdd_pp": mdd_deltas,
            "action_attribution": action_attribution(selected, matrix),
            "regimes": {regime:group([p for p in rows if p["report_context"]["regime"] == regime]) for regime in sorted(REGIMES)},
            "points": [{"point_id": p["point_id"], "as_of_date": p["context"]["as_of_date"],
                **p["report_context"], "branch_status": {name:branch_status(p["branches"][name]) for name in matrix}}
                for p in rows]}
    complete = all_complete and len(stocks) == 4
    if plan["split"] == "development_2023" and {s:len(d) for s,d in plan["symbol_cutoffs"].items()} != {"FPT":12,"VNM":16,"VCB":16,"MWG":16}:
        raise ValueError("Development phải giữ lịch 60 điểm đã khóa")
    return copy_prior_json({"report_version": VERSION, "metric_version": "cycle_risk_metrics_v2",
        "cohort_id": plan["cohort_id"], "split": plan["split"], "matrix": matrix, "binding": binding,
        "primary_status": "COMPLETE" if complete else "INCOMPLETE", "candidate_status": {
            name:"COMPLETE" if complete else "INCOMPLETE" for name in names},
        "candidate_delta_return_pp": {name:float(sum(s["candidate_delta_return_pp"][name] for s in stocks.values())/4) if complete else None for name in names},
        "candidate_delta_mdd_pp": {name:float(sum(s["candidate_delta_mdd_pp"][name] for s in stocks.values())/4) if complete else None for name in names},
        "selection_evidence_status": "DEVELOPMENT" if plan["split"] == "development_2023" and binding["execution_mode"] == "research" else "NOT_APPLICABLE",
        "stocks": stocks, "limitations": ["Bốn tài khoản độc lập, trung bình đều không phải portfolio.",
            "Pairwise/regime partial chỉ provisional; primary cần đủ toàn ma trận.",
            "Fixture/mock chỉ kiểm protocol; risk OFF, không annualize Sharpe/Sortino."]})


def verify_report(report: dict[str, Any], expected: dict[str, Any]) -> None:
    """So toàn semantic với bản dựng lại từ checkpoint đã verify, kể cả thứ tự list."""
    if report.get("report_version") not in ("research_report_v2", "research_report_v3", VERSION):
        raise ValueError("Version report nghiên cứu không được hỗ trợ")
    if canonical_hash(copy_prior_json(report)) != canonical_hash(copy_prior_json(expected)):
        raise ValueError("Report khác checkpoint/nguồn, support, metric hoặc thứ tự ngày tái dựng")


def read_report(path: Path, expected: dict[str, Any]) -> dict[str, Any]:
    """Loader legacy/v4 chỉ trả artifact sau khi đối chiếu semantic, không ghi lại."""
    from core.research_cohort import read_envelope
    report = read_envelope(path)
    verify_report(report, expected)
    return report
