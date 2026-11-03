"""CLI offline T10: fixtures Alpha, phản ví dụ causal và ảnh hưởng metadata frozen."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    """Tạo release mới hoặc đối soát hash, không inference/API."""
    from core.revision_alpha_contract import OUTPUT, check_release, run_audit
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(); output = args.output if args.output.is_absolute() else ROOT / args.output
    if args.check:
        print(f"T10 hashes PASS ({check_release(ROOT, output)} files).")
        return
    result = run_audit(ROOT, output)
    print(f"T10 audit: {result['result']}; fixtures={result['fixture_cases']}.")
    print(f"Outer cutoff={result['outer_cutoff_gate']}; native row-wise causal={result['native_rowwise_causal_gate']}.")
    print(f"Đầu ra: {output}")


if __name__ == "__main__":
    main()
