"""Numeric có mask: scaler quan sát được và retrieval PIT không đọc giá trị nhãn."""

from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any

import numpy as np

from core.mt_bicl_v41_protocol import CORE


def values(row: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    """Mask là nguồn sự thật; giá trị bị mask không được tham gia bất kỳ phép tính nào."""
    feature = row['features']
    raw, missing = feature['raw'], feature['missing_mask']
    if (len(raw) != 9 or len(missing) != 9 or any(type(v) is not bool for v in missing)
            or feature['feature_end_date'] != row['as_of_date']):
        raise ValueError('Schema/mốc thời gian feature v4.1 không hợp lệ')
    observed = np.asarray([0. if mask else v for v, mask in zip(raw, missing)], dtype=float)
    if not np.isfinite(observed).all() or any(v is None and not mask for v, mask in zip(raw, missing)):
        raise ValueError('Feature quan sát được thiếu hoặc không hữu hạn')
    return observed, np.asarray(missing, dtype=bool)


def core_valid(row: dict[str, Any]) -> bool:
    """Lõi đủ ba chiều; không dùng status complete-case hoặc agent/action để lọc."""
    _, mask = values(row)
    return bool(not mask[list(CORE)].any())


def fit_scaler(rows: list[dict[str, Any]], fit_end: str, *, query: str | None = None) -> dict[str, Any]:
    """Mỗi chiều fit riêng trên quan sát mature có lõi; không mượn thống kê tương lai."""
    if fit_end > '2020-12-31' or query is not None and fit_end >= query:
        raise ValueError('Scaler vượt cutoff train/query')
    eligible = [r for r in rows if r['label_eligible'] and r['exit_date'] <= fit_end
                and (query is None or r['exit_date'] < query) and core_valid(r)]
    if len({r['episode_id'] for r in eligible}) != len(eligible):
        raise ValueError('Scaler có ID trùng')
    matrix = np.asarray([values(r)[0] for r in eligible], dtype=float).reshape(-1, 9)
    masks = np.asarray([values(r)[1] for r in eligible], dtype=bool).reshape(-1, 9)
    n = (~masks).sum(axis=0)
    available = n >= 2
    means, scales = [], []
    for j in range(9):
        sample = matrix[~masks[:, j], j]
        means.append(float(sample.mean()) if available[j] else None)
        scales.append(float(max(sample.std(ddof=1), 1e-8)) if available[j] else None)
    return {'fit_end': fit_end, 'status': 'AVAILABLE' if bool(available[list(CORE)].all()) else 'INSUFFICIENT_CORE_HISTORY',
        'fit_ids': [r['episode_id'] for r in eligible], 'observed_count': n.tolist(),
        'available_dimensions': available.tolist(), 'mean': means, 'scale': scales}


def transform(row: dict[str, Any], scaler: dict[str, Any]) -> dict[str, Any]:
    """Điền0 sau chuẩn hóa; mask riêng phân biệt zero thật, xét OOD chỉ chiều quan sát."""
    raw, mask = values(row)
    available = np.asarray(scaler['available_dimensions'], dtype=bool)
    effective = mask | ~available
    z = np.zeros(9, dtype=float)
    for j in np.flatnonzero(~effective).tolist():
        z[j] = (raw[j] - scaler['mean'][j]) / scaler['scale'][j]
    if not np.isfinite(z).all():
        raise ValueError('Standardized feature không hữu hạn')
    reason = ('MISSING_CORE' if mask[list(CORE)].any() else
              'SCALER_UNAVAILABLE' if scaler['status'] != 'AVAILABLE' or bool((~mask & ~available).any()) else None)
    return {'z': z.tolist(), 'mask': effective.tolist(), 'source_mask': mask.tolist(),
            'eligible': reason is None, 'reason': reason, 'ood': bool((np.abs(z[~effective]) > 6).any())}


def distance(left: np.ndarray, lm: np.ndarray, right: np.ndarray, rm: np.ndarray) -> float:
    """Trung bình bình phương trên giao quan sát +0,25 tỷ lệ mask khác nhau."""
    shared = ~(lm | rm)
    if not bool(shared[list(CORE)].all()):
        raise ValueError('Retrieval không có đủ ba chiều lõi chung')
    return float(np.mean((left[shared] - right[shared])**2) + .25*np.mean(lm != rm))


def membership(query: dict[str, Any], rows: list[dict[str, Any]], scaler: dict[str, Any],
               regimes: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Đóng D/C bằng feature/mask/regime và chronology trước khi nạp nhãn sidecar."""
    cutoff = query['as_of_date']
    if scaler['fit_end'] >= cutoff:
        raise ValueError('Scaler membership fit tại/sau query')
    q = transform(query, scaler)
    result = {'query_id': query['episode_id'], 'prior': [], 'target': [], 'K': 0, 'm': 0,
              'query_z': q['z'], 'query_mask': q['mask'], 'ood': q['ood'], 'reason': q['reason']}
    if not q['eligible']:
        return result
    qz, qm = np.asarray(q['z']), np.asarray(q['mask'])
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if (row['symbol'] != query['symbol'] or row['exit_date'] >= cutoff
                or not row['label_eligible'] or not core_valid(row)):
            continue
        t = transform(row, scaler)
        if not t['eligible']:
            continue
        groups.setdefault(row['task_id'], []).append(row)
    ranked, target = [], []
    for task, group in groups.items():
        if task == query['task_id']:
            target = sorted(group, key=lambda r: (r['as_of_date'], r['episode_id']))[-32:]
            continue
        if not group[0]['block_complete'] or group[0]['block_end_date'] >= cutoff or len(group) < 2:
            continue
        ts = [transform(r, scaler) for r in group]
        matrix, masks = np.asarray([t['z'] for t in ts]), np.asarray([t['mask'] for t in ts])
        observed = (~masks).sum(axis=0)
        centroid_mask = observed == 0
        centroid = np.divide(np.where(masks, 0., matrix).sum(axis=0), observed,
                             out=np.zeros(9), where=observed > 0)
        rank_distance = distance(centroid, centroid_mask, qz, qm)
        regime, qr = regimes[group[0]['episode_id']]['task_name'], regimes[query['episode_id']]['query_name']
        if regime != 'UNKNOWN' and qr != 'UNKNOWN' and regime != qr:
            rank_distance += .25
        order = sorted(range(len(group)), key=lambda j: (distance(matrix[j], masks[j], qz, qm),
            -date.fromisoformat(group[j]['as_of_date']).toordinal(), group[j]['episode_id']))[:32]
        selected = sorted([group[j] for j in order], key=lambda r: (r['as_of_date'], r['episode_id']))
        latest = max(r['exit_date'] for r in group)
        ranked.append(((rank_distance, -date.fromisoformat(latest).toordinal(), task),
                       {'task_id': task, 'observation_ids': [r['episode_id'] for r in selected], 'distance': rank_distance}))
    k = max(i for i in (0, 1, 3) if i <= min(3, len(ranked)))
    prior = [item for _, item in sorted(ranked, key=lambda pair: pair[0])[:k]]
    ids = [i for task in prior for i in task['observation_ids']] + [r['episode_id'] for r in target]
    by_id = {r['episode_id']: r for group in groups.values() for r in group}
    if len(by_id) != sum(map(len, groups.values())):
        raise ValueError('Dữ liệu retrieval có ID trùng')
    intervals = sorted([(by_id[i]['entry_date'], by_id[i]['exit_date']) for i in ids] + [(query['entry_date'], query['exit_date'])])
    if len(ids) != len(set(ids)) or query['episode_id'] in ids or any(a[1] >= b[0] for a, b in zip(intervals, intervals[1:])):
        raise ValueError('D/C/query trùng ID hoặc entry–exit')
    result.update(prior=prior, target=[r['episode_id'] for r in target], K=k, m=len(target), reason='MASKED_NUMERIC_MEMBERSHIP_ONLY')
    return result


def support(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Đếm core/task trên input thật; không đếm mọi label thành observation đủ X."""
    labeled = [r for r in rows if r['label_eligible']]
    valid = [r for r in labeled if core_valid(r)]
    tasks = Counter(r['task_id'] for r in valid)
    return {'grid_queries': len(rows), 'labeled': len(labeled), 'core_valid': len(valid),
            'core_fraction': len(valid)/len(labeled) if labeled else 0.,
            'complete_case': sum(not any(r['features']['missing_mask']) for r in valid),
            'tasks_with_two_cycles': sum(n >= 2 for n in tasks.values())}
