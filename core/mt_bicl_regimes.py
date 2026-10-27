"""Regime đầu block và query MT-BICL bằng historical prefix, đóng băng cuối 2020."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

import numpy as np
import pandas as pd

from core.mt_bicl_bank import TRAIN_END, content_hash, day
from core.regime_detector import MarketRegimeDetector


class RegimeTimeline:
    """Cache model prefix riêng của MT-BICL; không nạp artifact cuối 2022."""

    def __init__(self, history: pd.DataFrame, *,
                 detector_factory: Callable[[], Any] = MarketRegimeDetector) -> None:
        """Caller kiểm checksum nguồn; factory tiêm chỉ phục vụ test offline."""
        self._history = history.loc[:, ["Datetime", "Close"]].copy()
        self._history["Datetime"] = pd.to_datetime(self._history["Datetime"], errors="raise")
        self.calendar = pd.DatetimeIndex(self._history["Datetime"])
        if (not len(self.calendar) or self.calendar.hasnans or self.calendar.tz is not None or self.calendar.has_duplicates
                or not self.calendar.is_monotonic_increasing or not self.calendar.equals(self.calendar.normalize())
                or self.calendar[0] != pd.Timestamp("2018-01-02")):
            raise ValueError("Lịch regime phải đúng neo và tăng dần duy nhất")
        self._factory = detector_factory
        self._models: dict[str, Any] = {}
        self._proofs: dict[str, dict[str, Any]] = {}
        self._blocks: dict[int, dict[str, Any]] = {}
        self._queries: dict[str, dict[str, Any]] = {}

    def _prefix(self, cutoff: str) -> pd.DataFrame:
        """Cắt trước kiểm Close, không để giá tương lai tham gia fit/calibration."""
        frame = self._history.loc[self._history["Datetime"] <= pd.Timestamp(day(cutoff))].copy()
        close = frame["Close"].to_numpy(dtype=float)
        if frame.empty or not np.isfinite(close).all() or (close <= 0).any():
            raise ValueError("Prefix VNINDEX không hợp lệ")
        return frame

    def _model(self, cutoff: str) -> tuple[Any | None, dict[str, Any]]:
        """Chỉ trả UNKNOWN khi thiếu 499 phiên; mọi lỗi fit khác được ném ra."""
        if cutoff > TRAIN_END:
            raise ValueError("Không được fit model regime sau 2020")
        prefix = self._prefix(cutoff)
        if len(prefix) < 499:
            return None, {"name": "UNKNOWN", "reason": "INSUFFICIENT_REGIME_HISTORY",
                          "model_fit_cutoff": cutoff, "prefix_rows": len(prefix),
                          "model_training_end_date": None, "model_sha256": None, "method": "UNKNOWN"}
        if cutoff not in self._models:
            detector = self._factory().fit(prefix)
            meta = detector.metadata
            if meta["train_end_date"] > cutoff or meta["train_end_date"] > TRAIN_END:
                raise ValueError("Model/scaler/calibration regime học sau cutoff")
            self._models[cutoff] = detector
            self._proofs[cutoff] = {"model_fit_cutoff": cutoff, "prefix_rows": len(prefix),
                "model_training_end_date": meta["train_end_date"], "training_data_sha256": meta["training_data_sha256"],
                "model_sha256": content_hash(self._serialize(detector)), "method": meta["classification_method"]}
        return self._models[cutoff], deepcopy(self._proofs[cutoff])

    @staticmethod
    def _serialize(detector: Any) -> dict[str, Any]:
        """Đọc tham số đã fit để seal trong artifact mới, không ghi model W9."""
        if not isinstance(detector, MarketRegimeDetector):
            return {"test_metadata": detector.metadata}
        model, scaler = detector._model, detector._scaler
        return {"metadata": detector.metadata,
                "model": {"startprob": model.startprob_.tolist(), "transmat": model.transmat_.tolist(),
                          "means": model.means_.tolist(), "covars": np.diagonal(model.covars_, axis1=1, axis2=2).tolist()},
                "scaler": {"mean": scaler.mean_.tolist(), "variance": scaler.var_.tolist(), "scale": scaler.scale_.tolist()}}

    def _classify(self, date: str, fit_cutoff: str) -> dict[str, Any]:
        """Model và feature query cùng PIT; giữ nguyên fallback đã khóa của primitive."""
        detector, proof = self._model(fit_cutoff)
        if detector is None:
            return {**proof, "as_of_date": date, "feature_end_date": None}
        prefix = self._prefix(date)
        if str(prefix["Datetime"].iloc[-1].date()) != date:
            raise ValueError("Thiếu phiên VNINDEX tại query regime")
        state = detector.classify_regime(prefix, date)
        if state["feature_end_date"] > date:
            raise ValueError("Feature regime vượt query")
        if content_hash(self._serialize(detector)) != proof["model_sha256"]:
            raise ValueError("Model/scaler/calibration regime bị đổi khi inference")
        return {**proof, "name": state["regime_name"], "reason": None, "as_of_date": date,
                "feature_end_date": state["feature_end_date"], "state": state}

    def task(self, block: int) -> dict[str, Any]:
        """Metadata đầu task không bị gán lại bằng model fit sau đầu block."""
        if type(block) is not int or block < 0 or 63*block >= len(self.calendar):
            raise ValueError("Block regime không hợp lệ")
        if block not in self._blocks:
            start = str(self.calendar[63*block].date())
            cutoff = start if start <= TRAIN_END else TRAIN_END
            self._blocks[block] = self._classify(start, cutoff)
        return deepcopy(self._blocks[block])

    def query(self, date: str) -> dict[str, Any]:
        """Train dùng model đầu block; query từ 2021 chỉ dùng model cuối 2020."""
        date = day(date)
        index = self.calendar.get_indexer([pd.Timestamp(date)])[0]
        if index < 0:
            raise ValueError("Query không thuộc lịch regime")
        if date not in self._queries:
            cutoff = str(self.calendar[(index//63)*63].date()) if date <= TRAIN_END else TRAIN_END
            self._queries[date] = self._classify(date, cutoff)
        return deepcopy(self._queries[date])

    def artifacts(self) -> dict[str, Any]:
        """Xuất mọi model đã sử dụng cùng metadata prefix, không pickle hoặc self-reseal."""
        return {key: {"proof": deepcopy(self._proofs[key]), "parameters": self._serialize(value)}
                for key, value in sorted(self._models.items())}
