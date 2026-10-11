"""Gate không che lỗi PIT, không dùng outcome query hay đọc lại tương lai."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from prior_price_similarity_support import PriceSimilarityFixture
from test_prior_quality_gate import gate_query


class QualityGateLeakageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = PriceSimilarityFixture()
        self.addCleanup(self.fx.close)

    def test_invalid_population_raises_before_gate_even_if_support_is_low(self) -> None:
        query = gate_query(self.fx)
        pool = self.fx.retriever.prepare_query(**{k:query[k] for k in
            ("symbol", "as_of_date", "current_regime", "current_signals")})
        future = next(row for row in self.fx.records if row["episode_id"] == "FPT:2022-01-03")
        for rows in ([future], pool["regime_population"] * 2, pool["regime_population"][:-1]):
            with (patch.object(self.fx.retriever, "prepare_query", return_value={**pool, "regime_population": rows}),
                  self.assertRaises(ValueError)):
                self.fx.retriever.quality_evidence(**query)

    def test_future_equal_exit_excluded_and_query_outcome_rejected(self) -> None:
        query = gate_query(self.fx)
        evidence = self.fx.retriever.quality_evidence(**query)
        ids = evidence["statistics"]["groups"]["population"]["episode_ids"]
        self.assertNotIn("FPT:2022-01-03", ids)
        self.assertNotIn("FPT:2022-01-06", ids)
        for extra in ({"outcome": "LOSS"}, {"net_return_pct": -5.}, {"exit_date": "2022-01-10"}):
            with self.assertRaises(ValueError):
                self.fx.retriever.quality_evidence(**query, **extra)

    def test_future_then_past_keeps_base_hash_and_no_future_outcome_reads(self) -> None:
        query = gate_query(self.fx, cutoff="2021-01-04")
        before = self.fx.retriever.quality_evidence(**query)
        self.fx.retriever.quality_evidence(**gate_query(self.fx))
        class ForbiddenOutcome(dict):
            """Bẫy chỉ ở RAM, không sửa bank đóng băng."""
            def __getitem__(self, key):
                raise AssertionError("Không đọc nhãn tương lai")
        for source in (self.fx.retriever._memory._records, self.fx.retriever._verified_by_id.values()):
            for row in source:
                if row["exit_date"] >= query["as_of_date"]:
                    row["outcome"] = ForbiddenOutcome()
        self.assertEqual(self.fx.retriever.quality_evidence(**query), before)

    def test_stats_examples_population_mismatch_is_error_not_fallback(self) -> None:
        query = gate_query(self.fx)
        selection = self.fx.retriever.select_price_examples(**query)
        changed = deepcopy(selection)
        changed["regime_population"].pop()
        with (patch.object(self.fx.retriever, "select_price_examples", return_value=changed), self.assertRaises(ValueError)):
            self.fx.retriever.quality_evidence(**query)
