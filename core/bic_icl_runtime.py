"""Cohort revision dùng upstream một lần, khóa context trước Decision, resume durable."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from core.bic_icl_decisions import DecisionBlock, DEVELOPMENT, branch_order, shared_stage_scope, _namespace
from core.bic_icl_protocol import CohortSources, ExecutionAuthorization, namespace_path, repeat_sample
from core.bic_icl_reports import build_report, project
from core.historical_signals import digest, native_json
from core.prior_config import copy_prior_json
from core.prior_context import REPORT_FIELDS
from core.prior_run_lock import PriorRunLock
from core.research_cohort import read_envelope
from core.research_input_lock import _write_once
from scripts.prepare_bic_icl_context import summarize_coverage


def context_lock(plan: dict[str, Any], packets: list[dict[str, Any]]) -> dict[str, Any]:
    """Khóa ma trận toàn cohort và repeat chỉ từ metadata, không action/return query."""
    if [p['point_id'] for p in packets] != [r['point_id'] for r in plan['schedule']]:
        raise ValueError('Context lock cần đủ lịch theo đúng thứ tự đã khóa')
    enabled = all(p['task_technical_available'] for p in packets)
    matrix = [name for name in DEVELOPMENT if enabled or not name.startswith('R_task_')]
    coverage = summarize_coverage(packets)
    return copy_prior_json({'lock_version': 'bic_icl_context_lock_v1', 'plan_sha256': digest(plan),
        'packet_sha256': {p['point_id']: digest(p) for p in packets}, 'task_enabled': enabled, 'matrix': matrix,
        'repeat_sample': repeat_sample(packets), 'coverage': coverage,
        'task_coverage_eligible': sum(r['at_least_two_tasks'] for r in coverage.values()) >= 6
            and all(r['at_least_two_tasks'] >= 1 for r in coverage.values()),
        'confirmation_allowed': False})


def requests_for(packet: dict[str, Any], lock: dict[str, Any], index: int, repeat_id: int) -> list[dict[str, Any]]:
    """Original đầu, rotation chính xác; duplicate có request giống nhưng invocation riêng."""
    by_name = deepcopy(packet['requests'])
    by_name['original_duplicate'] = {**by_name['original'], 'branch_id': 'original_duplicate'}
    names = branch_order('development', index, repeat_id, task_enabled=lock['task_enabled'])
    return [by_name[n] for n in names]


def fresh_shared(sources: CohortSources, row: dict[str, str], root: Path, signature: str,
                 builder: Any, *, fixture: bool, verify_only: bool) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    """Journal ba node upstream và Full riêng; chỉ chạy sau release development."""
    point = sources.adapter.prepare(row['symbol'], row['as_of_date'])
    path = root/'shared'/f"{row['point_id']}.json"
    with shared_stage_scope(root, signature, row['point_id'], digest(point.source_provenance),
                            create=not verify_only, fixture=fixture) as journal:
        if path.exists():
            bundle = read_envelope(path)
            shared = point.restore_full_bundle(bundle)
            if list(journal.document['nodes']) != ['indicator', 'pattern', 'trend', 'full']:
                raise ValueError('Shared fresh thiếu bốn stage durable')
            for name, stage in journal.document['nodes'].items():
                if stage['attempts'][-1]['status'] != 'complete':
                    raise ValueError('Shared fresh chứa upstream chưa complete')
                output = stage['attempts'][-1]['output']
                fields = REPORT_FIELDS[3:] if name == 'full' else (name+'_report',)
                if any(output[field] != bundle['reports'][field] for field in fields):
                    raise ValueError('Shared fresh khác journal output')
            if journal.document['nodes']['full']['attempts'][-1]['output']['sentiment_data'] != bundle['sentiment_data']:
                raise ValueError('Shared fresh khác sentiment journal')
            return point, shared, bundle
        if verify_only or builder is None:
            raise ValueError('Upstream fresh chưa complete; không được chạy Decision')
        from utils import static_util
        initial = point.agent_state()
        initial['pattern_image'] = static_util.generate_kline_image(deepcopy(initial['kline_data']), write_artifacts=False).get('pattern_image')
        initial['trend_image'] = static_util.generate_trend_image(deepcopy(initial['kline_data']), write_artifacts=False).get('trend_image')
        if any(type(initial[k]) is not str or not initial[k] for k in ('pattern_image', 'trend_image')):
            raise ValueError('Upstream fresh thiếu ảnh PIT')
        upstream = builder.compile_upstream(stage_checkpoint=journal.invoke).invoke(deepcopy(initial))
        expected = point.agent_state()
        for key in ('stock_name', 'as_of_date', 'time_frame', 'is_backtest', 'language', 'window_end_date',
                    'alpha_norm_method', 'alpha_weights', 'kline_data'):
            if digest(upstream.get(key)) != digest(expected[key]):
                raise ValueError('Upstream thay input PIT')
        if not upstream['point_in_time_df'].equals(expected['point_in_time_df']):
            raise ValueError('Upstream thay snapshot giá')
        upstream['sentiment_store'] = expected['sentiment_store']
        full = builder.compile_full_preparation(strict_research_mode=True, stage_checkpoint=journal.invoke).invoke(deepcopy(upstream))
        shared = point.bind_full(full)
        bundle = {**{k: shared[k] for k in ('current_signals', 'market_regime', 'prior_provenance')},
            'reports': {k: shared[k] for k in REPORT_FIELDS}, 'alpha_factors': native_json(full['sentiment_data']['alpha_results']),
            'sentiment_data': native_json(full['sentiment_data'])}
        _write_once(path, bundle)
        return point, shared, bundle


def _initialize_blocks(blocks: list[tuple[DecisionBlock, dict[str, Any], list[dict[str, Any]]]],
                       ready: Path, signature: str) -> None:
    """Khởi tạo toàn slot trước HTTP; mất file sau ready không được tạo lại/replay."""
    expected = {'run_signature': signature, 'blocks': [str(b.directory.relative_to(b.root)) for b, _, _ in blocks]}
    if ready.exists():
        if read_envelope(ready) != expected:
            raise ValueError('Ready cohort khác ma trận/slot đã khóa')
        return
    for block, shared, requests in blocks:
        if block.path.exists():
            previous = read_envelope(block.path)
            if any(b['status'] != 'planned' for b in previous['branches'].values()):
                raise ValueError('Thiếu ready sau khi Decision đã bắt đầu')
        binding = block._binding(shared, requests)
        _write_once(block.directory/'identity.json', binding)
        _write_once(block.path, {'binding': binding,
            'branches': {r['branch_id']: block._empty() for r in binding['requests']}})
        _write_once(block.directory/'ready.json', {'binding_sha256': digest(binding)})
    _write_once(ready, expected)


def _audit_caches(blocks: list[tuple[DecisionBlock, dict[str, Any], list[dict[str, Any]]]]) -> tuple[dict[str, Any], set[str]]:
    """Kiểm cache durable toàn snapshot trước API tiếp theo; chỉ hash HTTP thật."""
    path = blocks[0][0].pacer.path
    ledger = json.loads(path.read_text('utf8')) if path.exists() else {'requests': []}
    physical_ids = set()
    for block, _, _ in blocks:
        doc = read_envelope(block.path)
        for request in doc['binding']['requests']:
            branch = doc['branches'][request['branch_id']]
            if branch['status'] == 'complete' and branch['attempts']:
                attempt_id = branch['attempts'][0]['attempt_id']
                physical_ids.add(attempt_id)
                block._pending_cache(ledger, request['branch_id'], attempt_id, request)
    return ledger, physical_ids


def run_cohort(plan: dict[str, Any], sources: CohortSources, root: Path, llm: Any, *,
               builder: Any = None, resume: bool = False, verify_only: bool = False,
               fixture: bool = False, repeat_id: int = 0, authorization: ExecutionAuthorization | None = None,
               upstream_only: bool = False) -> dict[str, Any]:
    """Cùng run chứa primary/repeat nhưng report riêng; verifier không gọi mạng."""
    if type(repeat_id) is not int or repeat_id not in (0, 1, 2, 3):
        raise ValueError('Repeat ID phải là 0/1/2/3')
    if any(type(value) is not bool for value in (resume, verify_only, fixture, upstream_only)):
        raise ValueError('Cờ runtime phải là bool Python gốc')
    root = _namespace(root, fixture)
    if not fixture:
        root = namespace_path(root, 'run')
    sources.validate(plan)
    if not fixture and not verify_only:
        if (not isinstance(authorization, ExecutionAuthorization)
                or authorization.payload['plan_sha256'] != digest(plan)):
            raise ValueError('Runtime chưa có authorization đã kiểm; dừng trước upstream/Decision')
        authorization.verify(plan, run_root=root, ledger_path=llm.http_client._transport.pacer.path)
    from core.improvement_transport import validate_client
    validate_client(llm, 'agent', plan.get('inputs', {}).get('signal_config', {}).get('models',
        {'agent_llm_model': 'openai/gpt-oss-20b', 'agent_llm_temperature': 0., 'agent_llm_max_tokens': 2048}), online=True)
    if plan['upstream_policy'] == 'FRESH_SHARED' and builder is not None:
        validate_client(builder.graph_llm, 'graph', plan['inputs']['signal_config']['models'], online=True)
    def verify() -> None:
        sources.validate(plan)
        if not fixture and not verify_only:
            authorization.verify(plan)
    identity = {'identity_version': 'bic_icl_run_identity_v1', 'plan': plan,
        'ledger_path': str(llm.http_client._transport.pacer.path.resolve()), 'fixture': fixture}
    signature = digest(identity)
    with PriorRunLock(root, signature):
        manifest = root/'cohort.json'
        if manifest.exists():
            if read_envelope(manifest) != identity or not (resume or verify_only or repeat_id):
                raise ValueError('Run khác identity hoặc thiếu resume')
        else:
            if resume or verify_only or repeat_id or any(p.name not in ('run.lock', 'run.owner.json') for p in root.iterdir()):
                raise ValueError('Run mới cần thư mục trống; không resume run mất manifest')
            _write_once(manifest, identity)
        locked = (root/'context_lock.json').exists()
        packets, shared_rows = [], {}
        for row in plan['schedule']:
            verify()
            point, shared, bundle = (sources.cached(row) if plan['upstream_policy'] == 'VERIFIED_CACHE' else
                fresh_shared(sources, row, root, signature, builder, fixture=fixture, verify_only=verify_only or locked))
            packet = sources.packet(row, point, shared, bundle)
            path = root/'packets'/f"{row['point_id']}.json"
            if locked or verify_only:
                if read_envelope(path) != packet:
                    raise ValueError('Packet khác source/PIT/evidence/request đã dựng lại')
            else:
                _write_once(path, packet)
            packets.append(packet)
            shared_rows[row['point_id']] = bundle
        lock = context_lock(plan, packets)
        verify()
        if locked or verify_only:
            if read_envelope(root/'context_lock.json') != lock:
                raise ValueError('Context/repeat/matrix khác lock trước Decision')
        else:
            _write_once(root/'context_lock.json', lock)
        if upstream_only:
            return {'status': 'UPSTREAM_LOCKED', 'context_lock': lock, 'decision_calls': 0}
        if not fixture and not verify_only and authorization.payload['decision_context_lock_sha256'] != digest(lock):
            raise ValueError('Cần release khóa đúng context/request/repeat sau upstream; chưa gọi Decision')
        # Kiểm toàn primary trước mọi HTTP repeat; không nhập lượt lặp vào primary.
        primary_blocks = []
        for j, packet in enumerate(packets):
            block = DecisionBlock(root, signature, packet['point_id'], 0, llm, language=plan['language'], fixture=fixture)
            primary_blocks.append((block, shared_rows[packet['point_id']], requests_for(packet, lock, j, 0)))
        if (root/'primary_ready.json').exists() or not verify_only and not repeat_id:
            _initialize_blocks(primary_blocks, root/'primary_ready.json', signature)
        elif not (root/'primary_ready.json').exists():
            raise ValueError('Thiếu primary ready; không khởi tạo lại')
        snapshot = [b.run(s, r, verify_sources=verify, verify_only=True) for b, s, r in primary_blocks]
        _audit_caches(primary_blocks)
        if repeat_id:
            if any(item['status'] != 'complete' for doc in snapshot for item in doc['branches'].values()):
                raise ValueError('Repeat cần primary complete đã verify toàn cohort')
            chosen = {r['point_id'] for r in lock['repeat_sample']}
            selected = [p for p in packets if p['point_id'] in chosen]
            blocks = [(DecisionBlock(root, signature, p['point_id'], repeat_id, llm, language=plan['language'], fixture=fixture),
                shared_rows[p['point_id']], requests_for(p, lock, j, repeat_id)) for j, p in enumerate(selected)]
            if (root/f'repeat_{repeat_id}_ready.json').exists() or not verify_only:
                _initialize_blocks(blocks, root/f'repeat_{repeat_id}_ready.json', signature)
            elif not (root/f'repeat_{repeat_id}_ready.json').exists():
                raise ValueError('Repeat chưa được khởi tạo đầy đủ')
            snapshot = [b.run(s, r, verify_sources=verify, verify_only=True) for b, s, r in blocks]
            _audit_caches(blocks)
        else:
            blocks, selected = primary_blocks, packets
        stopped = False
        for document in snapshot:
            statuses = [branch['status'] for branch in document['branches'].values()]
            if stopped and any(status != 'planned' for status in statuses):
                raise ValueError('Point sau đã chạy trước point trước durable')
            stopped = stopped or any(status != 'complete' for status in statuses)
        if not verify_only:
            snapshot = [b.run(s, r, verify_sources=verify) for b, s, r in blocks]
        rows = [project(p, doc, sources.adapter, repeat_id=repeat_id, language=plan['language'])
                for p, doc in zip(selected, snapshot)]
        verify()
        paths = {root/'cohort.json', root/'context_lock.json', root/'primary_ready.json'}
        paths.update((root/'packets').glob('*.json'))
        for directory in ('shared', 'shared_stages'):
            paths.update(p for p in (root/directory).rglob('*.json') if p.name not in ('run.owner.json', 'run.recovery.json'))
        if repeat_id:
            paths.add(root/f'repeat_{repeat_id}_ready.json')
        ledger, physical_ids = _audit_caches([*primary_blocks, *blocks])
        for block, _, _ in [*primary_blocks, *blocks]:
            paths.update((block.path, block.directory/'identity.json', block.directory/'ready.json'))
        binding = {'run_signature': signature, 'plan_sha256': digest(plan), 'context_lock_sha256': digest(lock),
            'code_sha256': plan['code_sha256'], 'runtime': plan['runtime'],
            'checkpoint_sha256': {p.relative_to(root).as_posix(): hashlib_sha(p) for p in sorted(paths)},
            'http_record_sha256': {row['id']: digest(row) for row in ledger['requests']
                if row.get('checkpoint_attempt_id') in physical_ids}}
        return build_report(plan, lock, rows, binding, repeat_id=repeat_id)


def hashlib_sha(path: Path) -> str:
    """Hash byte cho checkpoint, giữ LF normalization riêng ở identity code."""
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()
