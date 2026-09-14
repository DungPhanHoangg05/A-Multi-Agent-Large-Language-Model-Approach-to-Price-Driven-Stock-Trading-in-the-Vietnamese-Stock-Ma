"""Kiểm thử hợp đồng tài khoản lãi kép cho backtest."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.backtest_engine import (
    BacktestEngine,
    TestPoint,
    compute_account_metrics,
    compute_round_trip_net_return,
)
from utils.static_util import generate_backtest_summary_chart


def _test_point(
    test_id: int,
    entry_open: float,
    exit_close: float,
    pred_full: str = "LONG",
    pred_no_alpha: str = "LONG",
) -> TestPoint:
    entry_time = datetime(2024, 1, 1) + timedelta(days=(test_id - 1) * 3)
    exit_time = entry_time + timedelta(days=2)
    net_return = (
        compute_round_trip_net_return(entry_open, exit_close)
        if entry_open > 0.0
        else 0.0
    )
    direction = "UP" if net_return > 0.0 else "DOWN"
    pct_change = net_return * 100.0
    return TestPoint(
        test_id=test_id,
        window_start="2024-01-01",
        window_end="2024-01-02",
        actual_prev_close=entry_open,
        actual_next_close=exit_close,
        actual_direction=direction,
        actual_pct_change=pct_change,
        pred_full=pred_full,
        correct_full=(pred_full == "LONG" and direction == "UP"),
        confidence_full="N/A",
        rr_full="N/A",
        pred_no_alpha=pred_no_alpha,
        correct_no_alpha=(pred_no_alpha == "LONG" and direction == "UP"),
        confidence_no_alpha="N/A",
        rr_no_alpha="N/A",
        time_full_sec=0.0,
        time_no_alpha_sec=0.0,
        entry_open=entry_open,
        exit_close=exit_close,
        entry_time=entry_time.isoformat(),
        exit_time=exit_time.isoformat(),
    )


class AccountPnlTests(unittest.TestCase):
    def test_long_buys_with_all_cash_and_marks_position_in_vnd(self):
        point = _test_point(1, 100.0, 110.0, pred_no_alpha="SHORT")

        metrics = compute_account_metrics(
            [point],
            fee=0.01,
            slippage=0.0,
            initial_capital_vnd=1_000.0,
            price_multiplier=1.0,
        )["full"]

        expected_shares = 1_000.0 / (100.0 * 1.01)
        expected_equity = expected_shares * 110.0 * 0.99
        self.assertEqual(point.executed_action_full, "BUY")
        self.assertAlmostEqual(point.cash_full_vnd, 0.0, places=8)
        self.assertAlmostEqual(point.shares_full, expected_shares, places=8)
        self.assertAlmostEqual(point.transaction_fee_full_vnd, 1_000.0 / 1.01 * 0.01, places=4)
        self.assertAlmostEqual(point.equity_full_vnd, expected_equity, places=4)
        self.assertAlmostEqual(metrics.final_equity_vnd, expected_equity, places=8)

    def test_repeated_long_holds_without_second_buy_fee(self):
        points = [
            _test_point(1, 100.0, 110.0),
            _test_point(2, 115.0, 120.0),
        ]

        compute_account_metrics(
            points,
            fee=0.01,
            slippage=0.0,
            initial_capital_vnd=1_000.0,
            price_multiplier=1.0,
        )

        self.assertEqual(points[0].executed_action_full, "BUY")
        self.assertEqual(points[1].executed_action_full, "HOLD")
        self.assertEqual(points[1].transaction_fee_full_vnd, 0.0)
        self.assertAlmostEqual(points[1].shares_full, points[0].shares_full, places=8)

    def test_short_sells_all_shares_and_charges_sell_fee(self):
        points = [
            _test_point(1, 100.0, 110.0, pred_full="LONG"),
            _test_point(2, 120.0, 119.0, pred_full="SHORT"),
        ]

        metrics = compute_account_metrics(
            points,
            fee=0.01,
            slippage=0.0,
            initial_capital_vnd=1_000.0,
            price_multiplier=1.0,
        )["full"]

        shares = 1_000.0 / (100.0 * 1.01)
        gross_sell = shares * 120.0
        expected_cash = gross_sell * 0.99
        self.assertEqual(points[1].executed_action_full, "SELL")
        self.assertAlmostEqual(points[1].transaction_fee_full_vnd, gross_sell * 0.01, places=4)
        self.assertEqual(points[1].shares_full, 0.0)
        self.assertAlmostEqual(points[1].cash_full_vnd, expected_cash, places=4)
        self.assertAlmostEqual(metrics.final_cash_vnd, expected_cash, places=8)
        self.assertAlmostEqual(metrics.final_equity_vnd, expected_cash, places=8)

    def test_short_without_position_keeps_fifty_million_cash(self):
        point = _test_point(
            1,
            100.0,
            90.0,
            pred_full="SHORT",
            pred_no_alpha="SHORT",
        )

        metrics = compute_account_metrics([point])["full"]

        self.assertEqual(point.executed_action_full, "CASH")
        self.assertEqual(point.execution_skip_reason_full, "NO_POSITION")
        self.assertEqual(point.cash_full_vnd, 50_000_000.0)
        self.assertEqual(point.equity_full_vnd, 50_000_000.0)
        self.assertEqual(metrics.total_pnl_vnd, 0.0)

    def test_unchanged_close_is_down_not_up_for_binary_classification(self):
        import pandas as pd

        df = pd.DataFrame(
            {
                "Open": [99.0, 100.0],
                "Close": [100.0, 100.0],
            }
        )
        engine = BacktestEngine({"use_historical_sentiment": False})

        direction, _, _, pct_change, _ = engine._get_actual_direction(
            df, end_idx=1, lookahead=1
        )

        self.assertEqual(direction, "DOWN")
        self.assertAlmostEqual(
            pct_change,
            compute_round_trip_net_return(100.0, 100.0) * 100.0,
            places=4,
        )

    def test_engine_uses_open_e_as_entry_and_horizon_close_as_exit(self):
        import pandas as pd

        df = pd.DataFrame(
            {
                "Open": [99.0, 105.0, 108.0, 111.0],
                "Close": [100.0, 107.0, 110.0, 115.0],
            }
        )
        engine = BacktestEngine({"use_historical_sentiment": False})

        direction, prev_close, exit_close, pct_change, entry_open = (
            engine._get_actual_direction(df, end_idx=1, lookahead=2)
        )

        self.assertEqual(direction, "UP")
        self.assertEqual(prev_close, 100.0)
        self.assertEqual(entry_open, 105.0)
        self.assertEqual(exit_close, 110.0)
        self.assertAlmostEqual(
            pct_change,
            compute_round_trip_net_return(105.0, 110.0) * 100.0,
            places=4,
        )

    def test_screenshot_case_uses_net_execution_return_for_accuracy_label(self):
        import pandas as pd

        df = pd.DataFrame(
            {
                "Open": [29.4, 29.9],
                "Close": [29.4, 29.5],
            }
        )
        engine = BacktestEngine({"use_historical_sentiment": False})

        direction, prev_close, exit_close, pct_change, entry_open = (
            engine._get_actual_direction(df, end_idx=1, lookahead=1)
        )
        point = _test_point(1, entry_open, exit_close, pred_full="LONG")
        compute_account_metrics([point])

        self.assertEqual(prev_close, 29.4)
        self.assertEqual(direction, "DOWN")
        self.assertAlmostEqual(
            pct_change,
            compute_round_trip_net_return(29.9, 29.5) * 100.0,
            places=4,
        )
        self.assertAlmostEqual(
            point.account_return_full,
            pct_change,
            places=4,
        )
        self.assertFalse(point.pred_full == "LONG" and direction == "UP")

    def test_gain_below_cost_is_down_for_economic_label(self):
        import pandas as pd

        df = pd.DataFrame(
            {
                "Open": [100.0, 100.0],
                "Close": [100.0, 100.2],
            }
        )
        engine = BacktestEngine({"use_historical_sentiment": False})

        direction, _, _, pct_change, _ = engine._get_actual_direction(
            df, end_idx=1, lookahead=1
        )

        self.assertEqual(direction, "DOWN")
        self.assertAlmostEqual(
            pct_change,
            compute_round_trip_net_return(100.0, 100.2) * 100.0,
            places=4,
        )

    def test_two_long_signals_buy_once_then_hold_same_position(self):
        points = [
            _test_point(1, 100.0, 110.0),
            _test_point(2, 100.0, 90.0),
        ]

        metrics = compute_account_metrics(
            points,
            allow_shorting=False,
            fee=0.0025,
            slippage=0.001,
        )["full"]

        expected_first = 1.0 + compute_round_trip_net_return(100.0, 110.0)
        expected_final = 1.0 + compute_round_trip_net_return(100.0, 90.0)
        self.assertAlmostEqual(metrics.total_return_pct, (expected_final - 1.0) * 100.0, places=6)
        self.assertAlmostEqual(metrics.equity_curve[1], expected_first, places=10)
        self.assertAlmostEqual(metrics.equity_curve[2], expected_final, places=10)
        self.assertEqual(points[0].executed_action_full, "BUY")
        self.assertEqual(points[1].executed_action_full, "HOLD")
        self.assertEqual(points[1].transaction_fee_full_vnd, 0.0)

    def test_losing_long_always_reduces_equity_and_cumulative_pnl(self):
        points = [
            _test_point(1, 100.0, 110.0),
            _test_point(2, 100.0, 99.0),
        ]

        metrics = compute_account_metrics(points)["full"]

        self.assertLess(points[1].account_return_full, 0.0)
        self.assertLess(points[1].equity_full, points[0].equity_full)
        self.assertLess(points[1].pnl_full, points[0].pnl_full)
        self.assertEqual(points[1].executed_action_full, "HOLD")
        self.assertAlmostEqual(points[1].execution_pct_change, -1.0, places=8)
        self.assertEqual(metrics.equity_curve[-1], points[1].equity_full)

    def test_flat_long_loses_transaction_cost(self):
        point = _test_point(1, 100.0, 100.0)

        compute_account_metrics([point])

        self.assertAlmostEqual(point.execution_pct_change, 0.0, places=8)
        expected = compute_round_trip_net_return(100.0, 100.0) * 100.0
        self.assertAlmostEqual(point.account_return_full, expected, places=8)
        self.assertAlmostEqual(point.pnl_full, expected, places=8)

    def test_economic_label_follows_profitable_execution_after_gap(self):
        import pandas as pd

        # Close-to-close là DOWN (100 -> 95), nhưng giao dịch Open-to-Close
        # thực sự có lãi sau phí (90 -> 95), nên nhãn kinh tế phải là UP.
        df = pd.DataFrame(
            {
                "Open": [99.0, 90.0],
                "Close": [100.0, 95.0],
            }
        )
        engine = BacktestEngine({"use_historical_sentiment": False})
        direction, prev_close, exit_close, pct_change, entry_open = (
            engine._get_actual_direction(df, end_idx=1, lookahead=1)
        )
        point = _test_point(1, entry_open, exit_close)
        point.actual_prev_close = prev_close
        point.actual_direction = direction
        point.actual_pct_change = pct_change

        compute_account_metrics([point])

        self.assertEqual(point.actual_direction, "UP")
        self.assertAlmostEqual(
            point.actual_pct_change,
            compute_round_trip_net_return(90.0, 95.0) * 100.0,
            places=4,
        )
        self.assertAlmostEqual(
            point.execution_pct_change,
            100.0 * (95.0 / 90.0 - 1.0),
            places=8,
        )
        self.assertGreater(point.account_return_full, 0.0)

    def test_invalid_prices_and_costs_fail_fast(self):
        with self.assertRaisesRegex(ValueError, "giá entry/exit"):
            compute_account_metrics([_test_point(1, 0.0, 100.0)])

        with self.assertRaisesRegex(ValueError, "fee"):
            compute_account_metrics([_test_point(1, 100.0, 101.0)], fee=-0.01)

    def test_overlapping_test_points_fail_fast(self):
        first = _test_point(1, 100.0, 110.0)
        overlapping = _test_point(2, 100.0, 150.0)
        overlapping.entry_time = "2024-01-02T00:00:00"
        overlapping.exit_time = "2024-01-04T00:00:00"

        with self.assertRaisesRegex(ValueError, "chồng lấn"):
            compute_account_metrics([first, overlapping])

    def test_entry_on_prior_exit_date_is_still_overlap(self):
        first = _test_point(1, 100.0, 110.0)
        same_day = _test_point(2, 100.0, 120.0)
        same_day.entry_time = first.exit_time

        with self.assertRaisesRegex(ValueError, "chồng lấn"):
            compute_account_metrics([first, same_day])

    def test_entry_after_prior_exit_executes_normally(self):
        points = [
            _test_point(1, 100.0, 110.0),
            _test_point(2, 100.0, 120.0),
        ]

        compute_account_metrics(points)

        self.assertEqual(points[1].executed_action_full, "HOLD")
        self.assertEqual(points[1].execution_skip_reason_full, "ALREADY_LONG")
        self.assertEqual(points[1].transaction_fee_full_vnd, 0.0)

    def test_full_and_no_alpha_have_independent_portfolio_state(self):
        first = _test_point(
            1,
            100.0,
            110.0,
            pred_full="LONG",
            pred_no_alpha="SHORT",
        )
        second = _test_point(2, 100.0, 120.0)

        compute_account_metrics([first, second])

        self.assertEqual(second.executed_action_full, "HOLD")
        self.assertEqual(second.executed_action_no_alpha, "BUY")
        self.assertGreater(second.shares_full, 0.0)
        self.assertGreater(second.shares_no_alpha, 0.0)

    def test_invalid_execution_times_fail_fast(self):
        point = _test_point(1, 100.0, 101.0)
        point.exit_time = "2023-12-31T00:00:00"

        with self.assertRaisesRegex(ValueError, "thời điểm entry/exit"):
            compute_account_metrics([point])

    def test_daily_stateful_backtest_rejects_overlapping_step(self):
        import pandas as pd

        engine = BacktestEngine({"use_historical_sentiment": False})
        with self.assertRaisesRegex(ValueError, "step=1.*horizon=3"):
            engine.run(
                pd.DataFrame(),
                symbol="FPT",
                timeframe="1 ngày",
                step=1,
            )

    def test_short_and_unknown_are_cash_without_cost(self):
        points = [
            _test_point(1, 100.0, 80.0, pred_full="SHORT", pred_no_alpha="SHORT"),
            _test_point(2, 100.0, 120.0, pred_full="UNKNOWN", pred_no_alpha="UNKNOWN"),
        ]

        metrics = compute_account_metrics(points, allow_shorting=False)

        for variant in (metrics["full"], metrics["no_alpha"]):
            self.assertEqual(variant.total_return_pct, 0.0)
            self.assertEqual(variant.period_returns, [0.0, 0.0])
            self.assertEqual(variant.equity_curve, [1.0, 1.0, 1.0])
            self.assertEqual(variant.sharpe_ratio, 0.0)
            self.assertEqual(variant.max_drawdown_pct, 0.0)

    def test_drawdown_is_computed_from_compounded_equity_curve(self):
        points = [
            _test_point(1, 100.0, 110.0),
            _test_point(2, 100.0, 80.0),
            _test_point(3, 100.0, 105.0),
        ]

        metrics = compute_account_metrics(points, fee=0.0, slippage=0.0)["full"]

        self.assertEqual(metrics.equity_curve, [1.0, 1.1, 0.8, 1.05])
        self.assertAlmostEqual(metrics.max_drawdown_pct, 100.0 * (1.0 - 0.8 / 1.1), places=8)
        self.assertAlmostEqual(metrics.total_return_pct, 5.0, places=8)

    def test_partial_and_final_summaries_expose_same_equity_curve(self):
        points = [
            _test_point(1, 100.0, 110.0),
            _test_point(2, 100.0, 90.0),
        ]
        engine = BacktestEngine({"use_historical_sentiment": False})

        partial = engine._compute_partial(points)
        summary = engine._build_summary(
            "FPT", "1 ngày", 2, 45, 3, points, "2024-01-01", "2024-02-01"
        )

        expected_curve = [
            1.0,
            round(1.0 + compute_round_trip_net_return(100.0, 110.0), 12),
            round(1.0 + compute_round_trip_net_return(100.0, 90.0), 12),
        ]
        self.assertEqual(partial.equity_curve_full, expected_curve)
        self.assertEqual(summary.equity_curve_full, expected_curve)
        self.assertEqual(summary.pnl_full, round((expected_curve[-1] - 1.0) * 100.0, 2))
        self.assertEqual(summary.initial_capital_vnd, 50_000_000.0)

        with tempfile.TemporaryDirectory() as temp_dir:
            result_path = str(Path(temp_dir) / "account_result.json")
            with patch("builtins.print"):
                engine._draw_backtest_result(summary, result_path)
            self.assertTrue(Path(temp_dir, "account_result.png").exists())

            summary_chart = str(Path(temp_dir) / "summary_result.png")
            generate_backtest_summary_chart(asdict(summary), summary_chart)
            self.assertTrue(Path(summary_chart).exists())


if __name__ == "__main__":
    unittest.main()
