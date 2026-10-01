"""Kiểm khoảng nghỉ LLM được giữ giữa request và sau khi khởi động lại."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from core.bayesian_memory import atomic_write_json, read_json
from scripts.run_paced_historical_memory import PACE_FILE, RequestPacer, make_paced_llm_class


class HistoricalMemoryPacingTests(unittest.TestCase):
    def test_all_llm_calls_respect_gap_across_worker_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            current = [1000.0]
            sleeps = []
            calls = []

            def clock():
                return current[0]

            def sleeper(seconds):
                sleeps.append(seconds)
                current[0] += seconds

            class Delegate:
                def invoke(self, prompt):
                    calls.append((prompt, current[0]))
                    return "ok"

            pacer = RequestPacer(output, 75.0, clock=clock, sleeper=sleeper)
            llm = make_paced_llm_class(pacer)(Delegate())
            self.assertEqual(llm.invoke("pattern"), "ok")
            self.assertEqual(llm.invoke("trend"), "ok")
            current[0] += 10.0
            restarted = make_paced_llm_class(
                RequestPacer(output, 75.0, clock=clock, sleeper=sleeper)
            )(Delegate())
            self.assertEqual(restarted.invoke("next episode"), "ok")
            self.assertEqual(calls, [("pattern", 1000.0), ("trend", 1075.0),
                                     ("next episode", 1150.0)])
            self.assertEqual(sum(sleeps), 140.0)
            self.assertEqual(read_json(output / PACE_FILE), {"last_call_epoch": 1150.0})

    def test_failed_request_still_starts_next_gap(self):
        with tempfile.TemporaryDirectory() as directory:
            current = [500.0]

            def clock():
                return current[0]

            def sleeper(seconds):
                current[0] += seconds

            class FailingDelegate:
                def invoke(self, prompt):
                    current[0] += 4.0
                    raise ValueError("lỗi dữ liệu")

            output = Path(directory)
            pacer = RequestPacer(output, 75.0, clock=clock, sleeper=sleeper)
            with self.assertRaisesRegex(ValueError, "lỗi dữ liệu"):
                make_paced_llm_class(pacer)(FailingDelegate()).invoke("first")
            self.assertEqual(read_json(output / PACE_FILE), {"last_call_epoch": 504.0})
            pacer.before_request()
            self.assertEqual(current[0], 579.0)

    def test_legacy_journal_and_invalid_pace_record(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            episodes = output / "episodes"
            episodes.mkdir()
            journal = episodes / "FPT-2020-06-01.json"
            journal.write_text("{}", encoding="utf-8")
            os.utime(journal, (1000.0, 1000.0))
            current = [1010.0]

            def sleeper(seconds):
                current[0] += seconds

            pacer = RequestPacer(output, 75.0, clock=lambda: current[0], sleeper=sleeper)
            pacer.before_request()
            self.assertEqual(current[0], 1075.0)
            atomic_write_json(output / PACE_FILE, {"last_call_epoch": "invalid"})
            with self.assertRaisesRegex(ValueError, "sai cấu trúc"):
                pacer.before_request()


if __name__ == "__main__":
    unittest.main()
