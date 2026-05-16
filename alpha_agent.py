import math
import time
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from langchain_core.messages import HumanMessage, SystemMessage

from alpha_selector import select_top_alphas
import alpha_compare


# ── Retry wrapper ──────────────────────────────────────────────────────────────

def _invoke_with_retry(call_fn, *args, retries=3, wait_sec=5):
    last_err = None
    for attempt in range(retries):
        try:
            return call_fn(*args)
        except Exception as e:
            last_err = e
            print(f"[AlphaAgent] Lỗi lần {attempt + 1}/{retries}: {e}")
            if attempt < retries - 1:
                time.sleep(wait_sec)
    raise RuntimeError(f"[AlphaAgent] Vượt quá số lần thử lại. Lỗi cuối: {last_err}")


# ── Math helpers ───────────────────────────────────────────────────────────────

def _clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(x)))


def _safe(x) -> float:
    try:
        v = float(x)
        return 0.0 if (math.isnan(v) or math.isinf(v)) else v
    except (TypeError, ValueError):
        return 0.0


def _hist_rank(series: List[float], descending: bool = False) -> float:
    clean: List[float] = [
        v for v in series
        if not (math.isnan(float(v)) or math.isinf(float(v)))
    ]
    if len(clean) < 2:
        return 0.5
    current = clean[-1]
    prior   = clean[:-1]
    rank    = sum(1 for v in prior if v <= current) / len(prior)
    return round(1.0 - rank if descending else rank, 4)


def _zscore_of_series(series: List[float]) -> float:
    clean = [_safe(v) for v in series]
    clean = [v for v in clean if not (math.isnan(v) or math.isinf(v))]
    if len(clean) < 2:
        return 0.0
    mu    = sum(clean) / len(clean)
    sigma = math.sqrt(sum((x - mu) ** 2 for x in clean) / len(clean))
    return round((clean[-1] - mu) / (sigma + 1e-9), 4)


def _sign(x: float) -> float:
    if x > 1e-9:  return  1.0
    if x < -1e-9: return -1.0
    return 0.0


# ── Technical Indicator Helpers ────────────────────────────────────────────────

def _ema(prices: List[float], period: int) -> float:
    n = len(prices)
    if n == 0:
        return 0.0
    init = sum(prices[:min(period, n)]) / min(period, n)
    k = 2.0 / (period + 1)
    val = init
    for p in prices[min(period, n):]:
        val = p * k + val * (1.0 - k)
    return val


def _sma(prices: List[float], period: int) -> float:
    window = prices[-period:] if len(prices) >= period else prices
    return sum(window) / len(window) if window else 0.0


def _rolling_std(prices: List[float], period: int) -> float:
    window = prices[-period:] if len(prices) >= period else prices
    if len(window) < 2:
        return 1e-6
    mu  = sum(window) / len(window)
    var = sum((x - mu) ** 2 for x in window) / len(window)
    return max(math.sqrt(var), 1e-9)


def _rsi(closes: List[float], period: int = 14) -> float:
    n = len(closes)
    if n <= period:
        return 50.0
    gains, losses = [], []
    for i in range(1, n):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(abs(min(d, 0.0)))
    ag = sum(gains[:period]) / period
    al = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        ag = (ag * (period - 1) + gains[i]) / period
        al = (al * (period - 1) + losses[i]) / period
    if al < 1e-9:
        return 100.0
    return round(100.0 - 100.0 / (1.0 + ag / al), 4)


def _willr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
    n = len(closes)
    p = min(period, n)
    if p == 0:
        return -50.0
    hh = max(highs[-p:])
    ll = min(lows[-p:])
    if hh - ll < 1e-9:
        return -50.0
    return round(-100.0 * (hh - closes[-1]) / (hh - ll), 4)


def _bollinger(closes: List[float], period: int = 20, mult: float = 2.0) -> Dict:
    window = closes[-period:] if len(closes) >= period else closes
    sma    = sum(window) / len(window)
    std    = math.sqrt(sum((x - sma) ** 2 for x in window) / len(window))
    upper  = sma + mult * std
    lower  = sma - mult * std
    width  = upper - lower
    pct_b  = (closes[-1] - lower) / (width + 1e-9)
    return {
        "upper":       round(upper, 4),
        "middle":      round(sma, 4),
        "lower":       round(lower, 4),
        "width_price": round(width, 4),
        "width_rel":   round(width / (sma + 1e-9), 4),
        "pct_b":       round(pct_b, 4),
        "std":         round(std, 4),
    }


def _macd_last_hist(closes: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> float:
    n = len(closes)
    if n < slow + signal:
        return 0.0
    macd_lines: List[float] = []
    for i in range(max(slow, n - signal - 10), n):
        ef = _ema(closes[:i + 1], fast)
        es = _ema(closes[:i + 1], slow)
        macd_lines.append(ef - es)
    if len(macd_lines) < 2:
        ef = _ema(closes, fast)
        es = _ema(closes, slow)
        return ef - es
    signal_val = _ema(macd_lines, signal)
    return round(macd_lines[-1] - signal_val, 6)


# ── Extract all technical vars ─────────────────────────────────────────────────

def _extract_tech_vars(kline_data: dict) -> dict:
    RANK_WINDOW = 30

    try:
        df     = pd.DataFrame(kline_data)
        closes = [_safe(x) for x in df["Close"].tolist()]
        highs  = [_safe(x) for x in df["High"].tolist()]
        lows   = [_safe(x) for x in df["Low"].tolist()]
        n      = len(closes)

        has_vol = (
            "Volume" in df.columns
            and df["Volume"].notna().sum() > n * 0.5
            and df["Volume"].sum() > 0
        )
        volumes = [_safe(x) for x in df["Volume"].tolist()] if has_vol else None

        close_0 = closes[-1]
        high_0  = highs[-1]
        low_0   = lows[-1]

        ema5  = _ema(closes, 5)
        ema20 = _ema(closes, 20)
        sma5  = _sma(closes, 5)
        sma10 = _sma(closes, 10)
        sma20 = _sma(closes, 20)
        bb    = _bollinger(closes, 20)
        rsi_val   = _rsi(closes, 14)
        willr_val = _willr(highs, lows, closes, 14)
        roc1_pct  = (
            (close_0 - closes[-2]) / (closes[-2] + 1e-9) * 100.0
            if n >= 2 else 0.0
        )
        ema_diff     = ema5 - ema20
        ema_diff_pct = ema_diff / (close_0 + 1e-9) * 100.0
        rs10         = _rolling_std(closes, 10)
        rs10_pct     = rs10 / (close_0 + 1e-9) * 100.0
        intra_range  = high_0 - low_0
        close_pos    = (close_0 - low_0) / (intra_range + 1e-9) - 0.5
        close_dev_sma10 = (close_0 - sma10) / (bb["width_price"] + 1e-9)

        if has_vol and volumes:
            vol_0     = volumes[-1]
            sma_vol20 = _sma(volumes, 20)
            vol_surge = vol_0 / (sma_vol20 + 1e-9)
        else:
            ranges    = [h - l for h, l in zip(highs, lows)]
            avg_range = _sma(ranges, 20) if ranges else 1.0
            vol_surge = intra_range / (avg_range + 1e-9)

        if has_vol and volumes:
            vol_10 = volumes[-10:] if len(volumes) >= 10 else volumes
        else:
            _ranges = [h - l for h, l in zip(highs, lows)]
            vol_10  = _ranges[-10:] if len(_ranges) >= 10 else _ranges
        vol_zscore_10 = _zscore_of_series(vol_10)

        macd_hist_cur  = _macd_last_hist(closes)
        macd_hist_sign = _sign(macd_hist_cur)

        close_dev5_series: List[float] = []
        for i in range(max(5, n - 20), n):
            s5_i = _sma(closes[max(0, i - 5): i + 1], 5)
            close_dev5_series.append((closes[i] - s5_i) / (closes[i] + 1e-9))
        if not close_dev5_series:
            close_dev5_series = [(close_0 - sma5) / (close_0 + 1e-9)]
        cur_close_dev5   = (close_0 - sma5) / (close_0 + 1e-9)
        zscore_close_dev5 = _zscore_of_series(close_dev5_series)

        roc1_history: List[float] = []
        for i in range(max(1, n - 25), n):
            roc1_history.append(
                (closes[i] - closes[i - 1]) / (closes[i - 1] + 1e-9) * 100.0
            )
        std_roc1 = max(
            math.sqrt(
                sum((r - sum(roc1_history) / len(roc1_history)) ** 2 for r in roc1_history)
                / len(roc1_history)
            ) if len(roc1_history) > 1 else 0.01,
            0.01,
        )
        roc1_adjusted = roc1_pct / (std_roc1 + 1e-9)

        roc1_adj_series: List[float] = []
        for i in range(max(21, n - RANK_WINDOW), n):
            roc_i    = (closes[i] - closes[i - 1]) / (closes[i - 1] + 1e-9) * 100.0
            roc_hist = [
                (closes[j] - closes[j - 1]) / (closes[j - 1] + 1e-9) * 100.0
                for j in range(max(1, i - 20), i)
            ]
            if roc_hist:
                mu_r  = sum(roc_hist) / len(roc_hist)
                std_r = max(math.sqrt(sum((r - mu_r) ** 2 for r in roc_hist) / len(roc_hist)), 0.01)
                roc1_adj_series.append(roc_i / (std_r + 1e-9))
            else:
                roc1_adj_series.append(0.0)
        if not roc1_adj_series:
            roc1_adj_series = [roc1_adjusted]

        vol_surge_series: List[float] = []
        for i in range(max(21, n - RANK_WINDOW), n):
            ir = highs[i] - lows[i]
            if has_vol and volumes:
                sv = _sma(volumes[max(0, i - 20): i], 20) or 1.0
                vol_surge_series.append(volumes[i] / (sv + 1e-9))
            else:
                rng_hist = [highs[j] - lows[j] for j in range(max(0, i - 20), i)]
                avg_r    = sum(rng_hist) / len(rng_hist) if rng_hist else 1.0
                vol_surge_series.append(ir / (avg_r + 1e-9))
        if not vol_surge_series:
            vol_surge_series = [vol_surge]

        bb_pos_series_5: List[float] = []
        for i in range(max(20, n - 15), n):
            bb_i    = _bollinger(closes[max(0, i - 20): i + 1], 20)
            width_i = bb_i["upper"] - bb_i["lower"]
            bb_pos_series_5.append((closes[i] - bb_i["lower"]) / (width_i + 1e-9))
        if not bb_pos_series_5:
            bb_pos_series_5 = [bb["pct_b"]]
        zscore_bb_pos = _zscore_of_series(bb_pos_series_5)

        if has_vol and volumes:
            vol_5 = volumes[-5:] if len(volumes) >= 5 else volumes
        else:
            _ranges2 = [h - l for h, l in zip(highs, lows)]
            vol_5    = _ranges2[-5:] if len(_ranges2) >= 5 else _ranges2
        vol_zscore_5 = _zscore_of_series(vol_5)

        ema5_minus_sma20 = ema5 - sma20
        ema_diff_series: List[float] = []
        for i in range(max(20, n - RANK_WINDOW), n):
            e5_i  = _ema(closes[max(0, i - 15): i + 1], 5)
            s20_i = _sma(closes[max(0, i - 20): i + 1], 20)
            ema_diff_series.append(e5_i - s20_i)
        if not ema_diff_series:
            ema_diff_series = [ema5_minus_sma20]

        return {
            "close_0":            round(close_0, 4),
            "high_0":             round(high_0, 4),
            "low_0":              round(low_0, 4),
            "ema5":               round(ema5, 4),
            "ema20":              round(ema20, 4),
            "ema_diff":           round(ema_diff, 4),
            "ema_diff_pct":       round(ema_diff_pct, 4),
            "sma5":               round(sma5, 4),
            "sma10":              round(sma10, 4),
            "sma20":              round(sma20, 4),
            "bb_upper":           bb["upper"],
            "bb_middle":          bb["middle"],
            "bb_lower":           bb["lower"],
            "bb_width_price":     bb["width_price"],
            "bb_width_rel":       bb["width_rel"],
            "bb_pct_b":           bb["pct_b"],
            "rolling_std10":      round(rs10, 4),
            "rolling_std10_pct":  round(rs10_pct, 4),
            "rsi":                round(rsi_val, 4),
            "willr":              round(willr_val, 4),
            "roc1_pct":           round(roc1_pct, 4),
            "close_pos":          round(close_pos, 4),
            "close_dev_sma10":    round(close_dev_sma10, 4),
            "vol_surge":          round(vol_surge, 4),
            "has_volume":         has_vol,
            "vol_zscore_10":      round(vol_zscore_10, 4),
            "macd_hist_cur":      round(macd_hist_cur, 6),
            "macd_hist_sign":     macd_hist_sign,
            "cur_close_dev5":     round(cur_close_dev5, 6),
            "zscore_close_dev5":  round(zscore_close_dev5, 4),
            "roc1_adjusted":      round(roc1_adjusted, 4),
            "std_roc1":           round(std_roc1, 4),
            "zscore_bb_pos":      round(zscore_bb_pos, 4),
            "vol_zscore_5":       round(vol_zscore_5, 4),
            "ema5_minus_sma20":   round(ema5_minus_sma20, 4),
            "_roc1_adj_series":   roc1_adj_series,
            "_vol_surge_series":  vol_surge_series,
            "_ema_diff_series":   ema_diff_series,
        }

    except Exception as e:
        print(f"[AlphaAgent] Lỗi tính tech vars: {e}")
        return {
            "error": str(e),
            "close_0": 100.0, "high_0": 101.0, "low_0": 99.0,
            "ema5": 100.0, "ema20": 100.0, "ema_diff": 0.0, "ema_diff_pct": 0.0,
            "sma5": 100.0, "sma10": 100.0, "sma20": 100.0,
            "bb_upper": 103.0, "bb_middle": 100.0, "bb_lower": 97.0,
            "bb_width_price": 6.0, "bb_width_rel": 0.06, "bb_pct_b": 0.5,
            "rolling_std10": 1.5, "rolling_std10_pct": 1.5,
            "rsi": 50.0, "willr": -50.0, "roc1_pct": 0.0,
            "close_pos": 0.0, "close_dev_sma10": 0.0,
            "vol_surge": 1.0, "has_volume": False,
            "vol_zscore_10": 0.0, "macd_hist_cur": 0.0, "macd_hist_sign": 0.0,
            "cur_close_dev5": 0.0, "zscore_close_dev5": 0.0,
            "roc1_adjusted": 0.0, "std_roc1": 1.0,
            "zscore_bb_pos": 0.0, "vol_zscore_5": 0.0,
            "ema5_minus_sma20": 0.0,
            "_roc1_adj_series": [0.0], "_vol_surge_series": [1.0],
            "_ema_diff_series": [0.0],
        }


# ── Sentiment normalization ────────────────────────────────────────────────────

def _normalize_sentiment_scores(sentiment_data: dict) -> dict:
    empty = {
        "z_score": 0.0, "rel_sentiment": 0.0,
        "article_count": 0, "is_reliable": False,
        "raw_avg_score": 0.0, "delta_1d_proxy": 0.0,
    }
    if not sentiment_data:
        return empty
    ms = sentiment_data.get("main_sentiment", {})
    if not ms:
        return empty
    article_count = ms.get("article_count", 0)
    if article_count < 3:
        return {**empty, "article_count": article_count}

    avg_score = ms.get("avg_score", 0.0)
    scored    = sentiment_data.get("scored_articles", [])

    if len(scored) >= 3:
        scores = [_safe(a.get("numeric_score", 0.0)) for a in scored]
        mu     = sum(scores) / len(scores)
        sigma  = math.sqrt(sum((s - mu) ** 2 for s in scores) / len(scores))
        z_score = round((avg_score - mu) / (sigma + 0.001), 4)
    else:
        z_score = 0.0

    rel_sent = sentiment_data.get("related_sentiment", {})
    if rel_sent:
        rel_scores = [v.get("avg_score", 0.0) for v in rel_sent.values()
                      if v.get("article_count", 0) >= 2]
        rel_mean     = sum(rel_scores) / len(rel_scores) if rel_scores else 0.0
        rel_sentiment = round(avg_score - rel_mean, 4)
    else:
        rel_sentiment = 0.0

    delta_proxy = round(z_score * 0.5, 4)

    return {
        "z_score":        z_score,
        "rel_sentiment":  rel_sentiment,
        "article_count":  article_count,
        "is_reliable":    article_count >= 8,
        "raw_avg_score":  round(avg_score, 4),
        "delta_1d_proxy": delta_proxy,
    }


def _normalize_related_sentiment(related_sentiment: dict) -> dict:
    result = {}
    for co, data in related_sentiment.items():
        art_count = data.get("article_count", 0)
        avg_score = data.get("avg_score", 0.0)
        if art_count < 2:
            result[co] = {
                "z_score": 0.0, "article_count": art_count,
                "is_reliable": False, "label": data.get("label", "neutral"),
            }
            continue
        pos = data.get("positive", 0)
        neg = data.get("negative", 0)
        neu = data.get("neutral_count", 0)
        approx = [1.0] * pos + [-1.0] * neg + [0.0] * neu
        if len(approx) >= 2:
            mu    = sum(approx) / len(approx)
            sigma = math.sqrt(sum((s - mu) ** 2 for s in approx) / len(approx))
            z     = round((avg_score - mu) / (sigma + 0.001), 4)
        else:
            z = 0.0
        result[co] = {
            "z_score": z, "article_count": art_count,
            "is_reliable": art_count >= 5,
            "label": data.get("label", "neutral"),
        }
    return result


# ── 5 Alpha Formulas ───────────────────────────────────────────────────────────

def _alpha1_fdm(tv: dict) -> dict:
    """Alpha 1 — Flow-Driven Momentum (FDM)"""
    roc1_adj = _safe(tv.get("roc1_adjusted", 0.0))
    vol_surge = _safe(tv.get("vol_surge", 1.0))
    
    raw = roc1_adj * vol_surge * 0.5
    value = math.tanh(raw)
    
    thr = 0.10
    sig = "TĂNG" if value > thr else "GIẢM" if value < -thr else "TRUNG TÍNH"

    return {
        "id": 1,
        "name": "Flow-Driven Momentum (FDM)",
        "type": "Cú hích T+1 (Tiếp diễn)",
        "formula": "Tanh( ROC(1)_adj × Vol_Surge × 0.5 )",
        "horizon": "—",
        "value": round(value, 4),
        "signal": sig,
        "components": {
            "roc1_adjusted": round(roc1_adj, 4),
            "vol_surge": round(vol_surge, 4),
            "raw_momentum": round(raw, 4),
        },
        "interpretation": (
            f"ROC(1) hiệu chỉnh={roc1_adj:+.2f}, Đột biến Vol={vol_surge:.2f}x. "
            f"{'Xung lực tăng mạnh có thể kéo dài sang nến T+1' if value > thr else 'Áp lực bán mạnh dự báo nến T+1 giảm' if value < -thr else 'Dòng tiền không rõ ràng'}."
        ),
    }


def _alpha2_sfa(sn: dict, tv: dict) -> dict:
    """Alpha 2 — Sentiment-Flow Asymmetry (SFA)"""
    z_sent = _safe(sn.get("z_score", 0.0))
    is_reliable = sn.get("is_reliable", False)
    roc1_adj = _safe(tv.get("roc1_adjusted", 0.0))
    macd_hist = _safe(tv.get("macd_hist_cur", 0.0))
    
    if is_reliable:
        raw = z_sent * 0.5 + roc1_adj * 0.5
        logic = f"Tin cậy. Z_Sent={z_sent:+.2f}, ROC_adj={roc1_adj:+.2f}."
    else:
        z_macd = math.tanh(macd_hist / (tv.get("close_0", 1.0) * 0.005)) * 1.5 
        raw = z_macd + roc1_adj * 0.5
        logic = f"Backtest/Sentiment yếu. Dùng Proxy MACD_Hist={macd_hist:+.4f} (Z~{z_macd:+.2f}) và ROC_adj={roc1_adj:+.2f}."

    value = math.tanh(raw)
    thr = 0.10
    sig = "TĂNG" if value > thr else "GIẢM" if value < -thr else "TRUNG TÍNH"

    return {
        "id": 2,
        "name": "Sentiment-Flow (SFA) / Proxy",
        "type": "Cú hích T+1 (Tiếp diễn / Phân kỳ)",
        "formula": "Tanh( Z_Sent×0.5 + ROC_adj×0.5 ) hoặc Proxy MACD_Hist",
        "horizon": "—",
        "value": round(value, 4),
        "signal": sig,
        "components": {
            "z_sent": round(z_sent, 4),
            "is_reliable": is_reliable,
            "roc1_adjusted": round(roc1_adj, 4),
            "macd_hist_cur": round(macd_hist, 6),
        },
        "interpretation": f"{logic} → Cân bằng lực lượng cho T+1: Value={value:+.4f}.",
    }


def _alpha3_lvr(tv: dict) -> dict:
    """Alpha 3 — Liquidity Void Reversion (LVR)"""
    z_close_dev5 = _safe(tv.get("zscore_close_dev5", 0.0))
    
    raw = -1.0 * z_close_dev5 * 0.8
    value = math.tanh(raw)

    thr = 0.15 
    sig = "TĂNG" if value > thr else "GIẢM" if value < -thr else "TRUNG TÍNH"

    return {
        "id": 3,
        "name": "Liquidity Void Reversion (LVR)",
        "type": "Đảo chiều T+1 (Mean-Reversion)",
        "formula": "Tanh( -0.8 × ZScore( (Close - SMA5)/Close ) )",
        "horizon": "—",
        "value": round(value, 4),
        "signal": sig,
        "components": {
            "zscore_close_dev5": round(z_close_dev5, 4),
            "cur_close_dev5": round(tv.get("cur_close_dev5", 0.0), 6),
        },
        "interpretation": (
            f"Z-Score lệch pha SMA(5)={z_close_dev5:+.2f}. "
            f"{'Giá bị đẩy rớt xa xuống, mồi thanh khoản để bật lại T+1' if value > thr else 'Giá hưng phấn rướn quá khỏi SMA5, rủi ro rũ nền T+1' if value < -thr else 'Dao động bám quanh SMA5, không có khoảng trống.'}"
        ),
    }


def _alpha4_bfe(tv: dict) -> dict:
    """Alpha 4 — Bollinger Squeeze & Flow (BFE)"""
    bb_pct_b = _safe(tv.get("bb_pct_b", 0.5))
    vol_z5 = _safe(tv.get("vol_zscore_5", 0.0))
    
    raw = (bb_pct_b - 0.5) * vol_z5 * 1.5
    value = math.tanh(raw)

    thr = 0.10
    sig = "TĂNG" if value > thr else "GIẢM" if value < -thr else "TRUNG TÍNH"

    return {
        "id": 4,
        "name": "Bollinger Squeeze & Flow (BFE)",
        "type": "Bùng nổ dải Band T+1",
        "formula": "Tanh( (%B - 0.5) × Vol_ZScore(5) × 1.5 )",
        "horizon": "—",
        "value": round(value, 4),
        "signal": sig,
        "components": {
            "bb_pct_b": round(bb_pct_b, 4),
            "vol_zscore_5": round(vol_z5, 4),
        },
        "interpretation": (
            f"BB %B={bb_pct_b:.2f}, Z-Score(Vol, 5)={vol_z5:+.2f}. "
            f"{'Xác nhận bứt phá biên trên cùng Vol' if value > thr else 'Áp lực đè biên dưới cùng Vol' if value < -thr else 'Chưa có sự ép biên rõ ràng'}"
        ),
    }


def _alpha5_ofe(tv: dict) -> dict:
    """Alpha 5 — Order Flow Exhaustion (OFE)"""
    roc1_adj = _safe(tv.get("roc1_adjusted", 0.0))
    close_pos = _safe(tv.get("close_pos", 0.0)) 
    
    raw = roc1_adj * close_pos * 3.0
    value = math.tanh(raw)

    thr = 0.10
    sig = "TĂNG" if value > thr else "GIẢM" if value < -thr else "TRUNG TÍNH"

    return {
        "id": 5,
        "name": "Order Flow Exhaustion (OFE)",
        "type": "Nén xả nội phiên T+1",
        "formula": "Tanh( ROC_adj × Vị_trí_đóng_nến × 3.0 )",
        "horizon": "—",
        "value": round(value, 4),
        "signal": sig,
        "components": {
            "roc1_adjusted": round(roc1_adj, 4),
            "close_pos": round(close_pos, 4),
        },
        "interpretation": (
            f"Động lực qua ngày ROC_adj={roc1_adj:+.2f}, Vị trí đóng nến (Pos)={close_pos:+.2f}. "
            f"{'Sự ủng hộ giá đóng cửa trên cao' if value > thr else 'Râu nến ngược hướng giá, đuối dòng tiền' if value < -thr else 'Thân nến trung bình'}"
        ),
    }


# ── Compute Dynamic Alphas ──────────────────────────────────────────────────

def _compute_all_alphas(
    kline_data: dict,
    sentiment_norm: dict,
    related_norm: dict,
    symbol: str,
    interval: str = "1d"
) -> Tuple[List[dict], dict]:
    """
    Computes top-5 dynamic alphas or falls back to original 5.
    """
    tv = _extract_tech_vars(kline_data)
    
    # 1. Try dynamic selection
    try:
        top_alphas = select_top_alphas(symbol, interval)
    except Exception as e:
        print(f"[AlphaAgent] Lỗi select_top_alphas: {e}")
        top_alphas = []

    if top_alphas:
        print(f"[AlphaAgent] Sử dụng {len(top_alphas)} dynamic alphas cho {symbol}")
        # Convert kline_data to DataFrame for alpha_compare functions
        df_base = pd.DataFrame(kline_data)
        # Ensure numeric
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            if col in df_base.columns:
                df_base[col] = pd.to_numeric(df_base[col], errors="coerce").fillna(0.0)
        
        d_features = alpha_compare.build_features(df_base)
        
        dynamic_results = []
        for i, a_meta in enumerate(top_alphas):
            aid = a_meta["alpha_id"]
            handler = a_meta["handler"]
            
            # Execute alpha on the dataframe
            try:
                series = handler(d_features)
                val = float(series.iloc[-1])
                if math.isnan(val) or math.isinf(val): val = 0.0
            except Exception as e:
                print(f"[AlphaAgent] Lỗi tính alpha {aid}: {e}")
                val = 0.0
            
            # Try to get metadata from NEW_ALPHA_TEMPLATES in alpha_compare
            template = alpha_compare.NEW_ALPHA_TEMPLATES.get(aid, {})
            name = template.get("name", a_meta["description"])
            a_type = template.get("type", "Quantitative Alpha")
            formula = template.get("formula", f"Adapted {aid}")
            interp_base = template.get("interp", a_meta["description"])
            
            thr = 0.10
            sig = "TĂNG" if val > thr else "GIẢM" if val < -thr else "TRUNG TÍNH"
            
            dynamic_results.append({
                "id": i + 1,
                "name": name,
                "type": a_type,
                "formula": formula,
                "horizon": "—",
                "value": round(val, 4),
                "signal": sig,
                "components": {
                    "composite_score": round(a_meta["composite_score"], 4),
                    "ic": round(a_meta["metrics"]["ic"], 4),
                    "accuracy": f"{a_meta['metrics']['accuracy']:.1%}"
                },
                "interpretation": f"{interp_base}. (IC={a_meta['metrics']['ic']:+.3f}, Acc={a_meta['metrics']['accuracy']:.1%})"
            })
        return dynamic_results, tv
    
    # 2. Fallback to original 5
    print("[AlphaAgent] Fallback về 5 alpha mặc định.")
    alphas = [
        _alpha1_fdm(tv),
        _alpha2_sfa(sentiment_norm, tv),
        _alpha3_lvr(tv),
        _alpha4_bfe(tv),
        _alpha5_ofe(tv),
    ]
    return alphas, tv


# ── Report builder ─────────────────────────────────────────────────────────────

def _build_alpha_report(
    alphas: List[dict], tv: dict, sn: dict, stock_name: str
) -> str:
    """
    Xây dựng báo cáo markdown cho 5 alpha.
    """
    sent_reliable_label = "✅ Đáng tin" if sn.get("is_reliable") else "⚠️ Ít bài"

    lines = [
        f"## 5 Alpha Factor — {stock_name}\n",
        "| # | Alpha | Loại | Giá trị | Tín hiệu | Horizon |",
        "|---|-------|------|---------|----------|---------|",
    ]
    for a in alphas:
        icon = "▲ TĂNG" if a["signal"] == "TĂNG" else "▼ GIẢM" if a["signal"] == "GIẢM" else "◆ Trung tính"
        lines.append(
            f"| {a['id']} | **{a['name']}** | {a['type']} "
            f"| **{a['value']}** | {icon} | {a['horizon']} |"
        )

    lines += [
        "",
        f"**Sentiment:** {sn.get('article_count', 0)} bài — {sent_reliable_label} | "
        f"Z-score: {sn.get('z_score', 0):+.4f} | "
        f"**Volume:** {'thực' if tv.get('has_volume') else 'proxy range'}",
        "",
        "---\n",
    ]

    for a in alphas:
        icon = "🟢" if a["signal"] == "TĂNG" else "🔴" if a["signal"] == "GIẢM" else "⚪"
        lines += [
            f"### Alpha {a['id']}: {a['name']}",
            f"**Loại:** {a['type']} | **Horizon:** {a['horizon']}",
            "",
            "**Công thức đầy đủ:**",
            f"`{a['formula']}`",
            "",
            "**Các bước tính toán:**",
        ]
        for k, v in a.get("components", {}).items():
            lines.append(f"- `{k}` = **{v}**")
            
        lines += [
            "",
            f"**Diễn giải:** *{a['interpretation']}*",
            "",
            f"**Kết quả cuối cùng:** `{a['value']}`",
            f"**Tín hiệu:** {icon} **{a['signal']}**",
            "",
            "---",
            ""
        ]

    return "\n".join(lines)


# ── LLM reasoning ─────────────────────────────────────────────────────────────

def _llm_reason(llm, report_md: str, sentiment_md: str, stock_name: str, horizon_label: str) -> str:
    """
    Yêu cầu LLM đọc 5 alpha và bản tin tâm lý để đưa ra nhận xét tổng hợp.
    """
    prompt = f"""Bạn là chuyên gia phân tích định lượng và dòng tiền chuyên dự đoán {horizon_label}.
Dưới đây là kết quả tính toán 5 alpha factor và bản tóm tắt tâm lý thị trường cho **{stock_name}**.

### 📊 KẾT QUẢ ALPHA FACTORS
{report_md}

### 🌍 TÂM LÝ THỊ TRƯỜNG & TIN TỨC
{sentiment_md}

Hãy kết hợp cả dữ liệu định lượng và tin tức để:
1. Nhận xét ngắn (1-2 câu) về xung lực dòng hiện tại.
2. Tổng hợp góc nhìn: Dòng tiền và Tâm lý đang đồng thuận hay mâu thuẫn? kịch bản nào cho {horizon_label} có xác suất cao hơn?
3. Chỉ ra rủi ro hoặc cơ hội tiềm ẩn từ tin tức mà các alpha kỹ thuật có thể chưa phản ánh hết.

KHÔNG phân tích dài dòng. Chỉ suy luận tự nhiên từ các con số để chốt cái nhìn về {horizon_label}.
Trả lời bằng tiếng Việt, giữ nguyên định dạng markdown."""

    try:
        resp = _invoke_with_retry(
            llm.invoke,
            [SystemMessage(content=f"Bạn là chuyên gia định lượng chứng khoán Việt Nam, dự báo {horizon_label}."),
             HumanMessage(content=prompt)],
        )
        return resp.content or report_md
    except Exception as e:
        print(f"[AlphaAgent] LLM reasoning lỗi: {e}")
        return report_md


# ── Sentinel constants ─────────────────────────────────────────────────────────

_NEUTRAL_SENTIMENT_DATA = {}
_BACKTEST_NO_CACHE_REPORT = (
    "## Sentiment — Backtest Mode (no cache)\n\n"
    "Backtest mode: Sentiment = neutral (0). Alpha thuần kỹ thuật."
)


# ── Main agent factory ─────────────────────────────────────────────────────────

def create_alpha_agent(llm):
    """Alpha Agent v6 — 5 alphas, Python computes, LLM reasons freely."""

    def alpha_agent_node(state):
        stock_name       = state["stock_name"]
        time_frame       = state["time_frame"]
        kline_data       = state["kline_data"]
        is_backtest      = state.get("is_backtest", False)

        # ── Step 1: Fetch sentiment ────────────────────────────────────────
        if not is_backtest:
            print(f"[AlphaAgent] Production — crawl sentiment cho {stock_name}...")
            try:
                from sentiment_agent import run_sentiment_for_alpha
                sentiment_data, sentiment_report = run_sentiment_for_alpha(
                    llm, stock_name, time_frame
                )
            except Exception as e:
                print(f"[AlphaAgent] Lỗi sentiment: {e}")
                sentiment_data, sentiment_report = {}, f"Lỗi sentiment: {e}"
        else:
            sentiment_store = state.get("sentiment_store")
            window_end_date = state.get("window_end_date")
            if sentiment_store is not None and window_end_date:
                print(f"[AlphaAgent] Backtest historical sentiment — {stock_name} @ {window_end_date}")
                try:
                    sentiment_data, sentiment_report = sentiment_store.get_sentiment_at(
                        symbol=stock_name, cutoff_date=window_end_date,
                        llm=llm, window_days=90,
                    )
                except Exception as e:
                    print(f"[AlphaAgent] Lỗi historical sentiment: {e}")
                    sentiment_data   = _NEUTRAL_SENTIMENT_DATA
                    sentiment_report = f"Lỗi: {e}"
            else:
                print(f"[AlphaAgent] Backtest neutral mode — {stock_name}")
                sentiment_data   = _NEUTRAL_SENTIMENT_DATA
                sentiment_report = _BACKTEST_NO_CACHE_REPORT

        # ── Step 2: Normalize sentiment ────────────────────────────────────
        print(f"[AlphaAgent] Chuẩn hóa sentiment và tính biến kỹ thuật...")
        sentiment_norm = _normalize_sentiment_scores(sentiment_data)
        related_norm   = _normalize_related_sentiment(
            sentiment_data.get("related_sentiment", {})
        )

        # ── Step 3: Compute all 5 alphas ───────────────────────────────────
        # ── Horizon động ──────────────────────────────────────────────────
        from static_util import get_forecast_horizon
        hz = get_forecast_horizon(time_frame)
        horizon_label = hz["horizon_short"]
        
        # Map time_frame display to interval key
        interval_map = {"1 ngày": "1d", "1 tuần": "1w", "1 tháng": "1mo", "1 giờ": "1h", "15 phút": "15m", "1 phút": "1m"}
        interval_key = interval_map.get(time_frame, "1d")

        print(f"[AlphaAgent] Tính 5 alpha factor ({horizon_label})...")
        alphas, tech_vars = _compute_all_alphas(kline_data, sentiment_norm, related_norm, symbol=stock_name, interval=interval_key)
        # Inject động horizon vào từng alpha
        for a in alphas:
            a["horizon"] = horizon_label

        n_long  = sum(1 for a in alphas if a["signal"] == "TĂNG")
        n_short = sum(1 for a in alphas if a["signal"] == "GIẢM")
        print(f"[AlphaAgent] TĂNG={n_long} GIẢM={n_short} TRUNG TÍNH={5-n_long-n_short}")

        # ── Step 4: Build base report ──────────────────────────────────────
        base_report = _build_alpha_report(alphas, tech_vars, sentiment_norm, stock_name)

        # ── Step 5: LLM reasons freely (Now with Sentiment context) ────────
        llm_reasoning = _llm_reason(llm, base_report, sentiment_report, stock_name, horizon_label)
        
        n_neu = 5 - n_long - n_short
        if n_long > n_short:
            consensus = "TĂNG"
        elif n_short > n_long:
            consensus = "GIẢM"
        else:
            consensus = "TRUNG TÍNH"

        alpha_report = (
            f"{base_report}\n"
            f"### 🤖 Chuyên gia định lượng nhận xét\n"
            f"{llm_reasoning}\n\n"
            f"**TỔNG HỢP: {consensus} ({n_long} TĂNG / {n_short} GIẢM / {n_neu} TRUNG TÍNH)**\n"
        )

        print(f"[AlphaAgent] Hoàn thành ({len(alpha_report)} ký tự).")

        sentiment_data_ext = {
            **sentiment_data,
            "sentiment_norm": sentiment_norm,
            "related_norm":   related_norm,
            "tech_vars":      tech_vars,
            "alpha_results":  alphas,
        }

        from langchain_core.messages import AIMessage
        dummy_msg = AIMessage(content=alpha_report)

        return {
            "messages":         state.get("messages", []) + [dummy_msg],
            "alpha_report":     alpha_report,
            "sentiment_report": sentiment_report,
            "sentiment_data":   sentiment_data_ext,
            "sentiment_norm":   sentiment_norm,
        }

    return alpha_agent_node