"""Oracle biên chỉ báo và tương tác volume có dấu; không dùng outcomes thị trường."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.audit_indicator_alpha_rules import FIXTURES, audit_indicator_path, evaluate, generate


class IndicatorAlphaRulesTests(unittest.TestCase):
    """Fixture độc lập kiểm thứ tự ưu tiên, biên, dữ liệu thiếu và đường truyền report."""

    @classmethod
    def setUpClass(cls) -> None:
        """Đọc oracle cố định, không suy expected từ classifier."""
        cls.cases = json.loads(FIXTURES.read_bytes())

    def test_indicator_boundaries(self) -> None:
        for case in self.cases["indicators"]:
            with self.subTest(case=case["id"]):
                selected = {key: [] for key in self.cases}
                selected["indicators"] = [case]
                evaluate(selected)

    def test_consensus_defined_over_five_indicators(self) -> None:
        selected = {key: [] for key in self.cases}
        selected["consensus"] = self.cases["consensus"]
        self.assertEqual(len(evaluate(selected)["consensus_cases"]), 5)

    def test_signed_volume_and_zero_cases(self) -> None:
        selected = {key: [] for key in self.cases}
        selected["alpha4"] = self.cases["alpha4"]
        rows = evaluate(selected)["alpha4_cases"]
        self.assertEqual(len(rows), 11)
        self.assertEqual(next(r for r in rows if r["id"] == "b0.75_z-1")["signal"], "GIẢM")

    def test_registry_formula_matches_independent_array_oracle(self) -> None:
        selected = {key: [] for key in self.cases}
        selected["registry_alpha4"] = self.cases["registry_alpha4"]
        self.assertEqual(len(evaluate(selected)["registry_cases"]), 3)

    def test_oracle_mismatch_is_rejected(self) -> None:
        cases = copy.deepcopy(self.cases)
        cases["indicators"][0]["expected"] = "GIẢM"
        with self.assertRaises(ValueError):
            evaluate(cases)

    def test_real_toolkit_path_only_returns_report_and_messages(self) -> None:
        result = audit_indicator_path()
        self.assertEqual(len(result["called_tools"]), 5)
        self.assertEqual(result["returned_keys"], ["indicator_report", "messages"])
        self.assertEqual(result["n_model_calls"], 0)

    def test_runtime_hashes_and_artifacts_are_deterministic(self) -> None:
        first = generate()
        self.assertEqual(first, generate())
        report = json.loads(first["report.json"])
        self.assertTrue(report["scoped_runtime_sources_unchanged_against_r4"])


if __name__ == "__main__":
    unittest.main()
