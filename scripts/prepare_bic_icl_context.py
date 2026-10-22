"""Preflight task/context offline trên nguồn development đã khóa, không chạy Decision."""

from __future__ import annotations

from copy import deepcopy
import argparse
import hashlib
from pathlib import Path
import sys
from typing import Any
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from core.bayesian_memory import read_json
from core.bic_icl_memory import (FrozenSources, RevisionMemory, RevisionPriceIndex, RevisionRetriever,
    METHOD_SHA, PREFIX, _BUILT, oos_adapter, sha, verify_method)
from core.bic_icl_prompt import (VERSION, build_context_evidence, capture_decision_prompt, render_profiles,
    verify_context_evidence)
from core.bic_icl_statistics import posterior
from core.bic_icl_tasks import TaskSelector
from core.historical_signals import digest
from core.price_feature_index import _VERIFIED
from core.prior_config import copy_prior_json
from core.research_cohort import read_envelope
from core.research_input_lock import _write_once, runtime_identity
from scripts.prepare_bic_icl_memory import component_identity as memory_code_identity

NAMESPACE = ROOT/'outputs/bayesian_benchmark/bic_icl_v2'
PREPARATION = 'docs/plan/week10/validation_gates/memory_pool_v1.zip'
PREPARATION_SHA = '0a92be91d26364762cd8b324676254500a5ba6f1e9067f085537360b87a00dc6'
FIXTURE = 'docs/plan/week10/context_budget_fixture_v1.json'


def code_identity() -> dict[str, str]:
    """Bind code cũ nguyên vẹn và dependency context mới theo UTF-8/LF."""
    return {**memory_code_identity(), **{name: hashlib.sha256((ROOT/name).read_text('utf-8').encode()).hexdigest()
        for name in ('core/bic_icl_tasks.py', 'core/bic_icl_prompt.py', 'scripts/prepare_bic_icl_context.py', FIXTURE)}}


class FrozenPreparation:
    """Nạp byte W10-04 có chứng cứ độc lập, kiểm lại toàn bộ source/code/runtime đã bind."""

    def __init__(self) -> None:
        verify_method()
        if sha(ROOT/PREPARATION) != PREPARATION_SHA:
            raise ValueError('Bằng chứng memory/train khác bản đã nghiệm thu')
        self.hashes = {PREPARATION: PREPARATION_SHA}
        payloads = {}
        with zipfile.ZipFile(ROOT/PREPARATION) as archive:
            for kind, files in (('memory', ('memory.json', 'index.json', 'receipt.json')),
                                ('train', ('diagnostics.json', 'receipt.json'))):
                for file in files:
                    name = f'outputs/bayesian_benchmark/bic_icl_v2/{kind}_v1/{file}'
                    if (ROOT/name).read_bytes() != archive.read(name):
                        raise ValueError(f'Artifact khác byte W10-04 đã khóa: {name}')
                    self.hashes[name] = sha(ROOT/name)
                    payloads[(kind, file)] = read_envelope(ROOT/name)
        for kind in ('memory', 'train'):
            receipt = payloads[(kind, 'receipt.json')]
            if (receipt['version'] != 'bic_icl_preparation_v1' or receipt['kind'] != kind
                    or receipt['method_sha256'] != METHOD_SHA or receipt['code_sha256'] != memory_code_identity()
                    or receipt['runtime'] != runtime_identity()):
                raise ValueError('Receipt W10-04 khác protocol/code/runtime đang chạy')
            for file, expected in receipt['outputs'].items():
                if digest(payloads[(kind, file)]) != expected:
                    raise ValueError('Output W10-04 khác hash trong receipt')
        memory, index, train = (payloads[('memory', 'memory.json')], payloads[('memory', 'index.json')],
                                payloads[('train', 'diagnostics.json')])
        self.hashes.update(memory['source_hashes'])
        self.hashes.update(train['source_hashes'])
        self.verify()
        self.memory = RevisionMemory(memory, verified=_BUILT)
        self.index = RevisionPriceIndex(index, _verified=_VERIFIED)
        self.retriever = RevisionRetriever(self.memory)
        self.strength = train['summary']['selected_lambda']
        if self.strength != 8 or train['summary']['status'] != 'LOCKED_TRAIN_SELECTION':
            raise ValueError('Lambda train khác lựa chọn đã khóa; không chọn lại trên development')

    def verify(self) -> None:
        """Không nhận nguồn trôi sau khi tạo đối tượng xác minh."""
        verify_method()
        if any(sha(ROOT/name) != expected for name, expected in self.hashes.items()):
            raise ValueError('Nguồn context/W10-04 đã thay đổi')


def budget_evidence() -> tuple[dict[str, Any], dict[str, Any]]:
    """Fixture tổng hợp 3×2 để thử renderer, không đại diện quan sát hay return thị trường."""
    recipe = copy_prior_json(read_json(ROOT/FIXTURE))
    if (recipe['fixture_version'] != 'bic_icl_context_budget_fixture_v1' or recipe['k_tasks'] != 3
            or recipe['examples_per_task'] != 2 or len(recipe['examples']) != 6):
        raise ValueError('Fixture ngân sách không giữ biên 3×2')
    examples = [{'episode_id': item['episode_id'], 'agent_signals': {
        'trend': item['trend'], 'pattern': item['pattern'], 'alpha_consensus': 'NEUTRAL',
        'indicator_consensus': 'NEUTRAL', 'sentiment': 'NEUTRAL'},
        'outcome': {'net_return_pct': item['net_return_pct']}} for item in recipe['examples']]
    tasks = [{'task_id': f'fixture-task-{i+1}', 'examples': examples[2*i:2*i+2]} for i in range(3)]
    views = {}
    for method, records in (('R_pool', examples[:3]), ('R_task', examples)):
        views[method] = {mode: {'visible_metric_ids': [] if mode == 'examples_only' else ['win_rate_long'],
            'visible_example_ids': [] if mode == 'stats_only' else [r['episode_id'] for r in records],
            'visible_task_ids': [t['task_id'] for t in tasks] if method == 'R_task' and mode != 'stats_only' else [],
            'k_tasks': 3 if method == 'R_task' and mode != 'stats_only' else 0,
            'k_episodes': 0 if mode == 'stats_only' else len(records), 'fallback_to_original': False}
            for mode in ('full_prior', 'stats_only', 'examples_only')}
    result = {'evidence_version': VERSION, 'query': {'symbol': recipe['symbol'],
        'current_regime': recipe['regime'], 'as_of_date': '2023-01-06', 'current_signals': examples[0]['agent_signals']},
        'pool': {'statistics': posterior(recipe['statistics_counts'], 8), 'selection': {'tasks': examples[:3]}},
        'task_selection': {'tasks': tasks}, 'content_views': views, 'fixture_scope': recipe['scope']}
    result['base_evidence_sha256'] = digest(result)
    return result, recipe


def check_budget_fixture() -> dict[str, Any]:
    """Hai ngôn ngữ, sáu nhãn/return nguyên vẹn, report dài và schema legacy thật."""
    evidence, recipe = budget_evidence()
    def verify(actual: dict[str, Any]) -> None:
        if actual != evidence:
            raise ValueError('Fixture renderer bị thay đổi')
    report = {'scope': recipe['scope'], 'fixture_sha256_lf': hashlib.sha256(
        (ROOT/FIXTURE).read_text('utf-8').encode()).hexdigest(), 'languages': {}}
    for language in ('vi', 'en'):
        rendered = render_profiles(evidence, language, verifier=verify)
        if rendered['R_task']['status'] != 'AVAILABLE':
            raise ValueError('R_task BLOCKED trước API: fixture biên không render đủ 3×2')
        prefix = rendered['R_task']['profiles']['full_prior']['prefix']
        for example in recipe['examples']:
            if example['label']+'/'+example['return_text'] not in prefix:
                raise ValueError('Fixture bị cắt/mất nhãn hoặc return gốc sau format')
        if prefix.count('→') != 6 or not all(f'G{i}'+'{' in prefix for i in (1, 2, 3)):
            raise ValueError('Fixture mất task boundary hoặc cặp x→y')
        state = {'stock_name': recipe['symbol'], 'as_of_date': '2023-01-06', 'language': language,
            'time_frame': '1d', 'is_backtest': True, **{name+'_report': 'Dữ liệu lịch sử. '*3000
            for name in ('indicator', 'pattern', 'trend', 'alpha', 'sentiment')}}
        prompts = {method: {mode: capture_decision_prompt(state, r['prefix'], verifier=lambda s: None)
            for mode, r in part['profiles'].items()} for method, part in rendered.items()}
        report['languages'][language] = {'profiles': rendered, 'prompts': prompts,
            'max_prefix_chars': max(len(r['prefix']) for part in rendered.values() for r in part['profiles'].values()),
            'max_prompt_chars': max(len(p) for modes in prompts.values() for p in modes.values())}
    return report


def summarize_coverage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Đếm task đã hiển thị qua gate, tách raw selection; không đọc action/return target."""
    result = {}
    for symbol in ('FPT', 'MWG', 'VCB', 'VNM'):
        selected = [r['evidence'] for r in rows if r['point_id'].startswith(symbol+'-')]
        result[symbol] = {'query_count': len(selected),
            'prior_visible': sum(e['gate']['R_task']['stats_ready'] or e['gate']['R_task']['examples_ready'] for e in selected),
            'task_examples_ready': sum(e['gate']['R_task']['examples_ready'] for e in selected),
            'raw_at_least_two_tasks': sum(e['task_selection']['metadata']['k_tasks'] >= 2 for e in selected),
            'at_least_two_tasks': sum(e['gate']['R_task']['examples_ready'] and
                e['task_selection']['metadata']['k_tasks'] >= 2 for e in selected)}
    return result


def build_preflight() -> dict[str, Any]:
    """Kiểm metadata/context 60 điểm 2023, không sinh action/payoff hoặc mở cohort 2025."""
    frozen, sources = FrozenPreparation(), FrozenSources()
    plan = sources.envelope(f'{PREFIX}/development/plan.json')
    adapter = oos_adapter(plan)
    selector = TaskSelector(frozen.index, pd.DatetimeIndex(adapter._vnindex.Datetime))
    fixture = check_budget_fixture()
    rows = []
    schedule = sorted((d, s) for s, days in plan['symbol_cutoffs'].items() for d in days)
    if len(schedule) != 60:
        raise ValueError('Preflight phải giữ nguyên 60 point development')
    for number, (cutoff, symbol) in enumerate(schedule, 1):
        point = adapter.prepare(symbol, cutoff)
        document = sources.envelope(f'{PREFIX}/development/run/points/{symbol}-{cutoff}.json')
        shared = point.restore_full_bundle(document['full_bundle'])
        options = {'selector': selector, 'query_features': point.price_features(), 'strength': frozen.strength,
            'symbol': symbol, 'as_of_date': cutoff, 'current_regime': shared['market_regime']['regime_name'],
            'current_signals': shared['current_signals']}
        evidence = build_context_evidence(frozen.retriever, **options)
        def verify(actual: dict[str, Any]) -> None:
            point.verify_source(shared)
            verify_context_evidence(actual, frozen.retriever, **options)
        rendering = {}
        for language in ('vi', 'en'):
            profiles = render_profiles(evidence, language, verifier=verify)
            state = {**deepcopy(shared), 'language': language}
            def check_state(actual: dict[str, Any]) -> None:
                if actual != state:
                    raise ValueError('Budget check đổi state sealed ngoài trường ngôn ngữ đã khai báo')
                point.verify_source(shared)
            original = capture_decision_prompt(state, '', verifier=check_state)
            prompts = {method: {mode: capture_decision_prompt(state, r['prefix'], verifier=check_state)
                for mode, r in part['profiles'].items()} for method, part in profiles.items()}
            for method, part in profiles.items():
                for mode, request in part['profiles'].items():
                    if request['trace']['fallback_to_original'] and prompts[method][mode] != original:
                        raise ValueError('Prior-off context khác prompt Original')
            if all(profiles[m]['status'] == 'AVAILABLE' for m in ('R_pool', 'R_task')):
                if prompts['R_pool']['stats_only'] != prompts['R_task']['stats_only']:
                    raise ValueError('Hai stats-only không giữ cùng request/prefix')
            rendering[language] = {'profiles': profiles, 'prompts': prompts, 'original_prompt': original}
        rows.append({'point_id': f'{symbol}-{cutoff}', 'shared_sha256': digest(shared),
                     'evidence': evidence, 'rendering': rendering})
        if number % 10 == 0:
            print(f'Đã preflight context {number}/60 điểm, không gọi LLM', flush=True)
    adapter.verify_sources(); frozen.verify(); sources.verify()
    coverage = summarize_coverage(rows)
    available = all(part['status'] == 'AVAILABLE' for row in rows for lang in row['rendering'].values()
                    for part in lang['profiles'].values())
    task_coverage_eligible = (sum(v['at_least_two_tasks'] for v in coverage.values()) >= 6
                              and all(v['at_least_two_tasks'] >= 1 for v in coverage.values()))
    return copy_prior_json({'report_version': 'bic_icl_context_preflight_v1', 'method_sha256': METHOD_SHA,
        'technical_status': 'PASS' if available else 'BLOCKED', 'decision_calls': 0, 'confirmation_allowed': False,
        'candidate_technical_available': {method: all(lang['profiles'][method]['status'] == 'AVAILABLE'
            for row in rows for lang in row['rendering'].values()) for method in ('R_pool', 'R_task')},
        'task_coverage_status': 'METADATA_ELIGIBLE' if task_coverage_eligible else 'INSUFFICIENT_CACHED_UPSTREAM_COVERAGE',
        'task_coverage_rule': {'at_least_two_tasks_total': 6, 'at_least_two_tasks_per_symbol': 1,
            'scope': 'CACHED_UPSTREAM_ONLY_RECHECK_WITH_UPSTREAM_LOCK_NO_RELAXATION_OR_NOMINATION'},
        'lambda': frozen.strength, 'query_count': len(rows), 'budget_fixture': fixture, 'coverage': coverage,
        'source_hashes': {**frozen.hashes, **sources.hashes, **adapter.source_hashes}, 'points': rows,
        'language_check_scope': 'VI_SOURCE_REPORTS_BOTH_TEMPLATE_LANGUAGES_NO_ENGLISH_COHORT_OR_DECISIONS'})


def prepare(destination: Path, *, verify_only: bool = False) -> dict[str, Any]:
    """Artifact mới bất biến; verify dựng lại source/grouping/prefix/prompt, không sửa W10-04."""
    destination = destination.resolve()
    if destination.parent != NAMESPACE.resolve() or not destination.name.startswith('context_'):
        raise ValueError('Preflight cần thư mục context_* mới ngay dưới namespace bic_icl_v2')
    identity, runtime = code_identity(), runtime_identity()
    expected = build_preflight()
    if code_identity() != identity or runtime_identity() != runtime:
        raise ValueError('Code/runtime thay đổi trong lúc preflight')
    receipt = {'version': 'bic_icl_context_preparation_v1', 'code_sha256': identity, 'runtime': runtime,
               'report_sha256': digest(expected), 'technical_status': expected['technical_status']}
    if verify_only:
        if read_envelope(destination/'preflight.json') != expected or read_envelope(destination/'receipt.json') != receipt:
            raise ValueError('Preflight khác semantic hoặc code/runtime đã dựng lại')
    else:
        _write_once(destination/'preflight.json', expected)
        _write_once(destination/'receipt.json', receipt)
    return {'status': 'VERIFIED' if verify_only else 'PREPARED', 'technical_status': expected['technical_status'],
            'report_sha256': digest(expected), 'coverage': expected['coverage']}


def main() -> None:
    """CLI offline riêng, không nhận model/key hoặc lệnh chạy Decision/cohort thật."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    print(prepare(args.destination, verify_only=args.verify), flush=True)


if __name__ == '__main__':
    main()
