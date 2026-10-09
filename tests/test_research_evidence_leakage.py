"""PIT evidence v2 và cohort bốn mã: chặn future/model/outcome trước LLM."""

from __future__ import annotations

from copy import deepcopy
import json
from typing import Any
import unittest
from unittest.mock import patch

from core.bayesian_memory import SYMBOLS
from core.historical_signals import digest
from core.prior_backtest import PriorBacktestRunner
from core.prior_evidence_v2 import retrieve_evidence, validate_evidence, format_evidence_prefix
from core import research_cohort
from prior_context_test_support import model_file, write_json
import test_research_evidence_v2 as evidence_support
import test_research_fault_recovery as cohort_support


class ResearchEvidenceLeakageTests(unittest.TestCase):
    """Kiểm bằng kho có QA thật, không mock thuật toán lọc/ranking/posterior."""

    def setUp(self) -> None:
        self.fixture = evidence_support.EvidenceV2Tests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_equal_exit_and_future_cycles_excluded_before_statistics_and_ranking(self) -> None:
        """Exit bằng cutoff không góp cả support lẫn ví dụ vào evidence."""
        fx = self.fixture.fx
        fx.rows = [fx.record("FPT", i, "BULL") for i in (0, 3, 6)] + [fx.record("MWG", 0, "BULL")]
        fx.publish_fixture()
        retriever = fx.create()
        query = fx.query(as_of_date=fx.rows[1]["exit_date"])
        evidence = retrieve_evidence(retriever, **query, config={"min_population_count": 1})
        self.assertEqual(evidence["population_count"], 1)
        self.assertEqual(evidence["selected_ids"], [fx.rows[0]["episode_id"]])
        self.assertEqual(evidence["metrics"]["win_rate_long"]["support_count"], 1)
        self.assertEqual(evidence["metrics"]["win_rate_long"]["posterior_mean"], 1/3)
        self.assertTrue(all(row["exit_date"] < query["as_of_date"] for row in evidence["tasks"]))
        for exit_date in (query["as_of_date"], fx.rows[2]["exit_date"]):
            with self.subTest(exit_date=exit_date):
                forged = deepcopy(evidence)
                forged["tasks"][0]["exit_date"] = exit_date
                forged["evidence_sha256"] = digest({k: v for k, v in forged.items() if k != "evidence_sha256"})
                with self.assertRaises(ValueError):
                    validate_evidence(forged)

    def test_injected_unclosed_population_fails_before_similarity_ranking(self) -> None:
        """Pool sai PIT bị từ chối thay vì âm thầm chọn ví dụ future."""
        fx = self.fixture.fx
        retriever = self.fixture.retriever
        query = fx.query(as_of_date=fx.rows[0]["exit_date"])
        pool = retriever.prepare_query(**query, k=3, mode="bayesian_regime", scope="same_symbol", seed=42)
        pool["regime_population"] = [deepcopy(fx.rows[0])]
        with patch.object(retriever, "prepare_query", return_value=pool), \
             patch.object(retriever, "_select_similarity", side_effect=AssertionError("Không rank pool future")), \
             self.assertRaises(ValueError):
            retrieve_evidence(retriever, **query, config={"min_population_count": 1})


class ResearchCohortLeakageTests(unittest.TestCase):
    """Chạy public cohort và Decision thật với client giả trên bốn mã."""

    def setUp(self) -> None:
        self.fixture = cohort_support.CohortFaultRecoveryTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_dated_news_only_and_query_outcome_absent_from_every_v2_decision(self) -> None:
        """24 prompt dùng tin PIT; evidence v2 không nhận nhãn/evaluation query."""
        fx = self.fixture
        for symbol in SYMBOLS:
            articles = [{"date_parsed": fx.fx.cutoff, "title": f"TIN_HOP_LE_{i}",
                "label": "positive", "numeric_score": .8, "confidence": .9} for i in range(3)]
            articles += [{**articles[0], "date_parsed": fx.fx.day(645), "title": "TIN_TUONG_LAI"},
                         {**articles[0], "date_parsed": None, "title": "TIN_KHONG_NGAY"}]
            write_json(fx.fx.root / f"run/inputs/news/{symbol}.json", {"symbol": symbol, "scored_articles": articles})
        fx.adapter = fx.fx.adapter()
        fx.plan["matrix"] = "research_v2"
        fx.runner = PriorBacktestRunner(fx.engine, fx.adapter, fx.builder,
            execution_mode="offline_fixture", quota_policy="request_admission_v2", durable_stages=True)
        original = research_cohort.create_final_trade_decider
        seen = []
        def factory(*args: Any, **kwargs: Any) -> Any:
            node = original(*args, **kwargs)
            def inspect(state: dict[str, Any]) -> dict[str, Any]:
                self.assertTrue(set(state).isdisjoint({"evaluation", "outcome", "entry_open", "exit_close", "actual_direction",
                    "point_in_time_df", "sentiment_store", "sentiment_data"}))
                seen.append(state["stock_name"])
                return node(state)
            return inspect
        query_fields = {"symbol", "as_of_date", "current_regime", "current_signals", "config"}
        evidence = fx.adapter._retriever.retrieve_evidence
        queries = []
        def check_query(**kwargs: Any) -> dict[str, Any]:
            self.assertEqual(set(kwargs), query_fields)
            queries.append(kwargs["symbol"])
            return evidence(**kwargs)
        with patch.object(research_cohort, "create_final_trade_decider", side_effect=factory), \
             patch.object(fx.adapter._retriever, "retrieve_evidence", side_effect=check_query):
            result = fx.run_cohort()
        fx.assert_complete(result)
        self.assertEqual(set(seen), SYMBOLS)
        self.assertEqual(set(queries), SYMBOLS)
        self.assertEqual(fx.llm.calls, 24)
        for prompt in fx.llm.prompts:
            self.assertNotIn("TIN_TUONG_LAI", str(prompt))
            self.assertNotIn("TIN_KHONG_NGAY", str(prompt))
        for symbol in SYMBOLS:
            doc = research_cohort.read_envelope(fx.point_path(symbol))
            news = doc["source_proof"]["news"]
            self.assertEqual(news["visible_count"], 3)
            self.assertEqual(news["excluded_counts"], {"undated": 1, "future": 1, "outside_window": 0})
            for article in doc["shared"]["full_bundle"]["sentiment_data"]["scored_articles"]:
                self.assertIsNotNone(article["date_parsed"])
                self.assertLessEqual(article["date_parsed"], fx.fx.cutoff)
            v2 = research_cohort.read_envelope(fx.output / f"v2/{symbol}-{fx.fx.cutoff}.json")
            self.assertLessEqual(len(format_evidence_prefix(v2["evidence"])), 600)
            json.dumps(v2, allow_nan=False)

    def test_future_model_and_invalid_freeze_stop_cohort_before_upstream(self) -> None:
        """Không gọi agent hoặc refit khi model học tới/sau ngày query."""
        fx = self.fixture
        for freeze in (fx.fx.cutoff, fx.fx.day(645)):
            with self.subTest(freeze=freeze):
                adapter = fx.fx.adapter(provider_mode="fixed_train_oos",
                    frozen_artifact_path="model/fixed.json", freeze_as_of_date=freeze)
                runner = PriorBacktestRunner(fx.engine, adapter, fx.builder,
                    execution_mode="offline_fixture", durable_stages=True)
                with self.assertRaises(ValueError):
                    runner.run_cohort(fx.plan, output_dir=fx.output)
        path = fx.fx.root / f"run/regimes/VNINDEX-{fx.fx.cutoff}.json"
        model_file(path, fx.fx.vnindex.iloc[:646])
        adapter = fx.fx.adapter()
        runner = PriorBacktestRunner(fx.engine, adapter, fx.builder,
            execution_mode="offline_fixture", durable_stages=True)
        with self.assertRaises(ValueError):
            runner.run_cohort(fx.plan, output_dir=fx.output)
        self.assertEqual(fx.llm.calls, 0)
        self.assertEqual(fx.events, [])
        self.assertFalse(fx.output.exists())


if __name__ == "__main__":
    unittest.main()
