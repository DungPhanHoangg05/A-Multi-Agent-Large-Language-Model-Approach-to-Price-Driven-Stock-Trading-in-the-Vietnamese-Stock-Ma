"""Kiểm PIT/bucket trước selection, future append và chống query label ở đường MT-BICL."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

import numpy as np
import pandas as pd
import talib

from core.mt_bicl_regimes import RegimeTimeline
from core.mt_bicl_stream import MarketStream
from core.mt_bicl_contracts import membership_hash, validate_context, validate_fact_packet, without_target
from core.mt_bicl_features import BucketTaskBuilder, bucket, make_fact_packet
from mt_bicl_tasks_support import FakeDetector, setup
from mt_bicl_support import episode, packet
from utils.graph_util import TechnicalTools


class FeatureLeakageTests(unittest.TestCase):
    """Dữ liệu tổng hợp đủ nhiều block; không fit HMM hoặc đọc nguồn2025."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.bank, cls.sources, cls.history = setup()
        cls.query = str(cls.history["Datetime"].iloc[995].date())

    def builder(self, bank: dict | None = None, sources: dict | None = None) -> BucketTaskBuilder:
        """Mỗi replay có stream và metadata độc lập."""
        bank, sources = bank or self.bank, sources or self.sources
        stream = MarketStream(bank, sources, pd.DatetimeIndex(self.history["Datetime"]))
        regimes = RegimeTimeline(self.history, detector_factory=FakeDetector)
        return BucketTaskBuilder(bank, stream, regimes, {s: f for s, (f, _) in sources.items()})

    def test_four_bucket_signs_missing_zero_and_no_rounding_epsilon(self) -> None:
        fixtures = json.loads(Path("docs/plan/week11/mt_bicl_fixtures.json").read_text(encoding="utf-8"))
        for case in fixtures["bucket_cases"]:
            self.assertEqual(bucket(case["macd_minus_signal"], case["close_minus_sma20"]), case["expected"])
        self.assertEqual(bucket(1e-15, -1e-15), "MACD_POS_PRICE_NEG")
        for value in (True, np.float64(1.), float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                bucket(value, 1.)

    def test_macd_exact_prefix45_matches_legacy_round4_last28(self) -> None:
        frame = self.sources["FPT"][0]
        prefix = frame.loc[frame["Datetime"] <= self.query].tail(45)
        actual = make_fact_packet(frame, "FPT", self.query)
        legacy = TechnicalTools.compute_macd.invoke({"kline_data": {"Close": prefix["Close"].tolist()}})
        values = talib.MACD(prefix["Close"].to_numpy(dtype=np.float64), fastperiod=12, slowperiod=26, signalperiod=9)
        self.assertEqual(round(actual["numeric"]["macd"], 4), legacy["macd"][-1])
        for array, key in zip(values, ("macd", "macd_signal", "macd_hist")):
            self.assertEqual([None if np.isnan(v) else round(float(v), 4) for v in array[-28:]], legacy[key])
        self.assertEqual(actual["numeric"]["sma20"], float(prefix["Close"].to_numpy()[-20:].mean()))

    def test_negative_macd_above_signal_is_not_below_signal(self) -> None:
        actual = packet("FPT-2023-01-06", macd=-.6521, signal=-.762)
        self.assertEqual(actual["assertions"]["MACD_ZERO"], "NEGATIVE")
        self.assertEqual(actual["assertions"]["MACD_SIGNAL"], "ABOVE")
        actual["assertions"]["MACD_SIGNAL"] = "BELOW"
        with self.assertRaises(ValueError):
            validate_fact_packet(actual)

    def test_insufficient_or_stale_prefix_keeps_explicit_unknown(self) -> None:
        frame = self.sources["FPT"][0]
        for date in (str(frame["Datetime"].iloc[20].date()), str((frame["Datetime"].iloc[100]+pd.Timedelta(days=1)).date())):
            source = frame if date == str(frame["Datetime"].iloc[20].date()) else frame.loc[frame["Datetime"] < date]
            value = make_fact_packet(source, "FPT", date)
            self.assertEqual(value["bucket"], "UNKNOWN")
            self.assertTrue(all(v is None for v in value["numeric"].values()))

    def test_future_price_append_and_poison_do_not_change_packet_or_context(self) -> None:
        changed = deepcopy(self.sources)
        for frame, events in changed.values():
            frame.loc[frame["Datetime"] > self.query, ["Open", "High", "Low", "Close", "Volume"]] = np.nan
            events.append({"exrightDate": "2024-01-01"})
        self.assertEqual(make_fact_packet(changed["FPT"][0], "FPT", self.query), make_fact_packet(self.sources["FPT"][0], "FPT", self.query))
        self.assertEqual(self.builder(sources=changed).build("FPT", self.query), self.builder().build("FPT", self.query))

    def test_filter_before_rank_centroid_population_and_multisymbol_cache(self) -> None:
        engine = self.builder()
        first = engine.build("FPT", self.query)
        self.assertGreaterEqual(first["K"], 2)
        for selected in first["prior"]:
            self.assertEqual(selected["population"], len(selected["centroid_fit_ids"]))
            self.assertTrue(set(selected["selected_by_distance_ids"]) <= set(selected["centroid_fit_ids"]))
            source = {row["episode_id"]: row for row in engine.view.source.closed_records()}
            raw = np.array([source[identifier]["features"]["vector"] for identifier in selected["centroid_fit_ids"]])
            matrix = np.clip((raw-first["scaler"]["mean"])/first["scaler"]["scale"], -4, 4)
            self.assertTrue(np.allclose(matrix.mean(axis=0), selected["centroid"], atol=1e-12, rtol=0))
        self.assertTrue(all(f["bucket"] == first["advisor"]["bucket"] for f in first["advisor"]["historical_facts"].values()))
        self.assertEqual(engine.build("MWG", self.query), self.builder().build("MWG", self.query))

    def test_query_outcome_and_candidate_labels_do_not_choose_membership(self) -> None:
        changed = deepcopy(self.bank)
        for row in changed["records"]:
            if row["episode_id"] == "FPT-"+self.query:
                row["outcome"] = {"y": "Nhãn query bị cấm", "r_net": float("nan")}
            elif row["outcome"] is not None:
                row["outcome"]["r_net"] *= -1
                row["outcome"]["y"] = int(row["outcome"]["r_net"] > 0)
        before, after = self.builder().build("FPT", self.query), self.builder(bank=changed).build("FPT", self.query)
        self.assertEqual(before["scaler"], after["scaler"])
        self.assertEqual([t["selected_by_distance_ids"] for t in before["prior"]], [t["selected_by_distance_ids"] for t in after["prior"]])
        self.assertEqual([r["episode_id"] for r in before["target"]], [r["episode_id"] for r in after["target"]])

    def test_injected_query_labels_equal_exit_overlap_duplicate_fail_even_rehashed(self) -> None:
        for mode in ("label", "top_outcome", "exit_equal", "duplicate", "overlap", "bucket", "future_proof"):
            value = episode()
            if mode == "label": value["query"]["r_net"] = .1
            if mode == "top_outcome": value["outcome"] = .1
            if mode == "exit_equal": value["target"][-1]["exit_date"] = value["query"]["as_of_date"]
            if mode == "duplicate": value["target"][1] = deepcopy(value["target"][0])
            if mode == "overlap": value["target"][1]["entry_date"] = value["target"][0]["entry_date"]
            if mode == "bucket": next(iter(value["advisor"]["historical_facts"].values()))["bucket"] = "MACD_NEG_PRICE_POS"
            if mode == "future_proof": next(iter(value["advisor"]["historical_facts"].values()))["frame_end_date"] = value["query"]["as_of_date"]
            value["membership_sha256"] = membership_hash(value)
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                validate_context(value)

    def test_without_target_preserves_D_query_and_prunes_only_target_proofs(self) -> None:
        full = episode()
        changed = without_target(full)
        self.assertEqual(changed["prior"], full["prior"])
        self.assertEqual(changed["query"], full["query"])
        self.assertEqual((changed["m"], changed["target"]), (0, []))
        self.assertNotEqual(changed["membership_sha256"], full["membership_sha256"])

    def test_bad_source_and_selected_membership_hash_raise(self) -> None:
        frame = self.sources["FPT"][0].copy()
        frame.loc[frame["Datetime"] == self.query, "Close"] = float("nan")
        with self.assertRaises(ValueError): make_fact_packet(frame, "FPT", self.query)
        value = episode()
        value["target"][0]["model_vector"][0] += .001
        with self.assertRaises(ValueError): validate_context(value)


if __name__ == "__main__":
    unittest.main()
