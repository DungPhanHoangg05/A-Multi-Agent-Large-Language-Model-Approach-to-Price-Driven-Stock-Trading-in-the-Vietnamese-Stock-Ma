"""Kiểm nguồn giá và lịch revision riêng; không gọi LLM hoặc tính nhãn/payoff."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.execution_prices import (
    RAW_FIELD_MAP, STOCK_SYMBOLS, normalise_vci_execution_prices, raw_point_in_time_snapshot,
)
from core.historical_signals import digest, native_json
from core.oos_coverage import build_oos_calendar
from scripts.verify_execution_price_gate import (
    BASE_URL, EVIDENCE_FIELDS, audit_event_samples, fetch_paginated, file_receipt,
    verify_bundle, write_json,
)

NAMESPACE = "outputs/bayesian_benchmark/bic_icl_v2"
EXPOSURE = "docs/plan/week10/exposure_inventory_v1.json"
VERSION = "bic_icl_v2_input_audit_v1"
DEPENDENCIES = ("scripts/audit_bic_icl_inputs.py", "scripts/verify_execution_price_gate.py",
    "core/execution_prices.py", "core/oos_coverage.py", "core/historical_signals.py")


def checksum(path: Path) -> str:
    """Băm byte, không diễn giải nhãn hoặc thông tin tài khoản."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def namespace_path(path: Path, root: Path = ROOT) -> Path:
    """Chỉ cho ghi vào namespace revision; cấm ghi đè bằng chứng cũ."""
    resolved = path.resolve()
    if not resolved.is_relative_to((root / NAMESPACE).resolve()):
        raise ValueError("Đường dẫn phải thuộc namespace bic_icl_v2")
    return resolved


def source_path(directory: Path, receipt: dict[str, str]) -> Path:
    """Chặn traversal và nguồn đổi byte trước khi đọc nội dung."""
    name = receipt["file"]
    path = directory / name
    if Path(name).name != name or path.resolve().parent != directory.resolve() or checksum(path) != receipt["sha256"]:
        raise ValueError("Checksum hoặc đường dẫn nguồn không hợp lệ")
    return path


def read_exposure(root: Path = ROOT) -> dict[str, Any]:
    """Giữ khai báo không xác minh được tách biệt với quyền thực hiện công việc."""
    value = json.loads((root / EXPOSURE).read_text(encoding="utf-8"))
    if (value.get("version") != "bic_icl_v2_exposure_inventory_v1"
            or value.get("status") != "UNVERIFIED" or value.get("confirmation_allowed") is not False
            or value.get("reason") != "PARTICIPANT_CANNOT_VERIFY_PRIOR_EXPOSURE"
            or not all(type(value.get(k)) is str and value[k] for k in
                       ("date", "participant_declaration", "execution_authorization", "interpretation"))):
        raise ValueError("Khai báo exposure không được tự chuyển thành bằng chứng chưa xem")
    return value


def design_calendar(frames: dict[str, pd.DataFrame], events: dict[str, list[dict[str, Any]]],
                    vnindex: pd.DataFrame) -> dict[str, Any]:
    """Chọn tám ngày/quý trên lưới neo đầu năm, chỉ dùng lịch và eligibility.

    Cắt phần sau 2025 trước kiểm tra nguồn; ngày sau cutoff chỉ dùng kiểm
    khả năng thực thi, tuyệt đối không tạo nhãn hoặc xếp hạng bằng payoff.
    """
    if set(frames) != set(STOCK_SYMBOLS) or set(events) != set(STOCK_SYMBOLS):
        raise ValueError("Lịch cần đủ bốn mã")
    index = vnindex.loc[pd.to_datetime(vnindex.Datetime) <= "2025-12-31"].copy()
    dates = pd.DatetimeIndex(index.Datetime)
    grid = set(dates[dates.year == 2025][::3].strftime("%Y-%m-%d"))
    stocks, selected, shortfalls = {}, {}, []
    for symbol in STOCK_SYMBOLS:
        frame = frames[symbol].loc[pd.to_datetime(frames[symbol].Datetime) <= "2025-12-31"].copy()
        visible_events = [e for e in events[symbol] if e.get("exrightDate", "")[:10] <= "2025-12-31"]
        rows = build_oos_calendar(frame, visible_events, index, start="2025-01-01", end="2025-12-31")
        for row in rows:
            reasons = list(row["reasons"])
            if row["exit_date"] and pd.Timestamp(row["exit_date"]).quarter != pd.Timestamp(row["as_of_date"]).quarter:
                reasons.append("CROSS_QUARTER_EXECUTION")
            if row["as_of_date"] not in grid:
                reasons.append("OFF_STEP3_GRID")
            row.update(eligible=not reasons, reasons=reasons, reason=reasons[0] if reasons else None)
        quarters, chosen = {}, []
        for quarter in range(1, 5):
            pool = [r for r in rows if r["eligible"] and r["quarter"] == f"2025Q{quarter}"]
            # Không giảm mục tiêu hoặc đánh lại phase khi loại quyền/thiếu giá.
            days = [pool[j * (len(pool) - 1) // 7]["as_of_date"] for j in range(8)] if len(pool) >= 8 else []
            quarters[f"2025Q{quarter}"] = {"eligible_pool": len(pool), "selected": days, "target": 8}
            if len(pool) < 8:
                shortfalls.append(f"{symbol}:2025Q{quarter}")
            chosen.extend(days)
        by_day = {row["as_of_date"]: row for row in rows}
        for day in chosen:
            # Xác nhận mỗi prefix được cắt tại query, không đọc giá t+1/t+3 để chọn.
            snapshot = raw_point_in_time_snapshot(frame, day)
            if snapshot.Datetime.max() != pd.Timestamp(day):
                raise ValueError("Snapshot không dừng đúng cutoff")
        selected[symbol] = [{key: by_day[d][key] for key in ("as_of_date", "entry_date", "exit_date", "quarter")}
                            for d in chosen]
        stocks[symbol] = {"quarters": quarters, "calendar": rows,
            "excluded_by_primary_reason": dict(sorted(Counter(r["reason"] for r in rows if not r["eligible"]).items()))}
    return native_json({"status": "BLOCKED" if shortfalls else "PASS", "shortfalls": shortfalls,
        "is_execution_plan": False, "selection_uses_outcome": False,
        "anchor": min(grid) if grid else None, "step_sessions": 3, "points_per_symbol_quarter": 8,
        "rank_rule": "floor(j*(N-1)/7), j=0..7", "replacement_after_failure": False,
        "stocks": stocks, "selected": selected, "selected_count": sum(map(len, selected.values()))})


def verify_samples(symbol: str, item: dict[str, Any], records: list[dict[str, Any]],
                   frame: pd.DataFrame, events: list[dict[str, Any]]) -> None:
    """Tái kiểm hai mẫu quyền từ trường thô, công thức Reference và đối chiếu VCI/KBS."""
    samples = item["event_samples"]
    if len(samples) != 2 or {s["type"] for s in samples} != {"stock_dividend", "cash_dividend"}:
        raise ValueError("Thiếu hai loại mẫu quyền")
    by_day = {r["tradingDate"][:10]: r for r in records}
    indexed = frame.set_index("Datetime")
    for sample in samples:
        day, before = sample["exright_date"], sample["previous_date"]
        same_day = {json.dumps({k: e.get(k) for k in ("eventCode", "eventTitleVi", "exrightDate",
            "valuePerShare", "exerciseRatio")}, sort_keys=True, ensure_ascii=False): e
            for e in events if e.get("exrightDate", "")[:10] == day}.values()
        cash = sum(float(e.get("valuePerShare", 0) or 0) for e in same_day if e.get("eventCode") == "DIV")
        ratio = sum(float(e.get("exerciseRatio", 0) or 0) for e in same_day
                    if "cổ tức bằng cổ phiếu" in e.get("eventTitleVi", "").lower()
                    or "cổ phiếu thưởng" in e.get("eventTitleVi", "").lower())
        theoretical = (by_day[before]["closePrice"] - cash) / (1 + ratio)
        difference = abs(by_day[day]["referencePrice"] - theoretical)
        if (sample["symbol"] != symbol or sample["raw_before"] != by_day[before]
                or sample["raw_exright"] != by_day[day] or sample["cash_dividend_vnd"] != cash
                or sample["stock_dividend_ratio"] != ratio or difference > 100
                or not np.isclose(sample["theoretical_reference_vnd"], theoretical, rtol=0, atol=1e-8)
                or not np.isclose(sample["reference_difference_vnd"], difference, rtol=0, atol=1e-8)
                or sample["raw_prefix_equals_extended"] is not True or not sample["prefix_request"]
                or set(sample["quotes"]) != {"VCI", "KBS"}
                or indexed.index.get_loc(pd.Timestamp(day)) != indexed.index.get_loc(pd.Timestamp(before)) + 1):
            raise ValueError("Mẫu quyền không khớp nguồn hoặc công thức")
        for quote in sample["quotes"].values():
            for label, date in (("before", before), ("exright", day)):
                raw = indexed.loc[pd.Timestamp(date), ["Open", "High", "Low", "Close"]].to_numpy(dtype=float)
                prices = np.array([quote[label][k] for k in ("Open", "High", "Low", "Close")], dtype=float)
                factors = prices / raw
                if not np.isfinite(factors).all() or not ((factors > 0) & (factors < 1)).all() or np.ptp(factors) > .002:
                    raise ValueError("Mẫu chưa phân biệt đúng giá thô và giá điều chỉnh")


def verify_prices(directory: Path, root: Path = ROOT, *, pending: bool = False
                  ) -> tuple[dict[str, Any], dict[str, pd.DataFrame], dict[str, list[dict[str, Any]]]]:
    """Tái dựng CSV từ evidence; chỉ chấp nhận snapshot riêng 2018–2025 đủ bốn mã."""
    namespace_path(directory, root)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    expected = {"price_basis": "UNADJUSTED_EXECUTION", "price_unit": "thousand_VND",
        "primary_source": "VCI", "crosscheck_sources": ["VCI", "KBS"], "raw_field_map": RAW_FIELD_MAP,
        "requested_start": "2018-01-01", "requested_end": "2025-12-31",
        "corporate_action_policy": "EXCLUDE_WHEN_ENTRY_LT_EXRIGHT_LE_EXIT",
        "signal_price_basis": "UNADJUSTED_PREFIX_NO_RETROACTIVE_ADJUSTMENTS"}
    if (any(manifest.get(k) != v for k, v in expected.items())
            or manifest.get("price_gate") not in (("PASS", "PENDING") if pending else ("PASS",))
            or set(manifest.get("files", {})) != set(STOCK_SYMBOLS)):
        raise ValueError("Manifest giá revision thiếu mã hoặc sai phạm vi/cơ sở")
    base_dir = root / "data/execution_prices_oos"
    base = verify_bundle(base_dir, start="2018-01-01", end="2024-12-31")
    if checksum(base_dir / "manifest.json") != manifest["base_manifest_sha256"]:
        raise ValueError("Nguồn giá cũ thay đổi")
    calendar_path = root / "data/historical/VNINDEX.csv"
    calendar_manifest = json.loads((calendar_path.parent / "manifest.json").read_text(encoding="utf-8"))
    if checksum(calendar_path) != manifest["calendar_sha256"] or checksum(calendar_path) != calendar_manifest["files"]["VNINDEX"]["sha256"]:
        raise ValueError("Lịch VNINDEX đổi nguồn")
    dates = pd.read_csv(calendar_path, usecols=["Datetime"], parse_dates=["Datetime"]).Datetime
    frames, events_by_symbol = {}, {}
    for symbol in STOCK_SYMBOLS:
        item = manifest["files"][symbol]
        paths = {kind: source_path(directory, item[kind]) for kind in ("csv", "evidence", "events")}
        evidence = json.loads(gzip.decompress(paths["evidence"].read_bytes()))
        frame = pd.read_csv(paths["csv"], parse_dates=["Datetime"])
        rebuilt = normalise_vci_execution_prices(evidence["records"], symbol, "2018-01-01", "2025-12-31")
        pd.testing.assert_frame_equal(frame, rebuilt, check_dtype=False, rtol=0, atol=1e-8)
        old = pd.read_csv(base_dir / base["files"][symbol]["csv"]["file"], parse_dates=["Datetime"])
        pd.testing.assert_frame_equal(frame.loc[frame.Datetime <= "2024-12-31"].reset_index(drop=True), old,
                                      check_dtype=False, rtol=0, atol=1e-8)
        if not frame.Datetime.equals(dates) or len(frame) != item["rows"]:
            raise ValueError("Giá revision không khớp lịch hoặc prefix nguồn cũ")
        event_envelope = json.loads(paths["events"].read_text(encoding="utf-8"))
        if paths["events"].read_bytes() != (base_dir / base["files"][symbol]["events"]["file"]).read_bytes():
            raise ValueError("Quyền revision phải dùng đúng evidence 2025 đã có")
        events = event_envelope["records"]
        verify_samples(symbol, item, evidence["records"], frame, events)
        frames[symbol], events_by_symbol[symbol] = frame, events
    return manifest, frames, events_by_symbol


def download_prices(directory: Path, root: Path = ROOT) -> None:
    """Nối giá 2025 vào snapshot mới; checkpoint theo mã, không sửa nguồn W9."""
    namespace_path(directory, root)
    manifest_path = directory / "manifest.json"
    if manifest_path.exists() and json.loads(manifest_path.read_text(encoding="utf-8")).get("price_gate") == "PASS":
        verify_prices(directory, root)
        print("Nguồn giá đã hoàn tất: xác minh offline, giữ nguyên byte và timestamp", flush=True)
        return
    base_dir = root / "data/execution_prices_oos"
    base = verify_bundle(base_dir, start="2018-01-01", end="2024-12-31")
    directory.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {
        **{k: base[k] for k in ("price_basis", "price_unit", "primary_source", "crosscheck_sources",
            "raw_field_map", "corporate_action_policy", "signal_price_basis", "source_library", "source_library_version")},
        "price_gate": "PENDING", "requested_start": "2018-01-01", "requested_end": "2025-12-31",
        "calendar_sha256": base["calendar_sha256"], "base_manifest_sha256": checksum(base_dir / "manifest.json"),
        "acquisition_method": "VERIFIED_PREFIX_2018_2024_PLUS_VCI_PUBLIC_RAW_2025", "files": {}}
    if (manifest["base_manifest_sha256"] != checksum(base_dir / "manifest.json")
            or manifest["calendar_sha256"] != checksum(root / "data/historical/VNINDEX.csv")):
        raise ValueError("Không resume với nguồn đã thay đổi")
    write_json(manifest_path, manifest)
    for symbol in STOCK_SYMBOLS:
        if symbol in manifest["files"]:
            for kind in ("csv", "evidence", "events"):
                source_path(directory, manifest["files"][symbol][kind])
            print(f"{symbol}: kiểm byte checkpoint đã có, không tải lại", flush=True)
            continue
        records, pages = fetch_paginated(f"{BASE_URL}/company/{symbol}/price-history",
            {"fromDate": "20250101", "toDate": "20251231"})
        extra = [{k: r[k] for k in EVIDENCE_FIELDS if k in r} for r in records]
        old = json.loads(gzip.decompress((base_dir / base["files"][symbol]["evidence"]["file"]).read_bytes()))
        full = old["records"] + extra
        frame = normalise_vci_execution_prices(full, symbol, "2018-01-01", "2025-12-31")
        event_bytes = (base_dir / base["files"][symbol]["events"]["file"]).read_bytes()
        events = json.loads(event_bytes)["records"]
        samples = audit_event_samples(symbol, full, events, frame, start="2018-01-01", end="2025-12-31")
        csv_path, evidence_path, event_path = (directory / f"{symbol}{suffix}" for suffix in
                                             (".csv", ".evidence.json.gz", ".events.json"))
        frame.to_csv(csv_path, index=False, date_format="%Y-%m-%d", float_format="%.8f")
        evidence_path.write_bytes(gzip.compress(json.dumps({"base_evidence_sha256": base["files"][symbol]["evidence"]["sha256"],
            "pages": pages, "records": full}, ensure_ascii=False, allow_nan=False).encode("utf-8"), mtime=0))
        event_path.write_bytes(event_bytes)
        manifest["files"][symbol] = {"csv": file_receipt(csv_path), "evidence": file_receipt(evidence_path),
            "events": file_receipt(event_path), "rows": int(len(frame)), "event_samples": samples}
        write_json(manifest_path, manifest)
        print(f"{symbol}: lưu {len(extra)} nến 2025 và hai mẫu quyền, không tính payoff", flush=True)
    verify_prices(directory, root, pending=True)
    manifest.update(price_gate="PASS", verified_at_utc=datetime.now(timezone.utc).isoformat())
    write_json(manifest_path, manifest)


def build_audit(directory: Path, root: Path = ROOT) -> dict[str, Any]:
    """Khóa lịch khả thi và nguồn riêng, giữ gate exposure độc lập với giá."""
    manifest, frames, events = verify_prices(directory, root)
    exposure = read_exposure(root)
    index = pd.read_csv(root / "data/historical/VNINDEX.csv", parse_dates=["Datetime"])
    calendar = design_calendar(frames, events, index)
    sources = {(directory / "manifest.json").relative_to(root).as_posix(): checksum(directory / "manifest.json"),
        EXPOSURE: checksum(root / EXPOSURE), "data/historical/VNINDEX.csv": manifest["calendar_sha256"]}
    for item in manifest["files"].values():
        for kind in ("csv", "evidence", "events"):
            path = directory / item[kind]["file"]
            sources[path.relative_to(root).as_posix()] = item[kind]["sha256"]
    return native_json({"version": VERSION, "namespace": "bic_icl_v2", "status": "BLOCKED",
        "confirmation_allowed": False, "blocking_reasons": ["EXPOSURE_UNVERIFIED"] +
            (["INSUFFICIENT_ELIGIBLE_CALENDAR"] if calendar["status"] != "PASS" else []),
        "price_gate": "PASS", "exposure": exposure, "calendar": calendar, "sources": sources,
        "code_sha256": {name: checksum(root / name) for name in DEPENDENCIES},
        "split": {"train": "2018-2022", "development": "2023_EXPLORATORY",
            "memory_refresh": "2023_2024_UPSTREAM_ONLY", "confirmation_2025": "BLOCKED",
            "fallback": "FORWARD_AFTER_LOCK_OR_NO_NEW_CONFIRMATION"},
        "is_execution_plan": False, "llm_calls": 0, "economic_labels_computed": False})


def main() -> None:
    """Tải giá công khai theo yêu cầu hoặc tái dựng audit hoàn toàn offline."""
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--download", action="store_true", help="Lấy giá thô 2025 công khai, không dùng API key/LLM")
    mode.add_argument("--build", action="store_true", help="Khóa nguồn và lịch eligibility, giữ exposure riêng")
    mode.add_argument("--verify", action="store_true", help="Tái dựng audit và so toàn payload, không gọi mạng")
    parser.add_argument("--output-dir", type=Path, default=ROOT / NAMESPACE)
    args = parser.parse_args()
    base = namespace_path(args.output_dir)
    prices, audit_path = base / "inputs/execution_prices_2025", base / "input_audit.json"
    if args.download:
        download_prices(prices)
        print("Gate giá revision PASS; chưa mở xác nhận hoặc sinh nhãn")
        return
    payload = build_audit(prices)
    envelope = {"payload": payload, "sha256": digest(payload)}
    if args.verify or audit_path.exists():
        saved = json.loads(audit_path.read_text(encoding="utf-8"))
        if saved != envelope:
            raise ValueError("Audit hoặc nguồn thay đổi; không ghi đè bản đã khóa")
    else:
        write_json(audit_path, envelope)
    print(f"Đối soát audit PASS: giá {payload['price_gate']}, lịch {payload['calendar']['status']}, "
          f"{payload['calendar']['selected_count']}/128 ngày; xác nhận {payload['status']} do exposure UNVERIFIED")


if __name__ == "__main__":
    main()
