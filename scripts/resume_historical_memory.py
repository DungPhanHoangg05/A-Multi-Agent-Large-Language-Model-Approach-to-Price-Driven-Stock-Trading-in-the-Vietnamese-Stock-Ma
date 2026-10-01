"""Tiếp tục Memory Bank theo đợt đến khi hết lịch hoặc runner báo lỗi."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import math
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

from dotenv import dotenv_values

from core.bayesian_memory import atomic_write_json, exact_object, read_json
from core.historical_runner import HistoricalMemoryRunner
from core.historical_signals import digest
from scripts.run_paced_historical_memory import DEFAULT_LLM_GAP_SECONDS

RETRY_LINE = re.compile(r"Lời gọi LLM lỗi lần \d+/\d+; chờ (\d+(?:\.\d+)?) giây")
COOLDOWN_FILE = "api_cooldown.json"


def current_key(env_file: Path, inherited: dict[str, str]) -> str:
    """Ưu tiên key mới trong .env; không ghi nội dung key vào log hay artifact."""
    values = dotenv_values(env_file) if env_file.is_file() else {}
    key = values.get("GROQ_API_KEY") if "GROQ_API_KEY" in values else inherited.get("GROQ_API_KEY")
    if type(key) is not str or not key.strip():
        raise ValueError("Thiếu GROQ_API_KEY trong .env hoặc môi trường")
    return key.strip()


def completed_count(output_dir: Path) -> int:
    """Đếm episode đã xuất; runner con sẽ xác minh lại journal trước mỗi điểm."""
    path = output_dir / "memory.json"
    if not path.exists():
        return 0
    records = read_json(path)
    if type(records) is not list:
        raise ValueError("Kho staging không phải danh sách episode")
    return len(records)


def run_batch(command: list[str], env: dict[str, str]) -> tuple[int, float | None]:
    """Hiển thị log trực tiếp; dừng ngay ở lỗi LLM đầu tiên, không retry."""
    process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                               errors="replace", bufsize=1)
    try:
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="", flush=True)
            match = RETRY_LINE.search(line)
            if match:
                delay = float(match.group(1))
                if process.poll() is None:
                    process.terminate()
                process.wait()
                print(f"Lời gọi LLM thất bại; đã dừng trước khi retry/chờ {delay:.1f} giây. "
                      "Checkpoint dở dang cần được rà soát.")
                return process.returncode or 1, delay
        return process.wait(), None
    except BaseException:
        if process.poll() is None:
            process.terminate()
            process.wait()
        raise
    finally:
        if process.stdout is not None:
            process.stdout.close()


def check_cooldown(output_dir: Path, *, now: datetime | None = None) -> None:
    """Từ chối gọi API trước thời điểm retry dự kiến của lỗi trước."""
    path = output_dir / COOLDOWN_FILE
    if not path.exists():
        return
    payload = read_json(path)
    if type(payload) is not dict or set(payload) != {"observed_at_utc", "retry_after_seconds", "pause_until_utc"}:
        raise ValueError("Biên bản cooldown API sai cấu trúc")
    try:
        deadline = datetime.fromisoformat(payload["pause_until_utc"])
    except (TypeError, ValueError) as exc:
        raise ValueError("Mốc cooldown API không hợp lệ") from exc
    if deadline.tzinfo is None or type(payload["retry_after_seconds"]) is not float:
        raise ValueError("Mốc cooldown API thiếu múi giờ hoặc thời gian chờ")
    current = now or datetime.now(timezone.utc)
    remaining = (deadline - current).total_seconds()
    if remaining > 0:
        raise RuntimeError(f"Cooldown sau lỗi LLM còn {remaining:.0f} giây; chưa gọi LLM. "
                           f"Xem {path} để biết thời điểm thử lại")


def save_cooldown(output_dir: Path, retry_after_seconds: float) -> None:
    """Ghi thời điểm thử lại dự kiến để tránh lỗi API lặp tức thì."""
    observed = datetime.now(timezone.utc)
    atomic_write_json(output_dir / COOLDOWN_FILE, {
        "observed_at_utc": observed.isoformat(),
        "retry_after_seconds": float(retry_after_seconds),
        "pause_until_utc": (observed + timedelta(seconds=retry_after_seconds)).isoformat(),
    })


def archive_interrupted_point(output_dir: Path, point: dict[str, str], completed: int) -> list[Path]:
    """Lưu bằng chứng điểm bị ngắt sau khi tiến trình con đã dừng hoàn toàn."""
    symbol, cutoff = point["symbol"], point["as_of_date"]
    if not re.fullmatch(r"[A-Z0-9]+", symbol) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", cutoff):
        raise ValueError("Điểm tiếp theo có mã hoặc ngày không hợp lệ")
    name = f"{symbol}-{cutoff}"
    signal_dir = output_dir / "signals"
    checkpoint = signal_dir / f"{name}.json"
    point_lock = signal_dir / f"{name}.lock"
    run_lock = output_dir / "run.lock"
    if len(list((output_dir / "episodes").glob("*.json"))) != completed:
        raise ValueError("Journal và kho staging khác số episode; giữ nguyên khóa để rà soát")
    if (output_dir / "episodes" / f"{name}.json").exists():
        raise ValueError("Điểm dở dang đã có episode; giữ nguyên khóa để rà soát")
    other_locks = set(signal_dir.glob("*.lock")) - {point_lock}
    if other_locks or not checkpoint.exists():
        raise ValueError("Checkpoint/khóa điểm dở dang không đúng lịch; giữ nguyên để rà soát")
    envelope = read_json(checkpoint)
    exact_object(envelope, {"payload", "sha256"})
    payload = envelope["payload"]
    if type(payload) is not dict or digest(payload) != envelope["sha256"]:
        raise ValueError("Checkpoint dở dang sai checksum; giữ nguyên để rà soát")
    if type(payload.get("signature")) is not str or not re.fullmatch(r"[0-9a-f]{64}", payload["signature"]):
        raise ValueError("Chữ ký checkpoint dở dang không hợp lệ; giữ nguyên để rà soát")
    stage = payload.get("stage")
    if type(stage) is not str or stage not in {"UPSTREAM_STARTED", "UPSTREAM_COMPLETE", "COMPLETE"}:
        raise ValueError("Stage checkpoint không hợp lệ; giữ nguyên để rà soát")
    sources = [path for path in (run_lock, point_lock) if path.exists()]
    if stage == "UPSTREAM_STARTED":
        sources.append(checkpoint)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destinations = [path.with_name(f"{path.name}.interrupted-{stamp}") for path in sources]
    if any(path.exists() for path in destinations):
        raise ValueError("Đích lưu bằng chứng đã tồn tại; giữ nguyên khóa")
    for source, destination in zip(sources, destinations):
        source.rename(destination)
    return destinations


def resume(output_dir: Path, *, batch_size: int = 8, env_file: Path = ROOT / ".env",
           llm_gap_seconds: float = DEFAULT_LLM_GAP_SECONDS) -> dict[str, int]:
    """Chạy hết lịch hoặc dừng ở lỗi đầu tiên; key mới có hiệu lực giữa hai đợt."""
    output_dir = output_dir.resolve()
    env_file = env_file.resolve()
    if type(batch_size) is not int or batch_size < 1:
        raise ValueError("Số điểm mỗi đợt phải là số nguyên dương")
    if isinstance(llm_gap_seconds, bool) or not isinstance(llm_gap_seconds, (int, float)) \
            or not math.isfinite(llm_gap_seconds) or llm_gap_seconds < 0:
        raise ValueError("Khoảng nghỉ LLM phải là số giây hữu hạn, không âm")
    manifest = output_dir / "run_manifest.json"
    if manifest.exists():
        identity = HistoricalMemoryRunner._read_envelope(manifest)
        options: dict[str, Any] = {"symbols": tuple(identity["symbols"]), "start": identity["start"],
                                   "end": identity["end"], "model_config": identity["models"]}
    else:
        options = {}
    plan = HistoricalMemoryRunner(output_dir, **options).plan()
    total = plan["eligible_count"]
    initial = completed_count(output_dir)
    if initial > total:
        raise ValueError("Kho staging dài hơn lịch đã chốt")
    current = initial
    while current < total:
        check_cooldown(output_dir)
        batch = min(batch_size, total - current)
        if (output_dir / "run.lock").exists():
            raise RuntimeError("Runner đang chạy hoặc khóa còn sót; cần rà soát trước khi tiếp tục")
        env = os.environ.copy()
        env["GROQ_API_KEY"] = current_key(env_file, env)
        env["HISTORICAL_LLM_GAP_SECONDS"] = str(float(llm_gap_seconds))
        command = [sys.executable, "-u", "-X", "utf8", str(ROOT / "scripts/run_paced_historical_memory.py"),
                   "--output-dir", str(output_dir), "--max-new-points", str(batch)]
        if options:
            command += ["--symbols", *options["symbols"], "--start", options["start"], "--end", options["end"]]
        returncode, retry_wait = run_batch(command, env)
        if returncode:
            if retry_wait is not None:
                save_cooldown(output_dir, retry_wait)
            saved = completed_count(output_dir)
            if not current <= saved <= current + batch:
                raise ValueError("Kho staging đổi bất thường sau khi runner báo lỗi")
            next_step = "kiểm checkpoint trước khi chạy lại"
            if retry_wait is not None and saved < total:
                archived = archive_interrupted_point(output_dir, plan["points"][saved], saved)
                print(f"Đã lưu riêng {len(archived)} file dở dang; episode hoàn chỉnh được giữ nguyên.")
                next_step = "đã rà soát checkpoint, có thể chạy lại sau cooldown"
            reason = f"lỗi LLM đầu tiên, retry sau {retry_wait:.1f} giây" if retry_wait is not None else f"mã thoát {returncode}"
            raise RuntimeError(f"Runner dừng sau {saved}/{total} episode ({reason}); {next_step}")
        updated = completed_count(output_dir)
        if updated != current + batch:
            raise ValueError("Runner không xuất đủ episode của đợt; dừng để rà soát journal")
        current = updated
        print(f"Đã hoàn thành {current}/{total}; lần tiếp theo sẽ đọc lại .env")
    return {"completed": current, "remaining": total - current, "new_points": current - initial}


def main() -> None:
    """Chạy nối tiếp đến khi hết lịch hoặc gặp lỗi; đọc lại key giữa hai đợt."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs/historical_memory_run")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--batch-size", type=int, default=8, help="Số episode mỗi đợt, mặc định 8; dùng 1 để đổi key sau từng điểm")
    parser.add_argument("--llm-gap-seconds", type=float, default=DEFAULT_LLM_GAP_SECONDS,
                        help="Khoảng nghỉ tối thiểu giữa hai lời gọi LLM, mặc định 75 giây")
    args = parser.parse_args()
    status = resume(args.output_dir, batch_size=args.batch_size, env_file=args.env_file,
                    llm_gap_seconds=args.llm_gap_seconds)
    print(f"Đã lưu {status['completed']} episode; còn {status['remaining']} điểm")


if __name__ == "__main__":
    main()
