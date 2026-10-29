"""Khóa/tái kiểm nomination v2 offline; không sửa report, mở xác nhận hoặc triển khai v3."""

from __future__ import annotations

import argparse
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.mt_bicl_bank import content_hash
from core.mt_bicl_v2_development import LOCK
from core.mt_bicl_v2_nomination import RECEIPT, rebuild, save_or_verify
from core.mt_bicl_v2_release import LEDGER
from core.prior_run_lock import PriorRunLock
from scripts.verify_mt_bicl_development import reject_network


def main() -> None:
    """Chặn socket, giữ khóa chung và chỉ tạo receipt nomination được phép bởi W11-05."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    socket.create_connection = reject_network
    socket.socket.connect = reject_network
    with PriorRunLock(ROOT/LOCK, content_hash({"scope": "MT_BICL_DEVELOPMENT_OPERATIONS_V2"})), PriorRunLock(
            (ROOT/LEDGER).parent/(Path(LEDGER).name+".lock"), "shared-account-ledger-v2"):
        result = rebuild(ROOT)
        save_or_verify(ROOT, result, verify_only=args.verify_only)
    print(f"W11-05 PASS; nomination v2={result['status']}; confirmation v2={result['confirmation_v2']['status']}; receipt={RECEIPT}.")


if __name__ == "__main__":
    main()
