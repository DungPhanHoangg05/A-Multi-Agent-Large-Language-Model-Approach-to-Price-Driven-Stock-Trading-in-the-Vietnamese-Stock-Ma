"""Union memory, nguồn bất biến và scaler revision kế thừa tham số train."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from core.bic_icl_memory import (FrozenSources, RevisionMemory, RevisionRetriever, _BUILT,
    adapt_checkpoint, union_records, build_revision_index)
from core.backtest_engine import compute_round_trip_net_return
from core.historical_signals import digest
from core.research_cohort import save_envelope
from bic_icl_memory_support import CheckpointFixture, revision_fixture
from prior_price_similarity_support import PriceSimilarityFixture


class MemoryRevisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = PriceSimilarityFixture()
        self.addCleanup(self.fx.close)

    def test_union_deduplicates_identical_cycle_without_mutating_original(self) -> None:
        original = deepcopy(self.fx.records)
        result, duplicates = union_records(original, [deepcopy(original[0])])
        self.assertEqual(len(result), len(original))
        self.assertEqual(duplicates, [original[0]['episode_id']])
        self.assertEqual(original, self.fx.records)

    def test_union_rejects_conflicting_id_cycle_and_any_2025_append(self) -> None:
        for field, value in (('episode_id', 'another'), ('regime', 'CHOPPY')):
            record = deepcopy(self.fx.records[0])
            record[field] = value
            with self.assertRaises(ValueError):
                union_records(self.fx.records, [record])
        record['episode_id'] = 'new'
        record.update(as_of_date='2025-01-02', entry_date='2025-01-03', exit_date='2025-01-06')
        with self.assertRaises(ValueError):
            union_records(self.fx.records, [record])

    def test_snapshot_is_owned_and_constructor_cannot_accept_unverified_payload(self) -> None:
        with self.assertRaises(ValueError):
            RevisionMemory({'records': []}, verified=object())
        memory, _ = revision_fixture(self.fx)
        first = memory.records[0]['episode_id']
        memory.records[0]['episode_id'] = 'mutated'
        memory.payload['records'].clear()
        self.assertEqual(memory.records[0]['episode_id'], first)
        self.assertTrue(memory.records)

    def test_revision_adds_2025_domain_but_legacy_still_rejects_it(self) -> None:
        memory, index = revision_fixture(self.fx)
        with self.assertRaises(ValueError):
            self.fx.index.scaler('FPT', '2025-01-02')
        current = index.scaler('FPT', '2025-01-02')
        legacy = self.fx.index.scaler('FPT', '2024-12-31')
        for field in ('mean', 'variance', 'scale', 'zero_variance', 'fit_episode_ids', 'fit_count',
                      'fit_cutoff', 'freeze_date', 'fit_max_exit_date'):
            self.assertEqual(current[field], legacy[field])
        self.assertEqual(current['fold_id'], 'confirmation_2025')
        self.assertEqual(index.payload['memory_sha256'], memory.identity)
        self.assertEqual(index.payload['legacy_index_sha256'], self.fx.index.identity)

    def test_revision_keeps_both_train_fold_scalers_and_never_fits(self) -> None:
        before = self.fx.index.payload
        with patch('core.price_feature_index._fit', side_effect=AssertionError('Cấm refit')):
            _, index = revision_fixture(self.fx)
        for name in ('train_2021', 'train_2022', 'oos_2023_2024'):
            self.assertEqual(index.payload['scalers'][name], before['scalers'][name])
        self.assertEqual(before, self.fx.index.payload)
        with self.assertRaises(ValueError):
            index.scaler('FPT', '2026-01-02')
        with self.assertRaises(ValueError):
            index.scaler('FPT', '2025-01-02', fold_id='train_2021')

    def test_revision_retriever_matches_legacy_eligible_and_records_are_bound(self) -> None:
        memory, index = revision_fixture(self.fx)
        retriever = RevisionRetriever(memory)
        query = self.fx.query()
        query['index'] = index
        ranked = retriever.rank_price_candidates(**query)
        self.assertEqual(ranked['metadata']['index_version'], 'bic_icl_price_index_v1')
        self.assertEqual(ranked['metadata']['ranked_ids'],
                         self.fx.retriever.rank_price_candidates(**self.fx.query())['metadata']['ranked_ids'])
        self.assertEqual(retriever._bank_sha256, memory.identity)
        self.assertFalse(any('outcome' in row for row in index.payload['records']))

    def test_A_and_R_use_identical_revision_snapshot_and_cycle_selector(self) -> None:
        from core.bic_icl_statistics import pool_evidence
        from core.improvement_prior import build_evidence
        from core.prior_example_selection import PriceExampleSelector
        memory, index = revision_fixture(self.fx)
        retriever = RevisionRetriever(memory)
        query = self.fx.query()
        query.pop('index')
        selector = PriceExampleSelector(index, self.fx.inputs['calendar'])
        a = build_evidence(retriever, 'A_tp_pool', selector=selector, **query)
        r = pool_evidence(retriever, selector=selector, strength=8, **query)
        self.assertEqual(a['bank_sha256'], r['bank_sha256'])
        self.assertEqual(a['selection'], r['selection'])
        self.assertEqual(a['statistics']['groups']['population']['cycle_count'], r['statistics']['same_regime_count'])

    def test_adapter_uses_upstream_before_engine_label_and_never_Decision(self) -> None:
        fx = CheckpointFixture()
        record = adapt_checkpoint(fx.document, fx.journal, **fx.options)
        self.assertTrue(fx.sealed)
        self.assertEqual(record['entry_date'], fx.days[3].strftime('%Y-%m-%d'))
        self.assertEqual(record['exit_date'], fx.days[5].strftime('%Y-%m-%d'))
        self.assertEqual(record['outcome']['net_return_pct'], 100*compute_round_trip_net_return(100., 102.))
        self.assertEqual(record['agent_signals'], fx.bundle['current_signals'])
        changed = deepcopy(fx.document)
        changed['decision'] = {'action': 'SHORT'}
        with self.assertRaises(ValueError):
            adapt_checkpoint(changed, fx.journal, **fx.options)

    def test_adapter_rejects_journal_unknown_report_and_wrong_binding(self) -> None:
        for kind in ('unknown', 'report', 'binding'):
            fx = CheckpointFixture()
            journal = deepcopy(fx.journal)
            if kind == 'unknown':
                journal['nodes']['trend']['attempts'][-1]['status'] = 'unknown'
            elif kind == 'report':
                journal['nodes']['trend']['attempts'][-1]['output']['trend_report'] = 'Khác'
            else:
                journal['binding']['run_signature'] = 'f'*64
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                adapt_checkpoint(fx.document, journal, **fx.options)

    def test_frozen_source_checks_independent_archive_bytes_and_no_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            relative = 'source.json'
            save_envelope(root/relative, {'value': 1})
            archive = root/'proof.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                z.write(root/relative, relative)
            with (patch('core.bic_icl_memory.ARCHIVE', archive.name),
                  patch('core.bic_icl_memory.ARCHIVE_SHA', hashlib.sha256(archive.read_bytes()).hexdigest()),
                  patch('core.bic_icl_memory.verify_method')):
                sources = FrozenSources(root)
                self.assertEqual(sources.envelope(relative), {'value': 1})
                save_envelope(root/relative, {'value': 2})
                with self.assertRaises(ValueError):
                    sources.envelope(relative)
                with self.assertRaises(ValueError):
                    sources.verify()
                with self.assertRaises(ValueError):
                    sources.envelope('../source.json')


if __name__ == '__main__':
    unittest.main()
