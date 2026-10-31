"""Kiểm feature, nhãn kinh tế, lineage và snapshot dataset bằng dữ liệu tổng hợp."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np
import pandas as pd
import talib

from core.mt_bicl_v4_data import NUMERIC, bounded_index, feature_rows, fit_scaler, membership, symbol_data
from core.mt_bicl_v4_dataset import coverage, fold_views, immutable
from core.mt_bicl_v4_data_regimes import DataRegimes
from core.mt_bicl_v4_lineage import SIGNAL_DIR, agent_row
from core.mt_bicl_v4_protocol import canonical
from mt_bicl_v4_data_support import lineage, members, prices, save_lineage


class DataTests(unittest.TestCase):
    """Đối soát scalar độc lập và giữ missing/query chưa đủ điều kiện trong mẫu."""

    def test_nine_features_match_scalar_formulas_and_exact_45_macd(self) -> None:
        frame, calendar = prices(100)
        frame["Volume"] = 1000 + np.arange(100)
        i = 65
        actual = feature_rows(frame, [], frame[["Datetime", "Close"]], calendar, np.array([i]))[0]
        c = frame["Close"].to_numpy()
        _, _, macd = talib.MACD(np.ascontiguousarray(c[i - 44:i + 1]), fastperiod=12, slowperiod=26, signalperiod=9)
        r = c[i - 19:i + 1] / c[i - 20:i] - 1
        expected = [c[i] / c[i - 5] - 1, c[i] / c[i - 20] - 1, np.std(r, ddof=1),
            c[i] / np.mean(c[i - 19:i + 1]) - 1, macd[-1] / c[i],
            frame['Volume'].iloc[i] / frame['Volume'].iloc[i - 19:i + 1].mean() - 1,
            (frame['High'].iloc[i - 19:i + 1].max() - frame['Low'].iloc[i - 19:i + 1].min()) / c[i],
            c[i] / c[i - 20] - 1, np.std(r, ddof=1)]
        np.testing.assert_allclose(actual['raw'], expected, rtol=0, atol=1e-14)
        self.assertEqual(actual['status'], 'AVAILABLE')

    def test_flat_market_label_is_down_after_four_cost_factors(self) -> None:
        frame, _ = prices(100, flat=True)
        rows, labels = symbol_data('FPT', frame, [], frame[['Datetime', 'Close']])
        value = labels[rows[0]['episode_id']]
        expected = (1 - .001) * (1 - .0025) / ((1 + .001) * (1 + .0025)) - 1
        self.assertAlmostEqual(value['r_net'], expected, places=15)
        self.assertEqual(value['y'], 0)
        self.assertEqual(len(rows), len(range(20, 97, 3)))

    def test_short_warmup_and_missing_X_do_not_delete_queries_or_labels(self) -> None:
        frame, _ = prices(100)
        rows, labels = symbol_data('FPT', frame, [], frame[['Datetime', 'Close']])
        first = rows[0]
        self.assertEqual(first['features']['status'], 'UNAVAILABLE')
        self.assertTrue(first['label_eligible'])
        self.assertIn(first['episode_id'], labels)
        self.assertNotIn('r_net', canonical(first).decode())

    def test_zero_volume_and_corporate_events_have_distinct_effects(self) -> None:
        frame, calendar = prices(100)
        changed = frame.copy()
        changed.loc[21, 'Volume'] = 0
        rows, labels = symbol_data('FPT', changed, [], frame[['Datetime', 'Close']])
        self.assertIn('NO_MATCHED_VOLUME_AT_EXECUTION', rows[0]['label_reasons'])
        self.assertNotIn(rows[0]['episode_id'], labels)
        a = feature_rows(frame, [{'exrightDate': str(calendar[55].date())}], frame[['Datetime', 'Close']], calendar, np.array([65]))[0]
        self.assertIn('CORPORATE_ACTION_FEATURE_WINDOW', a['reasons'])

    def test_raw_label_only_sidecar_and_JSON_native(self) -> None:
        frame, _ = prices(100)
        rows, labels = symbol_data('MWG', frame, [], frame[['Datetime', 'Close']])
        value = json.loads(canonical({'rows': rows, 'labels': labels}))
        self.assertEqual(len(value['rows']), len(rows))
        self.assertTrue(all('r_net' not in row for row in value['rows']))
        self.assertEqual(len(NUMERIC), 9)

    def test_membership_ranks_without_win_loss_bucket_and_selects_K_domain(self) -> None:
        rows, query, scaler, regimes = members()
        actual = membership(query, rows, scaler, regimes)
        self.assertEqual(actual['K'], 3)
        self.assertEqual(actual['m'], 4)
        self.assertEqual(set(actual['target']), {r['episode_id'] for r in rows[15:19]})
        smaller = rows[5:]
        self.assertEqual(membership(query, smaller, scaler, regimes)['K'], 1)

    def test_query_missing_or_cold_scaler_has_explicit_empty_membership(self) -> None:
        rows, query, scaler, regimes = members()
        query['features']['status'] = 'UNAVAILABLE'
        actual = membership(query, rows, scaler, regimes)
        self.assertEqual((actual['K'], actual['m']), (0, 0))
        self.assertEqual(actual['reason'], 'QUERY_OR_SCALER_UNAVAILABLE')

    def test_OOD_remains_in_cohort_without_clipping(self) -> None:
        rows, query, scaler, regimes = members()
        query['features']['raw'] = [7.] * 9
        actual = membership(query, rows, scaler, regimes)
        self.assertTrue(actual['ood'])
        self.assertEqual(actual['query_z'], [7.] * 9)

    def test_scaler_uses_sample_std_and_floor(self) -> None:
        frame, _ = prices(100, flat=True)
        rows, _ = symbol_data('FPT', frame, [], frame[['Datetime', 'Close']])
        s = fit_scaler(rows, '2018-12-31')
        self.assertEqual(s['status'], 'AVAILABLE')
        self.assertTrue(all(x == 1e-8 for x in s['scale']))

    def test_agent_reports_are_real_but_a0_is_never_fabricated(self) -> None:
        with TemporaryDirectory() as folder:
            root = Path(folder)
            row, frame, config, _ = lineage(root)
            actual = agent_row(root, row, frame, config)
            self.assertEqual(actual['categories']['trend'], 'BULLISH')
            self.assertEqual(actual['categories']['alpha_consensus'], 'BULLISH')
            self.assertEqual(actual['categories']['original_action'], 'UNKNOWN')
            self.assertEqual(actual['status'], 'UNAVAILABLE')
            self.assertIn('NO_DURABLE_ORIGINAL', actual['reasons'])

    def test_prompt_mismatch_is_not_silently_used_for_training(self) -> None:
        with TemporaryDirectory() as folder:
            root = Path(folder)
            row, frame, config, _ = lineage(root)
            (root / 'agents/trend_agent.py').write_text('new prompt', encoding='utf-8')
            actual = agent_row(root, row, frame, config)
            self.assertEqual(actual['observed_legacy_categories']['trend'], 'BULLISH')
            self.assertEqual(actual['categories']['trend'], 'UNKNOWN')
            self.assertIn('LEGACY_AGENT_PROMPT_SOURCE_INCOMPATIBLE', actual['reasons'])

    def test_agent_missing_before_warmup_is_retained_with_reason(self) -> None:
        with TemporaryDirectory() as folder:
            actual = agent_row(Path(folder), {'episode_id': 'FPT-2018-02-01', 'as_of_date': '2018-02-01',
                'alpha_history_rows': 20}, pd.DataFrame(), {})
            self.assertIn('ALPHA_WARMUP_LT600', actual['reasons'])
            self.assertIn('NO_HISTORICAL_AGENT_REPORT', actual['reasons'])

    def test_snapshot_write_is_immutable_and_cold_mode_cannot_materialize(self) -> None:
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'data.json'
            with self.assertRaises(ValueError): immutable(path, {'x': 1}, verify_only=True)
            immutable(path, {'x': 1})
            original = path.read_bytes()
            immutable(path, {'x': 1}, verify_only=True)
            self.assertEqual(path.read_bytes(), original)
            with self.assertRaises(ValueError): immutable(path, {'x': 2})

    def test_valid_numeric_artifacts_do_not_falsely_pass_agent_readiness(self) -> None:
        frame, _ = prices(100)
        rows = []
        for symbol in ('FPT', 'MWG', 'VCB', 'VNM'):
            group, _ = symbol_data(symbol, frame, [], frame[['Datetime', 'Close']])
            for row in group:
                row['agent'] = {'status': 'UNAVAILABLE', 'source': None,
                                'reasons': ['NO_DURABLE_ORIGINAL']}
            rows.extend(group)
        spec = json.loads(Path('docs/plan/week11/protocol_v4.json').read_bytes())
        with TemporaryDirectory() as folder:
            regimes = DataRegimes(frame[['Datetime', 'Close']], Path(folder))
            folds = fold_views(rows, spec, regimes)
            report = coverage(rows, folds, spec)
        self.assertEqual(report['technical_audit'], 'PASS')
        self.assertEqual(report['status'], 'INSUFFICIENT_DATA')
        self.assertFalse(report['ready_for_W11_19'])
        self.assertEqual(report['full_summary']['agent_valid'], 0)
        self.assertTrue(report['failed_checks'])


if __name__ == '__main__':
    unittest.main()
