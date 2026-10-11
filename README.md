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

## Tiến độ và tài liệu chính

**W1–W5 đã hoàn thành, W5 chốt 15/15 task ngày 10/10/2026.** Pilot thật W4 có
FPT 20 điểm/100 Decision; smoke W5 có bốn mã/20 Decision. Kho prior có 852 episode; W4 đã
tích hợp PIT/paired/checkpoint và xử lý cảnh báo p95: bốn mode 10,837–13,235 ms.
Nghiệm thu 07/10/2026: compileall/E2E, **521 unit/93 leakage PASS**, verifier pilot PASS.
Prior mặc định tắt; pilot có ngoại lệ upstream điểm 16 được xác nhận/audit;
chưa có benchmark đủ bốn mã/2023–2024 hoặc bằng chứng tăng lợi nhuận OOS.

- [Kế hoạch tổng](docs/plan/plan.md) và tiến độ [W1](docs/plan/week1/README.md),
  [W2](docs/plan/week2/README.md), [W3](docs/plan/week3/README.md), [W4](docs/plan/week4/README.md),
  [W5](docs/plan/week5/README.md), [W6](docs/plan/week6/README.md).
- [Phương pháp nghiên cứu](docs/methodology_spec.md).
- [Chạy/tiếp tục Memory Bank và QA](docs/plan/week2/phase_c_memory_generation.md).
- [API prior, checkpoint/resume và bàn giao W5](docs/plan/week4/week_close_and_handoff.md).
- Lộ trình đã mở rộng thành **10 tuần**: W5 vận hành/nền tảng Bayesian v2,
  W6 cải thiện thuật toán, W7 validation/khóa phiên bản, W8 benchmark,
  W9 thống kê, W10 luận văn. Giữ bốn phase W5; bổ sung đầu ra code
  posterior/gate bằng chứng/prefix, không coi cập nhật plan là đã triển khai.
  **W5 đã đóng Phase A/B/C/D, 15/15 task trong phạm vi DONE.** CLI cohort và
  evidence/gate/prefix v2 đã kiểm fixture; input/lịch khóa **124 điểm chính**
  (60 development/64 holdout) +**4 smoke riêng**, kiểm offline **128/128 PASS**.
  Smoke thật **4/4 điểm, 20/20 Decision structured**, verifier/reconcile PASS;
  W5-16 chạy lại **624 unit/105 leakage**, compileall/E2E PASS. 122 file bảo vệ
  nguyên byte. p95 W5-15 bốn mode **10,566/9,831/9,642/12,127 ms**, đều <30;
  evidence v2 **5,0475 ms** sau giảm tải, giữ cả lượt có tải FAIL để đối chiếu.
  BEAR OOS=0, tin reliable=0 và FPT Q1 thiếu bốn mẫu vẫn là giới hạn nguồn.
  Bàn giao lệnh từng mã, dữ liệu và xử lý dừng/unknown ở **mục W5-16 của README W5**;
  runtime output được gitignore, chưa có benchmark hoặc bằng chứng hiệu quả v2.
  **W5-11 đã bỏ khỏi phạm vi theo yêu cầu**; giữ nguyên mã các task còn lại.
  **W6: Phase A/B DONE, Gate A/B PASS; Phase C IN_PROGRESS, W6-01–10 DONE, 10/16 task hoàn thành**.
  Đã kiểm bàn giao W5, bản đồ tích hợp và provenance theo fold: bank/replay
  852/852, 217 scaler HMM prefix, 16 điểm Alpha và 4 ca sửa tương lai PASS
  offline. Đã chốt feature 21 phiên/xử lý quyền, scaler theo fold, ranking
  tín hiệu+giá/recency/diversity và shrink dùng background tách nhóm điều kiện.
  Đã đăng ký sáu cấu hình C0–C3/ablation, ngưỡng chất lượng và tiêu chí đánh
  giá paired. Đã triển khai extractor bốn feature giá/21 phiên PIT và
  callback adapter; audit train 699/852 hợp lệ, 153 barrier, fit 166/428.
  Đã có producer/loader/cache index phụ 852 episode, scaler riêng mã/fold
  fit 166/428 và OOS freeze 699 hàng train; round-trip/semantic/prefix OOS
  PASS offline, hot cache không I/O/refit. Index runtime đã gitignore.
  Đã triển khai base ranking tín hiệu+giá và trace S/d/P/base, giữ v1; audit
  651/651 query train khớp oracle độc lập. Policy recency/tuổi/similarity/gap
  phiên chọn K≤3 có trace giữ/loại, giữ population thống kê; 651/651 query
  chọn đúng oracle, không bù K. Thống kê điều kiện P/C/B rời nhau và shrink
  strength4 có validator tái tính nguồn; audit 651/651 query train PASS,
  C rỗng giữ posterior=null. Đã có quality gate tách stats/examples theo
  support/CrI, gate ghép cặp C1, reason/visibility/fallback và validator
  tái tính nguồn; K=0/prior off tắt toàn prior, không sửa action.
  Compileall/E2E, **729 unit/135 leakage PASS**.
  Tiếp theo **W6-11**: prefix/Decision contract và ablation nội dung theo
  [kế hoạch W6](docs/plan/week6/README.md); CLI/identity ứng viên thuộc W6-12.
  Các lượt dùng API key do người dùng tự chạy theo
  [hướng dẫn W5-14](docs/plan/week5/README.md#cách-tự-chạy-w5-14-bằng-terminal).
  Năm 2023 là tập phát triển; năm 2024 giữ cho đánh giá xác nhận.

Tiến độ cập nhật trong README từng tuần. Receipt lịch sử không phục vụ code/test
được gói nguyên byte trong [ZIP bằng chứng](docs/plan/implementation_evidence.zip).

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
