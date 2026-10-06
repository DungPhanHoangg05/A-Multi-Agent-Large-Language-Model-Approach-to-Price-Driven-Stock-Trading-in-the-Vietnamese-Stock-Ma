"""Ranh giới outcome/query và thay đổi nguồn trong vòng walk-forward mới."""

import json
from unittest.mock import patch
import unittest

from core import prior_backtest
import test_prior_backtest_integration as integration


class PriorBacktestLeakageTests(unittest.TestCase):
    setUp = integration.PriorBacktestIntegrationTests.setUp
    run_fixture = integration.PriorBacktestIntegrationTests.run_fixture
    read_payload = integration.PriorBacktestIntegrationTests.read_payload

    def test_future_execution_prices_only_enter_evaluation_after_five_decisions(self) -> None:
        seen = []
        compile_upstream = self.builder.compile_upstream
        def compile():
            graph = compile_upstream()
            invoke = graph.invoke
            def checked(state):
                cutoff = state["as_of_date"]
                self.assertLessEqual(state["point_in_time_df"].Datetime.max().strftime("%Y-%m-%d"), cutoff)
                self.assertEqual(state["kline_data"]["Datetime"][-1][:10], cutoff)
                self.assertTrue(set(state).isdisjoint({"evaluation", "outcome", "actual_direction", "entry_open", "exit_close"}))
                seen.append(cutoff)
                return invoke(state)
            from unittest.mock import Mock
            return Mock(invoke=checked)
        evaluate = prior_backtest.evaluate_point
        def checked_evaluate(frame, events, cutoff, branches):
            self.assertEqual(self.llm.calls, 5 * (self.cutoffs.index(cutoff) + 1))
            self.assertGreater(frame.Datetime.max().strftime("%Y-%m-%d"), cutoff)
            return evaluate(frame, events, cutoff, branches)
        with (patch.object(self.builder, "compile_upstream", side_effect=compile),
              patch("core.prior_backtest.evaluate_point", side_effect=checked_evaluate),
              patch.object(self.adapter._retriever, "retrieve", wraps=self.adapter._retriever.retrieve) as retrieve):
            result = self.run_fixture()
        self.assertEqual(seen, list(self.cutoffs))
        for call in retrieve.call_args_list:
            self.assertEqual(set(call.kwargs), {"symbol", "as_of_date", "current_regime", "current_signals", "mode", "k", "seed", "scope"})
        self.assertEqual(result["status"], "complete")

    def test_invalid_later_prefix_stops_entire_plan_before_first_upstream(self) -> None:
        path = self.fx.root / f"run/regimes/VNINDEX-{self.fx.day(647)}.json"
        path.write_text('{"payload":{},"sha256":"bad"}', encoding="utf-8")
        with self.assertRaises(ValueError):
            self.run_fixture()
        self.assertEqual(self.events, [])
        self.assertEqual(self.llm.calls, 0)
        self.assertFalse(self.output.exists())

    def test_changed_bank_after_first_cutoff_stops_before_second_upstream(self) -> None:
        def callback(progress):
            path = self.fx.root / "bank/bank.json"
            path.write_text(json.dumps([]), encoding="utf-8")
        with self.assertRaises(ValueError):
            self.run_fixture(callback=callback)
        self.assertEqual(self.events, ["indicator", "pattern", "trend", "full"])
        self.assertEqual(self.llm.calls, 5)
        result = self.read_payload(self.output / "results.json", "result")
        self.assertEqual(len(result["completed_point_ids"]), 1)
        self.assertTrue(all(s["sample_count"] == 1 for s in result["summary"].values()))


if __name__ == "__main__":
    unittest.main()
