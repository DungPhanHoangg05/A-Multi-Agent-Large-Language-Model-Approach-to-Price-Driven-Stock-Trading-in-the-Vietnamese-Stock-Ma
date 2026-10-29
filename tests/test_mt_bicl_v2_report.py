"""Kiểm tính đúng mẫu số, kinh tế, repeat và phép so teacher của báo cáo development."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pandas as pd

from core.backtest_engine import compute_round_trip_net_return
from core.mt_bicl_bank import content_hash
from core.mt_bicl_v2_audit import account
from core.mt_bicl_v2_io import write_envelope
from core.mt_bicl_v2_report import (
    Analysis, FIGURE, FULL, NAMES, REPORT, SYMBOLS, VERSION, actions, approximation, build_report, kl_gap, save_or_verify,
)


def fixture() -> tuple[dict, dict, dict]:
    """Chỉ mượn lịch đã đăng ký; action, p và payoff đều giả, không gọi API."""
    manifest = json.loads(Path("docs/plan/week11/development_run_manifest_v2.json").read_text(encoding="utf-8"))["payload"]
    points = []
    for block in manifest["layout"]["blocks"]:
        pid, r, j = block["point_id"], block["repeat_index"], block["point_index"]
        missing = j%6 == 0
        branches = {}
        for i, name in enumerate(NAMES):
            value = "LONG" if (j+r+i)%3 == 0 else "SHORT"
            if name == FULL:
                value = "LONG" if (j+r)%5 in (0, 1) else "SHORT"
            if name in ("Numeric_only", "Teacher_only"):
                probability = None if missing else .51 if name == "Numeric_only" and j == 1 else .48 if name == "Numeric_only" else .49
                branches[name] = {"action": "LONG" if probability is not None and probability > .5 else "CASH", "probability": probability}
            else:
                branches[name] = {"action": value, "shared_off_from": None if not missing or name == "Original" else 0}
        if r:
            branches["Original_duplicate"] = {"action": "LONG" if (j+r)%2 else "SHORT", "shared_off_from": None}
        day = pd.Timestamp(pid[4:])
        closing = 110. if j%2 else 90.
        points.append({"point_id": pid, "symbol": pid[:3], "as_of_date": pid[4:], "repeat_index": r,
            "context": {"K": 0 if missing else 3, "m": 0 if missing else 2, "regime": "CHOPPY",
                        "status": "UNAVAILABLE" if missing else "AVAILABLE", "reasons": ["FIXTURE_MISSING"] if missing else []},
            "branches": branches, "evaluation": {"entry_open": 100., "exit_close": closing,
                "entry_date": str((day+pd.Timedelta(days=1)).date()), "exit_date": str((day+pd.Timedelta(days=3)).date()),
                "net_return_long": compute_round_trip_net_return(100., closing), "actual_direction": "UP" if closing > 100 else "DOWN"}})
    accounts = {str(r): {s: {n: account([p for p in points if p["symbol"] == s and p["repeat_index"] == r], n)
                for n in NAMES+(("Original_duplicate",) if r else ())} for s in SYMBOLS} for r in range(4)}
    def row(identifier: str, branch: str, repeat: int, invocation: str, latency: float | None) -> dict:
        """Telemetry giả có thiếu số đo để kiểm null và filter invocation."""
        return {"id": identifier, "run_signature": "fixture", "branch_id": branch, "invocation_id": invocation,
            "improvement_audit": {"slot": {"repeat_index": repeat}}, "latency_seconds": latency, "pacing_seconds": 2.}
    ledger = {"requests": [row("h1","Original",0,"i1",1.),row("h2","Original_duplicate",1,"i2",None)],
        "invocations": {"i1": {"run_signature":"fixture","elapsed_seconds":10.,"wait_seconds":2.},
                        "i2": {"run_signature":"fixture","elapsed_seconds":20.,"wait_seconds":2.},
                        "unrelated": {"run_signature":"fixture","elapsed_seconds":999.,"wait_seconds":999.}}}
    return {"status":"PASS","phase":"development2023","run_signature":"fixture","points":points,
            "accounts":accounts,"account_contract":{"shares":"ENGINE_FRACTIONAL_SHARES_NO_BOARD_LOT"}},manifest,ledger


class ReportTests(unittest.TestCase):
    """Chỉ chọn các ca ảnh hưởng diễn giải kinh tế, common support hoặc integrity."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.source, cls.manifest, cls.ledger = fixture()
        cls.before = content_hash(cls.source)
        cls.report = build_report(cls.source,cls.manifest,cls.ledger)
        cls.primary = [p for p in cls.source["points"] if p["repeat_index"] == 0]

    def test_G_keeps_all60_and10_missing_feature(self) -> None:
        self.assertEqual(self.report["G"]["count"],60)
        self.assertEqual(self.report["support"]["feature_unavailable_retained"],10)
        self.assertEqual(self.report["support"]["excluded"],[])
        self.assertEqual(set(self.report["G"]["branches"]),set(NAMES))

    def test_D_is_equal_four_account_returns_not_mean_cycle_delta(self) -> None:
        a = Analysis()
        points = deepcopy(self.primary)
        for p in points:
            p["branches"][FULL]["action"] = "LONG"
            p["branches"]["Original"]["action"] = "CASH"
        result = a.contrast(points,FULL,"Original")
        expected = sum(account([p for p in points if p["symbol"] == s],FULL)["metrics"]["total_return_pct"] for s in SYMBOLS)/4
        cycle_mean = sum(p["evaluation"]["net_return_long"] for p in points)/len(points)*100
        self.assertAlmostEqual(result["mean_delta_return_pp"],expected)
        self.assertGreater(abs(expected-cycle_mean),.01)

    def test_empty_group_and_missing_symbol_do_not_fabricate_zero_D(self) -> None:
        a = Analysis()
        self.assertIsNone(a.group([])["branches"][FULL]["mean_account_return_pct"])
        group = a.group([p for p in self.primary if p["symbol"] == "FPT"])
        self.assertIsNone(group["contrasts"]["Original"]["mean_delta_return_pp"])
        self.assertEqual(group["contrasts"]["Original"]["contributing_symbol_count"],1)
        self.assertIsNotNone(group["contrasts"]["Original"]["descriptive_mean_available_symbols_pp"])

    def test_ACTION_direction_has_both_cross_cells(self) -> None:
        points = deepcopy(self.primary[:4])
        for p,(a,b) in zip(points,[("LONG","CASH"),("CASH","LONG"),("LONG","LONG"),("CASH","CASH")]):
            p["branches"][FULL]["action"] = a;p["branches"]["Original"]["action"] = b
        result=actions(points,FULL,"Original")
        self.assertEqual(result["counts"],{k:1 for k in ("CASH_TO_LONG","LONG_TO_CASH","LONG_TO_LONG","CASH_TO_CASH")})
        self.assertEqual(result["rate"],.5)

    def test_leave_one_change_out_reverts_action_and_keeps_G(self) -> None:
        cases=self.report["sensitivity"]["Original"]["leave_one_change_out"]
        self.assertTrue(cases)
        self.assertTrue(all(c["G_count"]==60 for c in cases))
        self.assertEqual({c["cycle_effect"] for c in cases},{"ADVERSE","BENEFICIAL"})
        case=cases[0];points=deepcopy(self.primary)
        p=next(p for p in points if p["point_id"]==case["point_id"])
        p["branches"][FULL]["action"]=p["branches"]["Original"]["action"]
        self.assertAlmostEqual(Analysis().contrast(points,FULL,"Original")["mean_delta_return_pp"],case["D_after_reverting_change_pp"])

    def test_leave_one_symbol_out_means_remaining_three(self) -> None:
        values=self.report["G"]["contrasts"]["Original"]["by_symbol"]
        for s in SYMBOLS:
            expected=sum(v["delta_return_pp"] for k,v in values.items() if k!=s)/3
            self.assertAlmostEqual(self.report["sensitivity"]["Original"]["leave_one_symbol_out"][s],expected)

    def test_all_strata_present_including_empty_adverse_groups(self) -> None:
        self.assertEqual(set(self.report["strata"]["quarter"]),{"Q1","Q2","Q3","Q4"})
        self.assertEqual(set(self.report["strata"]["K"]),{"0","1","2","3"})
        self.assertEqual(set(self.report["strata"]["m"]),{str(i) for i in range(9)})
        self.assertEqual(self.report["strata"]["regime"]["BULL"]["reason"],"NO_SUPPORT")
        self.assertEqual(self.report["strata"]["feature_status"]["UNAVAILABLE"]["count"],10)

    def test_repeat_is12_points_and72_dependent_pairs_not_primary_N(self) -> None:
        repeat=self.report["repeat"]
        self.assertFalse(repeat["in_primary"])
        self.assertTrue(all(g["count"]==12 for g in repeat["groups"].values()))
        self.assertEqual(repeat["disagreement"][FULL]["comparisons"],72)
        self.assertEqual(repeat["original_duplicate"]["denominator"],36)
        self.assertEqual(self.report["G"]["count"],60)
        self.assertEqual(len(repeat["contrasts"]["Original"]["D_by_repeat_pp"]),4)

    def test_repeat_group_sorts_stratum_sample_for_account_time(self) -> None:
        ids=self.report["repeat"]["groups"]["0"]["stocks"]["FPT"][FULL]["account"]["point_ids"]
        self.assertEqual(ids,sorted(ids))
        self.assertEqual(len(ids),3)

    def test_approximation_uses50_probabilities_and_all60_action_denominator(self) -> None:
        result=self.report["approximation"]
        self.assertEqual((result["G_count"],result["probability_count"],len(result["excluded"])),(60,50,10))
        self.assertEqual(result["action_disagreement_on_G"]["denominator"],60)
        self.assertEqual(result["probability_action_disagreement_count"],1)
        self.assertGreaterEqual(result["mean_kl_nats"],0.)

    def test_KL_endpoints_and_infinite_are_not_clipped(self) -> None:
        self.assertEqual(kl_gap(0.,0.),0.)
        self.assertEqual(kl_gap(1.,1.),0.)
        self.assertIsNone(kl_gap(0.,.1))
        self.assertIsNone(kl_gap(1.,.9))
        for bad in (float("nan"),float("inf"),-.1,1.1,True):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                kl_gap(bad,.4)

    def test_cash_only_hit_rate_is_null_not_zero_success(self) -> None:
        result=self.report["G"]["stocks"]["FPT"]["Teacher_only"]
        self.assertIsNone(result["account"]["metrics"]["hit_rate_pct"])
        self.assertEqual(result["hit_rate_reason"],"NO_LONG")

    def test_latency_scopes_invocations_and_keeps_missing_measurement(self) -> None:
        primary=self.report["telemetry"]["primary"]["Original"]["http"]
        repeat=self.report["telemetry"]["repeat"]["Original_duplicate"]["http"]
        self.assertEqual(primary["invocation_elapsed_seconds"]["sum"],10.)
        self.assertEqual(repeat["invocation_elapsed_seconds"]["sum"],20.)
        self.assertEqual(repeat["http_latency_seconds"]["missing_count"],1)
        self.assertIsNone(repeat["http_latency_seconds"]["sum"])
        self.assertIsNone(self.report["offline_latency"]["Numeric_only"]["value"])

    def test_source_account_tamper_is_rejected(self) -> None:
        source=deepcopy(self.source)
        source["accounts"]["0"]["FPT"][FULL]["metrics"]["total_return_pct"]+=1
        with self.assertRaisesRegex(ValueError,"Account nguồn"):
            build_report(source,self.manifest,self.ledger)

    def test_missing_primary_duplicate_wrong_phase_or_branch_fail(self) -> None:
        for mode in ("missing","duplicate","phase","branch"):
            source=deepcopy(self.source)
            if mode=="missing":source["points"].pop(0)
            if mode=="duplicate":source["points"].append(deepcopy(source["points"][0]))
            if mode=="phase":source["phase"]="confirmation2025"
            if mode=="branch":source["points"][0]["branches"].pop("Original")
            with self.subTest(mode=mode),self.assertRaises(ValueError):
                build_report(source,self.manifest,self.ledger)

    def test_invalid_action_never_becomes_cash(self) -> None:
        point=deepcopy(self.primary[0]);point["branches"][FULL]["action"]="unknown"
        with self.assertRaises(ValueError):
            actions([point],FULL,"Original")

    def test_input_unchanged_and_no_nomination_or_confirmation(self) -> None:
        self.assertEqual(content_hash(self.source),self.before)
        self.assertEqual(self.report["nomination"],"NOT_EVALUATED")
        self.assertFalse(self.report["confirmation_allowed"])

    def test_rehashed_report_tamper_is_not_overwritten(self) -> None:
        with TemporaryDirectory() as tmp,patch("core.mt_bicl_v2_report.figure_bytes",return_value=b"fixture-png"):
            root=Path(tmp);save_or_verify(root,self.report)
            save_or_verify(root,self.report,verify_only=True)
            changed=deepcopy(self.report);changed["G"]["count"]=60.
            write_envelope(root/REPORT,VERSION,changed)
            before=(root/REPORT).read_bytes()
            with self.assertRaises(ValueError):save_or_verify(root,self.report)
            self.assertEqual((root/REPORT).read_bytes(),before)
            self.assertEqual((root/FIGURE).read_bytes(),b"fixture-png")


if __name__ == "__main__":
    unittest.main()
