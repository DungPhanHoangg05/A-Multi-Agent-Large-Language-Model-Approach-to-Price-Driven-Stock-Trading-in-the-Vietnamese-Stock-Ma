"""Kiểm khóa spec và lineage metadata v4; không train hoặc mở nhãn thị trường."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from core.mt_bicl_v4_protocol import (BRANCHES, LOCK, PROTOCOL, PROTOCOL_SHA256, canonical,
    checksum, freeze, read, safe_path, source_binding, validate_protocol, verify, verify_inputs, verify_ledger)


def fixture() -> dict:
    """Episode giả chỉ kiểm ngày/ID, không đại diện dữ liệu thực hoặc X đầy đủ."""
    def row(identifier: str, as_of: str, entry: str, exit_date: str, task: str) -> dict:
        return {"episode_id": identifier, "symbol": "FPT", "task_id": task,
                "as_of_date": as_of, "entry_date": entry, "exit_date": exit_date,
                "feature_end_date": as_of, "scaler_fit_end": "2020-06-30",
                "regime_fit_end": "2019-12-31"}
    return {"query": row("q", "2020-07-10", "2020-07-13", "2020-07-15", "FPT:block1"),
            "prior": [{"task_id": "FPT:block0", "block_end_date": "2020-06-01", "observations": [
                row("d1", "2020-05-01", "2020-05-04", "2020-05-06", "FPT:block0"),
                row("d2", "2020-05-07", "2020-05-08", "2020-05-12", "FPT:block0")]}],
            "target": [row("c1", "2020-07-01", "2020-07-02", "2020-07-06", "FPT:block1")]}


class ProtocolTests(unittest.TestCase):
    """Đối soát spec, chống tự reseal và kiểm failure có ý nghĩa ở biên hợp đồng."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.data = PROTOCOL.read_bytes()
        cls.spec = validate_protocol(cls.data)

    def test_exact_spec_is_not_a_release(self) -> None:
        self.assertEqual(checksum(self.data), PROTOCOL_SHA256)
        self.assertTrue(all(v is False for v in self.spec["permissions"].values()))
        self.assertFalse(self.spec["confirmation"]["allowed"])
        self.assertEqual(self.spec["next_stage"], "W11_18_OFFLINE_DATA_PREPARATION_SEPARATE_TASK")

    def test_changed_semantics_or_whitespace_cannot_self_reseal(self) -> None:
        for path, value in [(('operation', 'hour_cap'), 18),
                            (('operation', 'calendar_deadline'), '2026-11-05'),
                            (('permissions', 'training_allowed'), True),
                            (('development', 'G'), 59)]:
            changed = deepcopy(self.spec)
            changed[path[0]][path[1]] = value
            with self.subTest(path=path), self.assertRaises(ValueError):
                validate_protocol(canonical(changed))
        with self.assertRaises(ValueError):
            validate_protocol(self.data + b' ')

    def test_json_rejects_duplicates_nonfinite_and_foreign_types(self) -> None:
        for data in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b'[]'):
            with self.subTest(data=data), self.assertRaises(ValueError):
                read(data)
        with self.assertRaises(ValueError):
            canonical({"x": (1, 2)})

    def test_paths_reject_absolute_traversal_and_drive_prefix(self) -> None:
        for name in ('../a', '/a', 'C:/a', 'a\\b', 'a//b', './a'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                safe_path(Path('.'), name)

    def test_ledger_accepts_append_preserves_old_rows(self) -> None:
        rows = [{"id": "old", "status": "unknown", "reserved_tokens": 100}]
        binding = {"count": 1, "requests_prefix_sha256": checksum(canonical(rows))}
        verify_ledger({"requests": rows + [{"id": "new", "status": "200"}]}, binding)
        for changed in ([], [{"id": "old", "status": "200", "reserved_tokens": 100}],
                        rows + [{"id": "old", "status": "200"}]):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                verify_ledger({"requests": changed}, binding)

    def test_input_tamper_fails_before_reading_ledger_or_models(self) -> None:
        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root / PROTOCOL).parent.mkdir(parents=True)
            (root / PROTOCOL).write_bytes(self.data)
            name = next(iter(self.spec['parent_sha256']))
            (root / name).write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'Binding nguồn'):
                verify_inputs(root)

    def test_git_source_must_match_worktree_bytes(self) -> None:
        with TemporaryDirectory() as folder:
            root = Path(folder)
            name = 'core/mt_bicl_v4_protocol.py'
            (root / name).parent.mkdir(parents=True)
            (root / name).write_bytes(b'changed')
            with patch('core.mt_bicl_v4_protocol.git', return_value=b'original'):
                with self.assertRaisesRegex(ValueError, 'khác Git'):
                    source_binding(root, 'a' * 40)

    def test_finite_registry_never_selects_on_2023_or_outer(self) -> None:
        self.assertEqual([f['id'] for f in self.spec['folds']], ['2020', '2021', '2022'])
        self.assertEqual([f['fit_end'] for f in self.spec['folds']],
                         ['2019-12-31', '2020-12-31', '2020-12-31'])
        self.assertIn('INNER_2020H1_H2_ONLY', self.spec['selection']['final_config'])
        self.assertEqual(self.spec['learner']['seeds'], [42, 137, 271])
        self.assertEqual(len(self.spec['learner']['architectures']), 2)
        self.assertEqual(self.spec['learner']['synthetic_pretraining_weight'], 0)
        self.assertEqual(self.spec['learner']['teacher_distillation_weight'], 0)

    def test_matrix_account_rows_and_api_slots_are_distinct(self) -> None:
        d = self.spec['development']
        self.assertEqual(d['matrix'], list(BRANCHES))
        self.assertEqual((d['primary_action_rows'], d['repeat_action_rows'], d['total_action_rows']),
                         (600, 396, 996))
        self.assertEqual((d['primary_llm_slots'], d['repeat_llm_slots'], d['total_nominal_llm_slots']),
                         (180, 144, 324))
        self.assertTrue(d['no_vote'])
        self.assertIn('NEW_V4_RESPONSE', d['original'])

    def test_economics_policy_and_support_do_not_repeat_v3_veto(self) -> None:
        e = self.spec['economics']
        self.assertEqual((e['entry'], e['exit']), ('Open(t+1)', 'Close(t+3)'))
        self.assertEqual((e['fee_each_side'], e['slippage_each_side']), (.0025, .001))
        self.assertFalse(e['second_cost_deduction'])
        self.assertIn('FRACTIONAL', e['shares'])
        self.assertIsNone(self.spec['context']['minimum_sign_counts'])
        self.assertFalse(self.spec['context']['hard_sign_bucket_filter'])
        self.assertFalse(self.spec['calibration_policy']['h_is_extra_fee'])
        self.assertIn('SAME_CALIBRATED_MIXTURE', self.spec['calibration_policy']['mean'])

    def test_gate_failure_and_nomination_do_not_promote_ablation(self) -> None:
        self.assertIn('NO_W11_20', self.spec['gates']['W11_19']['no_signal'])
        self.assertIn('No_target', self.spec['gates']['W11_21']['full_CRPS_vs'])
        n = self.spec['development']['nomination']
        self.assertEqual(n['candidate_only'], 'Full_conditional_MT')
        self.assertEqual((n['positive_symbols_min'], n['mean_delta_MDD_max_pp'], n['max_delta_MDD_max_pp']), (3, 2, 5))
        self.assertFalse(n['substitution_allowed'])
        self.assertFalse(n['repeat_vote'])
        self.assertNotIn('D_Full_Fact_Anchor_strict_min', n)

    def test_confirmation_remains_unreleased_with_eight_secondary(self) -> None:
        c = self.spec['confirmation']
        self.assertIsNone(c['sample_size'])
        self.assertIsNone(c['block_length'])
        self.assertEqual(set(c['secondary']), set(BRANCHES) - {'Original', 'Full_conditional_MT'})
        self.assertEqual(c['secondary_ci'], 1 - .05 / 8)
        self.assertEqual(c['independence'], 'UNPROVEN_NOT_RELEASED')

    def test_freeze_is_idempotent_and_replay_never_rewrites_receipt(self) -> None:
        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root / LOCK).parent.mkdir(parents=True)
            with patch('core.mt_bicl_v4_protocol.verify_inputs', return_value=self.spec), \
                 patch('core.mt_bicl_v4_protocol.git', return_value=b'commit\n'), \
                 patch('core.mt_bicl_v4_protocol.source_binding', return_value={'source': 'pinned'}):
                freeze(root)
                original = (root / LOCK).read_bytes()
                freeze(root)
                self.assertEqual(verify(root)['status'], 'SPEC_LOCK_PASS')
                self.assertEqual((root / LOCK).read_bytes(), original)

    def test_rehashed_receipt_cannot_grant_permission_or_rebind_source(self) -> None:
        for field in ('permissions', 'source_sha256', 'source_commit', 'ledger_baseline'):
            with self.subTest(field=field), TemporaryDirectory() as folder:
                root = Path(folder)
                (root / LOCK).parent.mkdir(parents=True)
                with patch('core.mt_bicl_v4_protocol.verify_inputs', return_value=self.spec), \
                     patch('core.mt_bicl_v4_protocol.git', return_value=b'commit\n'), \
                     patch('core.mt_bicl_v4_protocol.source_binding', return_value={'source': 'pinned'}):
                    freeze(root)
                    receipt = read((root / LOCK).read_bytes())
                    receipt['payload'][field] = 'forged'
                    receipt['sha256'] = checksum(canonical(receipt['payload']))
                    (root / LOCK).write_bytes(canonical(receipt))
                    with self.assertRaises(ValueError):
                        verify(root)

    def test_forward_calibration_and_numeric_control_are_explicit(self) -> None:
        p = self.spec['calibration_policy']
        self.assertIn('INNER_H2_MAP_FIT_H1_OOF_ONLY', p['forward_crossfit'])
        self.assertIn('NO_A0_HYSTERESIS', p['numerical_MT_action'])
        self.assertIn('FULL_SELECTED_h_SHARED', p['branch_matching'])


if __name__ == '__main__':
    unittest.main()
