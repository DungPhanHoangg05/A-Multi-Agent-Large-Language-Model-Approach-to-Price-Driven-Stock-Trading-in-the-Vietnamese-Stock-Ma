"""Áp dụng amendment số vòng EM v2.1, giữ nguyên thuật toán/corpus và bằng chứng v2."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Callable

from core.bayesian_memory import read_json
from core.mt_bicl_bank import content_hash
from core.mt_bicl_v2_io import ActiveBudget, read_envelope, write_envelope
from core.mt_bicl_v2_preparation import (
    BUDGET_PAYLOAD_SHA256, NAMESPACE, STREAMS, check_prediction, file_hash,
    fixture_input, load_inputs as load_base_inputs, prepare_corpus as prepare_base_corpus,
)
from core.mt_bicl_v2_reference import SequentialBetaOracle
from core.mt_bicl_v2_teacher import BetaBernoulliTeacher, grid_records, prior_predictive_audit, train_task_counts
from core.mt_bicl_v21_teacher import fit_hyperprior
from scripts.verify_mt_bicl_protocol_v2 import DIRECTORY, PROTOCOL_SHA256 as BASE_PROTOCOL_SHA256

PROTOCOL_SHA256 = "16f31de4f3d3a24d36b059ae1929001b618f3805a7fb95a2cd8d969bae3a8952"
PREREGISTRATION_COMMIT = "ab59534"
OUTPUT = NAMESPACE / "teacher_v2_1"
TEACHER_VERSION = "mt_bicl_teacher_fit_v2_1"
CORPUS_VERSION = "mt_bicl_corpus_v2_1"
INDEX_VERSION = "mt_bicl_teacher_index_v2_1"
CODE = ("core/mt_bicl_v21_teacher.py", "core/mt_bicl_v21_preparation.py", "scripts/prepare_mt_bicl_teacher_v21.py")


def validate_amendment(data: bytes) -> dict[str, Any]:
    """Chỉ nhận delta một thay đổi đã khóa; không nhận reseal hoặc nới gate."""
    if hashlib.sha256(data).hexdigest() != PROTOCOL_SHA256:
        raise ValueError("Amendment v2.1 khác SHA-256 khóa, không self-seal")
    value = json.loads(data)
    if (value["parent_protocol_sha256"] != BASE_PROTOCOL_SHA256
            or value["changes"] != [{"path": "teacher.fit.max_iterations", "from": 200, "to": 1000}]
            or value["budget_grant_payload_sha256"] != BUDGET_PAYLOAD_SHA256
            or not value["budget_not_reset"] or not value["all_other_parent_values_inherited"]):
        raise ValueError("Amendment không đúng thay đổi số vòng đã đăng ký")
    return value


def load_inputs(root: Path) -> dict[str, Any]:
    """Kiểm prereg Git, nguyên byte v2 và ngân sách; không fit hoặc sinh corpus."""
    path = root/DIRECTORY/"protocol_v2_1.json"
    amendment = validate_amendment(path.read_bytes())
    prereg = subprocess.run(["git", "show", PREREGISTRATION_COMMIT+":docs/plan/week10/protocol_v2_1.json"],
                            cwd=root, capture_output=True, check=False)
    if prereg.returncode or hashlib.sha256(prereg.stdout).hexdigest() != PROTOCOL_SHA256:
        raise ValueError("Amendment chưa được commit đúng bản trước fit production")
    for name, expected in {**amendment["preserved_code_sha256"], **amendment["preserved_evidence_sha256"]}.items():
        if file_hash(root/name) != expected:
            raise ValueError("Nguồn/bằng chứng STOP200 bị sửa: "+name)
    inputs = load_base_inputs(root)
    parent = inputs["protocol"]
    protocol = deepcopy(parent)
    protocol["teacher"]["fit"]["max_iterations"] = 1000
    reset = deepcopy(protocol)
    reset["teacher"]["fit"]["max_iterations"] = 200
    if reset != parent:
        raise ValueError("Effective protocol thay đổi ngoài trần EM")
    inputs["protocol"] = protocol
    inputs["amendment"] = amendment
    inputs["identity"] = {**inputs["identity"], "version": "mt_bicl_teacher_identity_v2_1",
                          "base_protocol_sha256": BASE_PROTOCOL_SHA256, "protocol_sha256": PROTOCOL_SHA256,
                          "preregistration_commit": PREREGISTRATION_COMMIT,
                          "code_sha256": {**inputs["identity"]["code_sha256"],
                                          **{name: file_hash(root/name) for name in CODE}}}
    return inputs


def prepare_corpus(inputs: dict[str, Any], fitted: dict[str, Any], teacher_hash: str,
                   stream: str, check_budget: Callable[[], None] = lambda: None) -> dict[str, Any]:
    """Dùng nguyên builder/RNG/oracle v2; chỉ bind metadata về amendment và teacher mới."""
    value = prepare_base_corpus(inputs, fitted, teacher_hash, stream, check_budget)
    value["base_protocol_sha256"] = BASE_PROTOCOL_SHA256
    value["protocol_sha256"] = PROTOCOL_SHA256
    return value


def prepare_teacher(inputs: dict[str, Any]) -> dict[str, Any]:
    """Fit đúng recipe; không hội tụ chỉ lưu chẩn đoán, không tạo corpus hoặc fallback."""
    uniform_teacher, uniform_reference = BetaBernoulliTeacher([1/16]*16), SequentialBetaOracle([1/16]*16)
    checked = []
    for fixture in inputs["fixtures"]["teacher_cases"]:
        data = fixture_input(fixture["prior_counts"], fixture["target_counts"])
        values = {}
        for pooled, key in ((False, "p"), (True, "pooling_p")):
            result, errors = check_prediction(uniform_teacher, uniform_reference, data, pooled=pooled)
            if abs(result["probability"]-fixture[key]) > fixture["atol"]:
                raise ValueError("Teacher không khớp fixture đặc tả")
            values[key] = {"actual": result["probability"], "expected": fixture[key], "errors": errors}
        checked.append({"id": fixture["id"], **values})
    tasks = train_task_counts(inputs["bank"], inputs["membership"])
    result = fit_hyperprior(tasks)
    predictive = prior_predictive_audit(tasks, result["pi"], inputs["manifest"]["streams"]["prior_predictive"]["seed"]) \
        if result["converged"] else {"status": "NOT_RUN_TEACHER_NONCONVERGENCE"}
    return {"protocol_sha256": PROTOCOL_SHA256, "identity": inputs["identity"],
            "source_sha256": inputs["identity"]["code_sha256"], "runtime": inputs["protocol"]["runtime"],
            "train_membership_sha256": inputs["protocol"]["artifacts"]["training_membership_v2.json"],
            "grid": grid_records(), **result, "task_counts": tasks,
            "prior_predictive_audit": predictive, "uniform_fixture_audit": checked,
            "training_allowed": False, "development_allowed": False, "decision_calls_allowed": False}


def run_preparation(root: Path, inputs: dict[str, Any], *, resume: bool) -> dict[str, Any]:
    """Journal từng stage immutable; caller giữ OS lock namespace v2 dùng chung."""
    output = root/OUTPUT
    index_path = output/"index.json"
    if index_path.exists():
        if not (root/NAMESPACE/"active_budget_v2.json").exists():
            raise ValueError("Journal đã có nhưng mất budget; không reset ngân sách")
        if not resume:
            raise ValueError("Run đã có; dùng --resume để kiểm rồi tiếp tục")
        index = read_envelope(index_path, INDEX_VERSION)
        if index["identity"] != inputs["identity"]:
            raise ValueError("Source/runtime/input đã đổi, không resume bằng identity mới")
    else:
        index = {"identity": inputs["identity"], "status": "PREPARING", "files": {},
                 "student_forward_run": False, "training_allowed": False,
                 "development_allowed": False, "decision_calls_allowed": False}
    with ActiveBudget(root/NAMESPACE/"active_budget_v2.json", inputs["budget_identity"]) as budget:
        def stage(name: str, version: str, build: Callable[[], dict[str, Any]]) -> dict[str, Any]:
            """Đối soát stage đã commit; orphan chỉ được nhận sau rebuild so toàn payload."""
            budget.check()
            path = output/name
            if name in index["files"]:
                if file_hash(path) != index["files"][name]["sha256"]:
                    raise ValueError("Stage đã khóa bị sửa: "+name)
                value = read_envelope(path, version)
                if value["identity"] != inputs["identity"]:
                    raise ValueError("Stage khác identity")
                return value
            value = build()
            budget.check()
            write_envelope(path, version, value, immutable=True)
            index["files"][name] = {"sha256": file_hash(path), "version": version, "bytes": path.stat().st_size}
            write_envelope(index_path, INDEX_VERSION, index)
            return value

        fitted = stage("teacher_fit.json", TEACHER_VERSION, lambda: prepare_teacher(inputs))
        if fitted["converged"]:
            teacher_hash = file_hash(output/"teacher_fit.json")
            for stream in STREAMS:
                stage(stream+".json", CORPUS_VERSION,
                      lambda stream=stream: prepare_corpus(inputs, fitted, teacher_hash, stream, budget.check))
            index["status"] = "COMPLETE_TEACHER_ORACLE_ONLY"
        else:
            index["status"] = fitted["status"]
        write_envelope(index_path, INDEX_VERSION, index)
    return index


def verify_preparation(root: Path, inputs: dict[str, Any], *, replay: bool) -> dict[str, Any]:
    """Kiểm hash/source mọi stage; replay tái dựng fit/corpus, không train student."""
    output = root/OUTPUT
    index = read_envelope(output/"index.json", INDEX_VERSION)
    if index["identity"] != inputs["identity"]:
        raise ValueError("Index teacher khác source/runtime hiện hành")
    fitted = read_envelope(output/"teacher_fit.json", TEACHER_VERSION)
    expected_names = {"teacher_fit.json", *(stream+".json" for stream in STREAMS)} if fitted["converged"] else {"teacher_fit.json"}
    expected_status = "COMPLETE_TEACHER_ORACLE_ONLY" if fitted["converged"] else "STOP_TEACHER_NONCONVERGENCE_NO_UNIFORM_FALLBACK"
    if set(index["files"]) != expected_names or index["status"] != expected_status:
        raise ValueError("Journal chưa hoàn tất hoặc không khớp trạng thái teacher")
    for name, descriptor in index["files"].items():
        path = output/name
        if file_hash(path) != descriptor["sha256"] or path.stat().st_size != descriptor["bytes"]:
            raise ValueError("Hash/size stage không khớp: "+name)
        value = read_envelope(path, descriptor["version"])
        if value["identity"] != inputs["identity"] or value["training_allowed"] or value["decision_calls_allowed"]:
            raise ValueError("Stage identity/quyền thực thi không hợp lệ")
    if replay:
        with ActiveBudget(root/NAMESPACE/"active_budget_v2.json", inputs["budget_identity"]) as budget:
            if fitted != prepare_teacher(inputs):
                raise ValueError("Teacher/EM/PPC khác cold replay")
            if fitted["converged"]:
                for stream in STREAMS:
                    actual = read_envelope(output/(stream+".json"), CORPUS_VERSION)
                    expected = prepare_corpus(inputs, fitted, file_hash(output/"teacher_fit.json"), stream, budget.check)
                    if actual != expected:
                        raise ValueError("Corpus/oracle khác cold replay: "+stream)
                    budget.check()
    return {"integrity": "PASS", "teacher_status": fitted["status"],
            "replay": "PASS" if replay else "NOT_REQUESTED", "files": index["files"],
            "iterations": fitted["iterations"], "max_pi_delta": fitted["max_pi_delta"],
            "training_allowed": False, "development_allowed": False, "decision_calls_allowed": False}
