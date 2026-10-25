"""CLI U-BICL: producer/loader/verifier/report offline, API chỉ qua gate và readiness đã khóa."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from pathlib import Path
import os
import sys
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx
from langchain_groq import ChatGroq

from core.candidate_selection import read_technical_gates
from core.groq_pacing import tokenizer_cached
from core.historical_signals import digest
from core.improvement_recovery import ResilientPacer
from core.prior_run_lock import PriorRunLock
from core.research_cohort import read_envelope
from core.unified_bayes_cohort import CohortRun, offline_transport, preflight, lock_authorization
from core.unified_bayes_contracts import sha
from core.unified_bayes_reports import read_report, write_report
from core.unified_bayes_source import (NAMESPACE, PLAN_PATH, RUN_PATH, SOURCE, load_source, prepare_plan)
from core.unified_bayes_transport import UnifiedTransport

LEDGER = ROOT / "outputs/oos_pilot/api_usage.json"


def make_llm(models: dict[str, Any], client: httpx.Client, key: str) -> ChatGroq:
    """Giữ nguyên serializer/options đã khóa, không để SDK tự retry ngầm."""
    llm = ChatGroq(model=models["agent_llm_model"], api_key=key, temperature=models["agent_llm_temperature"],
        max_tokens=models["agent_llm_max_tokens"], max_retries=0, reasoning_effort="low", reasoning_format="hidden", http_client=client)
    llm.temperature = models["agent_llm_temperature"]
    return llm


@contextmanager
def offline_client(models: dict[str, Any], ledger: Path, cache: Path, *, read_usage: bool = False) -> Iterator[Any]:
    """Không dùng dotenv hoặc credential thật, không tạo ledger mới khi chưa có usage."""
    def reject(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Producer plan không được gọi HTTP")
    transport = offline_transport(ledger, cache) if read_usage else httpx.MockTransport(reject)
    with httpx.Client(transport=transport, timeout=90.) as client:
        yield make_llm(models, client, "offline-no-network")


def authorize(plan: dict[str, Any], gates_path: Path | None, readiness_path: Path | None) -> dict[str, Any]:
    """Source/code/gate/readiness phải PASS trước đọc key; không nhận fixture hoặc release 2025."""
    if plan["split"] != "development_2023_exploratory":
        raise ValueError("Fixture chỉ kiểm offline; xác nhận phải có producer/release riêng")
    gates = read_technical_gates(gates_path, plan)
    if gates["status"] != "PASS" or readiness_path is None:
        raise ValueError("Cần receipt bốn gate và readiness U10-09 trước API")
    if readiness_path.name.startswith(".env"):
        raise ValueError("Readiness không được trỏ vào credential")
    saved = read_envelope(readiness_path)
    expected = {"readiness_version": "unified_bic_execution_readiness_v1", "stage": "U10_09",
        "plan_sha256": digest(plan), "technical_gates_sha256": gates["sha256"],
        "request_lock_sha256": plan["request_lock_sha256"], "confirmation_allowed": False}
    if digest(saved) != digest(expected):
        raise ValueError("Readiness khác source/schedule/request/plan hoặc gate hiện tại")
    return {"technical_gates_sha256": gates["sha256"], "readiness_sha256": sha(readiness_path)}


def main() -> None:
    """Mặc định chỉ verify plan; initialize/report là ghi rõ ràng, run/resume mới được dùng key."""
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    for mode in ("prepare", "dry-run", "initialize", "preflight", "run", "verify-only", "report", "verify-report"):
        modes.add_argument("--" + mode, action="store_true")
    parser.add_argument("--plan", type=Path, default=PLAN_PATH)
    parser.add_argument("--output-dir", type=Path, default=RUN_PATH)
    parser.add_argument("--ledger", type=Path, default=LEDGER)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--repeats", action="store_true")
    parser.add_argument("--technical-gates", type=Path)
    parser.add_argument("--readiness", type=Path)
    parser.add_argument("--env-file", type=Path)
    args = parser.parse_args()
    online = args.run or args.preflight
    if (args.resume or args.repeats) and not args.run:
        parser.error("Resume/repeats chỉ dùng với --run")
    if not online and any((args.technical_gates, args.readiness, args.env_file)):
        parser.error("Gate/readiness/env-file chỉ dùng với run hoặc preflight")
    if args.ledger.resolve() != LEDGER.resolve():
        raise ValueError("Giữ nguyên ledger tài khoản chung; không reset usage hoặc đổi ledger")
    if args.plan.resolve() != PLAN_PATH.resolve() or args.output_dir.resolve() != RUN_PATH.resolve():
        raise ValueError("CLI development chỉ dùng plan/run cố định trong namespace U-BICL; không đổi W9 hoặc fixture thành run thật")
    models = read_envelope(ROOT / SOURCE / "plan.json")["inputs"]["signal_config"]["models"]
    plan_only = args.prepare or args.dry_run or not any((args.initialize, online, args.verify_only, args.report, args.verify_report))
    with offline_client(models, args.ledger, args.output_dir / "http_cache", read_usage=not plan_only and not online) as offline:
        cohort = load_source(offline)
        plan = prepare_plan(cohort, args.plan, offline) if args.prepare else cohort.read_plan(args.plan, offline)
        if plan_only:
            print(f"Plan/source/request PASS: {len(plan['requests'])} điểm, {len(plan['schedule'])} block; HTTP/Decision=0; readiness U10-09 còn riêng")
            return
        if not online:
            run = CohortRun(cohort, plan, offline, args.output_dir, args.ledger, create=args.initialize)
            if args.initialize:
                print("Run planned đã khởi tạo offline; chưa có Decision, usage mới hoặc evaluation")
                return
            with PriorRunLock(run.root, run.signature):
                report = run.report()
                if args.verify_report:
                    read_report(run.root / "report.json", report)
                elif args.report:
                    write_report(run.root / "report.json", report)
            print(f"Snapshot/report PASS: primary={report['primary']['status']}, repeat={report['repeats']['status']}; không gọi API")
            return
        authorization = authorize(plan, args.technical_gates, args.readiness)
        if not tokenizer_cached():
            raise ValueError("Thiếu tokenizer cache; chưa đọc key hoặc gọi API")
        if args.run and (args.output_dir / "cohort.json").exists() and not args.resume:
            raise ValueError("Run đã có checkpoint; cần --resume để tiếp tục đúng identity")
        with PriorRunLock(args.output_dir / "authorization_lock", digest(plan)):
            authorization = lock_authorization(args.output_dir, plan, authorization)
        # Chỉ nhánh online sau mọi kiểm tra nguồn/gate mới được đọc credential.
        from dotenv import dotenv_values
        key = dotenv_values(args.env_file or ROOT / ".env").get("GROQ_API_KEY") or os.environ.get("GROQ_API_KEY", "")
        if not key:
            raise ValueError("Thiếu GROQ_API_KEY")
        with PriorRunLock(LEDGER.parent / (LEDGER.name + ".lock"), "shared-account-ledger-v2"):
            pacer = ResilientPacer(LEDGER, credential=key, amendment_sha256=digest(authorization), policy="request_admission_v2")
            with httpx.Client(transport=UnifiedTransport(pacer, args.output_dir / "http_cache"), timeout=90.) as client:
                llm = make_llm(models, client, key)
                cohort.verify(llm)
                preflight(cohort, plan, llm, args.output_dir, execute=True)
                if args.preflight:
                    print("Preflight model/options/schema PASS; không tạo sample nghiên cứu")
                    return
                run = CohortRun(cohort, plan, llm, args.output_dir, LEDGER, create=True)
                result = run.run(repeats=args.repeats)
                with PriorRunLock(run.root, run.signature):
                    write_report(run.root / "report.json", result)
                print(f"Run/report đã lưu: primary={result['primary']['status']}, repeat={result['repeats']['status']}")


if __name__ == "__main__":
    main()
