"""Manifest/runtime holdout production với nguồn thật dạng fixture và LLM offline."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from core.groq_pacing import PilotStop
from core.historical_signals import digest
from core.improvement_bootstrap import bootstrap_report
from core.improvement_holdout import _bound_files, prepare_plan, validate_plan, verified_development
from core.improvement_holdout_runtime import run_holdout
from core.improvement_protocol import prepare_plan as prepare_development
from core.improvement_recovery import recovery_scope
from core.improvement_reports import read_report, selection_artifact
from core.improvement_runtime import decision_path, run_primary
from core.research_cohort import read_envelope, save_envelope
from core.research_input_lock import _write_once
from scripts.run_improvement_holdout import main, release_artifact
from test_candidate_cohort import CandidateLlm, CandidateSetup


class ImprovementHoldoutTests(CandidateSetup, unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.builder.agent_llm = self.llm = CandidateLlm(structured=True)
        self.dev_path = self.fx.root/'improvement.json'
        self.dev = prepare_development(self.plan_path, self.dev_path, self.adapter)
        primary = run_primary(self.runner, self.dev, self.output)
        _write_once(self.output/'report.json', primary)
        _write_once(self.output/'selection.json', selection_artifact(primary, {'status': 'NOT_VERIFIED'},
            hashlib.sha256((self.output/'report.json').read_bytes()).hexdigest()))
        self.runner._holdout_fixture_run = self.output
        self.holdout_path = self.fx.root/'holdout.json'
        self.holdout = prepare_plan(self.holdout_path, self.adapter, fixture_plan=self.dev_path, fixture_runner=self.runner)
        self.holdout_run = self.fx.root/'holdout-run'
        # Prepare đã verify development fixture thật; các lượt sau tập trung consumer mới.
        fixture_proof = (self.dev, read_envelope(self.output/'selection.json'),
            {self.dev_path.relative_to(self.fx.root).as_posix(): hashlib.sha256(self.dev_path.read_bytes()).hexdigest()})
        fixture_reader = patch('core.improvement_holdout._fixture_development', return_value=fixture_proof)
        fixture_reader.start()
        self.addCleanup(fixture_reader.stop)

    def execute(self, **options):
        """Fixture đi đúng runtime holdout, không dispatch qua ma trận W7/development."""
        return run_holdout(self.runner, self.holdout, self.holdout_run,
            fixture_plan=self.dev_path, fixture_runner=self.runner, **options)

    def test_manifest_six_branches_immutable_rotation_shared_and_verified_resume(self) -> None:
        self.assertFalse(self.holdout_run.exists())
        self.assertEqual(self.holdout['selection_decision']['scope'], 'FIXTURE_PROTOCOL_ONLY')
        self.assertEqual(self.holdout['selection_decision']['nomination_status'], 'BLOCKED')
        self.assertEqual(self.holdout['statistics']['secondary_count'], 4)
        before = self.llm.calls
        report = self.execute()
        self.assertEqual(self.llm.calls-before, 24)
        self.assertEqual(self.events, ['indicator', 'pattern', 'trend', 'full']*8)
        self.assertEqual(self.llm.call_order[44:], [(row['point_id'], n) for row in self.holdout['schedule'] for n in row['branches']])
        self.assertEqual(report['primary_status'], 'COMPLETE')
        self.assertEqual(report['selection_evidence_status'], 'NOT_APPLICABLE')
        self.assertEqual(report['stocks']['FPT']['cash_reference']['long_count'], 0)
        self.assertEqual(report['stocks']['FPT']['cash_reference']['account_metrics']['total_return_pct'], 0.)
        for row in self.holdout['schedule']:
            docs = [read_envelope(decision_path(self.holdout_run, row['point_id'], n)) for n in self.holdout['matrix']]
            self.assertEqual(len({d['shared_sha256'] for d in docs}), 1)
            self.assertTrue(all(len(d['prompt']) < 6500 for d in docs))
            self.assertTrue(all(d['repeat_id'] == 0 and len(d['attempts']) == 1 for d in docs))
            self.assertTrue(all(not d['request'] or len(d['request']['prefix']) <= 600 for d in docs))
        _write_once(self.holdout_run/'report.json', report)
        self.assertEqual(self.execute(verify_only=True), report)
        self.assertEqual(self.execute(), report)
        self.assertEqual(self.llm.calls-before, 24)
        stats = bootstrap_report(self.holdout, report, 'f'*64)
        self.assertEqual(stats['status'], 'COMPLETE')
        self.assertEqual(stats['evidence_status'], 'FIXTURE_ONLY')
        self.assertAlmostEqual(stats['primary_point_estimate_pp'], 0., places=8)
        self.assertIsNone(report['stocks']['FPT']['time_groups']['Q4']['contrasts']['A_tp_pool__original']['delta_return_pp'])

    def test_resilient_unknown_same_uuid_no_extra_upstream_and_partial_not_cash(self) -> None:
        before = self.llm.calls; original = self.llm.structured_call
        def fail(prompt, schema):
            if self.llm.calls == before+2:
                raise RuntimeError('Fixture gián đoạn transport')
            return original(prompt, schema)
        with recovery_scope(), patch.object(self.llm, 'structured_call', side_effect=fail):
            with self.assertRaises(PilotStop): self.execute()
        first = self.holdout['schedule'][0]
        path = decision_path(self.holdout_run, first['point_id'], first['branches'][2])
        unknown = read_envelope(path); attempt = unknown['attempts'][0]['attempt_id']
        partial = self.execute(verify_only=True)
        self.assertEqual(partial['primary_status'], 'INCOMPLETE')
        self.assertIsNone(partial['primary_delta_return_pp'])
        self.assertEqual(bootstrap_report(self.holdout, partial, 'a'*64)['status'], 'INCOMPLETE')
        with recovery_scope(): self.assertEqual(self.execute()['primary_status'], 'COMPLETE')
        saved = read_envelope(path)
        self.assertEqual(saved['attempts'][0]['attempt_id'], attempt)
        self.assertEqual(len(saved['attempts']), 1)
        self.assertEqual(self.llm.calls-before, 24)
        self.assertEqual(self.events, ['indicator', 'pattern', 'trend', 'full']*8)

    def test_rehashed_manifest_or_checkpoint_cannot_change_selected_model_statistic_or_request(self) -> None:
        before = self.llm.calls
        for change in ('branch', 'seed', 'calendar', 'schema', 'model', 'code', 'repeat_type'):
            wrong = deepcopy(self.holdout)
            if change == 'branch': wrong['matrix'].append('B_semantic')
            elif change == 'seed': wrong['statistics']['seed'] = 1
            elif change == 'calendar': wrong['schedule'][0]['branches'].reverse()
            elif change == 'schema': wrong['registry']['profiles']['A_tp_pool']['decision'] = 'decision_prior_use_v1'
            elif change == 'model': wrong['inputs']['signal_config']['models']['agent_llm_temperature'] = .5
            elif change == 'repeat_type': wrong['repeat_id'] = False
            else: wrong['code_sha256'] = {}
            with self.assertRaises(ValueError):
                validate_plan(wrong, self.adapter, fixture_plan=self.dev_path, fixture_runner=self.runner)
        self.assertEqual(self.llm.calls, before)
        report = self.execute(); row = self.holdout['schedule'][0]
        path = decision_path(self.holdout_run, row['point_id'], 'A_tp_pool'); original = path.read_bytes()
        wrong = read_envelope(path); wrong['prompt'] += 'sai'; save_envelope(path, wrong)
        with self.assertRaises(ValueError): self.execute(verify_only=True)
        path.write_bytes(original)
        wrong = deepcopy(report); wrong['primary_delta_return_pp'] = 99.
        save_envelope(self.holdout_run/'report.json', wrong)
        with self.assertRaises(ValueError): read_report(self.holdout_run/'report.json', self.execute(verify_only=True))

    def test_cli_default_offline_and_fixture_cannot_be_released_or_used_online(self) -> None:
        with (patch('scripts.run_improvement_holdout.build_adapter', return_value=self.adapter),
              patch('scripts.run_improvement_holdout.validate_plan', return_value=None),
              patch('scripts.run_improvement_holdout.dotenv_values', side_effect=AssertionError('Cấm đọc key')),
              patch('httpx.HTTPTransport', side_effect=AssertionError('Cấm mạng')),
              patch('sys.argv', ['run_improvement_holdout.py', '--plan', str(self.holdout_path)])):
            main()
        self.assertFalse(self.holdout_run.exists())
        with (patch('scripts.run_improvement_holdout.build_adapter', return_value=self.adapter),
              patch('scripts.run_improvement_holdout.validate_plan', return_value=None),
              patch('scripts.run_improvement_holdout.read_technical_gates', return_value={'status': 'PASS'}),
              patch('scripts.run_improvement_holdout.dotenv_values', side_effect=AssertionError('Cấm đọc key')),
              patch('httpx.HTTPTransport', side_effect=AssertionError('Cấm mạng')),
              patch('sys.argv', ['run_improvement_holdout.py', '--run', '--plan', str(self.holdout_path), '--technical-gates', 'fixture'])):
            with self.assertRaisesRegex(ValueError, 'Fixture'):
                main()
        with self.assertRaises(ValueError): release_artifact(self.holdout, {'status': 'PASS'}, self.holdout_path)
        real_shape = {**self.holdout, 'split': 'holdout_2024'}
        with (patch('scripts.run_improvement_holdout.build_adapter', return_value=self.adapter),
              patch('scripts.run_improvement_holdout.validate_plan', return_value=None),
              patch('scripts.run_improvement_holdout.read_envelope', return_value=real_shape),
              patch('scripts.run_improvement_holdout.read_technical_gates', return_value={'status': 'PASS'}),
              patch('scripts.run_improvement_holdout.dotenv_values', side_effect=AssertionError('Cấm đọc key')),
              patch('httpx.HTTPTransport', side_effect=AssertionError('Cấm mạng')),
              patch('pathlib.Path.exists', return_value=False),
              patch('sys.argv', ['run_improvement_holdout.py', '--preflight', '--plan', str(self.holdout_path), '--technical-gates', 'fixture'])):
            with self.assertRaisesRegex(ValueError, 'Chưa có bàn giao'):
                main()
        with self.assertRaises(ValueError):
            prepare_plan(self.fx.root/'fake.json', self.adapter, fixture_plan=self.dev_path)

    def test_real_seal_rejects_self_rehashed_selection_and_ledger_tampering(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            from core.improvement_holdout import SEALED
            for name in SEALED:
                save_envelope(root/name, {'nomination_status': 'PROMOTED', 'research_candidate': 'B_semantic'})
            with self.assertRaisesRegex(ValueError, 'seal'):
                verified_development(root)
        row = {'id': 'http-fixture', 'status': 200}
        report = {'binding': {'checkpoint_sha256': {'http:http-fixture': digest(row)}}}
        _bound_files(self.fx.root, report, self.output, {'http-fixture': row})
        with self.assertRaises(ValueError):
            _bound_files(self.fx.root, report, self.output, {'http-fixture': {**row, 'status': 429}})


if __name__ == '__main__':
    unittest.main()
