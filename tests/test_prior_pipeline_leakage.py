"""Dò PIT xuyên adapter → graph → prior → prompt → checkpoint bằng nguồn tổng hợp."""

from copy import deepcopy
from datetime import date, timedelta
import gzip
import hashlib
import json
from typing import Any
import unittest
from unittest.mock import patch

from core.backtest_engine import BacktestEngine, PRIOR_BRANCH_MODES, compute_round_trip_net_return
from core.bayesian_memory import atomic_write_json
from core.bayesian_retriever import format_compact_prior_prefix
from core.historical_signals import snapshot_payload
from core.prior_backtest import canonical_hash
from core.prior_checkpoint import CheckpointSession
from core.prior_context import PriorContextAdapter
from core.regime_detector import _payload_hash
from prior_context_test_support import model_file, write_json
import test_prior_backtest_integration as support

PROVIDERS = ("historical_prefix", "fixed_train_oos")
SCOPES = ("same_symbol", "pooled")
COVERAGE = {
    "test_public_run_checks_snapshot_and_feature_prefix_before_upstream": "Giá/snapshot/VNINDEX future, stale và sai prefix trước upstream/retrieve/LLM",
    "test_every_pipeline_boundary_only_receives_pit_query_inputs": "Snapshot/chart/Alpha/query/Decision/point/evaluation, năm nhánh và hai provider",
    "test_news_filter_coverage_and_sparse_neutral_survive_all_five_prompts": "Tin future/undated/ngoài cửa sổ, coverage trước display, sparse NEUTRAL",
    "test_future_or_invalid_model_components_stop_public_run_before_agents": "Train future/scaler/calibration/hash artifact băm lại, hai provider",
    "test_injected_provider_wrong_dates_hash_and_training_proof_stop_before_agents": "Provider bị can thiệp trả state/feature/metadata/hash sai",
    "test_equal_exit_straddling_future_excluded_in_graph_tasks_ranking_stats_prefix": "Hai provider × hai scope × năm nhánh, exit < cutoff, ranking/stats/BRPP",
    "test_unclosed_history_append_and_mutation_leave_old_graph_evidence_unchanged": "Thêm/sửa future signals/regime/nhãn, IDs/scores/stats/seed/BRPP không đổi",
    "test_later_then_earlier_graph_queries_do_not_reuse_future_evidence": "Hai provider, thứ tự ngày ngược trên cùng adapter/retriever",
    "test_injected_pool_selectors_and_population_stop_before_formatter_or_llm": "Pool/selector/population future, bốn mode × hai scope, không skip/fallback",
    "test_future_execution_outcome_changes_evaluation_without_changing_decisions": "Đổi giá sau cutoff, nhãn future dùng engine; prompt/Decision giữ nguyên",
    "test_rehashed_checkpoint_future_sources_cannot_resume_either_provider": "Resume hai provider, mọi component model/news/price/cutoff trước API",
}


class PriorPipelineLeakageTests(unittest.TestCase):
    def setUp(self) -> None:
        support.PriorBacktestIntegrationTests.setUp(self)
        for target in ("socket.socket.connect", "langchain_groq.ChatGroq._generate"):
            self.stack.enter_context(patch(target, side_effect=AssertionError("Cấm mạng/LLM thật trong suite PIT")))

    run_fixture = support.PriorBacktestIntegrationTests.run_fixture
    read_payload = support.PriorBacktestIntegrationTests.read_payload

    def fresh_engine(self) -> None:
        """Engine mới cho scenario hoặc resume; không đổi cấu hình nghiên cứu."""
        self.engine = BacktestEngine(deepcopy(self.engine.config))
        self.engine.DELAY_BETWEEN_VARIANTS = self.engine.DELAY_BETWEEN_TESTS = 0.

    def adapter_for(self, provider: str) -> PriorContextAdapter:
        """Hai provider production dùng artifact tổng hợp đã được loader kiểm thật."""
        return self.fx.adapter() if provider == "historical_prefix" else self.fx.adapter(
            provider_mode=provider, frozen_artifact_path="model/fixed.json", freeze_as_of_date=self.fx.day(620))

    def point_payload(self) -> dict[str, Any]:
        return self.read_payload(self.output / f"points/FPT-{self.fx.cutoff}.json", "point")

    def history(self) -> None:
        """Kho gồm prior đóng, exit bằng cutoff, vắt ngang và future cho hai symbol."""
        self.fx.records = [self.record(symbol, position) for symbol in ("FPT", "MWG")
                           for position in ((600, 603, 606, 641, 644, 650) if symbol == "FPT"
                                            else (600, 603, 606, 642, 645, 650))]
        self.fx.publish_bank("a" * 64)
        model_file(self.fx.root / f"run/regimes/VNINDEX-{self.fx.day(643)}.json", self.fx.vnindex.iloc[:644])

    def record(self, symbol: str, position: int) -> dict[str, Any]:
        """Mỗi nhãn kể cả MWG được sinh bằng đúng hàm kinh tế engine."""
        row = self.fx.record(position, self.fx.regime["regime_name"])
        frame = self.fx.frame[symbol]
        net = float(100 * compute_round_trip_net_return(float(frame.Open.iloc[position + 1]),
                                                       float(frame.Close.iloc[position + 3])))
        row.update(symbol=symbol, episode_id=f"{symbol}:{row['as_of_date']}")
        row["outcome"] = {"actual_direction": "UP" if net > 0 else "DOWN", "net_return_pct": net,
            "result": "WIN_IF_LONG" if net > 0 else "LOSS_IF_LONG", "was_bull_trap": bool(net <= 0)}
        return row

    def graph_matrix(self, adapter: PriorContextAdapter, cutoff: str | None = None) -> dict:
        """Graph thật cho cả pooled; runner nghiên cứu vẫn khóa same_symbol."""
        cutoff = cutoff or self.fx.cutoff
        point = adapter.prepare("FPT", cutoff)
        shared = point.bind_full(self.fx.full(point))
        bundles = {}
        for scope in SCOPES:
            for branch, (mode, k) in PRIOR_BRANCH_MODES.items():
                state = deepcopy(shared)
                state["prior_config"].update(scope=scope, mode=mode, k=k)
                graph = self.builder.compile_report_decision(prior_config=state["prior_config"],
                    prior_retriever=point.retrieve, prior_source_validator=point.verify_source)
                bundles[(scope, branch)] = graph.invoke(state)
        return bundles

    def assert_same_evidence(self, before: dict, after: dict) -> None:
        """Hash toàn kho/nguồn có thể đổi; bằng chứng tại cutoff phải giữ nguyên."""
        for key, first in before.items():
            second = after[key]
            for field in ("prior_tasks", "prior_stats", "bayesian_prior_context", "decision_prompt",
                          "final_trade_decision", "current_signals", "market_regime"):
                self.assertEqual(first[field], second[field], (key, field))
            for field in first["prior_metadata"]:
                if field != "bank_sha256":
                    self.assertEqual(first["prior_metadata"][field], second["prior_metadata"][field], (key, field))

    def test_public_run_checks_snapshot_and_feature_prefix_before_upstream(self) -> None:
        for provider in PROVIDERS:
            adapter = self.adapter_for(provider)
            prepare = adapter.prepare
            snapshot = self.fx.frame["FPT"].loc[:, ["Datetime", "Open", "High", "Low", "Close", "Volume"]]
            changed = snapshot.iloc[:645].copy()
            changed.loc[0, "Close"] += .01
            cases = ({"point_in_time_df": snapshot.iloc[:646]}, {"point_in_time_df": snapshot.iloc[:644]},
                     {"point_in_time_df": changed}, {"vnindex_prefix": self.fx.vnindex.iloc[:646]},
                     {"vnindex_prefix": self.fx.vnindex.iloc[1:645]})
            for index, inputs in enumerate(cases):
                self.output = self.fx.root / f"bad-snapshot-{provider}-{index}"
                with (self.subTest(provider=provider, inputs=list(inputs)),
                      patch.object(adapter, "prepare", side_effect=lambda *a, **kw: prepare(*a, **kw, **inputs)),
                      patch.object(adapter._retriever, "retrieve", wraps=adapter._retriever.retrieve) as retrieve,
                      self.assertRaises(ValueError)):
                    self.run_fixture(adapter=adapter, cutoffs=(self.fx.cutoff,))
                retrieve.assert_not_called()
                self.assertFalse(self.output.exists())
        self.assertEqual(self.events, [])
        self.assertEqual(self.llm.calls, 0)
        self.compute.assert_not_called()

    def test_every_pipeline_boundary_only_receives_pit_query_inputs(self) -> None:
        for provider in PROVIDERS:
            adapter = self.adapter_for(provider)
            self.output = self.fx.root / f"boundaries-{provider}"
            self.fresh_engine()
            seen = []
            chart = self.candle.side_effect
            def capture_chart(data, **kwargs):
                self.assertEqual(data, snapshot_payload(self.fx.frame["FPT"].iloc[600:645]))
                return {"pattern_image": "image-pit"}
            compute = self.compute.side_effect
            def capture_alpha(data, *args, **kwargs):
                frame = kwargs["historical_df"]
                self.assertLessEqual(frame.Datetime.max().strftime("%Y-%m-%d"), self.fx.cutoff)
                self.assertEqual(len(frame.tail(600)), 600)
                self.assertEqual(kwargs["as_of_date"], self.fx.cutoff)
                return compute(data, *args, **kwargs)
            compile_graph = self.builder.compile_report_decision
            def compile_checked(**kwargs):
                callback = kwargs["before_decision"]
                def capture(state, prompt):
                    self.assertTrue(set(state).isdisjoint({"outcome", "evaluation", "actual_direction", "entry_open", "exit_close"}))
                    self.assertNotIn("point_in_time_df", state)
                    self.assertNotIn("net_return_long", prompt)
                    self.assertNotIn("exit_close", prompt)
                    self.assertTrue(all(task["exit_date"] < self.fx.cutoff for task in state["prior_tasks"]))
                    seen.append(state["prior_config"]["mode"])
                    return callback(state, prompt)
                return compile_graph(**{**kwargs, "before_decision": capture})
            self.candle.side_effect, self.compute.side_effect = capture_chart, capture_alpha
            try:
                with patch.object(self.builder, "compile_report_decision", side_effect=compile_checked):
                    self.run_fixture(adapter=adapter, cutoffs=(self.fx.cutoff,))
            finally:
                self.candle.side_effect, self.compute.side_effect = chart, compute
            payload = self.point_payload()
            self.assertEqual(len(seen), 5)
            self.assertEqual(payload["evaluation"]["exit_date"], self.fx.day(647))
            self.assertEqual(payload["shared"]["stage"], "shared_complete")
        self.assertEqual(self.events, ["indicator", "pattern", "trend", "full"] * 2)
        self.assertEqual(self.llm.calls, 10)

    def test_news_filter_coverage_and_sparse_neutral_survive_all_five_prompts(self) -> None:
        cutoff = date.fromisoformat(self.fx.cutoff)
        def article(day, title):
            return {"date_parsed": day, "label": "positive", "numeric_score": 1., "title": title, "content": title}
        excluded = [article(None, "UNDATED_SENTINEL"), article(self.fx.day(645), "FUTURE_SENTINEL"),
                    article((cutoff - timedelta(days=91)).isoformat(), "STALE_SENTINEL")]
        for count in (2, 18):
            rows = [article(self.fx.cutoff, f"PAST_SENTINEL_{i}") for i in range(count)] + excluded
            write_json(self.fx.root / "run/inputs/news/FPT.json", {"symbol": "FPT", "scored_articles": rows})
            self.adapter = self.fx.adapter()
            self.output = self.fx.root / f"news-{count}"
            self.fresh_engine()
            self.run_fixture(cutoffs=(self.fx.cutoff,))
            payload = self.point_payload()
            news = payload["source_proof"]["news"]
            self.assertEqual(news["visible_count"], count)
            self.assertEqual(news["excluded_counts"], {"undated": 1, "future": 1, "outside_window": 1})
            bundle = payload["shared"]["full_bundle"]
            self.assertEqual(len(bundle["sentiment_data"]["scored_articles"]), min(count, 15))
            self.assertEqual(bundle["current_signals"]["sentiment"], "NEUTRAL" if count == 2 else "POSITIVE")
            self.assertEqual(news["neutral_reason"], "INSUFFICIENT_DATED_HISTORY" if count == 2 else None)
            for branch in payload["branches"].values():
                prompt = branch["input"]["prompt"]["text"]
                for row in excluded:
                    self.assertNotIn(row["title"], prompt)
                if count == 2:
                    self.assertNotIn("PAST_SENTINEL_", prompt)
                    self.assertEqual(bundle["sentiment_data"]["main_sentiment"]["avg_score"], 0.)

    def test_future_or_invalid_model_components_stop_public_run_before_agents(self) -> None:
        for provider in PROVIDERS:
            path = self.fx.root / (f"run/regimes/VNINDEX-{self.fx.cutoff}.json" if provider == "historical_prefix" else "model/fixed.json")
            original = path.read_bytes()
            try:
                for mutation in ("train_future", "scaler", "calibration", "training_hash"):
                    path.write_bytes(original)
                    if mutation == "train_future":
                        model_file(path, self.fx.vnindex.iloc[:646])
                    else:
                        envelope = json.loads(original)
                        payload = envelope["payload"]
                        if mutation == "scaler":
                            payload["scaler"]["scale"][0] = 2.
                        elif mutation == "calibration":
                            payload["metadata"]["latent_state_names"] = ["BULL"] * 4
                        else:
                            payload["metadata"]["training_data_sha256"] = "b" * 64
                        envelope["sha256"] = _payload_hash(payload)
                        write_json(path, envelope)
                    self.output = self.fx.root / f"bad-model-{provider}-{mutation}"
                    with self.subTest(provider=provider, mutation=mutation), self.assertRaises(ValueError):
                        self.run_fixture(adapter=self.adapter_for(provider), cutoffs=(self.fx.cutoff,))
                    self.assertFalse(self.output.exists())
            finally:
                path.write_bytes(original)
        self.assertEqual(self.events, [])
        self.assertEqual(self.llm.calls, 0)

    def test_injected_provider_wrong_dates_hash_and_training_proof_stop_before_agents(self) -> None:
        adapter = self.fx.adapter()
        proof = adapter._provider.get(self.fx.cutoff, verify_only=True)
        cases = (("state", "feature_end_date", self.fx.day(645)), ("state", "as_of_date", self.fx.day(647)),
                 ("metadata", "train_end_date", self.fx.day(645)), ("metadata", "training_data_sha256", "b" * 64),
                 ("state", "trend_strength", 0.123456789),
                 (None, "artifact_sha256", "b" * 64))
        for index, (group, field, value) in enumerate(cases):
            wrong = deepcopy(proof)
            (wrong if group is None else wrong[group])[field] = value
            self.output = self.fx.root / f"bad-provider-{index}"
            with (self.subTest(field=field), patch.object(adapter._provider, "get", return_value=wrong),
                  self.assertRaises(ValueError)):
                self.run_fixture(adapter=adapter, cutoffs=(self.fx.cutoff,))
            self.assertFalse(self.output.exists())
        self.assertEqual(self.events, [])
        self.assertEqual(self.llm.calls, 0)

    def test_equal_exit_straddling_future_excluded_in_graph_tasks_ranking_stats_prefix(self) -> None:
        self.history()
        for provider in PROVIDERS:
            adapter = self.adapter_for(provider)
            for cutoff in (self.fx.day(643), self.fx.cutoff):
                bundles = self.graph_matrix(adapter, cutoff)
                for (scope, name), state in bundles.items():
                    self.check_boundary_evidence(provider, cutoff, scope, name, state)
        self.assertEqual(self.llm.calls, 40)

    def check_boundary_evidence(self, provider: str, cutoff: str, scope: str, name: str, state: dict) -> None:
        """Cùng cutoff 643/644 lần lượt chứng minh vắt ngang và exit bằng ngày query."""
        with self.subTest(provider=provider, cutoff=cutoff, scope=scope, branch=name):
            metadata = state["prior_metadata"]
            if name == "original":
                self.assertIsNone(state["prior_stats"])
                self.assertEqual(state["prior_tasks"], [])
                self.assertEqual(state["bayesian_prior_context"], "")
                return
            eligible = [r for r in self.fx.records if r["exit_date"] < cutoff
                        and (scope == "pooled" or r["symbol"] == "FPT")]
            population = [r for r in eligible if r["regime"] == state["market_regime"]["regime_name"]]
            self.assertEqual(metadata["eligible_count"], 3 if scope == "same_symbol" else 6)
            self.assertEqual(state["prior_stats"]["population_count"], len(population))
            self.assertEqual(state["prior_stats"]["metrics"]["win_rate_long"]["denominator"], len(population))
            self.assertEqual(state["prior_stats"]["metrics"]["win_rate_long"]["numerator"], 0)
            self.assertEqual(state["prior_stats"]["metrics"]["win_rate_long"]["rate"], 0. if population else None)
            self.assertTrue(all(task in eligible for task in state["prior_tasks"]))
            self.assertEqual(metadata["selected_ids"], [r["episode_id"] for r in state["prior_tasks"]])
            if name in ("recent", "similarity", "bayesian"):
                expected = [f"FPT:{self.fx.day(p)}" for p in (606, 603, 600)] if scope == "same_symbol" else [
                    f"FPT:{self.fx.day(606)}", f"MWG:{self.fx.day(606)}", f"FPT:{self.fx.day(603)}"]
                self.assertEqual(metadata["selected_ids"], [] if name == "bayesian" and not population else expected)
            if name in ("similarity", "bayesian"):
                self.assertTrue(all(item["score"] == 1. for item in metadata["selected_scores"]))
            for position in (641, 642, 644, 645, 650):
                self.assertNotIn("@" + self.fx.day(position), state["bayesian_prior_context"])
            self.assertEqual(state["bayesian_prior_context"], format_compact_prior_prefix(state["prior_tasks"], state["prior_stats"]))

    def test_unclosed_history_append_and_mutation_leave_old_graph_evidence_unchanged(self) -> None:
        self.history()
        before = {provider: self.graph_matrix(self.adapter_for(provider)) for provider in PROVIDERS}
        self.fx.records.extend(self.record(symbol, 660) for symbol in ("FPT", "MWG"))
        for row in self.fx.records:
            if row["exit_date"] >= self.fx.cutoff:
                row["regime"] = "BEAR" if row["regime"] != "BEAR" else "BULL"
                row["agent_signals"].update(trend="BEARISH", pattern="BULLISH", alpha_consensus="BULLISH")
                row["outcome"]["was_bull_trap"] = row["outcome"]["result"] == "LOSS_IF_LONG"
        self.fx.publish_bank("a" * 64)
        for provider in PROVIDERS:
            after = self.graph_matrix(self.adapter_for(provider))
            self.assert_same_evidence(before[provider], after)
            for key in before[provider]:
                self.assertNotEqual(before[provider][key]["prior_metadata"]["bank_sha256"], after[key]["prior_metadata"]["bank_sha256"])
        self.assertEqual(self.llm.calls, 40)

    def test_later_then_earlier_graph_queries_do_not_reuse_future_evidence(self) -> None:
        self.history()
        model_file(self.fx.root / f"run/regimes/VNINDEX-{self.fx.day(660)}.json", self.fx.vnindex.iloc[:661])
        for provider in PROVIDERS:
            adapter = self.adapter_for(provider)
            early = self.graph_matrix(adapter)
            later = self.graph_matrix(adapter, self.fx.day(660))
            self.assertGreater(later[("pooled", "recent")]["prior_metadata"]["eligible_count"],
                               early[("pooled", "recent")]["prior_metadata"]["eligible_count"])
            self.assert_same_evidence(early, self.graph_matrix(adapter))
        self.assertEqual(self.llm.calls, 60)

    def test_injected_pool_selectors_and_population_stop_before_formatter_or_llm(self) -> None:
        self.history()
        adapter = self.fx.adapter()
        point = adapter.prepare("FPT", self.fx.cutoff)
        shared = point.bind_full(self.fx.full(point))
        retriever = adapter._retriever
        future = next(row for row in self.fx.records if row["as_of_date"] == self.fx.cutoff and row["symbol"] == "FPT")
        for scope in SCOPES:
            for mode in ("random", "recent", "similarity", "bayesian_regime"):
                state = deepcopy(shared)
                state["prior_config"].update(scope=scope, mode=mode)
                graph = self.builder.compile_report_decision(prior_config=state["prior_config"],
                    prior_retriever=point.retrieve, prior_source_validator=point.verify_source)
                query = point._query(state)
                selected = retriever.select_prior_tasks(**query)
                selected["regime_population"].append(future)
                selector = "_select_recent" if mode == "recent" else "_select_random" if mode == "random" else "_select_similarity"
                value = [future] if mode == "recent" else ([future], "a" * 64) if mode == "random" else ([future], {future["episode_id"]: 1.})
                mutations = ((retriever._memory, "eligible", [future]), (retriever, selector, value),
                             (retriever, "select_prior_tasks", selected))
                for owner, method, returned in mutations:
                    with (self.subTest(scope=scope, mode=mode, method=method),
                          patch.object(owner, method, return_value=deepcopy(returned)),
                          patch("core.bayesian_retriever.format_compact_prior_prefix", wraps=format_compact_prior_prefix) as formatter,
                          self.assertRaises(ValueError)):
                        graph.invoke(state)
                    formatter.assert_not_called()
        self.assertEqual(self.llm.calls, 0)

    def test_future_execution_outcome_changes_evaluation_without_changing_decisions(self) -> None:
        self.run_fixture(cutoffs=(self.fx.cutoff,))
        before = self.point_payload()
        directory = self.fx.root / "data/execution_prices"
        evidence_path = directory / "FPT.evidence.json.gz"
        evidence = json.loads(gzip.decompress(evidence_path.read_bytes()))
        previous = None
        for row in evidence["records"]:
            if row["tradingDate"] > self.fx.cutoff:
                row["closePrice"] *= 1.02
                row["highestPrice"] = max(row["highestPrice"], row["closePrice"] + 1000)
                row["matchPrice"] = row["closePrice"]
                row["referencePrice"] = previous
            previous = row["closePrice"]
        from core.execution_prices import normalise_vci_execution_prices
        frame = normalise_vci_execution_prices(evidence["records"], "FPT", self.fx.day(0), self.fx.day(699))
        csv_path = directory / "FPT.csv"
        prefix = csv_path.read_text("utf-8").splitlines(keepends=True)[:646]
        csv_path.write_text("".join(prefix) + frame.loc[frame.Datetime > self.fx.cutoff].to_csv(
            index=False, header=False, date_format="%Y-%m-%d", float_format="%.17g"), encoding="utf-8")
        evidence_path.write_bytes(gzip.compress(json.dumps(evidence).encode("utf-8")))
        manifest_path = directory / "manifest.json"
        manifest = json.loads(manifest_path.read_text("utf-8"))
        for key, path in (("csv", csv_path), ("evidence", evidence_path)):
            manifest["files"]["FPT"][key]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        write_json(manifest_path, manifest)
        self.fx.frame["FPT"] = frame
        self.fx.records[-1] = self.record("FPT", 644)
        self.fx.publish_bank("a" * 64)
        self.adapter = self.fx.adapter()
        self.output = self.fx.root / "changed-future-execution"
        self.fresh_engine()
        self.run_fixture(cutoffs=(self.fx.cutoff,))
        after = self.point_payload()
        self.assertNotEqual(before["evaluation"], after["evaluation"])
        self.assertEqual(before["shared"]["full_bundle"]["current_signals"], after["shared"]["full_bundle"]["current_signals"])
        for name in PRIOR_BRANCH_MODES:
            first, second = before["branches"][name], after["branches"][name]
            for field in ("prior_tasks", "prior_stats", "bayesian_prior_context", "prompt"):
                self.assertEqual(first["input"][field], second["input"][field])
            self.assertEqual(first["decision"]["normalized_response"], second["decision"]["normalized_response"])
        self.assertEqual(after["evaluation"]["net_return_long"],
                         compute_round_trip_net_return(after["evaluation"]["entry_open"], after["evaluation"]["exit_close"]))

    def test_rehashed_checkpoint_future_sources_cannot_resume_either_provider(self) -> None:
        class Crash(BaseException):
            """Gián đoạn không ghi thêm status, tương tự tiến trình mất sau commit."""
        def stop(session, event):
            if event == "branch_complete:random":
                raise Crash()
        for provider in PROVIDERS:
            adapter = self.adapter_for(provider)
            self.output = self.fx.root / f"checkpoint-{provider}"
            self.fresh_engine()
            with patch.object(CheckpointSession, "_after_commit", stop), self.assertRaises(Crash):
                self.run_fixture(adapter=adapter, cutoffs=(self.fx.cutoff,))
            path = self.output / f"points/FPT-{self.fx.cutoff}.json"
            original, calls, events = path.read_bytes(), self.llm.calls, list(self.events)
            for field in ("cutoff", "price", "news", "hmm", "scaler", "calibration"):
                document = json.loads(original)["payload"]
                proof = document["source_proof"]
                if field == "cutoff":
                    document["context"]["as_of_date"] = self.fx.day(645)
                elif field == "price":
                    proof["prices"]["alpha_end_date"] = self.fx.day(645)
                elif field == "news":
                    proof["news"]["coverage_end_date"] = self.fx.day(645)
                else:
                    proof["regime"]["component_train_end_dates"][field] = self.fx.day(645)
                document["source_sha256"] = canonical_hash(proof)
                atomic_write_json(path, {"payload": document, "sha256": canonical_hash(document)})
                modified = path.read_bytes()
                self.fresh_engine()
                with self.subTest(provider=provider, field=field), self.assertRaises(ValueError):
                    self.run_fixture(adapter=adapter, cutoffs=(self.fx.cutoff,), resume=True)
                self.assertEqual(path.read_bytes(), modified)
                self.assertEqual(self.llm.calls, calls)
                self.assertEqual(self.events, events)
            path.write_bytes(original)


if __name__ == "__main__":
    unittest.main()
