"""Chống future/outcome query và đếm thiếu/trùng population trong thống kê."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from core.prior_example_selection import PriceExampleSelector
from prior_price_similarity_support import PriceSimilarityFixture
from test_prior_conditional_statistics import statistics_query


class ConditionalStatisticsLeakageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fx=PriceSimilarityFixture()
        self.addCleanup(self.fx.close)

    def test_future_equal_exit_and_other_symbol_regime_excluded_before_counting(self) -> None:
        query=statistics_query(self.fx)
        result=self.fx.retriever.conditional_statistics(**query)
        ids=result["groups"]["population"]["episode_ids"]
        self.assertNotIn("FPT:2022-01-03",ids)
        self.assertNotIn("FPT:2022-01-06",ids)
        self.assertNotIn("FPT:2020-06-09",ids)
        self.assertTrue(all(key.startswith("FPT:") for key in ids))
        pool=self.fx.retriever.prepare_query(**query)
        invalid=next(r for r in self.fx.records if r["episode_id"]=="FPT:2022-01-03")
        for rows in ([invalid],pool["regime_population"]*2,pool["regime_population"][:-1]):
            with (patch.object(self.fx.retriever,"prepare_query",return_value={**pool,"regime_population":rows}),
                  patch.object(self.fx.retriever,"_compute_statistics",side_effect=AssertionError("Không đếm pool sai")),
                  self.assertRaises(ValueError)):
                self.fx.retriever.conditional_statistics(**query)

    def test_future_then_past_and_reverse_input_are_deterministic(self) -> None:
        query=statistics_query(self.fx,cutoff="2021-01-04")
        before=self.fx.retriever.conditional_statistics(**query)
        self.fx.retriever.conditional_statistics(**statistics_query(self.fx))
        self.fx.retriever._memory._records.reverse()
        self.assertEqual(self.fx.retriever.conditional_statistics(**query),before)

    def test_future_outcomes_not_read_or_used_in_hyperprior(self) -> None:
        query=statistics_query(self.fx,cutoff="2021-01-04")
        before=self.fx.retriever.conditional_statistics(**query)
        class ForbiddenOutcome(dict):
            """Bẫy đọc nhãn tương lai; chỉ tiêm vào RAM, không xuất bank."""
            def __getitem__(self,key):raise AssertionError("Không được đọc outcome tương lai")
        for source in (self.fx.retriever._memory._records,self.fx.retriever._verified_by_id.values()):
            for row in source:
                if row["exit_date"]>=query["as_of_date"]:row["outcome"]=ForbiddenOutcome()
        self.assertEqual(self.fx.retriever.conditional_statistics(**query),before)

    def test_examples_k_quality_and_feature_status_never_change_statistics(self) -> None:
        query=statistics_query(self.fx)
        before=self.fx.retriever.conditional_statistics(**query)
        price_query=self.fx.query();price_query.pop("index")
        selector=PriceExampleSelector(self.fx.index,self.fx.inputs["calendar"])
        for config in ({"requested_k":1},{"min_gap_sessions":1000},{"min_similarity":1.},{"max_prior_age_days":0}):
            self.fx.retriever.select_price_examples(selector=selector,**price_query,config=config)
            self.assertEqual(self.fx.retriever.conditional_statistics(**query),before)
        self.assertIn("FPT:2020-06-12",before["groups"]["conditional"]["episode_ids"])

    def test_query_outcome_k_and_invalid_signals_cannot_enter_statistics(self) -> None:
        query=statistics_query(self.fx)
        for extra in ({"outcome":"WIN"},{"net_return_pct":1.},{"requested_k":0},{"scope":"cross_symbol"},{"query_features":{}}):
            with self.assertRaises(ValueError):self.fx.retriever.conditional_statistics(**query,**extra)
        for changed in ({"pattern":"unknown"},{"alpha_consensus":None}):
            with self.assertRaises(ValueError):
                self.fx.retriever.conditional_statistics(**{**query,"current_signals":{**query["current_signals"],**changed}})
        empty=self.fx.retriever.conditional_statistics(**statistics_query(self.fx,regime="CHOPPY"))
        self.assertEqual(empty["population_count"],0)
        self.assertTrue(all(m["posterior_mean"] is None for m in empty["metrics"].values()))
