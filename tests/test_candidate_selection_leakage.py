"""Selector không mở holdout và không dùng support thiếu như đủ 60 điểm."""

import unittest

from core.candidate_selection import evaluate_selection
from test_candidate_selection import oracle_report


class CandidateSelectionLeakageTests(unittest.TestCase):
    def test_rehashed_holdout_report_never_reaches_ranking(self) -> None:
        report = oracle_report()
        report["split"] = "holdout_2024"
        with self.assertRaises(ValueError):
            evaluate_selection(report,gates_passed=True)

    def test_holdout_point_cannot_be_hidden_inside_fixture_or_development(self) -> None:
        for split in ("fixture","development_2023"):
            report = oracle_report()
            report["split"] = split
            report["stocks"]["FPT"]["points"][0]["as_of_date"] = "2024-01-02"
            with self.assertRaises(ValueError):
                evaluate_selection(report,gates_passed=True)

    def test_forged_primary_and_support_count_do_not_rescue_unknown(self) -> None:
        report = oracle_report()
        report["stocks"]["VCB"]["points"][0]["branch_status"]["random"] = "unknown"
        with self.assertRaises(ValueError):
            evaluate_selection(report,gates_passed=True)

    def test_holdout_exit_cannot_be_hidden_behind_development_cutoff(self) -> None:
        report = oracle_report()
        report["stocks"]["FPT"]["action_attribution"] = {"points":[{"economic_label":{
            "entry_date":"2023-12-29","exit_date":"2024-01-03"}}]}
        with self.assertRaises(ValueError):
            evaluate_selection(report,gates_passed=True)
