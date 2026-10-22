"""Task lịch sử 20 phiên neo cố định, chọn cặp độc lập nhãn kinh tế."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
import math
from typing import Any

import numpy as np
import pandas as pd

from core.bayesian_memory import REGIMES, SYMBOLS, iso_date
from core.historical_signals import digest
from core.prior_config import copy_prior_json
from core.prior_example_selection import PriceExampleSelector, _select_trace, selection_config

ANCHOR = '2018-01-02'
VERSION = 'bic_icl_task_selection_v1'
ROW_KEYS = {'episode_id', 'symbol', 'regime', 'as_of_date', 'entry_date', 'exit_date',
            'session_index', 'entry_session', 'exit_session', 'rank_position', 'rank_score', 'scaled_vector'}


class TaskSelector(PriceExampleSelector):
    """Lịch đã bind index; index0 phải đúng phiên neo, không neo lại theo query."""

    def __init__(self, index: Any, calendar: pd.DatetimeIndex) -> None:
        super().__init__(index, calendar)
        if self._days[0] != ANCHOR:
            raise ValueError('Lịch task phải bắt đầu đúng VNINDEX 2018-01-02')

    def task_id(self, symbol: str, regime: str, as_of_date: str) -> str:
        """Block của ngày as_of, không dùng entry/exit để đặt định danh."""
        return f'{symbol}:{regime}:{self.session_position(as_of_date)//20:04d}'


def _vector(value: Any) -> np.ndarray:
    """Bốn chiều JSON gốc, hữu hạn; không cắt outlier hoặc sửa kiểu dữ liệu."""
    if (type(value) is not list or len(value) != 4
            or any(type(x) not in (int, float) for x in value)):
        raise ValueError('Task cần vector bốn chiều số Python gốc')
    try:
        result = np.asarray(value, dtype=float)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError('Vector task vượt miền số hữu hạn') from exc
    if not np.isfinite(result).all():
        raise ValueError('Vector task không hữu hạn')
    return result


def _conflicts(row: dict[str, Any], selected: list[dict[str, Any]]) -> list[str]:
    """Cùng gap≥5 phiên và khoảng entry–exit rời nhau trên mọi demonstrations."""
    return [r['episode_id'] for r in selected if abs(row['session_index']-r['session_index']) < 5
            or max(row['entry_session'], r['entry_session']) <= min(row['exit_session'], r['exit_session'])]


def group_task_cycles(rows: list[dict[str, Any]], query_vector: list[float], *,
                      symbol: str, regime: str, as_of_date: str) -> dict[str, Any]:
    """Biên thuần không nhận outcome: centroid toàn nhóm, cặp intrinsic rồi diversity global."""
    rows = copy_prior_json(rows)
    cutoff, query = iso_date(as_of_date), _vector(query_vector)
    if (type(rows) is not list or type(symbol) is not str or symbol not in SYMBOLS
            or type(regime) is not str or regime not in REGIMES):
        raise ValueError('Cycle task phải là danh sách')
    ids, cycles, ranks, groups = set(), set(), set(), {}
    for row in rows:
        if type(row) is not dict or set(row) != ROW_KEYS:
            raise ValueError('Projection grouping thiếu field hoặc chứa nhãn/outcome')
        key, day = row['episode_id'], iso_date(row['as_of_date'])
        entry, exit_day = iso_date(row['entry_date']), iso_date(row['exit_date'])
        try:
            score = float(row['rank_score'])
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError('Score cycle vượt miền số hữu hạn') from exc
        if (type(key) is not str or not key or key in ids or row['symbol'] != symbol or row['regime'] != regime
                or (symbol, day) in cycles or not day < entry < exit_day < cutoff
                or any(type(row[k]) is not int for k in ('session_index', 'entry_session', 'exit_session', 'rank_position'))
                or row['session_index'] < 0 or row['rank_position'] < 1 or row['rank_position'] in ranks
                or row['entry_session'] != row['session_index']+1 or row['exit_session'] != row['session_index']+3
                or type(row['rank_score']) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1):
            raise ValueError('Cycle task trùng/sai scope, PIT, horizon hoặc thứ tự rank')
        _vector(row['scaled_vector'])
        ids.add(key); cycles.add((symbol, day)); ranks.add(row['rank_position'])
        task_id = f"{symbol}:{regime}:{row['session_index']//20:04d}"
        groups.setdefault(task_id, []).append(row)
    trace, by_id = [], {r['episode_id']: r for r in rows}
    for key, members in sorted(groups.items()):
        members.sort(key=lambda r: r['rank_position'])
        with np.errstate(over='ignore', invalid='ignore'):
            centroid = np.asarray([r['scaled_vector'] for r in members], dtype=float).mean(axis=0)
            distance = float(np.sqrt(np.mean((centroid-query)**2)))
        if not np.isfinite(centroid).all() or not np.isfinite(distance):
            raise ValueError('Centroid/khoảng cách task không hữu hạn')
        pair, cycle_trace = [], []
        for row in members:
            conflicts = _conflicts(row, pair)
            reason = 'EXAMPLES_PER_TASK_LIMIT' if len(pair) == 2 else 'INTRINSIC_DIVERSITY_CONFLICT' if conflicts else None
            cycle_trace.append({'episode_id': row['episode_id'], 'reason': reason,
                                'conflicting_ids': conflicts if reason == 'INTRINSIC_DIVERSITY_CONFLICT' else []})
            if reason is None:
                pair.append(row)
        trace.append({'task_id': key, 'block_id': members[0]['session_index']//20,
            'eligible_episode_ids': [r['episode_id'] for r in members], 'centroid': centroid.tolist(),
            'centroid_distance': distance, 'latest_as_of_date': max(r['as_of_date'] for r in members),
            'intrinsic_pair': [r['episode_id'] for r in pair], 'cycle_trace': cycle_trace,
            'status': 'EXCLUDED', 'reason_codes': [] if len(pair) == 2 else ['NO_INTRINSIC_PAIR'],
            'global_conflicting_ids': [], 'selected_order': None})
    # Tách sort ổn định để khoảng cách tăng, ngày giảm rồi ID tăng; không có nhãn.
    ranked = sorted((t for t in trace if not t['reason_codes']), key=lambda t: t['task_id'])
    ranked.sort(key=lambda t: t['latest_as_of_date'], reverse=True)
    ranked.sort(key=lambda t: t['centroid_distance'])
    selected, accepted = [], []
    for task in ranked:
        pair = [by_id[key] for key in task['intrinsic_pair']]
        conflicts = sorted({key for row in pair for key in _conflicts(row, accepted)})
        if len(selected) == 3:
            task['reason_codes'] = ['K_TASKS_LIMIT']
        elif conflicts:
            task.update(reason_codes=['GLOBAL_DIVERSITY_CONFLICT'], global_conflicting_ids=conflicts)
        else:
            task.update(status='SELECTED', selected_order=len(selected)+1)
            selected.append(task['task_id'])
            accepted.extend(pair)
    return copy_prior_json({'task_trace': trace, 'ranked_task_ids': [t['task_id'] for t in ranked],
        'selected_task_ids': selected, 'selected_episode_ids': [r['episode_id'] for r in accepted]})


def select_tasks(retriever: Any, *, selector: TaskSelector, query_features: dict[str, Any],
                 **query: Any) -> dict[str, Any]:
    """Lọc PIT/scope/feature/tuổi/similarity trước grouping; nhãn chỉ ghép sau chọn IDs."""
    if not isinstance(selector, TaskSelector) or set(query) != {'symbol', 'as_of_date', 'current_regime', 'current_signals'}:
        raise ValueError('Task cần selector lịch neo và query đúng schema')
    calendar = selector.calendar_metadata(query['as_of_date'])
    base = retriever.rank_price_candidates(index=selector.index, query_features=query_features, **query)
    # ranked_ids chứa mọi cycle đạt tuổi/similarity, độc lập K=3/gap của selector episode.
    qualified_trace, qualified_ids, _ = _select_trace(base['trace'], selector, query['as_of_date'], selection_config(None))
    lookup = {r['episode_id']: r for r in qualified_trace}
    population = {r['episode_id']: r for r in base['regime_population']}
    scaled = {r['episode_id']: r for r in selector.index.prior_features(
        query['symbol'], query['as_of_date'], qualified_ids)}
    transformed = selector.index.transform_query(query['symbol'], query['as_of_date'], query_features)
    rows = []
    for key in qualified_ids:
        record, trace, features = population[key], lookup[key], scaled[key]
        if features['status'] != 'AVAILABLE' or transformed['status'] != 'AVAILABLE':
            raise ValueError('Cycle đã qualify nhưng thiếu vector/scaler đã xác minh')
        rows.append({'episode_id': key, 'symbol': record['symbol'], 'regime': record['regime'],
            **{k: record[k] for k in ('as_of_date', 'entry_date', 'exit_date')},
            'session_index': selector.session_position(record['as_of_date']),
            'entry_session': selector.session_position(record['entry_date']),
            'exit_session': selector.session_position(record['exit_date']),
            'rank_position': trace['rank_position'], 'rank_score': trace['rank_score'],
            'scaled_vector': features['scaled_vector']})
    plan = (group_task_cycles(rows, transformed['scaled_vector'], symbol=query['symbol'],
        regime=query['current_regime'], as_of_date=query['as_of_date']) if transformed['status'] == 'AVAILABLE' else
        {'task_trace': [], 'ranked_task_ids': [], 'selected_task_ids': [], 'selected_episode_ids': []})
    task_lookup = {t['task_id']: t for t in plan['task_trace']}
    tasks = [{'task_id': key, 'block_id': task_lookup[key]['block_id'],
        'examples': [deepcopy(population[pid]) for pid in task_lookup[key]['intrinsic_pair']]}
        for key in plan['selected_task_ids']]
    # Qualification trace bỏ reason K/gap episode vì task dùng policy hai cấp riêng.
    eligibility = [{**r, 'qualified': r['episode_id'] in qualified_ids,
        'qualification_reasons': ([*r['reason_codes']] if r['status'] != 'SCORED' else
            (['PRIOR_TOO_OLD'] if r['age_days'] > 730 else [])+
            (['BELOW_MIN_SIMILARITY'] if r['base_score'] < .625 else []))}
        for r in qualified_trace]
    for row in eligibility:
        for key in ('selection_status', 'selection_reasons', 'selected_order', 'conflicting_selected_ids'):
            row.pop(key)
    metadata = {**base['metadata'], **calendar, 'task_selection_version': VERSION,
        'base_ranking_version': base['metadata']['ranking_version'], 'ranking_version': 'bic_icl_centroid_task_rank_v1',
        'cycle_ranking_version': 'signal_price_recency_v1', 'episode_config': selection_config(None),
        'calendar_anchor': ANCHOR, 'block_sessions': 20, 'requested_k_tasks': 3, 'examples_per_task': 2,
        'k_tasks': len(tasks), 'k_episodes': len(plan['selected_episode_ids']),
        'qualified_count': len(qualified_ids), 'qualified_ids': qualified_ids,
        'reason_codes': [] if tasks else ['NO_QUALIFIED_TASK_PAIR'],
        'exclusion_counts': dict(sorted(Counter(reason for t in plan['task_trace'] for reason in t['reason_codes']).items()))}
    return copy_prior_json({'selection_version': VERSION, 'tasks': tasks, **plan,
        'eligible_cycles': rows, 'qualification_trace': eligibility, 'metadata': metadata,
        'query_features': transformed, 'prior_features': scaled})
