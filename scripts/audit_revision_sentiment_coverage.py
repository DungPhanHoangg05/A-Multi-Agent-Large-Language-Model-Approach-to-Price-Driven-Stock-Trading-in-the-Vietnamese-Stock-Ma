"""CLI T06 offline: coverage từ inventory T05, giữ nguyên runtime/prompt đang chạy."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    """Tạo release mới hoặc kiểm hashes; không gọi worker/API/scorer."""
    from core.revision_sentiment_coverage import OUTPUT, run_audit
    from core.revision_sentiment_inventory import verify_release
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    if args.check:
        print(f"Coverage T06: hash nguồn/đầu ra PASS ({verify_release(ROOT, output)} files).")
        return
    summary = run_audit(ROOT, output)
    counts = summary["release"]["main"]["pooled"]
    print(f"Coverage T06: main có >=3 bài hợp lệ {counts['with_at_least_3_valid_articles']}/{counts['cutoffs']}; missing={counts['missing']}.")
    print(f"Đầu ra: {output}")


if __name__ == "__main__":
    main()
