"""Hồi quy settlement/fill/cost sensitivity và thông tin quá khứ cho cap."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from core.revision_baselines import daily_ledger
from core.revision_execution import execution_ledger

POLICY = json.loads((Path(__file__).resolve().parents[1] / "revision/r15_execution_policy.json").read_bytes())


def scenario(**overrides: object) -> dict:
    """Khóa defaults, chỉ thay tham số đang kiểm tra."""
    return {**POLICY["defaults"], **overrides}


def frame() -> pd.DataFrame:
    """Dữ liệu giả có history capacity và weekend gaps, không dùng làm evidence thị trường."""
    close = np.full(45, 100.)
    close[22:25] = [90, 95, 110]
    close[25:28] = [100, 105, 120]
    return pd.DataFrame({"date": pd.bdate_range("2024-01-01", periods=45).strftime("%Y-%m-%d"),
                         "Open": np.full(45, 100.), "High": np.maximum(close, 100) + 1,
                         "Low": np.minimum(close, 100) - 1, "Close": close, "Volume": np.full(45, 100000.)})


class ExecutionTests(unittest.TestCase):
    """Oracle ledger độc lập, state conservation và lỗi timing tại open/close."""

    def test_reference_matches_frozen_daily_ledger_formula(self) -> None:
        data = frame()
        cycles = [(22, 24, 1, "a"), (25, 27, 1, "b")]
        config = {"fee_each_side": .0025, "slippage_each_side": .001, "initial_capital_vnd": 50000000.}
        expected = daily_ledger(data, [(e, x, a) for e, x, a, _ in cycles], config)
        actual = execution_ledger(data, cycles, scenario(), 50000000.)
        for field in ("net_return_pct", "daily_close_drawdown_pct", "brokerage_fee_vnd", "slippage_cost_vnd", "order_count"):
            self.assertAlmostEqual(actual["summary"][field], expected[field], places=7)
        np.testing.assert_allclose([r["equity_vnd"] for r in actual["daily"][:6]], [r["equity_vnd"] for r in expected["daily"]])

    def test_pending_cash_is_wealth_but_not_available_next_open(self) -> None:
        result = execution_ledger(frame(), [(22, 24, 1, "a"), (25, 27, 1, "b")], scenario(cash_mode="pending", stock_lag=2), 50000000.)
        self.assertEqual(result["summary"]["n_buy_fills"], 1)
        self.assertGreater(result["daily"][2]["pending_cash_vnd"], 0)
        self.assertAlmostEqual(result["daily"][2]["settled_cash_vnd"], 0, places=7)
        self.assertEqual(result["daily"][4]["pending_cash_vnd"], 0)
        self.assertEqual(result["daily"][4]["equity_vnd"], result["daily"][2]["equity_vnd"])

    def test_t_plus_two_afternoon_is_not_spendable_same_open(self) -> None:
        data = frame()
        blocked = execution_ledger(data, [(22, 24, 1, "a"), (26, 28, 1, "b")], scenario(cash_mode="pending"), 50000000.)
        allowed = execution_ledger(data, [(22, 24, 1, "a"), (27, 29, 1, "b")], scenario(cash_mode="pending"), 50000000.)
        self.assertEqual(blocked["summary"]["n_buy_fills"], 1)
        self.assertEqual(allowed["summary"]["n_buy_fills"], 2)

    def test_advance_assigns_receivable_once_and_charges_actual_calendar_days(self) -> None:
        data = frame()
        result = execution_ledger(data, [(22, 24, 1, "a"), (25, 27, 1, "b")],
                                  scenario(cash_mode="advance_on_demand", stock_lag=2), 50000000.)
        advance = next(e for e in result["events"] if e["side"] == "ADVANCE")
        days = (pd.Timestamp(data["date"].iloc[26]) - pd.Timestamp(data["date"].iloc[25])).days
        self.assertAlmostEqual(advance["fee_vnd"], advance["principal_vnd"] * .15 * days / 365)
        self.assertEqual(result["summary"]["n_buy_fills"], 2)
        self.assertAlmostEqual(result["summary"]["advance_fee_vnd"], advance["fee_vnd"])
        immediate = execution_ledger(data, [(22, 24, 1, "a"), (25, 27, 1, "b")], scenario(), 50000000.)
        self.assertLess(result["summary"]["net_return_pct"], immediate["summary"]["net_return_pct"])

    def test_auto_advance_cost_exists_without_next_purchase(self) -> None:
        result = execution_ledger(frame(), [(22, 24, 1, "a")], scenario(cash_mode="advance_auto"), 50000000.)
        self.assertGreater(result["summary"]["advance_fee_vnd"], 0)
        self.assertEqual(result["summary"]["final_pending_cash_vnd"], 0)

    def test_delayed_buy_respects_stock_maturity_and_fixed_prediction(self) -> None:
        data = frame()
        data.loc[22, "Volume"] = 0
        cycles = [(22, 24, 1, "a")]
        result = execution_ledger(data, cycles, scenario(block_proxy=True, entry_delay=2, stock_lag=2), 50000000.)
        fills = [e for e in result["events"] if e["status"] == "filled"]
        self.assertEqual(fills[0]["date"], data["date"].iloc[23])
        self.assertEqual(fills[1]["date"], data["date"].iloc[25])
        self.assertEqual(cycles, [(22, 24, 1, "a")])
        self.assertTrue(all(e["clock_time"] is None and e["phase"] in ("open", "close") for e in result["events"]))

    def test_blocked_exit_keeps_residual_stock_mtm(self) -> None:
        data = frame()
        data.loc[24:, ["Open", "High", "Low", "Close"]] = 80.
        result = execution_ledger(data, [(22, 24, 1, "a")], scenario(block_proxy=True, stock_lag=2), 50000000.)
        self.assertEqual(result["summary"]["n_sell_fills"], 0)
        self.assertGreater(result["summary"]["final_shares"], 0)
        self.assertFalse(result["summary"]["terminal_is_liquidated"])
        self.assertGreater(result["daily"][-1]["stock_mtm_vnd"], 0)
        self.assertEqual(result["summary"]["sell_charge_vnd"], 0)
        self.assertGreater(result["daily"][0]["unsettled_shares"], 0)
        self.assertEqual(result["daily"][0]["settled_shares"], 0)
        self.assertGreater(result["daily"][2]["settled_shares"], 0)
        self.assertEqual(result["daily"][2]["unsettled_shares"], 0)

    def test_capacity_uses_past_volume_and_round_lots(self) -> None:
        data = frame()
        data["Volume"] = 20000.
        config = scenario(participation=.01, lot_size=100)
        result = execution_ledger(data, [(22, 24, 1, "a")], config, 50000000.)
        buy = next(e for e in result["events"] if e["side"] == "BUY" and e["status"] == "filled")
        self.assertEqual(buy["quantity"], 200.)
        changed = data.copy()
        changed.loc[22:, "Volume"] *= 1000
        other = execution_ledger(changed, [(22, 24, 1, "a")], config, 50000000.)
        other_buy = next(e for e in other["events"] if e["side"] == "BUY" and e["status"] == "filled")
        self.assertEqual(buy["quantity"], other_buy["quantity"])

    def test_insufficient_lot_capacity_and_all_missed_are_cash(self) -> None:
        for config in (scenario(participation=.00001, lot_size=100), scenario(all_entries_missed=True)):
            result = execution_ledger(frame(), [(22, 24, 1, "a")], config, 50000000.)
            self.assertEqual(result["summary"]["n_buy_fills"], 0)
            self.assertEqual(result["summary"]["net_return_pct"], 0)
            self.assertEqual(result["summary"]["daily_close_drawdown_pct"], 0)

    def test_fixed_fill_cost_ordering_and_no_infinite_outputs(self) -> None:
        cycles = [(22, 24, 1, "a"), (25, 27, 1, "b")]
        low = execution_ledger(frame(), cycles, scenario(fee_each_side=.001, slippage_each_side=.0005), 50000000.)
        high = execution_ledger(frame(), cycles, scenario(fee_each_side=.005, slippage_each_side=.003, sell_charge=.001), 50000000.)
        self.assertGreater(low["summary"]["net_return_pct"], high["summary"]["net_return_pct"])
        json.dumps(high, allow_nan=False)

    def test_input_not_mutated_and_future_poison_does_not_change_past_events(self) -> None:
        data = frame()
        original = data.copy(deep=True)
        config = scenario(cash_mode="pending")
        result = execution_ledger(data, [(22, 24, 1, "a")], config, 50000000.)
        pd.testing.assert_frame_equal(data, original)
        changed = data.copy()
        changed.loc[25:, ["Open", "High", "Low", "Close"]] *= 10
        other = execution_ledger(changed, [(22, 24, 1, "a")], config, 50000000.)
        self.assertEqual(result["daily"][:3], other["daily"][:3])
        self.assertEqual(config, scenario(cash_mode="pending"))

    def test_invalid_schedule_and_policy_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            execution_ledger(frame(), [(22, 24, 1, "a"), (24, 26, 1, "b")], scenario(), 50000000.)
        for config in (scenario(lot_size=-1), scenario(fee_each_side=-1), scenario(participation=0)):
            with self.assertRaises(ValueError):
                execution_ledger(frame(), [(22, 24, 1, "a")], config, 50000000.)

    def test_maturity_outside_snapshot_remains_pending_without_invented_fee(self) -> None:
        result = execution_ledger(frame(), [(42, 44, 1, "a")], scenario(cash_mode="advance_auto"), 50000000.)
        self.assertGreater(result["summary"]["final_pending_cash_vnd"], 0)
        self.assertEqual(result["summary"]["advance_fee_vnd"], 0)
        self.assertTrue(any(e["status"] == "maturity_outside_snapshot" for e in result["events"]))


if __name__ == "__main__":
    unittest.main()
