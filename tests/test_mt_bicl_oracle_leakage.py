"""Chặn nhãn/latent/ID rò vào input và dữ liệu ngoài train trong batch optimizer."""

from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from core.mt_bicl_batches import TrainingBatchSource, load_context
from core.mt_bicl_bank import SYMBOLS, content_hash
from core.mt_bicl_context import pack_episode
from core.mt_bicl_oracle import FiniteBayesOracle
from core.mt_bicl_simulator import FiniteSimulator, pack_input, validate_input
from mt_bicl_tasks_support import builder, setup

ROOT = Path(__file__).resolve().parents[1]


class SyntheticLeakageTests(unittest.TestCase):
    """Những sidecar query/latent chỉ được dùng tạo nhãn, không làm predictor input."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.sim = FiniteSimulator.from_locked(ROOT)

    def test_duplicate_ids_rejected(self) -> None:
        data = self.sim.episode("synthetic_test", 0)["input"]
        data["target"]["observations"][0]["observation_id"] = data["query"]["observation_id"]
        with self.assertRaises(ValueError):
            validate_input(data)

    def test_label_latent_and_extra_fields_rejected(self) -> None:
        for destination, key, value in (("query", "y", 1), ("query", "outcome", {}),
                                        ("query", "lambda_index", 0), (None, "latent_provenance", {}),
                                        (None, "supervised_query_y", 1)):
            data = self.sim.episode("synthetic_test", 0)["input"]
            (data if destination is None else data[destination])[key] = value
            with self.assertRaises(ValueError):
                FiniteBayesOracle(self.sim).predict(data)

    def test_query_label_flip_changes_only_external_label(self) -> None:
        episode = self.sim.episode("synthetic_test", 0)
        data = episode["input"]
        a, b = pack_input(data, query_y=0), pack_input(data, query_y=1)
        self.assertNotEqual(a.pop("external_loss_labels"), b.pop("external_loss_labels"))
        self.assertEqual(a, b)
        before = FiniteBayesOracle(self.sim).predict(data)
        episode["supervised_query_y"] = 1-episode["supervised_query_y"]
        episode["latent_provenance"] = {}
        self.assertEqual(before, FiniteBayesOracle(self.sim).predict(data))

    def test_nonfinite_bool_numpy_and_out_of_domain_rejected(self) -> None:
        for value in (float("nan"), float("inf"), True, np.float64(.1), 4.001):
            data = self.sim.episode("synthetic_test", 0)["input"]
            data["query"]["x"][0] = value
            with self.assertRaises(ValueError):
                validate_input(data)

    def test_invalid_label_types_rejected(self) -> None:
        for y in (True, np.int64(1), 1., -1, 2):
            data = self.sim.episode("synthetic_test", 0)["input"]
            data["target"]["observations"][0]["y"] = y
            with self.assertRaises(ValueError):
                validate_input(data)


class BatchLeakageTests(unittest.TestCase):
    """Kiểm sampler bằng fixture PIT tự dựng; dữ liệu thật được kiểm riêng ở CLI."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.sim = FiniteSimulator.from_locked(ROOT)
        bank, prices, history = setup(periods=800)
        task_builder = builder(bank, prices, history)
        scalers, episodes = {}, []
        for index in (689, 719, 749):
            date = str(history["Datetime"].iloc[index].date())
            for symbol in SYMBOLS:
                row = task_builder.build(symbol, date)
                scaler = row.pop("scaler")
                key = content_hash(scaler)
                scalers[key] = scaler
                row["scaler_sha256"] = key
                row["split"] = "train"
                row["supervised_target"] = next(r["outcome"] for r in bank["records"]
                                                if r["episode_id"] == row["query"]["episode_id"])
                episodes.append(row)
        # Mẫu ngoài train/thiếu dữ liệu có mặt trong nguồn nhưng phải bị lọc trước sampling.
        for split, status in (("checkpoint_selection", "AVAILABLE"), ("validation", "AVAILABLE"), ("train", "UNAVAILABLE")):
            row = deepcopy(episodes[0])
            row.update(split=split, status=status)
            episodes.append(row)
        cls.context = {"episodes": episodes, "scalers": scalers}
        cls.source = TrainingBatchSource(cls.sim, cls.context)

    def test_only_train_source_and_counts(self) -> None:
        self.assertEqual({s: len(rows) for s, rows in self.source.groups.items()},
                         {symbol: 3 for symbol in SYMBOLS})
        for rows in self.source.groups.values():
            self.assertTrue(all(r["split"] == "train" and r["query"]["exit_date"] <= "2020-12-31" for r in rows))

    def test_tampered_context_bytes_rejected_before_loading(self) -> None:
        with patch.object(Path, "read_bytes", return_value=b"changed"):
            with self.assertRaises(ValueError):
                load_context(ROOT)

    def test_market_and_synthetic_same_packet_contract(self) -> None:
        row = deepcopy(self.source.groups["FPT"][-1])
        row["scaler"] = self.context["scalers"][row.pop("scaler_sha256")]
        def observation(item: dict) -> dict:
            return {"observation_id": item["episode_id"], "x": item["model_vector"], "y": item["y"]}
        data = {"prior": [{"task_id": task["task_id"], "observations": [observation(r) for r in task["observations"]]} for task in row["prior"]],
                "target": {"task_id": row["query"]["task_id"], "observations": [observation(r) for r in row["target"]]},
                "query": {"observation_id": row["query"]["episode_id"], "x": row["query"]["model_vector"]}}
        label = row["supervised_target"]["y"]
        self.assertEqual(pack_episode(row, training_query_y=label), pack_input(data, query_y=label))

    def test_interleave_shapes_labels_and_resume(self) -> None:
        batch = self.source.batch(0, model_seed=17)
        self.assertEqual(batch, self.source.batch(0, model_seed=17))
        self.assertEqual(len(batch), 128)
        for i, row in enumerate(batch):
            self.assertEqual(row["domain"], "market" if i % 2 else "synthetic")
            packet = row["packed"]
            self.assertEqual(len(packet["values"]), len(packet["roles"]))
            self.assertLessEqual(len(packet["values"]), 69)
            self.assertEqual(packet["values"][-1][4:], [0., 1.])
            self.assertEqual(packet["roles"][-1], 2)
            self.assertTrue(all(y in (0, 1) for y in packet["external_loss_labels"]))
            if row["domain"] == "market":
                self.assertLessEqual(row["source_id"].split("-", 1)[1], "2020-12-31")
                self.assertEqual(len(packet["external_loss_labels"]), row["m"]+1)

    def test_market_uniform_symbol_then_query_recipe(self) -> None:
        batch = self.source.batch(1, model_seed=42)
        symbols = tuple(self.source.groups)
        for i in range(64):
            rng = self.sim._rng("market_sampling", 42, 64+i)
            symbol = symbols[int(rng.integers(0, 4))]
            rows = self.source.groups[symbol]
            row = rows[int(rng.integers(0, len(rows)))]
            actual = batch[2*i+1]
            self.assertEqual(actual["symbol"], symbol)
            self.assertEqual(actual["source_id"], row["query"]["episode_id"])
            self.assertEqual(actual["K"], int(rng.integers(0, row["K"]+1)))
            self.assertEqual(actual["m"], int(rng.integers(0, row["m"]+1)))

    def test_preflight_disjoint_from_training(self) -> None:
        pre = self.source.batch(0, model_seed=0, preflight=True)
        train = self.source.batch(0, model_seed=17)
        self.assertEqual(pre[0]["stream"], "runtime_preflight")
        self.assertNotEqual(pre[0]["source_id"], train[0]["source_id"])
        for seed, flag, step in ((17, True, 0), (0, False, 0), (0, True, 100), (17, False, 10000)):
            with self.assertRaises(ValueError):
                self.source.batch(step, model_seed=seed, preflight=flag)

    def test_false_train_split_rejected(self) -> None:
        context = {"episodes": [deepcopy(rows[0]) for rows in self.source.groups.values()],
                   "scalers": self.context["scalers"]}
        context["episodes"][0]["query"]["exit_date"] = "2021-01-04"
        with self.assertRaises(ValueError):
            TrainingBatchSource(self.sim, context)

    def test_query_label_independent_market_input(self) -> None:
        # Thay mọi query label sau chọn; membership, dropout và tensor x/y context giữ nguyên.
        before = self.source.batch(0, model_seed=73)
        try:
            for rows in self.source.groups.values():
                for row in rows:
                    row["supervised_target"]["y"] = 1-row["supervised_target"]["y"]
            after = self.source.batch(0, model_seed=73)
        finally:
            for rows in self.source.groups.values():
                for row in rows:
                    row["supervised_target"]["y"] = 1-row["supervised_target"]["y"]
        for a, b in zip(before, after):
            if a["domain"] == "market":
                labels_a = a["packed"].pop("external_loss_labels")
                labels_b = b["packed"].pop("external_loss_labels")
                self.assertEqual(labels_a[:-1], labels_b[:-1])
                self.assertEqual(labels_a[-1], 1-labels_b[-1])
            self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
