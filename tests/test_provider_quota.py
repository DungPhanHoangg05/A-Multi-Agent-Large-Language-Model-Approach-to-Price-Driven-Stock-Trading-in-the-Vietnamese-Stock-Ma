"""Quota ngày từ provider, đổi key và lịch sử audit không phụ thuộc API thật."""

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

import httpx

from core.bayesian_memory import atomic_write_json, read_json
from core.groq_pacing import GroqPacer, MODEL_LIMITS, PacedGroqTransport, PilotStop
from core.provider_quota import POLICY, ProviderQuotaPacer, rejected_attempts
from core.research_invocation import ENABLED, invocation_scope
from core.research_cohort import save_envelope


class ProviderQuotaTests(unittest.TestCase):
    """Giữ các rào chắn phút/HTTP; bỏ riêng admission ngày local."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "usage.json"
        self.now = 100000.
        self.model = "openai/gpt-oss-20b"
        self.checksum = "a" * 64

    def sleep(self, seconds: float) -> None:
        """Đồng hồ giả tiến đúng thời gian nghỉ, không sleep thật."""
        self.now += seconds

    def pacer(self, credential: str = "credential-A") -> ProviderQuotaPacer:
        """Mỗi lần dựng lại mô phỏng một lần đổi key hoặc resume."""
        return ProviderQuotaPacer(self.path, credential=credential, amendment_sha256=self.checksum,
            policy="request_admission_v2", clock=lambda:self.now, monotonic=lambda:self.now, sleep=self.sleep)

    def test_local_daily_exhaustion_no_longer_blocks_and_old_records_unchanged(self) -> None:
        old = [{"id": f"old-{i}", "model": self.model, "reserved_tokens": 8000,
                "started_at": self.now-1000, "status": "unknown"} for i in range(30)]
        atomic_write_json(self.path, {"version":1, "limits":MODEL_LIMITS, "requests":old,
            "last_stop":{"reason":"DAILY_QUOTA"}})
        legacy = GroqPacer(self.path, clock=lambda:self.now)
        with self.assertRaises(PilotStop):
            legacy.daily_budget(self.model, 1, 8000)
        pacer = self.pacer()
        pacer.before_point()
        row = pacer.reserve(self.model, 8000)
        self.assertEqual(read_json(self.path)["requests"][:30], old)
        self.assertEqual(row["daily_policy"], POLICY)
        self.assertEqual(len(pacer.state["requests"]), 31)
        # Cả usage ngày của chính key mới cũng không phát DAILY_QUOTA local.
        for record in pacer.state["requests"][:30]:
            record["credential_scope"] = pacer.credential_scope
        pacer.save()
        self.assertEqual(pacer.daily_budget(self.model, 1, 8000)["remaining_tokens"], 0)
        pacer.before_point()

    def test_same_key_keeps_provider_daily_stop_changed_key_can_send_and_preserves_history(self) -> None:
        first = self.pacer()
        row = first.reserve(self.model, 1)
        row.update(status=200, completed_at=self.now, rate_limits={"x-ratelimit-remaining-requests":"0",
            "x-ratelimit-reset-requests":"1h"})
        first.save()
        original = deepcopy(read_json(self.path)["requests"])
        with self.assertRaises(PilotStop):
            self.pacer().before_point()
        second = self.pacer("credential-B")
        second.before_point()
        second.reserve(self.model, 1)
        saved = read_json(self.path)
        self.assertEqual(saved["requests"][:1], original)
        self.assertEqual(len(saved["requests"]), 2)
        self.assertNotIn("credential-A", self.path.read_text())
        self.assertNotIn("credential-B", self.path.read_text())

    def test_same_key_retains_minute_pacing_across_restart(self) -> None:
        first = self.pacer()
        first.reserve(self.model, 8000)
        second = self.pacer()
        second.reserve(self.model, 1)
        self.assertEqual(self.now, 100061.)
        self.assertEqual(len(second.state["requests"]), 2)

    def test_http_429_is_retried_with_one_budget_and_success_returns_full_telemetry(self) -> None:
        pacer = self.pacer()
        count = []
        def respond(request: httpx.Request) -> httpx.Response:
            count.append(request)
            if len(count) == 1:
                return httpx.Response(429, headers={"retry-after":"1"}, json={"error":{"message":"retry after 1 seconds"}})
            return httpx.Response(200, json={"id":"fixture-response", "usage":{"total_tokens":1}})
        token = ENABLED.set(True)
        try:
            with httpx.Client(transport=PacedGroqTransport(pacer, httpx.MockTransport(respond))) as client:
                with invocation_scope("fixture"):
                    response = client.post("https://api.groq.com/openai/v1/chat/completions", json={
                        "model":self.model, "messages":[{"role":"user","content":"ok"}], "max_tokens":1})
        finally:
            ENABLED.reset(token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([r["status"] for r in pacer.state["requests"]], [429,200])
        self.assertEqual({r["credential_scope"] for r in pacer.state["requests"]}, {pacer.credential_scope})
        self.assertEqual(len(pacer.state["invocations"]), 1)

    def test_transport_error_does_not_retry_or_disappear_on_key_change(self) -> None:
        pacer = self.pacer()
        def fail(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("Lỗi giả lập", request=request)
        with httpx.Client(transport=PacedGroqTransport(pacer, httpx.MockTransport(fail))) as client:
            with self.assertRaises(PilotStop):
                client.post("https://api.groq.com/openai/v1/chat/completions", json={
                    "model":self.model,"messages":[{"role":"user","content":"ok"}],"max_tokens":1})
        self.assertEqual(len(read_json(self.path)["requests"]),1)
        self.assertEqual(self.pacer("credential-B").state["requests"][0]["status"],"transport_error")

    def test_preflight_scope_stamps_only_matching_request_ids(self) -> None:
        first = self.pacer()
        row = first.reserve(self.model, 1)
        first.state["preflight"] = {"status":"PASS","request_ids":[row["id"]]}
        first.save()
        self.assertEqual(first.state["preflight"]["credential_scope"],first.credential_scope)
        second = self.pacer("credential-B")
        second.save()
        self.assertEqual(read_json(self.path)["preflight"]["credential_scope"], first.credential_scope)


class ProviderRejectionTests(unittest.TestCase):
    """Quota từ chối được audit; timeout và response thành công không tự replay."""

    def test_only_all_429_for_exact_checkpoint_identity_are_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            target = run / "candidates/C3/point.json"
            atomic_write_json(target, {"point_id":"FPT-2023-07-05","run_signature":"s",
                "attempts":[{"attempt_id":"attempt", "status":"unknown", "authorization":None}]})
            ledger = run / "usage.json"
            base = {"checkpoint_attempt_id":"attempt","point_id":"FPT-2023-07-05","run_signature":"s"}
            for statuses, expected in (([429], ["attempt"]), ([429,429], ["attempt"]),
                    ([200], []), ([429,200], []), (["transport_error"], []), ([], [])):
                with self.subTest(statuses=statuses):
                    atomic_write_json(ledger, {"requests":[{**base,"status":value} for value in statuses]})
                    self.assertEqual(rejected_attempts(run, ledger),expected)
            atomic_write_json(ledger, {"requests":[{**base,"status":429,"run_signature":"wrong"}]})
            self.assertEqual(rejected_attempts(run, ledger),[])

    def test_proven_provider_admission_stop_without_http_is_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            target = run / "candidates/C3/point.json"
            atomic_write_json(target, {"point_id":"FPT-2023-07-05","run_signature":"s",
                "attempts":[{"attempt_id":"attempt", "status":"unknown", "authorization":None}]})
            ledger = run / "usage.json"
            stop = {"reason":"PROVIDER_DAILY_QUOTA","daily_policy":POLICY,"checkpoint_attempt_id":"attempt",
                    "point_id":"FPT-2023-07-05","run_signature":"s"}
            atomic_write_json(ledger,{"requests":[],"last_stop":stop})
            self.assertEqual(rejected_attempts(run,ledger),["attempt"])
            atomic_write_json(ledger,{"requests":[],"last_stop":{**stop,"reason":"DAILY_QUOTA"}})
            self.assertEqual(rejected_attempts(run,ledger),[])

    def test_base_running_or_failed_quota_attempt_uses_existing_uuid_and_skips_approved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            target = run / "v1/FPT/points/point.json"
            ledger = run / "usage.json"
            atomic_write_json(ledger,{"requests":[{"status":429,"checkpoint_attempt_id":"attempt",
                "point_id":"FPT-2023-07-05","run_signature":"s"}]})
            for status in ("running","failed"):
                atomic_write_json(target,{"point_id":"FPT-2023-07-05","run_signature":"s","branches":{
                    "original":{"attempts":[{"attempt_id":"attempt","status":status}]}}})
                self.assertEqual(rejected_attempts(run,ledger),["attempt"])
            save_envelope(run / "replay_authorizations.json",{"attempts":{"attempt":{"reason":"Đã đối soát"}}})
            self.assertEqual(rejected_attempts(run,ledger),[])


if __name__ == "__main__":
    unittest.main()
