"""Kiểm T04 offline: support, repeats, ledger và release không ghi đè bằng chứng."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import numpy as np
import pandas as pd

from core.revision_common_study import digest, write_json
from core.revision_minimal_analysis import (account_rows, build_release, check_release, checked_predictions,
                                           metric_groups, numeric_closure, offline_guard, output_path, repeat_panel)
from core.revision_minimal_bank import BANK, sha


def fixture() -> tuple[list[dict], dict, dict]:
    """Hai lớp ở hai blocks; mỗi cycle đủ ba phiên với giá hữu hạn."""
    units = [{'id': 'u0', 'symbol': 'SYNTHETIC', 'fold': 'b0', 'date': '2026-01-01', 'decision': 0},
             {'id': 'u1', 'symbol': 'SYNTHETIC', 'fold': 'b1', 'date': '2026-01-05', 'decision': 4}]
    frame = pd.DataFrame({'date': pd.date_range('2026-01-01', periods=8).astype(str),
                          'Open': np.full(8, 100.), 'Close': [100., 100., 100., 110., 100., 100., 100., 90.]})
    protocol = {'fee_each_side': .0025, 'slippage_each_side': .001, 'initial_capital_vnd': 50_000_000.}
    return units, {'SYNTHETIC': frame}, protocol


class MinimalAnalysisTests(unittest.TestCase):
    """Không dùng response thật làm fixture hoặc gọi provider."""

    def rows(self) -> list[dict]:
        """Metadata/target/input giống nhau cho hai baseline giả lập."""
        units, _, _ = fixture()
        return [{**u, 'unit_id': u['id'], 'variant': v, 'label_net': 'UP' if u['id'] == 'u0' else 'DOWN',
                 'label_gross': 'UP' if u['id'] == 'u0' else 'DOWN', 'market_input_hash': u['id'],
                 'prediction': 'LONG' if v == 'long' else 'SHORT'} for v in ('cash', 'long') for u in units]

    def test_missing_duplicate_target_and_information_support_fail(self) -> None:
        units, _, _ = fixture(); labels = {'u0': ('UP', 'UP'), 'u1': ('DOWN', 'DOWN')}
        self.assertEqual(checked_predictions(self.rows(), units, labels, {'u0': 'u0', 'u1': 'u1'}), ['cash', 'long'])
        for mutation in ('missing', 'duplicate', 'target', 'input', 'metadata'):
            with self.subTest(mutation=mutation):
                rows = self.rows()
                if mutation == 'missing': rows.pop()
                elif mutation == 'duplicate': rows[-1] = deepcopy(rows[-2])
                elif mutation == 'target': rows[0]['label_net'] = 'DOWN'
                elif mutation == 'input': rows[0]['market_input_hash'] = 'future'
                else: rows[0]['date'] = '2099-01-01'
                with self.assertRaises(ValueError): checked_predictions(rows, units, labels, {'u0': 'u0', 'u1': 'u1'})

    def test_macro_support_and_undefined_class_are_explicit(self) -> None:
        rows = [r for r in self.rows() if r['variant'] == 'cash']
        actual = metric_groups(rows)
        self.assertEqual(actual['pooled']['balanced_accuracy'], .5)
        self.assertIsNone(actual['by_block']['b0']['balanced_accuracy'])
        self.assertEqual(actual['macro_symbol']['balanced_accuracy']['n_defined'], 1)
        self.assertIsNone(actual['pooled']['mcc'])
        with self.assertRaises(ValueError): metric_groups(rows + [rows[0]])

    def test_cash_and_two_leg_fee_ledger_match_independent_formula(self) -> None:
        units, frames, protocol = fixture()
        accounts, daily, counts, returns = account_rows(self.rows(), units, frames, protocol, 'main', 0)
        for row in accounts:
            if row['variant'] == 'cash':
                self.assertEqual(row['net_return_pct'], 0.); self.assertEqual(row['order_count'], 0)
            else:
                ratio = 1.1 if row['fold'] == 'b0' else .9
                expected = (ratio * .9975 * .999 / (1.0025 * 1.001) - 1) * 100
                self.assertAlmostEqual(row['net_return_pct'], expected)
                self.assertEqual(row['order_count'], 2)
        self.assertEqual(len(daily), 12)
        self.assertEqual(counts['cash'].sum(), 2)
        self.assertEqual(returns['cash'][:, 1].tolist(), [1., 1.])

    def panel(self, upstream: bool = False) -> tuple:
        """Mỗi execution có ID riêng, prediction có thể trùng nhưng không sao chép raw."""
        units, frames, protocol = fixture(); records, requests = [], {}
        variants = ('B', 'AS') if upstream else ('B', 'A', 'S', 'AS', 'P')
        for u in units:
            for v in variants:
                for run in range(3):
                    context = {'unit_id': u['id'], 'variant': v, 'realization': run if upstream else 0,
                               'repeat': 0 if upstream else run, 'model': 'mock', 'smoke': False, 'stage': 'decision'}
                    attempt = f"{u['id']}_{v}_{run}"
                    correct = (v == 'AS' and run != 1) or (v != 'AS' and run == 1)
                    pred = ('LONG' if u['id'] == 'u0' else 'SHORT') if correct else ('SHORT' if u['id'] == 'u0' else 'LONG')
                    records.append({'context': context, 'request_ids': [attempt], 'decision_source': 'llm_structured',
                                    'fallback_reason': None, 'prediction': pred,
                                    'parent': {'upstream_hash': f'parent{run if upstream else 0}'}})
                    requests[attempt] = {'context': context.copy(), 'messages': [u['id'], v, run if upstream else 0]}
        return units, records, requests, frames, protocol, {'u0': ('UP', 'UP'), 'u1': ('DOWN', 'DOWN')}, upstream

    def test_panel_keeps_all_three_runs_and_factorial_family(self) -> None:
        result, accounts, _, tensors = repeat_panel('factorial', *self.panel())
        self.assertEqual(result['n_decisions'], 30)
        self.assertEqual(result['n_unique_successful_requests'], 30)
        self.assertEqual(result['summaries']['AS']['balanced_accuracy']['mean'], 2/3)
        self.assertAlmostEqual(result['summaries']['AS']['balanced_accuracy']['sd'], np.std([1, 0, 1], ddof=1))
        self.assertEqual(result['statistics']['BA_family']['n_contrasts'], 7)
        self.assertGreater(result['statistics']['BA_family']['n_joint_undefined_draws'], 0)
        self.assertEqual(len(accounts), 30)
        self.assertEqual(tensors['factorial_counts_AS'].shape, (3, 2, 4))

    def test_repeat_copy_prompt_change_missing_or_parent_change_are_rejected(self) -> None:
        for mutation in ('copy', 'prompt', 'missing', 'parent'):
            with self.subTest(mutation=mutation):
                args = list(self.panel()); records, requests = args[1:3]
                if mutation == 'copy': records[1]['request_ids'] = records[0]['request_ids'][:]
                elif mutation == 'prompt': requests[records[1]['request_ids'][0]]['messages'] = ['changed']
                elif mutation == 'missing': records.pop()
                else: records[0]['parent']['upstream_hash'] = 'different'
                with self.assertRaises(ValueError): repeat_panel('factorial', *args)

    def test_upstream_panel_changes_prompt_between_realizations_only(self) -> None:
        result, _, _, _ = repeat_panel('upstream', *self.panel(True))
        self.assertEqual(result['n_decisions'], 12)
        self.assertEqual(result['n_executions'], 3)
        self.assertEqual(len(result['statistics']['contrasts']), 1)

    def test_output_cannot_write_paper_queue_or_overwrite_release(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for target in ('paper/generated', 'outputs/revision', 'outputs/revision/revision_minimal_v1', '../escape'):
                with self.assertRaises(ValueError): output_path(root, Path(target))
            output = output_path(root, Path('outputs/revision/test_release')); output.mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, 'ghi đè'): build_release(root, output)

    def test_incomplete_queue_cannot_create_analysis_directory(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); output = root / 'outputs/revision/new_release'
            with patch('core.revision_minimal_analysis.verify_manifest', return_value={}), \
                 patch('core.revision_minimal_analysis.status', return_value={'complete': 374, 'missing': 1}):
                with self.assertRaises(ValueError): build_release(root, output)
            self.assertFalse(output.exists())

    def test_historical_source_requires_matching_archive_not_current_code(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root / 'core/revision72_analysis.py'
            source.parent.mkdir(); source.write_bytes(b'old-source'); old_hash = sha(source)
            source.write_bytes(b'current-source')
            receipt = {'sources': [{'path': 'core/revision72_analysis.py', 'sha256': old_hash}], 'outputs': []}
            write_json(root / BANK / 'numeric/manifest.json', receipt, True)
            archive = root / 'outputs/revision/r1_72h_run_v2/runtime_history/original_sources.zip'
            archive.parent.mkdir(parents=True)
            with zipfile.ZipFile(archive, 'w') as handle: handle.writestr('core/revision72_analysis.py', b'old-source')
            paths, evidence = numeric_closure(root)
            self.assertIn(archive, paths); self.assertNotIn(source, paths)
            self.assertEqual(evidence[0]['sha256'], old_hash)
            with zipfile.ZipFile(archive, 'w') as handle: handle.writestr('core/revision72_analysis.py', b'wrong-source')
            with self.assertRaises(ValueError): numeric_closure(root)

    def test_check_detects_source_output_tamper_and_extra_file(self) -> None:
        with tempfile.TemporaryDirectory() as folder, patch('core.revision_minimal_analysis.runtime', return_value={}):
            root = Path(folder); source = root / 'source.json'; source.write_text('{}', encoding='utf-8')
            output = output_path(root, Path('outputs/revision/test_release')); output.mkdir(parents=True)
            value = output / 'summary.json'; value.write_text('{}', encoding='utf-8')
            m = {'runtime': {}, 'sources': [{'path': 'source.json', 'sha256': sha(source)}],
                 'outputs': [{'path': 'summary.json', 'sha256': sha(value)}]}
            write_json(output / 'manifest.json', {**m, 'sha256': digest(m)}, True)
            self.assertEqual(check_release(root, output), 2)
            for target in (source, value):
                target.write_text('{"tamper":1}', encoding='utf-8')
                with self.assertRaises(ValueError): check_release(root, output)
                target.write_text('{}', encoding='utf-8')
            (output / 'extra').write_text('x', encoding='utf-8')
            with self.assertRaises(ValueError): check_release(root, output)

    def test_offline_guard_blocks_network_and_refit(self) -> None:
        with offline_guard():
            with self.assertRaises(AssertionError): socket.create_connection(('example.invalid', 443))
            from core import revision_baselines
            with self.assertRaises(AssertionError): revision_baselines.logistic_predictions()


if __name__ == '__main__':
    unittest.main()
