"""Kiểm tra đơn vị giá thô, lịch T+2.5, quyền và phân trang nguồn."""

import unittest
from unittest.mock import Mock, patch

import pandas as pd

from core.execution_prices import (
    build_verified_cycle_schedule, corporate_action_barriers,
    execution_prices_for_cycle, normalise_vci_execution_prices,
)
from scripts.verify_execution_price_gate import fetch_paginated


def raw_records() -> list[dict]:
    """Tạo năm phiên, giá điều chỉnh khác rõ giá khớp lệnh thô."""
    return [{
        "ticker": "FPT", "tradingDate": date, "openPrice": 100_000,
        "highestPrice": 105_000, "lowestPrice": 99_000, "closePrice": 102_000,
        "matchPrice": 102_000, "referencePrice": 102_000, "totalMatchVolume": 1000,
        "openPriceAdjusted": 50_000, "closePriceAdjusted": 51_000,
    } for date in ("2022-06-09", "2022-06-10", "2022-06-13", "2022-06-14", "2022-06-15")]


def fixture_frame() -> pd.DataFrame:
    """Tạo frame thô trên lịch có cuối tuần."""
    return normalise_vci_execution_prices(raw_records(), "FPT", "2022-06-09", "2022-06-15")


class ExecutionPricesTests(unittest.TestCase):
    """Không dùng giá điều chỉnh hoặc lợi nhuận sai cửa sổ để mở gate."""

    def test_raw_fields_and_units_are_explicit(self) -> None:
        """Giá điều chỉnh không thể thay thế Open/Close thực thi."""
        frame = fixture_frame()
        self.assertEqual(float(frame.Open.iloc[0]), 100.0)
        self.assertEqual(float(frame.Close.iloc[0]), 102.0)
        self.assertEqual(float(frame.Volume.iloc[0]), 1000.0)
        self.assertNotIn("openPriceAdjusted", frame.columns)

    def test_adjusted_only_wrong_symbol_and_duplicate_raise(self) -> None:
        """Thiếu trường thô, lẫn mã hoặc ngày trùng phải bị từ chối."""
        adjusted_only = raw_records()
        for record in adjusted_only:
            record.pop("openPrice")
        mixed = raw_records()
        mixed[0]["ticker"] = "VNM"
        for records in (adjusted_only, mixed, raw_records() + raw_records()[:1]):
            with self.subTest(records=records), self.assertRaises(ValueError):
                normalise_vci_execution_prices(records, "FPT", "2022-06-09", "2022-06-15")

    def test_invalid_prices_volume_and_match_raise(self) -> None:
        """Không cắt biên giá hoặc bỏ qua giá khớp cuối bất nhất."""
        for key, value in (("openPrice", float("nan")), ("highestPrice", 1),
                           ("totalMatchVolume", -1), ("totalMatchVolume", 1.2),
                           ("matchPrice", -1), ("referencePrice", 0)):
            records = raw_records()
            records[0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                normalise_vci_execution_prices(records, "FPT", "2022-06-09", "2022-06-15")

    def test_distinct_close_and_last_match_do_not_rewrite_close(self) -> None:
        """Giá khớp cuối riêng không được thay giá đóng cửa của provider."""
        records = raw_records()
        records[0]["matchPrice"] = 101_000
        frame = normalise_vci_execution_prices(records, "FPT", "2022-06-09", "2022-06-15")
        self.assertEqual(float(frame.Close.iloc[0]), 102.0)
        self.assertEqual(float(frame.MatchPrice.iloc[0]), 101.0)

    def test_no_matched_volume_blocks_execution(self) -> None:
        """Giá giữ nguyên trong phiên không khớp không phải giá mua/bán có thể dùng."""
        frame = fixture_frame()
        frame.loc[1, "Volume"] = 0
        schedule = build_verified_cycle_schedule(frame, [], warmup=1)
        self.assertEqual(schedule.exclusion_reason.iloc[0], "NO_MATCHED_VOLUME_AT_EXECUTION")
        with self.assertRaisesRegex(ValueError, "khớp lệnh"):
            execution_prices_for_cycle(frame, [], "2022-06-09", "2022-06-10", "2022-06-14")

    def test_next_session_entry_and_third_session_exit(self) -> None:
        """Cuối tuần không được tính là phiên; dùng Open vào và Close ra."""
        frame = fixture_frame()
        frame.loc[1, "Open"] = 101.0
        frame.loc[3, "Close"] = 104.0
        frame.loc[4, "Reference"] = 104.0
        self.assertEqual(execution_prices_for_cycle(
            frame, [], "2022-06-09", "2022-06-10", "2022-06-14"
        ), (101.0, 104.0))
        with self.assertRaisesRegex(ValueError, r"t\+1"):
            execution_prices_for_cycle(frame, [], "2022-06-09", "2022-06-13", "2022-06-15")

    def test_cash_and_stock_rights_during_holding_raise(self) -> None:
        """Không coi mất giá ngày quyền là lỗ giao dịch của engine hiện tại."""
        for category in ("DIV", "ISS"):
            events = [{"eventCode": category, "exrightDate": "2022-06-13", "publicDate": "2022-06-01"}]
            with self.subTest(category=category), self.assertRaisesRegex(ValueError, "quyền"):
                execution_prices_for_cycle(fixture_frame(), events, "2022-06-09", "2022-06-10", "2022-06-14")

    def test_reference_gap_is_blocked_even_without_event(self) -> None:
        """Lịch sự kiện thiếu không được che thay đổi giá tham chiếu."""
        frame = fixture_frame()
        frame.loc[2, "Reference"] = 90.0
        self.assertIn(pd.Timestamp("2022-06-13"), corporate_action_barriers(frame, []))
        with self.assertRaisesRegex(ValueError, "quyền"):
            execution_prices_for_cycle(frame, [], "2022-06-09", "2022-06-10", "2022-06-14")

    def test_buying_on_exright_date_does_not_receive_right(self) -> None:
        """Quyền đúng ngày vào không phát sinh cho người mua mới."""
        events = [{"exrightDate": "2022-06-10"}]
        self.assertEqual(execution_prices_for_cycle(
            fixture_frame(), events, "2022-06-09", "2022-06-10", "2022-06-14"
        ), (100.0, 102.0))

    def test_candidate_schedule_retains_explicit_exclusions(self) -> None:
        """Không đánh lại index hay chuyển mốc sau khi loại chu kỳ có quyền."""
        events = [{"exrightDate": "2022-06-13"}]
        schedule = build_verified_cycle_schedule(fixture_frame(), events, warmup=1)
        self.assertEqual(len(schedule), 1)
        self.assertFalse(bool(schedule.eligible.iloc[0]))
        self.assertEqual(schedule.exclusion_reason.iloc[0], "CORPORATE_ACTION_DURING_HOLDING")
        self.assertEqual(schedule.entry_date.iloc[0], pd.Timestamp("2022-06-10"))

    @staticmethod
    def page(number: int, rows: list[int], *, size: int = 2, total: int = 3) -> Mock:
        """Mô phỏng server giới hạn size nhỏ hơn client yêu cầu."""
        response = Mock()
        response.url, response.content = "https://iq.vietcap.com.vn/test", b"response"
        response.json.return_value = {"successful": True, "code": 0, "data": {
            "content": [{"id": row} for row in rows], "number": number,
            "totalElements": total, "totalPages": 2, "size": size, "last": number == 1,
        }}
        return response

    def test_pagination_uses_effective_server_size(self) -> None:
        """Trang thứ hai dùng size thực tế để không bỏ mất dữ liệu."""
        with patch("vnstock.core.utils.user_agent.get_headers", return_value={}), patch("scripts.verify_execution_price_gate.requests.get", side_effect=[
            self.page(0, [1, 2]), self.page(1, [3])
        ]) as get, patch("scripts.verify_execution_price_gate.time.sleep"):
            records, receipts = fetch_paginated("https://iq.vietcap.com.vn/test", {})
        self.assertEqual([r["id"] for r in records], [1, 2, 3])
        self.assertEqual(get.call_args_list[1].kwargs["params"]["size"], 2)
        self.assertEqual(len(receipts), 2)

    def test_truncated_page_raises(self) -> None:
        """Một trang ngắn không được coi là đã tải đủ corpus."""
        with patch("vnstock.core.utils.user_agent.get_headers", return_value={}), \
                patch("scripts.verify_execution_price_gate.requests.get", return_value=self.page(0, [1])), \
                patch("scripts.verify_execution_price_gate.time.sleep"), self.assertRaisesRegex(ValueError, "cắt cụt"):
            fetch_paginated("https://iq.vietcap.com.vn/test", {})


if __name__ == "__main__":
    unittest.main()
