"""Cold nghiệm thu r2 và nối cửa dữ liệu sang W11-19; không mở payoff hoặc API."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx

from core.mt_bicl_v4_collect import clients
from core.mt_bicl_v4_collect_transport import OfflinePending, ReplayTransport
from core.mt_bicl_v4_dataset import immutable
from core.mt_bicl_v4_protocol import canonical, checksum, read
from core.mt_bicl_v41_r2_data import DATA, DOC, MANIFEST, PANEL, build
from core.mt_bicl_v41_r2_release import verify
from core.mt_bicl_v41_r2_warmup import COLLECTION, RELEASE, identity
from core.panel_collection import cold_point, controls
from core.panel_coordinator import PanelLayout, read_bindings

ACCEPTANCE = DOC / 'data_acceptance_v4_1_r2.json'
LAYOUT = PanelLayout(COLLECTION, DATA, RELEASE, identity)


def accept(root: Path) -> dict[str, Any]:
    """Chỉ DATA_READY_PASS sau đúng256 point, cold canonical replay và numeric rebuild."""
    release = verify(root)
    expected = set(release['point_ids'])
    actual = {p.parent.name for p in (root / COLLECTION / 'points').glob('*/complete.json')}
    if actual - expected:
        raise ValueError('Namespace r2 chứa ID ngoài panel')
    if actual != expected:
        return {'status': 'INCOMPLETE_PANEL', 'complete': len(actual), 'remaining': len(expected - actual), 'ready_for_W11_19': False}
    bank = build(root, verify_only=True)
    frames, warmup, signature = identity(root, release)
    mappings = read_bindings(root, release, layout=LAYOUT)
    allowed = {name: {m[name] for m in mappings} for name in release['shards']}
    rows = {r['episode_id']: r for r in read((root / DATA / 'observations.json').read_bytes())['rows']}
    ledger = read((root / 'outputs/oos_pilot/api_usage.json').read_bytes())
    ledger_by_id = {r['id']: r for r in ledger['requests']}
    news = {s: read((root / f'outputs/historical_memory_run/inputs/news/{s}.json').read_bytes())['scored_articles']
            for s in release['config']['symbol_order']}
    points, http_ids, scopes, evidence = {}, set(), set(), {}
    for index, pid in enumerate(release['point_ids']):
        name = next(n for n, ids in release['shards'].items() if pid in ids)
        record = cold_point(root, rows[pid], frames[rows[pid]['symbol']], news[rows[pid]['symbol']],
                            release, signature, ledger, collection=COLLECTION)
        for rid in record['http']['http_rows_sha256']:
            row = ledger_by_id[rid]
            if row.get('credential_scope') not in allowed[name] or row.get('operational_amendment_sha256') != checksum((root / RELEASE).read_bytes()):
                raise ValueError('HTTP point r2 sai release hoặc shard/scope')
            scopes.add(row['credential_scope'])
            http_ids.add(rid)
        points[pid] = checksum((root / COLLECTION / 'points' / pid / 'complete.json').read_bytes())
        evidence.update(record['files_sha256'])
        print(f'Cold r2 {index + 1}/256 PASS; không API hoặc P&L.', flush=True)
    for scope in scopes | set(mappings[-1].values()):
        with httpx.Client(transport=ReplayTransport(ledger, root / COLLECTION / 'http_cache')) as http:
            try:
                controls(root, release, signature, clients(release['config'], http, 'offline-fixture'),
                         SimpleNamespace(credential_scope=scope, state=ledger), collection=COLLECTION)
            except OfflinePending:
                raise ValueError('Thiếu raw probe scope r2 khi cold nghiệm thu') from None
    for folder in ('bindings', 'controls'):
        evidence.update({p.relative_to(root).as_posix(): checksum(p.read_bytes()) for p in (root / COLLECTION / folder).rglob('*.json')})
    evidence.update({v['path']: v['sha256'] for v in warmup['symbols'].values()})
    for name in ('warmup_verified.json', 'identity.json'):
        path = COLLECTION / name
        evidence[path.as_posix()] = checksum((root / path).read_bytes())
    result = {'version': 'conditional_v4_1_r2_data_acceptance', 'status': 'DATA_READY_PASS', 'ready_for_W11_19': True,
        'numeric_manifest_sha256': checksum((root / MANIFEST).read_bytes()), 'release_sha256': checksum((root / RELEASE).read_bytes()),
        'panel_manifest_sha256': checksum((root / PANEL).read_bytes()), 'points': points, 'warmup': warmup,
        'evidence_sha256': evidence, 'http_rows_sha256': {rid: checksum(canonical(ledger_by_id[rid])) for rid in sorted(http_ids)},
        'numeric_gate': bank['status'], 'unique_points': len(points), 'cold_canonical_replay': True,
        'historical_evidence_loss_retained': True, 'forecast_training_performed': False,
        'development_or_confirmation_allowed': False}
    immutable(root / ACCEPTANCE, result)
    return result
