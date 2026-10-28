"""Preflight, train ba seed, checkpoint có thể tiếp tục và selection seal v2."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any, Callable
from uuid import uuid4

import numpy as np
import torch

from core.mt_bicl_bank import content_hash
from core.mt_bicl_trainer import gpu_identity
from core.mt_bicl_training import configure, restore_rng, rng_state
from core.mt_bicl_training_io import save_checkpoint
from core.mt_bicl_v2_distillation import make_optimizer, optimizer_step, scheduled_lr, tensor_hash
from core.mt_bicl_v2_experiment import (
    ASSESSMENT_VERSION, NAMESPACE, OUTPUT, SEAL_VERSION, SEEDS, STEPS, checkpoint_logits,
    selection, training_batch, validation_summary,
)
from core.mt_bicl_v2_io import ActiveBudget, read_envelope, write_envelope
from core.mt_bicl_v2_student import DistilledStudent
from core.mt_bicl_v21_preparation import file_hash
from core.prior_run_lock import safe_path

STATE_VERSION = "mt_bicl_training_state_v2"
PREFLIGHT_VERSION = "mt_bicl_preflight_v2"
CHECKPOINT_VERSION = "mt_bicl_checkpoint_v2"


def projected_seconds(step:float, checkpoint:float, assessment:float) -> float:
    """Tính đủ600 snapshot định kỳ,60 assessment/replay và ba test/replay tối đa."""
    return float(15000*step+120*assessment+600*checkpoint+6*assessment*(30768/20248)+120)


def validate_preflight(value:dict[str,Any], inputs:dict[str,Any]) -> None:
    """Đối soát recipe/timing/projection receipt, không nhận status PASS tự khai thiếu100 bước."""
    physical = value["physical_batch"]
    times = value["step_seconds"]
    if (value["identity"] != inputs["identity"] or value["gpu"] != inputs["pilot_gpu"]
            or value["steps"] != 100 or value["weights_discarded"] is not True
            or physical not in (128,64,32) or value["accumulation"] != 128//physical or len(times) != 100
            or any(type(t) not in (float,int) or not np.isfinite(t) or t < 0 for t in times)):
        raise ValueError("Receipt preflight không đúng100 bước/batch/identity")
    timing = [value[k] for k in ("checkpoint_seconds","validation_20248_queries_seconds","remaining_active_seconds")]
    if not np.isfinite(timing).all() or min(timing[:2]) < 0:raise ValueError("Timing preflight không hợp lệ")
    conservative = max(float(np.mean(times)),float(np.quantile(times,.95,method="linear")))
    estimate = projected_seconds(conservative,*timing[:2])
    expected = "PASS" if estimate <= value["remaining_active_seconds"] else "INFEASIBLE_WITHIN_REMAINING_BUDGET"
    if value["conservative_step_seconds"] != conservative or value["projected_remaining_seconds"] != estimate or value["status"] != expected:
        raise ValueError("Projection/status preflight không khớp timing đã đo")
    trials = value["oom_trials"]
    if [r["physical_batch"] for r in trials] != list((128,64,32)[:(128,64,32).index(physical)]) or any(r["status"] != "OOM" or not 0 <= r["completed_steps"] < 100 for r in trials):
        raise ValueError("Physical batch không được giảm ngoài OOM-only")


def record(directory: Path, path: Path) -> dict[str, Any]:
    """Pointer tương đối, hash byte và kích thước, không nhận đường dẫn ngoài namespace."""
    return {"file":path.relative_to(directory).as_posix(),"sha256":file_hash(path),"bytes":path.stat().st_size}


def checked_path(directory: Path, pointer: dict[str, Any]) -> Path:
    """Kiểm byte trước đọc JSON hoặc pickle torch weights_only."""
    path = safe_path(directory,pointer["file"])
    if path.stat().st_size != pointer["bytes"] or file_hash(path) != pointer["sha256"]:
        raise ValueError("Artifact khác pointer đã khóa: "+pointer["file"])
    return path


def snapshot(inputs:dict[str,Any], model:DistilledStudent, optimizer:torch.optim.Optimizer,
             seed:int, step:int, physical:int, used:float) -> dict[str,Any]:
    """Đóng băng Adam/RNG/scheduler sau optimizer step đã hoàn thành."""
    return {"version":CHECKPOINT_VERSION,"identity_sha256":content_hash(inputs["identity"]),
            "seed":seed,"step":step,"physical_batch":physical,"accumulation":128//physical,
            "model":model.state_dict(),"optimizer":optimizer.state_dict(),"rng":rng_state(),
            "scheduler":{"completed_steps":step,"last_lr":scheduled_lr(step) if step else 3e-4},
            "active_seconds":used,"model_tensor_sha256":tensor_hash(model)}


def read_checkpoint(directory:Path, pointer:dict[str,Any], inputs:dict[str,Any],
                    *, seed:int, step:int, physical:int) -> dict[str,Any]:
    """Kiểm schema, Adam counter, lịch và FP32; không nhận checkpoint pilot/v1."""
    payload = torch.load(checked_path(directory,pointer),map_location="cpu",weights_only=True)
    if (set(payload) != {"version","identity_sha256","seed","step","physical_batch","accumulation",
                         "model","optimizer","rng","scheduler","active_seconds","model_tensor_sha256"}
            or payload["version"] != CHECKPOINT_VERSION or payload["identity_sha256"] != content_hash(inputs["identity"])
            or payload["seed"] != seed or payload["step"] != step or payload["physical_batch"] != physical
            or physical not in (128,64,32) or payload["accumulation"] != 128//physical
            or type(step) is not int or not 0 <= step <= 5000
            or not np.isfinite(payload["active_seconds"]) or payload["active_seconds"] < 0):
        raise ValueError("Checkpoint sai identity/step/seed/batch")
    lr = scheduled_lr(step) if step else 3e-4
    if payload["scheduler"] != {"completed_steps":step,"last_lr":lr}:
        raise ValueError("Scheduler không khớp step đã lưu")
    model = DistilledStudent()
    model.load_state_dict(payload["model"],strict=True)
    if tensor_hash(model) != payload["model_tensor_sha256"]:
        raise ValueError("Fingerprint model không khớp")
    if any(t.dtype != torch.float32 or not bool(torch.isfinite(t).all()) for t in payload["model"].values()):
        raise ValueError("Model không phải FP32 hữu hạn")
    optimizer = make_optimizer(model)
    expected_group = optimizer.state_dict()["param_groups"][0]
    expected_group["lr"] = lr
    if (set(payload["optimizer"]) != {"state","param_groups"}
            or payload["optimizer"]["param_groups"] != [expected_group]):
        raise ValueError("Cấu hình/parameter IDs AdamW khác optimizer đã khóa")
    optimizer.load_state_dict(payload["optimizer"])
    groups = optimizer.param_groups
    if len(groups) != 1 or groups[0]["lr"] != lr or groups[0]["betas"] != (.9,.999) or groups[0]["eps"] != 1e-8 or groups[0]["weight_decay"] != .01 or groups[0]["foreach"] is not False or groups[0]["fused"] is not False:
        raise ValueError("AdamW không đúng protocol")
    if step and len(optimizer.state) != len(list(model.parameters())):
        raise ValueError("Adam state thiếu parameter")
    if not step and optimizer.state:
        raise ValueError("Adam step0 đã có state")
    for parameter,state in optimizer.state.items():
        if set(state) != {"step","exp_avg","exp_avg_sq"} or float(state["step"]) != step:
            raise ValueError("Adam counter không khớp checkpoint")
        for name in ("exp_avg","exp_avg_sq"):
            tensor = state[name]
            if tensor.dtype != torch.float32 or tensor.shape != parameter.shape or not bool(torch.isfinite(tensor).all()):
                raise ValueError("Moment Adam sai shape/dtype/hữu hạn")
        if bool((state["exp_avg_sq"] < 0).any()):raise ValueError("Moment bậc hai Adam âm")
    return payload


def environment(inputs:dict[str,Any]) -> torch.device:
    """Chỉ dùng GPU/runtime đã nghiệm thu pilot; CPU chỉ dành unit test."""
    if gpu_identity() != inputs["pilot_gpu"]:raise ValueError("GPU khác pilot đã khóa")
    return torch.device("cuda")


def preflight(root:Path, inputs:dict[str,Any]) -> dict[str,Any]:
    """100 update thật, đo cả generation/teacher/IO/validation, bỏ toàn bộ weights."""
    directory = root/OUTPUT
    directory.mkdir(parents=True,exist_ok=True)
    path = directory/"preflight.json"
    if path.exists():
        result = read_envelope(path,PREFLIGHT_VERSION)
        validate_preflight(result,inputs)
        environment(inputs)
        return result
    device = environment(inputs)
    with ActiveBudget(root/NAMESPACE/"active_budget_v2.json",inputs["budget_identity"]) as budget:
        trials = []
        for physical in (128,64,32):
            configure(17,cuda=True)
            model = DistilledStudent().to(device)
            optimizer = make_optimizer(model)
            times = []
            try:
                for step in range(1,101):
                    budget.check()
                    tick = perf_counter()
                    packets = training_batch(inputs,step,17,preflight=True)
                    optimizer.param_groups[0]["lr"] = scheduled_lr(step)
                    optimizer_step(model,optimizer,packets,physical,device)
                    torch.cuda.synchronize()
                    times.append(perf_counter()-tick)
                    if step % 25 == 0:print(f"Preflight batch{physical}: {step}/100 bước.",flush=True)
                break
            except torch.cuda.OutOfMemoryError:
                trials.append({"physical_batch":physical,"status":"OOM","completed_steps":len(times)})
                del model,optimizer
                torch.cuda.empty_cache()
        else:raise RuntimeError("OOM ở batch32: dừng, không đổi model/effective batch")
        tick = perf_counter()
        probe = directory/(".preflight-"+uuid4().hex+".pt")
        try:
            save_checkpoint(probe,snapshot(inputs,model,optimizer,17,100,physical,budget.used()))
            read_checkpoint(directory,record(directory,probe),inputs,seed=17,step=100,physical=physical)
        finally:
            if probe.exists():probe.unlink()
        checkpoint_seconds = perf_counter()-tick
        tick = perf_counter()
        logits = checkpoint_logits(model,inputs,128,device,budget.check)
        assessment = {"logits":logits,"assessment":validation_summary(inputs,logits)}
        probe_report = directory/(".preflight-"+uuid4().hex+".json")
        try:
            write_envelope(probe_report,ASSESSMENT_VERSION,assessment,immutable=True)
            if read_envelope(probe_report,ASSESSMENT_VERSION) != assessment:raise ValueError("Assessment roundtrip không khớp")
        finally:
            if probe_report.exists():probe_report.unlink()
        assessment_seconds = perf_counter()-tick
        # Bao gồm 60 assessment, 60 replay và tối đa ba seed test cùng replay.
        conservative_step = max(float(np.mean(times)),float(np.quantile(times,.95,method="linear")))
        estimate = projected_seconds(conservative_step,checkpoint_seconds,assessment_seconds)
        remaining = inputs["budget_identity"]["cap_seconds"]-budget.used()
        result = {"identity":inputs["identity"],"gpu":inputs["pilot_gpu"],"physical_batch":physical,
                  "accumulation":128//physical,"steps":100,"weights_discarded":True,"oom_trials":trials,
                  "step_seconds":times,"conservative_step_seconds":conservative_step,
                  "checkpoint_seconds":checkpoint_seconds,"validation_20248_queries_seconds":assessment_seconds,
                  "remaining_active_seconds":remaining,"projected_remaining_seconds":estimate,
                  "projection_includes":"15000_UPDATES_600_SNAPSHOTS_60_ASSESSMENTS_60_REPLAYS_3_TESTS_WITH_REPLAY_IO_MARGIN",
                  "status":"PASS" if estimate <= remaining else "INFEASIBLE_WITHIN_REMAINING_BUDGET"}
        validate_preflight(result,inputs)
        write_envelope(path,PREFLIGHT_VERSION,result,immutable=True)
        del model,optimizer
        torch.cuda.empty_cache()
        return result


def read_state(directory:Path, inputs:dict[str,Any]) -> dict[str,Any]:
    """State chỉ điều phối; checkpoint/report còn phải đối soát độc lập."""
    state = read_envelope(directory/"state.json",STATE_VERSION)
    if state["identity"] != inputs["identity"] or state["gpu"] != inputs["pilot_gpu"]:
        raise ValueError("Training state khác source/GPU")
    if set(state["seeds"]) != {str(s) for s in SEEDS}:raise ValueError("Thiếu seed state")
    return state


def assess(directory:Path, inputs:dict[str,Any], case:dict[str,Any], seed:int,
           model:DistilledStudent, device:torch.device, budget:ActiveBudget) -> None:
    """Hoàn tất pending assessment trước update tiếp; receipt bất biến cho mọi checkpoint."""
    pending = case["pending"]
    step = pending["step"]
    payload = {"identity_sha256":content_hash(inputs["identity"]),"seed":seed,"step":step,
               "checkpoint":pending["checkpoint"],"model_tensor_sha256":tensor_hash(model),
               "logits":checkpoint_logits(model,inputs,128,device,budget.check)}
    payload["assessment"] = validation_summary(inputs,payload["logits"])
    path = directory/f"seed{seed}/checkpoint-{step:05d}.assessment.json"
    write_envelope(path,ASSESSMENT_VERSION,payload,immutable=True)
    case["reports"].append({"seed":seed,"step":step,"checkpoint":pending["checkpoint"],"report":record(directory,path)})
    case["pending"] = None
    print(f"Seed{seed} {step}/5000: cơ chế validation={payload['assessment']['mechanism_status']}; tiếp tục đủ protocol.",flush=True)


def _equivalent(a:Any,b:Any) -> bool:
    """So cây tensor/RNG chính xác khi nhận checkpoint mốc orphan sau hard crash."""
    if isinstance(a,torch.Tensor):return isinstance(b,torch.Tensor) and torch.equal(a,b)
    if isinstance(a,dict):return isinstance(b,dict) and a.keys() == b.keys() and all(_equivalent(a[k],b[k]) for k in a)
    if isinstance(a,(list,tuple)):return type(a) is type(b) and len(a) == len(b) and all(_equivalent(x,y) for x,y in zip(a,b))
    return type(a) is type(b) and a == b


def run_seed(root:Path, inputs:dict[str,Any], seed:int, *, resume:bool,
             stop:Callable[[],bool]=lambda:False) -> str:
    """Train đủ5000; pause chỉ theo người dùng/thời lượng, không theo metric."""
    directory = root/OUTPUT
    pre = read_envelope(directory/"preflight.json",PREFLIGHT_VERSION)
    validate_preflight(pre,inputs)
    if pre["identity"] != inputs["identity"] or pre["status"] != "PASS" or not pre["weights_discarded"]:
        raise ValueError("Cần preflight100 PASS cùng source trước train")
    physical = pre["physical_batch"]
    device = environment(inputs)
    path = directory/"state.json"
    if path.exists():
        state = read_state(directory,inputs)
        if not resume:raise ValueError("Đã có state: dùng --resume, không train lại")
    else:
        state = {"identity":inputs["identity"],"gpu":inputs["pilot_gpu"],"physical_batch":physical,
                 "preflight":record(directory,directory/"preflight.json"),
                 "seeds":{str(s):{"status":"PENDING","step":0,"resume":None,"pending":None,"reports":[],"loss_history":[]} for s in SEEDS}}
    if state["physical_batch"] != physical or checked_path(directory,state["preflight"]) != directory/"preflight.json":
        raise ValueError("Physical batch/preflight đã đổi")
    if any(state["seeds"][str(s)]["status"] != "COMPLETE" for s in SEEDS[:SEEDS.index(seed)]):
        raise ValueError("Phải train theo thứ tự17,42,73")
    case = state["seeds"][str(seed)]
    if case["status"] == "COMPLETE":return "COMPLETE"
    if (directory/"selection.json").exists():raise ValueError("Selection đã seal: không train thêm")
    def save() -> None:
        """Pointer chỉ đổi sau checkpoint fsync, trước xóa snapshot tạm cũ."""
        write_envelope(path,STATE_VERSION,state)
    with ActiveBudget(root/NAMESPACE/"active_budget_v2.json",inputs["budget_identity"]) as budget:
        configure(seed,cuda=True)
        model = DistilledStudent().to(device)
        optimizer = make_optimizer(model)
        if case["resume"] is not None:
            payload = read_checkpoint(directory,case["resume"],inputs,seed=seed,step=case["step"],physical=physical)
            if payload["active_seconds"] > budget.used():raise ValueError("Budget thấp hơn checkpoint, không reset")
            model.load_state_dict(payload["model"])
            optimizer.load_state_dict(payload["optimizer"])
            restore_rng(payload["rng"])
        elif case["step"] or case["reports"]:raise ValueError("State thiếu resume checkpoint")
        case["status"] = "RUNNING"
        save()
        if case["pending"] is not None:
            if case["pending"]["step"] != case["step"] or case["pending"]["checkpoint"] != case["resume"]:
                raise ValueError("Pending assessment không khớp checkpoint")
            assess(directory,inputs,case,seed,model,device,budget)
            save()
        for step in range(case["step"]+1,5001):
            budget.check()
            optimizer.param_groups[0]["lr"] = scheduled_lr(step)
            loss = optimizer_step(model,optimizer,training_batch(inputs,step,seed),physical,device)
            case["step"] = step
            case["loss_history"].append({"step":step,"lr":scheduled_lr(step),**loss})
            paused = stop()
            if step % 25 == 0 or paused:
                previous = case["resume"]
                fixed = step in STEPS
                cp = directory/f"seed{seed}"/(f"checkpoint-{step:05d}.pt" if fixed else "resume-"+uuid4().hex+".pt")
                payload = snapshot(inputs,model,optimizer,seed,step,physical,budget.used())
                if cp.exists():
                    old = read_checkpoint(directory,record(directory,cp),inputs,seed=seed,step=step,physical=physical)
                    if not _equivalent({k:v for k,v in old.items() if k != "active_seconds"},
                                       {k:v for k,v in payload.items() if k != "active_seconds"}):
                        raise ValueError("Checkpoint orphan khác replay; dừng, không ghi đè")
                    restore_rng(old["rng"])
                else:save_checkpoint(cp,payload)
                case["resume"] = record(directory,cp)
                if fixed:case["pending"] = {"step":step,"checkpoint":case["resume"]}
                save()
                if previous is not None and Path(previous["file"]).name.startswith("resume-"):
                    checked_path(directory,previous).unlink()
                if fixed:
                    assess(directory,inputs,case,seed,model,device,budget)
                    save()
                if paused and step < 5000:
                    case["status"] = "PAUSED"
                    save()
                    return "PAUSED"
        case["status"] = "COMPLETE"
        save()
        return "COMPLETE"


def verified_records(root:Path, inputs:dict[str,Any], *, replay:bool=False,
                     budget:ActiveBudget|None=None) -> tuple[dict[str,Any],list[dict[str,Any]]]:
    """Mọi seed đủ5000 và20 checkpoint; derive metric từ logits, replay tùy bước nghiệm thu."""
    directory = root/OUTPUT
    state = read_state(directory,inputs)
    pre = read_envelope(checked_path(directory,state["preflight"]),PREFLIGHT_VERSION)
    validate_preflight(pre,inputs)
    if pre["identity"] != inputs["identity"] or pre["status"] != "PASS" or pre["physical_batch"] != state["physical_batch"]:
        raise ValueError("Preflight/state không khớp")
    if replay:device = environment(inputs)
    records = []
    for seed in SEEDS:
        case = state["seeds"][str(seed)]
        if (case["status"] != "COMPLETE" or case["step"] != 5000 or case["pending"] is not None
                or [r["step"] for r in case["reports"]] != list(STEPS)
                or len(case["loss_history"]) != 5000):raise ValueError("Chưa đủ seed/step/checkpoint/report")
        if case["resume"] != case["reports"][-1]["checkpoint"]:raise ValueError("Resume cuối không phải checkpoint5000")
        for index,loss in enumerate(case["loss_history"],1):
            if loss["step"] != index or loss["lr"] != scheduled_lr(index) or any(not np.isfinite(loss[k]) for k in ("soft_cross_entropy","gradient_norm_before_clip")):
                raise ValueError("Loss history/scheduler không đúng")
        for row in case["reports"]:
            if budget is not None:budget.check()
            if row["seed"] != seed:raise ValueError("Report nằm sai seed")
            payload = read_checkpoint(directory,row["checkpoint"],inputs,seed=seed,step=row["step"],physical=state["physical_batch"])
            report = read_envelope(checked_path(directory,row["report"]),ASSESSMENT_VERSION)
            expected = {"identity_sha256":content_hash(inputs["identity"]),"seed":seed,"step":row["step"],
                        "checkpoint":row["checkpoint"],"model_tensor_sha256":payload["model_tensor_sha256"]}
            if any(report[k] != v for k,v in expected.items()) or report["assessment"] != validation_summary(inputs,report["logits"]):
                raise ValueError("Assessment khác weights/derived metric")
            if replay:
                model = DistilledStudent().to(device)
                model.load_state_dict(payload["model"])
                if checkpoint_logits(model,inputs,128,device,budget.check if budget else lambda:None) != report["logits"]:
                    raise ValueError("Raw validation/2021 logits khác cold replay")
                del model
                print(f"Replay checkpoint seed{seed}/{row['step']}: PASS.",flush=True)
            records.append({**row,"assessment":report["assessment"]})
    return state,records


def seal_selection(root:Path, inputs:dict[str,Any], *, budget:ActiveBudget|None=None) -> dict[str,Any]:
    """Khóa eligible/rank trước test, bind đầy đủ60 weights/report; không market-best fallback."""
    state,records = verified_records(root,inputs,budget=budget)
    directory = root/OUTPUT
    result = {"identity":inputs["identity"],**selection(records),"checkpoints":records,
              "state":record(directory,directory/"state.json"),"technical_status":"PASS",
              "test_forward_started_at_selection":False,"development_allowed":False,"decision_calls_allowed":False}
    if budget is not None:budget.check()
    write_envelope(directory/"selection.json",SEAL_VERSION,result,immutable=True)
    return result
