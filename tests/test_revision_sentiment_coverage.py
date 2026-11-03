"""Kiểm T06: cutoff, tỷ lệ, missing/neutral, replay và asset lineage offline."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.revision_audit import DEFAULT_SYMBOLS, sha256_file
from core.revision72_data import REVISION, audit_articles, news_from_scores
from core.revision72_run import signed
from core.revision_common_study import FrozenSentiment, digest, read_json, write_json
from core.revision_sentiment_coverage import (
    INVENTORY, availability, build_coverage, peers, proportions, run_audit, scorer_tables, summarize_rows, window_coverage,
)
from core.revision_sentiment_inventory import BANK, RUN, run_audit as inventory_audit, verify_release


def article(identity: str, **kwargs: object) -> dict:
    """Bản tin giả lập có identity riêng; không dùng response/model thật."""
    return {"article_id": identity, "date_parsed": "2026-01-02", "scorer": "visobert", "numeric_score": 0.0, **kwargs}


class WindowCoverageTests(unittest.TestCase):
    """Các biên kiểm tra độc lập với cache hiện tại và kết quả giao dịch."""

    def test_counts_and_percentages_share_denominator_and_empty_is_null(self) -> None:
        result = proportions(["visobert", "lexicon", "unknown"])
        self.assertEqual(sum(result["counts"].values()), result["total"])
        for key in result["counts"]:
            self.assertEqual(result["percentages"][key], 100 * result["counts"][key] / result["total"])
        self.assertTrue(all(value is None for value in proportions([])["percentages"].values()))

    def test_date_only_next_day_and_missing_different_from_zero_neutral(self) -> None:
        articles = [article(str(i)) for i in range(3)]
        same_day = window_coverage(articles, "2026-01-02")
        next_day = window_coverage(articles, "2026-01-03")
        self.assertTrue(same_day["sentiment_missing"])
        self.assertIsNone(same_day["sentiment_score"])
        self.assertEqual((next_day["valid_score_articles"], next_day["sentiment_score"], next_day["sentiment_state"]), (3, 0.0, "neutral"))
        sparse = window_coverage(articles[:2], "2026-01-03")
        self.assertEqual(sparse["valid_score_articles"], 2)
        self.assertIsNone(sparse["sentiment_score"])
        self.assertEqual(sparse["sentiment_state"], "missing")

    def test_explicit_availability_timezone_and_90_day_inclusive_bounds(self) -> None:
        items = [article("lower", available_at="2026-01-01T16:59:59+00:00"),
                 article("before", available_at="2026-01-01T23:59:58+07:00"),
                 article("upper", available_at="2026-04-01T23:59:59+07:00"),
                 article("after", available_at="2026-04-02T00:00:00+07:00")]
        result = window_coverage(items, "2026-04-01")
        self.assertEqual([r["article_id"] for r in result["article_membership"]], ["lower", "upper"])
        delayed = [article(str(i), available_at="2026-01-10T12:00:00+07:00") for i in range(3)]
        self.assertEqual(window_coverage(delayed, "2026-01-09")["valid_score_articles"], 0)
        self.assertEqual(window_coverage(delayed, "2026-01-10")["valid_score_articles"], 3)

    def test_unknown_and_invalid_scores_do_not_create_sentiment_evidence(self) -> None:
        unknown = [article(str(i), scorer="unknown", numeric_score=0.35) for i in range(5)]
        row = window_coverage(unknown, "2026-01-03")
        self.assertEqual(row["article_records"]["counts"]["unknown"], 5)
        self.assertEqual(row["valid_score_articles"], 0)
        self.assertTrue(row["sentiment_missing"])
        invalid = [article("nan", numeric_score=float("nan")), article("range", numeric_score=1.1), article("none", numeric_score=None)]
        self.assertEqual(window_coverage(invalid, "2026-01-03")["valid_score_articles"], 0)
        self.assertIsNone(availability(article("date", date_parsed="invalid")))

    def test_duplicate_identity_is_not_three_independent_articles(self) -> None:
        row = window_coverage([article("same")] * 3, "2026-01-03")
        self.assertEqual((row["article_records"]["total"], row["unique_article_identities"], row["valid_score_articles"]), (3, 1, 1))
        self.assertTrue(row["sentiment_missing"])
        with self.assertRaisesRegex(ValueError, "mâu thuẫn"):
            window_coverage([article("same"), article("same", numeric_score=0.5)], "2026-01-03")

    def test_mixed_vlu_window_does_not_count_unknown_as_valid_score(self) -> None:
        items = [article("v"), article("l", scorer="lexicon"), article("u", scorer="unknown")]
        row = window_coverage(items, "2026-01-03")
        self.assertEqual(row["article_records"]["counts"], {"visobert": 1, "lexicon": 1, "unknown": 1})
        self.assertEqual(row["valid_score_articles"], 2)
        self.assertTrue(row["sentiment_missing"])
        row = window_coverage(items + [article("l2", scorer="lexicon")], "2026-01-03")
        self.assertEqual(row["valid_score_articles"], 3)
        self.assertFalse(row["sentiment_missing"])

    def test_corpus_alias_provenance_conflict_stays_unknown(self) -> None:
        inventory = {"legacy_records": [{"symbol": "FPT", "article_id": "same", "legacy_scorer": {"category": "visobert"}},
                                         {"symbol": "VNM", "article_id": "same", "legacy_scorer": {"category": "lexicon"}}],
                     "frozen_news_records": []}
        tables = scorer_tables(inventory)
        self.assertEqual(tables["legacy_cache_records"]["counts"], {"visobert": 1, "lexicon": 1, "unknown": 0})
        self.assertEqual(tables["legacy_unique_identities"]["counts"]["unknown"], 1)
        self.assertIsNone(tables["frozen_news_symbol_article_records"]["percentages"]["visobert"])

    def test_pooled_and_macro_use_declared_symbol_denominators(self) -> None:
        absent = window_coverage([], "2026-01-03")
        present = window_coverage([article(str(i)) for i in range(3)], "2026-01-03")
        no_peers = peers({"related_companies": [], "related_sentiment": {}})
        rows = [{"symbol": "FPT", "coverage": absent, "peers": no_peers}, {"symbol": "FPT", "coverage": present, "peers": no_peers},
                {"symbol": "VNM", "coverage": present, "peers": no_peers}]
        summary = summarize_rows(rows)
        self.assertAlmostEqual(summary["pooled"]["coverage_pct"], 200 / 3)
        self.assertEqual(summary["macro_unweighted_symbol_coverage_pct"], 75.0)
        self.assertEqual(summary["pooled"]["peer_available_cutoffs"], 0)
        self.assertIsNone(summarize_rows([])["pooled"]["coverage_pct"])


class CoverageReleaseTests(unittest.TestCase):
    """Integration qua inventory, native get_at/FrozenSentiment và signed assets."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory(); self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.bank, self.run, self.inventory = self.root / BANK, self.root / RUN, self.root / INVENTORY
        for symbol in DEFAULT_SYMBOLS:
            rows = [{"title": f"Tin {symbol} {i}", "content": "Excerpt giả lập", "url": f"https://cafef.vn/{symbol}-{i}-188260101123456.chn",
                     "date_parsed": "2026-01-01", "date": "01/01/2026", "numeric_score": 0.0, "label": "neutral", "confidence": 0.5} for i in range(3)]
            if symbol == "FPT":
                rows.append({**rows[0], "url": "https://cafef.vn/FPT-extra-188260103123456.chn", "date_parsed": "2026-01-03", "numeric_score": 0.5, "label": "positive"})
            write_json(self.root / f"sentiment_cache_{symbol}.json", {"symbol": symbol, "scored_articles": rows})
            points = [{"test_id": i, "window_end": day} for i, day in enumerate(("2026-01-01", "2026-01-03"), 1)]
            write_json(self.root / f"outputs/backtest_result/backtest_{symbol}_fixture.json", {"symbol": symbol, "n_tests": 2, "test_points": points})
        audit = audit_articles(self.root)
        scores = {"revision": REVISION, "mapping": {"0": "NEG", "1": "POS", "2": "NEU"}, "max_length": 256,
                  "scores": {a["article_id"]: {"numeric_score": 0.0} for a in audit["articles"]}}
        news = news_from_scores(audit, scores)
        units = [{"id": f"FPT_fixture_{i}", "symbol": "FPT", "date": day, "fold": "fixture", "decision": i,
                  "verified_articles": 0 if i == 0 else 3} for i, day in enumerate(("2026-01-01", "2026-01-02"))]
        bank = {"news_hash": digest(news), "article_sources": audit["sources"], "units": units}
        bank["bank_id"] = digest(bank)
        for name, value in (("article_audit.json", audit), ("local_scores.json", scores), ("news.json", news), ("manifest.json", bank)):
            write_json(self.bank / name, value)
        queue = {"runtime": {"python": sys.version.split()[0]}, "sources": [], "panel": [units[1]],
                 "jobs": [{"phase": "main", "context": {"unit_id": units[0]["id"]}}, {"phase": "upstream", "context": {"unit_id": units[1]["id"]}}]}
        write_json(self.run / "manifest.json", signed(queue))
        source_names = ("core/revision_sentiment_inventory.py", "scripts/audit_sentiment_inventory.py", "tests/test_revision_sentiment_inventory.py",
                        "data_manager/sentiment_cache.py", "core/revision72_data.py", "core/revision_common_study.py", "core/revision_baselines.py",
                        "core/revision_minimal_run.py", "scripts/analyze_sentiment_coverage.py", "core/revision_sentiment_coverage.py",
                        "scripts/audit_revision_sentiment_coverage.py", "tests/test_revision_sentiment_coverage.py", "agents/sentiment_agent.py", "agents/alpha_agent.py")
        for name in source_names:
            path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b"fixture source\n")
        inventory_audit(self.root, self.inventory)
        for unit in units:
            data, report = FrozenSentiment(news).get_sentiment_at("FPT", unit["date"])
            asset = {"bank_id": bank["bank_id"], "sentiment_data": data, "sentiment_report": report,
                     "sentiment_norm": {"is_reliable": False, "raw_avg_score": 0.0}}
            write_json(self.bank / f"features/FPT_{unit['decision']}.json", signed(asset))
        for name in ("socket.socket.connect", "socket.getaddrinfo", "data_manager.sentiment_cache.SentimentCache.preload",
                     "data_manager.sentiment_cache._crawl_articles_full", "data_manager.sentiment_cache._score_articles", "core.revision72_data.score_local"):
            blocker = patch(name, side_effect=AssertionError("Cấm network/preload/rescore trong T06"))
            blocker.start(); self.addCleanup(blocker.stop)

    def build(self) -> tuple[dict, dict, set[Path]]:
        """Tạo coverage từ đúng release fixture, không đọc dữ liệu repo thật."""
        return build_coverage(self.root, self.inventory, self.bank, self.run)

    def test_legacy_same_day_and_unknown_provenance_are_kept_separate(self) -> None:
        coverage, summary, _ = self.build()
        row = next(r for r in coverage["legacy_cutoffs"] if r["symbol"] == "FPT" and r["cutoff"] == "2026-01-03")
        self.assertEqual(row["runtime_replay"]["article_records"]["total"], 4)
        self.assertEqual(row["runtime_replay"]["same_day_article_records"], 1)
        self.assertTrue(row["runtime_replay"]["runtime_is_reliable"])
        self.assertEqual(row["coverage"]["article_records"]["total"], 3)
        self.assertEqual(row["coverage"]["valid_score_articles"], 0)
        self.assertIsNone(row["coverage"]["sentiment_score"])
        self.assertEqual(summary["legacy"]["pooled"]["cutoffs"], 18)

    def test_release_matches_native_assets_and_keeps_panel_denominators(self) -> None:
        coverage, summary, _ = self.build()
        self.assertEqual(summary["release"]["main"]["pooled"]["cutoffs"], 2)
        self.assertEqual(summary["release"]["factorial"]["pooled"]["cutoffs"], 1)
        self.assertEqual(summary["release"]["upstream"]["pooled"]["cutoffs"], 1)
        self.assertEqual(summary["release"]["main"]["pooled"]["coverage_pct"], 50.0)
        available = coverage["release_cutoffs"][1]
        self.assertEqual(available["coverage"]["sentiment_state"], "neutral")
        self.assertFalse(available["normalizer_is_reliable"])
        self.assertEqual(available["peers"]["available_peer_count"], 0)
        self.assertEqual(coverage["scorer_tables"]["legacy_cache_records"]["percentages"]["unknown"], 100.0)
        self.assertEqual(coverage["scorer_tables"]["frozen_news_symbol_article_records"]["percentages"]["visobert"], 100.0)

    def test_changed_inventory_source_and_resigned_wrong_asset_are_rejected(self) -> None:
        path = self.bank / "features/FPT_1.json"
        asset = read_json(path); asset.pop("sha256"); asset["sentiment_data"]["is_unavailable"] = True
        write_json(path, signed(asset))
        with self.assertRaisesRegex(ValueError, "asset khác"):
            self.build()
        path = self.root / "sentiment_cache_FPT.json"
        value = read_json(path); value["scored_articles"][0]["numeric_score"] = 0.8; write_json(path, value)
        with self.assertRaisesRegex(ValueError, "Hash sai"):
            self.build()

    def test_export_preserves_inputs_blocks_overwrite_and_hashes_detect_tampering(self) -> None:
        before = {p: sha256_file(p) for p in self.root.rglob("*") if p.is_file()}
        output = self.root / "outputs/revision/coverage_fixture"
        run_audit(self.root, output)
        self.assertTrue(verify_release(self.root, output) > 0)
        self.assertTrue(all(sha256_file(p) == checksum for p, checksum in before.items()))
        self.assertFalse((self.root / "paper").exists())
        with self.assertRaisesRegex(ValueError, "không ghi đè"):
            run_audit(self.root, output)
        with self.assertRaisesRegex(ValueError, "Output phải"):
            run_audit(self.root, self.root / "paper/generated")
        value = read_json(output / "coverage.json"); value["release_cutoffs"] = []; write_json(output / "coverage.json", value)
        with self.assertRaisesRegex(ValueError, "Hash sai"):
            verify_release(self.root, output)


if __name__ == "__main__":
    unittest.main()
