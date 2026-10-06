"""Crash/quota/atomic/lock và resume thật trên pipeline nghiên cứu với LLM fixture."""

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from core.backtest_engine import BacktestEngine, PRIOR_BRANCH_MODES
from core.bayesian_memory import atomic_write_json
from core.prior_backtest import canonical_hash
from core.prior_checkpoint import CheckpointSession, read_document, safe_error
from core.prior_run_lock import PriorRunLock, lock_handle, process_start, safe_path
import test_prior_backtest_integration as support


class Crash(BaseException):
    """Mô phỏng tiến trình chết mà không đi qua handler ghi error của runner."""


class PriorCheckpointTests(unittest.TestCase):
    setUp = support.PriorBacktestIntegrationTests.setUp
    run_fixture = support.PriorBacktestIntegrationTests.run_fixture
    read_payload = support.PriorBacktestIntegrationTests.read_payload

    def fresh_engine(self) -> None:
        """Tạo engine mới như tiến trình resume; giữ adapter/bank/model đã khóa."""
        self.engine = BacktestEngine(deepcopy(self.engine.config))
        self.engine.DELAY_BETWEEN_VARIANTS = self.engine.DELAY_BETWEEN_TESTS = 0.

    def point_file(self) -> Path:
        return self.output / f"points/FPT-{self.fx.cutoff}.json"

    def load_point(self) -> dict:
        return self.read_payload(self.point_file(), "point")

    def crash_at(self, event: str) -> None:
        """Chết sau một commit durable có tên xác định."""
        def fail(session, actual):
            if actual == event:
                raise Crash(event)
        with patch.object(CheckpointSession, "_after_commit", fail), self.assertRaises(Crash):
            self.run_fixture(cutoffs=(self.fx.cutoff,))

    def test_quota_key_rotation_resume_three_pending_no_upstream_and_keeps_attempts(self) -> None:
        invoke, attempts = self.llm.invoke, []
        self.llm.api_key = "secret-old-fixture"
        def quota(prompt):
            attempts.append(prompt)
            if len(attempts) == 3:
                raise RuntimeError("quota secret-old-fixture retry after 554.0 seconds")
            return invoke(prompt)
        with (patch.object(self.llm, "invoke", side_effect=quota),
              patch("agents.decision_agent._invoke_with_retry", side_effect=lambda fn, *args: fn(*args)),
              self.assertRaisesRegex(RuntimeError, "quota")):
            self.run_fixture(cutoffs=(self.fx.cutoff,))
        before = self.load_point()
        self.assertEqual(before["branches"]["recent"]["error"]["code"], "QUOTA")
        self.assertEqual(before["branches"]["recent"]["error"]["retry_after_seconds"], 554.)
        saved = deepcopy({name: before["branches"][name] for name in ("original", "random")})
        signature = before["run_signature"]
        self.llm.api_key = "secret-new-fixture"
        self.fresh_engine()
        result = self.run_fixture(cutoffs=(self.fx.cutoff,), resume=True)
        after = self.load_point()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(after["run_signature"], signature)
        self.assertEqual(self.events, ["indicator", "pattern", "trend", "full"])
        self.assertEqual(self.llm.calls, 5)
        for name, branch in saved.items():
            self.assertEqual(after["branches"][name], branch)
        self.assertEqual([a["status"] for a in after["branches"]["recent"]["attempts"]], ["failed", "complete"])
        for path in self.output.rglob("*.json"):
            self.assertNotIn("secret-old-fixture", path.read_text("utf-8"))
            self.assertNotIn("secret-new-fixture", path.read_text("utf-8"))
        self.assertEqual(json.loads((self.output / "run.owner.json").read_text("utf-8"))["owner_state"], "released")

    def test_resume_cleans_only_owned_writer_temps_under_lock(self) -> None:
        self.crash_at("shared_complete")
        orphan = self.point_file().with_name(f".{self.point_file().name}.abcd1234.tmp")
        unrelated = self.point_file().with_name("user.tmp")
        unknown = self.point_file().with_name(".unplanned.json.abcd1234.tmp")
        for path in (orphan, unrelated, unknown):
            path.write_text("Tệp kiểm thử", encoding="utf-8")
        before = self.point_file().read_bytes()
        self.fresh_engine()
        self.run_fixture(cutoffs=(self.fx.cutoff,), resume=True)
        self.assertFalse(orphan.exists())
        self.assertTrue(unrelated.exists())
        self.assertTrue(unknown.exists())
        self.assertNotEqual(before, self.point_file().read_bytes())
        self.assertEqual(self.events, ["indicator", "pattern", "trend", "full"])
        self.assertEqual(self.llm.calls, 5)

    def test_crash_at_each_durable_boundary_and_resume_matches_continuous(self) -> None:
        original_output = self.output
        self.run_fixture(cutoffs=(self.fx.cutoff,))
        continuous = self.load_point()
        boundaries = ("upstream_started", "upstream_complete", "full_started", "shared_complete",
            *(f"decision_started:{name}" for name in PRIOR_BRANCH_MODES),
            *(f"branch_complete:{name}" for name in PRIOR_BRANCH_MODES), "point_complete")
        for index, event in enumerate(boundaries):
            with self.subTest(event=event):
                self.output = self.fx.root / f"crash-{index}"
                self.fresh_engine()
                old_calls, old_events = self.llm.calls, len(self.events)
                self.crash_at(event)
                stopped = self.load_point()
                complete_names = [name for name, b in stopped["branches"].items() if b["status"] == "complete"]
                self.fresh_engine()
                if event in ("upstream_started", "full_started"):
                    calls_at_stop = self.llm.calls
                    with self.assertRaisesRegex(ValueError, "AMBIGUOUS"):
                        self.run_fixture(cutoffs=(self.fx.cutoff,), resume=True)
                    self.assertEqual(self.llm.calls, calls_at_stop)
                    continue
                saved = deepcopy({name: stopped["branches"][name] for name in complete_names})
                result = self.run_fixture(cutoffs=(self.fx.cutoff,), resume=True)
                after = self.load_point()
                self.assertEqual(result["status"], "complete")
                self.assertEqual(self.llm.calls - old_calls, 5)
                self.assertEqual(self.events[old_events:], ["indicator", "pattern", "trend", "full"])
                self.assertEqual(after["shared"], continuous["shared"])
                self.assertEqual(after["evaluation"], continuous["evaluation"])
                for name, branch in after["branches"].items():
                    self.assertEqual(branch["input"], continuous["branches"][name]["input"])
                    for key in ("action", "confidence", "risk_reward_ratio", "raw_response", "normalized_response", "decision_source", "fallback_reason"):
                        self.assertEqual(branch["decision"][key], continuous["branches"][name]["decision"][key])
                    if name in saved:
                        self.assertEqual(branch, saved[name])
                    if event == f"decision_started:{name}":
                        self.assertEqual([a["status"] for a in branch["attempts"]], ["unknown", "complete"])
        self.output = original_output

    def test_after_last_branch_before_seal_and_lost_result_resume_without_llm(self) -> None:
        self.crash_at("branch_complete:bayesian")
        self.assertIsNone(self.load_point()["evaluation"])
        calls = self.llm.calls
        self.fresh_engine()
        self.run_fixture(cutoffs=(self.fx.cutoff,), resume=True)
        sealed_bytes = self.point_file().read_bytes()
        (self.output / "results.json").write_text("hỏng", encoding="utf-8")
        self.fresh_engine()
        result = self.run_fixture(cutoffs=(self.fx.cutoff,), resume=True)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(self.llm.calls, calls)
        self.assertEqual(self.point_file().read_bytes(), sealed_bytes)

    def test_init_false_missing_planned_can_finish_but_initialized_missing_rejected(self) -> None:
        self.engine.stop()
        self.run_fixture()
        path = self.output / "run_manifest.json"
        envelope = json.loads(path.read_text("utf-8"))
        envelope["payload"]["initialized"] = False
        envelope["sha256"] = canonical_hash(envelope["payload"])
        atomic_write_json(path, envelope)
        self.point_file().unlink()  # Xóa duy nhất fixture trong TemporaryDirectory.
        self.fresh_engine()
        self.run_fixture(resume=True)
        self.assertEqual(self.llm.calls, 10)
        self.point_file().unlink()
        calls = self.llm.calls
        self.fresh_engine()
        with self.assertRaisesRegex(ValueError, "bị mất"):
            self.run_fixture(resume=True)
        self.assertEqual(self.llm.calls, calls)

    def test_failed_atomic_branch_write_keeps_previous_point_and_stops_api(self) -> None:
        replace = os.replace
        def fail(source, target):
            if Path(target).name == self.point_file().name:
                payload = json.loads(Path(source).read_text("utf-8"))["payload"]
                if payload["branches"]["random"]["status"] == "complete":
                    raise OSError("Đĩa fixture không ghi được")
            return replace(source, target)
        with patch("core.bayesian_memory.os.replace", side_effect=fail), self.assertRaises(OSError):
            self.run_fixture(cutoffs=(self.fx.cutoff,))
        stopped = self.load_point()
        self.assertEqual(stopped["branches"]["original"]["status"], "complete")
        self.assertEqual(stopped["branches"]["random"]["status"], "running")
        saved = deepcopy(stopped["branches"]["original"])
        self.assertEqual(self.llm.calls, 2)
        self.assertEqual(list(self.output.rglob("*.tmp")), [])
        self.fresh_engine()
        self.run_fixture(cutoffs=(self.fx.cutoff,), resume=True)
        self.assertEqual(self.load_point()["branches"]["original"], saved)
        self.assertEqual(self.llm.calls, 6)  # Chưa durable có thể lặp remote; complete không lặp.

    def test_atomic_failure_at_each_intent_prevents_following_api(self) -> None:
        replace = os.replace
        for stage in ("upstream_started", "full_started", "shared_complete", "decision_started"):
            with self.subTest(stage=stage):
                self.output = self.fx.root / f"disk-{stage}"
                self.fresh_engine()
                before_calls, before_events = self.llm.calls, len(self.events)
                def fail(source, target):
                    if Path(target).name == self.point_file().name:
                        doc = json.loads(Path(source).read_text("utf-8"))["payload"]
                        match = doc["shared"]["stage"] == stage
                        if stage == "decision_started":
                            match = doc["branches"]["original"]["status"] == "running"
                        if match:
                            raise OSError("Ghi intent fixture thất bại")
                    return replace(source, target)
                with patch("core.bayesian_memory.os.replace", side_effect=fail), self.assertRaises(OSError):
                    self.run_fixture(cutoffs=(self.fx.cutoff,))
                self.assertEqual(self.llm.calls, before_calls)
                if stage == "upstream_started":
                    self.assertEqual(len(self.events), before_events)
                elif stage == "full_started":
                    self.assertEqual(self.events[before_events:], ["indicator", "pattern", "trend"])
                else:
                    self.assertEqual(self.events[before_events:], ["indicator", "pattern", "trend", "full"])

    def test_keyboard_interrupt_persists_failure_and_releases_owned_handle(self) -> None:
        invoke = self.llm.invoke
        def interrupt(prompt):
            if self.llm.calls == 1:
                raise KeyboardInterrupt()
            return invoke(prompt)
        with patch.object(self.llm, "invoke", side_effect=interrupt), self.assertRaises(KeyboardInterrupt):
            self.run_fixture(cutoffs=(self.fx.cutoff,))
        stopped = self.load_point()
        self.assertEqual(stopped["branches"]["random"]["error"]["code"], "INTERRUPT")
        self.fresh_engine()
        self.run_fixture(cutoffs=(self.fx.cutoff,), resume=True)
        self.assertEqual(self.llm.calls, 5)

    def test_identity_config_plan_model_and_source_changes_refused_before_api(self) -> None:
        self.crash_at("branch_complete:original")
        before = self.point_file().read_bytes()
        calls = self.llm.calls
        for options in (dict(step=4, cutoffs=(self.fx.cutoff,)), dict(cutoffs=self.cutoffs)):
            self.fresh_engine()
            with self.assertRaises(ValueError):
                self.run_fixture(resume=True, **options)
        self.fresh_engine()
        self.engine.config["agent_llm_model"] = "Đổi model"
        with self.assertRaises(ValueError):
            self.run_fixture(cutoffs=(self.fx.cutoff,), resume=True)
        self.fresh_engine()
        bank = self.fx.root / "bank/bank.json"
        bank.write_text("[]", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.run_fixture(cutoffs=(self.fx.cutoff,), resume=True)
        self.assertEqual(self.llm.calls, calls)
        self.assertEqual(self.point_file().read_bytes(), before)

    def test_duplicate_keys_nonfinite_wrong_checksum_and_legacy_not_imported(self) -> None:
        self.engine.stop()
        self.run_fixture(cutoffs=(self.fx.cutoff,))
        path, original = self.point_file(), self.point_file().read_bytes()
        for text in ('{"payload":{},"payload":{}}', '{"payload":NaN,"sha256":"bad"}', '{"payload":{},"sha256":"bad"}'):
            path.write_text(text, encoding="utf-8")
            self.fresh_engine()
            with self.assertRaises(ValueError):
                self.run_fixture(cutoffs=(self.fx.cutoff,), resume=True)
        path.write_bytes(original)
        self.output = self.fx.root / "legacy"
        self.output.mkdir()
        legacy = self.output / "results.json"
        legacy.write_text('{"test_points":[]}', encoding="utf-8")
        before = legacy.read_bytes()
        with self.assertRaises(ValueError):
            self.run_fixture(cutoffs=(self.fx.cutoff,), resume=True)
        self.assertEqual(legacy.read_bytes(), before)
        self.assertEqual(len(list(self.output.iterdir())), 1)
        self.assertEqual(self.llm.calls, 0)

    def test_exception_sanitization_and_retry_logs_do_not_contain_credentials(self) -> None:
        from agents.decision_agent import _invoke_with_retry
        for error, code in ((RuntimeError("quota api_key=secret retry after 2m3s"), "QUOTA"),
                            (RuntimeError("429 token=secret retry after 4 seconds"), "RATE_LIMIT")):
            result = safe_error(error)
            self.assertEqual(result["code"], code)
            self.assertNotIn("secret", json.dumps(result))
        with patch("agents.decision_agent.time.sleep"), patch("builtins.print") as output:
            with self.assertRaises(RuntimeError) as failed:
                _invoke_with_retry(lambda: (_ for _ in ()).throw(RuntimeError("api_key=secret")), retries=2)
        self.assertNotIn("secret", str(failed.exception))
        self.assertNotIn("secret", str(output.call_args_list))


class PriorRunLockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.signature = "a" * 64

    def owner(self) -> dict:
        return json.loads((self.root / "run.owner.json").read_text("utf-8"))

    def test_os_lock_blocks_live_child_and_released_live_owner_can_reacquire(self) -> None:
        code = "from pathlib import Path; import sys; from core.prior_run_lock import PriorRunLock; lock=PriorRunLock(Path(sys.argv[1]),sys.argv[2]); lock.__enter__(); print('LOCKED',flush=True); sys.stdin.readline(); lock.__exit__()"
        child = subprocess.Popen([sys.executable, "-X", "utf8", "-c", code, str(self.root), self.signature],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), "LOCKED")
            with self.assertRaisesRegex(RuntimeError, "khóa OS"):
                with PriorRunLock(self.root, self.signature):
                    pass
            child.communicate("\n", timeout=30)
            self.assertEqual(child.returncode, 0)
            with PriorRunLock(self.root, self.signature):
                self.assertEqual(self.owner()["owner_state"], "active")
            with PriorRunLock(self.root, self.signature):
                pass
            self.assertEqual(self.owner()["owner_state"], "released")
            self.assertTrue((self.root / "run.lock").exists())
        finally:
            if child.poll() is None:
                child.kill()
                child.communicate(timeout=30)

    def test_dead_child_owner_recovered_without_deleting_lock_file(self) -> None:
        code = "from pathlib import Path; import sys,os; from core.prior_run_lock import PriorRunLock; lock=PriorRunLock(Path(sys.argv[1]),sys.argv[2]); lock.__enter__(); os._exit(0)"
        subprocess.run([sys.executable, "-X", "utf8", "-c", code, str(self.root), self.signature], check=True, timeout=60)
        dead = self.owner()
        with PriorRunLock(self.root, self.signature):
            self.assertNotEqual(self.owner()["owner_uuid"], dead["owner_uuid"])
        self.assertEqual(json.loads((self.root / "run.recovery.json").read_text("utf-8"))["records"][-1]["reason"], "dead")

    def test_pid_reuse_live_without_handle_other_host_and_unknown_liveness(self) -> None:
        with PriorRunLock(self.root, self.signature):
            pass
        original = self.owner()
        active = {**original, "owner_state": "active", "released_at": None}
        for owner, expected in ((active, RuntimeError), ({**active, "host_id": "other-host"}, ValueError),
                                ({**active, "owner_uuid": None}, ValueError)):
            atomic_write_json(self.root / "run.owner.json", owner)
            with self.assertRaises(expected):
                with PriorRunLock(self.root, self.signature):
                    pass
            self.assertEqual(self.owner(), owner)
        recycled = {**active, "process_start_time": "old-creation-id"}
        atomic_write_json(self.root / "run.owner.json", recycled)
        with PriorRunLock(self.root, self.signature):
            pass
        self.assertEqual(json.loads((self.root / "run.recovery.json").read_text("utf-8"))["records"][-1]["reason"], "pid_reused")
        atomic_write_json(self.root / "run.owner.json", active)
        real = process_start
        def unknown(pid):
            if pid != os.getpid():
                raise RuntimeError("Không xác định liveness")
            return real(pid)
        atomic_write_json(self.root / "run.owner.json", {**active, "pid": os.getpid() + 10_000})
        with patch("core.prior_run_lock.process_start", side_effect=unknown), self.assertRaises(RuntimeError):
            with PriorRunLock(self.root, self.signature):
                pass

    def test_release_failure_closes_handle_and_never_overwrites_different_owner(self) -> None:
        lock = PriorRunLock(self.root, self.signature)
        lock.__enter__()
        with patch("core.prior_run_lock.atomic_write_json", side_effect=OSError("Không ghi được owner")), self.assertRaises(OSError):
            lock.__exit__()
        self.assertIsNone(lock.handle)
        released = {**self.owner(), "owner_state": "released", "released_at": self.owner()["acquired_at"]}
        atomic_write_json(self.root / "run.owner.json", released)
        lock = PriorRunLock(self.root, self.signature)
        lock.__enter__()
        other = {**self.owner(), "owner_uuid": str(uuid4())}
        atomic_write_json(self.root / "run.owner.json", other)
        with self.assertRaises(ValueError):
            lock.__exit__()
        self.assertIsNone(lock.handle)
        self.assertEqual(self.owner(), other)

    def test_paths_reject_absolute_parent_and_symlink_escape(self) -> None:
        for path in ("../point.json", "C:/point.json", "/point.json", "points\\test.json"):
            with self.assertRaises(ValueError):
                safe_path(self.root, path)
        self.assertEqual(safe_path(self.root, "points/test.json"), (self.root / "points/test.json").resolve())
        resolve = Path.resolve
        outside = self.root.parent / "outside-fixture"
        def symlink(path, **kwargs):
            return outside if path == self.root / "link/point.json" else resolve(path, **kwargs)
        with patch.object(Path, "resolve", symlink), self.assertRaises(ValueError):
            safe_path(self.root, "link/point.json")

    def test_posix_backend_uses_descriptor_lock_and_propagates_busy(self) -> None:
        backend, handle = Mock(), Mock()
        backend.LOCK_EX, backend.LOCK_NB = 2, 4
        with patch("core.prior_run_lock.os.name", "posix"), patch.dict(sys.modules, {"fcntl": backend}):
            lock_handle(handle)
            backend.flock.assert_called_once_with(handle, 6)
            backend.flock.side_effect = BlockingIOError("Khóa fixture đang bận")
            with self.assertRaises(BlockingIOError):
                lock_handle(handle)


if __name__ == "__main__":
    unittest.main()
