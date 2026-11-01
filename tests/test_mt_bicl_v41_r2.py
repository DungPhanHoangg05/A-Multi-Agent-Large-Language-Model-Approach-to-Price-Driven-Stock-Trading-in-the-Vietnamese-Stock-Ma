"""Kiểm lineage r2, warmup append-only, quyền collection và cửa downstream fail-closed."""

from contextlib import redirect_stdout
from copy import deepcopy
import io
from pathlib import Path
import platform
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from core.mt_bicl_v4_completion import DataCompletionError
from core.mt_bicl_v4_dataset import encoded, immutable
from core.mt_bicl_v4_protocol import canonical, checksum
from core.mt_bicl_v4_warmup import PendingWarmup
from core.mt_bicl_v41_r2_data import compare_numeric, original_proofs
from core.mt_bicl_v41_r2_release import verify
from core.mt_bicl_v41_r2_warmup import COLLECTION, RELEASE, load
from test_mt_bicl_v4_completion import warmup_fixture


def release_fixture(root: Path) -> tuple:
    """Receipt tối thiểu xác định để kiểm verifier, không phụ thuộc dữ liệu bị mất."""
    ids = [f'FPT-fixture-{i:03d}' for i in range(256)]
    panel = {'point_ids': ids, 'shards': {f'scope_{i+1}': ids[i::4] for i in range(4)}}
    old = {'config': {'fixture': 'same-model-options'}, 'warmup': {'fixture': 'same-window'}, 'dependency_sha256': {}}
    files = {'source.py': b'# fixture\n', 'data.json': b'{}\n', 'news.json': b'{}\n', 'old/evidence.json': b'preserved\n'}
    for name, raw in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(raw)
    bank = {'status': 'NUMERIC_BANK_PASS', 'artifact_sha256': {'data.json': checksum(files['data.json'])}}
    rows = [{'id': 'old-reserve-fixture', 'status': 200}]
    immutable(root / 'outputs/oos_pilot/api_usage.json', {'requests': rows})
    release = {'version': 'conditional_v4_1_r2_collection_release', 'status': 'USER_COLLECTION_RELEASED',
        'scope': 'PANEL256_ORIGINAL_UPSTREAM_ONLY_2019_2022', 'runtime_namespace': COLLECTION.parent.as_posix(),
        'collection_operator': 'USER_ONLY', 'source_commit': 'fixture-commit',
        'source_sha256': {'source.py': checksum(files['source.py'])}, 'receipt_sha256': {},
        'source_git_blob_sha256': {'source.py': checksum(files['source.py'])},
        'numeric_artifact_sha256': bank['artifact_sha256'], 'input_sha256': {},
        'news_sha256': {'news.json': checksum(files['news.json'])}, 'config': old['config'], 'warmup': old['warmup'],
        'point_ids': ids, 'shards': panel['shards'], 'nominal_research_HTTP': 768, 'controls_per_scope': 3,
        'hour_cap': None, 'calendar_deadline': None,
        'historical_evidence': {'surviving_evidence_sha256': {'old/evidence.json': checksum(files['old/evidence.json'])}},
        'runtime': {'python': platform.python_version(), 'platform': platform.system(), 'packages': {}}, 'acquisition_runtime': {},
        'ledger_baseline': {'count': 1, 'requests_prefix_sha256': checksum(canonical(rows))},
        **{k: False for k in ('training_allowed', 'reference_fit_allowed', 'development_allowed', 'confirmation_allowed')}}

    def receipt(actual_root, name):
        """Các receipt cũ chỉ là anchor, không gọi gate lịch sử đang thiếu file."""
        return {RELEASE.name: release, 'collection_release_v4_1.json': old,
                'dataset_manifest_v4_1_r2.json': bank, 'panel_manifest_v4_1.json': panel}[name]

    def git(actual_root, *args):
        """Source Git phải đúng byte; truy vấn ancestor không thay đổi file."""
        return files['source.py'] if args[0] == 'show' else b''

    return release, receipt, git


class ReplacementTests(unittest.TestCase):
    """Mất lịch sử không được biến thành PASS cũ hoặc nới hợp đồng nghiên cứu."""

    def test_numeric_equivalence_allows_only_model_proof_identity(self) -> None:
        value = {'regimes': {'id': {'query_proof': {'fit_end': '2020-12-31', 'model_sha256': 'new'}, 'query_name': 'BULL'}},
                 'memberships': [{'prior': ['same-id'], 'K': 1}], 'scaler': {'mean': [1.]}}
        mapping = {'2020-12-31': 'old'}
        before = deepcopy(value)
        expected = original_proofs(value, mapping)
        parent = {'artifact_sha256': {'outputs/bayesian_benchmark/mt_bicl_v4_1/data/folds.json': checksum(encoded(expected))}}
        compare_numeric({'folds.json': value}, parent, mapping)
        self.assertEqual(value, before)
        for change in ('regime', 'membership', 'scaler'):
            altered = deepcopy(value)
            if change == 'regime':
                altered['regimes']['id']['query_name'] = 'BEAR'
            elif change == 'membership':
                altered['memberships'][0]['prior'] = ['different-id']
            else:
                altered['scaler']['mean'] = [2.]
            with self.subTest(change=change), self.assertRaises(ValueError):
                compare_numeric({'folds.json': altered}, parent, mapping)

    def test_warmup_fetch_then_resume_uses_only_new_namespace(self) -> None:
        records, base, settings = warmup_fixture()
        release = {'config': {'symbol_order': ['FPT']}, 'warmup': settings}
        with TemporaryDirectory() as temporary, redirect_stdout(io.StringIO()):
            root = Path(temporary)
            with patch('core.mt_bicl_v41_r2_warmup.load_verified_execution_data', return_value=(base, [])):
                with self.assertRaises(PendingWarmup):
                    load(root, release)
                frames, ready = load(root, release, fetch=lambda *_: (records, [{'fixture': True}]))
                with patch('socket.socket.connect', side_effect=AssertionError('Không network')):
                    replay, receipt = load(root, release, fetch=lambda *_: self.fail('Không tải lại'))
                self.assertEqual(ready, receipt)
                self.assertTrue(frames['FPT'].equals(replay['FPT']))
                self.assertFalse((root / 'outputs/bayesian_benchmark/mt_bicl_v4/data_completion').exists())
                self.assertFalse(ready['pre2018_labels_created'])

    def test_warmup_sealed_raw_loss_cannot_trigger_fetch(self) -> None:
        records, base, settings = warmup_fixture()
        release = {'config': {'symbol_order': ['FPT']}, 'warmup': settings}
        with TemporaryDirectory() as temporary, redirect_stdout(io.StringIO()):
            root = Path(temporary)
            with patch('core.mt_bicl_v41_r2_warmup.load_verified_execution_data', return_value=(base, [])):
                load(root, release, fetch=lambda *_: (records, []))
                (root / COLLECTION / 'warmup/FPT.json').unlink()
                with self.assertRaisesRegex(DataCompletionError, 'seal'):
                    load(root, release, fetch=lambda *_: self.fail('Không thay raw đã seal'))

    def test_warmup_overlap_mismatch_stops_before_sealing(self) -> None:
        records, base, settings = warmup_fixture()
        release = {'config': {'symbol_order': ['FPT']}, 'warmup': settings}
        wrong = base.copy(deep=True)
        wrong['Close'] *= 2
        with TemporaryDirectory() as temporary, redirect_stdout(io.StringIO()):
            root = Path(temporary)
            with patch('core.mt_bicl_v41_r2_warmup.load_verified_execution_data', return_value=(wrong, [])):
                with self.assertRaises(DataCompletionError):
                    load(root, release, fetch=lambda *_: (records, []))
            self.assertFalse((root / COLLECTION / 'warmup/FPT.json').exists())

    def test_partial_warmup_resumes_without_refetching_first_symbol(self) -> None:
        records, base, settings = warmup_fixture()
        release = {'config': {'symbol_order': ['FPT', 'MWG']}, 'warmup': settings}
        calls = []

        def fetch(url, params):
            """Ngắt giữa hai mã, không tạo nguồn giả cho mã chưa tải."""
            calls.append(url)
            if len(calls) == 2:
                raise KeyboardInterrupt()
            return records, []

        with TemporaryDirectory() as temporary, redirect_stdout(io.StringIO()):
            root = Path(temporary)
            with patch('core.mt_bicl_v41_r2_warmup.load_verified_execution_data', return_value=(base, [])), self.assertRaises(KeyboardInterrupt):
                load(root, release, fetch=fetch)
            self.assertTrue((root / COLLECTION / 'warmup/FPT.json').exists())
            self.assertFalse((root / COLLECTION / 'warmup_verified.json').exists())
            resumed_calls = []

            def resume_fetch(url, params):
                """Chỉ mã thứ hai được tải; giữ nguyên byte raw mã thứ nhất."""
                resumed_calls.append(url)
                return [{**r, 'ticker': 'MWG'} for r in records], []

            before = (root / COLLECTION / 'warmup/FPT.json').read_bytes()
            with patch('core.mt_bicl_v41_r2_warmup.load_verified_execution_data', return_value=(base, [])):
                _, ready = load(root, release, fetch=resume_fetch)
            self.assertEqual(len(resumed_calls), 1)
            self.assertIn('/MWG/', resumed_calls[0])
            self.assertEqual(set(ready['symbols']), {'FPT', 'MWG'})
            self.assertEqual((root / COLLECTION / 'warmup/FPT.json').read_bytes(), before)

    def test_release_is_independent_of_missing_historical_parents(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            release, receipt, git = release_fixture(root)
            with patch('core.mt_bicl_v41_r2_release.pinned', side_effect=receipt), \
                 patch('core.mt_bicl_v41_r2_release.git', side_effect=git), \
                 patch('core.mt_bicl_v41_r2_release.SOURCES', ('source.py',)):
                self.assertEqual(verify(root), release)
                for key in ('training_allowed', 'reference_fit_allowed', 'development_allowed', 'confirmation_allowed'):
                    release[key] = True
                    with self.subTest(key=key), self.assertRaises(ValueError):
                        verify(root)
                    release[key] = False
                release['config'] = {'silent-model-change': True}
                with self.assertRaises(ValueError):
                    verify(root)

    def test_changed_source_news_old_evidence_or_ledger_fail_closed(self) -> None:
        for name in ('source.py', 'news.json', 'old/evidence.json', 'outputs/oos_pilot/api_usage.json'):
            with self.subTest(name=name), TemporaryDirectory() as temporary:
                root = Path(temporary)
                _, receipt, git = release_fixture(root)
                (root / name).write_bytes(b'{"changed":true}\n')
                with patch('core.mt_bicl_v41_r2_release.pinned', side_effect=receipt), \
                     patch('core.mt_bicl_v41_r2_release.git', side_effect=git), \
                     patch('core.mt_bicl_v41_r2_release.SOURCES', ('source.py',)), self.assertRaises((ValueError, KeyError)):
                    verify(root)

    def test_source_working_bytes_and_git_blob_are_both_pinned(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            release, receipt, git = release_fixture(root)
            raw = b'# fixture\r\n'
            (root / 'source.py').write_bytes(raw)
            release['source_sha256']['source.py'] = checksum(raw)
            with patch('core.mt_bicl_v41_r2_release.pinned', side_effect=receipt), \
                 patch('core.mt_bicl_v41_r2_release.git', side_effect=git), \
                 patch('core.mt_bicl_v41_r2_release.SOURCES', ('source.py',)):
                self.assertEqual(verify(root), release)
                release['source_git_blob_sha256']['source.py'] = 'f' * 64
                with self.assertRaises(ValueError):
                    verify(root)

    def test_acceptance_and_downstream_stay_closed_before_collection(self) -> None:
        from core.mt_bicl_v41_r2_acceptance import accept
        from core.mt_bicl_v41_r2_contract import load_ready
        release = {'point_ids': [str(i) for i in range(256)]}
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch('core.mt_bicl_v41_r2_acceptance.verify', return_value=release):
                result = accept(root)
                self.assertEqual(result['status'], 'INCOMPLETE_PANEL')
                self.assertEqual(result['remaining'], 256)
            with patch('core.mt_bicl_v41_r2_contract.verify', return_value=release), self.assertRaisesRegex(ValueError, 'chưa cold'):
                load_ready(root)

    def test_external_backup_whitelist_excludes_env_and_preserves_raw(self) -> None:
        from core.mt_bicl_v41_r2_backup import checkpoint
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / 'project'
            root.mkdir()
            destination = Path(temporary) / 'external'
            raw_path = COLLECTION / 'http_cache/fixture.json'
            immutable(root / raw_path, {'durable': True})
            immutable(root / 'outputs/oos_pilot/api_usage.json', {'requests': []})
            (root / '.env').write_bytes(b'FIXTURE_SECRET_DO_NOT_COPY')
            release = {'input_sha256': {}, 'news_sha256': {}, 'numeric_artifact_sha256': {}, 'receipt_sha256': {},
                       'historical_evidence': {'surviving_evidence_sha256': {}}}
            immutable(root / RELEASE, release)
            checkpoint(root, destination)
            self.assertFalse((destination / '.env').exists())
            self.assertEqual((destination / raw_path).read_bytes(), (root / raw_path).read_bytes())
            original = (destination / raw_path).read_bytes()
            (destination / raw_path).write_bytes(b'corrupted-backup')
            with self.assertRaisesRegex(ValueError, 'immutable'):
                checkpoint(root, destination)
            self.assertEqual((root / raw_path).read_bytes(), original)
            self.assertEqual((destination / raw_path).read_bytes(), b'corrupted-backup')

    def test_atomic_backup_write_failure_keeps_previous_copy(self) -> None:
        from core.mt_bicl_v41_r2_backup import write_atomic
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / 'ledger.json'
            path.write_bytes(b'previous')
            with patch('core.mt_bicl_v41_r2_backup.os.replace', side_effect=OSError('fixture')), self.assertRaises(OSError):
                write_atomic(path, b'next')
            self.assertEqual(path.read_bytes(), b'previous')
            self.assertEqual(len(list(path.parent.iterdir())), 1)

    def test_complete_acceptance_binds_new_release_shards_and_downstream(self) -> None:
        from core.mt_bicl_v41_r2_acceptance import ACCEPTANCE, accept
        from core.mt_bicl_v41_r2_contract import load_ready
        from core.mt_bicl_v41_r2_data import DATA, MANIFEST, PANEL
        from core.mt_bicl_v4_protocol import read
        with TemporaryDirectory() as temporary, redirect_stdout(io.StringIO()):
            root = Path(temporary)
            ids = [f'FPT-2020-fixture-{i:03d}' for i in range(256)]
            shards = {f'scope_{i+1}': ids[i::4] for i in range(4)}
            mapping = {name: 'fixture-credential-' + name for name in shards}
            release = {'point_ids': ids, 'shards': shards, 'config': {'symbol_order': ['FPT']}}
            immutable(root / RELEASE, release)
            immutable(root / MANIFEST, {'fixture': True})
            immutable(root / PANEL, {'point_ids': ids})
            immutable(root / DATA / 'observations.json', {'rows': [{'episode_id': pid, 'symbol': 'FPT'} for pid in ids]})
            immutable(root / DATA / 'folds.json', {})
            immutable(root / 'outputs/historical_memory_run/inputs/news/FPT.json', {'scored_articles': []})
            for name in ('warmup_verified.json', 'identity.json'):
                immutable(root / COLLECTION / name, {'fixture': True})
            rows = [{'id': pid, 'credential_scope': mapping[next(n for n, selected in shards.items() if pid in selected)],
                     'operational_amendment_sha256': checksum((root / RELEASE).read_bytes())} for pid in ids]
            immutable(root / 'outputs/oos_pilot/api_usage.json', {'requests': rows})

            def cold(actual_root, row, *args, **kwargs):
                """Plumbing256; cold graph/SDK thật được kiểm riêng trong CoordinatorTests."""
                record = {'original': {'decision': 'LONG'}, 'http': {'http_rows_sha256': {row['episode_id']: 'fixture'}}, 'files_sha256': {}}
                immutable(root / COLLECTION / 'points' / row['episode_id'] / 'complete.json', record)
                return record

            # Tạo complete để mở cold; nội dung thực tế sau đó vẫn phải qua cold callback.
            for pid in ids:
                cold(root, {'episode_id': pid})
            with patch('core.mt_bicl_v41_r2_acceptance.verify', return_value=release), \
                 patch('core.mt_bicl_v41_r2_acceptance.build', return_value={'status': 'NUMERIC_BANK_PASS'}), \
                 patch('core.mt_bicl_v41_r2_acceptance.identity', return_value=({'FPT': object()}, {'symbols': {}}, 'b'*64)), \
                 patch('core.mt_bicl_v41_r2_acceptance.read_bindings', return_value=[mapping]), \
                 patch('core.mt_bicl_v41_r2_acceptance.cold_point', side_effect=cold) as replay, \
                 patch('core.mt_bicl_v41_r2_acceptance.clients'), patch('core.mt_bicl_v41_r2_acceptance.controls'):
                result = accept(root)
                self.assertEqual(replay.call_count, 256)
                self.assertTrue(result['ready_for_W11_19'])
                self.assertEqual(result['unique_points'], 256)
                rows[0]['credential_scope'] = 'wrong-shard-credential'
                (root / 'outputs/oos_pilot/api_usage.json').write_bytes(encoded({'requests': rows}))
                with self.assertRaisesRegex(ValueError, 'shard/scope'):
                    accept(root)
            # Consumer chỉ đọc acceptance r2 đã neo; source/receipt anchor được kiểm ở verifier riêng.
            def pinned(actual_root, name):
                return {} if name == 'protocol_v4_1.json' else read((root / 'docs/plan/week11' / name).read_bytes())
            rows[0]['credential_scope'] = mapping['scope_1']
            (root / 'outputs/oos_pilot/api_usage.json').write_bytes(encoded({'requests': rows}))
            with patch('core.mt_bicl_v41_r2_contract.verify', return_value=release), \
                 patch('core.mt_bicl_v41_r2_contract.pinned', side_effect=pinned):
                ready = load_ready(root)
                self.assertEqual(len(ready['originals']), 256)
                self.assertEqual(ready['protocol']['namespace'], COLLECTION.parent.as_posix())


if __name__ == '__main__':
    unittest.main()
