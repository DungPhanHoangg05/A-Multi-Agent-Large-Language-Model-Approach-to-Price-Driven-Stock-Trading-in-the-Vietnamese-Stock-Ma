"""Một lệnh warmup → bốn scope preflight → panel256 r2; API do người dùng chạy."""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    """Offline không đọc key/mạng; online luôn giữ một writer và ledger chung."""
    from core.groq_pacing import PilotStop
    from core.mt_bicl_v4_completion import DataCompletionError
    from core.mt_bicl_v4_protocol import read
    from core.mt_bicl_v4_warmup import PendingWarmup
    from core.mt_bicl_v41_r2_acceptance import LAYOUT
    from core.mt_bicl_v41_r2_release import verify
    from core.mt_bicl_v41_r2_backup import checkpoint
    from core.mt_bicl_v41_r2_warmup import COLLECTION, load
    from core.panel_coordinator import run
    from core.prior_run_lock import PriorRunLock
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--verify-only', action='store_true')
    group.add_argument('--preflight-only', action='store_true')
    parser.add_argument('--rebind-scope', choices=[f'scope_{i}' for i in range(1, 5)])
    args = parser.parse_args()
    if args.verify_only:
        if args.rebind_scope:
            parser.error('Không rebind khi verify-only')
        from scripts.verify_mt_bicl_protocol_v4 import reject_network
        socket.create_connection = reject_network
        socket.socket.connect = reject_network
    try:
        with PriorRunLock(ROOT / COLLECTION / 'run.lock', 'conditional-panel-r2'):
            with PriorRunLock(ROOT / 'outputs/oos_pilot/api_usage.json.lock', 'shared-account-ledger-v2'):
                try:
                    release = verify(ROOT)
                except ValueError as error:
                    raise DataCompletionError(str(error)) from None
                if not args.verify_only:
                    from scripts.verify_execution_price_gate import fetch_paginated
                    load(ROOT, release, fetch=fetch_paginated)
                    backup = checkpoint(ROOT)
                    print('Bản sao runtime ngoài dự án: ' + backup['path'], flush=True)
                result = run(ROOT, release, offline=args.verify_only, preflight_only=args.preflight_only,
                             rebind=args.rebind_scope, layout=LAYOUT if args.verify_only else replace(LAYOUT, checkpoint=checkpoint))
        print(f"V4.1 r2: {result['status']}; complete={result.get('complete', 0)}/256. Chưa tự mở W11-19.")
        return 0
    except PendingWarmup:
        if args.verify_only:
            print('V4.1 r2: WAITING_USER_WARMUP; source/numeric/panel/ledger PASS; không key hoặc network. Người dùng chạy lại cùng lệnh bỏ --verify-only.')
            return 0
        raise
    except PilotStop:
        state = read((ROOT / 'outputs/oos_pilot/api_usage.json').read_bytes())
        reason = (state.get('last_stop') or {}).get('reason', 'PROVIDER_OR_INVOCATION_STOP')
        print(f'Dừng do {reason}; giữ UUID/cache/reserve. Đọc dòng Provider; xử lý nguyên nhân rồi chạy lại cùng lệnh.')
        return 3
    except KeyboardInterrupt:
        print('Đã dừng; giữ warmup/shard/scope/UUID/cache/checkpoint. Chạy lại cùng lệnh để tiếp tục.')
        return 3
    except FileNotFoundError as error:
        path = Path(error.filename) if error.filename else Path('không xác định')
        try:
            path = path.resolve().relative_to(ROOT)
        except ValueError:
            path = Path(path.name)
        print('Dừng kiểm r2: thiếu file ' + str(path) + '; giữ UUID/cache/reserve.', file=sys.stderr)
        return 1
    except Exception as error:
        detail = str(error) if isinstance(error, DataCompletionError) else type(error).__name__
        print('Dừng kiểm r2: ' + detail + '; giữ bằng chứng. Không đổi model/key ngầm.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
