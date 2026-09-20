import json
import tempfile
import unittest
from pathlib import Path

from scripts.analyze_sentiment_coverage import analyze_symbol, classify_scorer


class SentimentCoverageTests(unittest.TestCase):
    def test_scorer_requires_explicit_provenance(self):
        self.assertEqual(classify_scorer({"confidence": 0.5}), "unknown")
        self.assertEqual(
            classify_scorer({"scorer": "5CD-AI/Vietnamese-Sentiment-visobert"}),
            "visobert",
        )
        self.assertEqual(
            classify_scorer({"scorer": "viquant-lexicon-v1", "is_fallback": True}),
            "lexicon",
        )

    def test_symbol_summary_counts_dates_scorers_and_90_day_windows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "backtest_result").mkdir()
            cache = {
                "symbol": "FPT",
                "saved_at": "2026-09-20T00:00:00",
                "scored_articles": [
                    {
                        "url": "https://example.com/a",
                        "date_parsed": "2026-03-31",
                        "scorer": "5CD-AI/Vietnamese-Sentiment-visobert",
                    },
                    {
                        "url": "https://example.com/b",
                        "date": "01/04/2026",
                        "scorer": "viquant-lexicon-v1",
                        "is_fallback": True,
                    },
                    {
                        "url": "https://example.com/c",
                        "date_parsed": "2026-04-01",
                        "confidence": 0.5,
                    },
                    {"url": "https://example.com/d", "date": ""},
                ],
            }
            benchmark = {
                "symbol": "FPT",
                "n_tests": 2,
                "test_points": [
                    {"window_end": "2026-04-01"},
                    {"window_end": "2026-07-01"},
                ],
            }
            (root / "sentiment_cache_FPT.json").write_text(
                json.dumps(cache), encoding="utf-8"
            )
            (root / "backtest_result" / "backtest_FPT_fixture.json").write_text(
                json.dumps(benchmark), encoding="utf-8"
            )

            row = analyze_symbol(root, "FPT")

        self.assertEqual(row["total_articles"], 4)
        self.assertEqual(row["dated_articles"], 3)
        self.assertEqual(row["verified_visobert_articles"], 1)
        self.assertEqual(row["verified_lexicon_articles"], 1)
        self.assertEqual(row["unknown_scorer_articles"], 2)
        self.assertEqual(row["mean_articles_90d"], 1.5)
        self.assertEqual(row["min_articles_90d"], 0)
        self.assertEqual(row["max_articles_90d"], 3)
        self.assertEqual(row["test_points_ge_8_articles"], 0)


if __name__ == "__main__":
    unittest.main()
