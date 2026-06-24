import base64
import io

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import mplfinance as mpf
import numpy as np
import pandas as pd

from utils import color_style as color
from utils.graph_util import (
    fit_trendlines_high_low,
    fit_trendlines_single,
    get_line_points,
    split_line_into_segments,
)

matplotlib.use("Agg")

# ── Chart configuration ────────────────────────────────────────────────────────
CANDLE_COUNT   = 45          # default; overridden per-timeframe at call site
TICK_EVERY     = 5           # default x-axis label interval
DATE_FMT       = "%Y-%m-%d"  # default date format
FIGSIZE        = (12, 6)
DPI_SAVE       = 150
LABEL_FONTSIZE = 8

# Per-timeframe chart overrides
_TF_CHART = {
    "1m":  {"candles": 120, "date_fmt": "%H:%M",       "tick_every": 12},
    "5m":  {"candles": 78,  "date_fmt": "%d/%m %H:%M", "tick_every": 8},
    "15m": {"candles": 60,  "date_fmt": "%d/%m %H:%M", "tick_every": 6},
    "30m": {"candles": 50,  "date_fmt": "%d/%m %H:%M", "tick_every": 5},
    "1h":  {"candles": 45,  "date_fmt": "%d/%m %H:%M", "tick_every": 5},
    "1H":  {"candles": 45,  "date_fmt": "%d/%m %H:%M", "tick_every": 5},
    "1d":  {"candles": 45,  "date_fmt": "%Y-%m-%d",    "tick_every": 5},
    "1w":  {"candles": 52,  "date_fmt": "%Y-%m-%d",    "tick_every": 5},
    "1mo": {"candles": 36,  "date_fmt": "%Y-%m",       "tick_every": 4},
}

def _get_tf_chart(timeframe: str) -> dict:
    return _TF_CHART.get(timeframe, _TF_CHART["1d"])


# ── Forecast horizon — Vietnam T+2.5 settlement rules ─────────────────────────

# Display-name → key normalisation
_DISPLAY_TO_KEY = {
    "1 phút": "1m", "5 phút": "5m", "15 phút": "15m", "30 phút": "30m",
    "1 giờ": "1h", "1 ngày": "1d", "1 tuần": "1w", "1 tháng": "1mo",
}


def get_forecast_horizon(time_frame: str) -> dict:
    """
    Trả về thông tin dự báo phù hợp với quy định thanh toán T+2.5 tại Việt Nam.

    Quy tắc:
    ─────────────────────────────────────────────────────────────────────
    Timeframe ngày/tuần/tháng (1d, 1w, 1mo):
      • Cổ phiếu mua ngày T chỉ bán được chiều T+2 → nhà đầu tư chịu
        rủi ro qua ít nhất 3 nến (T, T+1, T+2).
      • Hệ thống dự báo hướng cho "3 phiên tới" (T+2.5).

    Timeframe nội phiên (1m, 5m, 15m, 30m, 1h):
      • Phù hợp cho phái sinh VN30F (T+0 — mua bán ngay).
      • Hoặc để tìm điểm Entry/Exit tối ưu cho cổ phiếu cơ sở.
      • Hệ thống dự báo "nến tiếp theo" (T+1).
    ─────────────────────────────────────────────────────────────────────

    Returns:
        dict with keys:
          horizon_desc      : mô tả đầy đủ (inject vào prompt)
          horizon_short     : nhãn ngắn gọn
          horizon_val       : giá trị cho JSON output (T+1 / T+2.5)
          lookahead_candles : số nến phía trước để backtest xác minh
          note              : ghi chú bổ sung
    """
    tf = time_frame.strip().lower()
    key = _DISPLAY_TO_KEY.get(tf, tf)

    if key in ("1d", "1w", "1mo"):
        return {
            "horizon_desc": (
                "xu hướng 3 phiên giao dịch tiếp theo (T → T+2) "
                "— theo quy định thanh toán T+2.5 trên TTCK Việt Nam"
            ),
            "horizon_short": "T+2.5 (3 phiên)",
            "horizon_val": "T+2.5",
            "lookahead_candles": 3,
            "note": (
                "Cổ phiếu cơ sở mua ngày T chỉ bán được chiều T+2. "
                "Nhà đầu tư chịu rủi ro qua tối thiểu 3 nến."
            ),
        }
    else:
        return {
            "horizon_desc": "nến tiếp theo (T+1)",
            "horizon_short": "T+1 (nến kế tiếp)",
            "horizon_val": "T+1",
            "lookahead_candles": 1,
            "note": (
                "Timeframe ngắn phù hợp cho phái sinh VN30F (T+0) "
                "hoặc tối ưu điểm vào lệnh cổ phiếu cơ sở."
            ),
        }


def _apply_date_xticks(ax, df: pd.DataFrame, date_fmt: str = DATE_FMT, tick_every: int = TICK_EVERY) -> None:
    """
    Set date/time labels every tick_every candles on the x-axis.
    date_fmt controls the strftime format (supports time for intraday).
    """
    n = len(df)
    positions = list(range(0, n, tick_every))
    if (n - 1) not in positions:
        positions.append(n - 1)

    labels = [df.index[i].strftime(date_fmt) for i in positions]

    ax.set_xticks(positions)
    ax.set_xticklabels(labels, rotation=90, ha="center", fontsize=LABEL_FONTSIZE)
    ax.xaxis.set_minor_locator(mticker.NullLocator())
    ax.xaxis.grid(True, which="major", linestyle="--", linewidth=0.4, alpha=0.45)
    ax.set_axisbelow(True)


def _parse_datetime(df: pd.DataFrame) -> pd.DataFrame:
    """Parse Datetime column into DatetimeIndex with format fallback."""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            df.index = pd.to_datetime(df["Datetime"], format=fmt)
            return df
        except (ValueError, KeyError):
            continue
    df.index = pd.to_datetime(df["Datetime"])
    return df


# ── generate_kline_image ───────────────────────────────────────────────────────

def generate_kline_image(kline_data, timeframe: str = "1d") -> dict:
    """
    Generate a candlestick (K-line) chart from OHLCV data.
    timeframe controls candle count, date format, and tick spacing.
    """
    cfg = _get_tf_chart(timeframe)
    candle_count = cfg["candles"]
    date_fmt     = cfg["date_fmt"]
    tick_every   = cfg["tick_every"]

    df = pd.DataFrame(kline_data).tail(candle_count).copy()
    df.to_csv("record.csv", index=False, date_format="%Y-%m-%d %H:%M:%S")
    df = _parse_datetime(df)

    fig, axlist = mpf.plot(
        df[["Open", "High", "Low", "Close"]],
        type="candle",
        style=color.my_color_style,
        figsize=FIGSIZE,
        returnfig=True,
        block=False,
    )

    ax = axlist[0]
    ax.set_ylabel("Price", fontweight="normal", fontsize=10)
    ax.set_xlabel("Date/Time",  fontweight="normal", fontsize=10)

    _apply_date_xticks(ax, df, date_fmt=date_fmt, tick_every=tick_every)

    ax.set_title(
        f"Candlestick Chart  ({len(df)} candles, {timeframe})  —  "
        f"{df.index[0].strftime(date_fmt)} to {df.index[-1].strftime(date_fmt)}",
        fontsize=9, pad=5,
    )

    fig.savefig("kline_chart.png", dpi=DPI_SAVE, bbox_inches="tight", pad_inches=0.2)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=DPI_SAVE, bbox_inches="tight", pad_inches=0.2)
    plt.close(fig)
    buf.seek(0)
    img_b64 = base64.b64encode(buf.read()).decode("utf-8")

    return {
        "pattern_image": img_b64,
        "pattern_image_description": (
            f"Candlestick chart — {len(df)} {timeframe} candles, "
            f"label every {tick_every} bars, horizontal."
        ),
    }


# ── generate_trend_image ───────────────────────────────────────────────────────

def generate_trend_image(kline_data, timeframe: str = "1d") -> dict:
    """
    Generate a candlestick chart with support/resistance trendlines.
    timeframe controls candle count, date format, and tick spacing.
    """
    cfg = _get_tf_chart(timeframe)
    candle_count = cfg["candles"]
    date_fmt     = cfg["date_fmt"]
    tick_every   = cfg["tick_every"]

    data    = pd.DataFrame(kline_data)
    candles = data.tail(candle_count).copy()

    candles["Datetime"] = pd.to_datetime(candles["Datetime"])
    candles.set_index("Datetime", inplace=True)

    # ── trendline computation (unchanged from original) ──────────────────────
    support_coefs_c, resist_coefs_c = fit_trendlines_single(candles["Close"])
    support_coefs,   resist_coefs   = fit_trendlines_high_low(
        candles["High"], candles["Low"], candles["Close"]
    )

    n              = len(candles)
    support_line_c = support_coefs_c[0] * np.arange(n) + support_coefs_c[1]
    resist_line_c  = resist_coefs_c[0]  * np.arange(n) + resist_coefs_c[1]
    support_line   = support_coefs[0]   * np.arange(n) + support_coefs[1]
    resist_line    = resist_coefs[0]    * np.arange(n) + resist_coefs[1]

    s_seq  = get_line_points(candles, support_line)
    r_seq  = get_line_points(candles, resist_line)
    s_seq2 = get_line_points(candles, support_line_c)
    r_seq2 = get_line_points(candles, resist_line_c)

    s_segments  = split_line_into_segments(s_seq)
    r_segments  = split_line_into_segments(r_seq)
    s2_segments = split_line_into_segments(s_seq2)
    r2_segments = split_line_into_segments(r_seq2)

    all_segments = s_segments + r_segments + s2_segments + r2_segments
    seg_colors   = (
        ["white"] * len(s_segments)
        + ["white"] * len(r_segments)
        + ["blue"]  * len(s2_segments)
        + ["red"]   * len(r2_segments)
    )

    apds = [
        mpf.make_addplot(support_line_c, color="blue", width=1.2, label="Support"),
        mpf.make_addplot(resist_line_c,  color="red",  width=1.2, label="Resistance"),
    ]

    # ── plot ─────────────────────────────────────────────────────────────────
    fig, axlist = mpf.plot(
        candles,
        type="candle",
        style=color.my_color_style,
        addplot=apds,
        alines=dict(alines=all_segments, colors=seg_colors, linewidths=0.8),
        returnfig=True,
        figsize=FIGSIZE,
        block=False,
    )

    ax = axlist[0]
    ax.set_ylabel("Price", fontweight="normal", fontsize=10)
    ax.set_xlabel("Date/Time", fontweight="normal", fontsize=10)

    _apply_date_xticks(ax, candles, date_fmt=date_fmt, tick_every=tick_every)

    ax.set_title(
        f"Trend Chart  ({n} candles, {timeframe})  —  "
        f"Blue = Support  |  Red = Resistance",
        fontsize=9, pad=5,
    )

    ax.legend(
        ["Support (close)", "Resistance (close)"],
        loc="upper left", fontsize=9, framealpha=0.7,
    )

    # ── save local file ──
    fig.savefig(
        "trend_graph.png", format="png",
        dpi=DPI_SAVE, bbox_inches="tight", pad_inches=0.2,
    )

    # ── encode to base64 ──
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=DPI_SAVE, bbox_inches="tight", pad_inches=0.2)
    plt.close(fig)
    buf.seek(0)
    img_b64 = base64.b64encode(buf.read()).decode("utf-8")

    return {
        "trend_image": img_b64,
        "trend_image_description": (
            f"Trend chart — {n} {timeframe} candles, "
            f"blue=support, red=resistance, "
            f"label every {tick_every} bars, horizontal."
        ),
    }


# ── generate_backtest_summary_chart ──────────────────────────────────────────

def generate_backtest_summary_chart(summary: dict, output_path: str) -> None:
    """
    Tạo biểu đồ so sánh hiệu quả Backtest:
    - Trên: Lợi nhuận gộp mô phỏng (Cumulative P&L %)
    - Dưới: Số lần dự đoán đúng lũy tiến.
    """
    try:
        test_points = summary.get("test_points", [])
        if not test_points:
            return

        ids = [tp["test_id"] for tp in test_points]
        pnl_f = [tp.get("pnl_full", 0.0) for tp in test_points]
        pnl_n = [tp.get("pnl_no_alpha", 0.0) for tp in test_points]
        
        # Tính số lần đúng lũy tiến
        correct_f = []
        count_f = 0
        for tp in test_points:
            if tp.get("correct_full"): count_f += 1
            correct_f.append(count_f)
            
        correct_n = []
        count_n = 0
        for tp in test_points:
            if tp.get("correct_no_alpha"): count_n += 1
            correct_n.append(count_n)

        # Draw
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
        plt.subplots_adjust(hspace=0.25)

        # Subplot 1: P&L
        ax1.plot(ids, pnl_f, marker='o', color='#2563eb', linewidth=2, label=f"Full System ({pnl_f[-1]:+.1f}%)")
        ax1.plot(ids, pnl_n, marker='s', color='#16a34a', linewidth=2, linestyle='--', label=f"No-Alpha ({pnl_n[-1]:+.1f}%)")
        ax1.axhline(y=0, color='black', linestyle='-', linewidth=0.8, alpha=0.3)
        ax1.set_title(f"Cumulative Simulated P&L - {summary.get('symbol')}", fontsize=12, fontweight='bold', pad=10)
        ax1.set_ylabel("P&L (%)", fontsize=10)
        ax1.legend(loc="upper left", fontsize=9)
        ax1.grid(True, linestyle=':', alpha=0.6)

        # Subplot 2: Correctness count
        ax2.step(ids, correct_f, where='post', color='#2563eb', linewidth=2, label=f"Full Correct ({count_f})")
        ax2.step(ids, correct_n, where='post', color='#16a34a', linewidth=2, linestyle='--', label=f"No-Alpha Correct ({count_n})")
        ax2.set_title("Cumulative Correct Predictions", fontsize=11, pad=8)
        ax2.set_xlabel("Test Point ID", fontsize=10)
        ax2.set_ylabel("Correct Count", fontsize=10)
        ax2.legend(loc="upper left", fontsize=9)
        ax2.grid(True, linestyle=':', alpha=0.6)

        # X-axis cleanup
        ax2.set_xticks(ids)

        # Footer info
        pnl_lift = summary.get('pnl_lift', (pnl_f[-1] - pnl_n[-1]) if pnl_f and pnl_n else 0.0)
        plt.figtext(0.5, 0.02, 
                    f"Backtest: {summary.get('symbol')} | {len(ids)} tests | "
                    f"Alpha Lift: {summary.get('alpha_lift', 0.0):+.1f}% | "
                    f"P&L Lift: {pnl_lift:+.1f}%", 
                    ha="center", fontsize=8, color="gray", style='italic')

        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
    except Exception as e:
        print(f"[static_util] Error drawing summary chart: {e}")