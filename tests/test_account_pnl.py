"""Kiểm thử hợp đồng tài khoản lãi kép cho backtest."""

from __future__ import annotations

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
    direction = "UP" if exit_close >= entry_open else "DOWN"
    pct_change = (exit_close / entry_open - 1.0) * 100.0
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
