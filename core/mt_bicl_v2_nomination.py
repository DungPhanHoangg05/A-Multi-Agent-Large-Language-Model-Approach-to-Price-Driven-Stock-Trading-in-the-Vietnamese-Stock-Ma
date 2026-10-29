"""Khóa nomination v2 bằng rule trước run và report đúng nguồn; không mở lại thí nghiệm."""

from __future__ import annotations

import math
from pathlib import Path
import subprocess
from typing import Any

from core.bayesian_memory import read_json
from core.mt_bicl_bank import content_hash
from core.mt_bicl_v2_io import read_envelope, write_envelope
from core.mt_bicl_v2_release import git_value
from core.mt_bicl_v2_report import (
    ACCOUNTS_SHA256, FULL, NAMES, REPORT, SYMBOLS, VERSION as REPORT_VERSION, rebuild as rebuild_report,
)
from core.mt_bicl_v21_preparation import file_hash

VERSION = "mt_bicl_development_nomination_v2"
RECEIPT = Path("docs/plan/week11/development_nomination_v2.json")
PROTOCOL = Path("docs/plan/week10/protocol_v2.json")
CODE = ("core/mt_bicl_v2_nomination.py", "scripts/nominate_mt_bicl_development.py", "tests/test_mt_bicl_v2_nomination.py")
REPORT_SHA256 = "ce4ac6b6c2f168ad8e88822236a38277ac46d812382414a691bcebfb8b89fb8d"
EVIDENCE = Path("outputs/bayesian_benchmark/mt_bicl_v2")
EVIDENCE_SHA256 = "abee3ec568a76d58335c064c9253391e7dfcd70a55c3efe605c1f8c3ffc2f6a3"
PLANNED = {"FPT": 12, "MWG": 16, "VCB": 16, "VNM": 16}
RULES = {"G": 60, "D_Full_Original_strict_min": 0, "positive_symbols_min": 3,
         "D_Full_A_inclusive_min": 0, "mean_delta_MDD_max_pp": 2,
         "max_delta_MDD_max_pp": 5, "candidate_substitution": False}


def number(value: Any) -> float:
    """Không chấp nhận null/bool/NaN hoặc tự biến lỗi metric thành kết quả không đề cử."""
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("Nomination cần metric số hữu hạn đúng kiểu")
    return float(value)


def evidence_snapshot(root: Path) -> dict[str, Any]:
    """Băm toàn bộ2597 file v2, chỉ loại ba tên metadata khóa OS có thể thay đổi."""
    directory = root/EVIDENCE
    excluded = {"run.lock", "run.owner.json", "run.recovery.json"}
    files = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError("Bằng chứng v2 chứa liên kết ngoài")
        if path.is_file() and path.name not in excluded:
            files[path.relative_to(directory).as_posix()] = file_hash(path)
    checksum = content_hash(files)
    if len(files) != 2597 or checksum != EVIDENCE_SHA256:
        raise ValueError("Cây bằng chứng v2 khác snapshot trước đóng nomination")
    return {"file_count": len(files), "sha256": checksum,
            "method": "SHA256_CANONICAL_JSON_MAP_NAMESPACE_RELATIVE_PATH_TO_FILE_BYTE_SHA256",
            "excluded_OS_lock_filenames": sorted(excluded)}


def evaluate(report: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    """Chỉ Full và primary G60; tính lại ΔR/MDD từ bốn tài khoản, không dùng accuracy/repeat."""
    if content_hash(rules) != content_hash(RULES):
        raise ValueError("Rule nomination khác protocol v2 đã đăng ký")
    if (report["status"] != "PASS" or report["phase"] != "development2023"
            or report["nomination"] != "NOT_EVALUATED" or report["confirmation_allowed"] is not False):
        raise ValueError("Nomination cần report mô tả v2 đã kiểm, không nhận holdout hoặc revision mới")
    points = report["all_primary_cases"]
    ids = [p["point_id"] for p in points]
    group = report["G"]
    if (type(group["count"]) is not int or group["count"] != 60 or len(points) != 60 or len(set(ids)) != 60
            or group["point_ids"] != ids or set(group["stocks"]) != set(SYMBOLS)
            or report["support"]["planned_count"] != 60 or report["support"]["complete_count"] != 60
            or report["support"]["excluded"]):
        raise ValueError("Primary/common support phải đủ60 point trước nomination")
    metrics = {}
    for symbol in SYMBOLS:
        selected = [p for p in points if p["symbol"] == symbol]
        expected_ids = [p["point_id"] for p in selected]
        if (len(selected) != PLANNED[symbol] or expected_ids != sorted(expected_ids)
                or any(p["repeat_index"] != 0 or not p["as_of_date"].startswith("2023-")
                       or p["point_id"] != symbol+"-"+p["as_of_date"] or set(p["branches"]) != set(NAMES)
                       or any(b["action"] not in ("LONG", "SHORT", "CASH") for b in p["branches"].values()) for p in selected)
                or set(group["stocks"][symbol]) != set(NAMES)):
            raise ValueError("Primary sai mã/ngày/lượt hoặc thiếu nhánh")
        stock = group["stocks"][symbol]
        for name in NAMES:
            value = stock[name]
            if (value["count"] != PLANNED[symbol] or value["reason"] is not None or value["account"] is None
                    or value["account"]["point_ids"] != expected_ids):
                raise ValueError("Tài khoản không ở cùng G đầy đủ")
        full, original, reference = (stock[n]["account"]["metrics"] for n in (FULL, "Original", "A_reference"))
        fr, old, ref = (number(v["total_return_pct"]) for v in (full, original, reference))
        fm, om, am = (number(v["max_drawdown_pct"]) for v in (full, original, reference))
        if min(fm, om, am) < 0:
            raise ValueError("MDD phải là độ lớn không âm")
        metrics[symbol] = {"count": len(selected), "return_full_pct": fr, "return_original_pct": old,
            "return_A_reference_pct": ref, "delta_return_original_pp": fr-old, "delta_return_A_pp": fr-ref,
            "MDD_full_pct": fm, "MDD_original_pct": om, "delta_MDD_original_pp": fm-om}
        for name, delta in (("Original", fr-old), ("A_reference", fr-ref)):
            supplied = group["contrasts"][name]["by_symbol"][symbol]
            if supplied["count"] != len(selected) or not math.isclose(number(supplied["delta_return_pp"]), delta, rel_tol=0, abs_tol=1e-10):
                raise ValueError("Contrast trong report khác tài khoản vừa tính")
    d = math.fsum(v["delta_return_original_pp"] for v in metrics.values())/4
    a = math.fsum(v["delta_return_A_pp"] for v in metrics.values())/4
    mean_mdd = math.fsum(v["delta_MDD_original_pp"] for v in metrics.values())/4
    max_mdd = max(v["delta_MDD_original_pp"] for v in metrics.values())
    positive = sum(v["delta_return_original_pp"] > 0 for v in metrics.values())
    for name, delta in (("Original", d), ("A_reference", a)):
        if not math.isclose(number(group["contrasts"][name]["mean_delta_return_pp"]), delta, rel_tol=0, abs_tol=1e-10):
            raise ValueError("D trong report khác mean đều bốn tài khoản")
    checks = {"complete_G60_verified": True, "D_Full_Original_gt_0": bool(d > rules["D_Full_Original_strict_min"]),
        "positive_symbols_at_least_3": bool(positive >= rules["positive_symbols_min"]),
        "D_Full_A_ge_0": bool(a >= rules["D_Full_A_inclusive_min"]),
        "mean_delta_MDD_le_2": bool(mean_mdd <= rules["mean_delta_MDD_max_pp"]),
        "max_delta_MDD_le_5": bool(max_mdd <= rules["max_delta_MDD_max_pp"])}
    nominated = all(checks.values())
    return {"revision": "v2", "verification": "PASS", "status": "NOMINATED" if nominated else "NOT_NOMINATED",
        "candidate_evaluated": FULL, "nominated_candidate": FULL if nominated else None,
        "rules": rules, "checks": checks, "failure_reasons": [k for k, passed in checks.items() if not passed],
        "metrics": {"G": 60, "D_Full_Original_pp": d, "positive_symbols": positive, "D_Full_A_pp": a,
                    "mean_delta_MDD_pp": mean_mdd, "max_delta_MDD_pp": max_mdd, "by_symbol": metrics},
        "confirmation_v2": {"status": "REQUIRES_SEPARATE_RELEASE" if nominated else "NOT_RUN", "allowed": False,
                            "reason": "SEPARATE_RELEASE_REQUIRED" if nominated else "V2_NOT_NOMINATED"},
        "scope": "V2_ONLY_NO_V3_PROTOCOL_OR_RELEASE", "candidate_substitution": False,
        "report_nomination_field_preserved": "NOT_EVALUATED"}


def rebuild(root: Path) -> dict[str, Any]:
    """Kiểm đúng byte/source/report, dựng lại report rồi đóng quyết định riêng ngoài namespace v2."""
    before = evidence_snapshot(root)
    if file_hash(root/REPORT) != REPORT_SHA256:
        raise ValueError("Report khác byte W11-04 đã nghiệm thu")
    saved = read_envelope(root/REPORT, REPORT_VERSION)
    actual = rebuild_report(root)
    if content_hash(saved) != content_hash(actual):
        raise ValueError("Report khác source/account vừa dựng lại; không được đóng nomination")
    rules = read_json(root/PROTOCOL)["development"]["nomination"]
    result = evaluate(actual, rules)
    if before != evidence_snapshot(root):
        raise ValueError("Bằng chứng v2 đổi trong khi kiểm nomination")
    commit = git_value(root, "log", "-1", "--format=%H", "--", *CODE)
    git_value(root, "diff", "--exit-code", commit, "--", *CODE)
    for name in CODE:
        git_value(root, "cat-file", "-e", commit+":"+name)
    result["binding"] = {"run_signature": actual["run_signature"], "report_path": REPORT.as_posix(),
        "report_sha256": REPORT_SHA256, "accounts_sha256": ACCOUNTS_SHA256,
        "report_consumer": actual["binding"], "protocol_path": PROTOCOL.as_posix(),
        "protocol_sha256": file_hash(root/PROTOCOL), "rule_payload_sha256": content_hash(rules),
        "v2_evidence": before, "source_commit": commit, "source_sha256": {n: file_hash(root/n) for n in CODE}}
    return result


def save_or_verify(root: Path, result: dict[str, Any], *, verify_only: bool = False) -> None:
    """Receipt immutable; tái kiểm phải khớp toàn payload và byte đã neo trong Git."""
    path = root/RECEIPT
    if verify_only or path.exists():
        if content_hash(read_envelope(path, VERSION)) != content_hash(result):
            raise ValueError("Receipt nomination khác source/report/rule/kết quả vừa tái dựng")
        if verify_only:
            anchored = subprocess.run(["git", "show", "HEAD:"+RECEIPT.as_posix()], cwd=root, capture_output=True, check=True)
            if anchored.stdout != path.read_bytes():
                raise ValueError("Receipt nomination chưa neo đúng byte Git HEAD")
    else:
        write_envelope(path, VERSION, result, immutable=True)
