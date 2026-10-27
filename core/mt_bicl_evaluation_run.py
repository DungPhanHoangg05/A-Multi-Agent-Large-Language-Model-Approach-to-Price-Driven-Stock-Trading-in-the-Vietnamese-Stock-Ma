"""Đánh giá đóng băng ba seed, journal riêng và xác minh báo cáo từ raw logits."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

import torch

from core.mt_bicl_bank import SYMBOLS, content_hash
from core.mt_bicl_batches import load_context
from core.mt_bicl_evaluation import (baseline_logits, fit_baselines, market_input, market_report,
                                    mechanism_metrics, model_fingerprint, predict_packets, probabilities,
                                    prior_swap_metrics)
from core.mt_bicl_model import MTBiCLLearner
from core.mt_bicl_oracle import FiniteBayesOracle
from core.mt_bicl_simulator import FiniteSimulator, pack_input, pair_inputs
from core.mt_bicl_trainer import gpu_identity, verify_training
from core.mt_bicl_training import configure, selection_rows
from core.mt_bicl_training_io import (TRAINING_PATH, file_hash, load_checkpoint, read_manifest,
                                     source_identity, write_manifest)

EVALUATION_PATH = "outputs/bayesian_benchmark/mt_bicl_v1/evaluation_v1"
CORPUS_PATH = "outputs/bayesian_benchmark/mt_bicl_v1/inputs/synthetic_oracle_v1.json"
CODE = ("core/mt_bicl_evaluation.py", "core/mt_bicl_evaluation_run.py", "scripts/evaluate_mt_bicl.py")
FROZEN = {"preflight.json": "31be2d8e2f8e2dea9fcfe2f10e9481e59ad753313f8fedbfea17b83335606a67",
          "state.json": "1764965dd94b71a35f024e78f1b2edd9a3bf74653a1d017efaa0444b381db927",
          "candidate_v1.json": "3f963fb7e4fa0e70311b78b40c4ac91a2e329b4c1c518825157e38736a4613fa"}


def load_inputs(root: Path) -> dict[str, Any]:
    """Cold-check nguồn và receipt W10-06; không sửa owner/state trong training namespace."""
    training = root/TRAINING_PATH
    for name, digest in FROZEN.items():
        if file_hash(training/name) != digest:
            raise ValueError("Artifact training khác nghiệm thu: "+name)
    training_identity = source_identity(root)
    context = load_context(root)
    selection = verify_training(training, training_identity, rows=selection_rows(context))
    corpus = read_manifest(root/CORPUS_PATH)
    tests, pairs = corpus["synthetic_test"], corpus["prior_swap_pairs"]
    if (len(tests) != 5000 or len(pairs) != 5000
            or [r["episode_index"] for r in tests] != list(range(5000))
            or [r["pair_index"] for r in pairs] != list(range(5000))
            or any(r["stream"] != "synthetic_test" or r["model_seed"] != 0 for r in tests)):
        raise ValueError("Corpus test/cặp khác IDs hoặc recipe đã khóa")
    rows = [r for r in context["episodes"] if r["split"] == "validation" and r["status"] == "AVAILABLE"]
    rows.sort(key=lambda r: (r["query"]["as_of_date"], SYMBOLS.index(r["query"]["symbol"])))
    if len(rows) != 256 or any(not "2022-01-01" <= r["query"]["as_of_date"] < r["query"]["exit_date"] <= "2022-12-31" for r in rows):
        raise ValueError("Validation khác 256 query 2022 đã nghiệm thu")
    bank = read_manifest(root/"outputs/bayesian_benchmark/mt_bicl_v1/inputs/dense_bank_v1.json")
    scaler_hash = content_hash(bank["frozen_scaler"])
    if any(r["scaler_sha256"] != scaler_hash for r in rows):
        raise ValueError("Validation không dùng scaler cuối train đã đóng băng")
    # Technical PIT/packing kiểm trước forward, không phụ thuộc nhãn query hoặc kết quả model.
    for row in rows:
        packet = pack_input(market_input(row, context))
        if any(packet[key] != row["packed"][key] for key in ("values", "roles", "prediction_positions", "query_position")):
            raise ValueError("Packing validation khác artifact task/context")
    identity = {"version": "mt_bicl_evaluation_identity_v1", "training_identity": content_hash(training_identity),
                "training_receipts_sha256": FROZEN, "candidate": selection["candidate"],
                "per_seed": selection["per_seed"], "corpus_sha256": file_hash(root/CORPUS_PATH),
                "code_sha256": {name: file_hash(root/name) for name in CODE},
                "runtime": training_identity["runtime"], "physical_batch": 128,
                "candidate_selection": "LOCKED_2021_NO_RESELECTION", "validation_year": 2022}
    return {"identity": identity, "training": training, "selection": selection, "context": context,
            "bank": bank, "corpus": corpus, "rows": rows}


def baseline_stage(inputs: dict[str, Any], root: Path) -> dict[str, Any]:
    """Chỉ fit hai baseline số bằng train; pooling là giả định simulator, không ground truth market."""
    tick = perf_counter()
    fit = fit_baselines(inputs["bank"])
    rows, context = inputs["rows"], inputs["context"]
    logits = baseline_logits(fit, [r["query"]["model_vector"] for r in rows])
    oracle = FiniteBayesOracle(FiniteSimulator.from_locked(root))
    logits["naive_pooling"] = []
    for row in rows:
        result = oracle.predict(market_input(row, context), pooled=True)
        logits["naive_pooling"].append(result["log_probability_one"]-result["log_probability_zero"])
    return {"identity_sha256": content_hash(inputs["identity"]), "fit": fit,
            "market_logits": logits, "seconds": perf_counter()-tick}


def seed_stage(inputs: dict[str, Any], seed: int, device: torch.device,
               progress: Callable[[str], None] = print) -> dict[str, Any]:
    """Một checkpoint riêng đã chọn bằng 2021; không train, không đổi candidate theo test."""
    record = inputs["selection"]["per_seed"][str(seed)]
    payload = load_checkpoint(inputs["training"], record, inputs["identity"]["training_identity"])
    model = MTBiCLLearner().to(device)
    model.load_state_dict(payload["model"], strict=True)
    del payload
    before = model_fingerprint(model)
    corpus, context, rows = inputs["corpus"], inputs["context"], inputs["rows"]
    jobs = {"synthetic_test": [r["input"] for r in corpus["synthetic_test"]],
            "prior_swap_a": [pair_inputs(r)[0] for r in corpus["prior_swap_pairs"]],
            "prior_swap_b": [pair_inputs(r)[1] for r in corpus["prior_swap_pairs"]],
            "pooling_control": [corpus["pooling_control"]["input"]],
            **{"market_"+mode: [market_input(row, context, mode) for row in rows]
               for mode in ("full", "no_prior", "no_target")}}
    logits, times = {}, {}
    for name, data in jobs.items():
        tick = perf_counter()
        logits[name] = predict_packets(model, [pack_input(row) for row in data], 128, device)
        times[name] = perf_counter()-tick
        progress(f"Seed {seed}, checkpoint {record['step']}: đã đánh giá {name}, {len(data)} query.")
    if before != model_fingerprint(model):
        raise ValueError("Model bị thay đổi trong evaluation")
    return {"identity_sha256": content_hash(inputs["identity"]), "seed": seed, "checkpoint": record,
            "model_tensor_sha256": before, "logits": logits, "stage_seconds": times,
            "optimizer_used": False, "weights_unchanged": True}


def derive_report(inputs: dict[str, Any], baseline: dict[str, Any], seeds: dict[str, Any]) -> dict[str, Any]:
    """Báo cả ba seed và kết quả bất lợi; PASS cơ chế không tự cấp release development."""
    identity = content_hash(inputs["identity"])
    if baseline["identity_sha256"] != identity or set(seeds) != {"17", "42", "73"}:
        raise ValueError("Stage sai identity hoặc thiếu seed")
    rows, corpus = inputs["rows"], inputs["corpus"]
    reports = {}
    for seed, stage in seeds.items():
        if (stage["identity_sha256"] != identity or stage["seed"] != int(seed)
                or stage["checkpoint"] != inputs["selection"]["per_seed"][seed]
                or stage["optimizer_used"] is not False or stage["weights_unchanged"] is not True):
            raise ValueError("Seed stage sai checkpoint hoặc không frozen")
        z = stage["logits"]
        if (set(z) != {"synthetic_test", "prior_swap_a", "prior_swap_b", "pooling_control",
                       "market_full", "market_no_prior", "market_no_target"}
                or len(z["pooling_control"]) != 1):
            raise ValueError("Seed stage thiếu/đổi job hoặc sai mẫu số pooling control")
        synthetic = mechanism_metrics(z["synthetic_test"], corpus["synthetic_test"])
        swaps = prior_swap_metrics(z["prior_swap_a"], z["prior_swap_b"], corpus["prior_swap_pairs"])
        model_p = float(probabilities(z["pooling_control"])[0][0])
        control = corpus["pooling_control"]
        oracle_p, pooled_p = control["hierarchical"]["probability"], control["pooled"]["probability"]
        market = {}
        for mode in ("full", "no_prior", "no_target"):
            metadata = deepcopy(rows)
            for row in metadata:
                if mode == "no_prior":
                    row["K"] = 0
                if mode == "no_target":
                    row["m"] = 0
            market[mode] = market_report(z["market_"+mode], metadata)
        status = "FAIL" if "FAIL" in (synthetic["gate"], swaps["gate"]) else swaps["gate"]
        reports[seed] = {"checkpoint": stage["checkpoint"], "synthetic": synthetic, "prior_swap": swaps,
                         "mechanism_status": status, "pooling_control": {"model_p": model_p, "oracle_p": oracle_p,
                         "pooled_p": pooled_p, "oracle_minus_pooled": oracle_p-pooled_p,
                         "model_absolute_error_oracle": abs(model_p-oracle_p), "model_absolute_error_pooled": abs(model_p-pooled_p),
                         "scope": "DIAGNOSTIC_NO_ADDITIONAL_THRESHOLD"}, "market": market,
                         "stage_seconds": stage["stage_seconds"]}
    shared = {name: market_report(values, rows) for name, values in baseline["market_logits"].items()}
    if set(shared) != {"base_rate", "logistic", "naive_pooling"}:
        raise ValueError("Thiếu baseline đăng ký")
    candidate = inputs["selection"]["candidate"]
    key = str(candidate["seed"])
    if reports[key]["checkpoint"] != candidate:
        raise ValueError("Không được chọn lại checkpoint/seed bằng synthetic hoặc 2022")
    metrics = reports[key]["market"]["full"]["metrics"]
    comparators = {**shared, **{name: reports[key]["market"][name] for name in ("no_prior", "no_target")}}
    comparisons = {}
    for name, report in comparators.items():
        ll = metrics["macro_log_loss"]-report["metrics"]["macro_log_loss"]
        brier = metrics["macro_brier"]-report["metrics"]["macro_brier"]
        comparisons[name] = {"delta_macro_log_loss_full_minus_baseline": ll,
                             "delta_macro_brier_full_minus_baseline": brier,
                             "performance": "BETTER_BOTH" if ll < 0 and brier < 0 else
                                            "WORSE_BOTH" if ll > 0 and brier > 0 else "MIXED_OR_TIE"}
    candidates = [r for r in inputs["bank"]["records"] if r["query_split"] == "validation"]
    status = reports[key]["mechanism_status"]
    return {"version": "mt_bicl_mechanism_validation_v1", "identity": inputs["identity"],
            "candidate_locked_2021": candidate, "candidate_mechanism_status": status,
            "release_status": "MECHANISM_PASS_AWAITING_INTEGRATION" if status == "PASS" else "NO_MT_BICL_RELEASE",
            "technical_status": "PASS", "market_reporting_status": "COMPLETE_NOT_A_PERFORMANCE_GATE",
            "per_seed": reports, "shared_market_baselines": shared, "baseline_fit": baseline["fit"],
            "baseline_seconds": baseline["seconds"], "candidate_market_comparisons": comparisons,
            "coverage": {"validation_candidate_cycles": len(candidates), "common_ready_queries": len(rows),
                         "status_counts": dict(Counter(r["status"] for r in candidates)),
                         "exclusion_reasons": dict(Counter(reason for r in candidates for reason in r["reasons"])),
                         "common_query_ids": [r["query"]["episode_id"] for r in rows]},
            "limitations": ["2022_PREVIOUSLY_EXPOSED_NOT_INDEPENDENT_HOLDOUT", "POOLING_NOT_MARKET_GROUND_TRUTH",
                            "PROBABILITY_NOT_EXPECTED_RETURN", "NO_2022_CHECKPOINT_RESELECTION"],
            "decision_calls_allowed": False, "development_allowed": False}


def evaluate_run(root: Path, directory: Path, inputs: dict[str, Any], *, resume: bool,
                 stop: Callable[[], bool]) -> bool:
    """Journal bất biến theo seed; Ctrl+C pause ở cuối stage, không sửa run training đã seal."""
    identity = inputs["identity"]
    index_path = directory/"index.json"
    gpu = gpu_identity()
    if gpu != read_manifest(inputs["training"]/"preflight.json")["gpu"]:
        raise ValueError("GPU khác training đã khóa")
    if index_path.exists():
        index = read_manifest(index_path)
        if index["identity"] != identity or index["gpu"] != gpu:
            raise ValueError("Evaluation identity/GPU đã đổi, không tự reseal")
        if not resume:
            raise ValueError("Evaluation đã bắt đầu; dùng run --resume")
    else:
        index = {"identity": identity, "gpu": gpu, "artifacts": {}, "status": "RUNNING"}
        write_manifest(index_path, index)
    device = configure(0, cuda=True)
    for name in ("baseline", "seed17", "seed42", "seed73"):
        path = directory/(name+".json")
        if name in index["artifacts"]:
            if file_hash(path) != index["artifacts"][name]:
                raise ValueError("Stage khác journal")
            continue
        # File durable trước khi index commit có thể được replay so độc lập sau crash.
        result = baseline_stage(inputs, root) if name == "baseline" else seed_stage(inputs, int(name[4:]), device)
        if path.exists():
            previous = read_manifest(path)
            left, right = deepcopy(previous), deepcopy(result)
            for value in (left, right):
                value.pop("seconds", None)
                value.pop("stage_seconds", None)
            if left != right:
                raise ValueError("Stage orphan khác replay; không ghi đè")
        else:
            write_manifest(path, result)
        index["artifacts"][name] = file_hash(path)
        write_manifest(index_path, index)
        if stop():
            return False
    baseline = read_manifest(directory/"baseline.json")
    seeds = {str(s): read_manifest(directory/f"seed{s}.json") for s in (17, 42, 73)}
    report = derive_report(inputs, baseline, seeds)
    path = directory/"report.json"
    if path.exists() and read_manifest(path) != report:
        raise ValueError("Report đã có khác derived report; không ghi đè")
    if not path.exists():
        write_manifest(path, report)
    index["artifacts"]["report"] = file_hash(path)
    index["status"] = "COMPLETE"
    write_manifest(index_path, index)
    return True


def verify_evaluation(root: Path, directory: Path, inputs: dict[str, Any], *, replay: bool) -> dict[str, Any]:
    """Tính lại metric từ raw logits; tùy chọn replay inference để kiểm self-seal dự báo sai."""
    index = read_manifest(directory/"index.json")
    if index["identity"] != inputs["identity"] or index["status"] != "COMPLETE" or set(index["artifacts"]) != {"baseline", "seed17", "seed42", "seed73", "report"}:
        raise ValueError("Evaluation chưa hoàn thành hoặc sai identity")
    for name, digest in index["artifacts"].items():
        if file_hash(directory/(name+".json")) != digest:
            raise ValueError("Evaluation artifact khác index")
    baseline = read_manifest(directory/"baseline.json")
    seeds = {str(s): read_manifest(directory/f"seed{s}.json") for s in (17, 42, 73)}
    report = derive_report(inputs, baseline, seeds)
    if read_manifest(directory/"report.json") != report:
        raise ValueError("Report không khớp raw logits và oracle đã khóa")
    if replay:
        if index["gpu"] != gpu_identity():
            raise ValueError("GPU replay khác identity")
        actual = baseline_stage(inputs, root)
        if any(actual[k] != baseline[k] for k in ("fit", "market_logits", "identity_sha256")):
            raise ValueError("Baseline khác replay train-only")
        device = configure(0, cuda=True)
        for seed in (17, 42, 73):
            actual = seed_stage(inputs, seed, device)
            expected = seeds[str(seed)]
            if any(actual[k] != expected[k] for k in ("logits", "model_tensor_sha256", "checkpoint", "identity_sha256")):
                raise ValueError("Inference replay khác raw logits đã lưu")
    proof = {"version": "mt_bicl_inference_replay_verification_v1", "identity_sha256": content_hash(inputs["identity"]),
             "index_sha256": file_hash(directory/"index.json"), "report_sha256": file_hash(directory/"report.json"),
             "gpu": index["gpu"], "status": "INFERENCE_REPLAY_MATCH", "optimizer_used": False}
    proof_path = directory/"replay_verification.json"
    if proof_path.exists() and read_manifest(proof_path) != proof:
        raise ValueError("Receipt replay không thuộc report/index/identity hiện tại")
    if replay and not proof_path.exists():
        write_manifest(proof_path, proof)
    return report
