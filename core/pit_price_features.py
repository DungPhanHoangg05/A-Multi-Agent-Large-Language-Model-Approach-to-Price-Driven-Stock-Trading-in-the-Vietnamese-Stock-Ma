"""Đặc trưng giá thô PIT dùng chung cho episode lịch sử và query."""

from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from core.execution_prices import PRICE_COLUMNS, corporate_action_barriers, validate_raw_frame


FEATURE_VERSION = "pit_price_features_v1"
PRICE_POLICY_VERSION = "raw_segment_21_v1"
FEATURE_COLUMNS = ("momentum_5", "momentum_20", "volatility_20", "ma_distance_20")
REQUIRED_BARS = 21
SOURCE_FIELDS = ("source_library", "primary_source", "price_basis", "price_unit")


def _daily_prefix(values: Any, cutoff: pd.Timestamp) -> pd.DatetimeIndex:
    """Cắt lịch/ngày nguồn trước kiểm thứ tự; không sắp xếp hoặc sửa ngày lỗi."""
    try:
        dates = pd.DatetimeIndex(pd.to_datetime(values, errors="raise"))
    except (TypeError, ValueError) as exc:
        raise ValueError("Ngày nguồn feature không hợp lệ") from exc
    if dates.hasnans or dates.tz is not None:
        raise ValueError("Ngày nguồn feature thiếu hoặc có múi giờ")
    visible = dates[dates <= cutoff]
    if (not visible.equals(visible.normalize()) or visible.has_duplicates
            or not visible.is_monotonic_increasing):
        raise ValueError("Ngày nguồn feature phải là phiên duy nhất, tăng dần")
    return visible


def extract_pit_price_features(
    frame: pd.DataFrame, events: list[dict[str, Any]],
    trading_calendar: pd.DatetimeIndex, as_of_date: str, *, source: dict[str, Any],
) -> dict[str, Any]:
    """Tính bốn feature trên 21 phiên đã biết; không nhận nhãn hoặc ngày thoát lệnh.

    Caller chịu trách nhiệm kiểm checksum và chứng cứ nguồn trước khi gọi hàm
    thuần này. Adapter production thực hiện việc đó qua bộ nguồn đã ghim.
    Đơn vị phải được loader chuẩn hóa sẵn; hàm không đổi đơn vị hoặc điền giá.
    Thiếu dữ liệu trả UNAVAILABLE; nguồn sai luôn ném ValueError.
    """
    try:
        if type(as_of_date) is not str or date.fromisoformat(as_of_date).isoformat() != as_of_date:
            raise ValueError("Cutoff feature phải có định dạng YYYY-MM-DD")
    except (TypeError, ValueError) as exc:
        raise ValueError("Cutoff feature phải là ngày ISO") from exc
    if (type(source) is not dict or any(type(source.get(key)) is not str for key in SOURCE_FIELDS)
            or source.get("source_library") != "vnstock"
            or source.get("primary_source") not in ("VCI", "KBS")
            or source.get("price_basis") != "UNADJUSTED_EXECUTION"
            or source.get("price_unit") != "thousand_VND"):
        raise ValueError("Nguồn feature phải là giá thô vnstock/VCI/KBS, nghìn VND")
    if (not isinstance(frame, pd.DataFrame) or frame.columns.has_duplicates
            or not {*PRICE_COLUMNS, "Reference"}.issubset(frame.columns)):
        raise ValueError("Nguồn feature thiếu OHLCV/Reference hoặc trùng cột")
    cutoff = pd.Timestamp(as_of_date)
    dates = _daily_prefix(frame["Datetime"], cutoff)
    calendar = _daily_prefix(trading_calendar, cutoff)
    visible = frame.loc[pd.to_datetime(frame["Datetime"], errors="raise") <= cutoff,
                        [*PRICE_COLUMNS, "Reference"]].copy()
    visible["Datetime"] = dates
    if not visible.empty:
        try:
            for column in (*PRICE_COLUMNS[1:], "Reference"):
                visible[column] = pd.to_numeric(visible[column], errors="raise")
            validate_raw_frame(visible)
        except (TypeError, ValueError) as exc:
            raise ValueError("Nguồn feature có OHLCV không hợp lệ") from exc
        reference = visible["Reference"].to_numpy(dtype=float)
        if not np.isfinite(reference).all() or (reference <= 0).any():
            raise ValueError("Nguồn feature có Reference không dương hoặc không hữu hạn")
    if len(dates.difference(calendar)):
        raise ValueError("Ngày giá không thuộc lịch phiên VNINDEX đã cung cấp")
    if type(events) is not list or any(type(event) is not dict for event in events):
        raise ValueError("Danh sách sự kiện quyền không hợp lệ")
    visible_events = []
    for event in events:
        if event.get("exrightDate") in (None, ""):
            continue
        event_day = _daily_prefix([event["exrightDate"]], pd.Timestamp.max.normalize())
        if event_day[0] <= cutoff:
            visible_events.append({"exrightDate": event_day[0].strftime("%Y-%m-%d")})

    expected = calendar[-REQUIRED_BARS:]
    window = visible.loc[visible["Datetime"].isin(expected)]
    missing = expected.difference(dates)
    leading = missing[missing < dates[0]] if len(dates) else missing
    middle = missing.difference(leading).difference(pd.DatetimeIndex([cutoff]))
    reasons = []
    if len(expected) < REQUIRED_BARS or len(leading):
        reasons.append("INSUFFICIENT_HISTORY")
    if cutoff not in dates or cutoff not in calendar:
        reasons.append("MISSING_CUTOFF")
    if len(middle):
        reasons.append("MISSING_SESSION")
    barriers = (corporate_action_barriers(visible, visible_events) if len(visible)
                else pd.DatetimeIndex([event["exrightDate"] for event in visible_events]))
    blocked = barriers[(barriers > expected[0]) & (barriers <= cutoff)] if len(expected) else barriers[:0]
    if len(blocked):
        reasons.append("CORPORATE_ACTION_WINDOW")
    end = None if window.empty else window["Datetime"].iloc[-1].strftime("%Y-%m-%d")
    result = {
        "feature_version": FEATURE_VERSION, "price_policy_version": PRICE_POLICY_VERSION,
        "feature_columns": list(FEATURE_COLUMNS), "as_of_date": as_of_date,
        "feature_end_date": end, "status": "UNAVAILABLE" if reasons else "AVAILABLE",
        "reasons": reasons, "vector": None,
        "source": {key: source[key] for key in SOURCE_FIELDS},
        "coverage": {
            "required_bars": REQUIRED_BARS, "expected_bars": int(len(expected)),
            "available_bars": int(len(window)),
            "start_date": None if window.empty else window["Datetime"].iloc[0].strftime("%Y-%m-%d"),
            "end_date": end, "missing_sessions": missing.strftime("%Y-%m-%d").tolist(),
            "barrier_dates": blocked.strftime("%Y-%m-%d").tolist(),
            "zero_volume_count": int(window["Volume"].eq(0).sum()),
        },
    }
    if reasons:
        return result
    close = window["Close"].to_numpy(dtype=float)
    # Mỗi phép toán chạy trên toàn vector, không duyệt từng nến DataFrame.
    with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
        returns = np.log(close[1:] / close[:-1])
        mean_close = np.mean(close[1:])
        vector = np.array([close[-1] / close[-6] - 1, close[-1] / close[0] - 1,
                           np.std(returns, ddof=0), close[-1] / mean_close - 1])
    if not np.isfinite(mean_close) or not np.isfinite(vector).all():
        raise ValueError("Kết quả feature không hữu hạn")
    result["vector"] = [float(value) for value in vector]
    return result
