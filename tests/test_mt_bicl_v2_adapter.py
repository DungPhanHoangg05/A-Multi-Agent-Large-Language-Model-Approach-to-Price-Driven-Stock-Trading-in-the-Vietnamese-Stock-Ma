"""Kiểm adapter/membership/PIT/projection v2 bằng nguồn giá tổng hợp, không GPU/API."""

from __future__ import annotations

from copy import deepcopy
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import torch

from core.mt_bicl_bank import content_hash
from core.historical_signals import digest as legacy_digest
from core.mt_bicl_context import project_episode
from core.mt_bicl_v2_adapter import StudentAdapter, VARIANTS, load_inputs, resolve_episode
from core.mt_bicl_v2_distillation import tensor_hash
from core.mt_bicl_v2_preparation import fixture_input
from core.mt_bicl_v2_student import DistilledStudent
from mt_bicl_tasks_support import builder, setup


class AdapterTests(unittest.TestCase):
    """Khóa các nhánh chính và tình huống dữ liệu sai trước model/prefix."""

    @classmethod
    def setUpClass(cls)->None:
        bank,sources,history = setup()
        query = str(history["Datetime"].iloc[995].date())
        cls.episode = builder(bank,sources,history).build("FPT",query)

    def adapter(self,*,available:bool=True)->tuple[StudentAdapter,dict,dict,list]:
        """P giả phụ thuộc C để chứng minh No_target recompute và giữ D/x."""
        row = deepcopy(self.episode)
        if not available:
            row.update(status="UNAVAILABLE",K=0,m=0,prior=[],target=[],reasons=["MISSING_FEATURE"])
            row["query"].update(raw=None,z=None,model_vector=None,feature_status="UNAVAILABLE")
        value = StudentAdapter.__new__(StudentAdapter)
        value.inputs = {"context":{},"rows":[deepcopy(row)]}
        calls = []
        def probability(episode:dict)->float:
            calls.append(deepcopy(episode))
            return .7 if episode["m"] else .4
        value.probability = probability
        reference = {"candidate_id":"A_tp_pool","decision_contract_version":"decision_legacy_v1","prefix":"A fixture",
                     "query":{"symbol":"FPT","as_of_date":row["query"]["as_of_date"]}}
        reference["request_sha256"] = legacy_digest(reference)
        return value,row,reference,calls

    def test_six_variants_projection_and_numeric(self)->None:
        adapter,row,ref,calls = self.adapter()
        result = adapter.prepare(row,a_reference=ref)
        self.assertEqual(set(result),set(VARIANTS)|{"Numeric_only"})
        self.assertEqual(result["Original"]["prefix"],"")
        self.assertEqual(result["A_reference"]["prefix"],"A fixture")
        self.assertNotIn("p=",result["Plain_ICL"]["prefix"])
        self.assertIn("p=0.700",result["Full_MT_BICL"]["prefix"])
        self.assertIn("p=0.400",result["No_target"]["prefix"])
        self.assertIn("p=0.700",result["Stats_only"]["prefix"])
        self.assertNotIn("P1:",result["Stats_only"]["prefix"])
        self.assertNotIn("T:",result["Stats_only"]["prefix"])
        self.assertEqual(result["Numeric_only"]["action"],"LONG")
        self.assertTrue(all(len(result[k]["prefix"])<=600 for k in VARIANTS))
        self.assertEqual(result["Plain_ICL"]["projection"]["visible_ids"],result["Full_MT_BICL"]["projection"]["visible_ids"])

    def test_no_target_keeps_D_query_and_recomputes_without_retrieval(self)->None:
        adapter,row,ref,calls = self.adapter()
        adapter.prepare(row,a_reference=ref)
        self.assertEqual(len(calls),2)
        self.assertEqual(calls[0]["prior"],calls[1]["prior"])
        self.assertEqual(calls[0]["query"],calls[1]["query"])
        self.assertEqual(calls[1]["target"],[])
        self.assertEqual(calls[1]["m"],0)

    def test_missing_feature_turns_context_off_without_model_forward(self)->None:
        adapter,row,ref,calls = self.adapter(available=False)
        result = adapter.prepare(row,a_reference=ref)
        self.assertFalse(calls)
        for name in ("Plain_ICL","Full_MT_BICL","No_target","Stats_only"):
            self.assertEqual(result[name]["prefix"],"")
            self.assertIsNone(result[name]["probability"])
        self.assertEqual(result["Numeric_only"],{"action":"CASH","probability":None,"reason":"QUERY_FEATURE_UNAVAILABLE"})

    def test_half_threshold_is_strict_and_not_LLM_override(self)->None:
        adapter,row,ref,calls = self.adapter()
        for p,action in ((.5,"CASH"),(.5000001,"LONG"),(0.,"CASH"),(1.,"LONG")):
            adapter.probability = lambda ep,q=p:q
            self.assertEqual(adapter.prepare(row,a_reference=ref)["Numeric_only"]["action"],action)

    def test_nonfinite_p_is_error_not_cash(self)->None:
        adapter,row,ref,calls = self.adapter()
        for p in (float("nan"),float("inf"),-.01,1.01):
            adapter.probability = lambda ep,q=p:q
            with self.subTest(p=p),self.assertRaises(ValueError):adapter.prepare(row,a_reference=ref)

    def test_mutated_membership_or_features_cannot_reseal(self)->None:
        adapter,row,ref,calls = self.adapter()
        bad = deepcopy(row)
        bad["target"][0]["y"] = 1-bad["target"][0]["y"]
        bad["target"][0]["r_net"] *= -1
        with self.assertRaises(ValueError):adapter.prepare(bad,a_reference=ref)
        self.assertFalse(calls)

    def test_query_outcomes_and_equal_exit_rejected(self)->None:
        for field in ("outcome","supervised_target","query_y","evaluation"):
            with self.subTest(field=field),self.assertRaises(ValueError):resolve_episode({**self.episode,field:0},{})
        bad = deepcopy(self.episode)
        bad["query"]["y"] = 1
        with self.assertRaises(ValueError):resolve_episode(bad,{})
        bad = deepcopy(self.episode)
        bad["target"][-1]["exit_date"] = bad["query"]["as_of_date"]
        with self.assertRaises(ValueError):resolve_episode(bad,{})

    def test_duplicate_and_future_scaler_rejected(self)->None:
        bad = deepcopy(self.episode)
        bad["target"][0] = deepcopy(bad["target"][1])
        with self.assertRaises(ValueError):resolve_episode(bad,{})
        bad = deepcopy(self.episode)
        bad["scaler"]["fit_max_exit_date"] = bad["query"]["as_of_date"]
        with self.assertRaises(ValueError):resolve_episode(bad,{})

    def test_reference_wrong_hash_point_or_profile_rejected(self)->None:
        adapter,row,ref,calls = self.adapter()
        for field,value in (("prefix","changed"),("candidate_id","C2"),("decision_contract_version","new_schema")):
            with self.subTest(field=field),self.assertRaises(ValueError):adapter.prepare(row,a_reference={**ref,field:value})
        ref["query"]["as_of_date"] = "2020-01-02"
        ref["request_sha256"] = legacy_digest({k:v for k,v in ref.items() if k != "request_sha256"})
        with self.assertRaises(ValueError):adapter.prepare(row,a_reference=ref)

    def test_source_ownership_and_native_json(self)->None:
        adapter,row,ref,calls = self.adapter()
        before = deepcopy(row)
        result = adapter.prepare(row,a_reference=ref)
        result["A_reference"]["a_reference"]["prefix"] = "changed"
        result["Full_MT_BICL"]["projection"]["visible_ids"]["target"].append("foreign")
        self.assertEqual(row,before)
        self.assertEqual(ref["prefix"],"A fixture")
        content_hash(result)

    def test_pure_model_cpu_finite_frozen_and_query_label_rejected(self)->None:
        torch.set_num_threads(1)
        adapter = StudentAdapter.__new__(StudentAdapter)
        adapter.device = torch.device("cpu")
        adapter.model = DistilledStudent().eval().requires_grad_(False)
        adapter.fingerprint = tensor_hash(adapter.model)
        data = fixture_input([[1,1]],[1,1])
        self.assertTrue(math.isfinite(adapter.predict_input(data)))
        self.assertEqual(tensor_hash(adapter.model),adapter.fingerprint)
        for field,value in (("y",1),("theta",.8)):
            wrong = deepcopy(data)
            wrong["query"][field] = value
            with self.assertRaises(ValueError):adapter.predict_input(wrong)
        data["query"]["x"][0] = float("nan")
        with self.assertRaises(ValueError):adapter.predict_input(data)

    def test_frozen_loader_does_not_accept_empty_training_namespace(self)->None:
        with TemporaryDirectory() as tmp,patch("core.mt_bicl_v2_adapter.load_teacher_inputs",return_value={}):
            with self.assertRaises(ValueError):load_inputs(Path(tmp))


if __name__ == "__main__":unittest.main()
