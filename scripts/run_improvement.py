"""CLI revision cải tiến: offline mặc định, chỉ người dùng chạy preflight/API sau gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx
from dotenv import dotenv_values

from core.backtest_engine import BacktestEngine
from core.candidate_selection import read_technical_gates
from core.historical_signals import digest
from core.improvement_protocol import prepare_plan, validate_plan
from core.improvement_runtime import run_primary, run_repeats, prepare_repeat_plan, reconcile
from core.improvement_reports import read_report, read_selection, selection_artifact
from core.improvement_transport import ImprovementTransport, validate_client
from core.pilot_readiness import build_adapter
from core.prior_backtest import PriorBacktestRunner
from core.prior_run_lock import PriorRunLock
from core.provider_quota import ProviderQuotaPacer
from core.research_cohort import read_envelope
from core.research_input_lock import _write_once
from core.research_invocation import ENABLED, invocation_scope
from scripts.run_bayesian_ablation import make_builder, preflight


def main() -> None:
    """Tách source/gate trước đọc key; không dispatch revision mới vào CLI W7."""
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    for flag in ('prepare', 'dry-run', 'preflight', 'run', 'verify-only', 'verify-report', 'prepare-repeat',
                 'select', 'verify-selection', 'reconcile', 'train', 'verify-train'):
        modes.add_argument('--'+flag, action='store_true')
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--parent', type=Path)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--technical-gates', type=Path)
    parser.add_argument('--ledger', type=Path, default=ROOT/'outputs/oos_pilot/api_usage.json')
    parser.add_argument('--env-file', type=Path, default=ROOT/'.env')
    parser.add_argument('--repeat-plan', type=Path)
    parser.add_argument('--repeat-dir', type=Path)
    parser.add_argument('--authorize-replay')
    parser.add_argument('--replay-reason')
    parser.add_argument('--train-report', type=Path)
    parser.add_argument('--train-index', default='outputs/bayesian_benchmark/price_features/train_validation_index_v1.json')
    args = parser.parse_args()
    if args.train or args.verify_train:
        from core.prior_context import PriorContextAdapter
        from core.improvement_diagnostics import run_diagnostics
        if args.train_report is None or any((args.plan, args.parent, args.output_dir, args.resume, args.authorize_replay)):
            parser.error('Train chỉ dùng train-report/train-index, không chạy cohort/API')
        adapter = PriorContextAdapter({'enable_bayesian_prior': True})
        destination = args.train_report.resolve()
        if not destination.is_relative_to((ROOT/'outputs/bayesian_benchmark/improvement_v1/train').resolve()):
            raise ValueError('Diagnostics cần namespace train cải tiến riêng')
        index = adapter.load_price_feature_index(args.train_index)
        report = run_diagnostics(adapter, index, destination, verify_only=args.verify_train)
        print(f"Diagnostics cải tiến PASS: {report['query_count']} query, Decision=0; {destination}")
        return
    if args.plan is None:
        parser.error('Cần --plan revision cải tiến')
    if args.resume and not args.run:
        parser.error('Resume chỉ dùng với run')
    if args.authorize_replay or args.replay_reason:
        if not args.reconcile or not args.authorize_replay or not args.replay_reason:
            parser.error('Xác nhận UUID chỉ dùng reconcile cùng lý do')
    if args.prepare:
        if args.parent is None or args.output_dir or args.resume:
            parser.error('Prepare cần parent và plan mới, không tạo run')
        parent = read_envelope(args.parent)
        adapter = build_adapter(parent['inputs'])
        prepare_plan(args.parent, args.plan, adapter)
        print(f'Plan cải tiến đã khóa offline: {args.plan}; chưa gọi API')
        return
    if args.parent is not None:
        parser.error('Parent chỉ dùng prepare')
    supplied = read_envelope(args.plan)
    repeat = supplied.get('plan_version') == 'improvement_repeat_plan_v1'
    plan = supplied['primary_plan'] if repeat else supplied
    adapter = build_adapter(plan['inputs'])
    validate_plan(plan, adapter)
    if args.dry_run or not any((args.preflight, args.run, args.verify_only, args.verify_report,
                               args.prepare_repeat, args.select, args.verify_selection, args.reconcile)):
        if repeat:
            raise ValueError('Dry-run repeat cần verifier nối primary bằng verify-only sau chuẩn bị run')
        print(f"Plan cải tiến/source/PIT PASS: {plan['split']}; 11 nhánh, risk OFF; chưa gọi API")
        return
    if args.output_dir is None:
        parser.error('Chế độ run/verify cần output-dir riêng')
    if repeat and args.prepare_repeat:
        parser.error('Prepare-repeat nhận plan primary')
    online = args.run or args.preflight
    if online and plan['split'] == 'fixture':
        raise ValueError('Fixture không được chạy API thật')
    if not args.output_dir.resolve().is_relative_to((ROOT/'outputs/bayesian_benchmark/improvement_v1').resolve()):
        raise ValueError('CLI cải tiến cần output namespace riêng khỏi W7')
    gates = read_technical_gates(args.technical_gates, plan)
    if gates['status'] != 'PASS':
        raise ValueError('Cần receipt bốn gate PASS đúng code/runtime cải tiến')
    ledger = args.ledger.resolve()
    if ledger != (ROOT/'outputs/oos_pilot/api_usage.json').resolve():
        raise ValueError('Giữ ledger tài khoản chung đã khóa, không reset usage')
    if online:
        from core.groq_pacing import tokenizer_cached
        if not tokenizer_cached():
            raise ValueError('Thiếu tokenizer cache; chưa đọc key/gọi API')
        key = dotenv_values(args.env_file).get('GROQ_API_KEY') or os.environ.get('GROQ_API_KEY', '')
        if not key:
            raise ValueError('Thiếu GROQ_API_KEY')
    else:
        key = 'offline-verifier-no-network'
    def reject(request: httpx.Request) -> httpx.Response:
        raise AssertionError('Verifier cải tiến không được gọi mạng')
    with PriorRunLock(ledger.parent/(ledger.name+'.lock'), 'shared-account-ledger-v2'):
        pacer = ProviderQuotaPacer(ledger, credential=key, amendment_sha256=plan['protocol_sha256'], policy='request_admission_v2') if online else None
        transport = ImprovementTransport(pacer) if online else httpx.MockTransport(reject)
        with httpx.Client(transport=transport, timeout=90.) as client:
            builder = make_builder(plan['inputs'], key, client)
            for role, llm in (('agent', builder.agent_llm), ('graph', builder.graph_llm)):
                validate_client(llm, role, plan['inputs']['signal_config']['models'], online=online)
            if online:
                proof = pacer.state.get('preflight', {})
                wanted = digest(supplied)
                valid = (proof.get('credential_scope') == pacer.credential_scope and proof.get('plan_sha256') == wanted
                         and proof.get('status') == 'PASS')
                if args.preflight or not valid:
                    token = ENABLED.set(True)
                    try:
                        first = len(pacer.state['requests'])
                        with invocation_scope('preflight'):
                            preflight(builder)
                        pacer.state['preflight'] = {'status': 'PASS', 'plan_sha256': wanted,
                            'request_ids': [r['id'] for r in pacer.state['requests'][first:]]}
                        pacer.save()
                    finally:
                        ENABLED.reset(token)
                if args.preflight:
                    return
            config = plan['inputs']['signal_config']
            engine = BacktestEngine({**config['models'], 'language': config['language'],
                'alpha_norm_method': config['norm_method'], 'alpha_weights': config['alpha_weights']})
            runner = PriorBacktestRunner(engine, adapter, builder, durable_stages=True,
                quota_policy='request_admission_v2', before_point=pacer.before_point if pacer else None)
            options = {'ledger_path': ledger, 'gates': gates}
            if args.prepare_repeat:
                if args.repeat_plan is None:
                    parser.error('Prepare-repeat cần repeat-plan đích mới')
                prepare_repeat_plan(runner, plan, args.output_dir, args.repeat_plan, **options)
                print(f'Plan repeat đã verify primary và khóa offline: {args.repeat_plan}')
                return
            if args.reconcile:
                result = reconcile(runner, supplied, args.output_dir, attempt_id=args.authorize_replay,
                                   reason=args.replay_reason, **options)
            else:
                execute = run_repeats if repeat else run_primary
                result = execute(runner, supplied, args.output_dir, resume=args.resume, verify_only=not args.run, **options)
                if args.verify_report or args.select or args.verify_selection:
                    read_report(args.output_dir/'report.json', result)
                if args.select or args.verify_selection:
                    if repeat:
                        raise ValueError('Repeat không được dùng nomination')
                    if args.repeat_plan is None or args.repeat_dir is None:
                        raise ValueError('Selection cần đủ repeat đã verify theo checklist W8')
                    repeat_plan = read_envelope(args.repeat_plan)
                    if (repeat_plan['primary_plan'] != plan or repeat_plan['primary_run'] !=
                            args.output_dir.resolve().relative_to(ROOT).as_posix()):
                        raise ValueError('Selection không nhận repeat của primary khác')
                    repeated = run_repeats(runner, repeat_plan, args.repeat_dir, verify_only=True, **options)
                    read_report(args.repeat_dir/'report.json', repeated)
                    if repeated['status'] != 'COMPLETE':
                        raise ValueError('Repeat INCOMPLETE chặn nghiệm thu trước selection')
                    expected = selection_artifact(result, gates, hashlib.sha256((args.output_dir/'report.json').read_bytes()).hexdigest())
                    target = args.output_dir/'selection.json'
                    if args.verify_selection:
                        read_selection(target, expected)
                    else:
                        _write_once(target, expected)
                    result = expected
                elif args.run:
                    _write_once(args.output_dir/'report.json', result)
            print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
