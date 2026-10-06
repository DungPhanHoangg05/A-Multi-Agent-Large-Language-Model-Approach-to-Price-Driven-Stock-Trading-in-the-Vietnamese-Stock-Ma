"""Kiểm state prior tại Decision; caller chịu trách nhiệm xác minh nguồn thật."""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any, Callable

from core.prior_config import (
    PRIOR_STATE_FIELDS, copy_prior_json, normalize_prior_config,
    normalize_prior_query_context, normalize_prior_state, validate_prior_execution,
)

PriorSourceValidator = Callable[[dict[str, Any]], None]


def prepare_decision_prior(
    state: dict[str, Any], *, source_validator: PriorSourceValidator | None = None,
) -> tuple[dict[str, Any], str]:
    """Kiểm config/query/result, xác minh nguồn qua callback rồi gọi formatter W3."""
    if type(state) is not dict:
        raise ValueError("State Decision phải là dict Python gốc")
    config = normalize_prior_config(state.get("prior_config"))
    if not config["enable_bayesian_prior"]:
        return normalize_prior_state(state), ""
    config, ablation, timeframe = validate_prior_execution(
        config, is_backtest=state.get("is_backtest"), time_frame=state.get("time_frame"),
        ablation_config=state.get("ablation_config"),
    )
    if any(field in state for field in ("current_regime", "regime_name", "selected_ids", "prior_result")):
        raise ValueError("State prior chứa alias trùng nguồn thông tin")
    missing = set(PRIOR_STATE_FIELDS).difference(state)
    if missing:
        raise ValueError(f"Decision enabled thiếu field prior: {sorted(missing)}")
    prior = {field: copy_prior_json(state[field]) for field in PRIOR_STATE_FIELDS}
    prior["prior_config"] = config
    query = normalize_prior_query_context({**state, **prior})
    prior.update(market_regime=query["market_regime"], current_signals=query["current_signals"])
    for name in ("trend", "pattern", "indicator", "alpha", "sentiment"):
        report = state.get(f"{name}_report")
        if type(report) is not str or not report.strip() or report in ("No data.", "Không có dữ liệu."):
            raise ValueError(f"Decision prior yêu cầu đủ Full reports: {name}")
    proof = prior["prior_provenance"]
    groups = {"contract_version", "context", "prices", "news", "regime", "signals", "bank"}
    if type(proof) is not dict or set(proof) != groups or proof["contract_version"] != "prior_provenance_v1":
        raise ValueError("Provenance Decision thiếu hoặc sai hợp đồng")
    context = proof["context"]
    if (type(context) is not dict or set(context) != {"symbol", "as_of_date", "time_frame", "provider_mode"}
            or context["symbol"] != query["stock_name"] or context["as_of_date"] != query["as_of_date"]
            or context["time_frame"] != timeframe
            or context["provider_mode"] not in ("historical_prefix", "fixed_train_oos")):
        raise ValueError("Provenance context khác query")
    if any(type(proof[group]) is not dict for group in groups - {"contract_version", "context"}):
        raise ValueError("Các nhóm provenance phải là object")
    # Import muộn để tránh vòng decision_agent → retriever → backtest → graph_setup.
    from core.bayesian_memory import iso_date
    from core.bayesian_retriever import VERSIONS, format_compact_prior_prefix

    tasks, stats, metadata = (prior[field] for field in ("prior_tasks", "prior_stats", "prior_metadata"))
    keys = set(VERSIONS) | {
        "bank_sha256", "symbol", "as_of_date", "current_regime", "mode", "scope", "requested_k", "seed",
        "eligible_count", "matched_regime_count", "candidate_count", "effective_seed", "selected_count",
        "selected_ids", "selected_scores", "status", "reason",
    }
    if type(tasks) is not list or type(metadata) is not dict or set(metadata) != keys:
        raise ValueError("Tasks/metadata Decision sai schema W3")
    expected = {**VERSIONS, "symbol": query["stock_name"], "as_of_date": query["as_of_date"],
                "current_regime": query["market_regime"]["regime_name"],
                "mode": config["mode"], "scope": config["scope"], "requested_k": config["k"], "seed": config["seed"]}
    if any(type(metadata[key]) is not type(value) or metadata[key] != value for key, value in expected.items()):
        raise ValueError("Metadata khác config/query/version")
    bank_hash = metadata["bank_sha256"]
    if type(bank_hash) is not str or re.fullmatch(r"[0-9a-f]{64}", bank_hash) is None:
        raise ValueError("Metadata thiếu hash kho hợp lệ")
    bank = proof["bank"]
    bank_versions = bank.get("versions")
    if (bank.get("bank_sha256") != bank_hash or type(bank_versions) is not dict
            or set(bank_versions) != set(VERSIONS)
            or any(type(bank_versions[key]) is not type(value) or bank_versions[key] != value
                   for key, value in VERSIONS.items())
            or any(bank.get(field) != config[field] for field in ("bank_path", "manifest_path", "audit_path"))):
        raise ValueError("Provenance bank khác config/metadata")
    for task in tasks:
        if type(task) is not dict or iso_date(task.get("exit_date")) >= query["as_of_date"]:
            raise ValueError("Task prior chưa đóng trước cutoff")
        if config["scope"] == "same_symbol" and task.get("symbol") != query["stock_name"]:
            raise ValueError("Task prior khác scope symbol")
        if config["mode"] == "bayesian_regime" and task.get("regime") != expected["current_regime"]:
            raise ValueError("Task Bayesian khác regime query")
    k, selected = config["k"], len(tasks)
    if type(metadata["selected_count"]) is not int or metadata["selected_count"] != selected or selected > k:
        raise ValueError("Selected count khác tasks/K")
    ids = [task.get("episode_id") for task in tasks]
    if metadata["selected_ids"] != ids or type(metadata["selected_scores"]) is not list:
        raise ValueError("Selected IDs/scores khác tasks")
    scores = metadata["selected_scores"]
    if len(scores) != selected:
        raise ValueError("Số score khác số task")
    for identifier, item in zip(ids, scores):
        if type(item) is not dict or set(item) != {"episode_id", "score"} or item["episode_id"] != identifier:
            raise ValueError("Score sai schema hoặc thứ tự ID")
        score = item["score"]
        if config["mode"] in ("bayesian_regime", "similarity"):
            if type(score) is not float or not 0 <= score <= 1:
                raise ValueError("Score similarity phải là float trong 0..1")
        elif score is not None:
            raise ValueError("Random/Recent không có score similarity")
    counts = [metadata[field] for field in ("eligible_count", "matched_regime_count", "candidate_count")]
    if k == 0:
        if (tasks or stats is not None or any(value is not None for value in counts)
                or metadata["status"] != "disabled" or metadata["reason"] != "k_zero"
                or metadata["effective_seed"] is not None):
            raise ValueError("Original K=0 sai tasks/stats/metadata")
    else:
        if any(type(value) is not int or value < 0 for value in counts):
            raise ValueError("Counts metadata phải là int không âm")
        eligible, matched, candidates = counts
        if matched > eligible or candidates != (matched if config["mode"] == "bayesian_regime" else eligible):
            raise ValueError("Population/candidate counts khác mode")
        if selected != min(k, candidates):
            raise ValueError("Selected count không khớp candidate count")
        status = "empty" if selected == 0 else "partial" if selected < k else "complete"
        reason = ("no_eligible_history" if eligible == 0 else "no_matching_regime") if selected == 0 else (
            "insufficient_candidates" if selected < k else None)
        if metadata["status"] != status or metadata["reason"] != reason:
            raise ValueError("Status/reason khác tình trạng selection")
        if (type(stats) is not dict or stats.get("regime") != expected["current_regime"]
                or type(stats.get("population_count")) is not int or stats["population_count"] != matched):
            raise ValueError("Stats khác population regime metadata")
        seed = metadata["effective_seed"]
        if config["mode"] == "random":
            if type(seed) is not str or re.fullmatch(r"[0-9a-f]{64}", seed) is None:
                raise ValueError("Random thiếu effective seed")
        elif seed is not None:
            raise ValueError("Mode không phải Random phải có effective seed None")
    if type(prior["bayesian_prior_context"]) is not str:
        raise ValueError("Prefix prior phải là str")
    if not callable(source_validator):
        raise ValueError("Decision enabled chưa có hàm xác minh nguồn PIT")
    projection = {**prior, **query, "time_frame": timeframe, "is_backtest": True,
                  "ablation_config": ablation,
                  **{f"{name}_report": state[f"{name}_report"]
                     for name in ("trend", "pattern", "indicator", "alpha", "sentiment")}}
    # Callback nhận bản sao JSON; không đưa DataFrame/message/provider vào proof.
    result = source_validator(deepcopy(projection))
    if result is not None:
        raise ValueError("Hàm xác minh nguồn phải trả None hoặc ném ngoại lệ")
    prefix = format_compact_prior_prefix(tasks, stats)
    if len(prefix) > 600 or prefix != prior["bayesian_prior_context"]:
        raise ValueError("Prefix không khớp formatter W3 hoặc vượt 600 ký tự")
    prepared = {**state, **prior, "time_frame": timeframe, "ablation_config": ablation}
    return prepared, prefix
