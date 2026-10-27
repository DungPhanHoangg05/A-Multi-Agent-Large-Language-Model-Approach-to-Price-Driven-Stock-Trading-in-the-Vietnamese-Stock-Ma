"""Kiểm inventory W10 offline, giữ nguyên giá, archive W9 và ledger dùng chung."""

from __future__ import annotations

import argparse
import gzip
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any
import zipfile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.execution_prices import (
    STOCK_SYMBOLS, build_verified_cycle_schedule, corporate_action_barriers,
    load_verified_execution_data, normalise_vci_execution_prices, validate_raw_frame,
)
from scripts.verify_execution_price_gate import verify_bundle
from scripts.prepare_historical_data import verify_saved_data
from core.regime_detector import MIN_TRAIN_FEATURES, WARMUP_ROWS

ARCHIVE = "docs/plan/implementation_evidence.zip"
RETIRED = "retired_20261027/"
SOURCE_2025 = "outputs/bayesian_benchmark/unified_bic_v1/inputs/execution_prices_2025/"
W9_BASE = "outputs/bayesian_benchmark/improvement_v1/holdout/"
W9_HASHES = {
    W9_BASE + "plan.json": "6b6760768fe98731e64e1e518ffbc351db29a41397f46bfad0d3a19d96956944",
    W9_BASE + "run/report.json": "0a926be1e6da2803d56dd7a572a4d3eae7b8863cc3fcd02eea111df35cd7c23f",
    W9_BASE + "run/verification.json": "9bb0868740de59972e3183f2e3c449b3f7cd81d559f7598c910ed020681db498",
    W9_BASE + "run/bootstrap.json": "78ae445037f68fa0f8cca4638dc7bc3e7c24efb2854539e078478e46db919e57",
    W9_BASE + "frozen_results_v1.zip": "1db2024a3a338cadcf72692287471f8a14feba49ce8a1b1a488b951896cfec70",
    "docs/figures/holdout_v1/manifest.json": "ce9dafcfa038bbff12bfe1b966ea5b2e519dd0e2d67adcea56ef00dc09d1cb48",
}


def digest(data: bytes) -> str:
    """Băm byte nguồn, không chuẩn hóa newline của bằng chứng."""
    return hashlib.sha256(data).hexdigest()


def provisional_counts(frame: pd.DataFrame, events: list[dict[str, Any]],
                       calendar: pd.DatetimeIndex) -> dict[str, Any]:
    """Đếm support giá/feature trên lưới thăm dò; chưa sinh nhãn hay khóa lịch.

    Neo query ở index 20, bước ba phiên; tách năm bằng cả query và exit.
    W10-02 phải khóa neo chính thức trước bank/train, không chọn theo outcome.
    """
    validate_raw_frame(frame)
    dates = pd.DatetimeIndex(frame["Datetime"])
    expected = calendar[(calendar >= dates[0]) & (calendar <= dates[-1])]
    if not dates.equals(expected):
        raise ValueError("Inventory yêu cầu lịch giá liên tiếp khớp VNINDEX")
    schedule = build_verified_cycle_schedule(frame, events, warmup=21, step=3)
    query = np.arange(20, len(frame) - 3, 3)
    barriers = corporate_action_barriers(frame, events).to_numpy(dtype="datetime64[ns]")
    raw_dates = dates.to_numpy(dtype="datetime64[ns]")
    feature_blocked = (
        np.searchsorted(barriers, raw_dates[query], side="right")
        - np.searchsorted(barriers, raw_dates[query - 20], side="right")
    ) > 0
    eligible = schedule["eligible"].to_numpy() & ~feature_blocked
    query_year = schedule["as_of_date"].dt.year.to_numpy()
    exit_year = schedule["exit_date"].dt.year.to_numpy()
    years = {}
    for year in range(int(dates[0].year), int(dates[-1].year) + 1):
        same_year = (query_year == year) & (exit_year == year)
        years[str(year)] = {
            "candidates": int(same_year.sum()),
            "holding_eligible": int((same_year & schedule["eligible"].to_numpy()).sum()),
            "feature_barrier": int((same_year & feature_blocked).sum()),
            "joint_eligible": int((same_year & eligible).sum()),
        }
    return {
        "grid": "PROVISIONAL_QUERY_INDEX_20_STEP_3_NOT_PROTOCOL",
        "years": years,
        "cross_year_excluded": int((query_year != exit_year).sum()),
        "note": "Chỉ kiểm giá/quyền và cửa sổ 21 phiên; chưa kiểm HMM/K/m/block63 hoặc sinh y/r_net.",
    }


def date_hits(value: Any, path: str = "") -> list[str]:
    """Chỉ lấy ngày query cấu trúc; không đọc nghĩa action, payoff hoặc UUID."""
    hits: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}/{key}"
            if key in {"as_of_date", "query_date", "query_cutoff", "query_cutoff_date"}:
                if isinstance(child, str) and re.fullmatch(r"2025-\d{2}-\d{2}(?:T.*)?", child):
                    hits.append(child_path + "=" + child[:10])
            hits.extend(date_hits(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            hits.extend(date_hits(child, f"{path}/{index}"))
    return hits


def scan_local_queries() -> dict[str, Any]:
    """Kiểm JSON runtime kể cả ignored; giữ reason nếu thư mục không đọc được."""
    errors: list[str] = []
    hits: dict[str, list[str]] = {}
    count = 0
    def walk_error(error: OSError) -> None:
        """Giữ đường dẫn bị từ chối; không suy thành không có exposure."""
        errors.append(str(Path(error.filename).relative_to(ROOT)))
    for parent, _, names in os.walk(ROOT / "outputs", onerror=walk_error):
        for name in sorted(names):
            if not name.endswith(".json"):
                continue
            path = Path(parent) / name
            relative = path.relative_to(ROOT).as_posix()
            try:
                data = json.loads(path.read_bytes())
                count += 1
                found = date_hits(data)
                if found:
                    hits[relative] = found
            except (OSError, ValueError) as exc:
                errors.append(relative + ":" + type(exc).__name__)
    return {"parsed_json": count, "query_2025_hits": dict(sorted(hits.items())),
            "errors": sorted(errors), "unseen_outcomes_proven": False,
            "confirmation_allowed": False,
            "limits": "Quét khóa ngày query trong JSON outputs và archive retired; không chứng minh "
                      "hoạt động ngoài workspace, ảnh/UI, khóa ngày tùy biến hoặc dữ liệu đã xóa chưa từng được xem."}


def audit() -> dict[str, Any]:
    """Đối soát nguồn và exposure; không khôi phục revision cũ vào runtime."""
    historical = verify_saved_data(ROOT / "data/historical")
    calendar = pd.DatetimeIndex(pd.read_csv(ROOT / "data/historical/VNINDEX.csv", parse_dates=["Datetime"])["Datetime"])
    manifests = {}
    stocks = {}
    for directory, end in (("data/execution_prices", "2022-12-31"),
                           ("data/execution_prices_oos", "2024-12-31")):
        manifest = verify_bundle(ROOT / directory, start="2018-01-01", end=end)
        manifests[directory] = digest((ROOT / directory / "manifest.json").read_bytes())
        stocks[directory] = {}
        for symbol in STOCK_SYMBOLS:
            frame, events = load_verified_execution_data(ROOT / directory, symbol)
            dates = pd.DatetimeIndex(frame["Datetime"])
            event_dates = pd.to_datetime([e["exrightDate"] for e in events if e.get("exrightDate")])
            stocks[directory][symbol] = {
                "rows": len(frame), "first": str(dates[0].date()), "last": str(dates[-1].date()),
                "events": len(events), "events_with_exright": len(event_dates),
                "barriers_in_price_range": int(len(corporate_action_barriers(frame, events).intersection(dates))),
                "zero_volume_dates": dates[frame["Volume"].eq(0)].strftime("%Y-%m-%d").tolist(),
                "calendar_missing": len(calendar[(calendar >= dates[0]) & (calendar <= dates[-1])].difference(dates)),
                "provisional_dense_support": provisional_counts(frame, events, calendar) if end == "2022-12-31" else None,
                "legacy_candidates": manifest["files"][symbol]["candidates"],
                "legacy_eligible": manifest["files"][symbol]["eligible"],
            }
    archived_queries = {}
    archived_source = {}
    with zipfile.ZipFile(ROOT / ARCHIVE) as archive:
        retired = json.loads(archive.read(RETIRED + "manifest.json"))
        for name, item in retired["files"].items():
            data = archive.read(RETIRED + name)
            if digest(data) != item["sha256"] or len(data) != item["bytes"]:
                raise ValueError("Archive retired sai checksum: " + name)
            if name.endswith(".json"):
                found = date_hits(json.loads(data))
                if found:
                    archived_queries[name] = found
        manifest = json.loads(archive.read(RETIRED + SOURCE_2025 + "manifest.json"))
        for symbol in STOCK_SYMBOLS:
            item = manifest["files"][symbol]
            for kind in ("csv", "events", "evidence", "acquisition"):
                source = item[kind]
                if digest(archive.read(RETIRED + SOURCE_2025 + source["file"])) != source["sha256"]:
                    raise ValueError("Checksum nguồn 2025 không khớp: " + symbol)
            frame = pd.read_csv(BytesIO(archive.read(RETIRED + SOURCE_2025 + item["csv"]["file"])), parse_dates=["Datetime"])
            evidence = json.loads(gzip.decompress(archive.read(RETIRED + SOURCE_2025 + item["evidence"]["file"])))
            rebuilt = normalise_vci_execution_prices(evidence["records"], symbol, "2018-01-01", "2025-12-31")
            pd.testing.assert_frame_equal(frame, rebuilt, check_dtype=False)
            prefix, _ = load_verified_execution_data(ROOT / "data/execution_prices_oos", symbol)
            pd.testing.assert_frame_equal(frame.iloc[:len(prefix)], prefix, check_dtype=False)
            dates = pd.DatetimeIndex(frame["Datetime"])
            if not dates.equals(calendar):
                raise ValueError("Lịch archive 2025 không khớp VNINDEX")
            archived_source[symbol] = {"rows": len(frame), "rows_2025": int((dates.year == 2025).sum()),
                                       "prefix_2024_matches": True, "raw_evidence_matches": True,
                                       "events_match_oos": item["events"]["sha256"] == json.loads((ROOT / "data/execution_prices_oos/manifest.json").read_bytes())["files"][symbol]["events"]["sha256"]}
    bindings = {}
    for name, expected in W9_HASHES.items():
        actual = digest((ROOT / name).read_bytes())
        if actual != expected:
            raise ValueError("Bằng chứng W9 khác binding: " + name)
        bindings[name] = actual
    ledger_path = ROOT / "outputs/oos_pilot/api_usage.json"
    ledger = json.loads(ledger_path.read_bytes())
    with zipfile.ZipFile(ROOT / (W9_BASE + "frozen_results_v1.zip")) as frozen:
        old = json.loads(frozen.read("outputs/oos_pilot/api_usage.json"))
    current_ids = {item["id"]: item for item in ledger["requests"]}
    unchanged = sum(current_ids.get(item["id"]) == item for item in old["requests"])
    if unchanged != len(old["requests"]):
        raise ValueError("Request W9 trong ledger chung đã bị thay đổi hoặc mất")
    declaration_ref = "4d34bc4:docs/plan/week10/exposure_inventory_v2.json"
    declaration_bytes = subprocess.run(
        ["git", "show", declaration_ref], cwd=ROOT, capture_output=True, check=True,
    ).stdout
    declaration = json.loads(declaration_bytes)
    return {
        "inventory_version": "mt_bicl_resources_v1", "audit_date": "2026-10-27",
        "script_sha256": digest(Path(__file__).read_bytes()),
        "historical_manifest_sha256": digest((ROOT / "data/historical/manifest.json").read_bytes()),
        "historical_basis": historical["corporate_action_basis"],
        "source_code_sha256": {name: digest((ROOT / name).read_bytes()) for name in (
            "core/execution_prices.py", "core/pit_price_features.py", "core/regime_detector.py",
            "scripts/verify_execution_price_gate.py", "scripts/prepare_historical_data.py")},
        "regime_prerequisites": {
            "warmup_rows": WARMUP_ROWS, "minimum_train_feature_rows": MIN_TRAIN_FEATURES,
            "minimum_history_rows": WARMUP_ROWS - 1 + MIN_TRAIN_FEATURES,
            "earliest_fit_date_by_row_count": str(calendar[WARMUP_ROWS - 2 + MIN_TRAIN_FEATURES].date()),
            "status": "NOT_FITTED_FOR_MT_BICL",
            "limits": "Ngày sớm nhất chỉ đủ số hàng, chưa đảm bảo fit hội tụ. Giá/feature 2018–2019 "
                      "có thể dùng nhưng regime đầu block chưa có historical prefix phải giữ missing/reason; "
                      "không dùng artifact cuối 2022 gán lại. W10-02 khóa chính sách trước train.",
        },
        "price_manifest_sha256": manifests, "prices": stocks,
        "retired_archive_sha256": digest((ROOT / ARCHIVE).read_bytes()),
        "retired_verified_entries": len(retired["files"]), "retired_base": retired["base_commit"],
        "archived_2025": {"path": RETIRED + SOURCE_2025, "stocks": archived_source,
                          "status": "ARCHIVE_BYTES_RAW_PREFIX_VERIFIED_NOT_RELEASED",
                          "limits": "Chưa phục hồi namespace mới hoặc chạy lại verifier quyền 2025; "
                                    "không tự kế thừa price_gate PASS của revision đã dừng."},
        "exposure": {"historical_declaration": retired["exposure"],
                     "participant_declaration": {"git_ref": declaration_ref,
                                                 "sha256": digest(declaration_bytes),
                                                 "text": declaration["participant_declaration"],
                                                 "unseen_outcomes_proven": declaration["unseen_outcomes_proven"]},
                     "local_outputs": scan_local_queries(), "retired_query_2025_hits": archived_queries,
                     "classification": {"through_2022": "REUSED_TRAIN_VALIDATION",
                                        "2023": "ADAPTIVE_DEVELOPMENT", "2024": "EXPOSED_W9",
                                        "2025": "SOURCE_SEEN_NO_NEW_CONFIRMATION_RELEASE"}},
        "w9_locked_sha256": bindings,
        "shared_ledger": {"sha256": digest(ledger_path.read_bytes()),
                          "current_requests": len(ledger["requests"]), "w9_frozen_requests": len(old["requests"]),
                          "w9_requests_unchanged": unchanged,
                          "note": "Ledger chung đã tiến triển sau W9; không so bằng hash ledger lịch sử, không reset."},
        "time_budget": {"status": "USER_CALENDAR_TRACKED_IN_WEEK_README", "training_cap_hours": 12,
                        "data_stop": "W12 ngày hai; không tự suy ngày dương lịch"},
        "confirmation_allowed": False,
    }


def main() -> None:
    """Tạo inventory mới hoặc đối soát toàn payload đã lưu; không gọi mạng."""
    parser = argparse.ArgumentParser(description="Inventory nguồn và tài nguyên MT-BICL offline")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/plan/week10/resource_inventory.json")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = audit()
    if args.check:
        if result != json.loads(args.output.read_bytes()):
            raise ValueError("Inventory khác nguồn hiện tại; phải đối soát thay đổi")
    else:
        with args.output.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
    print("Inventory nguồn hoàn tất; chưa cấp phép xác nhận hoặc chốt quỹ thời gian")


if __name__ == "__main__":
    main()
