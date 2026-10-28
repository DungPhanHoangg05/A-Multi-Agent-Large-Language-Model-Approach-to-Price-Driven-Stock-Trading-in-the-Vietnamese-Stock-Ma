"""Kiểm prompt chung, paired canonical, retry/format và unknown checkpoint offline."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from core.groq_pacing import PilotStop
from core.mt_bicl_v2_decision import COMMON_INSTRUCTION, JOURNAL_VERSION, DecisionSession, build_prompt, canonical_request, invoke_decision
from core.mt_bicl_v2_integration import OfflineDecisionFixture
from core.mt_bicl_v2_io import read_envelope, write_envelope
from core.research_invocation import CURRENT
from core.mt_bicl_context import project_episode
from test_mt_bicl_v2_adapter import AdapterTests


def shared()->dict:
    """Full reports fixture không chứa outcome query."""
    return {"stock_name":"FPT","as_of_date":"2023-04-12","time_frame":"1d","is_backtest":True,"language":"vi",
            **{k+"_report":"Báo cáo fixture trung tính." for k in ("indicator","pattern","trend","alpha","sentiment")}}


def protocol()->dict:
    """Model/options/schema chung; không cần plan hoặc API key production."""
    return {"decision":{"signal_config":{"models":{"agent_llm_model":"fixture","agent_llm_temperature":0.,"agent_llm_max_tokens":2048}},
                        "client_max_retries":0,"client_options":{"agent":{"reasoning_effort":"low","reasoning_format":"hidden"}},"service_tier":"on_demand"}}


class DecisionTests(unittest.TestCase):
    """Không HTTP: fault injection vào fixture invoke và ghi checkpoint thật ở temp."""

    def setUp(self)->None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/"decisions.json"
        self.binding = {"point_id":"FPT-2023-04-12","fixture":"same-source"}

    def session(self)->DecisionSession:return DecisionSession(self.path,self.binding)

    def test_all_branches_same_common_instruction_and_schema(self)->None:
        a,b = canonical_request(shared(),"",protocol()),canonical_request(shared(),"MT fixture p=0.700",protocol())
        self.assertEqual(a["structured"],b["structured"])
        self.assertEqual(a["model"],b["model"])
        self.assertEqual(b["messages"][0]["content"].replace("MT fixture p=0.700\n",""),a["messages"][0]["content"])
        self.assertEqual(a["messages"][0]["content"].count(COMMON_INSTRUCTION),1)
        self.assertIn("SHORT=CASH",a["messages"][0]["content"])

    def test_canonical_includes_model_schema_point_repeat(self)->None:
        a = canonical_request(shared(),"",protocol())
        self.assertNotEqual(a,canonical_request(shared(),"",protocol(),1))
        self.assertNotEqual(a,canonical_request({**shared(),"as_of_date":"2023-04-13"},"",protocol()))
        p = protocol();p["decision"]["signal_config"]["models"]["agent_llm_model"] = "different"
        self.assertNotEqual(a,canonical_request(shared(),"",p))

    def test_shared_off_only_after_durable_original_and_same_canonical(self)->None:
        llm = OfflineDecisionFixture()
        branches = {"Original":{"prefix":""},"Full_MT_BICL":{"prefix":""},"No_target":{"prefix":"MT fixture"}}
        result = self.session().run(shared(),branches,list(branches),protocol(),llm)
        self.assertEqual(llm.calls,2)
        self.assertEqual(result["branches"]["Full_MT_BICL"]["shared_off_from"],"Original")
        self.assertIsNone(result["branches"]["Full_MT_BICL"]["attempt_id"])
        before = deepcopy(result)
        self.assertEqual(self.session().run(shared(),branches,list(branches),protocol(),llm),before)
        self.assertEqual(llm.calls,2)

    def test_original_duplicate_is_an_independent_call_not_shared_off(self)->None:
        llm = OfflineDecisionFixture()
        branches = {"Original":{"prefix":""},"Original_duplicate":{"prefix":""}}
        value = self.session().run(shared(),branches,list(branches),protocol(),llm)
        self.assertEqual(llm.calls,2)
        self.assertIsNone(value["branches"]["Original_duplicate"]["shared_off_from"])

    def test_fixture_short_is_not_overridden_by_high_p(self)->None:
        llm = OfflineDecisionFixture()
        branches = {"Original":{"prefix":""},"Full_MT_BICL":{"prefix":"MT p=0.999"}}
        value = self.session().run(shared(),branches,list(branches),protocol(),llm)
        self.assertEqual(value["branches"]["Full_MT_BICL"]["decision"]["decision"],"SHORT")

    def test_ambiguous_call_keeps_uuid_and_blocks_automatic_replay(self)->None:
        class Failing(OfflineDecisionFixture):
            def invoke(self,prompt:str)->dict:
                self.calls += 1
                raise ConnectionError("fixture ambiguous")
        llm = Failing()
        branches = {"Original":{"prefix":""}}
        with self.assertRaises(PilotStop):self.session().run(shared(),branches,list(branches),protocol(),llm)
        saved = read_envelope(self.path,JOURNAL_VERSION)
        self.assertEqual(saved["branches"]["Original"]["status"],"unknown")
        self.assertIsNone(saved["branches"]["Original"]["decision"])
        with self.assertRaisesRegex(ValueError,"AMBIGUOUS"):self.session().run(shared(),branches,list(branches),protocol(),llm)
        self.assertEqual(llm.calls,1)
        self.assertEqual(read_envelope(self.path,JOURNAL_VERSION),saved)

    def test_complete_branch_mutated_request_or_binding_rejected(self)->None:
        llm = OfflineDecisionFixture()
        branches = {"Original":{"prefix":""}}
        self.session().run(shared(),branches,list(branches),protocol(),llm)
        with self.assertRaises(ValueError):DecisionSession(self.path,{**self.binding,"fixture":"different"})
        with self.assertRaises(ValueError):self.session().run(shared(),{"Original":{"prefix":"changed"}},["Original"],protocol(),llm)
        self.assertEqual(llm.calls,1)

    def test_failed_durable_write_keeps_RAM_and_disk_unknown(self)->None:
        llm = OfflineDecisionFixture();session = self.session()
        branches = {"Original":{"prefix":""}}
        def persist(path,version,value)->None:
            if value["branches"]["Original"]["status"] == "complete":raise OSError("fixture fsync failure")
            write_envelope(path,version,value)
        with patch("core.mt_bicl_v2_decision.write_envelope",side_effect=persist):
            with self.assertRaises(OSError):session.run(shared(),branches,list(branches),protocol(),llm)
        self.assertEqual(session.document["branches"]["Original"]["status"],"unknown")
        self.assertEqual(read_envelope(self.path,JOURNAL_VERSION)["branches"]["Original"]["status"],"unknown")
        with self.assertRaisesRegex(ValueError,"AMBIGUOUS"):session.run(shared(),branches,list(branches),protocol(),llm)
        self.assertEqual(llm.calls,1)

    def test_format_repair_reuses_invocation_budget_and_schema(self)->None:
        class Repair(OfflineDecisionFixture):
            budgets = []
            def invoke(self,prompt:str)->dict:
                self.budgets.append(CURRENT.get().invocation_id)
                result = super().invoke(prompt)
                if self.calls == 1:result["parsed"]["decision"] = "NEUTRAL"
                return result
        llm = Repair()
        value = invoke_decision(llm,canonical_request(shared(),"",protocol()))
        self.assertEqual(value["decision"],"SHORT")
        self.assertEqual(llm.calls,2)
        self.assertEqual(len(set(llm.budgets)),1)

    def test_invocation_links_checkpoint_uuid_point_and_branch(self)->None:
        seen = []
        class Capture(OfflineDecisionFixture):
            def invoke(self,prompt:str)->dict:
                b = CURRENT.get();seen.append((b.checkpoint_attempt_id,b.point_id,b.branch_id,b.run_signature))
                return super().invoke(prompt)
        value = self.session().run(shared(),{"Original":{"prefix":""}},["Original"],protocol(),Capture())
        self.assertEqual(seen[0][0],value["branches"]["Original"]["attempt_id"])
        self.assertEqual(seen[0][1:3],("FPT-2023-04-12","Original"))
        self.assertEqual(len(seen[0][3]),64)

    def test_prefix_or_total_overflow_rejected_before_fixture_call(self)->None:
        llm = OfflineDecisionFixture()
        with self.assertRaises(ValueError):build_prompt(shared(),"X"*601)
        with patch("core.mt_bicl_v2_decision._build_compact_prompt_vi",return_value="### [1]"+"X"*6500):
            with self.assertRaises(ValueError):self.session().run(shared(),{"Original":{"prefix":""}},["Original"],protocol(),llm)
        self.assertEqual(llm.calls,0)

    def test_query_outcome_rejected_before_render(self)->None:
        for field in ("outcome","evaluation","query_y","entry_open","net_return"):
            with self.subTest(field=field),self.assertRaises(ValueError):build_prompt({**shared(),field:0},"")

    def test_worst_full_projection_with_max_reports_keeps_budget(self)->None:
        if not hasattr(AdapterTests,"episode"):AdapterTests.setUpClass()
        episode = deepcopy(AdapterTests.episode)
        episode["query"]["model_vector"] = [-4.]*4
        for row in [*(r for t in episode["prior"] for r in t["observations"]),*episode["target"]]:row["model_vector"] = [-4.]*4
        projection = project_episode(episode,probability=.999)
        state = {**shared(),**{k+"_report":"Z"*20000 for k in ("indicator","pattern","trend","alpha","sentiment")}}
        prompt = build_prompt(state,projection["prefix"])
        self.assertLessEqual(len(projection["prefix"]),600)
        self.assertLess(len(prompt),6500)
        self.assertEqual(projection["learner_prior_count"],24)
        self.assertEqual(projection["learner_target_count"],8)

    def test_source_and_result_ownership(self)->None:
        state = shared();before = deepcopy(state)
        branches = {"Original":{"prefix":""},"Full_MT_BICL":{"prefix":""}}
        result = self.session().run(state,branches,list(branches),protocol(),OfflineDecisionFixture())
        result["branches"]["Full_MT_BICL"]["decision"]["justification"] = "changed"
        self.assertEqual(state,before)
        disk = read_envelope(self.path,JOURNAL_VERSION)
        self.assertEqual(disk["branches"]["Original"]["decision"],disk["branches"]["Full_MT_BICL"]["decision"])


if __name__ == "__main__":unittest.main()
