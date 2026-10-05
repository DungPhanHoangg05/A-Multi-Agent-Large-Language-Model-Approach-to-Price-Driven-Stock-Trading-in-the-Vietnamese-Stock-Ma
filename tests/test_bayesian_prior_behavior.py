"""Kiểm hợp đồng kết quả cuối cùng và query không được chứa nhãn kinh tế."""

import copy
import json
import math
from typing import Any
import unittest
from unittest.mock import patch

import numpy as np
from core.bayesian_retriever import MODES, REGIMES, SCOPES
from bayesian_test_support import PriorPipelineFixture


class BayesianPriorBehaviorTests(unittest.TestCase):
    """Bao phủ API/JSON toàn pipeline; tái dùng suite thuật toán đã có."""

    def setUp(self) -> None:
        self.fixture = PriorPipelineFixture()
        self.addCleanup(self.fixture.close)

    def test_all_modes_validate_unsafe_context_even_when_disabled_before_reading_memory(self) -> None:
        retriever = self.fixture.create()
        signals = self.fixture.query()['current_signals']
        invalid = [{'current_signals': {**signals, 'outcome': 'WIN_IF_LONG'}},
                   {'current_signals': {**signals, 'trend': 'BULLISH hoặc BEARISH'}},
                   {'current_signals': {**signals, 'trend': np.str_('BULLISH')}},
                   {'current_signals': {**signals, 'trend': float('nan')}},
                   {'seed': np.int64(42)}, {'as_of_date': '2020-1-14'}, {'current_regime': 'FUTURE_WIN'}]
        with patch.object(retriever._memory, 'eligible', side_effect=AssertionError('Đọc pool trước validation')):
            for mode in sorted(MODES):
                for k in (0, 3):
                    for change in invalid:
                        query = self.fixture.query(mode=mode, k=k, **copy.deepcopy(change))
                        before = copy.deepcopy(query)
                        with self.subTest(mode=mode, k=k, change=change), self.assertRaises(ValueError):
                            retriever.retrieve(**query)
                        # NaN không bằng chính nó; đối chiếu input bằng biểu diễn ổn định.
                        self.assertEqual(repr(query), repr(before))

    def test_complete_results_are_native_json_for_every_mode_scope_regime_and_k(self) -> None:
        retriever = self.fixture.create()

        def assert_native(value: Any) -> None:
            """Không để NumPy/Pandas scalar hoặc số không hữu hạn lọt vào state JSON."""
            self.assertIn(type(value), (dict, list, str, int, float, bool, type(None)))
            if type(value) is dict:
                for key, item in value.items():
                    self.assertIs(type(key), str)
                    assert_native(item)
            elif type(value) is list:
                for item in value:
                    assert_native(item)
            elif type(value) is float:
                self.assertTrue(math.isfinite(value))

        with patch('core.bayesian_retriever.read_json', side_effect=AssertionError('Query đọc JSON')), \
             patch('core.bayesian_memory.read_json', side_effect=AssertionError('Query đọc JSON')), \
             patch.object(retriever._memory, '_execution_loader', side_effect=AssertionError('Query đọc giá')):
            for mode in sorted(MODES):
                for scope in sorted(SCOPES):
                    for regime in sorted(REGIMES):
                        for k in (0, 1, 2, 3):
                            query = self.fixture.query(mode=mode, scope=scope, current_regime=regime, k=k)
                            before = copy.deepcopy(query)
                            bundle = self.fixture.bundle(retriever, query)
                            assert_native(bundle)
                            encoded = json.dumps(bundle, ensure_ascii=False, allow_nan=False)
                            self.assertEqual(json.loads(encoded), bundle)
                            self.assertEqual(query, before)
                            self.assertEqual(set(bundle['result']), {'tasks', 'stats', 'metadata'})
                            self.assertLessEqual(len(bundle['prefix']), 600)
                            if k == 0:
                                self.assertEqual(bundle['prefix'], '')
                                self.assertIsNone(bundle['result']['stats'])


if __name__ == '__main__':
    unittest.main()
