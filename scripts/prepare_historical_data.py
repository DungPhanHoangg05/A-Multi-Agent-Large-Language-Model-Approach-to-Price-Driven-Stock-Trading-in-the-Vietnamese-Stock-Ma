"""Tải và kiểm tra dữ liệu EOD dùng cho nghiên cứu theo kế hoạch tuần đầu."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


SYMBOLS = ("VNINDEX", "FPT", "VNM", "VCB", "MWG")
COLUMNS = ("Datetime", "Open", "High", "Low", "Close", "Volume")
START = "2018-01-01"
END = "2025-12-31"


def clean_ohlcv(raw: pd.DataFrame, symbol: str, start: str, end: str) -> pd.DataFrame:
    """Chuẩn hóa OHLCV; dữ liệu sai phải báo lỗi thay vì sửa hoặc điền nến."""
    if not isinstance(raw, pd.DataFrame) or raw.empty:
        raise ValueError(f"{symbol}: nguồn dữ liệu trống")
    renamed = raw.rename(columns={
        "time": "Datetime", "open": "Open", "high": "High",
        "low": "Low", "close": "Close", "volume": "Volume",
    })
    missing = set(COLUMNS) - set(renamed.columns)
    if missing:
        raise ValueError(f"{symbol}: thiếu cột {sorted(missing)}")
    frame = renamed.loc[:, COLUMNS].copy()
    frame["Datetime"] = pd.to_datetime(frame["Datetime"], errors="coerce")
    if frame["Datetime"].isna().any():
        raise ValueError(f"{symbol}: ngày giao dịch không hợp lệ")
    if frame["Datetime"].dt.tz is not None:
        frame["Datetime"] = frame["Datetime"].dt.tz_localize(None)
    frame["Datetime"] = frame["Datetime"].dt.normalize()
    frame = frame.loc[frame["Datetime"].between(start, end)].copy()
    if frame.empty:
        raise ValueError(f"{symbol}: không có nến trong giai đoạn yêu cầu")
    if frame["Datetime"].duplicated().any():
        raise ValueError(f"{symbol}: trùng ngày giao dịch")
    numeric = list(COLUMNS[1:])
    frame[numeric] = frame[numeric].apply(pd.to_numeric, errors="coerce")
    if not np.isfinite(frame[numeric].to_numpy(dtype=float)).all():
        raise ValueError(f"{symbol}: OHLCV có giá trị thiếu hoặc không hữu hạn")
    prices = frame[["Open", "High", "Low", "Close"]]
    if (prices <= 0).any().any() or (frame["Volume"] < 0).any():
        raise ValueError(f"{symbol}: giá hoặc khối lượng không hợp lệ")
    if (
        (frame["High"] < prices[["Open", "Low", "Close"]].max(axis=1)).any()
        or (frame["Low"] > prices[["Open", "High", "Close"]].min(axis=1)).any()
    ):
        raise ValueError(f"{symbol}: OHLC không nhất quán")
    return frame.sort_values("Datetime").reset_index(drop=True)


def validate_calendar(frames: dict[str, pd.DataFrame]) -> None:
    """So ngày của bốn cổ phiếu với lịch phiên của VN-Index."""
    reference = pd.DatetimeIndex(frames["VNINDEX"]["Datetime"])
    for symbol in SYMBOLS[1:]:
        dates = pd.DatetimeIndex(frames[symbol]["Datetime"])
        missing = reference.difference(dates)
        extra = dates.difference(reference)
        if len(missing) or len(extra):
            raise ValueError(
                f"{symbol}: lệch lịch VN-Index; thiếu {len(missing)} phiên, "
                f"thừa {len(extra)} phiên; ví dụ thiếu {missing[:5].strftime('%Y-%m-%d').tolist()}"
            )


def download_data(start: str, end: str, source: str) -> dict[str, pd.DataFrame]:
    """Lấy từng mã từ một nguồn được ghi rõ để tái lập bộ dữ liệu."""
    from vnstock.api.quote import Quote

    frames: dict[str, pd.DataFrame] = {}
    for symbol in SYMBOLS:
        raw = Quote(symbol=symbol, source=source).history(
            start=start, end=end, interval="1D"
        )
        frames[symbol] = clean_ohlcv(raw, symbol, start, end)
    validate_calendar(frames)
    return frames


def save_data(
    frames: dict[str, pd.DataFrame], output_dir: Path, source: str, start: str, end: str
) -> dict[str, Any]:
    """Ghi CSV và manifest kèm checksum sau khi toàn bộ mã đều hợp lệ."""
    import importlib.metadata

    output_dir.mkdir(parents=True, exist_ok=True)
    files: dict[str, dict[str, Any]] = {}
    for symbol, frame in frames.items():
        path = output_dir / f"{symbol}.csv"
        frame.to_csv(path, index=False, date_format="%Y-%m-%d", float_format="%.8f")
        files[symbol] = {
            "file": path.name,
            "rows": int(len(frame)),
            "first_date": frame["Datetime"].min().strftime("%Y-%m-%d"),
            "last_date": frame["Datetime"].max().strftime("%Y-%m-%d"),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    manifest: dict[str, Any] = {
        "source_library": "vnstock",
        "source_library_version": importlib.metadata.version("vnstock"),
        "source": source,
        "interval": "1D",
        "requested_start": start,
        "requested_end": end,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "price_unit": "nghìn VND/cổ phiếu đối với cổ phiếu; điểm đối với VNINDEX",
        "columns": list(COLUMNS),
        "files": files,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    """Điều phối tải dữ liệu EOD 2018–2025 và kiểm tra nhất quán."""
    parser = argparse.ArgumentParser(description="Chuẩn bị dữ liệu EOD nghiên cứu")
    parser.add_argument("--start", default=START)
    parser.add_argument("--end", default=END)
    parser.add_argument("--source", default="VCI")
    parser.add_argument("--output-dir", type=Path, default=Path("data/historical"))
    args = parser.parse_args()
    frames = download_data(args.start, args.end, args.source)
    manifest = save_data(frames, args.output_dir, args.source, args.start, args.end)
    for symbol, item in manifest["files"].items():
        print(f"{symbol}: {item['rows']} phiên, {item['first_date']} → {item['last_date']}")
    print(f"Đã ghi dữ liệu và manifest tại {args.output_dir}")


if __name__ == "__main__":
    main()
