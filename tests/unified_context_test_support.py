"""Memory/feature tổng hợp nhiều task để kiểm context U-BICL độc lập outcome thật."""

from copy import deepcopy
from typing import Any
from unittest.mock import patch

import pandas as pd

from core.historical_outcomes import HistoricalOutcomeGenerator
from core.historical_signals import digest
from core.pit_price_features import extract_pit_price_features
from core.unified_bayes_context import UnifiedBayesContext
from core.unified_bayes_memory import build_memory
from unified_memory_test_support import SIGNALS, memory_inputs


def reseal(evidence: dict[str, Any]) -> dict[str, Any]:
    """Reseal fixture renderer; verifier nguồn production phải vẫn từ chối sửa semantic."""
    evidence.pop("base_evidence_sha256", None)
    evidence["base_evidence_sha256"] = digest(evidence)
    return evidence


def dense_inputs() -> dict[str, Any]:
    """Tạo đủ support nhiều block/regime, mọi nhãn qua engine thật trên giá tổng hợp."""
    inputs = memory_inputs()
    calendar = inputs["calendar"]
    generator = HistoricalOutcomeGenerator(inputs["prices"].__getitem__)
    existing = [row for row in inputs["original"] if row["symbol"] == "FPT"]
    for pos in range(calendar.get_loc("2021-01-15"), calendar.get_loc("2022-12-15"), 6):
        day = calendar[pos].strftime("%Y-%m-%d")
        if any(abs(pos - calendar.get_loc(row["as_of_date"])) < 4 for row in existing):
            continue
        entry, exit_date = (calendar[pos + n].strftime("%Y-%m-%d") for n in (1, 3))
        regime = "BEAR" if (pos // 6) % 3 == 0 else "BULL"
        inputs["original"].append({"episode_id": f"FPT:{day}", "symbol": "FPT", "as_of_date": day,
            "entry_date": entry, "exit_date": exit_date, "regime": regime, "agent_signals": dict(SIGNALS),
            "outcome": generator.generate("FPT", day, entry, exit_date, SIGNALS, settled_as_of="2022-12-30")})
    return inputs


def make_context(inputs: dict[str, Any]) -> UnifiedBayesContext:
    """Chỉ mock cold artifact loader; thuật toán memory/index/stats/context đều chạy thật."""
    memory = build_memory(**inputs)
    with patch("core.unified_bayes_context.load_backbone_choice", return_value={"lambda": 8}):
        return UnifiedBayesContext(memory, inputs["calendar"])


def features(inputs: dict[str, Any], cutoff: str = "2023-01-06") -> dict[str, Any]:
    """Query feature qua extractor PIT thật, không đưa nhãn query vào input."""
    frame, events = inputs["prices"]["FPT"]
    return extract_pit_price_features(frame, events, inputs["calendar"], cutoff, source=inputs["source"])


def query(cutoff: str = "2023-01-06") -> dict[str, Any]:
    """Query typed dùng chung, khác target trong memory để dò self-match."""
    return {"symbol": "FPT", "as_of_date": cutoff, "current_regime": "BULL", "current_signals": dict(SIGNALS)}


def fixture_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Chỉ chiếu metadata/score; bỏ nhãn fixture trước khi gọi pure selector."""
    return [{key: deepcopy(row[key]) for key in ("episode_id", "cutoff_session", "entry_session", "exit_session", "age_days", "feature_available")} |
        {"base_score": row["base_score"] if row["feature_available"] else None,
         "feature_reasons": [] if row["feature_available"] else ["PRIOR_FEATURE_UNAVAILABLE"]} for row in records]
