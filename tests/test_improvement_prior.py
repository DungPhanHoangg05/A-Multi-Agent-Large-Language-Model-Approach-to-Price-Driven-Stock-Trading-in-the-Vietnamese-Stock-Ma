"""Can thiệp A/B cô lập, posterior tính tay, schema/token và fallback revision mới."""

from copy import deepcopy
import json
import unittest

from core.bayesian_retriever import PREFIX_METRICS
from core.historical_signals import digest
from core.improvement_prior import build_evidence, build_request, validate_evidence, validate_request, tp_statistics
from core.prior_prompt import _prefix
from core.prior_price_similarity import SIGNAL_FIELDS
from test_prior_quality_gate import populated_fixture, gate_query
from test_prior_prompt_contract import FixtureLlm, decision_result, invoke_request, request_state
from core.improvement_diagnostics import score_rows


class ImprovementPriorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = populated_fixture()
        self.addCleanup(self.fx.close)
        self.query = gate_query(self.fx)

    def test_a_relaxes_only_partition_and_matches_independent_counts_posterior(self) -> None:
        query = deepcopy(self.query)
        query['current_signals']['alpha_consensus'] = 'BULLISH'
        c2 = build_evidence(self.fx.retriever, 'C2', **query)
        a = build_evidence(self.fx.retriever, 'A_tp_pool', **query)
        self.assertEqual(c2['statistics']['conditional_count'], 0)
        self.assertGreater(a['statistics']['conditional_count'], 0)
        self.assertEqual(a['selection'], c2['selection'])
        self.assertEqual(SIGNAL_FIELDS, ('trend', 'pattern', 'alpha_consensus', 'indicator_consensus'))
        stats = a['statistics']
        groups = {name: set(value['episode_ids']) for name, value in stats['groups'].items()}
        self.assertFalse(groups['conditional'] & groups['background'])
        self.assertEqual(groups['population'], groups['conditional'] | groups['background'])
        records = {r['episode_id']: r for r in self.fx.records}
        for metric in PREFIX_METRICS:
            counts = {}
            for name, ids in groups.items():
                supported = [records[key] for key in ids if metric == 'win_rate_long' or
                    (metric == 'bull_trap_rate' and any(records[key]['agent_signals'][k] == 'BULLISH' for k in ('trend', 'pattern'))) or
                    (metric == 'trend_false_bullish_rate' and records[key]['agent_signals']['trend'] == 'BULLISH') or
                    (metric == 'pattern_false_bullish_rate' and records[key]['agent_signals']['pattern'] == 'BULLISH')]
                successes = sum(r['outcome']['result'] == ('WIN_IF_LONG' if metric == 'win_rate_long' else 'LOSS_IF_LONG') for r in supported)
                counts[name] = successes, len(supported)
                self.assertEqual(stats['metrics'][metric]['raw_counts'][name]['success_count'], successes)
                self.assertEqual(stats['metrics'][metric]['raw_counts'][name]['support_count'], len(supported))
            sc, nc = counts['conditional']; sb, nb = counts['background']
            expected = (4*(sb+1)/(nb+2)+sc)/(4+nc) if nc else None
            self.assertEqual(stats['metrics'][metric]['posterior_mean'], expected)
        validate_evidence(a, self.fx.retriever, 'A_tp_pool', selector=query['selector'], query_features=query['query_features'])
        json.dumps(a, allow_nan=False)

    def test_c2_renderer_unchanged_b_same_base_modes_schema_and_semantics(self) -> None:
        c2 = build_evidence(self.fx.retriever, 'C2', **self.query)
        b = build_evidence(self.fx.retriever, 'B_semantic', **self.query)
        self.assertEqual(c2, b)
        requests = []
        for base in ('C2', 'A_tp_pool', 'B_semantic'):
            evidence = build_evidence(self.fx.retriever, base, **self.query)
            for suffix in ('', '_stats_only', '_examples_only'):
                r = build_request(evidence, base+suffix, self.fx.retriever,
                    selector=self.query['selector'], query_features=self.query['query_features'])
                validate_request(r, evidence, self.fx.retriever, selector=self.query['selector'], query_features=self.query['query_features'])
                llm = FixtureLlm(decision_result())
                result = invoke_request(r, request_state(r), llm)
                self.assertEqual(llm.schema.__name__, 'TradeDecisionOutput')
                self.assertNotIn('prior_use', json.loads(result['final_trade_decision']))
                self.assertLess(len(llm.prompts[0]), 6500)
                self.assertLessEqual(len(r['prefix']), 600)
                requests.append(r)
        self.assertEqual(requests[0]['prefix'], _prefix(c2, 'C2'))
        self.assertEqual(requests[0]['base_evidence_sha256'], requests[6]['base_evidence_sha256'])
        self.assertEqual(requests[0]['trace'], requests[6]['trace'])
        self.assertIn('PF=N/A', requests[6]['prefix'])
        self.assertIn('không P(query)/E(return); SHORT=CASH.', requests[6]['prefix'])
        self.assertNotIn('nP=', requests[8]['prefix'])
        self.assertIn('Ví dụ lịch sử;', requests[8]['prefix'])
        self.assertNotIn('T/P/A/I:+', requests[7]['prefix'])
        self.assertIn('C=khớp T/P;', requests[3]['prefix'])

    def test_disabled_and_zero_skip_posterior_dependencies_and_keep_empty_prefix(self) -> None:
        from unittest.mock import patch
        for options in ({'requested_k': 0}, {'enable_bayesian_prior': False}):
            with patch.object(self.fx.retriever, 'conditional_statistics', side_effect=AssertionError('Không được đếm khi tắt')):
                for base in ('C2', 'A_tp_pool', 'B_semantic'):
                    evidence = build_evidence(self.fx.retriever, base,
                        **{k: v for k, v in self.query.items() if k not in ('selector', 'query_features')}, **options)
                    request = build_request(evidence, base, self.fx.retriever)
                    self.assertEqual(request['prefix'], '')
                    self.assertEqual(request['decision_contract_version'], 'decision_legacy_v1')

    def test_empty_conditional_and_background_do_not_invent_probability(self) -> None:
        query = {k: v for k, v in self.query.items() if k not in ('selector', 'query_features')}
        query['current_signals'] = {**query['current_signals'], 'trend': 'BEARISH', 'pattern': 'BEARISH'}
        empty = tp_statistics(self.fx.retriever, **query)
        self.assertEqual(empty['conditional_count'], 0)
        self.assertTrue(all(m['posterior_mean'] is None for m in empty['metrics'].values()))
        query['current_signals']['trend'] = 'BULLISH'
        query['current_signals']['pattern'] = 'NEUTRAL'
        stats = tp_statistics(self.fx.retriever, **query)
        self.assertTrue(all(m['raw_counts']['population']['support_count'] ==
                            m['raw_counts']['conditional']['support_count']+m['raw_counts']['background']['support_count']
                            for m in stats['metrics'].values()))

    def test_rehashed_stats_gate_request_and_version_tamper_are_rejected(self) -> None:
        evidence = build_evidence(self.fx.retriever, 'A_tp_pool', **self.query)
        request = build_request(evidence, 'A_tp_pool', self.fx.retriever,
            selector=self.query['selector'], query_features=self.query['query_features'])
        for field in ('statistics', 'gate', 'version'):
            wrong = deepcopy(evidence)
            if field == 'statistics':
                wrong['statistics']['metrics']['win_rate_long']['raw_counts']['conditional']['success_count'] += 1
            elif field == 'gate':
                wrong['gate']['stats_ready'] = not wrong['gate']['stats_ready']
            else:
                wrong['evidence_contract_version'] = 'prior_evidence_v3'
            wrong['base_evidence_sha256'] = digest({k: v for k, v in wrong.items() if k != 'base_evidence_sha256'})
            with self.assertRaises(ValueError):
                validate_evidence(wrong, self.fx.retriever, 'A_tp_pool', selector=self.query['selector'], query_features=self.query['query_features'])
        wrong = deepcopy(request)
        wrong['prefix'] += 'Sai'
        wrong['request_sha256'] = digest({k: v for k, v in wrong.items() if k != 'request_sha256'})
        with self.assertRaises(ValueError):
            validate_request(wrong, evidence, self.fx.retriever, selector=self.query['selector'], query_features=self.query['query_features'])


class ImprovementLossTests(unittest.TestCase):
    def test_losses_use_only_common_finite_queries_and_keep_null_and_magnitude_separate(self) -> None:
        rows = [{'episode_id': str(i), 'symbol': 'FPT', 'fold_id': 'train_2021', 'label': y,
            'net_long_return': net, 'probability': {'C2': c, 'A_tp_pool': a}, 'ready': {'C2': False, 'A_tp_pool': True}}
            for i, (y, net, c, a) in enumerate([(1, .1, .5, .75), (0, -.2, .5, .25), (1, .2, None, .9)])]
        result = score_rows(rows)['overall']
        self.assertEqual(result['paired_ids'], ['0', '1'])
        self.assertEqual(result['loss']['C2']['brier'], .25)
        self.assertEqual(result['loss']['A_tp_pool']['brier'], .0625)
        self.assertEqual(result['coverage']['C2']['missing_ids'], ['2'])
        self.assertAlmostEqual(result['long_outcomes']['win']['mean'], .15)
        self.assertEqual(result['long_outcomes']['loss']['mean'], -.2)
        rows[0]['probability']['C2'] = float('nan')
        with self.assertRaises(ValueError):
            score_rows(rows)
