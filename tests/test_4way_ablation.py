"""Kiểm thử bốn biến thể Alpha Factors/Sentiment độc lập."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.alpha_agent import create_alpha_agent
from agents.decision_agent import create_final_trade_decider
from core.backtest_engine import BacktestEngine
from utils.graph_setup import ABLATION_CONFIGS, SetGraph


class _FakeGraph:
    def __init__(self, invoke_fn):
        self._invoke_fn = invoke_fn

    def invoke(self, state: dict) -> dict:
        return self._invoke_fn(state)


class _DecisionLlm:
    def __init__(self):
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return SimpleNamespace(
            content=json.dumps(
                {
                    "decision": "LONG",
                    "confidence": "Cao",
                    "risk_reward_ratio": 2.0,
                    "justification": "test",
                }
            )
        )


class FourWayAblationTests(unittest.TestCase):
    def test_standard_configs_cover_all_four_combinations(self):
        combinations = {
            (
                config["enable_alpha_factors"],
                config["enable_sentiment"],
            )
            for config in ABLATION_CONFIGS.values()
        }

        self.assertEqual(
            set(ABLATION_CONFIGS),
            {"full", "alpha_only", "sentiment_only", "baseline"},
        )
        self.assertEqual(
            combinations,
            {(True, True), (True, False), (False, True), (False, False)},
        )

    def test_four_decision_graphs_emit_only_configured_reports(self):
        calls = []
        decision_inputs = []

        def feature_factory(_llm, enable_alpha_factors=True, enable_sentiment=True):
            def node(state):
                calls.append((enable_alpha_factors, enable_sentiment))
                output = {"messages": state.get("messages", [])}
                if enable_alpha_factors:
                    output["alpha_report"] = "alpha-enabled"
                if enable_sentiment:
                    output["sentiment_report"] = "sentiment-enabled"
                return output

            return node

        def decision_factory(_llm):
            def node(state):
                decision_inputs.append(
                    {
                        "alpha": state.get("alpha_report"),
                        "sentiment": state.get("sentiment_report"),
                    }
                )
                return {
                    "final_trade_decision": json.dumps({"decision": "LONG"}),
                }

            return node

        with (
            patch("utils.graph_setup.create_alpha_agent", feature_factory),
            patch("utils.graph_setup.create_final_trade_decider", decision_factory),
            patch("builtins.print"),
        ):
            builder = SetGraph(object(), object(), object())
            outputs = {
                name: builder.compile_decision(ablation_config=config).invoke(
                    {"messages": []}
                )
                for name, config in ABLATION_CONFIGS.items()
            }

        self.assertEqual(calls, [(True, True), (True, False), (False, True)])
        self.assertEqual(
            decision_inputs,
            [
                {"alpha": "alpha-enabled", "sentiment": "sentiment-enabled"},
                {"alpha": "alpha-enabled", "sentiment": None},
                {"alpha": None, "sentiment": "sentiment-enabled"},
                {"alpha": None, "sentiment": None},
            ],
        )

    def test_full_pipeline_set_graph_accepts_each_ablation_config(self):
        def passthrough_factory(*_args):
            return lambda _state: {}

        def feature_factory(_llm, enable_alpha_factors=True, enable_sentiment=True):
            def node(_state):
                result = {}
                if enable_alpha_factors:
                    result["alpha_report"] = "alpha"
                if enable_sentiment:
                    result["sentiment_report"] = "sentiment"
                return result

            return node

        def decision_factory(_llm):
            return lambda _state: {
                "final_trade_decision": json.dumps({"decision": "LONG"})
            }

        with (
            patch("utils.graph_setup.create_indicator_agent", passthrough_factory),
            patch("utils.graph_setup.create_pattern_agent", passthrough_factory),
            patch("utils.graph_setup.create_trend_agent", passthrough_factory),
            patch("utils.graph_setup.create_alpha_agent", feature_factory),
            patch("utils.graph_setup.create_final_trade_decider", decision_factory),
            patch("builtins.print"),
        ):
            builder = SetGraph(object(), object(), object())
            outputs = {
                name: builder.set_graph(ablation_config=config).invoke({})
                for name, config in ABLATION_CONFIGS.items()
            }

        for name, config in ABLATION_CONFIGS.items():
            self.assertEqual("alpha_report" in outputs[name], config["enable_alpha_factors"])
            self.assertEqual("sentiment_report" in outputs[name], config["enable_sentiment"])

    def test_decision_prompt_includes_alpha_and_sentiment_independently(self):
        cases = {
            "full": (True, True),
            "alpha_only": (True, False),
            "sentiment_only": (False, True),
            "baseline": (False, False),
        }
        for variant, (expect_alpha, expect_sentiment) in cases.items():
            with self.subTest(variant=variant):
                llm = _DecisionLlm()
                state = {
                    "stock_name": "FPT",
                    "time_frame": "1 ngày",
                    "language": "vi",
                    "indicator_report": "indicator",
                    "pattern_report": "pattern",
                    "trend_report": "trend",
                }
                if expect_alpha:
                    state["alpha_report"] = "ALPHA_PAYLOAD"
                if expect_sentiment:
                    state["sentiment_report"] = "SENTIMENT_PAYLOAD"

                with patch("builtins.print"):
                    result = create_final_trade_decider(llm)(state)
                prompt = result["decision_prompt"]

                self.assertEqual("ALPHA_PAYLOAD" in prompt, expect_alpha)
                self.assertEqual("SENTIMENT_PAYLOAD" in prompt, expect_sentiment)
                self.assertEqual("ALPHA FACTORS ĐỊNH LƯỢNG" in prompt, expect_alpha)
                self.assertEqual(
                    "TIN TỨC & TÂM LÝ THỊ TRƯỜNG" in prompt,
                    expect_sentiment,
                )

    def test_english_prompt_keeps_the_two_optional_sections_independent(self):
        for report_key, expected_heading, absent_heading in (
            ("alpha_report", "QUANTITATIVE ALPHA FACTORS", "NEWS & MARKET SENTIMENT"),
            ("sentiment_report", "NEWS & MARKET SENTIMENT", "QUANTITATIVE ALPHA FACTORS"),
        ):
            with self.subTest(report_key=report_key):
                llm = _DecisionLlm()
                state = {
                    "stock_name": "FPT",
                    "time_frame": "1 day",
                    "language": "en",
                    "indicator_report": "indicator",
                    "pattern_report": "pattern",
                    "trend_report": "trend",
                    report_key: "OPTIONAL_PAYLOAD",
                }

                with patch("builtins.print"):
                    prompt = create_final_trade_decider(llm)(state)["decision_prompt"]

                self.assertIn(expected_heading, prompt)
                self.assertNotIn(absent_heading, prompt)

    def test_alpha_only_does_not_read_sentiment(self):
        sentiment_store = Mock()
        state = {
            "stock_name": "FPT",
            "time_frame": "1 ngày",
            "kline_data": {},
            "is_backtest": True,
            "sentiment_store": sentiment_store,
            "window_end_date": "2024-01-31",
            "messages": [],
            "language": "vi",
        }

        with (
            patch("agents.alpha_agent._compute_all_alphas", return_value=([], {})),
            patch("agents.alpha_agent._build_alpha_report", return_value="alpha-only"),
            patch("agents.alpha_agent._llm_reason", return_value="reason"),
            patch("builtins.print"),
        ):
            result = create_alpha_agent(
                object(), enable_alpha_factors=True, enable_sentiment=False
            )(state)

        sentiment_store.get_sentiment_at.assert_not_called()
        self.assertIn("alpha_report", result)
        self.assertNotIn("sentiment_report", result)

    def test_sentiment_only_does_not_compute_alpha_factors(self):
        sentiment_store = Mock()
        sentiment_store.get_sentiment_at.return_value = (
            {"main_sentiment": {"avg_score": 0.5}},
            "sentiment-only",
        )
        state = {
            "stock_name": "FPT",
            "time_frame": "1 ngày",
            "kline_data": {},
            "is_backtest": True,
            "sentiment_store": sentiment_store,
            "window_end_date": "2024-01-31",
            "messages": [],
            "language": "vi",
        }

        with (
            patch("agents.alpha_agent._compute_all_alphas") as compute,
            patch("builtins.print"),
        ):
            result = create_alpha_agent(
                object(), enable_alpha_factors=False, enable_sentiment=True
            )(state)

        compute.assert_not_called()
        sentiment_store.get_sentiment_at.assert_called_once()
        self.assertNotIn("alpha_report", result)
        self.assertEqual(result["sentiment_report"], "sentiment-only")

    def test_engine_runs_four_variants_from_one_upstream_snapshot(self):
        upstream_calls = 0
        variant_inputs = {}

        def upstream(state):
            nonlocal upstream_calls
            upstream_calls += 1
            return {**state, "shared": {"values": [1]}}

        def variant_graph(name):
            def invoke(state):
                variant_inputs[name] = state
                if name == "full":
                    state["shared"]["values"].append(99)
                return {**state, "variant": name}

            return _FakeGraph(invoke)

        engine = BacktestEngine({"use_historical_sentiment": False})
        engine.DELAY_BETWEEN_VARIANTS = 0.0
        engine._graph_upstream = _FakeGraph(upstream)
        engine._graph_decision_variants = {
            name: variant_graph(name) for name in ABLATION_CONFIGS
        }

        with (
            patch("utils.static_util.generate_kline_image", return_value={}),
            patch("utils.static_util.generate_trend_image", return_value={}),
            patch("builtins.print"),
        ):
            results = engine._run_ablation_variants(
                {"Datetime": [], "Open": [], "High": [], "Low": [], "Close": []},
                "FPT",
                "1 ngày",
                variants=tuple(ABLATION_CONFIGS),
            )

        self.assertEqual(upstream_calls, 1)
        self.assertEqual(set(results), set(ABLATION_CONFIGS))
        self.assertEqual(
            [variant_inputs[name]["shared"]["values"] for name in ABLATION_CONFIGS],
            [[1, 99], [1], [1], [1]],
        )


if __name__ == "__main__":
    unittest.main()
