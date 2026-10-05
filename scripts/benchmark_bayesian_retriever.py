"""Đo retriever trên kho thật và query PIT đã đóng băng; không gọi LLM."""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import ExitStack
import copy
from datetime import datetime, timezone
import gc
import hashlib
from importlib.metadata import version
import math
import os
from pathlib import Path
import platform
import statistics
import sys
from time import perf_counter_ns
from typing import Any, Callable
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.bayesian_memory import atomic_write_json, read_json
from core.bayesian_retriever import BayesianPriorRetriever, MODES, REGIMES, SCOPES, SYMBOLS, VERSIONS, format_compact_prior_prefix
from core.historical_runner import HistoricalMemoryRunner
from scripts.verify_bayesian_prior import check_result, validate_source

THRESHOLD_NS = 30_000_000
SMOKE_PATH = ROOT / 'docs/week3/prior_smoke.json'


def file_hash(path: Path) -> str:
    """Băm byte nguyên bản để kiểm bằng chứng trước/sau phép đo."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(samples_ns: list[int]) -> dict[str, Any]:
    """Tính p95 nearest-rank, không nội suy hoặc làm tròn trước khi xét gate."""
    if not samples_ns or any(type(n) is not int or n < 0 for n in samples_ns):
        raise ValueError('Mẫu thời gian phải là int Python gốc không âm và không rỗng')
    ordered = sorted(samples_ns)
    p95 = ordered[math.ceil(0.95 * len(ordered)) - 1]
    return {'count': len(ordered), 'min_ms': ordered[0] / 1e6,
            'median_ms': statistics.median(ordered) / 1e6, 'p95_ms': p95 / 1e6,
            'max_ms': ordered[-1] / 1e6, 'p95_ns': p95}


def validate_counts(warmup: int, samples: int) -> None:
    """Không cho giảm số lượt đã khóa để nhận một receipt PASS không đủ mẫu."""
    if type(warmup) is not int or warmup < 100 or type(samples) is not int or samples < 1000:
        raise ValueError('Cần ít nhất 100 warm-up và 1.000 mẫu cho mỗi mode/phép đo')


def measure(operations: list[Callable[[], Any]], expected: list[Any], *, warmup: int,
            samples: int, clock: Callable[[], int] = perf_counter_ns) -> list[int]:
    """Luân phiên query; đối chiếu kết quả ngoài timer, không trừ chi phí trong API."""
    if not operations or len(operations) != len(expected):
        raise ValueError('Operation và kết quả tham chiếu phải có cùng số context không rỗng')
    durations: list[int] = []
    for index in range(warmup + samples):
        slot = index % len(operations) if index < warmup else (index - warmup) % len(operations)
        if index < warmup:
            result = operations[slot]()
        else:
            start = clock()
            result = operations[slot]()
            elapsed = clock() - start
            if elapsed < 0:
                raise ValueError('Đồng hồ đo không tăng đơn điệu')
            durations.append(elapsed)
        if result != expected[slot]:
            raise ValueError('Query hoặc formatter khác kết quả đã xác minh trong lúc đo')
    return durations


def select_contexts(smoke: dict[str, Any], records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Lấy đúng 16 context quan sát, chặn nguồn regime/tín hiệu sai cutoff hoặc kho."""
    if (smoke['status'] != 'PASS' or smoke['versions'] != VERSIONS
            or smoke['real_bank_records'] != 852 or len(records) != 852 or smoke['seed'] != 42):
        raise ValueError('Smoke không khớp phiên bản/kho/seed đã khóa')
    contexts = [copy.deepcopy(c) for c in smoke['contexts'] if c['case_kind'] == 'observed']
    coverage = Counter((c['query']['symbol'], c['query']['current_regime']) for c in contexts)
    if coverage != Counter({(s, r): 1 for s in SYMBOLS for r in REGIMES}):
        raise ValueError('Cần đúng một context cho mỗi mã/regime')
    by_id = {r['episode_id']: r for r in records}
    for context in contexts:
        query, source = context['query'], context['source']
        record = by_id[source['source_episode_id']]
        state = source['regime_state']
        cutoff = query['as_of_date']
        if (source['kind'] != 'verified_historical_prefix' or source['source_as_of_date'] != cutoff
                or record['symbol'] != query['symbol'] or record['as_of_date'] != cutoff
                or record['regime'] != query['current_regime'] or record['agent_signals'] != query['current_signals']
                or query['seed'] != 42 or state['as_of_date'] != cutoff
                or state['feature_end_date'] > cutoff or source['model_train_end_date'] > cutoff
                or state['regime_name'] != query['current_regime']):
            raise ValueError('Nguồn query không khớp record/PIT')
        cases = [case for case in context['cases'] if case['k'] == 3]
        if Counter((c['mode'], c['scope']) for c in cases) != Counter({(m, s): 1 for m in MODES for s in SCOPES}):
            raise ValueError('Context không có đủ kết quả bốn mode/hai scope/K=3')
    return sorted(contexts, key=lambda c: (c['query']['symbol'], c['query']['current_regime']))


def assert_evidence(hashes: dict[str, str]) -> None:
    """Từ chối archive/giá/kho/model khác lần xác minh nguồn query ban đầu."""
    for relative, expected in hashes.items():
        path = (ROOT / relative).resolve()
        if not path.is_relative_to(ROOT.resolve()) or file_hash(path) != expected:
            raise ValueError(f'Bằng chứng thay đổi hoặc nằm ngoài repo: {relative}')


def stage_receipt(samples_ns: list[int], queries: list[dict[str, Any]]) -> dict[str, Any]:
    """Lưu mẫu thô và thống kê từng scope để tự tính lại percentile."""
    return {'summary': summarize(samples_ns), 'samples_ns': samples_ns, 'by_scope': {
        scope: summarize([n for i, n in enumerate(samples_ns) if queries[i % len(queries)]['scope'] == scope])
        for scope in sorted(SCOPES)}}


def benchmark(*, warmup: int = 100, samples: int = 1000) -> dict[str, Any]:
    """Đo tuần tự ba giai đoạn, giữ nguyên validation/deep copy của API công khai."""
    validate_counts(warmup, samples)
    smoke = read_json(SMOKE_PATH)
    pins = {**smoke['protected_file_sha256'], str(SMOKE_PATH.relative_to(ROOT)): file_hash(SMOKE_PATH)}
    assert_evidence(pins)
    # Nguồn tạo context phải nguyên vẹn; retriever có thể được tối ưu sau profile.
    for relative, expected in smoke['source_text_sha256'].items():
        if relative != 'core/bayesian_retriever.py':
            if hashlib.sha256((ROOT / relative).read_text(encoding='utf-8').encode()).hexdigest() != expected:
                raise ValueError(f'Code xác minh nguồn query đã thay đổi: {relative}')
    bank = ROOT / 'data_manager/regime_memory_store.json'
    records = read_json(bank)
    if file_hash(bank) != smoke['bank_sha256']:
        raise ValueError('Hash kho khác context smoke')
    contexts = select_contexts(smoke, records)
    for context in contexts:
        query, source = context['query'], context['source']
        stem = f"{query['symbol']}-{query['as_of_date']}.json"
        archive = ROOT / 'outputs/historical_memory_run'
        episode_path, signal_path = archive / 'episodes' / stem, archive / 'signals' / stem
        if file_hash(episode_path) != source['episode_sha256'] or file_hash(signal_path) != source['signal_sha256']:
            raise ValueError('Context khác checkpoint đã đóng băng')
        episode = HistoricalMemoryRunner._read_envelope(episode_path)
        signal = HistoricalMemoryRunner._read_envelope(signal_path)
        proof = episode['provenance']['regime']
        if (proof['state'] != source['regime_state'] or proof['artifact_sha256'] != source['regime_artifact_sha256']
                or proof['metadata']['train_end_date'] != source['model_train_end_date']
                or proof['metadata']['training_data_sha256'] != source['training_data_sha256']):
            raise ValueError('Nguồn model/regime khác bằng chứng prefix')
        validate_source(next(r for r in records if r['episode_id'] == source['source_episode_id']),
                        episode, signal, proof, signature=smoke['run_signature'], price_hash=source['price_snapshot_sha256'])

    print('Đã kiểm nguồn PIT và hash bằng chứng; bắt đầu cold load.', flush=True)
    start = perf_counter_ns()
    retriever = BayesianPriorRetriever(bank_path=bank, manifest_path=ROOT / 'data_manager/regime_memory_store.manifest.json',
                                      audit_path=ROOT / 'docs/week2/memory_bank_audit.json')
    cold_ns = perf_counter_ns() - start
    results: dict[str, Any] = {}
    query_receipts: list[dict[str, Any]] = []
    with ExitStack() as guards:
        for target in ('core.bayesian_memory.read_json', 'core.bayesian_retriever.read_json',
                       'socket.create_connection', 'socket.socket.connect', 'core.regime_detector.GaussianHMM.fit',
                       'core.historical_signals.HistoricalSignalExtractor.extract', 'core.historical_runner.HistoricalMemoryRunner.run'):
            guards.enter_context(patch(target, side_effect=AssertionError('Hot query không được đọc file/gọi API/fit HMM')))
        guards.enter_context(patch.object(retriever._memory, '_execution_loader',
                                         side_effect=AssertionError('Hot query không được nạp giá')))
        for mode in sorted(MODES):
            queries, expected, prefixes = [], [], []
            for context in contexts:
                for scope in sorted(SCOPES):
                    query = {**copy.deepcopy(context['query']), 'mode': mode, 'scope': scope, 'k': 3}
                    result = retriever.retrieve(**query)
                    prefix = check_result(records, query, result)
                    case = next(c for c in context['cases'] if (c['mode'], c['scope'], c['k']) == (mode, scope, 3))
                    if (prefix != case['prefix'] or result['stats'] != case['stats']
                            or any(result['metadata'][key] != value for key, value in case['metadata'].items())):
                        raise ValueError('Đầu ra khác tham chiếu smoke đã đóng băng')
                    queries.append(query)
                    expected.append(result)
                    prefixes.append(prefix)
            original_queries, original_expected = copy.deepcopy(queries), copy.deepcopy(expected)
            retrieval = [lambda q=q: retriever.retrieve(**q) for q in queries]
            formatter = [lambda r=r: format_compact_prior_prefix(r['tasks'], r['stats']) for r in expected]

            def retrieve_and_format(query: dict[str, Any]) -> tuple[dict[str, Any], str]:
                """Đo toàn chuỗi retrieval→BRPP, giữ cả kết quả để kiểm ngoài timer."""
                result = retriever.retrieve(**query)
                return result, format_compact_prior_prefix(result['tasks'], result['stats'])

            combined = [lambda q=q: retrieve_and_format(q) for q in queries]
            stages = {}
            for name, operations, outputs in (('retrieval', retrieval, expected), ('formatter', formatter, prefixes),
                                               ('retrieval_and_format', combined, list(zip(expected, prefixes)))):
                timings = measure(operations, outputs, warmup=warmup, samples=samples)
                stages[name] = stage_receipt(timings, queries)
            if queries != original_queries:
                raise ValueError('API thay đổi query trong benchmark')
            if expected != original_expected:
                raise ValueError('Formatter thay đổi dữ liệu tham chiếu trong benchmark')
            passed = stages['retrieval']['summary']['p95_ns'] < THRESHOLD_NS
            results[mode] = {'gate_passed': passed, **stages}
            query_receipts.extend({'query': q, 'selected_ids': r['metadata']['selected_ids'],
                                   'eligible_count': r['metadata']['eligible_count'], 'population_count': r['stats']['population_count']}
                                  for q, r in zip(queries, expected))
            print(f"{mode}: p95 retrieval={stages['retrieval']['summary']['p95_ms']:.3f} ms; "
                  f"gate={'PASS' if passed else 'FAIL'}", flush=True)
    assert_evidence(pins)
    source_paths = ('scripts/benchmark_bayesian_retriever.py', 'core/bayesian_retriever.py', 'core/bayesian_memory.py',
                    'core/backtest_engine.py', 'core/execution_prices.py', 'scripts/verify_bayesian_prior.py')
    return {'format_version': 1, 'status': 'PASS' if all(r['gate_passed'] for r in results.values()) else 'FAIL',
            'measured_at_utc': datetime.now(timezone.utc).isoformat(), 'bank_sha256': file_hash(bank),
            'run_signature': smoke['run_signature'], 'real_bank_records': len(records), 'versions': VERSIONS,
            'environment': {'python': sys.version, 'executable': sys.executable, 'os': platform.platform(),
                            'cpu': platform.processor(), 'logical_cpu_count': os.cpu_count(), 'gc_enabled': gc.isenabled(),
                            'dependencies': {name: version(name) for name in ('numpy', 'pandas', 'scipy', 'hmmlearn')}},
            'method': {'clock': 'perf_counter_ns', 'percentile': 'nearest_rank_ceil_0.95_n', 'sequential': True,
                       'warmup_per_mode_per_stage': warmup, 'samples_per_mode_per_stage': samples,
                       'context_count': len(contexts), 'queries_per_mode': 32, 'query_rotation': 'sample_index % 32; reset after warmup',
                       'mode_order': sorted(MODES), 'stage_order': ['retrieval', 'formatter', 'retrieval_and_format'],
                       'k': 3, 'seed': 42, 'scopes': sorted(SCOPES), 'retrieval_gate_p95_ns_strictly_below': THRESHOLD_NS,
                       'cache': 'Không cache kết quả query/ranking; kho và snapshot xác minh nạp một lần.',
                       'validation': 'API công khai đầy đủ; oracle/đối chiếu smoke ngoài timer; không loại mẫu ngoại lai.',
                       'cold_includes': 'Constructor: I/O kho/QA/manifest, kiểm schema/giá/P&L và snapshot; import/preflight ở ngoài.',
                       'formatter_input': 'Kết quả thực đã xác minh, không tính retrieval vào formatter riêng.'},
            'cold_load_ms': cold_ns / 1e6, 'contexts': [{k: c[k] for k in ('query', 'source')} for c in contexts],
            'queries': query_receipts, 'modes': results, 'protected_file_sha256': pins,
            'source_sha256': {relative: file_hash(ROOT / relative) for relative in source_paths},
            'checks': {'historical_context_evidence_unchanged': True, 'reference_ranking_stats_prefix_equal': True,
                       'every_measured_result_equal': True, 'query_inputs_unchanged': True,
                       'formatter_inputs_unchanged': True, 'hot_io_blocked': True},
            'limitations': ['Thời gian phụ thuộc máy và tải nền; chạy lại tuần tự khi đổi môi trường.',
                            'Cần archive local đã đóng băng của W3-12; script từ chối nếu thiếu hoặc khác hash.',
                            '852 episode 2020–2022, sentiment NEUTRAL thiếu tin; không là kết quả giao dịch OOS.',
                            'W4 còn phải áp dụng cap và guard prompt cuối <6500 theo receipt W3-11.'],
            'runtime_integration': False, 'oos_trading_backtest': False}


def main() -> None:
    """Ghi cả receipt FAIL để giữ bằng chứng nếu vượt gate."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--warmup', type=int, default=100)
    parser.add_argument('--samples', type=int, default=1000)
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/week3/retrieval_benchmark.json')
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / 'docs/week3').resolve()) or output.suffix != '.json' or output.exists():
        parser.error('Receipt mới phải nằm trong docs/week3, đuôi .json và chưa tồn tại; không ghi đè bằng chứng')
    result = benchmark(warmup=args.warmup, samples=args.samples)
    atomic_write_json(output, result)
    print(f"Đã lưu receipt {output.relative_to(ROOT)}: {result['status']}", flush=True)
    if result['status'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
