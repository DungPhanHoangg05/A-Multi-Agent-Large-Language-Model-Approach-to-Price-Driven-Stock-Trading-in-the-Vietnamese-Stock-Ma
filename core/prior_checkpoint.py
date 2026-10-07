"""Checkpoint nghiên cứu strict/atomic; phục hồi các Decision còn thiếu từ Full PIT."""

from __future__ import annotations

from copy import deepcopy
import math
from pathlib import Path
import re
from typing import Any
from uuid import UUID, uuid4
from datetime import datetime

from core.backtest_engine import PRIOR_BRANCH_MODES
from core.bayesian_memory import read_json
from core.prior_backtest import SCHEMA_VERSION, canonical_hash, evaluate_point, summarize_points, write_document
from core.prior_config import copy_prior_json
from core.prior_context import REPORT_FIELDS
from core.prior_run_lock import PriorRunLock, safe_path, utc_now


def read_document(path: Path, schema: Any, definition: str) -> dict[str, Any]:
    """Kiểm envelope, JSON strict, canonical hash và schema local."""
    envelope = copy_prior_json(read_json(path))
    if type(envelope) is not dict or set(envelope) != {"payload", "sha256"}:
        raise ValueError("Checkpoint thiếu envelope nghiên cứu; không migrate legacy")
    if envelope["sha256"] != canonical_hash(envelope["payload"]):
        raise ValueError("Checksum checkpoint không khớp")
    schema.validate(envelope["payload"], definition)
    return envelope["payload"]


def safe_error(error: BaseException) -> dict[str, Any]:
    """Chỉ ghi mã/thông báo cố định; không lưu raw exception/request/key hoặc hash key."""
    messages, seen = [], set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        messages.append(str(current).lower())
        current = current.__cause__ or current.__context__
    text = " ".join(messages)
    code = "RUNTIME"
    if isinstance(error, (KeyboardInterrupt, InterruptedError)):
        code = "INTERRUPT"
    elif isinstance(error, FileNotFoundError):
        code = "SOURCE"
    elif isinstance(error, OSError):
        code = "PERSISTENCE"
    elif "ambiguous_upstream" in text:
        code = "AMBIGUOUS_UPSTREAM"
    elif "ambiguous_full" in text:
        code = "AMBIGUOUS_FULL"
    elif "quota" in text or "daily limit" in text or "tokens per day" in text:
        code = "QUOTA"
    elif "429" in text or "rate limit" in text or "rate_limit" in text:
        code = "RATE_LIMIT"
    elif isinstance(error, (ValueError, AssertionError, FileNotFoundError)):
        code = "SOURCE"
    elif "schema" in text or "format" in text or "long/short" in text:
        code = "FORMAT"
    delay = None
    match = re.search(r"(?:retry after|try again in)\s*(?:(\d+(?:\.\d+)?)\s*m)?\s*(\d+(?:\.\d+)?)\s*s", text)
    if match and code in ("QUOTA", "RATE_LIMIT"):
        value = 60 * float(match[1] or 0) + float(match[2])
        if math.isfinite(value):
            delay = value
    messages_vi = {"QUOTA": "Quota LLM đã hết; đổi key rồi resume với cùng cấu hình.",
        "RATE_LIMIT": "LLM bị giới hạn tốc độ; giữ input và áp dụng pacing trước resume.",
        "FORMAT": "Decision không hợp lệ; nhánh chưa được chấm thành quyết định.",
        "SOURCE": "Nguồn hoặc quan hệ dữ liệu không hợp lệ; cần kiểm tra trước resume.",
        "INTERRUPT": "Tiến trình bị ngắt; các nhánh complete đã lưu được giữ nguyên.",
        "PERSISTENCE": "Ghi/đọc dữ liệu thất bại; dừng API và kiểm checkpoint trên đĩa.",
        "AMBIGUOUS_UPSTREAM": "Upstream đã bắt đầu nhưng chưa có báo cáo durable; cần rà soát.",
        "AMBIGUOUS_FULL": "Full đã bắt đầu nhưng chưa có bundle durable; cần rà soát.",
        "RUNTIME": "Lời gọi thất bại; giữ checkpoint để kiểm tra hoặc resume Decision còn thiếu."}
    return {"code": code, "message_vi": messages_vi[code],
            "retryable": code in ("QUOTA", "RATE_LIMIT", "FORMAT", "INTERRUPT", "RUNTIME"), "retry_after_seconds": delay}


def planned_point(point: Any, signature: str, language: str) -> dict[str, Any]:
    """Point planned chỉ chứa proof/projection PIT, chưa có outcome hoặc report giả."""
    source = {key: point.source_provenance[key] for key in ("context", "prices", "news", "regime", "bank")}
    context, prices = source["context"], source["prices"]
    symbol, cutoff = context["symbol"], context["as_of_date"]
    return {"schema_version": SCHEMA_VERSION, "run_signature": signature, "document_type": "point_checkpoint",
        "point_id": f"{symbol}-{cutoff}", "revision": 1, "status": "planned",
        "context": {"symbol": symbol, "as_of_date": cutoff, "time_frame": "1d"},
        "source_proof": source, "source_sha256": canonical_hash(source),
        "agent_projection": {"stock_name": symbol, "as_of_date": cutoff, "window_end_date": cutoff,
            "time_frame": "1d", "language": language, "is_backtest": True,
            "snapshot_ref": {"path": prices["csv_path"], "csv_sha256": prices["csv_sha256"],
                "snapshot_sha256": prices["snapshot_sha256"], "rows": prices["snapshot_rows"],
                "start_date": prices["snapshot_start_date"], "end_date": cutoff, "schema": prices["schema"]}},
        "shared": {"stage": "not_started", "upstream_reports": None, "full_bundle": None, "shared_sha256": None},
        "branches": {name: {"status": "planned", "input": None, "attempts": [], "decision": None, "error": None}
                     for name in PRIOR_BRANCH_MODES}, "evaluation": None, "error": None}


class _BeforeApi(BaseException):
    """Thoát dry-run ngay trước API; không bị wrapper format/retry bắt lại."""

    def __init__(self, inputs: dict[str, Any]) -> None:
        self.inputs = inputs


class CheckpointSession:
    """Điểm mutable trong run đã giữ OS lock; RAM chỉ tiến sau commit durable."""

    def __init__(self, store: PriorCheckpointStore, point: Any, document: dict[str, Any]) -> None:
        self.store, self.runner, self.point = store, store.runner, point
        self.document, self.active_branch = deepcopy(document), None

    @property
    def stage(self) -> str:
        return self.document["shared"]["stage"]

    def _after_commit(self, event: str) -> None:
        """Ranh giới fault injection trong test; production không có side effect."""

    def save(self, candidate: dict[str, Any], event: str) -> None:
        """Tăng revision sau replace; không chỉnh checkpoint complete đã seal."""
        if self.document["status"] == "complete":
            raise ValueError("Point complete đã seal không được chỉnh sửa")
        candidate = copy_prior_json(candidate)
        candidate["revision"] = self.document["revision"] + 1
        write_document(self.store.point_path(candidate["point_id"]), candidate, self.runner.schema, "point")
        self.document = deepcopy(candidate)
        self._after_commit(event)

    def mark_stage(self, stage: str, *, reports: dict[str, str] | None = None,
                   bundle: dict[str, Any] | None = None) -> None:
        """Persist intent/output trước khi cho phép bước API kế tiếp."""
        allowed = {"not_started": "upstream_started", "upstream_started": "upstream_complete",
                   "upstream_complete": "full_started", "full_started": "shared_complete"}
        if allowed.get(self.stage) != stage:
            raise ValueError("Chuyển stage checkpoint không hợp lệ")
        doc = deepcopy(self.document)
        doc.update(status="running", error=None)
        doc["shared"]["stage"] = stage
        if reports is not None:
            doc["shared"]["upstream_reports"] = copy_prior_json(reports)
        if bundle is not None:
            doc["shared"].update(full_bundle=copy_prior_json(bundle), shared_sha256=canonical_hash(bundle))
        self.save(doc, stage)

    def restore_shared(self) -> dict[str, Any]:
        """Seal lại shared bằng nguồn PIT, không mang evaluation/errors vào agent."""
        return self.point.restore_full_bundle(self.document["shared"]["full_bundle"])

    def before_decision(self, name: str, shared: dict[str, Any], state: dict[str, Any], prompt: str) -> None:
        """Input/prompt/attempt running phải durable trước transport retry đầu."""
        inputs = self.runner.branch_input(self.point, shared, self.document["shared"]["shared_sha256"], name, state, prompt)
        doc = deepcopy(self.document)
        branch = doc["branches"][name]
        if branch["status"] == "complete":
            raise ValueError("Không được invoke lại nhánh complete")
        if branch["input"] is not None and canonical_hash(branch["input"]) != canonical_hash(inputs):
            raise ValueError("Input/prompt retry khác checkpoint đã lưu")
        if branch["attempts"] and branch["attempts"][-1]["status"] == "running":
            branch["attempts"][-1].update(status="unknown", finished_at=None)
        branch.update(status="running", input=copy_prior_json(inputs), decision=None, error=None)
        branch["attempts"].append({"attempt_id": str(uuid4()), "started_at": utc_now(),
            "finished_at": None, "status": "running", "error": None})
        doc.update(status="running", error=None)
        self.save(doc, f"decision_started:{name}")

    def complete_branch(self, name: str, shared: dict[str, Any], output: dict[str, Any]) -> None:
        """Ghi ngay output nhánh hợp lệ; giữ nguyên lịch sử attempt của lần resume."""
        branch = self.runner.branch_record(self.point, shared, self.document["shared"]["shared_sha256"], name, output)
        doc = deepcopy(self.document)
        previous = doc["branches"][name]
        if previous["status"] != "running" or canonical_hash(previous["input"]) != canonical_hash(branch["input"]):
            raise ValueError("Response không khớp input/attempt đã persist")
        attempts = deepcopy(previous["attempts"])
        attempts[-1].update(status="complete", finished_at=utc_now(), error=None)
        branch["attempts"] = attempts
        doc["branches"][name] = branch
        self.save(doc, f"branch_complete:{name}")

    def branch_output(self, name: str, shared: dict[str, Any]) -> dict[str, Any]:
        """Projection nghiên cứu W4-10 từ nhánh complete; không cấp outcome query."""
        branch = self.document["branches"][name]
        inputs, decision, attempt = branch["input"], branch["decision"], branch["attempts"][-1]
        state = {**deepcopy(shared), **{key: deepcopy(inputs[key]) for key in
            ("prior_config", "prior_tasks", "prior_stats", "prior_metadata", "bayesian_prior_context")},
            "decision_prompt": inputs["prompt"]["text"], "final_trade_decision": decision["normalized_response"]}
        return {"state": state, "elapsed_seconds": decision["latency_seconds"], "raw_response": decision["raw_response"],
                **{key: attempt[key] for key in ("attempt_id", "started_at", "finished_at")}}

    def fail(self, error: BaseException) -> None:
        """Ghi lỗi sanitized nếu còn ghi được; stage ambiguous vẫn giữ nguyên."""
        if isinstance(error, OSError) or self.document["status"] == "complete":
            return  # Lỗi đĩa không thử ghi lại response/status hoặc nuốt lỗi gốc.
        doc, info = deepcopy(self.document), safe_error(error)
        doc.update(status="failed", error=info)
        if self.active_branch is not None:
            branch = doc["branches"][self.active_branch]
            if branch["status"] != "complete":
                branch.update(status="failed", decision=None, error=deepcopy(info))
                if branch["attempts"] and branch["attempts"][-1]["status"] == "running":
                    branch["attempts"][-1].update(status="failed", finished_at=utc_now(), error=deepcopy(info))
        self.save(doc, "failed")

    def seal(self, completed: dict[str, Any]) -> None:
        """Chỉ seal sau năm nhánh durable và evaluation từ engine; không overwrite nhánh."""
        doc = deepcopy(completed)
        for name, branch in self.document["branches"].items():
            other = doc["branches"][name]
            if branch["status"] != "complete" or any(canonical_hash(branch[key]) != canonical_hash(other[key]) for key in ("input", "decision")):
                raise ValueError("Kết quả point khác các nhánh đã commit")
        doc["branches"] = deepcopy(self.document["branches"])
        self.save(doc, "point_complete")


class PriorCheckpointStore:
    """Manifest/point là nguồn resume; results dẫn xuất có thể dựng lại offline."""

    def __init__(self, runner: Any, root: Path, identity: dict[str, Any], contexts: list[Any],
                 frame: Any, events: list[dict[str, Any]]) -> None:
        self.runner, self.root, self.identity = runner, root.resolve(), identity
        self.signature, self.contexts, self.frame, self.events = canonical_hash(identity), contexts, frame, events
        self.sessions: list[CheckpointSession] = []
        self.lock = PriorRunLock(self.root, self.signature)

    def point_path(self, point_id: str) -> Path:
        """Path cố định từ point ID đã so plan; không lấy path arbitrary từ payload."""
        return safe_path(self.root, f"points/{point_id}.json")

    def cleanup_temporary_files(self) -> None:
        """Dọn temp writer đã biết sau preflight, chỉ trong run-dir đang giữ khóa."""
        if self.lock.handle is None:
            raise ValueError("Chỉ được dọn temp khi đang giữ OS lock")
        targets = [safe_path(self.root, name) for name in (
            "run_manifest.json", "identity.json", "results.json", "run.owner.json", "run.recovery.json")]
        targets.extend(self.point_path(s.document["point_id"]) for s in self.sessions)
        for target in targets:
            pattern = re.compile(r"\." + re.escape(target.name) + r"\.[a-z0-9_]{8}\.tmp")
            for temporary in target.parent.glob(f".{target.name}.*.tmp"):
                if pattern.fullmatch(temporary.name):
                    checked = safe_path(self.root, temporary.relative_to(self.root).as_posix())
                    if checked.is_file() and not temporary.is_symlink():
                        temporary.unlink()

    def initialize(self, *, resume: bool) -> None:
        """Toàn plan durable trước initialized=true; source kiểm trước API bất kỳ."""
        manifest_path = safe_path(self.root, "run_manifest.json")
        if manifest_path.exists():
            if not resume:
                raise ValueError("Run đã tồn tại; cần resume=True, không ghi đè")
            manifest = read_document(manifest_path, self.runner.schema, "manifest")
            if manifest["run_signature"] != self.signature or canonical_hash(manifest["identity"]) != self.signature:
                raise ValueError("Signature/identity khác config/nguồn/code/plan; không resume")
        else:
            if resume:
                raise ValueError("Không có manifest nghiên cứu; không migrate output legacy/W4-11")
            manifest = {"schema_version": SCHEMA_VERSION, "document_type": "run_manifest",
                "run_signature": self.signature, "identity": self.identity, "initialized": False, "created_at": utc_now()}
            write_document(manifest_path, manifest, self.runner.schema, "manifest")
        # identity.json giữ API artifact W4-11, không dùng nó làm nguồn resume.
        identity_path = safe_path(self.root, "identity.json")
        if identity_path.exists():
            if canonical_hash(read_document(identity_path, self.runner.schema, "identity")) != self.signature:
                raise ValueError("identity.json khác manifest")
        else:
            write_document(identity_path, self.identity, self.runner.schema, "identity")
        for point in self.contexts:
            expected = planned_point(point, self.signature, self.runner.config["language"])
            path = self.point_path(expected["point_id"])
            if path.exists():
                document = read_document(path, self.runner.schema, "point")
            elif manifest["initialized"]:
                raise ValueError("Point đã initialized bị mất; không tự gọi lại upstream")
            else:
                document = expected
                write_document(path, document, self.runner.schema, "point")
            session = CheckpointSession(self, point, document)
            self.validate_session(session, expected)
            self.sessions.append(session)
        found = {path.name for path in safe_path(self.root, "points").glob("*.json")}
        if found != {self.point_path(session.document["point_id"]).name for session in self.sessions}:
            raise ValueError("Point files khác plan; không bỏ qua điểm thừa")
        ids = [a["attempt_id"] for session in self.sessions for branch in session.document["branches"].values() for a in branch["attempts"]]
        if len(ids) != len(set(ids)):
            raise ValueError("Attempt UUID trùng giữa nhánh/điểm")
        if not manifest["initialized"]:
            if any(s.document["status"] != "planned" or s.stage != "not_started" for s in self.sessions):
                raise ValueError("Manifest chưa initialized nhưng có point đã bắt đầu")
            manifest["initialized"] = True
            write_document(manifest_path, manifest, self.runner.schema, "manifest")

    def _offline_input(self, session: CheckpointSession, shared: dict[str, Any], name: str) -> dict[str, Any]:
        """Replay retrieve/formatter/builder thật để so prompt, dừng trước invoke LLM."""
        mode, k = PRIOR_BRANCH_MODES[name]
        state = deepcopy(shared)
        state["prior_config"].update(mode=mode, k=k)
        def capture(prepared: dict[str, Any], prompt: str) -> None:
            raise _BeforeApi(self.runner.branch_input(session.point, shared,
                session.document["shared"]["shared_sha256"], name, prepared, prompt))
        graph = self.runner.builder.compile_report_decision(prior_config=state["prior_config"],
            prior_retriever=session.point.retrieve, prior_source_validator=session.point.verify_source,
            before_decision=capture)
        try:
            graph.invoke(state)
        except _BeforeApi as captured:
            return captured.inputs
        raise ValueError("Dry-run không dừng trước API")

    def validate_session(self, session: CheckpointSession, expected: dict[str, Any]) -> None:
        """Kiểm quan hệ khoa học; envelope tự băm lại không đủ để được resume."""
        doc = session.document
        for key in ("schema_version", "run_signature", "document_type", "point_id", "context", "source_proof", "source_sha256", "agent_projection"):
            if canonical_hash(doc[key]) != canonical_hash(expected[key]):
                raise ValueError(f"Checkpoint khác projection/nguồn/plan: {key}")
        if type(doc["revision"]) is not int or doc["revision"] < 1:
            raise ValueError("Revision checkpoint phải int dương")
        stage = session.stage
        if stage in ("upstream_started", "full_started"):
            raise ValueError("AMBIGUOUS_UPSTREAM" if stage == "upstream_started" else "AMBIGUOUS_FULL")
        if stage != "shared_complete" and (doc["evaluation"] is not None or any(
                b != expected["branches"][name] for name, b in doc["branches"].items())):
            raise ValueError("Point chưa shared_complete không được có branch/evaluation")
        if stage == "not_started" and doc["status"] != "planned":
            raise ValueError("Point not_started phải planned")
        if stage != "shared_complete":
            if doc["status"] == "complete":
                raise ValueError("Point complete thiếu shared")
            return
        shared_doc = doc["shared"]
        bundle = shared_doc["full_bundle"]
        if (shared_doc["shared_sha256"] != canonical_hash(bundle) or
                shared_doc["upstream_reports"] != {key: bundle["reports"][key] for key in REPORT_FIELDS[:3]}):
            raise ValueError("Shared hash/reports checkpoint không khớp")
        shared = session.restore_shared()
        for name, branch in doc["branches"].items():
            inputs, attempts = branch["input"], branch["attempts"]
            if inputs is not None:
                if canonical_hash(inputs) != canonical_hash(self._offline_input(session, shared, name)):
                    raise ValueError("Tasks/stats/metadata/prefix/query/prompt khác replay offline")
            for attempt in attempts:
                UUID(attempt["attempt_id"])
                start = datetime.fromisoformat(attempt["started_at"])
                if attempt["finished_at"] is not None and datetime.fromisoformat(attempt["finished_at"]) < start:
                    raise ValueError("Attempt kết thúc trước khi bắt đầu")
                if attempt["status"] in ("complete", "failed") and attempt["finished_at"] is None:
                    raise ValueError("Attempt kết thúc thiếu timestamp")
                if attempt["status"] in ("running", "unknown") and attempt["finished_at"] is not None:
                    raise ValueError("Attempt đang chạy/không rõ chưa có thời điểm kết thúc")
                if (attempt["status"] == "failed") != (attempt["error"] is not None):
                    raise ValueError("Attempt status/error không nhất quán")
            status = branch["status"]
            if status == "planned" and (inputs is not None or attempts or branch["decision"] is not None or branch["error"] is not None):
                raise ValueError("Nhánh planned chứa attempt/output")
            if status in ("running", "complete") and (not attempts or attempts[-1]["status"] != status):
                raise ValueError("Branch/attempt status không khớp")
            if status == "failed" and attempts and attempts[-1]["status"] != "failed":
                raise ValueError("Branch failed không có attempt thất bại cuối")
            if any(a["status"] == "running" for a in attempts[:-1]):
                raise ValueError("Attempt cũ còn running")
            if status == "complete":
                serialized = self.runner.branch_record(session.point, shared, shared_doc["shared_sha256"], name,
                                                       session.branch_output(name, shared))
                if canonical_hash(serialized["decision"]) != canonical_hash(branch["decision"]):
                    raise ValueError("Decision checkpoint không khớp parser/nguồn output")
        all_complete = all(b["status"] == "complete" for b in doc["branches"].values())
        if doc["status"] == "complete":
            if not all_complete or doc["error"] is not None or canonical_hash(doc["evaluation"]) != canonical_hash(
                    evaluate_point(self.frame, self.events, doc["context"]["as_of_date"], doc["branches"])):
                raise ValueError("Point complete/evaluation sai hợp đồng kinh tế")
        elif doc["evaluation"] is not None:
            raise ValueError("Point chưa seal không được có evaluation")

    def result(self) -> dict[str, Any]:
        """Dựng summary từ tất cả điểm complete đúng thứ tự plan, không đọc result cũ."""
        points = [s.document for s in self.sessions if s.document["status"] == "complete"]
        files = []
        import hashlib
        for point in points:
            path = self.point_path(point["point_id"])
            files.append({"point_id": point["point_id"], "path": path.relative_to(self.root).as_posix(),
                          "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        return {"schema_version": SCHEMA_VERSION, "run_signature": self.signature, "document_type": "research_result",
            "status": "complete" if len(points) == len(self.sessions) else "partial",
            "planned_point_ids": [s.document["point_id"] for s in self.sessions],
            "completed_point_ids": [p["point_id"] for p in points], "point_files": files, "summary": summarize_points(points)}

    def write_result(self) -> dict[str, Any]:
        """File result hỏng/mất được dựng lại sau khi kiểm toàn point/manifest."""
        result = self.result()
        write_document(safe_path(self.root, "results.json"), result, self.runner.schema, "result")
        return copy_prior_json(result)

    def execute(self, *, resume: bool, callback: Any = None) -> dict[str, Any]:
        """Giữ OS lock, preflight toàn checkpoint rồi chạy phần còn thiếu."""
        with self.lock:
            self.initialize(resume=resume)
            self.cleanup_temporary_files()
            self.write_result()
            for index, session in enumerate(self.sessions):
                if session.document["status"] == "complete":
                    continue
                if self.runner.engine._stop_event.is_set():
                    break
                if self.runner.before_point is not None:
                    self.runner.before_point()
                try:
                    self.runner.adapter.verify_sources()
                    paired = self.runner.engine.run_prior_point(session.point, graph_builder=self.runner.builder,
                                                               checkpoint=session)
                    self.runner.adapter.verify_sources()
                    completed = self.runner._completed_point(session.point, paired, self.signature, self.frame, self.events)
                    session.seal(completed)
                except (Exception, KeyboardInterrupt) as error:
                    session.fail(error)
                    raise
                result = self.write_result()
                if callback is not None:
                    callback(copy_prior_json({"completed": len(result["completed_point_ids"]), "total": len(self.sessions),
                        "latest": session.document, "partial": result}))
                if index < len(self.sessions) - 1 and self.runner.engine._stop_event.wait(self.runner.engine.DELAY_BETWEEN_TESTS):
                    break
            return self.write_result()

    def verify(self) -> dict[str, Any]:
        """Xác minh semantic mọi checkpoint và dựng kết quả, không gọi LLM."""
        with self.lock:
            self.initialize(resume=True)
            self.runner.adapter.verify_sources()
            return self.result()
