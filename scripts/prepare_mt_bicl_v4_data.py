"""Dựng/cold replay dataset v4 offline; không tự thu thập API khi thiếu agent thật."""

from __future__ import annotations

import argparse
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.mt_bicl_v4_dataset import build
from core.prior_run_lock import PriorRunLock
from scripts.verify_mt_bicl_protocol_v4 import reject_network


def main() -> None:
    """Khóa dataset/ledger; chặn socket và ghi mọi thiếu hụt vào artifact riêng."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true", help="Cold rebuild readonly, không fit lại regime")
    args = parser.parse_args()
    socket.create_connection = reject_network
    socket.socket.connect = reject_network
    with PriorRunLock(ROOT / "outputs/bayesian_benchmark/mt_bicl_v4/data.lock", "conditional-v4-data"):
        with PriorRunLock(ROOT / "outputs/oos_pilot/api_usage.json.lock", "shared-account-ledger-v2"):
            result = build(ROOT, verify_only=args.verify_only)
    print(f"W11-18: kiểm toán kỹ thuật PASS; dữ liệu={result['status']}; query={result['unique_queries']}; W11-19={'CHO_PHÉP_CHUẨN_BỊ' if result['ready_for_W11_19'] else 'CHƯA_ĐẠT_GATE'}.")


if __name__ == "__main__":
    main()
