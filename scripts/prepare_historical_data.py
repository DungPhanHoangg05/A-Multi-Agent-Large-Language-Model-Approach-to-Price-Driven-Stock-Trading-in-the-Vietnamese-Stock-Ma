"""Tải và kiểm tra dữ liệu EOD dùng cho nghiên cứu theo kế hoạch tuần đầu."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.realtime_loader import DATA_SOURCES, _fetch_from_vnstock


SYMBOLS = ("VNINDEX", "FPT", "VNM", "VCB", "MWG")
COLUMNS = ("Datetime", "Open", "High", "Low", "Close", "Volume")
START = "2018-01-01"
END = "2025-12-31"


def _invalid_ohlc(frame: pd.DataFrame) -> pd.Series:
    """Tìm nến có giá mở/đóng nằm ngoài biên cao/thấp."""
    prices = frame[["Open", "High", "Low", "Close"]]
    return (
        (frame["High"] < prices[["Open", "Low", "Close"]].max(axis=1))
        | (frame["Low"] > prices[["Open", "High", "Close"]].min(axis=1))
    )


def clean_ohlcv(
    raw: pd.DataFrame, symbol: str, start: str, end: str, *, check_ohlc: bool = True
) -> pd.DataFrame:
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
    if check_ohlc and _invalid_ohlc(frame).any():
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


def download_data(start: str, end: str) -> tuple[dict[str, pd.DataFrame], list[dict[str, Any]]]:
    """Lấy VCI, thay nguyên nến lỗi bằng KBS và lưu dấu vết từng thay đổi."""
    frames: dict[str, pd.DataFrame] = {}
    corrections: list[dict[str, Any]] = []
    for symbol in SYMBOLS:
        raw = _fetch_from_vnstock(symbol, start, end, "1D", "VCI")
        frame = clean_ohlcv(raw, symbol, start, end, check_ohlc=False)
        invalid = _invalid_ohlc(frame)
        if invalid.any():
            fallback_raw = _fetch_from_vnstock(symbol, start, end, "1D", "KBS")
            fallback = clean_ohlcv(
                fallback_raw, symbol, start, end, check_ohlc=False
            ).set_index("Datetime")
            for date in frame.loc[invalid, "Datetime"]:
                if date not in fallback.index:
                    raise ValueError(f"{symbol}: KBS thiếu nến đối chiếu {date.date()}")
                replacement = fallback.loc[date]
                if _invalid_ohlc(replacement.to_frame().T).any():
                    raise ValueError(f"{symbol}: KBS cũng sai OHLC ngày {date.date()}")
                original = frame.loc[frame["Datetime"].eq(date), list(COLUMNS[1:])].iloc[0]
                frame.loc[frame["Datetime"].eq(date), list(COLUMNS[1:])] = replacement[list(COLUMNS[1:])].to_numpy()
                corrections.append({
                    "symbol": symbol,
                    "date": date.strftime("%Y-%m-%d"),
                    "original_source": "VCI",
                    "replacement_source": "KBS",
                    "original": {key: float(original[key]) for key in COLUMNS[1:]},
                    "replacement": {key: float(replacement[key]) for key in COLUMNS[1:]},
                })
        frames[symbol] = clean_ohlcv(
            frame, symbol, start, end
        )
    validate_calendar(frames)
    return frames, corrections


def save_data(
    frames: dict[str, pd.DataFrame], corrections: list[dict[str, Any]],
    output_dir: Path, start: str, end: str
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
        "sources": list(DATA_SOURCES),
        "primary_source": "VCI",
        "corrections": corrections,
        "interval": "1D",
        "requested_start": start,
        "requested_end": end,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "price_unit": "nghìn VND/cổ phiếu đối với cổ phiếu; điểm đối với VNINDEX",
        "corporate_action_basis": "Chưa xác minh giá thô và hệ số điều chỉnh tại từng thời điểm; chỉ dùng cho đặc trưng kỹ thuật trước khi kiểm toán nhãn kinh tế.",
        "columns": list(COLUMNS),
        "files": files,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def verify_saved_data(output_dir: Path) -> dict[str, Any]:
    """Kiểm tra lại CSV, checksum, lịch phiên và các dòng đã thay mà không gọi mạng."""
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    if set(manifest["files"]) != set(SYMBOLS):
        raise ValueError("Manifest không chứa đủ năm mã nghiên cứu")
    frames: dict[str, pd.DataFrame] = {}
    for symbol in SYMBOLS:
        info = manifest["files"][symbol]
        path = output_dir / info["file"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != info["sha256"]:
            raise ValueError(f"{symbol}: checksum không khớp")
        frame = clean_ohlcv(
            pd.read_csv(path), symbol,
            manifest["requested_start"], manifest["requested_end"],
        )
        if len(frame) != info["rows"]:
            raise ValueError(f"{symbol}: số phiên không khớp manifest")
        frames[symbol] = frame
    validate_calendar(frames)
    for correction in manifest["corrections"]:
        frame = frames[correction["symbol"]]
        rows = frame.loc[frame["Datetime"].eq(pd.Timestamp(correction["date"]))]
        if len(rows) != 1:
            raise ValueError("Thiếu ngày đã thay trong manifest")
        for column in COLUMNS[1:]:
            if not np.isclose(float(rows.iloc[0][column]), correction["replacement"][column]):
                raise ValueError("Giá trị thay không khớp manifest")
    return manifest


def main() -> None:
    """Điều phối tải dữ liệu EOD 2018–2025 và kiểm tra nhất quán."""
    parser = argparse.ArgumentParser(description="Chuẩn bị dữ liệu EOD nghiên cứu")
    parser.add_argument("--start", default=START)
    parser.add_argument("--end", default=END)
    parser.add_argument("--output-dir", type=Path, default=Path("data/historical"))
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.verify_only:
        manifest = verify_saved_data(args.output_dir)
        print(f"Đã kiểm tra {len(manifest['files'])} CSV và {len(manifest['corrections'])} dòng thay nguồn")
        return
    frames, corrections = download_data(args.start, args.end)
    manifest = save_data(frames, corrections, args.output_dir, args.start, args.end)
    for symbol, item in manifest["files"].items():
        print(f"{symbol}: {item['rows']} phiên, {item['first_date']} → {item['last_date']}")
    print(f"Đã ghi dữ liệu và manifest tại {args.output_dir}")


if __name__ == "__main__":
    main()
