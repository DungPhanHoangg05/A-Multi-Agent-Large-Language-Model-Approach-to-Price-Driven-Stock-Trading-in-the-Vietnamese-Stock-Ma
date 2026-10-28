"""Kiểm resume một lệnh: interruption, cache, quota ngày và thay credential tự preflight."""

from __future__ import annotations

import base64
from copy import deepcopy
from contextlib import nullcontext, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

import httpx

from core.historical_signals import digest
from core.bayesian_memory import atomic_write_json, read_json
from core.groq_pacing import MODEL_LIMITS
from core.improvement_recovery import ResilientPacer
from core.improvement_transport import SLOT, body_contract
from core.mt_bicl_bank import content_hash
from core.mt_bicl_v2_api_preflight import client, manifest_facts, preflight_request, wire_body
from core.mt_bicl_v2_continuation import (
    ContinuationTransport, credential_preflight, finish_durable, inspect_prefix, resume_unknown,
)
from core.mt_bicl_v2_decision import invoke_decision
from core.mt_bicl_v2_development import DevelopmentRun, GuardedHTTP, OfflineDispatch, SLOT_VERSION
from core.mt_bicl_v2_integration import OfflineDecisionFixture
from core.mt_bicl_v2_io import read_envelope, write_envelope
from core.mt_bicl_v2_release import RELEASE_PATH
from core.mt_bicl_v2_run_manifest import CODE as PARENT_CODE
from core.mt_bicl_v21_preparation import file_hash
from core.research_cohort import read_envelope as read_cached, save_envelope as save_cached
from test_mt_bicl_v2_run_manifest import fixture


def response() -> dict:
    """Groq payload giả hợp lệ cho SDK thật, không có dữ liệu hoặc key production."""
    return {"id": "fixture", "object": "chat.completion", "created": 0, "model": "openai/gpt-oss-20b",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant",
                "content": json.dumps(OfflineDecisionFixture().invoke("")["parsed"], ensure_ascii=False)}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}}


class ContinuationTests(unittest.TestCase):
    """Mỗi test dùng Temp và mock HTTP, không truy cập env/key hoặc gọi API thật."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = TemporaryDirectory()
        root = Path(cls.tmp.name)
        for name in (*PARENT_CODE, RELEASE_PATH.as_posix()):
            path = root/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}", encoding="utf-8")
        data = fixture()
        cls.manifest = manifest_facts(root, data)
        cls.requests = [data["requests"][(p["point_id"], p["repeat_index"], p["branch_id"])] for p in cls.manifest["requests"]]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runner = DevelopmentRun(self.root, self.root/"run", {"fixture": True}, self.manifest, self.requests, mode="offline_fixture")
        self.runner.initialize()
        self.record = self.runner.empty(0)
        self.record.update(status="unknown", attempt_id=str(uuid4()))
        write_envelope(self.runner.path(0), SLOT_VERSION, self.record)
        self.fixture = OfflineDispatch(self.root, self.runner.directory, self.manifest)
        self.slot = self.runner.dispatch_slot(0, self.record)

    def dispatch(self, request: dict, slot: dict) -> dict:
        """Fixture bổ sung metadata transport thật mà verifier incomplete yêu cầu."""
        parsed = self.fixture(request, slot)
        self.fixture.state["requests"][-1].update(recovery_policy="resilient_invocation_v1", dispatch_phase="audited")
        return parsed

    def old_http(self, status: str | int, reserved: bool = False) -> dict:
        """Intent/HTTP chưa complete của lần chạy trước; không sửa hoặc xóa reserve cũ."""
        row = {"id": str(uuid4()), "status": status, "model": "openai/gpt-oss-20b", "reserved_tokens": 4408,
               "checkpoint_attempt_id": self.record["attempt_id"], "run_signature": self.runner.signature,
               "point_id": self.slot["point_id"], "branch_id": self.slot["branch_id"],
               "dispatch_phase": "reserved" if reserved else "audited", "recovery_policy": "resilient_invocation_v1",
               "improvement_audit": None if reserved else {"audit_version": "improvement_http_audit_v1", "slot": self.slot,
                   "request": deepcopy(self.manifest["requests"][0]["http_contract"]),
                   "response": None if status in ("unknown", "transport_error") else {"body_sha256": "f"*64, "message_sha256": None}}}
        self.fixture.state["requests"].append(row)
        return row

    def resume(self, dispatch: object | None = None) -> list:
        """Cùng một đường resume tự chọn UUID, không flag retry theo từng loại lỗi."""
        return resume_unknown(self.runner, lambda: self.fixture.state, self.fixture.cache, lambda: None,
                              dispatch or self.dispatch, {"authorized": "single command"}, "fixture-scope")

    def test_interrupt_before_any_http_auto_resumes_same_uuid(self) -> None:
        records = self.resume()
        self.assertEqual(records[0]["status"], "complete")
        self.assertEqual(records[0]["attempt_id"], self.record["attempt_id"])
        self.assertEqual(self.fixture.calls, 1)

    def test_reserved_before_send_transport_error_and429_auto_resume_preserve_rows(self) -> None:
        for status, reserved in (("unknown", True), ("transport_error", False), (429, False)):
            old = self.old_http(status, reserved)
            before = deepcopy(old)
            self.assertEqual(inspect_prefix(self.runner, self.fixture.state, self.fixture.cache)[0]["status"], "unknown")
            # Một intent có thể giữ đồng thời nhiều HTTP chưa xác định/quota từ chối.
            self.assertEqual(old, before)
        old_rows = deepcopy(self.fixture.state["requests"])
        records = self.resume()
        self.assertEqual(records[0]["status"], "complete")
        self.assertEqual(self.fixture.state["requests"][:-1], old_rows)
        self.assertEqual(self.fixture.calls, 1)

    def test_lost_unstamped_http200_response_retries_same_uuid_with_audit(self) -> None:
        row = self.old_http(200)
        before = deepcopy(row)
        records = self.resume()
        self.assertEqual(records[0]["request_ids"][0], row["id"])
        self.assertEqual(self.fixture.state["requests"][0], before)
        self.assertEqual(len(records[0]["request_ids"]), 2)

    def test_durable_success_recovered_without_second_dispatch(self) -> None:
        self.dispatch(self.requests[0], self.slot)
        never = Mock(side_effect=AssertionError("Không được gọi lại success"))
        result = self.resume(never)
        self.assertEqual(result[0]["status"], "complete")
        never.assert_not_called()
        self.resume(never)
        never.assert_not_called()

    def test_crash_between_cache_write_and_stamp_finishes_audited_cache(self) -> None:
        self.dispatch(self.requests[0], self.slot)
        row = self.fixture.state["requests"][0]
        del row["durable_response"]
        save = Mock()
        result = finish_durable(self.runner, self.fixture.state, self.fixture.cache, save)
        self.assertEqual(result[0]["status"], "complete")
        self.assertIn("durable_response", row)
        self.assertEqual(self.fixture.state["continuation_events"][0]["event"], "COMPLETE_UNSTAMPED_CACHE")
        save.assert_called_once()

    def test_missing_or_tampered_stamped_cache_stops_before_network(self) -> None:
        self.dispatch(self.requests[0], self.slot)
        cache = next(self.fixture.cache.glob("*.json"))
        original = cache.read_bytes()
        cache.write_bytes(original+b" ")
        with self.assertRaisesRegex(ValueError, "bị sửa"):
            self.resume()
        cache.unlink()
        with self.assertRaisesRegex(ValueError, "Mất raw cache"):
            self.resume()
        self.assertEqual(self.fixture.calls, 1)

    def test_changed_audit_or_request_or_complete_action_is_not_silently_retried(self) -> None:
        row = self.old_http(429)
        row["improvement_audit"]["request"]["canonical_body_sha256"] = "tampered"
        with self.assertRaisesRegex(ValueError, "HTTP body/audit"):
            self.resume()
        self.assertEqual(self.fixture.calls, 0)

    def test_interrupted_retry_keeps_original_uuid_and_durable_authorization(self) -> None:
        before = self.runner.path(0).read_bytes()
        with self.assertRaises(KeyboardInterrupt):
            self.resume(Mock(side_effect=KeyboardInterrupt))
        self.assertEqual(self.runner.path(0).read_bytes(), before)
        self.assertEqual(len(list((self.runner.directory/"continuation_authorizations").glob("*.json"))), 1)

    def test_complete_action_tamper_still_stops_with_new_resume_verifier(self) -> None:
        self.dispatch(self.requests[0], self.slot)
        result = self.resume()
        result[0]["decision"]["decision"] = "LONG"
        write_envelope(self.runner.path(0), SLOT_VERSION, result[0])
        with self.assertRaisesRegex(ValueError, "raw response"):
            inspect_prefix(self.runner, self.fixture.state, self.fixture.cache)

    def test_one_default_command_changed_key_and_unknown429_finishes_all612(self) -> None:
        import scripts.continue_mt_bicl_development as command
        old = self.old_http(429)
        old.update(started_at=0., credential_scope="previous-key-scope")
        atomic_write_json(self.root/"ledger.json", {"version": 1, "limits": MODEL_LIMITS, "requests": [old]})
        before = deepcopy(old)
        now = [1793232000.]
        calls = []
        real_pacer = ResilientPacer
        def make_pacer(path: Path, **kwargs: object) -> ResilientPacer:
            return real_pacer(path, **kwargs, clock=lambda: now[0], sleep=lambda s: now.__setitem__(0, now[0]+s))
        def respond(request: httpx.Request) -> httpx.Response:
            calls.append(deepcopy(SLOT.get()))
            return httpx.Response(200, json=response())
        with patch.object(command, "ROOT", self.root), patch.object(command, "RUN", Path("run")), \
             patch.object(command, "LEDGER", "ledger.json"), patch.object(command, "LOCK", Path("operations")), \
             patch.object(command, "PriorRunLock", side_effect=lambda *a, **k: nullcontext()), \
             patch.object(command, "verify_extension", return_value=({"fixture": True}, self.manifest, self.requests)), \
             patch.object(command, "verify", return_value={"authorization": "user single command"}), \
             patch.object(command, "DevelopmentRun", return_value=self.runner), \
             patch.object(command, "dotenv_values", return_value={"GROQ_API_KEY": "fake-new-key"}), \
             patch.object(command, "ResilientPacer", side_effect=make_pacer), \
             patch("httpx.HTTPTransport", side_effect=lambda **kwargs: httpx.MockTransport(respond)), \
             patch("sys.argv", ["continue_mt_bicl_development.py"]), redirect_stdout(io.StringIO()):
            self.assertEqual(command.main(), 0)
        ledger = read_json(self.root/"ledger.json")
        records = self.runner.inspect(ledger, self.fixture.cache)
        self.assertEqual(sum(r["status"] == "complete" for r in records), 612)
        self.assertEqual(ledger["requests"][0], before)
        self.assertEqual(sum(s["branch_id"] == "credential_preflight" for s in calls), 1)
        scientific = [s for s in calls if s["branch_id"] != "credential_preflight"]
        self.assertEqual(scientific[0]["checkpoint_attempt_id"], self.record["attempt_id"])
        self.assertEqual(len(scientific), 516)

    def test_credential_change_auto_preflights_new_key_and_preserves_old_proof(self) -> None:
        directory, ledger = self.root/"preflights", self.root/"ledger.json"
        calls = []
        def respond(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(200, json=response())
        old_proof = None
        for key in ("fake-key-a", "fake-key-a", "fake-key-b"):
            pacer = ResilientPacer(ledger, credential=key, amendment_sha256="fixture", policy="request_admission_v2")
            expected = {}
            transport = ContinuationTransport(pacer, directory/"http_cache", GuardedHTTP(expected, httpx.MockTransport(respond)))
            with httpx.Client(transport=transport) as http:
                llm = client(self.manifest["decision"], http, key)
                request = preflight_request()
                expected[content_hash(request)] = body_contract(wire_body(llm, request))
                proof = credential_preflight(directory, self.manifest, self.runner.signature, pacer, llm)
            self.assertEqual(proof["status"], "PASS")
            if old_proof is None:
                old_proof = (directory/(pacer.credential_scope+".json"), (directory/(pacer.credential_scope+".json")).read_bytes())
            self.assertEqual(old_proof[0].read_bytes(), old_proof[1])
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(list(directory.glob("*.json"))), 2)
        # Control request có signature riêng, không bị coi là orphan scientific slot.
        inspect_prefix(self.runner, pacer.state, self.fixture.cache)

    def test_interrupt_during_credential_preflight_resumes_same_control_uuid(self) -> None:
        directory = self.root/"preflights"
        pacer = ResilientPacer(self.root/"ledger.json", credential="fake-key", amendment_sha256="fixture", policy="request_admission_v2")
        attempts = []
        def respond(request: httpx.Request) -> httpx.Response:
            attempts.append(request)
            if len(attempts) == 1:
                raise KeyboardInterrupt()
            return httpx.Response(200, json=response())
        expected = {}
        with httpx.Client(transport=ContinuationTransport(pacer, directory/"http_cache", GuardedHTTP(expected, httpx.MockTransport(respond)))) as http:
            llm = client(self.manifest["decision"], http, "fake-key")
            control = preflight_request()
            expected[content_hash(control)] = body_contract(wire_body(llm, control))
            with self.assertRaises(KeyboardInterrupt):
                credential_preflight(directory, self.manifest, self.runner.signature, pacer, llm)
            proof = credential_preflight(directory, self.manifest, self.runner.signature, pacer, llm)
        ids = {r["checkpoint_attempt_id"] for r in pacer.state["requests"]}
        self.assertEqual(len(ids), 1)
        self.assertEqual(proof["status"], "PASS")

    def test_daily_quota_waits_reset_then_continues_same_http_uuid(self) -> None:
        now = [1793232000.]
        pacer = ResilientPacer(self.root/"ledger.json", credential="fake-key", amendment_sha256="fixture", policy="request_admission_v2",
                              clock=lambda: now[0], sleep=lambda s: now.__setitem__(0, now[0]+s))
        calls = []
        def respond(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            if len(calls) == 1:
                return httpx.Response(429, json={"error": {"message": "TPD daily limit, retry after 1 seconds"}},
                                      headers={"retry-after": "1", "x-ratelimit-remaining-requests": "0", "x-ratelimit-reset-requests": "1s"})
            return httpx.Response(200, json=response())
        expected = {p["canonical_sha256"]: p["http_contract"] for p in self.manifest["requests"]}
        with httpx.Client(transport=ContinuationTransport(pacer, self.fixture.cache, GuardedHTTP(expected, httpx.MockTransport(respond)))) as http:
            llm = client(self.manifest["decision"], http, "fake-key")
            token = SLOT.set(self.slot)
            try:
                parsed = invoke_decision(llm, self.requests[0], attempt_id=self.record["attempt_id"], run_signature=self.runner.signature, branch_id=self.slot["branch_id"])
            finally:
                SLOT.reset(token)
        self.assertEqual(parsed["decision"], "SHORT")
        self.assertEqual(len(calls), 2)
        self.assertGreater(now[0], 1793232000.)
        self.assertEqual({r["checkpoint_attempt_id"] for r in pacer.state["requests"]}, {self.record["attempt_id"]})

    def test_invalid_cached_schema_is_repaired_without_reusing_bad_response_forever(self) -> None:
        self.dispatch(self.requests[0], self.slot)
        row = self.fixture.state["requests"][0]
        path = self.fixture.cache/(row["id"]+".json")
        raw = read_cached(path)
        bad = response()
        bad["choices"][0]["message"]["content"] = "not-json"
        body = json.dumps(bad).encode()
        raw["body_base64"] = base64.b64encode(body).decode()
        save_cached(path, raw)
        row["durable_response"] = {"sha256": file_hash(path)}
        row["improvement_audit"]["response"] = {"body_sha256": hashlib.sha256(body).hexdigest(),
            "message_sha256": digest({"content": "not-json", "tool_calls": []})}
        row.update(model="openai/gpt-oss-20b", started_at=0., reserved_tokens=4408, total_tokens=20, invocation_id="previous")
        pacer = ResilientPacer(self.root/"ledger.json", credential="fake-key", amendment_sha256="fixture", policy="request_admission_v2")
        pacer.state["requests"].append(row)
        old = deepcopy(row)
        calls = []
        def respond(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(200, json=response())
        expected = {p["canonical_sha256"]: p["http_contract"] for p in self.manifest["requests"]}
        with httpx.Client(transport=ContinuationTransport(pacer, self.fixture.cache, GuardedHTTP(expected, httpx.MockTransport(respond)))) as http:
            llm = client(self.manifest["decision"], http, "fake-key")
            def dispatch(request: dict, slot: dict) -> dict:
                token = SLOT.set(slot)
                try:
                    return invoke_decision(llm, request, attempt_id=slot["checkpoint_attempt_id"], run_signature=slot["run_signature"], branch_id=slot["branch_id"])
                finally:
                    SLOT.reset(token)
            result = resume_unknown(self.runner, lambda: pacer.state, self.fixture.cache, pacer.save, dispatch, {}, pacer.credential_scope)
        self.assertEqual(result[0]["status"], "complete")
        self.assertEqual(len(calls), 1)
        self.assertEqual(row, old)


if __name__ == "__main__":
    unittest.main()
