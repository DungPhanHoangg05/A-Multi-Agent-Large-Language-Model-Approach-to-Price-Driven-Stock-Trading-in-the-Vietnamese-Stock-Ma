"""Kiểm thử giao thức paired shared reports của backtest."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.backtest_engine import BacktestEngine


class _FakeGraph:
    def __init__(self, invoke_fn):
        self._invoke_fn = invoke_fn

    def invoke(self, state: dict) -> dict:
        return self._invoke_fn(state)


class PairedProtocolTests(unittest.TestCase):
    def test_backtest_reasoning_models_hide_reasoning_and_set_token_limits(self):
        engine = BacktestEngine(
            {
                "groq_api_key": "gsk_test",
                "agent_llm_model": "openai/gpt-oss-20b",
                "graph_llm_model": "qwen/qwen3.8-27b",
                "agent_llm_max_tokens": 2048,
                "graph_llm_max_tokens": 1024,
            }
        )
        builder = Mock()
        builder.compile_upstream.return_value = object()
        builder.compile_decision.side_effect = [object(), object(), object(), object()]

        with (
            patch("langchain_groq.ChatGroq") as chat_groq,
            patch("utils.graph_setup.SetGraph", return_value=builder),
            patch("builtins.print"),
        ):
            engine._init_graphs()

        self.assertEqual(chat_groq.call_count, 2)
        agent_kwargs = chat_groq.call_args_list[0].kwargs
        graph_kwargs = chat_groq.call_args_list[1].kwargs
        self.assertEqual(agent_kwargs["reasoning_format"], "hidden")
        self.assertEqual(agent_kwargs["max_tokens"], 2048)
        self.assertEqual(graph_kwargs["reasoning_format"], "hidden")
        self.assertEqual(graph_kwargs["max_tokens"], 1024)

    def test_empty_final_state_is_rejected(self):
        engine = BacktestEngine({"use_historical_sentiment": False})

        with self.assertRaisesRegex(ValueError, "LONG/SHORT"):
            engine._parse_prediction({})

    def test_one_decision_variant_failure_aborts_paired_point(self):
        engine = BacktestEngine({"use_historical_sentiment": False})
        engine.DELAY_BETWEEN_VARIANTS = 0.0
        engine._graph_upstream = _FakeGraph(
            lambda state: {
                **state,
                "indicator_report": "indicator",
                "pattern_report": "pattern",
                "trend_report": "trend",
            }
        )
        engine._graph_decision_full = _FakeGraph(
            lambda state: {
                **state,
                "final_trade_decision": json.dumps({"decision": "LONG"}),
            }
        )
        engine._graph_decision_no_alpha = _FakeGraph(
            lambda _state: (_ for _ in ()).throw(RuntimeError("temporary LLM error"))
        )

        with (
            patch("utils.static_util.generate_kline_image", return_value={}),
            patch("utils.static_util.generate_trend_image", return_value={}),
            patch("builtins.print"),
        ):
            with self.assertRaisesRegex(RuntimeError, "temporary LLM error"):
                engine._run_paired_point(
                    {"Datetime": [], "Open": [], "High": [], "Low": [], "Close": []},
                    "BHN",
                    "1 ngày",
                )

    def test_generic_paired_failure_aborts_instead_of_saving_unknown(self):
        engine = BacktestEngine({"use_historical_sentiment": False})
        engine._graph_upstream = object()
        engine._run_paired_point = Mock(side_effect=RuntimeError("upstream unavailable"))
        engine._save = Mock()
        engine._draw_backtest_result = Mock()

        with patch("builtins.print"):
            with self.assertRaisesRegex(RuntimeError, "upstream unavailable"):
                engine.run(
                    self._benchmark_frame(),
                    "BHN",
                    timeframe="1 ngày",
                    n_tests=1,
                    window_size=45,
                    step=3,
                    result_path="unused.json",
                )

        engine._save.assert_not_called()

    @staticmethod
    def _benchmark_frame(periods: int = 603) -> pd.DataFrame:
        dates = pd.date_range("2022-01-03", periods=periods, freq="B")
        return pd.DataFrame(
            {
                "Datetime": dates,
                "Open": range(periods),
                "High": range(1, periods + 1),
                "Low": range(periods),
                "Close": range(1, periods + 1),
                "Volume": range(1_000_000, 1_000_000 + periods),
            }
        )

    def test_run_invokes_one_paired_execution_per_test_point(self):
        df = self._benchmark_frame()
        full_state = {"final_trade_decision": json.dumps({"decision": "LONG"})}
        no_alpha_state = {"final_trade_decision": json.dumps({"decision": "SHORT"})}
        paired_run = Mock(return_value=(full_state, 1.0, no_alpha_state, 0.5))

        engine = BacktestEngine({"use_historical_sentiment": False})
        engine._graph_upstream = object()
        engine._run_paired_point = paired_run
        engine._save = Mock()
        engine._draw_backtest_result = Mock()

        with patch("builtins.print"):
            summary = engine.run(
                df,
                "FPT",
                timeframe="1 ngày",
                n_tests=1,
                window_size=45,
                step=3,
                result_path="unused.json",
            )

        paired_run.assert_called_once()
        self.assertEqual(summary.test_points[0]["pred_full"], "LONG")
        self.assertEqual(summary.test_points[0]["pred_no_alpha"], "SHORT")
        self.assertEqual(summary.test_points[0]["decision_source_full"], "llm_json")
        self.assertEqual(summary.test_points[0]["decision_source_no_alpha"], "llm_json")

    def test_dynamic_alpha_failure_aborts_benchmark_immediately(self):
        engine = BacktestEngine({"use_historical_sentiment": False})
        engine._graph_upstream = object()
        engine._run_paired_point = Mock(
            side_effect=RuntimeError("Backtest không tuyển chọn được dynamic alpha")
        )
        engine._save = Mock()
        engine._draw_backtest_result = Mock()

        with patch("builtins.print"):
            with self.assertRaisesRegex(RuntimeError, "dynamic alpha"):
                engine.run(
                    self._benchmark_frame(),
                    "BHN",
                    timeframe="1 ngày",
                    n_tests=1,
                    window_size=45,
                    step=3,
                    result_path="unused.json",
                )

        engine._run_paired_point.assert_called_once()

    def test_split_graphs_execute_expected_nodes_and_preserve_control_fields(self):
        from utils.graph_setup import SetGraph

        calls = []

        def factory(name: str, output: dict):
            def make_node(*_args):
                def node(_state: dict) -> dict:
                    calls.append(name)
                    return output

                return node

            return make_node

        with (
            patch("utils.graph_setup.create_indicator_agent", factory("indicator", {"indicator_report": "i"})),
            patch("utils.graph_setup.create_pattern_agent", factory("pattern", {"pattern_report": "p"})),
            patch("utils.graph_setup.create_trend_agent", factory("trend", {"trend_report": "t"})),
            patch("utils.graph_setup.create_alpha_agent", factory("alpha", {"alpha_report": "a"})),
            patch(
                "utils.graph_setup.create_final_trade_decider",
                factory("decision", {"final_trade_decision": json.dumps({"decision": "LONG"})}),
            ),
            patch("builtins.print"),
        ):
            builder = SetGraph(object(), object(), object())
            upstream = builder.compile_upstream()
            full = builder.compile_decision(include_alpha=True)
            no_alpha = builder.compile_decision(include_alpha=False)

            shared = upstream.invoke(
                {
                    "stock_name": "FPT",
                    "messages": [],
                    "sentiment_store": "historical-store",
                    "window_end_date": "2024-04-22",
                }
            )
            full_state = full.invoke(
                {
                    **shared,
                    "alpha_norm_method": "rank",
                    "alpha_weights": {"ic": 1.0},
                }
            )
            no_alpha_state = no_alpha.invoke(shared)

        self.assertEqual(calls, ["indicator", "pattern", "trend", "alpha", "decision", "decision"])
        self.assertEqual(full_state["alpha_report"], "a")
        self.assertEqual(full_state["alpha_norm_method"], "rank")
        self.assertEqual(full_state["sentiment_store"], "historical-store")
        self.assertNotIn("alpha_report", no_alpha_state)

    def test_no_alpha_predictions_are_invariant_across_three_alpha_configs(self):
        upstream_calls = 0
        no_alpha_inputs = []
        predictions = []

        dates = pd.date_range("2024-01-02", periods=80, freq="B")
        history = pd.DataFrame(
            {
                "Datetime": dates,
                "Open": range(80),
                "High": range(1, 81),
                "Low": range(80),
                "Close": range(1, 81),
            }
        )
        ohlcv = {
            "Datetime": [str(value) for value in dates[-45:]],
            "Open": list(range(45)),
            "High": list(range(1, 46)),
            "Low": list(range(45)),
            "Close": list(range(1, 46)),
        }

        def run_upstream(state: dict) -> dict:
            nonlocal upstream_calls
            upstream_calls += 1
            return {
                **state,
                "indicator_report": "indicator-snapshot",
                "pattern_report": "pattern-snapshot",
                "trend_report": "trend-snapshot",
                "shared_payload": {"values": [1]},
            }

        def run_full(state: dict) -> dict:
            # Nếu không deepcopy, đột biến này sẽ làm bẩn nhánh No-Alpha.
            state["shared_payload"]["values"].append(999)
            norm = state["alpha_norm_method"]
            decision = "LONG" if norm == "zscore_tanh" else "SHORT"
            return {**state, "final_trade_decision": json.dumps({"decision": decision})}

        def run_no_alpha(state: dict) -> dict:
            no_alpha_inputs.append(state)
            reports = (
                state["indicator_report"],
                state["pattern_report"],
                state["trend_report"],
            )
            decision = "LONG" if reports == (
                "indicator-snapshot",
                "pattern-snapshot",
                "trend-snapshot",
            ) else "SHORT"
            return {**state, "final_trade_decision": json.dumps({"decision": decision})}

        for norm_method in ("zscore_tanh", "minmax", "rank"):
            engine = BacktestEngine(
                {
                    "use_historical_sentiment": False,
                    "alpha_norm_method": norm_method,
                    "alpha_weights": {"ic": 1.0},
                }
            )
            engine.DELAY_BETWEEN_VARIANTS = 0.0
            engine._graph_upstream = _FakeGraph(run_upstream)
            engine._graph_decision_full = _FakeGraph(run_full)
            engine._graph_decision_no_alpha = _FakeGraph(run_no_alpha)

            with (
                patch("utils.static_util.generate_kline_image", return_value={}),
                patch("utils.static_util.generate_trend_image", return_value={}),
                patch("builtins.print"),
            ):
                _, _, no_alpha_state, _ = engine._run_paired_point(
                    ohlcv,
                    "FPT",
                    "1 ngày",
                    window_end_date="2024-04-22",
                    point_in_time_df=history,
                )

            prediction, _, _, _, _ = engine._parse_prediction(no_alpha_state)
            predictions.append(prediction)

        self.assertEqual(predictions, ["LONG", "LONG", "LONG"])
        self.assertEqual(upstream_calls, 3, "Upstream phải chỉ chạy một lần mỗi test point")
        self.assertEqual(
            [state["shared_payload"]["values"] for state in no_alpha_inputs],
            [[1], [1], [1]],
            "Hai nhánh phải nhận deep-copy độc lập của snapshot upstream",
        )
        for state in no_alpha_inputs:
            self.assertNotIn("alpha_norm_method", state)
            self.assertNotIn("alpha_weights", state)
            self.assertNotIn("alpha_report", state)

        print(f"[PASS] No-Alpha predictions invariant: {predictions}")
        print(f"[PASS] Upstream invocations: {upstream_calls} (one per test point)")


if __name__ == "__main__":
    unittest.main()
