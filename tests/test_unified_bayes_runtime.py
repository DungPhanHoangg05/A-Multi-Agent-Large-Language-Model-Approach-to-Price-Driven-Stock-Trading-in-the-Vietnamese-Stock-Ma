"""Instruction/schema chung, shared-off và journal/retry qua SDK + HTTP mock."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch

import httpx

from core.unified_bayes_decision import LLM_BRANCHES, shared_off_allowed, build_prompt, trace_ids
from core.unified_bayes_runtime import branch_order, upstream_journal, upstream_checkpoint
from core.unified_bayes_transport import upstream_scope
from core.research_cohort import read_envelope
from core.groq_pacing import PilotStop
from agents.decision_agent import _invoke_with_retry
from unified_context_test_support import dense_inputs, make_context
from unified_execution_test_support import ExecutionFixture, shared_state, PAYLOAD


class UnifiedExecutionTests(unittest.TestCase):
    """Kernel production trên memory tổng hợp, không gọi API thật hoặc đổi nguồn khoa học."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.inputs = dense_inputs()
        cls.context = make_context(cls.inputs)

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.fx = ExecutionFixture(Path(directory.name), self.context, self.inputs)
        self.addCleanup(self.fx.close)

    def test_smoke_five_branches_run_sdk_schema_and_resume_without_http(self) -> None:
        prepared = self.fx.prepare()
        journal = self.fx.journal()
        docs = journal.run_point(prepared.point_id, execute=True)
        self.assertTrue(all(doc["status"] == "complete" for doc in docs.values()))
        count = len(self.fx.calls)
        self.assertEqual(journal.run_point(prepared.point_id, execute=True), docs)
        self.assertEqual(len(self.fx.calls), count)
        self.assertEqual(count, 5)

    def test_locked_shared_off_oracles(self) -> None:
        fixture = json.loads((Path(__file__).resolve().parents[1] /
            "docs/plan/week10/fixtures/unified_bic_contract_v1.json").read_text("utf-8"))
        for case in fixture["shared_off_cases"]:
            values = {k: v for k, v in case.items() if k not in ("case_id", "expected_reuse")}
            self.assertIs(shared_off_allowed(**values), case["expected_reuse"])

    def test_all_branches_share_schema_and_common_base_and_original_is_durable_first(self) -> None:
        point = self.fx.prepare(saturated=True)
        packets = {branch: point.packet(branch) for branch in LLM_BRANCHES}
        original = packets["Original"]
        for packet in packets.values():
            self.assertEqual(packet["body"]["response_format"], original["body"]["response_format"])
            self.assertLess(len(packet["prompt"]), 6500)
            self.assertIn("Open(t+1)→Close(t+3)", packet["prompt"])
            self.assertEqual(packet["shared_sha256"], original["shared_sha256"])
        journal = self.fx.journal()
        def check(_):
            if len(self.fx.calls) > 1:
                from core.research_cohort import read_envelope
                self.assertEqual(read_envelope(journal.path(point.point_id, 0, "Original"))["status"], "complete")
            return self.fx.response()
        self.fx.handler = check
        journal.run_point(point.point_id, execute=True)

    def test_off_branches_reuse_same_point_repeat_without_http_and_duplicate_is_independent(self) -> None:
        self.fx.cutoff = "2021-01-04"
        point = self.fx.prepare()
        self.assertTrue(all(not point.packet(branch)["prefix"] for branch in LLM_BRANCHES))
        journal = self.fx.journal(repeats=True)
        for rid in range(4):
            docs = journal.run_point(point.point_id, rid, execute=True)
            for branch in LLM_BRANCHES[1:]:
                self.assertEqual(docs[branch]["decision_origin"], "shared_original")
                self.assertEqual(docs[branch]["attempts"], [])
                self.assertEqual(docs[branch]["output"], docs["Original"]["output"])
                self.assertEqual(docs[branch]["shared_original"]["repeat_id"], rid)
            if rid:
                self.assertEqual(docs["Original_duplicate"]["decision_origin"], "invoked")
                self.assertNotEqual(docs["Original_duplicate"]["attempts"][0]["attempt_id"], docs["Original"]["attempts"][0]["attempt_id"])
        self.assertEqual(len(self.fx.calls), 7)
        self.assertEqual(len(self.fx.pacer.state["requests"]), 7)

    def test_equal_visible_stats_and_full_body_are_not_whitelisted_for_alias(self) -> None:
        from core.unified_bayes_decision import DecisionPreparer
        from unified_execution_test_support import SourcePoint, MODELS
        from unified_context_test_support import features
        f = features(self.inputs)
        f.update(status="UNAVAILABLE", vector=None, reasons=["INSUFFICIENT_HISTORY"])
        shared = shared_state()
        source = SourcePoint(f, shared)
        with patch("core.unified_bayes_decision.load_renderer_lock", return_value={}):
            producer = DecisionPreparer(self.context, self.fx.llm, MODELS)
        point = producer.prepare(source, shared)
        self.fx.prepared = point
        self.assertTrue(point.packet("U_full")["prefix"])
        self.assertEqual(point.packet("U_full")["body"], point.packet("U_stats")["body"])
        journal = self.fx.journal()
        docs = journal.run_point(point.point_id, execute=True)
        for name in ("U_full", "U_stats"):
            self.assertEqual(docs[name]["decision_origin"], "invoked")
            self.assertEqual(docs[name]["output"]["decision"], "LONG")
        self.assertNotEqual(docs["U_full"]["attempts"][0]["attempt_id"], docs["U_stats"]["attempts"][0]["attempt_id"])
        self.assertEqual(len(self.fx.calls), 4)

    def test_format_repair_uses_same_body_uuid_and_keeps_legacy_schema(self) -> None:
        point = self.fx.prepare()
        self.fx.handler = lambda _: self.fx.response("định dạng sai") if len(self.fx.calls) == 1 else self.fx.response()
        journal = self.fx.journal()
        docs = journal.run_point(point.point_id, execute=True)
        attempt = docs["Original"]["attempts"][0]
        self.assertEqual(len(attempt["responses"]), 2)
        rows = [row for row in self.fx.pacer.state["requests"] if row["checkpoint_attempt_id"] == attempt["attempt_id"]]
        self.assertEqual([row["status"] for row in rows], [200, 200])
        self.assertEqual(self.fx.calls[0], self.fx.calls[1])
        self.assertEqual(len(self.fx.calls), 6)

    def test_two_malformed_results_stop_without_cash_or_following_branch(self) -> None:
        point = self.fx.prepare()
        self.fx.handler = lambda _: self.fx.response("định dạng sai")
        journal = self.fx.journal()
        for _ in range(2):
            with self.assertRaises(ValueError):
                journal.run_point(point.point_id, execute=True)
        self.assertEqual(len(self.fx.calls), 2)
        saved = read_envelope(journal.path(point.point_id, 0, "Original"))
        self.assertEqual(saved["status"], "unknown")
        self.assertIsNone(saved["output"])

    def test_429_retry_after_and_transient_errors_share_body_uuid(self) -> None:
        point = self.fx.prepare()
        def handle(_):
            if len(self.fx.calls) == 1:
                return httpx.Response(429, headers={"retry-after": "135"}, json={"error": {"message": "TPM; retry after 135 seconds"}})
            if len(self.fx.calls) == 2:
                return httpx.Response(503, json={"error": {"message": "Tạm lỗi"}})
            return self.fx.response()
        self.fx.handler = handle
        journal = self.fx.journal()
        result = journal.run_point(point.point_id, execute=True)
        uid = result["Original"]["attempts"][0]["attempt_id"]
        rows = [row for row in self.fx.pacer.state["requests"] if row["checkpoint_attempt_id"] == uid]
        self.assertEqual([row["status"] for row in rows], [429, 503, 200])
        self.assertEqual(self.fx.calls[0], self.fx.calls[1])
        self.assertEqual(self.fx.calls[1], self.fx.calls[2])
        self.assertGreaterEqual(self.fx.now, 100135.)

    def test_auth_stop_then_resume_same_uuid_with_audit(self) -> None:
        point = self.fx.prepare()
        journal = self.fx.journal()
        self.fx.handler = lambda _: httpx.Response(401, json={"error": {"message": "Fixture key không hợp lệ"}})
        with self.assertRaises(PilotStop):
            journal.run_point(point.point_id, execute=True)
        before = read_envelope(journal.path(point.point_id, 0, "Original"))
        self.fx.handler = None
        after = journal.run_point(point.point_id, execute=True)["Original"]
        self.assertEqual(before["attempts"][0]["attempt_id"], after["attempts"][0]["attempt_id"])
        self.assertEqual(after["attempts"][0]["recoveries"][0]["reason"], "SAME_UUID_RETRY_WITH_AUDIT")

    def test_daily_quota_stops_and_resume_preserves_usage_and_uuid(self) -> None:
        point = self.fx.prepare()
        journal = self.fx.journal()
        self.fx.handler = lambda _: httpx.Response(429, headers={"retry-after": "3600"}, json={"error": {"message": "Quota TPD per day"}})
        with self.assertRaises(PilotStop):
            journal.run_point(point.point_id, execute=True)
        saved = read_envelope(journal.path(point.point_id, 0, "Original"))
        before = deepcopy(self.fx.pacer.state["requests"])
        self.fx.now += 86401
        self.fx.handler = None
        result = journal.run_point(point.point_id, execute=True)
        self.assertEqual(result["Original"]["attempts"][0]["attempt_id"], saved["attempts"][0]["attempt_id"])
        self.assertEqual(self.fx.pacer.state["requests"][:len(before)], before)

    def test_crash_after_http_cache_during_format_repair_restores_unconsumed_response(self) -> None:
        point = self.fx.prepare()
        journal = self.fx.journal()
        self.fx.handler = lambda _: self.fx.response("sai định dạng") if len(self.fx.calls) == 1 else self.fx.response()
        store, fired = self.fx.transport._store, []
        def fail(request, response):
            store(request, response)
            if len(self.fx.calls) == 2 and not fired:
                fired.append(True)
                raise OSError("Fixture crash sau cache của format repair")
        with patch.object(self.fx.transport, "_store", side_effect=fail), self.assertRaises(PilotStop):
            journal.run_point(point.point_id, execute=True)
        result = journal.run_point(point.point_id, execute=True)
        self.assertEqual(result["Original"]["status"], "complete")
        self.assertEqual(len(self.fx.calls), 6)
        self.assertEqual(len(result["Original"]["attempts"][0]["responses"]), 2)

    def test_crash_after_intent_or_response_and_complete_never_replays(self) -> None:
        for boundary in ("intent", "response", "complete"):
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as directory:
                fx = ExecutionFixture(Path(directory), self.context, self.inputs)
                self.addCleanup(fx.close)
                point = fx.prepare()
                journal = fx.journal()
                save, fired = journal.save, []
                def crash(path, value):
                    save(path, value)
                    trigger = (value["status"] == "complete" if boundary == "complete" else
                        bool(value["attempts"]) and bool(value["attempts"][0]["responses"]) == (boundary == "response"))
                    if path.name == "Original.json" and trigger and not fired:
                        fired.append(True)
                        raise OSError("Fixture crash sau durable")
                with patch.object(journal, "save", side_effect=crash), self.assertRaises(OSError):
                    journal.run_point(point.point_id, execute=True)
                result = journal.run_point(point.point_id, execute=True)
                self.assertTrue(all(doc["status"] == "complete" for doc in result.values()))
                self.assertEqual(len(fx.calls), 5)

    def test_transport_durable_response_cache_recovers_before_sdk_checkpoint(self) -> None:
        point = self.fx.prepare()
        journal = self.fx.journal()
        store, fired = self.fx.transport._store, []
        def fail(request, response):
            store(request, response)
            if not fired:
                fired.append(True)
                raise OSError("Fixture crash sau HTTP cache, trước SDK return")
        with patch.object(self.fx.transport, "_store", side_effect=fail), self.assertRaises(PilotStop):
            journal.run_point(point.point_id, execute=True)
        before = read_envelope(journal.path(point.point_id, 0, "Original"))
        uid = before["attempts"][0]["attempt_id"]
        journal.run_point(point.point_id, execute=True)
        rows = [row for row in self.fx.pacer.state["requests"] if row["checkpoint_attempt_id"] == uid]
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(self.fx.calls), 5)
        self.assertEqual(self.fx.pacer.state["recovery_events"][-1]["reason"], "DURABLE_RESPONSE_REUSED")

    def test_common_instruction_and_full_600_reserve_fit_both_languages(self) -> None:
        for lang in ("vi", "en"):
            shared = shared_state(language=lang, saturated=True)
            prompt = build_prompt(shared, "Đ" * 600)
            self.assertLess(len(prompt), 6500)
            self.assertIn("Open(t+1)→Close(t+3)", prompt)
            self.assertNotIn("prior_use", prompt)
        point = self.fx.prepare()
        data = deepcopy(PAYLOAD)
        data["justification"] = "LONG dù prior thấp; căn cứ hiện tại. E1 T9."
        self.fx.handler = lambda _: self.fx.response(data)
        journal = self.fx.journal()
        docs = journal.run_point(point.point_id, execute=True)
        self.assertEqual(len(self.fx.calls), 5)
        self.assertEqual(docs["U_full"]["output"]["decision"], "LONG")
        trace = trace_ids(point.packet("U_full"), docs["U_full"]["output"])
        self.assertIn("T9", trace["unknown_ids"])
        self.assertFalse(trace["for_promotion"])

    def test_upstream_stage_journal_reuses_all_four_nodes_without_llm_replay(self) -> None:
        root = self.fx.root / "upstream_run"
        journal = upstream_journal(root, "b" * 64, "FPT-2023-01-06", {"source": "a" * 64}, create=True)
        calls = []
        def run():
            state = {"stock_name": "FPT", "as_of_date": "2023-01-06"}
            with upstream_scope(lambda: None):
                for stage in ("indicator", "pattern", "trend", "full"):
                    def node(actual, name=stage):
                        calls.append(name)
                        response = _invoke_with_retry(self.fx.llm.invoke, "Upstream " + name)
                        if name == "full":
                            return {"alpha_report": response.content, "sentiment_report": response.content, "sentiment_data": {}}
                        return {name + "_report": response.content}
                    state.update(journal.invoke(stage, node, deepcopy(state)))
            return state
        self.assertEqual(run(), run())
        self.assertEqual(calls, ["indicator", "pattern", "trend", "full"])
        self.assertEqual(len(self.fx.calls), 4)

    def test_unknown_upstream_resumes_same_uuid_with_separate_audit(self) -> None:
        root = self.fx.root / "source_resume"
        proof, calls = {"source": "a" * 64}, []
        def node(state):
            calls.append(1)
            if len(calls) == 1:
                raise OSError("Fixture ngắt trước HTTP")
            return {"indicator_report": "Đã phục hồi"}
        with self.assertRaises(OSError), upstream_checkpoint(root, "b" * 64, "FPT-2023-01-06", proof, lambda: None, create=True) as journal:
            journal.invoke("indicator", node, {"input": "cố định"})
        uid = journal.document["nodes"]["indicator"]["attempts"][-1]["attempt_id"]
        with upstream_checkpoint(root, "b" * 64, "FPT-2023-01-06", proof, lambda: None) as resumed:
            resumed.invoke("indicator", node, {"input": "cố định"})
            self.assertEqual(resumed.document["nodes"]["indicator"]["attempts"][-1]["attempt_id"], uid)
        audit = read_envelope(root / "upstream/FPT-2023-01-06.recovery.json")
        self.assertEqual(audit["events"][0]["attempt_id"], uid)
        self.assertEqual(audit["events"][0]["reason"], "SAME_UUID_RETRY_WITH_AUDIT")

    def test_rotation_matches_locked_primary_and_repeat_oracles(self) -> None:
        self.assertEqual(branch_order(0), list(LLM_BRANCHES))
        self.assertEqual(branch_order(1), ["Original", "U_full", "U_stats", "U_examples", "A_reference"])
        self.assertEqual(branch_order(0, 1), [*LLM_BRANCHES, "Original_duplicate"])
        for value in (True, -1):
            with self.assertRaises(ValueError):
                branch_order(value)


class UnifiedExecutionContractTests(unittest.TestCase):
    """Persistence contract phân biệt numeric types và không ghi đè input khác source."""

    def test_cli_prepare_resume_verify_and_resealed_type_or_body_drift(self) -> None:
        from core.research_cohort import save_envelope
        from scripts import prepare_unified_bayes_execution as cli
        expected = {"query_count": 60, "prepared_llm_requests": 300, "max_prompt_chars": 6400,
                    "points": [{"body": {"model": "fixture"}}]}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "contract.json"
            with patch.object(cli, "OUTPUT", path), patch.object(cli, "build_contract", return_value=expected), patch("builtins.print"):
                def run(mode):
                    with patch.object(sys, "argv", ["contract", mode]):
                        cli.main()
                with self.assertRaises(ValueError):
                    run("--verify-only")
                run("--prepare")
                original = path.read_bytes()
                run("--prepare")
                run("--verify-only")
                self.assertEqual(original, path.read_bytes())
                for change in ("type", "body"):
                    saved = deepcopy(expected)
                    if change == "type":
                        saved["query_count"] = 60.0
                    else:
                        saved["points"][0]["body"]["model"] = "khác"
                    save_envelope(path, saved)
                    for mode in ("--verify-only", "--prepare"):
                        with self.assertRaises(ValueError):
                            run(mode)


if __name__ == "__main__":
    unittest.main()
