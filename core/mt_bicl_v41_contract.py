"""Cửa vào downstream v4.1; từ chối manifest v4, tách forecast dense và policy panel."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from core.mt_bicl_v4_protocol import checksum, git, read
from core.mt_bicl_v41_bank import DATA, MANIFEST, PANEL
from core.mt_bicl_v41_data import core_valid, fit_scaler, transform
from core.mt_bicl_v41_panel import ACCEPTANCE, RELEASE, verify_release
from core.mt_bicl_v41_protocol import PROTOCOL


def load_ready(root: Path) -> dict[str, Any]:
    """Chỉ mở W11-19 khi cold acceptance đúng revision đã commit và mọi hash còn khớp."""
    release = verify_release(root)
    if not (root/ACCEPTANCE).exists():
        raise ValueError('W11-18 v4.1 chưa cold nghiệm thu DATA_READY_PASS')
    raw = (root/ACCEPTANCE).read_bytes()
    receipt = read(raw)
    if (raw != git(root, 'show', 'HEAD:'+ACCEPTANCE.as_posix())
            or receipt.get('version') != 'conditional_v4_1_data_acceptance'
            or receipt.get('status') != 'DATA_READY_PASS' or not receipt.get('ready_for_W11_19')
            or receipt.get('numeric_gate') != 'NUMERIC_BANK_PASS' or receipt.get('unique_points') != 256
            or set(receipt.get('points', {})) != set(release['point_ids'])
            or not receipt.get('cold_canonical_replay')):
        raise ValueError('Receipt dữ liệu không phải acceptance đầy đủ v4.1')
    for key, path in (('numeric_manifest_sha256', MANIFEST), ('panel_manifest_sha256', PANEL), ('release_sha256', RELEASE)):
        if receipt[key] != checksum((root/path).read_bytes()):
            raise ValueError('Nguồn acceptance thay đổi')
    from core.mt_bicl_v41_collect import DIRECTORY
    for pid, sha in receipt['points'].items():
        if checksum((root/DIRECTORY/'points'/pid/'complete.json').read_bytes()) != sha:
            raise ValueError('Point acceptance bị sửa')
    for name, sha in receipt['evidence_sha256'].items():
        if checksum((root/name).read_bytes()) != sha:
            raise ValueError('Raw/journal/probe/source acceptance bị sửa')
    ledger = read((root/'outputs/oos_pilot/api_usage.json').read_bytes())
    from core.mt_bicl_v4_protocol import canonical
    by_id = {r['id']: r for r in ledger['requests']}
    if any(i not in by_id or checksum(canonical(by_id[i])) != sha for i, sha in receipt['http_rows_sha256'].items()):
        raise ValueError('Ledger acceptance bị sửa')
    originals = {pid: read((root/DIRECTORY/'points'/pid/'complete.json').read_bytes())['original'] for pid in receipt['points']}
    return {'protocol': read((root/PROTOCOL).read_bytes()),
            'bank': read((root/DATA/'observations.json').read_bytes()),
            'folds': read((root/DATA/'folds.json').read_bytes()),
            'panel': read((root/PANEL).read_bytes()), 'acceptance': receipt, 'originals': originals}


def feature_input(row: dict[str, Any], scaler: dict[str, Any], regime: str) -> dict[str, Any]:
    """Schema chung cho baseline/reference/learner:9 numeric,9 mask và regime; không a0."""
    if regime not in ('BULL', 'BEAR', 'CHOPPY', 'CONSOLIDATION', 'UNKNOWN'):
        raise ValueError('Regime ngoài schema v4.1')
    t = transform(row, scaler)
    return {'numeric': t['z'], 'missing_mask': t['mask'], 'regime': regime,
            'eligible': t['eligible'], 'ood': t['ood']}


def family_fit(rows: list[dict[str, Any]], fit_end: str, family: str) -> tuple[list[str], dict[str, Any]]:
    """Complete_case có tập fit/scaler riêng; cùng cutoff và registry lựa chọn với Full."""
    allowed = ('Full_conditional_MT', 'Target_only_K0', 'Pooled_context', 'No_target',
               'Complete_case_MT', 'Hierarchical_reference', 'Numerical_MT')
    if family not in allowed:
        raise ValueError('Family ngoài hợp đồng v4.1')
    candidates = [r for r in rows if r['label_eligible'] and r['exit_date'] <= fit_end and core_valid(r)
                  and (family != 'Complete_case_MT' or not any(r['features']['missing_mask']))]
    return [r['episode_id'] for r in candidates], fit_scaler(candidates, fit_end)


def policy_prediction_key(panel: dict[str, Any], fold_id: str, point_id: str) -> str:
    """Không lấy prediction fit2020 dùng cho outer2020 hoặc gán action ngoài panel."""
    if fold_id not in panel['fold_roles'] or point_id not in panel['fold_roles'][fold_id]:
        raise ValueError('Policy chỉ chấm đúng panel/fold đã đăng ký')
    return fold_id+'/'+point_id


def original_for_policy(data: dict[str, Any], fold_id: str, point_id: str) -> dict[str, Any]:
    """Chỉ cung cấp a0 thật cho đúng panel/fold; ngoài panel không có action thay thế."""
    policy_prediction_key(data['panel'], fold_id, point_id)
    if point_id not in data['originals']:
        raise ValueError('Thiếu Original durable của panel')
    return deepcopy(data['originals'][point_id])


def original_fallback(original: dict[str, Any], *, enabled: bool, numeric: dict[str, Any]) -> dict[str, Any] | None:
    """OFF/missing/OOD trả nguyên Original durable; không dựng CASH thay API lỗi."""
    if not isinstance(original, dict) or original.get('decision') not in ('LONG', 'SHORT'):
        raise ValueError('Fallback cần Original durable đúng schema')
    if not enabled or not numeric['eligible'] or numeric['ood']:
        return deepcopy(original)
    return None
