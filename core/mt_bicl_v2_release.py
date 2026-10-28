"""Freeze và verifier lạnh cho release development v2; không train, inference hoặc gọi API."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import math
import os
from pathlib import Path
import platform
import subprocess
from typing import Any

from agents.decision_agent import TradeDecisionOutput
from core.bayesian_memory import read_json
from core.mt_bicl_bank import content_hash
from core.mt_bicl_v2_adapter import (
    A_INDEX, NAMESPACE, OUTPUT as INTEGRATION, PILOT_PLAN, TRAINING, TRAINING_MANIFEST,
    load_inputs as load_integration_inputs,
)
from core.mt_bicl_v2_decision import COMMON_INSTRUCTION
from core.mt_bicl_v2_final_evaluation import REPORT_VERSION
from core.mt_bicl_v2_integration import DRY_VERSION, PROBE_VERSION, verify as verify_integration
from core.mt_bicl_v2_io import ActiveBudget, read_envelope, write_envelope
from core.mt_bicl_v2_pilot import FROZEN_TEACHER
from core.mt_bicl_v2_preparation import BUDGET_PAYLOAD_SHA256, PROTOCOL_SHA256 as BASE_PROTOCOL_SHA256
from core.mt_bicl_v21_preparation import OUTPUT as TEACHER, file_hash
from core.prior_run_lock import safe_path

RELEASE_PATH = Path("docs/plan/week10/development_release_v2.json")
RELEASE_VERSION = "mt_bicl_development_release_v2"
CODE = ("core/mt_bicl_v2_release.py","scripts/release_mt_bicl_v2.py")
INTEGRATION_MANIFEST = "8c8db514ef640da65042c7489610b5b130f30f121e7f954535a70e8a84cea950"
LEDGER = "outputs/oos_pilot/api_usage.json"
ACCEPTED_INTEGRATION_COMMIT = "8211f18"
SOURCE_DIRECTORIES = ("agents","core","data_manager","scripts","tests","utils")
PACKAGES = ("torch","numpy","pandas","scikit-learn","hmmlearn","scipy","TA-Lib","langgraph",
            "langchain-core","langchain-groq","groq","httpx","pydantic","jsonschema","Pillow","matplotlib")
SPECS = ("protocol_v1.json","simulator_v1.json","protocol_fixtures_v1.json","protocol_v2.json",
         "protocol_v2_1.json","corpus_manifest_v2.json","protocol_fixtures_v2.json",
         "training_membership_v2.json","budget_v2.json","resource_inventory.json","gpu_benchmark.json")
LEDGER_BASELINE_COUNT = 3974
LEDGER_BASELINE_SHA256 = "e73a87e2a45d73e76f63cdd58225c2de06b0df4e03ed09b91ad0f6f71c5c8796"
LEDGER_REQUESTS_SHA256 = "b2a07e8126e55cabd6d1dfdd214762feb3eacbef23df3b7657c0a30427084206"
AUTHORIZATION = {"development_allowed":True,"decision_calls_allowed":True,"confirmation_allowed":False,
    "training_allowed":False,"refit_allowed":False,"scope":"W11_2023_ONLY_AFTER_RUN_MANIFEST_AND_API_PREFLIGHT",
    "requires_W11_01_run_manifest":True,"api_or_development_started_by_release_task":False}


def tree_manifest(root:Path,relative:str|Path) -> dict[str,dict[str,Any]]:
    """Băm tên/byte/hash toàn cây, từ chối symlink hoặc file resolve thoát namespace."""
    base = safe_path(root,Path(relative).as_posix())
    result = {}
    for path in sorted(base.rglob("*")):
        if path.is_symlink():raise ValueError("Không freeze symlink: "+str(path))
        if path.is_file():
            name = path.relative_to(base).as_posix()
            if safe_path(base,name) != path.resolve():raise ValueError("Artifact thoát namespace")
            result[name] = {"bytes":path.stat().st_size,"sha256":file_hash(path)}
    return result


def manifest_hash(manifest:dict[str,Any]) -> str:
    """Giữ đúng chuẩn manifest byte đã dùng khi nghiệm thu W10-12/13."""
    return hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(",",":")).encode()).hexdigest()


def runtime_identity() -> dict[str,Any]:
    """Chỉ đọc phiên bản package/OS; không khởi tạo CUDA, client hoặc credential."""
    packages = {}
    for name in PACKAGES:
        try:packages[name] = version(name)
        except PackageNotFoundError as error:raise ValueError("Thiếu dependency đã dùng: "+name) from error
    return {"python":platform.python_version(),"platform":platform.system(),"os_name":os.name,"packages":packages}


def git_value(root:Path,*args:str) -> str:
    """Đọc lịch sử Git, không gọi shell hoặc sửa index/worktree."""
    result = subprocess.run(["git",*args],cwd=root,capture_output=True,text=True,encoding="utf-8",check=False)
    if result.returncode:raise ValueError("Không đối soát được commit Git đã khóa")
    return result.stdout.strip()


def source_paths(root:Path,commit:str) -> list[str]:
    """Đóng tập source/test tại commit; file W11 thêm sau không tự vào freeze cũ."""
    if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):raise ValueError("Commit freeze không đúng SHA40")
    paths = git_value(root,"ls-tree","-r","--name-only",commit,"--",*SOURCE_DIRECTORIES).splitlines()
    names = [name for name in paths if name.endswith(".py")]
    for name in (".python-version","requirements.txt"):
        git_value(root,"cat-file","-e",commit+":"+name)
        names.append(name)
    if not set(CODE).issubset(names):raise ValueError("Phải commit mã release trước freeze production")
    diff = subprocess.run(["git","diff","--quiet",commit,"--",*names],cwd=root,capture_output=True,check=False)
    if diff.returncode:raise ValueError("Source/test/config khác commit freeze, không reseal")
    return sorted(names)


def ledger_baseline(root:Path) -> dict[str,Any]:
    """Chụp từng request trước release; ledger sống được append, không khóa nguyên byte vĩnh viễn."""
    rows = read_json(safe_path(root,LEDGER))["requests"]
    if len({r["id"] for r in rows}) != len(rows):raise ValueError("Ledger trùng UUID")
    result = {"path":LEDGER,"baseline_count":len(rows),"baseline_file_sha256":file_hash(root/LEDGER),
            "request_sha256_by_id":{r["id"]:content_hash(r) for r in rows},
            "lifecycle":"APPEND_ONLY_PRESERVE_PRE_RELEASE_REQUESTS_NEW_RUN_BINDS_OWN_REQUESTS"}
    if (len(rows) != LEDGER_BASELINE_COUNT or result["baseline_file_sha256"] != LEDGER_BASELINE_SHA256
            or content_hash(result["request_sha256_by_id"]) != LEDGER_REQUESTS_SHA256):
        raise ValueError("Ledger đã khác mốc trước release; không cấp release sau response mới")
    return result


def verify_ledger(root:Path,baseline:dict[str,Any]) -> None:
    """Cho append hợp lệ sau release; sửa/mất request nền hoặc UUID trùng đều dừng."""
    if (baseline["path"] != LEDGER or baseline["baseline_count"] != LEDGER_BASELINE_COUNT
            or baseline["baseline_count"] != len(baseline["request_sha256_by_id"])
            or baseline["baseline_file_sha256"] != LEDGER_BASELINE_SHA256
            or content_hash(baseline["request_sha256_by_id"]) != LEDGER_REQUESTS_SHA256):
        raise ValueError("Baseline ledger không đúng schema/count")
    rows = read_json(safe_path(root,LEDGER))["requests"]
    actual = {r["id"]:content_hash(r) for r in rows}
    if len(actual) != len(rows) or any(actual.get(k) != v for k,v in baseline["request_sha256_by_id"].items()):
        raise ValueError("Request trước release bị sửa/mất hoặc UUID ledger trùng")


def check_gates(inputs:dict[str,Any],dry:dict[str,Any],probes:dict[str,Any],
                proof:dict[str,Any],report:dict[str,Any]) -> None:
    """Gate đúng protocol tổng hợp, không thêm ngưỡng thị trường hoặc hạ gate stress."""
    if (report["candidate_mechanism_status"] != "PASS" or report["technical_status"] != "PASS"
            or report["candidate_locked_before_test"] != inputs["selection"]["global_candidate_or_none"]
            or proof["status"] != "OFFLINE_INTEGRATION_REPLAY_MATCH" or proof["identity"] != inputs["identity"]
            or any(v["status"] != "PASS" or v["identity"] != inputs["identity"] or v["real_api_calls"] != 0
                   for v in (dry,probes)) or len(dry["points"]) != 60 or len(probes["probes"]) != 24
            or len(proof["journals_sha256"]) != 120 or dry["max_prefix_chars"] > 600 or dry["max_prompt_chars"] >= 6500):
        raise ValueError("Gate kỹ thuật/cơ chế/tích hợp chưa PASS, không release")
    support = dry["support"]
    gate = inputs["protocol"]["development"]["support_gate"]
    if (support["gate"] != "PASS" or support["simultaneous"] < gate["simultaneous_points_min"]
            or any(support["by_symbol"].get(s,0) < gate["simultaneous_each_symbol_min"] for s in inputs["protocol"]["decision"]["symbol_order"])):
        raise ValueError("INSUFFICIENT_CONTEXT_NO_API")
    if probes["llm_semantic_behavior"] != "NOT_RUN_BEFORE_RELEASE":raise ValueError("Không đổi probe offline thành hành vi LLM thật")


def collect_inputs(root:Path) -> dict[str,Any]:
    """Cold-check toàn dependency và receipt gốc; không đọc nhãn2025 hoặc chạy lại inference."""
    inputs = load_integration_inputs(root)
    trees = {}
    for path,expected,count in ((TRAINING,TRAINING_MANIFEST,131),(INTEGRATION,INTEGRATION_MANIFEST,123)):
        tree = tree_manifest(root,path)
        if len(tree) != count or manifest_hash(tree) != expected:raise ValueError("Cây bằng chứng khác nghiệm thu: "+str(path))
        trees[path.as_posix()] = tree
    teacher = tree_manifest(root,TEACHER)
    if set(teacher) != set(FROZEN_TEACHER) or any(teacher[n]["sha256"] != h for n,h in FROZEN_TEACHER.items()):
        raise ValueError("Teacher/corpus v2.1 bị sửa")
    trees[TEACHER.as_posix()] = teacher
    proof = verify_integration(root,inputs,replay=False)
    dry = read_envelope(root/INTEGRATION/"dry_run.json",DRY_VERSION)
    probes = read_envelope(root/INTEGRATION/"semantic_probes.json",PROBE_VERSION)
    report = read_envelope(root/TRAINING/"report.json",REPORT_VERSION)
    check_gates(inputs,dry,probes,proof,report)
    runtime = runtime_identity()
    return {"integration":inputs,"trees":trees,"dry":dry,"probes":probes,"proof":proof,
            "report":report,"runtime":runtime}


def budget_snapshot(root:Path,identity:dict[str,Any]) -> dict[str,Any]:
    """Không cấp quỹ mới; phát hiện reset counter, phiên chưa đóng hoặc cap/lịch trước freeze."""
    path = root/NAMESPACE/"active_budget_v2.json"
    if not path.exists():raise ValueError("Thiếu budget gốc")
    state = read_envelope(path,"mt_bicl_active_budget_v2")
    elapsed = state["elapsed_seconds"]
    durations = [r["duration_seconds"] for r in state["sessions"]]
    if (state["identity"] != identity or state["active_since"] is not None or type(elapsed) not in (int,float)
            or not math.isfinite(elapsed) or elapsed < 4940.306028200313
            or any(type(x) not in (int,float) or not math.isfinite(x) or x < 0 for x in durations)
            or elapsed+1e-9 < math.fsum(durations)):
        raise ValueError("Budget không đúng counter/identity đã nghiệm thu")
    return {"identity":deepcopy(identity),"elapsed_seconds":float(elapsed),"session_count":len(state["sessions"]),
            "sessions_sha256":content_hash(state["sessions"])}


def expected_budget_identity() -> dict[str,Any]:
    """Dùng grant gốc trước cả cold-check, không tin cap do caller hoặc state tự nâng."""
    return {"protocol_sha256":BASE_PROTOCOL_SHA256,"grant_payload_sha256":BUDGET_PAYLOAD_SHA256,
            "cap_seconds":14400,"W10_stop":"2026-11-01"}


def release_facts(root:Path,inputs:dict[str,Any]) -> dict[str,Any]:
    """Tái dựng toàn bộ quyền/gate/giới hạn từ nguồn, không tin receipt tự sửa rồi self-hash."""
    common,report = inputs["integration"],inputs["report"]
    candidate = report["candidate_locked_before_test"]
    selected = report["per_seed"][str(candidate["seed"])]
    budget = common["protocol"]["budget"]
    return {"version":RELEASE_VERSION,"status":"RELEASED_FOR_ADAPTIVE_DEVELOPMENT",
        "authorization_quote":"Hoàn thiện W10 với W10-14.","artifact_trees":inputs["trees"],"runtime":inputs["runtime"],
        "integration_identity_sha256":content_hash(common["identity"]),"candidate":deepcopy(candidate),
        "gpu_expected":deepcopy(common["pilot_gpu"]),"common_instruction":COMMON_INSTRUCTION,
        "common_instruction_sha256":content_hash(COMMON_INSTRUCTION),"decision_schema":TradeDecisionOutput.model_json_schema(),
        "decision":deepcopy(common["protocol"]["decision"]),
        "development":{**deepcopy(common["protocol"]["development"]),"point_ids":list(common["identity"]["point_ids"])},
        "authorization":deepcopy(AUTHORIZATION),
        "gate_evidence":{"mechanism":"PASS","integration":"PASS","support":deepcopy(inputs["dry"]["support"]),
            "training_proof_sha256":file_hash(root/TRAINING/"replay_verification.json"),
            "integration_proof_sha256":file_hash(root/INTEGRATION/"verification.json"),
            "inference_replayed_again":False,"llm_semantic_behavior":"NOT_RUN_BEFORE_RELEASE"},
        "deadlines":{k:deepcopy(budget[k]) for k in ("window","W10_stop","confirmation_release_and_start_by","data_stop")},
        "limitations":{"market_year":2022,"market_exposed":True,"student_market_comparisons":deepcopy(report["candidate_market_comparisons"]),
            "stress_subgroup":deepcopy(selected["synthetic"]["full"]["by_distribution"]["stress"]),
            "teacher_PPC_overdispersed":True,"mechanism_is_not_profit_proof":True,"hosted_LLM_future_knowledge_limit":True},
        "git_anchor_required_before_consumer":True}


def freeze(root:Path) -> dict[str,Any]:
    """Tạo receipt immutable sau gate và source commit; chỉ cấp phạm vi W11 development2023."""
    path = root/RELEASE_PATH
    if path.exists():return verify_release(root,require_anchor=False)
    commit = git_value(root,"rev-parse","HEAD")
    names = source_paths(root,commit)
    git_value(root,"merge-base","--is-ancestor",ACCEPTED_INTEGRATION_COMMIT,commit)
    identity = expected_budget_identity()
    previous = budget_snapshot(root,identity)
    with ActiveBudget(root/NAMESPACE/"active_budget_v2.json",identity) as budget:
        inputs = collect_inputs(root)
        common = inputs["integration"]
        if common["budget_identity"] != identity:raise ValueError("Grant nguồn khác ngân sách đã mở")
        budget.check()
        frozen = {name:{"bytes":safe_path(root,name).stat().st_size,"sha256":file_hash(safe_path(root,name))} for name in names}
        # Các spec JSON là snapshot bất biến; không đổi cờ false trong receipt lịch sử.
        for name in SPECS:
            relative = "docs/plan/week10/"+name
            file = safe_path(root,relative)
            frozen[relative] = {"bytes":file.stat().st_size,"sha256":file_hash(file)}
        for relative in (PILOT_PLAN,A_INDEX["path"]):
            file = safe_path(root,relative);frozen[relative] = {"bytes":file.stat().st_size,"sha256":file_hash(file)}
        result = {**release_facts(root,inputs),"released_at":datetime.now(timezone.utc).isoformat(),
            "source_commit":commit,"source_files":frozen,"ledger":ledger_baseline(root),
            "budget_before_freeze":previous,"budget_seconds_at_freeze":budget.used()}
        budget.check()
        write_envelope(path,RELEASE_VERSION,result,immutable=True)
    return result


def verify_release(root:Path,*,require_anchor:bool=True) -> dict[str,Any]:
    """Tiến trình mới kiểm release từ disk/Git; read-only, không CUDA/API hoặc tính lại optimizer."""
    path = root/RELEASE_PATH
    release = read_envelope(path,RELEASE_VERSION)
    if require_anchor:
        anchored = subprocess.run(["git","show","HEAD:"+RELEASE_PATH.as_posix()],cwd=root,capture_output=True,check=False)
        if anchored.returncode or anchored.stdout != path.read_bytes():raise ValueError("Release chưa neo byte trong Git HEAD hoặc bị self-reseal")
    if release["version"] != RELEASE_VERSION or release["status"] != "RELEASED_FOR_ADAPTIVE_DEVELOPMENT":raise ValueError("Chưa có release development hợp lệ")
    if release["authorization"] != AUTHORIZATION:raise ValueError("Cờ/scope release bị sửa hoặc mở xác nhận sớm")
    names = source_paths(root,release["source_commit"])
    expected_names = {*names,*("docs/plan/week10/"+n for n in SPECS),PILOT_PLAN,A_INDEX["path"]}
    if expected_names != set(release["source_files"]):raise ValueError("Release bỏ sót/thêm source/spec so với recipe freeze")
    for name,expected in release["source_files"].items():
        file = safe_path(root,name)
        if file.stat().st_size != expected["bytes"] or file_hash(file) != expected["sha256"]:raise ValueError("Source/spec đã freeze bị sửa: "+name)
    for name,expected in release["artifact_trees"].items():
        if tree_manifest(root,name) != expected:raise ValueError("Artifact đã freeze bị sửa: "+name)
    inputs = collect_inputs(root)
    common = inputs["integration"]
    facts = release_facts(root,inputs)
    operational = {"source_commit","source_files","released_at","ledger","budget_before_freeze","budget_seconds_at_freeze"}
    if set(release) != set(facts)|operational or any(release[k] != v for k,v in facts.items()):
        raise ValueError("Release khác runtime/protocol/candidate/prompt/schema/cohort đã khóa")
    git_value(root,"merge-base","--is-ancestor",ACCEPTED_INTEGRATION_COMMIT,release["source_commit"])
    released = datetime.fromisoformat(release["released_at"])
    deadline = datetime.fromisoformat(facts["deadlines"]["W10_stop"]+"T23:59:59+07:00")
    start = datetime.fromisoformat(facts["deadlines"]["window"][0]+"T00:00:00+07:00")
    if released.tzinfo is None or not start <= released <= deadline or released > datetime.now(timezone.utc):raise ValueError("Ngày release ngoài hạn/đi trước đồng hồ")
    verify_ledger(root,release["ledger"])
    current = budget_snapshot(root,common["budget_identity"])
    before = release["budget_before_freeze"]
    used = release["budget_seconds_at_freeze"]
    if (before["identity"] != common["budget_identity"] or type(used) not in (int,float) or not math.isfinite(used)
            or not 4940.306028200313 <= before["elapsed_seconds"] <= used < common["budget_identity"]["cap_seconds"]
            or current["elapsed_seconds"]+1e-9 < used):raise ValueError("Counter budget thấp hơn release/khác cap, không reset")
    state = read_envelope(root/NAMESPACE/"active_budget_v2.json","mt_bicl_active_budget_v2")
    count = before["session_count"]
    if (type(count) is not int or not 0 <= count <= len(state["sessions"])
            or content_hash(state["sessions"][:count]) != before["sessions_sha256"]):raise ValueError("Phiên budget nền bị sửa/mất")
    # Verify vẫn được dùng sau hạn/cap: chỉ freeze mới/optimization mới chịu gate thời gian.
    return release


def require_development_release(root:Path,*,phase:str="development",point_id:str|None=None) -> dict[str,Any]:
    """Biên cho W11: vẫn phải có run manifest/preflight riêng trước API; cấm xác nhận2025/refit."""
    if phase != "development":raise ValueError("Release này chỉ dành development2023; xác nhận/refit cần gate riêng")
    release = verify_release(root)
    if point_id is not None and point_id not in release["development"]["point_ids"]:raise ValueError("Point ngoài cohort2023 đã đăng ký")
    return deepcopy(release)
