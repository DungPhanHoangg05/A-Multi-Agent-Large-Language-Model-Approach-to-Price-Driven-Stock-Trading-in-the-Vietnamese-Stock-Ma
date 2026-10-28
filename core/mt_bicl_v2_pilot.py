"""Pilot v2 có giới hạn: hai packing, seed17, tiny-set cố định và diagnostic riêng."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any, Callable
from uuid import uuid4

import torch

from core.mt_bicl_bank import content_hash
from core.mt_bicl_trainer import gpu_identity
from core.mt_bicl_training import configure, restore_rng, rng_state
from core.mt_bicl_training_io import save_checkpoint
from core.mt_bicl_v2_distillation import evaluate, gradient_audit, make_optimizer, optimizer_step
from core.mt_bicl_v2_io import ActiveBudget, read_envelope, write_envelope
from core.mt_bicl_v2_student import CASES, LEGACY, PAIRED, DistilledStudent, collate_packets, pack_input, query_losses
from core.mt_bicl_v2_teacher import BetaBernoulliTeacher
from core.mt_bicl_v21_preparation import (
    CORPUS_VERSION, INDEX_VERSION as TEACHER_INDEX_VERSION, NAMESPACE, OUTPUT as TEACHER_OUTPUT,
    PROTOCOL_SHA256, TEACHER_VERSION, file_hash, load_inputs as load_teacher_inputs,
)
from core.prior_run_lock import safe_path

OUTPUT = NAMESPACE/"pilot_v2"
STATE_VERSION = "mt_bicl_pilot_state_v2"
REPORT_VERSION = "mt_bicl_pilot_report_v2"
CODE = ("core/mt_bicl_v2_student.py", "core/mt_bicl_v2_distillation.py", "core/mt_bicl_v2_pilot.py",
        "scripts/pilot_mt_bicl_v2.py", "core/mt_bicl_training.py", "core/mt_bicl_training_io.py",
        "core/mt_bicl_trainer.py")
FROZEN_TEACHER = {
    "teacher_fit.json": "7a89978336d1307d2b65a8a9712a26792451900f78351ba8bf03bf5ee277dc78",
    "index.json": "a1e20a1fe4036a6fc660b25302908efcac92cf08c241233b36284c9fbc18ed83",
    "diagnostic.json": "7b6435e3839c1953ef2e7e1ad3feb2dcabd2f51fed8c26b83d89a8c2a915caf2",
    "pilot_tiny.json": "91b1908f2253241593bb6ea97167f9ff84a75eb90d22db8bf7128c73bd087b2d",
    "synthetic_validation.json": "b5a761f7ac6b41cae4eb5a6af2fa8a57dbdf033c068b5fca40566eb5cb8d8721",
    "validation_swap.json": "8e5ee3dcb60a5125b480a01a1ff607cfe39f2c7ddfab87bfd5130146bdfd43ac",
    "synthetic_test.json": "f19db2a4678098fd5a7196d1b2789f202deedbfec45133e73501721a0de2bbec",
    "test_swap.json": "06432c5f0a4fd783c70adc1b019cd4acea5428a35242cb2cd28d14d5bbc739d1"}


def load_inputs(root: Path) -> dict[str, Any]:
    """Kiểm hash mọi corpus nhưng chỉ decode tiny/diagnostic; không mở student held-out."""
    base = load_teacher_inputs(root)
    directory = root/TEACHER_OUTPUT
    for name, expected in FROZEN_TEACHER.items():
        if file_hash(directory/name) != expected:
            raise ValueError("Teacher/corpus khác bản nghiệm thu: "+name)
    fitted = read_envelope(directory/"teacher_fit.json", TEACHER_VERSION)
    index = read_envelope(directory/"index.json", TEACHER_INDEX_VERSION)
    if (not fitted["converged"] or fitted["iterations"] != 237 or fitted["max_pi_delta"] >= 1e-10
            or fitted["identity"] != base["identity"] or index["status"] != "COMPLETE_TEACHER_ORACLE_ONLY"):
        raise ValueError("Teacher chưa đủ điều kiện pilot")
    teacher = BetaBernoulliTeacher(fitted["pi"])
    rows = {}
    for stream, count in (("pilot_tiny", 32), ("diagnostic", 1000)):
        corpus = read_envelope(directory/(stream+".json"), CORPUS_VERSION)
        if (corpus["stream"] != stream or corpus["identity"] != base["identity"]
                or len(corpus["episodes"]) != count
                or [row["index"] for row in corpus["episodes"]] != list(range(count))):
            raise ValueError("Sai corpus/ID cho pilot")
        for row in corpus["episodes"]:
            if abs(teacher.predict(row["input"])["probability"]-row["oracle"]["probability"]) > 1e-12:
                raise ValueError("q pilot không đúng posterior từ input đang thấy")
        rows[stream] = corpus["episodes"]
    identity = {"version": "mt_bicl_pilot_identity_v2", "protocol_sha256": PROTOCOL_SHA256,
                "teacher_identity_sha256": content_hash(base["identity"]),
                "teacher_artifacts_sha256": FROZEN_TEACHER,
                "code_sha256": {name: file_hash(root/name) for name in CODE},
                "runtime": base["protocol"]["runtime"], "seed": 17,
                "pilot_recipe": base["protocol"]["training"]["pilots"],
                "precision": "FP32_NO_AMP_NO_TF32", "student_heldout_forward": False}
    return {"identity": identity, "budget_identity": base["budget_identity"], "rows": rows}


def packets(inputs: dict[str, Any], packing: str, stream: str) -> list[dict[str, Any]]:
    """Chỉ chuyển input D/C/x và q; latent/query_y/source rows không đi qua tokenizer."""
    if stream not in ("pilot_tiny", "diagnostic"):
        raise ValueError("Pilot không được forward validation/test hoặc dữ liệu thị trường")
    return [pack_input(row["input"], teacher_q=row["oracle"]["probability"], packing=packing)
            for row in inputs["rows"][stream]]


def choose_capacity(inputs: dict[str, Any], device: torch.device, budget: ActiveBudget) -> dict[str, Any]:
    """Chỉ thử forward/backward bỏ weights; fallback128/64/32 duy nhất khi CUDA OOM."""
    attempts = []
    def trial(physical: int, packing: str) -> None:
        """Không optimizer.step, metric selection hoặc weights được giữ từ capacity probe."""
        configure(17, cuda=device.type == "cuda")
        model = DistilledStudent(packing).to(device).train()
        # Giữ hai buffer FP32 như moment AdamW để capacity không bỏ sót bộ nhớ optimizer.
        moments = [torch.empty_like(parameter) for parameter in model.parameters() for _ in (0, 1)]
        batch_rows = packets(inputs, packing, "pilot_tiny")*4
        for start in range(0, 128, physical):
            batch = collate_packets(batch_rows[start:start+physical], device)
            loss = query_losses(model(batch["values"], batch["roles"], batch["slots"], batch["padding"]), batch).sum()/128
            loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1., error_if_nonfinite=True)
        del moments
        if device.type == "cuda":
            torch.cuda.synchronize()
    for physical in (128, 64, 32):
        budget.check()
        try:
            for packing in CASES:
                trial(physical, packing)
        except torch.cuda.OutOfMemoryError:
            attempts.append({"physical_batch": physical, "status": "CUDA_OOM"})
        else:
            attempts.append({"physical_batch": physical, "status": "PASS"})
            return {"physical_batch": physical, "accumulation": 128//physical,
                    "attempts": attempts, "optimizer_steps": 0, "weights_discarded": True}
        finally:
            if device.type == "cuda":
                torch.cuda.empty_cache()
    raise RuntimeError("Capacity không đủ ở batch32; dừng, không đổi architecture")


def _validate_capacity(value: dict[str, Any]) -> None:
    """Không nhận batch ngoài recipe hoặc đổi batch không có chuỗi OOM trước train."""
    physical = value["physical_batch"]
    if physical not in (128,64,32):
        raise ValueError("Physical batch ngoài protocol")
    prefix = (128,64,32)[:(128,64,32).index(physical)+1]
    expected = [{"physical_batch": batch, "status": "PASS" if batch == physical else "CUDA_OOM"} for batch in prefix]
    if (value["accumulation"] != 128//physical or value["attempts"] != expected
            or value["optimizer_steps"] != 0 or value["weights_discarded"] is not True):
        raise ValueError("Capacity không đúng fallback OOM trước pilot")


def _report_step(model: DistilledStudent, inputs: dict[str, Any], packing: str,
                 step: int, physical: int, device: torch.device) -> dict[str, Any]:
    """Chỉ tiny/diagnostic ở step0/250/500; không đổi cấu hình từ metric."""
    return {"step": step, "tiny": evaluate(model, packets(inputs, packing, "pilot_tiny"), physical, device),
            "diagnostic": evaluate(model, packets(inputs, packing, "diagnostic"), physical, device)}


def _fresh_result(inputs: dict[str, Any], packing: str, physical: int, device: torch.device,
                  budget: ActiveBudget) -> dict[str, Any]:
    """Replay từ seed17 đủ500 step, bỏ weights; không chọn lại hoặc thêm step tối ưu."""
    configure(17, cuda=device.type == "cuda")
    model = DistilledStudent(packing).to(device)
    optimizer = make_optimizer(model)
    tiny = packets(inputs, packing, "pilot_tiny")
    audit = gradient_audit(model, tiny, device)
    reports, history = [_report_step(model, inputs, packing, 0, physical, device)], []
    for step in range(1, 501):
        budget.check()
        history.append(optimizer_step(model, optimizer, tiny*4, physical, device))
        if step in (250, 500):
            reports.append(_report_step(model, inputs, packing, step, physical, device))
    return _case_payload(inputs, packing, physical, reports, history, audit)


def _case_payload(inputs: dict[str, Any], packing: str, physical: int, reports: list,
                  history: list, audit: dict[str, Any]) -> dict[str, Any]:
    """Receipt không chứa weights; đủ raw logits/q để kiểm lại metric và replay."""
    return {"identity": inputs["identity"], "packing": packing, "seed": 17,
            "optimizer_steps": 500, "physical_batch": physical, "accumulation": 128//physical,
            "reports": reports, "loss_history": history, "gradient_audit": audit,
            "weights_discarded": True, "training_allowed": False,
            "development_allowed": False, "decision_calls_allowed": False}


def _checkpoint(directory: Path, inputs: dict[str, Any], packing: str, case: dict[str, Any],
                model: DistilledStudent, optimizer: torch.optim.Optimizer, budget: ActiveBudget) -> dict[str, Any]:
    """Resume weights tạm trong transaction; bị xóa sau receipt durable và commit case."""
    step, physical = case["step"], case["physical_batch"]
    payload = {"version": "mt_bicl_checkpoint_v2", "identity_sha256": content_hash(inputs["identity"]),
               "protocol_sha256": PROTOCOL_SHA256, "teacher_sha256": FROZEN_TEACHER["teacher_fit.json"],
               "corpus_sha256": {n: FROZEN_TEACHER[n] for n in ("pilot_tiny.json", "diagnostic.json")},
               "source_sha256": inputs["identity"]["code_sha256"], "runtime": inputs["identity"]["runtime"],
               "seed": 17, "step": step, "packing": packing, "model": model.state_dict(),
               "optimizer": optimizer.state_dict(), "scheduler": None,
               "python_numpy_torch_cuda_rng": rng_state(), "active_budget_seconds": budget.used(),
               "physical_batch": physical, "accumulation": 128//physical}
    return save_checkpoint(directory/f"resume-{packing}-{step:04d}-{uuid4().hex}.pt", payload)


def _read_checkpoint(directory: Path, record: dict[str, Any], identity: dict[str, Any], packing: str) -> dict[str, Any]:
    """Kiểm hash/identity/counter trước torch.load weights_only và resume optimizer."""
    path = safe_path(directory, record["file"])
    if file_hash(path) != record["sha256"] or path.stat().st_size != record["bytes"]:
        raise ValueError("Checkpoint pilot khác binding")
    value = torch.load(path, map_location="cpu", weights_only=True)
    if (value["identity_sha256"] != content_hash(identity) or value["packing"] != packing
            or value["version"] != "mt_bicl_checkpoint_v2" or value["seed"] != 17
            or type(value["step"]) is not int or value["step"] != record["step"] or not 0 <= value["step"] <= 500
            or value["physical_batch"] != record["physical_batch"] or value["scheduler"] is not None
            or value["physical_batch"] not in (128,64,32) or value["accumulation"] != 128//value["physical_batch"]
            or value["protocol_sha256"] != PROTOCOL_SHA256 or value["source_sha256"] != identity["code_sha256"]
            or value["runtime"] != identity["runtime"] or value["teacher_sha256"] != FROZEN_TEACHER["teacher_fit.json"]
            or value["corpus_sha256"] != {n:FROZEN_TEACHER[n] for n in ("pilot_tiny.json","diagnostic.json")}):
        raise ValueError("Checkpoint pilot sai identity/step/packing")
    states = value["optimizer"]["state"]
    if value["step"] and (len(states) != len(value["model"]) or
                          any(float(state["step"]) != value["step"] for state in states.values())):
        raise ValueError("Optimizer counter không khớp step pilot")
    if any(not bool(torch.isfinite(t).all()) for item in states.values() for t in item.values()
           if isinstance(t, torch.Tensor)):
        raise ValueError("Optimizer pilot chứa giá trị không hữu hạn")
    groups = value["optimizer"]["param_groups"]
    if (len(groups) != 1 or groups[0]["lr"] != 3e-4 or groups[0]["weight_decay"] != .01
            or tuple(groups[0]["betas"]) != (.9, .999) or groups[0]["eps"] != 1e-8
            or groups[0]["foreach"] is not False or groups[0]["fused"] is not False):
        raise ValueError("Optimizer pilot khác recipe đã khóa")
    if any(t.dtype != torch.float32 or not bool(torch.isfinite(t).all()) for t in value["model"].values()):
        raise ValueError("Weights pilot không phải FP32 hữu hạn")
    return value


def _discard(directory: Path, identity: dict[str, Any], packing: str) -> None:
    """Chỉ xóa checkpoint tạm đúng identity/case trong thư mục pilot đã resolve."""
    for candidate in directory.glob(f"resume-{packing}-*.pt"):
        path = safe_path(directory, candidate.name)
        value = torch.load(path, map_location="cpu", weights_only=True)
        if value.get("identity_sha256") != content_hash(identity) or value.get("packing") != packing:
            raise ValueError("Không xóa weights không thuộc pilot hiện hành")
        path.unlink()


def run_pilots(root: Path, inputs: dict[str, Any], *, resume: bool, stop: Callable[[], bool],
               device: torch.device | None = None) -> dict[str, Any]:
    """Production bắt buộc CUDA; CPU chỉ được truyền tường minh từ unit test fixture."""
    directory = root/OUTPUT
    if not directory.resolve().is_relative_to(root.resolve()):
        raise ValueError("Thư mục pilot vượt workspace qua junction/symlink")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory/"state.json"
    actual_gpu = gpu_identity() if device is None else {"fixture_device": str(device)}
    device = torch.device("cuda:0") if device is None else device
    if path.exists():
        if not resume:
            raise ValueError("Pilot đã có; dùng --resume")
        state = read_envelope(path, STATE_VERSION)
        if state["identity"] != inputs["identity"] or state["gpu"] != actual_gpu:
            raise ValueError("Source/input/GPU đổi, không resume bằng identity mới")
    else:
        if not (root/NAMESPACE/"active_budget_v2.json").exists():
            raise ValueError("Thiếu ngân sách dùng chung, không reset quỹ")
        state = {"identity": inputs["identity"], "gpu": actual_gpu, "status": "RUNNING",
                 "capacity": None, "cases": {name: {"status": "PENDING"} for name in CASES},
                 "training_allowed": False, "development_allowed": False, "decision_calls_allowed": False}

    def save() -> None:
        """Commit pointer sau checkpoint/report durable, trước xóa weights tạm."""
        write_envelope(path, STATE_VERSION, state)

    with ActiveBudget(root/NAMESPACE/"active_budget_v2.json", inputs["budget_identity"]) as budget:
        if state["capacity"] is None:
            state["capacity"] = choose_capacity(inputs, device, budget)
            save()
        _validate_capacity(state["capacity"])
        physical = state["capacity"]["physical_batch"]
        for packing in CASES:
            case = state["cases"][packing]
            if case["status"] != "PENDING" and case["physical_batch"] != physical:
                raise ValueError("Không đổi physical batch giữa pilot/resume")
            if case["status"] == "COMPLETE":
                report_path = safe_path(directory, case["receipt"]["file"])
                if file_hash(report_path) != case["receipt"]["sha256"]:
                    raise ValueError("Receipt pilot đã commit bị sửa")
                continue
            if case["status"] != "REPORT_READY":
                configure(17, cuda=device.type == "cuda")
                model = DistilledStudent(packing).to(device)
                optimizer = make_optimizer(model)
                tiny = packets(inputs, packing, "pilot_tiny")
                if case["status"] == "PENDING":
                    case.update(status="RUNNING", step=0, physical_batch=physical, reports=[], loss_history=[], checkpoint=None)
                    case["gradient_audit"] = gradient_audit(model, tiny, device)
                    case["reports"].append(_report_step(model, inputs, packing, 0, physical, device))
                else:
                    checkpoint = _read_checkpoint(directory, case["checkpoint"], inputs["identity"], packing)
                    model.load_state_dict(checkpoint["model"])
                    optimizer.load_state_dict(checkpoint["optimizer"])
                    restore_rng(checkpoint["python_numpy_torch_cuda_rng"])
                for step in range(case["step"]+1, 501):
                    budget.check()
                    case["loss_history"].append(optimizer_step(model, optimizer, tiny*4, physical, device))
                    case["step"] = step
                    if step in (250, 500):
                        case["reports"].append(_report_step(model, inputs, packing, step, physical, device))
                        print(f"Pilot {packing}: {step}/500, tiny KL={case['reports'][-1]['tiny']['mean_kl_nat']:.8g}.", flush=True)
                    paused = stop()
                    if step % 25 == 0 or paused:
                        previous = case["checkpoint"]
                        case["checkpoint"] = _checkpoint(directory, inputs, packing, case, model, optimizer, budget)
                        save()
                        if previous is not None:
                            old = safe_path(directory, previous["file"])
                            if file_hash(old) != previous["sha256"]:
                                raise ValueError("Checkpoint cũ bị sửa trước cleanup")
                            old.unlink()
                    if paused and step < 500:
                        state["status"] = "PAUSED"
                        save()
                        return state
                value = _case_payload(inputs, packing, physical, case["reports"], case["loss_history"], case["gradient_audit"])
                report_path = directory/(packing+".json")
                write_envelope(report_path, REPORT_VERSION, value, immutable=True)
                case.update(status="REPORT_READY", receipt={"file": report_path.name, "sha256": file_hash(report_path)})
                save()
                del model, optimizer
            ready_path = safe_path(directory, case["receipt"]["file"])
            if file_hash(ready_path) != case["receipt"]["sha256"]:
                raise ValueError("Receipt REPORT_READY bị sửa; giữ weights để rà soát")
            ready = read_envelope(ready_path, REPORT_VERSION)
            if ready["identity"] != inputs["identity"] or ready["packing"] != packing:
                raise ValueError("Receipt REPORT_READY khác identity/case")
            _discard(directory, inputs["identity"], packing)
            case.update(status="COMPLETE", checkpoint=None, reports=[], loss_history=[])
            save()
        paired = read_envelope(directory/state["cases"][PAIRED]["receipt"]["file"], REPORT_VERSION)
        passed = paired["reports"][-1]["tiny"]["mean_kl_nat"] < .001
        state["status"] = "PILOT_PASS_AWAITING_PREFLIGHT" if passed else "STOP_PAIRED_TINY_FIT_NO_RELEASE"
        save()
    return state


def verify_pilots(root: Path, inputs: dict[str, Any], *, replay: bool,
                  device: torch.device | None = None) -> dict[str, Any]:
    """Đối soát receipt/metric; replay đủ500 bước/case từ seed17 vì weights đã bỏ."""
    directory = root/OUTPUT
    state = read_envelope(directory/"state.json", STATE_VERSION)
    actual_gpu = gpu_identity() if device is None else {"fixture_device": str(device)}
    device = torch.device("cuda:0") if device is None else device
    if state["identity"] != inputs["identity"] or state["gpu"] != actual_gpu:
        raise ValueError("Pilot khác source/input/GPU")
    if state["status"] not in ("PILOT_PASS_AWAITING_PREFLIGHT", "STOP_PAIRED_TINY_FIT_NO_RELEASE"):
        raise ValueError("Pilot chưa hoàn tất cả hai case")
    _validate_capacity(state["capacity"])
    if list(directory.glob("*.pt")):
        raise ValueError("Weights pilot chưa được bỏ hết")
    values = {}
    for packing in CASES:
        case = state["cases"][packing]
        if case["status"] != "COMPLETE" or case["step"] != 500 or case["checkpoint"] is not None:
            raise ValueError("Case pilot chưa complete")
        path = safe_path(directory, case["receipt"]["file"])
        if file_hash(path) != case["receipt"]["sha256"]:
            raise ValueError("Hash receipt pilot không khớp")
        value = read_envelope(path, REPORT_VERSION)
        if (value["identity"] != inputs["identity"] or value["optimizer_steps"] != 500
                or len(value["loss_history"]) != 500 or [r["step"] for r in value["reports"]] != [0,250,500]
                or not value["weights_discarded"] or value["packing"] != packing
                or value["physical_batch"] != state["capacity"]["physical_batch"]
                or value["gradient_audit"]["status"] != "PASS"
                or value["gradient_audit"]["nonzero_outside_query"] != 0
                or value["training_allowed"] or value["development_allowed"] or value["decision_calls_allowed"]):
            raise ValueError("Receipt pilot sai step/loss/schema")
        from core.mt_bicl_v2_distillation import metric_report
        for report in value["reports"]:
            for stream in ("tiny", "diagnostic"):
                metrics = report[stream]
                source = "pilot_tiny" if stream == "tiny" else "diagnostic"
                if metrics["teacher_q"] != [row["oracle"]["probability"] for row in inputs["rows"][source]]:
                    raise ValueError("q trong receipt không khớp corpus được phép dùng")
                actual = metric_report(metrics["raw_logits"], metrics["teacher_q"])
                if any(actual[key] != metrics[key] for key in actual):
                    raise ValueError("Metric pilot không khớp raw logits/q")
        values[packing] = value
    passed = values[PAIRED]["reports"][-1]["tiny"]["mean_kl_nat"] < .001
    if passed != (state["status"] == "PILOT_PASS_AWAITING_PREFLIGHT"):
        raise ValueError("Gate tiny-set không khớp receipt")
    if replay:
        with ActiveBudget(root/NAMESPACE/"active_budget_v2.json", inputs["budget_identity"]) as budget:
            for packing in CASES:
                expected = _fresh_result(inputs, packing, state["capacity"]["physical_batch"], device, budget)
                if expected != values[packing]:
                    raise ValueError("Pilot không khớp cold replay từ seed17: "+packing)
        proof = {"identity_sha256": content_hash(inputs["identity"]), "state_sha256": file_hash(directory/"state.json"),
                 "case_receipts": {packing: state["cases"][packing]["receipt"] for packing in CASES},
                 "gpu": actual_gpu, "status": "OPTIMIZER_REPLAY_MATCH", "steps_each_case": 500,
                 "weights_discarded": True, "paired_tiny_gate": "PASS" if passed else "FAIL"}
        write_envelope(directory/"replay_verification.json", "mt_bicl_pilot_replay_v2", proof, immutable=True)
    proof_path = directory/"replay_verification.json"
    replay_status = "NOT_RUN"
    if proof_path.exists():
        proof = read_envelope(proof_path, "mt_bicl_pilot_replay_v2")
        if (proof["identity_sha256"] != content_hash(inputs["identity"])
                or proof["state_sha256"] != file_hash(directory/"state.json")
                or proof["case_receipts"] != {packing: state["cases"][packing]["receipt"] for packing in CASES}
                or proof["gpu"] != actual_gpu or proof["status"] != "OPTIMIZER_REPLAY_MATCH"):
            raise ValueError("Proof replay pilot không khớp artifact hiện hành")
        replay_status = "PASS"
    return {"integrity": "PASS", "replay": replay_status,
            "paired_tiny_gate": "PASS" if passed else "FAIL", "status": state["status"],
            "training_allowed": False, "development_allowed": False, "decision_calls_allowed": False}
