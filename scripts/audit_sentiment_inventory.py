"""CLI inventory sentiment T05; chỉ đọc cục bộ, không preload/scoring/LLM hoặc paper."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    """Tạo release riêng hoặc kiểm hash, tuyệt đối không chạy API worker."""
    from core.revision_sentiment_inventory import OUTPUT, run_audit, verify_release
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    if args.check:
        count = verify_release(ROOT, output)
        print(f"Inventory T05: hash nguồn/đầu ra PASS ({count} files).")
        return
    result = run_audit(ROOT, output)
    corpus = result["legacy"]["corpus"]
    print(f"Inventory T05: {corpus['records']} records / {corpus['unique_article_identities']} identities; "
          f"{result['local_rescore']['unique_scored_identities']} excerpts đã rescore từ trước.")
    print(f"Đầu ra: {output}")


if __name__ == "__main__":
    main()
