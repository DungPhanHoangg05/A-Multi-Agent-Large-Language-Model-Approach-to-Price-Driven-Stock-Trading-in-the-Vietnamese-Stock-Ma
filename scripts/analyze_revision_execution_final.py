"""CLI offline T19; xuất release riêng, không dùng producer execution cũ."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    """Build từ nguồn T04/T18 đã hash hoặc check chỉ đọc, không ghi paper/."""
    from core.revision_execution_final import OUTPUT, build_release, check_release
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('build', 'check'))
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    if args.command == 'build':
        result = build_release(ROOT, args.output)
        print(f"T19 PASS: {result['n_account_executions']} accounts/scenarios; API jobs=0.")
    else:
        print(f'T19 hashes PASS: {check_release(ROOT, args.output)}')


if __name__ == '__main__':
    main()
