"""Các biên PIT/query outcome/schema và holdout của revision cải tiến."""

from copy import deepcopy
import unittest

from core.improvement_prior import build_evidence, tp_statistics, build_request, check_binding
from core.improvement_protocol import branch_order, registry, protocol
from test_prior_quality_gate import populated_fixture, gate_query
from test_prior_prompt_contract import request_state


class ImprovementLeakageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = populated_fixture()
        self.addCleanup(self.fx.close)
        self.query = gate_query(self.fx)

    def test_tp_partition_excludes_exit_at_or_after_cutoff_and_other_symbol_regime(self) -> None:
        query = {k: v for k, v in self.query.items() if k not in ('selector', 'query_features')}
        records = {r['episode_id']: r for r in self.fx.records}
        for cutoff in ('2020-06-15', '2020-06-16', '2022-01-06'):
            value = tp_statistics(self.fx.retriever, **{**query, 'as_of_date': cutoff})
            for key in value['groups']['population']['episode_ids']:
                row = records[key]
                self.assertLess(row['exit_date'], cutoff)
                self.assertEqual(row['symbol'], 'FPT')
                self.assertEqual(row['regime'], 'BULL')

    def test_future_outcomes_do_not_change_tp_counts_or_posterior(self) -> None:
        query = {k: v for k, v in self.query.items() if k not in ('selector', 'query_features')}
        cutoff = '2020-06-15'
        before = tp_statistics(self.fx.retriever, **{**query, 'as_of_date': cutoff})
        for row in self.fx.retriever._verified_by_id.values():
            if row['exit_date'] >= cutoff:
                row['outcome'] = {'result': 'Độc dữ liệu tương lai, không được đọc'}
        after = tp_statistics(self.fx.retriever, **{**query, 'as_of_date': cutoff})
        self.assertEqual(after, before)

    def test_query_outcome_and_changed_full_signal_cannot_enter_decision_binding(self) -> None:
        evidence = build_evidence(self.fx.retriever, 'B_semantic', **self.query)
        request = build_request(evidence, 'B_semantic', self.fx.retriever,
            selector=self.query['selector'], query_features=self.query['query_features'])
        state = request_state(request)
        check_binding(request, state, request['prefix'])
        for field in ('outcome', 'evaluation', 'entry_open', 'exit_date', 'net_return'):
            with self.assertRaises(ValueError):
                check_binding(request, {**state, field: 1}, request['prefix'])
        state['current_signals']['trend'] = 'BEARISH'
        with self.assertRaises(ValueError):
            check_binding(request, state, request['prefix'])

    def test_registry_has_no_combined_method_risk_or_llm_seed_and_rotation_is_fixed(self) -> None:
        value = registry()
        self.assertEqual(value['nomination_order'], ['C2', 'A_tp_pool', 'B_semantic'])
        self.assertEqual(value['risk_policy'], 'OFF')
        self.assertEqual(len(value['order']), 11)
        self.assertNotIn('seed', protocol()['client_options']['agent'])
        self.assertEqual(branch_order(1), value['order'][1:]+value['order'][:1])
        with self.assertRaises(ValueError):
            branch_order(0, 4)
