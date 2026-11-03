"""CLI T07 offline: hash/tokenizer/probabilities/prompt; không API hoặc model forward."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    """Chỉ tạo release mới hoặc đối soát hash của release đã có."""
    from core.revision_sentiment_contract import OUTPUT, check_release, run_audit
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--snapshot-dir", type=Path, help="Snapshot local có cùng revision và byte hashes đã khóa")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    if args.check:
        print(f"T07 hashes PASS ({check_release(ROOT, output, args.snapshot_dir)} files).")
        return
    summary = run_audit(ROOT, output, args.snapshot_dir)
    print(f"T07 PASS: {summary['saved_scores_validated']} scores, {summary['prompts']['planned_prompts_checked']} frozen prompts; "
          f"{summary['prompts']['actual_raw_requests_checked']} raw requests hoàn chỉnh.")
    print(f"Đầu ra: {output}")


if __name__ == "__main__":
    main()
