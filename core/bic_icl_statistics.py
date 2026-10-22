"""Posterior empirical Bayes rời nhau và evidence R_pool theo protocol v1."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import date
import math
from typing import Any

from scipy.stats import beta

from core.bayesian_retriever import normalize_signals
from core.historical_signals import digest
from core.prior_config import copy_prior_json
from core.prior_example_selection import select_price_examples

VERSION = 'bic_icl_disjoint_hierarchical_beta_v1'
LAMBDAS = (2, 4, 8)


def posterior(counts: dict[str, dict[str, int]], strength: int) -> dict[str, Any]:
    """Tính Beta plug-in; support bằng không không biến thành quan sát giả."""
    counts = copy_prior_json(counts)
    if type(strength) is not int or strength not in LAMBDAS or set(counts) != {'C', 'B1', 'B2'}:
        raise ValueError('Lambda/partition chưa được đăng ký')
    for item in counts.values():
        if (type(item) is not dict or set(item) != {'s', 'n'}
                or any(type(v) is not int for v in item.values()) or not 0 <= item['s'] <= item['n']):
            raise ValueError('Counts phải là số nguyên gốc, 0≤s≤n')
    c, b1, b2 = (counts[k] for k in ('C', 'B1', 'B2'))
    m2 = (b2['s']+1)/(b2['n']+2)
    m1 = (b1['s']+strength*m2)/(b1['n']+strength)
    a, b = c['s']+strength*m1, c['n']-c['s']+strength*(1-m1)
    lo, hi = (float(beta.ppf(q, a, b)) for q in (.025, .975))
    p, width = float(a/(a+b)), hi-lo
    if not all(math.isfinite(v) for v in (a, b, p, lo, hi)) or not 0 <= lo <= p <= hi <= 1:
        raise ValueError('Posterior không hữu hạn hoặc sai miền')
    reasons = []
    if c['n'] < 5:
        reasons.append('CONDITIONAL_SUPPORT_BELOW_FIVE')
    if b1['n']+b2['n'] < 20:
        reasons.append('BACKGROUND_SUPPORT_BELOW_TWENTY')
    if width > .75:
        reasons.append('INTERVAL_TOO_WIDE')
    return {'statistics_version': VERSION, 'lambda': strength, 'counts': counts, 'm2': float(m2),
        'status': 'OBSERVED' if c['n'] else 'NO_CONDITIONAL_HISTORY',
        'raw_conditional_rate': float(c['s']/c['n']) if c['n'] else None,
        'm1': float(m1), 'a': float(a), 'b': float(b), 'posterior_mean': p,
        'credible_interval': {'lower': lo, 'upper': hi, 'level': .95, 'width': float(width)},
        'hyperprior_weight': float(strength/(c['n']+strength)), 'ready': not reasons,
        'reason_codes': reasons, 'background_reason': 'NO_OTHER_REGIME_BACKGROUND' if b2['n'] == 0 else None,
        'interval_scope': 'CONDITIONAL_ON_PLUGIN_HYPERPRIOR_NOT_EFFECTIVE_SAMPLE_SIZE'}


def pool_statistics(retriever: Any, *, strength: int, **query: Any) -> dict[str, Any]:
    """C/B1/B2 trên cùng mã đã đóng, không lọc tuổi/similarity/feature cho counts."""
    query = copy_prior_json(query)
    if set(query) != {'symbol', 'as_of_date', 'current_regime', 'current_signals'}:
        raise ValueError('Query chỉ nhận mã/cutoff/regime/tín hiệu, không nhận outcome hoặc scope khác')
    query['current_signals'] = normalize_signals(query['current_signals'])
    pool = retriever.prepare_query(**query)
    rows = sorted(pool['eligible_tasks'], key=lambda r: r['episode_id'])
    retriever._assert_pool(rows, symbol=query['symbol'], as_of_date=query['as_of_date'], scope='same_symbol')
    expected = {key for key, r in retriever._verified_by_id.items()
                if r['symbol'] == query['symbol'] and r['exit_date'] < query['as_of_date']}
    if expected != {r['episode_id'] for r in rows}:
        raise ValueError('Population thống kê thiếu/thừa cycle so với snapshot PIT')
    signals = normalize_signals(query['current_signals'])
    groups: dict[str, list[dict[str, Any]]] = {'C': [], 'B1': [], 'B2': []}
    for row in rows:
        prior_signals = normalize_signals(row['agent_signals'])
        key = 'B2' if row['regime'] != query['current_regime'] else (
            'C' if all(prior_signals[k] == signals[k] for k in ('trend', 'pattern')) else 'B1')
        groups[key].append(row)
    ids = [r['episode_id'] for values in groups.values() for r in values]
    if len(ids) != len(set(ids)) or set(ids) != {r['episode_id'] for r in rows}:
        raise ValueError('Partition C/B1/B2 không rời nhau hoặc thiếu cycle')
    result = posterior({key: {'s': sum(r['outcome']['net_return_pct'] > 0 for r in values), 'n': len(values)}
                        for key, values in groups.items()}, strength)
    result['groups'] = {key: {'episode_ids': sorted(r['episode_id'] for r in values),
        'age_days': [(date.fromisoformat(query['as_of_date'])-date.fromisoformat(r['as_of_date'])).days for r in values],
        'month_cluster_counts': dict(sorted(Counter(r['as_of_date'][:7] for r in values).items()))}
        for key, values in groups.items()}
    result['population_count'] = len(rows)
    result['same_regime_count'] = len(groups['C'])+len(groups['B1'])
    result['query'] = {k: deepcopy(query[k]) for k in ('symbol', 'as_of_date', 'current_regime', 'current_signals')}
    result['statistics_sha256'] = digest(result)
    return copy_prior_json(result)


def pool_evidence(retriever: Any, *, selector: Any, query_features: dict[str, Any],
                  strength: int, **query: Any) -> dict[str, Any]:
    """Tách stats/examples gate; selection giữ nguyên across full và ablation."""
    statistics = pool_statistics(retriever, strength=strength, **query)
    selection = select_price_examples(retriever, selector=selector, query_features=query_features, **query)
    selected = selection['metadata']['selected_ids']
    records = {r['episode_id']: r for r in selection['tasks']}
    for i, left in enumerate(selected):
        for right in selected[i+1:]:
            a, b = records[left], records[right]
            if max(a['entry_date'], b['entry_date']) <= min(a['exit_date'], b['exit_date']):
                raise ValueError('Selector trả ví dụ có entry–exit overlap')
    reasons = []
    if statistics['same_regime_count'] < 20:
        reasons.append('REGIME_POPULATION_BELOW_TWENTY')
    if selection['metadata']['scaler_status'] != 'AVAILABLE':
        reasons.append('SCALER_UNAVAILABLE')
    if selection['metadata']['query_feature_status'] != 'AVAILABLE':
        reasons.append('QUERY_FEATURE_UNAVAILABLE')
    if not selected:
        reasons.append('NO_QUALIFIED_EXAMPLES')
    examples_ready = not reasons
    stats_ready = statistics['ready']
    views = {}
    for mode in ('full_prior', 'stats_only', 'examples_only'):
        metric_ids = ['win_rate_long'] if stats_ready and mode != 'examples_only' else []
        example_ids = list(selected) if examples_ready and mode != 'stats_only' else []
        views[mode] = {'visible_metric_ids': metric_ids, 'visible_example_ids': example_ids,
            'fallback_to_original': not (metric_ids or example_ids)}
    result = {'evidence_version': 'bic_icl_pool_evidence_v1', 'bank_sha256': retriever._bank_sha256,
        'query': deepcopy(statistics['query']), 'statistics': statistics, 'selection': selection,
        'gate': {'stats_ready': stats_ready, 'examples_ready': examples_ready, 'examples_reason_codes': reasons},
        'content_views': views}
    result['base_evidence_sha256'] = digest(result)
    return copy_prior_json(result)


def verify_pool_evidence(evidence: dict[str, Any], retriever: Any, **options: Any) -> None:
    """Rebuild counts/rank/readiness; rehash envelope không thay bằng chứng nguồn."""
    if copy_prior_json(evidence) != pool_evidence(retriever, **options):
        raise ValueError('Evidence R_pool khác partition, selector, gate hoặc nguồn đã tái dựng')
