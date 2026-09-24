"""Kiểm thử đối chiếu nhận định thị giác với dữ liệu OHLCV thực tế."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.pattern_agent import (
    _verify_pattern_against_ohlcv,
    create_pattern_agent,
)
from agents.trend_agent import (
    _verify_trend_against_ohlcv,
    create_trend_agent,
)


PATTERN_BULLISH_VI = """**Mô hình:** Bullish Engulfing
**Độ tin cậy:** Cao
**Thiên lệch dự báo:** Tăng
**Bằng chứng:** Nến tăng bao phủ nến trước
**Nến quan trọng:** Nến cuối tăng mạnh
**Hàm ý giao dịch:** Mua"""

PATTERN_BULLISH_EN = """**Pattern:** Bullish Engulfing
**Confidence:** High
**Directional bias:** Bullish
**Evidence:** Bullish candle engulfs the prior candle
**Key candles:** Strong final green candle
**Trading implication:** Buy"""

TREND_UP_VI = """**Hướng xu hướng:** Tăng mạnh
**Mức hỗ trợ:** 100
**Mức kháng cự:** 170
**Độ dốc đường xu hướng:** Đang tăng
**Giá so với hỗ trợ:** Bật lên
**Phân tích chi tiết:** Giá duy trì trên đường xu hướng
**Dự đoán xu hướng:** Tiếp tục tăng
**Độ tin cậy:** Cao"""

TREND_UP_EN = """**Trend direction:** Strong Up
**Support level:** 100
**Resistance level:** 170
**Trendline slope:** Rising
**Price vs support:** Bouncing
**Detailed analysis:** Price holds above its trendline
**Trend forecast:** Continued advance
**Confidence:** High"""


def _ohlcv(opens, closes):
    return {
        "Datetime": [f"2024-01-{index + 1:02d}" for index in range(len(closes))],
        "Open": list(opens),
        "High": [max(open_, close) + 1.0 for open_, close in zip(opens, closes)],
        "Low": [min(open_, close) - 1.0 for open_, close in zip(opens, closes)],
        "Close": list(closes),
    }


class VisionVerificationTests(unittest.TestCase):
    def test_pattern_warning_downgrades_bullish_claim_on_strong_bearish_candle(self):
        data = _ohlcv(
            [105.0, 104.0, 103.0, 102.0, 110.0],
            [104.0, 103.0, 102.0, 101.0, 90.0],
        )

        verified = _verify_pattern_against_ohlcv(PATTERN_BULLISH_VI, data, "vi")

        self.assertIn("**Độ tin cậy:** Thấp", verified)
        self.assertIn(
            "[Cảnh báo đối chiếu: Nến thực tế không khớp mẫu hình tăng]",
            verified,
        )

    def test_pattern_warning_is_symmetric_for_bearish_claim(self):
        report = PATTERN_BULLISH_EN.replace("Bullish", "Bearish").replace(
            "High", "Medium"
        )
        data = _ohlcv(
            [95.0, 96.0, 97.0, 98.0, 90.0],
            [96.0, 97.0, 98.0, 99.0, 110.0],
        )

        verified = _verify_pattern_against_ohlcv(report, data, "en")

        self.assertIn("**Confidence:** Low", verified)
        self.assertIn("[Verification warning:", verified)
        self.assertIn("bearish pattern", verified)

    def test_pattern_matching_ohlcv_is_not_flagged(self):
        data = _ohlcv(
            [95.0, 96.0, 97.0, 98.0, 90.0],
            [96.0, 97.0, 98.0, 99.0, 110.0],
        )

        verified = _verify_pattern_against_ohlcv(PATTERN_BULLISH_VI, data, "vi")

        self.assertNotIn("Cảnh báo đối chiếu", verified)
        self.assertIn("**Độ tin cậy:** Cao", verified)

    def test_bullish_reversal_after_four_red_candles_is_not_flagged(self):
        data = _ohlcv(
            [105.0, 104.0, 103.0, 102.0, 90.0],
            [104.0, 103.0, 102.0, 101.0, 110.0],
        )

        verified = _verify_pattern_against_ohlcv(PATTERN_BULLISH_VI, data, "vi")

        self.assertNotIn("Cảnh báo đối chiếu", verified)

    def test_trend_warning_when_uptrend_is_below_falling_sma20_and_sma50(self):
        # W=45 là cửa sổ mặc định của backtest; SMA50 dùng lịch sử dài khả dụng.
        closes = [200.0 - index for index in range(45)]
        data = _ohlcv([close + 0.5 for close in closes], closes)

        verified = _verify_trend_against_ohlcv(TREND_UP_VI, data, "vi")

        self.assertIn("**Độ tin cậy:** Thấp", verified)
        self.assertIn(
            "[Cảnh báo đối chiếu: Xu hướng thị giác tăng mâu thuẫn với SMA20/SMA50 và độ dốc giá]",
            verified,
        )

    def test_trend_matching_ohlcv_is_not_flagged(self):
        closes = [100.0 + index for index in range(60)]
        data = _ohlcv([close - 0.5 for close in closes], closes)

        verified = _verify_trend_against_ohlcv(TREND_UP_VI, data, "vi")

        self.assertNotIn("Cảnh báo đối chiếu", verified)
        self.assertIn("**Độ tin cậy:** Cao", verified)

    def test_english_trend_warning_is_injected_and_downgraded(self):
        closes = [200.0 - index for index in range(60)]
        data = _ohlcv([close + 0.5 for close in closes], closes)

        verified = _verify_trend_against_ohlcv(TREND_UP_EN, data, "en")

        self.assertIn("**Confidence:** Low", verified)
        self.assertIn("[Verification warning: Visual uptrend", verified)

    def test_verifiers_fail_open_when_ohlcv_is_insufficient(self):
        self.assertEqual(
            _verify_pattern_against_ohlcv(PATTERN_BULLISH_VI, {}, "vi"),
            PATTERN_BULLISH_VI,
        )
        self.assertEqual(
            _verify_trend_against_ohlcv(TREND_UP_VI, {"Close": [100.0]}, "vi"),
            TREND_UP_VI,
        )

    def test_pattern_agent_places_verification_warning_in_downstream_report(self):
        data = _ohlcv(
            [105.0, 104.0, 103.0, 102.0, 110.0],
            [104.0, 103.0, 102.0, 101.0, 90.0],
        )
        vision_llm = Mock()
        vision_llm.invoke.return_value = SimpleNamespace(content=PATTERN_BULLISH_VI)

        with patch("builtins.print"):
            result = create_pattern_agent(object(), vision_llm, object())(
                {
                    "time_frame": "1 ngày",
                    "kline_data": data,
                    "pattern_image": "ZmFrZQ==",
                    "messages": [],
                    "language": "vi",
                }
            )

        self.assertIn("Cảnh báo đối chiếu", result["pattern_report"])

    def test_trend_agent_places_verification_warning_in_downstream_report(self):
        closes = [200.0 - index for index in range(60)]
        data = _ohlcv([close + 0.5 for close in closes], closes)
        vision_llm = Mock()
        vision_llm.invoke.return_value = SimpleNamespace(content=TREND_UP_VI)

        with patch("builtins.print"):
            result = create_trend_agent(object(), vision_llm, object())(
                {
                    "time_frame": "1 ngày",
                    "kline_data": data,
                    "trend_image": "ZmFrZQ==",
                    "messages": [],
                    "language": "vi",
                }
            )

        self.assertIn("Cảnh báo đối chiếu", result["trend_report"])


if __name__ == "__main__":
    unittest.main()
