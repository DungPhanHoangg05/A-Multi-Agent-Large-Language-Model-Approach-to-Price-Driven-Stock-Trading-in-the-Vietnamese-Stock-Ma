"""Kiểm kê sentiment qua loader thực và article audit đã khóa, không inference."""

from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import redirect_stdout
from datetime import datetime
from importlib.metadata import version
import hashlib
import io
from pathlib import Path
import re
import sys
from typing import Any

from core.revision_audit import DEFAULT_SYMBOLS, sha256_file
from core.revision_common_study import digest, read_json, write_json
from core.revision72_data import news_from_scores
from data_manager.sentiment_cache import SentimentCache

BANK = Path("outputs/revision/r1_72h_bank_v2")
RUN = Path("outputs/revision/revision_minimal_v1")
OUTPUT = Path("outputs/revision/sentiment_inventory_v1")


def require(condition: bool, message: str) -> None:
    """Dừng khi nguồn sai hợp đồng; không sửa cache hoặc receipt lịch sử."""
    if not condition:
        raise ValueError(message)


def text_sha(text: str) -> str:
    """Hash UTF-8 trực tiếp, tách với content hash JSON của article audit cũ."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def runtime_date(value: object) -> str | None:
    """Legacy get_at chỉ dùng date_parsed với %Y-%m-%d, không mượn raw date."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None


def scorer_provenance(article: dict) -> dict:
    """Chỉ nhận định danh tường minh; score/confidence/backend hiện tại không là bằng chứng."""
    keys = ("scorer", "scorer_name", "model_used", "model", "model_id", "scorer_backend", "is_fallback", "scorer_revision", "model_revision")
    fields = {key: article[key] for key in keys if key in article}
    names = " ".join(str(article.get(key, "")).lower() for key in keys[:6])
    visobert = bool(re.search(r"(?<![a-z0-9])visobert(?![a-z0-9])", names))
    lexicon = bool(re.search(r"(?<![a-z0-9])lexicon(?![a-z0-9])", names))
    conflict = (visobert and lexicon) or (visobert and article.get("is_fallback") is True)
    category = "unknown" if conflict else "visobert" if visobert else "lexicon" if lexicon else "unknown"
    return {"category": category, "status": "conflicting_metadata" if conflict else "explicit_record_metadata" if category != "unknown" else "unknown",
            "recorded_fields": fields, "immutable_model_revision": article.get("scorer_revision") or article.get("model_revision") or "unknown",
            "historical_execution_verified": False}


def load_disk_cache(cache_dir: Path, symbol: str) -> tuple[list[dict], dict]:
    """Gọi loader disk thực; không preload vì cache rỗng có thể kích hoạt crawler."""
    cache = SentimentCache(symbol, cache_dir=str(cache_dir))
    path = Path(cache._cache_path).resolve()
    require(path.is_file(), f"Thiếu cache của loader: {path}")
    payload = read_json(path)
    require(isinstance(payload, dict) and payload.get("symbol") == symbol, "Sai symbol/schema cache")
    rows = payload.get("scored_articles")
    require(isinstance(rows, list) and all(isinstance(row, dict) for row in rows), "scored_articles phải là list các object")
    with redirect_stdout(io.StringIO()):
        loaded = cache._load_from_disk()
    require(loaded == len(rows) and cache._scored_articles == rows, "Loader disk không khớp payload; không được fallback")
    return cache._scored_articles, {"path": path, "saved_at": payload.get("saved_at", "unknown"), "loaded_records": loaded}


def corpus_counts(rows: list[dict]) -> dict:
    """Mẫu số là bản ghi bài báo; không dùng số test points hoặc Decisions."""
    valid_dates = sorted(row["runtime_publication_date"] for row in rows if row["runtime_publication_date"] is not None)
    categories = Counter(row["legacy_scorer"]["category"] for row in rows)
    unique = {field: len({row[field] for row in rows}) for field in ("article_id", "url_normalized", "title_content_normalized_hash")}
    return {"records": len(rows), "unique_article_identities": unique["article_id"], "unique_urls": unique["url_normalized"],
            "unique_title_content_hashes": unique["title_content_normalized_hash"],
            "duplicate_identity_excess": len(rows) - unique["article_id"], "duplicate_url_excess": len(rows) - unique["url_normalized"],
            "duplicate_content_excess": len(rows) - unique["title_content_normalized_hash"],
            "dated_records_used_by_legacy_loader": len(valid_dates), "undated_or_invalid_records": len(rows) - len(valid_dates),
            "date_consistent_records_in_frozen_audit": sum(r["date_consistent_with_url_in_frozen_audit"] for r in rows),
            "date_inconsistent_records_in_frozen_audit": sum(not r["date_consistent_with_url_in_frozen_audit"] for r in rows),
            "eligible_records_in_frozen_audit": sum(r["eligible_source_in_frozen_audit"] for r in rows),
            "date_min": valid_dates[0] if valid_dates else None, "date_max": valid_dates[-1] if valid_dates else None,
            "legacy_scorer_categories": {key: int(categories[key]) for key in ("visobert", "lexicon", "unknown")}}


def duplicate_groups(rows: list[dict], field: str) -> list[dict]:
    """Giữ các aliases theo mã/index; không xóa hoặc dedup cache runtime."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[row[field]].append({"symbol": row["symbol"], "index": row["index"], "cache_path": row["cache_path"]})
    return [{"key": key, "records": group, "cross_symbol": len({r["symbol"] for r in group}) > 1}
            for key, group in sorted(groups.items()) if len(group) > 1]


def build_inventory(root: Path, cache_dir: Path, legacy_dir: Path, bank: Path, run: Path) -> tuple[dict, dict, set[Path]]:
    """Đối chiếu current disk với audit/rescore/news đã có; không chạy scorer hoặc coverage cutoff."""
    from core.revision72_run import checked
    audit_path, scores_path, news_path = (bank / name for name in ("article_audit.json", "local_scores.json", "news.json"))
    audit, scores, news = map(read_json, (audit_path, scores_path, news_path))
    bank_manifest, run_manifest = read_json(bank / "manifest.json"), checked(run / "manifest.json")
    require(digest({k: v for k, v in bank_manifest.items() if k != "bank_id"}) == bank_manifest["bank_id"], "Bank identity sai")
    require(digest(news) == bank_manifest["news_hash"], "Frozen news đã đổi")
    require(news_from_scores(audit, scores) == news, "News không khớp article audit/local rescore đã khóa")
    expected_cache_sources = {r["path"]: r["sha256"] for r in audit["sources"]}
    require(expected_cache_sources == {r["path"]: r["sha256"] for r in bank_manifest["article_sources"]}, "Hai nguồn khác cache provenance")
    audit_records = {(r["symbol"], r["index"]): r for r in audit["records"]}
    require(len(audit_records) == len(audit["records"]) == audit["n_records"], "Article audit trùng index hoặc sai tổng records")
    articles = {a["article_id"]: a for a in audit["articles"]}
    require(len(articles) == len(audit["articles"]) == audit["n_unique"], "Article audit trùng identity hoặc sai n_unique")
    rows, cache_metadata, legacy_artifacts, sources = [], [], [], {audit_path, scores_path, news_path, bank / "manifest.json", run / "manifest.json"}
    for symbol in DEFAULT_SYMBOLS:
        loaded, metadata = load_disk_cache(cache_dir, symbol)
        path = metadata.pop("path")
        require(expected_cache_sources.get(path.name) == sha256_file(path), "Cache khác snapshot article audit: " + path.name)
        sources.add(path)
        relative = path.relative_to(root).as_posix()
        cache_metadata.append({"symbol": symbol, "path": relative, **metadata, "historical_execution_cache_link": "unverified"})
        for index, item in enumerate(loaded):
            recorded = audit_records.get((symbol, index))
            require(recorded is not None, "Cache có record ngoài article audit")
            raw_url = str(item.get("url", ""))
            url = raw_url.split("?")[0].rstrip("/")
            raw_content = str(item.get("content", ""))
            normalized_text = " ".join((str(item.get("title", "")) + " " + raw_content).strip().split())
            article_id, content_hash = digest({"url": url, "text": normalized_text}), digest(normalized_text)
            require((recorded["article_id"], recorded["text_hash"], recorded["url"], recorded["date_parsed"]) ==
                    (article_id, content_hash, url, item.get("date_parsed")), "Record identity/date/content khác article audit")
            article = articles.get(article_id)
            require(article is not None and symbol in article["symbols"] and article["text"] == normalized_text, "Alias/article body không khớp")
            rows.append({"symbol": symbol, "index": index, "cache_path": relative, "article_id": article_id,
                         "url_raw": raw_url, "url_normalized": url, "url_raw_sha256": text_sha(raw_url), "url_normalized_sha256": text_sha(url),
                         "content_raw_sha256": text_sha(raw_content), "title_content_normalized_hash": content_hash,
                         "date_raw": item.get("date"), "date_parsed_raw": item.get("date_parsed"), "available_at_raw": item.get("available_at"),
                         "runtime_publication_date": runtime_date(item.get("date_parsed")),
                         "record_date_matches_audit_identity_date": item.get("date_parsed") == article["date_parsed"],
                         "date_consistent_with_url_in_frozen_audit": bool(article["date_consistent"]),
                         "eligible_source_in_frozen_audit": bool(article["eligible_source"]),
                         "legacy_scorer": scorer_provenance(item), "local_rescore_available": article_id in scores.get("scores", {}),
                         "source_pit": article["source_pit"], "full_article_content_verified": False})
        matches = sorted(legacy_dir.glob(f"backtest_{symbol}_*.json"))
        require(len(matches) == 1, f"{symbol}: cần đúng một benchmark ở {legacy_dir}, thấy {len(matches)}")
        benchmark = read_json(matches[0])
        points = benchmark.get("test_points")
        require(benchmark.get("symbol") == symbol and isinstance(points, list) and benchmark.get("n_tests") == len(points), "Benchmark sai symbol/n_tests/test_points")
        sources.add(matches[0])
        legacy_artifacts.append({"symbol": symbol, "path": matches[0].relative_to(root).as_posix(), "test_points": len(points),
                                 "cache_used_by_historical_execution": "unverified", "denominator": "test_points, không phải bài báo"})
    require(len(rows) == audit["n_records"], "Không phủ đủ records của article audit")
    require({row["article_id"] for row in rows} == set(articles), "Không phủ đúng article identities")
    for article_id, article in articles.items():
        require(set(article["symbols"]) == {r["symbol"] for r in rows if r["article_id"] == article_id}, "Article audit có alias thừa/thiếu")
        require(article["article_id"] == digest({"url": article["url"], "text": article["text"]}), "Article ID sai content")
    score_ids = set(scores.get("scores", {}))
    require(score_ids <= set(articles) and all(articles[key]["eligible_source"] for key in score_ids), "Rescore có identity ngoài nguồn đủ điều kiện")
    news_records = [{"symbol": symbol, **item} for symbol, entries in news.items() for item in entries]
    require(len({(r["symbol"], r["article_id"]) for r in news_records}) == len(news_records), "News trùng article/mã")
    card = bank / "model_card.md"
    card_verified = card.is_file() and sha256_file(card) == scores.get("model_card_sha256")
    if card.is_file(): sources.add(card)
    runtime_expected = run_manifest["runtime"]
    current_runtime = {key: sys.version.split()[0] if key == "python" else version(key) for key in runtime_expected}
    require(current_runtime == runtime_expected, "Runtime audit khác queue đã freeze")
    summary = {"scope": "T05: inventory/provenance, chưa phải coverage cutoff T06 hoặc validation T08",
               "legacy": {"corpus": corpus_counts(rows),
                          "per_symbol": [{"symbol": symbol, **corpus_counts([r for r in rows if r["symbol"] == symbol])} for symbol in DEFAULT_SYMBOLS],
                          "cache_metadata": cache_metadata, "benchmark_artifacts": legacy_artifacts,
                          "test_points_total": sum(r["test_points"] for r in legacy_artifacts)},
               "local_rescore": {"scope": "rescore mới trên excerpts đã cache; không xác nhận ngược scorer legacy",
                                 "unique_scored_identities": len(score_ids), "eligible_identities_in_article_audit": sum(a["eligible_source"] for a in articles.values()),
                                 "identities_without_rescore": len(articles) - len(score_ids),
                                 "reported_revision": scores.get("revision", "unknown"), "reported_mapping": scores.get("mapping"),
                                 "reported_max_length": scores.get("max_length"), "reported_files": scores.get("files", []),
                                 "model_card_url_recorded": scores.get("model_card_url"), "local_model_card_hash_matches_receipt": card_verified,
                                 "current_model_weights_hash_checked": False, "financial_domain_validated": False},
               "frozen_news": {"symbol_article_records": len(news_records), "unique_article_identities": len({r["article_id"] for r in news_records}),
                               "per_symbol": {symbol: len(entries) for symbol, entries in news.items()}, "content_digest_matches_bank": True},
               "evaluation_units": {"main_market_units": len(bank_manifest["units"]), "minimal_executions": len(run_manifest["jobs"]),
                                    "per_phase": dict(Counter(j["phase"] for j in run_manifest["jobs"])),
                                    "denominator": "market units/executions; không phải số bài hoặc identities"},
               "runtime": current_runtime,
               "loader_contracts": {"disk": "data_manager.sentiment_cache.SentimentCache._load_from_disk; scored_articles; cache_dir tường minh",
                                    "legacy_dates": "SentimentCache.get_at: date_parsed; cùng ngày có thể dùng, available_at không được xét",
                                    "frozen_news": "core.revision_common_study.FrozenSentiment / core.revision_baselines.sentiment_features",
                                    "active_queue": "core.revision_minimal_run: dùng prompt strings đã freeze; không reload cache/rescore",
                                    "legacy_benchmarks": legacy_dir.relative_to(root).as_posix()},
               "hash_definitions": {"article_id": "digest(JSON {url: normalized_url, text: whitespace-normalized title + content}); giữ nguyên identity article audit",
                                    "title_content_normalized_hash": "digest(JSON string normalized title + content); bằng text_hash trong article audit",
                                    "*_sha256": "SHA-256 trên UTF-8 nguyên chuỗi tương ứng, không phải full-page news snapshot"},
               "limits": ["Cache hiện có không xác thực snapshot submission, PIT nội dung hoặc weights của scorer lịch sử.",
                          "T05 không xuất tỷ lệ/cửa sổ theo cutoff; phần đó thuộc T06 dùng runtime riêng cho legacy và release mới.",
                          "Scorer metadata tường minh chưa đồng nghĩa immutable weights hoặc chất lượng tài chính đã validation.",
                          "CSV coverage cũ giữ nguyên để bảo toàn evidence; không sử dụng số liệu của nó làm nguồn inventory mới."]}
    inventory = {"legacy_records": rows, "duplicates": {field: duplicate_groups(rows, field) for field in
                 ("article_id", "url_normalized", "title_content_normalized_hash")},
                 "frozen_news_records": news_records}
    return inventory, summary, sources


def run_audit(root: Path, output: Path, cache_dir: Path | None = None, legacy_dir: Path | None = None,
              bank: Path | None = None, run: Path | None = None) -> dict:
    """Xuất release mới độc quyền dưới outputs/revision; không ghi paper hoặc run đang chạy."""
    root, output = root.resolve(), output.resolve()
    require(output.is_relative_to(root / "outputs/revision") and output != root / "outputs/revision", "Output phải là release riêng dưới outputs/revision")
    require(not output.exists(), "Release audit đã có; dùng --check, không ghi đè")
    bank, run = bank or root / BANK, run or root / RUN
    before = read_json(run / "manifest.json")
    frozen = {row["path"]: row["sha256"] for row in before["sources"]}
    for relative, checksum in frozen.items(): require(sha256_file(root / relative) == checksum, "Nguồn queue frozen đã đổi: " + relative)
    inventory, summary, sources = build_inventory(root, cache_dir or root, legacy_dir or root / "outputs/backtest_result", bank, run)
    for relative, checksum in frozen.items(): require(sha256_file(root / relative) == checksum, "Audit làm đổi nguồn queue: " + relative)
    sources.update(root / p for p in ("core/revision_sentiment_inventory.py", "scripts/audit_sentiment_inventory.py", "tests/test_revision_sentiment_inventory.py",
                                    "data_manager/sentiment_cache.py", "core/revision72_data.py", "core/revision_common_study.py", "core/revision_baselines.py",
                                    "core/revision_minimal_run.py", "scripts/analyze_sentiment_coverage.py"))
    before_hashes = [{"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)} for path in sorted(sources)]
    output.mkdir(parents=True)
    write_json(output / "inventory.json", inventory, True)
    write_json(output / "summary.json", summary, True)
    write_json(output / "manifest.json", {"schema_version": "sentiment_inventory_v1", "queue_run_signature": before["sha256"],
               "frozen_source_hashes_checked_before_after": len(frozen), "historical_inputs_modified": False, "network_or_inference": False,
               "sources": before_hashes, "outputs": [{"path": p.name, "sha256": sha256_file(p)} for p in sorted(output.iterdir())]}, True)
    return summary


def verify_release(root: Path, output: Path) -> int:
    """Kiểm source/output hashes của release T05 mà không tạo lại inventory."""
    manifest = read_json(output / "manifest.json")
    count = 0
    for group, base in (("sources", root), ("outputs", output)):
        for row in manifest[group]:
            path = (base / row["path"]).resolve()
            require(path.is_relative_to(base.resolve()) and sha256_file(path) == row["sha256"], "Hash sai: " + row["path"])
            count += 1
    return count
