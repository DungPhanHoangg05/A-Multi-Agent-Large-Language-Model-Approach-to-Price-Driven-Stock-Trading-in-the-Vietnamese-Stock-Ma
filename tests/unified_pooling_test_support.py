"""Nguồn tổng hợp và oracle cố định cho posterior/loss/pooling U-BICL."""

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

import pandas as pd

from core.price_feature_index import SYMBOLS
from core.unified_bayes_memory import build_memory
from core.unified_bayes_statistics import MODELS
from unified_memory_test_support import SIGNALS, memory_inputs


def fixture() -> dict[str, Any]:
    """Đọc đúng fixture tổng hợp đã khóa ở U10-02, không đọc payoff OOS."""
    return json.loads((Path(__file__).resolve().parents[1] /
                      "docs/plan/week10/fixtures/unified_bic_contract_v1.json").read_text("utf-8"))


def statistics_inputs() -> dict[str, Any]:
    """Ba tầng regime/T-P, có một observation thiếu feature nhưng vẫn hợp lệ."""
    inputs = memory_inputs()
    rows = [row for row in inputs["original"] if row["symbol"] == "FPT"]
    rows[0]["regime"], rows[1]["regime"] = "BEAR", "CHOPPY"
    rows[2]["agent_signals"]["pattern"] = "NEUTRAL"
    return inputs


def score_points(*, doubled: bool = False) -> list[dict[str, Any]]:
    """Tám ô fold×mã, mỗi query có một trọng số độc lập và cùng bốn dự báo."""
    rows = []
    for fold, start in (("train_2021", "2021-01-04"), ("train_2022", "2022-01-06")):
        for symbol in SYMBOLS:
            for offset in ((0, 7) if doubled else (0,)):
                cutoff = pd.Timestamp(start) + pd.offsets.BDay(offset)
                exit_date = cutoff + pd.offsets.BDay(3)
                day = cutoff.strftime("%Y-%m-%d")
                rows.append({"episode_id": f"{symbol}:{day}", "symbol": symbol, "as_of_date": day,
                    "exit_date": exit_date.strftime("%Y-%m-%d"), "fold_id": fold, "label": 1, "net_long_return": .02,
                    "probability": dict(zip(MODELS, (.6, .7, .65, .61))), "ready": {name: True for name in MODELS}})
    return deepcopy(rows)
