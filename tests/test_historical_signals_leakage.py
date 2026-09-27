"""Kiểm cutoff giá, tin và xử lý lỗi nghiên cứu khi trích tín hiệu."""

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

import test_historical_signals as fixtures
from agents.alpha_agent import _compute_all_alphas, create_alpha_agent
from core.historical_signals import FrozenSentimentSnapshot, HistoricalSignalExtractor
from default_config import DEFAULT_CONFIG


def article(published, score=0.8):
    return {"date_parsed": published, "title": "Tin thử nghiệm", "url": "https://example.test/article",
            "label": "positive", "numeric_score": score, "confidence": 0.9}


class HistoricalSignalsLeakageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.HistoricalSignalTests.setUpClass()

    def test_only_dated_past_news_reaches_alpha(self):
        cutoff = fixtures.HistoricalSignalTests.cutoff
        news = [article(cutoff), article(None), article("2025-01-01", float("nan")), article("2018-01-01")]
        snapshot = FrozenSentimentSnapshot("FPT", cutoff, news)
        self.assertEqual(snapshot.articles, [article(cutoff)])
        self.assertFalse(snapshot.data["is_reliable"])
        self.assertEqual(snapshot.data["main_sentiment"]["label"], "neutral")
        with self.assertRaises(ValueError):
            snapshot.get_sentiment_at("FPT", "2025-01-01", None)

    def test_future_prices_and_news_do_not_change_endpoint_or_cache(self):
        frame = fixtures.HistoricalSignalTests.frame.copy()
        cutoff = fixtures.HistoricalSignalTests.cutoff
        news = [article(cutoff), article(None), article("2025-01-01")]
        graph = Mock()
        graph.invoke.return_value = copy.deepcopy(fixtures.REPORTS)
        alpha = Mock(side_effect=fixtures.fake_alpha)
        with tempfile.TemporaryDirectory() as directory, \
                patch("utils.static_util.generate_kline_image", return_value={}), \
                patch("utils.static_util.generate_trend_image", return_value={}):
            extractor = HistoricalSignalExtractor(graph, alpha, directory, DEFAULT_CONFIG,
                                                  execution_loader=lambda symbol: (frame.copy(), []),
                                                  article_loader=lambda symbol: news)
            result = extractor.extract("FPT", cutoff)
            frame.loc[frame["Datetime"] > cutoff, ["Open", "High", "Low", "Close"]] = np.nan
            news[-1]["numeric_score"] = float("inf")
            self.assertEqual(extractor.extract("FPT", cutoff), result)
            state = graph.invoke.call_args.args[0]
            self.assertTrue((state["point_in_time_df"]["Datetime"] <= cutoff).all())
            self.assertEqual(set(state["point_in_time_df"]), {"Datetime", "Open", "High", "Low", "Close", "Volume"})
            self.assertEqual(graph.invoke.call_count, 1)

    def test_alpha_mutation_does_not_change_shared_reports(self):
        graph = Mock()
        graph.invoke.return_value = copy.deepcopy(fixtures.REPORTS)

        def mutate_alpha(state):
            state["trend_report"] = "MODIFIED"
            state["point_in_time_df"].loc[:, "Close"] = 999
            return fixtures.fake_alpha(state)

        with tempfile.TemporaryDirectory() as directory, \
                patch("utils.static_util.generate_kline_image", return_value={}), \
                patch("utils.static_util.generate_trend_image", return_value={}):
            extractor = HistoricalSignalExtractor(graph, mutate_alpha, directory, DEFAULT_CONFIG,
                                                  article_loader=lambda symbol: [])
            result = extractor.extract("FPT", fixtures.HistoricalSignalTests.cutoff)
            self.assertEqual(result["reports"]["trend_report"], fixtures.REPORTS["trend_report"])
            self.assertEqual(graph.invoke.return_value, fixtures.REPORTS)

    def test_missing_warmup_rejected_before_upstream(self):
        graph = Mock()
        with tempfile.TemporaryDirectory() as directory:
            extractor = HistoricalSignalExtractor(graph, fixtures.fake_alpha, directory, DEFAULT_CONFIG,
                                                  article_loader=lambda symbol: [])
            early = fixtures.HistoricalSignalTests.frame["Datetime"].iloc[598].strftime("%Y-%m-%d")
            with self.assertRaises(ValueError):
                extractor.extract("FPT", early)
            graph.invoke.assert_not_called()

    def test_strict_alpha_does_not_swallow_sentiment_leakage(self):
        store = Mock()
        store.get_sentiment_at.side_effect = ValueError("Tin vượt cutoff")
        state = {"stock_name": "FPT", "time_frame": "1d", "kline_data": {}, "is_backtest": True,
                 "sentiment_store": store, "window_end_date": "2020-06-01"}
        with self.assertRaises(ValueError):
            create_alpha_agent(None, strict_research_mode=True)(state)

    def test_strict_alpha_does_not_swallow_selector_leakage(self):
        with patch("agents.alpha_agent._extract_tech_vars", return_value={}), \
                patch("agents.alpha_agent.select_top_alphas", side_effect=AssertionError("Prefix có tương lai")):
            with self.assertRaises(AssertionError):
                _compute_all_alphas({}, {}, {}, "FPT", is_backtest=True, strict_research_mode=True)

    def test_returned_sentiment_leakage_is_rejected_without_final_record(self):
        def bad_alpha(state):
            result = fixtures.fake_alpha(state)
            result["sentiment_data"]["scored_articles"] = [article("2025-01-01")]
            return result

        graph = Mock()
        graph.invoke.return_value = copy.deepcopy(fixtures.REPORTS)
        with tempfile.TemporaryDirectory() as directory, \
                patch("utils.static_util.generate_kline_image", return_value={}), \
                patch("utils.static_util.generate_trend_image", return_value={}):
            extractor = HistoricalSignalExtractor(graph, bad_alpha, directory, DEFAULT_CONFIG, article_loader=lambda symbol: [])
            with self.assertRaises(ValueError):
                extractor.extract("FPT", fixtures.HistoricalSignalTests.cutoff)
            from core.bayesian_memory import read_json
            checkpoint = read_json(Path(directory) / f"FPT-{fixtures.HistoricalSignalTests.cutoff}.json")
            self.assertEqual(checkpoint["payload"]["stage"], "UPSTREAM_COMPLETE")
            self.assertNotIn("result", checkpoint["payload"])


if __name__ == "__main__":
    unittest.main()
