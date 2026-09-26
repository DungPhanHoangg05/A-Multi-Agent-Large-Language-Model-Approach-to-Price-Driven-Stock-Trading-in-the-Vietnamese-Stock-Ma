"""Nạp dữ liệu thị trường chỉ từ vnstock/VCI và vnstock/KBS."""

from __future__ import annotations

import re
import time
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

import pandas as pd
import numpy as np


REQUIRED_COLS = ["Datetime", "Open", "High", "Low", "Close", "Volume"]
INTERVAL_MAP = {
    "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1H", "1H": "1H", "1d": "1D", "1w": "1W", "1mo": "1M",
}
INTRADAY_INTERVALS = {"5m", "15m", "30m", "1h", "1H"}
TIMEFRAME_CONFIG = {
    "5m": {"lookback_days": 7, "tail": 250, "candles": 78, "display": "5 Phút", "date_fmt": "%d/%m %H:%M", "tick_every": 8, "group": "intraday"},
    "15m": {"lookback_days": 15, "tail": 200, "candles": 60, "display": "15 Phút", "date_fmt": "%d/%m %H:%M", "tick_every": 6, "group": "intraday"},
    "30m": {"lookback_days": 30, "tail": 200, "candles": 50, "display": "30 Phút", "date_fmt": "%d/%m %H:%M", "tick_every": 5, "group": "intraday"},
    "1h": {"lookback_days": 90, "tail": 200, "candles": 45, "display": "1 Giờ", "date_fmt": "%d/%m %H:%M", "tick_every": 5, "group": "intraday"},
    "1H": {"lookback_days": 90, "tail": 200, "candles": 45, "display": "1 Giờ", "date_fmt": "%d/%m %H:%M", "tick_every": 5, "group": "intraday"},
    "1d": {"lookback_days": 400, "tail": 200, "candles": 45, "display": "1 Ngày", "date_fmt": "%Y-%m-%d", "tick_every": 5, "group": "swing"},
    "1w": {"lookback_days": 900, "tail": 120, "candles": 52, "display": "1 Tuần", "date_fmt": "%Y-%m-%d", "tick_every": 5, "group": "swing"},
    "1mo": {"lookback_days": 2200, "tail": 60, "candles": 36, "display": "1 Tháng", "date_fmt": "%Y-%m", "tick_every": 4, "group": "longterm"},
}
DATA_SOURCES = ["VCI", "KBS"]
CACHE_TTL_SECONDS = 300
SYMBOL_CACHE_TTL = 3600

_cache: dict[tuple[str, str], tuple[float, pd.DataFrame]] = {}
_symbol_cache: Optional[List[dict]] = None
_symbol_cache_ts = 0.0
_vnstock_ok: Optional[bool] = None
_STOCK_CODE_RE = re.compile(r"^[A-Z]{2,5}[0-9]?$|^E1VF[A-Z0-9]{2,6}$")
_DERIVATIVE_RE = re.compile(r"^C[A-Z]{2,4}\d{4}$|^VN30F\d{4}$|^[A-Z]{2,5}\d{4,}$")


def get_timeframe_cfg(interval: str) -> dict:
    """Trả về cấu hình khung thời gian, mặc định theo ngày."""
    return TIMEFRAME_CONFIG.get(interval, TIMEFRAME_CONFIG["1d"])


def _is_pure_stock(code: str, name: str = "") -> bool:
    """Loại mã phái sinh, chứng quyền và trái phiếu."""
    if not code or _DERIVATIVE_RE.match(code):
        return False
    blocked = ("chứng quyền", "warrant", "futures", "hợp đồng tương lai", "trái phiếu", "bond", "vn30f")
    return not any(word in name.lower() for word in blocked) and bool(_STOCK_CODE_RE.match(code))


def check_vnstock_available() -> bool:
    """Kiểm tra thư viện trước khi gọi VCI hoặc KBS."""
    global _vnstock_ok
    if _vnstock_ok is None:
        try:
            import vnstock  # noqa: F401
            _vnstock_ok = True
        except ImportError:
            _vnstock_ok = False
    return _vnstock_ok


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Đưa tên cột hai nguồn về hợp đồng OHLCV của hệ thống."""
    aliases = {
        "time": "Datetime", "date": "Datetime", "datetime": "Datetime",
        "tradingdate": "Datetime", "trading_date": "Datetime",
        "open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume",
    }
    return df.rename(columns={column: aliases.get(str(column).strip().lower(), column) for column in df.columns})


def _fetch_from_vnstock(
    symbol: str, start: str, end: str, interval_str: str, source: str
) -> pd.DataFrame:
    """Tải OHLCV; vnstock 4.0.9 trả chỉ số theo điểm, cổ phiếu theo nghìn VND."""
    if source not in DATA_SOURCES:
        raise ValueError(f"Nguồn dữ liệu không được phép: {source}")
    from vnstock.api.quote import Quote

    kwargs = {"floating": None} if source == "KBS" else {}
    frame = Quote(symbol=symbol.upper(), source=source).history(
        start=start, end=end, interval=interval_str, **kwargs
    )
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise ValueError(f"{source}: dữ liệu rỗng cho {symbol}")
    return frame


def _clean_realtime_frame(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Kiểm tra cột, ngày và OHLCV trước khi đưa nến vào cache."""
    clean = _normalise_columns(frame)
    missing = [column for column in REQUIRED_COLS if column not in clean.columns]
    if missing:
        raise ValueError(f"{symbol}: thiếu cột {missing}")
    clean = clean[REQUIRED_COLS].copy()
    clean["Datetime"] = pd.to_datetime(clean["Datetime"], errors="coerce")
    if clean["Datetime"].isna().any() or clean["Datetime"].duplicated().any():
        raise ValueError(f"{symbol}: ngày giao dịch thiếu hoặc trùng")
    numeric = REQUIRED_COLS[1:]
    clean[numeric] = clean[numeric].apply(pd.to_numeric, errors="coerce")
    if not np.isfinite(clean[numeric].to_numpy(dtype=float)).all():
        raise ValueError(f"{symbol}: OHLCV có giá trị không hữu hạn")
    prices = clean[["Open", "High", "Low", "Close"]]
    if (prices <= 0).any().any() or (clean["Volume"] < 0).any():
        raise ValueError(f"{symbol}: giá hoặc khối lượng không hợp lệ")
    if (
        (clean["High"] < prices[["Open", "Low", "Close"]].max(axis=1)).any()
        or (clean["Low"] > prices[["Open", "High", "Close"]].min(axis=1)).any()
    ):
        raise ValueError(f"{symbol}: OHLC không nhất quán")
    return clean.sort_values("Datetime").reset_index(drop=True)


def fetch_realtime_ohlcv(
    symbol: str,
    interval: str = "1d",
    lookback_days: Optional[int] = None,
    tail: Optional[int] = None,
    use_cache: bool = True,
) -> Tuple[pd.DataFrame, str]:
    """Lấy OHLCV từ VCI rồi KBS; trả lỗi nếu cả hai đều thất bại."""
    if interval not in INTERVAL_MAP:
        return pd.DataFrame(), f"Khung thời gian không hỗ trợ: {interval}"
    config = get_timeframe_cfg(interval)
    lookback_days = config["lookback_days"] if lookback_days is None else lookback_days
    tail = config["tail"] if tail is None else tail
    if lookback_days < 1 or tail < 1:
        return pd.DataFrame(), "lookback_days và tail phải là số dương"
    cache_key = (symbol.upper(), interval)
    cached = _cache.get(cache_key)
    if use_cache and cached and time.time() - cached[0] < CACHE_TTL_SECONDS and len(cached[1]) >= tail:
        return cached[1].tail(tail).reset_index(drop=True), ""
    end = datetime.now()
    start = end - timedelta(days=lookback_days)
    errors = []
    for source in DATA_SOURCES:
        try:
            raw = _fetch_from_vnstock(
                symbol, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"),
                INTERVAL_MAP[interval], source,
            )
            clean = _clean_realtime_frame(raw, symbol)
            _cache[cache_key] = (time.time(), clean)
            print(f"[RealtimeLoader] {symbol.upper()} ← vnstock/{source}: {len(clean)} nến")
            return clean.tail(tail).reset_index(drop=True), ""
        except Exception as exc:
            errors.append(f"{source}: {exc}")
    return pd.DataFrame(), f"Không lấy được OHLCV {symbol.upper()}: {' | '.join(errors)}"


def _listing_from_vnstock(source: str) -> List[dict]:
    """Tải và lọc danh sách cổ phiếu từ một provider vnstock."""
    from vnstock.api.listing import Listing

    raw = Listing(source=source).symbols_by_exchange(exchange="HOSE")
    if not isinstance(raw, pd.DataFrame) or raw.empty:
        raise ValueError(f"{source}: danh sách mã rỗng")
    frame = raw.rename(columns={"symbol": "code", "organ_name": "name", "company_name": "name"}).copy()
    if "code" not in frame:
        raise ValueError(f"{source}: thiếu cột mã")
    for column in ("name", "exchange"):
        if column not in frame:
            frame[column] = ""
    frame["code"] = frame["code"].fillna("").astype(str).str.strip().str.upper()
    frame["name"] = frame["name"].fillna("").astype(str).str.strip()
    frame["exchange"] = frame["exchange"].fillna("").astype(str).str.strip().str.upper()
    mask = frame["code"].str.match(_STOCK_CODE_RE)
    mask &= ~frame["code"].str.match(_DERIVATIVE_RE)
    if "type" in frame:
        mask &= frame["type"].fillna("").astype(str).str.lower().eq("stock")
    mask &= ~frame["name"].str.lower().str.contains(
        "chứng quyền|warrant|futures|hợp đồng tương lai|trái phiếu|bond|vn30f", regex=True
    )
    return frame.loc[mask, ["code", "name", "exchange"]].drop_duplicates("code").to_dict("records")


def fetch_dstock_all_symbols(force_refresh: bool = False) -> List[dict]:
    """Lấy danh sách mã từ KBS rồi VCI, cache một giờ."""
    global _symbol_cache, _symbol_cache_ts
    if not force_refresh and _symbol_cache is not None and time.time() - _symbol_cache_ts < SYMBOL_CACHE_TTL:
        return _symbol_cache
    if not check_vnstock_available():
        return []
    for source in ("KBS", "VCI"):
        try:
            symbols = _listing_from_vnstock(source)
            if symbols:
                _symbol_cache = sorted(symbols, key=lambda row: row["code"])
                _symbol_cache_ts = time.time()
                print(f"[RealtimeLoader] Danh sách mã ← vnstock/{source}: {len(_symbol_cache)} mã")
                return _symbol_cache
        except Exception as exc:
            print(f"[RealtimeLoader] Danh sách mã {source} lỗi: {exc}")
    return []


def get_all_symbols_realtime() -> List[dict]:
    """Giữ giao diện danh sách mã cho web và sentiment agent."""
    return fetch_dstock_all_symbols()


def clear_cache(symbol: Optional[str] = None, interval: Optional[str] = None) -> None:
    """Xóa cache OHLCV theo mã/khung hoặc xóa toàn bộ."""
    if symbol and interval:
        _cache.pop((symbol.upper(), interval), None)
    else:
        _cache.clear()
    print("[RealtimeLoader] Cache đã xóa.")


def get_cache_info() -> dict:
    """Trả thông tin cache bằng kiểu JSON nguyên bản."""
    now = time.time()
    return {
        "ttl_seconds": CACHE_TTL_SECONDS,
        "entries": [
            {"symbol": symbol, "interval": interval, "rows": len(frame),
             "age_sec": int(now - timestamp), "expired": now - timestamp >= CACHE_TTL_SECONDS}
            for (symbol, interval), (timestamp, frame) in _cache.items()
        ],
    }


def get_realtime_status() -> dict:
    """Kiểm tra kết nối VCI/KBS qua một mã cổ phiếu."""
    status = {"available": check_vnstock_available(), "library": "vnstock",
              "sources": list(DATA_SOURCES), "cache_ttl": CACHE_TTL_SECONDS,
              "cached_items": len(_cache)}
    if not status["available"]:
        status["install_cmd"] = "py -3.13 -m pip install -r requirements.txt"
        return status
    end = datetime.now()
    start = end - timedelta(days=10)
    for source in DATA_SOURCES:
        try:
            frame = _fetch_from_vnstock(
                "VNM", start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), "1D", source
            )
            status.update({"connected": True, "connected_via": source,
                           "test_symbol": "VNM", "test_rows": len(frame)})
            return status
        except Exception:
            continue
    status.update({"connected": False, "test_symbol": "VNM", "test_rows": 0,
                   "error": "Cả VCI và KBS đều không trả dữ liệu"})
    return status


def get_stock_info_realtime(code: str) -> dict:
    """Lấy tên, sàn và hồ sơ từ hai provider được phép."""
    code = code.strip().upper()
    result = {"code": code, "source": "realtime", "exists": False}
    match = next((row for row in fetch_dstock_all_symbols() if row["code"] == code), None)
    if match:
        result.update({"exists": True, "name": match["name"], "exchange": match["exchange"]})
    if not check_vnstock_available():
        return result
    from vnstock.api.company import Company

    for source in DATA_SOURCES:
        try:
            frame = Company(symbol=code, source=source).overview()
            if frame is None or frame.empty:
                continue
            row = frame.iloc[0]
            result["exists"] = True
            fields = {
                "organ_name": ("organ_name",),
                "en_organ_name": ("en_organ_name",),
                "exchange": ("exchange",),
                "industry": ("industry_name", "sector"),
                "website": ("website",),
            }
            for target, candidates in fields.items():
                if result.get(target):
                    continue
                for candidate in candidates:
                    value = row.get(candidate)
                    if value is not None and pd.notna(value) and str(value).strip():
                        result[target] = str(value)
                        break
            if result.get("organ_name") and result.get("industry") and result.get("website"):
                break
        except Exception:
            continue
    return result
