"""Oracle posterior, partition, masks A, scoring và rule chọn pooling đã khóa."""

from copy import deepcopy
import math
from types import SimpleNamespace
import unittest

import numpy as np

from core.bayesian_retriever import BayesianPriorRetriever, PREFIX_METRICS
from core.improvement_prior import tp_statistics
from core.unified_bayes_diagnostics import fold_schedule, pooling_gate, rank_lambdas, score_rows, select_backbone
from core.unified_bayes_memory import build_memory
from core.unified_bayes_statistics import MODELS, UnifiedBayesStatistics, partition_records, posterior, stats_gate
from unified_memory_test_support import SIGNALS
from unified_pooling_test_support import fixture, score_points, statistics_inputs


class UnifiedStatisticsTests(unittest.TestCase):
    """Tính số bằng fixture độc lập và so A với primitive legacy trên memory chung."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = fixture()
        cls.inputs = statistics_inputs()
        cls.memory = build_memory(**cls.inputs)
        cls.statistics = UnifiedBayesStatistics(cls.memory)

    def test_locked_posterior_oracles_including_empty_tiers(self) -> None:
        """Tám oracle giữ đúng alpha/beta/mean/CrI, null và reason từng tầng."""
        for case in self.fixture["posterior_cases"]:
            values = dict(case["input"])
            values["lambda_value"] = values.pop("lambda")
            actual = posterior(**values)
            with self.subTest(case=case["case_id"]):
                for key, value in case["expected"].items():
                    if value is None:
                        self.assertIsNone(actual[key])
                    elif key == "credible_interval":
                        self.assertAlmostEqual(actual[key]["lower"], value[0], places=12)
                        self.assertAlmostEqual(actual[key]["upper"], value[1], places=12)
                    else:
                        self.assertAlmostEqual(actual[key], value, places=12)
                self.assertEqual(actual["reason_codes"], case["expected_reason_codes"])

    def test_locked_partition_oracle_is_disjoint_and_excludes_future(self) -> None:
        """C/B1/B2 chỉ dùng metadata PIT, khác mã và query self không lọt vào."""
        case = self.fixture["partition_case"]
        query = case["query"]
        records = [{"episode_id": row["id"], "symbol": row["symbol"], "regime": row["regime"],
            "as_of_date": row["as_of_date"], "exit_date": row["exit_date"],
            "agent_signals": {**SIGNALS, "trend": row["trend"], "pattern": row["pattern"]}} for row in case["records"]]
        result = partition_records(records, symbol=query["symbol"], as_of_date=query["as_of_date"],
            current_regime=query["regime"], current_signals={**SIGNALS, "trend": query["trend"], "pattern": query["pattern"]})
        self.assertEqual(result, {key: sorted(value) for key, value in case["expected"].items()})

    def test_readiness_boundaries_match_locked_fixture(self) -> None:
        """Raw posterior không bị bỏ trước scoring vì n/width chưa đạt gate."""
        for case in self.fixture["stats_gate_cases"]:
            with self.subTest(case=case["case_id"]):
                result = stats_gate("A_tp_pool" if case["backbone"] == "A" else "hierarchical_pool",
                    **{key: case[key] for key in ("population", "nC", "background", "width")})
                self.assertIs(result["ready"], case["expected_ready"])

    def test_pool_gate_and_lambda_rank_match_locked_fixture(self) -> None:
        """Không làm tròn loss hoặc nhận lambda thứ hai sau gate trượt."""
        for case in self.fixture["pooling_gate_cases"]:
            with self.subTest(case=case["case_id"]):
                self.assertIs(pooling_gate(case["A"], case["pool"])["accepted"], case["expected_accept"])
        for case in self.fixture["lambda_rank_cases"]:
            self.assertEqual(rank_lambdas(case["metrics"]), case["expected_lambda"])

    def test_reference_keeps_all_four_legacy_A_metrics(self) -> None:
        """A trên nguồn chung khớp tp_statistics, không rút A_reference thành một metric."""
        retriever = BayesianPriorRetriever.__new__(BayesianPriorRetriever)
        retriever._verified_by_id = deepcopy(self.memory._records)
        retriever._memory = SimpleNamespace(eligible=lambda day, symbol: self.memory.eligible(symbol, day))
        retriever._bank_sha256 = self.memory.index.payload["provenance"]["bank"]["bank_sha256"]
        query = {"symbol": "FPT", "as_of_date": "2023-06-01", "current_regime": "BULL", "current_signals": SIGNALS}
        legacy = tp_statistics(retriever, **query)
        current = self.statistics.evidence(**query)
        self.assertEqual(set(current["reference_metrics"]), set(PREFIX_METRICS))
        self.assertEqual(current["reference_metrics"], legacy["metrics"])
        self.assertEqual(current["counts"], {"nC": 4, "sC": 0, "n1": 1, "s1": 0, "n2": 2, "s2": 0})

    def test_missing_features_and_old_age_stay_in_statistics(self) -> None:
        """Observation quyền/tuổi cũ vẫn góp s/n; không giới hạn bằng K hay examples."""
        evidence = self.statistics.evidence(symbol="FPT", as_of_date="2025-01-02", current_regime="BULL", current_signals=SIGNALS)
        ids = sum((group["episode_ids"] for group in evidence["groups"].values()), [])
        self.assertIn("FPT:2020-06-12", ids)
        self.assertGreater(evidence["groups"]["B1"]["age_days"]["max"], 730)
        self.assertEqual(len(ids), 8)
        self.assertFalse(evidence["raw_support_is_effective_sample_size"])

    def test_invalid_counts_strength_nan_and_non_native_are_rejected(self) -> None:
        """Không coercion bool/NumPy thành counts hoặc thêm lambda sau khi xem loss."""
        base = {"nC": 5, "sC": 3, "n1": 20, "s1": 8, "n2": 10, "s2": 7}
        for changes in ({"nC": True}, {"sC": 6}, {"n1": -1}, {"n2": np.int64(10)}, {"lambda_value": 16}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                posterior(**(base | changes))
        with self.assertRaises(ValueError):
            rank_lambdas([[2, math.nan, .2], [4, .6, .2], [8, .6, .2]])

    def test_fold_purges_end_crossing_and_keeps_scaler_strict_at_start(self) -> None:
        """Không dùng mẫu số legacy bỏ qua purge cuối năm; không refit trong fold."""
        from scripts.prepare_unified_bayes_pooling import load_protocol
        protocol = load_protocol()
        with self.assertRaises(ValueError):
            fold_schedule(self.memory, self.inputs["calendar"], protocol)
        folds = fold_schedule(self.memory, self.inputs["calendar"], protocol, enforce_locked=False)
        self.assertEqual(len(folds["train_2021"]["purged_at_end_ids"]), 4)
        for fold in folds.values():
            self.assertTrue(all(self.memory._metadata[key]["exit_date"] <= fold["query_end"] for key in fold["query_ids"]))
            for item in fold["symbols"].values():
                self.assertTrue(all(self.memory._metadata[key]["exit_date"] < fold["query_start"] for key in item["fit_closed_ids"]))


class UnifiedScoringTests(unittest.TestCase):
    """Loss được chấm trên cùng mẫu số, gate chọn một lần và lưu đầy đủ lý do."""

    def test_brier_raw_logloss_clipped_and_readiness_does_not_remove_points(self) -> None:
        rows = score_points()
        for row in rows:
            row["probability"] = dict(zip(MODELS, (0., 1., .5, .25)))
            row["ready"] = {name: False for name in MODELS}
        summary = score_rows(rows)["overall"]
        self.assertEqual(summary["common_count"], 8)
        self.assertEqual(summary["loss"]["A_tp_pool"]["brier"], 1.)
        self.assertAlmostEqual(summary["loss"]["A_tp_pool"]["log_loss"], -math.log(1e-6), places=12)
        self.assertEqual(summary["loss"]["pool_2"]["brier"], 0.)
        self.assertEqual(summary["coverage"]["A_tp_pool"]["ready_count"], 0)

    def test_common_intersection_and_all_query_ready_coverage_are_distinct(self) -> None:
        rows = score_points(doubled=True)
        rows[0]["probability"]["pool_2"] = None
        rows[0]["ready"]["pool_2"] = False
        summary = score_rows(rows)
        self.assertEqual(summary["overall"]["common_count"], 15)
        self.assertEqual(summary["overall"]["coverage"]["A_tp_pool"]["raw_count"], 16)
        self.assertEqual(summary["overall"]["coverage"]["A_tp_pool"]["ready_count"], 16)
        choice = select_backbone(summary)
        self.assertEqual(choice["choice"], "A_tp_pool")
        self.assertEqual(choice["ranked_lambda"], 2)
        self.assertEqual(choice["reasons"], ["READY_COVERAGE_REDUCTION"])

    def test_loss_weights_queries_equally_not_strata_means(self) -> None:
        rows = score_points(doubled=True)
        rows = [row for i, row in enumerate(rows) if i not in (0, 2, 4)]
        for i, row in enumerate(rows):
            row["probability"] = {name: .1 + i / 100 for name in MODELS}
        result = score_rows(rows)["overall"]
        expected = sum((row["probability"]["A_tp_pool"] - 1.) ** 2 for row in rows) / len(rows)
        self.assertAlmostEqual(result["loss"]["A_tp_pool"]["brier"], expected, places=14)
        self.assertEqual(result["common_count"], len(rows))

    def test_winner_gate_fails_without_trying_valid_runner_up(self) -> None:
        summary = score_rows(score_points())
        for group in [summary["overall"], *summary["by_fold"].values(), *summary["by_symbol"].values(), *summary["by_fold_symbol"].values()]:
            for name, logloss, brier in zip(MODELS, (.69, .5, .6, .7), (.25, .3, .24, .24)):
                group["loss"][name] = {"log_loss": logloss, "brier": brier}
        choice = select_backbone(summary)
        self.assertEqual(choice["ranked_lambda"], 2)
        self.assertEqual(choice["choice"], "A_tp_pool")
        self.assertIsNone(choice["lambda"])
        self.assertIn("BRIER_REGRESSION", choice["reasons"])

    def test_missing_stratum_and_empty_common_keep_A_with_reasons(self) -> None:
        rows = score_points()
        choice = select_backbone(score_rows(rows[1:]))
        self.assertEqual(choice["choice"], "A_tp_pool")
        self.assertIn("MISSING_COMMON_FOLD_SYMBOL_STRATUM", choice["reasons"])
        for row in rows:
            row["probability"] = {name: None for name in MODELS}
            row["ready"] = {name: False for name in MODELS}
        choice = select_backbone(score_rows(rows))
        self.assertEqual(choice["reasons"], ["NO_COMMON_POSTERIOR"])

    def test_full_precision_ranking_and_successful_pool_gate(self) -> None:
        self.assertEqual(rank_lambdas([[2, .6, .24], [4, .6 - 1e-13, .25], [8, .7, .2]]), 4)
        choice = select_backbone(score_rows(score_points()))
        self.assertEqual((choice["choice"], choice["lambda"], choice["gate_status"]), ("hierarchical_pool", 2, "PASS"))

    def test_duplicate_cycle_oos_target_invalid_label_and_nan_raise(self) -> None:
        cases = []
        rows = score_points()
        cases.append(rows + [{**deepcopy(rows[0]), "episode_id": "another-id"}])
        for change in ({"label": 0}, {"net_long_return": math.nan}, {"as_of_date": "2023-01-03"}, {"exit_date": "2022-01-04"}):
            rows = score_points()
            rows[0].update(change)
            cases.append(rows)
        for rows in cases:
            with self.assertRaises(ValueError):
                score_rows(rows)

    def test_choice_binds_diagnostics_source_code_runtime_and_no_execution(self) -> None:
        from scripts.prepare_unified_bayes_pooling import PROTOCOL_SHA, choice_for_report
        report = {"report_version": "unified_pooling_diagnostics_v1", "protocol_sha256": PROTOCOL_SHA,
            "summary": score_rows(score_points()), "sources": {"fixture": "a" * 64},
            "memory_sha256": "b" * 64, "index_sha256": "c" * 64, "code_sha256": {}, "runtime": {"python": "fixture"}}
        choice = choice_for_report(report, "d" * 64)
        self.assertFalse(choice["confirmation_allowed"])
        self.assertEqual(choice["diagnostics_sha256"], "d" * 64)
        changed = deepcopy(report)
        changed["sources"]["fixture"] = "e" * 64
        self.assertNotEqual(choice_for_report(changed, "d" * 64)["source_sha256"], choice["source_sha256"])
        with self.assertRaises(ValueError):
            choice_for_report(report, "invalid")


if __name__ == "__main__":
    unittest.main()
