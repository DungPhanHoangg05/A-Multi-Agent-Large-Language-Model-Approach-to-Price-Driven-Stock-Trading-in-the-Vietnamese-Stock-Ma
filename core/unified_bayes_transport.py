"""Guard trước HTTP U-BICL; tái dùng nguyên retry/pacer/cache/ledger đã kiểm."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
import json
from typing import Any, Iterator

import httpx

from core.historical_signals import digest
from core.bayesian_memory import read_json
from core.improvement_recovery import ResilientTransport, recovery_scope
from core.improvement_transport import SLOT, body_contract
from core.prior_stage_journal import STAGES
from core.research_invocation import CURRENT, ENABLED, invocation_scope

ACTIVE: ContextVar[Any] = ContextVar("unified_bic_active_request", default=None)


def _wire_guard(request: httpx.Request) -> None:
    """Guard chạy cả trước từng HTTP retry; ValueError integrity không bị retry tạm thời."""
    active = ACTIVE.get()
    if active is None:
        raise ValueError("HTTP không có source scope")
    active["source_check"]()
    body = json.loads(request.content)
    body_contract(body)
    if active["body"] is not None and digest(body) != digest(active["body"]):
        raise ValueError("Body thay đổi trước gửi HTTP")


class _WireGuard(httpx.BaseTransport):
    """Bọc provider thật, không chạm admission/quota/ledger cũ."""

    def __init__(self, inner: httpx.BaseTransport) -> None:
        self.inner = inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Kiểm source trước provider, kể cả vòng retry trong transport cha."""
        try:
            _wire_guard(request)
        except (ValueError, AssertionError) as error:
            # SDK có thể bọc lỗi transport thành APIConnectionError; giữ lỗi gốc trong scope.
            if ACTIVE.get() is not None:
                ACTIVE.get()["integrity_error"] = error
            raise
        return self.inner.handle_request(request)

    def close(self) -> None:
        """Nhả kết nối provider theo lifecycle client."""
        self.inner.close()


class UnifiedTransport(ResilientTransport):
    """Chặn body/slot/source sai trước reserve hoặc HTTP, kể cả khi có cache durable."""

    def __init__(self, pacer: Any, cache_root: Any, inner: httpx.BaseTransport | None = None) -> None:
        super().__init__(pacer, cache_root, _WireGuard(inner or httpx.HTTPTransport(retries=0)))

    def verify_ledger_file(self) -> None:
        """Không đè lịch sử trên đĩa bằng RAM cũ khi ledger bị đổi hoặc mất."""
        with self.pacer._mutex:
            if self.pacer.path.exists():
                if digest(read_json(self.pacer.path)) != digest(self.pacer.state):
                    raise ValueError("Ledger trên đĩa khác state đang chạy; dừng để nạp lại/đối soát")
            elif self.pacer.state["requests"] or self.pacer.state.get("invocations"):
                raise ValueError("Ledger đã có usage nhưng file bị mất")

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Giữ lỗi integrity gốc kể cả khi SDK bọc lỗi guard trước HTTP đầu tiên."""
        try:
            return self._checked_request(request)
        except (ValueError, AssertionError) as error:
            if ACTIVE.get() is not None:
                ACTIVE.get()["integrity_error"] = error
            raise

    def _checked_request(self, request: httpx.Request) -> httpx.Response:
        """Không cho SDK đổi body; cùng UUID không được trỏ sang point/repeat khác."""
        if request.method != "POST" or request.url.host != "api.groq.com" or request.url.path != "/openai/v1/chat/completions":
            raise ValueError("Transport U-BICL chỉ nhận endpoint Groq chat đã khóa")
        active, budget = ACTIVE.get(), CURRENT.get()
        if active is None or budget is None or not budget.checkpoint_attempt_id or not budget.recovery_enabled:
            raise ValueError("HTTP U-BICL thiếu scope/source/UUID hoặc recovery policy")
        active["source_check"]()
        self.verify_ledger_file()
        body = json.loads(request.content)
        body_contract(body)
        if active["body"] is None:
            if budget.role not in STAGES or budget.branch_id is not None or SLOT.get() is not None:
                raise ValueError("Scope upstream không hợp lệ")
        elif digest(body) != digest(active["body"]) or digest(SLOT.get()) != digest(active["slot"]):
            raise ValueError("HTTP body/model/options/schema/slot khác request đã khóa")
        for row in self.pacer.state["requests"]:
            if row.get("checkpoint_attempt_id") != budget.checkpoint_attempt_id:
                continue
            if any(row.get(key) != getattr(budget, key) for key in ("run_signature", "point_id", "branch_id")):
                raise ValueError("UUID HTTP trỏ sang nguồn/point/branch khác")
            audit = row.get("improvement_audit")
            if audit is not None and digest(audit["slot"]) != digest(SLOT.get()):
                raise ValueError("UUID HTTP trỏ sang repeat khác")
        return super().handle_request(request)


@contextmanager
def decision_scope(*, packet: dict[str, Any], slot: dict[str, Any], source_check: Any) -> Iterator[Any]:
    """Một budget cho HTTP retry và hai format attempt; không thay UUID khi resume."""
    enabled = ENABLED.set(True)
    slot_token = SLOT.set(deepcopy(slot))
    active_token = ACTIVE.set({"body": deepcopy(packet["body"]), "slot": deepcopy(slot), "source_check": source_check})
    try:
        if CURRENT.get() is not None:
            raise ValueError("Decision U-BICL không được lồng vào budget khác")
        with recovery_scope(), invocation_scope("decision_" + slot["branch_id"]) as budget:
            for key in ("run_signature", "point_id", "branch_id", "checkpoint_attempt_id"):
                setattr(budget, key, slot[key])
            try:
                yield budget
            except BaseException:
                if ACTIVE.get().get("integrity_error") is not None:
                    raise ACTIVE.get()["integrity_error"] from None
                raise
    finally:
        ACTIVE.reset(active_token)
        SLOT.reset(slot_token)
        ENABLED.reset(enabled)


@contextmanager
def upstream_scope(source_check: Any) -> Iterator[None]:
    """StageJournal giữ UUID/input hash; chỉ upstream đã xác minh mới được gọi transport."""
    enabled = ENABLED.set(True)
    slot_token = SLOT.set(None)
    active_token = ACTIVE.set({"body": None, "slot": None, "source_check": source_check})
    try:
        with recovery_scope():
            source_check()
            try:
                yield
            except BaseException:
                if ACTIVE.get().get("integrity_error") is not None:
                    raise ACTIVE.get()["integrity_error"] from None
                raise
    finally:
        ACTIVE.reset(active_token)
        SLOT.reset(slot_token)
        ENABLED.reset(enabled)
