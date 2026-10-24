"""Nguồn tổng hợp cho memory U-BICL, không dùng giá/Decision thực nghiệm."""

from copy import deepcopy
from typing import Any

import numpy as np
import pandas as pd

from core.historical_outcomes import HistoricalOutcomeGenerator
from core.price_feature_index import SYMBOLS
from price_feature_index_support import SOURCE

SIGNALS = {"trend": "BULLISH", "pattern": "BEARISH", "alpha_consensus": "NEUTRAL",
           "indicator_consensus": "BULLISH", "sentiment": "NEUTRAL"}
COMPATIBILITY = {"signal_config": {"models": {"agent_llm_model": "fixture-text", "graph_llm_model": "fixture-vision"},
    "window_size": 45, "norm_method": "zscore_tanh", "alpha_weights": None, "language": "vi", "time_frame": "1d"},
    "client_options": {"agent": {"reasoning_effort": "low"}, "graph": {"reasoning_effort": "none"}}}


def upstream(symbol: str, cutoff: str) -> dict[str, Any]:
    """Chiếu tín hiệu và provenance đã kiểm; không có label hay Decision."""
    return {"episode_id": f"{symbol}:{cutoff}", "symbol": symbol, "as_of_date": cutoff,
        "regime": "BULL", "agent_signals": dict(SIGNALS), "source": {
            "cohort": "development_2023" if cutoff[:4] == "2023" else "holdout_2024",
            "point_id": f"{symbol}-{cutoff}", "run_signature": "a" * 64, "shared_sha256": "b" * 64,
            **deepcopy(COMPATIBILITY)}}


def memory_inputs() -> dict[str, Any]:
    """Tạo biên fold, feature thiếu do quyền và cycle 2023/2024 có thể kiểm PIT."""
    calendar = pd.bdate_range("2018-01-02", "2025-12-31")
    prices = {}
    for offset, symbol in enumerate(SYMBOLS):
        t = np.arange(len(calendar), dtype=float)
        close = 100 + offset * 5 + .01 * t + np.sin(t / (11 + offset))
        prices[symbol] = (pd.DataFrame({"Datetime": calendar, "Open": close + .1,
            "High": close + 1, "Low": close - 1, "Close": close, "Reference": np.r_[close[0], close[:-1]],
            "Volume": 1000}), [{"exrightDate": "2020-06-10"}] if symbol == "FPT" else [])
    original = []
    generator = HistoricalOutcomeGenerator(prices.__getitem__)
    for symbol in SYMBOLS:
        for cutoff in ("2020-06-01", "2020-06-04", "2020-06-12", "2020-12-30", "2021-12-30", "2022-12-27"):
            pos = calendar.get_loc(cutoff)
            entry, exit_date = (calendar[pos + n].strftime("%Y-%m-%d") for n in (1, 3))
            original.append({"episode_id": f"{symbol}:{cutoff}", "symbol": symbol, "as_of_date": cutoff,
                "entry_date": entry, "exit_date": exit_date, "regime": "BULL", "agent_signals": dict(SIGNALS),
                "outcome": generator.generate(symbol, cutoff, entry, exit_date, SIGNALS, settled_as_of="2022-12-30")})
    imported = [upstream(symbol, cutoff) for symbol in SYMBOLS for cutoff in ("2023-01-03", "2024-12-26")]
    return {"original": original, "imported": imported, "prices": prices, "calendar": calendar,
        "source": dict(SOURCE), "provenance": {"bank": {"bank_sha256": "a" * 64},
            "prices": {symbol: {"csv_sha256": "b" * 64} for symbol in SYMBOLS},
            "calendar": {"source_csv_sha256": "c" * 64}}, "compatibility": deepcopy(COMPATIBILITY),
        "source_files": {"fixture.json": "a" * 64}, "protocol_sha256": "d" * 64}
