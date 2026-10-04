"""Xác minh run và phát hành Memory Bank hoàn chỉnh cùng biên bản provenance."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import shutil
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.bayesian_memory import HistoricalMemory, SYMBOLS, atomic_write_json, exact_object, read_json
from core.historical_runner import HistoricalMemoryRunner
from core.historical_signals import digest, disk_articles
from scripts.run_paced_historical_memory import REPORT_PARSE_FILE


def freeze_report_compat(run_dir: Path, target: Path) -> dict[str, Any] | None:
    """Đóng băng biên bản và mã bộ đọc viết tắt đã dùng cho run."""
    path = run_dir / REPORT_PARSE_FILE
    if not path.exists():
        return None
    envelope = read_json(path)
    exact_object(envelope, {"payload", "sha256"})
    payload = envelope["payload"]
    exact_object(payload, {"format_version", "entries"})
    if payload["format_version"] != 1 or type(payload["entries"]) is not list or digest(payload) != envelope["sha256"]:
        raise ValueError("Biên bản bộ đọc tương thích sai checksum hoặc phiên bản")
    sources = {}
    for entry in payload["entries"]:
        exact_object(entry, {"report_sha256", "signal", "parser_sha256", "rule"})
        checksum = entry["parser_sha256"]
        if (type(checksum) is not str or len(checksum) != 64 or any(c not in "0123456789abcdef" for c in checksum)
                or entry["rule"] != "abbreviated_trend_direction_v1"
                or entry["signal"] not in {"BULLISH", "BEARISH", "NEUTRAL"}):
            raise ValueError("Biên bản bộ đọc có quy tắc hoặc checksum không hợp lệ")
        destination = run_dir / "inputs" / "compat" / f"{checksum}.py"
        source = destination if destination.exists() else Path(__file__).with_name("run_paced_historical_memory.py")
        if hashlib.sha256(source.read_bytes()).hexdigest() != checksum:
            raise ValueError("Không tìm thấy đúng mã bộ đọc đã dùng trong run")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source != destination:
            shutil.copyfile(source, destination)
        sources[checksum] = destination.relative_to(run_dir).as_posix()
    published = target.with_suffix(".parse_compat.json")
    if published.exists() and read_json(published) != envelope:
        raise ValueError("Biên bản bộ đọc đích khác nội dung; từ chối ghi đè")
    atomic_write_json(published, envelope)
    return {"file": published.name, "sha256": hashlib.sha256(published.read_bytes()).hexdigest(),
            "parser_sources": sources, "entries": len(payload["entries"])}


def frozen_articles(run_dir: Path, identity: dict[str, Any], symbol: str) -> list[dict[str, Any]]:
    """Đọc archive đã đóng băng hoặc cache gốc, luôn so hash đầu vào của run."""
    path = run_dir / "inputs" / "news" / f"{symbol}.json"
    if path.exists():
        payload = read_json(path)
        if (type(payload) is not dict or set(payload) != {"symbol", "scored_articles"}
                or payload["symbol"] != symbol or type(payload["scored_articles"]) is not list):
            raise ValueError("Archive tin đóng băng sai cấu trúc hoặc mã")
        articles = payload["scored_articles"]
    else:
        articles = disk_articles(ROOT, symbol)
    if digest(articles) != identity["data"][symbol]["news"]:
        raise ValueError("Archive tin không khớp đầu vào đã đóng băng của run")
    return articles


def publish(run_dir: Path, target: Path, *, require_complete: bool = False) -> dict[str, Any]:
    """Chỉ phát hành hơn 300 record đã xác minh trên đủ bốn mã; không ghi đè kho khác."""
    manifest_path = run_dir / "run_manifest.json"
    identity = HistoricalMemoryRunner._read_envelope(manifest_path)
    runner = HistoricalMemoryRunner(run_dir, symbols=tuple(identity["symbols"]),
                                    start=identity["start"], end=identity["end"], model_config=identity["models"],
                                    article_loader=lambda symbol: frozen_articles(run_dir, identity, symbol))
    status = runner.run(verify_only=True)
    if status["completed"] <= 300 or (require_complete and status["remaining"] != 0):
        raise ValueError("Kho chưa đủ hơn 300 episode hoặc run chưa hoàn tất theo yêu cầu")
    records = read_json(run_dir / "memory.json")
    if {record["symbol"] for record in records} != SYMBOLS:
        raise ValueError("Kho phải có đủ bốn mã nghiên cứu")
    memory = HistoricalMemory()
    memory.load(run_dir / "memory.json")
    if target.exists() and read_json(target) != records:
        raise ValueError("Kho đích đã có nội dung khác; từ chối ghi đè")
    reliable_news = Counter()
    for record in records:
        bundle_path = run_dir / "signals" / f"{record['symbol']}-{record['as_of_date']}.json"
        bundle = HistoricalMemoryRunner._read_envelope(bundle_path)["result"]
        if bundle["provenance"]["news_is_reliable"]:
            reliable_news[record["symbol"]] += 1
    frozen_news = {}
    for symbol in sorted(SYMBOLS):
        articles = frozen_articles(run_dir, identity, symbol)
        path = run_dir / "inputs" / "news" / f"{symbol}.json"
        atomic_write_json(path, {"symbol": symbol, "scored_articles": articles})
        frozen_news[symbol] = {"file": f"inputs/news/{symbol}.json",
                               "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    try:
        run_location = run_dir.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        run_location = run_dir.resolve().as_posix()
    compat = freeze_report_compat(run_dir, target)
    memory.save(target)
    receipt = {
        "format_version": 1, "run_dir": run_location,
        "run_signature": digest(identity), "records_sha256": digest(records),
        "bank_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "completed": len(records), "remaining": status["remaining"],
        "by_symbol": dict(sorted(Counter(record["symbol"] for record in records).items())),
        "by_regime": dict(sorted(Counter(record["regime"] for record in records).items())),
        "by_year": dict(sorted(Counter(record["as_of_date"][:4] for record in records).items())),
        "first_as_of_date": min(record["as_of_date"] for record in records),
        "last_exit_date": max(record["exit_date"] for record in records),
        "reliable_sentiment_by_symbol": {symbol: int(reliable_news[symbol]) for symbol in sorted(SYMBOLS)},
        "models": identity["models"], "frozen_news": frozen_news,
        "report_parse_compat": compat,
    }
    atomic_write_json(target.with_suffix(".manifest.json"), receipt)
    return receipt


def main() -> None:
    """Phát hành từ run đã đóng băng; không gọi API LLM hoặc sinh thêm episode."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=ROOT / "outputs/historical_memory_run")
    parser.add_argument("--target", type=Path, default=ROOT / "data_manager/regime_memory_store.json")
    parser.add_argument("--require-complete", action="store_true", help="Yêu cầu tạo xong toàn bộ lịch hợp lệ")
    args = parser.parse_args()
    receipt = publish(args.run_dir, args.target, require_complete=args.require_complete)
    print(f"Đã phát hành {receipt['completed']} episode; còn {receipt['remaining']} điểm trong lịch")


if __name__ == "__main__":
    main()
