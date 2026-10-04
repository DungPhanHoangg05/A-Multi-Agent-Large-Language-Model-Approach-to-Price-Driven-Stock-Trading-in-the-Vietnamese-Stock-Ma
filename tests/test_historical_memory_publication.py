"""Kiểm điều kiện phát hành và checksum của kho; dữ liệu giả lập chỉ ở thư mục tạm."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.bayesian_memory import DEFAULT_DATA_DIR, HistoricalMemory, atomic_write_json, read_json
from core.execution_prices import build_verified_cycle_schedule, load_verified_execution_data
from core.historical_outcomes import HistoricalOutcomeGenerator
from core.historical_signals import digest
from default_config import DEFAULT_CONFIG
from scripts.publish_historical_memory import frozen_articles, publish

SIGNALS = {"trend": "BULLISH", "pattern": "NEUTRAL", "alpha_consensus": "NEUTRAL",
           "indicator_consensus": "NEUTRAL", "sentiment": "NEUTRAL"}


class HistoricalMemoryPublicationTests(unittest.TestCase):
    def identity(self):
        return {"symbols": ["FPT", "MWG", "VCB", "VNM"], "start": "2018-01-01", "end": "2022-12-31",
                "models": {key: value for key, value in DEFAULT_CONFIG.items() if key.endswith(("model", "temperature", "tokens"))},
                "data": {symbol: {"news": digest([])} for symbol in ("FPT", "MWG", "VCB", "VNM")}}

    def test_frozen_archive_works_without_original_cache_and_rejects_mutation(self):
        with tempfile.TemporaryDirectory() as directory, patch("scripts.publish_historical_memory.disk_articles") as cache:
            root = Path(directory)
            path = root / "inputs/news/FPT.json"
            atomic_write_json(path, {"symbol": "FPT", "scored_articles": []})
            self.assertEqual(frozen_articles(root, self.identity(), "FPT"), [])
            cache.assert_not_called()
            atomic_write_json(path, {"symbol": "FPT", "scored_articles": [{"date_parsed": "2020-01-01"}]})
            with self.assertRaises(ValueError):
                frozen_articles(root, self.identity(), "FPT")

    def test_insufficient_or_incomplete_run_does_not_publish(self):
        with tempfile.TemporaryDirectory() as directory, patch("scripts.publish_historical_memory.HistoricalMemoryRunner") as runner:
            target = Path(directory) / "bank.json"
            runner._read_envelope.return_value = self.identity()
            for status in ({"completed": 300, "remaining": 0}, {"completed": 301, "remaining": 1}):
                runner.return_value.run.return_value = status
                with self.subTest(status=status), self.assertRaises(ValueError):
                    publish(Path(directory), target, require_complete=True)
                self.assertFalse(target.exists())

    def test_missing_stock_rejected_before_writing_bank(self):
        with tempfile.TemporaryDirectory() as directory, patch("scripts.publish_historical_memory.HistoricalMemoryRunner") as runner:
            root = Path(directory)
            runner._read_envelope.return_value = self.identity()
            runner.return_value.run.return_value = {"completed": 301, "remaining": 0}
            atomic_write_json(root / "memory.json", [{"symbol": "FPT"}] * 301)
            with self.assertRaises(ValueError):
                publish(root, root / "bank.json")
            self.assertFalse((root / "bank.json").exists())

    def test_validated_price_records_publish_with_matching_receipt_and_frozen_news(self):
        records = []
        for symbol in ("FPT", "MWG", "VCB", "VNM"):
            frame, events = load_verified_execution_data(DEFAULT_DATA_DIR, symbol)
            schedule = build_verified_cycle_schedule(frame, events)
            schedule = schedule.loc[schedule["eligible"]].head(76 if symbol == "FPT" else 75).copy()
            for key in ("as_of_date", "entry_date", "exit_date"):
                schedule[key] = schedule[key].dt.strftime("%Y-%m-%d")
            generator = HistoricalOutcomeGenerator(lambda code: (frame, events))
            for cycle in schedule[["as_of_date", "entry_date", "exit_date"]].to_dict("records"):
                outcome = generator.generate(symbol, **cycle, agent_signals=SIGNALS, settled_as_of="2022-12-31")
                records.append({"episode_id": f"{symbol}:{cycle['as_of_date']}", "symbol": symbol, **cycle,
                                "regime": "BULL", "agent_signals": SIGNALS, "outcome": outcome})
        with tempfile.TemporaryDirectory() as directory, patch("scripts.publish_historical_memory.HistoricalMemoryRunner") as runner, \
                patch("scripts.publish_historical_memory.ROOT", Path(directory)):
            root = Path(directory)
            runner._read_envelope.return_value = self.identity()
            runner.return_value.run.return_value = {"completed": 301, "remaining": 0}
            # Trạng thái runner đã được kiểm ở W2-12; test này kiểm riêng bước phát hành.
            atomic_write_json(root / "memory.json", records)
            for record in records:
                path = root / "signals" / f"{record['symbol']}-{record['as_of_date']}.json"
                atomic_write_json(path, {})
            runner._read_envelope.side_effect = lambda path: self.identity() if path.name == "run_manifest.json" else {
                "result": {"provenance": {"news_is_reliable": False}}}
            target = root / "bank.json"
            receipt = publish(root, target, require_complete=True)
            memory = HistoricalMemory()
            memory.load(target)
            self.assertEqual(len(memory.records), 301)
            self.assertEqual(receipt["bank_sha256"], hashlib.sha256(target.read_bytes()).hexdigest())
            self.assertEqual(receipt["records_sha256"], digest(records))
            self.assertEqual(receipt["by_symbol"], {"FPT": 76, "MWG": 75, "VCB": 75, "VNM": 75})
            self.assertEqual(read_json(target.with_suffix(".manifest.json")), receipt)
            self.assertEqual(read_json(root / "inputs/news/FPT.json")["scored_articles"], [])


if __name__ == "__main__":
    unittest.main()
