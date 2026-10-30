"""Transport v3 giữ audit/cache cũ, chặn cap/deadline cả HTTP và mọi pacing/retry wait."""

from __future__ import annotations

from datetime import datetime
import json
from typing import Any

import httpx

from core.groq_pacing import PilotStop
from core.improvement_recovery import ResilientTransport
from core.mt_bicl_v3_wire import REPLY_NAME, parse_message
from core.mt_bicl_v3_contracts import wire_schema
from agents.decision_agent import TradeDecisionOutput


class BudgetTransport(ResilientTransport):
    """Quota ngày chờ trong quỹ còn lại, không đổi key hoặc xóa reserve đã có."""

    def __init__(self, pacer: Any, cache_root: Any, budget: Any, inner: httpx.BaseTransport) -> None:
        super().__init__(pacer, cache_root, inner)
        self.runtime = budget

    def _wait(self, seconds: float) -> None:
        """Không bắt đầu chờ provider reset vượt cap/lịch; base chia mỗi lần≤30 giây."""
        self.runtime.check(seconds)
        super()._wait(seconds)
        self.runtime.checkpoint()

    def _cached(self, request: httpx.Request) -> httpx.Response | None:
        """Schema lỗi được repair cùng UUID, enum/facts sai hợp lệ vẫn để policy xử lý."""
        response = super()._cached(request)
        if response is None: return None
        body = json.loads(request.content)
        anchored = body["response_format"]["json_schema"]["name"] == REPLY_NAME
        descriptor = {"structured": {"schema": wire_schema()["$defs"]["reply"] if anchored else TradeDecisionOutput.model_json_schema()}}
        try:
            parse_message(response.json()["choices"][0]["message"], descriptor)
            return response
        except (ValueError, KeyError, TypeError, IndexError):
            response.close()
            return None

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Mọi retry nội bộ đi qua check trước network và sleep do caller bọc budget."""
        while True:
            self.runtime.check()
            try:
                return super().handle_request(request)
            except PilotStop:
                stop = self.pacer.state.get("last_stop") or {}
                until = stop.get("resume_not_before_utc")
                if stop.get("reason") != "PROVIDER_DAILY_QUOTA" or not until: raise
                delay = max(1., datetime.fromisoformat(until).timestamp()-self.pacer.clock())
                self.runtime.check(delay)
                print(f"[Quota v3] Chờ provider reset {delay:.0f} giây trong quỹ còn lại; cùng UUID.", flush=True)
                self._wait(delay)


class BudgetHTTP(httpx.BaseTransport):
    """Check cap ngay trước mỗi HTTP thật, kể cả retry 429/transport của lớp ngoài."""

    def __init__(self, budget: Any, inner: httpx.BaseTransport) -> None:
        self.budget, self.inner = budget, inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.budget.check(90.)
        return self.inner.handle_request(request)

    def close(self) -> None:
        self.inner.close()
