"""Task context PIT và episode fallback U-BICL; thứ tự chọn không nhận outcome."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import date
import hashlib
import math
from pathlib import Path
from typing import Any

import pandas as pd

from core.historical_signals import digest
from core.bayesian_retriever import normalize_signals
from core.bayesian_memory import REGIMES, SYMBOLS
from core.price_feature_index import _json_bytes
from core.prior_example_selection import PriceExampleSelector
from core.prior_price_similarity import signal_price_scores
from core.research_cohort import read_envelope
from core.research_input_lock import runtime_identity
from core.unified_bayes_memory import UnifiedMemory, reject_decision
from core.unified_bayes_statistics import UnifiedBayesStatistics

VERSION = "unified_bayes_context_v1"
CHOICE_SHA = "32d0115b4f65bbd376d2f06ad7abee5f8004bff283d28580cc7a1759daaaa8e4"
DIAGNOSTICS_SHA = "575b650ceb88b7c69bdbe73786b1240d0a9f0bcc60b820f186b7486535993dca"
RANK_KEYS = {"episode_id", "cutoff_session", "entry_session", "exit_session", "age_days", "base_score", "feature_available", "feature_reasons"}


def reject_target(value: Any) -> None:
    """Chặn nhãn query kể cả khi lồng vào provenance feature."""
    if type(value) is dict:
        if {"outcome", "evaluation", "net_return_pct", "actual_direction", "entry_open", "exit_close", "label"}.intersection(value):
            raise ValueError("Feature query chứa nhãn/evaluation bị cấm")
        for child in value.values():
            reject_target(child)
    elif type(value) is list:
        for child in value:
            reject_target(child)


def task_block(cutoff_session: int) -> int:
    """Neo block từ phiên 0 của lịch train; không neo lại theo query."""
    if type(cutoff_session) is not int or cutoff_session < 0:
        raise ValueError("Vị trí phiên task phải là số nguyên gốc không âm")
    return cutoff_session // 90


def select_demonstrations(rows: list[dict[str, Any]], *, population: int,
                          symbol: str, regime: str) -> dict[str, Any]:
    """Chọn thuần từ metadata/score, kể cả khi thử đại diện kế sau xung đột."""
    _json_bytes(rows)
    if (type(rows) is not list or type(population) is not int or population < len(rows)
            or type(symbol) is not str or symbol not in SYMBOLS or type(regime) is not str or regime not in REGIMES):
        raise ValueError("Population/trace chọn task không hợp lệ")
    trace, groups, seen = [], {}, set()
    for item in rows:
        if (type(item) is not dict or set(item) != RANK_KEYS or type(item["episode_id"]) is not str
                or not item["episode_id"] or item["episode_id"] in seen
                or any(type(item[key]) is not int for key in ("cutoff_session", "entry_session", "exit_session", "age_days"))
                or not 0 <= item["cutoff_session"] < item["entry_session"] <= item["exit_session"]
                or item["age_days"] <= 0 or type(item["feature_available"]) is not bool
                or type(item["feature_reasons"]) is not list
                or any(type(value) is not str for value in item["feature_reasons"])):
            raise ValueError("Metadata ranking sai schema/PIT hoặc chứa nhãn")
        base = item["base_score"]
        if (base is not None and (type(base) not in (int, float) or not math.isfinite(base) or not 0 <= base <= 1)
                or item["feature_available"] != (base is not None)
                or item["feature_available"] and item["feature_reasons"]):
            raise ValueError("Similarity/coverage đại diện không hợp lệ")
        seen.add(item["episode_id"])
        row = deepcopy(item)
        row["task_id"] = f"{symbol}|{regime}|b{task_block(row['cutoff_session']):04d}"
        row["rank_score"] = None if base is None else float(base * 2 ** (-row["age_days"] / 365))
        row["reason_codes"] = []
        if row["age_days"] > 730:
            row["reason_codes"].append("PRIOR_TOO_OLD")
        if not row["feature_available"]:
            row["reason_codes"] += row["feature_reasons"] or ["FEATURE_UNAVAILABLE"]
        elif base < .625:
            row["reason_codes"].append("BELOW_MIN_SIMILARITY")
        if row["age_days"] <= 730:
            groups.setdefault(row["task_id"], []).append(row["episode_id"])
        trace.append(row)
    trace.sort(key=lambda row: row["episode_id"])
    qualified = [row for row in trace if not row["reason_codes"]]

    def conflicts(row: dict[str, Any], selected: list[dict[str, Any]], *, task: bool) -> list[str]:
        """Task kiểm cả gap lẫn interval đóng; fallback giữ đúng diversity A."""
        return [other["episode_id"] for other in selected
            if abs(row["cutoff_session"] - other["cutoff_session"]) < 5
            or task and max(row["entry_session"], other["entry_session"]) <= min(row["exit_session"], other["exit_session"])]

    order = lambda row: (-row["rank_score"], row["age_days"], row["task_id"], row["episode_id"])
    selected: list[dict[str, Any]] = []
    remaining = {key for key, ids in groups.items() if len(ids) >= 2}
    while remaining and len(selected) < 3:
        nominations = []
        for key in sorted(remaining):
            candidates = sorted((row for row in qualified if row["task_id"] == key
                                 and not conflicts(row, selected, task=True)), key=order)
            if candidates:
                nominations.append(candidates[0])
        if not nominations:
            break
        winner = min(nominations, key=order)
        selected.append(winner)
        remaining.remove(winner["task_id"])
    mode, reasons = "task", []
    if not selected:
        mode = "episode_fallback"
        reasons.append("NO_SUPPORTED_TASK_REPRESENTATIVE")
        for row in sorted(qualified, key=lambda value: (-value["rank_score"], -value["exit_session"], value["episode_id"])):
            if len(selected) < 3 and not conflicts(row, selected, task=False):
                selected.append(row)
    if population < 20:
        reasons.append("LOW_POPULATION")
    if not selected:
        reasons.append("NO_QUALIFIED_EXAMPLES")
    if population < 20 or not selected:
        selected, mode = [], "off"
    ids = [row["episode_id"] for row in selected]
    for row in trace:
        row["selected_order"] = ids.index(row["episode_id"]) + 1 if row["episode_id"] in ids else None
        row["conflicting_selected_ids"] = conflicts(row, [other for other in selected if other != row], task=mode == "task")
        if row["selected_order"] is None and not row["reason_codes"]:
            row["reason_codes"] = (["LOW_POPULATION"] if population < 20 else
                ["REPRESENTATIVE_CONFLICT"] if row["conflicting_selected_ids"] else
                ["TASK_SUPPORT_BELOW_TWO"] if mode == "task" and len(groups[row["task_id"]]) < 2 else
                ["NOT_SELECTED_BY_RANK_OR_TASK_LIMIT"])
    return {"context_mode": mode, "selected_ids": ids, "qualified_ids": [row["episode_id"] for row in qualified],
        "groups": {key: sorted(ids) for key, ids in sorted(groups.items())}, "trace": trace,
        "gate": {"ready": bool(ids), "reason_codes": reasons},
        "exclusion_counts": dict(sorted(Counter(reason for row in trace for reason in row["reason_codes"]).items()))}


def load_backbone_choice(memory: UnifiedMemory) -> dict[str, Any]:
    """Cold loader chỉ nhận hai artifact U10-04 thật và nguồn/code/runtime còn khớp."""
    from scripts.prepare_unified_bayes_pooling import NAMESPACE, choice_for_report, code_identity, load_protocol
    load_protocol()
    paths = {"backbone_choice_v1.json": CHOICE_SHA, "pooling_diagnostics_v1.json": DIAGNOSTICS_SHA}
    for name, expected in paths.items():
        if hashlib.sha256((NAMESPACE / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Choice/diagnostics khác artifact đã khóa; không chọn lại backbone")
    report = read_envelope(NAMESPACE / "pooling_diagnostics_v1.json")
    choice = read_envelope(NAMESPACE / "backbone_choice_v1.json")
    if (choice != choice_for_report(report, DIAGNOSTICS_SHA) or choice["code_sha256"] != code_identity()
            or choice["runtime"] != runtime_identity() or choice["memory_sha256"] != memory.identity
            or choice["index_sha256"] != memory.index.identity):
        raise ValueError("Choice không bind đúng nguồn/code/runtime/memory/index")
    root = Path(__file__).resolve().parents[1]
    for name, expected in report["sources"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Nguồn backbone thay đổi: {name}")
    return choice


class UnifiedBayesContext:
    """Dựng một base evidence dùng chung cho các projection; hot query thuần RAM."""

    def __init__(self, memory: UnifiedMemory, calendar: pd.DatetimeIndex) -> None:
        if not isinstance(memory, UnifiedMemory):
            raise ValueError("Context cần memory U-BICL đã xác minh")
        self.memory = memory
        self.choice = load_backbone_choice(memory)
        self.statistics = UnifiedBayesStatistics(memory)
        self.selector = PriceExampleSelector(memory.index, calendar)
        if self.selector.session_position("2018-01-02") != 0:
            raise ValueError("Lịch task không neo phiên train 02/01/2018")
        self.metadata = deepcopy(memory._metadata)

    def evidence(self, *, symbol: str, as_of_date: str, current_regime: str,
                 current_signals: dict[str, str], query_features: dict[str, Any]) -> dict[str, Any]:
        """Lọc PIT trước đọc outcome; summary không tác động selection hoặc posterior."""
        reject_decision(query_features)
        reject_target(query_features)
        stats = self.statistics.evidence(symbol=symbol, as_of_date=as_of_date,
            current_regime=current_regime, current_signals=current_signals)
        query = self.memory.index.transform_query(symbol, as_of_date, query_features)
        population = self.memory.eligible(symbol, as_of_date, regime=current_regime)
        self.memory.assert_evidence(population, symbol, as_of_date)
        if len(population) != stats["counts"]["nC"] + stats["counts"]["n1"] or any(row["regime"] != current_regime for row in population):
            raise ValueError("Population examples khác population PIT cùng regime")
        priors = self.memory.index.prior_features(symbol, as_of_date, [row["episode_id"] for row in population])
        rows, available = [], []
        for pos, (record, prior) in enumerate(zip(population, priors)):
            meta = self.metadata[record["episode_id"]]
            sessions = [self.selector.session_position(meta[key]) for key in ("as_of_date", "entry_date", "exit_date")]
            if sessions != [meta["cutoff_session_index"], sessions[0] + 1, sessions[0] + 3]:
                raise ValueError("Episode task khác lịch neo hoặc hợp đồng T+3")
            reasons = []
            if query["scaler_status"] != "AVAILABLE":
                reasons.append("SCALER_UNAVAILABLE")
            if query["feature_status"] != "AVAILABLE":
                reasons.append("QUERY_FEATURE_UNAVAILABLE")
            if prior["feature_status"] != "AVAILABLE":
                reasons.append("PRIOR_FEATURE_UNAVAILABLE")
            rows.append({"episode_id": record["episode_id"], "cutoff_session": sessions[0],
                "entry_session": sessions[1], "exit_session": sessions[2],
                "age_days": (date.fromisoformat(as_of_date) - date.fromisoformat(record["as_of_date"])).days,
                "base_score": None, "feature_available": not reasons, "feature_reasons": reasons})
            if not reasons:
                available.append(pos)
        scores = signal_price_scores(query_signals=current_signals,
            prior_signals=[population[pos]["agent_signals"] for pos in available], query_vector=query["scaled_vector"],
            prior_vectors=[priors[pos]["scaled_vector"] for pos in available]) if available else []
        for pos, score in zip(available, scores):
            rows[pos]["base_score"] = score["base_score"]
        selection = select_demonstrations(rows, population=len(population), symbol=symbol, regime=current_regime)
        by_id = {row["episode_id"]: row for row in population}
        # Nhãn chỉ tham gia summary/hiển thị sau khi representative và mode đã chọn xong.
        groups = {key: {"episode_ids": ids, "n": len(ids),
            "s": sum(int(by_id[name]["outcome"]["net_return_pct"] > 0) for name in ids)}
            for key, ids in selection["groups"].items()}
        trace = {row["episode_id"]: row for row in selection["trace"]}
        examples = [{"episode_id": key, "task_id": trace[key]["task_id"],
            "as_of_date": by_id[key]["as_of_date"], "entry_date": by_id[key]["entry_date"], "exit_date": by_id[key]["exit_date"],
            "trend": normalize_signals(by_id[key]["agent_signals"])["trend"],
            "pattern": normalize_signals(by_id[key]["agent_signals"])["pattern"],
            "net_return_pct": float(by_id[key]["outcome"]["net_return_pct"])} for key in selection["selected_ids"]]
        model = "A_tp_pool" if self.choice["lambda"] is None else f"pool_{self.choice['lambda']}"
        result = {"context_version": VERSION, "choice_sha256": CHOICE_SHA,
            "memory_sha256": self.statistics.memory_identity, "index_sha256": self.memory.index.identity,
            "query": {key: stats[key] for key in ("symbol", "as_of_date", "current_regime", "current_signals")},
            "query_features_sha256": digest(query_features), "query_transform": query,
            "calendar": self.selector.calendar_metadata(as_of_date), "statistics": stats,
            "posterior": deepcopy(stats["posteriors"][model]), "context_mode": selection["context_mode"],
            "selection": selection, "task_groups": groups, "examples": examples}
        _json_bytes(result)
        result["base_evidence_sha256"] = digest(result)
        return result

    def validate(self, evidence: dict[str, Any], query_features: dict[str, Any]) -> None:
        """Tái dựng từ nguồn RAM để chặn sửa counts, mode, membership, score hoặc tự reseal."""
        _json_bytes(evidence)
        if type(evidence) is not dict or type(evidence.get("query")) is not dict:
            raise ValueError("Context thiếu query")
        expected = self.evidence(**evidence["query"], query_features=query_features)
        if digest(expected) != digest(evidence):
            raise ValueError("Context khác evidence PIT/selection/posterior đã tái dựng")

    def render(self, evidence: dict[str, Any], branch: str, query_features: dict[str, Any]) -> dict[str, Any]:
        """Biên tin cậy: kiểm semantic trước projection/renderer, không gọi LLM."""
        from core.unified_bayes_prompt import render_context
        self.validate(evidence, query_features)
        return render_context(evidence, branch)
