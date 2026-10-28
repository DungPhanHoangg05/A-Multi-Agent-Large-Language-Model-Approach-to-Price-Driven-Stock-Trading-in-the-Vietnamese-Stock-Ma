"""Input, batch synthetic, metric cơ chế và selection v2; test chỉ mở sau selection seal."""

from __future__ import annotations

from copy import deepcopy
import math
from pathlib import Path
from typing import Any

import numpy as np
import torch

from core.bayesian_memory import read_json
from core.mt_bicl_bank import content_hash
from core.mt_bicl_evaluation import market_input, mechanism_metrics, prior_swap_metrics, probabilities
from core.mt_bicl_training import selection_metrics, selection_rows
from core.mt_bicl_v2_distillation import tensor_hash
from core.mt_bicl_v2_io import read_envelope
from core.mt_bicl_v2_pilot import (
    FROZEN_TEACHER, OUTPUT as PILOT_OUTPUT, REPORT_VERSION as PILOT_REPORT_VERSION,
    STATE_VERSION as PILOT_STATE_VERSION, load_inputs as load_pilot_inputs,
)
from core.mt_bicl_v2_simulator import BetaTaskSimulator, train_feature_pool
from core.mt_bicl_v2_student import PAIRED, DistilledStudent, collate_packets, pack_input
from core.mt_bicl_v2_teacher import BetaBernoulliTeacher
from core.mt_bicl_v21_preparation import (
    CORPUS_VERSION, NAMESPACE, OUTPUT as TEACHER_OUTPUT, PROTOCOL_SHA256, TEACHER_VERSION,
    file_hash, load_inputs as load_teacher_inputs,
)

OUTPUT = NAMESPACE/"training_v2"
SEEDS = (17,42,73)
STEPS = tuple(range(250,5001,250))
SEAL_VERSION = "mt_bicl_selection_v2"
ASSESSMENT_VERSION = "mt_bicl_checkpoint_assessment_v2"
FROZEN_PILOT = {
    "LEGACY_X_Y_69_WITH_TASK_SLOT.json":"2c8f551a2c3905cda0e82b6af4eba53eadf2019a9c4ee787da4abc434b5e9762",
    "PAIRED_37.json":"ea0dcc8a01aeb081925dc35ea089f411ff154fdfd8ab8edfaab0b27e2d16a583",
    "state.json":"7bd4de906bd01833cbaa0966dda4970238ab2e4bc405f7c2cbe98ad64aeb86b9",
    "replay_verification.json":"f51524b57f70a3612cdc4a16f956ffdbf26ae65fa0c972b546b8814cd60faba7"}
CODE = ("core/mt_bicl_v2_experiment.py","core/mt_bicl_v2_training_run.py",
        "core/mt_bicl_v2_final_evaluation.py","scripts/train_mt_bicl_v2.py",
        "core/mt_bicl_v2_student.py","core/mt_bicl_v2_distillation.py","core/mt_bicl_evaluation.py",
        "core/mt_bicl_training.py","core/mt_bicl_training_io.py","core/mt_bicl_v2_io.py")
CONTEXT = "outputs/bayesian_benchmark/mt_bicl_v1/inputs/task_context_v1.json"
CONTEXT_SHA256 = "4fca2146fbc03f4f74762a5a6b4d44c184b4b4244c3cb28d5dfda68d93fa0c57"


def load_inputs(root: Path) -> dict[str, Any]:
    """Chỉ decode validation/2021 trước seal, băm test; không gọi CUDA hoặc train."""
    pilot = load_pilot_inputs(root)
    for name, expected in FROZEN_PILOT.items():
        if file_hash(root/PILOT_OUTPUT/name) != expected:
            raise ValueError("Pilot khác nghiệm thu W10-11: "+name)
    state = read_envelope(root/PILOT_OUTPUT/"state.json",PILOT_STATE_VERSION)
    proof = read_envelope(root/PILOT_OUTPUT/"replay_verification.json","mt_bicl_pilot_replay_v2")
    if (state["identity"] != pilot["identity"] or state["status"] != "PILOT_PASS_AWAITING_PREFLIGHT"
            or proof["status"] != "OPTIMIZER_REPLAY_MATCH" or proof["paired_tiny_gate"] != "PASS"
            or proof["state_sha256"] != FROZEN_PILOT["state.json"]):
        raise ValueError("Chưa đủ pilot/replay để preflight train chính")
    base = load_teacher_inputs(root)
    fitted = read_envelope(root/TEACHER_OUTPUT/"teacher_fit.json",TEACHER_VERSION)
    teacher = BetaBernoulliTeacher(fitted["pi"])
    simulator = BetaTaskSimulator(fitted["pi"],train_feature_pool(base["bank"],base["membership"]),base["manifest"])
    if file_hash(root/CONTEXT) != CONTEXT_SHA256:
        raise ValueError("Task/context không đúng bản đã khóa")
    envelope = read_json(root/CONTEXT)
    if content_hash(envelope["payload"]) != envelope["sha256"]:
        raise ValueError("Context sai envelope")
    context = envelope["payload"]
    rows = selection_rows(context)
    if len(rows) != 248:
        raise ValueError("Selection không đúng248 query2021")
    corpora = {}
    for stream in ("synthetic_validation","validation_swap"):
        corpus = read_envelope(root/TEACHER_OUTPUT/(stream+".json"),CORPUS_VERSION)
        if (corpus["stream"] != stream or len(corpus["episodes"]) != 5000
                or [r["index"] for r in corpus["episodes"]] != list(range(5000))):
            raise ValueError("Sai ID/count corpus validation")
        corpora[stream] = corpus["episodes"]
    identity = {"version":"mt_bicl_training_identity_v2","protocol_sha256":PROTOCOL_SHA256,
                "teacher_identity_sha256":content_hash(base["identity"]),
                "pilot_identity_sha256":content_hash(pilot["identity"]),"pilot_sha256":FROZEN_PILOT,
                "teacher_sha256":FROZEN_TEACHER,"context_sha256":CONTEXT_SHA256,
                "code_sha256":{name:file_hash(root/name) for name in CODE},"runtime":base["protocol"]["runtime"],
                "model_seeds":list(SEEDS),"steps_per_seed":5000,"effective_batch":128,
                "selection":"MECHANISM_ELIGIBLE_THEN_2021_MACRO","heldout_after_seal":True}
    return {"identity":identity,"budget_identity":base["budget_identity"],"protocol":base["protocol"],
            "teacher":teacher,"simulator":simulator,"bank":base["bank"],"context":context,
            "selection_rows":rows,"corpora":corpora,"pilot_gpu":state["gpu"]}


def training_batch(inputs: dict[str, Any], step: int, seed: int, *, preflight: bool=False) -> list[dict[str, Any]]:
    """Một effective batch128, synthetic-only; q tính lại từ D/C, không latent hoặc query_y."""
    if seed not in SEEDS or type(step) is not int or not 1 <= step <= (100 if preflight else 5000):
        raise ValueError("Step/seed train ngoài protocol")
    result = []
    for index in range((step-1)*128,step*128):
        row = inputs["simulator"].episode("preflight" if preflight else "train",index,model_seed=seed)
        q = inputs["teacher"].predict(row["input"])["probability"]
        result.append(pack_input(row["input"],teacher_q=q))
    return result


def ablate(data: dict[str, Any], mode: str) -> dict[str, Any]:
    """Giữ query/membership còn lại, bỏ đúng component; không truy xuất lại context."""
    if mode not in ("full","no_prior","no_target","context_blind"):
        raise ValueError("Ablation không thuộc protocol")
    value = deepcopy(data)
    if mode in ("no_prior","context_blind"):value["prior"] = []
    if mode in ("no_target","context_blind"):value["target"]["observations"] = []
    return value


def predict(model: DistilledStudent, packets: list[dict[str, Any]], physical: int,
            device: torch.device, check: Any=lambda:None) -> list[float]:
    """Inference cố định weights, không nhận nhãn query hoặc gọi optimizer."""
    before = tensor_hash(model)
    model.eval()
    for parameter in model.parameters():parameter.grad = None
    logits = []
    with torch.inference_mode():
        for start in range(0,len(packets),physical):
            check()
            batch = collate_packets(packets[start:start+physical],device)
            z = model(batch["values"],batch["roles"],batch["slots"],batch["padding"])
            logits.extend(z[torch.arange(len(batch["queries"]),device=device),batch["queries"]].cpu().tolist())
    probabilities(logits)
    if tensor_hash(model) != before or any(p.grad is not None for p in model.parameters()):
        raise ValueError("Weights/gradient thay đổi trong frozen inference")
    return logits


def validation_jobs(inputs: dict[str, Any]) -> dict[str,list[dict[str,Any]]]:
    """Chỉ validation và query2021; không materialize student test trước seal."""
    cache = inputs.get("validation_packets")
    if cache is None:
        rows,pairs = inputs["corpora"]["synthetic_validation"],inputs["corpora"]["validation_swap"]
        cache = {"full":[pack_input(r["input"]) for r in rows],
                 "context_blind":[pack_input(ablate(r["input"],"context_blind")) for r in rows],
                 "swap_a":[pack_input(r["input_a"]) for r in pairs],
                 "swap_b":[pack_input(r["input_b"]) for r in pairs],
                 "market_2021":[pack_input(market_input(row,inputs["context"])) for row in inputs["selection_rows"]]}
        inputs["validation_packets"] = cache
    return cache


def checkpoint_logits(model: DistilledStudent, inputs: dict[str,Any], physical:int,
                      device:torch.device, check:Any=lambda:None) -> dict[str,list[float]]:
    """Đủ validation/full/blind/swap và cùng248 query2021 cho mọi checkpoint."""
    return {name:predict(model,rows,physical,device,check) for name,rows in validation_jobs(inputs).items()}


def mechanism_report(logits:list[float], rows:list[dict[str,Any]]) -> dict[str,Any]:
    """Giữ cả K/m/joint và IID/stress; gate chính dùng toàn bộ5.000 episode."""
    value = mechanism_metrics(logits,rows)
    for name,group in (("joint",[(r["oracle"]["K"],r["oracle"]["m"]) for r in rows]),
                       ("distribution",["stress" if r["sidecar"]["stress"] else "iid" for r in rows])):
        value["by_"+name] = {}
        for key in sorted(set(group)):
            indices = [i for i,v in enumerate(group) if v == key]
            value["by_"+name][str(key)] = mechanism_metrics([logits[i] for i in indices],[rows[i] for i in indices])
    return value


def swap_report(a:list[float], b:list[float], pairs:list[dict[str,Any]]) -> dict[str,Any]:
    """Dấu, biên độ và Pearson Δp; giữ nguyên eligible từ oracle đã seal."""
    value = prior_swap_metrics(a,b,pairs)
    model = probabilities(b)[0]-probabilities(a)[0]
    oracle = np.asarray([r["oracle_b"]["probability"]-r["oracle_a"]["probability"] for r in pairs])
    mask = np.abs(oracle) >= .05
    value["delta_amplitude_quantiles"] = {"quantiles":[0.,.5,.95,1.],
        "model":np.quantile(np.abs(model[mask]),[0,.5,.95,1],method="linear").tolist() if mask.any() else None,
        "oracle":np.quantile(np.abs(oracle[mask]),[0,.5,.95,1],method="linear").tolist() if mask.any() else None}
    valid = int(mask.sum()) >= 2 and float(model[mask].std()) > 0 and float(oracle[mask].std()) > 0
    value["delta_pearson_correlation"] = float(np.corrcoef(model[mask],oracle[mask])[0,1]) if valid else None
    value["correlation_reason"] = None if valid else "INSUFFICIENT_OR_CONSTANT_DELTA"
    return value


def validation_summary(inputs:dict[str,Any], logits:dict[str,list[float]]) -> dict[str,Any]:
    """Eligibility chỉ từ synthetic validation, sau đó mới dùng2021 để rank."""
    expected = {"full","context_blind","swap_a","swap_b","market_2021"}
    if set(logits) != expected:raise ValueError("Thiếu job checkpoint validation")
    rows,pairs = inputs["corpora"]["synthetic_validation"],inputs["corpora"]["validation_swap"]
    synthetic = mechanism_report(logits["full"],rows)
    swap = swap_report(logits["swap_a"],logits["swap_b"],pairs)
    constant = float(sum(p*g[0] for p,g in zip(inputs["teacher"].pi,
                    [(mu,k) for mu in (.2,.4,.6,.8) for k in (2,8,32,128)])))
    constant_logits = [math.log(constant)-math.log1p(-constant)]*len(rows)
    control = mechanism_report(constant_logits,rows)
    flat = control["gate"] == "PASS" or swap["eligible_pairs"] < 200
    status = "INCONCLUSIVE_TEACHER_TOO_FLAT" if flat else "PASS" if synthetic["gate"] == swap["gate"] == "PASS" else "FAIL"
    if len(logits["market_2021"]) != len(inputs["selection_rows"]):raise ValueError("Sai mẫu số2021")
    records = [{"episode_id":r["query"]["episode_id"],"symbol":r["query"]["symbol"],
                "y":r["supervised_target"]["y"],"p":float(p)}
               for r,p in zip(inputs["selection_rows"],probabilities(logits["market_2021"])[0])]
    if len(records) != len(inputs["selection_rows"]):raise ValueError("Sai mẫu số2021")
    return {"synthetic":synthetic,"prior_swap":swap,"constant_control":control,
            "context_blind_control":mechanism_report(logits["context_blind"],rows),
            "mechanism_status":status,"eligible":status == "PASS",
            "market_2021":selection_metrics(records),"market_2021_records":records}


def selection(records:list[dict[str,Any]]) -> dict[str,Any]:
    """Không fallback market-best; buộc đủ60 report trước selection seal."""
    if {(r["seed"],r["step"]) for r in records} != {(s,t) for s in SEEDS for t in STEPS} or len(records) != 60:
        raise ValueError("Selection cần đủ60 checkpoint/report duy nhất")
    def key(row:dict[str,Any]) -> tuple:
        """Tie-break theo recipe, không P&L/test hoặc checkpoint cuối mặc định."""
        metrics = row["assessment"]["market_2021"]
        return (round(metrics["macro_log_loss"],12),round(metrics["macro_brier"],12),row["step"],SEEDS.index(row["seed"]))
    if any(type(r["assessment"]["eligible"]) is not bool or
           r["assessment"]["eligible"] != (r["assessment"]["mechanism_status"] == "PASS") for r in records):
        raise ValueError("Eligibility không khớp gate cơ chế")
    eligible = [row for row in records if row["assessment"]["eligible"]]
    def descriptor(row:dict[str,Any]) -> dict[str,Any]:
        """Bind weights và report đã đánh giá, không chỉ seed/step tự khai."""
        return {k:row[k] for k in ("seed","step","checkpoint","report")}
    return {"status":"SELECTED" if eligible else "NO_ELIGIBLE_CHECKPOINT",
            "global_candidate_or_none":descriptor(min(eligible,key=key)) if eligible else None,
            "per_seed_candidate_or_none":{str(seed):descriptor(min(group,key=key)) if
                (group := [r for r in eligible if r["seed"] == seed]) else None for seed in SEEDS},
            "eligibility_all_checkpoints":[{"seed":r["seed"],"step":r["step"],"eligible":r["assessment"]["eligible"],
                                            "mechanism_status":r["assessment"]["mechanism_status"]} for r in records],
            "ranking_key":["round(macro_log_loss_2021,12)","round(macro_brier_2021,12)","step","seed_order_17_42_73"]}


def open_test(root:Path, inputs:dict[str,Any], seal:dict[str,Any]) -> dict[str,list[dict[str,Any]]]:
    """Kiểm seal durable trước mọi decode test; không có eligible thì không mở."""
    path = root/OUTPUT/"selection.json"
    if not path.exists() or read_envelope(path,SEAL_VERSION) != seal or seal["identity"] != inputs["identity"]:
        raise ValueError("Student test chỉ mở sau selection seal đúng identity")
    if seal["status"] != "SELECTED" or seal["global_candidate_or_none"] is None:
        raise ValueError("NO_ELIGIBLE_CHECKPOINT: cấm mở student test")
    result = {}
    for stream in ("synthetic_test","test_swap"):
        path = root/TEACHER_OUTPUT/(stream+".json")
        if file_hash(path) != FROZEN_TEACHER[stream+".json"]:raise ValueError("Test khác corpus đã đóng băng")
        result[stream] = read_envelope(path,CORPUS_VERSION)["episodes"]
    return result
