"""Kiểm freeze/Git anchor/cold verify/quyền2023 và ledger append bằng repo fixture tạm."""

from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from core.mt_bicl_bank import content_hash
from core.mt_bicl_v2_io import read_envelope, write_envelope
from core.mt_bicl_v2_release import (
    A_INDEX, CODE, INTEGRATION, LEDGER, NAMESPACE, PILOT_PLAN, RELEASE_PATH, RELEASE_VERSION,
    SPECS, TEACHER, TRAINING, budget_snapshot, check_gates, freeze, ledger_baseline,
    require_development_release, source_paths, tree_manifest, verify_ledger, verify_release,
)


class ReleaseTests(unittest.TestCase):
    """Git/JSON/budget thật ở temp; mock duy nhất collector nguồn lớn đã có verifier riêng."""

    def git(self,*args:str)->str:
        result = subprocess.run(["git",*args],cwd=self.root,capture_output=True,text=True,encoding="utf-8",check=False)
        if result.returncode:raise AssertionError(result.stderr)
        return result.stdout.strip()

    def commit(self)->None:
        self.git("add",".")
        self.git("-c","user.name=Fixture","-c","user.email=fixture@example.invalid","commit","-m","test(fixture): snapshot release inputs")

    def setUp(self)->None:
        self.tmp = TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root = Path(self.tmp.name)
        self.git("init");self.git("config","core.autocrlf","false")
        for name in (*CODE,"tests/test_fixture.py","utils/frozen_helper.py",".python-version","requirements.txt"):
            path = self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b"fixture = 1\n")
        (self.root/".gitattributes").write_text("docs/plan/week10/development_release_v2.json -text\n",encoding="utf-8")
        for name in SPECS:
            path = self.root/"docs/plan/week10"/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text("{}",encoding="utf-8")
        for name in (PILOT_PLAN,A_INDEX["path"]):
            path = self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text("{}",encoding="utf-8")
        for relative,name in ((TRAINING,"replay_verification.json"),(INTEGRATION,"verification.json"),(TEACHER,"teacher_fit.json")):
            path = self.root/relative/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text("{}",encoding="utf-8")
        self.old_rows = [{"id":"old-a","status":200,"model":"fixture"},{"id":"old-b","status":"transport_error","model":"fixture"}]
        self.write_ledger(self.old_rows)
        baseline_file_hash = hashlib.sha256((self.root/LEDGER).read_bytes()).hexdigest()
        baseline_map = {r["id"]:content_hash(r) for r in self.old_rows}
        self.commit();self.code_commit = self.git("rev-parse","HEAD")
        point_ids = [f"FPT-2023-fixture-{i:02d}" for i in range(60)]
        identity = {"fixture":"integration"}
        budget = {"protocol_sha256":"same-parent","grant_payload_sha256":"same-grant","cap_seconds":14400,"W10_stop":"2099-01-01"}
        candidate = {"seed":42,"step":3000,"checkpoint":{"file":"seed42/frozen.pt"}}
        common = {"identity":identity,"budget_identity":budget,"pilot_gpu":{"fixture":"GPU_NOT_INITIALIZED"},
            "protocol":{"development":{"year":2023,"support_gate":{"simultaneous_points_min":30,"simultaneous_each_symbol_min":5}},
                        "decision":{"symbol_order":["FPT","MWG","VCB","VNM"],"llm_matrix":["Original","Full_MT_BICL"]},
                        "budget":{"window":["2026-10-28","2026-11-10"],"W10_stop":"2099-01-01","confirmation_release_and_start_by":"2026-11-05","data_stop":"2026-11-07"}},
            "selection":{"global_candidate_or_none":candidate}}
        identity["point_ids"] = point_ids
        support = {"gate":"PASS","simultaneous":41,"by_symbol":{"FPT":6,"MWG":12,"VCB":12,"VNM":11}}
        self.inputs = {"integration":common,"trees":{str(t):tree_manifest(self.root,t) for t in (TRAINING,INTEGRATION,TEACHER)},
            "dry":{"identity":identity,"status":"PASS","real_api_calls":0,"points":[{}]*60,"support":support,"max_prefix_chars":249,"max_prompt_chars":3182},
            "probes":{"identity":identity,"status":"PASS","real_api_calls":0,"probes":[{}]*24,"llm_semantic_behavior":"NOT_RUN_BEFORE_RELEASE"},
            "proof":{"identity":identity,"status":"OFFLINE_INTEGRATION_REPLAY_MATCH","journals_sha256":{str(i):"hash" for i in range(120)}},
            "report":{"candidate_mechanism_status":"PASS","technical_status":"PASS","candidate_locked_before_test":candidate,
                      "candidate_market_comparisons":{"base_rate":{"performance":"WORSE_BOTH"}},
                      "per_seed":{"42":{"synthetic":{"full":{"by_distribution":{"stress":{"gate":"FAIL","p95_absolute_error":.191}}}}}}},
            "runtime":{"python":"fixture","packages":{}}}
        write_envelope(self.root/NAMESPACE/"active_budget_v2.json","mt_bicl_active_budget_v2",
            {"identity":budget,"elapsed_seconds":5000.,"active_since":None,"sessions":[{"started_at":"2026-10-28T00:00:00+00:00","duration_seconds":5000.}]})
        stack = ExitStack();self.addCleanup(stack.close)
        self.collect = stack.enter_context(patch("core.mt_bicl_v2_release.collect_inputs",side_effect=lambda root:deepcopy(self.inputs)))
        stack.enter_context(patch("core.mt_bicl_v2_release.ACCEPTED_INTEGRATION_COMMIT",self.code_commit))
        stack.enter_context(patch("core.mt_bicl_v2_release.LEDGER_BASELINE_COUNT",2))
        stack.enter_context(patch("core.mt_bicl_v2_release.LEDGER_BASELINE_SHA256",baseline_file_hash))
        stack.enter_context(patch("core.mt_bicl_v2_release.LEDGER_REQUESTS_SHA256",content_hash(baseline_map)))
        stack.enter_context(patch("core.mt_bicl_v2_release.expected_budget_identity",return_value=budget))

    def write_ledger(self,rows:list[dict])->None:
        path = self.root/LEDGER;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps({"requests":rows},ensure_ascii=False,indent=2),encoding="utf-8")

    def anchor(self)->dict:
        value = freeze(self.root);self.commit()
        return value

    def reseal(self,value:dict)->None:write_envelope(self.root/RELEASE_PATH,RELEASE_VERSION,value)

    def test_freeze_requires_git_anchor_before_consumer(self)->None:
        value = freeze(self.root)
        self.assertTrue(value["authorization"]["development_allowed"])
        with self.assertRaisesRegex(ValueError,"neo byte"):verify_release(self.root)
        self.commit()
        self.assertEqual(verify_release(self.root),value)

    def test_idempotent_freeze_does_not_reset_or_rewrite_receipt(self)->None:
        value = self.anchor();raw = (self.root/RELEASE_PATH).read_bytes()
        before = read_envelope(self.root/NAMESPACE/"active_budget_v2.json","mt_bicl_active_budget_v2")
        self.assertEqual(freeze(self.root),value)
        self.assertEqual((self.root/RELEASE_PATH).read_bytes(),raw)
        self.assertEqual(read_envelope(self.root/NAMESPACE/"active_budget_v2.json","mt_bicl_active_budget_v2"),before)

    def test_artifact_change_rejected_by_cold_verify(self)->None:
        self.anchor();(self.root/TEACHER/"teacher_fit.json").write_text('{"changed":true}',encoding="utf-8")
        with self.assertRaises(ValueError):verify_release(self.root)

    def test_source_change_rejected_without_inference(self)->None:
        self.anchor();(self.root/"utils/frozen_helper.py").write_text("fixture = 2\n",encoding="utf-8")
        with self.assertRaises(ValueError):verify_release(self.root)

    def test_runtime_change_rejected(self)->None:
        self.anchor();self.inputs["runtime"]["python"] = "changed"
        with self.assertRaises(ValueError):verify_release(self.root)

    def test_missing_source_or_spec_cannot_self_reseal(self)->None:
        value = self.anchor();value["source_files"].pop("docs/plan/week10/protocol_v2.json");self.reseal(value)
        with self.assertRaises(ValueError):verify_release(self.root,require_anchor=False)

    def test_candidate_or_limits_cannot_be_reselected_or_hidden(self)->None:
        original = self.anchor()
        for change in ("candidate","limits","schema","cohort"):
            value = deepcopy(original)
            if change == "candidate":value["candidate"]["seed"] = 17
            if change == "limits":value["limitations"]["stress_subgroup"]["gate"] = "PASS"
            if change == "schema":value["decision_schema"] = {"new":"schema"}
            if change == "cohort":value["development"]["point_ids"][0] = "FPT-2025-01-02"
            self.reseal(value)
            with self.subTest(change=change),self.assertRaises(ValueError):verify_release(self.root,require_anchor=False)

    def test_confirmation_or_refit_cannot_be_enabled(self)->None:
        original = self.anchor()
        for flag in ("confirmation_allowed","training_allowed","refit_allowed"):
            value = deepcopy(original);value["authorization"][flag] = True;self.reseal(value)
            with self.subTest(flag=flag),self.assertRaises(ValueError):verify_release(self.root,require_anchor=False)

    def test_ledger_append_is_allowed_but_baseline_is_immutable(self)->None:
        value = self.anchor()
        self.write_ledger([*self.old_rows,{"id":"new-W11","status":"unknown","reserved_tokens":100}])
        self.assertEqual(verify_release(self.root),value)
        baseline = value["ledger"]
        for rows in (self.old_rows[:1],[{**self.old_rows[0],"status":500},self.old_rows[1]],[*self.old_rows,self.old_rows[0]]):
            self.write_ledger(rows)
            with self.subTest(rows=len(rows)),self.assertRaises(ValueError):verify_ledger(self.root,baseline)

    def test_empty_ledger_baseline_self_hash_does_not_grant(self)->None:
        value = self.anchor();value["ledger"].update(baseline_count=0,request_sha256_by_id={});self.reseal(value)
        with self.assertRaises(ValueError):verify_release(self.root,require_anchor=False)

    def test_new_responses_before_first_freeze_are_blocked(self)->None:
        self.write_ledger([*self.old_rows,{"id":"before-release","status":200}])
        with self.assertRaises(ValueError):freeze(self.root)
        self.assertFalse((self.root/RELEASE_PATH).exists())

    def test_budget_rollback_or_history_edit_is_rejected(self)->None:
        self.anchor();path = self.root/NAMESPACE/"active_budget_v2.json"
        original = read_envelope(path,"mt_bicl_active_budget_v2")
        for change in ("counter","history"):
            state = deepcopy(original)
            if change == "counter":state["elapsed_seconds"] = 4941.;state["sessions"][0]["duration_seconds"] = 4941.
            else:state["sessions"][0]["duration_seconds"] -= .1
            write_envelope(path,"mt_bicl_active_budget_v2",state)
            with self.subTest(change=change),self.assertRaises(ValueError):verify_release(self.root)

    def test_cold_verify_remains_readonly_after_cap_and_deadline(self)->None:
        value = self.anchor();path = self.root/NAMESPACE/"active_budget_v2.json"
        state = read_envelope(path,"mt_bicl_active_budget_v2");state["elapsed_seconds"] = 15000.
        write_envelope(path,"mt_bicl_active_budget_v2",state);raw = path.read_bytes()
        with patch("core.mt_bicl_v2_release.datetime") as clock:
            clock.fromisoformat.side_effect = datetime.fromisoformat
            clock.now.return_value = datetime(2100,1,1,tzinfo=timezone.utc)
            self.assertEqual(verify_release(self.root),value)
        self.assertEqual(path.read_bytes(),raw)

    def test_new_freeze_after_cap_is_blocked(self)->None:
        path = self.root/NAMESPACE/"active_budget_v2.json";state = read_envelope(path,"mt_bicl_active_budget_v2")
        state["elapsed_seconds"] = 14400.;write_envelope(path,"mt_bicl_active_budget_v2",state)
        with self.assertRaises(RuntimeError):freeze(self.root)
        self.assertFalse((self.root/RELEASE_PATH).exists())

    def test_missing_or_active_budget_cannot_create_new_grant(self)->None:
        path = self.root/NAMESPACE/"active_budget_v2.json"
        state = read_envelope(path,"mt_bicl_active_budget_v2");state["active_since"] = "2026-10-28T00:00:00+00:00"
        write_envelope(path,"mt_bicl_active_budget_v2",state)
        with self.assertRaises(ValueError):budget_snapshot(self.root,self.inputs["integration"]["budget_identity"])
        path.unlink()
        with self.assertRaises(ValueError):freeze(self.root)
        self.assertFalse(path.exists())

    def test_source_closure_allows_additional_W11_file_without_resealing(self)->None:
        value = self.anchor();path = self.root/"scripts/future_run.py";path.write_text("fixture = 1\n",encoding="utf-8");self.commit()
        self.assertEqual(verify_release(self.root),value)
        self.assertNotIn("scripts/future_run.py",value["source_files"])

    def test_market_worse_and_stress_fail_are_disclosed_not_new_gate(self)->None:
        i = self.inputs
        check_gates(i["integration"],i["dry"],i["probes"],i["proof"],i["report"])
        result = freeze(self.root)
        self.assertEqual(result["limitations"]["stress_subgroup"]["gate"],"FAIL")
        self.assertEqual(result["limitations"]["student_market_comparisons"]["base_rate"]["performance"],"WORSE_BOTH")

    def test_mechanism_support_or_missing_probe_blocks_release_gate(self)->None:
        for change in ("mechanism","support","probes","prefix"):
            i = deepcopy(self.inputs)
            if change == "mechanism":i["report"]["candidate_mechanism_status"] = "FAIL"
            if change == "support":i["dry"]["support"]["simultaneous"] = 29
            if change == "probes":i["probes"]["probes"].pop()
            if change == "prefix":i["dry"]["max_prefix_chars"] = 601
            with self.subTest(change=change),self.assertRaises(ValueError):check_gates(i["integration"],i["dry"],i["probes"],i["proof"],i["report"])

    def test_no_confirmation_or_out_of_cohort_API_authorization(self)->None:
        value = self.anchor()
        for phase in ("confirmation","training","refit","production"):
            with self.subTest(phase=phase),self.assertRaises(ValueError):require_development_release(self.root,phase=phase)
        with self.assertRaises(ValueError):require_development_release(self.root,point_id="FPT-2025-01-02")
        copy = require_development_release(self.root,point_id=value["development"]["point_ids"][0])
        copy["candidate"]["seed"] = 17
        self.assertEqual(verify_release(self.root)["candidate"]["seed"],42)

    def test_manifest_rejects_escape_and_symlink(self)->None:
        with self.assertRaises(ValueError):tree_manifest(self.root,"../outside")
        with patch("pathlib.Path.is_symlink",return_value=True):
            with self.assertRaises(ValueError):tree_manifest(self.root,TRAINING)


if __name__ == "__main__":unittest.main()
