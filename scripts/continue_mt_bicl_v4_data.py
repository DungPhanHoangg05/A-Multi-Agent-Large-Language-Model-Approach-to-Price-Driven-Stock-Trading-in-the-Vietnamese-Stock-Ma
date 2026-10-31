"""Một lệnh warmup → preflight → agent/Original → audit dữ liệu; API do người dùng chạy."""

from __future__ import annotations

import argparse
import base64
from copy import deepcopy
import io
import json
from pathlib import Path
import socket
import sys
from typing import Any
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx
from PIL import Image

from agents.decision_agent import TradeDecisionOutput
from core.groq_pacing import PilotStop
from core.historical_signals import native_json
from core.improvement_recovery import ResilientPacer
from core.improvement_transport import SLOT
from core.mt_bicl_v2_decision import invoke_decision
from core.mt_bicl_v4_collect import assemble, audit_http, clients, collect_point
from core.mt_bicl_v4_collect_transport import CONTROL_DECISION, CollectionTransport, OfflinePending, ReplayTransport
from core.mt_bicl_v4_completion import BASE, DIRECTORY, RELEASE, DataCompletionError, prepare, verify_release
from core.mt_bicl_v4_dataset import immutable
from core.mt_bicl_v4_protocol import canonical, checksum, read
from core.mt_bicl_v4_warmup import PendingWarmup, load_warmup
from core.prior_run_lock import PriorRunLock
from core.research_cohort import read_envelope, save_envelope
from core.research_invocation import CURRENT, ENABLED, RECOVERY, invocation_scope
from utils.historical_api import _invoke_with_retry
from scripts.prepare_groq_tokenizer import prepare_tokenizer


def control_requests() -> list[dict[str, Any]]:
    """Ba probe synthetic, không point/giá/nhãn thị trường; một probe có ảnh thật8×8."""
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (255, 0, 0)).save(buf, format="PNG")
    plain = "CONTROL ONLY. Chỉ trả chính xác CONTROL_PASS. Không có dữ liệu thị trường."
    expected = deepcopy(CONTROL_DECISION)
    return [{"id": "text", "role": "agent", "content": plain},
        {"id": "vision", "role": "graph", "content": [{"type": "text", "text": plain},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()}}]},
        {"id": "original", "role": "agent", "content": "CONTROL ONLY: Trả JSON đúng schema và nội dung sau: " + json.dumps(expected, ensure_ascii=False), "expected": expected}]


def controls(root: Path, release: dict[str, Any], signature: str, llms: tuple[Any, Any], pacer: Any) -> None:
    """Mỗi scope credential có intent/probe riêng; không xóa proof cũ khi đổi key."""
    scope = pacer.credential_scope
    control_signature = checksum(canonical({"collection": signature, "scope": scope, "purpose": "SYNTHETIC_ONLY"}))
    for request in control_requests():
        pid = "CONTROL_V4_" + request["id"]
        path = root / DIRECTORY / "controls" / scope / (request["id"] + ".json")
        if path.exists():
            saved = read_envelope(path)
            if saved["request"] != request or saved["signature"] != control_signature:
                raise DataCompletionError("Control khác request/scope")
        else:
            saved = {"signature": control_signature, "request": request, "attempt_id": str(uuid4()), "status": "unknown", "http": None, "result": None}
            save_envelope(path, saved)
        if saved["status"] == "complete":
            proof = audit_http(pacer.state, root / DIRECTORY / "http_cache", control_signature, pid, {saved["attempt_id"]})
            if proof != saved["http"]:
                raise DataCompletionError("Raw/ledger control đã đổi")
            if saved["result"] != (request["expected"] if request["id"] == "original" else "CONTROL_PASS"):
                raise DataCompletionError("Nội dung control complete bị sửa")
            continue
        from langchain_core.messages import HumanMessage
        enable, recovery = ENABLED.set(True), RECOVERY.set(True)
        try:
            with invocation_scope("decision_control" if request["id"] == "original" else "control_" + request["id"]) as budget:
                budget.run_signature, budget.point_id, budget.branch_id = control_signature, pid, "control_" + request["id"]
                budget.checkpoint_attempt_id = saved["attempt_id"]
                token = SLOT.set({"run_signature": control_signature, "point_id": pid, "branch_id": budget.branch_id, "checkpoint_attempt_id": saved["attempt_id"]})
                try:
                    if request["id"] == "original":
                        value = invoke_decision(llms[0], {"point_id": pid, "structured": {"schema": TradeDecisionOutput.model_json_schema()},
                            "messages": [{"role": "user", "content": request["content"]}]}, attempt_id=saved["attempt_id"], run_signature=control_signature, branch_id=budget.branch_id)
                        if value != request["expected"]:
                            raise DataCompletionError("Control Original sai nội dung synthetic")
                    else:
                        llm = llms[0 if request["role"] == "agent" else 1]
                        value = _invoke_with_retry(llm.invoke, [HumanMessage(content=request["content"])]).content
                        if not isinstance(value, str) or value.strip() != "CONTROL_PASS":
                            raise DataCompletionError("Control text/vision sai nội dung synthetic")
                finally:
                    SLOT.reset(token)
        finally:
            ENABLED.reset(enable)
            RECOVERY.reset(recovery)
        proof = audit_http(pacer.state, root / DIRECTORY / "http_cache", control_signature, pid, {saved["attempt_id"]})
        if not proof["raw_sha256"]:
            raise DataCompletionError("Control thiếu raw200")
        saved.update(status="complete", result=native_json(value), http=proof)
        save_envelope(path, saved)


def run(root: Path, release: dict[str, Any], *, offline: bool = False) -> dict[str, Any]:
    """Cache được replay bằng client fixture trước khi đọc credential; complete không API."""
    fetch = None
    if not offline:
        from scripts.verify_execution_price_gate import fetch_paginated
        fetch = fetch_paginated
    frames, warmup = load_warmup(root, release, fetch=fetch)
    identity = {"release_sha256": checksum((root / RELEASE).read_bytes()), "warmup": warmup,
                "point_ids_sha256": checksum(canonical(release["point_ids"]))}
    immutable(root / DIRECTORY / "identity.json", identity)
    signature = checksum(canonical(identity))
    rows = read((root / BASE / "observations.json").read_bytes())["rows"]
    news = {s: read(root.joinpath(f"outputs/historical_memory_run/inputs/news/{s}.json").read_bytes())["scored_articles"]
            for s in release["config"]["symbol_order"]}
    ledger_path = root / "outputs/oos_pilot/api_usage.json"
    current_ledger = read(ledger_path.read_bytes())
    cache = root / DIRECTORY / "http_cache"
    replay_http = httpx.Client(transport=ReplayTransport(current_ledger, cache), timeout=90.)
    replay_llms = None
    online_http, online_llms, pacer = None, None, None
    completed = []
    try:
        for row in rows:
            pid = row["episode_id"]
            point_path = root / DIRECTORY / "points" / pid / "complete.json"
            if not point_path.exists() and replay_llms is None:
                replay_llms = clients(release["config"], replay_http, "offline-fixture-not-a-credential")
            try:
                result = collect_point(root, row, frames[row["symbol"]], news[row["symbol"]], release, signature,
                    replay_llms, lambda: pacer.state if pacer is not None else current_ledger)
            except OfflinePending:
                if offline:
                    return {"status": "WAITING_USER_API", "complete_points": len(completed), "next_point": pid}
                if online_llms is None:
                    # Đây là đường chạy do người dùng gọi, sau khi đã thử hết durable cache.
                    prepare_tokenizer()
                    from dotenv import dotenv_values
                    values = dotenv_values(root / ".env")
                    key = values.get("GROQ_API_KEY")
                    if not key:
                        raise DataCompletionError("Cần GROQ_API_KEY cho phần collection còn thiếu")
                    pacer = ResilientPacer(ledger_path, credential=key, amendment_sha256=checksum((root / RELEASE).read_bytes()), policy="request_admission_v2")
                    online_http = httpx.Client(transport=CollectionTransport(pacer, cache), timeout=90.)
                    online_llms = clients(release["config"], online_http, key)
                    controls(root, release, signature, online_llms, pacer)
                previous = {r["id"]: checksum(canonical(r)) for r in pacer.state["requests"]}
                event = {"authority": release["resume"], "point_id": pid, "signature": signature,
                         "previous_point_rows": {r["id"]: checksum(canonical(r)) for r in pacer.state["requests"] if r.get("run_signature") == signature and r.get("point_id") == pid}}
                immutable(root / DIRECTORY / "resume_events" / (str(uuid4()) + ".json"), event)
                result = collect_point(root, row, frames[row["symbol"]], news[row["symbol"]], release, signature, online_llms, lambda: pacer.state)
                actual = {r["id"]: checksum(canonical(r)) for r in pacer.state["requests"]}
                if any(actual.get(rid) != sha for rid, sha in previous.items()):
                    raise DataCompletionError("Collection sửa HTTP/reserve cũ")
                # Replay tiếp theo phải thấy raw mới, không dùng ledger snapshot lúc đầu run.
                replay_http._transport.ledger = pacer.state
            completed.append(result)
            if not offline or len(completed) % 50 == 0:
                print(f"Đã lưu/đối soát {len(completed)}/{len(rows)} point; {pid}; chưa train hoặc phân tích P&L.", flush=True)
        verify_release(root)
        return assemble(root, release, signature, completed, warmup)
    finally:
        replay_http.close()
        if online_http is not None:
            online_http.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--prepare", action="store_true", help="Chỉ khóa release offline sau commit source")
    group.add_argument("--verify-only", action="store_true", help="Chỉ kiểm/replay cache, không đọc credential hoặc API")
    args = parser.parse_args()
    if args.prepare or args.verify_only:
        from scripts.verify_mt_bicl_protocol_v4 import reject_network
        socket.create_connection = reject_network
        socket.socket.connect = reject_network
    try:
        with PriorRunLock(ROOT / DIRECTORY / "run.lock", "conditional-v4-data-completion"):
            with PriorRunLock(ROOT / "outputs/oos_pilot/api_usage.json.lock", "shared-account-ledger-v2"):
                if args.prepare:
                    release = prepare(ROOT)
                    print(f"COLLECTION_RELEASE_PREPARED: {release['points']} point; không API, không trần giờ/ngày.")
                    return 0
                release = verify_release(ROOT)
                try:
                    result = run(ROOT, release, offline=args.verify_only)
                except PendingWarmup:
                    if not args.verify_only:
                        raise
                    print("WAITING_USER_WARMUP_AND_API: release/source PASS; chưa có warmup, không đọc key/API.")
                    return 0
                print(f"W11-18: {result['status']}; đủ point={result.get('points', result.get('complete_points', 0))}; chưa tự mở W11-19.")
                return 0
    except PilotStop as error:
        try:
            reason = json.loads(str(error)).get("reason", "PROVIDER_OR_INVOCATION_STOP")
        except (ValueError, TypeError, AttributeError):
            reason = "PROVIDER_OR_INVOCATION_STOP"
        print(f"Dừng do {reason}; giữ UUID/cache/reserve. Chạy lại cùng lệnh sau khi xử lý nguyên nhân, không đổi model/key ngầm.")
        return 3
    except KeyboardInterrupt:
        print("Đã dừng; giữ UUID/cache/reserve/checkpoint. Chạy lại cùng lệnh để tiếp tục, không trần giờ/ngày.")
        return 3
    except DataCompletionError as error:
        print(f"Dừng kiểm tra: {error}; giữ bằng chứng và UUID.", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"Dừng kiểm tra do {type(error).__name__}; giữ bằng chứng. Chạy lại cùng lệnh; lỗi integrity cần đối soát, không đổi key hoặc xóa dữ liệu ngầm.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
