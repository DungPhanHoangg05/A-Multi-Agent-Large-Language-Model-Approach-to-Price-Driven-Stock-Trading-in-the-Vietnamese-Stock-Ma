"""CLI offline cho kiểm input, preflight GPU, train/resume và seal MT-BICL."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import signal
import sys
from time import perf_counter

# Phải đặt trước import torch/CUDA; không thay dependency hoặc cấu hình runtime hệ thống.
os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.mt_bicl_bank import content_hash
from core.mt_bicl_batches import TrainingBatchSource, load_context
from core.mt_bicl_simulator import FiniteSimulator
from core.mt_bicl_trainer import preflight, seal_training, train_seed, verify_training
from core.mt_bicl_training import selection_rows
from core.mt_bicl_training_io import TRAINING_PATH, RunBudget, source_identity
from core.prior_run_lock import PriorRunLock


def main() -> int:
    """Không nhận cờ thay architecture/step/seed/split; pause chỉ đổi thời điểm resume."""
    parser = argparse.ArgumentParser(description="Train MT-BICL theo protocol đã khóa, không LLM/API")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check-inputs", help="Kiểm nguồn/runtime và tập train/2021, không chạy optimizer")
    sub.add_parser("preflight", help="Đo 100 optimizer step thật trước train, bỏ weights")
    training = sub.add_parser("train", help="Train một seed đủ 10000 step hoặc pause để resume")
    training.add_argument("--seed", type=int, choices=(17, 42, 73), required=True)
    training.add_argument("--resume", action="store_true")
    training.add_argument("--session-minutes", type=float, help="Tự pause sau số phút; không giảm tổng step")
    sub.add_parser("seal", help="Replay selection 2021 của 30 checkpoint và seal candidate")
    sub.add_parser("verify", help="Đối soát source/hash/index/metrics/model đã seal, không chạy lại optimizer")
    args = parser.parse_args()
    if args.command == "train" and args.session_minutes is not None and not 0 < args.session_minutes <= 720:
        parser.error("session-minutes phải hữu hạn trong (0,720]")
    directory = ROOT/TRAINING_PATH
    if not directory.resolve().is_relative_to((ROOT/"outputs/bayesian_benchmark/mt_bicl_v1").resolve()):
        parser.error("Run directory không được thoát namespace qua symlink/junction")
    requested = False

    def handle_stop(signum: int, frame: object) -> None:
        """Hoãn Ctrl+C tới boundary sau optimizer.step, không lưu weights đang update dở."""
        nonlocal requested
        requested = True
        print("Đã nhận yêu cầu dừng; chờ kết thúc step hiện tại và lưu checkpoint an toàn.", flush=True)

    started = perf_counter()
    limit = getattr(args, "session_minutes", None)

    def stop() -> bool:
        """Thời lượng phiên không phải early stopping bằng loss/validation."""
        return requested or (limit is not None and perf_counter()-started >= limit*60)

    identity = source_identity(ROOT)
    if args.command == "check-inputs":
        context = load_context(ROOT)
        source = TrainingBatchSource(FiniteSimulator.from_locked(ROOT), context)
        rows = selection_rows(context)
        print(f"Input/runtime PASS; train {sum(map(len, source.groups.values()))} query, "
              f"selection 2021 {len(rows)} query; identity={content_hash(identity)}.")
        print("Giữ protocol: ba seed 17/42/73, 10000 step/seed, effective batch128; chưa train/LLM.")
        return 0
    if not directory.is_dir() and args.command != "preflight":
        raise ValueError("Chưa có run; chạy check-inputs rồi preflight trước")
    with PriorRunLock(directory, content_hash(identity)):
        if args.command == "verify":
            summary = verify_training(directory, identity, rows=selection_rows(load_context(ROOT)))
            selected = summary["candidate"]
            print(f"Artifact/hash/index/selection/model PASS: seed{selected['seed']} step{selected['step']}; "
                  "mechanism NOT_RUN, chưa release development.")
            return 0
        if args.command == "seal" and (directory/"candidate_v1.json").exists():
            verify_training(directory, identity, rows=selection_rows(load_context(ROOT)))
            print("Candidate đã seal và đối soát PASS; giữ nguyên artifact.")
            return 0
        for event in (signal.SIGINT, *([signal.SIGBREAK] if hasattr(signal, "SIGBREAK") else [])):
            signal.signal(event, handle_stop)
        with RunBudget(directory, identity) as budget:
            budget.check()
            context = load_context(ROOT)
            rows = selection_rows(context)
            if args.command == "seal":
                seal_training(budget, rows)
                print("Đã seal training/candidate bằng 2021; chưa làm gate cơ chế/validation 2022.")
                return 0
            source = TrainingBatchSource(FiniteSimulator.from_locked(ROOT), context)
            if args.command == "preflight":
                complete = preflight(budget, source, rows, stop)
            else:
                complete = train_seed(budget, source, rows, args.seed, resume=args.resume, stop=stop)
            if not complete:
                print("Đã pause an toàn, mã thoát 3. Chạy lại cùng lệnh train --seed ... --resume; "
                      "preflight bị ngắt thì chạy lại preflight, weights cũ đã bỏ.")
                return 3
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, OSError) as error:
        print(f"Dừng, giữ bằng chứng hiện có: {error}", file=sys.stderr, flush=True)
        raise SystemExit(1) from error
