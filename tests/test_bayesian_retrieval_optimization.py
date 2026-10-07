"""Kiểm alias và ownership/type guard ở đường sao chép pool đã xác minh."""

import copy
import unicodedata
import unittest
from unittest.mock import patch

import numpy as np

from core.bayesian_retriever import (
    SENTIMENT_ALIASES, TECHNICAL_ALIASES, normalize_signals,
)
import test_bayesian_retriever as fixtures


class BayesianRetrievalOptimizationTests(unittest.TestCase):
    """Không dùng thời gian thực để nghiệm thu hiệu năng trong unit test."""

    def setUp(self) -> None:
        self.fixture = fixtures.BayesianRetrieverFoundationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_all_locked_aliases_unicode_case_and_whitespace_preserve_meaning(self) -> None:
        signals = copy.deepcopy(self.fixture.rows[0]['agent_signals'])
        for field in signals:
            aliases = SENTIMENT_ALIASES if field == 'sentiment' else TECHNICAL_ALIASES
            for expected, labels in aliases.items():
                for label in labels:
                    for value in (label, ' ' + label.lower() + ' ', unicodedata.normalize('NFD', label)):
                        query = {**signals, field: value}
                        before = copy.deepcopy(query)
                        with self.subTest(field=field, value=value):
                            self.assertEqual(normalize_signals(query)[field], expected)
                            self.assertEqual(query, before)
        for value in ('', ' ', 'không xác định', None, True, np.str_('BULLISH')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_signals({**signals, 'trend': value})

    def test_borrowed_valid_source_and_both_returned_pools_remain_independent(self) -> None:
        retriever = self.fixture.create()
        source = [row for row in self.fixture.rows if row['exit_date'] < self.fixture.query()['as_of_date']]
        before = copy.deepcopy(source)
        with patch.object(retriever._memory, 'eligible', return_value=source):
            result = retriever.prepare_query(**self.fixture.query(scope='pooled'))
        for key in ('eligible_tasks', 'regime_population'):
            self.assertIsNot(result[key], source)
        first = result['eligible_tasks'][0]
        population = next(row for row in result['regime_population'] if row['episode_id'] == first['episode_id'])
        self.assertIsNot(first, population)
        self.assertIsNot(first['agent_signals'], population['agent_signals'])
        self.assertIsNot(first['outcome'], population['outcome'])
        first['agent_signals']['trend'] = 'CHANGED'
        first['outcome']['net_return_pct'] = 999
        population['outcome']['was_bull_trap'] = not population['outcome']['was_bull_trap']
        result['eligible_tasks'].clear()
        self.assertEqual(source, before)
        with patch.object(retriever._memory, 'eligible', return_value=source):
            fresh = retriever.prepare_query(**self.fixture.query(scope='pooled'))
        self.assertEqual(fresh['eligible_tasks'], before)

    def test_invalid_nested_types_and_value_equal_scalars_stop_before_selection(self) -> None:
        retriever = self.fixture.create()
        original = self.fixture.rows[0]
        mutations = (
            lambda row: row['outcome'].update(net_return_pct=np.float64(row['outcome']['net_return_pct'])),
            lambda row: row['outcome'].update(was_bull_trap=int(row['outcome']['was_bull_trap'])),
            lambda row: row['agent_signals'].update(trend=np.str_(row['agent_signals']['trend'])),
            lambda row: row['agent_signals'].update(extra={'future': [1]}),
            lambda row: row.update(extra={'future': [1]}),
            lambda row: row.update(exit_date=self.fixture.query()['as_of_date']),
        )
        for mutate in mutations:
            row = copy.deepcopy(original)
            mutate(row)
            with self.subTest(row=row), patch.object(retriever._memory, 'eligible', return_value=[row]), \
                    patch.object(retriever, '_select_similarity') as selector, self.assertRaises(ValueError):
                retriever.select_prior_tasks(**self.fixture.query())
            selector.assert_not_called()

    def test_dict_key_order_and_repeated_cutoffs_preserve_exact_result(self) -> None:
        retriever = self.fixture.create()
        query = self.fixture.query(scope='pooled')
        expected = retriever.retrieve(**query)
        source = [copy.deepcopy(row) for row in self.fixture.rows if row['exit_date'] < query['as_of_date']]
        reordered = []
        for row in source:
            row['outcome'] = dict(reversed(list(row['outcome'].items())))
            row['agent_signals'] = dict(reversed(list(row['agent_signals'].items())))
            reordered.append(dict(reversed(list(row.items()))))
        with patch.object(retriever._memory, 'eligible', return_value=reordered):
            self.assertEqual(retriever.retrieve(**query), expected)
        retriever.retrieve(**self.fixture.query(as_of_date='2020-01-07'))
        self.assertEqual(retriever.retrieve(**query), expected)


if __name__ == '__main__':
    unittest.main()
