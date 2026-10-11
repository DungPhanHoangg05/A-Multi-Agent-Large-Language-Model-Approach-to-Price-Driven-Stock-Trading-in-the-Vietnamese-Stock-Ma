"""Tính độc lập outcome, thứ tự query và lọc PIT trước similarity giá."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from core.price_feature_index import build_price_feature_index
from prior_price_similarity_support import PriceSimilarityFixture


class PriceSimilarityLeakageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = PriceSimilarityFixture()
        self.addCleanup(self.fx.close)

    def test_symbol_regime_and_equal_future_exits_filtered_before_scoring(self) -> None:
        result = self.fx.retriever.rank_price_candidates(**self.fx.query())
        self.assertNotIn("FPT:2022-01-03", result["metadata"]["ranked_ids"])
        self.assertNotIn("FPT:2022-01-06", result["metadata"]["ranked_ids"])
        self.assertNotIn("FPT:2020-06-09", result["metadata"]["ranked_ids"])
        self.assertTrue(all(row["symbol"]=="FPT" and row["regime"]=="BULL" and row["exit_date"]<"2022-01-06"
                            for row in result["regime_population"]))
        query = self.fx.query()
        pool = self.fx.retriever.prepare_query(**{key:value for key,value in query.items() if key not in ("index","query_features")})
        bad = next(row for row in self.fx.records if row["episode_id"]=="FPT:2022-01-03")
        for rows in ([bad], pool["regime_population"][:-1], pool["regime_population"] * 2):
            with (patch.object(self.fx.retriever, "prepare_query", return_value={**pool, "regime_population":rows}),
                  patch("core.prior_price_similarity.signal_price_scores", side_effect=AssertionError("Không rank pool lỗi")),
                  self.assertRaises(ValueError)):
                self.fx.retriever.rank_price_candidates(**query)

    def test_outcome_permutation_on_ram_never_changes_scores_or_order(self) -> None:
        before = self.fx.retriever.rank_price_candidates(**self.fx.query())
        # Tiêm snapshot RAM để kiểm độc lập nhãn; không xuất bank/QA sai kinh tế.
        records = deepcopy(self.fx.retriever._memory._records)
        self.assertEqual({row["outcome"]["result"] for row in records}, {"WIN_IF_LONG", "LOSS_IF_LONG"})
        labels = [deepcopy(row["outcome"]) for row in records][::-1]
        for row, label in zip(records,labels):
            row["outcome"] = label
        self.fx.retriever._memory._records = records
        self.fx.retriever._verified_by_id = {row["episode_id"]:deepcopy(row) for row in records}
        after = self.fx.retriever.rank_price_candidates(**self.fx.query())
        self.assertNotEqual([row["outcome"] for row in before["ranked_tasks"]],
                            [row["outcome"] for row in after["ranked_tasks"]])
        self.assertEqual(after["trace"], before["trace"])
        self.assertEqual(after["metadata"], before["metadata"])
        self.assertEqual([row["episode_id"] for row in after["ranked_tasks"]], before["metadata"]["ranked_ids"])

    def test_future_then_past_query_does_not_reuse_later_fold_or_scores(self) -> None:
        early = self.fx.query(cutoff="2021-01-04")
        before = self.fx.retriever.rank_price_candidates(**early)
        self.fx.retriever.rank_price_candidates(**self.fx.query())
        after = self.fx.retriever.rank_price_candidates(**early)
        self.assertEqual(after,before)
        self.assertEqual(after["metadata"]["fold_id"],"train_2021")
        self.assertEqual(after["metadata"]["fit_cutoff"],"2021-01-04")

    def test_future_price_changes_do_not_change_early_ranking(self) -> None:
        early = self.fx.query(cutoff="2021-01-04")
        before = self.fx.retriever.rank_price_candidates(**early)
        inputs = deepcopy(self.fx.inputs)
        frame = inputs["prices"]["FPT"][0]
        mask = frame.Datetime > "2021-01-04"
        for column in ("Open","High","Low","Close","Reference"):
            frame.loc[mask,column] *= 2
        index = build_price_feature_index(**inputs)
        after = self.fx.retriever.rank_price_candidates(**{**early,"index":index})
        self.assertNotEqual(before["metadata"]["index_sha256"],after["metadata"]["index_sha256"])
        self.assertEqual(before["metadata"]["scaler_sha256"],after["metadata"]["scaler_sha256"])
        self.assertEqual(before["trace"],after["trace"])
        self.assertEqual(before["metadata"]["ranked_ids"],after["metadata"]["ranked_ids"])

    def test_query_outcome_and_invalid_feature_provenance_never_become_coverage(self) -> None:
        query = self.fx.query()
        with self.assertRaises(ValueError):
            self.fx.retriever.rank_price_candidates(**query,outcome="WIN")
        for changed in ({"outcome":"WIN"}, {"source":{}}, {"feature_end_date":"2024-01-01"},
                        {"vector":[float("nan")]*4}, {"as_of_date":"2021-01-04"}):
            with self.subTest(changed=str(changed)), self.assertRaises(ValueError):
                self.fx.retriever.rank_price_candidates(**{**query,"query_features":{**query["query_features"],**changed}})
