"""Kiểm scaler từng chiều, shared-core distance và panel lịch cố định."""

from copy import deepcopy
from pathlib import Path
import unittest

import numpy as np

from core.mt_bicl_v4_protocol import read
from core.mt_bicl_v41_bank import select_panel
from core.mt_bicl_v41_data import core_valid, distance, fit_scaler, membership, support, transform
from core.mt_bicl_v41_protocol import PANEL_SHA
from mt_bicl_v4_data_support import members


def fixture():
    """Lịch synthetic có lõi chung, task trước query và mask tường minh."""
    rows, query, scaler, regimes = members()
    for row in rows:
        row['features']['missing_mask'] = [False]*9
    query = deepcopy(rows[-1])
    scaler['available_dimensions'] = [True]*9
    return rows, query, scaler, regimes


class MaskedDataTests(unittest.TestCase):
    """Số0 chuẩn hóa không được thay thế ý nghĩa của mask."""

    def test_scaler_uses_each_observed_dimension_only(self) -> None:
        rows, query, _, _ = fixture()
        rows[0]['features']['missing_mask'][1] = True
        rows[0]['features']['raw'][1] = 1e99
        cap = rows[9]['exit_date']
        scaler = fit_scaler(rows, cap)
        self.assertEqual(scaler['observed_count'][0], 10)
        self.assertEqual(scaler['observed_count'][1], 9)
        expected = [r['features']['raw'][1] for r in rows[1:10]]
        self.assertAlmostEqual(scaler['mean'][1], np.mean(expected))
        self.assertAlmostEqual(scaler['scale'][1], np.std(expected, ddof=1))

    def test_missing_zero_has_separate_mask_and_no_OOD(self) -> None:
        _, query, scaler, _ = fixture()
        query['features']['missing_mask'][1] = True
        query['features']['raw'][1] = 1e99
        transformed = transform(query, scaler)
        self.assertEqual(transformed['z'][1], 0.)
        self.assertTrue(transformed['mask'][1])
        self.assertFalse(transformed['ood'])
        self.assertTrue(transformed['eligible'])

    def test_dimension_with_less_than_two_values_is_unavailable(self) -> None:
        rows, query, _, _ = fixture()
        for r in rows:
            r['features']['missing_mask'][1] = True
        scaler = fit_scaler(rows, rows[8]['exit_date'])
        self.assertIsNone(scaler['mean'][1])
        self.assertIsNone(scaler['scale'][1])
        self.assertFalse(scaler['available_dimensions'][1])
        self.assertFalse(transform(query, scaler)['eligible'])

    def test_shared_distance_matches_scalar_oracle_and_penalty(self) -> None:
        a, b = np.arange(9, dtype=float), np.zeros(9)
        am, bm = np.zeros(9, dtype=bool), np.zeros(9, dtype=bool)
        am[1:7] = True
        expected = (0+49+64)/3 + .25*6/9
        self.assertAlmostEqual(distance(a, am, b, bm), expected)
        bm[0] = True
        with self.assertRaises(ValueError): distance(a, am, b, bm)

    def test_membership_accepts_optional_missing_and_reports_mask(self) -> None:
        rows, query, scaler, regimes = fixture()
        for r in rows:
            r['features']['missing_mask'][1] = True
        query['features']['missing_mask'][1] = True
        member = membership(query, rows, scaler, regimes)
        self.assertEqual(member['K'], 3)
        self.assertTrue(member['query_mask'][1])
        self.assertEqual(member['query_z'][1], 0.)
        self.assertGreater(member['m'], 0)

    def test_missing_core_falls_back_and_is_not_counted_as_core_support(self) -> None:
        rows, query, scaler, regimes = fixture()
        query['features']['missing_mask'][0] = True
        self.assertFalse(core_valid(query))
        self.assertEqual(membership(query, rows, scaler, regimes)['reason'], 'MISSING_CORE')
        self.assertEqual(support([query])['core_valid'], 0)

    def test_actual_panel_256_hash_counts_and_dual_roles(self) -> None:
        directory = Path('outputs/bayesian_benchmark/mt_bicl_v4/data')
        rows = read((directory/'observations.json').read_bytes())['rows']
        folds = read((directory/'folds.json').read_bytes())
        panel = select_panel(rows, folds)
        self.assertEqual(panel['point_ids_sha256'], PANEL_SHA)
        self.assertEqual((panel['core_valid'], panel['complete_case']), (248, 155))
        self.assertEqual([len(s) for s in panel['shards'].values()], [64]*4)
        self.assertEqual(len(panel['fold_roles']['outer_2020']), 64)
        self.assertEqual(set(panel['fold_roles']['inner_2020H1']+panel['fold_roles']['inner_2020H2']), set(panel['fold_roles']['outer_2020']))

    def test_insufficient_panel_stratum_fails_without_reallocation(self) -> None:
        with self.assertRaisesRegex(ValueError, 'INSUFFICIENT_PANEL'):
            select_panel([], {})


if __name__ == '__main__':
    unittest.main()
