"""Kiểm phép đo và nguồn context; không đặt ngưỡng tốc độ trong unit test."""

import copy
import unittest

from core.bayesian_memory import copy_historical_records, read_json
from core.bayesian_retriever import _matches_snapshot
from scripts.benchmark_bayesian_retriever import (
    ROOT, SMOKE_PATH, THRESHOLD_NS, measure, select_contexts, stage_receipt, summarize, validate_counts,
)


class BayesianRetrieverBenchmarkTests(unittest.TestCase):
    """Dùng đồng hồ giả để kiểm ranh giới timer và percentile xác định."""

    def test_percentile_nearest_rank_and_strict_gate(self) -> None:
        samples = list(range(1, 1001))
        summary = summarize(samples[::-1])
        self.assertEqual(summary['p95_ns'], 950)
        self.assertEqual(summary['median_ms'], 500.5 / 1e6)
        self.assertEqual(summary['min_ms'], 1 / 1e6)
        self.assertEqual(summary['max_ms'], 1000 / 1e6)
        self.assertFalse(summarize([THRESHOLD_NS])['p95_ns'] < THRESHOLD_NS)
        self.assertTrue(summarize([THRESHOLD_NS - 1])['p95_ns'] < THRESHOLD_NS)
        for invalid in ([], [-1], [True], [1.0]):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                summarize(invalid)

    def test_rotation_warmup_excluded_and_comparison_outside_timer(self) -> None:
        events: list[str] = []
        ticks = iter([10, 15, 100, 107, 200, 211, 300, 313])

        def clock() -> int:
            """Ghi dấu mốc để kiểm phần được bao trong timer."""
            events.append('clock')
            return next(ticks)

        class Output:
            """Đánh dấu so sánh sau khi đồng hồ kết thúc."""

            def __eq__(self, other: object) -> bool:
                events.append('compare')
                return True

        def operation(slot: int) -> Output:
            """Ghi thứ tự query kể cả warm-up."""
            events.append(f'query_{slot}')
            return Output()

        durations = measure([lambda: operation(0), lambda: operation(1)], [0, 1], warmup=3, samples=4, clock=clock)
        self.assertEqual(durations, [5, 7, 11, 13])
        self.assertEqual(events[:6], ['query_0', 'compare', 'query_1', 'compare', 'query_0', 'compare'])
        self.assertEqual(events[6:], [item for slot in (0, 1, 0, 1)
                                     for item in ('clock', f'query_{slot}', 'clock', 'compare')])

    def test_wrong_output_and_backward_clock_rejected(self) -> None:
        ticks = iter([10, 20])
        with self.assertRaisesRegex(ValueError, 'khác kết quả'):
            measure([lambda: 'bad'], ['good'], warmup=0, samples=1, clock=lambda: next(ticks))
        ticks = iter([20, 10])
        with self.assertRaisesRegex(ValueError, 'đơn điệu'):
            measure([lambda: 'good'], ['good'], warmup=0, samples=1, clock=lambda: next(ticks))
        with self.assertRaises(ValueError):
            measure([], [], warmup=0, samples=1)

    def test_locked_minimum_counts(self) -> None:
        validate_counts(100, 1000)
        for counts in ((99, 1000), (100, 999), (True, 1000), (100, 1000.0)):
            with self.subTest(counts=counts), self.assertRaises(ValueError):
                validate_counts(*counts)

    def test_scope_statistics_follow_rotating_sample_indices(self) -> None:
        result = stage_receipt([1, 100, 2, 200, 3], [{'scope': 'same_symbol'}, {'scope': 'pooled'}])
        self.assertEqual(result['summary']['count'], 5)
        self.assertEqual(result['by_scope']['same_symbol']['count'], 3)
        self.assertEqual(result['by_scope']['pooled']['p95_ns'], 200)
        self.assertEqual(result['samples_ns'], [1, 100, 2, 200, 3])

    def test_contexts_cover_real_symbols_regimes_and_reject_stale_source(self) -> None:
        smoke = read_json(SMOKE_PATH)
        records = read_json(ROOT / 'data_manager/regime_memory_store.json')
        baseline = copy.deepcopy(smoke)
        self.assertEqual(len(select_contexts(smoke, records)), 16)
        self.assertEqual(smoke, baseline)
        for field in ('model_train_end_date', 'source_as_of_date'):
            bad = copy.deepcopy(smoke)
            context = next(c for c in bad['contexts'] if c['case_kind'] == 'observed')
            context['source'][field] = '2099-01-01'
            with self.subTest(field=field), self.assertRaises(ValueError):
                select_contexts(bad, records)
        bad = copy.deepcopy(smoke)
        bad['contexts'].append(copy.deepcopy(next(c for c in bad['contexts'] if c['case_kind'] == 'observed')))
        with self.assertRaises(ValueError):
            select_contexts(bad, records)

    def test_schema_copy_matches_deepcopy_and_isolates_every_mutable_level(self) -> None:
        records = read_json(ROOT / 'data_manager/regime_memory_store.json')[:2]
        before = copy.deepcopy(records)
        cloned = copy_historical_records(records)
        self.assertEqual(cloned, before)
        for original, returned in zip(records, cloned):
            self.assertIsNot(original, returned)
            self.assertIsNot(original['agent_signals'], returned['agent_signals'])
            self.assertIsNot(original['outcome'], returned['outcome'])
            returned['symbol'] = 'CHANGED'
            returned['agent_signals']['trend'] = 'CHANGED'
            returned['outcome']['net_return_pct'] = 999
        self.assertEqual(records, before)

    def test_schema_copy_fallback_preserves_invalid_types_and_extra_nested_data(self) -> None:
        import numpy as np

        record = read_json(ROOT / 'data_manager/regime_memory_store.json')[0]
        record['extra'] = {'nested': [1, {'flag': True}]}
        record['outcome']['net_return_pct'] = np.float64(1)
        cloned = copy_historical_records([record])[0]
        self.assertEqual(cloned, copy.deepcopy(record))
        self.assertIs(type(cloned['outcome']['net_return_pct']), np.float64)
        cloned['extra']['nested'][1]['flag'] = False
        self.assertTrue(record['extra']['nested'][1]['flag'])

    def test_snapshot_comparison_preserves_types_keys_and_values(self) -> None:
        import numpy as np

        expected = read_json(ROOT / 'data_manager/regime_memory_store.json')[0]
        self.assertTrue(_matches_snapshot(copy.deepcopy(expected), expected))
        for mutate in (lambda r: r.update(exit_date='2099-01-01'),
                       lambda r: r.update(extra=True),
                       lambda r: r.pop('symbol'),
                       lambda r: r['outcome'].update(was_bull_trap=np.bool_(r['outcome']['was_bull_trap'])),
                       lambda r: r['outcome'].update(net_return_pct=np.float64(r['outcome']['net_return_pct'])),
                       lambda r: r['outcome'].update(net_return_pct=float('nan')),
                       lambda r: r['agent_signals'].update(trend=np.str_(r['agent_signals']['trend'])),
                       lambda r: r['agent_signals'].pop('sentiment')):
            actual = copy.deepcopy(expected)
            mutate(actual)
            self.assertFalse(_matches_snapshot(actual, expected))


if __name__ == '__main__':
    unittest.main()
