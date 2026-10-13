"""Oracle số học độc lập cho đề cử development và artifact bất biến."""

from copy import deepcopy
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from core.backtest_engine import PRIOR_BRANCH_MODES
from core.candidate_selection import (GATES, ORDER, PLANNED, evaluate_selection, read_selection,
    read_technical_gates, selection_artifact, write_selection)
from core.paired_candidate_report import paired_candidate_report
from core.research_cohort import read_envelope, save_envelope
from test_paired_candidate_report import report_fixture


def oracle_report() -> dict:
    """60 slot tổng hợp; chỉ C0 exposed và có ΔR=(4,2,1,−1), ΔMDD=(5,1,1,1)."""
    matrix = [*PRIOR_BRANCH_MODES, *ORDER]
    stocks = {}
    for index,symbol in enumerate(PLANNED):
        points = []
        for position in range(PLANNED[symbol]):
            day = (date(2023,1,2)+timedelta(days=7*position)).isoformat()
            points.append({"point_id":f"{symbol}-{day}", "as_of_date":day,
                "branch_status":{name:"complete" for name in matrix},
                "prior":{name:{"prefix_sha256":"a"*64, "visible_metric_ids":["win_rate_long"]
                    if name == "C0" and position < (1,1,2,2)[index] else [], "visible_example_ids":[],
                    "retrieved_ids":["retrieved-only"]} for name in matrix}})
        stocks[symbol] = {"points":points,
            "global_common_support":{"point_ids":[p["point_id"] for p in points],"count":len(points)},
            "coverage":{name:{"prior_visible_count":(1,1,2,2)[index] if name == "C0" else 0} for name in ORDER},
            "metrics":{name:{"balanced_accuracy":None,"hit_rate_long":None,
                "account_metrics":{"total_return_pct":(4,2,1,-1)[index] if name == "C0" else 0.,
                    "max_drawdown_pct":10.+((5,1,1,1)[index] if name == "C0" else 0.)}} for name in matrix}}
    return {"report_version":"research_report_v5", "split":"fixture", "matrix":matrix,
        "stocks":stocks,"cohort_id":"selection-oracle", "primary_status":"COMPLETE",
        "selection_evidence_status":"NOT_APPLICABLE", "binding":{"execution_mode":"offline_fixture",
            "code_sha256":{},"runtime":{},"checkpoint_sha256":{"point.json":"a"},"sources":{"bank.json":"b"}}}


def configure(report: dict, name: str, *, returns: tuple = (1.5,)*4,
              mdd: tuple = (1.,)*4, exposure: tuple = (1,1,2,2)) -> None:
    """Đổi input oracle, không gọi economic engine hoặc chạm dữ liệu nghiên cứu thật."""
    for index,symbol in enumerate(PLANNED):
        stock = report["stocks"][symbol]
        stock["metrics"][name]["account_metrics"] = {"total_return_pct":returns[index],
            "max_drawdown_pct":10.+mdd[index]}
        stock["coverage"][name]["prior_visible_count"] = exposure[index]
        for position,point in enumerate(stock["points"]):
            point["prior"][name]["visible_metric_ids"] = ["win_rate_long"] if position < exposure[index] else []


def gates_fixture(root: Path, binding: dict) -> Path:
    """Receipt tổng hợp có log đọc được; chỉ phục vụ artifact fixture bị BLOCKED."""
    texts = {"compileall":"\n".join(f"Listing '{part}'..." for part in
        ("agents","core","data_manager","scripts","tests","utils")),
        "unit":"Ran 10 tests in 1.0s\n\nOK\n", "leakage":"Ran 3 tests in 0.2s\n\nOK\n",
        "e2e":"[PASS] ALL PIPELINE CHECKS SUCCESSFUL IN 1.0s\n"}
    checks = {}
    for name in GATES:
        path = root/f"{name}.log"
        path.write_text(texts[name],encoding="utf-8")
        checks[name] = {"status":"PASS","exit_code":0,
            "log":{"path":path.name,"sha256":hashlib.sha256(path.read_bytes()).hexdigest()}}
    path = root/"gates.json"
    save_envelope(path,{"gate_version":"research_technical_gates_v1", "code_sha256":binding["code_sha256"],
        "runtime":binding["runtime"],"checks":checks})
    return path


class CandidateSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.report = oracle_report()

    def test_exact_exposure_and_mdd_boundaries_promote(self) -> None:
        result = evaluate_selection(self.report,gates_passed=True)
        self.assertEqual((result["nomination_status"],result["research_candidate"],result["deployment_choice"]),
            ("PROMOTED","C0","C0"))
        candidate = result["candidates"]["C0"]
        self.assertEqual((candidate["delta_return_pp"],candidate["mean_delta_mdd_pp"],candidate["max_delta_mdd_pp"]),(1.5,2.,5.))
        self.assertEqual((candidate["visible_count"],candidate["visibility_denominator"]),(6,60))
        self.assertEqual(candidate["positive_symbol_count"],3)
        json.dumps(result,allow_nan=False)

    def test_zero_return_and_only_two_positive_symbols_do_not_promote(self) -> None:
        for returns in ((1,1,1,-3),(4,2,0,-1)):
            configure(self.report,"C0",returns=returns)
            result = evaluate_selection(self.report,gates_passed=True)
            self.assertEqual(result["nomination_status"],"NOT_PROMOTED")
            self.assertEqual(result["research_candidate"],"C0")
            self.assertEqual(result["deployment_choice"],"original")

    def test_mdd_above_each_boundary_is_not_rounded(self) -> None:
        for mdd in ((5,1,1,1.0004),(5.0004,0,0,0)):
            configure(self.report,"C0",mdd=mdd)
            result = evaluate_selection(self.report,gates_passed=True)
            self.assertEqual(result["nomination_status"],"NOT_PROMOTED")
            self.assertTrue(result["candidates"]["C0"]["eligible"])

    def test_exposure_requires_total_and_every_symbol_and_ignores_retrieval(self) -> None:
        for exposure,reason in (((1,1,1,2),"INSUFFICIENT_EXPOSURE"),((0,2,2,2),"INSUFFICIENT_EXPOSURE"),
                               ((0,0,0,0),"NO_EXPOSURE")):
            configure(self.report,"C0",exposure=exposure)
            result = evaluate_selection(self.report,gates_passed=True)
            self.assertEqual(result["nomination_status"],"BLOCKED")
            self.assertIsNone(result["research_candidate"])
            self.assertIn(reason,result["candidates"]["C0"]["eligibility_reasons"])

    def test_missing_one_unrelated_branch_blocks_primary_despite_pairwise(self) -> None:
        stock = self.report["stocks"]["FPT"]
        stock["points"][-1]["branch_status"]["random"] = "unknown"
        stock["global_common_support"]["point_ids"].pop()
        stock["global_common_support"]["count"] -= 1
        stock["pairwise_support"] = {"C0__original":{"count":12}}
        result = evaluate_selection(self.report,gates_passed=True)
        self.assertEqual(result["paired_count"],59)
        self.assertEqual(result["nomination_status"],"BLOCKED")
        self.assertIsNone(result["candidates"]["C0"]["delta_return_pp"])

    def test_missing_gates_blocks_even_positive_eligible_metrics(self) -> None:
        result = evaluate_selection(self.report,gates_passed=False)
        self.assertEqual(result["nomination_status"],"BLOCKED")
        self.assertIn("TECHNICAL_GATES_NOT_PASS",result["candidates"]["C0"]["eligibility_reasons"])

    def test_null_balanced_accuracy_and_hit_rate_do_not_exclude(self) -> None:
        self.assertIsNone(self.report["stocks"]["FPT"]["metrics"]["C0"]["balanced_accuracy"])
        self.assertTrue(evaluate_selection(self.report,gates_passed=True)["candidates"]["C0"]["eligible"])

    def test_total_sixty_cannot_replace_locked_counts_per_symbol(self) -> None:
        fpt, mwg = (self.report["stocks"][symbol] for symbol in ("FPT","MWG"))
        fpt["points"].pop()
        fpt["global_common_support"]["point_ids"].pop()
        fpt["global_common_support"]["count"] -= 1
        extra = deepcopy(mwg["points"][-1])
        extra.update(point_id="MWG-2023-05-01",as_of_date="2023-05-01")
        mwg["points"].append(extra)
        mwg["global_common_support"]["point_ids"].append(extra["point_id"])
        mwg["global_common_support"]["count"] += 1
        result = evaluate_selection(self.report,gates_passed=True)
        self.assertEqual(result["paired_count"],60)
        self.assertEqual(result["nomination_status"],"BLOCKED")
        self.assertFalse(result["candidates"]["C0"]["conditions"]["primary_complete"])

    def test_tie_uses_mdd_then_fixed_ablation_order(self) -> None:
        configure(self.report,"C0",mdd=(2.,)*4)
        configure(self.report,"C1",returns=(1.5000000005,)*4,mdd=(1.,)*4)
        self.assertEqual(evaluate_selection(self.report,gates_passed=True)["research_candidate"],"C1")
        self.report = oracle_report()
        configure(self.report,"C0",exposure=(0,)*4)
        for name in ("C3_stats_only","C3_examples_only"):
            configure(self.report,name)
        self.assertEqual(evaluate_selection(self.report,gates_passed=True)["research_candidate"],"C3_stats_only")

    def test_tie_is_anchored_at_maximum_not_chained(self) -> None:
        for name,value,mdd in (("C0",1.5,0),("C1",1.5000000005,0),("C2",1.500000002,2)):
            configure(self.report,name,returns=(value,)*4,mdd=(mdd,)*4)
        result = evaluate_selection(self.report,gates_passed=True)
        self.assertEqual(result["research_candidate"],"C2")
        self.assertEqual(result["promote_ranking"]["tie_groups"][0]["candidate_ids"],["C2"])

    def test_exact_tie_tolerance_and_no_mdd_tolerance(self) -> None:
        configure(self.report,"C0",returns=(0.,)*4,mdd=(0.,)*4)
        configure(self.report,"C1",returns=(1e-9,)*4,mdd=(2.0000000001,)*4)
        result = evaluate_selection(self.report,gates_passed=True)
        self.assertEqual(result["eligible_ranking"]["tie_groups"][0]["candidate_ids"],["C0","C1"])
        self.assertEqual(result["nomination_status"],"NOT_PROMOTED")
        self.assertEqual(result["research_candidate"],"C0")

    def test_no_promoted_candidate_keeps_best_research_and_original_deployment(self) -> None:
        configure(self.report,"C0",returns=(-.1,)*4,mdd=(0.,)*4)
        configure(self.report,"C1",returns=(-.2,)*4,mdd=(0.,)*4)
        result = evaluate_selection(self.report,gates_passed=True)
        self.assertEqual((result["nomination_status"],result["research_candidate"],result["deployment_choice"]),
            ("NOT_PROMOTED","C0","original"))
        configure(self.report,"C0",returns=(10.,)*4,mdd=(3.,)*4)
        configure(self.report,"C1")
        self.assertEqual(evaluate_selection(self.report,gates_passed=True)["research_candidate"],"C1")

    def test_null_nonfinite_or_bool_is_never_ranked_as_zero(self) -> None:
        for value in (None,float("nan"),float("inf"),True):
            changed = deepcopy(self.report)
            changed["stocks"]["FPT"]["metrics"]["C0"]["account_metrics"]["total_return_pct"] = value
            if value is None:
                result = evaluate_selection(changed,gates_passed=True)
                self.assertFalse(result["candidates"]["C0"]["eligible"])
                self.assertIsNone(result["candidates"]["C0"]["delta_return_pp"])
            else:
                with self.assertRaises(ValueError):
                    evaluate_selection(changed,gates_passed=True)

    def test_cached_delta_and_exposure_claim_cannot_replace_recalculation(self) -> None:
        self.report["candidate_delta_return_pp"] = {name:999. for name in ORDER}
        self.assertEqual(evaluate_selection(self.report,gates_passed=True)["candidates"]["C0"]["delta_return_pp"],1.5)
        self.report["stocks"]["FPT"]["coverage"]["C0"]["prior_visible_count"] = 12
        with self.assertRaises(ValueError):
            evaluate_selection(self.report,gates_passed=True)

    def test_fixture_and_mock_never_become_actual_nomination(self) -> None:
        for split,mode in (("fixture","research"),("development_2023","offline_fixture")):
            changed = deepcopy(self.report)
            changed["split"], changed["binding"]["execution_mode"] = split,mode
            changed["selection_evidence_status"] = "DEVELOPMENT"
            artifact = selection_artifact(changed,{"status":"PASS"},report_file_sha256="a"*64)
            self.assertEqual(artifact["nomination_status"],"BLOCKED")
            self.assertIsNone(artifact["research_candidate"])
            self.assertEqual(artifact["fixture_protocol_result"]["nomination_status"],"PROMOTED")

    def test_development_artifact_binds_rules_and_all_report_sources(self) -> None:
        self.report.update(split="development_2023",selection_evidence_status="DEVELOPMENT")
        self.report["binding"]["execution_mode"] = "research"
        artifact = selection_artifact(self.report,{"status":"PASS"},report_file_sha256="c"*64)
        self.assertEqual(artifact["nomination_status"],"PROMOTED")
        self.assertEqual(artifact["research_candidate"],"C0")
        self.assertIsNone(artifact["fixture_protocol_result"])
        for key in self.report["binding"]:
            self.assertEqual(artifact["binding"][key],self.report["binding"][key])
        self.assertEqual(artifact["binding"]["report_file_sha256"],"c"*64)

    def test_gate_receipt_requires_all_logs_current_code_and_no_skip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = gates_fixture(root,self.report["binding"])
            receipt = read_envelope(path)
            self.assertEqual(read_technical_gates(path,self.report["binding"])["status"],"PASS")
            for mutate in (lambda r:r["code_sha256"].update(other="changed"),
                           lambda r:r["checks"]["unit"].update(exit_code=1),
                           lambda r:r["checks"]["unit"].update(log=None)):
                changed = deepcopy(receipt)
                mutate(changed)
                save_envelope(path,changed)
                with self.assertRaises(ValueError):
                    read_technical_gates(path,self.report["binding"])
            save_envelope(path,receipt)
            failed = deepcopy(receipt)
            failed["checks"]["unit"].update(status="FAIL",exit_code=1)
            save_envelope(path,failed)
            self.assertEqual(read_technical_gates(path,self.report["binding"])["status"],"NOT_PASS")
            save_envelope(path,receipt)
            (root/"unit.log").write_text("Ran 10 tests in 1.0s\n\nOK (skipped=1)\n",encoding="utf-8")
            receipt["checks"]["unit"]["log"]["sha256"] = hashlib.sha256((root/"unit.log").read_bytes()).hexdigest()
            save_envelope(path,receipt)
            with self.assertRaises(ValueError):
                read_technical_gates(path,self.report["binding"])
            self.assertEqual(read_technical_gates(None,self.report["binding"])["status"],"NOT_VERIFIED")

    def test_selection_roundtrip_read_only_write_once_and_semantic_tamper(self) -> None:
        plan,points,binding = report_fixture()
        report = paired_candidate_report(plan,points,binding)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_path,selection_path = root/"report.json",root/"selection.json"
            save_envelope(report_path,report)
            gates = gates_fixture(root,binding)
            expected = write_selection(selection_path,report_path,report,gates_path=gates)
            before = selection_path.read_bytes()
            self.assertEqual(read_selection(selection_path,report_path,report,gates_path=gates),expected)
            self.assertEqual(write_selection(selection_path,report_path,report,gates_path=gates),expected)
            self.assertEqual(selection_path.read_bytes(),before)
            for mutate in (lambda r:r.update(nomination_status="PROMOTED",research_candidate="C0"),
                           lambda r:r["rules"].update(min_visible=0),
                           lambda r:r["candidates"]["C0"].update(eligible=True),
                           lambda r:r["binding"]["checkpoint_sha256"].update(forged="a")):
                changed = deepcopy(expected)
                mutate(changed)
                save_envelope(selection_path,changed)
                with self.assertRaises(ValueError):
                    read_selection(selection_path,report_path,report,gates_path=gates)
                with self.assertRaises(ValueError):
                    write_selection(selection_path,report_path,report,gates_path=gates)
            changed = deepcopy(report)
            changed["stocks"]["FPT"]["metrics"]["C0"]["account_metrics"]["total_return_pct"] = 999.
            save_envelope(report_path,changed)
            with self.assertRaises(ValueError):
                read_selection(selection_path,report_path,report,gates_path=gates)
