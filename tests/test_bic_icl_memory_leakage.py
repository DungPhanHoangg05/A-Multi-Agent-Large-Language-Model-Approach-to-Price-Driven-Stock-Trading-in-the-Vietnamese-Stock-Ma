"""Rào PIT/nguồn/nhãn và future append invariance của memory/pooling revision."""

from copy import deepcopy
import unittest
from unittest.mock import patch

import numpy as np

from core.bic_icl_memory import RevisionMemory, RevisionRetriever, _BUILT, adapt_checkpoint
from core.bic_icl_statistics import posterior, pool_statistics, pool_evidence, verify_pool_evidence
from core.historical_signals import digest
from core.prior_example_selection import PriceExampleSelector
from bic_icl_memory_support import CheckpointFixture, revision_fixture
from prior_price_similarity_support import PriceSimilarityFixture


class RevisionLeakageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = PriceSimilarityFixture()
        self.addCleanup(self.fx.close)

    def query(self) -> dict:
        query = self.fx.query()
        return {k: query[k] for k in ('symbol', 'as_of_date', 'current_regime', 'current_signals')}

    def test_exit_equal_cutoff_and_query_itself_never_enter_any_partition(self) -> None:
        query = self.query()
        for row in self.fx.records:
            if row['symbol'] != 'FPT':
                continue
            query['as_of_date'] = row['exit_date']
            result = pool_statistics(self.fx.retriever, strength=4, **query)
            ids = [key for group in result['groups'].values() for key in group['episode_ids']]
            self.assertNotIn(row['episode_id'], ids)
        query['as_of_date'] = '2022-01-06'
        result = pool_statistics(self.fx.retriever, strength=4, **query)
        self.assertNotIn('FPT:2022-01-06', [key for g in result['groups'].values() for key in g['episode_ids']])

    def test_missing_or_future_or_cross_symbol_population_is_error(self) -> None:
        query = self.query()
        pool = self.fx.retriever.prepare_query(**query)
        for kind in ('missing', 'future', 'symbol', 'duplicate'):
            changed = deepcopy(pool)
            if kind == 'missing':
                changed['eligible_tasks'].pop()
            elif kind == 'duplicate':
                changed['eligible_tasks'].append(changed['eligible_tasks'][0])
            else:
                changed['eligible_tasks'].append(next(r for r in self.fx.records if
                    r['as_of_date'] == query['as_of_date']) if kind == 'future'
                    else next(r for r in self.fx.records if r['symbol'] == 'MWG'))
            with patch.object(self.fx.retriever, 'prepare_query', return_value=changed):
                with self.subTest(kind=kind), self.assertRaises(ValueError):
                    pool_statistics(self.fx.retriever, strength=4, **query)

    def test_append_future_cycles_and_reorder_bank_leave_past_statistics_identical(self) -> None:
        records = deepcopy(self.fx.records)
        retriever = RevisionRetriever(RevisionMemory({'status': 'AVAILABLE', 'records': records}, verified=_BUILT))
        expected = pool_statistics(retriever, strength=4, **self.query())
        future = deepcopy(records[0])
        future.update(episode_id='FPT:2024-01-02', as_of_date='2024-01-02',
                      entry_date='2024-01-03', exit_date='2024-01-05')
        retriever = RevisionRetriever(RevisionMemory({'status': 'AVAILABLE', 'records': [future, *records[::-1]]}, verified=_BUILT))
        actual = pool_statistics(retriever, strength=4, **self.query())
        self.assertEqual(expected, actual)

    def test_query_outcome_and_scope_override_are_rejected_before_retrieval(self) -> None:
        for key, value in (('outcome', {}), ('net_return_long', .1), ('scope', 'pooled')):
            with patch.object(self.fx.retriever, 'prepare_query', side_effect=AssertionError('Không được gọi')):
                with self.assertRaises(ValueError):
                    pool_statistics(self.fx.retriever, strength=4, **self.query(), **{key: value})

    def test_numpy_counts_bool_invalid_strength_nan_are_not_native_json(self) -> None:
        counts = {'C': {'s': 1, 'n': 5}, 'B1': {'s': 0, 'n': 20}, 'B2': {'s': 0, 'n': 0}}
        for value in (True, np.int64(1), -.1, float('nan')):
            altered = deepcopy(counts)
            altered['C']['s'] = value
            with self.assertRaises(ValueError):
                posterior(altered, 4)
        for strength in (True, 3, 4., np.int64(4)):
            with self.assertRaises(ValueError):
                posterior(counts, strength)

    def test_rehashed_evidence_cannot_replace_counts_readiness_or_selection(self) -> None:
        query = self.fx.query()
        query.pop('index')
        options = {**query, 'selector': PriceExampleSelector(self.fx.index, self.fx.inputs['calendar']), 'strength': 4}
        original = pool_evidence(self.fx.retriever, **options)
        for kind in ('counts', 'ready', 'selection'):
            evidence = deepcopy(original)
            if kind == 'counts':
                evidence['statistics']['counts']['C']['n'] += 1
            elif kind == 'ready':
                evidence['gate']['stats_ready'] = True
            else:
                evidence['selection']['metadata']['selected_ids'] = []
            evidence['base_evidence_sha256'] = digest({k: v for k, v in evidence.items() if k != 'base_evidence_sha256'})
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                verify_pool_evidence(evidence, self.fx.retriever, **options)

    def test_ranking_is_label_blind_even_when_posterior_changes(self) -> None:
        memory, index = revision_fixture(self.fx)
        retriever = RevisionRetriever(memory)
        query = self.fx.query()
        query['index'] = index
        expected = retriever.rank_price_candidates(**query)
        # Thay riêng nhãn trên snapshot fixture sau biên xác minh để thử tính độc lập của rank.
        for row in retriever._verified_by_id.values():
            row['outcome']['net_return_pct'] *= -1
        changed_memory = RevisionMemory({'status': 'AVAILABLE', 'records': list(retriever._verified_by_id.values())}, verified=_BUILT)
        changed = RevisionRetriever(changed_memory)
        # Dùng cùng identity nguồn giả lập để tập trung kiểm API rank không đọc outcome.
        changed._bank_sha256 = memory.identity
        actual = changed.rank_price_candidates(**query)
        self.assertEqual(expected['metadata']['ranked_ids'], actual['metadata']['ranked_ids'])
        self.assertEqual(expected['trace'], actual['trace'])

    def test_future_feature_or_changed_model_proof_cannot_be_resealed(self) -> None:
        for kind in ('feature', 'model', 'signals', 'outcome'):
            fx = CheckpointFixture()
            doc = deepcopy(fx.document)
            if kind == 'model':
                doc['source_proof']['regime'] = {'artifact_sha256': 'f'*64}
            else:
                key = {'feature': 'feature_end_date', 'signals': 'current_signals', 'outcome': 'outcome'}[kind]
                doc['full_bundle'][key] = '2099-01-01' if kind == 'feature' else {}
                doc['shared_sha256'] = digest(doc['full_bundle'])
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                adapt_checkpoint(doc, fx.journal, **fx.options)

    def test_missing_checkpoint_proof_and_wrong_cycle_are_not_prior_off(self) -> None:
        for key in ('source_proof', 'journal_sha256', 'full_bundle'):
            fx = CheckpointFixture()
            doc = deepcopy(fx.document)
            doc.pop(key)
            with self.subTest(key=key), self.assertRaises(ValueError):
                adapt_checkpoint(doc, fx.journal, **fx.options)

    def test_revision_query_features_keep_actual_cutoff_and_reject_future_end(self) -> None:
        _, index = revision_fixture(self.fx)
        features = deepcopy(self.fx.query()['query_features'])
        features.update(as_of_date='2025-01-02', feature_end_date='2025-01-02')
        features['coverage']['end_date'] = '2025-01-02'
        result = index.transform_query('FPT', '2025-01-02', features)
        self.assertEqual(result['fold_id'], 'confirmation_2025')
        features['feature_end_date'] = features['coverage']['end_date'] = '2025-01-03'
        with self.assertRaises(ValueError):
            index.transform_query('FPT', '2025-01-02', features)

    def test_selector_keeps_730_day_limit_with_2025_scaler(self) -> None:
        memory, index = revision_fixture(self.fx)
        retriever = RevisionRetriever(memory)
        query = self.fx.query()
        query.pop('index')
        query['as_of_date'] = '2025-01-02'
        query['query_features'].update(as_of_date='2025-01-02', feature_end_date='2025-01-02')
        query['query_features']['coverage']['end_date'] = '2025-01-02'
        import pandas as pd
        calendar = pd.bdate_range(self.fx.inputs['calendar'][0], '2025-01-02')
        selector = PriceExampleSelector(index, calendar)
        result = pool_evidence(retriever, selector=selector, strength=4, **query)
        self.assertFalse(result['gate']['examples_ready'])
        self.assertEqual(result['selection']['tasks'], [])
        self.assertGreater(result['statistics']['population_count'], 0)
        self.assertIn('PRIOR_TOO_OLD', result['selection']['metadata']['exclusion_counts'])


if __name__ == '__main__':
    unittest.main()
