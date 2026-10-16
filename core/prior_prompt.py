"""Prefix và request Decision ứng viên; chỉ render bằng chứng đã tái kiểm nguồn PIT."""

from __future__ import annotations

from typing import Any

from core.bayesian_retriever import BayesianPriorRetriever, PREFIX_METRICS, _prefix_task_line
from core.historical_signals import digest
from core.prior_config import copy_prior_json
from core.prior_example_selection import PriceExampleSelector
from core.prior_quality_gate import COUPLED_GATE, SPLIT_GATE, validate_quality_evidence

CANDIDATE_PROFILES = {
    "C1": (COUPLED_GATE, "full_prior", "compact_brpp_v2_compat", "decision_legacy_v1"),
    "C2": (SPLIT_GATE, "full_prior", "compact_brpp_v3", "decision_legacy_v1"),
    "C3": (SPLIT_GATE, "full_prior", "compact_brpp_v3", "decision_prior_use_v1"),
    "C3_stats_only": (SPLIT_GATE, "stats_only", "compact_brpp_v3", "decision_prior_use_v1"),
    "C3_examples_only": (SPLIT_GATE, "examples_only", "compact_brpp_v3", "decision_prior_use_v1"),
}
METRIC_LABELS = ("Win", "Trap", "TrendFail", "PatternFail")
_QUERY_FIELDS = ("symbol", "as_of_date", "current_regime", "current_signals")


def _prefix(evidence: dict[str, Any], candidate_id: str) -> str:
    """Template C1 bằng byte W5; v3 chỉ render block và metric ready, không cắt K."""
    _, mode, version, _ = CANDIDATE_PROFILES[candidate_id]
    view = evidence["content_views"][mode]
    if view["fallback_to_original"]:
        return ""
    stats = evidence["statistics"]
    if version == "compact_brpp_v2_compat":
        # Giữ đúng template W5, không mượn validator v2 cho retrieval v3.
        metrics = []
        for label, key in zip(METRIC_LABELS, PREFIX_METRICS):
            item = stats["metrics"][key]
            interval = item["credible_interval"]
            value = "N/A" if interval is None else f"{item['posterior_mean']:.2f}[{interval['lower']:.2f},{interval['upper']:.2f}]"
            metrics.append(f"{label}={item['success_count']}/{item['support_count']}→{value}")
        prefix = (f"[BRPP v2] R={evidence['current_regime']}; n={stats['population_count']}; k={view['visible_k']}\n"
                  + "; ".join(metrics) + "\nLịch sử: mean[CrI95%], không là dự báo query; SHORT=CASH.\n"
                  + "\n".join(_prefix_task_line(task, allow_sentiment=True) for task in evidence["tasks"]))
    else:
        lines = [f"[BRPP v3] R={evidence['current_regime']}; k={view['visible_k']}"]
        if view["visible_metric_ids"]:
            lines[0] += f"; n_P={stats['population_count']}; n_C={stats['conditional_count']}"
            metrics = []
            for label, key in zip(METRIC_LABELS, PREFIX_METRICS):
                item = stats["metrics"][key]
                if key not in view["visible_metric_ids"]:
                    metrics.append(f"{key}=N/A")
                    continue
                counts = item["raw_counts"]["conditional"]
                interval = item["credible_interval"]
                metrics.append(f"{key}={counts['success_count']}/{counts['support_count']}→"
                               f"{item['posterior_mean']:.2f}[{interval['lower']:.2f},{interval['upper']:.2f}]")
            lines += ["; ".join(metrics), "C=khớp T/P/A/I; mean[CrI95%] plug-in là tỷ lệ lịch sử, không dự báo query."]
        if view["visible_example_ids"]:
            lines.append("T/P/A/I:+ tăng,- giảm,0 trung tính; W/L=LONG ròng lịch sử; SHORT=CASH.")
            by_id = {row["episode_id"]: row for row in evidence["tasks"]}
            for key in view["visible_example_ids"]:
                task = by_id[key]
                line = _prefix_task_line(task, allow_sentiment=True)
                lines.append(line.replace(f"{task['symbol']}@{task['as_of_date']}", key, 1))
        prefix = "\n".join(lines)
    if len(prefix) > 600:
        raise ValueError("BRPP ứng viên vượt 600 ký tự; không cắt bằng chứng hoặc đổi K")
    return prefix


def build_prior_request(evidence: dict[str, Any], candidate_id: str, retriever: BayesianPriorRetriever, *,
                        selector: PriceExampleSelector | None = None,
                        query_features: dict[str, Any] | None = None) -> dict[str, Any]:
    """Tái kiểm evidence, tách binding nội dung khỏi base hash chung của ba C3."""
    if type(candidate_id) is not str or candidate_id not in CANDIDATE_PROFILES:
        raise ValueError("Ứng viên prompt không được đăng ký; C0 dùng đường evidence W5 hiện hữu")
    validate_quality_evidence(evidence, retriever, selector=selector, query_features=query_features)
    evidence = copy_prior_json(evidence)
    gate_version, mode, prefix_version, decision_version = CANDIDATE_PROFILES[candidate_id]
    if evidence["gate_version"] != gate_version:
        raise ValueError("Gate evidence khác hồ sơ ứng viên")
    view = evidence["content_views"][mode]
    metadata = evidence["selection"]["metadata"] if evidence["selection"] is not None else {}
    prefix = _prefix(evidence, candidate_id)
    request = {"request_version": "prior_decision_request_v1", "candidate_id": candidate_id,
        "evidence_contract_version": "prior_evidence_v3", "prefix_version": prefix_version,
        "decision_contract_version": "decision_legacy_v1" if not prefix else decision_version,
        "content_mode": mode, "query": {key: evidence[key] for key in _QUERY_FIELDS},
        "base_evidence_sha256": evidence["base_evidence_sha256"], "prefix": prefix,
        "source": {"bank_sha256": evidence["bank_sha256"], **{key: metadata.get(key) for key in
            ("index_sha256", "scaler_sha256", "fold_id", "calendar_prefix_sha256")}},
        "trace": view}
    request["request_sha256"] = digest(request)
    return copy_prior_json(request)


def validate_prior_request(request: dict[str, Any], evidence: dict[str, Any], retriever: BayesianPriorRetriever, *,
                           selector: PriceExampleSelector | None = None,
                           query_features: dict[str, Any] | None = None) -> None:
    """Rebuild từ nguồn khi đọc artifact; hash tự khai không thay semantic verification."""
    request = copy_prior_json(request)
    if type(request) is not dict or type(request.get("candidate_id")) is not str:
        raise ValueError("Request prior thiếu hồ sơ ứng viên")
    expected = build_prior_request(evidence, request["candidate_id"], retriever,
                                   selector=selector, query_features=query_features)
    if digest(request) != digest(expected):
        raise ValueError("Request/prefix/visibility khác evidence và nguồn PIT đã tái dựng")


def check_request_binding(request: dict[str, Any], state: dict[str, Any], prefix: str) -> None:
    """Biên nội bộ Decision sau hook kiểm nguồn: request phải khớp Full và prefix.

    Caller tạo request bằng builder và kiểm nguồn tại hook prior trước mỗi
    invocation; khi đọc artifact phải dùng validate_prior_request ở trên.
    """
    if type(request) is dict and request.get("request_version") == "improvement_prior_request_v1":
        from core.improvement_prior import check_binding
        check_binding(request, state, prefix)
        return
    from core.bayesian_retriever import normalize_signals
    request = copy_prior_json(request)
    keys = {"request_version", "candidate_id", "evidence_contract_version", "prefix_version",
            "decision_contract_version", "content_mode", "query", "base_evidence_sha256",
            "prefix", "source", "trace", "request_sha256"}
    if (type(request) is not dict or set(request) != keys or type(request["candidate_id"]) is not str
            or request["candidate_id"] not in CANDIDATE_PROFILES):
        raise ValueError("Schema request prior không hợp lệ")
    _, mode, prefix_version, decision_version = CANDIDATE_PROFILES[request["candidate_id"]]
    if (request["request_sha256"] != digest({k:v for k,v in request.items() if k != "request_sha256"})
            or request["request_version"] != "prior_decision_request_v1"
            or request["evidence_contract_version"] != "prior_evidence_v3"
            or request["prefix_version"] != prefix_version or request["content_mode"] != mode
            or request["decision_contract_version"] != (decision_version if prefix else "decision_legacy_v1")
            or request["prefix"] != prefix or len(prefix) > 600):
        raise ValueError("Hash/version/prefix request prior không khớp")
    regime = state.get("market_regime")
    if type(regime) is not dict:
        raise ValueError("Request prior cần regime từ Full đã seal")
    query = {"symbol": state.get("stock_name"), "as_of_date": state.get("as_of_date"),
             "current_regime": regime.get("regime_name"),
             "current_signals": normalize_signals(state.get("current_signals"))}
    forbidden = {"outcome", "net_return_pct", "actual_direction", "entry_date", "exit_date",
                 "actual_pct_change", "entry_open", "exit_close", "net_return", "current_regime", "regime_name"}
    if (forbidden.intersection(state) or digest(query) != digest(request["query"])
            or state.get("is_backtest") is not True or state.get("time_frame") not in ("1d", "1 ngày")):
        raise ValueError("Request prior khác Full query hoặc chứa outcome/ngoài backtest daily")
    view = request["trace"]
    if (bool(prefix) == view["fallback_to_original"] or view["visible_k"] != len(view["visible_example_ids"])
            or any(key not in PREFIX_METRICS for key in view["visible_metric_ids"])
            or (mode == "stats_only" and view["visible_example_ids"])
            or (mode == "examples_only" and view["visible_metric_ids"])):
        raise ValueError("Visibility request khác chế độ nội dung")


def add_prior_use_contract(prompt: str, request: dict[str, Any], lang: str) -> str:
    """Thêm field self-report cho C3, giữ đủ nội dung Original và không ép action."""
    if request["decision_contract_version"] != "decision_prior_use_v1":
        return prompt
    instruction = ("So tín hiệu với support/CrI/ví dụ; được bác prior. "
                   "Chỉ IDs có số liệu; NOT_USED: IDs rỗng. Tự báo cáo."
                   if lang == "vi" else
                   "Compare signals, support/CrI and examples; may reject prior. "
                   "Data IDs only; NOT_USED: empty IDs. Self-report.")
    start = prompt.find(request["prefix"] + "\n")
    if start < 0:
        raise ValueError("Prompt thiếu prefix đã kiểm")
    start += len(request["prefix"]) + 1
    end = prompt.find("### [1]", start)
    if end < 0:
        raise ValueError("Prompt thiếu điểm nối báo cáo Original")
    # C3 thay chỉ dẫn prior W5 bằng contract mới; giữ nguyên toàn bộ report/cap.
    prompt = prompt[:start] + instruction + "\n" + prompt[end:]
    position = prompt.rfind("}")
    if position < 0 or '"justification"' not in prompt:
        raise ValueError("Prompt Original thiếu mẫu JSON Decision để mở contract prior")
    field = ',"prior_use":{"metric_ids":[],"example_ids":[],"assessment":"NOT_USED","reason":"lý do"}'
    return prompt[:position] + field + prompt[position:]
