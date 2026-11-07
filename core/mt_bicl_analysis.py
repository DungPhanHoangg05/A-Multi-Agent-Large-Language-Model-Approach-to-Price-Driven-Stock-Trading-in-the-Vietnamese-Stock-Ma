"""Phân tích development MT-BICL, tách account return/accuracy và các bước sửa quyết định."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from itertools import combinations
import math
from typing import Any

from core.backtest_engine import compute_round_trip_net_return
from core.mt_bicl_bank import content_hash
from core.mt_bicl_reporting import Analysis, actions
from core.mt_bicl_audit import FULL, NAMES, VIRTUAL, SYMBOLS, cash_action
from core.research_metrics import http_telemetry

VERSION = "utility_icl_development_analysis_v3"
REFERENCES = tuple(n for n in NAMES if n != FULL)
RULES = {"G": 60, "D_Full_Original_strict_min": 0, "positive_symbols_min": 3,
    "D_Full_A_inclusive_min": 0, "mean_delta_MDD_max_pp": 2, "max_delta_MDD_max_pp": 5,
    "candidate_substitution": False, "D_Full_Fact_Anchor_strict_min": 0,
    "candidate_only": FULL, "no_repeat_vote": True}


def validate_economics(points: list[dict[str, Any]]) -> None:
    """Bắt nhãn/đơn vị sai, không để accuracy hoặc sensitivity dùng outcome khác engine."""
    for point in points:
        value = point["evaluation"]
        expected = float(compute_round_trip_net_return(value["entry_open"], value["exit_close"]))
        if (value["net_return_long"] != expected or value["actual_direction"] != ("UP" if expected > 0 else "DOWN")):
            raise ValueError("Nhãn kinh tế/return khác helper engine")


def group(points: list[dict[str, Any]], analysis: Analysis, names: tuple[str, ...] = NAMES) -> dict[str, Any]:
    """Mean đều bốn account; subgroup thiếu mã giữ null, không chọn lại support."""
    stocks = {s: {n: analysis.metric([p for p in points if p["symbol"] == s], n) for n in names} for s in SYMBOLS}
    branches = {}
    for name in names:
        available = [stocks[s][name]["account"]["metrics"] for s in SYMBOLS if stocks[s][name]["account"] is not None]
        branches[name] = {"count": len(points), "long_count": sum(cash_action(p["branches"][name]["action"]) == "LONG" for p in points),
            "accuracy": sum((cash_action(p["branches"][name]["action"]) == "LONG") == (p["evaluation"]["actual_direction"] == "UP") for p in points)/len(points) if points else None,
            "mean_account_return_pct": math.fsum(m["total_return_pct"] for m in available)/4 if len(available) == 4 else None,
            "mean_account_mdd_pct": math.fsum(m["max_drawdown_pct"] for m in available)/4 if len(available) == 4 else None,
            "contributing_symbols": len(available)}
    return {"point_ids": [p["point_id"] for p in points], "count": len(points), "stocks": stocks,
        "branches": branches, "contrasts": {b: analysis.contrast(points, FULL, b) for b in REFERENCES}}


def sensitivity(points: list[dict[str, Any]], reference: str, analysis: Analysis) -> dict[str, Any]:
    """Hoàn nguyên một action khác biệt, giữ G; báo cả tác động thuận và bất lợi."""
    base = analysis.contrast(points, FULL, reference)
    by_symbol = {s: base["by_symbol"][s]["delta_return_pp"] for s in SYMBOLS}
    cases = []
    for point in points:
        a, b = (cash_action(point["branches"][n]["action"]) for n in (FULL, reference))
        if a == b: continue
        changed = deepcopy(point)
        changed["branches"][FULL]["action"] = b
        sample = [changed if p["point_id"] == point["point_id"] else p for p in points if p["symbol"] == point["symbol"]]
        counter = analysis.contrast(sample, FULL, reference)["by_symbol"][point["symbol"]]["delta_return_pp"]
        delta = point["evaluation"]["net_return_long"]*((a == "LONG")-(b == "LONG"))
        cases.append({"point_id": point["point_id"], "transition": b+"_TO_"+a,
            "cycle_delta_pct": delta*100, "cycle_effect": "BENEFICIAL" if delta > 0 else "ADVERSE" if delta < 0 else "ZERO",
            "D_after_reverting_change_pp": (math.fsum(v for s, v in by_symbol.items() if s != point["symbol"])+counter)/4})
    return {"leave_one_change_out": cases,
        "leave_one_symbol_out": {s: math.fsum(v for k, v in by_symbol.items() if k != s)/3 for s in SYMBOLS},
        "note": "Hoàn nguyên action, không bỏ point; cycle delta không cộng thành D tài khoản"}


def decomposition(points: list[dict[str, Any]], analysis: Analysis) -> dict[str, Any]:
    """Phân rã telescoping theo return account; không gán tương phản quan sát thành nhân quả."""
    chain = ("Original", "Fact_Anchor", VIRTUAL[0], VIRTUAL[1], FULL)
    steps = [analysis.contrast(points, a, b) for b, a in zip(chain, chain[1:])]
    total = analysis.contrast(points, FULL, "Original")["mean_delta_return_pp"]
    if not math.isclose(math.fsum(x["mean_delta_return_pp"] for x in steps), total, rel_tol=0, abs_tol=1e-10):
        raise ValueError("Phân rã account không khép tổng Full−Original")
    changes = []
    for point in points:
        branch = point["branches"][FULL]
        raw, facts, final = (cash_action(point["branches"][n]["action"]) for n in (*VIRTUAL, FULL))
        delta = point["evaluation"]["net_return_long"]*((final == "LONG")-(raw == "LONG"))
        changes.append({"point_id": point["point_id"], "anchor": branch["policy"]["anchor_action"],
            "raw_proposed_action": branch["raw_proposed_action"], "proposal_or_anchor": raw, "facts_validated": facts,
            "final_action": final, "reason": branch["policy"]["reason"], "bypass": branch["bypass"],
            "q10_delta_U_net_fraction": branch["policy"]["q10_delta_U_net_fraction"],
            "final_minus_raw_cycle_pct": delta*100,
            "effect": "BENEFICIAL" if delta > 0 else "ADVERSE" if delta < 0 else "UNCHANGED_OR_ZERO"})
    return {"chain": list(chain), "steps": steps, "total_Full_Original_pp": total,
        "reason_counts": dict(Counter(p["branches"][FULL]["policy"]["reason"] for p in points)),
        "policy_effect_on_raw_proposals": dict(Counter(p["effect"] for p in changes)), "cases": changes,
        "interpretation": "Counterfactual trên saved actions/payoff; các prompt có response LLM độc lập, không là hiệu ứng nhân quả thuần"}


def repeats(points: list[dict[str, Any]], selected: list[str], analysis: Analysis) -> dict[str, Any]:
    """Chẩn đoán cùng12 point/lượt0..3, không vote hoặc đưa repeat vào primary."""
    blocks = {(p["point_id"], p["repeat_index"]): p for p in points if p["point_id"] in selected}
    if set(blocks) != {(pid, r) for pid in selected for r in range(4)}: raise ValueError("Repeat sai mẫu/lượt")
    groups = {str(r): group([blocks[(pid, r)] for pid in selected], analysis, NAMES+(("Original_duplicate",) if r else ())) for r in range(4)}
    disagreements = {}
    for name in NAMES:
        pairs = [(pid, a, b, blocks[(pid, a)]["branches"][name]["action"], blocks[(pid, b)]["branches"][name]["action"])
                 for pid in selected for a, b in combinations(range(4), 2)]
        disagreements[name] = {"dependent_pairs": len(pairs), "disagreements": sum(cash_action(a) != cash_action(b) for _, _, _, a, b in pairs)}
    duplicates = [blocks[(pid, r)] for pid in selected for r in (1, 2, 3)]
    return {"selected_point_ids": selected, "groups": groups, "disagreement": disagreements,
        "Original_duplicate": actions(duplicates, "Original_duplicate", "Original"),
        "D_by_repeat": {b: [groups[str(r)]["contrasts"][b]["mean_delta_return_pp"] for r in range(4)] for b in REFERENCES},
        "note": "Mẫu có chủ đích sau MT-BICL; account reset trên12 point, không so trực tiếp return với full G60"}


def build_report(source: dict[str, Any], protocol: dict[str, Any], ledger: dict[str, Any]) -> dict[str, Any]:
    """Consumer chỉ dùng action/economics đã audit, không source thị trường hoặc model mới."""
    if source["status"] != "PASS" or source["phase"] != "development2023" or source["confirmation_allowed"] is not False:
        raise ValueError("Chỉ nhận account development đã audit")
    points = source["points"]
    validate_economics(points)
    primary = [p for p in points if p["repeat_index"] == 0]
    if ([p["point_id"] for p in primary] != protocol["development"]["point_ids"] or len(primary) != 60
            or len({(p["point_id"], p["repeat_index"]) for p in points}) != len(points)
            or any(set(p["branches"]) != set((*NAMES, *VIRTUAL, *(("Original_duplicate",) if p["repeat_index"] else ()))) for p in points)):
        raise ValueError("Sai G60/matrix hoặc trộn repeat vào primary")
    analysis = Analysis()
    for r, stocks in source["accounts"].items():
        for symbol, branches in stocks.items():
            sample = [p for p in points if p["repeat_index"] == int(r) and p["symbol"] == symbol]
            for name, expected in branches.items():
                actual = analysis.metric(sample, name)["account"]
                normalized = deepcopy(expected)
                # Analysis trình bày null cho hit-rate/avg-trade khi không LONG; engine nguồn giữ0.
                if not analysis.metric(sample, name)["long_count"]:
                    normalized["metrics"].update(hit_rate_pct=None, avg_trade_pct=None)
                if content_hash(actual) != content_hash(normalized): raise ValueError("Account nguồn khác engine")
    definitions = {"K": {str(k): lambda p, k=k: p["context"]["K"] == k for k in range(4)},
        "m": {str(m): lambda p, m=m: p["context"]["m"] == m for m in range(9)},
        "m_stratum": {"m=0": lambda p: p["context"]["m"] == 0, "m=1..3": lambda p: 1 <= p["context"]["m"] <= 3,
                       "m>=4": lambda p: p["context"]["m"] >= 4},
        "regime": {s: lambda p, s=s: p["context"]["regime"] == s for s in ("BULL", "BEAR", "CHOPPY", "CONSOLIDATION", "UNKNOWN")},
        "bucket": {s: lambda p, s=s: p["context"]["bucket"] == s for s in ("MACD_POS_PRICE_POS", "MACD_POS_PRICE_NEG", "MACD_NEG_PRICE_POS", "MACD_NEG_PRICE_NEG", "UNKNOWN")},
        "support": {"SUPPORTED": lambda p: p["context"]["full_supported"], "UNSUPPORTED": lambda p: not p["context"]["full_supported"]},
        "quarter": {"Q"+str(q): lambda p, q=q: (int(p["as_of_date"][5:7])-1)//3+1 == q for q in range(1, 5)}}
    strata = {family: {label: group([p for p in primary if predicate(p)], analysis) for label, predicate in defs.items()} for family, defs in definitions.items()}
    own = [r for r in ledger["requests"] if r.get("run_signature") == source["run_signature"]]
    telemetry = {}
    for name in (*NAMES[:-1], "Original_duplicate"):
        rows = [r for r in own if r["branch_id"] == name]
        ids = {r["invocation_id"] for r in rows if r.get("invocation_id")}
        telemetry[name] = http_telemetry(rows, [source["run_signature"]], {k:v for k,v in ledger.get("invocations", {}).items() if k in ids})
    return {"status": "PASS", "phase": "development2023", "run_signature": source["run_signature"],
        "binding": {"accounts_payload_sha256": content_hash(source), **source["binding"]}, "G": group(primary, analysis),
        "primary_cases": deepcopy(primary), "strata": strata, "decomposition": decomposition(primary, analysis),
        "sensitivity": {b: sensitivity(primary, b, analysis) for b in REFERENCES},
        "repeat": repeats(points, protocol["development"]["repeat_selection"]["point_ids"], analysis),
        "telemetry": telemetry, "approximation_frozen": {p["point_id"]: p.get("approximation") for p in primary},
        "nomination": "NOT_EVALUATED", "confirmation_allowed": False,
        "limitations": ["Development2023 adaptive/exposed; chưa phải kiểm định xác nhận.",
            "Accuracy là dự báo dấu lợi nhuận LONG sau phí, khác hit-rate lệnh LONG và khác return account.",
            "D là mean đều bốn account, không mean cycle hoặc return portfolio; cổ phiếu phân số, chưa lô chẵn.",
            "Repeat có chủ đích/phụ thuộc, không tăng N và không vote/chọn lượt tốt nhất.",
            "Decomposition là counterfactual quan sát saved actions; không quy mọi gain cho Bayes.",
            "Không dùng CI development để nominate; bootstrap xác nhận chỉ áp dụng khi có release riêng."]}


def nominate(report: dict[str, Any], protocol: dict[str, Any]) -> dict[str, Any]:
    """Tái dựng G/account rồi áp dụng đúng rule trước run, chỉ đề cử Full primary."""
    rules = protocol["development"]["nomination"]
    if (rules != RULES or report["status"] != "PASS" or report["phase"] != "development2023"
            or report["nomination"] != "NOT_EVALUATED" or report["confirmation_allowed"] is not False):
        raise ValueError("Rule/report nomination sai revision hoặc quyền")
    points = report["primary_cases"]
    validate_economics(points)
    if ([p["point_id"] for p in points] != protocol["development"]["point_ids"] or len(points) != 60
            or len({p["point_id"] for p in points}) != 60
            or any(p["repeat_index"] != 0 or p["as_of_date"][:4] != "2023"
                   or p["symbol"] != p["point_id"][:3] or p["as_of_date"] != p["point_id"][4:] for p in points)
            or Counter(p["symbol"] for p in points) != {"FPT": 12, "MWG": 16, "VCB": 16, "VNM": 16}):
        raise ValueError("Nomination phải đủ primary G60, không vote repeat hoặc lọc point")
    actual = group(points, Analysis())
    if content_hash(actual) != content_hash(report["G"]): raise ValueError("Metric nomination khác account vừa tái dựng")
    contrasts = actual["contrasts"]
    d = contrasts["Original"]["mean_delta_return_pp"]
    a = contrasts["A_reference"]["mean_delta_return_pp"]
    f = contrasts["Fact_Anchor"]["mean_delta_return_pp"]
    delta_mdd = [contrasts["Original"]["by_symbol"][s]["delta_mdd_pp"] for s in SYMBOLS]
    positive = sum(contrasts["Original"]["by_symbol"][s]["delta_return_pp"] > 0 for s in SYMBOLS)
    checks = {"complete_G60": True, "D_Full_Original_gt_0": d > 0, "positive_symbols_at_least_3": positive >= 3,
        "D_Full_A_ge_0": a >= 0, "D_Full_Fact_Anchor_gt_0": f > 0,
        "mean_delta_MDD_le_2": math.fsum(delta_mdd)/4 <= 2, "max_delta_MDD_le_5": max(delta_mdd) <= 5}
    passed = all(checks.values())
    return {"status": "NOMINATED" if passed else "NOT_NOMINATED", "candidate_evaluated": FULL,
        "nominated_candidate": FULL if passed else None, "candidate_substitution": False, "rules": rules,
        "checks": checks, "failure_reasons": [k for k,v in checks.items() if not v],
        "metrics": {"D_Full_Original_pp": d, "D_Full_A_pp": a, "D_Full_Fact_Anchor_pp": f,
            "positive_symbols": positive, "mean_delta_MDD_pp": math.fsum(delta_mdd)/4, "max_delta_MDD_pp": max(delta_mdd)},
        "confirmation": {"allowed": False, "status": "REQUIRES_EXPOSURE_AUDIT_AND_SEPARATE_RELEASE" if passed else "NOT_RUN_NOT_NOMINATED"}}


def figure_bytes(report: dict[str, Any]) -> bytes:
    """Hình tĩnh mô tả return và accuracy riêng, không hàm ý xác nhận độc lập."""
    import io
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    values = report["G"]["branches"]
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.8), layout="constrained")
    y = list(range(len(NAMES)))
    for axis, numbers, title, color in ((axes[0], [values[n]["mean_account_return_pct"] for n in NAMES], "Return trung bình 4 tài khoản (%)", "#276b8f"),
                                       (axes[1], [100*values[n]["accuracy"] for n in NAMES], "Accuracy dấu lợi nhuận LONG sau phí (%)", "#c67b2a")):
        axis.barh(y, numbers, color=color)
        axis.set_yticks(y, NAMES if axis is axes[0] else [""]*len(NAMES))
        axis.invert_yaxis()
        axis.axvline(0, color="#777777", linewidth=.7)
        axis.set_xlabel(title)
        axis.grid(axis="x", alpha=.2)
        for i, value in enumerate(numbers): axis.annotate(f"{value:.2f}", (value, i), xytext=(4 if value >= 0 else -4, 0), textcoords="offset points", ha="left" if value >= 0 else "right", va="center", fontsize=8)
        axis.margins(x=.2)
    fig.suptitle("Development2023, G60 — dữ liệu đã exposed; chưa là kết quả xác nhận")
    output = io.BytesIO()
    fig.savefig(output, format="png", dpi=160, metadata={"Software": "utility-icl-development-MT-BICL"})
    plt.close(fig)
    return output.getvalue()
