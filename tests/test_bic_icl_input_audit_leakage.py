"""Kiểm lịch revision không đọc payoff, không rò tương lai và không tự mở exposure."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

import numpy as np
import pandas as pd

from core.execution_prices import STOCK_SYMBOLS, normalise_vci_execution_prices
from scripts.audit_bic_icl_inputs import (
    DEPENDENCIES, EXPOSURE, EXPOSURE_ARCHIVE, EXPOSURE_REVIEW, EXPOSURE_V1, NAMESPACE, ROOT, build_audit, checksum,
    design_calendar, download_prices, exposure_inventory, namespace_path, read_exposure, source_path, verify_samples,
    write_exposure_review,
)
from core.historical_signals import digest


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
        value = read_exposure(ROOT, EXPOSURE_V1)
        self.assertEqual(value["status"], "UNVERIFIED")
        self.assertFalse(value["confirmation_allowed"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / EXPOSURE_V1
            path.parent.mkdir(parents=True)
            for field, replacement in (("status", "PASS"), ("confirmation_allowed", True)):
                changed = {**value, field: replacement}
                path.write_text(json.dumps(changed), encoding="utf-8")
                with self.assertRaises(ValueError):
                    read_exposure(root, EXPOSURE_V1)

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


class ExposureReviewTests(unittest.TestCase):
    """Khai báo được đối chiếu inventory; không mở release bằng cờ exposure."""

    def setUp(self) -> None:
        """Tạo snapshot local nhỏ, giữ nguyên lịch sử khai báo trong fixture."""
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.report = self.root / "outputs/backtest_result/fixture.json"
        self.write(self.report, {"test_points": [{"window_end": "2024-02-01", "decision": "LONG"}]})
        self.write(self.root / EXPOSURE_V1, json.loads((ROOT / EXPOSURE_V1).read_text(encoding="utf-8")))
        self.value = {"version": "bic_icl_v2_exposure_inventory_v2", "date": "2026-10-21", "status": "PASS",
            "basis": "PARTICIPANT_DECLARATION_AND_LOCAL_INVENTORY", "participant_declaration": "Không dùng outcome để tune.",
            "outcome_used_for_method_selection": False, "outcome_used_for_method_adjustment": False,
            "unseen_outcomes_proven": False, "confirmation_allowed": False, "interpretation": "Fixture theo phạm vi khai báo.",
            "previous_declaration": {"path": EXPOSURE_V1, "sha256": checksum(self.root / EXPOSURE_V1)}}
        self.refresh_review()

    def tearDown(self) -> None:
        """Dọn fixture, không sửa dữ liệu workspace."""
        self.directory.cleanup()

    def write(self, path: Path, value: object) -> None:
        """Ghi JSON UTF-8 hữu hạn vào fixture."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding="utf-8")

    def save_declaration(self) -> None:
        """Ghi khai báo hiện tại mà không tự sửa nội dung review."""
        self.write(self.root / EXPOSURE, self.value)

    def refresh_review(self) -> None:
        """Tái dựng inventory thật rồi bind checksum vào khai báo fixture."""
        for relative in (EXPOSURE_REVIEW, EXPOSURE_ARCHIVE):
            (self.root / relative).unlink(missing_ok=True)
        write_exposure_review(self.root)
        self.value["inventory_review"] = {"path": EXPOSURE_REVIEW, "sha256": checksum(self.root / EXPOSURE_REVIEW)}
        self.save_declaration()

    def test_declaration_and_inventory_pass_with_bounded_claim(self) -> None:
        """Không dùng outcome và không có query trái ngược cho PASS, không chứng minh chưa xem."""
        result = read_exposure(self.root)
        self.assertEqual(result["status"], "PASS")
        self.assertFalse(result["unseen_outcomes_proven"])
        self.assertFalse(result["confirmation_allowed"])

    def test_permission_only_cannot_resolve_unknown_use(self) -> None:
        """Quyền thực hiện không thay các khai báo còn chưa xác minh."""
        self.value.update(participant_declaration="Đã đủ quyền thực hiện.",
                          outcome_used_for_method_selection=None, outcome_used_for_method_adjustment=None)
        self.save_declaration()
        with self.assertRaises(ValueError):
            read_exposure(self.root)
        self.value["status"] = "UNVERIFIED"
        self.save_declaration()
        self.assertEqual(read_exposure(self.root)["status"], "UNVERIFIED")

    def test_exposed_and_false_independence_flags_reject_pass(self) -> None:
        """Chặn khai báo dùng outcome, cờ mở release, bool giả và chứng nhận chưa xem."""
        original = copy.deepcopy(self.value)
        for field, value in (("outcome_used_for_method_selection", True), ("confirmation_allowed", True),
                             ("unseen_outcomes_proven", True), ("outcome_used_for_method_adjustment", 0)):
            with self.subTest(field=field):
                self.value = {**original, field: value}
                self.save_declaration()
                with self.assertRaises(ValueError):
                    read_exposure(self.root)
        self.value = {**original, "outcome_used_for_method_selection": True, "status": "EXPOSED"}
        self.save_declaration()
        self.assertEqual(read_exposure(self.root)["status"], "EXPOSED")

    def test_real_query_trace_blocks_even_after_rehash(self) -> None:
        """Dấu vết query 2025 thật cần review thêm; băm lại không tự xóa mâu thuẫn."""
        for field in ("window_end", "as_of_date", "data_end"):
            self.value["status"] = "PASS"
            self.write(self.report, {"test_points": [{field: "2025-02-01", "decision": "LONG"}]})
            self.refresh_review()
            with self.assertRaises(ValueError):
                read_exposure(self.root)
            self.value["status"] = "UNVERIFIED"
            self.save_declaration()
            self.assertEqual(read_exposure(self.root)["status"], "UNVERIFIED")

    def test_mutated_source_and_empty_forged_inventory_fail(self) -> None:
        """Chặn sửa snapshot bằng băm lại receipt hoặc thay bằng inventory rỗng."""
        self.report.write_text("{}", encoding="utf-8")
        self.assertEqual(read_exposure(self.root)["status"], "PASS")
        with self.assertRaises(ValueError):
            write_exposure_review(self.root)
        path = self.root / EXPOSURE_REVIEW
        forged = json.loads(path.read_text(encoding="utf-8"))["payload"]
        archive = self.root / EXPOSURE_ARCHIVE
        with zipfile.ZipFile(archive, "w") as snapshot:
            snapshot.writestr(self.report.relative_to(self.root).as_posix(), b"{}")
        forged["archive"]["sha256"] = checksum(archive)
        self.write(path, {"payload": forged, "sha256": digest(forged)})
        self.value["inventory_review"]["sha256"] = checksum(path)
        self.save_declaration()
        with self.assertRaises(ValueError):
            read_exposure(self.root)
        forged.update(files={}, file_count=0)
        self.write(self.root / EXPOSURE_REVIEW, {"payload": forged, "sha256": digest(forged)})
        self.value["inventory_review"]["sha256"] = checksum(self.root / EXPOSURE_REVIEW)
        self.save_declaration()
        with self.assertRaises(ValueError):
            read_exposure(self.root)

    def test_live_ledger_append_keeps_snapshot_and_orphan_archive_recovers(self) -> None:
        """Ledger tăng sau lock vẫn replay được; archive complete trước receipt có thể phục hồi."""
        ledger = self.root / "outputs/oos_pilot/api_usage.json"
        self.write(ledger, {"invocations": []})
        self.refresh_review()
        original = checksum(self.root / EXPOSURE_ARCHIVE)
        (self.root / EXPOSURE_REVIEW).unlink()
        write_exposure_review(self.root)
        self.assertEqual(checksum(self.root / EXPOSURE_ARCHIVE), original)
        self.write(ledger, {"invocations": [{"window_end": "2026-11-02"}]})
        self.assertEqual(read_exposure(self.root)["status"], "PASS")
        with self.assertRaises(ValueError):
            write_exposure_review(self.root)
        archive = self.root / EXPOSURE_ARCHIVE
        archive.write_bytes(archive.read_bytes() + b"tamper")
        with self.assertRaises(ValueError):
            read_exposure(self.root)

    def test_previous_declaration_cannot_be_rewritten(self) -> None:
        """Khai báo mới giữ hash lịch sử; sửa lịch sử và băm lại vẫn không hợp lệ."""
        path = self.root / EXPOSURE_V1
        previous = json.loads(path.read_text(encoding="utf-8"))
        previous["status"] = "PASS"
        self.write(path, previous)
        self.value["previous_declaration"]["sha256"] = checksum(path)
        self.save_declaration()
        with self.assertRaises(ValueError):
            read_exposure(self.root)

    def test_metadata_and_post_lock_append_do_not_rewrite_snapshot(self) -> None:
        """Metadata lịch không là query; replay giữ phạm vi snapshot trước các file mới."""
        self.write(self.root / NAMESPACE / "input_audit.json", {"calendar": {"as_of_date": "2025-02-01"}})
        self.assertEqual(read_exposure(self.root)["status"], "PASS")
        self.write(self.root / "outputs/after_lock.json", {"window_end": "2026-11-02"})
        self.assertEqual(read_exposure(self.root)["status"], "PASS")
        self.assertEqual(exposure_inventory(self.root)["file_count"], 2)
        with self.assertRaises(ValueError):
            exposure_inventory(self.root, {"../escape.json": "0" * 64})

    def test_input_pass_does_not_release_confirmation(self) -> None:
        """Giá/lịch/exposure đủ chỉ mở gate đầu vào; thiếu lịch vẫn phải BLOCKED."""
        index = self.root / "data/historical/VNINDEX.csv"
        index.parent.mkdir(parents=True)
        index.write_text("Datetime\n2025-01-02\n", encoding="utf-8")
        prices = self.root / NAMESPACE / "inputs/execution_prices_2025"
        self.write(prices / "manifest.json", {})
        for relative in DEPENDENCIES:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# Dữ liệu giả\n", encoding="utf-8")
        manifest = {"files": {}, "calendar_sha256": checksum(index)}
        for calendar_status in ("PASS", "BLOCKED"):
            with patch("scripts.audit_bic_icl_inputs.verify_prices", return_value=(manifest, {}, {})), \
                    patch("scripts.audit_bic_icl_inputs.design_calendar", return_value={"status": calendar_status}):
                result = build_audit(prices, self.root)
            self.assertEqual(result["status"], calendar_status)
            self.assertEqual(result["input_eligible"], calendar_status == "PASS")
            self.assertFalse(result["confirmation_allowed"])
            self.assertTrue(result["pending_requirements"])


if __name__ == "__main__":
    unittest.main()
