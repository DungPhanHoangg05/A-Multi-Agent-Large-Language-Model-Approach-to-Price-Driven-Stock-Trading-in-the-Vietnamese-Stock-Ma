"""Kiểm ranh giới graph thật với callback nguồn/retriever và LLM fixture offline."""

import asyncio
from contextlib import ExitStack
from copy import deepcopy
import unittest
from unittest.mock import Mock, patch

from agents import decision_agent
from core.bayesian_retriever import format_compact_prior_prefix
from core.prior_config import PRIOR_STATE_FIELDS
from test_backtest_token_budget import _CountingLlm, _StructuredCountingLlm, _budget_state
from test_decision_prior_integration import prior_fixture
from utils.graph_setup import ABLATION_CONFIGS, SetGraph


def graph_input(expected: dict) -> dict:
    """Input trước truy xuất; không nhập lại result/prefix từ nhánh khác."""
    state = deepcopy(expected)
    state.update(prior_tasks=[], prior_stats=None, prior_metadata=None, bayesian_prior_context="")
    return state


def graph_hooks(expected: dict, events: list[str]) -> tuple[Mock, Mock]:
    """Hai lượt verifier là probe fixture, không xác minh giá/model thật."""
    def verify(state: dict) -> None:
        events.append("verify_context" if state["prior_metadata"] is None else "verify_result")
        for field in ("market_regime", "current_signals", "prior_provenance", "prior_config",
                      "stock_name", "as_of_date", "indicator_report", "pattern_report",
                      "trend_report", "alpha_report", "sentiment_report"):
            if state[field] != expected[field]:
                raise ValueError(f"Context khác fixture: {field}")
        if state["bayesian_prior_context"] != "":
            raise ValueError("Verifier phải chạy trước formatter")
        if state["prior_metadata"] is not None:
            for field in ("prior_tasks", "prior_stats", "prior_metadata"):
                if state[field] != expected[field]:
                    raise ValueError(f"Result khác fixture: {field}")

    def retrieve(state: dict) -> dict:
        events.append("retrieve")
        if state["prior_tasks"] or state["prior_stats"] is not None or state["prior_metadata"] is not None:
            raise ValueError("Retriever nhận result còn sót")
        return {key: deepcopy(expected[f"prior_{key}"]) for key in ("tasks", "stats", "metadata")}

    return Mock(side_effect=retrieve), Mock(side_effect=verify)


class PriorGraphIntegrationTests(unittest.TestCase):
    def test_real_graph_matrix_retains_prior_and_formats_once_before_decision(self):
        for lang in ("vi", "en"):
            for timeframe in ("1d", "1 ngày"):
                for mode in ("bayesian_regime", "random", "recent", "similarity"):
                    for k in range(4):
                        for structured in (False, True):
                            with self.subTest(lang=lang, timeframe=timeframe, mode=mode, k=k, structured=structured):
                                expected = prior_fixture(lang=lang, mode=mode, k=k)
                                state = graph_input(expected)
                                state["time_frame"] = timeframe
                                before = deepcopy(state)
                                events = []
                                retrieve, verify = graph_hooks(expected, events)
                                llm = _StructuredCountingLlm() if structured else _CountingLlm()
                                def format_once(*args):
                                    events.append("format")
                                    return format_compact_prior_prefix(*args)
                                with (patch("builtins.print"),
                                      patch("utils.graph_setup.create_alpha_agent") as alpha,
                                      patch("core.bayesian_retriever.format_compact_prior_prefix", side_effect=format_once) as formatter,
                                      patch.object(decision_agent, "_invoke_with_retry",
                                                   wraps=decision_agent._invoke_with_retry) as invoke):
                                    graph = SetGraph(llm, object(), object()).compile_report_decision(
                                        prior_config=expected["prior_config"], prior_retriever=retrieve,
                                        prior_source_validator=verify)
                                    self.assertTrue(set(PRIOR_STATE_FIELDS).issubset(graph.channels))
                                    self.assertEqual(set(graph.get_graph().nodes), {"__start__", "__end__", "Prior Preparation", "Decision Maker"})
                                    result = graph.invoke(state)
                                self.assertEqual(events, ["verify_context", "retrieve", "verify_result", "format"])
                                retrieve.assert_called_once()
                                self.assertEqual(verify.call_count, 2)
                                formatter.assert_called_once()
                                invoke.assert_called_once()
                                alpha.assert_not_called()
                                self.assertEqual(state, before)
                                self.assertEqual(result["time_frame"], "1d")
                                for field in PRIOR_STATE_FIELDS:
                                    self.assertEqual(result[field], expected[field])
                                for name in ("indicator", "pattern", "trend", "alpha", "sentiment"):
                                    self.assertEqual(result[f"{name}_report"], state[f"{name}_report"])
                                prompt = result["decision_prompt"]
                                self.assertEqual(prompt.count("[BRPP v1]"), int(k > 0))
                                self.assertLess(len(prompt), 6500)
                                self.assertEqual(llm.structured_prompts if structured else llm.prompts, [prompt])

    def test_shared_full_runs_upstream_and_alpha_once_for_five_branches(self):
        reports = _budget_state()
        calls = []
        def factory(name: str):
            def make(*args):
                def node(state):
                    calls.append(name)
                    return {f"{name}_report": reports[f"{name}_report"]}
                return node
            return make
        def alpha_factory(_llm, alpha, sentiment):
            self.assertTrue(alpha and sentiment)
            def node(state):
                self.assertTrue(all(f"{name}_report" in state for name in ("indicator", "pattern", "trend")))
                calls.append("alpha_sentiment")
                return {field: reports[field] for field in ("alpha_report", "sentiment_report")}
            return node
        with ExitStack() as stack:
            stack.enter_context(patch("builtins.print"))
            for name in ("indicator", "pattern", "trend"):
                stack.enter_context(patch(f"utils.graph_setup.create_{name}_agent", factory(name)))
            stack.enter_context(patch("utils.graph_setup.create_alpha_agent", alpha_factory))
            llm = _CountingLlm()
            builder = SetGraph(llm, object(), object())
            base = {key: value for key, value in reports.items() if not key.endswith("_report")}
            upstream = builder.compile_upstream().invoke(base)
            full_graph = builder.compile_full_preparation()
            self.assertEqual(set(full_graph.get_graph().nodes), {"__start__", "__end__", "Full Preparation"})
            full = full_graph.invoke(upstream)
            before = deepcopy(full)
            results = []
            for mode, k in (("bayesian_regime", 0), ("random", 3), ("recent", 3), ("similarity", 3), ("bayesian_regime", 3)):
                expected = prior_fixture(mode=mode, k=k)
                state = {**deepcopy(full), **{key: value for key, value in graph_input(expected).items()
                                             if key in PRIOR_STATE_FIELDS or key == "as_of_date"}}
                retrieve, verify = graph_hooks(expected, [])
                graph = builder.compile_report_decision(prior_config=expected["prior_config"],
                    prior_retriever=retrieve, prior_source_validator=verify)
                results.append(graph.invoke(state))
            self.assertEqual(calls, ["indicator", "pattern", "trend", "alpha_sentiment"])
            self.assertEqual(llm.calls, 5)
            self.assertEqual(full, before)
            results[-1]["prior_tasks"][0]["episode_id"] = "foreign"
            self.assertNotEqual(results[-1]["prior_tasks"], results[-2]["prior_tasks"])

    def test_four_legacy_ablations_and_include_alpha_keep_order(self):
        for combined in (False, True):
            for name, config in ABLATION_CONFIGS.items():
                calls = []
                def factory(label: str):
                    def make(*args):
                        def node(state):
                            calls.append(label)
                            return {f"{label}_report": label}
                        return node
                    return make
                def alpha_factory(_llm, alpha, sentiment):
                    self.assertEqual((alpha, sentiment), tuple(config.values()))
                    def node(state):
                        calls.append("alpha")
                        return {"alpha_report": "alpha" if alpha else "No data.",
                                "sentiment_report": "sentiment" if sentiment else "No data."}
                    return node
                def decide(_llm):
                    def node(state):
                        calls.append("decision")
                        return {"final_trade_decision": "LONG"}
                    return node
                with ExitStack() as stack:
                    stack.enter_context(patch("builtins.print"))
                    for node in ("indicator", "pattern", "trend"):
                        stack.enter_context(patch(f"utils.graph_setup.create_{node}_agent", factory(node)))
                    stack.enter_context(patch("utils.graph_setup.create_alpha_agent", alpha_factory))
                    stack.enter_context(patch("utils.graph_setup.create_final_trade_decider", decide))
                    builder = SetGraph(object(), object(), object())
                    graph = builder.set_graph(ablation_config=config) if combined else builder.compile_decision(ablation_config=config)
                    self.assertEqual(graph.invoke(_budget_state())["final_trade_decision"], "LONG")
                    expected = ["indicator"] if combined else []
                    if any(config.values()):
                        expected.append("alpha")
                    if combined:
                        expected.extend(["pattern", "trend"])
                    self.assertEqual(calls, expected + ["decision"])
                    if name in ("full", "baseline"):
                        calls.clear()
                        old = builder.set_graph(include_alpha=name == "full") if combined else builder.compile_decision(include_alpha=name == "full")
                        old.invoke(_budget_state())
                        self.assertEqual(calls, expected + ["decision"])

    def test_raw_input_invalid_config_alias_outcome_and_missing_reports_fail_before_hooks(self):
        expected = prior_fixture()
        base = graph_input(expected)
        cases = [{**base, "is_backtest": False}, {**base, "time_frame": "1 day"},
                 {**base, "prior_config": {"enable_bayesian_prior": True, "k": True}},
                 {**base, "ablation_config": ABLATION_CONFIGS["baseline"]},
                 {**base, "outcome": {"result": "WIN"}}, {**base, "current_regime": "BULL"},
                 {**base, "verified": True}, {**base, "bayesian_prior_context": expected["bayesian_prior_context"]},
                 {**base, "prior_tasks": expected["prior_tasks"]}, {**base, "prior_stats": {}},
                 {**base, "prior_metadata": {}}, {**base, "alpha_report": " No data. "}]
        for field in ("market_regime", "current_signals", "prior_provenance", "indicator_report"):
            state = deepcopy(base)
            state.pop(field)
            cases.append(state)
        for state in cases:
            llm, retrieve, verify = _CountingLlm(), Mock(), Mock()
            with self.subTest(keys=list(state)), patch("builtins.print"):
                graph = SetGraph(llm, object(), object()).compile_report_decision(
                    prior_config=expected["prior_config"], prior_retriever=retrieve, prior_source_validator=verify)
                with self.assertRaises(ValueError):
                    graph.invoke(state)
            retrieve.assert_not_called()
            verify.assert_not_called()
            self.assertEqual(llm.calls, 0)

    def test_missing_hooks_or_hooks_when_disabled_fail_before_factories(self):
        with patch("utils.graph_setup.create_final_trade_decider") as factory:
            builder = SetGraph(object(), object(), object())
            for kwargs in ({"prior_config": {"enable_bayesian_prior": True}},
                           {"prior_config": {"enable_bayesian_prior": True}, "prior_retriever": Mock()},
                           {"prior_retriever": Mock()}, {"prior_source_validator": Mock()},
                           {"prior_config": {"enable_bayesian_prior": "true"}}):
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                    builder.compile_report_decision(**kwargs)
            factory.assert_not_called()

    def test_source_failures_before_query_and_after_result_call_no_formatter_or_api(self):
        for k in (0, 3):
            for fail_at in (1, 2):
                expected = prior_fixture(k=k)
                retrieve, verify = graph_hooks(expected, [])
                verify.side_effect = ([ValueError("Nguồn lỗi")] if fail_at == 1 else [None, ValueError("Nguồn lỗi")])
                llm = _CountingLlm()
                with patch("core.bayesian_retriever.format_compact_prior_prefix") as formatter:
                    graph = SetGraph(llm, object(), object()).compile_report_decision(
                        prior_config=expected["prior_config"], prior_retriever=retrieve, prior_source_validator=verify)
                    with self.assertRaisesRegex(ValueError, "Nguồn lỗi"):
                        graph.invoke(graph_input(expected))
                self.assertEqual(retrieve.call_count, fail_at - 1)
                formatter.assert_not_called()
                self.assertEqual(llm.calls, 0)

    def test_invalid_retriever_result_cutoff_and_errors_propagate(self):
        expected = prior_fixture()
        valid = {key: expected[f"prior_{key}"] for key in ("tasks", "stats", "metadata")}
        future = deepcopy(valid)
        future["tasks"][0]["exit_date"] = expected["as_of_date"]
        for result in (None, {}, {**valid, "prefix": "foreign"}, future):
            llm = _CountingLlm()
            graph = SetGraph(llm, object(), object()).compile_report_decision(
                prior_config=expected["prior_config"], prior_retriever=Mock(return_value=result),
                prior_source_validator=lambda _: None)
            with self.subTest(result=result), self.assertRaises(ValueError):
                graph.invoke(graph_input(expected))
            self.assertEqual(llm.calls, 0)
        retrieve = Mock(side_effect=RuntimeError("Truy xuất lỗi"))
        graph = SetGraph(_CountingLlm(), object(), object()).compile_report_decision(
            prior_config=expected["prior_config"], prior_retriever=retrieve, prior_source_validator=lambda _: None)
        with self.assertRaisesRegex(RuntimeError, "Truy xuất lỗi"):
            graph.invoke(graph_input(expected))

    def test_callbacks_cannot_mutate_context_reports_or_owned_result(self):
        expected = prior_fixture()
        state = graph_input(expected)
        before = deepcopy(state)
        returned = {key: deepcopy(expected[f"prior_{key}"]) for key in ("tasks", "stats", "metadata")}
        def mutate_verify(projection):
            projection["prior_provenance"]["context"]["symbol"] = "foreign"
            projection["indicator_report"] = "foreign"
        def mutate_retrieve(projection):
            projection["market_regime"]["regime_name"] = "foreign"
            return returned
        with patch("builtins.print"):
            graph = SetGraph(_CountingLlm(), object(), object()).compile_report_decision(
                prior_config=expected["prior_config"], prior_retriever=mutate_retrieve,
                prior_source_validator=mutate_verify)
            result = graph.invoke(state)
        self.assertEqual(state, before)
        self.assertEqual(result["prior_provenance"], expected["prior_provenance"])
        result["prior_tasks"][0]["episode_id"] = "foreign"
        self.assertEqual(returned["tasks"], expected["prior_tasks"])

    def test_disabled_shared_report_graph_matches_original_without_prior_io(self):
        enabled = prior_fixture(k=0)
        retrieve, verify = graph_hooks(enabled, [])
        off = {key: value for key, value in enabled.items() if key not in PRIOR_STATE_FIELDS}
        llm = _CountingLlm()
        builder = SetGraph(llm, object(), object())
        with (patch("builtins.print"), patch("core.bayesian_retriever.format_compact_prior_prefix",
                                          wraps=format_compact_prior_prefix) as formatter):
            off_graph = builder.compile_report_decision()
            disabled = off_graph.invoke(off)
            formatter.assert_not_called()
            self.assertEqual(set(off_graph.get_graph().nodes), {"__start__", "__end__", "Decision Maker"})
            original = builder.compile_report_decision(prior_config=enabled["prior_config"],
                prior_retriever=retrieve, prior_source_validator=verify).invoke(graph_input(enabled))
        self.assertEqual(disabled["decision_prompt"], original["decision_prompt"])
        self.assertNotIn("prior_metadata", disabled)
        self.assertEqual(original["prior_metadata"]["reason"], "k_zero")

    def test_full_boundary_invalid_input_stops_before_alpha(self):
        node = Mock(return_value={})
        with patch("utils.graph_setup.create_alpha_agent", return_value=node):
            graph = SetGraph(object(), object(), object()).compile_full_preparation()
            for state in ({}, {**_budget_state(), "is_backtest": False},
                          {**_budget_state(), "trend_report": ""},
                          {**_budget_state(), "prior_config": {"enable_bayesian_prior": True}},
                          {**_budget_state(), "ablation_config": ABLATION_CONFIGS["alpha_only"]},
                          {**_budget_state(), "bayesian_prior_context": "stale"}):
                with self.subTest(state=state), self.assertRaises(ValueError):
                    graph.invoke(state)
        node.assert_not_called()

    def test_empty_partial_and_config_binding_have_independent_outputs(self):
        for selected in (0, 1, 2):
            expected = prior_fixture(selected=selected)
            config = deepcopy(expected["prior_config"])
            retrieve, verify = graph_hooks(expected, [])
            builder = SetGraph(_CountingLlm(), object(), object())
            graph = builder.compile_report_decision(prior_config=config, prior_retriever=retrieve,
                                                   prior_source_validator=verify)
            config["k"] = 0
            state = graph_input(expected)
            state.pop("prior_config")
            with patch("builtins.print"):
                first = graph.invoke(state)
                second = graph.invoke(state)
            self.assertEqual(first["prior_metadata"], expected["prior_metadata"])
            first["prior_metadata"]["selected_ids"].append("foreign")
            self.assertEqual(second["prior_metadata"], expected["prior_metadata"])

    def test_async_invoke_and_stream_run_same_guarded_graph(self):
        expected = prior_fixture()
        retrieve, verify = graph_hooks(expected, [])
        with patch("builtins.print"):
            graph = SetGraph(_CountingLlm(), object(), object()).compile_report_decision(
                prior_config=expected["prior_config"], prior_retriever=retrieve, prior_source_validator=verify)
            result = asyncio.run(graph.ainvoke(graph_input(expected)))
            updates = list(graph.stream(graph_input(expected), stream_mode="updates"))
            async def collect():
                return [chunk async for chunk in graph.astream(graph_input(expected), stream_mode="updates")]
            async_updates = asyncio.run(collect())
        self.assertEqual(result["prior_metadata"], expected["prior_metadata"])
        self.assertEqual([next(iter(update)) for update in updates], ["Prior Preparation", "Decision Maker"])
        self.assertEqual([next(iter(update)) for update in async_updates], ["Prior Preparation", "Decision Maker"])
        self.assertEqual(retrieve.call_count, 3)

    def test_final_prompt_overflow_and_api_error_do_not_return_cash(self):
        expected = prior_fixture(population=10**25)
        retrieve, verify = graph_hooks(expected, [])
        llm = _CountingLlm()
        graph = SetGraph(llm, object(), object()).compile_report_decision(
            prior_config=expected["prior_config"], prior_retriever=retrieve, prior_source_validator=verify)
        with (patch.object(decision_agent, "_build_compact_prompt_vi", return_value="### [1]" + "Đ" * 6500),
              patch.object(decision_agent, "_invoke_with_retry") as invoke,
              patch("builtins.print"), self.assertRaisesRegex(ValueError, "prompt=")):
            graph.invoke(graph_input(expected))
        invoke.assert_not_called()
        self.assertEqual(llm.calls, 0)
        with (patch.object(decision_agent, "_invoke_with_retry", side_effect=RuntimeError("API lỗi")),
              patch("builtins.print"), self.assertRaisesRegex(RuntimeError, "API lỗi")):
            graph.invoke(graph_input(expected))


if __name__ == "__main__":
    unittest.main()
