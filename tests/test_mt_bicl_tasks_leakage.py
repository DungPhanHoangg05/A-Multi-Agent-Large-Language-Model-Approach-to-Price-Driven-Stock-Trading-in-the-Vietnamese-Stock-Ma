"""Chống future membership, giao cycle, đổi nhãn query và leakage regime/stream."""

from __future__ import annotations

from copy import deepcopy
import unittest

import numpy as np
import pandas as pd

from core.mt_bicl_regimes import RegimeTimeline
from core.mt_bicl_stream import MarketStream
from core.mt_bicl_tasks import validate_episode
from mt_bicl_tasks_support import FakeDetector, builder, setup


class TaskLeakageTests(unittest.TestCase):
    """Mỗi test giữ source/prefix phù hợp và chỉ đổi phần được kiểm."""

    @classmethod
    def setUpClass(cls) -> None:
        """Nguồn đủ nhiều block nhưng detector giả để không lặp fit HMM."""
        cls.bank, cls.sources, cls.history = setup()
        cls.query = str(cls.history["Datetime"].iloc[995].date())
        cls.episode = builder(cls.bank, cls.sources, cls.history).build("FPT", cls.query)

    def test_query_outcome_flip_does_not_change_entire_input_episode(self) -> None:
        changed = deepcopy(self.bank)
        for row in changed["records"]:
            if row["episode_id"] == "FPT-"+self.query:
                row["outcome"] = {"y": "forbidden", "r_net": float("nan")}
        result = builder(changed, self.sources, self.history).build("FPT", self.query)
        self.assertEqual(result, self.episode)

    def test_prior_label_changes_do_not_change_ranking_or_scaler(self) -> None:
        changed = deepcopy(self.bank)
        for row in changed["records"]:
            if row["outcome"] is not None:
                row["outcome"]["r_net"] *= -1
                row["outcome"]["y"] = int(row["outcome"]["r_net"] > 0)
        result = builder(changed, self.sources, self.history).build("FPT", self.query)
        self.assertEqual(result["membership_sha256"], self.episode["membership_sha256"])
        self.assertEqual(result["scaler"], self.episode["scaler"])

    def test_future_prices_events_and_vnindex_close_leave_episode_unchanged(self) -> None:
        sources = deepcopy(self.sources)
        for frame, events in sources.values():
            frame.loc[frame["Datetime"] > self.query, ["Open", "Close", "High", "Low", "Reference"]] = np.nan
            events.append({"exrightDate": str(self.history["Datetime"].iloc[1020].date())})
        history = self.history.copy()
        history.loc[history["Datetime"] > self.query, "Close"] = float("nan")
        self.assertEqual(builder(self.bank, sources, history).build("FPT", self.query), self.episode)

    def test_early_train_query_never_fits_future_frozen_scaler(self) -> None:
        query = str(self.history["Datetime"].iloc[150].date())
        before = builder(self.bank, self.sources, self.history).build("FPT", query)
        changed = deepcopy(self.bank)
        for row in changed["records"]:
            if row["as_of_date"] > query:
                row["features"]["vector"] = [float("nan")]*4
        after = builder(changed, self.sources, self.history).build("FPT", query)
        self.assertEqual(before, after)

    def test_valid_context_becomes_prior_after_block_changes(self) -> None:
        engine = builder(self.bank, self.sources, self.history)
        before_date = str(self.history["Datetime"].iloc[15*63+50].date())
        later_date = str(self.history["Datetime"].iloc[16*63+25].date())
        before = engine.build("FPT", before_date)
        after = engine.build("FPT", later_date)
        self.assertNotEqual(before["query"]["task_id"], after["query"]["task_id"])
        self.assertTrue(all(row["task_id"] == after["query"]["task_id"] for row in after["target"]))
        visible = engine.stream.closed_records()
        old_target_ids = {row["episode_id"] for row in before["target"]}
        self.assertTrue(old_target_ids.issubset({row["episode_id"] for row in visible}))
        self.assertTrue(all(task["block_index"] < after["query"]["block_index"] for task in after["prior"]))

    def test_injected_exit_equal_query_and_duplicate_id_raise(self) -> None:
        changed = deepcopy(self.episode)
        changed["target"][-1]["exit_date"] = self.query
        with self.assertRaises(ValueError):
            validate_episode(changed)
        changed = deepcopy(self.episode)
        changed["target"].append(deepcopy(changed["target"][-1]))
        changed["m"] += 1
        with self.assertRaises(ValueError):
            validate_episode(changed)

    def test_overlap_and_other_symbol_cannot_enter_selected_context(self) -> None:
        changed = deepcopy(self.episode)
        changed["target"][1]["entry_date"] = changed["target"][0]["entry_date"]
        with self.assertRaises(ValueError):
            validate_episode(changed)
        changed = deepcopy(self.episode)
        changed["prior"][0]["observations"][0]["symbol"] = "VNM"
        with self.assertRaises(ValueError):
            validate_episode(changed)

    def test_future_scaler_or_regime_in_selected_context_raises(self) -> None:
        changed = deepcopy(self.episode)
        changed["scaler"]["fit_max_exit_date"] = self.query
        with self.assertRaises(ValueError):
            validate_episode(changed)
        changed = deepcopy(self.episode)
        changed["prior"][0]["regime"]["model_training_end_date"] = "2022-12-31"
        with self.assertRaises(ValueError):
            validate_episode(changed)

    def test_query_cannot_carry_label_and_stream_cannot_open_2025(self) -> None:
        changed = deepcopy(self.episode)
        changed["query"]["y"] = 1
        with self.assertRaises(ValueError):
            validate_episode(changed)
        stream = MarketStream(self.bank, self.sources, pd.DatetimeIndex(self.history["Datetime"]))
        with self.assertRaises(ValueError):
            stream.advance("2025-01-02")

    def test_historical_prefix_unknown_and_frozen_models_obey_cutoffs(self) -> None:
        timeline = RegimeTimeline(self.history, detector_factory=FakeDetector)
        early = timeline.task(7)
        self.assertEqual(early["name"], "UNKNOWN")
        self.assertEqual(early["reason"], "INSUFFICIENT_REGIME_HISTORY")
        known = timeline.task(8)
        self.assertEqual(known["model_training_end_date"], known["as_of_date"])
        proof = timeline.query(self.query)
        self.assertEqual(proof["model_fit_cutoff"], "2020-12-31")
        self.assertLessEqual(proof["model_training_end_date"], "2020-12-31")
        before = timeline.artifacts()
        timeline.query(str(self.history["Datetime"].iloc[1000].date()))
        self.assertEqual(before, timeline.artifacts())

    def test_fit_errors_are_not_downgraded_to_unknown(self) -> None:
        class Broken(FakeDetector):
            """Lỗi số học giả để kiểm không bị che bằng cold-start."""
            def fit(self, frame: pd.DataFrame) -> FakeDetector:
                raise ValueError("Lỗi fit kiểm thử")
        timeline = RegimeTimeline(self.history, detector_factory=Broken)
        with self.assertRaisesRegex(ValueError, "Lỗi fit"):
            timeline.task(8)

    def test_regime_parameters_cannot_change_during_inference(self) -> None:
        class Mutating(FakeDetector):
            """Giả lập inference âm thầm đổi metadata đã fit để kiểm freeze guard."""
            def classify_regime(self, frame: pd.DataFrame, date: str) -> dict:
                result = super().classify_regime(frame, date)
                self.metadata["train_end_date"] = date
                return result
        timeline = RegimeTimeline(self.history, detector_factory=Mutating)
        with self.assertRaisesRegex(ValueError, "bị đổi"):
            timeline.query(self.query)

    def test_stream_incremental_equals_cold_replay_and_hides_equal_exit(self) -> None:
        small, sources, history = setup(periods=150)
        initial = deepcopy(small)
        initial["records"] = [row for row in small["records"] if row["calendar_index"] < 60]
        calendar = pd.DatetimeIndex(history["Datetime"])
        first = MarketStream(initial, sources, calendar)
        q1, q2 = str(calendar[100].date()), str(calendar[130].date())
        first.advance(q1)
        incremental = first.advance(q2)
        cold = MarketStream(initial, sources, calendar).advance(q2)
        self.assertEqual(incremental, cold)
        self.assertTrue(all(row["exit_date"] < q2 for row in cold))
        self.assertEqual(incremental, first.advance(q2))
        with self.assertRaises(ValueError):
            first.advance(q1)


if __name__ == "__main__":
    unittest.main()
