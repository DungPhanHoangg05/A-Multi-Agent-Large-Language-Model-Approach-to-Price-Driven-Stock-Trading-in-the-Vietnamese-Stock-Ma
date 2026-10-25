"""Run/resume và snapshot đã kiểm cho cohort U-BICL; không đổi kernel đã khóa."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import re
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx

from agents.decision_agent import _invoke_with_retry
from core.backtest_engine import PRIOR_BRANCH_MODES
from core.groq_pacing import GroqPacer
from core.historical_signals import digest
from core.improvement_transport import verify_attempt_audit
from core.prior_backtest import evaluate_point
from core.prior_run_lock import PriorRunLock, utc_now
from core.research_cohort import read_envelope, save_envelope
from core.research_input_lock import _write_once
from core.research_invocation import CURRENT
from core.unified_bayes_contracts import MATRIX, code_identity, sha, validate
from core.unified_bayes_decision import LLM_BRANCHES, PreparedPoint, sdk_request, trace_ids
from core.unified_bayes_runtime import ExecutionJournal, _encode_response, _parsed
from core.unified_bayes_source import BoundCohort
from core.unified_bayes_transport import UnifiedTransport, decision_scope


class OfflineTransport(UnifiedTransport):
    """Đọc ledger không credential/ghi usage; mọi HTTP đều lỗi trước reserve."""

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        raise AssertionError("Chế độ offline U-BICL không được gọi HTTP")


def offline_transport(ledger: Path, cache_root: Path) -> OfflineTransport:
    """GroqPacer constructor chỉ kiểm ledger, không tạo file hoặc đọc key."""
    return OfflineTransport(GroqPacer(ledger, policy="request_admission_v2"), cache_root)


def numeric_decision(evidence: dict[str, Any]) -> dict[str, Any]:
    """Đúng policy mean>0,5 khi stats ready; không giả confidence hoặc invocation LLM."""
    posterior = evidence["posterior"]
    ready = posterior["gate"]["ready"]
    return {"action": "LONG" if ready and posterior["posterior_mean"] > .5 else "SHORT",
            "reason": "POSTERIOR_THRESHOLD" if ready else "STATS_NOT_READY", "kind": "OFFLINE"}


def lock_authorization(root: Path, plan: dict[str, Any], receipts: dict[str, str]) -> dict[str, Any]:
    """Ghim receipt trước API, không nhận thay gate/readiness giữa một run."""
    expected = {"authorization_version": "unified_bic_run_authorization_v1", "plan_sha256": digest(plan), **receipts}
    if set(expected) != {"authorization_version", "plan_sha256", "technical_gates_sha256", "readiness_sha256"}:
        raise ValueError("Authorization thiếu binding gate/readiness")
    _write_once(root / "authorization.json", expected)
    if digest(read_envelope(root / "authorization.json")) != digest(expected):
        raise ValueError("Authorization khác receipt đã khóa")
    return expected


def _authorization(root: Path, plan: dict[str, Any], pacer: Any, signature: str, *, required: bool = False) -> None:
    """Đối soát receipt với admission hiện tại và usage thật trước HTTP, không chỉ sau point."""
    path = root / "authorization.json"
    records = [row for row in pacer.state["requests"] if row.get("run_signature") == signature]
    if not path.exists():
        if plan["split"] != "fixture" and (required or records):
            raise ValueError("Run thật thiếu authorization durable")
        return
    auth = read_envelope(path)
    if (set(auth) != {"authorization_version", "plan_sha256", "technical_gates_sha256", "readiness_sha256"}
            or auth["authorization_version"] != "unified_bic_run_authorization_v1" or auth["plan_sha256"] != digest(plan)
            or any(type(auth[k]) is not str or not re.fullmatch(r"[0-9a-f]{64}", auth[k]) for k in ("technical_gates_sha256", "readiness_sha256"))
            or hasattr(pacer, "amendment_sha256") and pacer.amendment_sha256 != digest(auth)
            or any(row.get("operational_amendment_sha256") != digest(auth) for row in records)):
        raise ValueError("Admission/usage khác authorization/receipt đã khóa")


class _GuardedPoint(PreparedPoint):
    """Ủy quyền nguyên packet đã kiểm; chỉ bổ sung guard cohort lúc transport dispatch."""

    def __init__(self, point: PreparedPoint, guard: Any) -> None:
        self._point, self._guard = point, guard
        self.point_id, self.shared_sha256 = point.point_id, point.shared_sha256

    def packet(self, branch: str) -> dict[str, Any]:
        """Không tạo hoặc sửa body trong adapter cohort."""
        return self._point.packet(branch)

    def verify(self, llm: Any) -> None:
        """Guard toàn cohort trước từng HTTP/retry; verify ngoài scope vẫn dùng kernel cũ."""
        if CURRENT.get() is not None:
            self._guard()
        self._point.verify(llm)


class CohortRun:
    """Giữ binding toàn run, dùng kernel cho HTTP và dựng report từ journal đã verify."""

    def __init__(self, cohort: BoundCohort, plan: dict[str, Any], llm: Any, root: Path,
                 ledger: Path, *, create: bool = False) -> None:
        if digest(plan) != digest(cohort.plan(llm)):
            raise ValueError("Run khác plan/source/request hiện tại")
        self.cohort, self.plan, self.llm, self.root = cohort, deepcopy(plan), llm, Path(root).resolve()
        transport = getattr(llm.http_client, "_transport", None)
        if not isinstance(transport, UnifiedTransport) or transport.pacer.path.resolve() != ledger.resolve():
            raise ValueError("Run cần transport và ledger đúng binding")
        self.transport = transport
        self.binding = {"run_version": "unified_bic_cohort_identity_v1", "plan_sha256": digest(plan),
            "code_sha256": plan["code_sha256"], "runtime": plan["runtime"], "split": plan["split"],
            "ledger_path": str(ledger.resolve())}
        self.signature = digest(self.binding)
        with PriorRunLock(self.root, self.signature):
            path = self.root / "cohort.json"
            if create:
                _write_once(path, self.binding)
            if digest(read_envelope(path)) != digest(self.binding):
                raise ValueError("Cohort identity khác plan/code/runtime/ledger")
            self.journal = ExecutionJournal(self.root / "journal", self.signature,
                                            [_GuardedPoint(point, self._control) for point in cohort.prepared.values()],
                                            llm, plan["schedule"], create=create)
            self.verify()

    def _control(self) -> None:
        """Kiểm toàn nguồn/control trước dispatch; không gọi lại journal gây đệ quy."""
        if code_identity() != self.plan["code_sha256"] or digest(read_envelope(self.root / "cohort.json")) != digest(self.binding):
            raise ValueError("Code hoặc cohort identity đã đổi")
        self.cohort.source_check()
        _authorization(self.root, self.plan, self.transport.pacer, self.signature)

    def verify(self) -> dict[Any, Any]:
        """Cả point chưa chạy cũng phải giữ đúng source/code/request trước API tiếp theo."""
        self._control()
        return self.journal.verify()

    def snapshot(self) -> tuple[list[dict[str, Any]], dict[str, str]]:
        """Chỉ đánh giá sau đủ năm LLM của point; evaluator không đi vào prepared state."""
        docs, rows = self.verify(), []
        hashes = {"cohort.json": sha(self.root / "cohort.json"), "journal/identity.json": sha(self.root / "journal/identity.json")}
        if (self.root / "authorization.json").exists():
            hashes["authorization.json"] = sha(self.root / "authorization.json")
        for slot in self.plan["schedule"]:
            pid, rid = slot["point_id"], slot["repeat_id"]
            request = self.plan["requests"][pid]
            source = self.cohort.points[pid]
            row = {"point_id": pid, "repeat_id": rid, "context": deepcopy(request["source_proof"]["context"]),
                "source_proof": deepcopy(request["source_proof"]), "branches": {}, "evaluation": None,
                "regime": request["packets"]["Original"]["query"]["current_regime"],
                "readiness": {"stats": request["u_evidence"]["posterior"]["gate"]["ready"],
                    "examples": request["u_evidence"]["selection"]["gate"]["ready"],
                    "context_mode": request["u_evidence"]["context_mode"]}}
            for branch in slot["order"]:
                saved = docs[(pid, rid, branch)]
                packet = self.cohort.prepared[pid].packet(branch)
                output = saved["output"]
                decision = None if output is None else {"action": output["decision"], "confidence": output["confidence"],
                    "risk_reward_ratio": output["risk_reward_ratio"], "latency_seconds": None}
                row["branches"][branch] = {"status": saved["status"], "decision": decision, "output": deepcopy(output),
                    "decision_origin": saved["decision_origin"], "shared_original": deepcopy(saved["shared_original"]),
                    "prior_visible": bool(packet["prefix"]), "trace": trace_ids(packet, output) if output else None}
                path = self.journal.path(pid, rid, branch)
                hashes[path.relative_to(self.root).as_posix()] = sha(path)
            numeric = numeric_decision(request["u_evidence"])
            row["branches"]["Numeric_only"] = {"status": "complete", "decision": {"action": numeric["action"],
                "confidence": None, "risk_reward_ratio": None, "latency_seconds": None}, "output": numeric,
                "decision_origin": "offline_numeric", "shared_original": None, "prior_visible": False, "trace": None}
            if all(branch["status"] == "complete" for branch in row["branches"].values()):
                symbol, cutoff = pid[:3], pid[4:]
                frame, events = source._adapter.execution_data(symbol)
                evaluated = None
                for name, branch in row["branches"].items():
                    value = evaluate_point(frame, events, cutoff, {key: branch for key in PRIOR_BRANCH_MODES})
                    if evaluated is None:
                        evaluated = {**value, "branches": {}}
                    evaluated["branches"][name] = value["branches"]["original"]
                row["evaluation"] = evaluated
            rows.append(row)
        # Đối soát lại nguồn/journal/ledger sau evaluation, không chỉ snapshot RAM ban đầu.
        self.verify()
        records = self.transport.pacer.state["requests"]
        for record in records:
            if record.get("run_signature") == self.signature:
                hashes["http:" + record["id"]] = digest(record)
        return rows, dict(sorted(hashes.items()))

    def report(self) -> dict[str, Any]:
        """Report luôn tái dựng từ nguồn và journal hiện tại, không lấy report cũ làm input."""
        from core.unified_bayes_reports import build_report
        rows, hashes = self.snapshot()
        return build_report(self.plan, rows, {**self.binding, "run_signature": self.signature, "checkpoint_sha256": hashes},
                            self.transport.pacer.state)

    def run(self, *, repeats: bool = False) -> dict[str, Any]:
        """Primary và repeat chạy riêng; dừng giữ checkpoint, không ghi đè report cũ bằng run dở."""
        with PriorRunLock(self.root, self.signature):
            _authorization(self.root, self.plan, self.transport.pacer, self.signature, required=True)
            docs = self.verify()
            if repeats and any(doc["status"] != "complete" for (pid, rid, name), doc in docs.items() if rid == 0):
                raise ValueError("Chỉ chạy repeat khi toàn primary đã complete")
            for slot in self.plan["schedule"]:
                if bool(slot["repeat_id"]) != repeats:
                    continue
                self.verify()
                self.journal.run_point(slot["point_id"], slot["repeat_id"], execute=True)
            return self.report()


PREFLIGHT_PROMPT = ('Trả JSON hợp lệ theo schema được cung cấp: decision=SHORT, forecast_horizon=T+2.5, '
    'confidence=Thấp, risk_reward_ratio=1.0; giải thích đây là kiểm kết nối và schema, không phải giao dịch.')


def preflight(cohort: BoundCohort, plan: dict[str, Any], llm: Any, root: Path, *, execute: bool = False) -> dict[str, Any]:
    """Kiểm model/schema bằng prompt phi nghiên cứu; giữ UUID/cache khi bị ngắt, không tạo sample."""
    def verify() -> None:
        """Cả code mới và nguồn phải giữ nguyên trước HTTP preflight/retry."""
        if code_identity() != plan["code_sha256"]:
            raise ValueError("Code preflight đã đổi")
        cohort.verify(llm)
    verify()
    body, structured = sdk_request(llm, PREFLIGHT_PROMPT)
    binding = {"preflight_version": "unified_bic_preflight_v1", "plan_sha256": digest(plan), "body_sha256": digest(body)}
    signature = digest(binding)
    path = root / "preflight.json"
    with PriorRunLock(root / "preflight_lock", signature):
        if not path.exists():
            if not execute:
                raise ValueError("Chưa có preflight durable")
            save_envelope(path, {**binding, "attempt_id": str(uuid4()), "status": "unknown", "recoveries": [], "response": None})
        saved = read_envelope(path)
        if (set(saved) != {*binding, "attempt_id", "status", "recoveries", "response"}
                or any(digest(saved[k]) != digest(v) for k, v in binding.items()) or saved["status"] not in ("unknown", "complete")
                or type(saved["recoveries"]) is not list or saved["status"] == "complete" and saved["response"] is None):
            raise ValueError("Preflight khác plan/model/options/schema")
        UUID(saved["attempt_id"])
        transport = llm.http_client._transport
        _authorization(root, plan, transport.pacer, signature, required=execute)
        slot = {"run_signature": signature, "point_id": "provider-preflight", "branch_id": "Original", "repeat_id": 0,
            "checkpoint_attempt_id": saved["attempt_id"], "prompt_sha256": hashlib.sha256(PREFLIGHT_PROMPT.encode()).hexdigest()}
        from core.improvement_transport import body_contract
        if saved["response"] is None:
            if not execute:
                raise ValueError("Preflight chưa có response durable")
            saved["recoveries"].append({"at": utc_now(), "reason": "SAME_UUID_RETRY_WITH_AUDIT"})
            save_envelope(path, saved)
            with decision_scope(packet={"body": body}, slot=slot, source_check=verify):
                result = _invoke_with_retry(structured.invoke, PREFLIGHT_PROMPT)
            rows = [row for row in transport.pacer.state["requests"] if row.get("checkpoint_attempt_id") == saved["attempt_id"] and row["status"] == 200]
            if not rows:
                raise ValueError("Preflight không có HTTP thành công đã audit")
            saved["response"] = _encode_response(result, rows[-1]["id"])
            save_envelope(path, saved)
        _parsed(saved["response"])
        verify_attempt_audit(transport.pacer.state, slot, expected=body_contract(body), raw_message=saved["response"]["raw_message"]["data"])
        if saved["status"] != "complete":
            if not execute:
                raise ValueError("Preflight response chưa seal complete")
            saved["status"] = "complete"
            save_envelope(path, saved)
        return saved
