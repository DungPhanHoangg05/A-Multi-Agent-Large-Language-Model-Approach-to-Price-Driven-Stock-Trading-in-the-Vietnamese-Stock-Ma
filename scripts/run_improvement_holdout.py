"""CLI holdout riêng: offline mặc định; chỉ người dùng chạy API sau bàn giao W8."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx
from dotenv import dotenv_values

from core.backtest_engine import BacktestEngine
from core.candidate_selection import read_technical_gates
from core.historical_signals import digest
from core.improvement_bootstrap import bootstrap_report, read_bootstrap
from core.improvement_holdout import NAMESPACE, prepare_plan, sha, validate_plan, verified_development
from core.improvement_holdout_runtime import run_holdout
from core.improvement_recovery import ResilientPacer, ResilientTransport, recovery_scope
from core.improvement_reports import read_report
from core.improvement_transport import validate_client
from core.pilot_readiness import build_adapter
from core.prior_backtest import PriorBacktestRunner
from core.prior_run_lock import PriorRunLock
from core.research_cohort import read_envelope
from core.research_input_lock import _write_once
from core.research_invocation import ENABLED, invocation_scope
from scripts.run_bayesian_ablation import make_builder, preflight


def release_artifact(plan: dict[str, Any], gates: dict[str, Any], plan_file: Path) -> dict[str, Any]:
    """Receipt bàn giao riêng chỉ sau bốn gate PASS; chưa tạo run hoặc gọi API."""
    if plan['split'] != 'holdout_2024' or gates['status'] != 'PASS':
        raise ValueError('Bàn giao chỉ nhận holdout thật và bốn gate PASS')
    return {'release_version': 'improvement_holdout_release_v1', 'plan_file_sha256': sha(plan_file),
        'plan_sha256': digest(plan), 'technical_gates_sha256': gates['sha256'],
        'code_sha256': plan['code_sha256'], 'runtime': plan['runtime'], 'risk_policy': 'OFF'}


def main() -> None:
    """Giữ CLI/69 dependency development nguyên byte; chặn online trước đọc key."""
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    for name in ('prepare', 'dry-run', 'release', 'preflight', 'run', 'verify-only', 'verify-report', 'bootstrap', 'verify-bootstrap'):
        modes.add_argument('--'+name, action='store_true')
    parser.add_argument('--plan', type=Path, default=ROOT/NAMESPACE/'plan.json')
    parser.add_argument('--output-dir', type=Path, default=ROOT/NAMESPACE/'run')
    parser.add_argument('--technical-gates', type=Path)
    parser.add_argument('--handoff', type=Path, default=ROOT/NAMESPACE/'release.json')
    parser.add_argument('--ledger', type=Path, default=ROOT/'outputs/oos_pilot/api_usage.json')
    parser.add_argument('--env-file', type=Path, default=ROOT/'.env')
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    if args.resume and not args.run:
        parser.error('Resume chỉ dùng cùng run')
    if args.prepare:
        dev, _, _ = verified_development(ROOT)
        adapter = build_adapter(dev['inputs'])
        prepare_plan(args.plan, adapter)
        print(f'Manifest holdout đã khóa offline: {args.plan}; chưa tạo run hoặc gọi API.')
        return
    plan = read_envelope(args.plan)
    adapter = build_adapter(plan['inputs'])
    validate_plan(plan, adapter)
    if args.dry_run or not any((args.release, args.preflight, args.run, args.verify_only, args.verify_report,
                               args.bootstrap, args.verify_bootstrap)):
        print(f"Holdout/source/PIT/scaler PASS: {len(plan['schedule'])} điểm, {len(plan['matrix'])} nhánh; chưa gọi API.")
        return
    if args.technical_gates is None:
        parser.error('Cần receipt bốn gate đúng code/runtime holdout')
    gates = read_technical_gates(args.technical_gates, plan)
    if gates['status'] != 'PASS':
        raise ValueError('Bốn gate holdout chưa PASS')
    if args.handoff.resolve() != ROOT/NAMESPACE/'release.json':
        raise ValueError('Receipt bàn giao cần namespace holdout riêng')
    if args.release:
        _write_once(args.handoff, release_artifact(plan, gates, args.plan))
        print(f'Bàn giao holdout đã khóa: {args.handoff}; chưa gọi API.')
        return
    if args.ledger.resolve() != ROOT/'outputs/oos_pilot/api_usage.json' or args.output_dir.resolve() != ROOT/NAMESPACE/'run':
        raise ValueError('Giữ đúng ledger chung và namespace run holdout')
    online = args.run or args.preflight
    if online:
        if plan['split'] != 'holdout_2024':
            raise ValueError('Fixture không được chạy API thật')
        if not args.handoff.exists() or read_envelope(args.handoff) != release_artifact(plan, gates, args.plan):
            raise ValueError('Chưa có bàn giao W8 hợp lệ; dừng trước đọc key/preflight/API')
        from core.groq_pacing import tokenizer_cached
        if not tokenizer_cached():
            raise ValueError('Thiếu tokenizer cache; chưa đọc key/gọi API')
        key = dotenv_values(args.env_file).get('GROQ_API_KEY') or os.environ.get('GROQ_API_KEY', '')
        if not key:
            raise ValueError('Thiếu GROQ_API_KEY')
    else:
        key = 'offline-verifier-no-network'
    def reject(request: httpx.Request) -> httpx.Response:
        raise AssertionError('Verifier holdout không được gọi mạng')
    ledger = args.ledger.resolve(); output = args.output_dir.resolve()
    with recovery_scope(online), PriorRunLock(ledger.parent/(ledger.name+'.lock'), 'shared-account-ledger-v2'):
        pacer = ResilientPacer(ledger, credential=key, amendment_sha256=plan['protocol_sha256'], policy='request_admission_v2') if online else None
        transport = ResilientTransport(pacer, output/'http_cache') if online else httpx.MockTransport(reject)
        with httpx.Client(transport=transport, timeout=90.) as client:
            builder = make_builder(plan['inputs'], key, client)
            for role, llm in (('agent', builder.agent_llm), ('graph', builder.graph_llm)):
                validate_client(llm, role, plan['inputs']['signal_config']['models'], online=online)
            if online:
                proof = pacer.state.get('preflight', {})
                valid = (proof.get('credential_scope') == pacer.credential_scope and proof.get('plan_sha256') == digest(plan)
                         and proof.get('status') == 'PASS')
                if args.preflight or not valid:
                    token = ENABLED.set(True)
                    try:
                        first = len(pacer.state['requests'])
                        with invocation_scope('preflight'):
                            preflight(builder)
                        pacer.state['preflight'] = {'status': 'PASS', 'plan_sha256': digest(plan),
                            'request_ids': [r['id'] for r in pacer.state['requests'][first:]]}
                        pacer.save()
                    finally:
                        ENABLED.reset(token)
                if args.preflight:
                    return
            config = plan['inputs']['signal_config']
            engine = BacktestEngine({**config['models'], 'language': config['language'],
                'alpha_norm_method': config['norm_method'], 'alpha_weights': config['alpha_weights']})
            runner = PriorBacktestRunner(engine, adapter, builder, durable_stages=True, quota_policy='request_admission_v2',
                before_point=pacer.before_point if pacer else None)
            result = run_holdout(runner, plan, output, verify_only=not args.run, ledger_path=ledger, gates=gates)
            if args.run:
                _write_once(output/'report.json', result)
            elif args.verify_report or args.bootstrap or args.verify_bootstrap:
                read_report(output/'report.json', result)
            if args.bootstrap or args.verify_bootstrap:
                if result['primary_status'] != 'COMPLETE':
                    raise ValueError('Chưa đủ 64 paired points; không khóa bootstrap từ dữ liệu thiếu')
                expected = bootstrap_report(plan, result, sha(output/'report.json'))
                if args.verify_bootstrap:
                    read_bootstrap(output/'bootstrap.json', expected)
                else:
                    _write_once(output/'bootstrap.json', expected)
                result = expected
            print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
