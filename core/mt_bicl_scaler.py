"""Scaler MT-BICL chỉ fit feature của cycle train đã đóng, không đọc nhãn."""

from __future__ import annotations

from typing import Any

import numpy as np

from core.mt_bicl_bank import BANK_VERSION, PROTOCOL_SHA256, SOURCE, SYMBOLS, TRAIN_END, canonical_bytes, content_hash, day
from core.pit_price_features import FEATURE_COLUMNS, FEATURE_VERSION, PRICE_POLICY_VERSION

SCALER_VERSION = "mt_bicl_pit_scaler_v1"


def _vector(features: dict[str, Any], cutoff: str) -> np.ndarray:
    """Không nhận feature tính sau cutoff, sai thứ tự cột hoặc số không hữu hạn."""
    if (features.get("status") != "AVAILABLE" or features.get("reasons") != []
            or features.get("feature_version") != FEATURE_VERSION
            or features.get("price_policy_version") != PRICE_POLICY_VERSION or features.get("source") != SOURCE
            or features.get("feature_columns") != list(FEATURE_COLUMNS)
            or day(features["as_of_date"]) != cutoff or day(features["feature_end_date"]) != cutoff):
        raise ValueError("Feature/scaler vi phạm cutoff hoặc schema")
    values = features.get("vector")
    if (type(values) is not list or len(values) != 4
            or any(type(v) not in (int, float) for v in values)):
        raise ValueError("Vector feature phải có bốn số Python gốc")
    vector = np.asarray(values, dtype=float)
    if not np.isfinite(vector).all():
        raise ValueError("Vector feature không hữu hạn")
    return vector


def fit_scaler(bank: dict[str, Any], query_date: str) -> dict[str, Any]:
    """Train dùng exit<query; từ 2021 chỉ fit train exit<=2020-12-31.

    Chỉ kiểm feature sau lọc cutoff; nhãn, reports và feature tương lai không
    được đọc. Caller phải nạp bank qua verifier nguồn, không qua self-seal.
    """
    query = day(query_date)
    if (bank.get("bank_version") != BANK_VERSION or bank.get("protocol_sha256") != PROTOCOL_SHA256
            or bank.get("source") != SOURCE or bank.get("feature_columns") != list(FEATURE_COLUMNS)
            or query < "2018-01-02"):
        raise ValueError("Bank/query không thuộc protocol MT-BICL")
    inclusive = query > TRAIN_END
    cutoff = TRAIN_END if inclusive else query
    selected = [row for row in bank["records"] if row["status"] == "AVAILABLE" and row["split"] == "train"
                and (day(row["exit_date"]) <= cutoff if inclusive else day(row["exit_date"]) < cutoff)]
    selected.sort(key=lambda row: (row["exit_date"], SYMBOLS.index(row["symbol"]), row["episode_id"]))
    ids = [row["episode_id"] for row in selected]
    if len(ids) != len(set(ids)):
        raise ValueError("Scaler có episode ID trùng")
    vectors = []
    for row in selected:
        date = day(row["as_of_date"])
        if (not "2018-01-02" <= date < day(row["entry_date"]) < day(row["exit_date"]) <= TRAIN_END
                or row["episode_id"] != f"{row['symbol']}-{date}"):
            raise ValueError("Ngày cycle/scaler vi phạm PIT hoặc split train")
        vectors.append(_vector(row["features"], date))
    result = {"scaler_version": SCALER_VERSION, "protocol_sha256": PROTOCOL_SHA256,
              "mode": "frozen_train" if inclusive else "historical_prefix", "fit_cutoff": cutoff,
              "fit_inclusive": inclusive, "feature_columns": list(FEATURE_COLUMNS),
              "fit_episode_ids": ids, "fit_ids_sha256": content_hash(ids), "fit_count": len(ids),
              "fit_min_exit_date": min((row["exit_date"] for row in selected), default=None),
              "fit_max_exit_date": max((row["exit_date"] for row in selected), default=None),
              "status": "AVAILABLE" if len(ids) >= 2 else "UNAVAILABLE",
              "reasons": [] if len(ids) >= 2 else ["SCALER_NO_CLOSED_HISTORY"],
              "mean": None, "variance": None, "scale": None, "zero_variance": None}
    if len(ids) >= 2:
        matrix = np.asarray(vectors, dtype=float)
        mean = matrix.mean(axis=0)
        variance = ((matrix-mean)**2).mean(axis=0)
        scale = np.where(variance > 0, np.sqrt(variance), 1.)
        if not all(np.isfinite(v).all() for v in (mean, variance, scale)):
            raise ValueError("Tham số scaler không hữu hạn")
        result.update(mean=mean.tolist(), variance=variance.tolist(), scale=scale.tolist(),
                      zero_variance=(variance == 0).tolist())
    canonical_bytes(result)
    return result


def transform_features(features: dict[str, Any], scaler: dict[str, Any], *,
                       query_date: str | None = None) -> dict[str, Any]:
    """Giữ raw/z đầy đủ và model vector clip; không dùng label query để biến đổi."""
    if scaler.get("scaler_version") != SCALER_VERSION or scaler.get("protocol_sha256") != PROTOCOL_SHA256:
        raise ValueError("Scaler khác protocol")
    cutoff = day(features["as_of_date"])
    query = cutoff if query_date is None else day(query_date)
    if (cutoff > query or scaler["fit_cutoff"] > query
            or (scaler["fit_inclusive"] and scaler["fit_cutoff"] >= query)
            or (scaler["fit_max_exit_date"] is not None and scaler["fit_max_exit_date"] >= query)):
        raise ValueError("Scaler chứa cycle chưa đóng trước feature query")
    if (features.get("status") not in ("AVAILABLE", "UNAVAILABLE")
            or bool(features.get("reasons")) != (features["status"] == "UNAVAILABLE")
            or (features.get("feature_end_date") is not None and day(features["feature_end_date"]) > cutoff)):
        raise ValueError("Trạng thái hoặc ngày feature không hợp lệ")
    reasons = [*features.get("reasons", []), *scaler["reasons"]]
    result = {"status": "UNAVAILABLE" if reasons else "AVAILABLE", "reasons": reasons,
              "as_of_date": cutoff, "raw": None, "z": None, "model_vector": None,
              "scaler_sha256": content_hash(scaler)}
    if features["status"] == "AVAILABLE":
        result["raw"] = _vector(features, cutoff).tolist()
    if not reasons:
        vector = np.asarray(result["raw"], dtype=float)
        mean, scale = np.asarray(scaler["mean"], dtype=float), np.asarray(scaler["scale"], dtype=float)
        if mean.shape != (4,) or scale.shape != (4,) or (scale <= 0).any():
            raise ValueError("Tham số scaler không hợp lệ")
        z = (vector-mean)/scale
        if not np.isfinite(z).all():
            raise ValueError("Vector chuẩn hóa không hữu hạn")
        result.update(z=z.tolist(), model_vector=np.clip(z, -4, 4).tolist())
    canonical_bytes(result)
    return result
