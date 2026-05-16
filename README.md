# QuantAgent VN 🇻🇳

**A multi-agent AI system for Vietnamese stock market technical analysis and trading decision support.**

Based on [QuantAgent](https://github.com/y-research-sbu/QuantAgent) and the paper [*QuantAgent: A Multi-Agent Framework for Quantitative Financial Analysis*](https://arxiv.org/pdf/2509.09995), adapted and extended for the Vietnamese equity market (HOSE, HNX, UPCOM) with Vietnam-specific regulations (T+2.5 settlement), sentiment analysis via CafeF news and ViSoBERT, and a 101-formula alpha factor engine.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Agent Pipeline](#agent-pipeline)
- [Key Features](#key-features)
- [Tech Stack](#tech-stack)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Backtest Engine](#backtest-engine)
- [Alpha Factor System](#alpha-factor-system)
- [Project Structure](#project-structure)
- [Disclaimer](#disclaimer)

---

## Overview

QuantAgent VN orchestrates five specialized AI agents that independently analyze a stock and pass their findings to a final **Decision Agent**, which synthesizes all reports into a single **LONG** or **SHORT** trade recommendation with a risk/reward ratio and justification.

The system accounts for Vietnam's **T+2.5** settlement rule — any equity purchased on day T cannot be sold until the afternoon of day T+2, so forecasts are framed as "3-session ahead" directional calls rather than next-candle signals.

---

## Architecture

```
Real-Time Data (vnstock / entrade)
          │
          ▼
┌─────────────────────────────────────────────────────────┐
│                    LangGraph Pipeline                   │
│                                                         │
│  Indicator Agent ──► Alpha Agent ──► Pattern Agent      │
│        (MACD/RSI/…)   (sentiment+α)   (candlestick)     │
│                                            │            │
│                                       Trend Agent       │
│                                    (support/resistance) │
│                                            │            │
│                                    Decision Agent       │
│                                    (LONG / SHORT)       │
└─────────────────────────────────────────────────────────┘
          │
          ▼
    Web UI (Flask)  /  Backtest Engine
```

All text/tool agents run on **`llama-3.1-8b-instant`** (Groq). Vision agents (Pattern, Trend) use **`meta-llama/llama-4-scout-17b-16e-instruct`** for chart image analysis.

---

## Agent Pipeline

| Step | Agent | Model | Responsibility |
|------|-------|-------|----------------|
| 1 | **Indicator Agent** | llama-3.1-8b-instant | Computes MACD, RSI, Stochastic, Williams %R, ROC via TA-Lib; classifies signals in Python and passes classified results to the LLM for narrative interpretation only |
| 2 | **Alpha Agent** | llama-3.1-8b-instant | Crawls CafeF news, scores with ViSoBERT sentiment model, normalises scores, computes 5 quantitative alpha factors, and has the LLM synthesise a verdict |
| 3 | **Pattern Agent** | llama-4-scout (vision) | Receives a base64 candlestick chart image; identifies classical patterns (head-and-shoulders, flags, wedges, etc.) and directional bias |
| 4 | **Trend Agent** | llama-4-scout (vision) | Receives a trendline-annotated chart; identifies support/resistance, slope, and breakout/breakdown signals |
| 5 | **Decision Agent** | llama-3.1-8b-instant | Reads all four reports, applies chain-of-thought reasoning, and emits a structured JSON verdict: `decision`, `confidence`, `risk_reward_ratio`, `evidence_for`, `evidence_against`, `justification` |

The pipeline is built with **LangGraph** (`StateGraph`) and state is typed via `IndicatorAgentState` (TypedDict).

---

## Key Features

### Multi-Agent Reasoning
- Each agent works independently — no agent sees another's reasoning, only its final report — mirroring how a real trading desk operates.
- Decision Agent is forced to choose **LONG or SHORT** (no "neutral" cop-out) to ensure actionable output.

### Vietnam-Specific Adaptations
- **T+2.5 settlement** awareness: forecast horizon is dynamically set to "3 sessions ahead" for daily/weekly/monthly frames, "next candle" for intraday.
- **CafeF** news crawling with article-date extraction for temporally honest backtesting.
- **ViSoBERT** (`5CD-AI/Vietnamese-Sentiment-visobert`) for Vietnamese-language sentiment classification; lexicon fallback when the model is unavailable.
- **vnstock** integration (VCI / MSN / KBS sources) plus entrade REST fallback for intraday data.
- **VN price-limit** aware synthetic data generator (±7%).

### Alpha Factor Engine (`alpha_compare.py`)
- **87 candidate alphas** total: 5 original factors + 79 adapted WorldQuant-101 formulaic alphas + 3 VN-custom factors.
- Walk-forward backtest evaluates every candidate with IC (Spearman), directional accuracy, long-only accuracy (relevant because short-selling is restricted in Vietnam), and Sharpe ratio.
- Composite score: `0.35 × |IC| + 0.30 × Acc + 0.20 × LongAcc + 0.15 × Sharpe`.
- `AlphaSelector` auto-selects the **top-5** alphas for the given symbol and timeframe before each analysis session.

### Walk-Forward Backtest Engine
- Compares **Full System** (all 5 agents) vs. **No-Alpha System** (3 agents, no sentiment or alpha) across N rolling windows.
- Metrics: accuracy, long win-rate, short win-rate, alpha lift (pp improvement in accuracy), simulated P&L.
- Historical sentiment is replayed from a cached CafeF store (`BacktestSentimentStore`) to avoid data leakage — only news published before the window end date is used.
- Real-time progress via polling API; live Chart.js visualisation in the browser.

### Web Interface
- Flask backend with job-queue pattern (background threads, SSE-style polling).
- Three pages: main analysis form (`/demo`), results (`/output`), and backtest dashboard (`/backtest`).
- Symbol list auto-loaded from vnstock / VNDirect / SSI REST APIs with 300+ hardcoded fallback symbols.

---

## Tech Stack

| Layer | Library / Service |
|-------|-------------------|
| Orchestration | [LangGraph](https://github.com/langchain-ai/langgraph) |
| LLM inference | [Groq API](https://console.groq.com) (free tier) |
| LLM wrappers | LangChain (`langchain-groq`) |
| Technical indicators | [TA-Lib](https://ta-lib.org) |
| Chart generation | [mplfinance](https://github.com/matplotlib/mplfinance), matplotlib |
| Data — equities | [vnstock](https://github.com/thinh-vu/vnstock), entrade REST, TCBS REST, SSI REST |
| Sentiment model | [ViSoBERT](https://huggingface.co/5CD-AI/Vietnamese-Sentiment-visobert) (HuggingFace Transformers) |
| News source | [CafeF](https://cafef.vn) (BeautifulSoup crawler) |
| Web framework | Flask |
| Charts (UI) | Chart.js |
| Markdown rendering | marked.js |

---

## Installation

### Prerequisites

- Python 3.10+
- TA-Lib C library ([install guide](https://ta-lib.org/install/))
- A free [Groq API key](https://console.groq.com/keys)

### Steps

```bash
# 1. Clone the repository
git clone https://github.com/DungPhanHoangg05/viQuantAgent
cd quantagent-vn

# 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install Python dependencies
pip install -r requirements.txt
```

---

## Configuration

All defaults live in `default_config.py` (not shown but imported throughout):

```python
DEFAULT_CONFIG = {
    "agent_llm_model":        "llama-3.1-8b-instant",   # text agent 
    "graph_llm_model":        "meta-llama/llama-4-scout-17b-16e-instruct",  # vision agent 
    "agent_llm_provider":     "groq",
    "graph_llm_provider":     "groq",
    "agent_llm_temperature":  0.1,
    "graph_llm_temperature":  0.1,
    "groq_api_key":           "", 
    "use_historical_sentiment": True
}
```

You can also set the key via environment variable:

```bash
export GROQ_API_KEY="gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

---

## Usage

### Start the Web App

```bash
python web_interface.py
```

Then open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

1. Enter your **Groq API key** in the settings panel and click **Save API Key**.
2. Search for and select a **stock symbol** (e.g. `VNM`, `FPT`, `ACB`).
3. Choose a **timeframe** (5m / 15m / 30m / 1h / 1D / 1W / 1M).
4. Click **Run Analysis** and watch the 6-step progress bar as each agent completes.
5. Review the results page — indicator signals, alpha factors, sentiment, candlestick pattern, trendline analysis, and the final LONG/SHORT decision.

### Command-Line Alpha Comparison

Run the 87-alpha tournament for any symbol and print a ranked leaderboard:

```bash
python alpha_compare.py VNM 1d
# or
python alpha_compare.py ACB 1h
```

---

## Backtest Engine

Navigate to [http://127.0.0.1:5000/backtest](http://127.0.0.1:5000/backtest).

| Parameter | Default | Description |
|-----------|---------|-------------|
| Symbol | `VNM` | Stock ticker |
| Test points | `10` | Number of rolling windows to evaluate |
| Window size | `45` | Candles per analysis window |
| Step | `3` | Candles between consecutive windows |

The engine runs **two full pipeline passes** per test point (Full System and No-Alpha System) and measures whether Alpha Agent improves directional accuracy. Historical sentiment data is crawled once and cached to disk (`sentiment_cache_{SYMBOL}.json`) for reuse across runs, ensuring no future data leakage.


---

## Alpha Factor System

### Original 5 Alphas (always available as fallback)

| ID | Name | Type | Formula sketch |
|----|------|------|----------------|
| α1 | Flow-Driven Momentum (FDM) | Continuation | `tanh(ROC_adj × Vol_Surge × 0.5)` |
| α2 | Sentiment-Flow Asymmetry (SFA) | Hybrid | `tanh(Z_Sent × 0.5 + ROC_adj × 0.5)` |
| α3 | Liquidity Void Reversion (LVR) | Mean-reversion | `tanh(-0.8 × ZScore((Close-SMA5)/Close))` |
| α4 | Bollinger Squeeze & Flow (BFE) | Volatility breakout | `tanh((%B - 0.5) × Vol_ZScore(5) × 1.5)` |
| α5 | Order Flow Exhaustion (OFE) | Intrabar reversal | `tanh(ROC_adj × close_pos × 3.0)` |

### Adapted WorldQuant-101 Alphas

79 formulas from the [*101 Formulaic Alphas*](https://arxiv.org/abs/1601.00991) paper are adapted for single-stock Vietnamese OHLCV data (cross-sectional `rank()` → `ts_rank()`, VWAP proxy = `(H+L+C)/3`, `adv20` = 20-day average volume). Selected dynamically based on walk-forward IC and accuracy for each symbol.

---

## Project Structure

```
quantagent-vn/
│
├── web_interface.py        # Flask app — routes, job queue, backtest API
├── trading_graph.py        # TradingGraph — wires LLMs + toolkit + pipeline
├── graph_setup.py          # LangGraph StateGraph builder
├── agent_state.py          # IndicatorAgentState TypedDict (shared state schema)
│
├── indicator_agent.py      # Agent 1: TA-Lib indicators + Python signal classifier
├── alpha_agent.py          # Agent 2: sentiment + 5 alpha factor computation
├── pattern_agent.py        # Agent 3: vision candlestick pattern recognition
├── trend_agent.py          # Agent 4: vision trendline analysis
├── decision_agent.py       # Agent 5: multi-report synthesis → LONG/SHORT JSON
│
├── alpha_compare.py        # 87-alpha tournament + backtest metrics + WQ-101 registry
├── alpha_selector.py       # Auto-selects top-5 alphas for a symbol/timeframe
├── backtest_engine.py      # Walk-forward engine — Full vs No-Alpha comparison
│
├── sentiment_agent.py      # CafeF crawler + ViSoBERT scorer + report builder
├── sentiment_cache.py      # Historical sentiment store for bias-free backtesting
│
├── realtime_loader.py      # vnstock / entrade / TCBS / SSI data fetching + symbol list
├── static_util.py          # Chart generators (kline, trendline) + forecast horizon logic
├── graph_util.py           # Trendline math + LangChain @tool wrappers for indicators
├── color_style.py          # mplfinance colour theme (Vietnamese flag palette)
│
├── templates/
│   ├── demo_new.html       # Main analysis form UI
│   ├── output.html         # Results page (indicator, alpha, pattern, trend, decision)
│   └── backtest.html       # Backtest dashboard with Chart.js live updates
│
└── default_config.py       # Default LLM model names and settings
```
---

## Disclaimer

**This software is for educational and research purposes only.** It does not constitute financial advice. Trading stocks carries substantial risk of loss. The authors and contributors are not responsible for any financial decisions made based on this tool's output. Always consult a qualified financial advisor before making investment decisions.

The system calls the Groq API and crawls CafeF.vn; please respect each service's terms of use and rate limits.