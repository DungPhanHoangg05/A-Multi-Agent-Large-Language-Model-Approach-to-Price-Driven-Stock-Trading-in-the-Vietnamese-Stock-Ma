"""Oracle số, hợp đồng API, coverage và hồi quy v1 của similarity mới."""

from copy import deepcopy
import json
import math
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from core.bayesian_retriever import normalize_signals
from core.prior_price_similarity import signal_price_scores
from core.price_feature_index import build_price_feature_index
from prior_price_similarity_support import PriceSimilarityFixture, SIGNALS
from prior_context_test_support import ContextFixture


class PriceSimilarityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = PriceSimilarityFixture()
        self.addCleanup(self.fx.close)

    def test_manual_four_dimensions_aliases_and_ignored_sentiment(self) -> None:
        prior = {**SIGNALS, "pattern": "BULLISH", "sentiment": "POSITIVE"}
        query = {**SIGNALS, "trend": "TĂNG", "indicator_consensus": "GIẢM"}
        score = signal_price_scores(query_signals=query, prior_signals=[prior],
            query_vector=[0.] * 4, prior_vectors=[[1., 0., 0., 0.]])[0]
        self.assertEqual(score["signal_similarity"], .75)
        self.assertEqual(score["price_distance"], .5)
        self.assertEqual(score["price_similarity"], 2/3)
        self.assertAlmostEqual(score["base_score"], 17/24, places=15)
        identical = signal_price_scores(query_signals=SIGNALS, prior_signals=[SIGNALS],
            query_vector=[0.] * 4, prior_vectors=[[0.] * 4])[0]
        self.assertEqual(identical["base_score"], 1.)
        self.assertEqual(identical["price_distance"], 0.)
        for weight, expected in ((0., 2/3), (1., .75)):
            self.assertEqual(signal_price_scores(query_signals=query, prior_signals=[prior],
                query_vector=[0.] * 4, prior_vectors=[[1., 0., 0., 0.]], w_signal=weight)[0]["base_score"], expected)

    def test_invalid_vectors_weights_signals_and_overflow_are_errors(self) -> None:
        base = {"query_signals": SIGNALS, "prior_signals": [SIGNALS],
                "query_vector": [0.] * 4, "prior_vectors": [[1.] * 4]}
        for change in ({"w_signal": True}, {"w_signal": np.float64(.5)}, {"w_signal": -.1},
                       {"w_signal": 1.1}, {"w_signal": float("nan")}, {"w_signal": 10**400},
                       {"query_vector": [0.] * 3}, {"prior_vectors": [[1.] * 5]},
                       {"prior_vectors": [[True] * 4]}, {"prior_vectors": [[np.float64(1.)] * 4]},
                       {"query_vector": [float("inf")] * 4}, {"query_vector": [10**400] * 4},
                       {"query_vector": [1e308] * 4, "prior_vectors": [[-1e308] * 4]},
                       {"prior_signals": []}, {"query_signals": {**SIGNALS, "trend": "unknown"}},
                       {"query_signals": {k:v for k,v in SIGNALS.items() if k != "pattern"}}):
            with self.subTest(change=str(change)[:90]), self.assertRaises(ValueError):
                signal_price_scores(**{**base, **change})
        self.assertEqual(signal_price_scores(**{**base, "prior_signals": [], "prior_vectors": []}), [])

    def test_public_ranking_matches_scalar_oracle_and_preserves_population(self) -> None:
        query = self.fx.query()
        actual = self.fx.retriever.rank_price_candidates(**query)
        scaler = self.fx.index.scaler("FPT", query["as_of_date"])
        mean, scale = scaler["mean"], scaler["scale"]
        z_query = [(value - mu) / sd for value, mu, sd in zip(query["query_features"]["vector"], mean, scale)]
        raw = {row["episode_id"]: row["features"] for row in self.fx.index.payload["records"]}
        expected = []
        for row in actual["regime_population"]:
            features = raw[row["episode_id"]]
            if features["status"] != "AVAILABLE":
                continue
            signals = normalize_signals(row["agent_signals"])
            s = sum(signals[key] == SIGNALS[key] for key in ("trend", "pattern", "alpha_consensus", "indicator_consensus")) / 4
            z_prior = [(value - mu) / sd for value, mu, sd in zip(features["vector"], mean, scale)]
            d = math.sqrt(sum((a-b)**2 for a,b in zip(z_prior,z_query)) / 4)
            expected.append((row["episode_id"], row["exit_date"], .5*s + .5/(1+d), s, d))
        expected.sort(key=lambda item:item[0])
        expected.sort(key=lambda item:item[1], reverse=True)
        expected.sort(key=lambda item:item[2], reverse=True)
        self.assertEqual(actual["metadata"]["ranked_ids"], [item[0] for item in expected])
        trace = {row["episode_id"]:row for row in actual["trace"]}
        for key, _, base, s, d in expected:
            self.assertAlmostEqual(trace[key]["base_score"], base, places=14)
            self.assertEqual(trace[key]["signal_similarity"], s)
            self.assertAlmostEqual(trace[key]["price_distance"], d, places=14)
        self.assertIn("FPT:2020-06-12", [row["episode_id"] for row in actual["regime_population"]])
        self.assertNotIn("FPT:2020-06-12", actual["metadata"]["ranked_ids"])
        self.assertFalse(actual["metadata"]["policy_complete"])
        self.assertEqual(actual["metadata"]["metric_version"], "signal_price_similarity_v1")
        json.dumps(actual, allow_nan=False)

    def test_tie_break_exit_then_id_and_input_order_invariance(self) -> None:
        self.fx.records = [row for row in self.fx.records if row["symbol"] == "VCB"]
        for row in self.fx.records:
            row["agent_signals"] = deepcopy(SIGNALS)
        self.fx.publish()
        query = self.fx.query(symbol="VCB")
        expected = self.fx.retriever.rank_price_candidates(**query)
        self.assertEqual(expected["metadata"]["ranked_ids"], ["VCB:2020-06-04", "VCB:2020-06-01"])
        self.fx.retriever._memory._records.reverse()
        self.assertEqual(self.fx.retriever.rank_price_candidates(**query), expected)
        # Tiêm metadata cùng exit trên RAM để kiểm tie-break ID; không phát hành bank này.
        for row in self.fx.records:
            row["exit_date"] = "2020-06-09"
        projected = [{key:row[key] for key in ("episode_id","symbol","as_of_date","exit_date")} for row in self.fx.records]
        self.fx.index = build_price_feature_index(**{**self.fx.inputs, "records": projected})
        self.fx.retriever._verified_by_id = {row["episode_id"]:deepcopy(row) for row in self.fx.records}
        self.fx.retriever._memory._records = deepcopy(self.fx.records)
        actual = self.fx.retriever.rank_price_candidates(**self.fx.query(symbol="VCB"))
        self.assertEqual(actual["metadata"]["ranked_ids"], ["VCB:2020-06-01", "VCB:2020-06-04"])

    def test_unavailable_query_or_scaler_never_falls_back_to_signal_only(self) -> None:
        query = self.fx.query()
        query["query_features"]["status"] = "UNAVAILABLE"
        query["query_features"]["vector"] = None
        query["query_features"]["reasons"] = ["CORPORATE_ACTION_WINDOW"]
        query["query_features"]["coverage"]["barrier_dates"] = [query["as_of_date"]]
        result = self.fx.retriever.rank_price_candidates(**query, w_signal=1.)
        self.assertEqual(result["ranked_tasks"], [])
        self.assertGreater(result["metadata"]["population_count"], 0)
        self.assertTrue(all("QUERY_FEATURE_UNAVAILABLE" in row["reason_codes"] for row in result["trace"]))
        result = self.fx.retriever.rank_price_candidates(**self.fx.query(symbol="VNM"))
        self.assertEqual(result["metadata"]["scaler_status"], "SCALER_UNAVAILABLE")
        self.assertEqual(result["metadata"]["fit_count"], 1)
        self.assertEqual(result["ranked_tasks"], [])
        self.assertIn("SCALER_UNAVAILABLE", result["trace"][0]["reason_codes"])

    def test_empty_regime_and_unknown_index_or_missing_ids_fail_correctly(self) -> None:
        empty = self.fx.retriever.rank_price_candidates(**self.fx.query(regime="CHOPPY"))
        self.assertEqual(empty["ranked_tasks"], [])
        self.assertEqual(empty["trace"], [])
        with self.assertRaises(ValueError):
            self.fx.retriever.rank_price_candidates(**{**self.fx.query(), "index": None})
        inputs = deepcopy(self.fx.inputs)
        inputs["provenance"]["bank"]["bank_sha256"] = "f" * 64
        wrong = build_price_feature_index(**inputs)
        with self.assertRaises(ValueError):
            self.fx.retriever.rank_price_candidates(**{**self.fx.query(), "index": wrong})
        inputs = deepcopy(self.fx.inputs)
        inputs["records"].pop()
        missing = build_price_feature_index(**inputs)
        with self.assertRaises(ValueError):
            self.fx.retriever.rank_price_candidates(**{**self.fx.query(), "index": missing})

    def test_hot_cache_no_io_fit_or_payload_copy_and_owned_results(self) -> None:
        query = self.fx.query()
        before = self.fx.retriever.rank_price_candidates(**query)
        with (patch.object(Path, "read_bytes", side_effect=AssertionError("Cấm I/O")),
              patch.object(Path, "read_text", side_effect=AssertionError("Cấm I/O")),
              patch("core.price_feature_index._fit", side_effect=AssertionError("Cấm refit")),
              patch.object(type(self.fx.index), "payload", new=property(lambda _: (_ for _ in ()).throw(AssertionError("Cache đã bind"))))):
            after = self.fx.retriever.rank_price_candidates(**query)
            self.assertEqual(after, before)
        after["ranked_tasks"][0]["agent_signals"]["trend"] = "BEARISH"
        after["trace"][0]["reason_codes"].append("bad")
        after["metadata"]["config"]["w_signal"] = 0.
        self.assertEqual(self.fx.retriever.rank_price_candidates(**query), before)

    def test_legacy_v1_and_w5_evidence_are_unchanged(self) -> None:
        query = {key:value for key,value in self.fx.query().items() if key not in ("index","query_features")}
        v1 = {mode:self.fx.retriever.retrieve(**query, mode=mode) for mode in ("random","recent","similarity","bayesian_regime")}
        evidence = self.fx.retriever.retrieve_evidence(**query, config={"min_population_count":1})
        self.fx.retriever.rank_price_candidates(**self.fx.query())
        self.assertEqual(v1, {mode:self.fx.retriever.retrieve(**query, mode=mode) for mode in v1})
        self.assertEqual(evidence, self.fx.retriever.retrieve_evidence(**query, config={"min_population_count":1}))
        self.assertEqual(v1["bayesian_regime"]["metadata"]["metric_version"], "signal_match_v1")


class PriceSimilarityPointTests(unittest.TestCase):
    def setUp(self) -> None:
        dates = pd.bdate_range("2019-08-01", periods=700)
        with patch("prior_context_test_support.pd.bdate_range", return_value=dates):
            self.fx = ContextFixture()
        self.addCleanup(self.fx.close)
        for row in self.fx.records:
            row["regime"] = self.fx.regime["regime_name"]
        self.fx.publish_bank("a" * 64)

    def test_public_point_uses_sealed_full_verified_features_and_original_retrieval(self) -> None:
        adapter = self.fx.adapter()
        point = adapter.prepare("FPT", self.fx.cutoff)
        shared = point.bind_full(self.fx.full(point))
        v1 = point.retrieve(shared)
        index = adapter.build_price_feature_index()
        with (patch.object(adapter, "execution_data", side_effect=AssertionError("Cấm evaluator")),
              patch.object(point, "bind_full", side_effect=AssertionError("Không chạy lại Full"))):
            result = point.rank_price_candidates(shared, index)
        self.assertEqual(result["metadata"]["fold_id"], "train_2022")
        self.assertEqual(result["metadata"]["population_count"], 3)
        self.assertEqual(result["metadata"]["scored_count"], 3)
        self.assertEqual(point.retrieve(shared), v1)
        self.assertNotIn("query_features", shared)

    def test_unsealed_tampered_projection_or_source_stops_before_scoring(self) -> None:
        adapter = self.fx.adapter()
        point = adapter.prepare("FPT", self.fx.cutoff)
        index = adapter.build_price_feature_index()
        with self.assertRaises(ValueError):
            point.rank_price_candidates({}, index)
        shared = point.bind_full(self.fx.full(point))
        for changed in ({**shared, "outcome": "WIN"}, {**shared, "as_of_date": "2022-12-30"}):
            with self.assertRaises(ValueError):
                point.rank_price_candidates(changed, index)
        path = self.fx.root / "data/execution_prices/FPT.events.json"
        path.write_bytes(path.read_bytes() + b" ")
        with patch("core.prior_price_similarity.signal_price_scores", side_effect=AssertionError("Không được score")):
            with self.assertRaises(ValueError):
                point.rank_price_candidates(shared, index)
