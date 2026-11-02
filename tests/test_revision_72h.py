"""Kiểm paired profile, PIT/donor, replay SDK và caps năm org; không gọi API thật."""

from __future__ import annotations

from copy import deepcopy
from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import os
import shutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from core.revision_common_study import read_json, digest
from core.revision_call_archive import StudyStop
from core.revision72_data import schedules, make_jobs
from core.revision72_run import allocate, variant_state, CachedLLM, checked, worker
from core.revision72_quota import PoolLedger, PoolArchive
from core.revision72_provider import RoutedLLM, PoolUnavailable, scientific_context
from core.revision_baselines import load_prices
from core.revision72_analysis import block_interval, panel_summary
from core.revision_common_study import write_json
from core.revision_audit import sha256_file
from core.revision72_run import signed

ROOT = Path(__file__).resolve().parents[1]
BANK = ROOT / "outputs/revision/r1_72h_bank_v2"


class DesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = read_json(BANK / "manifest.json")

    def test_exact_design_counts_and_feasible_shards(self):
        m = self.m
        self.assertEqual(len(m["units"]), 102)
        self.assertEqual(sum(len(j["decisions"]) for j in m["jobs"]), 474)
        self.assertEqual(len(m["panel"]), 18)
        jobs = allocate(m)
        owners = {}
        for org in range(1, 6):
            own = [j for j in jobs if j["org"] == org]
            self.assertLessEqual(sum(len(j["decisions"]) for j in own) + 2, 120)
            self.assertLess(sum(len(j["decisions"]) for j in own) + 2 * len({(j["unit_id"], j["realization"]) for j in own}) + 4, 200)
            for job in own:
                owners.setdefault(job["unit_id"], set()).add(org)
        self.assertTrue(all(len(v) == 1 for v in owners.values()))
        fallback = deepcopy(m["units"])
        for unit in fallback: unit["gate"] = "fallback"
        self.assertEqual(sum(len(j["decisions"]) for j in make_jobs(fallback, m["panel"])), 366)

    def test_purge_quality_and_train_only_donor(self):
        for scope in self.m["schedule"]:
            self.assertLess(scope["last_train_label_date"], scope["first_validation_date"])
            self.assertLess(scope["last_validation_label_date"], scope["first_test_date"])
            self.assertTrue(all(i >= 599 for i in scope["train"] + scope["validation"] + scope["test"]))
            self.assertFalse(scope["symbol"] == "BHN" and scope["fold"].startswith("b"))
        for unit in self.m["units"]:
            scope = next(s for s in self.m["schedule"] if (s["symbol"], s["fold"]) == (unit["symbol"], unit["fold"]))
            self.assertIn(unit["placebo_donor"], scope["train"])
            self.assertLess(unit["placebo_donor"] + 3, unit["decision"])
        self.assertTrue(all(u["verified_articles"] >= 3 for u in self.m["units"] if u["id"] in self.m["panel"]))

    def test_future_mutation_keeps_date_selection(self):
        old = read_json(ROOT / "outputs/revision/r1_common_bank_v3/manifest.json")
        frames, _ = load_prices(ROOT / old["protocol"]["price_snapshot"], old["protocol"]["price_quality_policy"])
        before = schedules(frames, old)
        for frame in frames.values():
            frame.loc[frame["date"] >= "2026-07-01", ["Open", "High", "Low", "Close"]] *= 2
        self.assertEqual(before, schedules(frames, old))

    def test_variant_isolation_placebo_schema_and_no_mutation(self):
        unit = self.m["units"][-1]
        asset = checked(BANK / f"features/{unit['symbol']}_{unit['decision']}.json")
        donor = checked(BANK / f"features/{unit['symbol']}_{unit['placebo_donor']}.json")
        shared = {"messages": [], "stock_name": unit["symbol"], "indicator_report": "i", "pattern_report": "p", "trend_report": "t"}
        old = digest([shared, asset, donor])
        states = {v: variant_state(shared, asset, donor, v) for v in ("B", "A", "S", "AS", "P")}
        self.assertNotIn("alpha_report", states["B"])
        self.assertNotIn("sentiment_report", states["A"])
        self.assertNotIn("sentiment_data", states["A"])
        self.assertNotIn("alpha_report", states["S"])
        self.assertNotIn("alpha_results", states["S"]["sentiment_data"])
        self.assertEqual(states["A"]["alpha_report"], states["AS"]["alpha_report"])
        self.assertEqual(states["AS"]["sentiment_report"], states["P"]["sentiment_report"])
        headings = lambda s: [x for x in s.splitlines() if x.startswith(("##", "| #", "|---"))]
        self.assertEqual(headings(states["AS"]["alpha_report"]), headings(states["P"]["alpha_report"]))
        self.assertEqual(old, digest([shared, asset, donor]))


class QuotaTests(unittest.TestCase):
    def test_one_key_cannot_have_two_inflight_requests_across_workers(self):
        with tempfile.TemporaryDirectory() as temp:
            ledger = PoolLedger(Path(temp)/"quota.sqlite", "run")
            other = PoolLedger(Path(temp)/"quota.sqlite", "run")
            self.assertEqual(ledger.acquire("vision",1,"first",[1]),1)
            self.assertIsNone(other.acquire("text",1,"second",[1]))
            other.release(1,"wrong_owner")
            self.assertIsNone(other.acquire("text",1,"second",[1]))
            ledger.release(1,"first")
            self.assertEqual(other.acquire("text",1,"second",[1]),1)

    def test_provider_pool_uses_another_key_after_one_exhausts_quota(self):
        class Exhausted(FakeListChatModel):
            def _call(self, *args, **kwargs):
                raise RuntimeError("429 tokens per day (TPD). Please try again in 18m10s")
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp);ledger=PoolLedger(path/"quota.sqlite","run")
            archive=PoolArchive(path/"shard","bank","secret1",ledger,1,0)
            archive.context={"model":"text","stage":"decision","variant":"AS","unit_id":"fixture"}
            def factory(**kwargs):
                cls=Exhausted if kwargs['api_key']=='secret1' else FakeListChatModel
                return cls(responses=['{"decision":"LONG"}'], callbacks=kwargs['callbacks'])
            with patch('langchain_groq.ChatGroq',side_effect=factory),redirect_stdout(io.StringIO()):
                result=RoutedLLM(archive,['secret1','secret2'],1,{'model':'text'},'amendment',[1,2]).invoke('fixture')
            self.assertIn('LONG',result.content)
            self.assertEqual(archive.count,2)
            requests=[read_json(p) for p in (path/'shard/calls').glob('*.request.json')]
            self.assertEqual({r['context']['provider_org'] for r in requests},{1,2})
            self.assertTrue(all(scientific_context(r['context'])==archive.context for r in requests))
            self.assertTrue(ledger.states('text',[1])[0]['active'])
            self.assertIsNone(read_json(path/'shard/usage.json')['max_requests_current_command'])

    def test_pool_stops_only_after_all_allowed_keys_report_long_quota(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp);ledger=PoolLedger(path/'quota.sqlite','run')
            archive=PoolArchive(path/'shard','bank','secret1',ledger,1,0)
            archive.context={'model':'vision','stage':'upstream'}
            for org in (1,2):ledger.block(org,'vision','quota',1000,'provider TPD')
            with patch('langchain_groq.ChatGroq') as client:
                with self.assertRaises(PoolUnavailable):
                    RoutedLLM(archive,['secret1','secret2'],1,{'model':'vision'},'epoch',[1,2]).invoke('fixture')
                client.assert_not_called()
            self.assertEqual(archive.count,0)

    def test_short_rate_wait_is_retried_without_global_pause(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp);clock=[1000000.0]
            ledger=PoolLedger(path/'quota.sqlite','run',lambda:clock[0])
            archive=PoolArchive(path/'shard','bank','secret1',ledger,1,0)
            archive.context={'model':'text','stage':'decision'}
            ledger.block(1,'text','rate',5,'fixture ITPM')
            ledger.block(2,'text','quota',1000,'fixture TPD')
            def factory(**kw):return FakeListChatModel(responses=['LONG'],callbacks=kw['callbacks'])
            def sleep(seconds):clock[0]+=seconds
            with patch('langchain_groq.ChatGroq',side_effect=factory),patch('core.revision72_provider.time.sleep',side_effect=sleep):
                response=RoutedLLM(archive,['secret1','secret2'],1,{'model':'text'},'epoch',[1,2]).invoke('fixture')
            self.assertEqual(response.content,'LONG')
            self.assertGreaterEqual(clock[0],1000006)
            self.assertEqual(archive.count,1)

    def test_old_40_decision_limit_and_deadline_do_not_stop_provider_mode(self):
        with tempfile.TemporaryDirectory() as temp:
            now = [1000000.0]
            ledger = PoolLedger(Path(temp) / "q.sqlite", "run", lambda: now[0])
            for i in range(40):
                ledger.reserve(str(i), 1, "decision", "text", now[0]+1000000)
                now[0] += 31
            ledger.reserve("above_40", 1, "decision", "text", 0)
            now[0] += 86400
            ledger.reserve("nextday", 1, "decision", "text", now[0]+1000000)
            resumed = PoolLedger(Path(temp) / "q.sqlite", "run", lambda: now[0])
            self.assertGreater(resumed.next_at(1, "text"), now[0])
            with self.assertRaises(ValueError): PoolLedger(Path(temp) / "q.sqlite", "other")

    def test_old_200_org_and_1000_total_limits_are_not_enforced(self):
        with tempfile.TemporaryDirectory() as temp:
            now = [1000000.0]
            ledger = PoolLedger(Path(temp) / "q.sqlite", "run", lambda: now[0])
            for org in range(1, 6):
                for i in range(200):
                    ledger.reserve(f"{org}_{i}", org, "upstream", "vision", now[0]+1000000)
                    now[0] += 31
                ledger.reserve(f"{org}_above_200", org, "upstream", "vision", 0)
                now[0] += 31
            ledger.reserve("above_1000", 5, "upstream", "vision", 0)

    def test_old_600_decision_limit_is_not_enforced(self):
        with tempfile.TemporaryDirectory() as temp:
            now = [1000000.0]
            ledger = PoolLedger(Path(temp) / "q.sqlite", "run", lambda: now[0])
            for day in range(3):
                for org in range(1,6):
                    for i in range(40):
                        now[0] = 1000000.0 + day*90000 + org*1500 + i*31
                        ledger.reserve(f"{day}_{org}_{i}", org, "decision", "text", 9999999999)
            now[0] += 90000
            ledger.reserve("above_600", 1, "decision", "text", 0)

    def test_format_repair_consumes_new_attempt_instead_of_replaying_same_bad_output(self):
        from agents.decision_agent import create_final_trade_decider
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            clock = [1000000.0]
            def now(): clock[0] += 31; return clock[0]
            archive = PoolArchive(path / "shard", "bank", "secret", PoolLedger(path/"q.sqlite", "run", now), 1, 9999999999)
            archive.context = {"model": "text", "stage": "decision", "variant": "AS"}
            delegate = FakeListChatModel(responses=['không có quyết định', '{"decision":"LONG","risk_reward_ratio":1.5}'], callbacks=[archive])
            with redirect_stdout(io.StringIO()):
                node = create_final_trade_decider(CachedLLM(delegate, archive))
                result = node({"stock_name":"FPT","time_frame":"1 ngày","language":"vi","is_backtest":True,
                               "indicator_report":"i","pattern_report":"p","trend_report":"t"})
            self.assertEqual(archive.count, 2)
            self.assertIn("LONG", result["final_trade_decision"])

    def test_response_resume_without_new_invoke_and_corruption_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            ledger = PoolLedger(path / "quota.sqlite", "run")
            archive = PoolArchive(path / "shard", "bank", "secret", ledger, 1, 9999999999)
            archive.context = {"model": "text", "stage": "decision", "variant": "AS", "unit_id": "fixture"}
            model = FakeListChatModel(responses=['{"decision":"LONG"}'], callbacks=[archive])
            with redirect_stdout(io.StringIO()): raw = CachedLLM(model, archive).invoke("fixture")
            checksum = next((path / "shard/calls").glob("*.response_digest.json"))
            checksum.rename(checksum.with_suffix(".backup"))
            class Bomb:
                def invoke(self, *_args, **_kwargs): raise AssertionError("Không được gọi lại network")
            replay = CachedLLM(Bomb(), archive)
            self.assertEqual(replay.invoke("fixture").content, raw.content)
            self.assertTrue(read_json(checksum)["recovered_after_interruption"])
            self.assertEqual(archive.count, 1)
            response = next((path / "shard/calls").glob("*.response.json"))
            response.write_text(response.read_text(encoding="utf8").replace("LONG", "SHORT"), encoding="utf8")
            with self.assertRaisesRegex(ValueError, "Raw response"):
                CachedLLM(Bomb(), archive).invoke("fixture")

    def test_provider_failure_is_archived_before_fallback_stop(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            ledger = PoolLedger(path / "quota.sqlite", "run")
            archive = PoolArchive(path / "shard", "bank", "secret", ledger, 1, 9999999999)
            archive.context = {"stage": "upstream", "model": "vision"}
            from langchain_core.messages import HumanMessage
            from uuid import uuid4
            key = uuid4()
            archive.on_chat_model_start({}, [[HumanMessage(content="fixture")]], run_id=key)
            with self.assertRaises(StudyStop): archive.on_llm_error(RuntimeError("429 tokens per day. try again in 18m10s"), run_id=key)
            self.assertTrue((path / f"shard/calls/{key}.error.json").exists())
            self.assertGreater(ledger.next_at(1, "vision"), ledger.clock()+1080)


class WorkerTests(unittest.TestCase):
    def test_worker_continues_cached_text_jobs_when_all_vision_keys_are_blocked(self):
        """Không dừng cả shard ở job vision nếu panel dùng cache còn chạy được bằng text."""
        manifest=read_json(BANK/'manifest.json');p=manifest['protocol'];first,second=manifest['units'][:2]
        response='{"decision":"LONG","forecast_horizon":"T+2.5","confidence":"Cao","risk_reward_ratio":1.5,"evidence_for":"fixture","evidence_against":"fixture","justification":"fixture"}'
        def factory(**kw):return FakeListChatModel(responses=[response],callbacks=kw['callbacks'],metadata=kw['metadata'])
        clock=[1000000.0]
        def now():clock[0]+=31;return clock[0]
        with tempfile.TemporaryDirectory() as temp:
            run=Path(temp)
            identity={'sha256':'fixture','bank_id':manifest['bank_id'],'deadline_epoch':0,'jobs':[
                {'id':'first','unit_id':first['id'],'org':1,'realization':0,'decisions':[{'variant':v,'repeat':0} for v in ('B','AS')]}]}
            for i in range(1,6):write_json(run/f'shards/org{i}/smoke_complete.json',signed({'run_signature':'fixture','files':[]}))
            with (patch('core.revision72_run.freeze',return_value=identity),
                  patch('langchain_groq.ChatGroq',side_effect=factory),
                  patch('core.revision72_run.PoolLedger',side_effect=lambda path,sig:PoolLedger(path,sig,now)),
                  patch('utils.static_util.generate_kline_image',return_value={'pattern_image':'fixture'}),
                  patch('utils.static_util.generate_trend_image',return_value={'trend_image':'fixture'}),
                  patch.dict(os.environ,{f'GROQ_ORG_{i}_API_KEY':f'fixture_{i}' for i in range(1,6)}),redirect_stdout(io.StringIO())):
                worker(ROOT,BANK,run,1,False)
                original=next((run/'shards/org1/decisions').glob('*_B_n0.json')).read_bytes()
                ledger=PoolLedger(run/'quota.sqlite3','fixture',now)
                for i in range(1,6):ledger.block(i,p['graph_llm_model'],'quota',100000,'fixture TPD')
                identity['jobs']=[{'id':'blocked','unit_id':second['id'],'org':1,'realization':0,'decisions':[{'variant':'B','repeat':0}]},
                    {'id':'cached','unit_id':first['id'],'org':1,'realization':0,'decisions':[{'variant':'A','repeat':1}]}]
                with self.assertRaises(PoolUnavailable):worker(ROOT,BANK,run,1,False)
                self.assertTrue((run/f"shards/org1/decisions/{first['id']}_r0_A_n1.json").exists())
                self.assertEqual(next((run/'shards/org1/decisions').glob('*_B_n0.json')).read_bytes(),original)
                self.assertEqual(len(list((run/'shards/org1/calls').glob('*.request.json'))),5)

    def test_native_nodes_smoke_pair_and_resume_use_four_fake_calls_only(self):
        """Native agents và parser thật; fake responses chỉ trong temp, không phải evidence."""
        manifest = read_json(BANK / "manifest.json")
        protocol = manifest["protocol"]
        response = '{"decision":"LONG","forecast_horizon":"T+2.5","confidence":"Cao","risk_reward_ratio":1.5,"evidence_for":"fixture","evidence_against":"fixture","justification":"fixture"}'
        def factory(**kwargs):
            return FakeListChatModel(responses=[response], callbacks=kwargs["callbacks"], metadata=kwargs["metadata"])
        clock = [1000000.0]
        def now():
            clock[0] += 31
            return clock[0]
        catalog = SimpleNamespace(models=SimpleNamespace(list=lambda: SimpleNamespace(data=[
            SimpleNamespace(id=protocol["agent_llm_model"]), SimpleNamespace(id=protocol["graph_llm_model"])])))
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp)
            identity = {"sha256": "fixture_run", "bank_id": manifest["bank_id"], "deadline_epoch": 9999999999}
            with (patch("core.revision72_run.freeze", return_value=identity),
                  patch("groq.Groq", return_value=catalog),
                  patch("langchain_groq.ChatGroq", side_effect=factory),
                  patch("core.revision72_run.PoolLedger", side_effect=lambda p, sig: PoolLedger(p, sig, now)),
                  patch("utils.static_util.generate_kline_image", return_value={"pattern_image": "fixture"}),
                  patch("utils.static_util.generate_trend_image", return_value={"trend_image": "fixture"}),
                  patch.dict(os.environ, {f"GROQ_ORG_{i}_API_KEY": f"fixture_{i}" for i in range(1,6)}),
                  redirect_stdout(io.StringIO())):
                worker(ROOT, BANK, run, 1, True)
                self.assertEqual(len(list((run / "shards/org1/calls").glob("*.request.json"))), 4)
                self.assertEqual(len(list((run / "shards/org1/decisions").glob("*.json"))), 2)
                worker(ROOT, BANK, run, 1, True)
                self.assertEqual(len(list((run / "shards/org1/calls").glob("*.request.json"))), 4)


class AnalysisTests(unittest.TestCase):
    def test_numeric_and_paired_export_use_consistent_rows_and_no_api(self):
        """Fixture rút gọn chỉ trong temp kiểm đường xuất bảng, không phải predictions thật."""
        from core.revision72_analysis import numeric, analyze
        m = deepcopy(read_json(BANK / "manifest.json"))
        scope = next(s for s in m["schedule"] if s["symbol"] == "BHN" and s["fold"] == "f2025_q4")
        m["schedule"] = [scope]
        m["units"] = [u for u in m["units"] if u["symbol"] == "BHN" and u["fold"] == "f2025_q4"]
        m["panel"], m["n_decisions"] = [], 4
        with tempfile.TemporaryDirectory() as temp:
            bank, run = Path(temp)/"bank", Path(temp)/"run"
            write_json(bank/"manifest.json", m)
            files = []
            for i in set(scope["train"]+scope["validation"]+scope["test"]):
                p=bank/f"features/BHN_{i}.json";p.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(BANK/f"features/BHN_{i}.json", p)
                files.append({"path":p.relative_to(bank).as_posix(),"sha256":sha256_file(p)})
            write_json(bank/"assets_complete.json", {"files":files})
            fake = [{"context":{"unit_id":u["id"],"smoke":False,"realization":0,"variant":v,"repeat":0},"prediction":"SHORT"}
                    for u in m["units"] for v in ("B","AS")]
            write_json(run/"run_manifest.json", signed({"deadline_epoch":0}))
            with (patch("core.revision72_analysis.logistic_predictions", return_value=([0,0], {})),
                  patch("core.revision72_analysis.release_manifest"),
                  patch("core.revision72_analysis.verify", return_value=fake),redirect_stdout(io.StringIO())):
                numeric(ROOT,bank,run)
                self.assertEqual(read_json(bank/"numeric/report.json")["n_prediction_records"],14)
                self.assertEqual(len(read_json(bank/"numeric/gross_diagnostic.json")),7)
                analyze(ROOT,bank,run)
            self.assertEqual(read_json(run/"analysis/report.json")["n_paired_units"],2)
            self.assertEqual(len(read_json(run/"analysis/gross_diagnostic.json")),9)
            self.assertTrue((run/"analysis/r1_baselines.tex").is_file())

    def test_joint_block_bootstrap_identical_predictions_have_zero_delta(self):
        rows = [{"fold": f"b{block}", "variant": variant, "label_net": label, "prediction": pred}
                for block in range(6) for variant in ("AS", "B") for label, pred in (("UP","LONG"),("DOWN","SHORT"))]
        result = block_interval(rows, ("AS", "B"))
        self.assertEqual(result["n_resamples"], 10000)
        self.assertEqual(result["n_undefined"], 0)
        self.assertEqual(result["percentile_95"], [0.0, 0.0])
        self.assertEqual(result, block_interval(rows, ("AS", "B")))

    def test_panel_uses_complete_common_support_without_filling_missing(self):
        index = {(str(u),0,v,r): {"prediction":"LONG" if u % 2 else "SHORT"}
                 for u in range(4) for v in ("B","AS") for r in range(3)}
        truth = {str(u): "UP" if u % 2 else "DOWN" for u in range(4)}
        result = panel_summary(index, list(truth), ["B","AS"], truth)
        self.assertEqual(result["n_complete_common_units"], 4)
        self.assertEqual(result["results"][0]["dispersion"]["balanced_accuracy"]["sd"], 0)
        del index[("0",0,"AS",2)]
        result = panel_summary(index, list(truth), ["B","AS"], truth)
        self.assertEqual(result["n_complete_common_units"], 3)


if __name__ == "__main__":
    unittest.main()
