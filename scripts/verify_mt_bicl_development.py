"""Kiểm toán development đã hoàn tất và dựng account/Numeric/Teacher hoàn toàn offline."""

from __future__ import annotations

import argparse
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.mt_bicl_bank import content_hash
from core.mt_bicl_v2_audit import REPORT, rebuild, save_or_verify
from core.mt_bicl_v2_development import LOCK
from core.mt_bicl_v2_release import LEDGER
from core.prior_run_lock import PriorRunLock


def reject_network(*args: object, **kwargs: object) -> None:
    """Dừng nếu dependency vô tình mở socket; CLI không có tham số credential hoặc API."""
    raise AssertionError("Verifier offline không được kết nối mạng")


def main() -> None:
    """Khóa cùng runner/ledger, chỉ ghi report mới ngoài cây bằng chứng research."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    socket.create_connection = reject_network
    socket.socket.connect = reject_network
    with PriorRunLock(ROOT/LOCK, content_hash({"scope": "MT_BICL_DEVELOPMENT_OPERATIONS_V2"})), PriorRunLock(
            (ROOT/LEDGER).parent/(Path(LEDGER).name+".lock"), "shared-account-ledger-v2"):
        result = rebuild(ROOT)
        save_or_verify(ROOT, result, verify_only=args.verify_only)
    print(f"W11-03 PASS: 60 point,612 slot; account primary/repeat và Numeric/Teacher tại {REPORT}.")


if __name__ == "__main__":
    main()
