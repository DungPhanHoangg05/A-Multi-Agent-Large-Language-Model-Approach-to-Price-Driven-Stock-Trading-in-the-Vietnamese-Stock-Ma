"""Kiểm numeric control fit/predict và feature adapters không dùng validation/test tương lai."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import alpha_compare as alpha
from core.revision_alpha_contract import synthetic_frame
from core.revision_common_study import read_json
from core.revision_numeric_design import PROTOCOL, causal_factors, fit_on_scope, predict_vote, random_set
from test_revision_numeric_design import synthetic_scope

ROOT = Path(__file__).resolve().parents[1]


class NumericDesignLeakageTests(unittest.TestCase):
    """Tests chỉ fit dữ liệu giả; T12 không chạy controls trên giá thực."""

    def setUp(self) -> None:
        self.protocol = read_json(ROOT / PROTOCOL)

    def test_eligibility_imputation_scaling_orientation_and_ranking_ignore_validation_test(self) -> None:
        frame = synthetic_frame(720); scope = synthetic_scope()
        rng = np.random.default_rng(11)
        features = pd.DataFrame(rng.normal(size=(720, 85)), columns=sorted(alpha.ALPHA_REGISTRY))
        original = fit_on_scope(features, frame, scope, self.protocol)
        changed = features.copy(); changed.iloc[665:] = np.inf
        prices = frame.copy(); prices.loc[665:, ["Open", "High", "Low", "Close"]] = np.inf
        poisoned = fit_on_scope(changed, prices, scope, self.protocol)
        self.assertEqual(original, poisoned)
        for seed in self.protocol["strategies"]["random_eligible5"]["seeds"]:
            self.assertEqual(random_set(original["eligible_ids"], scope["scope_id"], seed, self.protocol),
                             random_set(poisoned["eligible_ids"], scope["scope_id"], seed, self.protocol))

    def test_prediction_of_one_row_does_not_fit_other_prediction_rows(self) -> None:
        frame = synthetic_frame(720); scope = synthetic_scope(); rng = np.random.default_rng(13)
        features = pd.DataFrame(rng.normal(size=(720, 85)), columns=sorted(alpha.ALPHA_REGISTRY))
        fitted = fit_on_scope(features, frame, scope, self.protocol); frozen = deepcopy(fitted)
        test = features.iloc[scope["test_indices"]].copy()
        before = predict_vote(test, fitted, fitted["dynamic_ids"], self.protocol)
        test.iloc[1] = 1e100
        after = predict_vote(test, fitted, fitted["dynamic_ids"], self.protocol)
        self.assertEqual(before[0], after[0])
        self.assertEqual(fitted, frozen)

    def test_causal_features_after_warmup_ignore_future_and_match_prefix(self) -> None:
        frame = synthetic_frame(720)
        original = causal_factors(frame, 699, self.protocol)
        changed = frame.copy(); changed.loc[650:, ["Open", "High", "Low", "Close"]] *= 20; changed.loc[650:, "Volume"] *= 1000
        poisoned = causal_factors(changed, 699, self.protocol)
        prefix = causal_factors(frame, 649, self.protocol)
        self.assertTrue(original.iloc[:599].isna().all().all())
        np.testing.assert_allclose(original.iloc[599:650], poisoned.iloc[599:650], equal_nan=True)
        np.testing.assert_allclose(original.iloc[649], prefix.iloc[649], equal_nan=True)
        self.assertEqual(original.shape[1], 85)

    def test_missing_raw_or_late_volume_proxy_switch_is_rejected(self) -> None:
        frame = synthetic_frame(720); frame.loc[:599, "Volume"] = 0.
        with self.assertRaisesRegex(ValueError, "proxy switch"): causal_factors(frame, 699, self.protocol)
        frame = synthetic_frame(720); frame.loc[620, "Volume"] = np.nan
        with self.assertRaisesRegex(ValueError, "Volume"): causal_factors(frame, 699, self.protocol)


if __name__ == "__main__":
    unittest.main()
