"""Thống kê sensitivity theo panel đã khóa, không thay helper hoặc kết quả legacy."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.stats import binomtest, norm, t as student_t

from core.revision_r3_repeats import array_metrics
from utils.statistical_tests import newey_west_mean_test

METRICS = ("balanced_accuracy", "accuracy")


def hac_summary(values: list[float] | np.ndarray, lag: int | None) -> dict[str, Any]:
    """Tái dùng Bartlett HAC gốc, giữ ngày và báo NA khi SE suy biến."""
    series = np.asarray(values, dtype=float)
    if series.ndim != 1 or not np.all(np.isfinite(series)):
        raise ValueError("Chuỗi HAC phải một chiều, hữu hạn; không bỏ ngày thiếu")
    result = newey_west_mean_test(series, max_lag=lag)
    defined = len(series) >= 2 and result["standard_error"] > np.finfo(float).eps
    mean = float(series.mean()) if len(series) else None
    half_width = (float(student_t.ppf(.975, len(series) - 1)) * result["standard_error"]
                  if defined else None)
    return {"n_dates_or_cutoffs": len(series), "mean": mean, "lag": int(result["max_lag"]),
            "standard_error": float(result["standard_error"]) if len(series) >= 2 else None,
            "statistic": float(result["statistic"]) if defined else None,
            "p_value": float(result["p_value"]) if defined else None,
            "interval_95": [mean - half_width, mean + half_width] if defined else None,
            "reference_df": len(series) - 1 if len(series) >= 2 else None,
            "status": "descriptive_hac" if defined else "undefined_insufficient_or_zero_variance",
            "reference": "Bartlett covariance denominator n; t(n-1); no finite-sample calibration"}


def discordance(actual: np.ndarray, full: np.ndarray, base: np.ndarray) -> dict[str, Any]:
    """Đếm đủ hai hướng discordance và exact diagnostic với independence giả định."""
    if actual.shape != full.shape or actual.shape != base.shape or actual.ndim != 1:
        raise ValueError("Ba vector phải cùng support một chiều")
    if not len(actual):
        raise ValueError("Không tính exact diagnostic trên support rỗng")
    full_correct, base_correct = full == actual, base == actual
    b = int(np.count_nonzero(full_correct & ~base_correct))
    c = int(np.count_nonzero(~full_correct & base_correct))
    return {"n": len(actual), "full_only_correct": b, "base_only_correct": c,
            "both_correct": int(np.count_nonzero(full_correct & base_correct)),
            "both_wrong": int(np.count_nonzero(~full_correct & ~base_correct)),
            "n_discordant": b + c, "accuracy_difference": float((b - c) / len(actual)),
            "exact_p_value": float(binomtest(b, b + c, .5).pvalue) if b + c else 1.0,
            "assumption": "conditional independent discordant pairs; diagnostic only, not a dependence-adjusted test"}


def circular_weights(n_blocks: int, length: int, draws: int, seed: int) -> np.ndarray:
    """Lấy circular blocks, giữ tổng trọng số đúng số study blocks gốc."""
    if not 1 <= length <= n_blocks or draws < 1:
        raise ValueError("Độ dài/số lần resample không hợp lệ")
    starts = np.random.default_rng(seed).integers(0, n_blocks, (draws, math.ceil(n_blocks / length)))
    indices = ((starts[..., None] + np.arange(length)) % n_blocks).reshape(draws, -1)[:, :n_blocks]
    return np.eye(n_blocks, dtype=int)[indices].sum(axis=1)


def score_samples(counts: np.ndarray, weights: np.ndarray) -> dict[str, np.ndarray]:
    """Tái dùng metric vector hóa R3, cùng draws cho mọi variants và toàn cross-section."""
    if counts.shape[-1] != 4 or counts.shape[-2] != weights.shape[-1] or np.any(counts < 0):
        raise ValueError("Tensor confusion không khớp weights")
    if not np.all(np.isfinite(counts)) or not np.all(weights.sum(axis=1) == counts.shape[-2]):
        raise ValueError("Counts/weights không hợp lệ")
    total = counts.sum(axis=-1)
    up = counts[..., 0] + counts[..., 1]
    if not np.all(total == total[..., :1, :]) or not np.all(up == up[..., :1, :]):
        raise ValueError("Các variants khác support hoặc truth")
    return array_metrics(np.einsum("db,...vbc->...vdc", weights, counts))


def percentile_summary(values: np.ndarray) -> dict[str, Any]:
    """Không biến draw mất class thành zero hoặc giấu mẫu số có điều kiện."""
    finite = np.isfinite(values)
    return {"n_draws": int(values.size), "n_defined": int(finite.sum()),
            "n_undefined": int((~finite).sum()),
            "percentile_95": np.quantile(values[finite], [.025, .975]).tolist() if np.any(finite) else None,
            "scope": "descriptive finite-draw percentiles; no coverage/significance guarantee"}


def _ar(rng: np.random.Generator, panels: int, dates: int, width: int, phi: float) -> np.ndarray:
    """Sinh AR stationary bằng vector trên panels/features, chỉ lặp trục thời gian."""
    innovations = rng.standard_normal((panels, dates, width))
    for time in range(1, dates):
        innovations[:, time] = phi * innovations[:, time - 1] + np.sqrt(1 - phi ** 2) * innovations[:, time]
    return innovations


def simulate_null_counts(panels: int, phi: float, share: float, seed: int,
                         up_probability: float = .3) -> np.ndarray:
    """Null exchangeable hai arms, AR và common factor, giữ đúng 102-cell mask."""
    if panels < 1 or not 0 <= phi < 1 or not 0 <= share <= 1 or not 0 < up_probability < 1:
        raise ValueError("Tham số mô phỏng null không hợp lệ")
    rng = np.random.default_rng(seed)
    market = _ar(rng, panels, 12, 1, phi)
    arms = _ar(rng, panels, 12, 2, phi)
    idio = _ar(rng, panels, 12, 18, phi).reshape(panels, 12, 2, 9)
    latent = np.sqrt(share / 2) * (market[..., None] + arms[..., None]) + np.sqrt(1 - share) * idio
    correct = latent > 0
    truth_market = _ar(rng, panels, 12, 1, phi)
    truth_idio = _ar(rng, panels, 12, 9, phi)
    truth = (np.sqrt(share) * truth_market + np.sqrt(1 - share) * truth_idio) > norm.ppf(1 - up_probability)
    prediction = np.where(correct, truth[:, :, None, :], ~truth[:, :, None, :])
    mask = np.ones((12, 9), dtype=bool)
    mask[:6, 0] = False
    y = truth[:, :, None, :]
    cells = np.stack((y & prediction, y & ~prediction, ~y & ~prediction, ~y & prediction), axis=-1)
    cells &= mask[None, :, None, :, None]
    # Gom hai selected dates và chín mã trong mỗi historical study block.
    return cells.reshape(panels, 6, 2, 2, 9, 4).sum(axis=(2, 4)).transpose(0, 2, 1, 3)


def null_coverage(counts: np.ndarray, weights: np.ndarray) -> list[dict[str, Any]]:
    """Đánh giá coverage zero theo từng panel, báo Wilson MC CI trên panels độc lập."""
    sampled = score_samples(counts, weights)
    point = array_metrics(counts.sum(axis=-2))
    result = []
    for metric in METRICS:
        delta = sampled[metric][:, 0] - sampled[metric][:, 1]
        finite = np.isfinite(delta)
        valid = finite.any(axis=1)
        limits = np.nanquantile(delta[valid], [.025, .975], axis=1) if np.any(valid) else np.empty((2, 0))
        covered = int(np.count_nonzero((limits[0] <= 0) & (limits[1] >= 0)))
        n = int(valid.sum())
        mc = binomtest(covered, n).proportion_ci(method="wilson") if n else None
        effects = point[metric][:, 0] - point[metric][:, 1]
        point_finite = np.isfinite(effects)
        result.append({"metric": metric, "n_panels": len(counts), "n_defined_panels": n,
                       "n_undefined_panels": int((~valid).sum()), "n_covered_zero": covered,
                       "coverage_given_defined": covered / n if n else None,
                       "zero_exclusion_given_defined": (n - covered) / n if n else None,
                       "monte_carlo_wilson_95": [float(mc.low), float(mc.high)] if mc else None,
                       "n_finite_bootstrap_draws": int(finite.sum()),
                       "n_undefined_bootstrap_draws": int((~finite).sum()),
                       "n_point_defined": int(point_finite.sum()),
                       "mean_observed_effect": float(effects[point_finite].mean()) if np.any(point_finite) else None})
    return result
