"""Khóa/phát hành release và oracle thứ tự/alias trước Decision, hoàn toàn offline."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from bic_icl_release_support import ReleaseFixture
from core.bic_icl_protocol import read_authorization
from core.bic_icl_release import issue_development_release, verify_development_release, request_manifest
from core.research_cohort import read_envelope
from scripts.prepare_bic_icl_release import main as release_main


class DevelopmentReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.silence = patch('builtins.print')
        self.silence.start()
        self.addCleanup(self.silence.stop)
        self.fx = ReleaseFixture()
        self.addCleanup(self.fx.close)
        for item in self.fx.patches():
            item.start()
            self.addCleanup(item.stop)

    def issue(self):
        return issue_development_release(self.fx.path, self.fx.gates, self.fx.plan, self.fx.sources,
            self.fx.root, ledger_path=self.fx.ledger)

    def test_release_locks_real_files_and_consumer_without_sdk_invocation(self):
        payload = self.issue()
        self.assertEqual(len(payload['snapshot_sha256']), 15)
        self.assertFalse(payload['confirmation_allowed'])
        self.assertEqual(read_envelope(self.fx.root/'request_manifest.json'), self.fx.manifest)
        auth = read_authorization(self.fx.path, self.fx.gates, self.fx.plan,
            run_root=self.fx.root, ledger_path=self.fx.ledger)
        auth.verify(self.fx.plan, run_root=self.fx.root, ledger_path=self.fx.ledger)
        copied = auth.payload
        copied['confirmation_allowed'] = True
        self.assertFalse(auth.payload['confirmation_allowed'])
        self.assertFalse(self.fx.cohort.sdk.requests)
        self.assertFalse((self.fx.root/'decision_blocks').exists())
        self.assertFalse((self.fx.root/'primary_ready.json').exists())

    def test_reissue_and_verify_preserve_all_scientific_bytes_and_timestamps(self):
        expected = self.issue()
        paths = [self.fx.path, *(self.fx.root/name for name in expected['snapshot_sha256'])]
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in paths}
        self.assertEqual(self.issue(), expected)
        self.assertEqual(verify_development_release(self.fx.path, self.fx.gates, self.fx.plan,
            run_root=self.fx.root, ledger_path=self.fx.ledger), expected)
        self.assertTrue(all((p.read_bytes(), p.stat().st_mtime_ns) == value for p, value in before.items()))

    def test_all_repeat_orders_match_independent_rotation_oracle(self):
        matrix = self.fx.lock['matrix']
        for block in self.fx.manifest['blocks']:
            r, j = block['repeat_id'], block['point_index']
            others = matrix[1:]+(['original_duplicate'] if r else [])
            shift = (3*j+r-1 if r else j) % len(others)
            self.assertEqual([s['branch_id'] for s in block['requests']],
                ['original', *others[shift:], *others[:shift]])
            if r:
                by_name = {s['branch_id']: s for s in block['requests']}
                self.assertEqual(by_name['original']['contract'], by_name['original_duplicate']['contract'])
                self.assertIsNone(by_name['original_duplicate']['source_branch'])
                self.assertEqual(by_name['original_duplicate']['decision_origin'], 'independent_duplicate')
        self.assertEqual(len(self.fx.manifest['blocks']), 48)
        self.assertEqual(self.fx.manifest['logical_slots'], 420)
        self.assertLess(self.fx.manifest['independent_slots'], 420)

    def test_global_block_excludes_all_task_slots_before_repeat_rotation(self):
        lock = deepcopy(self.fx.lock)
        lock.update(task_enabled=False, matrix=[n for n in lock['matrix'] if not n.startswith('R_task_')])
        manifest = request_manifest(self.fx.plan, self.fx.packets, lock, self.fx.cohort.sdk.llm)
        self.assertFalse(any(s['branch_id'].startswith('R_task_') for b in manifest['blocks'] for s in b['requests']))
        self.assertEqual(manifest['logical_slots'], 276)

    def test_consumer_snapshot_remains_valid_when_ledger_grows(self):
        self.issue()
        auth = read_authorization(self.fx.path, self.fx.gates, self.fx.plan)
        self.fx.ledger.write_text('{"requests": []}', encoding='utf8')
        auth.verify(self.fx.plan)
        self.assertEqual(auth.payload['run_binding']['ledger_path'], str(self.fx.ledger.resolve()))

    def test_release_cli_default_verifies_without_issuing_or_reading_environment(self):
        from core.research_input_lock import _write_once
        self.issue()
        plan_path = self.fx.base/'development_plan_fixture.json'
        _write_once(plan_path, self.fx.plan)
        with patch('scripts.prepare_bic_icl_release.issue_development_release',
                side_effect=AssertionError('Verify không phát hành')), patch(
                'dotenv.dotenv_values', side_effect=AssertionError('Offline không đọc key')):
            release_main(['--plan', str(plan_path), '--output-dir', str(self.fx.root),
                '--release', str(self.fx.path), '--technical-gates', str(self.fx.gates),
                '--ledger', str(self.fx.ledger)])
        self.assertFalse(self.fx.cohort.sdk.requests)


if __name__ == '__main__':
    unittest.main()
