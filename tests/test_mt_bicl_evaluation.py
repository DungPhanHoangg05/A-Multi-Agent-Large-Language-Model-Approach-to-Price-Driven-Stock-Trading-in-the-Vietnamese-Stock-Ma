"""Kiểm metric/gate, calibration và journal đánh giá bằng fixture, không xem held test."""

from copy import deepcopy
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from sklearn.exceptions import ConvergenceWarning
import torch

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

from core.mt_bicl_bank import content_hash
from core.mt_bicl_evaluation import (baseline_logits, fit_baselines, market_report, mechanism_metrics,
                                    model_fingerprint, predict_packets, probabilities, prior_swap_metrics)
from core.mt_bicl_evaluation_run import derive_report, evaluate_run, verify_evaluation
from core.mt_bicl_model import MTBiCLLearner
from core.mt_bicl_scaler import fit_scaler
from core.mt_bicl_simulator import FiniteSimulator, pack_input
from core.mt_bicl_training import configure
from core.mt_bicl_training_io import file_hash, read_manifest, write_manifest
from mt_bicl_tasks_support import setup

ROOT = Path(__file__).resolve().parents[1]


def fixture() -> tuple[dict, dict, dict]:
    """Tập nhỏ có candidate seed17 cố định và 201 cặp eligible, không là số liệu production."""
    rows = [{"query": {"episode_id": f"{s}-2022-01-04", "symbol": s, "as_of_date": "2022-01-04"},
             "supervised_target": {"y": i % 2, "r_net": .001 if i % 2 else -.05}, "K": 3, "m": i}
            for i, s in enumerate(("FPT", "MWG", "VCB", "VNM"))]
    tests = [{"oracle": {"probability": .5, "log_probability_one": math.log(.5),
                         "log_probability_zero": math.log(.5), "K": i, "m": i}} for i in range(2)]
    pairs = [{"oracle_a": {"probability": .2}, "oracle_b": {"probability": .8}, "eligible": True} for _ in range(201)]
    records = {str(s): {"seed": s, "step": 1000} for s in (17, 42, 73)}
    inputs = {"identity": {"fixture": "test_only"}, "selection": {"candidate": records["17"], "per_seed": records},
              "rows": rows, "corpus": {"synthetic_test": tests, "prior_swap_pairs": pairs,
              "pooling_control": {"hierarchical": {"probability": .71}, "pooled": {"probability": .61}}},
              "bank": {"records": [{"query_split": "validation", "status": "AVAILABLE", "reasons": []}]*4}}
    baseline = {"identity_sha256": content_hash(inputs["identity"]), "fit": {"fixture": True},
                "seconds": .01, "market_logits": {name: [0.]*4 for name in ("base_rate", "logistic", "naive_pooling")}}
    seeds = {str(s): {"identity_sha256": content_hash(inputs["identity"]), "seed": s, "checkpoint": records[str(s)],
              "optimizer_used": False, "weights_unchanged": True, "model_tensor_sha256": "fixture",
              "stage_seconds": {"fixture": .01}, "logits": {
              "synthetic_test": [1000.]*2 if s == 17 else [0.]*2,
              "prior_swap_a": [-1.]*201, "prior_swap_b": [1.]*201, "pooling_control": [0.],
              "market_full": [1000.]*4 if s == 17 else [0.]*4,
              "market_no_prior": [0.]*4, "market_no_target": [0.]*4}} for s in (17, 42, 73)}
    return inputs, baseline, seeds


class EvaluationMetricTests(unittest.TestCase):
    """Cực trị logits và kết quả bất lợi phải giữ nguyên, không đổi denominator/gate."""

    def test_kl_extreme_logits_is_not_hidden_by_probability_clipping(self) -> None:
        inputs, _, _ = fixture()
        result = mechanism_metrics([1000., -1000.], inputs["corpus"]["synthetic_test"])
        self.assertGreater(result["mean_kl_nats"], 499.)
        self.assertEqual(result["gate"], "FAIL")
        self.assertEqual(probabilities([1000., -1000.])[0].tolist(), [1., 0.])

    def test_oracle_identity_has_zero_kl_and_linear_p95(self) -> None:
        inputs, _, _ = fixture()
        episodes = inputs["corpus"]["synthetic_test"]
        result = mechanism_metrics([0., 0.], episodes)
        self.assertAlmostEqual(result["mean_kl_nats"], 0.)
        self.assertEqual(result["gate"], "PASS")
        errors = abs(probabilities([0., 2.])[0]-.5)
        self.assertAlmostEqual(mechanism_metrics([0., 2.], episodes)["p95_absolute_error"], float(np.quantile(errors, .95, method="linear")))

    def test_swap_denominator_minimum_zero_delta_and_wrong_eligibility(self) -> None:
        inputs, _, _ = fixture()
        pairs = inputs["corpus"]["prior_swap_pairs"]
        self.assertEqual(prior_swap_metrics([-1.]*201, [1.]*201, pairs)["sign_agreement"], 1.)
        zero = prior_swap_metrics([0.]*201, [0.]*201, pairs)
        self.assertEqual((zero["gate"], zero["zero_model_delta_eligible"]), ("FAIL", 201))
        self.assertEqual(prior_swap_metrics([-1.]*199, [1.]*199, pairs[:199])["gate"], "INCONCLUSIVE_BLOCK_DEVELOPMENT")
        pairs[0]["eligible"] = False
        with self.assertRaises(ValueError):
            prior_swap_metrics([-1.]*201, [1.]*201, pairs)

    def test_bad_probability_and_mismatched_counts_rejected(self) -> None:
        inputs, _, _ = fixture()
        for value in (float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                probabilities([value])
        with self.assertRaises(ValueError):
            mechanism_metrics([0.], inputs["corpus"]["synthetic_test"])
        inputs["corpus"]["synthetic_test"][0]["oracle"]["log_probability_zero"] = 0.
        with self.assertRaises(ValueError):
            mechanism_metrics([0., 0.], inputs["corpus"]["synthetic_test"])

    def test_calibration_empty_bins_endpoints_returns_and_macro(self) -> None:
        inputs, _, _ = fixture()
        result = market_report([-1000., 1000., 0., math.log(.1/.9)], inputs["rows"])
        self.assertEqual(len(result["calibration"]), 10)
        self.assertEqual(result["calibration"][0]["count"], 1)
        self.assertEqual(result["calibration"][-1]["count"], 1)
        self.assertTrue(result["calibration"][-1]["right_inclusive"])
        self.assertIsNone(result["calibration"][8]["mean_p"])
        self.assertEqual(result["return_diagnostics"]["mean_positive_gain"], .001)
        self.assertEqual(result["return_diagnostics"]["mean_nonpositive_loss"], -.05)
        self.assertEqual(len(result["positive_cycles_smallest_gain_first"]), 2)
        self.assertEqual(sum(m["count"] for m in result["metrics"]["symbols"].values()), 4)

    def test_candidate_is_not_reselected_and_adverse_result_is_not_pass(self) -> None:
        inputs, baseline, seeds = fixture()
        report = derive_report(inputs, baseline, seeds)
        self.assertEqual(report["candidate_locked_2021"]["seed"], 17)
        self.assertEqual(report["per_seed"]["42"]["mechanism_status"], "PASS")
        self.assertEqual(report["candidate_mechanism_status"], "FAIL")
        self.assertEqual(report["release_status"], "NO_MT_BICL_RELEASE")
        self.assertEqual(report["candidate_market_comparisons"]["base_rate"]["performance"], "WORSE_BOTH")
        self.assertFalse(report["development_allowed"])
        self.assertTrue(all(r["K"] == 0 for r in report["per_seed"]["17"]["market"]["no_prior"]["records"]))
        self.assertTrue(all(r["m"] == 0 for r in report["per_seed"]["17"]["market"]["no_target"]["records"]))

    def test_missing_seed_and_changed_checkpoint_rejected(self) -> None:
        inputs, baseline, seeds = fixture()
        del seeds["73"]
        with self.assertRaises(ValueError):
            derive_report(inputs, baseline, seeds)
        inputs, baseline, seeds = fixture()
        seeds["42"]["checkpoint"] = {"seed": 42, "step": 2000}
        with self.assertRaises(ValueError):
            derive_report(inputs, baseline, seeds)


class BaselineFitTests(unittest.TestCase):
    """Dữ liệu giá tổng hợp tự dựng; không fit baseline thật trước freeze mã đánh giá."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.bank, _, _ = setup(periods=800)
        cls.bank["frozen_scaler"] = fit_scaler(cls.bank, "2021-01-01")

    def test_final_train_scaler_and_laplace_membership(self) -> None:
        fit = fit_baselines(self.bank)
        rows = [r for r in self.bank["records"] if r["status"] == "AVAILABLE" and r["split"] == "train"]
        self.assertEqual(fit["fit_count"], len(rows))
        self.assertEqual(fit["base_rate"], (1+sum(r["outcome"]["y"] for r in rows))/(2+len(rows)))
        self.assertEqual(set(fit["fit_ids"]), {r["episode_id"] for r in rows})

    def test_future_append_does_not_change_fit(self) -> None:
        expected = fit_baselines(self.bank)
        bank = deepcopy(self.bank)
        future = deepcopy(next(r for r in bank["records"] if r["status"] == "AVAILABLE"))
        future.update(split="validation", episode_id="future")
        future["features"]["vector"] = [float("nan")]*4
        future["outcome"]["y"] = 9
        bank["records"].append(future)
        self.assertEqual(fit_baselines(bank), expected)

    def test_single_class_and_convergence_failure(self) -> None:
        bank = deepcopy(self.bank)
        for row in bank["records"]:
            if row["status"] == "AVAILABLE" and row["split"] == "train":
                row["outcome"].update(y=1, r_net=.01)
        fit = fit_baselines(bank)
        self.assertEqual(fit["logistic"]["status"], "SINGLE_CLASS_TRAIN")
        predicted = baseline_logits(fit, [[0.]*4])
        self.assertEqual(predicted["base_rate"], predicted["logistic"])
        with patch("core.mt_bicl_evaluation.LogisticRegression.fit", side_effect=ConvergenceWarning("fixture")):
            with self.assertRaises(ValueError):
                fit_baselines(self.bank)


class EvaluationJournalTests(unittest.TestCase):
    """Pause/resume và replay bắt tự rehash, mọi inference ở test đều là fixture CPU."""

    def test_resume_and_self_resealed_predictions_rejected_by_replay(self) -> None:
        inputs, baseline, seeds = fixture()
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            training = directory/"training"
            write_manifest(training/"preflight.json", {"gpu": {"fixture": True}})
            inputs["training"] = training
            with patch("core.mt_bicl_evaluation_run.gpu_identity", return_value={"fixture": True}), \
                    patch("core.mt_bicl_evaluation_run.configure", return_value=torch.device("cpu")), \
                    patch("core.mt_bicl_evaluation_run.baseline_stage", side_effect=lambda *a: deepcopy(baseline)) as base, \
                    patch("core.mt_bicl_evaluation_run.seed_stage", side_effect=lambda i, s, d: deepcopy(seeds[str(s)])):
                self.assertFalse(evaluate_run(ROOT, directory, inputs, resume=False, stop=lambda: True))
                self.assertTrue(evaluate_run(ROOT, directory, inputs, resume=True, stop=lambda: False))
                self.assertEqual(base.call_count, 1)
                verify_evaluation(ROOT, directory, inputs, replay=True)
                bad_seeds = deepcopy(seeds)
                bad_seeds["17"]["logits"]["market_full"][0] = 0.
                write_manifest(directory/"seed17.json", bad_seeds["17"])
                write_manifest(directory/"report.json", derive_report(inputs, baseline, bad_seeds))
                index = read_manifest(directory/"index.json")
                for key in ("seed17", "report"):
                    index["artifacts"][key] = file_hash(directory/(key+".json"))
                write_manifest(directory/"index.json", index)
                with self.assertRaisesRegex(ValueError, "replay khác raw logits"):
                    verify_evaluation(ROOT, directory, inputs, replay=True)

    def test_cpu_inference_frozen_without_optimizer(self) -> None:
        device = configure(0, cuda=False)
        model = MTBiCLLearner()
        row = FiniteSimulator.from_locked(ROOT).episode("synthetic_diagnostic", 0)
        a, b = pack_input(row["input"], query_y=0), pack_input(row["input"], query_y=1)
        before = model_fingerprint(model)
        with patch("torch.optim.AdamW", side_effect=AssertionError("optimizer forbidden")):
            first = predict_packets(model, [a], 128, device)
            second = predict_packets(model, [b], 128, device)
        self.assertEqual(first, second)
        self.assertEqual(before, model_fingerprint(model))
        self.assertTrue(all(p.grad is None for p in model.parameters()))


if __name__ == "__main__":
    unittest.main()
