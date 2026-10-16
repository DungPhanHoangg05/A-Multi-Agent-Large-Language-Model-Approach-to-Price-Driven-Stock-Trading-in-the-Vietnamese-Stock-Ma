"""SDK thật qua HTTP mock: body/schema audit, retry và fingerprint nối raw response."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx
from langchain_groq import ChatGroq
from langchain_core.messages import messages_to_dict

from agents.decision_agent import TradeDecisionOutput, _invoke_with_retry
from core.historical_signals import digest
from core.improvement_transport import SLOT, ImprovementTransport, body_contract, expected_contract, verify_attempt_audit, validate_client
from core.provider_quota import ProviderQuotaPacer
from core.research_invocation import ENABLED, invocation_scope
from core.groq_pacing import PilotStop


class ImprovementTransportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)/'usage.json'
        self.now = 100000.
        def sleep(seconds):
            self.now += seconds
        self.pacer = ProviderQuotaPacer(self.path, credential='fixture-secret', amendment_sha256='a'*64,
            clock=lambda: self.now, sleep=sleep, policy='request_admission_v2')
        self.payload = {'decision': 'LONG', 'forecast_horizon': 'T+2.5', 'confidence': 'Cao', 'risk_reward_ratio': 1.5,
            'evidence_for': 'Dữ liệu hiện tại.', 'evidence_against': 'Rủi ro.', 'justification': 'Fixture.'}
        self.slot = {'run_signature': 'a'*64, 'point_id': 'FPT-2023-01-06', 'branch_id': 'original', 'repeat_id': 0,
            'checkpoint_attempt_id': '00000000-0000-0000-0000-000000000001', 'prompt_sha256': None}

    def response(self):
        return httpx.Response(200, json={'id': 'fixture-response', 'object': 'chat.completion', 'created': 1,
            'model': 'openai/gpt-oss-20b', 'choices': [{'index': 0, 'message': {'role': 'assistant',
                'content': json.dumps(self.payload, ensure_ascii=False)}, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 5, 'completion_tokens': 5, 'total_tokens': 10}})

    def invoke(self, handler, slot=None):
        """Không có HTTP thật; mọi invocation vẫn đi qua wrapper và pacer production."""
        import hashlib
        prompt = 'Kiểm request nguyên byte.'
        self.slot['prompt_sha256'] = hashlib.sha256(prompt.encode()).hexdigest()
        active = self.slot if slot is None else slot
        token = ENABLED.set(True)
        scope = SLOT.set(active)
        try:
            with httpx.Client(transport=ImprovementTransport(self.pacer, httpx.MockTransport(handler))) as client:
                llm = ChatGroq(model='openai/gpt-oss-20b', api_key='fixture-secret', temperature=0, max_tokens=2048,
                    max_retries=0, reasoning_effort='low', reasoning_format='hidden', http_client=client)
                llm.temperature = 0
                expected = expected_contract(llm, prompt)
                with patch('core.groq_pacing.request_budget', return_value=20), invocation_scope('decision_original') as budget:
                    budget.run_signature, budget.point_id, budget.branch_id = active['run_signature'], active['point_id'], active['branch_id']
                    budget.checkpoint_attempt_id = active['checkpoint_attempt_id']
                    result = _invoke_with_retry(llm.with_structured_output(TradeDecisionOutput,
                        method='json_schema', include_raw=True).invoke, prompt)
                raw = messages_to_dict([result['raw']])[0]['data']
                return expected, raw
        finally:
            SLOT.reset(scope)
            ENABLED.reset(token)

    def test_canonical_body_matches_sdk_and_intent_is_durable_before_send(self) -> None:
        captured = []
        def handle(request):
            captured.append(json.loads(request.content))
            saved = json.loads(self.path.read_text(encoding='utf-8'))
            self.assertIsNotNone(saved['requests'][-1]['improvement_audit']['request'])
            self.assertIsNone(saved['requests'][-1]['improvement_audit']['response'])
            return self.response()
        expected, raw = self.invoke(handle)
        self.assertEqual(expected, body_contract(captured[0]))
        rows = verify_attempt_audit(self.pacer.state, self.slot, expected=expected, raw_message=raw)
        self.assertEqual(len(rows), 1)
        self.assertNotIn('fixture-secret', self.path.read_text(encoding='utf-8'))
        wrong = deepcopy(raw)
        wrong['content'] = 'Thay response'
        with self.assertRaises(ValueError):
            verify_attempt_audit(self.pacer.state, self.slot, expected=expected, raw_message=wrong)

    def test_429_uses_same_request_budget_and_audits_both_http_attempts(self) -> None:
        calls = []
        def handle(request):
            calls.append(json.loads(request.content))
            return httpx.Response(429, headers={'retry-after': '1'}, json={'error': {'message': 'retry after 1 seconds'}}) if len(calls) == 1 else self.response()
        expected, raw = self.invoke(handle)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0], calls[1])
        self.assertEqual([r['status'] for r in self.pacer.state['requests']], [429, 200])
        self.assertEqual(len(verify_attempt_audit(self.pacer.state, self.slot, expected=expected, raw_message=raw)), 2)

    def test_unknown_transport_keeps_intent_and_no_automatic_replay(self) -> None:
        calls = []
        def handle(request):
            calls.append(1)
            raise httpx.ConnectError('Fixture mất response')
        with self.assertRaises(PilotStop):
            self.invoke(handle)
        self.assertEqual(len(calls), 1)
        row = self.pacer.state['requests'][-1]
        self.assertEqual(row['status'], 'transport_error')
        self.assertIsNone(row['improvement_audit']['response'])

    def test_forbidden_body_option_is_not_silently_dropped_from_audit(self) -> None:
        with self.assertRaises(ValueError):
            body_contract({'model': 'openai/gpt-oss-20b', 'messages': [], 'api_key': 'fixture-secret'})

    def test_sdk_seed_or_additional_sampling_options_cannot_bypass_locked_protocol(self) -> None:
        llm = ChatGroq(model='openai/gpt-oss-20b', api_key='offline', temperature=0, max_tokens=2048,
                       max_retries=0, reasoning_effort='low', reasoning_format='hidden')
        llm.temperature = 0.
        models = {'agent_llm_model': 'openai/gpt-oss-20b', 'agent_llm_temperature': 0., 'agent_llm_max_tokens': 2048}
        validate_client(llm, 'agent', models)
        for kwargs in ({'seed': 42}, {'stop': ['LONG']}, {'top_p': .9}):
            llm.model_kwargs = kwargs
            with self.assertRaises(ValueError):
                validate_client(llm, 'agent', models)
