"""Facts số từ prefix45 PIT và lọc bucket trước bộ chọn task MT-BICL bất biến."""

from __future__ import annotations

from copy import deepcopy
import math
from typing import Any

import numpy as np
import pandas as pd
import talib

from core.mt_bicl_bank import SYMBOLS, content_hash, day
from core.mt_bicl_regimes import RegimeTimeline
from core.mt_bicl_stream import MarketStream
from core.mt_bicl_tasks import TaskBuilder
from core.mt_bicl_contracts import membership_hash, validate_context, validate_fact_packet

NUMERIC = ("macd", "signal", "macd_minus_signal", "close", "sma20", "close_minus_sma20")


def bucket(macd_minus_signal: float | None, close_minus_sma20: float | None) -> str:
    """So sánh float64 trước rounding, không epsilon; zero/missing thuộc UNKNOWN."""
    values = (macd_minus_signal, close_minus_sma20)
    if any(value is None for value in values):
        return "UNKNOWN"
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in values):
        raise ValueError("Trục bucket phải hữu hạn hoặc None")
    if any(value == 0 for value in values):
        return "UNKNOWN"
    return "MACD_"+("POS" if macd_minus_signal > 0 else "NEG")+"_PRICE_"+("POS" if close_minus_sma20 > 0 else "NEG")


def relation(left: float | None, right: float | None) -> str:
    """Phân biệt ABOVE/BELOW/EQUAL và UNKNOWN mà không đọc báo cáo LLM."""
    if left is None or right is None:
        return "UNKNOWN"
    return "ABOVE" if left > right else "BELOW" if left < right else "EQUAL"


def make_fact_packet(frame: pd.DataFrame, symbol: str, query_date: str, *,
                     reported_warnings: list[str] | None = None) -> dict[str, Any]:
    """Chỉ đọc nến <=query; caller chịu xác minh nguồn/quyền, packet bind đúng prefix thô."""
    cutoff = day(query_date)
    if symbol not in SYMBOLS or not {"Datetime", "Open", "High", "Low", "Close", "Volume"} <= set(frame):
        raise ValueError("Nguồn facts thiếu mã/cột OHLCV")
    dates = pd.DatetimeIndex(frame["Datetime"])
    if (dates.tz is not None or dates.hasnans or not dates.equals(dates.normalize())
            or dates.has_duplicates or not dates.is_monotonic_increasing):
        raise ValueError("Lịch nguồn facts không hợp lệ")
    prefix = frame.loc[dates <= pd.Timestamp(cutoff)].tail(45)
    visible_dates = pd.DatetimeIndex(prefix["Datetime"])
    end = str(visible_dates[-1].date()) if len(prefix) else cutoff
    columns = ["Open", "High", "Low", "Close", "Volume"]
    matrix = prefix[columns].to_numpy(dtype=np.float64)
    if not np.isfinite(matrix).all() or (matrix[:, :4] <= 0).any() or (matrix[:, 4] < 0).any():
        raise ValueError("Prefix facts có giá/volume không hợp lệ")
    numeric: dict[str, float | None] = dict.fromkeys(NUMERIC)
    if len(prefix) == 45 and end == cutoff:
        close = prefix["Close"].to_numpy(dtype=np.float64)
        macd, signal, _ = talib.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
        if not np.isfinite([macd[-1], signal[-1]]).all():
            raise ValueError("TA-Lib không trả MACD hữu hạn trên prefix45")
        numeric = {"macd": float(macd[-1]), "signal": float(signal[-1]),
                   "macd_minus_signal": float(macd[-1]-signal[-1]), "close": float(close[-1]),
                   "sma20": float(close[-20:].mean()), "close_minus_sma20": float(close[-1]-close[-20:].mean())}
    macd_zero = relation(numeric["macd"], 0.)
    packet = {"version": "utility_icl_facts_v3", "point_id": symbol+"-"+cutoff,
              "as_of_date": cutoff, "frame_end_date": end, "prefix_rows": len(prefix), "numeric": numeric,
              "bucket": bucket(numeric["macd_minus_signal"], numeric["close_minus_sma20"]),
              "assertions": {"MACD_SIGNAL": relation(numeric["macd"], numeric["signal"]),
                             "MACD_ZERO": {"ABOVE": "POSITIVE", "BELOW": "NEGATIVE", "EQUAL": "ZERO", "UNKNOWN": "UNKNOWN"}[macd_zero],
                             "PRICE_SMA20": relation(numeric["close"], numeric["sma20"])},
              "horizon": "T+2.5", "reported_warnings": deepcopy(reported_warnings or []),
              "source_sha256": {"raw_PIT_prefix": content_hash({"dates": visible_dates.strftime("%Y-%m-%d").tolist(),
                                                                  "columns": columns, "values": matrix.tolist()})}}
    validate_fact_packet(packet)
    return packet


class _BucketStream:
    """View label-blind cùng bucket cho mọi mã, trước rank của TaskBuilder bất biến."""

    def __init__(self, stream: MarketStream, frames: dict[str, pd.DataFrame]) -> None:
        """Giữ cache facts theo prefix riêng; không bọc hoặc thay nhãn trong stream gốc."""
        self.source = stream
        self.calendar = stream.calendar
        self.frames = {symbol: frame.copy() for symbol, frame in frames.items()}
        if set(self.frames) != set(SYMBOLS):
            raise ValueError("Cần bốn nguồn raw cho bucket lịch sử và query")
        self.facts: dict[str, dict[str, Any]] = {}

    def packet(self, symbol: str, cutoff: str) -> dict[str, Any]:
        """Dùng cùng một hàm/cửa sổ cho historical và query, không nhãn trong cache."""
        identifier = symbol+"-"+cutoff
        if identifier not in self.facts:
            self.facts[identifier] = make_fact_packet(self.frames[symbol], symbol, cutoff)
        return deepcopy(self.facts[identifier])

    def features(self, symbol: str, cutoff: str) -> dict[str, Any]:
        """Giữ nguyên bốn feature/scaler student của MT-BICL."""
        return self.source.features(symbol, cutoff)

    def advance(self, cutoff: str) -> list[dict[str, Any]]:
        """Candidate tương lai bị loại trước đọc facts/nhãn; không chọn theo win/loss."""
        rows = self.source.advance(cutoff)
        query_buckets = {symbol: self.packet(symbol, cutoff)["bucket"] for symbol in SYMBOLS}
        result = []
        for row in rows:
            if row["exit_date"] >= cutoff or row["status"] != "AVAILABLE":
                continue
            selected_bucket = query_buckets[row["symbol"]]
            if selected_bucket != "UNKNOWN" and self.packet(row["symbol"], row["as_of_date"])["bucket"] == selected_bucket:
                result.append(row)
        return result


class BucketTaskBuilder:
    """Thêm bộ lọc trước selection MT-BICL; không lọc lại membership đã cắt tám cycle."""

    def __init__(self, bank: dict[str, Any], stream: MarketStream, regimes: RegimeTimeline,
                 frames: dict[str, pd.DataFrame]) -> None:
        """Nguồn/bank/regime phải đã được verifier xác minh trước lệnh thực nghiệm."""
        self.view = _BucketStream(stream, frames)
        self.builder = TaskBuilder(bank, self.view, regimes)

    def build(self, symbol: str, query_date: str) -> dict[str, Any]:
        """Xuất episode tương thích PAIRED_37 cùng proof full precision của context mới."""
        episode = self.builder.build(symbol, query_date)
        facts = self.view.packet(symbol, query_date)
        if facts["prefix_rows"] < 45 or facts["frame_end_date"] != query_date:
            episode.update(status="UNAVAILABLE", prior=[], target=[], K=0, m=0,
                           reasons=[*episode["reasons"], "QUERY_FEATURE_UNAVAILABLE"])
        if facts["bucket"] == "UNKNOWN":
            episode.update(prior=[], target=[], K=0, m=0, reasons=[*episode["reasons"], "UNKNOWN_BUCKET"])
        ids = {identifier for task in episode["prior"] for identifier in task["centroid_fit_ids"]}
        ids.update(row["episode_id"] for row in episode["target"])
        episode["advisor"] = {"version": "utility_icl_context_v3", "bucket": facts["bucket"], "query_facts": facts,
                         "historical_facts": {identifier: deepcopy(self.view.facts[identifier]) for identifier in sorted(ids)}}
        episode["membership_sha256"] = membership_hash(episode)
        validate_context(episode)
        return episode
