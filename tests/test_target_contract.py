"""Đối chiếu net/gross, giá cutoff/entry và schema đánh giá không rò sang prompts."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import jsonschema
import numpy as np
import pandas as pd

from core.backtest_engine import BacktestEngine, TestPoint, compute_account_metrics
from core.alpha_compare import build_forward_execution_returns
from utils.target_contract import target_fields, validate_target_record
from agents.agent_state import IndicatorAgentState

SCHEMA = json.loads((Path(__file__).resolve().parents[1] / "revision/target_schema.json").read_bytes())


def frame() -> pd.DataFrame:
    """Gap và weekend giúp phân biệt ba loại return."""
    return pd.DataFrame({"Datetime": pd.to_datetime(["2024-01-05", "2024-01-08", "2024-01-09", "2024-01-10"]),
                         "Open": [100., 90., 92., 94.], "Close": [100., 91., 93., 95.]})


class TargetContractTests(unittest.TestCase):
    """Oracle gap, zero, chi phí, incomplete horizon và compatibility."""

    def test_overnight_gap_does_not_use_decision_close_as_entry(self) -> None:
        result = target_fields(frame(), 1, 3)
        self.assertEqual((result["decision_close"], result["entry_open"], result["exit_close"]), (100, 90, 95))
        self.assertEqual(result["label_net"], "UP")
        self.assertLess(result["exit_close"] / result["decision_close"] - 1, 0)
        jsonschema.validate(result, SCHEMA)

    def test_positive_gross_but_negative_net_is_down(self) -> None:
        data = frame(); data.loc[1, "Open"] = 100.; data.loc[3, "Close"] = 100.2
        result = target_fields(data, 1, 3)
        self.assertEqual(result["label_gross"], "UP")
        self.assertEqual(result["label_net"], "DOWN")

    def test_zero_returns_and_two_sided_fee_oracle(self) -> None:
        data = frame(); data.loc[3, "Close"] = data.loc[1, "Open"]
        zero = target_fields(data, 1, 3, 0, 0)
        self.assertEqual((zero["net_return"], zero["gross_return"]), (0., 0.))
        self.assertEqual((zero["label_net"], zero["label_gross"]), ("DOWN", "DOWN"))
        result = target_fields(data, 1, 3, .01, .02)
        self.assertAlmostEqual(result["net_return"], (.98 * .99) / (1.02 * 1.01) - 1)

    def test_holiday_uses_positions_and_incomplete_horizon_is_not_shortened(self) -> None:
        data = frame()
        self.assertEqual(target_fields(data, 1, 3)["target_horizon_bars"], 3)
        with self.assertRaises(ValueError): target_fields(data, 1, 4)
        self.assertEqual(BacktestEngine({})._get_actual_direction(data, 1, 4)[0], "UNKNOWN")
        for boundary, horizon in ((0, 3), (-1, 3), (1, 0), (True, 1)):
            with self.assertRaises(ValueError): target_fields(data, boundary, horizon)
            with self.assertRaises(ValueError): BacktestEngine({})._get_actual_direction(data, boundary, horizon)

    def test_alpha_and_engine_targets_remain_identical(self) -> None:
        data = frame()
        expected = target_fields(data, np.int64(1), np.int64(3))
        engine = BacktestEngine({"use_historical_sentiment": False})
        direction, previous, exit_price, pct, entry = engine._get_actual_direction(data, 1, 3)
        self.assertEqual(direction, expected["label_net"])
        self.assertEqual((previous, entry, exit_price), (100, 90, 95))
        self.assertEqual(pct, round(expected["net_return"] * 100, 4))
        self.assertAlmostEqual(build_forward_execution_returns(data).iloc[0], expected["net_return"])
        json.dumps(expected, allow_nan=False)

    def test_legacy_alias_is_not_automatically_migrated(self) -> None:
        point = TestPoint(1, "2024-01-01", "2024-01-05", 90, 95, "UP", 4., "LONG", True, "Cao", "1",
                          "SHORT", False, "Cao", "1", 0., 0., entry_open=90, exit_close=95,
                          entry_time="2024-01-08", exit_time="2024-01-10")
        compute_account_metrics([point])
        self.assertIsNone(point.decision_close)
        self.assertIsNone(point.label_net)
        self.assertEqual(point.label_contract_version, "legacy_unverified")
        jsonschema.validate(asdict(point), SCHEMA)

    def test_cost_sensitivity_does_not_relabel_the_primary_target(self) -> None:
        data = frame(); fields = target_fields(data, 1, 3)
        point = TestPoint(1, "2024-01-01", "2024-01-05", 100, 95, fields["label_net"], 4., "LONG", True,
                          "Cao", "1", "SHORT", False, "Cao", "1", 0., 0., entry_time="2024-01-08", exit_time="2024-01-10", **fields)
        before = (point.net_return, point.label_net, point.label_fee_each_side)
        compute_account_metrics([point], fee=.10, slippage=.02)
        self.assertEqual(before, (point.net_return, point.label_net, point.label_fee_each_side))
        self.assertLess(point.account_return_full, point.net_return * 100)

    def test_canonical_outcomes_are_not_graph_input_fields(self) -> None:
        for name in ("decision_close", "entry_open", "exit_close", "net_return", "gross_return", "label_net", "label_gross"):
            self.assertNotIn(name, IndicatorAgentState.__annotations__)

    def test_nondefault_prompt_costs_fail_before_network(self) -> None:
        for config in ({"tx_cost": .01}, {"slippage": .02}):
            with patch("langchain_groq.ChatGroq") as llm:
                with self.assertRaisesRegex(ValueError, "Phí label khác prompt"):
                    BacktestEngine(config)._init_graphs()
                llm.assert_not_called()

    def test_schema_rejects_incomplete_claimed_canonical_record(self) -> None:
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate({"label_contract_version": "net_cycle_v1", "decision_close": None}, SCHEMA)
        with self.assertRaises(ValueError): validate_target_record({"label_contract_version": "net_cycle_v1"})

    def test_tampered_canonical_label_and_return_are_rejected(self) -> None:
        record = target_fields(frame(), 1, 3)
        validate_target_record(record)
        for field, bad in (("label_net", "DOWN"), ("net_return", .99), ("actual_direction", "DOWN")):
            with self.assertRaises(ValueError): validate_target_record({**record, field: bad})
        validate_target_record({"actual_prev_close": 90., "entry_open": 90.})


if __name__ == "__main__":
    unittest.main()
