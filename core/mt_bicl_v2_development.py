"""Runner development giữ manifest W11, ledger/cache durable và dừng unknown khi resume."""

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

from agents.decision_agent import TradeDecisionOutput, _normalize_structured_result
from core.bayesian_memory import read_json
from core.improvement_transport import SLOT, body_contract, verify_attempt_audit
from core.mt_bicl_bank import content_hash
from core.mt_bicl_v2_api_preflight import (
    LIVE_VERSION, RECEIPT_PATH, RECEIPT_VERSION, client, preflight_request,
    verify_live_preflight, wire_body,
)
from core.mt_bicl_v2_decision import JOURNAL_VERSION, invoke_decision
from core.mt_bicl_v2_io import read_envelope, write_envelope
from core.mt_bicl_v2_release import LEDGER, git_value, verify_release
from core.mt_bicl_v2_run_manifest import MANIFEST_PATH, MANIFEST_VERSION, OUTPUT
from core.mt_bicl_v21_preparation import file_hash
from core.prior_run_lock import PriorRunLock, safe_path
from core.research_cohort import read_envelope as read_cached
from core.research_input_lock import runtime_identity

EXTENSION_PATH = Path("docs/plan/week11/development_runner_v2.json")
EXTENSION_VERSION = "mt_bicl_development_runner_v2"
REQUEST_VERSION = "mt_bicl_development_requests_v2"
SLOT_VERSION = "mt_bicl_development_slot_v2"
RUN_VERSION = "mt_bicl_development_identity_v2"
PROGRESS_VERSION = "mt_bicl_development_progress_v2"
RUN = OUTPUT/"run"
CODE = ("core/mt_bicl_v2_development.py", "scripts/run_mt_bicl_development.py",
        "tests/test_mt_bicl_v2_development.py")
LOCK = OUTPUT/"operations"
PARENT_SHA256 = "eb154447af175cc740fea5fd5602fcc39cba33e5cbe128689539ad04bda05561"
PARENT_RECEIPT_SHA256 = "60e9c5ee3cc0eed87b78bc8c75b49eb77b6a54209516b9b63cb3bba75d4b6abb"


def verify_parent(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Đối soát gate đã PASS bằng hash/runtime/Git; không chạy lại612 fixture và bảy mock HTTP."""
    if file_hash(root/MANIFEST_PATH) != PARENT_SHA256 or file_hash(root/RECEIPT_PATH) != PARENT_RECEIPT_SHA256:
        raise ValueError("Parent manifest/receipt khác byte W11-01 đã khóa")
    for relative in (MANIFEST_PATH, RECEIPT_PATH):
        anchored = subprocess.run(["git", "show", "HEAD:"+relative.as_posix()], cwd=root, capture_output=True, check=False)
        if anchored.returncode or anchored.stdout != (root/relative).read_bytes():
            raise ValueError("Parent chưa neo byte trong Git HEAD")
    release = verify_release(root)
    manifest = read_envelope(root/MANIFEST_PATH, MANIFEST_VERSION)
    receipt = read_envelope(root/RECEIPT_PATH, RECEIPT_VERSION)
    if (manifest["runtime"] != release["runtime"] or manifest["decision"] != release["decision"]
            or receipt["manifest_payload_sha256"] != content_hash(manifest)
            or receipt["dry_run"]["status"] != "PASS" or receipt["wire_preflight"]["status"] != "PASS"):
        raise ValueError("Gate/runtime/schema/model/options parent không còn đúng")
    for name, checksum in manifest["source_sha256"].items():
        if file_hash(safe_path(root, name)) != checksum:
            raise ValueError("Nguồn W11-01 đã khóa bị sửa: "+name)
    upstream = manifest["upstream"]
    cohort_path = safe_path(root, upstream["cohort_path"])
    if file_hash(cohort_path) != upstream["cohort_sha256"]:
        raise ValueError("Cohort upstream lịch sử bị sửa")
    cohort = read_cached(cohort_path)
    if cohort["plan"]["runtime"] != runtime_identity():
        raise ValueError("Runtime tạo upstream khác môi trường hiện tại")
    for name, checksum in cohort["sources"].items():
        if file_hash(safe_path(root, name)) != checksum:
            raise ValueError("Nguồn snapshot upstream đã đổi: "+name)
    for name, checksum in cohort["plan"]["code_sha256"].items():
        if hashlib.sha256(safe_path(root, name).read_text(encoding="utf-8").encode()).hexdigest() != checksum:
            raise ValueError("Mã tạo upstream lịch sử bị sửa: "+name)
    for point in upstream["points"].values():
        for kind in ("point", "journal"):
            if file_hash(safe_path(root, point[kind+"_path"])) != point[kind+"_sha256"]:
                raise ValueError("Upstream point/journal khác freeze")
    for name, checksum in receipt["dry_run"]["journals_sha256"].items():
        if file_hash(safe_path(root/OUTPUT, name)) != checksum:
            raise ValueError("Journal request W11-01 bị sửa/mất")
    return manifest, receipt


def requests_from_parent(root: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Chỉ trích request từ journal fixture đã seal; tuyệt đối không lấy fixture decision."""
    journals, requests = {}, []
    for slot in manifest["requests"]:
        key = (slot["point_id"], slot["repeat_index"])
        if key not in journals:
            journals[key] = read_envelope(root/OUTPUT/"offline_dry_run"/str(key[1])/(key[0]+".json"), JOURNAL_VERSION)
        request = deepcopy(journals[key]["branches"][slot["branch_id"]]["request"])
        if content_hash(request) != slot["canonical_sha256"] or request["point_id"] != slot["point_id"] or request["repeat_index"] != slot["repeat_index"]:
            raise ValueError("Request snapshot khác manifest đã khóa")
        requests.append(request)
    if len(requests) != 612:
        raise ValueError("Snapshot phải giữ đủ612 request")
    return requests


def extension_facts(root: Path, manifest: dict[str, Any], requests: list[dict[str, Any]]) -> dict[str, Any]:
    """Bổ sung khóa riêng cho orchestration; không sửa parent, teacher/student hoặc protocol."""
    return {"version": EXTENSION_VERSION, "parent_manifest_sha256": file_hash(root/MANIFEST_PATH),
            "parent_payload_sha256": content_hash(manifest), "parent_receipt_sha256": file_hash(root/RECEIPT_PATH),
            "runtime": manifest["runtime"], "source_sha256": {n: file_hash(root/n) for n in CODE},
            "requests_payload_sha256": content_hash({"requests": requests}), "run_output": RUN.as_posix(),
            "ledger_path": LEDGER, "slot_count": 612, "primary_slots": 360, "repeat_slots": 252,
            "preflight_lock": LOCK.as_posix(), "preflight_request": preflight_request(),
            "preflight_scope": "CONTROL_ONLY_ORIGINAL_PARENT_MANIFEST_SIGNATURE",
            "order_reuse_and_unknown_policy": "UNCHANGED_FROM_PARENT_MANIFEST",
            "authorization": "USER_RUNS_API_ONLY_AFTER_PARENT_AND_EXTENSION_GIT_ANCHORS",
            "confirmation_allowed": False, "training_allowed": False, "refit_allowed": False}


def prepare(root: Path) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Khóa extension sau test/source commit và trước mọi response development; không đọc key."""
    manifest, _ = verify_parent(root)
    requests = requests_from_parent(root, manifest)
    facts = extension_facts(root, manifest, requests)
    if (root/EXTENSION_PATH).exists():
        return verify_extension(root, parent=manifest, require_anchor=False)
    if any((root/RUN/name).exists() for name in ("identity.json", "ready.json", "slots")):
        raise ValueError("Run đã bắt đầu trước extension, không reseal")
    commit = git_value(root, "rev-parse", "HEAD")
    git_value(root, "diff", "--exit-code", commit, "--", *CODE)
    for name in CODE:
        git_value(root, "cat-file", "-e", commit+":"+name)
    extension = {**facts, "source_commit": commit}
    write_envelope(root/RUN/"requests.json", REQUEST_VERSION, {"requests": requests}, immutable=True)
    write_envelope(root/EXTENSION_PATH, EXTENSION_VERSION, extension, immutable=True)
    return extension, manifest, requests


def verify_extension(root: Path, *, parent: dict[str, Any] | None = None,
                     require_anchor: bool = True) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Cold-check parent/source/Git/request body trước key và trước resume; không có network."""
    manifest = verify_parent(root)[0] if parent is None else parent
    extension = read_envelope(root/EXTENSION_PATH, EXTENSION_VERSION)
    requests = requests_from_parent(root, manifest)
    if extension != {**extension_facts(root, manifest, requests), "source_commit": extension["source_commit"]}:
        raise ValueError("Extension khác source/parent/runtime/request đã khóa")
    if read_envelope(root/RUN/"requests.json", REQUEST_VERSION) != {"requests": requests}:
        raise ValueError("Snapshot request khác source đã khóa")
    git_value(root, "merge-base", "--is-ancestor", extension["source_commit"], "HEAD")
    git_value(root, "diff", "--exit-code", extension["source_commit"], "--", *CODE)
    if require_anchor:
        saved = subprocess.run(["git", "show", "HEAD:"+EXTENSION_PATH.as_posix()], cwd=root, capture_output=True, check=False)
        if saved.returncode or saved.stdout != (root/EXTENSION_PATH).read_bytes():
            raise ValueError("Extension chưa neo byte Git HEAD")
    return extension, manifest, requests


def normalized_decision(message: dict[str, Any]) -> dict[str, Any]:
    """Dùng đúng normalizer/schema hiện hữu để cold-check raw JSON, không đổi action."""
    normalized, _ = _normalize_structured_result({"parsed": json.loads(message["content"]), "raw": None, "parsing_error": None}, "vi")
    return TradeDecisionOutput.model_validate_json(normalized, strict=True).model_dump()


def audit_response(root: Path, cache: Path, ledger: dict[str, Any], slot: dict[str, Any],
                   contract: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Nối UUID/body/model/schema/raw cache với HTTP thật; không tin decision tự ghi trong checkpoint."""
    rows = [r for r in ledger["requests"] if r.get("checkpoint_attempt_id") == slot["checkpoint_attempt_id"]]
    success = [r for r in rows if r["status"] == 200]
    if not success:
        raise ValueError("Slot thiếu response HTTP thành công; giữ unknown/reserve")
    last = success[-1]
    path = safe_path(cache, str(UUID(last["id"]))+".json")
    if last.get("durable_response") != {"sha256": file_hash(path)}:
        raise ValueError("Raw response cache bị sửa/mất")
    raw = read_cached(path)
    body = base64.b64decode(raw["body_base64"], validate=True)
    if (set(raw) != {"version", "request", "body_base64", "headers"} or raw["version"] != "resilient_invocation_v1"
            or set(raw["headers"])-{"content-type", "x-request-id"} or raw["request"] != contract
            or hashlib.sha256(body).hexdigest() != last["improvement_audit"]["response"]["body_sha256"]):
        raise ValueError("Raw response khác body/audit đã khóa")
    message = json.loads(body)["choices"][0]["message"]
    parsed = normalized_decision(message)
    verify_attempt_audit(ledger, slot, expected=contract, raw_message={"content": message["content"], "tool_calls": []})
    return parsed, [r["id"] for r in rows]


class DevelopmentRun:
    """Một run cố định612 slot, prefix complete liên tục; unknown chỉ phục hồi từ raw durable."""

    def __init__(self, root: Path, directory: Path, extension: dict[str, Any], manifest: dict[str, Any],
                 requests: list[dict[str, Any]], *, mode: str = "research") -> None:
        if mode not in ("research", "offline_fixture"):
            raise ValueError("Mode runner không hợp lệ")
        self.root, self.directory, self.extension, self.manifest, self.requests = root, directory, extension, manifest, requests
        self.signature = content_hash(extension)
        self.identity = {"extension_sha256": self.signature, "parent_sha256": content_hash(manifest), "mode": mode}
        self.plans = manifest["requests"]
        if len(self.plans) != len(requests) or len(requests) != 612:
            raise ValueError("Runner không được đổi số slot")
        self.originals = {(p["point_id"], p["repeat_index"]): p["slot_index"] for p in self.plans if p["branch_id"] == "Original"}

    def path(self, i: int) -> Path:
        """Tên slot chỉ từ index0..611, không lấy path do response cung cấp."""
        return self.directory/"slots"/f"{i:04d}.json"

    def empty(self, i: int) -> dict[str, Any]:
        """Chỉ intent pending, không có action mặc định hoặc UUID giả."""
        return {"run_signature": self.signature, "plan": deepcopy(self.plans[i]), "status": "pending",
                "attempt_id": None, "shared_off_from": None, "decision": None, "request_ids": []}

    def initialize(self) -> None:
        """Mọi slot phải durable trước response đầu; resume không tự tạo lại slot đã mất."""
        identity = self.directory/"identity.json"
        ready = self.directory/"ready.json"
        if identity.exists():
            if read_envelope(identity, RUN_VERSION) != self.identity:
                raise ValueError("Run khác identity/mode, không migrate fixture sang production")
            if not ready.exists() and (self.directory/"slots").exists():
                for path in (self.directory/"slots").glob("*.json"):
                    if read_envelope(path, SLOT_VERSION)["status"] != "pending":
                        raise ValueError("Mất ready sau intent; không tái tạo slot")
        else:
            if (self.directory/"slots").exists():
                raise ValueError("Có slot trước identity, không reseal")
            write_envelope(identity, RUN_VERSION, self.identity, immutable=True)
        for i in range(612):
            if not self.path(i).exists():
                if ready.exists():
                    raise ValueError("Mất slot sau ready; dừng thay vì tái tạo")
                write_envelope(self.path(i), SLOT_VERSION, self.empty(i), immutable=True)
        expected = {f"{i:04d}.json" for i in range(612)}
        if {p.name for p in (self.directory/"slots").iterdir()} != expected:
            raise ValueError("Run có slot ngoài manifest")
        write_envelope(ready, RUN_VERSION, self.identity, immutable=True)

    def dispatch_slot(self, i: int, record: dict[str, Any]) -> dict[str, Any]:
        """Scientific slot đầy đủ được bind vào từng HTTP kể cả retry/format repair."""
        p = self.plans[i]
        return {"run_signature": self.signature, "point_id": p["point_id"], "branch_id": p["branch_id"],
                "repeat_index": p["repeat_index"], "slot_index": i, "canonical_sha256": p["canonical_sha256"],
                "checkpoint_attempt_id": record["attempt_id"]}

    def inspect(self, ledger: dict[str, Any], cache: Path, *, recover: bool = False) -> list[dict[str, Any]]:
        """Kiểm toàn bộ checkpoint trước HTTP tiếp; unknown không raw vẫn dừng, không tự replay."""
        records, gap, seen = [], False, set()
        for i, plan in enumerate(self.plans):
            record = read_envelope(self.path(i), SLOT_VERSION)
            if (set(record) != set(self.empty(i)) or record["plan"] != plan or record["run_signature"] != self.signature
                    or content_hash(self.requests[i]) != plan["canonical_sha256"]):
                raise ValueError("Checkpoint/request khác manifest")
            status = record["status"]
            if status not in ("pending", "unknown", "complete"):
                raise ValueError("Trạng thái slot không hợp lệ")
            if status == "pending":
                if record != self.empty(i):
                    raise ValueError("Pending chứa UUID/decision chưa được đăng ký")
            elif record["shared_off_from"] is not None:
                original = self.originals[(plan["point_id"], plan["repeat_index"])]
                if (status != "complete" or not plan["shared_off_eligible"] or plan["branch_id"] in ("Original", "Original_duplicate")
                        or original >= i or record["shared_off_from"] != original or record["attempt_id"] is not None
                        or record["request_ids"] or records[original]["status"] != "complete"
                        or self.requests[original] != self.requests[i] or record["decision"] != records[original]["decision"]):
                    raise ValueError("Shared-off khác Original durable cùng point/repeat/body")
            else:
                UUID(record["attempt_id"])
                if record["attempt_id"] in seen:
                    raise ValueError("UUID trùng giữa các slot")
                seen.add(record["attempt_id"])
                rows = [r for r in ledger["requests"] if r.get("checkpoint_attempt_id") == record["attempt_id"]]
                if status == "unknown" and not any(r["status"] == 200 for r in rows):
                    if record["decision"] is not None or record["request_ids"]:
                        raise ValueError("Unknown chứa decision/HTTP ID giả")
                else:
                    parsed, ids = audit_response(self.root, cache, ledger, self.dispatch_slot(i, record), plan["http_contract"])
                    if status == "unknown":
                        if recover:
                            record.update(status="complete", decision=parsed, request_ids=ids)
                            write_envelope(self.path(i), SLOT_VERSION, record)
                            status = "complete"
                    elif parsed != record["decision"] or ids != record["request_ids"]:
                        raise ValueError("Decision/ledger IDs khác raw response")
            if gap and status != "pending":
                raise ValueError("Checkpoint có slot chạy sau khoảng missing/unknown")
            if status != "complete":
                gap = True
            if status == "complete":
                TradeDecisionOutput.model_validate(record["decision"], strict=True)
            records.append(record)
        own = [r for r in ledger["requests"] if r.get("run_signature") == self.signature]
        if len({r["id"] for r in ledger["requests"]}) != len(ledger["requests"]) or any(r.get("checkpoint_attempt_id") not in seen for r in own):
            raise ValueError("Ledger UUID trùng hoặc request run không thuộc intent nào")
        return records

    def execute(self, dispatch: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
                ledger: Callable[[], dict[str, Any]], cache: Path) -> dict[str, Any]:
        """Chạy đủ lịch hoặc dừng giữ intent; không nhận limit/filter/action/outcome từ caller."""
        records = self.inspect(ledger(), cache, recover=True)
        if any(r["status"] == "unknown" for r in records):
            raise ValueError("AMBIGUOUS_DECISION: giữ UUID/reserve; không tự replay unknown")
        for i, plan in enumerate(self.plans):
            if records[i]["status"] == "complete":
                continue
            original = self.originals[(plan["point_id"], plan["repeat_index"])]
            record = self.empty(i)
            if plan["shared_off_eligible"]:
                if original >= i or records[original]["status"] != "complete" or self.requests[i] != self.requests[original]:
                    raise ValueError("Original chưa durable hoặc canonical không trùng")
                record.update(status="complete", decision=deepcopy(records[original]["decision"]), shared_off_from=original)
            else:
                record.update(status="unknown", attempt_id=str(uuid4()))
                write_envelope(self.path(i), SLOT_VERSION, record)
                slot = self.dispatch_slot(i, record)
                parsed = dispatch(deepcopy(self.requests[i]), slot)
                actual, ids = audit_response(self.root, cache, ledger(), slot, plan["http_contract"])
                if actual != parsed:
                    raise ValueError("Parsed Decision khác raw HTTP; giữ unknown")
                record.update(status="complete", decision=deepcopy(parsed), request_ids=ids)
            write_envelope(self.path(i), SLOT_VERSION, record)
            records[i] = record
            if i == 611 or self.plans[i+1]["point_id"] != plan["point_id"] or self.plans[i+1]["repeat_index"] != plan["repeat_index"]:
                self.progress(records)
                print(f"Đã lưu {i+1}/612 slot; point={plan['point_id']}, repeat={plan['repeat_index']}; chưa phân tích P&L.", flush=True)
        final = self.inspect(ledger(), cache)
        return self.progress(final)

    def progress(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        """Chỉ đếm trạng thái/HTTP, không đánh giá action, return hoặc nomination."""
        complete = [r for r in records if r["status"] == "complete"]
        result = {"identity": self.identity, "status": "COMPLETE_AWAITING_W11_03" if len(complete) == 612 else "INCOMPLETE",
                  "complete_slots": len(complete), "primary_complete": sum(r["plan"]["repeat_index"] == 0 for r in complete),
                  "repeat_complete": sum(r["plan"]["repeat_index"] > 0 for r in complete),
                  "unknown_slots": sum(r["status"] == "unknown" for r in records),
                  "pending_slots": sum(r["status"] == "pending" for r in records),
                  "shared_off": sum(r["shared_off_from"] is not None for r in complete),
                  "http_requests": sum(len(r["request_ids"]) for r in complete),
                  "duplicate_complete": sum(r["plan"]["branch_id"] == "Original_duplicate" for r in complete)}
        write_envelope(self.directory/"progress.json", PROGRESS_VERSION, result)
        return result


class GuardedHTTP(httpx.BaseTransport):
    """Biên cuối trước network: HTTP body phải đúng slot đã freeze, không truyền header ra log."""

    def __init__(self, expected: dict[str, dict[str, Any]], inner: httpx.BaseTransport) -> None:
        self.expected, self.inner = expected, inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Sai body/model/options/schema dừng trước network, kể cả retry hoặc format repair."""
        slot = SLOT.get()
        if not slot or self.expected.get(slot["canonical_sha256"]) != body_contract(json.loads(request.content)):
            raise ValueError("HTTP body không đúng scientific slot đã khóa")
        return self.inner.handle_request(request)

    def close(self) -> None:
        """Nhả transport thật theo lifecycle caller."""
        self.inner.close()


class OfflineDispatch:
    """Fixture audit/cache cho dry-run612 slot; chỉ dùng namespace offline, không credential/network."""

    def __init__(self, root: Path, directory: Path, manifest: dict[str, Any]) -> None:
        self.root, self.directory = root, directory
        self.cache = directory/"http_cache"
        self.state = read_json(directory/"fixture_ledger.json") if (directory/"fixture_ledger.json").exists() else {"requests": []}
        self.contracts = {p["canonical_sha256"]: p["http_contract"] for p in manifest["requests"]}
        self.calls = 0

    def __call__(self, request: dict[str, Any], slot: dict[str, Any]) -> dict[str, Any]:
        """Response trung tính chỉ kiểm plumbing, không được nhập sang run research."""
        from core.historical_signals import digest
        from core.mt_bicl_v2_integration import OfflineDecisionFixture
        from core.research_cohort import save_envelope as save_cached
        from core.bayesian_memory import atomic_write_json
        self.calls += 1
        parsed = OfflineDecisionFixture().invoke("")["parsed"]
        message = {"role": "assistant", "content": json.dumps(parsed, ensure_ascii=False)}
        body = json.dumps({"choices": [{"message": message}]}, ensure_ascii=False).encode()
        contract = self.contracts[content_hash(request)]
        rid = str(uuid4())
        path = self.cache/(rid+".json")
        save_cached(path, {"version": "resilient_invocation_v1", "request": contract,
                           "body_base64": base64.b64encode(body).decode(), "headers": {}})
        self.state["requests"].append({"id": rid, "status": 200, "checkpoint_attempt_id": slot["checkpoint_attempt_id"],
            "run_signature": slot["run_signature"], "point_id": slot["point_id"], "branch_id": slot["branch_id"],
            "durable_response": {"sha256": file_hash(path)}, "improvement_audit": {"audit_version": "improvement_http_audit_v1",
                "slot": deepcopy(slot), "request": contract, "response": {"body_sha256": hashlib.sha256(body).hexdigest(),
                    "message_sha256": digest({"content": message["content"], "tool_calls": []})}}})
        atomic_write_json(self.directory/"fixture_ledger.json", self.state)
        return normalized_decision(message)


def api_preflight(root: Path, manifest: dict[str, Any], key: str) -> dict[str, Any]:
    """Dùng lock operations riêng; giữ nguyên owner offline đã released và schema receipt cũ."""
    from core.improvement_recovery import ResilientPacer, ResilientTransport
    path = root/OUTPUT/"live_api_preflight.json"
    if path.exists():
        return verify_live_preflight(root, manifest)
    signature = content_hash(manifest)
    pacer = ResilientPacer(root/LEDGER, credential=key, amendment_sha256=signature, policy="request_admission_v2")
    request, attempt = preflight_request(), str(uuid4())
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
        actual, ids = audit_response(root, root/OUTPUT/"preflight_http_cache", pacer.state, slot, contract)
        if actual != parsed:
            raise ValueError("Preflight parser khác raw response; giữ unknown")
        saved.update(status="PASS", decision=parsed, request_ids=ids)
        write_envelope(path, LIVE_VERSION, saved)
    return verify_live_preflight(root, manifest)
