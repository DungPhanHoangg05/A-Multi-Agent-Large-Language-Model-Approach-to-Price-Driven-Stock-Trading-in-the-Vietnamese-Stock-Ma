"""Gate bằng chứng PIT; stats và examples độc lập, không quyết định lệnh giao dịch."""

from __future__ import annotations

from typing import Any

from core.bayesian_retriever import BayesianPriorRetriever, PREFIX_METRICS, normalize_signals
from core.historical_signals import digest
from core.prior_config import copy_prior_json
from core.prior_evidence_v2 import posterior_metric
from core.prior_example_selection import PriceExampleSelector

SPLIT_GATE = "split_quality_gate_v2"
COUPLED_GATE = "population_coupled_gate_v1"
THRESHOLDS = {"min_population_count": 20, "min_conditional_count": 5, "max_interval_width": .75}


def _readiness(population_count: int, metrics: dict[str, Any], metadata: dict[str, Any],
               gate_version: str) -> dict[str, Any]:
    """So biên chính xác trên dữ liệu producer đã kiểm; không làm tròn hay xét mean."""
    population_reasons = ["LOW_POPULATION_SUPPORT"] if population_count < THRESHOLDS["min_population_count"] else []
    example_reasons = list(population_reasons)
    if metadata["query_feature_status"] != "AVAILABLE":
        example_reasons.append("QUERY_FEATURE_UNAVAILABLE")
    if metadata["scaler_status"] != "AVAILABLE":
        example_reasons.append("SCALER_UNAVAILABLE")
    if not metadata["selected_ids"]:
        example_reasons.append("NO_QUALIFIED_EXAMPLES")
    examples_ready = not example_reasons
    metric_gates = {}
    for key in PREFIX_METRICS:
        item = metrics[key]
        reasons = list(population_reasons)
        if gate_version == SPLIT_GATE:
            support = item["raw_counts"]["conditional"]["support_count"]
            interval = item["credible_interval"]
            width = None if interval is None else interval["width"]
            if support < THRESHOLDS["min_conditional_count"]:
                reasons.append("LOW_CONDITIONAL_SUPPORT")
            if interval is None:
                reasons.append("NO_CONDITIONAL_HISTORY")
            elif width > THRESHOLDS["max_interval_width"]:
                reasons.append("WIDE_CREDIBLE_INTERVAL")
        else:
            support = item["support_count"]
            interval = item["credible_interval"]
            width = None if interval is None else float(interval["upper"] - interval["lower"])
            if not examples_ready:
                reasons.append("COUPLED_EXAMPLES_NOT_READY")
            if not support:
                reasons.append("NO_HISTORY")
        metric_gates[key] = {"status": "INSUFFICIENT_EVIDENCE" if reasons else "READY",
                             "reason_codes": reasons, "support_count": support, "interval_width": width}
    ready_ids = [key for key in PREFIX_METRICS if metric_gates[key]["status"] == "READY"]
    stats_ready = bool(ready_ids)
    reasons = list(dict.fromkeys(population_reasons + ([] if stats_ready else ["NO_READY_METRICS"]) + example_reasons))
    return {"status": "READY" if stats_ready or examples_ready else "INSUFFICIENT_EVIDENCE",
            "reason_codes": reasons, "stats_ready": stats_ready, "examples_ready": examples_ready,
            "stats_status": "READY" if stats_ready else "INSUFFICIENT_EVIDENCE",
            "stats_reason_codes": [] if stats_ready else ["NO_READY_METRICS"],
            "examples_status": "READY" if examples_ready else "INSUFFICIENT_EVIDENCE",
            "examples_reason_codes": example_reasons, "metrics": metric_gates,
            "ready_metric_ids": ready_ids,
            "ready_example_ids": list(metadata["selected_ids"]) if examples_ready else []}


def _content_views(gate: dict[str, Any], retrieved_k: int) -> dict[str, Any]:
    """Trace ba cách hiển thị cùng base evidence; builder prompt sẽ dùng ở bước sau."""
    views = {}
    for mode in ("full_prior", "stats_only", "examples_only"):
        metrics = [] if mode == "examples_only" else list(gate["ready_metric_ids"])
        examples = [] if mode == "stats_only" else list(gate["ready_example_ids"])
        ready = bool(metrics or examples)
        views[mode] = {"retrieved_k": retrieved_k, "visible_k": len(examples),
                       "visible_metric_ids": metrics, "visible_example_ids": examples,
                       "fallback_to_original": not ready,
                       "status": "READY" if ready else gate["status"] if gate["status"] == "DISABLED" else "INSUFFICIENT_EVIDENCE",
                       "reason_codes": [] if ready else list(gate["reason_codes"]) + ["NO_VISIBLE_PRIOR_BLOCK"]}
    return views


def retrieve_quality_evidence(retriever: BayesianPriorRetriever, *, symbol: str, as_of_date: str,
                              current_regime: str, current_signals: dict[str, str],
                              selector: PriceExampleSelector | None = None,
                              query_features: dict[str, Any] | None = None, requested_k: int = 3,
                              enable_bayesian_prior: bool = True, gate_version: str = SPLIT_GATE) -> dict[str, Any]:
    """Ghép hai producer production; thiếu/sai artifact ném lỗi, thiếu support mới fallback.

    C1 giữ Beta(1,1) trên P và gate ghép cặp. C2/C3 dùng posterior điều kiện
    cùng gate tách block. K=0/tắt prior không chạy stats, index hay selection.
    """
    if type(enable_bayesian_prior) is not bool or gate_version not in (SPLIT_GATE, COUPLED_GATE):
        raise ValueError("Trạng thái prior hoặc version quality gate không hợp lệ")
    retriever._validate_query(symbol=symbol, as_of_date=as_of_date, current_regime=current_regime,
        current_signals=current_signals, mode="bayesian_regime", k=requested_k, seed=42, scope="same_symbol")
    query = {"symbol": symbol, "as_of_date": as_of_date, "current_regime": current_regime,
             "current_signals": normalize_signals(current_signals)}
    thresholds = THRESHOLDS if gate_version == SPLIT_GATE else {"min_population_count": THRESHOLDS["min_population_count"]}
    settings = {"enable_bayesian_prior": enable_bayesian_prior, "requested_k": requested_k,
                "gate_version": gate_version, **thresholds}
    statistics = selection = None
    if not enable_bayesian_prior or requested_k == 0:
        reasons = (["PRIOR_DISABLED"] if not enable_bayesian_prior else []) + (["K_ZERO"] if not requested_k else [])
        gate = {"status": "DISABLED", "reason_codes": reasons, "stats_ready": False, "examples_ready": False,
                "stats_status": "DISABLED", "examples_status": "DISABLED", "stats_reason_codes": reasons,
                "examples_reason_codes": reasons, "metrics": {}, "ready_metric_ids": [], "ready_example_ids": []}
    else:
        if not isinstance(selector, PriceExampleSelector) or type(query_features) is not dict:
            raise ValueError("Prior enabled cần selector và feature có proof; thiếu artifact không là thiếu evidence")
        statistics = retriever.conditional_statistics(**query)
        selection = retriever.select_price_examples(**query, selector=selector, query_features=query_features,
                                                    config={"requested_k": requested_k})
        population = sorted(selection["regime_population"], key=lambda row: row["episode_id"])
        if (digest(population) != statistics["population_sha256"]
                or selection["metadata"]["bank_sha256"] != statistics["bank_sha256"]):
            raise ValueError("Population/nguồn giữa stats và examples không khớp")
        if gate_version == COUPLED_GATE:
            metrics = {key: posterior_metric(key, item["raw_counts"]["population"]["success_count"],
                item["raw_counts"]["population"]["support_count"], 1., 1.) for key, item in statistics["metrics"].items()}
            statistics = {key: value for key, value in statistics.items() if key not in
                ("config", "config_sha256", "evidence_sha256", "groups", "conditional_count", "background_count", "interpretation")}
            statistics.update(statistics_version="regime_beta_binomial_v2", contract_stage="POPULATION_STATISTICS",
                              interpretation="historical_population_rates", metrics=metrics,
                              config={"prior_alpha": 1., "prior_beta": 1.})
            statistics["config_sha256"] = digest(statistics["config"])
            statistics["evidence_sha256"] = digest(statistics)
        gate = _readiness(statistics["population_count"], statistics["metrics"], selection["metadata"], gate_version)
    retrieved_k = len(selection["tasks"]) if selection is not None else 0
    evidence = {"evidence_contract_version": "prior_evidence_v3", "contract_stage": "QUALITY_GATE",
                **query, "bank_sha256": retriever._bank_sha256, "gate_version": gate_version,
                "config": settings, "config_sha256": digest(settings), "statistics": statistics,
                "selection": selection, "gate": gate, "retrieved_k": retrieved_k,
                "effective_k": len(gate["ready_example_ids"]),
                "tasks": selection["tasks"] if gate["examples_ready"] else [],
                "content_views": _content_views(gate, retrieved_k)}
    evidence["base_evidence_sha256"] = digest(evidence)
    return copy_prior_json(evidence)


def validate_quality_evidence(evidence: dict[str, Any], retriever: BayesianPriorRetriever, *,
                              selector: PriceExampleSelector | None = None,
                              query_features: dict[str, Any] | None = None) -> None:
    """Tái dựng từ nguồn PIT, chặn cả sửa counts/readiness/IDs rồi tự băm lại."""
    evidence = copy_prior_json(evidence)
    required = {"symbol", "as_of_date", "current_regime", "current_signals", "config"}
    if type(evidence) is not dict or not required.issubset(evidence) or type(evidence["config"]) is not dict:
        raise ValueError("Evidence quality gate thiếu query/config")
    config = evidence["config"]
    thresholds = THRESHOLDS if config.get("gate_version") == SPLIT_GATE else {"min_population_count": THRESHOLDS["min_population_count"]}
    if set(config) != {"enable_bayesian_prior", "requested_k", "gate_version", *thresholds}:
        raise ValueError("Config quality gate khác hợp đồng")
    expected = retrieve_quality_evidence(retriever, **{key: evidence[key] for key in required - {"config"}},
        **{key: config[key] for key in ("enable_bayesian_prior", "requested_k", "gate_version")},
        selector=selector, query_features=query_features)
    if digest(evidence) != digest(expected):
        raise ValueError("Evidence quality gate khác nguồn, ngưỡng, readiness hoặc trace đã tái tính")
