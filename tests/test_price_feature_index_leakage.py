"""Chống rò rỉ qua fit fold, vector episode và đường nối archive OOS."""

from copy import deepcopy
import unittest

import numpy as np
import pandas as pd

from core.price_feature_index import build_price_feature_index
from price_feature_index_support import index_inputs


class PriceFeatureIndexLeakageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inputs = index_inputs()
        cls.index = build_price_feature_index(**cls.inputs)

    def test_future_price_changes_do_not_affect_past_features_or_early_fit(self) -> None:
        inputs = deepcopy(self.inputs)
        frame, _ = inputs["prices"]["FPT"]
        mask = frame.Datetime > pd.Timestamp("2021-01-04")
        for column in ("Open", "High", "Low", "Close", "Reference"):
            frame.loc[mask, column] *= 2
        changed = build_price_feature_index(**inputs)
        self.assertNotEqual(changed.identity, self.index.identity)
        old_scaler, new_scaler = self.index.scaler("FPT", "2021-01-04"), changed.scaler("FPT", "2021-01-04")
        old_scaler.pop("index_sha256")
        new_scaler.pop("index_sha256")
        self.assertEqual(old_scaler, new_scaler)
        before = {row["episode_id"]: row for row in self.index.payload["records"]}
        for row in changed.payload["records"]:
            if row["as_of_date"] <= "2021-01-04":
                self.assertEqual(row, before[row["episode_id"]])

    def test_later_closed_episode_not_added_to_frozen_earlier_fit(self) -> None:
        early = self.index.scaler("FPT", "2021-01-04")
        late = self.index.scaler("FPT", "2021-12-31")
        self.assertEqual(early, late)
        self.assertIn("FPT:2021-01-04", self.index.closed_episode_ids("FPT", "2021-12-31"))
        self.assertNotIn("FPT:2021-01-04", late["fit_episode_ids"])
        self.assertNotEqual(early["fit_episode_ids"], self.index.scaler("FPT", "2022-01-06")["fit_episode_ids"])

    def test_equal_future_exit_and_wrong_fold_are_rejected(self) -> None:
        for day, key in (("2021-01-04", "FPT:2020-12-30"),
                         ("2021-01-04", "FPT:2021-01-04"),
                         ("2022-01-06", "FPT:2022-01-03"),
                         ("2022-01-06", "FPT:2022-12-27")):
            with self.subTest(day=day, key=key), self.assertRaises(ValueError):
                self.index.prior_features("FPT", day, [key])
        with self.assertRaises(ValueError):
            self.index.prior_features("FPT", "2021-01-04", ["FPT:2020-06-01"], fold_id="oos_2023_2024")

    def test_oos_extension_keeps_train_scalers_and_rejects_altered_train_prefix(self) -> None:
        inputs = deepcopy(self.inputs)
        dates = pd.bdate_range("2023-01-02", "2024-12-31")
        inputs["calendar"] = inputs["calendar"].append(dates)
        for symbol, (frame, events) in inputs["prices"].items():
            close = np.full(len(dates), 999.)
            future = pd.DataFrame({"Datetime": dates, "Open": close, "High": close + 1,
                "Low": close - 1, "Close": close, "Reference": close, "Volume": 100})
            inputs["prices"][symbol] = (pd.concat([frame, future], ignore_index=True),
                                         events + [{"exrightDate": "2024-12-31T00:00:00"}])
        changed = build_price_feature_index(**inputs)
        self.assertEqual(changed.identity, self.index.identity)
        self.index.verify_query_sources(prices=inputs["prices"], calendar=inputs["calendar"],
                                        source=inputs["source"], bank=inputs["provenance"]["bank"])
        self.assertEqual(self.index.scaler("FPT", "2023-01-03"), self.index.scaler("FPT", "2024-12-31"))
        inputs["prices"]["FPT"][0].loc[0, "Close"] += 1
        with self.assertRaises(ValueError):
            self.index.verify_query_sources(prices=inputs["prices"], calendar=inputs["calendar"],
                                            source=inputs["source"], bank=inputs["provenance"]["bank"])

    def test_outcome_not_accepted_by_producer_and_unavailable_cannot_borrow_later_fold(self) -> None:
        for outcome in ("WIN", "LOSS", {"net_return": 999.}):
            inputs = deepcopy(self.inputs)
            inputs["records"][0]["outcome"] = outcome
            with self.assertRaises(ValueError):
                build_price_feature_index(**inputs)
        for day in ("2021-01-04", "2022-01-06", "2023-01-03", "2024-12-31"):
            scaler = self.index.scaler("VNM", day)
            self.assertEqual(scaler["fit_count"], 1)
            self.assertEqual(scaler["status"], "SCALER_UNAVAILABLE")
