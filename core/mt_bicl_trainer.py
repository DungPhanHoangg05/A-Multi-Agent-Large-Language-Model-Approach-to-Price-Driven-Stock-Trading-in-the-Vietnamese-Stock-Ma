"""Điều phối preflight/train/resume/seal cố định; không làm mechanism gate W10-07."""

from __future__ import annotations

from copy import deepcopy
import gc
import os
from pathlib import Path
import tempfile
from time import perf_counter
from typing import Any, Callable
from uuid import uuid4

import numpy as np
import torch

from core.mt_bicl_bank import content_hash
from core.mt_bicl_batches import TrainingBatchSource
from core.mt_bicl_model import MTBiCLLearner
from core.mt_bicl_training import (configure, evaluate_selection, make_optimizer, optimizer_step,
                                   restore_rng, selection_key, selection_metrics)
from core.mt_bicl_training_io import (RunBudget, checkpoint_payload, file_hash, load_checkpoint,
                                      read_manifest, save_checkpoint, write_manifest)
from core.prior_run_lock import safe_path


def gpu_identity() -> dict[str, Any]:
    """Khóa GPU/CUDA cho preflight và resume, không tự chuyển sang CPU hoặc AMP."""
    device = configure(0, cuda=True)
    properties = torch.cuda.get_device_properties(device)
    return {"name": properties.name, "memory_bytes": int(properties.total_memory),
            "capability": list(torch.cuda.get_device_capability(device)), "cuda": torch.version.cuda,
            "device_count": torch.cuda.device_count()}


def _packets(batch: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Chỉ packet numeric vào model; metadata nguồn/nhãn latent không đi qua forward."""
    if len(batch) != 128 or [r["domain"] for r in batch] != ["synthetic", "market"]*64:
        raise ValueError("Batch production phải interleave đúng 64 synthetic/64 market")
    return [r["packed"] for r in batch]


def _relative_record(directory: Path, path: Path, record: dict[str, Any]) -> dict[str, Any]:
    """Manifest dùng đường dẫn tương đối trong run, không dựa vào cwd khi resume."""
    return {**record, "file": path.relative_to(directory).as_posix()}


def _same_tree(left: Any, right: Any) -> bool:
    """Đối soát checkpoint mốc đã ghi nhưng transaction manifest bị ngắt."""
    if isinstance(left, torch.Tensor):
        return isinstance(right, torch.Tensor) and torch.equal(left.cpu(), right.cpu())
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(_same_tree(left[k], right[k]) for k in left)
    if isinstance(left, (list, tuple)):
        return len(left) == len(right) and all(_same_tree(a, b) for a, b in zip(left, right))
    return left == right


def save_resume(budget: RunBudget, model: MTBiCLLearner, optimizer: torch.optim.Optimizer,
                seed: int, step: int, physical: int) -> None:
    """Ghi file mới trước swap pointer atomic; crash không làm pointer trỏ byte đã bị ghi đè."""
    state = budget.state["seeds"][str(seed)]
    previous = state["resume"]
    path = budget.directory/f"seed{seed}/resume-{step:05d}-{uuid4().hex}.pt"
    payload = checkpoint_payload(model, optimizer, identity=content_hash(budget.identity),
                                 seed=seed, step=step, physical_batch=physical)
    state["resume"] = _relative_record(budget.directory, path, save_checkpoint(path, payload))
    budget.save()
    if previous is not None and "/resume-" in previous["file"]:
        try:
            safe_path(budget.directory, previous["file"]).unlink(missing_ok=True)
        except PermissionError:
            print("Giữ file resume cũ do Windows đang giữ handle; pointer mới đã lưu an toàn.", flush=True)


def preflight(budget: RunBudget, source: TrainingBatchSource, rows: list[dict[str, Any]],
              stop: Callable[[], bool]) -> bool:
    """Đo 100 optimizer step pipeline thật; chỉ giảm physical batch khi CUDA OOM trước train."""
    gpu = gpu_identity()
    if budget.state["preflight"] is not None:
        report = read_manifest(budget.directory/"preflight.json")
        if report != budget.state["preflight"] or report["gpu"] != gpu or report["status"] != "PASS":
            raise ValueError("Preflight/GPU không khớp trạng thái đã lưu")
        budget.check()
        print("Preflight đã PASS cùng identity; giữ physical batch đã chốt, không chạy lại.", flush=True)
        return True
    if any(s["status"] != "PENDING" for s in budget.state["seeds"].values()):
        raise ValueError("Không chạy lại preflight sau khi đã bắt đầu train")
    attempts = budget.state.setdefault("preflight_attempts", [])
    for physical in (128, 64, 32):
        budget.check()
        device = configure(0, cuda=True)
        model = MTBiCLLearner().to(device)
        optimizer = make_optimizer(model)
        durations, losses = [], []
        started = perf_counter()
        torch.cuda.reset_peak_memory_stats(device)
        try:
            for step in range(100):
                budget.check()
                tick = perf_counter()
                batch = source.batch(step, model_seed=0, preflight=True)
                losses.append(optimizer_step(model, optimizer, _packets(batch), physical, device))
                torch.cuda.synchronize(device)
                durations.append(perf_counter()-tick)
                if (step+1) % 10 == 0:
                    print(f"Preflight batch{physical}: {step+1}/100, loss={losses[-1]:.6f}", flush=True)
                if stop():
                    attempts.append({"physical_batch": physical, "status": "INTERRUPTED_WEIGHTS_DISCARDED",
                                     "completed_steps": step+1, "seconds": perf_counter()-started})
                    budget.save()
                    return False
            tick = perf_counter()
            evaluate_selection(model, rows, physical, device)
            # File tạm tự xóa khi đóng handle; weights preflight không trở thành candidate/resume.
            with tempfile.TemporaryFile(dir=budget.directory) as handle:
                torch.save(checkpoint_payload(model, optimizer, identity=content_hash(budget.identity),
                           seed=0, step=100, physical_batch=physical), handle)
                handle.flush()
                os.fsync(handle.fileno())
                size = handle.tell()
                handle.seek(0)
                torch.load(handle, map_location="cpu", weights_only=True)
            evaluation_io = perf_counter()-tick
            attempts.append({"physical_batch": physical, "status": "PASS", "completed_steps": 100,
                             "seconds": perf_counter()-started})
            # Gồm selection/checkpoint lúc train và 30 replay lúc seal, thêm 25% dự phòng.
            forecast = 1.25*(float(np.quantile(durations, .95, method="linear"))*30000+evaluation_io*60)
            report = {"version": "mt_bicl_real_preflight_v1", "status": "PASS", "gpu": gpu,
                      "identity_sha256": content_hash(budget.identity), "physical_batch": physical,
                      "effective_batch": 128, "accumulation": 128//physical, "steps": 100,
                      "step_seconds": durations, "losses": losses, "evaluation_checkpoint_seconds": evaluation_io,
                      "checkpoint_bytes": size, "forecast_remaining_seconds_with_25pct_margin": forecast,
                      "peak_allocated_bytes": int(torch.cuda.max_memory_allocated(device)),
                      "weights_retained": False, "attempts": deepcopy(attempts)}
            budget.check(forecast_seconds=forecast)
            write_manifest(budget.directory/"preflight.json", report)
            budget.state.update(preflight=report, status="READY_TO_TRAIN")
            budget.save()
            print(f"Preflight PASS: batch{physical}, accumulation={128//physical}, "
                  f"dự toán phần còn lại {forecast/3600:.2f} giờ; bỏ weights preflight.", flush=True)
            return True
        except torch.cuda.OutOfMemoryError:
            attempts.append({"physical_batch": physical, "status": "CUDA_OOM_WEIGHTS_DISCARDED",
                             "completed_steps": len(durations), "seconds": perf_counter()-started})
            budget.save()
            print(f"CUDA OOM trước train tại batch{physical}; thử mức physical batch kế tiếp đã đăng ký.", flush=True)
        finally:
            del model, optimizer
            gc.collect()
            torch.cuda.empty_cache()
    budget.state["status"] = "INCOMPLETE_NO_CANDIDATE"
    budget.save()
    raise RuntimeError("CUDA OOM ở cả batch128/64/32; không đổi kiến trúc hoặc precision")


def _milestone(budget: RunBudget, model: MTBiCLLearner, optimizer: torch.optim.Optimizer,
               rows: list[dict[str, Any]], seed: int, step: int, physical: int,
               device: torch.device) -> dict[str, Any]:
    """Commit checkpoint/predictions bất biến rồi cập nhật index; phục hồi orphan bằng so toàn state."""
    result = evaluate_selection(model, rows, physical, device)
    payload = checkpoint_payload(model, optimizer, identity=content_hash(budget.identity),
                                 seed=seed, step=step, physical_batch=physical)
    path = budget.directory/f"seed{seed}/checkpoint-{step:05d}.pt"
    if path.exists():
        record = {"file": path.relative_to(budget.directory).as_posix(), "sha256": file_hash(path),
                  "bytes": path.stat().st_size, "seed": seed, "step": step, "physical_batch": physical}
        if not _same_tree(load_checkpoint(budget.directory, record, content_hash(budget.identity)), payload):
            raise ValueError("Checkpoint orphan khác state vừa replay; không ghi đè")
    else:
        record = _relative_record(budget.directory, path, save_checkpoint(path, payload))
    selection_path = path.with_suffix(".selection.json")
    selection_payload = {"identity_sha256": content_hash(budget.identity), "seed": seed, "step": step,
                         "checkpoint_sha256": record["sha256"], **result}
    if selection_path.exists():
        if read_manifest(selection_path) != selection_payload:
            raise ValueError("Selection orphan khác dự báo vừa tính lại")
    else:
        write_manifest(selection_path, selection_payload)
    record.update(metrics=result["metrics"], selection_file=selection_path.relative_to(budget.directory).as_posix(),
                  selection_sha256=file_hash(selection_path))
    return record


def train_seed(budget: RunBudget, source: TrainingBatchSource, rows: list[dict[str, Any]], seed: int,
               *, resume: bool, stop: Callable[[], bool]) -> bool:
    """Train đủ 10.000 step; pause tại boundary an toàn, không đổi kế hoạch bằng metric."""
    report = budget.state["preflight"]
    if report is None or report["status"] != "PASS" or report["gpu"] != gpu_identity():
        raise ValueError("Cần preflight PASS cùng GPU trước train")
    if read_manifest(budget.directory/"preflight.json") != report:
        raise ValueError("Preflight khác manifest")
    for previous in (17, 42, 73):
        if previous == seed:
            break
        if budget.state["seeds"][str(previous)]["status"] != "COMPLETE":
            raise ValueError("Phải chạy theo thứ tự seed 17,42,73")
    state = budget.state["seeds"][str(seed)]
    if state["status"] == "COMPLETE":
        load_checkpoint(budget.directory, state["checkpoints"][-1], content_hash(budget.identity))
        print(f"Seed {seed} đã đủ 10.000 step; không train lại.", flush=True)
        return True
    if state["status"] != "PENDING" and not resume:
        raise ValueError("Seed đã bắt đầu; dùng --resume để giữ optimizer/RNG/step")
    if state["status"] not in ("PENDING", "RUNNING", "PAUSED"):
        raise ValueError("Seed lỗi integrity không được tự resume")
    physical = report["physical_batch"]
    device = configure(seed, cuda=True)
    model = MTBiCLLearner().to(device)
    optimizer = make_optimizer(model)
    step = 0
    if state["resume"] is not None:
        payload = load_checkpoint(budget.directory, state["resume"], content_hash(budget.identity))
        if payload["seed"] != seed or payload["physical_batch"] != physical:
            raise ValueError("Resume sai seed hoặc physical batch")
        model.load_state_dict(payload["model"], strict=True)
        optimizer.load_state_dict(payload["optimizer"])
        restore_rng(payload["rng"])
        step = payload["step"]
    state["status"], budget.state["status"] = "RUNNING", "TRAINING"
    budget.save()
    for index in range(step, 10000):
        budget.check()
        batch = source.batch(index, model_seed=seed)
        loss = optimizer_step(model, optimizer, _packets(batch), physical, device)
        completed = index+1
        if completed % 1000 == 0:
            record = _milestone(budget, model, optimizer, rows, seed, completed, physical, device)
            if any(r["step"] == completed for r in state["checkpoints"]):
                raise ValueError("Checkpoint step bị lặp trong index")
            state["checkpoints"].append(record)
        pause = stop()
        if completed % 100 == 0 or pause:
            save_resume(budget, model, optimizer, seed, completed, physical)
            print(f"Seed {seed}: {completed}/10000, loss={loss:.6f}, "
                  f"tổng thời gian đã dùng {budget.used()/3600:.2f}/12 giờ.", flush=True)
        budget.check()
        if pause and completed < 10000:
            state["status"], budget.state["status"] = "PAUSED", "PAUSED"
            budget.save()
            return False
    if [r["step"] for r in state["checkpoints"]] != list(range(1000, 10001, 1000)):
        raise ValueError("Seed thiếu một trong mười checkpoint đã đăng ký")
    state["status"] = "COMPLETE"
    budget.state["status"] = "TRAINING_COMPLETE" if all(s["status"] == "COMPLETE" for s in budget.state["seeds"].values()) else "READY_TO_TRAIN"
    budget.save()
    print(f"Seed {seed} hoàn tất 10.000 step, đủ mười checkpoint/selection 2021.", flush=True)
    return True


def verify_training(directory: Path, identity: dict[str, Any], *, allow_unsealed: bool = False,
                    snapshot: dict[str, Any] | None = None,
                    rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Kiểm toàn hash/index/selection; không tự gọi gate cơ chế hoặc phát hành development."""
    state = read_manifest(directory/"state.json") if snapshot is None else snapshot
    if state["identity"] != identity or state["active_since"] is not None:
        raise ValueError("Run khác identity hoặc session chưa đóng")
    if (state["version"] != "mt_bicl_training_run_v1" or set(state["seeds"]) != {"17", "42", "73"}
            or state["status"] not in ("TRAINING_COMPLETE", "SEALED_TRAINING_ONLY")):
        raise ValueError("Run chưa hoàn thành hoặc sai schema seed/status")
    if not np.isfinite(state["elapsed_seconds"]) or not 0 <= state["elapsed_seconds"] < 43200:
        raise ValueError("Run hết ngân sách, không được seal candidate")
    report = read_manifest(directory/"preflight.json")
    if (report != state["preflight"] or report["status"] != "PASS" or report["steps"] != 100
            or report["identity_sha256"] != content_hash(identity) or report["physical_batch"] not in (128, 64, 32)
            or report["effective_batch"] != 128 or report["accumulation"] != 128//report["physical_batch"]
            or report["weights_retained"] is not False or len(report["step_seconds"]) != 100
            or not np.isfinite(report["step_seconds"]).all() or min(report["step_seconds"]) <= 0):
        raise ValueError("Preflight không hợp lệ")
    expected_labels = None if rows is None else [(r["query"]["episode_id"], r["query"]["symbol"], r["supervised_target"]["y"]) for r in rows]
    all_records = []
    for seed in (17, 42, 73):
        group = state["seeds"][str(seed)]
        if group["status"] != "COMPLETE" or [r["step"] for r in group["checkpoints"]] != list(range(1000, 10001, 1000)):
            raise ValueError("Chưa đủ ba seed/30 checkpoint; W10-06 còn IN_PROGRESS")
        for record in group["checkpoints"]:
            if record["seed"] != seed or record["physical_batch"] != report["physical_batch"]:
                raise ValueError("Checkpoint sai seed/physical batch đã chốt")
            load_checkpoint(directory, record, content_hash(identity))
            path = safe_path(directory, record["selection_file"])
            if file_hash(path) != record["selection_sha256"]:
                raise ValueError("Selection file sai checksum")
            result = read_manifest(path)
            if (result["identity_sha256"] != content_hash(identity) or result["checkpoint_sha256"] != record["sha256"]
                    or result["metrics"] != record["metrics"] or result["seed"] != seed or result["step"] != record["step"]):
                raise ValueError("Selection không thuộc checkpoint/seed/step")
            if (result["dataset"] != "checkpoint_selection_2021"
                    or selection_metrics(result["records"]) != result["metrics"]
                    or (expected_labels is not None and [(r["episode_id"], r["symbol"], r["y"]) for r in result["records"]] != expected_labels)):
                raise ValueError("Selection khác tập ID/nhãn 2021 hoặc metrics không khớp dự báo")
            all_records.append(record)
        if group["resume"] is None or group["resume"]["step"] != 10000:
            raise ValueError("Thiếu resume cuối seed tại step10000")
        last = load_checkpoint(directory, group["checkpoints"][-1], content_hash(identity))
        resumed = load_checkpoint(directory, group["resume"], content_hash(identity))
        if not _same_tree(last, resumed):
            raise ValueError("Resume cuối khác weights/optimizer/RNG của checkpoint10000")
    candidate = min(all_records, key=selection_key)
    per_seed = {str(seed): min((r for r in all_records if r["seed"] == seed), key=selection_key) for seed in (17, 42, 73)}
    summary = {"candidate": candidate, "per_seed": per_seed, "checkpoints": all_records,
               "identity_sha256": content_hash(identity), "mechanism_status": "NOT_RUN", "development_allowed": False}
    if not allow_unsealed:
        seal = read_manifest(directory/"candidate_v1.json")
        if (seal["selection"] != summary or seal["identity"] != identity
                or seal["preflight_sha256"] != file_hash(directory/"preflight.json")
                or seal["selection_replayed"] is not True):
            raise ValueError("Seal candidate khác kết quả chọn bằng 2021")
        model_record = seal["model"]
        path = safe_path(directory, model_record["file"])
        if file_hash(path) != model_record["sha256"]:
            raise ValueError("Model export khác seal")
        exported = torch.load(path, map_location="cpu", weights_only=True)
        expected = load_checkpoint(directory, candidate, content_hash(identity))
        if (exported["identity_sha256"] != content_hash(identity)
                or exported["seed"] != candidate["seed"] or exported["step"] != candidate["step"]
                or not _same_tree(exported["model"], expected["model"])):
            raise ValueError("Model export không đúng weights được chọn")
    return summary


def seal_training(budget: RunBudget, rows: list[dict[str, Any]]) -> None:
    """Replay 30 checkpoint trên đúng 2021 trước seal, không tin metrics tự khai trong JSON."""
    if (budget.directory/"candidate_v1.json").exists():
        raise ValueError("Candidate đã seal; dùng verify, không ghi đè")
    if budget.state["preflight"] is None or budget.state["preflight"]["gpu"] != gpu_identity():
        raise ValueError("GPU seal khác preflight")
    # Snapshot chỉ trong RAM, không xóa active_since trên đĩa khi session còn chạy.
    snapshot = deepcopy(budget.state)
    snapshot["active_since"] = None
    snapshot["elapsed_seconds"] = budget.used()
    summary = verify_training(budget.directory, budget.identity, allow_unsealed=True, snapshot=snapshot, rows=rows)
    device = configure(0, cuda=True)
    model = MTBiCLLearner().to(device)
    physical = budget.state["preflight"]["physical_batch"]
    for record in summary["checkpoints"]:
        budget.check()
        payload = load_checkpoint(budget.directory, record, content_hash(budget.identity))
        model.load_state_dict(payload["model"], strict=True)
        actual = evaluate_selection(model, rows, physical, device)
        expected = read_manifest(safe_path(budget.directory, record["selection_file"]))
        if actual != {key: expected[key] for key in ("dataset", "records", "metrics")}:
            raise ValueError("Dự báo/metrics không khớp replay weights trên 2021")
        print(f"Seal đã replay seed {record['seed']} step {record['step']} trên 2021.", flush=True)
    payload = load_checkpoint(budget.directory, summary["candidate"], content_hash(budget.identity))
    path = budget.directory/f"candidate-{uuid4().hex}.pt"
    exported = {"version": "mt_bicl_inference_weights_v1", "identity_sha256": content_hash(budget.identity),
                "seed": payload["seed"], "step": payload["step"], "model": payload["model"]}
    # Writer atomic dùng chung; metadata optimizer/RNG không có trong inference export.
    record = save_checkpoint(path, {**exported, "physical_batch": physical})
    budget.check()
    write_manifest(budget.directory/"candidate_v1.json", {"version": "mt_bicl_candidate_v1", "identity": budget.identity,
                   "selection": summary, "model": record, "preflight_sha256": file_hash(budget.directory/"preflight.json"),
                   "selection_replayed": True, "mechanism_status": "NOT_RUN", "development_allowed": False})
    budget.state["status"] = "SEALED_TRAINING_ONLY"
    budget.save()
