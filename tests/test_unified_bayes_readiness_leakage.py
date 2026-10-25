"""Planning không nhận nhãn OOS, không điền dữ liệu thiếu hoặc cho fixture đổi thành release."""

from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from core.historical_signals import digest
from core.unified_bayes_readiness import account_delta, planning_policy, publish, repeat_design, simulate_noise, training_panels
from test_unified_bayes_readiness import ReadinessFixture, planning_inputs
from unified_validation_test_support import ValidationFixture


class PlanningLeakageTests(unittest.TestCase):
    """Checksum mới không hợp thức hóa target ngoài train hoặc calibration sai."""

    def test_2023_2024_2025_targets_rejected_even_when_memory_is_resealed(self) -> None:
        for year in (2023, 2024, 2025):
            with self.subTest(year=year):
                memory, pooling = planning_inputs()
                row = pooling["points"][0]
                row.update(episode_id=f"FPT:{year}-01-04", as_of_date=f"{year}-01-04", exit_date=f"{year}-01-07", fold_id=f"train_{year}")
                memory["records"][0].update({k: row[k] for k in ("episode_id", "as_of_date", "exit_date")})
                pooling["memory_sha256"] = digest(memory)
                with self.assertRaises(ValueError):
                    training_panels(pooling, memory)

    def test_cycle_crossing_train_year_boundary_is_not_calibration(self) -> None:
        memory, pooling = planning_inputs()
        pooling["points"][0]["exit_date"] = "2022-01-04"
        memory["records"][0]["exit_date"] = "2022-01-04"
        pooling["memory_sha256"] = digest(memory)
        with self.assertRaises(ValueError):
            training_panels(pooling, memory)

    def test_changed_label_missing_id_and_duplicate_cannot_enter_panel(self) -> None:
        for kind in ("label", "missing", "duplicate"):
            with self.subTest(kind=kind):
                memory, pooling = planning_inputs()
                if kind == "label":
                    pooling["points"][0]["net_long_return"] += .01
                elif kind == "missing":
                    pooling["points"].pop()
                else:
                    pooling["points"].append(deepcopy(pooling["points"][0]))
                with self.assertRaises(ValueError):
                    training_panels(pooling, memory)

    def test_missing_symbol_nonfinite_and_invalid_action_masks_are_not_zero_filled(self) -> None:
        panel = np.full((16, 4), .01)
        mask = np.ones((12, 4), dtype=bool)
        for kind in ("missing_symbol", "nonfinite", "odd_draws", "probability"):
            with self.subTest(kind=kind):
                values, active = panel.copy(), mask.copy()
                draws, rate = 100, .25
                if kind == "missing_symbol": active[:, 0] = False
                if kind == "nonfinite": values[0, 0] = np.nan
                if kind == "odd_draws": draws = 99
                if kind == "probability": rate = 2.
                with self.assertRaises(ValueError):
                    simulate_noise(values, active, block=4, disagreement=rate, draws=draws, seed=1)
        with self.assertRaises(ValueError):
            account_delta(np.full((1, 12, 4), .1), np.ones((1, 12, 4)), np.ones((1, 12, 4)), mask)

    def test_policy_cannot_be_tuned_by_resealing_fixture(self) -> None:
        changed = planning_policy()
        changed["disagreement_rates"] = [.001]
        with patch("core.unified_bayes_readiness.read_json", return_value=changed), self.assertRaises(ValueError):
            planning_policy()

    def test_repeat_sample_cannot_be_replaced_by_different_points(self) -> None:
        from core.unified_bayes_source import repeat_sample
        requests = {f"{s}-2023-01-0{j}": {"u_evidence": {"posterior": {"gate": {"ready": False}},
                    "selection": {"gate": {"ready": False}}}, "upstream": {}, "packets": {}}
                    for s in ("FPT", "MWG", "VCB", "VNM") for j in range(1, 5)}
        sample = repeat_sample(requests)
        sample[0] = "FPT-2023-01-04"
        with self.assertRaises(ValueError):
            repeat_design({"requests": requests, "repeat_sample": sample, "schedule": []})


class ReadinessReleaseLeakageTests(ValidationFixture, unittest.TestCase):
    """Capability nguồn thật vẫn bắt buộc, kể cả report fixture bị đổi nhãn."""

    def test_fixture_relabel_cannot_publish_execution_readiness(self) -> None:
        expected = {"split": "development_2023_exploratory", "execution_readiness": {}, "plan_sha256": digest(self.plan)}
        with self.assertRaises(ValueError):
            publish(self.fx.root / "release", expected, self.cohort, self.plan, self.fx.llm, prepare=True)
        self.assertFalse((self.fx.root / "release").exists())
        self.assertEqual(self.fx.calls, [])
        self.assertEqual(self.fx.evaluations, [])


class ReadinessGuardLeakageTests(ReadinessFixture, unittest.TestCase):
    """Mọi guard vẫn có hiệu lực trong MDE, không chỉ ở cold load ban đầu."""

    def test_source_changed_during_mde_is_rejected_before_readiness(self) -> None:
        from core.unified_bayes_readiness import mde_planning
        def changed(*args):
            result = mde_planning(*args)
            self.cohort.points["VNM-2023-01-06"].changed = True
            return result
        with patch("core.unified_bayes_readiness.mde_planning", side_effect=changed) as simulate:
            with self.assertRaisesRegex(ValueError, "Nguồn fixture"):
                self.assessment()
            simulate.assert_called_once()
        self.assertEqual(self.fx.calls, [])
        self.assertEqual(self.fx.evaluations, [])

    def test_pooling_bytes_changed_during_simulation_cannot_publish(self) -> None:
        from core.unified_bayes_readiness import mde_planning
        def changed(*args):
            result = mde_planning(*args)
            self.pool_path.write_bytes(self.pool_path.read_bytes() + b" ")
            return result
        with patch("core.unified_bayes_readiness.mde_planning", side_effect=changed) as simulate:
            with self.assertRaisesRegex(ValueError, "Nguồn MDE đổi"):
                self.assessment()
            simulate.assert_called_once()
        self.assertEqual(self.fx.calls, [])

    def test_gate_log_tamper_blocks_before_mde_or_publication(self) -> None:
        (self.audit.parent / "unit.log").write_text("fixture changed", encoding="utf-8")
        with patch("core.unified_bayes_readiness.mde_planning") as simulate, self.assertRaises(ValueError):
            self.assessment()
        simulate.assert_not_called()
        self.assertEqual(self.fx.calls, [])


if __name__ == "__main__":
    unittest.main()
