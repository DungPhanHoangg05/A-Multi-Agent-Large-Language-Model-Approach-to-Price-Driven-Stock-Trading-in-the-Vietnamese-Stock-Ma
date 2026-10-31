"""Một lệnh tiếp tục panel256 v4.1; API do người dùng chạy với bốn scope độc lập."""

from __future__ import annotations

import argparse
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    """Khóa run/ledger trước kiểm release; không đọc key trong chế độ offline."""
    from core.groq_pacing import PilotStop
    from core.mt_bicl_v4_completion import DataCompletionError
    from core.mt_bicl_v4_protocol import read
    from core.mt_bicl_v41_collect import DIRECTORY
    from core.mt_bicl_v41_panel import verify_release
    from core.mt_bicl_v41_runtime import run
    from core.prior_run_lock import PriorRunLock
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--verify-only', action='store_true')
    group.add_argument('--preflight-only', action='store_true')
    parser.add_argument('--rebind-scope', choices=[f'scope_{i}' for i in range(1, 5)])
    args = parser.parse_args()
    if args.verify_only:
        if args.rebind_scope:
            parser.error('Không rebind credential trong verify-only')
        from scripts.verify_mt_bicl_protocol_v4 import reject_network
        socket.create_connection = reject_network
        socket.socket.connect = reject_network
    try:
        with PriorRunLock(ROOT/DIRECTORY/'run.lock', 'conditional-v4-1-panel256'):
            with PriorRunLock(ROOT/'outputs/oos_pilot/api_usage.json.lock', 'shared-account-ledger-v2'):
                release = verify_release(ROOT)
                result = run(ROOT, release, offline=args.verify_only, preflight_only=args.preflight_only, rebind=args.rebind_scope)
        print(f"V4.1: {result['status']}; complete={result.get('complete', 0)}/256. Chưa tự mở W11-19.")
        return 0
    except PilotStop:
        state = read((ROOT/'outputs/oos_pilot/api_usage.json').read_bytes())
        reason = (state.get('last_stop') or {}).get('reason', 'PROVIDER_OR_INVOCATION_STOP')
        print(f'Dừng do {reason}; giữ UUID/cache/reserve. Đọc dòng Provider phía trên; chạy lại cùng lệnh sau khi xử lý nguyên nhân.')
        return 3
    except KeyboardInterrupt:
        print('Đã dừng; giữ shard/scope/UUID/cache/checkpoint. Chạy lại cùng lệnh để tiếp tục.')
        return 3
    except (ValueError, OSError, KeyError) as error:
        # Chỉ lỗi hợp đồng tự tạo được in chi tiết; lỗi SDK có thể chứa credential.
        detail = str(error) if isinstance(error, DataCompletionError) else type(error).__name__
        print('Dừng kiểm v4.1: '+detail+'; giữ bằng chứng.', file=sys.stderr)
        return 1
    except Exception as error:
        print('Dừng kiểm v4.1 do '+type(error).__name__+'; giữ bằng chứng, không đổi model/key ngầm.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
