"""Cold verify development và dựng tài khoản từ response durable; không train hoặc gọi API."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import asdict
import math
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pandas as pd

from core.backtest_engine import TestPoint, compute_account_metrics, compute_round_trip_net_return
from core.bayesian_memory import read_json
from core.execution_prices import execution_prices_for_cycle
from core.mt_bicl_bank import content_hash
from core.mt_bicl_evaluation import market_input
from core.mt_bicl_v2_adapter import VARIANTS, resolve_episode
from core.mt_bicl_v2_api_preflight import client, manifest_facts, preflight_request, verify_live_preflight, wire_body
from core.mt_bicl_v2_continuation import (
    EVENT_VERSION, PREFLIGHT_VERSION, validate_attempt, verify as verify_continuation,
)
from core.mt_bicl_v2_development import (
    DevelopmentRun, PROGRESS_VERSION, RUN, RUN_VERSION, audit_response, verify_extension,
)
from core.mt_bicl_v2_integration import reference_adapter
from core.mt_bicl_v2_io import read_envelope, write_envelope
from core.mt_bicl_v2_recovery import verify as verify_recovery
from core.mt_bicl_v2_reference import SequentialBetaOracle
from core.mt_bicl_v2_release import LEDGER, git_value
from core.mt_bicl_v2_run_manifest import MANIFEST_PATH, OUTPUT, collect
from core.mt_bicl_v2_teacher import BetaBernoulliTeacher
from core.mt_bicl_v21_preparation import OUTPUT as TEACHER, TEACHER_VERSION, file_hash
from core.improvement_transport import body_contract
from core.research_metrics import cycle_risk

VERSION = "mt_bicl_development_accounts_v2"
REPORT = OUTPUT/"verification"/"accounts.json"
CODE = ("core/mt_bicl_v2_audit.py", "scripts/verify_mt_bicl_development.py", "tests/test_mt_bicl_v2_audit.py")
ACCEPTED_LEDGER = "6de7ea8d023a9530c99d1c334ae94f248ba3c8297b7418497503cb73481b56b5"
ACCEPTED_RUN = "4e37d4809e4a0136766c53a3e46e62a811b0a316a95066ca7f121271bd936529"
OFFLINE = ("Numeric_only", "Teacher_only")


def snapshot(root: Path) -> dict[str, Any]:
    """Khóa byte của run đã nghiệm thu; output kiểm toán nằm ngoài cây này."""
    directory = root/RUN
    files = {p.relative_to(directory).as_posix(): file_hash(p) for p in sorted(directory.rglob("*")) if p.is_file()}
    if any(p.is_symlink() for p in directory.rglob("*")):
        raise ValueError("Cây run có liên kết ngoài bằng chứng đã nghiệm thu")
    result = {"ledger_sha256": file_hash(root/LEDGER), "run_files_sha256": files, "run_tree_sha256": content_hash(files)}
    if result["ledger_sha256"] != ACCEPTED_LEDGER or result["run_tree_sha256"] != ACCEPTED_RUN:
        raise ValueError("Ledger/cây run khác mốc nghiệm thu W11-02; không tự reseal")
    return result


def offline_decision(probability: float | None, available: bool) -> dict[str, Any]:
    """Ngưỡng cố định >0,5; thiếu feature giữ CASH có lý do, xác suất hỏng phải dừng."""
    if available:
        if type(probability) not in (int, float) or not math.isfinite(probability) or not 0 <= probability <= 1:
            raise ValueError("Xác suất offline không hợp lệ, không chuyển lỗi thành CASH")
    elif probability is not None:
        raise ValueError("Query thiếu feature nhưng vẫn có xác suất")
    action = "LONG" if available and probability > .5 else "CASH"
    return {"action": action, "probability": probability,
            "reason": "QUERY_FEATURE_UNAVAILABLE" if not available else "P_GT_HALF" if action == "LONG" else "P_NOT_GT_HALF"}


def check_labels(episode: dict[str, Any], bank: dict[str, Any]) -> int:
    """Đọc nhãn chỉ của context đã đóng; đối chiếu helper kinh tế, không mở y query."""
    observations = [r for task in episode["prior"] for r in task["observations"]]+episode["target"]
    for row in observations:
        original = bank[row["episode_id"]]
        outcome = original["outcome"]
        net = float(compute_round_trip_net_return(outcome["entry_open"], outcome["exit_close"]))
        if (any(row[k] != original[k] for k in ("symbol", "as_of_date", "entry_date", "exit_date", "task_id"))
                or row["exit_date"] >= episode["query"]["as_of_date"]
                or row["y"] != int(net > 0) or outcome["y"] != row["y"]
                or not math.isclose(row["r_net"], net, abs_tol=1e-12, rel_tol=0)
                or not math.isclose(outcome["r_net"], net, abs_tol=1e-12, rel_tol=0)):
            raise ValueError("Nhãn/membership context khác nguồn kinh tế hoặc vi phạm PIT")
    return len(observations)


def evaluate_cycle(frame: pd.DataFrame, events: list[dict[str, Any]], cutoff: str) -> dict[str, Any]:
    """Mở giá query sau khi mọi action đã cố định; đúng phiên Open(t+1)/Close(t+3)."""
    dates = pd.DatetimeIndex(frame.Datetime)
    if not dates.is_unique or not dates.is_monotonic_increasing:
        raise ValueError("Lịch giá không tăng duy nhất")
    index = int(dates.get_indexer([pd.Timestamp(cutoff)])[0])
    if index < 0 or index+3 >= len(dates):
        raise ValueError("Thiếu phiên thực thi T+2.5")
    entry, exit_date = (dates[index+i].strftime("%Y-%m-%d") for i in (1, 3))
    opening, closing = execution_prices_for_cycle(frame, events, cutoff, entry, exit_date)
    net = float(compute_round_trip_net_return(opening, closing))
    return {"entry_date": entry, "exit_date": exit_date, "entry_open": float(opening),
            "exit_close": float(closing), "net_return_long": net, "actual_direction": "UP" if net > 0 else "DOWN"}


def account(points: list[dict[str, Any]], branch: str) -> dict[str, Any]:
    """Một tài khoản/mã/nhánh/lượt; dùng nguyên engine và kiểm lãi kép độc lập."""
    if not points or len({p["point_id"] for p in points}) != len(points):
        raise ValueError("Tài khoản cần support không rỗng, không trùng point")
    if len({p["symbol"] for p in points}) != 1 or len({p["repeat_index"] for p in points}) != 1:
        raise ValueError("Không gộp mã hoặc repeat vào tài khoản primary")
    tests = []
    equity, peak, drawdown = 50_000_000., 50_000_000., 0.
    for i, point in enumerate(points):
        action = point["branches"][branch]["action"]
        if action not in ("LONG", "SHORT", "CASH"):
            raise ValueError("Action chưa hợp lệ, không chuyển lỗi thành CASH")
        evaluation = point["evaluation"]
        net = float(compute_round_trip_net_return(evaluation["entry_open"], evaluation["exit_close"]))
        equity *= 1+net if action == "LONG" else 1
        peak = max(peak, equity)
        drawdown = max(drawdown, (1-equity/peak)*100)
        decision = "LONG" if action == "LONG" else "SHORT"
        correct = bool((decision == "LONG") == (evaluation["actual_direction"] == "UP"))
        tests.append(TestPoint(test_id=i+1, window_start=point["as_of_date"], window_end=point["as_of_date"],
            actual_prev_close=0., actual_next_close=evaluation["exit_close"], actual_direction=evaluation["actual_direction"],
            actual_pct_change=net*100, pred_full=decision, pred_no_alpha=decision, correct_full=correct, correct_no_alpha=correct,
            confidence_full="", confidence_no_alpha="", rr_full="", rr_no_alpha="", time_full_sec=0., time_no_alpha_sec=0.,
            entry_open=evaluation["entry_open"], exit_close=evaluation["exit_close"],
            entry_time=evaluation["entry_date"], exit_time=evaluation["exit_date"]))
    metrics = asdict(compute_account_metrics(tests, fee=.0025, slippage=.001, initial_capital_vnd=50_000_000.)["full"])
    if not math.isclose(metrics["final_equity_vnd"], equity, abs_tol=1e-6, rel_tol=1e-12) or not math.isclose(metrics["max_drawdown_pct"], drawdown, abs_tol=1e-8):
        raise ValueError("Tài khoản engine lệch phép kiểm lãi kép độc lập")
    # Không xuất annualization mặc định của engine cho cohort lấy mẫu thưa.
    metrics = {k: v for k, v in metrics.items() if k not in ("sharpe_ratio", "sortino_ratio")}
    return {"point_ids": [p["point_id"] for p in points], "metrics": metrics,
            "risk": cycle_risk(metrics["period_returns"]),
            "cycles": [{"point_id": p["point_id"], "executed_action": t.executed_action_full,
                        "skip_reason": t.execution_skip_reason_full, "equity_vnd": t.equity_full_vnd,
                        "transaction_fee_vnd": t.transaction_fee_full_vnd, "slippage_cost_vnd": t.slippage_cost_full_vnd}
                       for p, t in zip(points, tests)]}


def controls(root: Path, runner: DevelopmentRun, ledger: dict[str, Any], policy: dict[str, Any]) -> dict[str, int]:
    """Kiểm proof đổi key và audit phục hồi, không đọc key hoặc ghi lại proof."""
    rows = ledger["requests"]
    original = verify_live_preflight(root, runner.manifest)
    originals = [r for r in rows if r["id"] in original["request_ids"]]
    scopes = {r["credential_scope"]: min(rows.index(x) for x in originals) for r in originals}
    proofs = sorted((root/RUN/"credential_preflights").glob("*.json"))
    def reject(request: httpx.Request) -> httpx.Response:
        """Serializer chỉ dùng mock transport từ chối mọi HTTP."""
        raise AssertionError("Không HTTP trong verifier")
    with httpx.Client(transport=httpx.MockTransport(reject)) as http:
        request = preflight_request()
        contract = body_contract(wire_body(client(runner.manifest["decision"], http, "offline-no-credential"), request))
    for path in proofs:
        proof = read_envelope(path, PREFLIGHT_VERSION)
        binding = proof["binding"]
        scope = binding["credential_scope"]
        if (path.stem != scope or proof["status"] != "PASS" or binding != {"run_signature": runner.signature,
                "manifest_sha256": content_hash(runner.manifest), "credential_scope": scope, "http_contract": contract}):
            raise ValueError("Preflight credential khác run/control đã khóa")
        slot = {"run_signature": content_hash({"credential_preflight": binding}), "point_id": "API_PREFLIGHT",
                "branch_id": "credential_preflight", "canonical_sha256": content_hash(request), "checkpoint_attempt_id": proof["attempt_id"]}
        cache = root/RUN/"credential_preflights"/"http_cache"
        checked = validate_attempt(ledger, slot, contract, cache)
        parsed, ids = audit_response(root, cache, ledger, slot, contract)
        if parsed != proof["decision"] or ids != proof["request_ids"] or any(r["credential_scope"] != scope for r in checked):
            raise ValueError("Proof credential khác raw/cache/ledger")
        scopes[scope] = min([scopes.get(scope, len(rows)), *[rows.index(r) for r in checked]])
    for i, row in enumerate(rows):
        if row.get("run_signature") == runner.signature and scopes.get(row["credential_scope"], len(rows)) >= i:
            raise ValueError("HTTP scientific trước preflight credential")
    events = sorted((root/RUN/"continuation_authorizations").glob("*.json"))
    for path in events:
        UUID(path.stem)
        event = read_envelope(path, EVENT_VERSION)
        if (event["policy_sha256"] != content_hash(policy) or event["run_signature"] != runner.signature
                or event["authorization"] != "USER_AUTHORIZED_SINGLE_COMMAND_RESUME" or event["credential_scope"] not in scopes):
            raise ValueError("Authorization khác policy/run")
        slot = event["slot"]
        from core.mt_bicl_v2_development import SLOT_VERSION
        record = read_envelope(runner.path(slot["slot_index"]), SLOT_VERSION)
        if slot != runner.dispatch_slot(slot["slot_index"], record):
            raise ValueError("Authorization khác UUID/slot")
        if any(content_hash(next(r for r in rows if r["id"] == rid)) != checksum for rid, checksum in event["previous_http_sha256"].items()):
            raise ValueError("HTTP/reserve trước retry bị sửa")
    return {"credential_preflights": len(proofs), "continuation_authorizations": len(events)}


def rebuild(root: Path) -> dict[str, Any]:
    """Tái dựng request/PIT trước khi mở outcome; không inference student hoặc đổi run cũ."""
    before = snapshot(root)
    extension, manifest, requests = verify_extension(root)
    verify_recovery(root, extension=extension)
    policy = verify_continuation(root, extension)
    runner = DevelopmentRun(root, root/RUN, extension, manifest, requests)
    for name in ("identity.json", "ready.json"):
        if read_envelope(root/RUN/name, RUN_VERSION) != runner.identity:
            raise ValueError("Identity research không hợp lệ")
    ledger = read_json(root/LEDGER)
    records = runner.inspect(ledger, root/RUN/"http_cache")
    if len(records) != 612 or any(r["status"] != "complete" for r in records):
        raise ValueError("Cần đủ612 slot durable trước kiểm toán kinh tế")
    expected_progress = {"identity": runner.identity, "status": "COMPLETE_AWAITING_W11_03", "complete_slots": 612,
        "primary_complete": 360, "repeat_complete": 252, "unknown_slots": 0, "pending_slots": 0,
        "shared_off": 121, "http_requests": 519, "duplicate_complete": 36}
    if read_envelope(root/RUN/"progress.json", PROGRESS_VERSION) != expected_progress:
        raise ValueError("Progress khác ma trận đã nghiệm thu")
    proof_counts = controls(root, runner, ledger, policy)
    print("Source/runtime/UUID/raw/cache/ledger PASS; tái dựng upstream/PIT và canonical request.", flush=True)
    data = collect(root)
    if manifest != {**manifest_facts(root, data), "source_commit": manifest["source_commit"]}:
        raise ValueError("Manifest khác canonical request được dựng lại từ nguồn PIT")
    bank = {r["episode_id"]: r for r in read_json(root/"outputs/bayesian_benchmark/mt_bicl_v1/inputs/dense_bank_v1.json")["payload"]["records"]}
    fitted = read_envelope(root/TEACHER/"teacher_fit.json", TEACHER_VERSION)
    teacher, oracle = BetaBernoulliTeacher(fitted["pi"]), SequentialBetaOracle(fitted["pi"])
    diagnostics, labels = {}, 0
    for row in data["inputs"]["rows"]:
        episode = resolve_episode(row, data["inputs"]["context"])
        labels += check_labels(episode, bank)
        pid = row["query"]["episode_id"]
        available = row["status"] == "AVAILABLE"
        p = data["variants"][pid]["Full_MT_BICL"]["probability"]
        q = None
        if available:
            packet = market_input(row, data["inputs"]["context"])
            q = teacher.predict(packet)["probability"]
            if abs(q-oracle.predict(packet)["probability"]) > 1e-12:
                raise ValueError("Teacher không khớp oracle scalar độc lập")
        diagnostics[pid] = {"episode_sha256": content_hash(episode), "status": row["status"], "reasons": row["reasons"],
            "K": row["K"], "m": row["m"], "regime": row["query"]["regime"]["name"],
            "Numeric_only": offline_decision(p, available), "Teacher_only": offline_decision(q, available)}
        if diagnostics[pid]["Numeric_only"] != data["variants"][pid]["Numeric_only"]:
            raise ValueError("Numeric khác rule/xác suất student đã khóa")
    print("Context/nhãn kinh tế và teacher oracle PASS; action offline đã cố định trước mở giá query.", flush=True)
    adapter, _ = reference_adapter(root, data["inputs"])
    prices = {s: adapter.execution_data(s) for s in manifest["decision"]["symbol_order"]}
    evaluations = {pid: evaluate_cycle(*prices[pid.split('-')[0]], pid[4:]) for pid in manifest["layout"]["point_ids"]}
    points = []
    for block in manifest["layout"]["blocks"]:
        pid, repeat = block["point_id"], block["repeat_index"]
        selected = [r for r in records if r["plan"]["point_id"] == pid and r["plan"]["repeat_index"] == repeat]
        branches = {r["plan"]["branch_id"]: {"action": r["decision"]["decision"], "slot_index": r["plan"]["slot_index"],
                    "attempt_id": r["attempt_id"], "request_ids": r["request_ids"], "shared_off_from": r["shared_off_from"]} for r in selected}
        branches.update({name: deepcopy(diagnostics[pid][name]) for name in OFFLINE})
        points.append({"point_id": pid, "symbol": pid[:3], "as_of_date": pid[4:], "repeat_index": repeat,
                       "context": deepcopy(diagnostics[pid]), "branches": branches, "evaluation": deepcopy(evaluations[pid])})
    accounts = {}
    for repeat in range(4):
        names = [*VARIANTS, *OFFLINE, *(["Original_duplicate"] if repeat else [])]
        accounts[str(repeat)] = {s: {n: account([p for p in points if p["symbol"] == s and p["repeat_index"] == repeat], n)
                                    for n in names} for s in manifest["decision"]["symbol_order"]}
    if snapshot(root) != before:
        raise ValueError("Nguồn ledger/run thay đổi trong kiểm toán")
    source_commit = git_value(root, "log", "-1", "--format=%H", "--", *CODE)
    git_value(root, "diff", "--exit-code", source_commit, "--", *CODE)
    for name in CODE:
        git_value(root, "cat-file", "-e", source_commit+":"+name)
    return {"status": "PASS", "phase": "development2023", "run_signature": runner.signature,
        "binding": {**before, "manifest_sha256": file_hash(root/MANIFEST_PATH), "source_commit": source_commit,
                    "source_sha256": {n: file_hash(root/n) for n in CODE}, "runtime": manifest["runtime"]},
        "checks": {"canonical_requests": 612, "upstream_points": 60, "context_label_occurrences": labels,
                   "available": sum(d["status"] == "AVAILABLE" for d in diagnostics.values()),
                   "http_status_counts": dict(Counter(str(r["status"]) for r in ledger["requests"] if r.get("run_signature") == runner.signature)),
                   **proof_counts, "PIT": "PASS", "economic_scalar_audit": "PASS", "student_forward_calls": 0, "real_api_calls": 0},
        "account_contract": {"initial_capital_vnd_per_symbol": 50_000_000., "fee_each_side": .0025, "slippage_each_side": .001,
                             "entry": "Open(t+1)", "exit": "Close(t+3)", "SHORT": "CASH",
                             "shares": "ENGINE_FRACTIONAL_SHARES_NO_BOARD_LOT", "repeat": "SEPARATE_SUBSAMPLE_ACCOUNTS_NOT_PRIMARY"},
        "points": points, "accounts": accounts, "nomination": "NOT_EVALUATED", "confirmation_allowed": False}


def save_or_verify(root: Path, result: dict[str, Any], *, verify_only: bool = False) -> None:
    """Không ghi đè report khác; verifier dựng lại đầy đủ trước khi so artifact."""
    path = root/REPORT
    if verify_only or path.exists():
        if read_envelope(path, VERSION) != result:
            raise ValueError("Report account khác nguồn/canonical/PIT/engine vừa dựng lại")
    else:
        write_envelope(path, VERSION, result, immutable=True)
