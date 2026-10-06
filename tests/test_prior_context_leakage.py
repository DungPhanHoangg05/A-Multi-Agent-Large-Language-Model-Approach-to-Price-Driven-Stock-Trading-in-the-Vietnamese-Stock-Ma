"""Dò leakage model/giá/tin/tín hiệu ở adapter, trước retrieve và Decision."""

from copy import deepcopy
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from core.prior_context import PriorContextAdapter
from prior_context_test_support import ContextFixture, model_file, write_json
from test_backtest_token_budget import _CountingLlm
from utils.graph_setup import SetGraph


def article(day: str | None, *, label: str = "positive") -> dict:
    """Bài tổng hợp nhỏ có ngày/nhãn/score xác định, không là tin thị trường."""
    return {"date_parsed": day, "label": label, "numeric_score": 1. if label == "positive" else 0.,
            "title": f"Tin fixture {day}", "content": "Dữ liệu tổng hợp."}


class PriorContextLeakageTests(unittest.TestCase):
    def setUp(self) -> None:
        for target in ("builtins.print", "core.regime_detector.MarketRegimeDetector.fit",
                       "data_manager.sentiment_cache.SentimentCache.preload"):
            guard = patch(target) if target == "builtins.print" else patch(target, side_effect=AssertionError("Cấm fit/crawl"))
            guard.start()
            self.addCleanup(guard.stop)
        self.fixture = ContextFixture()
        self.addCleanup(self.fixture.close)

    def test_snapshot_future_stale_symbol_and_modified_prices_fail_before_provider(self) -> None:
        fx = self.fixture
        adapter = fx.adapter()
        cases = [fx.frame["FPT"].iloc[:646].loc[:, ["Datetime", "Open", "High", "Low", "Close", "Volume"]],
                 fx.frame["FPT"].iloc[:644].loc[:, ["Datetime", "Open", "High", "Low", "Close", "Volume"]],
                 fx.frame["MWG"].iloc[:645].loc[:, ["Datetime", "Open", "High", "Low", "Close", "Volume"]]]
        wrong = cases[0].iloc[:-1].copy()
        wrong.loc[0, "Close"] += .01
        cases.append(wrong)
        wrong = cases[0].iloc[:-1].copy()
        wrong.attrs["symbol"] = "MWG"
        cases.append(wrong)
        with patch.object(adapter._provider, "get") as get:
            for frame in cases:
                with self.subTest(rows=len(frame)), self.assertRaises(ValueError):
                    adapter.prepare("FPT", fx.cutoff, point_in_time_df=frame)
        get.assert_not_called()

    def test_vnindex_future_missing_training_prefix_and_hash_mismatch_fail_before_model(self) -> None:
        fx = self.fixture
        adapter = fx.adapter()
        changed = fx.vnindex.iloc[:645].copy()
        changed.loc[100, "Close"] += .01
        with patch.object(adapter._provider, "get") as get:
            for prefix in (fx.vnindex.iloc[:646], fx.vnindex.iloc[1:645], changed):
                with self.subTest(rows=len(prefix)), self.assertRaises(ValueError):
                    adapter.prepare("FPT", fx.cutoff, vnindex_prefix=prefix)
        get.assert_not_called()

    def test_future_trained_replay_model_and_mismatching_artifact_hash_fail(self) -> None:
        fx = self.fixture
        path = fx.root / f"run/regimes/VNINDEX-{fx.cutoff}.json"
        model_file(path, fx.vnindex.iloc[:646])
        with self.assertRaises(ValueError):
            fx.adapter().prepare("FPT", fx.cutoff)
        model_file(path, fx.vnindex.iloc[:645])
        adapter = fx.adapter()
        proof = adapter._provider.get(fx.cutoff, verify_only=True)
        proof["artifact_sha256"] = "b" * 64
        with patch.object(adapter._provider, "get", return_value=proof), self.assertRaises(ValueError):
            adapter.prepare("FPT", fx.cutoff)

    def test_missing_replay_artifact_does_not_fit_create_or_switch_provider(self) -> None:
        fx = self.fixture
        adapter = fx.adapter()
        path = fx.root / f"run/regimes/VNINDEX-{fx.cutoff}.json"
        path.unlink()
        files_before = {item.relative_to(fx.root).as_posix() for item in fx.root.rglob("*") if item.is_file()}
        with self.assertRaises(FileNotFoundError):
            adapter.prepare("FPT", fx.cutoff)
        self.assertEqual(files_before, {item.relative_to(fx.root).as_posix() for item in fx.root.rglob("*") if item.is_file()})
        self.assertIsNone(adapter._fixed)

    def test_fixed_train_end_equal_cutoff_and_freeze_not_before_query_fail(self) -> None:
        fx = self.fixture
        model_file(fx.root / "model/fixed.json", fx.vnindex.iloc[:645])
        adapter = fx.adapter(provider_mode="fixed_train_oos", frozen_artifact_path="model/fixed.json", freeze_as_of_date=fx.cutoff)
        with self.assertRaises(ValueError):
            adapter.prepare("FPT", fx.cutoff)
        model_file(fx.root / "model/fixed.json", fx.vnindex.iloc[:600])
        for freeze in (fx.cutoff, fx.day(645)):
            adapter = fx.adapter(provider_mode="fixed_train_oos", frozen_artifact_path="model/fixed.json", freeze_as_of_date=freeze)
            with self.subTest(freeze=freeze), self.assertRaises(ValueError):
                adapter.prepare("FPT", fx.cutoff)
        with self.assertRaises(ValueError):
            fx.adapter(provider_mode="fixed_train_oos", frozen_artifact_path="model/fixed.json", freeze_as_of_date=fx.day(598))

    def test_model_component_state_feature_date_cannot_be_self_reported(self) -> None:
        fx = self.fixture
        adapter = fx.adapter()
        original = adapter._provider.get(fx.cutoff, verify_only=True)
        for field, value in (("as_of_date", fx.day(643)), ("feature_end_date", fx.day(643)),
                             ("feature_end_date", fx.day(645))):
            wrong = deepcopy(original)
            wrong["state"][field] = value
            with self.subTest(field=field), patch.object(adapter._provider, "get", return_value=wrong), self.assertRaises(ValueError):
                adapter.prepare("FPT", fx.cutoff)

    def test_causal_state_features_ignore_future_vnindex_archive_values(self) -> None:
        fx = self.fixture
        before = fx.adapter().prepare("FPT", fx.cutoff).source_provenance["regime"]
        path = fx.root / "data/historical/VNINDEX.csv"
        frame = fx.vnindex.copy()
        future = frame.Datetime > fx.cutoff
        frame.loc[future, ["Open", "High", "Low", "Close"]] *= 100.
        # Giữ nguyên byte prefix; đọc/ghi lại float quá khứ có thể làm đổi một ULP.
        prefix_lines = path.read_text("utf-8").splitlines(keepends=True)[:646]
        path.write_text("".join(prefix_lines) + frame.loc[future].to_csv(index=False, header=False,
            date_format="%Y-%m-%d", float_format="%.17g"), encoding="utf-8")
        manifest_path = path.parent / "manifest.json"
        manifest = json.loads(manifest_path.read_text("utf-8"))
        manifest["files"]["VNINDEX"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        write_json(manifest_path, manifest)
        after = fx.adapter().prepare("FPT", fx.cutoff).source_provenance["regime"]
        for field in ("inference_prefix_sha256", "feature_sha256", "state_sha256", "metadata", "artifact_sha256"):
            self.assertEqual(before[field], after[field])
        self.assertNotEqual(before["source_csv_sha256"], after["source_csv_sha256"])

    def test_news_cutoff_window_and_full_coverage_before_fifteen_article_display(self) -> None:
        fx = self.fixture
        cutoff = date.fromisoformat(fx.cutoff)
        boundary = (cutoff - timedelta(days=90)).isoformat()
        articles = [article(fx.cutoff) for _ in range(18)] + [article(boundary), article(None),
                    article((cutoff + timedelta(days=1)).isoformat()), article((cutoff - timedelta(days=91)).isoformat())]
        write_json(fx.root / "run/inputs/news/FPT.json", {"symbol": "FPT", "scored_articles": articles})
        point = fx.adapter().prepare("FPT", fx.cutoff)
        proof = point.source_provenance["news"]
        self.assertEqual(proof["input_count"], 22)
        self.assertEqual(proof["visible_count"], 19)
        self.assertEqual(proof["excluded_counts"], {"undated": 1, "future": 1, "outside_window": 1})
        self.assertEqual(proof["coverage_start_date"], boundary)
        self.assertEqual(proof["coverage_end_date"], fx.cutoff)
        self.assertTrue(proof["is_reliable"])
        full = fx.full(point)
        self.assertEqual(len(full["sentiment_data"]["scored_articles"]), 15)
        self.assertEqual(point.bind_full(full)["current_signals"]["sentiment"], "POSITIVE")

    def test_sparse_news_keeps_audit_but_neutral_signal_and_report(self) -> None:
        fx = self.fixture
        articles = [article(fx.cutoff), article(fx.day(643))]
        write_json(fx.root / "run/inputs/news/FPT.json", {"symbol": "FPT", "scored_articles": articles})
        point = fx.adapter().prepare("FPT", fx.cutoff)
        proof = point.source_provenance["news"]
        self.assertEqual(proof["visible_count"], 2)
        self.assertFalse(proof["is_reliable"])
        self.assertEqual(proof["neutral_reason"], "INSUFFICIENT_DATED_HISTORY")
        full = fx.full(point)
        self.assertEqual(full["sentiment_data"]["main_sentiment"]["avg_score"], 0.)
        self.assertNotIn(articles[0]["title"], full["sentiment_report"])
        self.assertEqual(point.bind_full(full)["current_signals"]["sentiment"], "NEUTRAL")

    def test_malformed_source_date_is_error_even_when_article_would_be_excluded(self) -> None:
        fx = self.fixture
        for day in ("2099-02-30", "2020-1-1", "2020-01-01T00:00:00Z"):
            write_json(fx.root / "run/inputs/news/FPT.json", {"symbol": "FPT", "scored_articles": [article(day)]})
            with self.subTest(day=day), self.assertRaises(ValueError):
                fx.adapter()

    def test_future_or_undated_news_in_full_visible_output_is_error_before_query(self) -> None:
        fx = self.fixture
        write_json(fx.root / "run/inputs/news/FPT.json", {"symbol": "FPT", "scored_articles": [article(fx.cutoff)]})
        point = fx.adapter().prepare("FPT", fx.cutoff)
        for day in (fx.day(645), None):
            full = fx.full(point)
            full["sentiment_data"]["scored_articles"][0]["date_parsed"] = day
            with self.subTest(day=day), self.assertRaises(ValueError):
                point.bind_full(full)
        self.assertIsNone(point._shared)

    def test_price_gate_oos_and_invalid_timeframe_are_rejected_before_upstream(self) -> None:
        fx = self.fixture
        adapter = fx.adapter()
        with patch.object(adapter._provider, "get") as get:
            for symbol, cutoff, timeframe in (("FPT", "2023-01-10", "1d"), ("FPT", fx.cutoff, "1 day"),
                                              ("FPT", fx.cutoff, "1w"), ("fpt", fx.cutoff, "1d")):
                with self.subTest(symbol=symbol, date=cutoff), self.assertRaises(ValueError):
                    adapter.prepare(symbol, cutoff, time_frame=timeframe)
        get.assert_not_called()

    def test_pinned_price_news_regime_or_bank_mutation_stops_graph_before_retrieve(self) -> None:
        fx = self.fixture
        point = fx.adapter().prepare("FPT", fx.cutoff)
        shared = point.bind_full(fx.full(point))
        for relative in ("data/execution_prices/FPT.csv", "run/inputs/news/FPT.json",
                         f"run/regimes/VNINDEX-{fx.cutoff}.json", "bank/bank.json"):
            path = fx.root / relative
            content = path.read_bytes()
            path.write_bytes(content + b"\n")
            llm = _CountingLlm()
            with patch.object(point._adapter._retriever, "retrieve") as retrieve:
                graph = SetGraph(llm, object(), object()).compile_report_decision(
                    prior_config=shared["prior_config"], prior_retriever=point.retrieve, prior_source_validator=point.verify_source)
                with self.subTest(source=relative), self.assertRaises(ValueError):
                    graph.invoke(shared)
                retrieve.assert_not_called()
                self.assertEqual(llm.calls, 0)
            path.write_bytes(content)

    def test_paths_cannot_escape_repo_or_change_symbol_through_source_manifest(self) -> None:
        fx = self.fixture
        for path in ("../news", "C:/news", "https://news", "news\\folder", "/news", "news/../other"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                fx.adapter(news_dir=path)
        files = fx.adapter()._files
        original = Path.resolve
        target = files.root / "escape/model.json"
        outside = files.root.parent / "outside-model.json"
        with patch.object(Path, "resolve", lambda value, *args, **kwargs: outside if value == target else original(value, *args, **kwargs)):
            with self.assertRaises(ValueError):
                files.path("escape/model.json")
        write_json(fx.root / "run/inputs/news/FPT.json", {"symbol": "MWG", "scored_articles": []})
        with self.assertRaises(ValueError):
            fx.adapter()

    def test_outcome_alias_and_changed_signals_never_reach_retriever(self) -> None:
        fx = self.fixture
        point = fx.adapter().prepare("FPT", fx.cutoff)
        shared = point.bind_full(fx.full(point))
        cases = [{**shared, "outcome": {"result": "WIN"}}, {**shared, "entry_open": 999.},
                 {**shared, "actual_pct_change": 1000.}, {**shared, "current_regime": "BULL"}]
        changed = deepcopy(shared)
        changed["current_signals"]["trend"] = "BEARISH"
        cases.append(changed)
        with patch.object(point._adapter._retriever, "retrieve") as retrieve:
            for projection in cases:
                with self.subTest(fields=list(projection)), self.assertRaises(ValueError):
                    point.retrieve(projection)
        retrieve.assert_not_called()


if __name__ == "__main__":
    unittest.main()
