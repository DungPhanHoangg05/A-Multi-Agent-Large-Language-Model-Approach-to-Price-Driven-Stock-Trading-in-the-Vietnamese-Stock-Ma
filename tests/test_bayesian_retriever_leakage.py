"""Chặn rò rỉ tương lai trong pool nền và population thống kê của retriever."""

import copy
import unittest
from unittest.mock import patch

from core.backtest_engine import compute_round_trip_net_return

import test_bayesian_retriever as fixtures


class BayesianRetrieverLeakageTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.BayesianRetrieverFoundationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_later_then_earlier_query_does_not_reuse_future_population(self):
        retriever = self.fixture.create()
        for mode in ("recent", "random", "similarity", "bayesian_regime"):
            for scope in ("same_symbol", "pooled"):
                retriever.prepare_query(**self.fixture.query(mode=mode, scope=scope))
                old = retriever.prepare_query(**self.fixture.query(
                    mode=mode, scope=scope, as_of_date="2020-01-07"))
                for key in ("eligible_tasks", "regime_population"):
                    self.assertTrue(all(r["exit_date"] < "2020-01-07" for r in old[key]))
                equal_exit = retriever.prepare_query(**self.fixture.query(
                    mode=mode, scope=scope, as_of_date=self.fixture.rows[0]["exit_date"]))
                self.assertEqual(equal_exit["eligible_tasks"], [])
                self.assertEqual(equal_exit["regime_population"], [])

    def test_future_record_or_outcome_cannot_enter_population_via_source(self):
        retriever = self.fixture.create()
        future = copy.deepcopy(self.fixture.rows[1])
        for row in (future, {**future, "outcome": {**future["outcome"], "net_return_pct": 99}}):
            with patch.object(retriever._memory, "eligible", return_value=[row]), self.assertRaises(ValueError):
                retriever.prepare_query(**self.fixture.query(as_of_date="2020-01-07"))

    def test_adding_valid_future_history_does_not_change_old_pool(self):
        before = self.fixture.create().prepare_query(**self.fixture.query(as_of_date="2020-01-07"))
        self.fixture.rows.append(self.fixture.record("FPT", 6, "BULL"))
        self.fixture.publish_fixture()
        after = self.fixture.create().prepare_query(**self.fixture.query(as_of_date="2020-01-07"))
        self.assertEqual(before["eligible_tasks"], after["eligible_tasks"])
        self.assertEqual(before["regime_population"], after["regime_population"])
        self.assertNotEqual(before["metadata"]["bank_sha256"], after["metadata"]["bank_sha256"])

    def test_all_selected_tasks_respect_equal_exit_and_earlier_query(self):
        retriever = self.fixture.create()
        for mode in ("recent", "random", "similarity", "bayesian_regime"):
            for scope in ("same_symbol", "pooled"):
                retriever.select_prior_tasks(**self.fixture.query(mode=mode, scope=scope))
                selected = retriever.select_prior_tasks(**self.fixture.query(
                    mode=mode, scope=scope, as_of_date="2020-01-07"))
                self.assertTrue(all(r["exit_date"] < "2020-01-07" for r in selected["tasks"]))
                equal = retriever.select_prior_tasks(**self.fixture.query(
                    mode=mode, scope=scope, as_of_date=self.fixture.rows[0]["exit_date"]))
                self.assertEqual(equal["tasks"], [])

    def test_bayesian_matching_future_regime_cannot_enter_selection(self):
        retriever = self.fixture.create()
        for pool in ([self.fixture.rows[1]], [self.fixture.rows[0], self.fixture.rows[1]]):
            with patch.object(retriever._memory, "eligible", return_value=pool), self.assertRaises(ValueError):
                retriever.select_prior_tasks(**self.fixture.query(
                    mode="bayesian_regime", current_regime="BEAR", as_of_date="2020-01-07"))

    def test_retrieve_statistics_equal_exit_and_later_then_earlier_queries(self):
        self.fixture.rows.append(self.fixture.record("FPT", 6, "BULL"))
        self.fixture.publish_fixture()
        retriever = self.fixture.create()
        for mode in ("recent", "random", "similarity", "bayesian_regime"):
            for scope in ("same_symbol", "pooled"):
                later = retriever.retrieve(**self.fixture.query(mode=mode, scope=scope))
                early = retriever.retrieve(**self.fixture.query(mode=mode, scope=scope, as_of_date="2020-01-07"))
                self.assertGreater(later["stats"]["population_count"], early["stats"]["population_count"])
                self.assertEqual(early["stats"]["population_count"], 1 if scope == "same_symbol" else 2)
                equal = retriever.retrieve(**self.fixture.query(
                    mode=mode, scope=scope, as_of_date=self.fixture.rows[0]["exit_date"]))
                self.assertEqual(equal["stats"]["population_count"], 0)
                self.assertTrue(all(m["rate"] is None for m in equal["stats"]["metrics"].values()))

    def test_valid_future_history_and_future_price_outcome_change_leave_old_stats_unchanged(self):
        query = self.fixture.query(as_of_date="2020-01-07", scope="pooled")
        before = self.fixture.create().retrieve(**query)
        future = self.fixture.record("FPT", 6, "BULL")
        self.fixture.rows.append(future)
        self.fixture.publish_fixture()
        added = self.fixture.create().retrieve(**query)
        self.fixture.frame.loc[9, "Close"] = 102.0
        self.fixture.frame["High"] = 103.0
        self.fixture.frame["Reference"] = self.fixture.frame["Close"].shift().fillna(100.0)
        future["outcome"] = {"actual_direction": "UP", "result": "WIN_IF_LONG", "was_bull_trap": False,
                             "net_return_pct": float(100 * compute_round_trip_net_return(100.0, 102.0))}
        self.fixture.publish_fixture()
        changed = self.fixture.create().retrieve(**query)
        for result in (added, changed):
            self.assertEqual(result["stats"], before["stats"])
            self.assertEqual(result["metadata"]["selected_ids"], before["metadata"]["selected_ids"])
            self.assertNotEqual(result["metadata"]["bank_sha256"], before["metadata"]["bank_sha256"])

    def test_statistics_guard_rejects_future_population_even_after_selection(self):
        retriever = self.fixture.create()
        selected = retriever.select_prior_tasks(**self.fixture.query(as_of_date="2020-01-07"))
        selected["regime_population"].append(self.fixture.rows[1])
        with patch.object(retriever, "select_prior_tasks", return_value=selected), self.assertRaises(ValueError):
            retriever.retrieve(**self.fixture.query(as_of_date="2020-01-07"))


if __name__ == "__main__":
    unittest.main()
