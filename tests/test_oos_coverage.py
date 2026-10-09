"""Đối soát coverage, lịch ngày và artifact runtime; không API hoặc nguồn thật."""

from copy import deepcopy
from contextlib import redirect_stdout
from io import StringIO
import json
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from core.historical_signals import digest
from core.oos_coverage import audit_oos_coverage, build_oos_calendar, save_coverage
from core.regime_detector import MarketRegimeDetector
from prior_context_test_support import ContextFixture


def calendar_frame() -> pd.DataFrame:
    """Lịch có đủ warm-up, cuối tuần và ranh giới hai năm."""
    return pd.DataFrame({"Datetime": pd.bdate_range(end="2024-01-12", periods=620),
        "Open": 100., "High": 102., "Low": 99., "Close": 101., "Reference": 101., "Volume": 1000})


class OOSCalendarTests(unittest.TestCase):
    """Lọc thực thi theo lịch, không theo lợi nhuận tương lai."""

    def setUp(self) -> None:
        self.frame = calendar_frame()

    def rows(self, frame: pd.DataFrame | None = None, events: list[dict] | None = None,
             start: str = "2023-12-20", end: str = "2024-01-12") -> list[dict]:
        """Chạy bộ lịch trên nguồn xác định."""
        return build_oos_calendar(self.frame if frame is None else frame, events or [],
                                  self.frame, start=start, end=end)

    def test_daily_denominator_legacy_anchor_and_year_boundary(self) -> None:
        """Mọi phiên là ứng viên; năm phát triển không mượn giá thoát năm holdout."""
        rows = self.rows()
        self.assertEqual(len(rows), len(pd.bdate_range("2023-12-20", "2024-01-12")))
        by_date = {r["as_of_date"]: r for r in rows}
        for cutoff in ("2023-12-27", "2023-12-28", "2023-12-29"):
            self.assertEqual(by_date[cutoff]["reason"], "CROSS_YEAR_EXECUTION")
        self.assertEqual(by_date["2024-01-05"]["entry_date"], "2024-01-08")
        self.assertEqual(by_date["2024-01-05"]["exit_date"], "2024-01-10")
        self.assertEqual(by_date["2024-01-12"]["reason"], "EXIT_OUTSIDE_CALENDAR")
        self.assertTrue(by_date["2024-01-05"]["eligible"])
        for row in rows:
            position = self.frame.Datetime.searchsorted(row["as_of_date"])
            self.assertEqual(row["legacy_step3"], position >= 599 and position < 617 and (position - 599) % 3 == 0)

    def test_exact_600_warmup(self) -> None:
        """599 nến bị loại, đúng 600 nến được giữ nếu còn đủ ba phiên."""
        rows = self.rows(start=self.frame.Datetime.iloc[598].strftime("%Y-%m-%d"),
                         end=self.frame.Datetime.iloc[599].strftime("%Y-%m-%d"))
        self.assertEqual(rows[0]["reason"], "WARMUP_600")
        self.assertEqual(rows[0]["stock_warmup_rows"], 599)
        self.assertTrue(rows[1]["eligible"])

    def test_missing_stock_cutoff_and_holding_session(self) -> None:
        """Thiếu ngày không được nén lịch sang phiên cổ phiếu khác."""
        frame = self.frame[self.frame.Datetime != "2024-01-09"].reset_index(drop=True)
        rows = {r["as_of_date"]: r for r in self.rows(frame)}
        self.assertEqual(rows["2024-01-09"]["reason"], "CUTOFF_NOT_IN_STOCK")
        self.assertEqual(rows["2024-01-05"]["reason"], "EXECUTION_CALENDAR_MISMATCH")

    def test_rights_on_entry_allowed_holding_blocked_volume_priority(self) -> None:
        """Quyền ở entry được phép; primary reason không đếm trùng volume và quyền."""
        events = [{"exrightDate": "2024-01-08"}]
        rows = {r["as_of_date"]: r for r in self.rows(events=events)}
        self.assertTrue(rows["2024-01-05"]["eligible"])
        self.assertEqual(rows["2024-01-04"]["reason"], "CORPORATE_ACTION_DURING_HOLDING")
        frame = self.frame.copy()
        frame.loc[frame.Datetime == "2024-01-08", "Volume"] = 0
        row = {r["as_of_date"]: r for r in self.rows(frame, events)}["2024-01-04"]
        self.assertEqual(row["reason"], "NO_MATCHED_VOLUME_AT_EXECUTION")
        self.assertIn("CORPORATE_ACTION_DURING_HOLDING", row["reasons"])

    def test_empty_scope_invalid_data_and_reference_gap_fail_or_exclude(self) -> None:
        """Không bỏ qua nguồn hỏng; khoảng tham chiếu giá được coi là ngày quyền."""
        with self.assertRaises(ValueError):
            self.rows(start="2025-01-01", end="2025-02-01")
        with self.assertRaises(ValueError):
            self.rows(start="2024-02-01", end="2024-01-01")
        broken = self.frame.copy()
        broken.loc[610, "Open"] = np.nan
        with self.assertRaises(ValueError):
            self.rows(broken)
        changed = self.frame.copy()
        changed.loc[changed.Datetime == "2024-01-09", "Reference"] = 99.
        rows = {r["as_of_date"]: r for r in self.rows(changed)}
        self.assertEqual(rows["2024-01-05"]["reason"], "CORPORATE_ACTION_DURING_HOLDING")


class OOSCoverageTests(unittest.TestCase):
    """Adapter production xác minh từng điểm trong repo fixture có checksum."""

    def setUp(self) -> None:
        self.fx = ContextFixture()
        self.addCleanup(self.fx.close)
        self.adapter = self.fx.adapter(provider_mode="fixed_train_oos",
            frozen_artifact_path="model/fixed.json", freeze_as_of_date=self.fx.day(620))

    def audit(self, **kwargs) -> dict:
        """Audit tám ứng viên mỗi mã, không cần archive hay tin live."""
        with redirect_stdout(StringIO()):
            return audit_oos_coverage(self.adapter, self.fx.vnindex,
                start=self.fx.day(640), end=self.fx.day(647), **kwargs)

    def test_all_dates_verified_counters_native_json_and_regime_copy(self) -> None:
        """Đối soát từng nhóm, tin thiếu là neutral chứ không mất chu kỳ."""
        with patch.object(self.adapter, "prepare", wraps=self.adapter.prepare) as prepare, \
             patch.object(MarketRegimeDetector, "fit", side_effect=AssertionError("Cấm fit")), \
             patch("socket.socket.connect", side_effect=AssertionError("Cấm mạng")), \
             patch("dotenv.load_dotenv", side_effect=AssertionError("Cấm env")), \
             patch("utils.historical_api._invoke_with_retry", side_effect=AssertionError("Cấm LLM")), \
             patch("core.backtest_engine.compute_round_trip_net_return", side_effect=AssertionError("Cấm outcome")):
            payload = self.audit()
        self.assertEqual(prepare.call_count, 32)
        self.assertEqual(payload["summary"]["eligible"], 32)
        self.assertEqual(payload["summary"]["eligible_news_neutral"], 32)
        self.assertFalse(payload["scope"]["is_execution_plan"])
        for stock in payload["stocks"].values():
            summary = stock["summary"]
            self.assertEqual(summary["candidates"], summary["eligible"] + summary["excluded"])
            for field in ("year", "quarter", "regime"):
                self.assertEqual(sum(g["candidates"] for g in stock["groups"][field].values()), 8)
            self.assertTrue(all(row["proof_sha256"] for row in stock["calendar"]))
        json.dumps(payload, allow_nan=False)
        with redirect_stdout(StringIO()):
            point = self.adapter.prepare("VNM", self.fx.day(640))
        state = point.market_regime
        state["regime_name"] = "sửa bản sao"
        self.assertNotEqual(state, point.market_regime)

    def test_save_idempotent_conflict_containment_and_changed_source(self) -> None:
        """Đích runtime an toàn; giữ byte cũ và phát hiện nguồn đổi trước ghi."""
        payload = self.audit()
        path = self.fx.root / "outputs/bayesian_benchmark/coverage.json"
        save_coverage(payload, path, root=self.fx.root)
        before = path.stat().st_mtime_ns
        save_coverage(payload, path, root=self.fx.root)
        self.assertEqual(before, path.stat().st_mtime_ns)
        self.assertEqual(json.loads(path.read_text("utf-8"))["sha256"], digest(payload))
        changed = deepcopy(payload)
        changed["scope"]["end"] = self.fx.day(649)
        with self.assertRaisesRegex(ValueError, "identity"):
            save_coverage(changed, path, root=self.fx.root)
        with self.assertRaises(ValueError):
            save_coverage(payload, self.fx.root / "data/manifest.json", root=self.fx.root)
        source = self.fx.root / "model/fixed.json"
        source.write_bytes(source.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "Nguồn thay đổi"):
            save_coverage(payload, path, root=self.fx.root)

    def test_cli_coverage_dispatch_blocks_download_and_legacy_output(self) -> None:
        """CLI audit không tải lại hoặc chạy gate train nhầm phạm vi."""
        from scripts import verify_execution_price_gate as cli
        for arguments in (("--oos-coverage", "--download"), ("--oos-coverage", "--verify-only"),
                          ("--oos-coverage", "--start", "2023-01-01"),
                          ("--coverage-output", "unused.json")):
            with self.subTest(arguments=arguments), patch("sys.argv", ["audit", *arguments]), \
                 redirect_stdout(StringIO()), self.assertRaises(SystemExit):
                cli.main()
        payload = self.audit()
        with patch("sys.argv", ["audit", "--oos-coverage"]), \
             patch("core.oos_coverage.audit_locked_oos", return_value=payload) as audit, \
             patch("core.oos_coverage.save_coverage") as save, \
             patch.object(cli, "verify_bundle", side_effect=AssertionError("Sai gate")), \
             patch.object(cli, "download_bundle", side_effect=AssertionError("Cấm tải")), redirect_stdout(StringIO()):
            cli.main()
        audit.assert_called_once()
        save.assert_called_once()

    def test_cli_stock_choices_match_four_actual_sources(self) -> None:
        """VNM được parser nhận; HPG ngoài bộ bốn mã bị chặn trước execute."""
        from scripts import run_bayesian_ablation as cli
        class Parsed(Exception):
            """Dừng ngay sau parser để không đọc input hoặc key."""
        with patch("sys.argv", ["runner", "--plan", "unused.json", "--symbol", "VNM"]), \
             patch.object(cli, "execute_cohort", side_effect=Parsed), self.assertRaises(Parsed):
            cli.main()
        with patch("sys.argv", ["runner", "--symbol", "HPG"]), self.assertRaises(SystemExit):
            cli.main()


if __name__ == "__main__":
    unittest.main()
