"""Report primary/repeat và lựa chọn revision mới từ snapshot đã kiểm nguồn."""

from __future__ import annotations

from copy import deepcopy
import math
from pathlib import Path
from typing import Any

from core.improvement_prior import BASES
from core.improvement_protocol import MATRIX, SYMBOL_ORDER, nomination_rules
from core.paired_candidate_report import _coverage, _metric as _engine_metric
from core.prior_config import copy_prior_json
from core.prior_disagreement_analysis import _actions, _case
from core.historical_signals import digest
from core.research_cohort import read_envelope
from core.research_input_lock import _write_once

VERSION = 'improvement_report_v1'
REPEAT_VERSION = 'improvement_repeat_report_v1'
SELECTION_VERSION = 'improvement_selection_v1'
PAIRS = tuple([(name, 'original') for name in MATRIX if name != 'original'] +
              [(name, 'C2') for name in BASES if name != 'C2'] +
              [(base, base+suffix) for base in BASES for suffix in ('_stats_only', '_examples_only')])


def _metric(rows: list[dict[str, Any]], name: str) -> dict[str, Any]:
    """Chiếu đúng input kinh tế; không deep-copy toàn evidence cho mỗi metric nhóm."""
    compact = [{'point_id': p['point_id'], 'context': p['context'], 'source_proof': p['source_proof'],
        'branches': {name: p['branches'][name]}, 'evaluation': {**p['evaluation'],
            'branches': {name: p['evaluation']['branches'][name]}}} for p in rows]
    return _engine_metric(compact, name)


def _complete(row: dict[str, Any], names: Any) -> bool:
    """Unknown/planned không được tự điền CASH hoặc loại khỏi mẫu đã khóa."""
    return all(row['branches'][name]['status'] == 'complete' for name in names)


def _support(rows: list[dict[str, Any]], names: Any) -> dict[str, Any]:
    """Giữ mẫu số, point và lý do thiếu của từng nhánh."""
    return {'point_ids': [p['point_id'] for p in rows if _complete(p, names)],
        'count': sum(_complete(p, names) for p in rows),
        'excluded': [{'point_id': p['point_id'], 'reasons': {name: p['branches'][name]['status']
                     for name in names if p['branches'][name]['status'] != 'complete'}}
                     for p in rows if not _complete(p, names)]}


def _delta(rows: list[dict[str, Any]], a: str, b: str) -> dict[str, Any]:
    """Dựng lại hai tài khoản trên cùng support, không lấy mean cycle thay return."""
    selected = [p for p in rows if _complete(p, (a, b))]
    am, bm = _metric(selected, a), _metric(selected, b)
    aa, ba = am['account_metrics'], bm['account_metrics']
    return {**_support(rows, (a, b)), 'a': a, 'b': b, 'metrics_a': am, 'metrics_b': bm,
        'delta_return_pp': float(aa['total_return_pct']-ba['total_return_pct']) if selected else None,
        'delta_mdd_pp': float(aa['max_drawdown_pct']-ba['max_drawdown_pct']) if selected else None,
        'actions': _actions(selected, a, b),
        'status': 'COMPLETE' if selected and len(selected) == len(rows) else 'PROVISIONAL' if selected else 'NO_SUPPORT'}


def _group(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """G và từng cặp đều báo riêng, gồm cả các trường hợp bất lợi/prior-off."""
    common = [p for p in rows if _complete(p, MATRIX)]
    return {'global_common_support': _support(rows, MATRIX),
        'metrics': {name: _metric(common, name) for name in MATRIX},
        'coverage': {name: _coverage(rows, name) for name in MATRIX},
        'pairwise_support': {f'{a}__{b}': _delta(rows, a, b) for a, b in PAIRS}}


def build_report(plan: dict[str, Any], points: dict[str, list[dict[str, Any]]], binding: dict[str, Any]) -> dict[str, Any]:
    """Producer report primary; không nhận snapshot repeat hoặc lịch tự chọn."""
    plan, points, binding = (copy_prior_json(v) for v in (plan, points, binding))
    if set(points) != set(SYMBOL_ORDER) or binding['plan_sha256'] != digest(plan):
        raise ValueError('Report cải tiến khác plan/bốn mã')
    stocks, all_rows = {}, []
    for symbol in SYMBOL_ORDER:
        rows = sorted(points[symbol], key=lambda p: p['context']['as_of_date'])
        if [p['context']['as_of_date'] for p in rows] != plan['symbol_cutoffs'][symbol]:
            raise ValueError('Report cải tiến thiếu/thừa/trùng ngày')
        for p in rows:
            if (p['context']['symbol'] != symbol or p['point_id'] != f"{symbol}-{p['context']['as_of_date']}"
                    or p.get('repeat_id') != 0 or set(p['branches']) != set(MATRIX)
                    or set(p['report_context']['prior']) != set(MATRIX)):
                raise ValueError('Report primary chứa repeat hoặc sai projection/ma trận')
        all_rows += rows
        stock = _group(rows)
        stock['points'] = [{'point_id': p['point_id'], 'as_of_date': p['context']['as_of_date'],
            **p['report_context'], 'branch_status': {n: p['branches'][n]['status'] for n in MATRIX}} for p in rows]
        stock['regimes'] = {regime: _group([p for p in rows if p['report_context']['regime'] == regime])
                            for regime in ('BULL', 'BEAR', 'CHOPPY', 'CONSOLIDATION')}
        stock['time_groups'] = {label: _group([p for p in rows if int(p['context']['as_of_date'][5:7]) in months])
            for label, months in [('Q1', range(1, 4)), ('Q2', range(4, 7)), ('Q3', range(7, 10)),
                                  ('Q4', range(10, 13)), ('H1', range(1, 7)), ('H2', range(7, 13))]}
        stock['prior_off'] = {}
        stock['ablation'] = {}
        for a, b in PAIRS:
            subset = [p for p in rows if all(not (p['report_context']['prior'][n]['visible_metric_ids'] or
                p['report_context']['prior'][n]['visible_example_ids']) for n in (a, b))]
            stock['prior_off'][f'{a}__{b}'] = _delta(subset, a, b)
        for base in BASES:
            ready = [p for p in rows if p['report_context']['prior'][base]['stats_ready'] is True
                     and p['report_context']['prior'][base]['examples_ready'] is True]
            stock['ablation'][base] = {'global': {suffix: _delta(rows, base, base+suffix)
                for suffix in ('_stats_only', '_examples_only')},
                'both_ready': {suffix: _delta(ready, base, base+suffix) for suffix in ('_stats_only', '_examples_only')}}
        stocks[symbol] = stock
    complete = all(_complete(p, MATRIX) for p in all_rows) and bool(all_rows)
    deltas = {name: {s: _delta(points[s], name, 'original')['delta_return_pp'] for s in SYMBOL_ORDER} for name in BASES}
    cases = {name: [_case(p, name) for p in all_rows if p['branches'][name]['status'] == 'complete'] for name in MATRIX}
    return copy_prior_json({'report_version': VERSION, 'metric_version': 'cycle_risk_metrics_v2',
        'cohort_id': plan['cohort_id'], 'split': plan['split'], 'matrix': list(MATRIX), 'repeat_id': 0,
        'binding': binding, 'primary_status': 'COMPLETE' if complete else 'INCOMPLETE',
        'selection_evidence_status': 'DEVELOPMENT' if plan['split'] == 'development_2023' and binding['execution_mode'] == 'research' else 'NOT_APPLICABLE',
        'stocks': stocks, 'cases': cases,
        'candidate_delta_return_pp': {name: float(sum(deltas[name].values())/4) if complete else None for name in BASES},
        'leave_one_symbol_out': {name: {s: float(sum(v for k, v in deltas[name].items() if k != s)/3)
            if complete else None for s in SYMBOL_ORDER} for name in BASES},
        'limitations': ['Development 2023 exploratory; bốn tài khoản, không là return portfolio.',
            'Repeat không vào primary/selection; prior-use không là bằng chứng nhân quả.']})


def build_repeat_report(plan: dict[str, Any], blocks: list[dict[str, Any]], binding: dict[str, Any]) -> dict[str, Any]:
    """Báo ba lượt riêng, cặp phụ thuộc và duplicate, không chọn lượt tốt nhất."""
    blocks = copy_prior_json(blocks)
    expected = {(p, r) for p in plan['sample'] for r in (1, 2, 3)}
    actual = [(p['point_id'], p['repeat_id']) for p in blocks]
    if set(actual) != expected or len(actual) != len(expected):
        raise ValueError('Report repeat thiếu/thừa/trùng block đã khóa')
    names = [*MATRIX, 'original_duplicate']
    if any(set(p['branches']) != set(names) for p in blocks):
        raise ValueError('Report repeat thiếu duplicate/nhánh')
    by_slot = {(p['point_id'], p['repeat_id']): p for p in blocks}
    disagreement = {}
    for name in names:
        observations = [(by_slot[(pid, a)], by_slot[(pid, b)]) for pid in plan['sample'] for a, b in ((1, 2), (1, 3), (2, 3))]
        valid = [(a, b) for a, b in observations if _complete(a, [name]) and _complete(b, [name])]
        disagreement[name] = {'planned_pairs': len(observations), 'observed_pairs': len(valid),
            'disagreements': sum(a['branches'][name]['decision']['action'] != b['branches'][name]['decision']['action'] for a, b in valid),
            'by_stratum': {stratum: {'observed_pairs': sum(plan['strata'][a['point_id']] == stratum for a, b in valid),
                'disagreements': sum(plan['strata'][a['point_id']] == stratum and
                    a['branches'][name]['decision']['action'] != b['branches'][name]['decision']['action'] for a, b in valid)}
                for stratum in sorted(set(plan['strata'].values()))}}
    per_repeat, contrasts = {}, {}
    for r in (1, 2, 3):
        rows = [p for p in blocks if p['repeat_id'] == r]
        per_repeat[str(r)] = {s: {f'{a}__{b}': _delta([p for p in rows if p['context']['symbol'] == s], a, b)
            for a, b in PAIRS} for s in SYMBOL_ORDER}
    for a, b in PAIRS:
        values = []
        for r in (1, 2, 3):
            items = [per_repeat[str(r)][s][f'{a}__{b}'] for s in SYMBOL_ORDER]
            values.append(float(sum(item['delta_return_pp'] for item in items)/4)
                          if all(item['status'] == 'COMPLETE' for item in items) else None)
        contrasts[f'{a}__{b}'] = {'by_repeat_pp': values, 'mean_three_repeats_pp':
            float(sum(values)/3) if all(v is not None for v in values) else None}
    duplicates = [_actions([p for p in blocks if p['repeat_id'] == r and _complete(p, ('original', 'original_duplicate'))],
                           'original', 'original_duplicate') for r in (1, 2, 3)]
    off = {name: [_actions([p for p in blocks if p['repeat_id'] == r and _complete(p, (name, 'original')) and
        not (p['report_context']['prior'][name]['visible_metric_ids'] or p['report_context']['prior'][name]['visible_example_ids'])],
        name, 'original') for r in (1, 2, 3)] for name in MATRIX if name != 'original'}
    return copy_prior_json({'report_version': REPEAT_VERSION, 'binding': binding,
        'status': 'COMPLETE' if all(_complete(p, names) for p in blocks) else 'INCOMPLETE',
        'sample': plan['sample'], 'strata': plan['strata'], 'repeat_ids': [1, 2, 3], 'in_primary': False,
        'disagreement': disagreement, 'original_duplicate': duplicates, 'prior_off_original': off,
        'per_repeat_accounts': per_repeat, 'contrasts': contrasts,
        'limitations': ['Các cặp lặp phụ thuộc; không dùng để nomination hoặc chọn lượt tốt nhất.']})


def read_report(path: Path, expected: dict[str, Any]) -> dict[str, Any]:
    """Consumer bắt buộc so toàn report với snapshot đã verifier dựng lại."""
    report = read_envelope(path)
    if report.get('report_version') not in (VERSION, REPEAT_VERSION) or digest(report) != digest(expected):
        raise ValueError('Report cải tiến khác checkpoint/metric/support đã tái dựng')
    return report


def evaluate_selection(report: dict[str, Any], *, gates_passed: bool) -> dict[str, Any]:
    """Chỉ full-prior C2/A/B, giữ eligibility/promotion và tie quanh D_max."""
    report = copy_prior_json(report)
    if (report['report_version'] != VERSION or report['matrix'] != list(MATRIX) or type(gates_passed) is not bool
            or report.get('repeat_id') != 0 or report['split'] not in ('fixture', 'development_2023')):
        raise ValueError('Selector cải tiến chỉ nhận report primary đúng revision')
    rules = nomination_rules()
    complete = report['primary_status'] == 'COMPLETE' and set(report['stocks']) == set(SYMBOL_ORDER)
    support = {s: report['stocks'][s]['global_common_support']['count'] for s in SYMBOL_ORDER}
    complete = complete and support == rules['planned']
    for s in SYMBOL_ORDER:
        stock = report['stocks'][s]
        points = stock['points']
        ids = [p['point_id'] for p in points]
        observed = [p['point_id'] for p in points if all(p['branch_status'][n] == 'complete' for n in MATRIX)]
        if len(set(ids)) != len(ids) or stock['global_common_support']['point_ids'] != observed or support[s] != len(observed):
            raise ValueError('Support lựa chọn cải tiến khác point/branch thực')
        complete = complete and len(points) == rules['planned'][s] and observed == ids
    candidates = {}
    for name in BASES:
        returns, drawdowns, visible = {}, {}, {}
        for s in SYMBOL_ORDER:
            stock = report['stocks'][s]
            for point in stock['points']:
                if point['as_of_date'] >= '2024-01-01':
                    raise ValueError('Selector cải tiến không nhận holdout')
            from core.candidate_selection import _number
            a, b = (stock['metrics'][n]['account_metrics'] for n in (name, 'original'))
            if a is not None and b is not None:
                ar, br, am, bm = (_number(v) for v in (a['total_return_pct'], b['total_return_pct'],
                                                      a['max_drawdown_pct'], b['max_drawdown_pct']))
                if any(v is not None and v < 0 for v in (am, bm)):
                    raise ValueError('MDD tài khoản không được âm')
                returns[s] = ar-br if ar is not None and br is not None else None
                drawdowns[s] = am-bm if am is not None and bm is not None else None
            else:
                returns[s] = drawdowns[s] = None
            visible[s] = sum(p['branch_status'][name] == 'complete' and bool(p['prior'][name]['visible_metric_ids'] or
                             p['prior'][name]['visible_example_ids']) for p in stock['points'])
            if visible[s] != stock['coverage'][name]['prior_visible_count']:
                raise ValueError('Exposure lựa chọn khác visibility/Decision đã verify')
        finite = all(v is not None and math.isfinite(v) for v in [*returns.values(), *drawdowns.values()])
        d = float(sum(returns.values())/4) if complete and finite else None
        mean_mdd = float(sum(drawdowns.values())/4) if complete and finite else None
        max_mdd = float(max(drawdowns.values())) if complete and finite else None
        conditions = {'technical_gates_pass': gates_passed, 'primary_complete': complete,
            'paired_60': sum(support.values()) == 60, 'finite_return_mdd': finite,
            'exposure_at_least_6': sum(visible.values()) >= rules['min_visible'],
            'exposure_each_symbol': all(v >= rules['min_visible_per_symbol'] for v in visible.values())}
        promotion = {'positive_mean_return': d is not None and d > 0,
            'positive_at_least_3_symbols': sum(v is not None and v > 0 for v in returns.values()) >= rules['min_positive_symbols'],
            'mean_delta_mdd_at_most_2': mean_mdd is not None and mean_mdd <= rules['max_mean_delta_mdd_pp'],
            'max_delta_mdd_at_most_5': max_mdd is not None and max_mdd <= rules['max_symbol_delta_mdd_pp']}
        candidates[name] = {'conditions': conditions, 'eligible': all(conditions.values()),
            'eligibility_reasons': [k.upper() for k, v in conditions.items() if not v],
            'delta_return_by_symbol_pp': returns, 'delta_mdd_by_symbol_pp': drawdowns,
            'delta_return_pp': d, 'mean_delta_mdd_pp': mean_mdd, 'max_delta_mdd_pp': max_mdd,
            'visible_by_symbol': visible, 'visible_count': sum(visible.values()), 'visibility_denominator': 60,
            'promotion_conditions': promotion, 'promotion_reasons': [k.upper() for k, v in promotion.items() if not v],
            'promotable': all(conditions.values()) and all(promotion.values())}
    def rank(names: list[str]) -> list[str]:
        """Tie quanh cực đại hiện tại, không nối chuỗi xấp xỉ."""
        result = []
        while names:
            top = max(candidates[n]['delta_return_pp'] for n in names)
            tied = [n for n in names if top-candidates[n]['delta_return_pp'] <= rules['return_tie_pp']]
            tied.sort(key=lambda n: (candidates[n]['mean_delta_mdd_pp'], BASES.index(n)))
            result.extend(tied)
            names = [n for n in names if n not in tied]
        return result
    eligible = rank([n for n in BASES if candidates[n]['eligible']])
    promoted = rank([n for n in BASES if candidates[n]['promotable']])
    selected = (promoted or eligible or [None])[0]
    return {'research_candidate': selected, 'nomination_status': 'PROMOTED' if promoted else 'NOT_PROMOTED' if eligible else 'BLOCKED',
        'deployment_choice': selected if promoted else 'original', 'candidates': candidates,
        'eligible_order': eligible, 'promotable_order': promoted, 'paired_count': sum(support.values())}


def selection_artifact(report: dict[str, Any], gates: dict[str, Any], report_file_sha256: str) -> dict[str, Any]:
    """Fixture luôn BLOCKED; artifact thật cần report và gate đã consumer kiểm."""
    result = evaluate_selection(report, gates_passed=gates['status'] == 'PASS')
    real = report['split'] == 'development_2023' and report['binding']['execution_mode'] == 'research'
    decision = result if real else {**result, 'nomination_status': 'BLOCKED', 'research_candidate': None, 'deployment_choice': 'original'}
    return {'selection_version': SELECTION_VERSION, 'rules': nomination_rules(), 'risk_policy': 'OFF', **decision,
        'selection_evidence_status': 'DEVELOPMENT' if real else 'NOT_APPLICABLE',
        'fixture_protocol_result': result if not real else None,
        'binding': {**deepcopy(report['binding']), 'report_sha256': digest(report),
                    'report_file_sha256': report_file_sha256, 'technical_gates': gates}}


def read_selection(path: Path, expected: dict[str, Any]) -> dict[str, Any]:
    """Lựa chọn tự băm lại vẫn bị chặn khi khác phép tính và binding thật."""
    selection = read_envelope(path)
    if selection.get('selection_version') != SELECTION_VERSION or digest(selection) != digest(expected):
        raise ValueError('Selection cải tiến khác report/gate/rules đã tái dựng')
    return selection
