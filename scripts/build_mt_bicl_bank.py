"""Dựng/kiểm bank MT-BICL 2018–2022 bằng nguồn đã khóa; không gọi LLM."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
from importlib.metadata import version
from pathlib import Path
import platform
import sys
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.backtest_engine import compute_round_trip_net_return
from core.bayesian_memory import atomic_write_json, read_json
from core.execution_prices import corporate_action_barriers, execution_prices_for_cycle, load_verified_execution_data
from core.mt_bicl_bank import BANK_END, PROTOCOL_SHA256, SOURCE, SYMBOLS, build_dense_bank, content_hash, partition, read_protocol
from core.mt_bicl_scaler import fit_scaler, transform_features
from core.pit_price_features import extract_pit_price_features
from scripts.verify_mt_bicl_protocol import verify as verify_protocol

NAMESPACE = ROOT / "outputs/bayesian_benchmark/mt_bicl"
DEFAULT_OUTPUT = NAMESPACE / "inputs/dense_bank.json"
CODE = ("core/mt_bicl_bank.py", "core/mt_bicl_scaler.py", "scripts/build_mt_bicl_bank.py",
        "scripts/verify_mt_bicl_protocol.py")


def verify_records(bank: dict[str, Any], prices: dict[str, tuple[pd.DataFrame, list[dict[str, Any]]]]) -> dict[str, Any]:
    """Đối chiếu toàn feature và nhãn với primitive độc lập, không duyệt row Pandas."""
    calendar = pd.DatetimeIndex(bank["calendar"])
    ids: set[str] = set()
    label_count = 0
    coverage = {}
    for symbol in SYMBOLS:
        frame, events = prices[symbol]
        coverage[symbol] = {"dates": pd.DatetimeIndex(frame["Datetime"]),
                            "barriers": corporate_action_barriers(frame, events),
                            "volume": frame.set_index("Datetime")["Volume"]}
    for row in bank["records"]:
        symbol = row["symbol"]
        if row["episode_id"] in ids or row["episode_id"] != f"{symbol}-{row['as_of_date']}":
            raise ValueError("ID cycle trùng hoặc không canonical")
        ids.add(row["episode_id"])
        dates = pd.to_datetime([row["as_of_date"], row["entry_date"], row["exit_date"]])
        indices = calendar.get_indexer(dates)
        if (indices < 0).any() or indices.tolist() != [row["calendar_index"], row["calendar_index"]+1, row["calendar_index"]+3]:
            raise ValueError("Cycle không đúng phiên t+1/t+3")
        block = int(indices[0]//63)
        if (row["task_id"] != f"{symbol}:block{block:04d}" or row["block_index"] != block
                or row["block_start_date"] != bank["calendar"][63*block]
                or row["block_start_calendar_index"] != block*63 or row["block_end_calendar_index"] != (block+1)*63-1):
            raise ValueError("Cycle không đúng block cố định")
        frame, events = prices[symbol]
        expected = extract_pit_price_features(frame, events, calendar, row["as_of_date"], source=SOURCE)
        features = dict(row["features"])
        actual_vector, expected_vector = features.pop("vector"), expected.pop("vector")
        if features != expected:
            raise ValueError("Feature coverage/reason khác primitive PIT: " + row["episode_id"])
        if expected_vector is None:
            if actual_vector is not None:
                raise ValueError("Feature missing bị điền vector")
        elif actual_vector is None or not np.allclose(actual_vector, expected_vector, rtol=0, atol=1e-12):
            raise ValueError("Bốn feature khác primitive PIT: " + row["episode_id"])
        reasons = []
        info = coverage[symbol]
        holding = calendar[indices[1]:indices[2]+1]
        if len(holding.difference(info["dates"])):
            reasons.append("MISSING_EXECUTION_SESSION")
        if info["volume"].reindex(holding).eq(0).any():
            reasons.append("NO_MATCHED_VOLUME_AT_EXECUTION")
        if ((info["barriers"] > dates[1]) & (info["barriers"] <= dates[2])).any():
            reasons.append("CORPORATE_ACTION_DURING_HOLDING")
        if indices[0]//63 != indices[2]//63:
            reasons.append("CROSS_BLOCK_HOLDING")
        query_split, exit_split = partition(row["as_of_date"]), partition(row["exit_date"])
        split = query_split if query_split == exit_split else None
        if split is None:
            reasons.append("PURGED_SPLIT_BOUNDARY")
        combined = [*expected["reasons"], *reasons]
        if (row["label_reasons"] != reasons or row["label_status"] != ("UNAVAILABLE" if reasons else "AVAILABLE")
                or row["split"] != split or row["query_split"] != query_split or row["reasons"] != combined
                or row["status"] != ("EXCLUDED" if combined else "AVAILABLE")):
            raise ValueError("Trạng thái/reason không khớp giá/block/split")
        if reasons:
            if row["outcome"] is not None:
                raise ValueError("Cycle bị loại vẫn có outcome")
        else:
            entry, close = execution_prices_for_cycle(frame, events, *[row[k] for k in ("as_of_date", "entry_date", "exit_date")])
            expected_net = compute_round_trip_net_return(entry, close)
            if row["outcome"] != {"entry_open": entry, "exit_close": close, "r_net": expected_net, "y": int(expected_net > 0)}:
                raise ValueError("Nhãn khác helper engine")
            label_count += 1
    return {"features_checked_against_primitive": len(ids), "labels_checked_against_engine": label_count,
            "tolerance_feature_absolute": 1e-12, "status": "PASS"}


def prepare(root: Path = ROOT) -> dict[str, Any]:
    """Dựng lại artifact từ giá/evidence, không tin hash tự ghi trong bank có sẵn."""
    protocol = read_protocol(root)
    verify_protocol(root)
    prices = {symbol: load_verified_execution_data(root / "data/execution_prices", symbol) for symbol in SYMBOLS}
    calendar = pd.DatetimeIndex(pd.read_csv(root / "data/historical/VNINDEX.csv", usecols=["Datetime"], parse_dates=["Datetime"])["Datetime"])
    bank = build_dense_bank(prices, calendar)
    verification = verify_records(bank, prices)
    frozen = fit_scaler(bank, "2021-01-01")
    prefix_audit = []
    train_queries = sorted({row["as_of_date"] for row in bank["records"] if row["split"] == "train" and row["status"] == "AVAILABLE"})
    for query in train_queries:
        scaler = fit_scaler(bank, query)
        prefix_audit.append({"as_of_date": query, "fit_count": scaler["fit_count"],
                             "fit_max_exit_date": scaler["fit_max_exit_date"], "fit_ids_sha256": scaler["fit_ids_sha256"],
                             "scaler_sha256": content_hash(scaler), "status": scaler["status"], "reasons": scaler["reasons"]})
    unavailable = set(row["as_of_date"] for row in prefix_audit if row["status"] == "UNAVAILABLE")
    scaler_missing = Counter(row["symbol"] for row in bank["records"] if row["status"] == "AVAILABLE" and row["as_of_date"] in unavailable)
    for row in bank["records"]:
        if row["status"] == "AVAILABLE" and row["split"] != "train":
            transform_features(row["features"], frozen)
    manifest = read_json(root / "data/execution_prices/manifest.json")
    sources = {"data/execution_prices/manifest.json": protocol["price_manifest_sha256"]["data/execution_prices"],
               "data/historical/VNINDEX.csv": hashlib.sha256((root / "data/historical/VNINDEX.csv").read_bytes()).hexdigest()}
    for item in manifest["files"].values():
        for key in ("csv", "evidence", "events"):
            proof = item[key]
            sources["data/execution_prices/"+proof["file"]] = proof["sha256"]
    bank.update(frozen_scaler=frozen, prefix_scaler_audit=prefix_audit,
                prefix_scaler_unavailable_train_cycles={symbol: int(scaler_missing[symbol]) for symbol in SYMBOLS},
                verification=verification,
                identity={"protocol_sha256": PROTOCOL_SHA256, "sources_sha256": sources,
                          "code_sha256": {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in CODE},
                          "runtime": {"python": platform.python_version(), "numpy": version("numpy"), "pandas": version("pandas")}},
                scope="PRICE_FEATURE_LABEL_SCALER_ONLY_NO_REGIME_TASK_RETRIEVAL_OR_TRAIN_RELEASE")
    return bank


def main() -> None:
    """Tạo mới một artifact trong namespace riêng hoặc cold-rebuild để kiểm toàn bộ."""
    parser = argparse.ArgumentParser(description="Dựng/kiểm dense bank MT-BICL offline đến hết 2022")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(NAMESPACE.resolve()) or output.suffix != ".json" or output.name.startswith("."):
        parser.error("Output phải là JSON trong namespace mt_bicl, không ghi vào bằng chứng cũ")
    if not args.check and output.exists():
        parser.error("Không ghi đè artifact; chọn đường dẫn mới hoặc --check")
    payload = prepare()
    envelope = {"payload": payload, "sha256": content_hash(payload)}
    if args.check:
        if read_json(output) != envelope:
            raise ValueError("Artifact không khớp cold-rebuild từ nguồn; self-seal không thay verification")
    else:
        atomic_write_json(output, envelope)
    summary = payload["summary"]
    print(f"Bank/feature/label/scaler đã kiểm: {summary['available']}/{summary['candidates']} cycle; "
          f"support={summary['minimum_support_status']}; chưa release train/Decision.")


if __name__ == "__main__":
    main()
