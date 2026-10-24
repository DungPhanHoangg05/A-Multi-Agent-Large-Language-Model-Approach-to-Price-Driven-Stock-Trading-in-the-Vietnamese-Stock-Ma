"""Posterior A và pooling U-BICL từ ba tập PIT rời nhau, không dùng top-K."""

from __future__ import annotations

from copy import deepcopy
from datetime import date
import math
from typing import Any

from scipy.stats import beta

from core.bayesian_memory import REGIMES, SYMBOLS, iso_date
from core.bayesian_retriever import BayesianPriorRetriever, PREFIX_METRICS, normalize_signals
from core.historical_signals import digest
from core.price_feature_index import _json_bytes
from core.prior_conditional_statistics import conditional_metric
from core.unified_bayes_memory import UnifiedMemory, reject_decision

VERSION = "unified_bayes_statistics_v1"
LAMBDAS = (2, 4, 8)
MODELS = ("A_tp_pool", "pool_2", "pool_4", "pool_8")


def partition_records(records: list[dict[str, Any]], *, symbol: str, as_of_date: str,
                      current_regime: str, current_signals: dict[str, str]) -> dict[str, Any]:
    """Chia metadata trước đọc nhãn; biên memory kiểm thêm integrity của pool khai PIT."""
    BayesianPriorRetriever._validate_query(symbol=symbol, as_of_date=as_of_date, current_regime=current_regime,
        current_signals=current_signals, mode="bayesian_regime", k=3, seed=42, scope="same_symbol")
    signals = normalize_signals(current_signals)
    result: dict[str, Any] = {key: [] for key in ("C", "B1", "B2", "excluded")}
    seen = set()
    if type(records) is not list:
        raise ValueError("Metadata partition phải là danh sách")
    for row in records:
        if (type(row) is not dict or set(row) != {"episode_id", "symbol", "as_of_date", "exit_date", "regime", "agent_signals"}
                or type(row["episode_id"]) is not str or not row["episode_id"].strip() or row["episode_id"] in seen
                or type(row["symbol"]) is not str or row["symbol"] not in SYMBOLS
                or type(row["regime"]) is not str or row["regime"] not in REGIMES):
            raise ValueError("Metadata partition sai schema hoặc ID trùng")
        seen.add(row["episode_id"])
        cutoff, exit_date = iso_date(row["as_of_date"]), iso_date(row["exit_date"])
        if not cutoff < exit_date:
            raise ValueError("Metadata partition sai thứ tự ngày")
        if row["symbol"] != symbol or cutoff >= as_of_date or exit_date >= as_of_date:
            result["excluded"].append(row["episode_id"])
            continue
        prior = normalize_signals(row["agent_signals"])
        group = "B2" if row["regime"] != current_regime else (
            "C" if all(prior[key] == signals[key] for key in ("trend", "pattern")) else "B1")
        result[group].append(row["episode_id"])
    return {key: sorted(values) for key, values in result.items()}


def posterior(*, nC: int, sC: int, n1: int, s1: int, n2: int, s2: int,
              lambda_value: int | None = None) -> dict[str, Any]:
    """Tính Beta plug-in; C rỗng luôn giữ posterior/CrI null, không điền 0,5."""
    for n, s in ((nC, sC), (n1, s1), (n2, s2)):
        if type(n) is not int or type(s) is not int or not 0 <= s <= n:
            raise ValueError("Counts posterior phải là số nguyên gốc hợp lệ")
    if lambda_value is not None and (type(lambda_value) is not int or lambda_value not in LAMBDAS):
        raise ValueError("Pooling chỉ nhận lambda 2, 4 hoặc 8 đã khóa")
    reasons = [] if nC else ["NO_CONDITIONAL_HISTORY"]
    if not n1:
        reasons.append("NO_REGIME_BACKGROUND")
    if lambda_value is not None and not n2:
        reasons.append("NO_CROSS_REGIME_BACKGROUND")
    strength = 4 if lambda_value is None else lambda_value
    try:
        m2 = float((s2 + 1) / (n2 + 2)) if lambda_value is not None else None
        m1 = float((s1 + 1) / (n1 + 2)) if lambda_value is None else (
            float((s1 + strength * m2) / (n1 + strength)) if n1 else m2)
        pa, pb = float(strength * m1), float(strength * (1 - m1))
        weight = float(strength / (nC + strength))
    except (OverflowError, ZeroDivisionError) as error:
        raise ValueError("Counts posterior vượt miền số hữu hạn") from error
    if not all(math.isfinite(v) and v > 0 for v in (pa, pb, weight)):
        raise ValueError("Hyperprior không hữu hạn dương")
    alpha = beta_param = mean = interval = None
    if nC:
        try:
            alpha, beta_param = float(sC + pa), float(nC - sC + pb)
            mean = float(alpha / (alpha + beta_param))
            lower, upper = (float(value) for value in beta.ppf([.025, .975], alpha, beta_param))
        except (OverflowError, ZeroDivisionError) as error:
            raise ValueError("Posterior vượt miền số hữu hạn") from error
        if (not all(math.isfinite(v) for v in (alpha, beta_param, mean, lower, upper))
                or not 0 <= mean <= 1 or not 0 <= lower <= upper <= 1):
            raise ValueError("Posterior/CrI Beta không hợp lệ")
        interval = {"level": .95, "method": "equal_tailed_beta_plugin", "lower": lower,
                    "upper": upper, "width": float(upper - lower)}
    return {"backbone": "A_tp_pool" if lambda_value is None else "hierarchical_pool",
        "lambda": lambda_value, "m2": m2, "m1": m1, "prior_alpha": pa, "prior_beta": pb,
        "posterior_alpha": alpha, "posterior_beta": beta_param, "posterior_mean": mean,
        "credible_interval": interval, "prior_weight": weight,
        "status": "OBSERVED" if nC else "NO_CONDITIONAL_HISTORY", "reason_codes": reasons}


def stats_gate(backbone: str, *, population: int, nC: int, background: int,
               width: float | None) -> dict[str, Any]:
    """Tách raw posterior khỏi readiness, giữ các ngưỡng biên đã khóa."""
    if backbone not in ("A_tp_pool", "hierarchical_pool") or any(
            type(n) is not int or n < 0 for n in (population, nC, background)) or nC > population:
        raise ValueError("Counts/backbone gate thống kê không hợp lệ")
    if width is not None and (type(width) not in (int, float) or not math.isfinite(width) or not 0 <= width <= 1):
        raise ValueError("Độ rộng CrI không hợp lệ")
    reasons = []
    support = population if backbone == "A_tp_pool" else background
    if support < 20:
        reasons.append("LOW_POPULATION" if backbone == "A_tp_pool" else "LOW_BACKGROUND")
    if nC < 5:
        reasons.append("LOW_CONDITIONAL_SUPPORT")
    if width is None:
        reasons.append("MISSING_POSTERIOR")
    elif width > .75:
        reasons.append("WIDE_CREDIBLE_INTERVAL")
    return {"ready": not reasons, "reason_codes": reasons}


class _Counter:
    """Tái dùng nguyên masks bốn metric A; guard nhận cùng snapshot U-BICL."""

    def __init__(self, memory: UnifiedMemory) -> None:
        self.memory = memory

    def _assert_pool(self, records: list[dict[str, Any]], *, symbol: str, as_of_date: str,
                     scope: str, regime: str) -> None:
        """Không cho hàm legacy đếm dữ liệu sai PIT, mã hoặc regime."""
        self.memory.assert_evidence(records, symbol, as_of_date)
        if scope != "same_symbol" or any(row["regime"] != regime for row in records):
            raise ValueError("Population metric A khác scope/regime query")

    _compute_statistics = BayesianPriorRetriever._compute_statistics


class UnifiedBayesStatistics:
    """Tạo evidence thuần trên RAM, luôn lọc PIT trước khi đếm outcome."""

    def __init__(self, memory: UnifiedMemory) -> None:
        if not isinstance(memory, UnifiedMemory):
            raise ValueError("Thống kê cần memory U-BICL đã xác minh")
        self.memory = memory
        self.memory_identity = memory.identity
        self._counter = _Counter(memory)
        self._metadata = deepcopy(memory._metadata)

    def evidence(self, *, symbol: str, as_of_date: str, current_regime: str,
                 current_signals: dict[str, str]) -> dict[str, Any]:
        """Chia C/B1/B2 sau exit<cutoff; không áp tuổi/feature/similarity cho stats."""
        reject_decision(current_signals)
        BayesianPriorRetriever._validate_query(symbol=symbol, as_of_date=as_of_date,
            current_regime=current_regime, current_signals=current_signals,
            mode="bayesian_regime", k=3, seed=42, scope="same_symbol")
        signals = normalize_signals(current_signals)
        eligible = self.memory.eligible(symbol, as_of_date)
        self.memory.assert_evidence(eligible, symbol, as_of_date)
        partition = partition_records([{key: row[key] for key in (
            "episode_id", "symbol", "as_of_date", "exit_date", "regime", "agent_signals")} for row in eligible],
            symbol=symbol, as_of_date=as_of_date, current_regime=current_regime, current_signals=signals)
        if partition["excluded"]:
            raise ValueError("Pool khai PIT vẫn chứa future/self hoặc khác mã")
        by_id = {row["episode_id"]: row for row in eligible}
        groups = {key: [by_id[identifier] for identifier in partition[key]] for key in ("C", "B1", "B2")}
        ids = [row["episode_id"] for rows in groups.values() for row in rows]
        if len(ids) != len(set(ids)) or set(ids) != {row["episode_id"] for row in eligible}:
            raise ValueError("Partition C/B1/B2 không rời nhau hoặc thiếu population PIT")
        summaries = {}
        for group, rows in groups.items():
            ages = [(date.fromisoformat(as_of_date) - date.fromisoformat(row["as_of_date"])).days for row in rows]
            summaries[group] = {"episode_ids": [row["episode_id"] for row in rows],
                "n": len(rows), "s": sum(int(row["outcome"]["net_return_pct"] > 0) for row in rows),
                "age_days": {"min": min(ages) if ages else None, "max": max(ages) if ages else None,
                             "mean": float(sum(ages) / len(ages)) if ages else None},
                "time_cluster_count_90_sessions": len({self._metadata[row["episode_id"]]["cutoff_session_index"] // 90 for row in rows})}
        counts = {key: summaries[group][field] for group, pairs in (
            ("C", (("nC", "n"), ("sC", "s"))), ("B1", (("n1", "n"), ("s1", "s"))),
            ("B2", (("n2", "n"), ("s2", "s")))) for key, field in pairs}
        posteriors = {}
        for name, strength in zip(MODELS, (None, *LAMBDAS)):
            item = posterior(**counts, lambda_value=strength)
            interval = item["credible_interval"]
            item["gate"] = stats_gate(item["backbone"], population=counts["nC"] + counts["n1"],
                nC=counts["nC"], background=counts["n1"] + counts["n2"], width=None if interval is None else interval["width"])
            posteriors[name] = item
        # A_reference giữ cả bốn metric/masks legacy trên cùng memory chung.
        raw = {group: self._counter._compute_statistics(groups[group], symbol=symbol, as_of_date=as_of_date,
            current_regime=current_regime, scope="same_symbol")["metrics"] for group in ("C", "B1")}
        reference = {metric: conditional_metric(metric, raw["C"][metric]["numerator"], raw["C"][metric]["denominator"],
            raw["B1"][metric]["numerator"], raw["B1"][metric]["denominator"]) for metric in PREFIX_METRICS}
        if reference["win_rate_long"]["posterior_mean"] != posteriors["A_tp_pool"]["posterior_mean"]:
            raise ValueError("Posterior A mục tiêu khác metric legacy trên cùng nguồn")
        result = {"statistics_version": VERSION, "memory_sha256": self.memory_identity,
            "index_sha256": self.memory.index.identity, "symbol": symbol, "as_of_date": as_of_date,
            "current_regime": current_regime, "current_signals": signals, "groups": summaries, "counts": counts,
            "posteriors": posteriors, "reference_metrics": reference,
            "interpretation": "historical_beta_plugin_not_calibrated_query_probability",
            "raw_support_is_effective_sample_size": False}
        _json_bytes(result)
        result["evidence_sha256"] = digest(result)
        return result

    def validate(self, evidence: dict[str, Any]) -> None:
        """Tái dựng từ memory/query thật; tự reseal không hợp thức hóa counts hay gate."""
        _json_bytes(evidence)
        if type(evidence) is not dict or not {"symbol", "as_of_date", "current_regime", "current_signals"} <= evidence.keys():
            raise ValueError("Evidence thống kê thiếu query")
        expected = self.evidence(**{key: evidence[key] for key in ("symbol", "as_of_date", "current_regime", "current_signals")})
        if digest(evidence) != digest(expected):
            raise ValueError("Evidence thống kê khác nguồn PIT, partition hoặc posterior đã tái kiểm")
