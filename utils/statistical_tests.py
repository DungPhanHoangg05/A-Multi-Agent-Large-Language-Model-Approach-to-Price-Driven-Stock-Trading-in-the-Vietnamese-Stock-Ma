"""Các kiểm định thống kê dùng cho backtest cặp Full và No-Alpha."""

from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

import numpy as np
from scipy.stats import binomtest, chi2, t as student_t, wilcoxon


_DIRECTION_MAP = {
    "UP": "UP",
    "LONG": "UP",
    "DOWN": "DOWN",
    "SHORT": "DOWN",
}


def _normalize_direction(value: object) -> str:
    """Chuẩn hóa nhãn giao dịch và nhãn giá về cùng không gian UP/DOWN."""

    return _DIRECTION_MAP.get(str(value).strip().upper(), "UNKNOWN")


def _validate_equal_lengths(*values: Sequence[object]) -> None:
    lengths = {len(value) for value in values}
    if len(lengths) > 1:
        raise ValueError("Các chuỗi actual/prediction phải có cùng số quan sát.")


def calculate_mcnemar_test(
    y_true: Sequence[object],
    y_pred_full: Sequence[object],
    y_pred_no_alpha: Sequence[object],
) -> Dict[str, float]:
    """So sánh độ chính xác cặp bằng McNemar, exact khi dưới 25 bất đồng."""

    _validate_equal_lengths(y_true, y_pred_full, y_pred_no_alpha)
    actual = np.asarray([_normalize_direction(value) for value in y_true])
    full = np.asarray([_normalize_direction(value) for value in y_pred_full])
    no_alpha = np.asarray(
        [_normalize_direction(value) for value in y_pred_no_alpha]
    )

    full_correct = full == actual
    no_alpha_correct = no_alpha == actual
    full_only = int(np.sum(full_correct & ~no_alpha_correct))
    no_alpha_only = int(np.sum(~full_correct & no_alpha_correct))
    n_discordant = full_only + no_alpha_only
    use_exact = n_discordant < 25

    if n_discordant == 0:
        statistic = 0.0
        p_value = 1.0
    elif use_exact:
        statistic = float(min(full_only, no_alpha_only))
        p_value = float(
            binomtest(
                min(full_only, no_alpha_only),
                n_discordant,
                p=0.5,
                alternative="two-sided",
            ).pvalue
        )
    else:
        statistic = (abs(full_only - no_alpha_only) - 1.0) ** 2 / n_discordant
        p_value = float(chi2.sf(statistic, df=1))

    return {
        "statistic": float(statistic),
        "p_value": p_value,
        "n_discordant": n_discordant,
        "exact": use_exact,
    }


def _moving_block_bootstrap_means(
    values: np.ndarray,
    block_size: int,
    n_iterations: int,
    rng: np.random.Generator,
) -> np.ndarray:
    if block_size < 1:
        raise ValueError("block_size phải lớn hơn hoặc bằng 1.")
    if n_iterations < 1:
        raise ValueError("n_iterations phải lớn hơn hoặc bằng 1.")

    n_samples = len(values)
    if n_samples == 0:
        return np.zeros(n_iterations, dtype=float)

    effective_block_size = min(block_size, n_samples)
    n_blocks = int(np.ceil(n_samples / effective_block_size))
    max_start = n_samples - effective_block_size
    bootstrap_means = np.empty(n_iterations, dtype=float)

    for iteration in range(n_iterations):
        starts = rng.integers(0, max_start + 1, size=n_blocks)
        sample = np.concatenate(
            [values[start : start + effective_block_size] for start in starts]
        )[:n_samples]
        bootstrap_means[iteration] = float(np.mean(sample))

    return bootstrap_means


def block_bootstrap_accuracy(
    y_true: Sequence[object],
    y_pred: Sequence[object],
    block_size: int = 5,
    n_iterations: int = 1000,
    alpha: float = 0.05,
    random_seed: int = 42,
) -> Tuple[float, float, float]:
    """Ước lượng khoảng tin cậy accuracy bằng moving-block bootstrap."""

    _validate_equal_lengths(y_true, y_pred)
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha phải nằm trong khoảng (0, 1).")
    if len(y_true) == 0:
        return 0.0, 0.0, 0.0

    actual = np.asarray([_normalize_direction(value) for value in y_true])
    prediction = np.asarray([_normalize_direction(value) for value in y_pred])
    correct = (actual == prediction).astype(float)
    bootstrapped = _moving_block_bootstrap_means(
        correct,
        block_size,
        n_iterations,
        np.random.default_rng(random_seed),
    )
    lower, upper = np.quantile(bootstrapped, [alpha / 2.0, 1.0 - alpha / 2.0])
    return float(np.mean(correct)), float(lower), float(upper)


def paired_wilcoxon_test(lifts_per_symbol: List[float]) -> Dict[str, float]:
    """Kiểm định signed-rank hai phía cho Alpha Lift của nhiều mã cổ phiếu."""

    values = np.asarray(lifts_per_symbol, dtype=float)
    values = values[np.isfinite(values)]
    n_symbols = int(values.size)

    if n_symbols == 0 or np.allclose(values, 0.0):
        statistic, p_value = 0.0, 1.0
    else:
        result = wilcoxon(
            values,
            zero_method="wilcox",
            correction=False,
            alternative="two-sided",
            method="auto",
        )
        statistic, p_value = float(result.statistic), float(result.pvalue)

    return {
        "statistic": statistic,
        "p_value": p_value,
        "n_symbols": n_symbols,
        "median_lift": float(np.median(values)) if n_symbols else 0.0,
        "is_significant_05": bool(p_value < 0.05),
    }


def newey_west_mean_test(
    values: Sequence[float],
    null_mean: float = 0.0,
    max_lag: int | None = None,
) -> Dict[str, float]:
    """Kiểm định trung bình với sai số chuẩn HAC Newey-West và trọng số Bartlett."""

    observations = np.asarray(values, dtype=float)
    observations = observations[np.isfinite(observations)]
    n_samples = int(observations.size)
    if n_samples == 0:
        return {
            "statistic": 0.0,
            "p_value": 1.0,
            "standard_error": 0.0,
            "n_samples": 0,
            "max_lag": 0,
        }

    if max_lag is None:
        max_lag = int(np.floor(4.0 * (n_samples / 100.0) ** (2.0 / 9.0)))
    max_lag = max(0, min(int(max_lag), n_samples - 1))

    centered = observations - float(np.mean(observations))
    long_run_variance = float(np.dot(centered, centered) / n_samples)
    for lag in range(1, max_lag + 1):
        covariance = float(np.dot(centered[lag:], centered[:-lag]) / n_samples)
        bartlett_weight = 1.0 - lag / (max_lag + 1.0)
        long_run_variance += 2.0 * bartlett_weight * covariance

    standard_error = float(np.sqrt(max(long_run_variance, 0.0) / n_samples))
    if standard_error <= np.finfo(float).eps or n_samples < 2:
        statistic, p_value = 0.0, 1.0
    else:
        statistic = (float(np.mean(observations)) - null_mean) / standard_error
        p_value = float(2.0 * student_t.sf(abs(statistic), df=n_samples - 1))

    return {
        "statistic": float(statistic),
        "p_value": p_value,
        "standard_error": standard_error,
        "n_samples": n_samples,
        "max_lag": max_lag,
    }


def calculate_metrics_with_significance(
    actuals: List[str],
    preds_full: List[str],
    preds_no_alpha: List[str],
    block_size: int = 5,
    n_bootstrap: int = 1000,
    random_seed: int = 42,
) -> Dict[str, object]:
    """Tính McNemar, Newey-West và CI bootstrap trên common support."""

    _validate_equal_lengths(actuals, preds_full, preds_no_alpha)
    common_support = []
    for actual, full, no_alpha in zip(actuals, preds_full, preds_no_alpha):
        normalized = (
            _normalize_direction(actual),
            _normalize_direction(full),
            _normalize_direction(no_alpha),
        )
        if "UNKNOWN" not in normalized:
            common_support.append(normalized)

    if not common_support:
        return {
            "n_samples": 0,
            "mcnemar_statistic": 0.0,
            "mcnemar_p_value": 1.0,
            "mcnemar_exact": True,
            "is_significant_05": False,
            "full_acc_ci": [0.0, 0.0],
            "no_alpha_acc_ci": [0.0, 0.0],
            "alpha_lift": 0.0,
            "alpha_lift_ci_95": [0.0, 0.0],
            "delta_acc_ci": [0.0, 0.0],
            "newey_west_statistic": 0.0,
            "newey_west_p_value": 1.0,
        }

    y_true, y_pred_full, y_pred_no_alpha = map(np.asarray, zip(*common_support))
    mcnemar_result = calculate_mcnemar_test(y_true, y_pred_full, y_pred_no_alpha)
    _, full_lower, full_upper = block_bootstrap_accuracy(
        y_true,
        y_pred_full,
        block_size,
        n_bootstrap,
        random_seed=random_seed,
    )
    _, no_alpha_lower, no_alpha_upper = block_bootstrap_accuracy(
        y_true,
        y_pred_no_alpha,
        block_size,
        n_bootstrap,
        random_seed=random_seed + 1,
    )

    full_correct = (y_true == y_pred_full).astype(float)
    no_alpha_correct = (y_true == y_pred_no_alpha).astype(float)
    paired_lift = full_correct - no_alpha_correct
    bootstrap_lifts = _moving_block_bootstrap_means(
        paired_lift,
        block_size,
        n_bootstrap,
        np.random.default_rng(random_seed + 2),
    )
    lift_lower, lift_upper = np.quantile(bootstrap_lifts, [0.025, 0.975])
    lift_ci = [float(lift_lower * 100.0), float(lift_upper * 100.0)]
    newey_west = newey_west_mean_test(paired_lift)

    return {
        "n_samples": len(common_support),
        "mcnemar_statistic": mcnemar_result["statistic"],
        "mcnemar_p_value": mcnemar_result["p_value"],
        "mcnemar_exact": mcnemar_result["exact"],
        "is_significant_05": bool(mcnemar_result["p_value"] < 0.05),
        "full_acc_ci": [float(full_lower * 100.0), float(full_upper * 100.0)],
        "no_alpha_acc_ci": [
            float(no_alpha_lower * 100.0),
            float(no_alpha_upper * 100.0),
        ],
        "alpha_lift": float(np.mean(paired_lift) * 100.0),
        "alpha_lift_ci_95": lift_ci,
        # Giữ khóa cũ để core/run_robustness.py tiếp tục tương thích.
        "delta_acc_ci": lift_ci,
        "newey_west_statistic": newey_west["statistic"],
        "newey_west_p_value": newey_west["p_value"],
    }
