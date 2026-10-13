"""Phân tích mô tả prior từ snapshot đã verify; không sửa action hoặc gọi LLM."""

from collections import Counter
from copy import deepcopy
from typing import Any, Callable

from core.bayesian_retriever import PREFIX_METRICS

VERSION = "prior_disagreement_analysis_v1"
C3_BRANCHES = ("C3", "C3_stats_only", "C3_examples_only")
ACTIVE_CONTRACT = "decision_prior_use_v1"


def _complete(point: dict[str, Any], name: str) -> bool:
    """Chỉ Decision đã complete mới góp action/exposure vào thống kê."""
    return point["branches"][name]["status"] == "complete"


def _view(point: dict[str, Any], name: str) -> dict[str, Any]:
    """Lấy projection evidence đã tái dựng từ nguồn và request thực."""
    return point["report_context"]["prior"][name]


def _visible(point: dict[str, Any], name: str) -> bool:
    """Retrieved riêng lẻ không là phơi nhiễm Decision."""
    view = _view(point, name)
    return bool(view["visible_metric_ids"] or view["visible_example_ids"])


def _action(point: dict[str, Any], name: str) -> str:
    """SHORT là giữ CASH theo hợp đồng kinh tế hiện hữu."""
    return "LONG" if point["branches"][name]["decision"]["action"] == "LONG" else "CASH"


def _ratio(numerator: int, denominator: int) -> dict[str, Any]:
    """Nhóm rỗng giữ null và mẫu số bằng 0."""
    return {"numerator": numerator, "denominator": denominator,
            "value": float(numerator/denominator) if denominator else None,
            "reason": None if denominator else "NO_SUPPORT"}


def _support(rows: list[dict[str, Any]], selected: list[dict[str, Any]],
             reasons: Callable[[dict[str, Any]], list[str]]) -> dict[str, Any]:
    """Giữ point ID, ngày và lý do của mọi điểm ngoài support."""
    ids = {p["point_id"] for p in selected}
    return {"point_ids": [p["point_id"] for p in selected],
            "dates": [p["context"]["as_of_date"] for p in selected], "count": len(selected),
            "status": "COMPLETE" if selected and len(selected) == len(rows) else
                      "PROVISIONAL" if selected else "NO_SUPPORT",
            "excluded": [{"point_id": p["point_id"], "reasons": reasons(p)} for p in rows if p["point_id"] not in ids]}


def _actions(rows: list[dict[str, Any]], a: str, b: str) -> dict[str, Any]:
    """Bảng 2×2 giữ chiều A/B; hai ô chéo cộng đúng disagreement."""
    counts = Counter(f"{_action(p,a)}_{_action(p,b)}" for p in rows)
    return {"action_counts": {key: int(counts[key]) for key in
            ("LONG_LONG", "LONG_CASH", "CASH_LONG", "CASH_CASH")},
            "disagreement": _ratio(counts["LONG_CASH"]+counts["CASH_LONG"], len(rows))}


def _trace(view: dict[str, Any]) -> dict[str, Any]:
    """Kiểm self-report bắt buộc; hợp lệ chỉ chứng minh đúng schema/IDs."""
    from agents.decision_agent import PriorUseOutput
    active = view["decision_contract_version"] == ACTIVE_CONTRACT
    use = view["prior_use"]
    if not active:
        if use is not None:
            raise ValueError("Trace prior-use xuất hiện ngoài contract active")
        return {"status": "NOT_APPLICABLE", "prior_use": None}
    use = PriorUseOutput.model_validate(use, strict=True).model_dump()
    for field, allowed in (("metric_ids", view["visible_metric_ids"]),
                           ("example_ids", view["visible_example_ids"])):
        if len(use[field]) != len(set(use[field])) or not set(use[field]).issubset(allowed):
            raise ValueError("Trace prior-use tham chiếu ID trùng hoặc không visible")
    cited = bool(use["metric_ids"] or use["example_ids"])
    if not use["reason"].strip() or (use["assessment"] == "NOT_USED") == cited:
        raise ValueError("Trace prior-use thiếu lý do hoặc assessment sai IDs")
    return {"status": "VALID", "prior_use": use}


def _case(point: dict[str, Any], name: str) -> dict[str, Any]:
    """Giữ đầy đủ ca thuận/bất lợi; xét ngưỡng 0,5 trước làm tròn prefix."""
    view = _view(point, name)
    metrics = {}
    for key in PREFIX_METRICS:
        item = view["metric_details"].get(key)
        observed = (key in view["visible_metric_ids"] and item is not None
                    and item["ready"] is True and item["posterior_mean"] is not None)
        adverse = None
        if observed:
            mean = item["posterior_mean"]
            adverse = bool(mean < .5 if key == "win_rate_long" else mean > .5)
        metrics[key] = {"status": "OBSERVED" if observed else "NOT_APPLICABLE",
            "reason": None if observed else "HIDDEN_OR_NOT_READY_OR_NO_POSTERIOR",
            "posterior_mean": item["posterior_mean"] if observed else None,
            "support_count": (item.get("support_count", item.get("raw_counts", {}).get("conditional", {}).get("support_count"))
                              if observed else None),
            "credible_interval": deepcopy(item["credible_interval"]) if observed else None,
            "adverse": adverse}
    evaluation = point["evaluation"]
    branch = evaluation["branches"][name]
    return {"point_id": point["point_id"], "symbol": point["context"]["symbol"],
        "as_of_date": point["context"]["as_of_date"], "regime": point["report_context"]["regime"],
        "raw_action": point["branches"][name]["decision"]["action"], "execution_action": _action(point,name),
        "economic_outcome": {key:evaluation[key] for key in
            ("actual_direction", "net_return_long", "entry_date", "exit_date")},
        "cycle_net_return": branch["cycle_net_return"], "correct": branch["correct"],
        "prior_visible": _visible(point,name), "retrieved_ids": view["retrieved_ids"],
        "visible_example_ids": view["visible_example_ids"], "visible_metric_ids": view["visible_metric_ids"],
        "base_evidence_sha256": view["base_evidence_sha256"], "request_sha256": view["request_sha256"],
        "prefix_sha256": view["prefix_sha256"], "metrics": metrics,
        "adverse": any(m["adverse"] is True for m in metrics.values()), "trace": _trace(view)}


def prior_analysis(rows: list[dict[str, Any]], matrix: list[str], pairs: list[tuple[str, str]], *,
                   metrics: Callable[[list[dict[str, Any]], str], dict[str, Any]] | None = None) -> dict[str, Any]:
    """Tổng hợp cohort/mã/regime; chỉ callback theo mã mới dựng tài khoản subgroup."""
    branches, comparisons = {}, {}
    for name in matrix:
        selected = [p for p in rows if _complete(p,name)]
        cases = [_case(p,name) for p in selected]
        off = [p for p in selected if not _visible(p,name)]
        flagged = [case for case in cases if case["adverse"]]
        required = sum(case["trace"]["status"] == "VALID" for case in cases)
        observed = sum(any(m["status"] == "OBSERVED" for m in case["metrics"].values()) for case in cases)
        branches[name] = {**_support(rows, selected, lambda p:[p["branches"][name]["status"]]),
            "long_count": sum(_action(p,name) == "LONG" for p in selected),
            "cash_count": sum(_action(p,name) == "CASH" for p in selected),
            "prior_off": {**_support(rows, off, lambda p:["NOT_COMPLETE" if not _complete(p,name) else "PRIOR_VISIBLE"]),
                "long_count": sum(_action(p,name) == "LONG" for p in off),
                "cash_count": sum(_action(p,name) == "CASH" for p in off)},
            "adverse_point_ids": [case["point_id"] for case in flagged],
            "adverse_on_observed": _ratio(len(flagged), observed),
            "long_on_adverse": _ratio(sum(case["execution_action"] == "LONG" for case in flagged), len(flagged)),
            "trace_required_count": required, "trace_not_applicable_count": len(cases)-required,
            "trace_validity": _ratio(required, required),
            "assessment_counts": dict(sorted(Counter(case["trace"]["prior_use"]["assessment"] for case in cases
                if case["trace"]["status"] == "VALID").items())), "cases": cases}
    for a,b in pairs:
        selected = [p for p in rows if _complete(p,a) and _complete(p,b)]
        off_names = [a] if b == "original" else [a,b]
        off = [p for p in selected if all(not _visible(p,name) for name in off_names)]
        entry = {**_support(rows, selected, lambda p:[f"{name}:{p['branches'][name]['status']}"
            for name in (a,b) if not _complete(p,name)]), "a": a, "b": b, **_actions(selected,a,b),
            "prior_off": {**_support(rows, off, lambda p:["NOT_PAIRED_COMPLETE" if p not in selected else "PRIOR_VISIBLE"]),
                "required_off_branches": off_names, **_actions(off,a,b)}}
        if metrics is not None:
            am, bm = metrics(off,a), metrics(off,b)
            entry["prior_off"].update(metrics_a=am, metrics_b=bm,
                delta_return_pp=float(am["account_metrics"]["total_return_pct"]-bm["account_metrics"]["total_return_pct"]) if off else None,
                delta_mdd_pp=float(am["account_metrics"]["max_drawdown_pct"]-bm["account_metrics"]["max_drawdown_pct"]) if off else None)
        comparisons[f"{a}__{b}"] = entry
    common = [p for p in rows if all(_complete(p,name) for name in matrix)]
    ready = []
    for p in common:
        views = [_view(p,name) for name in C3_BRANCHES]
        hashes = [v["base_evidence_sha256"] for v in views]
        if not hashes[0] or len(set(hashes)) != 1:
            raise ValueError("Ba C3 khác base evidence hoặc thiếu hash đã verify")
        if any((v["stats_ready"], v["examples_ready"]) !=
               (views[0]["stats_ready"], views[0]["examples_ready"]) for v in views):
            raise ValueError("Ba C3 khác readiness của base evidence")
        if views[0]["stats_ready"] is True and views[0]["examples_ready"] is True:
            if any(v["decision_contract_version"] != ACTIVE_CONTRACT for v in views):
                raise ValueError("Tập stats+examples ready thiếu contract active ở ba C3")
            ready.append(p)
    ablation = {}
    for label, subset in (("global", common), ("stats_examples_ready", ready)):
        entry = {**_support(rows, subset, lambda p:["NOT_GLOBAL_COMPLETE" if p not in common else "NOT_BOTH_READY"]),
            "branches": {name:{"long_count": sum(_action(p,name) == "LONG" for p in subset),
                "cash_count": sum(_action(p,name) == "CASH" for p in subset)} for name in C3_BRANCHES},
            "pairs": {f"{a}__{b}":_actions(subset,a,b) for a,b in
                (("C3","C3_stats_only"), ("C3","C3_examples_only"), ("C3_stats_only","C3_examples_only"))}}
        if metrics is not None:
            entry["metrics"] = {name:metrics(subset,name) for name in C3_BRANCHES}
            for key, comparison in entry["pairs"].items():
                a,b = key.split("__")
                am, bm = (entry["metrics"][name]["account_metrics"] for name in (a,b))
                comparison.update(delta_return_pp=float(am["total_return_pct"]-bm["total_return_pct"]) if subset else None,
                    delta_mdd_pp=float(am["max_drawdown_pct"]-bm["max_drawdown_pct"]) if subset else None)
        ablation[label] = entry
    return {"analysis_version": VERSION, "branches": branches, "pairs": comparisons, "ablation": ablation,
        "account_scope": "PER_SYMBOL" if metrics is not None else "COUNTS_ONLY_NO_POOLED_ACCOUNT",
        "limitations": ["Trace tự báo cáo chỉ kiểm schema/IDs, không chứng minh nhân quả hoặc model dùng prior.",
            "Ngưỡng bất lợi mô tả 0,5 không thêm quality gate hoặc ép action; SHORT=CASH, risk OFF.",
            "Subgroup không thay primary; tài khoản dựng riêng trên support từng mã."]}
