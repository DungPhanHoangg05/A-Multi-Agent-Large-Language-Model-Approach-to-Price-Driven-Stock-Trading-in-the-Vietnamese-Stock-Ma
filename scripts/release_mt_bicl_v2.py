"""CLI freeze/release W10-14; verifier lạnh chỉ đọc nguồn, không nạp GPU hoặc gọi API."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))

from core.mt_bicl_bank import content_hash
from core.mt_bicl_v2_release import NAMESPACE, collect_inputs, freeze, verify_release
from core.mt_bicl_v2_preparation import BUDGET_PAYLOAD_SHA256, PROTOCOL_SHA256 as BASE_PROTOCOL_SHA256
from core.prior_run_lock import PriorRunLock


def main()->int:
    """Không lệnh run/preflight API; freeze cấp scope, chưa bắt đầu thực nghiệm W11."""
    parser = argparse.ArgumentParser(description="Freeze teacher/student/protocol/runtime và release development v2")
    parser.add_argument("command",choices=("check-inputs","freeze","verify"))
    args = parser.parse_args()
    if args.command == "check-inputs":
        collect_inputs(ROOT)
        print("Cold-check source/runtime/teacher/student/proof/support PASS; không CUDA/LLM/API.")
        return 0
    identity = {"protocol_sha256":BASE_PROTOCOL_SHA256,"grant_payload_sha256":BUDGET_PAYLOAD_SHA256,"cap_seconds":14400,"W10_stop":"2026-11-01"}
    with PriorRunLock(ROOT/NAMESPACE,content_hash(identity)):
        if args.command == "freeze":
            release = freeze(ROOT)
            verify_release(ROOT,require_anchor=False)
            print("Freeze PASS; receipt cần neo Git trước consumer; scope=W11 development2023; release_task_API_calls=0.")
        else:
            release = verify_release(ROOT)
            print("Release="+release["status"]+"; cold integrity=PASS; scope=W11 development2023; confirmation=false; release_task_API_calls=0.")
    return 0


if __name__ == "__main__":
    try:raise SystemExit(main())
    except KeyboardInterrupt:
        print("Đã dừng; giữ receipt/budget, không có API được gọi.",file=sys.stderr)
        raise SystemExit(3)
    except (ValueError,RuntimeError,OSError,KeyError,TypeError) as error:
        print("Dừng freeze/release, giữ bằng chứng: "+str(error),file=sys.stderr)
        raise SystemExit(1)
