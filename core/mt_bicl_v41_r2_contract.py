"""Cửa downstream r2; chỉ mở khi cold acceptance mới đã neo Git."""

from pathlib import Path
from typing import Any

from core.mt_bicl_v4_protocol import canonical, checksum, read
from core.mt_bicl_v41_contract import (family_fit, feature_input, original_fallback,
    original_for_policy, policy_prediction_key)
from core.mt_bicl_v41_r2_acceptance import ACCEPTANCE
from core.mt_bicl_v41_r2_data import DATA, MANIFEST, NAMESPACE, PANEL, pinned
from core.mt_bicl_v41_r2_release import verify
from core.mt_bicl_v41_r2_warmup import COLLECTION, RELEASE


def load_ready(root: Path) -> dict[str, Any]:
    """Không dùng receipt v4/v4.1 cũ thay cho acceptance r2 đầy đủ256 ID."""
    release = verify(root)
    if not (root / ACCEPTANCE).is_file():
        raise ValueError('W11-18 r2 chưa cold nghiệm thu DATA_READY_PASS')
    receipt = pinned(root, ACCEPTANCE.name)
    if (receipt.get('version') != 'conditional_v4_1_r2_data_acceptance'
            or receipt.get('status') != 'DATA_READY_PASS' or not receipt.get('ready_for_W11_19')
            or receipt.get('numeric_gate') != 'NUMERIC_BANK_PASS' or receipt.get('unique_points') != 256
            or set(receipt.get('points', {})) != set(release['point_ids']) or not receipt.get('cold_canonical_replay')):
        raise ValueError('Receipt r2 chưa đủ cold gate/panel256')
    for key, path in (('numeric_manifest_sha256', MANIFEST), ('panel_manifest_sha256', PANEL), ('release_sha256', RELEASE)):
        if receipt[key] != checksum((root / path).read_bytes()):
            raise ValueError('Nguồn acceptance r2 đã thay đổi')
    for pid, sha in receipt['points'].items():
        if checksum((root / COLLECTION / 'points' / pid / 'complete.json').read_bytes()) != sha:
            raise ValueError('Point acceptance r2 bị sửa/mất')
    for name, sha in receipt['evidence_sha256'].items():
        if checksum((root / name).read_bytes()) != sha:
            raise ValueError('Bằng chứng acceptance r2 bị sửa/mất')
    ledger = read((root / 'outputs/oos_pilot/api_usage.json').read_bytes())
    by_id = {r['id']: r for r in ledger['requests']}
    if any(rid not in by_id or checksum(canonical(by_id[rid])) != sha for rid, sha in receipt['http_rows_sha256'].items()):
        raise ValueError('Ledger acceptance r2 bị sửa')
    protocol = pinned(root, 'protocol_v4_1.json')
    protocol['namespace'] = NAMESPACE.as_posix()
    protocol['runtime_amendment_sha256'] = checksum((root / RELEASE).read_bytes())
    originals = {pid: read((root / COLLECTION / 'points' / pid / 'complete.json').read_bytes())['original'] for pid in receipt['points']}
    return {'protocol': protocol, 'bank': read((root / DATA / 'observations.json').read_bytes()),
        'folds': read((root / DATA / 'folds.json').read_bytes()), 'panel': pinned(root, PANEL.name),
        'acceptance': receipt, 'originals': originals}
