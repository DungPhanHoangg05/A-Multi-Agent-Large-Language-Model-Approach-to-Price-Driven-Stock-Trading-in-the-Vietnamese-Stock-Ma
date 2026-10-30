"""Client/schema và audit raw v3; không đọc credential hoặc gọi HTTP khi serialize."""

from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import UUID

from agents.decision_agent import TradeDecisionOutput
from core.improvement_transport import body_contract, verify_attempt_audit
from core.mt_bicl_bank import content_hash
from core.mt_bicl_v2_api_preflight import client as legacy_client
from core.mt_bicl_v2_decision import invoke_decision
from core.mt_bicl_v2_io import read_envelope
from core.mt_bicl_v3_contracts import validate_wire, wire_schema
from core.mt_bicl_v3_decision import invoke_revision
from core.mt_bicl_v21_preparation import file_hash
from core.research_cohort import read_envelope as read_cache
from langchain_core.messages import HumanMessage

REPLY_NAME = "UtilityICLReplyV3"


def schema_for_sdk(schema: dict[str, Any]) -> Any:
    """Tên JSON Schema là metadata SDK; giữ nguyên properties/enum/ràng buộc đã khóa."""
    if schema == TradeDecisionOutput.model_json_schema():
        return TradeDecisionOutput
    if schema == wire_schema()["$defs"]["reply"]:
        return {"title": REPLY_NAME, **deepcopy(schema)}
    raise ValueError("Schema không thuộc hai contract v3 đã khóa")


class SchemaClient:
    """Adapter mỏng đặt tên schema dict cho LangChain, không thay hàm invoke v3 đã nghiệm thu."""

    def __init__(self, client: Any) -> None:
        self.client = client

    def with_structured_output(self, schema: dict[str, Any], **kwargs: Any) -> Any:
        return self.client.with_structured_output(schema_for_sdk(schema), **kwargs)


def client(decision: dict[str, Any], http: Any, key: str) -> SchemaClient:
    """Dùng nguyên model/options và SDK retry0, chỉ thêm adapter tên schema anchored."""
    return SchemaClient(legacy_client(decision, http, key))


def wire_body(llm: SchemaClient, request: dict[str, Any]) -> dict[str, Any]:
    """Serializer thật không gửi mạng, dùng đúng schema của request thay legacy mặc định."""
    messages, params = llm.client._create_message_dicts([HumanMessage(content=request["messages"][0]["content"])], None)
    structured = llm.with_structured_output(request["structured"]["schema"], method="json_schema", include_raw=True)
    raw = structured.steps[0].steps__["raw"]
    return {"messages": messages, **params, "response_format": raw.kwargs["response_format"]}


def parse_message(message: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    """Giữ metadata anchored đầy đủ; không ép lỗi schema hoặc enum thành CASH."""
    parsed = json.loads(message["content"])
    if request["structured"]["schema"] == TradeDecisionOutput.model_json_schema():
        from core.mt_bicl_v2_development import normalized_decision
        return normalized_decision(message)
    validate_wire(parsed, "reply")
    return parsed


def invoke(llm: SchemaClient, request: dict[str, Any], slot: dict[str, Any]) -> dict[str, Any]:
    """Mọi invocation qua retry wrapper hiện hữu, format repair vẫn cùng scientific UUID."""
    args = {"attempt_id": slot["checkpoint_attempt_id"], "run_signature": slot["run_signature"], "branch_id": slot["branch_id"]}
    if request["structured"]["schema"] == TradeDecisionOutput.model_json_schema():
        return invoke_decision(llm.client, request, **args)
    return invoke_revision(llm, request, **args)


def audit_attempt(ledger: dict[str, Any], cache: Path, slot: dict[str, Any], request: dict[str, Any],
                  contract: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str], dict[str, str]]:
    """Đọc durable success trước key/API; giữ unknown/HTTP lỗi và từ chối cache đã mất/sửa."""
    rows = [row for row in ledger["requests"] if row.get("checkpoint_attempt_id") == slot["checkpoint_attempt_id"]]
    parsed, hashes, last_message = None, {}, None
    for row in rows:
        if any(row.get(key) != slot[key] for key in ("run_signature", "point_id", "branch_id")) or row.get("recovery_policy") != "resilient_invocation_v1":
            raise ValueError("HTTP khác run/point/branch/UUID v3")
        audit = row.get("improvement_audit")
        if row["status"] == "unknown" and row.get("dispatch_phase") == "reserved" and audit is None:
            continue
        if not audit or audit["slot"] != slot or audit["request"] != contract:
            raise ValueError("HTTP audit khác body/intent v3")
        if row["status"] != 200:
            continue
        parsed, last_message = None, None
        path = cache/(str(UUID(row["id"]))+".json")
        if not path.exists():
            if row.get("durable_response") is not None: raise ValueError("Mất raw cache đã đóng dấu")
            continue
        checksum = file_hash(path)
        if row.get("durable_response") is not None and row["durable_response"] != {"sha256": checksum}:
            raise ValueError("Raw cache khác hash ledger")
        saved = read_cache(path)
        if (set(saved) != {"version", "request", "body_base64", "headers"} or saved["version"] != "resilient_invocation_v1"
                or saved["request"] != contract or set(saved["headers"])-{"content-type", "x-request-id"}):
            raise ValueError("Raw cache sai schema/body/header")
        body = base64.b64decode(saved["body_base64"], validate=True)
        if hashlib.sha256(body).hexdigest() != audit["response"]["body_sha256"]: raise ValueError("Raw cache khác response audit")
        message = json.loads(body)["choices"][0]["message"]
        try:
            value = parse_message(message, request)
        except (ValueError, KeyError, TypeError):
            parsed, last_message = None, None
            continue
        parsed, last_message = value, message
        hashes[row["id"]] = checksum
    if parsed is not None:
        verify_attempt_audit(ledger, slot, expected=contract, raw_message={"content": last_message["content"], "tool_calls": []})
    return parsed, [row["id"] for row in rows], hashes
