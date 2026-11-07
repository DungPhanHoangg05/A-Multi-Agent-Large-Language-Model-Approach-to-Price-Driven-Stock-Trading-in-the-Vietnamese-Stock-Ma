"""Thứ tự nhánh, stream ngẫu nhiên và kiểm schema MT-BICL."""

from __future__ import annotations
from datetime import date
import hashlib
import re
from typing import Any
from jsonschema import Draft202012Validator, FormatChecker
from core.mt_bicl_bank import canonical_bytes

PROTOCOL_SHA256 = "1912d18145fcc0eb46563206a83cfbacf5420d48fd828d0f79abfb56fa0b7b48"
PREFIX = ("Original", "A_reference", "Fact_Anchor")
REVISIONS = ("Plain_revision", "MT_BICL", "No_utility", "No_target", "Stats_only")

def branch_order(j: int, repeat: int = 0) -> list[str]:
    """Khóa thứ tự slot; j luôn là index toàn cohort, duplicate không shared cache."""
    if type(j) is not int or j < 0 or type(repeat) is not int or repeat not in (0, 1, 2, 3):
        raise ValueError("Index point/repeat ngoài protocol MT-BICL")
    tail = [*REVISIONS, *(["Original_duplicate"] if repeat else [])]
    shift = ((3*j+repeat-1) if repeat else j) % len(tail)
    return [*PREFIX, *tail[shift:], *tail[:shift]]


def component_seed(protocol_sha256: str, point_id: str, component: str) -> str:
    """Seed uint128 dạng chuỗi JSON; tách stream theo component, không theo nhánh/lượt."""
    if (type(protocol_sha256) is not str or type(point_id) is not str or type(component) is not str
            or not re.fullmatch(r"[0-9a-f]{64}", protocol_sha256) or not re.fullmatch(r"(FPT|MWG|VCB|VNM)-20\d{2}-\d{2}-\d{2}", point_id)):
        raise ValueError("Protocol hash hoặc query ID seed không hợp lệ")
    date.fromisoformat(point_id[4:])
    if component not in ("lambda", "theta") and not re.fullmatch(r"magnitude\|(FPT|MWG|VCB|VNM)-20\d{2}-\d{2}-\d{2}", component):
        raise ValueError("Seed component không thuộc CRN đã khóa")
    material = "utility-v3|"+protocol_sha256+"|"+point_id+"|"+component
    return str(int.from_bytes(hashlib.sha256(material.encode("utf-8")).digest()[:16], "big"))


def validate_document(value: Any, schema: dict[str, Any]) -> None:
    """Chỉ $ref nội bộ; từ chối kiểu NumPy/nonfinite trước JSON Schema, không fetch URI."""
    canonical_bytes(value)
    def check_refs(node: Any) -> None:
        """Không cho schema truy cập file/network bên ngoài trong bước metadata."""
        if type(node) is dict:
            if "$ref" in node and not node["$ref"].startswith("#/"):
                raise ValueError("Schema không được dùng reference bên ngoài")
            for child in node.values():
                check_refs(child)
        elif type(node) is list:
            for child in node:
                check_refs(child)
    check_refs(schema)
    Draft202012Validator.check_schema(schema)
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value))
    if errors:
        raise ValueError("Tài liệu không đúng schema utility-ICL MT-BICL")
