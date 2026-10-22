"""Phát hành development cache sau kiểm nguồn, khóa request/repeat và bốn gate."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from core.bic_icl_decisions import DecisionBlock
from core.bic_icl_protocol import CohortSources, ROOT, code_identity, namespace_path
from core.bic_icl_runtime import context_lock, hashlib_sha, requests_for
from core.candidate_selection import read_technical_gates
from core.historical_signals import digest
from core.improvement_transport import expected_contract, validate_client
from core.prior_run_lock import PriorRunLock, safe_path
from core.research_cohort import read_envelope
from core.research_input_lock import _write_once, runtime_identity

RELEASE_ROOT = ROOT/'docs/plan/week11'
LEDGER = ROOT/'outputs/oos_pilot/api_usage.json'
VERSION = 'bic_icl_development_release_v1'
KEYS = {'release_version', 'plan_sha256', 'technical_gates_sha256', 'upstream_policy',
    'code_sha256', 'runtime', 'decision_context_lock_sha256', 'confirmation_allowed',
    'run_binding', 'request_manifest_sha256', 'snapshot_sha256'}


def request_manifest(plan: dict[str, Any], packets: list[dict[str, Any]],
                     lock: dict[str, Any], llm: Any) -> dict[str, Any]:
    """Khóa body SDK, thứ tự và alias của mọi slot; duplicate luôn độc lập."""
    validate_client(llm, 'agent', plan['inputs']['signal_config']['models'])
    contracts: dict[str, dict[str, Any]] = {}
    blocks = []
    sample = {row['point_id'] for row in lock['repeat_sample']}
    for repeat_id in (0, 1, 2, 3):
        selected = packets if not repeat_id else [p for p in packets if p['point_id'] in sample]
        for index, packet in enumerate(selected):
            requests = requests_for(packet, lock, index, repeat_id)
            records, slots = [], []
            for request in requests:
                prompt = request['prompt']
                if not prompt or len(prompt) >= 6500 or len(request['prefix']) > 600:
                    raise ValueError('Request release vượt budget hoặc thiếu prompt')
                if prompt not in contracts:
                    contracts[prompt] = expected_contract(llm, prompt)
                record = {**request, 'contract': contracts[prompt]}
                records.append(record)
                source = DecisionBlock._source(records, len(records)-1)
                slots.append({'branch_id': request['branch_id'], 'request_sha256': digest(request),
                    'contract': record['contract'], 'source_branch': source[0] if source else None,
                    'decision_origin': source[1] if source else
                        ('independent_duplicate' if request['branch_id'] == 'original_duplicate' else 'independent')})
            blocks.append({'repeat_id': repeat_id, 'point_id': packet['point_id'],
                'point_index': index, 'requests': slots})
    return {'manifest_version': 'bic_icl_development_requests_v1', 'plan_sha256': digest(plan),
        'context_lock_sha256': digest(lock), 'blocks': blocks,
        'logical_slots': sum(len(b['requests']) for b in blocks),
        'independent_slots': sum(r['source_branch'] is None for b in blocks for r in b['requests']),
        'decision_calls': 0, 'confirmation_allowed': False}


def _population(plan: dict[str, Any], sources: CohortSources) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """Dựng lại 60 upstream/evidence từ nguồn PIT; không đọc action hoặc evaluation."""
    sources.validate(plan)
    if (plan['split'] != 'development_2023' or plan['upstream_policy'] != 'VERIFIED_CACHE'
            or len(plan['schedule']) != 60 or plan['confirmation_allowed'] is not False):
        raise ValueError('Producer này chỉ phát hành toàn cohort development 60 điểm VERIFIED_CACHE')
    packets = [sources.packet(row, *sources.cached(row)) for row in plan['schedule']]
    lock = context_lock(plan, packets)
    if len(lock['repeat_sample']) != 12:
        raise ValueError('Release cần mẫu repeat đủ 12 điểm trước Decision')
    from scripts.run_bayesian_ablation import make_builder
    def reject(request: httpx.Request) -> httpx.Response:
        raise AssertionError('Producer/verifier release không được gọi mạng')
    with httpx.Client(transport=httpx.MockTransport(reject)) as client:
        builder = make_builder(plan['inputs'], 'offline-release-no-credential', client)
        manifest = request_manifest(plan, packets, lock, builder.agent_llm)
    sources.validate(plan)
    return packets, lock, manifest


def _identity(plan: dict[str, Any], ledger: Path) -> dict[str, Any]:
    """Cùng identity runtime, khóa ledger path nhưng không đóng băng ledger đang tăng."""
    return {'identity_version': 'bic_icl_run_identity_v1', 'plan': plan,
        'ledger_path': str(ledger.resolve()), 'fixture': False}


def _artifacts(plan: dict[str, Any]) -> set[str]:
    """Danh mục snapshot bắt buộc, không nhận danh sách hash tự khai thiếu packet."""
    return {'cohort.json', 'context_lock.json', 'request_manifest.json',
        *(f"packets/{row['point_id']}.json" for row in plan['schedule'])}


def _assert_not_started(ledger: Path, signature: str) -> None:
    """Ledger còn intent/HTTP thì không tái tạo run dù mọi checkpoint đã bị mất."""
    if not ledger.exists():
        return
    try:
        document = json.loads(ledger.read_text('utf8'))
    except (ValueError, UnicodeError) as error:
        raise ValueError('Ledger provider không đọc được; chưa phát hành') from error
    if (type(document) is not dict or type(document.get('requests')) is not list
            or any(type(row) is not dict for row in document['requests'])):
        raise ValueError('Ledger provider thiếu danh sách request hợp lệ')
    if any(row.get('run_signature') == signature for row in document['requests']):
        raise ValueError('Ledger đã có intent/HTTP của cohort; không tạo lại release/checkpoint')


def verify_snapshot(payload: dict[str, Any], plan: dict[str, Any], *,
                    run_root: Path | None = None, ledger_path: Path | None = None) -> Path:
    """Consumer kiểm file thực trước key/HTTP; tự băm lại JSON không thay nguồn semantic."""
    if (type(payload) is not dict or set(payload) != KEYS or payload['release_version'] != VERSION
            or payload['plan_sha256'] != digest(plan) or payload['upstream_policy'] != 'VERIFIED_CACHE'
            or plan['upstream_policy'] != 'VERIFIED_CACHE' or plan['split'] != 'development_2023'
            or payload['confirmation_allowed'] is not False or plan['confirmation_allowed'] is not False
            or payload['code_sha256'] != plan['code_sha256'] or payload['runtime'] != plan['runtime']
            or plan['code_sha256'] != code_identity() or plan['runtime'] != runtime_identity()):
        raise ValueError('Release khác plan/code/runtime/policy development đã khóa')
    binding = payload['run_binding']
    if (type(binding) is not dict or set(binding) != {'run_root', 'ledger_path', 'run_signature'}
            or any(type(v) is not str or not v for v in binding.values())):
        raise ValueError('Release thiếu binding run/ledger/signature')
    root = namespace_path(Path(binding['run_root']), 'run')
    ledger = Path(binding['ledger_path']).resolve()
    identity = _identity(plan, ledger)
    if (str(root) != binding['run_root'] or ledger != LEDGER.resolve()
            or str(ledger) != binding['ledger_path'] or binding['run_signature'] != digest(identity)
            or run_root is not None and run_root.resolve() != root
            or ledger_path is not None and ledger_path.resolve() != ledger):
        raise ValueError('Release khác run root hoặc ledger provider chung')
    snapshot = payload['snapshot_sha256']
    if type(snapshot) is not dict or set(snapshot) != _artifacts(plan):
        raise ValueError('Release thiếu snapshot cohort/packet/context/request')
    if any(not safe_path(root, name).is_file() or hashlib_sha(safe_path(root, name)) != checksum
           for name, checksum in snapshot.items()):
        raise ValueError('Snapshot release đã thay byte hoặc mất artifact')
    if read_envelope(root/'cohort.json') != identity:
        raise ValueError('Run identity khác plan/ledger đã phát hành')
    lock = read_envelope(root/'context_lock.json')
    manifest = read_envelope(root/'request_manifest.json')
    if (digest(lock) != payload['decision_context_lock_sha256']
            or digest(manifest) != payload['request_manifest_sha256']
            or manifest['context_lock_sha256'] != digest(lock) or manifest['plan_sha256'] != digest(plan)):
        raise ValueError('Release không bind đúng context/request/repeat')
    return root


def verify_development_release(path: Path, gates_path: Path, plan: dict[str, Any], *,
                               sources: CohortSources | None = None,
                               run_root: Path | None = None, ledger_path: Path | None = None) -> dict[str, Any]:
    """Dựng lại nguồn và body SDK, đối chiếu release; chỉ đọc, không key/env/HTTP."""
    gates = read_technical_gates(gates_path, plan)
    if path.name.startswith('.env'):
        raise ValueError('Release không được trỏ tới credential')
    payload = read_envelope(path)
    root = verify_snapshot(payload, plan, run_root=run_root, ledger_path=ledger_path)
    if gates['status'] != 'PASS' or gates['sha256'] != payload['technical_gates_sha256']:
        raise ValueError('Release chưa có bốn gate PASS đúng receipt')
    packets, lock, manifest = _population(plan, sources if sources is not None else CohortSources())
    if (read_envelope(root/'context_lock.json') != lock
            or read_envelope(root/'request_manifest.json') != manifest
            or any(read_envelope(root/'packets'/f"{p['point_id']}.json") != p for p in packets)):
        raise ValueError('Snapshot khác upstream/PIT/evidence/request/repeat tái dựng')
    verify_snapshot(payload, plan, run_root=run_root, ledger_path=ledger_path)
    return payload


def issue_development_release(path: Path, gates_path: Path, plan: dict[str, Any], sources: CohortSources,
                              run_root: Path, *, ledger_path: Path = LEDGER) -> dict[str, Any]:
    """Ghi một lần sau gate/nguồn PASS; release có sẵn chỉ verify, không sửa snapshot."""
    path, root, ledger = path.resolve(), namespace_path(run_root, 'run'), ledger_path.resolve()
    if (path.parent != RELEASE_ROOT.resolve() or not path.name.startswith('development_')
            or path.suffix != '.json' or ledger != LEDGER.resolve()):
        raise ValueError('Release cần đường riêng development_*.json ở W11 và ledger chung')
    if path.exists():
        return verify_development_release(path, gates_path, plan, sources=sources,
            run_root=root, ledger_path=ledger)
    sources.validate(plan)
    gates = read_technical_gates(gates_path, plan)
    if gates['status'] != 'PASS':
        raise ValueError('Chưa đủ bốn gate PASS; không tạo run/release')
    identity = _identity(plan, ledger)
    _assert_not_started(ledger, digest(identity))
    packets, lock, manifest = _population(plan, sources)
    with PriorRunLock(root, digest(identity)):
        _assert_not_started(ledger, digest(identity))
        allowed = _artifacts(plan) | {'run.lock', 'run.owner.json', 'run.recovery.json'}
        actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
        if actual-allowed:
            raise ValueError('Không phát hành sau khi đã có Decision/report/cache hoặc artifact lạ')
        # Kiểm mọi file đã có trước khi ghi, tránh sửa một run dở đang sai identity.
        expected = {'cohort.json': identity, 'context_lock.json': lock, 'request_manifest.json': manifest,
            **{f"packets/{p['point_id']}.json": p for p in packets}}
        for name, value in expected.items():
            target = safe_path(root, name)
            if target.exists() and read_envelope(target) != value:
                raise ValueError('Snapshot đã có khác nguồn; không ghi đè hoặc tự băm lại')
        for name, value in expected.items():
            _write_once(safe_path(root, name), value)
        payload = {'release_version': VERSION, 'plan_sha256': digest(plan),
            'technical_gates_sha256': gates['sha256'], 'upstream_policy': plan['upstream_policy'],
            'code_sha256': plan['code_sha256'], 'runtime': plan['runtime'],
            'decision_context_lock_sha256': digest(lock), 'confirmation_allowed': False,
            'run_binding': {'run_root': str(root), 'ledger_path': str(ledger), 'run_signature': digest(identity)},
            'request_manifest_sha256': digest(manifest),
            'snapshot_sha256': {name: hashlib_sha(safe_path(root, name)) for name in sorted(expected)}}
        sources.validate(plan)
        if read_technical_gates(gates_path, plan) != gates:
            raise ValueError('Receipt gate đã đổi trong khi đóng băng')
        _assert_not_started(ledger, digest(identity))
        verify_snapshot(payload, plan, run_root=root, ledger_path=ledger)
        _write_once(path, payload)
    return payload
