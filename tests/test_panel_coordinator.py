"""Kiểm namespace độc lập, bốn scope, preflight, interruption và cold SDK bằng HTTP giả."""

from contextlib import redirect_stdout
from copy import deepcopy
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx

from core.groq_pacing import PilotStop
from core.improvement_recovery import ResilientPacer
from core.mt_bicl_v4_collect import clients
from core.mt_bicl_v4_completion import DataCompletionError
from core.mt_bicl_v4_dataset import immutable
from core.mt_bicl_v4_protocol import read
from core.panel_collection import cold_point, collect_point, controls
from core.panel_coordinator import PanelLayout, PanelTransport, bind, read_bindings, run
from test_mt_bicl_v4_collection import runtime as old_runtime

COLLECTION = Path('outputs/bayesian_benchmark/mt_bicl_v4_1_r2/collection')
DATA = COLLECTION.parent / 'data'
RELEASE = Path('docs/plan/week11/collection_release_v4_1_r2.json')


def runtime(root: Path) -> tuple:
    """SDK/graph thật với giá synthetic và provider MockTransport; không đọc .env."""
    row, frame, release, pacer, original, old_http, _, wires = old_runtime(root)
    release.update(point_ids=[row['episode_id']], shards={f'scope_{i}': [row['episode_id']] if i == 1 else [] for i in range(1, 5)},
                   credential_variables=[f'GROQ_API_KEY_{i}' for i in range(1, 5)])
    transport = PanelTransport(pacer, root / COLLECTION / 'http_cache', original.inner.inner)
    http = httpx.Client(transport=transport)
    llms = clients(release['config'], http, 'fixture-not-a-real-key')
    old_http.close()
    return row, frame, release, pacer, transport, http, llms, wires


class CoordinatorTests(unittest.TestCase):
    """Raw cache mất của lượt cũ không được chặn hoặc biến thành kết quả lượt mới."""

    def test_new_namespace_ignores_missing_old_raw_but_preserves_ledger(self) -> None:
        with TemporaryDirectory() as temporary, redirect_stdout(io.StringIO()):
            root = Path(temporary)
            row, frame, release, pacer, _, http, llms, wires = runtime(root)
            old = {'id': 'old-lost-fixture', 'status': 200, 'run_signature': 'old-signature',
                   'durable_response': {'sha256': 'f' * 64}}
            pacer.state['requests'].append(old)
            pacer.save()
            saved = collect_point(root, row, frame, [], release, 'b' * 64, llms, lambda: pacer.state, collection=COLLECTION)
            self.assertEqual(len(wires), 3)
            self.assertEqual(saved, cold_point(root, row, frame, [], release, 'b' * 64, pacer.state, collection=COLLECTION))
            self.assertEqual(pacer.state['requests'][0], old)
            self.assertFalse((root / 'outputs/bayesian_benchmark/mt_bicl_v4_1/collection/points').exists())
            http.close()

    def test_interruption_reuses_same_UUID_and_durable_raw(self) -> None:
        with TemporaryDirectory() as temporary, redirect_stdout(io.StringIO()):
            root = Path(temporary)
            row, frame, release, pacer, transport, http, llms, wires = runtime(root)
            store = transport._store
            stopped = []

            def stop_once(request, response):
                """Ngắt sau khi raw và ledger đã durable, trước checkpoint node."""
                store(request, response)
                if not stopped:
                    stopped.append(True)
                    raise KeyboardInterrupt()

            with patch.object(transport, '_store', stop_once), self.assertRaises(KeyboardInterrupt):
                collect_point(root, row, frame, [], release, 'b' * 64, llms, lambda: pacer.state, collection=COLLECTION)
            before = deepcopy(pacer.state['requests'][0])
            collect_point(root, row, frame, [], release, 'b' * 64, llms, lambda: pacer.state, collection=COLLECTION)
            self.assertEqual(len(wires), 3)
            self.assertEqual(pacer.state['requests'][0], before)
            http.close()

    def test_missing_new_sealed_raw_stops_without_new_HTTP(self) -> None:
        with TemporaryDirectory() as temporary, redirect_stdout(io.StringIO()):
            root = Path(temporary)
            row, frame, release, pacer, _, http, llms, wires = runtime(root)
            saved = collect_point(root, row, frame, [], release, 'b' * 64, llms, lambda: pacer.state, collection=COLLECTION)
            rid = next(iter(saved['http']['raw_sha256']))
            (root / COLLECTION / 'http_cache' / (rid + '.json')).unlink()
            with self.assertRaises((OSError, DataCompletionError)):
                collect_point(root, row, frame, [], release, 'b' * 64, llms, lambda: pacer.state, collection=COLLECTION)
            self.assertEqual(len(wires), 3)
            http.close()

    def test_binding_rebind_is_append_only_and_outside_panel_fails(self) -> None:
        with TemporaryDirectory() as temporary, redirect_stdout(io.StringIO()):
            root = Path(temporary)
            row, frame, release, pacer, _, http, llms, wires = runtime(root)
            immutable(root / RELEASE, {'fixture': True})
            layout = PanelLayout(COLLECTION, DATA, RELEASE, lambda *_: ({}, {}, 'b' * 64))
            keys = {n: 'fixture-' + n for n in release['shards']}
            first = bind(root, release, keys, layout=layout)
            original = (root / COLLECTION / 'bindings/0000.json').read_bytes()
            keys['scope_3'] = 'fixture-new-key'
            with self.assertRaises(DataCompletionError):
                bind(root, release, keys, layout=layout)
            second = bind(root, release, keys, rebind='scope_3', layout=layout)
            self.assertEqual(read_bindings(root, release, layout=layout), [first, second])
            self.assertEqual((root / COLLECTION / 'bindings/0000.json').read_bytes(), original)
            release['point_ids'] = []
            with self.assertRaises(DataCompletionError):
                collect_point(root, row, frame, [], release, 'b' * 64, llms, lambda: pacer.state, collection=COLLECTION)
            self.assertEqual(wires, [])
            http.close()

    def exercise_coordinator(self, *, daily_quota: bool) -> None:
        """Chạy đủ lệnh với HTTP giả, rồi chứng minh resume complete không đọc key."""
        with TemporaryDirectory() as temporary, redirect_stdout(io.StringIO()):
            root = Path(temporary)
            row, frame, release, pacer, transport, http, _, wires = runtime(root)
            immutable(root / RELEASE, {'fixture': True})
            immutable(root / DATA / 'observations.json', {'rows': [row]})
            for symbol in release['config']['symbol_order']:
                immutable(root / f'outputs/historical_memory_run/inputs/news/{symbol}.json', {'scored_articles': []})
            pacer.path = root / 'outputs/oos_pilot/api_usage.json'
            pacer.save()
            layout = PanelLayout(COLLECTION, DATA, RELEASE, lambda *_: ({'FPT': frame}, {}, 'b' * 64))
            keys = {f'scope_{i}': 'fixture-key-' + str(i) for i in range(1, 5)}
            normal = transport.inner.inner.handler
            failed = []

            def provider(request):
                """Scope1 hết quota ở probe đầu, các scope khác vẫn được kiểm trước."""
                if daily_quota and request.headers.get('authorization') == 'Bearer fixture-key-1' and not failed:
                    failed.append(True)
                    return httpx.Response(429, json={'error': {'message': 'TPD daily limit retry after 1 seconds'}},
                        headers={'retry-after': '1'}, request=request)
                return normal(request)

            def pacer_factory(path, credential, amendment_sha256, **kwargs):
                """Đồng hồ giả không ngủ thật hoặc truy cập quota từ xa."""
                return ResilientPacer(path, credential=credential, amendment_sha256=amendment_sha256,
                    clock=pacer.clock, monotonic=pacer.monotonic, sleep=pacer.sleep, **kwargs)

            with patch('core.panel_coordinator.credentials', return_value=keys) as credential, \
                 patch('core.panel_coordinator.ResilientPacer', side_effect=pacer_factory), \
                 patch('core.panel_coordinator.PanelTransport', side_effect=lambda p, c: PanelTransport(p, c, httpx.MockTransport(provider))), \
                 patch('scripts.prepare_groq_tokenizer.prepare_tokenizer'):
                result = run(root, release, layout=layout, clock=pacer.clock, sleep=pacer.sleep)
                self.assertEqual(result['complete'], 1)
                credential.assert_called_once()
            recorded = read(pacer.path.read_bytes())['requests']
            success = [r for r in recorded if r['status'] == 200]
            self.assertTrue(all(r['point_id'].startswith('CONTROL_') for r in success[:12]))
            self.assertEqual(len(wires), 15)
            if daily_quota:
                resumed = [r for r in recorded if r.get('checkpoint_attempt_id') == recorded[0]['checkpoint_attempt_id']]
                self.assertEqual([r['status'] for r in resumed], [429, 200])
            before = deepcopy(recorded)
            with patch('core.panel_coordinator.credentials', side_effect=AssertionError('Không đọc key')), \
                 patch('scripts.prepare_groq_tokenizer.prepare_tokenizer', side_effect=AssertionError('Không tải tokenizer')):
                self.assertEqual(run(root, release, offline=True, layout=layout, clock=pacer.clock)['complete'], 1)
            self.assertEqual(read(pacer.path.read_bytes())['requests'], before)
            self.assertEqual(len(wires), 15)
            http.close()

    def test_full_command_and_offline_resume(self) -> None:
        self.exercise_coordinator(daily_quota=False)

    def test_all_four_probes_must_pass_after_daily_quota_before_market(self) -> None:
        self.exercise_coordinator(daily_quota=True)

    def test_too_large_request_stops_without_retry_or_silent_model_change(self) -> None:
        with TemporaryDirectory() as temporary, redirect_stdout(io.StringIO()):
            root = Path(temporary)
            _, _, release, pacer, transport, http, llms, _ = runtime(root)
            transport.inner.inner.handler = lambda request: httpx.Response(429,
                json={'error': {'message': 'Request too large, Requested 1024 exceeds OTPM Limit 1000'}}, request=request)
            with self.assertRaises(PilotStop):
                controls(root, release, 'b' * 64, llms, pacer, collection=COLLECTION)
            self.assertEqual(pacer.state['last_stop']['reason'], 'PROVIDER_REQUEST_EXCEEDS_LIMIT')
            self.assertEqual(len(pacer.state['requests']), 1)
            http.close()

    def test_future_price_and_news_cannot_change_binding(self) -> None:
        with TemporaryDirectory() as temporary, redirect_stdout(io.StringIO()):
            root = Path(temporary)
            row, frame, release, pacer, _, http, llms, wires = runtime(root)
            collect_point(root, row, frame, [], release, 'b' * 64, llms, lambda: pacer.state, collection=COLLECTION)
            changed = frame.copy(deep=True)
            changed.loc[changed['Datetime'] > row['as_of_date'], ['Open', 'High', 'Low', 'Close']] *= 100
            cold_point(root, row, changed, [{'date_parsed': '2025-01-01', 'title': 'Tin tương lai'}], release,
                       'b' * 64, pacer.state, collection=COLLECTION)
            self.assertEqual(len(wires), 3)
            http.close()


if __name__ == '__main__':
    unittest.main()
