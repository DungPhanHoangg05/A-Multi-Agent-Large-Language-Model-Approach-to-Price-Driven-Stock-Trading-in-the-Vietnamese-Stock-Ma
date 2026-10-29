"""Khóa/tái kiểm metadata protocol v3 offline, không implement utility hoặc chạy LLM."""

from __future__ import annotations

import argparse
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.mt_bicl_v2_release import LEDGER
from core.mt_bicl_v3_protocol import freeze, verify
from core.prior_run_lock import PriorRunLock
from scripts.verify_mt_bicl_development import reject_network


def main() -> None:
    """Chỉ khóa ledger để chụp prefix nhất quán; không tạo runtime counter v3."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", action="store_true")
    args = parser.parse_args()
    socket.create_connection = reject_network
    socket.socket.connect = reject_network
    with PriorRunLock((ROOT/LEDGER).parent/(Path(LEDGER).name+".lock"), "shared-account-ledger-v2"):
        result = freeze(ROOT) if args.freeze else verify(ROOT)
    print(f"W11-07 PASS: protocol v3 SPEC_LOCK_PASS; ngân sách={result['budget_cap_seconds']/3600:.0f} giờ từ0; chưa utility/API. Tiếp theo W11-08.")


if __name__ == "__main__":
    main()
