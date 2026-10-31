"""Cold audit v3 trước mở payoff2023, rồi tái dựng account theo engine đã khóa."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from typing import Any

import httpx

from core.bayesian_memory import read_json
from core.execution_prices import load_verified_execution_data
from core.mt_bicl_bank import content_hash
from core.mt_bicl_v2_audit import account, check_labels, evaluate_cycle
from core.mt_bicl_v2_io import read_envelope
from core.mt_bicl_v21_preparation import file_hash
from core.mt_bicl_v3_freeze import OUTPUT, VALIDATION, POINT_VERSION
from core.mt_bicl_v3_policy import utility_only
from core.mt_bicl_v3_preflight import serialization, verify_controls
from core.mt_bicl_v3_run import DevelopmentRun, SLOT_VERSION, RUN_VERSION
from core.mt_bicl_v3_unbounded import verify
from core.mt_bicl_v3_validation_inputs import visible_prices
from core.mt_bicl_v3_wire import client

VERSION = "utility_icl_development_accounts_v3"
ACCOUNTS = OUTPUT/"verification/accounts.json"
FULL = "Full_utility_ICL"
NAMES = ("Original", "A_reference", "Fact_Anchor", "Plain_revision", FULL,
         "No_utility", "No_target", "Stats_only", "Utility_only")
VIRTUAL = ("Full_raw_proposal", "Full_facts_only")
SYMBOLS = ("FPT", "MWG", "VCB", "VNM")
ACCEPTED_LEDGER_COUNT = 5206
ACCEPTED_LEDGER_PREFIX = "18d68685a15d6043c722e38b32d96a67428d5c9b2dba7638e01ffa454fe6a390"
SLOTS_SHA = "7ae447b17b5079a1344edb5c5db972fe598ad8b440e329511d10136b7704ce03"
CACHE_SHA = "e0d880143995ecdf64c48926d02c0232f84bf5453e1133c71afe0b6cddc7cccb"
PROGRESS_SHA = "ebf129d61dfc0b857e36fb9c6a4debbe1fa20b5d4f101edf9a5b9001c192d029"


def evidence(root: Path) -> dict[str, Any]:
    """Chỉ chấp nhận snapshot nghiệm thu804 slot; ledger được append ngoài prefix đã khóa."""
    result = {}
    for name, relative, expected in (("slots", "run/research/slots", SLOTS_SHA), ("cache", "run/http_cache", CACHE_SHA)):
        paths = sorted((root/OUTPUT/relative).glob("*.json"))
        if any(p.is_symlink() for p in paths): raise ValueError("Bằng chứng có symlink")
        checksums = {p.name: file_hash(p) for p in paths}
        if content_hash(checksums) != expected: raise ValueError("Cây "+name+" khác nghiệm thu W11-11")
        result[name+"_tree_sha256"] = expected
    if file_hash(root/OUTPUT/"run/research/progress.json") != PROGRESS_SHA:
        raise ValueError("Progress khác nghiệm thu804 slot")
    rows = read_json(root/"outputs/oos_pilot/api_usage.json")["requests"]
    if len(rows) < ACCEPTED_LEDGER_COUNT or content_hash(rows[:ACCEPTED_LEDGER_COUNT]) != ACCEPTED_LEDGER_PREFIX:
        raise ValueError("Prefix ledger development đã bị sửa/reset")
    result.update(ledger_prefix_count=ACCEPTED_LEDGER_COUNT, ledger_prefix_sha256=ACCEPTED_LEDGER_PREFIX,
                  progress_sha256=PROGRESS_SHA)
    return result


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


def rebuild(root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Hash/source/PIT/raw trước, action cố định tiếp, cuối cùng mới mở giá query và dựng account."""
    before = evidence(root)
    manifest, snapshot = verify(root)
    ledger = read_json(root/"outputs/oos_pilot/api_usage.json")
    ledger["requests"] = ledger["requests"][:ACCEPTED_LEDGER_COUNT]
    proofs = [verify_controls(root, manifest, snapshot, p.parent.name)
              for p in sorted((root/OUTPUT/"controls").glob("*/ready.json"))]
    scopes = {p["credential_scope"]: {rid for c in p["controls"] for rid in c["request_ids"]} for p in proofs}
    runner = DevelopmentRun(root/OUTPUT/"run/research", manifest, snapshot)
    own = [r for r in ledger["requests"] if r.get("run_signature") == runner.signature]
    for scope in {r["credential_scope"] for r in own}:
        if scope not in scopes: raise ValueError("Thiếu preflight credential")
        if max(r.get("completed_at", r["started_at"]) for r in ledger["requests"] if r["id"] in scopes[scope]) > min(r["started_at"] for r in own if r["credential_scope"] == scope):
            raise ValueError("Preflight sau HTTP scientific")
    def reject(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Không được gọi API trong cold audit")
    with TemporaryDirectory() as temporary:
        directory = Path(temporary)/"research"
        shutil.copytree(root/OUTPUT/"run/research", directory)
        check = DevelopmentRun(directory, manifest, snapshot)
        with httpx.Client(transport=httpx.MockTransport(reject)) as http:
            llm = client(snapshot["protocol"]["decision"]["config"], http, "offline-no-credential")
            progress = check.execute(reject, lambda r: serialization(llm, r), lambda: ledger,
                root/OUTPUT/"run/http_cache", lambda: None, lambda: None)
    if progress != read_envelope(root/OUTPUT/"run/research/progress.json", RUN_VERSION) or progress["complete_slots"] != 804:
        raise ValueError("Cold replay không khớp progress804 slot")
    records = [read_envelope(runner.path(i), SLOT_VERSION) for i in range(804)]
    validation = {pid: read_envelope(root/VALIDATION/"points"/(pid+".json"), POINT_VERSION)
                  for pid in manifest["layout"]["point_ids"]}
    contexts = {pid: p["context"] for pid, p in validation.items()}
    points = materialize(records, manifest, snapshot, contexts)
    for point in points:
        point["approximation"] = deepcopy(validation[point["point_id"]]["approximation"])
    print("Raw/action/UUID/control/PIT PASS; đã cố định action trước mở payoff2023.", flush=True)
    prices = visible_prices({s: load_verified_execution_data(root/"data/execution_prices_oos", s) for s in SYMBOLS})
    bank = read_json(root/"outputs/bayesian_benchmark/mt_bicl_v1/inputs/dense_bank_v1.json")["payload"]
    lookup = {r["episode_id"]: r for r in bank["records"]}
    labels = sum(check_labels(c, lookup, prices) for c in contexts.values())
    evaluations = {pid: evaluate_cycle(*prices[pid[:3]], pid[4:]) for pid in manifest["layout"]["point_ids"]}
    for point in points: point["evaluation"] = deepcopy(evaluations[point["point_id"]])
    accounts = {str(r): {s: {n: account([p for p in points if p["repeat_index"] == r and p["symbol"] == s], n)
        for n in (*NAMES, *VIRTUAL, *(("Original_duplicate",) if r else ()))} for s in SYMBOLS} for r in range(4)}
    if evidence(root) != before: raise ValueError("Bằng chứng thay đổi trong kiểm toán")
    result = {"status": "PASS", "phase": "development2023", "run_signature": runner.signature,
        "binding": before, "checks": {"slots": 804, "primary_slots": 480, "repeat_slots": 324,
            "bypass_slots": progress["bypass_slots"], "context_label_occurrences": labels, "PIT": "PASS",
            "HTTP_status_counts": dict(Counter(str(r["status"]) for r in own)), "credential_scopes": len(scopes),
            "real_API_calls": 0, "model_forward_calls": 0, "economic_contract": snapshot["protocol"]["economic_contract"]},
        "points": points, "accounts": accounts, "nomination": "NOT_EVALUATED", "confirmation_allowed": False}
    return result, snapshot["protocol"], ledger
