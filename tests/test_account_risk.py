"""Kiểm tra risk ratio theo tần suất return thật và hợp đồng null cho callers."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from core.backtest_engine import BacktestEngine, TestPoint, compute_account_metrics
from utils.account_risk import cycle_frequency, risk_ratios
from scripts.audit_account_annualisation import daily_returns, economics_ast_check


def points() -> list[TestPoint]:
    """Giá/cutoff giả lập, bar index đều dù timestamp có weekend gap."""
    rows = []
    for index, (entry_date, exit_date, price) in enumerate((
        ("2024-01-04", "2024-01-08", 110.), ("2024-01-09", "2024-01-11", 90.),
        ("2024-01-12", "2024-01-16", 95.), ("2024-01-17", "2024-01-19", 105.))):
        rows.append(TestPoint(index + 1, "2023-01-01", entry_date, 100., price, "UP" if price > 100 else "DOWN",
                              price - 100, "LONG", price > 100, "Cao", "1.5", "SHORT", price <= 100,
                              "Cao", "1.5", 0., 0., entry_open=100., exit_close=price,
                              entry_time=entry_date, exit_time=exit_date, entry_bar_index=40 + index * 3,
                              exit_bar_index=42 + index * 3))
    return rows


class AccountRiskTests(unittest.TestCase):
    """Oracle tần suất/SD, lịch không đều và JSON của các caller bị ảnh hưởng."""

    def test_daily_and_three_session_ratios_scale_by_sqrt_three(self) -> None:
        returns = [.1, -.1, -.05, .05]
        daily, cycle = risk_ratios(returns, 252), risk_ratios(returns, 84)
        for key in ("sharpe_ratio", "sortino_ratio"):
            self.assertAlmostEqual(cycle[key], daily[key] / np.sqrt(3))
        nonzero = risk_ratios([.12, -.1, -.04, .06], 84)
        self.assertAlmostEqual(nonzero["sharpe_ratio"], np.mean([.12, -.1, -.04, .06]) /
                               np.std([.12, -.1, -.04, .06], ddof=0) * np.sqrt(84))
        self.assertAlmostEqual(nonzero["sortino_ratio"], np.mean([.12, -.1, -.04, .06]) /
                               np.std([-.1, -.04], ddof=0) * np.sqrt(84))

    def test_observed_bar_schedule_handles_weekends_without_calendar_guess(self) -> None:
        frequency = cycle_frequency(points(), "1 ngày", 3)
        self.assertEqual(frequency["periods_per_year"], 84)
        self.assertEqual(frequency["frequency_status"], "regular_observed_daily_cycles")

    def test_unknown_indices_and_intraday_are_not_daily(self) -> None:
        rows = points()
        rows[0].entry_bar_index = None
        self.assertIsNone(cycle_frequency(rows, "1d", 3)["periods_per_year"])
        self.assertIsNone(cycle_frequency(points(), "1h", 3)["periods_per_year"])
        self.assertIsNone(cycle_frequency(points()[:1], "1d", 3)["periods_per_year"])

    def test_irregular_or_gapped_cycles_require_daily_ledger(self) -> None:
        rows = points()
        rows[2].entry_bar_index += 1
        self.assertEqual(cycle_frequency(rows, "1d", 3)["frequency_status"], "irregular_or_gapped_cycles")
        rows = points()
        for i, row in enumerate(rows):
            row.entry_bar_index = i * 6
            row.exit_bar_index = i * 6 + 2
        self.assertIsNone(cycle_frequency(rows, "1d", 6)["periods_per_year"])

    def test_constant_cash_and_no_downside_are_undefined(self) -> None:
        for values in ([], [0, 0], [.1, .1]):
            result = risk_ratios(values, 84)
            self.assertIsNone(result["sharpe_ratio"])
            self.assertIsNone(result["sortino_ratio"])
            json.dumps(result, allow_nan=False)
        self.assertIsNone(risk_ratios([.1, .2], 84)["sortino_ratio"])
        self.assertIsNone(risk_ratios([-.1, .2], 84)["sortino_ratio"])

    def test_unspecified_frequency_never_claims_annualised_ratio(self) -> None:
        result = risk_ratios([.12, -.1, -.04, .06], None)
        self.assertIsNotNone(result["sharpe_unannualised"])
        self.assertIsNone(result["sharpe_ratio"])
        self.assertIsNone(result["sortino_ratio"])

    def test_invalid_returns_or_frequency_are_rejected(self) -> None:
        for frequency in (0, -1, float("nan"), float("inf"), True):
            with self.assertRaises(ValueError):
                risk_ratios([.1, -.1], frequency)
        with self.assertRaises(ValueError):
            risk_ratios([float("nan"), .1], 252)

    def test_account_pnl_equity_and_drawdown_do_not_depend_on_annualisation(self) -> None:
        daily = compute_account_metrics(points(), fee=0, slippage=0,
                                        risk_frequency={"periods_per_year": 252})["full"]
        cycle = compute_account_metrics(points(), fee=0, slippage=0,
                                        risk_frequency=cycle_frequency(points(), "1d", 3))["full"]
        for field in ("period_returns", "equity_curve", "max_drawdown_pct", "total_return_pct", "final_cash_vnd"):
            self.assertEqual(getattr(daily, field), getattr(cycle, field))
        self.assertEqual(cycle.risk_metrics["drawdown_basis"], "cycle_end_including_initial_wealth")
        json.dumps(asdict(cycle), allow_nan=False)

    def test_partial_final_summary_and_cash_json_share_the_contract(self) -> None:
        engine = BacktestEngine({"use_historical_sentiment": False})
        rows = points()
        partial = engine._compute_partial(rows, timeframe="1d", step=3)
        summary = engine._build_summary("FPT", "1d", 4, 45, 3, rows, "2023-01-01", "2024-01-19")
        self.assertEqual(partial.sharpe_full, summary.sharpe_full)
        self.assertEqual(summary.risk_metrics_full["periods_per_year"], 84)
        self.assertIsNone(summary.sharpe_no_alpha)
        self.assertIsNone(summary.sortino_no_alpha)
        encoded = json.dumps(asdict(summary), allow_nan=False)
        self.assertIn('"sharpe_no_alpha": null', encoded)

    def test_legacy_summary_without_indices_is_explicitly_unverified(self) -> None:
        rows = points()
        for row in rows:
            row.entry_bar_index = row.exit_bar_index = None
        engine = BacktestEngine({"use_historical_sentiment": False})
        summary = engine._build_summary("FPT", "1d", 4, 45, 3, rows, "2023-01-01", "2024-01-19")
        self.assertIsNone(summary.sharpe_full)
        self.assertEqual(summary.risk_metrics_full["frequency_status"], "missing_bar_indices")

    def test_daily_ledger_anchor_and_cash_gaps_are_retained(self) -> None:
        values = daily_returns([90., 90., 99.], 100.)
        np.testing.assert_allclose(values, [-.1, 0., .1], atol=1e-15)
        self.assertEqual(len(values), 3)
        with self.assertRaises(ValueError):
            daily_returns([0., 1.], 100.)

    def test_ast_guard_rejects_unrelated_economics_change(self) -> None:
        unchanged = "\n".join(f"def {name}():\n    return 1\n" for name in
            ("_validate_account_costs", "compute_round_trip_net_return", "_get_actual_direction", "_parse_prediction",
             "_run_ablation_variants", "_run_paired_point"))
        before = ("def compute_variant():\n    cash = 1\n    returns_array = []\n    equity_array = []\n    peak = 1\n    return cash\n" + unchanged).encode()
        after = before.replace(b"returns_array = []", b"frequency = {}")
        self.assertTrue(all(economics_ast_check(before, after).values()))
        with self.assertRaises(ValueError):
            economics_ast_check(before, after.replace(b"cash = 1", b"cash = 2"))


if __name__ == "__main__":
    unittest.main()
