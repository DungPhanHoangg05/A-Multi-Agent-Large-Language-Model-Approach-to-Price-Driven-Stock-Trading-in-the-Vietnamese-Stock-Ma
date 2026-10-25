"""Producer/loader cohort U-BICL từ upstream đã kiểm; không đọc Decision nguồn."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from core.historical_signals import digest
from core.improvement_protocol import calendar
from core.improvement_runtime import shared_point
from core.pilot_readiness import build_adapter
from core.prior_run_lock import safe_path
from core.research_cohort import read_envelope
from core.research_input_lock import _write_once, runtime_identity
from core.unified_bayes_context import UnifiedBayesContext
from core.unified_bayes_contracts import (ROOT, SYMBOLS, MATRIX, PLAN_VERSION, REQUEST_VERSION,
    code_identity, sha, validate)
from core.unified_bayes_decision import DecisionPreparer, LLM_BRANCHES, PreparedPoint
from core.unified_bayes_memory import OUTPUT as MEMORY_PATH, load_memory
from core.unified_bayes_runtime import branch_order
from scripts.prepare_unified_bayes_execution import OUTPUT as REQUEST_LOCK, SOURCE
from scripts.prepare_unified_bayes_memory import verified_inputs, PROTOCOL_SHA
from scripts.prepare_unified_bayes_pooling import load_protocol

REQUEST_SHA = "9d7ef5d43b7ebde1cd697aa1417730184600d38d815969ca92b15a4623f1abd0"
NAMESPACE = ROOT / "outputs/bayesian_benchmark/unified_bic_v1"
PLAN_PATH = NAMESPACE / "development/plan.json"
RUN_PATH = NAMESPACE / "development/run"
_VERIFIED = object()


def request_bundle(point: PreparedPoint, proof: dict[str, Any], upstream: dict[str, Any]) -> dict[str, Any]:
    """Giữ evidence/alias đầy đủ ở sidecar, không chèn thêm vào prompt."""
    return validate({"request_version": REQUEST_VERSION, "point_id": point.point_id,
        "source_proof": deepcopy(proof), "upstream": deepcopy(upstream), "u_evidence": point.base,
        "a_evidence": point.reference, "packets": {name: point.packet(name) for name in LLM_BRANCHES}}, "request")


def repeat_sample(requests: dict[str, Any]) -> list[str]:
    """Chọn đủ strata trước khi bù ngày sớm, không xem action hoặc payoff query."""
    selected = []
    for symbol in SYMBOLS:
        ids = sorted(pid for pid in requests if pid.startswith(symbol + "-"))
        picked = []
        for stratum in ("both_ready", "one_block_ready", "off"):
            available = [pid for pid in ids if readiness(requests[pid]) == stratum]
            if available:
                picked.append(available[0])
        picked += [pid for pid in ids if pid not in picked][:max(0, 3-len(picked))]
        selected += picked
    return sorted(selected, key=lambda pid: (pid[4:], SYMBOLS.index(pid[:3])))


def readiness(request: dict[str, Any]) -> str:
    """Metadata readiness tách khỏi visibility từng projection."""
    evidence = request["u_evidence"]
    count = int(evidence["posterior"]["gate"]["ready"]) + int(evidence["selection"]["gate"]["ready"])
    return ("off", "one_block_ready", "both_ready")[count]


class BoundCohort:
    """Handle nguồn đã kiểm; fixture không thể đổi nhãn thành development thật."""

    def __init__(self, prepared: list[PreparedPoint], points: dict[str, Any], upstream: dict[str, Any],
                 source_check: Callable[[], None], sources: dict[str, str], models: dict[str, Any], *,
                 split: str = "fixture", verified: object = None) -> None:
        if split != "fixture" and (split != "development_2023_exploratory" or verified is not _VERIFIED):
            raise ValueError("Cohort thật phải được loader nguồn cấp")
        self.prepared = {point.point_id: point for point in prepared}
        if not prepared or len(self.prepared) != len(prepared) or set(points) != set(self.prepared) or set(upstream) != set(points):
            raise ValueError("Cohort trùng/thiếu point hoặc nguồn upstream")
        self.points, self.upstream = points, deepcopy(upstream)
        self.source_check, self.sources, self.models, self.split = source_check, deepcopy(sources), deepcopy(models), split

    def verify(self, llm: Any) -> None:
        """Kiểm toàn nguồn và body SDK, kể cả point chưa được chọn chạy tiếp."""
        self.source_check()
        for point in self.prepared.values():
            point.verify(llm)

    def plan(self, llm: Any) -> dict[str, Any]:
        """Khóa request/schedule trước mọi action; release/readiness vẫn tách riêng."""
        self.verify(llm)
        ids = sorted(self.prepared, key=lambda pid: (pid[4:], SYMBOLS.index(pid[:3])))
        requests = {pid: request_bundle(self.prepared[pid], self.points[pid].source_provenance, self.upstream[pid]) for pid in ids}
        sample = repeat_sample(requests)
        schedule = [{"point_id": pid, "repeat_id": 0, "order": branch_order(j)} for j, pid in enumerate(ids)]
        schedule += [{"point_id": pid, "repeat_id": rid, "order": branch_order(j, rid)}
                     for rid in (1, 2, 3) for j, pid in enumerate(sample)]
        return validate({"plan_version": PLAN_VERSION, "split": self.split, "protocol_sha256": PROTOCOL_SHA,
            "request_lock_sha256": REQUEST_SHA if self.split != "fixture" else None,
            "code_sha256": code_identity(), "runtime": runtime_identity(), "sources": self.sources,
            "models": self.models, "matrix": list(MATRIX), "requests": requests, "schedule": schedule,
            "repeat_sample": sample, "confirmation_allowed": False, "risk_policy": "OFF",
            "readiness_stage": "PENDING_U10_09"}, "plan")

    def read_plan(self, path: Path, llm: Any) -> dict[str, Any]:
        """Checksum không thay semantic: dựng lại toàn source/request/schedule hiện tại."""
        saved = validate(read_envelope(path), "plan")
        if digest(saved) != digest(self.plan(llm)):
            raise ValueError("Plan khác nguồn/request/schedule/code/runtime đã tái dựng")
        return saved


def load_source(llm: Any) -> BoundCohort:
    """Cold loader development 60 point, chỉ cache W8/W9; không fresh fallback hoặc 2025."""
    from scripts.prepare_unified_bayes_execution import code_identity as lock_code
    protocol = load_protocol()
    if sha(ROOT / REQUEST_LOCK) != REQUEST_SHA:
        raise ValueError("Instruction/request lock khác bản đã nghiệm thu")
    locked = read_envelope(ROOT / REQUEST_LOCK)
    if locked["code_sha256"] != lock_code() or locked["runtime"] != runtime_identity():
        raise ValueError("Request lock khác code/runtime")
    inputs = verified_inputs()
    memory = load_memory(ROOT / MEMORY_PATH, **inputs)
    context = UnifiedBayesContext(memory, inputs["calendar"])
    parent = read_envelope(ROOT / SOURCE / "plan.json")
    identity = read_envelope(ROOT / SOURCE / "run/cohort.json")
    if digest(identity["plan"]) != digest(parent) or parent["symbol_cutoffs"] != protocol["development"]["symbol_cutoffs"]:
        raise ValueError("Nguồn development khác lịch/plan đã khóa")
    adapter = build_adapter(parent["inputs"], root=ROOT)
    models = parent["inputs"]["signal_config"]["models"]
    producer = DecisionPreparer(context, llm, models)
    expected = {row["point_id"]: row for row in locked["points"]}
    points, prepared, upstream = {}, [], {}
    files = {**locked["sources"], str(REQUEST_LOCK): REQUEST_SHA}
    # REQUEST_LOCK có thể là đường dẫn tương đối hoặc tuyệt đối trong producer cũ.
    files = {(Path(name).relative_to(ROOT).as_posix() if Path(name).is_absolute() else name): value for name, value in files.items()}
    for row in calendar(parent):
        point, shared, doc = shared_point(SimpleNamespace(adapter=adapter), row, ROOT / SOURCE / "run", digest(identity), verify_only=True)
        if shared is None:
            raise ValueError("Thiếu upstream; không được fallback fresh trong cohort")
        packet = producer.prepare(point, shared)
        if digest({name: packet.packet(name) for name in LLM_BRANCHES}) != digest(expected[row["point_id"]]["packets"]):
            raise ValueError("Request SDK khác lock U10-06")
        pid = row["point_id"]
        points[pid] = point
        prepared.append(packet)
        refs = {}
        for name in (f"points/{pid}.json", f"responses/{pid}.json"):
            path = safe_path(ROOT / SOURCE / "run", name)
            relative = path.relative_to(ROOT).as_posix()
            refs[relative] = sha(path)
        files.update(refs)
        upstream[pid] = {"files": refs, "shared_sha256": doc["shared_sha256"]}
    if len(prepared) != 60 or set(points) != set(expected):
        raise ValueError("Cohort development không đủ 60 request đã khóa")
    def verify() -> None:
        """Ràng buộc byte upstream và source, không chỉ tin dict cache trong RAM."""
        adapter.verify_sources()
        for name, checksum in files.items():
            if sha(safe_path(ROOT, name)) != checksum:
                raise ValueError(f"Nguồn cohort đổi: {name}")
    cohort = BoundCohort(prepared, points, upstream, verify, dict(sorted(files.items())), models,
                         split="development_2023_exploratory", verified=_VERIFIED)
    cohort.verify(llm)
    return cohort


def prepare_plan(cohort: BoundCohort, path: Path, llm: Any) -> dict[str, Any]:
    """Ghi một lần và luôn so digest native sau ghi, kể cả input tự reseal."""
    expected = cohort.plan(llm)
    _write_once(path, expected)
    if digest(read_envelope(path)) != digest(expected):
        raise ValueError("Plan đã có khác producer nguồn hiện tại")
    return expected
