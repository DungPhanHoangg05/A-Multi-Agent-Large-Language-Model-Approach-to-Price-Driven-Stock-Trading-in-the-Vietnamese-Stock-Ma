"""Biên CLI offline: namespace, artifact bất biến và verify semantic/code/runtime."""

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from core.research_cohort import read_envelope, save_envelope
from scripts.prepare_bic_icl_memory import prepare


class OfflinePreparationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.namespace = self.root/'bic_icl_v2'
        self.output = self.namespace/'train_v1'
        self.report = {'report_version': 'fixture', 'summary': {'selected_lambda': 8}}
        self.sources = SimpleNamespace(verify=lambda: None)
        for name, value in (('NAMESPACE', self.namespace), ('component_identity', lambda: {'code': 'a'*64}),
                ('runtime_identity', lambda: {'python': 'fixture'}), ('FrozenSources', lambda: self.sources),
                ('build_train_diagnostics', lambda *a, **k: deepcopy(self.report))):
            context = patch(f'scripts.prepare_bic_icl_memory.{name}', value)
            context.start()
            self.addCleanup(context.stop)

    def test_build_verify_replay_is_read_only_and_rejects_rehashed_output(self) -> None:
        result = prepare(self.output, kind='train')
        self.assertEqual(result['status'], 'PREPARED')
        before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.output.iterdir()}
        self.assertEqual(prepare(self.output, kind='train', verify_only=True)['status'], 'VERIFIED')
        self.assertEqual(before, {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.output.iterdir()})
        save_envelope(self.output/'diagnostics.json', {'report_version': 'forged'})
        with self.assertRaises(ValueError):
            prepare(self.output, kind='train', verify_only=True)

    def test_wrong_namespace_and_kind_stop_before_reading_sources(self) -> None:
        with patch('scripts.prepare_bic_icl_memory.FrozenSources', side_effect=AssertionError('Không đọc nguồn')):
            for path in (self.namespace, self.root/'other', self.namespace/'..'/'other'):
                with self.assertRaises(ValueError):
                    prepare(path, kind='train')
            with self.assertRaises(ValueError):
                prepare(self.output, kind='decision')

    def test_changed_code_or_loss_cannot_overwrite_frozen_artifact(self) -> None:
        prepare(self.output, kind='train')
        with patch('scripts.prepare_bic_icl_memory.component_identity', return_value={'code': 'b'*64}):
            with self.assertRaises(ValueError):
                prepare(self.output, kind='train', verify_only=True)
        self.report['summary']['selected_lambda'] = 2
        with self.assertRaises(ValueError):
            prepare(self.output, kind='train')
        self.assertEqual(read_envelope(self.output/'diagnostics.json')['summary']['selected_lambda'], 8)


if __name__ == '__main__':
    unittest.main()
