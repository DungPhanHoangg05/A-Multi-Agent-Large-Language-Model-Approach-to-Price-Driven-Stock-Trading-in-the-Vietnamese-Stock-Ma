"""Kiểm nền retriever bằng giá giả lập nhưng validator và engine P&L thật."""

import copy
from collections import Counter
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from core.backtest_engine import compute_round_trip_net_return
from core.bayesian_memory import atomic_write_json
from core.bayesian_memory import HistoricalMemory
from core.bayesian_retriever import BayesianPriorRetriever, ROOT, normalize_signals


class BayesianRetrieverFoundationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.frame = pd.DataFrame({"Datetime": pd.bdate_range("2020-01-01", periods=12),
            "Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0,
            "Volume": 1000, "Reference": 100.0})
        self.rows = [self.record("FPT", 0, "BULL"), self.record("FPT", 3, "BEAR"),
                     self.record("MWG", 0, "BULL")]
        self.bank = self.root / "bank.json"
        self.manifest = self.root / "manifest.json"
        self.audit = self.root / "audit.json"
        self.publish_fixture()

    def record(self, symbol, position, regime):
        dates = [self.frame.Datetime.iloc[position + offset].strftime("%Y-%m-%d")
                 for offset in (0, 1, 3)]
        net = float(100 * compute_round_trip_net_return(100.0, 100.0))
        return {"episode_id": f"{symbol}:{dates[0]}", "symbol": symbol,
            "as_of_date": dates[0], "entry_date": dates[1], "exit_date": dates[2], "regime": regime,
            "agent_signals": {"trend": "BULLISH", "pattern": "NEUTRAL", "alpha_consensus": "NEUTRAL",
                              "indicator_consensus": "BEARISH", "sentiment": "NEUTRAL"},
            "outcome": {"actual_direction": "DOWN", "net_return_pct": net,
                        "was_bull_trap": True, "result": "LOSS_IF_LONG"}}

    def publish_fixture(self):
        atomic_write_json(self.bank, self.rows)
        counts = {"by_symbol": dict(Counter(r["symbol"] for r in self.rows)),
                  "by_regime": dict(Counter(r["regime"] for r in self.rows)),
                  "by_year": dict(Counter(r["as_of_date"][:4] for r in self.rows))}
        evidence = {"format_version": 1, "bank_sha256": hashlib.sha256(self.bank.read_bytes()).hexdigest(),
                    "run_signature": "a" * 64, "completed": len(self.rows), **counts}
        self.manifest_data = {**copy.deepcopy(evidence), "remaining": 0}
        self.audit_data = {**copy.deepcopy(evidence), "status": "PASS", "schema_sha256": hashlib.sha256(
            (ROOT / "docs/plan/week1/historical_task_record.schema.json").read_bytes()).hexdigest()}
        atomic_write_json(self.manifest, self.manifest_data)
        atomic_write_json(self.audit, self.audit_data)

    def create(self):
        with patch("core.bayesian_memory.load_verified_execution_data",
                   return_value=(self.frame, [])) as loader:
            retriever = BayesianPriorRetriever(bank_path=self.bank, manifest_path=self.manifest,
                                               audit_path=self.audit)
        self.assertEqual(loader.call_count, 2)
        return retriever

    def query(self, **updates):
        result = {"symbol": "FPT", "as_of_date": "2020-01-15", "current_regime": "BULL",
                  "current_signals": copy.deepcopy(self.rows[0]["agent_signals"])}
        result.update(updates)
        return result

    def test_load_once_no_query_io_and_population_is_independent(self):
        retriever = self.create()
        with patch.object(retriever._memory, "_execution_loader", side_effect=AssertionError("Đọc giá")), \
             patch("core.bayesian_retriever.read_json", side_effect=AssertionError("Đọc JSON")), \
             patch("core.bayesian_memory.read_json", side_effect=AssertionError("Đọc JSON")):
            first = retriever.prepare_query(**self.query())
            self.assertEqual(len(first["eligible_tasks"]), 2)
            self.assertEqual(len(first["regime_population"]), 1)
            first["eligible_tasks"][0]["agent_signals"]["trend"] = "GIẢM"
            self.assertEqual(first["regime_population"][0]["agent_signals"]["trend"], "BULLISH")
            first["metadata"]["scope"] = "pooled"
            fresh = retriever.prepare_query(**self.query())
        self.assertEqual(fresh["eligible_tasks"][0]["agent_signals"]["trend"], "BULLISH")
        self.assertEqual(fresh["metadata"]["scope"], "same_symbol")
        json.dumps(fresh, allow_nan=False)

    def test_scope_counts_and_all_modes_share_the_same_eligible_pool(self):
        retriever = self.create()
        for mode in ("recent", "random", "similarity", "bayesian_regime"):
            result = retriever.prepare_query(**self.query(scope="pooled", mode=mode))
            meta = result["metadata"]
            self.assertEqual((meta["eligible_count"], meta["matched_regime_count"]), (3, 2))
            self.assertEqual(meta["candidate_count"], 2 if mode == "bayesian_regime" else 3)
            self.assertEqual({r["symbol"] for r in result["eligible_tasks"]}, {"FPT", "MWG"})

    def test_cutoff_excludes_equal_exit_and_straddling_cycle(self):
        retriever = self.create()
        for cutoff in ("2018-01-01", "2020-01-03", self.rows[0]["exit_date"]):
            self.assertEqual(retriever.prepare_query(**self.query(as_of_date=cutoff))["eligible_tasks"], [])
        result = retriever.prepare_query(**self.query(as_of_date="2020-01-07"))
        self.assertEqual([r["episode_id"] for r in result["eligible_tasks"]], [self.rows[0]["episode_id"]])
        retriever.prepare_query(**self.query())
        self.assertEqual(retriever.prepare_query(**self.query(as_of_date="2020-01-03"))["eligible_tasks"], [])

    def test_disabled_does_not_create_pool_or_accept_invalid_query(self):
        retriever = self.create()
        with patch.object(retriever._memory, "eligible", side_effect=AssertionError("Tạo pool K=0")):
            result = retriever.retrieve(**self.query(k=0, current_signals=None))
        self.assertEqual(result["tasks"], [])
        self.assertIsNone(result["stats"])
        self.assertEqual(result["metadata"]["status"], "disabled")
        self.assertTrue(all(result["metadata"][k] is None for k in (
            "eligible_count", "matched_regime_count", "candidate_count", "effective_seed")))
        with self.assertRaises(ValueError):
            retriever.retrieve(**self.query(k=0, symbol="UNKNOWN"))
        with self.assertRaises(NotImplementedError):
            retriever.retrieve(**self.query())

    def test_invalid_query_types_enums_and_required_signals(self):
        retriever = self.create()
        invalid = [{"k": v} for v in (-1, 4, True, 3.0, np.int64(3))]
        invalid += [{"seed": v} for v in (-1, 2**32, True, 42.0)]
        invalid += [{"symbol": "fpt"}, {"symbol": []}, {"as_of_date": "2020-02-30"},
                    {"as_of_date": "20200115"}, {"as_of_date": pd.Timestamp("2020-01-15")},
                    {"current_regime": "UNKNOWN"}, {"scope": "all"}, {"mode": "original"},
                    {"current_signals": None}, {"current_signals": {"trend": "BULLISH"}}]
        for update in invalid:
            with self.subTest(update=update), self.assertRaises(ValueError):
                retriever.prepare_query(**self.query(**update))
        retriever.prepare_query(**self.query(mode="recent", current_signals=None))

    def test_normalization_is_exact_and_does_not_mutate_input(self):
        signals = copy.deepcopy(self.rows[0]["agent_signals"])
        signals["trend"] = " ta\u0306ng "
        before = copy.deepcopy(signals)
        self.assertEqual(normalize_signals(signals)["trend"], "BULLISH")
        self.assertEqual(signals, before)
        for field, label in (("trend", "xu hướng tăng"), ("trend", "POSITIVE"), ("sentiment", "BULLISH")):
            with self.subTest(field=field, label=label), self.assertRaises(ValueError):
                normalize_signals({**signals, field: label})

    def test_bad_evidence_is_rejected_before_price_load(self):
        cases = [(self.audit, self.audit_data, "status", "FAIL"),
                 (self.audit, self.audit_data, "schema_sha256", "b" * 64),
                 (self.audit, self.audit_data, "run_signature", "b" * 64),
                 (self.manifest, self.manifest_data, "bank_sha256", "b" * 64),
                 (self.manifest, self.manifest_data, "format_version", True),
                 (self.manifest, self.manifest_data, "remaining", 1)]
        for path, original, key, value in cases:
            with self.subTest(key=key):
                atomic_write_json(path, {**original, key: value})
                with patch("core.bayesian_memory.load_verified_execution_data") as loader, self.assertRaises(ValueError):
                    BayesianPriorRetriever(bank_path=self.bank, manifest_path=self.manifest, audit_path=self.audit)
                loader.assert_not_called()
                atomic_write_json(path, original)

    def test_record_integrity_counts_and_aliases_are_not_trusted_from_qa(self):
        for mutation in (lambda rows: rows.append(copy.deepcopy(rows[0])),
                         lambda rows: rows[0]["outcome"].update(net_return_pct=999),
                         lambda rows: rows[0]["agent_signals"].update(sentiment="UNKNOWN")):
            self.rows = [self.record("FPT", 0, "BULL"), self.record("FPT", 3, "BEAR"), self.record("MWG", 0, "BULL")]
            mutation(self.rows)
            self.publish_fixture()
            with patch("core.bayesian_memory.load_verified_execution_data", return_value=(self.frame, [])), \
                 self.assertRaises(ValueError):
                BayesianPriorRetriever(bank_path=self.bank, manifest_path=self.manifest, audit_path=self.audit)
        self.rows = self.rows[:3]
        self.rows[0]["agent_signals"]["sentiment"] = "NEUTRAL"
        self.publish_fixture()
        atomic_write_json(self.audit, {**self.audit_data, "completed": 99})
        with patch("core.bayesian_memory.load_verified_execution_data", return_value=(self.frame, [])), \
             self.assertRaises(ValueError):
            BayesianPriorRetriever(bank_path=self.bank, manifest_path=self.manifest, audit_path=self.audit)

    def test_poisoned_pool_raises_instead_of_silently_filtering(self):
        retriever = self.create()
        bad_pools = [[self.rows[1]], [self.rows[2]], [self.rows[0], self.rows[0]],
                     [{**self.rows[0], "episode_id": "UNKNOWN"}],
                     [{**self.rows[0], "outcome": {**self.rows[0]["outcome"], "was_bull_trap": np.bool_(True)}}],
                     [{**self.rows[0], "outcome": {**self.rows[0]["outcome"], "net_return_pct": 1}}]]
        for pool in bad_pools:
            with self.subTest(pool=pool), patch.object(retriever._memory, "eligible", return_value=pool), \
                 self.assertRaises(ValueError):
                retriever.prepare_query(**self.query(as_of_date="2020-01-07"))

    def test_file_change_during_cold_load_is_rejected(self):
        original_load = HistoricalMemory.load

        def changed_load(memory, path):
            original_load(memory, path)
            self.bank.write_bytes(self.bank.read_bytes() + b" ")

        with patch("core.bayesian_memory.load_verified_execution_data", return_value=(self.frame, [])), \
             patch.object(HistoricalMemory, "load", new=changed_load), self.assertRaises(ValueError):
            BayesianPriorRetriever(bank_path=self.bank, manifest_path=self.manifest, audit_path=self.audit)

    def test_selection_postconditions_reject_wrong_regime_or_excess_k(self):
        retriever = self.create()
        args = {"symbol": "FPT", "as_of_date": "2020-01-15", "current_regime": "BULL",
                "scope": "same_symbol", "mode": "bayesian_regime", "k": 1}
        retriever._validate_selection([self.rows[0]], **args)
        with self.assertRaises(ValueError):
            retriever._validate_selection([self.rows[1]], **args)
        with self.assertRaises(ValueError):
            retriever._validate_selection(self.rows[:2], **{**args, "mode": "recent"})


if __name__ == "__main__":
    unittest.main()
