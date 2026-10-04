"""Kiểm tra đầu vào W3 và khả năng tái dùng kho lịch sử; không chạy retriever."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
from pathlib import Path
import platform
from statistics import median
import sys
from time import perf_counter
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.bayesian_memory import HistoricalMemory, atomic_write_json, read_json
from core.execution_prices import load_verified_execution_data


def verify() -> dict[str, Any]:
    """Đối chiếu bằng chứng và kiểm cutoff/bản sao/I/O trên kho chính thức."""
    bank_path = ROOT / "data_manager/regime_memory_store.json"
    manifest = read_json(bank_path.with_suffix(".manifest.json"))
    qa = read_json(ROOT / "docs/week2/memory_bank_audit.json")
    bank_hash = hashlib.sha256(bank_path.read_bytes()).hexdigest()
    schema_hash = hashlib.sha256((ROOT / "docs/plan/week1/historical_task_record.schema.json").read_bytes()).hexdigest()
    if qa["status"] != "PASS" or bank_hash != qa["bank_sha256"] or bank_hash != manifest["bank_sha256"]:
        raise ValueError("Kho chưa có manifest/QA PASS khớp checksum")
    if schema_hash != qa["schema_sha256"] or qa["run_signature"] != manifest["run_signature"]:
        raise ValueError("Schema hoặc signature không khớp biên bản QA")
    calls: Counter[str] = Counter()

    def loader(symbol: str) -> Any:
        """Đếm lần nạp/xác minh giá của từng mã trong cold load."""
        calls[symbol] += 1
        return load_verified_execution_data(ROOT / "data/execution_prices", symbol)

    memory = HistoricalMemory(execution_loader=loader)
    started = perf_counter()
    memory.load(bank_path)
    load_ms = (perf_counter() - started) * 1000.0
    records = memory.records
    original = read_json(bank_path)
    if len(records) != 852 or manifest["completed"] != len(records) or qa["completed"] != len(records):
        raise ValueError("Số record khác kho đã chốt 852 episode")
    coverage = {"by_symbol": dict(sorted(Counter(r["symbol"] for r in records).items())),
                "by_regime": dict(sorted(Counter(r["regime"] for r in records).items())),
                "by_year": dict(sorted(Counter(r["as_of_date"][:4] for r in records).items()))}
    for key, counts in coverage.items():
        if counts != manifest[key] or any(qa[key].get(name) != count for name, count in counts.items()):
            raise ValueError("Độ phủ khác manifest/QA")
    if dict(calls) != {symbol: 1 for symbol in coverage["by_symbol"]}:
        raise ValueError("Cold load không nạp đúng một lần giá mỗi mã")
    counts_after_load = dict(calls)
    timings: list[float] = []
    boundary = min(r["exit_date"] for r in records)
    checks: dict[str, bool] = {}
    # Chặn đọc JSON và giá: truy vấn phải chỉ dùng kho đã xác minh trong RAM.
    with patch("core.bayesian_memory.read_json", side_effect=AssertionError("Query đọc JSON")), \
         patch.object(memory, "_execution_loader", side_effect=AssertionError("Query đọc giá")):
        checks["first_exit_excluded"] = memory.eligible(boundary) == []
        checks["empty_before_first_episode"] = memory.eligible("2018-01-01") == []
        for cutoff in (boundary, "2021-01-04", "2022-12-30", "2023-01-03"):
            selected = memory.eligible(cutoff)
            expected = [r["episode_id"] for r in records if r["exit_date"] < cutoff]
            if [r["episode_id"] for r in selected] != expected:
                raise ValueError("eligible không khớp cutoff nghiêm ngặt")
        checks["strict_exit_cutoff"] = True
        selected = memory.eligible("2023-01-03", "FPT")
        if len(selected) != coverage["by_symbol"]["FPT"] or any(r["symbol"] != "FPT" for r in selected):
            raise ValueError("Bộ lọc mã không khớp kho")
        selected[0]["agent_signals"]["trend"] = "ĐÃ SỬA BẢN SAO"
        records[0]["agent_signals"]["trend"] = "ĐÃ SỬA BẢN SAO"
        fresh = memory.records
        if fresh != original:
            raise ValueError("Người gọi làm thay đổi kho đã xác minh")
        checks["records_and_eligible_deep_copy"] = True
        for _ in range(100):
            started = perf_counter()
            memory.eligible("2023-01-03", "FPT")
            timings.append((perf_counter() - started) * 1000.0)
    checks["no_query_json_or_price_io"] = dict(calls) == counts_after_load
    if not all(checks.values()):
        raise ValueError("Kiểm tra đầu vào hoặc API kho thất bại")
    sentiments = dict(sorted(Counter(r["agent_signals"]["sentiment"] for r in fresh).items()))
    return {"format_version": 1, "status": "PASS", "bank_sha256": bank_hash,
            "schema_sha256": schema_hash, "run_signature": manifest["run_signature"],
            "verifier_text_sha256": hashlib.sha256(Path(__file__).read_text(encoding="utf-8").encode("utf-8")).hexdigest(),
            "records": len(fresh), **coverage, "sentiment_counts": sentiments,
            "first_as_of_date": min(r["as_of_date"] for r in fresh),
            "last_exit_date": max(r["exit_date"] for r in fresh), "boundary_exit_date": boundary,
            "execution_loader_calls": counts_after_load, "checks": checks,
            "timing": {"python": platform.python_version(), "cold_load_ms": load_ms,
                       "eligible_same_symbol_median_ms": median(timings), "query_samples": len(timings),
                       "measurement": "Khảo sát load/eligible, không phải benchmark retriever bốn mode W3-14"}}


def main() -> None:
    """Xuất biên bản đầu vào; không sửa kho/model hoặc gọi LLM."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/week3/input_readiness.json")
    args = parser.parse_args()
    result = verify()
    atomic_write_json(args.output, result)
    print(f"Đầu vào W3 PASS: {result['records']} episode; biên bản {args.output}")


if __name__ == "__main__":
    main()
