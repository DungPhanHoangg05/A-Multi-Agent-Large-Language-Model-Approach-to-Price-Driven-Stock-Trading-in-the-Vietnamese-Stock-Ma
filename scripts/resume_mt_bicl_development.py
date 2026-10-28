"""Phục hồi tường minh request429 theo UUID, sau đó tiếp tục runner đã freeze."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
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
from core.mt_bicl_v2_api_preflight import client, verify_live_preflight
from core.mt_bicl_v2_decision import invoke_decision
from core.mt_bicl_v2_development import DevelopmentRun, GuardedHTTP, LOCK, RUN, verify_extension
from core.mt_bicl_v2_recovery import eligible, prepare, retry_rejected, verify
from core.mt_bicl_v2_release import LEDGER
from core.prior_run_lock import PriorRunLock


def main() -> int:
    """Check không key/API; retry cần UUID tường minh và không thay CLI/runner cũ."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "check", "retry-rejected"))
    parser.add_argument("attempt_id", nargs="?")
    parser.add_argument("--env-file", type=Path, default=ROOT/".env")
    args = parser.parse_args()
    if args.command != "prepare" and not args.attempt_id:
        parser.error("Cần UUID scientific intent cần kiểm/phục hồi")
    with PriorRunLock(ROOT/LOCK, content_hash({"scope": "MT_BICL_DEVELOPMENT_OPERATIONS_V2"})):
        if args.command == "prepare":
            prepare(ROOT)
            print("Nguồn phục hồi429 đã khóa offline; cần neo Git, chưa có HTTP mới.")
            return 0
        extension, manifest, requests = verify_extension(ROOT)
        recovery = verify(ROOT, extension=extension)
        proof = verify_live_preflight(ROOT, manifest)
        runner = DevelopmentRun(ROOT, ROOT/RUN, extension, manifest, requests)
        with PriorRunLock((ROOT/LEDGER).parent/(Path(LEDGER).name+".lock"), "shared-account-ledger-v2"):
            runner.initialize()
            ledger = read_json(ROOT/LEDGER)
            i, record, rejected = eligible(runner, ledger, ROOT/RUN/"http_cache", args.attempt_id)
            print(f"Slot={i}, point={record['plan']['point_id']}, branch={record['plan']['branch_id']}; "
                  f"trạng thái={record['status']}, HTTP429={len(rejected)}.", flush=True)
            if args.command == "check":
                return 0
            if datetime.now(timezone.utc) > datetime.fromisoformat("2026-11-07T23:59:59+07:00"):
                raise ValueError("Đã tới mốc khóa dữ liệu, không retry/API mới")
            if record["status"] != "complete":
                key = dotenv_values(args.env_file).get("GROQ_API_KEY") or os.environ.get("GROQ_API_KEY", "")
                if not key:
                    raise ValueError("Thiếu GROQ_API_KEY; chưa có HTTP mới")
                pacer = ResilientPacer(ROOT/LEDGER, credential=key, amendment_sha256=content_hash(extension), policy="request_admission_v2")
                by_id = {r["id"]: r for r in pacer.state["requests"]}
                if any(by_id[rid].get("credential_scope") != pacer.credential_scope for rid in proof["request_ids"]):
                    raise ValueError("Credential khác preflight, không reset quota hoặc đổi key ngầm")
                expected = {p["canonical_sha256"]: p["http_contract"] for p in manifest["requests"]}
                transport = ResilientTransport(pacer, ROOT/RUN/"http_cache", GuardedHTTP(expected, httpx.HTTPTransport(retries=0)))
                with httpx.Client(transport=transport, timeout=90.) as http:
                    llm = client(manifest["decision"], http, key)
                    validate_client(llm, "agent", manifest["decision"]["signal_config"]["models"], online=True)
                    def dispatch(request: dict[str, Any], slot: dict[str, Any]) -> dict[str, Any]:
                        """Quota/retry/audit giữ nguyên, không thay UUID cũ hoặc scientific slot."""
                        token = SLOT.set(slot)
                        try:
                            return invoke_decision(llm, request, attempt_id=slot["checkpoint_attempt_id"],
                                                   run_signature=slot["run_signature"], branch_id=slot["branch_id"])
                        finally:
                            SLOT.reset(token)
                    retry_rejected(runner, lambda: pacer.state, ROOT/RUN/"http_cache", args.attempt_id, dispatch, recovery)
                print("Slot429 đã lưu response durable cùng UUID; tiếp tục runner gốc.", flush=True)
    return subprocess.run([sys.executable, "-X", "utf8", str(ROOT/"scripts/run_mt_bicl_development.py"),
                           "run", "--env-file", str(args.env_file)], cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Đã dừng; giữ UUID/cache/reserve/authorization, không tự replay unknown.", file=sys.stderr)
        raise SystemExit(3)
    except (ValueError, RuntimeError, OSError, KeyError, TypeError) as error:
        print("Dừng phục hồi: "+str(error), file=sys.stderr)
        raise SystemExit(1)
