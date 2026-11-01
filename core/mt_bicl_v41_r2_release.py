"""Release lượt thay thế độc lập; bằng chứng cũ vẫn thiếu và không được reseal thành PASS."""

from __future__ import annotations

import importlib.metadata
from pathlib import Path
import platform
from typing import Any

from core.mt_bicl_v4_dataset import immutable
from core.mt_bicl_v4_protocol import canonical, checksum, git, read, verify_ledger
from core.mt_bicl_v41_r2_data import DATA, DOC, MANIFEST, NAMESPACE, PANEL, SOURCES as DATA_SOURCES, pinned
from core.mt_bicl_v41_r2_warmup import COLLECTION, RELEASE

OLD_RELEASE = DOC / 'collection_release_v4_1.json'
OLD_NAMESPACE = Path('outputs/bayesian_benchmark/mt_bicl_v4_1/collection')
SOURCES = (*DATA_SOURCES, '.gitattributes', 'core/panel_collection.py', 'core/panel_coordinator.py',
    'core/mt_bicl_v41_r2_warmup.py', 'core/mt_bicl_v41_r2_release.py',
    'core/mt_bicl_v41_r2_backup.py',
    'core/mt_bicl_v41_r2_acceptance.py', 'core/mt_bicl_v41_r2_contract.py',
    'scripts/continue_mt_bicl_v4_1_r2.py', 'scripts/prepare_mt_bicl_v4_1_r2.py',
    'tests/test_mt_bicl_v41_r2.py', 'tests/test_panel_coordinator.py')
PERMISSIONS = ('training_allowed', 'reference_fit_allowed', 'development_allowed', 'confirmation_allowed')


def historical_snapshot(root: Path, old: dict[str, Any], ledger: dict[str, Any]) -> dict[str, Any]:
    """Chỉ kiểm kê exposure/byte còn lại; không tính accuracy hoặc P&L."""
    sha = checksum((root / OLD_RELEASE).read_bytes())
    rows = [r for r in ledger['requests'] if r.get('operational_amendment_sha256') == sha]
    missing = {}
    for row in rows:
        path = OLD_NAMESPACE / 'http_cache' / (row['id'] + '.json')
        if row.get('durable_response') and not (root / path).is_file():
            missing[path.as_posix()] = row['durable_response']['sha256']
    return {'prior_release_sha256': sha, 'status': 'INCOMPLETE_LOST_EVIDENCE_NOT_ACCEPTED',
        'prior_requests': len(rows), 'prior_HTTP200': sum(r['status'] == 200 for r in rows),
        'prior_market_point_ids': sorted({r['point_id'] for r in rows if r['status'] == 200 and not r['point_id'].startswith('CONTROL_')}),
        'missing_sealed_raw_sha256': missing,
        'surviving_evidence_sha256': {p.relative_to(root).as_posix(): checksum(p.read_bytes())
            for p in sorted((root / OLD_NAMESPACE).rglob('*.json')) if p.name != 'run.owner.json'},
        'selection': 'RECOLLECT_ALL_REGISTERED_256_NO_RESPONSE_SELECTION_OR_REUSE',
        'historical_lineage': 'V3_AND_LEGACY_REPORT_PROOFS_REMAIN_INCOMPLETE_NOT_CERTIFIED_BY_R2',
        'old_responses_counted_as_new_results': False, 'exposure_reset': False}


def prepare(root: Path) -> dict[str, Any]:
    """Chỉ cấp collection≤2022 sau nguồn r2 đã commit và ngân hàng độc lập đã khóa."""
    if (root / RELEASE).exists():
        return verify(root)
    bank = pinned(root, MANIFEST.name)
    if bank['status'] != 'NUMERIC_BANK_PASS':
        raise ValueError('Ngân hàng r2 chưa PASS')
    old = pinned(root, OLD_RELEASE.name)
    spec = pinned(root, 'protocol_v4_1.json')
    acquisition = pinned(root, 'data_completion_release_v4.json')
    ledger = read((root / 'outputs/oos_pilot/api_usage.json').read_bytes())
    verify_ledger(ledger, old['ledger_baseline'])
    commit = git(root, 'rev-parse', 'HEAD').decode().strip()
    names = tuple(dict.fromkeys((*SOURCES, *old['dependency_sha256'], *old['source_sha256'])))
    sources, git_sources = {}, {}
    for name in names:
        raw = (root / name).read_bytes()
        blob = git(root, 'show', commit + ':' + name)
        if raw.replace(b'\r\n', b'\n') != blob.replace(b'\r\n', b'\n'):
            raise ValueError('Cần commit source trước release r2: ' + name)
        sources[name] = checksum(raw)
        git_sources[name] = checksum(blob)
    receipts = (OLD_RELEASE, MANIFEST, PANEL, DOC / 'protocol_v4_1.json', DOC / 'protocol_lock_v4_1.json', DOC / 'dataset_manifest_v4_1.json')
    panel = pinned(root, PANEL.name)
    result = {'version': 'conditional_v4_1_r2_collection_release', 'status': 'USER_COLLECTION_RELEASED',
        'authority': 'USER_2026_11_01_IMPLEMENT_REPLACEMENT_RUN_AND_CONTINUE_PLAN',
        'scope': 'PANEL256_ORIGINAL_UPSTREAM_ONLY_2019_2022', 'runtime_namespace': NAMESPACE.as_posix(),
        'source_commit': commit, 'source_sha256': sources, 'source_git_blob_sha256': git_sources,
        'receipt_sha256': {p.as_posix(): checksum((root / p).read_bytes()) for p in receipts},
        'numeric_artifact_sha256': bank['artifact_sha256'], 'input_sha256': bank['input_sha256'],
        'news_sha256': acquisition['news_sha256'], 'runtime': spec['runtime'],
        'acquisition_runtime': acquisition['acquisition_runtime'], 'config': old['config'], 'warmup': old['warmup'],
        'point_ids': panel['point_ids'], 'shards': panel['shards'], 'panel_sha256': checksum((root / PANEL).read_bytes()),
        'nominal_research_HTTP': 768, 'controls_per_scope': 3, 'credential_variables': old['credential_variables'],
        'scope_independence_authority': old['scope_independence_authority'],
        'collection_operator': 'USER_ONLY', 'writer': 'ONE_COORDINATOR_SHARED_LEDGER_LOCK',
        'backup_policy': 'MIRROR_OUTSIDE_PROJECT_AFTER_EVERY_RAW_AND_POINT_NO_CREDENTIALS',
        'hour_cap': None, 'calendar_deadline': None, 'daily_target_per_scope': 16,
        'resume': old['resume'], 'lost_unsealed_response': old['lost_unsealed_response'],
        'historical_evidence': historical_snapshot(root, old, ledger),
        'ledger_baseline': {'count': len(ledger['requests']), 'requests_prefix_sha256': checksum(canonical(ledger['requests']))},
        **{k: False for k in PERMISSIONS}}
    immutable(root / RELEASE, result)
    return result


def verify(root: Path) -> dict[str, Any]:
    """Verifier r2 độc lập: không gọi gate cha đã mất và không chứng nhận lại bằng chứng cũ."""
    release = pinned(root, RELEASE.name)
    old = pinned(root, OLD_RELEASE.name)
    bank = pinned(root, MANIFEST.name)
    panel = pinned(root, PANEL.name)
    names = set((*SOURCES, *old['dependency_sha256'], *old.get('source_sha256', {})))
    if (release['version'] != 'conditional_v4_1_r2_collection_release'
            or release['status'] != 'USER_COLLECTION_RELEASED'
            or release['scope'] != 'PANEL256_ORIGINAL_UPSTREAM_ONLY_2019_2022'
            or release['runtime_namespace'] != NAMESPACE.as_posix()
            or release['collection_operator'] != 'USER_ONLY' or any(release[k] for k in PERMISSIONS)
            or release['hour_cap'] is not None or release['calendar_deadline'] is not None
            or set(release['source_sha256']) != names or bank['status'] != 'NUMERIC_BANK_PASS'
            or release['config'] != old['config'] or release['warmup'] != old['warmup']
            or release['point_ids'] != panel['point_ids'] or len(release['point_ids']) != 256
            or release['shards'] != panel['shards'] or release['nominal_research_HTTP'] != 768
            or release['controls_per_scope'] != 3 or release['numeric_artifact_sha256'] != bank['artifact_sha256']):
        raise ValueError('Release r2 sai scope, panel, model hoặc quyền thực nghiệm')
    git(root, 'merge-base', '--is-ancestor', release['source_commit'], 'HEAD')
    for group in ('source_sha256', 'receipt_sha256', 'numeric_artifact_sha256', 'input_sha256', 'news_sha256'):
        for name, sha in release[group].items():
            raw = (root / name).read_bytes()
            if checksum(raw) != sha:
                raise ValueError('Nguồn r2 bị đổi/mất: ' + name)
            if group == 'source_sha256':
                blob = git(root, 'show', release['source_commit'] + ':' + name)
                if (checksum(blob) != release['source_git_blob_sha256'][name]
                        or raw.replace(b'\r\n', b'\n') != blob.replace(b'\r\n', b'\n')):
                    raise ValueError('Source r2 khác commit khóa: ' + name)
    for name, sha in release['historical_evidence']['surviving_evidence_sha256'].items():
        if checksum((root / name).read_bytes()) != sha:
            raise ValueError('Bằng chứng lượt cũ đã bị sửa/mất: ' + name)
    runtime = release['runtime']
    if platform.python_version() != runtime['python'] or platform.system() != runtime['platform']:
        raise ValueError('Runtime Python/platform khác bản khóa')
    for name, version in {**runtime['packages'], **release['acquisition_runtime']}.items():
        if importlib.metadata.version(name) != version:
            raise ValueError('Dependency khác bản khóa: ' + name)
    ledger = read((root / 'outputs/oos_pilot/api_usage.json').read_bytes())
    verify_ledger(ledger, release['ledger_baseline'])
    return release
