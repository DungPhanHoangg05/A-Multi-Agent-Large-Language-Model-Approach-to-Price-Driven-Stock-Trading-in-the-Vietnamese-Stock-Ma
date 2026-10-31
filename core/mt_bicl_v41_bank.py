"""Ngân hàng v4.1 và panel cố định; nhãn sidecar giữ byte, không fit predictor."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from core.execution_prices import load_verified_execution_data
from core.mt_bicl_v4_data import NUMERIC, bounded_index, symbol_data
from core.mt_bicl_v4_dataset import encoded, immutable
from core.mt_bicl_v4_protocol import canonical, checksum, git, read
from core.mt_bicl_v41_data import core_valid, fit_scaler, membership, support, transform
from core.mt_bicl_v41_protocol import NAMESPACE, PANEL_SHA, PROTOCOL, verify as verify_spec

OLD = Path('outputs/bayesian_benchmark/mt_bicl_v4/data')
DATA = NAMESPACE/'data'
MANIFEST = Path('docs/plan/week11/dataset_manifest_v4_1.json')
PANEL = Path('docs/plan/week11/panel_manifest_v4_1.json')
SOURCES = ('core/mt_bicl_v41_data.py', 'core/mt_bicl_v41_bank.py',
           'tests/test_mt_bicl_v41_data.py', 'tests/test_mt_bicl_v41_leakage.py')


def source_binding(root: Path, commit: str) -> dict[str, str]:
    """Khóa đúng source dựng dữ liệu theo commit, không phụ thuộc task tương lai."""
    result = {}
    git(root, 'merge-base', '--is-ancestor', commit, 'HEAD')
    for name in SOURCES:
        raw = (root/name).read_bytes()
        if raw != git(root, 'show', commit+':'+name):
            raise ValueError('Source ngân hàng chưa commit hoặc đã đổi: '+name)
        result[name] = checksum(raw)
    return result


def select_panel(rows: list[dict[str, Any]], folds: dict[str, Any]) -> dict[str, Any]:
    """Lấy midpoint8 trên32 stratum; chỉ metadata eligibility, không đọc nhãn/action/X."""
    if len({r['episode_id'] for r in rows}) != len(rows):
        raise ValueError('Grid có ID trùng')
    strata, ids = {}, []
    for year in range(2019, 2023):
        for symbol in ('FPT', 'MWG', 'VCB', 'VNM'):
            for half in (1, 2):
                pool = sorted((r for r in rows if r['label_eligible'] and r['symbol'] == symbol
                    and r['as_of_date'][:4] == str(year) and (1 if int(r['as_of_date'][5:7]) <= 6 else 2) == half),
                    key=lambda r: (r['as_of_date'], r['episode_id']))
                if len(pool) < 8:
                    raise ValueError('INSUFFICIENT_PANEL: '+f'{year}:{symbol}:H{half}')
                positions = [((2*j+1)*len(pool))//16 for j in range(8)]
                chosen = [pool[j]['episode_id'] for j in positions]
                strata[f'{year}:{symbol}:H{half}'] = {'pool_count': len(pool), 'positions': positions, 'point_ids': chosen}
                ids.extend(chosen)
    ids.sort()
    digest = checksum(('\n'.join(ids)+'\n').encode('utf-8'))
    if len(ids) != 256 or len(set(ids)) != 256 or digest != PANEL_SHA:
        raise ValueError('Panel256 không khớp lịch/hash đăng ký')
    by_id = {r['episode_id']: r for r in rows}
    return {'version': 'conditional_v4_1_panel256', 'point_ids': ids, 'point_ids_sha256': digest,
        'strata': strata, 'shards': {f'scope_{i+1}': ids[i::4] for i in range(4)},
        'fold_roles': {n: [i for i in ids if f['evaluation_start'] <= by_id[i]['as_of_date'] <= f['evaluation_end']]
                       for n, f in folds.items()},
        'core_valid': sum(core_valid(by_id[i]) for i in ids),
        'complete_case': sum(not any(by_id[i]['features']['missing_mask']) for i in ids),
        'actual_collection_complete': False, 'nominal_research_HTTP': 768,
        'population': 'SPARSE_POLICY_PANEL_NOT_FULL_GRID_ACCOUNT_RETURN'}


def verify_parent(root: Path) -> dict[str, Any]:
    """Kiểm receipt/source/artifact cũ và rebuild feature/nhãn thật từ giá đã khóa."""
    path = Path('docs/plan/week11/dataset_manifest_v4.json')
    raw = (root/path).read_bytes()
    if raw != git(root, 'show', 'HEAD:'+path.as_posix()):
        raise ValueError('Manifest cha khác Git')
    parent = read(raw)
    for group in ('source_sha256', 'artifact_sha256', 'agent_input_sha256'):
        for name, sha in parent[group].items():
            if checksum((root/name).read_bytes()) != sha:
                raise ValueError('Bằng chứng cha bị đổi: '+name)
    history = bounded_index(root/'data/historical/VNINDEX.csv', '2022-12-31')
    original = read((root/OLD/'observations.json').read_bytes())['rows']
    by_id = {r['episode_id']: r for r in original}
    labels, rebuilt_ids = {}, set()
    for symbol in ('FPT', 'MWG', 'VCB', 'VNM'):
        frame, events = load_verified_execution_data(root/'data/execution_prices', symbol)
        rebuilt, actual_labels = symbol_data(symbol, frame, events, history)
        for row in rebuilt:
            if row != {k: v for k, v in by_id[row['episode_id']].items() if k != 'agent'}:
                raise ValueError('Numeric/mask/metadata khác rebuild giá thật')
            rebuilt_ids.add(row['episode_id'])
        labels.update(actual_labels)
    if rebuilt_ids != set(by_id) or encoded(labels) != (root/OLD/'labels.json').read_bytes():
        raise ValueError('Nhãn engine hoặc grid khác snapshot cha')
    return parent


def coverage(rows: list[dict[str, Any]], folds: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    """Hai hợp đồng: numeric bank PASS không tự chứng nhận panel chưa thu thập."""
    groups, failures = {}, []
    by_id = {r['episode_id']: r for r in rows}
    minimum = spec['data']['minimum_support']
    for name, fold in folds.items():
        groups[name] = {}
        for symbol in spec['data']['symbols']:
            fit = [by_id[i] for i in fold['fit_ids'] if by_id[i]['symbol'] == symbol]
            evaluation = [by_id[i] for i in fold['evaluation_ids'] if by_id[i]['symbol'] == symbol]
            f, q = support(fit), support(evaluation)
            inner = name.startswith('inner_')
            checks = {'fit_core_cycles': f['core_valid'] >= minimum['inner_train_labeled_cycles_per_symbol' if inner else 'train_labeled_cycles_per_symbol'],
                'fit_core_tasks': f['tasks_with_two_cycles'] >= minimum['inner_train_tasks_per_symbol' if inner else 'train_tasks_with_two_cycles_per_symbol']}
            if not inner:
                checks.update(eval_core_cycles=q['core_valid'] >= minimum['outer_labeled_cycles_per_symbol'],
                              eval_core_fraction=q['core_fraction'] >= minimum['core_fraction_each_outer_symbol'])
            failures.extend({'fold': name, 'symbol': symbol, 'check': c} for c, passed in checks.items() if not passed)
            members = [m for m in fold['memberships'] if by_id[m['query_id']]['symbol'] == symbol]
            scaled = [transform(r, fold['scaler']) for r in evaluation]
            drift = []
            for j in range(9):
                v = [t['z'][j] for t in scaled if not t['mask'][j]]
                drift.append(float(np.mean(v)) if v else None)
            groups[name][symbol] = {'fit': f, 'evaluation': q, 'checks': checks,
                'mean_observed_standardized_shift': drift, 'ood_queries': sum(m['ood'] for m in members),
                'K_histogram': dict(Counter(str(m['K']) for m in members)),
                'm_histogram': dict(Counter(str(m['m']) for m in members)),
                'mask_histogram': dict(Counter(''.join(str(int(x)) for x in r['features']['missing_mask']) for r in evaluation))}
    return {'version': 'conditional_v4_1_numeric_coverage', 'status': 'INSUFFICIENT_NUMERIC_DATA' if failures else 'NUMERIC_BANK_PASS',
            'full_summary': support(rows), 'folds': groups, 'failed_checks': failures,
            'panel_status': 'AWAITING_USER_COLLECTION', 'ready_for_W11_19': False}


def build(root: Path, *, verify_only: bool = False) -> dict[str, Any]:
    """Dựng/cold rebuild scaler và D/C; chỉ load regime cha, không fit model dự báo."""
    spec = verify_spec(root)
    parent = verify_parent(root)
    rows = [{k: deepcopy(v) for k, v in row.items() if k != 'agent'}
            for row in read((root/OLD/'observations.json').read_bytes())['rows']]
    old_folds = read((root/OLD/'folds.json').read_bytes())
    train_old = read((root/OLD/'train_prefixes.json').read_bytes())
    folds = {}
    by_id = {r['episode_id']: r for r in rows}
    for name, old in old_folds.items():
        cap = old['fit_end']
        scaler = fit_scaler(rows, cap)
        folds[name] = {k: deepcopy(old[k]) for k in ('fit_end', 'evaluation_start', 'evaluation_end', 'evaluation_ids', 'regimes')}
        folds[name].update(scaler=scaler, fit_ids=[i for i in old['fit_ids'] if core_valid(by_id[i])],
            memberships=[membership(by_id[i], rows, scaler, old['regimes']) for i in old['evaluation_ids']])
        print(f"Ngân hàng v4.1 {name}: fit{len(folds[name]['fit_ids'])}, query{len(old['evaluation_ids'])}; không fit predictor.", flush=True)
    scalers, memberships = {}, []
    for row in rows:
        if row['as_of_date'] > '2020-12-31':
            continue
        query = row['as_of_date']
        if query not in scalers:
            scalers[query] = fit_scaler(rows, (date.fromisoformat(query)-timedelta(days=1)).isoformat(), query=query)
        memberships.append(membership(row, rows, scalers[query], train_old['regimes']))
    panel = select_panel(rows, old_folds)
    report = coverage(rows, folds, spec)
    artifacts = {'observations.json': {'feature_columns': list(NUMERIC), 'schema': 'NUMERIC9_MASK9_REGIME_ONLY_NO_AGENT_OR_A0', 'rows': rows},
        'labels.json': read((root/OLD/'labels.json').read_bytes()), 'folds.json': folds,
        'train_prefixes.json': {'scalers_by_query_date': scalers, 'memberships': memberships, 'regimes': train_old['regimes']},
        'coverage.json': report}
    existing = read((root/MANIFEST).read_bytes()) if (root/MANIFEST).exists() else None
    cold = verify_only or existing is not None
    if existing and (root/MANIFEST).read_bytes() != git(root, 'show', 'HEAD:'+MANIFEST.as_posix()):
        raise ValueError('Manifest numeric v4.1 chưa neo Git')
    for name, value in artifacts.items():
        immutable(root/DATA/name, value, verify_only=cold)
    immutable(root/PANEL, panel, verify_only=cold)
    if cold and (root/PANEL).read_bytes() != git(root, 'show', 'HEAD:'+PANEL.as_posix()):
        raise ValueError('Panel v4.1 chưa neo Git')
    commit = existing['source_commit'] if existing else git(root, 'rev-parse', 'HEAD').decode().strip()
    result = {'version': 'conditional_v4_1_numeric_manifest', 'status': report['status'], 'source_commit': commit,
        'source_sha256': source_binding(root, commit), 'protocol_sha256': checksum((root/PROTOCOL).read_bytes()),
        'parent_manifest_sha256': checksum((root/'docs/plan/week11/dataset_manifest_v4.json').read_bytes()),
        'inherited_artifact_sha256': parent['artifact_sha256'], 'panel_manifest_sha256': checksum((root/PANEL).read_bytes()),
        'artifact_sha256': {(DATA/n).as_posix(): checksum((root/DATA/n).read_bytes()) for n in artifacts},
        'labels_byte_identical': checksum((root/DATA/'labels.json').read_bytes()) == checksum((root/OLD/'labels.json').read_bytes()),
        'grid_queries': len(rows), 'numeric_summary': report['full_summary'], 'predictor_or_reference_fit': False,
        'ready_for_W11_19': False, 'training_allowed': False, 'collection_released': False}
    immutable(root/MANIFEST, result, verify_only=cold)
    return result
