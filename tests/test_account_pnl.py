"""Kiểm thử hợp đồng tài khoản lãi kép cho backtest."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.backtest_engine import BacktestEngine, TestPoint, compute_account_metrics


def _test_point(
    test_id: int,
    entry_open: float,
    exit_close: float,
    pred_full: str = "LONG",
    pred_no_alpha: str = "LONG",
) -> TestPoint:
    entry_time = datetime(2024, 1, 1) + timedelta(days=(test_id - 1) * 3)
    exit_time = entry_time + timedelta(days=2)
    direction = "UP" if exit_close >= entry_open else "DOWN"
    pct_change = (
        (exit_close / entry_open - 1.0) * 100.0
        if entry_open > 0.0
        else 0.0
    )
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
        self.assertEqual(pct_change, 0.0)

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
        self.assertEqual(pct_change, 10.0)

    def test_two_long_trades_compound_and_charge_each_execution(self):
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

        # Mỗi LONG chịu 0,35%: 1.0965 * 0.8965 - 1 = -1.698775%.
        self.assertAlmostEqual(metrics.total_return_pct, -1.698775, places=6)
        self.assertEqual(metrics.equity_curve, [1.0, 1.0965, 0.98301225])
        self.assertAlmostEqual(points[0].account_return_full, 9.65, places=8)
        self.assertAlmostEqual(points[1].account_return_full, -10.35, places=8)
        self.assertAlmostEqual(points[1].pnl_full, -1.698775, places=6)

    def test_losing_long_always_reduces_equity_and_cumulative_pnl(self):
        points = [
            _test_point(1, 100.0, 110.0),
            _test_point(2, 100.0, 99.0),
        ]

        metrics = compute_account_metrics(points)["full"]

        self.assertLess(points[1].account_return_full, 0.0)
        self.assertLess(points[1].equity_full, points[0].equity_full)
        self.assertLess(points[1].pnl_full, points[0].pnl_full)
        self.assertEqual(points[1].executed_action_full, "LONG")
        self.assertAlmostEqual(points[1].execution_pct_change, -1.0, places=8)
        self.assertEqual(metrics.equity_curve[-1], points[1].equity_full)

    def test_flat_long_loses_transaction_cost(self):
        point = _test_point(1, 100.0, 100.0)

        compute_account_metrics([point])

        self.assertAlmostEqual(point.execution_pct_change, 0.0, places=8)
        self.assertAlmostEqual(point.account_return_full, -0.35, places=8)
        self.assertAlmostEqual(point.pnl_full, -0.35, places=8)

    def test_label_return_and_execution_return_are_kept_separate_after_gap(self):
        import pandas as pd

        # Close-to-close vẫn DOWN (100 -> 95), nhưng lệnh mua tại Open=90
        # thực sự có lãi trước phí (90 -> 95). Hai đại lượng không được nhập làm một.
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

        self.assertEqual(point.actual_direction, "DOWN")
        self.assertAlmostEqual(point.actual_pct_change, -5.0, places=8)
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

    def test_overlapping_long_uses_cash_without_cost_or_equity_change(self):
        first = _test_point(1, 100.0, 110.0)
        overlapping = _test_point(2, 100.0, 150.0)
        overlapping.entry_time = "2024-01-02T00:00:00"
        overlapping.exit_time = "2024-01-04T00:00:00"

        metrics = compute_account_metrics([first, overlapping])["full"]

        self.assertEqual(overlapping.executed_action_full, "CASH")
        self.assertEqual(
            overlapping.execution_skip_reason_full,
            "OVERLAP_CAPITAL_LOCKED",
        )
        self.assertEqual(overlapping.account_return_full, 0.0)
        self.assertEqual(overlapping.equity_full, first.equity_full)
        self.assertEqual(metrics.equity_curve, [1.0, 1.0965, 1.0965])
        self.assertAlmostEqual(metrics.avg_trade_pct, 9.65, places=8)

    def test_entry_on_prior_exit_date_is_still_overlap(self):
        first = _test_point(1, 100.0, 110.0)
        same_day = _test_point(2, 100.0, 120.0)
        same_day.entry_time = first.exit_time

        compute_account_metrics([first, same_day])

        self.assertEqual(same_day.executed_action_full, "CASH")
        self.assertEqual(
            same_day.execution_skip_reason_full,
            "OVERLAP_CAPITAL_LOCKED",
        )

    def test_entry_after_prior_exit_executes_normally(self):
        points = [
            _test_point(1, 100.0, 110.0),
            _test_point(2, 100.0, 120.0),
        ]

        compute_account_metrics(points)

        self.assertEqual(points[1].executed_action_full, "LONG")
        self.assertEqual(points[1].execution_skip_reason_full, "")
        self.assertAlmostEqual(points[1].account_return_full, 19.65, places=8)

    def test_full_and_no_alpha_have_independent_capital_locks(self):
        first = _test_point(
            1,
            100.0,
            110.0,
            pred_full="LONG",
            pred_no_alpha="SHORT",
        )
        overlapping = _test_point(2, 100.0, 120.0)
        overlapping.entry_time = "2024-01-02T00:00:00"
        overlapping.exit_time = "2024-01-04T00:00:00"

        compute_account_metrics([first, overlapping])

        self.assertEqual(overlapping.executed_action_full, "CASH")
        self.assertEqual(overlapping.executed_action_no_alpha, "LONG")
        self.assertEqual(overlapping.account_return_full, 0.0)
        self.assertAlmostEqual(
            overlapping.account_return_no_alpha,
            19.65,
            places=8,
        )

    def test_invalid_execution_times_fail_fast(self):
        point = _test_point(1, 100.0, 101.0)
        point.exit_time = "2023-12-31T00:00:00"

        with self.assertRaisesRegex(ValueError, "thời điểm entry/exit"):
            compute_account_metrics([point])

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

        self.assertEqual(metrics.equity_curve, [1.0, 1.1, 0.88, 0.924])
        self.assertAlmostEqual(metrics.max_drawdown_pct, 20.0, places=8)
        self.assertAlmostEqual(metrics.total_return_pct, -7.6, places=8)

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

        expected_curve = [1.0, 1.0965, 0.98301225]
        self.assertEqual(partial.equity_curve_full, expected_curve)
        self.assertEqual(summary.equity_curve_full, expected_curve)
        self.assertEqual(summary.pnl_full, -1.7)

        with tempfile.TemporaryDirectory() as temp_dir:
            result_path = str(Path(temp_dir) / "account_result.json")
            with patch("builtins.print"):
                engine._draw_backtest_result(summary, result_path)
            self.assertTrue(Path(temp_dir, "account_result.png").exists())


if __name__ == "__main__":
    unittest.main()
