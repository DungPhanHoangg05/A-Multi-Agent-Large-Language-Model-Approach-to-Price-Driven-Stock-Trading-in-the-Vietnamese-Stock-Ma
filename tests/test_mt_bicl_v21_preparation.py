"""Kiểm amendment trước fit, tương đương EM và journal v2.1 không reset budget."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from core.mt_bicl_v2_io import read_envelope, write_envelope
from core.mt_bicl_v2_teacher import fit_hyperprior as base_fit
from core.mt_bicl_v21_teacher import MAX_ITERATIONS, TOLERANCE, fit_hyperprior
from core.mt_bicl_v21_preparation import (
    CORPUS_VERSION, INDEX_VERSION, NAMESPACE, OUTPUT, STREAMS, file_hash,
    load_inputs, run_preparation, validate_amendment, verify_preparation,
)

ROOT = Path(__file__).resolve().parents[1]


class AmendmentTests(unittest.TestCase):
    """Các kiểm tra không dùng nhãn validation/test thị trường hoặc learner."""

    def test_locked_amendment_rejects_changed_limit_or_gate_self_reseal(self) -> None:
        path = ROOT/"docs/plan/week10/protocol_v2_1.json"
        original = validate_amendment(path.read_bytes())
        self.assertEqual(original["changes"], [{"path":"teacher.fit.max_iterations","from":200,"to":1000}])
        for field,value in (("changes", []),("convergence_unchanged","RELAXED"),("budget_not_reset",False)):
            changed = deepcopy(original)
            changed[field] = value
            changed["self_sha256"] = "0"*64
            with self.assertRaisesRegex(ValueError,"không self-seal"):
                validate_amendment(json.dumps(changed).encode())

    def test_real_inputs_change_only_iteration_limit_and_preserve_shared_budget(self) -> None:
        inputs = load_inputs(ROOT)
        parent = json.loads((ROOT/"docs/plan/week10/protocol_v2.json").read_bytes())
        restored = deepcopy(inputs["protocol"])
        self.assertEqual(restored["teacher"]["fit"]["max_iterations"],1000)
        restored["teacher"]["fit"]["max_iterations"] = 200
        self.assertEqual(restored,parent)
        self.assertEqual(inputs["budget_identity"]["protocol_sha256"],inputs["amendment"]["parent_protocol_sha256"])
        self.assertEqual(inputs["budget_identity"]["cap_seconds"],14400)

    def test_em_prefix_is_bit_identical_and_old_fitter_remains_200(self) -> None:
        tasks = [{"task_id":str(j),"successes":j%9+1,"failures":(j*3)%11+2,
                  "count":j%9+1+(j*3)%11+2} for j in range(48)]
        before,after = base_fit(tasks),fit_hyperprior(tasks)
        self.assertEqual(MAX_ITERATIONS,1000)
        self.assertEqual(TOLERANCE,1e-10)
        self.assertEqual(after["fit_objective_trace"][:len(before["fit_objective_trace"])],before["fit_objective_trace"])
        self.assertTrue(after["converged"])
        self.assertLess(after["max_pi_delta"],1e-10)
        from core.mt_bicl_v2_teacher import MAX_ITERATIONS as old_limit
        self.assertEqual(old_limit,200)


class AmendedJournalTests(unittest.TestCase):
    """Stage giả trên đĩa, dùng đúng budget root cũ và không sửa artifact STOP200."""

    def setUp(self) -> None:
        """Tạo fixture riêng, không fit dữ liệu thật hoặc sinh corpus thật."""
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.inputs = {"identity":{"fixture":"v2.1"},"budget_identity":{
            "protocol_sha256":"parent","grant_payload_sha256":"same-grant",
            "cap_seconds":14400,"W10_stop":"2099-01-01"}}
        self.fitted = {"identity":self.inputs["identity"],"converged":True,"status":"CONVERGED",
                       "iterations":237,"max_pi_delta":9e-11,"training_allowed":False,"decision_calls_allowed":False}
        write_envelope(self.root/NAMESPACE/"active_budget_v2.json","mt_bicl_active_budget_v2",
                       {"identity":self.inputs["budget_identity"],"elapsed_seconds":12.5,
                        "active_since":None,"sessions":[]})

    def corpus(self,inputs:dict,fitted:dict,teacher_hash:str,stream:str,check:object=None)->dict:
        """Payload nhỏ để kiểm hash/schema/resume, không giả thành oracle thật."""
        return {"identity":inputs["identity"],"stream":stream,"teacher_byte_sha256":teacher_hash,
                "fixture_probability":.4,"training_allowed":False,"decision_calls_allowed":False}

    def test_resume_replay_new_output_and_shared_counter(self)->None:
        calls=[]
        def interrupted(*args:object)->dict:
            calls.append(args[3])
            if args[3]==STREAMS[1]:raise KeyboardInterrupt()
            return self.corpus(*args)
        with patch("core.mt_bicl_v21_preparation.prepare_teacher",return_value=self.fitted), \
                patch("core.mt_bicl_v21_preparation.prepare_corpus",side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):run_preparation(self.root,self.inputs,resume=True)
        with patch("core.mt_bicl_v21_preparation.prepare_teacher",side_effect=AssertionError("Không fit lại")), \
                patch("core.mt_bicl_v21_preparation.prepare_corpus",side_effect=self.corpus) as build:
            run_preparation(self.root,self.inputs,resume=True)
            self.assertEqual(build.call_count,len(STREAMS)-1)
        with patch("core.mt_bicl_v21_preparation.prepare_teacher",return_value=self.fitted), \
                patch("core.mt_bicl_v21_preparation.prepare_corpus",side_effect=self.corpus):
            self.assertEqual(verify_preparation(self.root,self.inputs,replay=True)["replay"],"PASS")
        self.assertTrue((self.root/OUTPUT/"index.json").exists())
        self.assertFalse((self.root/NAMESPACE/"teacher_v2").exists())
        state=read_envelope(self.root/NAMESPACE/"active_budget_v2.json","mt_bicl_active_budget_v2")
        self.assertGreaterEqual(state["elapsed_seconds"],12.5)

    def test_replay_stops_self_resealed_prediction(self)->None:
        with patch("core.mt_bicl_v21_preparation.prepare_teacher",return_value=self.fitted), \
                patch("core.mt_bicl_v21_preparation.prepare_corpus",side_effect=self.corpus):
            run_preparation(self.root,self.inputs,resume=True)
            path=self.root/OUTPUT/(STREAMS[0]+".json")
            value=read_envelope(path,CORPUS_VERSION)
            value["fixture_probability"]=.8
            write_envelope(path,CORPUS_VERSION,value)
            ip=self.root/OUTPUT/"index.json"
            index=read_envelope(ip,INDEX_VERSION)
            index["files"][path.name].update(sha256=file_hash(path),bytes=path.stat().st_size)
            write_envelope(ip,INDEX_VERSION,index)
            with self.assertRaisesRegex(ValueError,"khác cold replay"):
                verify_preparation(self.root,self.inputs,replay=True)

    def test_new_recipe_still_stops_without_corpus_if_nonconverged(self)->None:
        failed={**self.fitted,"converged":False,"status":"STOP_TEACHER_NONCONVERGENCE_NO_UNIFORM_FALLBACK"}
        with patch("core.mt_bicl_v21_preparation.prepare_teacher",return_value=failed), \
                patch("core.mt_bicl_v21_preparation.prepare_corpus",side_effect=AssertionError("Không fallback")):
            result=run_preparation(self.root,self.inputs,resume=True)
        self.assertEqual(set(result["files"]),{"teacher_fit.json"})
        self.assertEqual(verify_preparation(self.root,self.inputs,replay=False)["teacher_status"],failed["status"])


if __name__=="__main__":
    unittest.main()
