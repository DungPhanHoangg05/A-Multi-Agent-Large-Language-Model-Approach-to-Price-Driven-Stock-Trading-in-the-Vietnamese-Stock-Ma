"""PIT, future append, nhãn độc lập và chống rehash task/evidence."""

from copy import deepcopy
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from core.bic_icl_tasks import TaskSelector, group_task_cycles, select_tasks
from core.bic_icl_prompt import build_context_evidence, render_profiles, verify_context_evidence, capture_decision_prompt
from core.historical_signals import digest
from bic_icl_tasks_support import TaskFixture


class TaskLeakageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = TaskFixture()

    def plan(self, rows: list[dict]) -> dict:
        return group_task_cycles(rows, [0.]*4, symbol='FPT', regime='BULL', as_of_date='2022-01-06')

    def test_grouping_api_rejects_outcomes_labels_decisions_or_extra_features(self) -> None:
        for key in ('outcome', 'label', 'net_return_pct', 'decision', 'confidence'):
            rows = [self.fx.row(640, 1), self.fx.row(646, 2)]
            rows[0][key] = 1
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.plan(rows)

    def test_future_exit_equal_cutoff_wrong_scope_and_horizon_fail_closed(self) -> None:
        for field, value in (('exit_date', '2022-01-06'), ('exit_date', '2023-01-01'),
                ('symbol', 'MWG'), ('regime', 'BEAR'), ('entry_session', 642), ('exit_session', 644)):
            row = self.fx.row(640, 1)
            row[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.plan([row])

    def test_duplicate_ids_cycles_and_rank_positions_are_rejected(self) -> None:
        for field in ('episode_id', 'as_of_date', 'rank_position'):
            rows = [self.fx.row(640, 1), self.fx.row(646, 2)]
            rows[1][field] = rows[0][field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.plan(rows)

    def test_numpy_nonfinite_and_wrong_length_vectors_are_errors(self) -> None:
        for vector in ([np.float64(1.), 0., 0., 0.], [True, 0., 0., 0.], [float('nan')]*4,
                       [float('inf')]*4, [0.]*3, [10**1000, 0, 0, 0]):
            row = self.fx.row(640, 1)
            row['scaled_vector'] = vector
            with self.assertRaises(ValueError):
                self.plan([row])

    def test_future_calendar_append_does_not_reanchor_groups_or_change_past_receipt(self) -> None:
        before = select_tasks(self.fx.retriever, **self.fx.query())
        calendar = pd.bdate_range('2018-01-02', '2024-12-31')
        selector = TaskSelector(self.fx.index, calendar)
        after = select_tasks(self.fx.retriever, **self.fx.query(selector=selector))
        self.assertEqual(before, after)

    def test_future_bank_cycle_and_query_itself_are_excluded_before_ranking(self) -> None:
        before = select_tasks(self.fx.retriever, **self.fx.query())
        query_pos = self.fx.calendar.get_loc('2022-01-06')
        self.fx.records += [self.fx.record(query_pos), self.fx.record(query_pos+20)]
        self.fx.publish()
        after = select_tasks(self.fx.retriever, **self.fx.query())
        self.assertEqual(before['selected_task_ids'], after['selected_task_ids'])
        self.assertEqual(before['selected_episode_ids'], after['selected_episode_ids'])
        self.assertEqual(before['task_trace'], after['task_trace'])
        self.assertEqual(before['eligible_cycles'], after['eligible_cycles'])

    def test_permuting_only_historical_labels_does_not_change_ranking(self) -> None:
        before = select_tasks(self.fx.retriever, **self.fx.query())
        # Cố ý sửa cache fixture sau biên xác minh để kiểm sự độc lập của selector với nhãn.
        for row in self.fx.memory._payload['records']:
            row['outcome']['net_return_pct'] *= -1
        for row in self.fx.retriever._verified_by_id.values():
            row['outcome']['net_return_pct'] *= -1
        after = select_tasks(self.fx.retriever, **self.fx.query())
        for key in ('selected_task_ids', 'selected_episode_ids', 'task_trace', 'eligible_cycles'):
            self.assertEqual(before[key], after[key])
        self.assertNotEqual(before['tasks'][0]['examples'][0]['outcome'], after['tasks'][0]['examples'][0]['outcome'])

    def test_730_day_filter_kept_without_restricting_statistics_population(self) -> None:
        self.fx.records.append(self.fx.record(450))
        self.fx.publish()
        result = build_context_evidence(self.fx.retriever, strength=8, **self.fx.query())
        key = f'FPT:{self.fx.day(450)}'
        self.assertIn(key, result['pool']['statistics']['groups']['C']['episode_ids'])
        self.assertNotIn(key, result['task_selection']['metadata']['qualified_ids'])
        row = next(r for r in result['task_selection']['qualification_trace'] if r['episode_id'] == key)
        self.assertIn('PRIOR_TOO_OLD', row['qualification_reasons'])

    def test_changed_future_query_feature_rejected_before_task_grouping(self) -> None:
        options = self.fx.query()
        options['query_features']['feature_end_date'] = '2099-01-01'
        options['query_features']['coverage']['end_date'] = '2099-01-01'
        with patch('core.bic_icl_tasks.group_task_cycles', side_effect=AssertionError('Không được group')):
            with self.assertRaises(ValueError):
                select_tasks(self.fx.retriever, **options)

    def test_rehashed_centroid_pair_task_id_counts_and_gate_cannot_replace_source(self) -> None:
        options = {**self.fx.query(), 'strength': 8}
        original = build_context_evidence(self.fx.retriever, **options)
        for kind in ('centroid', 'pair', 'task_id', 'counts', 'gate'):
            evidence = deepcopy(original)
            if kind == 'centroid':
                evidence['task_selection']['task_trace'][0]['centroid'][0] = 99.
            elif kind == 'pair':
                evidence['task_selection']['tasks'][0]['examples'].reverse()
            elif kind == 'task_id':
                evidence['task_selection']['selected_task_ids'][0] = 'FPT:BULL:0000'
            elif kind == 'counts':
                evidence['pool']['statistics']['counts']['C']['n'] += 1
            else:
                evidence['gate']['R_task']['examples_ready'] = False
            evidence['base_evidence_sha256'] = digest({k: v for k, v in evidence.items() if k != 'base_evidence_sha256'})
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                render_profiles(evidence, 'vi', verifier=lambda actual: verify_context_evidence(actual, self.fx.retriever, **options))

    def test_query_outcome_and_scope_override_fail_before_retrieval(self) -> None:
        for key, value in (('outcome', {}), ('scope', 'pooled'), ('net_return_long', .1)):
            with patch.object(self.fx.retriever, 'rank_price_candidates', side_effect=AssertionError('Không được rank')):
                with self.assertRaises(ValueError):
                    select_tasks(self.fx.retriever, **self.fx.query(**{key: value}))

    def test_capture_rejects_query_outcome_non_daily_and_oversized_prefix_before_factory(self) -> None:
        state = {'stock_name': 'FPT', 'as_of_date': '2022-01-06', 'is_backtest': True, 'language': 'vi', 'time_frame': '1d'}
        for change, prefix in (({'outcome': {}}, ''), ({'entry_date': '2099-01-01'}, ''),
                ({'net_return_pct': .1}, ''), ({'time_frame': '1h'}, ''), ({}, 'x'*601)):
            with patch('agents.decision_agent.create_final_trade_decider', side_effect=AssertionError('Không được tạo node')):
                with self.assertRaises(ValueError):
                    capture_decision_prompt({**state, **change}, prefix, verifier=lambda actual: None)


if __name__ == '__main__':
    unittest.main()
