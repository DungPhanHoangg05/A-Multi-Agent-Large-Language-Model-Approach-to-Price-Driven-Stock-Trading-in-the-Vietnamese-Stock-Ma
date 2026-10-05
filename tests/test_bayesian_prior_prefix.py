"""Kiểm BRPP compact theo mẫu đã khóa, ý nghĩa kinh tế và validation đầu vào."""

import copy
import unittest
import unicodedata
from unittest.mock import patch

import numpy as np

from core.bayesian_memory import is_bullish, read_json
from core.bayesian_retriever import MODES, ROOT, format_compact_prior_prefix
import test_bayesian_statistics as fixtures


class CompactPriorPrefixTests(unittest.TestCase):
    def setUp(self):
        self.reference = read_json(ROOT / "docs/week3/statistics_prefix_review.json")
        self.stats = copy.deepcopy(self.reference["reference_stats"])
        self.tasks = [self.task("a", "BULLISH", "NEUTRAL", 1.25),
                      self.task("b", "BULLISH", "BULLISH", -1.25),
                      self.task("c", "BEARISH", "BULLISH", -1.25)]

    def task(self, identifier, trend, pattern, net, regime="BULL"):
        """Tạo task render giả lập; việc đối chiếu giá/cutoff vẫn thuộc retriever."""
        positive = net > 0
        return {"episode_id": identifier, "symbol": "FPT", "as_of_date": "2021-01-04",
                "entry_date": "2021-01-05", "exit_date": "2021-01-07", "regime": regime,
                "agent_signals": {"trend": trend, "pattern": pattern, "alpha_consensus": "BEARISH",
                                  "indicator_consensus": "NEUTRAL", "sentiment": "NEUTRAL"},
                "outcome": {"actual_direction": "UP" if positive else "DOWN", "net_return_pct": net,
                            "result": "WIN_IF_LONG" if positive else "LOSS_IF_LONG",
                            "was_bull_trap": (is_bullish(trend) or is_bullish(pattern)) and not positive}}

    def empty_stats(self, count=0, wins=0):
        metrics = {name: {"numerator": 0, "denominator": 0, "rate": None} for name in self.stats["metrics"]}
        metrics["win_rate_long"] = {"numerator": wins, "denominator": count,
                                    "rate": float(wins / count) if count else None}
        return {"regime": "BULL", "population_count": count, "metrics": metrics}

    def test_original_and_empty_population_match_frozen_reference(self):
        for tasks, stats, name in (([], None, "original_k0"), ([], self.empty_stats(), "empty_prior_n0")):
            prefix = format_compact_prior_prefix(tasks, stats)
            self.assertEqual(prefix, self.reference["prefix_examples"][name]["text"])
            self.assertEqual(len(prefix), self.reference["prefix_examples"][name]["length"])

    def test_k_1_2_3_matches_template_counts_and_economic_legend(self):
        for k in (1, 2, 3):
            prefix = format_compact_prior_prefix(self.tasks[:k], self.stats)
            self.assertEqual(prefix, self.reference["prefix_examples"][f"fixture_k{k}"]["text"])
            self.assertEqual(len(prefix.splitlines()), 3 + k)
            self.assertIn("n=4", prefix)
            self.assertIn("Trap=2/3(66.7%)", prefix)
            self.assertIn("W/L=LONG ròng sau phí; SHORT=tiền mặt; S=thiếu tin.", prefix)
            self.assertFalse(prefix.endswith("\n"))

    def test_no_bullish_and_zero_net_match_null_and_loss_references(self):
        task = self.task("a", "NEUTRAL", "NEUTRAL", 1.25)
        prefix = format_compact_prior_prefix([task], self.empty_stats(1, 1))
        self.assertEqual(prefix, self.reference["prefix_examples"]["no_bullish"]["text"])
        task = self.task("a", "NEUTRAL", "NEUTRAL", 0.0)
        prefix = format_compact_prior_prefix([task], self.empty_stats(1, 0))
        self.assertEqual(prefix, self.reference["prefix_examples"]["return_0.0"]["text"])

    def test_order_task_regime_and_actual_k_do_not_replace_population(self):
        tasks = copy.deepcopy(self.tasks[:2])
        tasks[0]["regime"] = "BEAR"
        tasks.reverse()
        prefix = format_compact_prior_prefix(tasks, self.stats)
        self.assertTrue(prefix.startswith("[BRPP v1] R=BULL; n=4; k=2\n"))
        self.assertTrue(prefix.splitlines()[3].endswith("++-0 L -1.25%"))
        self.assertIn("R=BEAR T/P/A/I=+0-0 W +1.25%", prefix.splitlines()[4])
        empty = format_compact_prior_prefix([], self.stats)
        self.assertIn("n=4; k=0", empty)
        self.assertIn("LONGwin=2/4(50.0%)", empty)
        other_regime = format_compact_prior_prefix([tasks[1]], self.empty_stats())
        self.assertIn("n=0; k=1", other_regime)

    def test_alias_nfc_determinism_and_input_independence(self):
        before = copy.deepcopy((self.tasks, self.stats))
        expected = format_compact_prior_prefix(self.tasks, self.stats)
        self.assertEqual((self.tasks, self.stats), before)
        self.assertEqual(format_compact_prior_prefix(self.tasks, self.stats), expected)
        self.tasks[0]["agent_signals"].update(trend=unicodedata.normalize("NFD", " tăng giá "),
                                            pattern="trung_tính", alpha_consensus="down", sentiment="trung tính")
        aliases = copy.deepcopy(self.tasks)
        self.assertEqual(format_compact_prior_prefix(self.tasks, self.stats), expected)
        self.assertEqual(self.tasks, aliases)
        self.assertTrue(unicodedata.is_normalized("NFC", expected))

    def test_percent_unit_sign_and_scientific_notation_are_preserved(self):
        for net, suffix in ((0.0, "L 0.00%"), (-0.0, "L 0.00%"), (0.001, "W +1.00e-03%"),
                            (-0.001, "L -1.00e-03%"), (0.005, "W +0.01%"),
                            (-0.005, "L -0.01%"), (1.25, "W +1.25%"), (-1.25, "L -1.25%"),
                            (10000.0, "W +1.00e+04%"), (1e308, "W +1.00e+308%"), (-1e308, "L -1.00e+308%")):
            with self.subTest(net=net):
                task = self.task("a", "NEUTRAL", "NEUTRAL", net)
                prefix = format_compact_prior_prefix([task], self.empty_stats(1, int(net > 0)))
                self.assertTrue(prefix.endswith(suffix), prefix)

    def test_invalid_stats_schema_types_counts_and_rates_raise(self):
        cases = [None, {**self.stats, "extra": 1}, {k: v for k, v in self.stats.items() if k != "regime"}]
        for value in (True, -1, 4.0, np.int64(4)):
            cases.append({**self.stats, "population_count": value})
        cases += [{**self.stats, "regime": v} for v in ("UNKNOWN", [], None)]
        for field, value in (("rate", 0), ("rate", np.float64(0.5)), ("rate", float("nan")),
                             ("rate", float("inf")), ("rate", 0.75), ("numerator", True),
                             ("numerator", -1), ("denominator", 5)):
            bad = copy.deepcopy(self.stats)
            bad["metrics"]["win_rate_long"][field] = value
            cases.append(bad)
        bad = self.empty_stats()
        bad["metrics"]["win_rate_long"]["rate"] = 0.0
        cases.append(bad)
        for stats in cases:
            with self.subTest(stats=stats), self.assertRaises(ValueError):
                format_compact_prior_prefix(self.tasks[:1], stats)

    def test_stats_win_union_and_trap_relationships_are_checked(self):
        for name, numerator, denominator in (("win_rate_long", 2, 3), ("bull_trap_rate", 3, 3),
                                             ("bull_trap_rate", 1, 3), ("trend_false_bullish_rate", 1, 4)):
            bad = copy.deepcopy(self.stats)
            bad["metrics"][name] = {"numerator": numerator, "denominator": denominator,
                                    "rate": float(numerator / denominator)}
            with self.subTest(name=name, numerator=numerator), self.assertRaises(ValueError):
                format_compact_prior_prefix([], bad)

    def test_task_schema_dates_labels_nonfinite_and_native_types_are_checked(self):
        cases = [{**self.tasks[0], "symbol": "UNKNOWN"}, {**self.tasks[0], "regime": "UNKNOWN"},
                 {**self.tasks[0], "episode_id": " "}, {**self.tasks[0], "as_of_date": "20210104"},
                 {**self.tasks[0], "entry_date": "2021-01-04"}, {**self.tasks[0], "exit_date": "2021-01-03"},
                 {**self.tasks[0], "extra": 1}, {}]
        for key, value in (("net_return_pct", True), ("net_return_pct", np.float64(1.25)),
                           ("net_return_pct", float("nan")), ("net_return_pct", float("inf")),
                           ("net_return_pct", 10**400), ("result", "LOSS_IF_LONG"),
                           ("actual_direction", "DOWN"), ("was_bull_trap", True), ("was_bull_trap", np.bool_(False))):
            bad = copy.deepcopy(self.tasks[0])
            bad["outcome"][key] = value
            cases.append(bad)
        for label in ("UNKNOWN", "BULLISH/BEARISH", "xu hướng tăng"):
            bad = copy.deepcopy(self.tasks[0])
            bad["agent_signals"]["trend"] = label
            cases.append(bad)
        for task in cases:
            with self.subTest(task=task), self.assertRaises(ValueError):
                format_compact_prior_prefix([task], self.stats)

    def test_wrong_container_duplicate_id_more_than_three_and_missing_stats_raise(self):
        for tasks, stats in ((tuple(self.tasks), self.stats), (None, self.stats),
                             ([self.tasks[0], self.tasks[0]], self.stats),
                             (self.tasks + [self.task("d", "NEUTRAL", "NEUTRAL", 1.25)], self.stats),
                             (self.tasks[:1], None)):
            with self.subTest(tasks=tasks), self.assertRaises(ValueError):
                format_compact_prior_prefix(tasks, stats)

    def test_missing_news_legend_cannot_be_used_with_news_signal(self):
        for label in ("POSITIVE", "NEGATIVE", "tích cực", "tiêu cực"):
            task = copy.deepcopy(self.tasks[0])
            task["agent_signals"]["sentiment"] = label
            with self.subTest(label=label), self.assertRaises(ValueError):
                format_compact_prior_prefix([task], self.stats)

    def test_overflow_is_error_instead_of_truncation_or_lost_examples(self):
        stats = copy.deepcopy(self.stats)
        stats["population_count"] = 10**100
        for name in stats["metrics"]:
            stats["metrics"][name] = {"numerator": 5 * 10**99, "denominator": 10**100, "rate": 0.5}
        with self.assertRaisesRegex(ValueError, "600"):
            format_compact_prior_prefix(self.tasks, stats)

    def test_formatter_accepts_validated_retrieval_without_io(self):
        fixture = fixtures.BayesianStatisticsTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        retriever = fixture.fixture.create()
        for mode in sorted(MODES):
            result = retriever.retrieve(**fixture.query(mode=mode))
            before = copy.deepcopy(result)
            with patch("core.bayesian_retriever.read_json", side_effect=AssertionError("Đọc JSON")), \
                 patch("pandas.read_csv", side_effect=AssertionError("Đọc giá")):
                prefix = format_compact_prior_prefix(result["tasks"], result["stats"])
            self.assertLessEqual(len(prefix), 600)
            self.assertEqual(result, before)
            self.assertIn("n=4; k=3", prefix)


if __name__ == "__main__":
    unittest.main()
