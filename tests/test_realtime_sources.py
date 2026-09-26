"""Kiểm tra loader chỉ dùng VCI và KBS."""

import unittest
from unittest.mock import patch

import pandas as pd

from core import realtime_loader as loader


class RealtimeSourcesTests(unittest.TestCase):
    """Bảo vệ thứ tự nguồn và đơn vị giá khi fallback."""

    def setUp(self) -> None:
        loader.clear_cache()

    def test_only_vci_and_kbs_are_configured(self) -> None:
        """Danh sách nguồn của OHLCV phải đúng hai provider."""
        self.assertEqual(loader.DATA_SOURCES, ["VCI", "KBS"])

    def test_kbs_is_used_when_vci_fails_validation(self) -> None:
        """Nến VCI sai OHLC không được đưa vào cache."""
        bad = pd.DataFrame({
            "time": ["2024-01-02"], "open": [12.0], "high": [11.0],
            "low": [9.0], "close": [10.0], "volume": [100],
        })
        good = bad.copy()
        good["open"] = 10.0

        def fetch(_symbol: str, _start: str, _end: str, _interval: str, source: str) -> pd.DataFrame:
            return bad if source == "VCI" else good

        with patch.object(loader, "_fetch_from_vnstock", side_effect=fetch) as mocked:
            frame, error = loader.fetch_realtime_ohlcv("FPT", tail=1, use_cache=False)
        self.assertEqual(error, "")
        self.assertEqual(float(frame.loc[0, "Open"]), 10.0)
        self.assertEqual([call.args[-1] for call in mocked.call_args_list], ["VCI", "KBS"])

    def test_index_price_is_preserved_in_points(self) -> None:
        """vnstock 4.0.9 trả chỉ số theo điểm; không được nhân thêm 1.000 lần."""
        raw = pd.DataFrame({
            "time": ["2024-01-02"], "open": [1200.0], "high": [1210.0],
            "low": [1190.0], "close": [1205.0], "volume": [100],
        })

        class FakeQuote:
            """Giả lập phản hồi Quote không dùng mạng."""

            def __init__(self, symbol: str, source: str) -> None:
                self.symbol = symbol
                self.source = source

            def history(self, **_kwargs) -> pd.DataFrame:
                return raw

        for source in loader.DATA_SOURCES:
            with self.subTest(source=source), patch("vnstock.api.quote.Quote", FakeQuote):
                frame = loader._fetch_from_vnstock("VNINDEX", "2024-01-01", "2024-01-31", "1D", source)
            self.assertEqual(float(frame.loc[0, "open"]), 1200.0)
            self.assertEqual(float(frame.loc[0, "close"]), 1205.0)


if __name__ == "__main__":
    unittest.main()
