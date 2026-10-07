"""Kiểm lựa chọn calendar OOS và thu thập tiếp không ghi đè train."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
import requests

from core.pilot_readiness import select_cutoffs
from scripts.verify_execution_price_gate import download_bundle, sample_event_dates, fetch_paginated


class OosPilotReadinessTests(unittest.TestCase):
    """Không chọn lại pilot theo return hoặc dự báo có lợi."""

    def test_sample_events_follow_explicit_oos_bounds(self) -> None:
        events = [{"exrightDate": date, "eventTitleVi": title, "eventCode": "DIV", "valuePerShare": cash}
            for date, title, cash in (("2022-06-01", "cổ tức bằng cổ phiếu", 0),
                ("2022-07-01", "tiền", 1000), ("2024-06-01", "cổ tức bằng cổ phiếu", 0),
                ("2024-07-01", "tiền", 2000))]
        self.assertEqual(sample_event_dates(events)["stock_dividend"], "2022-06-01")
        self.assertEqual(sample_event_dates(events, "2023-01-01", "2024-12-31")["cash_dividend"], "2024-07-01")

    def test_existing_evidence_never_overwritten_by_fresh_download(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            sentinel = path / "manifest.json"
            sentinel.write_bytes(b"unchanged")
            with self.assertRaisesRegex(ValueError, "không ghi đè"):
                download_bundle(path, end="2024-12-31")
            self.assertEqual(sentinel.read_bytes(), b"unchanged")

    def test_future_range_is_rejected_before_network(self) -> None:
        with self.assertRaises(ValueError):
            download_bundle(Path("unused"), end="2025-01-01")

    def test_cutoff_selection_does_not_read_outcomes(self) -> None:
        schedule = pd.DataFrame({"as_of_date": pd.to_datetime(["2022-12-28", "2023-01-03", "2023-01-06", "2023-01-11"]),
            "eligible": [True, True, False, True]})
        with patch("core.pilot_readiness.build_verified_cycle_schedule", return_value=schedule):
            self.assertEqual(select_cutoffs(pd.DataFrame(), [], 2), ("2023-01-03", "2023-01-11"))
            with self.assertRaises(ValueError):
                select_cutoffs(pd.DataFrame(), [], 3)


if __name__ == "__main__":
    unittest.main()
