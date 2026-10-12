"""Registry, plan và Decision durable cho sáu ứng viên trên cohort hiện hữu."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import time
from typing import Any
from uuid import UUID, uuid4

from agents import decision_agent
from core.backtest_engine import PRIOR_BRANCH_MODES
from core.historical_signals import digest
from core.prior_config import copy_prior_json
from core.prior_evidence_v2 import format_evidence_prefix, normalize_evidence_config
from core.prior_prompt import CANDIDATE_PROFILES, build_prior_request
from core.prior_quality_gate import COUPLED_GATE, SPLIT_GATE
from core.prior_run_lock import safe_path, utc_now
from core.prior_stage_journal import decode_output, encode_output
from core.research_input_lock import CODE_PATHS, ECONOMIC_CONTRACT, runtime_identity, _write_once
from core.research_invocation import invocation_scope
from utils.decision_parser import parse_decision

PLAN_VERSION = "research_cohort_plan_v3"
CANDIDATES = ("C0", *CANDIDATE_PROFILES)
CODE_FILES = tuple(sorted(set((*CODE_PATHS, "core/candidate_cohort.py", "core/prior_prompt.py",
    "core/pit_price_features.py", "core/price_feature_index.py", "core/prior_price_similarity.py",
    "core/prior_example_selection.py", "core/prior_conditional_statistics.py", "core/prior_quality_gate.py"))))


def registry() -> dict[str, Any]:
    """Hồ sơ cố định đã đăng ký; không nhận override ngưỡng hoặc chọn theo outcome."""
    from core.prior_example_selection import selection_config
    from core.prior_conditional_statistics import statistics_config
    from core.pit_price_features import FEATURE_VERSION, PRICE_POLICY_VERSION
    from core.price_feature_index import INDEX_VERSION, SCALER_VERSION
    from core.prior_example_selection import RANKING_VERSION, DIVERSITY_VERSION
    from core.prior_quality_gate import THRESHOLDS
    profiles = {"C0": {"evidence": "prior_evidence_v2", "statistics": "regime_beta_binomial_v2",
        "gate": "prior_quality_gate_v1", "prefix": "compact_brpp_v2",
        "decision": "decision_legacy_v1", "content_mode": "full_prior"}}
    for name, (gate, mode, prefix, contract) in CANDIDATE_PROFILES.items():
        profiles[name] = {"evidence": "prior_evidence_v3", "statistics": "regime_beta_binomial_v2"
            if gate == COUPLED_GATE else "conditional_disjoint_beta_v1", "gate": gate,
            "prefix": prefix, "decision": contract, "content_mode": mode}
    return {"registry_version": "prior_candidates_v1", "order": list(CANDIDATES), "profiles": profiles,
        "selection": selection_config(None), "statistics": statistics_config(),
        "quality": deepcopy(THRESHOLDS), "feature_versions": {"feature": FEATURE_VERSION, "price_policy": PRICE_POLICY_VERSION,
            "index": INDEX_VERSION, "scaler": SCALER_VERSION, "ranking": RANKING_VERSION, "diversity": DIVERSITY_VERSION},
        "economic_contract": deepcopy(ECONOMIC_CONTRACT), "risk_policy": "OFF"}


def _code() -> dict[str, str]:
    """Hash text LF để identity không đổi khi Git chuyển newline trên Windows."""
    root = Path(__file__).resolve().parents[1]
    return {name: hashlib.sha256((root / name).read_text(encoding="utf-8").encode("utf-8")).hexdigest()
            for name in CODE_FILES}


def inherited_plan(path: Path, root: Path, split: str | None = None) -> tuple[dict[str, Any], dict[str, str]]:
    """Kế thừa lịch/nguồn W5, kiểm byte lịch sử; không giả lập code W5 bằng code mới."""
    from core.research_cohort import read_envelope
    from core.research_input_lock import _smoke_plan
    if path.name.startswith(".env"):
        raise ValueError("Parent plan không được trỏ vào credential")
    parent = read_envelope(path)
    if parent["plan_version"] != "research_cohort_plan_v2" or parent["split"] == "holdout_2024":
        raise ValueError("Nguồn plan phải là v2 fixture/development; chưa mở holdout")
    sources = {path.resolve().relative_to(root.resolve()).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()}
    base = deepcopy(parent)
    binding = base["inputs"].pop("input_lock", None)
    if binding is not None:
        lock_path = safe_path(root, binding["path"])
        if set(binding) != {"path", "sha256"} or hashlib.sha256(lock_path.read_bytes()).hexdigest() != binding["sha256"]:
            raise ValueError("Input lock W5 khác parent plan")
        lock = read_envelope(lock_path)
        if base != _smoke_plan(lock):
            raise ValueError("Parent khác lịch/config smoke W5 đã khóa")
        sources.update(lock["sources"])
        sources[binding["path"]] = binding["sha256"]
        if split == "development_2023":
            base["symbol_cutoffs"] = deepcopy(lock["cohorts"][split])
            base["split"] = split
        elif split is not None and split != base["split"]:
            raise ValueError("Chỉ kế thừa smoke hoặc development 2023 đã khóa")
    elif base["split"] != "fixture" or split not in (None, "fixture"):
        raise ValueError("Plan thật cần input lock W5; fixture không đổi thành dữ liệu thật")
    for name, sha in sources.items():
        if name.split("/")[-1].startswith(".env") or hashlib.sha256(safe_path(root, name).read_bytes()).hexdigest() != sha:
            raise ValueError("Nguồn/lịch parent khác byte đã khóa")
    return base, sources


def prepare_candidate_plan(parent_path: Path, destination: Path, adapter: Any, *,
                           index_path: str, split: str | None = None) -> dict[str, Any]:
    """Khóa run mới offline; kế thừa lịch, tạo/nạp index phụ, không gọi model."""
    root = adapter._files.root
    base, inherited = inherited_plan(parent_path, root, split)
    if destination.resolve() == parent_path.resolve() or not destination.resolve().is_relative_to(root.resolve()):
        raise ValueError("Plan ứng viên cần đường mới trong workspace")
    target = safe_path(root, index_path)
    if target.name.startswith(".env") or destination.name.startswith(".env"):
        raise ValueError("Plan/index ứng viên không được trỏ vào credential")
    index = adapter.load_price_feature_index(index_path) if target.exists() else adapter.build_price_feature_index(index_path)
    plan = {**base, "plan_version": PLAN_VERSION, "matrix": "research_candidates_v1",
        "cohort_id": base["cohort_id"] + "-candidates-v1", "evidence_config": normalize_evidence_config(),
        "candidate_registry": registry(), "price_index": {"path": index_path,
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(), "identity": index.identity},
        "parent": {"path": parent_path.resolve().relative_to(root.resolve()).as_posix(), "split": split,
                   "sources": inherited}, "code_sha256": _code(), "runtime": runtime_identity()}
    from core.research_cohort import validate_plan
    validate_plan(plan, adapter)
    _write_once(destination, plan)
    return plan


def validate_candidate_plan(plan: dict[str, Any], adapter: Any) -> Any:
    """Tái dựng parent/registry/fold/index trước API; không chấp nhận chỉ băm lại JSON."""
    if set(plan) != {"plan_version", "cohort_id", "split", "matrix", "symbol_cutoffs", "evidence_config", "inputs",
                     "candidate_registry", "price_index", "parent", "code_sha256", "runtime"}:
        raise ValueError("Schema plan ứng viên không hợp lệ")
    if (plan["matrix"] != "research_candidates_v1" or plan["split"] not in ("fixture", "development_2023")
            or plan["candidate_registry"] != registry() or plan["code_sha256"] != _code()
            or plan["runtime"] != runtime_identity()):
        raise ValueError("Registry/code/runtime/split ứng viên khác hợp đồng đã khóa")
    if any(adapter.prior_config[key] != value for key, value in {
            "enable_bayesian_prior": True, "mode": "bayesian_regime", "k": 3, "seed": 42, "scope": "same_symbol"}.items()):
        raise ValueError("Adapter khác K/seed/scope đã đăng ký cho ứng viên")
    parent = plan["parent"]
    if type(parent) is not dict or set(parent) != {"path", "split", "sources"}:
        raise ValueError("Binding parent plan không hợp lệ")
    base, sources = inherited_plan(safe_path(adapter._files.root, parent["path"]), adapter._files.root, parent["split"])
    if (sources != parent["sources"] or plan["inputs"] != base["inputs"]
            or plan["split"] != base["split"] or plan["symbol_cutoffs"] != base["symbol_cutoffs"]
            or plan["cohort_id"] != base["cohort_id"] + "-candidates-v1"
            or plan["evidence_config"] != normalize_evidence_config()):
        raise ValueError("Plan ứng viên khác lịch/nguồn/config parent đã khóa")
    source = plan["price_index"]
    if type(source) is not dict or set(source) != {"path", "sha256", "identity"}:
        raise ValueError("Binding index không hợp lệ")
    if Path(source["path"]).name.startswith(".env"):
        raise ValueError("Index không được trỏ vào credential")
    index = adapter.load_price_feature_index(source["path"], expected_sha256=source["sha256"])
    if index.identity != source["identity"]:
        raise ValueError("Identity index khác plan")
    for name, sha in {**sources, source["path"]: source["sha256"]}.items():
        adapter._files.pin(name, sha)
    for symbol, days in plan["symbol_cutoffs"].items():
        for day in days:
            index.scaler(symbol, day)
    return index


def candidate_slot(signature: str, point_id: str, name: str) -> dict[str, str]:
    """Slot từng nhánh phải tồn tại trước bất kỳ request của cohort."""
    return {"checkpoint_version": "candidate_decision_slot_v1", "run_signature": signature,
            "point_id": point_id, "candidate_id": name}


def _checked_response(output: dict[str, Any], request: dict[str, Any] | None, lang: str) -> dict[str, Any]:
    """Tái chuẩn hóa raw content/tool args, đối soát response và self-report đã lưu."""
    decoded = decode_output(output)
    messages = decoded.get("messages")
    if type(messages) is not list or len(messages) != 1:
        raise ValueError("Decision durable cần một raw message cuối")
    message = messages[0]
    calls = getattr(message, "tool_calls", [])
    if calls:
        if len(calls) != 1 or type(calls[0].get("args")) is not dict:
            raise ValueError("Raw tool call Decision không hợp lệ")
        raw = calls[0]["args"]
    elif request is not None and request["decision_contract_version"] == "decision_prior_use_v1":
        raw = json.loads(message.content)
    else:
        raw = None
    active = request is not None and request["decision_contract_version"] == "decision_prior_use_v1"
    normalized = json.loads(output["final_trade_decision"])
    if active:
        expected, _ = decision_agent._normalize_prior_result({"parsed": raw, "raw": message}, lang, request)
    elif normalized.get("decision_source") == "llm_structured":
        if raw is None:
            raw = json.loads(message.content)
        expected, _ = decision_agent._normalize_structured_result({"parsed": raw, "raw": message}, lang)
    else:
        expected = decision_agent._safe_parse_and_enrich(message.content, "", lang=lang)
    if json.loads(expected) != normalized or parse_decision(expected, lang=lang)["decision"] not in ("LONG", "SHORT"):
        raise ValueError("Response raw khác Decision chuẩn hóa durable")
    if request is not None:
        trace = {"trace_version": "prior_decision_trace_v1", "request": request,
                 "raw_action": normalized["decision"], "prior_use": normalized.get("prior_use")}
        if output.get("prior_decision_trace") != trace:
            raise ValueError("Trace/evidence/action khác raw Decision")
    elif "prior_decision_trace" in output:
        raise ValueError("C0 không nhận schema/trace C3")
    return normalized


def candidate_point(runner: Any, document: dict[str, Any], plan: dict[str, Any], index: Any,
                    name: str, path: Path, signature: str, *, verify_only: bool,
                    reconcile: bool = False, authorize_replay: str | None = None,
                    replay_reason: str | None = None) -> dict[str, Any] | None:
    """Một Decision dùng Full đã seal; persist raw trước evaluation, không replay complete."""
    from core.research_cohort import read_envelope, save_envelope
    point = runner.adapter.prepare(**document["context"])
    shared = point.restore_full_bundle(document["shared"]["full_bundle"])
    request = None
    if name == "C0":
        evidence = point.evidence_v2(shared, plan["evidence_config"])
        prefix = format_evidence_prefix(evidence)
    else:
        evidence = point.quality_evidence(shared, index, gate_version=COUPLED_GATE if name == "C1" else SPLIT_GATE)
        request = build_prior_request(evidence, name, runner.adapter._retriever,
            selector=runner.adapter._price_example_selectors[index.identity], query_features=point.price_features())
        prefix = request["prefix"]
    binding = {"checkpoint_version": "candidate_decision_v1", "run_signature": signature,
        "point_id": document["point_id"], "candidate_id": name,
        "shared_sha256": document["shared"]["shared_sha256"], "evidence": evidence, "request": request}
    saved = read_envelope(path)
    if saved == candidate_slot(signature, document["point_id"], name):
        saved = {**binding, "prompt": None, "attempts": []}
    elif (set(saved) != {*binding, "prompt", "attempts"}
            or any(digest(saved[k]) != digest(v) for k, v in binding.items())):
        raise ValueError("Checkpoint ứng viên khác nguồn/evidence/Full/identity")
    attempts = saved["attempts"]
    if type(attempts) is not list:
        raise ValueError("Attempt ứng viên không hợp lệ")
    ids = set()
    for position, attempt in enumerate(attempts):
        if set(attempt) != {"attempt_id", "started_at", "status", "output", "latency_seconds", "authorization"}:
            raise ValueError("Schema attempt ứng viên không hợp lệ")
        UUID(attempt["attempt_id"])
        if attempt["attempt_id"] in ids or not attempt["started_at"].endswith("Z"):
            raise ValueError("UUID/timestamp attempt ứng viên không hợp lệ")
        ids.add(attempt["attempt_id"])
        datetime.fromisoformat(attempt["started_at"])
        auth = attempt["authorization"]
        if auth is not None:
            if set(auth) != {"at", "reason"} or not auth["reason"].strip() or len(auth["reason"]) > 1000 or not auth["at"].endswith("Z"):
                raise ValueError("Audit replay ứng viên không hợp lệ")
            datetime.fromisoformat(auth["at"])
        if attempt["status"] == "complete":
            if (position != len(attempts)-1 or auth is not None or type(attempt["output"]) is not dict
                    or type(attempt["latency_seconds"]) is not float or attempt["latency_seconds"] < 0):
                raise ValueError("Complete ứng viên không được replay hoặc thiếu output")
        elif (attempt["status"] != "unknown" or attempt["output"] is not None or attempt["latency_seconds"] is not None
              or position < len(attempts)-1 and auth is None):
            raise ValueError("Unknown ứng viên không nhất quán hoặc chưa có audit")

    class Captured(Exception):
        """Ngắt tại hook trước API để dựng lại prompt offline."""
    def prepare(state: dict[str, Any]) -> tuple[dict[str, Any], str]:
        if digest(state) != digest(shared):
            raise ValueError("State ứng viên khác Full đã seal")
        point.verify_source(state)
        runner.adapter.verify_sources()
        return deepcopy(state), prefix
    def capture(state: dict[str, Any], prompt: str) -> None:
        if saved["prompt"] is not None and saved["prompt"] != prompt:
            raise ValueError("Prompt ứng viên khác checkpoint")
        saved["prompt"] = prompt
        raise Captured()
    node = decision_agent.create_final_trade_decider(runner.builder.agent_llm, _prior_preparer=prepare,
                                                   _prior_request=request, _before_invoke=capture)
    try:
        node(deepcopy(shared))
    except Captured:
        pass
    latest = attempts[-1] if attempts else None
    if latest and latest["status"] == "unknown":
        if authorize_replay == latest["attempt_id"]:
            if not reconcile or not replay_reason or not replay_reason.strip() or latest["authorization"] is not None:
                raise ValueError("Replay chỉ xác nhận unknown cuối chưa được duyệt")
            latest["authorization"] = {"at": utc_now(), "reason": replay_reason}
            save_envelope(path, saved)
        if not verify_only and not reconcile and latest["authorization"] is None:
            raise ValueError(f"Decision {name} unknown {latest['attempt_id']}; cần reconcile trước replay")
    if latest is None or latest["status"] != "complete":
        if verify_only or reconcile:
            return None
        attempt = {"attempt_id": str(uuid4()), "started_at": utc_now(), "status": "unknown",
                   "output": None, "latency_seconds": None, "authorization": None}
        attempts.append(attempt)
        save_envelope(path, saved)
        started = time.monotonic()
        with invocation_scope(f"decision_{name}") as budget:
            if budget is not None:
                budget.checkpoint_attempt_id, budget.point_id = attempt["attempt_id"], document["point_id"]
                budget.branch_id, budget.run_signature = name, signature
            output = decision_agent.create_final_trade_decider(runner.builder.agent_llm,
                _prior_preparer=prepare, _prior_request=request)(deepcopy(shared))
        encoded = encode_output(output)
        _checked_response(encoded, request, runner.config["language"])
        attempt.update(status="complete", output=encoded, latency_seconds=float(time.monotonic()-started))
        save_envelope(path, saved)
        latest = attempt
    output = latest["output"]
    if (output.get("decision_prompt") != saved["prompt"]
            or set(output) != {"messages", "final_trade_decision", "decision_prompt",
                *[k for k in decision_agent.PRIOR_STATE_FIELDS if k in shared],
                *(["prior_decision_trace"] if request is not None else [])}
            or any(digest(output[k]) != digest(shared[k]) for k in decision_agent.PRIOR_STATE_FIELDS if k in shared)):
        raise ValueError("Output durable khác prompt/Full projection")
    normalized = _checked_response(output, request, runner.config["language"])
    result = deepcopy(document)
    result["branches"][name] = {"status": "complete", "decision": {"action": normalized["decision"],
        "confidence": normalized["confidence"], "risk_reward_ratio": normalized["risk_reward_ratio"],
        "normalized_response": output["final_trade_decision"], "latency_seconds": latest["latency_seconds"]}}
    from core.prior_backtest import evaluate_point
    frame, events = runner.adapter.execution_data(document["context"]["symbol"])
    evaluation = evaluate_point(frame, events, document["context"]["as_of_date"],
        {key: result["branches"][name] for key in PRIOR_BRANCH_MODES})
    result["evaluation"]["branches"][name] = evaluation["branches"]["original"]
    return result
