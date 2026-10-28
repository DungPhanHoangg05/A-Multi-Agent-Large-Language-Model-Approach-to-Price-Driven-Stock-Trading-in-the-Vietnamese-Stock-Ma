"""CLI teacher v2.1: kiểm input, fit/seal/resume và replay CPU; không có learner/LLM."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.mt_bicl_bank import content_hash
from core.mt_bicl_v21_preparation import NAMESPACE, load_inputs, run_preparation, verify_preparation
from core.prior_run_lock import PriorRunLock


def main() -> int:
    """Mã0: teacher hoàn tất; mã2: EM không hội tụ; mã3: pause; mã1: lỗi kỹ thuật."""
    parser = argparse.ArgumentParser(description="Chuẩn bị teacher Beta–Bernoulli v2.1 offline")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check-inputs")
    run = commands.add_parser("run")
    run.add_argument("--resume", action="store_true")
    verify = commands.add_parser("verify")
    verify.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    inputs = load_inputs(ROOT)
    if args.command == "check-inputs":
        print("Input/runtime/77 file v1 và grant thêm10 giờ PASS; chưa fit/sinh corpus/student/GPU/API.")
        return 0
    # Mọi stage v2 dùng chung khóa namespace để không tranh ngân sách giữa các seed.
    signature = content_hash(inputs["budget_identity"])
    with PriorRunLock(ROOT/NAMESPACE, signature):
        if args.command == "run":
            result = run_preparation(ROOT, inputs, resume=args.resume)
            converged = result["status"] == "COMPLETE_TEACHER_ORACLE_ONLY"
            print(f"Teacher: {result['status']}; student/GPU/API chưa chạy; training/development/Decision=false.")
            return 0 if converged else 2
        result = verify_preparation(ROOT, inputs, replay=args.replay)
        print(f"Integrity {result['integrity']}; replay={result['replay']}; teacher={result['teacher_status']}; "
              f"iteration={result['iterations']}, max_delta={result['max_pi_delta']:.12g}; chưa release train/Decision.")
        return 0 if result["teacher_status"] == "CONVERGED" else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Đã dừng teacher; stage đã commit giữ nguyên. Chạy lại run --resume.", file=sys.stderr)
        raise SystemExit(3)
    except (ValueError, RuntimeError, OSError) as error:
        print("Lỗi chuẩn bị teacher: "+str(error), file=sys.stderr)
        raise SystemExit(1)
