"""Kiểm poison nhãn/future/mask và disjoint D/C của đường dữ liệu v4.1."""

from copy import deepcopy
from pathlib import Path
import unittest

from core.mt_bicl_v4_protocol import read
from core.mt_bicl_v41_bank import select_panel
from core.mt_bicl_v41_data import fit_scaler, membership, transform
from test_mt_bicl_v41_data import fixture


class MaskedLeakageTests(unittest.TestCase):
    """Không mở nhãn để xếp context hoặc sửa panel sau action."""

    def test_label_and_agent_poison_do_not_change_scaler_or_membership(self) -> None:
        rows, query, scaler, regimes = fixture()
        before = membership(query, rows, scaler, regimes)
        changed = deepcopy(rows)
        for r in changed:
            r.update(r_net=1e90, y=0, agent={'status': 'AVAILABLE', 'original_action': 'LONG'})
        self.assertEqual(before, membership(query, changed, scaler, regimes))
        cap = rows[9]['exit_date']
        self.assertEqual(fit_scaler(rows, cap), fit_scaler(changed, cap))

    def test_future_observation_cannot_change_past_scaler_or_membership(self) -> None:
        rows, query, scaler, regimes = fixture()
        altered = deepcopy(rows)
        future = deepcopy(rows[-1])
        future.update(episode_id='FPT-2021-01-01', as_of_date='2021-01-01', entry_date='2021-01-04', exit_date='2021-01-06')
        future['features'].update(raw=[1e50]*9, feature_end_date='2021-01-01')
        altered.append(future)
        self.assertEqual(membership(query, rows, scaler, regimes), membership(query, altered, scaler, regimes))
        self.assertEqual(fit_scaler(rows, rows[9]['exit_date']), fit_scaler(altered, rows[9]['exit_date']))

    def test_future_feature_provenance_raises_instead_of_becoming_missing(self) -> None:
        rows, query, scaler, regimes = fixture()
        query['features']['feature_end_date'] = '2022-01-01'
        with self.assertRaises(ValueError): membership(query, rows, scaler, regimes)

    def test_scaler_future_and_exit_equal_query_are_forbidden(self) -> None:
        rows, query, scaler, regimes = fixture()
        scaler['fit_end'] = query['as_of_date']
        with self.assertRaises(ValueError): membership(query, rows, scaler, regimes)
        scaler['fit_end'] = '2018-12-31'
        rows[0]['exit_date'] = query['as_of_date']
        member = membership(query, rows, scaler, regimes)
        selected = [i for t in member['prior'] for i in t['observation_ids']] + member['target']
        self.assertNotIn(rows[0]['episode_id'], selected)

    def test_duplicate_context_ID_is_not_silently_reweighted(self) -> None:
        rows, query, scaler, regimes = fixture()
        rows.append(deepcopy(rows[0]))
        with self.assertRaises(ValueError): membership(query, rows, scaler, regimes)

    def test_panel_is_invariant_to_return_action_and_numeric_coverage_poison(self) -> None:
        directory = Path('outputs/bayesian_benchmark/mt_bicl_v4/data')
        rows = read((directory/'observations.json').read_bytes())['rows']
        folds = read((directory/'folds.json').read_bytes())
        before = select_panel(rows, folds)
        changed = deepcopy(rows)
        for r in changed:
            r.update(r_net=-1e90, action='SHORT', confidence=1., agent={})
            r['features']['raw'] = [0.]*9
            r['features']['missing_mask'] = [False]*9
        after = select_panel(changed, folds)
        for key in ('point_ids', 'strata', 'shards', 'point_ids_sha256', 'fold_roles'):
            self.assertEqual(before[key], after[key])

    def test_masked_value_poison_does_not_change_transform_or_retrieval(self) -> None:
        rows, query, scaler, regimes = fixture()
        query['features']['missing_mask'][3] = True
        rows[0]['features']['missing_mask'][3] = True
        before = membership(query, rows, scaler, regimes)
        query['features']['raw'][3] = 1e200
        rows[0]['features']['raw'][3] = -1e200
        self.assertEqual(before, membership(query, rows, scaler, regimes))
        self.assertEqual(transform(query, scaler)['z'][3], 0.)


if __name__ == '__main__':
    unittest.main()
