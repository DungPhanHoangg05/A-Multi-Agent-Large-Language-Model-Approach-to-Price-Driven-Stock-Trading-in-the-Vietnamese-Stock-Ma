"""Oracle chọn ví dụ, biên số học/lịch phiên và callback nguồn production."""

from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from core.prior_example_selection import PriceExampleSelector, _select_trace, selection_config
from core.price_feature_index import build_price_feature_index
from prior_price_similarity_support import PriceSimilarityFixture
from prior_context_test_support import ContextFixture


def query_for(fixture: PriceSimilarityFixture, **options: str) -> dict:
    """Dùng index/lịch/query thật, bỏ tham số index chỉ thuộc API base."""
    query = fixture.query(**options)
    query.pop("index")
    return {"selector": PriceExampleSelector(fixture.index, fixture.inputs["calendar"]), **query}


def trace_row(selector: PriceExampleSelector, day: str, score: float, key: str = "") -> dict:
    """Oracle nhỏ không chứa outcome; ngày thoát lấy đúng ba phiên trên lịch."""
    position = selector.session_position(day)
    return {"episode_id": key or day, "as_of_date": day, "exit_date": selector._days[position + 3],
            "status": "SCORED", "reason_codes": [], "signal_similarity": .75,
            "price_distance": .5, "price_similarity": 2/3, "base_score": score}


class ExampleSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = PriceSimilarityFixture()
        self.addCleanup(self.fx.close)
        self.selector = PriceExampleSelector(self.fx.index, self.fx.inputs["calendar"])

    def test_manual_recency_age_and_similarity_equality_without_rounding(self) -> None:
        rows = [trace_row(self.selector, day, score) for day,score in
                (("2021-01-06", 17/24), ("2020-01-07", .625), ("2020-01-06", 1.),
                 ("2021-01-07", np.nextafter(.625, 0.).item()))]
        trace, ranked, selected = _select_trace(rows, self.selector, "2022-01-06", selection_config(None))
        lookup = {row["episode_id"]: row for row in trace}
        self.assertEqual(selected, ["2021-01-06", "2020-01-07"])
        self.assertEqual(ranked, selected)
        self.assertEqual(lookup["2021-01-06"]["recency"], .5)
        self.assertAlmostEqual(lookup["2021-01-06"]["rank_score"], 17/48, places=15)
        self.assertEqual(lookup["2020-01-07"]["age_days"], 730)
        self.assertEqual(lookup["2020-01-07"]["rank_score"], .625/4)
        self.assertEqual(lookup["2020-01-06"]["selection_reasons"], ["PRIOR_TOO_OLD"])
        self.assertEqual(lookup["2021-01-07"]["selection_reasons"], ["BELOW_MIN_SIMILARITY"])
        self.assertGreater(lookup["2021-01-06"]["exit_age_days"], 0)
        self.assertNotEqual(lookup["2021-01-06"]["age_days"], lookup["2021-01-06"]["exit_age_days"])

    def test_greedy_gap_four_rejected_five_accepted_and_duplicate_day(self) -> None:
        rows = [trace_row(self.selector, day, score, key) for day,score,key in
                (("2021-01-04",1.,"first"),("2021-01-04",1.,"same"),
                 ("2021-01-08",.9,"gap4"),("2021-01-11",.8,"gap5"))]
        # Half-life lớn giữ thứ tự điểm; vẫn dùng phép tính recency production.
        config = selection_config({"half_life_days": 1000000})
        trace, ranked, selected = _select_trace(rows, self.selector, "2022-01-06", config)
        self.assertEqual(ranked, ["first","same","gap4","gap5"])
        self.assertEqual(selected, ["first","gap5"])
        lookup = {row["episode_id"]:row for row in trace}
        for key in ("same","gap4"):
            self.assertEqual(lookup[key]["selection_reasons"], ["SESSION_GAP_TOO_SMALL"])
            self.assertEqual(lookup[key]["conflicting_selected_ids"], ["first"])
        self.assertEqual(_select_trace(rows[::-1], self.selector, "2022-01-06", config)[1:], (ranked,selected))
        rows = [trace_row(self.selector,day,score) for day,score in
                (("2021-01-04",1.),("2021-01-18",.9),("2021-01-07",.8))]
        trace, _, selected = _select_trace(rows,self.selector,"2022-01-06",config)
        self.assertEqual(selected,["2021-01-04","2021-01-18"])
        self.assertEqual(trace[-1]["conflicting_selected_ids"],["2021-01-04"])

    def test_rank_ties_exit_then_id_and_k_limit(self) -> None:
        rows = [trace_row(self.selector,"2021-01-04",1.,key) for key in ("b","a")]
        # Tiêm score equal trên trace thuần để kiểm tie-break, không xuất bank sai T+3.
        newer = trace_row(self.selector,"2021-01-11",.5,"newer")
        recency_old = 2**(-367/365)
        recency_new = 2**(-360/365)
        newer["base_score"] = recency_old/recency_new
        rows.append(newer)
        trace, ranked, selected = _select_trace(rows,self.selector,"2022-01-06",
                                               selection_config({"requested_k":1,"min_similarity":0.}))
        self.assertEqual(ranked,["newer","a","b"])
        self.assertEqual(selected,["newer"])
        self.assertEqual([r["selection_reasons"] for r in trace[:2]], [["K_LIMIT"],["K_LIMIT"]])

    def test_production_api_matches_independent_scalar_selection_oracle(self) -> None:
        query = query_for(self.fx)
        result = self.fx.retriever.select_price_examples(**query)
        base = self.fx.retriever.rank_price_candidates(**self.fx.query())
        expected=[]
        for row in base["trace"]:
            age=(date(2022,1,6)-date.fromisoformat(row["as_of_date"])).days
            if row["status"]=="SCORED" and age<=730 and row["base_score"]>=.625:
                expected.append((row["episode_id"],row["exit_date"],row["base_score"]*2**(-age/365),
                                 self.fx.inputs["calendar"].get_loc(row["as_of_date"])))
        expected.sort(key=lambda r:r[0]); expected.sort(key=lambda r:r[1],reverse=True)
        expected.sort(key=lambda r:r[2],reverse=True)
        selected=[]
        for row in expected:
            if len(selected)<3 and all(abs(row[3]-other[3])>=5 for other in selected):selected.append(row)
        self.assertEqual(result["metadata"]["selected_ids"],[row[0] for row in selected])
        self.assertEqual(result["metadata"]["ranked_ids"],[row[0] for row in expected])
        self.assertEqual(result["regime_population"],base["regime_population"])
        self.assertEqual({r["episode_id"] for r in result["trace"]},
                         set(result["metadata"]["selected_ids"]+result["metadata"]["excluded_ids"]))
        self.assertEqual([r["episode_id"] for r in result["tasks"]],result["metadata"]["selected_ids"])
        self.assertTrue(result["metadata"]["policy_complete"])
        self.assertEqual(result["metadata"]["ranking_version"],"signal_price_recency_v1")
        self.assertEqual(result["metadata"]["diversity_version"],"session_gap_v1")
        json.dumps(result,allow_nan=False)

    def test_empty_single_and_unavailable_do_not_fill_k_or_drop_population(self) -> None:
        for symbol,regime,config in (("FPT","CHOPPY",{}),("VCB","BULL",{}),
                                      ("VNM","BULL",{}),("VCB","BULL",{"max_prior_age_days":0})):
            result=self.fx.retriever.select_price_examples(**query_for(self.fx,symbol=symbol,regime=regime),config=config)
            self.assertLess(result["metadata"]["k_eff"],3)
            self.assertIn("INSUFFICIENT_EXAMPLES",result["metadata"]["reason_codes"])
            if symbol=="VCB" and not config:self.assertEqual(result["metadata"]["k_eff"],1)
            if symbol=="VNM":
                self.assertEqual(result["metadata"]["population_count"],1)
                self.assertIn("SCALER_UNAVAILABLE",result["trace"][0]["selection_reasons"])
            if config:self.assertEqual(result["tasks"],[])
        query=query_for(self.fx)
        features=query["query_features"]
        features.update(status="UNAVAILABLE",vector=None,reasons=["CORPORATE_ACTION_WINDOW"])
        features["coverage"]["barrier_dates"]=[query["as_of_date"]]
        result=self.fx.retriever.select_price_examples(**query,config={"w_signal":1.})
        self.assertEqual(result["tasks"],[])
        self.assertGreater(result["metadata"]["population_count"],0)
        self.assertTrue(all(r["rank_score"] is None and "QUERY_FEATURE_UNAVAILABLE" in r["selection_reasons"]
                            for r in result["trace"]))

    def test_invalid_config_calendar_and_unknown_outcome_are_errors(self) -> None:
        for config in ([],{"unknown":1},{"outcome":"WIN"},{"requested_k":4},{"requested_k":0},
                       {"requested_k":True},{"seed":7},{"half_life_days":0},{"half_life_days":1.5},
                       {"half_life_days":10**400},{"min_gap_sessions":0},{"min_gap_sessions":True},
                       {"max_prior_age_days":-1},{"min_similarity":float("nan")},
                       {"min_similarity":np.float64(.5)},{"w_signal":10**400}):
            with self.subTest(config=str(config)[:70]),self.assertRaises(ValueError):selection_config(config)
        calendar=self.fx.inputs["calendar"]
        for changed in (calendar[::-1],calendar.append(calendar[-1:]),calendar.delete(20),
                        calendar.tz_localize("UTC"),calendar+pd.Timedelta(hours=1),pd.DatetimeIndex([pd.NaT])):
            with self.assertRaises(ValueError):PriceExampleSelector(self.fx.index,changed)
        with self.assertRaises(ValueError):self.fx.retriever.select_price_examples(**query_for(self.fx),outcome="WIN")
        with self.assertRaises(ValueError):self.fx.retriever.select_price_examples(**{**query_for(self.fx),"selector":None})
        with self.assertRaises(ValueError):self.selector.session_position("2021-01-09")

    def test_hot_no_io_fit_payload_copy_and_owned_results(self) -> None:
        query=query_for(self.fx)
        before=self.fx.retriever.select_price_examples(**query)
        with (patch.object(Path,"read_bytes",side_effect=AssertionError("Cấm I/O")),
              patch.object(Path,"read_text",side_effect=AssertionError("Cấm I/O")),
              patch("core.price_feature_index._fit",side_effect=AssertionError("Cấm fit")),
              patch.object(type(self.fx.index),"payload",new=property(lambda _: (_ for _ in ()).throw(AssertionError("Cấm copy index"))))):
            self.assertEqual(self.fx.retriever.select_price_examples(**query),before)
        changed=deepcopy(before)
        changed["trace"][0]["selection_reasons"].append("bad")
        changed["metadata"]["selected_ids"].append("bad")
        changed["regime_population"][0]["outcome"]["result"]="bad"
        self.assertEqual(self.fx.retriever.select_price_examples(**query),before)


class ExampleSelectionPointTests(unittest.TestCase):
    def test_sealed_full_source_calendar_k_and_legacy_results(self) -> None:
        with patch("prior_context_test_support.pd.bdate_range",return_value=pd.bdate_range("2019-08-01",periods=700)):
            fx=ContextFixture()
        self.addCleanup(fx.close)
        for row in fx.records:row["regime"]=fx.regime["regime_name"]
        fx.publish_bank("a"*64)
        adapter=fx.adapter();point=adapter.prepare("FPT",fx.cutoff);index=adapter.build_price_feature_index()
        with self.assertRaises(ValueError):point.select_price_examples({},index)
        shared=point.bind_full(fx.full(point));snapshot=deepcopy(shared)
        v1=point.retrieve(shared)
        evidence=point.evidence_v2(shared,{"min_population_count":1})
        with (patch.object(adapter,"execution_data",side_effect=AssertionError("Cấm evaluator")),
              patch.object(point,"bind_full",side_effect=AssertionError("Không gọi lại Full"))):
            result=point.select_price_examples(shared,index)
        self.assertEqual(result["metadata"]["population_count"],3)
        self.assertEqual(result["metadata"]["calendar_source"],adapter._vnindex_source)
        self.assertEqual(shared,snapshot)
        self.assertEqual(point.retrieve(shared),v1)
        self.assertEqual(point.evidence_v2(shared,{"min_population_count":1}),evidence)
        self.assertEqual(len(adapter._price_example_selectors),1)
        for config in ({"requested_k":1},{"seed":3},[]):
            with self.assertRaises(ValueError):point.select_price_examples(shared,index,config=config)
        path=fx.root/"data/execution_prices/FPT.events.json"
        path.write_bytes(path.read_bytes()+b" ")
        with patch("core.prior_example_selection._select_trace",side_effect=AssertionError("Nguồn sai không chọn")):
            with self.assertRaises(ValueError):point.select_price_examples(shared,index)
