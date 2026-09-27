"""Kiểm runner, tiếp tục journal, phục hồi kho xuất và tích hợp pipeline thực."""

import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import test_historical_signals as signal_fixtures
from core.bayesian_memory import DEFAULT_DATA_DIR, HistoricalMemory, atomic_write_json, read_json
from core.execution_prices import load_verified_execution_data
from core.historical_runner import HistoricalMemoryRunner, PrefixRegimeProvider, load_vnindex_archive
from core.historical_signals import HistoricalSignalExtractor
from core.regime_detector import MarketRegimeDetector, training_data_hash
from default_config import DEFAULT_CONFIG


class FastPrefix(PrefixRegimeProvider):
    """Provider giả lập cho test journal; test tích hợp riêng dùng HMM thật."""

    def get(self, as_of_date, *, verify_only=False):
        prefix = self.archive.loc[self.archive["Datetime"] <= as_of_date]
        payload = {"state": {"as_of_date": as_of_date, "feature_end_date": as_of_date, "regime_id": 0,
                             "regime_name": "BULL", "volatility_level": "LOW", "trend_strength": 1., "source_symbol": "VNINDEX"},
                   "metadata": {"train_start_date": "2018-01-02", "train_end_date": as_of_date,
                                "training_data_sha256": training_data_hash(prefix)}}
        path = self.artifact_dir / f"VNINDEX-{as_of_date}.json"
        if not path.exists():
            if verify_only:
                raise ValueError("Thiếu artifact giả lập")
            atomic_write_json(path, payload)
        return {**payload, "artifact_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


class HistoricalRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = {symbol: load_verified_execution_data(DEFAULT_DATA_DIR, symbol) for symbol in ("FPT", "VNM", "VCB", "MWG")}
        cls.index = load_vnindex_archive()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.output = Path(self.directory.name) / "run"
        self.graph = Mock()
        self.graph.invoke.return_value = copy.deepcopy(signal_fixtures.REPORTS)
        self.alpha = Mock(side_effect=signal_fixtures.fake_alpha)
        self.image_patches = []
        for name in ("generate_kline_image", "generate_trend_image"):
            p = patch(f"utils.static_util.{name}", return_value={})
            p.start()
            self.image_patches.append(p)
            self.addCleanup(p.stop)

    def loader(self, symbol):
        frame, events = self.data[symbol]
        return frame.copy(deep=True), copy.deepcopy(events)

    def runner(self, **kwargs):
        extractor = HistoricalSignalExtractor(self.graph, self.alpha, self.output / "signals", DEFAULT_CONFIG,
                                              execution_loader=self.loader, article_loader=lambda symbol: [])
        return HistoricalMemoryRunner(self.output, extractor, execution_loader=self.loader,
                                      regime_provider=kwargs.pop("provider", FastPrefix(self.output / "regimes", self.index)),
                                      article_loader=lambda symbol: [], **kwargs)

    def test_real_verified_plan_has_852_eligible_and_16_exclusions(self):
        runner = self.runner()
        plan = runner.plan()
        self.assertEqual(plan["candidate_count"], 868)
        self.assertEqual(plan["eligible_count"], 852)
        self.assertEqual(len(plan["excluded"]), 16)
        self.assertEqual(plan["points"][0]["as_of_date"], "2020-06-01")
        self.assertFalse(self.output.exists())

    def test_resume_processes_only_new_points_and_verify_without_llm(self):
        first = self.runner().run(max_new_points=1)
        self.assertEqual(first["completed"], 1)
        second = self.runner().run(max_new_points=1)
        self.assertEqual(second["completed"], 2)
        self.assertEqual(self.graph.invoke.call_count, 2)
        records = read_json(self.output / "memory.json")
        self.assertEqual(len(records), 2)
        self.assertEqual(len({record["episode_id"] for record in records}), 2)
        memory = HistoricalMemory(self.loader)
        memory.load(self.output / "memory.json")
        self.assertEqual(memory.records, records)
        verifier = HistoricalMemoryRunner(self.output, execution_loader=self.loader,
                                          regime_provider=FastPrefix(self.output / "regimes", self.index), article_loader=lambda symbol: [])
        self.assertEqual(verifier.run(verify_only=True), {"completed": 2, "remaining": 850, "new_points": 0})
        self.assertEqual(self.graph.invoke.call_count, 2)

    def test_crash_after_journal_before_export_recovers_without_upstream(self):
        def fail_export(path, payload):
            if Path(path).name == "memory.json" and len(payload) == 1:
                raise OSError("Gián đoạn khi xuất kho")
            return atomic_write_json(path, payload)

        with patch("core.historical_runner.atomic_write_json", side_effect=fail_export):
            with self.assertRaises(OSError):
                self.runner(symbols=("FPT",), start="2020-06-01", end="2020-06-04").run()
        self.assertEqual(read_json(self.output / "memory.json"), [])
        self.assertEqual(len(list((self.output / "episodes").glob("*.json"))), 1)
        result = self.runner(symbols=("FPT",), start="2020-06-01", end="2020-06-04").run()
        self.assertEqual(result["new_points"], 0)
        self.assertEqual(len(read_json(self.output / "memory.json")), 1)
        self.assertEqual(self.graph.invoke.call_count, 1)

    def test_failed_alpha_keeps_no_partial_episode_and_resume_reuses_upstream(self):
        calls = []
        def temporary_failure(state):
            calls.append(True)
            if len(calls) == 1:
                raise RuntimeError("Lỗi alpha thử nghiệm")
            return signal_fixtures.fake_alpha(state)
        self.alpha.side_effect = temporary_failure
        with self.assertRaises(RuntimeError):
            self.runner().run(max_new_points=1)
        self.assertEqual(read_json(self.output / "memory.json"), [])
        self.assertEqual(list((self.output / "episodes").glob("*.json")), [])
        self.assertEqual(self.runner().run(max_new_points=1)["completed"], 1)
        self.assertEqual(self.graph.invoke.call_count, 1)

    def test_changed_range_and_corrupt_journal_rejected(self):
        self.runner().run(max_new_points=1)
        with self.assertRaises(ValueError):
            self.runner(end="2022-12-30").run(max_new_points=1)
        path = next((self.output / "episodes").glob("*.json"))
        path.write_text(path.read_text(encoding="utf-8").replace('"net_return_pct":', '"wrong_return":'), encoding="utf-8")
        with self.assertRaises(ValueError):
            self.runner().run(max_new_points=1)
        self.assertEqual(self.graph.invoke.call_count, 1)

    def test_foreign_store_is_not_overwritten(self):
        self.output.mkdir()
        atomic_write_json(self.output / "memory.json", [{"foreign": True}])
        with self.assertRaises(ValueError):
            self.runner().run(max_new_points=1)
        self.assertEqual(read_json(self.output / "memory.json"), [{"foreign": True}])
        self.graph.invoke.assert_not_called()

    def test_run_lock_blocks_concurrent_runner(self):
        self.output.mkdir()
        (self.output / "run.lock").touch()
        with self.assertRaises(RuntimeError):
            self.runner().run(max_new_points=1)
        self.graph.invoke.assert_not_called()

    def test_duplicate_symbols_outside_study_and_invalid_limit_rejected(self):
        for kwargs in ({"symbols": ("FPT", "FPT")}, {"end": "2023-01-03"}, {"start": "2017-12-31"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.runner(**kwargs)
        with self.assertRaises(ValueError):
            self.runner().run(max_new_points=0)

    def test_real_hmm_graph_alpha_labels_and_resume_pipeline(self):
        from utils.graph_setup import SetGraph
        from utils.graph_util import TechnicalTools

        llm = signal_fixtures.LocalLLM()
        extractor = HistoricalSignalExtractor.from_graph_builder(SetGraph(llm, llm, TechnicalTools()),
                                                                 self.output / "signals", DEFAULT_CONFIG,
                                                                 execution_loader=self.loader, article_loader=lambda symbol: [])
        # Dùng ảnh thật trong bộ nhớ cho kiểm thử pipeline đầy đủ.
        for image_patch in self.image_patches:
            image_patch.stop()
        runner = HistoricalMemoryRunner(self.output, extractor, symbols=("FPT", "MWG"), start="2020-06-01", end="2020-06-04",
                                        execution_loader=self.loader, regime_provider=PrefixRegimeProvider(self.output / "regimes", self.index),
                                        article_loader=lambda symbol: [])
        original_fit = MarketRegimeDetector.fit
        with patch.object(MarketRegimeDetector, "fit", autospec=True, side_effect=original_fit) as fit, patch("builtins.print"):
            self.assertEqual(runner.run()["completed"], 2)
            self.assertEqual(runner.run()["new_points"], 0)
            self.assertEqual(fit.call_count, 1)
        self.assertEqual(len(list((self.output / "regimes").glob("*.json"))), 1)
        self.assertEqual(llm.calls, 4)
        records = read_json(self.output / "memory.json")
        self.assertTrue(all(record["exit_date"] == "2020-06-04" for record in records))


if __name__ == "__main__":
    unittest.main()
