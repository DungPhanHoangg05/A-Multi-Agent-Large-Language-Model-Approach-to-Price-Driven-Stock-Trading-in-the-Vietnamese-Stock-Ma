"""Collector panel v4.1; journal ri?ng, d?ng c?c primitive baseline ?? kh?a c?a v4."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from core.historical_signals import digest, native_json
from core.improvement_transport import SLOT, body_contract
from core.mt_bicl_v2_api_preflight import wire_body
from core.mt_bicl_v2_decision import canonical_request, invoke_decision
from core.mt_bicl_v4_collect import input_state, clients, audit_http, original_from_raw, _rows_for, _agent_features
from core.mt_bicl_v4_completion import DataCompletionError
from core.mt_bicl_v4_dataset import immutable
from core.mt_bicl_v4_protocol import canonical, checksum, read, safe_path
from core.mt_bicl_v41_protocol import NAMESPACE
from core.prior_stage_journal import StageJournal
from core.research_invocation import CURRENT, ENABLED, RECOVERY, invocation_scope
from core.research_cohort import read_envelope, save_envelope
from agents.decision_agent import TradeDecisionOutput
from utils.historical_api import _invoke_with_retry
from scripts.continue_mt_bicl_v4_data import control_requests
from core.mt_bicl_v4_collect_transport import OfflinePending, ReplayTransport

DIRECTORY = NAMESPACE / 'collection'


def collect_point(root: Path, row: dict[str, Any], frame: Any, articles: list[dict[str, Any]],
                  release: dict[str, Any], signature: str, llms: tuple[Any, Any], ledger: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """Mỗi node một UUID durable, complete chỉ đọc; replay trước key chạy cùng hàm này."""
    from utils.graph_setup import SetGraph
    from utils.graph_util import TechnicalTools
    from core.research_cohort import save_envelope, read_envelope
    pid = row["episode_id"]
    if pid not in release['point_ids']:
        raise DataCompletionError('Point không thuộc panel256 đã khóa')
    directory = root / DIRECTORY / "points" / pid
    path = directory / "complete.json"
    state, source = input_state(row, frame, articles, release["config"], render_images=not path.exists())
    binding = {"run_signature": signature, "point_id": pid, "source_sha256": checksum(canonical(source))}
    cache = root / DIRECTORY / "http_cache"
    if path.exists():
        saved = read(path.read_bytes())
        if saved.get('version') != 'conditional_v4_1_collected_point' or saved["binding"] != binding or saved["source"] != source:
            raise DataCompletionError("Point complete khác nguồn PIT")
        for name, expected in saved["files_sha256"].items():
            if checksum(safe_path(root, name).read_bytes()) != expected:
                raise DataCompletionError("Bằng chứng point complete bị sửa/mất")
        by_id = {r["id"]: r for r in ledger()["requests"]}
        for rid, expected in saved["http"]["http_rows_sha256"].items():
            if rid not in by_id or checksum(canonical(by_id[rid])) != expected:
                raise DataCompletionError("Ledger point complete bị sửa")
        from core.research_cohort import read_envelope
        journal = StageJournal(directory / "stages.json", binding)
        if list(journal.document["nodes"]) != ["indicator", "pattern", "trend", "full"]:
            raise DataCompletionError("Point complete thiếu4 node")
        expected_reports = {}
        for name, node in journal.document["nodes"].items():
            last = node["attempts"][-1]
            if last["status"] != "complete":
                raise DataCompletionError("Point complete còn stage unknown")
            fields = ("alpha_report", "sentiment_report") if name == "full" else (name + "_report",)
            expected_reports.update({k: last["output"][k] for k in fields})
        original = read_envelope(directory / "original.json")
        full = journal.document["nodes"]["full"]["attempts"][-1]["output"]
        attempts = {n["attempts"][-1]["attempt_id"] for n in journal.document["nodes"].values()} | {original["attempt_id"]}
        shared = {"stock_name": row["symbol"], "as_of_date": row["as_of_date"], "language": "vi", "is_backtest": True,
                  "time_frame": "1d", **expected_reports}
        if original["binding"] != binding or original["request"] != canonical_request(shared, "", {"decision": release["config"]}):
            raise DataCompletionError("Original complete khác canonical request từ reports PIT")
        if (saved["reports"] != expected_reports or original["status"] != "complete"
                or saved["original"] != original["decision"]
                or saved["agent"] != _agent_features(expected_reports, full["sentiment_data"]["alpha_results"], original["decision"])
                or saved["http"] != audit_http(ledger(), cache, signature, pid, attempts)):
            raise DataCompletionError("Point complete khác journal/Original/raw")
        parsed = original_from_raw(_rows_for(ledger(), signature, pid), cache, original["attempt_id"], original["contract"])
        if not parsed or original["decision"] != parsed[-1]:
            raise DataCompletionError("Original complete khác raw durable")
        return saved
    journal = StageJournal(directory / "stages.json", binding, create=True)
    def stage(name: str, function: Callable, current: dict[str, Any]) -> dict[str, Any]:
        def invoke(actual: dict[str, Any]) -> dict[str, Any]:
            budget = CURRENT.get()
            if budget is None:
                raise DataCompletionError("Node thiếu invocation")
            budget.branch_id = name
            token = SLOT.set({**binding, "branch_id": name, "checkpoint_attempt_id": budget.checkpoint_attempt_id})
            try:
                return function(actual)
            finally:
                SLOT.reset(token)
        return journal.invoke(name, invoke, current)
    enable, recovery = ENABLED.set(True), RECOVERY.set(True)
    try:
        builder = SetGraph(*llms, TechnicalTools())
        upstream = builder.compile_upstream(stage_checkpoint=stage).invoke(deepcopy(state))
        if (digest(upstream["kline_data"]) != digest(state["kline_data"])
                or not upstream["point_in_time_df"].equals(state["point_in_time_df"])):
            raise DataCompletionError("Upstream thay nguồn PIT")
        upstream["sentiment_store"] = state["sentiment_store"]
        full = builder.compile_full_preparation(strict_research_mode=True, stage_checkpoint=stage).invoke(deepcopy(upstream))
        sentiment = full["sentiment_data"]
        if any(sentiment.get(k) != v for k, v in state["sentiment_store"].data.items()):
            raise DataCompletionError("Alpha thay dữ liệu sentiment PIT")
        reports = {k: full[k] for k in ("indicator_report", "pattern_report", "trend_report", "alpha_report", "sentiment_report")}
        shared = {"stock_name": row["symbol"], "as_of_date": row["as_of_date"], "language": "vi", "is_backtest": True, "time_frame": "1d", **reports}
        request = canonical_request(shared, "", {"decision": release["config"]})
        contract = body_contract(wire_body(llms[0], request))
        original_path = directory / "original.json"
        if original_path.exists():
            original = read_envelope(original_path)
            if original["binding"] != binding or original["request"] != request or original["contract"] != contract:
                raise DataCompletionError("Original intent khác reports/request")
        else:
            original = {"binding": binding, "request": request, "contract": contract,
                        "attempt_id": str(uuid4()), "status": "unknown", "decision": None}
            save_envelope(original_path, original)
        if original["status"] != "complete":
            token = SLOT.set({**binding, "branch_id": "original", "checkpoint_attempt_id": original["attempt_id"]})
            try:
                decision = invoke_decision(llms[0], request, attempt_id=original["attempt_id"], run_signature=signature, branch_id="original")
            finally:
                SLOT.reset(token)
            original.update(status="complete", decision=decision)
            save_envelope(original_path, original)
        attempts = {node["attempts"][-1]["attempt_id"] for node in journal.document["nodes"].values()} | {original["attempt_id"]}
        http = audit_http(ledger(), cache, signature, pid, attempts)
        # Indicator/Alpha backtest là tính toán Python thật đã khóa, không gọi LLM.
        # Pattern/Trend/Original bắt buộc có response HTTP200 durable.
        rows = _rows_for(ledger(), signature, pid)
        required = {journal.document["nodes"][name]["attempts"][-1]["attempt_id"] for name in ("pattern", "trend")} | {original["attempt_id"]}
        deterministic = {journal.document["nodes"][name]["attempts"][-1]["attempt_id"] for name in ("indicator", "full")}
        if any(r.get("checkpoint_attempt_id") in deterministic for r in rows):
            raise DataCompletionError("Indicator/Alpha backtest không được tự thêm API")
        if any(not any(r.get("checkpoint_attempt_id") == attempt and r["status"] == 200 and r["id"] in http["raw_sha256"] for r in rows) for attempt in required):
            raise DataCompletionError("Stage collection thiếu raw HTTP200 durable")
        actual = original_from_raw(rows, cache, original["attempt_id"], contract)
        if not actual or actual[-1] != original["decision"]:
            raise DataCompletionError("Original parsed khác raw HTTP đã audit")
        features = _agent_features(reports, native_json(sentiment["alpha_results"]), original["decision"])
        files = {(directory / name).relative_to(root).as_posix(): checksum((directory / name).read_bytes()) for name in ("stages.json", "original.json")}
        files.update({(DIRECTORY / "http_cache" / (rid + ".json")).as_posix(): sha for rid, sha in http["raw_sha256"].items()})
        result = {"version": "conditional_v4_1_collected_point", "binding": binding, "source": source,
            "reports": reports, "agent": features, "original": original["decision"], "http": http, "files_sha256": files}
        immutable(path, result)
        return result
    finally:
        ENABLED.reset(enable)
        RECOVERY.reset(recovery)



def controls(root: Path, release: dict[str, Any], signature: str, llms: tuple[Any, Any], pacer: Any) -> None:
    """Mỗi scope credential có intent/probe riêng; không xóa proof cũ khi đổi key."""
    scope = pacer.credential_scope
    control_signature = checksum(canonical({"collection": signature, "scope": scope, "purpose": "SYNTHETIC_ONLY"}))
    for request in control_requests():
        pid = "CONTROL_V4_" + request["id"]
        path = root / DIRECTORY / "controls" / scope / (request["id"] + ".json")
        if path.exists():
            saved = read_envelope(path)
            if saved["request"] != request or saved["signature"] != control_signature:
                raise DataCompletionError("Control khác request/scope")
        else:
            saved = {"signature": control_signature, "request": request, "attempt_id": str(uuid4()), "status": "unknown", "http": None, "result": None}
            save_envelope(path, saved)
        if saved["status"] == "complete":
            proof = audit_http(pacer.state, root / DIRECTORY / "http_cache", control_signature, pid, {saved["attempt_id"]})
            if proof != saved["http"]:
                raise DataCompletionError("Raw/ledger control đã đổi")
            if saved["result"] != (request["expected"] if request["id"] == "original" else "CONTROL_PASS"):
                raise DataCompletionError("Nội dung control complete bị sửa")
            continue
        from langchain_core.messages import HumanMessage
        enable, recovery = ENABLED.set(True), RECOVERY.set(True)
        try:
            with invocation_scope("decision_control" if request["id"] == "original" else "control_" + request["id"]) as budget:
                budget.run_signature, budget.point_id, budget.branch_id = control_signature, pid, "control_" + request["id"]
                budget.checkpoint_attempt_id = saved["attempt_id"]
                token = SLOT.set({"run_signature": control_signature, "point_id": pid, "branch_id": budget.branch_id, "checkpoint_attempt_id": saved["attempt_id"]})
                try:
                    if request["id"] == "original":
                        value = invoke_decision(llms[0], {"point_id": pid, "structured": {"schema": TradeDecisionOutput.model_json_schema()},
                            "messages": [{"role": "user", "content": request["content"]}]}, attempt_id=saved["attempt_id"], run_signature=control_signature, branch_id=budget.branch_id)
                        if value != request["expected"]:
                            raise DataCompletionError("Control Original sai nội dung synthetic")
                    else:
                        llm = llms[0 if request["role"] == "agent" else 1]
                        value = _invoke_with_retry(llm.invoke, [HumanMessage(content=request["content"])]).content
                        if not isinstance(value, str) or value.strip() != "CONTROL_PASS":
                            raise DataCompletionError("Control text/vision sai nội dung synthetic")
                finally:
                    SLOT.reset(token)
        finally:
            ENABLED.reset(enable)
            RECOVERY.reset(recovery)
        proof = audit_http(pacer.state, root / DIRECTORY / "http_cache", control_signature, pid, {saved["attempt_id"]})
        if not proof["raw_sha256"]:
            raise DataCompletionError("Control thiếu raw200")
        saved.update(status="complete", result=native_json(value), http=proof)
        save_envelope(path, saved)


def cold_point(root: Path, row: dict[str, Any], frame: Any, articles: list[dict[str, Any]],
               release: dict[str, Any], signature: str, ledger: dict[str, Any]) -> dict[str, Any]:
    """Tái dựng cả canonical upstream/Original qua raw cache; không reserve/key/socket."""
    import httpx
    from utils.graph_setup import SetGraph
    from utils.graph_util import TechnicalTools
    saved = collect_point(root, row, frame, articles, release, signature, None, lambda: ledger)
    path = root/DIRECTORY/'points'/row['episode_id']
    journal = StageJournal(path/'stages.json', saved['binding'])
    with httpx.Client(transport=ReplayTransport(ledger, root/DIRECTORY/'http_cache')) as http:
        llms = clients(release['config'], http, 'offline-fixture-not-a-credential')
        state, proof = input_state(row, frame, articles, release['config'])
        if proof != saved['source']:
            raise DataCompletionError('Cold panel khác nguồn PIT')

        def stage(name: str, function: Callable, current: dict[str, Any]) -> dict[str, Any]:
            attempt = journal.document['nodes'][name]['attempts'][-1]['attempt_id']
            with invocation_scope(name) as budget:
                budget.run_signature, budget.point_id, budget.branch_id = signature, row['episode_id'], name
                budget.checkpoint_attempt_id = attempt
                token = SLOT.set({**saved['binding'], 'branch_id': name, 'checkpoint_attempt_id': attempt})
                try:
                    return function(current)
                finally:
                    SLOT.reset(token)
        enabled, recovery = ENABLED.set(True), RECOVERY.set(True)
        try:
            graph = SetGraph(*llms, TechnicalTools())
            upstream = graph.compile_upstream(stage_checkpoint=stage).invoke(deepcopy(state))
            upstream['sentiment_store'] = state['sentiment_store']
            full = graph.compile_full_preparation(strict_research_mode=True, stage_checkpoint=stage).invoke(deepcopy(upstream))
            reports = {k: full[k] for k in saved['reports']}
            if reports != saved['reports']:
                raise DataCompletionError('Cold reports không khớp raw/canonical upstream')
            original = read_envelope(path/'original.json')
            token = SLOT.set({**saved['binding'], 'branch_id': 'original', 'checkpoint_attempt_id': original['attempt_id']})
            try:
                actual = invoke_decision(llms[0], original['request'], attempt_id=original['attempt_id'],
                                         run_signature=signature, branch_id='original')
            finally:
                SLOT.reset(token)
            if actual != saved['original'] or _agent_features(reports, native_json(full['sentiment_data']['alpha_results']), actual) != saved['agent']:
                raise DataCompletionError('Cold Original/factor khác bằng chứng thật')
        except OfflinePending:
            raise DataCompletionError('Thiếu raw đúng canonical request khi cold panel') from None
        finally:
            ENABLED.reset(enabled)
            RECOVERY.reset(recovery)
    return saved

