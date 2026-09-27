"""Kiểm chứng giao dịch, schema và tính nguyên tử của kho lịch sử."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from core.backtest_engine import compute_round_trip_net_return
from core.bayesian_memory import DEFAULT_DATA_DIR, HistoricalMemory, validate_historical_task_record
from core.execution_prices import build_verified_cycle_schedule, execution_prices_for_cycle, load_verified_execution_data


class HistoricalMemoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame, cls.events = load_verified_execution_data(DEFAULT_DATA_DIR, "FPT")
        schedule = build_verified_cycle_schedule(cls.frame, cls.events)
        cls.cycles = schedule.loc[schedule["eligible"]].iloc[:3]

    def record(self, index=0):
        cycle = self.cycles.iloc[index]
        dates = {key: cycle[key].strftime("%Y-%m-%d") for key in ("as_of_date", "entry_date", "exit_date")}
        entry, exit_close = execution_prices_for_cycle(self.frame, self.events, **dates)
        net = float(100 * compute_round_trip_net_return(entry, exit_close))
        return {"episode_id": f"FPT:{dates['as_of_date']}", "symbol": "FPT", **dates,
                "regime": "BULL", "agent_signals": {"trend": "BULLISH", "pattern": "NEUTRAL",
                    "alpha_consensus": "NEUTRAL", "indicator_consensus": "BEARISH", "sentiment": "NEUTRAL"},
                "outcome": {"actual_direction": "UP" if net > 0 else "DOWN", "net_return_pct": net,
                    "was_bull_trap": bool(net <= 0), "result": "WIN_IF_LONG" if net > 0 else "LOSS_IF_LONG"}}

    def memory(self):
        return HistoricalMemory(lambda symbol: (self.frame.copy(), copy.deepcopy(self.events)))

    def test_verified_prices_and_default_loader(self):
        record = self.record()
        validate_historical_task_record(record, self.frame, self.events)
        memory = HistoricalMemory()
        memory.add(record)
        self.assertEqual(memory.records, [record])

    def test_save_load_round_trip_and_defensive_copy(self):
        memory = self.memory()
        record = self.record()
        memory.add(record)
        record["agent_signals"]["trend"] = "GIẢM"
        detached = memory.records
        detached.clear()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.json"
            memory.save(path)
            loaded = self.memory()
            loaded.load(path)
            self.assertEqual(loaded.records, [self.record()])

    def test_invalid_schema_native_types_and_dates(self):
        mutations = [lambda r: r.update(extra=True), lambda r: r.pop("regime"),
                     lambda r: r.update(symbol="VNINDEX"), lambda r: r.update(regime="UNKNOWN"),
                     lambda r: r.update(as_of_date="2020-02-30"), lambda r: r.update(as_of_date="20200601"),
                     lambda r: r["agent_signals"].update(trend="  "),
                     lambda r: r["agent_signals"].pop("sentiment"),
                     lambda r: r["outcome"].update(net_return_pct=float("nan")),
                     lambda r: r["outcome"].update(net_return_pct=np.float64(1)),
                     lambda r: r["outcome"].update(net_return_pct=True),
                     lambda r: r["outcome"].update(actual_direction=np.str_("UP")),
                     lambda r: r["outcome"].update(was_bull_trap=np.bool_(False))]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                record = self.record()
                mutate(record)
                with self.assertRaises(ValueError):
                    self.memory().add(record)

    def test_economic_inconsistency_rejected(self):
        for field, value in [("net_return_pct", 999), ("actual_direction", "UNKNOWN"),
                             ("result", "UNKNOWN"), ("was_bull_trap", not self.record()["outcome"]["was_bull_trap"])]:
            with self.subTest(field=field):
                record = self.record()
                record["outcome"][field] = value
                with self.assertRaises(ValueError):
                    self.memory().add(record)

    def test_weekend_and_wrong_holding_period_rejected(self):
        for dates in [{"entry_date": "2020-05-31"}, {"exit_date": self.record(1)["exit_date"]},
                      {"as_of_date": self.record()["exit_date"]}]:
            with self.subTest(dates=dates):
                record = self.record()
                record.update(dates)
                with self.assertRaises(ValueError):
                    self.memory().add(record)

    def test_duplicate_id_or_point_does_not_mutate(self):
        memory = self.memory()
        record = self.record()
        memory.add(record)
        for duplicate in [record, {**self.record(1), "episode_id": record["episode_id"]},
                          {**record, "episode_id": "another-id"}]:
            with self.assertRaises(ValueError):
                memory.add(duplicate)
        self.assertEqual(memory.records, [record])

    def test_overlapping_cycles_rejected(self):
        record = self.record()
        location = self.frame["Datetime"].searchsorted(record["as_of_date"])
        dates = [self.frame["Datetime"].iloc[int(location) + offset].strftime("%Y-%m-%d") for offset in (1, 2, 4)]
        other = copy.deepcopy(record)
        other.update(episode_id="overlap", as_of_date=dates[0], entry_date=dates[1], exit_date=dates[2])
        entry, exit_close = execution_prices_for_cycle(self.frame, self.events, *dates)
        net = float(100 * compute_round_trip_net_return(entry, exit_close))
        other["outcome"] = {"actual_direction": "UP" if net > 0 else "DOWN", "net_return_pct": net,
                            "was_bull_trap": bool(net <= 0), "result": "WIN_IF_LONG" if net > 0 else "LOSS_IF_LONG"}
        memory = self.memory()
        memory.add(record)
        with self.assertRaises(ValueError):
            memory.add(other)

    def test_load_rejects_entire_invalid_file(self):
        memory = self.memory()
        memory.add(self.record())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.json"
            for payload in [json.dumps([self.record(), {}]), '{}', '[{"x":1,"x":2}]', '[NaN]']:
                path.write_text(payload, encoding="utf-8")
                with self.assertRaises(ValueError):
                    memory.load(path)
                self.assertEqual(memory.records, [self.record()])

    def test_failed_atomic_replace_preserves_previous_file(self):
        memory = self.memory()
        memory.add(self.record())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.json"
            path.write_text("previous", encoding="utf-8")
            with patch("core.bayesian_memory.os.replace", side_effect=OSError("Lỗi ghi thử nghiệm")):
                with self.assertRaises(OSError):
                    memory.save(path)
            self.assertEqual(path.read_text(encoding="utf-8"), "previous")
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])

    def test_corrupt_execution_evidence_blocks_save(self):
        memory = self.memory()
        memory.add(self.record())
        memory._execution_loader = lambda symbol: (_ for _ in ()).throw(ValueError("Checksum sai"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.json"
            with self.assertRaises(ValueError):
                memory.save(path)
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
