"""Kiểm selection, packing và projection theo task/context đã khóa."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

import numpy as np

from core.mt_bicl_bank import SYMBOLS, build_dense_bank, canonical_bytes
from core.mt_bicl_prompt_limits import check_prompt_length
from core.mt_bicl_student import pack_input
from core.mt_bicl_oracle import numeric_input
from core.mt_bicl_tasks import validate_episode
from core.mt_bicl_tasks import coverage
from mt_bicl_tasks_support import builder, setup


class TaskContextTests(unittest.TestCase):
    """Đối chiếu membership và các giới hạn độc lập với learner chưa triển khai."""

    @classmethod
    def setUpClass(cls) -> None:
        """Dựng một nguồn tổng hợp, mỗi test tạo state builder mới."""
        cls.bank, cls.sources, cls.history = setup()
        cls.query = str(cls.history["Datetime"].iloc[995].date())
        cls.episode = builder(cls.bank, cls.sources, cls.history).build("FPT", cls.query)

    def test_three_tasks_eight_target_and_disjoint_intervals(self) -> None:
        e = self.episode
        self.assertEqual((e["K"], e["m"]), (3, 8))
        self.assertTrue(all(len(task["observations"]) == 8 for task in e["prior"]))
        self.assertTrue(all(task["known_regime_match"] for task in e["prior"]))
        validate_episode(e)

    def test_target_contains_latest_eight_closed_cycles_in_current_block(self) -> None:
        e = self.episode
        expected = sorted(row["episode_id"] for row in self.bank["records"]
                          if row["symbol"] == "FPT" and row["status"] == "AVAILABLE"
                          and row["block_index"] == e["query"]["block_index"] and row["exit_date"] < self.query)[-8:]
        self.assertEqual([row["episode_id"] for row in e["target"]], expected)

    def test_centroid_uses_all_closed_members_not_only_selected_eight(self) -> None:
        e = self.episode
        task = e["prior"][0]
        rows = [row for row in self.bank["records"] if row["episode_id"] in task["centroid_fit_ids"]]
        scaler = e["scaler"]
        matrix = np.clip((np.asarray([row["features"]["vector"] for row in rows])-scaler["mean"])/scaler["scale"], -4, 4)
        np.testing.assert_allclose(matrix.mean(axis=0), task["centroid"], rtol=0, atol=1e-12)
        self.assertGreater(task["population"], 8)

    def test_prior_cycle_rank_is_distance_then_recency_not_labels(self) -> None:
        e = self.episode
        task = e["prior"][0]
        rows = [r for r in self.bank["records"] if r["episode_id"] in task["centroid_fit_ids"]]
        scaler = e["scaler"]
        scored = []
        for row in rows:
            vector = np.clip((np.asarray(row["features"]["vector"])-scaler["mean"])/scaler["scale"], -4, 4)
            scored.append((float(np.linalg.norm(vector-e["query"]["model_vector"])),
                           -int(row["as_of_date"].replace("-", "")), row["episode_id"]))
        self.assertEqual([item[2] for item in sorted(scored)[:8]], task["selected_by_distance_ids"])

    def test_cold_start_with_no_prior_no_target_is_valid(self) -> None:
        bank, sources, history = setup(periods=120, late_fpt=True)
        query = str(history["Datetime"].iloc[55].date())
        e = builder(bank, sources, history).build("FPT", query)
        self.assertEqual(e["status"], "AVAILABLE")
        self.assertEqual((e["K"], e["m"]), (0, 0))
        self.assertIn("TARGET_COLD_START", e["reasons"])
        self.assertEqual(len(pack_input(numeric_input(e))["values"]), 2)



    def test_zero_distance_ties_choose_newest_tasks_and_cycles(self) -> None:
        frame = self.sources["FPT"][0].copy()
        frame[["Open", "High", "Low", "Close", "Reference"]] = 100.
        sources = {s: (frame, []) for s in SYMBOLS}
        history = frame.loc[:, ["Datetime", "Close"]]
        data = build_dense_bank(sources, self.history["Datetime"], end_date=str(history["Datetime"].iloc[-1].date()))
        result = builder(data, sources, history).build("FPT", self.query)
        block = result["query"]["block_index"]
        self.assertEqual([task["block_index"] for task in result["prior"]], [block-1, block-2, block-3])
        for task in result["prior"]:
            self.assertEqual(task["selected_by_distance_ids"], sorted(task["selected_by_distance_ids"], reverse=True))

    def test_old_prior_support_is_not_hidden_by_730_day_cap(self) -> None:
        sources = deepcopy(self.sources)
        sources["FPT"][1].extend({"exrightDate": str(date.date())} for date in self.history["Datetime"].iloc[252:945])
        data = build_dense_bank(sources, self.history["Datetime"], end_date=str(self.history["Datetime"].iloc[-1].date()))
        result = builder(data, sources, self.history).build("FPT", self.query)
        self.assertEqual(result["K"], 3)
        self.assertTrue(all(row["age_days"] > 730 for task in result["prior"] for row in task["observations"]))




    def test_prompt_exclusive_cap_and_native_json(self) -> None:
        check_prompt_length("x"*6499)
        with self.assertRaises(ValueError):
            check_prompt_length("x"*6500)
        self.assertEqual(json.loads(canonical_bytes(self.episode)), self.episode)

    def test_development_support_gate_is_not_applied_to_bank_partitions(self) -> None:
        self.assertEqual(coverage([self.episode])["development_support_gate"], "NOT_APPLICABLE")
        self.assertEqual(coverage([self.episode], development=True)["development_support_gate"], "INSUFFICIENT_CONTEXT")
