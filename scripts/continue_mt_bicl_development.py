"""Một lệnh chạy/tiếp tục W11-02: tự tìm checkpoint, preflight key hiện tại và giữ cùng UUID."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx
from dotenv import dotenv_values

from core.bayesian_memory import atomic_write_json, read_json
from core.groq_pacing import PilotStop
from core.improvement_recovery import ResilientPacer
from core.improvement_transport import SLOT, body_contract, validate_client
from core.mt_bicl_bank import content_hash
from core.mt_bicl_v2_api_preflight import client, preflight_request, wire_body
from core.mt_bicl_v2_continuation import (
    DEADLINE, ContinuationTransport, credential_preflight, finish_durable, inspect_prefix,
    prepare, resume_unknown, verify,
)
from core.mt_bicl_v2_decision import invoke_decision
from core.mt_bicl_v2_development import DevelopmentRun, GuardedHTTP, LOCK, RUN, verify_extension
from core.mt_bicl_v2_release import LEDGER
from core.prior_run_lock import PriorRunLock


def main() -> int:
    """Mặc định chạy tiếp; status/prepare không đọc key hoặc gọi mạng, không cần người dùng nhập UUID."""
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--status", action="store_true")
    parser.add_argument("--env-file", type=Path, default=ROOT/".env")
    args = parser.parse_args()
    with PriorRunLock(ROOT/LOCK, content_hash({"scope": "MT_BICL_DEVELOPMENT_OPERATIONS_V2"})):
        if args.prepare:
            prepare(ROOT)
            print("Nguồn resume một lệnh đã khóa offline; cần neo Git trước API.")
            return 0
        extension, manifest, requests = verify_extension(ROOT)
        policy = verify(ROOT, extension)
        runner = DevelopmentRun(ROOT, ROOT/RUN, extension, manifest, requests)
        with PriorRunLock((ROOT/LEDGER).parent/(Path(LEDGER).name+".lock"), "shared-account-ledger-v2"):
            runner.initialize()
            state = read_json(ROOT/LEDGER)
            cache = ROOT/RUN/"http_cache"
            records = inspect_prefix(runner, state, cache)
            if args.status:
                print(f"Đã lưu {sum(r['status']=='complete' for r in records)}/612; "
                      f"đang dở {sum(r['status']=='unknown' for r in records)}; chưa chạy HTTP mới.")
                return 0
            records = finish_durable(runner, state, cache, lambda: atomic_write_json(ROOT/LEDGER, state))
            if all(r["status"] == "complete" for r in records):
                runner.progress(records)
                print("Đã đủ612 slot durable; không gọi lại API. Chờ W11-03.")
                return 0
            if datetime.now(timezone.utc) > DEADLINE:
                raise ValueError("Đã đến mốc khóa dữ liệu; giữ INCOMPLETE, không gọi API mới")
            # Chỉ đọc key sau toàn bộ gate source/runtime/checkpoint; .env giữ ưu tiên như các runner trước.
            file_key = dotenv_values(args.env_file).get("GROQ_API_KEY")
            key = file_key or os.environ.get("GROQ_API_KEY", "")
            if not key:
                raise ValueError("Thiếu GROQ_API_KEY trong .env hoặc môi trường; thêm key rồi chạy lại cùng lệnh")
            print("[Credential] Dùng key từ file env đã chọn." if file_key else "[Credential] Dùng key từ biến môi trường.", flush=True)
            pacer = ResilientPacer(ROOT/LEDGER, credential=key, amendment_sha256=content_hash(extension), policy="request_admission_v2")
            preflight_dir = ROOT/RUN/"credential_preflights"
            expected: dict[str, dict[str, Any]] = {}
            transport = ContinuationTransport(pacer, preflight_dir/"http_cache", GuardedHTTP(expected, httpx.HTTPTransport(retries=0)))
            with httpx.Client(transport=transport, timeout=90.) as http:
                llm = client(manifest["decision"], http, key)
                control = preflight_request()
                expected[content_hash(control)] = body_contract(wire_body(llm, control))
                credential_preflight(preflight_dir, manifest, runner.signature, pacer, llm)
            print("[Preflight] Key hiện tại PASS; tiếp tục cùng run và checkpoint.", flush=True)
            expected = {p["canonical_sha256"]: p["http_contract"] for p in manifest["requests"]}
            transport = ContinuationTransport(pacer, cache, GuardedHTTP(expected, httpx.HTTPTransport(retries=0)))
            with httpx.Client(transport=transport, timeout=90.) as http:
                llm = client(manifest["decision"], http, key)
                validate_client(llm, "agent", manifest["decision"]["signal_config"]["models"], online=True)
                def dispatch(request: dict[str, Any], slot: dict[str, Any]) -> dict[str, Any]:
                    """HTTP tự phục hồi vẫn cùng UUID/body/model/schema; không gọi upstream mới."""
                    token = SLOT.set(slot)
                    try:
                        return invoke_decision(llm, request, attempt_id=slot["checkpoint_attempt_id"],
                                               run_signature=slot["run_signature"], branch_id=slot["branch_id"])
                    finally:
                        SLOT.reset(token)
                resume_unknown(runner, lambda: pacer.state, cache, pacer.save, dispatch, policy, pacer.credential_scope)
                result = runner.execute(dispatch, lambda: pacer.state, cache)
            print(f"Đủ {result['primary_complete']}/360 primary +{result['repeat_complete']}/252 repeat; chờ W11-03.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PilotStop as error:
        try:
            event = json.loads(str(error))
            reason = event.get("reason", "PROVIDER_STOP")
            reset = event.get("resume_not_before_utc")
        except (ValueError, TypeError):
            reason, reset = str(error), None
        print(f"Tạm dừng: {reason}; mốc provider={reset or 'chưa có'}. Giữ tiến độ; sửa điều kiện ngoài rồi chạy lại cùng lệnh.", file=sys.stderr)
        raise SystemExit(3)
    except KeyboardInterrupt:
        print("Đã tạm dừng an toàn. Khi muốn tiếp tục, chạy lại đúng lệnh này; không cần UUID hoặc reset file.", file=sys.stderr)
        raise SystemExit(3)
    except (ValueError, RuntimeError, OSError, KeyError, TypeError) as error:
        print("Dừng kiểm tra: "+str(error)+". Giữ nguyên checkpoint.", file=sys.stderr)
        raise SystemExit(1)
