"""Dữ liệu tổng hợp cho bank/scaler MT-BICL; không dùng nhãn thị trường thật."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from core.mt_bicl_bank import BANK_VERSION, PROTOCOL_SHA256, SOURCE, SYMBOLS, build_dense_bank
from core.pit_price_features import FEATURE_COLUMNS, FEATURE_VERSION, PRICE_POLICY_VERSION


def prices(periods: int = 100, *, flat: bool = False) -> tuple[pd.DataFrame, pd.DatetimeIndex]:
    """Nến hợp lệ tăng nhẹ, Reference bằng Close phiên trước, không có quyền giả."""
    calendar = pd.bdate_range("2018-01-02", periods=periods)
    close = np.full(periods, 100.) if flat else 100+np.arange(periods)*0.13+np.sin(np.arange(periods))
    frame = pd.DataFrame({"Datetime": calendar, "Open": close, "High": close+1, "Low": close-1,
                          "Close": close, "Volume": 1000, "Reference": np.r_[close[0], close[:-1]]})
    return frame, calendar


def bank(frame: pd.DataFrame, calendar: pd.DatetimeIndex, events: list[dict] | None = None) -> dict[str, Any]:
    """Dựng bốn mã có cùng nến để kiểm hợp đồng dữ liệu mà không gọi LLM."""
    return build_dense_bank({symbol: (frame, events or []) for symbol in SYMBOLS}, calendar,
                            end_date=str(calendar[-1].date()))


def feature(date: str, vector: list[float]) -> dict[str, Any]:
    """Feature đã xác minh giả lập để kiểm riêng phép fit, không giả lập giá thực thi."""
    return {"feature_version": FEATURE_VERSION, "price_policy_version": PRICE_POLICY_VERSION,
            "status": "AVAILABLE", "reasons": [], "as_of_date": date, "feature_end_date": date,
            "source": dict(SOURCE), "feature_columns": list(FEATURE_COLUMNS), "vector": vector}


def scaler_bank() -> dict[str, Any]:
    """Hai cycle trước cutoff, một cycle đóng sau, một cycle validation ngoài train."""
    records = []
    for symbol, query, entry, exit_date, vector, split in (
        ("FPT", "2020-12-21", "2020-12-22", "2020-12-24", [1., 2., 3., 4.], "train"),
        ("MWG", "2020-12-22", "2020-12-23", "2020-12-25", [3., 4., 5., 6.], "train"),
        ("VCB", "2020-12-24", "2020-12-25", "2020-12-29", [100., 100., 100., 100.], "train"),
        ("VNM", "2021-01-04", "2021-01-05", "2021-01-07", [-100.]*4, "checkpoint_selection"),
    ):
        records.append({"episode_id": f"{symbol}-{query}", "symbol": symbol, "as_of_date": query,
                        "entry_date": entry, "exit_date": exit_date, "status": "AVAILABLE", "split": split,
                        "features": feature(query, vector), "outcome": {"y": 1, "r_net": 0.01}})
    return {"bank_version": BANK_VERSION, "protocol_sha256": PROTOCOL_SHA256,
            "source": dict(SOURCE), "feature_columns": list(FEATURE_COLUMNS), "records": records}
