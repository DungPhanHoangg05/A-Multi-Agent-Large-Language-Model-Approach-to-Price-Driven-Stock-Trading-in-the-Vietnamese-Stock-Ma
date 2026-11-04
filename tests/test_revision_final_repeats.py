"""Kiểm T26 không chọn run, trộn panels hoặc nhầm interaction với best-single gap."""

from copy import deepcopy
from pathlib import Path
import json
import unittest

from scripts.export_revision_final_repeats import best_single_diagnostic, panel_tables, validate_panel_summary


def panels() -> dict:
    """Đọc frozen fixtures thật, không gọi inference hoặc sửa expected metrics."""
    base=Path('outputs/revision/revision_minimal_final_v1')
    return {n:json.loads((base/(n+'_panel.json')).read_bytes()) for n in ('upstream','factorial')}


class FinalRepeatTests(unittest.TestCase):
    """Các ràng buộc có thể làm sai estimand hoặc sample size."""
    def test_missing_duplicate_or_wrong_panel_support_is_rejected(self) -> None:
        source=panels()['upstream']
        for mode in ('missing','duplicate','units'):
            changed=deepcopy(source)
            if mode=='missing': changed['by_execution'].pop()
            elif mode=='duplicate': changed['by_execution'].append(changed['by_execution'][0])
            else: changed['n_units_per_execution']=27
            with self.subTest(mode=mode),self.assertRaises(ValueError): validate_panel_summary(changed,('B','AS'))

    def test_selected_best_run_cannot_replace_three_run_summary(self) -> None:
        source=panels()['upstream']; source['summaries']['AS']['balanced_accuracy']['mean']=1.
        with self.assertRaises(ValueError): validate_panel_summary(source,('B','AS'))

    def test_best_single_gap_and_interaction_are_different_estimands(self) -> None:
        values={'B':.5,'A':.6,'S':.6,'AS':.7}
        result=best_single_diagnostic([{'variant':v,'execution':i,'balanced_accuracy':x} for i in range(3) for v,x in values.items()])
        self.assertAlmostEqual(result['gap_of_means'],.1)
        self.assertAlmostEqual(result['interaction_summary']['mean'],0.)
        self.assertEqual(result['gap_summary']['n_planned'],3)

    def test_tables_preserve_executions_support_and_conditional_draw_denominators(self) -> None:
        summaries,executions,per_class,disagreements,intervals,contrasts=panel_tables(panels())
        self.assertEqual((len(summaries),len(executions),len(per_class),len(disagreements),len(intervals),len(contrasts)),(42,21,42,63,42,48))
        self.assertTrue(all(r['n_valid']==9 and r['support_up']==2 and r['support_down']==7 for r in executions))
        ba=[r for r in contrasts if r['metric']=='balanced_accuracy']
        self.assertTrue(all((r['n_executions_planned'],r['n_executions_defined'])==(3,3) for r in ba))
        self.assertTrue(all((r['n_draws_defined'],r['n_draws_undefined'],r['n_resamples'])==(6986,3014,10000) for r in ba))
        self.assertTrue(all(r['descriptive_family_low'] is None for r in ba if r['panel']=='upstream'))
        self.assertEqual({r['contrast'] for r in ba if r['panel']=='factorial'}, {'AS-B','A-B','AS-S','S-B','AS-A','AS-P','interaction'})

    def test_panels_are_not_pooled_even_with_same_unit_count(self) -> None:
        data=panels(); self.assertEqual(data['upstream']['n_units_per_execution'],data['factorial']['n_units_per_execution'])
        self.assertNotEqual(data['upstream']['n_dates'],data['factorial']['n_dates'])
        self.assertNotEqual(data['upstream']['n_symbols'],data['factorial']['n_symbols'])
        self.assertEqual(len(panel_tables(data)[1]),21)


if __name__=='__main__': unittest.main()
