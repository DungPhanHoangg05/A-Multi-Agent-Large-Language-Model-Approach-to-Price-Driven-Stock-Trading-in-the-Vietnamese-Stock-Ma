"""Chọn lambda trên train PIT cùng support A; công bố cả loss bất lợi và thiếu mẫu."""

from __future__ import annotations

import math
from typing import Any, Callable

import numpy as np
import pandas as pd

from core.backtest_engine import compute_round_trip_net_return
from core.bic_icl_memory import FrozenSources, METHOD_SHA, PREFIX, sha
from core.bic_icl_statistics import LAMBDAS, pool_statistics
from core.execution_prices import execution_prices_for_cycle
from core.historical_signals import digest
from core.improvement_prior import point_request
from core.prior_config import copy_prior_json
from core.prior_context import PriorContextAdapter
from core.train_pit_validation import fold_schedule, verify_regime_fit

VERSION = 'bic_icl_train_diagnostics_v1'
NAMES = ('A', 'R2', 'R4', 'R8')


def choose_lambda(losses: dict[str, dict[str, float | None]]) -> int | None:
    """Tie 1e−12 theo log loss, Brier rồi lambda nhỏ hơn; không nhận return."""
    if set(losses) != {'2', '4', '8'}:
        raise ValueError('Phải báo đủ ba lambda đã khóa')
    if all(losses[str(k)]['log_loss'] is None for k in LAMBDAS):
        return None
    for loss in losses.values():
        if any(type(loss.get(key)) not in (int, float) or not math.isfinite(loss[key]) or loss[key] < 0
               for key in ('log_loss', 'brier')):
            raise ValueError('Loss lambda thiếu hoặc không hữu hạn')
    eligible = list(LAMBDAS)
    for metric in ('log_loss', 'brier'):
        minimum = min(losses[str(k)][metric] for k in eligible)
        eligible = [k for k in eligible if losses[str(k)][metric]-minimum <= 1e-12]
    return min(eligible)


def score_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Giao hữu hạn chung mọi lambda/A; không dùng readiness để lọc scoring."""
    rows = copy_prior_json(rows)
    if len({r['episode_id'] for r in rows}) != len(rows):
        raise ValueError('Query diagnostics trùng ID')
    for row in rows:
        if (type(row['label']) is not int or row['label'] not in (0, 1)
                or type(row['net_long_return']) not in (int, float) or not math.isfinite(row['net_long_return'])
                or row['label'] != int(row['net_long_return'] > 0)
                or set(row['probability']) != set(NAMES) or set(row['ready']) != set(NAMES)):
            raise ValueError('Nhãn/probability/readiness diagnostics sai schema hoặc kinh tế')
        for name in NAMES:
            p = row['probability'][name]
            if (type(row['ready'][name]) is not bool or p is not None and (
                    type(p) not in (int, float) or not math.isfinite(p) or not 0 <= p <= 1)):
                raise ValueError('Xác suất phải hữu hạn trong [0,1] hoặc missing rõ ràng')

    def group(values: list[dict[str, Any]]) -> dict[str, Any]:
        """Giữ đủ mẫu số raw/ready, reliability bins kể cả rỗng và LONG lãi/lỗ."""
        paired = [r for r in values if all(r['probability'][n] is not None for n in NAMES)]
        loss, coverage, reliability = {}, {}, {}
        for name in NAMES:
            coverage[name] = {'raw': sum(r['probability'][name] is not None for r in values),
                'ready': sum(r['ready'][name] for r in values),
                'missing_ids': [r['episode_id'] for r in values if r['probability'][name] is None]}
            p = np.asarray([r['probability'][name] for r in paired], dtype=float)
            y = np.asarray([r['label'] for r in paired], dtype=float)
            clip = np.clip(p, 1e-6, 1-1e-6)
            loss[name] = {'log_loss': float(np.mean(-y*np.log(clip)-(1-y)*np.log(1-clip))) if paired else None,
                          'brier': float(np.mean((p-y)**2)) if paired else None}
            bins = []
            for i in range(5):
                mask = (p >= i/5) & ((p < (i+1)/5) if i < 4 else (p <= 1))
                bins.append({'lower': i/5, 'upper': (i+1)/5, 'upper_inclusive': i == 4,
                    'count': int(mask.sum()), 'mean_probability': float(p[mask].mean()) if mask.any() else None,
                    'win_fraction': float(y[mask].mean()) if mask.any() else None})
            reliability[name] = bins
        return {'query_count': len(values), 'common_count': len(paired), 'common_ids': [r['episode_id'] for r in paired],
            'coverage': coverage, 'loss': loss, 'reliability_bins': reliability,
            'long_returns': {label: {'count': len(selected), 'mean_fraction': float(np.mean(selected)) if selected else None}
                for label, selected in ((label, [r['net_long_return'] for r in values if
                    (r['net_long_return'] > 0 if label == 'win' else r['net_long_return'] < 0)]) for label in ('win', 'loss'))},
            'zero_count': sum(r['net_long_return'] == 0 for r in values)}
    overall = group(rows)
    losses = {str(k): overall['loss'][f'R{k}'] for k in LAMBDAS}
    selected = choose_lambda(losses)
    return {'status': 'LOCKED_TRAIN_SELECTION' if selected is not None else 'BLOCKED_NO_COMMON_POSTERIOR',
        'selected_lambda': selected, 'overall': overall,
        'delta_loss_vs_A': {str(k): {metric: None if selected is None else
            float(overall['loss'][f'R{k}'][metric]-overall['loss']['A'][metric]) for metric in ('log_loss', 'brier')}
            for k in LAMBDAS},
        'by_fold_symbol': {f'{fold}/{symbol}': group([r for r in rows if r['fold_id'] == fold and r['symbol'] == symbol])
            for fold in ('train_2021', 'train_2022') for symbol in ('FPT', 'MWG', 'VCB', 'VNM')},
        'by_regime': {regime: group([r for r in rows if r['regime'] == regime])
                      for regime in ('BULL', 'BEAR', 'CHOPPY', 'CONSOLIDATION')},
        'cluster_sensitivity': {quarter: group([r for r in rows if r['quarter'] != quarter])
            for quarter in sorted({r['quarter'] for r in rows})},
        'cluster_sensitivity_policy': 'LEAVE_ONE_QUERY_QUARTER_OUT_DESCRIPTIVE_NO_RESELECTION',
        'selection_bias': 'LAMBDA_SELECTED_ON_ALL_TRAIN_NOT_AN_ONLINE_CHOICE_IN_2021_OR_UNBIASED_CALIBRATION'}


def build_train_diagnostics(sources: FrozenSources, *, progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Replay 651 query/217 proof prefix, producer hoàn tất trước nhãn target."""
    sources.envelope('outputs/bayesian_benchmark/price_features/train_validation_index_v1.json')
    old = sources.envelope(f'{PREFIX}/train/diagnostics_resilient_v1.json')
    adapter = PriorContextAdapter({'enable_bayesian_prior': True}, root=sources.root)
    index = adapter.load_price_feature_index('outputs/bayesian_benchmark/price_features/train_validation_index_v1.json')
    records = adapter._retriever._memory.records
    folds = fold_schedule(records, index, pd.DatetimeIndex(adapter._vnindex.Datetime))
    if folds != old['folds'] or len(old['points']) != 651 or len(records) != 852:
        raise ValueError('Fold/query train khác nguồn đã đăng ký')
    fold_ids = {key: f for f, data in folds.items() for item in data['symbols'].values() for key in item['query_ids']}
    if set(fold_ids) != {r['episode_id'] for r in old['points']}:
        raise ValueError('651 query khác giao train của index')
    source_rows = {r['episode_id']: r for r in records}
    fits, rows = {}, []
    for number, previous in enumerate(old['points'], 1):
        record = source_rows[previous['episode_id']]
        symbol, cutoff = record['symbol'], record['as_of_date']
        proof = old['regime_fits'][cutoff]
        if sha(sources.root/proof['artifact_path']) != proof['artifact_sha256']:
            raise ValueError('HMM prefix train khác proof đã khóa')
        point = adapter.prepare(symbol, cutoff)
        shared = point.load_shared_checkpoint('outputs/historical_memory_run')
        if digest(shared) != previous['shared_sha256']:
            raise ValueError('Shared train khác nguồn diagnostics cũ')
        if cutoff not in fits:
            fits[cutoff] = verify_regime_fit(adapter, point)
            if fits[cutoff] != old['regime_fits'][cutoff]:
                raise ValueError('HMM/scaler/calibration train khác proof prefix')
        query = {'symbol': symbol, 'as_of_date': cutoff, 'current_regime': shared['market_regime']['regime_name'],
                 'current_signals': shared['current_signals']}
        # Nhãn target chỉ được đọc sau khi mọi producer posterior/selector đã xong.
        pooled = {str(k): pool_statistics(adapter._retriever, strength=k, **query) for k in LAMBDAS}
        a, _ = point_request(point, shared, index, 'A_tp_pool')
        pa = a['statistics']['metrics']['win_rate_long']['posterior_mean']
        if pa != previous['probability']['A_tp_pool'] or a['base_evidence_sha256'] != previous['base_hashes']['A_tp_pool']:
            raise ValueError('A reference train khác producer đã kiểm')
        frame, events = adapter.execution_data(symbol)
        entry, close = execution_prices_for_cycle(frame, events, cutoff, record['entry_date'], record['exit_date'])
        net = float(compute_round_trip_net_return(entry, close))
        if not math.isclose(net, previous['net_long_return'], abs_tol=1e-12, rel_tol=0):
            raise ValueError('Nhãn target khác engine chung')
        row = {'episode_id': record['episode_id'], 'symbol': symbol, 'as_of_date': cutoff,
            'fold_id': fold_ids[record['episode_id']], 'regime': query['current_regime'],
            'quarter': f'{cutoff[:4]}Q{(int(cutoff[5:7])-1)//3+1}', 'label': int(net > 0), 'net_long_return': net,
            'probability': {'A': pa, **{f'R{k}': pooled[str(k)]['posterior_mean'] for k in LAMBDAS}},
            'ready': {'A': a['gate']['metrics']['win_rate_long']['status'] == 'READY',
                      **{f'R{k}': pooled[str(k)]['ready'] for k in LAMBDAS}},
            'pooled': pooled, 'shared_sha256': digest(shared), 'A_base_sha256': a['base_evidence_sha256'],
            'scaler_sha256': index.scaler(symbol, cutoff)['scaler_sha256']}
        rows.append(row)
        if progress is not None and number % 40 == 0:
            progress(f'Đã replay {number}/651 query train')
    adapter.verify_sources()
    sources.verify()
    return copy_prior_json({'report_version': VERSION, 'method_sha256': METHOD_SHA, 'decision_calls': 0,
        'query_count': len(rows), 'source_diagnostics_sha256': sources.hashes[f'{PREFIX}/train/diagnostics_resilient_v1.json'],
        'source_hashes': {**sources.hashes, **adapter.source_hashes}, 'index_identity': index.identity,
        'folds': folds, 'regime_fits': fits, 'points': rows, 'summary': score_rows(rows)})
