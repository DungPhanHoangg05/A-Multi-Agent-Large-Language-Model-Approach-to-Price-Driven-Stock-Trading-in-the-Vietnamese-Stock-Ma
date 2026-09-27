"""Kiểm nhãn bằng giá VCI thật và tình huống chi phí/lịch phiên xác định."""

import copy
import json
import unittest
from unittest.mock import patch

import pandas as pd

from core.backtest_engine import compute_round_trip_net_return
from core.bayesian_memory import DEFAULT_DATA_DIR, validate_historical_task_record
from core.execution_prices import build_verified_cycle_schedule, load_verified_execution_data
from core.historical_outcomes import HistoricalOutcomeGenerator

SIGNALS = {"trend": "BULLISH", "pattern": "NEUTRAL", "alpha_consensus": "BEARISH",
           "indicator_consensus": "NEUTRAL", "sentiment": "NEUTRAL"}


def fixture_frame(exit_close: float = 102.0) -> pd.DataFrame:
    """Bốn phiên bắc qua cuối tuần; Close(t) khác hẳn giá vào để phát hiện sai nhãn."""
    return pd.DataFrame({"Datetime": pd.to_datetime(["2020-06-05", "2020-06-08", "2020-06-09", "2020-06-10"]),
                         "Open": [200., 100., 101., exit_close], "High": [201., 101., 102., exit_close + 1],
                         "Low": [199., 99., 100., exit_close - 1], "Close": [200., 100., 101., exit_close],
                         "Volume": [1000] * 4, "Reference": [200., 200., 100., 101.]})


class HistoricalOutcomeTests(unittest.TestCase):
    def generate(self, frame=None, signals=None, settled="2020-06-10", events=None, **dates):
        generator = HistoricalOutcomeGenerator(lambda symbol: (fixture_frame() if frame is None else frame, events or []))
        return generator.generate("FPT", dates.get("as_of_date", "2020-06-05"),
                                  dates.get("entry_date", "2020-06-08"), dates.get("exit_date", "2020-06-10"),
                                  SIGNALS if signals is None else signals, settled_as_of=settled)

    def test_shared_engine_function_and_full_precision(self):
        with patch("core.historical_outcomes.compute_round_trip_net_return", wraps=compute_round_trip_net_return) as economic:
            outcome = self.generate()
        economic.assert_called_once_with(100., 102., fee=0.0025, slippage=0.001)
        self.assertEqual(outcome["net_return_pct"], 100 * compute_round_trip_net_return(100, 102))
        self.assertEqual(outcome["actual_direction"], "UP")
        self.assertEqual(outcome["result"], "WIN_IF_LONG")
        self.assertFalse(outcome["was_bull_trap"])

    def test_price_gain_below_costs_is_long_loss_and_bull_trap(self):
        outcome = self.generate(frame=fixture_frame(100.5))
        self.assertLess(outcome["net_return_pct"], 0)
        self.assertEqual(outcome["actual_direction"], "DOWN")
        self.assertEqual(outcome["result"], "LOSS_IF_LONG")
        self.assertTrue(outcome["was_bull_trap"])

    def test_bull_trap_needs_trend_or_pattern_bullish(self):
        signals = {**SIGNALS, "trend": "BEARISH", "alpha_consensus": "BULLISH"}
        self.assertFalse(self.generate(frame=fixture_frame(99), signals=signals)["was_bull_trap"])
        signals["pattern"] = "BULLISH"
        self.assertTrue(self.generate(frame=fixture_frame(99), signals=signals)["was_bull_trap"])

    def test_zero_net_return_is_loss_if_long(self):
        with patch("core.historical_outcomes.compute_round_trip_net_return", return_value=0.0):
            outcome = self.generate()
        self.assertEqual(outcome["net_return_pct"], 0.0)
        self.assertEqual(outcome["actual_direction"], "DOWN")
        self.assertEqual(outcome["result"], "LOSS_IF_LONG")

    def test_wrong_trading_session_and_missing_signal_rejected(self):
        for changes in ({"entry_date": "2020-06-06"}, {"exit_date": "2020-06-09"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.generate(**changes)
        with self.assertRaises(ValueError):
            self.generate(signals={"trend": "BULLISH"})

    def test_corporate_action_and_no_execution_volume_rejected(self):
        with self.assertRaises(ValueError):
            self.generate(events=[{"exrightDate": "2020-06-09"}])
        frame = fixture_frame()
        frame.loc[2, "Volume"] = 0
        with self.assertRaises(ValueError):
            self.generate(frame=frame)

    def test_native_json_types(self):
        outcome = self.generate()
        self.assertIs(type(outcome["net_return_pct"]), float)
        self.assertIs(type(outcome["was_bull_trap"]), bool)
        self.assertEqual(json.loads(json.dumps(outcome, allow_nan=False)), outcome)

    def test_verified_cycles_for_all_four_symbols_match_memory_validator(self):
        generator = HistoricalOutcomeGenerator()
        for symbol in ("FPT", "VNM", "VCB", "MWG"):
            with self.subTest(symbol=symbol):
                frame, events = load_verified_execution_data(DEFAULT_DATA_DIR, symbol)
                schedule = build_verified_cycle_schedule(frame, events)
                cycle = schedule.loc[schedule["eligible"]].iloc[0]
                dates = {key: cycle[key].strftime("%Y-%m-%d") for key in ("as_of_date", "entry_date", "exit_date")}
                outcome = generator.generate(symbol, **dates, agent_signals=SIGNALS, settled_as_of="2022-12-31")
                record = {"episode_id": f"{symbol}:{dates['as_of_date']}", "symbol": symbol,
                          **dates, "regime": "BULL", "agent_signals": copy.deepcopy(SIGNALS), "outcome": outcome}
                validate_historical_task_record(record, frame, events)


if __name__ == "__main__":
    unittest.main()
