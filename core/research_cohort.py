"""Plan bốn mã và checkpoint v2 trên cùng runner, tái dùng Full v1 đã xác minh."""

from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import time
from typing import Any
from uuid import uuid4, UUID

import pandas as pd

from agents.decision_agent import create_final_trade_decider
from core.backtest_engine import PRIOR_BRANCH_MODES
from core.bayesian_memory import atomic_write_json, read_json, SYMBOLS
from core.execution_prices import execution_prices_for_cycle
from core.prior_backtest import canonical_hash, evaluate_point, ROOT
from core.prior_checkpoint import read_document, PriorCheckpointStore
from core.prior_config import copy_prior_json
from core.prior_evidence_v2 import normalize_evidence_config, format_evidence_prefix, VERSIONS
from core.prior_run_lock import PriorRunLock, safe_path, utc_now
from core.research_invocation import ENABLED, invocation_scope
from core.research_metrics import research_report
from utils.decision_parser import parse_decision


def read_envelope(path: Path) -> dict[str, Any]:
    """Đọc JSON native hữu hạn và hash, không chấp nhận artifact legacy."""
    envelope = copy_prior_json(read_json(path))
    if set(envelope) != {"payload", "sha256"} or canonical_hash(envelope["payload"]) != envelope["sha256"]:
        raise ValueError("Envelope nghiên cứu không hợp lệ")
    return envelope["payload"]


def save_envelope(path: Path, payload: dict[str, Any]) -> None:
    """Checkpoint atomic dùng primitive I/O có retry hữu hạn đã kiểm."""
    atomic_write_json(path, {"payload": payload, "sha256": canonical_hash(payload)})


def validate_plan(plan: dict[str, Any], adapter: Any) -> Any:
    """Schema plan mới; kiểm lịch/entry/exit trước API, không đưa nhãn vào query."""
    copy_prior_json(plan)
    if plan.get("plan_version") == "research_cohort_plan_v3":
        from core.candidate_cohort import validate_candidate_plan
        index = validate_candidate_plan(plan, adapter)
        base = {key: plan[key] for key in ("cohort_id", "split", "symbol_cutoffs", "evidence_config", "inputs")}
        validate_plan({**base, "plan_version": "research_cohort_plan_v2", "matrix": "research_v2"}, adapter)
        return index
    if set(plan) != {"plan_version", "cohort_id", "split", "matrix", "symbol_cutoffs", "evidence_config", "inputs"}:
        raise ValueError("Schema plan cohort không hợp lệ")
    if (plan["plan_version"] != "research_cohort_plan_v2" or plan["matrix"] not in ("smoke_v1", "research_v2")
            or plan["split"] not in ("fixture", "development_2023", "holdout_2024")
            or type(plan["cohort_id"]) is not str or not plan["cohort_id"].strip()
            or set(plan["symbol_cutoffs"]) != SYMBOLS):
        raise ValueError("Plan phải khóa bốn mã, cohort/split/matrix có version")
    if normalize_evidence_config(plan["evidence_config"]) != plan["evidence_config"]:
        raise ValueError("Plan phải ghi đầy đủ config evidence")
    if plan["inputs"]["signal_config"] != adapter.signal_config:
        raise ValueError("Input adapter khác config trong plan")
    if "input_lock" in plan["inputs"]:
        from core.research_input_lock import validate_bound_plan
        validate_bound_plan(plan, adapter._files.root)
    for symbol, cutoffs in plan["symbol_cutoffs"].items():
        if type(cutoffs) is not list or not cutoffs or len(set(cutoffs)) != len(cutoffs):
            raise ValueError("Cutoff plan thiếu hoặc trùng")
        frame, events = adapter.execution_data(symbol)
        dates = pd.DatetimeIndex(frame.Datetime)
        positions = dates.get_indexer(pd.to_datetime(cutoffs))
        if (positions < 599).any() or (positions + 3 >= len(dates)).any() or (positions[1:] - positions[:-1] < 3).any():
            raise ValueError("Lịch thiếu warmup/exit hoặc chu kỳ chồng lấn")
        for cutoff, position in zip(cutoffs, positions.tolist()):
            entry, exit_date = (dates[position + offset].strftime("%Y-%m-%d") for offset in (1, 3))
            execution_prices_for_cycle(frame, events, cutoff, entry, exit_date)
            if plan["split"] != "fixture":
                year = "2023" if plan["split"] == "development_2023" else "2024"
                if any(not day.startswith(year + "-") for day in (cutoff, entry, exit_date)):
                    raise ValueError("Chu kỳ vượt biên split đã khóa")
            adapter.prepare(symbol, cutoff)


def v2_point(runner: Any, document: dict[str, Any], config: dict[str, Any], path: Path,
             signature: str, *, verify_only: bool, reconcile: bool = False,
             authorize_replay: str | None = None, replay_reason: str | None = None) -> dict[str, Any] | None:
    """Decision độc lập dùng bản sao Full; unknown cần xác nhận UUID, complete không gọi lại."""
    point = runner.adapter.prepare(**document["context"])
    shared = point.restore_full_bundle(document["shared"]["full_bundle"])
    evidence = point.evidence_v2(shared, config)
    prefix = format_evidence_prefix(evidence)
    binding = {"checkpoint_version": "research_decision_v2", "run_signature": signature,
               "point_id": document["point_id"], "shared_sha256": document["shared"]["shared_sha256"], "evidence": evidence}
    if not path.exists():
        raise ValueError("Thiếu checkpoint slot v2; không tự gọi lại Decision")
    saved = read_envelope(path)
    if saved == {"checkpoint_version": "research_decision_slot_v2", "run_signature": signature, "point_id": document["point_id"]}:
        saved = None
    if saved is not None:
        if set(saved) != {*binding, "prompt", "attempts"} or any(saved[k] != v for k, v in binding.items()):
            raise ValueError("Identity/evidence checkpoint v2 khác nguồn")
        if type(saved["attempts"]) is not list or not saved["attempts"]:
            raise ValueError("Checkpoint v2 thiếu lịch sử attempt")
        for a in saved["attempts"]:
            if set(a) != {"attempt_id", "started_at", "status", "decision", "authorization"} or a["status"] not in ("unknown", "complete"):
                raise ValueError("Schema attempt v2 không hợp lệ")
            UUID(a["attempt_id"])
            if not a["started_at"].endswith("Z"):
                raise ValueError("Timestamp attempt phải UTC")
            datetime.fromisoformat(a["started_at"])
            if (a["status"] == "unknown") != (a["decision"] is None):
                raise ValueError("Attempt status/decision không nhất quán")
            if a["authorization"] is not None:
                auth = a["authorization"]
                if set(auth) != {"at", "reason"} or not auth["reason"].strip() or not auth["at"].endswith("Z"):
                    raise ValueError("Audit replay không hợp lệ")
                datetime.fromisoformat(auth["at"])
        if any(a["status"] == "complete" for a in saved["attempts"][:-1]):
            raise ValueError("Complete không được replay")
    class Captured(Exception):
        """Ngắt builder ngay trước API để đối chiếu prompt offline."""
    def prepare(state: dict[str, Any]) -> tuple[dict[str, Any], str]:
        if state != shared:
            raise ValueError("State v2 khác Full đã seal")
        point.verify_source(state)
        return deepcopy(state), prefix
    def capture(state: dict[str, Any], prompt: str) -> None:
        nonlocal saved
        if saved is not None and saved["prompt"] != prompt:
            raise ValueError("Prompt v2 khác identity checkpoint")
        if saved is None:
            saved = {**binding, "prompt": prompt, "attempts": []}
        raise Captured()
    node = create_final_trade_decider(runner.builder.agent_llm, _prior_preparer=prepare, _before_invoke=capture)
    try:
        node(deepcopy(shared))
    except Captured:
        pass
    latest = saved["attempts"][-1] if saved["attempts"] else None
    if latest and latest["status"] == "unknown":
        if authorize_replay == latest["attempt_id"]:
            if not reconcile or not replay_reason or not replay_reason.strip():
                raise ValueError("Replay cần reconcile và lý do")
            latest["authorization"] = {"at": utc_now(), "reason": replay_reason}
            save_envelope(path, saved)
        if not reconcile and not verify_only and latest["authorization"] is None:
            raise ValueError(f"Decision v2 unknown {latest['attempt_id']}; cần reconcile trước replay")
    if (reconcile or verify_only) and (latest is None or latest["status"] != "complete"):
        return None
    if latest is None or latest["status"] != "complete":
        saved["attempts"].append({"attempt_id": str(uuid4()), "started_at": utc_now(), "status": "unknown",
                                  "decision": None, "authorization": None})
        save_envelope(path, saved)
        started = time.monotonic()
        with invocation_scope("decision_bayesian_v2") as budget:
            if budget is not None:
                budget.checkpoint_attempt_id = saved["attempts"][-1]["attempt_id"]
                budget.point_id, budget.branch_id = document["point_id"], "bayesian_v2"
                budget.run_signature = signature
            output = create_final_trade_decider(runner.builder.agent_llm, _prior_preparer=prepare)(deepcopy(shared))
        decision = parse_decision(output["final_trade_decision"], lang=runner.config["language"])
        if decision["decision"] not in ("LONG", "SHORT"):
            raise ValueError("Decision v2 không hợp lệ")
        raw = [m.content for m in output["messages"]]
        saved["attempts"][-1].update(status="complete", decision={
            "action": decision["decision"], "confidence": decision["confidence"], "risk_reward_ratio": decision["risk_reward_ratio"],
            "normalized_response": output["final_trade_decision"], "raw_response": raw,
            "latency_seconds": float(time.monotonic() - started)})
        save_envelope(path, saved)
    decision = saved["attempts"][-1]["decision"]
    parsed = parse_decision(decision["normalized_response"], lang=runner.config["language"])
    if (set(decision) != {"action", "confidence", "risk_reward_ratio", "normalized_response", "raw_response", "latency_seconds"}
            or parsed["decision"] != decision["action"] or not decision["raw_response"]
            or parsed["confidence"] != decision["confidence"] or parsed["risk_reward_ratio"] != decision["risk_reward_ratio"]
            or type(decision["latency_seconds"]) is not float or decision["latency_seconds"] < 0):
        raise ValueError("Decision v2 checkpoint khác response")
    raw_actions = {parse_decision(text if type(text) is str else json.dumps(text, ensure_ascii=False),
                                  lang=runner.config["language"])["decision"] for text in decision["raw_response"]}
    raw_actions &= {"LONG", "SHORT"}
    if (raw_actions and raw_actions != {decision["action"]}) or (not raw_actions and runner.mode == "research"):
        raise ValueError("Response raw v2 không chứng minh action đã chuẩn hóa")
    result = deepcopy(document)
    result["branches"]["bayesian_v2"] = {"status": "complete", "decision": decision}
    frame, events = runner.adapter.execution_data(document["context"]["symbol"])
    evaluation = evaluate_point(frame, events, document["context"]["as_of_date"],
        {name: result["branches"]["bayesian_v2"] for name in document["branches"]})
    result["evaluation"]["branches"]["bayesian_v2"] = evaluation["branches"]["original"]
    return result


def _report_prior(inputs: dict[str, Any] | None = None, *,
                  saved: dict[str, Any] | None = None) -> dict[str, Any]:
    """Chiếu dữ liệu đã verify sang coverage; không suy readiness từ action của LLM."""
    from core.bayesian_retriever import PREFIX_METRICS
    result = {"stats_ready": None, "examples_ready": None, "fallback": None,
        "retrieved_ids": [], "visible_example_ids": [], "visible_metric_ids": [],
        "reason_codes": [], "prefix_sha256": None, "request_sha256": None, "base_evidence_sha256": None,
        "metric_details": {}, "decision_contract_version": "decision_legacy_v1", "prior_use": None}
    if saved is not None and "evidence" in saved:
        evidence, request = saved["evidence"], saved["request"]
        if request is not None:
            view = request["trace"]
            result.update(stats_ready=evidence["gate"]["stats_ready"], examples_ready=evidence["gate"]["examples_ready"],
                fallback=view["fallback_to_original"], retrieved_ids=(evidence["selection"]["metadata"]["selected_ids"]
                    if evidence["selection"] is not None else []),
                visible_example_ids=view["visible_example_ids"], visible_metric_ids=view["visible_metric_ids"],
                reason_codes=view["reason_codes"], request_sha256=request["request_sha256"],
                base_evidence_sha256=request["base_evidence_sha256"],
                decision_contract_version=request["decision_contract_version"])
            prefix = request["prefix"]
            stats = evidence["statistics"]
            result["metric_details"] = {key: {**stats["metrics"][key],
                "ready": evidence["gate"]["metrics"][key]["status"] == "READY"}
                for key in PREFIX_METRICS} if stats is not None else {}
            attempts = saved.get("attempts", [])
            if attempts and attempts[-1]["status"] == "complete":
                result["prior_use"] = attempts[-1]["output"]["prior_decision_trace"]["prior_use"]
        else:
            prefix = format_evidence_prefix(evidence)
            result.update(stats_ready=evidence["status"] == "READY", examples_ready=evidence["status"] == "READY",
                fallback=not bool(prefix), retrieved_ids=evidence["selected_ids"],
                visible_example_ids=evidence["selected_ids"] if prefix else [],
                visible_metric_ids=[key for key in PREFIX_METRICS if prefix and evidence["metrics"][key]["posterior_mean"] is not None],
                reason_codes=evidence["reason_codes"], base_evidence_sha256=evidence["evidence_sha256"],
                metric_details={key: {**item, "ready": evidence["status"] == "READY"}
                    for key,item in evidence["metrics"].items()})
    elif inputs is not None:
        prefix, stats = inputs["bayesian_prior_context"], inputs["prior_stats"]
        ids = [r["episode_id"] for r in inputs["prior_tasks"]]
        metrics = [key for key in PREFIX_METRICS if prefix and stats is not None and stats["metrics"][key]["denominator"] > 0]
        reason = inputs["prior_metadata"].get("reason")
        result.update(stats_ready=bool(metrics), examples_ready=bool(ids),
            fallback=not bool(prefix) and inputs["prior_config"]["k"] > 0, retrieved_ids=ids,
            visible_example_ids=ids if prefix else [], visible_metric_ids=metrics,
            reason_codes=[reason] if reason else [])
    else:
        return result
    result["prefix_sha256"] = hashlib.sha256(prefix.encode("utf-8")).hexdigest()
    return copy_prior_json(result)


def _candidate_report_inputs(runner: Any, plan: dict[str, Any], root: Path,
                             signature: str, extra_point: Any) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """Nạp mọi slot đã được runner verify, kể cả partial; chấm từng nhánh complete riêng."""
    records, hashes = {}, {}
    names = plan["candidate_registry"]["order"]
    def pin(path: Path) -> None:
        hashes[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    pin(safe_path(root, "cohort.json"))
    for symbol, days in plan["symbol_cutoffs"].items():
        child = safe_path(root, f"v1/{symbol}")
        pin(child / "run_manifest.json")
        frame, events = runner.adapter.execution_data(symbol)
        records[symbol] = []
        for day in days:
            pid = f"{symbol}-{day}"
            path = safe_path(child, f"points/{pid}.json")
            base = read_document(path, runner.schema, "point")
            pin(path)
            journal = safe_path(child, f"responses/{pid}.json")
            if journal.exists():
                pin(journal)
            point = runner.adapter.prepare(symbol, day)
            features = point.price_features()
            doc = deepcopy(base)
            views = {name:_report_prior(branch["input"]) for name,branch in base["branches"].items()}
            for name in names:
                cpath = safe_path(root, f"candidates/{name}/{pid}.json")
                saved = read_envelope(cpath)
                pin(cpath)
                extended = extra_point(base, root, name, signature, verify_only=True) if base["status"] == "complete" else None
                if extended is not None:
                    doc["branches"][name] = extended["branches"][name]
                    doc["evaluation"]["branches"][name] = extended["evaluation"]["branches"][name]
                else:
                    attempts = saved.get("attempts", [])
                    doc["branches"][name] = {"status": "unknown" if attempts else "planned", "decision": None, "error": None}
                views[name] = _report_prior(saved=saved)
            # Point v1 chưa seal vẫn có thể có các Decision complete đã verify.
            for name, branch in doc["branches"].items():
                if branch["status"] != "complete":
                    continue
                evaluation = evaluate_point(frame, events, day, {key:branch for key in PRIOR_BRANCH_MODES})
                if doc["evaluation"] is None:
                    doc["evaluation"] = {**evaluation, "branches": {}}
                doc["evaluation"]["branches"][name] = evaluation["branches"]["original"]
            doc["report_context"] = {"regime": point.market_regime["regime_name"],
                "feature_status": features["status"], "feature_reasons": features["reasons"], "prior": views}
            records[symbol].append(doc)
    return records, {"run_signature": signature, "execution_mode": runner.mode,
        "plan_sha256": canonical_hash(plan), "registry_sha256": canonical_hash(plan["candidate_registry"]),
        "code_sha256": plan["code_sha256"], "runtime": plan["runtime"], "sources": runner.adapter.source_hashes,
        "price_index": plan["price_index"], "model": plan["inputs"].get("model"), "checkpoint_sha256": hashes}


def run_cohort(runner: Any, plan: dict[str, Any], output_dir: Path, *, symbols: list[str] | None = None,
               resume: bool = False, verify_only: bool = False, reconcile: bool = False,
               authorize_replay: str | None = None, replay_reason: str | None = None,
               ledger_path: Path | None = None) -> dict[str, Any]:
    """Điều phối tuần tự bốn mã, reuse checkpoint/kiểm semantic v1 và bổ sung Decision v2."""
    index = validate_plan(plan, runner.adapter)
    candidate_mode = plan["plan_version"] == "research_cohort_plan_v3"
    if candidate_mode:
        if not runner.durable_stages:
            raise ValueError("Ứng viên cần durable stage journal")
        if runner.mode != "offline_fixture":
            expected_ledger = (runner.adapter._files.root / "outputs/oos_pilot/api_usage.json").resolve()
            if runner.quota_policy != "request_admission_v2" or ledger_path is None or ledger_path.resolve() != expected_ledger:
                raise ValueError("Ứng viên cần policy request và ledger tài khoản chung đã khóa")
            if plan["split"] == "fixture" and not (verify_only or reconcile):
                raise ValueError("Fixture ứng viên chỉ chạy với execution_mode offline_fixture")
    from core.candidate_cohort import CANDIDATES, candidate_point, candidate_slot
    extra_names = list(CANDIDATES) if candidate_mode else ["bayesian_v2"] if plan["matrix"] == "research_v2" else []
    def branch_path(root: Path, point_id: str, name: str) -> Path:
        return safe_path(root, f"candidates/{name}/{point_id}.json" if candidate_mode else f"v2/{point_id}.json")
    def extra_point(doc: dict[str, Any], root: Path, name: str, signature: str, **options: Any) -> dict[str, Any] | None:
        path = branch_path(root, doc["point_id"], name)
        if candidate_mode:
            return candidate_point(runner, doc, plan, index, name, path, signature, **options)
        return v2_point(runner, doc, plan["evidence_config"], path, signature, **options)
    if "input_lock" in plan["inputs"]:
        from core.research_input_lock import validate_bound_plan
        lock = validate_bound_plan(plan, runner.adapter._files.root)
        expected_ledger = (runner.adapter._files.root / lock["ledger_path"]).resolve()
        if runner.quota_policy != lock["quota_policy"] or ledger_path is None or ledger_path.resolve() != expected_ledger:
            raise ValueError("Runner khác policy hoặc ledger chung đã khóa")
    if authorize_replay is not None:
        UUID(authorize_replay)
        if not reconcile or type(replay_reason) is not str or not replay_reason.strip() or len(replay_reason) > 1000:
            raise ValueError("Xác nhận cần reconcile và lý do tối đa 1000 ký tự")
    symbols = sorted(SYMBOLS) if symbols is None else symbols
    if not symbols or len(set(symbols)) != len(symbols) or not set(symbols) <= SYMBOLS:
        raise ValueError("Danh sách mã không hợp lệ")
    contexts = {s: [runner.adapter.prepare(s, c) for c in plan["symbol_cutoffs"][s]] for s in sorted(SYMBOLS)}
    child_identities = {s: runner._identity(s, 3, points) for s, points in contexts.items()}
    identity = {"identity_version": "research_cohort_identity_v2", "plan": plan, "versions": VERSIONS,
                "ledger_path": str(ledger_path.resolve()) if ledger_path is not None else None,
                "retry_policy": "invocation_budget_v2", "metric_version": "cycle_risk_metrics_v2",
                "children": {s: canonical_hash(value) for s, value in child_identities.items()},
                "code_sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in (
                    "core/research_cohort.py", "core/research_metrics.py", "core/prior_evidence_v2.py", "core/research_invocation.py")}}
    if candidate_mode:
        identity.update(identity_version="research_cohort_identity_v3", versions=plan["candidate_registry"],
                        code_sha256=plan["code_sha256"], runtime=plan["runtime"])
    signature = canonical_hash(identity)
    root = Path(output_dir).resolve()
    manifest = safe_path(root, "cohort.json")
    if not manifest.exists() and (verify_only or reconcile or resume):
        raise ValueError("Thiếu cohort manifest; không migrate pilot W4")
    if not manifest.exists() and root.exists() and any(root.iterdir()):
        raise ValueError("Cohort mới cần thư mục trống")
    with PriorRunLock(root, signature):
        if manifest.exists():
            if not (resume or verify_only or reconcile) or read_envelope(manifest) != identity:
                raise ValueError("Cohort khác identity hoặc thiếu --resume")
        else:
            # Khởi tạo toàn plan trước API; mất một thư mục con sau đó phải báo lỗi.
            for symbol, points in contexts.items():
                frame, events = runner.adapter.execution_data(symbol)
                store = PriorCheckpointStore(runner, safe_path(root, f"v1/{symbol}"),
                    child_identities[symbol], points, frame, events)
                with store.lock:
                    store.initialize(resume=False)
            if extra_names:
                for symbol, cutoffs in plan["symbol_cutoffs"].items():
                    for cutoff in cutoffs:
                        pid = f"{symbol}-{cutoff}"
                        for name in extra_names:
                            slot = candidate_slot(signature, pid, name) if candidate_mode else {
                                "checkpoint_version": "research_decision_slot_v2", "run_signature": signature, "point_id": pid}
                            save_envelope(branch_path(root, pid, name), slot)
            save_envelope(manifest, identity)
        records: dict[str, list[dict[str, Any]]] = {}
        token = ENABLED.set(True)
        try:
            reconciled = {}
            # Kiểm toàn bộ checkpoint trước HTTP đầu tiên, kể cả mã không được chọn.
            for symbol in sorted(SYMBOLS):
                child = safe_path(root, f"v1/{symbol}")
                if not (child / "run_manifest.json").exists():
                    raise ValueError("Mất manifest mã đã khởi tạo; không tự chạy lại")
                reconciled[symbol] = runner.run(symbol, output_dir=child,
                    cutoffs=tuple(plan["symbol_cutoffs"][symbol]), reconcile=True)
            if extra_names:
                expected = {branch_path(root, f"{s}-{c}", name) for s, dates in plan["symbol_cutoffs"].items()
                            for c in dates for name in extra_names}
                directory = safe_path(root, "candidates" if candidate_mode else "v2")
                if set(directory.rglob("*.json")) != expected:
                    raise ValueError("Slot checkpoint v2 khác plan")
            reconciliation = {"run_signature": signature, "upstream": reconciled, "decisions": []}
            authorizations_path = safe_path(root, "replay_authorizations.json")
            approvals = read_envelope(authorizations_path) if authorizations_path.exists() else {"run_signature": signature, "attempts": {}}
            if set(approvals) != {"run_signature", "attempts"} or approvals["run_signature"] != signature:
                raise ValueError("Audit replay khác run")
            matched = False
            for symbol in reconciled:
                child = safe_path(root, f"v1/{symbol}")
                for meta in reconciled[symbol]["points"]:
                    for node in meta["nodes"]:
                        # Journal upstream tự kiểm UUID và chỉ cho phép xác nhận attempt cuối.
                        if authorize_replay and authorize_replay == node["attempt_id"]:
                            runner.run(symbol, output_dir=child, cutoffs=tuple(plan["symbol_cutoffs"][symbol]),
                                reconcile=True, authorize_replay=authorize_replay, replay_reason=replay_reason)
                            matched = True
                for path in (child / "points").glob("*.json"):
                    doc = read_document(path, runner.schema, "point")
                    for name, branch in doc["branches"].items():
                        if branch["status"] != "complete" and branch["attempts"]:
                            attempt = branch["attempts"][-1]["attempt_id"]
                            reconciliation["decisions"].append({"point_id": doc["point_id"], "branch": name, "attempt_id": attempt, "status": branch["status"]})
                            if authorize_replay == attempt:
                                matched = True
                                approvals["attempts"][attempt] = {"at": utc_now(), "reason": replay_reason}
                            if not verify_only and not reconcile and attempt not in approvals["attempts"]:
                                raise ValueError(f"Decision chưa rõ {attempt}; cần --reconcile và xác nhận replay")
                    for name in extra_names:
                        vpath = branch_path(root, doc["point_id"], name)
                        vdoc = read_envelope(vpath)
                        if doc["status"] != "complete":
                            slot = candidate_slot(signature, doc["point_id"], name) if candidate_mode else {
                                "checkpoint_version": "research_decision_slot_v2", "run_signature": signature, "point_id": doc["point_id"]}
                            if vdoc != slot:
                                raise ValueError("Decision bổ sung đã chạy trước Full/v1 complete")
                            continue
                        attempts = vdoc.get("attempts", [])
                        if attempts:
                            last = attempts[-1]
                            reconciliation["decisions"].append({"point_id": doc["point_id"], "branch": name, "attempt_id": last["attempt_id"], "status": last["status"]})
                            if authorize_replay == last["attempt_id"]:
                                if last["status"] != "unknown" or last["authorization"] is not None:
                                    raise ValueError("Chỉ xác nhận attempt v2 unknown cuối chưa được xác nhận")
                                matched = True
                            if not verify_only and not reconcile and last["status"] != "complete" and last["authorization"] is None:
                                raise ValueError(f"Decision v2 unknown {last['attempt_id']}; cần reconcile")
                        extra_point(doc, root, name, signature, verify_only=True,
                            reconcile=reconcile, authorize_replay=authorize_replay, replay_reason=replay_reason)
            if authorize_replay:
                if not reconcile or not replay_reason or not replay_reason.strip() or not matched:
                    raise ValueError("Replay cần UUID thuộc attempt cuối, --reconcile và lý do")
                save_envelope(authorizations_path, approvals)
            if reconcile:
                return reconciliation
            for symbol in sorted(SYMBOLS):
                child = safe_path(root, f"v1/{symbol}")
                exists = (child / "run_manifest.json").exists()
                selected = symbol in symbols and not verify_only and not reconcile
                if not selected and not exists:
                    continue
                callback = None
                if selected and candidate_mode:
                    def complete_candidates(doc: dict[str, Any]) -> None:
                        for name in extra_names:
                            doc = extra_point(doc, root, name, signature, verify_only=False)
                    # Điểm v1 đã complete trước crash phải xong candidate trước điểm kế.
                    for path in sorted((child / "points").glob("*.json")):
                        doc = read_document(path, runner.schema, "point")
                        if doc["status"] == "complete":
                            complete_candidates(doc)
                    callback = lambda event: complete_candidates(event["latest"])
                result = runner.run(symbol, output_dir=child, cutoffs=tuple(plan["symbol_cutoffs"][symbol]),
                    resume=exists, verify_only=not selected, reconcile=reconcile,
                    authorize_replay=None, replay_reason=None, **({"callback": callback} if callback else {}))
                if candidate_mode:
                    continue
                for item in result["point_files"]:
                    document = read_document(safe_path(child, item["path"]), runner.schema, "point")
                    for name in extra_names:
                        extended = extra_point(document, root, name, signature,
                            verify_only=not selected or candidate_mode, reconcile=reconcile,
                            authorize_replay=authorize_replay, replay_reason=replay_reason)
                        if extended is None:
                            document = None
                            break
                        document = extended
                    if document is not None:
                        records.setdefault(symbol, []).append(document)
            binding = None
            if candidate_mode:
                records, binding = _candidate_report_inputs(runner, plan, root, signature, extra_point)
            report = research_report(plan, records, binding=binding)
            report["run_signatures"] = [signature, *identity["children"].values()]
            if not verify_only and not reconcile:
                save_envelope(safe_path(root, "report.json"), report)
            return report
        finally:
            ENABLED.reset(token)
