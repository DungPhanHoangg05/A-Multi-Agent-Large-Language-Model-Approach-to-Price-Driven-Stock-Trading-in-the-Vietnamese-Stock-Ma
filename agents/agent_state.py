from typing import Annotated, Any, Dict, List, TypedDict

from langchain_core.messages import BaseMessage


class IndicatorAgentState(TypedDict):
    """State type for the multi-agent trading system."""

    kline_data: Annotated[
        dict, "OHLCV dictionary used for computing technical indicators"
    ]
    time_frame: Annotated[str, "time period for k line data provided"]
    stock_name: Annotated[dict, "stock name for prompt"]
    is_backtest: Annotated[bool, "Cờ nhận diện chế độ Backtest để chặn crawler mạng bên ngoài"]

    # ── Indicator Agent — oscillator / momentum ────────────────────────────────
    rsi: Annotated[List[float], "Relative Strength Index values"]
    macd: Annotated[List[float], "MACD line values"]
    macd_signal: Annotated[List[float], "MACD signal line values"]
    macd_hist: Annotated[List[float], "MACD histogram values"]
    stoch_k: Annotated[List[float], "Stochastic Oscillator %K values"]
    stoch_d: Annotated[List[float], "Stochastic Oscillator %D values"]
    roc: Annotated[List[float], "Rate of Change values"]
    willr: Annotated[List[float], "Williams %R values"]

    # ── Indicator Agent — volatility ───────────────────────────────────────────
    atr: Annotated[List[float], "Average True Range values"]
    atr_pct: Annotated[List[float], "ATR as percentage of Close price (ATR/Close*100)"]

    # ── Indicator Agent — Bollinger Bands ──────────────────────────────────────
    bb_upper: Annotated[List[float], "Bollinger Band upper line values"]
    bb_middle: Annotated[List[float], "Bollinger Band middle (MA20) values"]
    bb_lower: Annotated[List[float], "Bollinger Band lower line values"]
    bb_pct_b: Annotated[
        List[float],
        "Bollinger %B — price position in band: >1=above upper, <0=below lower",
    ]
    bb_bandwidth: Annotated[
        List[float],
        "Bollinger Bandwidth — (upper-lower)/middle*100, high=volatile, low=squeeze",
    ]

    # ── Indicator Agent — trend strength ──────────────────────────────────────
    adx: Annotated[List[float], "Average Directional Index — trend strength (>25=strong)"]
    plus_di: Annotated[List[float], "+DI directional indicator"]
    minus_di: Annotated[List[float], "-DI directional indicator"]

    indicator_report: Annotated[
        str, "Final indicator agent summary report to be used by downstream agents"
    ]

    # ── Alpha Agent ────────────────────────────────────────────────────────────
    alpha_report: Annotated[
        str, "5 alpha factor formulas generated for the stock, used by downstream agents"
    ]

    # ── Pattern Agent ──────────────────────────────────────────────────────────
    pattern_image: Annotated[
        str, "Base64-encoded K-line chart for pattern recognition agent use"
    ]
    pattern_image_filename: Annotated[
        str, "Local file path to saved K-line chart image"
    ]
    pattern_image_description: Annotated[
        str, "Brief description of the generated K-line image"
    ]
    pattern_report: Annotated[
        str, "Final pattern agent summary report to be used by downstream agents"
    ]

    # ── Trend Agent ────────────────────────────────────────────────────────────
    trend_image: Annotated[
        str,
        "Base64-encoded trend-annotated candlestick chart for trend recognition agent use",
    ]
    trend_image_filename: Annotated[
        str, "Local file path to saved trendline-enhanced K-line chart image"
    ]
    trend_image_description: Annotated[
        str,
        "Brief description of the chart, including support/resistance lines and visual characteristics",
    ]
    trend_report: Annotated[
        str,
        "Final trend analysis summary, describing structure, directional bias, and technical observations",
    ]

    # ── Sentiment Agent ────────────────────────────────────────────────────────
    sentiment_report: Annotated[
        str,
        "Sentiment analysis report from CafeF news — includes target stock sentiment, "
        "related companies, and market sentiment summary",
    ]
    sentiment_data: Annotated[
        Dict[str, Any],
        "Raw sentiment data dict: {main_sentiment, scored_articles, related_companies, related_sentiment}",
    ]
    sentiment_norm: Annotated[
        Dict[str, Any],
        "Normalized sentiment variables for alpha formulas: "
        "{z_score, net_polarity, conviction, rel_sentiment, sentiment_skew}. "
        "These are bias-corrected and safe to use directly in quantitative formulas.",
    ]

    # ── Final analysis and messaging context ───────────────────────────────────
    analysis_results: Annotated[str, "Computed result of the analysis or decision"]
    messages: Annotated[
        List[BaseMessage], "List of chat messages used in LLM prompt construction"
    ]
    decision_prompt: Annotated[str, "decision prompt for reflection"]
    final_trade_decision: Annotated[
        str, "Final LONG or SHORT decision made after analyzing all agent reports"
    ]