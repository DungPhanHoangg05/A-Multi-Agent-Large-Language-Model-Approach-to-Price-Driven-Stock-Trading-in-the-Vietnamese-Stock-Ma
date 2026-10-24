"""Bổ sung giá VCI 2025 vào snapshot riêng, không sinh nhãn hoặc gọi LLM."""

from __future__ import annotations

import argparse
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from core.execution_prices import (
    RAW_FIELD_MAP, STOCK_SYMBOLS, build_verified_cycle_schedule,
    load_verified_execution_data, normalise_vci_execution_prices,
)
from scripts.verify_execution_price_gate import (
    BASE_URL, EVIDENCE_FIELDS, audit_event_samples, fetch_paginated,
    file_receipt, sample_event_dates, verify_bundle, write_json,
)

VERSION = "unified_execution_prices_2025_v1"
OUTPUT = ROOT / "outputs/bayesian_benchmark/unified_bic_v1/inputs/execution_prices_2025"
PARENT = ROOT / "data/execution_prices_oos"
PARENT_SHA = "bb70790062210ad983e5250dae650a3d355cad4d4ba57807411208a5ac9c00f4"
CALENDAR = ROOT / "data/historical/VNINDEX.csv"
CALENDAR_SHA = "971eec19f3f2b252b0810f551bbfd50c0c31a2c26957da0b9434b9b25e869a34"
SOURCE_FILES = (
    "scripts/prepare_unified_execution_prices.py", "scripts/verify_execution_price_gate.py",
    "core/execution_prices.py", "scripts/prepare_historical_data.py",
)


def sha(path: Path) -> str:
    """Băm byte artifact; không đổi manifest nguồn đã khóa."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> Any:
    """Đọc JSON và từ chối số không hữu hạn."""
    def reject(value: str) -> None:
        raise ValueError(f"JSON chứa số không hữu hạn: {value}")
    return json.loads(path.read_text("utf-8"), parse_constant=reject)


def code_hashes() -> dict[str, str]:
    """Ghim code LF của công cụ độc lập, không sửa dependency W9."""
    return {name: hashlib.sha256((ROOT / name).read_text("utf-8").encode()).hexdigest()
            for name in SOURCE_FILES}


def write_once(path: Path, content: bytes) -> None:
    """Giữ nguyên artifact đã có; cho resume đúng nội dung sau gián đoạn."""
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError(f"Artifact đã tồn tại nhưng khác byte: {path.name}")
        return
    pending = path.with_suffix(path.suffix + ".tmp")
    pending.write_bytes(content)
    pending.replace(path)


def compressed(value: Any) -> bytes:
    """Nén JSON xác định, chỉ chứa số hữu hạn."""
    return gzip.compress(json.dumps(value, ensure_ascii=False, allow_nan=False).encode(), mtime=0)


def sources() -> tuple[dict[str, Any], pd.Series]:
    """Kiểm toàn gate OOS và lịch gốc trước mọi lần tải hoặc verify."""
    if sha(PARENT / "manifest.json") != PARENT_SHA or sha(CALENDAR) != CALENDAR_SHA:
        raise ValueError("Nguồn gốc hoặc lịch đã thay checksum W9")
    parent = verify_bundle(PARENT, end="2024-12-31")
    days = pd.read_csv(CALENDAR, usecols=["Datetime"], parse_dates=["Datetime"]).Datetime
    if (days.isna().any() or not days.is_unique or not days.is_monotonic_increasing
            or int(days.dt.year.eq(2025).sum()) != 249):
        raise ValueError("Lịch tham chiếu không có đúng 249 phiên 2025")
    return parent, days


def assert_extension(prefix: pd.DataFrame, extension: pd.DataFrame, calendar: pd.Series) -> None:
    """Chỉ nối năm 2025, không lặp ngày hoặc sửa prefix giá cũ."""
    if (extension.empty or not extension.Datetime.dt.year.eq(2025).all()
            or extension.Datetime.iloc[0] <= prefix.Datetime.iloc[-1]):
        raise ValueError("Phần nối phải chỉ gồm phiên 2025 sau prefix đã khóa")
    combined = pd.concat([prefix, extension], ignore_index=True)
    if not combined.Datetime.equals(calendar.reset_index(drop=True)):
        raise ValueError("Lịch phần nối không khớp VNINDEX hoặc thiếu phiên")


def assert_prefix(frame: pd.DataFrame, prefix: pd.DataFrame) -> None:
    """Từ chối cả thay đổi giá cũ lẫn chèn thêm ngày vào prefix."""
    visible = frame.loc[frame.Datetime <= prefix.Datetime.iloc[-1]].reset_index(drop=True)
    try:
        pd.testing.assert_frame_equal(visible, prefix, check_dtype=False, rtol=0, atol=1e-8)
    except AssertionError as exc:
        raise ValueError("Snapshot mới sửa prefix giá W9") from exc


def quarter_coverage(frame: pd.DataFrame, events: list[dict[str, Any]]) -> dict[str, Any]:
    """Đếm eligibility trên lưới cố định, không chọn 128 điểm hoặc tính return."""
    start = int(np.flatnonzero(frame.Datetime.dt.year.eq(2025).to_numpy())[0])
    schedule = build_verified_cycle_schedule(frame, events, warmup=start + 1, step=3)
    schedule = schedule.loc[schedule.as_of_date.dt.year.eq(2025)].copy()
    same_quarter = schedule.as_of_date.dt.to_period("Q").eq(schedule.exit_date.dt.to_period("Q"))
    ready = schedule.eligible & same_quarter
    return {"is_execution_plan": False, "step_anchor": frame.Datetime.iloc[start].strftime("%Y-%m-%d"),
            "step_sessions": 3, "quarters": {str(q): {
                "closed_within_quarter": int((same_quarter & schedule.as_of_date.dt.quarter.eq(q)).sum()),
                "eligible": int((ready & schedule.as_of_date.dt.quarter.eq(q)).sum()),
            } for q in (1, 2, 3, 4)}, "eligible": int(ready.sum()), "selected_dates": None}


def verify_samples(symbol: str, records: list[dict[str, Any]], events: list[dict[str, Any]],
                   frame: pd.DataFrame, samples: list[dict[str, Any]]) -> None:
    """Tái tính mẫu quyền, raw/adjusted và prefix proof hoàn toàn offline."""
    expected = sample_event_dates(events, "2018-01-01", "2025-12-31")
    if len(samples) != 2 or {s["type"]: s["exright_date"] for s in samples} != expected:
        raise ValueError("Mẫu quyền chưa đủ hoặc khác ngày đã đăng ký")
    by_day = {r["tradingDate"][:10]: r for r in records}
    indexed = frame.set_index("Datetime")
    for sample in samples:
        day, previous = sample["exright_date"], sample["previous_date"]
        pos = pd.DatetimeIndex(frame.Datetime).get_loc(pd.Timestamp(day))
        if (sample["symbol"] != symbol or pos < 1
                or frame.Datetime.iloc[pos - 1].strftime("%Y-%m-%d") != previous
                or sample["raw_before"] != by_day[previous] or sample["raw_exright"] != by_day[day]
                or sample["raw_prefix_equals_extended"] is not True or not sample["prefix_request"]):
            raise ValueError("Mẫu raw/prefix khác evidence đã lưu")
        unique = {json.dumps({k: e.get(k) for k in (
            "eventCode", "eventTitleVi", "exrightDate", "valuePerShare", "exerciseRatio"
        )}, sort_keys=True, ensure_ascii=False): e for e in events
                  if str(e.get("exrightDate", ""))[:10] == day}.values()
        cash = sum(float(e.get("valuePerShare", 0) or 0) for e in unique if e.get("eventCode") == "DIV")
        stock = sum(float(e.get("exerciseRatio", 0) or 0) for e in unique
                    if "cổ tức bằng cổ phiếu" in e.get("eventTitleVi", "").lower()
                    or "cổ phiếu thưởng" in e.get("eventTitleVi", "").lower())
        theoretical = (float(by_day[previous]["closePrice"]) - cash) / (1 + stock)
        difference = abs(float(by_day[day]["referencePrice"]) - theoretical)
        if (not np.isclose(cash, sample["cash_dividend_vnd"], rtol=0, atol=1e-8)
                or not np.isclose(stock, sample["stock_dividend_ratio"], rtol=0, atol=1e-12)
                or not np.isclose(theoretical, sample["theoretical_reference_vnd"], rtol=0, atol=1e-8)
                or not np.isclose(difference, sample["reference_difference_vnd"], rtol=0, atol=1e-8)
                or difference > 100 or set(sample["quotes"]) != {"VCI", "KBS"}):
            raise ValueError("Công thức quyền/Reference hoặc hai nguồn đối chiếu không khớp")
        for quote in sample["quotes"].values():
            for label, date in (("before", previous), ("exright", day)):
                raw = indexed.loc[pd.Timestamp(date), ["Open", "High", "Low", "Close"]].to_numpy(dtype=float)
                prices = pd.Series(quote[label]).reindex(["Open", "High", "Low", "Close"]).to_numpy(dtype=float)
                ratios = prices / raw
                if (not np.isfinite(ratios).all() or not ((ratios > 0) & (ratios < 1)).all()
                        or ratios.max() - ratios.min() > .002):
                    raise ValueError("OHLC đối chiếu không phân biệt được raw/adjusted cùng đơn vị")


def initial_manifest(parent: dict[str, Any]) -> dict[str, Any]:
    """Giữ metadata loader giá hiện hữu, thêm identity cho nguồn 2025 riêng."""
    result = {key: deepcopy(value) for key, value in parent.items() if key not in ("files", "verified_at_utc")}
    result.update(manifest_version=VERSION, price_gate="PENDING", requested_end="2025-12-31", files={},
                  parent_manifest_sha256=PARENT_SHA, calendar_sha256=CALENDAR_SHA,
                  code_sha256=code_hashes(), is_execution_plan=False, confirmation_allowed=False)
    return result


def verify(output: Path = OUTPUT, *, allow_partial: bool = False) -> dict[str, Any]:
    """Kiểm source, evidence, prefix và mẫu; không tin mỗi cờ PASS/hash tự khai."""
    parent, calendar = sources()
    manifest = read(output / "manifest.json")
    expected = initial_manifest(parent)
    if (set(manifest) != set(expected) or any(manifest[k] != expected[k] for k in expected
                                            if k not in ("files", "price_gate"))
            or manifest["price_gate"] not in (("PASS", "PENDING") if allow_partial else ("PASS",))
            or not set(manifest["files"]) <= set(STOCK_SYMBOLS)):
        raise ValueError("Snapshot 2025 khác version, nguồn, code hoặc cơ sở giá")
    if not allow_partial and set(manifest["files"]) != set(STOCK_SYMBOLS):
        raise ValueError("Snapshot 2025 chưa đủ bốn mã")
    for symbol, item in manifest["files"].items():
        acquisition = item["acquisition"]
        if acquisition["file"] != f"{symbol}.acquired.json.gz" or file_receipt(output / acquisition["file"]) != acquisition:
            raise ValueError("Acquisition sai đường dẫn hoặc checksum")
        acquired = json.loads(gzip.decompress((output / acquisition["file"]).read_bytes()))
        extension = normalise_vci_execution_prices(acquired["records"], symbol, "2025-01-01", "2025-12-31")
        prefix, events = load_verified_execution_data(PARENT, symbol)
        assert_extension(prefix, extension, calendar)
        pages = acquired["pages"]
        if (not pages or sum(p["rows"] for p in pages) != len(extension)
                or any(p["total_elements"] != len(extension) for p in pages)):
            raise ValueError("Acquisition thiếu trang hoặc sai tổng số phiên")
        if item["status"] == "DOWNLOADED" and allow_partial:
            continue
        if item["status"] != "VERIFIED":
            raise ValueError("Mã giá chưa được kiểm đầy đủ")
        for kind in ("csv", "events", "evidence"):
            suffix = {"csv": ".csv", "events": ".events.json", "evidence": ".evidence.json.gz"}[kind]
            if item[kind]["file"] != symbol + suffix or file_receipt(output / item[kind]["file"]) != item[kind]:
                raise ValueError("Artifact sai đường dẫn hoặc checksum")
        raw = json.loads(gzip.decompress((output / item["evidence"]["file"]).read_bytes()))
        old = json.loads(gzip.decompress((PARENT / parent["files"][symbol]["evidence"]["file"]).read_bytes()))
        if raw["records"] != old["records"] + acquired["records"]:
            raise ValueError("Evidence tổng không đúng prefix W9 cộng acquisition 2025")
        frame = pd.read_csv(output / item["csv"]["file"], parse_dates=["Datetime"])
        reconstructed = normalise_vci_execution_prices(raw["records"], symbol, "2018-01-01", "2025-12-31")
        pd.testing.assert_frame_equal(frame, reconstructed, check_dtype=False, rtol=0, atol=1e-8)
        assert_prefix(frame, prefix)
        if ((output / item["events"]["file"]).read_bytes() !=
                (PARENT / parent["files"][symbol]["events"]["file"]).read_bytes()):
            raise ValueError("Lịch quyền khác nguồn đã kiểm W9")
        if not frame.Datetime.equals(calendar) or len(frame) != item["rows"]:
            raise ValueError("Lịch hoặc số nến tổng không khớp")
        verify_samples(symbol, raw["records"], events, frame, item["event_samples"])
        if item["coverage_2025"] != quarter_coverage(frame, events):
            raise ValueError("Eligibility 2025 khác dữ liệu giá/quyền")
        if not allow_partial:
            load_verified_execution_data(output, symbol)
    return manifest


def prepare(output: Path = OUTPUT) -> dict[str, Any]:
    """Tải 2025 có checkpoint từng mã; không ghi vào giá/manifest W9."""
    parent, calendar = sources()
    resolved = output.resolve()
    if any(resolved.is_relative_to((ROOT / base).resolve()) for base in ("data", "data_manager", "outputs/bayesian_benchmark/improvement_v1")):
        raise ValueError("Không được ghi snapshot mới vào nguồn legacy")
    if output.exists() and any(output.iterdir()) and not (output / "manifest.json").exists():
        raise ValueError("Thư mục có artifact nhưng thiếu manifest; không ghi đè")
    output.mkdir(parents=True, exist_ok=True)
    if (output / "manifest.json").exists():
        manifest = verify(output, allow_partial=True)
    else:
        manifest = initial_manifest(parent)
        write_json(output / "manifest.json", manifest)
    for symbol in STOCK_SYMBOLS:
        item = manifest["files"].get(symbol)
        if item is not None and item["status"] == "VERIFIED":
            print(f"{symbol}: giữ nguyên phần đã kiểm, không tải lại", flush=True)
            continue
        if item is None:
            records, pages = fetch_paginated(f"{BASE_URL}/company/{symbol}/price-history",
                                           {"fromDate": "20250101", "toDate": "20251231"})
            projected = [{key: row[key] for key in EVIDENCE_FIELDS if key in row} for row in records]
            acquired_path = output / f"{symbol}.acquired.json.gz"
            write_once(acquired_path, compressed({"pages": pages, "records": projected}))
            item = {"status": "DOWNLOADED", "acquisition": file_receipt(acquired_path)}
            manifest["files"][symbol] = item
            write_json(output / "manifest.json", manifest)
        acquired = json.loads(gzip.decompress((output / item["acquisition"]["file"]).read_bytes()))
        extension = normalise_vci_execution_prices(acquired["records"], symbol, "2025-01-01", "2025-12-31")
        prefix, events = load_verified_execution_data(PARENT, symbol)
        assert_extension(prefix, extension, calendar)
        frame = pd.concat([prefix, extension], ignore_index=True)
        original = json.loads(gzip.decompress((PARENT / parent["files"][symbol]["evidence"]["file"]).read_bytes()))
        records = original["records"] + acquired["records"]
        csv_path = output / f"{symbol}.csv"
        event_path = output / f"{symbol}.events.json"
        evidence_path = output / f"{symbol}.evidence.json.gz"
        write_once(csv_path, frame.to_csv(index=False, date_format="%Y-%m-%d", float_format="%.8f").encode())
        write_once(event_path, (PARENT / parent["files"][symbol]["events"]["file"]).read_bytes())
        write_once(evidence_path, compressed({"records": records, "extension_pages": acquired["pages"],
                                             "parent_evidence_sha256": parent["files"][symbol]["evidence"]["sha256"]}))
        samples = audit_event_samples(symbol, records, events, frame, start="2018-01-01", end="2025-12-31")
        verify_samples(symbol, records, events, frame, samples)
        item.update(status="VERIFIED", csv=file_receipt(csv_path), events=file_receipt(event_path),
                    evidence=file_receipt(evidence_path), rows=int(len(frame)),
                    event_samples=samples, coverage_2025=quarter_coverage(frame, events))
        write_json(output / "manifest.json", manifest)
        print(f"{symbol}: kiểm {len(extension)} phiên 2025, prefix W9 nguyên; không sinh nhãn", flush=True)
    verify(output, allow_partial=True)
    manifest["price_gate"] = "PASS"
    write_json(output / "manifest.json", manifest)
    try:
        return verify(output)
    except Exception:
        manifest["price_gate"] = "PENDING"
        write_json(output / "manifest.json", manifest)
        raise


def main() -> None:
    """Mặc định verify offline; --download tự tiếp tục phần đã lưu hợp lệ."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="Tải giá công khai và kiểm nguồn, không dùng API key")
    parser.add_argument("--verify-only", action="store_true", help="Tái kiểm snapshot đã có hoàn toàn offline")
    args = parser.parse_args()
    if args.download and args.verify_only:
        parser.error("Chọn tải hoặc verify offline")
    result = prepare() if args.download else verify()
    counts = {symbol: item["coverage_2025"]["eligible"] for symbol, item in result["files"].items()}
    print(f"Gate giá 2025 PASS: 4 mã × 249 phiên; pool metadata={counts}; chưa chọn lịch/nhãn hoặc phát hành xác nhận")


if __name__ == "__main__":
    main()
