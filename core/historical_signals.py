"""Trích năm tín hiệu lịch sử và lưu provenance trước khi ghép nhãn kinh tế."""

from __future__ import annotations

import copy
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import re
from datetime import date
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from core.bayesian_memory import (
    DEFAULT_DATA_DIR, SYMBOLS, ExecutionLoader, atomic_write_json, iso_date, read_json, validate_signals,
)
from core.execution_prices import PRICE_COLUMNS, load_verified_execution_data, raw_point_in_time_snapshot
from data_manager.sentiment_cache import SentimentCache

ROOT = Path(__file__).resolve().parents[1]
CODE_FILES = (
    "core/historical_signals.py", "core/execution_prices.py", "core/bayesian_memory.py",
    "agents/indicator_agent.py", "agents/pattern_agent.py", "agents/trend_agent.py",
    "agents/alpha_agent.py", "data_manager/sentiment_cache.py", "agents/sentiment_agent.py",
    "core/alpha_compare.py", "utils/alpha_selector.py", "utils/static_util.py",
    "utils/graph_util.py", "utils/graph_setup.py", "utils/i18n.py",
)
MODEL_CONFIG_KEYS = {
    "agent_llm_model", "graph_llm_model", "agent_llm_temperature", "graph_llm_temperature",
    "agent_llm_max_tokens", "graph_llm_max_tokens",
}


def native_json(value: Any) -> Any:
    """Chuyển scalar NumPy trong báo cáo thành kiểu JSON gốc; cấm số lỗi."""
    if isinstance(value, np.generic):
        return native_json(value.item())
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise ValueError("Provenance phải dùng khóa chuỗi")
        return {key: native_json(item) for key, item in value.items()}
    if type(value) in (list, tuple):
        return [native_json(item) for item in value]
    if type(value) is float and not math.isfinite(value):
        raise ValueError("Provenance chứa số không hữu hạn")
    if value is None or type(value) in (str, int, float, bool):
        return value
    raise ValueError("Provenance chứa kiểu không hỗ trợ JSON")


def digest(value: Any) -> str:
    """Băm nội dung JSON chuẩn hóa, độc lập thứ tự khóa."""
    content = json.dumps(native_json(value), sort_keys=True, ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def snapshot_payload(frame: pd.DataFrame) -> dict[str, list[Any]]:
    """Xuất sáu trường OHLCV bằng phép vector hóa và kiểu Python gốc."""
    return {"Datetime": frame["Datetime"].dt.strftime("%Y-%m-%d").tolist(), **{
        key: frame[key].astype(float).tolist() for key in PRICE_COLUMNS if key != "Datetime"
    }}


def report_signal(report: str, labels: tuple[str, ...]) -> str:
    """Đọc đúng trường hướng đã chuẩn hóa; từ chối báo cáo thiếu/không xác định."""
    if type(report) is not str or not report.strip():
        raise ValueError("Báo cáo agent thiếu nội dung")
    cleaned = report.replace("**", "")
    fields = re.findall(r"^\s*(?:[-*]\s*)?(?:" + "|".join(re.escape(label) for label in labels)
                        + r")\s*:\s*(.+)$", cleaned, flags=re.IGNORECASE | re.MULTILINE)
    if len(fields) != 1 or "|" in fields[0]:
        raise ValueError("Báo cáo thiếu trường tín hiệu duy nhất hoặc còn mẫu hướng")
    text = fields[0].strip().lower()
    patterns = {
        "BULLISH": r"^(?:tăng|xu hướng tăng|bullish|uptrend|upward|rising|up)(?:\b|\s)",
        "BEARISH": r"^(?:giảm|xu hướng giảm|bearish|downtrend|downward|falling|down)(?:\b|\s)",
        "NEUTRAL": r"^(?:trung tính|đi ngang|hỗn hợp|neutral|mixed|sideways|consolidation|range)(?:\b|\s)",
    }
    for signal, pattern in patterns.items():
        if re.search(pattern, text):
            return signal
    raise ValueError("Không xác định được nhãn hướng trong báo cáo agent")


class FrozenSentimentSnapshot:
    """Adapter chỉ trả dữ liệu đã lọc trước; không crawl và không mượn tin thiếu ngày."""

    def __init__(self, symbol: str, cutoff: str, articles: list[dict[str, Any]]) -> None:
        self.symbol, self.cutoff = symbol, iso_date(cutoff)
        if type(articles) is not list:
            raise ValueError("Tin lịch sử phải là danh sách")
        endpoint = date.fromisoformat(cutoff)
        visible: list[dict[str, Any]] = []
        for article in articles:
            if type(article) is not dict:
                raise ValueError("Bài báo không hợp lệ")
            published = article.get("date_parsed")
            if published is None or published == "":
                continue
            published = iso_date(published)
            age = (endpoint - date.fromisoformat(published)).days
            if not 0 <= age <= 90:
                continue
            item = native_json(copy.deepcopy(article))
            if item.get("label") not in {"positive", "negative", "neutral"}:
                raise ValueError("Tin lịch sử chưa có nhãn sentiment hợp lệ")
            score = item.get("numeric_score")
            if type(score) not in (int, float) or not math.isfinite(score) or not -1 <= score <= 1:
                raise ValueError("Điểm sentiment lịch sử không hợp lệ")
            visible.append(item)
        self.articles = sorted(visible, key=lambda item: (item["date_parsed"], digest(item)), reverse=True)
        cache = SentimentCache(symbol)
        cache._loaded = True
        cache._scored_articles = copy.deepcopy(self.articles)
        self.data, self.report = cache.get_at(cutoff, llm=None, strict_research_mode=True, window_days=90)
        self.data = native_json(self.data)
        self._validate(self.data)

    def _validate(self, data: dict[str, Any]) -> None:
        if data.get("cutoff_date") != self.cutoff:
            raise ValueError("Sentiment trả cutoff khác ngày quyết định")
        for article in data.get("scored_articles", []):
            published = iso_date(article.get("date_parsed"))
            if published > self.cutoff:
                raise ValueError("Sentiment chứa bài báo tương lai")

    def get_sentiment_at(self, symbol: str, cutoff_date: str, llm: Any,
                         window_days: int = 90) -> tuple[dict[str, Any], str]:
        """Giao diện tương thích Alpha Agent với kiểm tra cutoff nghiêm ngặt."""
        if symbol != self.symbol or cutoff_date != self.cutoff or window_days != 90:
            raise ValueError("Alpha truy vấn sentiment ngoài snapshot đã đóng băng")
        self._validate(self.data)
        return copy.deepcopy(self.data), self.report


def disk_articles(cache_dir: Path, symbol: str) -> list[dict[str, Any]]:
    """Chỉ đọc cache tin đã chấm điểm; không tự thu thập khi cache thiếu."""
    path = cache_dir / f"sentiment_cache_{symbol}.json"
    if not path.exists():
        return []
    payload = read_json(path)
    if type(payload) is not dict or payload.get("symbol") != symbol or type(payload.get("scored_articles")) is not list:
        raise ValueError("Cache sentiment sai mã hoặc cấu trúc")
    return payload["scored_articles"]


class HistoricalSignalExtractor:
    """Chạy upstream một lần, rồi Alpha/Sentiment trên bản sao của cùng snapshot."""

    def __init__(self, upstream: Any, alpha_node: Callable[[dict[str, Any]], dict[str, Any]],
                 checkpoint_dir: str | Path, model_config: dict[str, Any], *,
                 execution_loader: ExecutionLoader | None = None,
                 article_loader: Callable[[str], list[dict[str, Any]]] | None = None,
                 window_size: int = 45, norm_method: str = "zscore_tanh",
                 alpha_weights: dict[str, float] | None = None) -> None:
        if not MODEL_CONFIG_KEYS <= set(model_config):
            raise ValueError("Cần ghi đủ model, nhiệt độ và giới hạn token vào provenance")
        if type(window_size) is not int or window_size < 20 or window_size > 600:
            raise ValueError("Cửa sổ agent phải từ 20 đến 600 nến")
        self.upstream, self.alpha_node = upstream, alpha_node
        self.checkpoint_dir = Path(checkpoint_dir)
        self.execution_loader = execution_loader or (lambda symbol: load_verified_execution_data(DEFAULT_DATA_DIR, symbol))
        self.article_loader = article_loader or (lambda symbol: disk_articles(ROOT, symbol))
        self.config = native_json({"models": {key: model_config[key] for key in sorted(MODEL_CONFIG_KEYS)},
                                  "window_size": window_size, "norm_method": norm_method,
                                  "alpha_weights": alpha_weights, "language": "vi", "time_frame": "1d"})

    @classmethod
    def from_graph_builder(cls, builder: Any, checkpoint_dir: str | Path,
                           model_config: dict[str, Any], **kwargs: Any) -> HistoricalSignalExtractor:
        """Tái sử dụng chuỗi graph hiện có; không khởi tạo Decision Agent."""
        from agents.alpha_agent import create_alpha_agent

        return cls(builder.compile_upstream(), create_alpha_agent(builder.agent_llm, strict_research_mode=True),
                   checkpoint_dir, model_config, **kwargs)

    def extract(self, symbol: str, as_of_date: str) -> dict[str, Any]:
        """Lưu checkpoint theo điểm; từ chối thay đổi đầu vào hoặc upstream dở dang."""
        if symbol not in SYMBOLS:
            raise ValueError("Mã lịch sử không hợp lệ")
        cutoff = iso_date(as_of_date)
        frame, _ = self.execution_loader(symbol)
        snapshot = raw_point_in_time_snapshot(frame, cutoff)
        if len(snapshot) < 600:
            raise ValueError("Thiếu 600 nến khởi động Alpha")
        sentiment = FrozenSentimentSnapshot(symbol, cutoff, self.article_loader(symbol))
        prefix = snapshot_payload(snapshot)
        provenance = {"symbol": symbol, "as_of_date": cutoff, "price_basis": "UNADJUSTED_EXECUTION",
                      "price_source": "VCI", "price_unit": "thousand_VND", "price_sha256": digest(prefix),
                      "price_start_date": prefix["Datetime"][0], "price_end_date": prefix["Datetime"][-1],
                      "price_rows": int(len(snapshot)), "alpha_start_date": prefix["Datetime"][-600],
                      "alpha_end_date": cutoff, "news_sha256": digest(sentiment.articles),
                      "news_dates": [item["date_parsed"] for item in sentiment.articles],
                      "news_count": int(len(sentiment.articles)), "news_is_reliable": bool(sentiment.data["is_reliable"]),
                      "sentiment_model": sentiment.data["model_used"], "config": copy.deepcopy(self.config),
                      "runtime": {"python": platform.python_version(), **{
                          name: importlib.metadata.version(name) for name in
                          ("numpy", "pandas", "scipy", "TA-Lib", "langgraph", "langchain-core", "langchain-groq")}},
                      "code_sha256": {name: hashlib.sha256((ROOT / name).read_text(encoding="utf-8").encode("utf-8")).hexdigest()
                                      for name in CODE_FILES}}
        signature = digest(provenance)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        path = self.checkpoint_dir / f"{symbol}-{cutoff}.json"
        lock = path.with_suffix(".lock")
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise RuntimeError("Điểm lịch sử đang được xử lý hoặc khóa cần kiểm tra sau gián đoạn") from exc
        os.close(descriptor)
        try:
            return self._extract_locked(path, signature, provenance, snapshot, sentiment)
        finally:
            lock.unlink()

    def _extract_locked(self, path: Path, signature: str, provenance: dict[str, Any],
                        snapshot: pd.DataFrame, sentiment: FrozenSentimentSnapshot) -> dict[str, Any]:
        checkpoint: dict[str, Any] | None = None
        if path.exists():
            envelope = read_json(path)
            if type(envelope) is not dict or set(envelope) != {"payload", "sha256"} or digest(envelope["payload"]) != envelope["sha256"]:
                raise ValueError("Checkpoint tín hiệu sai cấu trúc hoặc checksum")
            checkpoint = envelope["payload"]
            if checkpoint.get("signature") != signature:
                raise ValueError("Đầu vào/cấu hình thay đổi; cần rà soát phiên bản trước khi chạy lại")
            if checkpoint.get("stage") == "COMPLETE":
                result = checkpoint["result"]
                validate_signals(result["agent_signals"])
                return copy.deepcopy(result)
            if checkpoint.get("stage") != "UPSTREAM_COMPLETE":
                raise ValueError("Upstream dở dang; không tự gọi lại cùng điểm lịch sử")

        window = snapshot.tail(self.config["window_size"])
        state = {"stock_name": provenance["symbol"], "time_frame": "1d", "language": "vi",
                 "is_backtest": True, "messages": [], "kline_data": snapshot_payload(window),
                 "point_in_time_df": snapshot.copy(deep=True), "as_of_date": provenance["as_of_date"],
                 "window_end_date": provenance["as_of_date"], "alpha_norm_method": self.config["norm_method"],
                 "alpha_weights": copy.deepcopy(self.config["alpha_weights"])}

        def save(payload: dict[str, Any]) -> None:
            atomic_write_json(path, {"payload": payload, "sha256": digest(payload)})

        if checkpoint is None:
            from utils import static_util

            state["pattern_image"] = static_util.generate_kline_image(
                state["kline_data"], write_artifacts=False).get("pattern_image", "")
            state["trend_image"] = static_util.generate_trend_image(
                state["kline_data"], write_artifacts=False).get("trend_image", "")
            save({"stage": "UPSTREAM_STARTED", "signature": signature})
            shared = self.upstream.invoke(copy.deepcopy(state))
            reports = {key: shared.get(key) for key in ("indicator_report", "pattern_report", "trend_report")}
            if any(type(value) is not str or not value.strip() for value in reports.values()):
                raise ValueError("Upstream thiếu báo cáo; không tạo tín hiệu thay thế")
            checkpoint = {"stage": "UPSTREAM_COMPLETE", "signature": signature, "reports": reports}
            save(checkpoint)

        reports = copy.deepcopy(checkpoint["reports"])
        signals = {
            "trend": report_signal(reports["trend_report"], ("Hướng xu hướng", "Trend direction")),
            "pattern": report_signal(reports["pattern_report"], ("Thiên lệch dự báo", "Directional bias")),
            "indicator_consensus": report_signal(reports["indicator_report"], ("Đồng thuận chủ đạo", "Dominant consensus")),
        }
        alpha_state = copy.deepcopy(state)
        alpha_state.update(copy.deepcopy(reports))
        alpha_state["sentiment_store"] = sentiment
        alpha = self.alpha_node(alpha_state)
        data = native_json(alpha.get("sentiment_data"))
        if type(data) is not dict or any(data.get(key) != value for key, value in sentiment.data.items()):
            raise ValueError("Alpha/Sentiment đã thay đổi snapshot tin lịch sử")
        sentiment._validate(data)
        factors = data.get("alpha_results")
        if (type(factors) is not list or len(factors) != 5
                or any(type(item) is not dict or type(item.get("id")) is not int for item in factors)
                or len({item["id"] for item in factors}) != 5):
            raise ValueError("Alpha phải cung cấp đủ năm factor khác nhau")
        directions = [item.get("signal") for item in factors]
        if any(signal not in {"TĂNG", "GIẢM", "TRUNG TÍNH"} for signal in directions):
            raise ValueError("Alpha chứa nhãn tín hiệu không hợp lệ")
        bullish, bearish = directions.count("TĂNG"), directions.count("GIẢM")
        signals["alpha_consensus"] = "BULLISH" if bullish > bearish else ("BEARISH" if bearish > bullish else "NEUTRAL")
        label = data["main_sentiment"]["label"]
        if label not in {"positive", "negative", "neutral"}:
            raise ValueError("Sentiment thiếu nhãn tổng hợp")
        signals["sentiment"] = {"positive": "POSITIVE", "negative": "NEGATIVE", "neutral": "NEUTRAL"}[label]
        validate_signals(signals)
        for key in ("alpha_report", "sentiment_report"):
            if type(alpha.get(key)) is not str or not alpha[key].strip():
                raise ValueError("Thiếu báo cáo Alpha/Sentiment")
            reports[key] = alpha[key]
        provenance["reports_sha256"] = digest(reports)
        provenance["alpha_factors"] = factors
        result = {"symbol": provenance["symbol"], "as_of_date": provenance["as_of_date"],
                  "agent_signals": signals, "reports": reports, "provenance": native_json(provenance)}
        save({**checkpoint, "stage": "COMPLETE", "result": result})
        return copy.deepcopy(result)
