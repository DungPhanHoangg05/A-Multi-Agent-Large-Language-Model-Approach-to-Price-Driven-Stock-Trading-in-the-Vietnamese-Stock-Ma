"""Chuẩn bị teacher/corpus v2 offline, seal từng stage và kiểm replay độc lập."""

from __future__ import annotations

from collections import Counter
import hashlib
from pathlib import Path
from typing import Any, Callable

from core.bayesian_memory import read_json
from core.mt_bicl_bank import content_hash
from core.mt_bicl_v2_io import ActiveBudget, read_envelope, write_envelope
from core.mt_bicl_v2_reference import SequentialBetaOracle
from core.mt_bicl_v2_simulator import BetaTaskSimulator, train_feature_pool
from core.mt_bicl_v2_teacher import (
    BetaBernoulliTeacher, fit_hyperprior, grid_records, prior_predictive_audit, train_task_counts,
)
from scripts.verify_mt_bicl_protocol_v2 import DIRECTORY, PROTOCOL_SHA256, validate_spec, verify_evidence

NAMESPACE = Path("outputs/bayesian_benchmark/mt_bicl_v2")
OUTPUT = NAMESPACE / "teacher_v2"
BUDGET_PAYLOAD_SHA256 = "52b7d54ba31f6c02f12c304877a36dbe1958337152f6f77d957644064c128cf4"
CODE = ("core/mt_bicl_v2_teacher.py", "core/mt_bicl_v2_reference.py", "core/mt_bicl_v2_simulator.py",
        "core/mt_bicl_v2_io.py", "core/mt_bicl_v2_preparation.py", "scripts/prepare_mt_bicl_teacher.py",
        "scripts/verify_mt_bicl_protocol_v2.py", "scripts/verify_mt_bicl_protocol.py",
        "core/bayesian_memory.py", "core/prior_run_lock.py")
STREAMS = ("diagnostic", "pilot_tiny", "synthetic_validation", "validation_swap", "synthetic_test", "test_swap")
TEACHER_VERSION = "mt_bicl_teacher_fit_v2"
CORPUS_VERSION = "mt_bicl_corpus_v2"
INDEX_VERSION = "mt_bicl_teacher_index_v2"


def file_hash(path: Path) -> str:
    """Băm streaming, không mở checkpoint bằng torch hoặc load model."""
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024*1024), b""):
            value.update(chunk)
    return value.hexdigest()


def load_inputs(root: Path) -> dict[str, Any]:
    """Kiểm byte/runtime/grant trước đọc nhãn train; không fit, sinh episode hoặc gọi GPU."""
    directory = root / DIRECTORY
    protocol = read_json(directory / "protocol_v2.json")
    artifacts = {name: (directory/name).read_bytes() for name in protocol["artifacts"]}
    validate_spec((directory/"protocol_v2.json").read_bytes(), artifacts)
    membership = read_json(directory/"training_membership_v2.json")
    verify_evidence(root, protocol, membership)
    grant = read_envelope(directory/"budget_v2.json", "mt_bicl_budget_v2")
    if (content_hash(grant) != BUDGET_PAYLOAD_SHA256 or grant["protocol_sha256"] != PROTOCOL_SHA256
            or not grant["budget_authorized"] or grant["additional_hours"] != 10
            or grant["v2_active_allocation_seconds"] != 14400):
        raise ValueError("Grant ngân sách không khớp xác nhận đã khóa")
    bank = read_json(root/"outputs/bayesian_benchmark/mt_bicl_v1/inputs/dense_bank_v1.json")["payload"]
    identity = {"version": "mt_bicl_teacher_identity_v2", "protocol_sha256": PROTOCOL_SHA256,
                "budget_byte_sha256": file_hash(directory/"budget_v2.json"),
                "spec_artifacts_sha256": protocol["artifacts"],
                "code_sha256": {name: file_hash(root/name) for name in CODE}, "runtime": protocol["runtime"]}
    return {"protocol": protocol, "membership": membership, "bank": bank, "identity": identity,
            "manifest": read_json(directory/"corpus_manifest_v2.json"),
            "fixtures": read_json(directory/"protocol_fixtures_v2.json"),
            "budget_identity": {"protocol_sha256": PROTOCOL_SHA256,
                                "grant_payload_sha256": BUDGET_PAYLOAD_SHA256,
                                "cap_seconds": 14400, "W10_stop": grant["W10_stop"]}}


def fixture_input(prior: list[list[int]], target: list[int]) -> dict[str, Any]:
    """Tái dựng fixture count với ID riêng; không dùng outcome hay tham số đã fit."""
    def task(name: str, counts: list[int]) -> dict[str, Any]:
        """Các giá trị bằng nhau vẫn là observation độc lập có ID khác nhau."""
        labels = [1]*counts[0]+[0]*counts[1]
        return {"task_id": name, "observations": [{"observation_id": f"{name}:{j}",
                "x": [0., 0., 0., 0.], "y": y} for j, y in enumerate(labels)]}
    return {"prior": [task(f"P{i}", pair) for i, pair in enumerate(prior)],
            "target": task("T", target), "query": {"observation_id": "Q", "x": [0., 0., 0., 0.]}}


def check_prediction(teacher: BetaBernoulliTeacher, reference: SequentialBetaOracle,
                     data: dict[str, Any], *, pooled: bool = False) -> tuple[dict[str, Any], dict[str, float]]:
    """So p và cả hai log probability với tolerance1e−12, không clip sai khác."""
    actual, expected = teacher.predict(data, pooled=pooled), reference.predict(data, pooled=pooled)
    errors = {key: abs(actual[key]-expected[key]) for key in (
        "probability", "log_probability_one", "log_probability_zero")}
    if max(errors.values()) > 1e-12:
        raise ValueError("Teacher khác oracle tuần tự độc lập")
    return actual, errors


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


def prepare_corpus(inputs: dict[str, Any], fitted: dict[str, Any], teacher_hash: str,
                   stream: str, check_budget: Callable[[], None] = lambda: None) -> dict[str, Any]:
    """Sinh đúng ID đã đăng ký, kiểm toàn bộ oracle; không có learner/optimizer/market evaluation."""
    if not fitted["converged"] or fitted["identity"] != inputs["identity"]:
        raise ValueError("Không được sinh corpus từ teacher chưa hội tụ/khác identity")
    if stream not in STREAMS:
        raise ValueError("Chỉ seal các corpus cố định của teacher")
    pool = train_feature_pool(inputs["bank"], inputs["membership"])
    simulator = BetaTaskSimulator(fitted["pi"], pool, inputs["manifest"])
    teacher, reference = BetaBernoulliTeacher(fitted["pi"]), SequentialBetaOracle(fitted["pi"])
    rows, probabilities = [], []
    maxima = {key: 0. for key in ("probability", "log_probability_one", "log_probability_zero")}
    comparisons, eligible = 0, 0

    def checked(data: dict[str, Any], *, pooled: bool = False) -> dict[str, Any]:
        """Cập nhật max error từ phép tính độc lập cho mọi input, không lấy mẫu con."""
        nonlocal comparisons
        value, errors = check_prediction(teacher, reference, data, pooled=pooled)
        for key, error in errors.items():
            maxima[key] = max(maxima[key], error)
        comparisons += 1
        return value

    spec = inputs["manifest"]["streams"][stream]
    swapped = stream.endswith("_swap")
    for index in range(spec["ids"]["stop_exclusive"]):
        if index % 100 == 0:
            check_budget()
        if swapped:
            row = simulator.pair(stream, index)
            a, b = checked(row["input_a"]), checked(row["input_b"])
            row["oracle_a"], row["oracle_b"] = a, b
            row["pooling_a"], row["pooling_b"] = checked(row["input_a"], pooled=True), checked(row["input_b"], pooled=True)
            delta = b["probability"]-a["probability"]
            row["oracle_delta_b_minus_a"], row["eligible"] = delta, bool(abs(delta) >= .05)
            eligible += int(row["eligible"])
            probabilities.append([a["probability"], b["probability"]])
        else:
            row = simulator.episode(stream, index)
            row["oracle"], row["pooling"] = checked(row["input"]), checked(row["input"], pooled=True)
            probabilities.append(row["oracle"]["probability"])
        rows.append(row)
        if (index+1) % 1000 == 0:
            print(f"Đã kiểm oracle {stream}: {index+1}/{spec['ids']['stop_exclusive']}.", flush=True)
    return {"protocol_sha256": PROTOCOL_SHA256, "identity": inputs["identity"],
            "teacher_byte_sha256": teacher_hash, "manifest_sha256": inputs["protocol"]["artifacts"]["corpus_manifest_v2.json"],
            "feature_pool_sha256": content_hash(pool), "scaler_sha256": pool["scaler_sha256"],
            "stream": stream, "seed": spec["seed"], "episode_ids": [row["episode_id"] for row in rows],
            "episodes": rows, "oracle_probabilities": probabilities,
            "verification": {"oracle_status": "PASS", "independent_predictions": comparisons,
                             "maximum_absolute_differences": maxima,
                             "stress_count": sum(row["sidecar"]["stress"] for row in rows),
                             "eligible_swap_pairs": eligible if swapped else None,
                             "swap_support_status": ("SUFFICIENT" if eligible >= 200 else "INCONCLUSIVE_NO_REDRAW") if swapped else None,
                             "K_histogram": dict(sorted(Counter(str(len(row["input_a" if swapped else "input"]["prior"]))
                                                                   for row in rows).items()))},
            "held_until_selection_seal": spec["held_until_selection_seal"],
            "student_forward_run": False, "training_allowed": False, "decision_calls_allowed": False}


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
