"""Kiểm thống kê thực nghiệm bằng fixture giá và nhãn kinh tế được xác minh thật."""

import copy
import json
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from core.backtest_engine import compute_round_trip_net_return
from core.bayesian_memory import is_bullish, read_json
from core.bayesian_retriever import MODES, ROOT
import test_bayesian_retriever as fixtures


class BayesianStatisticsTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.BayesianRetrieverFoundationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.frame = pd.DataFrame({"Datetime": pd.bdate_range("2020-01-01", periods=18),
            "Open": 100.0, "High": 103.0, "Low": 99.0, "Close": 100.0,
            "Volume": 1000, "Reference": 100.0})
        self.fixture.frame.loc[[3, 12], "Close"] = 102.0
        self.fixture.frame["High"] = 103.0
        self.fixture.frame["Reference"] = self.fixture.frame["Close"].shift().fillna(100.0)
        self.fixture.rows = [self.record("FPT", pos, "BULL", trend, pattern)
            for pos, trend, pattern in ((0, "BULLISH", "NEUTRAL"), (3, "BULLISH", "BULLISH"),
                                       (6, "BEARISH", "BULLISH"), (9, "NEUTRAL", "NEUTRAL"))]
        self.fixture.rows += [self.record("MWG", 0, "BULL", "BULLISH", "NEUTRAL"),
                              self.record("FPT", 12, "BEAR", "BULLISH", "NEUTRAL")]
        self.fixture.publish_fixture()

    def record(self, symbol, position, regime, trend, pattern):
        """Dùng đúng engine để nhãn WIN/LOSS/trap khớp giá giả lập sau phí."""
        row = self.fixture.record(symbol, position, regime)
        row["agent_signals"].update(trend=trend, pattern=pattern)
        net = float(100 * compute_round_trip_net_return(100.0, float(self.fixture.frame.Close.iloc[position + 3])))
        row["outcome"] = {"actual_direction": "UP" if net > 0 else "DOWN", "net_return_pct": net,
                          "was_bull_trap": (is_bullish(trend) or is_bullish(pattern)) and net <= 0,
                          "result": "WIN_IF_LONG" if net > 0 else "LOSS_IF_LONG"}
        return row

    def query(self, **updates):
        return self.fixture.query(**{"as_of_date": "2020-02-01", **updates})

    def test_hand_reference_shared_across_all_modes_k_and_selection(self):
        retriever = self.fixture.create()
        reference = read_json(ROOT / "docs/week3/statistics_prefix_review.json")["reference_stats"]
        selections = set()
        for mode in sorted(MODES):
            for k in (1, 2, 3):
                result = retriever.retrieve(**self.query(mode=mode, k=k))
                self.assertEqual(result["stats"], reference)
                self.assertEqual(set(result), {"tasks", "stats", "metadata"})
                self.assertEqual(len(result["tasks"]), k)
                self.assertEqual(result["metadata"]["matched_regime_count"], 4)
                self.assertEqual(result["metadata"]["eligible_count"], 5)
                selections.add(tuple(result["metadata"]["selected_ids"]))
        self.assertGreater(len(selections), 3)

    def test_scope_and_regime_use_distinct_populations_with_correct_denominators(self):
        retriever = self.fixture.create()
        pooled = retriever.retrieve(**self.query(scope="pooled"))["stats"]
        self.assertEqual(pooled["population_count"], 5)
        self.assertEqual(pooled["metrics"]["win_rate_long"], {"numerator": 3, "denominator": 5, "rate": 0.6})
        self.assertEqual(pooled["metrics"]["bull_trap_rate"], {"numerator": 2, "denominator": 4, "rate": 0.5})
        bear = retriever.retrieve(**self.query(current_regime="BEAR"))["stats"]
        self.assertEqual(bear["population_count"], 1)
        self.assertEqual(bear["metrics"]["win_rate_long"], {"numerator": 0, "denominator": 1, "rate": 0.0})
        self.assertEqual(bear["metrics"]["bull_trap_rate"], {"numerator": 1, "denominator": 1, "rate": 1.0})

    def test_empty_population_is_object_with_null_rates_even_when_control_has_tasks(self):
        retriever = self.fixture.create()
        for mode in sorted(MODES):
            for cutoff, regime in (("2020-01-06", "BULL"), ("2020-02-01", "CHOPPY")):
                result = retriever.retrieve(**self.query(mode=mode, as_of_date=cutoff, current_regime=regime))
                self.assertEqual(result["stats"]["population_count"], 0)
                self.assertEqual(result["stats"]["regime"], regime)
                self.assertTrue(all(item == {"numerator": 0, "denominator": 0, "rate": None}
                                    for item in result["stats"]["metrics"].values()))
                if cutoff == "2020-02-01":
                    self.assertEqual(len(result["tasks"]), 0 if mode == "bayesian_regime" else 3)
                json.dumps(result, allow_nan=False)

    def test_no_bullish_preserves_win_rate_but_three_rates_are_null(self):
        for row in self.fixture.rows:
            row["agent_signals"].update(trend="BEARISH", pattern="NEUTRAL")
            row["outcome"]["was_bull_trap"] = False
        self.fixture.publish_fixture()
        result = self.fixture.create().retrieve(**self.query())["stats"]
        self.assertEqual(result["metrics"]["win_rate_long"], {"numerator": 2, "denominator": 4, "rate": 0.5})
        for name in ("bull_trap_rate", "trend_false_bullish_rate", "pattern_false_bullish_rate"):
            self.assertEqual(result["metrics"][name], {"numerator": 0, "denominator": 0, "rate": None})

    def test_zero_net_return_is_loss_and_trap_without_smoothing(self):
        entry = 100.0
        exit_close = entry * (1 + 0.001) * (1 + 0.0025) / ((1 - 0.001) * (1 - 0.0025))
        self.assertEqual(compute_round_trip_net_return(entry, exit_close), 0.0)
        self.fixture.frame.loc[3, "Close"] = exit_close
        self.fixture.frame["Reference"] = self.fixture.frame["Close"].shift().fillna(100.0)
        self.fixture.rows = [self.record("FPT", 0, "BULL", "BULLISH", "BULLISH"),
                             self.record("MWG", 0, "BULL", "BULLISH", "BULLISH")]
        self.fixture.publish_fixture()
        stats = self.fixture.create().retrieve(**self.query())["stats"]
        self.assertEqual(stats["metrics"]["win_rate_long"], {"numerator": 0, "denominator": 1, "rate": 0.0})
        self.assertEqual(stats["metrics"]["bull_trap_rate"], {"numerator": 1, "denominator": 1, "rate": 1.0})

    def test_aliases_are_normalized_and_raw_bank_is_unchanged(self):
        for row in self.fixture.rows:
            for name in ("trend", "pattern"):
                row["agent_signals"][name] = {"BULLISH": " tăng giá ", "BEARISH": "down", "NEUTRAL": "trung_tính"}[row["agent_signals"][name]]
        self.fixture.publish_fixture()
        original = copy.deepcopy(self.fixture.rows)
        stats = self.fixture.create().retrieve(**self.query())["stats"]
        self.assertEqual(stats, read_json(ROOT / "docs/week3/statistics_prefix_review.json")["reference_stats"])
        self.assertEqual(self.fixture.rows, original)

    def test_zero_k_does_not_build_population_or_compute_statistics_in_any_mode(self):
        retriever = self.fixture.create()
        with patch.object(retriever._memory, "eligible", side_effect=AssertionError("Tạo pool K=0")), \
             patch.object(retriever, "_compute_statistics", side_effect=AssertionError("Tính stats K=0")):
            for mode in sorted(MODES):
                result = retriever.retrieve(**self.query(mode=mode, k=0, current_signals=None))
                self.assertEqual(result["tasks"], [])
                self.assertIsNone(result["stats"])
                self.assertEqual(result["metadata"]["status"], "disabled")
        with self.assertRaises(ValueError):
            retriever.retrieve(**self.query(k=0, symbol="UNKNOWN"))

    def test_native_json_exact_schema_and_counts_relationships(self):
        result = self.fixture.create().retrieve(**self.query())
        stats = result["stats"]
        self.assertEqual(set(stats), {"regime", "population_count", "metrics"})
        self.assertEqual(set(stats["metrics"]), {"win_rate_long", "bull_trap_rate", "trend_false_bullish_rate", "pattern_false_bullish_rate"})
        self.assertIs(type(stats["population_count"]), int)
        for item in stats["metrics"].values():
            self.assertEqual(set(item), {"numerator", "denominator", "rate"})
            self.assertIs(type(item["numerator"]), int)
            self.assertIs(type(item["denominator"]), int)
            self.assertIs(type(item["rate"]), float)
            self.assertLessEqual(item["numerator"], item["denominator"])
            self.assertLessEqual(item["denominator"], stats["population_count"])
            self.assertAlmostEqual(item["rate"], item["numerator"] / item["denominator"], delta=1e-12)
        self.assertEqual(json.loads(json.dumps(result, allow_nan=False)), result)

    def test_retrieve_deep_copies_and_no_hot_query_io_or_repeated_pool_load(self):
        retriever = self.fixture.create()
        query = self.query()
        original = copy.deepcopy(query)
        with patch("core.bayesian_retriever.read_json", side_effect=AssertionError("Đọc JSON")), \
             patch("core.bayesian_memory.read_json", side_effect=AssertionError("Đọc JSON")), \
             patch("pandas.read_csv", side_effect=AssertionError("Đọc CSV")), \
             patch.object(retriever._memory, "_execution_loader", side_effect=AssertionError("Đọc giá")), \
             patch.object(retriever._memory, "eligible", wraps=retriever._memory.eligible) as eligible:
            expected = retriever.retrieve(**query)
            self.assertEqual(eligible.call_count, 1)
            altered = retriever.retrieve(**query)
            altered["stats"]["metrics"]["win_rate_long"]["rate"] = 999
            altered["tasks"][0]["agent_signals"]["trend"] = "BEARISH"
            altered["metadata"]["selected_ids"].clear()
            self.assertEqual(retriever.retrieve(**query), expected)
        self.assertEqual(query, original)

    def test_statistics_guard_rejects_corrupt_populations_and_trap_labels(self):
        retriever = self.fixture.create()
        population = retriever.prepare_query(**self.query())["regime_population"]
        corrupt = copy.deepcopy(population)
        corrupt[0]["outcome"]["was_bull_trap"] = True
        numpy_row = copy.deepcopy(population[0])
        numpy_row["outcome"]["was_bull_trap"] = np.bool_(False)
        for rows in (corrupt, [numpy_row], [population[0], population[0]], [self.fixture.rows[-1]], [self.fixture.rows[-2]]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                retriever._compute_statistics(rows, symbol="FPT", as_of_date="2020-02-01", current_regime="BULL", scope="same_symbol")
        with patch.object(retriever, "_assert_pool"), self.assertRaises(ValueError):
            retriever._compute_statistics(corrupt, symbol="FPT", as_of_date="2020-02-01", current_regime="BULL", scope="same_symbol")

    def test_retrieve_rejects_population_count_mismatch(self):
        retriever = self.fixture.create()
        selected = retriever.select_prior_tasks(**self.query())
        for count in (True, 3, 4.0):
            selected["metadata"]["matched_regime_count"] = count
            with patch.object(retriever, "select_prior_tasks", return_value=selected), self.assertRaises(ValueError):
                retriever.retrieve(**self.query())


if __name__ == "__main__":
    unittest.main()
