"""Release tự khai, snapshot đổi nguồn/PIT/request và sai run phải dừng trước HTTP."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from bic_icl_release_support import ReleaseFixture
from core.bic_icl_protocol import read_authorization
from core.bic_icl_release import _population, issue_development_release, verify_development_release
from core.bic_icl_runtime import hashlib_sha
from core.research_cohort import read_envelope, save_envelope
from scripts.run_bic_icl import main as runner_main


class DevelopmentReleaseLeakageTests(unittest.TestCase):
    def setUp(self) -> None:
        quiet = patch('builtins.print')
        quiet.start()
        self.addCleanup(quiet.stop)
        self.fx = ReleaseFixture()
        self.addCleanup(self.fx.close)
        for item in self.fx.patches():
            item.start()
            self.addCleanup(item.stop)

    def issue(self):
        return issue_development_release(self.fx.path, self.fx.gates, self.fx.plan, self.fx.sources,
            self.fx.root, ledger_path=self.fx.ledger)

    def verify(self, **options):
        return verify_development_release(self.fx.path, self.fx.gates, self.fx.plan, **options)

    def test_gate_failure_creates_no_run_or_release(self):
        gate = read_envelope(self.fx.gates)
        gate['checks']['unit'].update(status='FAIL', exit_code=1)
        save_envelope(self.fx.gates, gate)
        with self.assertRaises(ValueError):
            self.issue()
        self.assertFalse(self.fx.path.exists())
        self.assertFalse(self.fx.root.exists())

    def test_source_failure_creates_no_run_even_with_passing_receipt(self):
        with patch.object(self.fx.sources, 'validate', side_effect=ValueError('Nguồn đã đổi')):
            with self.assertRaises(ValueError):
                self.issue()
        self.assertFalse(self.fx.root.exists())

    def test_fresh_confirmation_or_partial_cohort_cannot_issue_cache_release(self):
        for changes in ({'upstream_policy': 'FRESH_SHARED'}, {'split': 'confirmation_2025'}, {'schedule': []}):
            plan = {**self.fx.plan, **changes}
            with patch.object(self.fx.sources, 'validate'), self.assertRaises(ValueError):
                _population(plan, self.fx.sources)
        self.assertFalse(self.fx.cohort.sdk.requests)

    def test_changed_or_missing_packet_blocks_consumer_and_reissue_without_repair(self):
        self.issue()
        path = self.fx.root/'packets'/f"{self.fx.packets[0]['point_id']}.json"
        path.unlink()
        for call in (self.verify, self.issue):
            with self.assertRaises((ValueError, FileNotFoundError)):
                call()
            self.assertFalse(path.exists())

    def test_rehashed_future_packet_does_not_replace_pit_source(self):
        payload = self.issue()
        relative = 'packets/'+self.fx.packets[0]['point_id']+'.json'
        path = self.fx.root/relative
        value = read_envelope(path)
        value['source_proof']['context']['as_of_date'] = '2099-01-01'
        save_envelope(path, value)
        payload['snapshot_sha256'][relative] = hashlib_sha(path)
        save_envelope(self.fx.path, payload)
        with self.assertRaises(ValueError):
            self.verify()
        self.assertFalse(self.fx.cohort.sdk.requests)

    def test_rehashed_order_or_canonical_sdk_body_cannot_replace_requests(self):
        self.issue()
        path = self.fx.root/'request_manifest.json'
        before, release = path.read_bytes(), self.fx.path.read_bytes()
        for mutate in ('order', 'schema'):
            value = read_envelope(path)
            if mutate == 'order':
                value['blocks'][0]['requests'].reverse()
            else:
                value['blocks'][0]['requests'][0]['contract']['response_format_sha256'] = 'a'*64
            save_envelope(path, value)
            payload = read_envelope(self.fx.path)
            from core.historical_signals import digest
            payload['snapshot_sha256']['request_manifest.json'] = hashlib_sha(path)
            payload['request_manifest_sha256'] = digest(value)
            save_envelope(self.fx.path, payload)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                self.verify()
            path.write_bytes(before)
            self.fx.path.write_bytes(release)

    def test_wrong_run_or_ledger_rejected_before_credential_or_decision(self):
        self.issue()
        for options in ({'run_root': self.fx.base/'development_other'}, {'ledger_path': self.fx.base/'other.json'}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                read_authorization(self.fx.path, self.fx.gates, self.fx.plan, **options)
        self.assertFalse(self.fx.cohort.sdk.requests)

    def test_missing_snapshot_or_old_self_declared_release_is_not_authorization(self):
        payload = self.issue()
        del payload['snapshot_sha256']['request_manifest.json']
        save_envelope(self.fx.path, payload)
        with self.assertRaises(ValueError):
            self.verify()
        for key in ('snapshot_sha256', 'run_binding', 'request_manifest_sha256'):
            payload.pop(key, None)
        save_envelope(self.fx.path, payload)
        with self.assertRaises(ValueError):
            read_authorization(self.fx.path, self.fx.gates, self.fx.plan)

    def test_cannot_issue_after_decision_started_or_overwrite_wrong_partial_lock(self):
        self.fx.root.mkdir()
        (self.fx.root/'primary_ready.json').write_text('{}', encoding='utf8')
        with self.assertRaises(ValueError):
            self.issue()
        self.assertFalse(self.fx.path.exists())
        (self.fx.root/'primary_ready.json').unlink()
        save_envelope(self.fx.root/'context_lock.json', {'forged': True})
        with self.assertRaises(ValueError):
            self.issue()
        self.assertEqual(read_envelope(self.fx.root/'context_lock.json'), {'forged': True})
        self.assertFalse((self.fx.root/'cohort.json').exists())

    def test_auth_rechecks_gate_release_and_snapshot_before_later_http(self):
        self.issue()
        auth = read_authorization(self.fx.path, self.fx.gates, self.fx.plan)
        path = self.fx.root/'context_lock.json'
        value = read_envelope(path)
        value['repeat_sample'].reverse()
        save_envelope(path, value)
        with self.assertRaises(ValueError):
            auth.verify(self.fx.plan)

    def test_changed_gate_and_release_cannot_reuse_cached_authorization(self):
        self.issue()
        auth = read_authorization(self.fx.path, self.fx.gates, self.fx.plan)
        log = self.fx.gates.parent/'unit.log'
        before = log.read_bytes()
        log.write_text('Ran 1 test in 0.001s\nFAILED\n', encoding='utf8')
        with self.assertRaises(ValueError):
            auth.verify(self.fx.plan)
        log.write_bytes(before)
        changed = auth.payload
        changed['confirmation_allowed'] = True
        save_envelope(self.fx.path, changed)
        with self.assertRaises(ValueError):
            auth.verify(self.fx.plan)

    def test_online_wrong_root_stops_before_dotenv_and_http(self):
        self.issue()
        with patch('scripts.run_bic_icl.CohortSources', return_value=self.fx.sources), patch(
                'scripts.run_bic_icl.read_envelope', return_value=self.fx.plan), patch(
                'dotenv.dotenv_values', side_effect=AssertionError('Sai binding phải dừng trước key')):
            with self.assertRaises(ValueError):
                runner_main(['--preflight', '--plan', str(self.fx.base/'development_plan_fixture.json'),
                    '--output-dir', str(self.fx.base/'development_other'),
                    '--handoff', str(self.fx.path), '--technical-gates', str(self.fx.gates)])
        self.assertFalse(self.fx.cohort.sdk.requests)

    def test_lost_release_and_checkpoint_cannot_replay_existing_ledger_intent(self):
        import json
        payload = self.issue()
        self.fx.path.unlink()
        (self.fx.root/'cohort.json').unlink()
        self.fx.ledger.write_text(json.dumps({'requests': [{'run_signature':
            payload['run_binding']['run_signature'], 'status': 'unknown'}]}), encoding='utf8')
        with self.assertRaises(ValueError):
            self.issue()
        self.assertFalse(self.fx.path.exists())
        self.assertFalse((self.fx.root/'cohort.json').exists())

    def test_malformed_ledger_prevents_issuance_before_any_snapshot(self):
        self.fx.ledger.write_text('{"requests": null}', encoding='utf8')
        with self.assertRaises(ValueError):
            self.issue()
        self.assertFalse(self.fx.path.exists())
        self.assertFalse(self.fx.root.exists())


if __name__ == '__main__':
    unittest.main()
