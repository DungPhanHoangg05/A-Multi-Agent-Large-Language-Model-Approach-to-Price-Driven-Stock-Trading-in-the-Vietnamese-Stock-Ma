"""CLI T01/T02/T03: prepare/verify/status/dry-run/analyze offline; chỉ run gọi API."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    """Queue riêng chỉ dùng whitelist mới, không khởi động các runner grid cũ."""
    from core.revision_call_archive import StudyStop
    from core.revision_common_study import write_json
    from core.revision_minimal_bank import DEST, legacy_guard, prepare, verify_manifest
    from core.revision_minimal_run import analyze, run_queue, status
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "verify", "status", "dry-run", "run", "analyze"))
    parser.add_argument("--all", action="store_true", help="Dùng năm worker trong một queue chung")
    parser.add_argument("--output", type=Path, help="Chỉ dry-run: ghi danh sách jobs thiếu ra file mới")
    args = parser.parse_args()
    if args.all and args.command != "run": parser.error("--all chỉ dùng với run")
    if args.output and args.command != "dry-run": parser.error("--output chỉ dùng với dry-run")
    run = ROOT / DEST
    try:
        if args.command == "prepare":
            with legacy_guard(ROOT):
                m = prepare(ROOT, run)
            print(json.dumps({"counts": m["counts"], "run_signature": m["sha256"]}, ensure_ascii=False, indent=2))
            return
        m = verify_manifest(ROOT, run)
        if args.command == "run":
            if not args.all: parser.error("Dùng run --all để một coordinator giữ khóa cho cả queue")
            run_queue(ROOT, run, m)
        elif args.command == "analyze":
            analyze(ROOT, run, m)
        else:
            result = status(ROOT, run, m)
            if args.output:
                write_json(args.output.resolve(), result, True)
            summary = {k: v for k, v in result.items() if k != "missing_jobs"}
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            if args.command == "verify": print("Integrity whitelist PASS; chưa phải đóng T04 hoặc reviewer.")
    except BaseException as exc:
        if isinstance(exc, (SystemExit, KeyboardInterrupt)): raise
        message = str(exc)
        for name, value in os.environ.items():
            if name.startswith("GROQ_") and name.endswith("API_KEY") and value:
                message = message.replace(value, "[REDACTED]")
        parser.exit(3 if isinstance(exc, StudyStop) else 1, "Queue dừng có checkpoint: " + message + "\n")


if __name__ == "__main__":
    main()
