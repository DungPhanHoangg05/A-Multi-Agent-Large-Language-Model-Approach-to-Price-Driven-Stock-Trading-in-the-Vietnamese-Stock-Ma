"""Kiểm journal/resume, replay chống self-reseal và đồng hồ chung bằng fixture CPU."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from core.mt_bicl_v2_io import ActiveBudget, read_envelope, write_envelope
from core.mt_bicl_v2_preparation import (
    CORPUS_VERSION, INDEX_VERSION, NAMESPACE, OUTPUT, STREAMS, TEACHER_VERSION,
    file_hash, run_preparation, verify_preparation,
)


class PreparationJournalTests(unittest.TestCase):
    """Stage mô phỏng không fit thật, sinh held-out thật hoặc dùng optimizer/GPU."""

    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.inputs = {"identity": {"fixture": True}, "budget_identity": {
            "protocol_sha256": "fixture", "grant_payload_sha256": "fixture",
            "cap_seconds": 14400, "W10_stop": "2099-01-01"}}
        self.fitted = {"identity": self.inputs["identity"], "converged": True,
                       "status": "CONVERGED", "iterations": 1, "max_pi_delta": 0.,
                       "training_allowed": False, "decision_calls_allowed": False}

    def corpus(self, inputs: dict, fitted: dict, teacher_hash: str, stream: str, check: object = None) -> dict:
        """Payload giả nhỏ để kiểm giao dịch đĩa và binding stage."""
        return {"identity": inputs["identity"], "stream": stream, "teacher_byte_sha256": teacher_hash,
                "fixture_probability": .5, "training_allowed": False, "decision_calls_allowed": False}

    def test_pause_resume_skips_committed_stages_and_same_identity(self) -> None:
        calls = []
        def interrupted(*args: object) -> dict:
            stream = args[3]
            calls.append(stream)
            if stream == STREAMS[1]:
                raise KeyboardInterrupt()
            return self.corpus(*args)
        with patch("core.mt_bicl_v2_preparation.prepare_teacher", return_value=self.fitted), \
                patch("core.mt_bicl_v2_preparation.prepare_corpus", side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                run_preparation(self.root, self.inputs, resume=True)
        self.assertEqual(calls, list(STREAMS[:2]))
        with patch("core.mt_bicl_v2_preparation.prepare_teacher", side_effect=AssertionError("Không fit lại stage đã commit")), \
                patch("core.mt_bicl_v2_preparation.prepare_corpus", side_effect=self.corpus) as remaining:
            result = run_preparation(self.root, self.inputs, resume=True)
        self.assertEqual(result["status"], "COMPLETE_TEACHER_ORACLE_ONLY")
        self.assertEqual(remaining.call_count, len(STREAMS)-1)
        changed = deepcopy(self.inputs)
        changed["identity"]["modified"] = True
        with self.assertRaisesRegex(ValueError, "identity mới"):
            run_preparation(self.root, changed, resume=True)

    def test_replay_rejects_prediction_even_after_self_resealing_index(self) -> None:
        with patch("core.mt_bicl_v2_preparation.prepare_teacher", return_value=self.fitted), \
                patch("core.mt_bicl_v2_preparation.prepare_corpus", side_effect=self.corpus):
            run_preparation(self.root, self.inputs, resume=True)
            self.assertEqual(verify_preparation(self.root, self.inputs, replay=True)["replay"], "PASS")
            path = self.root/OUTPUT/(STREAMS[0]+".json")
            payload = read_envelope(path, CORPUS_VERSION)
            payload["fixture_probability"] = .9
            write_envelope(path, CORPUS_VERSION, payload)
            index_path = self.root/OUTPUT/"index.json"
            index = read_envelope(index_path, INDEX_VERSION)
            index["files"][path.name].update(sha256=file_hash(path), bytes=path.stat().st_size)
            write_envelope(index_path, INDEX_VERSION, index)
            with self.assertRaisesRegex(ValueError, "khác cold replay"):
                verify_preparation(self.root, self.inputs, replay=True)

    def test_nonconverged_teacher_is_saved_without_any_corpus_or_fallback(self) -> None:
        failed = {**self.fitted, "converged": False,
                  "status": "STOP_TEACHER_NONCONVERGENCE_NO_UNIFORM_FALLBACK"}
        with patch("core.mt_bicl_v2_preparation.prepare_teacher", return_value=failed), \
                patch("core.mt_bicl_v2_preparation.prepare_corpus", side_effect=AssertionError("Không sinh corpus")):
            result = run_preparation(self.root, self.inputs, resume=True)
        self.assertEqual(set(result["files"]), {"teacher_fit.json"})
        self.assertEqual(verify_preparation(self.root, self.inputs, replay=False)["teacher_status"], failed["status"])
        with self.assertRaises(ValueError):
            write_envelope(self.root/OUTPUT/"teacher_fit.json", TEACHER_VERSION, self.fitted, immutable=True)

    def test_shared_budget_charges_uncertain_crash_gap_and_rejects_reset_or_cap(self) -> None:
        path = self.root/NAMESPACE/"active_budget_v2.json"
        identity = self.inputs["budget_identity"]
        write_envelope(path, "mt_bicl_active_budget_v2", {"identity": identity,
            "elapsed_seconds": 100., "active_since": "2026-01-01T00:00:00+00:00", "sessions": []})
        class Clock:
            @staticmethod
            def now(tz: object) -> datetime:
                return datetime(2026,1,1,0,0,30,tzinfo=timezone.utc)
            fromisoformat = staticmethod(datetime.fromisoformat)
        with patch("core.mt_bicl_v2_io.datetime", Clock):
            with ActiveBudget(path, identity) as budget:
                self.assertGreaterEqual(budget.used(), 130.)
        saved = read_envelope(path, "mt_bicl_active_budget_v2")
        self.assertIsNone(saved["active_since"])
        reset = deepcopy(saved)
        reset["elapsed_seconds"] = 0.
        write_envelope(path, "mt_bicl_active_budget_v2", reset)
        with self.assertRaisesRegex(ValueError, "không reset"):
            with ActiveBudget(path, identity):
                self.fail("Không nhận counter thấp hơn lịch sử phiên")
        write_envelope(path, "mt_bicl_active_budget_v2", saved)
        changed = {**identity, "cap_seconds": 28800}
        with self.assertRaisesRegex(ValueError, "khác identity"):
            ActiveBudget(path, changed)
        saved["elapsed_seconds"] = 14401.
        write_envelope(path, "mt_bicl_active_budget_v2", saved)
        with self.assertRaisesRegex(RuntimeError, "Hết cap"):
            with ActiveBudget(path, identity):
                self.fail("Không được mở phiên khi hết cap")


if __name__ == "__main__":
    unittest.main()
