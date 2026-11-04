"""Kiểm fit train/predict validation-test T13 không đổi khi poison phần tương lai."""

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
from core.revision_numeric_controls import evaluate_scope
from core.revision_numeric_design import PROTOCOL
from test_revision_numeric_design import synthetic_scope
from test_revision_numeric_statistics import family

ROOT = Path(__file__).resolve().parents[1]


class NumericControlsLeakageTests(unittest.TestCase):
    """Không dùng LLM hoặc labels thật; assertions kiểm cả 20 random seeds/no-flip."""

    def test_scope_fitted_state_sets_and_no_flip_are_independent_of_validation_test_prices(self) -> None:
        protocol = read_json(ROOT / PROTOCOL); frame = synthetic_frame(720); scope = synthetic_scope()
        features = pd.DataFrame(np.random.default_rng(17).normal(size=(720, 85)), columns=sorted(alpha.ALPHA_REGISTRY))
        design = {"protocol": protocol, "strategy_ids": family()[0]}; run = {"sha256": "run"}; receipt = {"sha256": "cache"}
        a = evaluate_scope(features, frame, scope, design, run, receipt)
        changed = features.copy(); changed.iloc[665:] *= -1000
        prices = frame.copy(); prices.loc[665:, ["Open", "High", "Low", "Close"]] *= 10
        b = evaluate_scope(changed, prices, scope, design, run, receipt)
        self.assertEqual(a["fitted"], b["fitted"])
        self.assertEqual(a["strategies"], b["strategies"])
        self.assertEqual(a["strategies"]["dynamic_train_top5"]["ids"], a["strategies"]["dynamic_train_top5_no_flip"]["ids"])
        self.assertEqual(len({r["fit_digest"] for r in a["strategies"].values()}), 1)


if __name__ == "__main__":
    unittest.main()
