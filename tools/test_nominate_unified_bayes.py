"""Kiểm đúng biên nomination và consumer nguồn; fixture không phát hành quyết định thật."""

from __future__ import annotations

from contextlib import nullcontext, redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import math
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import numpy as np

from core.historical_signals import digest
from core.research_cohort import save_envelope
from core.research_input_lock import _write_once
from tools import nominate_unified_bayes as m
from unified_validation_test_support import ValidationFixture


def primary_fixture() -> dict:
    """Bảng 60 điểm giả chỉ kiểm các bất đẳng thức, không dùng Decision thật."""
    stocks = {}
    for symbol, count in m.PLANNED.items():
        stocks[symbol] = {"support": {"planned": count, "count": count,
            "point_ids": [f"{symbol}-2023-01-{j+1:02d}" for j in range(count)], "excluded": []},
            "metrics": {name: {"return_pct": 0., "mdd_pct": 0.} for name in m.MATRIX}}
        stocks[symbol]["metrics"]["U_full"]["return_pct"] = 1.
    return {"point_count": 60, "stocks": stocks}


def coverage_fixture() -> dict:
    """Đúng ngưỡng tổng và từng mã, có thể kiểm từng biên độc lập."""
    return {"prior_visible": {"count": 30, "by_symbol": {"FPT": 5, "MWG": 5, "VCB": 10, "VNM": 10}},
        "examples_visible": {"count": 12, "by_symbol": {s: 3 for s in m.SYMBOLS}}}


class NominationRuleTests(unittest.TestCase):
    """Không làm tròn, không đổi candidate và không dùng repeat để cứu gate primary."""

    def setUp(self) -> None:
        self.primary = primary_fixture()
        self.coverage = coverage_fixture()
        self.verification = {key: "PASS" for key in m.VERIFICATIONS}

    def evaluate(self) -> dict:
        return m.evaluate_rules(self.primary, self.coverage, self.verification)

    def test_all_gates_nominate_only_full_and_never_release_confirmation(self) -> None:
        result = self.evaluate()
        self.assertEqual(result["status"], "NOMINATED")
        self.assertEqual(result["research_candidate"], "U_full")
        self.assertFalse(result["confirmation_allowed"])

    def test_two_positive_symbols_fail_even_when_average_is_positive(self) -> None:
        for s, value in zip(m.SYMBOLS, (-.3, .4, .1, 0.)):
            self.primary["stocks"][s]["metrics"]["U_full"]["return_pct"] = value
        result = self.evaluate()
        self.assertGreater(result["mean_delta_return_original_pp"], 0)
        self.assertEqual(result["positive_symbols"], 2)
        self.assertEqual(result["failed_checks"], ["at_least_three_positive_symbols"])
        self.assertEqual(result["status"], "NOT_NOMINATED")
        self.assertIsNone(result["research_candidate"])

    def test_zero_is_not_positive_but_unrounded_tiny_gain_is_positive(self) -> None:
        for symbol in ("VCB", "VNM"):
            self.primary["stocks"][symbol]["metrics"]["U_full"]["return_pct"] = 0.
        self.assertEqual(self.evaluate()["positive_symbols"], 2)
        self.primary["stocks"]["VCB"]["metrics"]["U_full"]["return_pct"] = 1e-14
        self.assertEqual(self.evaluate()["status"], "NOMINATED")

    def test_mean_gain_is_strictly_positive_and_reference_is_inclusive(self) -> None:
        for s in m.SYMBOLS:
            self.primary["stocks"][s]["metrics"]["U_full"]["return_pct"] = 0.
        result = self.evaluate()
        self.assertFalse(result["checks"]["mean_delta_return_original_positive"])
        self.assertTrue(result["checks"]["mean_delta_return_reference_nonnegative"])
        self.primary["stocks"]["FPT"]["metrics"]["A_reference"]["return_pct"] = 1e-12
        self.assertFalse(self.evaluate()["checks"]["mean_delta_return_reference_nonnegative"])

    def test_mdd_limits_include_exact_boundaries(self) -> None:
        for s, value in zip(m.SYMBOLS, (5., 1., 1., 1.)):
            self.primary["stocks"][s]["metrics"]["U_full"]["mdd_pct"] = value
        result = self.evaluate()
        self.assertEqual(result["mean_delta_mdd_pp"], 2.)
        self.assertEqual(result["max_delta_mdd_pp"], 5.)
        self.assertEqual(result["status"], "NOMINATED")

    def test_mean_and_worst_symbol_mdd_are_independent_guards(self) -> None:
        for values, failed in (((3., 3., 3., 0.), "mean_delta_mdd_within_limit"),
                               ((5.01, 0., 0., 0.), "max_delta_mdd_within_limit")):
            with self.subTest(values=values):
                for s, value in zip(m.SYMBOLS, values):
                    self.primary["stocks"][s]["metrics"]["U_full"]["mdd_pct"] = value
                self.assertEqual(self.evaluate()["failed_checks"], [failed])

    def test_visibility_requires_overall_and_every_symbol(self) -> None:
        for field, overall, per_symbol in (("prior_visible", 29, 4), ("examples_visible", 11, 1)):
            for change in ("overall", "symbol"):
                with self.subTest(field=field, change=change):
                    self.coverage = coverage_fixture()
                    self.coverage[field]["count"] = overall if change == "overall" else self.coverage[field]["count"]
                    if change == "symbol":
                        self.coverage[field]["by_symbol"]["FPT"] = per_symbol
                    self.assertEqual(self.evaluate()["status"], "INSUFFICIENT_EVIDENCE")

    def test_missing_branch_metrics_or_support_never_becomes_cash(self) -> None:
        self.primary["stocks"]["FPT"]["metrics"]["U_examples"]["return_pct"] = None
        self.assertEqual(self.evaluate()["status"], "INSUFFICIENT_EVIDENCE")
        self.primary = primary_fixture()
        self.primary["stocks"]["FPT"]["support"]["point_ids"][0] = self.primary["stocks"]["FPT"]["support"]["point_ids"][1]
        self.assertFalse(self.evaluate()["checks"]["primary_common_support_60"])

    def test_missing_or_failed_verification_cannot_nominate(self) -> None:
        for proof in ({}, {key: "PASS" for key in m.VERIFICATIONS[:-1]},
                      {**self.verification, "technical_gates": "FAIL"}):
            self.verification = proof
            self.assertEqual(self.evaluate()["status"], "INSUFFICIENT_EVIDENCE")

    def test_bool_nonfinite_and_negative_mdd_are_rejected(self) -> None:
        for value in (True, math.nan, math.inf, np.float64(1.)):
            self.primary["stocks"]["FPT"]["metrics"]["U_full"]["return_pct"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.evaluate()
        self.primary = primary_fixture()
        self.primary["stocks"]["FPT"]["metrics"]["U_full"]["mdd_pct"] = -1.
        with self.assertRaises(ValueError):
            self.evaluate()

    def test_ablation_gain_cannot_replace_failed_full(self) -> None:
        for s in m.SYMBOLS:
            self.primary["stocks"][s]["metrics"]["U_full"]["return_pct"] = 0.
            self.primary["stocks"][s]["metrics"]["U_stats"]["return_pct"] = 100.
        self.assertIsNone(self.evaluate()["research_candidate"])

    def test_missing_symbol_group_has_null_four_account_mean(self) -> None:
        self.assertIsNone(m.mean_four({"FPT": 1., "MWG": 2., "VCB": 3., "VNM": None}))
        with self.assertRaises(ValueError):
            m.mean_four({"FPT": 1.})

    def test_locked_protocol_rejects_rule_type_drift(self) -> None:
        actual = m.locked_protocol()
        poisoned = deepcopy(actual)
        poisoned["nomination"]["positive_symbols_min"] = 3.0
        with patch.object(m, "read_json", return_value=poisoned), self.assertRaises(ValueError):
            m.locked_protocol()


class NominationAnalysisTests(ValidationFixture, unittest.TestCase):
    """Report SDK/engine thật qua HTTP mock, subgroup và consumer chống tự reseal."""

    def setUp(self) -> None:
        super().setUp()
        self.diag = self.diagnostic()
        self.run = self.handle()
        self.run.run()
        self.report = self.run.run(repeats=True)
        self.proof = {key: "PASS" for key in m.VERIFICATIONS}
        self.analysis = m.describe_analysis(self.plan, self.report, self.diag, self.proof)

    def artifact(self) -> dict:
        """Envelope giả trong temp chỉ kiểm schema/consumer, không xuất ở namespace thật."""
        return {"selection_version": m.VERSION, "split": "development_2023_exploratory", "candidate": "U_full",
            "rules": m.RULES, "rules_sha256": digest(m.RULES), "binding": {"fixture": True},
            "verification": self.proof, "analysis": self.analysis, "decision": self.analysis["decision"],
            "confirmation_allowed": False, "risk_policy": "OFF", "limitations": ["Fixture."] * 5}

    def test_g_t_and_context_partition_keep_fixed_four_symbol_estimand(self) -> None:
        strata, modes = self.analysis["strata"], self.analysis["context_modes"]
        self.assertEqual(strata["G_all"]["point_count"], 4)
        self.assertEqual(sum(strata[k]["point_count"] for k in
            ("T_both_ready", "stats_only_ready", "examples_only_ready", "prior_off")), 4)
        self.assertEqual(sum(v["point_count"] for v in modes.values()), 4)
        self.assertEqual(self.analysis["quarters"]["Q2"]["point_count"], 0)
        self.assertTrue(all(v is None for v in self.analysis["quarters"]["Q2"]["equal_weight_delta_return_pp"].values()))

    def test_repeat_and_duplicate_have_denominators_and_do_not_enter_primary(self) -> None:
        repeat = self.analysis["repeat"]
        self.assertFalse(repeat["in_primary"])
        self.assertFalse(repeat["vote"])
        self.assertEqual(set(repeat["on_locked_sample"]), {"0", "1", "2", "3"})
        self.assertEqual(self.analysis["primary"]["point_count"], 4)
        for counts in repeat["primary_vs_repeats"].values():
            self.assertEqual(counts["observed_pairs"], counts["planned_pairs"])
            self.assertEqual(counts["planned_pairs"], 12)

    def test_cash_and_net_account_returns_match_independent_cycle_oracle(self) -> None:
        for s in m.SYMBOLS:
            row = next(p for p in self.report["points"] if p["repeat_id"] == 0 and p["point_id"].startswith(s+"-"))
            e = row["evaluation"]
            net = (e["exit_close"]/e["entry_open"]) * (.999*.9975)/(1.001*1.0025)-1
            self.assertAlmostEqual(net, e["net_return_long"], places=12)
            for name in m.MATRIX:
                expected = 100*net if row["branches"][name]["decision"]["action"] == "LONG" else 0.
                self.assertAlmostEqual(self.analysis["primary"]["stocks"][s]["metrics"][name]["return_pct"], expected, places=10)

    def test_future_query_or_exit_is_rejected_before_nomination(self) -> None:
        for kind in ("cutoff", "exit"):
            report = deepcopy(self.report)
            row = report["points"][0]
            if kind == "cutoff":
                row["point_id"] = row["point_id"][:4] + "2025-01-06"
                row["context"]["as_of_date"] = "2025-01-06"
            else:
                row["evaluation"]["exit_date"] = "2024-01-02"
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                m.describe_analysis(self.plan, report, self.diag, self.proof)

    def test_visibility_or_schedule_drift_is_rejected(self) -> None:
        report = deepcopy(self.report)
        report["points"][0]["branches"]["U_full"]["prior_visible"] = not report["points"][0]["branches"]["U_full"]["prior_visible"]
        with self.assertRaises(ValueError):
            m.describe_analysis(self.plan, report, self.diag, self.proof)
        report = deepcopy(self.report)
        report["points"] = report["points"][1:]
        with self.assertRaises(ValueError):
            m.describe_analysis(self.plan, report, self.diag, self.proof)

    def test_fixture_cannot_publish_real_nomination(self) -> None:
        with self.assertRaises(ValueError):
            m.make_artifact({"plan": self.plan})

    def test_write_once_and_consumer_reject_resealed_decision_metric_and_repeat(self) -> None:
        path = self.fx.root / "selection.json"
        expected = self.artifact()
        m.validate_artifact(expected)
        _write_once(path, expected)
        raw = path.read_bytes()
        _write_once(path, expected)
        self.assertEqual(path.read_bytes(), raw)
        m.read_selection(path, expected)
        for field in ("decision", "metric", "repeat"):
            changed = deepcopy(expected)
            if field == "decision":
                changed["decision"]["positive_symbols"] = 4
            elif field == "metric":
                changed["analysis"]["coverage"]["prior_visible"]["count"] = 60
            else:
                changed["analysis"]["repeat"]["vote"] = True
            save_envelope(path, changed)
            with self.subTest(field=field), self.assertRaises(ValueError):
                m.read_selection(path, expected)

    def test_default_cli_never_writes_and_guard_failure_stops_prepare(self) -> None:
        artifact = self.artifact()
        guard = Mock()
        with patch.object(m, "verified_evidence", return_value=nullcontext({"guard": guard})), \
             patch.object(m, "make_artifact", return_value=artifact), patch.object(m, "_write_once") as write, \
             patch.object(m, "read_selection", return_value=artifact), patch.object(sys, "argv", ["nominate"]), \
             redirect_stdout(io.StringIO()):
            m.main()
            write.assert_not_called()
        guard.side_effect = ValueError("Nguồn fixture đổi")
        with patch.object(m, "verified_evidence", return_value=nullcontext({"guard": guard})), \
             patch.object(m, "make_artifact", return_value=artifact), patch.object(m, "_write_once") as write, \
             patch.object(sys, "argv", ["nominate", "--prepare"]), self.assertRaises(ValueError):
            m.main()
        write.assert_not_called()


class NominationGuardTests(unittest.TestCase):
    """Chặn drift trước ghi artifact và không cung cấp cờ chạy API/tune ngưỡng."""

    def test_file_drift_or_changed_ledger_fails_guard(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "source.txt"
            path.write_text("Nguồn fixture", encoding="utf-8")
            hashes = {"source.txt": m.sha(path)}
            run = SimpleNamespace(transport=SimpleNamespace(verify_ledger_file=Mock()), verify=Mock())
            with patch.object(m, "ROOT", root):
                m.guard_binding(hashes, run)
                path.write_text("Nguồn khác", encoding="utf-8")
                with self.assertRaises(ValueError):
                    m.guard_binding(hashes, run)
                hashes["source.txt"] = m.sha(path)
                run.transport.verify_ledger_file.side_effect = ValueError("Ledger đổi")
                with self.assertRaises(ValueError):
                    m.guard_binding(hashes, run)

    def test_cli_rejects_api_or_model_tuning_before_loading_sources(self) -> None:
        for option in ("--run", "--model", "--threshold"):
            with patch.object(m, "verified_evidence") as source, patch.object(sys, "argv", ["nominate", option]), \
                 redirect_stderr(io.StringIO()), self.subTest(option=option), self.assertRaises(SystemExit):
                m.main()
            source.assert_not_called()

    def test_analysis_code_drift_fails_before_source_or_ledger_access(self) -> None:
        run = SimpleNamespace(transport=SimpleNamespace(verify_ledger_file=Mock()), verify=Mock())
        with patch.object(m, "analysis_identity", return_value={"code.py": "b" * 64}), self.assertRaises(ValueError):
            m.guard_binding({}, run, {"code.py": "a" * 64})
        run.transport.verify_ledger_file.assert_not_called()
        run.verify.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
