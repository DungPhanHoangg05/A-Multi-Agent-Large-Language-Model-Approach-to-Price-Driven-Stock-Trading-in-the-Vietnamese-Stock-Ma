"""Khóa đặc tả utility-ICL v3; chỉ kiểm metadata/schema, chưa triển khai mô hình hoặc policy."""

from __future__ import annotations

from datetime import date
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping

from jsonschema import Draft202012Validator, FormatChecker

from core.bayesian_memory import read_json
from core.mt_bicl_bank import canonical_bytes, content_hash
from core.mt_bicl_v2_io import read_envelope, write_envelope
from core.mt_bicl_v2_nomination import VERSION as NOMINATION_VERSION, evidence_snapshot
from core.mt_bicl_v2_release import git_value, verify_release
from core.mt_bicl_v21_preparation import file_hash
from core.prior_run_lock import safe_path

DIRECTORY = Path("docs/plan/week11")
PROTOCOL = DIRECTORY/"protocol_v3.json"
LOCK = DIRECTORY/"protocol_lock_v3.json"
LOCK_VERSION = "utility_icl_protocol_lock_v3"
PROTOCOL_SHA256 = "1912d18145fcc0eb46563206a83cfbacf5420d48fd828d0f79abfb56fa0b7b48"
CODE = ("core/mt_bicl_v3_protocol.py", "scripts/verify_mt_bicl_protocol_v3.py", "tests/test_mt_bicl_v3_protocol.py")
PREFIX = ("Original", "A_reference", "Fact_Anchor")
REVISIONS = ("Plain_revision", "Full_utility_ICL", "No_utility", "No_target", "Stats_only")


def branch_order(j: int, repeat: int = 0) -> list[str]:
    """Khóa thứ tự slot; j luôn là index toàn cohort, duplicate không shared cache."""
    if type(j) is not int or j < 0 or type(repeat) is not int or repeat not in (0, 1, 2, 3):
        raise ValueError("Index point/repeat ngoài protocol v3")
    tail = [*REVISIONS, *(["Original_duplicate"] if repeat else [])]
    shift = ((3*j+repeat-1) if repeat else j) % len(tail)
    return [*PREFIX, *tail[shift:], *tail[:shift]]


def repeat_ids(point_ids: list[str], changed_ids: list[str]) -> list[str]:
    """Mẫu12 có chủ đích sau exposure v2; không đọc outcome hoặc action v3."""
    if (len(point_ids) != 60 or len(set(point_ids)) != 60 or len(changed_ids) != 5
            or len(set(changed_ids)) != 5 or not set(changed_ids) <= set(point_ids)):
        raise ValueError("Cohort hoặc năm ID action-change v2 không đúng")
    ranked = sorted((p for p in point_ids if p not in changed_ids),
                    key=lambda p: (hashlib.sha256(("v3-repeat|"+p).encode("utf-8")).hexdigest(), p))
    return sorted([*changed_ids, *ranked[:7]], key=point_ids.index)


def component_seed(protocol_sha256: str, point_id: str, component: str) -> str:
    """Seed uint128 dạng chuỗi JSON; tách stream theo component, không theo nhánh/lượt."""
    if (type(protocol_sha256) is not str or type(point_id) is not str or type(component) is not str
            or not re.fullmatch(r"[0-9a-f]{64}", protocol_sha256) or not re.fullmatch(r"(FPT|MWG|VCB|VNM)-20\d{2}-\d{2}-\d{2}", point_id)):
        raise ValueError("Protocol hash hoặc query ID seed không hợp lệ")
    date.fromisoformat(point_id[4:])
    if component not in ("lambda", "theta") and not re.fullmatch(r"magnitude\|(FPT|MWG|VCB|VNM)-20\d{2}-\d{2}-\d{2}", component):
        raise ValueError("Seed component không thuộc CRN đã khóa")
    material = "utility-v3|"+protocol_sha256+"|"+point_id+"|"+component
    return str(int.from_bytes(hashlib.sha256(material.encode("utf-8")).digest()[:16], "big"))


def validate_document(value: Any, schema: dict[str, Any]) -> None:
    """Chỉ $ref nội bộ; từ chối kiểu NumPy/nonfinite trước JSON Schema, không fetch URI."""
    canonical_bytes(value)
    def check_refs(node: Any) -> None:
        """Không cho schema truy cập file/network bên ngoài trong bước metadata."""
        if type(node) is dict:
            if "$ref" in node and not node["$ref"].startswith("#/"):
                raise ValueError("Schema không được dùng reference bên ngoài")
            for child in node.values():
                check_refs(child)
        elif type(node) is list:
            for child in node:
                check_refs(child)
    check_refs(schema)
    Draft202012Validator.check_schema(schema)
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value))
    if errors:
        raise ValueError("Tài liệu không đúng schema utility-ICL v3")


def validate_bundle(data: bytes, artifacts: Mapping[str, bytes]) -> dict[str, Any]:
    """Không chấp nhận self-rehash; ràng buộc số học và scope trước bước08."""
    if hashlib.sha256(data).hexdigest() != PROTOCOL_SHA256:
        raise ValueError("Protocol v3 khác byte đã khóa; cần amendment trước run")
    protocol = json.loads(data)
    canonical_bytes(protocol)
    if set(artifacts) != set(protocol["artifacts_sha256"]):
        raise ValueError("Thiếu/thừa artifact protocol v3")
    values = {}
    for name, checksum in protocol["artifacts_sha256"].items():
        if hashlib.sha256(artifacts[name]).hexdigest() != checksum:
            raise ValueError("Artifact khác binding protocol v3: "+name)
        values[name] = json.loads(artifacts[name])
        canonical_bytes(values[name])
    if any(protocol[k] is not False for k in ("training_allowed", "teacher_fit_allowed", "development_allowed", "decision_calls_allowed", "confirmation_allowed")):
        raise ValueError("Đặc tả không cấp quyền train/refit/API")
    budget = values[(DIRECTORY/"budget_v3.json").as_posix()]
    if (budget["cap_seconds"] != 18*3600 or budget["charged_seconds_at_reset"] != 0
            or budget["deduct_v1_v2_runtime"] is not False or budget["new_API_quota_granted"] is not False
            or budget["resume_and_W12"] != "SAME_COUNTER_NO_RESET"):
        raise ValueError("Ngân sách v3 phải là18 giờ mới sau reset, không lấy số dư v2")
    development, confirmation = protocol["development"], protocol["confirmation"]
    if (protocol["decision"]["llm_matrix"] != [*PREFIX, *REVISIONS]
            or development["primary_slots"] != 8*60 or development["repeat_slots"] != 12*3*9
            or development["nominal_max_slots"] != 804 or confirmation["nominal_max_slots"] != 8*128+12*3*9):
        raise ValueError("Ma trận/số slot không đúng protocol")
    sample = development["repeat_selection"]
    expected = repeat_ids(development["point_ids"], sample["changed_v2_ids"])
    fixtures = values[(DIRECTORY/"protocol_fixtures_v3.json").as_posix()]
    Draft202012Validator.check_schema(values[(DIRECTORY/"utility_icl_v3.schema.json").as_posix()])
    if expected != sample["point_ids"] or expected != fixtures["development_repeat_ids"]:
        raise ValueError("Repeat ID khác quy tắc đã đăng ký")
    if len(confirmation["secondary"]) != 7 or confirmation["bootstrap"]["secondary_ci"] != 1-.05/7:
        raise ValueError("Family xác nhận phải có7 secondary Bonferroni")
    if (protocol["utility"]["draws"] != 4096 or protocol["utility"]["support"] != {"K_min": 2, "gain_min": 5, "loss_min": 5, "zero_net_in_loss": True}
            or protocol["policy"]["zero_threshold"] != 0. or development["nomination"]["D_Full_Fact_Anchor_strict_min"] != 0):
        raise ValueError("Utility/support/nomination khác đặc tả")
    seed = fixtures["seed"]
    if component_seed(seed["protocol_sha256"], seed["point_id"], seed["component"]) != seed["uint128_decimal"]:
        raise ValueError("Fixture seed không đúng SHA-256")
    for case in fixtures["utility_analytic_cases"]:
        actual = case["theta_mean"]*case["gain_mean"]-(1-case["theta_mean"])*case["loss_mean"]
        if not math.isclose(actual, case["U"], rel_tol=0, abs_tol=1e-15):
            raise ValueError("Fixture mean utility sai dấu/đơn vị")
    return protocol


def verify_ledger(ledger: dict[str, Any], baseline: dict[str, Any]) -> None:
    """Cho phép append sau release v3, không sửa/xóa request/reserve đã có."""
    rows = ledger["requests"]
    if (len(rows) < baseline["count"] or len({r["id"] for r in rows}) != len(rows)
            or content_hash(rows[:baseline["count"]]) != baseline["requests_prefix_sha256"]):
        raise ValueError("Ledger bị reset, sửa row nền hoặc trùng UUID")


def verify_inputs(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Đối soát source/weights/π/runtime v2, chỉ hash; không forward, fit hoặc mở2025 outcome."""
    data = (root/PROTOCOL).read_bytes()
    if hashlib.sha256(data).hexdigest() != PROTOCOL_SHA256:
        raise ValueError("Protocol v3 khác byte trước đọc dependency")
    protocol = json.loads(data)
    artifacts = {name: safe_path(root, name).read_bytes() for name in protocol["artifacts_sha256"]}
    validate_bundle(data, artifacts)
    parent = protocol["parent"]
    for path_key, checksum_key in (("nomination_path", "nomination_sha256"), ("release_path", "release_sha256"), ("report_path", "report_sha256")):
        if file_hash(safe_path(root, parent[path_key])) != parent[checksum_key]:
            raise ValueError("Dependency v2 khác receipt đã nghiệm thu")
    nomination = read_envelope(root/parent["nomination_path"], NOMINATION_VERSION)
    if nomination["status"] != "NOT_NOMINATED" or nomination["confirmation_v2"]["allowed"] is not False:
        raise ValueError("Phải đóng v2 trước protocol mới")
    release = verify_release(root)
    if protocol["runtime"] != release["runtime"] or protocol["candidate"] != release["candidate"]:
        raise ValueError("V3 đổi runtime hoặc candidate đã khóa")
    for section in ("inherited_source_sha256", "frozen_assets_sha256"):
        for name, checksum in protocol[section].items():
            if file_hash(safe_path(root, name)) != checksum:
                raise ValueError("Source/artifact kế thừa bị sửa: "+name)
    report = read_json(root/parent["report_path"])["payload"]
    actual_changes = [r["point_id"] for r in report["sensitivity"]["Original"]["leave_one_change_out"]]
    if actual_changes != protocol["development"]["repeat_selection"]["changed_v2_ids"]:
        raise ValueError("Năm case đã exposed không khớp report v2")
    verify_ledger(read_json(root/"outputs/oos_pilot/api_usage.json"), protocol["ledger_baseline"])
    evidence = evidence_snapshot(root)
    return protocol, evidence


def lock_facts(root: Path, evidence: dict[str, Any], commit: str) -> dict[str, Any]:
    """Nội dung receipt được tái dựng toàn bộ, không tin cờ trạng thái tự khai."""
    return {"status": "SPEC_LOCK_PASS", "protocol_sha256": PROTOCOL_SHA256, "source_commit": commit,
        "source_sha256": {name: file_hash(root/name) for name in CODE}, "v2_evidence": evidence,
        "budget_cap_seconds": 64800, "charged_experiment_seconds_at_lock": 0,
        "budget_counter_materialized_at_lock": False, "API_allowed": False,
        "next_task": "W11-08", "utility_implementation_exists_at_lock": False,
        "development_slots": 804, "confirmation_slots_conditional": 1348}


def freeze(root: Path) -> dict[str, Any]:
    """Tạo receipt spec-only sau commit source; không tạo counter hoặc namespace thực nghiệm."""
    if (root/LOCK).exists():
        return verify(root)
    protocol, evidence = verify_inputs(root)
    commit = git_value(root, "log", "-1", "--format=%H", "--", *CODE)
    git_value(root, "diff", "--exit-code", commit, "--", *CODE)
    for name in (*CODE, PROTOCOL.as_posix(), *protocol["artifacts_sha256"]):
        git_value(root, "cat-file", "-e", commit+":"+name)
    result = lock_facts(root, evidence, commit)
    write_envelope(root/LOCK, LOCK_VERSION, result, immutable=True)
    return result


def verify(root: Path) -> dict[str, Any]:
    """Receipt/hash/Git phải cùng bản khóa; không sửa cờ API trong protocol lịch sử."""
    protocol, evidence = verify_inputs(root)
    saved = read_envelope(root/LOCK, LOCK_VERSION)
    if content_hash(saved) != content_hash(lock_facts(root, evidence, saved["source_commit"])):
        raise ValueError("Receipt spec v3 khác source/budget/evidence")
    git_value(root, "merge-base", "--is-ancestor", saved["source_commit"], "HEAD")
    git_value(root, "diff", "--exit-code", saved["source_commit"], "--", *CODE)
    for relative in (PROTOCOL.as_posix(), LOCK.as_posix(), *protocol["artifacts_sha256"]):
        anchored = subprocess.run(["git", "show", "HEAD:"+relative], cwd=root, capture_output=True, check=True)
        if anchored.stdout != (root/relative).read_bytes():
            raise ValueError("Artifact spec v3 chưa neo đúng byte Git: "+relative)
    return saved
