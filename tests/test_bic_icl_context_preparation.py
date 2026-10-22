"""Nguồn W10-04 bị sửa/code drift không được dùng để render revision mới."""

from pathlib import Path
import hashlib
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from core.bic_icl_memory import METHOD_SHA
from core.historical_signals import digest
from core.research_cohort import read_envelope, save_envelope
from scripts.prepare_bic_icl_context import FrozenPreparation, prepare, summarize_coverage
from bic_icl_tasks_support import TaskFixture


class ContextPreparationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.namespace = self.root/'outputs/bayesian_benchmark/bic_icl_v2'
        self.raw = self.root/'source.dat'
        self.raw.write_bytes(b'nguon-fixture')
        fx = TaskFixture()
        sources = {'source.dat': hashlib.sha256(self.raw.read_bytes()).hexdigest()}
        self.code, self.runtime = {'code': 'a'*64}, {'python': 'fixture'}
        objects = {'memory': {'memory.json': {**fx.memory.payload, 'source_hashes': sources}, 'index.json': fx.index.payload},
                   'train': {'diagnostics.json': {'source_hashes': sources, 'summary': {
                       'selected_lambda': 8, 'status': 'LOCKED_TRAIN_SELECTION'}}}}
        for kind, values in objects.items():
            values['receipt.json'] = {'version': 'bic_icl_preparation_v1', 'kind': kind,
                'method_sha256': METHOD_SHA, 'code_sha256': self.code, 'runtime': self.runtime,
                'outputs': {name: digest(value) for name, value in values.items()}}
            for name, value in values.items():
                save_envelope(self.namespace/f'{kind}_v1'/name, value)
        archive = self.root/'proof.zip'
        with zipfile.ZipFile(archive, 'w') as z:
            for path in self.namespace.rglob('*.json'):
                z.write(path, path.relative_to(self.root).as_posix())
        for name, value in (('ROOT', self.root), ('NAMESPACE', self.namespace), ('PREPARATION', archive.name),
                ('PREPARATION_SHA', hashlib.sha256(archive.read_bytes()).hexdigest()), ('verify_method', lambda: None),
                ('memory_code_identity', lambda: self.code), ('runtime_identity', lambda: self.runtime)):
            context = patch('scripts.prepare_bic_icl_context.'+name, value)
            context.start()
            self.addCleanup(context.stop)

    def test_accepted_snapshot_keeps_selected_lambda_and_verified_source(self) -> None:
        frozen = FrozenPreparation()
        self.assertEqual(frozen.strength, 8)
        self.assertEqual(len(frozen.memory.records), 44)
        frozen.verify()

    def test_rehashed_memory_receipt_or_train_cannot_replace_frozen_bytes(self) -> None:
        for relative in ('memory_v1/memory.json', 'memory_v1/receipt.json', 'train_v1/diagnostics.json'):
            path = self.namespace/relative
            old = path.read_bytes()
            value = read_envelope(path)
            value['forged'] = True
            save_envelope(path, value)
            with self.subTest(path=relative), self.assertRaises(ValueError):
                FrozenPreparation()
            path.write_bytes(old)

    def test_code_runtime_and_source_drift_fail_before_context_producer(self) -> None:
        frozen = FrozenPreparation()
        self.raw.write_bytes(b'nguon-khac')
        with self.assertRaises(ValueError):
            frozen.verify()
        with self.assertRaises(ValueError):
            FrozenPreparation()
        self.raw.write_bytes(b'nguon-fixture')
        self.code = {'code': 'b'*64}
        with self.assertRaises(ValueError):
            FrozenPreparation()
        self.code = {'code': 'a'*64}
        self.runtime = {'python': 'khac'}
        with self.assertRaises(ValueError):
            FrozenPreparation()

    def test_namespace_protects_memory_train_and_other_frozen_directories(self) -> None:
        with patch('scripts.prepare_bic_icl_context.build_preflight', side_effect=AssertionError('Không đọc nguồn')):
            for path in (self.namespace, self.namespace/'memory_v1', self.namespace/'train_v1',
                         self.namespace/'protocol_v1', self.root/'context_outside'):
                with self.assertRaises(ValueError):
                    prepare(path)

    def test_nomination_coverage_counts_visible_tasks_not_hidden_selection(self) -> None:
        row = {'point_id': 'FPT-2023-01-06', 'evidence': {'gate': {'R_task': {
            'stats_ready': True, 'examples_ready': False}}, 'task_selection': {'metadata': {'k_tasks': 3}}}}
        result = summarize_coverage([row])
        self.assertEqual(result['FPT']['raw_at_least_two_tasks'], 1)
        self.assertEqual(result['FPT']['at_least_two_tasks'], 0)
        self.assertEqual(result['FPT']['prior_visible'], 1)
        row['evidence']['gate']['R_task']['examples_ready'] = True
        self.assertEqual(summarize_coverage([row])['FPT']['at_least_two_tasks'], 1)


if __name__ == '__main__':
    unittest.main()
