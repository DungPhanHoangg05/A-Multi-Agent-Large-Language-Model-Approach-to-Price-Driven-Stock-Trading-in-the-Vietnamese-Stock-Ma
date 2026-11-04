"""Kiểm wiring T25: mask, cohort, fixed-date HAC và không classifier fit/API."""

from pathlib import Path
import json
import socket
import unittest

import numpy as np

from scripts.analyze_revision_final_dependence import analysis_guard, cohort, date_hac
from core.revision_dependent_statistics import circular_weights, score_samples


def rows() -> list[dict]:
    """Dùng support frozen T04, không sinh predictions thay thế."""
    return json.loads(Path('outputs/revision/revision_minimal_final_v1/main_predictions.json').read_bytes())


class FinalDependenceTests(unittest.TestCase):
    """Kiểm ước lượng theo fixed universe và toàn study block."""
    def test_cohort_rectangles_and_bhn_mask(self) -> None:
        data=rows()
        for name,n,blocks in [('all_102',102,6),('common_eight_96',96,6),('recent_nine_54',54,3)]:
            result=cohort(data,name); self.assertEqual(len(result['units']),n)
            self.assertEqual(result['counts'].shape,(9,blocks,4)); self.assertTrue(np.all(result['counts'].sum(axis=(1,2))==n))
        with self.assertRaises(ValueError): cohort(data+[data[0]],'all_102')
        with self.assertRaises(ValueError): cohort([r for r in data if not(r['variant']=='AS' and r['symbol']=='BHN')],'all_102')

    def test_hac_date_means_keep_equal_weights_and_row_order_invariance(self) -> None:
        data=rows(); dates,hac=date_hac(data,[0,1,2]); reversed_dates,reversed_hac=date_hac(list(reversed(data)),[0,1,2])
        self.assertEqual(dates,reversed_dates); self.assertEqual(hac,reversed_hac); self.assertEqual(len(dates),18); self.assertEqual(len(hac),6)
        for name,symbols in [('common_eight_96',8),('recent_nine_54',9)]:
            selected=[r for r in dates if r['cohort']==name]; reference=cohort(data,name)
            matrix=(reference['predictions'][0]==reference['truth']).astype(float)-(reference['predictions'][1]==reference['truth'])
            self.assertAlmostEqual(np.mean([r['accuracy_difference'] for r in selected]),float(matrix.mean()))
            self.assertTrue(all(r['n_symbols']==symbols and r['weight_per_symbol']==1/symbols for r in selected))

    def test_length_three_on_three_blocks_is_degenerate_not_more_replications(self) -> None:
        data=cohort(rows(),'recent_nine_54'); weights=circular_weights(3,3,100,20261103)
        np.testing.assert_array_equal(weights,np.ones((100,3),dtype=int))
        scores=score_samples(data['counts'],weights)['balanced_accuracy']; delta=scores[0]-scores[1]
        np.testing.assert_allclose(delta,delta[0],atol=1e-14)

    def test_guard_rejects_network_and_classifier_fit(self) -> None:
        from sklearn.linear_model import LogisticRegression
        with analysis_guard():
            with self.assertRaises(AssertionError): socket.create_connection(('example.invalid',443))
            with self.assertRaises(AssertionError): LogisticRegression().fit([[0.],[1.]],[0,1])


if __name__=='__main__': unittest.main()
