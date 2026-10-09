"""Evidence Beta–Binomial và gate chất lượng: chỉ dùng chu kỳ lịch sử PIT."""

from datetime import date
import math
from typing import Any

from scipy.stats import beta

from core.bayesian_retriever import BayesianPriorRetriever, PREFIX_METRICS, _prefix_task_line, _validate_prefix_statistics
from core.bayesian_memory import SYMBOLS, REGIMES, iso_date
from core.historical_signals import digest
from core.prior_config import copy_prior_json

VERSIONS = {"evidence_contract_version": "prior_evidence_v2",
            "statistics_version": "regime_beta_binomial_v2", "gate_version": "prior_quality_gate_v1",
            "prefix_version": "compact_brpp_v2"}
DEFAULTS = {"prior_alpha": 1., "prior_beta": 1., "min_population_count": 20,
            "min_similarity": .75, "max_prior_age_days": 730, "requested_k": 3,
            "seed": 42, "scope": "same_symbol"}


def normalize_evidence_config(value: dict[str, Any] | None = None) -> dict[str, Any]:
    """Kiểm config ứng viên kỹ thuật, không coi các ngưỡng là đã tối ưu."""
    if value is not None and (type(value) is not dict or set(value) - set(DEFAULTS)):
        raise ValueError("Config evidence chứa field ngoài hợp đồng")
    config = {**DEFAULTS, **(value or {})}
    for field in ("prior_alpha", "prior_beta", "min_similarity"):
        v = config[field]
        if type(v) not in (int, float) or not math.isfinite(v):
            raise ValueError("Tham số evidence phải hữu hạn, không nhận bool")
        config[field] = float(v)
    if config["prior_alpha"] <= 0 or config["prior_beta"] <= 0 or not 0 <= config["min_similarity"] <= 1:
        raise ValueError("Alpha/beta phải dương, similarity thuộc [0,1]")
    for field in ("min_population_count", "max_prior_age_days", "requested_k", "seed"):
        if type(config[field]) is not int:
            raise ValueError("Tham số đếm phải int gốc")
    if (config["min_population_count"] < 1 or config["max_prior_age_days"] < 1
            or not 0 <= config["requested_k"] <= 3 or config["seed"] != 42 or config["scope"] != "same_symbol"):
        raise ValueError("Config evidence ngoài phạm vi đã khóa")
    return config


def posterior_metric(metric_id: str, success: int, support: int, alpha: float, beta_prior: float) -> dict[str, Any]:
    """Posterior của tỷ lệ lịch sử; n=0 trả null thay vì giả bằng chứng."""
    config = normalize_evidence_config({"prior_alpha": alpha, "prior_beta": beta_prior})
    if type(success) is not int or type(support) is not int or not 0 <= success <= support:
        raise ValueError("Counts posterior không hợp lệ")
    if metric_id not in PREFIX_METRICS:
        raise ValueError("Metric evidence không được hỗ trợ")
    a, b = config["prior_alpha"], config["prior_beta"]
    pa, pb = (a + success, b + support - success) if support else (None, None)
    interval = None if not support else {"level": .95, "method": "equal_tailed_beta",
                                       "lower": float(beta.ppf(.025, pa, pb)), "upper": float(beta.ppf(.975, pa, pb))}
    return {"metric_id": metric_id, "success_count": success, "support_count": support,
            "raw_rate": float(success / support) if support else None,
            "prior_alpha": a, "prior_beta": b, "posterior_alpha": pa, "posterior_beta": pb,
            "posterior_mean": float(pa / (pa + pb)) if support else None,
            "credible_interval": interval, "status": "OBSERVED" if support else "NO_HISTORY"}


def retrieve_evidence(retriever: BayesianPriorRetriever, *, symbol: str, as_of_date: str,
                      current_regime: str, current_signals: dict[str, str],
                      config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Lọc PIT trước stats/ranking; quality gate không dùng kết quả query để chọn ví dụ."""
    config = normalize_evidence_config(config)
    query = {"symbol": symbol, "as_of_date": as_of_date, "current_regime": current_regime,
             "current_signals": current_signals, "mode": "bayesian_regime", "scope": "same_symbol", "seed": 42}
    pool = retriever.prepare_query(**query, k=3)
    population = pool["regime_population"]
    stats = retriever._compute_statistics(population, symbol=symbol, as_of_date=as_of_date,
                                         current_regime=current_regime, scope="same_symbol")
    ranked, scores = retriever._select_similarity(population, len(population), current_signals)
    cutoff = date.fromisoformat(as_of_date)
    ages = {r["episode_id"]: {"age_days": (cutoff - date.fromisoformat(r["as_of_date"])).days,
                              "exit_age_days": (cutoff - date.fromisoformat(r["exit_date"])).days} for r in ranked}
    candidates = [r for r in ranked if scores[r["episode_id"]] >= config["min_similarity"]
                  and ages[r["episode_id"]]["age_days"] <= config["max_prior_age_days"]]
    reasons = []
    if config["requested_k"] == 0:
        status, reasons = "DISABLED", ["PRIOR_DISABLED"]
    else:
        if not population:
            reasons.append("NO_HISTORY")
        if len(population) < config["min_population_count"]:
            reasons.append("LOW_SUPPORT")
        if not candidates:
            reasons.append("NO_QUALITY_CANDIDATE")
        status = "INSUFFICIENT_EVIDENCE" if reasons else "READY"
    tasks = candidates[:config["requested_k"]] if status == "READY" else []
    retriever._validate_selection(tasks, symbol=symbol, as_of_date=as_of_date, current_regime=current_regime,
                                  scope="same_symbol", mode="bayesian_regime", k=config["requested_k"])
    evidence = {**VERSIONS, "symbol": symbol, "as_of_date": as_of_date, "regime": current_regime,
                "population_scope": "same_symbol_same_regime_pit", "bank_sha256": pool["metadata"]["bank_sha256"],
                "config": config, "config_sha256": digest(config), "eligible_count": len(pool["eligible_tasks"]),
                "population_count": len(population), "quality_candidate_count": len(candidates),
                "requested_k": config["requested_k"], "effective_k": len(tasks), "status": status,
                "reason_codes": reasons, "selected_ids": [r["episode_id"] for r in tasks],
                "selected_scores": [float(scores[r["episode_id"]]) for r in tasks],
                "selected_ages": [ages[r["episode_id"]] for r in tasks], "tasks": tasks,
                "metrics": {key: posterior_metric(key, stats["metrics"][key]["numerator"],
                    stats["metrics"][key]["denominator"], config["prior_alpha"], config["prior_beta"]) for key in PREFIX_METRICS}}
    evidence["evidence_sha256"] = digest(evidence)
    validate_evidence(evidence)
    return copy_prior_json(evidence)


def validate_evidence(evidence: dict[str, Any]) -> None:
    """Kiểm hash, counts, posterior và PIT của artifact; caller còn phải so với kho nguồn."""
    evidence = copy_prior_json(evidence)
    keys = {*VERSIONS, "symbol", "as_of_date", "regime", "population_scope", "bank_sha256", "config",
            "config_sha256", "evidence_sha256", "eligible_count", "population_count", "quality_candidate_count",
            "requested_k", "effective_k", "status", "reason_codes", "selected_ids", "selected_scores",
            "selected_ages", "tasks", "metrics"}
    if type(evidence) is not dict or set(evidence) != keys:
        raise ValueError("Schema evidence không hợp lệ")
    if any(evidence[k] != v for k, v in VERSIONS.items()):
        raise ValueError("Version evidence không hợp lệ")
    iso_date(evidence["as_of_date"])
    if (evidence["symbol"] not in SYMBOLS or evidence["regime"] not in REGIMES
            or evidence["population_scope"] != "same_symbol_same_regime_pit"
            or type(evidence["bank_sha256"]) is not str or len(evidence["bank_sha256"]) != 64
            or any(c not in "0123456789abcdef" for c in evidence["bank_sha256"])):
        raise ValueError("Provenance evidence không hợp lệ")
    config = normalize_evidence_config(evidence["config"])
    if evidence["config_sha256"] != digest(config) or evidence["evidence_sha256"] != digest({k: v for k, v in evidence.items() if k != "evidence_sha256"}):
        raise ValueError("Hash evidence/config sai")
    for field in ("eligible_count", "population_count", "quality_candidate_count", "requested_k", "effective_k"):
        if type(evidence[field]) is not int or evidence[field] < 0:
            raise ValueError("Count evidence sai")
    if not 0 <= evidence["effective_k"] <= evidence["requested_k"] == config["requested_k"] <= 3:
        raise ValueError("K evidence không hợp lệ")
    if not evidence["quality_candidate_count"] <= evidence["population_count"] <= evidence["eligible_count"]:
        raise ValueError("Quan hệ population sai")
    if set(evidence["metrics"]) != set(PREFIX_METRICS):
        raise ValueError("Thiếu metric evidence")
    for key, item in evidence["metrics"].items():
        expected = posterior_metric(key, item["success_count"], item["support_count"], config["prior_alpha"], config["prior_beta"])
        if item != expected or item["support_count"] > evidence["population_count"]:
            raise ValueError("Posterior không khớp counts")
    if evidence["metrics"]["win_rate_long"]["support_count"] != evidence["population_count"]:
        raise ValueError("Mẫu số LONG không bằng population")
    _validate_prefix_statistics({"regime": evidence["regime"], "population_count": evidence["population_count"],
        "metrics": {key: {"numerator": m["success_count"], "denominator": m["support_count"], "rate": m["raw_rate"]}
                    for key, m in evidence["metrics"].items()}})
    tasks = evidence["tasks"]
    if any(type(evidence[k]) is not list or len(evidence[k]) != evidence["effective_k"]
           for k in ("tasks", "selected_ids", "selected_scores", "selected_ages")):
        raise ValueError("Số task/metadata không khớp K hiệu dụng")
    if evidence["selected_ids"] != [r["episode_id"] for r in tasks] or len(set(evidence["selected_ids"])) != len(tasks):
        raise ValueError("ID task không khớp")
    for task, score, age in zip(tasks, evidence["selected_scores"], evidence["selected_ages"]):
        _prefix_task_line(task, allow_sentiment=True)
        cutoff = date.fromisoformat(evidence["as_of_date"])
        expected_age = {"age_days": (cutoff - date.fromisoformat(task["as_of_date"])).days,
                        "exit_age_days": (cutoff - date.fromisoformat(task["exit_date"])).days}
        if (task["symbol"] != evidence["symbol"] or task["regime"] != evidence["regime"]
                or task["exit_date"] >= evidence["as_of_date"] or age != expected_age
                or type(score) is not float or not config["min_similarity"] <= score <= 1
                or age["age_days"] > config["max_prior_age_days"]):
            raise ValueError("Task evidence vi phạm PIT/quality/scope")
    reasons = (["PRIOR_DISABLED"] if not config["requested_k"] else
               (["NO_HISTORY"] if not evidence["population_count"] else []) +
               (["LOW_SUPPORT"] if evidence["population_count"] < config["min_population_count"] else []) +
               (["NO_QUALITY_CANDIDATE"] if not evidence["quality_candidate_count"] else []))
    status = "DISABLED" if not config["requested_k"] else "INSUFFICIENT_EVIDENCE" if reasons else "READY"
    if (evidence["reason_codes"] != reasons or evidence["status"] != status or evidence["effective_k"] !=
            (min(config["requested_k"], evidence["quality_candidate_count"]) if status == "READY" else 0)):
        raise ValueError("Gate evidence không khớp config/counts")


def format_evidence_prefix(evidence: dict[str, Any]) -> str:
    """BRPP v2 không quá 600 ký tự; gate off trả chuỗi rỗng đúng Original."""
    validate_evidence(evidence)
    if not evidence["effective_k"]:
        return ""
    metrics = []
    for label, key in zip(("Win", "Trap", "TrendFail", "PatternFail"), PREFIX_METRICS):
        item = evidence["metrics"][key]
        interval = item["credible_interval"]
        value = "N/A" if interval is None else f"{item['posterior_mean']:.2f}[{interval['lower']:.2f},{interval['upper']:.2f}]"
        metrics.append(f"{label}={item['success_count']}/{item['support_count']}→{value}")
    prefix = (f"[BRPP v2] R={evidence['regime']}; n={evidence['population_count']}; k={evidence['effective_k']}\n"
              + "; ".join(metrics) + "\nLịch sử: mean[CrI95%], không là dự báo query; SHORT=CASH.\n"
              + "\n".join(_prefix_task_line(task, allow_sentiment=True) for task in evidence["tasks"]))
    if len(prefix) > 600:
        raise ValueError("BRPP v2 vượt 600 ký tự; không cắt bằng chứng hoặc tự đổi K")
    return prefix
