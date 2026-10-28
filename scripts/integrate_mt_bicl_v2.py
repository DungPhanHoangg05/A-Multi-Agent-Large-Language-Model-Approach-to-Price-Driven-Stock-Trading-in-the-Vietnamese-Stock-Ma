"""CLI W10-13 chỉ có kiểm offline; không đọc API key, không có lệnh gọi Decision API."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG",":4096:8")
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))

from core.mt_bicl_bank import content_hash
from core.mt_bicl_v2_adapter import NAMESPACE, load_inputs
from core.mt_bicl_v2_integration import run_stage, verify
from core.mt_bicl_v2_io import ActiveBudget
from core.mt_bicl_v2_preparation import BUDGET_PAYLOAD_SHA256, PROTOCOL_SHA256 as BASE_PROTOCOL_SHA256
from core.prior_run_lock import PriorRunLock


def main()->int:
    """Bốn lệnh offline; release development/Decision luôn false ở task này."""
    parser = argparse.ArgumentParser(description="Adapter/dry-run60/24 semantic contract probe offline, không LLM/API")
    commands = parser.add_subparsers(dest="command",required=True)
    commands.add_parser("check-inputs")
    commands.add_parser("dry-run")
    commands.add_parser("probes")
    verifier = commands.add_parser("verify")
    verifier.add_argument("--replay",action="store_true")
    args = parser.parse_args()
    if args.command == "check-inputs":
        load_inputs(ROOT)
        print("Nguồn/runtime/candidate W10-12 PASS; lịch60 point giữ nguyên; chưa GPU/optimizer/LLM/API.")
        return 0
    identity = {"protocol_sha256":BASE_PROTOCOL_SHA256,"grant_payload_sha256":BUDGET_PAYLOAD_SHA256,
                "cap_seconds":14400,"W10_stop":"2026-11-01"}
    if not (ROOT/NAMESPACE/"active_budget_v2.json").exists():raise ValueError("Thiếu budget gốc, không cấp lại4 giờ")
    with PriorRunLock(ROOT/NAMESPACE,content_hash(identity)):
        with ActiveBudget(ROOT/NAMESPACE/"active_budget_v2.json",identity):inputs = load_inputs(ROOT)
        if inputs["budget_identity"] != identity:raise ValueError("Ngân sách không đúng grant gốc")
        result = verify(ROOT,inputs,replay=args.replay) if args.command == "verify" else run_stage(ROOT,inputs,args.command)
        print("Tích hợp offline: "+result["status"]+"; LLM/API=0; development/Decision=false, chờ W10-14.")
    return 0


if __name__ == "__main__":
    try:raise SystemExit(main())
    except KeyboardInterrupt:
        print("Đã dừng; giữ journal/UUID và budget, không tự gửi lại request unknown.",file=sys.stderr)
        raise SystemExit(3)
    except (ValueError,RuntimeError,OSError,KeyError,TypeError) as error:
        print("Dừng tích hợp, giữ bằng chứng: "+str(error),file=sys.stderr)
        raise SystemExit(1)
