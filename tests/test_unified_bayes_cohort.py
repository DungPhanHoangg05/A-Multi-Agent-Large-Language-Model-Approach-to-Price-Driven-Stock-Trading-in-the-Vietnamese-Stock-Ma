"""Producer/run/resume/report U-BICL với schema riêng, engine và HTTP mock thật."""

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from core.backtest_engine import compute_round_trip_net_return
from core.historical_signals import digest
from core.research_cohort import read_envelope, save_envelope
from core.unified_bayes_cohort import CohortRun, numeric_decision, preflight
from core.unified_bayes_reports import read_report, write_report
from core.unified_bayes_source import prepare_plan, repeat_sample
from unified_context_test_support import dense_inputs, make_context
from unified_execution_test_support import ExecutionFixture, MODELS
from unified_cohort_test_support import make_cohort


class UnifiedCohortTests(unittest.TestCase):
    """Không có kết quả LLM thực nghiệm; toàn luồng kernel/source/report vẫn production."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.inputs = dense_inputs()
        cls.context = make_context(cls.inputs)

    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.fx = ExecutionFixture(Path(temp.name), self.context, self.inputs)
        self.addCleanup(self.fx.close)
        self.cohort = make_cohort(self.fx)
        self.plan = self.cohort.plan(self.fx.llm)

    def run_handle(self, create=True):
        return CohortRun(self.cohort, self.plan, self.fx.llm, self.fx.root / "cohort", self.fx.pacer.path, create=create)

    def test_prepare_loader_idempotent_and_plan_contains_no_query_payoff(self) -> None:
        path = self.fx.root / "plan.json"
        prepare_plan(self.cohort, path, self.fx.llm)
        raw = path.read_bytes()
        self.cohort.read_plan(path, self.fx.llm)
        prepare_plan(self.cohort, path, self.fx.llm)
        self.assertEqual(raw, path.read_bytes())
        self.assertEqual(self.fx.calls, [])
        self.assertEqual(self.fx.evaluations, [])
        self.assertEqual(len(self.plan["schedule"]), 16)
        self.assertEqual(len(self.plan["repeat_sample"]), 4)
        for request in self.plan["requests"].values():
            self.assertNotIn("evaluation", request)
            self.assertNotIn("outcome", request["source_proof"])

    def test_initialize_is_planned_without_http_or_target_evaluation(self) -> None:
        run = self.run_handle()
        result = run.report()
        self.assertEqual(self.fx.calls, [])
        self.assertEqual(self.fx.evaluations, [])
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertIsNone(result["primary"]["equal_weight_delta_return_pp"]["U_full__Original"])
        self.assertEqual(result["telemetry"]["http_attempt_count"], 0)
        self.assertIsNone(result["telemetry"]["total_tokens"]["sum"])

    def test_primary_engine_support_and_repeat_keeps_primary_unchanged(self) -> None:
        run = self.run_handle()
        result = run.run()
        self.assertEqual(result["primary"]["status"], "COMPLETE")
        self.assertEqual(result["repeats"]["status"], "INCOMPLETE")
        for row in result["points"][:4]:
            e = row["evaluation"]
            self.assertEqual(e["net_return_long"], compute_round_trip_net_return(e["entry_open"], e["exit_close"]))
            self.assertEqual(e["entry_date"], "2023-01-09")
            self.assertEqual(e["exit_date"], "2023-01-11")
        for stock in result["primary"]["stocks"].values():
            self.assertEqual(stock["global_common_support"]["count"], 1)
            self.assertEqual(stock["metrics"]["Original"]["account_metrics"]["total_return_pct"], stock["metrics"]["U_full"]["account_metrics"]["total_return_pct"])
        primary = deepcopy(result["primary"])
        repeated = run.run(repeats=True)
        self.assertEqual(repeated["primary"], primary)
        self.assertEqual(repeated["repeats"]["status"], "COMPLETE")
        self.assertEqual(repeated["repeats"]["disagreement"]["Original"]["planned_pairs"], 12)
        self.assertEqual(set(repeated["repeats"]["original_duplicate"]["1"]["by_symbol"]), {"FPT", "MWG", "VCB", "VNM"})
        self.assertFalse(repeated["nomination_allowed"])
        calls = len(self.fx.calls)
        run.run()
        run.run(repeats=True)
        self.assertEqual(len(self.fx.calls), calls)

    def test_report_roundtrip_and_self_resealed_metric_is_rejected(self) -> None:
        run = self.run_handle()
        report = run.run()
        path = run.root / "report.json"
        write_report(path, report)
        read_report(path, run.report())
        report["primary"]["equal_weight_delta_return_pp"]["U_full__Original"] = 999.
        save_envelope(path, report)
        with self.assertRaises(ValueError):
            read_report(path, run.report())

    def test_numeric_threshold_and_missing_stats_are_offline_policy(self) -> None:
        e = next(iter(self.cohort.prepared.values())).base
        for ready, mean, action in ((True, .5, "SHORT"), (True, .5001, "LONG"), (False, .9, "SHORT")):
            value = deepcopy(e)
            value["posterior"]["gate"]["ready"] = ready
            value["posterior"]["posterior_mean"] = mean
            self.assertEqual(numeric_decision(value)["action"], action)
        self.assertEqual(self.fx.calls, [])

    def test_repeat_selects_available_strata_before_filling_missing(self) -> None:
        requests = {}
        for symbol in ("FPT", "MWG", "VCB", "VNM"):
            for day, flags in (("01", (True, True)), ("02", (True, True)), ("03", (False, False)), ("04", (False, False))):
                requests[symbol + "-2023-01-" + day] = {"u_evidence": {"posterior": {"gate": {"ready": flags[0]}}, "selection": {"gate": {"ready": flags[1]}}}}
        chosen = repeat_sample(requests)
        self.assertEqual(len(chosen), 12)
        self.assertEqual([p[4:] for p in chosen if p.startswith("FPT")], ["2023-01-01", "2023-01-02", "2023-01-03"])
        requests["FPT-2023-01-04"]["u_evidence"]["selection"]["gate"]["ready"] = True
        self.assertEqual([p[4:] for p in repeat_sample(requests) if p.startswith("FPT")], ["2023-01-01", "2023-01-03", "2023-01-04"])

    def test_partial_checkpoint_has_no_target_or_cash_fallback_and_resumes(self) -> None:
        run = self.run_handle()
        real = run.journal._invoke
        def stop(key, saved):
            if key[2] == "U_stats":
                raise OSError("Ngắt fixture")
            return real(key, saved)
        with patch.object(run.journal, "_invoke", side_effect=stop), self.assertRaises(OSError):
            run.run()
        result = run.report()
        row = result["points"][0]
        self.assertIsNone(row["evaluation"])
        self.assertIsNone(row["branches"]["U_stats"]["decision"])
        self.assertEqual(self.fx.evaluations, [])
        count = len(self.fx.calls)
        self.run_handle(create=False).run()
        self.assertGreater(len(self.fx.calls), count)

    def test_preflight_is_separate_and_complete_never_replays(self) -> None:
        root = self.fx.root / "preflight"
        first = preflight(self.cohort, self.plan, self.fx.llm, root, execute=True)
        second = preflight(self.cohort, self.plan, self.fx.llm, root)
        self.assertEqual(first, second)
        self.assertEqual(len(self.fx.calls), 1)
        self.assertEqual(self.fx.evaluations, [])
        result = self.run_handle().report()
        self.assertEqual(result["telemetry"]["http_attempt_count"], 0)

    def test_cli_offline_lifecycle_and_fixture_online_stops_before_key(self) -> None:
        from scripts import run_unified_bayes as cli
        root = self.fx.root
        source = root / "source"
        source.mkdir()
        save_envelope(source / "plan.json", {"inputs": {"signal_config": {"models": MODELS}}})
        plan, run = root / "plan.json", root / "cli_run"
        with patch.multiple(cli, ROOT=root, SOURCE="source", PLAN_PATH=plan, RUN_PATH=run, LEDGER=self.fx.pacer.path), \
             patch.object(cli, "load_source", return_value=self.cohort), patch("builtins.print"), \
             patch("dotenv.dotenv_values", side_effect=AssertionError("Đọc key")):
            def invoke(*flags):
                with patch.object(sys, "argv", ["unified", *flags]):
                    cli.main()
            invoke("--prepare")
            raw = plan.read_bytes()
            invoke()
            invoke("--dry-run")
            invoke("--initialize")
            invoke("--verify-only")
            invoke("--report")
            invoke("--verify-report")
            self.assertEqual(raw, plan.read_bytes())
            with self.assertRaises(ValueError):
                invoke("--run", "--resume")
        self.assertEqual(self.fx.calls, [])
        self.assertEqual(self.fx.evaluations, [])

    def test_preflight_cached_http_recovers_same_uuid_before_sdk_checkpoint(self) -> None:
        root = self.fx.root / "preflight_crash"
        with patch("core.unified_bayes_cohort._encode_response", side_effect=OSError("Ngắt trước checkpoint SDK")), self.assertRaises(OSError):
            preflight(self.cohort, self.plan, self.fx.llm, root, execute=True)
        uid = read_envelope(root / "preflight.json")["attempt_id"]
        recovered = preflight(self.cohort, self.plan, self.fx.llm, root, execute=True)
        self.assertEqual(recovered["attempt_id"], uid)
        self.assertEqual(len(self.fx.calls), 1)
        self.assertEqual(recovered["status"], "complete")

    def test_preflight_malformed_response_stops_without_creating_scientific_sample(self) -> None:
        self.fx.handler = lambda _: self.fx.response("{}")
        with self.assertRaises(ValueError):
            preflight(self.cohort, self.plan, self.fx.llm, self.fx.root / "bad_preflight", execute=True)
        self.assertFalse((self.fx.root / "cohort/cohort.json").exists())
        self.assertEqual(self.fx.evaluations, [])

    def test_gate_and_readiness_bind_actual_log_bytes_and_plan(self) -> None:
        from core.research_input_lock import runtime_identity
        from core.unified_bayes_contracts import sha
        from scripts.run_unified_bayes import authorize
        # Receipt/log ở đây là fixture kiểm consumer, không phải gate nghiệm thu dự án.
        plan = deepcopy(self.plan)
        plan["split"] = "development_2023_exploratory"
        checks = {}
        logs = {"compileall": "\n".join("Listing '"+p+"'..." for p in ("agents", "core", "data_manager", "scripts", "tests", "utils")),
                "unit": "Ran 1 test in 0.1s\n\nOK\n", "leakage": "Ran 1 test in 0.1s\n\nOK\n",
                "e2e": "ALL PIPELINE CHECKS SUCCESSFUL"}
        for name, content in logs.items():
            log = self.fx.root / (name + ".log")
            log.write_text(content, encoding="utf-8")
            checks[name] = {"status": "PASS", "exit_code": 0, "log": {"path": log.name, "sha256": sha(log)}}
        gates, readiness = self.fx.root / "gates.json", self.fx.root / "ready.json"
        save_envelope(gates, {"gate_version": "research_technical_gates_v1", "code_sha256": plan["code_sha256"], "runtime": runtime_identity(), "checks": checks})
        ready = {"readiness_version": "unified_bic_execution_readiness_v1", "stage": "U10_09", "plan_sha256": digest(plan),
                 "technical_gates_sha256": sha(gates), "request_lock_sha256": plan["request_lock_sha256"], "confirmation_allowed": False}
        save_envelope(readiness, ready)
        self.assertEqual(authorize(plan, gates, readiness)["readiness_sha256"], sha(readiness))
        (self.fx.root / "unit.log").write_text("FAILED", encoding="utf-8")
        with self.assertRaises(ValueError):
            authorize(plan, gates, readiness)


if __name__ == "__main__":
    unittest.main()
