"""Hồi quy T19: lịch chính thức, oracle settlement và bảo toàn release offline."""

from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from core.revision_execution import execution_ledger
from core.revision_execution_final import (COSTS, POLICY, audit_ledger, build_release, cases_from_final,
    check_calendar, check_manifest, check_release, json_bytes, output_path, read, settlement, sha)

ROOT = Path(__file__).resolve().parents[1]
POLICY_VALUE = read(ROOT / POLICY)


def fixture() -> tuple[pd.DataFrame, dict]:
    """Dữ liệu giả có lịch nghỉ 30/4 sửa đổi; không là evidence thị trường."""
    config = {'weekmask': '1111100', 'holidays': ['2024-04-18', '2024-04-29', '2024-04-30', '2024-05-01'],
              'supported_years': [2024]}
    days = pd.bdate_range('2024-04-01', periods=65).strftime('%Y-%m-%d')
    days = days[~days.isin(config['holidays'])]
    close = np.full(len(days), 100.)
    close[24:28] = [105., 98., 102., 110.]
    frame = pd.DataFrame({'date': days, 'Open': np.full(len(days), 100.),
        'High': np.maximum(close, 100.) + 1, 'Low': np.minimum(close, 100.) - 1,
        'Close': close, 'Volume': np.full(len(days), 100000.)})
    return frame, config


class FinalExecutionTests(unittest.TestCase):
    """Oracle có ngày thay cho offsets, và fixtures chặn mất/tamper evidence."""

    def test_calendar_amendment_and_missing_vendor_day_fail_closed(self) -> None:
        frame, config = fixture()
        calendar = check_calendar(frame, 0, len(frame) - 1, config)
        self.assertEqual(settlement('2024-04-25', 2, calendar), '2024-05-02')
        self.assertEqual(settlement('2024-04-26', 2, calendar), '2024-05-03')
        with self.assertRaises(ValueError): settlement('2024-04-29', 2, calendar)
        missing = frame.drop(index=24).reset_index(drop=True)
        with self.assertRaisesRegex(ValueError, 'Observed bars'): check_calendar(missing, 0, len(missing) - 1, config)
        with self.assertRaises(ValueError): check_calendar(frame, 0, 5, {**config, 'supported_years': [2023]})

    def test_oracle_full_family_with_fast_cash_reuse_and_residuals(self) -> None:
        frame, config = fixture()
        calendar = check_calendar(frame, 0, len(frame) - 1, config)
        for chosen in POLICY_VALUE['scenarios']:
            with self.subTest(chosen['id']):
                scenario = {**POLICY_VALUE['defaults'], **chosen}
                result = execution_ledger(frame, [(22, 24, 1, 'a'), (25, 27, 1, 'b')], scenario, 50_000_000.)
                self.assertEqual(audit_ledger(frame, result, scenario, 50_000_000., 1000., calendar), len(result['daily']))
                if chosen['id'] == 'advance_on_demand': self.assertGreater(result['summary']['advance_fee_vnd'], 0)
                if chosen['id'] == 'pending_t2': self.assertEqual(result['summary']['n_buy_fills'], 1)
                if chosen['id'] == 'all_entries_missed': self.assertEqual(result['summary']['net_return_pct'], 0.)

    def test_oracle_catches_pending_double_count_and_stock_sale_before_maturity(self) -> None:
        frame, calendar_config = fixture()
        calendar = check_calendar(frame, 0, len(frame) - 1, calendar_config)
        config = {**POLICY_VALUE['defaults'], 'cash_mode': 'pending', 'stock_lag': 2}
        result = execution_ledger(frame, [(22, 24, 1, 'a')], config, 50_000_000.)
        broken = deepcopy(result)
        broken['daily'][2]['settled_cash_vnd'] += broken['daily'][2]['pending_cash_vnd']
        with self.assertRaisesRegex(ValueError, 'settled_cash'): audit_ledger(frame, broken, config, 50_000_000., 1000., calendar)
        with self.assertRaisesRegex(ValueError, 'chưa về'):
            audit_ledger(frame, result, {**config, 'stock_lag': 3}, 50_000_000., 1000., calendar)

    def test_oracle_delayed_buy_exit_residual_and_tax_formula(self) -> None:
        frame, calendar_config = fixture()
        frame.loc[22, 'Volume'] = 0.
        config = {**POLICY_VALUE['defaults'], 'cash_mode': 'pending', 'stock_lag': 2,
                  'block_proxy': True, 'entry_delay': 2, 'sell_charge': .001}
        calendar = check_calendar(frame, 0, len(frame) - 1, calendar_config)
        result = execution_ledger(frame, [(22, 24, 1, 'a')], config, 50_000_000.)
        self.assertEqual(next(e['date'] for e in result['events'] if e['side'] == 'BUY' and e['status'] == 'filled'), frame['date'].iloc[23])
        audit_ledger(frame, result, config, 50_000_000., 1000., calendar)
        sell = next(e for e in result['events'] if e['side'] == 'SELL' and e['status'] == 'filled')
        self.assertAlmostEqual(result['summary']['sell_charge_vnd'], sell['quantity'] * sell['fill_price_vnd'] * .001)
        frame.loc[25:, ['Open', 'High', 'Low', 'Close']] = 80.
        residual = execution_ledger(frame, [(22, 24, 1, 'a')], config, 50_000_000.)
        self.assertGreater(residual['summary']['final_shares'], 0.)
        audit_ledger(frame, residual, config, 50_000_000., 1000., calendar)

    def test_oracle_maturity_outside_prices_preserves_pending(self) -> None:
        frame, calendar_config = fixture()
        config = {**POLICY_VALUE['defaults'], 'cash_mode': 'advance_auto', 'stock_lag': 2}
        end = len(frame) - 1
        result = execution_ledger(frame, [(end - 2, end, 1, 'tail')], config, 50_000_000.)
        calendar = check_calendar(frame, 0, end, calendar_config)
        audit_ledger(frame, result, config, 50_000_000., 1000., calendar)
        self.assertGreater(result['summary']['final_pending_cash_vnd'], 0.)
        self.assertEqual(result['summary']['advance_fee_vnd'], 0.)

    def manifest_fixture(self, root: Path, folder: Path) -> None:
        """Receipt tối thiểu có self-digest, source và output độc lập."""
        (root / 'source').write_bytes(b'input')
        folder.mkdir(parents=True)
        (folder / 'report.json').write_bytes(b'{}')
        manifest = {'runtime': {}, 'sources': [{'path': 'source', 'sha256': sha(root / 'source')}],
                    'outputs': [{'path': 'report.json', 'sha256': sha(folder / 'report.json')}]}
        manifest['sha256'] = hashlib.sha256(json_bytes(manifest)).hexdigest()
        (folder / 'manifest.json').write_bytes(json_bytes(manifest))

    def test_hash_source_output_self_digest_and_extra_file(self) -> None:
        for mutation in ('source', 'output', 'self', 'extra'):
            with self.subTest(mutation), tempfile.TemporaryDirectory() as folder:
                root = Path(folder); output = root / 'outputs/revision/execution_final_test'
                self.manifest_fixture(root, output)
                self.assertEqual(check_manifest(root, output), 2)
                if mutation == 'source': (root / 'source').write_bytes(b'tampered')
                elif mutation == 'output': (output / 'report.json').write_bytes(b'tampered')
                elif mutation == 'self':
                    manifest = read(output / 'manifest.json'); manifest['runtime'] = {'tampered': True}
                    (output / 'manifest.json').write_bytes(json_bytes(manifest))
                else: (output / 'extra').write_bytes(b'extra')
                with self.assertRaises(ValueError): check_manifest(root, output)

    def test_check_is_hash_only_and_validates_parents(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); output = root / 'outputs/revision/execution_final_test'
            self.manifest_fixture(root, output)
            with patch('core.revision_execution_final.runtime', return_value={}), \
                 patch('core.revision_execution_final.generate', side_effect=AssertionError('Không build khi check')), \
                 patch('core.revision_execution_final.check_parents', return_value={'T04': 3524, 'T18': 24}) as parents:
                self.assertEqual(check_release(root, output), {'T19': 2, 'T04': 3524, 'T18': 24})
                parents.assert_called_once_with(root)

    def test_output_guards_and_build_offline_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for target in ('paper/new', 'outputs/revision/revision_minimal_v1', '../execution_final_escape',
                           'outputs/revision/execution_final_a/child'):
                with self.assertRaises(ValueError): output_path(root, Path(target))
            output = root / 'outputs/revision/execution_final_test'; output.mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, 'ghi đè'): build_release(root, output)
            output.rmdir()
            with patch('core.revision_execution_final.generate', side_effect=lambda _: socket.create_connection(('example.invalid', 443))):
                with self.assertRaisesRegex(AssertionError, 'offline'): build_release(root, output)
            self.assertFalse(output.exists())

    def test_duplicate_missing_or_nonfinal_prediction_support_rejected(self) -> None:
        with self.assertRaises(ValueError): cases_from_final([], [], [])
        units = [{'id': f'u{i}'} for i in range(102)]
        with self.assertRaises(ValueError): cases_from_final(units, [{'unit_id': 'same', 'variant': 'B'}] * 918, [])


if __name__ == '__main__':
    unittest.main()
