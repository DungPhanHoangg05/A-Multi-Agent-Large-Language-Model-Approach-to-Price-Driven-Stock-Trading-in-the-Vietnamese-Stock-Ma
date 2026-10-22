"""Chấm sau Decision và báo tài khoản cùng support, không đề cử hoặc mở xác nhận."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from core.backtest_engine import PRIOR_BRANCH_MODES
from core.candidate_cohort import _checked_response
from core.improvement_reports import _metric
from core.prior_backtest import evaluate_point
from core.prior_config import copy_prior_json
from core.research_cohort import read_envelope


def numeric_action(evidence: dict[str, Any]) -> dict[str, Any]:
    """Heuristic riêng dùng posterior chung; p=0,5 hoặc gate off giữ CASH hợp lệ."""
    stats = evidence['pool']['statistics']
    ready = evidence['gate']['R_pool']['stats_ready']
    import math
    probability = stats['posterior_mean']
    if (type(ready) is not bool or type(probability) not in (int, float)
            or not math.isfinite(probability) or not 0 <= probability <= 1):
        raise ValueError('Numeric cần posterior/gate hữu hạn; missing không được chuyển CASH')
    action = 'LONG' if ready and stats['posterior_mean'] > .5 else 'SHORT'
    return {'action': action, 'reason': 'POSTERIOR_GT_HALF' if action == 'LONG' else
        'STATS_OFF' if not ready else 'POSTERIOR_NOT_GT_HALF', 'posterior_mean': stats['posterior_mean'],
        'stats_ready': ready, 'base_evidence_sha256': evidence['base_evidence_sha256']}


def project(packet: dict[str, Any], block: dict[str, Any], adapter: Any, *, repeat_id: int,
            language: str) -> dict[str, Any]:
    """Không chấm nhánh lỗi/missing thành CASH; Numeric chỉ xuất hiện ở primary."""
    branches = {}
    for name, branch in block['branches'].items():
        decision = None
        if branch['status'] == 'complete':
            normalized = _checked_response(branch['output'], None, language)
            decision = {'action': normalized['decision'], 'confidence': normalized['confidence'],
                'risk_reward_ratio': normalized['risk_reward_ratio'], 'latency_seconds':
                branch['attempts'][0]['latency_seconds'] if branch['attempts'] else 0.,
                'normalized_response': deepcopy(branch['output']['final_trade_decision'])}
        branches[name] = {'status': branch['status'], 'decision': decision,
            'decision_origin': branch['decision_origin'], 'source': branch['source'],
            'scientific_attempt_count': len(branch['attempts'])}
    numeric = numeric_action(packet['evidence'])
    if repeat_id == 0:
        branches['Numeric_only'] = {'status': 'complete', 'decision': {**numeric, 'confidence': 'Numeric',
            'risk_reward_ratio': 0., 'latency_seconds': 0.}, 'decision_origin': 'numeric',
            'source': None, 'scientific_attempt_count': 0}
    context = packet['source_proof']['context']
    evaluation = None
    # Không tính payoff query trong preflight hoặc khi block còn dở.
    if all(b['status'] == 'complete' for b in branches.values()):
        frame, events = adapter.execution_data(context['symbol'])
        result = evaluate_point(frame, events, context['as_of_date'],
            {name: branches['original'] for name in PRIOR_BRANCH_MODES})
        evaluations = {}
        for name, branch in branches.items():
            action = branch['decision']['action']
            evaluations[name] = {'correct': bool((action == 'LONG') == (result['actual_direction'] == 'UP')),
                'executed_action': 'BUY_SELL' if action == 'LONG' else 'CASH',
                'cycle_net_return': result['net_return_long'] if action == 'LONG' else 0.}
        evaluation = {**result, 'branches': evaluations}
    return copy_prior_json({'point_id': packet['point_id'], 'context': context, 'repeat_id': repeat_id,
        'source_proof': packet['source_proof'], 'branches': branches, 'evaluation': evaluation,
        'prior': {'gate': packet['evidence']['gate'], 'content_views': packet['evidence']['content_views'],
            'k_tasks': packet['evidence']['task_selection']['metadata']['k_tasks']}})


def build_report(plan: dict[str, Any], lock: dict[str, Any], rows: list[dict[str, Any]],
                 binding: dict[str, Any], *, repeat_id: int) -> dict[str, Any]:
    """Chỉ tài khoản common support đầy đủ, repeat riêng, không mean cycle thay D."""
    from core.bic_icl_protocol import SYMBOLS, validate_schema
    names = [*lock['matrix'], *(['original_duplicate'] if repeat_id else ['Numeric_only'])]
    expected = [r['point_id'] for r in (lock['repeat_sample'] if repeat_id else plan['schedule'])]
    if [r['point_id'] for r in rows] != expected or any(r['repeat_id'] != repeat_id or set(r['branches']) != set(names) for r in rows):
        raise ValueError('Report thiếu/thừa point/branch/repeat so với cohort đã khóa')
    complete = bool(rows) and all(r['evaluation'] is not None for r in rows)
    stocks = {}
    for symbol in SYMBOLS:
        selected = [r for r in rows if r['context']['symbol'] == symbol]
        common = [r for r in selected if r['evaluation'] is not None]
        stocks[symbol] = {'planned_count': len(selected), 'common_count': len(common),
            'excluded_point_ids': [r['point_id'] for r in selected if r['evaluation'] is None],
            'metrics': {name: _metric(common, name) for name in names}}
    deltas = {}
    for name in names:
        per_symbol = {symbol: (stock['metrics'][name]['account_metrics']['total_return_pct']-
            stock['metrics']['original']['account_metrics']['total_return_pct']) if complete else None
            for symbol, stock in stocks.items()}
        deltas[name] = {'per_symbol_pp': per_symbol,
            'mean_four_accounts_pp': float(sum(per_symbol.values())/4) if complete else None}
    result = copy_prior_json({'report_version': 'bic_icl_cohort_report_v1', 'split': plan['split'],
        'repeat_id': repeat_id, 'in_primary': repeat_id == 0, 'matrix': names,
        'status': 'COMPLETE' if complete else 'INCOMPLETE', 'binding': binding,
        'stocks': stocks, 'delta_vs_original': deltas, 'points': rows,
        'coverage': lock['coverage'], 'nomination_performed': False, 'confirmation_allowed': False})
    validate_schema(result, 'report')
    return result


def verify_report(path: Path, expected: dict[str, Any]) -> None:
    """So toàn payload dựng từ checkpoint/raw/PIT; tự băm lại không thay verifier."""
    if read_envelope(path) != expected:
        raise ValueError('Report khác checkpoint, economics, source hoặc support đã dựng lại')


def check_economic_fixture() -> dict[str, Any]:
    """Oracle bốn chuỗi LONG/CASH độc lập, đối chiếu nhãn và engine tài khoản thật."""
    import itertools
    import math
    import pandas as pd
    from core.bic_icl_protocol import ROOT, ECONOMIC_FIXTURE, read_envelope_json
    recipe = read_envelope_json(ROOT/ECONOMIC_FIXTURE)
    frame = pd.DataFrame(recipe['prices'])
    frame['Datetime'] = pd.to_datetime(frame['Datetime'])
    cases = []
    for actions in itertools.product(recipe['actions'], repeat=len(recipe['cycles'])):
        capital, rows = recipe['initial_capital_vnd'], []
        peak, drawdown = capital, 0.
        for cycle, action in zip(recipe['cycles'], actions):
            decision = {'action': action, 'confidence': 'Cao', 'risk_reward_ratio': 1., 'latency_seconds': 0.}
            branches = {name: {'status': 'complete', 'decision': decision} for name in PRIOR_BRANCH_MODES}
            result = evaluate_point(frame, [], cycle['cutoff'], branches)
            if any(result[name] != cycle[reference] for name, reference in (
                    ('entry_date', 'entry'), ('exit_date', 'exit'), ('entry_open', 'entry_open'), ('exit_close', 'exit_close'))):
                raise ValueError('Fixture sai entry/exit T+2.5')
            # Tính tiền mua/bán bằng đơn vị VND, không dùng return đã sinh làm oracle.
            unit_buy = cycle['entry_open']*recipe['price_multiplier']*(1+recipe['slippage'])
            shares = capital/(unit_buy*(1+recipe['fee']))
            proceeds = shares*cycle['exit_close']*recipe['price_multiplier']*(1-recipe['slippage'])*(1-recipe['fee'])
            net = proceeds/capital-1.
            if not math.isclose(net, result['net_return_long'], abs_tol=1e-14):
                raise ValueError('Nhãn fixture khác oracle kinh tế độc lập')
            capital = proceeds if action == 'LONG' else capital
            peak = max(peak, capital); drawdown = max(drawdown, (peak-capital)/peak*100)
            rows.append({'point_id': 'FPT-'+cycle['cutoff'], 'context': {'symbol': 'FPT', 'as_of_date': cycle['cutoff']},
                'source_proof': {'prices': {'snapshot_start_date': '2023-01-06'}},
                'branches': branches, 'evaluation': result})
        metrics = _metric(rows, 'original')['account_metrics']
        expected_return = (capital/recipe['initial_capital_vnd']-1)*100
        if (not math.isclose(metrics['total_return_pct'], expected_return, abs_tol=1e-10)
                or not math.isclose(metrics['max_drawdown_pct'], drawdown, abs_tol=1e-10)):
            raise ValueError('Engine fixture khác vốn ghép/phí/MDD oracle')
        cases.append({'actions': list(actions), 'oracle_capital_vnd': capital,
            'oracle_return_pct': expected_return, 'oracle_mdd_pct': drawdown,
            'engine_metrics': metrics})
    return copy_prior_json({'status': 'PASS', 'scope': recipe['scope'], 'cases': cases, 'llm_calls': 0})
