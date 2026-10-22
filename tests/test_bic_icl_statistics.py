"""Oracle hậu nghiệm, gates và chấm train chung support không chọn theo return."""

from copy import deepcopy
import json
import math
import unittest
from unittest.mock import patch

from scipy.optimize import brentq
from scipy.special import betainc

from core.bic_icl_diagnostics import choose_lambda, score_rows
from core.bic_icl_statistics import posterior, pool_statistics, pool_evidence, verify_pool_evidence
from core.prior_example_selection import PriceExampleSelector
from bic_icl_memory_support import diagnostic_row
from prior_price_similarity_support import PriceSimilarityFixture


class PoolStatisticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = PriceSimilarityFixture()
        self.addCleanup(self.fx.close)

    def query(self) -> dict:
        query = self.fx.query()
        return {k: query[k] for k in ('symbol', 'as_of_date', 'current_regime', 'current_signals')}

    def test_three_level_posterior_matches_independent_beta_cdf_oracle(self) -> None:
        counts = {'C': {'s': 3, 'n': 7}, 'B1': {'s': 9, 'n': 20}, 'B2': {'s': 6, 'n': 11}}
        for strength in (2, 4, 8):
            p = posterior(counts, strength)
            background = (9+strength*7/13)/(20+strength)
            a, b = 3+strength*background, 4+strength*(1-background)
            self.assertAlmostEqual(p['posterior_mean'], a/(7+strength), places=15)
            for q, side in ((.025, 'lower'), (.975, 'upper')):
                expected = brentq(lambda x: betainc(a, b, x)-q, 0, 1, xtol=1e-14)
                self.assertAlmostEqual(p['credible_interval'][side], expected, places=12)

    def test_zero_counts_record_no_support_without_fake_observations(self) -> None:
        result = posterior({k: {'s': 0, 'n': 0} for k in ('C', 'B1', 'B2')}, 4)
        self.assertEqual(result['posterior_mean'], .5)
        self.assertEqual(result['background_reason'], 'NO_OTHER_REGIME_BACKGROUND')
        self.assertFalse(result['ready'])
        self.assertEqual(result['hyperprior_weight'], 1.)

    def test_readiness_support_five_and_background_twenty_exactly(self) -> None:
        counts = {'C': {'s': 3, 'n': 5}, 'B1': {'s': 10, 'n': 20}, 'B2': {'s': 0, 'n': 0}}
        self.assertTrue(posterior(counts, 4)['ready'])
        counts['C'] = {'s': 3, 'n': 4}
        self.assertFalse(posterior(counts, 4)['ready'])
        counts['C'] = {'s': 3, 'n': 5}
        counts['B1'] = {'s': 10, 'n': 19}
        self.assertFalse(posterior(counts, 4)['ready'])

    def test_partition_is_disjoint_same_symbol_and_tp_only(self) -> None:
        query = self.query()
        result = pool_statistics(self.fx.retriever, strength=4, **query)
        expected = {'C': [], 'B1': [], 'B2': []}
        for row in self.fx.records:
            if row['symbol'] != 'FPT' or row['exit_date'] >= query['as_of_date']:
                continue
            key = 'B2' if row['regime'] != query['current_regime'] else 'C' if all(
                row['agent_signals'][k] == query['current_signals'][k] for k in ('trend', 'pattern')) else 'B1'
            expected[key].append(row)
        for key, rows in expected.items():
            self.assertEqual(result['counts'][key], {'s': sum(r['outcome']['net_return_pct'] > 0 for r in rows), 'n': len(rows)})
            self.assertEqual(result['groups'][key]['episode_ids'], sorted(r['episode_id'] for r in rows))
        query['current_signals']['alpha_consensus'] = 'BULLISH'
        self.assertEqual(result['counts'], pool_statistics(self.fx.retriever, strength=4, **query)['counts'])

    def test_statistics_do_not_apply_example_age_or_feature_filters(self) -> None:
        query = self.query()
        query['as_of_date'] = '2024-12-31'
        result = pool_statistics(self.fx.retriever, strength=8, **query)
        self.assertEqual(result['population_count'], sum(r['symbol'] == 'FPT' for r in self.fx.records))
        self.assertTrue(any(age > 730 for group in result['groups'].values() for age in group['age_days']))

    def test_evidence_keeps_selection_and_independent_views(self) -> None:
        query = self.fx.query()
        query.pop('index')
        options = {**query, 'selector': PriceExampleSelector(self.fx.index, self.fx.inputs['calendar']), 'strength': 4}
        evidence = pool_evidence(self.fx.retriever, **options)
        self.assertFalse(evidence['gate']['stats_ready'])
        self.assertFalse(evidence['gate']['examples_ready'])
        self.assertTrue(all(v['fallback_to_original'] for v in evidence['content_views'].values()))
        self.assertEqual(evidence['selection']['metadata']['selected_ids'],
                         self.fx.retriever.select_price_examples(**{k: v for k, v in options.items() if k != 'strength'})['metadata']['selected_ids'])
        verify_pool_evidence(evidence, self.fx.retriever, **options)
        self.assertEqual(json.loads(json.dumps(evidence, allow_nan=False)), evidence)

    def test_stats_and_examples_can_be_ready_independently(self) -> None:
        query = self.fx.query()
        query.pop('index')
        selector = PriceExampleSelector(self.fx.index, self.fx.inputs['calendar'])
        stat = pool_statistics(self.fx.retriever, strength=4, **self.query())
        for stats, examples in ((True, False), (False, True), (True, True)):
            altered = deepcopy(stat)
            altered.update(ready=stats, same_regime_count=20 if examples else 19)
            with patch('core.bic_icl_statistics.pool_statistics', return_value=altered):
                evidence = pool_evidence(self.fx.retriever, selector=selector, strength=4, **query)
            self.assertEqual(evidence['gate']['examples_ready'], examples)
            self.assertEqual(bool(evidence['content_views']['stats_only']['visible_metric_ids']), stats)
            self.assertEqual(bool(evidence['content_views']['examples_only']['visible_example_ids']), examples)
            self.assertEqual(evidence['selection']['metadata']['selected_ids'],
                             ['FPT:2021-12-28', 'FPT:2021-01-04', 'FPT:2020-06-01'])

    def test_interval_gate_uses_unrounded_width_at_point_seventy_five(self) -> None:
        counts = {'C': {'s': 3, 'n': 5}, 'B1': {'s': 10, 'n': 20}, 'B2': {'s': 0, 'n': 0}}
        with patch('core.bic_icl_statistics.beta.ppf', side_effect=[.125, .875]):
            self.assertTrue(posterior(counts, 4)['ready'])
        with patch('core.bic_icl_statistics.beta.ppf', side_effect=[.125, .8750000000000002]):
            self.assertFalse(posterior(counts, 4)['ready'])


class TrainScoringTests(unittest.TestCase):
    def test_common_support_all_lambda_and_A_without_ready_filter(self) -> None:
        rows = [diagnostic_row('one', 1), diagnostic_row('two', 0)]
        rows[1]['probability']['R8'] = None
        result = score_rows(rows)
        self.assertEqual(result['overall']['common_ids'], ['one'])
        self.assertEqual(result['overall']['coverage']['R2']['ready'], 0)
        self.assertAlmostEqual(result['overall']['loss']['R2']['log_loss'], -math.log(.6))
        self.assertEqual(result['overall']['loss']['R2']['brier'], .4**2)

    def test_empty_intersection_is_blocked_not_half_probability(self) -> None:
        row = diagnostic_row('one', 1)
        row['probability']['A'] = None
        result = score_rows([row])
        self.assertEqual(result['status'], 'BLOCKED_NO_COMMON_POSTERIOR')
        self.assertIsNone(result['selected_lambda'])
        self.assertIsNone(result['overall']['loss']['R2']['log_loss'])

    def test_tie_tolerance_then_brier_then_small_lambda(self) -> None:
        loss = {'2': {'log_loss': .5+5e-13, 'brier': .3}, '4': {'log_loss': .5, 'brier': .2},
                '8': {'log_loss': .5, 'brier': .2}}
        self.assertEqual(choose_lambda(loss), 4)
        loss['2']['brier'] = .2
        self.assertEqual(choose_lambda(loss), 2)
        loss['2']['log_loss'] = .5+2e-12
        self.assertEqual(choose_lambda(loss), 4)

    def test_reliability_bin_boundaries_include_zero_and_one(self) -> None:
        rows = [diagnostic_row(str(i), i % 2, {n: p for n in ('A', 'R2', 'R4', 'R8')})
                for i, p in enumerate((0., .2, .4, .6, .8, 1.))]
        result = score_rows(rows)
        self.assertEqual([b['count'] for b in result['overall']['reliability_bins']['R2']], [1, 1, 1, 1, 2])
        self.assertTrue(math.isfinite(result['overall']['loss']['R2']['log_loss']))

    def test_loss_adverse_retained_cluster_sensitivity_and_no_return_selection(self) -> None:
        rows = [diagnostic_row('one', 1, {'A': .9, 'R2': .2, 'R4': .3, 'R8': .4})]
        result = score_rows(rows)
        self.assertGreater(result['delta_loss_vs_A']['8']['log_loss'], 0)
        self.assertEqual(result['selected_lambda'], 8)
        rows[0]['net_long_return'] = 10.
        self.assertEqual(score_rows(rows)['selected_lambda'], 8)
        self.assertEqual(result['cluster_sensitivity']['2021Q1']['common_count'], 0)

    def test_invalid_probability_label_duplicates_and_lambda_are_errors(self) -> None:
        for field, value in (('label', True), ('label', 0), ('net_long_return', float('nan'))):
            row = diagnostic_row('one', 1)
            row[field] = value
            with self.assertRaises(ValueError):
                score_rows([row])
        for p in (float('inf'), -.1, 1.1, True):
            row = diagnostic_row('one', 1)
            row['probability']['R2'] = p
            with self.assertRaises(ValueError):
                score_rows([row])
        row = diagnostic_row('one', 1)
        with self.assertRaises(ValueError):
            score_rows([row, row])
        with self.assertRaises(ValueError):
            choose_lambda({'2': {'log_loss': None, 'brier': None}})


if __name__ == '__main__':
    unittest.main()
