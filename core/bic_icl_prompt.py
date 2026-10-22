"""Evidence chung R_pool/R_task và BRPP hai ngôn ngữ, giữ schema Decision legacy."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import math
from typing import Any, Callable

from agents import decision_agent
from core.bayesian_memory import SYMBOLS, iso_date
from core.bayesian_retriever import normalize_signals
from core.bic_icl_statistics import pool_evidence
from core.bic_icl_tasks import TaskSelector, select_tasks
from core.historical_signals import digest
from core.prior_config import copy_prior_json

VERSION = 'bic_icl_context_evidence_v1'
REQUEST_VERSION = 'bic_icl_context_request_v1'
METHODS = ('R_pool', 'R_task')
MODES = ('full_prior', 'stats_only', 'examples_only')
LANGUAGES = ('vi', 'en')


class ContextBudgetError(ValueError):
    """Thiếu ngân sách là BLOCKED kỹ thuật, không cắt ví dụ hoặc biến thành prior-off."""


def build_context_evidence(retriever: Any, *, selector: TaskSelector, query_features: dict[str, Any],
                           strength: int, **query: Any) -> dict[str, Any]:
    """Một posterior W10-04 và hai selector; không cộng demonstrations vào counts."""
    pooled = pool_evidence(retriever, selector=selector, query_features=query_features, strength=strength, **query)
    tasks = select_tasks(retriever, selector=selector, query_features=query_features, **query)
    reasons = []
    if pooled['statistics']['same_regime_count'] < 20:
        reasons.append('REGIME_POPULATION_BELOW_TWENTY')
    if tasks['metadata']['scaler_status'] != 'AVAILABLE':
        reasons.append('SCALER_UNAVAILABLE')
    if tasks['metadata']['query_feature_status'] != 'AVAILABLE':
        reasons.append('QUERY_FEATURE_UNAVAILABLE')
    if not tasks['selected_task_ids']:
        reasons.append('NO_QUALIFIED_TASK_PAIR')
    gates = {'R_pool': deepcopy(pooled['gate']), 'R_task': {'stats_ready': pooled['gate']['stats_ready'],
        'examples_ready': not reasons, 'examples_reason_codes': reasons}}
    views = {}
    for method in METHODS:
        selected_ids = (pooled['selection']['metadata']['selected_ids'] if method == 'R_pool' else tasks['selected_episode_ids'])
        views[method] = {}
        for mode in MODES:
            metrics = ['win_rate_long'] if gates[method]['stats_ready'] and mode != 'examples_only' else []
            examples = list(selected_ids) if gates[method]['examples_ready'] and mode != 'stats_only' else []
            visible_tasks = list(tasks['selected_task_ids']) if method == 'R_task' and examples else []
            views[method][mode] = {'visible_metric_ids': metrics, 'visible_example_ids': examples,
                'visible_task_ids': visible_tasks, 'k_tasks': len(visible_tasks), 'k_episodes': len(examples),
                'fallback_to_original': not (metrics or examples)}
    result = {'evidence_version': VERSION, 'query': deepcopy(pooled['query']),
        'bank_sha256': retriever._bank_sha256, 'pool': pooled, 'task_selection': tasks,
        'gate': gates, 'content_views': views}
    result['base_evidence_sha256'] = digest(result)
    return copy_prior_json(result)


def verify_context_evidence(evidence: dict[str, Any], retriever: Any, **options: Any) -> None:
    """Tái dựng toàn bộ từ snapshot/scaler/lịch PIT, kể cả artifact được tự băm lại."""
    if copy_prior_json(evidence) != build_context_evidence(retriever, **options):
        raise ValueError('Context khác source, posterior, task, centroid, ordering hoặc visibility đã dựng lại')


def _example(record: dict[str, Any]) -> str:
    """x=T/P → y=nhãn theo dấu gốc và return ròng %, hai chữ số thập phân."""
    signals = normalize_signals(record['agent_signals'])
    signs = {'BULLISH': '+', 'BEARISH': '-', 'NEUTRAL': '0'}
    x = ''.join(signs[signals[k]] for k in ('trend', 'pattern'))
    net = record['outcome']['net_return_pct']
    if type(net) not in (int, float) or not math.isfinite(net):
        raise ValueError('Return ví dụ phải là số Python gốc hữu hạn')
    label = 'W' if net > 0 else 'L'
    return f"{x}→{label}/{float(net) if net != 0 else 0.:+.2f}%"


def render_prefix(evidence: dict[str, Any], method: str, mode: str, language: str) -> str:
    """Formatter thuần sau semantic verifier; không giảm K hoặc xóa nhãn để đủ 600."""
    evidence = copy_prior_json(evidence)
    if method not in METHODS or mode not in MODES or language not in LANGUAGES:
        raise ValueError('Method/mode/ngôn ngữ context chưa đăng ký')
    if (evidence.get('evidence_version') != VERSION or evidence.get('base_evidence_sha256') !=
            digest({k: v for k, v in evidence.items() if k != 'base_evidence_sha256'})):
        raise ValueError('Context sai version/hash; cần verifier nguồn trước render')
    view, query = evidence['content_views'][method][mode], evidence['query']
    if view['fallback_to_original']:
        return ''
    lines = [f"[BRPP EB1] {query['symbol']}/{query['current_regime']}; C=T/P"]
    if view['visible_metric_ids']:
        stats = evidence['pool']['statistics']
        interval = stats['credible_interval']
        lines[0] += (f"; nC={stats['counts']['C']['n']}; λ={stats['lambda']}; "
            f"p={stats['posterior_mean']:.2f}[{interval['lower']:.2f},{interval['upper']:.2f}]")
    if view['visible_example_ids']:
        lines.append('x=T/P(+:tăng,-:giảm,0:ngang); y=W/L,ròng%; W:ròng>0,L:≤0.' if language == 'vi' else
                     'x=T/P(+:up,-:down,0:flat); y=W/L,net%; W:net>0,L:≤0.')
        if method == 'R_task':
            for number, task in enumerate(evidence['task_selection']['tasks'], 1):
                lines.append(f"G{number}"+'{'+ ';'.join(_example(r) for r in task['examples'])+'}')
        else:
            lines.append('E{'+ ';'.join(_example(r) for r in evidence['pool']['selection']['tasks'])+'}')
    if view['visible_metric_ids']:
        lines.append('p=LONG ròng>0 lịch sử; mean[CrI95%] plug-in; không P(query)/E(return); SHORT=CASH.' if language == 'vi' else
                     'p=historical LONG net>0; mean[95% CrI], plug-in; not P(query)/E(return); SHORT=CASH.')
    else:
        lines.append('Ví dụ đã đóng; không dự báo query; SHORT=CASH.' if language == 'vi' else
                     'Closed examples; not a query forecast; SHORT=CASH.')
    prefix = '\n'.join(lines)
    if len(prefix) > 600:
        raise ContextBudgetError(f'BRPP {method}/{mode}/{language} dài {len(prefix)}>600; giữ nguyên task/nhãn')
    return prefix


def render_profiles(evidence: dict[str, Any], language: str, *,
                    verifier: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    """Kiểm cả ba view trước API; một view quá trần chặn toàn bộ candidate đó."""
    if not callable(verifier):
        raise ValueError('Renderer request cần semantic verifier nguồn')
    evidence = copy_prior_json(evidence)
    verifier(deepcopy(evidence))
    result = {}
    for method in METHODS:
        try:
            prefixes = {mode: render_prefix(evidence, method, mode, language) for mode in MODES}
        except ContextBudgetError as exc:
            result[method] = {'status': 'BLOCKED', 'reason': str(exc), 'profiles': {},
                'blocked_branch_ids': [method+suffix for suffix in ('_full', '_stats_only', '_examples_only')]}
            continue
        profiles = {}
        for mode, prefix in prefixes.items():
            result_mode = {'request_version': REQUEST_VERSION, 'method': method, 'content_mode': mode,
                'decision_contract_version': 'decision_legacy_v1', 'language': language,
                'query': deepcopy(evidence['query']), 'base_evidence_sha256': evidence['base_evidence_sha256'],
                'prefix': prefix, 'prefix_sha256': hashlib.sha256(prefix.encode()).hexdigest(),
                'trace': deepcopy(evidence['content_views'][method][mode])}
            result_mode['request_sha256'] = digest(result_mode)
            profiles[mode] = result_mode
        result[method] = {'status': 'AVAILABLE', 'reason': None, 'profiles': profiles, 'blocked_branch_ids': []}
    return copy_prior_json(result)


def capture_decision_prompt(state: dict[str, Any], prefix: str, *,
                            verifier: Callable[[dict[str, Any]], None]) -> str:
    """Chạy đúng distill/cap/template/schema legacy đến trước invoke, không có client/API."""
    state = copy_prior_json(state)
    iso_date(state.get('as_of_date'))
    if (not callable(verifier) or type(prefix) is not str or len(prefix) > 600
            or type(state.get('stock_name')) is not str or state['stock_name'] not in SYMBOLS
            or state.get('is_backtest') is not True or state.get('language') not in LANGUAGES
            or state.get('time_frame') not in ('1d', '1 ngày')
            or {'outcome', 'evaluation', 'actual_direction', 'actual_pct_change', 'net_return_long',
                'net_return', 'net_return_pct', 'entry_date', 'exit_date', 'entry_open', 'exit_close'}.intersection(state)):
        raise ValueError('Capture cần state backtest daily sạch và prefix đúng ngân sách')
    prompts = []
    class Captured(Exception):
        """Dừng trước retry/HTTP ở hook đã có của Decision Agent."""
    class NoClient:
        """Không có kết nối hoặc credential; lỗi nếu luồng vô tình đến invoke."""
        def invoke(self, *args: Any, **kwargs: Any) -> None:
            raise AssertionError('Capture không được gọi LLM')
    def prepare(actual: dict[str, Any]) -> tuple[dict[str, Any], str]:
        if actual != state:
            raise ValueError('State thay đổi trước capture')
        verifier(deepcopy(actual))
        return deepcopy(actual), prefix
    def capture(actual: dict[str, Any], prompt: str) -> None:
        if actual != state:
            raise ValueError('State thay đổi khi build prompt')
        prompts.append(prompt)
        raise Captured()
    try:
        decision_agent.create_final_trade_decider(NoClient(), _prior_preparer=prepare,
            _before_invoke=capture)(deepcopy(state))
    except Captured:
        pass
    if len(prompts) != 1 or len(prompts[0]) >= 6500:
        raise ContextBudgetError('Prompt Decision không được capture duy nhất dưới 6500 ký tự')
    return prompts[0]
