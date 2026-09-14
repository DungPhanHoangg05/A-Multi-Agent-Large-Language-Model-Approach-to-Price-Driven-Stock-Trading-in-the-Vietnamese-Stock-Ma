"""Kiểm thử tính toàn vẹn của tín hiệu Alpha trước khi chạy benchmark."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.alpha_agent import _compute_all_alphas
from agents.decision_agent import (
    _distill_report,
    _safe_parse_and_enrich,
    create_final_trade_decider,
)
from core.alpha_compare import build_forward_execution_returns, rank_alphas
from core.backtest_engine import (
    ALPHA_HISTORY_CANDLES,
    BacktestEngine,
    build_walk_forward_end_indices,
    required_backtest_rows,
)
from core.realtime_loader import REQUIRED_COLS, _normalise_columns


def _history(periods: int = 180) -> pd.DataFrame:
    close = np.linspace(90.0, 110.0, periods)
    return pd.DataFrame(
        {
            "Datetime": pd.date_range("2024-01-01", periods=periods, freq="B"),
            "Open": close - 0.2,
            "High": close + 0.5,
            "Low": close - 0.5,
            "Close": close,
            "Volume": np.linspace(1_000_000.0, 2_000_000.0, periods),
        }
    )


class _DecisionLlm:
    def invoke(self, _messages):
        return SimpleNamespace(
            content='{"decision":"SHORT","confidence":"Cao",'
            '"risk_reward_ratio":2.0,"justification":"test"}'
        )


class _EmptyDecisionLlm:
    def invoke(self, _messages):
        return SimpleNamespace(content="")


class AlphaSignalIntegrityTests(unittest.TestCase):
    def test_empty_llm_output_falls_back_to_conservative_short(self):
        normalized = json.loads(_safe_parse_and_enrich("", "BHN", lang="vi"))

        self.assertEqual(normalized["decision"], "SHORT")
        self.assertEqual(normalized["decision_source"], "fallback_conservative")
        self.assertEqual(normalized["fallback_reason"], "EMPTY_RESPONSE")

    def test_none_output_falls_back_to_conservative_short(self):
        normalized = json.loads(_safe_parse_and_enrich(None, "BHN", lang="vi"))

        self.assertEqual(normalized["decision"], "SHORT")
        self.assertEqual(normalized["fallback_reason"], "EMPTY_RESPONSE")

    def test_neutral_llm_output_is_forced_to_binary_short(self):
        normalized = json.loads(
            _safe_parse_and_enrich(
                '{"decision":"NEUTRAL","justification":"Không đủ tín hiệu"}',
                "BHN",
                lang="vi",
            )
        )

        self.assertEqual(normalized["decision"], "SHORT")
        self.assertEqual(normalized["decision_source"], "fallback_conservative")
        self.assertEqual(normalized["fallback_reason"], "NO_BINARY_DECISION")

    def test_malformed_json_recovers_explicit_long_from_text(self):
        normalized = json.loads(
            _safe_parse_and_enrich(
                'Phân tích bị cắt giữa JSON {"decision": nhưng kết luận cuối cùng: LONG',
                "BHN",
                lang="vi",
            )
        )

        self.assertEqual(normalized["decision"], "LONG")
        self.assertEqual(normalized["decision_source"], "llm_text_recovery")

    def test_decision_node_never_emits_unknown_for_empty_content(self):
        state = {
            "stock_name": "BHN",
            "time_frame": "1 ngày",
            "language": "vi",
            "indicator_report": "indicator",
            "pattern_report": "pattern",
            "trend_report": "trend",
        }

        with patch("builtins.print"):
            result = create_final_trade_decider(_EmptyDecisionLlm())(state)

        decision = json.loads(result["final_trade_decision"])
        self.assertEqual(decision["decision"], "SHORT")
        self.assertEqual(decision["decision_source"], "fallback_conservative")

    def test_alpha_selection_target_matches_net_open_to_close_label(self):
        frame = pd.DataFrame(
            {
                "Open": [100.0, 110.0, 120.0, 130.0, 140.0],
                "Close": [100.0, 111.0, 121.0, 132.0, 141.0],
            }
        )

        target = build_forward_execution_returns(
            frame,
            lookahead=3,
            fee=0.0025,
            slippage=0.001,
        )

        # Signal tại index 0: mua Open[1], bán Close[3], trừ phí một lần.
        self.assertAlmostEqual(
            target.iloc[0],
            132.0 / 110.0 * (1.0 - 0.001) * (1.0 - 0.0025)
            / ((1.0 + 0.001) * (1.0 + 0.0025)) - 1.0,
            places=12,
        )
        self.assertTrue(pd.isna(target.iloc[-3:]).all())

    def test_twenty_point_benchmark_reserves_600_candles_before_every_decision(self):
        required = required_backtest_rows(
            n_tests=20,
            window_size=45,
            step=3,
            lookahead=3,
        )
        self.assertEqual(required, 660)

        ends = build_walk_forward_end_indices(
            total=required,
            n_tests=20,
            window_size=45,
            step=3,
            lookahead=3,
        )

        self.assertEqual(len(ends), 20)
        self.assertGreaterEqual(min(ends), ALPHA_HISTORY_CANDLES)
        with self.assertRaisesRegex(ValueError, "660"):
            build_walk_forward_end_indices(
                total=required - 1,
                n_tests=20,
                window_size=45,
                step=3,
                lookahead=3,
            )

    def test_backtest_never_silently_falls_back_when_dynamic_selection_fails(self):
        history = _history(600)

        with patch("agents.alpha_agent.select_top_alphas", return_value=[]):
            with self.assertRaisesRegex(RuntimeError, "dynamic alpha"):
                _compute_all_alphas(
                    history.tail(45).to_dict(orient="list"),
                    {},
                    {},
                    symbol="BHN",
                    historical_df=history,
                    is_backtest=True,
                )

    def test_dynamic_alpha_uses_full_history_and_normalizes_before_threshold(self):
        history = _history(650)
        cutoff_row = 619
        cutoff_history = history.iloc[: cutoff_row + 1]
        short_window = cutoff_history.tail(45)
        observed_lengths = []

        def raw_positive_but_bearish_relative(features: pd.DataFrame) -> pd.Series:
            observed_lengths.append(len(features))
            values = np.full(len(features), 10.0)
            values[-1] = 1.0
            return pd.Series(values, index=features.index)

        selected = [
            {
                "alpha_id": "TEST_ALPHA",
                "handler": raw_positive_but_bearish_relative,
                "description": "test",
                "composite_score": 1.0,
                "metrics": {"ic": 0.2, "accuracy": 0.6, "long_acc": 0.9, "sharpe": 1.0},
            }
        ]

        with patch("agents.alpha_agent.select_top_alphas", return_value=selected):
            results, _ = _compute_all_alphas(
                short_window.to_dict(orient="list"),
                {},
                {},
                symbol="FPT",
                historical_df=history,
                as_of_date=str(history["Datetime"].iloc[cutoff_row].date()),
                is_backtest=True,
            )

        self.assertEqual(observed_lengths, [600])
        self.assertLess(results[0]["value"], -0.1)
        self.assertEqual(results[0]["signal"], "GIẢM")

    def test_rank_is_neutral_to_long_only_accuracy(self):
        results = pd.DataFrame(
            [
                {"alpha_id": "A", "ic": 0.2, "accuracy": 0.6, "long_acc": 0.1, "sharpe": 1.0},
                {"alpha_id": "B", "ic": 0.2, "accuracy": 0.6, "long_acc": 0.9, "sharpe": 1.0},
            ]
        )

        ranked = rank_alphas(results)

        self.assertAlmostEqual(ranked.loc[0, "composite"], ranked.loc[1, "composite"])

    def test_volume_survives_loader_normalization_and_backtest_window(self):
        raw = _history(60).rename(columns={"Volume": "volume"})
        normalized = _normalise_columns(raw)
        self.assertIn("Volume", REQUIRED_COLS)
        self.assertIn("Volume", normalized.columns)

        payload, _, _ = BacktestEngine(
            {"use_historical_sentiment": False}
        )._prepare_window(normalized, end_idx=60, window_size=45)

        self.assertEqual(payload["Volume"], normalized["Volume"].tail(45).tolist())

    def test_alpha_distillation_keeps_numbers_but_drops_expert_narrative(self):
        report = (
            "## Alpha\n| # | Value |\n| 1 | -0.4 |\n\n---\n\n"
            "### Nhận định của chuyên gia Alpha\nDòng tiền lớn đang gom hàng.\n\n"
            "**TỔNG HỢP: GIẢM (1 TĂNG / 3 GIẢM / 1 TRUNG TÍNH)**"
        )

        distilled = _distill_report("alpha", report, "vi")

        self.assertIn("| 1 | -0.4 |", distilled)
        self.assertIn("TỔNG HỢP: GIẢM", distilled)
        self.assertNotIn("gom hàng", distilled)

    def test_decision_prompt_contains_evidence_hierarchy_and_conflict_gate(self):
        state = {
            "stock_name": "FPT",
            "time_frame": "1 ngày",
            "language": "vi",
            "indicator_report": "indicator",
            "pattern_report": "pattern",
            "trend_report": "trend",
            "alpha_report": "alpha",
            "sentiment_report": "sentiment",
        }

        with patch("builtins.print"):
            prompt = create_final_trade_decider(_DecisionLlm())(state)["decision_prompt"]

        self.assertIn("THỨ TỰ ƯU TIÊN BẰNG CHỨNG", prompt)
        self.assertIn("Trend và Pattern cùng xác nhận xu hướng giảm", prompt)
        self.assertIn("không được chọn LONG chỉ vì Alpha", prompt)
        self.assertIn("phí môi giới 0,25%", prompt)
        self.assertIn("tín hiệu bán toàn bộ cổ phiếu đang có", prompt)


if __name__ == "__main__":
    unittest.main()
