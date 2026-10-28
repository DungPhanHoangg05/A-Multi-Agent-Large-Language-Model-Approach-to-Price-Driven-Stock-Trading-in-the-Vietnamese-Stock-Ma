"""Kiểm gate cơ chế, tie-break, miền train và rào test sau seal v2."""

from __future__ import annotations

from copy import deepcopy
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import torch

from core.mt_bicl_bank import SYMBOLS
from core.mt_bicl_v2_experiment import (
    OUTPUT, SEAL_VERSION, SEEDS, STEPS, ablate, mechanism_report, open_test, predict,
    selection, swap_report, training_batch, validation_summary,
)
from core.mt_bicl_v2_io import write_envelope
from core.mt_bicl_v2_preparation import fixture_input
from core.mt_bicl_v2_student import DistilledStudent, pack_input
from core.mt_bicl_v2_teacher import BetaBernoulliTeacher


def oracle(q:float) -> dict:
    """Oracle scalar độc lập cho kiểm metric float64."""
    return {"probability":q,"log_probability_one":math.log(q),"log_probability_zero":math.log1p(-q),"K":1,"m":0}


def metric_fixture() -> tuple[dict,dict]:
    """Đủ200 cặp eligible và bốn mã; không đọc output production/test đã khóa."""
    rows = [{"oracle":oracle(q),"sidecar":{"stress":bool(i%2)}} for i,q in enumerate([.15,.85]*100)]
    pairs = [{"oracle_a":oracle(.3),"oracle_b":oracle(.7),"eligible":True} for _ in range(200)]
    market = [{"query":{"episode_id":symbol,"symbol":symbol},"supervised_target":{"y":i%2}} for i,symbol in enumerate(SYMBOLS)]
    inputs = {"teacher":BetaBernoulliTeacher([1/16]*16),"corpora":{"synthetic_validation":rows,"validation_swap":pairs},"selection_rows":market}
    logits = {"full":[math.log(r["oracle"]["probability"]/(1-r["oracle"]["probability"])) for r in rows],
              "context_blind":[0.]*200,"swap_a":[math.log(.3/.7)]*200,"swap_b":[math.log(.7/.3)]*200,"market_2021":[0.]*4}
    return inputs,logits


class ExperimentTests(unittest.TestCase):
    """Các hợp đồng chọn mẫu/metric không phụ thuộc optimizer hoặc GPU."""

    def test_mechanism_and_context_blind_control(self)->None:
        inputs,z = metric_fixture()
        result = validation_summary(inputs,z)
        self.assertTrue(result["eligible"])
        self.assertEqual(result["context_blind_control"]["gate"],"FAIL")
        self.assertEqual(result["constant_control"]["gate"],"FAIL")
        self.assertIn("by_joint",result["synthetic"])
        self.assertEqual(set(result["synthetic"]["by_distribution"]),{"iid","stress"})

    def test_zero_delta_is_disagreement_and_null_correlation(self)->None:
        inputs,z = metric_fixture()
        report = swap_report(z["swap_a"],z["swap_a"],inputs["corpora"]["validation_swap"])
        self.assertEqual(report["zero_model_delta_eligible"],200)
        self.assertEqual(report["sign_agreement"],0.)
        self.assertIsNone(report["delta_pearson_correlation"])
        self.assertEqual(report["gate"],"FAIL")

    def test_constant_passing_or_insufficient_support_is_inconclusive(self)->None:
        inputs,z = metric_fixture()
        for row in inputs["corpora"]["synthetic_validation"]:row["oracle"] = oracle(.5)
        z["full"] = [0.]*200
        self.assertEqual(validation_summary(inputs,z)["mechanism_status"],"INCONCLUSIVE_TEACHER_TOO_FLAT")
        inputs,z = metric_fixture()
        inputs["corpora"]["validation_swap"] = inputs["corpora"]["validation_swap"][:199]
        z["swap_a"],z["swap_b"] = z["swap_a"][:199],z["swap_b"][:199]
        self.assertFalse(validation_summary(inputs,z)["eligible"])

    def test_market_extra_or_missing_logits_rejected(self)->None:
        inputs,z = metric_fixture()
        for values in ([0.]*3,[0.]*5):
            with self.subTest(n=len(values)),self.assertRaises(ValueError):
                validation_summary(inputs,{**z,"market_2021":values})

    def test_eligible_first_then_rank_and_no_fallback(self)->None:
        rows = [{"seed":s,"step":t,"checkpoint":{"file":f"{s}/{t}"},"report":{"file":f"{s}/{t}.json"},
                 "assessment":{"eligible":False,"mechanism_status":"FAIL","market_2021":{"macro_log_loss":0.,"macro_brier":0.}}} for s in SEEDS for t in STEPS]
        none = selection(rows)
        self.assertEqual(none["status"],"NO_ELIGIBLE_CHECKPOINT")
        self.assertIsNone(none["global_candidate_or_none"])
        for row in rows:
            if row["step"] in (500,750):
                row["assessment"] = {"eligible":True,"mechanism_status":"PASS","market_2021":{"macro_log_loss":.7,"macro_brier":.25}}
        selected = selection(rows)
        self.assertEqual((selected["global_candidate_or_none"]["seed"],selected["global_candidate_or_none"]["step"]),(17,500))
        with self.assertRaises(ValueError):selection(rows[:-1])
        with self.assertRaises(ValueError):selection(rows[:-1]+[rows[0]])
        rows[0]["assessment"]["eligible"] = True
        with self.assertRaises(ValueError):selection(rows)

    def test_training_batch_only_registered_stream_and_ids_no_sidecars(self)->None:
        class Simulator:
            """Ghi nhận index/seed và cố tình đưa latent/query_y khác nhau."""
            def __init__(self)->None:self.calls=[]
            def episode(self,stream:str,index:int,*,model_seed:int)->dict:
                self.calls.append((stream,index,model_seed))
                return {"input":fixture_input([[1,1]],[0,0]),"sidecar":{"query_y":index%2,"theta":[index]}}
        simulator = Simulator()
        inputs = {"simulator":simulator,"teacher":BetaBernoulliTeacher([1/16]*16)}
        batch = training_batch(inputs,5000,73)
        self.assertEqual(simulator.calls,[("train",i,73) for i in range(639872,640000)])
        self.assertTrue(all(p == batch[0] for p in batch))
        self.assertNotIn("sidecar",batch[0])
        training_batch(inputs,100,17,preflight=True)
        self.assertEqual(simulator.calls[-1],("preflight",12799,17))
        for step,seed in ((0,17),(5001,17),(1,99)):
            with self.assertRaises(ValueError):training_batch(inputs,step,seed)

    def test_component_removal_keeps_query_and_remaining_ids(self)->None:
        data = fixture_input([[1,1]],[2,1])
        original = deepcopy(data)
        for mode in ("full","no_prior","no_target","context_blind"):
            value = ablate(data,mode)
            self.assertEqual(value["query"],data["query"])
            if mode not in ("no_prior","context_blind"):self.assertEqual(value["prior"],data["prior"])
            if mode not in ("no_target","context_blind"):self.assertEqual(value["target"],data["target"])
        self.assertEqual(data,original)

    def test_test_barrier_no_seal_wrong_identity_and_no_eligible(self)->None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = {"identity":{"fixture":1}}
            seal = {"identity":inputs["identity"],"status":"SELECTED","global_candidate_or_none":{"seed":17}}
            with self.assertRaises(ValueError):open_test(root,inputs,seal)
            blocked = {**seal,"status":"NO_ELIGIBLE_CHECKPOINT","global_candidate_or_none":None}
            write_envelope(root/OUTPUT/"selection.json",SEAL_VERSION,blocked)
            with patch("core.mt_bicl_v2_experiment.read_envelope",return_value=blocked) as read:
                with self.assertRaises(ValueError):open_test(root,inputs,blocked)
                self.assertEqual(read.call_count,1)
            with self.assertRaises(ValueError):open_test(root,{"identity":{"fixture":2}},blocked)

    def test_frozen_inference_has_slots_no_q_and_no_parameter_update(self)->None:
        torch.set_num_threads(1)
        model = DistilledStudent()
        packets = [pack_input(fixture_input([[1,1]],[1,1]))]*3
        before = deepcopy(model.state_dict())
        values = predict(model,packets,2,torch.device("cpu"))
        self.assertEqual(len(values),3)
        self.assertTrue(all(torch.equal(before[k],v) for k,v in model.state_dict().items()))
        self.assertTrue(all(p.grad is None for p in model.parameters()))


if __name__ == "__main__":unittest.main()
