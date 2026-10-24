"""Lịch train, loss và gate chọn backbone U-BICL theo rule đã khóa trước diagnostics."""

from __future__ import annotations

from copy import deepcopy
import math
from typing import Any

import numpy as np
import pandas as pd

from core.bayesian_memory import iso_date
from core.price_feature_index import SYMBOLS, TRAIN_END, _hash, _json_bytes
from core.unified_bayes_memory import UnifiedMemory
from core.unified_bayes_statistics import LAMBDAS, MODELS

VERSION = "unified_pooling_diagnostics_v1"
SELECTION_VERSION = "unified_backbone_choice_v1"
FOLD_DATES = {"train_2021": ("2021-01-04", "2021-12-31"), "train_2022": ("2022-01-06", "2022-12-30")}
SCORE_KEYS = {"episode_id", "symbol", "as_of_date", "exit_date", "fold_id", "label", "net_long_return", "probability", "ready"}


def fold_schedule(memory: UnifiedMemory, calendar: pd.DatetimeIndex, protocol: dict[str, Any], *,
                  enforce_locked: bool = True) -> dict[str, Any]:
    """Purge cả hai biên fold, kiểm scaler train-only và hash IDs của 647 query."""
    metadata = sorted(deepcopy(list(memory._metadata.values())), key=lambda row: row["episode_id"])
    index = memory.index.payload
    if (not isinstance(calendar, pd.DatetimeIndex) or calendar.empty or calendar.hasnans
            or calendar.tz is not None or not calendar.is_unique or not calendar.is_monotonic_increasing
            or not calendar.equals(calendar.normalize())
            or _hash(calendar[calendar <= TRAIN_END].strftime("%Y-%m-%d").tolist()) != index["train_material"]["calendar_sha256"]):
        raise ValueError("Lịch diagnostics khác lịch train đã bind trong index")
    positions = np.column_stack([calendar.get_indexer(pd.to_datetime([row[key] for row in metadata]))
                                 for key in ("as_of_date", "entry_date", "exit_date")])
    if ((positions < 0).any() or (positions[:, 1] != positions[:, 0] + 1).any()
            or (positions[:, 2] != positions[:, 0] + 3).any()):
        raise ValueError("Metadata diagnostics sai chu kỳ Open(t+1)/Close(t+3)")
    indexed = {row["episode_id"]: row for row in index["records"]}
    folds = {}
    for spec in protocol["offline_selection"]["folds"]:
        name = spec["fold_id"]
        if name not in FOLD_DATES or (spec["query_start"], spec["query_end"]) != FOLD_DATES[name]:
            raise ValueError("Fold diagnostics khác ngày train đã khóa")
        start, end = FOLD_DATES[name]
        queries = [row for row in metadata if start <= row["as_of_date"] <= end]
        kept = [row for row in queries if row["exit_date"] <= end]
        kept_ids = [row["episode_id"] for row in kept]
        purged_end = [row["episode_id"] for row in queries if row["exit_date"] > end]
        if enforce_locked and (len(queries) != spec["query_count_before_end_purge"]
                or len(kept) != spec["query_count"] or _hash(kept_ids) != spec["query_ids_sha256"]
                or purged_end != spec["purged_query_ids"]):
            raise ValueError("Số query/IDs/purge khác protocol 647 query, không dùng mẫu số legacy 651")
        symbols = {}
        for symbol in SYMBOLS:
            rows = [row for row in metadata if row["symbol"] == symbol]
            fit = [row["episode_id"] for row in rows if row["exit_date"] < start]
            feature_fit = [key for key in fit if indexed[key]["features"]["status"] == "AVAILABLE"]
            scaler = memory.index.scaler(symbol, start, fold_id=name)
            if (scaler["fit_episode_ids"] != feature_fit or scaler["fit_inclusive"] is not False
                    or scaler["freeze_date"] != start or scaler["fit_cutoff"] != start):
                raise ValueError("Scaler diagnostics chứa episode vắt biên hoặc không freeze đầu fold")
            symbols[symbol] = {"fit_closed_ids": fit, "fit_feature_ids": feature_fit,
                "purged_at_start_ids": [row["episode_id"] for row in rows if row["as_of_date"] < start <= row["exit_date"]],
                "query_ids": [row["episode_id"] for row in kept if row["symbol"] == symbol],
                "scaler": scaler}
        folds[name] = {"query_start": start, "query_end": end, "query_ids": kept_ids,
            "purged_at_end_ids": purged_end, "symbols": symbols}
    if set(folds) != set(FOLD_DATES):
        raise ValueError("Diagnostics thiếu hai fold đã khóa")
    return folds


def score_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Chấm cùng giao raw hữu hạn của A và ba lambda, trước readiness, không refit."""
    _json_bytes(rows)
    if type(rows) is not list:
        raise ValueError("Điểm scoring phải là danh sách JSON")
    seen, cycles = set(), set()
    for row in rows:
        if type(row) is not dict or set(row) != SCORE_KEYS:
            raise ValueError("Schema điểm scoring không khớp")
        symbol, fold = row["symbol"], row["fold_id"]
        if (type(row["episode_id"]) is not str or not row["episode_id"].strip()
                or row["episode_id"] in seen or type(symbol) is not str or symbol not in SYMBOLS
                or type(fold) is not str or fold not in FOLD_DATES):
            raise ValueError("Scoring trùng ID hoặc sai mã/fold")
        seen.add(row["episode_id"])
        start, end = FOLD_DATES[fold]
        cutoff, exit_date = iso_date(row["as_of_date"]), iso_date(row["exit_date"])
        if (symbol, cutoff) in cycles:
            raise ValueError("Scoring trùng cycle dưới ID khác")
        cycles.add((symbol, cutoff))
        net = row["net_long_return"]
        if (not start <= cutoff < exit_date <= end or type(net) not in (int, float) or not math.isfinite(net)
                or type(row["label"]) is not int or row["label"] not in (0, 1) or row["label"] != int(net > 0)):
            raise ValueError("Target scoring sai fold/purge hoặc khác dấu LONG ròng")
        if any(type(row[key]) is not dict or set(row[key]) != set(MODELS) for key in ("probability", "ready")):
            raise ValueError("Scoring thiếu A hoặc một lambda trong giao chung")
        for name in MODELS:
            p, ready = row["probability"][name], row["ready"][name]
            if (type(ready) is not bool or ready and p is None or p is not None
                    and (type(p) not in (int, float) or not math.isfinite(p) or not 0 <= p <= 1)):
                raise ValueError("Raw posterior/readiness scoring không hợp lệ")
    rows = sorted(rows, key=lambda row: (row["as_of_date"], SYMBOLS.index(row["symbol"]), row["episode_id"]))

    def group(values: list[dict[str, Any]]) -> dict[str, Any]:
        """Mỗi query có trọng số như nhau, không bình quân loss các ô khác mẫu số."""
        common = [row for row in values if all(row["probability"][name] is not None for name in MODELS)]
        coverage, loss = {}, {}
        for name in MODELS:
            coverage[name] = {"raw_count": sum(row["probability"][name] is not None for row in values),
                "ready_count": sum(row["ready"][name] for row in values),
                "missing_ids": [row["episode_id"] for row in values if row["probability"][name] is None]}
            if common:
                p = np.asarray([row["probability"][name] for row in common], dtype=float)
                y = np.asarray([row["label"] for row in common], dtype=float)
                clipped = np.clip(p, 1e-6, 1 - 1e-6)
                loss[name] = {"brier": float(np.mean((p - y) ** 2)),
                    "log_loss": float(np.mean(-(y * np.log(clipped) + (1 - y) * np.log(1 - clipped))))}
            else:
                loss[name] = {"brier": None, "log_loss": None, "reason": "NO_COMMON_POSTERIOR"}
        return {"query_count": len(values), "query_ids": [row["episode_id"] for row in values],
            "common_count": len(common), "common_ids": [row["episode_id"] for row in common], "coverage": coverage, "loss": loss}

    return {"return_unit": "fraction", "weighting": "equal_query", "overall": group(rows),
        "by_fold": {fold: group([r for r in rows if r["fold_id"] == fold]) for fold in FOLD_DATES},
        "by_symbol": {s: group([r for r in rows if r["symbol"] == s]) for s in SYMBOLS},
        "by_fold_symbol": {f"{f}/{s}": group([r for r in rows if r["fold_id"] == f and r["symbol"] == s])
                           for f in FOLD_DATES for s in SYMBOLS}}


def pooling_gate(reference: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Gate một lần cho lambda đứng đầu, không nhận runner-up khi trượt."""
    if (type(reference) is not dict or set(reference) != {"log_loss", "brier", "ready"}
            or type(candidate) is not dict or set(candidate) != {
                "log_loss", "brier", "ready", "max_symbol_brier_increase", "all_strata_have_common"}):
        raise ValueError("Gate pooling thiếu diagnostics")
    for value in (reference["log_loss"], reference["brier"], candidate["log_loss"], candidate["brier"], candidate["max_symbol_brier_increase"]):
        if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
            raise ValueError("Diagnostics gate pooling không hữu hạn")
    for item in (reference, candidate):
        if (item["log_loss"] is not None and item["log_loss"] < 0
                or item["brier"] is not None and not 0 <= item["brier"] <= 1):
            raise ValueError("Loss gate pooling ngoài miền hợp lệ")
    if any(type(item["ready"]) is not int or item["ready"] < 0 for item in (reference, candidate)) or type(candidate["all_strata_have_common"]) is not bool:
        raise ValueError("Coverage gate pooling sai kiểu")
    reasons = []
    if not candidate["all_strata_have_common"]:
        reasons.append("MISSING_COMMON_FOLD_SYMBOL_STRATUM")
    if any(value is None for value in (reference["log_loss"], reference["brier"], candidate["log_loss"], candidate["brier"], candidate["max_symbol_brier_increase"])):
        reasons.append("MISSING_LOSS_DIAGNOSTICS")
    else:
        if candidate["log_loss"] > reference["log_loss"]:
            reasons.append("LOG_LOSS_REGRESSION")
        if candidate["brier"] > reference["brier"]:
            reasons.append("BRIER_REGRESSION")
        if not (candidate["log_loss"] < reference["log_loss"] or candidate["brier"] < reference["brier"]):
            reasons.append("NO_STRICT_IMPROVEMENT")
        if candidate["max_symbol_brier_increase"] > .01:
            reasons.append("SYMBOL_BRIER_REGRESSION")
    if candidate["ready"] < reference["ready"]:
        reasons.append("READY_COVERAGE_REDUCTION")
    return {"accepted": not reasons, "reason_codes": reasons}


def rank_lambdas(metrics: list[list[int | float]]) -> int:
    """Rank tuple loss/Brier/lambda bằng đầy đủ precision, không làm tròn."""
    if type(metrics) is not list or len(metrics) != 3:
        raise ValueError("Ranking cần đủ ba lambda đã khóa")
    for row in metrics:
        if (type(row) is not list or len(row) != 3 or type(row[0]) is not int or row[0] not in LAMBDAS
                or any(type(value) not in (int, float) or not math.isfinite(value) for value in row[1:])
                or row[1] < 0 or not 0 <= row[2] <= 1):
            raise ValueError("Loss ranking thiếu hoặc không hữu hạn")
    if {row[0] for row in metrics} != set(LAMBDAS):
        raise ValueError("Lambda ranking thiếu/trùng")
    return int(min(metrics, key=lambda row: (row[1], row[2], row[0]))[0])


def select_backbone(summary: dict[str, Any]) -> dict[str, Any]:
    """Chọn đúng winner rồi gate; thiếu support giữ A cùng reason, không thử lambda khác."""
    _json_bytes(summary)
    required = {f"{f}/{s}" for f in FOLD_DATES for s in SYMBOLS}
    if (type(summary) is not dict or set(summary) != {"return_unit", "weighting", "overall", "by_fold", "by_symbol", "by_fold_symbol"}
            or summary["return_unit"] != "fraction" or summary["weighting"] != "equal_query"
            or any(type(summary[key]) is not dict for key in ("overall", "by_fold", "by_symbol", "by_fold_symbol"))
            or set(summary["by_fold_symbol"]) != required or set(summary["by_symbol"]) != set(SYMBOLS)
            or set(summary["by_fold"]) != set(FOLD_DATES)):
        raise ValueError("Summary chọn backbone thiếu fold/mã hoặc sai weighting")
    for group in (summary["overall"], *summary["by_fold"].values(), *summary["by_symbol"].values(), *summary["by_fold_symbol"].values()):
        if (type(group) is not dict or set(group) != {"query_count", "query_ids", "common_count", "common_ids", "coverage", "loss"}
                or type(group["query_count"]) is not int or type(group["common_count"]) is not int
                or not 0 <= group["common_count"] <= group["query_count"]
                or len(group["query_ids"]) != group["query_count"] or len(group["common_ids"]) != group["common_count"]
                or type(group["coverage"]) is not dict or set(group["coverage"]) != set(MODELS)
                or type(group["loss"]) is not dict or set(group["loss"]) != set(MODELS)):
            raise ValueError("Diagnostics summary thiếu mẫu số/IDs/model")
        for name in MODELS:
            loss, coverage = group["loss"][name], group["coverage"][name]
            if (type(loss) is not dict or not {"log_loss", "brier"} <= loss.keys()
                    or type(coverage) is not dict or set(coverage) != {"raw_count", "ready_count", "missing_ids"}
                    or any(type(coverage[key]) is not int or not 0 <= coverage[key] <= group["query_count"]
                           for key in ("raw_count", "ready_count")) or coverage["ready_count"] > coverage["raw_count"]):
                raise ValueError("Summary loss/coverage không hợp lệ")
            for key in ("log_loss", "brier"):
                value = loss[key]
                if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0
                                          or key == "brier" and value > 1):
                    raise ValueError("Summary chứa loss sai miền hoặc không hữu hạn")
    overall = summary["overall"]
    all_strata = all(item["common_count"] > 0 for item in summary["by_fold_symbol"].values())
    losses = overall["loss"]
    if set(losses) != set(MODELS) or set(overall["coverage"]) != set(MODELS):
        raise ValueError("Summary thiếu model posterior")
    available = all(losses[name][key] is not None for name in MODELS for key in ("log_loss", "brier"))
    if not available:
        return {"selection_version": SELECTION_VERSION, "choice": "A_tp_pool", "lambda": None,
            "ranked_lambda": None, "gate_status": "FAIL", "reasons": ["NO_COMMON_POSTERIOR"], "ranking": []}
    metrics = [[strength, losses[f"pool_{strength}"]["log_loss"], losses[f"pool_{strength}"]["brier"]] for strength in LAMBDAS]
    winner = rank_lambdas(metrics)
    name = f"pool_{winner}"
    deltas = [item["loss"][name]["brier"] - item["loss"]["A_tp_pool"]["brier"]
              for item in summary["by_symbol"].values() if item["common_count"]]
    reference = {**losses["A_tp_pool"], "ready": overall["coverage"]["A_tp_pool"]["ready_count"]}
    candidate = {**losses[name], "ready": overall["coverage"][name]["ready_count"],
        "max_symbol_brier_increase": float(max(deltas)) if len(deltas) == len(SYMBOLS) else None,
        "all_strata_have_common": all_strata}
    gate = pooling_gate(reference, candidate)
    return {"selection_version": SELECTION_VERSION, "choice": "hierarchical_pool" if gate["accepted"] else "A_tp_pool",
        "lambda": winner if gate["accepted"] else None, "ranked_lambda": winner,
        "gate_status": "PASS" if gate["accepted"] else "FAIL", "reasons": gate["reason_codes"],
        "ranking": sorted(metrics, key=lambda row: (row[1], row[2], row[0])), "gate_inputs": {"A": reference, "pool": candidate}}
