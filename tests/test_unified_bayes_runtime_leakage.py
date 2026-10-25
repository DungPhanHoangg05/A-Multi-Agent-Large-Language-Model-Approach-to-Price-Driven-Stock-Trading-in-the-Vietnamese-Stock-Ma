"""PIT/source/body/repeat binding và chống reseal journal U-BICL trước HTTP."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.research_cohort import read_envelope, save_envelope
from core.unified_bayes_transport import decision_scope
from unified_context_test_support import dense_inputs, make_context
from unified_execution_test_support import ExecutionFixture


class UnifiedRuntimeLeakageTests(unittest.TestCase):
    """Mọi sửa source/request/raw hoặc alias sai scope phải dừng trước HTTP mới."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.inputs = dense_inputs()
        cls.context = make_context(cls.inputs)

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.fx = ExecutionFixture(Path(directory.name), self.context, self.inputs)
        self.addCleanup(self.fx.close)

    def test_source_changed_blocks_all_slots_before_first_http(self) -> None:
        point = self.fx.prepare()
        journal = self.fx.journal()
        self.fx.source.changed = True
        with self.assertRaises(ValueError):
            journal.run_point(point.point_id, execute=True)
        self.assertEqual(self.fx.calls, [])
        self.fx.source.changed = False
        send = self.fx.client._send_single_request
        def change_at_dispatch(request):
            self.fx.source.changed = True
            return send(request)
        with patch.object(self.fx.client, "_send_single_request", side_effect=change_at_dispatch), self.assertRaises(ValueError):
            journal.run_point(point.point_id, execute=True)
        self.assertEqual(self.fx.calls, [])

    def test_source_changed_during_retry_stops_before_next_provider_http(self) -> None:
        import httpx
        point = self.fx.prepare()
        journal = self.fx.journal()
        def fail(_):
            self.fx.source.changed = True
            return httpx.Response(503, json={"error": {"message": "Fixture tạm lỗi"}})
        self.fx.handler = fail
        with self.assertRaises(ValueError):
            journal.run_point(point.point_id, execute=True)
        self.assertEqual(len(self.fx.calls), 1)

    def test_unselected_point_source_changed_blocks_selected_point_before_http(self) -> None:
        from core.unified_bayes_decision import DecisionPreparer
        from core.unified_bayes_runtime import ExecutionJournal, branch_order
        from unified_execution_test_support import MODELS, SourcePoint, shared_state
        from unified_context_test_support import features
        first = self.fx.prepare()
        shared = shared_state("2023-04-04")
        other = SourcePoint(features(self.inputs, "2023-04-04"), shared)
        with patch("core.unified_bayes_decision.load_renderer_lock", return_value={}):
            producer = DecisionPreparer(self.context, self.fx.llm, MODELS)
        second = producer.prepare(other, shared)
        schedule = [{"point_id": point.point_id, "repeat_id": 0, "order": branch_order(i)} for i, point in enumerate((first, second))]
        journal = ExecutionJournal(self.fx.root / "run", "b" * 64, [first, second], self.fx.llm, schedule, create=True)
        other.changed = True
        with self.assertRaises(ValueError):
            journal.run_point(first.point_id, execute=True)
        self.assertEqual(self.fx.calls, [])

    def test_manifest_or_ledger_file_changed_cannot_be_hidden_by_cached_ram(self) -> None:
        point = self.fx.prepare()
        journal = self.fx.journal()
        identity = journal.root / "identity.json"
        original = read_envelope(identity)
        changed = deepcopy(original)
        changed["run_signature"] = "c" * 64
        save_envelope(identity, changed)
        with self.assertRaises(ValueError):
            journal.run_point(point.point_id, execute=True)
        save_envelope(identity, original)
        journal.run_point(point.point_id, execute=True)
        path = self.fx.pacer.path
        on_disk = json.loads(path.read_text("utf-8"))
        on_disk["requests"] = []
        path.write_text(json.dumps(on_disk), encoding="utf-8")
        with self.assertRaises(ValueError):
            journal.run_point(point.point_id, execute=True)
        self.assertEqual(len(self.fx.calls), 5)

    def test_wrong_endpoint_is_rejected_before_provider_or_ledger(self) -> None:
        point = self.fx.prepare()
        packet = point.packet("Original")
        slot = {"run_signature": "b" * 64, "point_id": point.point_id, "branch_id": "Original", "repeat_id": 0,
            "checkpoint_attempt_id": "00000000-0000-0000-0000-000000000001", "prompt_sha256": packet["prompt_sha256"]}
        with decision_scope(packet=packet, slot=slot, source_check=lambda: point.verify(self.fx.llm)), self.assertRaises(ValueError):
            self.fx.client.post("https://api.groq.com/endpoint-khac", json=packet["body"])
        self.assertEqual(self.fx.calls, [])
        self.assertEqual(self.fx.pacer.state["requests"], [])

    def test_foreign_point_repeat_or_integer_type_drift_cannot_reseal_slot(self) -> None:
        point = self.fx.prepare()
        journal = self.fx.journal()
        path = journal.path(point.point_id, 0, "U_examples")
        original = read_envelope(path)
        for key, value in (("point_id", "VCB-2023-01-06"), ("repeat_id", 1), ("repeat_id", 0.0), ("packet_sha256", "a" * 64)):
            saved = deepcopy(original)
            saved[key] = value
            save_envelope(path, saved)
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                journal.run_point(point.point_id, execute=True)
        self.assertEqual(self.fx.calls, [])

    def test_parsed_action_and_output_resealed_together_cannot_replace_raw_http(self) -> None:
        point = self.fx.prepare()
        journal = self.fx.journal()
        journal.run_point(point.point_id, execute=True)
        path = journal.path(point.point_id, 0, "Original")
        saved = read_envelope(path)
        saved["attempts"][0]["responses"][-1]["parsed"]["decision"] = "SHORT"
        saved["output"]["decision"] = "SHORT"
        save_envelope(path, saved)
        with self.assertRaises(ValueError):
            journal.run_point(point.point_id, execute=True)
        self.assertEqual(len(self.fx.calls), 5)

    def test_shared_off_reference_cannot_move_between_repeats(self) -> None:
        self.fx.cutoff = "2021-01-04"
        point = self.fx.prepare()
        journal = self.fx.journal(repeats=True)
        journal.run_point(point.point_id, execute=True)
        journal.run_point(point.point_id, 1, execute=True)
        path = journal.path(point.point_id, 1, "U_full")
        saved = read_envelope(path)
        for foreign in (journal._original_ref(point.point_id, 0)[1], {**saved["shared_original"], "repeat_id": 1.0}):
            changed = deepcopy(saved)
            changed["shared_original"] = foreign
            save_envelope(path, changed)
            with self.assertRaises(ValueError):
                journal.run_point(point.point_id, 1, execute=True)
        self.assertEqual(len(self.fx.calls), 3)

    def test_visible_branch_or_duplicate_cannot_be_forged_into_shared_original(self) -> None:
        point = self.fx.prepare()
        journal = self.fx.journal()
        docs = journal.run_point(point.point_id, execute=True)
        path = journal.path(point.point_id, 0, "U_stats")
        saved = deepcopy(docs["U_stats"])
        saved.update(decision_origin="shared_original", attempts=[], shared_original=journal._original_ref(point.point_id, 0)[1],
            output=deepcopy(docs["Original"]["output"]), reason_codes=["CANONICAL_REQUEST_IDENTICAL"])
        save_envelope(path, saved)
        with self.assertRaises(ValueError):
            journal.run_point(point.point_id, execute=True)
        self.assertEqual(len(self.fx.calls), 5)

    def test_body_model_options_schema_guard_blocks_before_reserve_or_http(self) -> None:
        point = self.fx.prepare()
        packet = point.packet("Original")
        slot = {"run_signature": "b" * 64, "point_id": point.point_id, "branch_id": "Original", "repeat_id": 0,
            "checkpoint_attempt_id": "00000000-0000-0000-0000-000000000001", "prompt_sha256": packet["prompt_sha256"]}
        for changes in ({"model": "khác-model"}, {"temperature": .8}, {"response_format": {"type": "text"}}):
            with decision_scope(packet=packet, slot=slot, source_check=lambda: point.verify(self.fx.llm)), self.assertRaises(ValueError):
                self.fx.client.post("https://api.groq.com/openai/v1/chat/completions", json={**packet["body"], **changes})
        self.assertEqual(self.fx.calls, [])
        self.assertEqual(self.fx.pacer.state["requests"], [])

    def test_ledger_repeat_binding_changed_blocks_before_any_new_invocation(self) -> None:
        point = self.fx.prepare()
        journal = self.fx.journal()
        journal.run_point(point.point_id, execute=True)
        self.fx.pacer.state["requests"][0]["improvement_audit"]["slot"]["repeat_id"] = 1
        self.fx.pacer.save()
        with self.assertRaises(ValueError):
            journal.run_point(point.point_id, execute=True)
        self.assertEqual(len(self.fx.calls), 5)

    def test_unknown_numeric_or_foreign_branches_never_invoke_llm(self) -> None:
        point = self.fx.prepare()
        for branch in ("Numeric_only", "U_unknown"):
            with self.assertRaises(ValueError):
                point.packet(branch)
        self.assertEqual(self.fx.calls, [])

    def test_source_state_with_query_outcome_cannot_enter_packet_even_when_off(self) -> None:
        from core.unified_bayes_decision import DecisionPreparer
        from unified_execution_test_support import MODELS, SourcePoint, shared_state
        from unified_context_test_support import features
        state = shared_state("2021-01-04")
        state["outcome"] = {"net_return_pct": 100.}
        source = SourcePoint(features(self.inputs, "2021-01-04"), state)
        with patch("core.unified_bayes_decision.load_renderer_lock", return_value={}):
            producer = DecisionPreparer(self.context, self.fx.llm, MODELS)
        with self.assertRaises(ValueError):
            producer.prepare(source, state)
        self.assertEqual(self.fx.calls, [])

    def test_readonly_run_has_no_invocation_or_evaluation_and_no_secret_in_artifacts(self) -> None:
        point = self.fx.prepare()
        journal = self.fx.journal()
        with patch("agents.decision_agent._invoke_with_retry", side_effect=AssertionError("LLM")), \
             patch("core.prior_backtest.evaluate_point", side_effect=AssertionError("evaluation")):
            docs = journal.run_point(point.point_id)
        self.assertTrue(all(doc["status"] == "planned" for doc in docs.values()))
        self.assertEqual(self.fx.calls, [])
        journal.run_point(point.point_id, execute=True)
        for path in self.fx.root.rglob("*.json"):
            self.assertNotIn("fixture-secret", path.read_text("utf-8"))


if __name__ == "__main__":
    unittest.main()
