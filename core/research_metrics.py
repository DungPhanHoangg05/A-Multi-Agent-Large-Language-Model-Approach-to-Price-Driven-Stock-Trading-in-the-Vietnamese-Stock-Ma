"""Metric chu kỳ không annualize; bốn tài khoản độc lập, không giả portfolio."""

from copy import deepcopy
from typing import Any
import numpy as np

from core.backtest_engine import PRIOR_BRANCH_MODES, compute_round_trip_net_return
from core.prior_backtest import summarize_points
from core.prior_config import copy_prior_json


def http_telemetry(records: list[dict[str, Any]], signatures: list[str],
                   invocations: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """Ghép theo identity/UUID rõ ràng; missing khác zero, không cộng timer node lồng HTTP."""
    rows = [r for r in records if r.get("run_signature") in signatures]
    if len({r["id"] for r in rows}) != len(rows):
        raise ValueError("Telemetry trùng HTTP ID")
    def distribution(field: str, source: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        source = rows if source is None else source
        values = [r[field] for r in source if r.get(field) is not None]
        if any(type(v) not in (int, float) or not np.isfinite(v) or v < 0 for v in values):
            raise ValueError("Số đo telemetry không hợp lệ")
        return {"measured_count": len(values), "missing_count": len(source)-len(values),
                "sum": float(sum(values)) if values else None,
                "p95": float(np.quantile(values, .95, method="linear")) if values else None}
    invocation_rows = [r for r in (invocations or {}).values() if r.get("run_signature") in signatures]
    return {"telemetry_version": "research_http_telemetry_v2", "http_attempt_count": len(rows),
            "invocation_count": len({r["invocation_id"] for r in rows if r.get("invocation_id")}),
            "http_latency_seconds": distribution("latency_seconds"), "wait_seconds": distribution("pacing_seconds"),
            "invocation_elapsed_seconds": distribution("elapsed_seconds", invocation_rows),
            "invocation_wait_seconds": distribution("wait_seconds", invocation_rows),
            "prompt_tokens": distribution("prompt_tokens"), "completion_tokens": distribution("completion_tokens"),
            "total_tokens": distribution("total_tokens"),
            "requests": [{k: r.get(k) for k in ("id", "invocation_id", "checkpoint_attempt_id", "point_id", "branch_id", "role", "attempt_number", "status", "request_id")} for r in rows],
            "timing_note": "HTTP và pacing là hai phần riêng; không cộng thêm timer node/Decision bao ngoài."}


def cycle_risk(returns: list[float]) -> dict[str, Any]:
    """Sharpe ddof=1; downside dùng toàn N, CASH và mẫu ít trả null có lý do."""
    r = np.asarray(returns, dtype=float)
    if r.ndim != 1 or not np.isfinite(r).all():
        raise ValueError("Lợi nhuận chu kỳ phải hữu hạn")
    result = {"version": "cycle_risk_metrics_v2", "sample_count": int(r.size),
              "sharpe_cycle": None, "sortino_cycle": None, "sharpe_reason": None, "sortino_reason": None,
              "annualization_factor": None, "sharpe_annualized": None, "sortino_annualized": None}
    for metric, denominator in (("sharpe", float(np.std(r, ddof=1)) if r.size > 1 else 0.),
                                ("sortino", float(np.sqrt(np.mean(np.minimum(r, 0.) ** 2))) if r.size else 0.)):
        reason = "N_LT_2" if r.size < 2 else "ZERO_DENOMINATOR" if denominator <= 1e-12 else None
        result[f"{metric}_reason"] = reason
        result[f"{metric}_cycle"] = None if reason else float(r.mean() / denominator)
    return result


def branch_metrics(points: list[dict[str, Any]], name: str) -> dict[str, Any]:
    """Tái dùng engine tài khoản/lot/phí; chỉ thay metric rủi ro sai annualization v1."""
    projected = deepcopy(points)
    if name not in PRIOR_BRANCH_MODES:
        for point in projected:
            point["branches"] = {key: deepcopy(point["branches"][name]) for key in PRIOR_BRANCH_MODES}
            point["evaluation"]["branches"] = {key: deepcopy(point["evaluation"]["branches"][name]) for key in PRIOR_BRANCH_MODES}
        source = "original"
    else:
        source = name
        for point in projected:
            point["branches"] = {key: point["branches"][key] for key in PRIOR_BRANCH_MODES}
    summary = summarize_points(projected)[source]
    account = summary["account_metrics"]
    if account is not None:
        account = {k: v for k, v in account.items() if "sharpe" not in k and "sortino" not in k}
    n = len(points)
    actions = [p["branches"][name]["decision"]["action"] for p in points]
    correct = [p["evaluation"]["branches"][name]["correct"] for p in points]
    actual = [p["evaluation"]["actual_direction"] for p in points]
    longs = sum(a == "LONG" for a in actions)
    if account is not None and not longs:
        account["hit_rate_pct"] = None
        account["avg_trade_pct"] = None
    balanced = None if set(actual) != {"UP", "DOWN"} else float(np.mean([
        np.mean([ok for ok, label in zip(correct, actual) if label == target]) for target in ("UP", "DOWN")]))
    return {"sample_count": n, "accuracy": summary["accuracy"], "balanced_accuracy": balanced,
            "balanced_accuracy_reason": None if balanced is not None else "MISSING_CLASS",
            "participation": float(longs / n) if n else None, "cash_rate": float((n-longs)/n) if n else None,
            "hit_rate_long": float(sum(ok for ok, a in zip(correct, actions) if a == "LONG") / longs) if longs else None,
            "hit_rate_reason": None if longs else "NO_LONG", "account_metrics": account,
            "risk": cycle_risk(account["period_returns"] if account is not None else [])}


def research_report(plan: dict[str, Any], points: dict[str, list[dict[str, Any]]], *,
                    binding: dict[str, Any] | None = None) -> dict[str, Any]:
    """Chỉ lấy common support; chỉ primary khi đủ bốn mã của cohort đã khóa."""
    if plan["matrix"] == "research_candidates_v1":
        if binding is not None:
            from core.paired_candidate_report import paired_candidate_report
            return paired_candidate_report(plan, points, binding)
        return candidate_report(plan, points)
    matrix = list(PRIOR_BRANCH_MODES) + (["bayesian_v2"] if plan["matrix"] == "research_v2" else [])
    stocks, complete = {}, True
    for symbol, cutoffs in plan["symbol_cutoffs"].items():
        rows = points.get(symbol, [])
        done = {p["context"]["as_of_date"] for p in rows}
        if len(done) != len(rows) or not done <= set(cutoffs):
            raise ValueError("Report có điểm ngoài plan hoặc trùng điểm")
        pending = [c for c in cutoffs if c not in done]
        complete = complete and not pending
        metrics = {name: branch_metrics(rows, name) for name in matrix}
        cash = deepcopy(rows)
        for row in cash:
            for name in matrix:
                row["branches"][name]["decision"]["action"] = "SHORT"
                row["evaluation"]["branches"][name] = {"correct": row["evaluation"]["actual_direction"] == "DOWN",
                    "executed_action": "CASH", "cycle_net_return": 0.}
        cash_metrics = branch_metrics(cash, "original")
        delta = None
        if not pending and plan["matrix"] == "research_v2":
            delta = float(metrics["bayesian_v2"]["account_metrics"]["total_return_pct"] -
                          metrics["original"]["account_metrics"]["total_return_pct"])
        stocks[symbol] = {"completed": len(rows), "pending": pending, "metrics": metrics,
                          "cash_reference": cash_metrics, "delta_return_pp": delta}
    status = "NOT_APPLICABLE" if plan["matrix"] != "research_v2" else "COMPLETE" if complete and len(stocks) == 4 else "INCOMPLETE"
    return copy_prior_json({"report_version": "research_report_v2", "metric_version": "cycle_risk_metrics_v2",
        "cohort_id": plan["cohort_id"], "split": plan["split"], "matrix": matrix, "stocks": stocks,
        "primary_status": status, "primary_delta_return_pp": float(np.mean([s["delta_return_pp"] for s in stocks.values()])) if status == "COMPLETE" else None,
        "limitations": ["Bốn tài khoản 50 triệu độc lập; trung bình đều không phải portfolio.",
                         "MDD theo equity cuối chu kỳ; không annualize Sharpe/Sortino; chưa chứng minh hiệu quả v2."]})


def action_attribution(points: list[dict[str, Any]], matrix: list[str]) -> dict[str, Any]:
    """Đối soát policy OFF ở lớp báo cáo; không sửa Decision hoặc nhãn kinh tế."""
    rows = []
    for point in points:
        evaluation = point["evaluation"]
        net = evaluation["net_return_long"]
        expected = float(compute_round_trip_net_return(evaluation["entry_open"], evaluation["exit_close"]))
        if type(net) not in (float, int) or not np.isfinite(net) or net != expected:
            raise ValueError("Nhãn kinh tế khác hàm lợi nhuận T+2.5")
        label = "UP" if net > 0 else "DOWN"
        if evaluation["actual_direction"] != label:
            raise ValueError("Hướng kinh tế khác dấu lợi nhuận LONG sau phí")
        branches = {}
        for name in matrix:
            branch = point["branches"][name]
            raw = branch["decision"]["action"]
            result = evaluation["branches"][name]
            execution = "BUY_SELL" if raw == "LONG" else "CASH"
            cycle_return = result["cycle_net_return"]
            correct = (raw == "LONG") == (label == "UP")
            if (branch["status"] != "complete" or raw not in ("LONG", "SHORT")
                    or result["executed_action"] != execution
                    or type(cycle_return) not in (int, float) or not np.isfinite(cycle_return)
                    or cycle_return != (net if raw == "LONG" else 0.)
                    or type(result["correct"]) is not bool or result["correct"] != correct):
                raise ValueError("Policy OFF không được thay action hoặc kết quả kinh tế")
            branches[name] = {"raw_action": raw, "executed_action": raw,
                "execution_action": execution, "policy_reason": "RISK_POLICY_OFF",
                "cycle_net_return": float(cycle_return), "correct": correct}
        rows.append({"as_of_date": point["context"]["as_of_date"],
            "economic_label": {"actual_direction": label, "net_return_long": float(net),
                "entry_date": evaluation["entry_date"], "exit_date": evaluation["exit_date"]},
            "branches": branches})
    return {"attribution_version": "action_attribution_v1", "risk_policy": "OFF",
        "policy_status": "DEFERRED", "policy_hash": None, "override_count": 0, "points": rows}


def candidate_report(plan: dict[str, Any], points: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Tách sáu candidate ID, cùng support đủ 11 nhánh; pending không thành CASH."""
    if plan["candidate_registry"]["risk_policy"] != "OFF":
        raise ValueError("Chưa đăng ký ablation cho numeric risk policy")
    names = plan["candidate_registry"]["order"]
    matrix = [*PRIOR_BRANCH_MODES, *names]
    stocks = {}
    complete = True
    for symbol, cutoffs in plan["symbol_cutoffs"].items():
        supplied = points.get(symbol, [])
        dates = [p["context"]["as_of_date"] for p in supplied]
        if len(set(dates)) != len(dates) or not set(dates) <= set(cutoffs):
            raise ValueError("Report ứng viên có điểm trùng hoặc ngoài plan")
        rows = sorted([p for p in supplied if all(p["branches"].get(name, {}).get("status") == "complete"
            and name in p["evaluation"]["branches"] for name in matrix)], key=lambda p:p["context"]["as_of_date"])
        done = {p["context"]["as_of_date"] for p in rows}
        pending = [day for day in cutoffs if day not in done]
        complete = complete and not pending
        attribution = action_attribution(rows, matrix)
        metrics = {name: branch_metrics(rows, name) for name in matrix}
        cash = deepcopy(rows)
        for row in cash:
            row["branches"]["original"]["decision"]["action"] = "SHORT"
            row["evaluation"]["branches"]["original"] = {"correct": row["evaluation"]["actual_direction"] == "DOWN",
                "executed_action": "CASH", "cycle_net_return": 0.}
        deltas = {name: None if pending else float(metrics[name]["account_metrics"]["total_return_pct"] -
                  metrics["original"]["account_metrics"]["total_return_pct"]) for name in names}
        stocks[symbol] = {"completed": len(rows), "pending": pending, "common_support": sorted(done),
            "metrics": metrics, "cash_reference": branch_metrics(cash, "original"),
            "candidate_delta_return_pp": deltas, "action_attribution": attribution}
    status = "COMPLETE" if complete and len(stocks) == 4 else "INCOMPLETE"
    return copy_prior_json({"report_version": "research_report_v3", "metric_version": "cycle_risk_metrics_v2",
        "cohort_id": plan["cohort_id"], "split": plan["split"], "matrix": matrix, "stocks": stocks,
        "primary_status": status, "candidate_status": {name: status for name in names},
        "candidate_delta_return_pp": {name: float(np.mean([s["candidate_delta_return_pp"][name] for s in stocks.values()]))
            if status == "COMPLETE" else None for name in names},
        "limitations": ["Fixture/mock chỉ kiểm protocol, không là hiệu quả đầu tư LLM.",
            "Bốn tài khoản độc lập; trung bình đều theo candidate không phải portfolio.",
            "Common support đủ 11 nhánh; không annualize Sharpe/Sortino; risk policy tắt."]})
