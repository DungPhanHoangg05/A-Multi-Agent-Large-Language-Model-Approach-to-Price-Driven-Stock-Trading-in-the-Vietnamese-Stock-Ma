"""Đối chiếu công thức, coverage và lỗi nguồn cho feature giá PIT."""

from copy import deepcopy
import json
import math
from typing import Any
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from core.pit_price_features import FEATURE_COLUMNS, extract_pit_price_features
from prior_context_test_support import ContextFixture


SOURCE = {"source_library": "vnstock", "primary_source": "VCI",
          "price_basis": "UNADJUSTED_EXECUTION", "price_unit": "thousand_VND"}


def price_frame(close: np.ndarray | list[float]) -> pd.DataFrame:
    """Nến tổng hợp trên lịch phiên, Reference bằng Close phiên trước."""
    close = np.asarray(close, dtype=float)
    return pd.DataFrame({"Datetime": pd.bdate_range("2021-01-04", periods=len(close)),
        "Open": close, "High": close, "Low": close, "Close": close,
        "Volume": 100, "Reference": np.r_[close[:1], close[:-1]]})


class PitPriceFeatureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.frame = price_frame([100.] * 20 + [110.])
        self.calendar = pd.DatetimeIndex(self.frame.Datetime)
        self.cutoff = self.calendar[-1].strftime("%Y-%m-%d")

    def extract(self, frame: pd.DataFrame | None = None, events: list | None = None,
                **kwargs: Any) -> dict:
        """Gọi hàm thuần bằng nguồn rõ đơn vị; không cần nhãn hoặc evaluator."""
        return extract_pit_price_features(self.frame if frame is None else frame,
            [] if events is None else events, self.calendar, self.cutoff,
            source=kwargs.get("source", SOURCE))

    def test_hand_calculated_single_jump_population_volatility_and_ma_window(self) -> None:
        result = self.extract()
        expected = [.1, .1, math.log(1.1) * math.sqrt(19) / 20, 19 / 201]
        np.testing.assert_allclose(result["vector"], expected, rtol=0, atol=1e-12)
        self.assertEqual(result["feature_columns"], list(FEATURE_COLUMNS))
        self.assertEqual(result["status"], "AVAILABLE")
        self.assertEqual(result["reasons"], [])
        self.assertEqual(result["feature_version"], "pit_price_features_v1")
        self.assertEqual(result["price_policy_version"], "raw_segment_21_v1")
        self.assertEqual(result["feature_end_date"], self.cutoff)
        self.assertEqual(result["coverage"]["available_bars"], 21)

    def test_constant_prices_produce_four_valid_zeroes(self) -> None:
        self.assertEqual(self.extract(price_frame([100.] * 21))["vector"], [0.] * 4)

    def test_geometric_growth_uses_five_and_twenty_returns(self) -> None:
        result = self.extract(price_frame(100 * 1.01 ** np.arange(21)))
        np.testing.assert_allclose(result["vector"],
            [.0510100501, .220190039947967, 0., .09733296812973058], rtol=0, atol=1e-12)

    def test_uniform_price_unit_scaling_preserves_features_without_rescaling(self) -> None:
        scaled = self.frame.copy()
        columns = ["Open", "High", "Low", "Close", "Reference"]
        scaled[columns] *= 1000
        np.testing.assert_allclose(self.extract(scaled)["vector"], self.extract()["vector"], rtol=0, atol=1e-12)

    def test_zero_volume_is_diagnostic_only_and_json_is_native(self) -> None:
        frame = self.frame.copy()
        frame.loc[[0, 20], "Volume"] = 0
        result = self.extract(frame)
        self.assertEqual(result["vector"], self.extract()["vector"])
        self.assertEqual(result["coverage"]["zero_volume_count"], 2)
        self.assertEqual(json.loads(json.dumps(result, allow_nan=False)), result)
        self.assertTrue(all(type(value) is float for value in result["vector"]))
        self.assertIs(type(result["coverage"]["available_bars"]), int)

    def test_vci_and_kbs_are_the_only_accepted_sources(self) -> None:
        kbs = {**SOURCE, "primary_source": "KBS"}
        self.assertEqual(self.extract(source=kbs)["vector"], self.extract()["vector"])
        for field, value in (("source_library", "other"), ("primary_source", "TCBS"),
                             ("price_basis", "ADJUSTED"), ("price_unit", "VND"),
                             ("price_unit", np.str_("thousand_VND"))):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.extract(source={**SOURCE, field: value})
        with self.assertRaises(ValueError):
            self.extract(source={})

    def test_less_than_twenty_one_sessions_and_late_source_start_are_unavailable(self) -> None:
        for start in (1, 15):
            result = self.extract(self.frame.iloc[start:])
            self.assertEqual(result["reasons"], ["INSUFFICIENT_HISTORY"])
            self.assertIsNone(result["vector"])
            self.assertEqual(result["coverage"]["available_bars"], 21 - start)
        result = extract_pit_price_features(self.frame.iloc[:20], [], self.calendar[:20],
            self.calendar[19].strftime("%Y-%m-%d"), source=SOURCE)
        self.assertEqual(result["reasons"], ["INSUFFICIENT_HISTORY"])

    def test_missing_middle_session_is_not_joined_or_filled(self) -> None:
        result = self.extract(self.frame.drop(index=10))
        self.assertEqual(result["reasons"], ["MISSING_SESSION"])
        self.assertEqual(result["coverage"]["missing_sessions"], [self.calendar[10].strftime("%Y-%m-%d")])
        self.assertEqual(result["coverage"]["available_bars"], 20)
        self.assertIsNone(result["vector"])

    def test_missing_cutoff_and_empty_history_have_explicit_reasons(self) -> None:
        result = self.extract(self.frame.iloc[:-1])
        self.assertEqual(result["reasons"], ["MISSING_CUTOFF"])
        self.assertEqual(result["feature_end_date"], self.calendar[-2].strftime("%Y-%m-%d"))
        empty = self.extract(self.frame.iloc[:0])
        self.assertEqual(empty["status"], "UNAVAILABLE")
        self.assertEqual(empty["reasons"], ["INSUFFICIENT_HISTORY", "MISSING_CUTOFF"])
        self.assertIsNone(empty["feature_end_date"])
        self.assertIsNone(empty["coverage"]["start_date"])

    def test_exright_barrier_at_left_boundary_allowed_at_cutoff_rejected(self) -> None:
        first = [{"exrightDate": self.calendar[0].strftime("%Y-%m-%d")}]
        self.assertEqual(self.extract(events=first)["vector"], self.extract()["vector"])
        for index in (1, 10, 20):
            day = self.calendar[index].strftime("%Y-%m-%d")
            result = self.extract(events=[{"exrightDate": day}])
            self.assertEqual(result["reasons"], ["CORPORATE_ACTION_WINDOW"])
            self.assertEqual(result["coverage"]["barrier_dates"], [day])
            self.assertIsNone(result["vector"])

    def test_reference_barrier_without_event_is_detected_and_deduplicated(self) -> None:
        frame = self.frame.copy()
        frame.loc[10, "Reference"] += .01
        day = self.calendar[10].strftime("%Y-%m-%d")
        result = self.extract(frame, [{"exrightDate": day}])
        self.assertEqual(result["coverage"]["barrier_dates"], [day])
        self.assertEqual(result["reasons"], ["CORPORATE_ACTION_WINDOW"])
        self.assertEqual(self.extract(frame)["reasons"], ["CORPORATE_ACTION_WINDOW"])

    def test_reference_change_at_first_window_bar_is_allowed(self) -> None:
        frame = price_frame([100.] * 22)
        frame.loc[1, "Reference"] = 90.
        result = extract_pit_price_features(frame, [], pd.DatetimeIndex(frame.Datetime),
            frame.Datetime.iloc[-1].strftime("%Y-%m-%d"), source=SOURCE)
        self.assertEqual(result["vector"], [0.] * 4)
        self.assertEqual(result["coverage"]["barrier_dates"], [])

    def test_invalid_ohlcv_reference_is_integrity_error_even_outside_window(self) -> None:
        for field, value in (("Close", np.nan), ("Open", 0.), ("High", 1.), ("Low", 999.),
                             ("Volume", -.1), ("Volume", 1.5), ("Reference", np.inf),
                             ("Reference", 0.), ("Close", "bad")):
            frame = self.frame.astype({field: object})
            frame.loc[0, field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.extract(frame)
        frame = price_frame([100.] * 22)
        frame.loc[0, "Reference"] = np.nan
        with self.assertRaises(ValueError):
            extract_pit_price_features(frame, [], pd.DatetimeIndex(frame.Datetime),
                frame.Datetime.iloc[-1].strftime("%Y-%m-%d"), source=SOURCE)

    def test_duplicate_unsorted_nan_intraday_or_timezone_dates_raise(self) -> None:
        for frame in (pd.concat([self.frame, self.frame.iloc[-1:]]), self.frame.iloc[::-1],
                      self.frame.assign(Datetime=self.frame.Datetime.mask(self.frame.index == 5)),
                      self.frame.assign(Datetime=self.frame.Datetime + pd.Timedelta(hours=1)),
                      self.frame.assign(Datetime=self.frame.Datetime.dt.tz_localize("UTC"))):
            with self.subTest(dates=str(frame.Datetime.dtype)), self.assertRaises(ValueError):
                self.extract(frame)

    def test_calendar_integrity_is_checked_and_off_calendar_price_rejected(self) -> None:
        for calendar in (self.calendar[::-1], self.calendar.append(self.calendar[-1:]),
                         self.calendar.delete(5), self.calendar.tz_localize("UTC")):
            with self.subTest(calendar=str(calendar.dtype)), self.assertRaises(ValueError):
                extract_pit_price_features(self.frame, [], calendar, self.cutoff, source=SOURCE)

    def test_bad_events_cutoff_or_missing_source_columns_raise(self) -> None:
        for events in ({}, [None], [{"exrightDate": "bad"}], [{"exrightDate": "2021-01-12T12:00:00"}]):
            with self.subTest(events=events), self.assertRaises(ValueError):
                self.extract(events=events)
        for cutoff in (None, "20210104", "2021-01-04T00:00:00"):
            with self.subTest(cutoff=cutoff), self.assertRaises(ValueError):
                extract_pit_price_features(self.frame, [], self.calendar, cutoff, source=SOURCE)
        for field in ("Volume", "Reference"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.extract(self.frame.drop(columns=field))

    def test_nonfinite_arithmetic_is_integrity_error(self) -> None:
        for close in ([1e-300] * 20 + [1e300], [1e308] * 21):
            with self.subTest(close=close[-1]), self.assertRaises(ValueError):
                self.extract(price_frame(close))

    def test_inputs_and_returned_metadata_are_owned_and_unmodified(self) -> None:
        frame, source = self.frame.copy(deep=True), deepcopy(SOURCE)
        result = self.extract(frame, source=source)
        pd.testing.assert_frame_equal(frame, self.frame)
        result["source"]["price_unit"] = "changed"
        result["coverage"]["barrier_dates"].append("2099-01-01")
        self.assertEqual(source, SOURCE)
        self.assertEqual(self.extract()["coverage"]["barrier_dates"], [])


class PitPriceFeatureAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = ContextFixture()
        self.addCleanup(self.fx.close)

    def test_public_adapter_and_point_use_same_extractor_without_evaluator(self) -> None:
        adapter = self.fx.adapter()
        point = adapter.prepare("FPT", self.fx.cutoff)
        before = point.source_provenance
        with (patch.object(adapter, "execution_data", side_effect=AssertionError("Cấm evaluator")),
              patch.object(adapter._provider, "get", side_effect=AssertionError("Không cần regime")),
              patch.object(adapter._retriever, "retrieve", side_effect=AssertionError("Không cần prior"))):
            result = point.price_features()
            self.assertEqual(result, adapter.price_features("FPT", self.fx.cutoff))
            # Một cửa sổ đủ 21 phiên không cần 600 phiên Alpha hoặc artifact HMM.
            early = adapter.price_features("FPT", self.fx.day(20))
            self.assertEqual(early["status"], "AVAILABLE")
        direct = extract_pit_price_features(self.fx.frame["FPT"], [], pd.DatetimeIndex(self.fx.vnindex.Datetime),
            self.fx.cutoff, source=SOURCE)
        self.assertEqual(result["vector"], direct["vector"])
        self.assertEqual(point.source_provenance, before)
        self.assertEqual(result["symbol"], "FPT")
        self.assertEqual(result["source_provenance"]["prices"]["csv_sha256"], before["prices"]["csv_sha256"])
        self.assertEqual(result["source_provenance"]["calendar"]["source_csv_sha256"],
                         before["regime"]["source_csv_sha256"])

    def test_feature_request_preserves_shared_full_and_legacy_retrieval(self) -> None:
        adapter = self.fx.adapter()
        point = adapter.prepare("FPT", self.fx.cutoff)
        shared = point.bind_full(self.fx.full(point))
        before = point.retrieve(shared)
        features = point.price_features()
        features["vector"][0] = 999.
        features["source_provenance"]["prices"]["csv_sha256"] = "wrong"
        self.assertEqual(point.retrieve(shared), before)
        self.assertEqual(point.bind_full(self.fx.full(point)), shared)
        self.assertNotIn("price_features", shared)
        self.assertNotEqual(point.price_features()["vector"][0], 999.)

    def test_public_adapter_rejects_source_tampering_before_extraction(self) -> None:
        adapter = self.fx.adapter()
        path = self.fx.root / "data/execution_prices/FPT.events.json"
        path.write_text('{"records": []}\n ', encoding="utf-8")
        with (patch("core.prior_context.extract_pit_price_features") as extract,
              self.assertRaises(ValueError)):
            adapter.price_features("FPT", self.fx.cutoff)
        extract.assert_not_called()

    def test_public_adapter_rejects_bad_symbol_or_cutoff(self) -> None:
        adapter = self.fx.adapter()
        for symbol, cutoff in (("VNINDEX", self.fx.cutoff), ("FPT", "2099-01-01"), ("FPT", "20200101")):
            with self.subTest(symbol=symbol, cutoff=cutoff), self.assertRaises(ValueError):
                adapter.price_features(symbol, cutoff)
