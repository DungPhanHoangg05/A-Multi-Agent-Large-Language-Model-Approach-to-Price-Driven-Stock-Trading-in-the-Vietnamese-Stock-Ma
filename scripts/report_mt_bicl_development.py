"""Dựng/tái kiểm báo cáo W11-04 offline, không chạy nomination hoặc gọi API."""

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
from core.mt_bicl_v2_release import LEDGER
from core.mt_bicl_v2_report import REPORT, rebuild, save_or_verify
from core.prior_run_lock import PriorRunLock
from scripts.verify_mt_bicl_development import reject_network


def main() -> None:
    """Khóa evidence dùng chung, chặn socket; chỉ ghi report/hình ngoài run đã freeze."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    socket.create_connection = reject_network
    socket.socket.connect = reject_network
    with PriorRunLock(ROOT/LOCK, content_hash({"scope": "MT_BICL_DEVELOPMENT_OPERATIONS_V2"})), PriorRunLock(
            (ROOT/LEDGER).parent/(Path(LEDGER).name+".lock"), "shared-account-ledger-v2"):
        result = rebuild(ROOT)
        save_or_verify(ROOT, result, verify_only=args.verify_only)
    d = result["G"]["contrasts"]["Original"]["mean_delta_return_pp"]
    print(f"W11-04 PASS: G={result['G']['count']}; D Full−Original={d:.9f} đpt. Báo cáo: {REPORT}; chưa nomination.")


if __name__ == "__main__":
    main()
