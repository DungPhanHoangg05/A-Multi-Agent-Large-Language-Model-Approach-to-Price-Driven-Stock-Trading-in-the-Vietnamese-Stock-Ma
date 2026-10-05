"""Kiểm trần BRPP, prompt ghép VI/EN và ngân sách bàn giao W4 bằng builder thật."""

import copy
import math
import unittest
import unicodedata
from unittest.mock import patch

from agents import decision_agent
from core.bayesian_retriever import REGIMES, format_compact_prior_prefix
from scripts.verify_prior_prompt_budget import (
    HANDOFF_REPORT_CHAR_LIMITS, build_fixture_prompt, prefix_fixture, report_fixture, verify_budget,
)


class PriorPromptBudgetTests(unittest.TestCase):
    """Xác minh ngân sách formatter và cấu hình prompt bàn giao, không chạy API."""

    def test_all_regimes_k_0_3_extreme_returns_and_many_digit_counts(self) -> None:
        for regime in sorted(REGIMES):
            for k in (0, 1, 2, 3):
                for count in (852, 10**12):
                    for net in (0.0, -0.0, 0.004999, -0.004999, 0.005, -0.005,
                                9999.99, 10000.0, 1e308, -1e308, math.nextafter(0.0, 1.0)):
                        tasks, stats = prefix_fixture(regime, k, count)
                        for task in tasks:
                            positive = net > 0
                            task["outcome"].update(net_return_pct=net, actual_direction="UP" if positive else "DOWN",
                                result="WIN_IF_LONG" if positive else "LOSS_IF_LONG", was_bull_trap=not positive)
                        before = copy.deepcopy((tasks, stats))
                        prefix = format_compact_prior_prefix(tasks, stats)
                        self.assertLessEqual(len(prefix), 600)
                        self.assertEqual(len(prefix.splitlines()), 0 if k == 0 else 3 + k)
                        self.assertEqual((tasks, stats), before)
                        self.assertEqual(format_compact_prior_prefix(tasks, stats), prefix)

    def test_exactly_600_accepted_next_larger_fixture_rejected_without_dropping_examples(self) -> None:
        tasks, stats = prefix_fixture(population=10**25)
        prefix = format_compact_prior_prefix(tasks, stats)
        self.assertEqual(len(prefix), 600)
        self.assertEqual(len(prefix.splitlines()), 6)
        tasks, stats = prefix_fixture(population=10**26)
        before = copy.deepcopy((tasks, stats))
        with self.assertRaisesRegex(ValueError, "600"):
            format_compact_prior_prefix(tasks, stats)
        self.assertEqual((tasks, stats), before)

    def test_long_ids_unicode_aliases_do_not_expand_or_corrupt_prefix(self) -> None:
        tasks, stats = prefix_fixture()
        canonical = format_compact_prior_prefix(tasks, stats)
        for i, task in enumerate(tasks):
            task["episode_id"] = str(i) + "Định danh nghiên cứu " * 1000
            task["agent_signals"].update(trend=unicodedata.normalize("NFD", " tăng giá "),
                pattern="UP", alpha_consensus="giảm giá", indicator_consensus="trung_tính", sentiment="trung tính")
        before = copy.deepcopy(tasks)
        result = format_compact_prior_prefix(tasks, stats)
        self.assertEqual(result, canonical)
        self.assertTrue(unicodedata.is_normalized("NFC", result))
        self.assertGreater(len(result.encode("utf-8")), len(result))
        self.assertEqual(tasks, before)

    def test_empty_stats_no_bullish_and_no_examples_assemble_in_both_languages(self) -> None:
        metrics = {name: {"numerator": 0, "denominator": 0, "rate": None}
                   for name in prefix_fixture()[1]["metrics"]}
        for count in (0, 852):
            stats = {"regime": "CONSOLIDATION", "population_count": count, "metrics": copy.deepcopy(metrics)}
            stats["metrics"]["win_rate_long"] = {"numerator": count // 2, "denominator": count,
                                                 "rate": 0.5 if count else None}
            prefix = format_compact_prior_prefix([], stats)
            self.assertIn("k=0", prefix)
            self.assertIn("Trap=0/0(N/A)", prefix)
            for lang in ("vi", "en"):
                prompt, _ = build_fixture_prompt(report_fixture(lang), prefix, lang=lang,
                                                 report_limits=HANDOFF_REPORT_CHAR_LIMITS)
                self.assertLess(len(prompt), 6500)

    def test_legacy_saturated_reports_exceed_6500_and_are_not_reported_as_pass(self) -> None:
        tasks, stats = prefix_fixture()
        prefix = format_compact_prior_prefix(tasks, stats)
        for lang, expected in (("vi", 6565), ("en", 6582)):
            prompt, reports = build_fixture_prompt(report_fixture(lang), prefix, lang=lang)
            self.assertEqual(len(prompt), expected)
            self.assertGreaterEqual(len(prompt), 6500)
            self.assertEqual(sum(map(len, reports.values())), 4500)

    def test_real_builders_share_original_or_insert_prior_before_reports_with_economic_contract(self) -> None:
        tasks, stats = prefix_fixture()
        prefix = format_compact_prior_prefix(tasks, stats)
        for lang in ("vi", "en"):
            raw = report_fixture(lang)
            original, _ = build_fixture_prompt(raw, "", lang=lang, report_limits=HANDOFF_REPORT_CHAR_LIMITS)
            prior, _ = build_fixture_prompt(raw, prefix, lang=lang, report_limits=HANDOFF_REPORT_CHAR_LIMITS)
            self.assertEqual(prior.replace(prefix + "\n", "", 1), original)
            self.assertEqual(len(prior), len(original) + len(prefix) + 1)
            self.assertLess(prior.index("[BRPP v1]"), prior.index("### [1]"))
            self.assertEqual(prior.count("[BRPP v1]"), 1)
            for text in ("LONG", "SHORT", "Open", "Close", "CASH", "T+2.5", "3/5"):
                self.assertIn(text, prior)
            self.assertIn("0,25%" if lang == "vi" else "0.25%", prior)
            self.assertIn("0,10%" if lang == "vi" else "0.10%", prior)
            self.assertIn("Cổng xung đột" if lang == "vi" else "Conflict gate", prior)

    def test_report_distill_cap_preserve_endpoints_and_remove_discarded_detail(self) -> None:
        for lang in ("vi", "en"):
            raw = report_fixture(lang, "structured")
            before = copy.deepcopy(raw)
            _, reports = build_fixture_prompt(raw, "", lang=lang, report_limits=HANDOFF_REPORT_CHAR_LIMITS)
            for name, text in reports.items():
                self.assertLessEqual(len(text), HANDOFF_REPORT_CHAR_LIMITS[name])
                self.assertIn(name.upper() + "_END", text)
            self.assertNotIn("CHI_TIET_BO", reports["indicator"])
            self.assertNotIn("BINH_LUAN_BO", reports["alpha"])
            self.assertNotIn("BAI_BAO_BO", reports["sentiment"])
            self.assertEqual(raw, before)

    def test_full_handoff_matrix_reserves_600_and_restores_runtime_caps_without_llm(self) -> None:
        caps_before = copy.deepcopy(decision_agent._REPORT_CHAR_LIMITS)
        with patch.object(decision_agent, "_invoke_with_retry", side_effect=AssertionError("Gọi LLM")), \
             patch.object(decision_agent, "create_final_trade_decider", side_effect=AssertionError("Chạy node")):
            receipt = verify_budget()
        self.assertEqual(receipt["matrix_case_count"], 1024)
        self.assertLess(receipt["matrix_max_prompt_length"], 6500)
        self.assertEqual(receipt["handoff_total_report_budget"], 4000)
        self.assertEqual(receipt["status"], "PASS_WITH_REQUIRED_W4_HANDOFF")
        self.assertFalse(receipt["runtime_budget_gate_passed"])
        self.assertFalse(receipt["runtime_decision_changed"])
        self.assertTrue(all(not r["within_limit"] for r in receipt["legacy_saturated_findings"]))
        self.assertTrue(all(r["prefix_length"] == 600 and r["prompt_length"] < 6500
                            for r in receipt["full_600_character_reserve"]))
        self.assertEqual(decision_agent._REPORT_CHAR_LIMITS, caps_before)

    def test_ambiguous_labels_nan_and_k_over_3_fail_before_prompt_assembly(self) -> None:
        tasks, stats = prefix_fixture()
        bad_tasks = copy.deepcopy(tasks)
        bad_tasks[0]["agent_signals"]["trend"] = "BULLISH hoặc BEARISH"
        bad_stats = copy.deepcopy(stats)
        bad_stats["metrics"]["win_rate_long"]["rate"] = float("nan")
        for bad_input in ((bad_tasks, stats), (tasks, bad_stats), (tasks + [copy.deepcopy(tasks[0])], stats)):
            with self.assertRaises(ValueError):
                format_compact_prior_prefix(*bad_input)


if __name__ == "__main__":
    unittest.main()
