"""Khôi phục artifact xác định bằng đúng SHA-256 cũ; không gọi API hoặc reseal."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
import argparse
import hashlib
import os
from pathlib import Path
import socket
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.mt_bicl_v4_dataset import encoded


def sha256(raw: bytes) -> str:
    """Băm nguyên byte, không chuẩn hóa xuống dòng hoặc thứ tự JSON."""
    return hashlib.sha256(raw).hexdigest()


def restore_exact(root: Path, name: str, raw: bytes, expected: str) -> str:
    """Chỉ tạo file thiếu nếu khớp hash; không ghi đè file khác hoặc thoát thư mục."""
    target = (root / name).resolve()
    if not target.is_relative_to(root.resolve()) or target == root.resolve():
        raise ValueError('Đường dẫn phục hồi nằm ngoài workspace')
    if sha256(raw) != expected:
        raise ValueError('Bản dựng không trùng SHA-256 đã khóa: ' + name)
    if target.exists():
        if target.read_bytes() != raw:
            raise ValueError('Giữ nguyên file hiện có khác bằng chứng: ' + name)
        return 'ALREADY_EXACT'
    target.parent.mkdir(parents=True, exist_ok=True)
    # Hard link chỉ công bố file sau fsync và không ghi đè khi có writer khác.
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return 'RESTORED_EXACT'


def recover(root: Path) -> dict[str, Any]:
    """Dựng numeric/mask/PIT từ giá gốc; chỉ cài artifact trùng manifest Git cũ."""
    from core.execution_prices import load_verified_execution_data
    from core.mt_bicl_v4_data import NUMERIC, bounded_index, symbol_data
    from core.mt_bicl_v4_data_regimes import DataRegimes
    from core.mt_bicl_v4_dataset import fold_views, train_views
    from core.mt_bicl_v4_protocol import git, read
    from core.mt_bicl_v41_bank import coverage, select_panel
    from core.mt_bicl_v41_data import core_valid, fit_scaler, membership

    receipts = {}
    for name in ('protocol_v4.json', 'protocol_v4_1.json', 'dataset_manifest_v4.json',
                 'dataset_manifest_v4_1.json', 'panel_manifest_v4_1.json',
                 'collection_release_v4_1.json', 'data_completion_release_v4.json'):
        relative = 'docs/plan/week11/' + name
        raw = (root / relative).read_bytes()
        if raw != git(root, 'show', 'HEAD:' + relative):
            raise ValueError('Receipt phục hồi khác Git: ' + relative)
        receipts[name] = read(raw)
    parent = receipts['dataset_manifest_v4.json']
    bank = receipts['dataset_manifest_v4_1.json']
    for manifest in (parent, bank):
        for name, expected in manifest['source_sha256'].items():
            if sha256((root / name).read_bytes()) != expected:
                raise ValueError('Source dựng dữ liệu khác bản đã khóa: ' + name)
    for name, expected in parent['source_input_sha256'].items():
        if sha256((root / name).read_bytes()) != expected:
            raise ValueError('Nguồn giá gốc khác manifest: ' + name)

    history = bounded_index(root / 'data/historical/VNINDEX.csv', '2022-12-31')
    rows, labels = [], {}
    spec = receipts['protocol_v4.json']
    for symbol in spec['data']['symbols']:
        frame, events = load_verified_execution_data(root / 'data/execution_prices', symbol)
        actual_rows, actual_labels = symbol_data(symbol, frame, events, history)
        rows.extend(actual_rows)
        labels.update(actual_labels)
        print(f'Phục hồi {symbol}: {len(actual_rows)} query từ giá gốc; không API.', flush=True)
    rows.sort(key=lambda r: (r['as_of_date'], spec['data']['symbols'].index(r['symbol'])))
    restored: dict[str, str] = {}
    failures: dict[str, str] = {}

    def install(name: str, raw: bytes, expected: str) -> None:
        """Ghi kết quả từng file; hash không khớp chỉ báo thiếu, không tự đổi receipt."""
        try:
            restored[name] = restore_exact(root, name, raw, expected)
        except ValueError as error:
            failures[name] = str(error)

    old = 'outputs/bayesian_benchmark/mt_bicl_v4/data/'
    new = 'outputs/bayesian_benchmark/mt_bicl_v4_1/data/'
    for prefix, manifest in ((old, parent), (new, bank)):
        install(prefix + 'labels.json', encoded(labels), manifest['artifact_sha256'][prefix + 'labels.json'])
    observations = {'feature_columns': list(NUMERIC), 'schema': 'NUMERIC9_MASK9_REGIME_ONLY_NO_AGENT_OR_A0', 'rows': rows}
    install(new + 'observations.json', encoded(observations), bank['artifact_sha256'][new + 'observations.json'])
    release = receipts['collection_release_v4_1.json']
    acquisition = receipts['data_completion_release_v4.json']
    from core.historical_signals import disk_articles
    for symbol in spec['data']['symbols']:
        name = f'outputs/historical_memory_run/inputs/news/{symbol}.json'
        value = {'symbol': symbol, 'scored_articles': disk_articles(root, symbol)}
        # Publisher cũ ghi text mode trên Windows; hash cũ phân biệt CRLF và LF.
        install(name, encoded(value).replace(b'\n', b'\r\n'), acquisition['news_sha256'][name])
    warmup = 'outputs/bayesian_benchmark/mt_bicl_v4/data_completion/warmup_verified.json'
    # Seal này được nhúng nguyên nội dung trong release; raw nguồn vẫn phải có riêng.
    install(warmup, encoded(release['warmup_verified']),
            'fd4e649ed3ebe3b52bd0b03f9a2be15aa42a2977049e80b5595081e0a2b93cc4')

    with tempfile.TemporaryDirectory(prefix='mt_bicl_exact_rebuild_') as temporary:
        directory = Path(temporary)
        class CandidateRegimes(DataRegimes):
            """Thử tái dựng proof cũ; toàn bộ artifact phải trùng hash trước khi cài."""

            def classify(self, as_of: str, fit_cutoff: str) -> dict[str, Any]:
                """Khôi phục ID model đã biết; không công nhận model mới là model gốc."""
                state = super().classify(as_of, fit_cutoff)
                name = old + 'regime_models/' + fit_cutoff + '.json'
                if state['model_sha256'] is not None:
                    state['model_sha256'] = parent['artifact_sha256'][name]
                return state

        regimes = CandidateRegimes(history, directory / 'regime_models')
        # Reuse các model đã phục hồi đúng byte; fit lại chỉ tạo ứng viên trong staging.
        for name, expected in parent['artifact_sha256'].items():
            if '/regime_models/' in name and (root / name).is_file():
                raw = (root / name).read_bytes()
                if sha256(raw) != expected:
                    raise ValueError('Model hiện có khác manifest: ' + name)
                target = directory / 'regime_models' / Path(name).name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
        old_folds = fold_views(rows, spec, regimes)
        old_train = train_views(rows, regimes)
        for name, value in {'folds.json': old_folds, 'train_prefixes.json': old_train,
                            'regime_registry.json': regimes.records}.items():
            install(old + name, encoded(value), parent['artifact_sha256'][old + name])
        for path in sorted((directory / 'regime_models').glob('*.json')):
            name = old + 'regime_models/' + path.name
            install(name, path.read_bytes(), parent['artifact_sha256'][name])
        # Dẫn xuất chỉ được cài khi toàn bộ byte khớp hash cũ, kể cả proof model.
        if old + 'folds.json' not in failures and old + 'train_prefixes.json' not in failures:
            folds = {}
            by_id = {r['episode_id']: r for r in rows}
            for name, fold in old_folds.items():
                scaler = fit_scaler(rows, fold['fit_end'])
                folds[name] = {k: deepcopy(fold[k]) for k in
                    ('fit_end', 'evaluation_start', 'evaluation_end', 'evaluation_ids', 'regimes')}
                folds[name].update(scaler=scaler, fit_ids=[i for i in fold['fit_ids'] if core_valid(by_id[i])],
                    memberships=[membership(by_id[i], rows, scaler, fold['regimes']) for i in fold['evaluation_ids']])
            scalers, members = {}, []
            for row in rows:
                if row['as_of_date'] > '2020-12-31':
                    continue
                query = row['as_of_date']
                if query not in scalers:
                    cap = (date.fromisoformat(query) - timedelta(days=1)).isoformat()
                    scalers[query] = fit_scaler(rows, cap, query=query)
                members.append(membership(row, rows, scalers[query], old_train['regimes']))
            values = {'folds.json': folds,
                'train_prefixes.json': {'scalers_by_query_date': scalers, 'memberships': members, 'regimes': old_train['regimes']},
                'coverage.json': coverage(rows, folds, receipts['protocol_v4_1.json'])}
            for name, value in values.items():
                install(new + name, encoded(value), bank['artifact_sha256'][new + name])
            panel_path = 'docs/plan/week11/panel_manifest_v4_1.json'
            install(panel_path, encoded(select_panel(rows, old_folds)), release['panel_sha256'])

    required = {**parent['artifact_sha256'], **bank['artifact_sha256'], **parent['agent_input_sha256'],
                **spec['parent_sha256'], **spec['input_sha256']}
    required.update(acquisition['news_sha256'])
    required.update({v['path']: v['sha256'] for v in release['warmup_verified']['symbols'].values()})
    ledger_path = root / 'outputs/oos_pilot/api_usage.json'
    ledger_sha = sha256(ledger_path.read_bytes())
    ledger = read(ledger_path.read_bytes())
    release_sha = sha256((root / 'docs/plan/week11/collection_release_v4_1.json').read_bytes())
    raw_paths = {}
    for row in ledger['requests']:
        if row.get('operational_amendment_sha256') == release_sha and row.get('durable_response'):
            name = f"outputs/bayesian_benchmark/mt_bicl_v4_1/collection/http_cache/{row['id']}.json"
            raw_paths[name] = row['durable_response']['sha256']
    required.update(raw_paths)
    missing = [name for name in required if not (root / name).is_file()]
    mismatched = [name for name, expected in required.items()
                  if (root / name).is_file() and sha256((root / name).read_bytes()) != expected]
    return {'version': 'mt_bicl_exact_runtime_recovery', 'status': 'RESTORED' if not missing and not mismatched and not failures else 'PARTIAL_RECOVERY',
            'restored': restored, 'rebuild_failures': failures, 'missing': missing, 'mismatched': mismatched,
            'sealed_raw_cache_missing': [name for name in raw_paths if name in missing],
            'ledger_sha256': ledger_sha, 'ledger_requests': len(ledger['requests']),
            'API_calls': 0, 'runtime_ready': not missing and not mismatched and not failures,
            'scientific_receipts_modified': False, 'ledger_modified': False}


def reject_network(*args: Any, **kwargs: Any) -> Any:
    """Chặn mạng trong toàn bộ thao tác phục hồi offline."""
    raise RuntimeError('Phục hồi offline không được gọi mạng')


def main() -> int:
    """Một lệnh phục hồi chính xác, xuất JSON phần còn thiếu mà không giả PASS."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, default=Path('outputs/recovery_20261101/reconstruction.json'))
    args = parser.parse_args()
    socket.create_connection = reject_network
    socket.socket.connect = reject_network
    result = recover(ROOT)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_bytes(encoded(result))
    print(f"Phục hồi: {result['status']}; kiểm/cài {len(result['restored'])} file đúng SHA-256; còn thiếu {len(result['missing'])} file. Báo cáo: {args.report}")
    return 0 if result['runtime_ready'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
