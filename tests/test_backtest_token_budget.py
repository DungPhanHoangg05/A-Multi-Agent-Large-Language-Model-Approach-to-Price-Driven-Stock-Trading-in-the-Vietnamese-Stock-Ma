"""Kiểm thử ngân sách token đầu vào cho benchmark 20 điểm."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.alpha_agent import create_alpha_agent
from agents import decision_agent
from agents.decision_agent import create_final_trade_decider, TradeDecisionOutput
from agents.indicator_agent import create_indicator_agent
from scripts.verify_prior_prompt_budget import report_fixture


class _CountingLlm:
    def __init__(self):
        self.calls = 0
        self.prompts = []

    def invoke(self, _messages):
        self.calls += 1
        self.prompts.append(_messages)
        return SimpleNamespace(
            content=(
                '{"decision":"LONG","forecast_horizon":"T+2.5",'
                '"confidence":"Trung bình","risk_reward_ratio":1.5,'
                '"evidence_for":"Xu hướng và động lượng đồng thuận.",'
                '"evidence_against":"Biến động còn cao.",'
                '"justification":"Xác suất tăng ròng cao hơn."}'
            )
        )


class _StructuredCountingLlm(_CountingLlm):
    """Giả lập binding structured; phân biệt call text và call có schema."""

    def __init__(self):
        super().__init__()
        self.structured_prompts = []

    def with_structured_output(self, schema, **kwargs):
        self.schema = schema
        self.options = kwargs
        return SimpleNamespace(invoke=self._invoke_structured)

    def _invoke_structured(self, prompt):
        self.structured_prompts.append(prompt)
        return {"parsed": TradeDecisionOutput(
            decision="LONG", forecast_horizon="T+2.5", confidence="Cao",
            risk_reward_ratio=1.5, evidence_for="Đồng thuận.",
            evidence_against="Biến động.", justification="Kỳ vọng lãi ròng.",
        ), "raw": SimpleNamespace(content="fixture"), "parsing_error": None}


def _budget_state(lang="vi", timeframe="1d", style="saturated", symbol="FPT",
                  has_alpha=True, has_sentiment=True):
    """Fixture giới hạn prompt; không là dữ liệu giá hoặc bằng chứng PIT."""
    reports = report_fixture(lang, style)
    if style == "short":
        reports = {name: f"{name.upper()}_BEGIN {name.upper()}_END" for name in reports}
    state = {"stock_name": symbol, "time_frame": timeframe, "language": lang,
             "is_backtest": True}
    for name, text in reports.items():
        if name == "alpha" and not has_alpha or name == "sentiment" and not has_sentiment:
            continue
        state[f"{name}_report"] = text
    return state


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
        self.assertLess(len(prompt), 6_500)
        self.assertIn("LONG", prompt)
        self.assertIn("SHORT", prompt)
        self.assertIn("Trend và Pattern cùng xác nhận xu hướng giảm", prompt)
        self.assertIn("ALPHA FACTORS ĐỊNH LƯỢNG", prompt)
        self.assertEqual(llm.calls, 1)

    def test_runtime_matrix_preserves_contract_caps_and_input(self):
        for lang in ("vi", "en"):
            for timeframe in ("1d", "1 ngày"):
                for symbol in ("FPT", "MWG", "VCB", "VNM"):
                    for has_alpha, has_sentiment in ((False, False), (True, False),
                                                     (False, True), (True, True)):
                        for style in ("short", "saturated", "structured"):
                            with self.subTest(lang=lang, timeframe=timeframe, symbol=symbol,
                                              alpha=has_alpha, sentiment=has_sentiment, style=style):
                                state = _budget_state(lang, timeframe, style, symbol,
                                                      has_alpha, has_sentiment)
                                before = deepcopy(state)
                                llm = _CountingLlm()
                                with patch("builtins.print"):
                                    result = create_final_trade_decider(llm)(state)
                                prompt = result["decision_prompt"]
                                self.assertEqual(llm.prompts, [prompt])
                                self.assertLess(len(prompt), 6500)
                                self.assertEqual(state, before)
                                for word in ("LONG", "SHORT", "Open", "Close", "CASH", "T+2.5", "3/5"):
                                    self.assertIn(word, prompt)
                                self.assertIn("0,25%" if lang == "vi" else "0.25%", prompt)
                                self.assertIn("0,10%" if lang == "vi" else "0.10%", prompt)
                                self.assertIn("Cổng xung đột" if lang == "vi" else "Conflict gate", prompt)
                                for name in ("trend", "pattern", "indicator"):
                                    self.assertIn(name.upper() + "_END", prompt)
                                if has_alpha:
                                    self.assertIn("ALPHA_END", prompt)
                                if has_sentiment:
                                    self.assertIn("SENTIMENT_END", prompt)
                                self.assertNotIn("BINH_LUAN_BO", prompt)
                                self.assertNotIn("BAI_BAO_BO", prompt)
                                self.assertNotIn("CHI_TIET_BO", prompt)

    def test_backtest_caps_are_separate_from_live_and_keep_report_endpoints(self):
        self.assertEqual(sum(decision_agent._BACKTEST_REPORT_CHAR_LIMITS.values()), 4000)
        self.assertEqual(sum(decision_agent._REPORT_CHAR_LIMITS.values()), 4500)
        for lang in ("vi", "en"):
            for name, text in report_fixture(lang).items():
                capped = decision_agent._distill_report(
                    name, text, lang, report_limits=decision_agent._BACKTEST_REPORT_CHAR_LIMITS)
                self.assertLessEqual(len(capped), decision_agent._BACKTEST_REPORT_CHAR_LIMITS[name])
                self.assertIn(name.upper() + "_BEGIN", capped)
                self.assertIn(name.upper() + "_END", capped)
                self.assertEqual(len(decision_agent._distill_report(name, text, lang)),
                                 decision_agent._REPORT_CHAR_LIMITS[name])

    def test_missing_reports_do_not_create_extra_report_sections(self):
        for lang in ("vi", "en"):
            for reports in ({}, {"alpha_report": None, "sentiment_report": ""},
                            {"alpha_report": "Không có dữ liệu.", "sentiment_report": "No data."}):
                llm = _CountingLlm()
                state = {"is_backtest": True, "stock_name": "FPT", "time_frame": "1d",
                         "language": lang, **reports}
                with patch("builtins.print"):
                    prompt = create_final_trade_decider(llm)(state)["decision_prompt"]
                self.assertNotIn("### [4]", prompt)
                self.assertNotIn("### [5]", prompt)
                self.assertLess(len(prompt), 6500)

    def test_real_builder_accepts_6499_and_rejects_6500_before_any_llm(self):
        for lang in ("vi", "en"):
            for structured in (False, True):
                for target in (6499, 6500):
                    with self.subTest(lang=lang, structured=structured, target=target):
                        llm = _StructuredCountingLlm() if structured else _CountingLlm()
                        node = create_final_trade_decider(llm)
                        state = _budget_state(lang, style="short")
                        with patch("builtins.print"):
                            base = node(state)["decision_prompt"]
                        llm.calls = 0
                        llm.prompts.clear()
                        if structured:
                            llm.structured_prompts.clear()
                        state["stock_name"] += "Đ" * (target - len(base))
                        with (patch("builtins.print"),
                              patch.object(decision_agent, "_invoke_with_retry",
                                           wraps=decision_agent._invoke_with_retry) as invoke):
                            if target == 6499:
                                result = node(state)
                                self.assertEqual(len(result["decision_prompt"]), 6499)
                                invoke.assert_called_once()
                            else:
                                with self.assertRaisesRegex(ValueError, "prompt=6500.*<6500"):
                                    node(state)
                                invoke.assert_not_called()
                        self.assertEqual(llm.calls, int(target == 6499 and not structured))
                        if structured:
                            self.assertEqual(len(llm.structured_prompts), int(target == 6499))

    def test_final_guard_includes_builder_extensions_and_full_600_reserve(self):
        # Mô phỏng template thêm BRPP/hướng dẫn; formatter và chèn runtime thuộc W4-07.
        for lang in ("vi", "en"):
            for timeframe in ("1d", "1 ngày"):
                build_name = f"_build_compact_prompt_{lang}"
                original = getattr(decision_agent, build_name)
                for extra in (600, 2000):
                    def extended(*args, _extra=extra):
                        head, marker, tail = original(*args).partition("### [1]")
                        return head + "Đ" * _extra + "\n" + marker + tail

                    llm = _CountingLlm()
                    with (patch.object(decision_agent, build_name, extended),
                          patch("builtins.print"),
                          patch.object(decision_agent, "_invoke_with_retry",
                                       wraps=decision_agent._invoke_with_retry) as invoke):
                        if extra == 600:
                            result = create_final_trade_decider(llm)(_budget_state(lang, timeframe))
                            self.assertIn("Đ" * 600, result["decision_prompt"])
                            self.assertLess(len(result["decision_prompt"]), 6500)
                            invoke.assert_called_once()
                        else:
                            with self.assertRaisesRegex(ValueError, "vượt ngân sách"):
                                create_final_trade_decider(llm)(_budget_state(lang, timeframe))
                            invoke.assert_not_called()
                    self.assertEqual(llm.calls, int(extra == 600))

    def test_budget_logs_report_caps_prefix_and_final_length(self):
        llm = _CountingLlm()
        with patch("builtins.print") as log:
            result = create_final_trade_decider(llm)(_budget_state())
        messages = "\n".join(str(call.args[0]) for call in log.call_args_list)
        self.assertIn("cap=", messages)
        self.assertIn("report=", messages)
        self.assertIn("prefix=0", messages)
        self.assertIn(f"prompt={len(result['decision_prompt'])}", messages)
        self.assertIn("<6500", messages)
        self.assertNotIn("7500", messages)

    def test_structured_and_text_format_retries_use_same_guarded_prompt(self):
        for structured in (False, True):
            llm = _StructuredCountingLlm() if structured else _CountingLlm()
            calls = []
            original = llm._invoke_structured if structured else llm.invoke

            def invalid_then_valid(prompt):
                calls.append(prompt)
                if len(calls) == 1:
                    if structured:
                        return {"parsed": None, "parsing_error": ValueError("fixture"), "raw": None}
                    return SimpleNamespace(content='{"decision":"NEUTRAL"}')
                return original(prompt)

            if structured:
                llm._invoke_structured = invalid_then_valid
            else:
                llm.invoke = invalid_then_valid
            with patch("builtins.print"):
                result = create_final_trade_decider(llm)(_budget_state())
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls, [result["decision_prompt"]] * 2)
            self.assertLess(len(calls[0]), 6500)
            self.assertEqual(json.loads(result["final_trade_decision"])["decision"], "LONG")

    def test_live_builder_keeps_old_caps_and_is_not_subject_to_backtest_guard(self):
        for lang in ("vi", "en"):
            llm = _CountingLlm()
            state = _budget_state(lang)
            state["is_backtest"] = False
            with (patch("builtins.print"), patch.object(decision_agent, "_guard_backtest_prompt") as guard,
                  patch.object(decision_agent, "_distill_report", wraps=decision_agent._distill_report) as distill):
                result = create_final_trade_decider(llm)(state)
            guard.assert_not_called()
            self.assertTrue(all(call.kwargs["report_limits"] is decision_agent._REPORT_CHAR_LIMITS
                                for call in distill.call_args_list))
            self.assertGreater(len(result["decision_prompt"]), 6500)
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
