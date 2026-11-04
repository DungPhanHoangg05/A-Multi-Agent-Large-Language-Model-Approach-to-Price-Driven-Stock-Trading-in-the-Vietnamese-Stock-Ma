"""Oracle cho paired BA, sign flip, bootstrap, Holm và undefined support T13."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.revision_numeric_statistics import classification, contrast_matrix, describe, holm, paired_inference


def family() -> tuple[list[str], list[str]]:
    """Tên strategies/contrasts khớp thiết kế nhưng dữ liệu kiểm là tổng hợp."""
    return (["fixed_custom5", "dynamic_train_top5", "dynamic_train_top5_no_flip"] + [f"random_seed_{i:02d}" for i in range(20)],
            ["dynamic_vs_fixed", "dynamic_vs_random_mean", "dynamic_vs_no_flip"] + [f"dynamic_vs_random_seed_{i:02d}" for i in range(20)])


class NumericStatisticsTests(unittest.TestCase):
    """Expected values có closed-form, không chép lại algorithm đang kiểm."""

    def test_metrics_missing_class_and_constant_prediction_keep_null(self) -> None:
        result = classification([0, 0], [0, 0])
        self.assertEqual(result["accuracy"], 1)
        self.assertIsNone(result["balanced_accuracy"])
        self.assertIsNone(result["mcc"])
        self.assertEqual(result["per_class"]["UP"]["support"], 0)
        with self.assertRaises(ValueError): classification([0, .2], [0, 1])

    def test_dispersion_counts_undefined_and_sample_sd(self) -> None:
        result = describe([1., 3., None])
        self.assertEqual((result["n_planned"], result["n_defined"], result["n_undefined"]), (3, 2, 1))
        self.assertEqual(result["mean"], 2.)
        self.assertAlmostEqual(result["sd"], np.sqrt(2))
        self.assertIsNone(describe([None])["mean"])
        self.assertIsNone(describe([1.])["sd"])

    def test_holm_closed_form_preserves_full_family_with_undefined(self) -> None:
        np.testing.assert_allclose(holm([.01, .04, .03]), [.03, .06, .06])
        result = holm([.01, None, .03])
        self.assertEqual(result[0], .03); self.assertIsNone(result[1]); self.assertEqual(result[2], .06)
        with self.assertRaises(ValueError): holm([1.01])

    def test_six_balanced_blocks_have_exact_p_and_constant_bootstrap_delta(self) -> None:
        strategies, contrasts = family(); truth = np.tile([0, 1], 6)
        predicted = np.zeros((12, 23), dtype=int); predicted[:, 1] = truth; predicted[:, 2] = 1 - truth
        result, arrays = paired_inference(truth, predicted, [f"b{i // 2}" for i in range(12)], strategies, contrasts, draws=200)
        first = result["contrasts"][0]
        self.assertAlmostEqual(first["balanced_accuracy_difference"], .5)
        self.assertEqual(first["p_exact_two_sided"], 2 / 64)
        self.assertEqual(first["p_holm_family_23"], 23 * 2 / 64)
        np.testing.assert_allclose(first["bootstrap_percentile_95"], [.5, .5])
        self.assertFalse(first["reject_holm_0_05"])
        self.assertEqual(arrays["bootstrap_differences"].shape, (200, 23))
        np.testing.assert_array_equal(np.abs(arrays["sign_assignments"]), 1)

    def test_random_mean_is_mean_of_trial_scores_and_all_seeds_stay_present(self) -> None:
        strategies, contrasts = family(); truth = np.tile([0, 1], 6)
        predicted = np.zeros((12, 23), dtype=int); predicted[:, 1] = truth
        for seed in range(20): predicted[:, 3 + seed] = truth if seed < 7 else 1 - truth
        correct = (predicted == truth[:, None]).astype(float)
        delta = contrast_matrix(correct, strategies, contrasts)
        self.assertTrue(np.allclose(delta[:, 1], .65))
        result, _ = paired_inference(truth, predicted, [f"b{i // 2}" for i in range(12)], strategies, contrasts, draws=100)
        self.assertAlmostEqual(result["contrasts"][1]["balanced_accuracy_difference"], .65)
        self.assertEqual(len(result["contrasts"]), 23)

    def test_bootstrap_reports_missing_classes_and_shared_draws_are_reproducible(self) -> None:
        strategies, contrasts = family(); truth = np.array([1, 0, 0, 0, 0, 0])
        predicted = np.zeros((6, 23), dtype=int); predicted[:, 1] = truth
        a, arrays_a = paired_inference(truth, predicted, [f"b{i}" for i in range(6)], strategies, contrasts, draws=300, seed=0)
        b, arrays_b = paired_inference(truth, predicted, [f"b{i}" for i in range(6)], strategies, contrasts, draws=300, seed=0)
        self.assertEqual(a, b)
        np.testing.assert_array_equal(arrays_a["bootstrap_indices"], arrays_b["bootstrap_indices"])
        self.assertGreater(a["contrasts"][0]["bootstrap_undefined"], 0)
        self.assertEqual(a["contrasts"][0]["bootstrap_defined"] + a["contrasts"][0]["bootstrap_undefined"], 300)

    def test_globally_undefined_ba_has_no_p_rejection_or_interval(self) -> None:
        strategies, contrasts = family()
        result, _ = paired_inference(np.zeros(6), np.zeros((6, 23)), [f"b{i}" for i in range(6)], strategies, contrasts, draws=50)
        for row in result["contrasts"]:
            self.assertIsNone(row["balanced_accuracy_difference"])
            self.assertIsNone(row["p_holm_family_23"])
            self.assertIsNone(row["reject_holm_0_05"])
            self.assertEqual(row["bootstrap_percentile_95"], [None, None])

    def test_wrong_support_family_block_or_nonbinary_truth_fails(self) -> None:
        strategies, contrasts = family()
        with self.assertRaises(ValueError): paired_inference([.2] * 6, np.zeros((6, 23)), list("ABCDEF"), strategies, contrasts)
        with self.assertRaises(ValueError): paired_inference([0, 1], np.zeros((2, 23)), ["one", "one"], strategies, contrasts)
        with self.assertRaises(ValueError): contrast_matrix(np.ones((2, 23)), strategies, contrasts[:-1])


if __name__ == "__main__":
    unittest.main()
