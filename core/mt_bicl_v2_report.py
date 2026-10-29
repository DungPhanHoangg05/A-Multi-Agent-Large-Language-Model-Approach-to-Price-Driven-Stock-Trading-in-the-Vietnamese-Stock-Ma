"""Báo cáo development mô tả, giữ đủ G và repeat; không quyết định nomination."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from itertools import combinations
import io
import math
from pathlib import Path
from typing import Any

import numpy as np

from core.bayesian_memory import read_json
from core.mt_bicl_bank import content_hash
from core.mt_bicl_v2_adapter import VARIANTS
from core.mt_bicl_v2_audit import CODE as AUDIT_CODE, OFFLINE, REPORT as ACCOUNTS, VERSION as ACCOUNT_VERSION, account, snapshot
from core.mt_bicl_v2_development import verify_extension
from core.mt_bicl_v2_io import read_envelope, write_envelope
from core.mt_bicl_v2_release import LEDGER, git_value
from core.mt_bicl_v2_run_manifest import OUTPUT
from core.mt_bicl_v21_preparation import file_hash
from core.research_metrics import http_telemetry

VERSION = "mt_bicl_development_analysis_v2"
REPORT = OUTPUT/"analysis"/"report.json"
FIGURE = OUTPUT/"analysis"/"results.png"
ACCOUNTS_SHA256 = "fab7ebe0b2102a17487ed02d5c099a53671b696323a9d7ca377dec050544a348"
CODE = ("core/mt_bicl_v2_report.py", "scripts/report_mt_bicl_development.py", "tests/test_mt_bicl_v2_report.py")
NAMES = (*VARIANTS, *OFFLINE)
FULL = "Full_MT_BICL"
REFERENCES = tuple(n for n in NAMES if n != FULL)
SYMBOLS = ("FPT", "MWG", "VCB", "VNM")


def action(point: dict[str, Any], name: str) -> str:
    """Chuẩn hóa SHORT thành CASH nhưng không nhận action lỗi hoặc unknown."""
    value = point["branches"][name]["action"]
    if value not in ("LONG", "SHORT", "CASH"):
        raise ValueError("Action lỗi không được đổi thành CASH trong báo cáo")
    return "LONG" if value == "LONG" else "CASH"


def actions(points: list[dict[str, Any]], a: str, b: str) -> dict[str, Any]:
    """Chiều chuyển từ B sang A; giữ cả chuyển thuận và bất lợi."""
    counts = Counter(action(p, b)+"_TO_"+action(p, a) for p in points)
    changed = counts["CASH_TO_LONG"]+counts["LONG_TO_CASH"]
    return {"counts": {k: counts[k] for k in ("CASH_TO_LONG", "LONG_TO_CASH", "LONG_TO_LONG", "CASH_TO_CASH")},
            "disagreements": changed, "denominator": len(points), "rate": changed/len(points) if points else None}


def kl_gap(student: float, teacher: float) -> float | None:
    """KL Bernoulli teacher||student, không clip xác suất hoặc giấu KL vô hạn."""
    for p in (student, teacher):
        if type(p) not in (float, int) or not math.isfinite(p) or not 0 <= p <= 1:
            raise ValueError("Xác suất không hợp lệ")
    if student == 0 and teacher > 0 or student == 1 and teacher < 1:
        return None
    terms = []
    if teacher > 0:
        terms.append(teacher*(math.log(teacher)-math.log(student)))
    if teacher < 1:
        terms.append((1-teacher)*(math.log1p(-teacher)-math.log1p(-student)))
    result = math.fsum(terms)
    if result < -1e-12:
        raise ValueError("KL âm ngoài sai số số học")
    return float(max(0., result))


def approximation(points: list[dict[str, Any]]) -> dict[str, Any]:
    """Mọi p full precision cùng G; thiếu feature giữ reason, không đổi mẫu số thị trường."""
    rows, excluded = [], []
    for point in points:
        if point["context"]["status"] != "AVAILABLE":
            excluded.append({"point_id": point["point_id"], "reasons": point["context"]["reasons"]})
            continue
        p, q = (point["branches"][n]["probability"] for n in OFFLINE)
        gap = kl_gap(p, q)
        rows.append({"point_id": point["point_id"], "p_student": p, "p_teacher": q,
            "delta_student_minus_teacher": p-q, "absolute_error": abs(p-q), "kl_teacher_student_nats": gap,
            "kl_reason": "INFINITE_KL" if gap is None else None,
            "threshold_action_disagreement": bool((p > .5) != (q > .5))})
    finite = [r["kl_teacher_student_nats"] for r in rows if r["kl_reason"] is None]
    return {"G_count": len(points), "probability_count": len(rows), "excluded": excluded, "points": rows,
        "mean_kl_nats": float(np.mean(finite)) if rows and len(finite) == len(rows) else None,
        "infinite_kl_count": len(rows)-len(finite),
        "mean_absolute_error": float(np.mean([r["absolute_error"] for r in rows])) if rows else None,
        "p95_absolute_error": float(np.quantile([r["absolute_error"] for r in rows], .95, method="linear")) if rows else None,
        "action_disagreement_on_G": actions(points, "Numeric_only", "Teacher_only"),
        "probability_action_disagreement_count": sum(r["threshold_action_disagreement"] for r in rows),
        "interpretation": "KL đo approximation teacher, không là accuracy thị trường hoặc P&L"}


class Analysis:
    """Dựng lại mỗi tài khoản subgroup trên đúng support, cache chỉ trong một report."""

    def __init__(self) -> None:
        self.cache: dict[tuple[Any, ...], dict[str, Any]] = {}

    def metric(self, points: list[dict[str, Any]], name: str) -> dict[str, Any]:
        """Nhóm rỗng trả null; tài khoản không LONG có hit rate null kèm lý do."""
        if not points:
            return {"count": 0, "account": None, "reason": "NO_SUPPORT", "accuracy": None, "long_rate": None}
        points = sorted(points, key=lambda p: (p["as_of_date"], p["point_id"]))
        key = (name, tuple((p["point_id"], p["repeat_index"], action(p, name)) for p in points))
        if key not in self.cache:
            rebuilt = account(points, name)
            longs = sum(action(p, name) == "LONG" for p in points)
            correct = sum((action(p, name) == "LONG") == (p["evaluation"]["actual_direction"] == "UP") for p in points)
            if not longs:
                rebuilt["metrics"]["hit_rate_pct"] = None
                rebuilt["metrics"]["avg_trade_pct"] = None
            self.cache[key] = {"count": len(points), "account": rebuilt, "reason": None,
                "accuracy": correct/len(points), "long_count": longs, "cash_count": len(points)-longs,
                "long_rate": longs/len(points), "hit_rate_reason": None if longs else "NO_LONG"}
        return deepcopy(self.cache[key])

    def contrast(self, points: list[dict[str, Any]], a: str, b: str) -> dict[str, Any]:
        """D là mean đều bốn Δreturn tài khoản, không mean payoff từng cycle."""
        symbols = {}
        for symbol in SYMBOLS:
            subset = [p for p in points if p["symbol"] == symbol]
            am, bm = (self.metric(subset, name) for name in (a, b))
            aa, bb = (v["account"]["metrics"] if v["account"] else None for v in (am, bm))
            symbols[symbol] = {"count": len(subset), "delta_return_pp": aa["total_return_pct"]-bb["total_return_pct"] if aa else None,
                "delta_mdd_pp": aa["max_drawdown_pct"]-bb["max_drawdown_pct"] if aa else None}
        values = [v["delta_return_pp"] for v in symbols.values() if v["delta_return_pp"] is not None]
        return {"a": a, "b": b, "count": len(points), "by_symbol": symbols,
            "mean_delta_return_pp": math.fsum(values)/4 if len(values) == 4 else None,
            "descriptive_mean_available_symbols_pp": math.fsum(values)/len(values) if values else None,
            "contributing_symbol_count": len(values), "actions": actions(points, a, b)}

    def group(self, points: list[dict[str, Any]], names: tuple[str, ...] = NAMES) -> dict[str, Any]:
        """Báo mọi nhánh và mọi contrast Full; không thay subgroup cho G."""
        stocks = {s: {n: self.metric([p for p in points if p["symbol"] == s], n) for n in names} for s in SYMBOLS}
        branches = {}
        for name in names:
            values = [stocks[s][name]["account"]["metrics"] for s in SYMBOLS if stocks[s][name]["account"] is not None]
            branches[name] = {"count": len(points), "long_count": sum(action(p, name) == "LONG" for p in points),
                "long_rate": sum(action(p, name) == "LONG" for p in points)/len(points) if points else None,
                "accuracy": sum((action(p, name) == "LONG") == (p["evaluation"]["actual_direction"] == "UP") for p in points)/len(points) if points else None,
                "mean_account_return_pct": math.fsum(v["total_return_pct"] for v in values)/4 if len(values) == 4 else None,
                "mean_account_mdd_pct": math.fsum(v["max_drawdown_pct"] for v in values)/4 if len(values) == 4 else None}
        return {"point_ids": [p["point_id"] for p in points], "count": len(points),
            "reason": None if points else "NO_SUPPORT",
            "stocks": stocks, "branches": branches,
            "contrasts": {b: self.contrast(points, FULL, b) for b in REFERENCES}}

    def sensitivity(self, points: list[dict[str, Any]], b: str) -> dict[str, Any]:
        """Bỏ một action change bằng hoàn nguyên Full về B; giữ nguyên toàn bộ G."""
        base = self.contrast(points, FULL, b)
        deltas = {s: base["by_symbol"][s]["delta_return_pp"] for s in SYMBOLS}
        cases = []
        for p in points:
            if action(p, FULL) == action(p, b):
                continue
            switched = deepcopy(p)
            switched["branches"][FULL]["action"] = p["branches"][b]["action"]
            subset = [switched if q["point_id"] == p["point_id"] else q for q in points if q["symbol"] == p["symbol"]]
            counterfactual = self.contrast(subset, FULL, b)["by_symbol"][p["symbol"]]["delta_return_pp"]
            d = (math.fsum(v for s, v in deltas.items() if s != p["symbol"])+counterfactual)/4
            cycle = p["evaluation"]["net_return_long"]*((action(p, FULL) == "LONG")-(action(p, b) == "LONG"))
            cases.append({"point_id": p["point_id"], "symbol": p["symbol"],
                "transition": action(p, b)+"_TO_"+action(p, FULL), "cycle_delta_pct": cycle*100,
                "cycle_effect": "BENEFICIAL" if cycle > 0 else "ADVERSE" if cycle < 0 else "ZERO",
                "D_after_reverting_change_pp": d, "G_count": len(points)})
        return {"leave_one_change_out": cases,
            "leave_one_symbol_out": {s: math.fsum(v for k, v in deltas.items() if k != s)/3 for s in SYMBOLS},
            "note": "Hoàn nguyên một action, không loại point; cycle delta không cộng thành D"}


def repeat_report(points: list[dict[str, Any]], sample: list[str], analysis: Analysis) -> dict[str, Any]:
    """So cùng12 point ở lượt0..3; báo mọi lượt/cặp phụ thuộc, không vote hoặc chọn tốt nhất."""
    blocks = {(p["point_id"], p["repeat_index"]): p for p in points if p["point_id"] in sample}
    if set(blocks) != {(pid, r) for pid in sample for r in range(4)}:
        raise ValueError("Repeat thiếu point/lượt đã khóa")
    groups = {str(r): analysis.group([blocks[(pid, r)] for pid in sample],
              NAMES+(('Original_duplicate',) if r else ())) for r in range(4)}
    pairs = {}
    for name in NAMES:
        values = [(pid, a, b, action(blocks[(pid, a)], name), action(blocks[(pid, b)], name))
                  for pid in sample for a, b in combinations(range(4), 2)]
        pairs[name] = {"comparisons": len(values), "disagreements": sum(a != b for _, _, _, a, b in values),
            "dependent_pairs": [{"point_id": pid, "repeat_a": a, "repeat_b": b, "action_a": x, "action_b": y} for pid, a, b, x, y in values]}
    duplicates = [blocks[(pid, r)] for pid in sample for r in (1, 2, 3)]
    signs = {b: {"D_by_repeat_pp": [groups[str(r)]["contrasts"][b]["mean_delta_return_pp"] for r in range(4)],
                 "signs_by_repeat": [int(np.sign(groups[str(r)]["contrasts"][b]["mean_delta_return_pp"])) for r in range(4)]} for b in REFERENCES}
    return {"sample": sample, "in_primary": False, "groups": groups, "disagreement": pairs,
            "original_duplicate": actions(duplicates, "Original_duplicate", "Original"), "contrasts": signs,
            "note": "Tài khoản reset trên cùng12 point; cặp lặp phụ thuộc, không nhân N primary"}


def build_report(source: dict[str, Any], manifest: dict[str, Any], ledger: dict[str, Any]) -> dict[str, Any]:
    """Consumer mô tả từ report đã audit; không mở nguồn market hoặc chạy model."""
    if source["status"] != "PASS" or source["phase"] != "development2023":
        raise ValueError("Consumer chỉ nhận account development đã nghiệm thu")
    points = source["points"]
    primary = [p for p in points if p["repeat_index"] == 0]
    if ([p["point_id"] for p in primary] != manifest["layout"]["point_ids"]
            or len({(p["point_id"], p["repeat_index"]) for p in points}) != len(points)
            or any(set(p["branches"]) != set(NAMES+(("Original_duplicate",) if p["repeat_index"] else ())) for p in points)):
        raise ValueError("Report thiếu/thừa/trùng point/branch hoặc trộn primary/repeat")
    analysis = Analysis()
    global_group = analysis.group(primary)
    # Đối soát toàn bộ140 tài khoản gốc trước khi dùng callback dựng subgroup.
    for repeat, stocks in source["accounts"].items():
        for symbol, branches in stocks.items():
            subset = [p for p in points if p["repeat_index"] == int(repeat) and p["symbol"] == symbol]
            for name, expected in branches.items():
                if content_hash(account(subset, name)) != content_hash(expected):
                    raise ValueError("Account nguồn khác engine vừa dựng lại")
    strata: dict[str, dict[str, Any]] = {}
    definitions = {
        "K": {str(k): lambda p, k=k: p["context"]["K"] == k for k in range(4)},
        "m": {str(m): lambda p, m=m: p["context"]["m"] == m for m in range(9)},
        "m_stratum": {"m=0": lambda p: p["context"]["m"] == 0, "m=1..3": lambda p: 1 <= p["context"]["m"] <= 3,
                       "m>=4": lambda p: p["context"]["m"] >= 4},
        "regime": {r: lambda p, r=r: p["context"]["regime"] == r for r in ("BULL", "BEAR", "CHOPPY", "CONSOLIDATION", "UNKNOWN")},
        "quarter": {"Q"+str(q): lambda p, q=q: (int(p["as_of_date"][5:7])-1)//3+1 == q for q in range(1, 5)},
        "feature_status": {s: lambda p, s=s: p["context"]["status"] == s for s in ("AVAILABLE", "UNAVAILABLE")},
        "support": {"K>=2_m>=2": lambda p: p["context"]["status"] == "AVAILABLE" and p["context"]["K"] >= 2 and p["context"]["m"] >= 2}}
    for family, predicates in definitions.items():
        strata[family] = {label: analysis.group([p for p in primary if predicate(p)]) for label, predicate in predicates.items()}
    prior_off = {n: analysis.group([p for p in primary if p["branches"][n]["shared_off_from"] is not None]) for n in VARIANTS[1:]}
    http = [r for r in ledger["requests"] if r.get("run_signature") == source["run_signature"]]
    def telemetry_for(name: str, repeats: set[int]) -> dict[str, Any]:
        """Invocation cùng ID/phase; không cộng timer invocation lồng với HTTP/pacing."""
        selected = [r for r in http if r["branch_id"] == name and r["improvement_audit"]["slot"]["repeat_index"] in repeats]
        ids = {r["invocation_id"] for r in selected if r.get("invocation_id")}
        invocations = {k: v for k, v in ledger.get("invocations", {}).items() if k in ids}
        return http_telemetry(selected, [source["run_signature"]], invocations)
    telemetry = {phase: {n: {"scientific_slots": sum(p["repeat_index"] in repeats for p in points if n in p["branches"]),
        "http": telemetry_for(n, repeats)}
        for n in (*VARIANTS, "Original_duplicate")} for phase, repeats in (("primary", {0}), ("repeat", {1, 2, 3}))}
    return {"status": "PASS", "phase": "development2023", "run_signature": source["run_signature"],
        "G": global_group, "support": {"planned_count": len(manifest["layout"]["point_ids"]), "complete_count": len(primary),
            "excluded": [], "feature_unavailable_retained": sum(p["context"]["status"] != "AVAILABLE" for p in primary)},
        "strata": strata, "prior_off": prior_off,
        "sensitivity": {b: analysis.sensitivity(primary, b) for b in REFERENCES},
        "repeat": repeat_report(points, [r["point_id"] for r in manifest["layout"]["repeat_selection"]], analysis),
        "approximation": approximation(primary), "telemetry": telemetry,
        "offline_latency": {n: {"value": None, "reason": "NOT_MEASURED_IN_FROZEN_AUDIT"} for n in OFFLINE},
        "all_primary_cases": deepcopy(primary), "account_contract": source["account_contract"],
        "nomination": "NOT_EVALUATED", "confirmation_allowed": False,
        "limitations": ["Development2023 đã exposed/adaptive; subgroup và repeat không thay G hoặc tạo xác nhận.",
            "Full−A so toàn phương pháp khác bank; không quy riêng gain cho Bayes.",
            "KL teacher không là nhãn thị trường; accuracy không là P&L; không claim hosted LLM tự tính Bayes.",
            "D là mean bốn tài khoản độc lập, không return portfolio; subgroup thiếu mã giữ D null.",
            "HTTP latency/pacing không là end-to-end; offline inference không được đo, không gán0.",
            "Engine cổ phiếu phân số, chưa lô chẵn; repeat reset trên sample12, không so trực tiếp full G60."]}


def rebuild(root: Path) -> dict[str, Any]:
    """Viện dẫn cold replay W11-03 theo hash, không chạy lại upstream/PIT/model đã khóa."""
    before = snapshot(root)
    if file_hash(root/ACCOUNTS) != ACCOUNTS_SHA256:
        raise ValueError("Account report khác byte W11-03 đã nghiệm thu")
    source = read_envelope(root/ACCOUNTS, ACCOUNT_VERSION)
    _, manifest, _ = verify_extension(root)
    for name in AUDIT_CODE:
        if file_hash(root/name) != source["binding"]["source_sha256"][name]:
            raise ValueError("Consumer account đã khóa bị sửa")
    git_value(root, "merge-base", "--is-ancestor", source["binding"]["source_commit"], "HEAD")
    git_value(root, "diff", "--exit-code", source["binding"]["source_commit"], "--", *AUDIT_CODE)
    if source["binding"]["runtime"] != manifest["runtime"] or any(source["binding"][k] != v for k, v in before.items()):
        raise ValueError("Account report khác runtime/ledger/run")
    result = build_report(source, manifest, read_json(root/LEDGER))
    if snapshot(root) != before or file_hash(root/ACCOUNTS) != ACCOUNTS_SHA256:
        raise ValueError("Bằng chứng bị đổi trong khi dựng báo cáo")
    commit = git_value(root, "log", "-1", "--format=%H", "--", *CODE)
    git_value(root, "diff", "--exit-code", commit, "--", *CODE)
    for name in CODE:
        git_value(root, "cat-file", "-e", commit+":"+name)
    result["binding"] = {"accounts_sha256": ACCOUNTS_SHA256, "run_tree_sha256": before["run_tree_sha256"],
        "ledger_sha256": before["ledger_sha256"], "source_commit": commit, "source_sha256": {n: file_hash(root/n) for n in CODE},
        "runtime": manifest["runtime"]}
    return result


def figure_bytes(report: dict[str, Any]) -> bytes:
    """Hình khoa học tĩnh từ cùng report; không dùng dữ liệu ngoài hoặc giấu nhánh bất lợi."""
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    stocks = report["G"]["stocks"]
    x = np.arange(len(SYMBOLS))
    for i, name in enumerate(NAMES):
        axes[0].bar(x+(i-3.5)*.10, [stocks[s][name]["account"]["metrics"]["total_return_pct"] for s in SYMBOLS],
                    width=.10, label=name)
    axes[0].axhline(0, color="black", linewidth=.6)
    axes[0].set(xticks=x, xticklabels=SYMBOLS, ylabel="Return tài khoản sau phí (%)", title="Development 2023 — tám nhánh, G=60")
    axes[0].legend(fontsize=7, ncol=2)
    rows = report["approximation"]["points"]
    axes[1].scatter([r["p_teacher"] for r in rows], [r["p_student"] for r in rows], alpha=.7)
    axes[1].plot([0, 1], [0, 1], color="gray", linewidth=.7)
    axes[1].axhline(.5, color="gray", linestyle=":")
    axes[1].axvline(.5, color="gray", linestyle=":")
    axes[1].set(xlim=(0, 1), ylim=(0, 1), xlabel="p teacher", ylabel="p student", title=f"Approximation — {len(rows)}/60 point có feature")
    fig.suptitle("Mô tả development; chưa là xác nhận độc lập", fontsize=11)
    fig.tight_layout()
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=150, metadata={"Software": "MT-BICL development report"})
    plt.close(fig)
    return buffer.getvalue()


def save_or_verify(root: Path, result: dict[str, Any], *, verify_only: bool = False) -> None:
    """Tái dựng cả JSON/hình; artifact khác dừng, không ghi đè báo cáo đã có."""
    path, figure = root/REPORT, root/FIGURE
    image = figure_bytes(result)
    if verify_only or path.exists():
        if content_hash(read_envelope(path, VERSION)) != content_hash(result):
            raise ValueError("Báo cáo khác số liệu/source vừa dựng lại")
    else:
        write_envelope(path, VERSION, result, immutable=True)
    if verify_only or figure.exists():
        if figure.read_bytes() != image:
            raise ValueError("Hình khác báo cáo vừa dựng lại")
    else:
        figure.write_bytes(image)
