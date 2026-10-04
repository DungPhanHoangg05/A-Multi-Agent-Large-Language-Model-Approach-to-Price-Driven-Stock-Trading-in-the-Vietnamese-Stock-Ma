"""Kiểm QA lịch đầy đủ, kiểu JSON và bằng chứng bộ đọc trước phát hành."""

import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

import numpy as np

from core.bayesian_memory import DEFAULT_DATA_DIR, atomic_write_json, read_json
from core.execution_prices import build_verified_cycle_schedule, load_verified_execution_data
from core.historical_outcomes import HistoricalOutcomeGenerator
from core.historical_signals import digest
from scripts.audit_historical_memory import summarize_records, validate_native
from scripts.publish_historical_memory import freeze_report_compat
from scripts.run_paced_historical_memory import REPORT_PARSE_FILE


class HistoricalMemoryAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Tạo record từ giá thật; tín hiệu thử nghiệm chỉ giữ trong bộ nhớ test."""
        cls.records, cls.points = [], []
        signals = {"trend": "BULLISH", "pattern": "NEUTRAL", "alpha_consensus": "NEUTRAL",
                   "indicator_consensus": "NEUTRAL", "sentiment": "NEUTRAL"}
        for symbol in ("FPT", "MWG", "VCB", "VNM"):
            frame, events = load_verified_execution_data(DEFAULT_DATA_DIR, symbol)
            schedule = build_verified_cycle_schedule(frame, events)
            schedule = schedule.loc[schedule["eligible"]].head(76).copy()
            for key in ("as_of_date", "entry_date", "exit_date"):
                schedule[key] = schedule[key].dt.strftime("%Y-%m-%d")
            generator = HistoricalOutcomeGenerator(lambda code: (frame, events))
            for cycle in schedule[["as_of_date", "entry_date", "exit_date"]].to_dict("records"):
                point = {"symbol": symbol, **cycle}
                cls.points.append(point)
                cls.records.append({"episode_id": f"{symbol}:{cycle['as_of_date']}", **point,
                    "regime": "BULL", "agent_signals": copy.deepcopy(signals),
                    "outcome": generator.generate(**point, agent_signals=signals, settled_as_of="2022-12-31")})

    def test_coverage_keeps_warmup_years_explicit(self):
        summary = summarize_records(self.records, self.points)
        self.assertEqual(summary["completed"], 304)
        self.assertEqual(summary["by_year"]["2018"], 0)
        self.assertEqual(summary["by_year"]["2019"], 0)
        self.assertEqual(summary["by_symbol"], {symbol: 76 for symbol in ("FPT", "MWG", "VCB", "VNM")})
        self.assertEqual(sum(summary["economic_labels"].values()), 304)

    def test_missing_valid_episode_still_fails_full_schedule(self):
        with self.assertRaisesRegex(ValueError, "lịch"):
            summarize_records(self.records[:-1], self.points)

    def test_duplicate_id_is_not_hidden_by_counts(self):
        records = copy.deepcopy(self.records)
        records[-1]["episode_id"] = records[0]["episode_id"]
        with self.assertRaisesRegex(ValueError, "trùng"):
            summarize_records(records, self.points)

    def test_numpy_and_nonfinite_values_are_rejected_before_serialization(self):
        for value in (np.bool_(True), np.float64(1.0), np.int64(1), float("nan"), float("inf")):
            with self.subTest(value=str(value)), self.assertRaises(ValueError):
                validate_native({"nested": [value]})

    def test_parser_source_is_frozen_and_bad_evidence_rejected(self):
        source = Path(__file__).resolve().parents[1] / "scripts/run_paced_historical_memory.py"
        checksum = hashlib.sha256(source.read_bytes()).hexdigest()
        entry = {"report_sha256": digest("Hướng xu: Tăng"), "signal": "BULLISH",
                 "parser_sha256": checksum, "rule": "abbreviated_trend_direction_v1"}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = {"format_version": 1, "entries": [entry]}
            atomic_write_json(root / REPORT_PARSE_FILE, {"payload": payload, "sha256": digest(payload)})
            receipt = freeze_report_compat(root, root / "bank.json")
            frozen = root / receipt["parser_sources"][checksum]
            self.assertEqual(hashlib.sha256(frozen.read_bytes()).hexdigest(), checksum)
            self.assertEqual(read_json(root / "bank.parse_compat.json")["payload"], payload)
            atomic_write_json(root / REPORT_PARSE_FILE, {"payload": payload, "sha256": "wrong"})
            with self.assertRaisesRegex(ValueError, "checksum"):
                freeze_report_compat(root, root / "bank.json")


if __name__ == "__main__":
    unittest.main()
