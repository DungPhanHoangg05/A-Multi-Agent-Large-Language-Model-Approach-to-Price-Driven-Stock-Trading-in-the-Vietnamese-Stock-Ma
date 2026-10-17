"""Retry/resume mới bằng SDK thật và HTTP mock, không gọi API hoặc đọc key."""

from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import httpx

from core.groq_pacing import PilotStop
from core.improvement_recovery import ResilientPacer, ResilientTransport, recovery_scope, VERSION
from core.improvement_transport import verify_attempt_audit
from core.prior_stage_journal import StageJournal
from core.research_cohort import read_envelope, save_envelope
from core.research_invocation import RECOVERY, ENABLED, invocation_scope
import test_improvement_transport as support


class ImprovementRecoveryTests(unittest.TestCase):
    """Mỗi HTTP retry có record thật; cache không tạo HTTP thành công giả."""

    def setUp(self) -> None:
        self.fixture = support.ImprovementTransportTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.pacer = self.pacer('fixture-key-one')
        self.cache = Path(self.fixture.directory.name)/'cache'

    def pacer(self, key: str) -> ResilientPacer:
        """Đồng hồ và sleep giả, giữ cùng một ledger giữa hai key."""
        return ResilientPacer(self.fixture.path, credential=key, amendment_sha256='b'*64,
            clock=lambda: self.fixture.now, sleep=lambda seconds: setattr(self.fixture, 'now', self.fixture.now+seconds),
            policy='request_admission_v2')

    def invoke(self, handle):
        """Dùng nguyên helper SDK/schema/audit production, chỉ đổi transport revision."""
        def transport(pacer, inner):
            return ResilientTransport(pacer, self.cache, inner)
        with recovery_scope(), patch.object(support, 'ImprovementTransport', transport):
            return self.fixture.invoke(handle)

    def test_transport_and_server_errors_retry_same_body_uuid_with_audit(self) -> None:
        bodies = []
        def handle(request):
            bodies.append(request.content)
            if len(bodies) == 1:
                raise httpx.ConnectError('Fixture kết nối bị ngắt')
            if len(bodies) == 2:
                return httpx.Response(502, json={'error': {'message': 'Fixture server tạm lỗi'}})
            if len(bodies) == 3:
                raise httpx.ReadTimeout('Fixture mất response')
            return self.fixture.response()
        expected, raw = self.invoke(handle)
        rows = verify_attempt_audit(self.fixture.pacer.state, self.fixture.slot, expected=expected, raw_message=raw)
        self.assertEqual([r['status'] for r in rows], ['transport_error', 502, 'transport_error', 200])
        self.assertEqual(len(set(bodies)), 1)
        self.assertEqual(len({r['checkpoint_attempt_id'] for r in rows}), 1)
        self.assertEqual(len(self.fixture.pacer.state['recovery_events']), 3)
        self.assertTrue(all(r['recovery_policy'] == VERSION for r in rows))
        self.assertNotIn('fixture-key-one', self.fixture.path.read_text(encoding='utf-8'))

    def test_minute_limit_waits_beyond_old_budget_without_stopping(self) -> None:
        calls = []
        def handle(request):
            calls.append(1)
            return httpx.Response(429, headers={'retry-after': '355'}, json={
                'error': {'message': 'Rate limit reached on tokens per minute (TPM)'}}) if len(calls) == 1 else self.fixture.response()
        self.invoke(handle)
        self.assertEqual(len(calls), 2)
        self.assertGreaterEqual(self.fixture.now, 100356.)
        self.assertEqual(self.fixture.pacer.state['recovery_events'][0]['reason'], 'RATE_LIMIT_WAIT')

    def test_daily_quota_stops_and_new_key_resumes_same_uuid_without_erasing_usage(self) -> None:
        with self.assertRaises(PilotStop):
            self.invoke(lambda request: httpx.Response(429, headers={'retry-after': '3600'}, json={
                'error': {'message': 'Rate limit reached on tokens per day (TPD)'}}))
        before = deepcopy(self.fixture.pacer.state['requests'])
        self.assertEqual(self.fixture.pacer.state['last_stop']['reason'], 'PROVIDER_DAILY_QUOTA')
        self.fixture.pacer = self.pacer('fixture-key-two')
        expected, raw = self.invoke(lambda request: self.fixture.response())
        rows = self.fixture.pacer.state['requests']
        self.assertEqual(rows[:len(before)], before)
        self.assertEqual([r['status'] for r in rows], [429, 200])
        self.assertNotEqual(rows[0]['credential_scope'], rows[1]['credential_scope'])
        verify_attempt_audit(self.fixture.pacer.state, self.fixture.slot, expected=expected, raw_message=raw)

    def test_durable_response_recovery_uses_no_additional_http(self) -> None:
        expected, raw = self.invoke(lambda request: self.fixture.response())
        before = len(self.fixture.pacer.state['requests'])
        recovered, recovered_raw = self.invoke(lambda request: self.fail('Response đã durable, cấm gửi lại'))
        self.assertEqual(expected, recovered)
        self.assertEqual(raw['content'], recovered_raw['content'])
        self.assertEqual(len(self.fixture.pacer.state['requests']), before)
        self.assertEqual(self.fixture.pacer.state['recovery_events'][-1]['reason'], 'DURABLE_RESPONSE_REUSED')
        verify_attempt_audit(self.fixture.pacer.state, self.fixture.slot, expected=recovered, raw_message=recovered_raw)

    def test_response_cache_tamper_blocks_before_http(self) -> None:
        self.invoke(lambda request: self.fixture.response())
        path = next(self.cache.glob('*.json'))
        saved = read_envelope(path)
        saved['body_base64'] = 'e30='
        save_envelope(path, saved)
        calls = []
        with self.assertRaises((ValueError, PilotStop)):
            self.invoke(lambda request: calls.append(1) or self.fixture.response())
        self.assertEqual(calls, [])

    def test_stage_with_multiple_prompts_restores_each_matching_response(self) -> None:
        token = ENABLED.set(True)
        self.addCleanup(ENABLED.reset, token)
        def execute(handler):
            with recovery_scope(), invocation_scope('full') as budget, httpx.Client(
                    transport=ResilientTransport(self.fixture.pacer, self.cache, httpx.MockTransport(handler))) as client:
                budget.run_signature = self.fixture.slot['run_signature']
                budget.point_id = self.fixture.slot['point_id']
                budget.checkpoint_attempt_id = self.fixture.slot['checkpoint_attempt_id']
                return [client.post('https://api.groq.com/openai/v1/chat/completions', json={
                    'model': 'openai/gpt-oss-20b', 'max_tokens': 2048,
                    'messages': [{'role': 'user', 'content': prompt}]}).content for prompt in ('Báo cáo A', 'Báo cáo B')]
        def respond(request):
            self.fixture.payload['justification'] = json.loads(request.content)['messages'][0]['content']
            return self.fixture.response()
        with patch('core.groq_pacing.request_budget', return_value=20):
            original = execute(respond)
            recovered = execute(lambda request: self.fail('Phải dùng cache của đúng prompt'))
        self.assertEqual(original, recovered)
        self.assertEqual(len(self.fixture.pacer.state['requests']), 2)

    def test_missing_confirmed_response_cache_blocks_before_http(self) -> None:
        self.invoke(lambda request: self.fixture.response())
        next(self.cache.glob('*.json')).unlink()
        calls = []
        with self.assertRaises((ValueError, PilotStop)):
            self.invoke(lambda request: calls.append(1) or self.fixture.response())
        self.assertEqual(calls, [])

    def test_rate_limit_backoff_stays_bounded_after_many_http_attempts(self) -> None:
        token = ENABLED.set(True)
        self.addCleanup(ENABLED.reset, token)
        calls = []
        def respond(request):
            calls.append(1)
            return (httpx.Response(429, headers={'retry-after': '1'}, json={'error': {'message': 'TPM'}})
                    if len(calls) == 1 else self.fixture.response())
        with recovery_scope(), invocation_scope('full') as budget, patch('core.groq_pacing.request_budget', return_value=20):
            budget.attempts = 1024
            with httpx.Client(transport=ResilientTransport(self.fixture.pacer, self.cache, httpx.MockTransport(respond))) as client:
                response = client.post('https://api.groq.com/openai/v1/chat/completions', json={
                    'model': 'openai/gpt-oss-20b', 'messages': [{'role': 'user', 'content': 'Kiểm backoff'}]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(calls, [1, 1])
        self.assertLessEqual(self.fixture.now-100000., 60.)

    def test_invalid_key_is_not_retried_forever(self) -> None:
        calls = []
        def handle(request):
            calls.append(1)
            return httpx.Response(401, json={'error': {'message': 'Invalid API key'}})
        with self.assertRaises(PilotStop):
            self.invoke(handle)
        self.assertEqual(calls, [1])

    def test_unknown_stage_resumes_same_uuid_and_complete_is_never_replayed(self) -> None:
        path = Path(self.fixture.directory.name)/'journal.json'
        binding = {'run_signature': 'a'*64, 'point_id': 'FPT-2023-01-06', 'source_sha256': 'b'*64}
        journal = StageJournal(path, binding, create=True)
        with self.assertRaises(OSError):
            journal.invoke('indicator', lambda state: (_ for _ in ()).throw(OSError('Fixture ngắt')), {})
        attempt = journal.document['nodes']['indicator']['attempts'][-1]['attempt_id']
        with recovery_scope():
            result = journal.invoke('indicator', lambda state: {'indicator_report': 'Báo cáo hợp lệ'}, {})
        self.assertFalse(RECOVERY.get())
        attempts = journal.document['nodes']['indicator']['attempts']
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]['attempt_id'], attempt)
        self.assertEqual(attempts[0]['status'], 'complete')
        self.assertEqual(journal.invoke('indicator', lambda state: self.fail('Cấm gọi node complete'), {}), result)


if __name__ == '__main__':
    unittest.main()
