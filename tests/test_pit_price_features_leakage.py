"""Bất biến PIT của feature khi thêm hoặc sửa dữ liệu sau cutoff."""

from copy import deepcopy
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from core.pit_price_features import extract_pit_price_features
from test_pit_price_features import SOURCE, price_frame
from prior_context_test_support import ContextFixture


class PitPriceFeatureLeakageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.frame = price_frame(100 * 1.01 ** np.arange(51))
        self.calendar = pd.DatetimeIndex(self.frame.Datetime)
        self.cutoff = self.calendar[30].strftime("%Y-%m-%d")

    def extract(self, frame: pd.DataFrame, events: list | None = None,
                calendar: pd.DatetimeIndex | None = None) -> dict:
        """Không truyền ngày entry/exit hoặc outcome dưới bất kỳ hình thức nào."""
        return extract_pit_price_features(frame, events or [], self.calendar if calendar is None else calendar,
                                          self.cutoff, source=SOURCE)

    def test_appending_future_bars_and_calendar_leaves_entire_pit_result_unchanged(self) -> None:
        first = self.extract(self.frame.iloc[:31], calendar=self.calendar[:31])
        self.assertEqual(first, self.extract(self.frame))

    def test_future_ohlcv_reference_even_nan_do_not_enter_validation_or_math(self) -> None:
        expected = self.extract(self.frame)
        for field in ("Open", "High", "Low", "Close", "Volume", "Reference"):
            frame = self.frame.copy()
            frame.loc[31:, field] = np.nan
            with self.subTest(field=field):
                self.assertEqual(self.extract(frame), expected)

    def test_future_exright_and_reference_barriers_do_not_change_past_coverage(self) -> None:
        expected = self.extract(self.frame)
        frame = self.frame.copy()
        frame.loc[31:, "Reference"] *= .5
        events = [{"exrightDate": self.calendar[31].strftime("%Y-%m-%d")},
                  {"exrightDate": "2099-01-01"}]
        self.assertEqual(self.extract(frame, events), expected)

    def test_later_prices_cannot_fill_missing_past_session_or_cutoff(self) -> None:
        for missing, reason in ((25, "MISSING_SESSION"), (30, "MISSING_CUTOFF")):
            frame = self.frame.drop(index=missing)
            result = self.extract(frame)
            self.assertIn(reason, result["reasons"])
            self.assertIsNone(result["vector"])
            prefix = frame.loc[frame.Datetime <= pd.Timestamp(self.cutoff)]
            self.assertEqual(result, self.extract(prefix, calendar=self.calendar[:31]))

    def test_historical_episode_uses_own_cutoff_instead_of_later_query_prices(self) -> None:
        historical = extract_pit_price_features(self.frame, [], self.calendar,
            self.calendar[20].strftime("%Y-%m-%d"), source=SOURCE)
        later = self.frame.copy()
        later.loc[21:, ["Open", "High", "Low", "Close"]] *= 1.5
        replay = extract_pit_price_features(later, [], self.calendar,
            self.calendar[20].strftime("%Y-%m-%d"), source=SOURCE)
        self.assertEqual(historical, replay)

    def test_adapter_cuts_before_features_and_never_consults_query_outcome(self) -> None:
        fx = ContextFixture()
        self.addCleanup(fx.close)
        adapter = fx.adapter()
        with (patch("socket.socket.connect", side_effect=AssertionError("Cấm mạng")),
              patch.object(adapter, "execution_data", side_effect=AssertionError("Cấm evaluator")),
              patch.object(adapter._retriever, "retrieve", side_effect=AssertionError("Cấm outcome"))):
            expected = adapter.price_features("FPT", fx.cutoff)
            frame, events = adapter._prices["FPT"]
            changed = frame.copy()
            changed.loc[645:, ["Open", "High", "Low", "Close", "Reference"]] = np.nan
            adapter._prices["FPT"] = changed, deepcopy(events) + [{"exrightDate": fx.day(650)}]
            self.assertEqual(adapter.price_features("FPT", fx.cutoff), expected)


if __name__ == "__main__":
    unittest.main()
