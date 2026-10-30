"""Dry-run SDK, control preflight và projection ngân sách cho release development v3."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import numpy as np

from agents.decision_agent import TradeDecisionOutput
from core.bayesian_memory import read_json
from core.groq_pacing import request_budget
from core.improvement_recovery import ResilientPacer
from core.improvement_transport import SLOT, body_contract
from core.mt_bicl_bank import content_hash
from core.mt_bicl_v2_development import GuardedHTTP
from core.mt_bicl_v2_io import read_envelope, write_envelope
from core.mt_bicl_v21_preparation import file_hash
from core.mt_bicl_v3_contracts import wire_schema
from core.mt_bicl_v3_freeze import OUTPUT, DRY_VERSION, RELEASE, RELEASE_VERSION, legacy_fixture, fixture_reply
from core.mt_bicl_v3_run import DevelopmentRun
from core.mt_bicl_v3_transport import BudgetTransport
from core.mt_bicl_v3_wire import client, wire_body, invoke, audit_attempt, REPLY_NAME

CONTROL_VERSION = "utility_icl_live_control_v3"
CONTROL_READY = "utility_icl_live_control_ready_v3"


def check_control_semantics(request: dict[str, Any], decision: dict[str, Any]) -> None:
    """Control sai facts không được retry để chọn câu trả lời thuận lợi hoặc cấp release."""
    if decision["decision"] != "SHORT" or decision["forecast_horizon"] != "T+2.5":
        raise ValueError("Control synthetic không giữ action/horizon đã yêu cầu")
    if request["control_id"].startswith("anchored") and (decision["fact_assertions"] != {"MACD_SIGNAL": "UNKNOWN", "MACD_ZERO": "UNKNOWN", "PRICE_SMA20": "UNKNOWN"}
            or decision["context_reason"] != "NOT_APPLICABLE"):
        raise ValueError("Control synthetic sai assertion/context reason")


def serialization(llm: Any, request: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Dùng một serializer cho mock/live/verify, không tự dựng body HTTP khác SDK."""
    body = wire_body(llm, request)
    return body_contract(body), request_budget(body)


def dry_run(root: Path, manifest: dict[str, Any], snapshot: dict[str, Any], budget: Any) -> dict[str, Any]:
    """Chạy804 slot qua engine/SDK/audit/cache thật và replay không invoke lần hai."""
    directory = root/OUTPUT/"offline_dry_run"
    runner = DevelopmentRun(directory, manifest, snapshot, mode="offline_fixture")
    now = [1800000000.]
    pacer = ResilientPacer(directory/"fixture_ledger.json", credential="offline-no-credential", amendment_sha256=content_hash(manifest),
                           policy="request_admission_v2", clock=lambda: now[0], monotonic=lambda: now[0], sleep=lambda n: now.__setitem__(0, now[0]+n))
    expected: dict[str, Any] = {}
    def respond(request: httpx.Request) -> httpx.Response:
        """Response giả chỉ theo facts/role, không dựa nhãn query hoặc đánh giá P&L."""
        slot = SLOT.get()
        point = snapshot["points"][slot["point_id"]]
        anchored = json.loads(request.content)["response_format"]["json_schema"]["name"] == REPLY_NAME
        parsed = fixture_reply(point["facts"]) if anchored else legacy_fixture()
        if anchored and slot["branch_id"] != "Fact_Anchor": parsed["context_reason"] = "SUPPORTED"
        now[0] += 61.
        return httpx.Response(200, json={"id": "offline-fixture", "object": "chat.completion", "created": 0,
            "model": snapshot["protocol"]["decision"]["config"]["signal_config"]["models"]["agent_llm_model"],
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": json.dumps(parsed, ensure_ascii=False)}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 20, "total_tokens": 40}})
    transport = BudgetTransport(pacer, directory/"http_cache", budget, GuardedHTTP(expected, httpx.MockTransport(respond)))
    with httpx.Client(transport=transport) as http:
        llm = client(snapshot["protocol"]["decision"]["config"], http, "offline-no-credential")
        def dispatch(request: dict[str, Any], slot: dict[str, Any]) -> dict[str, Any]:
            expected[slot["canonical_sha256"]] = serialization(llm, request)[0]
            token = SLOT.set(slot)
            try: return invoke(llm, request, slot)
            finally: SLOT.reset(token)
        result = runner.execute(dispatch, lambda request: serialization(llm, request), lambda: pacer.state, directory/"http_cache", budget.check, budget.checkpoint)
        def reject(request: dict[str, Any], slot: dict[str, Any]) -> dict[str, Any]:
            raise AssertionError("Cold replay fixture đã gọi lại model/HTTP")
        replay = runner.execute(reject, lambda request: serialization(llm, request), lambda: pacer.state, directory/"http_cache", budget.check, budget.checkpoint)
    if replay != result or result["complete_slots"] != 804: raise ValueError("Dry-run/replay không đủ804 slot")
    facts = {"status": "PASS", "scope": "OFFLINE_FIXTURE_NOT_MARKET_ACTIONS", "result": result, "cold_replay": "PASS",
             "real_HTTP_calls": 0, "upstream_new_calls": 0, "model_forward_calls": 0,
             "journal_sha256": {path.relative_to(directory).as_posix(): file_hash(path) for path in sorted((directory/"slots").glob("*.json"))},
             "fixture_ledger_sha256": file_hash(directory/"fixture_ledger.json")}
    write_envelope(root/OUTPUT/"freeze/dry_run.json", DRY_VERSION, facts, immutable=True)
    return facts


def controls(manifest: dict[str, Any], snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Bốn probe synthetic, schema legacy/anchored và độ dài đại diện; không dự báo cohort."""
    requests = []
    length = max(v["max_prompt_chars"] for group in manifest["request_bounds"].values() for v in group.values())
    for anchored in (False, True):
        for long in (False, True):
            parsed = legacy_fixture()
            if anchored:
                parsed.update(version="utility_icl_reply_v3", fact_ids=["MACD_SIGNAL", "MACD_ZERO", "PRICE_SMA20"],
                              fact_assertions={"MACD_SIGNAL": "UNKNOWN", "MACD_ZERO": "UNKNOWN", "PRICE_SMA20": "UNKNOWN"}, context_reason="NOT_APPLICABLE")
            text = "CONTROL ONLY: không dự báo thị trường, không dùng point/nhãn. Trả chính xác một JSON hợp lệ theo schema và nội dung sau: "+json.dumps(parsed, ensure_ascii=False)
            if long:
                pad = " Kiểm định giao thức, dữ liệu giả lập, không phải dữ liệu thị trường."
                text += (pad*math.ceil(max(0, length-len(text))/len(pad)))[:max(0, length-len(text))]
            requests.append({"point_id": "API_PREFLIGHT_V3", "repeat_index": 0,
                             "structured": {"schema": deepcopy(wire_schema()["$defs"]["reply"] if anchored else TradeDecisionOutput.model_json_schema())},
                             "messages": [{"role": "user", "content": text}], "control_id": ("anchored" if anchored else "legacy")+("_long" if long else "_short")})
    return requests


def control_run(root: Path, manifest: dict[str, Any], snapshot: dict[str, Any], pacer: Any, llm: Any, expected: dict[str, Any], budget: Any) -> dict[str, Any]:
    """Theo credential scope, intent/control durable; không chạy primary ở bước preflight."""
    directory = root/OUTPUT/"controls"/pacer.credential_scope
    signature = content_hash({"manifest_sha256": content_hash(manifest), "credential_scope": pacer.credential_scope, "purpose": "CONTROL_ONLY"})
    cache = root/OUTPUT/"run/http_cache"
    proofs = []
    for request in controls(manifest, snapshot):
        budget.check()
        path = directory/(request["control_id"]+".json")
        contract, reserve = serialization(llm, request)
        expected[content_hash(request)] = contract
        if path.exists():
            saved = read_envelope(path, CONTROL_VERSION)
            if (saved["request"] != request or saved["contract"] != contract or saved["run_signature"] != signature
                    or saved["status"] not in ("unknown", "complete")):
                raise ValueError("Control intent khác source/body/scope/status")
        else:
            saved = {"status": "unknown", "request": request, "contract": contract, "run_signature": signature,
                     "attempt_id": str(uuid4()), "decision": None, "request_ids": [], "cache_hashes": {}}
            write_envelope(path, CONTROL_VERSION, saved, immutable=True)
        slot = {"run_signature": signature, "point_id": "API_PREFLIGHT_V3", "branch_id": "Fact_Anchor" if request["control_id"].startswith("anchored") else "Original",
                "canonical_sha256": content_hash(request), "checkpoint_attempt_id": saved["attempt_id"], "control_id": request["control_id"]}
        parsed, ids, hashes = audit_attempt(pacer.state, cache, slot, request, contract)
        if saved["status"] == "complete":
            if parsed != saved["decision"] or ids != saved["request_ids"] or hashes != saved["cache_hashes"]: raise ValueError("Control complete khác raw/ledger")
        else:
            if parsed is None:
                previous = {r["id"]: content_hash(r) for r in pacer.state["requests"]}
                token = SLOT.set(slot)
                try: result = invoke(llm, request, slot)
                finally: SLOT.reset(token)
                current = {r["id"]: content_hash(r) for r in pacer.state["requests"]}
                if any(current.get(rid) != checksum for rid, checksum in previous.items()):
                    raise ValueError("Control retry đã sửa/xóa ledger cũ")
                parsed, ids, hashes = audit_attempt(pacer.state, cache, slot, request, contract)
                if parsed is None or parsed != result: raise ValueError("Control response chưa durable/đúng schema")
            check_control_semantics(request, parsed)
            saved.update(status="complete", decision=parsed, request_ids=ids, cache_hashes=hashes)
            write_envelope(path, CONTROL_VERSION, saved)
        proofs.append({"path": path.relative_to(root).as_posix(), "sha256": file_hash(path), "request_ids": ids})
        budget.checkpoint()
    result = {"status": "PASS", "scope": "CONTROL_ONLY_NO_MARKET_RESPONSES", "manifest_sha256": content_hash(manifest),
              "credential_scope": pacer.credential_scope, "controls": proofs}
    write_envelope(directory/"ready.json", CONTROL_READY, result, immutable=True)
    return result


def projected_seconds(reserves: list[int], latency: float, *, multiplier: int = 1) -> float:
    """Mô phỏng sliding61 giây RPM/TPM theo reserve, gồm thời gian response đo được."""
    if type(latency) not in (int, float) or not math.isfinite(latency) or latency < 0 or type(multiplier) is not int or multiplier not in (1, 2):
        raise ValueError("Latency/retry scenario projection không hợp lệ")
    now, minute = 0., []
    for reserve in reserves:
        if type(reserve) is not int or not 0 < reserve <= 8000: raise ValueError("Reserve projection ngoài TPM")
        for _ in range(multiplier):
            minute = [(t, n) for t, n in minute if t > now-61]
            while len(minute) >= 30 or sum(n for _, n in minute)+reserve > 8000:
                now = max(now, minute[0][0]+61.)
                minute = [(t, n) for t, n in minute if t > now-61]
            minute.append((now, reserve))
            now += latency
    return float(now)


def feasibility(manifest: dict[str, Any], ledger: dict[str, Any], controls_proof: dict[str, Any] | None, remaining: float) -> dict[str, Any]:
    """Báo cả804/1348 slot và retry, không coi quota ngày local là quota provider mới."""
    ids = {rid for record in (controls_proof or {}).get("controls", []) for rid in record["request_ids"]}
    rows = [r for r in ledger["requests"] if r["id"] in ids]
    historical = [r for r in ledger["requests"] if r.get("status") == 200 and r.get("model") == "openai/gpt-oss-20b" and r.get("latency_seconds") is not None]
    latencies = [float(r["latency_seconds"]) for r in {r["id"]: r for r in [*historical, *rows]}.values() if r.get("status") == 200]
    latency = float(np.quantile(latencies, .95, method="linear")) if latencies else 90.
    reserves = [manifest["request_bounds"][slot["point_id"]][slot["branch_id"]]["reserved_tokens_upper"] for slot in manifest["layout"]["slots"]]
    active = [n for n in reserves if n]
    maximum = max(active)
    verification = 2*433.95922559686
    dev = projected_seconds(active, latency)+verification
    combined = projected_seconds([*active, *([maximum]*1348)], latency)+2*verification
    all_slots = projected_seconds([n or maximum for n in reserves], latency)+verification
    return {"status": "AWAITING_LIVE_CONTROLS" if not controls_proof else "DEVELOPMENT_FEASIBLE" if dev <= remaining else "INFEASIBLE_DEVELOPMENT",
        "remaining_seconds_at_measurement": remaining, "latency_p95_seconds": latency, "latency_samples": len(latencies),
        "development": {"nominal_slots": 804, "eligible_HTTP_upper_before_anchor_validation": len(active), "policy_bypass_min": len(reserves)-len(active),
                        "projected_seconds": dev, "all804_as_HTTP_stress_seconds": all_slots,
                        "format_repair_every_invocation_seconds": projected_seconds(active, latency, multiplier=2)+verification},
        "conditional_confirmation": {"nominal_slots": 1348, "combined_projected_seconds": combined,
                                     "combined_fits_remaining": combined <= remaining, "future_prompt_cost": "ESTIMATED_AT_CURRENT_MAX_RECHECK_WITH_2025_METADATA_AT_RELEASE"},
        "verification_reserve_seconds": verification, "verification_reserve_basis": "TWO_TIMES_MEASURED_OFFLINE_COLD_PASS_ESTIMATE",
        "daily_quota": "PROVIDER_AUTHORITATIVE_NOT_RESET_NOT_GUARANTEED",
        "transient_retries": "UNBOUNDED_WITH_HARD_RUNTIME_STOP", "projection_is_guarantee": False,
        "confirmation_allowed": False}


def verify_controls(root: Path, manifest: dict[str, Any], snapshot: dict[str, Any], scope: str) -> dict[str, Any]:
    """Cold audit control proof dùng ledger/cache; không đọc key hoặc gọi SDK invoke."""
    if len(scope) != 64 or any(c not in "0123456789abcdef" for c in scope): raise ValueError("Credential scope không hợp lệ")
    directory = root/OUTPUT/"controls"/scope
    ready = read_envelope(directory/"ready.json", CONTROL_READY)
    ledger = read_json(root/"outputs/oos_pilot/api_usage.json")
    signature = content_hash({"manifest_sha256": content_hash(manifest), "credential_scope": scope, "purpose": "CONTROL_ONLY"})
    expected = []
    def reject(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Cold control serializer không được gửi HTTP")
    with httpx.Client(transport=httpx.MockTransport(reject)) as http:
        llm = client(snapshot["protocol"]["decision"]["config"], http, "offline-no-credential")
        contracts = {r["control_id"]: serialization(llm, r)[0] for r in controls(manifest, snapshot)}
    for request in controls(manifest, snapshot):
        path = directory/(request["control_id"]+".json")
        saved = read_envelope(path, CONTROL_VERSION)
        if (saved["request"] != request or saved["status"] != "complete" or saved["run_signature"] != signature
                or saved["contract"] != contracts[request["control_id"]]):
            raise ValueError("Control chưa complete/cùng manifest/serializer")
        slot = {"run_signature": signature, "point_id": "API_PREFLIGHT_V3", "branch_id": "Fact_Anchor" if request["control_id"].startswith("anchored") else "Original",
                "canonical_sha256": content_hash(request), "checkpoint_attempt_id": saved["attempt_id"], "control_id": request["control_id"]}
        parsed, ids, hashes = audit_attempt(ledger, root/OUTPUT/"run/http_cache", slot, request, saved["contract"])
        if parsed != saved["decision"] or ids != saved["request_ids"] or hashes != saved["cache_hashes"]: raise ValueError("Control proof không khớp raw/UUID/body")
        check_control_semantics(request, parsed)
        if any(r.get("credential_scope") != scope for r in ledger["requests"] if r["id"] in ids): raise ValueError("Control khác credential scope")
        expected.append({"path": path.relative_to(root).as_posix(), "sha256": file_hash(path), "request_ids": ids})
    if ready != {"status": "PASS", "scope": "CONTROL_ONLY_NO_MARKET_RESPONSES", "manifest_sha256": content_hash(manifest), "credential_scope": scope, "controls": expected}:
        raise ValueError("Ready receipt khác control bytes/ledger")
    return ready


def release(root: Path, manifest: dict[str, Any], snapshot: dict[str, Any], budget: Any) -> dict[str, Any]:
    """Chỉ release development sau control thật/source/feasibility; không cấp quyền2025."""
    from core.mt_bicl_v3_freeze import MANIFEST
    scopes = sorted((root/OUTPUT/"controls").glob("*/ready.json"))
    if not scopes: raise ValueError("Thiếu control API thật: người dùng chạy scripts/continue_mt_bicl_v3.py")
    proof = verify_controls(root, manifest, snapshot, scopes[-1].parent.name)
    dry = read_envelope(root/OUTPUT/"freeze/dry_run.json", DRY_VERSION)
    if dry["status"] != "PASS" or dry["result"]["complete_slots"] != 804: raise ValueError("Dry-run chưa PASS đủ804 slot")
    now = datetime.now(timezone.utc)
    stop = datetime.fromisoformat("2026-11-05T23:59:59+07:00")
    if now > stop: raise ValueError("Quá mốc release/bắt đầu05/11, không mở development mới")
    profile = feasibility(manifest, read_json(root/"outputs/oos_pilot/api_usage.json"), proof, budget.remaining_seconds())
    if profile["status"] != "DEVELOPMENT_FEASIBLE": raise ValueError("Không đủ quỹ cho development theo preflight")
    result = {"status": "RELEASED_DEVELOPMENT_2023_ONLY", "manifest_sha256": content_hash(manifest),
              "manifest_byte_sha256": file_hash(root/MANIFEST), "source_commit": manifest["source_commit"],
              "control_proof": proof, "dry_run_sha256": file_hash(root/OUTPUT/"freeze/dry_run.json"), "feasibility": profile,
              "created_at": now.isoformat(), "development_allowed": True, "decision_calls_allowed": True,
              "confirmation_allowed": False, "training_allowed": False, "candidate_substitution_allowed": False}
    if (root/RELEASE).exists():
        saved = read_envelope(root/RELEASE, RELEASE_VERSION)
        if saved["manifest_sha256"] != content_hash(manifest): raise ValueError("Release khác manifest v3")
        return saved
    write_envelope(root/RELEASE, RELEASE_VERSION, result, immutable=True)
    return result
