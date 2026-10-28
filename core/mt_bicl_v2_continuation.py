"""Resume một lệnh theo ủy quyền mới: tự preflight credential và phục hồi UUID chưa complete."""

from __future__ import annotations

import base64
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Callable
from uuid import UUID, uuid4

import httpx
from pydantic import ValidationError

from core.groq_pacing import PilotStop
from core.improvement_recovery import ResilientTransport
from core.improvement_transport import SLOT, body_contract
from core.mt_bicl_bank import content_hash
from core.mt_bicl_v2_api_preflight import preflight_request, wire_body
from core.mt_bicl_v2_development import (
    DevelopmentRun, EXTENSION_PATH, SLOT_VERSION, audit_response, normalized_decision, verify_extension,
)
from core.mt_bicl_v2_decision import invoke_decision
from core.mt_bicl_v2_io import read_envelope, write_envelope
from core.mt_bicl_v2_release import git_value
from core.mt_bicl_v21_preparation import file_hash
from core.prior_run_lock import safe_path
from core.research_cohort import read_envelope as read_cached
from core.research_invocation import CURRENT

PATH = Path("docs/plan/week11/development_continuation_v2.json")
VERSION = "mt_bicl_unified_continuation_v2"
PREFLIGHT_VERSION = "mt_bicl_credential_preflight_v2"
EVENT_VERSION = "mt_bicl_continuation_authorization_v2"
CODE = ("core/mt_bicl_v2_continuation.py", "scripts/continue_mt_bicl_development.py", "tests/test_mt_bicl_v2_continuation.py")
DEADLINE = datetime.fromisoformat("2026-11-07T23:59:59+07:00")


def facts(root: Path, extension: dict[str, Any]) -> dict[str, Any]:
    """Amendment vận hành được người dùng yêu cầu; không đổi protocol nghiên cứu hoặc nguồn cũ."""
    return {"version": VERSION, "runner_extension_sha256": file_hash(root/EXTENSION_PATH),
            "run_signature": content_hash(extension), "runtime": extension["runtime"],
            "source_sha256": {n: file_hash(root/n) for n in CODE},
            "user_authorization": "tôi cần khi bị ngắt vì bất kì lý do gì thì chỉ cần chạy 1 lệnh là chạy được tiếp",
            "resume": "AUTO_SAME_UUID_FOR_INCOMPLETE_ONLY_REUSE_VALID_DURABLE_SUCCESS_FIRST",
            "credential": "AUTO_PREFLIGHT_CURRENT_CREDENTIAL_PRESERVE_OLD_PROOFS_AND_LEDGER",
            "quota": "WAIT_PROVIDER_RESET_KEEP_ALL_RESERVES_NO_AUTOMATIC_KEY_ROTATION",
            "complete": "NEVER_REPLAY", "integrity": "STOP_ON_CORRUPT_OR_CHANGED_FROZEN_DATA",
            "physical_duplicate_possible_for_lost_response": True,
            "candidate_weights_prompts_schema_cohort_order_repeats_economics_PIT": "UNCHANGED"}


def prepare(root: Path) -> dict[str, Any]:
    """Khóa mã resume riêng trước khi người dùng chạy, không đọc credential hoặc gọi API."""
    extension, _, _ = verify_extension(root)
    if (root/PATH).exists():
        return verify(root, extension, require_anchor=False)
    commit = git_value(root, "rev-parse", "HEAD")
    git_value(root, "diff", "--exit-code", commit, "--", *CODE)
    for name in CODE:
        git_value(root, "cat-file", "-e", commit+":"+name)
    result = {**facts(root, extension), "source_commit": commit}
    write_envelope(root/PATH, VERSION, result, immutable=True)
    return result


def verify(root: Path, extension: dict[str, Any], *, require_anchor: bool = True) -> dict[str, Any]:
    """Resume không được bỏ qua source/runtime/request/Git gate đã khóa."""
    result = read_envelope(root/PATH, VERSION)
    if result != {**facts(root, extension), "source_commit": result["source_commit"]}:
        raise ValueError("Source/policy resume một lệnh khác bản đã khóa")
    git_value(root, "merge-base", "--is-ancestor", result["source_commit"], "HEAD")
    git_value(root, "diff", "--exit-code", result["source_commit"], "--", *CODE)
    if require_anchor:
        saved = subprocess.run(["git", "show", "HEAD:"+PATH.as_posix()], cwd=root, capture_output=True, check=False)
        if saved.returncode or saved.stdout != (root/PATH).read_bytes():
            raise ValueError("Policy resume chưa neo byte Git HEAD")
    return result


def read_response(cache: Path, row: dict[str, Any], contract: dict[str, Any]) -> tuple[dict[str, Any] | None, bool]:
    """Phân biệt cache chưa được ghi do crash với cache đã đóng dấu nhưng bị mất/sửa."""
    path = safe_path(cache, str(UUID(row["id"]))+".json")
    proof = row.get("durable_response")
    if not path.exists():
        if proof is not None:
            raise ValueError("Mất raw cache đã đóng dấu; không tự bỏ qua integrity")
        return None, False
    checksum = file_hash(path)
    if proof is not None and proof != {"sha256": checksum}:
        raise ValueError("Raw cache bị sửa; không retry thay kết quả")
    raw = read_cached(path)
    if (set(raw) != {"version", "request", "body_base64", "headers"} or raw["version"] != "resilient_invocation_v1"
            or raw["request"] != contract or set(raw["headers"])-{"content-type", "x-request-id"}):
        raise ValueError("Raw cache khác request/schema/header đã khóa")
    body = base64.b64decode(raw["body_base64"], validate=True)
    if hashlib.sha256(body).hexdigest() != (row.get("improvement_audit", {}).get("response") or {}).get("body_sha256"):
        raise ValueError("Raw cache khác HTTP audit")
    try:
        parsed = normalized_decision(json.loads(body)["choices"][0]["message"])
    except (ValueError, KeyError, IndexError, TypeError, ValidationError):
        parsed = None
    return parsed, proof is None


def validate_attempt(ledger: dict[str, Any], slot: dict[str, Any], contract: dict[str, Any], cache: Path) -> list[dict[str, Any]]:
    """Kiểm mọi HTTP của intent, kể cả reserve chưa dispatch, lỗi mạng và response bị mất khi crash."""
    rows = [r for r in ledger["requests"] if r.get("checkpoint_attempt_id") == slot["checkpoint_attempt_id"]]
    for row in rows:
        if (row.get("run_signature") != slot["run_signature"] or row.get("point_id") != slot["point_id"]
                or row.get("branch_id") != slot["branch_id"] or row.get("recovery_policy") != "resilient_invocation_v1"):
            raise ValueError("HTTP khác run/point/branch/UUID đã khóa")
        audit = row.get("improvement_audit")
        if row["status"] == "unknown" and row.get("dispatch_phase") == "reserved" and audit is None:
            continue
        if (type(audit) is not dict or audit.get("audit_version") != "improvement_http_audit_v1"
                or audit.get("slot") != slot or audit.get("request") != contract):
            raise ValueError("HTTP body/audit khác intent, không tự phục hồi dữ liệu sai")
        if row["status"] == 200:
            if type(audit.get("response")) is not dict:
                raise ValueError("HTTP200 thiếu audit response; giữ checkpoint để kiểm integrity")
            read_response(cache, row, contract)
        elif audit.get("response") is None and row["status"] not in ("unknown", "transport_error"):
            raise ValueError("HTTP thiếu response audit")
    return rows


def inspect_prefix(runner: DevelopmentRun, ledger: dict[str, Any], cache: Path) -> list[dict[str, Any]]:
    """Verifier cũ kiểm complete prefix; audit incomplete được kiểm riêng, không sửa ledger thật."""
    rows = ledger["requests"]
    if len({r["id"] for r in rows}) != len(rows):
        raise ValueError("Ledger trùng UUID")
    documents = [read_envelope(runner.path(i), SLOT_VERSION) for i in range(612)]
    incomplete = {r["attempt_id"] for r in documents if r["status"] == "unknown"}
    # Không coi HTTP200 chưa có checkpoint hợp lệ là complete khi kiểm prefix.
    view = {**ledger, "requests": [r for r in rows if r.get("checkpoint_attempt_id") not in incomplete]}
    records = runner.inspect(view, cache)
    for i, record in enumerate(records):
        if record["status"] == "unknown":
            validate_attempt(ledger, runner.dispatch_slot(i, record), runner.plans[i]["http_contract"], cache)
    return records


def finish_durable(runner: DevelopmentRun, ledger: dict[str, Any], cache: Path,
                   save: Callable[[], None]) -> list[dict[str, Any]]:
    """Khôi phục success trước key/API; chỉ hoàn thiện dấu cache còn thiếu khi byte/audit khớp."""
    records = inspect_prefix(runner, ledger, cache)
    for i, record in enumerate(records):
        if record["status"] != "unknown":
            continue
        rows = validate_attempt(ledger, runner.dispatch_slot(i, record), runner.plans[i]["http_contract"], cache)
        success = [r for r in rows if r["status"] == 200]
        if not success:
            continue
        row = success[-1]
        parsed, unstamped = read_response(cache, row, runner.plans[i]["http_contract"])
        if parsed is None:
            continue
        if unstamped:
            before = content_hash(row)
            row["durable_response"] = {"sha256": file_hash(cache/(row["id"]+".json"))}
            ledger.setdefault("continuation_events", []).append({"event": "COMPLETE_UNSTAMPED_CACHE", "request_id": row["id"],
                "previous_row_sha256": before, "new_row_sha256": content_hash(row)})
            save()
        actual, ids = audit_response(runner.root, cache, ledger, runner.dispatch_slot(i, record), runner.plans[i]["http_contract"])
        completed = {**record, "status": "complete", "decision": actual, "request_ids": ids}
        write_envelope(runner.path(i), SLOT_VERSION, completed)
    return inspect_prefix(runner, ledger, cache)


def resume_unknown(runner: DevelopmentRun, ledger: Callable[[], dict[str, Any]], cache: Path,
                   save: Callable[[], None], dispatch: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
                   policy: dict[str, Any], credential_scope: str) -> list[dict[str, Any]]:
    """Theo ủy quyền một lệnh: tự tìm intent dở, reuse cache trước, retry cùng UUID và ghi audit."""
    records = finish_durable(runner, ledger(), cache, save)
    for i, record in enumerate(records):
        if record["status"] != "unknown":
            continue
        slot = runner.dispatch_slot(i, record)
        old = validate_attempt(ledger(), slot, runner.plans[i]["http_contract"], cache)
        authorization = {"policy_sha256": content_hash(policy), "authorization": "USER_AUTHORIZED_SINGLE_COMMAND_RESUME",
            "run_signature": runner.signature, "slot": slot, "credential_scope": credential_scope,
            "previous_http_sha256": {r["id"]: content_hash(r) for r in old},
            "created_at": datetime.now(timezone.utc).isoformat()}
        write_envelope(runner.directory/"continuation_authorizations"/(str(uuid4())+".json"), EVENT_VERSION, authorization, immutable=True)
        parsed = dispatch(deepcopy(runner.requests[i]), slot)
        current = {r["id"]: content_hash(r) for r in ledger()["requests"]}
        if any(current.get(rid) != checksum for rid, checksum in authorization["previous_http_sha256"].items()):
            raise ValueError("Resume đã sửa HTTP/reserve cũ; giữ unknown")
        actual, ids = audit_response(runner.root, cache, ledger(), slot, runner.plans[i]["http_contract"])
        if parsed != actual:
            raise ValueError("Parsed resume khác raw response")
        write_envelope(runner.path(i), SLOT_VERSION, {**record, "status": "complete", "decision": actual, "request_ids": ids})
    return runner.inspect(ledger(), cache)


class ContinuationTransport(ResilientTransport):
    """Giữ transport cũ, bổ sung chờ quota ngày và bỏ cache response sai schema để format repair."""

    def _cached(self, request: httpx.Request) -> httpx.Response | None:
        """Cache thành công hợp lệ luôn reuse; cache lỗi định dạng giữ audit rồi cho phép repair."""
        response = super()._cached(request)
        if response is None:
            return None
        try:
            normalized_decision(response.json()["choices"][0]["message"])
            return response
        except (ValueError, KeyError, IndexError, TypeError, ValidationError):
            response.close()
            budget = CURRENT.get()
            if budget is not None:
                for row in self.pacer.state["requests"]:
                    if row.get("checkpoint_attempt_id") == budget.checkpoint_attempt_id and row["status"] == 200:
                        self.used_cache.add((budget.invocation_id, row["id"]))
            print("[Phục hồi] Response cũ sai schema; giữ audit và tiếp tục format repair.", flush=True)
            return None

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Quota ngày có mốc reset thì chờ; auth/config/integrity vẫn báo rõ để sửa bên ngoài."""
        while True:
            if datetime.now(timezone.utc) > DEADLINE:
                raise ValueError("Đã đến mốc khóa dữ liệu, giữ checkpoint INCOMPLETE")
            try:
                return super().handle_request(request)
            except PilotStop:
                stop = self.pacer.state.get("last_stop") or {}
                until = stop.get("resume_not_before_utc")
                if stop.get("reason") != "PROVIDER_DAILY_QUOTA" or not until:
                    raise
                reset = datetime.fromisoformat(until)
                if reset > DEADLINE:
                    raise PilotStop("Quota reset sau mốc khóa dữ liệu; giữ INCOMPLETE") from None
                delay = max(1., reset.timestamp()-self.pacer.clock())
                print(f"[Quota] Hết quota ngày; tự chờ {delay:.0f} giây rồi tiếp tục cùng UUID.", flush=True)
                self._wait(delay)


def credential_preflight(directory: Path, manifest: dict[str, Any], run_signature: str,
                         pacer: Any, llm: Any) -> dict[str, Any]:
    """Mỗi credential có control proof riêng; đổi key tự preflight, không ghi đè proof/key cũ."""
    scope = pacer.credential_scope
    path, cache = directory/(scope+".json"), directory/"http_cache"
    request = preflight_request()
    contract = body_contract(wire_body(llm, request))
    binding = {"run_signature": run_signature, "manifest_sha256": content_hash(manifest),
               "credential_scope": scope, "http_contract": contract}
    saved = read_envelope(path, PREFLIGHT_VERSION) if path.exists() else {
        "binding": binding, "attempt_id": str(uuid4()), "status": "unknown", "decision": None, "request_ids": []}
    if saved["binding"] != binding:
        raise ValueError("Preflight credential khác run/body đã khóa")
    control_signature = content_hash({"credential_preflight": binding})
    slot = {"run_signature": control_signature, "point_id": "API_PREFLIGHT", "branch_id": "credential_preflight",
            "canonical_sha256": content_hash(request), "checkpoint_attempt_id": saved["attempt_id"]}
    rows = validate_attempt(pacer.state, slot, contract, cache)
    if any(r.get("credential_scope") != scope for r in rows):
        raise ValueError("HTTP preflight khác credential scope")
    success = [r for r in rows if r["status"] == 200]
    parsed = None
    if success:
        parsed, unstamped = read_response(cache, success[-1], contract)
        if parsed is not None and unstamped:
            success[-1]["durable_response"] = {"sha256": file_hash(cache/(success[-1]["id"]+".json"))}
            pacer.save()
    if saved["status"] == "PASS" and parsed is None:
        raise ValueError("Preflight PASS thiếu raw response hợp lệ")
    if parsed is None:
        write_envelope(path, PREFLIGHT_VERSION, saved)
        token = SLOT.set(slot)
        try:
            invoke_decision(llm, request, attempt_id=saved["attempt_id"], run_signature=control_signature, branch_id="credential_preflight")
        finally:
            SLOT.reset(token)
    actual, ids = audit_response(directory, cache, pacer.state, slot, contract)
    if saved["status"] == "PASS" and (saved["decision"] != actual or saved["request_ids"] != ids):
        raise ValueError("Preflight credential khác raw/cache/ledger")
    result = {**saved, "status": "PASS", "decision": actual, "request_ids": ids}
    write_envelope(path, PREFLIGHT_VERSION, result)
    return result
