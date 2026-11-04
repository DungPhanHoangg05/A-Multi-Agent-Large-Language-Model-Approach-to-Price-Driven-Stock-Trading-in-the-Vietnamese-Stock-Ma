"""Metrics/paired BA inference T13 theo family và whole-block draws đã khóa ở T12."""

from __future__ import annotations

from itertools import product
from typing import Any

import numpy as np

from core.revision_sentiment_inventory import require
from utils.statistical_tests import binary_classification_metrics


def classification(truth: Any, predictions: Any) -> dict:
    """Bắt buộc binary/common support; giữ null của metric thiếu mẫu số."""
    actual, predicted = np.asarray(truth), np.asarray(predictions)
    require(actual.ndim == predicted.ndim == 1 and actual.shape == predicted.shape and len(actual) > 0, "Sai classification support")
    require(bool(np.isin(actual, [0, 1]).all() and np.isin(predicted, [0, 1]).all()), "Prediction/label ngoài binary contract")
    return binary_classification_metrics(np.where(actual, "UP", "DOWN").tolist(), np.where(predicted, "LONG", "SHORT").tolist())


def describe(values: list[float | None]) -> dict:
    """Không chọn trial đẹp; mean/sample-SD/median/range cùng defined denominator."""
    finite = np.asarray([v for v in values if v is not None and np.isfinite(v)], dtype=float)
    return {"n_planned": len(values), "n_defined": len(finite), "n_undefined": len(values) - len(finite),
            "mean": float(finite.mean()) if len(finite) else None, "sd": float(finite.std(ddof=1)) if len(finite) > 1 else None,
            "median": float(np.median(finite)) if len(finite) else None,
            "min": float(finite.min()) if len(finite) else None, "max": float(finite.max()) if len(finite) else None}


def holm(values: list[float | None]) -> list[float | None]:
    """Giữ family size kể cả undefined; null không biến thành p có ý nghĩa."""
    require(all(v is None or np.isfinite(v) and 0 <= v <= 1 for v in values), "P-value không hợp lệ")
    raw = np.asarray([1. if value is None else value for value in values])
    order = np.argsort(raw, kind="stable")
    adjusted = np.minimum(1., np.maximum.accumulate(raw[order] * (len(raw) - np.arange(len(raw)))))
    output = np.empty(len(raw)); output[order] = adjusted
    return [float(output[i]) if values[i] is not None else None for i in range(len(values))]


def contrast_matrix(correct: np.ndarray, strategies: list[str], contrasts: list[str]) -> np.ndarray:
    """Random-family mean là mean score của 20 trials, không ensemble prediction."""
    require(correct.ndim == 2 and correct.shape[1] == len(strategies) == len(set(strategies)) == 23, "Sai strategy matrix")
    index = {name: position for position, name in enumerate(strategies)}
    random = [index[f"random_seed_{seed:02d}"] for seed in range(20)]
    dynamic = correct[:, index["dynamic_train_top5"]]
    mapping = {"dynamic_vs_fixed": correct[:, index["fixed_custom5"]],
               "dynamic_vs_no_flip": correct[:, index["dynamic_train_top5_no_flip"]],
               "dynamic_vs_random_mean": correct[:, random].mean(axis=1)}
    mapping.update({f"dynamic_vs_random_seed_{seed:02d}": correct[:, index[f"random_seed_{seed:02d}"]] for seed in range(20)})
    require(len(contrasts) == len(set(contrasts)) == 23 and set(contrasts) == set(mapping), "Sai contrast family")
    return np.column_stack([dynamic - mapping[name] for name in contrasts])


def paired_inference(truth: Any, predictions: Any, blocks: list[str], strategies: list[str], contrasts: list[str],
                     draws: int = 10000, seed: int = 0) -> tuple[dict, dict[str, np.ndarray]]:
    """Exact six-block sign flip và paired block bootstrap, giữ cùng draws cho cả 23 contrasts."""
    y, predicted = np.asarray(truth), np.asarray(predictions)
    require(predicted.shape == (len(y), len(strategies)) and len(blocks) == len(y), "Inference không common support")
    require(np.isin(y, [0, 1]).all() and np.isin(predicted, [0, 1]).all(), "Inference labels/predictions sai schema")
    y = y.astype(int)
    order = list(dict.fromkeys(blocks)); require(len(order) == 6, "Phải giữ đủ sáu market blocks")
    membership = np.asarray(blocks)
    delta = contrast_matrix((predicted == y[:, None]).astype(float), strategies, contrasts)
    up = np.asarray([y[membership == block].sum() for block in order], dtype=int)
    total = np.asarray([(membership == block).sum() for block in order], dtype=int); down = total - up
    up_delta = np.vstack([delta[(membership == block) & (y == 1)].sum(axis=0) for block in order])
    down_delta = np.vstack([delta[(membership == block) & (y == 0)].sum(axis=0) for block in order])
    assignments = np.asarray(list(product([-1, 1], repeat=6)), dtype=np.int8)
    rng = np.random.default_rng(seed); indices = rng.integers(0, 6, size=(draws, 6))
    weights = np.eye(6, dtype=int)[indices].sum(axis=1)
    bootstrap_up, bootstrap_down = weights @ up, weights @ down
    valid = (bootstrap_up > 0) & (bootstrap_down > 0)
    samples = np.full((draws, len(contrasts)), np.nan)
    samples[valid] = .5 * ((weights[valid] @ up_delta) / bootstrap_up[valid, None] + (weights[valid] @ down_delta) / bootstrap_down[valid, None])
    defined = bool(up.sum() > 0 and down.sum() > 0)
    block_contributions = .5 * (up_delta / up.sum() + down_delta / down.sum()) if defined else np.full((6, len(contrasts)), np.nan)
    observed = block_contributions.sum(axis=0)
    permutations = assignments @ block_contributions
    raw_p = [float(np.mean(np.abs(permutations[:, i]) >= abs(observed[i]) - 1e-12)) if defined else None for i in range(len(contrasts))]
    adjusted = holm(raw_p)
    rows = []
    for position, name in enumerate(contrasts):
        finite = samples[valid, position]
        ci = np.quantile(finite, [.025, .975]).tolist() if len(finite) else [None, None]
        rows.append({"contrast": name, "balanced_accuracy_difference": float(observed[position]) if defined else None,
                     "p_exact_two_sided": raw_p[position], "p_holm_family_23": adjusted[position],
                     "reject_holm_0_05": bool(adjusted[position] <= .05) if adjusted[position] is not None else None,
                     "bootstrap_percentile_95": ci, "bootstrap_defined": int(valid.sum()), "bootstrap_undefined": int((~valid).sum())})
    report = {"family_size": len(contrasts), "common_units": len(y), "class_support": {"UP": int(up.sum()), "DOWN": int(down.sum())},
              "block_order": order, "block_support": [{"block": block, "n": int(total[i]), "UP": int(up[i]), "DOWN": int(down[i])} for i, block in enumerate(order)],
              "sign_assignments": len(assignments), "bootstrap_draws": draws, "bootstrap_seed": seed, "contrasts": rows,
              "limits": "Sáu blocks có phụ thuộc; exchangeability/symmetry chưa xác nhận. Holm/CI/p-values chỉ diagnostic; không confirmatory hoặc LLM ablation."}
    arrays = {"bootstrap_indices": indices, "bootstrap_differences": samples, "sign_assignments": assignments,
              "permutation_statistics": permutations, "block_contributions": block_contributions, "block_order": np.asarray(order)}
    return report, arrays
