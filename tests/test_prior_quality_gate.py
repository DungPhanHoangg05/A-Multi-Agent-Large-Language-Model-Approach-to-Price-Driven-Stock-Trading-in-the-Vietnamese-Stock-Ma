"""Biên support/uncertainty, block độc lập và callback nguồn của quality gate."""

from copy import deepcopy
import math
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from core.backtest_engine import compute_round_trip_net_return
from core.bayesian_retriever import PREFIX_METRICS
from core.historical_signals import digest
from core.prior_conditional_statistics import conditional_metric
from core.prior_example_selection import PriceExampleSelector
from core.prior_quality_gate import COUPLED_GATE, SPLIT_GATE, _content_views, _readiness, validate_quality_evidence
from prior_price_similarity_support import PriceSimilarityFixture, SIGNALS
from prior_context_test_support import ContextFixture


def gate_query(fixture: PriceSimilarityFixture, **options: str) -> dict:
    """Dùng query/feature/index/lịch thật của fixture production."""
    query = fixture.query(**options)
    query.pop("index")
    return {**query, "selector": PriceExampleSelector(fixture.index, fixture.inputs["calendar"])}


def populated_fixture() -> PriceSimilarityFixture:
    """Bổ sung 24 cycle trước quyền; mọi nhãn vẫn lấy từ engine và giá thật fixture."""
    fx = PriceSimilarityFixture()
    frame, events = fx.inputs["prices"]["FPT"]
    events.append({"exrightDate": "2021-01-12T00:00:00"})
    calendar = fx.inputs["calendar"]
    for cutoff in pd.bdate_range("2020-01-02", periods=96)[::4]:
        position = calendar.get_loc(cutoff)
        net = float(100 * compute_round_trip_net_return(float(frame.Open.iloc[position + 1]),
                                                        float(frame.Close.iloc[position + 3])))
        day = cutoff.strftime("%Y-%m-%d")
        fx.records.append({"episode_id": f"FPT:{day}", "symbol": "FPT", "as_of_date": day,
            "entry_date": calendar[position + 1].strftime("%Y-%m-%d"),
            "exit_date": calendar[position + 3].strftime("%Y-%m-%d"), "regime": "BULL",
            "agent_signals": deepcopy(SIGNALS), "outcome": {"actual_direction": "UP" if net > 0 else "DOWN",
            "net_return_pct": net, "result": "WIN_IF_LONG" if net > 0 else "LOSS_IF_LONG", "was_bull_trap": bool(net <= 0)}})
    fx.publish()
    return fx


class QualityGateBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.metrics = {key: conditional_metric(key, 2, 5, 7, 15) for key in PREFIX_METRICS}
        for item in self.metrics.values():
            item["credible_interval"]["width"] = .75
        self.metadata = {"query_feature_status": "AVAILABLE", "scaler_status": "AVAILABLE", "selected_ids": ["example"]}

    def test_population_support_and_width_boundaries_without_rounding(self) -> None:
        # Oracle chỉ kiểm phép so gate; các posterior giả này không xuất thành artifact production.
        for population in (19, 20, 21):
            for support in (4, 5, 6):
                for width in (math.nextafter(.75, 0.), .75, math.nextafter(.75, 1.)):
                    with self.subTest(population=population, support=support, width=width):
                        for item in self.metrics.values():
                            item["raw_counts"]["conditional"]["support_count"] = support
                            item["credible_interval"]["width"] = width
                        gate = _readiness(population, self.metrics, self.metadata, SPLIT_GATE)
                        self.assertEqual(gate["stats_ready"], population >= 20 and support >= 5 and width <= .75)
                        self.assertEqual(gate["examples_ready"], population >= 20)

    def test_masks_gate_each_metric_and_empty_conditional_is_not_zero_rate(self) -> None:
        self.metrics["pattern_false_bullish_rate"] = conditional_metric("pattern_false_bullish_rate", 0, 0, 7, 15)
        self.metrics["bull_trap_rate"]["raw_counts"]["conditional"]["support_count"] = 4
        gate = _readiness(20, self.metrics, self.metadata, SPLIT_GATE)
        self.assertEqual(gate["ready_metric_ids"], ["win_rate_long", "trend_false_bullish_rate"])
        self.assertIn("NO_CONDITIONAL_HISTORY", gate["metrics"]["pattern_false_bullish_rate"]["reason_codes"])
        self.assertIsNone(gate["metrics"]["pattern_false_bullish_rate"]["interval_width"])

    def test_missing_examples_query_feature_or_scaler_preserves_stats(self) -> None:
        for changed, reason in (({"selected_ids": []}, "NO_QUALIFIED_EXAMPLES"),
                ({"query_feature_status": "UNAVAILABLE", "selected_ids": []}, "QUERY_FEATURE_UNAVAILABLE"),
                ({"scaler_status": "SCALER_UNAVAILABLE", "selected_ids": []}, "SCALER_UNAVAILABLE")):
            gate = _readiness(20, self.metrics, {**self.metadata, **changed}, SPLIT_GATE)
            self.assertTrue(gate["stats_ready"])
            self.assertFalse(gate["examples_ready"])
            self.assertIn(reason, gate["examples_reason_codes"])
            views = _content_views(gate, 0)
            self.assertFalse(views["stats_only"]["fallback_to_original"])
            self.assertEqual(views["stats_only"]["visible_k"], 0)
            self.assertTrue(views["examples_only"]["fallback_to_original"])

    def test_examples_independent_of_statistics_and_content_visibility(self) -> None:
        for item in self.metrics.values():
            item["raw_counts"]["conditional"]["support_count"] = 4
        gate = _readiness(20, self.metrics, self.metadata, SPLIT_GATE)
        self.assertFalse(gate["stats_ready"])
        self.assertTrue(gate["examples_ready"])
        views = _content_views(gate, 1)
        self.assertTrue(views["stats_only"]["fallback_to_original"])
        self.assertEqual(views["examples_only"]["visible_metric_ids"], [])
        self.assertEqual(views["full_prior"]["visible_example_ids"], ["example"])

    def test_mean_is_not_a_trading_gate(self) -> None:
        before = _readiness(20, self.metrics, self.metadata, SPLIT_GATE)
        for mean in (0., .5, 1.):
            for item in self.metrics.values():
                item["posterior_mean"] = mean
            self.assertEqual(_readiness(20, self.metrics, self.metadata, SPLIT_GATE), before)


class QualityGateProductionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = populated_fixture()
        self.addCleanup(self.fx.close)

    def test_real_producers_ready_and_owned_base_trace_for_all_content_modes(self) -> None:
        query = gate_query(self.fx)
        snapshot = deepcopy(query["query_features"])
        evidence = self.fx.retriever.quality_evidence(**query)
        self.assertTrue(evidence["gate"]["stats_ready"])
        self.assertTrue(evidence["gate"]["examples_ready"])
        self.assertEqual(evidence["gate"]["metrics"]["pattern_false_bullish_rate"]["status"], "INSUFFICIENT_EVIDENCE")
        self.assertNotIn("pattern_false_bullish_rate", evidence["content_views"]["full_prior"]["visible_metric_ids"])
        self.assertEqual(evidence["retrieved_k"], len(evidence["selection"]["tasks"]))
        self.assertEqual(evidence["base_evidence_sha256"], digest({k:v for k,v in evidence.items() if k != "base_evidence_sha256"}))
        self.assertEqual(evidence["content_views"]["stats_only"]["visible_k"], 0)
        self.assertEqual(evidence["content_views"]["examples_only"]["visible_metric_ids"], [])
        validate_quality_evidence(evidence, self.fx.retriever, selector=query["selector"], query_features=query["query_features"])
        self.assertEqual(query["query_features"], snapshot)
        evidence["selection"]["tasks"].clear()
        self.assertTrue(self.fx.retriever.quality_evidence(**query)["selection"]["tasks"])

    def test_real_unavailable_feature_keeps_stats_and_zero_k_eff(self) -> None:
        evidence = self.fx.retriever.quality_evidence(**gate_query(self.fx, cutoff="2021-01-14"))
        self.assertEqual(evidence["selection"]["metadata"]["query_feature_status"], "UNAVAILABLE")
        self.assertTrue(evidence["gate"]["stats_ready"])
        self.assertFalse(evidence["gate"]["examples_ready"])
        self.assertEqual(evidence["effective_k"], 0)
        self.assertFalse(evidence["content_views"]["stats_only"]["fallback_to_original"])

    def test_c1_preserves_population_beta_and_coupled_gate(self) -> None:
        query = gate_query(self.fx)
        evidence = self.fx.retriever.quality_evidence(**query, gate_version=COUPLED_GATE)
        stats = evidence["statistics"]
        legacy = self.fx.retriever.retrieve_evidence(**{k:query[k] for k in
            ("symbol", "as_of_date", "current_regime", "current_signals")})
        self.assertEqual(stats["statistics_version"], "regime_beta_binomial_v2")
        self.assertNotIn("min_conditional_count", evidence["config"])
        self.assertEqual(stats["metrics"], legacy["metrics"])
        self.assertEqual(stats["metrics"]["win_rate_long"]["support_count"], stats["population_count"])
        self.assertTrue(evidence["gate"]["stats_ready"])
        off = self.fx.retriever.quality_evidence(**gate_query(self.fx, cutoff="2021-01-14"), gate_version=COUPLED_GATE)
        self.assertFalse(off["gate"]["stats_ready"])
        self.assertFalse(off["gate"]["examples_ready"])
        validate_quality_evidence(evidence, self.fx.retriever, selector=query["selector"], query_features=query["query_features"])

    def test_disabled_and_zero_skip_both_producers_and_artifact_dependencies(self) -> None:
        query = {k:v for k,v in gate_query(self.fx).items() if k not in ("selector", "query_features")}
        for options in ({"requested_k": 0}, {"enable_bayesian_prior": False},
                        {"requested_k": 0, "enable_bayesian_prior": False}):
            with (patch.object(self.fx.retriever, "conditional_statistics", side_effect=AssertionError("Không đếm")),
                  patch.object(self.fx.retriever, "select_price_examples", side_effect=AssertionError("Không chọn"))):
                evidence = self.fx.retriever.quality_evidence(**query, **options)
            self.assertEqual(evidence["gate"]["status"], "DISABLED")
            self.assertIsNone(evidence["statistics"])
            self.assertIsNone(evidence["selection"])
            self.assertEqual(evidence["tasks"], [])
            self.assertTrue(all(v["fallback_to_original"] for v in evidence["content_views"].values()))
            validate_quality_evidence(evidence, self.fx.retriever)

    def test_empty_population_insufficient_and_invalid_inputs_raise(self) -> None:
        query = gate_query(self.fx)
        evidence = self.fx.retriever.quality_evidence(**{**query, "current_regime": "CHOPPY"})
        self.assertEqual(evidence["gate"]["status"], "INSUFFICIENT_EVIDENCE")
        self.assertTrue(all(v["fallback_to_original"] for v in evidence["content_views"].values()))
        for options in ({"requested_k": True}, {"requested_k": 4}, {"requested_k": np.int64(3)},
                        {"enable_bayesian_prior": 1}, {"gate_version": "unknown"}, {"outcome": "WIN"},
                        {"selector": None}, {"query_features": {}}, {"min_conditional_count": 0}):
            with self.subTest(options=str(options)), self.assertRaises(ValueError):
                self.fx.retriever.quality_evidence(**{**query, **options})

    def test_rehashed_corruption_cannot_bypass_semantic_validator(self) -> None:
        query = gate_query(self.fx)
        evidence = self.fx.retriever.quality_evidence(**query)
        for mutate in (lambda e: e["gate"].update(stats_ready=False),
                       lambda e: e["statistics"].update(population_count=999),
                       lambda e: e["content_views"]["stats_only"].update(visible_k=1),
                       lambda e: e["config"].update(min_conditional_count=0),
                       lambda e: e["selection"]["metadata"]["selected_ids"].reverse()):
            changed = deepcopy(evidence)
            mutate(changed)
            changed["base_evidence_sha256"] = digest({k:v for k,v in changed.items() if k != "base_evidence_sha256"})
            with self.assertRaises(ValueError):
                validate_quality_evidence(changed, self.fx.retriever, selector=query["selector"], query_features=query["query_features"])


class QualityGatePointTests(unittest.TestCase):
    def test_sealed_full_source_disabled_and_legacy_unchanged(self) -> None:
        with patch("prior_context_test_support.pd.bdate_range", return_value=pd.bdate_range("2019-08-01", periods=700)):
            fx = ContextFixture()
        self.addCleanup(fx.close)
        for row in fx.records:
            row["regime"] = fx.regime["regime_name"]
        fx.publish_bank("a" * 64)
        adapter = fx.adapter()
        point = adapter.prepare("FPT", fx.cutoff)
        with self.assertRaises(ValueError):
            point.quality_evidence({})
        shared = point.bind_full(fx.full(point))
        snapshot = deepcopy(shared)
        index = adapter.build_price_feature_index()
        legacy = point.retrieve(shared)
        with (patch.object(point, "bind_full", side_effect=AssertionError("Không gọi lại Full")),
              patch.object(adapter, "execution_data", side_effect=AssertionError("Không đọc query outcome"))):
            evidence = point.quality_evidence(shared, index)
        self.assertEqual(evidence["gate"]["status"], "INSUFFICIENT_EVIDENCE")
        for options in ({"k": 0}, {"enable_bayesian_prior": False}):
            projection = {**shared, "prior_config": {**shared["prior_config"], **options}}
            with patch.object(point, "price_features", side_effect=AssertionError("Không cần feature")):
                self.assertEqual(point.quality_evidence(projection)["gate"]["status"], "DISABLED")
        self.assertEqual(shared, snapshot)
        self.assertEqual(point.retrieve(shared), legacy)
        path = fx.root / "data/execution_prices/FPT.events.json"
        path.write_bytes(path.read_bytes() + b" ")
        with patch.object(adapter._retriever, "quality_evidence", side_effect=AssertionError("Nguồn sai phải dừng")):
            with self.assertRaises(ValueError):
                point.quality_evidence(shared, index)
