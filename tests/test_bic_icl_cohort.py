"""Producer/loader/cohort/repeat mới chạy SDK mock với posterior và engine thật."""

from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from bic_icl_cohort_support import CohortFixture
from core.bic_icl_protocol import (protocol, repeat_sample, validate_schema, namespace_path,
    read_authorization, ExecutionAuthorization)
from core.bic_icl_reports import check_economic_fixture, numeric_action, verify_report
from core.bic_icl_runtime import context_lock, requests_for, run_cohort
from core.historical_signals import digest
from core.research_cohort import read_envelope, save_envelope
from core.research_input_lock import _write_once


class CohortTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = CohortFixture()
        self.addCleanup(self.fx.close)
        silence = patch('builtins.print')
        silence.start()
        self.addCleanup(silence.stop)

    def run_cohort(self, **options):
        return run_cohort(self.fx.plan, self.fx.sources, self.fx.root, self.fx.sdk.llm, fixture=True, **options)

    def packets(self):
        return [self.fx.sources.packet(row, *self.fx.sources.cached(row)) for row in self.fx.plan['schedule']]

    def test_protocol_is_separate_and_preserves_matrix_economics_budget(self):
        spec = protocol()
        self.assertEqual(len(spec['development_matrix']), 9)
        self.assertEqual(spec['nomination_order'], ['R_pool', 'R_task'])
        self.assertEqual(spec['economic']['short'], 'CASH')
        self.assertEqual(spec['economic']['entry'], 'Open(t+1)')
        self.assertEqual(spec['economic']['exit'], 'Close(t+3)')
        self.assertEqual(spec['prior_chars_max'], 600)
        self.assertEqual(spec['bootstrap']['seed'], 20261021)

    def test_actual_sdk_primary_resume_read_only_and_no_nomination(self):
        report = self.run_cohort()
        self.assertEqual(report['status'], 'COMPLETE')
        self.assertFalse(report['nomination_performed'])
        self.assertFalse(report['confirmation_allowed'])
        self.assertEqual(len(report['points']), 12)
        requests = len(self.fx.sdk.requests)
        self.assertGreater(requests, 12)
        protected = {p: p.read_bytes() for p in self.fx.root.rglob('*.json')
            if p.name not in ('run.owner.json', 'run.recovery.json')}
        self.assertEqual(self.run_cohort(resume=True), report)
        self.assertEqual(self.run_cohort(verify_only=True), report)
        self.assertEqual(len(self.fx.sdk.requests), requests)
        self.assertTrue(all(p.read_bytes() == data for p, data in protected.items()))
        _write_once(self.fx.root/'report_0.json', report)
        verify_report(self.fx.root/'report_0.json', report)

    def test_three_repeats_keep_primary_bytes_and_duplicate_independent(self):
        primary = self.run_cohort()
        protected = {p: p.read_bytes() for p in (self.fx.root/'decision_blocks/0').rglob('*.json')}
        for repeat_id in (1, 2, 3):
            before = len(self.fx.sdk.requests)
            report = self.run_cohort(repeat_id=repeat_id, resume=True)
            self.assertFalse(report['in_primary'])
            self.assertNotIn('Numeric_only', report['matrix'])
            self.assertEqual(len(report['points']), 12)
            for row in report['points']:
                self.assertEqual(row['branches']['original_duplicate']['decision_origin'], 'independent_duplicate')
                self.assertEqual(row['branches']['original_duplicate']['scientific_attempt_count'], 1)
            self.assertGreaterEqual(len(self.fx.sdk.requests)-before, 24)
            self.assertEqual(self.run_cohort(repeat_id=repeat_id, verify_only=True), report)
        self.assertTrue(all(p.read_bytes() == data for p, data in protected.items()))
        self.assertEqual(self.run_cohort(verify_only=True), primary)

    def test_context_repeat_uses_readiness_and_fallback_without_actions(self):
        packets = self.packets()
        sample = repeat_sample(packets)
        self.assertEqual(len({r['point_id'] for r in sample}), 12)
        self.assertEqual(sum(r['reason'] == 'EARLIEST_UNUSED_FALLBACK' for r in sample), 8)
        changed = deepcopy(packets)
        for p in changed:
            p['evidence']['unused_decision_action'] = 'SHORT'
        self.assertEqual(repeat_sample(changed), sample)

    def test_global_task_block_removes_three_ids_and_relocks_rotation(self):
        packets = self.packets()
        packets[0]['task_technical_available'] = False
        lock = context_lock(self.fx.plan, packets)
        self.assertFalse(lock['task_enabled'])
        self.assertEqual(len(lock['matrix']), 5)
        requests = requests_for(packets[1], lock, 1, 0)
        self.assertEqual([r['branch_id'] for r in requests], ['original',
            'R_pool_full', 'R_pool_stats_only', 'R_pool_examples_only', 'A_reference_shared_off'])

    def test_numeric_strict_threshold_and_zero_gate_are_not_missing_fallback(self):
        evidence = self.packets()[0]['evidence']
        for ready, p, action in ((True, .5, 'SHORT'), (True, .500001, 'LONG'), (False, .9, 'SHORT')):
            evidence['gate']['R_pool']['stats_ready'] = ready
            evidence['pool']['statistics']['posterior_mean'] = p
            result = numeric_action(evidence)
            self.assertEqual(result['action'], action)

    def test_economic_fixture_matches_real_engine_four_action_paths(self):
        report = check_economic_fixture()
        self.assertEqual(report['status'], 'PASS')
        self.assertEqual(len(report['cases']), 4)
        cash = report['cases'][-1]
        self.assertEqual(cash['actions'], ['SHORT', 'SHORT'])
        self.assertEqual(cash['oracle_return_pct'], 0.)
        self.assertEqual(cash['oracle_capital_vnd'], 50000000.)

    def test_schema_rejects_request_extra_outcomes_and_overbudget(self):
        request = self.packets()[0]['requests']['original']
        validate_schema(request, 'request')
        for update in ({'evaluation': {}}, {'prefix': 'x'*601}, {'prompt': 'x'*6500}):
            with self.subTest(update=list(update)), self.assertRaises(ValueError):
                validate_schema({**request, **update}, 'request')

    def test_english_renderer_uses_same_sdk_schema_and_horizon(self):
        from core.bic_icl_decisions import DecisionBlock
        self.fx.plan['language'] = 'en'
        self.fx.signature = digest(self.fx.plan)
        self.fx.sdk.payload['confidence'] = 'High'
        row = self.fx.plan['schedule'][0]
        packet = self.fx.sources.packet(row, *self.fx.sources.cached(row))
        requests = [packet['requests'][name] for name in ('original', 'R_pool_stats_only', 'R_task_stats_only')]
        block = DecisionBlock(self.fx.root, 'a'*64, row['point_id'], 0, self.fx.sdk.llm, language='en', fixture=True)
        doc = block.run(packet['bundle'], requests, verify_sources=lambda: None, create=True)
        self.assertEqual(len(self.fx.sdk.requests), 2)
        self.assertEqual(doc['branches']['R_task_stats_only']['decision_origin'], 'stats_alias')
        for body in self.fx.sdk.requests:
            self.assertEqual(body['response_format']['json_schema']['name'], 'TradeDecisionOutput')
        for branch in doc['branches'].values():
            self.assertIn('T+2.5', branch['output']['final_trade_decision'])

    def test_numeric_missing_probability_raises_instead_of_cash(self):
        evidence = self.packets()[0]['evidence']
        evidence['pool']['statistics']['posterior_mean'] = None
        with self.assertRaises(ValueError):
            numeric_action(evidence)

    def test_namespace_and_authorization_reject_before_keys(self):
        for name in ('memory_v1', 'train_v1', 'context_v1', '../outside'):
            with self.assertRaises(ValueError):
                namespace_path(self.fx.root/name, 'run')
        with self.assertRaises(ValueError):
            read_authorization(None, None, self.fx.plan)
        with self.assertRaises(ValueError):
            ExecutionAuthorization({}, verified=object())


if __name__ == '__main__':
    unittest.main()
