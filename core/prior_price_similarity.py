"""Similarity tín hiệu và giá PIT; cung cấp thứ tự nền cho policy chọn ví dụ."""

from __future__ import annotations

from copy import deepcopy
import math
from typing import Any

import numpy as np

from core.bayesian_memory import copy_historical_records
from core.bayesian_retriever import BayesianPriorRetriever, normalize_signals
from core.historical_signals import digest
from core.pit_price_features import FEATURE_VERSION, PRICE_POLICY_VERSION
from core.price_feature_index import PriceFeatureIndex, SCALER_VERSION, INDEX_VERSION

METRIC_VERSION = "signal_price_similarity_v1"
RANKING_VERSION = "base_similarity_ranking_v1"
SIGNAL_FIELDS = ("trend", "pattern", "alpha_consensus", "indicator_consensus")


def _weight(value: Any) -> float:
    """Không nhận bool, NumPy scalar hoặc trọng số ngoài [0,1]."""
    if type(value) not in (int, float) or not 0 <= value <= 1 or not math.isfinite(value):
        raise ValueError("Trọng số tín hiệu phải là số Python gốc hữu hạn trong [0,1]")
    return float(value)


def signal_price_scores(*, query_signals: dict[str, str], prior_signals: list[dict[str, str]],
                        query_vector: list[float], prior_vectors: list[list[float]],
                        w_signal: float = .5) -> list[dict[str, float]]:
    """Tính S/d/P/base vector hóa trên bốn chiều; API không nhận nhãn/outcome."""
    weight = _weight(w_signal)
    query = normalize_signals(query_signals)
    if type(prior_signals) is not list or type(prior_vectors) is not list or len(prior_vectors) != len(prior_signals):
        raise ValueError("Số vector prior không khớp số bộ tín hiệu")
    signals = [normalize_signals(item) for item in prior_signals]
    for vector in [query_vector, *prior_vectors]:
        if (type(vector) is not list or len(vector) != 4
                or any(type(value) not in (int, float) for value in vector)):
            raise ValueError("Similarity cần đủ bốn chiều số gốc, không nhận bool/NumPy scalar")
    try:
        q = np.asarray(query_vector, dtype=float)
        matrix = np.asarray(prior_vectors, dtype=float).reshape(-1, 4)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Vector similarity không chuyển được thành số hữu hạn") from exc
    if not np.isfinite(q).all() or not np.isfinite(matrix).all():
        raise ValueError("Vector similarity không hữu hạn")
    if not signals:
        return []
    signal_matrix = np.asarray([[item[key] for key in SIGNAL_FIELDS] for item in signals])
    s = np.mean(signal_matrix == np.asarray([query[key] for key in SIGNAL_FIELDS]), axis=1)
    with np.errstate(over="ignore", invalid="ignore"):
        d = np.sqrt(np.mean((matrix - q) ** 2, axis=1))
        p = 1. / (1. + d)
        base = weight * s + (1. - weight) * p
    if not all(np.isfinite(value).all() for value in (s, d, p, base)):
        raise ValueError("Khoảng cách hoặc score similarity không hữu hạn")
    return [{"signal_similarity": float(a), "price_distance": float(b),
             "price_similarity": float(c), "base_score": float(e)} for a, b, c, e in zip(s, d, p, base)]


def _bind_index(retriever: BayesianPriorRetriever, index: PriceFeatureIndex) -> None:
    """Đối chiếu bank và mọi ID/ngày trên RAM một lần theo identity index."""
    if not isinstance(index, PriceFeatureIndex):
        raise ValueError("Similarity yêu cầu index được producer/loader xác minh")
    if index.identity in retriever._price_index_identities:
        return
    payload = index.payload
    if payload["provenance"]["bank"].get("bank_sha256") != retriever._bank_sha256:
        raise ValueError("Index giá thuộc bank khác retriever đã kiểm")
    rows = {row["episode_id"]: row for row in payload["records"]}
    if set(rows) != set(retriever._verified_by_id) or any(
            any(rows[key][field] != record[field] for field in ("symbol", "as_of_date", "exit_date"))
            for key, record in retriever._verified_by_id.items()):
        raise ValueError("ID/mã/cutoff/exit của index khác bank đã kiểm")
    retriever._price_index_identities.add(index.identity)


def rank_price_candidates(retriever: BayesianPriorRetriever, *, index: PriceFeatureIndex,
                          symbol: str, as_of_date: str, current_regime: str,
                          current_signals: dict[str, str], query_features: dict[str, Any],
                          w_signal: float = .5) -> dict[str, Any]:
    """Xếp base_score sau lọc PIT/mã/regime, chưa áp tuổi/diversity hoặc gate.

    Adapter chịu trách nhiệm nguồn feature query trước biên thuần này. Cả
    query/prior dùng scaler fold query từ cache đã kiểm; hot query không I/O.
    Population thống kê giữ nguyên cả episode thiếu feature; chỉ examples
    không có vector hợp lệ mới không được xếp hạng. Không fallback tín hiệu.
    """
    weight = _weight(w_signal)
    retriever._validate_query(symbol=symbol, as_of_date=as_of_date, current_regime=current_regime,
                             current_signals=current_signals, mode="bayesian_regime", k=3, seed=42,
                             scope="same_symbol")
    query_signals = normalize_signals(current_signals)
    _bind_index(retriever, index)
    query = index.transform_query(symbol, as_of_date, query_features)
    scaler = index.scaler(symbol, as_of_date)
    pool = retriever.prepare_query(symbol=symbol, as_of_date=as_of_date, current_regime=current_regime,
                                  current_signals=query_signals)
    population = pool["regime_population"]
    retriever._assert_pool(pool["eligible_tasks"], symbol=symbol, as_of_date=as_of_date, scope="same_symbol")
    retriever._assert_pool(population, symbol=symbol, as_of_date=as_of_date,
                           scope="same_symbol", regime=current_regime)
    closed = set(index.closed_episode_ids(symbol, as_of_date))
    expected = {key for key in closed if retriever._verified_by_id[key]["regime"] == current_regime}
    if (closed != {row["episode_id"] for row in pool["eligible_tasks"]}
            or expected != {row["episode_id"] for row in population}):
        raise ValueError("Population similarity thiếu/thừa episode so với bank/index PIT")
    population = sorted(population, key=lambda row: row["episode_id"])
    priors = index.prior_features(symbol, as_of_date, [row["episode_id"] for row in population])
    normalized = [normalize_signals(row["agent_signals"]) for row in population]
    trace, available = [], []
    for position, (row, prior, signals) in enumerate(zip(population, priors, normalized)):
        reasons = []
        if query["scaler_status"] != "AVAILABLE":
            reasons.append("SCALER_UNAVAILABLE")
        if query["feature_status"] != "AVAILABLE":
            reasons.append("QUERY_FEATURE_UNAVAILABLE")
        if prior["feature_status"] != "AVAILABLE":
            reasons.append("PRIOR_FEATURE_UNAVAILABLE")
        trace.append({"episode_id": row["episode_id"], "as_of_date": row["as_of_date"],
                      "exit_date": row["exit_date"], "status": "UNAVAILABLE" if reasons else "SCORED",
                      "reason_codes": reasons, "feature_reasons": prior["feature_reasons"],
                      "signal_similarity": float(sum(signals[key] == query_signals[key] for key in SIGNAL_FIELDS) / 4),
                      "price_distance": None, "price_similarity": None, "base_score": None})
        if not reasons:
            available.append(position)
    scores = signal_price_scores(query_signals=query_signals,
        prior_signals=[normalized[pos] for pos in available],
        query_vector=query["scaled_vector"],
        prior_vectors=[priors[pos]["scaled_vector"] for pos in available], w_signal=weight) if available else []
    for position, score in zip(available, scores):
        trace[position].update(score)
    # Các khóa đều độc lập nhãn kinh tế; sort ổn định theo ID rồi exit rồi score.
    ranked = sorted(available, key=lambda pos: population[pos]["episode_id"])
    ranked.sort(key=lambda pos: population[pos]["exit_date"], reverse=True)
    ranked.sort(key=lambda pos: trace[pos]["base_score"], reverse=True)
    config = {"w_signal": weight}
    return {"ranked_tasks": copy_historical_records([population[pos] for pos in ranked]),
            "regime_population": copy_historical_records(population), "trace": trace,
            "metadata": {"metric_version": METRIC_VERSION, "ranking_version": RANKING_VERSION,
                "policy_stage": "BASE_SIMILARITY", "policy_complete": False,
                "symbol": symbol, "as_of_date": as_of_date, "current_regime": current_regime,
                "scope": "same_symbol", "bank_sha256": retriever._bank_sha256,
                "feature_version": FEATURE_VERSION, "price_policy_version": PRICE_POLICY_VERSION,
                "scaler_version": SCALER_VERSION, "index_version": INDEX_VERSION,
                "index_sha256": index.identity, "scaler_sha256": scaler["scaler_sha256"],
                "fold_id": scaler["fold_id"], "fit_cutoff": scaler["fit_cutoff"],
                "fit_inclusive": scaler["fit_inclusive"], "fit_count": scaler["fit_count"],
                "freeze_date": scaler["freeze_date"], "scaler_status": scaler["status"],
                "query_feature_status": query["feature_status"], "query_feature_reasons": deepcopy(query["feature_reasons"]),
                "config": config, "config_sha256": digest(config), "eligible_count": len(closed),
                "population_count": len(population), "scored_count": len(ranked),
                "unavailable_count": len(population) - len(ranked),
                "ranked_ids": [population[pos]["episode_id"] for pos in ranked]}}
