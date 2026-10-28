"""Kiểm pause/resume/discard/replay và capacity bằng optimizer scalar fixture CPU."""

from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import torch
from torch import nn
from torch.nn import functional as F

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG",":4096:8")

from core.mt_bicl_bank import content_hash
from core.mt_bicl_v2_distillation import metric_report, tensor_hash
from core.mt_bicl_v2_io import read_envelope, write_envelope
from core.mt_bicl_v2_pilot import (
    NAMESPACE, OUTPUT, REPORT_VERSION, STATE_VERSION, _read_checkpoint, choose_capacity,
    file_hash, run_pilots, verify_pilots,
)
from core.mt_bicl_v2_preparation import fixture_input
from core.mt_bicl_v2_student import CASES, LEGACY, PAIRED, collate_packets, pack_input


class ScalarStudent(nn.Module):
    """Model một tham số để kiểm transaction, không thay bài kiểm learner thật."""

    def __init__(self,packing:str=PAIRED)->None:
        super().__init__()
        self.packing=packing
        self.max_tokens=37 if packing==PAIRED else 69
        self.scalar=nn.Parameter(torch.zeros(1,dtype=torch.float32))

    def forward(self,values:torch.Tensor,roles:torch.Tensor,slots:torch.Tensor,padding:torch.Tensor)->torch.Tensor:
        """Giữ graph tới scalar để capacity có backward thật trên CPU."""
        return self.scalar.expand(len(values),self.max_tokens)


class PilotJournalTests(unittest.TestCase):
    """Mock chỉ model/forward để chạy hết500 counter; I/O và AdamW/resume là thật."""

    def setUp(self)->None:
        """Corpus giả nhỏ; không sinh output pilot trong namespace production."""
        self.temporary=TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        rows=[{"input":fixture_input([[2,2]],[0,0]),"oracle":{"probability":.52}} for _ in range(3)]
        self.inputs={"identity":{"fixture":True,"code_sha256":{},"runtime":{}},
                     "budget_identity":{"protocol_sha256":"parent","grant_payload_sha256":"same",
                                        "cap_seconds":14400,"W10_stop":"2099-01-01"},
                     "rows":{"pilot_tiny":rows[:2],"diagnostic":rows}}
        write_envelope(self.root/NAMESPACE/"active_budget_v2.json","mt_bicl_active_budget_v2",
                       {"identity":self.inputs["budget_identity"],"elapsed_seconds":254.9,
                        "active_since":None,"sessions":[]})
        self.capacity={"physical_batch":128,"accumulation":1,"attempts":[{"physical_batch":128,"status":"PASS"}],
                       "optimizer_steps":0,"weights_discarded":True}

    def report(self,model:ScalarStudent,inputs:dict,packing:str,step:int,physical:int,device:torch.device)->dict:
        """Raw logit/metric thật từ scalar; dùng để kiểm receipt và replay."""
        def metrics(source:str)->dict:
            qs=[row["oracle"]["probability"] for row in inputs["rows"][source]]
            value=metric_report([float(model.scalar.detach())]*len(qs),qs)
            value["model_tensor_sha256"]=tensor_hash(model)
            return value
        return {"step":step,"tiny":metrics("pilot_tiny"),"diagnostic":metrics("diagnostic")}

    def update(self,model:ScalarStudent,optimizer:torch.optim.Optimizer,rows:list,physical:int,device:torch.device)->dict:
        """Một AdamW step thật, counter/moment cần được khôi phục đúng khi resume."""
        optimizer.zero_grad(set_to_none=True)
        loss=F.binary_cross_entropy_with_logits(model.scalar,torch.full_like(model.scalar,.52))
        loss.backward()
        norm=float(model.scalar.grad.abs().sum())
        optimizer.step()
        return {"soft_cross_entropy":float(loss.detach()),"gradient_norm_before_clip":norm}

    def mocks(self)->tuple:
        """Cùng patch dùng cho producer và cold replay, không patch serialization/budget."""
        return (patch("core.mt_bicl_v2_pilot.DistilledStudent",ScalarStudent),
                patch("core.mt_bicl_v2_pilot.choose_capacity",return_value=self.capacity),
                patch("core.mt_bicl_v2_pilot.gradient_audit",return_value={"status":"PASS","nonzero_outside_query":0}),
                patch("core.mt_bicl_v2_pilot._report_step",side_effect=self.report),
                patch("core.mt_bicl_v2_pilot.optimizer_step",side_effect=self.update))

    def start_mocks(self)->None:
        """Tự dừng mọi patch sau test để không ảnh hưởng model suite."""
        for mocked in self.mocks():
            mocked.start()
            self.addCleanup(mocked.stop)

    def test_pause_resume_500_each_discard_and_optimizer_replay(self)->None:
        self.start_mocks()
        counter=0
        def stop()->bool:
            nonlocal counter
            counter+=1
            return counter==37
        paused=run_pilots(self.root,self.inputs,resume=True,stop=stop,device=torch.device("cpu"))
        self.assertEqual(paused["status"],"PAUSED")
        self.assertEqual(paused["cases"][LEGACY]["step"],37)
        self.assertTrue(list((self.root/OUTPUT).glob("*.pt")))
        result=run_pilots(self.root,self.inputs,resume=True,stop=lambda:False,device=torch.device("cpu"))
        self.assertEqual(result["status"],"PILOT_PASS_AWAITING_PREFLIGHT")
        self.assertFalse(list((self.root/OUTPUT).glob("*.pt")))
        verified=verify_pilots(self.root,self.inputs,replay=True,device=torch.device("cpu"))
        self.assertEqual(verified["replay"],"PASS")
        self.assertEqual(verify_pilots(self.root,self.inputs,replay=False,device=torch.device("cpu"))["replay"],"PASS")
        budget=read_envelope(self.root/NAMESPACE/"active_budget_v2.json","mt_bicl_active_budget_v2")
        self.assertGreater(budget["elapsed_seconds"],254.9)
        for packing in CASES:
            receipt=read_envelope(self.root/OUTPUT/(packing+".json"),REPORT_VERSION)
            self.assertEqual(receipt["optimizer_steps"],500)
            self.assertEqual([r["step"] for r in receipt["reports"]],[0,250,500])

    def test_wrong_optimizer_counter_is_rejected_even_with_rehashed_checkpoint(self)->None:
        self.start_mocks()
        state=run_pilots(self.root,self.inputs,resume=True,stop=lambda:True,device=torch.device("cpu"))
        record=state["cases"][LEGACY]["checkpoint"]
        path=self.root/OUTPUT/record["file"]
        value=torch.load(path,map_location="cpu",weights_only=True)
        next(iter(value["optimizer"]["state"].values()))["step"].fill_(99)
        torch.save(value,path)
        record.update(sha256=file_hash(path),bytes=path.stat().st_size)
        with self.assertRaisesRegex(ValueError,"counter"):
            _read_checkpoint(self.root/OUTPUT,record,self.inputs["identity"],LEGACY)

    def test_cleanup_interruption_recovers_report_ready_without_extra_training(self)->None:
        self.start_mocks()
        from core.mt_bicl_v2_pilot import _discard
        calls=0
        def interrupted(directory:Path,identity:dict,packing:str)->None:
            nonlocal calls
            calls+=1
            if calls==1:raise OSError("Fixture ngắt trước discard")
            _discard(directory,identity,packing)
        with patch("core.mt_bicl_v2_pilot._discard",side_effect=interrupted):
            with self.assertRaises(OSError):
                run_pilots(self.root,self.inputs,resume=True,stop=lambda:False,device=torch.device("cpu"))
        state=read_envelope(self.root/OUTPUT/"state.json",STATE_VERSION)
        self.assertEqual(state["cases"][LEGACY]["status"],"REPORT_READY")
        with patch("core.mt_bicl_v2_pilot.optimizer_step",side_effect=self.update) as update:
            run_pilots(self.root,self.inputs,resume=True,stop=lambda:False,device=torch.device("cpu"))
        self.assertEqual(update.call_count,500)
        self.assertFalse(list((self.root/OUTPUT).glob("*.pt")))

    def test_real_student_checkpoint_resume_preserves_adam_update(self)->None:
        from core.mt_bicl_training import configure,restore_rng
        from core.mt_bicl_v2_student import DistilledStudent
        from core.mt_bicl_v2_distillation import make_optimizer,optimizer_step
        from core.mt_bicl_v2_pilot import _checkpoint
        from test_mt_bicl_v2_student import sample_packets
        configure(17,cuda=False)
        a=DistilledStudent()
        oa=make_optimizer(a)
        data=sample_packets()
        optimizer_step(a,oa,data,4,torch.device("cpu"))
        class Budget:
            def used(self)->float:
                """Fixture chỉ kiểm schema/checkpoint, không dùng quỹ production."""
                return 255.
        record=_checkpoint(self.root/OUTPUT,self.inputs,PAIRED,{"step":1,"physical_batch":128},a,oa,Budget())
        payload=_read_checkpoint(self.root/OUTPUT,record,self.inputs["identity"],PAIRED)
        b=DistilledStudent()
        ob=make_optimizer(b)
        b.load_state_dict(payload["model"])
        ob.load_state_dict(payload["optimizer"])
        restore_rng(payload["python_numpy_torch_cuda_rng"])
        optimizer_step(a,oa,data,4,torch.device("cpu"))
        optimizer_step(b,ob,data,4,torch.device("cpu"))
        self.assertEqual(tensor_hash(a),tensor_hash(b))

    def test_forged_logits_self_reseal_cannot_pass_replay(self)->None:
        self.start_mocks()
        state=run_pilots(self.root,self.inputs,resume=True,stop=lambda:False,device=torch.device("cpu"))
        path=self.root/OUTPUT/(LEGACY+".json")
        receipt=read_envelope(path,REPORT_VERSION)
        metrics=receipt["reports"][-1]["diagnostic"]
        metrics["raw_logits"][0]+=.01
        metrics.update(metric_report(metrics["raw_logits"],metrics["teacher_q"]))
        write_envelope(path,REPORT_VERSION,receipt)
        state["cases"][LEGACY]["receipt"]["sha256"]=file_hash(path)
        write_envelope(self.root/OUTPUT/"state.json",STATE_VERSION,state)
        with self.assertRaisesRegex(ValueError,"cold replay"):
            verify_pilots(self.root,self.inputs,replay=True,device=torch.device("cpu"))

    def test_default_verify_binds_q_and_rejects_retained_weights(self)->None:
        self.start_mocks()
        state=run_pilots(self.root,self.inputs,resume=True,stop=lambda:False,device=torch.device("cpu"))
        foreign=self.root/OUTPUT/"foreign.pt"
        foreign.write_bytes(b"not-owned")
        with self.assertRaisesRegex(ValueError,"chưa được bỏ"):
            verify_pilots(self.root,self.inputs,replay=False,device=torch.device("cpu"))
        self.assertTrue(foreign.exists())
        foreign.unlink()
        path=self.root/OUTPUT/(LEGACY+".json")
        receipt=read_envelope(path,REPORT_VERSION)
        metrics=receipt["reports"][-1]["tiny"]
        metrics["teacher_q"][0]=.99
        metrics.update(metric_report(metrics["raw_logits"],metrics["teacher_q"]))
        write_envelope(path,REPORT_VERSION,receipt)
        state["cases"][LEGACY]["receipt"]["sha256"]=file_hash(path)
        write_envelope(self.root/OUTPUT/"state.json",STATE_VERSION,state)
        with self.assertRaisesRegex(ValueError,"q trong receipt"):
            verify_pilots(self.root,self.inputs,replay=False,device=torch.device("cpu"))

    def test_capacity_falls_back_only_after_oom_without_optimizer_step(self)->None:
        packet=pack_input(fixture_input([[2,2]],[0,0]),teacher_q=.52)
        def checked(rows:list,device:torch.device)->dict:
            if len(rows)>64:raise torch.cuda.OutOfMemoryError("OOM fixture")
            return collate_packets(rows,device)
        class Budget:
            def check(self)->None:
                """Fixture không dùng ngân sách production."""
                return None
        with patch("core.mt_bicl_v2_pilot.DistilledStudent",ScalarStudent), \
                patch("core.mt_bicl_v2_pilot.packets",return_value=[packet]*32), \
                patch("core.mt_bicl_v2_pilot.collate_packets",side_effect=checked):
            result=choose_capacity(self.inputs,torch.device("cpu"),Budget())
        self.assertEqual(result["physical_batch"],64)
        self.assertEqual(result["optimizer_steps"],0)
        self.assertEqual([v["status"] for v in result["attempts"]],["CUDA_OOM","PASS"])


if __name__=="__main__":
    unittest.main()
