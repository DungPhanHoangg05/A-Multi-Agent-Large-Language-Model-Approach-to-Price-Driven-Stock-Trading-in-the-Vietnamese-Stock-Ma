"""Thu thập và xác minh gate giá thô VCI cho Phase A; không tạo nhãn kinh tế."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.metadata
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
from core.execution_prices import (
    RAW_FIELD_MAP, STOCK_SYMBOLS, build_verified_cycle_schedule,
    load_verified_execution_data, normalise_vci_execution_prices, raw_point_in_time_snapshot,
)
from scripts.prepare_historical_data import clean_ohlcv, verify_saved_data


START, END = "2018-01-01", "2022-12-31"
BASE_URL = "https://iq.vietcap.com.vn/api/iq-insight-service/v1"
EVENT_CODES = "DIV,ISS,AIS,MA,MOVE,NLIS,OTHE,RETU,SUSP"
EVIDENCE_FIELDS = tuple(dict.fromkeys((
    "id", "ticker", *RAW_FIELD_MAP, "openPriceAdjusted", "highestPriceAdjusted",
    "lowestPriceAdjusted", "closePriceAdjusted", "totalShares",
)))


def write_json(path: Path, payload: Any) -> None:
    """Ghi checkpoint JSON nguyên tử, chỉ chứa kiểu nguyên bản."""
    pending = path.with_suffix(path.suffix + ".tmp")
    pending.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    pending.replace(path)


def fetch_paginated(url: str, params: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Lấy đủ trang theo pageSize thực tế; không tin size yêu cầu hoặc trang đầu."""
    from vnstock.core.utils.user_agent import get_headers

    records: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    page, expected_total, expected_pages, page_size = 0, None, None, None
    while True:
        request_params = {**params, "page": page, "size": page_size or 1000}
        for attempt in range(3):
            try:
                response = requests.get(url, params=request_params, headers=get_headers(data_source="VCI"), timeout=(20, 30))
                break
            except (requests.Timeout, requests.ConnectionError):
                if attempt == 2:
                    raise
                print(f"Nguồn VCI tạm gián đoạn; thử lại trang {page} sau {2 ** attempt} giây", flush=True)
                time.sleep(2 ** attempt)
        response.raise_for_status()
        payload = response.json()
        if payload.get("successful") is not True or payload.get("code") != 0:
            raise ValueError("VCI không xác nhận request thành công")
        data = payload["data"]
        if page == 0:
            expected_total, expected_pages, page_size = data["totalElements"], data["totalPages"], data["size"]
            if not isinstance(page_size, int) or page_size < 1 or expected_total < 1:
                raise ValueError("Phân trang VCI không hợp lệ")
            if expected_pages != int(np.ceil(expected_total / page_size)):
                raise ValueError("Số trang VCI không nhất quán")
        if (data["number"] != page or data["totalElements"] != expected_total
                or data["totalPages"] != expected_pages or data["size"] != page_size):
            raise ValueError("Metadata phân trang thay đổi giữa các trang")
        content = data["content"]
        if len(content) != min(page_size, expected_total - len(records)):
            raise ValueError("API cắt cụt trang giá/sự kiện")
        records.extend(content)
        receipts.append({
            "url": response.url, "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "response_sha256": hashlib.sha256(response.content).hexdigest(),
            "number": page, "size": page_size, "rows": len(content),
            "total_elements": expected_total, "total_pages": expected_pages,
        })
        time.sleep(1.05)
        if page + 1 == expected_pages:
            if data["last"] is not True or len(records) != expected_total:
                raise ValueError("Thiếu trang cuối VCI")
            break
        if data["last"] is not False:
            raise ValueError("API báo trang cuối quá sớm")
        page += 1
    return records, receipts


def sample_event_dates(events: list[dict[str, Any]], start: str = START, end: str = END) -> dict[str, str]:
    """Chọn một ngày chia cổ phiếu và một ngày cổ tức tiền mặt khác nhau."""
    dated = [e for e in events if e.get("exrightDate") and start <= e["exrightDate"][:10] <= end]
    stock = [e for e in dated if "cổ tức bằng cổ phiếu" in e.get("eventTitleVi", "").lower()
             or "cổ phiếu thưởng" in e.get("eventTitleVi", "").lower()]
    if not stock:
        raise ValueError("Không có sự kiện chia cổ phiếu để kiểm toán")
    split_date = max(e["exrightDate"][:10] for e in stock)
    cash = [e for e in dated if e.get("eventCode") == "DIV" and e.get("valuePerShare", 0) > 0
            and e["exrightDate"][:10] != split_date]
    if not cash:
        raise ValueError("Không có ngày cổ tức tiền mặt riêng để kiểm toán")
    return {"stock_dividend": split_date, "cash_dividend": max(e["exrightDate"][:10] for e in cash)}


def audit_event_samples(
    symbol: str, records: list[dict[str, Any]], events: list[dict[str, Any]], frame: pd.DataFrame,
    *, start: str = START, end: str = END,
) -> list[dict[str, Any]]:
    """Đối chiếu giá thô, giá điều chỉnh hai nguồn và công thức Reference ngày quyền."""
    from vnstock.api.quote import Quote

    audit: list[dict[str, Any]] = []
    by_date = {r["tradingDate"][:10]: r for r in records}
    for event_type, date in sample_event_dates(events, start, end).items():
        position = pd.DatetimeIndex(frame["Datetime"]).get_loc(pd.Timestamp(date))
        previous = frame.iloc[position - 1]["Datetime"].strftime("%Y-%m-%d")
        same_day = [e for e in events if e.get("exrightDate", "")[:10] == date]
        # Hai bản ghi giống nội dung không được làm nhân đôi cổ tức hoặc tỷ lệ chia.
        unique = {json.dumps({k: e.get(k) for k in (
            "eventCode", "eventTitleVi", "exrightDate", "valuePerShare", "exerciseRatio"
        )}, sort_keys=True, ensure_ascii=False): e for e in same_day}.values()
        cash = sum(float(e.get("valuePerShare", 0) or 0) for e in unique if e.get("eventCode") == "DIV")
        stock_ratio = sum(float(e.get("exerciseRatio", 0) or 0) for e in unique
                          if "cổ tức bằng cổ phiếu" in e.get("eventTitleVi", "").lower()
                          or "cổ phiếu thưởng" in e.get("eventTitleVi", "").lower())
        before, after = by_date[previous], by_date[date]
        theoretical_reference = (float(before["closePrice"]) - cash) / (1 + stock_ratio)
        reference_difference = abs(float(after["referencePrice"]) - theoretical_reference)
        if reference_difference > 100:
            raise ValueError(f"{symbol} {date}: Reference không khớp quyền trong sai số một bước giá")
        quotes: dict[str, Any] = {}
        for source in ("VCI", "KBS"):
            end = (pd.Timestamp(date) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            raw = Quote(symbol=symbol, source=source).history(start=previous, end=end, interval="1D", floating=None)
            quoted = clean_ohlcv(raw, symbol, previous, end).set_index("Datetime")
            prices = quoted.loc[pd.to_datetime([previous, date]), ["Open", "High", "Low", "Close"]]
            ratios = prices.to_numpy() / frame.set_index("Datetime").loc[prices.index, prices.columns].to_numpy()
            if not ((ratios > 0).all() and (ratios < 1).all()):
                raise ValueError("Mẫu không phân biệt được giá biểu đồ với giá thô")
            if (ratios.max(axis=1) - ratios.min(axis=1)).max() > 0.002:
                raise ValueError("OHLC điều chỉnh không cùng cơ sở tỷ lệ trong một phiên")
            quotes[source] = {
                "before": prices.iloc[0].to_dict(), "exright": prices.iloc[1].to_dict(),
                "close_scale_before": float(ratios[0, 3]), "close_scale_exright": float(ratios[1, 3]),
            }
            time.sleep(1.05)
        prefix, receipts = fetch_paginated(
            f"{BASE_URL}/company/{symbol}/price-history",
            {"fromDate": previous.replace("-", ""), "toDate": previous.replace("-", "")},
        )
        prefix_frame = normalise_vci_execution_prices(prefix, symbol, previous, previous)
        expected = raw_point_in_time_snapshot(frame, previous).tail(1).reset_index(drop=True)
        pd.testing.assert_frame_equal(prefix_frame.loc[:, expected.columns], expected, check_dtype=False)
        audit.append({
            "symbol": symbol, "type": event_type, "previous_date": previous, "exright_date": date,
            "raw_before": {k: before[k] for k in EVIDENCE_FIELDS if k in before},
            "raw_exright": {k: after[k] for k in EVIDENCE_FIELDS if k in after},
            "cash_dividend_vnd": cash, "stock_dividend_ratio": stock_ratio,
            "theoretical_reference_vnd": theoretical_reference,
            "reference_difference_vnd": reference_difference, "quotes": quotes,
            "prefix_request": receipts, "raw_prefix_equals_extended": True,
        })
    return audit


def file_receipt(path: Path) -> dict[str, str]:
    """Lưu checksum byte của artifact."""
    return {"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def download_bundle(output_dir: Path, *, start: str = START, end: str = END, resume: bool = False) -> None:
    """Checkpoint từng mã; chỉ bật PASS sau kiểm toán đủ bốn mã."""
    if not START <= start <= end <= "2024-12-31":
        raise ValueError("Phạm vi giá phải trong 2018–2024")
    if output_dir.exists() and any(output_dir.iterdir()) and not resume:
        raise ValueError("Thư mục giá đã có dữ liệu; chọn thư mục mới, không ghi đè bằng chứng")
    historical = REPO_ROOT / "data/historical"
    verify_saved_data(historical)
    calendar = pd.read_csv(historical / "VNINDEX.csv", parse_dates=["Datetime"])
    calendar = calendar.loc[calendar["Datetime"].between(start, end), "Datetime"].reset_index(drop=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "price_gate": "PENDING", "price_basis": "UNADJUSTED_EXECUTION", "price_unit": "thousand_VND",
        "primary_source": "VCI", "crosscheck_sources": ["VCI", "KBS"],
        "acquisition_method": "VCI_PUBLIC_PRICE_HISTORY_REST_WITH_VNSTOCK_HEADERS",
        "source_library": "vnstock", "source_library_version": importlib.metadata.version("vnstock"),
        "requested_start": start, "requested_end": end, "raw_field_map": RAW_FIELD_MAP,
        "calendar_sha256": hashlib.sha256((historical / "VNINDEX.csv").read_bytes()).hexdigest(),
        "corporate_action_policy": "EXCLUDE_WHEN_ENTRY_LT_EXRIGHT_LE_EXIT",
        "signal_price_basis": "UNADJUSTED_PREFIX_NO_RETROACTIVE_ADJUSTMENTS",
        "files": {},
    }
    if resume:
        manifest = verify_bundle(output_dir, start=start, end=end, allow_partial=True)
    else:
        write_json(output_dir / "manifest.json", manifest)
    for symbol in STOCK_SYMBOLS:
        if symbol in manifest["files"]:
            print(f"{symbol}: dùng phần đã lưu và xác minh; không tải lại", flush=True)
            continue
        records, pages = fetch_paginated(
            f"{BASE_URL}/company/{symbol}/price-history",
            {"fromDate": start.replace("-", ""), "toDate": end.replace("-", "")},
        )
        events, event_pages = fetch_paginated(
            f"{BASE_URL}/events", {"ticker": symbol, "fromDate": "20170101",
                                   "toDate": f"{int(end[:4]) + 1}1231", "eventCode": EVENT_CODES},
        )
        frame = normalise_vci_execution_prices(records, symbol, start, end)
        if not frame["Datetime"].equals(calendar):
            raise ValueError(f"{symbol}: lịch giá thô không khớp VN-Index")
        event_path = output_dir / f"{symbol}.events.json"
        write_json(event_path, {"pages": event_pages, "records": events})
        evidence_path = output_dir / f"{symbol}.evidence.json.gz"
        projected = [{k: r[k] for k in EVIDENCE_FIELDS if k in r} for r in records]
        evidence_path.write_bytes(gzip.compress(json.dumps(
            {"pages": pages, "records": projected}, ensure_ascii=False, allow_nan=False
        ).encode("utf-8"), mtime=0))
        csv_path = output_dir / f"{symbol}.csv"
        frame.to_csv(csv_path, index=False, date_format="%Y-%m-%d", float_format="%.8f")
        samples = audit_event_samples(symbol, records, events, frame, start=start, end=end)
        schedule = build_verified_cycle_schedule(frame, events)
        rejected = schedule.loc[~schedule["eligible"]].copy()
        for column in ("as_of_date", "entry_date", "exit_date"):
            rejected[column] = rejected[column].dt.strftime("%Y-%m-%d")
        manifest["files"][symbol] = {
            "csv": file_receipt(csv_path), "evidence": file_receipt(evidence_path),
            "events": file_receipt(event_path), "rows": int(len(frame)),
            "candidates": int(len(schedule)), "eligible": int(schedule["eligible"].sum()),
            "excluded_cycles": rejected.to_dict("records"), "event_samples": samples,
            "nonmatched_dates": frame.loc[frame["Volume"].eq(0), "Datetime"].dt.strftime("%Y-%m-%d").tolist(),
            "close_last_match_disagreements": frame.loc[
                ~np.isclose(frame["Close"], frame["MatchPrice"], rtol=0, atol=1e-9), "Datetime"
            ].dt.strftime("%Y-%m-%d").tolist(),
        }
        write_json(output_dir / "manifest.json", manifest)
        print(f"{symbol}: {len(frame)} nến thô; {int(schedule['eligible'].sum())}/{len(schedule)} chu kỳ qua gate giá", flush=True)
    manifest["price_gate"] = "PASS"
    manifest["verified_at_utc"] = datetime.now(timezone.utc).isoformat()
    write_json(output_dir / "manifest.json", manifest)
    try:
        verify_bundle(output_dir, start=start, end=end)
    except Exception:
        manifest["price_gate"] = "PENDING"
        write_json(output_dir / "manifest.json", manifest)
        raise


def verify_bundle(output_dir: Path, *, start: str = START, end: str = END,
                  allow_partial: bool = False) -> dict[str, Any]:
    """Tái tính gate từ evidence, CSV, lịch, mẫu quyền và lịch ứng viên hoàn toàn offline."""
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    found = set(manifest["files"])
    if (not START <= start <= end <= "2024-12-31" or not found <= set(STOCK_SYMBOLS)
            or (not allow_partial and found != set(STOCK_SYMBOLS))
            or manifest["price_gate"] not in (("PASS", "PENDING") if allow_partial else ("PASS",))
            or manifest["price_basis"] != "UNADJUSTED_EXECUTION" or manifest["price_unit"] != "thousand_VND"
            or manifest["primary_source"] != "VCI" or manifest["source_library"] != "vnstock"
            or manifest["requested_start"] != start or manifest["requested_end"] != end or manifest["raw_field_map"] != RAW_FIELD_MAP
            or manifest["crosscheck_sources"] != ["VCI", "KBS"]
            or manifest["corporate_action_policy"] != "EXCLUDE_WHEN_ENTRY_LT_EXRIGHT_LE_EXIT"):
        raise ValueError("Phạm vi hoặc cơ sở gate không hợp lệ")
    calendar_path = REPO_ROOT / "data/historical/VNINDEX.csv"
    if hashlib.sha256(calendar_path.read_bytes()).hexdigest() != manifest["calendar_sha256"]:
        raise ValueError("Lịch tham chiếu của gate đã thay đổi")
    calendar = pd.read_csv(calendar_path, parse_dates=["Datetime"])
    calendar = calendar.loc[calendar["Datetime"].between(start, end), "Datetime"].reset_index(drop=True)
    for symbol in STOCK_SYMBOLS:
        if symbol not in found:
            continue
        item = manifest["files"][symbol]
        for kind in ("csv", "evidence", "events"):
            receipt = item[kind]
            if Path(receipt["file"]).name != receipt["file"] or file_receipt(output_dir / receipt["file"]) != receipt:
                raise ValueError("Checksum hoặc đường dẫn giá đã lưu không hợp lệ")
        frame = pd.read_csv(output_dir / item["csv"]["file"], parse_dates=["Datetime"])
        events = json.loads((output_dir / item["events"]["file"]).read_text(encoding="utf-8"))["records"]
        if not allow_partial:
            frame, events = load_verified_execution_data(output_dir, symbol)
        evidence = json.loads(gzip.decompress((output_dir / item["evidence"]["file"]).read_bytes()))
        reconstructed = normalise_vci_execution_prices(evidence["records"], symbol, start, end)
        pd.testing.assert_frame_equal(frame, reconstructed, check_dtype=False)
        if len(frame) != item["rows"]:
            raise ValueError("Số nến không khớp bằng chứng")
        if not frame["Datetime"].equals(calendar):
            raise ValueError("Lịch CSV thực thi không khớp VN-Index")
        schedule = build_verified_cycle_schedule(frame, events)
        if len(schedule) != item["candidates"] or int(schedule["eligible"].sum()) != item["eligible"]:
            raise ValueError("Lịch ứng viên thay đổi so với kiểm toán")
        rejected = schedule.loc[~schedule["eligible"]].copy()
        for column in ("as_of_date", "entry_date", "exit_date"):
            rejected[column] = rejected[column].dt.strftime("%Y-%m-%d")
        if rejected.to_dict("records") != item["excluded_cycles"]:
            raise ValueError("Danh sách chu kỳ loại không khớp kiểm toán")
        if len(item["event_samples"]) != 2 or {s["type"] for s in item["event_samples"]} != {
            "stock_dividend", "cash_dividend"
        }:
            raise ValueError("Thiếu mẫu ngày chia cổ phiếu/cổ tức tiền mặt")
        for sample in item["event_samples"]:
            if (sample["raw_prefix_equals_extended"] is not True or sample["reference_difference_vnd"] > 100
                    or set(sample["quotes"]) != {"VCI", "KBS"}):
                raise ValueError("Mẫu giá và kiểm tra prefix chưa qua gate")
            evidence_by_date = {r["tradingDate"][:10]: r for r in evidence["records"]}
            if (sample["raw_before"] != evidence_by_date[sample["previous_date"]]
                    or sample["raw_exright"] != evidence_by_date[sample["exright_date"]]):
                raise ValueError("Giá mẫu không khớp evidence thô")
            expected_reference = (sample["raw_before"]["closePrice"] - sample["cash_dividend_vnd"]) / (
                1 + sample["stock_dividend_ratio"]
            )
            if not np.isclose(expected_reference, sample["theoretical_reference_vnd"], rtol=0, atol=1e-8):
                raise ValueError("Công thức quyền trong biên bản không khớp")
            for quote in sample["quotes"].values():
                for label, date in (("before", sample["previous_date"]), ("exright", sample["exright_date"])):
                    raw_prices = frame.set_index("Datetime").loc[pd.Timestamp(date), ["Open", "High", "Low", "Close"]]
                    prices = pd.Series(quote[label]).reindex(raw_prices.index).to_numpy(dtype=float)
                    ratios = prices / raw_prices.to_numpy(dtype=float)
                    if not np.isfinite(ratios).all() or not ((ratios > 0).all() and (ratios < 1).all()) or ratios.max() - ratios.min() > 0.002:
                        raise ValueError("Đối chiếu đơn vị giá mẫu không tái lập được")
    return manifest


def main() -> None:
    """Chạy kiểm toán hoặc tái lập offline; mặc định không gọi mạng."""
    parser = argparse.ArgumentParser(description="Xác minh gate giá thực thi VCI/KBS")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "data/execution_prices")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--resume", action="store_true", help="Tiếp tục tải sau xác minh phần đã lưu")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--start", default=START, help="Ngày đầu nguồn giá, gồm warm-up")
    parser.add_argument("--end", default=END, help="Ngày cuối nguồn giá; OOS đến 2024-12-31")
    args = parser.parse_args()
    if args.download and args.verify_only:
        parser.error("Chọn tải mới hoặc xác minh offline")
    if args.resume and not args.download:
        parser.error("--resume cần đi cùng --download")
    if args.download:
        download_bundle(args.output_dir, start=args.start, end=args.end, resume=args.resume)
    manifest = verify_bundle(args.output_dir, start=args.start, end=args.end)
    eligible = sum(item["eligible"] for item in manifest["files"].values())
    candidates = sum(item["candidates"] for item in manifest["files"].values())
    print(f"Gate giá PASS: 4 mã, 8 mẫu quyền, {eligible}/{candidates} chu kỳ đủ cơ sở giá; chưa sinh nhãn")


if __name__ == "__main__":
    main()
