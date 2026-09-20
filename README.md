# A Multi-Agent Large Language Model Approach to Price-Driven Stock Trading in the Vietnamese Stock Market

This repository contains the research code for a LangGraph-based trading-decision framework tailored to the Vietnamese stock market. Five specialized agents combine technical indicators, candlestick patterns, trend structure, dynamically selected quantitative alpha factors, and Vietnamese financial-news sentiment to produce a forced `LONG`/`SHORT` classification.

The economic evaluation is deliberately distinct from directional classification: `LONG` executes a fixed-horizon buy-then-sell cycle, while `SHORT` remains in cash because uncovered short selling of the underlying stock is not modeled. Account returns are compounded and include a 0.25% brokerage fee plus 0.10% slippage on each trade leg.

## Reproducible setup

Python **3.13** is required. The repository is tested with Python 3.13.5; using the system `python` command is not sufficient when it resolves to another installed version.

On Windows PowerShell, clone the repository and create an isolated environment as follows:

```powershell
git clone https://github.com/DungPhanHoangg05/A-Multi-Agent-Large-Language-Model-Approach-to-Price-Driven-Stock-Trading-in-the-Vietnamese-Stock-Ma.git
cd A-Multi-Agent-Large-Language-Model-Approach-to-Price-Driven-Stock-Trading-in-the-Vietnamese-Stock-Ma
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

TA-Lib is listed in `requirements.txt`. If its wheel is unavailable for a different platform, install the platform's TA-Lib native library first and then rerun the final command. Do not silently switch Python versions.

### Environment variables

Create a local `.env` file in the repository root for online inference:

```dotenv
GROQ_API_KEY=replace_with_your_groq_key
HF_TOKEN=replace_with_your_optional_huggingface_token
```

`GROQ_API_KEY` is required for live text/vision inference. `HF_TOKEN` enables the hosted ViSoBERT sentiment scorer; when it is absent or unavailable, the code records and uses its lexicon fallback. Never commit `.env` or API keys. The automated end-to-end regression test below is fully offline and requires neither key.

## One-command end-to-end reproduction

After installing `requirements.txt`, run:

```powershell
py -3.13 scripts/run_end_to_end_test.py
```

The command executes one complete T+2.5 walk-forward point through the real data contracts, CafeF parser, historical sentiment cache, chart generators, 85-candidate Alpha Selector, five-agent LangGraph, structured Decision Agent output, compounded account P&L, transaction costs, and statistical summary. Network and hosted-LLM boundaries use deterministic local fixtures, so the regression result is independent of API quota and model drift. A successful run ends with:

```text
[PASS] ALL PIPELINE CHECKS SUCCESSFUL IN <runtime>s
```

Temporary JSON and PNG artifacts are validated and removed automatically. The test also reports peak Python-traced memory. It exits with a non-zero status at the first violated pipeline contract.

To run the complete unit-test suite:

```powershell
py -3.13 -X utf8 -m unittest discover -s tests -v
```

## Running the application

With `GROQ_API_KEY` configured, start the web interface:

```powershell
py -3.13 web_interface.py
```

Open `http://127.0.0.1:5000`. The interface supports live analysis and walk-forward backtesting. Backtest JSON and figures are written beneath `backtest_result/`; this directory is intentionally excluded from version control because full runs are large and may be regenerated.

## Reproducing research experiments

Online experiments require `.env`, market-data access, and the historical `sentiment_cache_<TICKER>.json` files appropriate to the frozen evaluation dates. All commands must use Python 3.13.

Robustness panels for FPT (20 points each):

```powershell
py -3.13 core/run_robustness.py --mode hyperparams --symbol FPT --n_tests 20
py -3.13 core/run_robustness.py --mode norm --symbol FPT --n_tests 20
py -3.13 core/run_robustness.py --mode weights --symbol FPT --n_tests 20
```

Four-way ablation for the frozen nine-symbol sample:

```powershell
py -3.13 scripts/run_ablation_matrix.py --symbols FPT,CMG,VCB,MBB,MWG,VNM,BHN,HVN,VJC --n_tests 20
```

Both experiment runners checkpoint completed work. After an HTTP 429 response, stop the process, replace the exhausted key in `.env`, and rerun the same command to resume from the last valid checkpoint.

The paper-facing validation utilities are:

```powershell
py -3.13 scripts/analyze_sentiment_coverage.py
py -3.13 scripts/verify_latex_tables.py
```

## Reproducibility boundary

The offline regression command is deterministic (`random.seed(42)` and `numpy.random.seed(42)`) and validates the full integration path without external services. Exact paper-result regeneration additionally depends on the archived market-data cutoffs, dated sentiment caches, and the hosted model versions used for the recorded runs. Hosted LLM inference is not bit-reproducible across provider revisions; consequently, the repository distinguishes deterministic software regression from empirical reruns and retains structured JSON/CSV checkpoints for auditability.

No trading result in this repository is investment advice. The framework is a research prototype and does not model every exchange rule, tax, liquidity constraint, or production execution risk.

## Architecture

- **Indicator Agent** computes and classifies momentum, volatility, and trend-strength indicators from the decision window only.
- **Pattern Agent** inspects a generated candlestick chart and applies OHLCV-based consistency guards.
- **Trend Agent** analyzes chart structure, support, resistance, and trend direction with factual verification.
- **Alpha Agent** selects the top five factors from an 85-candidate registry using at most 600 candles ending at the decision cutoff, and reads only news dated at or before that cutoff.
- **Decision Agent** synthesizes the available reports through a strict structured-output schema and returns only `LONG` or `SHORT`.

The backtest uses a shared upstream snapshot for paired variants, preventing stochastic differences in Indicator, Pattern, or Trend reports from contaminating the treatment/control comparison.

## Repository structure

- `agents/`: five agent implementations and output contracts.
- `core/`: alpha evaluation, data loading, robustness runner, and compounded backtest engine.
- `data_manager/`: historical sentiment-cache management.
- `scripts/`: end-to-end regression, ablation, coverage, and manuscript-validation utilities.
- `tests/`: unit and regression tests for leakage, paired execution, finance, statistics, and report guards.
- `outputs/`: structured robustness, ablation, coverage, and paper-facing audit artifacts.
- `ESWA/`: Elsevier manuscript source and compiled paper.
- `web_interface.py`, `templates/`, `static/`: Flask application and user interface.

## Code and artifact availability

The repository contains the source code, automated tests, experiment runners, structured analysis artifacts, and manuscript required to audit the reported method. Secrets, temporary charts, raw backtest work products, and local sentiment caches are excluded from version control. Researchers publishing a release should archive the frozen input snapshots and result directory alongside the tagged source revision so that empirical outputs remain traceable to their exact data cutoff and model configuration.
