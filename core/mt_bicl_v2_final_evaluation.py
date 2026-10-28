"""Đánh giá sau seal, báo cả kết quả bất lợi và cold replay từ weights đã khóa."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
import math
from pathlib import Path
from typing import Any, Callable

import torch

from core.mt_bicl_bank import SYMBOLS, content_hash
from core.mt_bicl_evaluation import baseline_logits, fit_baselines, market_input, market_report
from core.mt_bicl_training_io import save_checkpoint
from core.mt_bicl_v2_distillation import tensor_hash
from core.mt_bicl_v2_experiment import (
    NAMESPACE, OUTPUT, SEEDS, ablate, mechanism_report, open_test, predict, swap_report,
)
from core.mt_bicl_v2_io import ActiveBudget, read_envelope, write_envelope
from core.mt_bicl_v2_student import DistilledStudent, pack_input
from core.mt_bicl_v2_training_run import (
    checked_path, environment, read_checkpoint, record, seal_selection, verified_records,
)

STAGE_VERSION = "mt_bicl_evaluation_stage_v2"
REPORT_VERSION = "mt_bicl_final_report_v2"
PROOF_VERSION = "mt_bicl_training_replay_v2"


def market_rows(inputs:dict[str,Any]) -> list[dict[str,Any]]:
    """Cùng256 query2022/scaler train, kiểm PIT ở pack_input/market_input trước forward."""
    rows = [r for r in inputs["context"]["episodes"] if r["split"] == "validation" and r["status"] == "AVAILABLE"]
    rows.sort(key=lambda r:(r["query"]["as_of_date"],SYMBOLS.index(r["query"]["symbol"])))
    if len(rows) != 256 or any(not "2022-01-01" <= r["query"]["as_of_date"] < r["query"]["exit_date"] <= "2022-12-31" for r in rows):
        raise ValueError("Không đúng common256 query2022")
    if any(r["scaler_sha256"] != content_hash(inputs["bank"]["frozen_scaler"]) for r in rows):
        raise ValueError("2022 không dùng scaler train đã khóa")
    return rows


def teacher_logit(inputs:dict[str,Any], data:dict[str,Any], *, pooled:bool=False) -> float:
    """Log odds teacher từ counts, không sinh lại nhãn kinh tế hoặc fit teacher."""
    result = inputs["teacher"].predict(data,pooled=pooled)
    return float(result["log_probability_one"]-result["log_probability_zero"])


def baseline_stage(inputs:dict[str,Any], rows:list[dict[str,Any]], check:Callable[[],None]) -> dict[str,Any]:
    """Hai baseline train-only và bốn teacher trên cùng input/support2022."""
    fit = fit_baselines(inputs["bank"])
    z = baseline_logits(fit,[r["query"]["model_vector"] for r in rows])
    for mode in ("full","no_prior","no_target","pooling"):
        values = []
        for row in rows:
            check()
            data = market_input(row,inputs["context"],"full" if mode == "pooling" else mode)
            values.append(teacher_logit(inputs,data,pooled=mode == "pooling"))
        z["teacher_"+mode] = values
    return {"fit":fit,"market_logits":z}


def test_jobs(inputs:dict[str,Any], corpus:dict[str,Any], rows:list[dict[str,Any]]) -> dict[str,Any]:
    """Chỉ caller đã kiểm selection seal mới được tạo packets test."""
    tests,pairs = corpus["synthetic_test"],corpus["test_swap"]
    return {**{"test_"+mode:[pack_input(ablate(r["input"],mode)) for r in tests]
               for mode in ("full","context_blind","no_prior","no_target")},
            "swap_a":[pack_input(r["input_a"]) for r in pairs],
            "swap_b":[pack_input(r["input_b"]) for r in pairs],
            **{"market_"+mode:[pack_input(market_input(r,inputs["context"],mode)) for r in rows]
               for mode in ("full","no_prior","no_target")}}


def seed_stage(root:Path, inputs:dict[str,Any], seal:dict[str,Any], seed:int, jobs:dict[str,Any],
               device:torch.device, check:Callable[[],None]) -> dict[str,Any]:
    """Forward checkpoint eligible riêng của seed; tuyệt đối không fallback seed khác."""
    candidate = seal["per_seed_candidate_or_none"][str(seed)]
    if candidate is None:return {"seed":seed,"status":"NOT_RUN_NO_ELIGIBLE_CHECKPOINT","student_forward":False}
    physical = read_envelope(root/OUTPUT/"state.json","mt_bicl_training_state_v2")["physical_batch"]
    payload = read_checkpoint(root/OUTPUT,candidate["checkpoint"],inputs,seed=seed,step=candidate["step"],physical=physical)
    model = DistilledStudent().to(device)
    model.load_state_dict(payload["model"])
    logits = {}
    for name,packets in jobs.items():
        logits[name] = predict(model,packets,128,device,check)
        print(f"Seed{seed}, checkpoint{candidate['step']}: đã đánh giá {name}, {len(packets)} query.",flush=True)
    return {"seed":seed,"status":"COMPLETE","candidate":candidate,"model_tensor_sha256":tensor_hash(model),
            "logits":logits,"optimizer_used":False,"weights_unchanged":True}


def market_variant(logits:list[float], rows:list[dict[str,Any]], mode:str) -> dict[str,Any]:
    """Metadata strata phản ánh component đã bỏ; mẫu số và nhãn giữ nguyên."""
    metadata = deepcopy(rows)
    for row in metadata:
        if mode == "no_prior":row["K"] = 0
        if mode == "no_target":row["m"] = 0
    return market_report(logits,metadata)


def test_teacher_controls(inputs:dict[str,Any], corpus:dict[str,Any], check:Callable[[],None]) -> dict[str,Any]:
    """Các control teacher dùng đúng inputs/corpus đã đăng ký; không đổi test theo kết quả."""
    tests = corpus["synthetic_test"]
    constant = sum(p*mu for p,(mu,k) in zip(inputs["teacher"].pi,[(m,k) for m in (.2,.4,.6,.8) for k in (2,8,32,128)]))
    z = {"constant":[math.log(constant)-math.log1p(-constant)]*len(tests)}
    for mode in ("full","no_prior","no_target","pooling"):
        values = []
        for row in tests:
            check()
            values.append(teacher_logit(inputs,ablate(row["input"],"full" if mode == "pooling" else mode),pooled=mode == "pooling"))
        z[mode] = values
    return {"logits":z,"reports":{k:mechanism_report(v,tests) for k,v in z.items()}}


def derive_report(inputs:dict[str,Any], seal:dict[str,Any], rows:list[dict[str,Any]],
                  baseline:dict[str,Any], stages:dict[str,Any], corpus:dict[str,Any]|None,
                  controls:dict[str,Any]|None) -> dict[str,Any]:
    """Gate synthetic tách khỏi mô tả2022; test FAIL giữ nguyên lựa chọn đã seal."""
    expected = {"base_rate","logistic","teacher_full","teacher_no_prior","teacher_no_target","teacher_pooling"}
    if set(baseline["market_logits"]) != expected or set(stages) != {str(s) for s in SEEDS}:
        raise ValueError("Thiếu baseline/seed evaluation")
    shared = {name:market_variant(values,rows,name.removeprefix("teacher_")) for name,values in baseline["market_logits"].items()}
    reports = {}
    for seed in SEEDS:
        stage = stages[str(seed)]
        candidate = seal["per_seed_candidate_or_none"][str(seed)]
        if candidate is None:
            if stage != {"seed":seed,"status":"NOT_RUN_NO_ELIGIBLE_CHECKPOINT","student_forward":False}:
                raise ValueError("Seed không eligible đã bị forward/fallback")
            reports[str(seed)] = stage
            continue
        if (corpus is None or controls is None or stage["candidate"] != candidate or stage["seed"] != seed
                or stage["status"] != "COMPLETE" or stage["optimizer_used"] is not False or stage["weights_unchanged"] is not True):
            raise ValueError("Stage không khớp checkpoint đã seal")
        z = stage["logits"]
        if set(z) != {"test_full","test_context_blind","test_no_prior","test_no_target","swap_a","swap_b","market_full","market_no_prior","market_no_target"}:
            raise ValueError("Thiếu job test/control")
        tests,pairs = corpus["synthetic_test"],corpus["test_swap"]
        synthetic = {mode:mechanism_report(z["test_"+mode],tests) for mode in ("full","context_blind","no_prior","no_target")}
        swap = swap_report(z["swap_a"],z["swap_b"],pairs)
        flat = controls["reports"]["constant"]["gate"] == "PASS" or swap["eligible_pairs"] < 200
        status = "INCONCLUSIVE_TEACHER_TOO_FLAT" if flat else "PASS" if synthetic["full"]["gate"] == swap["gate"] == "PASS" else "FAIL"
        reports[str(seed)] = {"candidate":candidate,"synthetic":synthetic,"prior_swap":swap,"mechanism_status":status,
                              "market":{mode:market_variant(z["market_"+mode],rows,mode) for mode in ("full","no_prior","no_target")}}
    global_candidate = seal["global_candidate_or_none"]
    status = reports[str(global_candidate["seed"])]["mechanism_status"] if global_candidate else "NO_ELIGIBLE_CHECKPOINT"
    comparisons = {}
    if global_candidate:
        selected = reports[str(global_candidate["seed"])]["market"]
        metric = selected["full"]["metrics"]
        for name,value in {**shared,**{k:selected[k] for k in ("no_prior","no_target")}}.items():
            ll = metric["macro_log_loss"]-value["metrics"]["macro_log_loss"]
            brier = metric["macro_brier"]-value["metrics"]["macro_brier"]
            comparisons[name] = {"delta_macro_log_loss_student_minus_comparator":ll,"delta_macro_brier_student_minus_comparator":brier,
                                 "performance":"BETTER_BOTH" if ll < 0 and brier < 0 else "WORSE_BOTH" if ll > 0 and brier > 0 else "MIXED_OR_TIE"}
    candidates = [r for r in inputs["bank"]["records"] if r["query_split"] == "validation"]
    return {"identity":inputs["identity"],"candidate_locked_before_test":global_candidate,"candidate_mechanism_status":status,
            "technical_status":"PASS","release_status":"MECHANISM_PASS_AWAITING_INTEGRATION" if status == "PASS" else "NO_MT_BICL_RELEASE_V2",
            "per_seed":reports,"shared_market_baselines":shared,"baseline_fit":baseline["fit"],
            "teacher_synthetic_controls":controls,"candidate_market_comparisons":comparisons,
            "coverage":{"candidate_cycles":len(candidates),"common_queries":len(rows),
                        "excluded":dict(Counter(r["status"] for r in candidates if r["status"] != "AVAILABLE")),
                        "episode_ids":[r["query"]["episode_id"] for r in rows]},
            "synthetic_test_status":"COMPLETE" if global_candidate else "NOT_RUN_NO_ELIGIBLE_CHECKPOINT",
            "market_status":"2022_EXPOSED_DESCRIPTIVE_NOT_PERFORMANCE_GATE","reselection_allowed":False,
            "development_allowed":False,"decision_calls_allowed":False,"p_is_expected_return":False}


def export_candidate(root:Path, inputs:dict[str,Any], seal:dict[str,Any]) -> dict[str,Any]|None:
    """Export model-only sau seal; không có eligible thì không tạo artifact weights mới."""
    directory = root/OUTPUT
    path = directory/"candidate.pt"
    candidate = seal["global_candidate_or_none"]
    if candidate is None:
        if path.exists():raise ValueError("NO_ELIGIBLE nhưng có candidate export")
        return None
    state = read_envelope(directory/"state.json","mt_bicl_training_state_v2")
    cp = read_checkpoint(directory,candidate["checkpoint"],inputs,seed=candidate["seed"],step=candidate["step"],physical=state["physical_batch"])
    payload = {"version":"mt_bicl_candidate_weights_v2","seed":candidate["seed"],"step":candidate["step"],
               "physical_batch":state["physical_batch"],"selection_sha256":record(directory,directory/"selection.json")["sha256"],
               "model_tensor_sha256":cp["model_tensor_sha256"],"model":cp["model"],"identity_sha256":content_hash(inputs["identity"])}
    if path.exists():
        from core.mt_bicl_v2_training_run import _equivalent
        if not _equivalent(torch.load(path,map_location="cpu",weights_only=True),payload):raise ValueError("Export khác checkpoint đã chọn")
    else:save_checkpoint(path,payload)
    return record(directory,path)


def evaluate_final(root:Path, inputs:dict[str,Any], *, resume:bool,
                   stop:Callable[[],bool]=lambda:False) -> str:
    """Journal từng stage; no eligible chỉ teacher/baselines2022, không decode/forward test."""
    directory = root/OUTPUT
    if not (directory/"selection.json").exists():raise ValueError("Chạy seal trước evaluate")
    device = environment(inputs)
    with ActiveBudget(root/NAMESPACE/"active_budget_v2.json",inputs["budget_identity"]) as budget:
        seal = seal_selection(root,inputs,budget=budget)
        export = export_candidate(root,inputs,seal)
        output = directory/"evaluation"
        output.mkdir(exist_ok=True)
        if any(output.iterdir()) and not resume:raise ValueError("Đã có evaluation: dùng --resume")
        binding = {"identity_sha256":content_hash(inputs["identity"]),"selection":record(directory,directory/"selection.json")}
        rows = market_rows(inputs)
        def stage(name:str, build:Callable[[],dict[str,Any]]) -> dict[str,Any]:
            """Stage immutable gắn selection seal và source; resume không forward lại stage xong."""
            path = output/(name+".json")
            if path.exists():
                value = read_envelope(path,STAGE_VERSION)
                if value["binding"] != binding:raise ValueError("Stage evaluation sai binding")
                return value["result"]
            budget.check()
            result = build()
            budget.check()
            write_envelope(path,STAGE_VERSION,{"binding":binding,"result":result},immutable=True)
            return result
        baseline = stage("baseline",lambda:baseline_stage(inputs,rows,budget.check))
        if stop():return "PAUSED"
        corpus = open_test(root,inputs,seal) if seal["global_candidate_or_none"] else None
        controls = stage("teacher_controls",lambda:test_teacher_controls(inputs,corpus,budget.check)) if corpus else None
        if stop():return "PAUSED"
        jobs = test_jobs(inputs,corpus,rows) if corpus else {}
        seeds = {}
        for seed in SEEDS:
            seeds[str(seed)] = stage(f"seed{seed}",lambda s=seed:seed_stage(root,inputs,seal,s,jobs,device,budget.check))
            if stop():return "PAUSED"
        report = derive_report(inputs,seal,rows,baseline,seeds,corpus,controls)
        report.update(selection=binding["selection"],export=export,
                      stages={p.name:record(directory,p) for p in sorted(output.glob("*.json"))})
        budget.check()
        write_envelope(directory/"report.json",REPORT_VERSION,report,immutable=True)
        return report["release_status"]


def verify_final(root:Path, inputs:dict[str,Any], *, replay:bool) -> dict[str,Any]:
    """Kiểm source/hash/derive; replay 60 assessment và các stage cuối, không train lại."""
    directory = root/OUTPUT
    device = environment(inputs)
    with ActiveBudget(root/NAMESPACE/"active_budget_v2.json",inputs["budget_identity"]) as budget:
        if replay:verified_records(root,inputs,replay=True,budget=budget)
        seal = seal_selection(root,inputs,budget=budget)
        report = read_envelope(directory/"report.json",REPORT_VERSION)
        rows = market_rows(inputs)
        binding = {"identity_sha256":content_hash(inputs["identity"]),"selection":record(directory,directory/"selection.json")}
        stage_values = {}
        for name,pointer in report["stages"].items():
            value = read_envelope(checked_path(directory,pointer),STAGE_VERSION)
            if value["binding"] != binding or name != Path(pointer["file"]).name:raise ValueError("Stage sai seal/name")
            stage_values[name.removesuffix(".json")] = value["result"]
        expected_names = {"baseline","seed17","seed42","seed73"}|({"teacher_controls"} if seal["global_candidate_or_none"] else set())
        if set(stage_values) != expected_names:raise ValueError("Sai tập stage final")
        baseline = baseline_stage(inputs,rows,budget.check)
        if baseline != stage_values["baseline"]:raise ValueError("Baseline/teacher không khớp train-only replay")
        corpus = open_test(root,inputs,seal) if seal["global_candidate_or_none"] else None
        controls = stage_values.get("teacher_controls")
        if corpus:
            if controls != test_teacher_controls(inputs,corpus,budget.check):raise ValueError("Teacher controls khác replay")
        stages = {str(s):stage_values[f"seed{s}"] for s in SEEDS}
        if replay:
            jobs = test_jobs(inputs,corpus,rows) if corpus else {}
            for seed in SEEDS:
                if stages[str(seed)] != seed_stage(root,inputs,seal,seed,jobs,device,budget.check):
                    raise ValueError("Final student logits không khớp cold replay")
        expected = derive_report(inputs,seal,rows,baseline,stages,corpus,controls)
        expected.update(selection=binding["selection"],export=export_candidate(root,inputs,seal),stages=report["stages"])
        if report != expected:raise ValueError("Report khác derived metrics/raw logits")
        proof = {"identity_sha256":content_hash(inputs["identity"]),"gpu":inputs["pilot_gpu"],
                 "selection":binding["selection"],"report":record(directory,directory/"report.json"),
                 "status":"FROZEN_INFERENCE_REPLAY_MATCH","checkpoints":60,"optimizer_retrained":False,
                 "release_status":report["release_status"]}
        budget.check()
        if replay:write_envelope(directory/"replay_verification.json",PROOF_VERSION,proof,immutable=True)
        proof_path = directory/"replay_verification.json"
        if not proof_path.exists() or read_envelope(proof_path,PROOF_VERSION) != proof:
            raise ValueError("Chưa có proof đúng artifacts: chạy verify --replay")
        return {"integrity":"PASS","replay":"PASS","candidate_mechanism_status":report["candidate_mechanism_status"],
                "release_status":report["release_status"]}
