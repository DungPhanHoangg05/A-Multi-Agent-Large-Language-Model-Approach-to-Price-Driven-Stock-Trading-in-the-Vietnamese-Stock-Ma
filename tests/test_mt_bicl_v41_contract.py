"""Kiểm cửa vào downstream không dùng nhầm gate/schema v4 và không tạo action ngoài panel."""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from core.mt_bicl_v41_contract import family_fit, feature_input, load_ready, original_fallback, original_for_policy, policy_prediction_key
from core.mt_bicl_v41_panel import ACCEPTANCE, plan_binding
from core.mt_bicl_v4_protocol import checksum
from core.mt_bicl_v4_dataset import encoded
from test_mt_bicl_v41_data import fixture


class ContractTests(unittest.TestCase):
    """Full/K0/pooled/reference cùng numeric/mask; Original chỉ ở policy."""

    def test_agent_and_original_poison_cannot_enter_numeric_input(self) -> None:
        _, query, scaler, _ = fixture()
        before = feature_input(query, scaler, 'BULL')
        query.update(agent={'trend':'BEARISH'}, original={'decision':'LONG'}, conflicts=[1,1])
        self.assertEqual(before, feature_input(query, scaler, 'BULL'))
        self.assertEqual(len(before['numeric']), 9)
        self.assertEqual(len(before['missing_mask']), 9)
        self.assertNotIn('agent', before)

    def test_complete_case_filters_fit_and_fits_own_scaler(self) -> None:
        rows, _, _, _ = fixture()
        rows[0]['features']['missing_mask'][1] = True
        full, scaler = family_fit(rows, rows[9]['exit_date'], 'Full_conditional_MT')
        case, cc_scaler = family_fit(rows, rows[9]['exit_date'], 'Complete_case_MT')
        self.assertEqual((len(full), len(case)), (10,9))
        self.assertNotEqual(scaler['fit_ids'], cc_scaler['fit_ids'])

    def test_off_missing_and_OOD_keep_exact_original(self) -> None:
        original = {'decision':'SHORT','content':'Giữ nguyên raw đã có.','extra':{'proof':[1,2]}}
        for enabled, eligible, ood in ((False,True,False),(True,False,False),(True,True,True)):
            result = original_fallback(original, enabled=enabled, numeric={'eligible':eligible,'ood':ood})
            self.assertEqual(result, original)
            self.assertIsNot(result, original)
        with self.assertRaises(ValueError): original_fallback({},enabled=False,numeric={'eligible':False,'ood':False})

    def test_same_2020_point_has_distinct_outer_and_inner_prediction_key(self) -> None:
        p = {'fold_roles': {'outer_2020':['FPT-2020-02-03'],'inner_2020H1':['FPT-2020-02-03']}}
        self.assertNotEqual(policy_prediction_key(p,'outer_2020','FPT-2020-02-03'), policy_prediction_key(p,'inner_2020H1','FPT-2020-02-03'))
        with self.assertRaises(ValueError): policy_prediction_key(p,'outer_2020','FPT-2020-02-04')
        data={'panel':p,'originals':{'FPT-2020-02-03':{'decision':'LONG'}}}
        self.assertEqual(original_for_policy(data,'outer_2020','FPT-2020-02-03'),{'decision':'LONG'})
        with self.assertRaises(ValueError): original_for_policy(data,'outer_2020','FPT-2020-02-04')

    def test_no_acceptance_and_old_v4_receipt_cannot_open_next_task(self) -> None:
        with TemporaryDirectory() as folder, patch('core.mt_bicl_v41_contract.verify_release',return_value={'point_ids':[]}):
            root=Path(folder)
            with self.assertRaisesRegex(ValueError,'chưa cold'): load_ready(root)
            path=root/ACCEPTANCE;path.parent.mkdir(parents=True)
            path.write_bytes(encoded({'version':'conditional_v4_completed_dataset','status':'DATA_READY_PASS'}))
            with patch('core.mt_bicl_v41_contract.git',return_value=path.read_bytes()):
                with self.assertRaises(ValueError): load_ready(root)

    def test_plan_binding_uses_Git_blob_despite_CRLF_or_uncommitted_progress(self) -> None:
        with TemporaryDirectory() as folder:
            root=Path(folder);path=root/'docs/plan/week11/README.md'
            path.parent.mkdir(parents=True);path.write_bytes(b'new progress\r\n')
            blob=b'registered plan\n'
            with patch('core.mt_bicl_v41_panel.git',side_effect=[b'fixture\n',blob]):
                binding=plan_binding(root)
            self.assertEqual(binding['sha256'],checksum(blob))
            self.assertNotEqual(binding['sha256'],checksum(path.read_bytes()))


if __name__ == '__main__':
    unittest.main()
