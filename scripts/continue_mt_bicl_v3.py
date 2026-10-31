"""Tiếp tục cùng run v3 không có giới hạn bộ đếm, theo chỉ đạo ngày31/10/2026."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.mt_bicl_v3_unbounded import main

if __name__ == "__main__":
    raise SystemExit(main(ROOT))
