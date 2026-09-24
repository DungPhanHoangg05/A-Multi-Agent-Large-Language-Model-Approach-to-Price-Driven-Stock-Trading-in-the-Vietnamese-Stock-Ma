"""Kiểm tra các rào chắn dữ liệu EOD dùng trong nghiên cứu."""

import unittest
from unittest.mock import patch

import pandas as pd

from scripts.prepare_historical_data import clean_ohlcv, download_data, validate_calendar


class HistoricalDataPrepTests(unittest.TestCase):
    """Bảo đảm nến lỗi và phiên thiếu không thể đi vào bộ dữ liệu."""

    @staticmethod
    def fixture() -> pd.DataFrame:
        """Tạo hai phiên giao dịch tối giản."""
        return pd.DataFrame({
            "time": ["2024-01-02", "2024-01-03"],
            "open": [10.0, 11.0],
            "high": [11.0, 12.0],
            "low": [9.0, 10.0],
            "close": [10.5, 11.5],
            "volume": [1000, 1200],
        })

    def test_valid_frame_is_sorted_and_normalized(self) -> None:
        """Dữ liệu hợp lệ có đúng cấu trúc engine cần."""
        frame = clean_ohlcv(self.fixture().iloc[::-1], "FPT", "2024-01-01", "2024-01-31")
        self.assertEqual(frame.columns.tolist(), ["Datetime", "Open", "High", "Low", "Close", "Volume"])
        self.assertEqual(frame["Datetime"].dt.strftime("%Y-%m-%d").tolist(), ["2024-01-02", "2024-01-03"])

    def test_duplicate_and_invalid_ohlc_raise(self) -> None:
        """Không tự động xóa nến trùng hoặc chữa giá sai."""
        duplicate = pd.concat([self.fixture(), self.fixture().iloc[[0]]], ignore_index=True)
        with self.assertRaisesRegex(ValueError, "trùng ngày"):
            clean_ohlcv(duplicate, "FPT", "2024-01-01", "2024-01-31")
        invalid = self.fixture()
        invalid.loc[0, "high"] = 8.0
        with self.assertRaisesRegex(ValueError, "OHLC không nhất quán"):
            clean_ohlcv(invalid, "FPT", "2024-01-01", "2024-01-31")

    def test_missing_session_raises(self) -> None:
        """Ngày giao dịch thiếu so với VN-Index phải được báo rõ."""
        reference = clean_ohlcv(self.fixture(), "VNINDEX", "2024-01-01", "2024-01-31")
        frames = {symbol: reference.copy() for symbol in ("VNINDEX", "FPT", "VNM", "VCB", "MWG")}
        frames["FPT"] = reference.iloc[[0]].copy()
        with self.assertRaisesRegex(ValueError, "thiếu 1 phiên"):
            validate_calendar(frames)

    def test_vci_bad_candle_is_replaced_by_complete_kbs_candle(self) -> None:
        """Chỉ dùng KBS cho nguyên nến lỗi và lưu cả hai bản gốc."""
        primary = self.fixture()
        primary.loc[0, "open"] = 12.0
        secondary = self.fixture()
        secondary.loc[0, "open"] = 10.2
        secondary.loc[0, "volume"] = 900

        def fetch(_symbol: str, _start: str, _end: str, _interval: str, source: str) -> pd.DataFrame:
            return primary if source == "VCI" else secondary

        with (
            patch("scripts.prepare_historical_data.SYMBOLS", ("VNINDEX",)),
            patch("scripts.prepare_historical_data._fetch_from_vnstock", side_effect=fetch),
        ):
            frames, corrections = download_data("2024-01-01", "2024-01-31")
        self.assertEqual(len(corrections), 1)
        self.assertEqual(corrections[0]["date"], "2024-01-02")
        self.assertEqual(corrections[0]["original"]["Open"], 12.0)
        self.assertEqual(corrections[0]["replacement"]["Volume"], 900.0)
        self.assertEqual(float(frames["VNINDEX"].loc[0, "Volume"]), 900.0)


if __name__ == "__main__":
    unittest.main()
