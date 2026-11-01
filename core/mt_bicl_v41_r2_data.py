"""Ngân hàng độc lập r2 từ giá gốc; giữ nguyên numeric, nhãn và lựa chọn D/C v4.1."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from core.execution_prices import load_verified_execution_data
from core.mt_bicl_v4_data import NUMERIC, bounded_index, symbol_data
from core.mt_bicl_v4_data_regimes import DataRegimes
from core.mt_bicl_v4_dataset import encoded, immutable
from core.mt_bicl_v4_protocol import checksum, fit_eligible, git, read
from core.mt_bicl_v41_bank import coverage, select_panel
from core.mt_bicl_v41_data import core_valid, fit_scaler, membership

NAMESPACE = Path('outputs/bayesian_benchmark/mt_bicl_v4_1_r2')
DATA = NAMESPACE / 'data'
DOC = Path('docs/plan/week11')
MANIFEST = DOC / 'dataset_manifest_v4_1_r2.json'
PANEL = DOC / 'panel_manifest_v4_1.json'
SOURCES = ('core/mt_bicl_v41_r2_data.py', 'core/mt_bicl_v4_data.py',
    'core/mt_bicl_v4_data_regimes.py', 'core/mt_bicl_v4_dataset.py',
    'core/mt_bicl_v41_data.py', 'core/mt_bicl_v41_bank.py', 'core/regime_detector.py',
    'core/execution_prices.py', 'core/backtest_engine.py')


def pinned(root: Path, name: str) -> dict[str, Any]:
    """Đọc receipt Git hiện hành, không gọi verifier phụ thuộc raw lịch sử đã mất."""
    path = DOC / name
    raw = (root / path).read_bytes()
    if raw != git(root, 'show', 'HEAD:' + path.as_posix()):
        raise ValueError('Receipt khác Git: ' + name)
    return read(raw)


def original_proofs(value: Any, model_hashes: dict[str, str]) -> Any:
    """Đổi duy nhất ID proof model khi so byte; không đổi regime, scaler hoặc membership."""
    if isinstance(value, list):
        return [original_proofs(v, model_hashes) for v in value]
    if isinstance(value, dict):
        result = {k: original_proofs(v, model_hashes) for k, v in value.items()}
        if result.get('model_sha256') is not None:
            result['model_sha256'] = model_hashes[result['fit_end']]
        return result
    return value


def compare_numeric(values: dict[str, Any], parent: dict[str, Any], models: dict[str, str]) -> None:
    """Bắt thay đổi thiết kế; chỉ cho phép proof hash của model tái dựng thay đổi."""
    for name, value in values.items():
        old = 'outputs/bayesian_benchmark/mt_bicl_v4_1/data/' + name
        candidate = original_proofs(value, models) if name in ('folds.json', 'train_prefixes.json') else value
        if checksum(encoded(candidate)) != parent['artifact_sha256'][old]:
            raise ValueError('Dữ liệu hoặc lựa chọn r2 khác v4.1 đã đăng ký: ' + name)


def build(root: Path, *, verify_only: bool = False) -> dict[str, Any]:
    """Dựng/cold rebuild từ nguồn giá≤2022; HMM mới không mở predictor hoặc API."""
    spec = pinned(root, 'protocol_v4_1.json')
    parent = pinned(root, 'dataset_manifest_v4_1.json')
    legacy = pinned(root, 'dataset_manifest_v4.json')
    price_spec = pinned(root, 'protocol_v4.json')
    for group in ('input_sha256', 'baseline_source_sha256'):
        for name, sha in price_spec[group].items():
            if checksum((root / name).read_bytes()) != sha:
                raise ValueError('Nguồn giá hoặc kinh tế khác bản khóa: ' + name)
    existing = pinned(root, MANIFEST.name) if (root / MANIFEST).exists() else None
    if verify_only and existing is None:
        raise ValueError('Chưa có manifest ngân hàng r2')
    if existing:
        for name, sha in existing['artifact_sha256'].items():
            if checksum((root / name).read_bytes()) != sha:
                raise ValueError('Artifact r2 bị đổi/mất: ' + name)
    history = bounded_index(root / 'data/historical/VNINDEX.csv', '2022-12-31')
    rows, labels = [], {}
    for symbol in spec['data']['symbols']:
        frame, events = load_verified_execution_data(root / 'data/execution_prices', symbol)
        actual_rows, actual_labels = symbol_data(symbol, frame, events, history)
        rows.extend(actual_rows)
        labels.update(actual_labels)
    rows.sort(key=lambda r: (r['as_of_date'], spec['data']['symbols'].index(r['symbol'])))
    if len({r['episode_id'] for r in rows}) != 1640 or len(labels) != 1523:
        raise ValueError('Grid/nhãn r2 khác cỡ mẫu đã khóa')
    frozen = read((root / DATA / 'regime_registry.json').read_bytes()) if existing else None
    regimes = DataRegimes(history, root / DATA / 'regime_models', frozen=frozen)
    definitions = {}
    for outer in spec['folds']:
        definitions['outer_' + outer['id']] = outer
        for inner in outer['inner']:
            definitions['inner_' + inner['id']] = inner
    folds = {}
    for name, definition in sorted(definitions.items()):
        cap = definition['fit_end']
        states = regimes.view(rows, cap)
        queries = [r for r in rows if definition['evaluation_start'] <= r['as_of_date'] <= definition['evaluation_end']]
        scaler = fit_scaler(rows, cap)
        folds[name] = {k: definition[k] for k in ('fit_end', 'evaluation_start', 'evaluation_end')}
        folds[name].update(evaluation_ids=[r['episode_id'] for r in queries],
            regimes={r['episode_id']: states[r['episode_id']] for r in rows if r['as_of_date'] <= definition['evaluation_end']},
            scaler=scaler,
            fit_ids=[r['episode_id'] for r in rows if r['label_eligible'] and core_valid(r) and
                fit_eligible(r['entry_date'], r['exit_date'], cap, definition['evaluation_start'], definition['evaluation_end'])],
            memberships=[membership(r, rows, scaler, states) for r in queries])
        print(f'Ngân hàng r2 {name}: {len(queries)} query; không API hoặc fit predictor.', flush=True)
    train = [r for r in rows if r['as_of_date'] <= '2020-12-31']
    states = regimes.view(rows, '2020-12-31')
    scalers, members = {}, []
    for row in train:
        query = row['as_of_date']
        if query not in scalers:
            cap = (date.fromisoformat(query) - timedelta(days=1)).isoformat()
            scalers[query] = fit_scaler(rows, cap, query=query)
        members.append(membership(row, rows, scalers[query], states))
    values = {'observations.json': {'feature_columns': list(NUMERIC), 'schema': 'NUMERIC9_MASK9_REGIME_ONLY_NO_AGENT_OR_A0', 'rows': rows},
        'labels.json': labels, 'folds.json': folds,
        'train_prefixes.json': {'scalers_by_query_date': scalers, 'memberships': members,
                              'regimes': {r['episode_id']: states[r['episode_id']] for r in train}},
        'coverage.json': coverage(rows, folds, spec)}
    model_hashes = {Path(name).stem: sha for name, sha in legacy['artifact_sha256'].items() if '/regime_models/' in name}
    compare_numeric(values, parent, model_hashes)
    if encoded(select_panel(rows, folds)) != (root / PANEL).read_bytes():
        raise ValueError('Panel r2 khác panel256 đã đăng ký')
    for name, value in {**values, 'regime_registry.json': regimes.records}.items():
        immutable(root / DATA / name, value, verify_only=bool(existing))
    commit = existing['source_commit'] if existing else git(root, 'rev-parse', 'HEAD').decode().strip()
    sources = {}
    for name in SOURCES:
        raw = (root / name).read_bytes()
        if raw != git(root, 'show', commit + ':' + name):
            raise ValueError('Source r2 chưa commit hoặc đã thay đổi: ' + name)
        sources[name] = checksum(raw)
    paths = [DATA / name for name in (*values, 'regime_registry.json')]
    paths.extend(DATA / 'regime_models' / (cap + '.json') for cap in regimes.records)
    result = {'version': 'conditional_v4_1_r2_numeric_manifest', 'status': values['coverage.json']['status'],
        'source_commit': commit, 'source_sha256': sources,
        'protocol_sha256': checksum((root / DOC / 'protocol_v4_1.json').read_bytes()),
        'parent_manifest_sha256': checksum((root / DOC / 'dataset_manifest_v4_1.json').read_bytes()),
        'input_sha256': price_spec['input_sha256'],
        'artifact_sha256': {p.as_posix(): checksum((root / p).read_bytes()) for p in paths},
        'numeric_labels_scalers_memberships_and_regime_names_identical': True,
        'model_proof_policy': 'REBUILD_SAME_HMM_SEED_PARAMETERS_PREFIX_RUNTIME_NEW_BYTE_IDENTITY_NOT_OLD_RESTORE',
        'historical_agent_reports_required': False, 'grid_queries': len(rows), 'labeled_cycles': len(labels),
        'panel_manifest_sha256': checksum((root / PANEL).read_bytes()),
        'predictor_or_reference_fit': False, 'training_allowed': False, 'ready_for_W11_19': False}
    if result['status'] != 'NUMERIC_BANK_PASS':
        raise ValueError('Ngân hàng r2 chưa đạt hỗ trợ dữ liệu')
    immutable(root / MANIFEST, result, verify_only=bool(existing))
    return result
