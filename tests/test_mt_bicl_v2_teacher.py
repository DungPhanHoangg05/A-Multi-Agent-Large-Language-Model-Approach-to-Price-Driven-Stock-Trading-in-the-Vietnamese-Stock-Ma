"""Kiểm toán teacher, MAP-EM và sampler v2 bằng fixture/toán độc lập trên CPU."""

from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from core.mt_bicl_bank import canonical_bytes
from core.mt_bicl_v2_preparation import fixture_input, prepare_teacher
from core.mt_bicl_v2_reference import SequentialBetaOracle
from core.mt_bicl_v2_simulator import BetaTaskSimulator
from core.mt_bicl_v2_teacher import BetaBernoulliTeacher, fit_hyperprior, prior_predictive_audit

ROOT = Path(__file__).resolve().parents[1]


def simulator() -> BetaTaskSimulator:
    """Pool giả731 vector nguyên vẹn, không đọc nhãn thị trường thật."""
    manifest = json.loads((ROOT/"docs/plan/week10/corpus_manifest_v2.json").read_bytes())
    pool = {"vectors": [[float((i+j) % 9-4) for j in range(4)] for i in range(731)],
            "source_outcomes_used": False}
    return BetaTaskSimulator([1/16]*16, pool, manifest)


class TeacherMathTests(unittest.TestCase):
    """Oracle scalar và expected fixture không dùng chung likelihood log-beta."""

    def setUp(self) -> None:
        """Mỗi test có teacher mới, không fit market hoặc dùng CUDA."""
        self.pi = [1/16]*16
        self.teacher, self.reference = BetaBernoulliTeacher(self.pi), SequentialBetaOracle(self.pi)
        self.fixtures = json.loads((ROOT/"docs/plan/week10/protocol_fixtures_v2.json").read_bytes())

    def test_five_locked_math_fixtures_and_posterior(self) -> None:
        for fixture in self.fixtures["teacher_cases"]:
            data = fixture_input(fixture["prior_counts"], fixture["target_counts"])
            for pooled, key in ((False, "p"), (True, "pooling_p")):
                actual = self.teacher.predict(data, pooled=pooled, posterior=True)
                expected = self.reference.predict(data, pooled=pooled, posterior=True)
                self.assertAlmostEqual(actual["probability"], fixture[key], delta=1e-12)
                for field in ("probability", "log_probability_one", "log_probability_zero"):
                    self.assertAlmostEqual(actual[field], expected[field], delta=1e-12)
                np.testing.assert_allclose(actual["lambda_posterior"], expected["lambda_posterior"], atol=1e-12, rtol=0)
                self.assertAlmostEqual(math.exp(actual["log_probability_one"])+math.exp(actual["log_probability_zero"]), 1., delta=1e-12)

    def test_reference_does_not_call_production_likelihood(self) -> None:
        data = fixture_input([[6, 0], [0, 6]], [3, 0])
        with patch("core.mt_bicl_v2_teacher.log_likelihood", side_effect=AssertionError("Không dùng helper chung")):
            self.assertAlmostEqual(self.reference.predict(data)["probability"], .8400543462360881, delta=1e-12)

    def test_nonuniform_pi_extreme_labels_and_features_remain_consistent(self) -> None:
        pi = (np.arange(1,17,dtype=float)/136).tolist()
        teacher, oracle = BetaBernoulliTeacher(pi), SequentialBetaOracle(pi)
        for prior, target in (([[8,0]]*3,[8,0]), ([[0,8]]*3,[0,8]), ([[8,0],[0,8]],[0,0])):
            data = fixture_input(prior,target)
            data["query"]["x"] = [4.,-4.,4.,-4.]
            for pooled in (False,True):
                a,b = teacher.predict(data,pooled=pooled),oracle.predict(data,pooled=pooled)
                for key in ("probability","log_probability_one","log_probability_zero"):
                    self.assertAlmostEqual(a[key],b[key],delta=1e-12)

    def test_target_updates_lambda_and_frozen_pi(self) -> None:
        data = fixture_input([], [3, 0])
        result = self.teacher.predict(data, posterior=True)
        self.assertGreater(max(abs(x-1/16) for x in result["lambda_posterior"]), .01)
        frozen_lambda = sum((mu*k+3)/(k+3)/16 for mu in (.2,.4,.6,.8) for k in (2,8,32,128))
        self.assertGreater(abs(result["probability"]-frozen_lambda), .01)
        self.pi[0] = .9
        self.assertEqual(self.teacher.pi.tolist(), [1/16]*16)
        with self.assertRaises(ValueError):
            self.teacher.pi[0] = .9
        canonical_bytes(result)

    def test_task_grouping_changes_hierarchy_but_not_shared_theta(self) -> None:
        original = fixture_input([[6, 0], [0, 6]], [3, 0])
        regrouped = fixture_input([[3, 3], [3, 3]], [3, 0])
        self.assertGreater(abs(self.teacher.predict(original)["probability"]-self.teacher.predict(regrouped)["probability"]), .01)
        self.assertAlmostEqual(self.teacher.predict(original, pooled=True)["probability"],
                               self.teacher.predict(regrouped, pooled=True)["probability"], delta=1e-12)
        permuted = deepcopy(original)
        permuted["prior"].reverse()
        for task in [*permuted["prior"], permuted["target"]]:
            task["observations"].reverse()
        self.assertAlmostEqual(self.teacher.predict(original)["probability"], self.teacher.predict(permuted)["probability"], delta=1e-12)

    def test_one_em_step_matches_independent_scalar_responsibilities(self) -> None:
        tasks = [{"task_id": "A", "successes": 7, "failures": 2, "count": 9},
                 {"task_id": "B", "successes": 1, "failures": 6, "count": 7}]
        scalar = []
        for task in tasks:
            likelihoods = []
            for mu in (.2,.4,.6,.8):
                for k in (2,8,32,128):
                    a, b, value = mu*k, (1-mu)*k, 1.
                    for y in [1]*task["successes"]+[0]*task["failures"]:
                        value *= (a if y else b)/(a+b)
                        a, b = a+y, b+1-y
                    likelihoods.append(value)
            scalar.append([v/math.fsum(likelihoods) for v in likelihoods])
        expected = [(sum(row[j] for row in scalar)+1)/18 for j in range(16)]
        with patch("core.mt_bicl_v2_teacher.MAX_ITERATIONS", 1):
            result = fit_hyperprior(tasks)
        np.testing.assert_allclose(result["pi"], expected, atol=1e-13, rtol=0)
        self.assertFalse(result["converged"])
        self.assertEqual(result["iterations"], 1)
        self.assertGreaterEqual(result["fit_objective_trace"][1]["objective"], result["fit_objective_trace"][0]["objective"])

    def test_em_stationary_uniform_and_nonconvergence_blocks_predictive(self) -> None:
        tasks = [{"task_id": str(j), "successes": j % 2, "failures": 1-j % 2, "count": 1} for j in range(16)]
        result = fit_hyperprior(tasks)
        self.assertTrue(result["converged"])
        self.assertEqual(result["iterations"], 1)
        np.testing.assert_allclose(result["pi"], [1/16]*16, atol=1e-15, rtol=0)
        inputs = {"fixtures": self.fixtures, "bank": {}, "membership": {},
                  "identity": {"code_sha256": {}}, "protocol": {"runtime": {}, "artifacts": {"training_membership_v2.json": "fixture"}}}
        failed = {**result, "converged": False, "status": "STOP_TEACHER_NONCONVERGENCE_NO_UNIFORM_FALLBACK"}
        with patch("core.mt_bicl_v2_preparation.train_task_counts", return_value=tasks), \
                patch("core.mt_bicl_v2_preparation.fit_hyperprior", return_value=failed), \
                patch("core.mt_bicl_v2_preparation.prior_predictive_audit", side_effect=AssertionError("Không dùng π chưa hội tụ")):
            value = prepare_teacher(inputs)
        self.assertEqual(value["prior_predictive_audit"]["status"], "NOT_RUN_TEACHER_NONCONVERGENCE")

    def test_prior_predictive_reproducible_sizes_quantiles_and_no_new_gate(self) -> None:
        tasks = [{"task_id": "A", "count": 3, "successes": 1}, {"task_id": "B", "count": 7, "successes": 5}]
        audit = prior_predictive_audit(tasks, self.pi, 2026102808)
        self.assertEqual(audit, prior_predictive_audit(tasks, self.pi, 2026102808))
        self.assertEqual(audit["task_sizes"], [3,7])
        self.assertEqual(audit["observed"]["mean_rate"], .6)
        intervals = np.quantile([r["mean_rate"] for r in audit["replicate_summaries"]], [.025,.975], method="linear")
        self.assertEqual(audit["predictive_95_percent_intervals"]["mean_rate"], intervals.tolist())
        self.assertFalse(audit["market_fit_quality_is_release_gate"])
        canonical_bytes(audit)


class TeacherSimulatorTests(unittest.TestCase):
    """Kiểm RNG, stress, intervention và oracle trên episode do sampler sinh."""

    def test_random_access_stream_separation_whole_vector_and_oracle(self) -> None:
        sim = simulator()
        original = sim.episode("diagnostic", 0)
        sim.episode("train", 1000, model_seed=42)
        self.assertEqual(original, sim.episode("diagnostic", 0))
        ids = {sim.episode(name, 0, model_seed=seed)["episode_id"] for name, seed in (
            ("train",17), ("train",42), ("train",73), ("diagnostic",0), ("synthetic_validation",0), ("synthetic_test",0))}
        self.assertEqual(len(ids), 6)
        for index in range(64):
            episode = sim.episode("diagnostic", index)
            data = episode["input"]
            for task in [*data["prior"], data["target"]]:
                for row in task["observations"]:
                    self.assertIn(row["x"], sim.pool.tolist())
            a = BetaBernoulliTeacher([1/16]*16).predict(data)
            b = SequentialBetaOracle([1/16]*16).predict(data)
            self.assertAlmostEqual(a["probability"], b["probability"], delta=1e-12)

    def test_stress_recipe_counts_sign_and_no_latent(self) -> None:
        sim = simulator()
        for index in (4500,4504,4505,4509,4510,4999):
            episode = sim.episode("synthetic_validation", index)
            case = (index-4500) % 10
            self.assertEqual(len(episode["input"]["prior"]), 1 if case < 5 else 3)
            self.assertEqual(len(episode["input"]["target"]["observations"]), [0,1,2,4,8][case % 5])
            self.assertIsNone(episode["sidecar"]["theta"])
            self.assertIsNone(episode["sidecar"]["query_y"])
            self.assertEqual(len(episode["input"]["prior"][0]["observations"]), 8)
        with self.assertRaises(ValueError):
            sim.episode("synthetic_test", 5000)
        with self.assertRaises(ValueError):
            sim.episode("train", 0)

    def test_prior_swap_holds_all_features_target_query_and_ids(self) -> None:
        sim = simulator()
        for index in (0,1,10,4500,4509,4510):
            pair = sim.pair("validation_swap", index)
            self.assertEqual(pair, sim.pair("validation_swap", index))
            a, b = pair["input_a"], pair["input_b"]
            self.assertEqual(a["target"], b["target"])
            self.assertEqual(a["query"], b["query"])
            for left, right in zip(a["prior"],b["prior"]):
                self.assertEqual(left["task_id"], right["task_id"])
                self.assertEqual([{k:v for k,v in row.items() if k != "y"} for row in left["observations"]],
                                 [{k:v for k,v in row.items() if k != "y"} for row in right["observations"]])
            if index == 4500:
                teacher = BetaBernoulliTeacher([1/16]*16)
                self.assertGreater(abs(teacher.predict(a)["probability"]-teacher.predict(b)["probability"]), .05)


if __name__ == "__main__":
    unittest.main()
