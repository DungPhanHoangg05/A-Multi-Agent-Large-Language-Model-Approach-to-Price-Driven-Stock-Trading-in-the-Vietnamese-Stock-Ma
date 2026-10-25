"""Planning MDE từ train, oracle tài khoản và giải trình readiness/repeat trước action."""

from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from core.backtest_engine import TestPoint, compute_account_metrics, compute_round_trip_net_return
from core.historical_signals import digest
from core.research_cohort import save_envelope
from core.unified_bayes_readiness import (account_delta, coverage, mde_planning, planning_policy,
    build_assessment, read_assessment, repeat_design, simulate_noise, training_panels)
from core.unified_bayes_source import repeat_sample
from core.unified_bayes_validation import diagnostics, run_gates
from unified_context_test_support import dense_inputs, make_context
from unified_cohort_test_support import make_cohort
from unified_execution_test_support import ExecutionFixture


def planning_inputs() -> tuple[dict, dict]:
    """Nguồn train nhỏ tổng hợp với nhãn qua engine; không đọc artifact ignored thật."""
    records, points = [], []
    for year in (2021, 2022):
        for index in range(12):
            cutoff = date(year, 1, 4) + timedelta(days=4*index)
            for j, symbol in enumerate(("FPT", "MWG", "VCB", "VNM")):
                net = float(compute_round_trip_net_return(100., 101. + (index % 5-2)*2+j))
                row = {"episode_id": f"{symbol}:{cutoff}", "symbol": symbol, "as_of_date": str(cutoff),
                    "exit_date": str(cutoff+timedelta(days=3))}
                records.append({**row, "outcome": {"net_return_pct": net*100.}})
                points.append({**row, "fold_id": f"train_{year}", "net_long_return": net*100./100.})
    # Cụm thiếu ba mã phải bị khai báo loại, không được điền return 0.
    extra = deepcopy(records[-4])
    extra.update(episode_id="FPT:2022-03-01", as_of_date="2022-03-01", exit_date="2022-03-04")
    records.append(extra)
    points.append({k: extra[k] for k in ("episode_id", "symbol", "as_of_date", "exit_date")} |
                  {"fold_id": "train_2022", "net_long_return": extra["outcome"]["net_return_pct"]/100.})
    memory = {"protocol_sha256": "a"*64, "records": records}
    pooling = {"memory_sha256": digest(memory), "protocol_sha256": memory["protocol_sha256"],
        "points": points, "query_count": len(points),
        "folds": {f"train_{year}": {"query_ids": [r["episode_id"] for r in points if r["fold_id"] == f"train_{year}"]}
                  for year in (2021, 2022)}}
    return memory, pooling


class PlanningTests(unittest.TestCase):
    """Power giả định không trở thành tiêu chí chọn N hoặc kết quả LLM quan sát được."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.memory, cls.pooling = planning_inputs()
        cls.panels = training_panels(cls.pooling, cls.memory)

    def test_train_complete_clusters_and_fold_sensitivity_are_explicit(self) -> None:
        panel = self.panels["train_2021_2022"]
        self.assertEqual(len(panel["dates"]), 24)
        self.assertEqual(panel["source_rows"], 97)
        self.assertEqual(panel["excluded_incomplete_cluster_dates"], ["2022-03-01"])
        self.assertEqual(len(panel["included_episode_ids"]), 96)
        self.assertEqual(len(self.panels["train_2021"]["dates"]), 12)
        self.assertEqual(len(self.panels["train_2022"]["dates"]), 12)

    def test_account_compounding_matches_engine_not_cycle_sum(self) -> None:
        opens, closes = [100., 110., 90.], [120., 100., 105.]
        net = np.array([compute_round_trip_net_return(a, b) for a, b in zip(opens, closes)])
        values = np.broadcast_to(net[None, :, None], (1, 3, 4))
        original = np.zeros_like(values, dtype=bool)
        candidate = np.ones_like(values, dtype=bool)
        mask = np.ones((3, 4), dtype=bool)
        points = [TestPoint(test_id=j+1, window_start="2020-01-01", window_end=f"2021-01-{4+4*j:02d}",
            actual_prev_close=0., actual_next_close=closes[j], actual_direction="UP", actual_pct_change=float(net[j]*100),
            pred_full="LONG", pred_no_alpha="SHORT", entry_open=opens[j], exit_close=closes[j],
            correct_full=True, confidence_full="Cao", rr_full=1.5, correct_no_alpha=False,
            confidence_no_alpha="Cao", rr_no_alpha=1.5, time_full_sec=0., time_no_alpha_sec=0.,
            entry_time=f"2021-01-{5+4*j:02d}", exit_time=f"2021-01-{7+4*j:02d}") for j in range(3)]
        expected = compute_account_metrics(points)["full"].total_return_pct
        self.assertAlmostEqual(float(account_delta(values, original, candidate, mask)[0]), expected, places=8)
        self.assertNotAlmostEqual(expected, float(net.sum()*100), places=4)
        self.assertEqual(float(account_delta(values, original, original, mask)[0]), 0.)

    def test_rng_reproducible_antithetic_and_no_global_state_mutation(self) -> None:
        values = np.asarray(self.panels["train_2021_2022"]["net_returns"])
        mask = np.ones((16, 4), dtype=bool)
        before = deepcopy(np.random.get_state())
        a = simulate_noise(values, mask, block=4, disagreement=.25, draws=200, seed=20261024)
        b = simulate_noise(values, mask, block=4, disagreement=.25, draws=200, seed=20261024)
        np.testing.assert_array_equal(a, b)
        np.testing.assert_array_equal(a[:100], -a[100:])
        after = np.random.get_state()
        self.assertEqual(before[0], after[0])
        np.testing.assert_array_equal(before[1], after[1])
        self.assertEqual(before[2:], after[2:])

    def test_no_disagreement_has_exact_zero_account_delta(self) -> None:
        noise = simulate_noise(np.asarray(self.panels["train_2021"]["net_returns"]), np.ones((12, 4), dtype=bool),
                               block=4, disagreement=0., draws=100, seed=3)
        np.testing.assert_array_equal(noise, np.zeros(100))

    def test_mask_preserves_four_separate_unequal_accounts(self) -> None:
        values = np.full((1, 3, 4), .1)
        a, b = np.zeros_like(values, dtype=bool), np.ones_like(values, dtype=bool)
        mask = np.array([[True]*4, [False, True, True, True], [False, False, True, True]])
        actual = account_delta(values, a, b, mask)[0]
        expected = float(np.mean([1.1-1, 1.1**2-1, 1.1**3-1, 1.1**3-1])*100)
        self.assertAlmostEqual(actual, expected, places=10)

    def test_mde_grid_is_planning_only_and_never_selects_a_sample(self) -> None:
        plan = {"requests": {f"{s}-2023-01-06": {} for s in ("FPT", "MWG", "VCB", "VNM")}}
        result = mde_planning(self.panels, plan)
        self.assertEqual(len(result["scenarios"]), 54)
        self.assertEqual(result["independent_antithetic_pairs"], 5000)
        self.assertFalse(result["confirmation_power_certified"])
        self.assertFalse(result["alters_sample_or_method"])
        self.assertEqual(result["status"], "PLANNING_ONLY")
        for row in result["scenarios"]:
            powers = [v["power"] for v in row["power_curve"]]
            self.assertEqual(powers, sorted(powers))
            self.assertTrue(all(0 <= v <= 1 for v in powers))
            self.assertTrue(all(v["monte_carlo_se"] >= 0 for v in row["power_curve"]))
            self.assertGreaterEqual(row["location_shift_mde_80_pp"], 0)
            self.assertEqual(row["points"], 128 if row["layout"].startswith("hypothetical") else 4)
        self.assertEqual(result["policy"], planning_policy())

    def test_repeat_fill_records_missing_stratum_without_changing_sample(self) -> None:
        requests = {}
        for s in ("FPT", "MWG", "VCB", "VNM"):
            for day, flags in (("01", (True, True)), ("02", (True, True)), ("03", (False, False)), ("04", (False, False))):
                requests[f"{s}-2023-01-{day}"] = {"u_evidence": {"posterior": {"gate": {"ready": flags[0]}},
                    "selection": {"gate": {"ready": flags[1]}}}, "upstream": {}, "packets": {}}
        plan = {"requests": requests, "repeat_sample": repeat_sample(requests), "schedule": []}
        before = deepcopy(plan)
        result = repeat_design(plan)
        self.assertEqual([r["point_id"] for r in result["sample"]], plan["repeat_sample"])
        fillers = [r for r in result["sample"] if r["selection_reason"] == "FILL_MISSING_STRATUM"]
        self.assertEqual(len(fillers), 4)
        self.assertTrue(all(r["filled_for"] == "one_block_ready" for r in fillers))
        self.assertFalse(result["in_primary"])
        self.assertFalse(result["vote"])
        self.assertEqual(plan, before)

    def test_coverage_gates_are_separate_from_observed_llm_support(self) -> None:
        branch = {"U_full": {"visible_count": 8}, "U_examples": {"visible_count": 3}}
        stock = {"branches": branch, "at_least_two_selected_tasks": 3}
        diag = {"overall": {"branches": {"U_full": {"visible_count": 32}, "U_examples": {"visible_count": 12}},
                            "at_least_two_selected_tasks": 12},
                "by_symbol": {s: deepcopy(stock) for s in ("FPT", "MWG", "VCB", "VNM")}}
        result = coverage(diag)
        self.assertEqual(set(result["checks"].values()), {"PASS"})
        self.assertEqual(result["observed_llm_common_support"], 0)
        self.assertFalse(result["nomination_allowed"])
        diag["by_symbol"]["FPT"]["branches"]["U_full"]["visible_count"] = 4
        self.assertEqual(coverage(diag)["checks"]["prior_visible"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(coverage(diag)["checks"]["examples_visible"], "PASS")

    def test_assessment_reader_rejects_self_resealed_mde_or_release_claim(self) -> None:
        expected = {"assessment_version": "fixture", "mde": {"status": "PLANNING_ONLY"}, "confirmation_allowed": False}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "assessment.json"
            save_envelope(path, expected)
            self.assertEqual(read_assessment(path, expected), expected)
            value = deepcopy(expected)
            value["confirmation_allowed"] = True
            save_envelope(path, value)
            with self.assertRaises(ValueError):
                read_assessment(path, expected)


class ReadinessFixture:
    """Nguồn bốn mã tổng hợp; receipt/log giả chỉ kiểm tích hợp trong temp, không nghiệm thu."""

    @classmethod
    def setUpClass(cls) -> None:
        from core.historical_outcomes import HistoricalOutcomeGenerator
        from scripts.prepare_unified_bayes_memory import PROTOCOL_SHA
        inputs = dense_inputs()
        inputs["protocol_sha256"] = PROTOCOL_SHA
        generator = HistoricalOutcomeGenerator(inputs["prices"].__getitem__)
        for year in ("2021", "2022"):
            sample = [r for r in inputs["original"] if r["symbol"] == "FPT" and r["as_of_date"].startswith(year)][:12]
            for source in sample:
                for symbol in ("MWG", "VCB", "VNM"):
                    if any(r["symbol"] == symbol and r["as_of_date"] == source["as_of_date"] for r in inputs["original"]):
                        continue
                    row = deepcopy(source)
                    row.update(symbol=symbol, episode_id=f"{symbol}:{source['as_of_date']}")
                    row["outcome"] = generator.generate(symbol, row["as_of_date"], row["entry_date"], row["exit_date"],
                        row["agent_signals"], settled_as_of="2022-12-30")
                    inputs["original"].append(row)
        cls.inputs, cls.context = inputs, make_context(inputs)

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.fx = ExecutionFixture(Path(temporary.name), self.context, self.inputs)
        self.addCleanup(self.fx.close)
        self.cohort = make_cohort(self.fx)
        self.plan = self.cohort.plan(self.fx.llm)
        self.memory = self.context.memory.payload
        points = [{k: r[k] for k in ("episode_id", "symbol", "as_of_date", "exit_date")} |
                  {"fold_id": "train_"+r["as_of_date"][:4], "net_long_return": r["outcome"]["net_return_pct"]/100.}
                  for r in self.memory["records"] if r["as_of_date"][:4] in ("2021", "2022")
                  and r["exit_date"][:4] == r["as_of_date"][:4]]
        self.pool_path = self.fx.root / "pooling_fixture.json"
        save_envelope(self.pool_path, {"memory_sha256": digest(self.memory), "protocol_sha256": self.plan["protocol_sha256"],
            "points": points, "query_count": len(points), "sources": {}, "runtime": self.plan["runtime"],
            "folds": {"train_"+year: {"query_ids": [r["episode_id"] for r in points if r["as_of_date"].startswith(year)]}
                      for year in ("2021", "2022")}})
        diag = diagnostics(self.cohort, self.plan, self.fx.llm, self.memory)
        def fixture_process(command, **kwargs):
            # Các chuỗi này chỉ kiểm consumer trong fixture, không phải log dự án.
            if "compileall" in command:
                text = "\n".join(f"Listing '{p}'..." for p in ("agents", "core", "data_manager", "scripts", "tests", "utils"))
            elif "scripts/run_end_to_end_test.py" in command:
                text = "ALL PIPELINE CHECKS SUCCESSFUL"
            else:
                text = "Ran 1 test in 0.1s\n\nOK\n"
            kwargs["stdout"].write(text.encode("utf-8"))
            return SimpleNamespace(returncode=0)
        with patch("core.unified_bayes_validation.subprocess.run", side_effect=fixture_process):
            self.audit = run_gates(self.plan, diag, self.fx.root / "validation", notify=lambda _: None)

    def assessment(self) -> dict:
        """Tái dựng qua cả source, diagnostic, receipt và MDE production."""
        return build_assessment(self.cohort, self.plan, self.fx.llm, self.memory, self.audit, pooling_path=self.pool_path)


class ReadinessIntegrationTests(ReadinessFixture, unittest.TestCase):
    """Không tạo action/UUID/payoff query khi khóa readiness và kế hoạch noise."""

    def test_whole_assessment_rebuilds_with_zero_http_and_query_evaluation(self) -> None:
        result = self.assessment()
        self.assertEqual(result["logical_slots"], {"primary_llm": 20, "repeat_llm": 72, "numeric_offline_blocks": 16})
        self.assertEqual(len(result["mde"]["scenarios"]), 54)
        self.assertIsNone(result["execution_readiness"])
        self.assertEqual(self.fx.calls, [])
        self.assertEqual(self.fx.evaluations, [])
        self.assertFalse((self.fx.root / "cohort").exists())

    def test_assessment_repeat_model_and_mde_edits_are_not_trusted(self) -> None:
        result = self.assessment()
        path = self.fx.root / "assessment.json"
        for field in ("models", "repeat", "mde"):
            with self.subTest(field=field):
                value = deepcopy(result)
                value[field] = {}
                save_envelope(path, value)
                with self.assertRaises(ValueError):
                    read_assessment(path, result)

    def test_cli_fixture_stops_without_key_or_runtime_writes(self) -> None:
        import sys
        from scripts import prepare_unified_bayes_readiness as cli
        source, plan_path, memory_path = self.fx.root / "source", self.fx.root / "plan.json", self.fx.root / "memory.json"
        source.mkdir()
        save_envelope(source / "plan.json", {"inputs": {"signal_config": {"models": self.plan["models"]}}})
        save_envelope(plan_path, self.plan)
        save_envelope(memory_path, self.memory)
        output = self.fx.root / "readiness"
        with patch.multiple(cli, ROOT=self.fx.root, SOURCE=source, PLAN_PATH=plan_path, MEMORY_PATH=memory_path,
                            NAMESPACE=self.fx.root, OUTPUT=output), \
             patch.object(cli, "load_source", return_value=self.cohort), \
             patch.object(cli, "build_assessment", return_value={"split": "fixture", "execution_readiness": None}), \
             patch("dotenv.dotenv_values", side_effect=AssertionError("Đọc key")), \
             patch.object(sys, "argv", ["readiness", "--prepare", "--validation-audit", str(self.audit)]), \
             self.assertRaises(ValueError):
            cli.main()
        self.assertFalse(output.exists())
        self.assertEqual(self.fx.calls, [])


if __name__ == "__main__":
    unittest.main()
