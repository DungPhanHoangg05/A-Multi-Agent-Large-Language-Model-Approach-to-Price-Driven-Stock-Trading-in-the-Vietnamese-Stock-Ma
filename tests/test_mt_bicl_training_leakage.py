"""Kiểm causal mask/loss, query label và split selection trên learner thật."""

from copy import deepcopy
import os
from pathlib import Path
import unittest

import torch
from torch.nn import functional as F

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

from core.mt_bicl_model import MTBiCLLearner, collate_packets, episode_losses
from core.mt_bicl_simulator import FiniteSimulator, pack_input
from core.mt_bicl_training import (configure, evaluate_selection, make_optimizer, optimizer_step,
                                   selection_key, selection_rows)

ROOT = Path(__file__).resolve().parents[1]


def packets(count: int = 4) -> list[dict]:
    """Diagnostic stream chỉ dùng unit test, không vào training production."""
    simulator = FiniteSimulator.from_locked(ROOT)
    return [pack_input(row["input"], query_y=row["supervised_query_y"])
            for row in (simulator.episode("synthetic_diagnostic", i) for i in range(count))]


class ModelLeakageTests(unittest.TestCase):
    """Đo tác động lên logit/gradient, không chỉ kiểm tên mask trong schema."""

    def setUp(self) -> None:
        self.device = configure(17, cuda=False)
        self.model = MTBiCLLearner().eval()
        self.packets = packets()

    def forward(self, batch: dict) -> torch.Tensor:
        """Không đưa nhãn loss hoặc sidecar vào forward."""
        with torch.inference_mode():
            return self.model(batch["values"], batch["roles"], batch["padding"])

    def test_architecture_and_fp32(self) -> None:
        self.assertEqual(sum(p.numel() for p in self.model.parameters()), 275201)
        self.assertEqual(len(self.model.decoder.layers), 2)
        self.assertTrue(all(p.dtype == torch.float32 for p in self.model.parameters()))
        self.assertEqual(int(self.model.causal_mask.sum()), 69*68//2)

    def test_future_y_and_x_cannot_change_earlier_prediction(self) -> None:
        packet = next(p for p in self.packets if len(p["prediction_positions"]) > 1)
        batch = collate_packets([packet], self.device)
        position = packet["prediction_positions"][0]
        expected = self.forward(batch)[0, position].clone()
        batch["values"][0, position+1:, :] = torch.randn_like(batch["values"][0, position+1:, :])*4
        actual = self.forward(batch)[0, position]
        self.assertEqual(float(actual), float(expected))

    def test_query_label_flip_does_not_change_logits(self) -> None:
        a = collate_packets(self.packets, self.device)
        changed = deepcopy(self.packets)
        for packet in changed:
            packet["external_loss_labels"][-1] = 1-packet["external_loss_labels"][-1]
        b = collate_packets(changed, self.device)
        self.assertTrue(torch.equal(a["values"], b["values"]))
        self.assertFalse(torch.equal(a["labels"], b["labels"]))
        self.assertTrue(torch.equal(self.forward(a), self.forward(b)))

    def test_padding_mask_and_mixed_length_batch(self) -> None:
        batch = collate_packets(self.packets, self.device)
        expected = self.forward(batch)
        for i, packet in enumerate(self.packets):
            length = len(packet["values"])
            self.assertFalse(bool(batch["padding"][i, :length].any()))
            self.assertTrue(bool(batch["padding"][i, length:].all()))
            alone = self.forward(collate_packets([packet], self.device))[0, packet["query_position"]]
            self.assertAlmostEqual(float(expected[i, packet["query_position"]]), float(alone), delta=1e-6)
        batch["values"][batch["padding"]] = 10000.
        actual = self.forward(batch)
        for i, packet in enumerate(self.packets):
            self.assertEqual(float(expected[i, packet["query_position"]]), float(actual[i, packet["query_position"]]))

    def test_gradient_only_at_target_x_and_query(self) -> None:
        batch = collate_packets(self.packets, self.device)
        logits = torch.randn(4, 69, requires_grad=True)
        losses = episode_losses(logits, batch)
        for i, packet in enumerate(self.packets):
            positions = packet["prediction_positions"]
            expected = F.binary_cross_entropy_with_logits(logits[i, positions], batch["labels"][i, positions])
            self.assertAlmostEqual(float(losses[i].detach()), float(expected.detach()), delta=1e-7)
        losses.mean().backward()
        self.assertEqual(int(torch.count_nonzero(logits.grad[~batch["loss_mask"]])), 0)
        self.assertTrue(bool((logits.grad[batch["loss_mask"]] != 0).all()))

    def test_missing_all_loss_labels_rejected(self) -> None:
        packet = deepcopy(self.packets[0])
        packet["external_loss_labels"] = [None]*len(packet["prediction_positions"])
        batch = collate_packets([packet], self.device)
        with self.assertRaises(ValueError):
            episode_losses(torch.zeros(1, 69), batch)

    def test_injected_label_prior_loss_and_bad_masks_rejected(self) -> None:
        for key in ("query_label", "loss_prior", "mask", "nonfinite"):
            packet = deepcopy(self.packets[0])
            if key == "query_label":
                packet["values"][-1][4] = 1.
            elif key == "loss_prior":
                packet["prediction_positions"].insert(0, 0)
                packet["external_loss_labels"].insert(0, 1)
            elif key == "mask":
                packet["causal_mask"] = "BIDIRECTIONAL"
            else:
                packet["values"][0][0] = float("nan")
            with self.assertRaises(ValueError):
                collate_packets([packet], self.device)

    def test_accumulation_preserves_episode_mean_gradients(self) -> None:
        a, b = MTBiCLLearner(), MTBiCLLearner()
        b.load_state_dict(a.state_dict())
        # Tắt dropout chỉ trong phép đối chiếu số học accumulation, không đổi cấu hình production.
        for model in (a, b):
            for module in model.modules():
                if isinstance(module, torch.nn.Dropout):
                    module.p = 0.
                elif isinstance(module, torch.nn.MultiheadAttention):
                    module.dropout = 0.
        optimizer_a, optimizer_b = make_optimizer(a), make_optimizer(b)
        from unittest.mock import patch
        with patch.object(optimizer_a, "step"), patch.object(optimizer_b, "step"):
            loss_a = optimizer_step(a, optimizer_a, self.packets, 4, self.device)
            loss_b = optimizer_step(b, optimizer_b, self.packets, 2, self.device)
        self.assertAlmostEqual(loss_a, loss_b, delta=1e-6)
        for left, right in zip(a.parameters(), b.parameters()):
            torch.testing.assert_close(left.grad, right.grad, atol=1e-6, rtol=1e-5)

    def test_selection_eval_no_weights_or_rng_update(self) -> None:
        rows = [{"packed": p, "query": {"episode_id": f"{s}-{i}", "symbol": s},
                 "supervised_target": {"y": p["external_loss_labels"][-1]}}
                for i, (s, p) in enumerate(zip(("FPT", "MWG", "VCB", "VNM"), self.packets))]
        weights = deepcopy(self.model.state_dict())
        rng = torch.get_rng_state().clone()
        result = evaluate_selection(self.model, rows, 2, self.device)
        self.assertEqual(len(result["records"]), 4)
        self.assertTrue(torch.equal(rng, torch.get_rng_state()))
        self.assertTrue(all(torch.equal(v, self.model.state_dict()[k]) for k, v in weights.items()))
        self.assertTrue(all(p.grad is None for p in self.model.parameters()))
        self.assertFalse(self.model.training)

    def test_selection_split_guard(self) -> None:
        rows = [{"split": "checkpoint_selection", "status": "AVAILABLE",
                 "query": {"symbol": s, "as_of_date": "2021-01-04", "exit_date": "2021-01-07"}}
                for s in ("FPT", "MWG", "VCB", "VNM") for _ in range(40)]
        self.assertEqual(len(selection_rows({"episodes": rows})), 160)
        rows[0]["query"]["exit_date"] = "2022-01-01"
        with self.assertRaises(ValueError):
            selection_rows({"episodes": rows})

    def test_selection_key_fixed_ties(self) -> None:
        def row(seed: int, step: int, loss: float = .5, brier: float = .2) -> dict:
            return {"seed": seed, "step": step, "metrics": {"macro_log_loss": loss, "macro_brier": brier}}
        values = [row(73, 1000), row(17, 2000), row(42, 1000), row(17, 1000)]
        self.assertEqual(min(values, key=selection_key), row(17, 1000))
        self.assertLess(selection_key(row(73, 10000, .4)), selection_key(row(17, 1000)))
        self.assertLess(selection_key(row(73, 10000, brier=.1)), selection_key(row(17, 1000)))


if __name__ == "__main__":
    unittest.main()
