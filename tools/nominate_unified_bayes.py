"""Phân tích và khóa nomination U-BICL development từ nguồn thật, hoàn toàn offline."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import math
from pathlib import Path
import sys
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jsonschema import Draft202012Validator

from core.bayesian_memory import read_json
from core.candidate_selection import read_technical_gates
from core.historical_signals import digest
from core.prior_config import copy_prior_json
from core.prior_backtest import canonical_hash
from core.prior_run_lock import PriorRunLock, safe_path
from core.research_cohort import read_envelope
from core.research_input_lock import _write_once
from core.unified_bayes_cohort import preflight
from core.unified_bayes_contracts import MATRIX, SYMBOLS, sha
from core.unified_bayes_memory import OUTPUT as MEMORY_PATH
from core.unified_bayes_readiness import build_assessment, read_assessment
from core.unified_bayes_reports import PAIRS, group, read_report
from core.unified_bayes_source import NAMESPACE, PLAN_PATH, RUN_PATH, SOURCE, load_source
from scripts.prepare_unified_bayes_memory import PROTOCOL, PROTOCOL_SHA
from scripts.run_unified_bayes import LEDGER, authorize, offline_client
from tools.resume_unified_bayes import READINESS, VALIDATION, RECEIPT_NAME, ResumedCohort

VERSION = "unified_bic_development_nomination_v1"
PROTOCOL_FILE_SHA = "9cf64755a5db462ba189cca4fd363e06399dc71d56f415f2fe89d4aaafabad7d"
SCHEMA = ROOT / "tools/unified_bayes_nomination_v1.schema.json"
OUTPUT = NAMESPACE / "development/nomination/selection.json"
CODE = ("tools/nominate_unified_bayes.py", "tools/test_nominate_unified_bayes.py",
        "tools/unified_bayes_nomination_v1.schema.json")
PLANNED = {"FPT": 12, "MWG": 16, "VCB": 16, "VNM": 16}
CONTRASTS = tuple(a + "__" + b for a, b in PAIRS)
VERIFICATIONS = ("cold_source_runtime", "technical_gates", "primary_three_repeats", "readiness_assessment", "resume_adapter")
RULES = {"candidate": "U_full", "required_common_support": 60, "all_branches_required": True,
    "finite_metrics": True, "require_four_gates_current_source_runtime": True,
    "require_primary_and_three_repeat_verification": True, "prior_visible_min": 30,
    "prior_visible_per_symbol_min": 5, "examples_visible_min": 12, "examples_visible_per_symbol_min": 2,
    "mean_delta_return_original": "> 0", "positive_symbols_min": 3, "mean_delta_return_A": ">= 0",
    "mean_delta_mdd_max_pp": 2, "max_delta_mdd_max_pp": 5, "otherwise": "STOP_NO_CONFIRMATION_RELEASE"}


def locked_protocol() -> dict[str, Any]:
    """Giữ đúng byte protocol và rule trước outcome, không đọc giá hoặc kết quả 2025."""
    path = ROOT / PROTOCOL
    if sha(path) != PROTOCOL_FILE_SHA:
        raise ValueError("Protocol nomination khác byte đã khóa")
    protocol = read_json(path)
    if canonical_hash(protocol) != PROTOCOL_SHA or digest(protocol["nomination"]) != digest(RULES):
        raise ValueError("Ngưỡng nomination khác rule đã đăng ký")
    return protocol


def finite(value: Any) -> bool:
    """Null là thiếu metric; bool và số không hữu hạn không được dùng làm lợi nhuận."""
    if value is None:
        return False
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("Metric nomination phải là số hữu hạn, không phải bool")
    return True


def mean_four(values: dict[str, Any]) -> float | None:
    """Mẫu số cố định bốn mã; nhóm thiếu mã trả null, không điền 0 hoặc đổi estimand."""
    if set(values) != set(SYMBOLS):
        raise ValueError("Metric thiếu schema bốn mã")
    return float(sum(values.values()) / 4) if all(finite(v) for v in values.values()) else None


def compact_stock(stock: dict[str, Any]) -> dict[str, Any]:
    """Giữ mẫu số, tài khoản, accuracy/LONG-CASH và contrast; bỏ lặp equity curve lớn."""
    metrics = {}
    for name in MATRIX:
        row, account = stock["metrics"][name], stock["metrics"][name]["account_metrics"]
        metrics[name] = {"return_pct": None if account is None else account["total_return_pct"],
            "mdd_pct": None if account is None else account["max_drawdown_pct"],
            **{key: deepcopy(row[key]) for key in ("sample_count", "accuracy", "balanced_accuracy",
                "balanced_accuracy_reason", "long_count", "cash_count", "hit_rate_long", "hit_rate_reason")}}
    return {"support": deepcopy(stock["global_common_support"]), "metrics": metrics,
        "coverage": deepcopy(stock["coverage"]), "contrasts": {key: {field: deepcopy(row[field])
            for field in ("count", "delta_return_pp", "delta_mdd_pp", "disagreements")}
            for key, row in stock["pairs"].items()}}


def summarize(stocks: dict[str, Any]) -> dict[str, Any]:
    """Tổng hợp đều bốn tài khoản, cả nhóm không có support vẫn giữ đủ bốn mã."""
    result = {symbol: compact_stock(stocks[symbol]) for symbol in SYMBOLS}
    return {"point_count": sum(row["support"]["count"] for row in result.values()), "stocks": result,
        "equal_weight_delta_return_pp": {key: mean_four({s: result[s]["contrasts"][key]["delta_return_pp"]
                                                       for s in SYMBOLS}) for key in CONTRASTS}}


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Tái dùng nguyên metric engine cho subgroup; không cộng các cycle return."""
    return summarize({s: group([row for row in rows if row["point_id"].startswith(s + "-")]) for s in SYMBOLS})


def evaluate_rules(primary: dict[str, Any], coverage: dict[str, Any], verification: dict[str, Any]) -> dict[str, Any]:
    """Chỉ U_full, so sánh strict trên precision gốc; repeat không tham gia lựa chọn."""
    stocks = primary["stocks"]
    complete = all(stocks[s]["support"]["planned"] == stocks[s]["support"]["count"] == PLANNED[s]
                   and len(set(stocks[s]["support"]["point_ids"])) == stocks[s]["support"]["count"]
                   and len(stocks[s]["support"]["point_ids"]) == stocks[s]["support"]["count"]
                   and not stocks[s]["support"]["excluded"] for s in SYMBOLS)
    finite_metrics = all([finite(stocks[s]["metrics"][name][key]) for s in SYMBOLS
                         for name in MATRIX for key in ("return_pct", "mdd_pct")])
    if any(finite(stocks[s]["metrics"][name]["mdd_pct"]) and stocks[s]["metrics"][name]["mdd_pct"] < 0
           for s in SYMBOLS for name in MATRIX):
        raise ValueError("MDD tài khoản không được âm")
    returns, reference, mdd = {}, {}, {}
    for s in SYMBOLS:
        metrics = stocks[s]["metrics"]
        for values, base, field in ((returns, "Original", "return_pct"), (reference, "A_reference", "return_pct"),
                                    (mdd, "Original", "mdd_pct")):
            a, b = metrics["U_full"][field], metrics[base][field]
            values[s] = float(a-b) if finite(a) and finite(b) else None
    d, d_a, mean_mdd = mean_four(returns), mean_four(reference), mean_four(mdd)
    max_mdd = float(max(mdd.values())) if all(finite(v) for v in mdd.values()) else None
    positive = sum(v > 0 for v in returns.values() if finite(v))
    checks = {"source_runtime_receipts_verified": set(verification) == set(VERIFICATIONS) and all(
                  verification[key] == "PASS" for key in VERIFICATIONS),
        "primary_common_support_60": complete and primary["point_count"] == 60,
        "finite_account_return_mdd": finite_metrics,
        "prior_visible": coverage["prior_visible"]["count"] >= RULES["prior_visible_min"] and all(
            coverage["prior_visible"]["by_symbol"][s] >= RULES["prior_visible_per_symbol_min"] for s in SYMBOLS),
        "examples_visible": coverage["examples_visible"]["count"] >= RULES["examples_visible_min"] and all(
            coverage["examples_visible"]["by_symbol"][s] >= RULES["examples_visible_per_symbol_min"] for s in SYMBOLS),
        "mean_delta_return_original_positive": d is not None and d > 0,
        "at_least_three_positive_symbols": positive >= RULES["positive_symbols_min"],
        "mean_delta_return_reference_nonnegative": d_a is not None and d_a >= 0,
        "mean_delta_mdd_within_limit": mean_mdd is not None and mean_mdd <= RULES["mean_delta_mdd_max_pp"],
        "max_delta_mdd_within_limit": max_mdd is not None and max_mdd <= RULES["max_delta_mdd_max_pp"]}
    eligibility = list(checks)[:5]
    status = "INSUFFICIENT_EVIDENCE" if not all(checks[k] for k in eligibility) else (
        "NOMINATED" if all(checks.values()) else "NOT_NOMINATED")
    return {"status": status, "research_candidate": "U_full" if status == "NOMINATED" else None,
        "nomination_allowed": status == "NOMINATED", "confirmation_allowed": False,
        "checks": checks, "failed_checks": [key for key, value in checks.items() if not value],
        "delta_return_original_by_symbol_pp": returns, "delta_return_reference_by_symbol_pp": reference,
        "delta_mdd_original_by_symbol_pp": mdd, "mean_delta_return_original_pp": d,
        "mean_delta_return_reference_pp": d_a, "positive_symbols": positive,
        "mean_delta_mdd_pp": mean_mdd, "max_delta_mdd_pp": max_mdd,
        "next_action": "PREPARE_SEPARATE_CONFIRMATION_RELEASE" if status == "NOMINATED" else RULES["otherwise"]}


def describe_analysis(plan: dict[str, Any], report: dict[str, Any], diag: dict[str, Any],
                      verification: dict[str, Any]) -> dict[str, Any]:
    """Báo G/T, task/fallback, nhóm xấu và từng repeat, không bootstrap xác nhận hoặc chọn lượt."""
    rows = report["points"]
    if report["matrix"] != list(MATRIX) or report["split"] != plan["split"]:
        raise ValueError("Report khác ma trận/split nguồn đã khóa")
    for row in rows:
        day = row["point_id"][4:]
        if not day.startswith("2023-") or row["context"]["as_of_date"] != day:
            raise ValueError("Nomination chỉ nhận development 2023, không nhận holdout")
        if row["evaluation"] is not None and not day < row["evaluation"]["entry_date"] <= row["evaluation"]["exit_date"] < "2024-01-01":
            raise ValueError("Cycle nomination vượt biên development")
    primary = [row for row in rows if row["repeat_id"] == 0]
    if ([(r["point_id"], r["repeat_id"]) for r in rows] != [(r["point_id"], r["repeat_id"]) for r in plan["schedule"]]
            or {row["point_id"] for row in primary} != set(plan["requests"])
            or {row["point_id"] for row in diag["points"]} != set(plan["requests"])):
        raise ValueError("Analysis khác cohort/schedule/diagnostics đã khóa")
    coverage = {}
    for field, branch in (("prior_visible", "U_full"), ("examples_visible", "U_examples")):
        counts = {s: sum(row["branches"][branch]["prior_visible"] for row in primary if row["point_id"].startswith(s+"-")) for s in SYMBOLS}
        if any(counts[s] != diag["by_symbol"][s]["branches"][branch]["visible_count"] for s in SYMBOLS):
            raise ValueError("Visibility thực khác diagnostics nguồn trước action")
        coverage[field] = {"count": sum(counts.values()), "denominator": len(primary), "by_symbol": counts}
    two_tasks = {s: diag["by_symbol"][s]["at_least_two_selected_tasks"] for s in SYMBOLS}
    coverage["multi_task"] = {"count": sum(two_tasks.values()), "denominator": len(primary), "by_symbol": two_tasks,
        "claim_gate_pass": sum(two_tasks.values()) >= 12 and all(n >= 2 for n in two_tasks.values())}
    primary_summary = summarize(report["primary"]["stocks"])
    if digest(primary_summary["equal_weight_delta_return_pp"]) != digest(report["primary"]["equal_weight_delta_return_pp"]):
        raise ValueError("D toàn G khác trung bình đều bốn tài khoản")
    diag_by_id = {row["point_id"]: row for row in diag["points"]}
    predicates = {"G_all": lambda r: True, "T_both_ready": lambda r: r["readiness"]["stats"] and r["readiness"]["examples"],
        "stats_only_ready": lambda r: r["readiness"]["stats"] and not r["readiness"]["examples"],
        "examples_only_ready": lambda r: r["readiness"]["examples"] and not r["readiness"]["stats"],
        "prior_off": lambda r: not r["branches"]["U_full"]["prior_visible"],
        "multi_task": lambda r: diag_by_id[r["point_id"]]["selected_task_count"] >= 2}
    strata = {name: primary_summary if name == "G_all" else summarize_rows([r for r in primary if predicate(r)])
              for name, predicate in predicates.items()}
    modes = {name: summarize_rows([r for r in primary if r["readiness"]["context_mode"] == name])
             for name in ("task", "episode_fallback", "off")}
    regimes = {name: summarize({s: report["primary"]["stocks"][s]["regimes"][name] for s in SYMBOLS})
               for name in ("BULL", "BEAR", "CHOPPY", "CONSOLIDATION")}
    quarters = {name: summarize({s: report["primary"]["stocks"][s]["time_groups"][name] for s in SYMBOLS})
                for name in ("Q1", "Q2", "Q3", "Q4")}
    samples = {"0": summarize_rows([r for r in primary if r["point_id"] in plan["repeat_sample"]]),
               **{rid: summarize(stocks) for rid, stocks in report["repeats"]["per_repeat"].items()}}
    additional_mean = {key: float(sum(samples[str(r)]["equal_weight_delta_return_pp"][key] for r in (1, 2, 3))/3)
        if all(samples[str(r)]["equal_weight_delta_return_pp"][key] is not None for r in (1, 2, 3)) else None for key in CONTRASTS}
    by_slot = {(r["point_id"], r["repeat_id"]): r for r in rows}
    versus_primary = {}
    for branch in MATRIX[:-1]:
        pairs = [(by_slot[(pid, 0)]["branches"][branch], by_slot[(pid, rid)]["branches"][branch])
                 for pid in plan["repeat_sample"] for rid in (1, 2, 3)]
        complete = [(a, b) for a, b in pairs if a["status"] == b["status"] == "complete"]
        versus_primary[branch] = {"planned_pairs": len(pairs), "observed_pairs": len(complete),
            "disagreements": sum(a["decision"]["action"] != b["decision"]["action"] for a, b in complete)}
    duplicates = {rid: {**{key: row[key] for key in ("planned", "observed", "disagreements")},
        "by_symbol": {s: {key: row["by_symbol"][s][key] for key in
            ("count", "delta_return_pp", "delta_mdd_pp", "disagreements")} for s in SYMBOLS}}
        for rid, row in report["repeats"]["original_duplicate"].items()}
    return copy_prior_json({"coverage": coverage, "primary": primary_summary, "strata": strata,
        "context_modes": modes, "regimes": regimes, "quarters": quarters,
        "repeat": {"sample": plan["repeat_sample"], "on_locked_sample": samples,
            "mean_additional_repeat_delta_pp": additional_mean, "primary_vs_repeats": versus_primary,
            "between_additional_repeats": deepcopy(report["repeats"]["disagreement"]),
            "original_duplicate": duplicates, "in_primary": False, "vote": False},
        "telemetry": {k: deepcopy(v) for k, v in report["telemetry"].items() if k != "requests"},
        "leave_one_symbol_out": deepcopy(report["primary"]["leave_one_symbol_out"]),
        "diagnostics": {key: deepcopy(diag["overall"][key]) for key in
            ("readiness", "context_modes", "stats_reasons", "examples_reasons", "feature_reasons")},
        "decision": evaluate_rules(primary_summary, coverage, verification),
        "inference": {"scope": "DEVELOPMENT_EXPLORATORY", "confidence_intervals": None,
                      "confirmation_run": False, "provider_determinism_claim": False}})


def validate_artifact(value: dict[str, Any]) -> dict[str, Any]:
    """Schema riêng và JSON native hữu hạn; checksum không thay semantic source verifier."""
    value = copy_prior_json(value)
    errors = list(Draft202012Validator(read_json(SCHEMA)).iter_errors(value))
    if errors:
        raise ValueError(f"Nomination sai schema: {errors[0].json_path}")
    return value


def analysis_identity() -> dict[str, str]:
    """Ghim text LF code/test/schema riêng, ổn định khi Git đổi CRLF trên Windows."""
    return {name: hashlib.sha256((ROOT / name).read_text("utf-8").encode()).hexdigest() for name in CODE}


def guard_binding(hashes: dict[str, str], run: ResumedCohort, analysis_code: dict[str, str] | None = None) -> None:
    """Kiểm lại file, ledger trên đĩa và mọi slot trước khi khóa hoặc xác minh selection."""
    if analysis_code is not None and analysis_identity() != analysis_code:
        raise ValueError("Code/test/schema nomination đổi trong lúc kiểm")
    for name, checksum in hashes.items():
        if sha(safe_path(ROOT, name)) != checksum:
            raise ValueError(f"Nguồn nomination đổi trong lúc kiểm: {name}")
    run.transport.verify_ledger_file()
    run.verify()


@contextmanager
def verified_evidence() -> Iterator[dict[str, Any]]:
    """Tái dựng toàn nguồn/readiness/journal/report bằng kernel đã khóa; không đọc key/2025."""
    protocol = locked_protocol()
    models = read_envelope(ROOT / SOURCE / "plan.json")["inputs"]["signal_config"]["models"]
    inputs = [ROOT / PROTOCOL, PLAN_PATH, RUN_PATH / "report.json", RUN_PATH / "cohort.json",
        RUN_PATH / "authorization.json", RUN_PATH / "preflight.json", RUN_PATH / RECEIPT_NAME,
        RUN_PATH / "journal/identity.json", READINESS, READINESS.parent / "assessment.json",
        VALIDATION / "validation_audit.json", VALIDATION / "technical_gates.json", VALIDATION / "diagnostics.json",
        *(VALIDATION / (name + ".log") for name in ("compileall", "unit", "e2e", "leakage"))]
    hashes = {p.resolve().relative_to(ROOT).as_posix(): sha(p) for p in inputs}
    own_code = analysis_identity()
    with offline_client(models, LEDGER, RUN_PATH / "http_cache", read_usage=True) as llm:
        cohort = load_source(llm)
        plan = cohort.read_plan(PLAN_PATH, llm)
        if cohort.split != "development_2023_exploratory" or len(plan["requests"]) != 60:
            raise ValueError("Nomination thật chỉ nhận cold source development 60 điểm đã khóa")
        assessment = build_assessment(cohort, plan, llm, read_envelope(ROOT / MEMORY_PATH), VALIDATION / "validation_audit.json")
        read_assessment(READINESS.parent / "assessment.json", assessment)
        authorize(plan, VALIDATION / "technical_gates.json", READINESS)
        gates = read_technical_gates(VALIDATION / "technical_gates.json", plan)
        diag = read_envelope(VALIDATION / "diagnostics.json")
        run = ResumedCohort(cohort, plan, llm, RUN_PATH, LEDGER, record=False)
        with PriorRunLock(run.root, run.signature):
            report = run.report()
            read_report(RUN_PATH / "report.json", report)
            preflight(cohort, plan, llm, RUN_PATH, execute=False)
            if report["status"] != "COMPLETE" or report["repeats"]["in_primary"] or report["repeats"]["repeat_ids"] != [1, 2, 3]:
                raise ValueError("Nomination cần primary và ba repeat complete/verify, không trộn primary")
            def guard() -> None:
                """Không công bố với nguồn/code/artifact/usage đổi giữa phân tích và ghi khóa."""
                guard_binding(hashes, run, own_code)
            guard()
            yield {"protocol": protocol, "plan": plan, "report": report, "diagnostics": diag,
                "verification": {"cold_source_runtime": "PASS", "technical_gates": gates["status"],
                    "primary_three_repeats": "PASS", "readiness_assessment": "PASS", "resume_adapter": "PASS"},
                "binding": {"input_file_sha256": hashes, "analysis_code_sha256": own_code,
                    "plan_sha256": digest(plan), "run_signature": run.signature,
                    "checkpoint_payload_sha256": digest(report["binding"]["checkpoint_sha256"]),
                    "source_map_sha256": digest(plan["sources"]), "execution_code_sha256": plan["code_sha256"],
                    "validation_code_sha256": digest(assessment["validation_code_sha256"]), "runtime": plan["runtime"]},
                "guard": guard}
            guard()


def make_artifact(evidence: dict[str, Any]) -> dict[str, Any]:
    """Chỉ gọi sau cold verification; fixture không được khóa thành nomination nghiên cứu thật."""
    if evidence["plan"]["split"] != "development_2023_exploratory":
        raise ValueError("Fixture không được phát hành nomination thật")
    analysis = describe_analysis(evidence["plan"], evidence["report"], evidence["diagnostics"], evidence["verification"])
    return validate_artifact({"selection_version": VERSION, "split": evidence["plan"]["split"],
        "candidate": "U_full", "rules": RULES, "rules_sha256": digest(RULES),
        "binding": deepcopy(evidence["binding"]), "verification": deepcopy(evidence["verification"]),
        "analysis": analysis, "decision": deepcopy(analysis["decision"]),
        "confirmation_allowed": False, "risk_policy": "OFF",
        "limitations": ["Nomination là rule development đã xem, không phải kiểm định thống kê xác nhận.",
            "T/task/fallback và repeat chỉ mô tả; không thay G, vote hoặc chọn response thuận lợi.",
            "Không nominate ablation hoặc mở 2025 nếu U_full không đạt; không hạ ngưỡng sau outcome.",
            "Alias và cặp repeat phụ thuộc không tăng số quan sát độc lập; không suy provider deterministic.",
            "Gate W10 bao phủ kernel đã khóa; code/schema/test phân tích này có nghiệm thu bổ sung riêng."]})


def read_selection(path: Path, expected: dict[str, Any]) -> dict[str, Any]:
    """Consumer yêu cầu bản dựng lại, từ chối cả JSON tự reseal nhưng sai số liệu/quyết định."""
    saved = validate_artifact(read_envelope(path))
    if digest(saved) != digest(expected):
        raise ValueError("Nomination khác source/metric/rule/repeat/decision đã tái dựng")
    return saved


def main() -> None:
    """Prepare write-once hoặc mặc định cold verify; không có mode API hoặc đổi threshold."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    args = parser.parse_args()
    with verified_evidence() as evidence:
        expected = make_artifact(evidence)
        evidence["guard"]()
        if args.prepare:
            _write_once(OUTPUT, expected)
        saved = read_selection(OUTPUT, expected)
        evidence["guard"]()
        decision = saved["decision"]
        print(f"Nomination nguồn/report/rule PASS: {decision['status']}; "
              f"positive_symbols={decision['positive_symbols']}/4; "
              f"D={decision['mean_delta_return_original_pp']:.9f} đpt; "
              "API=0, confirmation_allowed=false")


if __name__ == "__main__":
    main()
