# A Multi-Agent Large Language Model Approach to Price-Driven Stock Trading in the Vietnamese Stock Market

Research code for a LangGraph-based stock-direction framework designed for the Vietnamese market. The pipeline combines technical indicators, chart-pattern and trend analysis, dynamically selected quantitative alpha factors, Vietnamese financial-news sentiment, and a structured decision stage that emits a binary `LONG` or `SHORT` forecast.

The forecast label and the economic simulation are intentionally separate. A `LONG` forecast opens a fixed-horizon buy-at-open, sell-at-target-close cycle. A `SHORT` forecast remains in cash because the simulator does not assume uncovered short selling of Vietnamese underlying equities. Account returns are compounded from an initial VND 50,000,000 balance and apply a 0.25% brokerage fee plus 0.10% slippage on both the buy and sell legs.

## What is implemented

- Five-stage LangGraph workflow: Indicator, Alpha/Sentiment, Pattern, Trend, and Decision.
- Point-in-time alpha selection from an 85-factor registry, using at most 600 candles ending at the decision cutoff.
- Strict historical-sentiment filtering that rejects future-dated and undated records in research mode.
- Shared upstream reports for paired comparisons, preventing repeated vision or indicator inference from contaminating treatment/control results.
- Four ablation modes: `full`, `alpha_only`, `sentiment_only`, and `baseline`.
- Compounded account P&L, two-sided trading costs, maximum drawdown, Sharpe ratio, and hit-rate reporting.
- McNemar, Wilcoxon, Newey-West, and block-bootstrap significance utilities.
- OHLCV consistency guards for chart-pattern and trend reports.
- A deterministic offline end-to-end regression test that does not require API credentials.

## Requirements

- Windows with the Python launcher (`py`) for the commands below.
- Python **3.13**. The checked-in `.python-version` pins 3.13.5.
- Internet access for live market data, model download, and hosted-model inference.
- A Groq API key for live agent inference, supplied through `.env` or the web interface.
- ViSoBERT runs locally through Transformers by default. A Hugging Face token is optional for the public model, but is normally required for a protected Dedicated Inference Endpoint.

## Installation

```powershell
git clone https://github.com/DungPhanHoangg05/A-Multi-Agent-Large-Language-Model-Approach-to-Price-Driven-Stock-Trading-in-the-Vietnamese-Stock-Ma.git
cd A-Multi-Agent-Large-Language-Model-Approach-to-Price-Driven-Stock-Trading-in-the-Vietnamese-Stock-Ma
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

`TA-Lib` is declared in `requirements.txt`. If a wheel is unavailable on another platform, install that platform's native TA-Lib dependency before rerunning the final command. Do not switch Python versions silently; the supported runtime is Python 3.13.

Create a local `.env` file for credentials and optional ViSoBERT settings:

```dotenv
GROQ_API_KEY=replace_with_your_groq_key
HF_TOKEN=replace_with_your_optional_huggingface_token

# auto (default), local, endpoint, or lexicon
VISOBERT_BACKEND=auto
# auto (default), cpu, or cuda:0
VISOBERT_DEVICE=auto
# Required only when VISOBERT_BACKEND=endpoint. Use the exact URL created by
# Hugging Face Dedicated Inference Endpoints, not router.huggingface.co.
HF_INFERENCE_ENDPOINT_URL=https://your-endpoint.endpoints.huggingface.cloud
```

Never commit `.env` or credentials.

In `auto` mode, the application calls `HF_INFERENCE_ENDPOINT_URL` when it is set and falls back to the local Transformers model if that endpoint fails. Without an endpoint URL it loads `5CD-AI/Vietnamese-Sentiment-visobert` locally. The first local request downloads and caches the model, so it can take longer than later requests. The lexicon scorer is used only if the selected ViSoBERT backend cannot run, and each article records `scorer`, `scorer_backend`, and `is_fallback` provenance fields.

## Verify the system

Run the deterministic end-to-end test:

```powershell
py -3.13 scripts/run_end_to_end_test.py
```

It exercises the production data contracts with fixed local OHLCV and CafeF fixtures, generates the charts, selects alpha factors, executes the LangGraph workflow with deterministic LLM doubles, computes account metrics, and validates the statistical summary. A successful run ends with:

```text
[PASS] ALL PIPELINE CHECKS SUCCESSFUL IN <runtime>s
```

Run the complete unit-test suite:

```powershell
py -3.13 -X utf8 -m unittest discover -s tests -v
```

Optionally compile every Python module before running the tests:

```powershell
py -3.13 -m compileall agents core data_manager scripts tests utils web_interface.py
```

## Run the web application

```powershell
py -3.13 web_interface.py
```

Open `http://127.0.0.1:5000`. Set `PORT` to override the default port. The interface accepts a Groq key at runtime when `GROQ_API_KEY` is not already configured.

The UI supports live analysis and walk-forward backtesting. Generated JSON and PNG files are written to `backtest_result/`, which is intentionally excluded from version control.

## Run the research experiments

These commands use live market data and hosted models, so exact reruns depend on provider availability, the requested data cutoff, local dated sentiment caches, and model revisions.

Robustness sweeps:

```powershell
py -3.13 core/run_robustness.py --mode hyperparams --symbol FPT --n_tests 20
py -3.13 core/run_robustness.py --mode norm --symbol FPT --n_tests 20
py -3.13 core/run_robustness.py --mode weights --symbol FPT --n_tests 20
```

Four-way ablation on the representative sample:

```powershell
py -3.13 scripts/run_ablation_matrix.py --symbols FPT,VNM,VCB --n_tests 20
```

Both runners checkpoint completed work. If a hosted service returns HTTP 429, stop the process, update the credential if necessary, and rerun the same command to resume. Their generated files are written beneath `outputs/`, which is also excluded from version control.

Use `--data-cutoff YYYY-MM-DD` to freeze the final market-data date and `--output-dir <path>` to choose a different local artifact directory.

## Architecture

1. **Indicator Agent** computes momentum, volatility, and trend-strength indicators from the decision window.
2. **Alpha/Sentiment stage** selects the top five point-in-time alpha factors and, when enabled, loads only news available at the cutoff.
3. **Pattern Agent** analyzes a candlestick chart and applies OHLCV-based consistency checks.
4. **Trend Agent** analyzes chart structure, support, resistance, and direction with numerical verification.
5. **Decision Agent** receives only the reports enabled by the selected ablation mode and returns structured `LONG` or `SHORT` output.

For paired backtests, Indicator, Pattern, and Trend run once per test point. Their state is deep-copied into the treatment and baseline decision branches so upstream stochasticity cannot alter the control input.

## Repository layout

- `agents/`: agent implementations, prompts, and structured output contracts.
- `core/`: market-data loading, alpha evaluation, the backtest engine, and robustness runner.
- `data_manager/`: historical sentiment-cache filtering and lookup.
- `scripts/`: deterministic end-to-end testing and experiment utilities.
- `tests/`: leakage, pairing, ablation, financial, statistical, token-budget, and vision-guard tests.
- `utils/`: graph assembly, technical tools, decision parsing, alpha selection, and statistical helpers.
- `templates/`, `static/`, `web_interface.py`: Flask user interface.

## Public/private artifact boundary

This public repository contains the implementation and automated tests. The manuscript, private planning/governance documents, local sentiment caches, raw backtest outputs, and generated experiment artifacts are intentionally not versioned. The corresponding ignore rules cover `ESWA/`, `plan/`, `AGENTS.md`, `sentiment_cache_*`, `backtest_result/`, and `outputs/`.

Some audit utilities can consume those private local artifacts when they are present, but they are not required for the deterministic software test suite.

## Reproducibility notes

The offline regression path seeds Python and NumPy with 42 and replaces network/LLM boundaries with deterministic fixtures. It verifies software behavior, not the exact empirical outputs of a historical hosted-model run.

Exact empirical reproduction additionally requires the original point-in-time market snapshots, dated sentiment caches, model identifiers/revisions, and private result artifacts. Hosted inference is not guaranteed to be bit-reproducible across provider revisions.

This project is a research prototype, not investment advice. It does not model every exchange rule, tax, liquidity constraint, market-impact effect, or production execution risk.