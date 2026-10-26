"""Hồi quy riêng adapter mở journal; SDK/HTTP mock, không key hoặc API thật."""

from __future__ import annotations

from copy import deepcopy
from contextlib import nullcontext
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import httpx

from core.groq_pacing import PilotStop
from core.improvement_recovery import ResilientPacer
from core.research_cohort import read_envelope, save_envelope
from core.historical_signals import digest
from core.unified_bayes_cohort import CohortRun, lock_authorization, preflight
from core.unified_bayes_transport import UnifiedTransport
from scripts.run_unified_bayes import make_llm
from tools import resume_unified_bayes as adapter
from unified_cohort_test_support import make_cohort
from unified_context_test_support import dense_inputs, make_context
from unified_execution_test_support import ExecutionFixture, MODELS


class ResumeEntrypointTests(unittest.TestCase):
    """Đổi key và mở lại tiến trình vẫn giữ UUID, output và lịch sử ledger."""

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
        self.root = self.fx.root / "cohort"
        self.original = CohortRun(self.cohort, self.plan, self.fx.llm, self.root, self.fx.pacer.path, create=True)

    def resume(self, *, record: bool = True) -> adapter.ResumedCohort:
        """Mở đúng các file cũ bằng đường create=False của kernel."""
        return adapter.ResumedCohort(self.cohort, self.plan, self.fx.llm, self.root, self.fx.pacer.path, record=record)

    def completed(self) -> dict[Path, bytes]:
        """Đối soát byte mọi slot đã có kết quả trước lần phục hồi."""
        return {p: p.read_bytes() for p in (self.root / "journal/decisions").rglob("*.json")
                if read_envelope(p)["status"] == "complete"}

    def test_reproduces_legacy_create_error_and_resumes_without_rewriting_slots(self) -> None:
        pid = self.plan["schedule"][0]["point_id"]
        self.original.journal.run_point(pid, execute=True)
        before = self.completed()
        with self.assertRaisesRegex(ValueError, "identity"):
            CohortRun(self.cohort, self.plan, self.fx.llm, self.root, self.fx.pacer.path, create=True)
        self.assertEqual(self.resume().run()["primary"]["status"], "COMPLETE")
        for path, raw in before.items():
            self.assertEqual(path.read_bytes(), raw)

    def test_quota_stop_new_credential_keeps_unknown_uuid_and_old_ledger(self) -> None:
        def quota_after_original(_: httpx.Request) -> httpx.Response:
            if len(self.fx.calls) == 2:
                return httpx.Response(429, headers={"retry-after": "3600"},
                    json={"error": {"message": "Quota TPD per day"}})
            return self.fx.response()
        self.fx.handler = quota_after_original
        with self.assertRaises(PilotStop):
            self.original.run()
        unknown = next(p for p in (self.root / "journal/decisions").rglob("*.json")
                       if read_envelope(p)["status"] == "unknown")
        uid = read_envelope(unknown)["attempts"][0]["attempt_id"]
        before = self.completed()
        ledger = deepcopy(self.fx.pacer.state["requests"])
        self.fx.client.close()
        self.fx.pacer = ResilientPacer(self.fx.pacer.path, credential="fixture-replacement-key",
            amendment_sha256="a" * 64, clock=lambda: self.fx.now,
            sleep=lambda seconds: setattr(self.fx, "now", self.fx.now + seconds), policy="request_admission_v2")
        self.fx.transport = UnifiedTransport(self.fx.pacer, self.fx.root / "cache", httpx.MockTransport(self.fx.respond))
        self.fx.client = httpx.Client(transport=self.fx.transport)
        self.fx.llm = make_llm(MODELS, self.fx.client, "fixture-replacement-key")
        self.fx.handler = None
        self.assertEqual(self.resume().run()["primary"]["status"], "COMPLETE")
        self.assertEqual(read_envelope(unknown)["attempts"][0]["attempt_id"], uid)
        self.assertEqual(self.fx.pacer.state["requests"][:len(ledger)], ledger)
        self.assertEqual(len({r["credential_scope"] for r in self.fx.pacer.state["requests"]}), 2)
        for path, raw in before.items():
            self.assertEqual(path.read_bytes(), raw)
        success = [r["checkpoint_attempt_id"] for r in self.fx.pacer.state["requests"] if r["status"] == 200]
        self.assertEqual(len(success), len(set(success)))

    def test_complete_resume_and_repeat_reopen_do_not_replay_or_change_primary(self) -> None:
        run = self.resume()
        primary = deepcopy(run.run()["primary"])
        receipt = (self.root / adapter.RECEIPT_NAME).read_bytes()
        repeated = self.resume().run(repeats=True)
        self.assertEqual(repeated["primary"], primary)
        self.assertEqual(repeated["repeats"]["status"], "COMPLETE")
        before, count = self.completed(), len(self.fx.calls)
        self.resume().run()
        self.resume().run(repeats=True)
        self.assertEqual(count, len(self.fx.calls))
        self.assertEqual((self.root / adapter.RECEIPT_NAME).read_bytes(), receipt)
        for path, raw in before.items():
            self.assertEqual(path.read_bytes(), raw)

    def test_missing_slot_or_identity_is_rejected_without_reinitialization(self) -> None:
        row = self.plan["schedule"][0]
        path = self.original.journal.path(row["point_id"], 0, "Original")
        path.unlink()
        with self.assertRaises(FileNotFoundError):
            self.resume()
        self.assertFalse(path.exists())
        self.assertFalse((self.root / adapter.RECEIPT_NAME).exists())

    def test_adapter_or_receipt_drift_stops_before_http(self) -> None:
        run = self.resume()
        calls = len(self.fx.calls)
        with patch.object(adapter, "adapter_sha256", return_value="f" * 64), self.assertRaises(ValueError):
            run.run()
        path = self.root / adapter.RECEIPT_NAME
        saved = read_envelope(path)
        saved["policy"] = "CHANGED"
        save_envelope(path, saved)
        with self.assertRaises(ValueError):
            run.run()
        self.assertEqual(calls, len(self.fx.calls))

    def test_offline_handle_does_not_create_adapter_receipt(self) -> None:
        self.resume(record=False).report()
        self.assertFalse((self.root / adapter.RECEIPT_NAME).exists())
        self.assertEqual(self.fx.calls, [])

    def test_cli_routes_resume_to_existing_handle_and_restores_legacy_entrypoint(self) -> None:
        previous = adapter.cli.CohortRun
        previous_argv = sys.argv
        save_envelope(self.root / "preflight.json", {"status": "complete"})
        observed = []
        def dispatch() -> None:
            observed.append(sys.argv[1:])
            run = adapter.cli.CohortRun(self.cohort, self.plan, self.fx.llm, self.root, self.fx.pacer.path, create=True)
            self.assertIsInstance(run, adapter.ResumedCohort)
            raise RuntimeError("Ngắt entrypoint fixture")
        with patch.object(adapter.cli, "RUN_PATH", self.root), patch.object(adapter.cli, "main", side_effect=dispatch):
            with self.assertRaises(RuntimeError):
                adapter.main(["--run", "--resume", "--repeats", "--env-file", ".env"])
        self.assertEqual(observed[0][:2], ["--run", "--resume"])
        self.assertIn("--repeats", observed[0])
        self.assertEqual(observed[0][-2:], ["--env-file", ".env"])
        self.assertIs(adapter.cli.CohortRun, previous)
        self.assertIs(sys.argv, previous_argv)
        self.assertEqual(self.fx.calls, [])

    def test_online_requires_resume_and_completed_preflight_before_legacy_cli(self) -> None:
        with patch.object(adapter.cli, "main") as legacy, patch.object(adapter.cli, "RUN_PATH", self.root):
            with self.assertRaises(SystemExit):
                adapter.main(["--run"])
            with self.assertRaises(ValueError):
                adapter.main(["--run", "--resume"])
            with self.assertRaises(SystemExit):
                adapter.main(["--verify-only", "--env-file", ".env"])
            legacy.assert_not_called()

    def test_real_cli_online_dispatch_reopens_progressed_journal_without_replaying(self) -> None:
        """Chạy main CLI thật; chỉ thay biên nguồn/credential/HTTP/clock bằng fixture."""
        receipts = {"technical_gates_sha256": "c" * 64, "readiness_sha256": "d" * 64}
        authorization = lock_authorization(self.root, self.plan, receipts)
        self.fx.pacer.amendment_sha256 = digest(authorization)
        preflight(self.cohort, self.plan, self.fx.llm, self.root, execute=True)
        self.original.journal.run_point(self.plan["schedule"][0]["point_id"], execute=True)
        before = self.completed()
        source = self.fx.root / "source"
        source.mkdir()
        save_envelope(source / "plan.json", {"inputs": {"signal_config": {"models": MODELS}}})
        plan_path = self.fx.root / "plan.json"
        save_envelope(plan_path, self.plan)
        with patch.multiple(adapter.cli, ROOT=self.fx.root, SOURCE="source", PLAN_PATH=plan_path,
                            RUN_PATH=self.root, LEDGER=self.fx.pacer.path), \
             patch.object(adapter.cli, "load_source", return_value=self.cohort), \
             patch.object(adapter.cli, "authorize", return_value=receipts), \
             patch.object(adapter.cli, "tokenizer_cached", return_value=True), \
             patch.object(adapter.cli, "offline_client", return_value=nullcontext(self.fx.llm)), \
             patch.object(adapter.cli, "ResilientPacer", return_value=self.fx.pacer), \
             patch.object(adapter.cli, "UnifiedTransport", return_value=self.fx.transport), \
             patch.object(adapter.cli, "make_llm", return_value=self.fx.llm), \
             patch("dotenv.dotenv_values", return_value={"GROQ_API_KEY": "fixture-secret"}):
            adapter.main(["--run", "--resume", "--env-file", ".env"])
        report = read_envelope(self.root / "report.json")
        self.assertEqual(report["primary"]["status"], "COMPLETE")
        self.assertTrue((self.root / adapter.RECEIPT_NAME).is_file())
        for path, raw in before.items():
            self.assertEqual(path.read_bytes(), raw)
        success = [r["checkpoint_attempt_id"] for r in self.fx.pacer.state["requests"] if r["status"] == 200]
        self.assertEqual(len(success), len(set(success)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
