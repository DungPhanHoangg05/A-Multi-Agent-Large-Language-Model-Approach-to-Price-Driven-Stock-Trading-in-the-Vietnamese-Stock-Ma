"""Kiểm thay key giữa episode mà không lặp hay sửa checkpoint khi lỗi."""

from __future__ import annotations

from contextlib import redirect_stdout
from datetime import datetime
import io
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from core.bayesian_memory import atomic_write_json, read_json
from core.historical_signals import digest
from scripts.resume_historical_memory import (
    COOLDOWN_FILE, archive_interrupted_point, check_cooldown, current_key, resume, run_batch,
)


class HistoricalMemoryKeyResumeTests(unittest.TestCase):
    def test_new_key_loaded_for_each_episode_without_logging_or_manifest_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "run"
            output.mkdir()
            env_file = root / ".env"
            env_file.write_text("GROQ_API_KEY=old-secret\n", encoding="utf-8")
            atomic_write_json(output / "run_manifest.json", {"test": True})
            atomic_write_json(output / "memory.json", [{"episode_id": "first"}])
            identity = {"symbols": ["FPT"], "start": "2018-01-01", "end": "2022-12-31",
                        "models": {"graph_llm_model": "qwen/qwen3.8-27b"}}
            observed = []

            def one_point(command, env):
                observed.append((list(command), env["GROQ_API_KEY"], env["HISTORICAL_LLM_GAP_SECONDS"]))
                records = read_json(output / "memory.json")
                records.append({"episode_id": f"new-{len(records)}"})
                atomic_write_json(output / "memory.json", records)
                if len(observed) == 1:
                    env_file.write_text("GROQ_API_KEY=new-secret\n", encoding="utf-8")
                return 0, None

            with patch("scripts.resume_historical_memory.HistoricalMemoryRunner") as runner, \
                    patch("scripts.resume_historical_memory.run_batch", side_effect=one_point):
                runner._read_envelope.return_value = identity
                runner.return_value.plan.return_value = {"eligible_count": 3}
                output_text = io.StringIO()
                with redirect_stdout(output_text):
                    status = resume(output, env_file=env_file, batch_size=1)
            self.assertEqual(status, {"completed": 3, "remaining": 0, "new_points": 2})
            self.assertEqual([key for _, key, _ in observed], ["old-secret", "new-secret"])
            self.assertTrue(all(gap == "75.0" for _, _, gap in observed))
            self.assertTrue(all(command[4].endswith("run_paced_historical_memory.py")
                                and command[-1] == "2022-12-31" for command, _, _ in observed))
            self.assertEqual(read_json(output / "run_manifest.json"), {"test": True})
            self.assertNotIn("old-secret", output_text.getvalue())
            self.assertNotIn("new-secret", output_text.getvalue())
            self.assertTrue(all("old-secret" not in command and "new-secret" not in command
                                for command, _, _ in observed))

    def test_failed_batch_keeps_completed_episode_and_incomplete_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "run"
            output.mkdir()
            env_file = root / ".env"
            env_file.write_text("GROQ_API_KEY=secret\n", encoding="utf-8")
            checkpoint = output / "signals/FPT-2020-06-04.json"
            point = {"symbol": "FPT", "as_of_date": "2020-06-04"}

            def failed_point(command, env):
                atomic_write_json(output / "memory.json", [{"episode_id": "settled"}])
                atomic_write_json(output / "episodes/FPT-2020-06-01.json", {"record": "settled"})
                payload = {"stage": "UPSTREAM_STARTED", "signature": "a" * 64}
                atomic_write_json(checkpoint, {"payload": payload, "sha256": digest(payload)})
                (output / "run.lock").touch()
                checkpoint.with_suffix(".lock").touch()
                return 1, 1000.0

            with patch("scripts.resume_historical_memory.HistoricalMemoryRunner") as runner, \
                    patch("scripts.resume_historical_memory.run_batch", side_effect=failed_point) as process:
                runner.return_value.plan.return_value = {"eligible_count": 3, "points": [
                    {"symbol": "FPT", "as_of_date": "2020-06-01"}, point,
                    {"symbol": "FPT", "as_of_date": "2020-06-09"},
                ]}
                with self.assertRaisesRegex(RuntimeError, "đã rà soát checkpoint"):
                    resume(output, env_file=env_file, batch_size=2)
                with self.assertRaisesRegex(RuntimeError, "chưa gọi LLM"):
                    resume(output, env_file=env_file, batch_size=2)
            self.assertEqual(process.call_count, 1)
            self.assertFalse(checkpoint.exists())
            self.assertFalse((output / "run.lock").exists())
            self.assertFalse(checkpoint.with_suffix(".lock").exists())
            self.assertEqual(len(list((output / "signals").glob("*.json.interrupted-*"))), 1)
            self.assertEqual(len(list(output.glob("run.lock.interrupted-*"))), 1)
            self.assertEqual(read_json(output / "memory.json"), [{"episode_id": "settled"}])
            cooldown = read_json(output / COOLDOWN_FILE)
            self.assertEqual(cooldown["retry_after_seconds"], 1000.0)
            check_cooldown(output, now=datetime.fromisoformat(cooldown["pause_until_utc"]))

    def test_archive_rejects_completed_episode_without_moving_locks(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            point = {"symbol": "FPT", "as_of_date": "2020-06-04"}
            checkpoint = output / "signals/FPT-2020-06-04.json"
            payload = {"stage": "UPSTREAM_STARTED", "signature": "a" * 64}
            atomic_write_json(checkpoint, {"payload": payload, "sha256": digest(payload)})
            atomic_write_json(output / "episodes/FPT-2020-06-04.json", {"record": "settled"})
            (output / "run.lock").touch()
            with self.assertRaisesRegex(ValueError, "đã có episode"):
                archive_interrupted_point(output, point, 1)
            self.assertTrue(checkpoint.exists())
            self.assertTrue((output / "run.lock").exists())

    def test_archive_keeps_completed_upstream_for_next_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            point = {"symbol": "FPT", "as_of_date": "2020-06-04"}
            checkpoint = output / "signals/FPT-2020-06-04.json"
            payload = {"stage": "UPSTREAM_COMPLETE", "signature": "a" * 64,
                       "reports": {"pattern_report": "đã lưu"}}
            atomic_write_json(checkpoint, {"payload": payload, "sha256": digest(payload)})
            (output / "run.lock").touch()
            checkpoint.with_suffix(".lock").touch()
            archived = archive_interrupted_point(output, point, 0)
            self.assertEqual(len(archived), 2)
            self.assertEqual(read_json(checkpoint)["payload"], payload)
            self.assertFalse((output / "run.lock").exists())
            self.assertFalse(checkpoint.with_suffix(".lock").exists())

    def test_any_retry_stops_child_before_waiting(self):
        class Process:
            def __init__(self, line):
                self.stdout = io.StringIO(line)
                self.returncode = None
                self.terminated = False

            def poll(self):
                return self.returncode

            def terminate(self):
                self.terminated = True
                self.returncode = 1

            def wait(self):
                if self.returncode is None:
                    self.returncode = 0
                return self.returncode

        for seconds in (1000.1, 20.5, 5.0):
            with self.subTest(seconds=seconds):
                child = Process(f"Lời gọi LLM lỗi lần 1/3; chờ {seconds:.1f} giây\n")
                with patch("scripts.resume_historical_memory.subprocess.Popen", return_value=child):
                    with redirect_stdout(io.StringIO()):
                        returncode, retry_wait = run_batch(["python"], {"GROQ_API_KEY": "secret"})
                self.assertTrue(child.terminated)
                self.assertEqual(retry_wait, seconds)
                self.assertEqual(returncode, 1)

    def test_env_file_precedes_stale_shell_key(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("GROQ_API_KEY=rotated\n", encoding="utf-8")
            self.assertEqual(current_key(path, {"GROQ_API_KEY": "stale"}), "rotated")

    def test_real_child_is_stopped_before_short_retry_sleep(self):
        command = [sys.executable, "-u", "-X", "utf8", "-c",
                   "import time; print('Lời gọi LLM lỗi lần 1/3; chờ 5.0 giây', flush=True); time.sleep(5)"]
        started = time.monotonic()
        with redirect_stdout(io.StringIO()):
            returncode, retry_wait = run_batch(command, os.environ.copy())
        self.assertNotEqual(returncode, 0)
        self.assertEqual(retry_wait, 5.0)
        self.assertLess(time.monotonic() - started, 4.0)


if __name__ == "__main__":
    unittest.main()
