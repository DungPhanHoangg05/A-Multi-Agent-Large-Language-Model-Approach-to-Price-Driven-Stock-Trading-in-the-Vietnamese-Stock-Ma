"""Regime prefix riêng cho dataset v4; không nạp model cuối2022 cho fold sớm."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pandas as pd

from core.mt_bicl_v4_protocol import canonical, checksum
from core.regime_detector import MarketRegimeDetector, training_data_hash


class DataRegimes:
    """Fit một lần mỗi prefix; cold replay chỉ load tham số đã khóa và kiểm training hash."""

    def __init__(self, history: pd.DataFrame, directory: Path, *, frozen: dict[str, Any] | None = None) -> None:
        self.history = history.copy()
        self.directory = directory
        self.frozen = frozen
        self.models: dict[str, MarketRegimeDetector] = {}
        self.records: dict[str, Any] = {}
        self.cache: dict[tuple[str, str], dict[str, Any]] = {}

    def model(self, cutoff: str) -> MarketRegimeDetector | None:
        """Thiếu499 phiên mới UNKNOWN; fit/schema/runtime lỗi phải raise."""
        if cutoff > "2020-12-31":
            raise ValueError("Regime fit vượt cuối train2020")
        prefix = self.history.loc[self.history["Datetime"] <= cutoff].copy()
        if len(prefix) < 499:
            return None
        if cutoff not in self.models:
            training_hash = training_data_hash(prefix)
            path = self.directory / (cutoff + ".json")
            if self.frozen is not None:
                record = self.frozen[cutoff]
                if record["training_data_sha256"] != training_hash or checksum(path.read_bytes()) != record["file_sha256"]:
                    raise ValueError("Regime artifact khác prefix/hash đã khóa")
                model = MarketRegimeDetector.load(path, expected_training_hash=training_hash)
            elif path.exists():
                model = MarketRegimeDetector.load(path, expected_training_hash=training_hash)
            else:
                print(f"Fit regime dữ liệu prefix≤{cutoff}; không dùng nhãn hoặc API.", flush=True)
                model = MarketRegimeDetector().fit(prefix)
                model.save(path)
            if model.metadata["train_end_date"] > cutoff:
                raise ValueError("Metadata regime dùng tương lai")
            self.models[cutoff] = model
            self.records[cutoff] = {"file_sha256": checksum(path.read_bytes()),
                "training_data_sha256": training_hash, "fit_end": cutoff,
                "training_rows": len(prefix), "metadata": model.metadata}
        return self.models[cutoff]

    def classify(self, as_of: str, fit_cutoff: str) -> dict[str, Any]:
        """Model/scaler chỉ từ prefix, feature classify kết thúc đúng as_of."""
        if fit_cutoff > as_of:
            raise ValueError("Regime model fit sau query")
        key = (as_of, fit_cutoff)
        if key not in self.cache:
            model = self.model(fit_cutoff)
            if model is None:
                state = {"name": "UNKNOWN", "fit_end": fit_cutoff, "model_sha256": None,
                         "feature_end_date": None, "reason": "INSUFFICIENT_REGIME_HISTORY"}
            else:
                prefix = self.history.loc[self.history["Datetime"] <= as_of].copy()
                result = model.classify_regime(prefix, as_of)
                if result["feature_end_date"] > as_of:
                    raise ValueError("Feature regime sau query")
                state = {"name": result["regime_name"], "fit_end": fit_cutoff,
                         "model_sha256": self.records[fit_cutoff]["file_sha256"],
                         "feature_end_date": result["feature_end_date"], "reason": None}
            canonical(state)
            self.cache[key] = state
        return deepcopy(self.cache[key])

    def view(self, rows: list[dict[str, Any]], fit_end: str) -> dict[str, Any]:
        """Regime observation được fit không sau đầu block, kể cả historical D/C."""
        result = {}
        for row in rows:
            cutoff = min(row["block_start_date"], fit_end)
            query = self.classify(row["as_of_date"], cutoff)
            task = self.classify(row["block_start_date"], cutoff)
            result[row["episode_id"]] = {"query_name": query["name"], "task_name": task["name"],
                                          "query_proof": query, "task_proof": task}
        return result
