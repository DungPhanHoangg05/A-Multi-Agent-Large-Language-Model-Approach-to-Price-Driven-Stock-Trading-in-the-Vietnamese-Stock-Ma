"""Mẫu chính chỉ phụ thuộc ngày/eligibility; không xem outcome/forecast holdout."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from core.cohort_calendar import design_calendar
from core.execution_prices import STOCK_SYMBOLS
from test_cohort_calendar import coverage_fixture


class CohortCalendarLeakageTests(unittest.TestCase):
    """Không xếp hạng bằng regime/tin hoặc bù ngày lỗi sau API."""

    def test_selection_invariant_to_regime_news_and_legacy_grid(self) -> None:
        """Các trường mô tả sau chọn không được thay ngày smoke hoặc mẫu chính."""
        coverage = coverage_fixture()
        pilot = {symbol: [] for symbol in STOCK_SYMBOLS}
        original = design_calendar(coverage, pilot)
        for stock in coverage["stocks"].values():
            for row in stock["calendar"]:
                row.update(regime="BEAR", legacy_step3=True, news={"is_reliable": True})
        changed = design_calendar(coverage, pilot)
        self.assertEqual(original["smoke"], changed["smoke"])
        for split in original["cohorts"]:
            self.assertEqual(original["cohorts"][split]["symbol_cutoffs"], changed["cohorts"][split]["symbol_cutoffs"])

    def test_changing_development_eligibility_does_not_reselect_holdout(self) -> None:
        """Tách hai năm: calendar 2024 không thích nghi theo dữ liệu development."""
        coverage = coverage_fixture()
        pilot = {symbol: [] for symbol in STOCK_SYMBOLS}
        original = design_calendar(coverage, pilot)
        for stock in coverage["stocks"].values():
            for row in stock["calendar"][:12]:
                row.update(eligible=False, reason="NO_MATCHED_VOLUME_AT_EXECUTION", reasons=["NO_MATCHED_VOLUME_AT_EXECUTION"])
        changed = design_calendar(coverage, pilot)
        self.assertEqual(original["cohorts"]["holdout_2024"], changed["cohorts"]["holdout_2024"])

    def test_pure_design_never_calls_evaluator_llm_or_network_and_has_no_replacement(self) -> None:
        """Chọn trước API; kết quả chạy không phải đầu vào của bộ chọn lịch."""
        with patch("core.backtest_engine.compute_round_trip_net_return", side_effect=AssertionError("Cấm outcome")), \
             patch("utils.historical_api._invoke_with_retry", side_effect=AssertionError("Cấm LLM")), \
             patch("socket.socket.connect", side_effect=AssertionError("Cấm mạng")):
            result = design_calendar(coverage_fixture(), {symbol: [] for symbol in STOCK_SYMBOLS})
        self.assertFalse(result["selection"]["replacement_after_failure"])
        self.assertFalse(result["selection"]["selection_uses_outcome_or_regime_or_news"])
        self.assertEqual(result["status"], "DRAFT_PENDING_QUOTA_AND_INPUT_LOCK")


if __name__ == "__main__":
    unittest.main()
