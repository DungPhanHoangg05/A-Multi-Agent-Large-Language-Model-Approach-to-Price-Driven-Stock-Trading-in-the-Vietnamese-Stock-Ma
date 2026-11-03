"""CLI T12 offline: khóa numeric control design, chưa chạy T13 hoặc API."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    """Xuất design mới hoặc kiểm hashes của release có sẵn."""
    from core.revision_numeric_design import OUTPUT, check_release, freeze_design
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(); output = args.output if args.output.is_absolute() else ROOT / args.output
    if args.check:
        print(f"T12 hashes PASS ({check_release(ROOT, output)} files).")
        return
    result = freeze_design(ROOT, output)
    print(f"T12 design PASS: {result['fit_scopes']} scopes, {result['strategies']} strategies; T13 chưa chạy, real-data fits=0.")
    print(f"Đầu ra: {output}")


if __name__ == "__main__":
    main()
