"""Giữ split/PIT, gộp ngày và chặn dữ liệu future hoặc nhãn giả ở consumer mới."""

from copy import deepcopy
from pathlib import Path
import json
import unittest

from core.historical_signals import digest
from core.improvement_bootstrap import bootstrap_report, specification


class ImprovementHoldoutLeakageTests(unittest.TestCase):
    def test_holdout_cycle_crossing_year_and_economic_label_mismatch_raise(self) -> None:
        fx = json.loads((Path(__file__).resolve().parents[1]/'docs/plan/week8/fixtures/improvement_bootstrap_v1.json').read_text(encoding='utf-8'))
        plan = {'split': 'holdout_2024', 'statistics': specification('A_tp_pool'), 'symbol_cutoffs': fx['symbol_cutoffs'],
            'selection_decision': {'primary_branch': 'A_tp_pool'}, 'code_sha256': {}, 'runtime': {}}
        report = {'report_version': 'improvement_holdout_report_v1', 'primary_status': 'COMPLETE',
            'matrix': plan['statistics']['matrix'], 'binding': {'plan_sha256': digest(plan), 'run_signature': 'fixture'},
            'bootstrap_cases': fx['cases'], 'primary_delta_return_pp': fx['expected']['point_estimates_pp']['A_tp_pool__original']}
        for change in ('year', 'cutoff', 'label', 'prices'):
            wrong = deepcopy(report); case = wrong['bootstrap_cases'][0]
            if change == 'year': case['exit_date'] = '2025-01-02'
            elif change == 'cutoff': case['entry_date'] = case['as_of_date']
            elif change == 'label': case['net_return_long'] = 0.
            else: case['exit_close'] *= 2
            with self.assertRaises(ValueError): bootstrap_report(plan, wrong, 'a'*64)


if __name__ == '__main__':
    unittest.main()
