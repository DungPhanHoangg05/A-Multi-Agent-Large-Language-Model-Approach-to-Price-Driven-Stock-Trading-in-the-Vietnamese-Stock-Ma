"""Oracle độc lập cho tài khoản, common support, coverage và verifier report."""

from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
import json
import tempfile
import unittest

from core.backtest_engine import PRIOR_BRANCH_MODES, compute_round_trip_net_return
from core.candidate_cohort import registry
from core.paired_candidate_report import paired_candidate_report, read_report, verify_report
from core.prior_backtest import canonical_hash
from core.research_cohort import save_envelope


def report_fixture() -> tuple[dict, dict, dict]:
    """Ba chu kỳ có net LONG +10%, −20%, +20%; Original luôn giữ CASH."""
    names = [*PRIOR_BRANCH_MODES, *registry()["order"]]
    days = [(date(2023, 1, 2)+timedelta(days=7*i)).isoformat() for i in range(3)]
    plan = {"cohort_id": "paired-fixture", "split": "fixture", "candidate_registry": registry(),
        "symbol_cutoffs": {s:days for s in ("FPT", "MWG", "VCB", "VNM")},
        "code_sha256": {}, "runtime": {}, "price_index": {}, "inputs": {}}
    points = {}
    for symbol in plan["symbol_cutoffs"]:
        rows = []
        for day, target in zip(days, (.1, -.2, .2)):
            close = 100*(1+target)*1.0025*1.001/(.9975*.999)
            net = float(compute_round_trip_net_return(100., close))
            label = "UP" if net > 0 else "DOWN"
            branches, results, views = {}, {}, {}
            for name in names:
                action = "LONG" if name == "C0" else "SHORT"
                branches[name] = {"status": "complete", "decision": {"action": action,
                    "confidence": "Cao", "risk_reward_ratio": 1., "latency_seconds": 0.}, "error": None}
                results[name] = {"correct": (action == "LONG") == (label == "UP"),
                    "executed_action": "BUY_SELL" if action == "LONG" else "CASH", "cycle_net_return": net if action == "LONG" else 0.}
                views[name] = {"stats_ready": True, "examples_ready": True, "fallback": False,
                    "retrieved_ids": ["prior-1"], "visible_example_ids": ["prior-1"],
                    "visible_metric_ids": ["win_rate_long"], "reason_codes": [],
                    "base_evidence_sha256": "a"*64, "request_sha256": "b"*64, "prefix_sha256": "c"*64,
                    "metric_details": {"win_rate_long": {"ready": True, "posterior_mean": .5,
                        "support_count": 20, "credible_interval": {"lower": .3, "upper": .7}}},
                    "decision_contract_version": "decision_prior_use_v1" if name.startswith("C3") else "decision_legacy_v1",
                    "prior_use": {"metric_ids": [], "example_ids": [], "assessment": "NOT_USED", "reason": "Fixture."}
                        if name.startswith("C3") else None}
            rows.append({"point_id": f"{symbol}-{day}", "status": "complete",
                "context": {"symbol": symbol, "as_of_date": day},
                "source_proof": {"prices": {"snapshot_start_date": "2022-11-01"}},
                "branches": branches, "evaluation": {"entry_open": 100., "exit_close": close,
                    "entry_date": (date.fromisoformat(day)+timedelta(days=1)).isoformat(),
                    "exit_date": (date.fromisoformat(day)+timedelta(days=3)).isoformat(),
                    "net_return_long": net, "actual_direction": label, "branches": results},
                "report_context": {"regime": "BULL", "feature_status": "AVAILABLE", "feature_reasons": [], "prior": views}})
        points[symbol] = rows
    binding = {"plan_sha256": canonical_hash(plan), "registry_sha256": canonical_hash(registry()),
        "execution_mode": "offline_fixture", "code_sha256": {}, "runtime": {}, "price_index": {},
        "model": None, "sources": {}, "checkpoint_sha256": {}, "run_signature": "fixture"}
    return plan, points, binding


class PairedCandidateReportTests(unittest.TestCase):
    def test_primary_weights_stocks_equally_when_planned_counts_differ(self) -> None:
        plan, points, binding = report_fixture()
        points["FPT"] = points["FPT"][:1]
        plan["symbol_cutoffs"]["FPT"] = plan["symbol_cutoffs"]["FPT"][:1]
        binding["plan_sha256"] = canonical_hash(plan)
        report = paired_candidate_report(plan, points, binding)
        self.assertAlmostEqual(report["candidate_delta_return_pp"]["C0"], 6.7, places=10)

    def test_unobserved_readiness_is_unknown_and_all_pending_is_no_support(self) -> None:
        plan, points, binding = report_fixture()
        for rows in points.values():
            for p in rows:
                p["evaluation"] = None
                for name in p["branches"]:
                    p["branches"][name] = {"status":"planned", "decision":None, "error":None}
                    p["report_context"]["prior"][name].update(stats_ready=None, examples_ready=None,
                        visible_example_ids=[], visible_metric_ids=[], fallback=None)
        report = paired_candidate_report(plan, points, binding)
        coverage = report["stocks"]["FPT"]["coverage"]["C0"]
        self.assertEqual(coverage["readiness_unknown"], 3)
        self.assertEqual(coverage["stats_ready"], 0)
        self.assertEqual(coverage["prior_visible_count"], 0)
        self.assertEqual(coverage["visibility_on_complete"]["reason"], "NO_COMPLETE")
        self.assertIsNone(report["stocks"]["FPT"]["metrics"]["C0"]["account_metrics"])

    def test_account_equity_mdd_and_equal_stock_primary_match_numeric_oracle(self) -> None:
        plan, points, binding = report_fixture()
        before = deepcopy(points)
        report = paired_candidate_report(plan, points, binding)
        stock = report["stocks"]["FPT"]
        account = stock["metrics"]["C0"]["account_metrics"]
        self.assertAlmostEqual(account["total_return_pct"], 5.6, places=10)
        self.assertAlmostEqual(account["max_drawdown_pct"], 20., places=10)
        self.assertAlmostEqual(report["candidate_delta_return_pp"]["C0"], 5.6, places=10)
        self.assertAlmostEqual(report["candidate_delta_mdd_pp"]["C0"], 20., places=10)
        self.assertEqual(report["selection_evidence_status"], "NOT_APPLICABLE")
        self.assertEqual(len(stock["pairwise_support"]), 19)
        self.assertEqual(points, before)
        json.dumps(report, allow_nan=False)

    def test_pairwise_rebuild_uses_identical_subset_and_does_not_rescue_primary(self) -> None:
        plan, points, binding = report_fixture()
        point = points["FPT"][1]
        point["branches"]["random"] = {"status": "unknown", "decision": None, "error": None}
        point["evaluation"]["branches"].pop("random")
        report = paired_candidate_report(plan, points, binding)
        stock = report["stocks"]["FPT"]
        self.assertEqual(stock["global_common_support"]["count"], 2)
        self.assertEqual(stock["pairwise_support"]["C0__original"]["count"], 3)
        self.assertAlmostEqual(stock["metrics"]["C0"]["account_metrics"]["total_return_pct"], 32., places=10)
        self.assertAlmostEqual(stock["pairwise_support"]["C0__original"]["delta_return_pp"], 5.6, places=10)
        self.assertEqual(stock["coverage"]["random"]["unknown"], 1)
        self.assertEqual(stock["coverage"]["random"]["missing_result"], 1)
        self.assertEqual(report["primary_status"], "INCOMPLETE")
        self.assertTrue(all(v is None for v in report["candidate_delta_return_pp"].values()))

    def test_pending_failed_and_recovered_counts_partition_planned(self) -> None:
        plan, points, binding = report_fixture()
        for index, status in enumerate(("planned", "failed", "running")):
            points["FPT"][index]["branches"]["C2"] = {"status": status, "decision": None,
                "error": {"code": "FORMAT"} if status == "failed" else None}
            points["FPT"][index]["evaluation"]["branches"].pop("C2")
        report = paired_candidate_report(plan, points, binding)
        coverage = report["stocks"]["FPT"]["coverage"]["C2"]
        self.assertEqual([coverage[k] for k in ("planned", "complete", "pending", "failed", "unknown")], [3,0,1,1,1])
        self.assertEqual(coverage["error_counts"], {"FORMAT":1,"UNKNOWN_DECISION":1})

    def test_missing_class_cash_and_empty_regime_keep_distinct_null_reasons(self) -> None:
        plan, points, binding = report_fixture()
        for symbol in points:
            points[symbol] = [points[symbol][0], points[symbol][2]]
            plan["symbol_cutoffs"][symbol] = [p["context"]["as_of_date"] for p in points[symbol]]
        binding["plan_sha256"] = canonical_hash(plan)
        stock = paired_candidate_report(plan, points, binding)["stocks"]["FPT"]
        cash = stock["cash_reference"]
        self.assertEqual(cash["accuracy"], 0.)
        self.assertIsNone(cash["balanced_accuracy"])
        self.assertEqual(cash["balanced_accuracy_reason"], "MISSING_CLASS")
        self.assertEqual(cash["hit_rate_reason"], "NO_LONG")
        self.assertEqual(cash["risk"]["sharpe_reason"], "ZERO_DENOMINATOR")
        self.assertEqual(cash["account_metrics"]["total_return_pct"], 0.)
        empty = stock["regimes"]["BEAR"]
        self.assertIsNone(empty["metrics"]["C0"]["account_metrics"])
        self.assertEqual(empty["metrics"]["C0"]["support_reason"], "NO_SUPPORT")
        self.assertEqual(empty["metrics"]["C0"]["risk"]["sharpe_reason"], "N_LT_2")
        self.assertEqual(empty["coverage"]["C0"]["visibility_coverage"]["reason"], "NO_PLANNED")

    def test_stats_only_visible_metric_counts_exposure_but_retrieval_alone_does_not(self) -> None:
        plan, points, binding = report_fixture()
        for point in points["FPT"]:
            view = point["report_context"]["prior"]["C3_stats_only"]
            view["visible_example_ids"] = []
            view = point["report_context"]["prior"]["C3_examples_only"]
            view.update(visible_example_ids=[], visible_metric_ids=[], fallback=True,
                decision_contract_version="decision_legacy_v1", prior_use=None)
            for name in ("C3", "C3_stats_only", "C3_examples_only"):
                point["report_context"]["prior"][name]["examples_ready"] = False
        views = paired_candidate_report(plan, points, binding)["stocks"]["FPT"]["coverage"]
        self.assertEqual(views["C3_stats_only"]["prior_visible_count"], 3)
        self.assertEqual(views["C3_examples_only"]["prior_visible_count"], 0)
        self.assertEqual(views["C3_examples_only"]["fallback_count"], 3)

    def test_invalid_outcome_ids_nan_or_incomplete_evaluation_fail_closed(self) -> None:
        plan, points, binding = report_fixture()
        mutations = [lambda p:p["FPT"][0]["evaluation"].update(net_return_long=.9),
            lambda p:p["FPT"].append(deepcopy(p["FPT"][0])), lambda p:p["FPT"].pop(),
            lambda p:p["FPT"][0]["evaluation"].update(exit_close=float("nan")),
            lambda p:p["FPT"][0]["evaluation"]["branches"]["C0"].update(correct=False)]
        for mutate in mutations:
            changed = deepcopy(points)
            mutate(changed)
            with self.assertRaises(ValueError):
                paired_candidate_report(plan, changed, binding)

    def test_rehashed_report_edits_and_date_reordering_are_detected_read_only(self) -> None:
        plan, points, binding = report_fixture()
        expected = paired_candidate_report(plan, points, binding)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"report.json"
            save_envelope(path, expected)
            before = path.read_bytes()
            self.assertEqual(read_report(path, expected), expected)
            self.assertEqual(path.read_bytes(), before)
            mutations = [lambda r:r["stocks"]["FPT"]["global_common_support"]["dates"].reverse(),
                lambda r:r["stocks"]["FPT"]["pairwise_support"]["C0__original"].update(count=2),
                lambda r:r["stocks"]["FPT"]["metrics"]["C0"]["account_metrics"].update(total_return_pct=999.)]
            for mutate in mutations:
                changed = deepcopy(expected)
                mutate(changed)
                save_envelope(path, changed)
                with self.assertRaises(ValueError):
                    read_report(path, expected)
        legacy = {"report_version":"research_report_v3", "value":1}
        verify_report(legacy, deepcopy(legacy))
