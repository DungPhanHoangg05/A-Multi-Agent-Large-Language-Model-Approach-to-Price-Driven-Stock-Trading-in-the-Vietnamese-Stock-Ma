"""Kiểm causal bằng logit, query-label barrier và chỉ decode corpus pilot được phép."""

from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import torch

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG",":4096:8")

from core.mt_bicl_training import configure
from core.mt_bicl_v2_io import read_envelope
from core.mt_bicl_v2_pilot import load_inputs, packets
from core.mt_bicl_v2_student import CASES, DistilledStudent, collate_packets, pack_input
from test_mt_bicl_v2_student import sample_packets
from core.mt_bicl_v2_preparation import fixture_input

ROOT=Path(__file__).resolve().parents[1]


class StudentLeakageTests(unittest.TestCase):
    """Không dùng kết quả thị trường hoặc learner held-out thật trong các kiểm tra."""

    def setUp(self)->None:
        """CPU fixture deterministic."""
        self.device=configure(17,cuda=False)

    def forward(self,model:DistilledStudent,batch:dict)->torch.Tensor:
        """Teacher q không xuất hiện trong lời gọi forward."""
        with torch.inference_mode():
            return model(batch["values"],batch["roles"],batch["slots"],batch["padding"])

    def test_q_flip_does_not_change_numeric_input_or_logits(self)->None:
        for packing in CASES:
            rows=sample_packets(packing)
            changed=deepcopy(rows)
            for row in changed:row["teacher_q"]=1-row["teacher_q"]
            a,b=collate_packets(rows,self.device),collate_packets(changed,self.device)
            model=DistilledStudent(packing).eval()
            self.assertTrue(torch.equal(a["values"],b["values"]))
            self.assertFalse(torch.equal(a["teacher_q"],b["teacher_q"]))
            self.assertTrue(torch.equal(self.forward(model,a),self.forward(model,b)))

    def test_future_tokens_cannot_change_earlier_logit(self)->None:
        for packing in CASES:
            model=DistilledStudent(packing).eval()
            batch=collate_packets(sample_packets(packing),self.device)
            position=2
            before=self.forward(model,batch)[:,position].clone()
            batch["values"][:,position+1:]=torch.randn_like(batch["values"][:,position+1:])*100
            self.assertTrue(torch.equal(before,self.forward(model,batch)[:,position]))

    def test_padding_and_mixed_length_batch_do_not_change_query(self)->None:
        for packing in CASES:
            rows=sample_packets(packing)
            rows.append(pack_input(fixture_input([],[0,0]),teacher_q=.5,packing=packing))
            batch=collate_packets(rows,self.device)
            model=DistilledStudent(packing).eval()
            before=self.forward(model,batch)
            batch["values"][batch["padding"]]=10000.
            after=self.forward(model,batch)
            for i,row in enumerate(rows):
                query=row["query_position"]
                self.assertEqual(float(before[i,query]),float(after[i,query]))
                alone=self.forward(model,collate_packets([row],self.device))[0,query]
                self.assertAlmostEqual(float(before[i,query]),float(alone),delta=1e-6)

    def test_injected_query_y_role_slot_mask_and_prior_loss_are_rejected(self)->None:
        for kind in ("query_y","role","slot","mask","loss","latent"):
            row=deepcopy(sample_packets()[0])
            if kind=="query_y":row["values"][-1][4]=1.
            elif kind=="role":row["roles"][-1]=0
            elif kind=="slot":row["task_slots"][-1]=0
            elif kind=="mask":row["causal_mask"]="BIDIRECTIONAL"
            elif kind=="loss":row["loss_positions"]=[0,row["query_position"]]
            else:row["theta"]=.9
            with self.assertRaises(ValueError):collate_packets([row],self.device)
        data=fixture_input([[2,0]],[0,0])
        data["query"]["y"]=1
        with self.assertRaises(ValueError):pack_input(data)

    def test_pilot_refuses_validation_test_and_market_streams(self)->None:
        for stream in ("synthetic_validation","synthetic_test","validation_swap","test_swap","2022"):
            with self.assertRaises(ValueError):packets({},CASES[0],stream)

    def test_real_loader_only_decodes_permitted_teacher_and_two_corpora(self)->None:
        decoded=[]
        def record(path:Path,version:str)->dict:
            """Theo dõi decode; hash streaming held-out vẫn được phép."""
            decoded.append(path.name)
            return read_envelope(path,version)
        with patch("core.mt_bicl_v2_pilot.read_envelope",side_effect=record):
            inputs=load_inputs(ROOT)
        self.assertEqual(set(decoded),{"teacher_fit.json","index.json","pilot_tiny.json","diagnostic.json"})
        self.assertEqual(len(inputs["rows"]["pilot_tiny"]),32)
        self.assertEqual(len(inputs["rows"]["diagnostic"]),1000)


if __name__=="__main__":
    unittest.main()
