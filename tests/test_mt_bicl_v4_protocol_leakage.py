"""Kiểm ranh giới PIT/purge của fixture metadata; chưa nghiệm thu dataset v4."""

from __future__ import annotations

from copy import deepcopy
import unittest

from core.mt_bicl_v4_protocol import check_episode_metadata, fit_eligible
from test_mt_bicl_v4_protocol import fixture


class MetadataLeakageTests(unittest.TestCase):
    """Chặn ngày bằng cutoff, D/C trùng, query payoff và fit tương lai."""

    def test_purge_uses_closed_label_interval_not_only_asof(self) -> None:
        self.assertTrue(fit_eligible('2019-12-25', '2019-12-27', '2019-12-31', '2020-01-01', '2020-12-31'))
        for end in ('2020-01-01', '2020-01-02'):
            self.assertFalse(fit_eligible('2019-12-30', end, '2019-12-31', '2020-01-01', '2020-12-31'))
        self.assertFalse(fit_eligible('2019-12-25', '2019-12-31', '2019-12-30', '2020-01-01', '2020-12-31'))
        with self.assertRaises(ValueError):
            fit_eligible('2019-12-25', '2019-12-31', '2020-01-01', '2020-01-01', '2020-12-31')

    def test_valid_metadata_and_trained_cold_start(self) -> None:
        check_episode_metadata(fixture())
        cold = fixture()
        cold.update(prior=[], target=[])
        check_episode_metadata(cold)

    def test_context_exit_equal_query_or_future_is_rejected(self) -> None:
        for end in ('2020-07-10', '2020-07-11'):
            value = fixture()
            value['target'][0]['exit_date'] = end
            with self.subTest(end=end), self.assertRaises(ValueError):
                check_episode_metadata(value)

    def test_query_label_or_payoff_never_enters_metadata(self) -> None:
        for key in ('y', 'r_net', 'outcome', 'future_close'):
            value = fixture()
            value['query'][key] = 1
            with self.subTest(key=key), self.assertRaises(ValueError):
                check_episode_metadata(value)

    def test_future_feature_scaler_or_regime_is_rejected(self) -> None:
        for field in ('feature_end_date', 'scaler_fit_end', 'regime_fit_end'):
            value = fixture()
            value['target'][0][field] = '2020-07-11'
            with self.subTest(field=field), self.assertRaises(ValueError):
                check_episode_metadata(value)

    def test_historical_rows_may_share_train_scaler_without_future_query_fit(self) -> None:
        value = fixture()
        self.assertGreater(value['prior'][0]['observations'][0]['scaler_fit_end'],
                           value['prior'][0]['observations'][0]['as_of_date'])
        check_episode_metadata(value)
        value['query']['scaler_fit_end'] = value['query']['as_of_date']
        with self.assertRaises(ValueError):
            check_episode_metadata(value)

    def test_disjoint_ids_intervals_and_task_boundary(self) -> None:
        variants = []
        value = fixture(); value['target'][0]['episode_id'] = 'q'; variants.append(value)
        value = fixture(); value['target'][0]['task_id'] = 'FPT:block0'; variants.append(value)
        value = fixture(); value['prior'][0]['block_end_date'] = '2020-07-10'; variants.append(value)
        value = fixture(); value['prior'][0]['block_end_date'] = '2020-05-05'; variants.append(value)
        value = fixture(); value['prior'][0]['observations'][1]['entry_date'] = '2020-05-06'
        value['prior'][0]['observations'][1]['as_of_date'] = '2020-05-05'
        value['prior'][0]['observations'][1]['feature_end_date'] = '2020-05-05'; variants.append(value)
        value = fixture(); value['target'][0]['symbol'] = 'MWG'; variants.append(value)
        for i, value in enumerate(variants):
            with self.subTest(i=i), self.assertRaises(ValueError):
                check_episode_metadata(value)

    def test_length_domain_does_not_pad_duplicate_tasks(self) -> None:
        value = fixture()
        value['prior'].append(deepcopy(value['prior'][0]))
        with self.assertRaises(ValueError):
            check_episode_metadata(value)
        value = fixture()
        value['target'] *= 33
        with self.assertRaises(ValueError):
            check_episode_metadata(value)

    def test_confirmation_year_is_not_opened_by_metadata(self) -> None:
        value = fixture()
        for field in ('as_of_date', 'feature_end_date'):
            value['query'][field] = '2025-01-02'
        value['query'].update(entry_date='2025-01-03', exit_date='2025-01-07')
        with self.assertRaises(ValueError):
            check_episode_metadata(value)


if __name__ == '__main__':
    unittest.main()
