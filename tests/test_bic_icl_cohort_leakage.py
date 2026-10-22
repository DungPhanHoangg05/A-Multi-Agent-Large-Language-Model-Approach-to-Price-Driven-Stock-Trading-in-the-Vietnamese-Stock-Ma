"""Integrity semantic của plan/packet/report và ngăn replay sau sửa/mất artifact."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from bic_icl_cohort_support import CohortFixture
from core.bic_icl_runtime import run_cohort
from core.bic_icl_decisions import DecisionBlock
from core.research_cohort import read_envelope, save_envelope


class CohortLeakageTests(unittest.TestCase):
    def setUp(self):
        self.fx = CohortFixture()
        self.addCleanup(self.fx.close)
        silence = patch('builtins.print')
        silence.start()
        self.addCleanup(silence.stop)

    def execute(self, **options):
        return run_cohort(self.fx.plan, self.fx.sources, self.fx.root, self.fx.sdk.llm, fixture=True, **options)

    def test_rehashed_packet_context_and_repeat_lock_fail_before_http(self):
        self.execute()
        count = len(self.fx.sdk.requests)
        paths = [next((self.fx.root/'packets').glob('*.json')), self.fx.root/'context_lock.json']
        for path in paths:
            original = path.read_bytes()
            payload = read_envelope(path)
            payload['forged'] = True
            save_envelope(path, payload)
            with self.subTest(path=path.name), self.assertRaises(ValueError):
                self.execute(resume=True)
            self.assertEqual(len(self.fx.sdk.requests), count)
            path.write_bytes(original)

    def test_missing_completed_block_state_does_not_recreate_or_replay(self):
        self.execute()
        count = len(self.fx.sdk.requests)
        path = next((self.fx.root/'decision_blocks/0').glob('*/state.json'))
        path.unlink()
        with self.assertRaises((ValueError, FileNotFoundError)):
            self.execute(resume=True)
        self.assertEqual(len(self.fx.sdk.requests), count)
        self.assertFalse(path.exists())

    def test_later_corruption_is_checked_before_resuming_first_point(self):
        self.execute()
        paths = sorted((self.fx.root/'decision_blocks/0').glob('*/state.json'))
        payload = read_envelope(paths[-1])
        payload['branches']['original']['output']['decision_prompt'] += ' sai'
        save_envelope(paths[-1], payload)
        count = len(self.fx.sdk.requests)
        with self.assertRaises(ValueError):
            self.execute(resume=True)
        self.assertEqual(len(self.fx.sdk.requests), count)

    def test_changed_plan_or_source_prevents_any_sdk_invocation(self):
        self.fx.plan['schedule'].reverse()
        with self.assertRaises(ValueError):
            self.execute()
        self.assertFalse(self.fx.sdk.requests)
        self.fx.plan['schedule'].reverse()
        with patch.object(self.fx.sources, 'verify', side_effect=ValueError('Nguồn đã đổi')):
            with self.assertRaises(ValueError):
                self.execute()
        self.assertFalse(self.fx.sdk.requests)

    def test_repeat_without_primary_is_rejected_before_decision(self):
        with self.assertRaises(ValueError):
            self.execute(repeat_id=1)
        self.assertFalse(self.fx.sdk.requests)

    def test_unknown_after_durable_response_resumes_same_uuid_without_second_http(self):
        from core.bic_icl_decisions import save_envelope as real_save
        crashed = []
        def fail(path, payload):
            if path.name == 'state.json' and not crashed and any(
                    b['status'] == 'complete' and b['attempts'] for b in payload['branches'].values()):
                crashed.append(True)
                raise KeyboardInterrupt('Ngắt sau HTTP durable trước commit')
            return real_save(path, payload)
        with patch('core.bic_icl_decisions.save_envelope', side_effect=fail):
            with self.assertRaises(KeyboardInterrupt):
                self.execute()
        self.assertEqual(len(self.fx.sdk.requests), 1)
        path = next((self.fx.root/'decision_blocks/0').glob('*/state.json'))
        before = read_envelope(path)
        attempt_id = before['branches']['original']['attempts'][0]['attempt_id']
        partial = self.execute(verify_only=True)
        self.assertEqual(partial['status'], 'INCOMPLETE')
        self.assertTrue(all(row['evaluation'] is None for row in partial['points']))
        self.assertEqual(len(self.fx.sdk.requests), 1)
        complete = self.execute(resume=True)
        self.assertEqual(complete['status'], 'COMPLETE')
        after = read_envelope(path)
        self.assertEqual(after['branches']['original']['attempts'][0]['attempt_id'], attempt_id)
        self.assertEqual(len(after['branches']['original']['attempts']), 1)
        ledger = self.fx.sdk.pacer.state['requests']
        self.assertEqual(sum(r.get('checkpoint_attempt_id') == attempt_id for r in ledger), 1)

    def test_modified_durable_cache_is_rejected_before_resume(self):
        self.execute()
        count = len(self.fx.sdk.requests)
        path = next(self.fx.sdk.transport.cache_root.glob('*.json'))
        payload = read_envelope(path)
        payload['body_base64'] += 'AAAA'
        save_envelope(path, payload)
        with self.assertRaises(ValueError):
            self.execute(resume=True)
        self.assertEqual(len(self.fx.sdk.requests), count)

    def test_production_requires_release_before_creating_run(self):
        from core.bic_icl_protocol import NAMESPACE
        destination = NAMESPACE/'development_missing_release_fixture'
        with self.assertRaises(ValueError):
            run_cohort(self.fx.plan, self.fx.sources, destination, self.fx.sdk.llm)
        self.assertFalse(destination.exists())
        self.assertFalse(self.fx.sdk.requests)


if __name__ == '__main__':
    unittest.main()
