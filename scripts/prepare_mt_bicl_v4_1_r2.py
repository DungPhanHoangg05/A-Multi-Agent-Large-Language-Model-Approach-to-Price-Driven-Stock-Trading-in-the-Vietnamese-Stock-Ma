"""Chuẩn bị hoặc cold nghiệm thu r2 offline; không gọi API hoặc đọc credential."""

from __future__ import annotations

import argparse
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    """Tách build/release để receipt nguồn luôn được commit trước bước khóa tiếp theo."""
    from scripts.verify_mt_bicl_protocol_v4 import reject_network
    socket.create_connection = reject_network
    socket.socket.connect = reject_network
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('data', 'release', 'accept'))
    args = parser.parse_args()
    if args.action == 'data':
        from core.mt_bicl_v41_r2_data import build
        result = build(ROOT)
    elif args.action == 'release':
        from core.mt_bicl_v41_r2_release import prepare
        result = prepare(ROOT)
    else:
        from core.mt_bicl_v41_r2_acceptance import accept
        from core.mt_bicl_v41_r2_warmup import COLLECTION
        from core.prior_run_lock import PriorRunLock
        with PriorRunLock(ROOT / COLLECTION / 'run.lock', 'conditional-panel-r2'):
            with PriorRunLock(ROOT / 'outputs/oos_pilot/api_usage.json.lock', 'shared-account-ledger-v2'):
                result = accept(ROOT)
    print(f"R2: {result['status']}; chưa tự mở development hoặc confirmation.")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
