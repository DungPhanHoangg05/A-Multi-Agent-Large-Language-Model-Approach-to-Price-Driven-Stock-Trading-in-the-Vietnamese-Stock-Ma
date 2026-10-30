"""Kiểm journal/recovery/paired v3 với SDK/mock HTTP thật, không dùng ledger tài khoản."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx

from core.improvement_recovery import ResilientPacer
from core.improvement_transport import SLOT
from core.mt_bicl_bank import content_hash
from core.mt_bicl_v2_development import GuardedHTTP
from core.mt_bicl_v2_io import read_envelope, write_envelope
from core.mt_bicl_v2_teacher import BetaBernoulliTeacher
from core.mt_bicl_v3_context import prepare_variants
from core.mt_bicl_v3_contracts import REVISION_BRANCHES
from core.mt_bicl_v3_freeze import OUTPUT, fixture_reply, legacy_fixture
from core.mt_bicl_v3_preflight import serialization, control_run, verify_controls, CONTROL_VERSION
from core.mt_bicl_v3_run import DevelopmentRun, SLOT_VERSION
from core.mt_bicl_v3_transport import BudgetTransport, BudgetHTTP
from core.mt_bicl_v3_wire import client, invoke, REPLY_NAME
from mt_bicl_v3_support import episode, protocol, shared


class BudgetFixture:
    """Không sleep thật hoặc mở counter repository; dùng để fault-inject hard cap."""

    def __init__(self) -> None:
        self.remaining = 100000.

    def check(self, required: float = 0.) -> None:
        if self.remaining <= 0 or required > self.remaining: raise RuntimeError("Hết cap fixture")

    def checkpoint(self) -> None:
        pass


class RecoveryTests(unittest.TestCase):
    """Mỗi test ledger/cache riêng; response fixture không được dùng như nghiên cứu thật."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.protocol = protocol()
        value = episode()
        cls.facts = value["v3"]["query_facts"]
        cls.variants = prepare_variants(value, BetaBernoulliTeacher([1/16]*16), lambda _: .6)["branches"]

    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pid = self.facts["point_id"]
        names = ["Original", "A_reference", "Fact_Anchor", *REVISION_BRANCHES, "Original_duplicate"]
        self.manifest = {"layout": {"slots": [{"slot_index": i, "point_id": self.pid, "point_index": 0, "repeat_index": 1, "branch_id": name} for i, name in enumerate(names)]},
                         "request_bounds": {self.pid: {name: {"reserved_tokens_upper": 8000} for name in names}}}
        self.snapshot = {"protocol": self.protocol, "points": {self.pid: {"facts": self.facts, "shared": shared(self.facts), "variants": deepcopy(self.variants), "a_reference": {"prefix": "A fixture"}}}}
        self.budget = BudgetFixture()
        self.now = [1800000000.]
        self.calls = []
        self.bad_anchor = False
        self.fail_before = False
        self.fail_after = False
        self.interrupt_HTTP = False
        self.expected = {}
        self.pacer = ResilientPacer(self.root/"ledger.json", credential="offline-fixture", amendment_sha256="0"*64,
            policy="request_admission_v2", clock=lambda: self.now[0], monotonic=lambda: self.now[0], sleep=lambda n: self.now.__setitem__(0, self.now[0]+n))
        def respond(request: httpx.Request) -> httpx.Response:
            slot = SLOT.get()
            self.calls.append(deepcopy(slot))
            if self.interrupt_HTTP: raise KeyboardInterrupt
            anchored = json.loads(request.content)["response_format"]["json_schema"]["name"] == REPLY_NAME
            parsed = fixture_reply(self.facts) if anchored else legacy_fixture("LONG")
            if anchored and slot["branch_id"] != "Fact_Anchor": parsed["context_reason"] = "SUPPORTED"
            if self.bad_anchor and slot["branch_id"] == "Fact_Anchor": parsed["fact_assertions"]["MACD_ZERO"] = "NEGATIVE"
            self.now[0] += 61.
            return httpx.Response(200, json={"id": "fixture", "object": "chat.completion", "created": 0, "model": "openai/gpt-oss-20b",
                "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": json.dumps(parsed, ensure_ascii=False)}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 20, "total_tokens": 40}})
        transport = BudgetTransport(self.pacer, self.root/"cache", self.budget, GuardedHTTP(self.expected, httpx.MockTransport(respond)))
        self.http = httpx.Client(transport=transport)
        self.addCleanup(self.http.close)
        self.llm = client(self.protocol["decision"]["config"], self.http, "offline-fixture")

    def runner(self) -> DevelopmentRun:
        return DevelopmentRun(self.root/"run", self.manifest, self.snapshot, mode="offline_fixture")

    def dispatch(self, request: dict, slot: dict) -> dict:
        if self.fail_before: raise KeyboardInterrupt
        self.expected[slot["canonical_sha256"]] = serialization(self.llm, request)[0]
        token = SLOT.set(slot)
        try: result = invoke(self.llm, request, slot)
        finally: SLOT.reset(token)
        if self.fail_after: raise KeyboardInterrupt
        return result

    def execute(self, dispatch=None) -> dict:
        return self.runner().execute(dispatch or self.dispatch, lambda r: serialization(self.llm, r), lambda: self.pacer.state,
                                     self.root/"cache", self.budget.check, self.budget.checkpoint)

    def test_all_slots_complete_replay_no_HTTP_and_duplicate_independent(self) -> None:
        result = self.execute()
        self.assertEqual(result["complete_slots"], 9)
        before = len(self.calls)
        self.execute(lambda *_: self.fail("Không replay complete"))
        self.assertEqual(len(self.calls), before)
        original = next(s for s in self.calls if s["branch_id"] == "Original")
        duplicate = next(s for s in self.calls if s["branch_id"] == "Original_duplicate")
        self.assertNotEqual(original["checkpoint_attempt_id"], duplicate["checkpoint_attempt_id"])
        self.assertEqual(original["canonical_sha256"], duplicate["canonical_sha256"])

    def test_cache_durable_recovered_before_callback_or_key(self) -> None:
        self.manifest["layout"]["slots"] = self.manifest["layout"]["slots"][:1]
        self.fail_after = True
        with self.assertRaises(KeyboardInterrupt): self.execute()
        saved = read_envelope(self.runner().path(0), SLOT_VERSION)
        self.assertEqual(saved["status"], "unknown")
        result = self.execute(lambda *_: self.fail("Cache phải phục hồi trước key/API"))
        self.assertEqual((result["complete_slots"], len(self.calls)), (1, 1))
        self.assertEqual(read_envelope(self.runner().path(0), SLOT_VERSION)["attempt_id"], saved["attempt_id"])

    def test_incomplete_retry_same_UUID_without_reset(self) -> None:
        self.manifest["layout"]["slots"] = self.manifest["layout"]["slots"][:1]
        self.fail_before = True
        with self.assertRaises(KeyboardInterrupt): self.execute()
        old = read_envelope(self.runner().path(0), SLOT_VERSION)
        self.fail_before = False
        self.execute()
        self.assertEqual(self.calls[0]["checkpoint_attempt_id"], old["attempt_id"])

    def test_bad_anchor_bypasses_all_revisions_keeps_Original_LONG(self) -> None:
        self.bad_anchor = True
        result = self.execute()
        self.assertEqual(result["bypass_slots"], 5)
        self.assertEqual(len(self.calls), 4)
        for i in range(3, 8):
            row = read_envelope(self.runner().path(i), SLOT_VERSION)
            self.assertEqual((row["policy"]["final_action"], row["policy"]["reason"], row["attempt_id"]), ("LONG", "ANCHOR_INVALID_USE_ORIGINAL", None))

    def test_future_completed_gap_is_rejected_before_new_HTTP(self) -> None:
        runner = self.runner()
        runner.initialize()
        row = runner.empty(self.manifest["layout"]["slots"][-1])
        row["status"] = "complete"
        write_envelope(runner.path(8), SLOT_VERSION, row)
        with self.assertRaises(ValueError): self.execute()
        self.assertFalse(self.calls)

    def test_complete_cache_tamper_never_replays(self) -> None:
        self.execute()
        row = self.pacer.state["requests"][0]
        path = self.root/"cache"/(row["id"]+".json")
        path.write_bytes(path.read_bytes()+b" ")
        before = len(self.calls)
        with self.assertRaises(ValueError): self.execute()
        self.assertEqual(len(self.calls), before)

    def test_fixture_cannot_be_promoted_to_research_identity(self) -> None:
        self.execute()
        with self.assertRaises(ValueError):
            DevelopmentRun(self.root/"run", self.manifest, self.snapshot, mode="research").initialize()

    def test_missing_identity_after_ready_cannot_be_recreated(self) -> None:
        self.runner().initialize()
        (self.root/"run/identity.json").unlink()
        with self.assertRaises(ValueError): self.execute()
        self.assertFalse(self.calls)

    def test_missing_ready_after_intent_cannot_be_recreated(self) -> None:
        self.fail_before = True
        with self.assertRaises(KeyboardInterrupt): self.execute()
        (self.root/"run/ready.json").unlink()
        with self.assertRaises(ValueError): self.execute()
        self.assertFalse(self.calls)

    def test_unknown_HTTP_reserve_kept_and_same_UUID_retried(self) -> None:
        self.manifest["layout"]["slots"] = self.manifest["layout"]["slots"][:1]
        self.interrupt_HTTP = True
        with self.assertRaises(KeyboardInterrupt): self.execute()
        old = deepcopy(self.pacer.state["requests"][0])
        self.assertEqual(old["status"], "unknown")
        self.interrupt_HTTP = False
        self.now[0] += 61.
        self.execute()
        self.assertEqual(self.pacer.state["requests"][0], old)
        rows = self.pacer.state["requests"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["checkpoint_attempt_id"], old["checkpoint_attempt_id"])
        self.assertGreater(old["reserved_tokens"], 0)

    def test_duplicate_ledger_id_is_rejected_without_HTTP(self) -> None:
        self.execute()
        self.pacer.state["requests"].append(deepcopy(self.pacer.state["requests"][0]))
        before = len(self.calls)
        with self.assertRaises(ValueError): self.execute()
        self.assertEqual(len(self.calls), before)

    def test_control_four_schemas_durable_replay_and_cold_serializer(self) -> None:
        manifest = {"request_bounds": {"fixture": {"branch": {"max_prompt_chars": 6100}}}}
        expected, calls = {}, []
        def respond(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            parsed = legacy_fixture()
            if body["response_format"]["json_schema"]["name"] == REPLY_NAME:
                parsed = fixture_reply({"assertions": {"MACD_SIGNAL": "UNKNOWN", "MACD_ZERO": "UNKNOWN", "PRICE_SMA20": "UNKNOWN"}})
            calls.append(deepcopy(SLOT.get()))
            self.now[0] += 61.
            return httpx.Response(200, json={"id": "fixture", "object": "chat.completion", "created": 0, "model": "openai/gpt-oss-20b",
                "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": json.dumps(parsed)}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 20, "total_tokens": 40}})
        transport = BudgetTransport(self.pacer, self.root/OUTPUT/"run/http_cache", self.budget, GuardedHTTP(expected, httpx.MockTransport(respond)))
        with httpx.Client(transport=transport) as http:
            llm = client(self.protocol["decision"]["config"], http, "offline-fixture")
            proof = control_run(self.root, manifest, self.snapshot, self.pacer, llm, expected, self.budget)
            self.assertEqual(control_run(self.root, manifest, self.snapshot, self.pacer, llm, expected, self.budget), proof)
            self.assertEqual(len(calls), 4)
        with patch("core.mt_bicl_v3_preflight.read_json", return_value=self.pacer.state):
            self.assertEqual(verify_controls(self.root, manifest, self.snapshot, self.pacer.credential_scope), proof)
            path = self.root/proof["controls"][0]["path"]
            saved = read_envelope(path, CONTROL_VERSION)
            saved["contract"]["model"] = "changed-model"
            write_envelope(path, CONTROL_VERSION, saved)
            with self.assertRaises(ValueError): verify_controls(self.root, manifest, self.snapshot, self.pacer.credential_scope)
        self.assertEqual(len(calls), 4)

    def test_budget_HTTP_checks_before_network_and_wait_bound(self) -> None:
        sent = []
        inner = BudgetHTTP(self.budget, httpx.MockTransport(lambda r: sent.append(r) or httpx.Response(200)))
        self.budget.remaining = 5.
        with self.assertRaises(RuntimeError): inner.handle_request(httpx.Request("POST", "https://offline.invalid"))
        self.assertFalse(sent)
        with self.assertRaises(RuntimeError): self.http._transport._wait(10.)


if __name__ == "__main__":
    unittest.main()
