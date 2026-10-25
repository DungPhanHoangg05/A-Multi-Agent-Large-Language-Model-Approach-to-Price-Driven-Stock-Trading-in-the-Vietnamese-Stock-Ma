"""Diagnostics tái dựng và receipt hồi quy U-BICL, tách khỏi quyền chạy API."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
import subprocess
import sys
from time import monotonic
from typing import Any, Callable
from uuid import uuid4

from core.bayesian_memory import iso_date
from core.bayesian_retriever import normalize_signals
from core.candidate_selection import read_technical_gates
from core.historical_signals import digest
from core.prior_run_lock import safe_path, utc_now
from core.research_cohort import read_envelope, save_envelope
from core.research_input_lock import _write_once, runtime_identity
from core.unified_bayes_contracts import ROOT, SYMBOLS, code_identity, sha
from core.unified_bayes_decision import LLM_BRANCHES, shared_off_allowed
from core.unified_bayes_prompt import BRANCHES, assemble_prompt, check_budget, render_context
from core.unified_bayes_source import BoundCohort, readiness

VERSION = "unified_bic_validation_diagnostics_v1"
AUDIT_VERSION = "unified_bic_validation_audit_v1"
COMMANDS = {
    "compileall": ["-m", "compileall", "agents", "core", "data_manager", "scripts", "tests", "utils"],
    "unit": ["-m", "unittest", "discover", "-s", "tests", "-v"],
    "e2e": ["scripts/run_end_to_end_test.py"],
    "leakage": ["-m", "unittest", "discover", "-s", "tests", "-p", "test_*leakage.py", "-v"],
}


def validation_identity() -> dict[str, str]:
    """Ghim LF code/test/fixture/schema cùng cấu hình; không sửa map execution đã khóa."""
    paths = set(ROOT.glob("*.py"))
    for folder in ("agents", "core", "data_manager", "scripts", "tests", "utils", "docs/plan"):
        paths.update(path for path in (ROOT / folder).rglob("*")
                     if path.is_file() and path.suffix in (".py", ".json") and "__pycache__" not in path.parts)
    paths.update(ROOT / name for name in ("requirements.txt", ".python-version"))
    import hashlib
    return {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_text("utf-8").encode()).hexdigest()
            for path in sorted(paths)}


def _members(ids: list[str], metadata: dict[str, Any], query: dict[str, Any], *, recent: bool = False) -> None:
    """Mọi ID dùng làm evidence phải cùng mã, cycle đã đóng và khác query."""
    if type(ids) is not list or len(ids) != len(set(ids)):
        raise ValueError("Membership trùng hoặc sai kiểu")
    cutoff = query["as_of_date"]
    for key in ids:
        row = metadata.get(key)
        if (row is None or row["symbol"] != query["symbol"] or row["exit_date"] >= cutoff
                or row["as_of_date"] >= cutoff or key == f"{query['symbol']}:{cutoff}"):
            raise ValueError("Diagnostics phát hiện future/self/cycle chưa đóng hoặc sai mã")
        if recent and ((date.fromisoformat(cutoff) - date.fromisoformat(row["as_of_date"])).days > 730
                       or row["regime"] != query["current_regime"]):
            raise ValueError("Examples/task chứa cycle quá tuổi hoặc sai regime")


def diagnostics(cohort: BoundCohort, plan: dict[str, Any], llm: Any, memory: dict[str, Any]) -> dict[str, Any]:
    """Tái dựng nguồn trước khi đếm; chỉ chiếu metadata memory, không đánh giá query."""
    if digest(plan) != digest(cohort.plan(llm)):
        raise ValueError("Diagnostics khác plan/source/request đã tái dựng")
    memory_sha = digest(memory)
    rows = memory["metadata"]
    metadata = {row["episode_id"]: row for row in rows}
    keys = {"episode_id", "symbol", "as_of_date", "entry_date", "exit_date", "regime", "agent_signals", "cutoff_session_index"}
    if len(metadata) != len(rows) or any(set(row) != keys for row in rows):
        raise ValueError("Metadata memory trùng hoặc chứa trường ngoài whitelist")
    for row in rows:
        if (row["symbol"] not in SYMBOLS or row["episode_id"] != f"{row['symbol']}:{row['as_of_date']}"
                or not iso_date(row["as_of_date"]) < iso_date(row["entry_date"]) <= iso_date(row["exit_date"])):
            raise ValueError("Metadata memory sai mã/ngày/identity")
    result = []
    for pid, request in plan["requests"].items():
        base, packets = request["u_evidence"], request["packets"]
        query = base["query"]
        if base["memory_sha256"] != memory_sha:
            raise ValueError("Metadata không thuộc memory đã khóa của request")
        # Partition độc lập từ metadata, không đọc outcome để chọn thành viên.
        groups: dict[str, list[str]] = {name: [] for name in ("C", "B1", "B2")}
        for key, row in metadata.items():
            if row["symbol"] != query["symbol"] or row["exit_date"] >= query["as_of_date"] or row["as_of_date"] >= query["as_of_date"]:
                continue
            signals = normalize_signals(row["agent_signals"])
            group = "B2" if row["regime"] != query["current_regime"] else (
                "C" if all(signals[k] == query["current_signals"][k] for k in ("trend", "pattern")) else "B1")
            groups[group].append(key)
        for name, ids in groups.items():
            actual = base["statistics"]["groups"][name]
            _members(actual["episode_ids"], metadata, query)
            if sorted(ids) != sorted(actual["episode_ids"]) or actual["n"] != len(ids):
                raise ValueError("Partition/count diagnostics khác metadata PIT")
        selection = base["selection"]
        _members(selection["selected_ids"], metadata, query, recent=True)
        _members(selection["qualified_ids"], metadata, query, recent=True)
        for item in selection["trace"]:
            _members([item["episode_id"]], metadata, query)
            row = metadata[item["episode_id"]]
            age = (date.fromisoformat(query["as_of_date"]) - date.fromisoformat(row["as_of_date"])).days
            if item["age_days"] != age or item["cutoff_session"] != row["cutoff_session_index"]:
                raise ValueError("Trace tuổi/phiên khác metadata nguồn")
        for task_id, task in base["task_groups"].items():
            _members(task["episode_ids"], metadata, query, recent=True)
            if task["n"] != len(task["episode_ids"]) or any(
                    task_id != f"{query['symbol']}|{query['current_regime']}|b{metadata[key]['cutoff_session_index'] // 90:04d}"
                    for key in task["episode_ids"]):
                raise ValueError("Task membership/support khác block 90 phiên nguồn")
        branches = {}
        original = packets["Original"]
        for name in LLM_BRANCHES:
            packet = packets[name]
            check_budget(packet["prefix"], packet["prompt"])
            # Bundle upstream và state Full phục hồi có miền hash riêng; loader đã kiểm bundle.
            if (packet["shared_sha256"] != cohort.prepared[pid].shared_sha256
                    or packet["base_evidence_sha256"] != base["base_evidence_sha256"]
                    or packet["prompt"] != assemble_prompt(original["prompt"], packet["prefix"])):
                raise ValueError("Nhánh khác Full/base/instruction dùng chung")
            body = deepcopy(packet["body"])
            body["messages"] = deepcopy(original["body"]["messages"])
            if digest(body) != digest(original["body"]):
                raise ValueError("Model/options/schema khác giữa các nhánh")
            if name in BRANCHES:
                view = render_context(base, name)
                if packet["prefix"] != view["prefix"] or digest(packet["visible_aliases"]) != digest(view["aliases"]):
                    raise ValueError("Prefix/alias khác projection đã khóa")
            if name in ("Original", "A_reference", "U_stats") and packet["visible_aliases"]:
                raise ValueError("Nhánh không có examples vẫn chứa alias")
            branches[name] = {"prior_visible": bool(packet["prefix"]), "prefix_chars": len(packet["prefix"]),
                "prompt_chars": len(packet["prompt"]), "alias_count": len(packet["visible_aliases"]),
                "canonical_off_eligible": name != "Original" and shared_off_allowed(prior_visible=bool(packet["prefix"]),
                    same_identity=digest(packet["body"]) == digest(original["body"]), same_point_repeat=True,
                    original_durable=True, duplicate=False)}
        result.append({"point_id": pid, "symbol": query["symbol"], "as_of_date": query["as_of_date"],
            "regime": query["current_regime"], "readiness": readiness(request), "context_mode": base["context_mode"],
            "stats_reasons": list(base["posterior"]["gate"]["reason_codes"]),
            "examples_reasons": list(selection["gate"]["reason_codes"]),
            "feature_reasons": list(base["query_transform"]["feature_reasons"]),
            "partition_counts": {name: len(ids) for name, ids in groups.items()},
            "selected_count": len(selection["selected_ids"]),
            "selected_task_count": len({row["task_id"] for row in base["examples"]}) if base["context_mode"] == "task" else 0,
            "supported_task_count": sum(int(task["n"] >= 2) for task in base["task_groups"].values()),
            "selection_exclusions": deepcopy(selection["exclusion_counts"]), "branches": branches})
    def summarize(items: list[dict[str, Any]]) -> dict[str, Any]:
        """Coverage mô tả, không làm gate MDE hoặc chọn mẫu theo outcome."""
        return {"point_count": len(items), "context_modes": dict(sorted(Counter(r["context_mode"] for r in items).items())),
            "readiness": dict(sorted(Counter(r["readiness"] for r in items).items())),
            "at_least_two_selected_tasks": sum(int(r["selected_task_count"] >= 2) for r in items),
            "stats_reasons": dict(sorted(Counter(reason for r in items for reason in r["stats_reasons"]).items())),
            "examples_reasons": dict(sorted(Counter(reason for r in items for reason in r["examples_reasons"]).items())),
            "feature_reasons": dict(sorted(Counter(reason for r in items for reason in r["feature_reasons"]).items())),
            "branches": {name: {"visible_count": sum(int(r["branches"][name]["prior_visible"]) for r in items),
                "canonical_off_count": sum(int(r["branches"][name]["canonical_off_eligible"]) for r in items),
                "max_prefix_chars": max((r["branches"][name]["prefix_chars"] for r in items), default=0),
                "max_prompt_chars": max((r["branches"][name]["prompt_chars"] for r in items), default=0)} for name in LLM_BRANCHES}}
    cohort.verify(llm)
    return {"diagnostics_version": VERSION, "plan_sha256": digest(plan), "memory_sha256": memory_sha,
        "execution_code_sha256": plan["code_sha256"], "validation_code_sha256": validation_identity(),
        "runtime": runtime_identity(), "source_files": deepcopy(plan["sources"]),
        "checks": {name: "PASS" for name in ("source_request", "partition_pit", "examples_pit", "paired_prompt", "prefix_budget", "aliases")},
        "overall": summarize(result), "by_symbol": {s: summarize([r for r in result if r["symbol"] == s]) for s in SYMBOLS},
        "points": result, "query_evaluations": 0, "http_attempts": 0,
        "readiness_stage": "PENDING_U10_09", "confirmation_allowed": False, "nomination_allowed": False}


def read_diagnostics(path: Path, expected: dict[str, Any]) -> dict[str, Any]:
    """Consumer yêu cầu bản dựng lại; tự reseal không hợp thức hóa diagnostics sửa tay."""
    saved = read_envelope(path)
    if digest(saved) != digest(expected):
        raise ValueError("Diagnostics khác nguồn/plan/code hiện tại")
    return saved


def _guard(plan: dict[str, Any], identity: dict[str, str]) -> None:
    """Chặn trộn code/runtime/source trong và sau bốn gate."""
    if code_identity() != plan["code_sha256"] or runtime_identity() != plan["runtime"] or validation_identity() != identity:
        raise ValueError("Code/test/fixture/runtime đã đổi trong đợt hồi quy")
    for name, checksum in plan["sources"].items():
        if sha(safe_path(ROOT, name)) != checksum:
            raise ValueError(f"Nguồn đổi trong đợt hồi quy: {name}")


def run_gates(plan: dict[str, Any], expected: dict[str, Any], output: Path,
              *, notify: Callable[[str], None] = print) -> Path:
    """Thực chạy bốn lệnh cố định vào thư mục mới; lỗi không tạo receipt PASS."""
    identity = validation_identity()
    if (expected["plan_sha256"] != digest(plan) or expected["validation_code_sha256"] != identity
            or expected["runtime"] != runtime_identity()):
        raise ValueError("Diagnostics chưa bind code/runtime/plan hiện tại")
    _guard(plan, identity)
    root = output / (datetime.now().strftime("%Y%m%dT%H%M%S") + "_" + uuid4().hex)
    root.mkdir(parents=True, exist_ok=False)
    diagnostic_path = root / "diagnostics.json"
    _write_once(diagnostic_path, expected)
    started, runs, checks = utc_now(), {}, {}
    for name, command in COMMANDS.items():
        _guard(plan, identity)
        notify(f"Bắt đầu gate {name}; log: {root / (name + '.log')}")
        tick = monotonic()
        with (root / (name + ".log")).open("wb") as stream:
            # Không shell, không đọc key và không sửa lệnh theo kết quả test.
            process = subprocess.run([sys.executable, "-X", "utf8", *command], cwd=ROOT,
                                     stdout=stream, stderr=subprocess.STDOUT, check=False)
        runs[name] = {"command": ["python", "-X", "utf8", *command], "elapsed_seconds": float(monotonic() - tick)}
        checks[name] = {"status": "PASS" if process.returncode == 0 else "FAIL", "exit_code": int(process.returncode),
            "log": {"path": name + ".log", "sha256": sha(root / (name + ".log"))}}
        save_envelope(root / "progress.json", {"started_at": started, "checks": checks, "runs": runs})
        _guard(plan, identity)
        if process.returncode:
            raise ValueError(f"Gate {name} FAIL; giữ nguyên log và dừng nghiệm thu")
        notify(f"Gate {name} hoàn tất, exit=0; đang kiểm nguồn/log")
    receipt = root / "technical_gates.json"
    _write_once(receipt, {"gate_version": "research_technical_gates_v1", "code_sha256": plan["code_sha256"],
        "runtime": plan["runtime"], "checks": checks})
    if read_technical_gates(receipt, plan)["status"] != "PASS":
        raise ValueError("Bốn log chưa đủ điều kiện PASS của consumer")
    _guard(plan, identity)
    audit = root / "validation_audit.json"
    _write_once(audit, {"audit_version": AUDIT_VERSION, "plan_sha256": digest(plan),
        "validation_code_sha256": identity, "runtime": runtime_identity(), "started_at": started, "completed_at": utc_now(),
        "runs": runs, "diagnostics_sha256": sha(diagnostic_path), "technical_gates_sha256": sha(receipt),
        "readiness_stage": "PENDING_U10_09", "confirmation_allowed": False})
    read_validation(audit, plan, expected)
    return audit


def read_validation(path: Path, plan: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    """Đối soát receipt execution với audit toàn code/test, log và diagnostics tái dựng."""
    audit = read_envelope(path)
    fields = {"audit_version", "plan_sha256", "validation_code_sha256", "runtime", "started_at", "completed_at",
        "runs", "diagnostics_sha256", "technical_gates_sha256", "readiness_stage", "confirmation_allowed"}
    if (set(audit) != fields or audit["audit_version"] != AUDIT_VERSION or audit["plan_sha256"] != digest(plan)
            or expected["plan_sha256"] != digest(plan) or expected["runtime"] != plan["runtime"]
            or audit["runtime"] != plan["runtime"] or audit["validation_code_sha256"] != expected["validation_code_sha256"]
            or audit["readiness_stage"] != "PENDING_U10_09" or audit["confirmation_allowed"] is not False
            or set(audit["runs"]) != set(COMMANDS)):
        raise ValueError("Audit thiếu binding hoặc khác code/plan/runtime")
    _guard(plan, audit["validation_code_sha256"])
    for name, command in COMMANDS.items():
        row = audit["runs"][name]
        if (set(row) != {"command", "elapsed_seconds"} or row["command"] != ["python", "-X", "utf8", *command]
                or type(row["elapsed_seconds"]) is not float or row["elapsed_seconds"] < 0):
            raise ValueError("Audit khác lệnh hồi quy cố định")
    if datetime.fromisoformat(audit["completed_at"]) < datetime.fromisoformat(audit["started_at"]):
        raise ValueError("Audit đảo thứ tự thời gian")
    gates, diagnostic_path = path.parent / "technical_gates.json", path.parent / "diagnostics.json"
    if (sha(gates) != audit["technical_gates_sha256"] or sha(diagnostic_path) != audit["diagnostics_sha256"]
            or read_technical_gates(gates, plan)["status"] != "PASS"):
        raise ValueError("Audit khác byte receipt/log/diagnostics hoặc gate chưa PASS")
    read_diagnostics(diagnostic_path, expected)
    return audit
