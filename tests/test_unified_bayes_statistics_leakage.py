"""Chặn target/future leakage và sửa evidence khi tính posterior/pooling U-BICL."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from core.historical_signals import digest
from core.unified_bayes_memory import build_memory
from core.unified_bayes_statistics import UnifiedBayesStatistics
from unified_memory_test_support import SIGNALS
from unified_pooling_test_support import statistics_inputs


class UnifiedStatisticsLeakageTests(unittest.TestCase):
    """Nguồn tổng hợp và poison target xác nhận việc lọc PIT diễn ra trước đếm nhãn."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.inputs = statistics_inputs()
        cls.memory = build_memory(**cls.inputs)
        cls.statistics = UnifiedBayesStatistics(cls.memory)
        cls.query = {"symbol": "FPT", "as_of_date": "2023-01-06", "current_regime": "BULL", "current_signals": SIGNALS}

    def test_self_equal_exit_and_future_outcomes_are_not_read(self) -> None:
        class Poison(dict):
            """Bất kỳ copy record tương lai nào đều làm test thất bại."""
            def __deepcopy__(self, memo: dict) -> dict:
                raise AssertionError("Đã đọc nhãn target/future")
        memory = build_memory(**self.inputs)
        statistics = UnifiedBayesStatistics(memory)
        expected = statistics.evidence(**self.query)
        for key, row in list(memory._records.items()):
            if row["symbol"] == "FPT" and row["exit_date"] >= self.query["as_of_date"]:
                memory._records[key] = Poison(row)
        self.assertEqual(statistics.evidence(**self.query), expected)

    def test_future_append_leaves_past_groups_and_all_posteriors_equal(self) -> None:
        inputs = deepcopy(self.inputs)
        inputs["imported"] = [row for row in inputs["imported"] if row["as_of_date"] < "2024-01-01"]
        smaller = UnifiedBayesStatistics(build_memory(**inputs)).evidence(**self.query)
        larger = self.statistics.evidence(**self.query)
        for key in ("groups", "counts", "posteriors", "reference_metrics"):
            self.assertEqual(smaller[key], larger[key])

    def test_declared_PIT_pool_with_self_or_other_symbol_raises_before_counts(self) -> None:
        rows = [self.memory._records["FPT:2023-01-03"]]
        for row in (rows[0], self.memory._records["MWG:2020-06-01"]):
            with patch.object(self.memory, "eligible", return_value=[deepcopy(row)]), self.assertRaises(ValueError):
                self.statistics.evidence(**self.query)

    def test_resealed_partition_counts_posterior_or_gate_cannot_pass_validation(self) -> None:
        original = self.statistics.evidence(**self.query)
        for change in ("group", "counts", "posterior", "gate"):
            evidence = deepcopy(original)
            if change == "group":
                evidence["groups"]["C"]["episode_ids"].append("future")
            elif change == "counts":
                evidence["counts"]["nC"] += 1
            elif change == "posterior":
                evidence["posteriors"]["A_tp_pool"]["posterior_mean"] = .99
            else:
                evidence["posteriors"]["A_tp_pool"]["gate"]["ready"] = True
            evidence.pop("evidence_sha256")
            evidence["evidence_sha256"] = digest(evidence)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.statistics.validate(evidence)

    def test_empty_conditional_stays_null_with_cross_regime_history(self) -> None:
        evidence = self.statistics.evidence(symbol="FPT", as_of_date="2021-01-04", current_regime="CONSOLIDATION", current_signals=SIGNALS)
        self.assertGreater(evidence["counts"]["n2"], 0)
        self.assertEqual(evidence["counts"]["nC"], 0)
        for item in evidence["posteriors"].values():
            self.assertIsNone(item["posterior_mean"])
            self.assertIsNone(item["credible_interval"])
            self.assertFalse(item["gate"]["ready"])

    def test_decision_feature_and_unknown_query_regime_are_rejected(self) -> None:
        for changes in ({"current_signals": {**SIGNALS, "confidence": .9}}, {"current_regime": "unknown"}):
            with self.assertRaises(ValueError):
                self.statistics.evidence(**(self.query | changes))

    def test_hot_statistics_does_not_read_files_extract_features_or_generate_target(self) -> None:
        with patch("pathlib.Path.read_bytes", side_effect=AssertionError("I/O")), \
             patch("pathlib.Path.read_text", side_effect=AssertionError("I/O")), \
             patch.object(self.memory.index, "prior_features", side_effect=AssertionError("feature filter")), \
             patch("core.historical_outcomes.HistoricalOutcomeGenerator.generate", side_effect=AssertionError("target")):
            self.statistics.evidence(**self.query)


if __name__ == "__main__":
    unittest.main()
