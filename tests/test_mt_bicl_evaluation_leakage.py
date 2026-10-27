"""Kiểm PIT và query label ở đường chuyển market context sang input đánh giá."""

from copy import deepcopy
import unittest

from core.mt_bicl_bank import content_hash
from core.mt_bicl_evaluation import baseline_logits, fit_baselines, market_input
from core.mt_bicl_scaler import fit_scaler
from core.mt_bicl_simulator import pack_input
from mt_bicl_tasks_support import builder, setup


class EvaluationLeakageTests(unittest.TestCase):
    """Fixture tự dựng, không đọc nhãn 2022 hoặc corpus mechanism test thật."""

    @classmethod
    def setUpClass(cls) -> None:
        bank, sources, history = setup(periods=800)
        bank["frozen_scaler"] = fit_scaler(bank, "2021-01-01")
        row = builder(bank, sources, history).build("FPT", str(history["Datetime"].iloc[749].date()))
        scaler = row.pop("scaler")
        key = content_hash(scaler)
        row["scaler_sha256"] = key
        row["supervised_target"] = {"y": 1, "r_net": .01}
        cls.row, cls.context, cls.bank = row, {"scalers": {key: scaler}}, bank

    def test_query_sidecar_flip_has_identical_input(self) -> None:
        before = market_input(self.row, self.context)
        row = deepcopy(self.row)
        row["supervised_target"] = {"y": 0, "r_net": -999.}
        self.assertEqual(before, market_input(row, self.context))
        self.assertIsNone(pack_input(before)["external_loss_labels"][-1])

    def test_future_member_and_duplicate_id_rejected(self) -> None:
        for case in ("future", "duplicate"):
            row = deepcopy(self.row)
            item = row["prior"][0]["observations"][0]
            if case == "future":
                item["exit_date"] = row["query"]["as_of_date"]
            else:
                item["episode_id"] = row["query"]["episode_id"]
            with self.assertRaises(ValueError):
                market_input(row, self.context)

    def test_no_prior_no_target_preserve_query_and_other_task(self) -> None:
        full = market_input(self.row, self.context)
        no_prior = market_input(self.row, self.context, "no_prior")
        no_target = market_input(self.row, self.context, "no_target")
        self.assertEqual(no_prior["query"], full["query"])
        self.assertEqual(no_target["query"], full["query"])
        self.assertEqual(no_prior["target"], full["target"])
        self.assertEqual(no_target["prior"], full["prior"])
        self.assertEqual(no_prior["prior"], [])
        self.assertEqual(no_target["target"]["observations"], [])

    def test_baseline_prediction_has_no_validation_labels_or_refit(self) -> None:
        fit = fit_baselines(self.bank)
        before = deepcopy(fit)
        x = [self.row["query"]["model_vector"]]
        a = baseline_logits(fit, x)
        changed = deepcopy(self.row)
        changed["supervised_target"] = {"y": 0, "r_net": -1.}
        self.assertEqual(a, baseline_logits(fit, [changed["query"]["model_vector"]]))
        self.assertEqual(fit, before)


if __name__ == "__main__":
    unittest.main()
