"""Fixture số học riêng cho validation train; không tạo kết quả Decision."""

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from sklearn.preprocessing import StandardScaler

from core.regime_detector import FEATURE_COLUMNS, HMM_PARAMETERS, build_regime_features
from price_feature_index_support import index_inputs


def regime_fixture(root: Path) -> tuple:
    """Artifact scaler/calibration tính thật từ prefix; không cần fit HMM cho test helper."""
    frame = index_inputs()["prices"]["FPT"][0]
    cutoff = "2021-01-04"
    raw = build_regime_features(frame.loc[frame.Datetime <= cutoff], cutoff)[list(FEATURE_COLUMNS)].to_numpy()
    scaler = StandardScaler().fit(raw)
    metadata = {"train_end_date": cutoff, "parameters": dict(HMM_PARAMETERS),
        "training_data_sha256": "a"*64, "classification_method": "HMM",
        "volatility_quantiles": np.quantile(raw[:, 1], [1/3, 2/3]).tolist(),
        "trend_threshold": float(np.median(np.abs(raw[:, 4]))), "ma200_train_std": float(raw[:, 4].std(ddof=1))}
    artifact = {"payload": {"scaler": {"mean": scaler.mean_.tolist(), "var": scaler.var_.tolist(),
                                      "scale": scaler.scale_.tolist()}}}
    (root/"model.json").write_text(json.dumps(artifact), encoding="utf-8")
    proof = {"context": {"as_of_date": cutoff}, "regime": {"metadata": metadata,
        "component_train_end_dates": dict.fromkeys(("hmm", "scaler", "calibration"), cutoff),
        "frozen_model": None, "artifact_path": "model.json", "artifact_sha256": "b"*64}}
    return SimpleNamespace(_vnindex=frame, _files=SimpleNamespace(path=lambda name:root/name)), SimpleNamespace(source_provenance=proof)
