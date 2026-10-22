"""CLI/schema và upstream fresh production; không đọc credential hoặc gọi mạng."""

from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from core.bic_icl_protocol import CohortSources, validate_schema, protocol
from core.bic_icl_runtime import fresh_shared
from core.research_cohort import read_envelope, save_envelope
from test_candidate_cohort import CandidateSetup
from scripts.run_bic_icl import main


class FreshSharedTests(CandidateSetup, unittest.TestCase):
    def test_fresh_upstream_runs_one_time_then_restores_without_builder(self):
        sources = SimpleNamespace(adapter=self.adapter)
        row = {'point_id': 'FPT-'+self.cutoffs[0], 'symbol': 'FPT', 'as_of_date': self.cutoffs[0]}
        point, shared, bundle = fresh_shared(sources, row, self.output, 'a'*64, self.builder,
            fixture=True, verify_only=False)
        self.assertEqual(self.events, ['indicator', 'pattern', 'trend', 'full'])
        _, restored, restored_bundle = fresh_shared(sources, row, self.output, 'a'*64, None,
            fixture=True, verify_only=True)
        self.assertEqual(restored, shared)
        self.assertEqual(restored_bundle, bundle)
        self.assertEqual(len(self.events), 4)
        point.verify_source(shared)

    def test_rehashed_fresh_bundle_outcome_fails_without_reinvoking_upstream(self):
        sources = SimpleNamespace(adapter=self.adapter)
        row = {'point_id': 'FPT-'+self.cutoffs[0], 'symbol': 'FPT', 'as_of_date': self.cutoffs[0]}
        fresh_shared(sources, row, self.output, 'a'*64, self.builder, fixture=True, verify_only=False)
        path = self.output/'shared'/f"{row['point_id']}.json"
        bundle = read_envelope(path)
        bundle['outcome'] = {'return': 99}
        save_envelope(path, bundle)
        with self.assertRaises(ValueError):
            fresh_shared(sources, row, self.output, 'a'*64, self.builder, fixture=True, verify_only=False)
        self.assertEqual(len(self.events), 4)


class CohortCliTests(unittest.TestCase):
    def test_identity_binds_dependencies_without_enumerating_unrelated_future_modules(self):
        from pathlib import Path
        from core.bic_icl_protocol import code_identity
        with patch.object(Path, 'rglob', side_effect=AssertionError('Không bind analyzer ngoài phạm vi')):
            identity = code_identity()
        for name in ('core/bic_icl_protocol.py', 'core/bic_icl_runtime.py', 'core/bic_icl_decisions.py',
                     'core/bic_icl_prompt.py', 'core/improvement_recovery.py', 'core/backtest_engine.py'):
            self.assertIn(name, identity)
        self.assertNotIn('docs/plan/week10/README.md', identity)

    def test_release_consumer_detects_changed_gate_and_returns_copy(self):
        from pathlib import Path
        import tempfile
        from core.bic_icl_protocol import read_authorization
        from core.historical_signals import digest
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'release.json'
            plan = {'code_sha256': {'code': 'a'*64}, 'runtime': {'python': 'fixture'}, 'upstream_policy': 'VERIFIED_CACHE'}
            payload = {'release_version': 'bic_icl_development_release_v1', 'plan_sha256': digest(plan),
                'technical_gates_sha256': 'b'*64, 'upstream_policy': 'VERIFIED_CACHE',
                'code_sha256': plan['code_sha256'], 'runtime': plan['runtime'],
                'decision_context_lock_sha256': 'c'*64, 'confirmation_allowed': False}
            save_envelope(path, payload)
            with patch('core.candidate_selection.read_technical_gates', return_value={'status': 'PASS', 'sha256': 'b'*64}):
                authorization = read_authorization(path, Path(directory)/'gates.json', plan)
                copied = authorization.payload
                copied['confirmation_allowed'] = True
                self.assertFalse(authorization.payload['confirmation_allowed'])
                authorization.verify(plan)
            with patch('core.candidate_selection.read_technical_gates', return_value={'status': 'PASS', 'sha256': 'd'*64}):
                with self.assertRaises(ValueError):
                    authorization.verify(plan)

    def test_economic_mode_does_not_construct_source_or_read_environment(self):
        with patch('scripts.run_bic_icl.CohortSources', side_effect=AssertionError('Không đọc nguồn')), patch('builtins.print'):
            main(['--economic-fixture'])

    def test_default_is_dry_run_without_client_or_credentials(self):
        source = SimpleNamespace(validate=lambda plan: None)
        with patch('scripts.run_bic_icl.CohortSources', return_value=source), patch(
                'scripts.run_bic_icl.read_envelope', return_value={}), patch(
                'scripts.run_bic_icl.dry_run', return_value={'status': 'PASS', 'lock': None,
                    'fresh_requests_pending': True}) as dry, patch('builtins.print'):
            main([])
        dry.assert_called_once()

    def test_online_missing_release_rejects_before_builder(self):
        from core.bic_icl_protocol import NAMESPACE
        source = SimpleNamespace(validate=lambda plan: None)
        with patch('scripts.run_bic_icl.CohortSources', return_value=source), patch(
                'scripts.run_bic_icl.read_envelope', return_value={}), patch(
                'scripts.run_bic_icl.read_authorization', side_effect=ValueError('Chưa release')) as auth, patch(
                'scripts.run_bayesian_ablation.make_builder', side_effect=AssertionError('Không tạo SDK')):
            with self.assertRaises(ValueError):
                main(['--run'])
        auth.assert_called_once()

    def test_loader_rejects_rehashed_later_schedule_or_method(self):
        import pandas as pd
        plan = {'plan_version': 'bic_icl_cohort_plan_v1', 'split': 'development_2023',
            'method_sha256': 'a'*64, 'protocol': protocol(), 'inputs': {},
            'schedule': [{'point_id': 'FPT-'+day.strftime('%Y-%m-%d'), 'symbol': 'FPT',
                'as_of_date': day.strftime('%Y-%m-%d')} for day in pd.bdate_range('2023-01-02', periods=60)],
            'upstream_policy': 'VERIFIED_CACHE', 'language': 'vi',
            'code_sha256': {}, 'runtime': {}, 'source_hashes': {}, 'confirmation_allowed': False}
        validate_schema(plan, 'plan')
        source = SimpleNamespace(plan=lambda policy: deepcopy(plan))
        CohortSources.validate(source, plan)
        for update in ({'method_sha256': 'b'*64}, {'schedule': list(reversed(plan['schedule']))},
                       {'language': 'en'}, {'confirmation_allowed': True}):
            with self.subTest(update=list(update)), self.assertRaises(ValueError):
                CohortSources.validate(source, {**plan, **update})


if __name__ == '__main__':
    unittest.main()
