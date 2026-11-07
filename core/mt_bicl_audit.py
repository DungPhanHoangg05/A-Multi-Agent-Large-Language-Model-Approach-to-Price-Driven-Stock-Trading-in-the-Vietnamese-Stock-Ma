"""Cố định actions và phân rã policy trước khi truy cập outcome."""

from __future__ import annotations
from copy import deepcopy
from typing import Any
from core.mt_bicl_policy import utility_only

FULL = "MT_BICL"
NAMES = ("Original", "A_reference", "Fact_Anchor", "Plain_revision", FULL,
         "No_utility", "No_target", "Stats_only", "Utility_only")
VIRTUAL = ("Full_raw_proposal", "Full_facts_only")
SYMBOLS = ("FPT", "MWG", "VCB", "VNM")

def cash_action(value: str) -> str:
    """SHORT là CASH; lỗi/missing action không được ép thành giữ tiền."""
    if value not in ("LONG", "SHORT", "CASH"): raise ValueError("Action không hợp lệ")
    return "LONG" if value == "LONG" else "CASH"


def materialize(records: list[dict[str, Any]], manifest: dict[str, Any], snapshot: dict[str, Any], contexts: dict[str, Any]) -> list[dict[str, Any]]:
    """Cố định toàn bộ raw/final/offline/counterfactual trước khi đọc payoff query."""
    slots = manifest["layout"]["slots"]
    if len(records) != len(slots) or any(r["status"] != "complete" or r["slot"] != s for r, s in zip(records, slots)):
        raise ValueError("Action chưa complete đúng toàn bộ manifest")
    by_block: dict[tuple[str, int], dict[str, Any]] = {}
    for record in records:
        slot = record["slot"]
        key = slot["point_id"], slot["repeat_index"]
        name = slot["branch_id"]
        group = by_block.setdefault(key, {})
        if name in group: raise ValueError("Nhánh trùng trong block")
        policy = record["policy"]
        proposed = record["decision"]["decision"] if record["decision"] is not None else None
        final = policy["final_action"] if policy is not None else proposed
        group[name] = {"action": cash_action(final), "raw_proposed_action": proposed,
            "raw_decision": deepcopy(record["decision"]), "policy": deepcopy(policy), "bypass": record["bypass"],
            "slot_index": slot["slot_index"], "attempt_id": record["attempt_id"], "request_ids": record["request_ids"]}
    points = []
    for block in manifest["layout"]["blocks"]:
        pid, repeat = block["point_id"], block["repeat_index"]
        branches = deepcopy(by_block[(pid, repeat)])
        if set(branches) != set(block["order"]): raise ValueError("Block thiếu nhánh đã khóa")
        if pid[4:8] != "2023" or pid[:3] not in SYMBOLS: raise ValueError("Không mở payoff ngoài development2023")
        source, context = snapshot["points"][pid], contexts[pid]
        offline = utility_only(source["facts"], source["variants"]["Utility_only"])
        if offline != source["offline_utility_only"]: raise ValueError("Utility_only khác frozen policy")
        branches["Utility_only"] = {"action": cash_action(offline["final_action"]), "policy": offline,
                                    "raw_proposed_action": None, "bypass": offline["bypass"]}
        policy = branches[FULL]["policy"]
        a0 = cash_action(policy["anchor_action"])
        raw = branches[FULL]["raw_proposed_action"]
        proposal = cash_action(raw) if raw is not None else a0
        facts_only = proposal if policy["fact_assertions_valid"] and policy["eligible"] else a0
        branches[VIRTUAL[0]] = {"action": proposal, "diagnostic_only": True}
        branches[VIRTUAL[1]] = {"action": facts_only, "diagnostic_only": True}
        full = source["variants"][FULL]
        removed = source["variants"]["No_target"]
        points.append({"point_id": pid, "symbol": pid[:3], "as_of_date": pid[4:], "repeat_index": repeat,
            "context": {"K": context["K"], "m": context["m"], "status": context["status"],
                "regime": context["query"]["regime"]["name"], "bucket": source["facts"]["bucket"],
                "full_supported": full["eligible"], "no_target_supported": removed["eligible"],
                "probability_full": full["probability"], "probability_no_target": removed["probability"],
                "utility_full": full["utility"], "utility_no_target": removed["utility"]}, "branches": branches})
    return points
