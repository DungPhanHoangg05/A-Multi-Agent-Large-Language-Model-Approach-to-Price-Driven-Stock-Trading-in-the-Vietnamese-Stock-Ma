"""Kiểm thử chống rò rỉ bài báo không ngày trong sentiment backtest."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data_manager.sentiment_cache import SentimentCache


def _article(date_parsed, label="positive", score=0.5):
    return {
        "title": f"Tin {date_parsed or 'khong-ngay'}",
        "url": "https://example.test/article",
        "date_parsed": date_parsed,
        "label": label,
        "numeric_score": score,
        "confidence": 0.9,
    }


class SentimentLeakageTests(unittest.TestCase):
    def _cache_with(self, articles):
        cache = SentimentCache("FPT")
        cache._loaded = True
        cache._scored_articles = articles
        return cache

    def test_strict_mode_rejects_undated_and_returns_unreliable_neutral_when_sparse(self):
        cache = self._cache_with(
            [
                _article("2024-03-01", "positive", 0.8),
                _article("2024-03-15", "negative", -0.6),
                _article(None, "positive", 1.0),
                _article("2024-04-01", "positive", 1.0),
                _article("not-a-date", "positive", 1.0),
            ]
        )

        with patch("builtins.print"):
            data, report = cache.get_at(
                "2024-03-20",
                llm=None,
                window_days=90,
                min_articles=3,
            )

        self.assertFalse(data["is_reliable"])
        self.assertEqual(data["n_articles_used"], 2)
        self.assertEqual(data["main_sentiment"]["article_count"], 2)
        self.assertEqual(data["main_sentiment"]["label"], "neutral")
        self.assertEqual(data["main_sentiment"]["avg_score"], 0.0)
        self.assertIn("không đủ", report.lower())
        self.assertTrue(data["scored_articles"])
        cutoff = datetime.strptime("2024-03-20", "%Y-%m-%d")
        for article in data["scored_articles"]:
            self.assertTrue(article.get("date_parsed"))
            article_date = datetime.strptime(article["date_parsed"], "%Y-%m-%d")
            self.assertLessEqual(article_date, cutoff)

    def test_strict_mode_aggregates_only_dated_articles_when_enough_exist(self):
        cache = self._cache_with(
            [
                _article("2024-03-01", "positive", 0.5),
                _article("2024-03-10", "positive", 0.5),
                _article("2024-03-15", "neutral", 0.0),
                _article(None, "negative", -1.0),
                _article("2024-03-25", "negative", -1.0),
            ]
        )

        with patch("builtins.print"):
            data, _ = cache.get_at(
                "2024-03-20",
                llm=None,
                min_articles=3,
                strict_research_mode=True,
            )

        self.assertTrue(data["is_reliable"])
        self.assertEqual(data["n_articles_used"], 3)
        self.assertEqual(data["main_sentiment"]["article_count"], 3)
        self.assertEqual(
            [article["date_parsed"] for article in data["scored_articles"]],
            ["2024-03-01", "2024-03-10", "2024-03-15"],
        )

    def test_strict_mode_returns_unreliable_neutral_when_no_valid_article_exists(self):
        cache = self._cache_with(
            [
                _article(None),
                _article("2024-05-01"),
            ]
        )

        with patch("builtins.print"):
            data, _ = cache.get_at(
                "2024-03-20",
                llm=None,
                strict_research_mode=True,
            )

        self.assertFalse(data["is_reliable"])
        self.assertEqual(data["n_articles_used"], 0)
        self.assertEqual(data["scored_articles"], [])


if __name__ == "__main__":
    unittest.main()
