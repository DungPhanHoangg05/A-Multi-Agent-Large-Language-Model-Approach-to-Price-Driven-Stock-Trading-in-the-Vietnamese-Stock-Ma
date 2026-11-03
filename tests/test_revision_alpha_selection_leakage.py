"""Kiểm diagnostic T11 chỉ đọc prefix tới cutoff và không che giới hạn causal T10."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.revision_alpha_contract import rowwise_diagnostics
from core.revision_alpha_selection import analyse_cutoff, cutoff_history
from core.revision_baselines import load_prices
from core.revision_common_study import read_json
from core.revision_sentiment_inventory import BANK

ROOT = Path(__file__).resolve().parents[1]


class AlphaSelectionLeakageTests(unittest.TestCase):
    """Poison ngoài cutoff không đổi bất kỳ candidate/rank/value/turnover nào."""

    def test_all_candidate_diagnostics_ignore_future_price_volume_and_date_poison(self) -> None:
        bank = read_json(ROOT / BANK / "manifest.json"); protocol = bank["protocol"]
        frames, _ = load_prices(ROOT / protocol["price_snapshot"], protocol["price_quality_policy"])
        frame = frames["FPT"]; index = 699
        unit = {"id": "FPT_fixture", "symbol": "FPT", "fold": "fixture", "decision": index, "date": str(frame["date"].iloc[index])}
        original_copy = frame.copy(deep=True)
        changed = frame.copy(); changed.loc[index + 1:, ["Open", "High", "Low", "Close", "Volume"]] = np.inf
        changed.loc[index + 1:, "date"] = "not a valid date"
        with patch("core.alpha_compare.load_data", side_effect=AssertionError("Cấm realtime")):
            first, second = analyse_cutoff(frame, unit, protocol), analyse_cutoff(changed, unit, protocol)
        self.assertEqual(first, second)
        pd.testing.assert_frame_equal(frame, original_copy)
        self.assertEqual(first["history"]["rows"], 600)
        self.assertEqual(first["history"]["last_date"], unit["date"])

    def test_cutoff_date_or_missing_history_is_rejected_before_evaluation(self) -> None:
        frame = pd.DataFrame({"date": pd.bdate_range("2020-01-01", periods=700).strftime("%Y-%m-%d")})
        unit = {"decision": 699, "date": "2099-01-01"}
        with self.assertRaisesRegex(ValueError, "date cutoff"): cutoff_history(frame, unit)
        short = deepcopy(unit); short["decision"] = 598
        with self.assertRaisesRegex(ValueError, "prefix 600"): cutoff_history(frame, short)

    def test_native_rowwise_limit_is_not_relabelled_as_zero_leakage(self) -> None:
        self.assertEqual(rowwise_diagnostics()["native_rowwise_causal_gate"], "FAIL")


if __name__ == "__main__":
    unittest.main()
