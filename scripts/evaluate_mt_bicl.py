"""CLI đánh giá frozen MT-BICL; kết quả FAIL vẫn được lưu đầy đủ, không train lại."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import signal
import sys

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.mt_bicl_bank import content_hash
from core.mt_bicl_evaluation_run import EVALUATION_PATH, evaluate_run, load_inputs, verify_evaluation
from core.prior_run_lock import PriorRunLock


def main() -> int:
    """Cố định corpus/ngưỡng/checkpoint; không cờ chọn seed lại theo kết quả test."""
    parser = argparse.ArgumentParser(description="Kiểm cơ chế và validation 2022 MT-BICL offline")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check-inputs", help="Kiểm nguồn, training receipt, corpus và PIT validation")
    run = sub.add_parser("run", help="Đánh giá cả ba seed và baseline, không optimizer")
    run.add_argument("--resume", action="store_true")
    verify = sub.add_parser("verify", help="Kiểm hash và tính lại metric từ raw logits")
    verify.add_argument("--replay", action="store_true", help="Replay GPU inference và baseline để đối chiếu raw logits")
    args = parser.parse_args()
    directory = ROOT/EVALUATION_PATH
    if not directory.resolve().is_relative_to((ROOT/"outputs/bayesian_benchmark/mt_bicl_v1").resolve()):
        parser.error("Evaluation directory không được thoát namespace")
    inputs = load_inputs(ROOT)
    if args.command == "check-inputs":
        print(f"Input/PIT/receipt PASS: 5000 test, 5000 cặp, {len(inputs['rows'])} validation 2022; "
              f"candidate cố định seed{inputs['selection']['candidate']['seed']}, "
              f"identity={content_hash(inputs['identity'])}.")
        return 0
    if not directory.is_dir() and args.command == "verify":
        raise ValueError("Chưa có evaluation; chạy run trước")
    requested = False
    def pause(signum: int, frame: object) -> None:
        """Không ngắt file đang ghi; hoàn thành stage hiện tại rồi pause."""
        nonlocal requested
        requested = True
        print("Đã nhận Ctrl+C; chờ lưu xong stage hiện tại rồi pause.", flush=True)
    for event in (signal.SIGINT, *([signal.SIGBREAK] if hasattr(signal, "SIGBREAK") else [])):
        signal.signal(event, pause)
    with PriorRunLock(directory, content_hash(inputs["identity"])):
        if args.command == "run":
            if not evaluate_run(ROOT, directory, inputs, resume=args.resume, stop=lambda: requested):
                print("Đã pause an toàn, mã thoát 3; tiếp tục bằng run --resume.")
                return 3
            report = verify_evaluation(ROOT, directory, inputs, replay=False)
        else:
            report = verify_evaluation(ROOT, directory, inputs, replay=args.replay)
        replay_status = "PASS" if (directory/"replay_verification.json").is_file() else "NOT_RUN"
        print(f"Báo cáo/integrity PASS; replay={replay_status}; gate cơ chế candidate={report['candidate_mechanism_status']}; "
              f"release={report['release_status']}; development_allowed=false.")
        for name, result in report["candidate_market_comparisons"].items():
            print(f"2022 Full so {name}: {result['performance']}, "
                  f"delta log loss={result['delta_macro_log_loss_full_minus_baseline']:.6f}, "
                  f"delta Brier={result['delta_macro_brier_full_minus_baseline']:.6f}.")
        print("Mã thoát 0 chỉ xác nhận hoàn thành/khớp báo cáo; không đổi FAIL cơ chế thành PASS.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, OSError) as error:
        print(f"Dừng đánh giá, giữ bằng chứng: {error}", file=sys.stderr, flush=True)
        raise SystemExit(1) from error
