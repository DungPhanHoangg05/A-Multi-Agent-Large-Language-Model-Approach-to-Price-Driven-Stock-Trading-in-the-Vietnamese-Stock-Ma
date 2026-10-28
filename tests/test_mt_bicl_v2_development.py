"""Kiểm runner612 slot, audit/raw cache, phục hồi durable và sửa khóa preflight bằng namespace mới."""

from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
import io
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx

from core.improvement_recovery import ResilientPacer, ResilientTransport
from core.improvement_transport import SLOT
from core.mt_bicl_bank import content_hash
from core.mt_bicl_v2_api_preflight import MANIFEST_PATH, RECEIPT_PATH, client, manifest_facts, wire_body
from core.mt_bicl_v2_decision import JOURNAL_VERSION, invoke_decision
from core.mt_bicl_v2_development import (
    CODE, EXTENSION_PATH, EXTENSION_VERSION, LOCK, OUTPUT, REQUEST_VERSION, RUN, SLOT_VERSION,
    DevelopmentRun, GuardedHTTP, OfflineDispatch, api_preflight, audit_response, extension_facts,
    requests_from_parent, verify_extension, verify_parent,
)
from core.mt_bicl_v2_integration import OfflineDecisionFixture
from core.mt_bicl_v2_io import read_envelope, write_envelope
from core.mt_bicl_v2_release import RELEASE_PATH
from core.mt_bicl_v2_run_manifest import CODE as PARENT_CODE, MANIFEST_VERSION
from core.mt_bicl_v2_api_preflight import RECEIPT_VERSION
from core.mt_bicl_v21_preparation import file_hash
from core.prior_run_lock import PriorRunLock
from test_mt_bicl_v2_run_manifest import fixture


def response(request: httpx.Request) -> httpx.Response:
    """Response SDK giả, không truy cập API hoặc credential thật."""
    return httpx.Response(200, json={"id": "fixture", "object": "chat.completion", "created": 0,
        "model": "openai/gpt-oss-20b", "choices": [{"index": 0, "finish_reason": "stop", "message": {
            "role": "assistant", "content": json.dumps(OfflineDecisionFixture().invoke("")["parsed"], ensure_ascii=False)}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}})


class DevelopmentTests(unittest.TestCase):
    """Các file fixture ở Temp; chỉ dry-run mô phỏng đủ612 slot, không production API."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = TemporaryDirectory()
        root = Path(cls.tmp.name)
        for n in (*PARENT_CODE, RELEASE_PATH.as_posix()):
            p = root/n
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("{}", encoding="utf-8")
        cls.data = fixture()
        cls.manifest = manifest_facts(root, cls.data)
        cls.requests = [cls.data["requests"][(p["point_id"], p["repeat_index"], p["branch_id"])] for p in cls.manifest["requests"]]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.directory = self.root/"offline_fixture"
        self.runner = DevelopmentRun(self.root, self.directory, {"fixture": True}, self.manifest, self.requests, mode="offline_fixture")
        self.runner.initialize()
        self.dispatch = OfflineDispatch(self.root, self.directory, self.manifest)

    def intent(self, i: int = 0) -> dict:
        """Ghi scientific intent thật trước fixture HTTP, giống runner production."""
        from uuid import uuid4
        record = self.runner.empty(i)
        record.update(status="unknown", attempt_id=str(uuid4()))
        write_envelope(self.runner.path(i), SLOT_VERSION, record)
        return record

    def test_all612_exact_order_duplicate_independence_and_idempotent_resume(self) -> None:
        actual = []
        def dispatch(request: dict, slot: dict) -> dict:
            actual.append(slot["slot_index"])
            return self.dispatch(request, slot)
        before = deepcopy(self.requests)
        with redirect_stdout(io.StringIO()):
            result = self.runner.execute(dispatch, lambda: self.dispatch.state, self.dispatch.cache)
            calls = self.dispatch.calls
            repeated = self.runner.execute(dispatch, lambda: self.dispatch.state, self.dispatch.cache)
        self.assertEqual((result["primary_complete"], result["repeat_complete"], result["unknown_slots"]), (360, 252, 0))
        self.assertEqual(result["duplicate_complete"], 36)
        self.assertEqual(result["shared_off"], 96)
        self.assertEqual(calls, 516)
        self.assertEqual(actual, [p["slot_index"] for p in self.manifest["requests"] if not p["shared_off_eligible"]])
        self.assertEqual(result, repeated)
        self.assertEqual(self.dispatch.calls, calls)
        self.assertEqual(self.requests, before)

    def test_unknown_without_durable_response_never_replayed_or_cash(self) -> None:
        dispatch = Mock(side_effect=OSError("Fixture ngắt trước HTTP"))
        with self.assertRaises(OSError):
            self.runner.execute(dispatch, lambda: self.dispatch.state, self.dispatch.cache)
        record = read_envelope(self.runner.path(0), SLOT_VERSION)
        self.assertEqual(record["status"], "unknown")
        self.assertIsNone(record["decision"])
        with self.assertRaisesRegex(ValueError, "AMBIGUOUS_DECISION"):
            self.runner.execute(dispatch, lambda: self.dispatch.state, self.dispatch.cache)
        self.assertEqual(dispatch.call_count, 1)
        self.assertEqual(read_envelope(self.runner.path(0), SLOT_VERSION), record)

    def test_interrupted_after_success_recovers_same_uuid_offline_without_second_HTTP(self) -> None:
        record = self.intent()
        slot = self.runner.dispatch_slot(0, record)
        parsed = self.dispatch(self.requests[0], slot)
        records = self.runner.inspect(self.dispatch.state, self.dispatch.cache, recover=True)
        self.assertEqual(records[0]["status"], "complete")
        self.assertEqual(records[0]["attempt_id"], record["attempt_id"])
        self.assertEqual(records[0]["decision"], parsed)
        self.assertEqual(self.dispatch.calls, 1)
        self.runner.inspect(self.dispatch.state, self.dispatch.cache)
        self.assertEqual(self.dispatch.calls, 1)

    def test_raw_cache_tamper_cannot_be_hidden_by_checkpoint_self_hash(self) -> None:
        record = self.intent()
        self.dispatch(self.requests[0], self.runner.dispatch_slot(0, record))
        cache = next(self.dispatch.cache.glob("*.json"))
        cache.write_bytes(cache.read_bytes()+b" ")
        with self.assertRaisesRegex(ValueError, "cache"):
            self.runner.inspect(self.dispatch.state, self.dispatch.cache, recover=True)

    def test_raw_action_cannot_be_changed_in_complete_checkpoint(self) -> None:
        record = self.intent()
        self.dispatch(self.requests[0], self.runner.dispatch_slot(0, record))
        records = self.runner.inspect(self.dispatch.state, self.dispatch.cache, recover=True)
        records[0]["decision"]["decision"] = "LONG"
        write_envelope(self.runner.path(0), SLOT_VERSION, records[0])
        with self.assertRaisesRegex(ValueError, "raw response"):
            self.runner.inspect(self.dispatch.state, self.dispatch.cache)

    def test_missing_slot_after_ready_is_not_recreated(self) -> None:
        self.runner.path(17).unlink()
        with self.assertRaisesRegex(ValueError, "Mất slot"):
            self.runner.initialize()
        self.assertFalse(self.runner.path(17).exists())

    def test_missing_ready_after_intent_is_not_recreated(self) -> None:
        self.intent()
        (self.directory/"ready.json").unlink()
        with self.assertRaisesRegex(ValueError, "Mất ready"):
            self.runner.initialize()

    def test_fixture_namespace_cannot_be_migrated_to_research(self) -> None:
        other = DevelopmentRun(self.root, self.directory, {"fixture": True}, self.manifest, self.requests)
        with self.assertRaisesRegex(ValueError, "identity/mode"):
            other.initialize()

    def test_complete_shared_off_requires_durable_original(self) -> None:
        record = self.runner.empty(1)
        record.update(status="complete", shared_off_from=0, decision=OfflineDecisionFixture().invoke("")["parsed"])
        write_envelope(self.runner.path(1), SLOT_VERSION, record)
        with self.assertRaisesRegex(ValueError, "Shared-off"):
            self.runner.inspect(self.dispatch.state, self.dispatch.cache)

    def test_request_mutation_rejected_before_dispatch(self) -> None:
        requests = deepcopy(self.requests)
        requests[0]["model"] = "wrong-model"
        runner = DevelopmentRun(self.root, self.directory, {"fixture": True}, self.manifest, requests, mode="offline_fixture")
        dispatch = Mock()
        with self.assertRaisesRegex(ValueError, "request khác"):
            runner.execute(dispatch, lambda: self.dispatch.state, self.dispatch.cache)
        dispatch.assert_not_called()

    def test_transport_guard_rejects_wrong_body_before_inner_HTTP(self) -> None:
        inner = Mock(spec=httpx.BaseTransport)
        p = self.manifest["requests"][0]
        guard = GuardedHTTP({p["canonical_sha256"]: p["http_contract"]}, inner)
        token = SLOT.set({"canonical_sha256": p["canonical_sha256"]})
        try:
            with self.assertRaisesRegex(ValueError, "HTTP body"):
                guard.handle_request(httpx.Request("POST", "https://fixture.invalid", json={"model": "wrong", "messages": [{"role": "user", "content": "Fixture kiểm guard."}]}))
        finally:
            SLOT.reset(token)
        inner.handle_request.assert_not_called()

    def test_real_sdk_retry_transport_audit_and_raw_parser_on_one_slot(self) -> None:
        record = self.intent()
        slot = self.runner.dispatch_slot(0, record)
        pacer = ResilientPacer(self.directory/"sdk_ledger.json", credential="fixture-only", amendment_sha256="fixture", policy="request_admission_v2")
        expected = {p["canonical_sha256"]: p["http_contract"] for p in self.manifest["requests"]}
        transport = ResilientTransport(pacer, self.dispatch.cache, GuardedHTTP(expected, httpx.MockTransport(response)))
        with httpx.Client(transport=transport) as http:
            llm = client(self.manifest["decision"], http, "fixture-only")
            token = SLOT.set(slot)
            try:
                parsed = invoke_decision(llm, self.requests[0], attempt_id=slot["checkpoint_attempt_id"], run_signature=slot["run_signature"], branch_id=slot["branch_id"])
            finally:
                SLOT.reset(token)
        actual, ids = audit_response(self.root, self.dispatch.cache, pacer.state, slot, self.manifest["requests"][0]["http_contract"])
        self.assertEqual(actual, parsed)
        self.assertEqual(len(ids), 1)

    def test_operations_lock_does_not_modify_or_reuse_offline_owner(self) -> None:
        real_transport = ResilientTransport
        with patch("core.prior_run_lock.host_boot", return_value=("fixture-host", "fixture-boot")), patch("core.prior_run_lock.process_start", return_value="fixture-start"):
            with PriorRunLock(self.root/OUTPUT, "offline-signature"):
                pass
            previous = (self.root/OUTPUT/"run.owner.json").read_bytes()
            with PriorRunLock(self.root/LOCK, "operations-signature"), patch("core.improvement_recovery.ResilientTransport", side_effect=lambda p, c: real_transport(p, c, httpx.MockTransport(response))):
                saved = api_preflight(self.root, self.manifest, "fixture-only")
                self.assertEqual(saved["status"], "PASS")
                self.assertEqual(api_preflight(self.root, self.manifest, "fixture-only"), saved)
            self.assertEqual((self.root/OUTPUT/"run.owner.json").read_bytes(), previous)

    def test_parent_fixture_decisions_never_enter_request_snapshot(self) -> None:
        for block in self.manifest["layout"]["blocks"]:
            pid, r = block["point_id"], block["repeat_index"]
            branches = {}
            for name in block["order"]:
                base = "Original" if name == "Original_duplicate" else name
                request = next(self.requests[p["slot_index"]] for p in self.manifest["requests"] if p["point_id"] == pid and p["repeat_index"] == r and p["branch_id"] == name)
                branches[name] = {"request": request, "decision": {"decision": "LONG", "query_y": 1, "net_return": 999}}
            write_envelope(self.root/OUTPUT/"offline_dry_run"/str(r)/(pid+".json"), JOURNAL_VERSION, {"branches": branches})
        self.assertEqual(requests_from_parent(self.root, self.manifest), self.requests)

    def test_extension_self_reseal_or_changed_source_rejected(self) -> None:
        for n in (*CODE, MANIFEST_PATH.as_posix(), RECEIPT_PATH.as_posix()):
            p = self.root/n
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("{}", encoding="utf-8")
        facts = extension_facts(self.root, self.manifest, self.requests)
        extension = {**facts, "source_commit": "fixture", "confirmation_allowed": True}
        write_envelope(self.root/EXTENSION_PATH, EXTENSION_VERSION, extension)
        write_envelope(self.root/RUN/"requests.json", REQUEST_VERSION, {"requests": self.requests})
        with patch("core.mt_bicl_v2_development.requests_from_parent", return_value=self.requests), self.assertRaisesRegex(ValueError, "Extension khác"):
            verify_extension(self.root, parent=self.manifest, require_anchor=False)

    def test_parent_gate_rejects_changed_manifest_before_release_or_network(self) -> None:
        path = self.root/MANIFEST_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
        with patch("core.mt_bicl_v2_development.verify_release") as release, self.assertRaisesRegex(ValueError, "Parent manifest"):
            verify_parent(self.root)
        release.assert_not_called()

    def test_parent_gate_checks_frozen_source_and_upstream_without_fixture_replay(self) -> None:
        from core.research_cohort import save_envelope
        manifest = deepcopy(self.manifest)
        for name in (*PARENT_CODE, "snapshot.csv", "producer.py", "point.json", "journal.json", "dry.json"):
            path = self.root/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture", encoding="utf-8")
        manifest["source_sha256"] = {n: file_hash(self.root/n) for n in PARENT_CODE}
        cohort = {"sources": {"snapshot.csv": file_hash(self.root/"snapshot.csv")},
                  "plan": {"runtime": {"fixture": True}, "code_sha256": {"producer.py": hashlib.sha256(b"fixture").hexdigest()}}}
        save_envelope(self.root/"cohort.json", cohort)
        manifest["upstream"] = {"cohort_path": "cohort.json", "cohort_sha256": file_hash(self.root/"cohort.json"),
            "points": {"fixture": {"point_path": "point.json", "point_sha256": file_hash(self.root/"point.json"),
                                   "journal_path": "journal.json", "journal_sha256": file_hash(self.root/"journal.json")}}}
        dry = self.root/OUTPUT/"dry.json"
        dry.parent.mkdir(parents=True, exist_ok=True)
        dry.write_text("fixture", encoding="utf-8")
        write_envelope(self.root/MANIFEST_PATH, MANIFEST_VERSION, manifest)
        receipt = {"manifest_payload_sha256": content_hash(manifest), "wire_preflight": {"status": "PASS"},
                   "dry_run": {"status": "PASS", "journals_sha256": {"dry.json": file_hash(dry)}}}
        write_envelope(self.root/RECEIPT_PATH, RECEIPT_VERSION, receipt)
        def anchor(args: list, **kwargs: dict) -> SimpleNamespace:
            return SimpleNamespace(returncode=0, stdout=(self.root/args[-1].split(":", 1)[1]).read_bytes())
        with patch("core.mt_bicl_v2_development.PARENT_SHA256", file_hash(self.root/MANIFEST_PATH)), \
             patch("core.mt_bicl_v2_development.PARENT_RECEIPT_SHA256", file_hash(self.root/RECEIPT_PATH)), \
             patch("core.mt_bicl_v2_development.subprocess.run", side_effect=anchor), \
             patch("core.mt_bicl_v2_development.runtime_identity", return_value={"fixture": True}), \
             patch("core.mt_bicl_v2_development.verify_release", return_value={"runtime": manifest["runtime"], "decision": manifest["decision"]}):
            self.assertEqual(verify_parent(self.root), (manifest, receipt))
            (self.root/"point.json").write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "point/journal"):
                verify_parent(self.root)
