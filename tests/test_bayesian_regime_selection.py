"""Kiểm bộ chọn cùng regime trên pool PIT và ranking tín hiệu đã khóa."""

import copy
import json
import unittest
from unittest.mock import patch

from core.backtest_engine import compute_round_trip_net_return
from core.bayesian_memory import read_json
from core.bayesian_retriever import ROOT
import test_bayesian_retriever as fixtures


class RegimeSelectionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.BayesianRetrieverFoundationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def select(self, retriever, **updates):
        return retriever.select_prior_tasks(**self.fixture.query(mode="bayesian_regime", **updates))

    def ranking_fixture(self):
        """Tạo giá/nhãn hợp lệ với quan hệ score/exit/ID của ví dụ A,B,C,D."""
        query = {"trend": "BULLISH", "pattern": "BULLISH", "alpha_consensus": "BEARISH",
                 "indicator_consensus": "NEUTRAL", "sentiment": "NEUTRAL"}
        rows = [self.fixture.record("FPT", 0, "BULL"), self.fixture.record("FPT", 3, "BEAR"),
                self.fixture.record("MWG", 3, "BULL"), self.fixture.record("FPT", 6, "BULL")]
        for i, row in enumerate(rows):
            row["agent_signals"] = {**query, "pattern": "BEARISH" if i == 3 else "BULLISH"}
        self.fixture.rows = rows
        self.fixture.publish_fixture()
        return query, {name: row["episode_id"] for name, row in zip("ABCD", rows)}

    def test_all_four_regimes_use_matching_population_and_native_scores(self):
        self.fixture.rows[2]["regime"] = "CONSOLIDATION"
        self.fixture.rows.append(self.fixture.record("FPT", 6, "CHOPPY"))
        self.fixture.publish_fixture()
        retriever = self.fixture.create()
        for regime in ("BULL", "BEAR", "CHOPPY", "CONSOLIDATION"):
            result = self.select(retriever, current_regime=regime, scope="pooled")
            expected = [r for r in self.fixture.rows if r["regime"] == regime]
            self.assertEqual(result["tasks"], expected)
            self.assertEqual(result["regime_population"], expected)
            meta = result["metadata"]
            self.assertEqual((meta["eligible_count"], meta["matched_regime_count"], meta["candidate_count"]), (4, 1, 1))
            self.assertEqual((meta["status"], meta["reason"]), ("partial", "insufficient_candidates"))
            self.assertIsNone(meta["effective_seed"])
            self.assertEqual(meta["selected_scores"], [{"episode_id": expected[0]["episode_id"], "score": 1.0}])
            self.assertIs(type(meta["selected_scores"][0]["score"]), float)
            json.dumps(result, allow_nan=False)
        missing_symbol = self.select(retriever, current_regime="CONSOLIDATION")
        self.assertEqual(missing_symbol["tasks"], [])
        self.assertEqual(missing_symbol["metadata"]["reason"], "no_matching_regime")
        self.assertEqual(missing_symbol["metadata"]["eligible_count"], 3)

    def test_frozen_ranking_differs_from_similarity_only_by_regime_filter(self):
        signals, identifiers = self.ranking_fixture()
        retriever = self.fixture.create()
        query = self.fixture.query(current_signals=signals, scope="pooled")
        bayesian = retriever.select_prior_tasks(**query)
        similarity = retriever.select_prior_tasks(**{**query, "mode": "similarity"})
        reference = read_json(ROOT / "docs/plan/week3/selection_policy_review.json")["reference_fixture"]["rankings"]
        for mode, result in (("bayesian_regime", bayesian), ("similarity", similarity)):
            self.assertEqual(result["metadata"]["selected_ids"], [identifiers[name] for name in reference[mode]])
        self.assertEqual([item["score"] for item in bayesian["metadata"]["selected_scores"]], [1.0, 1.0, 0.75])
        self.assertEqual(bayesian["metadata"]["candidate_count"], 3)
        self.assertEqual(similarity["metadata"]["candidate_count"], 4)
        self.assertEqual(bayesian["regime_population"], similarity["regime_population"])
        self.fixture.rows.reverse()
        self.fixture.publish_fixture()
        reordered = self.fixture.create().select_prior_tasks(**query)
        self.assertEqual(reordered["tasks"], bayesian["tasks"])
        self.assertEqual(reordered["metadata"], bayesian["metadata"] | {"bank_sha256": reordered["metadata"]["bank_sha256"]})

    def test_empty_pool_and_missing_regime_have_distinct_reasons_without_fallback(self):
        retriever = self.fixture.create()
        empty = self.select(retriever, as_of_date="2020-01-06")
        self.assertEqual((empty["metadata"]["status"], empty["metadata"]["reason"]), ("empty", "no_eligible_history"))
        self.assertEqual(empty["metadata"]["eligible_count"], 0)
        missing = self.select(retriever, current_regime="CHOPPY", scope="pooled")
        self.assertEqual((missing["metadata"]["status"], missing["metadata"]["reason"]), ("empty", "no_matching_regime"))
        self.assertEqual((missing["metadata"]["eligible_count"], missing["metadata"]["matched_regime_count"], missing["metadata"]["candidate_count"]), (3, 0, 0))
        self.assertEqual((missing["tasks"], missing["regime_population"], missing["metadata"]["selected_scores"]), ([], [], []))

    def test_k_scope_and_population_counts_do_not_fill_from_other_symbols_or_regimes(self):
        retriever = self.fixture.create()
        for k in (1, 2, 3):
            same = self.select(retriever, k=k)
            pooled = self.select(retriever, k=k, scope="pooled")
            self.assertEqual(len(same["tasks"]), 1)
            self.assertEqual(len(pooled["tasks"]), min(k, 2))
            self.assertEqual(same["metadata"]["status"], "complete" if k == 1 else "partial")
            self.assertEqual(pooled["metadata"]["status"], "partial" if k == 3 else "complete")
            self.assertEqual(len(pooled["regime_population"]), 2)
            self.assertEqual(pooled["metadata"]["matched_regime_count"], 2)
            self.assertTrue(all(r["regime"] == "BULL" and r["symbol"] == "FPT" for r in same["tasks"]))
        opposite = {"trend": "BEARISH", "pattern": "BULLISH", "alpha_consensus": "BULLISH",
                    "indicator_consensus": "BULLISH", "sentiment": "POSITIVE"}
        zero = self.select(retriever, current_signals=opposite)
        self.assertEqual(zero["metadata"]["selected_scores"][0]["score"], 0.0)
        self.assertEqual(len(zero["tasks"]), 1)

    def test_disabled_and_invalid_context_still_follow_query_validation(self):
        retriever = self.fixture.create()
        with patch.object(retriever._memory, "eligible", side_effect=AssertionError("Tạo pool K=0")):
            result = self.select(retriever, k=0, current_signals=None)
        self.assertEqual(result["metadata"]["status"], "disabled")
        self.assertIsNone(result["metadata"]["candidate_count"])
        for update in ({"current_regime": None}, {"current_regime": "UNKNOWN"},
                       {"current_signals": None}, {"current_signals": {"trend": "BULLISH"}}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                self.select(retriever, **update)
        with self.assertRaises(ValueError):
            self.select(retriever, k=0, current_regime="UNKNOWN")

    def test_valid_outcome_change_cannot_prefer_winners_or_change_scores(self):
        signals, _ = self.ranking_fixture()
        query = self.fixture.query(current_signals=signals, scope="pooled")
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
        self.assertTrue(all(r["outcome"]["result"] == "WIN_IF_LONG" for r in after["tasks"]))
        self.assertNotEqual(before["metadata"]["bank_sha256"], after["metadata"]["bank_sha256"])

    def test_copies_query_order_seed_and_no_hot_query_io(self):
        retriever = self.fixture.create()
        query = self.fixture.query(scope="pooled")
        original = copy.deepcopy(query)
        with patch("core.bayesian_retriever.read_json", side_effect=AssertionError("Đọc JSON")), \
             patch("core.bayesian_memory.read_json", side_effect=AssertionError("Đọc JSON")), \
             patch("pandas.read_csv", side_effect=AssertionError("Đọc CSV")), \
             patch.object(retriever._memory, "_execution_loader", side_effect=AssertionError("Đọc giá")):
            expected = retriever.select_prior_tasks(**query)
            mutated = retriever.select_prior_tasks(**query)
            mutated["tasks"][0]["agent_signals"]["trend"] = "BEARISH"
            mutated["metadata"]["selected_scores"].clear()
            self.select(retriever, current_regime="BEAR", as_of_date="2020-01-07")
            self.assertEqual(retriever.select_prior_tasks(**query), expected)
            reseeded = retriever.select_prior_tasks(**{**query, "seed": 123})
            self.assertEqual(reseeded["tasks"], expected["tasks"])
            self.assertEqual(reseeded["metadata"]["selected_scores"], expected["metadata"]["selected_scores"])
        self.assertEqual(query, original)
        self.assertEqual(mutated["regime_population"], expected["regime_population"])

    def test_valid_future_matching_history_cannot_change_old_selection(self):
        query = self.fixture.query(as_of_date="2020-01-07", scope="pooled", current_regime="BEAR")
        before = self.fixture.create().select_prior_tasks(**query)
        self.fixture.rows.append(self.fixture.record("FPT", 6, "BEAR"))
        self.fixture.publish_fixture()
        after = self.fixture.create().select_prior_tasks(**query)
        for key in ("selected_ids", "selected_scores", "candidate_count", "reason"):
            self.assertEqual(before["metadata"][key], after["metadata"][key])
        self.assertEqual(after["metadata"]["reason"], "no_matching_regime")

    def test_postconditions_reject_other_regime_duplicate_or_excess_selection(self):
        retriever = self.fixture.create()
        pools = [[self.fixture.rows[1]], [self.fixture.rows[2]],
                 [self.fixture.rows[0], self.fixture.rows[0]]]
        for pool in pools:
            with patch.object(retriever, "_select_similarity", return_value=(pool, {})), self.assertRaises(ValueError):
                self.select(retriever)
        with patch.object(retriever, "_select_similarity", return_value=(
                [self.fixture.rows[0], self.fixture.rows[2]], {})), self.assertRaises(ValueError):
            self.select(retriever, scope="pooled", k=1)


if __name__ == "__main__":
    unittest.main()
