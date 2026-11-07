"""Fixture giá và detector giả chỉ dành kiểm hợp đồng task/context offline."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pandas as pd

from core.mt_bicl_bank import SYMBOLS, build_dense_bank
from core.mt_bicl_regimes import RegimeTimeline
from core.mt_bicl_stream import MarketStream
from core.mt_bicl_tasks import TaskBuilder
from core.regime_detector import training_data_hash
from mt_bicl_bank_support import prices


class FakeDetector:
    """Ghi cutoff thật nhưng không fit HMM trong unit test selection."""

    def fit(self, frame: pd.DataFrame) -> FakeDetector:
        """Metadata chỉ từ prefix được truyền; không có archive tương lai."""
        self.metadata = {"train_end_date": str(frame["Datetime"].iloc[-1].date()),
                         "training_rows": len(frame), "training_data_sha256": training_data_hash(frame),
                         "classification_method": "MULTI_FACTOR"}
        return self

    def classify_regime(self, frame: pd.DataFrame, date: str) -> dict[str, Any]:
        """Trả BULL cố định để tách test membership khỏi nhiễu HMM thật."""
        if str(frame["Datetime"].iloc[-1].date()) != date or self.metadata["train_end_date"] > date:
            raise ValueError("Detector fixture thấy future hoặc thiếu query")
        return {"as_of_date": date, "feature_end_date": date, "regime_name": "BULL"}


def setup(periods: int = 1050, *, late_fpt: bool = False) -> tuple[dict, dict, pd.DataFrame]:
    """Tạo đủ lịch để có nhiều block, giữ bốn mã có x giống nhau cho test tie."""
    frame, calendar = prices(periods=periods)
    sources = {symbol: (frame.copy(), []) for symbol in SYMBOLS}
    if late_fpt:
        sources["FPT"] = (frame.iloc[35:].copy(), [])
    end = min(str(calendar[-1].date()), "2022-12-31")
    bank = build_dense_bank(sources, calendar, end_date=end)
    return bank, sources, frame.loc[:, ["Datetime", "Close"]]


def builder(bank: dict, sources: dict, history: pd.DataFrame) -> TaskBuilder:
    """Mỗi replay có cache và stream riêng; không chia sẻ state giữa test."""
    timeline = RegimeTimeline(history, detector_factory=FakeDetector)
    return TaskBuilder(deepcopy(bank), MarketStream(bank, sources, pd.DatetimeIndex(history["Datetime"])), timeline)
