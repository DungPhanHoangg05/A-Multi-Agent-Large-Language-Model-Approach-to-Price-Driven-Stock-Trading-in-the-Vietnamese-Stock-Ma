"""Đề cử development từ report tái dựng; fixture không là bằng chứng lựa chọn thật."""

from copy import deepcopy
import hashlib
import math
from pathlib import Path
import re
from typing import Any

from core.backtest_engine import PRIOR_BRANCH_MODES
from core.paired_candidate_report import VERSION as REPORT_VERSION, read_report
from core.prior_backtest import canonical_hash
from core.prior_config import copy_prior_json
from core.prior_run_lock import safe_path

VERSION = "candidate_selection_v1"
RULE_VERSION = "development_nomination_rules_v1"
ORDER = ("C0", "C1", "C2", "C3", "C3_stats_only", "C3_examples_only")
PLANNED = {"FPT": 12, "VNM": 16, "VCB": 16, "MWG": 16}
GATES = ("compileall", "unit", "e2e", "leakage")
RULES = {"rule_version": RULE_VERSION, "candidate_order": list(ORDER), "planned": PLANNED,
    "min_visible": 6, "min_visible_per_symbol": 1, "min_positive_symbols": 3,
    "max_mean_delta_mdd_pp": 2., "max_symbol_delta_mdd_pp": 5., "return_tie_pp": 1e-9,
    "risk_policy": "OFF"}


def _sha(path: Path) -> str:
    """Băm byte artifact thực, không lấy checksum tự khai làm nguồn tin."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_technical_gates(path: Path | None, binding: dict[str, Any]) -> dict[str, Any]:
    """Kiểm receipt bốn gate theo code/runtime và log; không chạy test trong selector."""
    from core.research_cohort import read_envelope
    if path is None:
        return {"status": "NOT_VERIFIED", "sha256": None, "checks": {name:"NOT_RUN" for name in GATES}}
    if path.name.startswith(".env"):
        raise ValueError("Receipt gate không được trỏ vào credential")
    receipt = read_envelope(path)
    if (set(receipt) != {"gate_version", "code_sha256", "runtime", "checks"}
            or receipt["gate_version"] != "research_technical_gates_v1"
            or receipt["code_sha256"] != binding["code_sha256"] or receipt["runtime"] != binding["runtime"]
            or set(receipt["checks"]) != set(GATES)):
        raise ValueError("Receipt gate khác code/runtime hoặc thiếu bốn gate")
    checks = {}
    for name in GATES:
        check = receipt["checks"][name]
        if (set(check) != {"status", "exit_code", "log"} or check["status"] not in ("PASS", "FAIL", "NOT_RUN")
                or check["exit_code"] is not None and type(check["exit_code"]) is not int):
            raise ValueError("Schema kết quả gate không hợp lệ")
        log = check["log"]
        text = ""
        if log is not None:
            if set(log) != {"path", "sha256"}:
                raise ValueError("Log gate thiếu path/hash")
            source = safe_path(path.parent, log["path"])
            if source.name.startswith(".env") or _sha(source) != log["sha256"]:
                raise ValueError("Log gate khác byte đã khóa hoặc trỏ vào credential")
            text = source.read_text(encoding="utf-8-sig")
        if check["status"] == "PASS":
            if check["exit_code"] != 0 or not text:
                raise ValueError("Gate PASS thiếu log hoặc exit code bằng 0")
            if name in ("unit", "leakage"):
                if (not re.search(r"^Ran [1-9]\d* tests? in [\d.]+s\s+OK\s*$", text, re.M)
                        or re.search(r"^(?:FAILED|ERROR:)|\bskipped\b", text, re.M)):
                    raise ValueError("Log unittest chưa pass đầy đủ hoặc có skip")
            elif name == "e2e":
                if "ALL PIPELINE CHECKS SUCCESSFUL" not in text or "[FAIL]" in text:
                    raise ValueError("Log E2E chưa pass")
            elif ("*** Error" in text or not all(f"Listing '{part}'" in text for part in
                  ("agents", "core", "data_manager", "scripts", "tests", "utils"))):
                raise ValueError("Log compileall chưa kiểm đủ codebase")
        checks[name] = check["status"]
    return {"status": "PASS" if all(value == "PASS" for value in checks.values()) else "NOT_PASS",
            "sha256": _sha(path), "checks": checks, "receipt": receipt}


def _number(value: Any) -> float | None:
    """Null hợp lệ cho primary thiếu; số không hữu hạn hoặc bool không là metric."""
    if value is None:
        return None
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("Return/MDD lựa chọn phải là số hữu hạn")
    return float(value)


def _ranking(names: list[str], candidates: dict[str, Any]) -> dict[str, Any]:
    """Chia tie quanh từng D_max; không nối chuỗi các D gần nhau."""
    remaining, ranked, groups = list(names), [], []
    while remaining:
        maximum = max(candidates[name]["delta_return_pp"] for name in remaining)
        tied = [name for name in remaining if maximum-candidates[name]["delta_return_pp"] <= RULES["return_tie_pp"]]
        tied.sort(key=lambda name:(candidates[name]["mean_delta_mdd_pp"], ORDER.index(name)))
        ranked.extend(tied)
        groups.append({"d_max_pp": maximum, "candidate_ids": tied})
        remaining = [name for name in remaining if name not in tied]
    return {"order": ranked, "tie_groups": groups}


def evaluate_selection(report: dict[str, Any], *, gates_passed: bool) -> dict[str, Any]:
    """Tái tính eligibility/D/MDD/exposure từ report nguồn đã verify; không tạo nomination thật."""
    report = copy_prior_json(report)
    matrix = [*PRIOR_BRANCH_MODES, *ORDER]
    if (report["report_version"] != REPORT_VERSION or report["split"] not in ("fixture", "development_2023")
            or report["matrix"] != matrix or set(report["stocks"]) != set(PLANNED) or type(gates_passed) is not bool):
        raise ValueError("Selector chỉ nhận report ứng viên development/fixture đúng ma trận")
    support, planned, visible = {}, {}, {name:{} for name in ORDER}
    complete = True
    for symbol in PLANNED:
        stock = report["stocks"][symbol]
        points = stock["points"]
        ids = [point["point_id"] for point in points]
        common = stock["global_common_support"]
        if (len(ids) != len(set(ids)) or common["count"] != len(common["point_ids"])
                or len(set(common["point_ids"])) != common["count"]):
            raise ValueError("Support lựa chọn trùng hoặc khác count")
        for point in points:
            day = point["as_of_date"]
            if day >= "2024-01-01" or (report["split"] == "development_2023" and not day.startswith("2023-")):
                raise ValueError("Selector không nhận point holdout hoặc ngoài development")
        for point in stock.get("action_attribution", {}).get("points", []):
            label = point["economic_label"]
            if any(label[key] >= "2024-01-01" for key in ("entry_date", "exit_date")):
                raise ValueError("Selector không nhận outcome vượt biên development")
        actual_common = [point["point_id"] for point in points if all(point["branch_status"][name] == "complete" for name in matrix)]
        if actual_common != common["point_ids"]:
            raise ValueError("Support lựa chọn khác trạng thái đủ 11 nhánh")
        planned[symbol], support[symbol] = len(points), common["count"]
        complete = complete and len(points) == PLANNED[symbol] and actual_common == ids
        for name in ORDER:
            count = sum(point["branch_status"][name] == "complete" and bool(point["prior"][name]["prefix_sha256"])
                and bool(point["prior"][name]["visible_metric_ids"] or point["prior"][name]["visible_example_ids"]) for point in points)
            if count != stock["coverage"][name]["prior_visible_count"]:
                raise ValueError("Exposure lựa chọn khác prefix/Decision đã verify")
            visible[name][symbol] = int(count)
    paired_60 = sum(support.values()) == 60
    candidates = {}
    for name in ORDER:
        returns, drawdowns = {}, {}
        for symbol in PLANNED:
            stock = report["stocks"][symbol]
            a, b = (stock["metrics"][key]["account_metrics"] for key in (name,"original"))
            ar, br = (_number(value["total_return_pct"]) if value is not None else None for value in (a,b))
            am, bm = (_number(value["max_drawdown_pct"]) if value is not None else None for value in (a,b))
            if any(value is not None and value < 0 for value in (am,bm)):
                raise ValueError("MDD tài khoản không được âm")
            returns[symbol] = _number(ar-br) if ar is not None and br is not None else None
            drawdowns[symbol] = _number(am-bm) if am is not None and bm is not None else None
        finite = all(value is not None for value in [*returns.values(), *drawdowns.values()])
        d = _number(sum(returns.values())/4) if complete and finite else None
        mean_mdd = _number(sum(drawdowns.values())/4) if complete and finite else None
        max_mdd = float(max(drawdowns.values())) if complete and finite else None
        total_visible = sum(visible[name].values())
        conditions = {"technical_gates_pass": gates_passed, "primary_complete": complete,
            "paired_60": paired_60, "finite_return_mdd": finite,
            "exposure_at_least_6": total_visible >= 6, "exposure_each_symbol": all(v >= 1 for v in visible[name].values())}
        exposure_reason = ("EXPOSURE_NOT_EVALUATED_INCOMPLETE_PRIMARY" if not complete else
            "NO_EXPOSURE" if total_visible == 0 else "INSUFFICIENT_EXPOSURE" if
            not conditions["exposure_at_least_6"] or not conditions["exposure_each_symbol"] else None)
        failure_codes = {"technical_gates_pass":"TECHNICAL_GATES_NOT_PASS", "primary_complete":"PRIMARY_INCOMPLETE",
            "paired_60":"PAIRED_POINTS_NOT_60", "finite_return_mdd":"MISSING_OR_NONFINITE_RETURN_MDD"}
        reasons = [code for key,code in failure_codes.items() if not conditions[key]]
        if exposure_reason is not None:
            reasons.append(exposure_reason)
        promotion = {"positive_mean_return": d is not None and d > 0,
            "positive_at_least_3_symbols": sum(v is not None and v > 0 for v in returns.values()) >= 3,
            "mean_delta_mdd_at_most_2": mean_mdd is not None and mean_mdd <= 2,
            "max_delta_mdd_at_most_5": max_mdd is not None and max_mdd <= 5}
        eligible = all(conditions.values())
        candidates[name] = {"conditions": conditions, "eligibility_reasons": reasons, "eligible": eligible,
            "visible_by_symbol": visible[name], "visible_count": total_visible, "visibility_denominator": 60,
            "delta_return_by_symbol_pp": returns, "delta_mdd_by_symbol_pp": drawdowns,
            "delta_return_pp": d, "mean_delta_mdd_pp": mean_mdd, "max_delta_mdd_pp": max_mdd,
            "positive_symbol_count": sum(v is not None and v > 0 for v in returns.values()),
            "promotion_conditions": promotion, "promotion_reasons": [key.upper() for key,value in promotion.items() if not value],
            "promotable": eligible and all(promotion.values())}
    eligible = _ranking([name for name in ORDER if candidates[name]["eligible"]], candidates)
    promote = _ranking([name for name in ORDER if candidates[name]["promotable"]], candidates)
    selected = (promote["order"] or eligible["order"] or [None])[0]
    status = "PROMOTED" if promote["order"] else "NOT_PROMOTED" if eligible["order"] else "BLOCKED"
    return {"nomination_status": status, "research_candidate": selected,
        "deployment_choice": selected if status == "PROMOTED" else "original", "candidates": candidates,
        "eligible_ranking": eligible, "promote_ranking": promote, "planned_by_symbol": planned,
        "paired_by_symbol": support, "paired_count": sum(support.values()),
        "reasons": [] if status != "BLOCKED" else
            (["TECHNICAL_GATES_NOT_PASS"] if not gates_passed else []) +
            (["PRIMARY_INCOMPLETE"] if not complete else []) + ["NO_ELIGIBLE_CANDIDATE"]}


def selection_artifact(report: dict[str, Any], gates: dict[str, Any], *, report_file_sha256: str) -> dict[str, Any]:
    """Khóa quyết định và mọi binding; mô phỏng fixture luôn BLOCKED ở cấp artifact."""
    result = evaluate_selection(report, gates_passed=gates["status"] == "PASS")
    real = (report["split"] == "development_2023" and report["binding"]["execution_mode"] == "research"
            and report["selection_evidence_status"] == "DEVELOPMENT")
    decision = {**result} if real else {**result, "nomination_status":"BLOCKED", "research_candidate":None,
        "deployment_choice":"original", "reasons":["NOT_DEVELOPMENT_EVIDENCE", *result["reasons"]]}
    return copy_prior_json({"selection_version": VERSION, "rules": RULES, "rules_sha256": canonical_hash(RULES),
        "cohort_id": report["cohort_id"], "split": report["split"], "risk_policy":"OFF",
        "selection_evidence_status": "DEVELOPMENT" if real else "NOT_APPLICABLE", **decision,
        "fixture_protocol_result": result if not real else None,
        "binding": {**deepcopy(report["binding"]), "report_sha256": canonical_hash(report),
            "report_file_sha256": report_file_sha256, "technical_gates": gates},
        "limitations": ["Đề cử development chưa chứng minh lợi ích holdout; risk policy giữ OFF.",
            "Fixture/mock chỉ kiểm protocol; NOT_PROMOTED vẫn giữ ứng viên nghiên cứu, triển khai Original."]})


def selection_for_report(report_path: Path, expected_report: dict[str, Any], *,
                         gates_path: Path | None = None) -> dict[str, Any]:
    """Caller tái dựng expected_report từ runner/checkpoint; không dùng report tự khai."""
    report = read_report(report_path, expected_report)
    gates = read_technical_gates(gates_path, report["binding"])
    return selection_artifact(report, gates, report_file_sha256=_sha(report_path))


def read_selection(path: Path, report_path: Path, expected_report: dict[str, Any], *,
                   gates_path: Path | None = None) -> dict[str, Any]:
    """Dựng lại report nguồn/gate/ranking và so toàn artifact, không ghi lại file."""
    from core.research_cohort import read_envelope
    expected = selection_for_report(report_path, expected_report, gates_path=gates_path)
    saved = read_envelope(path)
    if canonical_hash(saved) != canonical_hash(expected):
        raise ValueError("Quyết định khác nguồn/report, gate, eligibility hoặc thứ tự đã tái tính")
    return saved


def write_selection(path: Path, report_path: Path, expected_report: dict[str, Any], *,
                    gates_path: Path | None = None) -> dict[str, Any]:
    """Output mới bất biến; không ghi đè report/checkpoint hoặc quyết định cũ."""
    from core.research_input_lock import _write_once
    if path.name.startswith(".env") or path.resolve() == report_path.resolve():
        raise ValueError("Quyết định cần đường output riêng, không trỏ vào credential/report")
    result = selection_for_report(report_path, expected_report, gates_path=gates_path)
    _write_once(path, result)
    return result
