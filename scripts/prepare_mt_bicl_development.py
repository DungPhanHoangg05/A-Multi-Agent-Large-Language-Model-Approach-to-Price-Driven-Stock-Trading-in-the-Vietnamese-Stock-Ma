"""Chuẩn bị W11 offline; API preflight chỉ chạy khi người dùng chọn lệnh tường minh."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.mt_bicl_bank import content_hash
from core.mt_bicl_v2_api_preflight import live_preflight, prepare, verify
from core.mt_bicl_v2_run_manifest import OUTPUT
from core.prior_run_lock import PriorRunLock


def main() -> int:
    """Mặc định verify offline, không đọc key; không cung cấp lệnh run ma trận/API study."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "verify", "api-preflight"), nargs="?", default="verify")
    parser.add_argument("--env-file", type=Path, default=ROOT/".env")
    args = parser.parse_args()
    if args.command == "api-preflight":
        result = live_preflight(ROOT, args.env_file)
        print("API preflight="+result["status"]+"; HTTP đã ghi ledger; chưa chạy primary/repeat/upstream.")
        return 0
    with PriorRunLock(ROOT/OUTPUT, content_hash({"scope": "W11_DEVELOPMENT_MANIFEST_OFFLINE"})):
        manifest, receipt = prepare(ROOT) if args.command == "prepare" else verify(ROOT)
    print(f"Manifest/dry-run/preflight offline PASS: {manifest['primary_slots']} primary + {manifest['repeat_slots']} repeat; "
          f"support={manifest['layout']['support']['simultaneous']}/60; API thật=0; live preflight="+receipt["live_api_preflight"])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Đã dừng; giữ manifest/journal/UUID/usage, không tự replay unknown.", file=sys.stderr)
        raise SystemExit(3)
    except (ValueError, RuntimeError, OSError, KeyError, TypeError) as error:
        print("Dừng preflight, giữ bằng chứng: "+str(error), file=sys.stderr)
        raise SystemExit(1)
