"""Report không mở holdout hoặc nhận nhãn future từ checkpoint tự băm lại."""

from copy import deepcopy
import unittest

from core.paired_candidate_report import paired_candidate_report
from core.prior_backtest import canonical_hash
from core.prior_checkpoint import write_document
from test_candidate_cohort import CandidateSetup
from test_paired_candidate_report import report_fixture


class PairedReportLeakageTests(unittest.TestCase):
    def test_candidate_report_rejects_holdout_before_selection_protocol(self) -> None:
        plan, points, binding = report_fixture()
        plan["split"] = "holdout_2024"
        binding["plan_sha256"] = canonical_hash(plan)
        with self.assertRaisesRegex(ValueError, "holdout"):
            paired_candidate_report(plan, points, binding)


class PairedCheckpointLeakageTests(CandidateSetup, unittest.TestCase):
    def test_rehashed_evaluation_dates_cannot_reach_paired_report(self) -> None:
        self.runner.run_cohort(self.plan, output_dir=self.output, symbols=["FPT"])
        from core.prior_checkpoint import read_document
        path = self.output / "v1/FPT/points" / f"FPT-{self.cutoffs[0]}.json"
        original = read_document(path, self.runner.schema, "point")
        changed = deepcopy(original)
        changed["evaluation"]["entry_date"] = changed["context"]["as_of_date"]
        write_document(path, changed, self.runner.schema, "point")
        with self.assertRaises(ValueError):
            self.runner.run_cohort(self.plan, output_dir=self.output, verify_only=True)
