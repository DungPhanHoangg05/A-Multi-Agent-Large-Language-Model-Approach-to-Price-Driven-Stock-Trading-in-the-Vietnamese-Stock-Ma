"""CLI train distillation v2: preflight, ba seed, seal, evaluate và verify sau cùng."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import signal
import sys
from time import perf_counter

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG",":4096:8")
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))

from core.mt_bicl_bank import content_hash
from core.mt_bicl_v2_experiment import NAMESPACE, SEEDS, load_inputs
from core.mt_bicl_v2_final_evaluation import evaluate_final, export_candidate, verify_final
from core.mt_bicl_v2_io import ActiveBudget
from core.mt_bicl_v2_preparation import BUDGET_PAYLOAD_SHA256, PROTOCOL_SHA256 as BASE_PROTOCOL_SHA256
from core.mt_bicl_v2_training_run import preflight, run_seed, seal_selection
from core.prior_run_lock import PriorRunLock


def main() -> int:
    """0=stage xong (kể cả kết quả khoa học âm),1=lỗi,2=preflight bất khả thi,3=pause."""
    parser = argparse.ArgumentParser(description="Train v2 theo protocol đã khóa, không LLM/API")
    commands = parser.add_subparsers(dest="command",required=True)
    commands.add_parser("check-inputs")
    commands.add_parser("preflight")
    train = commands.add_parser("train")
    train.add_argument("--seed",type=int,choices=SEEDS,required=True)
    train.add_argument("--resume",action="store_true")
    train.add_argument("--session-minutes",type=float)
    commands.add_parser("seal")
    evaluation = commands.add_parser("evaluate")
    evaluation.add_argument("--resume",action="store_true")
    evaluation.add_argument("--session-minutes",type=float)
    verify = commands.add_parser("verify")
    verify.add_argument("--replay",action="store_true")
    args = parser.parse_args()
    limit = getattr(args,"session_minutes",None)
    if limit is not None and not 0 < limit <= 240:parser.error("session-minutes phải trong(0,240]")
    if args.command == "check-inputs":
        load_inputs(ROOT)
        print("Source/runtime/teacher/pilot PASS; validation5000+swap5000, selection2021=248; chưa CUDA/optimizer/test/API.")
        return 0
    requested,started = False,perf_counter()
    def handle_stop(signum:int, frame:object) -> None:
        """Train/evaluate pause tại ranh giới an toàn; stage khác dừng để chạy lại nguyên lệnh."""
        nonlocal requested
        if args.command not in ("train","evaluate"):raise KeyboardInterrupt()
        requested = True
        print("Đã nhận pause; chờ hoàn tất bước/assessment/stage hiện tại và ghi checkpoint.",flush=True)
    def stop() -> bool:
        """Giới hạn phiên không phụ thuộc metric và không cấp lại ngân sách chung."""
        return requested or (limit is not None and perf_counter()-started >= limit*60)
    for event in (signal.SIGINT,*([signal.SIGBREAK] if hasattr(signal,"SIGBREAK") else [])):
        signal.signal(event,handle_stop)
    budget_identity = {"protocol_sha256":BASE_PROTOCOL_SHA256,"grant_payload_sha256":BUDGET_PAYLOAD_SHA256,
                       "cap_seconds":14400,"W10_stop":"2026-11-01"}
    if not (ROOT/NAMESPACE/"active_budget_v2.json").exists():
        raise ValueError("Thiếu ngân sách teacher/pilot đã nghiệm thu; cấm tạo lại quỹ4 giờ")
    with PriorRunLock(ROOT/NAMESPACE,content_hash(budget_identity)):
        with ActiveBudget(ROOT/NAMESPACE/"active_budget_v2.json",budget_identity):
            inputs = load_inputs(ROOT)
            if inputs["budget_identity"] != budget_identity:raise ValueError("Identity ngân sách không khớp")
        if args.command == "preflight":
            result = preflight(ROOT,inputs)
            print(f"Preflight={result['status']}; batch={result['physical_batch']}; dự toán còn={result['projected_remaining_seconds']:.1f}s; quỹ còn={result['remaining_active_seconds']:.1f}s.")
            return 0 if result["status"] == "PASS" else 2
        if args.command == "train":
            status = run_seed(ROOT,inputs,args.seed,resume=args.resume,stop=stop)
            print(f"Seed{args.seed}: {status}.")
            return 3 if status == "PAUSED" else 0
        if args.command == "seal":
            with ActiveBudget(ROOT/NAMESPACE/"active_budget_v2.json",inputs["budget_identity"]) as budget:
                result = seal_selection(ROOT,inputs,budget=budget)
                export_candidate(ROOT,inputs,result)
            print("Selection đã khóa: "+result["status"]+"; chưa forward student test.")
            return 0
        if args.command == "evaluate":
            status = evaluate_final(ROOT,inputs,resume=args.resume,stop=stop)
            print("Đánh giá: "+status+"; development/Decision chưa được cấp.")
            return 3 if status == "PAUSED" else 0
        result = verify_final(ROOT,inputs,replay=args.replay)
        print(f"Integrity={result['integrity']}; replay={result['replay']}; cơ chế={result['candidate_mechanism_status']}; release={result['release_status']}.")
        return 0


if __name__ == "__main__":
    try:raise SystemExit(main())
    except KeyboardInterrupt:
        print("Đã dừng; giữ artifacts/budget, chạy lại đúng lệnh để tiếp tục.",file=sys.stderr)
        raise SystemExit(3)
    except (ValueError,RuntimeError,OSError,KeyError,TypeError) as error:
        print("Dừng, giữ nguyên bằng chứng/checkpoint: "+str(error),file=sys.stderr)
        raise SystemExit(1)
