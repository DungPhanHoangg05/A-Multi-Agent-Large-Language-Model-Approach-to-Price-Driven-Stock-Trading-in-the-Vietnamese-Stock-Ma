"""Runtime holdout sáu nhánh dùng journal/request/transport đã kiểm của development."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from core.historical_signals import digest
from core.improvement_holdout import NAMESPACE, sha, validate_plan
from core.improvement_protocol import SYMBOL_ORDER
from core.improvement_reports import _complete, _delta, _metric, _support
from core.improvement_runtime import _empty, _journal, _snapshot, decision, decision_path, shared_point
from core.paired_candidate_report import _coverage
from core.prior_config import copy_prior_json
from core.prior_disagreement_analysis import _case
from core.prior_run_lock import PriorRunLock
from core.research_cohort import read_envelope
from core.research_input_lock import _write_once
from core.research_invocation import ENABLED

VERSION = 'improvement_holdout_report_v1'


def build_report(plan: dict[str, Any], rows: list[dict[str, Any]], binding: dict[str, Any]) -> dict[str, Any]:
    """G phải đủ mọi nhánh; subgroup chỉ mô tả, không đổi primary hoặc chọn lại."""
    names = plan['matrix']; primary = plan['selection_decision']['primary_branch']
    pairs = [plan['statistics']['primary'], *plan['statistics']['secondary_contrasts']]
    if (binding['plan_sha256'] != digest(plan) or [p['point_id'] for p in rows] != [r['point_id'] for r in plan['schedule']]
            or any(p['repeat_id'] != 0 or set(p['branches']) != set(names) for p in rows)):
        raise ValueError('Report holdout khác lịch, ma trận hoặc repeat ID')
    def group(subset: list[dict[str, Any]]) -> dict[str, Any]:
        """Dựng tài khoản mới trên từng support, giữ null cho nhóm rỗng."""
        common = [p for p in subset if _complete(p, names)]
        cash = deepcopy(common)
        for p in cash:
            p['branches']['original']['decision']['action'] = 'SHORT'
            p['evaluation']['branches']['original'] = {'correct': p['evaluation']['actual_direction'] == 'DOWN',
                'executed_action': 'CASH', 'cycle_net_return': 0.}
        return {'global_common_support': _support(subset, names),
            'metrics': {n: _metric(common, n) for n in names},
            'cash_reference': _metric(cash, 'original'),
            'coverage': {n: _coverage(subset, n) for n in names},
            'contrasts': {f'{a}__{b}': _delta(subset, a, b) for a, b in pairs}}
    stocks = {}
    for s in SYMBOL_ORDER:
        subset = [p for p in rows if p['context']['symbol'] == s]
        stock = group(subset)
        stock['points'] = [{'point_id': p['point_id'], 'as_of_date': p['context']['as_of_date'], **p['report_context'],
            'branch_status': {n: p['branches'][n]['status'] for n in names}} for p in subset]
        stock['time_groups'] = {label: group([p for p in subset if int(p['context']['as_of_date'][5:7]) in months])
            for label, months in [('Q1', range(1, 4)), ('Q2', range(4, 7)), ('Q3', range(7, 10)),
                ('Q4', range(10, 13)), ('H1', range(1, 7)), ('H2', range(7, 13))]}
        stock['regimes'] = {r: group([p for p in subset if p['report_context']['regime'] == r])
                           for r in ('BULL', 'BEAR', 'CHOPPY', 'CONSOLIDATION')}
        stock['prior_off'] = {f'{a}__{b}': _delta([p for p in subset if all(not
            (p['report_context']['prior'][n]['visible_metric_ids'] or p['report_context']['prior'][n]['visible_example_ids'])
            for n in (a, b))], a, b) for a, b in pairs}
        ready = [p for p in subset if p['report_context']['prior'][primary]['stats_ready'] is True
                 and p['report_context']['prior'][primary]['examples_ready'] is True]
        stock['ablation_both_ready'] = {suffix: _delta(ready, primary, primary+suffix)
                                       for suffix in ('_stats_only', '_examples_only')}
        stocks[s] = stock
    complete = bool(rows) and all(_complete(p, names) for p in rows)
    key = primary+'__original'
    deltas = {s: stocks[s]['contrasts'][key]['delta_return_pp'] for s in SYMBOL_ORDER}
    cases = []
    for p in rows:
        if _complete(p, names):
            e = p['evaluation']
            cases.append({'point_id': p['point_id'], 'symbol': p['context']['symbol'],
                'as_of_date': p['context']['as_of_date'], **{k: e[k] for k in
                ('entry_date', 'exit_date', 'entry_open', 'exit_close', 'net_return_long')},
                'actions': {n: p['branches'][n]['decision']['action'] for n in names}})
    return copy_prior_json({'report_version': VERSION, 'metric_version': 'cycle_risk_metrics_v2',
        'cohort_id': plan['cohort_id'], 'split': plan['split'], 'matrix': names, 'repeat_id': 0,
        'research_primary': primary, 'binding': binding,
        'selection_evidence_status': 'HOLDOUT_NOT_FOR_SELECTION' if plan['split'] == 'holdout_2024' else 'NOT_APPLICABLE',
        'primary_status': 'COMPLETE' if complete else 'INCOMPLETE', 'stocks': stocks,
        'primary_delta_return_pp': float(sum(deltas.values())/4) if complete else None,
        'leave_one_symbol_out': {s: float(sum(v for k, v in deltas.items() if k != s)/3) if complete else None for s in SYMBOL_ORDER},
        'cases': {n: [_case(p, n) for p in rows if p['branches'][n]['status'] == 'complete'] for n in names},
        'bootstrap_cases': cases, 'selection_decision': plan['selection_decision'],
        'limitations': ['Primary kế thừa development; không đề cử lại theo holdout.',
            'Bốn tài khoản độc lập; prior-use và subgroup không chứng minh nhân quả.']})


def run_holdout(runner: Any, plan: dict[str, Any], root: Path, *, verify_only: bool = False,
                ledger_path: Path | None = None, gates: dict[str, Any] | None = None,
                fixture_plan: Path | None = None, fixture_runner: Any = None) -> dict[str, Any]:
    """Một upstream/point; resume giữ slot/UUID qua cơ chế phục hồi hiện hành."""
    index = validate_plan(plan, runner.adapter, fixture_plan=fixture_plan, fixture_runner=fixture_runner)
    root = root.resolve(); workspace = runner.adapter._files.root.resolve()
    if not runner.durable_stages or plan['split'] == 'fixture' and runner.mode != 'offline_fixture':
        raise ValueError('Holdout cần journal durable và fixture offline')
    if plan['split'] == 'holdout_2024' and (runner.mode != 'research' or root != workspace/NAMESPACE/'run'
            or ledger_path != workspace/'outputs/oos_pilot/api_usage.json' or gates is None or gates['status'] != 'PASS'
            or runner.quota_policy != 'request_admission_v2'):
        raise ValueError('Holdout thật cần đúng run/ledger chung và bốn gate PASS')
    if runner.mode == 'research':
        from core.improvement_transport import validate_client
        for role, llm in (('agent', runner.builder.agent_llm), ('graph', runner.builder.graph_llm)):
            validate_client(llm, role, plan['inputs']['signal_config']['models'], online=not verify_only)
    if (root == workspace or not root.is_relative_to(workspace) or any(
            (workspace/p).resolve().is_relative_to(root) for p in runner.adapter.source_hashes)):
        raise ValueError('Run holdout chồng lên nguồn hoặc vượt workspace')
    identity = {'identity_version': 'improvement_holdout_run_identity_v1', 'plan': plan,
        'execution_mode': runner.mode, 'ledger_path': str(ledger_path) if ledger_path else None,
        'gates': gates, 'sources': runner.adapter.source_hashes, 'upstream_reuse': False}
    signature = digest(identity); manifest = root/'cohort.json'; ready = root/'ready.json'
    orders = [({k: r[k] for k in ('point_id', 'symbol', 'as_of_date')}, 0, r['branches']) for r in plan['schedule']]
    count = len(orders)*len(plan['matrix'])
    if verify_only and not ready.exists():
        raise ValueError('Holdout chưa khởi tạo đủ slot; verifier không tự tạo run')
    token = ENABLED.set(True)
    try:
        with PriorRunLock(root, signature):
            if manifest.exists():
                if read_envelope(manifest) != identity:
                    raise ValueError('Run holdout khác identity đã khóa')
            else:
                if any(p.name not in ('run.lock', 'run.owner.json') for p in root.iterdir()):
                    raise ValueError('Holdout mới cần output trống')
                _write_once(manifest, identity)
            if not ready.exists():
                for row, _, names in orders:
                    point = runner.adapter.prepare(row['symbol'], row['as_of_date'])
                    _journal(runner, point, root, signature, row['point_id'], create=True)
                    _write_once(root/'points'/f"{row['point_id']}.json", {'point_version': 'improvement_shared_point_v1',
                        'run_signature': signature, 'point_id': row['point_id'],
                        'context': {'symbol': row['symbol'], 'as_of_date': row['as_of_date']},
                        'source_proof': point.source_provenance, 'full_bundle': None, 'shared_sha256': None, 'journal_sha256': None})
                    for name in names:
                        _write_once(decision_path(root, row['point_id'], name), _empty(signature, row['point_id'], name, 0))
                _write_once(ready, {'run_signature': signature, 'slot_count': count})
            if read_envelope(ready) != {'run_signature': signature, 'slot_count': count}:
                raise ValueError('Ready marker holdout khác lịch/ma trận')
            rows, hashes = _snapshot(runner, plan, root, index, signature, orders=orders)
            pending = {p['point_id']: [n for n in p['branches'] if p['branches'][n]['status'] != 'complete'] for p in rows}
            if not verify_only and any(pending.values()):
                for row, _, names in orders:
                    if not pending[row['point_id']]:
                        continue
                    if runner.engine._stop_event.is_set():
                        raise InterruptedError('Dừng trước point holdout, giữ checkpoint')
                    if runner.before_point:
                        runner.before_point()
                    point, shared, _ = shared_point(runner, row, root, signature, verify_only=False)
                    for name in names:
                        if name in pending[row['point_id']]:
                            if runner.engine._stop_event.is_set():
                                raise InterruptedError('Dừng trước Decision holdout, giữ checkpoint')
                            decision(runner, point, shared, index, decision_path(root, row['point_id'], name),
                                     signature, row['point_id'], name, 0, verify_only=False)
                rows, hashes = _snapshot(runner, plan, root, index, signature, orders=orders)
            hashes.update({'cohort.json': sha(manifest), 'ready.json': sha(ready)})
            binding = {'run_signature': signature, 'execution_mode': runner.mode, 'plan_sha256': digest(plan),
                'checkpoint_sha256': hashes, 'code_sha256': plan['code_sha256'], 'runtime': plan['runtime'],
                'sources': runner.adapter.source_hashes, 'selection_proof': plan['development_proof']}
            return build_report(plan, rows, binding)
    finally:
        ENABLED.reset(token)
