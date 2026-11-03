"""Kiểm native prompt capture trước API, không dựng prediction giả."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.prepare_chart_r4 import native_prompt
from core.revision_r4_factorial import prompt_parts


class PrepareChartR4Tests(unittest.TestCase):
    """Dựng đúng reports/contract và tính xác định khi chưa có Decision output."""

    def test_native_capture_is_deterministic_and_contains_three_reports(self) -> None:
        state = {"stock_name": "SYNTHETIC", "time_frame": "1 ngày", "language": "vi", "is_backtest": True,
                 "indicator_report": "indicator fixture", "pattern_report": "pattern fixture", "trend_report": "trend fixture"}
        first = native_prompt(state)
        self.assertEqual(first, native_prompt(state))
        parts = prompt_parts(first)
        self.assertEqual(parts["trend"], "trend fixture")
        self.assertEqual(parts["pattern"], "pattern fixture")
        self.assertNotIn("final_trade_decision", state)


if __name__ == "__main__":
    unittest.main()
