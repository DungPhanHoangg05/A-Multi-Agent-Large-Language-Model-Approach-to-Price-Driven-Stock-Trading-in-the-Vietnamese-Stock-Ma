"""Kiểm biên audit: không biến lỗi thành CASH, không trộn repeat và không lệch kinh tế/PIT."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pandas as pd

from core.backtest_engine import compute_round_trip_net_return
from core.mt_bicl_bank import content_hash
from core.mt_bicl_v2_audit import (
    REPORT, RUN, VERSION, account, check_labels, evaluate_cycle, offline_decision, save_or_verify, snapshot,
)
from core.mt_bicl_v2_io import write_envelope
from scripts.verify_mt_bicl_development import reject_network


def point(day: str, action: str = "LONG", closing: float = 110.) -> dict:
    """Một cycle khép kín cho tài khoản fixture; không có response API tổng hợp."""
    cutoff = pd.Timestamp(day)
    return {"point_id": "FPT-"+day, "symbol": "FPT", "as_of_date": day, "repeat_index": 0,
        "branches": {"Full_MT_BICL": {"action": action}}, "evaluation": {
            "entry_open": 100., "exit_close": closing,
            "entry_date": str((cutoff+pd.Timedelta(days=1)).date()),
            "exit_date": str((cutoff+pd.Timedelta(days=3)).date()),
            "actual_direction": "UP" if compute_round_trip_net_return(100., closing) > 0 else "DOWN"}}


class OfflineAuditTests(unittest.TestCase):
    """Các trường hợp biên có hậu quả kinh tế hoặc làm mất mẫu nghiên cứu."""

    def test_strict_threshold_and_missing_feature(self) -> None:
        self.assertEqual(offline_decision(.5, True)["action"], "CASH")
        self.assertEqual(offline_decision(.5000000001, True)["action"], "LONG")
        self.assertEqual(offline_decision(None, False)["reason"], "QUERY_FEATURE_UNAVAILABLE")

    def test_bad_probability_never_becomes_cash(self) -> None:
        for p in (None, float("nan"), float("inf"), -.1, 1.1, True, "0.6"):
            with self.subTest(p=p), self.assertRaises(ValueError):
                offline_decision(p, True)
        with self.assertRaises(ValueError):
            offline_decision(.6, False)

    def test_engine_compounds_each_cycle_and_audits_both_fees(self) -> None:
        points = [point("2023-01-01"), point("2023-02-01", closing=90.)]
        before = deepcopy(points)
        result = account(points, "Full_MT_BICL")
        expected = 50_000_000.*(1+compute_round_trip_net_return(100.,110.))*(1+compute_round_trip_net_return(100.,90.))
        self.assertAlmostEqual(result["metrics"]["final_equity_vnd"], expected, places=6)
        self.assertGreater(result["metrics"]["max_drawdown_pct"], 0.)
        self.assertTrue(all(c["transaction_fee_vnd"] > 0 and c["slippage_cost_vnd"] > 0 for c in result["cycles"]))
        self.assertNotIn("sharpe_ratio", result["metrics"])
        self.assertIsNone(result["risk"]["annualization_factor"])
        self.assertEqual(points, before)

    def test_short_cash_and_fractional_engine_contract(self) -> None:
        for action in ("SHORT", "CASH"):
            with self.subTest(action=action):
                result = account([point("2023-01-01", action)], "Full_MT_BICL")
                self.assertEqual(result["metrics"]["final_equity_vnd"], 50_000_000.)
                self.assertEqual(result["cycles"][0]["transaction_fee_vnd"], 0.)
                self.assertEqual(result["cycles"][0]["executed_action"], "CASH")

    def test_invalid_action_missing_and_duplicate_are_not_filtered(self) -> None:
        for points in ([], [point("2023-01-01", "ERROR")], [point("2023-01-01")]*2):
            with self.subTest(points=points), self.assertRaises(ValueError):
                account(points, "Full_MT_BICL")

    def test_repeat_symbol_overlap_and_unsorted_fail(self) -> None:
        a,b = point("2023-01-01"),point("2023-02-01")
        for field,value in (("repeat_index",1),("symbol","VCB")):
            changed=deepcopy(b);changed[field]=value
            with self.subTest(field=field), self.assertRaises(ValueError):
                account([a,changed],"Full_MT_BICL")
        for points in ([b,a],[a,point("2023-01-02")]):
            with self.assertRaises(ValueError):
                account(points,"Full_MT_BICL")

    def test_account_detects_engine_equity_and_mdd_drift(self) -> None:
        from core.backtest_engine import compute_account_metrics
        def changed(points: list, **kwargs: object) -> dict:
            """Mô phỏng một engine sai lệch để kiểm phép audit độc lập của caller."""
            result = compute_account_metrics(points, **kwargs)
            setattr(result["full"], field, getattr(result["full"], field)+1.)
            return result
        for field in ("final_equity_vnd", "max_drawdown_pct"):
            with self.subTest(field=field), patch("core.mt_bicl_v2_audit.compute_account_metrics", side_effect=changed), self.assertRaises(ValueError):
                account([point("2023-01-01")], "Full_MT_BICL")

    def test_execution_uses_trading_sessions_not_calendar_days(self) -> None:
        dates=pd.to_datetime(["2023-01-06","2023-01-09","2023-01-10","2023-01-11"])
        frame=pd.DataFrame({"Datetime":dates,"Open":[100.,120.,100.,100.],"Close":[100.,100.,100.,110.],
                            "High":[101.,121.,101.,111.],"Low":[99.,99.,99.,99.],"Volume":[1000]*4,"Reference":[100.]*4})
        result=evaluate_cycle(frame,[],"2023-01-06")
        self.assertEqual((result["entry_date"],result["exit_date"]),("2023-01-09","2023-01-11"))
        self.assertEqual((result["entry_open"],result["exit_close"]),(120.,110.))
        self.assertEqual(result["actual_direction"],"DOWN")
        for bad in (frame.iloc[:-1],frame.iloc[::-1],pd.concat([frame,frame.iloc[-1:]])):
            with self.assertRaises(ValueError):
                evaluate_cycle(bad,[],"2023-01-06")

    def test_context_label_checks_helper_and_exit_before_query(self) -> None:
        net=compute_round_trip_net_return(100.,100.)
        row={"episode_id":"FPT-2022-01-01","symbol":"FPT","as_of_date":"2022-01-01",
             "entry_date":"2022-01-02","exit_date":"2022-01-04","task_id":"P1","y":0,"r_net":net}
        episode={"query":{"as_of_date":"2023-01-01"},"prior":[{"observations":[row]}],"target":[]}
        bank={row["episode_id"]:{**row,"outcome":{"entry_open":100.,"exit_close":100.,"y":0,"r_net":net}}}
        self.assertEqual(check_labels(episode,bank),1)
        for field,value in (("y",1),("r_net",0.),("exit_date","2023-01-01")):
            changed=deepcopy(episode);changed["prior"][0]["observations"][0][field]=value
            with self.subTest(field=field), self.assertRaises(ValueError):
                check_labels(changed,bank)

    def test_context_audit_never_reads_query_outcome(self) -> None:
        class ForbidQuery(dict):
            """Le query không được mở nhãn ngay cả khi bank có payload đó."""
            def __getitem__(self, key: str) -> object:
                raise AssertionError("Đã mở outcome query trước cố định action")
        self.assertEqual(check_labels({"query":{"as_of_date":"2023-01-01"},"prior":[],"target":[]},ForbidQuery()),0)

    def test_snapshot_rejects_rehashed_run_and_never_reseals(self) -> None:
        with TemporaryDirectory() as tmp:
            root=Path(tmp);(root/RUN).mkdir(parents=True)
            ledger=root/"outputs/oos_pilot/api_usage.json";ledger.parent.mkdir(parents=True);ledger.write_text("{}")
            with self.assertRaisesRegex(ValueError,"nghiệm thu"):
                snapshot(root)

    def test_report_tamper_rehashed_is_rejected_and_original_not_overwritten(self) -> None:
        with TemporaryDirectory() as tmp:
            root=Path(tmp);expected={"status":"PASS","equity":50_000_000.}
            save_or_verify(root,expected)
            self.assertTrue((root/REPORT).exists())
            save_or_verify(root,expected,verify_only=True)
            changed={**expected,"equity":60_000_000.}
            write_envelope(root/REPORT,VERSION,changed)
            before=(root/REPORT).read_bytes()
            with self.assertRaises(ValueError):
                save_or_verify(root,expected)
            self.assertEqual((root/REPORT).read_bytes(),before)

    def test_cli_has_explicit_network_denial(self) -> None:
        with self.assertRaises(AssertionError):
            reject_network("example.invalid",443)


if __name__ == "__main__":
    unittest.main()
