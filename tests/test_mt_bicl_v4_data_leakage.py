"""Kiểm input tương lai, query payoff, label-blind selection và lineage agent."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd

from core.mt_bicl_v4_data import bounded_index, feature_rows, fit_scaler, membership, symbol_data
from core.mt_bicl_v4_data_regimes import DataRegimes
from core.mt_bicl_v4_lineage import SIGNAL_DIR, agent_row
from core.mt_bicl_v4_protocol import checksum
from core.regime_detector import training_data_hash
from mt_bicl_v4_data_support import lineage, members, prices, save_lineage


class DataLeakageTests(unittest.TestCase):
    """Mọi phép chọn dùng X/metadata; mutation y hoặc hậu kỳ không làm đổi đầu vào."""

    def test_future_poisoned_prices_events_do_not_change_prefix_dataset(self) -> None:
        frame, calendar = prices(120)
        before = symbol_data('FPT', frame.iloc[:90], [], frame.iloc[:90][['Datetime', 'Close']])
        changed = frame.copy()
        changed.loc[90:, ['Open', 'High', 'Low', 'Close', 'Reference']] = np.nan
        after = symbol_data('FPT', changed, [{'exrightDate': str(calendar[100].date())}], frame.iloc[:90][['Datetime', 'Close']])
        self.assertEqual(before, after)

    def test_query_execution_price_is_never_a_query_feature(self) -> None:
        frame, calendar = prices(100)
        indices = np.array([50])
        before = feature_rows(frame, [], frame[['Datetime', 'Close']], calendar, indices)
        changed = frame.copy()
        changed.loc[51, ['Open', 'High']] = 200
        changed.loc[53, ['Close', 'High']] = 250
        after = feature_rows(changed, [], frame[['Datetime', 'Close']], calendar, indices)
        self.assertEqual(before, after)
        a = symbol_data('FPT', frame, [], frame[['Datetime', 'Close']])[1]
        b = symbol_data('FPT', changed, [], frame[['Datetime', 'Close']])[1]
        self.assertNotEqual(a['FPT-' + str(calendar[50].date())], b['FPT-' + str(calendar[50].date())])

    def test_scaler_and_membership_ignore_arbitrary_query_labels(self) -> None:
        rows, query, scaler, regimes = members()
        before = membership(query, rows, scaler, regimes)
        changed = deepcopy(rows)
        for row in changed:
            row['outcome'] = {'r_net': float('nan'), 'y': 'poison'}
        self.assertEqual(before, membership(query, changed, scaler, regimes))
        self.assertEqual(fit_scaler(rows, '2019-12-31'), fit_scaler(changed, '2019-12-31'))

    def test_scaler_excludes_exit_equal_query_and_feature_after_asof(self) -> None:
        rows, query, _, _ = members()
        equal = rows[5]['exit_date']
        fit_end = (pd.Timestamp(equal) - pd.Timedelta(days=1)).strftime('%Y-%m-%d')
        s = fit_scaler(rows, fit_end, query=equal)
        self.assertNotIn(rows[5]['episode_id'], s['fit_ids'])
        rows[0]['features']['feature_end_date'] = '2020-12-31'
        with self.assertRaises(ValueError): fit_scaler(rows, '2019-12-31')

    def test_future_fit_end_or_after_2020_is_rejected(self) -> None:
        rows, query, scaler, regimes = members()
        scaler['fit_end'] = query['as_of_date']
        with self.assertRaises(ValueError): membership(query, rows, scaler, regimes)
        with self.assertRaises(ValueError): fit_scaler(rows, '2021-01-01')

    def test_membership_excludes_unclosed_and_future_blocks(self) -> None:
        rows, query, scaler, regimes = members()
        changed = deepcopy(rows)
        changed[0]['exit_date'] = query['as_of_date']
        changed[1]['block_end_date'] = query['as_of_date']
        result = membership(query, changed, scaler, regimes)
        ids = [i for task in result['prior'] for i in task['observation_ids']] + result['target']
        self.assertNotIn(changed[0]['episode_id'], ids)

    def test_cross_block_and_year_boundary_labels_are_purged(self) -> None:
        frame, _ = prices(300)
        rows, labels = symbol_data('FPT', frame, [], frame[['Datetime', 'Close']])
        purged = [r for r in rows if 'CROSS_BLOCK_HOLDING' in r['label_reasons']]
        self.assertTrue(purged)
        self.assertTrue(all(r['episode_id'] not in labels for r in purged))
        year_purged = [r for r in rows if r['as_of_date'][:4] != r['exit_date'][:4]]
        self.assertTrue(year_purged)
        self.assertTrue(all(not r['label_eligible'] for r in year_purged))

    def test_index_reader_does_not_parse_future_payoff_fields(self) -> None:
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'index.csv'
            path.write_text('Datetime,Close\n2018-01-02,100\n2025-01-02,NOT_A_NUMBER\n', encoding='utf-8')
            actual = bounded_index(path, '2022-12-31')
            self.assertEqual(actual['Close'].tolist(), [100.])

    def test_future_news_or_price_metadata_cannot_be_rehashed_into_validity(self) -> None:
        for field in ('news_dates', 'price_end_date', 'alpha_end_date'):
            with self.subTest(field=field), TemporaryDirectory() as folder:
                root = Path(folder)
                row, frame, config, payload = lineage(root)
                payload['result']['provenance'][field] = ['2025-01-01'] if field == 'news_dates' else '2025-01-01'
                save_lineage(root, row['episode_id'], payload)
                with self.assertRaises(ValueError): agent_row(root, row, frame, config)

    def test_raw_agent_checksum_and_episode_cross_binding_are_required(self) -> None:
        with TemporaryDirectory() as folder:
            root = Path(folder)
            row, frame, config, payload = lineage(root)
            p = root / SIGNAL_DIR / (row['episode_id'] + '.json')
            p.write_bytes(p.read_bytes().replace(b'BULLISH', b'BEARISH', 1))
            with self.assertRaises(ValueError): agent_row(root, row, frame, config)

    def test_regime_after_train_or_query_is_rejected_and_early_prefix_unknown(self) -> None:
        frame, _ = prices(100)
        with TemporaryDirectory() as folder:
            r = DataRegimes(frame[['Datetime', 'Close']], Path(folder))
            self.assertEqual(r.classify('2018-04-01', '2018-03-01')['name'], 'UNKNOWN')
            with self.assertRaises(ValueError): r.model('2021-01-01')
            with self.assertRaises(ValueError): r.classify('2018-03-01', '2018-04-01')

    def test_cold_regime_replay_loads_matching_prefix_without_refit(self) -> None:
        frame, calendar = prices(620)
        history = frame[['Datetime', 'Close']]
        cutoff = str(calendar[599].date())
        with TemporaryDirectory() as folder:
            path = Path(folder) / (cutoff + '.json')
            path.write_bytes(b'fixture parameters')
            registry = {cutoff: {'file_sha256': checksum(path.read_bytes()),
                                'training_data_sha256': training_data_hash(history.iloc[:600])}}
            model = Mock()
            model.metadata = {'train_end_date': cutoff}
            with patch('core.mt_bicl_v4_data_regimes.MarketRegimeDetector.load', return_value=model) as load, \
                 patch('core.mt_bicl_v4_data_regimes.MarketRegimeDetector.fit', side_effect=AssertionError('không refit')):
                regime = DataRegimes(history, Path(folder), frozen=registry)
                regime.model(cutoff)
                load.assert_called_once()
            path.write_bytes(b'changed weights')
            with self.assertRaises(ValueError):
                DataRegimes(history, Path(folder), frozen=registry).model(cutoff)


if __name__ == '__main__':
    unittest.main()
