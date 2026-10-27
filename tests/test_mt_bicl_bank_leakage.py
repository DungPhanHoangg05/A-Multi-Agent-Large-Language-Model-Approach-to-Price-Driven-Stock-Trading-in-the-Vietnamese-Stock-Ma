"""Kiểm cutoff bank/scaler, append tương lai và tách feature khỏi nhãn query."""

from __future__ import annotations

from copy import deepcopy
import unittest

import numpy as np
import pandas as pd

from core.mt_bicl_scaler import fit_scaler, transform_features
from mt_bicl_bank_support import bank, feature, prices, scaler_bank


class DenseBankLeakageTests(unittest.TestCase):
    """Thay dữ liệu sau cutoff không được làm đổi đầu vào đã quan sát."""

    def test_future_bars_reference_events_and_adjusted_columns_do_not_change_bank(self) -> None:
        frame, calendar = prices(periods=120)
        past_calendar = calendar[:90]
        original = bank(frame.iloc[:90], past_calendar)
        changed = frame.copy()
        changed.loc[90:, ["Open", "High", "Low", "Close", "Reference"]] = np.nan
        changed["closePriceAdjusted"] = -999.
        later_event = [{"exrightDate": str(calendar[100].date())}]
        self.assertEqual(bank(changed, past_calendar, later_event), original)

    def test_query_feature_does_not_change_when_execution_prices_change(self) -> None:
        frame, calendar = prices(flat=True)
        before = bank(frame, calendar)["records"][0]
        changed = frame.copy()
        changed.loc[21, ["Open", "High"]] = 200.
        after = bank(changed, calendar)["records"][0]
        self.assertEqual(before["features"], after["features"])
        self.assertNotEqual(before["outcome"], after["outcome"])

    def test_exit_equal_query_is_not_in_scaler(self) -> None:
        data = scaler_bank()
        scaler = fit_scaler(data, "2020-12-25")
        self.assertEqual(scaler["fit_count"], 1)
        self.assertEqual(scaler["fit_episode_ids"], ["FPT-2020-12-21"])
        self.assertEqual(scaler["status"], "UNAVAILABLE")

    def test_future_features_and_labels_do_not_enter_scaler(self) -> None:
        data = scaler_bank()
        before = fit_scaler(data, "2020-12-28")
        changed = deepcopy(data)
        changed["records"][2]["features"]["vector"] = [float("nan")]*4
        changed["records"][2]["outcome"] = {"bad": "future label"}
        changed["records"][3]["features"]["vector"] = [float("inf")]*4
        self.assertEqual(fit_scaler(changed, "2020-12-28"), before)

    def test_labels_never_change_fit_ids_mean_or_transformation(self) -> None:
        data = scaler_bank()
        before = fit_scaler(data, "2020-12-28")
        changed = deepcopy(data)
        for row in changed["records"]:
            row["outcome"] = {"y": "invalid label", "r_net": float("nan")}
        self.assertEqual(fit_scaler(changed, "2020-12-28"), before)

    def test_frozen_scaler_uses_no_2021_or_2022_rows(self) -> None:
        data = scaler_bank()
        first = fit_scaler(data, "2021-01-01")
        self.assertEqual(first["fit_count"], 3)
        self.assertEqual(first["mode"], "frozen_train")
        self.assertEqual(first, fit_scaler(data, "2022-12-30"))
        data["records"][3]["features"]["vector"] = [999999.]*4
        self.assertEqual(first, fit_scaler(data, "2022-12-30"))

    def test_injected_future_feature_date_and_invalid_cycle_raise(self) -> None:
        data = scaler_bank()
        data["records"][0]["features"]["feature_end_date"] = "2022-01-01"
        with self.assertRaises(ValueError):
            fit_scaler(data, "2020-12-28")
        data = scaler_bank()
        data["records"][0]["as_of_date"] = "2021-01-01"
        with self.assertRaises(ValueError):
            fit_scaler(data, "2020-12-28")

    def test_scaler_from_future_and_future_context_cannot_transform_query(self) -> None:
        scaler = fit_scaler(scaler_bank(), "2021-01-01")
        with self.assertRaises(ValueError):
            transform_features(feature("2020-12-28", [0.]*4), scaler)
        scaler = fit_scaler(scaler_bank(), "2020-12-28")
        with self.assertRaises(ValueError):
            transform_features(feature("2021-01-04", [0.]*4), scaler, query_date="2020-12-28")


if __name__ == "__main__":
    unittest.main()
