"""Bank cycle giá thô MT-BICL theo protocol; không dùng báo cáo hoặc action LLM."""

from __future__ import annotations

from collections import Counter
from datetime import date
from functools import partial
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

from core.backtest_engine import compute_round_trip_net_return
from core.execution_prices import PRICE_COLUMNS, corporate_action_barriers, validate_raw_frame
from core.pit_price_features import FEATURE_COLUMNS, FEATURE_VERSION, PRICE_POLICY_VERSION, REQUIRED_BARS

BANK_VERSION = "mt_bicl_dense_bank"
PROTOCOL_SHA256 = "c94667b3fc6d1924ef187f5456a1f2b77db9beb4d1116a6a56453a2fa73118d4"
SYMBOLS = ("FPT", "MWG", "VCB", "VNM")
TRAIN_END = "2020-12-31"
BANK_END = "2022-12-31"
SOURCE = {"source_library": "vnstock", "primary_source": "VCI",
          "price_basis": "UNADJUSTED_EXECUTION", "price_unit": "thousand_VND"}
PARTITIONS = {"train": ("2018-01-02", TRAIN_END),
              "checkpoint_selection": ("2021-01-01", "2021-12-31"),
              "validation": ("2022-01-01", BANK_END)}


def day(value: Any) -> str:
    """Nhận đúng ngày ISO gốc, không tự sửa giờ hoặc múi giờ."""
    if type(value) is not str or date.fromisoformat(value).isoformat() != value:
        raise ValueError("Ngày phải là chuỗi YYYY-MM-DD")
    return value


def canonical_bytes(value: Any) -> bytes:
    """Chỉ nhận kiểu JSON Python gốc và số hữu hạn trước băm/lưu artifact."""
    def native(item: Any) -> None:
        """Từ chối kiểu NumPy hoặc object lọt vào sidecar."""
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                raise ValueError("Khóa JSON phải là str gốc")
            for child in item.values():
                native(child)
        elif type(item) is list:
            for child in item:
                native(child)
        elif item is not None and type(item) not in (str, bool, int, float):
            raise ValueError("Bank/scaler chứa kiểu JSON không nguyên bản")
    native(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def content_hash(value: Any) -> str:
    """Băm nội dung xác định, không nhận self-seal thay xác minh nguồn."""
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def read_protocol(root: Path) -> dict[str, Any]:
    """Đọc đúng protocol đã khóa, không sửa split hoặc chi phí tại caller."""
    data = (root / "docs/plan/week11/mt_bicl_protocol.json").read_bytes()
    if hashlib.sha256(data).hexdigest() != PROTOCOL_SHA256:
        raise ValueError("Protocol MT-BICL khác khóa MT-BICL")
    protocol = json.loads(data)
    if (any(list(bounds) != protocol["splits"][key] for key, bounds in PARTITIONS.items())
            or protocol["features"]["columns"] != list(FEATURE_COLUMNS)
            or protocol["features"]["required_bars"] != REQUIRED_BARS
            or protocol["calendar"]["block_sessions"] != 63 or protocol["calendar"]["step"] != 3
            or protocol["economic_contract"]["fee_each_side"] != 0.0025
            or protocol["economic_contract"]["slippage_each_side"] != 0.001):
        raise ValueError("Hằng số bank khác protocol đã khóa")
    return protocol


def partition(value: str) -> str | None:
    """Phân loại bằng ngày, không dùng nhãn hoặc các thống kê outcome."""
    return next((key for key, (start, end) in PARTITIONS.items() if start <= value <= end), None)


def calendar_prefix(calendar: pd.DatetimeIndex, end_date: str) -> pd.DatetimeIndex:
    """Cắt lịch trước kiểm thứ tự và giữ neo toàn cục 02/01/2018."""
    cutoff = pd.Timestamp(day(end_date))
    if end_date > BANK_END:
        raise ValueError("Bank W10-03 chưa được phép sinh nhãn sau 2022")
    dates = pd.DatetimeIndex(calendar)
    if dates.hasnans or dates.tz is not None:
        raise ValueError("Lịch có ngày thiếu hoặc múi giờ")
    dates = dates[dates <= cutoff]
    if (len(dates) < 24 or dates[0] != pd.Timestamp("2018-01-02")
            or not dates.is_monotonic_increasing or dates.has_duplicates
            or not dates.equals(dates.normalize())):
        raise ValueError("Lịch không đúng neo/ngày phiên duy nhất tăng dần")
    return dates


def _visible_prices(frame: pd.DataFrame, calendar: pd.DatetimeIndex) -> pd.DataFrame:
    """Bỏ nến sau cutoff trước kiểm OHLC; không điền phiên nguồn bị thiếu."""
    if frame.columns.has_duplicates or not {*PRICE_COLUMNS, "Reference"}.issubset(frame.columns):
        raise ValueError("Nguồn bank thiếu OHLCV/Reference hoặc trùng cột")
    dates = pd.DatetimeIndex(pd.to_datetime(frame["Datetime"], errors="raise"))
    if dates.hasnans or dates.tz is not None:
        raise ValueError("Ngày nguồn giá thiếu hoặc có múi giờ")
    result = frame.loc[dates <= calendar[-1], [*PRICE_COLUMNS, "Reference"]].copy()
    result["Datetime"] = pd.to_datetime(result["Datetime"])
    if not result.empty:
        validate_raw_frame(result)
        reference = result["Reference"].to_numpy(dtype=float)
        if not np.isfinite(reference).all() or (reference <= 0).any():
            raise ValueError("Reference không dương hoặc không hữu hạn")
        if len(pd.DatetimeIndex(result["Datetime"]).difference(calendar)):
            raise ValueError("Giá có ngày không thuộc lịch VNINDEX")
    return result


def _visible_events(events: list[dict[str, Any]], cutoff: pd.Timestamp) -> list[dict[str, str]]:
    """Chuẩn hóa ngày quyền, chỉ giữ phần có ngày không sau cutoff của bank."""
    if type(events) is not list or any(type(item) is not dict for item in events):
        raise ValueError("Events phải là danh sách object")
    values = [item["exrightDate"] for item in events if item.get("exrightDate") not in (None, "")]
    dates = pd.DatetimeIndex(pd.to_datetime(values, format="mixed", errors="raise"))
    if dates.hasnans or dates.tz is not None or not dates.equals(dates.normalize()):
        raise ValueError("Ngày quyền không phải ngày phiên chuẩn")
    return [{"exrightDate": value} for value in dates[dates <= cutoff].strftime("%Y-%m-%d").tolist()]


def batch_features(frame: pd.DataFrame, events: list[dict[str, str]], calendar: pd.DatetimeIndex,
                   indices: np.ndarray) -> tuple[list[dict[str, Any]], pd.DatetimeIndex]:
    """Tính bốn primitive trên sliding windows; chỉ vòng lặp khi tạo JSON coverage.

    Cửa sổ 21 phiên, ddof=0 và MA của 20 Close cuối giữ đúng primitive hiện hữu.
    Nhãn/giá thực thi không tham gia phép tính hoặc eligibility của feature.
    """
    aligned = frame.set_index("Datetime").reindex(calendar)
    present = calendar.isin(pd.DatetimeIndex(frame["Datetime"]))
    close = aligned["Close"].to_numpy(dtype=float)
    windows = sliding_window_view(close, REQUIRED_BARS)[indices - 20]
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        returns = np.log(windows[:, 1:] / windows[:, :-1])
        vectors = np.column_stack((windows[:, -1] / windows[:, -6] - 1,
                                   windows[:, -1] / windows[:, 0] - 1,
                                   np.std(returns, axis=1, ddof=0),
                                   windows[:, -1] / np.mean(windows[:, 1:], axis=1) - 1))
    available = sliding_window_view(present, REQUIRED_BARS)[indices - 20]
    volume = aligned["Volume"].to_numpy(dtype=float)
    zero_volume = sliding_window_view(volume == 0, REQUIRED_BARS)[indices - 20].sum(axis=1)
    barriers = (corporate_action_barriers(frame, events) if not frame.empty
                else pd.DatetimeIndex([item["exrightDate"] for item in events]))
    first = calendar.get_indexer([frame["Datetime"].iloc[0]])[0] if not frame.empty else len(calendar)
    result = []
    for slot, index in enumerate(indices.tolist()):
        expected = calendar[index-20:index+1]
        mask = available[slot]
        missing = expected[~mask]
        leading = missing[missing < calendar[first]] if first < len(calendar) else missing
        middle = missing.difference(leading).difference(pd.DatetimeIndex([calendar[index]]))
        blocked = barriers[(barriers > expected[0]) & (barriers <= calendar[index])]
        reasons = []
        if len(leading):
            reasons.append("INSUFFICIENT_HISTORY")
        if not present[index]:
            reasons.append("MISSING_CUTOFF")
        if len(middle):
            reasons.append("MISSING_SESSION")
        if len(blocked):
            reasons.append("CORPORATE_ACTION_WINDOW")
        if not reasons and not np.isfinite(vectors[slot]).all():
            raise ValueError("Feature vector không hữu hạn")
        visible = expected[mask]
        start, end = ((str(visible[0].date()), str(visible[-1].date())) if len(visible) else (None, None))
        result.append({
            "feature_version": FEATURE_VERSION, "price_policy_version": PRICE_POLICY_VERSION,
            "feature_columns": list(FEATURE_COLUMNS), "as_of_date": str(calendar[index].date()),
            "feature_end_date": end, "status": "UNAVAILABLE" if reasons else "AVAILABLE",
            "reasons": reasons, "vector": None if reasons else vectors[slot].tolist(), "source": dict(SOURCE),
            "coverage": {"required_bars": 21, "expected_bars": 21, "available_bars": int(mask.sum()),
                         "start_date": start, "end_date": end, "missing_sessions": missing.strftime("%Y-%m-%d").tolist(),
                         "barrier_dates": blocked.strftime("%Y-%m-%d").tolist(), "zero_volume_count": int(zero_volume[slot])},
        })
    return result, barriers


def build_symbol_records(symbol: str, frame: pd.DataFrame, events: list[dict[str, Any]],
                         calendar: pd.DatetimeIndex) -> list[dict[str, Any]]:
    """Giữ lịch ứng viên và mọi reason; chỉ sinh nhãn qua helper engine scalar."""
    if symbol not in SYMBOLS:
        raise ValueError("Mã không thuộc protocol")
    calendar = calendar_prefix(calendar, BANK_END)
    frame = _visible_prices(frame, calendar)
    events = _visible_events(events, calendar[-1])
    indices = np.arange(20, len(calendar)-3, 3)
    features, barriers = batch_features(frame, events, calendar, indices)
    aligned = frame.set_index("Datetime").reindex(calendar)
    present = calendar.isin(pd.DatetimeIndex(frame["Datetime"]))
    entry, exits = indices+1, indices+3
    holding = np.stack((entry, entry+1, exits), axis=1)
    holding_missing = ~present[holding].all(axis=1)
    no_volume = (aligned["Volume"].to_numpy(dtype=float)[holding] == 0).any(axis=1)
    crossed = (np.searchsorted(barriers, calendar[exits], side="right")
               - np.searchsorted(barriers, calendar[entry], side="right")) > 0
    crossed_block = indices//63 != exits//63
    days = calendar.strftime("%Y-%m-%d").tolist()
    query_split = [partition(days[i]) for i in indices]
    exit_split = [partition(days[i]) for i in exits]
    crossed_split = np.asarray([q != e or q is None for q, e in zip(query_split, exit_split)])
    label_ok = ~(holding_missing | no_volume | crossed | crossed_block | crossed_split)
    open_values = aligned["Open"].to_numpy(dtype=float)[entry]
    close_values = aligned["Close"].to_numpy(dtype=float)[exits]
    net = np.full(len(indices), np.nan)
    # Helper hiện hữu chỉ nhận scalar; ufunc object gọi đúng helper cho mỗi cặp hợp lệ.
    economic = np.frompyfunc(partial(compute_round_trip_net_return, fee=0.0025, slippage=0.001), 2, 1)
    if label_ok.any():
        net[label_ok] = economic(open_values[label_ok], close_values[label_ok]).astype(float)
    records = []
    for slot, index in enumerate(indices.tolist()):
        label_reasons = []
        for condition, reason in ((holding_missing[slot], "MISSING_EXECUTION_SESSION"),
                                  (no_volume[slot], "NO_MATCHED_VOLUME_AT_EXECUTION"),
                                  (crossed[slot], "CORPORATE_ACTION_DURING_HOLDING"),
                                  (crossed_block[slot], "CROSS_BLOCK_HOLDING"),
                                  (crossed_split[slot], "PURGED_SPLIT_BOUNDARY")):
            if condition:
                label_reasons.append(reason)
        reasons = [*features[slot]["reasons"], *label_reasons]
        block = index//63
        records.append({
            "episode_id": f"{symbol}-{days[index]}", "symbol": symbol, "as_of_date": days[index],
            "entry_date": days[index+1], "exit_date": days[index+3], "calendar_index": index,
            "task_id": f"{symbol}:block{block:04d}", "block_index": block,
            "block_start_date": days[block*63], "block_start_calendar_index": block*63,
            "block_end_calendar_index": (block+1)*63-1,
            "query_split": query_split[slot], "split": None if crossed_split[slot] else query_split[slot],
            "status": "EXCLUDED" if reasons else "AVAILABLE", "reasons": reasons,
            "features": features[slot], "label_status": "UNAVAILABLE" if label_reasons else "AVAILABLE",
            "label_reasons": label_reasons,
            "outcome": None if label_reasons else {"entry_open": float(open_values[slot]),
                "exit_close": float(close_values[slot]), "r_net": float(net[slot]), "y": int(net[slot] > 0)},
        })
    return records


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Báo support thật và các nhóm loại có thể giao nhau, không đếm thành accuracy."""
    groups = {}
    failures = []
    for symbol in SYMBOLS:
        group = [row for row in records if row["symbol"] == symbol]
        by_split = {}
        for split in PARTITIONS:
            rows = [row for row in group if row["query_split"] == split]
            valid = [row for row in rows if row["status"] == "AVAILABLE"]
            blocks = Counter(row["task_id"] for row in valid)
            by_split[split] = {"candidates": len(rows), "available": len(valid),
                "excluded": len(rows)-len(valid), "blocks_with_two_cycles": sum(n >= 2 for n in blocks.values()),
                "reasons": dict(sorted(Counter(r for row in rows for r in row["reasons"]).items()))}
        if (by_split["train"]["available"] < 100 or by_split["train"]["blocks_with_two_cycles"] < 4
                or by_split["checkpoint_selection"]["available"] < 40):
            failures.append(symbol)
        groups[symbol] = by_split
    return {"symbols": groups, "candidates": len(records),
            "available": sum(row["status"] == "AVAILABLE" for row in records),
            "minimum_support_status": "STOP_INSUFFICIENT_TRAIN_SUPPORT" if failures else "PASS",
            "minimum_support_failed_symbols": failures,
            "regime_status": "DEFERRED_TO_TASK_BUILDER_NO_HMM_FIT", "training_allowed": False}


def build_dense_bank(prices: dict[str, tuple[pd.DataFrame, list[dict[str, Any]]]],
                     calendar: pd.DatetimeIndex, *, end_date: str = BANK_END) -> dict[str, Any]:
    """Dựng bank 2018–2022; provenance file phải được caller xác minh trước."""
    if type(prices) is not dict or set(prices) != set(SYMBOLS):
        raise ValueError("Bank phải có đủ bốn mã protocol")
    dates = calendar_prefix(calendar, end_date)
    records = [row for symbol in SYMBOLS for row in build_symbol_records(symbol, *prices[symbol], dates)]
    records.sort(key=lambda row: (row["as_of_date"], SYMBOLS.index(row["symbol"])))
    result = {"bank_version": BANK_VERSION, "protocol_sha256": PROTOCOL_SHA256,
              "end_date": end_date, "calendar": dates.strftime("%Y-%m-%d").tolist(),
              "feature_columns": list(FEATURE_COLUMNS), "source": dict(SOURCE),
              "records": records, "summary": summarize(records)}
    canonical_bytes(result)
    return result
