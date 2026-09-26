"""Nhận diện chế độ VN-Index từ đặc trưng chỉ sử dụng lịch sử đã biết."""

from __future__ import annotations

from copy import deepcopy
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import tempfile
from typing import Any

import numpy as np
import pandas as pd
from types import MappingProxyType
from hmmlearn.hmm import GaussianHMM
from sklearn.preprocessing import StandardScaler


FEATURE_COLUMNS = (
    "log_return", "volatility_20", "distance_ma20", "distance_ma50", "distance_ma200",
)
WARMUP_ROWS = 200
TRAIN_START = pd.Timestamp("2018-01-01")
TRAIN_END = pd.Timestamp("2022-12-31")
MIN_TRAIN_FEATURES = 300
HMM_PARAMETERS = MappingProxyType({
    "n_components": 4, "covariance_type": "diag", "random_state": 42,
    "n_iter": 500, "tol": 0.001, "min_covar": 0.001, "implementation": "log",
})
REGIME_NAMES = ("BULL", "BEAR", "CHOPPY", "CONSOLIDATION")


def _as_date(value: str | pd.Timestamp) -> pd.Timestamp:
    """Chuẩn hóa ngày EOD, từ chối giờ hoặc múi giờ không rõ hợp đồng."""
    date = pd.Timestamp(value)
    if pd.isna(date) or date.tz is not None or date != date.normalize():
        raise ValueError("Mốc EOD phải là ngày hợp lệ, không có giờ hoặc múi giờ")
    return date


def _validate_history(frame: pd.DataFrame) -> pd.DataFrame:
    """Xác thực giá đóng cửa VN-Index; không tự sửa, sắp xếp hoặc bỏ nến lỗi."""
    if not {"Datetime", "Close"}.issubset(frame.columns) or frame.empty:
        raise ValueError("Lịch sử phải có Datetime và Close, không được rỗng")
    if frame.attrs.get("symbol", "VNINDEX") != "VNINDEX":
        raise ValueError("Bộ nhận diện chỉ nhận lịch sử VNINDEX")
    result = frame.loc[:, ["Datetime", "Close"]].copy()
    try:
        result["Datetime"] = pd.to_datetime(result["Datetime"], errors="raise")
        result["Close"] = pd.to_numeric(result["Close"], errors="raise")
    except (TypeError, ValueError) as exc:
        raise ValueError("Ngày hoặc giá đóng cửa không hợp lệ") from exc
    dates = result["Datetime"]
    if (dates.isna().any() or dates.dt.tz is not None
            or not dates.equals(dates.dt.normalize())
            or dates.duplicated().any() or not dates.is_monotonic_increasing):
        raise ValueError("Lịch phiên phải tăng dần, duy nhất, không thiếu ngày hoặc chứa giờ")
    prices = result["Close"].to_numpy(dtype=float)
    if not np.isfinite(prices).all() or (prices <= 0).any():
        raise ValueError("Giá đóng cửa phải dương và hữu hạn")
    return result.reset_index(drop=True)


def build_regime_features(
    point_in_time_df: pd.DataFrame, as_of_date: str | pd.Timestamp,
) -> pd.DataFrame:
    """Tính đặc trưng EOD; input có nến sau cutoff bị từ chối ngay."""
    date = _as_date(as_of_date)
    history = _validate_history(point_in_time_df)
    if history["Datetime"].max() > date:
        raise ValueError("Lịch sử chứa nến sau as_of_date")
    if len(history) < WARMUP_ROWS:
        raise ValueError("Cần ít nhất 200 phiên để khởi động MA200")
    close = history["Close"]
    returns = np.log(close / close.shift(1))
    features = pd.DataFrame({
        "Datetime": history["Datetime"],
        "log_return": returns,
        "volatility_20": returns.rolling(20, min_periods=20).std(ddof=1),
        **{f"distance_ma{window}": close / close.rolling(window, min_periods=window).mean() - 1.0
           for window in (20, 50, 200)},
    })
    features = features.iloc[WARMUP_ROWS - 1:].reset_index(drop=True)
    if not np.isfinite(features.loc[:, FEATURE_COLUMNS].to_numpy(dtype=float)).all():
        raise ValueError("Đặc trưng không hữu hạn sau khởi động")
    return features


def training_data_hash(frame: pd.DataFrame) -> str:
    """Băm đúng ngày và Close được dùng, độc lập index của DataFrame."""
    history = _validate_history(frame)
    history["Close"] = history["Close"].astype(float)
    canonical = history.to_csv(index=False, date_format="%Y-%m-%d", float_format="%.17g", lineterminator="\n")
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _runtime_versions() -> dict[str, str]:
    """Ghi môi trường số học để kiểm tra khả năng tái lập khi nạp."""
    return {"python": platform.python_version(), **{
        name: version(name) for name in ("numpy", "pandas", "scipy", "hmmlearn", "scikit-learn")
    }}


def _payload_hash(payload: dict[str, Any]) -> str:
    """Băm nội dung JSON chuẩn, đồng thời từ chối NaN và Infinity."""
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _regime_calibration(metadata: dict[str, Any]) -> dict[str, Any]:
    """Ánh xạ latent và quyết định fallback bằng tiêu chí đã chốt trên train."""
    means = np.asarray(metadata["state_feature_means"], dtype=float)
    occupancy = np.asarray(metadata["state_occupancy"], dtype=float)
    bull = min(range(4), key=lambda state: (-means[state, 4], state))
    bear = min((state for state in range(4) if state != bull), key=lambda state: (means[state, 4], state))
    neutral = [state for state in range(4) if state not in (bull, bear)]
    choppy = min(neutral, key=lambda state: (-means[state, 1], state))
    consolidation = next(state for state in neutral if state != choppy)
    names = [""] * 4
    for state, name in ((bull, "BULL"), (bear, "BEAR"), (choppy, "CHOPPY"), (consolidation, "CONSOLIDATION")):
        names[state] = name
    reasons = []
    if not metadata["em_converged"]:
        reasons.append("EM chưa hội tụ theo tiêu chí gain đã chốt")
    if (occupancy < 0.05).any():
        reasons.append("Có trạng thái chiếm dưới 5% posterior train")
    if not (means[bull, 4] > 0 and means[bear, 4] < 0):
        reasons.append("BULL/BEAR không tách được hai phía MA200")
    if means[bull, 4] - means[bear, 4] < 0.5 * metadata["ma200_train_std"]:
        reasons.append("Khoảng cách BULL/BEAR dưới ngưỡng phân tách")
    if not (means[choppy, 1] > 0 and means[choppy, 1] >= 1.1 * means[consolidation, 1]):
        reasons.append("CHOPPY/CONSOLIDATION không tách đủ biến động")
    return {"calibration_rule_version": 1, "latent_state_names": names,
            "classification_method": "MULTI_FACTOR" if reasons else "HMM", "fallback_reasons": reasons}


def _fallback_regime(feature: np.ndarray, metadata: dict[str, Any]) -> str:
    """Phân loại đa yếu tố bằng MA và ngưỡng biến động chỉ từ tập train."""
    _, volatility, _, distance50, distance200 = feature
    threshold = metadata["trend_threshold"]
    if distance50 > 0 and distance200 > threshold:
        return "BULL"
    if distance50 < 0 and distance200 < -threshold:
        return "BEAR"
    if volatility > 0 and volatility >= metadata["volatility_quantiles"][1]:
        return "CHOPPY"
    return "CONSOLIDATION"


class MarketRegimeDetector:
    """Quản lý HMM/scaler đóng băng; mỗi instance chỉ được fit một lần."""

    def __init__(self) -> None:
        self._model: GaussianHMM | None = None
        self._scaler: StandardScaler | None = None
        self._metadata: dict[str, Any] = {}

    @property
    def metadata(self) -> dict[str, Any]:
        """Trả bản sao metadata, không cho caller sửa trạng thái đã đóng băng."""
        return deepcopy(self._metadata)

    def fit(self, training_df: pd.DataFrame) -> MarketRegimeDetector:
        """Fit prefix VN-Index trong 2018–2022; không cắt bỏ nến ngoài khoảng."""
        if self._model is not None:
            raise ValueError("Instance đã fit hoặc nạp artifact; không được refit")
        history = _validate_history(training_df)
        if history.Datetime.min() < TRAIN_START or history.Datetime.max() > TRAIN_END:
            raise ValueError("Tập train phải nằm hoàn toàn trong 2018–2022")
        features = build_regime_features(history, history.Datetime.iloc[-1])
        if len(features) < MIN_TRAIN_FEATURES:
            raise ValueError("Cần ít nhất 300 hàng đặc trưng sau khởi động để fit HMM")
        raw = features.loc[:, FEATURE_COLUMNS].to_numpy(dtype=float)
        scaler = StandardScaler().fit(raw)
        model = GaussianHMM(**HMM_PARAMETERS).fit(scaler.transform(raw))
        posterior = model.predict_proba(scaler.transform(raw))
        mass = posterior.sum(axis=0)
        state_means = posterior.T @ raw / np.maximum(mass[:, None], np.finfo(float).tiny)
        gains = list(model.monitor_.history)
        gain = float(gains[-1] - gains[-2]) if len(gains) >= 2 else None
        self._model, self._scaler = model, scaler
        self._metadata = {
            "source_symbol": "VNINDEX", "parameters": dict(HMM_PARAMETERS),
            "feature_columns": list(FEATURE_COLUMNS), "versions": _runtime_versions(),
            "train_start_date": history.Datetime.iloc[0].strftime("%Y-%m-%d"),
            "train_end_date": history.Datetime.iloc[-1].strftime("%Y-%m-%d"),
            "training_rows": int(len(history)), "feature_rows": int(len(features)),
            "training_data_sha256": training_data_hash(history),
            "iterations": int(model.monitor_.iter), "last_gain": gain,
            "em_converged": bool(gain is not None and 0 <= gain < HMM_PARAMETERS["tol"]
                                 and model.monitor_.iter < HMM_PARAMETERS["n_iter"]),
            "state_occupancy": (mass / len(raw)).tolist(), "state_feature_means": state_means.tolist(),
            "volatility_quantiles": np.quantile(raw[:, 1], [1 / 3, 2 / 3]).tolist(),
            "trend_threshold": float(np.median(np.abs(raw[:, 4]))),
            "ma200_train_std": float(raw[:, 4].std(ddof=1)),
            "price_basis_status": "UNVERIFIED", "artifact_purpose": "RESEARCH_ONLY",
        }
        self._metadata.update(_regime_calibration(self._metadata))
        self._validate_fitted()
        return self

    def _validate_fitted(self) -> None:
        """Từ chối model/scaler/metadata sai thay vì suy luận tiếp âm thầm."""
        if self._model is None or self._scaler is None:
            raise ValueError("Chưa fit hoặc nạp model")
        meta, model, scaler = self._metadata, self._model, self._scaler
        try:
            if (meta["source_symbol"] != "VNINDEX" or meta["parameters"] != dict(HMM_PARAMETERS)
                    or meta["feature_columns"] != list(FEATURE_COLUMNS)
                    or meta["versions"] != _runtime_versions()
                    or meta["price_basis_status"] != "UNVERIFIED"
                    or meta["artifact_purpose"] != "RESEARCH_ONLY"):
                raise ValueError("Metadata, cấu hình, nguồn hoặc phiên bản không khớp")
            start, end = _as_date(meta["train_start_date"]), _as_date(meta["train_end_date"])
            if not TRAIN_START <= start <= end <= TRAIN_END:
                raise ValueError("Khoảng train trong artifact không hợp lệ")
            if (type(meta["training_rows"]) is not int or type(meta["feature_rows"]) is not int
                    or meta["feature_rows"] != meta["training_rows"] - 199
                    or meta["feature_rows"] < MIN_TRAIN_FEATURES):
                raise ValueError("Số hàng train không khớp khởi động")
            digest = meta["training_data_sha256"]
            if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError("Hash dữ liệu train không hợp lệ")
            arrays = [model.startprob_, model.transmat_, model.means_, model.covars_,
                      scaler.mean_, scaler.scale_, scaler.var_]
            if any(not np.isfinite(array).all() for array in arrays):
                raise ValueError("Tham số model/scaler không hữu hạn")
            if (model.startprob_.shape != (4,) or model.transmat_.shape != (4, 4)
                    or model.means_.shape != (4, 5) or model.covars_.shape != (4, 5, 5)
                    or any(array.shape != (5,) for array in (scaler.mean_, scaler.scale_, scaler.var_))):
                raise ValueError("Kích thước model/scaler không khớp")
            if ((model.startprob_ < 0).any() or (model.transmat_ < 0).any()
                    or not np.isclose(model.startprob_.sum(), 1)
                    or not np.allclose(model.transmat_.sum(axis=1), 1)
                    or (np.diagonal(model.covars_, axis1=1, axis2=2) <= 0).any()
                    or (scaler.scale_ <= 0).any() or (scaler.var_ < 0).any()
                    or not np.allclose(scaler.scale_, np.where(scaler.var_ > 0, np.sqrt(scaler.var_), 1))):
                raise ValueError("Xác suất, covariance hoặc scaler không hợp lệ")
            occupancy = np.asarray(meta["state_occupancy"], dtype=float)
            means = np.asarray(meta["state_feature_means"], dtype=float)
            quantiles = np.asarray(meta["volatility_quantiles"], dtype=float)
            if (occupancy.shape != (4,) or means.shape != (4, 5) or quantiles.shape != (2,)
                    or not all(np.isfinite(a).all() for a in (occupancy, means, quantiles))
                    or (occupancy < 0).any() or not np.isclose(occupancy.sum(), 1)
                    or not 0 <= quantiles[0] <= quantiles[1]
                    or not np.isfinite(meta["trend_threshold"]) or meta["trend_threshold"] < 0
                    or not np.isfinite(meta["ma200_train_std"]) or meta["ma200_train_std"] < 0):
                raise ValueError("Thống kê calibration không hợp lệ")
            calibration = _regime_calibration(meta)
            if any(meta[key] != value for key, value in calibration.items()):
                raise ValueError("Ánh xạ trạng thái hoặc quyết định fallback không khớp train")
        except (KeyError, TypeError, AttributeError, IndexError) as exc:
            raise ValueError("Artifact thiếu hoặc sai trường bắt buộc") from exc

    def save(self, path: str | Path) -> None:
        """Lưu JSON model/scaler nguyên tử, có checksum và không dùng pickle."""
        self._validate_fitted()
        model, scaler = self._model, self._scaler
        payload = {
            "format_version": 2, "metadata": self.metadata,
            "model": {"startprob": model.startprob_.tolist(), "transmat": model.transmat_.tolist(),
                      "means": model.means_.tolist(),
                      "covars": np.diagonal(model.covars_, axis1=1, axis2=2).tolist()},
            "scaler": {"mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist(), "var": scaler.var_.tolist()},
        }
        envelope = {"sha256": _payload_hash(payload), "payload": payload}
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent, delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(envelope, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(target)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()

    @classmethod
    def load(cls, path: str | Path, *, expected_training_hash: str | None = None) -> MarketRegimeDetector:
        """Nạp tham số JSON đã xác thực; khác dữ liệu/môi trường phải báo lỗi."""
        try:
            envelope = json.loads(Path(path).read_text(encoding="utf-8"))
            payload = envelope["payload"]
            if envelope["sha256"] != _payload_hash(payload) or payload["format_version"] not in (1, 2):
                raise ValueError("Checksum hoặc phiên bản artifact không hợp lệ")
            result = cls()
            result._metadata = payload["metadata"]
            if payload["format_version"] == 1:
                result._metadata.update(_regime_calibration(result._metadata))
            result._model = GaussianHMM(**HMM_PARAMETERS)
            model = payload["model"]
            result._model.startprob_ = np.asarray(model["startprob"], dtype=float)
            result._model.transmat_ = np.asarray(model["transmat"], dtype=float)
            result._model.means_ = np.asarray(model["means"], dtype=float)
            result._model.covars_ = np.asarray(model["covars"], dtype=float)
            result._model.n_features = len(FEATURE_COLUMNS)
            result._scaler = StandardScaler()
            scaler = payload["scaler"]
            result._scaler.mean_ = np.asarray(scaler["mean"], dtype=float)
            result._scaler.scale_ = np.asarray(scaler["scale"], dtype=float)
            result._scaler.var_ = np.asarray(scaler["var"], dtype=float)
            result._scaler.n_features_in_ = len(FEATURE_COLUMNS)
            result._scaler.n_samples_seen_ = result._metadata["feature_rows"]
            result._validate_fitted()
            if expected_training_hash is not None and result._metadata["training_data_sha256"] != expected_training_hash:
                raise ValueError("Artifact không khớp hash dữ liệu train yêu cầu")
            return result
        except (KeyError, TypeError, AttributeError, IndexError, json.JSONDecodeError) as exc:
            raise ValueError("Nội dung artifact không hợp lệ") from exc
