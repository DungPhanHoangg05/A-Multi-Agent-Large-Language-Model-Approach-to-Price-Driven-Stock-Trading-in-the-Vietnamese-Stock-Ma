"""Runner chặn model/tín hiệu tương lai và giữ nguyên prefix khi tương lai đổi."""

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import test_historical_runner as fixtures
from core.bayesian_memory import atomic_write_json, read_json
from core.historical_runner import HistoricalMemoryRunner, PrefixRegimeProvider
from core.historical_signals import HistoricalSignalExtractor, digest
from default_config import DEFAULT_CONFIG


class HistoricalRunnerLeakageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.HistoricalRunnerTests.setUpClass()

    def test_future_model_rejected_before_llm_and_episode(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            provider = fixtures.FastPrefix(output / "regimes", fixtures.HistoricalRunnerTests.index)
            original = provider.get
            def future_model(cutoff, **kwargs):
                result = original(cutoff, **kwargs)
                result["metadata"]["train_end_date"] = "2022-12-30"
                return result
            provider.get = future_model
            extractor = Mock(config={"models": {}})
            runner = HistoricalMemoryRunner(output, extractor, symbols=("FPT",), regime_provider=provider,
                                             article_loader=lambda symbol: [])
            with self.assertRaises(ValueError):
                runner.run(max_new_points=1)
            extractor.extract.assert_not_called()
            self.assertEqual(list((output / "episodes").glob("*.json")), [])

    def test_future_index_does_not_change_prefix_model_or_state(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = PrefixRegimeProvider(directory, fixtures.HistoricalRunnerTests.index)
            with patch("builtins.print"):
                first = provider.get("2020-06-01")
                provider.archive.loc[provider.archive["Datetime"] > "2020-06-01", "Close"] = float("nan")
                second = provider.get("2020-06-01")
            self.assertEqual(first, second)
            self.assertEqual(first["metadata"]["train_end_date"], "2020-06-01")

    def test_future_news_provenance_rejected_even_when_signal_checksum_matches(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch("utils.static_util.generate_kline_image", return_value={}), \
                patch("utils.static_util.generate_trend_image", return_value={}):
            output = Path(directory)
            graph = Mock()
            graph.invoke.return_value = copy.deepcopy(fixtures.signal_fixtures.REPORTS)
            extractor = HistoricalSignalExtractor(graph, fixtures.signal_fixtures.fake_alpha, output / "signals",
                                                  DEFAULT_CONFIG, article_loader=lambda symbol: [])
            original = extractor.extract
            def corrupted(symbol, cutoff):
                bundle = original(symbol, cutoff)
                bundle["provenance"]["news_dates"] = ["2025-01-01"]
                path = output / "signals" / f"{symbol}-{cutoff}.json"
                payload = read_json(path)["payload"]
                payload["result"] = bundle
                atomic_write_json(path, {"payload": payload, "sha256": digest(payload)})
                return bundle
            extractor.extract = corrupted
            runner = HistoricalMemoryRunner(output, extractor, symbols=("FPT",), article_loader=lambda symbol: [],
                                             regime_provider=fixtures.FastPrefix(output / "regimes", fixtures.HistoricalRunnerTests.index))
            with self.assertRaises(ValueError):
                runner.run(max_new_points=1)
            self.assertEqual(read_json(output / "memory.json"), [])
            self.assertEqual(list((output / "episodes").glob("*.json")), [])

    def test_labels_are_computed_after_signal_extraction_on_separate_inputs(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch("utils.static_util.generate_kline_image", return_value={}), \
                patch("utils.static_util.generate_trend_image", return_value={}):
            output = Path(directory)
            graph = Mock()
            graph.invoke.return_value = copy.deepcopy(fixtures.signal_fixtures.REPORTS)
            extractor = HistoricalSignalExtractor(graph, fixtures.signal_fixtures.fake_alpha, output / "signals",
                                                  DEFAULT_CONFIG, article_loader=lambda symbol: [])
            runner = HistoricalMemoryRunner(output, extractor, symbols=("FPT",), article_loader=lambda symbol: [],
                                             regime_provider=fixtures.FastPrefix(output / "regimes", fixtures.HistoricalRunnerTests.index))
            with patch.object(runner.outcomes, "generate", wraps=runner.outcomes.generate) as label:
                runner.run(max_new_points=1)
            state = graph.invoke.call_args.args[0]
            self.assertNotIn("outcome", state)
            self.assertNotIn("entry_date", state)
            self.assertNotIn("exit_date", state)
            self.assertEqual(state["point_in_time_df"]["Datetime"].max().strftime("%Y-%m-%d"), "2020-06-01")
            self.assertEqual(label.call_args.kwargs["exit_date"], "2020-06-04")


if __name__ == "__main__":
    unittest.main()
