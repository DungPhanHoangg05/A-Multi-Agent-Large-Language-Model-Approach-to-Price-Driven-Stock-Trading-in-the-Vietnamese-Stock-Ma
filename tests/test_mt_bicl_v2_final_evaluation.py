"""Kiểm candidate test FAIL không reselection, export và journal sau seal bằng CPU fixture."""

from __future__ import annotations

from contextlib import ExitStack, redirect_stdout
import io
import math
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG",":4096:8")

import torch

from core.mt_bicl_bank import SYMBOLS
from core.mt_bicl_training import configure
from core.mt_bicl_training_io import save_checkpoint
from core.mt_bicl_v2_distillation import make_optimizer, scheduled_lr
from core.mt_bicl_v2_experiment import NAMESPACE, OUTPUT, SEAL_VERSION
from core.mt_bicl_v2_final_evaluation import REPORT_VERSION, evaluate_final, export_candidate, verify_final
from core.mt_bicl_v2_io import read_envelope, write_envelope
from core.mt_bicl_v2_preparation import fixture_input
from core.mt_bicl_v2_teacher import BetaBernoulliTeacher
from core.mt_bicl_v2_training_run import STATE_VERSION, record, snapshot
from core.mt_bicl_v21_preparation import CORPUS_VERSION, OUTPUT as TEACHER_OUTPUT, file_hash
from test_mt_bicl_v2_training_run import ScalarStudent, update


class FinalEvaluationTests(unittest.TestCase):
    """Fixture chỉ có một eligible seed; hai seed khác không được forward hoặc thay thế."""

    def setUp(self)->None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.directory = self.root/OUTPUT
        self.inputs = {"identity":{"fixture":"test-after-seal"},"pilot_gpu":{"fixture":"CPU"},
                       "teacher":BetaBernoulliTeacher([1/16]*16),
                       "budget_identity":{"protocol_sha256":"parent","grant_payload_sha256":"grant","cap_seconds":14400,"W10_stop":"2099-01-01"},
                       "context":{},"bank":{"records":[{"query_split":"validation","status":"AVAILABLE"} for _ in SYMBOLS]}}
        write_envelope(self.root/NAMESPACE/"active_budget_v2.json","mt_bicl_active_budget_v2",
                       {"identity":self.inputs["budget_identity"],"elapsed_seconds":456.49,"active_since":None,"sessions":[]})
        configure(17,cuda=False)
        model = ScalarStudent()
        optimizer = make_optimizer(model)
        for step in range(1,251):
            optimizer.param_groups[0]["lr"] = scheduled_lr(step)
            update(model,optimizer,[],128,torch.device("cpu"))
        cp = self.directory/"seed17/checkpoint-00250.pt"
        save_checkpoint(cp,snapshot(self.inputs,model,optimizer,17,250,128,456.49))
        candidate = {"seed":17,"step":250,"checkpoint":record(self.directory,cp),"report":{"fixture":1}}
        self.seal = {"identity":self.inputs["identity"],"status":"SELECTED","global_candidate_or_none":candidate,
                     "per_seed_candidate_or_none":{"17":candidate,"42":None,"73":None}}
        write_envelope(self.directory/"selection.json",SEAL_VERSION,self.seal)
        write_envelope(self.directory/"state.json",STATE_VERSION,{"physical_batch":128})
        def oracle(q:float)->dict:
            """Giá trị scalar độc lập chỉ dùng kiểm logic report/gate."""
            return {"probability":q,"log_probability_one":math.log(q),"log_probability_zero":math.log1p(-q),"K":1,"m":0}
        data = fixture_input([[1,1]],[1,1])
        tests = [{"input":data,"oracle":oracle(q),"sidecar":{"stress":bool(i%2)}} for i,q in enumerate([.15,.85]*100)]
        pairs = [{"input_a":data,"input_b":data,"oracle_a":oracle(.3),"oracle_b":oracle(.7),"eligible":True} for _ in range(200)]
        for name,episodes in (("synthetic_test",tests),("test_swap",pairs)):
            write_envelope(self.root/TEACHER_OUTPUT/(name+".json"),CORPUS_VERSION,{"episodes":episodes})
        self.rows = [{"query":{"episode_id":s,"symbol":s,"as_of_date":"2022-01-04"},"K":1,"m":0,
                      "supervised_target":{"y":i%2,"r_net":.02 if i%2 else -.03}} for i,s in enumerate(SYMBOLS)]
        self.baseline = {"fit":{"fixture":"TRAIN_ONLY"},"market_logits":{k:[0.]*4 for k in
                         ("base_rate","logistic","teacher_full","teacher_no_prior","teacher_no_target","teacher_pooling")}}
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(redirect_stdout(io.StringIO()))
        self.stack.enter_context(patch.dict("core.mt_bicl_v2_experiment.FROZEN_TEACHER",
            {name+".json":file_hash(self.root/TEACHER_OUTPUT/(name+".json")) for name in ("synthetic_test","test_swap")}))
        for module in ("core.mt_bicl_v2_training_run","core.mt_bicl_v2_final_evaluation"):
            self.stack.enter_context(patch(module+".DistilledStudent",ScalarStudent))
        self.stack.enter_context(patch("core.mt_bicl_v2_final_evaluation.environment",return_value=torch.device("cpu")))
        self.stack.enter_context(patch("core.mt_bicl_v2_final_evaluation.seal_selection",return_value=self.seal))
        self.stack.enter_context(patch("core.mt_bicl_v2_final_evaluation.verified_records",return_value=({},[])))
        self.stack.enter_context(patch("core.mt_bicl_v2_final_evaluation.market_rows",return_value=self.rows))
        self.stack.enter_context(patch("core.mt_bicl_v2_final_evaluation.market_input",side_effect=lambda *a:data))
        self.stack.enter_context(patch("core.mt_bicl_v2_final_evaluation.baseline_stage",return_value=self.baseline))
        self.stack.enter_context(patch("core.mt_bicl_v2_final_evaluation.predict",side_effect=lambda m,rows,*a:[float(m.scalar.detach())]*len(rows)))

    def test_failed_test_keeps_candidate_no_reselection_and_technical_replay_pass(self)->None:
        sealed = (self.directory/"selection.json").read_bytes()
        self.assertEqual(evaluate_final(self.root,self.inputs,resume=True),"NO_MT_BICL_RELEASE_V2")
        report = read_envelope(self.directory/"report.json",REPORT_VERSION)
        self.assertEqual(report["candidate_locked_before_test"]["seed"],17)
        self.assertEqual(report["candidate_mechanism_status"],"FAIL")
        self.assertFalse(report["reselection_allowed"])
        self.assertFalse(report["development_allowed"])
        self.assertEqual(report["per_seed"]["42"]["status"],"NOT_RUN_NO_ELIGIBLE_CHECKPOINT")
        self.assertEqual(report["per_seed"]["73"]["status"],"NOT_RUN_NO_ELIGIBLE_CHECKPOINT")
        self.assertIn("teacher_full",report["candidate_market_comparisons"])
        self.assertIn("by_distribution",report["per_seed"]["17"]["synthetic"]["full"])
        self.assertEqual(verify_final(self.root,self.inputs,replay=True)["replay"],"PASS")
        self.assertEqual(verify_final(self.root,self.inputs,replay=False)["replay"],"PASS")
        self.assertEqual((self.directory/"selection.json").read_bytes(),sealed)
        exported = torch.load(self.directory/"candidate.pt",map_location="cpu",weights_only=True)
        self.assertNotIn("optimizer",exported)
        self.assertEqual(exported["seed"],17)

    def test_pause_after_baseline_resume_does_not_forward_finished_stage(self)->None:
        self.assertEqual(evaluate_final(self.root,self.inputs,resume=True,stop=lambda:True),"PAUSED")
        self.assertFalse((self.directory/"report.json").exists())
        with patch("core.mt_bicl_v2_final_evaluation.baseline_stage",side_effect=AssertionError("baseline must resume")):
            self.assertEqual(evaluate_final(self.root,self.inputs,resume=True),"NO_MT_BICL_RELEASE_V2")

    def test_missing_seal_blocks_evaluation_before_test_or_export(self)->None:
        (self.directory/"selection.json").unlink()
        with self.assertRaises(ValueError):evaluate_final(self.root,self.inputs,resume=True)
        self.assertFalse((self.directory/"candidate.pt").exists())

    def test_export_cannot_overwrite_changed_candidate_weights(self)->None:
        export_candidate(self.root,self.inputs,self.seal)
        path = self.directory/"candidate.pt"
        value = torch.load(path,map_location="cpu",weights_only=True)
        value["model"]["scalar"] += 1
        torch.save(value,path)
        with self.assertRaises(ValueError):export_candidate(self.root,self.inputs,self.seal)


if __name__ == "__main__":unittest.main()
