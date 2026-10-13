"""Holdout có selection bất biến; xác minh development offline trước mọi request."""

from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
from typing import Any

from core.candidate_cohort import CANDIDATES, _code, inherited_plan, registry
from core.prior_evidence_v2 import normalize_evidence_config
from core.prior_run_lock import safe_path
from core.research_input_lock import _write_once, runtime_identity

PLAN_VERSION = "research_cohort_plan_v4"
MATRIX = "selection_bound_holdout_v1"
BINDING_KEYS = {"development_plan", "development_run", "selection", "technical_gates", "ledger"}


def _file(root: Path, proof: dict[str, str]) -> Path:
    """Kiểm byte nguồn đã khóa, chặn credential và đường vượt workspace."""
    if type(proof) is not dict or set(proof) != {"path", "sha256"}:
        raise ValueError("Binding file holdout không hợp lệ")
    path = safe_path(root, proof["path"])
    if path.name.startswith(".env") or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != proof["sha256"]:
        raise ValueError("Nguồn selection/development khác checksum đã khóa")
    return path


def selection_binding(root: Path, development_plan: Path, development_run: Path,
                      selection: Path, technical_gates: Path | None, ledger: Path) -> dict[str, Any]:
    """Khóa vị trí và byte; semantic được tái dựng riêng từ run development."""
    def relative(path: Path) -> str:
        return path.resolve().relative_to(root.resolve()).as_posix()
    def proof(path: Path) -> dict[str, str]:
        return {"path": relative(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return {"development_plan": proof(development_plan), "development_run": relative(development_run),
        "selection": proof(selection), "technical_gates": proof(technical_gates) if technical_gates else None,
        "ledger": relative(ledger)}


def _verify_development(root: Path, binding: dict[str, Any], development_runner: Any = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Dựng lại report/selection từ checkpoint, không tin report JSON tự băm lại."""
    from core.candidate_selection import read_selection
    from core.research_cohort import read_envelope
    if type(binding) is not dict or set(binding) != BINDING_KEYS:
        raise ValueError("Holdout thiếu selection binding đầy đủ")
    plan_path = _file(root, binding["development_plan"])
    selected_path = _file(root, binding["selection"])
    gates = _file(root, binding["technical_gates"]) if binding["technical_gates"] is not None else None
    plan = read_envelope(plan_path)
    if plan.get("plan_version") != "research_cohort_plan_v3" or plan.get("split") not in ("fixture", "development_2023"):
        raise ValueError("Selection chỉ kế thừa run development v3 hoặc fixture offline")
    run = safe_path(root, binding["development_run"])
    ledger = safe_path(root, binding["ledger"])
    if selected_path.parent != run:
        raise ValueError("Selection phải thuộc thư mục run development đã khóa")
    if development_runner is not None:
        if (plan["split"] != "fixture" or development_runner.mode != "offline_fixture"
                or development_runner.adapter._files.root.resolve() != root.resolve()):
            raise ValueError("Runner tiêm chỉ dành cho fixture offline cùng workspace")
        expected = development_runner.run_cohort(plan, output_dir=run, verify_only=True)
    else:
        if plan["split"] != "development_2023" or gates is None:
            raise ValueError("Holdout thật cần development và receipt bốn gate đã khóa")
        import httpx
        from core.backtest_engine import BacktestEngine
        from core.groq_pacing import GroqPacer
        from core.pilot_readiness import build_adapter
        from core.prior_backtest import PriorBacktestRunner
        from core.research_metrics import http_telemetry
        from scripts.run_bayesian_ablation import make_builder
        def reject(request: httpx.Request) -> httpx.Response:
            raise AssertionError("Verifier selection không được gọi mạng")
        adapter = build_adapter(plan["inputs"], root=root)
        config = adapter.signal_config
        engine = BacktestEngine({**config["models"], "language": config["language"],
            "alpha_norm_method": config["norm_method"], "alpha_weights": config["alpha_weights"]})
        with httpx.Client(transport=httpx.MockTransport(reject)) as client:
            runner = PriorBacktestRunner(engine, adapter, make_builder(plan["inputs"], "offline-verifier-no-network", client),
                extra_source_paths=(binding["development_plan"]["path"],),
                quota_policy="request_admission_v2", durable_stages=True)
            expected = runner.run_cohort(plan, output_dir=run, verify_only=True, ledger_path=ledger)
        state = GroqPacer(ledger, policy="request_admission_v2").state
        expected["telemetry"] = http_telemetry(state["requests"], expected["run_signatures"], state.get("invocations"))
    selection = read_selection(selected_path, run / "report.json", expected, gates_path=gates)
    if plan["split"] == "development_2023":
        if (selection["selection_evidence_status"] != "DEVELOPMENT" or selection["nomination_status"] not in ("PROMOTED", "NOT_PROMOTED")
                or selection["research_candidate"] not in CANDIDATES or selection["risk_policy"] != "OFF"):
            raise ValueError("Selection development chưa đủ điều kiện mở holdout")
    elif selection["selection_evidence_status"] != "NOT_APPLICABLE" or selection["nomination_status"] != "BLOCKED":
        raise ValueError("Fixture không được giả thành nomination thật")
    return plan, selection


def _inherit(root: Path, development: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """Lấy nguyên lịch holdout W5 qua parent/lock checksum, không tự chọn ngày."""
    from core.research_cohort import read_envelope
    parent = development["parent"]
    path = safe_path(root, parent["path"])
    base, sources = inherited_plan(path, root, parent["split"])
    if development["split"] == "fixture":
        return base, sources
    smoke = read_envelope(path)
    lock = read_envelope(_file(root, smoke["inputs"]["input_lock"]))
    base["split"] = "holdout_2024"
    base["symbol_cutoffs"] = deepcopy(lock["cohorts"]["holdout_2024"])
    if {s:len(days) for s, days in base["symbol_cutoffs"].items()} != {"FPT":16, "VNM":16, "VCB":16, "MWG":16}:
        raise ValueError("Holdout phải kế thừa đủ lịch 64 điểm W5")
    return base, sources


def _decision(development: dict[str, Any], selection: dict[str, Any]) -> dict[str, Any]:
    """Fixture dùng C3 cố định để kiểm protocol, không sinh quyết định khoa học."""
    fixture = development["split"] == "fixture"
    return {"scope": "FIXTURE_PROTOCOL_ONLY" if fixture else "DEVELOPMENT_SELECTION",
        "nomination_status": selection["nomination_status"], "research_candidate": selection["research_candidate"],
        "primary_branch": "C3" if fixture else selection["research_candidate"],
        "deployment_choice": selection["deployment_choice"], "risk_policy": "OFF"}


def prepare_holdout_plan(destination: Path, adapter: Any, binding: dict[str, Any], *,
                         development_runner: Any = None) -> dict[str, Any]:
    """Khóa plan v4 sau xác minh development; chưa tạo manifest/run holdout."""
    root = adapter._files.root
    development, selection = _verify_development(root, binding, development_runner)
    base, sources = _inherit(root, development)
    relative = destination.resolve().relative_to(root.resolve()).as_posix()
    if destination.name.startswith(".env") or relative in sources or relative in (
            binding["development_plan"]["path"], binding["selection"]["path"], development["price_index"]["path"]):
        raise ValueError("Holdout cần đường plan mới, không ghi đè nguồn đã khóa")
    plan = {**base, "plan_version": PLAN_VERSION, "matrix": MATRIX,
        "cohort_id": base["cohort_id"] + "-selection-bound-holdout-v1",
        "evidence_config": normalize_evidence_config(), "candidate_registry": registry(),
        "price_index": deepcopy(development["price_index"]), "parent": {"sources": sources},
        "selection_binding": deepcopy(binding), "selection_decision": _decision(development, selection),
        "code_sha256": _code(), "runtime": runtime_identity()}
    validate_holdout_plan(plan, adapter, development_runner=development_runner)
    _write_once(destination, plan)
    return plan


def validate_holdout_plan(plan: dict[str, Any], adapter: Any, *, development_runner: Any = None) -> Any:
    """Validator v4 riêng, tái kiểm selection trước giá holdout và trước API."""
    if set(plan) != {"plan_version", "cohort_id", "split", "matrix", "symbol_cutoffs", "evidence_config", "inputs",
            "candidate_registry", "price_index", "parent", "selection_binding", "selection_decision", "code_sha256", "runtime"}:
        raise ValueError("Schema holdout v4 không hợp lệ")
    if (plan["plan_version"] != PLAN_VERSION or plan["matrix"] != MATRIX
            or plan["candidate_registry"] != registry() or plan["code_sha256"] != _code()
            or plan["runtime"] != runtime_identity() or plan["evidence_config"] != normalize_evidence_config()):
        raise ValueError("Holdout khác version/registry/code/runtime/economic contract đã khóa")
    root = adapter._files.root
    development, selection = _verify_development(root, plan["selection_binding"], development_runner)
    base, sources = _inherit(root, development)
    if (plan["selection_decision"] != _decision(development, selection) or plan["parent"] != {"sources": sources}
            or plan["price_index"] != development["price_index"]
            or any(plan[key] != base[key] for key in ("split", "symbol_cutoffs", "inputs"))
            or plan["cohort_id"] != base["cohort_id"] + "-selection-bound-holdout-v1"):
        raise ValueError("Holdout khác selection/lịch/model/config W5 đã khóa")
    if any(adapter.prior_config[key] != value for key, value in {
            "enable_bayesian_prior": True, "mode": "bayesian_regime", "k":3, "seed":42, "scope":"same_symbol"}.items()):
        raise ValueError("Holdout khác K/seed/scope đã đăng ký")
    index = adapter.load_price_feature_index(plan["price_index"]["path"], expected_sha256=plan["price_index"]["sha256"])
    if index.identity != plan["price_index"]["identity"]:
        raise ValueError("Holdout khác identity index development")
    for name, sha in {**sources, plan["price_index"]["path"]:plan["price_index"]["sha256"]}.items():
        adapter._files.pin(name, sha)
    from core.research_cohort import validate_plan
    legacy = {key:plan[key] for key in ("cohort_id", "split", "symbol_cutoffs", "evidence_config", "inputs")}
    validate_plan({**legacy, "plan_version":"research_cohort_plan_v2", "matrix":"research_v2"}, adapter)
    for symbol, days in plan["symbol_cutoffs"].items():
        for day in days:
            index.scaler(symbol, day)
    return index


def holdout_report(plan: dict[str, Any], points: dict[str, Any], binding: dict[str, Any]) -> dict[str, Any]:
    """Giữ metric ghép cặp, công bố primary cố định; holdout không làm evidence lựa chọn."""
    from core.backtest_engine import PRIOR_BRANCH_MODES
    from core.paired_candidate_report import _paired_candidate_report
    if plan["plan_version"] != PLAN_VERSION or plan["matrix"] != MATRIX:
        raise ValueError("Report holdout cần protocol v4")
    result = _paired_candidate_report(plan, points, binding, splits=("fixture", "holdout_2024"))
    primary = plan["selection_decision"]["primary_branch"]
    if primary not in CANDIDATES:
        raise ValueError("Holdout thiếu primary được khóa")
    result.update(report_version="research_report_v6", selection_binding=deepcopy(plan["selection_binding"]),
        selection_decision=deepcopy(plan["selection_decision"]), research_primary=primary,
        selection_evidence_status="HOLDOUT_NOT_FOR_SELECTION" if plan["split"] == "holdout_2024" else "NOT_APPLICABLE",
        branch_roles={name:"RESEARCH_PRIMARY" if name == primary else "CONTROL" if name in PRIOR_BRANCH_MODES
            else "ABLATION" if name.endswith("_only") else "SECONDARY_CANDIDATE" for name in result["matrix"]})
    result["limitations"].append("Primary kế thừa development; không chọn lại, promote hoặc chỉnh ngưỡng theo holdout.")
    return result
