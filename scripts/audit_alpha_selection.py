"""CLI T11 offline: selection diagnostics trên whitelist frozen, không sửa runtime/API."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    """Tạo release mới hoặc kiểm hash; không ghi đè snapshot hiện có."""
    from core.revision_alpha_selection import OUTPUT, check_release, run_audit
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(); output = args.output if args.output.is_absolute() else ROOT / args.output
    if args.check:
        print(f"T11 hashes PASS ({check_release(ROOT, output)} files).")
        return
    result = run_audit(ROOT, output)
    print(f"T11 PASS: {result['main_cutoffs']} cutoffs, {result['selected_slots_verified']} selected slots; chỉ native in-sample diagnostics.")
    print(f"Đầu ra: {output}")


if __name__ == "__main__":
    main()
