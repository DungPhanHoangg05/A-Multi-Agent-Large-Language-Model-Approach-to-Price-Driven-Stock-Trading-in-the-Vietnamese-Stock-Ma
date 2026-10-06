"""Kiểm BRPP tại node Decision thật với verifier/LLM fixture offline."""

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from agents import decision_agent
from core.bayesian_retriever import VERSIONS, format_compact_prior_prefix
from core.prior_config import PRIOR_STATE_FIELDS, normalize_prior_config
from scripts.verify_prior_prompt_budget import prefix_fixture
from test_backtest_token_budget import _CountingLlm, _StructuredCountingLlm, _budget_state

ROOT = Path(__file__).resolve().parents[1]


def prior_fixture(*, lang: str = "vi", mode: str = "bayesian_regime", k: int = 3,
                  selected: int | None = None, population: int = 852) -> dict:
    """Tạo shape nhất quán; provenance là mẫu, không chứng minh giá/model fixture."""
    selected = k if selected is None else selected
    tasks, stats = prefix_fixture("CONSOLIDATION", k, population)
    tasks = tasks[:selected]
    proof = json.loads((ROOT / "docs/plan/week4/provenance_examples.json").read_text("utf-8"))[
        "replay_examples"][0]["prior_provenance"]
    config = normalize_prior_config({"enable_bayesian_prior": True, "mode": mode, "k": k})
    state = _budget_state(lang)
    cutoff = "2022-12-27"
    state.update(as_of_date=cutoff, prior_config=config,
        market_regime={"as_of_date": cutoff, "regime_id": 3, "regime_name": "CONSOLIDATION",
                       "volatility_level": "LOW", "trend_strength": 0.0,
                       "feature_end_date": cutoff, "source_symbol": "VNINDEX"},
        current_signals={"trend": "BULLISH", "pattern": "NEUTRAL", "alpha_consensus": "BEARISH",
                         "indicator_consensus": "NEUTRAL", "sentiment": "NEUTRAL"},
        prior_provenance=proof, prior_tasks=tasks, prior_stats=stats)
    proof["context"] = {"symbol": "FPT", "as_of_date": cutoff, "time_frame": "1d",
                        "provider_mode": "historical_prefix"}
    candidates = population if selected == k else selected
    if selected < k:
        # Partial/empty: stats từ population regime, fixture mode Bayesian cần cùng candidate count.
        if mode == "bayesian_regime":
            _, stats = prefix_fixture("CONSOLIDATION", 3, selected)
            state["prior_stats"] = stats
            population = selected
            for name, metric in stats["metrics"].items():
                metric.update(numerator=selected if name == "win_rate_long" else 0,
                              denominator=selected,
                              rate=(1.0 if name == "win_rate_long" else 0.0) if selected else None)
        candidates = selected
    metadata = {**VERSIONS, "bank_sha256": proof["bank"]["bank_sha256"], "symbol": "FPT",
                "as_of_date": cutoff, "current_regime": "CONSOLIDATION", "mode": mode,
                "scope": "same_symbol", "requested_k": k, "seed": 42,
                "eligible_count": candidates, "matched_regime_count": population,
                "candidate_count": candidates,
                "effective_seed": "a" * 64 if mode == "random" and k else None,
                "selected_count": len(tasks), "selected_ids": [task["episode_id"] for task in tasks],
                "selected_scores": [{"episode_id": task["episode_id"],
                                     "score": 0.75 if mode in ("similarity", "bayesian_regime") else None}
                                    for task in tasks],
                "status": "disabled" if k == 0 else "empty" if selected == 0 else "partial" if selected < k else "complete",
                "reason": "k_zero" if k == 0 else "no_eligible_history" if selected == 0 else "insufficient_candidates" if selected < k else None}
    if k == 0:
        metadata.update(eligible_count=None, matched_regime_count=None, candidate_count=None)
    state["prior_metadata"] = metadata
    state["bayesian_prior_context"] = format_compact_prior_prefix(tasks, state["prior_stats"])
    return state


def fixture_verifier(expected: dict) -> Mock:
    """Kiểm bản sao fixture; tuyệt đối không là adapter xác minh artifact thật."""
    def check(projection: dict) -> None:
        for field in (*PRIOR_STATE_FIELDS, "stock_name", "as_of_date"):
            if projection[field] != expected[field]:
                raise ValueError(f"Projection khác fixture ở {field}")
    return Mock(side_effect=check)


class DecisionPriorIntegrationTests(unittest.TestCase):
    def test_five_branches_and_k_matrix_with_text_and_structured_llms(self):
        for lang in ("vi", "en"):
            for mode in ("bayesian_regime", "random", "recent", "similarity"):
                for k in range(4):
                    for structured in (False, True):
                        with self.subTest(lang=lang, mode=mode, k=k, structured=structured):
                            state = prior_fixture(lang=lang, mode=mode, k=k)
                            before = deepcopy(state)
                            verifier = fixture_verifier(state)
                            llm = _StructuredCountingLlm() if structured else _CountingLlm()
                            with (patch("builtins.print"),
                                  patch("core.bayesian_retriever.format_compact_prior_prefix",
                                        wraps=format_compact_prior_prefix) as formatter,
                                  patch.object(decision_agent, "_invoke_with_retry",
                                               wraps=decision_agent._invoke_with_retry) as invoke):
                                result = decision_agent.create_final_trade_decider(
                                    llm, prior_source_validator=verifier)(state)
                            prompt = result["decision_prompt"]
                            self.assertEqual(state, before)
                            verifier.assert_called_once()
                            formatter.assert_called_once()
                            invoke.assert_called_once()
                            self.assertLess(len(prompt), 6500)
                            self.assertEqual(result["prior_metadata"], state["prior_metadata"])
                            if k == 0:
                                self.assertNotIn("[BRPP v1]", prompt)
                                self.assertNotIn("PRIOR:", prompt)
                            else:
                                prefix = state["bayesian_prior_context"]
                                self.assertEqual(prompt.count("[BRPP v1]"), 1)
                                self.assertEqual(prompt.count(prefix), 1)
                                self.assertLess(prompt.index(prefix), prompt.index("### [1]"))
                                self.assertIn(decision_agent._PRIOR_REASONING[lang], prompt)
                                self.assertIn("S=thiếu tin", prompt)
                            captured = llm.structured_prompts if structured else llm.prompts
                            self.assertEqual(captured, [prompt])
                            for text in ("LONG", "SHORT", "CASH", "Open", "Close", "T+2.5", "3/5"):
                                self.assertIn(text, prompt)

    def test_original_has_same_prompt_as_disabled_and_keeps_metadata(self):
        for lang in ("vi", "en"):
            state = prior_fixture(lang=lang, k=0)
            off = {key: value for key, value in state.items() if key not in PRIOR_STATE_FIELDS}
            with patch("builtins.print"):
                enabled = decision_agent.create_final_trade_decider(
                    _CountingLlm(), prior_source_validator=fixture_verifier(state))(state)
                disabled = decision_agent.create_final_trade_decider(_CountingLlm())(off)
            self.assertEqual(enabled["decision_prompt"], disabled["decision_prompt"])
            self.assertEqual(enabled["prior_metadata"]["reason"], "k_zero")
            self.assertNotIn("prior_metadata", disabled)

    def test_disabled_rejects_stale_state_and_does_not_call_source_or_formatter(self):
        llm, verifier = _CountingLlm(), Mock()
        with patch("core.bayesian_retriever.format_compact_prior_prefix") as formatter, patch("builtins.print"):
            node = decision_agent.create_final_trade_decider(llm, prior_source_validator=verifier)
            node(_budget_state())
            for field, value in (("bayesian_prior_context", "stale"), ("prior_stats", {}),
                                 ("prior_metadata", {}), ("prior_tasks", [{"outcome": "stale"}])):
                with self.subTest(field=field), self.assertRaises(ValueError):
                    node({**_budget_state(), field: value})
        self.assertEqual(llm.calls, 1)
        formatter.assert_not_called()
        verifier.assert_not_called()

    def test_missing_invalid_config_query_metadata_and_proof_fail_before_api(self):
        base = prior_fixture()
        cases = []
        for field in PRIOR_STATE_FIELDS:
            state = deepcopy(base)
            state.pop(field)
            cases.append(state)
        for change in ({"prior_config": {"enable_bayesian_prior": "true"}},
                       {"prior_config": {"enable_bayesian_prior": True, "k": True}},
                       {"outcome": {"result": "WIN"}}, {"time_frame": "1 day"},
                       {"is_backtest": False}, {"current_signals": {}},
                       {"prior_provenance": {"status": "PASS"}}, {"prior_metadata": {}},
                       {"alpha_report": ""}, {"prior_stats": None},
                       {"bayesian_prior_context": "caller supplied"}):
            cases.append({**deepcopy(base), **change})
        for state in cases:
            llm = _CountingLlm()
            with self.subTest(keys=list(state)), patch("builtins.print"), self.assertRaises(ValueError):
                decision_agent.create_final_trade_decider(
                    llm, prior_source_validator=lambda _: None)(state)
            self.assertEqual(llm.calls, 0)

    def test_self_reported_provenance_without_verifier_and_verifier_error_stop_before_formatter(self):
        for k in (0, 3):
            state = prior_fixture(k=k)
            llm = _CountingLlm()
            with patch("core.bayesian_retriever.format_compact_prior_prefix") as formatter:
                with self.assertRaisesRegex(ValueError, "hàm xác minh nguồn"):
                    decision_agent.create_final_trade_decider(llm)(state)
                with self.assertRaisesRegex(ValueError, "Nguồn lỗi"):
                    decision_agent.create_final_trade_decider(
                        llm, prior_source_validator=Mock(side_effect=ValueError("Nguồn lỗi")))(state)
                formatter.assert_not_called()
            self.assertEqual(llm.calls, 0)

    def test_empty_and_partial_preserve_none_counts_status_and_ownership(self):
        for selected in (0, 1, 2):
            state = prior_fixture(selected=selected)
            before = deepcopy(state)
            with patch("builtins.print"):
                result = decision_agent.create_final_trade_decider(
                    _CountingLlm(), prior_source_validator=fixture_verifier(state))(state)
            self.assertEqual(result["prior_metadata"], before["prior_metadata"])
            if selected == 0:
                self.assertIn("0/0(N/A)", result["decision_prompt"])
                self.assertIsNone(result["prior_stats"]["metrics"]["win_rate_long"]["rate"])
            result["prior_metadata"]["selected_ids"].append("foreign")
            result["prior_stats"]["metrics"]["win_rate_long"]["numerator"] = -1
            self.assertEqual(state, before)

    def test_selection_cutoff_ids_scores_and_stats_mismatch_are_errors(self):
        cases = []
        for group, field, value in (("prior_metadata", "selected_ids", ["foreign"]),
                                    ("prior_metadata", "selected_count", True),
                                    ("prior_metadata", "status", "empty"),
                                    ("prior_metadata", "seed", True),
                                    ("prior_metadata", "matched_regime_count", 851),
                                    ("prior_stats", "population_count", 851)):
            state = prior_fixture()
            state[group][field] = value
            cases.append(state)
        state = prior_fixture()
        state["prior_tasks"][0]["exit_date"] = state["as_of_date"]
        cases.append(state)
        state = prior_fixture()
        state["prior_tasks"][0]["outcome"]["net_return_pct"] = float("nan")
        cases.append(state)
        for state in cases:
            llm = _CountingLlm()
            with self.subTest(), self.assertRaises(ValueError):
                decision_agent.create_final_trade_decider(llm, prior_source_validator=lambda _: None)(state)
            self.assertEqual(llm.calls, 0)

    def test_prefix_600_with_reasoning_passes_and_601_or_total_6500_calls_no_api(self):
        for lang in ("vi", "en"):
            state = prior_fixture(lang=lang, population=10**25)
            self.assertEqual(len(state["bayesian_prior_context"]), 600)
            llm = _CountingLlm()
            node = decision_agent.create_final_trade_decider(llm, prior_source_validator=fixture_verifier(state))
            with patch("builtins.print"):
                result = node(state)
            self.assertLess(len(result["decision_prompt"]), 6500)
            llm.calls = 0
            build_name = f"_build_compact_prompt_{lang}"
            build = getattr(decision_agent, build_name)
            delta = 6500 - len(result["decision_prompt"])
            with (patch.object(decision_agent, build_name, side_effect=lambda *args: build(*args) + "Đ" * delta),
                  patch.object(decision_agent, "_invoke_with_retry") as invoke,
                  patch("builtins.print"), self.assertRaisesRegex(ValueError, "prompt=6500")):
                node(state)
            invoke.assert_not_called()
            self.assertEqual(llm.calls, 0)
            # Formatter thực từ chối ngay cả trước khi fixture được đưa vào Decision.
            with self.assertRaisesRegex(ValueError, "600"):
                prior_fixture(lang=lang, population=10**26)

    def test_prefix_overflow_and_duplicate_in_builder_rejected_before_api(self):
        state = prior_fixture()
        for prefix in (state["bayesian_prior_context"] + "extra", "X" * 601):
            wrong = {**state, "bayesian_prior_context": prefix}
            llm = _CountingLlm()
            with self.assertRaises(ValueError):
                decision_agent.create_final_trade_decider(llm, prior_source_validator=lambda _: None)(wrong)
            self.assertEqual(llm.calls, 0)
        llm = _CountingLlm()
        with (patch.object(decision_agent, "_build_compact_prompt_vi", return_value="[BRPP v1]\n### [1]"),
              self.assertRaisesRegex(ValueError, "đã chứa BRPP")):
            decision_agent.create_final_trade_decider(llm, prior_source_validator=lambda _: None)(state)
        self.assertEqual(llm.calls, 0)

    def test_source_validator_gets_own_copy_and_cannot_rewrite_prepared_result(self):
        state = prior_fixture()
        before = deepcopy(state)

        def mutate_copy(projection: dict) -> None:
            projection["prior_tasks"][0]["outcome"]["net_return_pct"] = -2.0
            projection["prior_metadata"]["selected_ids"].append("foreign")

        with patch("builtins.print"):
            result = decision_agent.create_final_trade_decider(
                _CountingLlm(), prior_source_validator=mutate_copy)(state)
        self.assertEqual(state, before)
        self.assertEqual(result["prior_tasks"], before["prior_tasks"])
        self.assertEqual(result["prior_metadata"], before["prior_metadata"])
        for output in (True, {"status": "PASS"}):
            with self.subTest(output=output), self.assertRaisesRegex(ValueError, "trả None"):
                decision_agent.create_final_trade_decider(
                    _CountingLlm(), prior_source_validator=lambda _: output)(state)

    def test_enabled_api_and_output_errors_propagate_without_cash_fallback(self):
        state = prior_fixture()
        for api_error in (True, False):
            llm = _CountingLlm()
            llm.invoke = Mock(side_effect=RuntimeError("Lỗi API fixture")) if api_error else Mock(
                return_value=SimpleNamespace(content='{"decision":"NEUTRAL"}'))
            with (patch("builtins.print"), patch.object(decision_agent.time, "sleep"),
                  self.assertRaises(RuntimeError)):
                decision_agent.create_final_trade_decider(
                    llm, prior_source_validator=fixture_verifier(state))(state)
            self.assertEqual(llm.invoke.call_count, 3 if api_error else 2)


if __name__ == "__main__":
    unittest.main()
