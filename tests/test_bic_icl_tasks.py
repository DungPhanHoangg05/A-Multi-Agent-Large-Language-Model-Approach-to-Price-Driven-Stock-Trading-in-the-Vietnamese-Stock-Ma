"""Oracle task 20 phiên, centroid, cặp intrinsic và diversity toàn demonstrations."""

from copy import deepcopy
import json
import unittest

import pandas as pd

from core.bic_icl_tasks import TaskSelector, group_task_cycles, select_tasks
from core.bic_icl_prompt import build_context_evidence
from core.bic_icl_statistics import pool_evidence
from core.price_feature_index import build_price_feature_index
from bic_icl_tasks_support import TaskFixture


class TaskGroupingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = TaskFixture()

    def plan(self, rows: list[dict]) -> dict:
        return group_task_cycles(rows, [0., 0., 0., 0.], symbol='FPT', regime='BULL', as_of_date='2022-01-06')

    def test_anchor_and_block_boundary_use_asof_not_entry(self) -> None:
        selector = self.fx.selector
        self.assertEqual(selector.task_id('FPT', 'BULL', self.fx.day(0)), 'FPT:BULL:0000')
        self.assertEqual(selector.task_id('FPT', 'BULL', self.fx.day(19)), 'FPT:BULL:0000')
        self.assertEqual(selector.task_id('FPT', 'BULL', self.fx.day(20)), 'FPT:BULL:0001')
        self.assertEqual(selector.task_id('FPT', 'BULL', self.fx.day(639)), 'FPT:BULL:0031')
        self.assertEqual(selector.task_id('FPT', 'BULL', self.fx.day(640)), 'FPT:BULL:0032')

    def test_calendar_cannot_start_in_later_year_even_if_index_matches(self) -> None:
        inputs = {**self.fx.inputs, 'calendar': self.fx.calendar[self.fx.calendar >= '2019-01-01']}
        inputs['prices'] = {symbol: (frame.loc[frame.Datetime >= '2019-01-01'].copy(), events)
                            for symbol, (frame, events) in self.fx.prices.items()}
        index = build_price_feature_index(**inputs)
        with self.assertRaisesRegex(ValueError, '2018-01-02'):
            TaskSelector(index, inputs['calendar'])

    def test_centroid_includes_all_qualified_members_not_only_pair(self) -> None:
        rows = [self.fx.row(p, rank, [v]*4) for rank, (p, v) in enumerate(((640, 0.), (646, 2.), (652, 10.)), 1)]
        task = self.plan(rows)['task_trace'][0]
        self.assertEqual(task['centroid'], [4.]*4)
        self.assertEqual(task['centroid_distance'], 4.)
        self.assertEqual(task['intrinsic_pair'], [r['episode_id'] for r in rows[:2]])

    def test_rank_centroid_distance_before_recency_then_stable_ids(self) -> None:
        rows = [self.fx.row(p, rank, [v]*4) for rank, (p, v) in enumerate(((640, .1), (646, .1), (660, .2), (666, .2)), 1)]
        plan = self.plan(rows)
        self.assertEqual(plan['ranked_task_ids'], ['FPT:BULL:0032', 'FPT:BULL:0033'])
        for r in rows:
            r['scaled_vector'] = [0.]*4
        plan = self.plan(rows)
        self.assertEqual(plan['ranked_task_ids'], ['FPT:BULL:0033', 'FPT:BULL:0032'])
        self.assertEqual(plan, self.plan(rows[::-1]))

    def test_intrinsic_legacy_rank_gap_four_rejects_five_accepts(self) -> None:
        rows = [self.fx.row(p, rank) for rank, p in enumerate((640, 644, 645), 1)]
        task = self.plan(rows)['task_trace'][0]
        self.assertEqual(task['intrinsic_pair'], [rows[0]['episode_id'], rows[2]['episode_id']])
        self.assertEqual(task['cycle_trace'][1]['reason'], 'INTRINSIC_DIVERSITY_CONFLICT')
        self.assertEqual(task['cycle_trace'][1]['conflicting_ids'], [rows[0]['episode_id']])

    def test_single_cycle_and_only_overlapping_cycles_never_make_fake_pair(self) -> None:
        for positions in ((640,), (640, 642), (640, 643, 644)):
            result = self.plan([self.fx.row(p, i) for i, p in enumerate(positions, 1)])
            self.assertEqual(result['selected_episode_ids'], [])
            self.assertEqual(result['task_trace'][0]['reason_codes'], ['NO_INTRINSIC_PAIR'])

    def test_global_conflict_drops_whole_pair_and_continues_next_task(self) -> None:
        specs = [(654, 0.), (659, 0.), (661, .1), (666, .1), (671, .1), (681, .2), (686, .2)]
        result = self.plan([self.fx.row(p, i, [v]*4) for i, (p, v) in enumerate(specs, 1)])
        trace = {t['task_id']: t for t in result['task_trace']}
        self.assertEqual(result['selected_task_ids'], ['FPT:BULL:0032', 'FPT:BULL:0034'])
        self.assertEqual(trace['FPT:BULL:0033']['reason_codes'], ['GLOBAL_DIVERSITY_CONFLICT'])
        self.assertEqual(trace['FPT:BULL:0033']['intrinsic_pair'], [f'FPT:{self.fx.day(p)}' for p in (661, 666)])

    def test_limit_three_tasks_six_cycles_without_changing_pair_size(self) -> None:
        positions = [p for start in (600, 620, 640, 660, 680) for p in (start+1, start+7)]
        result = self.plan([self.fx.row(p, i) for i, p in enumerate(positions, 1)])
        self.assertEqual(len(result['selected_task_ids']), 3)
        self.assertEqual(len(result['selected_episode_ids']), 6)
        self.assertEqual(sum(t['reason_codes'] == ['K_TASKS_LIMIT'] for t in result['task_trace']), 2)


class TaskEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = TaskFixture()

    def test_production_selector_chooses_three_latest_tasks_with_two_cycles(self) -> None:
        result = select_tasks(self.fx.retriever, **self.fx.query())
        self.assertEqual(result['selected_task_ids'], ['FPT:BULL:0050', 'FPT:BULL:0049', 'FPT:BULL:0048'])
        self.assertEqual(result['selected_episode_ids'], [f'FPT:{self.fx.day(p)}' for p in (1007, 1001, 987, 981, 967, 961)])
        self.assertEqual(result['metadata']['k_tasks'], 3)
        self.assertEqual(result['metadata']['k_episodes'], 6)
        self.assertEqual(result['metadata']['examples_per_task'], 2)
        for key in result['selected_episode_ids']:
            self.assertEqual(result['prior_features'][key]['raw_vector'], [0.]*4)
        self.assertEqual(json.loads(json.dumps(result, allow_nan=False)), result)

    def test_posterior_and_pool_selection_unchanged_when_task_examples_added(self) -> None:
        options = {**self.fx.query(), 'strength': 8}
        pool = pool_evidence(self.fx.retriever, **options)
        context = build_context_evidence(self.fx.retriever, **options)
        self.assertEqual(context['pool'], pool)
        self.assertEqual(context['gate']['R_task']['stats_ready'], context['gate']['R_pool']['stats_ready'])
        self.assertEqual(context['pool']['statistics']['population_count'], 44)
        self.assertEqual(len(context['content_views']['R_task']['full_prior']['visible_example_ids']), 6)
        self.assertEqual(len(context['content_views']['R_pool']['full_prior']['visible_example_ids']), 3)

    def test_task_readiness_does_not_let_six_examples_replace_twenty_population(self) -> None:
        self.fx.records = [r for r in self.fx.records if r['regime'] == 'BEAR' or r['as_of_date'] >= self.fx.day(960)]
        self.fx.publish()
        context = build_context_evidence(self.fx.retriever, strength=8, **self.fx.query())
        self.assertTrue(context['gate']['R_task']['stats_ready'])
        self.assertFalse(context['gate']['R_task']['examples_ready'])
        self.assertIn('REGIME_POPULATION_BELOW_TWENTY', context['gate']['R_task']['examples_reason_codes'])
        self.assertEqual(context['content_views']['R_task']['examples_only']['visible_example_ids'], [])

    def test_no_matching_regime_has_no_tasks_and_keeps_stats_population_separate(self) -> None:
        context = build_context_evidence(self.fx.retriever, strength=8, **self.fx.query(current_regime='CHOPPY'))
        self.assertEqual(context['task_selection']['tasks'], [])
        self.assertFalse(context['gate']['R_task']['stats_ready'])
        self.assertFalse(context['gate']['R_task']['examples_ready'])
        self.assertGreater(context['pool']['statistics']['population_count'], 0)


if __name__ == '__main__':
    unittest.main()
