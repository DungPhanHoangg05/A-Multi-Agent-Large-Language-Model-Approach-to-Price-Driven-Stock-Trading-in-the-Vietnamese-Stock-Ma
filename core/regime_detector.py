"""Nhận diện chế độ VN-Index từ đặc trưng chỉ sử dụng lịch sử đã biết."""

from __future__ import annotations

import numpy as np
import pandas as pd
from types import MappingProxyType


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
