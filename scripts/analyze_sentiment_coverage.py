"""Phân tích coverage và provenance của sentiment cache tại các test point."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
SYMBOLS = ("BHN", "CMG", "FPT", "HVN", "MBB", "MWG", "VCB", "VJC", "VNM")
DEFAULT_OUTPUT = ROOT / "outputs" / "sentiment_coverage" / "sentiment_coverage.csv"
WINDOW_DAYS = 90
REVIEWER_THRESHOLD = 8


@dataclass(frozen=True)
class ScorerCounts:
    visobert: int = 0
    lexicon: int = 0
    unknown: int = 0


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    _require(isinstance(payload, dict), f"JSON phải là object: {path}")
    return payload


def _single_benchmark(root: Path, symbol: str) -> Path:
    matches = sorted((root / "backtest_result").glob(f"backtest_{symbol}_*.json"))
    _require(
        len(matches) == 1,
        f"{symbol}: cần đúng 1 benchmark JSON, tìm thấy {len(matches)}",
    )
    return matches[0]


def parse_article_date(article: dict[str, Any]) -> date | None:
    """Đọc ngày bài báo mà không suy diễn ngày bị thiếu hoặc không hợp lệ."""

    values = (article.get("date_parsed"), article.get("date"))
    formats = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y")
    for raw in values:
        if not isinstance(raw, str) or not raw.strip():
            continue
        for fmt in formats:
            try:
                return datetime.strptime(raw.strip(), fmt).date()
            except ValueError:
                continue
    return None


def classify_scorer(article: dict[str, Any]) -> str:
    """Phân loại scorer chỉ từ provenance tường minh, không đoán từ score."""

    is_fallback = article.get("is_fallback")
    fields = (
        article.get("scorer"),
        article.get("scorer_name"),
        article.get("model_used"),
        article.get("model"),
        article.get("model_id"),
    )
    provenance = " ".join(str(value).lower() for value in fields if value is not None)

    if is_fallback is True or "lexicon" in provenance or "fallback" in provenance:
        return "lexicon"
    if is_fallback is False and ("visobert" in provenance or "5cd-ai" in provenance):
        return "visobert"
    if "visobert" in provenance or "5cd-ai" in provenance:
        return "visobert"
    return "unknown"


def count_scorers(articles: Iterable[dict[str, Any]]) -> ScorerCounts:
    counts = {"visobert": 0, "lexicon": 0, "unknown": 0}
    for article in articles:
        counts[classify_scorer(article)] += 1
    return ScorerCounts(**counts)


def _percentage(numerator: int, denominator: int) -> float:
    return round(100.0 * numerator / denominator, 2) if denominator else 0.0


def analyze_symbol(root: Path, symbol: str) -> dict[str, Any]:
    cache_path = root / f"sentiment_cache_{symbol}.json"
    _require(cache_path.is_file(), f"Thiếu cache: {cache_path}")
    cache = _load_json(cache_path)
    _require(cache.get("symbol") == symbol, f"Sai symbol trong {cache_path}")

    articles = cache.get("scored_articles", [])
    _require(isinstance(articles, list), f"scored_articles không phải list: {cache_path}")
    _require(all(isinstance(item, dict) for item in articles), f"Bản ghi cache lỗi: {cache_path}")

    urls = [item.get("url") for item in articles if item.get("url")]
    _require(len(urls) == len(set(urls)), f"{symbol}: cache có URL trùng lặp")

    dated_articles = [
        (article, parsed)
        for article in articles
        if (parsed := parse_article_date(article)) is not None
    ]
    scorer_counts = count_scorers(articles)

    benchmark_path = _single_benchmark(root, symbol)
    benchmark = _load_json(benchmark_path)
    _require(benchmark.get("symbol") == symbol, f"Sai symbol trong {benchmark_path}")
    test_points = benchmark.get("test_points", [])
    _require(isinstance(test_points, list) and test_points, f"{symbol}: thiếu test_points")
    _require(
        benchmark.get("n_tests") == len(test_points),
        f"{symbol}: n_tests không khớp số test point",
    )

    counts_90d: list[int] = []
    for point in test_points:
        cutoff_raw = point.get("window_end")
        _require(isinstance(cutoff_raw, str), f"{symbol}: test point thiếu window_end")
        cutoff = date.fromisoformat(cutoff_raw)
        lower_bound = cutoff - timedelta(days=WINDOW_DAYS)
        counts_90d.append(
            sum(lower_bound <= article_date <= cutoff for _, article_date in dated_articles)
        )

    points_ge_threshold = sum(count >= REVIEWER_THRESHOLD for count in counts_90d)
    total_articles = len(articles)
    return {
        "symbol": symbol,
        "cache_saved_at": cache.get("saved_at", ""),
        "benchmark_file": benchmark_path.name,
        "total_articles": total_articles,
        "dated_articles": len(dated_articles),
        "undated_articles": total_articles - len(dated_articles),
        "verified_visobert_articles": scorer_counts.visobert,
        "verified_lexicon_articles": scorer_counts.lexicon,
        "unknown_scorer_articles": scorer_counts.unknown,
        "verified_visobert_pct": _percentage(scorer_counts.visobert, total_articles),
        "verified_lexicon_pct": _percentage(scorer_counts.lexicon, total_articles),
        "unknown_scorer_pct": _percentage(scorer_counts.unknown, total_articles),
        "test_points": len(test_points),
        "mean_articles_90d": round(mean(counts_90d), 2),
        "min_articles_90d": min(counts_90d),
        "max_articles_90d": max(counts_90d),
        "test_points_ge_8_articles": points_ge_threshold,
        "test_points_ge_8_pct": _percentage(points_ge_threshold, len(test_points)),
    }


def write_csv(rows: list[dict[str, Any]], output_path: Path) -> None:
    _require(bool(rows), "Không có dữ liệu để ghi CSV")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def verify_manuscript(root: Path, rows: list[dict[str, Any]]) -> None:
    """Đối chiếu số liệu coverage đã công bố trong hai file LaTeX của TASK-12."""

    setup_path = root / "ESWA" / "sections" / "05_experimental_setup.tex"
    appendix_path = root / "ESWA" / "sections" / "appendices.tex"
    _require(setup_path.is_file(), f"Thiếu file LaTeX: {setup_path}")
    _require(appendix_path.is_file(), f"Thiếu file LaTeX: {appendix_path}")
    setup = setup_path.read_text(encoding="utf-8")
    appendix = appendix_path.read_text(encoding="utf-8")

    total_articles = sum(row["total_articles"] for row in rows)
    unknown_articles = sum(row["unknown_scorer_articles"] for row in rows)
    total_points = sum(row["test_points"] for row in rows)
    qualifying_points = sum(row["test_points_ge_8_articles"] for row in rows)
    overall_mean = mean(row["mean_articles_90d"] for row in rows)
    overall_pct = _percentage(qualifying_points, total_points)

    _require("\\label{tab:ticker_sentiment_coverage}" in appendix, "Thiếu bảng coverage")
    _require(f"{qualifying_points} of {total_points}" in setup, "Section 5 sai số test point coverage")
    _require(f"({overall_pct:.2f}\\%)" in setup, "Section 5 sai tỷ lệ coverage")
    _require(
        f"all {total_articles} are conservatively reported" in setup,
        "Section 5 thiếu công bố legacy-unknown",
    )

    for row in rows:
        numeric_tail = (
            rf"^{row['symbol']}\s*&.*&\s*{row['dated_articles']}/{row['total_articles']}\s*"
            rf"&\s*{row['verified_visobert_articles']}/{row['verified_lexicon_articles']}/"
            rf"{row['unknown_scorer_articles']}\s*&\s*{row['mean_articles_90d']:.2f}\s*"
            rf"&\s*{row['test_points_ge_8_articles']}/{row['test_points']}\s*\\\\"
        )
        _require(
            re.search(numeric_tail, appendix, flags=re.MULTILINE) is not None,
            f"Bảng coverage thiếu hoặc sai hàng {row['symbol']}",
        )

    _require(
        f"\\textbf{{{total_articles}/{total_articles}}}" in appendix
        and f"\\textbf{{0/0/{unknown_articles}}}" in appendix
        and f"\\textbf{{{overall_mean:.2f}}}" in appendix
        and f"\\textbf{{{qualifying_points}/{total_points}}}" in appendix,
        "Hàng tổng coverage không khớp CSV",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="Thư mục gốc repository")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="CSV đầu ra")
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    args = parse_args()
    root = args.root.resolve()
    output_path = args.output
    if not output_path.is_absolute():
        output_path = root / output_path

    rows = [analyze_symbol(root, symbol) for symbol in SYMBOLS]
    write_csv(rows, output_path)
    verify_manuscript(root, rows)

    total_articles = sum(row["total_articles"] for row in rows)
    verified_visobert = sum(row["verified_visobert_articles"] for row in rows)
    unknown = sum(row["unknown_scorer_articles"] for row in rows)
    qualifying_points = sum(row["test_points_ge_8_articles"] for row in rows)
    total_points = sum(row["test_points"] for row in rows)

    print(f"[PASS] Đã phân tích {len(rows)} mã và {total_points} test points")
    print(f"[DATA] Tổng bài={total_articles}; ViSoBERT xác minh={verified_visobert}; "
          f"provenance chưa biết={unknown}")
    print(f"[DATA] Test points có >=8 bài/90 ngày: {qualifying_points}/{total_points} "
          f"({_percentage(qualifying_points, total_points):.2f}%)")
    print("[PASS] Section 5.1 và Appendix khớp dữ liệu coverage")
    print(f"[OUTPUT] {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
