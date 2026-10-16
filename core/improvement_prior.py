"""Evidence A/C2 và prefix A/B theo protocol đã khóa, giữ retrieval bốn tín hiệu."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from core.bayesian_retriever import PREFIX_METRICS, normalize_signals, _prefix_task_line
from core.historical_signals import digest
from core.prior_conditional_statistics import conditional_metric
from core.prior_config import copy_prior_json
from core.prior_quality_gate import (
    SPLIT_GATE, _content_views, _readiness, retrieve_quality_evidence, validate_quality_evidence,
)

BASES = ('C2', 'A_tp_pool', 'B_semantic')
MODES = ('full_prior', 'stats_only', 'examples_only')
PROFILES = {base + suffix: (base, mode) for base in BASES for suffix, mode in
            (('', 'full_prior'), ('_stats_only', 'stats_only'), ('_examples_only', 'examples_only'))}
PREFIXES = {'C2': 'compact_brpp_v3', 'A_tp_pool': 'compact_brpp_v3_tp_v1',
            'B_semantic': 'compact_brpp_semantic_v1'}
REQUEST_VERSION = 'improvement_prior_request_v1'
EVIDENCE_VERSION = 'improvement_prior_evidence_v1'
STATISTICS_VERSION = 'conditional_tp_disjoint_beta_v1'
QUERY_FIELDS = ('symbol', 'as_of_date', 'current_regime', 'current_signals')


def tp_statistics(retriever: Any, **query: Any) -> dict[str, Any]:
    """Chia P bằng T/P; tái dùng đúng masks/nhãn, không đổi trường chấm retrieval."""
    legacy = retriever.conditional_statistics(**query)
    rows = [retriever._verified_by_id[key] for key in legacy['groups']['population']['episode_ids']]
    signals = normalize_signals(query['current_signals'])
    conditional, background = [], []
    for row in rows:
        if row['symbol'] != query['symbol'] or row['regime'] != query['current_regime'] or row['exit_date'] >= query['as_of_date']:
            raise ValueError('Population A vi phạm mã/regime/PIT')
        target = conditional if all(row['agent_signals'][key] == signals[key] for key in ('trend', 'pattern')) else background
        target.append(row)
    groups = {'population': rows, 'conditional': conditional, 'background': background}
    raw = {name: retriever._compute_statistics(values, symbol=query['symbol'], as_of_date=query['as_of_date'],
        current_regime=query['current_regime'], scope='same_symbol')['metrics'] for name, values in groups.items()}
    result = deepcopy(legacy)
    result.update(evidence_contract_version=EVIDENCE_VERSION, statistics_version=STATISTICS_VERSION,
                  conditional_count=len(conditional), background_count=len(background),
                  groups={name: {'episode_ids': [r['episode_id'] for r in values], 'cycle_count': len(values)}
                          for name, values in groups.items()})
    for key in PREFIX_METRICS:
        c, b, p = (raw[name][key] for name in ('conditional', 'background', 'population'))
        metric = conditional_metric(key, c['numerator'], c['denominator'], b['numerator'], b['denominator'])
        counts = metric['raw_counts']['population']
        if counts['success_count'] != p['numerator'] or counts['support_count'] != p['denominator']:
            raise ValueError('Counts A không bảo toàn P=C+B')
        result['metrics'][key] = metric
    result.pop('evidence_sha256')
    result['evidence_sha256'] = digest(result)
    return copy_prior_json(result)


def build_evidence(retriever: Any, base: str, **options: Any) -> dict[str, Any]:
    """C2/B giữ nguyên base hash; A chỉ đổi thống kê, readiness và version."""
    if type(base) is not str or base not in BASES or options.get('gate_version', SPLIT_GATE) != SPLIT_GATE:
        raise ValueError('Base cải tiến chưa đăng ký')
    evidence = retrieve_quality_evidence(retriever, **options)
    if base != 'A_tp_pool':
        return evidence
    evidence = deepcopy(evidence)
    evidence['evidence_contract_version'] = EVIDENCE_VERSION
    if evidence['statistics'] is not None:
        evidence['statistics'] = tp_statistics(retriever, **{k: evidence[k] for k in QUERY_FIELDS})
        evidence['gate'] = _readiness(evidence['statistics']['population_count'], evidence['statistics']['metrics'],
                                      evidence['selection']['metadata'], SPLIT_GATE)
        evidence['effective_k'] = len(evidence['gate']['ready_example_ids'])
        evidence['tasks'] = evidence['selection']['tasks'] if evidence['gate']['examples_ready'] else []
        evidence['content_views'] = _content_views(evidence['gate'], evidence['retrieved_k'])
    evidence.pop('base_evidence_sha256')
    evidence['base_evidence_sha256'] = digest(evidence)
    return copy_prior_json(evidence)


def validate_evidence(evidence: dict[str, Any], retriever: Any, base: str, *,
                      selector: Any = None, query_features: Any = None) -> None:
    """Đọc lại nguồn PIT và tái dựng; checksum tự khai không thay counts/partition."""
    evidence = copy_prior_json(evidence)
    if type(base) is not str or base not in BASES:
        raise ValueError('Base evidence không hợp lệ')
    if base != 'A_tp_pool':
        validate_quality_evidence(evidence, retriever, selector=selector, query_features=query_features)
        return
    config = evidence.get('config', {})
    if set(config) != {'enable_bayesian_prior', 'requested_k', 'gate_version',
                       'min_population_count', 'min_conditional_count', 'max_interval_width'}:
        raise ValueError('Config evidence A không hợp lệ')
    expected = build_evidence(retriever, base, **{k: evidence[k] for k in QUERY_FIELDS},
        **{k: config[k] for k in ('enable_bayesian_prior', 'requested_k', 'gate_version')},
        selector=selector, query_features=query_features)
    if digest(expected) != digest(evidence):
        raise ValueError('Evidence A khác nguồn, counts, gate hoặc version đã tái dựng')


def render_prefix(evidence: dict[str, Any], candidate: str) -> str:
    """Chỉ gọi sau kiểm evidence; không cắt K/nội dung để né giới hạn token."""
    from core.prior_prompt import _prefix
    if type(candidate) is not str or candidate not in PROFILES:
        raise ValueError('Profile prefix cải tiến không hợp lệ')
    base, mode = PROFILES[candidate]
    view = evidence['content_views'][mode]
    if view['fallback_to_original']:
        return ''
    if base != 'B_semantic':
        # Renderer C2 giữ nguyên byte; dùng view tương ứng mà không sửa base.
        projected = deepcopy(evidence)
        projected['content_views']['full_prior'] = deepcopy(view)
        prefix = _prefix(projected, 'C2')
        if base == 'A_tp_pool':
            prefix = prefix.replace('[BRPP v3]', '[BRPP v3 TP]', 1).replace('C=khớp T/P/A/I;', 'C=khớp T/P;', 1)
    else:
        stats = evidence['statistics']
        lines = [f"[BRPP v4] R={evidence['current_regime']}; k={view['visible_k']}"]
        if view['visible_metric_ids']:
            lines[0] += f"; nP={stats['population_count']}; nC={stats['conditional_count']}"
            metrics = []
            for label, key in zip(('W', 'BT', 'TF', 'PF'), PREFIX_METRICS):
                if key not in view['visible_metric_ids']:
                    metrics.append(f'{label}=N/A')
                else:
                    item = stats['metrics'][key]
                    counts, interval = item['raw_counts']['conditional'], item['credible_interval']
                    metrics.append(f"{label}={counts['success_count']}/{counts['support_count']}→"
                                   f"{item['posterior_mean']:.2f}[{interval['lower']:.2f},{interval['upper']:.2f}]")
            lines += ['; '.join(metrics),
                'W=LONG ròng>0; BT/TF/PF=bẫy/sai tăng; tỷ lệ lịch sử khớp T/P/A/I.',
                'Mean[CrI95%] plug-in, không P(query)/E(return); SHORT=CASH.']
        else:
            lines.append('Ví dụ lịch sử; không dự báo query; SHORT=CASH.')
        if view['visible_example_ids']:
            lines.append('T/P/A/I:+ tăng,- giảm,0 trung tính; W/L=LONG ròng lịch sử.')
            tasks = {r['episode_id']: r for r in evidence['tasks']}
            for key in view['visible_example_ids']:
                task = tasks[key]
                lines.append(_prefix_task_line(task, allow_sentiment=True).replace(
                    f"{task['symbol']}@{task['as_of_date']}", key, 1))
        prefix = '\n'.join(lines)
    if len(prefix) > 600:
        raise ValueError('BRPP cải tiến vượt 600 ký tự; giữ nguyên bằng chứng và K')
    return prefix


def build_request(evidence: dict[str, Any], candidate: str, retriever: Any, *,
                  selector: Any = None, query_features: Any = None) -> dict[str, Any]:
    """Request version mới, schema legacy ở cả visible và fallback."""
    if type(candidate) is not str or candidate not in PROFILES:
        raise ValueError('Profile request cải tiến không hợp lệ')
    base, mode = PROFILES[candidate]
    validate_evidence(evidence, retriever, base, selector=selector, query_features=query_features)
    if evidence['gate_version'] != SPLIT_GATE:
        raise ValueError('Request cải tiến chỉ nhận gate tách block')
    metadata = evidence['selection']['metadata'] if evidence['selection'] is not None else {}
    result = {'request_version': REQUEST_VERSION, 'candidate_id': candidate,
        'evidence_contract_version': evidence['evidence_contract_version'], 'prefix_version': PREFIXES[base],
        'decision_contract_version': 'decision_legacy_v1', 'content_mode': mode,
        'query': {k: evidence[k] for k in QUERY_FIELDS}, 'base_evidence_sha256': evidence['base_evidence_sha256'],
        'prefix': render_prefix(evidence, candidate), 'source': {'bank_sha256': evidence['bank_sha256'],
            **{k: metadata.get(k) for k in ('index_sha256', 'scaler_sha256', 'fold_id', 'calendar_prefix_sha256')}},
        'trace': evidence['content_views'][mode]}
    result['request_sha256'] = digest(result)
    return copy_prior_json(result)


def validate_request(request: dict[str, Any], evidence: dict[str, Any], retriever: Any, **options: Any) -> None:
    """Loader semantic phải rebuild request từ nguồn, không chỉ kiểm envelope."""
    request = copy_prior_json(request)
    expected = build_request(evidence, request.get('candidate_id'), retriever, **options)
    if digest(request) != digest(expected):
        raise ValueError('Request cải tiến khác evidence/prefix/visibility đã tái dựng')


def check_binding(request: dict[str, Any], state: dict[str, Any], prefix: str) -> None:
    """Biên Decision chỉ nhận request đã verifier nguồn tạo từ cùng Full seal."""
    request = copy_prior_json(request)
    keys = {'request_version', 'candidate_id', 'evidence_contract_version', 'prefix_version',
            'decision_contract_version', 'content_mode', 'query', 'base_evidence_sha256', 'prefix',
            'source', 'trace', 'request_sha256'}
    if set(request) != keys or type(request.get('candidate_id')) is not str or request.get('candidate_id') not in PROFILES:
        raise ValueError('Schema request cải tiến không hợp lệ')
    base, mode = PROFILES[request['candidate_id']]
    version = EVIDENCE_VERSION if base == 'A_tp_pool' else 'prior_evidence_v3'
    query = {'symbol': state.get('stock_name'), 'as_of_date': state.get('as_of_date'),
        'current_regime': (state.get('market_regime') or {}).get('regime_name'),
        'current_signals': normalize_signals(state.get('current_signals'))}
    forbidden = {'outcome', 'evaluation', 'net_return_pct', 'actual_direction', 'entry_date', 'exit_date',
                 'entry_open', 'exit_close', 'net_return', 'actual_pct_change', 'current_regime', 'regime_name'}
    if (request['request_version'] != REQUEST_VERSION or request['evidence_contract_version'] != version
            or request['decision_contract_version'] != 'decision_legacy_v1'
            or request['prefix_version'] != PREFIXES[base] or request['content_mode'] != mode
            or request['request_sha256'] != digest({k: v for k, v in request.items() if k != 'request_sha256'})
            or digest(query) != digest(request['query']) or forbidden.intersection(state)
            or request['prefix'] != prefix or len(prefix) > 600 or state.get('is_backtest') is not True
            or state.get('time_frame') not in ('1d', '1 ngày')):
        raise ValueError('Binding cải tiến khác Full/query/version hoặc chứa outcome')
    view = request['trace']
    if (bool(prefix) == view['fallback_to_original'] or view['visible_k'] != len(view['visible_example_ids'])
            or len(set(view['visible_example_ids'])) != view['visible_k']
            or not set(view['visible_metric_ids']).issubset(PREFIX_METRICS)
            or mode == 'stats_only' and view['visible_example_ids']
            or mode == 'examples_only' and view['visible_metric_ids']):
        raise ValueError('Visibility cải tiến khác content mode')


def point_request(point: Any, shared: dict[str, Any], index: Any, candidate: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Adapter nguồn hiện hữu kiểm Full/feature/index trước producer revision mới."""
    if type(candidate) is not str or candidate not in PROFILES:
        raise ValueError('Profile point cải tiến không hợp lệ')
    point.verify_source(shared)
    base = PROFILES[candidate][0]
    c2 = point.quality_evidence(shared, index)
    adapter = point._adapter
    enabled = c2['config']['enable_bayesian_prior'] and c2['config']['requested_k'] > 0
    selector = adapter._price_example_selectors.get(index.identity) if enabled else None
    features = point.price_features() if enabled else None
    evidence = c2 if base != 'A_tp_pool' else build_evidence(adapter._retriever, base,
        **{k: c2[k] for k in QUERY_FIELDS}, selector=selector, query_features=features,
        requested_k=c2['config']['requested_k'], enable_bayesian_prior=c2['config']['enable_bayesian_prior'])
    request = build_request(evidence, candidate, adapter._retriever, selector=selector, query_features=features)
    return evidence, request
