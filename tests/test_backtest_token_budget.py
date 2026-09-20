"""Kiểm thử ngân sách token đầu vào cho benchmark 20 điểm."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.alpha_agent import create_alpha_agent
from agents.decision_agent import create_final_trade_decider
from agents.indicator_agent import create_indicator_agent


class _CountingLlm:
    def __init__(self):
        self.calls = 0

    def invoke(self, _messages):
        self.calls += 1
        return SimpleNamespace(
            content=(
                '{"decision":"LONG","forecast_horizon":"T+2.5",'
                '"confidence":"Trung bình","risk_reward_ratio":1.5,'
                '"evidence_for":"Xu hướng và động lượng đồng thuận.",'
                '"evidence_against":"Biến động còn cao.",'
                '"justification":"Xác suất tăng ròng cao hơn."}'
            )
        )


class BacktestTokenBudgetTests(unittest.TestCase):
    def test_backtest_decision_prompt_has_hard_character_budget(self):
        llm = _CountingLlm()
        state = {
            "stock_name": "BHN",
            "time_frame": "1 ngày",
            "language": "vi",
            "is_backtest": True,
            "indicator_report": "INDICATOR " * 1000,
            "pattern_report": "PATTERN " * 1000,
            "trend_report": "TREND " * 1000,
            "alpha_report": "ALPHA " * 1000,
            "sentiment_report": "SENTIMENT " * 1000,
        }

        with patch("builtins.print"):
            result = create_final_trade_decider(llm)(state)

        prompt = result["decision_prompt"]
        self.assertLessEqual(len(prompt), 7_500)
        self.assertIn("LONG", prompt)
        self.assertIn("SHORT", prompt)
        self.assertIn("Trend và Pattern cùng xác nhận xu hướng giảm", prompt)
        self.assertIn("ALPHA FACTORS ĐỊNH LƯỢNG", prompt)
        self.assertEqual(llm.calls, 1)

    def test_backtest_indicator_uses_deterministic_python_report_without_llm(self):
        llm = _CountingLlm()
        summary = {
            "n_tang": 3,
            "n_giam": 2,
            "n_trung": 0,
            "total": 5,
            "consensus": "TĂNG",
            "confidence": "CAO",
        }
        with (
            patch("agents.indicator_agent._compute_all_indicators", return_value={}),
            patch(
                "agents.indicator_agent._classify_signals",
                return_value={"__summary__": summary},
            ),
            patch("agents.indicator_agent._render_indicator_table", return_value="TABLE"),
            patch(
                "agents.indicator_agent._render_classification_block",
                return_value="SUMMARY",
            ),
            patch("builtins.print"),
        ):
            result = create_indicator_agent(llm, object())(
                {
                    "kline_data": {},
                    "time_frame": "1 ngày",
                    "language": "vi",
                    "is_backtest": True,
                    "messages": [],
                }
            )

        self.assertEqual(llm.calls, 0)
        self.assertEqual(result["indicator_report"], "TABLE\n\n---\n\nSUMMARY")

    def test_backtest_alpha_does_not_generate_discarded_narrative(self):
        llm = _CountingLlm()
        alphas = [
            {"id": index, "signal": "TĂNG" if index <= 3 else "GIẢM"}
            for index in range(1, 6)
        ]
        with (
            patch(
                "agents.alpha_agent._compute_all_alphas",
                return_value=(alphas, {}),
            ),
            patch("agents.alpha_agent._build_alpha_report", return_value="ALPHA TABLE"),
            patch("agents.alpha_agent._llm_reason") as reason,
            patch("builtins.print"),
        ):
            result = create_alpha_agent(
                llm,
                enable_alpha_factors=True,
                enable_sentiment=False,
            )(
                {
                    "stock_name": "BHN",
                    "time_frame": "1 ngày",
                    "kline_data": {},
                    "is_backtest": True,
                    "language": "vi",
                    "messages": [],
                }
            )

        reason.assert_not_called()
        self.assertEqual(llm.calls, 0)
        self.assertIn("ALPHA TABLE", result["alpha_report"])
        self.assertIn("TỔNG HỢP", result["alpha_report"])


if __name__ == "__main__":
    unittest.main()
