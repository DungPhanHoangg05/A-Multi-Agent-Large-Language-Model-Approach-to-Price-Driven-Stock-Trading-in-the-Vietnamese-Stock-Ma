"""Kiểm account/decomposition/nomination v3 bằng action/payoff giả, không đọc outcome thật."""

from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pandas as pd

from core.backtest_engine import compute_round_trip_net_return
from core.mt_bicl_bank import content_hash
from core.mt_bicl_v2_audit import account
from core.mt_bicl_v2_report import Analysis
from core.mt_bicl_v3_audit import FULL, NAMES, VIRTUAL, SYMBOLS, cash_action, materialize
from core.mt_bicl_v3_analysis import build_report, group, nominate, decomposition, sensitivity


def fixture() -> tuple[dict, dict, dict]:
    """Mượn cohort/order đã đăng ký, action/giá/metadata hoàn toàn giả để test consumer."""
    protocol = json.loads(Path("docs/plan/week11/protocol_v3.json").read_text(encoding="utf-8"))
    manifest = json.loads(Path("docs/plan/week11/development_manifest_v3.json").read_text(encoding="utf-8"))["payload"]
    points = []
    for block in manifest["layout"]["blocks"]:
        pid, r, j = block["point_id"], block["repeat_index"], block["point_index"]
        missing = j%6 == 0
        closing = 110. if j%2 else 90.
        net = compute_round_trip_net_return(100., closing)
        final = "LONG" if net > 0 and not missing else "CASH"
        proposed = None if missing else "LONG"
        policy = {"anchor_action": "CASH", "reason": "BYPASS" if missing else "ACCEPT" if final == "LONG" else "REJECT_NONPOSITIVE_Q10_DELTA_U",
                  "fact_assertions_valid": True, "eligible": not missing, "q10_delta_U_net_fraction": None if missing else .01 if final == "LONG" else -.01}
        branches = {n: {"action": final if n == FULL else "CASH", "raw_proposed_action": proposed if n == FULL else "SHORT",
                       "policy": deepcopy(policy), "bypass": missing, "request_ids": []} for n in NAMES}
        branches[VIRTUAL[0]] = {"action": "LONG" if proposed else "CASH", "diagnostic_only": True}
        branches[VIRTUAL[1]] = deepcopy(branches[VIRTUAL[0]])
        if r: branches["Original_duplicate"] = {"action": "LONG", "policy": None}
        day = pd.Timestamp(pid[4:])
        points.append({"point_id": pid, "symbol": pid[:3], "as_of_date": pid[4:], "repeat_index": r,
            "context": {"K": 0 if missing else 3, "m": j%9, "status": "UNAVAILABLE" if missing else "AVAILABLE",
                "regime": "CHOPPY", "bucket": "UNKNOWN" if missing else "MACD_POS_PRICE_POS", "full_supported": not missing},
            "branches": branches, "evaluation": {"entry_open": 100., "exit_close": closing,
                "entry_date": str((day+pd.Timedelta(days=1)).date()), "exit_date": str((day+pd.Timedelta(days=3)).date()),
                "net_return_long": net, "actual_direction": "UP" if net > 0 else "DOWN"}})
    return source_from(points), protocol, {"requests": []}


def source_from(points: list[dict]) -> dict:
    """Dựng account nguồn từ chính helper engine để consumer có hợp đồng đối soát."""
    accounts = {str(r): {s: {n: account([p for p in points if p["repeat_index"] == r and p["symbol"] == s], n)
        for n in (*NAMES, *VIRTUAL, *(("Original_duplicate",) if r else ()))} for s in SYMBOLS} for r in range(4)}
    return {"status": "PASS", "phase": "development2023", "run_signature": "fixture", "binding": {},
            "points": points, "accounts": accounts, "confirmation_allowed": False}


class AnalysisTests(unittest.TestCase):
    """Các guard có hệ quả kinh tế; không kiểm kiểu mirror từng dòng implementation."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.source, cls.protocol, cls.ledger = fixture()
        cls.report = build_report(cls.source, cls.protocol, cls.ledger)
        cls.primary = cls.report["primary_cases"]

    def test_keeps_G60_missing_features_and_repeat_separate(self) -> None:
        self.assertEqual(self.report["G"]["count"], 60)
        self.assertEqual(sum(p["context"]["status"] == "UNAVAILABLE" for p in self.primary), 10)
        self.assertEqual(self.report["strata"]["support"]["UNSUPPORTED"]["count"], 10)
        self.assertEqual(self.report["repeat"]["groups"]["0"]["count"], 12)
        self.assertEqual(self.report["repeat"]["Original_duplicate"]["denominator"], 36)
        self.assertEqual(self.report["repeat"]["disagreement"][FULL]["dependent_pairs"], 72)

    def test_account_mean_is_four_account_returns_not_mean_cycle(self) -> None:
        value = self.report["G"]
        expected = sum(value["stocks"][s][FULL]["account"]["metrics"]["total_return_pct"] for s in SYMBOLS)/4
        self.assertEqual(value["branches"][FULL]["mean_account_return_pct"], expected)
        cycles = sum(p["evaluation"]["net_return_long"]*(p["branches"][FULL]["action"] == "LONG") for p in self.primary)/60*100
        self.assertNotAlmostEqual(expected, cycles)

    def test_all_cash_accuracy_not_return_and_no_trade_hit_rate_null(self) -> None:
        value = self.report["G"]
        self.assertEqual(value["branches"]["Utility_only"]["mean_account_return_pct"], 0.)
        self.assertGreater(value["branches"]["Utility_only"]["accuracy"], 0.)
        self.assertIsNone(value["stocks"]["FPT"]["Utility_only"]["account"]["metrics"]["hit_rate_pct"])
        self.assertNotIn("sharpe_ratio", value["stocks"]["FPT"][FULL]["account"]["metrics"])

    def test_decomposition_closes_account_D_and_keeps_raw_proposals(self) -> None:
        value = self.report["decomposition"]
        self.assertAlmostEqual(sum(x["mean_delta_return_pp"] for x in value["steps"]), value["total_Full_Original_pp"])
        self.assertGreater(value["policy_effect_on_raw_proposals"].get("BENEFICIAL", 0), 0)
        self.assertTrue(any(p["raw_proposed_action"] is None for p in value["cases"]))
        self.assertEqual(len(value["cases"]), 60)

    def test_subgroup_missing_symbol_D_null_never_replaces_G(self) -> None:
        value = group([p for p in self.primary if p["symbol"] == "FPT"], Analysis())
        self.assertIsNone(value["contrasts"]["Original"]["mean_delta_return_pp"])
        self.assertIsNone(value["branches"][FULL]["mean_account_return_pct"])
        self.assertEqual(self.report["G"]["count"], 60)

    def test_sensitivity_reverts_change_keeps_all_G_and_has_no_mutation(self) -> None:
        before = content_hash(self.primary)
        value = sensitivity(self.primary, "Original", Analysis())
        self.assertTrue(value["leave_one_change_out"])
        self.assertEqual(set(value["leave_one_symbol_out"]), set(SYMBOLS))
        self.assertEqual(content_hash(self.primary), before)

    def test_nomination_positive_rule_does_not_release_confirmation(self) -> None:
        result = nominate(self.report, self.protocol)
        self.assertEqual(result["status"], "NOMINATED")
        self.assertEqual(result["nominated_candidate"], FULL)
        self.assertFalse(result["candidate_substitution"])
        self.assertFalse(result["confirmation"]["allowed"])

    def test_strict_zero_Full_FactAnchor_is_not_nominated(self) -> None:
        report = deepcopy(self.report)
        for p in report["primary_cases"]: p["branches"]["Fact_Anchor"]["action"] = p["branches"][FULL]["action"]
        report["G"] = group(report["primary_cases"], Analysis())
        result = nominate(report, self.protocol)
        self.assertEqual(result["status"], "NOT_NOMINATED")
        self.assertIn("D_Full_Fact_Anchor_gt_0", result["failure_reasons"])

    def test_strict_zero_Original_gap_fails_even_with_high_accuracy(self) -> None:
        report = deepcopy(self.report)
        for p in report["primary_cases"]: p["branches"]["Original"]["action"] = p["branches"][FULL]["action"]
        report["G"] = group(report["primary_cases"], Analysis())
        self.assertIn("D_Full_Original_gt_0", nominate(report, self.protocol)["failure_reasons"])

    def test_risk_guards_apply_to_account_MDD_mean_and_max(self) -> None:
        for symbols, close, reason in ((("MWG",), 94., "max_delta_MDD_le_5"), (SYMBOLS, 97.5, "mean_delta_MDD_le_2")):
            report = deepcopy(self.report)
            for symbol in symbols:
                p = next(p for p in report["primary_cases"] if p["symbol"] == symbol)
                p["branches"][FULL]["action"] = "LONG"
                p["evaluation"].update(exit_close=close, net_return_long=compute_round_trip_net_return(100., close), actual_direction="DOWN")
            report["G"] = group(report["primary_cases"], Analysis())
            with self.subTest(reason=reason): self.assertIn(reason, nominate(report, self.protocol)["failure_reasons"])

    def test_negative_A_gap_cannot_be_replaced_by_winning_ablation(self) -> None:
        report = deepcopy(self.report)
        for p in report["primary_cases"]: p["branches"]["A_reference"]["action"] = p["branches"][FULL]["action"]
        p = next(p for p in report["primary_cases"] if p["evaluation"]["net_return_long"] < 0)
        p["branches"][FULL]["action"] = "LONG"
        report["G"] = group(report["primary_cases"], Analysis())
        result = nominate(report, self.protocol)
        self.assertIn("D_Full_A_ge_0", result["failure_reasons"])
        self.assertFalse(result["candidate_substitution"])

    def test_only_two_positive_symbols_fail_even_if_aggregate_positive(self) -> None:
        report = deepcopy(self.report)
        for p in report["primary_cases"]:
            if p["symbol"] in ("FPT", "MWG"): p["branches"][FULL]["action"] = "CASH"
        report["G"] = group(report["primary_cases"], Analysis())
        result = nominate(report, self.protocol)
        self.assertGreater(result["metrics"]["D_Full_Original_pp"], 0)
        self.assertEqual(result["metrics"]["positive_symbols"], 2)
        self.assertIn("positive_symbols_at_least_3", result["failure_reasons"])

    def test_changed_rule_metrics_or_repeat_cannot_self_reseal(self) -> None:
        protocol = deepcopy(self.protocol)
        protocol["development"]["nomination"]["D_Full_Fact_Anchor_strict_min"] = -1
        with self.assertRaises(ValueError): nominate(self.report, protocol)
        report = deepcopy(self.report)
        report["G"]["branches"][FULL]["mean_account_return_pct"] += 1.
        with self.assertRaises(ValueError): nominate(report, self.protocol)
        report = deepcopy(self.report)
        report["primary_cases"][0]["repeat_index"] = 1
        with self.assertRaises(ValueError): nominate(report, self.protocol)

    def test_source_cycle_tamper_is_rejected_even_metrics_identical(self) -> None:
        source = deepcopy(self.source)
        source["accounts"]["0"]["FPT"][FULL]["cycles"][0]["equity_vnd"] += 1
        with self.assertRaises(ValueError): build_report(source, self.protocol, self.ledger)

    def test_bad_action_or_economic_label_never_becomes_cash(self) -> None:
        with self.assertRaises(ValueError): cash_action("UNKNOWN")
        source = deepcopy(self.source)
        source["points"][0]["evaluation"]["actual_direction"] = "UP"
        with self.assertRaises(ValueError): build_report(source, self.protocol, self.ledger)

    def minimal_actions(self) -> tuple[list, dict, dict, dict]:
        """Block missing feature có anchor LONG để phát hiện fallback CASH sai."""
        pid = "FPT-2023-01-06"
        order = list(NAMES[:-1])
        slots = [{"slot_index": i, "point_id": pid, "repeat_index": 0, "branch_id": n} for i,n in enumerate(order)]
        policy = {"final_action": "LONG", "anchor_action": "LONG", "fact_assertions_valid": True, "eligible": False}
        rows = [{"status": "complete", "slot": s, "policy": None if s["branch_id"] in ("Original", "A_reference") else deepcopy(policy),
                 "decision": None if s["branch_id"] == FULL else {"decision": "LONG"}, "bypass": s["branch_id"] == FULL,
                 "attempt_id": None, "request_ids": []} for s in slots]
        offline = {"final_action": "CASH", "bypass": False}
        branch = {"eligible": False, "probability": None, "utility": {}}
        snapshot = {"points": {pid: {"facts": {"bucket": "UNKNOWN"}, "variants": {FULL: branch, "No_target": branch, "Utility_only": {}}, "offline_utility_only": offline}}}
        manifest = {"layout": {"slots": slots, "blocks": [{"point_id": pid, "repeat_index": 0, "order": order}]}}
        contexts = {pid: {"K": 0, "m": 0, "status": "UNAVAILABLE", "query": {"regime": {"name": "UNKNOWN"}}}}
        return rows, manifest, snapshot, contexts

    def test_materialize_bypass_keeps_anchor_LONG_and_does_not_create_response(self) -> None:
        args = self.minimal_actions()
        with patch("core.mt_bicl_v3_audit.utility_only", return_value={"final_action": "CASH", "bypass": False}):
            point = materialize(*args)[0]
        self.assertEqual(point["branches"][FULL]["action"], "LONG")
        self.assertIsNone(point["branches"][FULL]["raw_decision"])
        self.assertEqual(point["branches"][VIRTUAL[0]]["action"], "LONG")
        self.assertEqual(point["branches"]["Utility_only"]["action"], "CASH")

    def test_materialize_incomplete_fails_before_economic_access(self) -> None:
        args = self.minimal_actions()
        args[0][0]["status"] = "unknown"
        with patch("core.mt_bicl_v3_audit.utility_only", side_effect=AssertionError("Chưa được đi tiếp")):
            with self.assertRaises(ValueError): materialize(*args)

    def test_materialize_2025_query_is_rejected_before_offline_policy(self) -> None:
        args = self.minimal_actions()
        for row in args[0]: row["slot"]["point_id"] = "FPT-2025-01-06"
        args[1]["layout"]["blocks"][0]["point_id"] = "FPT-2025-01-06"
        with patch("core.mt_bicl_v3_audit.utility_only", side_effect=AssertionError("Không mở2025")):
            with self.assertRaises(ValueError): materialize(*args)

    def test_saved_artifact_cannot_be_silently_overwritten(self) -> None:
        from scripts.analyze_mt_bicl_v3 import save
        with TemporaryDirectory() as temporary:
            root, path = Path(temporary), Path("report.json")
            save(root, path, "fixture", {"result": 1}, False)
            before = (root/path).read_bytes()
            with self.assertRaises(ValueError): save(root, path, "fixture", {"result": 2}, False)
            self.assertEqual((root/path).read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
