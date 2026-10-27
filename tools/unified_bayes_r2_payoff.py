"""Payoff NIG của R2: thuần số học, lọc metadata PIT trước khi đọc nhãn."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import math
from pathlib import Path
from typing import Any, Mapping

import numpy as np
from scipy.stats import t

from core.bayesian_memory import read_json
from core.historical_signals import digest
from core.prior_backtest import canonical_hash
from core.unified_bayes_memory import reject_decision
from core.unified_bayes_statistics import partition_records, posterior, stats_gate

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = "docs/plan/week11/unified_bic_r2_protocol_v1.json"
PROTOCOL_SHA = "55cea533fe0854776d1d9bd2b0f1d138fdb71a9ec8895f1e9a14a90c8062afa0"
VERSION = "unified_bic_r2_payoff_nig_v1"
FIELDS = ("episode_id", "symbol", "as_of_date", "exit_date", "regime", "agent_signals")


def load_protocol(root: Path = ROOT) -> dict[str, Any]:
    """Protocol đăng ký trước phép đo; đổi cả ngưỡng hoặc tham số đều bị chặn."""
    spec = read_json(root / PROTOCOL)
    if canonical_hash(spec) != PROTOCOL_SHA:
        raise ValueError("Protocol R2 khác bản đã đăng ký trước phép đo")
    parent = read_json(root / spec["parent_protocol"]["path"])
    if canonical_hash(parent) != spec["parent_protocol"]["canonical_sha256"]:
        raise ValueError("Protocol v1 đã khóa bị thay đổi")
    if any(parent[key] != value for key, value in spec["inherited_sections"].items()):
        raise ValueError("Hợp đồng kế thừa R2 khác v1")
    return spec


def _returns(values: list[float]) -> np.ndarray:
    """Đơn vị tỷ lệ, không phải phần trăm; lỗi số học không thành missing/CASH."""
    if type(values) is not list or any(type(v) not in (int, float) or not math.isfinite(v) or v <= -1 for v in values):
        raise ValueError("Payoff phải là danh sách return tỷ lệ hữu hạn lớn hơn -1")
    return np.asarray(values, dtype=float)


def _distribution(mean: float, kappa: float, alpha: float, beta: float) -> dict[str, Any]:
    """Tách rõ scale của mean và predictive; SciPy dùng scale, không variance."""
    if not all(math.isfinite(v) for v in (mean, kappa, alpha, beta)) or min(kappa, alpha, beta) <= 0:
        raise ValueError("Tham số NIG vượt miền số hữu hạn")
    mean_scale = math.sqrt(beta / (alpha * kappa))
    predictive_scale = math.sqrt(beta * (kappa + 1) / (alpha * kappa))
    df = float(2 * alpha)
    intervals = []
    for level, scale in ((.95, mean_scale), (.90, predictive_scale)):
        lower, upper = (float(v) for v in t.ppf([(1-level)/2, (1+level)/2], df, loc=mean, scale=scale))
        if not all(math.isfinite(v) for v in (lower, upper, scale)) or scale <= 0 or lower > upper:
            raise ValueError("Khoảng NIG/Student-t không hữu hạn hợp lệ")
        intervals.append({"level": level, "lower": lower, "upper": upper, "width": float(upper-lower)})
    return {"mean": float(mean), "kappa": float(kappa), "alpha": float(alpha), "beta": float(beta),
            "df": df, "mean_scale": float(mean_scale), "predictive_scale": float(predictive_scale),
            "mean_credible_interval": intervals[0], "predictive_interval": intervals[1]}


def estimate_payoff(conditional: list[float], background: list[float], *, stats_ready: bool) -> dict[str, Any]:
    """Một NIG duy nhất: prior EB từ B rời C; raw không đồng nghĩa ready/visible."""
    if type(stats_ready) is not bool:
        raise ValueError("Readiness stats phải là bool gốc")
    c, b = _returns(conditional), _returns(background)
    n_c, n_b = int(c.size), int(b.size)
    reasons = ([] if n_b >= 20 else ["LOW_BACKGROUND"]) + ([] if n_c >= 5 else ["LOW_CONDITIONAL_SUPPORT"])
    if not stats_ready:
        reasons.append("V1_STATS_NOT_READY")
    prior = updated = None
    if n_b >= 2:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            try:
                m0, beta0 = float(b.mean()), max(float(b.var(ddof=1)), 1e-6)
                prior = _distribution(m0, 4., 2., beta0)
                if n_c:
                    average = float(c.mean())
                    kappa, alpha = float(4+n_c), float(2+n_c/2)
                    beta_n = float(beta0 + np.sum((c-average)**2)/2 + 4*n_c*(average-m0)**2/(2*kappa))
                    updated = _distribution((4*m0+n_c*average)/kappa, kappa, alpha, beta_n)
            except (FloatingPointError, OverflowError, ZeroDivisionError) as error:
                raise ValueError("Payoff NIG vượt miền số học") from error
    if prior is None or updated is None:
        reasons.append("MISSING_PAYOFF_POSTERIOR")
    result = {"payoff_version": VERSION, "return_unit": "ratio", "nC": n_c, "nB": n_b,
              "prior": prior, "posterior": updated, "gate": {"ready": not reasons, "reason_codes": reasons}}
    return result


class PayoffEvidence:
    """Nhận metadata riêng; không copy hoặc mở outcome ngoài pool PIT của query."""

    def __init__(self, metadata: list[dict[str, Any]], records: Mapping[str, dict[str, Any]]) -> None:
        if (type(metadata) is not list or not isinstance(records, Mapping)
                or any(type(row) is not dict or not set(FIELDS).issubset(row) for row in metadata)):
            raise ValueError("Schema metadata/memory payoff không hợp lệ")
        for row in metadata:
            reject_decision(row["agent_signals"])
        self.metadata = [{key: deepcopy(row[key]) for key in FIELDS} for row in metadata]
        ids = [row["episode_id"] for row in self.metadata]
        cycles = [(row["symbol"], row["as_of_date"]) for row in self.metadata]
        if len(ids) != len(set(ids)) or len(cycles) != len(set(cycles)) or set(ids) != set(records):
            raise ValueError("Memory payoff trùng ID/cycle hoặc thiếu record")
        self.records = records

    def evidence(self, *, symbol: str, as_of_date: str, current_regime: str,
                 current_signals: dict[str, str]) -> dict[str, Any]:
        """Không nhận target; C/B1/B2 được chia từ metadata trước đọc return."""
        query = dict(symbol=symbol, as_of_date=as_of_date, current_regime=current_regime, current_signals=current_signals)
        reject_decision(current_signals)
        groups = partition_records(self.metadata, **query)
        metadata = {row["episode_id"]: row for row in self.metadata}
        returns, wins = {}, {}
        for group in ("C", "B1", "B2"):
            values = []
            for identifier in groups[group]:
                if (identifier not in metadata or metadata[identifier]["symbol"] != symbol
                        or not metadata[identifier]["as_of_date"] < metadata[identifier]["exit_date"] < as_of_date):
                    raise ValueError("Membership payoff khai PIT chứa future/self hoặc khác mã")
                row = self.records[identifier]
                if (not isinstance(row, dict) or not {*FIELDS, "outcome"}.issubset(row)
                        or any(row[key] != metadata[identifier][key] for key in FIELDS)
                        or row["symbol"] != symbol or not row["as_of_date"] < row["exit_date"] < as_of_date):
                    raise ValueError("Pool payoff khai PIT chứa future/self hoặc record khác metadata")
                if type(row["outcome"]) is not dict or "net_return_pct" not in row["outcome"]:
                    raise ValueError("Payoff thiếu schema nhãn kinh tế")
                value = row["outcome"]["net_return_pct"]
                if type(value) not in (int, float) or not math.isfinite(value):
                    raise ValueError("Nhãn payoff không phải số hữu hạn gốc")
                values.append(float(value/100))
            _returns(values)
            returns[group], wins[group] = values, int(sum(v > 0 for v in values))
        counts = {"nC": len(returns["C"]), "sC": wins["C"], "n1": len(returns["B1"]),
                  "s1": wins["B1"], "n2": len(returns["B2"]), "s2": wins["B2"]}
        probability = posterior(**counts, lambda_value=8)
        interval = probability["credible_interval"]
        gate = stats_gate("hierarchical_pool", population=counts["nC"]+counts["n1"], nC=counts["nC"],
                          background=counts["n1"]+counts["n2"], width=None if interval is None else interval["width"])
        prediction = estimate_payoff(returns["C"], returns["B1"]+returns["B2"], stats_ready=gate["ready"])
        value = {"query": deepcopy(query), "groups": {key: groups[key] for key in ("C", "B1", "B2")},
                 "counts": counts, "v1_probability": probability["posterior_mean"], "v1_stats_gate": gate,
                 "prediction": prediction}
        value["evidence_sha256"] = digest(value)
        return value


def point_metrics(prediction: dict[str, Any], target: float) -> dict[str, float | bool] | None:
    """Chấm target sau tạo evidence; cùng một row cho NIG, zero, m0 và density prior."""
    _returns([target])
    if not prediction["gate"]["ready"]:
        return None
    prior, fitted = prediction["prior"], prediction["posterior"]
    interval = fitted["predictive_interval"]
    values = {"absolute_error_nig": float(abs(target-fitted["mean"])), "absolute_error_zero": float(abs(target)),
              "absolute_error_m0": float(abs(target-prior["mean"])),
              "nll_nig": float(-t.logpdf(target, fitted["df"], loc=fitted["mean"], scale=fitted["predictive_scale"])),
              "nll_prior": float(-t.logpdf(target, prior["df"], loc=prior["mean"], scale=prior["predictive_scale"])),
              "predictive_covered": bool(interval["lower"] <= target <= interval["upper"]),
              "predictive_width": float(interval["width"])}
    if any(not math.isfinite(v) for v in values.values()):
        raise ValueError("Metric payoff không hữu hạn; không được bỏ row")
    return values


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Giữ mẫu số planned/common/excluded; nhóm trống là null, không điền zero."""
    usable = [row for row in rows if row["metrics"] is not None]
    summary = {"planned": len(rows), "common_count": len(usable), "excluded_count": len(rows)-len(usable)}
    summary["metrics"] = ({key: float(np.mean([row["metrics"][key] for row in usable])) for key in usable[0]["metrics"]}
                          if usable else None)
    return summary


def evaluate_gate(panels: dict[str, Any]) -> dict[str, Any]:
    """Rule cố định, so sánh precision gốc; thiếu một ô fold/mã là inconclusive."""
    symbols = {"FPT", "MWG", "VCB", "VNM"}
    cells = {f"{fold}/{symbol}" for fold in ("train_2021", "train_2022") for symbol in symbols}
    if set(panels["by_symbol"]) != symbols or set(panels["by_fold_symbol"]) != cells:
        raise ValueError("Gate payoff phải giữ đủ bốn mã và tám ô fold/mã")
    for panel in (panels["overall"], *panels["by_symbol"].values(), *panels["by_fold_symbol"].values()):
        if (type(panel["common_count"]) is not int or not 0 <= panel["common_count"] <= panel["planned"]
                or panel["common_count"] and (panel["metrics"] is None or any(
                    type(v) not in (int, float) or not math.isfinite(v) for v in panel["metrics"].values()))):
            raise ValueError("Support/metric gate payoff không hữu hạn hợp lệ")
    if not panels["overall"]["common_count"] or any(not v["common_count"] for v in panels["by_fold_symbol"].values()):
        return {"status": "INCONCLUSIVE", "checks": {"eight_nonempty_fold_symbol_cells": False},
                "failed_checks": ["eight_nonempty_fold_symbol_cells"], "development_allowed": False}
    metrics = panels["overall"]["metrics"]
    checks = {"mae_le_zero": metrics["absolute_error_nig"] <= metrics["absolute_error_zero"],
              "mae_le_m0": metrics["absolute_error_nig"] <= metrics["absolute_error_m0"],
              "strict_mae_improvement": metrics["absolute_error_nig"] < metrics["absolute_error_zero"]
              or metrics["absolute_error_nig"] < metrics["absolute_error_m0"],
              "symbol_mae_increase_le_0_001": all(v["metrics"]["absolute_error_nig"]-v["metrics"]["absolute_error_m0"] <= .001
                                                  for v in panels["by_symbol"].values()),
              "nll_le_prior": metrics["nll_nig"] <= metrics["nll_prior"],
              "predictive_coverage_ge_0_85": metrics["predictive_covered"] >= .85}
    passed = all(checks.values())
    return {"status": "PASS" if passed else "FAIL", "checks": checks, "failed_checks": [k for k,v in checks.items() if not v],
            "development_allowed": passed}
