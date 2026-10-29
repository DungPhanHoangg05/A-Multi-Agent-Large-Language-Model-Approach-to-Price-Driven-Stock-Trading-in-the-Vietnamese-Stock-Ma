"""Fact anchor, bypass và veto Q10ΔU nghiêm ngặt; không xử lý lỗi API thành CASH."""

from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import UUID

from agents.decision_agent import TradeDecisionOutput
from core.mt_bicl_bank import content_hash
from core.mt_bicl_v3_contracts import REVISION_BRANCHES, action, validate_branch, validate_fact_packet, validate_wire


def facts_match(reply: dict[str, Any], packet: dict[str, Any]) -> bool:
    """Chỉ chứng minh citation/enum, không tuyên bố đã kiểm mọi mâu thuẫn văn xuôi."""
    validate_fact_packet(packet)
    validate_wire(reply, "reply")
    return set(reply["fact_ids"]) == set(packet["assertions"]) and reply["fact_assertions"] == packet["assertions"]


def _request_id(value: str | None) -> None:
    """Nhánh đã gọi LLM cần UUID; bypass/offline không giả là request/cache hit."""
    if type(value) is not str:
        raise ValueError("Thiếu UUID cho response LLM")
    UUID(value)


def resolve_anchor(packet: dict[str, Any], original: dict[str, Any], anchor_reply: dict[str, Any], *,
                   original_source_sha256: str, anchor_source_sha256: str, request_id: str) -> dict[str, Any]:
    """Assertion sai dùng Original có proof ở mọi nhánh anchored; response mất/lỗi phải raise."""
    validate_fact_packet(packet)
    TradeDecisionOutput.model_validate(original, strict=True)
    valid = facts_match(anchor_reply, packet) and anchor_reply["context_reason"] == "NOT_APPLICABLE"
    _request_id(request_id)
    proof = {"point_id": packet["point_id"], "fact_packet_sha256": content_hash(packet),
             "original_source_sha256": original_source_sha256, "anchor_source_sha256": anchor_source_sha256,
             "original": deepcopy(original), "anchor_reply": deepcopy(anchor_reply), "assertions_valid": valid}
    selected = anchor_reply if valid else original
    a0 = action(selected["decision"])
    wire = {"version": "utility_icl_policy_v3", "point_id": packet["point_id"], "branch_id": "Fact_Anchor",
            "raw_proposed_action": anchor_reply["decision"], "anchor_action": a0, "final_action": a0,
            "fact_assertions_valid": valid, "eligible": valid, "anchor_source_sha256": content_hash(proof),
            "reason": "NO_NUMERIC_VETO" if valid else "ANCHOR_INVALID_USE_ORIGINAL", "q10_delta_U_net_fraction": None,
            "bypass": False, "request_id": request_id}
    for checksum in (original_source_sha256, anchor_source_sha256):
        if type(checksum) is not str or len(checksum) != 64 or any(c not in "0123456789abcdef" for c in checksum):
            raise ValueError("Thiếu hash nguồn Original/Fact_Anchor")
    validate_wire(wire, "policy")
    return {"policy": wire, "proof": proof}


def validate_anchor(anchor: dict[str, Any], packet: dict[str, Any]) -> None:
    """Phục hồi a0 từ raw/source/facts, không tin final_action do caller tự khai."""
    wire, proof = anchor["policy"], anchor["proof"]
    expected = resolve_anchor(packet, proof["original"], proof["anchor_reply"],
        original_source_sha256=proof["original_source_sha256"], anchor_source_sha256=proof["anchor_source_sha256"], request_id=wire["request_id"])
    if expected != anchor:
        raise ValueError("Anchor proof/action/source không khớp facts hiện tại")


def apply_revision(packet: dict[str, Any], anchor: dict[str, Any], branch: dict[str, Any], *,
                   reply: dict[str, Any] | None = None, request_id: str | None = None) -> dict[str, Any]:
    """Thiếu support giữ a0; đổi LONG↔CASH chỉ khi Q10ΔU>0, không catch lỗi kỹ thuật."""
    validate_anchor(anchor, packet)
    validate_branch(branch)
    name = branch["branch_id"]
    if name not in REVISION_BRANCHES or branch["point_id"] != packet["point_id"]:
        raise ValueError("Branch/point policy khác protocol")
    a0 = anchor["policy"]["final_action"]
    valid_anchor = anchor["policy"]["fact_assertions_valid"]
    eligible = branch["eligible"] and valid_anchor
    reason = branch["reason"]
    wire = {"version": "utility_icl_policy_v3", "point_id": packet["point_id"], "branch_id": name,
            "raw_proposed_action": None, "anchor_action": a0, "final_action": a0,
            "fact_assertions_valid": False, "eligible": eligible, "anchor_source_sha256": anchor["policy"]["anchor_source_sha256"],
            "reason": "ANCHOR_INVALID_USE_ORIGINAL" if not valid_anchor else "BYPASS_QUERY_FEATURE_UNAVAILABLE" if reason == "QUERY_FEATURE_UNAVAILABLE"
                      else "BYPASS_UNKNOWN_BUCKET" if reason == "UNKNOWN_BUCKET" else "BYPASS_UTILITY_UNSUPPORTED",
            "q10_delta_U_net_fraction": None, "bypass": not eligible, "request_id": request_id}
    if not eligible:
        if reply is not None or request_id is not None:
            raise ValueError("Bypass không được có response/request giả hoặc replay LLM")
    else:
        if reply is None:
            raise ValueError("Thiếu response revision; giữ checkpoint, không đổi thành policy bypass")
        _request_id(request_id)
        valid = facts_match(reply, packet) and reply["context_reason"] == "SUPPORTED"
        wire.update(raw_proposed_action=reply["decision"], fact_assertions_valid=valid)
        proposed = action(reply["decision"])
        if not valid:
            wire["reason"] = "REJECT_FACT_ASSERTIONS"
        elif proposed == a0:
            wire["reason"] = "KEEP_PROPOSED_SAME"
        elif name in ("Plain_revision", "No_utility"):
            if branch["utility"] is not None:
                raise ValueError("Nhánh bỏ utility không được nhận numeric veto")
            wire.update(final_action=proposed, reason="NO_NUMERIC_VETO")
        else:
            utility = branch["utility"]
            q10_delta = utility["q10_U_net_fraction"] if a0 == "CASH" else -utility["q90_U_net_fraction"]
            wire.update(q10_delta_U_net_fraction=float(q10_delta),
                        final_action=proposed if q10_delta > 0 else a0,
                        reason="ACCEPT_POSITIVE_Q10_DELTA_U" if q10_delta > 0 else "REJECT_NONPOSITIVE_Q10_DELTA_U")
    validate_wire(wire, "policy")
    return wire


def utility_only(packet: dict[str, Any], branch: dict[str, Any]) -> dict[str, Any]:
    """Comparator offline: LONG iff có support và Q10U>0; không dùng action/TP/SL LLM."""
    validate_fact_packet(packet)
    validate_branch(branch)
    utility = branch["utility"]
    validate_wire(utility, "utility")
    if branch["branch_id"] != "Utility_only" or utility["point_id"] != packet["point_id"] or utility["branch_id"] != "Utility_only":
        raise ValueError("Utility_only sai branch/point")
    enabled = utility["status"] == "SUPPORTED"
    wire = {"version": "utility_icl_policy_v3", "point_id": packet["point_id"], "branch_id": "Utility_only",
            "raw_proposed_action": None, "anchor_action": "CASH",
            "final_action": "LONG" if enabled and utility["q10_U_net_fraction"] > 0 else "CASH",
            "fact_assertions_valid": True, "eligible": enabled, "anchor_source_sha256": content_hash(packet),
            "reason": "UTILITY_ONLY_RULE", "q10_delta_U_net_fraction": utility["q10_U_net_fraction"], "bypass": not enabled, "request_id": None}
    validate_wire(wire, "policy")
    return wire
