"""Dò thay đổi nguồn/giá sau upstream trước khi Full dùng dữ liệu."""

import unittest
from unittest.mock import patch

import test_prior_paired_protocol as support


class PriorPairedProtocolLeakageTests(unittest.TestCase):
    setUp = support.PriorPairedProtocolTests.setUp

    def test_upstream_future_snapshot_stops_before_alpha_or_decision(self) -> None:
        def trend(state):
            return {"trend_report": "Hướng xu hướng: Tăng",
                    "point_in_time_df": self.fx.frame["FPT"].iloc[:646]}
        with patch("utils.graph_setup.create_trend_agent", return_value=trend), self.assertRaisesRegex(ValueError, "snapshot"):
            self.engine.run_prior_point(self.point, graph_builder=self.builder)
        self.alpha_factory.assert_not_called()
        self.compute.assert_not_called()
        self.assertEqual(self.llm.calls, 0)

    def test_upstream_future_kline_stops_before_alpha_or_decision(self) -> None:
        def trend(state):
            state["kline_data"]["Datetime"][-1] = self.fx.day(645)
            return {"trend_report": "Hướng xu hướng: Tăng", "kline_data": state["kline_data"]}
        with patch("utils.graph_setup.create_trend_agent", return_value=trend), self.assertRaisesRegex(ValueError, "kline_data"):
            self.engine.run_prior_point(self.point, graph_builder=self.builder)
        self.alpha_factory.assert_not_called()
        self.assertEqual(self.llm.calls, 0)

    def test_news_source_mutation_during_upstream_stops_before_full(self) -> None:
        path = self.fx.root / "run/inputs/news/FPT.json"
        def trend(state):
            path.write_text(path.read_text("utf-8") + "\n", encoding="utf-8")
            return {"trend_report": "Hướng xu hướng: Tăng"}
        with patch("utils.graph_setup.create_trend_agent", return_value=trend), self.assertRaisesRegex(ValueError, "Nguồn thay đổi"):
            self.engine.run_prior_point(self.point, graph_builder=self.builder)
        self.alpha_factory.assert_not_called()
        self.assertEqual(self.llm.calls, 0)


if __name__ == "__main__":
    unittest.main()
