"""Selection/nguồn giả mạo và fixture không thể mở holdout thật."""

from copy import deepcopy
import hashlib
import unittest

from core.research_cohort import read_envelope, save_envelope
from test_holdout_protocol import HoldoutSetup


class HoldoutProtocolLeakageTests(HoldoutSetup, unittest.TestCase):
    def test_rehashed_selection_and_binding_cannot_authorize_new_calls(self) -> None:
        self.lock_development()
        self.prepare_holdout()
        calls = self.llm.calls
        selection = read_envelope(self.selection_path)
        selection.update(nomination_status="PROMOTED", research_candidate="C3", selection_evidence_status="DEVELOPMENT")
        save_envelope(self.selection_path, selection)
        self.holdout["selection_binding"]["selection"]["sha256"] = hashlib.sha256(self.selection_path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, "Quyết định khác"):
            self.run_holdout()
        self.assertEqual(self.llm.calls, calls)
        self.assertFalse(self.output.exists())

    def test_rehashed_development_report_and_selection_cannot_replace_checkpoints(self) -> None:
        self.lock_development()
        self.prepare_holdout()
        path = self.development_output/"report.json"
        report = read_envelope(path)
        report["stocks"]["FPT"]["metrics"]["C3"]["account_metrics"]["total_return_pct"] = 999.
        save_envelope(path, report)
        calls = self.llm.calls
        with self.assertRaisesRegex(ValueError, "Report khác"):
            self.run_holdout()
        self.assertEqual(self.llm.calls, calls)
        self.assertFalse(self.output.exists())

    def test_development_source_checkpoint_tamper_blocks_even_unselected_stock(self) -> None:
        self.lock_development()
        self.prepare_holdout()
        path = self.development_output/f"candidates/C3/FPT-{self.cutoffs[0]}.json"
        doc = read_envelope(path)
        doc["prompt"] += " giả"
        save_envelope(path, doc)
        calls = self.llm.calls
        with self.assertRaises(ValueError):
            self.run_holdout(symbols=["MWG"])
        self.assertEqual(self.llm.calls, calls)
        self.assertFalse(self.output.exists())

    def test_fixture_relabel_or_real_runner_never_opens_2024(self) -> None:
        self.lock_development()
        self.prepare_holdout()
        calls = self.llm.calls
        changed = deepcopy(self.holdout)
        changed["split"] = "holdout_2024"
        with self.assertRaises(ValueError):
            self.runner.run_cohort(changed, output_dir=self.output, development_runner=self.development_runner)
        self.runner.mode = "research"
        with self.assertRaisesRegex(ValueError, "Fixture holdout"):
            self.run_holdout()
        self.assertEqual(self.llm.calls, calls)
        self.assertFalse(self.output.exists())
