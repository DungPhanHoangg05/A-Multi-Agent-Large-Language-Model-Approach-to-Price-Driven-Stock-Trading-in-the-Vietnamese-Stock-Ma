"""Kiểm toán và bootstrap holdout offline, giữ nguyên runtime thực nghiệm đã khóa."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx

from core.backtest_engine import BacktestEngine
from core.candidate_selection import read_technical_gates
from core.historical_signals import digest
from core.improvement_bootstrap import bootstrap_report, read_bootstrap
from core.improvement_holdout import NAMESPACE, sha
from core.improvement_holdout_runtime import VERSION as REPORT_VERSION, run_holdout
from core.improvement_transport import validate_client
from core.pilot_readiness import build_adapter
from core.prior_backtest import PriorBacktestRunner
from core.prior_run_lock import PriorRunLock
from core.research_cohort import read_envelope
from core.research_input_lock import _write_once
from scripts.run_bayesian_ablation import make_builder
from scripts.run_improvement_holdout import release_artifact

VERSION = 'improvement_holdout_verification_v1'
SOURCE = 'scripts/verify_improvement_holdout.py'
GATES = 'docs/plan/week8/validation_gates/bound_holdout_v1/technical_gates.json'


def read_holdout_report(path: Path, expected: dict[str, Any]) -> dict[str, Any]:
    """Nhận đúng version holdout và so toàn payload với snapshot vừa kiểm, kể cả kiểu số."""
    saved = read_envelope(path)
    if (saved.get('report_version') != REPORT_VERSION or expected.get('report_version') != REPORT_VERSION
            or digest(saved) != digest(expected)):
        raise ValueError('Report holdout khác version hoặc checkpoint/metric/support đã tái dựng')
    return saved


def verification_artifact(plan: dict[str, Any], report: dict[str, Any], gates: dict[str, Any],
                          *, root: Path = ROOT) -> dict[str, Any]:
    """Khóa consumer riêng cùng report/binding gốc, không thay code hash hoặc identity của run."""
    if (plan['split'] != 'holdout_2024' or report['primary_status'] != 'COMPLETE'
            or report['report_version'] != REPORT_VERSION or gates['status'] != 'PASS'
            or len(plan['schedule']) != 64 or len(plan['matrix']) != 6
            or report['matrix'] != plan['matrix'] or report['binding']['plan_sha256'] != digest(plan)):
        raise ValueError('Nghiệm thu cần đúng plan holdout và đủ 64 điểm/sáu nhánh')
    for symbol, cutoffs in plan['symbol_cutoffs'].items():
        stock = report['stocks'][symbol]
        expected_ids = [symbol+'-'+day for day in cutoffs]
        if (len(cutoffs) != 16 or stock['global_common_support'] !=
                {'point_ids': expected_ids, 'count': 16, 'excluded': []}
                or [p['point_id'] for p in stock['points']] != expected_ids
                or any(set(p['branch_status']) != set(plan['matrix']) or
                       any(v != 'complete' for v in p['branch_status'].values()) for p in stock['points'])):
            raise ValueError('Common support thiếu điểm/nhánh hoặc còn planned/unknown')
    return {'verification_version': VERSION, 'status': 'PASS',
        'verifier_code_sha256': {SOURCE: hashlib.sha256((root/SOURCE).read_text(encoding='utf-8').encode()).hexdigest()},
        'plan_file_sha256': sha(root/NAMESPACE/'plan.json'),
        'release_file_sha256': sha(root/NAMESPACE/'release.json'),
        'technical_gates_sha256': gates['sha256'], 'frozen_code_sha256': digest(plan['code_sha256']),
        'runtime': plan['runtime'], 'run_signature': report['binding']['run_signature'],
        'report_file_sha256': sha(root/NAMESPACE/'run/report.json'), 'report_payload_sha256': digest(report),
        'report_binding_sha256': digest(report['binding']), 'points': 64, 'decisions': 384}


def read_verification(path: Path, expected: dict[str, Any]) -> dict[str, Any]:
    """Bootstrap chỉ dùng nghiệm thu đúng consumer, report và nguồn đã tái kiểm."""
    saved = read_envelope(path)
    if saved.get('verification_version') != VERSION or digest(saved) != digest(expected):
        raise ValueError('Receipt kiểm toán khác consumer/report/nguồn hiện hành')
    return saved


def rebuild(plan: dict[str, Any], gates: dict[str, Any], root: Path) -> dict[str, Any]:
    """Dùng nguyên runner đã khóa; không đọc key, tạo slot hoặc cho phép request mạng."""
    def reject(request: httpx.Request) -> httpx.Response:
        raise AssertionError('Kiểm toán holdout offline không được gọi mạng')
    ledger = root/'outputs/oos_pilot/api_usage.json'
    with PriorRunLock(ledger.parent/(ledger.name+'.lock'), 'shared-account-ledger-v2'):
        with httpx.Client(transport=httpx.MockTransport(reject)) as client:
            builder = make_builder(plan['inputs'], 'offline-verifier-no-network', client)
            config = plan['inputs']['signal_config']
            for role, llm in (('agent', builder.agent_llm), ('graph', builder.graph_llm)):
                validate_client(llm, role, config['models'], online=False)
            engine = BacktestEngine({**config['models'], 'language': config['language'],
                'alpha_norm_method': config['norm_method'], 'alpha_weights': config['alpha_weights']})
            runner = PriorBacktestRunner(engine, build_adapter(plan['inputs']), builder,
                durable_stages=True, quota_policy='request_admission_v2')
            return run_holdout(runner, plan, root/NAMESPACE/'run', verify_only=True,
                ledger_path=ledger, gates=gates)


def main() -> None:
    """Lệnh offline riêng sửa tương thích consumer; không nhận chế độ run/preflight hoặc key."""
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    for name in ('verify-report', 'verify-only', 'bootstrap', 'verify-bootstrap'):
        modes.add_argument('--'+name, action='store_true')
    args = parser.parse_args()
    plan_file = ROOT/NAMESPACE/'plan.json'; output = ROOT/NAMESPACE/'run'
    plan = read_envelope(plan_file)
    gates = read_technical_gates(ROOT/GATES, plan)
    if (gates['status'] != 'PASS' or plan['split'] != 'holdout_2024'
            or read_envelope(ROOT/NAMESPACE/'release.json') != release_artifact(plan, gates, plan_file)):
        raise ValueError('Cần đúng release holdout và bốn gate đã khóa')
    result = rebuild(plan, gates, ROOT)
    if args.verify_only:
        print(json.dumps({'primary_status': result['primary_status'], 'binding': result['binding']}, ensure_ascii=False))
        return
    report = read_holdout_report(output/'report.json', result)
    receipt = verification_artifact(plan, report, gates, root=ROOT)
    if args.bootstrap or args.verify_bootstrap:
        read_verification(output/'verification.json', receipt)
        expected = bootstrap_report(plan, report, sha(output/'report.json'))
        if args.verify_bootstrap:
            read_bootstrap(output/'bootstrap.json', expected)
        else:
            _write_once(output/'bootstrap.json', expected)
        print(json.dumps(expected, ensure_ascii=False, indent=2))
    else:
        _write_once(output/'verification.json', receipt)
        read_verification(output/'verification.json', receipt)
        print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
