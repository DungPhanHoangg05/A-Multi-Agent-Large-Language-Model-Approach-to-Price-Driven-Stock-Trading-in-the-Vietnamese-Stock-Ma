"""Kiểm nguồn nối 2025 và cutoff, không gọi mạng hoặc sinh nhãn thị trường."""

from copy import deepcopy
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from core.execution_prices import raw_point_in_time_snapshot
from scripts import prepare_unified_execution_prices as producer
from test_execution_prices import fixture_frame


class UnifiedExecutionInputTests(unittest.TestCase):
    """Giữ prefix, kiểm quyền/eligibility và chống tự mở gate bằng metadata."""

    def extension(self) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
        """Tạo ví dụ nối giả lập; không sử dụng giá 2025 thật."""
        prefix = fixture_frame()
        extension = prefix.tail(2).copy().reset_index(drop=True)
        extension["Datetime"] = pd.to_datetime(["2025-01-02", "2025-01-03"])
        calendar = pd.concat([prefix.Datetime, extension.Datetime], ignore_index=True)
        return prefix, extension, calendar

    def test_valid_extension_preserves_point_in_time_prefix(self) -> None:
        """Nối nến mới không làm thay đổi snapshot trước năm 2025."""
        prefix, extension, calendar = self.extension()
        producer.assert_extension(prefix, extension, calendar)
        combined = pd.concat([prefix, extension], ignore_index=True)
        producer.assert_prefix(combined, prefix)
        pd.testing.assert_frame_equal(raw_point_in_time_snapshot(combined, "2022-06-10"),
                                      raw_point_in_time_snapshot(prefix, "2022-06-10"))

    def test_missing_or_duplicate_session_rejects_extension(self) -> None:
        """Không nội suy phiên thiếu hoặc nhận ngày lặp khi nối nguồn."""
        prefix, extension, calendar = self.extension()
        for frame in (extension.iloc[:1], pd.concat([extension, extension.tail(1)], ignore_index=True)):
            with self.subTest(rows=len(frame)), self.assertRaises(ValueError):
                producer.assert_extension(prefix, frame, calendar)

    def test_wrong_year_rejects_extension(self) -> None:
        """Nguồn tải ngoài 2025 không thể được gắn nhãn snapshot 2025."""
        prefix, extension, calendar = self.extension()
        extension.loc[0, "Datetime"] = pd.Timestamp("2024-12-31")
        with self.assertRaisesRegex(ValueError, "2025"):
            producer.assert_extension(prefix, extension, calendar)

    def test_rewriting_legacy_prices_is_rejected(self) -> None:
        """Dù có nến 2025 hợp lệ, sửa giá trước 2025 vẫn bị phát hiện."""
        prefix, extension, _ = self.extension()
        combined = pd.concat([prefix, extension], ignore_index=True)
        combined.loc[0, "Open"] *= .5
        with self.assertRaisesRegex(ValueError, "prefix"):
            producer.assert_prefix(combined, prefix)

    def test_invalid_future_prices_do_not_leak_into_old_snapshot(self) -> None:
        """Cutoff phải áp trước kiểm giá phần tương lai của snapshot."""
        prefix, extension, _ = self.extension()
        combined = pd.concat([prefix, extension], ignore_index=True)
        combined.loc[combined.Datetime.dt.year.eq(2025), "Open"] = float("inf")
        pd.testing.assert_frame_equal(raw_point_in_time_snapshot(combined, "2022-06-10"),
                                      raw_point_in_time_snapshot(prefix, "2022-06-10"))

    def calendar_frame(self) -> pd.DataFrame:
        """Dùng lịch thật với giá hằng tổng hợp để kiểm lưới, không tính payoff."""
        days = pd.read_csv(producer.CALENDAR, usecols=["Datetime"], parse_dates=["Datetime"])
        for name in ("Open", "High", "Low", "Close", "Reference", "MatchPrice"):
            days[name] = 100.
        days["Volume"] = 1000
        return days

    def test_quarter_grid_does_not_select_confirmation_dates(self) -> None:
        """Giữ phase step3 qua biên quý; metadata không là lịch execution."""
        coverage = producer.quarter_coverage(self.calendar_frame(), [])
        self.assertEqual([v["eligible"] for v in coverage["quarters"].values()], [19, 19, 20, 21])
        self.assertEqual(coverage["eligible"], 79)
        self.assertEqual(coverage["step_anchor"], "2025-01-02")
        self.assertIsNone(coverage["selected_dates"])
        self.assertIs(coverage["is_execution_plan"], False)

    def test_right_during_holding_reduces_pool_without_rephasing(self) -> None:
        """Quyền trong cycle đầu bị loại, không dời lịch để bù điểm."""
        frame = self.calendar_frame()
        coverage = producer.quarter_coverage(frame, [{"exrightDate": "2025-01-06"}])
        self.assertEqual(coverage["quarters"]["1"], {"closed_within_quarter": 19, "eligible": 18})
        self.assertEqual(coverage["eligible"], 78)

    def test_write_once_rejects_changed_artifact(self) -> None:
        """Resume cùng byte hợp lệ; nội dung khác không được ghi đè."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.json"
            producer.write_once(path, b"original")
            producer.write_once(path, b"original")
            with self.assertRaises(ValueError):
                producer.write_once(path, b"changed")
            self.assertEqual(path.read_bytes(), b"original")

    def test_parent_checksum_cannot_be_bypassed(self) -> None:
        """Không chấp nhận manifest nguồn khác bằng việc đổi trạng thái PASS."""
        with patch.object(producer, "PARENT_SHA", "0" * 64):
            with self.assertRaisesRegex(ValueError, "checksum"):
                producer.sources()

    def test_output_cannot_overwrite_legacy_inputs(self) -> None:
        """Ngay cả lệnh tải cũng không được ghi vào thư mục giá W9."""
        with patch.object(producer, "sources", return_value=({}, pd.Series(dtype="datetime64[ns]"))):
            with self.assertRaisesRegex(ValueError, "legacy"):
                producer.prepare(producer.PARENT)

    def test_event_oracle_recomputes_cash_and_reference(self) -> None:
        """Kiểm thuật toán bằng mẫu lịch sử đã khóa, rồi sửa số để thử âm."""
        parent = producer.read(producer.PARENT / "manifest.json")
        item = parent["files"]["FPT"]
        frame = pd.read_csv(producer.PARENT / item["csv"]["file"], parse_dates=["Datetime"])
        records = json.loads(gzip.decompress((producer.PARENT / item["evidence"]["file"]).read_bytes()))["records"]
        events = producer.read(producer.PARENT / item["events"]["file"])["records"]
        samples = deepcopy(item["event_samples"])
        expected = {s["type"]: s["exright_date"] for s in samples}
        with patch.object(producer, "sample_event_dates", return_value=expected):
            producer.verify_samples("FPT", records, events, frame, samples)
            samples[0]["cash_dividend_vnd"] += 1
            with self.assertRaisesRegex(ValueError, "Reference"):
                producer.verify_samples("FPT", records, events, frame, samples)

    def test_missing_event_samples_do_not_pass(self) -> None:
        """Không có hai mẫu raw/adjusted thì gate mẫu phải dừng rõ lý do."""
        with patch.object(producer, "sample_event_dates", return_value={"stock_dividend": "2025-06-12", "cash_dividend": "2025-12-01"}):
            with self.assertRaisesRegex(ValueError, "Mẫu quyền"):
                producer.verify_samples("FPT", [], [], pd.DataFrame(), [])


if __name__ == "__main__":
    unittest.main()
