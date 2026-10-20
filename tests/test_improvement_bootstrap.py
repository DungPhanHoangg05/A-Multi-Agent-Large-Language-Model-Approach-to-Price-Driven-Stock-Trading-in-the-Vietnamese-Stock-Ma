"""Oracle độc lập, engine tài khoản và biên bootstrap/CI đã đăng ký."""

from copy import deepcopy
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

import numpy as np
import pandas as pd

from core.backtest_engine import compute_account_metrics
from core.historical_signals import digest
from core.improvement_bootstrap import _inputs, _interval, bootstrap_report, circular_indices, read_bootstrap, rebuild, specification
from core.improvement_protocol import SYMBOL_ORDER
from core.research_input_lock import _write_once


class ImprovementBootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        path = Path(__file__).resolve().parents[1]/'docs/plan/week8/fixtures/improvement_bootstrap_v1.json'
        self.fx = json.loads(path.read_text(encoding='utf-8'))
        self.plan = {'split': 'fixture', 'statistics': specification('A_tp_pool'),
            'symbol_cutoffs': self.fx['symbol_cutoffs'], 'selection_decision': {'primary_branch': 'A_tp_pool'},
            'code_sha256': {}, 'runtime': {}}
        self.report = {'report_version': 'improvement_holdout_report_v1', 'primary_status': 'COMPLETE',
            'matrix': self.plan['statistics']['matrix'], 'binding': {'plan_sha256': digest(self.plan), 'run_signature': 'fixture'},
            'bootstrap_cases': self.fx['cases'],
            'primary_delta_return_pp': self.fx['expected']['point_estimates_pp']['A_tp_pool__original']}

    def test_golden_independent_products_rng_and_bonferroni_all_three_blocks(self) -> None:
        result = bootstrap_report(self.plan, self.report, 'f'*64)
        self.assertEqual(result['evidence_status'], 'FIXTURE_ONLY')
        self.assertEqual(result['status'], 'COMPLETE')
        for block, contrasts in self.fx['expected']['blocks'].items():
            actual = result['blocks'][block]
            self.assertEqual((actual['draws'], actual['valid_draws'], actual['invalid_draws']), (10000, 10000, 0))
            for key, expected in contrasts.items():
                item = actual['contrasts'][key]
                np.testing.assert_allclose(item['ci'], expected, rtol=1e-10, atol=1e-9)
                self.assertAlmostEqual(item['point_estimate_pp'], self.fx['expected']['point_estimates_pp'][key], places=9)
                self.assertAlmostEqual(item['confidence_level'], .95 if key.endswith('__original') else .9875)
            for symbol in SYMBOL_ORDER:
                self.assertEqual(actual['sample_counts'][symbol]['histogram'], {'3': 10000})
        self.assertEqual(result, bootstrap_report(self.plan, self.report, 'f'*64))

    def test_rebuild_matches_real_engine_with_fractional_shares_cash_and_synthetic_order(self) -> None:
        _, present, entry, exit_price, actions = _inputs(self.plan, self.fx['cases'])
        sample = [2, 0, 2]
        returns, counts = rebuild(np.array([sample]), present, entry, exit_price, actions)
        self.assertTrue((counts == 3).all())
        for s, symbol in enumerate(SYMBOL_ORDER):
            cases = sorted([c for c in self.fx['cases'] if c['symbol'] == symbol], key=lambda c: c['as_of_date'])
            for n, name in enumerate(self.plan['statistics']['matrix']):
                points = []
                for j, index in enumerate(sample):
                    case = cases[index]; start = pd.Timestamp('2000-01-01')+pd.Timedelta(days=4*j)
                    points.append(SimpleNamespace(test_id=j, entry_open=case['entry_open'], exit_close=case['exit_close'],
                        entry_time=str(start), exit_time=str(start+pd.Timedelta(days=2)),
                        pred_full=case['actions'][name], pred_no_alpha=case['actions'][name]))
                expected = compute_account_metrics(points)['full']
                self.assertAlmostEqual(returns[0, s, n], expected.total_return_pct, places=10)
                self.assertEqual(expected.final_shares, 0.)

    def test_clusters_keep_all_symbols_and_rng_exact_first_rows(self) -> None:
        indices = circular_indices(7, 4)
        starts = np.random.Generator(np.random.PCG64(20261016)).integers(0, 7, size=(3, 2))
        for j in range(3):
            expected = [(int(start)+k) % 7 for start in starts[j] for k in range(4)][:7]
            self.assertEqual(indices[j].tolist(), expected)
        self.assertEqual(indices.shape, (10000, 7))
        self.assertTrue(any(row != sorted(row) for row in indices[:10].tolist()))
        for bad in (0, True, 1., -1):
            with self.assertRaises(ValueError):
                circular_indices(bad, 4)
        with self.assertRaises(ValueError):
            circular_indices(7, 1)

    def test_missing_symbol_draws_not_replaced_and_threshold_boundary(self) -> None:
        cases = []
        cutoffs = {}
        for s, symbol in enumerate(SYMBOL_ORDER):
            originals = [c for c in self.fx['cases'] if c['symbol'] == symbol][:2]
            cutoffs[symbol] = []
            for j, case in enumerate(originals):
                day = f'2024-02-{1+4*(s*2+j):02d}' if s < 3 else f'2024-03-{1+4*j:02d}'
                start = pd.Timestamp(day); case = deepcopy(case)
                case.update(point_id=symbol+'-'+day, as_of_date=day,
                    entry_date=str((start+pd.Timedelta(days=1)).date()), exit_date=str((start+pd.Timedelta(days=3)).date()))
                cases.append(case); cutoffs[symbol].append(day)
        plan = {**self.plan, 'symbol_cutoffs': cutoffs}
        report = deepcopy(self.report); report['binding']['plan_sha256'] = digest(plan); report['bootstrap_cases'] = cases
        d = []
        for symbol in SYMBOL_ORDER:
            rows = [c for c in cases if c['symbol'] == symbol]
            returns = {n: (math.prod(1+c['net_return_long'] if c['actions'][n] == 'LONG' else 1 for c in rows)-1)*100
                       for n in ('A_tp_pool', 'original')}
            d.append(returns['A_tp_pool']-returns['original'])
        report['primary_delta_return_pp'] = sum(d)/4
        result = bootstrap_report(plan, report, 'f'*64)
        block = result['blocks']['4']
        self.assertEqual(block['draws'], 10000)
        self.assertGreater(block['invalid_reasons']['MISSING_SYMBOL'], 500)
        self.assertEqual(block['valid_draws']+block['invalid_draws'], 10000)
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertIsNone(block['contrasts']['A_tp_pool__original']['ci'])
        values = np.arange(10000, dtype=float); valid = np.arange(10000) < 9500
        interval = _interval(values, valid, .05)
        self.assertEqual(interval['status'], 'COMPLETE')
        np.testing.assert_allclose(interval['ci'], [237.475, 9261.525], atol=1e-10)
        valid[9499] = False
        self.assertEqual(_interval(values, valid, .05)['status'], 'BLOCKED')

    def test_sensitivity_missing_draws_do_not_replace_main_block_or_zero_effect(self) -> None:
        cases = []; cutoffs = {}
        for s, symbol in enumerate(SYMBOL_ORDER):
            case = deepcopy(next(c for c in self.fx['cases'] if c['symbol'] == symbol))
            day = f'2024-02-{1+5*s:02d}'; start = pd.Timestamp(day)
            case.update(point_id=symbol+'-'+day, as_of_date=day,
                entry_date=str((start+pd.Timedelta(days=1)).date()), exit_date=str((start+pd.Timedelta(days=3)).date()))
            cases.append(case); cutoffs[symbol] = [day]
        plan = {**self.plan, 'symbol_cutoffs': cutoffs}
        report = deepcopy(self.report); report['binding']['plan_sha256'] = digest(plan); report['bootstrap_cases'] = cases
        report['primary_delta_return_pp'] = sum(c['net_return_long']*100*((c['actions']['A_tp_pool'] == 'LONG')-
            (c['actions']['original'] == 'LONG')) for c in cases)/4
        result = bootstrap_report(plan, report, 'a'*64)
        self.assertEqual(result['status'], 'COMPLETE')
        self.assertEqual(result['blocks']['4']['valid_draws'], 10000)
        self.assertEqual(result['blocks']['2']['contrasts']['A_tp_pool__original']['status'], 'BLOCKED')
        interval = _interval(np.zeros(10000), np.ones(10000, dtype=bool), .05)
        self.assertEqual(interval['ci'], [0., 0.])
        self.assertEqual(interval['interpretation'], 'INCONCLUSIVE')

    def test_missing_primary_nonfinite_or_corrupt_cases_cannot_be_imputed(self) -> None:
        report = deepcopy(self.report); report['primary_status'] = 'INCOMPLETE'; report['bootstrap_cases'] = []
        self.assertEqual(bootstrap_report(self.plan, report, 'a'*64)['blocks'], {})
        for change in ('missing', 'duplicate', 'nan', 'label', 'action', 'matrix'):
            report = deepcopy(self.report); case = report['bootstrap_cases'][0]
            if change == 'missing': report['bootstrap_cases'].pop()
            elif change == 'duplicate': report['bootstrap_cases'][-1] = deepcopy(case)
            elif change == 'nan': case['entry_open'] = float('nan')
            elif change == 'label': case['net_return_long'] = 0.
            elif change == 'action': case['actions']['original'] = 'CASH'
            else: report['matrix'] = ['original']
            with self.assertRaises(ValueError):
                bootstrap_report(self.plan, report, 'a'*64)

    def test_dedup_c2_and_rehashed_ci_or_seed_cannot_replace_fixed_protocol(self) -> None:
        spec = specification('C2')
        self.assertEqual(spec['matrix'], ['original', 'bayesian', 'C2', 'C2_stats_only', 'C2_examples_only'])
        self.assertEqual(spec['secondary_count'], 3)
        expected = bootstrap_report(self.plan, self.report, 'a'*64)
        with TemporaryDirectory() as directory:
            path = Path(directory)/'bootstrap.json'; _write_once(path, expected)
            self.assertEqual(read_bootstrap(path, expected), expected)
            wrong = deepcopy(expected); wrong['blocks']['4']['contrasts']['A_tp_pool__original']['ci'] = [99., 100.]
            path.unlink(); _write_once(path, wrong)
            with self.assertRaises(ValueError): read_bootstrap(path, expected)
        wrong = deepcopy(self.plan); wrong['statistics']['seed'] = 1
        with self.assertRaises(ValueError): bootstrap_report(wrong, self.report, 'a'*64)


if __name__ == '__main__':
    unittest.main()
