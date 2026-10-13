"""Oracle disagreement/prior-off/ablation và trace, không dùng LLM judge."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from core.paired_candidate_report import comparison_pairs, paired_candidate_report, read_report
from core.prior_disagreement_analysis import C3_BRANCHES, prior_analysis
from core.research_cohort import save_envelope
from test_paired_candidate_report import report_fixture


def set_action(point: dict, name: str, action: str) -> None:
    """Đổi action fixture và nhãn execution nhất quán, không đổi economic label."""
    point["branches"][name]["decision"]["action"] = action
    point["evaluation"]["branches"][name] = {
        "correct": (action == "LONG") == (point["evaluation"]["actual_direction"] == "UP"),
        "executed_action": "BUY_SELL" if action == "LONG" else "CASH",
        "cycle_net_return": point["evaluation"]["net_return_long"] if action == "LONG" else 0.}


def turn_off(point: dict, name: str) -> None:
    """Giữ retrieved IDs nhưng bỏ nội dung thực hiển thị và contract C3."""
    point["report_context"]["prior"][name].update(visible_metric_ids=[], visible_example_ids=[],
        decision_contract_version="decision_legacy_v1", prior_use=None)


class PriorDisagreementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan, self.points, self.binding = report_fixture()
        self.rows = self.points["FPT"]
        self.matrix = list(self.rows[0]["branches"])
        self.pairs = comparison_pairs(self.plan["candidate_registry"]["order"])

    def analysis(self) -> dict:
        """Chỉ thống kê action; fixture tài khoản được kiểm qua producer production."""
        return prior_analysis(self.rows, self.matrix, self.pairs)

    def test_directional_disagreement_keeps_both_directions_and_denominator(self) -> None:
        set_action(self.rows[1], "C0", "SHORT")
        set_action(self.rows[1], "original", "LONG")
        set_action(self.rows[2], "C0", "SHORT")
        pair = self.analysis()["pairs"]["C0__original"]
        self.assertEqual(len(self.analysis()["pairs"]), 19)
        self.assertEqual(pair["action_counts"], {"LONG_LONG":0,"LONG_CASH":1,"CASH_LONG":1,"CASH_CASH":1})
        self.assertEqual(pair["disagreement"], {"numerator":2,"denominator":3,"value":2/3,"reason":None})
        self.assertEqual(pair["point_ids"], [p["point_id"] for p in self.rows])

    def test_prior_off_intersection_ignores_retrieval_and_unknown(self) -> None:
        turn_off(self.rows[0], "C0")
        turn_off(self.rows[0], "C1")
        turn_off(self.rows[1], "C1")
        self.rows[2]["branches"]["C1"] = {"status":"unknown","decision":None}
        analysis = self.analysis()
        original = analysis["pairs"]["C1__original"]["prior_off"]
        self.assertEqual(original["count"], 2)
        self.assertEqual(original["required_off_branches"], ["C1"])
        pair = analysis["pairs"]["C1__C0"]
        self.assertEqual(pair["count"], 2)
        self.assertEqual(pair["prior_off"]["count"], 1)
        self.assertEqual(pair["prior_off"]["required_off_branches"], ["C1","C0"])
        self.assertIn("unknown", pair["excluded"][0]["reasons"][0])
        self.assertEqual(analysis["branches"]["C1"]["prior_off"]["cash_count"], 2)
        self.assertTrue(self.rows[0]["report_context"]["prior"]["C1"]["retrieved_ids"])

    def test_ready_intersection_rebuilds_account_on_own_dates(self) -> None:
        for point in self.rows:
            for name in C3_BRANCHES:
                set_action(point,name,"LONG")
                if point is self.rows[1]:
                    point["report_context"]["prior"][name]["stats_ready"] = False
        report = paired_candidate_report(self.plan,self.points,self.binding)
        analysis = report["stocks"]["FPT"]["prior_analysis"]
        full, ready = (analysis["ablation"][key] for key in ("global","stats_examples_ready"))
        self.assertEqual((full["count"],ready["count"]), (3,2))
        self.assertEqual(ready["point_ids"], [self.rows[i]["point_id"] for i in (0,2)])
        self.assertAlmostEqual(full["metrics"]["C3"]["account_metrics"]["total_return_pct"],5.6)
        self.assertAlmostEqual(ready["metrics"]["C3"]["account_metrics"]["total_return_pct"],32.)
        self.assertEqual(report["prior_analysis"]["account_scope"], "COUNTS_ONLY_NO_POOLED_ACCOUNT")
        self.assertNotIn("metrics", report["prior_analysis"]["ablation"]["global"])

    def test_empty_ready_and_regime_keep_null_support(self) -> None:
        for point in self.rows:
            for name in C3_BRANCHES:
                point["report_context"]["prior"][name]["examples_ready"] = False
        report = paired_candidate_report(self.plan,self.points,self.binding)
        ready = report["stocks"]["FPT"]["prior_analysis"]["ablation"]["stats_examples_ready"]
        self.assertEqual(ready["status"],"NO_SUPPORT")
        self.assertIsNone(ready["metrics"]["C3"]["account_metrics"])
        empty = report["stocks"]["FPT"]["regimes"]["BEAR"]["prior_analysis"]
        self.assertEqual(empty["pairs"]["C3__original"]["disagreement"]["reason"],"NO_SUPPORT")

    def test_adverse_uses_full_precision_visible_ready_posterior_only(self) -> None:
        means = (.4999999999, .5, .5000000001)
        for point,mean in zip(self.rows,means):
            view = point["report_context"]["prior"]["C0"]
            view["metric_details"]["win_rate_long"]["posterior_mean"] = mean
            view["metric_details"]["bull_trap_rate"] = {"ready":True,"posterior_mean":.9,
                "support_count":8,"credible_interval":{"lower":.7,"upper":.99}}
        branch = self.analysis()["branches"]["C0"]
        self.assertEqual(branch["adverse_point_ids"], [self.rows[0]["point_id"]])
        self.assertEqual(branch["long_on_adverse"]["value"],1.)
        self.assertEqual(branch["adverse_on_observed"]["denominator"],3)
        self.assertIsNone(branch["cases"][0]["metrics"]["bull_trap_rate"]["adverse"])
        for index in (1,2):
            view = self.rows[index]["report_context"]["prior"]["C0"]
            view["visible_metric_ids"].append("bull_trap_rate")
            view["metric_details"]["bull_trap_rate"]["posterior_mean"] = .5 if index == 1 else .5000000001
        self.rows[0]["report_context"]["prior"]["C0"]["metric_details"]["win_rate_long"]["ready"] = False
        branch = self.analysis()["branches"]["C0"]
        self.assertEqual(branch["adverse_point_ids"], [self.rows[2]["point_id"]])
        self.assertEqual(branch["cases"][2]["metrics"]["bull_trap_rate"]["support_count"],8)
        self.rows[2]["report_context"]["prior"]["C0"]["metric_details"]["bull_trap_rate"]["posterior_mean"] = None
        self.assertEqual(self.analysis()["branches"]["C0"]["long_on_adverse"]["reason"],"NO_SUPPORT")

    def test_all_symbols_dates_and_both_economic_outcomes_are_retained(self) -> None:
        for rows in self.points.values():
            for point in rows:
                point["report_context"]["prior"]["C0"]["metric_details"]["win_rate_long"]["posterior_mean"] = .49
        report = paired_candidate_report(self.plan,self.points,self.binding)
        branch = report["prior_analysis"]["branches"]["C0"]
        self.assertEqual(branch["long_on_adverse"]["denominator"],12)
        self.assertEqual({c["symbol"] for c in branch["cases"]}, set(self.points))
        self.assertEqual({c["economic_outcome"]["actual_direction"] for c in branch["cases"]}, {"UP","DOWN"})
        self.assertEqual(len({c["as_of_date"] for c in branch["cases"]}),3)
        self.assertEqual({c["correct"] for c in branch["cases"]}, {True,False})
        json.dumps(report,allow_nan=False)

    def test_stats_only_exposure_uses_conditional_support_and_valid_self_report(self) -> None:
        for point in self.rows:
            view = point["report_context"]["prior"]["C3_stats_only"]
            view["visible_example_ids"] = []
            item = view["metric_details"]["win_rate_long"]
            item.pop("support_count")
            item.update(posterior_mean=.49, raw_counts={"conditional":{"support_count":5},
                "population":{"support_count":40}})
            view["prior_use"].update(metric_ids=["win_rate_long"],assessment="CONFLICTS")
        set_action(self.rows[0],"C3_stats_only","LONG")
        branch = self.analysis()["branches"]["C3_stats_only"]
        self.assertEqual(branch["prior_off"]["count"],0)
        self.assertEqual(branch["long_on_adverse"]["value"],1/3)
        self.assertEqual(branch["assessment_counts"],{"CONFLICTS":3})
        self.assertEqual(branch["cases"][0]["metrics"]["win_rate_long"]["support_count"],5)
        self.assertEqual(branch["cases"][0]["visible_example_ids"],[])

    def test_trace_missing_hidden_duplicate_or_inconsistent_ids_fail_closed(self) -> None:
        original = deepcopy(self.rows)
        mutations = [lambda v:v.update(prior_use=None),
            lambda v:v["prior_use"].update(metric_ids=["bull_trap_rate"],assessment="CONFLICTS"),
            lambda v:v["prior_use"].update(metric_ids=["win_rate_long"]*2,assessment="SUPPORTS"),
            lambda v:v["prior_use"].update(assessment="MIXED"),
            lambda v:v["prior_use"].update(reason=" ")]
        for mutate in mutations:
            self.rows = deepcopy(original)
            mutate(self.rows[0]["report_context"]["prior"]["C3"])
            with self.assertRaises(ValueError):
                self.analysis()
        self.rows = original
        branch = self.analysis()["branches"]["C3"]
        self.assertEqual(branch["trace_validity"]["value"],1.)
        self.assertEqual(branch["assessment_counts"],{"NOT_USED":3})
        self.assertEqual(self.analysis()["branches"]["C0"]["trace_not_applicable_count"],3)

    def test_same_base_readiness_and_active_contract_are_required(self) -> None:
        original = deepcopy(self.rows)
        mutations = [lambda v:v.update(base_evidence_sha256="different"),
            lambda v:v.update(stats_ready=False),
            lambda v:v.update(decision_contract_version="decision_legacy_v1",prior_use=None)]
        for mutate in mutations:
            self.rows = deepcopy(original)
            mutate(self.rows[0]["report_context"]["prior"]["C3_stats_only"])
            with self.assertRaises(ValueError):
                self.analysis()

    def test_rehashed_analysis_mutations_fail_semantic_verifier(self) -> None:
        expected = paired_candidate_report(self.plan,self.points,self.binding)
        mutations = [lambda a:a["pairs"]["C0__original"]["disagreement"].update(value=0.),
            lambda a:a["ablation"]["stats_examples_ready"]["point_ids"].reverse(),
            lambda a:a["branches"]["C3"]["cases"][0]["trace"]["prior_use"].update(assessment="SUPPORTS"),
            lambda a:a["branches"]["C0"]["cases"][0]["metrics"]["win_rate_long"].update(posterior_mean=.01)]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"report.json"
            save_envelope(path,expected)
            original = path.read_bytes()
            self.assertEqual(read_report(path,expected),expected)
            self.assertEqual(path.read_bytes(),original)
            for mutate in mutations:
                report = deepcopy(expected)
                mutate(report["prior_analysis"])
                save_envelope(path,report)
                with self.assertRaises(ValueError):
                    read_report(path,expected)
