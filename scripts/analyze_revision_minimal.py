"""CLI T04: khóa/phân tích release rút gọn hoặc kiểm hash, hoàn toàn offline."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    """Không sửa queue, release cũ, paper hoặc tự khởi động inference."""
    from core.revision_minimal_analysis import OUTPUT, build_release, check_release, offline_guard
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('build', 'check'))
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    with offline_guard():
        if args.command == 'build':
            result = build_release(ROOT, args.output)
            print(f"T04 PASS: {result['research_executions']} executions; API phân tích=0, baseline fits=0.")
        else:
            print(f'T04 hashes PASS ({check_release(ROOT, args.output)} files).')
    print(f'Đầu ra: {args.output}')


if __name__ == '__main__':
    main()
