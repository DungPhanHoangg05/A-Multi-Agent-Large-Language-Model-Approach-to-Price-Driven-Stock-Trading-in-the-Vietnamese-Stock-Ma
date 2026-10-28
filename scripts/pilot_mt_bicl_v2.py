"""CLI pilot GPU v2: hai packing/seed17, checkpoint/resume và replay không giữ weights."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import signal
import sys
from time import perf_counter

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.mt_bicl_bank import content_hash
from core.mt_bicl_v2_pilot import NAMESPACE, load_inputs, run_pilots, verify_pilots
from core.prior_run_lock import PriorRunLock


def main() -> int:
    """Mã0 hoàn tất,2 gate tiny FAIL,3 pause,1 lỗi kỹ thuật; chưa cấp train lớn/API."""
    parser = argparse.ArgumentParser(description="Pilot distillation v2 theo protocol, không LLM/API")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check-inputs")
    run = commands.add_parser("run")
    run.add_argument("--resume", action="store_true")
    run.add_argument("--session-minutes", type=float)
    verify = commands.add_parser("verify")
    verify.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    limit = getattr(args, "session_minutes", None)
    if limit is not None and not 0 < limit <= 240:
        parser.error("session-minutes phải hữu hạn trong(0,240]")
    inputs = load_inputs(ROOT)
    if args.command == "check-inputs":
        print("Teacher v2.1/source/runtime/hash PASS; tiny32/diagnostic1000 hợp lệ; chưa gọi GPU/optimizer/API.")
        return 0
    requested, started = False, perf_counter()
    def handle_stop(signum: int, frame: object) -> None:
        """Hoãn Ctrl+C tới sau optimizer.step và ghi checkpoint an toàn."""
        nonlocal requested
        requested = True
        if args.command == "verify":
            raise KeyboardInterrupt()
        print("Đã nhận yêu cầu pause; chờ hết bước hiện tại và checkpoint.", flush=True)
    def stop() -> bool:
        """Thời lượng phiên không là early stopping theo metric."""
        return requested or (limit is not None and perf_counter()-started >= limit*60)
    for event in (signal.SIGINT, *([signal.SIGBREAK] if hasattr(signal, "SIGBREAK") else [])):
        signal.signal(event, handle_stop)
    with PriorRunLock(ROOT/NAMESPACE, content_hash(inputs["budget_identity"])):
        if args.command == "run":
            result = run_pilots(ROOT, inputs, resume=args.resume, stop=stop)
            print("Pilot: "+result["status"]+"; chưa release train lớn/development/Decision.")
            return 3 if result["status"] == "PAUSED" else 0 if result["status"] == "PILOT_PASS_AWAITING_PREFLIGHT" else 2
        result = verify_pilots(ROOT, inputs, replay=args.replay)
        print(f"Integrity={result['integrity']}; replay={result['replay']}; paired tiny gate={result['paired_tiny_gate']}; "
              "weights đã bỏ, chưa release train lớn/Decision.")
        return 0 if result["paired_tiny_gate"] == "PASS" else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Đã dừng kiểm/replay; artifact pilot giữ nguyên. Chạy lại cùng lệnh verify khi tiếp tục.", file=sys.stderr)
        raise SystemExit(3)
    except (ValueError, RuntimeError, OSError) as error:
        print("Dừng pilot, giữ checkpoint/bằng chứng: "+str(error), file=sys.stderr)
        raise SystemExit(1)
