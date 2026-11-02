"""Kiểm nhân quả regime, purge và join/resampling của audit R2, không gọi API."""

from __future__ import annotations

from copy import deepcopy
import unittest

import numpy as np
import pandas as pd

from core.revision72_analysis import block_interval
from core.revision_r2_panel import audit_fold, calendar_panel, classify_context, context_features


def frame() -> pd.DataFrame:
    """Dựng chuỗi có biến động không hằng để thử thay đổi tương lai."""
    i = np.arange(160)
    close = 100 * np.exp(.001 * i + .02 * np.sin(i / 5))
    return pd.DataFrame({"date": pd.bdate_range("2020-01-01", periods=len(i)).strftime("%Y-%m-%d"),
                         "Close": close, "Volume": 1000 + (i % 17) * 300})


class RegimeLeakageTests(unittest.TestCase):
    """Các thông tin chưa quan sát không được đổi phân nhóm tại cutoff."""

    def test_future_prices_and_volumes_do_not_change_context(self) -> None:
        """Mutation toàn bộ tương lai vẫn giữ features và ngưỡng của unit trước đó."""
        original = frame()
        changed = original.copy()
        changed.loc[121:, "Close"] *= 30
        changed.loc[121:, "Volume"] *= 1000
        train = list(range(60, 90, 3))
        self.assertEqual(classify_context(context_features(original), train, 120),
                         classify_context(context_features(changed), train, 120))

    def test_validation_distribution_cannot_fit_thresholds(self) -> None:
        """Thay validation sau train không được đổi median dùng phân nhóm test."""
        data = context_features(frame())
        changed = data.copy()
        changed.loc[90:119, ["volatility_20", "turnover_proxy_20"]] *= 10000
        train = list(range(60, 90, 3))
        a, b = classify_context(data, train, 120), classify_context(changed, train, 120)
        self.assertEqual(a, b)

    def test_no_history_or_zero_liquidity_is_unknown(self) -> None:
        """Không biến thiếu lịch sử hoặc mẫu train thanh khoản rỗng thành neutral/high."""
        data = frame()
        data["Volume"] = 0
        features = context_features(data)
        result = classify_context(features, [20, 23, 26], 30)
        self.assertEqual(result["trend"], "unknown")
        self.assertEqual(result["liquidity_proxy"], "unknown")
        with self.assertRaises(ValueError):
            classify_context(features, [30], 30)

    def test_purge_rejects_label_touching_validation_or_test(self) -> None:
        """Label exit đúng ngày split kế tiếp vẫn bị từ chối."""
        data = frame()
        scope = {"symbol": "A", "fold": "test", "train": [60, 63], "validation": [69, 72], "test": [78, 85],
            "last_train_label_date": data["date"].iloc[66], "first_validation_date": data["date"].iloc[69],
            "last_validation_label_date": data["date"].iloc[75], "first_test_date": data["date"].iloc[78]}
        protocol = {"horizon_observed_sessions": 3, "alpha_history": 60, "fee_each_side": .0025, "slippage_each_side": .001}
        self.assertTrue(audit_fold(data.assign(Open=data["Close"]), scope, protocol)["purge_pass"])
        for role, bad in (("validation", [66, 72]), ("test", [75, 85])):
            changed = deepcopy(scope)
            changed[role] = bad
            with self.assertRaisesRegex(ValueError, "Label span"):
                audit_fold(data.assign(Open=data["Close"]), changed, protocol)


class CalendarDependenceTests(unittest.TestCase):
    """Panel phải dùng ngày thật, giữ missing và phụ thuộc chéo giữa các mã."""

    def sample(self) -> tuple[list[dict], list[dict]]:
        """BHN thiếu ngày đầu, không giả định test_id đồng nhất giữa các mã."""
        units = [{"id": "A_early", "symbol": "A", "date": "2023-07-03"},
                 {"id": "A_late", "symbol": "A", "date": "2025-10-01"},
                 {"id": "BHN_late", "symbol": "BHN", "date": "2025-10-01"}]
        rows = [{"unit_id": u["id"], "symbol": u["symbol"], "date": u["date"], "variant": v,
                 "prediction": "SHORT", "label_net": "DOWN"} for u in units for v in ("B", "AS")]
        return units, rows

    def test_calendar_join_retains_missing_cells_and_ignores_row_order(self) -> None:
        """Hai ô thiếu BHN vẫn là NaN, không bị điền SHORT/CASH."""
        units, rows = self.sample()
        a = calendar_panel(units, rows, ["A", "BHN"])
        b = calendar_panel(units[::-1], rows[::-1], ["A", "BHN"])
        pd.testing.assert_frame_equal(a, b)
        missing = a.loc[~a["eligible"]]
        self.assertEqual(len(missing), 2)
        self.assertTrue(missing["prediction"].isna().all())
        self.assertEqual(set(missing["date"]), {"2023-07-03"})

    def test_duplicate_or_missing_committed_prediction_rejected(self) -> None:
        """Thiếu inference không được giả làm exclusion trong panel."""
        units, rows = self.sample()
        for changed in (rows + [rows[0]], rows[2:], [dict(rows[0], unit_id="wrong")] + rows[1:]):
            with self.assertRaises(ValueError):
                calendar_panel(units, changed, ["A", "BHN"])

    def test_perfectly_correlated_symbols_do_not_narrow_block_interval(self) -> None:
        """Nhân bản cùng market shock qua mã không tạo thêm cluster độc lập."""
        def predictions(symbols: list[str]) -> list[dict]:
            return [{"unit_id": f"{s}_{block}_{day}", "symbol": s, "fold": f"b{block}",
                "date": f"202{block}-01-0{day+1}", "variant": variant,
                "label_net": "UP" if day == 0 else "DOWN",
                "prediction": ("LONG" if day == 0 else "SHORT") if variant == "AS" and block % 2 else "SHORT"}
                for block in range(6) for day in range(2) for s in symbols for variant in ("AS", "B")]
        one = block_interval(predictions(["A"]), ("AS", "B"))
        many = block_interval(predictions(["A", "B", "C", "D"]), ("AS", "B"))
        self.assertEqual(one["n_blocks"], many["n_blocks"])
        np.testing.assert_allclose(one["percentile_95"], many["percentile_95"], atol=1e-14)
        shuffled = list(reversed(predictions(["A", "B", "C", "D"])))
        self.assertEqual(many, block_interval(shuffled, ("AS", "B")))


if __name__ == "__main__":
    unittest.main()
