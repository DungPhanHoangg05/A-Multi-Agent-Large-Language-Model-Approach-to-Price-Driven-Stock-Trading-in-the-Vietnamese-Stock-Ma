"""Oracle nomination v2: kiểm biên rule cũ, đầy đủ G và receipt riêng bất biến."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from core.mt_bicl_bank import content_hash
from core.mt_bicl_v2_io import write_envelope
from core.mt_bicl_v2_nomination import RECEIPT, RULES, VERSION, evaluate, rebuild, save_or_verify
from core.mt_bicl_v2_report import FULL, NAMES, SYMBOLS


def fixture(returns: tuple[float, ...] = (4., 2., 1., -1.),
            delta_mdd: tuple[float, ...] = (5., 1., 1., 1.), reference_gap: float = 0.) -> dict:
    """Giữ lịch thật nhưng metric giả; D=1,5, ba mã tăng, hai guard MDD ở đúng biên."""
    manifest = json.loads(Path("docs/plan/week11/development_run_manifest_v2.json").read_text(encoding="utf-8"))["payload"]
    points = [{"point_id": pid, "symbol": pid[:3], "as_of_date": pid[4:], "repeat_index": 0,
               "branches": {n: {"action": "CASH"} for n in NAMES}} for pid in manifest["layout"]["point_ids"]]
    stocks, contrasts = {}, {n: {"by_symbol": {}} for n in ("Original", "A_reference")}
    for s, r, delta in zip(SYMBOLS, returns, delta_mdd):
        ids = [p["point_id"] for p in points if p["symbol"] == s]
        stocks[s] = {n: {"count": len(ids), "reason": None,
            "account": {"point_ids": ids, "metrics": {"total_return_pct": r if n == FULL else r-reference_gap if n == "A_reference" else 0.,
                                                      "max_drawdown_pct": 10.+delta if n == FULL else 10.}}} for n in NAMES}
        for n, d in (("Original", r), ("A_reference", r-(r-reference_gap))):
            contrasts[n]["by_symbol"][s] = {"count": len(ids), "delta_return_pp": d}
    for n in contrasts:
        contrasts[n]["mean_delta_return_pp"] = sum(v["delta_return_pp"] for v in contrasts[n]["by_symbol"].values())/4
    return {"status": "PASS", "phase": "development2023", "nomination": "NOT_EVALUATED", "confirmation_allowed": False,
            "all_primary_cases": points, "support": {"planned_count": 60, "complete_count": 60, "excluded": []},
            "G": {"count": 60, "point_ids": [p["point_id"] for p in points], "stocks": stocks, "contrasts": contrasts}}


class NominationTests(unittest.TestCase):
    """Không lấy kết quả mô tả hoặc gate v3 thay rule nomination v2 đã khóa."""

    def test_three_positive_and_inclusive_A_MDD_boundaries_pass(self) -> None:
        result = evaluate(fixture(), RULES)
        self.assertEqual(result["status"], "NOMINATED")
        self.assertEqual(result["nominated_candidate"], FULL)
        self.assertEqual(result["metrics"]["D_Full_Original_pp"], 1.5)
        self.assertEqual((result["metrics"]["mean_delta_MDD_pp"], result["metrics"]["max_delta_MDD_pp"]), (2., 5.))
        self.assertFalse(result["confirmation_v2"]["allowed"])
        self.assertEqual(result["confirmation_v2"]["status"], "REQUIRES_SEPARATE_RELEASE")

    def test_zero_D_is_not_strictly_positive_even_with_three_winning_symbols(self) -> None:
        result = evaluate(fixture((1., 1., 1., -3.)), RULES)
        self.assertEqual(result["failure_reasons"], ["D_Full_Original_gt_0"])
        self.assertEqual(result["confirmation_v2"]["status"], "NOT_RUN")

    def test_tiny_positive_D_is_not_replaced_by_rounded_zero(self) -> None:
        result = evaluate(fixture((1e-12, 1e-12, 1e-12, 0.)), RULES)
        self.assertEqual(result["status"], "NOMINATED")

    def test_zero_return_does_not_count_as_positive_symbol(self) -> None:
        result = evaluate(fixture((1., 1., 0., 0.)), RULES)
        self.assertEqual(result["metrics"]["positive_symbols"], 2)
        self.assertEqual(result["failure_reasons"], ["positive_symbols_at_least_3"])

    def test_negative_A_gap_is_not_allowed_even_if_tiny(self) -> None:
        result = evaluate(fixture(reference_gap=-1e-9), RULES)
        self.assertEqual(result["failure_reasons"], ["D_Full_A_ge_0"])

    def test_mean_MDD_above2_fails_even_when_max_at5(self) -> None:
        result = evaluate(fixture(delta_mdd=(5., 1., 1., 1.000004)), RULES)
        self.assertEqual(result["failure_reasons"], ["mean_delta_MDD_le_2"])

    def test_max_MDD_above5_fails_even_when_mean_below2(self) -> None:
        result = evaluate(fixture(delta_mdd=(5.000001, 0., 0., 0.)), RULES)
        self.assertEqual(result["failure_reasons"], ["max_delta_MDD_le_5"])

    def test_bad_or_negative_MDD_stops_instead_of_not_nominated(self) -> None:
        for value in (None, True, float("nan"), float("inf"), -1.):
            report = fixture();report["G"]["stocks"]["FPT"][FULL]["account"]["metrics"]["max_drawdown_pct"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                evaluate(report, RULES)

    def test_missing_duplicate_wrong_phase_repeat_or_branch_stops(self) -> None:
        for mode in ("missing", "duplicate", "phase", "repeat", "branch", "account"):
            report = fixture()
            if mode == "missing": report["all_primary_cases"].pop()
            if mode == "duplicate": report["all_primary_cases"][-1] = deepcopy(report["all_primary_cases"][0])
            if mode == "phase": report["phase"] = "confirmation2025"
            if mode == "repeat": report["all_primary_cases"][0]["repeat_index"] = 1
            if mode == "branch": report["all_primary_cases"][0]["branches"].pop("Stats_only")
            if mode == "account": report["G"]["stocks"]["FPT"]["Stats_only"]["account"] = None
            with self.subTest(mode=mode), self.assertRaises(ValueError): evaluate(report, RULES)

    def test_new_or_relaxed_rules_are_rejected(self) -> None:
        for rules in ({**RULES, "positive_symbols_min": 1}, {**RULES, "D_Full_Fact_Anchor_strict_min": 0},
                      {**RULES, "candidate_substitution": True}):
            with self.assertRaises(ValueError): evaluate(fixture(), rules)

    def test_accuracy_repeat_and_winning_ablation_cannot_promote(self) -> None:
        report = fixture((1., 1., 1., -4.));before = content_hash(report)
        report["repeat"] = {"D": 100.};report["accuracy"] = 1.
        report["G"]["stocks"]["FPT"]["No_target"]["account"]["metrics"]["total_return_pct"] = 100.
        result = evaluate(report, RULES)
        self.assertEqual(result["status"], "NOT_NOMINATED")
        self.assertEqual(result["candidate_evaluated"], FULL)
        self.assertIsNone(result["nominated_candidate"])
        self.assertNotEqual(content_hash(report), before)

    def test_contrast_tamper_cannot_override_accounts(self) -> None:
        for mode in ("D", "symbol"):
            report = fixture()
            if mode == "D": report["G"]["contrasts"]["Original"]["mean_delta_return_pp"] = 999.
            else: report["G"]["contrasts"]["Original"]["by_symbol"]["FPT"]["delta_return_pp"] = 999.
            with self.subTest(mode=mode), self.assertRaises(ValueError): evaluate(report, RULES)

    def test_evaluation_preserves_input_report_and_rules(self) -> None:
        report, rules = fixture(), deepcopy(RULES)
        before = content_hash({"report": report, "rules": rules})
        evaluate(report, rules)
        self.assertEqual(content_hash({"report": report, "rules": rules}), before)
        self.assertEqual(report["nomination"], "NOT_EVALUATED")

    def test_wrong_report_hash_stops_before_rebuilding_report(self) -> None:
        with patch("core.mt_bicl_v2_nomination.evidence_snapshot", return_value={}), \
             patch("core.mt_bicl_v2_nomination.file_hash", return_value="wrong"), \
             patch("core.mt_bicl_v2_nomination.rebuild_report", side_effect=AssertionError("Không được chạy tiếp")), self.assertRaises(ValueError):
            rebuild(Path("."))

    def test_immutable_receipt_rehashed_tamper_is_rejected(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp);result = evaluate(fixture(), RULES)
            save_or_verify(root, result);save_or_verify(root, result)
            write_envelope(root/RECEIPT, VERSION, {**result, "status": "NOT_NOMINATED"})
            before = (root/RECEIPT).read_bytes()
            with self.assertRaises(ValueError): save_or_verify(root, result)
            self.assertEqual((root/RECEIPT).read_bytes(), before)

    def test_verify_receipt_requires_exact_Git_anchor(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp);result = evaluate(fixture(), RULES);save_or_verify(root, result)
            with patch("core.mt_bicl_v2_nomination.subprocess.run", return_value=SimpleNamespace(stdout=b"wrong")), self.assertRaises(ValueError):
                save_or_verify(root, result, verify_only=True)
            with patch("core.mt_bicl_v2_nomination.subprocess.run", return_value=SimpleNamespace(stdout=(root/RECEIPT).read_bytes())):
                save_or_verify(root, result, verify_only=True)


if __name__ == "__main__":
    unittest.main()
