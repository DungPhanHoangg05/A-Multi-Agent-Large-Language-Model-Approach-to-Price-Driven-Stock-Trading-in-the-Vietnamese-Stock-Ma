import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from core.run_robustness import (
    load_market_data,
    run_shared_alpha_sweep,
    run_sweep,
    save_results,
    validate_sweep_results,
)
from core.backtest_engine import BacktestEngine


class _FakeGraph:
    def __init__(self, invoke_fn):
        self._invoke_fn = invoke_fn

    def invoke(self, state):
        return self._invoke_fn(state)


def _market_frame(rows: int = 720) -> pd.DataFrame:
    dates = pd.date_range("2023-01-02", periods=rows, freq="B")
    return pd.DataFrame(
        {
            "Datetime": dates,
            "Open": [100.0] * rows,
            "High": [101.0] * rows,
            "Low": [99.0] * rows,
            "Close": [100.5] * rows,
            "Volume": [1_000_000.0] * rows,
        }
    )


def _fake_result() -> dict:
    predictions = ["LONG", "SHORT"] * 10
    actuals = ["UP", "DOWN"] * 10
    return {
        "n_tests": 20,
        "acc_no_alpha": 100.0,
        "_baseline_predictions": predictions,
        "_actual_directions": actuals,
    }


class RobustnessSweepTests(unittest.TestCase):
    def test_window_panel_uses_twenty_points_for_every_window(self):
        calls = []

        def fake_run(*args, **kwargs):
            calls.append(kwargs)
            return [_fake_result()]

        with (
            patch("core.run_robustness.load_market_data", return_value=_market_frame()),
            patch(
                "core.run_robustness.run_shared_alpha_sweep",
                side_effect=fake_run,
            ),
            patch(
                "core.run_robustness.save_results",
                return_value=Path("sweep_hyperparams_FPT.csv"),
            ),
        ):
            run_sweep("hyperparams", "FPT", n_tests=20)

        self.assertEqual([call["window_size"] for call in calls], [30, 45, 60])
        self.assertEqual([call["n_tests"] for call in calls], [20, 20, 20])
        self.assertTrue(
            all(call["protocol"] == "paired_shared_reports" for call in calls)
        )
        self.assertTrue(
            all(not call["shared_across_alpha_configs"] for call in calls)
        )

    def test_norm_panel_passes_three_methods_and_requires_invariant_control(self):
        received_scenarios = []

        def fake_shared(_symbol, _timeframe, _config, scenarios, **_kwargs):
            received_scenarios.extend(scenarios)
            return [_fake_result() for _ in scenarios]

        with (
            patch("core.run_robustness.load_market_data", return_value=_market_frame()),
            patch(
                "core.run_robustness.run_shared_alpha_sweep",
                side_effect=fake_shared,
            ),
            patch(
                "core.run_robustness.save_results",
                return_value=Path("sweep_norm_FPT.csv"),
            ),
        ):
            run_sweep("norm", "FPT", n_tests=20)

        self.assertEqual(
            [overrides["alpha_norm_method"] for _, overrides in received_scenarios],
            ["zscore_tanh", "minmax", "rank"],
        )

    def test_alpha_panels_share_one_upstream_and_one_baseline_per_point(self):
        calls = {"upstream": 0, "baseline": 0, "full": 0}

        def fake_init_graphs(engine):
            def upstream(state):
                calls["upstream"] += 1
                return {
                    **state,
                    "indicator_report": "indicator",
                    "pattern_report": "pattern",
                    "trend_report": "trend",
                }

            def baseline(state):
                calls["baseline"] += 1
                return {
                    **state,
                    "final_trade_decision": json.dumps({"decision": "LONG"}),
                }

            def full(state):
                calls["full"] += 1
                decision = (
                    "SHORT" if state["alpha_norm_method"] == "rank" else "LONG"
                )
                return {
                    **state,
                    "final_trade_decision": json.dumps({"decision": decision}),
                }

            engine._graph_upstream = _FakeGraph(upstream)
            engine._graph_decision_variants = {
                "baseline": _FakeGraph(baseline),
                "full": _FakeGraph(full),
            }

        scenarios = [
            ("zscore_tanh", {"alpha_norm_method": "zscore_tanh"}),
            ("minmax", {"alpha_norm_method": "minmax"}),
            ("rank", {"alpha_norm_method": "rank"}),
        ]
        config = {
            "use_historical_sentiment": False,
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
            ):
                rows = run_shared_alpha_sweep(
                    "FPT",
                    "1d",
                    config,
                    scenarios,
                    df=_market_frame(610),
                    n_tests=2,
                    window_size=45,
                    step=3,
                    output_dir=Path(directory),
                    mode="norm",
                )
                first_calls = dict(calls)
                calls.update({"upstream": 0, "baseline": 0, "full": 0})
                resumed_rows = run_shared_alpha_sweep(
                    "FPT",
                    "1d",
                    config,
                    scenarios,
                    df=_market_frame(610),
                    n_tests=2,
                    window_size=45,
                    step=3,
                    output_dir=Path(directory),
                    mode="norm",
                )

        self.assertEqual(
            first_calls, {"upstream": 2, "baseline": 2, "full": 6}
        )
        self.assertEqual(calls, {"upstream": 0, "baseline": 0, "full": 0})
        self.assertEqual(len({row["baseline_signature"] for row in rows}), 1)
        self.assertTrue(all(row["shared_across_alpha_configs"] for row in rows))
        self.assertEqual(
            [row["baseline_signature"] for row in resumed_rows],
            [row["baseline_signature"] for row in rows],
        )

    def test_control_drift_stops_sweep(self):
        rows = [_fake_result() for _ in range(3)]
        for index, row in enumerate(rows):
            row["scenario"] = f"scenario-{index}"
        rows[2]["_baseline_predictions"] = ["SHORT"] * 20

        with self.assertRaisesRegex(RuntimeError, "No-Alpha không bất biến"):
            validate_sweep_results(
                rows,
                n_tests=20,
                require_invariant_control=True,
            )

    def test_loader_rejects_insufficient_real_history(self):
        with patch(
            "core.run_robustness.fetch_realtime_ohlcv",
            return_value=(_market_frame(659), ""),
        ):
            with self.assertRaisesRegex(ValueError, "A20 cần ít nhất 660 nến"):
                load_market_data(
                    "FPT",
                    n_tests=20,
                    max_window_size=60,
                )

    def test_csv_does_not_expose_internal_prediction_arrays(self):
        row = _fake_result()
        row.update({"scenario": "rank", "symbol": "FPT"})
        with tempfile.TemporaryDirectory() as directory:
            output = save_results([row], Path(directory), "sweep_norm", "FPT")
            saved = pd.read_csv(output)

        self.assertIn("scenario", saved.columns)
        self.assertNotIn("_baseline_predictions", saved.columns)
        self.assertNotIn("_actual_directions", saved.columns)


if __name__ == "__main__":
    unittest.main()
