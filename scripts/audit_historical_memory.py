"""Kiểm toán kho đã phát hành bằng journal, giá thô, báo cáo agent và lịch cố định."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import math
from pathlib import Path
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.bayesian_memory import HistoricalMemory, SYMBOLS, atomic_write_json, read_json
from core.historical_runner import HistoricalMemoryRunner
from core.historical_signals import digest, report_signal
from scripts.publish_historical_memory import frozen_articles
from scripts.run_paced_historical_memory import make_compatible_report_parser


def validate_native(value: Any) -> None:
    """Từ chối scalar NumPy, số không hữu hạn hoặc kiểu không thuộc JSON gốc."""
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise ValueError("JSON có khóa không phải chuỗi Python gốc")
        for child in value.values():
            validate_native(child)
    elif type(value) is list:
        for child in value:
            validate_native(child)
    elif type(value) is float:
        if not math.isfinite(value):
            raise ValueError("JSON có số không hữu hạn")
    elif value is not None and type(value) not in (str, bool, int):
        raise ValueError("JSON có kiểu không thuộc Python gốc")


def summarize_records(records: list[dict[str, Any]], points: list[dict[str, str]]) -> dict[str, Any]:
    """Đối chiếu toàn bộ lịch và nhãn kinh tế trước khi thống kê độ phủ."""
    validate_native(records)
    if type(records) is not list or len(records) <= 300:
        raise ValueError("Kho phải có hơn 300 record và đủ bốn mã")
    if {r["symbol"] for r in records} != SYMBOLS:
        raise ValueError("Kho phải có hơn 300 record và đủ bốn mã")
    memory = HistoricalMemory()
    memory._validate_all(records)
    expected = [(p["symbol"], p["as_of_date"], p["entry_date"], p["exit_date"]) for p in points]
    observed = [(r["symbol"], r["as_of_date"], r["entry_date"], r["exit_date"]) for r in records]
    if observed != expected:
        raise ValueError("Kho không khớp toàn bộ lịch hợp lệ đã chốt")
    if any(not "2018-01-01" <= r["as_of_date"] < r["exit_date"] <= "2022-12-31" for r in records):
        raise ValueError("Kho có chu kỳ ngoài giai đoạn nghiên cứu")
    net = [float(r["outcome"]["net_return_pct"]) for r in records]
    return {
        "completed": len(records),
        "by_symbol": dict(sorted(Counter(r["symbol"] for r in records).items())),
        "by_regime": dict(sorted(Counter(r["regime"] for r in records).items())),
        "by_year": {str(year): sum(r["as_of_date"].startswith(str(year)) for r in records)
                    for year in range(2018, 2023)},
        "by_symbol_year": {symbol: {str(year): sum(r["symbol"] == symbol and
            r["as_of_date"].startswith(str(year)) for r in records) for year in range(2018, 2023)}
            for symbol in sorted(SYMBOLS)},
        "by_symbol_regime": {symbol: {regime: sum(r["symbol"] == symbol and r["regime"] == regime
            for r in records) for regime in ("BULL", "BEAR", "CHOPPY", "CONSOLIDATION")}
            for symbol in sorted(SYMBOLS)},
        "first_as_of_date": min(r["as_of_date"] for r in records),
        "last_exit_date": max(r["exit_date"] for r in records),
        "economic_labels": dict(sorted(Counter(r["outcome"]["result"] for r in records).items())),
        "bull_traps": sum(r["outcome"]["was_bull_trap"] for r in records),
        "net_return_pct": {"minimum": min(net), "maximum": max(net), "mean": sum(net) / len(net)},
        "sentiment_labels": dict(sorted(Counter(r["agent_signals"]["sentiment"] for r in records).items())),
    }


def _audit(run_dir: Path, bank: Path) -> dict[str, Any]:
    """Xác minh kho và manifest; báo cáo không gọi API hoặc sửa staging."""
    identity = HistoricalMemoryRunner._read_envelope(run_dir / "run_manifest.json")
    runner = HistoricalMemoryRunner(run_dir, symbols=tuple(identity["symbols"]), start=identity["start"],
        end=identity["end"], model_config=identity["models"],
        article_loader=lambda symbol: frozen_articles(run_dir, identity, symbol))
    status = runner.run(verify_only=True)
    if status["remaining"] != 0:
        raise ValueError("Run chưa hoàn tất toàn bộ lịch")
    records = read_json(bank)
    if records != read_json(run_dir / "memory.json"):
        raise ValueError("Kho phát hành khác staging đã xác minh")
    plan = runner.plan()
    summary = summarize_records(records, plan["points"])
    receipt = read_json(bank.with_suffix(".manifest.json"))
    if (receipt["bank_sha256"] != hashlib.sha256(bank.read_bytes()).hexdigest()
            or receipt["records_sha256"] != digest(records) or receipt["run_signature"] != digest(identity)
            or receipt["completed"] != summary["completed"] or receipt["remaining"] != 0):
        raise ValueError("Manifest phát hành không khớp kho hoặc run")
    for key in ("by_symbol", "by_regime"):
        if receipt[key] != summary[key]:
            raise ValueError("Thống kê manifest không khớp kho")
    if receipt["by_year"] != {key: count for key, count in summary["by_year"].items() if count}:
        raise ValueError("Độ phủ năm trong manifest sai")
    if set(receipt["frozen_news"]) != SYMBOLS:
        raise ValueError("Manifest thiếu archive tin của mã nghiên cứu")
    for symbol, info in receipt["frozen_news"].items():
        path = run_dir / "inputs" / "news" / f"{symbol}.json"
        if info["sha256"] != hashlib.sha256(path.read_bytes()).hexdigest():
            raise ValueError("Archive tin sai checksum")
        frozen_articles(run_dir, identity, symbol)
    compat = receipt.get("report_parse_compat")
    entries = []
    if compat is not None:
        path = bank.with_suffix(".parse_compat.json")
        if compat["sha256"] != hashlib.sha256(path.read_bytes()).hexdigest():
            raise ValueError("Biên bản bộ đọc đã phát hành sai checksum")
        payload = HistoricalMemoryRunner._read_envelope(path)
        entries = payload["entries"]
        if (payload != HistoricalMemoryRunner._read_envelope(run_dir / "report_parse_compat.json")
                or len(entries) != compat["entries"]):
            raise ValueError("Biên bản bộ đọc phát hành khác staging")
        for checksum, location in compat["parser_sources"].items():
            expected = f"inputs/compat/{checksum}.py"
            if location != expected or hashlib.sha256((run_dir / expected).read_bytes()).hexdigest() != checksum:
                raise ValueError("Mã bộ đọc đóng băng sai đường dẫn hoặc checksum")
    used = set()
    reliable = Counter()
    with tempfile.TemporaryDirectory() as directory:
        parse = make_compatible_report_parser(Path(directory))
        for record in records:
            path = run_dir / "signals" / f"{record['symbol']}-{record['as_of_date']}.json"
            bundle = HistoricalMemoryRunner._read_envelope(path)["result"]
            reports = bundle["reports"]
            for agent, field, labels in (
                ("trend", "trend_report", ("Hướng xu hướng", "Trend direction")),
                ("pattern", "pattern_report", ("Thiên lệch dự báo", "Directional bias")),
                ("indicator_consensus", "indicator_report", ("Đồng thuận chủ đạo", "Dominant consensus")),
            ):
                try:
                    signal = report_signal(reports[field], labels)
                except ValueError:
                    signal = parse(reports[field], labels)
                    checksum = digest(reports[field])
                    evidence = [e for e in entries if e["report_sha256"] == checksum and e["signal"] == signal
                                and e["rule"] == "abbreviated_trend_direction_v1"
                                and e["parser_sha256"] in compat["parser_sources"]]
                    if not evidence:
                        raise ValueError("Tín hiệu viết tắt thiếu bằng chứng bộ đọc")
                    used.add(checksum)
                if signal != record["agent_signals"][agent]:
                    raise ValueError("Tín hiệu không khớp báo cáo agent đã lưu")
            if bundle["provenance"]["news_is_reliable"]:
                reliable[record["symbol"]] += 1
            elif record["agent_signals"]["sentiment"] != "NEUTRAL":
                raise ValueError("Tin không đáng tin cậy phải có nhãn sentiment NEUTRAL")
            factors = bundle["provenance"]["alpha_factors"]
            if len(factors) != 5 or len({factor["id"] for factor in factors}) != 5:
                raise ValueError("Provenance Alpha không có đủ năm factor khác nhau")
            directions = [factor["signal"] for factor in factors]
            if any(direction not in {"TĂNG", "GIẢM", "TRUNG TÍNH"} for direction in directions):
                raise ValueError("Provenance Alpha chứa nhãn không hợp lệ")
            up, down = directions.count("TĂNG"), directions.count("GIẢM")
            alpha = "BULLISH" if up > down else ("BEARISH" if down > up else "NEUTRAL")
            if record["agent_signals"]["alpha_consensus"] != alpha:
                raise ValueError("Đồng thuận Alpha không khớp năm factor đã lưu")
    if {e["report_sha256"] for e in entries} != used:
        raise ValueError("Biên bản bộ đọc chứa báo cáo ngoài kho")
    summary["reliable_sentiment_by_symbol"] = {symbol: int(reliable[symbol]) for symbol in sorted(SYMBOLS)}
    if receipt["reliable_sentiment_by_symbol"] != summary["reliable_sentiment_by_symbol"]:
        raise ValueError("Độ phủ tin trong manifest không khớp provenance")
    return {"status": "PASS", "format_version": 1, "bank_sha256": receipt["bank_sha256"],
        "run_signature": receipt["run_signature"], "schema_sha256": hashlib.sha256(
            (ROOT / "docs/plan/week1/historical_task_record.schema.json").read_bytes()).hexdigest(),
        "candidate_count": plan["candidate_count"], "excluded_count": len(plan["excluded"]),
        "compatible_trend_reports": len(used), **summary,
        "checks": ["schema_native_json", "unique_ids", "complete_schedule", "nonoverlap",
                   "execution_prices_and_net_labels", "regime_and_news_cutoff", "journal_and_report_checksums",
                   "signals_match_reports", "publication_manifest", "frozen_news", "compat_parser_evidence"],
        "limitations": ["600 phiên khởi động: không có episode 2018–2019; lịch quyết định bắt đầu 2020-06-01.",
                        "Thiếu tin lịch sử đáng tin cậy được ghi rõ; không diễn giải NEUTRAL thành tin thị trường trung tính.",
                        "QA này không mở gate giá thô kiểm định 2023–2024."]}


def audit(run_dir: Path, bank: Path) -> dict[str, Any]:
    """Đổi lỗi cấu trúc bằng chứng thành ValueError để dừng kiểm toán rõ ràng."""
    try:
        return _audit(run_dir, bank)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("Kho hoặc bằng chứng kiểm toán thiếu trường hoặc sai kiểu") from exc


def main() -> None:
    """Xuất biên bản JSON có thể tái lập; không sinh thêm episode."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=ROOT / "outputs/historical_memory_run")
    parser.add_argument("--bank", type=Path, default=ROOT / "data_manager/regime_memory_store.json")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/week2/memory_bank_audit.json")
    args = parser.parse_args()
    result = audit(args.run_dir, args.bank)
    atomic_write_json(args.output, result)
    print(f"Kiểm toán PASS: {result['completed']} episode; biên bản {args.output}")


if __name__ == "__main__":
    main()
