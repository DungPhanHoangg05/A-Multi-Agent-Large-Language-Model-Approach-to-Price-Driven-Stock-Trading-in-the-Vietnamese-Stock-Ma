"""Kiểm T05 qua disk loader và fixtures provenance, không gọi network/scorer."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.revision_audit import DEFAULT_SYMBOLS
from core.revision72_data import REVISION, audit_articles, news_from_scores
from core.revision72_run import signed
from core.revision_common_study import digest, read_json, write_json
from core.revision_sentiment_inventory import (
    BANK, RUN, build_inventory, load_disk_cache, run_audit, runtime_date, scorer_provenance, verify_release,
)
from data_manager.sentiment_cache import SentimentCache


class SentimentInventoryTests(unittest.TestCase):
    """Mỗi fixture tách cache records, aliases, score mới và test points."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.bank, self.run = self.root / BANK, self.root / RUN
        self.benchmarks = self.root / "outputs/backtest_result"
        shared = {"title": "Bài chung", "content": "Nội dung excerpt", "url": "https://cafef.vn/a-188260401123456.chn?alias=1",
                  "date": "01/04/2026", "date_parsed": "2026-04-01", "numeric_score": 0.35, "confidence": 0.5}
        self.caches = {symbol: [] for symbol in DEFAULT_SYMBOLS}
        self.caches["FPT"] = [shared, {"title": "Không ngày", "content": "Excerpt không ngày", "url": "https://cafef.vn/undated",
                                      "date": "02/04/2026", "date_parsed": None}, deepcopy(shared),
                               {"title": "ViSoBERT tường minh", "content": "Excerpt V", "url": "https://cafef.vn/v-188260331123456.chn",
                                "date_parsed": "2026-03-31", "scorer": "5CD-AI/Vietnamese-Sentiment-visobert", "is_fallback": False}]
        alias = deepcopy(shared); alias["url"] = "https://cafef.vn/a-188260401123456.chn?alias=2"
        self.caches["VNM"] = [alias, {"title": "Lexicon tường minh", "content": "Excerpt L", "url": "https://cafef.vn/l-188260402123456.chn",
                                    "date_parsed": "2026-04-02", "scorer": "viquant-lexicon-v1", "is_fallback": True}]
        for symbol, articles in self.caches.items():
            write_json(self.root / f"sentiment_cache_{symbol}.json", {"symbol": symbol, "saved_at": "fixture", "scored_articles": articles})
            points = [{"window_end": "2026-04-03"}] * (2 if symbol == "FPT" else 1)
            write_json(self.benchmarks / f"backtest_{symbol}_fixture.json", {"symbol": symbol, "n_tests": len(points), "test_points": points})
        audit = audit_articles(self.root)
        scores = {"revision": REVISION, "mapping": {"0": "NEG", "1": "POS", "2": "NEU"}, "max_length": 256,
                  "files": [], "scores": {a["article_id"]: {"numeric_score": 0.2} for a in audit["articles"] if a["eligible_source"]}}
        news = news_from_scores(audit, scores)
        for name, value in (("article_audit.json", audit), ("local_scores.json", scores), ("news.json", news)):
            write_json(self.bank / name, value)
        manifest = {"news_hash": digest(news), "article_sources": audit["sources"], "units": [{"id": "fixture-unit"}]}
        write_json(self.bank / "manifest.json", {**manifest, "bank_id": digest(manifest)})
        write_json(self.run / "manifest.json", signed({"runtime": {"python": sys.version.split()[0]},
                                                       "jobs": [{"phase": "main"}, {"phase": "upstream"}], "sources": []}))
        for filename in ("core/revision_sentiment_inventory.py", "scripts/audit_sentiment_inventory.py", "tests/test_revision_sentiment_inventory.py",
                         "data_manager/sentiment_cache.py", "core/revision72_data.py", "core/revision_common_study.py", "core/revision_baselines.py",
                         "core/revision_minimal_run.py", "scripts/analyze_sentiment_coverage.py"):
            path = self.root / filename; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b"fixture source\n")
        for target in ("socket.socket.connect", "socket.getaddrinfo", "data_manager.sentiment_cache.SentimentCache.preload",
                       "data_manager.sentiment_cache._crawl_articles_full", "data_manager.sentiment_cache._score_articles", "core.revision72_data.score_local"):
            blocker = patch(target, side_effect=AssertionError("Cấm network/preload/rescore trong inventory"))
            blocker.start(); self.addCleanup(blocker.stop)

    def build(self) -> tuple[dict, dict, set[Path]]:
        """Dùng đường dẫn explicit giống CLI, không đổi cwd hoặc biến môi trường."""
        return build_inventory(self.root, self.root, self.benchmarks, self.bank, self.run)

    def test_disk_loader_used_even_for_empty_cache_without_preload(self) -> None:
        original = SentimentCache._load_from_disk
        seen = []

        def loader(instance: SentimentCache) -> int:
            """Quan sát loader thực, không thay payload trả về."""
            seen.append(instance.symbol)
            return original(instance)

        with patch.object(SentimentCache, "_load_from_disk", loader):
            inventory, summary, _ = self.build()
        self.assertEqual(seen, list(DEFAULT_SYMBOLS))
        self.assertEqual(summary["legacy"]["corpus"]["records"], 6)
        self.assertEqual(len(inventory["legacy_records"]), 6)

    def test_records_points_identities_duplicates_and_news_have_separate_denominators(self) -> None:
        inventory, summary, _ = self.build()
        corpus = summary["legacy"]["corpus"]
        self.assertEqual((corpus["records"], corpus["unique_article_identities"], corpus["duplicate_identity_excess"]), (6, 4, 2))
        self.assertEqual(summary["legacy"]["test_points_total"], 10)
        self.assertEqual(summary["evaluation_units"]["minimal_executions"], 2)
        self.assertEqual(summary["frozen_news"]["symbol_article_records"], 4)
        self.assertEqual(summary["frozen_news"]["unique_article_identities"], 3)
        self.assertEqual(summary["local_rescore"]["unique_scored_identities"], 3)
        duplicate = inventory["duplicates"]["article_id"][0]
        self.assertEqual(len(duplicate["records"]), 3)
        self.assertTrue(duplicate["cross_symbol"])
        fpt = next(r for r in summary["legacy"]["per_symbol"] if r["symbol"] == "FPT")
        self.assertEqual((fpt["records"], fpt["unique_article_identities"], fpt["duplicate_identity_excess"]), (4, 3, 1))

    def test_legacy_unknown_not_relabelled_by_new_rescore(self) -> None:
        inventory, summary, _ = self.build()
        first = inventory["legacy_records"][0]
        self.assertEqual(first["legacy_scorer"]["category"], "unknown")
        self.assertTrue(first["local_rescore_available"])
        self.assertEqual(summary["legacy"]["corpus"]["legacy_scorer_categories"], {"visobert": 1, "lexicon": 1, "unknown": 4})
        self.assertFalse(summary["local_rescore"]["financial_domain_validated"])

    def test_dates_and_raw_normalized_hashes_remain_explicit(self) -> None:
        inventory, summary, _ = self.build()
        first, alias = inventory["legacy_records"][0], inventory["legacy_records"][4]
        self.assertEqual(first["article_id"], alias["article_id"])
        self.assertEqual(first["url_normalized_sha256"], alias["url_normalized_sha256"])
        self.assertNotEqual(first["url_raw_sha256"], alias["url_raw_sha256"])
        undated = inventory["legacy_records"][1]
        self.assertEqual(undated["date_raw"], "02/04/2026")
        self.assertIsNone(undated["runtime_publication_date"])
        self.assertEqual(summary["legacy"]["corpus"]["undated_or_invalid_records"], 1)
        self.assertIsNone(runtime_date("2026-02-31"))

    def test_explicit_conflicting_or_missing_scorer_metadata(self) -> None:
        for record in ({"numeric_score": 0.35, "confidence": 0.5}, {"is_fallback": True}, {"model": "5CD-AI/other"}, {"scorer_backend": "local"}):
            self.assertEqual(scorer_provenance(record)["category"], "unknown")
        conflict = scorer_provenance({"scorer": "visobert", "is_fallback": True})
        self.assertEqual((conflict["category"], conflict["status"]), ("unknown", "conflicting_metadata"))
        self.assertEqual(scorer_provenance({"scorer": "visobert", "scorer_backend": "lexicon-fallback"})["category"], "unknown")

    def test_changed_cache_or_news_cannot_be_used_as_frozen_source(self) -> None:
        path = self.root / "sentiment_cache_FPT.json"
        original = read_json(path); changed = deepcopy(original); changed["scored_articles"][0]["confidence"] = 0.7
        write_json(path, changed)
        with self.assertRaisesRegex(ValueError, "Cache khác snapshot"):
            self.build()
        write_json(path, original)
        news = read_json(self.bank / "news.json"); news["FPT"][0]["numeric_score"] += 0.1
        write_json(self.bank / "news.json", news)
        with self.assertRaisesRegex(ValueError, "Frozen news đã đổi"):
            self.build()

    def test_malformed_loader_payload_is_not_silently_empty(self) -> None:
        path = self.root / "sentiment_cache_FPT.json"
        write_json(path, {"symbol": "FPT", "scored_articles": "not a list"})
        with self.assertRaisesRegex(ValueError, "scored_articles"):
            load_disk_cache(self.root, "FPT")
        write_json(path, {"symbol": "VNM", "scored_articles": []})
        with self.assertRaisesRegex(ValueError, "symbol/schema"):
            load_disk_cache(self.root, "FPT")

    def test_correct_benchmark_path_and_ambiguous_matches_fail(self) -> None:
        _, summary, _ = self.build()
        self.assertEqual(summary["loader_contracts"]["legacy_benchmarks"], "outputs/backtest_result")
        write_json(self.benchmarks / "backtest_FPT_duplicate.json", {})
        with self.assertRaisesRegex(ValueError, "đúng một benchmark"):
            self.build()

    def test_release_is_read_only_for_inputs_and_never_writes_paper_or_existing_release(self) -> None:
        source_bytes = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        output = self.root / "outputs/revision/inventory_fixture"
        run_audit(self.root, output)
        self.assertTrue(verify_release(self.root, output) > 0)
        self.assertTrue(all(path.read_bytes() == data for path, data in source_bytes.items()))
        self.assertFalse((self.root / "paper").exists())
        with self.assertRaisesRegex(ValueError, "không ghi đè"):
            run_audit(self.root, output)
        with self.assertRaisesRegex(ValueError, "Output phải"):
            run_audit(self.root, self.root / "paper/generated")
        report = read_json(output / "summary.json"); report["scope"] = "changed"
        write_json(output / "summary.json", report)
        with self.assertRaisesRegex(ValueError, "Hash sai"):
            verify_release(self.root, output)

    def test_active_queue_frozen_source_guard_is_preserved(self) -> None:
        manifest_path = self.run / "manifest.json"
        manifest = read_json(manifest_path); manifest.pop("sha256")
        manifest["sources"] = [{"path": "core/revision_minimal_run.py", "sha256": "wrong hash"}]
        write_json(manifest_path, signed(manifest))
        with self.assertRaisesRegex(ValueError, "Nguồn queue frozen đã đổi"):
            run_audit(self.root, self.root / "outputs/revision/guard_fixture")


if __name__ == "__main__":
    unittest.main()
