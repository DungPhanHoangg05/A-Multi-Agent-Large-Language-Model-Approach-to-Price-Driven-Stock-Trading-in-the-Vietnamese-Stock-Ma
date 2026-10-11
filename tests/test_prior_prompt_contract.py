"""Prefix/ablation/schema Decision trên producer thật và LLM fixture offline."""

from copy import deepcopy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pandas as pd

from agents import decision_agent
from core.historical_signals import digest
from core.prior_prompt import CANDIDATE_PROFILES, build_prior_request, validate_prior_request
from core.prior_quality_gate import COUPLED_GATE
from core.prior_evidence_v2 import format_evidence_prefix
from core.research_invocation import ENABLED, CURRENT
from test_prior_quality_gate import gate_query, populated_fixture
from test_backtest_token_budget import _budget_state
from prior_context_test_support import ContextFixture


class FixtureLlm:
    """Ghi schema/prompt và trả JSON fixture; không có HTTP hoặc ép hướng theo prior."""

    def __init__(self, result: dict | list[dict], *, structured: bool = True) -> None:
        self.results = result if type(result) is list else [result]
        self.structured = structured
        self.prompts = []
        self.schema = None
        self.budgets = []

    def with_structured_output(self, schema, **options):
        if not self.structured:
            raise NotImplementedError("Fixture text")
        self.schema = schema
        self.options = options
        return SimpleNamespace(invoke=self.invoke_structured)

    def invoke(self, prompt):
        self.prompts.append(prompt)
        self.budgets.append(CURRENT.get())
        return SimpleNamespace(content=json.dumps(self.results[min(len(self.prompts)-1, len(self.results)-1)], ensure_ascii=False))

    def invoke_structured(self, prompt):
        raw = self.invoke(prompt)
        return {"parsed": json.loads(raw.content), "raw": raw, "parsing_error": None}


def decision_result(request: dict | None = None, *, action: str = "LONG") -> dict:
    """Decision giả chỉ kiểm giao thức, không dùng để báo hiệu quả đầu tư."""
    result = {"decision": action, "forecast_horizon": "T+2.5", "confidence": "Cao", "risk_reward_ratio": 1.5,
              "evidence_for": "Alpha hiện tại.", "evidence_against": "Lịch sử có rủi ro.", "justification": "Đối chiếu hiện tại."}
    if request is not None and request["decision_contract_version"] == "decision_prior_use_v1":
        view = request["trace"]
        result["prior_use"] = {"metric_ids": view["visible_metric_ids"][:1],
                               "example_ids": view["visible_example_ids"][:1],
                               "assessment": "CONFLICTS", "reason": "Tín hiệu hiện tại khác lịch sử; vẫn giữ phán quyết gốc."}
    return result


def request_state(request: dict, lang: str = "vi", style: str = "short") -> dict:
    """Projection báo cáo xác định cho node; source thật được kiểm ở builder/point test."""
    query = request["query"]
    return {**_budget_state(lang, style=style, symbol=query["symbol"]), "as_of_date": query["as_of_date"],
            "market_regime": {"regime_name": query["current_regime"]}, "current_signals": deepcopy(query["current_signals"])}


def invoke_request(request: dict, state: dict, llm: FixtureLlm) -> dict:
    """Hook fixture cung cấp cùng projection/prefix; không thay adapter nguồn production."""
    def prepare(actual):
        if digest(actual) != digest(state):
            raise ValueError("Projection khác fixture")
        return deepcopy(actual), request["prefix"]
    return decision_agent.create_final_trade_decider(llm, _prior_preparer=prepare, _prior_request=request)(deepcopy(state))


class PriorPromptContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = populated_fixture()
        self.addCleanup(self.fx.close)
        self.query = gate_query(self.fx)
        self.evidence = self.fx.retriever.quality_evidence(**self.query)

    def request(self, candidate: str = "C3", evidence: dict | None = None, query: dict | None = None) -> dict:
        query = query or self.query
        return build_prior_request(self.evidence if evidence is None else evidence, candidate, self.fx.retriever,
                                   selector=query["selector"], query_features=query["query_features"])

    def test_three_content_modes_share_base_and_hide_only_requested_blocks(self) -> None:
        requests = [self.request(key) for key in ("C3", "C3_stats_only", "C3_examples_only")]
        self.assertEqual(len({r["base_evidence_sha256"] for r in requests}), 1)
        self.assertEqual(len({r["request_sha256"] for r in requests}), 3)
        full, stats, examples = requests
        self.assertEqual(full["trace"]["visible_metric_ids"], stats["trace"]["visible_metric_ids"])
        self.assertEqual(full["trace"]["visible_example_ids"], examples["trace"]["visible_example_ids"])
        self.assertEqual(stats["trace"]["visible_k"], 0)
        self.assertGreater(stats["trace"]["retrieved_k"], 0)
        self.assertEqual(examples["trace"]["visible_metric_ids"], [])
        self.assertNotIn("win_rate_long=", examples["prefix"])
        self.assertNotIn("n_C=", examples["prefix"])
        self.assertNotIn("FPT@", stats["prefix"])
        self.assertNotIn("FPT:", stats["prefix"])
        self.assertTrue(all(key in examples["prefix"] for key in examples["trace"]["visible_example_ids"]))
        self.assertIn("pattern_false_bullish_rate=N/A", stats["prefix"])
        self.assertNotIn("pattern_false_bullish_rate", stats["trace"]["visible_metric_ids"])
        for request in requests:
            self.assertLessEqual(len(request["prefix"]), 600)
            validate_prior_request(request, self.evidence, self.fx.retriever,
                                   selector=self.query["selector"], query_features=self.query["query_features"])

    def test_c1_prefix_and_reasoning_match_w5_bytes_and_c2_retains_reasoning(self) -> None:
        evidence = self.fx.retriever.quality_evidence(**self.query, gate_version=COUPLED_GATE)
        request = self.request("C1", evidence)
        legacy = self.fx.retriever.retrieve_evidence(**{k:self.query[k] for k in
            ("symbol", "as_of_date", "current_regime", "current_signals")})
        # Cùng stats/tasks: adapter fixture cho template W5, không phát hành artifact v2 giả.
        legacy["tasks"] = evidence["tasks"]
        legacy["effective_k"] = len(evidence["tasks"])
        with patch("core.prior_evidence_v2.validate_evidence"):
            expected = format_evidence_prefix(legacy)
        self.assertEqual(request["prefix"].encode(), expected.encode())
        c2 = self.request("C2")
        for lang in ("vi", "en"):
            prompt1 = invoke_request(request, request_state(request, lang), FixtureLlm(decision_result()))["decision_prompt"]
            prompt2 = invoke_request(c2, request_state(c2, lang), FixtureLlm(decision_result()))["decision_prompt"]
            reasoning1 = prompt1.split(request["prefix"] + "\n", 1)[1].split("\n### [1]", 1)[0]
            reasoning2 = prompt2.split(c2["prefix"] + "\n", 1)[1].split("\n### [1]", 1)[0]
            self.assertEqual(reasoning1, reasoning2)
            self.assertNotIn('"prior_use"', prompt2)

    def test_all_profiles_long_reports_languages_and_both_llm_routes_fit_caps(self) -> None:
        maximum = 0
        legacy = self.fx.retriever.retrieve_evidence(**{k:self.query[k] for k in
            ("symbol", "as_of_date", "current_regime", "current_signals")})
        legacy_prefix = format_evidence_prefix(legacy)
        for lang in ("vi", "en"):
            for style in ("short", "saturated", "structured"):
                for structured in (True, False):
                    with self.subTest(candidate="C0", lang=lang, style=style, structured=structured), patch("builtins.print"):
                        llm = FixtureLlm(decision_result(), structured=structured)
                        state = _budget_state(lang, style=style)
                        output = decision_agent.create_final_trade_decider(llm,
                            _prior_preparer=lambda state:(deepcopy(state), legacy_prefix))(deepcopy(state))
                        self.assertLessEqual(len(legacy_prefix), 600)
                        self.assertLess(len(output["decision_prompt"]), 6500)
                        self.assertNotIn("prior_decision_trace", output)
                        self.assertEqual(len(llm.prompts), 1)
        for candidate in CANDIDATE_PROFILES:
            evidence = self.fx.retriever.quality_evidence(**self.query, gate_version=COUPLED_GATE) if candidate == "C1" else self.evidence
            request = self.request(candidate, evidence)
            for lang in ("vi", "en"):
                for style in ("short", "saturated", "structured"):
                    for structured in (True, False):
                        with self.subTest(candidate=candidate, lang=lang, style=style, structured=structured), patch("builtins.print"):
                            state = request_state(request, lang, style)
                            before = deepcopy(state)
                            llm = FixtureLlm(decision_result(request), structured=structured)
                            output = invoke_request(request, state, llm)
                            prompt = output["decision_prompt"]
                            maximum = max(maximum, len(prompt))
                            self.assertLess(len(prompt), 6500)
                            self.assertEqual(prompt.count(request["prefix"]), 1)
                            self.assertEqual(state, before)
                            self.assertEqual(len(llm.prompts), 1)
                            self.assertEqual(output["prior_decision_trace"]["raw_action"], "LONG")
                            for marker in ("### [1]", "### [2]", "### [3]", "### [4]", "### [5]", "LONG", "SHORT", "CASH", "Open", "Close", "3/5"):
                                self.assertIn(marker, prompt)
        self.assertGreater(maximum, 5000)

    def test_disabled_zero_and_no_visible_block_use_exact_original_prompt_and_schema(self) -> None:
        options = ({"requested_k": 0}, {"enable_bayesian_prior": False}, {"current_regime": "CHOPPY"})
        for changed in options:
            evidence = self.fx.retriever.quality_evidence(**{**self.query, **changed})
            for candidate in ("C3", "C3_stats_only", "C3_examples_only"):
                request = self.request(candidate, evidence)
                for lang in ("vi", "en"):
                    state = request_state(request, lang, "saturated")
                    original_llm = FixtureLlm(decision_result())
                    plain = {k:v for k,v in state.items() if k not in ("market_regime", "current_signals")}
                    original = decision_agent.create_final_trade_decider(original_llm)(deepcopy(plain))
                    llm = FixtureLlm(decision_result())
                    output = invoke_request(request, state, llm)
                    self.assertEqual(output["decision_prompt"].encode(), original["decision_prompt"].encode())
                    self.assertIs(llm.schema, decision_agent.TradeDecisionOutput)
                    self.assertEqual(request["prefix"], "")
                    self.assertIsNone(output["prior_decision_trace"]["prior_use"])
                    self.assertNotIn("prior_use", output["final_trade_decision"])

    def test_real_missing_examples_keeps_stats_only_and_examples_only_original(self) -> None:
        query = gate_query(self.fx, cutoff="2021-01-14")
        evidence = self.fx.retriever.quality_evidence(**query)
        stats = self.request("C3_stats_only", evidence, query)
        examples = self.request("C3_examples_only", evidence, query)
        self.assertTrue(stats["prefix"])
        self.assertEqual(stats["trace"]["retrieved_k"], 0)
        self.assertEqual(stats["trace"]["visible_k"], 0)
        self.assertEqual(examples["prefix"], "")
        self.assertEqual(examples["decision_contract_version"], "decision_legacy_v1")

    def test_conflict_or_not_used_never_forces_action_or_extra_llm_call(self) -> None:
        request = self.request()
        for action in ("LONG", "SHORT"):
            for used in (True, False):
                response = decision_result(request, action=action)
                if not used:
                    response["prior_use"].update(metric_ids=[], example_ids=[], assessment="NOT_USED")
                llm = FixtureLlm(response)
                output = invoke_request(request, request_state(request), llm)
                self.assertEqual(output["prior_decision_trace"]["raw_action"], action)
                self.assertEqual(json.loads(output["final_trade_decision"])["decision"], action)
                self.assertEqual(len(llm.prompts), 1)

    def test_full_600_reserve_and_exact_6499_6500_boundary_before_llm(self) -> None:
        # Chỉ oracle cap nội bộ; request padding không được phát hành thành artifact nguồn.
        request = self.request()
        request["prefix"] += " " * (600 - len(request["prefix"]))
        request["request_sha256"] = digest({k:v for k,v in request.items() if k != "request_sha256"})
        for lang in ("vi", "en"):
            state = request_state(request, lang, "saturated")
            with patch("builtins.print"):
                output = invoke_request(request, state, FixtureLlm(decision_result(request)))
            length = len(output["decision_prompt"])
            self.assertLess(length, 6500)
            build_name = f"_build_compact_prompt_{lang}"
            original = getattr(decision_agent, build_name)
            for target in (6499, 6500):
                def extended(*args):
                    return original(*args) + "Đ" * (target - length)
                llm = FixtureLlm(decision_result(request))
                with patch.object(decision_agent, build_name, side_effect=extended), patch("builtins.print"):
                    if target == 6499:
                        self.assertEqual(len(invoke_request(request, state, llm)["decision_prompt"]), target)
                    else:
                        with self.assertRaisesRegex(ValueError, "prompt=6500"):
                            invoke_request(request, state, llm)
                        self.assertEqual(llm.prompts, [])
        request["prefix"] += " "
        request["request_sha256"] = digest({k:v for k,v in request.items() if k != "request_sha256"})
        llm = FixtureLlm(decision_result(request))
        with self.assertRaises(ValueError):
            invoke_request(request, request_state(request), llm)
        self.assertEqual(llm.prompts, [])

    def test_longest_regime_all_four_metrics_three_examples_fit_without_changing_reports(self) -> None:
        for row in self.fx.records:
            if row["symbol"] == "FPT":
                row["regime"] = "CONSOLIDATION"
                row["agent_signals"]["pattern"] = "BULLISH"
        self.fx.publish()
        query = gate_query(self.fx, regime="CONSOLIDATION")
        query["current_signals"]["pattern"] = "BULLISH"
        evidence = self.fx.retriever.quality_evidence(**query)
        self.assertEqual(len(evidence["gate"]["ready_metric_ids"]), 4)
        self.assertEqual(evidence["effective_k"], 3)
        request = self.request("C3", evidence, query)
        self.assertLessEqual(len(request["prefix"]), 600)
        c2 = self.request("C2", evidence, query)
        for lang in ("vi", "en"):
            with patch("builtins.print"):
                output = invoke_request(request, request_state(request, lang, "saturated"), FixtureLlm(decision_result(request)))
                legacy = invoke_request(c2, request_state(c2, lang, "saturated"), FixtureLlm(decision_result()))
            self.assertLess(len(output["decision_prompt"]), 6500)
            for index in range(1, 6):
                start = f"### [{index}]"
                end = f"### [{index+1}]" if index < 5 else ("THỨ TỰ ƯU TIÊN" if lang == "vi" else "EVIDENCE PRIORITY")
                reports = [item["decision_prompt"].split(start, 1)[1].split(end, 1)[0] for item in (output, legacy)]
                self.assertEqual(reports[0], reports[1])

    def test_hidden_ids_duplicates_missing_trace_and_unknown_fields_are_format_errors(self) -> None:
        request = self.request("C3_stats_only")
        good = decision_result(request)
        bad = []
        for change in ({"metric_ids": ["pattern_false_bullish_rate"]}, {"example_ids": self.evidence["gate"]["ready_example_ids"][:1]},
                       {"metric_ids": ["win_rate_long"] * 2}, {"assessment": "NOT_USED"}, {"reason": " "}):
            value = deepcopy(good)
            value["prior_use"].update(change)
            bad.append(value)
        missing = deepcopy(good)
        missing.pop("prior_use")
        bad += [missing, {**good, "unregistered": True}]
        for invalid in bad:
            with self.subTest(invalid=invalid), patch("builtins.print"):
                llm = FixtureLlm(invalid)
                with self.assertRaises(RuntimeError):
                    invoke_request(request, request_state(request), llm)
                self.assertEqual(len(llm.prompts), decision_agent.DECISION_FORMAT_ATTEMPTS)

    def test_format_repair_uses_same_wrapper_and_invocation_budget(self) -> None:
        request = self.request()
        good = decision_result(request)
        invalid = {k:v for k,v in good.items() if k != "prior_use"}
        llm = FixtureLlm([invalid, good])
        token = ENABLED.set(True)
        self.addCleanup(ENABLED.reset, token)
        with patch.object(decision_agent, "_invoke_with_retry", wraps=decision_agent._invoke_with_retry) as invoke:
            invoke_request(request, request_state(request), llm)
        self.assertEqual(invoke.call_count, 2)
        self.assertIsNotNone(llm.budgets[0])
        self.assertIs(llm.budgets[0], llm.budgets[1])
        self.assertEqual(llm.prompts[0], llm.prompts[1])

    def test_semantic_request_validator_rejects_rehashed_prefix_visibility_or_source(self) -> None:
        request = self.request()
        for mutate in (lambda r:r.update(prefix=r["prefix"] + " fake"),
                       lambda r:r["trace"]["visible_metric_ids"].append("pattern_false_bullish_rate"),
                       lambda r:r["source"].update(bank_sha256="0" * 64)):
            changed = deepcopy(request)
            mutate(changed)
            changed["request_sha256"] = digest({k:v for k,v in changed.items() if k != "request_sha256"})
            with self.assertRaises(ValueError):
                validate_prior_request(changed, self.evidence, self.fx.retriever,
                    selector=self.query["selector"], query_features=self.query["query_features"])


class PriorPromptPointTests(unittest.TestCase):
    def test_actual_sealed_full_source_hook_and_builder_do_not_repeat_upstream(self) -> None:
        with patch("prior_context_test_support.pd.bdate_range", return_value=pd.bdate_range("2019-08-01", periods=700)):
            fx = ContextFixture()
        self.addCleanup(fx.close)
        for row in fx.records:
            row["regime"] = fx.regime["regime_name"]
        fx.publish_bank("a" * 64)
        adapter = fx.adapter()
        point = adapter.prepare("FPT", fx.cutoff)
        shared = point.bind_full(fx.full(point))
        before = deepcopy(shared)
        index = adapter.build_price_feature_index()
        evidence = point.quality_evidence(shared, index)
        request = build_prior_request(evidence, "C3", adapter._retriever,
            selector=adapter._price_example_selectors[index.identity], query_features=point.price_features())
        def prepare(state):
            point.verify_source(state)
            return deepcopy(state), request["prefix"]
        llm = FixtureLlm(decision_result(request))
        node = decision_agent.create_final_trade_decider(llm, _prior_preparer=prepare, _prior_request=request)
        with patch.object(point, "bind_full", side_effect=AssertionError("Không gọi lại Full")):
            output = node(deepcopy(shared))
        self.assertEqual(shared, before)
        self.assertEqual(output["prior_decision_trace"]["request"]["base_evidence_sha256"], evidence["base_evidence_sha256"])
        path = fx.root / "data/execution_prices/FPT.events.json"
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            node(deepcopy(shared))
        self.assertEqual(len(llm.prompts), 1)
