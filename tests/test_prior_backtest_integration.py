"""Walk-forward/schema/kinh tế trên pipeline thật với file và LLM fixture."""

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from core.backtest_engine import BacktestEngine, PRIOR_BRANCH_MODES, compute_round_trip_net_return
from core.prior_backtest import ResearchSchema, canonical_hash, evaluate_point, summarize_points
from prior_context_test_support import model_file
import test_prior_paired_protocol as paired_support
from test_backtest_token_budget import _StructuredCountingLlm
from utils.graph_setup import SetGraph


class PriorBacktestIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        paired_support.PriorPairedProtocolTests.setUp(self)
        self.engine.config.update(self.fx.config["models"], language=self.fx.config["language"],
                                  alpha_norm_method=self.fx.config["norm_method"], alpha_weights=None)
        self.engine.DELAY_BETWEEN_TESTS = 0.
        self.output = self.fx.root / "results"
        self.cutoffs = (self.fx.day(644), self.fx.day(647))
        model_file(self.fx.root / f"run/regimes/VNINDEX-{self.fx.day(647)}.json", self.fx.vnindex.iloc[:648])

    def run_fixture(self, **kwargs):
        """Đường public chỉ được khai offline_fixture khi dùng LLM giả."""
        options = dict(adapter=self.adapter, graph_builder=self.builder, output_dir=self.output,
                       cutoffs=self.cutoffs, execution_mode="offline_fixture")
        options.update(kwargs)
        return self.engine.run_prior_backtest("FPT", **options)

    def read_payload(self, path: Path, definition: str):
        """Kiểm envelope/hash/schema trên byte thực đã được runner ghi."""
        envelope = json.loads(path.read_text("utf-8"))
        self.assertEqual(set(envelope), {"payload", "sha256"})
        self.assertEqual(canonical_hash(envelope["payload"]), envelope["sha256"])
        ResearchSchema().validate(envelope["payload"], definition)
        return envelope["payload"]

    def test_two_cutoffs_schema_metadata_shared_hash_and_load_once(self) -> None:
        with (patch("core.bayesian_memory.HistoricalMemory.__init__", side_effect=AssertionError("Cấm nạp lại kho")),
              patch("core.prior_context.load_verified_execution_data", side_effect=AssertionError("Cấm nạp lại giá")),
              patch("core.bayesian_memory.compute_round_trip_net_return", side_effect=AssertionError("Cấm chấm lại nhãn kho")),
              patch.object(self.adapter._retriever, "retrieve", wraps=self.adapter._retriever.retrieve) as retrieve):
            result = self.run_fixture()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(len(result["completed_point_ids"]), 2)
        self.assertEqual(self.events, ["indicator", "pattern", "trend", "full"] * 2)
        self.assertEqual((self.llm.calls, retrieve.call_count, self.compute.call_count), (10, 10, 2))
        self.assertEqual(self.read_payload(self.output / "results.json", "result"), result)
        identity = self.read_payload(self.output / "identity.json", "identity")
        self.assertEqual(result["run_signature"], canonical_hash(identity))
        self.assertEqual(identity["run_config"]["execution_mode"], "offline_fixture")
        for file in result["point_files"]:
            path = self.output / file["path"]
            self.assertEqual(file["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
            point = self.read_payload(path, "point")
            self.assertEqual(point["shared"]["shared_sha256"], canonical_hash(point["shared"]["full_bundle"]))
            stats = []
            for name, branch in point["branches"].items():
                inputs = branch["input"]
                self.assertEqual(inputs["shared_sha256"], point["shared"]["shared_sha256"])
                self.assertEqual(branch["decision"]["decision_source"], "llm_json")
                self.assertTrue(branch["decision"]["raw_response"])
                self.assertLess(inputs["prompt"]["char_count"], 6500)
                self.assertLessEqual(len(inputs["bayesian_prior_context"]), 600)
                self.assertIn("statistics_version", inputs["prior_metadata"])
                self.assertEqual(inputs["prior_metadata"]["selected_ids"],
                                 [task["episode_id"] for task in inputs["prior_tasks"]])
                if name == "original":
                    self.assertEqual(inputs["prior_tasks"], [])
                    self.assertIsNone(inputs["prior_stats"])
                else:
                    stats.append(inputs["prior_stats"])
            self.assertTrue(all(stat == stats[0] for stat in stats))
            self.assertEqual(point["evaluation"]["entry_date"], self.fx.day(645 if file == result["point_files"][0] else 648))
        self.assertTrue(all(s["sample_count"] == 2 for s in result["summary"].values()))
        json.dumps(result, allow_nan=False)

    def test_default_schedule_uses_latest_valid_nonoverlapping_points(self) -> None:
        adapter = self.fx.adapter(provider_mode="fixed_train_oos", frozen_artifact_path="model/fixed.json",
                                  freeze_as_of_date=self.fx.day(620))
        result = self.run_fixture(adapter=adapter, cutoffs=None, n_tests=2)
        self.assertEqual(result["planned_point_ids"], [f"FPT-{self.fx.day(p)}" for p in (693, 696)])
        point = self.read_payload(self.output / result["point_files"][-1]["path"], "point")
        self.assertEqual(point["evaluation"]["exit_date"], self.fx.day(699))

    def test_llm_failure_preserves_previous_complete_point_without_failed_cash(self) -> None:
        invoke = self.llm.invoke
        def fail(messages):
            if self.llm.calls == 6:
                raise RuntimeError("Quota fixture")
            return invoke(messages)
        with (patch.object(self.llm, "invoke", side_effect=fail),
              patch("agents.decision_agent._invoke_with_retry", side_effect=lambda fn, *args: fn(*args)),
              self.assertRaisesRegex(RuntimeError, "Quota fixture")):
            self.run_fixture()
        result = self.read_payload(self.output / "results.json", "result")
        self.assertEqual((result["status"], len(result["completed_point_ids"])), ("partial", 1))
        self.assertEqual(len(list((self.output / "points").glob("*.json"))), 1)
        self.assertTrue(all(s["sample_count"] == 1 for s in result["summary"].values()))
        self.assertTrue(self.engine._prior_run_lock.acquire(False))
        self.engine._prior_run_lock.release()

    def test_invalid_plan_daily_horizon_and_config_rejected_before_api(self) -> None:
        cases = [dict(time_frame="1h"), dict(step=2), dict(n_tests=True), dict(cutoffs=()),
                 dict(cutoffs=(self.fx.day(647), self.fx.day(644))),
                 dict(cutoffs=(self.fx.day(644), self.fx.day(645))),
                 dict(cutoffs=(self.fx.day(598),)), dict(cutoffs=(self.fx.day(697),))]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.run_fixture(**case)
        for key, value in (("tx_cost", 0), ("allow_shorting", True), ("language", "en"), ("agent_llm_model", "wrong")):
            before = deepcopy(self.engine.config)
            self.engine.config[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.run_fixture()
            self.engine.config = before
        self.assertEqual(self.llm.calls, 0)
        self.assertFalse(self.output.exists())

    def test_research_does_not_accept_fixture_client_or_nonempty_output(self) -> None:
        with self.assertRaises(ValueError):
            self.run_fixture(execution_mode="research")
        self.output.mkdir()
        marker = self.output / "keep.txt"
        marker.write_text("Giữ nguyên", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.run_fixture()
        self.assertEqual(marker.read_text("utf-8"), "Giữ nguyên")
        self.assertEqual(self.llm.calls, 0)

    def test_callback_copies_and_stop_exclude_incomplete_points(self) -> None:
        def callback(progress):
            self.assertEqual(progress["completed"], 1)
            progress["latest"]["branches"]["original"]["decision"]["action"] = "SHORT"
            progress["partial"]["summary"]["original"]["sample_count"] = 999
            self.engine.stop()
        result = self.run_fixture(callback=callback)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["summary"]["original"]["sample_count"], 1)
        self.assertEqual(result["summary"]["original"]["long_count"], 1)
        self.assertEqual(self.llm.calls, 5)

    def test_zero_complete_support_stays_null_and_zero(self) -> None:
        self.engine.stop()
        result = self.run_fixture()
        self.assertEqual(result["completed_point_ids"], [])
        for s in result["summary"].values():
            self.assertEqual(s["sample_count"], 0)
            self.assertIsNone(s["accuracy"])
            self.assertIsNone(s["account_metrics"])
        self.assertEqual(self.llm.calls, 0)

    def test_structured_tool_calls_preserve_raw_and_normalized_separately(self) -> None:
        llm = _StructuredCountingLlm()
        invoke = llm._invoke_structured
        def structured(prompt):
            result = invoke(prompt)
            result["raw"] = SimpleNamespace(content="", tool_calls=[{
                "name": "TradeDecisionOutput", "args": result["parsed"].model_dump(), "id": "fixture-id"}])
            return result
        with patch.object(llm, "_invoke_structured", side_effect=structured):
            result = self.run_fixture(cutoffs=(self.fx.cutoff,), graph_builder=SetGraph(llm, object(), object()))
        point = self.read_payload(self.output / result["point_files"][0]["path"], "point")
        for branch in point["branches"].values():
            decision = branch["decision"]
            self.assertEqual(decision["decision_source"], "llm_structured")
            self.assertEqual(json.loads(decision["raw_response"])["tool_calls"][0]["id"], "fixture-id")
            self.assertNotEqual(decision["raw_response"], decision["normalized_response"])

    def test_missing_raw_or_invalid_decision_cannot_be_sealed_as_success(self) -> None:
        for index, invalid in enumerate(("raw", "decision", "config")):
            self.engine = BacktestEngine(deepcopy(self.engine.config))
            self.engine.DELAY_BETWEEN_VARIANTS = 0.
            self.output = self.fx.root / f"invalid-{index}"
            original = self.engine.run_prior_point
            def bad(point, **kwargs):
                result = original(point, **kwargs)
                branch = result["branches"]["original"]
                if invalid == "raw":
                    branch["raw_response"] = None
                elif invalid == "decision":
                    branch["state"]["final_trade_decision"] = "Không có quyết định hợp lệ"
                else:
                    branch["state"]["prior_config"]["seed"] = 7
                return result
            with self.subTest(invalid=invalid), patch.object(self.engine, "run_prior_point", side_effect=bad), self.assertRaises(ValueError):
                self.run_fixture()
            result = self.read_payload(self.output / "results.json", "result")
            self.assertEqual(result["completed_point_ids"], [])

    def test_legacy_run_signature_summary_and_callback_remain_usable_without_bank(self) -> None:
        # Bộ test legacy đã kiểm pipeline; ở đây kiểm chính API public sau bổ sung runner.
        import inspect
        self.assertEqual(list(inspect.signature(BacktestEngine.run).parameters),
                         ["self", "df", "symbol", "timeframe", "n_tests", "window_size", "step", "callback", "result_path"])
        engine = BacktestEngine({"use_historical_sentiment": False})
        engine._graph_upstream = object()
        engine._run_paired_point = Mock(return_value=(
            {"final_trade_decision": '{"decision":"LONG"}'}, 1.,
            {"final_trade_decision": '{"decision":"SHORT"}'}, .5))
        engine._save, engine._draw_backtest_result = Mock(), Mock()
        progress = []
        with patch("core.prior_backtest.PriorBacktestRunner", side_effect=AssertionError("Flag off không I/O kho")):
            result = engine.run(self.fx.frame["FPT"], "FPT", timeframe="1 ngày", n_tests=1,
                                callback=progress.append, result_path="unused.json")
        self.assertEqual(result.test_points[0]["pred_full"], "LONG")
        self.assertEqual(result.test_points[0]["pred_no_alpha"], "SHORT")
        self.assertTrue(progress)
        self.assertNotIn("run_signature", progress[0])
        config = self.adapter.signal_config
        config["models"]["agent_llm_model"] = "Đột biến"
        frame, events = self.adapter.execution_data("FPT")
        frame.loc[0, "Open"] = 0
        events.append({"exrightDate": self.fx.cutoff})
        unchanged, original_events = self.adapter.execution_data("FPT")
        self.assertGreater(unchanged.Open.iloc[0], 0)
        self.assertEqual(original_events, [])
        self.assertEqual(self.adapter.signal_config["models"]["agent_llm_model"], "mock/decision")


class PriorEconomicTests(unittest.TestCase):
    def setUp(self) -> None:
        from prior_context_test_support import ContextFixture
        self.fx = ContextFixture()
        self.addCleanup(self.fx.close)
        self.branches = {name: {"status": "complete", "decision": {"action": "LONG"}}
                         for name in PRIOR_BRANCH_MODES}

    def test_long_profit_loss_zero_and_short_cash_use_round_trip_engine(self) -> None:
        frame = self.fx.frame["FPT"].copy()
        entry = float(frame.Open.iloc[645])
        # Công thức đảo giá break-even; không thay hàm nhãn trong engine.
        break_even = entry * (1.001 * 1.0025) / (.999 * .9975)
        # Chọn float lân cận có return đúng 0, tránh dùng tolerance đổi nhãn.
        candidates = (break_even, math.nextafter(break_even, math.inf), math.nextafter(break_even, -math.inf))
        break_even = next(price for price in candidates if compute_round_trip_net_return(entry, price) == 0.)
        for exit_price in (entry * 1.1, entry * .9, break_even):
            frame.loc[647, "Close"] = exit_price
            frame.loc[647, "High"] = max(exit_price, float(frame.Open.iloc[647])) + 1
            frame.loc[647, "Low"] = min(exit_price, float(frame.Open.iloc[647])) - 1
            result = evaluate_point(frame, [], self.fx.cutoff, self.branches)
            net = compute_round_trip_net_return(entry, exit_price)
            self.assertEqual(result["net_return_long"], net)
            self.assertEqual(result["actual_direction"], "UP" if net > 0 else "DOWN")
            self.assertEqual((result["entry_date"], result["exit_date"]), (self.fx.day(645), self.fx.day(647)))
            self.assertEqual(result["branches"]["original"]["cycle_net_return"], net)
        self.assertEqual(result["net_return_long"], 0.)
        self.assertEqual(result["actual_direction"], "DOWN")
        for branch in self.branches.values():
            branch["decision"]["action"] = "SHORT"
        result = evaluate_point(frame, [], self.fx.cutoff, self.branches)
        self.assertTrue(all(b["executed_action"] == "CASH" and b["cycle_net_return"] == 0.
                            for b in result["branches"].values()))

    def test_missing_exit_zero_volume_corporate_action_and_failed_branch_rejected(self) -> None:
        frame = self.fx.frame["FPT"].copy()
        with self.assertRaises(ValueError):
            evaluate_point(frame.iloc[:647], [], self.fx.cutoff, self.branches)
        with self.assertRaises(ValueError):
            evaluate_point(frame, [{"exrightDate": self.fx.day(646)}], self.fx.cutoff, self.branches)
        frame.loc[645, "Volume"] = 0
        with self.assertRaises(ValueError):
            evaluate_point(frame, [], self.fx.cutoff, self.branches)
        frame.loc[645, "Volume"] = 1000
        self.branches["random"]["status"] = "failed"
        with self.assertRaises(ValueError):
            evaluate_point(frame, [], self.fx.cutoff, self.branches)
        self.assertTrue(all(s["sample_count"] == 0 for s in summarize_points([]).values()))

    def test_five_account_summaries_compound_long_and_keep_cash_short(self) -> None:
        frame, points = self.fx.frame["FPT"].copy(), []
        for index, position in enumerate((644, 647)):
            entry = float(frame.Open.iloc[position + 1])
            exit_price = entry * (1.1 if index == 0 else .9)
            frame.loc[position + 3, ["Close", "High", "Low"]] = [exit_price, max(exit_price, entry) + 2, min(exit_price, entry) - 2]
            branches = deepcopy(self.branches)
            for name, branch in branches.items():
                branch["decision"].update(confidence="Cao", risk_reward_ratio="1.5", latency_seconds=0.)
                if name == "original" and index == 1:
                    branch["decision"]["action"] = "SHORT"
            evaluation = evaluate_point(frame, [], self.fx.day(position), branches)
            points.append({"status": "complete", "source_proof": {"prices": {"snapshot_start_date": self.fx.day(0)}},
                "context": {"as_of_date": self.fx.day(position)}, "branches": branches, "evaluation": evaluation})
        summaries = summarize_points(points)
        win, loss = [point["evaluation"]["net_return_long"] for point in points]
        for name, s in summaries.items():
            self.assertEqual(s["sample_count"], 2)
            expected = 50_000_000. * (1 + win) * (1 if name == "original" else 1 + loss)
            self.assertAlmostEqual(s["account_metrics"]["final_equity_vnd"], expected, places=4)
            self.assertEqual(s["account_metrics"]["final_shares"], 0.)
        self.assertEqual((summaries["original"]["long_count"], summaries["original"]["short_count"]), (1, 1))
        self.assertEqual(summaries["original"]["accuracy"], 1.)


if __name__ == "__main__":
    unittest.main()
