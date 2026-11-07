"""Tổng hợp metrics, contrast và sensitivity của MT-BICL."""

from __future__ import annotations
from collections import Counter
from copy import deepcopy
import math
from typing import Any
from core.mt_bicl_bank import content_hash
from core.mt_bicl_accounting import account
from core.mt_bicl_audit import FULL, NAMES, SYMBOLS

REFERENCES = tuple(name for name in NAMES if name != FULL)

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
