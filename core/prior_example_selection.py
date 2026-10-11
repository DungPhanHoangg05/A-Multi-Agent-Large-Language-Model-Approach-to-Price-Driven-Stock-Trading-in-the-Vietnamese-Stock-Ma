"""Chọn ví dụ theo tuổi, similarity và khoảng cách phiên; không dùng outcome."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import date
import math
from typing import Any

import pandas as pd

from core.bayesian_memory import copy_historical_records
from core.bayesian_retriever import BayesianPriorRetriever
from core.historical_signals import digest
from core.price_feature_index import PriceFeatureIndex, TRAIN_END, _day, _hash

RANKING_VERSION = "signal_price_recency_v1"
DIVERSITY_VERSION = "session_gap_v1"
DEFAULT_CONFIG = {"w_signal": .5, "half_life_days": 365, "max_prior_age_days": 730,
                  "min_gap_sessions": 5, "min_similarity": .625, "requested_k": 3, "seed": 42}


def selection_config(value: dict[str, Any] | None) -> dict[str, Any]:
    """Kiểm tham số phương pháp; CLI sẽ khóa cấu hình ứng viên khi tích hợp."""
    if value is not None and (type(value) is not dict or set(value) - set(DEFAULT_CONFIG)):
        raise ValueError("Cấu hình chọn ví dụ chứa trường ngoài whitelist")
    result = {**DEFAULT_CONFIG, **(value or {})}
    for key in ("w_signal", "min_similarity"):
        number = result[key]
        if type(number) not in (int, float) or not 0 <= number <= 1 or not math.isfinite(number):
            raise ValueError("Trọng số/ngưỡng similarity phải hữu hạn trong [0,1]")
        result[key] = float(number)
    for key, minimum in (("half_life_days", 1), ("max_prior_age_days", 0),
                         ("min_gap_sessions", 1), ("requested_k", 1)):
        if type(result[key]) is not int or result[key] < minimum:
            raise ValueError("Tuổi, half-life, khoảng cách phiên và K phải là số nguyên hợp lệ")
    try:
        if not math.isfinite(float(result["half_life_days"])):
            raise ValueError("Half-life không hữu hạn")
    except OverflowError as exc:
        raise ValueError("Half-life vượt miền số hữu hạn") from exc
    if result["requested_k"] > 3 or type(result["seed"]) is not int or result["seed"] != 42:
        raise ValueError("Policy chỉ nhận K≤3 và seed=42; không bù ví dụ ngẫu nhiên")
    return result


class PriceExampleSelector:
    """Cache lịch VNINDEX gắn đúng index đã kiểm; không I/O/refit ở hot query.

    Biên adapter xác minh file nguồn lịch. Biên thuần này còn kiểm prefix
    train khớp index; phần lịch OOS phải được adapter xác minh trước khi cấp.
    """

    def __init__(self, index: PriceFeatureIndex, calendar: pd.DatetimeIndex) -> None:
        if (not isinstance(index, PriceFeatureIndex) or not isinstance(calendar, pd.DatetimeIndex)
                or calendar.empty or calendar.hasnans or calendar.tz is not None
                or not calendar.is_unique or not calendar.is_monotonic_increasing
                or not calendar.equals(calendar.normalize())):
            raise ValueError("Selector cần index đã kiểm và lịch VNINDEX duy nhất, tăng, ngày gốc")
        days = calendar.strftime("%Y-%m-%d").tolist()
        payload = index.payload
        if _hash([day for day in days if day <= TRAIN_END]) != payload["train_material"]["calendar_sha256"]:
            raise ValueError("Lịch diversity khác prefix train đã khóa trong index")
        self._index = index
        self._days = tuple(days)
        self._positions = {day: position for position, day in enumerate(days)}
        self._source = deepcopy(payload["provenance"]["calendar"])
        self._prefix_hashes: dict[str, str] = {}

    @property
    def index(self) -> PriceFeatureIndex:
        """Index bất biến đã gắn với lịch, dùng lại API base ranking production."""
        return self._index

    def session_position(self, day: str) -> int:
        """Chỉ nhận ngày có phiên thật; không dùng ngày lịch thay phiên giao dịch."""
        day = _day(day)
        if day not in self._positions:
            raise ValueError("Ngày query/prior không nằm trong lịch VNINDEX đã kiểm")
        return self._positions[day]

    def calendar_metadata(self, cutoff: str) -> dict[str, Any]:
        """Băm đúng prefix ≤query; nối phiên tương lai không làm đổi proof quá khứ."""
        position = self.session_position(cutoff)
        if cutoff not in self._prefix_hashes:
            self._prefix_hashes[cutoff] = _hash(list(self._days[:position + 1]))
        return {"calendar_source": deepcopy(self._source), "calendar_cutoff": cutoff,
                "calendar_prefix_sha256": self._prefix_hashes[cutoff], "calendar_session_count": position + 1}


def _select_trace(trace: list[dict[str, Any]], selector: PriceExampleSelector,
                  cutoff: str, config: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Policy thuần trên trace không chứa nhãn; giữ mọi lý do loại, không bù K."""
    selector.session_position(cutoff)
    query_date = date.fromisoformat(cutoff)
    rows = deepcopy(trace)
    qualified = []
    for row in rows:
        age = (query_date - date.fromisoformat(_day(row["as_of_date"]))).days
        exit_age = (query_date - date.fromisoformat(_day(row["exit_date"]))).days
        if age <= 0 or exit_age <= 0 or row["as_of_date"] >= row["exit_date"]:
            raise ValueError("Prior chưa đóng nghiêm ngặt trước query")
        position = selector.session_position(row["as_of_date"])
        selector.session_position(row["exit_date"])
        recency = float(2 ** (-age / config["half_life_days"]))
        row.update(age_days=age, exit_age_days=exit_age, session_index=position,
                   recency=recency, rank_score=None, rank_position=None, selected_order=None,
                   selection_status="EXCLUDED", selection_reasons=[], conflicting_selected_ids=[])
        if row["status"] != "SCORED":
            row["selection_reasons"] = list(row["reason_codes"])
            continue
        row["rank_score"] = float(row["base_score"] * recency)
        if age > config["max_prior_age_days"]:
            row["selection_reasons"].append("PRIOR_TOO_OLD")
        if row["base_score"] < config["min_similarity"]:
            row["selection_reasons"].append("BELOW_MIN_SIMILARITY")
        if not row["selection_reasons"]:
            qualified.append(row)
    qualified.sort(key=lambda row: row["episode_id"])
    qualified.sort(key=lambda row: row["exit_date"], reverse=True)
    qualified.sort(key=lambda row: row["rank_score"], reverse=True)
    selected: list[dict[str, Any]] = []
    for position, row in enumerate(qualified, 1):
        row["rank_position"] = position
        if len(selected) == config["requested_k"]:
            row["selection_reasons"] = ["K_LIMIT"]
            continue
        conflicts = [prior["episode_id"] for prior in selected
                     if abs(row["session_index"] - prior["session_index"]) < config["min_gap_sessions"]]
        if conflicts:
            row["selection_reasons"] = ["SESSION_GAP_TOO_SMALL"]
            row["conflicting_selected_ids"] = conflicts
            continue
        row["selection_status"] = "SELECTED"
        row["selected_order"] = len(selected) + 1
        selected.append(row)
    return rows, [row["episode_id"] for row in qualified], [row["episode_id"] for row in selected]


def select_price_examples(retriever: BayesianPriorRetriever, *, selector: PriceExampleSelector, symbol: str,
                          as_of_date: str, current_regime: str, current_signals: dict[str, str],
                          query_features: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Áp policy lên base ranking; population P và nhãn sau chọn giữ nguyên."""
    if not isinstance(selector, PriceExampleSelector):
        raise ValueError("Cần selector gắn lịch/index đã xác minh")
    settings = selection_config(config)
    calendar = selector.calendar_metadata(as_of_date)
    base = retriever.rank_price_candidates(index=selector.index, symbol=symbol, as_of_date=as_of_date,
        current_regime=current_regime, current_signals=current_signals, query_features=query_features,
        w_signal=settings["w_signal"])
    trace, ranked_ids, selected_ids = _select_trace(base["trace"], selector, as_of_date, settings)
    population = base["regime_population"]
    by_id = {row["episode_id"]: row for row in population}
    reasons = []
    if not population:
        reasons.append("EMPTY_POPULATION")
    elif not ranked_ids:
        reasons.append("NO_QUALIFIED_EXAMPLES")
    if len(selected_ids) < settings["requested_k"]:
        reasons.append("INSUFFICIENT_EXAMPLES")
    metadata = {**base["metadata"], **calendar, "base_ranking_version": base["metadata"]["ranking_version"],
        "ranking_version": RANKING_VERSION, "diversity_version": DIVERSITY_VERSION,
        "policy_stage": "EXAMPLE_SELECTION", "policy_complete": True,
        "config": settings, "config_sha256": digest(settings), "requested_k": settings["requested_k"],
        "k_eff": len(selected_ids), "base_ranked_ids": base["metadata"]["ranked_ids"],
        "ranked_ids": ranked_ids, "qualified_count": len(ranked_ids), "selected_ids": selected_ids,
        "excluded_ids": [row["episode_id"] for row in trace if row["selection_status"] == "EXCLUDED"],
        "exclusion_counts": dict(sorted(Counter(reason for row in trace for reason in row["selection_reasons"]).items())),
        "reason_codes": reasons}
    return {"tasks": copy_historical_records([by_id[key] for key in selected_ids]),
            "regime_population": population, "trace": trace, "metadata": metadata}
