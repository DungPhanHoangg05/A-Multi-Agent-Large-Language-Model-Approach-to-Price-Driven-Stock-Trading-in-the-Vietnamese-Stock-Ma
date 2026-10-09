"""Coverage không được biến lỗi PIT thành loại ngày hoặc dùng outcome để chọn."""

from contextlib import redirect_stdout
from io import StringIO
import unittest
from unittest.mock import patch

from core.oos_coverage import audit_oos_coverage, build_oos_calendar
from prior_context_test_support import ContextFixture, write_json


class OOSCoverageLeakageTests(unittest.TestCase):
    """Dùng adapter thật, model cố định và tin có timestamp."""

    def setUp(self) -> None:
        self.fx = ContextFixture()
        self.addCleanup(self.fx.close)

    def adapter(self):
        """Cấp provider train cố định trước mọi cutoff audit."""
        return self.fx.adapter(provider_mode="fixed_train_oos", frozen_artifact_path="model/fixed.json",
                               freeze_as_of_date=self.fx.day(620))

    def audit(self, adapter) -> dict:
        """Bốn điểm đã khóa, không làm phát sinh output file."""
        with redirect_stdout(StringIO()):
            return audit_oos_coverage(adapter, self.fx.vnindex, start=self.fx.day(640), end=self.fx.day(640))

    def test_future_undated_news_filtered_and_sparse_neutral_keeps_calendar(self) -> None:
        """Tin tương lai/không ngày không tăng độ tin cậy tại cutoff."""
        articles = [{"date_parsed": date, "title": f"Tin {index}", "url": f"https://example.test/{index}",
                     "label": "positive", "numeric_score": .8, "confidence": .9}
                    for index, date in enumerate((self.fx.day(640), self.fx.day(641), None, self.fx.day(0)))]
        for symbol in self.fx.frame:
            write_json(self.fx.root / f"run/inputs/news/{symbol}.json", {"symbol": symbol, "scored_articles": articles})
        result = self.audit(self.adapter())
        for stock in result["stocks"].values():
            row = stock["calendar"][0]
            self.assertTrue(row["eligible"])
            self.assertEqual(row["news"]["visible_count"], 1)
            self.assertEqual(row["news"]["excluded_counts"], {"undated": 1, "future": 1, "outside_window": 1})
            self.assertFalse(row["news"]["is_reliable"])

    def test_corrupt_source_and_temporal_violation_stop_entire_audit(self) -> None:
        """Lỗi nguồn/leakage phải được ném ra thay vì âm thầm đổi ngày chọn."""
        adapter = self.adapter()
        with patch.object(adapter, "prepare", side_effect=ValueError("Rò rỉ tương lai")), \
             self.assertRaisesRegex(ValueError, "Rò rỉ"):
            self.audit(adapter)
        path = self.fx.root / "model/fixed.json"
        path.write_bytes(path.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "checksum"):
            self.audit(adapter)

    def test_eligibility_invariant_to_future_prices_when_execution_remains_valid(self) -> None:
        """Giá/mức lợi nhuận tương lai không xếp hạng hoặc thay đổi ngày đủ điều kiện."""
        frame = self.fx.frame["FPT"].copy()
        original = build_oos_calendar(frame, [], self.fx.vnindex, start=self.fx.day(640), end=self.fx.day(645))
        future = frame.Datetime > self.fx.day(645)
        frame.loc[future, ["Open", "High", "Low", "Close"]] *= 2
        # Giữ tính liên tục Reference để không tạo quyền giả khi đổi mức giá.
        frame["Reference"] = frame.Close.shift().fillna(frame.Close.iloc[0])
        changed = build_oos_calendar(frame, [], self.fx.vnindex, start=self.fx.day(640), end=self.fx.day(645))
        self.assertEqual(original, changed)


if __name__ == "__main__":
    unittest.main()
