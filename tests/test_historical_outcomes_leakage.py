"""Không gắn nhãn trước khi thoát; dữ liệu sau ngày thoát không ảnh hưởng nhãn."""

import unittest

import pandas as pd

import test_historical_outcomes as fixtures
from core.historical_outcomes import HistoricalOutcomeGenerator


class HistoricalOutcomeLeakageTests(unittest.TestCase):
    def test_unsettled_cycle_is_rejected_before_loading_future_prices(self):
        calls = []
        generator = HistoricalOutcomeGenerator(lambda symbol: calls.append(symbol))
        with self.assertRaises(ValueError):
            generator.generate("FPT", "2020-06-05", "2020-06-08", "2020-06-10", fixtures.SIGNALS,
                               settled_as_of="2020-06-09")
        self.assertEqual(calls, [])

    def test_prices_after_exit_do_not_change_labels(self):
        frame = fixtures.fixture_frame()
        generator = HistoricalOutcomeGenerator(lambda symbol: (frame.copy(), []))
        args = ("FPT", "2020-06-05", "2020-06-08", "2020-06-10", fixtures.SIGNALS)
        expected = generator.generate(*args, settled_as_of="2020-06-10")
        future = {key: float("nan") for key in frame.columns if key != "Datetime"}
        future["Datetime"] = pd.Timestamp("2020-06-11")
        frame.loc[len(frame)] = future
        self.assertEqual(generator.generate(*args, settled_as_of="2020-06-10"), expected)


if __name__ == "__main__":
    unittest.main()
