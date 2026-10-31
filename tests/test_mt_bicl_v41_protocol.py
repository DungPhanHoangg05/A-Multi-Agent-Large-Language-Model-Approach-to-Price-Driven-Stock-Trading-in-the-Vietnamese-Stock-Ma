"""Kiểm amendment không âm thầm sửa economics, model, cutoff hoặc family."""

from copy import deepcopy
from pathlib import Path
import unittest

from core.mt_bicl_v4_protocol import read
from core.mt_bicl_v41_protocol import expected_spec, validate


class AmendmentTests(unittest.TestCase):
    """Spec mới tách learner numeric khỏi Original ở policy và giữ đối chứng."""

    def setUp(self) -> None:
        self.parent = read(Path('docs/plan/week11/protocol_v4.json').read_bytes())
        self.spec = expected_spec(self.parent)

    def test_only_registered_revision_is_accepted(self) -> None:
        self.assertEqual(validate(self.spec, self.parent), self.spec)
        for key in ('economics', 'folds', 'learner', 'reference', 'baselines'):
            self.assertEqual(self.spec[key], self.parent[key])
        self.assertFalse(any(self.spec['permissions'].values()))

    def test_no_agent_input_and_no_duplicate_ablation(self) -> None:
        self.assertEqual(self.spec['features']['agent_categories'], {})
        self.assertEqual(self.spec['features']['core_indices'], [0, 7, 8])
        matrix = self.spec['development']['matrix']
        self.assertIn('Complete_case_MT', matrix)
        self.assertNotIn('No_agent_features', matrix)
        self.assertEqual(len(matrix), 10)
        self.assertEqual(self.spec['development']['total_action_rows'], 996)
        self.assertEqual(self.spec['development']['total_nominal_llm_slots'], 324)

    def test_scientific_changes_cannot_be_resealed_as_same_spec(self) -> None:
        for section, key, value in [('permissions', 'training_allowed', True),
                                    ('features', 'core_indices', [0]), ('panel', 'points', 64),
                                    ('operation', 'hour_cap', 18)]:
            bad = deepcopy(self.spec)
            bad[section][key] = value
            with self.assertRaises(ValueError): validate(bad, self.parent)

    def test_dense_forecast_sparse_policy_and_fold_specific_predictions(self) -> None:
        self.assertIn('FULL_GRID', self.spec['metrics']['forecast_population'])
        self.assertIn('PANEL256', self.spec['metrics']['policy_population'])
        self.assertEqual(self.spec['calibration_policy']['artifact_key'], 'FOLD_ID_PLUS_POINT_ID_NOT_POINT_ID_ALONE')
        self.assertEqual(self.spec['confirmation']['secondary_ci'], self.parent['confirmation']['secondary_ci'])
        self.assertEqual(len(self.spec['confirmation']['secondary']), 8)


if __name__ == '__main__':
    unittest.main()
