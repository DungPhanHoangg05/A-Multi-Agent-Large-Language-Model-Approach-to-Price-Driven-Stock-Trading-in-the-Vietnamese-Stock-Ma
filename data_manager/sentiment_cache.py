"""
SentimentCache — Thu thập sentiment lịch sử cho Backtest
=========================================================
Workflow:
  1. Trước khi chạy backtest: gọi SentimentCache.preload(symbol, related_symbols)
     → Crawl tất cả bài báo CafeF một lần duy nhất, lưu kèm ngày đăng
  2. Trong mỗi test point: gọi get_sentiment_at(symbol, cutoff_date)
     → Trả về sentiment chỉ từ bài báo đăng TRƯỚC cutoff_date
     → Tránh data leakage tương lai

Tại sao không bias:
  - Mỗi test window [start → end] chỉ dùng tin tức đã xuất hiện tại thời điểm end
  - Bài báo tương lai không được dùng
  - Khớp hoàn toàn với quyết định thực tế tại thời điểm đó
"""

import json
import os
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# ── Constants ──────────────────────────────────────────────────────────────────

CACHE_FILE_TPL   = "sentiment_cache_{symbol}.json"   # lưu đĩa để tái sử dụng
MAX_PAGES_PRELOAD = 8       # crawl nhiều trang hơn so với production (200+ bài)
MAX_ARTICLES_PRELOAD = 250  # tổng bài tối đa per symbol
DATE_FORMATS = [
    "%d/%m/%Y",   # CafeF thường dùng: 15/04/2024
    "%Y-%m-%d",   # ISO
    "%d-%m-%Y",
    "%m/%d/%Y",
]


# ── Date helpers ───────────────────────────────────────────────────────────────

def _parse_article_date(date_str: str) -> Optional[datetime]:
    """
    Parse ngày bài báo từ nhiều định dạng.
    Trả về None nếu không parse được.
    """
    if not date_str:
        return None
    date_str = date_str.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    # Thử tìm pattern dd/mm/yyyy trong chuỗi dài hơn
    m = re.search(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', date_str)
    if m:
        try:
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return datetime(y, mo, d)
        except ValueError:
            pass
    return None


def _date_to_str(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def _cutoff_dt(cutoff_date: str) -> datetime:
    """Parse cutoff_date string → datetime."""
    for fmt in ["%Y-%m-%d", "%d/%m/%Y"]:
        try:
            return datetime.strptime(cutoff_date, fmt)
        except ValueError:
            continue
    raise ValueError(f"Không parse được cutoff_date: {cutoff_date}")


# ── CafeF enhanced crawler (crawl nhiều trang hơn) ────────────────────────────

def _crawl_articles_full(
    ticker: str,
    max_articles: int = MAX_ARTICLES_PRELOAD,
    max_pages: int    = MAX_PAGES_PRELOAD,
) -> List[dict]:
    """
    Crawl tất cả bài báo CafeF cho ticker.
    Giữ nguyên `date` field từ listing page — dùng để filter theo cutoff.
    """
    # Import các hàm nội bộ từ sentiment_agent
    from agents.sentiment_agent import (
        _get, _parse_listing_page, _fetch_article_content,
        CAFEF_BASE_URL, REQUEST_DELAY,
    )

    ticker_lower = ticker.lower()
    url_patterns = [ticker_lower, f"co-phieu-{ticker_lower}"]

    all_articles: List[dict] = []
    seen_urls: set = set()

    for pattern in url_patterns:
        if len(all_articles) >= max_articles:
            break

        pattern_found = False
        for page in range(1, max_pages + 1):
            if len(all_articles) >= max_articles:
                break

            url = (
                f"{CAFEF_BASE_URL}/{pattern}.html"
                if page == 1
                else f"{CAFEF_BASE_URL}/{pattern}-p{page}.html"
            )

            resp = _get(url)
            if resp is None:
                break
            if "Không tìm thấy" in resp.text[:500] or len(resp.text) < 3000:
                break

            page_arts = _parse_listing_page(resp.text)
            if not page_arts:
                break

            pattern_found = True
            new_count = 0
            for art in page_arts:
                if art["url"] not in seen_urls and len(all_articles) < max_articles:
                    # Validate date ngay khi crawl
                    art_dt = _parse_article_date(art.get("date", ""))
                    art["date_parsed"] = _date_to_str(art_dt) if art_dt else None
                    seen_urls.add(art["url"])
                    all_articles.append(art)
                    new_count += 1

            print(f"[SentimentCache] {ticker} trang {page}: +{new_count} → tổng {len(all_articles)}")
            if new_count == 0:
                break

            time.sleep(REQUEST_DELAY)

        if pattern_found and all_articles:
            break

    # Enrich snippet cho bài không đủ nội dung
    enriched = 0
    for art in all_articles:
        combined = (art.get("title", "") + " " + art.get("snippet", "")).strip()
        if len(combined) < 80 and art.get("url") and enriched < 15:
            content = _fetch_article_content(art["url"])
            if content:
                art["snippet"] = content[:1200]
                enriched += 1
            time.sleep(REQUEST_DELAY * 0.5)

    print(f"[SentimentCache] ✓ {ticker}: {len(all_articles)} bài, {enriched} enriched")
    return all_articles


# ── Score articles (reuse logic từ sentiment_agent) ────────────────────────────

def _score_articles(articles: List[dict]) -> List[dict]:
    from agents.sentiment_agent import _score_text
    scored = []
    for art in articles:
        text = (art.get("title", "") + " " + art.get("snippet", "")).strip()
        if text:
            s = _score_text(text)
            scored.append({
                "title":         art.get("title", ""),
                "url":           art.get("url", ""),
                "date":          art.get("date", ""),
                "date_parsed":   art.get("date_parsed"),   # YYYY-MM-DD hoặc None
                "label":         s["label"],
                "numeric_score": s["numeric_score"],
                "confidence":    s["confidence"],
                "content":       text[:200],
            })
    return scored


# ── Aggregate (reuse từ sentiment_agent) ──────────────────────────────────────

def _aggregate(scored: List[dict]) -> Dict[str, Any]:
    from agents.sentiment_agent import _aggregate_sentiment
    return _aggregate_sentiment(scored)


# ── SentimentCache class ───────────────────────────────────────────────────────

class SentimentCache:
    """
    Cache sentiment lịch sử cho một mã cổ phiếu.

    Vòng đời:
        cache = SentimentCache(symbol="VNM")
        cache.preload()                           # crawl CafeF 1 lần
        sent_data, report = cache.get_at("2024-03-15", llm)   # dùng trong backtest
    """

    def __init__(self, symbol: str, cache_dir: str = "."):
        self.symbol    = symbol.upper()
        self.cache_dir = cache_dir
        self._scored_articles: List[dict] = []    # tất cả bài đã score
        self._loaded = False
        self._cache_path = os.path.join(
            cache_dir, CACHE_FILE_TPL.format(symbol=self.symbol)
        )

    # ── Preload ────────────────────────────────────────────────────────────────

    def preload(
        self,
        force_recrawl: bool = False,
        max_articles: int   = MAX_ARTICLES_PRELOAD,
    ) -> int:
        """
        Crawl và score tất cả bài báo.
        Lưu vào file JSON để tái sử dụng giữa các lần chạy backtest.

        Returns:
            Số bài đã score.
        """
        # Thử load từ đĩa trước
        if not force_recrawl and os.path.exists(self._cache_path):
            loaded = self._load_from_disk()
            if loaded > 0:
                print(f"[SentimentCache] {self.symbol}: Load từ đĩa — {loaded} bài ✓")
                self._loaded = True
                return loaded

        print(f"[SentimentCache] {self.symbol}: Crawl CafeF ({max_articles} bài)...")
        raw_articles = _crawl_articles_full(self.symbol, max_articles=max_articles)
        scored       = _score_articles(raw_articles)

        # Loại bỏ bài không có ngày (không thể dùng cho time-filtered backtest)
        with_date    = [a for a in scored if a.get("date_parsed")]
        without_date = [a for a in scored if not a.get("date_parsed")]

        print(
            f"[SentimentCache] {self.symbol}: {len(with_date)} bài có ngày, "
            f"{len(without_date)} bài không có ngày"
        )

        self._scored_articles = scored   # giữ tất cả (bài không ngày dùng làm fallback)
        self._save_to_disk()
        self._loaded = True
        return len(scored)

    # ── Get sentiment tại một thời điểm ───────────────────────────────────────

    def get_at(
        self,
        cutoff_date: str,
        llm,
        window_days: int = 90,
        min_articles: int = 3,
    ) -> Tuple[Dict[str, Any], str]:
        """
        Trả về (sentiment_data, sentiment_report) sử dụng bài báo
        được đăng trong khoảng [cutoff_date - window_days, cutoff_date].

        Args:
            cutoff_date  : "YYYY-MM-DD" — ngày cuối cửa sổ backtest
            llm          : LLM instance để tạo báo cáo
            window_days  : Chỉ dùng bài trong N ngày gần nhất
            min_articles : Nếu ít hơn min_articles bài, dùng neutral

        Returns:
            (sentiment_data dict, report string)
        """
        if not self._loaded:
            self.preload()

        cutoff_dt = _cutoff_dt(cutoff_date)

        # Filter: bài có ngày ≤ cutoff VÀ trong window_days gần nhất
        filtered = []
        for art in self._scored_articles:
            dp = art.get("date_parsed")
            if dp:
                try:
                    art_dt = datetime.strptime(dp, "%Y-%m-%d")
                    days_diff = (cutoff_dt - art_dt).days
                    if 0 <= days_diff <= window_days:
                        filtered.append(art)
                except ValueError:
                    continue

        print(
            f"[SentimentCache] {self.symbol} @ {cutoff_date}: "
            f"{len(filtered)} bài (window={window_days}d)"
        )

        # Fallback: không đủ bài có ngày → dùng tất cả bài không có ngày
        if len(filtered) < min_articles:
            no_date_articles = [a for a in self._scored_articles if not a.get("date_parsed")]
            filtered = filtered + no_date_articles[:max(0, min_articles - len(filtered))]
            print(
                f"[SentimentCache] {self.symbol}: Bổ sung {len(no_date_articles)} "
                f"bài không có ngày làm fallback"
            )

        if not filtered:
            return self._neutral_result(cutoff_date)

        # Tổng hợp sentiment
        main_agg = _aggregate(filtered)

        sentiment_data = {
            "target_stock":      self.symbol,
            "main_sentiment":    main_agg,
            "scored_articles":   filtered[:15],
            "related_companies": [],
            "related_sentiment": {},
            "model_used":        "cached-historical",
            "cutoff_date":       cutoff_date,
            "n_articles_used":   len(filtered),
        }

        # Tạo báo cáo ngắn (không gọi LLM để tiết kiệm rate limit)
        report = self._build_short_report(main_agg, filtered, cutoff_date)

        return sentiment_data, report

    # ── Neutral fallback ───────────────────────────────────────────────────────

    def _neutral_result(self, cutoff_date: str) -> Tuple[Dict, str]:
        neutral_agg = {
            "label": "neutral", "avg_score": 0.0, "article_count": 0,
            "positive": 0, "negative": 0, "neutral_count": 0,
        }
        report = (
            f"## 📰 Sentiment lịch sử — {self.symbol} @ {cutoff_date}\n\n"
            "⚠️ Không có bài báo trong khoảng thời gian này.\n"
            "Sentiment = neutral (0.0)."
        )
        return {
            "target_stock": self.symbol, "main_sentiment": neutral_agg,
            "scored_articles": [], "related_companies": [],
            "related_sentiment": {}, "model_used": "neutral-fallback",
            "cutoff_date": cutoff_date, "n_articles_used": 0,
        }, report

    # ── Short report (không cần LLM) ──────────────────────────────────────────

    def _build_short_report(
        self,
        main_agg: Dict,
        articles: List[dict],
        cutoff_date: str,
    ) -> str:
        avg   = main_agg.get("avg_score", 0.0)
        lbl   = main_agg.get("label", "neutral").upper()
        n     = main_agg.get("article_count", len(articles))
        pos   = main_agg.get("positive", 0)
        neg   = main_agg.get("negative", 0)
        neu_c = main_agg.get("neutral_count", 0)

        bar_size = int(abs(avg) * 10)
        bar = f"{'█' * bar_size}" if bar_size > 0 else "▒"

        # 5 bài gần nhất
        recent = sorted(
            [a for a in articles if a.get("date_parsed")],
            key=lambda x: x["date_parsed"],
            reverse=True,
        )[:5]
        art_lines = "\n".join(
            f"  {i+1}. {'🟢' if a['label']=='positive' else '🔴' if a['label']=='negative' else '⚪'}"
            f" [{a['label'].upper()}] {a['title'][:70]}"
            for i, a in enumerate(recent)
        )

        return (
            f"## 📰 Sentiment lịch sử — {self.symbol} @ {cutoff_date}\n\n"
            f"| Chỉ số | Giá trị |\n|--------|----------|\n"
            f"| Số bài (window 90d) | {n} |\n"
            f"| Điểm sentiment TB | **{avg:+.4f}** |\n"
            f"| Nhận định | **{lbl}** |\n"
            f"| Phân bổ | 🟢{pos} / ⚪{neu_c} / 🔴{neg} |\n"
            f"| Thanh cảm xúc | {lbl} ({avg:+.3f}) {bar} |\n\n"
            f"### 5 bài gần nhất (≤ {cutoff_date})\n{art_lines or '_Không có_'}\n"
        )

    # ── Disk persistence ───────────────────────────────────────────────────────

    def _save_to_disk(self):
        try:
            with open(self._cache_path, "w", encoding="utf-8") as f:
                json.dump({
                    "symbol":           self.symbol,
                    "saved_at":         datetime.now().isoformat(),
                    "scored_articles":  self._scored_articles,
                }, f, ensure_ascii=False, indent=2)
            print(f"[SentimentCache] Đã lưu {self._cache_path}")
        except Exception as e:
            print(f"[SentimentCache] Lỗi lưu cache: {e}")

    def _load_from_disk(self) -> int:
        try:
            with open(self._cache_path, encoding="utf-8") as f:
                data = json.load(f)
            self._scored_articles = data.get("scored_articles", [])
            saved_at = data.get("saved_at", "unknown")
            print(f"[SentimentCache] Load {self.symbol}: {len(self._scored_articles)} bài (saved {saved_at})")
            return len(self._scored_articles)
        except Exception as e:
            print(f"[SentimentCache] Lỗi load cache: {e}")
            return 0

    def clear_disk_cache(self):
        if os.path.exists(self._cache_path):
            os.remove(self._cache_path)
            print(f"[SentimentCache] Đã xóa {self._cache_path}")


# ── Multi-symbol preloader (dùng trước khi chạy backtest) ─────────────────────

class BacktestSentimentStore:
    """
    Quản lý SentimentCache cho nhiều mã (target + related).
    Gọi một lần trước khi chạy backtest.
    """

    def __init__(self, cache_dir: str = "."):
        self.cache_dir = cache_dir
        self._caches: Dict[str, SentimentCache] = {}

    def preload_symbol(
        self,
        symbol: str,
        force_recrawl: bool = False,
    ) -> SentimentCache:
        """Preload cache cho một mã."""
        if symbol not in self._caches:
            self._caches[symbol] = SentimentCache(symbol, self.cache_dir)
        cache = self._caches[symbol]
        if not cache._loaded:
            cache.preload(force_recrawl=force_recrawl)
        return cache

    def get_sentiment_at(
        self,
        symbol: str,
        cutoff_date: str,
        llm,
        window_days: int = 90,
    ) -> Tuple[Dict, str]:
        """
        Trả về sentiment cho symbol tại cutoff_date.
        Tự động preload nếu chưa có cache.
        """
        cache = self.preload_symbol(symbol)
        return cache.get_at(cutoff_date, llm, window_days=window_days)

    def preload_with_related(
        self,
        main_symbol: str,
        related_symbols: List[str],
        force_recrawl: bool = False,
    ):
        """Preload main symbol + related symbols cùng lúc."""
        all_symbols = [main_symbol] + related_symbols
        print(f"\n[BacktestSentimentStore] Preloading {len(all_symbols)} mã: {all_symbols}")
        for sym in all_symbols:
            self.preload_symbol(sym, force_recrawl=force_recrawl)
            time.sleep(2)   # throttle giữa các mã
        print(f"[BacktestSentimentStore] ✓ Hoàn thành preload {len(all_symbols)} mã")