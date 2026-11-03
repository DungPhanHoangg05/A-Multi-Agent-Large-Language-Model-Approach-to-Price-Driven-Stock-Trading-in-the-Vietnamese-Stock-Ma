"""Tách outer-cutoff isolation khỏi phản ví dụ row-wise; không gọi fail detection là zero-leakage."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.revision_alpha_contract import cutoff_diagnostics, numeric_adapter_diagnostics, require_rowwise_causal, rowwise_diagnostics


class AlphaContractLeakageTests(unittest.TestCase):
    """Tests PASS khi audit phát hiện đúng giới hạn và guard chặn claim sai."""

    def test_actual_agent_selector_all_handlers_ignore_post_cutoff_poison(self) -> None:
        result = cutoff_diagnostics()
        self.assertEqual(result["result"], "PASS")
        self.assertEqual(result["actual_native_backtest_runs"], 2)
        self.assertEqual(result["candidates_per_run"], 85)
        self.assertEqual(len(result["selected_factor_names"]), 5)

    def test_native_rowwise_counterexamples_are_detected_and_fail_causal_guard(self) -> None:
        result = rowwise_diagnostics()
        self.assertEqual(result["diagnostic_result"], "PASS_DETECTION")
        self.assertEqual(result["native_rowwise_causal_gate"], "FAIL")
        self.assertTrue(result["delay_bfill_changes_past"])
        self.assertTrue(result["global_volume_branch_changes_past"])
        self.assertTrue(all(row["historical_values_changed"] for row in result["normalization"].values()))
        with self.assertRaisesRegex(ValueError, "Không được|không được"): require_rowwise_causal(result)

    def test_causal_numeric_adapters_are_separate_and_ignore_future_after_warmup(self) -> None:
        result = numeric_adapter_diagnostics()
        self.assertEqual(result["result"], "PASS")
        self.assertEqual(result["alpha_columns"], 85)
        self.assertEqual(result["poison_checked_rows"], 51)


if __name__ == "__main__":
    unittest.main()
