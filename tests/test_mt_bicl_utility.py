"""Oracle số học độc lập cho mixture/utility và CRN trên fixture tổng hợp."""

from __future__ import annotations

from copy import deepcopy
import math
import unittest
from unittest.mock import patch

import numpy as np
from scipy.stats import beta as beta_distribution

from core.backtest_engine import compute_round_trip_net_return
from core.mt_bicl_bank import canonical_bytes, content_hash
from core.mt_bicl_student import PAIRED, pack_input
from core.mt_bicl_teacher import ALPHA, BETA, BetaBernoulliTeacher
from core.mt_bicl_context import NoActionableContext, prepare_variants, project_context, require_actionable_context
from core.mt_bicl_contracts import membership_hash, without_target
from core.mt_bicl_utility import DRAWS, common_uniforms, observations, posterior_utility
from mt_bicl_support import episode


class UtilityTests(unittest.TestCase):
    """Không gọi frozen weights/GPU; callback p giả tách riêng kiểm membership mới."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.teacher = BetaBernoulliTeacher([(i+1)/136 for i in range(16)])
        cls.full = episode()
        cls.result = posterior_utility(cls.full, cls.teacher, .6)

    def test_independent_scalar_mixture_theta_and_all_MC_draws(self) -> None:
        tasks = [task["observations"] for task in self.full["prior"]]+[self.full["target"]]
        counts = [(sum(r["y"] for r in rows), sum(1-r["y"] for r in rows)) for rows in tasks]
        logs = []
        for a, b, pi in zip(ALPHA.tolist(), BETA.tolist(), self.teacher.pi.tolist()):
            value = math.log(pi)
            for s, f in counts:
                value += math.fsum(math.log(a+i) for i in range(s))+math.fsum(math.log(b+i) for i in range(f))-math.fsum(math.log(a+b+i) for i in range(s+f))
            logs.append(value)
        unnormalized = [math.exp(value-max(logs)) for value in logs]
        mass = [value/math.fsum(unnormalized) for value in unnormalized]
        s, f = counts[-1]
        mean_theta = math.fsum(w*(a+s)/(a+b+s+f) for w, a, b in zip(mass, ALPHA, BETA))
        self.assertAlmostEqual(mean_theta, self.result["wire"]["posterior_mean_theta"], delta=1e-12)
        self.assertTrue(np.allclose(mass, self.result["audit"]["lambda_posterior"], atol=1e-12, rtol=0))
        point_id = self.full["query"]["episode_id"]
        lambda_uniform, theta_uniform = common_uniforms(point_id, "lambda"), common_uniforms(point_id, "theta")
        rows = observations(self.full)
        uniforms = {r["episode_id"]: common_uniforms(point_id, "magnitude|"+r["episode_id"]) for r in rows}
        gains, losses = [r for r in rows if r["y"]], [r for r in rows if not r["y"]]
        expected = []
        for i in range(DRAWS):
            total, latent = 0., 15
            for j, weight in enumerate(mass):
                total += weight
                if lambda_uniform[i] < total:
                    latent = j
                    break
            theta = float(beta_distribution.ppf(float(theta_uniform[i]), float(ALPHA[latent]+s), float(BETA[latent]+f)))
            magnitudes = []
            for group in (gains, losses):
                exponentials = [-math.log(float(uniforms[r["episode_id"]][i])) for r in group]
                magnitudes.append(math.fsum(e*abs(r["r_net"]) for e, r in zip(exponentials, group))/math.fsum(exponentials))
            expected.append(theta*magnitudes[0]-(1-theta)*magnitudes[1])
        self.assertTrue(np.allclose(expected, self.result["audit"]["draws"]["U"], atol=1e-12, rtol=0))
        self.assertAlmostEqual(mean_theta*.04-(1-mean_theta)*.02, self.result["wire"]["mean_U_net_fraction"], delta=1e-12)

    def test_MC_mean_quantiles_and_draw_hash_not_confused_with_analytic_mean(self) -> None:
        wire, audit = self.result["wire"], self.result["audit"]
        draws = np.array(audit["draws"]["U"])
        self.assertEqual(wire["draws_sha256"], content_hash(audit["draws"]))
        self.assertEqual(wire["MC_mean_U_net_fraction"], float(draws.mean()))
        self.assertEqual([wire["q10_U_net_fraction"], wire["q90_U_net_fraction"]], np.quantile(draws, [.1, .9], method="linear").tolist())
        self.assertAlmostEqual(audit["MC_standard_error_net_fraction"], float(draws.std(ddof=1)/math.sqrt(DRAWS)), delta=1e-15)
        self.assertEqual(audit["MC_mean_minus_analytic_net_fraction"], wire["MC_mean_U_net_fraction"]-wire["mean_U_net_fraction"])
        canonical_bytes(self.result)

    def test_full_no_target_common_streams_subset_and_recompute(self) -> None:
        alternative = posterior_utility(without_target(self.full), self.teacher, .3, branch_id="No_target")
        full, removed = self.result["audit"], alternative["audit"]
        self.assertEqual(removed["target_counts"], [0, 0])
        self.assertEqual(full["prior_counts"], removed["prior_counts"])
        self.assertNotEqual(full["lambda_posterior"], removed["lambda_posterior"])
        self.assertNotEqual(full["draws"]["U"], removed["draws"]["U"])
        for component, seed in removed["component_seeds"].items():
            self.assertEqual(full["component_seeds"][component], seed)
        self.assertTrue(all(0 < value < 1 for value in common_uniforms(self.full["query"]["episode_id"], "theta")))

    def test_zero_net_is_retained_once_in_loss_and_no_double_cost(self) -> None:
        value = episode()
        rows = [r for task in value["prior"] for r in task["observations"]]+value["target"]
        gains = losses = 0
        for i, row in enumerate(rows):
            net = float(compute_round_trip_net_return(100., 104. if i % 2 else 100.))
            if i == 0: net = 0.
            row.update(r_net=net, y=int(net > 0))
            gains += net > 0
            losses += net <= 0
        value["membership_sha256"] = membership_hash(value)
        result = posterior_utility(value, self.teacher, .6)
        self.assertEqual((result["wire"]["gain_count"], result["wire"]["loss_count"]), (gains, losses))
        self.assertEqual(len(set(result["audit"]["unique_observation_ids"])), len(rows))
        p = result["wire"]["posterior_mean_theta"]
        expected = p*math.fsum(r["r_net"] for r in rows if r["y"])/gains-(1-p)*math.fsum(-r["r_net"] for r in rows if not r["y"])/losses
        self.assertAlmostEqual(expected, result["wire"]["mean_U_net_fraction"], delta=1e-12)

    def test_support_boundaries_no_sampler_on_unsupported(self) -> None:
        for K, gain_count, supported in ((1, 8, False), (2, 4, False), (2, 12, False), (2, 5, True), (2, 11, True)):
            value = without_target(self.full)
            value["prior"] = value["prior"][:K]
            value["K"] = K
            keep = {identifier for task in value["prior"] for identifier in task["centroid_fit_ids"]}
            value["advisor"]["historical_facts"] = {k: v for k, v in value["advisor"]["historical_facts"].items() if k in keep}
            for i, row in enumerate(r for task in value["prior"] for r in task["observations"]):
                row.update(y=int(i < gain_count), r_net=.04 if i < gain_count else -.02)
            value["membership_sha256"] = membership_hash(value)
            if supported:
                result = posterior_utility(value, self.teacher, .6)
                self.assertEqual(result["wire"]["status"], "SUPPORTED")
            else:
                with patch("core.mt_bicl_utility.common_uniforms", side_effect=AssertionError("Không được sample")):
                    result = posterior_utility(value, self.teacher, .6)
                self.assertEqual((result["wire"]["draws"], result["wire"]["draws_sha256"], result["audit"]["draws"]), (0, None, None))

    def test_nonfinite_numpy_missing_student_or_query_label_rejected(self) -> None:
        for p in (float("nan"), float("inf"), True, np.float64(.5), -.1, 1.1, None):
            with self.subTest(p=p), self.assertRaises(ValueError):
                posterior_utility(self.full, self.teacher, p)
        value = episode()
        value["query"]["y"] = 1
        with self.assertRaises(ValueError): posterior_utility(value, self.teacher, .6)

    def test_variants_recompute_two_p_and_full_mask_without_U_leakage(self) -> None:
        calls = []
        def probability(value: dict) -> float:
            """P thay đổi theo C để phát hiện reuse sai."""
            calls.append(deepcopy(value))
            return .6 if value["m"] else .3
        result = prepare_variants(self.full, self.teacher, probability)
        branches = result["branches"]
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["prior"], calls[1]["prior"])
        self.assertEqual(branches["No_target"]["probability"], .3)
        for name in ("Plain_revision", "No_utility"):
            self.assertEqual(branches[name]["eligible"], branches["MT_BICL"]["eligible"])
            self.assertIsNone(branches[name]["utility"])
            self.assertNotIn("U(mean", branches[name]["projection"]["prefix"])
        self.assertIsNone(branches["Plain_revision"]["probability"])
        self.assertNotIn("p=", branches["Plain_revision"]["projection"]["prefix"])
        self.assertEqual(branches["Stats_only"]["utility"]["draws_sha256"], branches["MT_BICL"]["utility"]["draws_sha256"])
        self.assertNotIn("exemplars", branches["Stats_only"]["projection"])
        self.assertEqual(branches["Stats_only"]["projection"]["summary"], branches["MT_BICL"]["projection"]["summary"])
        self.assertNotIn("\nT ", branches["No_target"]["projection"]["prefix"])

    def test_projection_all_counts_exemplar_label_blind_and_600_guard(self) -> None:
        projection = project_context(self.full, branch_id="MT_BICL", probability=.6, utility=self.result["wire"])
        self.assertLessEqual(len(projection["prefix"]), 600)
        self.assertEqual(sum(s["n"] for s in projection["summary"]), len(observations(self.full)))
        self.assertEqual(len(projection["exemplars"]), self.full["K"]+1)
        value = episode()
        for row in [r for task in value["prior"] for r in task["observations"]]+value["target"]:
            row.update(y=1-row["y"], r_net=-row["r_net"])
        value["membership_sha256"] = membership_hash(value)
        changed = project_context(value, branch_id="Plain_revision", probability=None, utility=None)
        self.assertEqual([e["episode_id"] for e in projection["exemplars"]], [e["episode_id"] for e in changed["exemplars"]])
        with patch("core.mt_bicl_context.LEGEND", "x"*601), self.assertRaises(ValueError):
            project_context(self.full, branch_id="Plain_revision", probability=None, utility=None)

    def test_missing_or_unknown_does_not_forward_and_keeps_every_branch(self) -> None:
        value = without_target(self.full)
        value.update(status="UNAVAILABLE", K=0, prior=[], m=0, target=[])
        value["advisor"]["historical_facts"] = {}
        value["membership_sha256"] = membership_hash(value)
        with patch("builtins.input", side_effect=AssertionError("Không hỏi runtime")):
            result = prepare_variants(value, self.teacher, lambda _: self.fail("Không forward missing"))
        self.assertEqual(len(result["branches"]), 6)
        self.assertTrue(all(not b["eligible"] and b["projection"] is None for b in result["branches"].values()))

    def test_global_no_actionable_blocks_before_API_including_zero_boundary(self) -> None:
        value = prepare_variants(self.full, self.teacher, lambda _: .6)
        for q10, q90 in ((-.01, .01), (0., 0.)):
            value["branches"]["MT_BICL"]["utility"].update(q10_U_net_fraction=q10, q90_U_net_fraction=q90)
            with self.assertRaises(NoActionableContext): require_actionable_context([value])
        value["branches"]["MT_BICL"]["utility"].update(q10_U_net_fraction=1e-15, q90_U_net_fraction=.01)
        self.assertEqual(require_actionable_context([value])["positive_interval"], 1)
        with self.assertRaises(ValueError): require_actionable_context([value, value])

    def test_packing_still_four_dimensions_and_37_tokens_no_query_label(self) -> None:
        from core.mt_bicl_evaluation import market_input
        value = deepcopy(self.full)
        checksum = content_hash(value.pop("scaler"))
        value["scaler_sha256"] = checksum
        data = market_input(value, {"scalers": {checksum: self.full["scaler"]}})
        packed = pack_input(data)
        self.assertEqual(packed["packing"], PAIRED)
        self.assertLessEqual(len(packed["values"]), 37)
        self.assertEqual(packed["values"][-1][4:], [0., 1.])
        self.assertEqual(set(data["query"]), {"observation_id", "x"})


if __name__ == "__main__":
    unittest.main()
