"""CLI/protocol ứng viên trên nguồn thật dạng fixture, LLM giả và checkpoint durable."""

from copy import deepcopy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pandas as pd
from langchain_core.messages import AIMessage

from core.backtest_engine import PRIOR_BRANCH_MODES
from core.candidate_cohort import CANDIDATES, prepare_candidate_plan, registry
from core.prior_backtest import PriorBacktestRunner
from core.prior_evidence_v2 import normalize_evidence_config
from core.research_cohort import read_envelope, save_envelope, validate_plan
from core.research_invocation import CURRENT
import test_prior_backtest_integration as support


class CandidateLlm:
    """Fixture trả đúng schema được yêu cầu, hỗ trợ raw text và raw tool args."""

    def __init__(self, structured: bool = False) -> None:
        self.calls = 0
        self.prompts = []
        self.structured = structured
        self.call_order = []

    def with_structured_output(self, schema, **kwargs):
        if not self.structured:
            raise NotImplementedError("Fixture text")
        return SimpleNamespace(invoke=lambda prompt:self.structured_call(prompt, schema))

    def payload(self, prompt: str) -> dict:
        self.calls += 1
        self.prompts.append(prompt)
        budget = CURRENT.get()
        self.call_order.append((budget.point_id, budget.branch_id) if budget is not None else None)
        result = {"decision": "LONG", "forecast_horizon": "T+2.5", "confidence": "Cao", "risk_reward_ratio": 1.5,
                  "evidence_for": "Tín hiệu hiện tại.", "evidence_against": "Rủi ro lịch sử.", "justification": "Fixture protocol."}
        if '"prior_use"' in prompt:
            result["prior_use"] = {"metric_ids": [], "example_ids": [], "assessment": "NOT_USED",
                                   "reason": "Không dựa prior trong fixture; không ép hướng."}
        return result

    def invoke(self, prompt: str) -> AIMessage:
        return AIMessage(content=json.dumps(self.payload(prompt), ensure_ascii=False))

    def structured_call(self, prompt: str, schema) -> dict:
        payload = self.payload(prompt)
        return {"parsed": schema.model_validate(payload), "parsing_error": None,
                "raw": AIMessage(content="", tool_calls=[{"id": "fixture-call", "name": schema.__name__, "args": payload}])}


class CandidateSetup:
    """Dùng adapter/graph/engine production với 24 cycle có nhãn kinh tế thật."""

    def setUp(self) -> None:
        dates = pd.bdate_range("2019-08-01", periods=700)
        with patch("prior_context_test_support.pd.bdate_range", return_value=dates):
            support.PriorBacktestIntegrationTests.setUp(self)
        self.fx.records = [self.fx.record(position, self.fx.regime["regime_name"]) for position in range(500, 620, 5)]
        self.fx.publish_bank("a" * 64)
        self.adapter = self.fx.adapter()
        self.llm = CandidateLlm()
        self.builder.agent_llm = self.llm
        self.runner = PriorBacktestRunner(self.engine, self.adapter, self.builder,
            execution_mode="offline_fixture", durable_stages=True)
        self.parent = self.fx.root / "parent.json"
        self.plan_path = self.fx.root / "candidate_plan.json"
        save_envelope(self.parent, {"plan_version": "research_cohort_plan_v2", "cohort_id": "fixture-candidates",
            "matrix": "research_v2", "split": "fixture", "symbol_cutoffs": {s:[self.cutoffs[0]] for s in ("FPT", "MWG", "VCB", "VNM")},
            "evidence_config": normalize_evidence_config(),
            "inputs": {"signal_config": self.adapter.signal_config}})
        self.plan = prepare_candidate_plan(self.parent, self.plan_path, self.adapter, index_path="index.json")

    def checkpoint(self, name: str = "C3", symbol: str = "FPT"):
        path = self.output / f"candidates/{name}/{symbol}-{self.cutoffs[0]}.json"
        return path, read_envelope(path)

    def refresh_adapter(self) -> None:
        """Đổi parent fixture là run mới, cần adapter mới thay vì nới pin nguồn cũ."""
        self.adapter = self.fx.adapter()
        self.runner = PriorBacktestRunner(self.engine, self.adapter, self.builder,
            execution_mode="offline_fixture", durable_stages=True)


class CandidateCohortTests(CandidateSetup, unittest.TestCase):
    def test_four_stocks_eleven_branches_same_full_and_complete_resume(self) -> None:
        parent_bytes = self.parent.read_bytes()
        result = self.runner.run_cohort(self.plan, output_dir=self.output)
        self.assertEqual(self.llm.calls, 44)
        self.assertEqual(self.events, ["indicator", "pattern", "trend", "full"] * 4)
        self.assertEqual(result["primary_status"], "COMPLETE")
        self.assertEqual(result["matrix"], [*PRIOR_BRANCH_MODES, *CANDIDATES])
        self.assertEqual(set(result["candidate_delta_return_pp"]), set(CANDIDATES))
        self.assertEqual(self.parent.read_bytes(), parent_bytes)
        docs = [self.checkpoint(name)[1] for name in CANDIDATES]
        self.assertEqual(len({d["shared_sha256"] for d in docs}), 1)
        c3 = docs[3:]
        self.assertEqual(len({d["request"]["base_evidence_sha256"] for d in c3}), 1)
        self.assertTrue(all(d["request"]["prefix"] for d in c3))
        self.assertNotIn("FPT:", c3[1]["prompt"])
        self.assertNotIn("win_rate_long=", c3[2]["prompt"])
        self.assertTrue(all(len(d["prompt"]) < 6500 for d in docs))
        self.assertEqual(docs[0]["request"], None)
        for stock in result["stocks"].values():
            analysis = stock["prior_analysis"]
            view = stock["points"][0]["prior"]["C3"]
            both_ready = view["stats_ready"] is True and view["examples_ready"] is True
            active = view["decision_contract_version"] == "decision_prior_use_v1"
            self.assertEqual(analysis["ablation"]["stats_examples_ready"]["count"], int(both_ready))
            self.assertEqual(analysis["branches"]["C3"]["trace_required_count"], int(active))
            self.assertEqual(analysis["branches"]["C3"]["assessment_counts"], {"NOT_USED":1} if active else {})
            self.assertEqual(analysis["branches"]["original"]["trace_not_applicable_count"], 1)
            self.assertEqual(analysis["pairs"]["C3__original"]["disagreement"]["value"], 0.)
            self.assertFalse(analysis["branches"]["C3_examples_only"]["cases"][0]["visible_metric_ids"])
            self.assertTrue(all(m["sample_count"] == 1 for m in stock["metrics"].values()))
            self.assertTrue(all(m["risk"]["annualization_factor"] is None for m in stock["metrics"].values()))
            attribution = stock["action_attribution"]
            self.assertEqual(attribution["policy_status"], "DEFERRED")
            self.assertEqual(attribution["override_count"], 0)
            self.assertEqual(len(attribution["points"]), 1)
            self.assertEqual(set(attribution["points"][0]["branches"]), set(result["matrix"]))
            self.assertTrue(all(b["raw_action"] == b["executed_action"] == "LONG"
                for b in attribution["points"][0]["branches"].values()))
        with patch.object(self.llm, "invoke", side_effect=AssertionError("Không gọi lại complete")):
            self.assertEqual(self.runner.run_cohort(self.plan, output_dir=self.output, verify_only=True), result)
            self.assertEqual(self.runner.run_cohort(self.plan, output_dir=self.output, resume=True), result)

    def test_structured_tool_raw_survives_offline_verification(self) -> None:
        self.llm.structured = True
        result = self.runner.run_cohort(self.plan, output_dir=self.output, symbols=["FPT"])
        self.assertEqual(self.llm.calls, 11)
        self.assertEqual(result["primary_status"], "INCOMPLETE")
        with patch.object(self.llm, "structured_call", side_effect=AssertionError("Cấm LLM verifier")):
            self.assertEqual(self.runner.run_cohort(self.plan, output_dir=self.output, verify_only=True), result)
        self.assertTrue(all(value is None for value in result["candidate_delta_return_pp"].values()))

    def test_partial_candidate_durable_response_is_reused_after_failure(self) -> None:
        import core.research_cohort as cohort
        save = cohort.save_envelope
        def fail(path, payload):
            save(path, payload)
            if path.parent.name == "C2" and payload.get("attempts", [{}])[-1].get("status") == "complete":
                raise OSError("Fixture crash sau response durable")
        with patch.object(cohort, "save_envelope", side_effect=fail), self.assertRaises(OSError):
            self.runner.run_cohort(self.plan, output_dir=self.output, symbols=["FPT"])
        calls, events = self.llm.calls, list(self.events)
        self.assertEqual(calls, 8)
        verified = self.runner.run_cohort(self.plan, output_dir=self.output, verify_only=True)
        self.assertEqual(verified["report_version"], "research_report_v5")
        self.assertEqual(verified["stocks"]["FPT"]["completed"], 0)
        self.assertTrue(all(m["sample_count"] == 0 for m in verified["stocks"]["FPT"]["metrics"].values()))
        stock = verified["stocks"]["FPT"]
        self.assertEqual(stock["pairwise_support"]["C0__original"]["count"], 1)
        self.assertEqual(stock["coverage"]["C2"]["complete"], 1)
        self.assertEqual(stock["coverage"]["C3"]["pending"], 1)
        self.assertEqual(stock["coverage"]["C3"]["readiness_unknown"], 1)
        self.runner.run_cohort(self.plan, output_dir=self.output, symbols=["FPT"], resume=True)
        self.assertEqual(self.llm.calls, calls + 3)
        self.assertEqual(self.events, events)

    def test_unknown_requires_exact_reconcile_and_only_replays_missing_branch(self) -> None:
        import core.research_cohort as cohort
        save = cohort.save_envelope
        def fail(path, payload):
            if path.parent.name == "C2" and payload.get("attempts", [{}])[-1].get("status") == "complete":
                raise OSError("Fixture mất response trước durable")
            save(path, payload)
        with patch.object(cohort, "save_envelope", side_effect=fail), self.assertRaises(OSError):
            self.runner.run_cohort(self.plan, output_dir=self.output, symbols=["FPT"])
        calls = self.llm.calls
        with self.assertRaisesRegex(ValueError, "unknown"):
            self.runner.run_cohort(self.plan, output_dir=self.output, resume=True, symbols=["MWG"])
        reconciled = self.runner.run_cohort(self.plan, output_dir=self.output, reconcile=True)
        unknown = [r for r in reconciled["decisions"] if r["status"] == "unknown"]
        self.assertEqual(len(unknown), 1)
        self.assertEqual(unknown[0]["branch"], "C2")
        self.assertEqual(self.llm.calls, calls)
        verified = self.runner.run_cohort(self.plan, output_dir=self.output, verify_only=True)
        self.assertEqual(verified["stocks"]["FPT"]["coverage"]["C2"]["unknown"], 1)
        self.assertEqual(verified["stocks"]["FPT"]["coverage"]["C2"]["prior_visible_count"], 0)
        self.runner.run_cohort(self.plan, output_dir=self.output, reconcile=True,
            authorize_replay=unknown[0]["attempt_id"], replay_reason="Đối soát fixture; cho replay đúng UUID")
        self.runner.run_cohort(self.plan, output_dir=self.output, resume=True, symbols=["FPT"])
        self.assertEqual(self.llm.calls, calls + 4)
        self.assertEqual(len(self.checkpoint("C2")[1]["attempts"]), 2)

    def test_rehashed_evidence_prompt_and_raw_trace_tampering_block_before_llm(self) -> None:
        self.runner.run_cohort(self.plan, output_dir=self.output, symbols=["FPT"])
        path, saved = self.checkpoint()
        mutations = [lambda d:d["evidence"]["statistics"]["metrics"]["win_rate_long"].update(posterior_mean=.123),
            lambda d:d.update(prompt=d["prompt"] + " giả"),
            lambda d:d["attempts"][-1]["output"]["prior_decision_trace"].update(raw_action="SHORT"),
            lambda d:d["attempts"][-1]["output"].update(final_trade_decision=d["attempts"][-1]["output"]["final_trade_decision"].replace("LONG", "SHORT"))]
        calls = self.llm.calls
        for mutate in mutations:
            changed = deepcopy(saved)
            mutate(changed)
            save_envelope(path, changed)
            with self.assertRaises(ValueError):
                self.runner.run_cohort(self.plan, output_dir=self.output, resume=True, symbols=["MWG"])
            self.assertEqual(self.llm.calls, calls)
        save_envelope(path, saved)

    def test_plan_registry_model_index_and_missing_slot_block_before_new_call(self) -> None:
        self.runner.run_cohort(self.plan, output_dir=self.output, symbols=["FPT"])
        calls = self.llm.calls
        for mutate in (lambda p:p["candidate_registry"]["selection"].update(min_similarity=.1),
                       lambda p:p["inputs"]["signal_config"]["models"].update(agent_llm_model="other/model"),
                       lambda p:p["price_index"].update(identity="0" * 64),
                       lambda p:p.update(split="holdout_2024")):
            changed = deepcopy(self.plan)
            mutate(changed)
            with self.assertRaises(ValueError):
                self.runner.run_cohort(changed, output_dir=self.output, resume=True)
        self.checkpoint("C3_examples_only", "MWG")[0].unlink()
        with self.assertRaisesRegex(ValueError, "Slot checkpoint"):
            self.runner.run_cohort(self.plan, output_dir=self.output, resume=True, symbols=["MWG"])
        self.assertEqual(self.llm.calls, calls)

    def test_prepare_and_dry_run_cli_never_read_key_or_network(self) -> None:
        from scripts import run_bayesian_ablation as cli
        from core.groq_pacing import MODEL_LIMITS
        parent = read_envelope(self.parent)
        parent["inputs"].update(limits=MODEL_LIMITS, execution_dir="unused", news_dir="unused",
            execution_manifest_sha256="a", model={"freeze_as_of_date":"2022-12-30", "artifact_path":"unused",
                "artifact_sha256":"a", "source_path":"unused2", "source_sha256":"a"},
            news_sources={s:{"snapshot_sha256":"a"} for s in self.plan["symbol_cutoffs"]})
        save_envelope(self.parent, parent)
        destination = self.fx.root / "cli_plan.json"
        self.refresh_adapter()
        with patch.object(cli, "build_adapter", return_value=self.adapter), patch("core.pilot_readiness.sha_file", return_value="a"), \
             patch.object(cli, "dotenv_values", side_effect=AssertionError("Cấm key")), \
             patch("socket.socket.connect", side_effect=AssertionError("Cấm mạng")):
            for argv in (["--prepare", "--plan", str(self.parent), "--candidate-plan", str(destination), "--price-index", "index.json"],
                         ["--dry-run", "--plan", str(destination)]):
                with patch("sys.argv", ["runner", *argv, "--output-dir", str(self.output)]):
                    cli.main()
        self.assertEqual(read_envelope(destination)["candidate_registry"], registry())
        self.assertEqual(self.llm.calls, 0)

    def test_two_points_finish_candidates_in_registered_order_before_next_point(self) -> None:
        parent = read_envelope(self.parent)
        parent["symbol_cutoffs"]["FPT"] = list(self.cutoffs)
        save_envelope(self.parent, parent)
        self.refresh_adapter()
        plan = prepare_candidate_plan(self.parent, self.fx.root / "two_points.json", self.adapter, index_path="index.json")
        self.runner.run_cohort(plan, output_dir=self.output, symbols=["FPT"])
        expected = [(f"FPT-{day}", name) for day in self.cutoffs for name in (*PRIOR_BRANCH_MODES, *CANDIDATES)]
        self.assertEqual(self.llm.call_order, expected)
        self.assertEqual(self.events, ["indicator", "pattern", "trend", "full"] * 2)

    def test_malformed_c3_stops_bounded_and_keeps_completed_candidates(self) -> None:
        payload = self.llm.payload
        def malformed(prompt):
            result = payload(prompt)
            result.pop("prior_use", None)
            return result
        with patch.object(self.llm, "payload", side_effect=malformed), self.assertRaises(RuntimeError):
            self.runner.run_cohort(self.plan, output_dir=self.output, symbols=["FPT"])
        self.assertEqual(self.llm.calls, 10)
        self.assertTrue(all(self.checkpoint(name)[1]["attempts"][-1]["status"] == "complete" for name in ("C0", "C1", "C2")))
        diagnostic = self.runner.run_cohort(self.plan, output_dir=self.output, reconcile=True)
        self.assertEqual([(r["branch"], r["status"]) for r in diagnostic["decisions"] if r["status"] == "unknown"], [("C3", "unknown")])

    def test_cli_verify_and_reconcile_use_checkpoint_without_key_or_http(self) -> None:
        from scripts import run_bayesian_ablation as cli
        from core.groq_pacing import MODEL_LIMITS
        parent = read_envelope(self.parent)
        parent["inputs"].update(limits=MODEL_LIMITS, execution_dir="unused", news_dir="unused",
            execution_manifest_sha256="a", model={"freeze_as_of_date":"2022-12-30", "artifact_path":"unused",
                "artifact_sha256":"a", "source_path":"unused2", "source_sha256":"a"},
            news_sources={s:{"snapshot_sha256":"a"} for s in self.plan["symbol_cutoffs"]})
        save_envelope(self.parent, parent)
        path = self.fx.root / "cli_verify_plan.json"
        self.refresh_adapter()
        plan = prepare_candidate_plan(self.parent, path, self.adapter, index_path="index.json")
        ledger = self.fx.root / "ledger.json"
        result = self.runner.run_cohort(plan, output_dir=self.output, symbols=["FPT"], ledger_path=ledger)
        from core.research_metrics import http_telemetry
        result["telemetry"] = http_telemetry([], result["run_signatures"], {})
        save_envelope(self.output / "report.json", result)
        calls = self.llm.calls
        with patch.object(cli, "ROOT", self.fx.root), patch.object(cli, "build_adapter", return_value=self.adapter), \
             patch("core.pilot_readiness.sha_file", return_value="a"), patch.object(cli, "make_builder", return_value=self.builder), \
             patch.object(cli, "PriorBacktestRunner", return_value=self.runner), \
             patch.object(cli, "dotenv_values", side_effect=AssertionError("Cấm key")), \
             patch("socket.socket.connect", side_effect=AssertionError("Cấm HTTP")):
            for mode in ("--verify-only", "--reconcile", "--verify-report", "--select-candidate", "--verify-selection"):
                with patch("sys.argv", ["runner", mode, "--plan", str(path), "--output-dir", str(self.output), "--ledger", str(ledger)]):
                    cli.main()
            selection_path = self.output / "candidate_selection_v1.json"
            selection = read_envelope(selection_path)
            self.assertEqual(selection["nomination_status"],"BLOCKED")
            self.assertIsNone(selection["research_candidate"])
            self.assertEqual(selection["binding"]["technical_gates"]["status"],"NOT_VERIFIED")
            changed_selection = deepcopy(selection)
            changed_selection.update(nomination_status="PROMOTED",research_candidate="C0")
            save_envelope(selection_path,changed_selection)
            with patch("sys.argv", ["runner", "--verify-selection", "--plan", str(path), "--output-dir", str(self.output), "--ledger", str(ledger)]), self.assertRaisesRegex(ValueError, "Quyết định khác"):
                cli.main()
            changed = deepcopy(result)
            changed["stocks"]["FPT"]["global_common_support"]["count"] = 999
            save_envelope(self.output / "report.json", changed)
            with patch("sys.argv", ["runner", "--verify-report", "--plan", str(path), "--output-dir", str(self.output), "--ledger", str(ledger)]), self.assertRaisesRegex(ValueError, "Report khác"):
                cli.main()
        self.assertEqual(self.llm.calls, calls)
