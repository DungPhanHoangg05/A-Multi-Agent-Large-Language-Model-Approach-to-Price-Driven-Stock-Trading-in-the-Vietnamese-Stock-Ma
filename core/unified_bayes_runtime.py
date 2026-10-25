"""Journal Decision U-BICL, shared-off và phục hồi cùng UUID trên transport đã audit."""

from __future__ import annotations

from copy import deepcopy
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator
from uuid import UUID, uuid4
import hashlib
import json

from langchain_core.messages import messages_to_dict

from agents import decision_agent as legacy
from core.historical_signals import digest
from core.improvement_transport import verify_attempt_audit
from core.prior_run_lock import PriorRunLock, safe_path, utc_now
from core.prior_stage_journal import StageJournal
from core.research_cohort import read_envelope, save_envelope
from core.research_input_lock import _write_once, runtime_identity
from core.research_invocation import RECOVERY
from core.unified_bayes_decision import LLM_BRANCHES, PreparedPoint, sdk_request, shared_off_allowed
from core.unified_bayes_transport import UnifiedTransport, decision_scope, upstream_scope

VERSION = "unified_bic_execution_journal_v1"
BRANCH_ROTATION = ("A_reference", "U_full", "U_stats", "U_examples")
CODE = ("core/unified_bayes_decision.py", "core/unified_bayes_transport.py", "core/unified_bayes_runtime.py",
    "agents/decision_agent.py", "core/prior_stage_journal.py", "core/research_invocation.py",
    "core/improvement_recovery.py", "core/improvement_transport.py", "core/provider_quota.py",
    "core/groq_pacing.py", "core/prior_run_lock.py")


def code_identity() -> dict[str, str]:
    """Ghim riêng kernel mới cùng các primitive retry/journal/SDK contract đang dùng."""
    root = Path(__file__).resolve().parents[1]
    return {name: hashlib.sha256((root / name).read_text("utf-8").encode()).hexdigest() for name in CODE}


class UnifiedStageJournal(StageJournal):
    """Không đổi schema journal cũ; audit same-UUID resume nằm cạnh output từng point."""

    def __init__(self, path: Path, binding: dict[str, str], *, create: bool = False) -> None:
        super().__init__(path, binding, create=create)
        if any(len(node["attempts"]) != 1 or node["attempts"][0]["authorization"] is not None
               for node in self.document["nodes"].values()):
            raise ValueError("Upstream U-BICL chỉ phục hồi cùng UUID, không tạo scientific attempt mới")
        self._audit()

    def _audit(self) -> dict[str, Any]:
        """Audit phải tham chiếu đúng node/UUID trong journal nguồn, kể cả khi node complete."""
        path = self.path.with_suffix(".recovery.json")
        binding = self.document["binding"]
        audit = read_envelope(path) if path.exists() else {"version": "unified_upstream_recovery_audit_v1", "binding": binding, "events": []}
        if (set(audit) != {"version", "binding", "events"} or audit["version"] != "unified_upstream_recovery_audit_v1"
                or digest(audit["binding"]) != digest(binding) or type(audit["events"]) is not list):
            raise ValueError("Audit upstream khác source/point/run")
        ids = {node["attempts"][0]["attempt_id"]: name for name, node in self.document["nodes"].items()}
        for event in audit["events"]:
            if (set(event) != {"node", "attempt_id", "reason", "at"} or event["reason"] != "SAME_UUID_RETRY_WITH_AUDIT"
                    or ids.get(event["attempt_id"]) != event["node"]):
                raise ValueError("Audit upstream sai schema/node/UUID")
            datetime.fromisoformat(event["at"])
        return audit

    def invoke(self, name: str, function: Any, state: dict[str, Any]) -> dict[str, Any]:
        """Ghi audit trước phục hồi unknown; complete vẫn dùng nguyên output durable."""
        node = self.document["nodes"].get(name)
        if RECOVERY.get() and node and node["attempts"][-1]["status"] == "unknown":
            path = self.path.with_suffix(".recovery.json")
            audit = self._audit()
            audit["events"].append({"node": name, "attempt_id": node["attempts"][-1]["attempt_id"],
                                   "reason": "SAME_UUID_RETRY_WITH_AUDIT", "at": utc_now()})
            save_envelope(path, audit)
        return super().invoke(name, function, state)


def upstream_journal(root: Path, signature: str, point_id: str, source_proof: dict[str, Any], *, create: bool = False) -> StageJournal:
    """Adapter StageJournal cũ trong namespace run mới, giữ bốn node và same-UUID recovery."""
    return UnifiedStageJournal(safe_path(root, f"upstream/{point_id}.json"),
        {"run_signature": signature, "point_id": point_id, "source_sha256": digest(source_proof)}, create=create)


@contextmanager
def upstream_checkpoint(root: Path, signature: str, point_id: str, source_proof: dict[str, Any],
                        source_check: Any, *, create: bool = False) -> Iterator[StageJournal]:
    """Giữ khóa OS suốt bốn node, dùng cùng StageJournal cho primary và repeat."""
    with PriorRunLock(root, signature), upstream_scope(source_check):
        yield upstream_journal(root, signature, point_id, source_proof, create=create)


class _FormatError(ValueError):
    """Chỉ raw output sai định dạng mới được tiêu thêm một format attempt."""


def branch_order(index: int, repeat_id: int = 0) -> list[str]:
    """Original đầu; vòng primary/repeat đúng công thức protocol, không chọn theo action."""
    if type(index) is not int or index < 0 or type(repeat_id) is not int or not 0 <= repeat_id <= 3:
        raise ValueError("Index/repeat phải là số nguyên gốc hợp lệ")
    names = list(BRANCH_ROTATION) + (["Original_duplicate"] if repeat_id else [])
    offset = ((3 * index + repeat_id - 1) if repeat_id else index) % len(names)
    return ["Original", *names[offset:], *names[:offset]]


def _sha(path: Path) -> str:
    """Bind byte slot nguồn, không coi payload tự reseal là bằng chứng nguồn."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parsed(response: dict[str, Any]) -> dict[str, Any]:
    """Chỉ lỗi định dạng được repair; không ép action theo prior hoặc viện dẫn ID."""
    try:
        data = json.loads(response["raw_message"]["data"]["content"])
        if type(data) is not dict or set(data) != set(legacy.TradeDecisionOutput.model_fields):
            raise ValueError("Sai field Decision")
        result = legacy.TradeDecisionOutput.model_validate(data, strict=True).model_dump()
        if result["forecast_horizon"] != "T+2.5" or not result["confidence"].strip():
            raise ValueError("Sai horizon/confidence")
    except (ValueError, TypeError) as error:
        raise _FormatError("Raw Decision sai schema/horizon; không đổi thành CASH") from error
    if response["parsing_error"] or digest(response["parsed"]) != digest(result):
        raise ValueError("Parsed Decision khác raw HTTP đã lưu")
    return result


def _encode_response(result: Any, request_id: str) -> dict[str, Any]:
    """Lưu raw message trước parse; không lưu repr exception hoặc credential/header."""
    if type(result) is not dict or result.get("raw") is None:
        raise ValueError("SDK thiếu raw structured response để audit")
    parsed = result.get("parsed")
    if hasattr(parsed, "model_dump"):
        parsed = parsed.model_dump()
    return {"http_request_id": request_id, "parsed": deepcopy(parsed),
        "parsing_error": result.get("parsing_error") is not None,
        "raw_message": messages_to_dict([result["raw"]])[0]}


class ExecutionJournal:
    """Run kernel dùng prepared packets đã kiểm; producer/report/release thuộc CLI kế tiếp."""

    def __init__(self, root: Path, signature: str, prepared: list[PreparedPoint], llm: Any,
                 schedule: list[dict[str, Any]], *, create: bool = False) -> None:
        if (type(signature) is not str or not StageJournal.is_hash(signature) or type(prepared) is not list
                or not prepared or any(not isinstance(point, PreparedPoint) for point in prepared)):
            raise ValueError("Journal thiếu identity/prepared point đã kiểm")
        self.root, self.signature, self.llm = Path(root).resolve(), signature, llm
        self.code = code_identity()
        self.transport = getattr(getattr(llm, "http_client", None), "_transport", None)
        if not isinstance(self.transport, UnifiedTransport):
            raise ValueError("Journal U-BICL cần transport guard/audit/pacer đã kiểm")
        self.points = {point.point_id: point for point in prepared}
        if len(self.points) != len(prepared) or type(schedule) is not list or not schedule:
            raise ValueError("Point trùng hoặc thiếu schedule đã khóa")
        if any(type(row) is not dict or set(row) != {"point_id", "repeat_id", "order"} for row in schedule):
            raise ValueError("Schedule sai schema")
        primary_ids = sorted(self.points, key=lambda pid: (pid[4:], pid[:3]))
        repeat_ids = sorted({row["point_id"] for row in schedule if row.get("repeat_id", 0)}, key=lambda pid: (pid[4:], pid[:3]))
        self.schedule, self.expected = deepcopy(schedule), {}
        seen = set()
        for row in schedule:
            if (type(row) is not dict or set(row) != {"point_id", "repeat_id", "order"}
                    or row["point_id"] not in self.points or type(row["repeat_id"]) is not int
                    or not 0 <= row["repeat_id"] <= 3):
                raise ValueError("Schedule sai schema/point/repeat")
            pid, rid = row["point_id"], row["repeat_id"]
            if (pid, rid) in seen:
                raise ValueError("Schedule trùng point/repeat")
            seen.add((pid, rid))
            index = (repeat_ids if rid else primary_ids).index(pid)
            if row["order"] != branch_order(index, rid):
                raise ValueError("Rotation khác protocol đã khóa")
            for branch in row["order"]:
                packet = self.points[pid].packet(branch)
                self.expected[(pid, rid, branch)] = packet
        if any((pid, 0) not in seen for pid in primary_ids) or any((pid, rid) not in seen for pid in repeat_ids for rid in (1, 2, 3)):
            raise ValueError("Schedule thiếu primary hoặc một trong ba repeat")
        manifest = {"journal_version": VERSION, "run_signature": signature, "schedule": schedule,
            "code_sha256": self.code, "runtime": runtime_identity(),
            "packets": {self.key(*key): digest(packet) for key, packet in self.expected.items()}}
        self.manifest = deepcopy(manifest)
        with PriorRunLock(self.root, signature):
            path = safe_path(self.root, "identity.json")
            if create:
                _write_once(path, manifest)
                for key, packet in self.expected.items():
                    _write_once(self.path(*key), self.initial(*key, packet))
            if digest(read_envelope(path)) != digest(manifest):
                raise ValueError("Run khác schedule/source/request hoặc code đã khóa")
            self.verify()

    @staticmethod
    def key(pid: str, rid: int, branch: str) -> str:
        """Key logic không phụ thuộc UUID hoặc số HTTP retry."""
        return f"{pid}/{rid}/{branch}"

    def path(self, pid: str, rid: int, branch: str) -> Path:
        """Không cho key checkpoint vượt run root."""
        return safe_path(self.root, "decisions/" + self.key(pid, rid, branch) + ".json")

    def initial(self, pid: str, rid: int, branch: str, packet: dict[str, Any]) -> dict[str, Any]:
        """Slot planned tồn tại trước HTTP đầu; shared-off không tạo attempts giả."""
        return {"journal_version": VERSION, "run_signature": self.signature, "point_id": pid,
            "repeat_id": rid, "branch_id": branch, "packet_sha256": digest(packet), "status": "planned",
            "decision_origin": None, "shared_original": None, "reason_codes": [], "attempts": [], "output": None}

    def save(self, path: Path, value: dict[str, Any]) -> None:
        """Primitive nguyên tử chung; điểm lỗi giữ intent/response đã durable."""
        save_envelope(path, value)

    def _slot(self, pid: str, rid: int, branch: str, attempt_id: str) -> dict[str, Any]:
        """Slot audit tương thích transport hiện hữu và thêm repeat binding."""
        return {"run_signature": self.signature, "point_id": pid, "branch_id": branch, "repeat_id": rid,
            "checkpoint_attempt_id": attempt_id, "prompt_sha256": self.expected[(pid, rid, branch)]["prompt_sha256"]}

    def _original_ref(self, pid: str, rid: int) -> tuple[dict[str, Any], dict[str, Any]]:
        """Chỉ Original cùng point/repeat hoàn tất mới được làm nguồn reuse."""
        original = read_envelope(self.path(pid, rid, "Original"))
        if original["status"] != "complete":
            raise ValueError("Original chưa durable trước nhánh khác")
        ref = {"point_id": pid, "repeat_id": rid, "branch_id": "Original",
            "slot_sha256": _sha(self.path(pid, rid, "Original")), "packet_sha256": original["packet_sha256"],
            "output_sha256": digest(original["output"])}
        return original, ref

    def _validate(self, key: tuple[str, int, str], saved: dict[str, Any], ids: set[str]) -> None:
        """Tái kiểm toàn bộ slot trước API, kể cả nhánh/point không được chọn chạy tiếp."""
        pid, rid, branch = key
        packet = self.expected[key]
        empty = self.initial(pid, rid, branch, packet)
        fixed = ("journal_version", "run_signature", "point_id", "repeat_id", "branch_id", "packet_sha256")
        if (type(saved) is not dict or set(saved) != set(empty)
                or any(digest(saved[field]) != digest(empty[field]) for field in fixed)):
            raise ValueError("Slot khác source/point/repeat/body binding")
        if saved["status"] == "planned":
            if digest(saved) != digest(empty):
                raise ValueError("Slot planned chứa output/attempt giả")
            return
        if saved["status"] not in ("unknown", "complete") or type(saved["reason_codes"]) is not list:
            raise ValueError("Trạng thái slot không hợp lệ")
        if branch != "Original":
            original, ref = self._original_ref(pid, rid)
        else:
            original = ref = None
        if saved["decision_origin"] == "shared_original":
            permitted = shared_off_allowed(prior_visible=bool(packet["prefix"]), same_identity=
                digest(packet["body"]) == digest(self.expected[(pid, rid, "Original")]["body"]),
                same_point_repeat=True, original_durable=True, duplicate=branch == "Original_duplicate")
            if (not permitted or saved["status"] != "complete" or saved["attempts"] or digest(saved["shared_original"]) != digest(ref)
                    or digest(saved["output"]) != digest(original["output"]) or saved["reason_codes"] != ["CANONICAL_REQUEST_IDENTICAL"]):
                raise ValueError("Shared-off khác Original durable/canonical body hoặc tạo HTTP giả")
            if any(((row.get("improvement_audit") or {}).get("slot") or {}).get("branch_id") == branch
                   and row.get("run_signature") == self.signature and row.get("point_id") == pid
                   and ((row.get("improvement_audit") or {}).get("slot") or {}).get("repeat_id") == rid
                   for row in self.transport.pacer.state["requests"]):
                raise ValueError("Shared-off có HTTP không được phép")
            return
        if saved["decision_origin"] != "invoked" or saved["shared_original"] is not None or len(saved["attempts"]) != 1:
            raise ValueError("Slot invoked sai schema attempts/origin")
        reason = ("ORIGINAL" if branch == "Original" else "INDEPENDENT_DUPLICATE" if branch == "Original_duplicate"
                  else "PRIOR_VISIBLE" if packet["prefix"] else "CANONICAL_REQUEST_DIFFERS")
        if saved["reason_codes"] != [reason]:
            raise ValueError("Lý do invoke khác request đã khóa")
        if (branch not in ("Original", "Original_duplicate") and not packet["prefix"]
                and digest(packet["body"]) == digest(self.expected[(pid, rid, "Original")]["body"])):
            raise ValueError("Prior-off body trùng Original phải reuse, không tạo HTTP mới")
        attempt = saved["attempts"][0]
        if set(attempt) != {"attempt_id", "started_at", "recoveries", "responses"}:
            raise ValueError("Attempt sai schema")
        UUID(attempt["attempt_id"])
        if attempt["attempt_id"] in ids:
            raise ValueError("UUID bị dùng chéo slot")
        ids.add(attempt["attempt_id"])
        datetime.fromisoformat(attempt["started_at"])
        if type(attempt["recoveries"]) is not list or type(attempt["responses"]) is not list or len(attempt["responses"]) > legacy.DECISION_FORMAT_ATTEMPTS:
            raise ValueError("Số format attempt hoặc recovery không hợp lệ")
        for event in attempt["recoveries"]:
            if set(event) != {"at", "reason"} or event["reason"] != "SAME_UUID_RETRY_WITH_AUDIT":
                raise ValueError("Recovery thiếu audit")
            datetime.fromisoformat(event["at"])
        for response in attempt["responses"]:
            if (type(response) is not dict or set(response) != {"http_request_id", "parsed", "parsing_error", "raw_message"}
                    or type(response["parsing_error"]) is not bool):
                raise ValueError("Response durable sai schema")
            rows = self.transport.pacer.state["requests"]
            last_id = attempt["responses"][-1]["http_request_id"]
            last_index = next((i for i, row in enumerate(rows) if row["id"] == last_id), None)
            if last_index is None:
                raise ValueError("Response durable thiếu HTTP record")
            records = verify_attempt_audit({"requests": rows[:last_index + 1]}, self._slot(pid, rid, branch, attempt["attempt_id"]),
                expected=packet["contract"], raw_message=attempt["responses"][-1]["raw_message"]["data"])
            match = next((row for row in records if row["id"] == response["http_request_id"]), None)
            data = response["raw_message"]["data"]
            fingerprint = digest({"content": data.get("content") or "", "tool_calls": data.get("tool_calls") or []})
            if match is None or match["improvement_audit"]["response"]["message_sha256"] != fingerprint:
                raise ValueError("Response durable không khớp HTTP record")
            try:
                _parsed(response)
            except _FormatError:
                pass
        successful = [row["id"] for row in self.transport.pacer.state["requests"]
                      if row.get("checkpoint_attempt_id") == attempt["attempt_id"] and row["status"] == 200]
        consumed = [response["http_request_id"] for response in attempt["responses"]]
        if consumed != successful[:len(consumed)] or len(successful) - len(consumed) > 1:
            raise ValueError("Response journal không phải prefix durable của HTTP cùng UUID")
        if saved["status"] == "complete":
            if not attempt["responses"] or digest(_parsed(attempt["responses"][-1])) != digest(saved["output"]):
                raise ValueError("Decision complete khác response durable/schema")
        elif saved["output"] is not None:
            raise ValueError("Unknown chứa output giả")

    def verify(self) -> dict[tuple[str, int, str], dict[str, Any]]:
        """Verifier nguồn + toàn snapshot; không gọi LLM, evaluator hoặc fit."""
        if code_identity() != self.code:
            raise ValueError("Code kernel/retry/journal đổi giữa run")
        if digest(read_envelope(safe_path(self.root, "identity.json"))) != digest(self.manifest):
            raise ValueError("Identity/schedule/code run bị sửa trên đĩa")
        self.transport.verify_ledger_file()
        for point in self.points.values():
            point.verify(self.llm)
        docs, ids = {}, set()
        for key in self.expected:
            saved = read_envelope(self.path(*key))
            try:
                self._validate(key, saved, ids)
            except (KeyError, TypeError, AttributeError) as error:
                raise ValueError("Journal sai schema hoặc thiếu nguồn durable") from error
            docs[key] = saved
        by_uuid = {doc["attempts"][0]["attempt_id"]: key for key, doc in docs.items() if doc["attempts"]}
        for row in self.transport.pacer.state["requests"]:
            if row.get("run_signature") != self.signature or row.get("branch_id") is None:
                continue
            key = by_uuid.get(row.get("checkpoint_attempt_id"))
            if key is None or row.get("point_id") != key[0] or row.get("branch_id") != key[2]:
                raise ValueError("Ledger chứa HTTP không có slot/UUID invoked tương ứng")
            audit = row.get("improvement_audit")
            if audit is not None and digest(audit["slot"]) != digest(self._slot(*key, row["checkpoint_attempt_id"])):
                raise ValueError("Ledger khác point/repeat slot")
            if audit is not None and digest(audit["request"]) != digest(self.expected[key]["contract"]):
                raise ValueError("Ledger body/schema/model/options khác packet đã khóa")
        return docs

    def _invoke(self, key: tuple[str, int, str], saved: dict[str, Any]) -> None:
        """Lưu intent/raw response trước parse; cache thành công được dùng trước HTTP mới."""
        pid, rid, branch = key
        packet, point = self.expected[key], self.points[pid]
        path = self.path(*key)
        if not saved["attempts"]:
            saved.update(status="unknown", decision_origin="invoked",
                reason_codes=["ORIGINAL" if branch == "Original" else "INDEPENDENT_DUPLICATE" if branch == "Original_duplicate" else
                              "PRIOR_VISIBLE" if packet["prefix"] else "CANONICAL_REQUEST_DIFFERS"])
            saved["attempts"] = [{"attempt_id": str(uuid4()), "started_at": utc_now(), "recoveries": [], "responses": []}]
            self.save(path, saved)
        else:
            saved["attempts"][0]["recoveries"].append({"at": utc_now(), "reason": "SAME_UUID_RETRY_WITH_AUDIT"})
            self.save(path, saved)
        attempt = saved["attempts"][0]
        slot = self._slot(pid, rid, branch, attempt["attempt_id"])
        with decision_scope(packet=packet, slot=slot, source_check=lambda: point.verify(self.llm)) as budget:
            while True:
                if attempt["responses"]:
                    try:
                        output = _parsed(attempt["responses"][-1])
                    except _FormatError:
                        if len(attempt["responses"]) >= legacy.DECISION_FORMAT_ATTEMPTS:
                            raise ValueError("Decision hết hai format attempt; giữ checkpoint, không đổi thành CASH")
                    else:
                        saved.update(status="complete", output=output)
                        self.save(path, saved)
                        return
                # Không dùng lại response lỗi định dạng đã được checkpoint xác nhận tiêu thụ.
                self.transport.used_cache.update((budget.invocation_id, response["http_request_id"]) for response in attempt["responses"])
                body, structured = sdk_request(self.llm, packet["prompt"])
                if digest(body) != digest(packet["body"]):
                    raise ValueError("SDK đổi body trước invoke")
                result = legacy._invoke_with_retry(structured.invoke, packet["prompt"])
                raw = messages_to_dict([result["raw"]])[0]["data"]
                fingerprint = digest({"content": raw.get("content") or "", "tool_calls": raw.get("tool_calls") or []})
                records = [row for row in self.transport.pacer.state["requests"]
                    if row.get("checkpoint_attempt_id") == attempt["attempt_id"] and row["status"] == 200
                    and (row.get("improvement_audit") or {}).get("response", {}).get("message_sha256") == fingerprint]
                if not records:
                    raise ValueError("SDK response không có HTTP audit tương ứng")
                response = _encode_response(result, records[-1]["id"])
                attempt["responses"].append(response)
                self.save(path, saved)

    def run_point(self, point_id: str, repeat_id: int = 0, *, execute: bool = False) -> dict[str, Any]:
        """Mặc định readonly; operator/fixture phải bật execute rõ ràng, không tự gọi API."""
        if type(execute) is not bool or type(repeat_id) is not int:
            raise ValueError("Execute/repeat sai kiểu")
        order = next((row["order"] for row in self.schedule if row["point_id"] == point_id and row["repeat_id"] == repeat_id), None)
        if order is None:
            raise ValueError("Point/repeat chưa nằm trong schedule đã khóa")
        with PriorRunLock(self.root, self.signature):
            for branch in order:
                docs = self.verify()
                key = (point_id, repeat_id, branch)
                saved, packet = docs[key], self.expected[key]
                if saved["status"] == "complete" or not execute:
                    continue
                if branch != "Original":
                    original, ref = self._original_ref(point_id, repeat_id)
                    reuse = shared_off_allowed(prior_visible=bool(packet["prefix"]), same_identity=
                        digest(packet["body"]) == digest(self.expected[(point_id, repeat_id, "Original")]["body"]),
                        same_point_repeat=True, original_durable=True, duplicate=branch == "Original_duplicate")
                    if reuse:
                        saved.update(status="complete", decision_origin="shared_original", shared_original=ref,
                            reason_codes=["CANONICAL_REQUEST_IDENTICAL"], output=deepcopy(original["output"]))
                        self.save(self.path(*key), saved)
                        continue
                self._invoke(key, saved)
            docs = self.verify()
        return {branch: deepcopy(docs[(point_id, repeat_id, branch)]) for branch in order}
