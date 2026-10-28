"""Kiểm24 probe thực và loop60/journal/cold replay bằng fixture offline có phạm vi rõ."""

from __future__ import annotations

from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
import io
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from core.mt_bicl_bank import content_hash
from core.historical_signals import digest as legacy_digest
from core.mt_bicl_v2_adapter import A_INDEX, NAMESPACE, OUTPUT, VARIANTS, StudentAdapter
from core.mt_bicl_v2_decision import JOURNAL_VERSION
from core.mt_bicl_v2_integration import DRY_VERSION, PROBE_VERSION, probe_result, reference_adapter, run_stage, verify
from core.mt_bicl_v2_io import read_envelope, write_envelope
from core.mt_bicl_v2_student import pack_input
from core.mt_bicl_v21_preparation import OUTPUT as TEACHER_OUTPUT, TEACHER_VERSION
from mt_bicl_tasks_support import builder, setup


class SemanticProbeTests(unittest.TestCase):
    """24 ID và mọi nhánh probe dùng code thật; chỉ predictor là scalar đã validate input."""

    @classmethod
    def setUpClass(cls)->None:
        bank,sources,history = setup()
        cls.template = builder(bank,sources,history).build("FPT",str(history["Datetime"].iloc[995].date()))

    def test_all24_registered_semantic_contracts_no_LLM(self)->None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixtures = root/"docs/plan/week10/protocol_fixtures_v1.json"
            fixtures.parent.mkdir(parents=True)
            fixtures.write_bytes(Path("docs/plan/week10/protocol_fixtures_v1.json").read_bytes())
            missing = deepcopy(self.template)
            missing.update(status="UNAVAILABLE",reasons=["MISSING_FEATURE"],prior=[],target=[],K=0,m=0)
            q = missing["query"]
            q.update(symbol="MWG",episode_id="MWG-"+q["as_of_date"],task_id="MWG:block"+format(q["block_index"],"04d"),
                     raw=None,z=None,model_vector=None,feature_status="UNAVAILABLE")
            inputs = {"identity":{"fixture":True},"context":{},"rows":[self.template,missing]}
            student = StudentAdapter.__new__(StudentAdapter);student.inputs = inputs
            def predict(data:dict)->float:
                pack_input(data)
                return .7
            student.predict_input = predict
            ref = {"candidate_id":"A_tp_pool","decision_contract_version":"decision_legacy_v1","prefix":"",
                   "query":{"symbol":"MWG","as_of_date":q["as_of_date"]}}
            ref["request_sha256"] = legacy_digest(ref)
            write_envelope(root/OUTPUT/"dry_run.json",DRY_VERSION,{"points":[{"point_id":q["episode_id"],"variants":{"A_reference":{"a_reference":ref}}}]})
            write_envelope(root/TEACHER_OUTPUT/"teacher_fit.json",TEACHER_VERSION,{"pi":[1/16]*16})
            with redirect_stdout(io.StringIO()):result = probe_result(root,inputs,student,lambda:None)
            self.assertEqual(result["status"],"PASS")
            self.assertEqual(len(result["probes"]),24)
            self.assertEqual(result["real_api_calls"],0)
            self.assertEqual(sum(r.get("student_forward") is False for r in result["probes"]),3)
            for row in result["probes"]:
                if row["id"].startswith("negative_net_after_costs"):
                    self.assertLess(row["diagnostic"]["historical_fixture_r_net"],0)
                    self.assertEqual(row["diagnostic"]["historical_fixture_y"],0)

    def test_reference_reuses_exact_W9_OOS_index_without_rebuild(self)->None:
        adapter = Mock()
        inputs = {"legacy_plan":{"signal_config":"old"},"protocol":{"decision":{"signal_config":{"fixture":True}}}}
        with patch("core.mt_bicl_v2_integration.build_adapter",return_value=adapter):reference_adapter(Path("."),inputs)
        adapter.load_price_feature_index.assert_called_once_with(A_INDEX["path"],expected_sha256=A_INDEX["sha256"])
        adapter.build_price_feature_index.assert_not_called()


class PointFixture:
    """Nguồn giả chỉ dành test orchestration; không thay bài dry-run nguồn thật."""
    def __init__(self,symbol:str,date:str)->None:self.symbol,self.date = symbol,date
    @property
    def source_provenance(self)->dict:return {"fixture":True,"symbol":self.symbol,"date":self.date}
    def agent_state(self)->dict:
        return {"stock_name":self.symbol,"as_of_date":self.date,"is_backtest":True,"time_frame":"1d","language":"vi",
                "sentiment_store":SimpleNamespace(data={"fixture":True},report="Sentiment fixture.")}
    def bind_full(self,state:dict)->dict:
        return {k:v for k,v in state.items() if k != "sentiment_store"}


class StudentFixture:
    """Predictor không GPU cho test journal60; không dùng làm bằng chứng học cơ chế."""
    def __init__(self,*args,**kwargs)->None:pass
    def prepare(self,row:dict,*,a_reference:dict)->dict:
        return {**{k:{"prefix":"" if k in ("Original","A_reference") else "MT fixture","probability":.7} for k in VARIANTS},
                "Numeric_only":{"probability":.7,"action":"LONG","reason":"P_GT_HALF"}}


class IntegrationJournalTests(unittest.TestCase):
    """Thực thi loop60, UUID/fsync/replay thật trên temp; không sửa production artifacts."""
    def setUp(self)->None:
        self.tmp = TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root = Path(self.tmp.name)
        symbols = ("FPT","MWG","VCB","VNM")
        rows = [{"query":{"episode_id":f"{s}-2023-{1+j//27:02d}-{1+j%27:02d}","symbol":s,"as_of_date":f"2023-{1+j//27:02d}-{1+j%27:02d}"},
                 "status":"AVAILABLE","reasons":[],"K":3,"m":8} for j in range(15) for s in symbols]
        self.inputs = {"rows":rows,"identity":{"fixture":True,"point_ids":[r["query"]["episode_id"] for r in rows]},
            "budget_identity":{"protocol_sha256":"same","grant_payload_sha256":"same","cap_seconds":14400,"W10_stop":"2099-01-01"},
            "protocol":{"development":{"support_gate":{"simultaneous_points_min":30,"simultaneous_each_symbol_min":5}},
                        "decision":{"symbol_order":list(symbols),"signal_config":{"models":{"agent_llm_model":"fixture","agent_llm_temperature":0.,"agent_llm_max_tokens":2048}},
                                    "client_max_retries":0,"client_options":{"agent":{}},"service_tier":"on_demand"}}}
        write_envelope(self.root/NAMESPACE/"active_budget_v2.json","mt_bicl_active_budget_v2",
                       {"identity":self.inputs["budget_identity"],"elapsed_seconds":4583.69,"active_since":None,"sessions":[]})
        stack = ExitStack();self.addCleanup(stack.close)
        stack.enter_context(redirect_stdout(io.StringIO()))
        adapter = SimpleNamespace(prepare=lambda s,d:PointFixture(s,d))
        stack.enter_context(patch("core.mt_bicl_v2_integration.reference_adapter",return_value=(adapter,None)))
        stack.enter_context(patch("core.mt_bicl_v2_integration.point_request",return_value=({"fixture":True},{"fixture":True})))
        stack.enter_context(patch("core.mt_bicl_v2_integration.StudentAdapter",StudentFixture))
        self.probes = {"identity":self.inputs["identity"],"status":"PASS","real_api_calls":0,"development_allowed":False,"decision_calls_allowed":False,"probes":[{"id":str(i)} for i in range(24)]}
        stack.enter_context(patch("core.mt_bicl_v2_integration.probe_result",return_value=self.probes))

    def test_all60_points_primary_order_four_stages_and_cold_replay(self)->None:
        dry = run_stage(self.root,self.inputs,"dry-run")
        run_stage(self.root,self.inputs,"probes")
        self.assertEqual(len(dry["points"]),60)
        self.assertEqual(dry["support"]["simultaneous"],60)
        self.assertTrue(all(p["upstream_stages"] == {k:1 for k in ("indicator","pattern","trend","full")} for p in dry["points"]))
        for i,row in enumerate(dry["points"]):
            rest = list(VARIANTS[1:]);expected = ["Original",*rest[i%5:],*rest[:i%5]]
            self.assertEqual(row["order"],expected)
        result = verify(self.root,self.inputs,replay=True)
        self.assertEqual(result["status"],"OFFLINE_INTEGRATION_REPLAY_MATCH")
        self.assertEqual(len(result["journals_sha256"]),120)
        self.assertEqual(verify(self.root,self.inputs,replay=False),result)
        self.assertEqual(run_stage(self.root,self.inputs,"dry-run"),dry)

    def test_insufficient_support_blocks_before_any_decision(self)->None:
        for row in self.inputs["rows"]:row["m"] = 0
        with self.assertRaisesRegex(ValueError,"INSUFFICIENT_CONTEXT"):run_stage(self.root,self.inputs,"dry-run")
        self.assertFalse((self.root/OUTPUT/"dry_run.json").exists())

    def test_nonoffline_stage_name_is_rejected_without_execution(self)->None:
        for name in ("run","train","release","decide"):
            with self.subTest(name=name),self.assertRaises(ValueError):run_stage(self.root,self.inputs,name)

    def test_journal_tamper_not_hidden_by_receipt_or_self_hash(self)->None:
        dry = run_stage(self.root,self.inputs,"dry-run");run_stage(self.root,self.inputs,"probes")
        verify(self.root,self.inputs,replay=True)
        path = self.root/OUTPUT/"dry_points"/dry["points"][0]["point_id"]/"decisions.json"
        value = read_envelope(path,JOURNAL_VERSION)
        value["branches"]["Original"]["status"] = "unknown"
        write_envelope(path,JOURNAL_VERSION,value)
        with self.assertRaises(ValueError):verify(self.root,self.inputs,replay=False)


if __name__ == "__main__":unittest.main()
