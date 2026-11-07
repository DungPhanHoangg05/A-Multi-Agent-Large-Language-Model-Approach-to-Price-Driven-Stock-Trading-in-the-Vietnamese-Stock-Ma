"""CLI readiness H02: import nguyên byte và cold audit, không chạy thí nghiệm."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.historical_asset_readiness import run


def main() -> None:
    """Giữ blockers khoa học trong receipt; integrity lỗi phải dừng bằng ngoại lệ."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true", help="Dựng lại receipt mà không ghi file.")
    args = parser.parse_args()
    result = run(ROOT, verify=args.verify_only)
    print("Đã đối soát readiness: " + result["status"])
    for row in result["registry"]:
        print(row["method"] + ": " + row["status"] + " " + ", ".join(row["blocking_dependencies"]))


if __name__ == "__main__":
    main()
