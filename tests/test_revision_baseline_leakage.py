"""Kiểm thử PIT, preprocessing, baseline và ledger hằng phiên của R1."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.revision_baselines import (daily_ledger, factor_vote, load_prices, logistic_predictions,
    numerical_features, samples, sentiment_features, temporal_split, validate_prices)
from core.revision_audit import round_trip_net_return, sha256_file
from scripts.evaluate_revision_baselines import matched_schedule

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = json.loads((ROOT / "revision/r1_protocol.json").read_bytes())


def fixture(n: int = 700) -> pd.DataFrame:
    """Dữ liệu giả chỉ dùng unit test, không đưa vào báo cáo thực nghiệm."""
    t = np.arange(n, dtype=float)
    close = 100 + .02 * t + np.sin(t / 3)
    return pd.DataFrame({"date": pd.bdate_range("2023-01-02", periods=n).strftime("%Y-%m-%d"),
        "Open": close - .1, "High": close + .5, "Low": close - .5, "Close": close,
        "Volume": 1000 + t % 17 * 30})


class RevisionBaselineLeakageTests(unittest.TestCase):
    def test_future_price_and_volume_poison_does_not_change_cutoff_features(self):
        frame = fixture()
        original, price_cols, alpha_cols = numerical_features(frame, [])
        changed = frame.copy()
        changed.loc[401:, ["Open", "High", "Low", "Close"]] *= 20
        changed.loc[401:, "Volume"] *= 1000
        poisoned, _, _ = numerical_features(changed, [])
        np.testing.assert_allclose(original.iloc[350:401].to_numpy(), poisoned.iloc[350:401].to_numpy(), equal_nan=True)
        prefix, _, _ = numerical_features(frame.iloc[:401].copy(), [])
        np.testing.assert_allclose(original.iloc[400].to_numpy(), prefix.iloc[400].to_numpy(), equal_nan=True)
        self.assertEqual(len(alpha_cols), 85)
        self.assertGreater(len(price_cols), 5)

    def test_unknown_scorer_is_missing_not_neutral(self):
        article = {"date_parsed": "2026-01-01", "numeric_score": .5}
        output = sentiment_features(pd.Series(["2026-01-10"]), [article] * 4)
        self.assertTrue(np.isnan(output["sentiment_score"].iloc[0]))
        self.assertEqual(output["sentiment_missing"].iloc[0], 1)
        self.assertEqual(output["verified_article_count"].iloc[0], 0)

    def test_date_only_next_day_explicit_availability_and_90_day_window(self):
        articles = [{"date_parsed": "2026-01-02", "numeric_score": .5, "scorer": "visobert"}] * 3
        output = sentiment_features(pd.Series(["2026-01-02", "2026-01-03", "2026-05-01"]), articles)
        self.assertEqual(output["sentiment_missing"].tolist(), [1, 0, 1])
        delayed = [{**a, "available_at": "2026-01-10T12:00:00+07:00"} for a in articles]
        output = sentiment_features(pd.Series(["2026-01-09", "2026-01-10"]), delayed)
        self.assertEqual(output["sentiment_missing"].tolist(), [1, 0])

    def test_time_split_purges_all_label_spans_touching_next_split(self):
        frame = fixture(1200)
        protocol = dict(PROTOCOL)
        sample = samples(frame, protocol)
        train, val = temporal_split(sample, "2026-09-01", protocol)
        self.assertLess(sample.loc[train, "exit_date"].max(), sample.loc[val, "date"].min())
        self.assertLess(sample.loc[val, "exit_date"].max(), "2026-09-01")
        self.assertTrue((sample.loc[train, "date"] <= protocol["train_end"]).all())

    def test_imputer_scaler_and_selection_ignore_test_distribution(self):
        rng = np.random.default_rng(23)
        x = pd.DataFrame(rng.normal(size=(180, 3)))
        x.iloc[::5, 0] = np.nan
        y = (x[1].to_numpy() > 0).astype(int)
        _, model = logistic_predictions(x.iloc[:120], y[:120], x.iloc[120:150], y[120:150], x.iloc[150:], PROTOCOL)
        poisoned_test = x.iloc[150:].copy() * 1e8
        _, changed = logistic_predictions(x.iloc[:120], y[:120], x.iloc[120:150], y[120:150], poisoned_test, PROTOCOL)
        for key in ("C", "threshold", "refit_imputer_statistics", "refit_scaler_mean", "coefficients"):
            self.assertEqual(model[key], changed[key])

    def test_factor_orientation_has_no_test_labels_or_distribution_fit(self):
        x = pd.DataFrame({"a": [-2., -1., 1., 2.], "b": [0., 0., 0., 0.]})
        y = np.array([0, 0, 1, 1])
        pred, fitted = factor_vote(x, y, pd.DataFrame({"a": [-3., 3.], "b": [0., 0.]}))
        self.assertEqual(pred.tolist(), [0, 1])
        _, other = factor_vote(x, y, pd.DataFrame({"a": [3000.], "b": [float("nan")]}))
        self.assertEqual(fitted, other)

    def test_missing_or_tampered_snapshot_is_not_fetched_live(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "AAA.csv"
            fixture().to_csv(path, index=False)
            (root / "manifest.json").write_text(json.dumps({"symbols": [{"symbol": "AAA", "path": "AAA.csv", "sha256": "wrong", "n_rows": 700}]}))
            with self.assertRaises(ValueError):
                load_prices(root)

    def test_bad_ohlc_suffix_policy_is_explicit_raw_bytes_unchanged(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            frame = fixture()
            frame.loc[10, "Open"] = frame.loc[10, "Low"] - 1
            path = root / "AAA.csv"
            frame.to_csv(path, index=False)
            before = path.read_bytes()
            (root / "manifest.json").write_text(json.dumps({"symbols": [{"symbol": "AAA", "path": "AAA.csv", "sha256": sha256_file(path), "n_rows": len(frame)}]}))
            with self.assertRaises(ValueError): load_prices(root)
            views, manifest = load_prices(root, "valid_suffix_after_last_bad_ohlc")
            self.assertEqual(len(views["AAA"]), len(frame) - 11)
            self.assertEqual(manifest["analysis_quality_views"]["AAA"]["excluded_prefix_rows"], 11)
            self.assertEqual(before, path.read_bytes())

    def test_schedule_mismatches_are_recorded_without_rewriting_legacy(self):
        frame = fixture(50)
        legacy = {"test_points": [{"test_id": 1, "window_end": frame["date"].iloc[20],
            "entry_time": frame["date"].iloc[21], "exit_time": frame["date"].iloc[23],
            "entry_open": 200., "exit_close": 250., "actual_direction": "UP"}]}
        original = deepcopy(legacy)
        test, mismatch = matched_schedule(frame, legacy, PROTOCOL)
        self.assertEqual(len(mismatch), 1)
        self.assertIn("entry_open", mismatch[0]["fields"])
        self.assertEqual(legacy, original)
        self.assertEqual(test["entry"].iloc[0], 21)

    def test_duplicate_dates_and_impossible_ohlc_fail_closed(self):
        frame = fixture()
        frame.loc[1, "date"] = frame.loc[0, "date"]
        with self.assertRaises(ValueError): validate_prices(frame)
        frame = fixture()
        frame.loc[20, "Low"] = frame.loc[20, "High"] + 1
        with self.assertRaises(ValueError): validate_prices(frame)


class RevisionDailyLedgerTests(unittest.TestCase):
    def test_daily_drawdown_sees_intra_cycle_loss_cycle_end_misses(self):
        frame = pd.DataFrame({"date": ["2026-01-01", "2026-01-02", "2026-01-05"],
            "Open": [100, 80, 100], "Close": [100, 80, 110]})
        protocol = {**PROTOCOL, "fee_each_side": 0, "slippage_each_side": 0}
        result = daily_ledger(frame, [(0, 2, 1)], protocol)
        self.assertAlmostEqual(result["daily_close_drawdown_pct"], 20)
        self.assertAlmostEqual(result["net_return_pct"], 10)
        self.assertEqual(result["order_count"], 2)

    def test_round_trip_equivalence_fees_and_gap_cash(self):
        frame = fixture(10)
        result = daily_ledger(frame, [(0, 2, 1), (5, 7, 0)], PROTOCOL)
        expected = round_trip_net_return(float(frame["Open"].iloc[0]), float(frame["Close"].iloc[2]), .0025, .001) * 100
        self.assertAlmostEqual(result["net_return_pct"], expected)
        daily = result["daily"]
        self.assertEqual(daily[3]["equity_vnd"], daily[2]["equity_vnd"])
        self.assertEqual(daily[4]["held_during_session"], 0)
        self.assertEqual(result["order_count"], 2)
        self.assertAlmostEqual(sum(d["brokerage_fee_vnd"] for d in daily), result["brokerage_fee_vnd"])

    def test_continuous_hold_is_one_purchase_and_sale_across_gaps(self):
        frame = fixture(12)
        hold = daily_ledger(frame, [(0, 10, 1)], PROTOCOL)
        cycles = daily_ledger(frame, [(0, 2, 1), (5, 7, 1), (8, 10, 1)], PROTOCOL)
        self.assertEqual(hold["order_count"], 2)
        self.assertEqual(cycles["order_count"], 6)
        self.assertNotAlmostEqual(hold["net_return_pct"], cycles["net_return_pct"])
        self.assertEqual(hold["held_session_fraction"], 1.)

    def test_overlap_and_incomplete_horizon_rejected(self):
        frame = fixture(10)
        for cycles in ([(0, 2, 1), (2, 4, 1)], [(0, 15, 1)]):
            with self.assertRaises(ValueError): daily_ledger(frame, cycles, PROTOCOL)


if __name__ == "__main__":
    unittest.main()
