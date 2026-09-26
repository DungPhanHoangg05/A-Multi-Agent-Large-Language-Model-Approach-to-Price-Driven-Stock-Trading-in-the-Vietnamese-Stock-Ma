"""Kiểm tra ánh xạ bốn trạng thái và fallback có tiêu chí xác định."""

from copy import deepcopy
import unittest

import numpy as np

from core.regime_detector import REGIME_NAMES, _fallback_regime, _regime_calibration


class RegimeMappingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.meta = {
            "state_feature_means": [[0, .01, .1, .1, .2], [0, .02, -.1, -.1, -.2],
                                    [0, .04, 0, 0, .01], [0, .008, 0, 0, 0]],
            "state_occupancy": [.25] * 4, "em_converged": True,
            "ma200_train_std": .1, "trend_threshold": .05, "volatility_quantiles": [.01, .02],
        }

    def test_names_are_bijective_and_canonical(self) -> None:
        result = _regime_calibration(self.meta)
        self.assertEqual(result["latent_state_names"], list(REGIME_NAMES))
        self.assertEqual(result["classification_method"], "HMM")
        self.assertEqual(result["fallback_reasons"], [])

    def test_each_quality_failure_triggers_recorded_fallback(self) -> None:
        cases = []
        for key, value in (("em_converged", False), ("state_occupancy", [.01, .33, .33, .33]),
                           ("ma200_train_std", 1.0)):
            case = deepcopy(self.meta)
            case[key] = value
            cases.append(case)
        case = deepcopy(self.meta)
        case["state_feature_means"][2][1] = .008
        cases.append(case)
        case = deepcopy(self.meta)
        case["state_feature_means"][1][4] = .02
        cases.append(case)
        for case in cases:
            result = _regime_calibration(case)
            self.assertEqual(result["classification_method"], "MULTI_FACTOR")
            self.assertTrue(result["fallback_reasons"])

    def test_ties_are_stable_and_names_remain_unique(self) -> None:
        self.meta["state_feature_means"] = [[0] * 5 for _ in range(4)]
        result = _regime_calibration(self.meta)
        self.assertEqual(result["latent_state_names"], list(REGIME_NAMES))
        self.assertEqual(result, _regime_calibration(self.meta))

    def test_fallback_covers_four_regimes_and_flat_price(self) -> None:
        for feature, expected in (([0, .01, .1, .1, .1], "BULL"), ([0, .01, -.1, -.1, -.1], "BEAR"),
                                  ([0, .03, 0, 0, 0], "CHOPPY"), ([0, .005, 0, 0, 0], "CONSOLIDATION")):
            self.assertEqual(_fallback_regime(np.array(feature), self.meta), expected)
        self.meta["volatility_quantiles"] = [0, 0]
        self.assertEqual(_fallback_regime(np.zeros(5), self.meta), "CONSOLIDATION")
