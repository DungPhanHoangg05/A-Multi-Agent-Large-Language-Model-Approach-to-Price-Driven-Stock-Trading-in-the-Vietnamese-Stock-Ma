"""Kiểm adapter nguồn thật trên file fixture: không fit, crawl, API hoặc archive local."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from core import prior_context
from core.bayesian_retriever import format_compact_prior_prefix
from core.historical_signals import digest
from core.regime_detector import MarketRegimeDetector
from prior_context_test_support import ContextFixture, envelope, write_json
from test_backtest_token_budget import _CountingLlm, _StructuredCountingLlm
from utils.graph_setup import SetGraph


class PriorContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.stack = []
        for target in ("builtins.print", "core.regime_detector.MarketRegimeDetector.fit",
                       "data_manager.sentiment_cache.SentimentCache.preload"):
            guard = patch(target) if target == "builtins.print" else patch(target, side_effect=AssertionError("Cấm fit/crawl"))
            self.stack.append(guard.start())
            self.addCleanup(guard.stop)
        self.fixture = ContextFixture()
        self.addCleanup(self.fixture.close)

    def test_prefix_context_binds_actual_sources_before_upstream(self) -> None:
        fx = self.fixture
        # Manifest archive W1 dùng 1D; query/proof vẫn chuẩn hóa về 1d.
        manifest_path = fx.root / "data/historical/manifest.json"
        manifest = json.loads(manifest_path.read_text("utf-8"))
        manifest["interval"] = "1D"
        write_json(manifest_path, manifest)
        adapter = fx.adapter()
        with patch.object(adapter._provider, "get", wraps=adapter._provider.get) as get:
            point = adapter.prepare("FPT", fx.cutoff, time_frame="1 ngày")
        get.assert_called_once_with(fx.cutoff, verify_only=True)
        proof = point.source_provenance
        self.assertNotIn("signals", proof)
        self.assertEqual(proof["regime"]["metadata"]["train_end_date"], fx.cutoff)
        self.assertEqual(set(proof["regime"]["component_train_end_dates"].values()), {fx.cutoff})
        self.assertIsNone(proof["regime"]["frozen_model"])
        state = point.agent_state()
        self.assertNotIn("prior_config", state)
        self.assertEqual(state["as_of_date"], state["window_end_date"])
        self.assertEqual(len(state["point_in_time_df"]), 645)
        self.assertEqual(len(state["kline_data"]["Datetime"]), 45)
        self.assertEqual(proof["prices"]["alpha_rows"], 600)
        self.assertEqual(proof["prices"]["alpha_start_date"], fx.day(45))
        for group in ("prices", "news", "regime", "bank"):
            for field, value in proof[group].items():
                if field.endswith("_path"):
                    checksum = field.replace("_path", "_sha256")
                    if checksum in proof[group]:
                        self.assertEqual(hashlib.sha256((fx.root / value).read_bytes()).hexdigest(), proof[group][checksum])

    def test_both_providers_all_modes_k_languages_and_llm_routes_use_verified_hooks(self) -> None:
        fx = self.fixture
        for lang in ("vi", "en"):
            fx.config["language"] = lang
            for provider in ("historical_prefix", "fixed_train_oos"):
                options = {} if provider == "historical_prefix" else {
                    "provider_mode": provider, "frozen_artifact_path": "model/fixed.json", "freeze_as_of_date": fx.day(620)}
                adapter = fx.adapter(**options)
                point = adapter.prepare("FPT", fx.cutoff)
                shared = point.bind_full(fx.full(point))
                proof = shared["prior_provenance"]
                self.assertEqual(set(proof), {"contract_version", "context", "prices", "news", "regime", "signals", "bank"})
                self.assertEqual(proof["signals"]["origin"], "shared_full")
                self.assertEqual(proof["signals"]["signals_sha256"], digest(shared["current_signals"]))
                self.assertEqual(proof["signals"]["reports_sha256"], digest({field: shared[field] for field in prior_context.REPORT_FIELDS}))
                self.assertEqual(shared["current_signals"], {"trend": "BULLISH", "pattern": "NEUTRAL",
                    "indicator_consensus": "BEARISH", "alpha_consensus": "NEUTRAL", "sentiment": "NEUTRAL"})
                before = deepcopy(shared)
                for mode in ("bayesian_regime", "random", "recent", "similarity"):
                    for k in range(4):
                        for structured in (False, True):
                            with self.subTest(provider=provider, lang=lang, mode=mode, k=k, structured=structured):
                                state = deepcopy(shared)
                                state["prior_config"].update(mode=mode, k=k)
                                llm = _StructuredCountingLlm() if structured else _CountingLlm()
                                with (patch.object(adapter._retriever, "retrieve", wraps=adapter._retriever.retrieve) as retrieve,
                                      patch("core.bayesian_retriever.format_compact_prior_prefix", wraps=format_compact_prior_prefix) as formatter):
                                    result = SetGraph(llm, object(), object()).compile_report_decision(
                                        prior_config=state["prior_config"], prior_retriever=point.retrieve,
                                        prior_source_validator=point.verify_source).invoke(state)
                                retrieve.assert_called_once()
                                formatter.assert_called_once()
                                self.assertEqual(result["prior_provenance"], proof)
                                self.assertLess(len(result["decision_prompt"]), 6500)
                                self.assertTrue(all(task["exit_date"] < fx.cutoff for task in result["prior_tasks"]))
                                self.assertEqual(len(llm.structured_prompts if structured else llm.prompts), 1)
                                if k == 0:
                                    self.assertEqual(result["bayesian_prior_context"], "")
                                    self.assertIsNone(result["prior_stats"])
                self.assertEqual(shared, before)

    def test_fixed_model_loaded_once_and_parameters_remain_frozen(self) -> None:
        fx = self.fixture
        with patch.object(MarketRegimeDetector, "load", wraps=MarketRegimeDetector.load) as load:
            adapter = fx.adapter(provider_mode="fixed_train_oos", frozen_artifact_path="model/fixed.json", freeze_as_of_date=fx.day(620))
            before = deepcopy(adapter._fixed.metadata)
            point = adapter.prepare("FPT", fx.cutoff)
            adapter.prepare("FPT", fx.day(645))
        load.assert_called_once()
        self.assertEqual(before, adapter._fixed.metadata)
        frozen = point.source_provenance["regime"]["frozen_model"]
        self.assertEqual(frozen["freeze_as_of_date"], fx.day(620))
        self.assertEqual(frozen["training_data_sha256"], before["training_data_sha256"])

    def test_fresh_source_proof_and_agent_state_are_owned_copies(self) -> None:
        point = self.fixture.adapter().prepare("FPT", self.fixture.cutoff)
        proof = point.source_provenance
        proof["regime"]["metadata"]["train_end_date"] = "2099-01-01"
        state = point.agent_state()
        state["point_in_time_df"].loc[0, "Close"] = 1.
        state["kline_data"]["Close"][0] = 1.
        state["sentiment_store"].data["n_articles_used"] = 999
        fresh = point.agent_state()
        self.assertNotEqual(fresh["point_in_time_df"].Close.iloc[0], 1.)
        self.assertNotEqual(fresh["kline_data"]["Close"][0], 1.)
        self.assertEqual(fresh["sentiment_store"].data["n_articles_used"], 0)
        self.assertEqual(point.source_provenance["regime"]["metadata"]["train_end_date"], self.fixture.cutoff)

    def test_source_callback_compares_every_provenance_group_and_native_type(self) -> None:
        point = self.fixture.adapter().prepare("FPT", self.fixture.cutoff)
        shared = point.bind_full(self.fixture.full(point))
        changes = [("prices", "snapshot_rows", True), ("news", "visible_count", False),
                   ("regime", "artifact_sha256", "a" * 64), ("signals", "origin", "historical_signal_checkpoint"),
                   ("bank", "bank_sha256", "b" * 64), ("context", "as_of_date", self.fixture.day(643))]
        for group, field, value in changes:
            wrong = deepcopy(shared)
            wrong["prior_provenance"][group][field] = value
            with self.subTest(group=group), self.assertRaises(ValueError):
                point.verify_source(wrong)
        wrong = deepcopy(shared)
        wrong["prior_provenance"]["status"] = "PASS"
        with self.assertRaises(ValueError):
            point.verify_source(wrong)

    def test_result_is_compared_with_own_verified_retriever_not_self_reported_counts(self) -> None:
        point = self.fixture.adapter().prepare("FPT", self.fixture.cutoff)
        shared = point.bind_full(self.fixture.full(point))
        result = point.retrieve(shared)
        projection = {**shared, **{f"prior_{key}": value for key, value in result.items()}}
        point.verify_source(projection)
        for field in ("tasks", "stats", "metadata"):
            wrong = deepcopy(projection)
            wrong[f"prior_{field}"] = [{"episode_id": "foreign"}] if field == "tasks" else {}
            with self.subTest(field=field), self.assertRaises(ValueError):
                point.verify_source(wrong)
        changed = deepcopy(result)
        changed["metadata"]["selected_ids"].append("foreign")
        self.assertNotEqual(changed, point.retrieve(shared))

    def test_metadata_cannot_be_verified_before_actual_retrieve_and_full_seal(self) -> None:
        point = self.fixture.adapter().prepare("FPT", self.fixture.cutoff)
        with self.assertRaises(ValueError):
            point.retrieve({})
        with self.assertRaises(ValueError):
            point.verify_source({})
        shared = point.bind_full(self.fixture.full(point))
        with self.assertRaises(ValueError):
            point.verify_source({**shared, "prior_metadata": {"status": "PASS"}})

    def test_graph_rejects_source_before_real_retrieval_or_llm(self) -> None:
        fx = self.fixture
        adapter = fx.adapter()
        point = adapter.prepare("FPT", fx.cutoff)
        shared = point.bind_full(fx.full(point))
        wrong = deepcopy(shared)
        wrong["market_regime"]["regime_name"] = "BULL" if shared["market_regime"]["regime_name"] != "BULL" else "BEAR"
        llm = _CountingLlm()
        with patch.object(adapter._retriever, "retrieve") as retrieve:
            graph = SetGraph(llm, object(), object()).compile_report_decision(
                prior_config=shared["prior_config"], prior_retriever=point.retrieve, prior_source_validator=point.verify_source)
            with self.assertRaises(ValueError):
                graph.invoke(wrong)
        retrieve.assert_not_called()
        self.assertEqual(llm.calls, 0)

    def test_fresh_full_missing_reports_templates_and_factor_mismatches_are_errors(self) -> None:
        point = self.fixture.adapter().prepare("FPT", self.fixture.cutoff)
        valid = self.fixture.full(point)
        cases = [{**valid, "trend_report": "Hướng xu hướng: Tăng|Giảm\n"},
                 {**valid, "indicator_report": "Đồng thuận chủ đạo: FUTURE_WIN\n"},
                 {**valid, "pattern_report": ""}, {**valid, "alpha_report": "TỔNG HỢP: Tăng\n"},
                 {**valid, "sentiment_report": "Nhận định: POSITIVE"}]
        wrong = deepcopy(valid)
        wrong["sentiment_data"]["alpha_results"][0]["signal"] = "GIẢM"
        cases.append(wrong)
        wrong = deepcopy(valid)
        wrong["sentiment_data"]["alpha_results"][1]["id"] = 1
        cases.append(wrong)
        for state in cases:
            with self.subTest(reports=[state.get(key) for key in prior_context.REPORT_FIELDS]), self.assertRaises(ValueError):
                point.bind_full(state)
        self.assertIsNone(point._shared)

    def test_fresh_full_snapshot_window_config_and_query_outcome_are_bound(self) -> None:
        point = self.fixture.adapter().prepare("FPT", self.fixture.cutoff)
        base = self.fixture.full(point)
        cases = [{**base, "stock_name": "MWG"}, {**base, "as_of_date": self.fixture.day(643)},
                 {**base, "time_frame": "1w"}, {**base, "alpha_norm_method": "minmax"},
                 {**base, "language": "en"}, {**base, "alpha_weights": {"ic": 1.}},
                 {**base, "kline_data": {}}, {**base, "window_end_date": self.fixture.day(643)}]
        for field in prior_context._FORBIDDEN:
            cases.append({**base, field: "future"})
        wrong = deepcopy(base)
        wrong["point_in_time_df"].loc[0, "Close"] *= 1.001
        cases.append(wrong)
        for state in cases:
            with self.subTest(keys=list(state)), self.assertRaises(ValueError):
                point.bind_full(state)

    def test_full_cannot_be_replaced_after_seal_or_mutated_through_output(self) -> None:
        point = self.fixture.adapter().prepare("FPT", self.fixture.cutoff)
        full = self.fixture.full(point)
        shared = point.bind_full(full)
        shared["current_signals"]["trend"] = "BEARISH"
        self.assertEqual(point.bind_full(full)["current_signals"]["trend"], "BULLISH")
        wrong = {**full, "trend_report": full["trend_report"] + "Thêm lời bình khác."}
        with self.assertRaises(ValueError):
            point.bind_full(wrong)

    def test_valid_historical_journal_preserves_origin_identity_and_checks_signals(self) -> None:
        fx = self.fixture
        fx.make_replay()
        point = fx.adapter(signal_config=None).prepare("FPT", fx.cutoff)
        with self.assertRaises(ValueError):
            point.agent_state()
        shared = point.load_shared_checkpoint("run")
        proof = shared["prior_provenance"]["signals"]
        self.assertEqual(proof["origin"], "historical_signal_checkpoint")
        self.assertEqual(proof["checkpoint_sha256"], hashlib.sha256((fx.root / proof["checkpoint_path"]).read_bytes()).hexdigest())
        self.assertEqual(set(proof["code_sha256"]), set(prior_context.CODE_FILES))
        self.assertNotEqual(proof["code_sha256"]["utils/graph_setup.py"], hashlib.sha256(
            (prior_context.ROOT / "utils/graph_setup.py").read_text("utf-8").encode()).hexdigest())
        self.assertEqual(proof["runtime"]["python"], "historical-fixture")
        self.assertNotIn("outcome", shared)
        result = point.retrieve(shared)
        point.verify_source({**shared, **{f"prior_{key}": value for key, value in result.items()}})

    def test_historical_stage_signature_regime_and_report_binding_are_strict(self) -> None:
        fx = self.fixture
        fx.make_replay()
        paths = [fx.root / f"run/signals/FPT-{fx.cutoff}.json", fx.root / f"run/episodes/FPT-{fx.cutoff}.json"]
        original = [path.read_bytes() for path in paths]
        for kind in ("stage", "signature", "reports", "regime", "code", "dates", "signals", "record_type", "proof_type"):
            for path, content in zip(paths, original):
                path.write_bytes(content)
            checkpoint = json.loads(paths[0].read_text("utf-8"))["payload"]
            episode = json.loads(paths[1].read_text("utf-8"))["payload"]
            if kind == "stage":
                checkpoint["stage"] = "UPSTREAM_COMPLETE"
            elif kind == "signature":
                checkpoint["signature"] = "b" * 64
            elif kind == "reports":
                checkpoint["result"]["reports"]["trend_report"] = "Hướng xu hướng: Giảm\n"
            elif kind == "regime":
                episode["provenance"]["regime"]["metadata"]["train_end_date"] = fx.day(643)
            elif kind == "code":
                checkpoint["result"]["provenance"]["code_sha256"]["utils/graph_setup.py"] = "b" * 64
            elif kind == "dates":
                checkpoint["result"]["provenance"]["news_dates"] = [fx.day(645)]
            elif kind == "record_type":
                episode["record"] = []
            elif kind == "proof_type":
                episode["provenance"]["regime"] = []
            else:
                checkpoint["result"]["agent_signals"]["trend"] = "BEARISH"
            envelope(paths[0], checkpoint)
            episode["provenance"]["signal_checkpoint_sha256"] = hashlib.sha256(paths[0].read_bytes()).hexdigest()
            envelope(paths[1], episode)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                fx.adapter().prepare("FPT", fx.cutoff).load_shared_checkpoint("run")

    def test_disabled_and_unsupported_provider_options_do_not_read_new_sources(self) -> None:
        cases = [("disabled", {"prior_config": {}}), ("provider", {"provider_mode": "enum_only"}),
                 ("window", {"window_size": True}), ("prefix_frozen", {"frozen_artifact_path": "model/fixed.json"}),
                 ("fixed_missing", {"provider_mode": "fixed_train_oos"})]
        with patch.object(Path, "read_bytes", side_effect=AssertionError("Đọc nguồn khi config sai")):
            for name, changes in cases:
                config = changes.pop("prior_config", self.fixture.prior_config)
                with self.subTest(name=name), self.assertRaises(ValueError):
                    prior_context.PriorContextAdapter(config, root=self.fixture.root, **changes)

    def test_constructor_checks_file_hashes_price_gate_sources_and_bank_qa(self) -> None:
        fx = self.fixture
        manifest_path = fx.root / "data/execution_prices/manifest.json"
        original = manifest_path.read_bytes()
        for field, value in (("primary_source", "KBS"), ("crosscheck_sources", ["VCI", "SSI"]),
                             ("price_basis", "ADJUSTED"), ("price_unit", "VND"),
                             ("source_library", "other"), ("price_gate", "FAIL")):
            manifest_path.write_bytes(original)
            manifest = json.loads(original)
            manifest[field] = value
            write_json(manifest_path, manifest)
            with self.subTest(field=field), self.assertRaises(ValueError):
                fx.adapter()
        manifest_path.write_bytes(original)
        retriever = fx.retriever()
        audit_path = fx.root / "bank/audit.json"
        audit = json.loads(audit_path.read_text("utf-8"))
        audit["schema_sha256"] = "b" * 64
        write_json(audit_path, audit)
        with self.assertRaises(ValueError):
            fx.adapter(retriever=retriever)

    def test_graph_callbacks_do_not_parse_json_fit_crawl_or_reload_retriever(self) -> None:
        point = self.fixture.adapter().prepare("FPT", self.fixture.cutoff)
        shared = point.bind_full(self.fixture.full(point))
        with (patch("core.prior_context.read_json", side_effect=AssertionError("Parse JSON sau chuẩn bị nguồn")),
              patch("core.bayesian_retriever.read_json", side_effect=AssertionError("Retrieve đọc JSON")),
              patch.object(MarketRegimeDetector, "load", side_effect=AssertionError("Nạp model trong query"))):
            point.verify_source(shared)
            result = point.retrieve(shared)
            point.verify_source({**shared, **{f"prior_{key}": value for key, value in result.items()}})
        json.dumps(shared, allow_nan=False, ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
