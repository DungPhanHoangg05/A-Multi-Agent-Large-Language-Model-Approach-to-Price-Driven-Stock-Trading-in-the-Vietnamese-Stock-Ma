"""Kiểm hợp đồng xuất baseline: fail-closed support, class undefined và hold."""

from copy import deepcopy
import unittest

from scripts.export_revision_final_baselines import csv_bytes, flatten, subset, validate_panel
from core.revision_clean_metrics import classification


class FinalBaselineTests(unittest.TestCase):
    """Các lỗi support/định nghĩa có thể làm đổi kết luận bảng."""
    def test_hold_or_missing_pair_is_not_classifier_support(self) -> None:
        from pathlib import Path
        import json
        rows=json.loads(Path('outputs/revision/revision_minimal_final_v1/main_predictions.json').read_bytes())
        validate_panel(rows)
        for mutated in (rows[:-1],rows+[rows[0]],deepcopy(rows)):
            if len(mutated)==len(rows): mutated[0]['variant']='continuous_hold_price_only'
            with self.assertRaises(ValueError): validate_panel(mutated)

    def test_pair_metadata_mismatch_is_rejected(self) -> None:
        from pathlib import Path
        import json
        rows=json.loads(Path('outputs/revision/revision_minimal_final_v1/main_predictions.json').read_bytes()); rows[0]['label_net']='UP' if rows[0]['label_net']=='DOWN' else 'DOWN'
        with self.assertRaises(ValueError): validate_panel(rows)

    def test_cohorts_do_not_backfill_bhn_or_pick_outcomes(self) -> None:
        rows=[{'symbol':'BHN','fold':'b_old'},{'symbol':'FPT','fold':'b_old'},{'symbol':'BHN','fold':'f_recent'}]
        self.assertEqual(subset(rows,'common_eight_96'),[rows[1]])
        self.assertEqual(subset(rows,'recent_nine_54'),[rows[2]])
        with self.assertRaises(ValueError): subset(rows,'best_results')

    def test_imbalance_accuracy_and_undefined_mcc_remain_explicit(self) -> None:
        result=flatten(classification(['UP']*25+['DOWN']*77,['SHORT']*102))
        self.assertEqual(result['support_up'],25); self.assertEqual(result['support_down'],77)
        self.assertEqual(result['accuracy'],77/102); self.assertEqual(result['balanced_accuracy'],.5); self.assertIsNone(result['mcc'])
        self.assertIn(b'NA',csv_bytes([result]))


if __name__=='__main__': unittest.main()
