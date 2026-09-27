"""Giá thực thi thô và rào chắn chu kỳ có quyền doanh nghiệp chưa mô hình hóa."""

from __future__ import annotations

import hashlib
import json
import gzip
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


STOCK_SYMBOLS = ("FPT", "VNM", "VCB", "MWG")
PRICE_COLUMNS = ("Datetime", "Open", "High", "Low", "Close", "Volume")
RAW_FIELD_MAP = {
    "tradingDate": "Datetime", "openPrice": "Open", "highestPrice": "High",
    "lowestPrice": "Low", "closePrice": "Close", "totalMatchVolume": "Volume",
    "referencePrice": "Reference", "matchPrice": "MatchPrice",
}


def validate_raw_frame(frame: pd.DataFrame) -> None:
    """Từ chối nến lỗi, ngày trùng, đơn vị không hữu hạn và thứ tự sai."""
    if frame.empty or not set(PRICE_COLUMNS).issubset(frame.columns):
        raise ValueError("Thiếu dữ liệu giá thô OHLCV")
    dates = pd.to_datetime(frame["Datetime"], errors="raise")
    if dates.isna().any() or dates.dt.tz is not None or not dates.eq(dates.dt.normalize()).all():
        raise ValueError("Ngày giá thô phải là ngày phiên không có múi giờ")
    if dates.duplicated().any() or not dates.is_monotonic_increasing:
        raise ValueError("Ngày giá thô trùng hoặc không tăng dần")
    values = frame.loc[:, PRICE_COLUMNS[1:]].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values[:, :4] <= 0).any():
        raise ValueError("Giá thô phải dương và hữu hạn")
    if (values[:, 4] < 0).any() or not np.equal(values[:, 4], np.floor(values[:, 4])).all():
        raise ValueError("Khối lượng khớp phải là số nguyên không âm")
    if (frame["High"] < frame[["Open", "Low", "Close"]].max(axis=1)).any() or (
        frame["Low"] > frame[["Open", "High", "Close"]].min(axis=1)
    ).any():
        raise ValueError("OHLC giá thô không nhất quán")


def normalise_vci_execution_prices(
    records: list[dict[str, Any]], symbol: str, start: str, end: str
) -> pd.DataFrame:
    """Chỉ chọn trường thô VCI; đổi VND sang nghìn VND đúng một lần."""
    source = pd.DataFrame(records)
    if symbol not in STOCK_SYMBOLS or not set(RAW_FIELD_MAP).union({"ticker"}).issubset(source.columns):
        raise ValueError("Thiếu trường giá thô VCI hoặc mã không được phép")
    if not source["ticker"].eq(symbol).all():
        raise ValueError("API trả lẫn mã cổ phiếu")
    frame = source.loc[:, list(RAW_FIELD_MAP)].rename(columns=RAW_FIELD_MAP).copy()
    frame["Datetime"] = pd.to_datetime(frame["Datetime"], errors="raise")
    if not frame["Datetime"].between(pd.Timestamp(start), pd.Timestamp(end)).all():
        raise ValueError("API giá thô trả ngày ngoài phạm vi yêu cầu")
    for column in (*PRICE_COLUMNS[1:5], "Reference", "MatchPrice"):
        frame[column] = pd.to_numeric(frame[column], errors="raise") / 1_000.0
    frame["Volume"] = pd.to_numeric(frame["Volume"], errors="raise")
    frame = frame.sort_values("Datetime").reset_index(drop=True)
    validate_raw_frame(frame)
    # Close là trường đóng cửa riêng; matchPrice của provider không luôn bằng Close.
    if not np.isfinite(frame[["Reference", "MatchPrice"]].to_numpy()).all() or (
        frame["Reference"] <= 0
    ).any() or (frame["MatchPrice"] < 0).any():
        raise ValueError("Giá tham chiếu hoặc giá khớp không hợp lệ")
    return frame


def raw_point_in_time_snapshot(frame: pd.DataFrame, as_of_date: str) -> pd.DataFrame:
    """Cắt trước kiểm tra giá và chỉ đưa OHLCV thô vào đầu vào của agent."""
    cutoff = pd.Timestamp(as_of_date)
    if pd.isna(cutoff) or cutoff.tz is not None or cutoff != cutoff.normalize():
        raise ValueError("as_of_date phải là ngày phiên")
    dates = pd.to_datetime(frame["Datetime"], errors="raise")
    visible = frame.loc[dates <= cutoff, PRICE_COLUMNS].copy()
    validate_raw_frame(visible)
    if visible["Datetime"].iloc[-1] != cutoff:
        raise ValueError("Thiếu nến tại as_of_date")
    return visible.reset_index(drop=True)


def corporate_action_barriers(frame: pd.DataFrame, events: list[dict[str, Any]]) -> pd.DatetimeIndex:
    """Gộp ngày quyền với mọi thay đổi Reference so với Close phiên trước."""
    validate_raw_frame(frame)
    reference = pd.to_numeric(frame["Reference"], errors="raise")
    if not np.isfinite(reference).all() or (reference <= 0).any():
        raise ValueError("Giá Reference không hợp lệ")
    gaps = reference.sub(frame["Close"].shift()).abs() > 0.00001
    event_dates = pd.to_datetime(
        [event["exrightDate"] for event in events if event.get("exrightDate")], errors="raise"
    )
    if event_dates.isna().any():
        raise ValueError("Ngày quyền không hợp lệ")
    return pd.DatetimeIndex(frame.loc[gaps, "Datetime"]).union(event_dates).sort_values()


def build_verified_cycle_schedule(
    frame: pd.DataFrame, events: list[dict[str, Any]], *, warmup: int = 600, step: int = 3
) -> pd.DataFrame:
    """Giữ lịch ứng viên; ghi rõ chu kỳ loại vì quyền, tuyệt đối không sinh nhãn."""
    validate_raw_frame(frame)
    if warmup < 1 or step < 3:
        raise ValueError("Warm-up phải dương và bước phải ít nhất ba phiên")
    starts = np.arange(warmup, len(frame) - 2, step)
    dates = frame["Datetime"].to_numpy(dtype="datetime64[ns]")
    barriers = corporate_action_barriers(frame, events).to_numpy(dtype="datetime64[ns]")
    entry, exit_dates = dates[starts], dates[starts + 2]
    # Mua ngay ngày không hưởng quyền không được nhận quyền đó; chỉ chặn (entry, exit].
    counts = np.searchsorted(barriers, exit_dates, side="right") - np.searchsorted(
        barriers, entry, side="right"
    )
    volumes = frame["Volume"].to_numpy(dtype=float)
    no_execution = (volumes[starts] <= 0) | (volumes[starts + 1] <= 0) | (volumes[starts + 2] <= 0)
    return pd.DataFrame({
        "as_of_date": pd.to_datetime(dates[starts - 1]),
        "entry_date": pd.to_datetime(entry), "exit_date": pd.to_datetime(exit_dates),
        "eligible": (counts == 0) & ~no_execution,
        "exclusion_reason": np.where(no_execution, "NO_MATCHED_VOLUME_AT_EXECUTION",
                                     np.where(counts > 0, "CORPORATE_ACTION_DURING_HOLDING", "")),
    })


def execution_prices_for_cycle(
    frame: pd.DataFrame, events: list[dict[str, Any]], as_of_date: str,
    entry_date: str, exit_date: str
) -> tuple[float, float]:
    """Xác nhận Open(t+1)/Close(t+3), từ chối quyền và sai lịch phiên."""
    requested = pd.to_datetime([as_of_date, entry_date, exit_date], errors="raise")
    frame = frame.loc[pd.to_datetime(frame["Datetime"], errors="raise") <= requested[2]].copy()
    validate_raw_frame(frame)
    dates = pd.DatetimeIndex(frame["Datetime"])
    positions = dates.get_indexer(requested)
    if (positions < 0).any() or positions[1] != positions[0] + 1 or positions[2] != positions[0] + 3:
        raise ValueError("Chu kỳ phải vào t+1 và thoát t+3 theo phiên")
    if (frame.iloc[positions[1]:positions[2] + 1]["Volume"] <= 0).any():
        raise ValueError("Khoảng nắm giữ có phiên không khớp lệnh để xác nhận giá thực thi")
    barriers = corporate_action_barriers(frame.iloc[:positions[2] + 1], events)
    if ((barriers > requested[1]) & (barriers <= requested[2])).any():
        raise ValueError("Chu kỳ có quyền doanh nghiệp chưa được engine mô hình hóa")
    return float(frame.iloc[positions[1]]["Open"]), float(frame.iloc[positions[2]]["Close"])


def load_verified_execution_data(output_dir: Path, symbol: str) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Nạp giá chỉ khi manifest qua gate và CSV/sự kiện còn đúng checksum."""
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    if (symbol not in STOCK_SYMBOLS or manifest.get("price_gate") != "PASS"
            or manifest.get("price_basis") != "UNADJUSTED_EXECUTION"
            or manifest.get("price_unit") != "thousand_VND"
            or manifest.get("primary_source") != "VCI"
            or set(manifest.get("files", {})) != set(STOCK_SYMBOLS)
            or manifest.get("raw_field_map") != RAW_FIELD_MAP):
        raise ValueError("Bộ giá chưa qua gate giá thực thi VCI")
    item = manifest["files"][symbol]
    for key in ("csv", "evidence", "events"):
        path = output_dir / item[key]["file"]
        if path.resolve().parent != output_dir.resolve() or hashlib.sha256(path.read_bytes()).hexdigest() != item[key]["sha256"]:
            raise ValueError("Checksum hoặc đường dẫn giá thực thi không hợp lệ")
    frame = pd.read_csv(output_dir / item["csv"]["file"], parse_dates=["Datetime"])
    validate_raw_frame(frame)
    if len(frame) != item["rows"]:
        raise ValueError("Số nến thực thi không khớp manifest")
    evidence = json.loads(gzip.decompress((output_dir / item["evidence"]["file"]).read_bytes()))
    reconstructed = normalise_vci_execution_prices(
        evidence["records"], symbol, manifest["requested_start"], manifest["requested_end"]
    )
    if not np.array_equal(frame["Datetime"].to_numpy(), reconstructed["Datetime"].to_numpy()) or not np.allclose(
        frame.drop(columns="Datetime").to_numpy(), reconstructed.drop(columns="Datetime").to_numpy(), rtol=0, atol=1e-8
    ):
        raise ValueError("CSV không khớp các trường thô trong evidence VCI")
    events = json.loads((output_dir / item["events"]["file"]).read_text(encoding="utf-8"))["records"]
    return frame, events
