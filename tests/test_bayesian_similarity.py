"""Kiểm metric so khớp tín hiệu, ranking và độc lập với nhãn kinh tế."""

import copy
import json
import math
import unittest
import unicodedata
from unittest.mock import patch

from core.backtest_engine import compute_round_trip_net_return
from core.bayesian_memory import read_json
from core.bayesian_retriever import BayesianPriorRetriever, ROOT
import test_bayesian_retriever as fixtures


class SimilaritySelectionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.BayesianRetrieverFoundationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def select(self, retriever, **updates):
        return retriever.select_prior_tasks(**self.fixture.query(mode="similarity", **updates))

    def test_scores_cover_zero_partial_full_and_neutral_matches(self):
        fields = ("trend", "pattern", "alpha_consensus", "indicator_consensus")
        query = dict.fromkeys((*fields, "sentiment"), "NEUTRAL")
        for matches, expected in enumerate((0.0, 0.25, 0.5, 0.75, 1.0)):
            signals = {field: "NEUTRAL" if i < matches else "BEARISH" for i, field in enumerate(fields)}
            signals["sentiment"] = "POSITIVE"
            row = {"episode_id": "A", "exit_date": "2020-01-06", "agent_signals": signals}
            selected, scores = BayesianPriorRetriever._select_similarity([row], 3, query)
            self.assertEqual(selected, [row])
            self.assertEqual(scores, {"A": expected})
            self.assertIs(type(scores["A"]), float)
            self.assertTrue(math.isfinite(scores["A"]))

    def test_ranking_matches_frozen_reference_and_file_order_is_irrelevant(self):
        query = {"trend": "BULLISH", "pattern": "BULLISH", "alpha_consensus": "BEARISH",
                 "indicator_consensus": "NEUTRAL", "sentiment": "NEUTRAL"}
        rows = [{"episode_id": name, "exit_date": exit_date, "regime": regime,
                 "agent_signals": {**query, "pattern": "BEARISH" if name == "D" else "BULLISH"}}
                for name, exit_date, regime in (("A", "2021-01-04", "BULL"),
                    ("B", "2021-01-07", "BEAR"), ("C", "2021-01-07", "BULL"),
                    ("D", "2021-01-08", "BULL"))]
        reference = read_json(ROOT / "docs/plan/week3/selection_policy_review.json")["reference_fixture"]
        before = copy.deepcopy(rows)
        for candidates in (rows, list(reversed(rows))):
            selected, scores = BayesianPriorRetriever._select_similarity(candidates, 3, query)
            self.assertEqual([r["episode_id"] for r in selected], reference["rankings"]["similarity"])
            self.assertEqual([scores[r["episode_id"]] for r in rows], reference["scores"])
        self.assertEqual(rows, before)

    def test_aliases_nfc_sentiment_zero_weight_and_raw_signals_preserved(self):
        retriever = self.fixture.create()
        canonical = self.select(retriever, scope="pooled")
        aliases = {"trend": unicodedata.normalize("NFD", " tăng giá "), "pattern": "trung_tính",
                   "alpha_consensus": " trung tính ", "indicator_consensus": "down",
                   "sentiment": "tích cực"}
        before = copy.deepcopy(aliases)
        aliased = self.select(retriever, current_signals=aliases, scope="pooled")
        self.assertEqual(aliased, canonical)
        self.assertEqual(aliases, before)
        self.assertEqual([r["agent_signals"] for r in aliased["tasks"]],
                         [r["agent_signals"] for r in canonical["tasks"]])
        self.fixture.rows[0]["agent_signals"]["trend"] = " tăng "
        self.fixture.publish_fixture()
        raw = self.select(self.fixture.create(), scope="pooled")
        self.assertEqual(raw["metadata"]["selected_scores"], canonical["metadata"]["selected_scores"])
        self.assertEqual(next(r for r in raw["tasks"] if r["episode_id"] == self.fixture.rows[0]["episode_id"])
                         ["agent_signals"]["trend"], " tăng ")

    def test_invalid_labels_missing_signals_fail_even_for_empty_pool(self):
        retriever = self.fixture.create()
        signals = self.fixture.query()["current_signals"]
        invalid = [None, {"trend": "BULLISH"}]
        invalid += [{**signals, "trend": label} for label in ("UNKNOWN", "BULLISH/BEARISH", "xu hướng tăng")]
        invalid.append({**signals, "sentiment": "BULLISH"})
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.select(retriever, current_signals=value, as_of_date="2020-01-06")

    def test_metadata_scope_regime_independence_and_small_pools(self):
        retriever = self.fixture.create()
        for k in (1, 2, 3):
            result = self.select(retriever, k=k)
            metadata = result["metadata"]
            self.assertEqual(metadata["selected_ids"], [self.fixture.rows[i]["episode_id"] for i in (1, 0)][:k])
            self.assertEqual((metadata["eligible_count"], metadata["matched_regime_count"], metadata["candidate_count"]), (2, 1, 2))
            self.assertEqual(metadata["status"], "partial" if k == 3 else "complete")
            self.assertEqual(metadata["reason"], "insufficient_candidates" if k == 3 else None)
            self.assertIsNone(metadata["effective_seed"])
            self.assertTrue(all(r["score"] == 1.0 for r in metadata["selected_scores"]))
            json.dumps(result, allow_nan=False)
        other = self.select(retriever, current_regime="BEAR", seed=123)
        self.assertEqual(other["metadata"]["selected_ids"], result["metadata"]["selected_ids"])
        self.assertEqual(other["metadata"]["selected_scores"], result["metadata"]["selected_scores"])
        self.assertEqual(len(self.select(retriever, scope="pooled")["tasks"]), 3)
        empty = self.select(retriever, as_of_date="2020-01-06")
        self.assertEqual((empty["tasks"], empty["metadata"]["selected_scores"]), ([], []))
        self.assertEqual(empty["metadata"]["reason"], "no_eligible_history")
        with patch.object(retriever._memory, "eligible", side_effect=AssertionError("Tạo pool K=0")):
            disabled = self.select(retriever, k=0, current_signals=None)
        self.assertEqual(disabled["metadata"]["status"], "disabled")

    def test_valid_outcome_change_does_not_change_ranking_or_scores(self):
        query = self.fixture.query(mode="similarity", scope="pooled")
        before = self.fixture.create().select_prior_tasks(**query)
        self.fixture.frame["Close"] = 101.0
        self.fixture.frame["Reference"] = 101.0
        self.fixture.frame["High"] = 102.0
        net = float(100 * compute_round_trip_net_return(100.0, 101.0))
        self.assertGreater(net, 0)
        for row in self.fixture.rows:
            row["outcome"] = {"actual_direction": "UP", "net_return_pct": net,
                              "was_bull_trap": False, "result": "WIN_IF_LONG"}
        self.fixture.publish_fixture()
        after = self.fixture.create().select_prior_tasks(**query)
        for key in ("selected_ids", "selected_scores"):
            self.assertEqual(before["metadata"][key], after["metadata"][key])
        self.assertNotEqual(before["metadata"]["bank_sha256"], after["metadata"]["bank_sha256"])
        self.assertTrue(all(r["outcome"]["result"] == "WIN_IF_LONG" for r in after["tasks"]))

    def test_repeated_queries_copies_and_no_hot_query_io(self):
        retriever = self.fixture.create()
        query = self.fixture.query(mode="similarity", scope="pooled")
        before = copy.deepcopy(query)
        with patch("core.bayesian_retriever.read_json", side_effect=AssertionError("Đọc JSON")), \
             patch("core.bayesian_memory.read_json", side_effect=AssertionError("Đọc JSON")), \
             patch("pandas.read_csv", side_effect=AssertionError("Đọc CSV")), \
             patch.object(retriever._memory, "_execution_loader", side_effect=AssertionError("Đọc giá")):
            expected = retriever.select_prior_tasks(**query)
            altered = retriever.select_prior_tasks(**query)
            altered["tasks"][0]["agent_signals"]["trend"] = "BEARISH"
            altered["metadata"]["selected_scores"].clear()
            self.select(retriever, as_of_date="2020-01-07")
            self.assertEqual(retriever.select_prior_tasks(**query), expected)
        self.assertEqual(query, before)
        self.assertEqual(altered["regime_population"], expected["regime_population"])

    def test_valid_future_history_does_not_change_old_similarity(self):
        query = self.fixture.query(mode="similarity", as_of_date="2020-01-07", scope="pooled")
        before = self.fixture.create().select_prior_tasks(**query)
        self.fixture.rows.append(self.fixture.record("FPT", 6, "BULL"))
        self.fixture.publish_fixture()
        after = self.fixture.create().select_prior_tasks(**query)
        for key in ("selected_ids", "selected_scores", "candidate_count"):
            self.assertEqual(before["metadata"][key], after["metadata"][key])

    def test_corrupted_selector_is_rejected_by_postconditions(self):
        retriever = self.fixture.create()
        for selected in ([self.fixture.rows[1]], [self.fixture.rows[0], self.fixture.rows[0]]):
            with patch.object(retriever, "_select_similarity", return_value=(selected, {})), \
                 self.assertRaises(ValueError):
                self.select(retriever, as_of_date="2020-01-07")


if __name__ == "__main__":
    unittest.main()
