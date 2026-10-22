"""Memory revision từ upstream đã đóng băng; không đọc quyết định để sinh feature."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
from pathlib import Path
from typing import Any
import zipfile

import pandas as pd

from core.backtest_engine import compute_round_trip_net_return
from core.bayesian_memory import iso_date, is_bullish, read_json, validate_historical_task_record
from core.bayesian_retriever import BayesianPriorRetriever, normalize_signals
from core.execution_prices import execution_prices_for_cycle
from core.historical_signals import digest
from core.price_feature_index import PriceFeatureIndex, SCALER_VERSION, _VERIFIED
from core.prior_config import copy_prior_json
from core.prior_context import PriorContextAdapter, REPORT_FIELDS
from core.research_cohort import read_envelope

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'bic_icl_memory_v1'
INDEX_VERSION = 'bic_icl_price_index_v1'
ARCHIVE = 'outputs/bayesian_benchmark/improvement_v1/holdout/frozen_results_v1.zip'
ARCHIVE_SHA = '1db2024a3a338cadcf72692287471f8a14feba49ce8a1b1a488b951896cfec70'
METHOD = 'docs/plan/week10/method_protocol_v1.md'
METHOD_SHA = 'e9c8410bed048733d1ad3faa296a200409c91bfd8be72557d98639ecd8e8313b'
PREFIX = 'outputs/bayesian_benchmark/improvement_v1'
_BUILT = object()


def sha(path: Path) -> str:
    """Băm byte nguồn; chỉ mã/phương pháp dùng chuẩn hóa LF riêng."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_method(root: Path = ROOT) -> None:
    """Không nhận sửa ngữ nghĩa protocol dưới cùng version."""
    if hashlib.sha256((root/METHOD).read_text('utf-8').encode()).hexdigest() != METHOD_SHA:
        raise ValueError('Protocol phương pháp khác bản đã khóa')


class FrozenSources:
    """Chỉ nhận file trùng byte entry trong archive W9 có checksum đã khóa."""

    def __init__(self, root: Path = ROOT) -> None:
        self.root = root.resolve()
        verify_method(self.root)
        if sha(self.root/ARCHIVE) != ARCHIVE_SHA:
            raise ValueError('Archive W9 khác nguồn đã khóa')
        self.hashes = {ARCHIVE: ARCHIVE_SHA}

    def envelope(self, relative: str, *, journal: bool = False) -> dict[str, Any]:
        """Pin file trước đọc; checksum tự khai không thay byte nguồn độc lập."""
        target = (self.root/relative).resolve()
        if not target.is_relative_to(self.root) or target.name.startswith('.env'):
            raise ValueError('Nguồn nằm ngoài workspace hoặc trỏ credential')
        with zipfile.ZipFile(self.root/ARCHIVE) as archive:
            try:
                expected = archive.read(relative)
            except KeyError as exc:
                raise ValueError('Nguồn không nằm trong archive đã khóa') from exc
        if target.read_bytes() != expected:
            raise ValueError(f'Nguồn đã thay đổi: {relative}')
        self.hashes[relative] = sha(target)
        if journal:
            envelope = copy_prior_json(read_json(target))
            if set(envelope) != {'payload', 'sha256'} or digest(envelope['payload']) != envelope['sha256']:
                raise ValueError('Envelope journal không hợp lệ')
            return envelope['payload']
        return read_envelope(target)

    def verify(self) -> None:
        """Kiểm lại mọi byte đã dùng, kể cả archive; không tạo artifact nguồn."""
        verify_method(self.root)
        if any(sha(self.root/name) != value for name, value in self.hashes.items()):
            raise ValueError('Nguồn memory thay đổi trong lúc xử lý')


def oos_adapter(plan: dict[str, Any], root: Path = ROOT) -> PriorContextAdapter:
    """Dựng adapter read-only với đúng model/config và snapshot nguồn lịch sử."""
    inputs = plan['inputs']
    return PriorContextAdapter({'enable_bayesian_prior': True}, root=root,
        execution_dir=inputs['execution_dir'], news_dir=inputs['news_dir'],
        provider_mode='fixed_train_oos', frozen_artifact_path=inputs['model']['artifact_path'],
        freeze_as_of_date=inputs['model']['freeze_as_of_date'], signal_config=inputs['signal_config'])


def adapt_checkpoint(document: dict[str, Any], journal: dict[str, Any], *,
                     point: Any, signature: str, journal_sha256: str) -> dict[str, Any]:
    """Tái seal upstream với nguồn thật trước khi đọc giá để sinh nhãn LONG."""
    symbol, cutoff = point.source_provenance['context']['symbol'], point.source_provenance['context']['as_of_date']
    pid = f'{symbol}-{cutoff}'
    if (set(document) != {'point_version', 'run_signature', 'point_id', 'context', 'source_proof',
            'full_bundle', 'shared_sha256', 'journal_sha256'}
            or document['point_version'] != 'improvement_shared_point_v1'
            or document['run_signature'] != signature or document['point_id'] != pid
            or document['context'] != {'symbol': symbol, 'as_of_date': cutoff}
            or document['source_proof'] != point.source_provenance
            or not '2023-01-01' <= cutoff <= '2024-12-31'
            or document['journal_sha256'] != journal_sha256
            or document['shared_sha256'] != digest(document['full_bundle'])):
        raise ValueError('Checkpoint khác schema, source, cutoff hoặc journal')
    bundle = document['full_bundle']
    shared = point.restore_full_bundle(bundle)
    expected_binding = {'run_signature': signature, 'point_id': pid,
                        'source_sha256': digest(point.source_provenance)}
    if (set(journal) != {'version', 'binding', 'nodes'} or journal['version'] != 'agent_stage_journal_v1'
            or journal['binding'] != expected_binding
            or list(journal['nodes']) != ['indicator', 'pattern', 'trend', 'full']):
        raise ValueError('Journal upstream thiếu binding hoặc stage đã khóa')
    for name, node in journal['nodes'].items():
        attempts = node['attempts']
        if not attempts or attempts[-1]['status'] != 'complete':
            raise ValueError('Upstream thiếu output complete')
        output = attempts[-1]['output']
        fields = REPORT_FIELDS[3:] if name == 'full' else (name+'_report',)
        if any(output[key] != bundle['reports'][key] for key in fields):
            raise ValueError('Báo cáo khác output journal durable')
        if name == 'full' and output['sentiment_data'] != bundle['sentiment_data']:
            raise ValueError('Sentiment khác output journal durable')
    frame, events = point._adapter.execution_data(symbol)
    dates = pd.DatetimeIndex(frame.Datetime)
    position = dates.get_loc(pd.Timestamp(cutoff))
    entry_day, exit_day = (dates[position+i].strftime('%Y-%m-%d') for i in (1, 3))
    if exit_day > '2024-12-31':
        raise ValueError('Cycle memory vượt snapshot cuối 2024')
    entry, exit_close = execution_prices_for_cycle(frame, events, cutoff, entry_day, exit_day)
    net = float(compute_round_trip_net_return(entry, exit_close)*100)
    signals = normalize_signals(shared['current_signals'])
    record = {'episode_id': f'{symbol}:{cutoff}', 'symbol': symbol, 'as_of_date': cutoff,
        'entry_date': entry_day, 'exit_date': exit_day, 'regime': shared['market_regime']['regime_name'],
        'agent_signals': signals, 'outcome': {'actual_direction': 'UP' if net > 0 else 'DOWN',
            'net_return_pct': net, 'was_bull_trap': bool(net <= 0 and any(is_bullish(signals[k]) for k in ('trend', 'pattern'))),
            'result': 'WIN_IF_LONG' if net > 0 else 'LOSS_IF_LONG'}}
    validate_historical_task_record(record, frame, events)
    return copy_prior_json(record)


def union_records(original: list[dict[str, Any]], additions: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """Union xác định theo cycle và ID; record mâu thuẫn không được chọn tùy tiện."""
    records, cycles, ids, duplicates = [], {}, {}, []
    for record in copy_prior_json(original)+copy_prior_json(additions):
        key, cycle = record['episode_id'], (record['symbol'], record['as_of_date'])
        if record['exit_date'] > '2024-12-31':
            raise ValueError('Không append cycle 2025 vào bank revision')
        prior = ids.get(key) or cycles.get(cycle)
        if prior is not None:
            if prior != record:
                raise ValueError('Trùng ID/cycle nhưng khác tín hiệu, regime hoặc nhãn')
            duplicates.append(key)
            continue
        ids[key] = cycles[cycle] = record
        records.append(record)
    return sorted(records, key=lambda r: r['episode_id']), duplicates


class RevisionMemory:
    """Snapshot đã kiểm; trả bản sao, cắt exit trước query ở mọi lần retrieval."""

    def __init__(self, payload: dict[str, Any], *, verified: object) -> None:
        if verified is not _BUILT:
            raise ValueError('Memory revision chỉ được tạo bởi adapter nguồn')
        self._payload = copy_prior_json(payload)
        self.identity = digest(self._payload)

    @property
    def payload(self) -> dict[str, Any]:
        """Trả bản sao sở hữu của snapshot và provenance."""
        return deepcopy(self._payload)

    @property
    def records(self) -> list[dict[str, Any]]:
        """Không cho caller sửa record đã xác minh trong RAM."""
        return deepcopy(self._payload['records'])

    def eligible(self, as_of_date: str, symbol: str | None = None) -> list[dict[str, Any]]:
        """Chỉ cycle đã đóng; query tự nó và nguồn tương lai luôn bị loại trước rank."""
        cutoff = iso_date(as_of_date)
        return deepcopy([r for r in self._payload['records'] if r['exit_date'] < cutoff
                         and (symbol is None or r['symbol'] == symbol)])


def build_memory(sources: FrozenSources) -> tuple[RevisionMemory, PriorContextAdapter]:
    """Nhập tối đa 124 checkpoint đã khóa, không chọn theo outcome, không gọi API."""
    sources.envelope('outputs/bayesian_benchmark/price_features/candidate_index_v1.json')
    additions, trace, provenance = [], [], {}
    adapter = None
    for phase, count in (('development', 60), ('holdout', 64)):
        plan = sources.envelope(f'{PREFIX}/{phase}/plan.json')
        config = plan['inputs']['signal_config']
        if adapter is None:
            adapter = oos_adapter(plan, sources.root)
        if config != adapter.signal_config or plan['inputs']['client_options'] != {
                'agent': {'reasoning_effort': 'low', 'reasoning_format': 'hidden'},
                'graph': {'reasoning_effort': 'none', 'reasoning_format': 'hidden'}}:
            raise ValueError('Hai cohort không tương thích signal/model/options')
        cohort = sources.envelope(f'{PREFIX}/{phase}/run/cohort.json')
        if cohort['plan'] != plan or cohort['execution_mode'] != 'research':
            raise ValueError('Nguồn upstream không thuộc run API thật của plan đã khóa')
        signature = digest(cohort)
        schedule = sorted((s, d) for s, days in plan['symbol_cutoffs'].items() for d in days)
        if len(schedule) != count or len(set(schedule)) != count:
            raise ValueError('Nguồn memory khác 60/64 point đã khóa')
        for symbol, cutoff in schedule:
            pid = f'{symbol}-{cutoff}'
            path = f'{PREFIX}/{phase}/run/points/{pid}.json'
            journal_path = f'{PREFIX}/{phase}/run/responses/{pid}.json'
            document, journal = sources.envelope(path), sources.envelope(journal_path, journal=True)
            try:
                record = adapt_checkpoint(document, journal, point=adapter.prepare(symbol, cutoff),
                    signature=signature, journal_sha256=sources.hashes[journal_path])
            except (ValueError, KeyError, TypeError, IndexError) as exc:
                trace.append({'point_id': pid, 'status': 'EXCLUDED', 'reason': 'INCOMPATIBLE_UPSTREAM',
                              'detail': str(exc), 'source_path': path})
                continue
            additions.append(record)
            provenance[record['episode_id']] = {'point_path': path, 'point_sha256': sources.hashes[path],
                'journal_path': journal_path, 'journal_sha256': sources.hashes[journal_path],
                'source_proof_sha256': digest(document['source_proof']), 'shared_sha256': document['shared_sha256'],
                'signals': deepcopy(document['full_bundle']['prior_provenance']['signals'])}
            trace.append({'point_id': pid, 'status': 'IMPORTED', 'reason': None, 'source_path': path})
    original = adapter._retriever._memory.records
    if len(original) != 852:
        raise ValueError('Bank gốc khác 852 episode đã khóa')
    records, duplicates = union_records(original, additions)
    adapter.verify_sources()
    sources.verify()
    payload = {'memory_version': VERSION, 'snapshot_end': '2024-12-31', 'method_sha256': METHOD_SHA,
        'original_bank': deepcopy(adapter._bank), 'original_count': 852, 'scheduled_count': 124,
        'imported_count': len(additions), 'excluded_count': 124-len(additions), 'deduplicated_ids': duplicates,
        'status': 'AVAILABLE' if additions else 'BLOCKED', 'trace': trace, 'record_provenance': provenance,
        'by_year': dict(sorted(Counter(r['as_of_date'][:4] for r in records).items())),
        'source_hashes': {**sources.hashes, **adapter.source_hashes}, 'records': records}
    return RevisionMemory(payload, verified=_BUILT), adapter


class RevisionPriceIndex(PriceFeatureIndex):
    """Miền 2025 riêng; scaler gốc train-only không refit hoặc đổi validator legacy."""

    def scaler(self, symbol: str, as_of_date: str, *, fold_id: str | None = None) -> dict[str, Any]:
        """Chọn đúng fold revision và giữ nguyên mọi tham số fit của scaler cũ."""
        cutoff = iso_date(as_of_date)
        if type(symbol) is not str or symbol not in ('FPT', 'MWG', 'VCB', 'VNM'):
            raise ValueError('Mã scaler revision không hợp lệ')
        matches = [name for name, f in self._payload['folds'].items() if f['query_start'] <= cutoff <= f['query_end']]
        if len(matches) != 1 or fold_id is not None and fold_id != matches[0] or symbol not in self._payload['scalers'][matches[0]]:
            raise ValueError('Fold/mã revision sai cutoff hoặc ngoài miền đã khóa')
        name = matches[0]
        return {'fold_id': name, 'index_sha256': self.identity, 'scaler_version': SCALER_VERSION,
            'scaler_sha256': self._scaler_hashes[(name, symbol)], **deepcopy(self._payload['scalers'][name][symbol])}


def build_revision_index(memory: RevisionMemory, adapter: PriorContextAdapter,
                         legacy: PriceFeatureIndex) -> RevisionPriceIndex:
    """Nối feature PIT, kế thừa bốn scaler đúng train, không gọi fit trên nguồn mới."""
    if not isinstance(memory, RevisionMemory) or not isinstance(legacy, PriceFeatureIndex):
        raise ValueError('Index revision cần snapshot memory và index legacy đã kiểm')
    payload = legacy.payload
    if payload['provenance']['bank'] != adapter._price_feature_index_inputs()['provenance']['bank']:
        raise ValueError('Index legacy không thuộc bank nguồn của adapter')
    legacy.verify_query_sources(prices=adapter._prices, calendar=pd.DatetimeIndex(adapter._vnindex.Datetime),
        source=payload['source'], bank=payload['provenance']['bank'])
    rows = {r['episode_id']: r for r in payload['records']}
    for record in memory.records:
        if record['episode_id'] in rows:
            if any(record[k] != rows[record['episode_id']][k] for k in ('symbol', 'as_of_date', 'exit_date')):
                raise ValueError('Record gốc khác ID/ngày index')
        else:
            rows[record['episode_id']] = {k: record[k] for k in ('episode_id', 'symbol', 'as_of_date', 'exit_date')}
            rows[record['episode_id']]['features'] = adapter.price_features(record['symbol'], record['as_of_date'])
    if set(rows) != {r['episode_id'] for r in memory.records}:
        raise ValueError('Index revision thừa/thiếu ID memory')
    payload['index_version'] = INDEX_VERSION
    payload['legacy_index_sha256'] = legacy.identity
    payload['legacy_scalers_sha256'] = digest(payload['scalers'])
    payload['provenance']['bank'] = {'bank_sha256': memory.identity}
    payload['folds']['confirmation_2025'] = {**payload['folds']['oos_2023_2024'],
        'query_start': '2025-01-01', 'query_end': '2025-12-31'}
    payload['scalers']['confirmation_2025'] = deepcopy(payload['scalers']['oos_2023_2024'])
    payload['records'] = sorted(rows.values(), key=lambda r: r['episode_id'])
    payload['memory_sha256'] = memory.identity
    return RevisionPriceIndex(payload, _verified=_VERIFIED)


class RevisionRetriever(BayesianPriorRetriever):
    """Gắn cùng snapshot revision cho A/R/Numeric, tái dùng masks/selector legacy."""

    def __init__(self, memory: RevisionMemory) -> None:
        if not isinstance(memory, RevisionMemory) or memory.payload['status'] != 'AVAILABLE':
            raise ValueError('Memory revision chưa có nguồn tương thích')
        self._memory = memory
        self._verified_by_id = {r['episode_id']: r for r in memory.records}
        self._bank_sha256 = memory.identity
        self._price_index_identities: set[str] = set()

    def rank_price_candidates(self, **query: Any) -> dict[str, Any]:
        """Giữ ranking legacy; ghi đúng version index revision trong sidecar."""
        result = super().rank_price_candidates(**query)
        result['metadata']['index_version'] = INDEX_VERSION
        return result
