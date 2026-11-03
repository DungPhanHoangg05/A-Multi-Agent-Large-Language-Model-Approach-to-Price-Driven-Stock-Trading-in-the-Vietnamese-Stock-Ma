"""Coverage T06 từ inventory T05; tách replay legacy và dữ liệu release đã khóa."""

from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import redirect_stdout
from datetime import date
from importlib.metadata import version
import io
import math
from pathlib import Path
import sys
from unittest.mock import patch

import pandas as pd

from core.revision_audit import sha256_file
from core.revision_baselines import sentiment_features
from core.revision_common_study import FrozenSentiment, digest, read_json, write_json
from core.revision72_run import checked
from core.revision_sentiment_inventory import BANK, RUN, load_disk_cache, require, runtime_date, verify_release
from data_manager.sentiment_cache import SentimentCache

INVENTORY = Path("outputs/revision/sentiment_inventory_v1")
OUTPUT = Path("outputs/revision/sentiment_coverage_v1")
CATEGORIES = ("visobert", "lexicon", "unknown")
ZONE = "Asia/Ho_Chi_Minh"


def proportions(categories: list[str]) -> dict:
    """V/L/U và tỷ lệ dùng cùng mẫu số; mẫu số zero cho null, không cho NaN."""
    require(all(value in CATEGORIES for value in categories), "Scorer category ngoài V/L/U")
    counts = Counter(categories)
    total = len(categories)
    return {"total": total, "counts": {key: int(counts[key]) for key in CATEGORIES},
            "percentages": {key: float(100 * counts[key] / total) if total else None for key in CATEGORIES}}


def availability(article: dict) -> pd.Timestamp | None:
    """Giữ explicit available_at; thiếu thì publication +1 ngày như runtime frozen."""
    raw = article.get("available_at")
    try:
        if not raw and article.get("date_parsed"):
            raw = (pd.Timestamp(article["date_parsed"]) + pd.Timedelta(days=1)).isoformat()
        stamp = pd.Timestamp(raw)
        if pd.isna(stamp): return None
        return stamp.tz_localize(ZONE) if stamp.tzinfo is None else stamp.tz_convert(ZONE)
    except (ValueError, TypeError, OverflowError):
        return None


def window_coverage(articles: list[dict], cutoff: str) -> dict:
    """Cửa sổ [cutoff EOD−90d, cutoff EOD], >=3 identities có score hữu hạn/provenance."""
    end = pd.Timestamp(cutoff).tz_localize(ZONE) + pd.Timedelta(hours=23, minutes=59, seconds=59)
    start = end - pd.Timedelta(days=90)
    eligible, evidence = [], {}
    for article in articles:
        stamp = availability(article)
        if stamp is None or not start <= stamp <= end:
            continue
        category = article.get("category", article.get("scorer", "unknown"))
        category = category if category in CATEGORIES else "unknown"
        identity = article["article_id"]
        eligible.append({"article_id": identity, "category": category, "available_at": stamp.isoformat()})
        try:
            score = float(article.get("numeric_score"))
        except (TypeError, ValueError):
            continue
        if category not in ("visobert", "lexicon") or not math.isfinite(score) or not -1 <= score <= 1:
            continue
        row = {"article_id": identity, "scorer": category, "numeric_score": score, "available_at": stamp.isoformat()}
        require(identity not in evidence or evidence[identity] == row, "Cùng identity có score/provenance/availability mâu thuẫn")
        evidence[identity] = row
    # Tính score bằng đúng hàm runtime, chỉ loại bản lặp identity trong diagnostic legacy.
    feature = sentiment_features(pd.Series([cutoff]), list(evidence.values())).iloc[0]
    count = int(feature["verified_article_count"])
    require(count == len(evidence), "Membership coverage khác loader numeric")
    missing = bool(feature["sentiment_missing"])
    score = None if missing else float(feature["sentiment_score"])
    return {"window_start": start.isoformat(), "window_end": end.isoformat(), "window_days": 90, "minimum_valid_articles": 3,
            "article_records": proportions([r["category"] for r in eligible]), "unique_article_identities": len({r["article_id"] for r in eligible}),
            "valid_score_articles": count, "sentiment_missing": missing, "sentiment_score": score,
            "sentiment_state": "missing" if missing else "neutral" if score == 0 else "positive" if score > 0 else "negative",
            "article_membership": eligible, "valid_score_article_ids": sorted(evidence)}


def peers(data: dict, historical: bool = False) -> dict:
    """Chỉ đọc peers thực được runtime cung cấp, không mượn corpus mã khác làm peer."""
    names = data.get("related_companies", [])
    values = data.get("related_sentiment", {})
    available = [name for name in names if values.get(name, {}).get("article_count", 0) >= 3]
    return {"runtime_related_companies": list(names), "available_peer_symbols": available,
            "available_peer_count": len(available), "peer_evidence_available": bool(available),
            "status": "available" if available else "unavailable_in_runtime_payload",
            "historical_execution_verified": False if historical else None}


def legacy_replay(cache: SentimentCache, indexed: list[dict], cutoff: str) -> dict:
    """Dùng get_at thật trên cache hiện có, giữ nguyên lệch same-day của legacy."""
    end = date.fromisoformat(cutoff)
    eligible = [row for row in indexed if row["runtime_publication_date"] is not None
                and 0 <= (end - date.fromisoformat(row["runtime_publication_date"])).days <= 90]
    # Import aggregate legacy có load_dotenv ở module scope; chỉ chặn bước đọc key,
    # không thay selection/aggregate/report của get_at và không gọi scorer.
    with redirect_stdout(io.StringIO()), patch("dotenv.load_dotenv", return_value=False):
        data, _ = cache.get_at(cutoff, llm=None, window_days=90, min_articles=3, strict_research_mode=True)
    count = int(data["n_articles_used"])
    require(count == len(eligible) and bool(data["is_reliable"]) == (count >= 3), "Replay legacy khác membership audit")
    return {"article_records": proportions([r["legacy_scorer"]["category"] for r in eligible]),
            "article_ids": [r["article_id"] for r in eligible], "same_day_article_records": sum(r["runtime_publication_date"] == cutoff for r in eligible),
            "runtime_is_reliable": bool(data["is_reliable"]), "runtime_avg_score": float(data["main_sentiment"]["avg_score"]),
            "runtime_neutral_due_to_insufficient_articles": count < 3, "returned_article_preview_count": len(data["scored_articles"]),
            "peers": peers(data, historical=True), "historical_cache_link": "unverified"}


def summarize_rows(rows: list[dict]) -> dict:
    """Tổng hợp từ đúng các rows đã xuất; pooled khác macro theo mã có support."""
    def totals(part: list[dict]) -> dict:
        """Mỗi row là một cutoff, không phải một API execution/repeat."""
        n = len(part)
        available = sum(not r["coverage"]["sentiment_missing"] for r in part)
        value = {"cutoffs": n, "with_at_least_3_valid_articles": available, "missing": n - available,
                 "coverage_pct": float(100 * available / n) if n else None,
                 "available_neutral_cutoffs": sum(r["coverage"]["sentiment_state"] == "neutral" for r in part),
                 "peer_available_cutoffs": sum(r["peers"]["peer_evidence_available"] for r in part)}
        if part and "runtime_replay" in part[0]:
            value["legacy_runtime_count_ge3_cutoffs"] = sum(r["runtime_replay"]["runtime_is_reliable"] for r in part)
            value["legacy_same_day_article_memberships"] = sum(r["runtime_replay"]["same_day_article_records"] for r in part)
        if part and "normalizer_is_reliable" in part[0]:
            value["normalizer_reliable_cutoffs"] = sum(r["normalizer_is_reliable"] for r in part)
        return value
    symbols = sorted({r["symbol"] for r in rows})
    per_symbol = [{"symbol": symbol, **totals([r for r in rows if r["symbol"] == symbol])} for symbol in symbols]
    macro = float(sum(r["coverage_pct"] for r in per_symbol) / len(per_symbol)) if per_symbol else None
    return {"pooled": totals(rows), "per_symbol": per_symbol, "macro_unweighted_symbol_coverage_pct": macro,
            "denominator": "một cutoff/mã; không đếm repeats như thị trường độc lập"}


def scorer_tables(inventory: dict) -> dict:
    """Toàn bộ V/L/U counts và percentages xuất từ cùng inventory T05."""
    legacy, news = inventory["legacy_records"], inventory["frozen_news_records"]

    def unique_categories(rows: list[dict], legacy_view: bool) -> list[str]:
        """Metadata mâu thuẫn giữa aliases được ghi unknown, không chọn scorer thuận lợi."""
        groups: dict[str, set[str]] = defaultdict(set)
        for row in rows:
            groups[row["article_id"]].add(row["legacy_scorer"]["category"] if legacy_view else row["scorer"])
        return [next(iter(values)) if len(values) == 1 else "unknown" for values in groups.values()]

    return {"legacy_cache_records": proportions([r["legacy_scorer"]["category"] for r in legacy]),
            "legacy_unique_identities": proportions(unique_categories(legacy, True)),
            "frozen_news_symbol_article_records": proportions([r["scorer"] for r in news]),
            "frozen_news_unique_identities": proportions(unique_categories(news, False)),
            "legacy_per_symbol": [{"symbol": s, **proportions([r["legacy_scorer"]["category"] for r in legacy if r["symbol"] == s])}
                                  for s in sorted({r["symbol"] for r in legacy})],
            "frozen_news_per_symbol": [{"symbol": s, **proportions([r["scorer"] for r in news if r["symbol"] == s])}
                                       for s in sorted({r["symbol"] for r in legacy})]}


def build_coverage(root: Path, inventory_dir: Path, bank: Path, run: Path) -> tuple[dict, dict, set[Path]]:
    """Replay coverage và so với sentiment assets, không đọc prediction/raw đang ghi."""
    verify_release(root, inventory_dir)
    inventory = read_json(inventory_dir / "inventory.json")
    t05 = read_json(inventory_dir / "summary.json")
    bank_manifest, run_manifest = read_json(bank / "manifest.json"), checked(run / "manifest.json")
    require(digest({k: v for k, v in bank_manifest.items() if k != "bank_id"}) == bank_manifest["bank_id"], "Bank identity sai")
    require(run_manifest["runtime"] == t05["runtime"], "Queue khác runtime inventory T05")
    current_runtime = {key: sys.version.split()[0] if key == "python" else version(key) for key in run_manifest["runtime"]}
    require(current_runtime == run_manifest["runtime"], "Runtime hiện tại khác queue đã freeze")
    news = read_json(bank / "news.json")
    require(digest(news) == bank_manifest["news_hash"], "Frozen news sai hash")
    require([{ "symbol": symbol, **a} for symbol, items in news.items() for a in items] == inventory["frozen_news_records"], "Frozen news khác inventory")
    sources = {inventory_dir / name for name in ("inventory.json", "summary.json", "manifest.json")}
    sources.update((bank / "manifest.json", bank / "news.json", run / "manifest.json"))
    legacy_rows = []
    for artifact in t05["legacy"]["benchmark_artifacts"]:
        symbol = artifact["symbol"]
        indexed = [r for r in inventory["legacy_records"] if r["symbol"] == symbol]
        cache_info = next(r for r in t05["legacy"]["cache_metadata"] if r["symbol"] == symbol)
        cache_path = root / cache_info["path"]
        raw, _ = load_disk_cache(cache_path.parent, symbol)
        require(len(raw) == len(indexed), "Legacy loader khác inventory record count")
        cache = SentimentCache(symbol, str(cache_path.parent)); cache._scored_articles = raw; cache._loaded = True
        sources.add(cache_path)
        path = root / artifact["path"]; sources.add(path)
        points = read_json(path)["test_points"]
        require(len(points) == artifact["test_points"], "Benchmark test points đã đổi")
        normalized = [{**raw[r["index"]], "article_id": r["article_id"], "category": r["legacy_scorer"]["category"],
                       "date_parsed": r["runtime_publication_date"]} for r in indexed]
        for position, point in enumerate(points):
            cutoff = date.fromisoformat(point["window_end"]).isoformat()
            runtime = legacy_replay(cache, indexed, cutoff)
            legacy_rows.append({"id": f"legacy_{symbol}_{position}", "symbol": symbol, "test_id": point["test_id"], "cutoff": cutoff,
                                "view": "legacy_current_cache_availability_diagnostic", "coverage": window_coverage(normalized, cutoff),
                                "runtime_replay": runtime, "peers": runtime["peers"]})
    panel = {u["id"] for u in run_manifest["panel"]}
    upstream = {j["context"]["unit_id"] for j in run_manifest["jobs"] if j["phase"] == "upstream"}
    frozen = FrozenSentiment(news)
    release_rows = []
    for unit in bank_manifest["units"]:
        symbol, cutoff = unit["symbol"], unit["date"]
        require(len({a["article_id"] for a in news[symbol]}) == len(news[symbol]), "News trùng identity/mã")
        coverage = window_coverage(news[symbol], cutoff)
        data, report = frozen.get_sentiment_at(symbol, cutoff)
        require(coverage["valid_score_articles"] == int(data["verified_article_count"]) == unit["verified_articles"], "Coverage count khác bank/runtime")
        require(coverage["sentiment_missing"] == bool(data["is_unavailable"]) and coverage["sentiment_score"] == data["main_sentiment"]["avg_score"], "Missing/score khác FrozenSentiment")
        path = bank / f"features/{symbol}_{unit['decision']}.json"
        asset = checked(path); sources.add(path)
        require(asset["bank_id"] == bank_manifest["bank_id"] and asset["sentiment_data"] == data and asset["sentiment_report"] == report, "Sentiment asset khác coverage/runtime")
        release_rows.append({"id": unit["id"], "symbol": symbol, "fold": unit["fold"], "cutoff": cutoff,
                             "view": "corrected_chart_frozen_news", "in_factorial_panel": unit["id"] in panel,
                             "in_upstream_panel": unit["id"] in upstream, "coverage": coverage, "peers": peers(data),
                             "runtime_report_article_count": int(data["main_sentiment"]["article_count"]),
                             "normalizer_is_reliable": bool(asset["sentiment_norm"]["is_reliable"]),
                             "normalizer_raw_avg_score": float(asset["sentiment_norm"]["raw_avg_score"]),
                             "feature_path": path.relative_to(root).as_posix()})
    require(panel <= {r["id"] for r in release_rows} and upstream <= {r["id"] for r in release_rows}, "Panel ngoài main cutoff support")
    coverage = {"scorer_tables": scorer_tables(inventory), "legacy_cutoffs": legacy_rows, "release_cutoffs": release_rows}
    summary = {"scope": "T06 coverage; không phải bằng chứng validation tài chính, PIT nội dung hoặc inference mới", "runtime": current_runtime,
               "legacy": summarize_rows(legacy_rows),
               "release": {"main": summarize_rows(release_rows),
                           "upstream": summarize_rows([r for r in release_rows if r["in_upstream_panel"]]),
                           "factorial": summarize_rows([r for r in release_rows if r["in_factorial_panel"]])},
               "scorer_tables": coverage["scorer_tables"],
               "rules": {"availability": "date-only publication +1 ngày; explicit available_at giữ nguyên; timezone Asia/Ho_Chi_Minh",
                         "window": "[cutoff ngày 23:59:59 −90 ngày, cutoff ngày 23:59:59], inclusive",
                         "minimum": ">=3 identities khác nhau có scorer V/L tường minh và score hữu hạn trong [-1,1]",
                         "provenance": "V/L/U là metadata đã ghi, không tự chứng nhận chất lượng scorer hoặc PIT",
                         "missing": "score=null và state=missing; score=0 chỉ là neutral khi đủ >=3 bài hợp lệ",
                         "legacy_replay": "Giữ nguyên runtime same-day/unknown scorer/neutral fallback; diagnostic không sửa kết quả cũ",
                         "percentages": "Tính từ cùng counts/total; mẫu số zero xuất null; không pool legacy với release mới",
                         "peers": "Chỉ runtime related_companies/related_sentiment; aliases hoặc mã khác có cache không tạo peer evidence"},
               "limits": ["Legacy chỉ replay cache hiện có, chưa xác minh cache hoặc peer payload của execution lịch sử.",
                          "Frozen news/data đủ 3 bài khác normalizer legacy is_reliable >=8; ghi riêng, không đổi prompt đang chạy.",
                          "Các số zero trong normalized feature khi missing không được coi là sentiment neutral/evidence.",
                          "T07 còn kiểm tokenizer/scorer và prompt thiếu tin; T08 còn domain validation; T06 không đóng các task đó."]}
    return coverage, summary, sources


def run_audit(root: Path, output: Path) -> dict:
    """Ghi release T06 riêng, kiểm sources frozen trước/sau, không chạm worker/ledger."""
    root, output = root.resolve(), output.resolve()
    require(output.is_relative_to(root / "outputs/revision") and output != root / "outputs/revision", "Output phải là release riêng dưới outputs/revision")
    require(not output.exists(), "Release đã có; dùng --check, không ghi đè")
    run = root / RUN
    manifest = checked(run / "manifest.json")
    for row in manifest["sources"]: require(sha256_file(root / row["path"]) == row["sha256"], "Nguồn queue frozen đã đổi: " + row["path"])
    coverage, summary, sources = build_coverage(root, root / INVENTORY, root / BANK, run)
    for row in manifest["sources"]: require(sha256_file(root / row["path"]) == row["sha256"], "Nguồn queue đổi trong audit: " + row["path"])
    sources.update(root / p for p in ("core/revision_sentiment_coverage.py", "scripts/audit_revision_sentiment_coverage.py",
                                    "tests/test_revision_sentiment_coverage.py", "core/revision_sentiment_inventory.py",
                                    "core/revision_baselines.py", "core/revision_common_study.py", "data_manager/sentiment_cache.py",
                                    "agents/sentiment_agent.py", "agents/alpha_agent.py"))
    # Khóa cả nguồn T05 đã đọc gián tiếp, không chỉ checksum manifest T05.
    sources.update(root / r["path"] for r in read_json(root / INVENTORY / "manifest.json")["sources"])
    output.mkdir(parents=True)
    write_json(output / "coverage.json", coverage, True)
    write_json(output / "summary.json", summary, True)
    write_json(output / "manifest.json", {"schema_version": "sentiment_coverage_v1", "queue_run_signature": manifest["sha256"],
               "frozen_source_hashes_checked_before_after": len(manifest["sources"]), "network_or_inference": False,
               "sources": [{"path": p.relative_to(root).as_posix(), "sha256": sha256_file(p)} for p in sorted(sources)],
               "outputs": [{"path": p.name, "sha256": sha256_file(p)} for p in sorted(output.iterdir())]}, True)
    return summary
