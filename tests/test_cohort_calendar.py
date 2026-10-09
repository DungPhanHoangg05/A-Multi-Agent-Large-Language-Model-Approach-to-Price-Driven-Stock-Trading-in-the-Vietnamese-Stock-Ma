"""Lịch mẫu bốn mã: chọn theo ngày, tách exposure và giữ nguyên mẫu số sau lỗi."""

from copy import deepcopy
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from core.cohort_calendar import design_calendar, build_locked_calendar, _verify_files, _envelope, _read_locked_coverage
from core.execution_prices import STOCK_SYMBOLS
from core.historical_signals import digest
from prior_context_test_support import write_json


def coverage_fixture() -> dict:
    """Tạo lịch kiểm phương pháp; không chứa giá, tín hiệu hoặc nhãn kinh tế."""
    dates = pd.bdate_range("2023-01-02", "2024-12-31")
    rows = []
    for index, stamp in enumerate(dates):
        eligible = index + 3 < len(dates) and dates[min(index + 3, len(dates) - 1)].year == stamp.year
        rows.append({"as_of_date": stamp.strftime("%Y-%m-%d"),
            "entry_date": dates[index + 1].strftime("%Y-%m-%d") if index + 1 < len(dates) else None,
            "exit_date": dates[index + 3].strftime("%Y-%m-%d") if index + 3 < len(dates) else None,
            "year": int(stamp.year), "quarter": f"{stamp.year}Q{stamp.quarter}",
            "stock_warmup_rows": 1300 + index, "vnindex_warmup_rows": 1300 + index,
            "eligible": eligible, "reason": None if eligible else "CROSS_YEAR_EXECUTION",
            "reasons": [] if eligible else ["CROSS_YEAR_EXECUTION"], "legacy_step3": False,
            "regime": "BULL", "regime_state_sha256": "b" * 64, "proof_sha256": "a" * 64,
            "news": {"is_reliable": False}})
    return {"version": "oos_coverage_v1", "status": "PASS",
        "scope": {"start": "2023-01-01", "end": "2024-12-31", "is_execution_plan": False},
        "stocks": {symbol: {"calendar": deepcopy(rows)} for symbol in STOCK_SYMBOLS}}


class CohortCalendarTests(unittest.TestCase):
    """Kiểm thiết kế xác định và các giới hạn dữ liệu trước API."""

    def setUp(self) -> None:
        self.coverage = coverage_fixture()
        self.pilot = {symbol: [] for symbol in STOCK_SYMBOLS}

    def test_default_balanced_quarters_four_smoke_and_global_spacing(self) -> None:
        """Đủ 128 điểm chính khi dữ liệu cho phép; smoke riêng và spacing qua biên quý."""
        result = design_calendar(self.coverage, self.pilot)
        self.assertEqual(result["summary"], {"target_main": 128, "planned_main": 128,
                                          "planned_smoke": 4, "observed_pilot": 0})
        self.assertFalse(result["is_execution_plan"])
        dates = [r["as_of_date"] for r in self.coverage["stocks"]["FPT"]["calendar"]]
        for symbol in STOCK_SYMBOLS:
            smoke = result["smoke"]["symbol_cutoffs"][symbol]
            self.assertEqual(smoke, ["2023-01-02"])
            all_main = []
            for group in result["cohorts"].values():
                main = group["symbol_cutoffs"][symbol]
                self.assertEqual(len(main), 16)
                self.assertTrue(all(q["selected"] == 4 for q in group["by_symbol"][symbol]["quarters"].values()))
                all_main.extend(main)
            selected = sorted(all_main + smoke)
            positions = [dates.index(day) for day in selected]
            self.assertTrue(all(right - left >= 3 for left, right in zip(positions, positions[1:])))
            self.assertTrue(set(smoke).isdisjoint(all_main))
        self.assertEqual(result, design_calendar(self.coverage, self.pilot))

    def test_pilot_holding_embargo_shortfall_and_other_symbols_unchanged(self) -> None:
        """Pilot gần kín quý I gây thiếu mẫu FPT, không mượn quý khác để bù."""
        rows = self.coverage["stocks"]["FPT"]["calendar"]
        self.pilot["FPT"] = [r["as_of_date"] for r in rows if r["quarter"] == "2023Q1"][::3]
        result = design_calendar(self.coverage, self.pilot)
        stats = result["cohorts"]["development_2023"]["by_symbol"]["FPT"]
        self.assertEqual(stats["quarters"]["2023Q1"]["selected"], 0)
        self.assertEqual(stats["shortfall"], 4)
        self.assertEqual(result["summary"]["planned_main"], 124)
        self.assertTrue(result["smoke"]["symbol_cutoffs"]["FPT"][0] >= "2023-04-01")
        for symbol in ("VNM", "VCB", "MWG"):
            self.assertEqual(result["cohorts"]["development_2023"]["by_symbol"][symbol]["selected"], 16)
        by_date = {r["as_of_date"]: r for r in rows}
        main = result["cohorts"]["development_2023"]["symbol_cutoffs"]["FPT"]
        for day in main + result["smoke"]["symbol_cutoffs"]["FPT"]:
            query = by_date[day]
            for old_day in self.pilot["FPT"]:
                old = by_date[old_day]
                self.assertFalse(query["entry_date"] <= old["exit_date"] and query["exit_date"] >= old["entry_date"])

    def test_ineligible_grid_slot_does_not_shift_anchor_or_lose_spacing(self) -> None:
        """Lọc quyền trước khi chọn đều, giữ phase grid của toàn bộ năm."""
        for symbol in STOCK_SYMBOLS:
            row = self.coverage["stocks"][symbol]["calendar"][6]
            row.update(eligible=False, reason="CORPORATE_ACTION_DURING_HOLDING",
                       reasons=["CORPORATE_ACTION_DURING_HOLDING"])
        result = design_calendar(self.coverage, self.pilot)
        rows = self.coverage["stocks"]["FPT"]["calendar"]
        dates_2023 = [r["as_of_date"] for r in rows if r["year"] == 2023]
        for main in result["cohorts"]["development_2023"]["symbol_cutoffs"].values():
            self.assertNotIn(rows[6]["as_of_date"], main)
            self.assertTrue(all(dates_2023.index(day) % 3 == 0 for day in main))

    def test_invalid_target_exposure_schema_calendar_and_year_fail(self) -> None:
        """Thiếu mã, pilot holdout, schema mở rộng và lịch sai phải dừng."""
        for target in (0, 21, True, 2.5):
            with self.subTest(target=target), self.assertRaises(ValueError):
                design_calendar(self.coverage, self.pilot, points_per_quarter=target)
        for change in ("missing_symbol", "pilot_holdout", "duplicate", "bad_exit", "outcome"):
            coverage, pilot = deepcopy(self.coverage), deepcopy(self.pilot)
            if change == "missing_symbol":
                pilot.pop("VNM")
            elif change == "pilot_holdout":
                pilot["FPT"] = ["2024-01-02"]
            elif change == "duplicate":
                coverage["stocks"]["FPT"]["calendar"].insert(0, deepcopy(coverage["stocks"]["FPT"]["calendar"][0]))
            elif change == "bad_exit":
                coverage["stocks"]["FPT"]["calendar"][0]["exit_date"] = "2024-01-02"
            else:
                coverage["stocks"]["FPT"]["calendar"][0]["outcome"] = {"net_return": 1.}
            with self.subTest(change=change), self.assertRaises(ValueError):
                design_calendar(coverage, pilot)

    def test_empty_development_fails_instead_of_smoke_from_holdout(self) -> None:
        """Không lấy smoke ở 2024 khi development không còn điểm hợp lệ."""
        for row in self.coverage["stocks"]["FPT"]["calendar"]:
            if row["year"] == 2023:
                row.update(eligible=False, reason="CORPORATE_ACTION_DURING_HOLDING", reasons=["CORPORATE_ACTION_DURING_HOLDING"])
        with self.assertRaisesRegex(ValueError, "smoke"):
            design_calendar(self.coverage, self.pilot)

    def test_source_hash_containment_strict_json_and_output_never_overwrites_input(self) -> None:
        """Nguồn/JSON hỏng bị chặn trước adapter hoặc credential."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "source.json"
            write_json(path, {"payload": self.coverage, "sha256": digest(self.coverage)})
            _verify_files({"source.json": hashlib.sha256(path.read_bytes()).hexdigest()}, root)
            self.assertEqual(_envelope(path), self.coverage)
            for name, sha in (("source.json", "0" * 64), ("../outside", "0" * 64), (".env", "0" * 64)):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    _verify_files({name: sha}, root)
            with patch("core.pilot_readiness.verify_inputs", side_effect=AssertionError("Cấm adapter")):
                for destination in (path, root / "data/price.json"):
                    with self.assertRaises(ValueError):
                        build_locked_calendar(path, destination, root=root)
            path.write_text('{"payload":1,"payload":2,"sha256":"bad"}',encoding="utf-8")
            with self.assertRaises(ValueError):
                _envelope(path)
            # Mô phỏng thay byte giữa parse và kiểm nguồn; không được ghim hash mới.
            coverage = {**self.coverage, "sources": {}, "code_sha256": {}}
            write_json(path, {"payload": coverage, "sha256": digest(coverage)})
            def changed_during_read(_path: Path) -> dict:
                """Thay byte sau khi đã ghim checksum đầu vào."""
                path.write_bytes(path.read_bytes() + b"\n")
                return coverage
            with patch("core.cohort_calendar._envelope", side_effect=changed_during_read), self.assertRaises(ValueError):
                _read_locked_coverage("source.json", root)

    def test_cli_design_is_separate_from_execute_and_never_reads_key(self) -> None:
        """CLI tạo lịch draft trước nhánh chạy/verify và không đọc .env."""
        from scripts import run_bayesian_ablation as cli
        result = design_calendar(self.coverage, self.pilot)
        with patch("sys.argv", ["runner", "--design-calendar"]), \
             patch("core.cohort_calendar.build_locked_calendar", return_value=result) as build, \
             patch.object(cli, "dotenv_values", side_effect=AssertionError("Cấm key")), \
             patch.object(cli, "verify_inputs", side_effect=AssertionError("Sai luồng")), \
             patch.object(cli, "execute_cohort", side_effect=AssertionError("Cấm chạy")), redirect_stdout(StringIO()):
            cli.main()
        build.assert_called_once()
        for arguments in (("--design-calendar", "--run"), ("--design-calendar", "--plan", "unused.json"),
                          ("--design-calendar", "--symbol", "FPT"), ("--points-per-quarter", "5"),
                          ("--calendar-output", "unused.json")):
            with self.subTest(arguments=arguments), patch("sys.argv", ["runner", *arguments]), \
                 redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                cli.main()


if __name__ == "__main__":
    unittest.main()
