"""Chặn rò rỉ tương lai trong pool nền và population thống kê của retriever."""

import copy
from typing import Any
import unittest
from unittest.mock import patch

from core.backtest_engine import compute_round_trip_net_return
from core.bayesian_retriever import BayesianPriorRetriever, MODES, SCOPES
from bayesian_test_support import PriorPipelineFixture

import test_bayesian_retriever as fixtures


class BayesianRetrieverLeakageTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.BayesianRetrieverFoundationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_later_then_earlier_query_does_not_reuse_future_population(self):
        retriever = self.fixture.create()
        for mode in ("recent", "random", "similarity", "bayesian_regime"):
            for scope in ("same_symbol", "pooled"):
                retriever.prepare_query(**self.fixture.query(mode=mode, scope=scope))
                old = retriever.prepare_query(**self.fixture.query(
                    mode=mode, scope=scope, as_of_date="2020-01-07"))
                for key in ("eligible_tasks", "regime_population"):
                    self.assertTrue(all(r["exit_date"] < "2020-01-07" for r in old[key]))
                equal_exit = retriever.prepare_query(**self.fixture.query(
                    mode=mode, scope=scope, as_of_date=self.fixture.rows[0]["exit_date"]))
                self.assertEqual(equal_exit["eligible_tasks"], [])
                self.assertEqual(equal_exit["regime_population"], [])

    def test_future_record_or_outcome_cannot_enter_population_via_source(self):
        retriever = self.fixture.create()
        future = copy.deepcopy(self.fixture.rows[1])
        for row in (future, {**future, "outcome": {**future["outcome"], "net_return_pct": 99}}):
            with patch.object(retriever._memory, "eligible", return_value=[row]), self.assertRaises(ValueError):
                retriever.prepare_query(**self.fixture.query(as_of_date="2020-01-07"))

    def test_adding_valid_future_history_does_not_change_old_pool(self):
        before = self.fixture.create().prepare_query(**self.fixture.query(as_of_date="2020-01-07"))
        self.fixture.rows.append(self.fixture.record("FPT", 6, "BULL"))
        self.fixture.publish_fixture()
        after = self.fixture.create().prepare_query(**self.fixture.query(as_of_date="2020-01-07"))
        self.assertEqual(before["eligible_tasks"], after["eligible_tasks"])
        self.assertEqual(before["regime_population"], after["regime_population"])
        self.assertNotEqual(before["metadata"]["bank_sha256"], after["metadata"]["bank_sha256"])

    def test_all_selected_tasks_respect_equal_exit_and_earlier_query(self):
        retriever = self.fixture.create()
        for mode in ("recent", "random", "similarity", "bayesian_regime"):
            for scope in ("same_symbol", "pooled"):
                retriever.select_prior_tasks(**self.fixture.query(mode=mode, scope=scope))
                selected = retriever.select_prior_tasks(**self.fixture.query(
                    mode=mode, scope=scope, as_of_date="2020-01-07"))
                self.assertTrue(all(r["exit_date"] < "2020-01-07" for r in selected["tasks"]))
                equal = retriever.select_prior_tasks(**self.fixture.query(
                    mode=mode, scope=scope, as_of_date=self.fixture.rows[0]["exit_date"]))
                self.assertEqual(equal["tasks"], [])

    def test_bayesian_matching_future_regime_cannot_enter_selection(self):
        retriever = self.fixture.create()
        for pool in ([self.fixture.rows[1]], [self.fixture.rows[0], self.fixture.rows[1]]):
            with patch.object(retriever._memory, "eligible", return_value=pool), self.assertRaises(ValueError):
                retriever.select_prior_tasks(**self.fixture.query(
                    mode="bayesian_regime", current_regime="BEAR", as_of_date="2020-01-07"))

    def test_retrieve_statistics_equal_exit_and_later_then_earlier_queries(self):
        self.fixture.rows.append(self.fixture.record("FPT", 6, "BULL"))
        self.fixture.publish_fixture()
        retriever = self.fixture.create()
        for mode in ("recent", "random", "similarity", "bayesian_regime"):
            for scope in ("same_symbol", "pooled"):
                later = retriever.retrieve(**self.fixture.query(mode=mode, scope=scope))
                early = retriever.retrieve(**self.fixture.query(mode=mode, scope=scope, as_of_date="2020-01-07"))
                self.assertGreater(later["stats"]["population_count"], early["stats"]["population_count"])
                self.assertEqual(early["stats"]["population_count"], 1 if scope == "same_symbol" else 2)
                equal = retriever.retrieve(**self.fixture.query(
                    mode=mode, scope=scope, as_of_date=self.fixture.rows[0]["exit_date"]))
                self.assertEqual(equal["stats"]["population_count"], 0)
                self.assertTrue(all(m["rate"] is None for m in equal["stats"]["metrics"].values()))

    def test_valid_future_history_and_future_price_outcome_change_leave_old_stats_unchanged(self):
        query = self.fixture.query(as_of_date="2020-01-07", scope="pooled")
        before = self.fixture.create().retrieve(**query)
        future = self.fixture.record("FPT", 6, "BULL")
        self.fixture.rows.append(future)
        self.fixture.publish_fixture()
        added = self.fixture.create().retrieve(**query)
        self.fixture.frame.loc[9, "Close"] = 102.0
        self.fixture.frame["High"] = 103.0
        self.fixture.frame["Reference"] = self.fixture.frame["Close"].shift().fillna(100.0)
        future["outcome"] = {"actual_direction": "UP", "result": "WIN_IF_LONG", "was_bull_trap": False,
                             "net_return_pct": float(100 * compute_round_trip_net_return(100.0, 102.0))}
        self.fixture.publish_fixture()
        changed = self.fixture.create().retrieve(**query)
        for result in (added, changed):
            self.assertEqual(result["stats"], before["stats"])
            self.assertEqual(result["metadata"]["selected_ids"], before["metadata"]["selected_ids"])
            self.assertNotEqual(result["metadata"]["bank_sha256"], before["metadata"]["bank_sha256"])

    def test_statistics_guard_rejects_future_population_even_after_selection(self):
        retriever = self.fixture.create()
        selected = retriever.select_prior_tasks(**self.fixture.query(as_of_date="2020-01-07"))
        selected["regime_population"].append(self.fixture.rows[1])
        with patch.object(retriever, "select_prior_tasks", return_value=selected), self.assertRaises(ValueError):
            retriever.retrieve(**self.fixture.query(as_of_date="2020-01-07"))


class BayesianPriorPipelineLeakageTests(unittest.TestCase):
    """Kiểm ranking, stats và BRPP cùng nhau qua schema/giá/P&L thật."""

    def setUp(self) -> None:
        self.fixture = PriorPipelineFixture()
        self.addCleanup(self.fixture.close)

    def snapshots(self, retriever: BayesianPriorRetriever,
                  query: dict[str, Any] | None = None) -> dict[tuple[str, str], dict[str, Any]]:
        """Lưu toàn bộ bundle trên cùng cutoff cho mọi mode/scope."""
        shared_query = self.fixture.query() if query is None else query
        return {(mode, scope): self.fixture.bundle(retriever, {**shared_query, 'mode': mode, 'scope': scope})
                for mode in sorted(MODES) for scope in sorted(SCOPES)}

    def assert_same_evidence(self, before: dict, after: dict) -> None:
        """Hash kho có thể đổi khi thêm tương lai; bằng chứng hợp lệ phải giữ nguyên."""
        for key in before:
            self.assertEqual(before[key]['prefix'], after[key]['prefix'])
            self.assertEqual(before[key]['result']['tasks'], after[key]['result']['tasks'])
            self.assertEqual(before[key]['result']['stats'], after[key]['result']['stats'])
            for field in ('selected_ids', 'selected_scores', 'effective_seed', 'eligible_count',
                          'matched_regime_count', 'candidate_count', 'selected_count', 'status', 'reason'):
                self.assertEqual(before[key]['result']['metadata'][field], after[key]['result']['metadata'][field])

    def test_equal_exit_straddling_and_future_query_are_excluded_from_final_evidence(self) -> None:
        retriever = self.fixture.create()
        for mode in sorted(MODES):
            for scope in sorted(SCOPES):
                for position in (8, 9):
                    for k in (1, 2, 3):
                        bundle = self.fixture.bundle(retriever, self.fixture.query(
                            mode=mode, scope=scope, as_of_date=self.fixture.day(position), k=k))
                        result = bundle['result']
                        self.assertEqual(result['metadata']['eligible_count'], 2 if scope == 'same_symbol' else 4)
                        self.assertEqual(result['stats']['population_count'], 2 if scope == 'same_symbol' else 3)
                        expected = {'numerator': 1, 'denominator': 2, 'rate': 0.5} if scope == 'same_symbol' else {
                            'numerator': 2, 'denominator': 3, 'rate': 2 / 3}
                        self.assertEqual(result['stats']['metrics']['win_rate_long'], expected)
                        for task in result['tasks']:
                            self.assertLess(task['exit_date'], self.fixture.day(position))
                        for excluded in (self.fixture.day(6), self.fixture.day(9), self.fixture.day(12)):
                            self.assertNotIn('@' + excluded, bundle['prefix'])
                empty = self.fixture.bundle(retriever, self.fixture.query(mode=mode, scope=scope,
                    as_of_date=self.fixture.day(3)))
                self.assertEqual(empty['result']['tasks'], [])
                self.assertEqual(empty['result']['stats']['population_count'], 0)
                self.assertIn('0/0(N/A)', empty['prefix'])

    def test_valid_future_append_does_not_change_ids_stats_scores_seed_or_prefix(self) -> None:
        before = self.snapshots(self.fixture.create())
        self.fixture.base.rows.append(self.fixture.record('FPT', 15, 'BULL', 'BULLISH', 'BULLISH'))
        self.fixture.base.publish_fixture()
        after = self.snapshots(self.fixture.create())
        self.assert_same_evidence(before, after)
        for key in before:
            self.assertNotEqual(before[key]['result']['metadata']['bank_sha256'], after[key]['result']['metadata']['bank_sha256'])

    def test_valid_future_price_signal_regime_and_outcome_changes_leave_old_prefix_unchanged(self) -> None:
        before = self.snapshots(self.fixture.create())
        self.fixture.base.frame.loc[[12, 15], 'Close'] = [104.0, 103.0]
        self.fixture.refresh_reference()
        for row in self.fixture.base.rows:
            if row['exit_date'] >= self.fixture.day(9):
                row['regime'] = 'CONSOLIDATION'
                row['agent_signals'].update(trend='BEARISH', pattern='NEUTRAL', alpha_consensus='BULLISH')
        self.fixture.relabel()
        after = self.snapshots(self.fixture.create())
        self.assert_same_evidence(before, after)

    def test_late_queries_then_early_queries_cannot_reuse_future_stats_or_prefix(self) -> None:
        retriever = self.fixture.create()
        expected = self.snapshots(retriever)
        with patch.object(retriever._memory, '_execution_loader', side_effect=AssertionError('Query đọc giá')):
            for mode in sorted(MODES):
                for scope in sorted(SCOPES):
                    late = self.fixture.bundle(retriever, self.fixture.query(mode=mode, scope=scope,
                        as_of_date=self.fixture.day(16)))
                    self.assertGreater(late['result']['metadata']['eligible_count'],
                                       expected[(mode, scope)]['result']['metadata']['eligible_count'])
                    self.assertNotEqual(late['prefix'], expected[(mode, scope)]['prefix'])
            self.assertEqual(self.snapshots(retriever), expected)

    def test_poisoned_eligible_sources_fail_before_prefix_in_every_mode_and_scope(self) -> None:
        retriever = self.fixture.create()
        rows = self.fixture.base.rows
        past, equal_exit, query_record, future = (copy.deepcopy(rows[i]) for i in (0, 2, 3, 4))
        unknown = {**copy.deepcopy(past), 'episode_id': 'UNKNOWN'}
        changed = copy.deepcopy(past)
        changed['outcome']['net_return_pct'] = float('nan')
        pools = [[equal_exit], [query_record], [future], [past, future], [past, past], [unknown], [changed]]
        for mode in sorted(MODES):
            for scope in sorted(SCOPES):
                cases = pools + ([[rows[5]]] if scope == 'same_symbol' else [])
                for pool in cases:
                    with self.subTest(mode=mode, scope=scope, pool=pool), \
                         patch.object(retriever._memory, 'eligible', return_value=copy.deepcopy(pool)), \
                         patch('core.bayesian_retriever.format_compact_prior_prefix') as formatter:
                        with self.assertRaises(ValueError):
                            self.fixture.bundle(retriever, self.fixture.query(mode=mode, scope=scope))
                        formatter.assert_not_called()

    def test_corrupt_selectors_cannot_inject_a_future_task_into_prefix(self) -> None:
        retriever = self.fixture.create()
        future = copy.deepcopy(self.fixture.base.rows[3])
        for mode in sorted(MODES):
            method = '_select_recent' if mode == 'recent' else '_select_random' if mode == 'random' else '_select_similarity'
            value = [future] if mode == 'recent' else ([future], 'bad-seed') if mode == 'random' else ([future], {future['episode_id']: 1.0})
            for scope in sorted(SCOPES):
                with self.subTest(mode=mode, scope=scope), patch.object(retriever, method, return_value=value), \
                     patch('core.bayesian_retriever.format_compact_prior_prefix') as formatter:
                    with self.assertRaises(ValueError):
                        self.fixture.bundle(retriever, self.fixture.query(mode=mode, scope=scope))
                    formatter.assert_not_called()

    def test_poisoned_statistics_population_fails_after_selection_before_prefix(self) -> None:
        retriever = self.fixture.create()
        rows = self.fixture.base.rows
        for mode in sorted(MODES):
            for scope in sorted(SCOPES):
                query = self.fixture.query(mode=mode, scope=scope)
                original = retriever.select_prior_tasks(**query)
                populations = [[rows[2]], [rows[3]], [rows[6]], [rows[0], rows[0]]]
                if scope == 'same_symbol':
                    populations.append([rows[5]])
                changed = copy.deepcopy(rows[0])
                changed['outcome']['was_bull_trap'] = True
                populations.append([changed])
                for population in populations:
                    selected = copy.deepcopy(original)
                    selected['regime_population'] = copy.deepcopy(population)
                    selected['metadata']['matched_regime_count'] = len(population)
                    with self.subTest(mode=mode, scope=scope, population=population), \
                         patch.object(retriever, 'select_prior_tasks', return_value=selected), \
                         patch('core.bayesian_retriever.format_compact_prior_prefix') as formatter:
                        with self.assertRaises(ValueError):
                            self.fixture.bundle(retriever, query)
                        formatter.assert_not_called()

    def test_query_outcome_and_query_id_cannot_appear_in_prior_evidence(self) -> None:
        retriever = self.fixture.create()
        # Query thực sự có WIN ở tương lai trong kho; prior chỉ có 1/2 WIN cùng mã.
        query_record = self.fixture.base.rows[3]
        self.assertEqual(query_record['outcome']['result'], 'WIN_IF_LONG')
        for mode in sorted(MODES):
            for scope in sorted(SCOPES):
                query = self.fixture.query(mode=mode, scope=scope)
                bundle = self.fixture.bundle(retriever, query)
                self.assertNotIn(query_record['episode_id'], bundle['result']['metadata']['selected_ids'])
                self.assertNotIn('@' + query_record['as_of_date'], bundle['prefix'])
                self.assertNotIn('outcome', query)
                self.assertNotIn('current_outcome', query)
                if scope == 'same_symbol':
                    self.assertIn('LONGwin=1/2(50.0%)', bundle['prefix'])

    def test_branch_mutations_do_not_change_shared_query_bank_or_other_bundles(self) -> None:
        retriever = self.fixture.create()
        query = self.fixture.query()
        query_before, bank_before = copy.deepcopy(query), copy.deepcopy(self.fixture.base.rows)
        bundles = self.snapshots(retriever, query)
        expected = copy.deepcopy(bundles)
        poisoned = bundles[('recent', 'same_symbol')]['result']
        poisoned['tasks'][0]['agent_signals']['trend'] = 'ĐÃ SỬA NHÁNH'
        poisoned['stats']['metrics']['win_rate_long']['numerator'] = 999
        poisoned['metadata']['selected_ids'].append('ĐÃ SỬA NHÁNH')
        self.assertEqual(query, query_before)
        self.assertEqual(self.fixture.base.rows, bank_before)
        for key in bundles:
            if key != ('recent', 'same_symbol'):
                self.assertEqual(bundles[key], expected[key])
        self.assertEqual(self.snapshots(retriever, query), expected)

    def test_past_labels_change_evidence_but_never_select_winners_by_outcome(self) -> None:
        before = self.snapshots(self.fixture.create())
        self.fixture.base.frame.loc[3, 'Close'] = 100.0
        self.fixture.refresh_reference()
        self.fixture.relabel()
        after = self.snapshots(self.fixture.create())
        for key in before:
            for field in ('selected_ids', 'selected_scores', 'effective_seed'):
                self.assertEqual(before[key]['result']['metadata'][field], after[key]['result']['metadata'][field])
            self.assertNotEqual(before[key]['result']['stats'], after[key]['result']['stats'])
            self.assertNotEqual(before[key]['prefix'], after[key]['prefix'])


if __name__ == "__main__":
    unittest.main()
