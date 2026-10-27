"""Kiểm oracle độc lập, joint, ranh giới task và packing synthetic đã khóa."""

from copy import deepcopy
import itertools
import json
import math
from pathlib import Path
import unittest

import numpy as np

from core.mt_bicl_oracle import FiniteBayesOracle
from core.mt_bicl_oracle_reference import EnumerationOracle
from core.mt_bicl_simulator import FiniteSimulator, pack_input, pair_inputs
from scripts.prepare_mt_bicl_oracle import pooling_control

ROOT = Path(__file__).resolve().parents[1]


class OracleTests(unittest.TestCase):
    """Đối chiếu toàn latent cho K=1 và factorization scalar riêng cho K tới ba."""

    @classmethod
    def setUpClass(cls) -> None:
        """Chỉ đọc coefficients/fixture đã khóa, không fit hoặc gọi model."""
        cls.sim = FiniteSimulator.from_locked(ROOT)
        cls.oracle = FiniteBayesOracle(cls.sim)
        cls.reference = EnumerationOracle(cls.sim.config)
        cls.fixtures = json.loads((ROOT/"docs/plan/week10/protocol_fixtures_v1.json").read_bytes())

    def control(self) -> dict:
        """Mỗi test nhận input mới, tránh sửa fixture chung."""
        return pooling_control(self.fixtures["pooling_control"])

    def test_locked_pooling_control(self) -> None:
        data = self.control()
        for pooled, key in ((False, "expected_hierarchical_p"), (True, "expected_pooled_p")):
            for oracle in (self.oracle, self.reference):
                self.assertAlmostEqual(oracle.predict(data, pooled=pooled)["probability"],
                                       self.fixtures["pooling_control"][key], delta=1e-12)

    def test_independent_random_and_extreme_posteriors(self) -> None:
        for index in range(32):
            data = self.sim.episode("synthetic_diagnostic", index)["input"]
            if index == 0:
                data["query"]["x"] = [4., -4., 4., -4.]
            for pooled in (False, True):
                actual = self.oracle.predict(data, pooled=pooled, posterior=True)
                reference = self.reference.predict(data, pooled=pooled, posterior=True)
                for key in ("probability", "log_probability_one", "log_probability_zero"):
                    self.assertAlmostEqual(actual[key], reference[key], delta=1e-12)
                np.testing.assert_allclose(actual["target_weight_posterior"], reference["target_weight_posterior"], atol=1e-12, rtol=0)
                self.assertLess(actual["normalization_error"], 1e-12)
                self.assertAlmostEqual(math.exp(actual["log_probability_one"])+math.exp(actual["log_probability_zero"]), 1., delta=1e-12)
                if not pooled:
                    np.testing.assert_allclose(actual["lambda_posterior"], reference["lambda_posterior"], atol=1e-12, rtol=0)

    def test_full_cartesian_single_prior(self) -> None:
        data = self.control()
        data["prior"] = data["prior"][:1]
        # Duyệt đủ 16*64*64 assignments; không dùng marginal likelihood của hai oracle.
        config = self.sim.config
        conditional = []
        for center in config["lambda_centers"]:
            values = [math.exp(-sum((a-b)**2 for a, b in zip(w, center))/(2*.75**2)) for w in config["w_support"]]
            conditional.append([v/math.fsum(values) for v in values])
        p = [1/(1+math.exp(-sum(a*b for a, b in zip(w, [1., *data["query"]["x"]])))) for w in config["w_support"]]
        masses, numerators = [], []
        for latent, prior_w, target_w in itertools.product(range(16), range(64), range(64)):
            mass = config["p_lambda"][latent]*conditional[latent][prior_w]*conditional[latent][target_w]*p[prior_w]**6*p[target_w]**3
            masses.append(mass)
            numerators.append(mass*p[target_w])
        self.assertAlmostEqual(self.oracle.predict(data)["probability"], math.fsum(numerators)/math.fsum(masses), delta=1e-12)

    def test_zero_prior_zero_context_is_marginal(self) -> None:
        data = self.control()
        data["prior"], data["target"]["observations"] = [], []
        result = self.oracle.predict(data, posterior=True)
        expected = sum(self.sim.p_lambda@self.sim.conditional * (1/(1+np.exp(-(self.sim.support@np.array([1, 1, 0, 0, 0]))))))
        self.assertAlmostEqual(result["probability"], float(expected), delta=1e-12)
        np.testing.assert_allclose(result["lambda_posterior"], self.sim.p_lambda, atol=1e-12, rtol=0)

    def test_context_updates_lambda(self) -> None:
        data = self.control()
        data["prior"] = []
        posterior = self.oracle.predict(data, posterior=True)["lambda_posterior"]
        self.assertGreater(max(abs(np.array(posterior)-self.sim.p_lambda)), .01)

    def test_prior_and_observation_permutations(self) -> None:
        data = self.control()
        expected = self.oracle.predict(data)["probability"]
        data["prior"].reverse()
        for task in [*data["prior"], data["target"]]:
            task["observations"].reverse()
        self.assertAlmostEqual(self.oracle.predict(data)["probability"], expected, delta=1e-12)

    def test_regrouping_changes_hierarchical_but_not_pooling(self) -> None:
        data = self.control()
        changed = deepcopy(data)
        a, b = changed["prior"]
        a["observations"][3:], b["observations"][3:] = b["observations"][3:], a["observations"][3:]
        self.assertGreater(abs(self.oracle.predict(data)["probability"]-self.oracle.predict(changed)["probability"]), 1e-3)
        self.assertAlmostEqual(self.oracle.predict(data, pooled=True)["probability"], self.oracle.predict(changed, pooled=True)["probability"], delta=1e-12)

    def test_equal_values_retain_likelihood_factors(self) -> None:
        data = self.control()
        before = self.oracle.predict(data)["probability"]
        data["target"]["observations"].pop()
        self.assertGreater(abs(before-self.oracle.predict(data)["probability"]), 1e-3)

    def test_token_fixture(self) -> None:
        f = self.fixtures["token_example"]
        def task(name: str, rows: list) -> dict:
            return {"task_id": name, "observations": [{"observation_id": f"{name}:{i}", **row} for i, row in enumerate(rows)]}
        data = {"prior": [task("P", f["prior"])], "target": task("T", f["target_context"]),
                "query": {"observation_id": "Q", "x": f["query_x"]}}
        packet = pack_input(data, query_y=1)
        self.assertEqual(packet["values"], [row["values"] for row in f["tokens"]])
        self.assertEqual(packet["roles"], [0]*5+[1]*3+[2])
        self.assertEqual(packet["prediction_positions"], f["loss_positions"])
        self.assertEqual(packet["external_loss_labels"], f["external_loss_labels"])

    def test_rng_golden_random_access_and_stream_separation(self) -> None:
        episode = self.sim.episode("synthetic_test", 0)
        self.assertEqual(episode["latent_provenance"], {"lambda_index": 15, "w_indices": [63]})
        self.assertAlmostEqual(self.oracle.predict(episode["input"])["probability"], .40054337656657363, delta=1e-12)
        self.sim.episode("synthetic_train", 1234, model_seed=17)
        self.assertEqual(episode, self.sim.episode("synthetic_test", 0))
        ids = {self.sim.episode(stream, 0, model_seed=seed)["episode_id"] for stream, seed in (
            ("synthetic_train", 17), ("synthetic_train", 42), ("synthetic_train", 73),
            ("synthetic_test", 0), ("synthetic_diagnostic", 0), ("runtime_preflight", 0))}
        self.assertEqual(len(ids), 6)

    def test_pair_fixed_target_and_random_access(self) -> None:
        pair = self.sim.prior_swap_pair(3)
        a, b = pair_inputs(pair)
        self.assertEqual(a["target"], b["target"])
        self.assertEqual(a["query"], b["query"])
        self.assertNotEqual(a["prior"], b["prior"])
        self.assertEqual(pair, self.sim.prior_swap_pair(3))
        a["query"]["x"][0] = 4.
        self.assertNotEqual(a["query"], b["query"])

    def test_generation_domains_and_native_json(self) -> None:
        episodes = [self.sim.episode("synthetic_diagnostic", i) for i in range(128)]
        self.assertEqual({len(e["input"]["prior"]) for e in episodes}, set(range(4)))
        self.assertEqual({len(e["input"]["target"]["observations"]) for e in episodes}, set(range(9)))
        for e in episodes:
            json.dumps(e, allow_nan=False)
            self.assertLessEqual(len(pack_input(e["input"])["values"]), 69)

    def test_no_global_rng_mutation(self) -> None:
        before = np.random.get_state()
        self.sim.episode("synthetic_diagnostic", 0)
        after = np.random.get_state()
        self.assertEqual(before[0], after[0])
        np.testing.assert_array_equal(before[1], after[1])
        self.assertEqual(before[2:], after[2:])

    def test_maximum_context_has_69_tokens(self) -> None:
        data = self.control()
        template = deepcopy(data["prior"][0]["observations"][0])
        data["prior"] = [{"task_id": f"P{k}", "observations": [
            {**template, "observation_id": f"P{k}:{i}"} for i in range(8)]} for k in range(3)]
        data["target"]["observations"] = [{**template, "observation_id": f"T:{i}"} for i in range(8)]
        packet = pack_input(data, query_y=0)
        self.assertEqual(len(packet["values"]), 69)
        self.assertEqual(packet["prediction_positions"], list(range(52, 69, 2)))

    def test_invalid_stream_seed_id_rejected(self) -> None:
        for stream, index, seed in (("synthetic_test", 0, 17), ("synthetic_train", 0, 0),
                                    ("market_sampling", 0, 0), ("synthetic_test", -1, 0),
                                    ("synthetic_test", True, 0)):
            with self.assertRaises(ValueError):
                self.sim.episode(stream, index, model_seed=seed)


if __name__ == "__main__":
    unittest.main()
