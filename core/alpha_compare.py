"""
alpha_compare.py — So sánh 5 alpha hiện tại vs các alpha từ bài báo "101 Formulaic Alphas"
=========================================================================================
- Tải dữ liệu lịch sử VNM (hoặc bất kỳ mã nào)
- Tính tất cả alpha candidates
- Backtest walk-forward, đo accuracy / IC / Sharpe
- In bảng xếp hạng, chọn top-5 cho VN market

Chạy:  python alpha_compare.py [SYMBOL] [TIMEFRAME]
Ví dụ: python alpha_compare.py VNM 1d
"""

import math
import sys
import time
import warnings
from typing import List, Tuple, Dict, Any

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────────────────────────
# 1. Primitives (shared by all alphas)
# ─────────────────────────────────────────────────────────────────────────────

def _safe_val(x) -> float:
    try:
        v = float(x)
        return 0.0 if (math.isnan(v) or math.isinf(v)) else v
    except Exception:
        return 0.0

def _safe_series(s: pd.Series) -> pd.Series:
    return s.replace([np.inf, -np.inf], np.nan).fillna(0.0)

def ts_rank(series: pd.Series, window: int) -> pd.Series:
    """Time-series percentile rank over rolling window [0,1]."""
    return series.rolling(window, min_periods=max(1, window // 2)).apply(
        lambda x: (x[-1] > x[:-1]).sum() / max(len(x) - 1, 1), raw=True
    )

def ts_min(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window, min_periods=1).min()

def ts_max(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window, min_periods=1).max()

def ts_std(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window, min_periods=2).std().fillna(0.0)

def ts_corr(s1: pd.Series, s2: pd.Series, window: int) -> pd.Series:
    return s1.rolling(window, min_periods=max(2, window // 2)).corr(s2).fillna(0.0)

def ts_cov(s1: pd.Series, s2: pd.Series, window: int) -> pd.Series:
    return s1.rolling(window, min_periods=max(2, window // 2)).cov(s2).fillna(0.0)

def ts_sum(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window, min_periods=1).sum().fillna(0.0)

def ts_mean(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window, min_periods=1).mean().fillna(0.0)

def decay_linear(series: pd.Series, window: int) -> pd.Series:
    """Linearly weighted decaying sum: most recent gets highest weight."""
    weights = np.arange(1, window + 1, dtype=float)
    weights /= weights.sum()
    def _apply(x):
        w = weights[-len(x):]
        w = w / w.sum()
        return float(np.dot(x, w))
    return series.rolling(window, min_periods=1).apply(_apply, raw=True).fillna(0.0)

def signed_power(series: pd.Series, power) -> pd.Series:
    """signed_power(x, a): supports scalar or Series exponent."""
    if isinstance(power, pd.Series):
        # element-wise: sign(x) * |x|^a
        def _elem(x, a):
            if x == 0: return 0.0
            try:
                return math.copysign(abs(x) ** float(a), x)
            except Exception:
                return 0.0
        return pd.Series(
            [_elem(x, a) for x, a in zip(series, power)],
            index=series.index
        )
    return series.apply(lambda x: math.copysign(abs(x) ** power, x) if x != 0 else 0.0)

def delta(series: pd.Series, period: int = 1) -> pd.Series:
    return series.diff(period).fillna(0.0)

def delay(series: pd.Series, period: int = 1) -> pd.Series:
    return series.shift(period).bfill()

def sign(series: pd.Series) -> pd.Series:
    return series.apply(lambda x: 1.0 if x > 1e-9 else (-1.0 if x < -1e-9 else 0.0))

def normalize_alpha(series: pd.Series, method: str = "zscore_tanh") -> pd.Series:
    """Normalize alpha using different methods to make them comparable."""
    clean = series.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    
    if method == "minmax":
        mn, mx = clean.min(), clean.max()
        if mx - mn < 1e-9:
            return pd.Series(0.0, index=series.index)
        return ((clean - mn) / (mx - mn)) * 2 - 1.0
        
    elif method == "rank":
        return (clean.rank(method="average") / len(clean)) * 2 - 1.0
        
    else: # default: zscore_tanh
        mu = clean.mean()
        sigma = clean.std()
        if sigma < 1e-9:
            return pd.Series(0.0, index=series.index)
        z = (clean - mu) / sigma
        return z.apply(math.tanh)

# ─────────────────────────────────────────────────────────────────────────────
# 2. Build feature frame from OHLCV DataFrame
# ─────────────────────────────────────────────────────────────────────────────

def build_features(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["returns"] = d["Close"].pct_change().fillna(0.0)
    d["log_ret"] = np.log(d["Close"] / d["Close"].shift(1)).fillna(0.0)

    # VWAP proxy: (H+L+C)/3
    d["vwap"] = (d["High"] + d["Low"] + d["Close"]) / 3.0

    # Volume
    has_vol = ("Volume" in d.columns and d["Volume"].notna().sum() > len(d) * 0.4
               and d["Volume"].sum() > 0)
    if has_vol:
        d["volume"] = d["Volume"].fillna(0.0)
        d["log_vol"] = np.log(d["Volume"].replace(0, np.nan)).ffill().fillna(0.0)
    else:
        # Volume proxy = intra-bar range
        d["volume"] = (d["High"] - d["Low"]).fillna(0.0)
        d["log_vol"] = np.log((d["High"] - d["Low"]).replace(0, np.nan)).ffill().fillna(0.0)
        has_vol = False

    d["adv20"] = ts_mean(d["volume"], 20)
    d["adv10"] = ts_mean(d["volume"], 10)

    # Close position in bar
    d["bar_range"] = (d["High"] - d["Low"]).replace(0, np.nan).ffill()
    d["close_pos"] = (d["Close"] - d["Low"]) / d["bar_range"].replace(0, 1.0) - 0.5

    d["_has_vol"] = has_vol
    return d

# ─────────────────────────────────────────────────────────────────────────────
# 3. Current 5 alphas
# ─────────────────────────────────────────────────────────────────────────────

def alpha_fdm(d: pd.DataFrame) -> pd.Series:
    """
    CURRENT Alpha 1 — Flow-Driven Momentum (FDM)
    Tanh( ROC(1)_adj × Vol_Surge × 0.5 )
    """
    roc1 = d["returns"]
    std_roc = roc1.rolling(20, min_periods=5).std().replace(0, 1e-9)
    roc_adj = roc1 / std_roc
    vol_surge = d["volume"] / d["adv20"].replace(0, 1.0)
    raw = roc_adj * vol_surge * 0.5
    return raw.apply(math.tanh)

def alpha_sfa(d: pd.DataFrame) -> pd.Series:
    """
    CURRENT Alpha 2 — Sentiment-Flow (SFA proxy using MACD hist)
    Tanh( MACD_hist_normalized + ROC_adj × 0.5 )
    """
    ema12 = d["Close"].ewm(span=12, adjust=False).mean()
    ema26 = d["Close"].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal
    z_macd = hist / (d["Close"] * 0.005 + 1e-9)
    z_macd = z_macd.apply(lambda x: math.tanh(x) * 1.5)

    std_roc = d["returns"].rolling(20, min_periods=5).std().replace(0, 1e-9)
    roc_adj = d["returns"] / std_roc
    raw = z_macd + roc_adj * 0.5
    return raw.apply(math.tanh)

def alpha_lvr(d: pd.DataFrame) -> pd.Series:
    """
    CURRENT Alpha 3 — Liquidity Void Reversion (LVR)
    Tanh( -0.8 × ZScore( (Close - SMA5)/Close ) )
    """
    sma5 = ts_mean(d["Close"], 5)
    dev5 = (d["Close"] - sma5) / d["Close"].replace(0, 1.0)
    mu = dev5.rolling(20, min_periods=5).mean().fillna(0.0)
    sigma = dev5.rolling(20, min_periods=5).std().fillna(1.0).replace(0, 1.0)
    zscore = (dev5 - mu) / sigma
    raw = -0.8 * zscore
    return raw.apply(math.tanh)

def alpha_bfe(d: pd.DataFrame) -> pd.Series:
    """
    CURRENT Alpha 4 — Bollinger Squeeze & Flow (BFE)
    Tanh( (%B - 0.5) × Vol_ZScore(5) × 1.5 )
    """
    sma20 = ts_mean(d["Close"], 20)
    std20 = ts_std(d["Close"], 20).replace(0, 1e-9)
    bb_lower = sma20 - 2 * std20
    bb_upper = sma20 + 2 * std20
    bb_width = (bb_upper - bb_lower).replace(0, 1e-9)
    pct_b = (d["Close"] - bb_lower) / bb_width

    vol_mu5 = ts_mean(d["volume"], 5)
    vol_std5 = ts_std(d["volume"], 5).replace(0, 1e-9)
    vol_z5 = (d["volume"] - vol_mu5) / vol_std5

    raw = (pct_b - 0.5) * vol_z5 * 1.5
    return raw.apply(math.tanh)

def alpha_ofe(d: pd.DataFrame) -> pd.Series:
    """
    CURRENT Alpha 5 — Order Flow Exhaustion (OFE)
    Tanh( ROC_adj × close_pos × 3.0 )
    """
    std_roc = d["returns"].rolling(20, min_periods=5).std().replace(0, 1e-9)
    roc_adj = d["returns"] / std_roc
    raw = roc_adj * d["close_pos"] * 3.0
    return raw.apply(math.tanh)

# ─────────────────────────────────────────────────────────────────────────────
# 4. Selected WQ-101 alphas — adapted for single-stock VN OHLCV
#    Adaptation rules:
#    - cross-sectional rank() → ts_rank(,20) normalized to [0,1]
#    - vwap → (H+L+C)/3
#    - adv20 → 20-day average volume
#    - returns = daily log return
# ─────────────────────────────────────────────────────────────────────────────

def wq2(d: pd.DataFrame) -> pd.Series:
    """
    WQ#2 (adapted): -correlation(ts_rank(delta(log(volume),2),6),
                                  ts_rank((close-open)/open,6), 6)
    Price/volume divergence — opens that don't match volume tend to reverse
    """
    body = (d["Close"] - d["Open"]) / d["Open"].replace(0, 1.0)
    vol_delta = delta(d["log_vol"], 2)
    s1 = ts_rank(vol_delta, 6)
    s2 = ts_rank(body, 6)
    return _safe_series(-ts_corr(s1, s2, 6))

def wq3(d: pd.DataFrame) -> pd.Series:
    """
    WQ#3 (adapted): -correlation(ts_rank(open,10), ts_rank(volume,10), 10)
    If open-price rank correlates with volume rank → contrarian signal
    """
    s1 = ts_rank(d["Open"], 10)
    s2 = ts_rank(d["volume"], 10)
    return _safe_series(-ts_corr(s1, s2, 10))

def wq6(d: pd.DataFrame) -> pd.Series:
    """
    WQ#6 (adapted): -correlation(open, volume, 10)
    Negative open-volume correlation as signal
    """
    return _safe_series(-ts_corr(d["Open"], d["volume"], 10))

def wq7(d: pd.DataFrame) -> pd.Series:
    """
    WQ#7 (adapted): volume>adv20 ? (-ts_rank(abs(delta(close,7)),60) * sign(delta(close,7))) : -1
    Volume surge × momentum reversal
    """
    vol_flag = (d["volume"] > d["adv20"]).astype(float)
    abs_delta7 = abs(delta(d["Close"], 7))
    s_delta7 = sign(delta(d["Close"], 7))
    rank_abs = ts_rank(abs_delta7, 30)
    result = vol_flag * (-rank_abs * s_delta7) + (1 - vol_flag) * (-1.0)
    return _safe_series(result)

def wq9(d: pd.DataFrame) -> pd.Series:
    """
    WQ#9 (adapted): 0 < ts_min(delta(close,1),5) → delta(close,1)
                    else ts_max(delta(close,1),5) < 0 → delta(close,1)
                    else -delta(close,1)
    Momentum continuation vs reversal
    """
    d1 = delta(d["Close"], 1)
    min5 = ts_min(d1, 5)
    max5 = ts_max(d1, 5)
    cond1 = (min5 > 0).astype(float)
    cond2 = (max5 < 0).astype(float)
    result = cond1 * d1 + (1 - cond1) * (cond2 * d1 + (1 - cond2) * (-d1))
    return _safe_series(result)

def wq12(d: pd.DataFrame) -> pd.Series:
    """
    WQ#12: sign(delta(volume,1)) * (-1 * delta(close,1))
    Volume increase → expect close to reverse
    """
    return _safe_series(sign(delta(d["volume"], 1)) * (-delta(d["Close"], 1)))

def wq13(d: pd.DataFrame) -> pd.Series:
    """
    WQ#13 (adapted): -ts_rank(covariance(ts_rank(close,5), ts_rank(volume,5), 5), 5)
    High close-volume covariance predicts reversal
    """
    rc = ts_rank(d["Close"], 5)
    rv = ts_rank(d["volume"], 5)
    cov = ts_cov(rc, rv, 5)
    return _safe_series(-ts_rank(cov, 5))

def wq16(d: pd.DataFrame) -> pd.Series:
    """
    WQ#16 (adapted): -ts_rank(covariance(ts_rank(high,5), ts_rank(volume,5), 5), 5)
    High-volume covariance reversal
    """
    rh = ts_rank(d["High"], 5)
    rv = ts_rank(d["volume"], 5)
    cov = ts_cov(rh, rv, 5)
    return _safe_series(-ts_rank(cov, 5))

def wq19(d: pd.DataFrame) -> pd.Series:
    """
    WQ#19 (adapted): (-sign((close - delay(close,7)) + delta(close,7)))
                     * (1 + ts_rank(1+sum(returns,250), 20))
    Long-term trend × short-term reversal
    """
    gap7 = d["Close"] - delay(d["Close"], 7)
    d7 = delta(d["Close"], 7)
    combined_sign = sign(gap7 + d7)
    cumret = 1 + ts_sum(d["returns"], min(250, len(d)))
    rank_cumret = ts_rank(cumret, 20)
    result = (-combined_sign) * (1 + rank_cumret)
    return _safe_series(result)

def wq20(d: pd.DataFrame) -> pd.Series:
    """
    WQ#20 (adapted): (-ts_rank(open - delay(high,1),5)) * ts_rank(open - delay(close,1),5)
                     * ts_rank(open - delay(low,1),5)
    Gap analysis: open relative to prior day's high/close/low
    """
    r1 = ts_rank(d["Open"] - delay(d["High"], 1), 5)
    r2 = ts_rank(d["Open"] - delay(d["Close"], 1), 5)
    r3 = ts_rank(d["Open"] - delay(d["Low"], 1), 5)
    return _safe_series(-r1 * r2 * r3)

def wq25(d: pd.DataFrame) -> pd.Series:
    """
    WQ#25 (adapted): ts_rank(((-1*returns) * adv20 * vwap) * (high - close), 5)
    Price bar height * volume * return momentum
    """
    bar_height = d["High"] - d["Close"]
    raw = (-d["returns"]) * d["adv20"] * d["vwap"] * bar_height
    return _safe_series(ts_rank(raw, 5))

def wq30(d: pd.DataFrame) -> pd.Series:
    """
    WQ#30 (adapted): (1 - ts_rank((sign(close-delay(close,1))+sign(delay(close,1)-delay(close,2))
                      +sign(delay(close,2)-delay(close,3))) * sum(volume,5) / sum(volume,20)))
    3-day sign streak with volume normalization
    """
    s1 = sign(delta(d["Close"], 1))
    s2 = sign(delay(d["Close"], 1) - delay(d["Close"], 2))
    s3 = sign(delay(d["Close"], 2) - delay(d["Close"], 3))
    streak = s1 + s2 + s3
    vol_ratio = ts_sum(d["volume"], 5) / ts_sum(d["volume"], 20).replace(0, 1.0)
    raw = streak * vol_ratio
    return _safe_series(1 - ts_rank(raw, 10))

def wq33(d: pd.DataFrame) -> pd.Series:
    """
    WQ#33 (adapted): ts_rank(-1 * ((1 - open/close)^1), 10)
    Open-to-close body direction momentum
    """
    body = -1 * (1 - d["Open"] / d["Close"].replace(0, 1.0))
    return _safe_series(ts_rank(body, 10))

def wq34(d: pd.DataFrame) -> pd.Series:
    """
    WQ#34 (adapted): ts_rank(1 - ts_rank(stddev(returns,2)/stddev(returns,5),5), 5)
                     + (1 - ts_rank(delta(close,1),5))
    Short vs medium volatility ratio + reversal
    """
    std2 = ts_std(d["returns"], 2).replace(0, 1e-9)
    std5 = ts_std(d["returns"], 5).replace(0, 1e-9)
    vol_ratio = std2 / std5
    r1 = ts_rank(1 - ts_rank(vol_ratio, 5), 5)
    r2 = 1 - ts_rank(delta(d["Close"], 1), 5)
    return _safe_series(r1 + r2)

def wq38(d: pd.DataFrame) -> pd.Series:
    """
    WQ#38 (adapted): (-ts_rank(close,10)) * (close / open)
    Downward ts_rank with close/open ratio
    """
    body_ratio = d["Close"] / d["Open"].replace(0, 1.0)
    return _safe_series(-ts_rank(d["Close"], 10) * body_ratio)

def wq40(d: pd.DataFrame) -> pd.Series:
    """
    WQ#40 (adapted): (-ts_rank(stddev(high,10),5)) * correlation(high, volume, 10)
    High volatility × high-volume correlation reversal
    """
    std_high = ts_std(d["High"], 10)
    corr_hv = ts_corr(d["High"], d["volume"], 10)
    return _safe_series(-ts_rank(std_high, 5) * corr_hv)

def wq41(d: pd.DataFrame) -> pd.Series:
    """
    WQ#41 (adapted): (high * low)^0.5 - vwap
    Geometric mean of high/low vs vwap — volatility-adjusted fair value gap
    """
    geo_mean = (d["High"] * d["Low"]).apply(math.sqrt)
    return _safe_series(geo_mean - d["vwap"])

def wq43(d: pd.DataFrame) -> pd.Series:
    """
    WQ#43 (adapted): ts_rank(volume / adv20, 20) * ts_rank(-delta(close,7), 8)
    Volume surge × medium-term price reversal
    """
    vol_ratio = d["volume"] / d["adv20"].replace(0, 1.0)
    r1 = ts_rank(vol_ratio, 20)
    r2 = ts_rank(-delta(d["Close"], 7), 8)
    return _safe_series(r1 * r2)

def wq44(d: pd.DataFrame) -> pd.Series:
    """
    WQ#44 (adapted): -correlation(high, ts_rank(volume,5), 5)
    High price × volume rank negative correlation
    """
    rv = ts_rank(d["volume"], 5)
    return _safe_series(-ts_corr(d["High"], rv, 5))

def wq53(d: pd.DataFrame) -> pd.Series:
    """
    WQ#53 (adapted): -delta((((close-low) - (high-close)) / (close-low+1e-9)), 9)
    Change in close position within bar
    """
    denom = (d["Close"] - d["Low"] + 1e-9)
    pos = ((d["Close"] - d["Low"]) - (d["High"] - d["Close"])) / denom
    return _safe_series(-delta(pos, 9))

def wq54(d: pd.DataFrame) -> pd.Series:
    """
    WQ#54 (adapted): -1 * ((low - close) * (open^5)) / ((low - high) * (close^5))
    Bar position asymmetry weighted by magnitude
    """
    num = (d["Low"] - d["Close"]) * (d["Open"] ** 2)
    denom = ((d["Low"] - d["High"]) * (d["Close"] ** 2)).replace(0, 1e-9)
    return _safe_series(-num / denom)

def wq55(d: pd.DataFrame) -> pd.Series:
    """
    WQ#55 (adapted): -correlation(ts_rank((close - ts_min(low,12)) / (ts_max(high,12) - ts_min(low,12)), 6),
                                   ts_rank(volume,6), 6)
    Stochastic-like position rank × volume rank negative correlation
    """
    lo12 = ts_min(d["Low"], 12)
    hi12 = ts_max(d["High"], 12)
    stoch = (d["Close"] - lo12) / (hi12 - lo12 + 1e-9)
    r1 = ts_rank(stoch, 6)
    r2 = ts_rank(d["volume"], 6)
    return _safe_series(-ts_corr(r1, r2, 6))

def wq1(d: pd.DataFrame) -> pd.Series:
    """
    WQ#1: rank(Ts_ArgMax(SignedPower(returns<0 ? stddev(returns,20) : close, 2), 5)) - 0.5
    Uses stddev on bad days, close on good days; argmax position as rank.
    """
    std20 = ts_std(d["returns"], 20).fillna(0.0)
    cond = d["returns"] < 0
    x = pd.Series(np.where(cond, std20, d["Close"]), index=d.index)
    sp = signed_power(x, 2.0)
    argmax5 = sp.rolling(5, min_periods=1).apply(lambda v: float(np.argmax(v)), raw=True)
    return _safe_series(ts_rank(argmax5, 20) - 0.5)


def wq4(d: pd.DataFrame) -> pd.Series:
    """WQ#4: -1 * Ts_Rank(rank(low), 9)  — low-price persistence reversal"""
    r_low = ts_rank(d["Low"], 20)
    return _safe_series(-ts_rank(r_low, 9))


def wq5(d: pd.DataFrame) -> pd.Series:
    """WQ#5: rank(open - sum(vwap,10)/10) * (-abs(rank(close - vwap)))"""
    r1 = ts_rank(d["Open"] - ts_mean(d["vwap"], 10), 20)
    r2 = ts_rank(d["Close"] - d["vwap"], 20)
    return _safe_series(r1 * (-r2.abs()))


def wq8(d: pd.DataFrame) -> pd.Series:
    """WQ#8: -rank((sum(open,5)*sum(returns,5)) - delay(sum(open,5)*sum(returns,5), 10))"""
    val = ts_sum(d["Open"], 5) * ts_sum(d["returns"], 5)
    return _safe_series(-ts_rank(val - delay(val, 10), 20))


def wq10(d: pd.DataFrame) -> pd.Series:
    """WQ#10: rank(ts_min/max delta filter — 4-day window version of #9)"""
    d1 = delta(d["Close"], 1)
    min4 = ts_min(d1, 4)
    max4 = ts_max(d1, 4)
    cond1 = (min4 > 0).astype(float)
    cond2 = (max4 < 0).astype(float)
    result = cond1 * d1 + (1 - cond1) * (cond2 * d1 + (1 - cond2) * (-d1))
    return _safe_series(ts_rank(result, 20))


def wq11(d: pd.DataFrame) -> pd.Series:
    """WQ#11: (rank(ts_max(vwap-close,3)) + rank(ts_min(vwap-close,3))) * rank(delta(vol,3))"""
    vc = d["vwap"] - d["Close"]
    r1 = ts_rank(ts_max(vc, 3), 20)
    r2 = ts_rank(ts_min(vc, 3), 20)
    r3 = ts_rank(delta(d["volume"], 3), 20)
    return _safe_series((r1 + r2) * r3)


def wq14(d: pd.DataFrame) -> pd.Series:
    """WQ#14: (-rank(delta(returns,3))) * correlation(open, volume, 10)"""
    r = -ts_rank(delta(d["returns"], 3), 20)
    c = ts_corr(d["Open"], d["volume"], 10)
    return _safe_series(r * c)


def wq15(d: pd.DataFrame) -> pd.Series:
    """WQ#15: -sum(rank(corr(rank(high), rank(vol), 3)), 3)"""
    rh = ts_rank(d["High"], 20)
    rv = ts_rank(d["volume"], 20)
    corr = ts_corr(rh, rv, 3)
    r_corr = ts_rank(corr, 20)
    return _safe_series(-ts_sum(r_corr, 3))


def wq17(d: pd.DataFrame) -> pd.Series:
    """WQ#17: (-rank(ts_rank(close,10))) * rank(delta(delta(close,1),1)) * rank(ts_rank(vol/adv20,5))"""
    r1 = ts_rank(ts_rank(d["Close"], 10), 20)
    r2 = ts_rank(delta(delta(d["Close"], 1), 1), 20)
    vol_ratio = d["volume"] / d["adv20"].replace(0, 1.0)
    r3 = ts_rank(ts_rank(vol_ratio, 5), 20)
    return _safe_series(-r1 * r2 * r3)


def wq18(d: pd.DataFrame) -> pd.Series:
    """WQ#18: -rank(stddev(abs(close-open),5) + (close-open) + corr(close,open,10))"""
    abs_co = (d["Close"] - d["Open"]).abs()
    std5 = ts_std(abs_co, 5)
    co = d["Close"] - d["Open"]
    corr = ts_corr(d["Close"], d["Open"], 10)
    return _safe_series(-ts_rank(std5 + co + corr, 20))


def wq21(d: pd.DataFrame) -> pd.Series:
    """WQ#21: 3-way conditional on SMA8 vs SMA2 vs volume"""
    sma8 = ts_mean(d["Close"], 8)
    std8 = ts_std(d["Close"], 8)
    sma2 = ts_mean(d["Close"], 2)
    vol_ratio = d["volume"] / d["adv20"].replace(0, 1.0)
    cond1 = (sma8 + std8) < sma2
    cond2 = sma2 < (sma8 - std8)
    cond3 = vol_ratio >= 1
    result = pd.Series(-1.0, index=d.index)
    result[cond1] = -1.0
    result[(~cond1) & cond2] = 1.0
    result[(~cond1) & (~cond2) & cond3] = 1.0
    return _safe_series(result)


def wq22(d: pd.DataFrame) -> pd.Series:
    """WQ#22: -delta(corr(high,vol,5),5) * rank(stddev(close,20))"""
    corr = ts_corr(d["High"], d["volume"], 5)
    r = ts_rank(ts_std(d["Close"], 20), 20)
    return _safe_series(-delta(corr, 5) * r)


def wq23(d: pd.DataFrame) -> pd.Series:
    """WQ#23: SMA20(high) < high → -delta(high,2) else 0"""
    sma20h = ts_mean(d["High"], 20)
    cond = (sma20h < d["High"]).astype(float)
    return _safe_series(cond * (-delta(d["High"], 2)))


def wq24(d: pd.DataFrame) -> pd.Series:
    """WQ#24: if 100-day slope ≤ 0.05 → -(close-min), else -delta(close,3)"""
    sma100 = ts_mean(d["Close"], 100)
    d_close_100 = delay(d["Close"], 100).replace(0, 1.0)
    change = delta(sma100, 100) / d_close_100
    tsmin100 = ts_min(d["Close"], 100)
    cond = (change <= 0.05)
    result = cond.astype(float) * (-(d["Close"] - tsmin100)) + \
             (~cond).astype(float) * (-delta(d["Close"], 3))
    return _safe_series(result)


def wq26(d: pd.DataFrame) -> pd.Series:
    """WQ#26: -ts_max(corr(ts_rank(vol,5), ts_rank(high,5), 5), 3)"""
    rv = ts_rank(d["volume"], 5)
    rh = ts_rank(d["High"], 5)
    corr = ts_corr(rv, rh, 5)
    return _safe_series(-ts_max(corr, 3))


def wq27(d: pd.DataFrame) -> pd.Series:
    """WQ#27: 0.5 < rank(sum(corr(rank(vol),rank(vwap),6),2)/2) → -1 : 1"""
    rv = ts_rank(d["volume"], 6)
    rvwap = ts_rank(d["vwap"], 6)
    corr = ts_corr(rv, rvwap, 6)
    rank_val = ts_rank(ts_mean(corr, 2), 20)
    result = (rank_val > 0.5).astype(float) * (-1) + (rank_val <= 0.5).astype(float) * 1
    return _safe_series(result)


def wq28(d: pd.DataFrame) -> pd.Series:
    """WQ#28: scale(corr(adv20,low,5) + (high+low)/2 - close)"""
    corr = ts_corr(d["adv20"], d["Low"], 5)
    val = corr + (d["High"] + d["Low"]) / 2 - d["Close"]
    return _safe_series(normalize_alpha(val))


def wq29(d: pd.DataFrame) -> pd.Series:
    """WQ#29: nested rank/log/product + ts_rank(delay(-returns,6),5)"""
    inner = -ts_rank(ts_rank(delta(d["Close"], 5), 20), 20)
    inner2 = ts_rank(-inner, 5)
    log_val = np.log(ts_sum(inner2.abs(), 2).replace(0, 1e-9))
    p1 = ts_rank(normalize_alpha(log_val), 5)
    p2 = ts_rank(delay(-d["returns"], 6), 5)
    return _safe_series(p1 + p2)


def wq31(d: pd.DataFrame) -> pd.Series:
    """WQ#31: rank(rank(rank(decay(-rank(rank(delta(close,10))),10)))) + rank(-delta(close,3)) + sign(scale(corr(adv20,low,12)))"""
    inner = -ts_rank(ts_rank(delta(d["Close"], 10), 20), 20)
    p1 = ts_rank(ts_rank(ts_rank(decay_linear(inner, 10), 20), 20), 20)
    p2 = ts_rank(-delta(d["Close"], 3), 20)
    corr_val = ts_corr(d["adv20"], d["Low"], 12)
    p3 = sign(normalize_alpha(corr_val))
    return _safe_series(p1 + p2 + p3)


def wq32(d: pd.DataFrame) -> pd.Series:
    """WQ#32: scale(sma7-close) + 20*scale(corr(vwap,delay(close,5),230))"""
    p1 = normalize_alpha(ts_mean(d["Close"], 7) - d["Close"])
    n = min(230, max(len(d) - 6, 2))
    corr = ts_corr(d["vwap"], delay(d["Close"], 5), n)
    p2 = 20 * normalize_alpha(corr)
    return _safe_series(p1 + p2)


def wq35(d: pd.DataFrame) -> pd.Series:
    """WQ#35: Ts_Rank(vol,32) * (1-Ts_Rank(close+high-low,16)) * (1-Ts_Rank(returns,32))"""
    r1 = ts_rank(d["volume"], 32)
    r2 = ts_rank(d["Close"] + d["High"] - d["Low"], 16)
    r3 = ts_rank(d["returns"], 32)
    return _safe_series(r1 * (1 - r2) * (1 - r3))


def wq36(d: pd.DataFrame) -> pd.Series:
    """WQ#36: 2.21*rank(corr(close-open,delay(vol,1),15)) + 0.7*rank(open-close) + 0.73*rank(Ts_Rank(delay(-returns,6),5)) + rank(|corr(vwap,adv20,6)|) + 0.6*rank((sma200-open)*(close-open))"""
    p1 = 2.21 * ts_rank(ts_corr(d["Close"] - d["Open"], delay(d["volume"], 1), 15), 20)
    p2 = 0.7  * ts_rank(d["Open"] - d["Close"], 20)
    p3 = 0.73 * ts_rank(ts_rank(delay(-d["returns"], 6), 5), 20)
    p4 = ts_rank(ts_corr(d["vwap"], d["adv20"], 6).abs(), 20)
    sma200 = ts_mean(d["Close"], min(200, len(d)))
    p5 = 0.6  * ts_rank((sma200 - d["Open"]) * (d["Close"] - d["Open"]), 20)
    return _safe_series(p1 + p2 + p3 + p4 + p5)


def wq37(d: pd.DataFrame) -> pd.Series:
    """WQ#37: rank(corr(delay(open-close,1), close, 200)) + rank(open-close)"""
    oc = d["Open"] - d["Close"]
    n = min(200, max(len(d) - 2, 2))
    p1 = ts_rank(ts_corr(delay(oc, 1), d["Close"], n), 20)
    p2 = ts_rank(oc, 20)
    return _safe_series(p1 + p2)


def wq39(d: pd.DataFrame) -> pd.Series:
    """WQ#39: -rank(delta(close,7) * (1-rank(decay(vol/adv20,9)))) * (1+rank(sum(returns,250)))"""
    vol_ratio = d["volume"] / d["adv20"].replace(0, 1.0)
    p1 = ts_rank(delta(d["Close"], 7) * (1 - ts_rank(decay_linear(vol_ratio, 9), 20)), 20)
    n = min(250, len(d) - 1)
    p2 = 1 + ts_rank(ts_sum(d["returns"], n), 20)
    return _safe_series(-p1 * p2)


def wq42(d: pd.DataFrame) -> pd.Series:
    """WQ#42: rank(vwap-close) / rank(vwap+close)"""
    r1 = ts_rank(d["vwap"] - d["Close"], 20)
    r2 = ts_rank(d["vwap"] + d["Close"], 20).replace(0, 1e-9)
    return _safe_series(r1 / r2)


def wq45(d: pd.DataFrame) -> pd.Series:
    """WQ#45: -rank(sum(delay(close,5),20)/20 * corr(close,vol,2)) * rank(corr(sum(close,5),sum(close,20),2))"""
    r1 = ts_rank(ts_mean(delay(d["Close"], 5), 20), 20)
    c1 = ts_corr(d["Close"], d["volume"], 2)
    s5  = ts_sum(d["Close"], 5)
    s20 = ts_sum(d["Close"], 20)
    r2 = ts_rank(ts_corr(s5, s20, 2), 20)
    return _safe_series(-r1 * c1 * r2)


def wq46(d: pd.DataFrame) -> pd.Series:
    """WQ#46: diff>0.25 → -1 ; diff<0 → 1 ; else -delta(close,1)"""
    diff = ((delay(d["Close"], 20) - delay(d["Close"], 10)) / 10) - \
           ((delay(d["Close"], 10) - d["Close"]) / 10)
    d1 = delta(d["Close"], 1)
    result = -d1.copy()
    result[diff > 0.25] = -1.0
    result[(diff <= 0.25) & (diff < 0)] = 1.0
    return _safe_series(result)


def wq47(d: pd.DataFrame) -> pd.Series:
    """WQ#47: (rank(1/close)*vol/adv20) * (high*rank(high-close)/sma5(high)) - rank(vwap-delay(vwap,5))"""
    r1 = ts_rank(1 / d["Close"].replace(0, 1.0), 20)
    vol_ratio = d["volume"] / d["adv20"].replace(0, 1.0)
    high_part = d["High"] * ts_rank(d["High"] - d["Close"], 20) / \
                (ts_mean(d["High"], 5) + 1e-9)
    r2 = ts_rank(d["vwap"] - delay(d["vwap"], 5), 20)
    return _safe_series(r1 * vol_ratio * high_part - r2)


def wq49(d: pd.DataFrame) -> pd.Series:
    """WQ#49: diff < -0.1 → 1 ; else -delta(close,1)"""
    diff = ((delay(d["Close"], 20) - delay(d["Close"], 10)) / 10) - \
           ((delay(d["Close"], 10) - d["Close"]) / 10)
    d1 = delta(d["Close"], 1)
    result = -d1.copy()
    result[diff < -0.1] = 1.0
    return _safe_series(result)


def wq50(d: pd.DataFrame) -> pd.Series:
    """WQ#50: -ts_max(rank(corr(rank(vol), rank(vwap), 5)), 5)"""
    rv = ts_rank(d["volume"], 20)
    rvwap = ts_rank(d["vwap"], 20)
    corr = ts_corr(rv, rvwap, 5)
    r = ts_rank(corr, 20)
    return _safe_series(-ts_max(r, 5))


def wq51(d: pd.DataFrame) -> pd.Series:
    """WQ#51: diff < -0.05 → 1 ; else -delta(close,1)"""
    diff = ((delay(d["Close"], 20) - delay(d["Close"], 10)) / 10) - \
           ((delay(d["Close"], 10) - d["Close"]) / 10)
    d1 = delta(d["Close"], 1)
    result = -d1.copy()
    result[diff < -0.05] = 1.0
    return _safe_series(result)


def wq52(d: pd.DataFrame) -> pd.Series:
    """WQ#52: (-ts_min(low,5)+delay(ts_min(low,5),5)) * rank((ΣRet240-ΣRet20)/220) * ts_rank(vol,5)"""
    tmin5 = ts_min(d["Low"], 5)
    p1 = -tmin5 + delay(tmin5, 5)
    n240 = min(240, len(d) - 1)
    r1 = ts_rank((ts_sum(d["returns"], n240) - ts_sum(d["returns"], 20)) / 220, 20)
    r2 = ts_rank(d["volume"], 5)
    return _safe_series(p1 * r1 * r2)


def wq57(d: pd.DataFrame) -> pd.Series:
    """WQ#57: -(close-vwap) / decay_linear(rank(ts_argmax(close,30)),2)"""
    argmax30 = d["Close"].rolling(30, min_periods=1).apply(
        lambda x: float(np.argmax(x)), raw=True)
    r_argmax = ts_rank(argmax30, 20)
    denom = decay_linear(r_argmax, 2).replace(0, 1e-9)
    return _safe_series(-(d["Close"] - d["vwap"]) / denom)


def wq60(d: pd.DataFrame) -> pd.Series:
    """WQ#60: -(2*scale(rank(((close-low)-(high-close))/(high-low)*vol)) - scale(rank(ts_argmax(close,10))))"""
    hl = (d["High"] - d["Low"]).replace(0, 1e-9)
    body = ((d["Close"] - d["Low"]) - (d["High"] - d["Close"])) / hl * d["volume"]
    r1 = 2 * normalize_alpha(ts_rank(body, 20))
    argmax10 = d["Close"].rolling(10, min_periods=1).apply(
        lambda x: float(np.argmax(x)), raw=True)
    r2 = normalize_alpha(ts_rank(argmax10, 20))
    return _safe_series(-(r1 - r2))


def wq61(d: pd.DataFrame) -> pd.Series:
    """WQ#61: rank(vwap-ts_min(vwap,16)) < rank(corr(vwap,adv180,18))"""
    adv180 = ts_mean(d["volume"], 180)
    r1 = ts_rank(d["vwap"] - ts_min(d["vwap"], 16), 20)
    r2 = ts_rank(ts_corr(d["vwap"], adv180, 18), 20)
    return _safe_series((r1 < r2).astype(float) * 2 - 1)


def wq62(d: pd.DataFrame) -> pd.Series:
    """WQ#62: (rank(corr(vwap,sum(adv20,22),10)) < rank(2*rank(open) < rank(hl/2)+rank(high))) * -1"""
    adv20_sum = ts_sum(d["adv20"], 22)
    r1 = ts_rank(ts_corr(d["vwap"], adv20_sum, 10), 20)
    cond = (2 * ts_rank(d["Open"], 20)) < \
           (ts_rank((d["High"] + d["Low"]) / 2, 20) + ts_rank(d["High"], 20))
    r2 = ts_rank(cond.astype(float), 20)
    return _safe_series(-((r1 < r2).astype(float) * 2 - 1))


def wq65(d: pd.DataFrame) -> pd.Series:
    """WQ#65: rank(corr(w*open+(1-w)*vwap, sum(adv60,9), 6)) < rank(open-ts_min(open,14)) — reversed signal"""
    adv60 = ts_mean(d["volume"], 60)
    x = 0.00817205 * d["Open"] + (1 - 0.00817205) * d["vwap"]
    r1 = ts_rank(ts_corr(x, ts_sum(adv60, 9), 6), 20)
    r2 = ts_rank(d["Open"] - ts_min(d["Open"], 14), 20)
    return _safe_series(-((r1 < r2).astype(float) * 2 - 1))


def wq66(d: pd.DataFrame) -> pd.Series:
    """WQ#66: -(rank(decay(delta(vwap,3),7)) + Ts_Rank(decay((low-vwap)/(open-hl/2),11),7))"""
    p1 = ts_rank(decay_linear(delta(d["vwap"], 3), 7), 20)
    denom = (d["Open"] - (d["High"] + d["Low"]) / 2).replace(0, 1e-9)
    p2 = ts_rank(decay_linear((d["Low"] - d["vwap"]) / denom, 11), 7)
    return _safe_series(-(p1 + p2))


def wq71(d: pd.DataFrame) -> pd.Series:
    """WQ#71: max(Ts_Rank(decay(corr(ts_rank(close,3),ts_rank(adv180,12),18),4),16), Ts_Rank(decay(rank((low+open-2*vwap)^2),16),4))"""
    adv180 = ts_mean(d["volume"], 180)
    corr1 = ts_corr(ts_rank(d["Close"], 3), ts_rank(adv180, 12), 18)
    p1 = ts_rank(decay_linear(corr1, 4), 16)
    x2 = signed_power(ts_rank(d["Low"] + d["Open"] - 2 * d["vwap"], 20), 2)
    p2 = ts_rank(decay_linear(x2, 16), 4)
    return _safe_series(pd.concat([p1, p2], axis=1).max(axis=1))


def wq72(d: pd.DataFrame) -> pd.Series:
    """WQ#72: rank(decay(corr(hl/2,adv40,9),10)) / rank(decay(corr(ts_rank(vwap,4),ts_rank(vol,19),7),3))"""
    adv40 = ts_mean(d["volume"], 40)
    num = ts_rank(decay_linear(ts_corr((d["High"] + d["Low"]) / 2, adv40, 9), 10), 20)
    denom = ts_rank(decay_linear(ts_corr(ts_rank(d["vwap"], 4), ts_rank(d["volume"], 19), 7), 3), 20)
    return _safe_series(num / (denom.replace(0, 1e-9)))


def wq73(d: pd.DataFrame) -> pd.Series:
    """WQ#73: -max(rank(decay(delta(vwap,5),3)), Ts_Rank(decay(-delta(w*open+(1-w)*low,2)/x,3),17))"""
    p1 = ts_rank(decay_linear(delta(d["vwap"], 5), 3), 20)
    x = 0.147155 * d["Open"] + (1 - 0.147155) * d["Low"]
    dv = -delta(x, 2) / x.replace(0, 1e-9)
    p2 = ts_rank(decay_linear(dv, 3), 17)
    return _safe_series(-pd.concat([p1, p2], axis=1).max(axis=1))


def wq74(d: pd.DataFrame) -> pd.Series:
    """WQ#74: rank(corr(close,sum(adv30,37),15)) < rank(corr(rank(w*high+(1-w)*vwap),rank(vol),11)) → -1"""
    adv30 = ts_mean(d["volume"], 30)
    r1 = ts_rank(ts_corr(d["Close"], ts_sum(adv30, 37), 15), 20)
    x = 0.0261661 * d["High"] + (1 - 0.0261661) * d["vwap"]
    r2 = ts_rank(ts_corr(ts_rank(x, 20), ts_rank(d["volume"], 20), 11), 20)
    return _safe_series(-((r1 < r2).astype(float) * 2 - 1))


def wq75(d: pd.DataFrame) -> pd.Series:
    """WQ#75: rank(corr(vwap,vol,4)) < rank(corr(rank(low),rank(adv50),12))"""
    adv50 = ts_mean(d["volume"], 50)
    r1 = ts_rank(ts_corr(d["vwap"], d["volume"], 4), 20)
    r2 = ts_rank(ts_corr(ts_rank(d["Low"], 20), ts_rank(adv50, 20), 12), 20)
    return _safe_series((r1 < r2).astype(float) * 2 - 1)


def wq77(d: pd.DataFrame) -> pd.Series:
    """WQ#77: min(rank(decay((hl/2+high)-(vwap+high),20)), rank(decay(corr(hl/2,adv40,3),6)))"""
    adv40 = ts_mean(d["volume"], 40)
    hl2 = (d["High"] + d["Low"]) / 2
    p1 = ts_rank(decay_linear(hl2 - d["vwap"], 20), 20)
    p2 = ts_rank(decay_linear(ts_corr(hl2, adv40, 3), 6), 20)
    return _safe_series(pd.concat([p1, p2], axis=1).min(axis=1))


def wq78(d: pd.DataFrame) -> pd.Series:
    """WQ#78: rank(corr(sum(w*low+(1-w)*vwap,20),sum(adv40,20),7)) ^ rank(corr(rank(vwap),rank(vol),6))"""
    adv40 = ts_mean(d["volume"], 40)
    x = 0.352233 * d["Low"] + (1 - 0.352233) * d["vwap"]
    r1 = ts_rank(ts_corr(ts_sum(x, 20), ts_sum(adv40, 20), 7), 20)
    r2 = ts_rank(ts_corr(ts_rank(d["vwap"], 20), ts_rank(d["volume"], 20), 6), 20)
    return _safe_series(signed_power(r1, r2))


def wq83(d: pd.DataFrame) -> pd.Series:
    """WQ#83: (rank(delay(HL/sma5close,2)) * rank(rank(vol))) / (HL/sma5close / (vwap-close))"""
    hl = (d["High"] - d["Low"]) / (ts_mean(d["Close"], 5) + 1e-9)
    r1 = ts_rank(delay(hl, 2), 20)
    r2 = ts_rank(ts_rank(d["volume"], 20), 20)
    denom = (hl / (d["vwap"] - d["Close"]).replace(0, 1e-9)).replace(0, 1e-9)
    return _safe_series(r1 * r2 / denom)


def wq84(d: pd.DataFrame) -> pd.Series:
    """WQ#84: SignedPower(Ts_Rank(vwap-ts_max(vwap,15),21), delta(close,5))"""
    x = d["vwap"] - ts_max(d["vwap"], 15)
    r = ts_rank(x, 21)
    d5 = delta(d["Close"], 5)
    return _safe_series(signed_power(r, d5))


def wq85(d: pd.DataFrame) -> pd.Series:
    """WQ#85: rank(corr(w*high+(1-w)*close,adv30,10)) ^ rank(corr(ts_rank(hl/2,4),ts_rank(vol,10),7))"""
    adv30 = ts_mean(d["volume"], 30)
    x = 0.876703 * d["High"] + (1 - 0.876703) * d["Close"]
    r1 = ts_rank(ts_corr(x, adv30, 10), 20)
    r2 = ts_rank(ts_corr(ts_rank((d["High"] + d["Low"]) / 2, 4), ts_rank(d["volume"], 10), 7), 20)
    return _safe_series(signed_power(r1, r2))


def wq86(d: pd.DataFrame) -> pd.Series:
    """WQ#86: Ts_Rank(corr(close,sum(adv20,15),6),21) < rank((open+close)-(vwap+open)) → -1"""
    adv20_sum = ts_sum(d["adv20"], 15)
    r1 = ts_rank(ts_corr(d["Close"], adv20_sum, 6), 21)
    r2 = ts_rank(d["Close"] - d["vwap"], 20)
    return _safe_series(-((r1 < r2).astype(float) * 2 - 1))


def wq88(d: pd.DataFrame) -> pd.Series:
    """WQ#88: min(rank(decay((rank(open)+rank(low))-(rank(high)+rank(close)),8)), Ts_Rank(decay(corr(ts_rank(close,8),ts_rank(adv60,21),8),7),3))"""
    adv60 = ts_mean(d["volume"], 60)
    x1 = (ts_rank(d["Open"], 20) + ts_rank(d["Low"], 20) -
           ts_rank(d["High"], 20) - ts_rank(d["Close"], 20))
    p1 = ts_rank(decay_linear(x1, 8), 20)
    corr2 = ts_corr(ts_rank(d["Close"], 8), ts_rank(adv60, 21), 8)
    p2 = ts_rank(decay_linear(corr2, 7), 3)
    return _safe_series(pd.concat([p1, p2], axis=1).min(axis=1))


def wq89(d: pd.DataFrame) -> pd.Series:
    """WQ#89: Ts_Rank(decay(corr(low,adv10,7),6),4) - Ts_Rank(decay(delta(vwap,3),10),15)"""
    adv10 = ts_mean(d["volume"], 10)
    p1 = ts_rank(decay_linear(ts_corr(d["Low"], adv10, 7), 6), 4)
    p2 = ts_rank(decay_linear(delta(d["vwap"], 3), 10), 15)
    return _safe_series(p1 - p2)


def wq92(d: pd.DataFrame) -> pd.Series:
    """WQ#92: min(Ts_Rank(decay((hl/2+close)<(low+open),15),19), Ts_Rank(decay(corr(rank(low),rank(adv30),8),7),7))"""
    adv30 = ts_mean(d["volume"], 30)
    cond = (((d["High"] + d["Low"]) / 2 + d["Close"]) < (d["Low"] + d["Open"])).astype(float)
    p1 = ts_rank(decay_linear(cond, 15), 19)
    corr2 = ts_corr(ts_rank(d["Low"], 20), ts_rank(adv30, 20), 8)
    p2 = ts_rank(decay_linear(corr2, 7), 7)
    return _safe_series(pd.concat([p1, p2], axis=1).min(axis=1))


def wq94(d: pd.DataFrame) -> pd.Series:
    """WQ#94: rank(vwap-ts_min(vwap,12)) ^ Ts_Rank(corr(ts_rank(vwap,20),ts_rank(adv60,4),18),3) * -1"""
    adv60 = ts_mean(d["volume"], 60)
    r1 = ts_rank(d["vwap"] - ts_min(d["vwap"], 12), 20)
    corr = ts_corr(ts_rank(d["vwap"], 20), ts_rank(adv60, 4), 18)
    r2 = ts_rank(corr, 3)
    return _safe_series(-signed_power(r1, r2))


def wq95(d: pd.DataFrame) -> pd.Series:
    """WQ#95: rank(open-ts_min(open,12)) < Ts_Rank(rank(corr(sum(hl/2,19),sum(adv40,19),13))^5, 12)"""
    adv40 = ts_mean(d["volume"], 40)
    hl2 = (d["High"] + d["Low"]) / 2
    r1 = ts_rank(d["Open"] - ts_min(d["Open"], 12), 20)
    corr = ts_corr(ts_sum(hl2, 19), ts_sum(adv40, 19), 13)
    r2 = ts_rank(signed_power(ts_rank(corr, 20), 5), 12)
    return _safe_series((r1 < r2).astype(float) * 2 - 1)


def wq96(d: pd.DataFrame) -> pd.Series:
    """WQ#96: -max(Ts_Rank(decay(corr(rank(vwap),rank(vol),4),4),8), Ts_Rank(decay(ts_argmax(corr(ts_rank(close,8),ts_rank(adv60,4),4),13),14),13))"""
    adv60 = ts_mean(d["volume"], 60)
    corr1 = ts_corr(ts_rank(d["vwap"], 20), ts_rank(d["volume"], 20), 4)
    p1 = ts_rank(decay_linear(corr1, 4), 8)
    corr2 = ts_corr(ts_rank(d["Close"], 8), ts_rank(adv60, 4), 4)
    argmax2 = corr2.rolling(13, min_periods=1).apply(
        lambda x: float(np.argmax(x)), raw=True)
    p2 = ts_rank(decay_linear(argmax2, 14), 13)
    return _safe_series(-pd.concat([p1, p2], axis=1).max(axis=1))


def wq98(d: pd.DataFrame) -> pd.Series:
    """WQ#98: rank(decay(corr(vwap,sum(adv5,27),5),7)) - rank(decay(ts_rank(ts_argmin(corr(rank(open),rank(adv15),21),9),7),8))"""
    adv5  = ts_mean(d["volume"], 5)
    adv15 = ts_mean(d["volume"], 15)
    corr1 = ts_corr(d["vwap"], ts_sum(adv5, 27), 5)
    p1 = ts_rank(decay_linear(corr1, 7), 20)
    corr2 = ts_corr(ts_rank(d["Open"], 20), ts_rank(adv15, 20), 21)
    argmin = corr2.rolling(9, min_periods=1).apply(
        lambda x: float(np.argmin(x)), raw=True)
    p2 = ts_rank(decay_linear(ts_rank(argmin, 7), 8), 20)
    return _safe_series(p1 - p2)


def wq99(d: pd.DataFrame) -> pd.Series:
    """WQ#99: rank(corr(sum(hl/2,20),sum(adv60,20),9)) < rank(corr(low,vol,6)) → -1"""
    adv60 = ts_mean(d["volume"], 60)
    hl2 = (d["High"] + d["Low"]) / 2
    r1 = ts_rank(ts_corr(ts_sum(hl2, 20), ts_sum(adv60, 20), 9), 20)
    r2 = ts_rank(ts_corr(d["Low"], d["volume"], 6), 20)
    return _safe_series(-((r1 < r2).astype(float) * 2 - 1))


def wq101(d: pd.DataFrame) -> pd.Series:
    """WQ#101: (close - open) / ((high - low) + 0.001)  — intraday body ratio"""
    return _safe_series((d["Close"] - d["Open"]) / (d["High"] - d["Low"] + 0.001))


# ─────────────────────────────────────────────────────────────────────────────
# 5. Alpha registry
# ─────────────────────────────────────────────────────────────────────────────

ALPHA_REGISTRY = {
    # ── Current 5 ──────────────────────────────────────────────────────────
    "CURRENT_1_FDM":  (alpha_fdm,    "Flow-Driven Momentum (hiện tại)"),
    "CURRENT_2_SFA":  (alpha_sfa,    "Sentiment-Flow MACD Proxy (hiện tại)"),
    "CURRENT_3_LVR":  (alpha_lvr,    "Liquidity Void Reversion (hiện tại)"),
    "CURRENT_4_BFE":  (alpha_bfe,    "Bollinger Squeeze & Flow (hiện tại)"),
    "CURRENT_5_OFE":  (alpha_ofe,    "Order Flow Exhaustion (hiện tại)"),
    # ── WQ-101 Full Set (adapted for single-stock OHLCV) ───────────────────
    "WQ01_ArgMaxRank":     (wq1,   "WQ#1 rank(ts_argmax(signedpower(ret<0?std:close,2),5))-0.5"),
    "WQ02_PriceVolDiv":    (wq2,   "WQ#2 Price/Volume Divergence (–corr vol_delta vs body)"),
    "WQ03_OpenVolCorr":    (wq3,   "WQ#3 –corr(rank_open, rank_vol, 10)"),
    "WQ04_LowRankRev":     (wq4,   "WQ#4 –Ts_Rank(rank(low), 9)"),
    "WQ05_OpenVwapBody":   (wq5,   "WQ#5 rank(open-sma_vwap)*(-abs(rank(close-vwap)))"),
    "WQ06_OpenVol":        (wq6,   "WQ#6 –corr(open, volume, 10)"),
    "WQ07_VolSurgeMom":    (wq7,   "WQ#7 Volume Surge × Momentum Reversal"),
    "WQ08_OpenRetMom":     (wq8,   "WQ#8 –rank(sum(open,5)*sum(ret,5) – delay(…,10))"),
    "WQ09_MomContRev":     (wq9,   "WQ#9 Momentum Continuation vs Reversal (ts_min/max filter)"),
    "WQ10_MomRank4":       (wq10,  "WQ#10 rank(ts_min/max delta filter — 4-day window)"),
    "WQ11_VwapCloseVol":   (wq11,  "WQ#11 (rank(ts_max(vwap-close,3))+rank(ts_min(…,3)))*rank(Δvol,3)"),
    "WQ12_VolPriceSign":   (wq12,  "WQ#12 sign(Δvol) × –Δclose"),
    "WQ13_CovReverse":     (wq13,  "WQ#13 –ts_rank(cov(rank_close, rank_vol))"),
    "WQ14_RetDeltaCorr":   (wq14,  "WQ#14 –rank(delta(returns,3)) * corr(open,vol,10)"),
    "WQ15_HighVolSumCorr": (wq15,  "WQ#15 –sum(rank(corr(rank(high),rank(vol),3)),3)"),
    "WQ16_HighVolCov":     (wq16,  "WQ#16 –ts_rank(cov(rank_high, rank_vol))"),
    "WQ17_TripleRank":     (wq17,  "WQ#17 –rank(ts_rank(close,10))*rank(Δ²close)*rank(ts_rank(vol/adv20,5))"),
    "WQ18_StdBodyCorr":    (wq18,  "WQ#18 –rank(std(|close-open|,5)+(close-open)+corr(close,open,10))"),
    "WQ19_LongShortMom":   (wq19,  "WQ#19 Long-term trend × short-term reversal"),
    "WQ20_GapAnalysis":    (wq20,  "WQ#20 Open gap vs prior High/Close/Low"),
    "WQ21_SmaCondition":   (wq21,  "WQ#21 3-way SMA8 vs SMA2 vs volume condition"),
    "WQ22_CorrDeltaStd":   (wq22,  "WQ#22 –delta(corr(high,vol,5),5)*rank(std(close,20))"),
    "WQ23_HighSmaBreak":   (wq23,  "WQ#23 SMA20(high)<high → –delta(high,2)"),
    "WQ24_TrendSlope":     (wq24,  "WQ#24 100-day slope ≤0.05 → -(close-min100) else –delta(close,3)"),
    "WQ25_RetVolHeight":   (wq25,  "WQ#25 return × volume × bar-height momentum"),
    "WQ26_TsMaxCorrVol":   (wq26,  "WQ#26 –ts_max(corr(ts_rank(vol,5),ts_rank(high,5),5),3)"),
    "WQ27_CorrRankCond":   (wq27,  "WQ#27 conditional on rank(sum(corr,2)/2) vs 0.5"),
    "WQ28_CorrLowClose":   (wq28,  "WQ#28 scale(corr(adv20,low,5)+(high+low)/2-close)"),
    "WQ29_NestedRankLog":  (wq29,  "WQ#29 nested rank/log + ts_rank(delay(-ret,6),5)"),
    "WQ30_SignStreakVol":   (wq30,  "WQ#30 3-day sign streak with volume ratio"),
    "WQ31_DecayDeltaCorr": (wq31,  "WQ#31 rank(rank(rank(decay(-rank(rank(Δclose10)),10))))+rank(-Δclose3)+sign(scale(corr))"),
    "WQ32_ScaleCorr230":   (wq32,  "WQ#32 scale(sma7-close)+20*scale(corr(vwap,delay(close,5),230))"),
    "WQ33_BodyDirection":  (wq33,  "WQ#33 Open-to-close body direction rank"),
    "WQ34_VolRatioRev":    (wq34,  "WQ#34 Volatility ratio + reversal"),
    "WQ35_TripleTsRank":   (wq35,  "WQ#35 Ts_Rank(vol,32)*(1-Ts_Rank(c+h-l,16))*(1-Ts_Rank(ret,32))"),
    "WQ36_WeightedCombo":  (wq36,  "WQ#36 2.21*corr+0.7*oc+0.73*delay_rank+corr_abs+0.6*sma_body"),
    "WQ37_DelayOcCorr":    (wq37,  "WQ#37 rank(corr(delay(open-close,1),close,200))+rank(open-close)"),
    "WQ38_TsRankBody":     (wq38,  "WQ#38 –ts_rank(close) × close/open ratio"),
    "WQ39_DeltaDecayRet":  (wq39,  "WQ#39 –rank(Δclose7*(1-rank(decay(vol/adv20,9))))*(1+rank(ΣRet250))"),
    "WQ40_HighVolatVol":   (wq40,  "WQ#40 –rank(std_high) × corr(high,vol)"),
    "WQ41_GeoMeanVwap":    (wq41,  "WQ#41 sqrt(H×L) – vwap (fair-value gap)"),
    "WQ42_VwapCloseRatio": (wq42,  "WQ#42 rank(vwap-close)/rank(vwap+close)"),
    "WQ43_VolSurgeRev7":   (wq43,  "WQ#43 Volume surge × 7-day price reversal"),
    "WQ44_HighVolCorr":    (wq44,  "WQ#44 –corr(high, rank_vol, 5)"),
    "WQ45_DelayCloseCorr": (wq45,  "WQ#45 –rank(sum(delay(close,5),20)/20*corr(close,vol,2))*rank(corr(s5,s20,2))"),
    "WQ46_SlopeCond025":   (wq46,  "WQ#46 10-day slope diff > 0.25 → –1; < 0 → 1; else –Δclose"),
    "WQ47_CloseMomentum":  (wq47,  "WQ#47 rank(1/close)*vol/adv20 * high*rank(h-c)/sma5h – rank(Δvwap5)"),
    "WQ49_SlopeCond01":    (wq49,  "WQ#49 slope diff < –0.1 → 1; else –Δclose"),
    "WQ50_TsMaxCorrRank":  (wq50,  "WQ#50 –ts_max(rank(corr(rank(vol),rank(vwap),5)),5)"),
    "WQ51_SlopeCond005":   (wq51,  "WQ#51 slope diff < –0.05 → 1; else –Δclose"),
    "WQ52_TsMinRetVol":    (wq52,  "WQ#52 (–ts_min(low,5)+delay)*rank(ΣRet_diff/220)*ts_rank(vol,5)"),
    "WQ53_BarPosChange":   (wq53,  "WQ#53 –Δ(close position in bar, 9-day)"),
    "WQ54_BarAsymm":       (wq54,  "WQ#54 Bar asymmetry weighted by magnitude"),
    "WQ55_StochVolCorr":   (wq55,  "WQ#55 –corr(stochastic rank, vol rank)"),
    "WQ57_VwapArgmax":     (wq57,  "WQ#57 –(close-vwap)/decay(rank(ts_argmax(close,30)),2)"),
    "WQ60_BodyScaleArgmax":(wq60,  "WQ#60 –(2*scale(rank(body_vol))-scale(rank(ts_argmax(close,10))))"),
    "WQ61_VwapMinCorr":    (wq61,  "WQ#61 rank(vwap-ts_min(vwap,16)) < rank(corr(vwap,adv180,18))"),
    "WQ62_CorrOpenRank":   (wq62,  "WQ#62 rank(corr(vwap,sum(adv20,22),10)) < rank(open rank vs hl rank)"),
    "WQ65_WeightedCorrMin":(wq65,  "WQ#65 rank(corr(w*open+(1-w)*vwap,adv60_sum,6)) < rank(open-ts_min(open,14))"),
    "WQ66_DecayVwapLow":   (wq66,  "WQ#66 –(rank(decay(Δvwap,7))+Ts_Rank(decay((low-vwap)/body,11),7))"),
    "WQ71_MaxTsRankDecay": (wq71,  "WQ#71 max(Ts_Rank(decay(corr(ts_rank(close,3),ts_rank(adv180,12),18),4),16), Ts_Rank(decay(rank((low+open-2*vwap)^2),16),4))"),
    "WQ72_DecayRatio":     (wq72,  "WQ#72 rank(decay(corr(hl/2,adv40,9),10))/rank(decay(corr(ts_rank(vwap,4),ts_rank(vol,19),7),3))"),
    "WQ73_MaxDecayDelta":  (wq73,  "WQ#73 –max(rank(decay(Δvwap5,3)), Ts_Rank(decay(–Δ(w*open+(1-w)*low)/x,3),17))"),
    "WQ74_CorrCloseAdv30": (wq74,  "WQ#74 rank(corr(close,sum(adv30,37),15)) < rank(corr(rank(w*high+vwap),rank(vol),11)) → –1"),
    "WQ75_CorrVwapAdv50":  (wq75,  "WQ#75 rank(corr(vwap,vol,4)) < rank(corr(rank(low),rank(adv50),12))"),
    "WQ77_MinDecayHL":     (wq77,  "WQ#77 min(rank(decay(hl/2–vwap,20)),rank(decay(corr(hl/2,adv40,3),6)))"),
    "WQ78_CorrRankPow":    (wq78,  "WQ#78 rank(corr(sum(w*low+(1-w)*vwap,20),sum(adv40,20),7))^rank(corr(rank(vwap),rank(vol),6))"),
    "WQ83_HLRatioVol":     (wq83,  "WQ#83 rank(delay(HL/sma5close,2))*rank(rank(vol))/(HL/sma5close/(vwap-close))"),
    "WQ84_SignedPowerArgmax":(wq84,"WQ#84 SignedPower(Ts_Rank(vwap–ts_max(vwap,15),21), delta(close,5))"),
    "WQ85_CorrPow":        (wq85,  "WQ#85 rank(corr(w*high+(1-w)*close,adv30,10))^rank(corr(ts_rank(hl/2,4),ts_rank(vol,10),7))"),
    "WQ86_CorrCloseAdv20": (wq86,  "WQ#86 Ts_Rank(corr(close,sum(adv20,15),6),21) < rank(close-vwap) → –1"),
    "WQ88_MinDecayOpen":   (wq88,  "WQ#88 min(rank(decay((rank(open)+rank(low))–(rank(high)+rank(close)),8)), Ts_Rank(decay(corr(ts_rank(close,8),ts_rank(adv60,21),8),7),3))"),
    "WQ89_DecayLowVwap":   (wq89,  "WQ#89 Ts_Rank(decay(corr(low,adv10,7),6),4) – Ts_Rank(decay(delta(vwap,3),10),15)"),
    "WQ92_MinCondDecay":   (wq92,  "WQ#92 min(Ts_Rank(decay(hl/2+close<low+open,15),19), Ts_Rank(decay(corr(rank(low),rank(adv30),8),7),7))"),
    "WQ94_VwapMinPow":     (wq94,  "WQ#94 –rank(vwap–ts_min(vwap,12))^Ts_Rank(corr(ts_rank(vwap,20),ts_rank(adv60,4),18),3)"),
    "WQ95_OpenMinCorr":    (wq95,  "WQ#95 rank(open–ts_min(open,12)) < Ts_Rank(rank(corr(sum(hl/2,19),sum(adv40,19),13))^5,12)"),
    "WQ96_MaxDecayCorr":   (wq96,  "WQ#96 –max(Ts_Rank(decay(corr(rank(vwap),rank(vol),4),4),8), Ts_Rank(decay(ts_argmax(corr(ts_rank(close,8),ts_rank(adv60,4),4),13),14),13))"),
    "WQ98_DecayDiff":      (wq98,  "WQ#98 rank(decay(corr(vwap,sum(adv5,27),5),7)) – rank(decay(ts_rank(ts_argmin(corr(rank(open),rank(adv15),21),9),7),8))"),
    "WQ99_CorrHLAdv60":    (wq99,  "WQ#99 rank(corr(sum(hl/2,20),sum(adv60,20),9)) < rank(corr(low,vol,6)) → –1"),
    "WQ101_IntradayBody":  (wq101, "WQ#101 (close–open)/((high–low)+0.001) — intraday body ratio"),
}

# ─────────────────────────────────────────────────────────────────────────────
# 6. Backtesting engine
# ─────────────────────────────────────────────────────────────────────────────

def compute_metrics(alpha_values: np.ndarray, forward_returns: np.ndarray,
                    lookahead: int = 3) -> dict:
    """
    Compute performance metrics for one alpha.
    alpha_values : signal at time t (clipped to [-1,1])
    forward_returns: actual return over next `lookahead` periods starting at t+1
    """
    mask = np.isfinite(alpha_values) & np.isfinite(forward_returns)
    if mask.sum() < 20:
        return {"ic": 0.0, "accuracy": 0.5, "sharpe": 0.0, "n": 0}

    av = alpha_values[mask]
    fr = forward_returns[mask]

    # Information Coefficient (Spearman rank correlation)
    from scipy.stats import spearmanr
    ic, _ = spearmanr(av, fr)
    ic = 0.0 if math.isnan(ic) else ic

    # Flip the signal for performance evaluation if IC < 0
    flip_signal = ic < 0
    av_metric = -av if flip_signal else av

    # Directional accuracy: sign(signal) matches sign(return)
    valid = (np.abs(av_metric) > 0.05)  # only predict when signal strong enough
    if valid.sum() < 10:
        accuracy = 0.5
    else:
        correct = np.sign(av_metric[valid]) == np.sign(fr[valid])
        accuracy = correct.mean()

    # Realistic PnL calculations
    tx_cost = 0.0025
    slippage = 0.001
    
    # Gross returns from signal
    gross_ret = np.sign(av_metric) * fr
    
    # Subtract costs where trades occur (whenever signal changes or we just assume a trade per period)
    # For a simple alpha ranking, let's assume we pay spread/cost every period we are in a trade
    # A more complex would be `np.abs(np.diff(np.sign(av_metric))) > 0`
    net_ret = gross_ret - (tx_cost + slippage) * np.abs(np.sign(av_metric))
    
    strategy_ret = net_ret
    mean_ret = strategy_ret.mean()
    std_ret = strategy_ret.std()
    sharpe = (mean_ret / (std_ret + 1e-9)) * math.sqrt(252 / lookahead)
    
    # Sortino
    downside = strategy_ret[strategy_ret < 0]
    std_down = downside.std() if len(downside) > 0 else 0.0
    sortino = (mean_ret / (std_down + 1e-9)) * math.sqrt(252 / lookahead)
    
    # Max Drawdown
    cum = np.cumsum(strategy_ret)
    max_so_far = np.maximum.accumulate(cum)
    dd = max_so_far - cum
    mdd = np.max(dd) if len(dd) > 0 else 0.0

    # Hit Rate and Average Trade
    trades = strategy_ret[np.abs(np.sign(av_metric)) > 0]
    hit_rate = (trades > 0).mean() * 100 if len(trades) > 0 else 0.0
    avg_trade = trades.mean() if len(trades) > 0 else 0.0

    # Long-only accuracy (important for VN market — limited shorting)
    long_mask = av_metric > 0.05
    if long_mask.sum() >= 5:
        long_acc = (fr[long_mask] > 0).mean()
    else:
        long_acc = 0.5
        
    return {
        "ic":        round(float(ic), 4),
        "accuracy":  round(float(accuracy), 4),
        "long_acc":  round(float(long_acc), 4),
        "sharpe":    round(float(sharpe), 3),
        "sortino":   round(float(sortino), 3),
        "mdd":       round(float(mdd * 100), 2),
        "hit_rate":  round(float(hit_rate), 2),
        "avg_trade": round(float(avg_trade * 100), 4),
        "n":         int(mask.sum()),
        "mean_ret":  round(float(mean_ret), 5),
    }


def run_backtest(df: pd.DataFrame, lookahead: int = 3,
                 min_history: int = 60, norm_method: str = "zscore_tanh") -> pd.DataFrame:
    """
    Compute all alphas on the full DataFrame, then evaluate
    predictive power against `lookahead`-period forward returns.
    """
    if len(df) < min_history + lookahead + 20:
        raise ValueError(f"Cần ít nhất {min_history + lookahead + 20} nến, hiện có {len(df)}")

    print(f"\n[AlphaCompare] Tính features trên {len(df)} nến...")
    d = build_features(df)

    # Forward returns (T+1 to T+lookahead sum)
    fwd_ret = d["log_ret"].shift(-1).rolling(lookahead, min_periods=1).sum().shift(-(lookahead - 1))
    fwd_arr = fwd_ret.values

    results = []
    total = len(ALPHA_REGISTRY)
    for i, (name, (fn, desc)) in enumerate(ALPHA_REGISTRY.items()):
        print(f"  [{i+1:02d}/{total}] {name:<28} ...", end=" ")
        try:
            alpha_series = fn(d)
            alpha_norm   = normalize_alpha(alpha_series, method=norm_method)
            alpha_arr    = alpha_norm.values

            metrics = compute_metrics(alpha_arr, fwd_arr, lookahead)
            results.append({
                "alpha_id":   name,
                "description": desc,
                **metrics,
            })
            print(f"IC={metrics['ic']:+.3f}  Acc={metrics['accuracy']:.3f}  "
                  f"LongAcc={metrics['long_acc']:.3f}  Sharpe={metrics['sharpe']:+.2f}  "
                  f"Sortino={metrics['sortino']:+.2f}  MDD={metrics['mdd']:.2f}%")
        except Exception as e:
            print(f"LỖI: {e}")
            results.append({
                "alpha_id": name, "description": desc,
                "ic": 0.0, "accuracy": 0.5, "long_acc": 0.5,
                "sharpe": 0.0, "sortino": 0.0, "mdd": 0.0,
                "hit_rate": 0.0, "avg_trade": 0.0,
                "n": 0, "mean_ret": 0.0,
            })

    df_results = pd.DataFrame(results)
    return df_results


def rank_alphas(df_results: pd.DataFrame, weights: dict = None) -> pd.DataFrame:
    """
    Composite score:  0.35×|IC| + 0.30×accuracy + 0.20×long_acc + 0.15×sign(sharpe)
    Weighted for VN market (long-biased, T+2.5 settlement).
    """
    r = df_results.copy()
    r["ic_abs"] = r["ic"].abs()

    # Normalize each metric to [0,1]
    def norm01(s):
        lo, hi = s.min(), s.max()
        if hi - lo < 1e-9:
            return pd.Series(0.5, index=s.index)
        return (s - lo) / (hi - lo)

    r["score_ic"]     = norm01(r["ic_abs"])
    r["score_acc"]    = norm01(r["accuracy"])
    r["score_long"]   = norm01(r["long_acc"])
    r["score_sharpe"] = norm01(r["sharpe"])
    
    if weights is None:
        weights = {"ic": 0.35, "acc": 0.30, "long_acc": 0.20, "sharpe": 0.15}
        
    r["composite"] = (
        weights.get("ic", 0.35) * r["score_ic"]
      + weights.get("acc", 0.30) * r["score_acc"]
      + weights.get("long_acc", 0.20) * r["score_long"]
      + weights.get("sharpe", 0.15) * r["score_sharpe"]
    )

    return r.sort_values("composite", ascending=False).reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────────────
# 7. Data loader (reuses project's realtime_loader)
# ─────────────────────────────────────────────────────────────────────────────

def load_data(symbol: str, interval: str = "1d", lookback_days: int = 600) -> pd.DataFrame:
    try:
        from core.realtime_loader import fetch_realtime_ohlcv
        print(f"[AlphaCompare] Loading data for {symbol} ({interval}) from vnstock...")
        df, err = fetch_realtime_ohlcv(symbol=symbol, interval=interval,
                                        lookback_days=lookback_days, tail=600)
        if err:
            raise RuntimeError(err)
        if df.empty:
            raise RuntimeError("DataFrame rỗng")
        print(f"[AlphaCompare] ✓ {len(df)} candles from {df['Datetime'].iloc[0]} to {df['Datetime'].iloc[-1]}")
        return df
    except Exception as e:
        print(f"[AlphaCompare] Error loading realtime: {e}")
        print("[AlphaCompare] Thử tạo synthetic data để test...")
        return _synthetic_data(300)


def _synthetic_data(n: int = 300) -> pd.DataFrame:
    """Synthetic VN-like OHLCV for offline testing."""
    np.random.seed(42)
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    price = 50.0
    prices, highs, lows, opens, vols = [], [], [], [], []
    for _ in range(n):
        o = price * (1 + np.random.normal(0, 0.003))
        c = o * (1 + np.random.normal(0, 0.012))
        # clamp to ±7% (VN price limit)
        c = np.clip(c, o * 0.93, o * 1.07)
        h = max(o, c) * (1 + abs(np.random.normal(0, 0.003)))
        l = min(o, c) * (1 - abs(np.random.normal(0, 0.003)))
        v = max(1000, int(np.random.lognormal(10, 0.8)))
        opens.append(o); highs.append(h); lows.append(l); prices.append(c); vols.append(v)
        price = c
    return pd.DataFrame({
        "Datetime": dates, "Open": opens, "High": highs,
        "Low": lows, "Close": prices, "Volume": vols,
    })


# ─────────────────────────────────────────────────────────────────────────────
# 8. Report generator
# ─────────────────────────────────────────────────────────────────────────────

def print_report(ranked: pd.DataFrame, symbol: str, top_n: int = 5):
    sep = "─" * 100
    print(f"\n{'='*100}")
    print(f"  BẢNG XẾP HẠNG ALPHA — {symbol}")
    print(f"  Tiêu chí: IC×0.35 + Accuracy×0.30 + LongAccuracy×0.20 + Sharpe×0.15")
    print(f"{'='*100}")
    print(f"{'#':>3}  {'Alpha ID':<28}  {'IC':>6}  {'Acc':>6}  {'LongAcc':>8}  {'Sharpe':>7}  {'Score':>6}  Mô tả")
    print(sep)

    for i, row in ranked.iterrows():
        marker = "★ " if i < top_n else "  "
        print(f"{marker}{i+1:>3}  {row['alpha_id']:<28}  "
              f"{row['ic']:>+6.3f}  {row['accuracy']:>6.3f}  "
              f"{row['long_acc']:>8.3f}  {row['sharpe']:>+7.2f}  "
              f"{row['composite']:>6.3f}  {row['description'][:50]}")

    print(sep)
    print(f"\n🏆 TOP {top_n} ALPHA CHO {symbol}:")
    for i, row in ranked.head(top_n).iterrows():
        print(f"  [{i+1}] {row['alpha_id']} — {row['description']}")
        print(f"       IC={row['ic']:+.4f}  Accuracy={row['accuracy']:.1%}  "
              f"LongAcc={row['long_acc']:.1%}  Sharpe={row['sharpe']:+.2f}")

    current_ids = [k for k in ranked["alpha_id"] if k.startswith("CURRENT_")]
    current_ranked = ranked[ranked["alpha_id"].isin(current_ids)][["alpha_id", "composite"]].reset_index(drop=True)
    print(f"\n📊 Thứ hạng 5 alpha HIỆN TẠI:")
    for _, row in current_ranked.iterrows():
        rank = ranked[ranked["alpha_id"] == row["alpha_id"]].index[0] + 1
        print(f"  #{rank:>3}  {row['alpha_id']} — composite score={row['composite']:.4f}")


# ─────────────────────────────────────────────────────────────────────────────
# 9. Generate new alpha_agent patch
# ─────────────────────────────────────────────────────────────────────────────

NEW_ALPHA_TEMPLATES = {
    # ── Current Hardcoded Alphas ──
    "CURRENT_1_FDM": {
        "name": "Flow-Driven Momentum (FDM)",
        "type": "Tiếp diễn xu hướng",
        "formula": "Tanh( MACD_hist_normalized + ROC_adj × 0.5 )",
        "interp": "Đo lường sự hội tụ của dòng tiền thông qua MACD và xung lực giá (ROC).",
    },
    "CURRENT_2_SFA": {
        "name": "Sentiment-Flow Alpha (SFA)",
        "type": "Sentiment-Technical Hybrid",
        "formula": "Tanh( [SENT_Z × 0.8] + [LVR × 0.4] )",
        "interp": "Kết hợp tâm lý tin tức (CafeF/ViSoBERT) với sự phục hồi thanh khoản.",
    },
    "CURRENT_3_LVR": {
        "name": "Liquidity Void Reversion (LVR)",
        "type": "Phản đảo chiều (Mean Reversion)",
        "formula": "Tanh( -0.8 × ZScore( (Close - SMA5)/Close ) )",
        "interp": "Kỳ vọng giá quay đầu khi lệch quá xa khỏi đường trung bình 5 phiên.",
    },
    "CURRENT_4_BFE": {
        "name": "Bollinger Squeeze & Flow (BFE)",
        "type": "Đột phá biến động",
        "formula": "Tanh( (%B - 0.5) × Vol_ZScore(5) × 1.5 )",
        "interp": "Xác định điểm nổ volume khi giá đang ở biên Bollinger.",
    },
    "CURRENT_5_OFE": {
        "name": "Order Flow Exhaustion (OFE)",
        "type": "Đảo chiều cực đại",
        "formula": "Tanh( ROC_adj × close_pos × 3.0 )",
        "interp": "Phát hiện sự kiệt sức của dòng tiền tại các vùng giá cực trị.",
    },

    # ── WorldQuant 101 Adapted Alphas ──
    "WQ02_PriceVolDiv": {
        "name": "Price/Volume Divergence (WQ#2)",
        "type": "Phân kỳ (Divergence)",
        "formula": "−corr(rank(ΔlogVol,2), rank(Body,6), 6)",
        "interp": "Phát hiện sự lệch pha giữa nỗ lực (khối lượng) và kết quả (biến động giá).",
    },
    "WQ03_OpenVolCorr": {
        "name": "Open-Volume Correlation (WQ#3)",
        "type": "Tương quan ngược",
        "formula": "−corr(rank(Open,10), rank(Vol,10), 10)",
        "interp": "Tương quan âm giữa giá mở cửa và khối lượng thường báo hiệu đảo chiều.",
    },
    "WQ06_OpenVol": {
        "name": "Price-Volume Negative Sync (WQ#6)",
        "type": "Xung lực khối lượng",
        "formula": "−corr(Open, Vol, 10)",
        "interp": "Sự đồng thuận tiêu cực giữa giá và lượng phản ánh áp lực bán.",
    },
    "WQ07_VolSurgeMom": {
        "name": "Volume Surge Momentum (WQ#7)",
        "type": "Đột phá động lượng",
        "formula": "Vol>Avg ? (−rank(|ΔC7|,60)×sign(ΔC7)) : −1",
        "interp": "Phản ứng giá sau khi có sự bùng nổ khối lượng so với 20 phiên trước.",
    },
    "WQ09_MomContRev": {
        "name": "Momentum Cont/Rev Filter (WQ#9)",
        "type": "Lọc xu hướng",
        "formula": "min(ΔC1,5)>0 ? ΔC1 : (max<0 ? ΔC1 : −ΔC1)",
        "interp": "Tiếp diễn nếu xu hướng đồng nhất, đảo chiều nếu có sự pha trộn trong 5 phiên.",
    },
    "WQ12_VolPriceSign": {
        "name": "Volume-Price Sign Reversal (WQ#12)",
        "type": "Đảo chiều T+1 / T+3",
        "formula": "sign(Δvolume) × (−Δclose)",
        "interp": "Tăng khối lượng khi giá giảm → kỳ vọng bật lại; tăng khối lượng khi giá tăng → kỳ vọng rũ xuống.",
    },
    "WQ13_CovReverse": {
        "name": "Close-Vol Covariance Rev (WQ#13)",
        "type": "Hiệp biến đảo chiều",
        "formula": "−rank(cov(rank(C,5), rank(V,5), 5), 5)",
        "interp": "Hiệp biến cao giữa giá đóng cửa và khối lượng dự báo sự kiệt sức của xu hướng.",
    },
    "WQ16_HighVolCov": {
        "name": "High-Vol Covariance Rev (WQ#16)",
        "type": "Đảo chiều giá cao",
        "formula": "−rank(cov(rank(H,5), rank(V,5), 5), 5)",
        "interp": "Tương tự WQ13 nhưng tập trung vào giá cao nhất để tìm đỉnh ngắn hạn.",
    },
    "WQ19_LongShortMom": {
        "name": "Long-Term Trend × Short Rev (WQ#19)",
        "type": "Xu hướng & Đảo chiều",
        "formula": "−sign(ΔC7 + (C−C7)) × (1 + rank(ΣRet250, 20))",
        "interp": "Ưu tiên đảo chiều ngắn hạn trên nền một xu hướng dài hạn mạnh mẽ.",
    },
    "WQ20_GapAnalysis": {
        "name": "Open Gap Analysis (WQ#20)",
        "type": "Gap play T+1",
        "formula": "−rank(O−H1) × rank(O−C1) × rank(O−L1)",
        "interp": "Phân tích vị thế giá mở cửa so với vùng giá ngày hôm trước để tìm điểm fill gap.",
    },
    "WQ25_RetVolHeight": {
        "name": "Return-Vol Bar Momentum (WQ#25)",
        "type": "Động lượng thanh nến",
        "formula": "rank((−Ret × ADV20 × VWAP) × (H − C), 5)",
        "interp": "Kết hợp biên độ nến, khối lượng trung bình và tỷ suất sinh lời.",
    },
    "WQ30_SignStreakVol": {
        "name": "3-Day Sign Streak Vol (WQ#30)",
        "type": "Chuỗi tăng/giảm",
        "formula": "1 − rank(sign_streak × V5/V20, 10)",
        "interp": "Đánh giá sức mạnh của chuỗi tăng/giảm 3 ngày liên tiếp qua tỷ lệ khối lượng.",
    },
    "WQ33_BodyDirection": {
        "name": "Body Direction Rank (WQ#33)",
        "type": "Xung lực thân nến",
        "formula": "rank(−1 × (1 − O/C), 10)",
        "interp": "Xếp hạng dựa trên hướng và độ dài của thân nến so với quá khứ.",
    },
    "WQ34_VolRatioRev": {
        "name": "Volatility Ratio Reversal (WQ#34)",
        "type": "Đảo chiều biến động",
        "formula": "rank(1−rank(std2/std5)) + (1−rank(ΔC1))",
        "interp": "Biến động ngắn hạn thấp hơn trung bình kèm giá giảm là tín hiệu mua tốt.",
    },
    "WQ38_TsRankBody": {
        "name": "TsRank Close × Body Ratio (WQ#38)",
        "type": "Đảo chiều vùng cao",
        "formula": "−rank(C,10) × (C/O)",
        "interp": "Kết hợp thứ hạng giá với hình dạng nến để tìm điểm đảo chiều.",
    },
    "WQ40_HighVolatVol": {
        "name": "High Volatility × Vol Corr (WQ#40)",
        "type": "Đảo chiều biến động mạnh",
        "formula": "−rank(std(H,10),5) × corr(H, V, 10)",
        "interp": "Khi biến động giá cao nhất tăng kèm tương quan volume thuận → báo hiệu đỉnh.",
    },
    "WQ41_GeoMeanVwap": {
        "name": "GeoMean H/L vs VWAP (WQ#41)",
        "type": "Fair Value Gap",
        "formula": "sqrt(H × L) − VWAP",
        "interp": "Đo lường sự lệch pha giữa giá trị hợp lý (trung bình nhân H/L) và giá trung bình tích lũy.",
    },
    "WQ43_VolSurgeRev7": {
        "name": "Volume Surge × 7D Rev (WQ#43)",
        "type": "Đảo chiều trung hạn",
        "formula": "rank(V/ADV20, 20) × rank(−ΔC7, 8)",
        "interp": "Kết hợp bùng nổ khối lượng với sự quá bán trong 7 phiên (phù hợp T+2.5).",
    },
    "WQ44_HighVolCorr": {
        "name": "High-Price Vol Corr (WQ#44)",
        "type": "Tương quan giá-lượng",
        "formula": "−corr(H, rank(V,5), 5)",
        "interp": "Tương quan âm giữa giá cao nhất và thứ hạng khối lượng dự báo sự suy yếu.",
    },
    "WQ53_BarPosChange": {
        "name": "Bar Position Change (WQ#53)",
        "type": "Vị thế trong nến",
        "formula": "−Δ( (C−L − H−C)/(C−L), 9)",
        "interp": "Đo lường sự thay đổi của vị trí giá đóng cửa trong phạm vi nến trong 9 phiên.",
    },
    "WQ54_BarAsymm": {
        "name": "Bar Asymmetry Magnitude (WQ#54)",
        "type": "Bất đối xứng nến",
        "formula": "−1 × ((L−C)×O^2) / ((L−H)×C^2)",
        "interp": "Sử dụng độ bất đối xứng của nến để dự báo sự mất cân bằng cung cầu.",
    },
    "WQ55_StochVolCorr": {
        "name": "Stochastic-Vol Corr Rev (WQ#55)",
        "type": "Đảo chiều T+2.5",
        "formula": "−corr(rank(stoch, 6), rank(V, 6), 6)",
        "interp": "Corr âm giữa vị thế giá (Stochastic) và khối lượng thường là điểm mua/bán tốt.",
    },

    # ── Full WQ-101 set ────────────────────────────────────────────────────
    "WQ01_ArgMaxRank": {
        "name": "ArgMax SignedPower Rank (WQ#1)",
        "type": "Đảo chiều cực trị",
        "formula": "rank(ts_argmax(SignedPower(ret<0?std20:close, 2), 5)) – 0.5",
        "interp": "Dùng std khi ngày xấu, close khi ngày tốt; vị trí cực trị trong 5 nến dự báo đảo chiều.",
    },
    "WQ04_LowRankRev": {
        "name": "Low Price Persistence (WQ#4)",
        "type": "Đảo chiều giá thấp",
        "formula": "–Ts_Rank(rank(low), 9)",
        "interp": "Giá thấp liên tục nhiều phiên tạo áp lực phục hồi kỹ thuật.",
    },
    "WQ05_OpenVwapBody": {
        "name": "Open-VWAP Body Combo (WQ#5)",
        "type": "Đảo chiều VWAP",
        "formula": "rank(open – sma(vwap,10)) × (–abs(rank(close – vwap)))",
        "interp": "Open xa khỏi VWAP kép với thân nến dẹt dự báo quay đầu về VWAP.",
    },
    "WQ08_OpenRetMom": {
        "name": "Open × Return Momentum (WQ#8)",
        "type": "Xung lực mở cửa",
        "formula": "–rank(sum(open,5)×sum(ret,5) – delay(sum(open,5)×sum(ret,5),10))",
        "interp": "Phân kỳ giữa lực mua mở cửa hiện tại và 10 phiên trước.",
    },
    "WQ10_MomRank4": {
        "name": "Momentum Rank Filter 4D (WQ#10)",
        "type": "Lọc xu hướng",
        "formula": "rank(ts_min/max delta(close,1), 4-day filter)",
        "interp": "Lọc đà giá trong 4 phiên: tiếp diễn hoặc đảo chiều.",
    },
    "WQ11_VwapCloseVol": {
        "name": "VWAP-Close Range × Volume (WQ#11)",
        "type": "Biến động VWAP",
        "formula": "(rank(ts_max(vwap–close,3)) + rank(ts_min(vwap–close,3))) × rank(Δvol,3)",
        "interp": "Biên độ vwap-close kết hợp với thay đổi volume dự báo breakout.",
    },
    "WQ14_RetDeltaCorr": {
        "name": "Return Delta × Open-Vol Corr (WQ#14)",
        "type": "Phân kỳ dòng tiền",
        "formula": "–rank(delta(returns,3)) × corr(open,volume,10)",
        "interp": "Đà giảm momentum kết hợp tương quan open-vol âm báo tín hiệu mua.",
    },
    "WQ15_HighVolSumCorr": {
        "name": "Sum High-Vol Corr (WQ#15)",
        "type": "Tương quan đỉnh-volume",
        "formula": "–sum(rank(corr(rank(high),rank(vol),3)),3)",
        "interp": "Corr cao giữa đỉnh giá và volume trong 3 phiên = sắp kiệt lực.",
    },
    "WQ17_TripleRank": {
        "name": "Triple Rank Acceleration (WQ#17)",
        "type": "Gia tốc giá đảo chiều",
        "formula": "–rank(ts_rank(close,10)) × rank(Δ²close) × rank(ts_rank(vol/adv20,5))",
        "interp": "Kết hợp thứ hạng giá, gia tốc và áp lực volume để tìm điểm đảo chiều.",
    },
    "WQ18_StdBodyCorr": {
        "name": "Std + Body + Corr Rank (WQ#18)",
        "type": "Biến động tổng hợp",
        "formula": "–rank(std(|c–o|,5) + (c–o) + corr(close,open,10))",
        "interp": "Biến động thân nến + thân hiện tại + tương quan đóng-mở dự báo tiếp diễn.",
    },
    "WQ21_SmaCondition": {
        "name": "SMA Band Condition (WQ#21)",
        "type": "Điều kiện dải SMA",
        "formula": "SMA8+std8 < SMA2 → –1; SMA2 < SMA8–std8 → 1; vol≥adv → 1",
        "interp": "3 điều kiện dải SMA8 ± std kết hợp tỷ lệ volume để lọc xu hướng.",
    },
    "WQ22_CorrDeltaStd": {
        "name": "Corr Delta × Std Rank (WQ#22)",
        "type": "Phân kỳ corr-std",
        "formula": "–delta(corr(high,vol,5),5) × rank(std(close,20))",
        "interp": "Thay đổi tương quan đỉnh-volume kết hợp với biến động lịch sử.",
    },
    "WQ23_HighSmaBreak": {
        "name": "High SMA Breakout (WQ#23)",
        "type": "Đột phá đỉnh SMA20",
        "formula": "SMA20(high) < high → –delta(high,2)",
        "interp": "Khi giá cao vượt SMA20-đỉnh, dự báo điều chỉnh kỹ thuật ngắn hạn.",
    },
    "WQ24_TrendSlope": {
        "name": "100-Day Slope Condition (WQ#24)",
        "type": "Xu hướng dài hạn",
        "formula": "slope100 ≤ 0.05 → –(close–min100); else –delta(close,3)",
        "interp": "Xu hướng phẳng dài hạn → mean-reversion; xu hướng dốc → momentum ngắn.",
    },
    "WQ26_TsMaxCorrVol": {
        "name": "TsMax Corr Vol-High (WQ#26)",
        "type": "Cực trị tương quan",
        "formula": "–ts_max(corr(ts_rank(vol,5), ts_rank(high,5), 5), 3)",
        "interp": "Cực trị 3 phiên của tương quan ts_rank_vol vs ts_rank_high dự báo đảo chiều.",
    },
    "WQ27_CorrRankCond": {
        "name": "Corr Rank Threshold (WQ#27)",
        "type": "Ngưỡng tương quan",
        "formula": "rank(sum(corr(rank(vol),rank(vwap),6),2)/2) > 0.5 → –1 else 1",
        "interp": "Khi tương quan vol-vwap vượt ngưỡng 50th-percentile, dự báo đảo chiều.",
    },
    "WQ28_CorrLowClose": {
        "name": "Corr ADV20 Low Scaled (WQ#28)",
        "type": "Fair value gap",
        "formula": "scale(corr(adv20,low,5) + (high+low)/2 – close)",
        "interp": "Kết hợp corr adv20-thấp với vị trí giá so với HL/2 để đo fair value gap.",
    },
    "WQ29_NestedRankLog": {
        "name": "Nested Rank Log (WQ#29)",
        "type": "Tổng hợp rank lồng nhau",
        "formula": "min(product(rank(rank(scale(log(sum(ts_min(…)))))),5),5) + ts_rank(delay(–ret,6),5)",
        "interp": "Rank lồng nhau sâu + delay momentum dự báo đà tiếp theo.",
    },
    "WQ31_DecayDeltaCorr": {
        "name": "Decay Delta Corr Combo (WQ#31)",
        "type": "Kết hợp decay-delta-corr",
        "formula": "rank³(decay(–rank²(Δclose10),10)) + rank(–Δclose3) + sign(scale(corr(adv20,low,12)))",
        "interp": "Triple rank với decay tạo tín hiệu bền vững; sign(corr) xác nhận.",
    },
    "WQ32_ScaleCorr230": {
        "name": "Scale + Corr 230 (WQ#32)",
        "type": "Dài hạn + Trung hạn",
        "formula": "scale(sma7–close) + 20×scale(corr(vwap,delay(close,5),230))",
        "interp": "Kết hợp sai lệch SMA7 với tương quan VWAP dài hạn 230 phiên.",
    },
    "WQ35_TripleTsRank": {
        "name": "Triple TsRank Product (WQ#35)",
        "type": "Xung lực đa chiều",
        "formula": "Ts_Rank(vol,32) × (1–Ts_Rank(close+high–low,16)) × (1–Ts_Rank(returns,32))",
        "interp": "Volume mạnh × biên độ thấp × return thấp = tích lũy trước nổ.",
    },
    "WQ36_WeightedCombo": {
        "name": "Weighted 5-Factor Combo (WQ#36)",
        "type": "Tổng hợp 5 nhân tố",
        "formula": "2.21×corr(c–o,delay(vol,1),15) + 0.7×rank(o–c) + 0.73×delay_rank + corr_abs + 0.6×sma_body",
        "interp": "Tổ hợp có trọng số 5 nhân tố: corr thân-vol, thân, delay, corr_vwap_adv, sma×thân.",
    },
    "WQ37_DelayOcCorr": {
        "name": "Delay OC Corr Long (WQ#37)",
        "type": "Tương quan trễ dài hạn",
        "formula": "rank(corr(delay(open–close,1),close,200)) + rank(open–close)",
        "interp": "Tương quan 200-phiên giữa thân trễ và giá đóng + momentum thân.",
    },
    "WQ39_DeltaDecayRet": {
        "name": "Delta Decay Return (WQ#39)",
        "type": "Momentum decay",
        "formula": "–rank(Δclose7×(1–rank(decay(vol/adv20,9)))) × (1+rank(ΣRet250))",
        "interp": "Momentum 7 phiên điều chỉnh theo decay volume, khuếch đại bởi xu hướng 250 phiên.",
    },
    "WQ42_VwapCloseRatio": {
        "name": "VWAP-Close Ratio (WQ#42)",
        "type": "Mean-reversion VWAP",
        "formula": "rank(vwap–close) / rank(vwap+close)",
        "interp": "Tỷ lệ rank của khoảng cách và tổng VWAP-close: delay-0 mean-reversion alpha.",
    },
    "WQ45_DelayCloseCorr": {
        "name": "Delay Close Sum Corr (WQ#45)",
        "type": "Đảo chiều tích lũy",
        "formula": "–rank(sum(delay(close,5),20)/20 × corr(c,vol,2)) × rank(corr(sum(c,5),sum(c,20),2))",
        "interp": "Giá trễ trung bình kết hợp với tương quan đóng-vol và tương quan tổng-giá.",
    },
    "WQ46_SlopeCond025": {
        "name": "Slope Condition 0.25 (WQ#46)",
        "type": "Đảo chiều slope",
        "formula": "diff>0.25 → –1; diff<0 → 1; else –Δclose",
        "interp": "Đánh giá tốc độ thay đổi slope 10 phiên; tăng tốc mạnh → đảo chiều.",
    },
    "WQ47_CloseMomentum": {
        "name": "Close Momentum × High Factor (WQ#47)",
        "type": "Xung lực đóng-đỉnh",
        "formula": "rank(1/close)×vol/adv20 × high×rank(h–c)/sma5h – rank(Δvwap5)",
        "interp": "Tích hợp nghịch đảo giá, volume, đỉnh-đóng và thay đổi VWAP.",
    },
    "WQ49_SlopeCond01": {
        "name": "Slope Condition –0.1 (WQ#49)",
        "type": "Đảo chiều slope yếu",
        "formula": "diff < –0.1 → 1; else –Δclose",
        "interp": "Khi slope sụt mạnh dưới –0.1, dự báo phục hồi kỹ thuật.",
    },
    "WQ50_TsMaxCorrRank": {
        "name": "TsMax Corr Rank Vol-VWAP (WQ#50)",
        "type": "Cực trị tương quan VWAP",
        "formula": "–ts_max(rank(corr(rank(vol),rank(vwap),5)),5)",
        "interp": "Cực trị tương quan vol-vwap trong 5 phiên; đỉnh corr = sắp đảo chiều.",
    },
    "WQ51_SlopeCond005": {
        "name": "Slope Condition –0.05 (WQ#51)",
        "type": "Đảo chiều slope nhẹ",
        "formula": "diff < –0.05 → 1; else –Δclose",
        "interp": "Ngưỡng slope nhẹ hơn WQ#49; nhạy cảm hơn với sụt giảm nhỏ.",
    },
    "WQ52_TsMinRetVol": {
        "name": "TsMin Return Volume (WQ#52)",
        "type": "Đột phá từ đáy",
        "formula": "(–ts_min(low,5)+delay) × rank((ΣRet240–ΣRet20)/220) × ts_rank(vol,5)",
        "interp": "Kết hợp bật từ đáy, momentum tương đối dài hạn và volume tăng.",
    },
    "WQ57_VwapArgmax": {
        "name": "VWAP Argmax Decay (WQ#57)",
        "type": "VWAP mean-reversion",
        "formula": "–(close–vwap) / decay(rank(ts_argmax(close,30)),2)",
        "interp": "Khoảng cách close-vwap chuẩn hóa theo vị trí đỉnh 30 phiên.",
    },
    "WQ60_BodyScaleArgmax": {
        "name": "Body Scale vs Argmax (WQ#60)",
        "type": "Áp lực thân nến",
        "formula": "–(2×scale(rank(body_vol)) – scale(rank(ts_argmax(close,10))))",
        "interp": "Hiệu số giữa tỷ lệ thân-volume và vị trí đỉnh giá gần nhất.",
    },
    "WQ61_VwapMinCorr": {
        "name": "VWAP Min vs ADV180 Corr (WQ#61)",
        "type": "So sánh VWAP-adv180",
        "formula": "rank(vwap–ts_min(vwap,16)) < rank(corr(vwap,adv180,18))",
        "interp": "Khi khoảng cách vwap-đáy nhỏ hơn tương quan với volume dài hạn.",
    },
    "WQ62_CorrOpenRank": {
        "name": "VWAP Corr vs Open Rank (WQ#62)",
        "type": "So sánh corr-rank",
        "formula": "rank(corr(vwap,sum(adv20,22),10)) < rank(2×rank(open) < rank(hl/2)+rank(high))",
        "interp": "Tương quan VWAP-adv20 so sánh với cấu trúc open/hl để phát hiện phân kỳ.",
    },
    "WQ65_WeightedCorrMin": {
        "name": "Weighted Price-ADV60 Corr (WQ#65)",
        "type": "Corr vs Open min",
        "formula": "rank(corr(w×open+(1–w)×vwap, sum(adv60,9), 6)) < rank(open–ts_min(open,14))",
        "interp": "Tương quan giá pha trộn với adv60 so sánh với breakout open khỏi đáy 14 phiên.",
    },
    "WQ66_DecayVwapLow": {
        "name": "Decay VWAP Low Gap (WQ#66)",
        "type": "Khoảng cách VWAP-low",
        "formula": "–(rank(decay(Δvwap,7)) + Ts_Rank(decay((low–vwap)/body,11),7))",
        "interp": "Kết hợp decay delta-vwap và tỷ lệ khoảng cách low-vwap trên thân nến.",
    },
    "WQ71_MaxTsRankDecay": {
        "name": "Max Decay Corr Rank (WQ#71)",
        "type": "Tổng hợp decay max",
        "formula": "max(Ts_Rank(decay(corr(ts_rank(c,3),ts_rank(adv180,12),18),4),16), Ts_Rank(decay(rank((l+o–2×vwap)²),16),4))",
        "interp": "Max của 2 decay: tương quan ts_rank close-adv180 và bình phương khoảng cách open-vwap.",
    },
    "WQ72_DecayRatio": {
        "name": "Decay Corr Ratio (WQ#72)",
        "type": "Tỷ lệ tương quan",
        "formula": "rank(decay(corr(hl/2,adv40,9),10)) / rank(decay(corr(ts_rank(vwap,4),ts_rank(vol,19),7),3))",
        "interp": "Tỷ số corr hl/2-adv40 trên corr ts_rank(vwap)-ts_rank(vol).",
    },
    "WQ73_MaxDecayDelta": {
        "name": "Max Decay Delta VWAP (WQ#73)",
        "type": "Đảo chiều VWAP delta",
        "formula": "–max(rank(decay(Δvwap5,3)), Ts_Rank(decay(–Δ(w×open+(1–w)×low)/x,3),17))",
        "interp": "Max của decay delta-vwap5 và decay tỷ lệ thay đổi open-low.",
    },
    "WQ74_CorrCloseAdv30": {
        "name": "Close-ADV30 vs High-Vol Corr (WQ#74)",
        "type": "So sánh tương quan",
        "formula": "rank(corr(close,sum(adv30,37),15)) < rank(corr(rank(w×high+(1–w)×vwap),rank(vol),11)) → –1",
        "interp": "Tương quan close-adv30 nhỏ hơn corr rank(high_blend)-rank(vol).",
    },
    "WQ75_CorrVwapAdv50": {
        "name": "VWAP-Vol vs Low-ADV50 Corr (WQ#75)",
        "type": "So sánh tương quan vol",
        "formula": "rank(corr(vwap,vol,4)) < rank(corr(rank(low),rank(adv50),12))",
        "interp": "Tương quan vwap-vol ngắn so với corr low-adv50 dài.",
    },
    "WQ77_MinDecayHL": {
        "name": "Min Decay HL VWAP (WQ#77)",
        "type": "Kết hợp min decay",
        "formula": "min(rank(decay(hl/2–vwap,20)), rank(decay(corr(hl/2,adv40,3),6)))",
        "interp": "Min của 2 decay: khoảng cách hl/2-vwap và corr hl/2-adv40.",
    },
    "WQ78_CorrRankPow": {
        "name": "Corr Rank Power (WQ#78)",
        "type": "Corr rank mũ",
        "formula": "rank(corr(sum(w×low+(1–w)×vwap,20),sum(adv40,20),7))^rank(corr(rank(vwap),rank(vol),6))",
        "interp": "Corr blend low-vwap mũ corr rank(vwap)-rank(vol).",
    },
    "WQ83_HLRatioVol": {
        "name": "HL Ratio Volume Rank (WQ#83)",
        "type": "Biên độ-volume",
        "formula": "(rank(delay(HL/sma5c,2))×rank²(vol)) / (HL/sma5c / (vwap–close))",
        "interp": "Tỷ số biên độ delay và volume chia cho tỷ lệ biên độ-vwap.",
    },
    "WQ84_SignedPowerArgmax": {
        "name": "SignedPower TsRank Argmax (WQ#84)",
        "type": "VWAP momentum power",
        "formula": "SignedPower(Ts_Rank(vwap–ts_max(vwap,15),21), delta(close,5))",
        "interp": "Vị trí VWAP dưới đỉnh 15 phiên khuếch đại theo delta close 5 phiên.",
    },
    "WQ85_CorrPow": {
        "name": "Corr Power High-Vol (WQ#85)",
        "type": "Tương quan mũ",
        "formula": "rank(corr(w×high+(1–w)×close,adv30,10))^rank(corr(ts_rank(hl/2,4),ts_rank(vol,10),7))",
        "interp": "Corr blend high-close với adv30, mũ corr ts_rank(hl/2)-ts_rank(vol).",
    },
    "WQ86_CorrCloseAdv20": {
        "name": "Close-ADV20 Sum Corr (WQ#86)",
        "type": "Corr vs body gap",
        "formula": "Ts_Rank(corr(close,sum(adv20,15),6),21) < rank(close–vwap) → –1",
        "interp": "Khi tương quan close-adv20 nhỏ hơn rank khoảng cách close-vwap.",
    },
    "WQ88_MinDecayOpen": {
        "name": "Min Decay Open Low High (WQ#88)",
        "type": "OHLC balance",
        "formula": "min(rank(decay((rank(o)+rank(l))–(rank(h)+rank(c)),8)), Ts_Rank(decay(corr(ts_rank(c,8),ts_rank(adv60,21),8),7),3))",
        "interp": "Min của rank decay OHLC balance và ts_rank decay corr close-adv60.",
    },
    "WQ89_DecayLowVwap": {
        "name": "Decay Low-ADV10 vs VWAP Delta (WQ#89)",
        "type": "Phân kỳ low-vwap",
        "formula": "Ts_Rank(decay(corr(low,adv10,7),6),4) – Ts_Rank(decay(delta(vwap,3),10),15)",
        "interp": "Hiệu số corr low-adv10 trừ decay delta-vwap dự báo phân kỳ.",
    },
    "WQ92_MinCondDecay": {
        "name": "Min Condition Decay (WQ#92)",
        "type": "Áp lực giá min",
        "formula": "min(Ts_Rank(decay(hl/2+c<l+o,15),19), Ts_Rank(decay(corr(rank(low),rank(adv30),8),7),7))",
        "interp": "Min của điều kiện áp lực giá và corr low-adv30.",
    },
    "WQ94_VwapMinPow": {
        "name": "VWAP Min Power (WQ#94)",
        "type": "VWAP rebound power",
        "formula": "–rank(vwap–ts_min(vwap,12))^Ts_Rank(corr(ts_rank(vwap,20),ts_rank(adv60,4),18),3)",
        "interp": "Khoảng cách vwap từ đáy mũ tương quan ts_rank(vwap)-ts_rank(adv60).",
    },
    "WQ95_OpenMinCorr": {
        "name": "Open Min vs Sum HL Corr (WQ#95)",
        "type": "Open breakout vs corr",
        "formula": "rank(open–ts_min(open,12)) < Ts_Rank(rank(corr(sum(hl/2,19),sum(adv40,19),13))^5,12)",
        "interp": "Breakout open khỏi đáy 12 phiên so với corr^5 của tổng hl/2-adv40.",
    },
    "WQ96_MaxDecayCorr": {
        "name": "Max Decay Corr ArgMax (WQ#96)",
        "type": "Đảo chiều cực trị corr",
        "formula": "–max(Ts_Rank(decay(corr(rank(vwap),rank(vol),4),4),8), Ts_Rank(decay(ts_argmax(corr(…),13),14),13))",
        "interp": "Max decay của corr vwap-vol và argmax corr close-adv60.",
    },
    "WQ98_DecayDiff": {
        "name": "Decay Corr Difference (WQ#98)",
        "type": "Phân kỳ corr decay",
        "formula": "rank(decay(corr(vwap,sum(adv5,27),5),7)) – rank(decay(ts_rank(ts_argmin(corr(rank(o),rank(adv15),21),9),7),8))",
        "interp": "Hiệu decay corr vwap-adv5 trừ decay argmin corr open-adv15.",
    },
    "WQ99_CorrHLAdv60": {
        "name": "HL-ADV60 vs Low-Vol Corr (WQ#99)",
        "type": "So sánh corr HL-vol",
        "formula": "rank(corr(sum(hl/2,20),sum(adv60,20),9)) < rank(corr(low,vol,6)) → –1",
        "interp": "Tương quan tổng hl/2-adv60 so với corr low-vol ngắn hạn.",
    },
    "WQ101_IntradayBody": {
        "name": "Intraday Body Ratio (WQ#101)",
        "type": "Tỷ lệ thân nến nội phiên",
        "formula": "(close – open) / ((high – low) + 0.001)",
        "interp": "Tỷ lệ thân nến so với tổng biên độ ngày: +1 là nến tăng hoàn hảo, –1 là giảm.",
    },
}


def generate_new_alpha_agent(ranked: pd.DataFrame, top_n: int = 5,
                              output_path: str = "/mnt/user-data/outputs/alpha_agent_new.py"):
    """Generate updated alpha_agent.py with top-5 new alphas."""
    top5 = ranked.head(top_n)["alpha_id"].tolist()
    print(f"\n[AlphaCompare] Tạo alpha_agent_new.py với top-5: {top5}")

    # Map alpha IDs to their template implementations
    selected_templates = {}
    for aid in top5:
        if aid in NEW_ALPHA_TEMPLATES:
            selected_templates[aid] = NEW_ALPHA_TEMPLATES[aid]
        elif aid.startswith("CURRENT_"):
            selected_templates[aid] = {"keep_original": True}
        else:
            # fallback: use a generic template
            selected_templates[aid] = {
                "name": aid,
                "type": "Adapted WQ Alpha",
                "formula": f"Adapted from 101 Formulaic Alphas: {aid}",
                "interp": f"Alpha from WorldQuant 101 adapted for VN single-stock."
            }

    return top5, selected_templates


# ─────────────────────────────────────────────────────────────────────────────
# 10. Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    symbol   = sys.argv[1] if len(sys.argv) > 1 else "VNM"
    interval = sys.argv[2] if len(sys.argv) > 2 else "1d"

    print("=" * 100)
    print(f"  ALPHA COMPARISON — {symbol} / {interval}")
    print("=" * 100)

    df = load_data(symbol, interval, lookback_days=600)

    # Lookahead = 3 candles for daily (T+2.5), 1 for intraday
    lookahead = 3 if interval in ("1d", "1w", "1mo") else 1

    results = run_backtest(df, lookahead=lookahead)
    ranked  = rank_alphas(results)

    print_report(ranked, symbol, top_n=5)

    # Save CSV
    out_csv = f"alpha_ranking_{symbol}_{interval}.csv"
    import os; os.makedirs("outputs", exist_ok=True)
    ranked.to_csv(out_csv, index=False, encoding="utf-8-sig")
    print(f"\n[AlphaCompare] ✓ Đã lưu bảng xếp hạng: {out_csv}")

    top5_ids, templates = generate_new_alpha_agent(ranked, top_n=5)

    return ranked, top5_ids


if __name__ == "__main__":
    main()
