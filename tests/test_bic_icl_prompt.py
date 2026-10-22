"""BRPP 3×2, hai ngôn ngữ, nhãn theo dấu gốc và prompt legacy không API."""

from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from core.bic_icl_prompt import (ContextBudgetError, build_context_evidence, capture_decision_prompt,
    render_prefix, render_profiles, verify_context_evidence)
from core.historical_signals import digest
from scripts.prepare_bic_icl_context import budget_evidence, check_budget_fixture
from bic_icl_tasks_support import TaskFixture


def rehash(evidence: dict) -> dict:
    """Tái băm chỉ phục vụ ca giả mạo, không được coi là verifier nguồn."""
    evidence['base_evidence_sha256'] = digest({k: v for k, v in evidence.items() if k != 'base_evidence_sha256'})
    return evidence


class ContextRendererTests(unittest.TestCase):
    def setUp(self) -> None:
        silence = patch('builtins.print')
        silence.start()
        self.addCleanup(silence.stop)
        self.fx = TaskFixture()
        self.options = {**self.fx.query(), 'strength': 8}
        self.evidence = build_context_evidence(self.fx.retriever, **self.options)

    def verify(self, evidence: dict) -> None:
        verify_context_evidence(evidence, self.fx.retriever, **self.options)

    def test_three_tasks_six_examples_all_xy_and_group_boundaries_fit_both_languages(self) -> None:
        for lang in ('vi', 'en'):
            profiles = render_profiles(self.evidence, lang, verifier=self.verify)
            full = profiles['R_task']['profiles']['full_prior']
            prefix = full['prefix']
            self.assertLessEqual(len(prefix), 600)
            self.assertEqual(prefix.count('→'), 6)
            self.assertEqual(sum(prefix.count(f'G{i}'+'{') for i in (1, 2, 3)), 3)
            self.assertIn('x=T/P', prefix)
            self.assertIn('y=W/L', prefix)
            self.assertIn('SHORT=CASH', prefix)
            self.assertEqual(full['trace']['k_tasks'], 3)
            self.assertEqual(full['trace']['k_episodes'], 6)
            self.assertEqual(full['decision_contract_version'], 'decision_legacy_v1')

    def test_stats_requests_are_byte_equal_prefix_with_same_joint_base(self) -> None:
        for lang in ('vi', 'en'):
            profiles = render_profiles(self.evidence, lang, verifier=self.verify)
            left, right = (profiles[m]['profiles']['stats_only'] for m in ('R_pool', 'R_task'))
            self.assertEqual(left['prefix'], right['prefix'])
            self.assertEqual(left['base_evidence_sha256'], right['base_evidence_sha256'])
            self.assertNotEqual(left['request_sha256'], right['request_sha256'])
            self.assertEqual(left['trace'], right['trace'])

    def test_ablation_hides_blocks_without_changing_evidence_or_selected_ids(self) -> None:
        before = deepcopy(self.evidence)
        profiles = render_profiles(self.evidence, 'vi', verifier=self.verify)['R_task']['profiles']
        self.assertNotIn('→', profiles['stats_only']['prefix'])
        self.assertNotIn('p=', profiles['examples_only']['prefix'])
        self.assertEqual(profiles['examples_only']['prefix'].count('→'), 6)
        self.assertEqual(self.evidence, before)
        self.assertEqual(json.loads(json.dumps(profiles, allow_nan=False)), profiles)

    def test_boundary_recipe_retains_large_tiny_zero_and_bankers_rounding(self) -> None:
        evidence, recipe = budget_evidence()
        for lang in ('vi', 'en'):
            prefix = render_prefix(evidence, 'R_task', 'full_prior', lang)
            for row in recipe['examples']:
                self.assertIn(row['label']+'/'+row['return_text'], prefix)
            self.assertIn('0+→W/+0.00%', prefix)
            self.assertIn('+0→L/-0.00%', prefix)
            self.assertIn('00→L/+0.00%', prefix)
            self.assertIn('-+→L/-100.00%', prefix)

    def test_long_reports_keep_actual_distill_cap_and_both_prompts_under_6500(self) -> None:
        result = check_budget_fixture()
        self.assertEqual(result['languages']['vi']['max_prefix_chars'], 300)
        self.assertEqual(result['languages']['en']['max_prefix_chars'], 297)
        for lang, row in result['languages'].items():
            self.assertLess(row['max_prompt_chars'], 6500)
            for method in row['prompts'].values():
                for prompt in method.values():
                    self.assertIn('T+2.5', prompt)
                    self.assertIn('[BRPP EB1]', prompt)

    def test_budget_overflow_blocks_all_task_profiles_without_dropping_examples(self) -> None:
        evidence, _ = budget_evidence()
        for task in evidence['task_selection']['tasks'][2:]:
            for example in task['examples']:
                example['outcome']['net_return_pct'] = 1e308
        rehash(evidence)
        before = deepcopy(evidence)
        with self.assertRaises(ContextBudgetError):
            render_prefix(evidence, 'R_task', 'full_prior', 'vi')
        result = render_profiles(evidence, 'vi', verifier=lambda actual: None)
        self.assertEqual(result['R_task']['status'], 'BLOCKED')
        self.assertEqual(result['R_task']['profiles'], {})
        self.assertEqual(result['R_task']['blocked_branch_ids'], ['R_task_full', 'R_task_stats_only', 'R_task_examples_only'])
        self.assertEqual(result['R_pool']['status'], 'AVAILABLE')
        self.assertEqual(evidence, before)

    def test_fallback_empty_prefix_captures_exact_original_in_both_languages(self) -> None:
        options = {**self.options, 'current_regime': 'CHOPPY'}
        evidence = build_context_evidence(self.fx.retriever, **options)
        for lang in ('vi', 'en'):
            profiles = render_profiles(evidence, lang, verifier=lambda actual: verify_context_evidence(actual, self.fx.retriever, **options))
            state = {'stock_name': 'FPT', 'as_of_date': '2022-01-06', 'is_backtest': True, 'language': lang,
                'time_frame': '1d', 'trend_report': 'Dữ liệu xu hướng lịch sử.'}
            original = capture_decision_prompt(state, '', verifier=lambda actual: None)
            for part in profiles.values():
                for request in part['profiles'].values():
                    self.assertEqual(request['prefix'], '')
                    self.assertEqual(capture_decision_prompt(state, request['prefix'], verifier=lambda actual: None), original)

    def test_capture_checks_source_before_prompt_and_never_invokes_client(self) -> None:
        state = {'stock_name': 'FPT', 'as_of_date': '2022-01-06', 'is_backtest': True, 'language': 'vi', 'time_frame': '1d'}
        def reject(actual: dict) -> None:
            raise ValueError('Nguồn không hợp lệ')
        with self.assertRaisesRegex(ValueError, 'Nguồn không hợp lệ'):
            capture_decision_prompt(state, '', verifier=reject)
        with patch('agents.decision_agent._invoke_with_retry', side_effect=AssertionError('Cấm API')):
            self.assertTrue(capture_decision_prompt(state, '', verifier=lambda actual: None))

    def test_invalid_profile_and_missing_semantic_verifier_are_errors(self) -> None:
        for method, mode, lang in (('A', 'full_prior', 'vi'), ('R_task', 'other', 'vi'), ('R_task', 'full_prior', 'fr')):
            with self.assertRaises(ValueError):
                render_prefix(self.evidence, method, mode, lang)
        with self.assertRaises(ValueError):
            render_profiles(self.evidence, 'vi', verifier=None)


if __name__ == '__main__':
    unittest.main()
