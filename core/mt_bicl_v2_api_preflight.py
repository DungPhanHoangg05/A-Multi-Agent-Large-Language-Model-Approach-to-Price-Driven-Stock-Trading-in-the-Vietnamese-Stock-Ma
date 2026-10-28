"""Preflight serializer/transport offline và cổng API do người dùng chạy sau manifest."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import base64
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from uuid import uuid4

import httpx
from langchain_core.messages import HumanMessage
from langchain_groq import ChatGroq

from agents.decision_agent import TradeDecisionOutput
from core.bayesian_memory import read_json
from core.groq_pacing import GroqPacer, MODEL_LIMITS, request_budget, tokenizer_cached
from core.improvement_transport import ImprovementTransport, body_contract, validate_client
from core.mt_bicl_bank import content_hash
from core.mt_bicl_v2_adapter import VARIANTS
from core.mt_bicl_v2_decision import DecisionSession, invoke_decision
from core.mt_bicl_v2_integration import OfflineDecisionFixture
from core.mt_bicl_v2_io import read_envelope, write_envelope
from core.mt_bicl_v2_release import LEDGER, RELEASE_PATH, git_value
from core.mt_bicl_v2_run_manifest import CODE, MANIFEST_PATH, MANIFEST_VERSION, OUTPUT, collect
from core.mt_bicl_v21_preparation import file_hash

RECEIPT_PATH = Path("docs/plan/week11/development_preflight_v2.json")
RECEIPT_VERSION = "mt_bicl_development_preflight_v2"
DRY_VERSION = "mt_bicl_development_dry_run_v2"
LIVE_VERSION = "mt_bicl_live_api_preflight_v2"


def client(decision: dict[str, Any], http: httpx.Client, key: str) -> ChatGroq:
    """Dùng đúng constructor/options đã freeze, SDK retry=0, không fallback model."""
    models = decision["signal_config"]["models"]
    llm = ChatGroq(model=models["agent_llm_model"], temperature=models["agent_llm_temperature"],
                   max_tokens=models["agent_llm_max_tokens"], max_retries=0, api_key=key,
                   http_client=http, service_tier=decision["service_tier"], **decision["client_options"]["agent"])
    llm.temperature = models["agent_llm_temperature"]
    validate_client(llm, "agent", models)
    return llm


def wire_body(llm: ChatGroq, request: dict[str, Any]) -> dict[str, Any]:
    """Serializer SDK thật; không HTTP, header hoặc credential trong kết quả."""
    messages, params = llm._create_message_dicts([HumanMessage(content=request["messages"][0]["content"])], None)
    structured = llm.with_structured_output(TradeDecisionOutput, method="json_schema", include_raw=True)
    raw = structured.steps[0].steps__["raw"]
    return {"messages": messages, **params, "response_format": raw.kwargs["response_format"]}


def manifest_facts(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    """Bind toàn612 canonical request/HTTP body, teacher/student và upstream thật đã kiểm."""
    if not tokenizer_cached():
        raise ValueError("Thiếu tokenizer cache đã xác minh; chưa gọi API")
    decision = data["release"]["decision"]
    records = []
    def reject(request: httpx.Request) -> httpx.Response:
        """Chặn tuyệt đối network trong bước serialize manifest."""
        raise AssertionError("Serialize offline không được gửi HTTP")
    with httpx.Client(transport=httpx.MockTransport(reject)) as http:
        llm = client(decision, http, "offline-no-credential")
        for slot in data["layout"]["slots"]:
            key = (slot["point_id"], slot["repeat_index"], slot["branch_id"])
            request = data["requests"][key]
            body = wire_body(llm, request)
            reserve = request_budget(body)
            if reserve > MODEL_LIMITS[request["model"]]["tpm"]:
                raise ValueError("Request vượt reserve TPM đã khóa")
            original = data["requests"][(slot["point_id"], slot["repeat_index"], "Original")]
            reuse = slot["branch_id"] not in ("Original", "Original_duplicate") and request == original
            records.append({**slot, "canonical_sha256": content_hash(request), "http_contract": body_contract(body),
                            "reserved_tokens": reserve, "shared_off_eligible": reuse})
    return {"version": MANIFEST_VERSION, "phase": "development2023", "status": "FROZEN_BEFORE_FIRST_RESPONSE",
            "release": {"path": RELEASE_PATH.as_posix(), "sha256": file_hash(root/RELEASE_PATH)},
            "source_sha256": {n: file_hash(root/n) for n in CODE}, "runtime": data["release"]["runtime"],
            "candidate": deepcopy(data["release"]["candidate"]),
            "teacher_student_identity_sha256": data["release"]["integration_identity_sha256"],
            "decision": deepcopy(decision), "layout": deepcopy(data["layout"]), "requests": records,
            "upstream": deepcopy(data["upstream"]), "run_output": OUTPUT.as_posix(), "ledger_path": LEDGER,
            "offline_branches": ["Numeric_only", "Teacher_only"],
            "reuse_rule": "EXACT_CANONICAL_POINT_REPEAT_BODY_MODEL_OPTIONS_SCHEMA_AND_DURABLE_ORIGINAL_ONLY",
            "unknown_rule": "STOP_KEEP_UUID_RESERVE_NO_AUTOMATIC_REPLAY_OR_CASH",
            "primary_slots": 360, "repeat_slots": 252, "primary_N": 60,
            "HTTP_attempts_are_not_scientific_slots": True,
            "live_api_preflight_required_before_primary": True,
            "confirmation_allowed": False, "training_allowed": False, "refit_allowed": False}


def dry_run(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    """Chạy đủ primary/repeat qua journal thật với reports thật, Decision fixture tách namespace."""
    total, reused, duplicates, max_prompt, max_prefix = 0, 0, 0, 0, 0
    journals = {}
    for block in data["layout"]["blocks"]:
        pid, repeat = block["point_id"], block["repeat_index"]
        shared = data["shared"][pid]
        before = content_hash(shared)
        variants = deepcopy(data["variants"][pid])
        if repeat:
            variants["Original_duplicate"] = deepcopy(variants["Original"])
        branches = {n: variants[n] for n in block["order"]}
        path = root/OUTPUT/"offline_dry_run"/str(repeat)/(pid+".json")
        binding = {"scope": "OFFLINE_FIXTURE_NOT_MARKET_ACTION", "point_id": pid,
                   "repeat_index": repeat, "shared_sha256": before,
                   "release_sha256": file_hash(root/RELEASE_PATH)}
        fixture = OfflineDecisionFixture()
        saved = DecisionSession(path, binding).run(deepcopy(shared), branches, block["order"], data["inputs"]["protocol"], fixture, repeat=repeat)
        class RejectFixture:
            """Cold replay phải dùng durable output, không invoke lần nữa."""
            def with_structured_output(self, *args: Any, **kwargs: Any) -> Any:
                raise AssertionError("Cold replay đã gọi lại Decision")
        DecisionSession(path, binding).run(deepcopy(shared), branches, block["order"], data["inputs"]["protocol"], RejectFixture(), repeat=repeat)
        for name, record in saved["branches"].items():
            if record["request"] != data["requests"][(pid, repeat, name)]:
                raise ValueError("Request dry-run khác manifest")
            total += 1
            reused += int(record["shared_off_from"] == "Original")
            duplicates += int(name == "Original_duplicate" and record["shared_off_from"] is None)
            max_prompt = max(max_prompt, len(record["request"]["messages"][0]["content"]))
            max_prefix = max(max_prefix, len(branches[name]["prefix"]))
        if content_hash(shared) != before:
            raise ValueError("Dry-run mutate upstream chung")
        journals[path.relative_to(root/OUTPUT).as_posix()] = file_hash(path)
    if total != 612 or duplicates != 36 or max_prompt >= 6500 or max_prefix > 600:
        raise ValueError("Dry-run thiếu slot/duplicate hoặc vượt token contract")
    return {"status": "PASS", "scope": "REAL_VERIFIED_REPORTS_FROZEN_STUDENT_P_DECISION_FIXTURE",
            "slots": total, "shared_off": reused, "fixture_invocations": total-reused,
            "duplicate_invocations": duplicates, "max_prompt_chars": max_prompt, "max_prefix_chars": max_prefix,
            "journals_sha256": journals, "real_api_calls": 0, "new_upstream_calls": 0,
            "student_forward_calls": 0, "cold_replay": "PASS", "llm_semantic_behavior": "NOT_RUN"}


def offline_wire_preflight(data: dict[str, Any]) -> dict[str, Any]:
    """Bảy request qua SDK/retry/pacer/audit thật, inner MockTransport không có network."""
    results = []
    decision = data["release"]["decision"]
    names = [*VARIANTS, "Original_duplicate"]
    now = [1800000000.]
    with TemporaryDirectory() as tmp:
        pacer = GroqPacer(Path(tmp)/"ledger.json", policy="request_admission_v2", clock=lambda: now[0])
        expected: list[dict[str, Any]] = []
        def respond(request: httpx.Request) -> httpx.Response:
            """Kiểm byte body trước fixture response; không ghi header vào bằng chứng."""
            contract = body_contract(json.loads(request.content))
            if contract != expected[-1]:
                raise ValueError("HTTP body thực khác serializer đã freeze")
            now[0] += 61.
            parsed = OfflineDecisionFixture().invoke("")["parsed"]
            return httpx.Response(200, json={"id": "offline-fixture", "object": "chat.completion",
                "created": 0, "model": decision["signal_config"]["models"]["agent_llm_model"],
                "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": json.dumps(parsed, ensure_ascii=False)}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}})
        with httpx.Client(transport=ImprovementTransport(pacer, httpx.MockTransport(respond))) as http:
            llm = client(decision, http, "offline-no-credential")
            validate_client(llm, "agent", decision["signal_config"]["models"], online=True)
            for name in names:
                base = "Original" if name == "Original_duplicate" else name
                key = max((k for k in data["requests"] if k[2] == base and k[1] == 0),
                          key=lambda k: len(data["requests"][k]["messages"][0]["content"]))
                request = data["requests"][key]
                expected.append(body_contract(wire_body(llm, request)))
                invoke_decision(llm, request, branch_id=name)
                record = pacer.state["requests"][-1]
                if record["status"] != 200 or record["improvement_audit"]["request"] != expected[-1]:
                    raise ValueError("Preflight thiếu ledger/audit thành công")
                results.append({"branch_id": name, "point_id": key[0], "http_contract": expected[-1],
                                "status": "PASS", "reserved_tokens": record["reserved_tokens"]})
    return {"status": "PASS", "scope": "SDK_RETRY_PACER_AUDIT_MOCK_HTTP_ONLY", "mock_http_calls": len(results),
            "real_api_calls": 0, "tokenizer_cached": True, "limits": deepcopy(MODEL_LIMITS), "requests": results}


def prepare(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Freeze immutable sau dry-run; ledger tài khoản/ngân sách W10 không bị ghi hoặc reset."""
    if (root/MANIFEST_PATH).exists() or (root/RECEIPT_PATH).exists():
        return verify(root, require_anchor=False)
    data = collect(root)
    before = file_hash(root/LEDGER)
    facts = manifest_facts(root, data)
    commit = git_value(root, "rev-parse", "HEAD")
    for name in CODE:
        tracked = git_value(root, "show", commit+":"+name)
        if tracked != (root/name).read_text(encoding="utf-8").strip():
            raise ValueError("Phải commit source W11 trước freeze: "+name)
    if any(p.exists() for p in (root/OUTPUT/"primary", root/OUTPUT/"repeats", root/OUTPUT/"live_api_preflight.json")):
        raise ValueError("Đã có run/API output trước manifest, không reseal")
    dry = dry_run(root, data)
    wire = offline_wire_preflight(data)
    if file_hash(root/LEDGER) != before:
        raise ValueError("Bước offline đã thay ledger tài khoản")
    manifest = {**facts, "source_commit": commit}
    receipt = {"status": "OFFLINE_PASS_AWAITING_USER_LIVE_API_PREFLIGHT", "manifest_payload_sha256": content_hash(manifest),
               "source_sha256": facts["source_sha256"], "dry_run": dry, "wire_preflight": wire,
               "ledger_before_after_sha256": before, "real_api_calls": 0,
               "live_api_preflight": "NOT_RUN_USER_EXECUTES_BEFORE_PRIMARY",
               "created_at": datetime.now(timezone.utc).isoformat()}
    write_envelope(root/MANIFEST_PATH, MANIFEST_VERSION, manifest, immutable=True)
    write_envelope(root/RECEIPT_PATH, RECEIPT_VERSION, receipt, immutable=True)
    return manifest, receipt


def verify(root: Path, *, require_anchor: bool = True) -> tuple[dict[str, Any], dict[str, Any]]:
    """Cold verifier tái dựng lịch/request từ nguồn; receipt self-hash không thay chứng cứ Git."""
    manifest = read_envelope(root/MANIFEST_PATH, MANIFEST_VERSION)
    receipt = read_envelope(root/RECEIPT_PATH, RECEIPT_VERSION)
    if require_anchor:
        import subprocess
        for relative in (MANIFEST_PATH, RECEIPT_PATH):
            saved = subprocess.run(["git", "show", "HEAD:"+relative.as_posix()], cwd=root, capture_output=True, check=False)
            if saved.returncode or saved.stdout != (root/relative).read_bytes():
                raise ValueError("Manifest/receipt W11 chưa neo byte Git HEAD")
    data = collect(root)
    if manifest != {**manifest_facts(root, data), "source_commit": manifest["source_commit"]}:
        raise ValueError("Manifest khác source/runtime/cohort/order/repeat/upstream/request đã khóa")
    git_value(root, "merge-base", "--is-ancestor", manifest["source_commit"], "HEAD")
    git_value(root, "diff", "--exit-code", manifest["source_commit"], "--", *CODE)
    if (receipt["manifest_payload_sha256"] != content_hash(manifest) or receipt["source_sha256"] != manifest["source_sha256"]
            or receipt["status"] != "OFFLINE_PASS_AWAITING_USER_LIVE_API_PREFLIGHT" or receipt["real_api_calls"] != 0
            or receipt["live_api_preflight"] != "NOT_RUN_USER_EXECUTES_BEFORE_PRIMARY"):
        raise ValueError("Receipt không đúng phạm vi offline")
    for name, checksum in receipt["dry_run"]["journals_sha256"].items():
        if file_hash(root/OUTPUT/name) != checksum:
            raise ValueError("Journal dry-run bị sửa/mất: "+name)
    if dry_run(root, data) != receipt["dry_run"] or offline_wire_preflight(data) != receipt["wire_preflight"]:
        raise ValueError("Dry-run/serializer/transport không tái lập đúng receipt")
    return manifest, receipt


def live_preflight(root: Path, env_file: Path) -> dict[str, Any]:
    """Chỉ CLI tường minh do người dùng chạy; không gọi cohort, upstream hoặc train."""
    import os
    from dotenv import dotenv_values
    from core.improvement_recovery import ResilientPacer, ResilientTransport
    from core.improvement_transport import SLOT
    from core.prior_run_lock import PriorRunLock

    manifest, _ = verify(root)
    signature = content_hash(manifest)
    path = root/OUTPUT/"live_api_preflight.json"
    ledger_path = root/LEDGER
    with PriorRunLock(root/OUTPUT, signature), PriorRunLock(ledger_path.parent/(ledger_path.name+".lock"), "shared-account-ledger-v2"):
        if path.exists():
            saved = read_envelope(path, LIVE_VERSION)
            if saved["manifest_sha256"] != signature or saved["status"] != "PASS":
                raise ValueError("API preflight unknown/khác identity; giữ UUID/reserve, không tự replay")
            verify_live_preflight(root, manifest)
            return saved
        deadline = datetime.fromisoformat("2026-11-05T23:59:59+07:00")
        if datetime.now(timezone.utc) > deadline:
            raise ValueError("Đã quá hạn mở run development, ghi NOT_RUN")
        # Credential chỉ đọc sau manifest/receipt/Git/source/ledger cold-check đã PASS.
        key = dotenv_values(env_file).get("GROQ_API_KEY") or os.environ.get("GROQ_API_KEY", "")
        if not key:
            raise ValueError("Thiếu GROQ_API_KEY; chưa có HTTP")
        pacer = ResilientPacer(root/LEDGER, credential=key, amendment_sha256=signature, policy="request_admission_v2")
        attempt = str(uuid4())
        request = preflight_request()
        slot = {"run_signature": signature, "point_id": "API_PREFLIGHT", "branch_id": "api_preflight", "checkpoint_attempt_id": attempt}
        with httpx.Client(transport=ResilientTransport(pacer, root/OUTPUT/"preflight_http_cache"), timeout=90.) as http:
            llm = client(manifest["decision"], http, key)
            contract = body_contract(wire_body(llm, request))
            saved = {"status": "unknown", "manifest_sha256": signature, "slot": slot,
                     "http_contract": contract, "request": request, "request_ids": [], "decision": None}
            write_envelope(path, LIVE_VERSION, saved)
            token = SLOT.set(slot)
            try:
                parsed = invoke_decision(llm, request, attempt_id=attempt, run_signature=signature, branch_id="api_preflight")
            finally:
                SLOT.reset(token)
            records = [r for r in pacer.state["requests"] if r.get("checkpoint_attempt_id") == attempt]
            if not records or records[-1]["status"] != 200 or any(r.get("improvement_audit", {}).get("request") != contract for r in records):
                raise ValueError("API preflight thiếu HTTP/schema/model/options đúng identity")
            saved.update(status="PASS", decision=parsed, request_ids=[r["id"] for r in records])
            write_envelope(path, LIVE_VERSION, saved)
    verify_live_preflight(root, manifest)
    return saved


def preflight_request() -> dict[str, Any]:
    """Control cố định không dùng cutoff, nhãn, báo cáo hoặc action của cohort."""
    return {"point_id": "API_PREFLIGHT", "repeat_index": 0,
            "messages": [{"role": "user", "content": "Kiểm tra giao thức JSON, không dự báo thị trường. Trả một TradeDecisionOutput hợp lệ: decision SHORT, forecast_horizon T+2.5, confidence Thấp, risk_reward_ratio 1.0; ba trường evidence_for/evidence_against/justification giải thích đây chỉ là kiểm tra API. SHORT nghĩa là giữ tiền mặt, không mở bán khống."}]}


def verify_live_preflight(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    """Cổng dùng trước primary: không nhận receipt offline như API PASS hoặc đổi UUID."""
    saved = read_envelope(root/OUTPUT/"live_api_preflight.json", LIVE_VERSION)
    if saved["status"] != "PASS" or saved["manifest_sha256"] != content_hash(manifest):
        raise ValueError("Cần API preflight PASS đúng manifest trước primary")
    slot = saved["slot"]
    request = preflight_request()
    def reject(request: httpx.Request) -> httpx.Response:
        """Verifier live receipt vẫn tuyệt đối không gọi HTTP."""
        raise AssertionError("Cold verify không được HTTP")
    with httpx.Client(transport=httpx.MockTransport(reject)) as http:
        llm = client(manifest["decision"], http, "offline-no-credential")
        expected = body_contract(wire_body(llm, request))
    if (saved["request"] != request or saved["http_contract"] != expected
            or slot["run_signature"] != content_hash(manifest) or slot["point_id"] != "API_PREFLIGHT"
            or slot["branch_id"] != "api_preflight"):
        raise ValueError("API preflight khác control request/manifest/model/options")
    rows = [r for r in read_json(root/LEDGER)["requests"] if r.get("checkpoint_attempt_id") == slot["checkpoint_attempt_id"]]
    if (not rows or [r["id"] for r in rows] != saved["request_ids"] or rows[-1]["status"] != 200
            or any(r.get("run_signature") != slot["run_signature"] or r.get("point_id") != "API_PREFLIGHT"
                   or r.get("branch_id") != "api_preflight" or r.get("improvement_audit", {}).get("slot") != slot
                   or r["improvement_audit"]["request"] != saved["http_contract"] for r in rows)):
        raise ValueError("API preflight khác ledger/UUID/body đã khóa")
    TradeDecisionOutput.model_validate(saved["decision"], strict=True)
    last = rows[-1]
    cache = root/OUTPUT/"preflight_http_cache"/(last["id"]+".json")
    if last.get("durable_response") != {"sha256": file_hash(cache)}:
        raise ValueError("API preflight thiếu raw response durable đúng hash")
    from core.improvement_transport import verify_attempt_audit
    from core.research_cohort import read_envelope as read_cached
    raw = read_cached(cache)
    body = base64.b64decode(raw["body_base64"], validate=True)
    if (raw["request"] != expected or hashlib.sha256(body).hexdigest() != last["improvement_audit"]["response"]["body_sha256"]):
        raise ValueError("Raw API preflight khác request/HTTP response")
    message = json.loads(body)["choices"][0]["message"]
    parsed = TradeDecisionOutput.model_validate_json(message["content"], strict=True).model_dump()
    if parsed != saved["decision"]:
        raise ValueError("Decision preflight khác raw response đã lưu")
    verify_attempt_audit({"requests": rows}, slot, expected=expected, raw_message={"content": message["content"], "tool_calls": []})
    return saved
