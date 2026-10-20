"""Bootstrap cụm ngày cutoff, tái dựng tài khoản và CI theo protocol đã khóa."""

from __future__ import annotations

from collections import Counter
import hashlib
import math
from pathlib import Path
from typing import Any

import numpy as np

from core.backtest_engine import compute_round_trip_net_return
from core.historical_signals import digest
from core.improvement_protocol import SYMBOL_ORDER, protocol
from core.prior_config import copy_prior_json
from core.research_cohort import read_envelope

VERSION = 'improvement_bootstrap_v1'


def specification(selected: str) -> dict[str, Any]:
    """Gộp ID/contrast trùng trước outcome; family secondary độc lập với primary."""
    from core.improvement_prior import BASES
    if selected not in BASES:
        raise ValueError('Primary phải là full-prior đã đăng ký')
    matrix = list(dict.fromkeys(('original', 'bayesian', 'C2', selected,
                                selected+'_stats_only', selected+'_examples_only')))
    secondary = list(dict.fromkeys((selected, b) for b in
        ('C2', 'bayesian', selected+'_stats_only', selected+'_examples_only') if b != selected))
    return {'statistics_version': VERSION, **protocol()['holdout'], 'matrix': matrix,
        'primary': [selected, 'original'], 'secondary_contrasts': [list(p) for p in secondary],
        'secondary_count': len(secondary), 'initial_capital_vnd': 50_000_000.,
        'fee': .0025, 'slippage': .001, 'price_multiplier': 1000.,
        'account_contract': 'engine_fractional_shares_full_cash_round_trip',
        'invalid_draw': 'missing_any_symbol_or_nonfinite_any_branch',
        'inference_scope': 'conditional_on_locked_method_and_saved_decisions'}


def circular_indices(n_dates: int, block: int) -> np.ndarray:
    """Mỗi hàng là một draw; giữ thứ tự tổng hợp, không sắp lại theo ngày gốc."""
    if type(n_dates) is not int or n_dates < 1 or block not in (2, 4, 8) or type(block) is not int:
        raise ValueError('Số ngày/block bootstrap không hợp lệ')
    spec = protocol()['holdout']
    starts = np.random.Generator(np.random.PCG64(spec['seed'])).integers(
        0, n_dates, size=(spec['draws'], math.ceil(n_dates/block)))
    return ((starts[:, :, None]+np.arange(block)) % n_dates).reshape(spec['draws'], -1)[:, :n_dates]


def _inputs(plan: dict[str, Any], cases: list[dict[str, Any]]) -> tuple[Any, ...]:
    """Kiểm đủ G, nhãn kinh tế và cùng giá/action; dữ liệu lỗi không được điền CASH."""
    spec = plan['statistics']; names = spec['matrix']
    expected = {f'{s}-{day}' for s, days in plan['symbol_cutoffs'].items() for day in days}
    if len(cases) != len(expected) or {c['point_id'] for c in cases} != expected:
        raise ValueError('Bootstrap cần đủ common support đã khóa, không thừa/trùng/thiếu point')
    dates = sorted({c['as_of_date'] for c in cases}); day_index = {d: j for j, d in enumerate(dates)}
    shape = (len(dates), len(SYMBOL_ORDER))
    present = np.zeros(shape, dtype=bool); entry = np.ones(shape); exit_price = np.ones(shape)
    actions = np.zeros((*shape, len(names)), dtype=bool)
    keys = {'point_id', 'symbol', 'as_of_date', 'entry_date', 'exit_date', 'entry_open',
            'exit_close', 'net_return_long', 'actions'}
    for case in cases:
        if (set(case) != keys or case['symbol'] not in SYMBOL_ORDER
                or case['point_id'] != case['symbol']+'-'+case['as_of_date']
                or not case['as_of_date'] < case['entry_date'] <= case['exit_date']
                or set(case['actions']) != set(names)
                or any(a not in ('LONG', 'SHORT') for a in case['actions'].values())):
            raise ValueError('Case bootstrap sai schema, thời gian hoặc ma trận action')
        if plan['split'] == 'holdout_2024' and any(not case[k].startswith('2024-') for k in
                                                   ('as_of_date', 'entry_date', 'exit_date')):
            raise ValueError('Case bootstrap vượt split holdout')
        if any(type(case[k]) not in (int, float) or not math.isfinite(case[k]) for k in
               ('entry_open', 'exit_close', 'net_return_long')):
            raise ValueError('Giá/nhãn bootstrap không hữu hạn')
        net = compute_round_trip_net_return(case['entry_open'], case['exit_close'])
        if case['net_return_long'] != net:
            raise ValueError('Nhãn bootstrap khác hàm kinh tế dùng chung')
        d, s = day_index[case['as_of_date']], SYMBOL_ORDER.index(case['symbol'])
        if present[d, s]:
            raise ValueError('Một mã có nhiều point trong cùng cutoff')
        present[d, s] = True; entry[d, s] = case['entry_open']; exit_price[d, s] = case['exit_close']
        actions[d, s] = [case['actions'][name] == 'LONG' for name in names]
    return dates, present, entry, exit_price, actions


def rebuild(indices: np.ndarray, present: np.ndarray, entry: np.ndarray,
            exit_price: np.ndarray, actions: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Vector hóa theo draw/mã/nhánh; cùng phép tính cổ phiếu lẻ và phí của engine."""
    cash = np.full((len(indices), len(SYMBOL_ORDER), actions.shape[-1]), 50_000_000.)
    counts = np.zeros((len(indices), len(SYMBOL_ORDER)), dtype=np.int64)
    with np.errstate(over='ignore', invalid='ignore', divide='ignore', under='ignore'):
        for column in indices.T:
            exists = present[column]; counts += exists
            buy_price = entry[column, :, None]*1000.
            sell_price = exit_price[column, :, None]*1000.
            shares = (cash/(1.+.0025))/(buy_price*(1.+.001))
            notional = shares*sell_price*(1.-.001)
            after = notional-notional*.0025
            cash = np.where(exists[:, :, None] & actions[column], after, cash)
    return (cash/50_000_000.-1.)*100., counts


def _hash_array(value: np.ndarray) -> str:
    """Băm mảng little-endian cùng shape để tái lập chỉ số/draw không cần lưu JSON lớn."""
    array = np.ascontiguousarray(value, dtype='<i8' if value.dtype.kind in 'biu' else '<f8')
    return hashlib.sha256(str(array.shape).encode('ascii')+array.tobytes()).hexdigest()


def _interval(values: np.ndarray, valid: np.ndarray, alpha: float) -> dict[str, Any]:
    """Không sinh draw thay thế; giữ null khi thiếu tối thiểu 9.500 draw hợp lệ."""
    n = int(valid.sum()); enough = n >= protocol()['holdout']['minimum_valid']
    ci = [float(x) for x in np.quantile(values[valid], [alpha/2, 1-alpha/2], method='linear')] if enough else None
    return {'status': 'COMPLETE' if enough else 'BLOCKED', 'valid_draws': n, 'ci': ci,
        'confidence_level': 1.-alpha, 'quantile_method': 'linear',
        'reason': None if enough else 'INSUFFICIENT_VALID_DRAWS',
        'interpretation': 'POSITIVE' if ci is not None and ci[0] > 0 else 'NEGATIVE' if
            ci is not None and ci[1] < 0 else 'INCONCLUSIVE' if enough else 'BLOCKED'}


def bootstrap_report(plan: dict[str, Any], report: dict[str, Any], report_file_sha256: str) -> dict[str, Any]:
    """Nhận report vừa được runner verify; không đọc outcome để đổi cấu hình/contrast."""
    plan, report = (copy_prior_json(x) for x in (plan, report))
    spec = plan['statistics']
    if (spec != specification(plan['selection_decision']['primary_branch'])
            or report['binding']['plan_sha256'] != digest(plan) or report['matrix'] != spec['matrix']
            or report['report_version'] != 'improvement_holdout_report_v1'):
        raise ValueError('Report bootstrap khác manifest/matrix/statistics đã khóa')
    binding = {'plan_sha256': digest(plan), 'report_sha256': digest(report),
        'report_file_sha256': report_file_sha256, 'run_signature': report['binding']['run_signature'],
        'statistics_sha256': digest(spec), 'code_sha256': plan['code_sha256'], 'runtime': plan['runtime']}
    result = {'statistics_version': VERSION, 'binding': binding, 'split': plan['split'],
        'evidence_status': 'HOLDOUT_NOT_FOR_SELECTION' if plan['split'] == 'holdout_2024' else 'FIXTURE_ONLY',
        'specification': spec, 'status': 'INCOMPLETE', 'primary_point_estimate_pp': None, 'blocks': {},
        'limitations': ['CI điều kiện trên method/Decision đã lưu; không gồm bất định training/provider/LLM.',
            'Không chọn lại theo CI, secondary, subgroup hoặc sensitivity; không là return portfolio.']}
    if report['primary_status'] != 'COMPLETE':
        return result
    dates, present, entry, exit_price, actions = _inputs(plan, report['bootstrap_cases'])
    names = spec['matrix']; pairs = [spec['primary'], *spec['secondary_contrasts']]
    original, _ = rebuild(np.arange(len(dates))[None, :], present, entry, exit_price, actions)
    point = {f'{a}__{b}': float(np.mean(original[0, :, names.index(a)]-original[0, :, names.index(b)])) for a, b in pairs}
    primary_key = '__'.join(spec['primary'])
    if not math.isclose(point[primary_key], report['primary_delta_return_pp'], abs_tol=1e-7, rel_tol=1e-10):
        raise ValueError('Tái dựng tài khoản bootstrap khác point estimate engine')
    result.update(status='COMPLETE', primary_point_estimate_pp=point[primary_key], cutoff_dates=dates)
    for block in (spec['block'], *spec['sensitivity_blocks']):
        indices = circular_indices(len(dates), block)
        returns, counts = rebuild(indices, present, entry, exit_price, actions)
        missing = (counts == 0).any(axis=1); nonfinite = ~np.isfinite(returns).all(axis=(1, 2))
        valid = ~(missing | nonfinite)
        contrasts = {}
        for j, (a, b) in enumerate(pairs):
            values = np.mean(returns[:, :, names.index(a)]-returns[:, :, names.index(b)], axis=1)
            contrasts[f'{a}__{b}'] = {'point_estimate_pp': point[f'{a}__{b}'],
                'family': 'PRIMARY' if j == 0 else 'SECONDARY_BONFERRONI',
                **_interval(values, valid, .05 if j == 0 else .05/spec['secondary_count']),
                'valid_values_sha256': _hash_array(values[valid])}
        result['blocks'][str(block)] = {'role': 'PRIMARY' if block == 4 else 'SENSITIVITY',
            'draws': spec['draws'], 'valid_draws': int(valid.sum()), 'invalid_draws': int((~valid).sum()),
            'invalid_reasons': {'MISSING_SYMBOL': int(missing.sum()), 'NONFINITE_METRIC': int(nonfinite.sum()),
                                'BOTH': int((missing & nonfinite).sum())},
            'indices_sha256': _hash_array(indices), 'valid_mask_sha256': _hash_array(valid),
            'sample_counts': {s: {'minimum': int(counts[:, j].min()), 'maximum': int(counts[:, j].max()),
                'mean': float(counts[:, j].mean()), 'histogram': {str(k): int(v) for k, v in sorted(Counter(counts[:, j].tolist()).items())}}
                for j, s in enumerate(SYMBOL_ORDER)}, 'contrasts': contrasts}
    if result['blocks']['4']['valid_draws'] < spec['minimum_valid']:
        result['status'] = 'BLOCKED'
    return copy_prior_json(result)


def read_bootstrap(path: Path, expected: dict[str, Any]) -> dict[str, Any]:
    """Loader so toàn report tái tính; sửa CI rồi tự băm lại vẫn bị từ chối."""
    saved = read_envelope(path)
    if saved.get('statistics_version') != VERSION or digest(saved) != digest(expected):
        raise ValueError('Bootstrap khác report nguồn, RNG, quantile hoặc kết quả tái dựng')
    return saved
