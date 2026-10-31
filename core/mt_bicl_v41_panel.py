"""Release panel256 và cold acceptance; ngân hàng numeric và a0 kiểm độc lập."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx

from core.mt_bicl_v4_collect import clients
from core.mt_bicl_v4_collect_transport import ReplayTransport
from core.mt_bicl_v4_completion import DEPENDENCIES, RELEASE as OLD_RELEASE
from core.mt_bicl_v4_dataset import immutable
from core.mt_bicl_v4_protocol import canonical, checksum, git, read, verify_ledger
from core.mt_bicl_v4_warmup import load_warmup
from core.mt_bicl_v41_bank import DATA, MANIFEST, PANEL, build, source_binding as bank_sources
from core.mt_bicl_v41_collect import DIRECTORY, cold_point, controls
from core.mt_bicl_v41_protocol import LOCK, PROTOCOL, NAMESPACE, verify as verify_spec

RELEASE = Path('docs/plan/week11/collection_release_v4_1.json')
ACCEPTANCE = Path('docs/plan/week11/data_acceptance_v4_1.json')
COVERAGE = Path('docs/plan/week11/coverage_v4_1.json')
SOURCES = ('core/mt_bicl_v41_collect.py', 'core/mt_bicl_v41_panel.py',
           'core/mt_bicl_v41_runtime.py', 'core/mt_bicl_v41_contract.py',
           'scripts/continue_mt_bicl_v4_1.py', 'tests/test_mt_bicl_v41_collection.py',
           'tests/test_mt_bicl_v41_contract.py')
EXTRA = ('core/mt_bicl_v4_collect.py', 'core/mt_bicl_v4_collect_transport.py',
         'core/mt_bicl_v4_completion.py', 'core/mt_bicl_v4_warmup.py',
         'core/mt_bicl_v4_http_diagnostics.py', 'core/mt_bicl_v4_protocol.py',
         'core/mt_bicl_v4_dataset.py', 'core/mt_bicl_v4_data.py', 'core/mt_bicl_v4_lineage.py',
         'scripts/continue_mt_bicl_v4_data.py', 'core/mt_bicl_v41_protocol.py',
         'scripts/prepare_mt_bicl_v4_1.py')


def prepare_release(root: Path) -> dict[str, Any]:
    """Chỉ cấp collection Original/panel2019–2022 sau ngân hàng cold PASS và commit code."""
    if (root/RELEASE).exists():
        return verify_release(root)
    spec = verify_spec(root)
    bank = build(root, verify_only=True)
    if bank['status'] != 'NUMERIC_BANK_PASS':
        raise ValueError('Numeric bank chưa đạt gate; không cấp API')
    parent = read((root/OLD_RELEASE).read_bytes())
    _, warmup = load_warmup(root, parent)
    panel = read((root/PANEL).read_bytes())
    immutable(root/COVERAGE, read((root/DATA/'coverage.json').read_bytes()))
    commit = git(root, 'rev-parse', 'HEAD').decode().strip()
    sources = {}
    for name in SOURCES:
        raw = (root/name).read_bytes()
        if raw != git(root, 'show', commit+':'+name):
            raise ValueError('Cần commit source panel trước release')
        sources[name] = checksum(raw)
    ledger = read((root/'outputs/oos_pilot/api_usage.json').read_bytes())
    result = {'version': 'conditional_v4_1_panel_release', 'status': 'USER_COLLECTION_RELEASED',
        'scope': 'PANEL256_ORIGINAL_UPSTREAM_ONLY_2019_2022', 'source_commit': commit, 'source_sha256': sources,
        'dependency_sha256': {n: checksum((root/n).read_bytes()) for n in dict.fromkeys((*DEPENDENCIES, *EXTRA))},
        'receipt_sha256': {p.as_posix(): checksum((root/p).read_bytes()) for p in
            (PROTOCOL, LOCK, MANIFEST, PANEL, COVERAGE, OLD_RELEASE, Path('docs/plan/week11/data_collection_hotfix_v4.json'))},
        'numeric_artifact_sha256': bank['artifact_sha256'], 'config': parent['config'], 'warmup': parent['warmup'],
        'warmup_verified': warmup, 'point_ids': panel['point_ids'], 'shards': panel['shards'],
        'panel_sha256': checksum((root/PANEL).read_bytes()), 'nominal_research_HTTP': 768, 'controls_per_scope': 3,
        'credential_variables': spec['operation']['credential_variables'],
        'scope_independence_authority': 'USER_CONFIRMED_FOUR_INDEPENDENT_ORGANIZATIONS',
        'plan_authority': {'commit': git(root, 'log', '-1', '--format=%H', '--', 'docs/plan/week11/README.md').decode().strip(),
                           'path': 'docs/plan/week11/README.md', 'sha256': checksum((root/'docs/plan/week11/README.md').read_bytes())},
        'resume': parent['resume'], 'lost_unsealed_response': parent['lost_unsealed_response'],
        'collection_operator': 'USER_ONLY', 'writer': 'ONE_COORDINATOR_SHARED_LEDGER_LOCK',
        'training_allowed': False, 'reference_fit_allowed': False, 'development_allowed': False, 'confirmation_allowed': False,
        'hour_cap': None, 'calendar_deadline': None, 'daily_target_per_scope': 16,
        'ledger_baseline': {'count': len(ledger['requests']), 'requests_prefix_sha256': checksum(canonical(ledger['requests']))}}
    immutable(root/RELEASE, result)
    return result


def verify_release(root: Path) -> dict[str, Any]:
    """Kiểm nguồn, panel, warmup và prefix ledger; không tự reseal hoặc đọc key."""
    verify_spec(root)
    release = read((root/RELEASE).read_bytes())
    if ((root/RELEASE).read_bytes() != git(root, 'show', 'HEAD:'+RELEASE.as_posix())
            or release['version'] != 'conditional_v4_1_panel_release'
            or release['scope'] != 'PANEL256_ORIGINAL_UPSTREAM_ONLY_2019_2022'
            or set(release['source_sha256']) != set(SOURCES)
            or set(release['dependency_sha256']) != set((*DEPENDENCIES, *EXTRA))
            or any(release[k] for k in ('training_allowed', 'reference_fit_allowed', 'development_allowed', 'confirmation_allowed'))
            or release['hour_cap'] is not None or release['calendar_deadline'] is not None):
        raise ValueError('Release v4.1 sai scope/Git hoặc cấp quyền ngoài collection')
    authority = release['plan_authority']
    git(root, 'merge-base', '--is-ancestor', authority['commit'], 'HEAD')
    if checksum(git(root, 'show', authority['commit']+':'+authority['path'])) != authority['sha256']:
        raise ValueError('Plan amendment khác snapshot Git đã khóa')
    bank = read((root/MANIFEST).read_bytes())
    if bank['status'] != 'NUMERIC_BANK_PASS' or bank['source_sha256'] != bank_sources(root, bank['source_commit']):
        raise ValueError('Source/gate numeric bank khác manifest')
    for group in ('source_sha256', 'dependency_sha256', 'receipt_sha256', 'numeric_artifact_sha256'):
        for name, sha in release[group].items():
            if checksum((root/name).read_bytes()) != sha:
                raise ValueError('Nguồn release v4.1 đã đổi: '+name)
    for name, sha in release['source_sha256'].items():
        if checksum(git(root, 'show', release['source_commit']+':'+name)) != sha:
            raise ValueError('Source panel khác commit khóa')
    panel = read((root/PANEL).read_bytes())
    parent = read((root/OLD_RELEASE).read_bytes())
    if (release['point_ids'] != panel['point_ids'] or len(release['point_ids']) != 256
            or release['shards'] != panel['shards'] or release['config'] != parent['config']
            or release['warmup'] != parent['warmup'] or release['nominal_research_HTTP'] != 768):
        raise ValueError('Panel/config/slot khác release đã đăng ký')
    for name, sha in bank['inherited_artifact_sha256'].items():
        if checksum((root/name).read_bytes()) != sha:
            raise ValueError('Artifact v4 cha bị đổi')
    verify_ledger(read((root/'outputs/oos_pilot/api_usage.json').read_bytes()), release['ledger_baseline'])
    return release


def identity(root: Path, release: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Reuse đúng warmup đã seal; giữ namespace/identity mới cho panel, không fetch ngầm."""
    frames, warmup = load_warmup(root, release)
    if warmup != release['warmup_verified']:
        raise ValueError('Warmup khác release panel')
    binding = {'release_sha256': checksum((root/RELEASE).read_bytes()), 'warmup': warmup,
               'panel_manifest_sha256': release['panel_sha256']}
    immutable(root/DIRECTORY/'identity.json', binding)
    return frames, warmup, checksum(canonical(binding))


def accept(root: Path) -> dict[str, Any]:
    """Cold từng canonical body trên256 point; chỉ DATA_READY_PASS khi hai hợp đồng PASS."""
    release = verify_release(root)
    bank = build(root, verify_only=True)
    expected = set(release['point_ids'])
    actual = {p.parent.name for p in (root/DIRECTORY/'points').glob('*/complete.json')}
    if actual - expected:
        raise ValueError('Namespace panel chứa complete ID ngoài manifest')
    if actual != expected:
        return {'status': 'INCOMPLETE_PANEL', 'complete': len(actual), 'remaining': len(expected-actual), 'ready_for_W11_19': False}
    from core.mt_bicl_v41_runtime import read_bindings
    mappings = read_bindings(root, release)
    frames, warmup, signature = identity(root, release)
    rows = {r['episode_id']: r for r in read((root/DATA/'observations.json').read_bytes())['rows']}
    ledger = read((root/'outputs/oos_pilot/api_usage.json').read_bytes())
    news = {s: read((root/f'outputs/historical_memory_run/inputs/news/{s}.json').read_bytes())['scored_articles']
            for s in release['config']['symbol_order']}
    allowed = {name: {m[name] for m in mappings} for name in release['shards']}
    points, http_ids, scopes, evidence = {}, set(), set(), {}
    for i, pid in enumerate(release['point_ids']):
        name = next(n for n, ids in release['shards'].items() if pid in ids)
        record = cold_point(root, rows[pid], frames[rows[pid]['symbol']], news[rows[pid]['symbol']], release, signature, ledger)
        for row in ledger['requests']:
            if row['id'] in record['http']['http_rows_sha256']:
                if row.get('credential_scope') not in allowed[name]:
                    raise ValueError('HTTP point không thuộc shard/scope đã bind')
                scopes.add(row['credential_scope'])
                http_ids.add(row['id'])
        points[pid] = checksum((root/DIRECTORY/'points'/pid/'complete.json').read_bytes())
        evidence.update(record['files_sha256'])
        print(f'Cold panel {i+1}/256 PASS; không API hoặc tính P&L.', flush=True)
    for scope in scopes:
        with httpx.Client(transport=ReplayTransport(ledger, root/DIRECTORY/'http_cache')) as http:
            controls(root, release, signature, clients(release['config'], http, 'offline-fixture'),
                     SimpleNamespace(credential_scope=scope, state=ledger))
    for folder in ('bindings', 'controls'):
        evidence.update({p.relative_to(root).as_posix(): checksum(p.read_bytes())
                         for p in (root/DIRECTORY/folder).rglob('*.json')})
    evidence.update({v['path']: v['sha256'] for v in warmup['symbols'].values()})
    result = {'version': 'conditional_v4_1_data_acceptance', 'status': 'DATA_READY_PASS', 'ready_for_W11_19': True,
        'numeric_manifest_sha256': checksum((root/MANIFEST).read_bytes()), 'release_sha256': checksum((root/RELEASE).read_bytes()),
        'panel_manifest_sha256': checksum((root/PANEL).read_bytes()), 'points': points, 'warmup': warmup,
        'evidence_sha256': evidence,
        'http_rows_sha256': {r['id']: checksum(canonical(r)) for r in ledger['requests'] if r['id'] in http_ids},
        'numeric_gate': bank['status'], 'unique_points': len(points), 'cold_canonical_replay': True,
        'forecast_training_performed': False, 'development_or_confirmation_allowed': False}
    immutable(root/ACCEPTANCE, result)
    return result
