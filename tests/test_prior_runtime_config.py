"""Kiểm config/state prior, JSON và channel graph bằng fixture offline."""

from copy import deepcopy
from datetime import date
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd
from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph

from agents.agent_state import IndicatorAgentState
from core.prior_config import (
    CONTRACT_VERSION, PRIOR_STATE_FIELDS, copy_prior_json, normalize_prior_config,
    normalize_prior_query_context, normalize_prior_state, resolve_prior_paths,
    validate_prior_execution,
)
from utils.graph_setup import (
    ABLATION_CONFIGS, BacktestAgentState, SetGraph, _guard_prior_state,
    resolve_ablation_config,
)

ROOT = Path(__file__).resolve().parents[1]


def _context() -> dict:
    """Tạo context có shape hợp lệ; không giả định đã xác minh artifact."""
    return {
        "stock_name": "FPT", "as_of_date": "2022-12-27",
        "market_regime": {
            "as_of_date": "2022-12-27", "regime_id": 1, "regime_name": "BEAR",
            "volatility_level": "HIGH", "trend_strength": 0.2,
            "source_symbol": "VNINDEX", "feature_end_date": "2022-12-27",
        },
        "current_signals": {
            "trend": "TĂNG", "pattern": "NEUTRAL", "alpha_consensus": "DOWN",
            "indicator_consensus": "UP", "sentiment": "TRUNG TÍNH",
        },
    }


class PriorConfigTests(unittest.TestCase):
    def test_frozen_policy_defaults_and_examples(self):
        policy = json.loads((ROOT / "docs/plan/week4/integration_policy.json").read_text("utf-8"))
        examples = json.loads((ROOT / "docs/plan/week4/integration_examples.json").read_text("utf-8"))
        self.assertEqual(CONTRACT_VERSION, policy["contract_version"])
        self.assertEqual(normalize_prior_config(), policy["config"]["defaults"])
        self.assertEqual(set(PRIOR_STATE_FIELDS), set(policy["state"]["fields"]))
        for case in examples["config_examples"]:
            with self.subTest(case=case["case"]):
                self.assertEqual(normalize_prior_config(case["input"]), case["expected_normalized"])
        for case in examples["invalid_config_examples"]:
            with self.subTest(case=case["case"]), self.assertRaises(ValueError):
                normalize_prior_config(case["input"])

    def test_partial_config_and_defaults_are_independent(self):
        supplied = {"mode": "recent", "scope": "pooled", "k": 1}
        before = supplied.copy()
        first = normalize_prior_config(supplied)
        first["seed"] = 10
        self.assertEqual(supplied, before)
        self.assertEqual(normalize_prior_config(supplied)["seed"], 42)
        self.assertFalse(normalize_prior_config()["enable_bayesian_prior"])

    def test_modes_scopes_and_integer_boundaries(self):
        for mode in ("bayesian_regime", "random", "recent", "similarity"):
            for scope in ("same_symbol", "pooled"):
                for k in range(4):
                    with self.subTest(mode=mode, scope=scope, k=k):
                        result = normalize_prior_config({"mode": mode, "scope": scope, "k": k,
                                                         "seed": 2**32 - 1})
                        self.assertEqual(result["k"], k)
        self.assertEqual(normalize_prior_config({"seed": 0})["seed"], 0)

    def test_rejects_non_native_types_and_unknown_keys_even_disabled(self):
        class ConfigSubclass(dict):
            pass

        cases = [[], "full", ConfigSubclass(), {1: "bad"}, {"model": "llm"},
                 {"enable_bayesian_prior": np.bool_(False)}, {"k": np.int64(3)},
                 {"seed": np.int64(42)}, {"mode": np.str_("recent")},
                 {"k": "3"}, {"seed": None}, {"scope": "SAME_SYMBOL"}]
        for value in cases:
            with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                normalize_prior_config(value)

    def test_path_syntax_rejects_escape_and_ambiguous_segments(self):
        for value in ("/tmp/x", "C:/x", "//host/x", "a\\b", "../x", "a/../x",
                      "./x", "a//b", "a/", "https://host/x", "x\n.json", "x\x7f.json"):
            for field in ("bank_path", "manifest_path", "audit_path"):
                with self.subTest(value=value, field=field), self.assertRaises(ValueError):
                    normalize_prior_config({field: value})

    def test_disabled_does_not_touch_filesystem(self):
        with (patch.object(Path, "resolve", side_effect=AssertionError("Không resolve")),
              patch.object(Path, "is_file", side_effect=AssertionError("Không stat")),
              patch.object(Path, "open", side_effect=AssertionError("Không mở kho"))):
            self.assertIsNone(resolve_prior_paths({"bank_path": "missing/bank.json"}))
            normalize_prior_state({"prior_config": {}, "prior_tasks": []})

    def test_enabled_resolves_three_existing_files_without_reading_contents(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = {"enable_bayesian_prior": True, "k": 0,
                      "bank_path": "bank.json", "manifest_path": "manifest.json",
                      "audit_path": "audit.json"}
            for name in ("bank.json", "manifest.json", "audit.json"):
                (root / name).write_text("{}", encoding="utf-8")
            with patch.object(Path, "open", side_effect=AssertionError("Chưa nạp kho")):
                paths = resolve_prior_paths(config, root=root)
            self.assertEqual(set(paths), {"bank_path", "manifest_path", "audit_path"})
            self.assertEqual(paths["bank_path"], (root / "bank.json").resolve())

    def test_enabled_missing_file_or_directory_rejected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = {"enable_bayesian_prior": True, "bank_path": "missing.json"}
            with self.assertRaises(FileNotFoundError):
                resolve_prior_paths(config, root=root)
            (root / "missing.json").mkdir()
            with self.assertRaises(FileNotFoundError):
                resolve_prior_paths(config, root=root)

    def test_resolved_escape_rejected_before_file_check(self):
        # Mô phỏng kết quả resolve của symlink để không phụ thuộc quyền tạo link Windows.
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            outside = root.parent / "outside.json"
            with (patch.object(Path, "resolve", side_effect=[root, outside]),
                  patch.object(Path, "is_file") as is_file,
                  self.assertRaises(ValueError)):
                resolve_prior_paths({"enable_bayesian_prior": True}, root=root)
            is_file.assert_not_called()

    def test_original_is_enabled_full_daily_with_k_zero(self):
        for timeframe in ("1d", "1 ngày"):
            config, ablation, canonical = validate_prior_execution(
                {"enable_bayesian_prior": True, "k": 0}, is_backtest=True,
                time_frame=timeframe, include_alpha=True,
            )
            self.assertTrue(config["enable_bayesian_prior"])
            self.assertEqual(config["k"], 0)
            self.assertEqual(ablation, ABLATION_CONFIGS["full"])
            self.assertEqual(canonical, "1d")

    def test_enabled_rejects_non_full_or_truthy_ablation(self):
        cases = [ABLATION_CONFIGS[name] for name in ("alpha_only", "sentiment_only", "baseline")]
        cases += [{"enable_alpha_factors": 1, "enable_sentiment": True},
                  {"enable_alpha_factors": True, "enable_sentiment": "true"},
                  {"enable_alpha_factors": True},
                  {**ABLATION_CONFIGS["full"], "extra": True}]
        for ablation in cases:
            with self.subTest(ablation=ablation), self.assertRaises(ValueError):
                validate_prior_execution({"enable_bayesian_prior": True}, is_backtest=True,
                                         time_frame="1d", ablation_config=ablation)

    def test_enabled_rejects_live_invalid_alias_and_include_alpha(self):
        cases = [{"is_backtest": value} for value in (None, False, 1, "true", np.bool_(True))]
        cases += [{"time_frame": value} for value in (None, "1 day", " 1d", "1D", "1h", 1)]
        cases += [{"include_alpha": value} for value in (False, 1, "true")]
        for changed in cases:
            args = {"is_backtest": True, "time_frame": "1d", **changed}
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                validate_prior_execution({"enable_bayesian_prior": True}, **args)

    def test_config_conflict_uses_original_resolver(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled), self.assertRaises(ValueError):
                validate_prior_execution({"enable_bayesian_prior": enabled}, is_backtest=True,
                                         time_frame="1d", include_alpha=True,
                                         ablation_config=ABLATION_CONFIGS["full"])

    def test_disabled_preserves_four_ablations_legacy_alias_and_coercion(self):
        configs = list(ABLATION_CONFIGS.values()) + [
            {"enable_alpha_factors": "yes", "enable_sentiment": 0, "legacy_extra": 1}]
        for ablation in configs:
            config, result, timeframe = validate_prior_execution(
                is_backtest=False, time_frame="1 day", ablation_config=ablation)
            self.assertFalse(config["enable_bayesian_prior"])
            self.assertEqual(result, resolve_ablation_config(ablation))
            self.assertEqual(timeframe, "1 day")
        for flag in (None, True, False, 0, "yes"):
            _, result, _ = validate_prior_execution(is_backtest=False, time_frame=None,
                                                   include_alpha=flag)
            self.assertEqual(result, resolve_ablation_config(include_alpha=flag))


class PriorJsonStateTests(unittest.TestCase):
    def test_nested_tasks_stats_metadata_copy_and_json_roundtrip(self):
        value = {"prior_tasks": [{"outcome": {"net_return_pct": -0.5}, "exit_date": "2022-12-20"}],
                 "prior_stats": {"counts": [1, 2], "rate": None},
                 "prior_metadata": {"fallback": False, "selected_ids": ["e1"]}}
        copied = copy_prior_json(value)
        self.assertEqual(json.loads(json.dumps(copied, allow_nan=False)), value)
        copied["prior_tasks"][0]["outcome"]["net_return_pct"] = 1.0
        copied["prior_stats"]["counts"].append(3)
        copied["prior_metadata"]["selected_ids"].append("e2")
        self.assertEqual(value["prior_tasks"][0]["outcome"]["net_return_pct"], -0.5)
        self.assertEqual(value["prior_stats"]["counts"], [1, 2])
        self.assertEqual(value["prior_metadata"]["selected_ids"], ["e1"])

    def test_json_rejects_runtime_numpy_nonfinite_and_nonstring_keys(self):
        values = [np.bool_(True), np.int64(1), np.float64(1.0), np.str_("x"),
                  float("nan"), float("inf"), -float("inf"), Path("x"), (1,), {1},
                  {1: "x"}, date(2022, 12, 27), pd.DataFrame({"x": [1]}),
                  HumanMessage(content="test")]
        for value in values:
            with self.subTest(type=type(value).__name__), self.assertRaises(ValueError):
                copy_prior_json({"nested": [value]})

    def test_legacy_missing_fields_preserves_runtime_objects_and_keys(self):
        frame = pd.DataFrame({"Close": [1.0]})
        state = {"point_in_time_df": frame, "messages": [HumanMessage(content="test")]}
        copied = normalize_prior_state(state)
        self.assertEqual(set(copied), set(state))
        self.assertIs(copied["point_in_time_df"], frame)
        self.assertIsNot(copied, state)

    def test_disabled_all_sentinels_normalized_without_mutating_input(self):
        state = {"prior_config": {}, "market_regime": None, "current_signals": None,
                 "prior_provenance": None, "prior_tasks": [], "prior_stats": None,
                 "prior_metadata": None, "bayesian_prior_context": ""}
        result = normalize_prior_state(state)
        self.assertEqual(set(result), set(PRIOR_STATE_FIELDS))
        self.assertEqual(state["prior_config"], {})
        self.assertEqual(result["prior_config"], normalize_prior_config())
        self.assertIsNot(result["prior_tasks"], state["prior_tasks"])

    def test_disabled_rejects_stale_fields_and_wrong_sentinel_types(self):
        for field in PRIOR_STATE_FIELDS[1:]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                normalize_prior_state({"prior_config": {}, field: "stale"})
        for state in ({"prior_tasks": None}, {"prior_tasks": {}}, {"bayesian_prior_context": None}):
            with self.subTest(state=state), self.assertRaises(ValueError):
                normalize_prior_state(state)

    def test_disabled_rejects_duplicate_aliases_at_input_boundary(self):
        for field in ("current_regime", "regime_name", "selected_ids", "prior_result"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                normalize_prior_state({"prior_config": {}, field: None})

    def test_query_context_normalizes_iso_regime_and_signals_on_copy(self):
        state = _context()
        before = deepcopy(state)
        result = normalize_prior_query_context(state)
        self.assertEqual(result["as_of_date"], "2022-12-27")
        self.assertEqual(result["current_signals"]["trend"], "BULLISH")
        self.assertEqual(result["current_signals"]["alpha_consensus"], "BEARISH")
        self.assertEqual(result["current_signals"]["sentiment"], "NEUTRAL")
        result["market_regime"]["trend_strength"] = 0.9
        self.assertEqual(state, before)

    def test_query_context_rejects_missing_wrong_dates_symbol_and_outcome(self):
        cases = [{}, {**_context(), "as_of_date": "20221227"},
                 {**_context(), "as_of_date": date(2022, 12, 27)},
                 {**_context(), "as_of_date": "2022-12-26"},
                 {**_context(), "stock_name": "fpt"},
                 {**_context(), "outcome": {"result": "WIN"}},
                 {**_context(), "current_signals": {"trend": "UP"}}]
        for state in cases:
            with self.subTest(state=state), self.assertRaises(ValueError):
                normalize_prior_query_context(state)
        state = _context()
        state["market_regime"]["feature_end_date"] = "2022-12-28"
        with self.assertRaises(ValueError):
            normalize_prior_query_context(state)

    def test_enabled_missing_or_self_reported_proof_rejected_before_node(self):
        for k in (0, 3):
            node = Mock(return_value={})
            guard = _guard_prior_state(node)
            state = {"prior_config": {"enable_bayesian_prior": True, "k": k},
                     "is_backtest": True, "time_frame": "1d", **_context()}
            with self.assertRaisesRegex(ValueError, "thiếu regime/signals/provenance"):
                guard(state)
            state["prior_provenance"] = {"status": "PASS", "hash": "a" * 64}
            with self.assertRaisesRegex(ValueError, "chưa có adapter"):
                guard(state)
            node.assert_not_called()

    def test_node_cannot_emit_stale_prior_payload(self):
        node = Mock(return_value={"bayesian_prior_context": "stale"})
        with self.assertRaises(ValueError):
            _guard_prior_state(node)({})
        node.assert_called_once()


class PriorGraphSchemaTests(unittest.TestCase):
    def test_optional_fields_declared_in_both_real_schemas(self):
        for schema in (IndicatorAgentState, BacktestAgentState):
            self.assertTrue(set(PRIOR_STATE_FIELDS).issubset(schema.__optional_keys__))
            self.assertFalse(set(PRIOR_STATE_FIELDS).intersection(schema.__required_keys__))

    def test_schema_probe_retains_all_fields_including_enabled_payload(self):
        # Probe channel TypedDict thuần; không là phép chạy prior trên graph production.
        payload = {"prior_config": normalize_prior_config({"enable_bayesian_prior": True}),
                   "market_regime": _context()["market_regime"],
                   "current_signals": _context()["current_signals"],
                   "prior_provenance": {"context": {"cutoff": "2022-12-27"}},
                   "prior_tasks": [{"episode_id": "e1"}], "prior_stats": {"count": 1},
                   "prior_metadata": {"selected_ids": ["e1"]}, "bayesian_prior_context": "BRPP"}
        for schema in (IndicatorAgentState, BacktestAgentState):
            graph = StateGraph(schema)
            graph.add_node("probe", lambda state: copy_prior_json(state))
            graph.add_edge(START, "probe")
            graph.add_edge("probe", END)
            compiled = graph.compile()
            self.assertTrue(set(PRIOR_STATE_FIELDS).issubset(compiled.channels))
            self.assertEqual(compiled.invoke(payload), payload)

    def test_production_graphs_preserve_disabled_fields_and_legacy_output(self):
        captured = []

        def factory(*_args):
            def node(state):
                captured.append(deepcopy(state))
                return {"indicator_report": "fixture"}
            return node

        with (patch("utils.graph_setup.create_indicator_agent", factory),
              patch("utils.graph_setup.create_pattern_agent", factory),
              patch("utils.graph_setup.create_trend_agent", factory),
              patch("utils.graph_setup.create_alpha_agent", factory),
              patch("utils.graph_setup.create_final_trade_decider", factory),
              patch("builtins.print")):
            builder = SetGraph(object(), object(), object())
            graphs = [builder.compile_upstream(), builder.compile_decision(), builder.set_graph()]
            state = {"prior_config": {}, "market_regime": None, "current_signals": None,
                     "prior_provenance": None, "prior_tasks": [], "prior_stats": None,
                     "prior_metadata": None, "bayesian_prior_context": ""}
            for graph in graphs:
                legacy = graph.invoke({})
                result = graph.invoke(state)
                self.assertEqual(legacy, {"indicator_report": "fixture"})
                self.assertEqual({key: result[key] for key in legacy}, legacy)
                self.assertEqual(result["prior_config"], normalize_prior_config())
                self.assertTrue(set(PRIOR_STATE_FIELDS).issubset(result))
                self.assertEqual(result["bayesian_prior_context"], "")
            self.assertEqual(state["prior_config"], {})
        self.assertEqual(len(captured), 20)

    def test_production_graphs_reject_stale_or_unverified_state_before_nodes(self):
        node = Mock(return_value={})
        factory = Mock(return_value=node)
        with (patch("utils.graph_setup.create_indicator_agent", factory),
              patch("utils.graph_setup.create_pattern_agent", factory),
              patch("utils.graph_setup.create_trend_agent", factory),
              patch("utils.graph_setup.create_alpha_agent", factory),
              patch("utils.graph_setup.create_final_trade_decider", factory),
              patch("builtins.print")):
            builder = SetGraph(object(), object(), object())
            for graph in (builder.compile_upstream(), builder.compile_decision(), builder.set_graph()):
                for state in ({"bayesian_prior_context": "stale"},
                              {"prior_config": {"k": True}},
                              {"prior_config": {"enable_bayesian_prior": True, "k": 0},
                               "is_backtest": True, "time_frame": "1d", **_context()}):
                    with self.assertRaises(ValueError):
                        graph.invoke(state)
        node.assert_not_called()


if __name__ == "__main__":
    unittest.main()
