"""Renderer mới đi qua serializer/schema/alias legacy, HTTP chỉ là mock."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from core.bic_icl_prompt import build_context_evidence, render_profiles, capture_decision_prompt, verify_context_evidence
from bic_icl_fixture import DecisionFixture
from bic_icl_tasks_support import TaskFixture


class ContextDecisionContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = TaskFixture()
        self.sdk = DecisionFixture()
        self.addCleanup(self.sdk.close)
        silence = patch('builtins.print')
        silence.start()
        self.addCleanup(silence.stop)
        self.sdk.shared['market_regime'].update(as_of_date='2022-01-06', feature_end_date='2022-01-06')
        self.sdk.shared['prior_provenance']['context']['as_of_date'] = '2022-01-06'
        self.state = {'stock_name': 'FPT', 'as_of_date': '2022-01-06', 'language': 'vi', 'time_frame': '1d',
                      'is_backtest': True, 'trend_report': self.sdk.shared['reports']['trend_report']}

    def setup_profiles(self, **changes: str) -> tuple:
        options = {**self.fx.query(**changes), 'strength': 8}
        evidence = build_context_evidence(self.fx.retriever, **options)
        profiles = render_profiles(evidence, 'vi', verifier=lambda e: verify_context_evidence(e, self.fx.retriever, **options))
        original = capture_decision_prompt(self.state, '', verifier=lambda actual: None)
        return evidence, profiles, original

    def test_actual_sdk_stats_alias_uses_same_schema_messages_and_joint_evidence(self) -> None:
        evidence, profiles, original = self.setup_profiles()
        requests = [self.sdk.request('original', prompt=original)]
        for name in ('R_pool', 'R_task'):
            request = profiles[name]['profiles']['stats_only']
            prompt = capture_decision_prompt(self.state, request['prefix'], verifier=lambda actual: None)
            requests.append(self.sdk.request(name+'_stats_only', prompt=prompt, prefix=request['prefix'],
                                             base=evidence['base_evidence_sha256']))
        block = self.sdk.block(point_id='FPT-2022-01-06')
        result = self.sdk.run(block, requests, create=True)
        self.assertEqual(len(self.sdk.requests), 2)
        self.assertEqual(result['branches']['R_task_stats_only']['decision_origin'], 'stats_alias')
        self.assertEqual(result['branches']['R_task_stats_only']['attempts'], [])
        body = self.sdk.requests[-1]
        self.assertEqual(body['model'], 'openai/gpt-oss-20b')
        self.assertEqual(body['response_format']['json_schema']['name'], 'TradeDecisionOutput')
        self.assertEqual(body['messages'][0]['content'], requests[1]['prompt'])
        count = len(self.sdk.requests)
        self.sdk.run(block, requests, verify_only=True)
        self.assertEqual(len(self.sdk.requests), count)

    def test_real_rendered_prior_off_reuses_original_without_fake_http(self) -> None:
        evidence, profiles, original = self.setup_profiles(current_regime='CHOPPY')
        self.sdk.shared['market_regime']['regime_name'] = 'CHOPPY'
        requests = [self.sdk.request('original', prompt=original)]
        for name in ('R_pool', 'R_task'):
            request = profiles[name]['profiles']['full_prior']
            self.assertEqual(request['prefix'], '')
            prompt = capture_decision_prompt(self.state, request['prefix'], verifier=lambda actual: None)
            requests.append(self.sdk.request(name+'_full', prompt=prompt, prefix='', base=evidence['base_evidence_sha256']))
        result = self.sdk.run(self.sdk.block(point_id='FPT-2022-01-06'), requests, create=True)
        self.assertEqual(len(self.sdk.requests), 1)
        for name in ('R_pool_full', 'R_task_full'):
            self.assertEqual(result['branches'][name]['decision_origin'], 'shared_original')
            self.assertEqual(result['branches'][name]['output'], result['branches']['original']['output'])


if __name__ == '__main__':
    unittest.main()
