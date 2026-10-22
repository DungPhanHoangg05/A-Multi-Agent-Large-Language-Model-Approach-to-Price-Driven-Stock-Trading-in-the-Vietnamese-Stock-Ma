"""CLI cohort Bayesian ICL riêng, offline mặc định; chỉ development có release mới gọi API."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.bic_icl_protocol import (CohortSources, NAMESPACE, POLICIES, dry_run,
    namespace_path, prepare_plan, read_authorization)
from core.bic_icl_reports import check_economic_fixture, verify_report
from core.bic_icl_runtime import run_cohort
from core.historical_signals import digest
from core.research_cohort import read_envelope
from core.research_input_lock import _write_once


def main(argv: list[str] | None = None) -> None:
    """Offline không đọc env/key; online kiểm release trước khởi tạo client thật."""
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    for name in ('prepare', 'dry-run', 'economic-fixture', 'preflight', 'lock-upstream', 'run', 'verify-only', 'verify-report'):
        modes.add_argument('--'+name, action='store_true')
    parser.add_argument('--plan', type=Path, default=NAMESPACE/'development_plan_v1.json')
    parser.add_argument('--output-dir', type=Path, default=NAMESPACE/'development_run_v1')
    parser.add_argument('--upstream', choices=POLICIES, default='VERIFIED_CACHE')
    parser.add_argument('--repeat-id', type=int, choices=(0, 1, 2, 3), default=0)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--handoff', type=Path)
    parser.add_argument('--technical-gates', type=Path)
    parser.add_argument('--ledger', type=Path, default=ROOT/'outputs/oos_pilot/api_usage.json')
    parser.add_argument('--env-file', type=Path, default=ROOT/'.env')
    args = parser.parse_args(argv)
    if args.resume and not (args.run or args.lock_upstream):
        parser.error('Resume chỉ dùng run/lock-upstream')
    if args.repeat_id and not (args.run or args.verify_only or args.verify_report):
        parser.error('Repeat chỉ dùng run/verify')
    if args.economic_fixture:
        print(json.dumps(check_economic_fixture(), ensure_ascii=False))
        return
    sources = CohortSources()
    if args.prepare:
        plan = prepare_plan(args.plan, sources, upstream_policy=args.upstream)
        print(json.dumps({'status': 'PREPARED', 'plan_sha256': digest(plan), 'decision_calls': 0}))
        return
    plan = read_envelope(namespace_path(args.plan, 'plan'))
    sources.validate(plan)
    online = args.run or args.preflight or args.lock_upstream
    if args.dry_run or not (online or args.verify_only or args.verify_report):
        result = dry_run(plan, sources)
        print(json.dumps({'status': result['status'], 'decision_calls': 0,
            'context_lock': result['lock'], 'fresh_requests_pending': result['fresh_requests_pending']}, ensure_ascii=False))
        return
    output = namespace_path(args.output_dir, 'run')
    if args.ledger.resolve() != ROOT/'outputs/oos_pilot/api_usage.json':
        raise ValueError('CLI cohort phải giữ ledger provider chung')
    authorization = read_authorization(args.handoff, args.technical_gates, plan,
        run_root=output, ledger_path=args.ledger) if online else None
    # Tất cả đường từ chối release ở trên chạy trước import/đọc credential.
    import httpx
    from core.improvement_recovery import ResilientPacer, ResilientTransport, recovery_scope
    from core.improvement_transport import validate_client
    from core.prior_run_lock import PriorRunLock
    from core.research_invocation import ENABLED, invocation_scope
    from scripts.run_bayesian_ablation import make_builder, preflight
    if online:
        from core.groq_pacing import tokenizer_cached
        if not tokenizer_cached():
            raise ValueError('Thiếu tokenizer cache; chưa đọc key hoặc gọi API')
        from dotenv import dotenv_values
        import os
        key = dotenv_values(args.env_file).get('GROQ_API_KEY') or os.environ.get('GROQ_API_KEY', '')
        if not key:
            raise ValueError('Thiếu GROQ_API_KEY')
    else:
        key = 'offline-verifier-no-network'
    def reject(request: httpx.Request) -> Any:
        raise AssertionError('Verifier cohort không được gọi mạng')
    with PriorRunLock(args.ledger.parent/(args.ledger.name+'.lock'), 'shared-account-ledger-v2'):
        pacer = ResilientPacer(args.ledger, credential=key, amendment_sha256=plan['method_sha256'], policy='request_admission_v2')
        transport = ResilientTransport(pacer, output/'http_cache', None if online else httpx.MockTransport(reject))
        with httpx.Client(transport=transport, timeout=90.) as client:
            builder = make_builder(plan['inputs'], key, client)
            for role, llm in (('agent', builder.agent_llm), ('graph', builder.graph_llm)):
                validate_client(llm, role, plan['inputs']['signal_config']['models'], online=True)
            if online:
                if args.preflight:
                    token = ENABLED.set(True)
                    try:
                        first = len(pacer.state['requests'])
                        with recovery_scope(), invocation_scope('preflight'):
                            preflight(builder)
                        pacer.state['preflight'] = {'status': 'PASS', 'plan_sha256': digest(plan),
                            'request_ids': [r['id'] for r in pacer.state['requests'][first:]]}
                        pacer.save()
                    finally:
                        ENABLED.reset(token)
                    return
                proof = pacer.state.get('preflight', {})
                if (proof.get('status') != 'PASS' or proof.get('credential_scope') != pacer.credential_scope
                        or proof.get('plan_sha256') != digest(plan)):
                    raise ValueError('Cần preflight text/vision PASS cùng credential và plan')
            result = run_cohort(plan, sources, output, builder.agent_llm, builder=builder,
                resume=args.resume, verify_only=not online, repeat_id=args.repeat_id,
                authorization=authorization, upstream_only=args.lock_upstream)
            report_path = output/f'report_{args.repeat_id}.json'
            if args.verify_report:
                verify_report(report_path, result)
            elif args.run:
                _write_once(report_path, result)
            print(json.dumps({'status': result['status'], 'repeat_id': args.repeat_id,
                              'confirmation_allowed': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
