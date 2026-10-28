"""Retry tường minh request429 cùng UUID; giữ nguyên runner và mọi receipt đã freeze."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import subprocess
from typing import Any, Callable
from uuid import UUID, uuid4

from core.mt_bicl_bank import content_hash
from core.mt_bicl_v2_api_preflight import verify_live_preflight
from core.mt_bicl_v2_development import DevelopmentRun, EXTENSION_PATH, RUN, SLOT_VERSION, audit_response, verify_extension
from core.mt_bicl_v2_io import read_envelope, write_envelope
from core.mt_bicl_v2_release import git_value
from core.mt_bicl_v21_preparation import file_hash

PATH = Path("docs/plan/week11/development_recovery_v2.json")
VERSION = "mt_bicl_rejected_request_recovery_v2"
AUTH_VERSION = "mt_bicl_rejected_request_authorization_v2"
CODE = ("core/mt_bicl_v2_recovery.py", "scripts/resume_mt_bicl_development.py", "tests/test_mt_bicl_v2_recovery.py")


def facts(root: Path, extension: dict[str, Any]) -> dict[str, Any]:
    """Chỉ bổ sung vận hành sau partial run; không đổi source/request hoặc phương pháp cũ."""
    return {"version": VERSION, "runner_extension_sha256": file_hash(root/EXTENSION_PATH),
            "run_signature": content_hash(extension), "runtime": extension["runtime"],
            "source_sha256": {n: file_hash(root/n) for n in CODE},
            "policy": "EXPLICIT_UUID_ALL_HTTP_429_AUDITED_NO_RESPONSE_RETRY_SAME_UUID_AND_BODY",
            "reserve": "PRESERVE_ALL_OLD_REQUESTS_AND_RESERVES_APPEND_NEW_HTTP",
            "complete": "NEVER_REPLAY", "other_unknown": "STOP_NO_AUTOMATIC_RETRY",
            "method_candidate_cohort_order_prompts_schema_weights": "UNCHANGED",
            "scope": "OPERATIONAL_RECOVERY_AFTER_PARTIAL_DEVELOPMENT_NOT_NEW_EXPERIMENT"}


def prepare(root: Path) -> dict[str, Any]:
    """Khóa nguồn phục hồi riêng sau đối soát parent và preflight thật; không đọc key/API."""
    extension, manifest, _ = verify_extension(root)
    verify_live_preflight(root, manifest)
    if (root/PATH).exists():
        return verify(root, extension=extension, require_anchor=False)
    commit = git_value(root, "rev-parse", "HEAD")
    git_value(root, "diff", "--exit-code", commit, "--", *CODE)
    for name in CODE:
        git_value(root, "cat-file", "-e", commit+":"+name)
    result = {**facts(root, extension), "source_commit": commit}
    write_envelope(root/PATH, VERSION, result, immutable=True)
    return result


def verify(root: Path, *, extension: dict[str, Any], require_anchor: bool = True) -> dict[str, Any]:
    """Recovery không nới gate source/runtime/Git của runner đã khóa."""
    result = read_envelope(root/PATH, VERSION)
    if result != {**facts(root, extension), "source_commit": result["source_commit"]}:
        raise ValueError("Nguồn/policy phục hồi khác bản đã khóa")
    git_value(root, "merge-base", "--is-ancestor", result["source_commit"], "HEAD")
    git_value(root, "diff", "--exit-code", result["source_commit"], "--", *CODE)
    if require_anchor:
        saved = subprocess.run(["git", "show", "HEAD:"+PATH.as_posix()], cwd=root, capture_output=True, check=False)
        if saved.returncode or saved.stdout != (root/PATH).read_bytes():
            raise ValueError("Recovery chưa neo byte Git HEAD")
    return result


def eligible(runner: DevelopmentRun, ledger: dict[str, Any], cache: Path,
             attempt_id: str) -> tuple[int, dict[str, Any], list[dict[str, Any]]]:
    """Chỉ HTTP429 đã audit đúng slot/body và không có response; không suy từ lỗi mạng."""
    UUID(attempt_id)
    records = runner.inspect(ledger, cache)
    found = [(i, r) for i, r in enumerate(records) if r["attempt_id"] == attempt_id]
    if len(found) != 1:
        raise ValueError("UUID không thuộc đúng một intent của run")
    i, record = found[0]
    if record["status"] == "complete":
        return i, record, []
    if record["status"] != "unknown" or sum(r["status"] == "unknown" for r in records) != 1:
        raise ValueError("Chỉ phục hồi đúng unknown hiện tại, không chọn lại slot")
    rows = [r for r in ledger["requests"] if r.get("checkpoint_attempt_id") == attempt_id]
    slot = runner.dispatch_slot(i, record)
    for row in rows:
        audit = row.get("improvement_audit") or {}
        response = audit.get("response")
        if (row["status"] != 429 or row.get("recovery_policy") != "resilient_invocation_v1"
                or row.get("dispatch_phase") != "audited" or row.get("run_signature") != runner.signature
                or row.get("point_id") != slot["point_id"] or row.get("branch_id") != slot["branch_id"]
                or audit.get("audit_version") != "improvement_http_audit_v1" or audit.get("slot") != slot
                or audit.get("request") != runner.plans[i]["http_contract"] or type(response) is not dict
                or response.get("message_sha256") is not None or row.get("durable_response") is not None
                or (cache/(str(UUID(row["id"]))+".json")).exists()):
            raise ValueError("Không chứng minh được toàn bộ HTTP bị429 từ chối; giữ unknown/reserve")
    if not rows:
        raise ValueError("Unknown chưa có HTTP429 chứng minh từ chối; không retry")
    return i, record, rows


def retry_rejected(runner: DevelopmentRun, ledger: Callable[[], dict[str, Any]], cache: Path,
                   attempt_id: str, dispatch: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
                   recovery: dict[str, Any]) -> dict[str, Any]:
    """Một lệnh người dùng tường minh; cùng UUID/body và giữ mọi row/reserve đã có."""
    before = ledger()
    i, record, rejected = eligible(runner, before, cache, attempt_id)
    if record["status"] == "complete":
        return record
    baseline = {r["id"]: content_hash(r) for r in before["requests"]}
    authorization = {"run_signature": runner.signature, "attempt_id": attempt_id, "slot_index": i,
                     "canonical_sha256": runner.plans[i]["canonical_sha256"], "recovery_sha256": content_hash(recovery),
                     "created_at": datetime.now(timezone.utc).isoformat(), "authorization": "USER_EXPLICIT_RETRY_REJECTED_UUID_COMMAND",
                     "rejected_request_ids": [r["id"] for r in rejected], "baseline_request_sha256": baseline}
    write_envelope(runner.directory/"recovery_authorizations"/(str(uuid4())+".json"), AUTH_VERSION, authorization, immutable=True)
    parsed = dispatch(deepcopy(runner.requests[i]), runner.dispatch_slot(i, record))
    after = ledger()
    by_id = {r["id"]: content_hash(r) for r in after["requests"]}
    if any(by_id.get(rid) != checksum for rid, checksum in baseline.items()):
        raise ValueError("Ledger/reserve lịch sử bị sửa; giữ unknown")
    actual, ids = audit_response(runner.root, cache, after, runner.dispatch_slot(i, record), runner.plans[i]["http_contract"])
    if actual != parsed:
        raise ValueError("Parsed retry khác raw response; giữ unknown")
    completed = {**record, "status": "complete", "decision": deepcopy(parsed), "request_ids": ids}
    write_envelope(runner.path(i), SLOT_VERSION, completed)
    runner.progress(runner.inspect(after, cache))
    return completed
