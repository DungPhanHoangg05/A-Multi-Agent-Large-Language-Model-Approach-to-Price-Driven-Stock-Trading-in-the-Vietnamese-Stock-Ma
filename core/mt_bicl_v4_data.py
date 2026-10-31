"""Đặc trưng liên tục và nhãn v4 từ giá thô; không đọc report hoặc fit learner."""

from __future__ import annotations

import csv
from functools import partial
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import talib
from numpy.lib.stride_tricks import sliding_window_view

from core.backtest_engine import compute_round_trip_net_return
from core.execution_prices import corporate_action_barriers, validate_raw_frame
from core.mt_bicl_v4_protocol import canonical, checksum

NUMERIC = ("momentum_5", "momentum_20", "volatility_20", "ma_distance_20",
           "macd_hist_relative", "relative_volume_20", "range_20",
           "index_momentum_20", "index_volatility_20")


def bounded_index(path: Path, end: str) -> pd.DataFrame:
    """Dừng trước chuyển giá sau cutoff thành số; không phân tích payoff2025."""
    rows = []
    with path.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            if row["Datetime"][:10] > end:
                break
            rows.append({"Datetime": pd.Timestamp(row["Datetime"]), "Close": float(row["Close"])})
    frame = pd.DataFrame(rows)
    dates = pd.DatetimeIndex(frame["Datetime"])
    if (dates.has_duplicates or dates.hasnans or not dates.is_monotonic_increasing
            or dates.tz is not None or not dates.equals(dates.normalize())
            or not np.isfinite(frame["Close"]).all() or frame["Close"].le(0).any()):
        raise ValueError("Lịch/Close VNINDEX không hợp lệ")
    return frame


def feature_rows(frame: pd.DataFrame, events: list[dict[str, Any]], history: pd.DataFrame,
                 calendar: pd.DatetimeIndex, indices: np.ndarray) -> list[dict[str, Any]]:
    """Rolling vector hóa, MACD riêng prefix45; payoff không tham gia phép tính X."""
    cutoff = calendar[-1]
    frame = frame.loc[pd.to_datetime(frame["Datetime"]) <= cutoff].copy()
    events = [e for e in events if e.get("exrightDate") and e["exrightDate"][:10] <= str(cutoff.date())]
    history = history.loc[pd.to_datetime(history["Datetime"]) <= cutoff].copy()
    validate_raw_frame(frame)
    aligned = frame.set_index("Datetime").reindex(calendar)
    close, volume = aligned["Close"], aligned["Volume"]
    index_close = history.set_index("Datetime")["Close"].reindex(calendar)
    changes = close / close.shift(1) - 1
    index_changes = index_close / index_close.shift(1) - 1
    matrix = np.column_stack((close / close.shift(5) - 1, close / close.shift(20) - 1,
        changes.rolling(20).std(ddof=1), close / close.rolling(20).mean() - 1,
        np.full(len(calendar), np.nan), volume / volume.rolling(20).mean().replace(0, np.nan) - 1,
        (aligned["High"].rolling(20).max() - aligned["Low"].rolling(20).min()) / close,
        index_close / index_close.shift(20) - 1, index_changes.rolling(20).std(ddof=1)))
    if len(close) >= 45:
        windows = sliding_window_view(close.to_numpy(dtype=float), 45)
        for i in indices[indices >= 44].tolist():
            window = windows[i - 44]
            if np.isfinite(window).all():
                _, _, hist = talib.MACD(np.ascontiguousarray(window), fastperiod=12, slowperiod=26, signalperiod=9)
                matrix[i, 4] = float(hist[-1] / window[-1])
    barriers = corporate_action_barriers(frame, events)
    present = calendar.isin(pd.DatetimeIndex(frame["Datetime"]))
    required = (6, 21, 21, 20, 45, 20, 20, 21, 21)
    rows = []
    for i in indices.tolist():
        reasons = []
        mask = []
        for j, width in enumerate(required):
            start = max(0, i - width + 1)
            valid = i + 1 >= width and np.isfinite(matrix[i, j])
            if j < 7:
                valid = valid and present[start:i + 1].all()
                valid = valid and not ((barriers > calendar[start]) & (barriers <= calendar[i])).any()
            mask.append(not bool(valid))
        if i < 44:
            reasons.append("INSUFFICIENT_HISTORY_45")
        if not present[max(0, i - 44):i + 1].all():
            reasons.append("MISSING_FEATURE_SESSION")
        if ((barriers > calendar[max(0, i - 44)]) & (barriers <= calendar[i])).any():
            reasons.append("CORPORATE_ACTION_FEATURE_WINDOW")
        if mask[5] and not any(r in reasons for r in ("INSUFFICIENT_HISTORY_45", "MISSING_FEATURE_SESSION", "CORPORATE_ACTION_FEATURE_WINDOW")):
            reasons.append("MISSING_OR_ZERO_MEAN_VOLUME")
        raw = [None if missing else float(matrix[i, j]) for j, missing in enumerate(mask)]
        prefix = aligned.iloc[max(0, i - 44):i + 1]
        proof = {"dates": prefix.index.strftime("%Y-%m-%d").tolist(),
                 "OHLCV": [[None if pd.isna(x) else float(x) for x in row]
                           for row in prefix[["Open", "High", "Low", "Close", "Volume"]].to_numpy()]}
        rows.append({"status": "UNAVAILABLE" if any(mask) else "AVAILABLE", "raw": raw,
                     "missing_mask": mask, "reasons": reasons, "feature_end_date": str(calendar[i].date()),
                     "prefix45_sha256": checksum(canonical(proof))})
    return rows


def symbol_data(symbol: str, frame: pd.DataFrame, events: list[dict[str, Any]],
                history: pd.DataFrame) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Giữ mọi grid query; sidecar nhãn tách X, chỉ sinh khi đủ phiên/thanh khoản/quyền."""
    calendar = pd.DatetimeIndex(history["Datetime"])
    if not len(calendar) or calendar[0] != pd.Timestamp("2018-01-02") or calendar[-1] > pd.Timestamp("2022-12-31"):
        raise ValueError("Dataset chỉ được mở miền2018–2022, neo02/01/2018")
    indices = np.arange(20, len(calendar) - 3, 3)
    features = feature_rows(frame, events, history, calendar, indices)
    frame = frame.loc[pd.to_datetime(frame["Datetime"]) <= calendar[-1]].copy()
    events = [e for e in events if e.get("exrightDate") and e["exrightDate"][:10] <= str(calendar[-1].date())]
    aligned = frame.set_index("Datetime").reindex(calendar)
    present = calendar.isin(pd.DatetimeIndex(frame["Datetime"]))
    barriers = corporate_action_barriers(frame, events)
    entries, exits = indices + 1, indices + 3
    holding = np.column_stack((entries, entries + 1, exits))
    missing = ~present[holding].all(axis=1)
    no_volume = (aligned["Volume"].to_numpy(dtype=float)[holding] <= 0).any(axis=1)
    crossed = (np.searchsorted(barriers, calendar[exits], side="right")
               - np.searchsorted(barriers, calendar[entries], side="right")) > 0
    block_cross = indices // 63 != exits // 63
    year_cross = calendar[indices].year != calendar[exits].year
    allowed = ~(missing | no_volume | crossed | block_cross | year_cross)
    opens = aligned["Open"].to_numpy(dtype=float)[entries]
    closes = aligned["Close"].to_numpy(dtype=float)[exits]
    net = np.full(len(indices), np.nan)
    helper = np.frompyfunc(partial(compute_round_trip_net_return, fee=.0025, slippage=.001), 2, 1)
    net[allowed] = helper(opens[allowed], closes[allowed]).astype(float)
    days = calendar.strftime("%Y-%m-%d").tolist()
    rows, labels = [], {}
    for slot, i in enumerate(indices.tolist()):
        identifier = symbol + "-" + days[i]
        block = i // 63
        reasons = [r for flag, r in ((missing[slot], "MISSING_EXECUTION_SESSION"),
            (no_volume[slot], "NO_MATCHED_VOLUME_AT_EXECUTION"), (crossed[slot], "CORPORATE_ACTION_DURING_HOLDING"),
            (block_cross[slot], "CROSS_BLOCK_HOLDING"), (year_cross[slot], "PURGED_YEAR_BOUNDARY")) if flag]
        rows.append({"episode_id": identifier, "symbol": symbol, "as_of_date": days[i],
            "entry_date": days[i + 1], "exit_date": days[i + 3], "calendar_index": i,
            "task_id": f"{symbol}:block{block:04d}", "block_start_date": days[block * 63],
            "block_end_date": days[min((block + 1) * 63 - 1, len(days) - 1)],
            "block_complete": (block + 1) * 63 <= len(days), "features": features[slot],
            "label_eligible": bool(allowed[slot]), "label_reasons": reasons,
            "alpha_history_rows": int(present[:i + 1].sum())})
        if allowed[slot]:
            labels[identifier] = {"entry_open": float(opens[slot]), "exit_close": float(closes[slot]),
                                  "r_net": float(net[slot]), "y": int(net[slot] > 0)}
    canonical(rows)
    canonical(labels)
    return rows, labels


def fit_scaler(rows: list[dict[str, Any]], fit_end: str, *, query: str | None = None) -> dict[str, Any]:
    """Không đọc label value; chỉ fit cycle đã mature và numeric đủ trong train prefix."""
    if fit_end > "2020-12-31" or (query is not None and fit_end >= query):
        raise ValueError("Scaler fit sau train/query")
    eligible = [r for r in rows if r["label_eligible"] and r["exit_date"] <= fit_end
                and (query is None or r["exit_date"] < query) and r["features"]["status"] == "AVAILABLE"]
    if any(r["features"]["feature_end_date"] > r["as_of_date"] for r in eligible):
        raise ValueError("Feature dùng fit scaler nhìn tương lai")
    matrix = np.asarray([r["features"]["raw"] for r in eligible], dtype=float).reshape(-1, 9)
    if not np.isfinite(matrix).all():
        raise ValueError("Fit scaler có số không hữu hạn")
    valid = len(matrix) >= 2
    return {"fit_end": fit_end, "status": "AVAILABLE" if valid else "INSUFFICIENT_HISTORY",
            "fit_ids": [r["episode_id"] for r in eligible],
            "mean": matrix.mean(axis=0).tolist() if valid else None,
            "scale": np.maximum(matrix.std(axis=0, ddof=1), 1e-8).tolist() if valid else None}


def membership(query: dict[str, Any], rows: list[dict[str, Any]], scaler: dict[str, Any],
               regimes: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Chọn D/C bằng X/metadata trước nhãn; giữ toàn bộ query thiếu X trong audit."""
    cutoff = query["as_of_date"]
    if scaler["fit_end"] >= cutoff:
        raise ValueError("Scaler membership không được fit tại/sau query")
    if query["features"]["status"] != "AVAILABLE" or scaler["status"] != "AVAILABLE":
        return {"query_id": query["episode_id"], "prior": [], "target": [], "K": 0, "m": 0,
                "reason": "QUERY_OR_SCALER_UNAVAILABLE", "query_z": None, "ood": False}
    mean, scale = np.asarray(scaler["mean"]), np.asarray(scaler["scale"])
    z = (np.asarray(query["features"]["raw"]) - mean) / scale
    eligible = [r for r in rows if r["symbol"] == query["symbol"] and r["exit_date"] < cutoff
                and r["label_eligible"] and r["features"]["status"] == "AVAILABLE"]
    if any(r["features"]["feature_end_date"] > r["as_of_date"] for r in eligible):
        raise ValueError("Context feature nhìn tương lai")
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in eligible:
        groups.setdefault(row["task_id"], []).append(row)
    ranked = []
    target = []
    for task_id, group in groups.items():
        if task_id == query["task_id"]:
            target = sorted(group, key=lambda r: (r["as_of_date"], r["episode_id"]))[-32:]
            continue
        if not group[0]["block_complete"] or group[0]["block_end_date"] >= cutoff or len(group) < 2:
            continue
        vectors = (np.asarray([r["features"]["raw"] for r in group]) - mean) / scale
        distances = np.mean((vectors - z) ** 2, axis=1)
        regime = regimes[group[0]["episode_id"]]["task_name"]
        query_regime = regimes[query["episode_id"]]["query_name"]
        penalty = .25 if regime != "UNKNOWN" and query_regime != "UNKNOWN" and regime != query_regime else 0.
        distance = float(np.mean((vectors.mean(axis=0) - z) ** 2) + penalty)
        selected = sorted(range(len(group)), key=lambda s: (float(distances[s]),
            -pd.Timestamp(group[s]["as_of_date"]).toordinal(), group[s]["episode_id"]))[:32]
        ids = [r["episode_id"] for r in sorted([group[s] for s in selected], key=lambda r: (r["as_of_date"], r["episode_id"]))]
        latest = max(r["exit_date"] for r in group)
        ranked.append(((distance, -pd.Timestamp(latest).toordinal(), task_id),
                       {"task_id": task_id, "observation_ids": ids, "distance": distance}))
    k = max(n for n in (0, 1, 3) if n <= min(3, len(ranked)))
    prior = [task for _, task in sorted(ranked, key=lambda t: t[0])[:k]]
    ids = [identifier for task in prior for identifier in task["observation_ids"]] + [r["episode_id"] for r in target]
    by_id = {r["episode_id"]: r for r in eligible}
    intervals = sorted((by_id[i]["entry_date"], by_id[i]["exit_date"]) for i in ids)
    if len(ids) != len(set(ids)) or any(a[1] >= b[0] for a, b in zip(intervals, intervals[1:])):
        raise ValueError("Membership D/C trùng ID hoặc khoảng entry–exit")
    return {"query_id": query["episode_id"], "prior": prior,
            "target": [r["episode_id"] for r in target], "K": k, "m": len(target),
            "reason": "NUMERIC_MEMBERSHIP_ONLY_AGENT_READINESS_SEPARATE", "query_z": z.tolist(),
            "ood": bool((np.abs(z) > 6).any())}
