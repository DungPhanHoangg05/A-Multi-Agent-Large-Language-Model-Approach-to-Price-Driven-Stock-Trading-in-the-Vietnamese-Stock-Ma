"""Kiểm T27 không đếm replay hai lần, giấu retries hoặc lấp provenance thiếu."""

from copy import deepcopy
import io
from pathlib import Path
import unittest

from PIL import Image

from core.revision_reproducibility import offline_guard
from core.revision_common_study import digest
from scripts.analyze_revision_final_costs import attempt_key, build, capture_text, compare_png, retries, retry_wait, summarize, validate_upstream_jobs


def request() -> dict:
    """Định danh giả chỉ chứa schema, không key/client/network."""
    return {'context': {'unit_id': 'ABC_1', 'realization': 0, 'node': 'Decision Maker', 'variant': 'B',
                        'repeat': 0, 'provider_org': 1, 'execution_epoch': 'old'},
            'messages': ['same prompt'], 'model_metadata': {'ls_model_name': 'fixed'},
            'invocation_parameters': {'response_format': 'schema'}}


def row(attempt: str, outcome: str, stamp: str) -> dict:
    """Một attempt có usage success hoặc thiếu hoàn toàn khi error."""
    return {'attempt_id': attempt, 'outcome': outcome, 'started_at_utc': stamp,
            'execution_epoch': 'epoch', 'selected_job_id': 'job' if outcome == 'success' else None,
            'node': 'Decision Maker', 'prompt_tokens': 10 if outcome == 'success' else None,
            'completion_tokens': 2 if outcome == 'success' else None,
            'latency_seconds': 1.5 if outcome == 'success' else None}


class FinalCostTests(unittest.TestCase):
    """Bảo vệ mẫu số, raw identity và từ chối giả lập quan sát còn thiếu."""

    def test_retry_identity_ignores_only_routing_and_epoch(self) -> None:
        source = request(); changed = deepcopy(source)
        changed['context'].update(provider_org=5, execution_epoch='new')
        self.assertEqual(attempt_key(source), attempt_key(changed))
        for field in ('unit_id', 'realization', 'variant', 'repeat', 'org'):
            changed = deepcopy(source); changed['context'][field] = 'different'
            self.assertNotEqual(attempt_key(source), attempt_key(changed))
        for field in ('messages', 'model_metadata', 'invocation_parameters'):
            changed = deepcopy(source); changed[field] = ['different']
            self.assertNotEqual(attempt_key(source), attempt_key(changed))

    def test_retries_keep_errors_and_cross_epoch_without_invented_sleep(self) -> None:
        rows = [row('error', 'error', '01'), row('ok', 'success', '02')]
        rows[0]['execution_epoch'] = 'old'
        result = retries(rows, {r['attempt_id']: request() for r in rows})
        self.assertEqual(result[0]['failed_attempts_before_success'], 1)
        self.assertTrue(result[0]['cross_epoch'])
        self.assertIsNone(result[0]['actual_sleep_seconds'])
        self.assertEqual([r['attempt_ordinal'] for r in rows], [1, 2])
        self.assertTrue(all(r['resolved_job_id'] == 'job' for r in rows))

    def test_missing_duplicate_or_later_attempt_after_success_rejected(self) -> None:
        for rows in ([row('a', 'error', '01')], [row('a', 'success', '01'), row('b', 'success', '02')],
                     [row('a', 'success', '01'), row('b', 'error', '02')]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                retries(rows, {r['attempt_id']: request() for r in rows})

    def test_unknown_usage_latency_and_billing_remain_null(self) -> None:
        error = row('error', 'error', '01'); success = row('ok', 'success', '02')
        missing = summarize([error]); mixed = summarize([error, success])
        self.assertIsNone(missing['prompt_tokens_observed_sum'])
        self.assertIsNone(missing['latency_seconds_p95'])
        self.assertIsNone(mixed['monetary_cost'])
        self.assertEqual((mixed['attempts'], mixed['successes'], mixed['errors']), (2, 1, 1))
        self.assertEqual((mixed['prompt_tokens_observed_sum'], mixed['prompt_tokens_n_observed'], mixed['prompt_tokens_n_missing']), (10, 1, 1))
        self.assertEqual(mixed['latency_seconds_observed_sum'], 1.5)

    def test_provider_wait_is_observation_not_actual_sleep(self) -> None:
        self.assertAlmostEqual(retry_wait('Please try again in 10m7.824s.'), 607.824)
        self.assertEqual(retry_wait('retry after 2.5 seconds'), 2.5)
        self.assertEqual(retry_wait('try again in 1h2m3s'), 3723.)
        self.assertIsNone(retry_wait('429 without documented wait'))

    def test_changed_image_pixels_or_bytes_rejected(self) -> None:
        def png(color: str) -> bytes:
            """Ảnh tổng hợp nhỏ để kiểm tamper, không thay ảnh nghiên cứu."""
            stream = io.BytesIO(); Image.new('RGB', (2, 2), color).save(stream, format='PNG')
            return stream.getvalue()
        green = png('green'); compare_png(green, green)
        with self.assertRaises(ValueError): compare_png(green, png('red'))
        with self.assertRaises(ValueError): compare_png(green, green + b'changed metadata')

    def test_distinct_phase_parent_hashes_cannot_hide_changed_nodes(self) -> None:
        nodes = ['indicator', 'pattern', 'trend']; run = 'run'
        jobs = [{'phase': 'main', 'origin_parent': {'node_hashes': nodes, 'run_signature': run, 'upstream_hash': 'state'}},
                {'phase': 'factorial', 'origin_parent': {'upstream_hash': digest({'node_hashes': nodes, 'run_signature': run})}}]
        validate_upstream_jobs(jobs, nodes, run, 'state')
        changed = deepcopy(jobs); changed[1]['origin_parent']['upstream_hash'] = 'state'
        with self.assertRaises(ValueError): validate_upstream_jobs(changed, nodes, run, 'state')
        with self.assertRaises(ValueError): validate_upstream_jobs(jobs, ['indicator', 'old pattern', 'trend'], run, 'state')

    def test_actual_node_templates_can_be_captured_without_network(self) -> None:
        with offline_guard():
            pattern = capture_text('pattern', 'vi'); trend = capture_text('trend', 'vi')
        self.assertTrue(pattern and trend)
        self.assertNotEqual(pattern, trend)
        self.assertIn('xanh', '\n'.join(trend))

    def test_output_guard_rejects_paper_existing_and_nested_paths(self) -> None:
        for path in ('paper', 'outputs/revision/revision_minimal_final_v1', 'outputs/revision/new/sub'):
            with self.subTest(path=path), self.assertRaises(ValueError): build(Path.cwd(), Path(path))


if __name__ == '__main__':
    unittest.main()
