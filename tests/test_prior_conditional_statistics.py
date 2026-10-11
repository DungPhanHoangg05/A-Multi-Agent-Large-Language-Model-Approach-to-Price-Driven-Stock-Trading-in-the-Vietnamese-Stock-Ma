"""Công thức tính tay, masks, partition và validator thống kê điều kiện."""

from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from core.bayesian_retriever import PREFIX_METRICS
from core.historical_signals import digest
from core.prior_conditional_statistics import conditional_metric, statistics_config, validate_conditional_statistics
from prior_price_similarity_support import PriceSimilarityFixture, SIGNALS
from prior_context_test_support import ContextFixture


def statistics_query(fixture: PriceSimilarityFixture, **options: str) -> dict:
    """Query chỉ có mã/ngày/regime/tín hiệu, không có feature, K hoặc outcome."""
    return {k:v for k,v in fixture.query(**options).items() if k not in ("index","query_features")}


class ConditionalStatisticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fx=PriceSimilarityFixture()
        self.addCleanup(self.fx.close)

    def test_manual_disjoint_background_example_and_no_double_likelihood(self) -> None:
        item=conditional_metric("win_rate_long",3,4,8,20)
        self.assertEqual(item["raw_counts"]["population"],{"success_count":11,"support_count":24,"raw_rate":11/24})
        self.assertEqual(item["background_mean"],9/22)
        self.assertAlmostEqual(item["prior_alpha"],18/11,places=14)
        self.assertAlmostEqual(item["prior_beta"],26/11,places=14)
        self.assertAlmostEqual(item["posterior_alpha"],51/11,places=14)
        self.assertAlmostEqual(item["posterior_beta"],37/11,places=14)
        self.assertAlmostEqual(item["posterior_mean"],51/88,places=14)
        self.assertAlmostEqual(item["posterior_alpha"]+item["posterior_beta"],8.)
        self.assertNotAlmostEqual(item["posterior_mean"],15/28)
        self.assertEqual(item["hyperprior_source"],"DISJOINT_BACKGROUND")

    def test_empty_conditional_background_one_observation_and_single_class(self) -> None:
        for success,support in ((0,0),(0,1),(1,1),(0,4),(4,4)):
            item=conditional_metric("win_rate_long",success,support,0,0)
            self.assertEqual(item["prior_alpha"],2.)
            self.assertEqual(item["prior_beta"],2.)
            self.assertIn("FIXED_SYMMETRIC_PRIOR",item["reason_codes"])
            if support:
                self.assertAlmostEqual(item["posterior_mean"],(2+success)/(4+support))
                self.assertEqual(item["status"],"OBSERVED")
            else:
                self.assertEqual(item["status"],"NO_CONDITIONAL_HISTORY")
                for field in ("posterior_alpha","posterior_beta","posterior_mean","credible_interval"):
                    self.assertIsNone(item[field])
                self.assertIsNone(item["raw_counts"]["conditional"]["raw_rate"])
        item=conditional_metric("bull_trap_rate",0,0,3,10)
        self.assertEqual(item["background_mean"],1/3)
        self.assertIsNone(item["posterior_mean"])
        self.assertEqual(item["reason_codes"],["NO_CONDITIONAL_HISTORY"])
        # Không mất beta_prior do cộng rồi trừ n_C trong nhóm chỉ WIN.
        tiny=conditional_metric("win_rate_long",1,1,0,0,shrink_strength=1e-15)
        self.assertEqual(tiny["posterior_beta"],5e-16)

    def test_interval_matches_independent_beta_three_two_polynomial(self) -> None:
        item=conditional_metric("win_rate_long",1,1,0,0)
        interval=item["credible_interval"]
        # Beta(3,2) có CDF 4x³−3x⁴; bisection độc lập scipy.ppf.
        for probability,field in ((.025,"lower"),(.975,"upper")):
            low,high=0.,1.
            for _ in range(80):
                mid=(low+high)/2
                if 4*mid**3-3*mid**4<probability:low=mid
                else:high=mid
            self.assertAlmostEqual(interval[field],(low+high)/2,places=13)
        self.assertEqual(interval["method"],"equal_tailed_beta_plugin")
        self.assertEqual(interval["width"],interval["upper"]-interval["lower"])

    def test_invalid_counts_strength_and_nonfinite_beta_do_not_fallback(self) -> None:
        for strength in (0.,-1.,True,np.float64(4.),float("nan"),float("inf"),10**400,5e-324):
            with self.subTest(strength=str(strength)[:50]),self.assertRaises(ValueError):
                conditional_metric("win_rate_long",1,2,1,2,shrink_strength=strength)
        for values in ((-1,2,0,0),(3,2,0,0),(True,2,0,0),(1,2,np.int64(0),2),(0,0,1,-1)):
            with self.assertRaises(ValueError):conditional_metric("win_rate_long",*values)
        for config in ([],{"requested_k":1},{"prior_alpha":1.},{"outcome":"WIN"}):
            with self.assertRaises(ValueError):statistics_config(config)
        with self.assertRaises(ValueError):conditional_metric("unknown",0,0,0,0)
        with patch("core.prior_conditional_statistics.beta.ppf",return_value=float("nan")):
            with self.assertRaises(ValueError):conditional_metric("win_rate_long",1,2,1,2)

    def test_production_masks_union_and_partition_match_scalar_counts(self) -> None:
        query=statistics_query(self.fx)
        result=self.fx.retriever.conditional_statistics(**query)
        records={r["episode_id"]:r for r in self.fx.records}
        ids={name:set(group["episode_ids"]) for name,group in result["groups"].items()}
        self.assertFalse(ids["conditional"]&ids["background"])
        self.assertEqual(ids["conditional"]|ids["background"],ids["population"])
        self.assertIn("FPT:2020-06-12",ids["conditional"])
        self.assertIn("FPT:2020-06-04",ids["background"])
        for metric in PREFIX_METRICS:
            for group,keys in ids.items():
                supported=[]
                for key in keys:
                    r=records[key];signals=r["agent_signals"]
                    t=signals["trend"]=="BULLISH";p=signals["pattern"]=="BULLISH"
                    mask={"win_rate_long":True,"bull_trap_rate":t or p,
                          "trend_false_bullish_rate":t,"pattern_false_bullish_rate":p}[metric]
                    if mask:supported.append(r)
                success=sum(r["outcome"]["result"]==("WIN_IF_LONG" if metric=="win_rate_long" else "LOSS_IF_LONG") for r in supported)
                actual=result["metrics"][metric]["raw_counts"][group]
                self.assertEqual(actual["support_count"],len(supported))
                self.assertEqual(actual["success_count"],success)
        # Cycle bullish ở cả Trend/Pattern vẫn chỉ góp một lần vào union.
        self.assertEqual(result["metrics"]["bull_trap_rate"]["raw_counts"]["population"]["support_count"],result["population_count"])
        self.assertEqual(result["metrics"]["pattern_false_bullish_rate"]["status"],"NO_CONDITIONAL_HISTORY")
        validate_conditional_statistics(result,self.fx.retriever)
        json.dumps(result,allow_nan=False)

    def test_conflicting_tuple_alias_sentiment_and_rare_group_are_distinct(self) -> None:
        query=statistics_query(self.fx)
        before=self.fx.retriever.conditional_statistics(**query)
        alias={**SIGNALS,"trend":"TĂNG","indicator_consensus":"GIẢM","sentiment":"POSITIVE"}
        after=self.fx.retriever.conditional_statistics(**{**query,"current_signals":alias})
        self.assertEqual(after["groups"],before["groups"])
        self.assertEqual(after["metrics"],before["metrics"])
        rare=self.fx.retriever.conditional_statistics(**{**query,"current_signals":{**SIGNALS,"alpha_consensus":"BULLISH"}})
        self.assertEqual(rare["conditional_count"],0)
        self.assertEqual(rare["background_count"],rare["population_count"])
        self.assertTrue(all(m["posterior_mean"] is None for m in rare["metrics"].values()))

    def test_validator_recomputes_source_even_if_forgery_is_rehashed(self) -> None:
        original=self.fx.retriever.conditional_statistics(**statistics_query(self.fx))
        for field in ("counts","partition","mean","source","config","extra"):
            changed=deepcopy(original)
            if field=="counts":changed["metrics"]["win_rate_long"]["raw_counts"]["conditional"]["success_count"]+=1
            if field=="partition":changed["groups"]["conditional"]["episode_ids"].reverse()
            if field=="mean":changed["metrics"]["win_rate_long"]["posterior_mean"]=.999
            if field=="source":changed["bank_sha256"]="0"*64
            if field=="config":changed["config"]["shrink_strength"]=5.
            if field=="extra":changed["query_outcome"]="WIN"
            changed["evidence_sha256"]=digest({k:v for k,v in changed.items() if k!="evidence_sha256"})
            with self.subTest(field=field),self.assertRaises(ValueError):validate_conditional_statistics(changed,self.fx.retriever)
        invalid=deepcopy(original);invalid["metrics"]["win_rate_long"]["posterior_mean"]=np.float64(.5)
        with self.assertRaises(ValueError):validate_conditional_statistics(invalid,self.fx.retriever)

    def test_hot_no_io_feature_ranking_or_fit_and_owned_result(self) -> None:
        query=statistics_query(self.fx)
        before=self.fx.retriever.conditional_statistics(**query)
        with (patch.object(Path,"read_bytes",side_effect=AssertionError("Cấm I/O")),
              patch.object(Path,"read_text",side_effect=AssertionError("Cấm I/O")),
              patch.object(self.fx.retriever,"select_price_examples",side_effect=AssertionError("Không phụ thuộc K")),
              patch("core.price_feature_index._fit",side_effect=AssertionError("Cấm fit"))):
            self.assertEqual(self.fx.retriever.conditional_statistics(**query),before)
        changed=deepcopy(before);changed["groups"]["population"]["episode_ids"].clear()
        changed["metrics"]["win_rate_long"]["posterior_mean"]=1.
        self.assertEqual(self.fx.retriever.conditional_statistics(**query),before)


class ConditionalStatisticsPointTests(unittest.TestCase):
    def test_full_source_callback_and_legacy_results_are_preserved(self) -> None:
        with patch("prior_context_test_support.pd.bdate_range",return_value=pd.bdate_range("2019-08-01",periods=700)):
            fx=ContextFixture()
        self.addCleanup(fx.close)
        for row in fx.records:row["regime"]=fx.regime["regime_name"]
        fx.publish_bank("a"*64)
        adapter=fx.adapter();point=adapter.prepare("FPT",fx.cutoff)
        with self.assertRaises(ValueError):point.conditional_statistics({})
        shared=point.bind_full(fx.full(point));snapshot=deepcopy(shared)
        v1=point.retrieve(shared);v2=point.evidence_v2(shared,{"min_population_count":1})
        with (patch.object(adapter,"execution_data",side_effect=AssertionError("Không đọc query outcome")),
              patch.object(point,"price_features",side_effect=AssertionError("Không cần feature")),
              patch.object(point,"bind_full",side_effect=AssertionError("Không gọi lại Full"))):
            result=point.conditional_statistics(shared)
        self.assertEqual(result["population_count"],3)
        validate_conditional_statistics(result,adapter._retriever)
        self.assertEqual(shared,snapshot)
        self.assertEqual(point.retrieve(shared),v1)
        self.assertEqual(point.evidence_v2(shared,{"min_population_count":1}),v2)
        for change in ({"outcome":"WIN"},{"as_of_date":"2022-12-30"}):
            with self.assertRaises(ValueError):point.conditional_statistics({**shared,**change})
        path=fx.root/"data/execution_prices/FPT.events.json";path.write_bytes(path.read_bytes()+b" ")
        with patch.object(adapter._retriever,"conditional_statistics",side_effect=AssertionError("Nguồn sai phải dừng")):
            with self.assertRaises(ValueError):point.conditional_statistics(shared)
