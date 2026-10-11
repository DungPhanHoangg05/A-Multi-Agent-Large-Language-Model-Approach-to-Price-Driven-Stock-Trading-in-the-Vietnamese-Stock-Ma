"""Thống kê điều kiện với hyperprior từ background PIT rời nhau, không dùng K."""

from __future__ import annotations

import math
from typing import Any

from scipy.stats import beta

from core.bayesian_retriever import BayesianPriorRetriever, PREFIX_METRICS, normalize_signals
from core.historical_signals import digest
from core.prior_config import copy_prior_json
from core.prior_price_similarity import SIGNAL_FIELDS

STATISTICS_VERSION = "conditional_disjoint_beta_v1"
EVIDENCE_VERSION = "prior_evidence_v3"


def statistics_config(value: dict[str, Any] | None = None) -> dict[str, float]:
    """Chỉ nhận sức co dương/hữu hạn; mặc định đúng cấu hình đã đăng ký."""
    if value is not None and (type(value) is not dict or set(value) - {"shrink_strength"}):
        raise ValueError("Cấu hình thống kê chứa trường ngoài whitelist")
    strength = (value or {}).get("shrink_strength", 4.)
    if type(strength) not in (int, float):
        raise ValueError("Sức co phải là số Python gốc, không nhận bool/NumPy scalar")
    try:
        strength = float(strength)
    except OverflowError as exc:
        raise ValueError("Sức co vượt miền số hữu hạn") from exc
    if not math.isfinite(strength) or strength <= 0:
        raise ValueError("Sức co phải hữu hạn và dương")
    return {"shrink_strength": strength}


def _counts(success: int, support: int) -> dict[str, Any]:
    """Mỗi cycle góp tối đa một quan sát; mẫu số rỗng giữ rate=null."""
    if type(success) is not int or type(support) is not int or not 0 <= success <= support:
        raise ValueError("Success/support phải là số nguyên gốc hợp lệ")
    return {"success_count": success, "support_count": support,
            "raw_rate": float(success / support) if support else None}


def conditional_metric(metric_id: str, conditional_success: int, conditional_support: int,
                       background_success: int, background_support: int, *,
                       shrink_strength: float = 4.) -> dict[str, Any]:
    """Empirical Bayes plug-in: B chỉ định mean prior, C là likelihood duy nhất.

    CrI là khoảng tỷ lệ lịch sử có điều kiện trên hyperprior, không phải
    xác suất query/LLM được hiệu chuẩn hoặc khoảng dự báo lợi nhuận.
    """
    if type(metric_id) is not str or metric_id not in PREFIX_METRICS:
        raise ValueError("Metric thống kê điều kiện không hợp lệ")
    strength = statistics_config({"shrink_strength": shrink_strength})["shrink_strength"]
    c = _counts(conditional_success, conditional_support)
    b = _counts(background_success, background_support)
    p = _counts(conditional_success + background_success, conditional_support + background_support)
    background_mean = float((background_success + 1) / (background_support + 2))
    alpha, beta_prior = strength * background_mean, strength * (1 - background_mean)
    if not all(math.isfinite(v) and v > 0 for v in (alpha, beta_prior)):
        raise ValueError("Hyperprior không biểu diễn được bằng số hữu hạn dương")
    reasons = ["FIXED_SYMMETRIC_PRIOR"] if not background_support else []
    pa = pb = mean = interval = None
    if conditional_support:
        try:
            pa = float(alpha + conditional_success)
            pb = float(beta_prior + (conditional_support - conditional_success))
        except OverflowError as exc:
            raise ValueError("Counts posterior vượt miền số hữu hạn") from exc
        total = pa + pb
        if not all(math.isfinite(v) and v > 0 for v in (pa, pb, total)):
            raise ValueError("Tham số posterior không hữu hạn dương")
        mean = float(pa / total)
        lower, upper = float(beta.ppf(.025, pa, pb)), float(beta.ppf(.975, pa, pb))
        if not all(math.isfinite(v) for v in (mean, lower, upper)) or not 0 <= lower <= upper <= 1:
            raise ValueError("Posterior hoặc khoảng Beta không hợp lệ")
        interval = {"level": .95, "method": "equal_tailed_beta_plugin", "lower": lower,
                    "upper": upper, "width": float(upper - lower)}
    else:
        reasons.append("NO_CONDITIONAL_HISTORY")
    return {"metric_id": metric_id, "raw_counts": {"population": p, "conditional": c, "background": b},
            "hyperprior_source": "DISJOINT_BACKGROUND" if background_support else "FIXED_SYMMETRIC_PRIOR",
            "background_mean": background_mean, "shrink_strength": strength,
            "prior_alpha": float(alpha), "prior_beta": float(beta_prior),
            "posterior_alpha": pa, "posterior_beta": pb, "posterior_mean": mean,
            "credible_interval": interval, "status": "OBSERVED" if conditional_support else "NO_CONDITIONAL_HISTORY",
            "reason_codes": reasons}


def compute_conditional_statistics(retriever: BayesianPriorRetriever, *, symbol: str, as_of_date: str,
                                   current_regime: str, current_signals: dict[str, str],
                                   config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Dựng P/C/B từ bank đã kiểm, lọc PIT trước đọc outcome để đếm thống kê."""
    settings = statistics_config(config)
    retriever._validate_query(symbol=symbol, as_of_date=as_of_date, current_regime=current_regime,
        current_signals=current_signals, mode="bayesian_regime", k=3, seed=42, scope="same_symbol")
    signals = normalize_signals(current_signals)
    pool = retriever.prepare_query(symbol=symbol, as_of_date=as_of_date, current_regime=current_regime,
                                  current_signals=signals)
    eligible, population = pool["eligible_tasks"], pool["regime_population"]
    retriever._assert_pool(eligible, symbol=symbol, as_of_date=as_of_date, scope="same_symbol")
    retriever._assert_pool(population, symbol=symbol, as_of_date=as_of_date, scope="same_symbol", regime=current_regime)
    expected = {key for key, row in retriever._verified_by_id.items()
                if row["symbol"] == symbol and row["exit_date"] < as_of_date}
    expected_p = {key for key in expected if retriever._verified_by_id[key]["regime"] == current_regime}
    if expected != {r["episode_id"] for r in eligible} or expected_p != {r["episode_id"] for r in population}:
        raise ValueError("Population thống kê thiếu/thừa cycle so với bank PIT đã kiểm")
    population = sorted(population, key=lambda row: row["episode_id"])
    conditional, background = [], []
    for row in population:
        prior = normalize_signals(row["agent_signals"])
        target = conditional if all(prior[key] == signals[key] for key in SIGNAL_FIELDS) else background
        target.append(row)
    groups = {"population": population, "conditional": conditional, "background": background}
    # Tái dùng đúng masks/nhãn kinh tế hiện hữu; kiểm raw P độc lập với C+B.
    raw = {name: retriever._compute_statistics(rows, symbol=symbol, as_of_date=as_of_date,
        current_regime=current_regime, scope="same_symbol")["metrics"] for name, rows in groups.items()}
    metrics = {}
    for key in PREFIX_METRICS:
        c, b = raw["conditional"][key], raw["background"][key]
        item = conditional_metric(key, c["numerator"], c["denominator"], b["numerator"], b["denominator"],
                                  shrink_strength=settings["shrink_strength"])
        if item["raw_counts"]["population"] != _counts(raw["population"][key]["numerator"], raw["population"][key]["denominator"]):
            raise ValueError("Counts P khác tổng counts của C và B rời nhau")
        metrics[key] = item
    evidence = {"evidence_contract_version": EVIDENCE_VERSION, "statistics_version": STATISTICS_VERSION,
        "contract_stage": "CONDITIONAL_STATISTICS", "interpretation": "historical_rates_empirical_bayes_plugin",
        "symbol": symbol, "as_of_date": as_of_date, "current_regime": current_regime, "current_signals": signals,
        "population_scope": "same_symbol_same_regime_pit", "bank_sha256": retriever._bank_sha256,
        "population_sha256": digest(population), "eligible_count": len(eligible), "population_count": len(population),
        "conditional_count": len(conditional), "background_count": len(background),
        "groups": {name: {"episode_ids": [row["episode_id"] for row in rows], "cycle_count": len(rows)}
                   for name, rows in groups.items()}, "config": settings, "config_sha256": digest(settings), "metrics": metrics}
    evidence["evidence_sha256"] = digest(evidence)
    return copy_prior_json(evidence)


def validate_conditional_statistics(evidence: dict[str, Any], retriever: BayesianPriorRetriever) -> None:
    """Tái tính toàn bộ counts/partition/posterior từ nguồn, kể cả artifact đã tự băm lại."""
    evidence = copy_prior_json(evidence)
    if type(evidence) is not dict or not {"symbol", "as_of_date", "current_regime", "current_signals", "config"}.issubset(evidence):
        raise ValueError("Artifact thống kê thiếu query/config")
    expected = compute_conditional_statistics(retriever,
        **{key: evidence[key] for key in ("symbol", "as_of_date", "current_regime", "current_signals", "config")})
    if digest(evidence) != digest(expected):
        raise ValueError("Artifact thống kê khác nguồn PIT, partition, counts, hyperprior hoặc posterior")
