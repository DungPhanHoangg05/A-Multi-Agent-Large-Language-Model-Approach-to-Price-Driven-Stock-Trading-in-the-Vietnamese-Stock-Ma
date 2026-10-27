"""Dựng task/context và audit coverage MT-BICL offline; không train hoặc gọi LLM."""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
from pathlib import Path
import sys
from typing import Any

import pandas as pd
import numpy as np
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.bayesian_memory import atomic_write_json, read_json
from core.execution_prices import execution_prices_for_cycle, load_verified_execution_data
from core.backtest_engine import compute_round_trip_net_return
from core.mt_bicl_bank import SOURCE, SYMBOLS, content_hash, read_protocol
from core.mt_bicl_context import pack_episode, project_episode
from core.mt_bicl_regimes import RegimeTimeline
from core.mt_bicl_stream import MarketStream
from core.mt_bicl_tasks import TaskBuilder, validate_episode
from core.pit_price_features import extract_pit_price_features
from scripts.build_mt_bicl_bank import DEFAULT_OUTPUT as BANK_PATH, NAMESPACE, prepare as prepare_bank

DEFAULT_OUTPUT = NAMESPACE / "inputs/task_context_v1.json"
CODE = ("core/mt_bicl_regimes.py", "core/mt_bicl_stream.py", "core/mt_bicl_tasks.py",
        "core/mt_bicl_context.py", "scripts/build_mt_bicl_tasks.py")


def _compact(episode: dict[str, Any], scalers: dict[str, Any]) -> dict[str, Any]:
    """Dedupe scaler theo hash để artifact không lặp hàng trăm tập fit ID."""
    result = deepcopy(episode)
    scaler = result.pop("scaler")
    key = content_hash(scaler)
    scalers.setdefault(key, scaler)
    result["scaler_sha256"] = key
    return result


def coverage(rows: list[dict[str, Any]], *, development: bool = False) -> dict[str, Any]:
    """Giữ mọi point và nhóm missing; không dùng coverage để suy hiệu quả dự báo."""
    groups = {}
    for symbol in SYMBOLS:
        group = [row for row in rows if row["query"]["symbol"] == symbol]
        groups[symbol] = {"count": len(group), "available": sum(row["status"] == "AVAILABLE" for row in group),
            "both_K2_m2": sum(row["status"] == "AVAILABLE" and row["K"] >= 2 and row["m"] >= 2 for row in group),
            "K_histogram": dict(sorted(Counter(str(row["K"]) for row in group).items())),
            "m_histogram": dict(sorted(Counter(str(row["m"]) for row in group).items())),
            "reasons": dict(sorted(Counter(reason for row in group for reason in row["reasons"]).items()))}
    total = sum(g["both_K2_m2"] for g in groups.values())
    strata = {}
    for row in rows:
        query = row["query"]
        quarter = (int(query["as_of_date"][5:7])-1)//3+1
        key = f"{query['symbol']}:{query['regime']['name']}:{query['as_of_date'][:4]}Q{quarter}"
        counts = strata.setdefault(key, {"count": 0, "available": 0, "both_K2_m2": 0})
        counts["count"] += 1
        counts["available"] += int(row["status"] == "AVAILABLE")
        counts["both_K2_m2"] += int(row["status"] == "AVAILABLE" and row["K"] >= 2 and row["m"] >= 2)
    gate = ("PASS" if len(rows) == 60 and total >= 30 and all(g["both_K2_m2"] >= 5 for g in groups.values())
            else "INSUFFICIENT_CONTEXT") if development else "NOT_APPLICABLE"
    return {"symbols": groups, "both_K2_m2": total, "development_support_gate": gate,
            "symbol_regime_quarter": dict(sorted(strata.items()))}


def verify_stream(stream: MarketStream, prices: dict[str, Any]) -> dict[str, Any]:
    """Đối chiếu x/y nối sau bank gốc bằng primitive và giá thực thi thực, không self-seal."""
    checked_features = checked_labels = 0
    for row in stream.closed_records():
        if row["as_of_date"] < "2022-12-30":
            continue
        frame, events = prices[row["symbol"]]
        expected = extract_pit_price_features(frame, events, stream.calendar, row["as_of_date"], source=SOURCE)
        actual = deepcopy(row["features"])
        av, ev = actual.pop("vector"), expected.pop("vector")
        if (actual != expected or ((av is None) != (ev is None))
                or (ev is not None and not np.allclose(av, ev, rtol=0, atol=1e-12))):
            raise ValueError("Stream feature khác primitive PIT")
        checked_features += 1
        if row["outcome"] is not None:
            entry, close = execution_prices_for_cycle(frame, events, row["as_of_date"], row["entry_date"], row["exit_date"])
            net = compute_round_trip_net_return(entry, close)
            if row["outcome"] != {"entry_open": entry, "exit_close": close, "r_net": net, "y": int(net > 0)}:
                raise ValueError("Stream label khác helper engine")
            checked_labels += 1
    return {"status": "PASS", "new_stream_features": checked_features, "new_stream_labels": checked_labels}


def prepare(root: Path = ROOT) -> dict[str, Any]:
    """Cold-verify bank trước dựng episodes, metadata HMM và projection trên nguồn thật."""
    protocol = read_protocol(root)
    bank = prepare_bank(root)
    source_bank = read_json(root / BANK_PATH.relative_to(ROOT))
    if source_bank != {"payload": bank, "sha256": content_hash(bank)}:
        raise ValueError("Bank W10-03 khác cold-rebuild; không tự rehash để nhận nguồn")
    calendar_frame = pd.read_csv(root / "data/historical/VNINDEX.csv", parse_dates=["Datetime"])
    prices = {symbol: load_verified_execution_data(root / "data/execution_prices_oos", symbol) for symbol in SYMBOLS}
    # Model cache dùng cùng thread limit ở mọi cold-rebuild, không đổi HMM parameters.
    with threadpool_limits(limits=1):
        regimes = RegimeTimeline(calendar_frame)
        stream = MarketStream(bank, prices, pd.DatetimeIndex(calendar_frame["Datetime"]))
        builder = TaskBuilder(bank, stream, regimes)
        scalers: dict[str, Any] = {}
        episodes = []
        diagnostics = []
        for row in bank["records"]:
            if row["status"] != "AVAILABLE":
                continue
            episode = builder.build(row["symbol"], row["as_of_date"])
            validate_episode(episode)
            compact = _compact(episode, scalers)
            compact["split"] = row["split"]
            # Nhãn query chỉ ở phần supervised bên ngoài input, sau khi đã dựng context.
            compact["supervised_target"] = deepcopy(row["outcome"])
            if episode["status"] == "AVAILABLE":
                packed = pack_episode(episode, training_query_y=row["outcome"]["y"])
                compact["packed"] = packed
                compact["projection_fixture"] = project_episode(episode)
            episodes.append(compact)
            diagnostics.append(episode)
        development = []
        points = sorted((date, SYMBOLS.index(symbol), symbol) for symbol, dates in protocol["development"]["symbol_cutoffs"].items() for date in dates)
        for date, _, symbol in points:
            episode = builder.build(symbol, date)
            validate_episode(episode)
            compact = _compact(episode, scalers)
            compact["split"] = "development"
            if episode["status"] == "AVAILABLE":
                compact["packed"] = pack_episode(episode)
                compact["projection_fixture"] = project_episode(episode)
            development.append(compact)
        task_metadata = {f"{symbol}:block{block:04d}": regimes.task(block)
                         for symbol in SYMBOLS for block in range(1+max(e["query"]["block_index"] for e in [*episodes, *development]))}
        # Xuất lại sau metadata cuối để không bỏ sót model có thể vừa được tạo.
        models = regimes.artifacts()
        verification = verify_stream(stream, prices)
    max_prefix = max(row["projection_fixture"]["prefix_chars"] for row in [*episodes, *development] if "projection_fixture" in row)
    by_split = {split: coverage([e for e in diagnostics if protocol["splits"][split][0] <= e["query"]["as_of_date"] <= protocol["splits"][split][1]])
                for split in ("train", "checkpoint_selection", "validation")}
    return {"version": "mt_bicl_task_context_v1", "protocol_sha256": bank["protocol_sha256"],
            "bank_payload_sha256": content_hash(bank), "scalers": scalers, "regime_models": models,
            "task_metadata": task_metadata, "episodes": episodes, "development": development,
            "coverage": {"bank_partitions": by_split, "development": coverage(development, development=True)},
            "stream_audit": stream.audit, "max_fixture_prefix_chars": max_prefix,
            "stream_verification": verification,
            "identity": {"code_sha256": {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in CODE},
                         "raw_oos_manifest_sha256": protocol["price_manifest_sha256"]["data/execution_prices_oos"],
                         "regime_cpu_thread_limit": 1},
            "training_allowed": False, "decision_calls_allowed": False,
            "probability_scope": "PROJECTION_FIXTURE_P_NA_NO_LEARNER_INFERENCE"}


def main() -> None:
    """Tạo artifact mới hoặc kiểm lại toàn bộ bằng cold-rebuild, không cờ API/train."""
    parser = argparse.ArgumentParser(description="Dựng/kiểm task context MT-BICL offline")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(NAMESPACE.resolve()) or output.suffix != ".json" or output.name.startswith("."):
        parser.error("Output phải trong namespace mt_bicl_v1")
    if not args.check and output.exists():
        parser.error("Không ghi đè artifact đã lưu")
    payload = prepare()
    result = {"payload": payload, "sha256": content_hash(payload)}
    if args.check:
        if read_json(output) != result:
            raise ValueError("Task/context khác cold-rebuild từ nguồn")
    else:
        atomic_write_json(output, result)
    summary = payload["coverage"]["development"]
    print(f"Task/context đã kiểm: {len(payload['episodes'])} bank query, 60 development; "
          f"K>=2,m>=2: {summary['both_K2_m2']}/60, support={summary['development_support_gate']}; chưa train/LLM.")


if __name__ == "__main__":
    main()
