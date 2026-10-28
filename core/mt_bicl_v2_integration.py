"""Dry-run60 điểm và24 probe hợp đồng offline; không gọi LLM hoặc cấp release."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from core.backtest_engine import compute_round_trip_net_return
from core.bayesian_memory import read_json
from core.improvement_prior import point_request
from core.mt_bicl_bank import content_hash
from core.mt_bicl_context import project_episode
from core.mt_bicl_evaluation import market_input
from core.mt_bicl_v2_adapter import A_INDEX, NAMESPACE, OUTPUT, VARIANTS, StudentAdapter, resolve_episode
from core.mt_bicl_v2_decision import COMMON_INSTRUCTION, DecisionSession, build_prompt
from core.mt_bicl_v2_decision import JOURNAL_VERSION
from core.mt_bicl_v2_io import ActiveBudget, read_envelope, write_envelope
from core.mt_bicl_v2_preparation import fixture_input
from core.mt_bicl_v2_teacher import BetaBernoulliTeacher
from core.mt_bicl_v21_preparation import OUTPUT as TEACHER_OUTPUT, TEACHER_VERSION, file_hash
from core.pilot_readiness import build_adapter
from core.prior_context import REPORT_FIELDS
from core.prior_stage_journal import StageJournal

DRY_VERSION = "mt_bicl_integration_dry_run_v2"
PROBE_VERSION = "mt_bicl_semantic_contract_probes_v2"
VERIFY_VERSION = "mt_bicl_integration_verification_v2"


class OfflineDecisionFixture:
    """Client thuần offline, cố định SHORT để kiểm pipeline không ép action theo p."""

    def __init__(self)->None:self.calls = 0

    def with_structured_output(self,*args:Any,**kwargs:Any)->OfflineDecisionFixture:
        """Cùng giao diện structured; không có network, key hoặc quota thật."""
        return self

    def invoke(self,prompt:str)->dict[str,Any]:
        """Response fixture không được dùng như hành vi LLM hoặc kết quả thị trường."""
        self.calls += 1
        return {"parsed":{"decision":"SHORT","forecast_horizon":"T+2.5","confidence":"Thấp",
            "risk_reward_ratio":1.,"evidence_for":"Fixture kiểm hợp đồng.",
            "evidence_against":"Không có suy luận LLM thật.","justification":"Fixture offline; không đo lợi nhuận."},
            "raw":None,"parsing_error":None}


def shared_fixture(point:Any,path:Path,binding:dict[str,Any]) -> tuple[dict[str,Any],dict[str,int]]:
    """Tái dùng journal4 stage thật với reports fixture; sentiment và giá vẫn từ nguồn PIT."""
    journal = StageJournal(path,binding,create=True)
    state = point.agent_state()
    def full(current:dict[str,Any])->dict[str,Any]:
        """Năm Alpha trung tính tổng hợp nhất quán, sentiment giữ snapshot thực đã lọc."""
        store = current["sentiment_store"]
        factors = [{"id":i,"signal":"TRUNG TÍNH"} for i in range(1,6)]
        report = "\n".join(["| ID | Tên | Giá trị | Trọng số | Tín hiệu | Ghi chú |",
            *[f"| {i} | Fixture | 0 | 1 | TRUNG TÍNH | Offline |" for i in range(1,6)],"TỔNG HỢP: Trung tính"])
        return {"alpha_report":report,"sentiment_report":store.report,"sentiment_data":{**deepcopy(store.data),"alpha_results":factors}}
    nodes = {"indicator":lambda s:{"indicator_report":"Đồng thuận chủ đạo: Trung tính\nFixture offline."},
             "pattern":lambda s:{"pattern_report":"Thiên lệch dự báo: Trung tính\nFixture offline."},
             "trend":lambda s:{"trend_report":"Hướng xu hướng: Trung tính\nFixture offline."},"full":full}
    for name,node in nodes.items():state.update(journal.invoke(name,node,deepcopy(state)))
    shared = point.bind_full(state)
    counts = {name:len(value["attempts"]) for name,value in journal.document["nodes"].items()}
    if counts != {k:1 for k in nodes}:raise ValueError("Dry-run gọi stage upstream nhiều hơn một lần/point")
    return shared,counts


def reference_adapter(root:Path,inputs:dict[str,Any])->tuple[Any,Any]:
    """Giữ bank/selector/scaler/hệ thống A_tp_pool nguồn W9, cùng cấu hình upstream run mới."""
    plan = deepcopy(inputs["legacy_plan"])
    plan["signal_config"] = deepcopy(inputs["protocol"]["decision"]["signal_config"])
    adapter = build_adapter(plan,root)
    index = adapter.load_price_feature_index(A_INDEX["path"],expected_sha256=A_INDEX["sha256"])
    return adapter,index


def dry_result(root:Path,inputs:dict[str,Any],student:StudentAdapter,work:Path,check:Any)->dict[str,Any]:
    """Toàn bộ60 point, sáu nhánh+numeric, nguồn thật và fixture reports/Decision; không P&L."""
    adapter,index = reference_adapter(root,inputs)
    rows = inputs["rows"]
    simultaneous = [r for r in rows if r["status"] == "AVAILABLE" and r["K"] >= 2 and r["m"] >= 2]
    counts = Counter(r["query"]["symbol"] for r in simultaneous)
    gate = inputs["protocol"]["development"]["support_gate"]
    support = len(simultaneous) >= gate["simultaneous_points_min"] and all(counts[s] >= gate["simultaneous_each_symbol_min"] for s in inputs["protocol"]["decision"]["symbol_order"])
    if not support:raise ValueError("INSUFFICIENT_CONTEXT_NO_API")
    points = []
    for number,row in enumerate(rows):
        check()
        query = row["query"]
        point = adapter.prepare(query["symbol"],query["as_of_date"])
        binding = {"run_signature":content_hash(inputs["identity"]),"point_id":query["episode_id"],
                   "source_sha256":content_hash(point.source_provenance)}
        path = work/query["episode_id"]
        shared,stages = shared_fixture(point,path/"upstream.json",binding)
        evidence,a_reference = point_request(point,deepcopy(shared),index,"A_tp_pool")
        branches = student.prepare(row,a_reference=a_reference)
        order = ["Original",*VARIANTS[1:][number%5:],*VARIANTS[1:][:number%5]]
        session = DecisionSession(path/"decisions.json",{**binding,"shared_sha256":content_hash(shared),"repeat_index":0})
        value = session.run(deepcopy(shared),{k:branches[k] for k in VARIANTS},order,inputs["protocol"],OfflineDecisionFixture())
        saved = value["branches"]
        points.append({"point_id":query["episode_id"],"status":row["status"],"reasons":list(row["reasons"]),
            "K":row["K"],"m":row["m"],"upstream_stages":stages,"shared_sha256":content_hash(shared),"order":order,
            "variants":branches,"a_reference_evidence_sha256":content_hash(evidence),
            "canonical_requests":{k:v["request"] for k,v in saved.items()},
            "fixture_decisions":{k:v["decision"] for k,v in saved.items()},
            "shared_off":{k:v["shared_off_from"] for k,v in saved.items()}})
        print(f"Dry-run {number+1}/60: {query['episode_id']}, K={row['K']}, m={row['m']}; không LLM/API.",flush=True)
    return {"identity":inputs["identity"],"status":"PASS","scope":"OFFLINE_CONTRACT_NO_LLM",
            "support":{"simultaneous":len(simultaneous),"by_symbol":dict(counts),"gate":"PASS",
                       "available":sum(r["status"] == "AVAILABLE" for r in rows),"unavailable":sum(r["status"] != "AVAILABLE" for r in rows)},
            "points":points,"common_instruction_sha256":content_hash(COMMON_INSTRUCTION),
            "max_prefix_chars":max(len(v["prefix"]) for p in points for name,v in p["variants"].items() if name in VARIANTS),
            "max_prompt_chars":max(len(q["messages"][0]["content"]) for p in points for q in p["canonical_requests"].values()),
            "real_api_calls":0,"llm_semantic_behavior":"NOT_RUN_BEFORE_RELEASE",
            "development_allowed":False,"decision_calls_allowed":False}


def semantic_episode(template:dict[str,Any],data:dict[str,Any])->dict[str,Any]:
    """Fixture can thiệp nhãn/vector trên schema PIT mẫu; không phải outcome thị trường mới."""
    result = deepcopy(template)
    result.pop("membership_sha256",None)
    result["reasons"] = ["SEMANTIC_FIXTURE_NOT_MARKET_OUTCOME"]
    tasks = []
    for old,task in zip(template["prior"],data["prior"]):
        value = deepcopy(old)
        value["observations"] = value["observations"][:len(task["observations"])]
        for row,new in zip(value["observations"],task["observations"]):row.update(y=new["y"],r_net=.01 if new["y"] else -.01,model_vector=list(new["x"]))
        value["selected_by_distance_ids"] = [r["episode_id"] for r in value["observations"]]
        tasks.append(value)
    result["prior"],result["K"] = tasks,len(tasks)
    result["target"] = result["target"][:len(data["target"]["observations"])]
    for row,new in zip(result["target"],data["target"]["observations"]):row.update(y=new["y"],r_net=.01 if new["y"] else -.01,model_vector=list(new["x"]))
    result["m"] = len(result["target"])
    result["query"]["model_vector"] = list(data["query"]["x"])
    return result


def probe_result(root:Path,inputs:dict[str,Any],student:StudentAdapter,check:Any,*,dry:dict[str,Any]|None=None)->dict[str,Any]:
    """Đúng24 ID đã đăng ký: token/prefix/PIT/ngữ nghĩa kinh tế, không đo reasoning LLM."""
    fixtures = read_json(root/"docs/plan/week10/protocol_fixtures_v1.json")
    ids = fixtures["semantic_probe_ids"]
    template = next(resolve_episode(r,inputs["context"]) for r in inputs["rows"] if r["K"] == 3 and r["m"] == 8 and all(len(t["observations"]) == 8 for t in r["prior"]))
    teacher = BetaBernoulliTeacher(read_envelope(root/TEACHER_OUTPUT/"teacher_fit.json",TEACHER_VERSION)["pi"])
    shared = {"stock_name":template["query"]["symbol"],"as_of_date":template["query"]["as_of_date"],
              "is_backtest":True,"time_frame":"1d","language":"vi",**{k:"Fixture offline: không suy luận LLM." for k in REPORT_FIELDS}}
    results = []
    for identifier in ids:
        check()
        group,num = identifier.rsplit("-",1)
        i = int(num)-1
        data = fixture_input([[1,1]],[1,1])
        alternative = None
        expected_reject = False
        diagnostic = {}
        if group == "prior_swap_fixed_target":
            data = fixture_input([[0,8]]*(1+i%3),[(0,0),(1,0),(0,1),(1,1)][i])
            alternative = deepcopy(data)
            for task in alternative["prior"]:
                for row in task["observations"]:row["y"] = 1
            assert data["target"] == alternative["target"] and data["query"] == alternative["query"]
        elif group == "target_swap_fixed_prior":
            data = fixture_input([[1,1],[1,1]],[0,i+1])
            alternative = deepcopy(data)
            for row in alternative["target"]["observations"]:row["y"] = 1
            assert data["prior"] == alternative["prior"] and data["query"] == alternative["query"]
        elif group == "cold_start":
            k,m = [(0,0),(0,1),(1,0),(3,0)][i]
            data = fixture_input([[1,1]]*k,[m,0])
        elif group == "conflicting_tasks":data = fixture_input([[0,2+i],[8,0]],[(1,0),(2,0),(0,1),(0,2)][i])
        elif group == "negative_net_after_costs":
            net = float(compute_round_trip_net_return(100.,100.+i*.1,fee=.0025,slippage=.001))
            if net >= 0:raise ValueError("Fixture âm sau phí không đúng kinh tế engine")
            diagnostic = {"historical_fixture_r_net":net,"historical_fixture_y":int(net > 0)}
            data = fixture_input([[0,2]],[0,2])
        elif group == "missing_or_extreme_feature":
            if i == 0:
                missing = next(r for r in inputs["rows"] if r["status"] != "AVAILABLE")
                source_dry = read_envelope(root/OUTPUT/"dry_run.json",DRY_VERSION) if dry is None else dry
                ref = next(p["variants"]["A_reference"]["a_reference"] for p in source_dry["points"] if p["point_id"] == missing["query"]["episode_id"])
                prepared = student.prepare(missing,a_reference=ref)
                if (any(prepared[k]["prefix"] or prepared[k]["probability"] is not None for k in ("Plain_ICL","Full_MT_BICL","No_target","Stats_only"))
                        or prepared["Numeric_only"]["action"] != "CASH"):raise ValueError("Missing query không tắt context đúng hợp đồng")
                results.append({"id":identifier,"status":"PASS","contract":"MISSING_QUERY_CONTEXT_OFF",
                                "prefix":"","student_forward":False,"numeric_action":"CASH","reason":"QUERY_FEATURE_UNAVAILABLE"})
                continue
            data["query"]["x"] = [4.,-4.,.25,.75] if i == 1 else [float("nan") if i == 2 else float("inf"),0.,0.,0.]
            expected_reject = i >= 2
        else:raise ValueError("Probe group không đúng đăng ký")
        if expected_reject:
            try:student.predict_input(data)
            except (ValueError,AssertionError):
                results.append({"id":identifier,"status":"PASS","contract":"NONFINITE_REJECTED_BEFORE_FORWARD","student_forward":False})
                continue
            raise ValueError("Probe vector không hữu hạn không bị từ chối")
        p = student.predict_input(data)
        ep = semantic_episode(template,data)
        projected = project_episode(ep,probability=p)
        prompt = build_prompt(shared,projected["prefix"])
        if group == "negative_net_after_costs":
            lines = [v for v in projected["prefix"].splitlines() if v.startswith(("P1:","T:"))]
            if sum(v.count(">0") for v in lines) != 4 or any(">1" in v for v in lines):raise ValueError("Projection làm mất nhãn âm sau phí")
        if group == "missing_or_extreme_feature" and "Q:(8,-8,0,2)" not in projected["prefix"]:raise ValueError("Lượng tử hóa không ties-to-even")
        q = teacher.predict(data)
        diagnostic.update(student_p=p,teacher_p=q["probability"],teacher_pooled_p=teacher.predict(data,pooled=True)["probability"])
        if alternative is not None:
            diagnostic.update(alternative_student_p=student.predict_input(alternative),alternative_teacher_p=teacher.predict(alternative)["probability"])
        results.append({"id":identifier,"status":"PASS","contract":group,"input":data,
                        "diagnostic":diagnostic,"projection":projected,"prompt":prompt,
                        "scope":"SYNTHETIC_INTERVENTION_NOT_MARKET_DATA_NO_EXTRA_MECHANISM_THRESHOLD"})
    if len(ids) != 24 or [r["id"] for r in results] != ids or any(r["status"] != "PASS" for r in results):
        raise ValueError("Thiếu/sai semantic probe đã đăng ký")
    return {"identity":inputs["identity"],"status":"PASS","scope":"OFFLINE_SEMANTIC_CONTRACT_ONLY",
            "probes":results,"real_api_calls":0,"llm_semantic_behavior":"NOT_RUN_BEFORE_RELEASE",
            "development_allowed":False,"decision_calls_allowed":False}


def run_stage(root:Path,inputs:dict[str,Any],name:str)->dict[str,Any]:
    """Artifact immutable; mỗi stage dùng budget cũ, không mở quota/API hoặc train."""
    if name not in ("dry-run","probes"):raise ValueError("Task tích hợp chỉ cho dry-run/probes offline")
    version = DRY_VERSION if name == "dry-run" else PROBE_VERSION
    filename = "dry_run.json" if name == "dry-run" else "semantic_probes.json"
    path = root/OUTPUT/filename
    if path.exists():
        value = read_envelope(path,version)
        if value["identity"] != inputs["identity"]:raise ValueError("Receipt integration khác nguồn/mã")
        return value
    with ActiveBudget(root/NAMESPACE/"active_budget_v2.json",inputs["budget_identity"]) as budget:
        student = StudentAdapter(root,inputs)
        result = dry_result(root,inputs,student,root/OUTPUT/"dry_points",budget.check) if name == "dry-run" else probe_result(root,inputs,student,budget.check)
        budget.check()
        write_envelope(path,version,result,immutable=True)
        return result


def verify(root:Path,inputs:dict[str,Any],*,replay:bool)->dict[str,Any]:
    """Cold replay offline so p/prompt/request/schema/fixture output; proof không là release W10-14."""
    directory = root/OUTPUT
    dry = read_envelope(directory/"dry_run.json",DRY_VERSION)
    probes = read_envelope(directory/"semantic_probes.json",PROBE_VERSION)
    if any(v["identity"] != inputs["identity"] or v["status"] != "PASS" or v["real_api_calls"] != 0
           or v["development_allowed"] or v["decision_calls_allowed"] for v in (dry,probes)):
        raise ValueError("Receipt offline integration sai binding/gate")
    if [p["point_id"] for p in dry["points"]] != inputs["identity"]["point_ids"] or len(probes["probes"]) != 24:
        raise ValueError("Receipt thiếu point/probe đã đăng ký")
    journals = {}
    for p in dry["points"]:
        path = directory/"dry_points"/p["point_id"]
        raw = read_envelope(path/"decisions.json",JOURNAL_VERSION)
        if (raw["binding"]["point_id"] != p["point_id"] or raw["binding"]["shared_sha256"] != p["shared_sha256"]
                or raw["binding"]["run_signature"] != content_hash(inputs["identity"]) or raw["binding"]["repeat_index"] != 0
                or set(raw["branches"]) != set(VARIANTS)):raise ValueError("Journal paired khác point/shared/nhánh")
        for name,value in raw["branches"].items():
            if (value["status"] != "complete" or value["request"] != p["canonical_requests"][name]
                    or value["canonical_sha256"] != content_hash(value["request"])
                    or value["decision"] != p["fixture_decisions"][name] or value["shared_off_from"] != p["shared_off"][name]):
                raise ValueError("Journal khác request/output durable")
        binding = {k:raw["binding"][k] for k in ("run_signature","point_id","source_sha256")}
        upstream = StageJournal(path/"upstream.json",binding)
        if set(upstream.document["nodes"]) != {"indicator","pattern","trend","full"} or any(len(n["attempts"]) != 1 or n["attempts"][0]["status"] != "complete" for n in upstream.document["nodes"].values()):
            raise ValueError("Upstream journal không đúng một lần/stage")
        for file in (path/"decisions.json",path/"upstream.json"):journals[file.relative_to(directory).as_posix()] = file_hash(file)
    proof = {"identity":inputs["identity"],"status":"OFFLINE_INTEGRATION_REPLAY_MATCH",
             "dry_run_sha256":file_hash(directory/"dry_run.json"),"semantic_probes_sha256":file_hash(directory/"semantic_probes.json"),
             "journals_sha256":journals,"points":60,"probes":24,"real_api_calls":0,"development_allowed":False,"decision_calls_allowed":False}
    if replay:
        with ActiveBudget(root/NAMESPACE/"active_budget_v2.json",inputs["budget_identity"]) as budget:
            student = StudentAdapter(root,inputs)
            with TemporaryDirectory(prefix="integration-replay-") as temporary:
                if dry_result(root,inputs,student,Path(temporary),budget.check) != dry:raise ValueError("Dry-run khác cold replay")
            if probe_result(root,inputs,student,budget.check) != probes:raise ValueError("Semantic probe khác cold replay")
            budget.check()
            write_envelope(directory/"verification.json",VERIFY_VERSION,proof,immutable=True)
    if read_envelope(directory/"verification.json",VERIFY_VERSION) != proof:raise ValueError("Proof integration chưa đúng: chạy verify --replay")
    return proof
