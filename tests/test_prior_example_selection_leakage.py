"""Policy ví dụ độc lập outcome/K/population và bất biến dữ liệu tương lai."""

from copy import deepcopy
import unittest
from unittest.mock import patch

import pandas as pd

from core.prior_example_selection import PriceExampleSelector, _select_trace, selection_config
from core.price_feature_index import build_price_feature_index
from prior_price_similarity_support import PriceSimilarityFixture
from test_prior_example_selection import query_for, trace_row


class ExampleSelectionLeakageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fx=PriceSimilarityFixture()
        self.addCleanup(self.fx.close)

    def test_label_permutation_changes_content_only_not_selection(self) -> None:
        query=query_for(self.fx);before=self.fx.retriever.select_price_examples(**query)
        records=deepcopy(self.fx.retriever._memory._records)
        self.assertEqual({r["outcome"]["result"] for r in records},{"WIN_IF_LONG","LOSS_IF_LONG"})
        # Hoán vị trên RAM, không xuất bank/QA vi phạm nhãn engine.
        for row,label in zip(records,[deepcopy(r["outcome"]) for r in records][::-1]):row["outcome"]=label
        self.fx.retriever._memory._records=records
        self.fx.retriever._verified_by_id={r["episode_id"]:deepcopy(r) for r in records}
        after=self.fx.retriever.select_price_examples(**query)
        self.assertNotEqual(before["regime_population"],after["regime_population"])
        self.assertNotEqual([r["outcome"] for r in before["tasks"]],[r["outcome"] for r in after["tasks"]])
        self.assertEqual(before["trace"],after["trace"])
        self.assertEqual(before["metadata"],after["metadata"])

    def test_k_gap_quality_and_age_do_not_change_statistics_population(self) -> None:
        query=query_for(self.fx);before=self.fx.retriever.select_price_examples(**query)
        for config in ({"requested_k":1},{"min_gap_sessions":1},{"min_gap_sessions":1000},
                       {"min_similarity":1.},{"max_prior_age_days":0}):
            after=self.fx.retriever.select_price_examples(**query,config=config)
            self.assertEqual(after["regime_population"],before["regime_population"])
            self.assertEqual(after["metadata"]["population_count"],before["metadata"]["population_count"])
            self.assertEqual(after["metadata"]["scaler_sha256"],before["metadata"]["scaler_sha256"])
            self.assertNotEqual(after["metadata"]["config_sha256"],before["metadata"]["config_sha256"])

    def test_future_then_past_and_reverse_memory_preserve_selection(self) -> None:
        early=query_for(self.fx,cutoff="2021-01-04")
        before=self.fx.retriever.select_price_examples(**early)
        self.fx.retriever.select_price_examples(**query_for(self.fx))
        self.fx.retriever._memory._records.reverse()
        self.assertEqual(self.fx.retriever.select_price_examples(**early),before)

    def test_future_prices_and_calendar_extension_leave_past_selection_unchanged(self) -> None:
        early=query_for(self.fx,cutoff="2021-01-04");before=self.fx.retriever.select_price_examples(**early)
        inputs=deepcopy(self.fx.inputs);frame=inputs["prices"]["FPT"][0];mask=frame.Datetime>"2021-01-04"
        for column in ("Open","High","Low","Close","Reference"):frame.loc[mask,column]*=2
        index=build_price_feature_index(**inputs)
        extended=inputs["calendar"].append(pd.bdate_range("2023-01-02","2024-12-31"))
        selector=PriceExampleSelector(index,extended)
        after=self.fx.retriever.select_price_examples(**{**early,"selector":selector})
        self.assertEqual(before["tasks"],after["tasks"])
        self.assertEqual(before["trace"],after["trace"])
        self.assertEqual(before["metadata"]["calendar_prefix_sha256"],after["metadata"]["calendar_prefix_sha256"])
        self.assertEqual(before["metadata"]["scaler_sha256"],after["metadata"]["scaler_sha256"])

    def test_injected_future_equal_exit_or_wrong_pool_fails_before_policy(self) -> None:
        query=query_for(self.fx)
        basequery={key:value for key,value in self.fx.query().items() if key not in ("index","query_features")}
        pool=self.fx.retriever.prepare_query(**basequery)
        future=next(r for r in self.fx.records if r["episode_id"]=="FPT:2022-01-03")
        for rows in ([future],pool["regime_population"]*2,pool["regime_population"][:-1]):
            with (patch.object(self.fx.retriever,"prepare_query",return_value={**pool,"regime_population":rows}),
                  patch("core.prior_example_selection._select_trace",side_effect=AssertionError("Không chọn pool lỗi")),
                  self.assertRaises(ValueError)):
                self.fx.retriever.select_price_examples(**query)
        selector=query["selector"]
        row=trace_row(selector,"2022-01-03",1.)
        self.assertEqual(row["exit_date"],"2022-01-06")
        with self.assertRaises(ValueError):_select_trace([row],selector,"2022-01-06",selection_config(None))
