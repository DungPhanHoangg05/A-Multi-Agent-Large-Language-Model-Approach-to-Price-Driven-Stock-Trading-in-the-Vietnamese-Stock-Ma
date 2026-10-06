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

## Tiến độ nâng cấp nghiên cứu

Kế hoạch theo tuần đặt tại `docs/plan/week<N>/`; kế hoạch tổng ở
[docs/plan/plan.md](docs/plan/plan.md). **W3 đã hoàn thành 16/16 task**, bàn giao API retriever độc lập,
thống kê regime, BRPP và kiểm chứng offline tại
[biên bản chốt/bàn giao W4](docs/plan/week3/week_close_and_handoff.md).
W4 tiếp tục tích hợp state/graph/Decision/checkpoint và áp dụng cap/guard prompt;
runtime tích hợp và kết quả giao dịch ngoài mẫu có gate riêng.
[Kế hoạch W4](docs/plan/week4/README.md) đã chia 16 task trong bốn phase;
**Phase A W4 hoàn thành 4/4**, **Phase B 4/4 (W4-05..08)**,
**Phase C 4/4 (W4-09..12)**, **Phase D 3/4 (W4-13..15)**, tiến độ W4 **15/16**;
Gate A PASS đặc tả với
[hợp đồng kết quả/checkpoint](docs/plan/week4/checkpoint_contract.md) và
[receipt](docs/plan/week4/checkpoint_review.json). State/config runtime đã có tám field
optional, parser strict và guard off/enabled, **367 unit/E2E/56 leakage PASS**:
[biên bản](docs/plan/week4/state_config_runtime.md). Cap backtest 4.000 và guard
prompt cuối `<6500` đã PASS **375 unit/E2E/56 leakage**:
[biên bản ngân sách runtime](docs/plan/week4/runtime_prompt_budget.md).
BRPP/reasoning tại node Decision đã PASS **386 unit/E2E/56 leakage**, kể cả
prefix 600 + hướng dẫn (max 6.467): [biên bản](docs/plan/week4/decision_prior_integration.md).
Graph tách Full preparation và prior/Decision đã PASS **399 unit/E2E/56 leakage**,
128 ca graph thật và hồi quy bốn ablation: [biên bản/API](docs/plan/week4/graph_prior_integration.md).
**Gate B PASS offline với verifier/retriever fixture**. Adapter W4-09 đã kiểm
nguồn thật, hai provider PIT và seal Full signals; **430 unit/E2E/71 leakage PASS**:
[biên bản/API](docs/plan/week4/prior_context_adapter.md),
[receipt](docs/plan/week4/prior_context_review.json). Engine W4-10 đã chạy
upstream/Full một lần và năm Decision tuần tự, kiểm mutation/đảo thứ tự:
[API/biên bản](docs/plan/week4/paired_prior_point.md),
[receipt](docs/plan/week4/paired_prior_point_review.json), **445 unit/E2E/74 leakage PASS**.
W4-11 đã có vòng walk-forward năm nhánh, schema kết quả và P&L từ engine hiện có:
[biên bản/API](docs/plan/week4/prior_backtest_integration.md),
[receipt](docs/plan/week4/prior_backtest_review.json), **461 unit/E2E/77 leakage PASS**.
W4-12 đã có checkpoint/resume từng nhánh, manifest/shared/input durable trước API,
semantic verifier và OS lock kiểm native Windows:
[API/biên bản](docs/plan/week4/prior_checkpoint_resume.md),
[receipt](docs/plan/week4/paired_checkpoint_review.json), **483 unit/E2E/82 leakage PASS**.
**Gate C PASS offline**. W4-13 đã kiểm leakage toàn đường tích hợp và sửa
đối chiếu proof provider với artifact/prefix thật:
[coverage/biên bản](docs/plan/week4/pipeline_leakage_validation.md),
[receipt](docs/plan/week4/pipeline_leakage_review.json), **494 unit/E2E/93 leakage PASS**.
W4-14 smoke E2E riêng đã PASS: 8 context tổng hợp bốn regime/VI-EN, năm nhánh,
resume/flag off/budget và 6 replay context thật (Decision giả):
[biên bản](docs/plan/week4/prior_integration_smoke.md),
[receipt](docs/plan/week4/integration_smoke.json), **498 unit/E2E/93 leakage PASS**.
W4-15 đã PASS bốn gate mới, hash/scope và ngân sách runtime; overhead adapter/formatter/graph
được đo riêng. **Benchmark bổ sung FAIL ngưỡng p95 <30 ms dưới tải máy hiện tại**;
retriever/memory giữ nguyên, cảnh báo hiệu năng được bàn giao:
[biên bản](docs/plan/week4/integration_gate_validation.md),
[receipt gate](docs/plan/week4/integration_gate_review.json),
[receipt hiệu năng](docs/plan/week4/integration_performance_review.json).
Tiếp theo W4-16 chốt/bàn giao W5; Gate D và giá ngoài mẫu/pilot còn mở.

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

`requirements.txt` ghim `vnstock==4.0.9`, `vnai==2.6.2` và bổ sung kho gói chính thức `https://vnstocks.com/api/simple`, nên lệnh cài từ file requirements ở trên đã có cấu hình cần thiết. Loader sử dụng VCI/KBS; chỉ số giữ đơn vị điểm và giá cổ phiếu giữ đơn vị nghìn VND. Xem [biên bản nâng cấp](docs/vnstock_upgrade.md).

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

## Triển khai trên Oracle Cloud

Backend Flask và mô hình ViSoBERT được triển khai bằng Docker Compose trên Oracle Compute VM. Dùng một Gunicorn worker, PyTorch CPU và volume lưu cache mô hình/kết quả. Xem [hướng dẫn Oracle từ bước tạo VM](docs/oracle_deployment.md), bao gồm truy cập SSH khi chưa có tên miền và HTTPS khi công bố ứng dụng.

Không còn workflow xuất toàn repository lên GitHub Pages. Cấu hình Oracle không đặt trần RAM container; cần chọn VM đủ bộ nhớ và theo dõi mức sử dụng thực tế.

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

## Reproducibility notes

The offline regression path seeds Python and NumPy with 42 and replaces network/LLM boundaries with deterministic fixtures. It verifies software behavior, not the exact empirical outputs of a historical hosted-model run.

Exact empirical reproduction additionally requires the original point-in-time market snapshots, dated sentiment caches, model identifiers/revisions, and private result artifacts. Hosted inference is not guaranteed to be bit-reproducible across provider revisions.

This project is a research prototype, not investment advice. It does not model every exchange rule, tax, liquidity constraint, market-impact effect, or production execution risk.
