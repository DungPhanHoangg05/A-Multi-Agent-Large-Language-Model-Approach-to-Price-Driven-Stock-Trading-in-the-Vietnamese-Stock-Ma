"""Kiểm packing/loss/architecture và khả năng học context trên fixture nhỏ CPU."""

from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import unittest

import torch
from torch.nn import functional as F

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

from core.mt_bicl_bank import canonical_bytes
from core.mt_bicl_training import configure
from core.mt_bicl_v2_distillation import evaluate, make_optimizer, metric_report, optimizer_step, scheduled_lr, tensor_hash
from core.mt_bicl_v2_preparation import fixture_input
from core.mt_bicl_v2_student import CASES, LEGACY, PAIRED, DistilledStudent, _encode, collate_packets, pack_input, query_losses
from core.mt_bicl_v2_teacher import BetaBernoulliTeacher

ROOT = Path(__file__).resolve().parents[1]


def sample_packets(packing: str = PAIRED) -> list[dict]:
    """Bốn context giả, cùng query x; q từ posterior chứ không từ latent/query label."""
    teacher = BetaBernoulliTeacher([1/16]*16)
    inputs = [fixture_input(prior, target) for prior,target in (
        ([[8,0]],[0,0]), ([[0,8]],[0,0]), ([[4,4]],[2,0]), ([[4,4]],[0,2]))]
    return [pack_input(data,packing=packing,teacher_q=teacher.predict(data)["probability"]) for data in inputs]


class StudentTests(unittest.TestCase):
    """Mọi update là fixture CPU; không chạy pilot32 thật hoặc mở held-out student."""

    def setUp(self) -> None:
        """Ghim deterministic/FP32, không khởi tạo CUDA."""
        self.device = configure(17,cuda=False)

    def test_paired_token_fixture_and_production_minimum_support(self) -> None:
        f=json.loads((ROOT/"docs/plan/week10/protocol_fixtures_v2.json").read_bytes())["paired_packet"]
        data={"prior":[{"task_id":"P","observations":[{"observation_id":"P:0","x":[1,0,0,0],"y":1}]}],
              "target":{"task_id":"T","observations":[{"observation_id":"T:0","x":[0,1,0,0],"y":0}]},
              "query":{"observation_id":"Q","x":[0,0,1,1]}}
        packet=_encode(data,PAIRED,None)
        for key in ("values","roles","task_slots","query_position","loss_positions"):
            self.assertEqual(packet[key],f[key])
        with self.assertRaises(ValueError):pack_input(data)
        maximum=fixture_input([[4,4]]*3,[4,4])
        for packing,size in ((PAIRED,37),(LEGACY,69)):
            p=pack_input(maximum,packing=packing,teacher_q=.4)
            self.assertEqual(len(p["values"]),size)
            self.assertEqual(p["loss_positions"],[size-1])
            self.assertEqual(p["values"][-1][4:],[0.,1.])

    def test_architecture_and_shared_initial_weights_across_packing(self) -> None:
        configure(17,cuda=False)
        a=DistilledStudent(LEGACY)
        configure(17,cuda=False)
        b=DistilledStudent(PAIRED)
        self.assertEqual(sum(p.numel() for p in a.parameters()),275969)
        self.assertEqual(sum(p.numel() for p in b.parameters()),271873)
        for name,value in b.state_dict().items():
            self.assertTrue(torch.equal(value,a.state_dict()[name][:37] if name=="position.weight" else a.state_dict()[name]),name)
        self.assertTrue(all(p.dtype==torch.float32 for p in b.parameters()))
        self.assertEqual(b.decoder.layers[0].dropout.p,0.)
        self.assertTrue(b.decoder.layers[0].norm_first)

    def test_soft_loss_only_query_q_detached(self) -> None:
        for packing in CASES:
            batch=collate_packets(sample_packets(packing),self.device)
            batch["teacher_q"].requires_grad_()
            logits=torch.randn(4,69 if packing==LEGACY else 37,requires_grad=True)
            losses=query_losses(logits,batch)
            expected=F.binary_cross_entropy_with_logits(logits[torch.arange(4),batch["queries"]],batch["teacher_q"].detach(),reduction="none")
            self.assertTrue(torch.equal(losses,expected))
            losses.mean().backward()
            mask=torch.zeros_like(logits,dtype=torch.bool)
            mask[torch.arange(4),batch["queries"]]=True
            self.assertEqual(int(torch.count_nonzero(logits.grad[~mask])),0)
            self.assertTrue(bool((logits.grad[mask]!=0).all()))
            self.assertIsNone(batch["teacher_q"].grad)

    def test_accumulation_has_same_episode_mean_update(self) -> None:
        a,b=DistilledStudent(),DistilledStudent()
        b.load_state_dict(a.state_dict())
        opt_a,opt_b=make_optimizer(a),make_optimizer(b)
        samples=sample_packets()*2
        optimizer_step(a,opt_a,samples,8,self.device)
        optimizer_step(b,opt_b,samples,4,self.device)
        for left,right in zip(a.parameters(),b.parameters()):
            torch.testing.assert_close(left,right,atol=2e-6,rtol=0)

    def test_frozen_evaluation_and_extreme_kl_no_clipping(self) -> None:
        model=DistilledStudent()
        before=tensor_hash(model)
        report=evaluate(model,sample_packets(),2,self.device)
        self.assertEqual(before,tensor_hash(model))
        canonical_bytes(report)
        extreme=metric_report([1000.],[.5])
        self.assertGreater(extreme["mean_kl_nat"],499.)
        self.assertEqual(metric_report([-1000.,1000.],[0.,1.])["mean_kl_nat"],0.)

    def test_scheduler_endpoints_and_missing_q_rejected(self) -> None:
        self.assertEqual(scheduled_lr(1),3e-4/250)
        self.assertEqual(scheduled_lr(250),3e-4)
        self.assertEqual(scheduled_lr(5000),3e-5)
        for step in (0,5001):
            with self.assertRaises(ValueError):scheduled_lr(step)
        packets=sample_packets()
        packets[0]["teacher_q"]=None
        batch=collate_packets(packets,self.device)
        with self.assertRaises(ValueError):query_losses(torch.zeros(4,37),batch)

    def test_tiny_fixture_can_fit_context_soft_targets(self) -> None:
        model=DistilledStudent()
        optimizer=make_optimizer(model)
        packets=sample_packets()
        initial=evaluate(model,packets,4,self.device)["mean_kl_nat"]
        for _ in range(200):optimizer_step(model,optimizer,packets,4,self.device)
        final=evaluate(model,packets,4,self.device)["mean_kl_nat"]
        self.assertLess(final,.001)
        self.assertLess(final,initial)


if __name__=="__main__":
    unittest.main()
