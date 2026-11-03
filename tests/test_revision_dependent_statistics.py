"""Hồi quy D2-05 cho pairing, mẫu số, HAC và resampling có phụ thuộc."""

from __future__ import annotations

from copy import deepcopy
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from scipy.stats import binomtest

from core.revision_dependent_statistics import (circular_weights, discordance, hac_summary,
    null_coverage, percentile_summary, score_samples, simulate_null_counts)
from core.revision_r3_repeats import array_metrics
from scripts.analyze_revision_statistics import VARIANTS, cohort, json_text, validate_panel


def panel_fixture() -> list[dict]:
    """Panel 12 ngày với mask sáu BHN cells thiếu, không thay bằng CASH."""
    rows = []
    for day in range(12):
        for symbol in ("BHN", "CMG", "FPT", "HVN", "MBB", "MWG", "VCB", "VJC", "VNM"):
            if symbol == "BHN" and day < 6:
                continue
            for variant in VARIANTS:
                rows.append({"unit_id": f"{symbol}-{day}", "symbol": symbol, "date": f"2026-{day + 1:02}-01",
                             "fold": ("b" if day < 6 else "f") + str(day // 2),
                             "variant": variant, "label_net": "UP" if day % 3 else "DOWN",
                             "prediction": "LONG" if variant == "AS" else "SHORT", "market_input_hash": f"hash-{day}-{symbol}"})
    return rows


class DependentStatisticsTests(unittest.TestCase):
    """Các oracle độc lập kiểm công thức và invariance thay vì chỉ mirror code."""

    def test_hac_matches_explicit_bartlett_covariance(self) -> None:
        x = np.array([1., -1., 0., 1., 0., -1.])
        centered = x - x.mean()
        covariance = np.outer(centered, centered)
        lrv = np.trace(covariance) / len(x)
        for lag in (1, 2):
            lrv += 2 * (1 - lag / 3) * np.diag(covariance, k=lag).sum() / len(x)
        result = hac_summary(x, 2)
        self.assertAlmostEqual(result["standard_error"], math.sqrt(lrv / len(x)))
        self.assertAlmostEqual(result["statistic"], x.mean() / math.sqrt(lrv / len(x)))
        self.assertEqual(result["reference_df"], 5)

    def test_hac_degenerate_missing_and_singleton_are_not_p_one(self) -> None:
        for values in ([], [1], [0, 0, 0], [1, 1, 1]):
            result = hac_summary(values, 1)
            self.assertIsNone(result["statistic"])
            self.assertIsNone(result["p_value"])
            self.assertIsNone(result["interval_95"])
            json_text(result)
        with self.assertRaises(ValueError):
            hac_summary([0, float("nan"), 1], 1)

    def test_discordance_counts_both_directions_and_exact(self) -> None:
        y = np.array([True] * 6)
        full = np.array([1, 1, 1, 1, 0, 0], dtype=bool)
        base = np.array([1, 0, 0, 0, 1, 0], dtype=bool)
        result = discordance(y, full, base)
        self.assertEqual((result["full_only_correct"], result["base_only_correct"]), (3, 1))
        self.assertEqual(result["both_correct"] + result["both_wrong"] + result["n_discordant"], 6)
        self.assertAlmostEqual(result["exact_p_value"], binomtest(3, 4, .5).pvalue)
        self.assertEqual(discordance(y, y, y)["exact_p_value"], 1)

    def test_circular_geometry_and_full_length_degeneracy(self) -> None:
        weights = circular_weights(6, 2, 500, 5)
        np.testing.assert_array_equal(weights.sum(axis=1), 6)
        np.testing.assert_array_equal(weights, circular_weights(6, 2, 500, 5))
        np.testing.assert_array_equal(circular_weights(3, 3, 40, 1), np.ones((40, 3)))
        for length in (0, 7):
            with self.assertRaises(ValueError):
                circular_weights(6, length, 20, 1)

    def test_clone_symbols_does_not_shrink_bootstrap_interval(self) -> None:
        counts = simulate_null_counts(1, .6, .7, 3)[0]
        weights = circular_weights(6, 2, 200, 4)
        original = score_samples(counts, weights)
        cloned = score_samples(counts * 9, weights)
        for metric in ("accuracy", "balanced_accuracy"):
            np.testing.assert_allclose(original[metric], cloned[metric], equal_nan=True)

    def test_shared_draw_preserves_zero_contrast_and_variant_support(self) -> None:
        counts = simulate_null_counts(1, .3, .2, 5)[0]
        weights = circular_weights(6, 1, 200, 4)
        twin = np.stack([counts[0], counts[0]])
        scores = score_samples(twin, weights)
        np.testing.assert_allclose(scores["accuracy"][0] - scores["accuracy"][1], 0)
        counts[1, 0, 0] += 1
        with self.assertRaises(ValueError):
            score_samples(counts, weights)

    def test_class_loss_is_undefined_and_denominator_visible(self) -> None:
        values = np.array([np.nan, .1, .2, np.nan])
        result = percentile_summary(values)
        self.assertEqual((result["n_defined"], result["n_undefined"]), (2, 2))
        self.assertIsNone(percentile_summary(np.array([np.nan]))["percentile_95"])
        json_text(result)

    def test_panel_pairing_and_mask_are_strict(self) -> None:
        rows = panel_fixture()
        validate_panel(rows)
        self.assertEqual(cohort(rows, "all_102")["counts"].sum(axis=(1, 2)).tolist(), [102] * 9)
        self.assertEqual(len(cohort(rows, "common_eight_96")["units"]), 96)
        self.assertEqual(len(cohort(rows, "recent_nine_54")["units"]), 54)
        for broken in (rows + rows[:1], rows[:-1]):
            with self.assertRaises(ValueError):
                validate_panel(broken)
        changed = deepcopy(rows)
        changed[1]["label_net"] = "UP" if changed[1]["label_net"] == "DOWN" else "DOWN"
        with self.assertRaises(ValueError):
            validate_panel(changed)

    def test_simulation_mask_reproducibility_and_arm_swap(self) -> None:
        counts = simulate_null_counts(50, .6, .7, 6)
        np.testing.assert_array_equal(counts, simulate_null_counts(50, .6, .7, 6))
        np.testing.assert_array_equal(counts.sum(axis=(-2, -1)), 102)
        weights = circular_weights(6, 2, 100, 6)
        original = null_coverage(counts, weights)
        swapped = null_coverage(counts[:, ::-1], weights)
        for a, b in zip(original, swapped):
            self.assertEqual(a["n_covered_zero"], b["n_covered_zero"])
            self.assertEqual(a["n_defined_panels"], b["n_defined_panels"])
            self.assertAlmostEqual(a["mean_observed_effect"], -b["mean_observed_effect"])
            self.assertEqual(a["n_finite_bootstrap_draws"] + a["n_undefined_bootstrap_draws"], 5000)
        json_text(original)

    def test_metric_oracle_agrees_with_direct_counting(self) -> None:
        data = cohort(panel_fixture(), "common_eight_96")
        scores = array_metrics(data["counts"].sum(axis=1))
        y, p = data["truth"], data["predictions"][0]
        expected_ba = ((p[y] == y[y]).mean() + (p[~y] == y[~y]).mean()) / 2
        self.assertAlmostEqual(scores["balanced_accuracy"][0], expected_ba)

    def test_simulation_honors_probability_and_rejects_invalid_contract(self) -> None:
        low = simulate_null_counts(50, .5, .5, 3, .1)
        high = simulate_null_counts(50, .5, .5, 3, .9)
        self.assertLess((low[..., 0] + low[..., 1]).sum(), (high[..., 0] + high[..., 1]).sum())
        with self.assertRaises(ValueError):
            simulate_null_counts(10, .5, .5, 3, 0)


if __name__ == "__main__":
    unittest.main()
