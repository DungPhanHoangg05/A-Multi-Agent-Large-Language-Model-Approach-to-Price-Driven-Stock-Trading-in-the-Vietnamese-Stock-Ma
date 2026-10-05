"""Smoke retriever/BRPP trên kho thật với query prefix PIT; không chạy giao dịch."""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import ExitStack
import copy
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import random
import sys
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.bayesian_memory import atomic_write_json, iso_date, read_json
from core.bayesian_retriever import (
    BayesianPriorRetriever, MODES, REGIMES, SCOPES, SYMBOLS, VERSIONS, format_compact_prior_prefix, normalize_signals,
)
from core.execution_prices import load_verified_execution_data, raw_point_in_time_snapshot
from core.historical_runner import HistoricalMemoryRunner, PrefixRegimeProvider
from core.historical_signals import HistoricalSignalExtractor, digest, snapshot_payload
from core.regime_detector import MarketRegimeDetector


def reference_statistics(population: list[dict[str, Any]], regime: str) -> dict[str, Any]:
    """Tính counts độc lập từ ID tập hợp; không gọi hàm thống kê của retriever."""
    wins = {r['episode_id'] for r in population if r['outcome']['net_return_pct'] > 0}
    trend = {r['episode_id'] for r in population if normalize_signals(r['agent_signals'])['trend'] == 'BULLISH'}
    pattern = {r['episode_id'] for r in population if normalize_signals(r['agent_signals'])['pattern'] == 'BULLISH'}
    universe = {r['episode_id'] for r in population}
    pairs = {'win_rate_long': (wins, universe), 'bull_trap_rate': ((trend | pattern) - wins, trend | pattern),
             'trend_false_bullish_rate': (trend - wins, trend), 'pattern_false_bullish_rate': (pattern - wins, pattern)}
    return {'regime': regime, 'population_count': len(population), 'metrics': {
        name: {'numerator': len(numerator), 'denominator': len(denominator),
               'rate': float(len(numerator) / len(denominator)) if denominator else None}
        for name, (numerator, denominator) in pairs.items()}}


def check_result(records: list[dict[str, Any]], query: dict[str, Any], result: dict[str, Any]) -> str:
    """Đối chiếu cutoff/scope, ranking, counts và BRPP trên dữ liệu đã xác minh."""
    meta, tasks = result['metadata'], result['tasks']
    for key in ('symbol', 'as_of_date', 'current_regime', 'mode', 'scope', 'seed'):
        if meta[key] != query[key]:
            raise ValueError('Metadata khác query đã gửi')
    if meta['requested_k'] != query['k']:
        raise ValueError('Metadata khác K yêu cầu')
    if query['k'] == 0:
        if tasks or result['stats'] is not None or meta['status'] != 'disabled' or meta['reason'] != 'k_zero':
            raise ValueError('Original K=0 nhận prior hoặc thống kê')
        if any(meta[key] is not None for key in ('eligible_count', 'matched_regime_count', 'candidate_count', 'effective_seed')):
            raise ValueError('Original K=0 vẫn tính pool hoặc seed')
        prefix = format_compact_prior_prefix(tasks, result['stats'])
        if prefix:
            raise ValueError('Original K=0 có BRPP')
        return prefix
    pool = [r for r in records if r['exit_date'] < query['as_of_date']
            and (query['scope'] == 'pooled' or r['symbol'] == query['symbol'])]
    population = [r for r in pool if r['regime'] == query['current_regime']]
    candidates = population if query['mode'] == 'bayesian_regime' else pool
    if (meta['eligible_count'], meta['matched_regime_count'], meta['candidate_count']) != (
            len(pool), len(population), len(candidates)):
        raise ValueError('Counts khác population PIT tham chiếu')
    if result['stats'] != reference_statistics(population, query['current_regime']):
        raise ValueError('Thống kê khác counts tham chiếu trên toàn population')
    signals = normalize_signals(query['current_signals'])
    scores = {r['episode_id']: float(sum(normalize_signals(r['agent_signals'])[f] == signals[f]
              for f in ('trend', 'pattern', 'alpha_consensus', 'indicator_consensus')) / 4) for r in candidates}
    effective_seed = None
    if query['mode'] == 'random':
        seed_fields = {key: meta[key] for key in ('sampling_version', 'seed', 'symbol', 'as_of_date', 'scope')}
        encoded = json.dumps(seed_fields, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        effective_seed = hashlib.sha256(encoded).hexdigest()
        expected = random.Random(int(effective_seed, 16)).sample(
            sorted(candidates, key=lambda r: r['episode_id']), min(query['k'], len(candidates)))
    else:
        expected = sorted(candidates, key=lambda r: (
            -scores[r['episode_id']] if query['mode'] != 'recent' else 0,
            -date.fromisoformat(r['exit_date']).toordinal(), r['episode_id']))[:query['k']]
    identifiers = [r['episode_id'] for r in expected]
    expected_scores = [{'episode_id': identifier,
                        'score': scores[identifier] if query['mode'] in {'similarity', 'bayesian_regime'} else None}
                       for identifier in identifiers]
    if (tasks != expected or meta['selected_ids'] != identifiers or meta['selected_count'] != len(expected)
            or meta['effective_seed'] != effective_seed or meta['selected_scores'] != expected_scores):
        raise ValueError('IDs/thứ tự/score/seed khác bộ chọn tham chiếu')
    status = 'empty' if not expected else 'partial' if len(expected) < query['k'] else 'complete'
    reason = ('no_eligible_history' if not pool else 'no_matching_regime') if not expected else (
        'insufficient_candidates' if status == 'partial' else None)
    if (meta['status'], meta['reason']) != (status, reason):
        raise ValueError('Trạng thái thiếu mẫu không đúng')
    if any(r['exit_date'] >= query['as_of_date'] for r in tasks):
        raise ValueError('Prior vắt ngang hoặc vượt cutoff')
    prefix = format_compact_prior_prefix(tasks, result['stats'])
    if len(prefix) > 600:
        raise ValueError('BRPP vượt 600 ký tự')
    json.dumps(result, ensure_ascii=False, allow_nan=False)
    return prefix


def validate_source(record: dict[str, Any], episode: dict[str, Any], signal: dict[str, Any],
                    proof: dict[str, Any], *, signature: str, price_hash: str) -> None:
    """Chặn query lịch sử sai episode, model/scaler, endpoint giá/tin hoặc checksum."""
    cutoff = record['as_of_date']
    HistoricalMemoryRunner._validate_regime(proof, cutoff)
    bundle = signal.get('result', {})
    provenance = bundle.get('provenance', {})
    if (episode.get('signature') != signature or episode.get('record') != record
            or episode.get('provenance', {}).get('regime') != proof
            or proof['state']['regime_name'] != record['regime']
            or signal.get('stage') != 'COMPLETE' or bundle.get('symbol') != record['symbol']
            or bundle.get('as_of_date') != cutoff or bundle.get('agent_signals') != record['agent_signals']
            or provenance.get('price_end_date') != cutoff or provenance.get('alpha_end_date') != cutoff
            or provenance.get('price_sha256') != price_hash
            or type(provenance.get('news_dates')) is not list
            or any(iso_date(day) > cutoff for day in provenance['news_dates'])
            or digest(bundle.get('reports')) != provenance.get('reports_sha256')):
        raise ValueError('Query lịch sử không có provenance PIT hợp lệ')


def context_specs(records: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any], str]]:
    """Chốt bốn mã/regime và bốn biên; chọn context không dùng outcome query."""
    contexts = []
    for symbol in sorted(SYMBOLS):
        rows = sorted((r for r in records if r['symbol'] == symbol), key=lambda r: r['as_of_date'])
        for regime in sorted(REGIMES):
            contexts.append(('observed', next(r for r in reversed(rows) if r['regime'] == regime), ''))
        boundary = next(r for r in rows if r['as_of_date'] == rows[0]['exit_date'])
        partial = next(r for r in rows if 0 < sum(
            p['exit_date'] < r['as_of_date'] and p['regime'] == r['regime'] for p in rows) < 3)
        contexts.extend([('equal_exit', boundary, ''), ('partial', partial, ''),
                         ('before_first', rows[0], (date.fromisoformat(rows[0]['as_of_date']) - timedelta(days=1)).isoformat()),
                         ('after_last', rows[-1], (date.fromisoformat(max(r['exit_date'] for r in records)) + timedelta(days=1)).isoformat())])
    return contexts


def verify() -> dict[str, Any]:
    """Nạp kho giá đã QA một lần; smoke chỉ đọc và mọi lỗi gây dừng trước xuất PASS."""
    bank = ROOT / 'data_manager/regime_memory_store.json'
    manifest_path = bank.with_suffix('.manifest.json')
    audit_path = ROOT / 'docs/plan/week2/memory_bank_audit.json'
    manifest = read_json(manifest_path)
    budget_path = ROOT / 'docs/plan/week3/prompt_budget_review.json'
    budget = read_json(budget_path)
    if (budget['status'] != 'PASS_WITH_REQUIRED_W4_HANDOFF' or budget['matrix_max_prompt_length'] >= 6500
            or any(row['prefix_length'] != 600 or row['prompt_length'] >= 6500 for row in budget['full_600_character_reserve'])):
        raise ValueError('Biên bản ngân sách bàn giao chưa đạt')
    for name, checksum in budget['source_text_sha256'].items():
        if hashlib.sha256((ROOT / name).read_text(encoding='utf-8').encode('utf-8')).hexdigest() != checksum:
            raise ValueError('Nguồn kiểm ngân sách thay đổi; cần chạy lại W3-11')
    run_dir = (ROOT / manifest['run_dir']).resolve()
    if not run_dir.is_relative_to(ROOT.resolve()):
        raise ValueError('Archive run phải nằm trong workspace nghiên cứu')
    protected: dict[str, str] = {}

    def pin(path: Path) -> str:
        """Ghi hash file đọc; phát hiện file đổi giữa kiểm chứng và xuất receipt."""
        name = path.resolve().relative_to(ROOT.resolve()).as_posix()
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        if name in protected and protected[name] != checksum:
            raise ValueError('File bằng chứng thay đổi giữa phép đo')
        protected[name] = checksum
        return checksum

    for path in (bank, manifest_path, audit_path, budget_path, ROOT / 'docs/plan/week1/historical_task_record.schema.json',
                 run_dir / 'run_manifest.json', *sorted((ROOT / 'data/execution_prices').glob('*')),
                 ROOT / 'data/historical/manifest.json'):
        if path.is_file():
            pin(path)
    index_manifest = read_json(ROOT / 'data/historical/manifest.json')
    pin(ROOT / 'data/historical' / index_manifest['files']['VNINDEX']['file'])
    frames: dict[str, Any] = {}
    loader_calls: Counter[str] = Counter()

    def loader(directory: Path, symbol: str) -> Any:
        """Tái dùng giá xác minh lúc cold load để đối chiếu query snapshot."""
        loader_calls[symbol] += 1
        value = load_verified_execution_data(directory, symbol)
        frames[symbol] = value[0]
        return value

    with ExitStack() as guards:
        for target in ('socket.socket.connect', 'socket.create_connection'):
            guards.enter_context(patch(target, side_effect=AssertionError('Smoke gọi mạng')))
        for target, method in ((MarketRegimeDetector, 'fit'), (HistoricalSignalExtractor, 'extract'),
                               (HistoricalMemoryRunner, 'run')):
            guards.enter_context(patch.object(target, method, side_effect=AssertionError('Smoke chạy sinh dữ liệu')))
        with patch('core.bayesian_memory.load_verified_execution_data', side_effect=loader):
            retriever = BayesianPriorRetriever(bank_path=bank, manifest_path=manifest_path, audit_path=audit_path)
        records = read_json(bank)
        if len(records) != 852 or dict(loader_calls) != {symbol: 1 for symbol in SYMBOLS}:
            raise ValueError('Kho smoke không đủ 852 hoặc nạp giá nhiều lần')
        identity = HistoricalMemoryRunner._read_envelope(run_dir / 'run_manifest.json')
        if digest(identity) != manifest['run_signature'] or digest(records) != manifest['records_sha256']:
            raise ValueError('Archive hoặc records khác signature phát hành')
        provider = PrefixRegimeProvider(run_dir / 'regimes')
        proofs: dict[str, Any] = {}
        contexts = []
        for kind, record, fixture_date in context_specs(records):
            source: dict[str, Any] = {'kind': 'boundary_fixture' if fixture_date else 'verified_historical_prefix',
                                     'source_episode_id': record['episode_id'],
                                     'source_as_of_date': record['as_of_date']}
            if fixture_date:
                source = {'kind': 'boundary_fixture', 'boundary_anchor_episode_id': record['episode_id'],
                          'boundary_anchor_as_of_date': record['as_of_date'],
                          'query_signal_and_regime_origin': 'fixed_synthetic_not_observed'}
            if not fixture_date:
                cutoff = record['as_of_date']
                episode_path = run_dir / 'episodes' / f"{record['symbol']}-{cutoff}.json"
                signal_path = run_dir / 'signals' / f"{record['symbol']}-{cutoff}.json"
                source.update(episode_sha256=pin(episode_path), signal_sha256=pin(signal_path))
                episode = HistoricalMemoryRunner._read_envelope(episode_path)
                signal = HistoricalMemoryRunner._read_envelope(signal_path)
                if cutoff not in proofs:
                    pin(run_dir / 'regimes' / f'VNINDEX-{cutoff}.json')
                    proofs[cutoff] = provider.get(cutoff, verify_only=True)
                proof = proofs[cutoff]
                if episode['provenance']['signal_checkpoint_sha256'] != source['signal_sha256']:
                    raise ValueError('Hash checkpoint tín hiệu khác episode')
                price_hash = digest(snapshot_payload(raw_point_in_time_snapshot(frames[record['symbol']], cutoff)))
                validate_source(record, episode, signal, proof, signature=manifest['run_signature'], price_hash=price_hash)
                source.update(regime_state=proof['state'], model_train_end_date=proof['metadata']['train_end_date'],
                              training_data_sha256=proof['metadata']['training_data_sha256'],
                              regime_artifact_sha256=proof['artifact_sha256'], price_snapshot_sha256=price_hash)
            query = {'symbol': record['symbol'], 'as_of_date': fixture_date or record['as_of_date'],
                     'current_regime': record['regime'], 'current_signals': copy.deepcopy(record['agent_signals']), 'seed': 42}
            if fixture_date:
                # Không mượn tín hiệu/ngữ cảnh của episode để giả định trạng thái ngày biên.
                query.update(current_regime='CHOPPY', current_signals={key: 'NEUTRAL' for key in record['agent_signals']})
            cases = []
            # Không đọc lại JSON/giá trong các query; provider chỉ dùng để chuẩn bị context.
            with patch('core.bayesian_retriever.read_json', side_effect=AssertionError('Query đọc JSON')), \
                 patch('core.bayesian_memory.read_json', side_effect=AssertionError('Query đọc JSON')), \
                 patch.object(retriever._memory, '_execution_loader', side_effect=AssertionError('Query đọc giá')):
                for scope in sorted(SCOPES):
                    configs = [(mode, 3) for mode in sorted(MODES)]
                    if kind == 'observed':
                        configs.append(('bayesian_regime', 0))
                    for mode, k in configs:
                        request = {**copy.deepcopy(query), 'mode': mode, 'scope': scope, 'k': k}
                        before = copy.deepcopy(request)
                        result = retriever.retrieve(**request)
                        prefix = check_result(records, request, result)
                        repeated = retriever.retrieve(**request)
                        if (request != before or repeated != result
                                or format_compact_prior_prefix(repeated['tasks'], repeated['stats']) != prefix):
                            raise ValueError('Query không xác định hoặc làm thay đổi input')
                        metadata = {name: value for name, value in result['metadata'].items() if name in {
                            'eligible_count', 'matched_regime_count', 'candidate_count', 'effective_seed',
                            'selected_count', 'selected_ids', 'selected_scores', 'status', 'reason'}}
                        cases.append({'mode': mode, 'scope': scope, 'k': k, 'metadata': metadata,
                                      'selected_dates': [{'episode_id': t['episode_id'], 'symbol': t['symbol'],
                                          'as_of_date': t['as_of_date'], 'entry_date': t['entry_date'],
                                          'exit_date': t['exit_date'], 'regime': t['regime']} for t in result['tasks']],
                                      'stats': result['stats'], 'prefix_length': len(prefix), 'prefix': prefix})
            contexts.append({'case_kind': kind, 'query': query, 'source': source, 'cases': cases})
        if records != read_json(bank):
            raise ValueError('Smoke làm thay đổi kho')
    for name, checksum in protected.items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != checksum:
            raise ValueError('Smoke làm thay đổi file bằng chứng')
    cases = [case for context in contexts for case in context['cases']]
    source_files = ('scripts/verify_bayesian_prior.py', 'core/bayesian_retriever.py', 'core/historical_runner.py',
                    'core/regime_detector.py', 'core/historical_signals.py')
    return {'format_version': 1, 'status': 'PASS', 'date': date.today().isoformat(), 'bank_sha256': protected[bank.relative_to(ROOT).as_posix()],
            'run_signature': manifest['run_signature'], 'real_bank_records': len(records), 'seed': 42, 'versions': dict(VERSIONS),
            'context_count': len(contexts), 'query_count': len(cases), 'repeat_query_count': len(cases),
            'context_kinds': dict(sorted(Counter(c['case_kind'] for c in contexts).items())),
            'result_status_counts': dict(sorted(Counter(c['metadata']['status'] for c in cases).items())),
            'max_prefix_length': max(c['prefix_length'] for c in cases), 'execution_loader_calls': dict(sorted(loader_calls.items())),
            'protected_file_sha256': protected, 'contexts': contexts,
            'source_text_sha256': {name: hashlib.sha256((ROOT / name).read_text(encoding='utf-8').encode('utf-8')).hexdigest() for name in source_files},
            'checks': {'strict_exit_cutoff': True, 'reference_statistics_and_selection': True,
                       'historical_query_prefix_and_signal_provenance': True, 'deterministic_no_input_mutation': True,
                       'original_empty_prefix': True, 'no_query_json_or_price_io': True, 'no_network_or_fit_or_generation': True,
                       'protected_files_unchanged': True, 'prefix_limit_600': True},
            'limitations': ['Kho prior phủ 2020–2022 do warm-up 600 phiên; sentiment thiếu tin là NEUTRAL.',
                            'Context trước/sau kho là fixture, không suy ra regime thị trường ngày giả định.',
                            'Đây là smoke retrieval/BRPP, không phải benchmark tốc độ hoặc giao dịch OOS.',
                            'W4 còn phải áp dụng ngân sách cap/guard prompt theo receipt W3-11.'],
            'prompt_budget_handoff': {'receipt_sha256': protected[budget_path.relative_to(ROOT).as_posix()],
                                      'status': budget['status'], 'max_full_reserve_prompt_length': max(
                                          row['prompt_length'] for row in budget['full_600_character_reserve']),
                                      'runtime_budget_gate_passed': False, 'required_w4_actions': budget['required_w4_actions']},
            'runtime_integration': False, 'oos_trading_backtest': False}


def main() -> None:
    """Xuất receipt mới; không viết vào archive, kho/model hoặc .env."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/plan/week3/prior_smoke.json')
    args = parser.parse_args()
    output = args.output.resolve()
    if any(output.is_relative_to(ROOT / directory) for directory in ('data', 'data_manager', 'outputs', 'agents', 'core')):
        raise ValueError('Receipt smoke không được ghi vào dữ liệu/archive hoặc module hệ thống')
    receipt = verify()
    atomic_write_json(output, receipt)
    print(f"Smoke PASS: {receipt['query_count']} query, BRPP tối đa {receipt['max_prefix_length']} ký tự; {output}")


if __name__ == '__main__':
    main()
