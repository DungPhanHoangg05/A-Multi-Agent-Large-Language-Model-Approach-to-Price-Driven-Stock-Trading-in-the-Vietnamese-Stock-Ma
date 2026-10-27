"""Kiểm hợp đồng inventory offline, không dùng GPU hoặc gọi nhà cung cấp."""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from scripts.audit_mt_bicl_resources import date_hits, provisional_counts


class ResourceAuditTests(unittest.TestCase):
    """Bảo vệ đếm support và cách nhận diện exposure ngày query."""

    def setUp(self) -> None:
        """Tạo 40 phiên liên tiếp đủ cửa sổ feature và giữ lệnh."""
        self.calendar = pd.bdate_range("2019-01-02", periods=40)
        self.frame = pd.DataFrame({
            "Datetime": self.calendar, "Open": 100.0, "High": 101.0,
            "Low": 99.0, "Close": 100.0, "Reference": 100.0,
            "Volume": np.full(40, 1000),
        })

    def test_dense_inventory_does_not_inherit_600_bar_warmup(self) -> None:
        """History sớm có support thật, không coi lịch memory cũ là toàn nguồn."""
        result = provisional_counts(self.frame, [], self.calendar)
        year = result["years"]["2019"]
        self.assertEqual(year["candidates"], 6)
        self.assertEqual(year["joint_eligible"], 6)

    def test_holding_and_feature_barriers_are_separate(self) -> None:
        """Ngày quyền có thể chặn nhãn hoặc cửa sổ feature theo từng khoảng."""
        events = [{"exrightDate": self.calendar[22].strftime("%Y-%m-%d")}]
        year = provisional_counts(self.frame, events, self.calendar)["years"]["2019"]
        self.assertEqual(year["holding_eligible"], 5)
        self.assertEqual(year["feature_barrier"], 5)
        self.assertEqual(year["joint_eligible"], 0)

    def test_future_event_does_not_change_support(self) -> None:
        """Thêm quyền sau nguồn hiện tại không đổi đếm prefix."""
        before = provisional_counts(self.frame, [], self.calendar)
        after = provisional_counts(self.frame, [{"exrightDate": "2025-01-02"}], self.calendar)
        self.assertEqual(before, after)

    def test_missing_calendar_session_fails_closed(self) -> None:
        """Không nén lịch bị thiếu phiên để tạo support giả."""
        with self.assertRaises(ValueError):
            provisional_counts(self.frame.drop(index=10), [], self.calendar)

    def test_cycles_crossing_year_are_not_counted_in_either_year(self) -> None:
        """Purge theo query lẫn exit trước chia split."""
        frame = self.frame.copy()
        calendar = pd.bdate_range("2019-11-28", periods=40)
        frame["Datetime"] = calendar
        result = provisional_counts(frame, [], calendar)
        self.assertEqual(result["cross_year_excluded"], 1)
        self.assertEqual(sum(v["candidates"] for v in result["years"].values()), 5)

    def test_exposure_scans_nested_query_dates_only(self) -> None:
        """Không nhầm ngày quyền, năm trong UUID hoặc nguồn giá thành response test."""
        value = {"id": "2025-01-01", "exrightDate": "2025-01-02",
                 "requested_end": "2025-12-31", "points": [
                     {"as_of_date": "2024-12-31"}, {"query_date": "2025-03-03"},
                     {"as_of_date": "2025-04-02"}]}
        self.assertEqual(date_hits(value), ["/points/1/query_date=2025-03-03",
                                           "/points/2/as_of_date=2025-04-02"])


if __name__ == "__main__":
    unittest.main()
