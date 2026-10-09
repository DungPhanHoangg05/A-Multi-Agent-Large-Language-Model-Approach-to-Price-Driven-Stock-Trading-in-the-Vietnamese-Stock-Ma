"""Khóa/xác minh input cohort W5 offline; quota tạm hoãn, không gọi LLM."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.research_input_lock import prepare_inputs, verify_inputs


def main() -> None:
    """Chỉ tạo hai artifact cần cho luồng chính hoặc xác minh lại chỉ đọc."""
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true", help="Khóa lịch/nguồn và plan smoke một lần")
    mode.add_argument("--verify", action="store_true", help="Dry-run lại manifest và toàn bộ ngày đã khóa")
    parser.add_argument("--calendar", type=Path, default=ROOT / "outputs/bayesian_benchmark/calendar.json")
    args = parser.parse_args()
    if args.verify and args.calendar != ROOT / "outputs/bayesian_benchmark/calendar.json":
        parser.error("--verify dùng calendar đã ghim trong manifest")
    result = prepare_inputs(args.calendar, progress=print) if args.prepare else verify_inputs(progress=print)
    checked = result["dry_run"]
    print(f"Input lock {checked['status']}: {checked['verified_points']} điểm; {checked['by_cohort']}")
    print("Ngân sách W5-11 tạm hoãn; Gate C pending; prompt thực chưa sinh, không gọi API.")


if __name__ == "__main__":
    main()
