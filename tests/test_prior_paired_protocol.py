"""Kiểm năm Decision dùng chung Full trên engine/graph/adapter thật, không gọi API."""

from contextlib import ExitStack
from copy import deepcopy
import json
import unittest
from unittest.mock import Mock, patch

from agents.alpha_agent import create_alpha_agent
from core.backtest_engine import BacktestEngine, PRIOR_BRANCH_MODES
from core.bayesian_retriever import format_compact_prior_prefix
from core.historical_signals import FrozenSentimentSnapshot, digest
from prior_context_test_support import ContextFixture
from test_backtest_token_budget import _CountingLlm, _StructuredCountingLlm
from utils.graph_setup import SetGraph


class PriorPairedProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch("builtins.print"))
        self.stack.enter_context(patch("core.regime_detector.MarketRegimeDetector.fit", side_effect=AssertionError("Cấm fit")))
        self.stack.enter_context(patch("data_manager.sentiment_cache.SentimentCache.preload", side_effect=AssertionError("Cấm crawl")))
        self.fx = ContextFixture()
        self.addCleanup(self.fx.close)
        self.adapter = self.fx.adapter()
        self.point = self.adapter.prepare("FPT", self.fx.cutoff)
        self.events = []
        reports = self.fx.reports(self.point.agent_state()["sentiment_store"])
        for name in ("indicator", "pattern", "trend"):
            def factory(*args, name=name):
                def node(state):
                    self.events.append(name)
                    return {f"{name}_report": reports[f"{name}_report"]}
                return node
            self.stack.enter_context(patch(f"utils.graph_setup.create_{name}_agent", side_effect=factory))

        def alpha_factory(llm, alpha, sentiment, **kwargs):
            self.assertTrue(alpha and sentiment)
            self.assertEqual(kwargs, {"strict_research_mode": True})
            node = create_alpha_agent(llm, alpha, sentiment, **kwargs)
            def run(state):
                self.events.append("full")
                return node(state)
            return run
        self.alpha_factory = self.stack.enter_context(patch("utils.graph_setup.create_alpha_agent", side_effect=alpha_factory))
        self.compute = self.stack.enter_context(patch("agents.alpha_agent._compute_all_alphas",
            side_effect=lambda *args, **kwargs: (deepcopy(self.fx.factors()), {"has_volume": True})))
        self.candle = self.stack.enter_context(patch("utils.static_util.generate_kline_image", return_value={"pattern_image": "image-pit"}))
        self.trend = self.stack.enter_context(patch("utils.static_util.generate_trend_image", return_value={"trend_image": "image-pit"}))
        self.llm = _CountingLlm()
        self.builder = SetGraph(self.llm, object(), object())
        self.engine = BacktestEngine({"use_historical_sentiment": False})
        self.engine.DELAY_BETWEEN_VARIANTS = 0.

    def test_engine_runs_each_upstream_full_and_sentiment_once_five_decisions(self) -> None:
        seen = []
        original = FrozenSentimentSnapshot.get_sentiment_at
        def sentiment(store, *args, **kwargs):
            seen.append(kwargs["cutoff_date"])
            return original(store, *args, **kwargs)
        with (patch.object(FrozenSentimentSnapshot, "get_sentiment_at", sentiment),
              patch.object(self.adapter._retriever, "retrieve", wraps=self.adapter._retriever.retrieve) as retrieve,
              patch("core.bayesian_retriever.format_compact_prior_prefix", wraps=format_compact_prior_prefix) as formatter,
              patch.object(self.engine._stop_event, "wait", return_value=False) as wait):
            result = self.engine.run_prior_point(self.point, graph_builder=self.builder)
        self.assertEqual(self.events, ["indicator", "pattern", "trend", "full"])
        self.assertEqual(seen, [self.fx.cutoff])
        self.compute.assert_called_once()
        self.assertEqual(self.llm.calls, 5)
        self.assertEqual(retrieve.call_count, 5)
        self.assertEqual(formatter.call_count, 5)
        self.assertEqual(wait.call_count, 4)
        self.candle.assert_called_once()
        self.trend.assert_called_once()
        self.assertFalse(self.candle.call_args.kwargs["write_artifacts"])
        self.assertFalse(self.trend.call_args.kwargs["write_artifacts"])
        self.assertEqual(list(result["branches"]), list(PRIOR_BRANCH_MODES))
        report_hash = digest(result["full_bundle"]["reports"])
        signal_hash = digest(result["shared"]["current_signals"])
        stats = []
        for name, branch in result["branches"].items():
            state = branch["state"]
            mode, k = PRIOR_BRANCH_MODES[name]
            self.assertEqual((state["prior_config"]["mode"], state["prior_config"]["k"]), (mode, k))
            self.assertEqual(state["prior_provenance"]["signals"]["reports_sha256"], report_hash)
            self.assertEqual(digest(state["current_signals"]), signal_hash)
            self.assertLess(len(state["decision_prompt"]), 6500)
            self.assertLessEqual(len(state["bayesian_prior_context"]), 600)
            self.assertNotIn("messages", state)
            self.assertNotIn("point_in_time_df", state)
            self.assertNotIn("outcome", state)
            if k:
                stats.append(state["prior_stats"])
            else:
                self.assertIsNone(state["prior_stats"])
                self.assertEqual(state["prior_tasks"], [])
                self.assertEqual(state["bayesian_prior_context"], "")
        self.assertTrue(all(item == stats[0] for item in stats))
        json.dumps(result, allow_nan=False, ensure_ascii=False)

    def test_mutating_one_branch_input_does_not_contaminate_later_branches(self) -> None:
        original = self.builder.compile_report_decision
        captured = []
        def compile(**kwargs):
            graph = original(**kwargs)
            def invoke(state):
                captured.append(deepcopy(state))
                output = graph.invoke(state)
                state["prior_provenance"]["news"]["visible_count"] = 999
                state["current_signals"]["trend"] = "BEARISH"
                state["prior_config"]["k"] = 1
                state["indicator_report"] = "Đột biến nhánh"
                state["messages"] = ["Tin nhắn còn sót"]
                state["bayesian_prior_context"] = "Prefix còn sót"
                return output
            return Mock(invoke=invoke)
        with patch.object(self.builder, "compile_report_decision", side_effect=compile):
            result = self.engine.run_prior_point(self.point, graph_builder=self.builder)
        self.assertTrue(all(state["prior_provenance"]["news"]["visible_count"] == 0 for state in captured))
        self.assertTrue(all("messages" not in state and not state["bayesian_prior_context"] for state in captured))
        baseline = deepcopy(result["branches"]["bayesian"])
        result["branches"]["random"]["state"]["prior_tasks"][0]["outcome"]["result"] = "Đột biến"
        result["shared"]["prior_provenance"]["news"]["visible_count"] = 888
        self.assertEqual(result["branches"]["bayesian"], baseline)
        self.assertEqual(result["full_bundle"]["prior_provenance"]["news"]["visible_count"], 0)
        self.assertEqual(self.point.source_provenance["news"]["visible_count"], 0)

    def test_reversed_order_has_same_reports_signals_ids_stats_prefix_and_decisions(self) -> None:
        forward = self.engine.run_prior_point(self.point, graph_builder=self.builder)
        other = BacktestEngine({"use_historical_sentiment": False})
        other.DELAY_BETWEEN_VARIANTS = 0.
        reverse = other.run_prior_point(self.point, graph_builder=self.builder,
                                       branch_order=tuple(reversed(PRIOR_BRANCH_MODES)))
        for branch in PRIOR_BRANCH_MODES:
            self.assertEqual(forward["branches"][branch]["state"], reverse["branches"][branch]["state"])
        self.assertEqual(forward["shared"], reverse["shared"])

    def test_completed_or_failed_point_cannot_repeat_upstream(self) -> None:
        self.engine.run_prior_point(self.point, graph_builder=self.builder)
        with self.assertRaisesRegex(RuntimeError, "không tự gọi lại"):
            self.engine.run_prior_point(self.adapter.prepare("FPT", self.fx.cutoff), graph_builder=self.builder)
        self.assertEqual(self.llm.calls, 5)
        self.assertEqual(self.events, ["indicator", "pattern", "trend", "full"])

    def test_branch_llm_failure_aborts_without_fallback_or_repeating_upstream(self) -> None:
        calls = []
        invoke = self.llm.invoke
        def fail(messages):
            calls.append(messages)
            if len(calls) == 2:
                raise RuntimeError("Quota fixture đã hết")
            return invoke(messages)
        with patch.object(self.llm, "invoke", side_effect=fail), patch("agents.decision_agent._invoke_with_retry", side_effect=lambda fn, *args: fn(*args)):
            with self.assertRaisesRegex(RuntimeError, "Quota fixture"):
                self.engine.run_prior_point(self.point, graph_builder=self.builder)
        self.assertEqual(len(calls), 2)
        with self.assertRaisesRegex(RuntimeError, "không tự gọi lại"):
            self.engine.run_prior_point(self.point, graph_builder=self.builder)
        self.assertEqual(self.events, ["indicator", "pattern", "trend", "full"])
        self.assertTrue(self.engine._prior_point_lock.acquire(blocking=False))
        self.engine._prior_point_lock.release()

    def test_stop_before_point_and_between_branches_prevents_extra_llm_calls(self) -> None:
        self.engine.stop()
        with self.assertRaises(InterruptedError):
            self.engine.run_prior_point(self.point, graph_builder=self.builder)
        self.assertEqual(self.events, [])
        self.engine._stop_event.clear()
        original = self.llm.invoke
        def stop(messages):
            result = original(messages)
            self.engine.stop()
            return result
        with patch.object(self.llm, "invoke", side_effect=stop), self.assertRaises(InterruptedError):
            self.engine.run_prior_point(self.point, graph_builder=self.builder)
        self.assertEqual(self.llm.calls, 1)

    def test_invalid_order_or_matrix_config_fails_before_upstream(self) -> None:
        for order in ((), ("original",) * 5, tuple(PRIOR_BRANCH_MODES)[:-1], list(PRIOR_BRANCH_MODES)):
            with self.subTest(order=order), self.assertRaises(ValueError):
                self.engine.run_prior_point(self.point, graph_builder=self.builder, branch_order=order)
        for key, value in (("seed", 7), ("scope", "pooled")):
            config = deepcopy(self.fx.prior_config)
            config[key] = value
            # Fixture cung cấp config trước khi adapter ghim nguồn.
            before = self.fx.prior_config
            self.fx.prior_config = config
            try:
                point = self.fx.adapter().prepare("FPT", self.fx.cutoff)
                with self.assertRaises(ValueError):
                    self.engine.run_prior_point(point, graph_builder=self.builder)
            finally:
                self.fx.prior_config = before
        self.assertEqual(self.events, [])
        self.assertEqual(self.llm.calls, 0)

    def test_strict_full_sentiment_failure_propagates_before_any_decision(self) -> None:
        with patch.object(FrozenSentimentSnapshot, "get_sentiment_at", side_effect=ValueError("Nguồn sentiment hỏng")):
            with self.assertRaisesRegex(ValueError, "Nguồn sentiment hỏng"):
                self.engine.run_prior_point(self.point, graph_builder=self.builder)
        self.compute.assert_not_called()
        self.assertEqual(self.llm.calls, 0)
        with self.assertRaisesRegex(RuntimeError, "không tự gọi lại"):
            self.engine.run_prior_point(self.point, graph_builder=self.builder)

    def test_chart_or_upstream_failure_stops_before_full_and_decision(self) -> None:
        self.candle.side_effect = ValueError("Ảnh hỏng")
        with self.assertRaisesRegex(ValueError, "Ảnh hỏng"):
            self.engine.run_prior_point(self.point, graph_builder=self.builder)
        self.assertEqual(self.events, [])
        self.alpha_factory.assert_not_called()
        self.assertEqual(self.llm.calls, 0)
        self.candle.side_effect = None
        other = BacktestEngine({"use_historical_sentiment": False})
        with patch.object(self.builder, "compile_upstream", return_value=Mock(invoke=Mock(side_effect=ValueError("Upstream hỏng")))):
            with self.assertRaisesRegex(ValueError, "Upstream hỏng"):
                other.run_prior_point(self.point, graph_builder=self.builder)
        self.alpha_factory.assert_not_called()
        self.assertEqual(self.llm.calls, 0)

    def test_other_engine_call_cannot_run_concurrently(self) -> None:
        self.engine._prior_point_lock.acquire()
        try:
            with self.assertRaisesRegex(RuntimeError, "không chạy song song"):
                self.engine.run_prior_point(self.point, graph_builder=self.builder)
        finally:
            self.engine._prior_point_lock.release()
        self.assertEqual(self.events, [])

    def test_structured_decision_route_and_native_full_bundle(self) -> None:
        llm = _StructuredCountingLlm()
        result = self.engine.run_prior_point(self.point, graph_builder=SetGraph(llm, object(), object()))
        self.assertEqual(len(llm.structured_prompts), 5)
        self.assertEqual(len(result["full_bundle"]["alpha_factors"]), 5)
        self.assertTrue(all(json.loads(item["state"]["final_trade_decision"])["decision_source"] == "llm_structured"
                            for item in result["branches"].values()))
        json.dumps(result, allow_nan=False)

    def test_both_providers_and_languages_run_complete_five_branch_matrix(self) -> None:
        for lang in ("vi", "en"):
            self.fx.config["language"] = lang
            for provider in ("historical_prefix", "fixed_train_oos"):
                options = {} if provider == "historical_prefix" else {
                    "provider_mode": provider, "frozen_artifact_path": "model/fixed.json", "freeze_as_of_date": self.fx.day(620)}
                point = self.fx.adapter(**options).prepare("FPT", self.fx.cutoff)
                engine = BacktestEngine({"language": lang, "use_historical_sentiment": False})
                engine.DELAY_BETWEEN_VARIANTS = 0.
                with self.subTest(provider=provider, language=lang):
                    result = engine.run_prior_point(point, graph_builder=self.builder)
                    self.assertEqual(len(result["branches"]), 5)
                    self.assertEqual(result["shared"]["language"], lang)
                    self.assertEqual(result["shared"]["prior_provenance"]["context"]["provider_mode"], provider)
                    stats = [item["state"]["prior_stats"] for name, item in result["branches"].items() if name != "original"]
                    self.assertTrue(all(stat == stats[0] for stat in stats))
        self.assertEqual(self.llm.calls, 20)


if __name__ == "__main__":
    unittest.main()
