"""Baselines R1 với fit theo thời gian và ledger MTM hằng phiên quan sát."""

from __future__ import annotations

from datetime import timedelta
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
import talib

from core.alpha_compare import (ALPHA_REGISTRY, build_features, ts_corr, ts_mean, ts_rank,
                                ts_sum, delay, delta, sign, decay_linear)
from core.revision_audit import sha256_file
from utils.statistical_tests import binary_classification_metrics


def validate_prices(frame: pd.DataFrame) -> None:
    """Từ chối snapshot thiếu/trùng ngày hoặc có giá/volume không hợp lệ."""
    dates = pd.to_datetime(frame["date"], errors="raise")
    if dates.duplicated().any() or not dates.is_monotonic_increasing:
        raise ValueError("Ngày snapshot phải tăng nghiêm ngặt và không trùng")
    prices = frame[["Open", "High", "Low", "Close"]].to_numpy(dtype=float)
    volume = frame["Volume"].to_numpy(dtype=float)
    if not np.isfinite(prices).all() or (prices <= 0).any():
        raise ValueError("OHLC phải dương và hữu hạn")
    if not np.isfinite(volume).all() or (volume < 0).any() or not volume.sum() > 0:
        raise ValueError("Volume phải hữu hạn, không âm và có giao dịch")
    if ((prices[:, 1] < prices[:, [0, 2, 3]].max(axis=1)) |
            (prices[:, 2] > prices[:, [0, 1, 3]].min(axis=1))).any():
        raise ValueError("OHLC vi phạm thứ tự High/Low")


def load_prices(directory: Path, quality_policy: str = "reject") -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    """Chỉ đọc snapshot đã hash; đường đánh giá không chứa vendor/network fallback."""
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    frames, quality_views = {}, {}
    for record in manifest["symbols"]:
        path = (directory / record["path"]).resolve()
        if not path.is_relative_to(directory.resolve()) or sha256_file(path) != record["sha256"]:
            raise ValueError("Hash/đường dẫn snapshot không hợp lệ")
        frame = pd.read_csv(path)
        if len(frame) != record["n_rows"] or record["symbol"] in frames:
            raise ValueError("Số dòng hoặc symbol snapshot không hợp lệ")
        bad_ohlc = ((frame["High"] < frame[["Open", "Close", "Low"]].max(axis=1)) |
                    (frame["Low"] > frame[["Open", "Close", "High"]].min(axis=1)))
        if bad_ohlc.any() and quality_policy == "valid_suffix_after_last_bad_ohlc":
            last_bad = int(np.flatnonzero(bad_ohlc.to_numpy())[-1])
            quality_views[record["symbol"]] = {"excluded_prefix_rows": last_bad + 1,
                "invalid_ohlc_rows": frame.loc[bad_ohlc].to_dict(orient="records"),
                "reason": "unverified OHLC contradiction; retain raw file, no synthetic correction",
                "analysis_first_date": str(frame["date"].iloc[last_bad + 1]) if last_bad + 1 < len(frame) else None}
            frame = frame.iloc[last_bad + 1:].reset_index(drop=True)
        validate_prices(frame)
        frames[record["symbol"]] = frame
    manifest = {**manifest, "analysis_quality_views": quality_views}
    return frames, manifest


def sentiment_features(dates: pd.Series, articles: list[dict[str, Any]]) -> pd.DataFrame:
    """Chỉ nhận score có provenance và available_at; ngày trần sang ngày tiếp theo.

    Thiếu score giữ NaN và missingness riêng, không đồng nhất với sentiment neutral.
    Không đọc full text hoặc gọi scorer/LLM trong đường này.
    """
    observations = []
    for article in articles:
        publication = article.get("date_parsed")
        available = article.get("available_at")
        if not available and publication:
            available = (pd.Timestamp(publication) + timedelta(days=1)).isoformat()
        try:
            stamp = pd.Timestamp(available)
            stamp = stamp.tz_localize("Asia/Ho_Chi_Minh") if stamp.tzinfo is None else stamp.tz_convert("Asia/Ho_Chi_Minh")
            score = float(article.get("numeric_score", float("nan")))
            known = article.get("scorer") in ("visobert", "lexicon")
            if pd.isna(stamp) or not known or not np.isfinite(score) or not -1 <= score <= 1:
                continue
            observations.append((stamp, score))
        except (ValueError, TypeError):
            continue
    rows = []
    for day in dates:
        cutoff = pd.Timestamp(day).tz_localize("Asia/Ho_Chi_Minh") + pd.Timedelta(hours=23, minutes=59, seconds=59)
        eligible = [(stamp, score) for stamp, score in observations
                    if cutoff - pd.Timedelta(days=90) <= stamp <= cutoff]
        reliable = len(eligible) >= 3
        if reliable:
            age = np.asarray([(cutoff - stamp).total_seconds() / 86400 for stamp, _ in eligible])
            weights = np.exp(-np.log(2) * age / 30)
            score = float(np.average([score for _, score in eligible], weights=weights))
        else:
            score = np.nan
        rows.append((score, float(not reliable), float(len(eligible))))
    return pd.DataFrame(rows, columns=["sentiment_score", "sentiment_missing", "verified_article_count"])


def numerical_features(frame: pd.DataFrame, articles: list[dict[str, Any]]) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Tạo các feature nhân quả; không chuẩn hóa/định hướng trên toàn bộ frame."""
    validate_prices(frame)
    close = frame["Close"].astype(float)
    high, low = frame["High"].to_numpy(float), frame["Low"].to_numpy(float)
    values = close.to_numpy(float)
    macd, signal, hist = talib.MACD(values)
    stoch, _ = talib.STOCH(high, low, values)
    price = pd.DataFrame({
        "return_1": close.pct_change(), "return_5": close.pct_change(5),
        "return_20": close.pct_change(20), "return_60": close.pct_change(60),
        "volatility_20": close.pct_change().rolling(20).std(),
        "body": close / frame["Open"] - 1, "range": (frame["High"] - frame["Low"]) / close,
        "volume_ratio_20": frame["Volume"] / frame["Volume"].rolling(20).mean(),
        "rsi_14": talib.RSI(values) / 100, "macd": macd / values,
        "macd_signal": signal / values, "macd_hist": hist / values,
        "stoch": stoch / 100, "willr": talib.WILLR(high, low, values) / 100,
        "cci": talib.CCI(high, low, values) / 100,
        "sma60_gap": close / close.rolling(60).mean() - 1,
    })
    # build_features không được phép đổi toàn bộ series sang volume proxy ở đây.
    prepared = build_features(frame)
    # Năm công thức gọi normalize_alpha toàn prefix phải có bản chuyển đổi nhân quả.
    # Không sửa registry legacy: baseline mới ghi rõ khác biệt này trong protocol.
    def causal_scale(series: pd.Series) -> pd.Series:
        mean = series.expanding(min_periods=2).mean()
        std = series.expanding(min_periods=2).std().replace(0, np.nan)
        return np.tanh((series - mean) / std).fillna(0)

    low_corr = ts_corr(prepared["adv20"], prepared["Low"], 5)
    # Phần rank đổi dấu của WQ29 giữ đúng thứ tự operator từ registry.
    inner = -ts_rank(ts_rank(delta(prepared["Close"], 5), 20), 20)
    log_value = np.log(ts_sum(ts_rank(-inner, 5).abs(), 2).replace(0, 1e-9))
    body = ((prepared["Close"] - prepared["Low"]) - (prepared["High"] - prepared["Close"])) / (prepared["High"] - prepared["Low"]).replace(0, 1e-9) * prepared["volume"]
    argmax = prepared["Close"].rolling(10, min_periods=1).apply(lambda x: float(np.argmax(x)), raw=True)
    adapters = {
        "WQ28_CorrLowClose": causal_scale(low_corr + (prepared["High"] + prepared["Low"]) / 2 - prepared["Close"]),
        "WQ29_NestedRankLog": ts_rank(causal_scale(log_value), 5) + ts_rank(delay(-prepared["returns"], 6), 5),
        "WQ31_DecayDeltaCorr": ts_rank(ts_rank(ts_rank(
            decay_linear(-ts_rank(ts_rank(delta(prepared["Close"], 10), 20), 20), 10), 20), 20), 20)
            + ts_rank(-delta(prepared["Close"], 3), 20) + sign(causal_scale(ts_corr(prepared["adv20"], prepared["Low"], 12))),
        "WQ32_ScaleCorr230": causal_scale(ts_mean(prepared["Close"], 7) - prepared["Close"])
            + 20 * causal_scale(ts_corr(prepared["vwap"], delay(prepared["Close"], 5), 230)),
        "WQ60_BodyScaleArgmax": -(2 * causal_scale(ts_rank(body, 20)) - causal_scale(ts_rank(argmax, 20))),
    }
    if not set(adapters).issubset(ALPHA_REGISTRY):
        raise ValueError("Registry alpha không khớp các bản chuyển đổi nhân quả đã khóa")
    factors = pd.DataFrame({f"alpha_{key}": adapters[key] if key in adapters else fn(prepared)
                            for key, (fn, _) in ALPHA_REGISTRY.items()})
    sentiment = sentiment_features(frame["date"], articles)
    features = pd.concat([price, factors, sentiment], axis=1).replace([np.inf, -np.inf], np.nan)
    return features, list(price.columns), list(factors.columns)


def samples(frame: pd.DataFrame, protocol: dict[str, Any]) -> pd.DataFrame:
    """Xác định target net/gross riêng với horizon theo phiên quan sát, không rút ngắn."""
    horizon = int(protocol["horizon_observed_sessions"])
    start = int(protocol["warmup_sessions"])
    decision = np.arange(start, len(frame) - horizon, int(protocol["training_step"]))
    entry, exit_index = decision + 1, decision + horizon
    gross = frame["Close"].to_numpy(float)[exit_index] / frame["Open"].to_numpy(float)[entry] - 1
    fee, slip = protocol["fee_each_side"], protocol["slippage_each_side"]
    net = (gross + 1) * (1 - fee) * (1 - slip) / ((1 + fee) * (1 + slip)) - 1
    return pd.DataFrame({"decision": decision, "entry": entry, "exit": exit_index,
                         "date": frame["date"].to_numpy()[decision],
                         "exit_date": frame["date"].to_numpy()[exit_index],
                         "net_return": net, "gross_return": gross,
                         "label": (net > 0).astype(int), "label_gross": (gross > 0).astype(int)})


def temporal_split(sample: pd.DataFrame, first_test_date: str, protocol: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    """Purge mọi label span chạm ngày quyết định đầu của validation hoặc test."""
    validation = sample.loc[(sample["date"] >= protocol["validation_start"]) &
                            (sample["exit_date"] < first_test_date)]
    if validation.empty:
        raise ValueError("Không đủ validation đã trưởng thành trước test")
    train = sample.loc[(sample["date"] <= protocol["train_end"]) &
                       (sample["exit_date"] < validation["date"].iloc[0])]
    if len(train) < 100 or len(validation) < 10:
        raise ValueError("Train/validation không đủ support đã định trước")
    return train.index.to_numpy(), validation.index.to_numpy()


def logistic_predictions(train_x: pd.DataFrame, train_y: np.ndarray, val_x: pd.DataFrame,
                         val_y: np.ndarray, test_x: pd.DataFrame, protocol: dict[str, Any]) -> tuple[np.ndarray, dict[str, Any]]:
    """Chọn C/threshold chỉ trên validation, refit preprocessing trên train+validation."""
    if len(np.unique(train_y)) != 2:
        raise ValueError("Train logistic phải có đủ hai lớp")

    def pipeline(c_value: float):
        return make_pipeline(SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True),
                             StandardScaler(), LogisticRegression(C=c_value, solver=protocol["logistic_solver"],
                             max_iter=protocol["logistic_max_iter"], random_state=0))

    best = None
    for c_value in protocol["logistic_C_grid"]:
        fitted = pipeline(c_value).fit(train_x, train_y)
        probabilities = fitted.predict_proba(val_x)[:, 1]
        for threshold in protocol["logistic_threshold_grid"]:
            predicted = probabilities >= threshold
            metrics = binary_classification_metrics(np.where(val_y, "UP", "DOWN"), np.where(predicted, "LONG", "SHORT"))
            score = metrics["balanced_accuracy"]
            if score is None:
                raise ValueError("Validation thiếu một lớp; không chọn threshold bằng accuracy thay thế")
            if best is None or score > best["validation_ba"]:
                best = {"C": c_value, "threshold": threshold, "validation_ba": score}
    final_x = pd.concat([train_x, val_x], ignore_index=True)
    final_y = np.concatenate([train_y, val_y])
    final = pipeline(best["C"]).fit(final_x, final_y)
    probabilities = final.predict_proba(test_x)[:, 1]
    best["train_rows"], best["validation_rows"] = len(train_y), len(val_y)
    best["columns"] = list(train_x.columns)
    best["refit_imputer_statistics"] = [float(x) for x in final[0].statistics_]
    best["refit_scaler_mean"] = [float(x) for x in final[1].mean_]
    best["refit_scaler_scale"] = [float(x) for x in final[1].scale_]
    best["coefficients"] = final[-1].coef_.tolist()
    best["intercept"] = final[-1].intercept_.tolist()
    best["test_probabilities"] = probabilities.tolist()
    best["converged"] = bool(np.max(final[-1].n_iter_) < protocol["logistic_max_iter"])
    if not best["converged"]:
        raise ValueError("Logistic không hội tụ; không công bố fit chưa đạt")
    return (probabilities >= best["threshold"]).astype(int), best


def factor_vote(train_x: pd.DataFrame, train_y: np.ndarray, test_x: pd.DataFrame) -> tuple[np.ndarray, dict[str, Any]]:
    """Vote bằng tất cả factor cố định, fit median và chiều chỉ trên train."""
    median = train_x.median().fillna(0).to_numpy(float)
    train = np.where(np.isfinite(train_x.to_numpy(float)), train_x.to_numpy(float), median) - median
    centered_y = train_y - np.mean(train_y)
    orientation = np.sign(np.mean(train * centered_y[:, None], axis=0))
    raw = np.where(np.isfinite(test_x.to_numpy(float)), test_x.to_numpy(float), median) - median
    vote = np.mean(np.sign(raw) * orientation, axis=1)
    return (vote > 0).astype(int), {"median": median.tolist(), "orientation": orientation.tolist(),
                                  "columns": list(train_x.columns), "train_rows": len(train_y)}


def daily_ledger(frame: pd.DataFrame, cycles: list[tuple[int, int, int]], protocol: dict[str, Any]) -> dict[str, Any]:
    """Mô phỏng fractional shares có phí hai chiều và close MTM, không khẳng định executable.

    cycles chứa (entry index, exit index, LONG=1/CASH=0). Cho buy-and-hold,
    caller truyền đúng một cycle từ entry đầu tới exit cuối, giữ qua mọi gap.
    """
    if not cycles:
        raise ValueError("Ledger cần lịch chu kỳ không rỗng")
    first, last = cycles[0][0], cycles[-1][1]
    if first < 0 or last >= len(frame):
        raise ValueError("Horizon ledger nằm ngoài snapshot")
    previous = -1
    for entry, exit_index, action in cycles:
        if entry <= previous or entry > exit_index or action not in (0, 1):
            raise ValueError("Chu kỳ sai thứ tự, chồng lấn hoặc action không hợp lệ")
        previous = exit_index
    fee, slip = protocol["fee_each_side"], protocol["slippage_each_side"]
    initial = protocol["initial_capital_vnd"]
    cash = float(initial)
    size = last - first + 1
    equity = np.full(size, np.nan)
    fees, slips, notional = np.zeros(size), np.zeros(size), np.zeros(size)
    held, at_close = np.zeros(size), np.zeros(size)
    next_fill = 0
    orders = 0
    for entry, exit_index, action in cycles:
        left, right = entry - first, exit_index - first
        equity[next_fill:left] = cash
        if action:
            opening = float(frame["Open"].iloc[entry])
            shares = cash / ((1 + fee) * (1 + slip) * opening)
            quoted_buy = shares * opening
            buy_value = quoted_buy * (1 + slip)
            fees[left] += buy_value * fee
            slips[left] += quoted_buy * slip
            notional[left] += quoted_buy
            marks = frame["Close"].iloc[entry:exit_index + 1].to_numpy(float) * shares
            equity[left:right + 1] = marks
            quoted_sell = marks[-1]
            sell_value = quoted_sell * (1 - slip)
            fees[right] += sell_value * fee
            slips[right] += quoted_sell * slip
            notional[right] += quoted_sell
            cash = sell_value * (1 - fee)
            equity[right] = cash
            held[left:right + 1] = 1
            at_close[left:right] = 1
            orders += 2
        else:
            equity[left:right + 1] = cash
        next_fill = right + 1
    equity[next_fill:] = cash
    anchor = np.concatenate(([initial], equity))
    drawdown = 1 - anchor / np.maximum.accumulate(anchor)
    turnover = notional / anchor[:-1]
    return {"net_return_pct": float((equity[-1] / initial - 1) * 100),
            "daily_close_drawdown_pct": float(drawdown.max() * 100), "order_count": orders,
            "mean_daily_turnover": float(turnover.mean()), "total_turnover": float(turnover.sum()),
            "held_session_fraction": float(held.mean()), "mean_close_exposure": float(at_close.mean()),
            "brokerage_fee_vnd": float(fees.sum()), "slippage_cost_vnd": float(slips.sum()),
            "daily": [{"date": str(day), "equity_vnd": float(value), "turnover": float(turn),
                       "held_during_session": int(h), "close_exposure": int(exp),
                       "brokerage_fee_vnd": float(f), "slippage_cost_vnd": float(s)}
                      for day, value, turn, h, exp, f, s in zip(frame["date"].iloc[first:last + 1],
                          equity, turnover, held, at_close, fees, slips)]}
