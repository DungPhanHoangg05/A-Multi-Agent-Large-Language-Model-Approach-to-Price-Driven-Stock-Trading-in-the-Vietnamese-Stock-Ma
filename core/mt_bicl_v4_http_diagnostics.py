"""Amendment probe synthetic và chẩn đoán HTTP; giữ nguyên request nghiên cứu."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

import httpx

from core.improvement_transport import _AuditInner
from core.mt_bicl_v4_protocol import checksum, git, read

AMENDMENT = Path("docs/plan/week11/data_collection_hotfix_v4.json")
PARENT = Path("docs/plan/week11/data_completion_release_v4.json")
PARENT_SHA = "e4420086d6c16d0d46332c22283f762f061b6dd18ad9bfb844c2787d23f25004"
SOURCES = ("core/mt_bicl_v4_completion.py", "core/mt_bicl_v4_collect_transport.py",
           "scripts/continue_mt_bicl_v4_data.py", "core/mt_bicl_v4_http_diagnostics.py",
           "tests/test_mt_bicl_v4_http_diagnostics.py")
POLICY = {"vision_control": "NEW_SYNTHETIC_ID_vision_r2_PNG_RGB_224x224_KEEP_OLD_INTENT",
          "http_errors": "SANITIZED_PROVIDER_FIELDS_AND_BODY_HASH_BEFORE_PACER_STOP",
          "research_requests_changed": False, "collection_identity_changed": False,
          "old_ledger_rows_changed": False, "hour_cap": None}


def verify_hotfix(root: Path) -> dict[str, str]:
    """Chỉ chấp nhận source đã neo Git và amendment riêng, không reseal receipt cha."""
    from core.mt_bicl_v4_completion import DataCompletionError
    if not (root / AMENDMENT).exists():
        return {}
    raw = (root / AMENDMENT).read_bytes()
    amendment = read(raw)
    if (raw != git(root, "show", "HEAD:" + AMENDMENT.as_posix())
            or set(amendment) != {"version", "parent_sha256", "source_commit", "source_sha256", "policy"}
            or amendment["version"] != "conditional_v4_collection_http_hotfix_v1"
            or amendment["parent_sha256"] != PARENT_SHA
            or checksum((root / PARENT).read_bytes()) != PARENT_SHA
            or amendment["policy"] != POLICY or set(amendment["source_sha256"]) != set(SOURCES)):
        raise DataCompletionError("Amendment HTTP/probe khác hợp đồng hoặc chưa neo Git")
    for name, sha in amendment["source_sha256"].items():
        if (checksum((root / name).read_bytes()) != sha
                or (root / name).read_bytes() != git(root, "show", amendment["source_commit"] + ":" + name)):
            raise DataCompletionError("Source HTTP/probe khác amendment: " + name)
    return amendment["source_sha256"]


def error_fields(response: httpx.Response, request: httpx.Request) -> dict[str, str]:
    """Lọc lỗi provider; loại credential, data URL và chuỗi token dài trước lưu/in."""
    try:
        error = response.json().get("error", {})
    except (ValueError, AttributeError):
        return {"message": "Provider trả lỗi không phải JSON"}
    if not isinstance(error, dict):
        return {"message": "Provider trả lỗi ngoài schema"}
    auth = request.headers.get("authorization", "")
    secrets = [value for value in (auth, auth.removeprefix("Bearer ")) if value]
    result = {}
    for name in ("code", "type", "param", "message"):
        value = error.get(name)
        if not isinstance(value, (str, int, float, bool)):
            continue
        text = str(value)
        for secret in secrets:
            text = text.replace(secret, "[ĐÃ ẨN]")
        text = re.sub(r"data:[^\s\"']+", "[ẢNH ĐÃ ẨN]", text, flags=re.I)
        text = re.sub(r"(?i)\bBearer\s+\S+|\b(?:gsk_|sk-)[A-Za-z0-9_-]+|[A-Za-z0-9_+/=-]{48,}", "[ĐÃ ẨN]", text)
        result[name] = " ".join(text.split())[:1000]
    return result or {"message": "Provider không trả chi tiết lỗi"}


class DiagnosticInner(_AuditInner):
    """Ghi lỗi trước khi pacer ném PilotStop; không retry hoặc sửa request/ledger."""

    def __init__(self, pacer: Any, cache: Path, inner: httpx.BaseTransport) -> None:
        super().__init__(pacer, inner)
        self.directory = cache.parent / "http_errors"

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        response = super().handle_request(request)
        if response.status_code >= 400:
            from core.mt_bicl_v4_dataset import immutable
            row = self.pacer.state["requests"][-1]
            fields = error_fields(response, request)
            evidence = {"version": "conditional_v4_http_error_v1", "request_id": row["id"],
                        "checkpoint_attempt_id": row.get("checkpoint_attempt_id"),
                        "point_id": row.get("point_id"), "model": row["model"],
                        "status": int(response.status_code), "body_sha256": checksum(response.content),
                        "error": fields}
            immutable(self.directory / (row["id"] + ".json"), evidence)
            print(f"[Provider HTTP {response.status_code}] point={row.get('point_id')}; model={row['model']}; "
                  + json.dumps(fields, ensure_ascii=False), flush=True)
        return response

