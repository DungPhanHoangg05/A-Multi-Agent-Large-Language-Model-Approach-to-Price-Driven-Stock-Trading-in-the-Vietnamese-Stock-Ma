import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from core.backtest_engine import BacktestEngine
from scripts.run_ablation_matrix import (
    DEFAULT_N_TESTS,
    VARIANTS,
    load_checkpoint,
    run_symbol,
    summarize_symbol,
)


class _FakeGraph:
    def __init__(self, invoke_fn):
        self._invoke_fn = invoke_fn

    def invoke(self, state):
        return self._invoke_fn(state)


def _market_frame(rows: int = 660) -> pd.DataFrame:
    dates = pd.date_range("2023-01-02", periods=rows, freq="B")
    close = [100.0 + index * 0.1 for index in range(rows)]
    return pd.DataFrame(
        {
            "Datetime": dates,
            "Open": close,
            "High": [value + 1.0 for value in close],
            "Low": [value - 1.0 for value in close],
            "Close": [value + 0.5 for value in close],
            "Volume": [1_000_000.0] * rows,
        }
    )


def _completed_points() -> list[dict]:
    points = []
    for test_id in range(1, DEFAULT_N_TESTS + 1):
        actual = "UP" if test_id <= 12 else "DOWN"
        variants = {}
        predictions = {
            "full": "LONG" if test_id <= 15 else "SHORT",
            "alpha_only": "LONG" if test_id <= 14 else "SHORT",
            "sentiment_only": "LONG" if test_id <= 11 else "SHORT",
            "baseline": "LONG" if test_id <= 8 else "SHORT",
        }
        for variant in VARIANTS:
            prediction = predictions[variant]
            variants[variant] = {
                "prediction": prediction,
                "correct": (prediction == "LONG" and actual == "UP")
                or (prediction == "SHORT" and actual == "DOWN"),
                "confidence": "Cao",
                "risk_reward_ratio": "1.5",
                "time_sec": 1.0,
                "decision_source": "structured_output",
                "fallback_reason": "",
                "error": "",
            }
        entry_date = pd.Timestamp("2025-01-01") + pd.Timedelta(days=test_id * 3)
        points.append(
            {
                "test_id": test_id,
                "window_start": "2024-01-01",
                "window_end": "2024-03-01",
                "actual_prev_close": 100.0,
                "actual_next_close": 102.0,
                "actual_direction": actual,
                "actual_pct_change": 1.0,
                "entry_open": 100.0,
                "exit_close": 102.0,
                "entry_time": entry_date.isoformat(),
                "exit_time": (entry_date + pd.Timedelta(days=2)).isoformat(),
                "variants": variants,
            }
        )
    return points


class AblationMatrixTests(unittest.TestCase):
    def test_summary_reports_all_four_variants_and_marginal_contributions(self):
        summary = summarize_symbol(
            "FPT",
            _completed_points(),
            config={"tx_cost": 0.0025, "slippage": 0.001},
            data_start="2023-01-01",
            data_end="2025-12-31",
        )

        self.assertEqual([row["variant"] for row in summary["rows"]], list(VARIANTS))
        self.assertEqual(summary["n_tests"], 20)
        self.assertGreater(summary["contributions"]["alpha_contribution_pp"], 0.0)
        self.assertIn("sentiment_contribution_pp", summary["contributions"])
        self.assertIn("synergy_pp", summary["contributions"])

    def test_one_upstream_drives_four_variants_and_checkpoint_resumes(self):
        calls = {"upstream": 0, **{variant: 0 for variant in VARIANTS}}

        def fake_init_graphs(engine):
            def upstream(state):
                calls["upstream"] += 1
                return {**state, "shared_marker": "same-snapshot"}

            def variant_graph(name):
                def invoke(state):
                    calls[name] += 1
                    self.assertEqual(state["shared_marker"], "same-snapshot")
                    return {
                        **state,
                        "final_trade_decision": json.dumps({"decision": "LONG"}),
                    }

                return _FakeGraph(invoke)

            engine._graph_upstream = _FakeGraph(upstream)
            engine._graph_decision_variants = {
                variant: variant_graph(variant) for variant in VARIANTS
            }

        config = {
            "use_historical_sentiment": False,
            "tx_cost": 0.0025,
            "slippage": 0.001,
            "alpha_norm_method": "zscore_tanh",
            "alpha_weights": {"ic": 0.4, "acc": 0.35, "sharpe": 0.25},
        }
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(BacktestEngine, "_init_graphs", fake_init_graphs),
                patch.object(BacktestEngine, "DELAY_BETWEEN_VARIANTS", 0.0),
                patch.object(BacktestEngine, "DELAY_BETWEEN_TESTS", 0.0),
                patch("utils.static_util.generate_kline_image", return_value={}),
                patch("utils.static_util.generate_trend_image", return_value={}),
                patch("scripts.run_ablation_matrix.DEFAULT_N_TESTS", 2),
            ):
                first = run_symbol(
                    "FPT",
                    df=_market_frame(606),
                    output_dir=Path(directory),
                    n_tests=2,
                    config=config,
                )
                first_calls = dict(calls)
                for key in calls:
                    calls[key] = 0
                resumed = run_symbol(
                    "FPT",
                    df=_market_frame(606),
                    output_dir=Path(directory),
                    n_tests=2,
                    config=config,
                )

        self.assertEqual(first_calls["upstream"], 2)
        self.assertTrue(all(first_calls[variant] == 2 for variant in VARIANTS))
        self.assertTrue(all(value == 0 for value in calls.values()))
        self.assertEqual(first["rows"], resumed["rows"])

    def test_checkpoint_rejects_different_data_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint_ablation_FPT.json"
            path.write_text(
                json.dumps(
                    {
                        "symbol": "FPT",
                        "n_tests": 20,
                        "window_size": 45,
                        "step": 3,
                        "data_start": "2023-01-01",
                        "data_end": "2026-09-18",
                        "test_points": [],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "không khớp"):
                load_checkpoint(
                    path,
                    symbol="FPT",
                    n_tests=20,
                    window_size=45,
                    step=3,
                    data_start="2023-01-01",
                    data_end="2026-09-19",
                )


if __name__ == "__main__":
    unittest.main()
