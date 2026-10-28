"""Kiểm transaction train/resume/60 checkpoint và pipeline kết quả âm bằng scalar CPU."""

from __future__ import annotations

from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
import io
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG",":4096:8")

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

from core.mt_bicl_bank import SYMBOLS
from core.mt_bicl_training import configure
from core.mt_bicl_training_io import save_checkpoint
from core.mt_bicl_v2_distillation import make_optimizer, scheduled_lr, tensor_hash
from core.mt_bicl_v2_experiment import NAMESPACE, OUTPUT, SEEDS
from core.mt_bicl_v2_final_evaluation import evaluate_final, export_candidate, verify_final
from core.mt_bicl_v2_io import read_envelope, write_envelope
from core.mt_bicl_v2_training_run import (
    PREFLIGHT_VERSION, STATE_VERSION, _equivalent, preflight, projected_seconds, read_checkpoint, read_state, record,
    run_seed, seal_selection, snapshot, verified_records,
)


class ScalarStudent(nn.Module):
    """Adam thật với một parameter; rút gọn forward, không rút gọn counters/I/O."""
    def __init__(self)->None:
        super().__init__()
        self.scalar = nn.Parameter(torch.randn(1,dtype=torch.float32))


def update(model:ScalarStudent, optimizer:torch.optim.Optimizer, packets:list, physical:int, device:torch.device)->dict:
    """Một step thật, soft target cố định; kiểm Adam/RNG/scheduler khi tiếp tục."""
    optimizer.zero_grad(set_to_none=True)
    loss = F.binary_cross_entropy_with_logits(model.scalar,torch.full_like(model.scalar,.63))
    loss.backward()
    norm = torch.nn.utils.clip_grad_norm_(model.parameters(),1.)
    optimizer.step()
    return {"soft_cross_entropy":float(loss.detach()),"gradient_norm_before_clip":float(norm)}


class TrainingJournalTests(unittest.TestCase):
    """Mock CUDA/model/dữ liệu, giữ nguyên loop5000, Adam, checkpoint và selection."""

    def setUp(self)->None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.directory = self.root/OUTPUT
        self.inputs = {"identity":{"fixture":"main-training"},"pilot_gpu":{"fixture":"CPU"},
                       "budget_identity":{"protocol_sha256":"same-parent","grant_payload_sha256":"same-grant",
                                          "cap_seconds":14400,"W10_stop":"2099-01-01"},
                       "bank":{"records":[{"query_split":"validation","status":"AVAILABLE"} for _ in SYMBOLS]}}
        write_envelope(self.root/NAMESPACE/"active_budget_v2.json","mt_bicl_active_budget_v2",
                       {"identity":self.inputs["budget_identity"],"elapsed_seconds":456.49,"active_since":None,"sessions":[]})
        times = [.001]*100
        conservative = max(float(np.mean(times)),.001)
        write_envelope(self.directory/"preflight.json",PREFLIGHT_VERSION,
                       {"identity":self.inputs["identity"],"gpu":self.inputs["pilot_gpu"],"physical_batch":128,
                        "weights_discarded":True,"status":"PASS","steps":100,"accumulation":1,"oom_trials":[],
                        "step_seconds":times,"conservative_step_seconds":conservative,"checkpoint_seconds":.01,
                        "validation_20248_queries_seconds":.01,"remaining_active_seconds":13943.51,
                        "projected_remaining_seconds":projected_seconds(conservative,.01,.01)})
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(redirect_stdout(io.StringIO()))
        for module in ("core.mt_bicl_v2_training_run","core.mt_bicl_v2_final_evaluation"):
            self.stack.enter_context(patch(module+".DistilledStudent",ScalarStudent))
            self.stack.enter_context(patch(module+".environment",return_value=torch.device("cpu")))
        self.stack.enter_context(patch("core.mt_bicl_v2_training_run.configure",side_effect=lambda s,cuda:configure(s,cuda=False)))
        self.stack.enter_context(patch("core.mt_bicl_v2_training_run.training_batch",return_value=[{"fixture":1}]*128))
        self.stack.enter_context(patch("core.mt_bicl_v2_training_run.optimizer_step",side_effect=update))
        self.stack.enter_context(patch("core.mt_bicl_v2_training_run.checkpoint_logits",side_effect=lambda m,*a:{"scalar":[float(m.scalar.detach())]}))
        self.stack.enter_context(patch("core.mt_bicl_v2_training_run.validation_summary",side_effect=lambda inputs,z:
            {"eligible":False,"mechanism_status":"FAIL","market_2021":{"macro_log_loss":abs(z["scalar"][0]),"macro_brier":.25}}))

    def pause_at(self,seed:int,steps:int)->str:
        """Dừng sau số update mới, vẫn ghi checkpoint ngoài mốc25."""
        calls = 0
        def stop()->bool:
            nonlocal calls
            calls += 1
            return calls >= steps
        return run_seed(self.root,self.inputs,seed,resume=True,stop=stop)

    def test_pause_resume_equals_uninterrupted_adam_rng_and_schedule(self)->None:
        self.assertEqual(self.pause_at(17,37),"PAUSED")
        state = read_state(self.directory,self.inputs)
        self.assertEqual(state["seeds"]["17"]["step"],37)
        self.assertEqual(self.pause_at(17,214),"PAUSED")
        state = read_state(self.directory,self.inputs)
        case = state["seeds"]["17"]
        cp = read_checkpoint(self.directory,case["resume"],self.inputs,seed=17,step=251,physical=128)
        configure(17,cuda=False)
        model = ScalarStudent()
        optimizer = make_optimizer(model)
        for step in range(1,252):
            optimizer.param_groups[0]["lr"] = scheduled_lr(step)
            update(model,optimizer,[],128,torch.device("cpu"))
        expected = snapshot(self.inputs,model,optimizer,17,251,128,0.)
        self.assertTrue(_equivalent(cp["model"],expected["model"]))
        self.assertTrue(_equivalent(cp["optimizer"],expected["optimizer"]))
        self.assertTrue(_equivalent(cp["rng"],expected["rng"]))
        self.assertEqual(case["reports"][0]["step"],250)
        self.assertEqual(len(list((self.directory/"seed17").glob("resume-*.pt"))),1)
        self.assertGreater(read_envelope(self.root/NAMESPACE/"active_budget_v2.json","mt_bicl_active_budget_v2")["elapsed_seconds"],456.49)

    def test_pending_assessment_is_completed_before_next_optimizer_step(self)->None:
        with patch("core.mt_bicl_v2_training_run.checkpoint_logits",side_effect=ValueError("fixture interrupted assessment")):
            with self.assertRaisesRegex(ValueError,"interrupted"):self.pause_at(17,250)
        case = read_state(self.directory,self.inputs)["seeds"]["17"]
        self.assertEqual(case["step"],250)
        self.assertEqual(case["pending"]["step"],250)
        self.assertFalse(case["reports"])
        self.pause_at(17,1)
        case = read_state(self.directory,self.inputs)["seeds"]["17"]
        self.assertIsNone(case["pending"])
        self.assertEqual([r["step"] for r in case["reports"]],[250])
        self.assertEqual(case["step"],251)

    def test_orphan_fixed_checkpoint_is_adopted_only_if_identical(self)->None:
        original = write_envelope
        def fail_pointer(path:Path,version:str,payload:dict,**kwargs)->None:
            if version == STATE_VERSION and payload["seeds"]["17"]["step"] == 250:
                raise OSError("fixture pointer crash")
            original(path,version,payload,**kwargs)
        with patch("core.mt_bicl_v2_training_run.write_envelope",side_effect=fail_pointer):
            with self.assertRaisesRegex(OSError,"pointer crash"):self.pause_at(17,250)
        self.assertEqual(read_state(self.directory,self.inputs)["seeds"]["17"]["step"],225)
        path = self.directory/"seed17/checkpoint-00250.pt"
        before = path.read_bytes()
        self.pause_at(17,26)
        self.assertEqual(path.read_bytes(),before)
        self.assertEqual(read_state(self.directory,self.inputs)["seeds"]["17"]["step"],251)

    def test_checkpoint_rejects_tampered_adam_lr_source_and_hash(self)->None:
        self.pause_at(17,1)
        cp_record = read_state(self.directory,self.inputs)["seeds"]["17"]["resume"]
        cp = read_checkpoint(self.directory,cp_record,self.inputs,seed=17,step=1,physical=128)
        for change in ("step","lr","identity","dtype","maximize"):
            bad = deepcopy(cp)
            if change == "step":next(iter(bad["optimizer"]["state"].values()))["step"] += 1
            if change == "lr":bad["optimizer"]["param_groups"][0]["lr"] = .1
            if change == "identity":bad["identity_sha256"] = "wrong"
            if change == "dtype":bad["model"]["scalar"] = bad["model"]["scalar"].double()
            if change == "maximize":bad["optimizer"]["param_groups"][0]["maximize"] = True
            path = self.directory/("bad-"+change+".pt")
            save_checkpoint(path,bad)
            with self.subTest(change=change),self.assertRaises(ValueError):
                read_checkpoint(self.directory,record(self.directory,path),self.inputs,seed=17,step=1,physical=128)
        altered = {**cp_record,"sha256":"0"*64}
        with self.assertRaises(ValueError):read_checkpoint(self.directory,altered,self.inputs,seed=17,step=1,physical=128)

    def test_full_three_seed_negative_pipeline_60_checkpoints_no_test_no_export(self)->None:
        with self.assertRaises(ValueError):run_seed(self.root,self.inputs,42,resume=True)
        for seed in SEEDS:self.assertEqual(run_seed(self.root,self.inputs,seed,resume=True),"COMPLETE")
        state,records = verified_records(self.root,self.inputs,replay=True)
        self.assertEqual(len(records),60)
        self.assertEqual(len(list(self.directory.glob("seed*/checkpoint-*.pt"))),60)
        self.assertFalse(list(self.directory.glob("seed*/resume-*.pt")))
        seal = seal_selection(self.root,self.inputs)
        self.assertEqual(seal["status"],"NO_ELIGIBLE_CHECKPOINT")
        self.assertIsNone(export_candidate(self.root,self.inputs,seal))
        self.assertFalse((self.directory/"candidate.pt").exists())
        rows = [{"query":{"episode_id":s,"symbol":s,"as_of_date":"2022-01-04"},"K":1,"m":0,"supervised_target":{"y":i%2,"r_net":.02 if i%2 else -.03}} for i,s in enumerate(SYMBOLS)]
        baseline = {"fit":{"fixture":"TRAIN_ONLY"},"market_logits":{k:[0.]*4 for k in
                    ("base_rate","logistic","teacher_full","teacher_no_prior","teacher_no_target","teacher_pooling")}}
        with patch("core.mt_bicl_v2_final_evaluation.market_rows",return_value=rows),\
             patch("core.mt_bicl_v2_final_evaluation.baseline_stage",return_value=baseline),\
             patch("core.mt_bicl_v2_final_evaluation.open_test",side_effect=AssertionError("test must stay closed")):
            self.assertEqual(evaluate_final(self.root,self.inputs,resume=True),"NO_MT_BICL_RELEASE_V2")
            verified = verify_final(self.root,self.inputs,replay=True)
            self.assertEqual(verified["integrity"],"PASS")
            self.assertEqual(verified["candidate_mechanism_status"],"NO_ELIGIBLE_CHECKPOINT")
            self.assertEqual(verify_final(self.root,self.inputs,replay=False)["replay"],"PASS")
        saved = (self.directory/"selection.json").read_bytes()
        seal_selection(self.root,self.inputs)
        self.assertEqual((self.directory/"selection.json").read_bytes(),saved)
        state["seeds"]["17"]["reports"][0]["checkpoint"]["sha256"] = "0"*64
        write_envelope(self.directory/"state.json",STATE_VERSION,state)
        with self.assertRaises(ValueError):verified_records(self.root,self.inputs)

    def test_preflight_true100_updates_oom_only_fallback_and_weights_discarded(self)->None:
        (self.directory/"preflight.json").unlink()
        calls = []
        def trial(model,optimizer,rows,physical,device)->dict:
            calls.append(physical)
            if len(calls) == 1:raise torch.cuda.OutOfMemoryError("fixture128 OOM")
            return update(model,optimizer,rows,physical,device)
        with patch("core.mt_bicl_v2_training_run.optimizer_step",side_effect=trial),\
             patch("core.mt_bicl_v2_training_run.torch.cuda.synchronize"),\
             patch("core.mt_bicl_v2_training_run.torch.cuda.empty_cache"):
            result = preflight(self.root,self.inputs)
        self.assertEqual(calls,[128]+[64]*100)
        self.assertEqual(result["steps"],100)
        self.assertEqual(result["physical_batch"],64)
        self.assertTrue(result["weights_discarded"])
        self.assertFalse(list(self.directory.glob("*.pt")))
        self.assertEqual(result["status"],"PASS")

    def test_preflight_non_oom_error_does_not_reduce_batch_or_write_pass(self)->None:
        (self.directory/"preflight.json").unlink()
        with patch("core.mt_bicl_v2_training_run.optimizer_step",side_effect=ValueError("fixture invalid loss")) as step:
            with self.assertRaisesRegex(ValueError,"invalid loss"):preflight(self.root,self.inputs)
            self.assertEqual(step.call_count,1)
        self.assertFalse((self.directory/"preflight.json").exists())

    def test_preflight_projection_blocks_main_without_extra_training(self)->None:
        pre = read_envelope(self.directory/"preflight.json",PREFLIGHT_VERSION)
        for field,value in (("status","INFEASIBLE_WITHIN_REMAINING_BUDGET"),("steps",99),
                            ("physical_batch",64),("projected_remaining_seconds",0.)):
            bad = {**pre,field:value}
            write_envelope(self.directory/"preflight.json",PREFLIGHT_VERSION,bad)
            with self.subTest(field=field),self.assertRaises(ValueError):run_seed(self.root,self.inputs,17,resume=True)
        self.assertFalse((self.directory/"state.json").exists())


if __name__ == "__main__":unittest.main()
