"""Đối soát hoặc khóa metadata v4 offline; không train, đọc key hay gọi API."""

from __future__ import annotations

import argparse
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.mt_bicl_v4_protocol import freeze, verify
from core.prior_run_lock import PriorRunLock


def reject_network(*args: object, **kwargs: object) -> None:
    """Không cho đường kiểm spec mở kết nối mạng."""
    raise RuntimeError("Kiểm protocol chỉ được chạy offline")


def main() -> None:
    """Giữ OS lock ledger khi chụp prefix; chỉ ghi receipt mới nếu yêu cầu freeze."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", action="store_true", help="Khóa spec sau commit source")
    args = parser.parse_args()
    socket.create_connection = reject_network
    socket.socket.connect = reject_network
    with PriorRunLock(ROOT / "outputs/oos_pilot/api_usage.json.lock", "shared-account-ledger-v2"):
        result = freeze(ROOT) if args.freeze else verify(ROOT)
    print(f"W11-17 PASS: {result['status']}; v4 không trần giờ/hạn ngày; chưa cấp release train/API. Tiếp theo W11-18.")


if __name__ == "__main__":
    main()
