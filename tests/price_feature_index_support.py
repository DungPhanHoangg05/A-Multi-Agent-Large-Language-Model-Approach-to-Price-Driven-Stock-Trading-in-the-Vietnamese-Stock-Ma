"""Nguồn số xác định cho scaler/index; không có outcome, LLM hay file thật."""

from typing import Any

import numpy as np
import pandas as pd

from core.price_feature_index import SYMBOLS

SOURCE = {"source_library": "vnstock", "primary_source": "VCI",
          "price_basis": "UNADJUSTED_EXECUTION", "price_unit": "thousand_VND"}


def index_inputs() -> dict[str, Any]:
    """Tạo bốn mã, quyền, biên purge và một mã không đủ hai hàng fit."""
    calendar = pd.bdate_range("2019-01-02", "2022-12-30")
    prices = {}
    for offset, symbol in enumerate(SYMBOLS):
        positions = np.arange(len(calendar), dtype=float)
        close = (np.full(len(calendar), 100.) if symbol == "VCB" else
                 100 + offset * 10 + .02 * positions + 3 * np.sin(positions / (13 + offset)))
        prices[symbol] = (pd.DataFrame({"Datetime": calendar, "Open": close, "High": close + 1,
            "Low": close - 1, "Close": close, "Volume": 100,
            "Reference": np.r_[close[0], close[:-1]]}),
            [{"exrightDate": "2020-06-10T00:00:00"}] if symbol == "FPT" else [])
    records = []
    for symbol in SYMBOLS:
        days = ["2020-06-01", "2020-06-04"]
        if symbol == "FPT":
            days += ["2020-06-09", "2020-06-12", "2020-12-30", "2021-01-04",
                     "2021-12-28", "2022-01-03", "2022-01-06", "2022-12-27"]
        if symbol == "VNM":
            days = days[:1]
        for cutoff in days:
            exit_date = calendar[calendar.get_loc(cutoff) + 3].strftime("%Y-%m-%d")
            records.append({"episode_id": f"{symbol}:{cutoff}", "symbol": symbol,
                            "as_of_date": cutoff, "exit_date": exit_date})
    provenance = {"bank": {"bank_sha256": "a" * 64},
                  "prices": {symbol: {"csv_sha256": "b" * 64} for symbol in SYMBOLS},
                  "calendar": {"source_csv_sha256": "c" * 64}}
    return {"records": records, "prices": prices, "calendar": calendar,
            "source": dict(SOURCE), "provenance": provenance}
