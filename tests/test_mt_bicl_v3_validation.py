"""Kiểm oracle/report/checkpoint contract trên fixture, không đọc weights hoặc payoff thật."""

from __future__ import annotations

from copy import deepcopy
import unittest

from core.mt_bicl_bank import canonical_bytes
from core.mt_bicl_v2_teacher import BetaBernoulliTeacher
from core.mt_bicl_v3_context import prepare_variants
from core.mt_bicl_v3_oracle import check_posterior
from core.mt_bicl_v3_utility import posterior_utility
from core.mt_bicl_v3_validation import _drop_prior, approximation, check_projection, derive_report
from core.mt_bicl_v3_validation_inputs import validate_checks
from mt_bicl_v3_support import episode


class ValidationTests(unittest.TestCase):
    """Oracle scalar không gọi sampler production, gate không đổi theo outcome."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.episode = episode()
        cls.teacher = BetaBernoulliTeacher([(i+1)/136 for i in range(16)])
        cls.prepared = prepare_variants(cls.episode, cls.teacher, lambda value: .6 if value["m"] else .3)

    def test_oracle_all4096_draws_and_nonuniform_pi_match(self) -> None:
        value = posterior_utility(self.episode, self.teacher, .6)
        proof = check_posterior(self.episode, value, self.teacher.pi.tolist())
        self.assertEqual(proof["draws_checked"], 4096)
        self.assertLessEqual(proof["max_error"], 1e-12)
        value["audit"]["draws"]["U"][123] += .0001
        with self.assertRaises(ValueError): check_posterior(self.episode, value, self.teacher.pi.tolist())

    def test_projection_counts_exemplar_stats_and_No_target_must_match(self) -> None:
        check_projection(self.prepared)
        for mode in ("count", "example", "stats", "mask", "target"):
            value = deepcopy(self.prepared)
            if mode == "count": value["branches"]["Full_utility_ICL"]["projection"]["summary"][0]["wins"] += 1
            if mode == "example": value["branches"]["Full_utility_ICL"]["projection"]["exemplars"][0]["episode_id"] = "hidden"
            if mode == "stats": value["branches"]["Stats_only"]["utility"]["mean_U_net_fraction"] += .01
            if mode == "mask": value["branches"]["No_utility"]["eligible"] = False
            if mode == "target": value["contexts"]["No_target"]["m"] = 1
            with self.subTest(mode=mode), self.assertRaises(ValueError): check_projection(value)

    def test_approximation_union_not_mean_of_group_means(self) -> None:
        rows = [{"p": .5, "q": .5}]*9+[{"p": .1, "q": .9}]
        value = approximation(rows)
        self.assertEqual(value["available_contexts"], 10)
        self.assertEqual(value["status"], "FAIL_APPROXIMATION_NO_TEACHER_FALLBACK")
        self.assertAlmostEqual(value["mean_absolute_error"], .08)
        self.assertEqual(approximation([{"p": .5, "q": .5}])["status"], "PASS")

    def test_infinite_KL_is_explicit_failure_not_JSON_infinity_or_clipping(self) -> None:
        value = approximation([{"p": 0., "q": .5}, {"p": None, "q": None}])
        self.assertIsNone(value["mean_KL_nats"])
        self.assertEqual((value["infinite_KL_contexts"], value["unavailable_contexts"]), (1, 1))
        self.assertNotEqual(value["status"], "PASS")
        canonical_bytes(value)
        for p in (float("nan"), float("inf"), True):
            with self.assertRaises(ValueError): approximation([{"p": p, "q": .5}])

    def test_leave_one_task_out_keeps_query_target_and_no_refill(self) -> None:
        changed = _drop_prior(self.episode, 1)
        self.assertEqual(changed["prior"], [self.episode["prior"][0], self.episode["prior"][2]])
        self.assertEqual(changed["target"], self.episode["target"])
        self.assertEqual(changed["query"], self.episode["query"])
        value = posterior_utility(changed, self.teacher, .6)
        self.assertEqual(check_posterior(changed, value, self.teacher.pi.tolist())["status"], "PASS")

    def test_failed_approx_and_no_actionable_are_both_retained_without_release(self) -> None:
        pid = self.episode["query"]["episode_id"]
        variants = deepcopy(self.prepared["branches"])
        for name in ("Full_utility_ICL", "No_target"):
            variants[name]["utility"].update(q10_U_net_fraction=0., q90_U_net_fraction=0.)
        point = {"point_id": pid, "stage": "development2023", "symbol": "FPT", "regime": "BULL", "bucket": "MACD_POS_PRICE_POS",
                 "variants": variants, "oracles": {"Full": {"max_error": 0., "draws_checked": 4096}},
                 "approximation": [{"p": .1, "q": .9, "stage": "development2023", "branch_id": name} for name in ("Full_utility_ICL", "No_target")]}
        identity = {"cohort": [{"point_id": pid}]}
        report = derive_report(identity, [point])
        self.assertEqual(report["failed_gates"], ["FAIL_APPROXIMATION_NO_TEACHER_FALLBACK", "NO_ACTIONABLE_CONTEXT"])
        self.assertFalse(report["decision_calls_allowed"])
        self.assertFalse(report["teacher_point_fallback"])
        self.assertEqual(report["point_ids"], [pid])
        with self.assertRaises(ValueError): derive_report(identity, [])

    def test_receipt_missing_group_stale_source_or_missing_test_is_rejected(self) -> None:
        value = {"status": "PASS", "source_sha256": {"code": "0"*64}, "tests_run": 1, "failures": [], "errors": [],
                 "successful_test_ids": ["test.unit"], "semantic_groups": {"group": {"status": "PASS", "test_ids": ["test.unit"]}}}
        validate_checks(value, {"code": "0"*64}, ["group"])
        for mode in ("source", "group", "test", "failure"):
            changed = deepcopy(value)
            if mode == "source": changed["source_sha256"]["code"] = "1"*64
            if mode == "group": changed["semantic_groups"] = {}
            if mode == "test": changed["semantic_groups"]["group"]["test_ids"] = ["missing"]
            if mode == "failure": changed["failures"] = ["test.unit"]
            with self.subTest(mode=mode), self.assertRaises(ValueError): validate_checks(changed, {"code": "0"*64}, ["group"])


if __name__ == "__main__":
    unittest.main()
