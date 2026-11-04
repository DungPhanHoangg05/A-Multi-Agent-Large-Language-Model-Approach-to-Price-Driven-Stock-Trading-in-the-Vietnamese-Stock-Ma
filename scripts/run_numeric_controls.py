"""CLI T13 offline: prepare khóa code, run/resume controls, check toàn release."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    """Không tự gọi API, không tạo release mới hoặc bỏ hash guard khi resume."""
    from core.revision_numeric_controls import OUTPUT, check_release, prepare, run_controls
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "run", "check"))
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args(); output = args.output if args.output.is_absolute() else ROOT / args.output
    if args.command == "prepare":
        result = prepare(ROOT, output); print(f"T13 source freeze PASS: {len(result['scope_ids'])} scopes; chưa fit.")
    elif args.command == "check": print(f"T13 hashes PASS ({check_release(ROOT, output)} files).")
    else:
        result = run_controls(ROOT, output)
        print(f"T13 PASS: {result['test_predictions']} predictions, {result['strategies']} strategies, API=0.")
    print(f"Đầu ra: {output}")


if __name__ == "__main__":
    main()
