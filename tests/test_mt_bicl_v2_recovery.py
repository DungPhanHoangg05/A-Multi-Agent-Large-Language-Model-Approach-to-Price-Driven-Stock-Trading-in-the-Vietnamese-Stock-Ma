"""Kiểm phục hồi429 cùng UUID; không dùng API hoặc sửa runner đã freeze."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock
from uuid import uuid4

from core.mt_bicl_v2_api_preflight import manifest_facts
from core.mt_bicl_v2_development import DevelopmentRun, OfflineDispatch, SLOT_VERSION
from core.mt_bicl_v2_io import read_envelope, write_envelope
from core.mt_bicl_v2_recovery import eligible, retry_rejected
from core.mt_bicl_v2_release import RELEASE_PATH
from core.mt_bicl_v2_run_manifest import CODE as PARENT_CODE
from test_mt_bicl_v2_run_manifest import fixture


class RecoveryTests(unittest.TestCase):
    """Một unknown đầu run và HTTP giả để kiểm đúng policy429 mà không chạy lại612 slot."""

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
        self.tmpcase = TemporaryDirectory()
        self.addCleanup(self.tmpcase.cleanup)
        self.root = Path(self.tmpcase.name)
        self.runner = DevelopmentRun(self.root, self.root/"fixture", {"fixture": True}, self.manifest, self.requests, mode="offline_fixture")
        self.runner.initialize()
        self.dispatch = OfflineDispatch(self.root, self.runner.directory, self.manifest)
        self.record = self.runner.empty(0)
        self.record.update(status="unknown", attempt_id=str(uuid4()))
        write_envelope(self.runner.path(0), SLOT_VERSION, self.record)
        slot = self.runner.dispatch_slot(0, self.record)
        self.rejected = {"id": str(uuid4()), "status": 429, "dispatch_phase": "audited", "reserved_tokens": 4408,
            "checkpoint_attempt_id": self.record["attempt_id"], "run_signature": self.runner.signature,
            "point_id": slot["point_id"], "branch_id": slot["branch_id"], "recovery_policy": "resilient_invocation_v1",
            "durable_response": None, "improvement_audit": {"audit_version": "improvement_http_audit_v1", "slot": slot,
                "request": deepcopy(self.manifest["requests"][0]["http_contract"]),
                "response": {"body_sha256": "f"*64, "message_sha256": None}}}
        self.dispatch.state["requests"] = [self.rejected]

    def test_retry_preserves_uuid_rejection_reserve_and_appends_success(self) -> None:
        old = deepcopy(self.rejected)
        result = retry_rejected(self.runner, lambda: self.dispatch.state, self.dispatch.cache,
                                self.record["attempt_id"], self.dispatch, {"fixture_recovery": True})
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["attempt_id"], self.record["attempt_id"])
        self.assertEqual(self.dispatch.state["requests"][0], old)
        self.assertEqual(len(result["request_ids"]), 2)
        self.assertEqual(self.dispatch.calls, 1)
        self.assertEqual(len(list((self.runner.directory/"recovery_authorizations").glob("*.json"))), 1)
        self.runner.inspect(self.dispatch.state, self.dispatch.cache)

    def test_complete_never_replayed_even_if_explicit_command_repeated(self) -> None:
        result = retry_rejected(self.runner, lambda: self.dispatch.state, self.dispatch.cache,
                                self.record["attempt_id"], self.dispatch, {})
        never = Mock()
        self.assertEqual(retry_rejected(self.runner, lambda: self.dispatch.state, self.dispatch.cache,
                                      self.record["attempt_id"], never, {}), result)
        never.assert_not_called()

    def test_transport_or_unknown_or_other_http_not_accepted_as_rejection(self) -> None:
        for status in ("unknown", "transport_error", 503):
            self.rejected["status"] = status
            with self.subTest(status=status), self.assertRaisesRegex(ValueError, "429"):
                eligible(self.runner, self.dispatch.state, self.dispatch.cache, self.record["attempt_id"])
        self.assertEqual(self.dispatch.calls, 0)

    def test_no_http_record_is_not_proof_of_rejection(self) -> None:
        self.dispatch.state["requests"] = []
        with self.assertRaisesRegex(ValueError, "chưa có HTTP429"):
            eligible(self.runner, self.dispatch.state, self.dispatch.cache, self.record["attempt_id"])

    def test_wrong_uuid_or_audit_body_or_slot_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "UUID không thuộc"):
            eligible(self.runner, self.dispatch.state, self.dispatch.cache, str(uuid4()))
        self.rejected["improvement_audit"]["request"]["canonical_body_sha256"] = "wrong"
        with self.assertRaisesRegex(ValueError, "429"):
            eligible(self.runner, self.dispatch.state, self.dispatch.cache, self.record["attempt_id"])

    def test_cached_or_message_bearing_response_cannot_be_retried_as429(self) -> None:
        self.rejected["improvement_audit"]["response"]["message_sha256"] = "unexpected-model-message"
        with self.assertRaisesRegex(ValueError, "429"):
            eligible(self.runner, self.dispatch.state, self.dispatch.cache, self.record["attempt_id"])
        self.rejected["improvement_audit"]["response"]["message_sha256"] = None
        self.dispatch.cache.mkdir(parents=True)
        (self.dispatch.cache/(self.rejected["id"]+".json")).write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "429"):
            eligible(self.runner, self.dispatch.state, self.dispatch.cache, self.record["attempt_id"])

    def test_interrupt_keeps_same_unknown_intent_and_authorization(self) -> None:
        before = self.runner.path(0).read_bytes()
        with self.assertRaises(KeyboardInterrupt):
            retry_rejected(self.runner, lambda: self.dispatch.state, self.dispatch.cache,
                           self.record["attempt_id"], Mock(side_effect=KeyboardInterrupt), {})
        self.assertEqual(self.runner.path(0).read_bytes(), before)
        self.assertEqual(len(list((self.runner.directory/"recovery_authorizations").glob("*.json"))), 1)

    def test_old_ledger_row_must_remain_byte_equivalent_in_content(self) -> None:
        def mutate(request: dict, slot: dict) -> dict:
            parsed = self.dispatch(request, slot)
            self.dispatch.state["requests"][0]["reserved_tokens"] = 1
            return parsed
        with self.assertRaisesRegex(ValueError, "Ledger/reserve"):
            retry_rejected(self.runner, lambda: self.dispatch.state, self.dispatch.cache,
                           self.record["attempt_id"], mutate, {})
        self.assertEqual(read_envelope(self.runner.path(0), SLOT_VERSION)["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
