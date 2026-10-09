"""Cohort bốn mã fixture: paired, identity, resume, gate-off và common support."""

from copy import deepcopy
import unittest
from unittest.mock import patch
import importlib

from core.bayesian_memory import SYMBOLS
from core.prior_backtest import PriorBacktestRunner
from core.prior_evidence_v2 import normalize_evidence_config
from core.research_cohort import read_envelope, validate_plan
from core import research_cohort
import test_prior_backtest_integration as support


class ResearchCohortTests(unittest.TestCase):
    def setUp(self):
        support.PriorBacktestIntegrationTests.setUp(self)
        self.plan = {"plan_version": "research_cohort_plan_v2", "cohort_id": "fixture-four",
                     "split": "fixture", "matrix": "research_v2",
                     "symbol_cutoffs": {s: [self.cutoffs[0]] for s in sorted(SYMBOLS)},
                     "evidence_config": normalize_evidence_config(), "inputs": {"signal_config": self.adapter.signal_config}}
        self.runner = PriorBacktestRunner(self.engine, self.adapter, self.builder,
                                         execution_mode="offline_fixture", durable_stages=True)

    def test_four_symbols_shared_once_resume_and_exact_original_when_gate_off(self):
        result = self.runner.run_cohort(self.plan, output_dir=self.output)
        self.assertEqual(result["primary_status"], "COMPLETE")
        self.assertEqual(len(result["stocks"]), 4)
        self.assertEqual(self.llm.calls, 24)
        self.assertEqual(len(self.events), 16)
        v2 = read_envelope(self.output / f"v2/FPT-{self.cutoffs[0]}.json")
        v1 = read_envelope(self.output / f"v1/FPT/points/FPT-{self.cutoffs[0]}.json")
        self.assertEqual(v2["prompt"], v1["branches"]["original"]["input"]["prompt"]["text"])
        with patch.object(self.llm, "invoke", side_effect=AssertionError("Không gọi lại complete")):
            verified = self.runner.run_cohort(self.plan, output_dir=self.output, verify_only=True)
            resumed = self.runner.run_cohort(self.plan, output_dir=self.output, resume=True)
        self.assertEqual(result, verified)
        self.assertEqual(result, resumed)

    def test_partial_missing_stock_and_wrong_identity(self):
        result = self.runner.run_cohort(self.plan, output_dir=self.output, symbols=["FPT"])
        self.assertEqual(result["primary_status"], "INCOMPLETE")
        self.assertIsNone(result["primary_delta_return_pp"])
        changed = deepcopy(self.plan)
        changed["evidence_config"]["min_population_count"] = 21
        with self.assertRaises(ValueError):
            self.runner.run_cohort(changed, output_dir=self.output, resume=True)
        self.assertEqual(self.llm.calls, 6)

    def test_split_boundary_and_schema_fail_before_llm(self):
        changed = deepcopy(self.plan)
        changed["split"] = "holdout_2024"
        with self.assertRaises(ValueError):
            validate_plan(changed, self.adapter)
        changed = deepcopy(self.plan)
        changed["symbol_cutoffs"]["FPT"] *= 2
        with self.assertRaises(ValueError):
            validate_plan(changed, self.adapter)
        self.assertEqual(self.llm.calls, 0)

    def test_unknown_v2_requires_exact_audited_replay(self):
        save = research_cohort.save_envelope
        def fail(path, payload):
            if path.parent.name == "v2" and payload.get("attempts", [{}])[-1].get("status") == "complete":
                raise OSError("Lỗi đĩa trước khi response durable")
            return save(path, payload)
        with patch.object(research_cohort, "save_envelope", side_effect=fail), self.assertRaises(OSError):
            self.runner.run_cohort(self.plan, output_dir=self.output, symbols=["FPT"])
        calls = self.llm.calls
        with self.assertRaisesRegex(ValueError, "unknown"):
            self.runner.run_cohort(self.plan, output_dir=self.output, symbols=["FPT"], resume=True)
        report = self.runner.run_cohort(self.plan, output_dir=self.output, reconcile=True)
        unknown = [r for r in report["decisions"] if r["status"] == "unknown"]
        self.assertEqual(len(unknown), 1)
        self.assertEqual(self.llm.calls, calls)
        self.runner.run_cohort(self.plan, output_dir=self.output, reconcile=True,
            authorize_replay=unknown[0]["attempt_id"], replay_reason="Xác nhận trong fixture offline")
        self.runner.run_cohort(self.plan, output_dir=self.output, symbols=["FPT"], resume=True)
        self.assertEqual(self.llm.calls, calls + 1)
        checkpoint = read_envelope(self.output / f"v2/FPT-{self.cutoffs[0]}.json")
        self.assertEqual(len(checkpoint["attempts"]), 2)
        self.assertIsNotNone(checkpoint["attempts"][0]["authorization"])

    def test_missing_v2_checkpoint_blocks_before_any_llm(self):
        self.runner.run_cohort(self.plan, output_dir=self.output, symbols=["FPT"])
        (self.output / f"v2/FPT-{self.cutoffs[0]}.json").unlink()
        calls = self.llm.calls
        with self.assertRaisesRegex(ValueError, "Slot checkpoint"):
            self.runner.run_cohort(self.plan, output_dir=self.output, resume=True)
        self.assertEqual(self.llm.calls, calls)

    def test_raw_action_tamper_rejected_even_with_recomputed_envelope(self):
        self.runner.run_cohort(self.plan, output_dir=self.output, symbols=["FPT"])
        path = self.output / f"v2/FPT-{self.cutoffs[0]}.json"
        payload = read_envelope(path)
        decision = payload["attempts"][-1]["decision"]
        wrong = "SHORT" if decision["action"] == "LONG" else "LONG"
        decision["raw_response"] = [decision["normalized_response"].replace(decision["action"], wrong)]
        research_cohort.save_envelope(path, payload)
        with self.assertRaisesRegex(ValueError, "Response raw"):
            self.runner.run_cohort(self.plan, output_dir=self.output, verify_only=True)

    def test_cli_dry_run_with_reliable_news_never_loads_env_or_network(self):
        from scripts import run_bayesian_ablation as cli
        from core.groq_pacing import MODEL_LIMITS
        from prior_context_test_support import write_json
        articles = [{"date_parsed": self.cutoffs[0], "title": f"Tin {i}", "url": f"https://example.test/{i}",
                     "label": "positive", "numeric_score": .8, "confidence": .9} for i in range(3)]
        for symbol in SYMBOLS:
            write_json(self.fx.root / f"run/inputs/news/{symbol}.json", {"symbol": symbol, "scored_articles": articles})
        import agents.sentiment_agent as sentiment
        with patch("dotenv.load_dotenv", side_effect=AssertionError("Cấm env")), \
             patch.object(cli, "dotenv_values", side_effect=AssertionError("Cấm key")), \
             patch("socket.socket.connect", side_effect=AssertionError("Cấm mạng")):
            importlib.reload(sentiment)
            adapter = self.fx.adapter()
            self.assertTrue(adapter.prepare("FPT", self.cutoffs[0]).agent_state()["sentiment_store"].data["is_reliable"])
            plan = deepcopy(self.plan)
            plan["inputs"].update(limits=MODEL_LIMITS, execution_dir="unused", news_dir="unused",
                execution_manifest_sha256="a", model={"freeze_as_of_date": "2022-12-30", "artifact_path": "unused",
                    "artifact_sha256": "a", "source_path": "unused2", "source_sha256": "a"},
                news_sources={s: {"snapshot_sha256": "a"} for s in SYMBOLS})
            path = self.fx.root / "plan.json"
            research_cohort.save_envelope(path, plan)
            with patch.object(cli, "build_adapter", return_value=adapter), patch("core.pilot_readiness.sha_file", return_value="a"), \
                 patch("sys.argv", ["runner", "--plan", str(path), "--output-dir", str(self.output), "--dry-run"]):
                cli.main()


if __name__ == "__main__":
    unittest.main()
