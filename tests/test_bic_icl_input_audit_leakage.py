"""Kiểm lịch revision không đọc payoff, không rò tương lai và không tự mở exposure."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from core.execution_prices import STOCK_SYMBOLS, normalise_vci_execution_prices
from scripts.audit_bic_icl_inputs import (
    EXPOSURE, NAMESPACE, ROOT, design_calendar, download_prices, namespace_path, read_exposure, source_path, verify_samples,
)


class BicICLInputAuditTests(unittest.TestCase):
    """Giữ mẫu số, phase và quyền; quyền thực hiện không chứng minh chưa xem outcome."""

    def setUp(self) -> None:
        """Tạo dữ liệu tổng hợp đủ warm-up; không tải dữ liệu hoặc gọi API."""
        self.index = pd.DataFrame({"Datetime": pd.bdate_range("2021-01-01", "2025-12-31"),
            "Open": 100., "High": 102., "Low": 99., "Close": 101., "Reference": 101., "Volume": 1000})
        self.frames = {s: self.index.copy() for s in STOCK_SYMBOLS}
        self.events = {s: [] for s in STOCK_SYMBOLS}

    def design(self) -> dict:
        """Dựng lịch từ fixture hiện tại, không dùng nhãn."""
        return design_calendar(self.frames, self.events, self.index)

    def test_exact_ranks_and_native_json(self) -> None:
        """Chọn đúng tám hạng/quý, đủ 128; JSON không chứa scalar NumPy."""
        value = self.design()
        self.assertEqual(value["selected_count"], 128)
        self.assertEqual(value["status"], "PASS")
        self.assertFalse(value["is_execution_plan"])
        self.assertFalse(value["selection_uses_outcome"])
        for symbol in STOCK_SYMBOLS:
            rows = value["stocks"][symbol]["calendar"]
            for q in range(1, 5):
                pool = [r["as_of_date"] for r in rows if r["eligible"] and r["quarter"] == f"2025Q{q}"]
                self.assertEqual(value["stocks"][symbol]["quarters"][f"2025Q{q}"]["selected"],
                                 [pool[j * (len(pool) - 1) // 7] for j in range(8)])
        json.dumps(value, allow_nan=False)

    def test_horizon_quarter_and_nonoverlap(self) -> None:
        """Entry t+1/exit t+3; cycle trong quý, các khoảng giữ lệnh không giao nhau."""
        dates = pd.DatetimeIndex(self.index.Datetime)
        for points in self.design()["selected"].values():
            previous_exit = None
            for point in points:
                pos = dates.get_loc(pd.Timestamp(point["as_of_date"]))
                self.assertEqual(point["entry_date"], dates[pos + 1].strftime("%Y-%m-%d"))
                self.assertEqual(point["exit_date"], dates[pos + 3].strftime("%Y-%m-%d"))
                self.assertEqual(pd.Timestamp(point["exit_date"]).quarter, pd.Timestamp(point["as_of_date"]).quarter)
                if previous_exit:
                    self.assertGreater(point["entry_date"], previous_exit)
                previous_exit = point["exit_date"]

    def test_payoff_blind_ranking(self) -> None:
        """Thay Open hợp lệ làm thay payoff nhưng không được đổi lịch hoặc thứ hạng."""
        before = self.design()
        for frame in self.frames.values():
            frame["Open"] = 99.5
            frame["decision_action"] = "LONG"
        self.assertEqual(self.design(), before)

    def test_shortfall_blocks_without_lowering_target(self) -> None:
        """Không đủ tám ngày thì để quý rỗng và BLOCKED, không tự giảm mẫu."""
        self.frames["FPT"].loc[self.frames["FPT"].Datetime.dt.quarter == 1, "Volume"] = 0
        value = self.design()
        self.assertEqual(value["status"], "BLOCKED")
        self.assertIn("FPT:2025Q1", value["shortfalls"])
        self.assertEqual(value["stocks"]["FPT"]["quarters"]["2025Q1"]["selected"], [])
        self.assertEqual(value["stocks"]["FPT"]["quarters"]["2025Q1"]["target"], 8)

    def test_rights_entry_allowed_holding_rejected_without_reanchoring(self) -> None:
        """Quyền ở entry được phép, quyền sau entry bị loại mà không dịch phase."""
        before = self.design()
        first = before["selected"]["FPT"][0]
        self.events["FPT"] = [{"exrightDate": first["entry_date"]}]
        rows = {r["as_of_date"]: r for r in self.design()["stocks"]["FPT"]["calendar"]}
        self.assertTrue(rows[first["as_of_date"]]["eligible"])
        self.events["FPT"] = [{"exrightDate": first["exit_date"]}]
        after = self.design()
        row = next(r for r in after["stocks"]["FPT"]["calendar"] if r["as_of_date"] == first["as_of_date"])
        self.assertIn("CORPORATE_ACTION_DURING_HOLDING", row["reasons"])
        self.assertEqual(after["anchor"], before["anchor"])
        dates = pd.DatetimeIndex(self.index.Datetime)
        grid = set(dates[dates.year == 2025][::3].strftime("%Y-%m-%d"))
        self.assertTrue(all(p["as_of_date"] in grid for p in after["selected"]["FPT"]))

    def test_missing_execution_is_not_compressed(self) -> None:
        """Thiếu phiên thực thi không được nén lịch cổ phiếu để tạo cycle khác."""
        first = self.design()["selected"]["FPT"][0]
        self.frames["FPT"] = self.frames["FPT"].loc[self.frames["FPT"].Datetime != first["entry_date"]].copy()
        row = next(r for r in self.design()["stocks"]["FPT"]["calendar"] if r["as_of_date"] == first["as_of_date"])
        self.assertIn("EXECUTION_CALENDAR_MISMATCH", row["reasons"])

    def test_unannounced_reference_gap_excludes_cycle(self) -> None:
        """Reference đổi so Close trước vẫn là barrier khi event feed thiếu quyền."""
        first = self.design()["selected"]["FPT"][0]
        self.frames["FPT"].loc[self.frames["FPT"].Datetime == first["exit_date"], "Reference"] = 100.
        row = next(r for r in self.design()["stocks"]["FPT"]["calendar"] if r["as_of_date"] == first["as_of_date"])
        self.assertIn("CORPORATE_ACTION_DURING_HOLDING", row["reasons"])

    def test_future_append_invariance(self) -> None:
        """Giá/tin quyền sau năm xác nhận không được đổi lịch, kể cả giá tương lai lỗi."""
        before = self.design()
        extra = self.index.tail(1).copy()
        extra["Datetime"] = pd.Timestamp("2026-01-02")
        extra["Close"] = np.nan
        self.index = pd.concat([self.index, extra], ignore_index=True)
        for symbol in STOCK_SYMBOLS:
            self.frames[symbol] = pd.concat([self.frames[symbol], extra], ignore_index=True)
            self.events[symbol].append({"exrightDate": "2026-01-02"})
        self.assertEqual(self.design(), before)

    def test_exposure_cannot_be_promoted_by_execution_authorization(self) -> None:
        """Có quyền chạy không biến khai báo không chắc thành xác nhận chưa xem."""
        value = read_exposure()
        self.assertEqual(value["status"], "UNVERIFIED")
        self.assertFalse(value["confirmation_allowed"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / EXPOSURE
            path.parent.mkdir(parents=True)
            for field, replacement in (("status", "PASS"), ("confirmation_allowed", True)):
                changed = {**value, field: replacement}
                path.write_text(json.dumps(changed), encoding="utf-8")
                with self.assertRaises(ValueError):
                    read_exposure(root)

    def test_namespace_cannot_overwrite_legacy(self) -> None:
        """Cấm traversal sang nguồn W9 hoặc namespace cũ."""
        for path in (ROOT / "data/execution_prices_oos", ROOT / "outputs/bayesian_benchmark/improvement_v1",
                     ROOT / "outputs/bayesian_benchmark/bic_icl_v2/../improvement_v1"):
            with self.assertRaises(ValueError):
                namespace_path(path)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                source_path(Path(directory), {"file": "../escape.json", "sha256": "0" * 64})

    def test_completed_download_never_rewrites_or_calls_network(self) -> None:
        """Chạy lại nguồn complete chỉ verify, không đổi timestamp/hash hoặc tải lại."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prices = root / NAMESPACE / "inputs/execution_prices_2025"
            prices.mkdir(parents=True)
            manifest = prices / "manifest.json"
            original = b'{"price_gate":"PASS"}\n'
            manifest.write_bytes(original)
            with patch("scripts.audit_bic_icl_inputs.verify_prices") as verify, \
                    patch("scripts.audit_bic_icl_inputs.fetch_paginated") as network, \
                    patch("scripts.audit_bic_icl_inputs.write_json") as write:
                download_prices(prices, root)
            verify.assert_called_once_with(prices, root)
            network.assert_not_called()
            write.assert_not_called()
            self.assertEqual(manifest.read_bytes(), original)

    def test_sample_receipts_cannot_replace_rights_arithmetic(self) -> None:
        """Checksum/proof tự khai không thay phép đối chiếu quyền với record nguồn."""
        dates = ["2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07"]
        records = [{"ticker": "FPT", "tradingDate": d, "openPrice": 100000., "highestPrice": 105000.,
            "lowestPrice": 99000., "closePrice": 102000., "referencePrice": 102000.,
            "matchPrice": 102000., "totalMatchVolume": 1000} for d in dates]
        records[1]["referencePrice"], records[2]["referencePrice"] = 101000., 51000.
        events = [{"exrightDate": dates[1], "eventCode": "DIV", "valuePerShare": 1000., "eventTitleVi": "Tiền mặt"},
                  {"exrightDate": dates[2], "eventCode": "ISS", "exerciseRatio": 1., "eventTitleVi": "Cổ tức bằng cổ phiếu"}]
        frame = normalise_vci_execution_prices(records, "FPT", dates[0], dates[-1])
        samples = []
        for i, kind, cash, ratio in ((1, "cash_dividend", 1000., 0.), (2, "stock_dividend", 0., 1.)):
            quote = {label: {k: float(frame.iloc[pos][k]) / 2 for k in ("Open", "High", "Low", "Close")}
                     for label, pos in (("before", i - 1), ("exright", i))}
            samples.append({"symbol": "FPT", "type": kind, "exright_date": dates[i], "previous_date": dates[i - 1],
                "raw_before": records[i - 1], "raw_exright": records[i], "cash_dividend_vnd": cash,
                "stock_dividend_ratio": ratio, "theoretical_reference_vnd": (102000. - cash) / (1 + ratio),
                "reference_difference_vnd": 0., "raw_prefix_equals_extended": True,
                "prefix_request": [{"response_sha256": "0" * 64}], "quotes": {"VCI": quote, "KBS": quote}})
        verify_samples("FPT", {"event_samples": samples}, records, frame, events)
        changed = copy.deepcopy(samples)
        changed[0]["cash_dividend_vnd"] = 2000.
        with self.assertRaises(ValueError):
            verify_samples("FPT", {"event_samples": changed}, records, frame, events)


if __name__ == "__main__":
    unittest.main()
