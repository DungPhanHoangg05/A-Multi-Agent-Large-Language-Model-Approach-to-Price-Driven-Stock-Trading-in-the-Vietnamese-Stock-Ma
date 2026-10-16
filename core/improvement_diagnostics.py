"""Diagnostics A/C2 trên query train PIT, scoring tách khỏi producer prior."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from core.historical_signals import digest
from core.improvement_prior import point_request
from core.improvement_protocol import code_identity, protocol
from core.prior_config import copy_prior_json
from core.research_cohort import read_envelope
from core.research_input_lock import _write_once, runtime_identity
from core.train_pit_validation import fold_schedule, verify_regime_fit

VERSION = 'improvement_train_diagnostics_v1'


def score_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Chấm giao posterior hữu hạn, null không điền 0,5; chỉ clip khi tính loss."""
    def group(values: list[dict[str, Any]]) -> dict[str, Any]:
        """Báo cả raw/ready/missing và hai loss trên cùng giao query."""
        paired = [r for r in values if r['probability']['C2'] is not None and r['probability']['A_tp_pool'] is not None]
        result = {'query_count': len(values), 'paired_ids': [r['episode_id'] for r in paired], 'paired_count': len(paired),
            'coverage': {}, 'loss': {}, 'long_outcomes': {}}
        for name in ('C2', 'A_tp_pool'):
            observed = [r for r in values if r['probability'][name] is not None]
            for row in observed:
                p = row['probability'][name]
                if type(p) not in (int, float) or not math.isfinite(p) or not 0 <= p <= 1:
                    raise ValueError('Xác suất train phải hữu hạn trong [0,1]')
            result['coverage'][name] = {'raw': len(observed), 'ready': sum(r['ready'][name] for r in values),
                                        'missing_ids': [r['episode_id'] for r in values if r['probability'][name] is None]}
            if paired:
                p = np.asarray([r['probability'][name] for r in paired], dtype=float)
                y = np.asarray([r['label'] for r in paired], dtype=float)
                clipped = np.clip(p, 1e-6, 1-1e-6)
                result['loss'][name] = {'brier': float(np.mean((p-y)**2)),
                    'log_loss': float(np.mean(-(y*np.log(clipped)+(1-y)*np.log(1-clipped))))}
            else:
                result['loss'][name] = {'brier': None, 'log_loss': None, 'reason': 'NO_COMMON_POSTERIOR'}
        for label, condition in (('win', lambda r: r['net_long_return'] > 0), ('loss', lambda r: r['net_long_return'] < 0)):
            selected = [r['net_long_return'] for r in values if condition(r)]
            result['long_outcomes'][label] = {'count': len(selected), 'mean': float(np.mean(selected)) if selected else None}
        result['long_outcomes']['zero_count'] = sum(r['net_long_return'] == 0 for r in values)
        return result
    rows = copy_prior_json(rows)
    if len({r['episode_id'] for r in rows}) != len(rows):
        raise ValueError('Query train trùng ID')
    for row in rows:
        if type(row['label']) is not int or row['label'] not in (0, 1) or row['label'] != int(row['net_long_return'] > 0):
            raise ValueError('Nhãn train khác LONG ròng>0')
        if not math.isfinite(row['net_long_return']):
            raise ValueError('Return train không hữu hạn')
    return {'long_return_unit': 'fraction', 'overall': group(rows), 'by_fold_symbol': {f'{f}/{s}': group([r for r in rows if r['fold_id'] == f and r['symbol'] == s])
        for f in sorted({r['fold_id'] for r in rows}) for s in ('FPT', 'MWG', 'VCB', 'VNM')}}


def build_diagnostics(adapter: Any, index: Any, *, run_dir: str = 'outputs/historical_memory_run') -> dict[str, Any]:
    """Replay bank/scaler/HMM prefix, dựng A/C2 rồi mới đọc outcome query để scoring."""
    from core.backtest_engine import PRIOR_BRANCH_MODES
    from core.prior_backtest import evaluate_point
    if adapter._mode != 'historical_prefix':
        raise ValueError('Diagnostics cải tiến cần HMM prefix theo fold train')
    adapter._bind_price_feature_index(index)
    records = sorted(adapter._retriever._memory.records, key=lambda r: (r['as_of_date'], r['symbol']))
    folds = fold_schedule(records, index, pd.DatetimeIndex(adapter._vnindex.Datetime))
    query_folds = {key: fold for fold, data in folds.items() for item in data['symbols'].values() for key in item['query_ids']}
    rows, fits = [], {}
    historical_identity = None
    for record in records:
        point = adapter.prepare(record['symbol'], record['as_of_date'])
        shared = point.load_shared_checkpoint(run_dir)
        proof = shared['prior_provenance']['signals']
        identity = {k: proof[k] for k in ('config_sha256', 'code_sha256', 'runtime')}
        if historical_identity is None:
            historical_identity = identity
        elif historical_identity != identity:
            raise ValueError('Diagnostics cải tiến trộn identity lịch sử')
        if record['as_of_date'] not in fits:
            fits[record['as_of_date']] = verify_regime_fit(adapter, point)
        if record['episode_id'] not in query_folds:
            continue
        # Producer prior hoàn tất trước mọi truy cập nhãn target.
        c2, _ = point_request(point, shared, index, 'C2')
        a, _ = point_request(point, shared, index, 'A_tp_pool')
        if a['selection'] != c2['selection']:
            raise ValueError('Diagnostics A thay retrieval so với C2')
        frame, events = adapter.execution_data(record['symbol'])
        branch = {'status': 'complete', 'decision': {'action': 'LONG'}}
        economic = evaluate_point(frame, events, record['as_of_date'], {n: branch for n in PRIOR_BRANCH_MODES})
        net = economic['net_return_long']
        rows.append({'episode_id': record['episode_id'], 'symbol': record['symbol'], 'as_of_date': record['as_of_date'],
            'fold_id': query_folds[record['episode_id']], 'label': int(net > 0), 'net_long_return': net,
            'probability': {n: e['statistics']['metrics']['win_rate_long']['posterior_mean'] for n, e in (('C2', c2), ('A_tp_pool', a))},
            'ready': {n: e['gate']['metrics']['win_rate_long']['status'] == 'READY' for n, e in (('C2', c2), ('A_tp_pool', a))},
            'base_hashes': {n: e['base_evidence_sha256'] for n, e in (('C2', c2), ('A_tp_pool', a))},
            'shared_sha256': digest(shared), 'economic_label': {k: economic[k] for k in ('entry_date', 'exit_date', 'entry_open', 'exit_close')}})
    if len(records) != 852 or len(rows) != 651:
        raise ValueError('Diagnostics thật phải giữ 852 replay/651 query đã khóa')
    adapter.verify_sources()
    return copy_prior_json({'report_version': VERSION, 'decision_calls': 0, 'replayed_count': len(records),
        'query_count': len(rows), 'protocol_sha256': digest(protocol()), 'code_sha256': code_identity(),
        'runtime': runtime_identity(), 'sources': adapter.source_hashes, 'index_identity': index.identity,
        'historical_identity': historical_identity, 'folds': folds, 'regime_fits': fits, 'points': rows,
        'summary': score_rows(rows), 'limitations': ['Xác suất sự kiện lịch sử, không là calibration LLM hoặc expected-return policy.',
            'B giữ posterior C2; PIT hồi cứu không chứng nhận vintage provider/kiến thức LLM.']})


def run_diagnostics(adapter: Any, index: Any, destination: Path, *, verify_only: bool = False) -> dict[str, Any]:
    """Producer/loader/verifier chung, luôn dựng lại nguồn/PIT trước nhận report."""
    expected = build_diagnostics(adapter, index)
    if verify_only:
        report = read_envelope(destination)
        if report.get('report_version') != VERSION or digest(report) != digest(expected):
            raise ValueError('Diagnostics cải tiến khác nguồn/posterior/loss đã tái dựng')
        return report
    _write_once(destination, expected)
    return expected
