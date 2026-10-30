"""Freeze source/cohort/templates v3 và đối soát validation, chưa cấp quyền primary."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import subprocess
from typing import Any

import httpx

from core.bayesian_memory import read_json
from core.groq_pacing import MODEL_LIMITS, request_budget, tokenizer_cached
from core.improvement_transport import body_contract
from core.mt_bicl_bank import content_hash
from core.mt_bicl_v2_adapter import load_inputs as inherited_inputs
from core.mt_bicl_v2_io import read_envelope, write_envelope
from core.mt_bicl_v2_run_manifest import MANIFEST_PATH as OLD_MANIFEST, MANIFEST_VERSION as OLD_VERSION, verified_upstream
from core.mt_bicl_v21_preparation import file_hash
from core.mt_bicl_v3_contracts import REVISION_BRANCHES, validate_branch
from core.mt_bicl_v3_decision import canonical_request
from core.mt_bicl_v3_policy import resolve_anchor, utility_only
from core.mt_bicl_v3_protocol import verify as verify_protocol, branch_order
from core.mt_bicl_v3_validation import INDEX_VERSION, POINT_VERSION, PROOF_VERSION, REPORT_VERSION
from core.mt_bicl_v3_wire import client, wire_body

OUTPUT = Path("outputs/bayesian_benchmark/mt_bicl_v3/development2023")
MANIFEST = Path("docs/plan/week11/development_manifest_v3.json")
RELEASE = Path("docs/plan/week11/development_release_v3.json")
MANIFEST_VERSION = "utility_icl_development_manifest_v3"
SNAPSHOT_VERSION = "utility_icl_development_snapshot_v3"
DRY_VERSION = "utility_icl_development_dry_run_v3"
RELEASE_VERSION = "utility_icl_development_release_v3"
VALIDATION = Path("outputs/bayesian_benchmark/mt_bicl_v3/offline_validation")
VALIDATION_SHA = "690db24e3c20d25dc446199899e4f6018a3142132db23546d2b1ad55c9d16334"
PROOF_SHA = "507cc8497003106d92b3da99685df35a20a001bcd1ad56ce10bf81c6cef0fbcf"
CODE = ("core/mt_bicl_v3_wire.py", "core/mt_bicl_v3_run.py", "core/mt_bicl_v3_transport.py",
        "core/mt_bicl_v3_freeze.py", "core/mt_bicl_v3_preflight.py", "scripts/prepare_mt_bicl_v3.py",
        "scripts/continue_mt_bicl_v3.py", "tests/test_mt_bicl_v3_freeze.py", "tests/test_mt_bicl_v3_recovery.py")


def layout(protocol: dict[str, Any]) -> dict[str, Any]:
    """96 block và804 slot đúng j toàn cohort, sample12 đã khóa trước outcome v3."""
    ids = protocol["development"]["point_ids"]
    selected = protocol["development"]["repeat_selection"]["point_ids"]
    if len(ids) != 60 or len(set(ids)) != 60 or len(selected) != 12 or len(set(selected)) != 12 or not set(selected) <= set(ids):
        raise ValueError("Cohort/repeat v3 không đúng60/12 ID")
    blocks = [{"point_id": pid, "point_index": j, "repeat_index": r, "order": branch_order(j, r)}
              for r in (0, 1, 2, 3) for j, pid in enumerate(ids) if r == 0 or pid in selected]
    slots = [{"slot_index": i, "point_id": block["point_id"], "point_index": block["point_index"],
              "repeat_index": block["repeat_index"], "branch_id": name}
             for i, (block, name) in enumerate((block, name) for block in blocks for name in block["order"])]
    if len(slots) != 804: raise ValueError("Ma trận phải đủ804 slot kể cả bypass")
    return {"point_ids": ids, "repeat_selection": selected, "blocks": blocks, "slots": slots}


def fixture_reply(facts: dict[str, Any], decision: str = "SHORT") -> dict[str, Any]:
    """Decision fixture chỉ kiểm plumbing, không là response thị trường hoặc nhãn query."""
    return {"version": "utility_icl_reply_v3", "decision": decision, "forecast_horizon": "T+2.5", "confidence": "Thấp",
            "risk_reward_ratio": 1., "evidence_for": "Fixture offline.", "evidence_against": "Không suy luận LLM.",
            "justification": "Chỉ kiểm giao thức, không dùng làm kết quả thị trường.", "fact_ids": list(facts["assertions"]),
            "fact_assertions": deepcopy(facts["assertions"]), "context_reason": "NOT_APPLICABLE"}


def legacy_fixture(decision: str = "SHORT") -> dict[str, Any]:
    """Bảy field legacy, không chèn trace anchored vào Original/A."""
    return {"decision": decision, "forecast_horizon": "T+2.5", "confidence": "Thấp", "risk_reward_ratio": 1.,
            "evidence_for": "Fixture offline.", "evidence_against": "Không suy luận LLM.", "justification": "Chỉ kiểm plumbing."}


def collect(root: Path) -> dict[str, Any]:
    """Chỉ hash/reuse inference đã cold-verify; upstream60 point được đối soát một lần."""
    verify_protocol(root)
    if file_hash(root/VALIDATION/"report.json") != VALIDATION_SHA or file_hash(root/VALIDATION/"replay.json") != PROOF_SHA:
        raise ValueError("Validation v3 khác bản nghiệm thu W11-09")
    report = read_envelope(root/VALIDATION/"report.json", REPORT_VERSION)
    proof = read_envelope(root/VALIDATION/"replay.json", PROOF_VERSION)
    index = read_envelope(root/VALIDATION/"index.json", INDEX_VERSION)
    if (report["status"] != "OFFLINE_VALIDATION_PASS" or report["failed_gates"] or proof["status"] != "REPLAY_MATCH"
            or proof["point_tree_sha256"] != content_hash(index["points"]) or index["identity"] != report["identity"]):
        raise ValueError("Thiếu gate/replay/membership v3 trước freeze")
    for group in ("source_sha256", "input_sha256"):
        for name, checksum in report["identity"][group].items():
            if file_hash(root/name) != checksum: raise ValueError("Nguồn validation thay đổi: "+name)
    for pid, checksum in index["points"].items():
        if file_hash(root/VALIDATION/"points"/(pid+".json")) != checksum: raise ValueError("Point validation bị sửa")
    inherited = inherited_inputs(root)
    shared, upstream, references = verified_upstream(root, inherited)
    protocol = read_json(root/"docs/plan/week11/protocol_v3.json")
    points = {}
    for pid in protocol["development"]["point_ids"]:
        point = read_envelope(root/VALIDATION/"points"/(pid+".json"), POINT_VERSION)
        facts = point["context"]["v3"]["query_facts"]
        for branch in point["variants"].values(): validate_branch(branch)
        points[pid] = {"facts": facts, "shared": shared[pid], "shared_sha256": content_hash(shared[pid]),
                       "variants": point["variants"], "context_sha256": point["context_sha256"],
                       "validation_point_sha256": index["points"][pid], "a_reference": references[pid],
                       "offline_utility_only": utility_only(facts, point["variants"]["Utility_only"])}
    return {"scope": "FROZEN_INPUTS_NOT_MARKET_RESPONSES", "protocol": protocol, "points": points, "upstream": upstream,
            "validation_report_sha256": VALIDATION_SHA, "validation_proof_sha256": PROOF_SHA}


def templates(point: dict[str, Any], protocol: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Hai a0 và hash nguồn mẫu chỉ để bound renderer; nguồn a0 thật phải bind raw/UUID ở run."""
    result = {}
    for name in (*protocol["decision"]["llm_matrix"], "Original_duplicate"):
        if name in REVISION_BRANCHES:
            if not point["variants"][name]["eligible"]:
                result[name] = []
                continue
            values = []
            for a0 in ("LONG", "SHORT"):
                anchor = resolve_anchor(point["facts"], legacy_fixture(a0), fixture_reply(point["facts"], a0),
                    original_source_sha256="0"*64, anchor_source_sha256="1"*64, request_id="00000000-0000-4000-8000-000000000001")
                values.append(canonical_request(point["shared"], protocol, branch_id=name, packet=point["facts"],
                                               projection=point["variants"][name]["projection"], anchor=anchor))
            result[name] = values
        else:
            result[name] = [canonical_request(point["shared"], protocol, branch_id=name, packet=point["facts"] if name == "Fact_Anchor" else None,
                                            prefix=point["a_reference"]["prefix"] if name == "A_reference" else "")]
    return result


def prepare(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Khóa manifest trước control/response v3, không đọc key hoặc gọi HTTP thật."""
    if (root/MANIFEST).exists(): return verify(root)
    if not tokenizer_cached(): raise ValueError("Thiếu tokenizer đã kiểm, không tải cache ngầm")
    snapshot = collect(root)
    protocol = snapshot["protocol"]
    commit = subprocess.check_output(["git", "log", "-1", "--format=%H", "--", *CODE], cwd=root, text=True).strip()
    for name in CODE:
        if subprocess.check_output(["git", "show", commit+":"+name], cwd=root) != (root/name).read_bytes():
            raise ValueError("Source freeze chưa neo Git: "+name)
    bounds = {}
    old = read_envelope(root/OLD_MANIFEST, OLD_VERSION)
    def reject(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Freeze không được HTTP")
    with httpx.Client(transport=httpx.MockTransport(reject)) as http:
        llm = client(protocol["decision"]["config"], http, "offline-no-credential")
        for pid, point in snapshot["points"].items():
            bounds[pid] = {}
            for name, requests in templates(point, protocol).items():
                bodies = [wire_body(llm, request) for request in requests]
                reserve = max((request_budget(body) for body in bodies), default=0)
                # Trường động duy nhất trong prompt là a0 và16 ký tự hash hex, có padding token bảo thủ.
                upper = reserve+64 if name in REVISION_BRANCHES and reserve else reserve
                if upper > MODEL_LIMITS[protocol["decision"]["config"]["signal_config"]["models"]["agent_llm_model"]]["tpm"]:
                    raise ValueError("Token upper bound vượt TPM")
                bounds[pid][name] = {"reserved_tokens_upper": upper, "max_prompt_chars": max((len(r["messages"][0]["content"]) for r in requests), default=0),
                                    "template_http_contracts": [body_contract(body) for body in bodies], "requires_HTTP_if_anchor_valid": bool(requests)}
            previous = next(r["http_contract"] for r in old["requests"] if r["point_id"] == pid and r["repeat_index"] == 0 and r["branch_id"] == "Original")
            if bounds[pid]["Original"]["template_http_contracts"] != [previous]: raise ValueError("Original v3 khác body v2 trên upstream giống nhau")
    manifest = {"version": MANIFEST_VERSION, "scope": "DEVELOPMENT_2023_ONLY", "status": "FROZEN_BEFORE_V3_RESPONSES",
        "source_commit": commit, "source_sha256": {name: file_hash(root/name) for name in CODE},
        "runtime": protocol["runtime"], "candidate": protocol["candidate"], "protocol_sha256": file_hash(root/"docs/plan/week11/protocol_v3.json"),
        "snapshot_sha256": content_hash(snapshot), "layout": layout(protocol), "request_bounds": bounds,
        "ledger_baseline": deepcopy(protocol["ledger_baseline"]), "validation_report_sha256": VALIDATION_SHA, "validation_proof_sha256": PROOF_SHA,
        "dynamic_fields": ["anchor_action", "anchor_source_sha256"], "dynamic_policy": "DERIVE_FROM_DURABLE_ORIGINAL_AND_FACT_ANCHOR_SAME_POINT_REPEAT",
        "preflight_required": True, "primary_allowed": False, "confirmation_allowed": False, "training_allowed": False}
    write_envelope(root/OUTPUT/"freeze/input_snapshot.json", SNAPSHOT_VERSION, snapshot, immutable=True)
    write_envelope(root/MANIFEST, MANIFEST_VERSION, manifest, immutable=True)
    return manifest, snapshot


def verify(root: Path, *, require_anchor: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    """Hash/source/Git/cold proof phải còn đúng; không tính lại inference hoặc đọc key."""
    manifest = read_envelope(root/MANIFEST, MANIFEST_VERSION)
    verify_protocol(root)
    snapshot = read_envelope(root/OUTPUT/"freeze/input_snapshot.json", SNAPSHOT_VERSION)
    if content_hash(snapshot) != manifest["snapshot_sha256"] or layout(snapshot["protocol"]) != manifest["layout"]:
        raise ValueError("Snapshot/layout khác manifest")
    protocol = read_json(root/"docs/plan/week11/protocol_v3.json")
    if (manifest["candidate"] != protocol["candidate"] or manifest["runtime"] != protocol["runtime"]
            or manifest["protocol_sha256"] != file_hash(root/"docs/plan/week11/protocol_v3.json")
            or manifest["ledger_baseline"] != protocol["ledger_baseline"] or manifest["primary_allowed"] is not False
            or manifest["confirmation_allowed"] is not False or manifest["training_allowed"] is not False):
        raise ValueError("Manifest đổi candidate/runtime/quyền hoặc reset ledger")
    if content_hash(collect(root)) != manifest["snapshot_sha256"]:
        raise ValueError("Snapshot khác validation/upstream thật đã khóa")
    if file_hash(root/VALIDATION/"report.json") != VALIDATION_SHA or file_hash(root/VALIDATION/"replay.json") != PROOF_SHA:
        raise ValueError("Validation thay đổi sau freeze")
    report = read_envelope(root/VALIDATION/"report.json", REPORT_VERSION)
    for group in ("source_sha256", "input_sha256"):
        for name, checksum in report["identity"][group].items():
            if file_hash(root/name) != checksum: raise ValueError("Nguồn/runtime validation thay đổi: "+name)
    upstream = snapshot["upstream"]
    if file_hash(root/upstream["cohort_path"]) != upstream["cohort_sha256"]: raise ValueError("Cohort upstream thay đổi")
    for point in upstream["points"].values():
        for kind in ("point", "journal"):
            if file_hash(root/point[kind+"_path"]) != point[kind+"_sha256"]: raise ValueError("Nguồn upstream đã khóa bị sửa")
    for name, checksum in manifest["source_sha256"].items():
        if file_hash(root/name) != checksum or subprocess.check_output(["git", "show", manifest["source_commit"]+":"+name], cwd=root) != (root/name).read_bytes():
            raise ValueError("Source runner khác freeze: "+name)
    if require_anchor and subprocess.check_output(["git", "show", "HEAD:"+MANIFEST.as_posix()], cwd=root) != (root/MANIFEST).read_bytes():
        raise ValueError("Manifest chưa neo byte Git trước API")
    return manifest, snapshot
