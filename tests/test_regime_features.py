"""Kiểm tra công thức và hợp đồng thời gian của đặc trưng VN-Index."""

import unittest

import numpy as np
import pandas as pd

from core.regime_detector import FEATURE_COLUMNS, build_regime_features


def make_history(rows: int = 650, start: str = "2018-01-02") -> pd.DataFrame:
    """Tạo lịch sử xác định có xu hướng và biến động, không dùng mạng."""
    index = np.arange(rows, dtype=float)
    return pd.DataFrame({
        "Datetime": pd.bdate_range(start, periods=rows),
        "Close": 1000.0 * np.exp(0.0002 * index + 0.06 * np.sin(index / 21)),
    })


class RegimeFeatureTests(unittest.TestCase):
    def test_formulas_and_first_valid_session(self) -> None:
        history = make_history()
        features = build_regime_features(history, history.Datetime.iloc[-1])
        self.assertEqual(len(features), len(history) - 199)
        self.assertEqual(features.Datetime.iloc[0], history.Datetime.iloc[199])
        close = history.Close
        self.assertAlmostEqual(features.log_return.iloc[-1], np.log(close.iloc[-1] / close.iloc[-2]))
        self.assertAlmostEqual(features.volatility_20.iloc[-1], np.log(close / close.shift()).iloc[-20:].std(ddof=1))
        for window in (20, 50, 200):
            self.assertAlmostEqual(features[f"distance_ma{window}"].iloc[-1], close.iloc[-1] / close.iloc[-window:].mean() - 1)

    def test_prefix_features_do_not_depend_on_future(self) -> None:
        history = make_history()
        prefix = history.iloc[:400].copy()
        actual = build_regime_features(prefix, prefix.Datetime.iloc[-1])
        full = build_regime_features(history, history.Datetime.iloc[-1])
        pd.testing.assert_frame_equal(actual, full.iloc[:len(actual)].reset_index(drop=True))

    def test_invalid_history_and_cutoff_raise(self) -> None:
        history = make_history()
        invalid = [history.iloc[:199], history.iloc[::-1], pd.concat([history, history.iloc[[-1]]])]
        for value in (np.nan, np.inf, 0, -1):
            frame = history.copy()
            frame.loc[250, "Close"] = value
            invalid.append(frame)
        for frame in invalid:
            with self.subTest(rows=len(frame)), self.assertRaises(ValueError):
                build_regime_features(frame, history.Datetime.iloc[-1])
        with self.assertRaises(ValueError):
            build_regime_features(history, history.Datetime.iloc[-2])

    def test_constant_price_has_finite_zero_features(self) -> None:
        history = make_history(200)
        history["Close"] = 1000.0
        features = build_regime_features(history, history.Datetime.iloc[-1])
        self.assertTrue((features.loc[:, FEATURE_COLUMNS].to_numpy() == 0).all())
