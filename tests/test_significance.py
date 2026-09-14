"""Kiểm thử bộ kiểm định ý nghĩa thống kê tích hợp của backtest."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.backtest_engine import BacktestEngine, TestPoint
from utils.aggregate_benchmarks import DEFAULT_SYMBOLS, aggregate_benchmarks
from utils.statistical_tests import (
    calculate_mcnemar_test,
    calculate_metrics_with_significance,
    newey_west_mean_test,
    paired_wilcoxon_test,
)


def _point(test_id: int, actual: str, full: str, no_alpha: str) -> TestPoint:
    entry_time = datetime(2024, 1, 1) + timedelta(days=(test_id - 1) * 3)
    exit_time = entry_time + timedelta(days=2)
    return TestPoint(
        test_id=test_id,
        window_start="2024-01-01",
        window_end="2024-01-02",
        actual_prev_close=100.0,
        actual_next_close=101.0 if actual == "UP" else 99.0,
        actual_direction=actual,
        actual_pct_change=1.0 if actual == "UP" else -1.0,
        pred_full=full,
        correct_full=(full == "LONG" and actual == "UP")
        or (full == "SHORT" and actual == "DOWN"),
        confidence_full="N/A",
        rr_full="N/A",
        pred_no_alpha=no_alpha,
        correct_no_alpha=(no_alpha == "LONG" and actual == "UP")
        or (no_alpha == "SHORT" and actual == "DOWN"),
        confidence_no_alpha="N/A",
        rr_no_alpha="N/A",
        time_full_sec=0.0,
        time_no_alpha_sec=0.0,
        entry_open=100.0,
        exit_close=101.0 if actual == "UP" else 99.0,
        entry_time=entry_time.isoformat(),
        exit_time=exit_time.isoformat(),
    )


class SignificanceTests(unittest.TestCase):
    def test_mcnemar_uses_exact_binomial_for_small_discordant_count(self):
        actual = ["UP"] * 10
        full = ["LONG"] * 10
        no_alpha = ["SHORT"] * 10

        result = calculate_mcnemar_test(actual, full, no_alpha)

        self.assertTrue(result["exact"])
        self.assertEqual(result["n_discordant"], 10)
        self.assertAlmostEqual(result["p_value"], 0.001953125, places=12)

    def test_metrics_map_long_short_to_up_down_and_are_reproducible(self):
        actual = ["UP", "DOWN"] * 10
        full = ["LONG", "SHORT"] * 10
        no_alpha = ["SHORT", "LONG"] * 10

        first = calculate_metrics_with_significance(
            actual, full, no_alpha, block_size=4, n_bootstrap=250, random_seed=7
        )
        second = calculate_metrics_with_significance(
            actual, full, no_alpha, block_size=4, n_bootstrap=250, random_seed=7
        )

        self.assertEqual(first, second)
        self.assertEqual(first["n_samples"], 20)
        self.assertEqual(first["alpha_lift_ci_95"], [100.0, 100.0])
        self.assertEqual(first["delta_acc_ci"], first["alpha_lift_ci_95"])
        self.assertLess(first["mcnemar_p_value"], 0.05)

    def test_small_sample_returns_complete_safe_schema(self):
        result = calculate_metrics_with_significance(
            ["UP", "DOWN"], ["LONG", "SHORT"], ["LONG", "LONG"], n_bootstrap=50
        )

        self.assertEqual(result["n_samples"], 2)
        self.assertIn("mcnemar_p_value", result)
        self.assertIn("alpha_lift_ci_95", result)
        self.assertEqual(len(result["alpha_lift_ci_95"]), 2)

    def test_paired_wilcoxon_over_nine_positive_lifts(self):
        result = paired_wilcoxon_test([1.0] * 9)

        self.assertEqual(result["n_symbols"], 9)
        self.assertAlmostEqual(result["p_value"], 0.00390625, places=12)
        self.assertTrue(result["is_significant_05"])

    def test_paired_wilcoxon_handles_all_zero_lifts(self):
        result = paired_wilcoxon_test([0.0] * 9)

        self.assertEqual(result["statistic"], 0.0)
        self.assertEqual(result["p_value"], 1.0)
        self.assertFalse(result["is_significant_05"])

    def test_newey_west_test_reports_finite_result(self):
        result = newey_west_mean_test([0.02, 0.01, 0.03, 0.015, 0.025], max_lag=1)

        self.assertEqual(result["n_samples"], 5)
        self.assertEqual(result["max_lag"], 1)
        self.assertGreater(result["standard_error"], 0.0)
        self.assertGreaterEqual(result["p_value"], 0.0)
        self.assertLessEqual(result["p_value"], 1.0)

    def test_backtest_summary_persists_significance_fields(self):
        points = [
            _point(i + 1, "UP" if i % 2 == 0 else "DOWN", "LONG" if i % 2 == 0 else "SHORT", "SHORT" if i % 2 == 0 else "LONG")
            for i in range(20)
        ]
        engine = BacktestEngine({"use_historical_sentiment": False})

        payload = asdict(
            engine._build_summary(
                "FPT", "1 ngày", 20, 45, 3, points, "2024-01-01", "2024-04-01"
            )
        )

        self.assertIn("mcnemar_p_value", payload)
        self.assertIn("is_significant_05", payload)
        self.assertEqual(payload["alpha_lift_ci_95"], [100.0, 100.0])

    def test_aggregate_script_computes_overall_p_value_and_latex(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result_dir = Path(temp_dir)
            for index, symbol in enumerate(DEFAULT_SYMBOLS):
                payload = {
                    "symbol": symbol,
                    "acc_full": 60.0 + index,
                    "acc_no_alpha": 50.0 + index,
                    "alpha_lift": 10.0,
                    "mcnemar_p_value": 0.008 if index == 0 else 0.03,
                    "alpha_lift_ci_95": [2.0, 18.0],
                }
                path = result_dir / f"backtest_{symbol}_20260101_0000.json"
                path.write_text(json.dumps(payload), encoding="utf-8")

            aggregate = aggregate_benchmarks(result_dir)

        self.assertEqual(aggregate["wilcoxon"]["n_symbols"], 9)
        self.assertAlmostEqual(aggregate["wilcoxon"]["p_value"], 0.00390625, places=12)
        self.assertIn("FPT", aggregate["latex_table"])
        self.assertIn("Wilcoxon", aggregate["latex_table"])
        self.assertIn("^{**}", aggregate["latex_table"])


if __name__ == "__main__":
    unittest.main()
