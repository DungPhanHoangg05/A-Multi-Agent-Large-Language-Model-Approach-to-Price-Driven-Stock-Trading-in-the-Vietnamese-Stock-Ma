"""CLI W11-02: mặc định status offline; chỉ lệnh run/api-preflight do người dùng mới gọi API."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx
from dotenv import dotenv_values

from core.bayesian_memory import read_json
from core.improvement_recovery import ResilientPacer, ResilientTransport
from core.improvement_transport import SLOT, validate_client
from core.mt_bicl_bank import content_hash
from core.mt_bicl_v2_api_preflight import verify_live_preflight, client
from core.mt_bicl_v2_decision import invoke_decision
from core.mt_bicl_v2_development import (
    DevelopmentRun, GuardedHTTP, LOCK, OfflineDispatch, OUTPUT, RUN,
    api_preflight, prepare, verify_extension,
)
from core.mt_bicl_v2_release import LEDGER
from core.prior_run_lock import PriorRunLock


def main() -> int:
    """Một run cố định, tự resume complete; không có lọc mã/ngày/nhánh hoặc giảm N."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "verify", "dry-run", "status", "api-preflight", "run"), nargs="?", default="status")
    parser.add_argument("--env-file", type=Path, default=ROOT/".env")
    args = parser.parse_args()
    with PriorRunLock(ROOT/LOCK, content_hash({"scope": "MT_BICL_DEVELOPMENT_OPERATIONS_V2"})):
        extension, manifest, requests = prepare(ROOT) if args.command == "prepare" else verify_extension(ROOT)
        if args.command in ("prepare", "verify"):
            if args.command == "prepare":
                DevelopmentRun(ROOT, ROOT/RUN, extension, manifest, requests).initialize()
            print("Extension/source/request612 PASS; chưa đọc key hoặc gọi API; receipt cần neo Git trước run.")
            return 0
        if args.command == "dry-run":
            directory = ROOT/OUTPUT/"runner_dry_run"
            runner = DevelopmentRun(ROOT, directory, extension, manifest, requests, mode="offline_fixture")
            runner.initialize()
            fixture = OfflineDispatch(ROOT, directory, manifest)
            result = runner.execute(fixture, lambda: fixture.state, fixture.cache)
            print(f"Dry-run offline: {result['complete_slots']}/612; duplicate={result['duplicate_complete']}; "
                  f"fixture dispatch={fixture.calls}; API thật=0; không phải kết quả thị trường.")
            return 0
        runner = DevelopmentRun(ROOT, ROOT/RUN, extension, manifest, requests)
        if args.command == "status":
            if not (ROOT/RUN/"ready.json").exists():
                print("Run chưa initialized; chưa có primary/repeat hoặc API mới.")
                return 0
            records = runner.inspect(read_json(ROOT/LEDGER), ROOT/RUN/"http_cache")
            result = runner.progress(records)
            live = (ROOT/OUTPUT/"live_api_preflight.json").exists()
            if live:
                verify_live_preflight(ROOT, manifest)
            print(f"Preflight thật={'PASS' if live else 'NOT_RUN'}; primary={result['primary_complete']}/360; "
                  f"repeat={result['repeat_complete']}/252; unknown={result['unknown_slots']}; trạng thái={result['status']}.")
            return 0
        now = datetime.now(timezone.utc)
        if now > datetime.fromisoformat("2026-11-07T23:59:59+07:00"):
            raise ValueError("Đã tới mốc khóa dữ liệu, không gọi API mới")
        with PriorRunLock((ROOT/LEDGER).parent/(Path(LEDGER).name+".lock"), "shared-account-ledger-v2"):
            runner.initialize()
            ledger = read_json(ROOT/LEDGER)
            records = runner.inspect(ledger, ROOT/RUN/"http_cache", recover=True)
            if args.command == "run" and all(r["status"] == "complete" for r in records):
                result = runner.progress(records)
                print("Đã đủ612 slot durable; không gọi lại API. Chờ cold verify/account W11-03.")
                return 0
            if any(r["status"] == "unknown" for r in records):
                raise ValueError("AMBIGUOUS_DECISION: giữ UUID/reserve; không tự replay unknown")
            if (now > datetime.fromisoformat("2026-11-05T23:59:59+07:00")
                    and all(r["status"] == "pending" for r in records)):
                raise ValueError("Quá hạn mở run mới; không giảm N hoặc đổi mẫu")
            # Các gate/source/anchor/intent đã kiểm; chỉ từ đây mới được đọc credential.
            key = dotenv_values(args.env_file).get("GROQ_API_KEY") or os.environ.get("GROQ_API_KEY", "")
            if not key:
                raise ValueError("Thiếu GROQ_API_KEY; chưa có HTTP")
            proof = api_preflight(ROOT, manifest, key)
            print("Nghiệm thu API preflight W11-01 PASS; không có outcome cohort trong control request.", flush=True)
            if args.command == "api-preflight":
                return 0
            pacer = ResilientPacer(ROOT/LEDGER, credential=key, amendment_sha256=content_hash(extension), policy="request_admission_v2")
            by_id = {r["id"]: r for r in pacer.state["requests"]}
            if any(by_id[rid].get("credential_scope") != pacer.credential_scope for rid in proof["request_ids"]):
                raise ValueError("Credential khác preflight đã PASS; dừng trước primary, không reset quota")
            expected = {p["canonical_sha256"]: p["http_contract"] for p in manifest["requests"]}
            transport = ResilientTransport(pacer, ROOT/RUN/"http_cache", GuardedHTTP(expected, httpx.HTTPTransport(retries=0)))
            with httpx.Client(transport=transport, timeout=90.) as http:
                llm = client(manifest["decision"], http, key)
                validate_client(llm, "agent", manifest["decision"]["signal_config"]["models"], online=True)
                def dispatch(request: dict[str, Any], slot: dict[str, Any]) -> dict[str, Any]:
                    """SLOT audit và invocation dùng cùng scientific UUID; không gọi upstream."""
                    if datetime.now(timezone.utc) > datetime.fromisoformat("2026-11-07T23:59:59+07:00"):
                        raise ValueError("Đã tới mốc khóa dữ liệu; giữ checkpoint để tổng kết INCOMPLETE")
                    token = SLOT.set(slot)
                    try:
                        return invoke_decision(llm, request, attempt_id=slot["checkpoint_attempt_id"],
                                               run_signature=slot["run_signature"], branch_id=slot["branch_id"])
                    finally:
                        SLOT.reset(token)
                result = runner.execute(dispatch, lambda: pacer.state, ROOT/RUN/"http_cache")
            print(f"W11-02 đủ {result['primary_complete']}/360 primary +{result['repeat_complete']}/252 repeat; "
                  f"unknown={result['unknown_slots']}; chưa cold verify/account hoặc nomination W11-03–05.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Đã dừng; giữ UUID/cache/reserve/checkpoint, không tự replay unknown.", file=sys.stderr)
        raise SystemExit(3)
    except (ValueError, RuntimeError, OSError, KeyError, TypeError) as error:
        print("Dừng development, giữ bằng chứng: "+str(error), file=sys.stderr)
        raise SystemExit(1)
