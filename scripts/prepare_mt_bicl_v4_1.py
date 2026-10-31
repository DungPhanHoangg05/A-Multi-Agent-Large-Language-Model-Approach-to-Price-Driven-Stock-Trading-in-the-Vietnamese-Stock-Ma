"""Khóa spec, dựng ngân hàng hoặc cold nghiệm thu v4.1 hoàn toàn offline."""

from __future__ import annotations

import argparse
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    """Không đọc credential, mở socket hoặc tự chạy collection từ lệnh chuẩn bị."""
    from scripts.verify_mt_bicl_protocol_v4 import reject_network
    from core.prior_run_lock import PriorRunLock
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    for name in ('freeze-spec', 'build', 'release', 'verify-only', 'accept'):
        group.add_argument('--'+name, action='store_true')
    args = parser.parse_args()
    socket.create_connection = reject_network
    socket.socket.connect = reject_network
    try:
        with PriorRunLock(ROOT/'outputs/oos_pilot/api_usage.json.lock', 'shared-account-ledger-v2'):
            if args.freeze_spec:
                from core.mt_bicl_v41_protocol import freeze
                result = freeze(ROOT)
            elif args.build or args.verify_only:
                from core.mt_bicl_v41_bank import build
                result = build(ROOT, verify_only=args.verify_only)
            elif args.release:
                from core.mt_bicl_v41_panel import prepare_release
                result = prepare_release(ROOT)
            else:
                from core.mt_bicl_v41_panel import accept
                result = accept(ROOT)
        print('V4.1: '+result['status']+'; không API hoặc fit predictor.')
        return 0
    except (ValueError, OSError, KeyError) as error:
        print(f'Dừng đối soát v4.1: {type(error).__name__}: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
