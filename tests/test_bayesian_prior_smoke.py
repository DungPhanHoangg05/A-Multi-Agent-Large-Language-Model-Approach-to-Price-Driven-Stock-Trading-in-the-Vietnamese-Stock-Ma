"""Kiểm smoke kho thật, nguồn query PIT và lỗi bằng chứng; không gọi API."""

import copy
import unittest

from core.bayesian_memory import read_json
from core.historical_signals import digest
from scripts.verify_bayesian_prior import ROOT, check_result, validate_source


class BayesianPriorSmokeTests(unittest.TestCase):
    """Kiểm receipt/kho đã commit và hàm xác minh; không phụ thuộc archive local."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.receipt = read_json(ROOT / 'docs/plan/week3/prior_smoke.json')

    def test_coverage_and_original_on_real_bank(self) -> None:
        r = self.receipt
        self.assertEqual((r['real_bank_records'], r['context_count'], r['query_count']), (852, 32, 288))
        self.assertEqual(r['repeat_query_count'], 288)
        self.assertEqual(r['result_status_counts'], {'complete': 176, 'disabled': 32, 'empty': 64, 'partial': 16})
        observed = [c for c in r['contexts'] if c['case_kind'] == 'observed']
        self.assertEqual({(c['query']['symbol'], c['query']['current_regime']) for c in observed},
                         {(s, g) for s in ('FPT', 'MWG', 'VCB', 'VNM') for g in ('BULL', 'BEAR', 'CHOPPY', 'CONSOLIDATION')})
        self.assertTrue(all(r['checks'].values()))
        self.assertFalse(r['oos_trading_backtest'])
        self.assertFalse(r['runtime_integration'])
        for context in observed:
            self.assertEqual({case['mode'] for case in context['cases']}, {'random', 'recent', 'similarity', 'bayesian_regime'})
            for case in context['cases']:
                if case['k'] == 0:
                    self.assertEqual(case['prefix'], '')
                    self.assertEqual(case['selected_dates'], [])
                    self.assertIsNone(case['stats'])

    def test_all_outputs_obey_cutoff_scope_and_population_statistics(self) -> None:
        for context in self.receipt['contexts']:
            query = context['query']
            for case in context['cases']:
                self.assertEqual(len(case['prefix']), case['prefix_length'])
                self.assertLessEqual(case['prefix_length'], 600)
                for task in case['selected_dates']:
                    self.assertLess(task['exit_date'], query['as_of_date'])
                    if case['scope'] == 'same_symbol':
                        self.assertEqual(task['symbol'], query['symbol'])
                    if case['mode'] == 'bayesian_regime':
                        self.assertEqual(task['regime'], query['current_regime'])
                if case['k']:
                    self.assertEqual(case['stats']['population_count'], case['metadata']['matched_regime_count'])
                    if case['metadata']['status'] == 'empty':
                        self.assertEqual(case['stats']['population_count'], 0)
                        self.assertIn('0/0(N/A)', case['prefix'])

    def test_historical_sources_are_prefix_verified_and_boundary_contexts_are_explicit_fixtures(self) -> None:
        for context in self.receipt['contexts']:
            source, query = context['source'], context['query']
            if context['case_kind'] in {'before_first', 'after_last'}:
                self.assertEqual(source['kind'], 'boundary_fixture')
                self.assertEqual(source['query_signal_and_regime_origin'], 'fixed_synthetic_not_observed')
                self.assertEqual(set(query['current_signals'].values()), {'NEUTRAL'})
                self.assertNotIn('regime_state', source)
            else:
                self.assertEqual(source['kind'], 'verified_historical_prefix')
                self.assertEqual(source['model_train_end_date'], query['as_of_date'])
                self.assertEqual(source['regime_state']['as_of_date'], query['as_of_date'])
                self.assertLessEqual(source['regime_state']['feature_end_date'], query['as_of_date'])
                self.assertEqual(source['regime_state']['regime_name'], query['current_regime'])
                self.assertEqual(len(source['regime_artifact_sha256']), 64)

    def test_equal_exit_empty_and_partial_do_not_expand_scope(self) -> None:
        for context in self.receipt['contexts']:
            if context['case_kind'] in {'before_first', 'equal_exit'}:
                self.assertTrue(all(case['metadata']['status'] == 'empty' for case in context['cases']))
            if context['case_kind'] == 'partial':
                for case in context['cases']:
                    if case['scope'] == 'same_symbol':
                        self.assertEqual(case['metadata']['status'], 'partial')
                        self.assertLess(case['metadata']['selected_count'], 3)
                        self.assertEqual(case['metadata']['reason'], 'insufficient_candidates')

    def test_future_model_or_news_and_corrupt_reports_are_rejected(self) -> None:
        context = next(c for c in self.receipt['contexts'] if c['case_kind'] == 'observed')
        source = context['source']
        symbol, cutoff = context['query']['symbol'], context['query']['as_of_date']
        record = next(r for r in read_json(ROOT / 'data_manager/regime_memory_store.json') if r['episode_id'] == source['source_episode_id'])
        # Payload giả lập cho ca từ chối; không cần archive local vốn không được push.
        proof = {'state': copy.deepcopy(source['regime_state']), 'artifact_sha256': source['regime_artifact_sha256'],
                 'metadata': {'train_start_date': '2018-01-02', 'train_end_date': cutoff,
                              'training_data_sha256': source['training_data_sha256']}}
        reports = {'trend_report': 'Báo cáo fixture kiểm checksum'}
        signal = {'stage': 'COMPLETE', 'result': {'symbol': symbol, 'as_of_date': cutoff,
                  'agent_signals': copy.deepcopy(record['agent_signals']), 'reports': reports,
                  'provenance': {'price_end_date': cutoff, 'alpha_end_date': cutoff, 'news_dates': [],
                                 'price_sha256': source['price_snapshot_sha256'], 'reports_sha256': digest(reports)}}}
        episode = {'signature': self.receipt['run_signature'], 'record': record, 'provenance': {'regime': proof}}
        args = {'signature': self.receipt['run_signature'], 'price_hash': source['price_snapshot_sha256']}
        validate_source(episode['record'], episode, signal, proof, **args)
        future = copy.deepcopy(proof)
        future['metadata']['train_end_date'] = '2099-01-01'
        news = copy.deepcopy(signal)
        news['result']['provenance']['news_dates'] = ['2099-01-01']
        reports = copy.deepcopy(signal)
        reports['result']['reports']['trend_report'] += ' ĐÃ SỬA'
        prices = copy.deepcopy(signal)
        prices['result']['provenance']['price_sha256'] = '0' * 64
        for bad_signal, bad_proof in ((signal, future), (news, proof), (reports, proof), (prices, proof)):
            with self.assertRaises(ValueError):
                validate_source(episode['record'], episode, bad_signal, bad_proof, **args)

    def test_bad_cutoff_result_cannot_produce_a_pass_prefix(self) -> None:
        records = read_json(ROOT / 'data_manager/regime_memory_store.json')
        by_id = {r['episode_id']: r for r in records}
        context = next(c for c in self.receipt['contexts'] if c['case_kind'] == 'observed')
        case = next(c for c in context['cases'] if c['scope'] == 'same_symbol' and c['mode'] == 'recent' and c['k'] == 3)
        query = {**context['query'], 'scope': case['scope'], 'mode': case['mode'], 'k': case['k']}
        metadata = {**copy.deepcopy(case['metadata']), **self.receipt['versions'],
                    **{key: value for key, value in query.items() if key not in {'current_signals', 'k'}},
                    'requested_k': query['k'], 'bank_sha256': self.receipt['bank_sha256']}
        result = {'tasks': [copy.deepcopy(by_id[i]) for i in metadata['selected_ids']],
                  'stats': copy.deepcopy(case['stats']), 'metadata': metadata}
        self.assertEqual(check_result(records, query, result), case['prefix'])
        future = copy.deepcopy(result)
        future['tasks'][0]['exit_date'] = query['as_of_date']
        bad_counts = copy.deepcopy(result)
        bad_counts['stats']['population_count'] += 1
        for invalid in (future, bad_counts):
            with self.assertRaises(ValueError):
                check_result(records, query, invalid)


if __name__ == '__main__':
    unittest.main()
