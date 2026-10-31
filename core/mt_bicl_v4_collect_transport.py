"""Transport collection unbounded, cache trước credential; giữ retry/pacer/ledger chung."""

from __future__ import annotations

import base64
from datetime import datetime
import json
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx

from core.groq_pacing import PilotStop
from core.improvement_recovery import ResilientTransport
from core.improvement_transport import body_contract
from core.mt_bicl_v2_development import normalized_decision
from core.research_cohort import read_envelope
from core.research_invocation import CURRENT
from core.mt_bicl_v4_protocol import checksum
from core.mt_bicl_v4_completion import DataCompletionError

CONTROL_DECISION = {"decision": "SHORT", "forecast_horizon": "T+2.5", "confidence": "Thấp", "risk_reward_ratio": 1.,
    "evidence_for": "Kiểm giao thức giả lập.", "evidence_against": "Không có dữ liệu thị trường.", "justification": "Chỉ kiểm schema."}


class OfflinePending(BaseException):
    """Thiếu durable response; dừng trước HTTP/credential trong replay offline."""


def raw_body(cache: Path, row: dict[str, Any]) -> tuple[bytes, dict[str, Any]] | None:
    """Cache đóng dấu bị thiếu/sửa là lỗi integrity, không được tự gọi thay thế."""
    path = cache / (str(UUID(row["id"])) + ".json")
    proof = row.get("durable_response")
    if not path.exists():
        if proof is not None:
            raise DataCompletionError("Mất raw cache đã đóng dấu")
        return None
    if proof is not None and proof != {"sha256": checksum(path.read_bytes())}:
        raise DataCompletionError("Raw cache collection bị sửa")
    saved = read_envelope(path)
    audit = row.get("improvement_audit") or {}
    if (set(saved) != {"version", "request", "body_base64", "headers"}
            or saved["version"] != "resilient_invocation_v1" or saved["request"] != audit.get("request")
            or set(saved["headers"]) - {"content-type", "x-request-id"}):
        raise DataCompletionError("Schema raw cache/audit không hợp lệ")
    body = base64.b64decode(saved["body_base64"], validate=True)
    if checksum(body) != (audit.get("response") or {}).get("body_sha256"):
        raise DataCompletionError("Raw response khác audit HTTP")
    return body, saved


class ReplayTransport(httpx.BaseTransport):
    """Chỉ đọc cache/audit đúng UUID và canonical body; không tạo reserve hoặc mở socket."""

    def __init__(self, ledger: dict[str, Any], cache: Path) -> None:
        self.ledger, self.cache, self.used = ledger, cache, set()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        budget = CURRENT.get()
        if budget is None:
            raise DataCompletionError("Replay thiếu invocation identity")
        contract = body_contract(json.loads(request.content))
        for row in self.ledger["requests"]:
            if (row.get("run_signature") != budget.run_signature or row.get("checkpoint_attempt_id") != budget.checkpoint_attempt_id
                    or row.get("point_id") != budget.point_id or row["status"] != 200 or row["id"] in self.used):
                continue
            saved = raw_body(self.cache, row)
            if saved is None:
                continue
            body, cache = saved
            if cache["request"] != contract:
                continue
            self.used.add(row["id"])
            if budget.role.startswith("decision"):
                try:
                    decision = normalized_decision(json.loads(body)["choices"][0]["message"])
                    if budget.role == "decision_control" and decision != CONTROL_DECISION:
                        continue
                except (ValueError, KeyError, TypeError, IndexError):
                    continue
            elif budget.role in ("control_text", "control_vision"):
                try:
                    if json.loads(body)["choices"][0]["message"]["content"].strip() != "CONTROL_PASS":
                        continue
                except (ValueError, KeyError, TypeError, IndexError, AttributeError):
                    continue
            return httpx.Response(200, content=body, headers=cache["headers"], request=request)
        raise OfflinePending()


class CollectionTransport(ResilientTransport):
    """Không cap giờ/ngày/số retry; quota provider được chờ đúng reset, cùng UUID."""

    def _cached(self, request: httpx.Request) -> httpx.Response | None:
        budget = CURRENT.get()
        if budget is None:
            raise DataCompletionError("Collection thiếu invocation")
        contract = body_contract(json.loads(request.content))
        # Giữ thứ tự response khi một node từng gọi cùng body nhiều lần.
        for row in self.pacer.state["requests"]:
            key = (budget.invocation_id, row["id"])
            if (row.get("run_signature") != budget.run_signature or row.get("checkpoint_attempt_id") != budget.checkpoint_attempt_id
                    or row.get("point_id") != budget.point_id or row["status"] != 200
                    or row.get("invocation_id") == budget.invocation_id or key in self.used_cache):
                continue
            saved = raw_body(self.cache_root, row)
            if saved is None or saved[1]["request"] != contract:
                continue
            body, cache = saved
            self.used_cache.add(key)
            if budget.role.startswith("decision"):
                try:
                    decision = normalized_decision(json.loads(body)["choices"][0]["message"])
                    if budget.role == "decision_control" and decision != CONTROL_DECISION:
                        continue
                except (ValueError, KeyError, TypeError, IndexError):
                    continue
            elif budget.role in ("control_text", "control_vision"):
                try:
                    if json.loads(body)["choices"][0]["message"]["content"].strip() != "CONTROL_PASS":
                        continue
                except (ValueError, KeyError, TypeError, IndexError, AttributeError):
                    continue
            self._event("DURABLE_RESPONSE_REUSED", row)
            return httpx.Response(200, content=body, headers=cache["headers"], request=request)
        return None

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        while True:
            try:
                return super().handle_request(request)
            except PilotStop:
                stop = self.pacer.state.get("last_stop") or {}
                if stop.get("reason") != "PROVIDER_DAILY_QUOTA" or not stop.get("resume_not_before_utc"):
                    raise
                delay = max(1., datetime.fromisoformat(stop["resume_not_before_utc"]).timestamp() - self.pacer.clock())
                print(f"Quota provider: chờ reset {delay:.0f} giây; giữ UUID/cache/reserve, không trần giờ.", flush=True)
                self._wait(delay)
