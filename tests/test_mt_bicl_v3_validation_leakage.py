"""Kiểm cohort label-blind và oracle toàn population, future/overlap/query exclusion v3."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from core.mt_bicl_regimes import RegimeTimeline
from core.mt_bicl_stream import MarketStream
from core.mt_bicl_v3_contracts import membership_hash
from core.mt_bicl_v3_features import BucketTaskBuilder
from core.mt_bicl_v3_validation import SourceAudit
from core.mt_bicl_v3_validation_inputs import FrozenRegimes, cohort
from mt_bicl_tasks_support import FakeDetector, setup


class ValidationLeakageTests(unittest.TestCase):
    """Nguồn giả nhưng engine/feature primitive thật; không forward weights/GPU/API."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.bank, cls.sources, cls.history = setup()
        cls.query = str(cls.history["Datetime"].iloc[995].date())

    def engine(self, sources: dict | None = None, bank: dict | None = None) -> tuple:
        """Builder và oracle có cache riêng để bắt proof nguồn bị sửa."""
        sources, bank = sources or self.sources, bank or self.bank
        calendar = pd.DatetimeIndex(self.history["Datetime"])
        regimes = RegimeTimeline(self.history, detector_factory=FakeDetector)
        stream = MarketStream(bank, sources, calendar)
        builder = BucketTaskBuilder(bank, stream, regimes, {s: f for s, (f, _) in sources.items()})
        return builder, stream, regimes, SourceAudit(sources, calendar)

    def test_full_population_rank_and_closed_engine_labels_pass(self) -> None:
        builder, stream, regimes, audit = self.engine()
        episode = builder.build("FPT", self.query)
        result = audit.context(episode, stream.closed_records(), regimes)
        self.assertGreater(result["selected_labels_checked"], 0)
        self.assertTrue(all(pid[4:] < self.query for pid in audit.labels))

    def test_removed_centroid_member_cannot_self_rehash_to_smaller_population(self) -> None:
        builder, stream, regimes, audit = self.engine()
        episode = builder.build("FPT", self.query)
        task = next(task for task in episode["prior"] if len(task["centroid_fit_ids"]) > len(task["observations"]))
        excluded = next(pid for pid in task["centroid_fit_ids"] if pid not in task["selected_by_distance_ids"])
        task["centroid_fit_ids"].remove(excluded)
        task["population"] -= 1
        episode["v3"]["historical_facts"].pop(excluded)
        episode["membership_sha256"] = membership_hash(episode)
        with self.assertRaises(ValueError): audit.context(episode, stream.closed_records(), regimes)

    def test_future_prices_and_query_label_poison_do_not_affect_input_or_audit(self) -> None:
        builder, stream, regimes, audit = self.engine()
        expected = builder.build("FPT", self.query)
        audit.context(expected, stream.closed_records(), regimes)
        sources, bank = deepcopy(self.sources), deepcopy(self.bank)
        for frame, _ in sources.values():
            frame.loc[frame["Datetime"] > self.query, ["Open", "High", "Low", "Close", "Volume"]] = np.nan
        for row in bank["records"]:
            if row["episode_id"] == "FPT-"+self.query: row["outcome"] = {"y": "Cấm đọc query", "r_net": float("nan")}
        builder, stream, regimes, second = self.engine(sources, bank)
        actual = builder.build("FPT", self.query)
        self.assertEqual(actual, expected)
        second.context(actual, stream.closed_records(), regimes)
        self.assertEqual(audit.labels, second.labels)

    def test_bad_historical_y_or_future_exit_raise_instead_of_support_bypass(self) -> None:
        for mode in ("label", "exit", "vector"):
            builder, stream, regimes, audit = self.engine()
            episode = builder.build("FPT", self.query)
            row = episode["prior"][0]["observations"][0]
            if mode == "label": row.update(y=1-row["y"], r_net=-row["r_net"])
            if mode == "exit": row["exit_date"] = self.query
            if mode == "vector": row["raw"][0] += .001
            episode["membership_sha256"] = membership_hash(episode)
            with self.subTest(mode=mode), self.assertRaises(ValueError): audit.context(episode, stream.closed_records(), regimes)

    def test_cohort_keeps_missing_feature_and_ignores_outcome_values_and2025(self) -> None:
        bank = {"records": [
            {"episode_id": f"FPT-{year}-01-04", "symbol": "FPT", "as_of_date": f"{year}-01-04", "exit_date": f"{year}-01-07",
             "label_status": "AVAILABLE", "status": "EXCLUDED", "features": None, "outcome": {"y": "Không đọc", "r_net": float("nan")}}
            for year in (2021, 2022, 2025)]}
        spec = {"development": {"point_ids": ["FPT-2023-01-04"]}}
        result = cohort(bank, spec)
        self.assertEqual([r["point_id"] for r in result], ["FPT-2021-01-04", "FPT-2022-01-04", "FPT-2023-01-04"])
        changed = deepcopy(bank)
        for row in changed["records"]: row["outcome"] = None
        self.assertEqual(cohort(changed, spec), result)

    def test_frozen_timeline_rejects_fit_after2020_before_detector_access(self) -> None:
        with TemporaryDirectory() as temp:
            frozen = FrozenRegimes(self.history, {}, Path(temp))
            with patch("core.regime_detector.MarketRegimeDetector.fit", side_effect=AssertionError("Không refit")):
                with self.assertRaises(ValueError): frozen._model("2021-01-04")
                model, proof = frozen._model(str(self.history["Datetime"].iloc[40].date()))
                self.assertIsNone(model)
                self.assertEqual(proof["name"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
