"""Kiểm Recent/Random, seed đóng băng, thứ tự, thiếu mẫu và bản sao kết quả."""

import copy
import json
import random
import unittest
from unittest.mock import patch

from core.bayesian_memory import read_json
from core.bayesian_retriever import BayesianPriorRetriever, ROOT
import test_bayesian_retriever as fixtures


class RecentRandomSelectionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.BayesianRetrieverFoundationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def select(self, retriever, **updates):
        return retriever.select_prior_tasks(**self.fixture.query(**updates))

    def test_recent_tie_break_and_reordered_bank(self):
        first = self.select(self.fixture.create(), mode="recent", scope="pooled")
        expected = [self.fixture.rows[i]["episode_id"] for i in (1, 0, 2)]
        self.assertEqual(first["metadata"]["selected_ids"], expected)
        self.fixture.rows.reverse()
        self.fixture.publish_fixture()
        second = self.select(self.fixture.create(), mode="recent", scope="pooled")
        self.assertEqual(second["metadata"]["selected_ids"], expected)
        self.assertTrue(all(item["score"] is None for item in second["metadata"]["selected_scores"]))

    def test_random_matches_frozen_reference_digest_and_draw(self):
        reference = read_json(ROOT / "docs/week3/selection_policy_review.json")["reference_fixture"]
        payload = reference["random_seed_payload"]
        candidates = [{"episode_id": name} for name in ("D", "C", "B", "A")]
        selected, digest = BayesianPriorRetriever._select_random(candidates, 3, payload)
        self.assertEqual(digest, reference["random_effective_seed"])
        self.assertEqual([r["episode_id"] for r in selected], reference["random_ids"])

    def test_random_repeats_across_query_order_and_preserves_global_rng(self):
        retriever = self.fixture.create()
        state = random.getstate()
        first = self.select(retriever, mode="random", scope="pooled")
        self.select(retriever, mode="random", scope="pooled", seed=123)
        self.select(retriever, mode="random", as_of_date="2020-01-03")
        self.select(retriever, mode="recent")
        second = self.select(retriever, mode="random", scope="pooled")
        self.assertEqual(first, second)
        self.assertEqual(random.getstate(), state)
        self.assertEqual(len(set(first["metadata"]["selected_ids"])), 3)
        self.fixture.rows.reverse()
        self.fixture.publish_fixture()
        reordered = self.select(self.fixture.create(), mode="random", scope="pooled")
        self.assertEqual(reordered["metadata"]["selected_ids"], first["metadata"]["selected_ids"])
        self.assertEqual(reordered["metadata"]["effective_seed"], first["metadata"]["effective_seed"])

    def test_empty_partial_complete_and_disabled_metadata(self):
        retriever = self.fixture.create()
        for mode in ("recent", "random"):
            for k in (1, 2, 3):
                result = self.select(retriever, mode=mode, k=k)
                self.assertEqual(len(result["tasks"]), min(k, 2))
                self.assertEqual(result["metadata"]["status"], "partial" if k == 3 else "complete")
                self.assertEqual(result["metadata"]["reason"], "insufficient_candidates" if k == 3 else None)
                self.assertTrue(all(r["symbol"] == "FPT" for r in result["tasks"]))
            empty = self.select(retriever, mode=mode, as_of_date="2020-01-06")
            self.assertEqual(empty["metadata"]["status"], "empty")
            self.assertEqual(empty["metadata"]["reason"], "no_eligible_history")
            self.assertEqual(empty["metadata"]["candidate_count"], 0)
            if mode == "random":
                self.assertRegex(empty["metadata"]["effective_seed"], r"^[0-9a-f]{64}$")
            else:
                self.assertIsNone(empty["metadata"]["effective_seed"])
            disabled = self.select(retriever, mode=mode, k=0, current_signals=None)
            self.assertEqual(disabled["metadata"]["status"], "disabled")
            self.assertIsNone(disabled["metadata"]["effective_seed"])
            self.assertIsNone(disabled["metadata"]["candidate_count"])
            json.dumps(result, allow_nan=False)

    def test_selected_population_and_input_remain_independent_without_io(self):
        retriever = self.fixture.create()
        query = self.fixture.query(mode="random", scope="pooled")
        before = copy.deepcopy(query)
        with patch("core.bayesian_retriever.read_json", side_effect=AssertionError("Đọc JSON")), \
             patch.object(retriever._memory, "_execution_loader", side_effect=AssertionError("Đọc giá")):
            result = retriever.select_prior_tasks(**query)
            result["tasks"][0]["outcome"]["net_return_pct"] = 999
            result["metadata"]["selected_ids"].clear()
            fresh = retriever.select_prior_tasks(**query)
        self.assertEqual(query, before)
        self.assertTrue(all(r["outcome"]["net_return_pct"] != 999 for r in fresh["tasks"]))
        self.assertTrue(all(r["outcome"]["net_return_pct"] != 999 for r in result["regime_population"]))

    def test_future_history_and_query_regime_signals_do_not_change_random_draw(self):
        old_query = self.fixture.query(mode="random", as_of_date="2020-01-07", scope="pooled")
        before = self.fixture.create().select_prior_tasks(**old_query)
        self.fixture.rows.append(self.fixture.record("FPT", 6, "BULL"))
        self.fixture.publish_fixture()
        retriever = self.fixture.create()
        after = retriever.select_prior_tasks(**old_query)
        changed_context = retriever.select_prior_tasks(**{**old_query, "current_regime": "BEAR",
            "current_signals": {**old_query["current_signals"], "trend": "BEARISH"}})
        for other in (after, changed_context):
            self.assertEqual(before["metadata"]["selected_ids"], other["metadata"]["selected_ids"])
            self.assertEqual(before["metadata"]["effective_seed"], other["metadata"]["effective_seed"])
        self.assertNotEqual(before["metadata"]["bank_sha256"], after["metadata"]["bank_sha256"])

    def test_selector_corruption_fails_postconditions(self):
        retriever = self.fixture.create()
        for selected in ([self.fixture.rows[0], self.fixture.rows[0]], [self.fixture.rows[1]]):
            with patch.object(retriever, "_select_recent", return_value=selected), self.assertRaises(ValueError):
                self.select(retriever, mode="recent", as_of_date="2020-01-07")


if __name__ == "__main__":
    unittest.main()
