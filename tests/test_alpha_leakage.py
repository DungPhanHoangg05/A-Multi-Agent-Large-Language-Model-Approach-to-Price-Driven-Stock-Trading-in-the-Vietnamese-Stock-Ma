"""Kiểm thử chống rò rỉ dữ liệu tương lai khi chọn alpha động."""

from __future__ import annotations

import unittest
from pathlib import Path
import sys
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.alpha_selector import select_top_alphas


def _make_ohlcv(periods: int = 700) -> pd.DataFrame:
    dates = pd.date_range("2022-01-03", periods=periods, freq="B")
    close = np.linspace(20.0, 90.0, periods)
    return pd.DataFrame(
        {
            "Datetime": dates,
            "Open": close - 0.2,
            "High": close + 0.5,
            "Low": close - 0.5,
            "Close": close,
            "Volume": np.arange(periods, dtype=float) + 10_000.0,
        }
    )


def _fake_backtest(df: pd.DataFrame, **_: object) -> pd.DataFrame:
    """Trả thứ hạng phụ thuộc dữ liệu nhận được để phát hiện future leakage."""
    score = float(df["Close"].mean())
    return pd.DataFrame(
        [
            {
                "alpha_id": "CURRENT_1_FDM",
                "ic": score,
                "accuracy": 0.6,
                "long_acc": 0.6,
                "sharpe": 1.0,
            },
            {
                "alpha_id": "CURRENT_2_SFA",
                "ic": -score,
                "accuracy": 0.5,
                "long_acc": 0.5,
                "sharpe": 0.0,
            },
        ]
    )


class AlphaLeakageTests(unittest.TestCase):
    def test_backtest_without_snapshot_never_falls_back_to_realtime(self):
        with patch("utils.alpha_selector.load_data") as realtime_loader:
            with self.assertRaisesRegex(ValueError, "historical_df"):
                select_top_alphas("FPT", is_backtest=True)

        realtime_loader.assert_not_called()

    def test_historical_snapshot_is_cut_at_as_of_date_and_limited_to_600_rows(self):
        history = _make_ohlcv()
        as_of_date = history["Datetime"].iloc[649]
        captured: list[pd.DataFrame] = []

        def capture_backtest(df: pd.DataFrame, **kwargs: object) -> pd.DataFrame:
            captured.append(df.copy())
            return _fake_backtest(df, **kwargs)

        with (
            patch("utils.alpha_selector.load_data") as realtime_loader,
            patch("utils.alpha_selector.run_backtest", side_effect=capture_backtest),
        ):
            select_top_alphas(
                "FPT",
                historical_df=history,
                as_of_date=as_of_date,
                is_backtest=True,
            )

        realtime_loader.assert_not_called()
        self.assertEqual(len(captured), 1)
        selected_history = captured[0]
        self.assertEqual(len(selected_history), 600)
        self.assertLessEqual(selected_history["Datetime"].max(), as_of_date)
        self.assertEqual(selected_history["Datetime"].max(), as_of_date)

    def test_future_mutations_do_not_change_alpha_ranking(self):
        history = _make_ohlcv()
        as_of_date = history["Datetime"].iloc[599]
        mutated = history.copy()
        mutated.loc[mutated["Datetime"] > as_of_date, "Close"] *= 1_000.0

        with (
            patch("utils.alpha_selector.load_data") as realtime_loader,
            patch("utils.alpha_selector.run_backtest", side_effect=_fake_backtest),
        ):
            original = select_top_alphas(
                "FPT",
                historical_df=history,
                as_of_date=as_of_date,
                is_backtest=True,
            )
            changed_future = select_top_alphas(
                "FPT",
                historical_df=mutated,
                as_of_date=as_of_date,
                is_backtest=True,
            )

        realtime_loader.assert_not_called()
        self.assertEqual(len(original), 2)
        self.assertEqual(len(changed_future), 2)
        self.assertEqual(
            [item["alpha_id"] for item in original],
            [item["alpha_id"] for item in changed_future],
        )
        self.assertEqual(
            [item["composite_score"] for item in original],
            [item["composite_score"] for item in changed_future],
        )

    def test_backtest_engine_places_exact_snapshot_and_cutoff_in_state(self):
        from core.backtest_engine import BacktestEngine

        history = _make_ohlcv(120)
        snapshot = history.iloc[:100].copy()
        captured_state: dict = {}

        class FakeGraph:
            def invoke(self, state: dict) -> dict:
                captured_state.update(state)
                return state

        engine = BacktestEngine({"use_historical_sentiment": False})
        with (
            patch("utils.static_util.generate_kline_image", return_value={}),
            patch("utils.static_util.generate_trend_image", return_value={}),
        ):
            engine._run_single(
                FakeGraph(),
                {"Datetime": [], "Open": [], "High": [], "Low": [], "Close": []},
                "FPT",
                "1 ngày",
                window_end_date="2022-05-20",
                point_in_time_df=snapshot,
            )

        self.assertIs(captured_state["point_in_time_df"], snapshot)
        self.assertEqual(captured_state["as_of_date"], snapshot["Datetime"].iloc[-1])
        self.assertLess(captured_state["as_of_date"], history["Datetime"].iloc[100])

    def test_alpha_agent_forwards_snapshot_and_cutoff_to_selector_path(self):
        from agents.alpha_agent import create_alpha_agent

        snapshot = _make_ohlcv(100)
        cutoff = snapshot["Datetime"].iloc[-1]
        state = {
            "stock_name": "FPT",
            "time_frame": "1 ngày",
            "kline_data": {},
            "is_backtest": True,
            "point_in_time_df": snapshot,
            "as_of_date": cutoff,
            "messages": [],
            "language": "vi",
        }

        with (
            patch("agents.alpha_agent._compute_all_alphas", return_value=([], {})) as compute,
            patch("agents.alpha_agent._build_alpha_report", return_value="report"),
            patch("agents.alpha_agent._llm_reason", return_value="reason"),
            patch("builtins.print"),
        ):
            create_alpha_agent(object())(state)

        kwargs = compute.call_args.kwargs
        self.assertIs(kwargs["historical_df"], snapshot)
        self.assertEqual(kwargs["as_of_date"], cutoff)
        self.assertTrue(kwargs["is_backtest"])


if __name__ == "__main__":
    unittest.main()
