"""Biên JSON/schema và context v3; không cấp quyền chạy hoặc thay bản khóa v2."""

from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from core.mt_bicl_bank import canonical_bytes, content_hash
from core.mt_bicl_tasks import validate_episode

SCHEMA_SHA256 = "61a426b75ee2464e9644d503ed5a9530565248f3fde888c999f680db23721057"
QUERY_KEYS = {"episode_id", "symbol", "as_of_date", "entry_date", "exit_date", "calendar_index",
              "block_index", "task_id", "raw", "z", "model_vector", "feature_status", "regime"}
FORBIDDEN = {"supervised_target", "query_y", "outcome", "evaluation", "actual_direction",
             "actual_pct_change", "entry_open", "exit_close", "net_return", "net_return_pct"}
REVISION_BRANCHES = ("Plain_revision", "Full_utility_ICL", "No_utility", "No_target", "Stats_only")
UTILITY_BRANCHES = ("Full_utility_ICL", "No_target", "Stats_only", "Utility_only")


@lru_cache(maxsize=1)
def wire_schema() -> dict[str, Any]:
    """Đọc schema nội bộ đúng byte protocol; không resolve URL hoặc đọc key."""
    path = Path(__file__).resolve().parents[1]/"docs/plan/week11/utility_icl_v3.schema.json"
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != SCHEMA_SHA256:
        raise ValueError("Schema v3 khác byte đã khóa")
    return json.loads(data)


@lru_cache(maxsize=4)
def _validator(definition: str) -> Draft202012Validator:
    """Chỉ cho phép bốn định nghĩa cục bộ của schema đã khóa."""
    if definition not in ("fact_packet", "reply", "utility", "policy"):
        raise ValueError("Định nghĩa schema v3 không hợp lệ")
    schema = {"$ref": "#/$defs/"+definition, "$defs": wire_schema()["$defs"]}
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validate_wire(value: dict[str, Any], definition: str) -> None:
    """Từ chối NumPy/nonfinite/bool giả số trước kiểm wire schema."""
    canonical_bytes(value)
    if list(_validator(definition).iter_errors(value)):
        raise ValueError("Dữ liệu không đúng schema v3: "+definition)


def action(value: str) -> str:
    """SHORT luôn giữ CASH, không có vị thế bán khống."""
    if type(value) is not str or value not in ("LONG", "SHORT", "CASH"):
        raise ValueError("Action không thuộc LONG/SHORT/CASH")
    return "LONG" if value == "LONG" else "CASH"


def validate_fact_packet(packet: dict[str, Any]) -> None:
    """Kiểm quan hệ số/enum và ngày; schema đơn thuần không chứng minh facts đúng."""
    validate_wire(packet, "fact_packet")
    if (packet["point_id"].split("-", 1)[1] != packet["as_of_date"]
            or packet["frame_end_date"] > packet["as_of_date"]):
        raise ValueError("Facts khác point/cutoff")
    n = packet["numeric"]
    def relation(left: float | None, right: float | None) -> str:
        """So sánh cùng float64 đã ghi, zero không được đổi thành missing."""
        return "UNKNOWN" if left is None or right is None else "ABOVE" if left > right else "BELOW" if left < right else "EQUAL"
    for difference, left, right in (("macd_minus_signal", "macd", "signal"), ("close_minus_sma20", "close", "sma20")):
        expected = None if n[left] is None or n[right] is None else n[left]-n[right]
        if n[difference] != expected:
            raise ValueError("Sai dấu/hiệu số trong fact packet")
    assertions = {"MACD_SIGNAL": relation(n["macd"], n["signal"]),
                  "MACD_ZERO": {"ABOVE": "POSITIVE", "BELOW": "NEGATIVE", "EQUAL": "ZERO", "UNKNOWN": "UNKNOWN"}[relation(n["macd"], 0.)],
                  "PRICE_SMA20": relation(n["close"], n["sma20"])}
    axes = [n["macd_minus_signal"], n["close_minus_sma20"]]
    expected_bucket = "UNKNOWN" if any(value is None or value == 0 for value in axes) else "MACD_"+("POS" if axes[0] > 0 else "NEG")+"_PRICE_"+("POS" if axes[1] > 0 else "NEG")
    if packet["assertions"] != assertions or packet["bucket"] != expected_bucket:
        raise ValueError("Fact enums/bucket không đúng số raw")
    if (packet["prefix_rows"] < 45 or packet["frame_end_date"] != packet["as_of_date"]) and any(value is not None for value in n.values()):
        raise ValueError("Facts không đủ prefix45 vẫn có số được khai là hợp lệ")


def validate_branch(branch: dict[str, Any]) -> None:
    """Không tin cờ eligible khi utility/hash/projection tương ứng bị lỗi hoặc đổi point."""
    canonical_bytes(branch)
    name = branch["branch_id"]
    if name not in (*REVISION_BRANCHES, "Utility_only") or type(branch["eligible"]) is not bool:
        raise ValueError("Nhánh v3 hoặc mask eligibility không hợp lệ")
    if branch["eligible"] != (branch["reason"] == "SUPPORTED"):
        raise ValueError("Mask eligibility không khớp reason")
    projection = branch["projection"]
    if (branch["eligible"] and name != "Utility_only") != (projection is not None):
        raise ValueError("Projection không khớp mask eligibility")
    if projection is not None and projection["membership_sha256"] != branch["membership_sha256"]:
        raise ValueError("Projection khác membership branch")
    if branch["eligibility_source_membership_sha256"] != branch["membership_sha256"]:
        raise ValueError("Mask eligibility khác membership branch")
    if name in ("Plain_revision", "No_utility"):
        if branch["utility"] is not None or (name == "Plain_revision" and branch["probability"] is not None):
            raise ValueError("Ablation nhận p/U ngoài hợp đồng")
    else:
        wire = branch["utility"]
        validate_wire(wire, "utility")
        if (wire["branch_id"] != name or wire["point_id"] != branch["point_id"]
                or wire["membership_sha256"] != branch["membership_sha256"]
                or wire["reason"] != branch["reason"] or wire["probability_student"] != branch["probability"]
                or (wire["status"] == "SUPPORTED") != branch["eligible"]
                or (branch["eligible"] and wire["q10_U_net_fraction"] > wire["q90_U_net_fraction"])):
            raise ValueError("Utility/point/membership không khớp branch")


def membership_hash(episode: dict[str, Any]) -> str:
    """Bind toàn context được chọn, query/scaler và chứng cứ bucket, không chỉ ID."""
    return content_hash({key: episode[key] for key in ("query", "scaler", "prior", "target", "v3")})


def validate_context(episode: dict[str, Any]) -> None:
    """Khóa query không nhãn và bucket trước mọi projection, inference hoặc utility."""
    if (type(episode) is not dict or FORBIDDEN.intersection(episode)
            or type(episode.get("query")) is not dict or set(episode["query"]) != QUERY_KEYS):
        raise ValueError("Context v3 chứa outcome hoặc trường query ngoài hợp đồng")
    validate_episode(episode)
    meta = episode["v3"]
    facts = meta["query_facts"]
    validate_fact_packet(facts)
    if (meta["version"] != "utility_icl_context_v3" or facts["point_id"] != episode["query"]["episode_id"]
            or facts["as_of_date"] != episode["query"]["as_of_date"]
            or facts["frame_end_date"] > facts["as_of_date"]
            or meta["bucket"] != facts["bucket"]
            or episode["membership_sha256"] != membership_hash(episode)):
        raise ValueError("Context/bucket/hash không cùng query")
    rows = [r for task in episode["prior"] for r in task["observations"]]+episode["target"]
    proofs = meta["historical_facts"]
    needed = {r["episode_id"] for r in rows}
    needed.update(identifier for task in episode["prior"] for identifier in task["centroid_fit_ids"])
    if set(proofs) != needed:
        raise ValueError("Thiếu/thừa proof bucket của membership/centroid")
    for identifier, packet in proofs.items():
        validate_fact_packet(packet)
        if (packet["point_id"] != identifier or packet["frame_end_date"] != packet["as_of_date"]
                or packet["as_of_date"] >= facts["as_of_date"] or packet["prefix_rows"] != 45
                or packet["bucket"] == "UNKNOWN" or packet["bucket"] != meta["bucket"]):
            raise ValueError("Membership/centroid khác bucket hoặc chứa future")
    if ((meta["bucket"] == "UNKNOWN" or facts["prefix_rows"] < 45 or episode["status"] != "AVAILABLE")
            and (episode["K"] or episode["m"])):
        raise ValueError("Query thiếu feature/bucket không được có context được chọn")


def without_target(episode: dict[str, Any]) -> dict[str, Any]:
    """Ablation bỏ C và proof chỉ thuộc C, giữ nguyên D/query rồi bind membership mới."""
    validate_context(episode)
    result = deepcopy(episode)
    result.update(target=[], m=0, reasons=[*episode["reasons"], "TARGET_DISABLED"])
    kept = {identifier for task in result["prior"] for identifier in task["centroid_fit_ids"]}
    result["v3"]["historical_facts"] = {key: packet for key, packet in result["v3"]["historical_facts"].items() if key in kept}
    result["membership_sha256"] = membership_hash(result)
    validate_context(result)
    return result
