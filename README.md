# A Multi-Agent Large Language Model Approach to Price-Driven Stock Trading in the Vietnamese Stock Market

Research codebase for a quantitative multi-agent trading system designed for the Vietnamese stock market (HOSE). The system leverages LangGraph to orchestrate specialized agents combining technical indicators, chart-pattern and trend visual analysis, point-in-time quantitative alpha factors, Vietnamese financial news sentiment, and Regime-Aware Multi-Task Bayesian In-Context Learning (BRPP) for economic decision-making under non-stationary market regimes.

---

## Overview

Large Language Models (LLMs) deployed in zero-shot multi-agent trading frameworks often suffer from unconditioned reasoning, rendering them vulnerable to false breakouts and bull/bear traps when financial markets shift phases (regime shifts). 

Adapting theoretical foundations from *Multi-Task Bayesian In-Context Learning* (Zhu, Oermann, Cho — ICML 2026), this repository introduces a **Bayesian Regime Prior Prefix (BRPP)** architecture. By injecting distilled historical trading cycles from the same macro-regime as an in-context prefix, the system enables amortized hierarchical Bayesian inference in the Decision Agent at inference time without modifying model weights.

### Economic Contract & Trading Simulation

The forecasting decision and economic simulation are strictly decoupled:
- **`LONG` Decision**: Executes a round-trip position buying at next-day open price $\text{Open}(t+1)$ and liquidating at target close price $\text{Close}(t+3)$ (a $T+2.5$ settlement horizon matching Vietnamese exchange conventions).
- **`SHORT` Decision**: Holds 100% cash balance. The framework does not assume uncovered short selling of underlying Vietnamese equities.
- **Transaction Costs**: Realistically accounts for two-sided frictions with a **0.25% brokerage fee** plus **0.10% slippage** applied to both the buy and sell legs (~0.70% total round-trip turnover cost).
- **Portfolio Tracking**: Compounded account equity starting from VND 50,000,000 capital.

---

## System Architecture

```text
+-----------------------------------------------------------------------------------+
| 1. POINT-IN-TIME DATA & MACRO REGIME LAYER                                        |
| • Market Data Loader (vnstock / VCI / KBS): Daily EOD OHLCV                       |
| • 4-State Gaussian HMM: Market Regime (BULL, BEAR, CHOPPY, CONSOLIDATION)         |
+-----------------------------------------+-----------------------------------------+
                                          |
+-----------------------------------------v-----------------------------------------+
| 2. HISTORICAL MEMORY & BAYESIAN RETRIEVAL                                         |
| • Point-in-Time Memory Bank: 852 verified historical T+2.5 cycles (2018-2022)     |
| • Bayesian Prior Retriever: Strict temporal cutoff (exit_date < as_of_date)       |
| • Compact BRPP Prefix: Similar historical episodes + Empirical / Beta-Binomial    |
+-----------------------------------------+-----------------------------------------+
                                          |
+-----------------------------------------v-----------------------------------------+
| 3. LANGGRAPH MULTI-AGENT EXECUTION PIPELINE                                       |
| • Indicator Agent: Momentum, volatility, and trend strength indicators (TA-Lib)   |
| • Alpha / Sentiment Stage: Top 5 point-in-time alpha factors & CafeF news sentiment|
| • Pattern Agent: Vision analysis on candlestick charts with OHLCV consistency     |
| • Trend Agent: Chart structure, support/resistance, and directional verification  |
| • Decision Agent: Bayesian ICL conditioning -> Structured LONG / SHORT Decision   |
+-----------------------------------------+-----------------------------------------+
                                          |
+-----------------------------------------v-----------------------------------------+
| 4. ECONOMIC EVALUATION & AUDIT LAYER                                              |
| • Paired Comparative Protocol: Single upstream pass deep-copied across baselines  |
| • T+2.5 Compounded Account Simulation (Returns, Max Drawdown, Sharpe, Sortino)    |
| • Statistical Tests: McNemar, Wilcoxon Signed-Rank, Block Bootstrap 95% CI        |
+-----------------------------------------------------------------------------------+
```

### Agent Roles

1. **Indicator Agent**: Calculates core quantitative indicators (RSI, MACD, Bollinger Bands, ATR, ADX) over a 45-candle lookback window.
2. **Alpha / Sentiment Stage**: Dynamically selects the top 5 predictive alpha factors from an 85-factor quantitative registry using point-in-time cross-validation, and extracts financial sentiment from dated CafeF articles using a fine-tuned ViSoBERT model.
3. **Pattern Agent**: Analyzes rendered candlestick charts to identify reversal and continuation patterns, reinforced with numeric OHLCV boundary validation.
4. **Trend Agent**: Evaluates market structure, moving average alignments, support/resistance levels, and breakout validity.
5. **Decision Agent**: Synthesizes distilled upstream reports, conditions reasoning on the Bayesian Regime Prior Prefix, and emits a structured `LONG` or `SHORT` forecast with categorical confidence and justification.

---

## Methodological Safeguards & Zero-Leakage Directives

- **P0-1 Strict Temporal Cutoff**: For any evaluation at date $t$, all inputs (market data, alpha evaluation, news articles, and historical memory) strictly satisfy $\text{timestamp} \le t$. Prior task episodes require $\text{exit\_date} < t$. Future-dated or undated records are automatically rejected with loud exceptions.
- **P0-2 Economic Contract Invariance**: All historical memory labels and backtest evaluations use the identical `compute_round_trip_net_return` function with full two-sided fees and slippage.
- **P0-3 Strict Token Budget**: The BRPP prefix is strictly capped at $\le 600$ characters. Total Decision Agent prompt size is guarded under $< 6,500$ characters to prevent Groq API rate limits (TPM/RPM) and context-dilution effects.
- **P0-4 Paired Upstream Invariance**: Upstream perception passes (`Indicator -> Pattern -> Trend`) execute exactly once per test point and are deep-copied across all comparative branches (Original, Random, Recent, Similarity, and Bayesian candidates) to eliminate stochastic vision inference variance.
- **Durable Checkpointing**: Automatic state persistence after each test point with native Windows OS file locks, ensuring seamless recovery from interruptions without duplicate API invocations.

---

## Requirements

- **Operating System**: Windows (tested with the Python launcher `py`), Linux, or macOS.
- **Python Runtime**: **Python 3.13** (pinned to Python 3.13.5 in `.python-version`).
- **Dependencies**: TA-Lib native library, PyTorch, LangGraph, LangChain, Transformers.
- **API Access**: Groq API key for hosted LLM inference (`openai/gpt-oss-20b`, `qwen/qwen3.8-27b`).
- **Sentiment Model**: ViSoBERT (`5CD-AI/Vietnamese-Sentiment-visobert`) runs locally by default; Hugging Face Dedicated Inference Endpoint is optionally supported.

---

## Installation

1. **Clone the repository**:
   ```powershell
   git clone https://github.com/DungPhanHoangg05/A-Multi-Agent-Large-Language-Model-Approach-to-Price-Driven-Stock-Trading-in-the-Vietnamese-Stock-Ma.git
   cd A-Multi-Agent-Large-Language-Model-Approach-to-Price-Driven-Stock-Trading-in-the-Vietnamese-Stock-Ma
   ```

2. **Create and activate a virtual environment**:
   ```powershell
   py -3.13 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. **Install dependencies**:
   ```powershell
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   ```
   *Note*: `requirements.txt` pins `vnstock==4.0.9` and `vnai==2.6.2`, utilizing the official index `https://vnstocks.com/api/simple`. For market data, loaders query VCI and KBS; index series are measured in points and stock prices in thousands of VND. See [vnstock upgrade documentation](docs/vnstock_upgrade.md).

4. **Configure environment variables**:
   Create a local `.env` file in the root directory:
   ```dotenv
   GROQ_API_KEY=your_groq_api_key_here
   HF_TOKEN=your_optional_huggingface_token
   
   # ViSoBERT configuration: auto (default), local, endpoint, or lexicon
   VISOBERT_BACKEND=auto
   VISOBERT_DEVICE=auto
   
   # Required only if VISOBERT_BACKEND=endpoint
   HF_INFERENCE_ENDPOINT_URL=https://your-endpoint.endpoints.huggingface.cloud
   ```
   *Never commit `.env` or API credentials to version control.*

---

## Verification & Testing

Before running experiments, verify the integrity of the system through the four mandatory quality gates:

1. **Compile all Python source files**:
   ```powershell
   py -3.13 -m compileall agents core data_manager scripts tests utils web_interface.py
   ```

2. **Run deterministic offline end-to-end regression test**:
   ```powershell
   py -3.13 scripts/run_end_to_end_test.py
   ```
   Exercises data loaders, chart generation, alpha selection, LangGraph multi-agent execution with deterministic LLM doubles, and financial metrics calculation offline.

3. **Run complete unit test suite**:
   ```powershell
   py -3.13 -X utf8 -m unittest discover -s tests -v
   ```

4. **Run zero-leakage security test suite**:
   ```powershell
   py -3.13 -X utf8 -m unittest discover -s tests -p "test_*leakage.py" -v
   ```

---

## Web Interface

The repository includes an interactive Flask web application for visual analysis and backtesting:

```powershell
py -3.13 web_interface.py
```

Access the interface at `http://127.0.0.1:5000`. You can configure API keys, select stock symbols (e.g., `FPT`, `VNM`, `VCB`, `MWG`), inspect generated technical charts, view distilled agent reports, and run interactive walk-forward simulations.

---

## Cloud Deployment

The backend application and local ViSoBERT model can be containerized and deployed using Docker Compose on an Oracle Cloud Compute VM (or any cloud Linux VM) using a Gunicorn worker, PyTorch CPU, and volume-mounted model cache. 

For step-by-step guidance on VM provisioning, SSH tunneling, and HTTPS configuration, refer to the [Oracle Cloud deployment guide](docs/oracle_deployment.md).

---

## Research Experiments

Research scripts support paired walk-forward backtesting across five baseline regimes and multi-candidate Bayesian v2 configurations:

1. **Run paired ablation benchmark**:
   ```powershell
   py -3.13 scripts/run_bayesian_ablation.py --symbol FPT --n_tests 20
   ```

2. **Run multi-symbol comparative sweeps**:
   ```powershell
   py -3.13 scripts/run_ablation_matrix.py --symbols FPT,VNM,VCB,MWG --n_tests 20
   ```

3. **Verify completed cohort runs offline**:
   ```powershell
   py -3.13 scripts/run_bayesian_ablation.py --verify-only
   ```

All runners support checkpointing via native file locks. If an API rate limit (`HTTP 429`) is encountered, the process suspends gracefully and can be resumed without data loss. Output artifacts are persisted under `outputs/`.

---

## Repository Structure

```text
├── agents/             # Multi-agent implementations, prompts, and output schemas
│   ├── agent_state.py      # LangGraph state schema with Bayesian prior context
│   ├── decision_agent.py   # Decision Agent with BRPP conditioning and budget guards
│   ├── indicator_agent.py  # Quantitative indicator generator
│   ├── pattern_agent.py    # Candlestick pattern vision agent
│   ├── sentiment_agent.py  # ViSoBERT financial news sentiment analyzer
│   └── trend_agent.py      # Market structure and trendline analysis agent
├── core/               # Core analytical and backtesting engines
│   ├── backtest_engine.py  # Economic simulation engine (T+2.5, fees, slippage)
│   ├── bayesian_memory.py  # Historical episode memory bank manager
│   ├── bayesian_retriever.py # Point-in-time Bayesian prior retrieval engine
│   ├── candidate_cohort.py # Bayesian v2 candidate evaluation framework
│   ├── groq_pacing.py      # Rate limit pacing and admission control guard
│   ├── pit_price_features.py # Point-in-time price feature extractors
│   ├── prior_backtest.py   # Paired multi-branch walk-forward coordinator
│   └── regime_detector.py  # 4-state Gaussian HMM market regime classifier
├── data/               # Market price datasets and verification manifests
├── data_manager/       # Historical sentiment caches and memory bank stores
├── docs/               # Research documentation and specifications
│   ├── methodology_spec.md # Formal research methodology specification
│   ├── oracle_deployment.md# Cloud production deployment instructions
│   ├── vnstock_upgrade.md  # Market data API upgrade notes
│   └── plan/               # Weekly implementation plans and audit logs
├── outputs/            # Checkpoints, benchmark runs, and performance reports
├── scripts/            # End-to-end tests, data preparation, and execution runners
├── tests/              # Test suites (leakage, pairing, token budgets, financial)
├── utils/              # Graph assembly, technical indicators, and statistical tests
└── web_interface.py    # Flask web UI and visualization server
```

---

## Research Documentation & Planning

Detailed academic and implementation documentation is maintained in the `docs/` directory:
- **Research Methodology**: [docs/methodology_spec.md](docs/methodology_spec.md) defines the mathematical mapping from hierarchical Bayesian inference to stock trading, economic conventions, and hypothesis testing protocols.
- **Implementation Master Plan**: [docs/plan/plan.md](docs/plan/plan.md) details the 10-week implementation roadmap and experimental matrix.
- **Weekly Progress & Audit Logs**: Detailed weekly worklogs, checklists, and verification receipts are organized chronologically under `docs/plan/week<N>/`.

---

## Reproducibility & Disclaimer

- **Deterministic Verification**: The offline test suite seeds Python and NumPy with `42` and replaces external network/LLM boundaries with deterministic test doubles, guaranteeing reproducible validation of software logic.
- **Empirical Reproducibility**: Exact empirical reruns of hosted LLM inference depend on provider model revisions, prompt token limits, and market data snapshots. Checkpoints and audit ledgers preserve exact execution hashes for independent auditing.
- **Academic Disclaimer**: This software is an academic research prototype developed for a graduation thesis. It does not constitute financial or investment advice. The economic simulator does not model continuous order-book depth, exchange circuit breakers, borrowing constraints, or tax policies.
