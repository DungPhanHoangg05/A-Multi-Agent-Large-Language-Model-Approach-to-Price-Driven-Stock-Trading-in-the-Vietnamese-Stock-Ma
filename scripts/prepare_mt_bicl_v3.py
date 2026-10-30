"""Freeze/dry-run/verify/release v3 offline; live controls chỉ do người dùng chạy."""

from __future__ import annotations

import argparse
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from core.mt_bicl_v3_budget import RuntimeBudget
from core.mt_bicl_v3_freeze import OUTPUT, prepare, verify
from core.mt_bicl_v3_preflight import dry_run, feasibility, release
from core.mt_bicl_v2_io import write_envelope
from core.bayesian_memory import read_json
from core.prior_run_lock import PriorRunLock
from scripts.verify_mt_bicl_development import reject_network


def main() -> None:
    """Mọi mode bị chặn socket; không nạp dotenv hoặc khởi tạo client dùng key thật."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "verify", "release"))
    args = parser.parse_args()
    socket.create_connection = reject_network
    socket.socket.connect = reject_network
    with RuntimeBudget(ROOT, "API_preflight" if args.command == "prepare" else "cold_verification") as budget:
        with PriorRunLock(ROOT/"outputs/oos_pilot/api_usage.json.lock", "shared-account-ledger-v2"):
            manifest, snapshot = prepare(ROOT) if args.command == "prepare" else verify(ROOT, require_anchor=True)
            if args.command == "prepare":
                result = dry_run(ROOT, manifest, snapshot, budget)
                profile = feasibility(manifest, read_json(ROOT/"outputs/oos_pilot/api_usage.json"), None, budget.remaining_seconds())
                write_envelope(ROOT/OUTPUT/"freeze/offline_preflight.json", "utility_icl_offline_preflight_v3", {"dry_run": result, "feasibility": profile})
                print("Freeze/dry-run v3 PASS; chưa control API thật, chưa release. Người dùng chạy scripts/continue_mt_bicl_v3.py.")
            elif args.command == "release":
                result = release(ROOT, manifest, snapshot, budget)
                print(result["status"]+"; cần neo receipt Git trước primary.")
            else:
                print("Manifest/source/snapshot v3 PASS; không HTTP/model/refit; không đổi quyền release.")
        budget.checkpoint()


if __name__ == "__main__":
    main()
