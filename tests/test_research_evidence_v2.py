"""Kiểm số posterior, gate, PIT và BRPP v2 bằng kho fixture có QA thật."""

from copy import deepcopy
import json
import unittest

from core.prior_evidence_v2 import posterior_metric, retrieve_evidence, format_evidence_prefix, validate_evidence
from core.historical_signals import digest
from core.research_metrics import cycle_risk
import test_bayesian_retriever as support


class EvidenceV2Tests(unittest.TestCase):
    def setUp(self):
        self.fx = support.BayesianRetrieverFoundationTests()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.retriever = self.fx.create()

    def evidence(self, **config):
        return retrieve_evidence(self.retriever, **self.fx.query(), config=config)

    def test_posterior_known_counts_and_zero_history(self):
        metric = posterior_metric("win_rate_long", 1, 2, 1., 1.)
        self.assertEqual(metric["posterior_mean"], .5)
        self.assertAlmostEqual(metric["credible_interval"]["lower"], .094299324050246, places=12)
        empty = posterior_metric("win_rate_long", 0, 0, 1., 1.)
        self.assertIsNone(empty["posterior_mean"])
        self.assertIsNone(empty["credible_interval"])
        for a, b in ((0, 1), (1, -1), (True, 1), (float("nan"), 1)):
            with self.assertRaises(ValueError):
                posterior_metric("win_rate_long", 1, 2, a, b)

    def test_low_support_disabled_and_partial_k(self):
        low = self.evidence()
        self.assertEqual(low["reason_codes"], ["LOW_SUPPORT"])
        self.assertEqual(format_evidence_prefix(low), "")
        ready = self.evidence(min_population_count=1)
        self.assertEqual((ready["requested_k"], ready["effective_k"], ready["population_count"]), (3, 1, 1))
        self.assertLessEqual(len(format_evidence_prefix(ready)), 600)
        self.assertEqual(ready["metrics"]["win_rate_long"]["posterior_mean"], 1/3)
        self.assertEqual(self.evidence(requested_k=0)["reason_codes"], ["PRIOR_DISABLED"])
        json.dumps(ready, allow_nan=False)

    def test_pit_equal_exit_old_quality_and_corruption(self):
        empty = retrieve_evidence(self.retriever, **self.fx.query(as_of_date=self.fx.rows[0]["exit_date"]))
        self.assertEqual(empty["population_count"], 0)
        old = self.evidence(min_population_count=1, max_prior_age_days=1)
        self.assertEqual(old["reason_codes"], ["NO_QUALITY_CANDIDATE"])
        corrupt = deepcopy(self.evidence(min_population_count=1))
        corrupt["metrics"]["win_rate_long"]["posterior_mean"] = .9
        corrupt["evidence_sha256"] = digest({k:v for k,v in corrupt.items() if k != "evidence_sha256"})
        with self.assertRaises(ValueError):
            validate_evidence(corrupt)

    def test_cycle_metrics_no_annualization_cash_and_small_n(self):
        for values, reason in (([], "N_LT_2"), ([.1], "N_LT_2"), ([0., 0.], "ZERO_DENOMINATOR")):
            out = cycle_risk(values)
            self.assertIsNone(out["sharpe_cycle"])
            self.assertEqual(out["sharpe_reason"], reason)
        result = cycle_risk([.1, -.1])
        self.assertEqual(result["sharpe_cycle"], 0.)
        self.assertIsNone(result["sharpe_annualized"])
        self.assertIsNone(cycle_risk([.1, .2])["sortino_cycle"])

    def test_three_examples_caps_and_deterministic_order(self):
        fpt_rows = [self.fx.record("FPT", i, "BULL") for i in (0, 3, 6)]
        self.fx.rows = fpt_rows + [self.fx.record("MWG", 0, "BULL")]
        self.fx.publish_fixture()
        retriever = self.fx.create()
        query = self.fx.query(as_of_date="2020-02-01")
        evidence = retrieve_evidence(retriever, **query, config={"min_population_count": 1})
        self.assertEqual(evidence["effective_k"], 3)
        self.assertEqual(evidence["selected_ids"], [r["episode_id"] for r in fpt_rows[::-1]])
        prefix = format_evidence_prefix(evidence)
        self.assertLessEqual(len(prefix), 600)
        from agents.decision_agent import _insert_prior_context
        self.assertNotIn("không smoothing", _insert_prior_context("### [1] report", prefix, "vi"))


if __name__ == "__main__":
    unittest.main()
