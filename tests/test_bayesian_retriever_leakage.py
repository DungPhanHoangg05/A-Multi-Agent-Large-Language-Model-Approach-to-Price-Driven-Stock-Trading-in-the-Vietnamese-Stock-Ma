"""Chặn rò rỉ tương lai trong pool nền và population thống kê của retriever."""

import copy
import unittest
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
