"""Guard năm/query-label/PIT/economics của consumer MT-BICL, không API hoặc dữ liệu2025 thật."""

from __future__ import annotations

from copy import deepcopy
import unittest

import pandas as pd

from core.backtest_engine import compute_round_trip_net_return
from core.mt_bicl_accounting import check_labels, evaluate_cycle
from core.mt_bicl_reporting import Analysis
from core.mt_bicl_analysis import nominate, validate_economics, group
from test_mt_bicl_analysis import fixture


class AnalysisLeakageTests(unittest.TestCase):
    """Kiểm rò rỉ/thay nhãn được ném lỗi, không bị loại point hoặc trả NOT_NOMINATED giả."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.source, cls.protocol, _ = fixture()
        cls.primary = [p for p in cls.source["points"] if p["repeat_index"] == 0]

    def test_equal_exit_context_not_visible(self) -> None:
        context = {"query": {"as_of_date": "2023-01-06"}, "prior": [],
                   "target": [{"exit_date": "2023-01-06"}]}
        with self.assertRaises(ValueError): check_labels(context, {})

    def test_economic_label_is_net_after_both_fees_and_slippage(self) -> None:
        dates = pd.bdate_range("2023-01-02", periods=5)
        frame = pd.DataFrame({"Datetime": dates, "Open": [100.]*5, "High": [101.]*5, "Low": [99.]*5, "Close": [100.]*5, "Reference": [100.]*5, "Volume": [10.]*5})
        result = evaluate_cycle(frame, [], "2023-01-02")
        self.assertEqual(result["entry_date"], "2023-01-03")
        self.assertEqual(result["exit_date"], "2023-01-05")
        self.assertEqual(result["net_return_long"], compute_round_trip_net_return(100., 100.))
        self.assertEqual(result["actual_direction"], "DOWN")

    def test_future_append_does_not_change_current_cycle_prices(self) -> None:
        dates = pd.bdate_range("2023-01-02", periods=8)
        frame = pd.DataFrame({"Datetime": dates, "Open": [100.]*8, "High": [101.]*8, "Low": [99.]*8, "Close": [100.]*8, "Reference": [100.]*8, "Volume": [10.]*8})
        before = evaluate_cycle(frame.iloc[:5].copy(), [], "2023-01-02")
        frame.loc[5:, ["Open", "Close"]] = 99999.
        self.assertEqual(evaluate_cycle(frame, [], "2023-01-02"), before)

    def test_2025_or_filtered_primary_cannot_enter_nomination(self) -> None:
        for mode in ("year", "drop"):
            points = deepcopy(self.primary)
            if mode == "year": points[0]["as_of_date"] = "2025-01-06"
            else: points.pop()
            report = {"status": "PASS", "phase": "development2023", "nomination": "NOT_EVALUATED", "confirmation_allowed": False,
                      "primary_cases": points, "G": group(self.primary, Analysis())}
            with self.assertRaises(ValueError): nominate(report, self.protocol)

    def test_poison_net_label_does_not_silently_change_accuracy(self) -> None:
        point = deepcopy(self.primary[0])
        point["evaluation"]["net_return_long"] = -point["evaluation"]["net_return_long"]
        with self.assertRaises(ValueError): validate_economics([point])


if __name__ == "__main__":
    unittest.main()
