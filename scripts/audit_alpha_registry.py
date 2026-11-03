"""CLI offline T09: xuất registry Alpha từ AST và đối chiếu catalogue gốc đã lưu."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    """Tạo release mới hoặc kiểm hash, không gọi loader/selector/model."""
    from core.revision_alpha_registry import OUTPUT, check_release, run_audit
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    if args.check:
        print(f"T09 hashes PASS ({check_release(ROOT, output)} files).")
        return
    result = run_audit(ROOT, output)
    print(f"T09 PASS: {result['counts']}; khớp 80/21/5={result['count_contract_80_21_5_matches']}.")
    print(f"Đầu ra: {output}")


if __name__ == "__main__":
    main()
