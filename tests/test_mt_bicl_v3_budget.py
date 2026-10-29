"""Kiểm counter18 giờ resume, clean pause và hard crash bằng đồng hồ/OS lock fixture."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from core.mt_bicl_v2_io import read_envelope, write_envelope
from core.mt_bicl_v3_budget import BudgetStop, RuntimeBudget, VERSION


class Clock:
    """Đồng hồ giả tách UTC/monotonic, không sleep hoặc tiêu runtime thực nghiệm."""

    def __init__(self) -> None:
        self.utc = datetime(2026, 10, 30, tzinfo=timezone.utc)
        self.tick = 0.

    def advance(self, seconds: float) -> None:
        """Cộng thời gian fixture một lần cho cả pacing và hoạt động CPU giả."""
        self.utc += timedelta(seconds=seconds)
        self.tick += seconds


class BudgetTests(unittest.TestCase):
    """Chỉ ghi trong TemporaryDirectory; không materialize counter v3 của repository."""

    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.clock = Clock()
        self.lock_patch = patch("core.mt_bicl_v3_budget.PriorRunLock")
        factory = self.lock_patch.start()
        def lock(root: Path, signature: str):
            """Giữ hiệu ứng tạo thư mục của khóa OS, không lấy owner máy thật trong fixture."""
            from unittest.mock import MagicMock
            root.mkdir(parents=True, exist_ok=True)
            return MagicMock()
        factory.side_effect = lock
        self.addCleanup(self.lock_patch.stop)

    def budget(self, stage: str = "offline_validation") -> RuntimeBudget:
        """Một root/counter cho mọi stage, không truyền cap hoặc path riêng từng run."""
        return RuntimeBudget(self.root, stage, now=lambda: self.clock.utc, monotonic=lambda: self.clock.tick)

    def test_import_constructor_does_not_create_counter(self) -> None:
        value = self.budget()
        self.assertFalse(value.path.exists())
        self.assertEqual(value.identity["cap_seconds"], 64800)

    def test_resume_stages_and_W12_share_counter_clean_pause_excludes_downtime(self) -> None:
        with self.budget() as first:
            self.clock.advance(10.)
            first.checkpoint()
            self.clock.advance(20.)
        self.clock.advance(3600.)
        with self.budget("confirmation_if_released") as second:
            self.assertEqual(second.used(), 30.)
            self.clock.advance(40.)
        saved = read_envelope(second.path, VERSION)
        self.assertEqual(saved["elapsed_seconds"], 70.)
        self.assertIsNone(saved["active_since"])
        self.assertEqual({s["stage"] for s in saved["sessions"]}, {"offline_validation", "confirmation_if_released"})

    def test_crash_gap_conservative_and_capped_not_fresh_grant(self) -> None:
        first = self.budget()
        first.__enter__()
        self.clock.advance(15.)
        first.checkpoint()
        self.clock.advance(100.)
        with self.budget("development") as recovered:
            self.assertEqual(recovered.used(), 115.)
        saved = read_envelope(first.path, VERSION)
        self.assertEqual(sum(s["charged_seconds"] for s in saved["sessions"] if s["kind"] == "CRASH_GAP_CONSERVATIVE"), 100.)
        self.clock.advance(70000.)
        with self.budget() as fresh:
            self.assertEqual(fresh.used(), 115.)

    def test_cap_and_wait_precheck_stop_keep_counter(self) -> None:
        with self.budget() as value:
            self.clock.advance(64799.)
            with self.assertRaises(BudgetStop): value.check(2.)
            value.check(.5)
            self.clock.advance(2.)
            with self.assertRaises(BudgetStop): value.check()
        with self.assertRaises(BudgetStop):
            self.budget("report_replay").__enter__()
        self.assertEqual(read_envelope(value.path, VERSION)["elapsed_seconds"], 64800.)

    def test_crash_past_data_stop_bounded_and_clean_deadline_stop(self) -> None:
        self.clock.utc = datetime.fromisoformat("2026-11-07T23:59:49+07:00")
        first = self.budget()
        first.__enter__()
        self.clock.advance(100.)
        with self.assertRaises(BudgetStop): self.budget("cold_verification").__enter__()
        saved = read_envelope(first.path, VERSION)
        self.assertEqual(saved["elapsed_seconds"], 10.)
        self.assertIsNone(saved["active_since"])

    def test_counter_tamper_missing_or_identity_change_not_reset(self) -> None:
        with self.budget() as value: self.clock.advance(10.)
        saved = read_envelope(value.path, VERSION)
        saved["elapsed_seconds"] = 0.
        write_envelope(value.path, VERSION, saved)
        with self.assertRaises(ValueError): self.budget().__enter__()
        saved["elapsed_seconds"] = 10.
        saved["identity"]["cap_seconds"] = 999999
        write_envelope(value.path, VERSION, saved)
        with self.assertRaises(ValueError): self.budget().__enter__()
        value.path.unlink()
        (value.path.parent/"checkpoint.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Mất counter"): self.budget().__enter__()

    def test_clock_rollback_raises_and_CtrlC_cleanly_closes(self) -> None:
        with self.assertRaises(KeyboardInterrupt):
            with self.budget() as value:
                self.clock.advance(3.)
                raise KeyboardInterrupt
        self.assertIsNone(read_envelope(value.path, VERSION)["active_since"])
        first = self.budget()
        first.__enter__()
        self.clock.utc -= timedelta(seconds=1)
        with self.assertRaises(ValueError): self.budget().__enter__()

    def test_real_OS_lock_rejects_concurrent_session_then_allows_resume(self) -> None:
        self.lock_patch.stop()
        with self.budget() as first:
            with self.assertRaisesRegex(RuntimeError, "khóa OS"):
                self.budget("development").__enter__()
            self.clock.advance(2.)
        with self.budget("cold_verification") as second:
            self.assertEqual(second.used(), 2.)
        second.path.unlink()
        with self.assertRaisesRegex(ValueError, "Mất counter"):
            self.budget().__enter__()


if __name__ == "__main__":
    unittest.main()
