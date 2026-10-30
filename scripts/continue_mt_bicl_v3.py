"""Một lệnh control/tiếp tục development v3; primary chỉ sau release đã neo Git."""

from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

import httpx
from dotenv import dotenv_values

from core.bayesian_memory import read_json
from core.groq_pacing import PilotStop
from core.improvement_recovery import ResilientPacer
from core.improvement_transport import SLOT
from core.mt_bicl_bank import content_hash
from core.mt_bicl_v2_development import GuardedHTTP
from core.mt_bicl_v2_io import read_envelope
from core.mt_bicl_v3_budget import RuntimeBudget, BudgetStop
from core.mt_bicl_v3_freeze import OUTPUT, RELEASE, RELEASE_VERSION, verify
from core.mt_bicl_v3_preflight import control_run, serialization, verify_controls
from core.mt_bicl_v3_run import DevelopmentRun
from core.mt_bicl_v3_transport import BudgetHTTP, BudgetTransport
from core.mt_bicl_v3_wire import client, invoke
from core.prior_run_lock import PriorRunLock


def main() -> int:
    """Sau controls sẽ dừng chờ release Git; resume không cần nhập UUID/reset/đổi key."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT/".env")
    args = parser.parse_args()
    with RuntimeBudget(ROOT, "development" if (ROOT/RELEASE).exists() else "API_preflight") as budget:
        with PriorRunLock(ROOT/"outputs/oos_pilot/api_usage.json.lock", "shared-account-ledger-v2"):
            manifest, snapshot = verify(ROOT, require_anchor=True)
            def sleep(seconds: float) -> None:
                """Pacer không thể ngủ vượt cap; Ctrl+C đóng counter và giữ mọi intent/reserve."""
                budget.check(seconds)
                time.sleep(min(30., seconds))
                budget.checkpoint()
                budget.check()
            expected = {}
            cache = ROOT/OUTPUT/"run/http_cache"
            with ExitStack() as stack:
                live = {}
                def start_live() -> tuple:
                    """Chỉ nạp key/HTTP khi không thể phục hồi durable; đổi key tự control riêng."""
                    if live: return live["llm"], live["pacer"]
                    file_key = dotenv_values(args.env_file).get("GROQ_API_KEY")
                    key = file_key or os.environ.get("GROQ_API_KEY", "")
                    if not key: raise ValueError("Thiếu GROQ_API_KEY; thêm key rồi chạy lại cùng lệnh")
                    pacer = ResilientPacer(ROOT/"outputs/oos_pilot/api_usage.json", credential=key, amendment_sha256=content_hash(manifest), policy="request_admission_v2", sleep=sleep)
                    transport = BudgetTransport(pacer, cache, budget, GuardedHTTP(expected, BudgetHTTP(budget, httpx.HTTPTransport(retries=0))))
                    http = stack.enter_context(httpx.Client(transport=transport, timeout=90.))
                    llm = client(snapshot["protocol"]["decision"]["config"], http, key)
                    control_run(ROOT, manifest, snapshot, pacer, llm, expected, budget)
                    live.update(llm=llm, pacer=pacer)
                    return llm, pacer
                if not (ROOT/RELEASE).exists():
                    if datetime.now(timezone.utc) > datetime.fromisoformat("2026-11-05T23:59:59+07:00"):
                        raise ValueError("Quá hạn release05/11; không mở controls/development mới")
                    start_live()
                    print("CONTROL_PREFLIGHT_PASS: đã lưu raw/cache/ledger; chưa chạy primary. Gửi kết quả để hoàn tất W11-10.")
                    return 0
                release = read_envelope(ROOT/RELEASE, RELEASE_VERSION)
                if (subprocess.check_output(["git", "show", "HEAD:"+RELEASE.as_posix()], cwd=ROOT) != (ROOT/RELEASE).read_bytes()
                        or release["manifest_sha256"] != content_hash(manifest) or release["status"] != "RELEASED_DEVELOPMENT_2023_ONLY"
                        or release["confirmation_allowed"] is not False):
                    raise ValueError("Release chưa neo Git hoặc sai phạm vi development2023")
                proof = verify_controls(ROOT, manifest, snapshot, release["control_proof"]["credential_scope"])
                if (proof != release["control_proof"] or release["development_allowed"] is not True
                        or release["decision_calls_allowed"] is not True or release["training_allowed"] is not False
                        or release["candidate_substitution_allowed"] is not False or release["source_commit"] != manifest["source_commit"]):
                    raise ValueError("Release sai control proof/source/quyền")
                runner = DevelopmentRun(ROOT/OUTPUT/"run/research", manifest, snapshot)
                def ledger() -> dict:
                    """Đọc ledger không cần key để phục hồi cache/check complete prefix."""
                    return live["pacer"].state if live else read_json(ROOT/"outputs/oos_pilot/api_usage.json")
                def dispatch(request: dict, slot: dict) -> dict:
                    """Mỗi body động phải qua serializer, guard và ledger cùng UUID đã durable."""
                    own = [row for row in ledger()["requests"] if row.get("run_signature") == runner.signature]
                    if not own and datetime.now(timezone.utc) > datetime.fromisoformat("2026-11-05T23:59:59+07:00"):
                        raise ValueError("Development chưa bắt đầu trước05/11")
                    llm, _ = start_live()
                    expected[slot["canonical_sha256"]] = serialization(llm, request)[0]
                    token = SLOT.set(slot)
                    try: return invoke(llm, request, slot)
                    finally: SLOT.reset(token)
                def reject(request: httpx.Request) -> httpx.Response:
                    raise AssertionError("Serializer không HTTP")
                offline_http = stack.enter_context(httpx.Client(transport=httpx.MockTransport(reject)))
                offline_llm = client(snapshot["protocol"]["decision"]["config"], offline_http, "offline-no-credential")
                result = runner.execute(dispatch, lambda r: serialization(offline_llm, r), ledger, cache, budget.check, budget.checkpoint)
                print(f"Đủ {result['complete_slots']}/804 slot v3; chờ W11-12 kiểm định, chưa P&L.")
        budget.checkpoint()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PilotStop as error:
        try: reason = __import__("json").loads(str(error)).get("reason", "PROVIDER_STOP")
        except (ValueError, TypeError): reason = "INVOCATION_OR_PROVIDER_STOP"
        print(f"Tạm dừng: {reason}; giữ UUID/reserve/cache/counter. Chạy lại cùng lệnh.", file=sys.stderr)
        raise SystemExit(3)
    except (KeyboardInterrupt, BudgetStop):
        print("Đã dừng, giữ counter/UUID/cache/reserve/checkpoint. Chạy lại cùng lệnh để tiếp tục trong quỹ/lịch còn lại.", file=sys.stderr)
        raise SystemExit(3)
    except (ValueError, RuntimeError, OSError, KeyError, TypeError):
        print("Dừng kiểm tra source/config/credential/schema; giữ checkpoint và raw audit, không đổi thành CASH.", file=sys.stderr)
        raise SystemExit(1)
    except Exception as error:
        print(f"Tạm dừng do {type(error).__name__}; giữ UUID/cache/ledger, chạy lại cùng lệnh. Không in credential hoặc body lỗi SDK.", file=sys.stderr)
        raise SystemExit(3)
