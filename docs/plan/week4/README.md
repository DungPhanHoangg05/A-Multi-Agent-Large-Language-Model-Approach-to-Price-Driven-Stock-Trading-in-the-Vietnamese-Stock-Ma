# Tuần 4 — Tích hợp prior vào LangGraph và backtest

**Trạng thái: Phase A hoàn thành 4/4 task; Phase B hoàn thành W4-05..08 (4/4),
Phase C hoàn thành W4-09..12 (4/4), Phase D W4-13..15 hoàn thành (3/4),
tiến độ W4 15/16 ngày 06/10/2026.
Gate A PASS đặc tả, Gate B PASS offline graph/prompt
với verifier/retriever fixture. [State/config](integration_contract.md),
[provenance/PIT](provenance_contract.md), [kết quả/checkpoint](checkpoint_contract.md),
[receipt/Gate A](checkpoint_review.json), [state/config runtime](state_config_runtime_review.json).
[cap/guard runtime](runtime_prompt_budget_review.json), [BRPP tại Decision](decision_prior_integration_review.json).
[graph/Full reports](graph_prior_integration_review.json),
[adapter nguồn PIT](prior_context_review.json), [paired runtime](paired_prior_point_review.json).
[walk-forward/kết quả](prior_backtest_review.json), [checkpoint/resume](paired_checkpoint_review.json).
Gate C PASS offline, khóa kiểm native Windows. [Leakage toàn pipeline](pipeline_leakage_review.json)
PASS. [Smoke tích hợp](prior_integration_smoke.md), [receipt](integration_smoke.json)
PASS tổng hợp và replay nguồn thật với Decision giả. [Gate/phạm vi](integration_gate_review.json),
[hiệu năng](integration_performance_review.json) ghi benchmark FAIL p95 dưới tải máy;
runtime budget đã nghiệm thu, rủi ro hiệu năng được bàn giao.
Tiếp theo W4-16; Gate D và giá OOS/pilot còn mở.**
Tài liệu này tiếp nối [bàn giao W3](../week3/week_close_and_handoff.md) và
[kế hoạch tổng](../plan.md). Checklist bên dưới chỉ đánh dấu hoàn thành khi
đầu ra và kiểm chứng của task đều đạt.

## Mục tiêu và ranh giới

Đưa retriever, thống kê và BRPP đã nghiệm thu vào luồng quyết định thật, có
kiểm chứng point-in-time (PIT), ngân sách prompt, báo cáo dùng chung và resume.
Hệ thống phải giữ các entry point, bốn ablation cũ và hợp đồng kinh tế hiện có.

- W4: state/config, provenance regime, Decision/graph, backtest adapter,
  checkpoint và kiểm thử tích hợp offline.
- W5: CLI điều phối nghiên cứu, pilot FPT bằng LLM thật và đo token/quota.
- W6: benchmark giao dịch ngoài mẫu 2023–2024 sau khi đủ gate dữ liệu.

W4 không sinh lại kho, fit lại toàn bộ model, tải giá/tin, gọi API LLM thật hoặc
chạy pilot. Fixture offline phục vụ kiểm chứng kỹ thuật, không là kết quả đầu tư.
Các module/test/receipt ghi là **dự kiến** chỉ được tạo ở task triển khai tương ứng.

## Đầu vào và điểm còn mở

| Đầu vào | Hiện trạng / việc W4 phải làm |
| --- | --- |
| Kho 852 episode, manifest, QA W2 | Đã PASS; giữ nguyên byte/nhãn. SHA-256 kho `09b48c6192a092b562173e8b3b7eceb44025c6e02454093e34214a730a460949` |
| `BayesianPriorRetriever.retrieve()` | Tasks/stats/metadata hoàn chỉnh; constructor nạp một lần, query trên RAM |
| Hợp đồng và policy W3 | K=0..3; seed=42; mặc định `same_symbol`; bốn mode và fallback đã khóa |
| `format_compact_prior_prefix()` | BRPP ≤600 ký tự, K=0 rỗng; caller phải chứng minh nguồn regime/snapshot |
| Decision runtime | Cap cũ tổng 4.500 chưa đủ khi ghép BRPP; cần cap tổng 4.000 và guard cuối `<6500` |
| Graph/backtest hiện tại | Upstream ba agent đã dùng chung; graph Decision còn chạy Alpha/Sentiment theo nhánh; chưa có năm nhánh prior/checkpoint tương ứng |
| Model/regime | Có artifact train và archive prefix PIT; phải chọn provider đúng ngày, không chỉ truyền tên regime |
| Giá thô kiểm định 2023–2024 | Chưa mở gate; không chặn tích hợp offline, bắt buộc mở trước pilot/OOS |

Kho phủ 2020–2022 do warm-up 600 phiên. Sentiment của 852 episode đều NEUTRAL
do thiếu tin; giữ trọng số sentiment bằng 0 trong similarity. Stats là tỷ lệ
thực nghiệm, không là xác suất thắng đã hiệu chuẩn của LLM.

## Cấu hình so sánh cần giữ

| Nhánh nghiên cứu | Mode retriever | K | Báo cáo / stats |
| --- | --- | ---: | --- |
| Original | `bayesian_regime` | 0 | Full dùng chung; không stats, BRPP rỗng |
| Random | `random` | 3 | Full dùng chung; stats cùng population regime |
| Recent | `recent` | 3 | Full dùng chung; stats cùng population regime |
| Similarity | `similarity` | 3 | Full dùng chung; stats cùng population regime |
| Bayesian | `bayesian_regime` | 3 | Full dùng chung; stats cùng population regime |

`prior_config` là chiều cấu hình riêng với `ablation_config` cũ (`full`,
`alpha_only`, `sentiment_only`, `baseline`). Flag prior mặc định tắt. Ma trận
nghiên cứu W4 dùng `full`; không tự nhân thành 4×5 nhánh. So sánh với Original
có cả tác động stats và ví dụ; không quy toàn bộ thay đổi cho thuật toán chọn K.

## Quy tắc theo dõi

- `[ ]` chưa hoàn thành; `[x]` chỉ sau khi đầu ra và kiểm chứng task đều đạt.
- Sau mỗi task cập nhật dòng trong bảng, checklist ở phase và nhật ký: ngày,
  nhánh/commit, file, lệnh, kết quả, giới hạn còn lại. Task bị chặn ghi rõ điều kiện.
- Mỗi task trên nhánh riêng từ `develop`; commit/merge theo [AGENTS.md](../../../AGENTS.md).
  Bốn gate phải PASS trước merge; không đưa mã tuần vào commit message.
- Tài liệu/receipt tuần đặt tại `docs/plan/week4/`; log/checkpoint chạy tại
  `outputs/`, không lưu key, dữ liệu tạm hoặc kho sao chép trong tài liệu.
- Receipt W2/W3 đã đóng băng giữ nguyên; kiểm chứng mới dùng receipt W4 riêng.

## A. Khóa hợp đồng tích hợp

Chi tiết: [Phase A](phase_a_integration_contract.md).

| Mã | Task | Đầu ra / điều kiện hoàn thành | Phụ thuộc | Trạng thái |
| --- | --- | --- | --- | --- |
| W4-01 | Kiểm tra bàn giao và các điểm nối runtime | [Bản đồ/biên bản](input_readiness.md), [receipt](input_readiness.json): 852 record và archive/QA/hash PASS; replay 288 query + 288 lượt lặp, bốn gate mới PASS | W3 hoàn thành | [x] |
| W4-02 | Chốt state và cấu hình prior độc lập | [Contract v1](integration_contract.md), [policy](integration_policy.json), [ví dụ](integration_examples.json), [receipt](state_config_review.json): tám config/tám field, Full only, daily chuẩn, bốn gate PASS; chưa cài validator runtime | W4-01 | [x] |
| W4-03 | Chốt provenance và thứ tự PIT | [Contract](provenance_contract.md), [policy](provenance_policy.json), [ví dụ](provenance_examples.json), [receipt](provenance_review.json): hai provider, nguồn/shape/thứ tự PIT, 5 replay context và 14 probe hiện có, bốn gate PASS; chưa cài adapter | W4-01, W4-02 | [x] |
| W4-04 | Chốt schema kết quả và resume | [Contract](checkpoint_contract.md), [schema](research_checkpoint.schema.json), [policy](checkpoint_policy.json), [ví dụ](checkpoint_examples.json), [receipt](checkpoint_review.json): identity không chứa key, lưu từng nhánh, xử lý crash/khóa; bốn gate PASS, Gate A đóng đặc tả | W4-02, W4-03 | [x] |

## B. State, prompt và graph

Chi tiết: [Phase B](phase_b_state_prompt_graph.md).

| Mã | Task | Đầu ra / điều kiện hoàn thành | Phụ thuộc | Trạng thái |
| --- | --- | --- | --- | --- |
| W4-05 | Cài state/config và validator | [Biên bản](state_config_runtime.md), [receipt](state_config_runtime_review.json): tám field optional, parser strict, JSON/context, guard off/enabled, 28 test mới và bốn gate PASS | Gate A | [x] |
| W4-06 | Áp dụng cap và guard prompt runtime | [Biên bản](runtime_prompt_budget.md), [receipt](runtime_prompt_budget_review.json): cap backtest 4.000; guard cuối <6.500, 192 ca + dự phòng 600, text/structured boundary và bốn gate PASS | W4-05 | [x] |
| W4-07 | Chèn BRPP và hướng dẫn reasoning | [Biên bản](decision_prior_integration.md), [receipt](decision_prior_integration_review.json): formatter W3, prefix một lần + reasoning, Original rỗng, empty/partial, node offline và bốn gate PASS | W4-06 | [x] |
| W4-08 | Ghép graph với ranh giới chuẩn bị báo cáo | [Biên bản/API](graph_prior_integration.md), [receipt](graph_prior_integration_review.json): Full riêng, Prior Preparation → Decision; 128 ca graph, bốn ablation/async/stream và bốn gate PASS | W4-05, W4-07 | [x] |

## C. PIT, ghép cặp và checkpoint

Chi tiết: [Phase C](phase_c_pit_paired_checkpoint.md).

| Mã | Task | Đầu ra / điều kiện hoàn thành | Phụ thuộc | Trạng thái |
| --- | --- | --- | --- | --- |
| W4-09 | Cài adapter context/regime PIT | [API/biên bản](prior_context_adapter.md), [receipt](prior_context_review.json): hai provider, seal Full/proof, 31 test mới/128 ca graph, 6 replay thật và bốn gate PASS | Gate A, W4-05 | [x] |
| W4-10 | Tạo báo cáo chung cho năm nhánh | [API/biên bản](paired_prior_point.md), [receipt](paired_prior_point_review.json): engine chạy upstream/Full một lần, năm Decision tuần tự; mutation/đảo thứ tự, 15 test mới và bốn gate PASS | Gate B, W4-09 | [x] |
| W4-11 | Ghép retriever vào backtest | [API/biên bản](prior_backtest_integration.md), [receipt](prior_backtest_review.json): walk-forward/schema năm nhánh, nguồn dùng một lần, P&L engine cũ; 16 test mới và bốn gate PASS | W4-09, W4-10 | [x] |
| W4-12 | Lưu và phục hồi tiến trình từng nhánh | [API/biên bản](prior_checkpoint_resume.md), [receipt](paired_checkpoint_review.json): manifest/shared/attempt/nhánh atomic trước API, verifier semantic, OS lock Windows; 22 test mới, 15 ranh giới crash và bốn gate PASS | W4-04, W4-11 | [x] |

## D. Nghiệm thu tích hợp và bàn giao

Chi tiết: [Phase D](phase_d_validation_handoff.md).

| Mã | Task | Đầu ra / điều kiện hoàn thành | Phụ thuộc | Trạng thái |
| --- | --- | --- | --- | --- |
| W4-13 | Kiểm thử leakage toàn đường tích hợp | [Biên bản/coverage](pipeline_leakage_validation.md), [receipt](pipeline_leakage_review.json): 11 test mới trên hai provider/hai scope, nguồn/prior/checkpoint sai bị chặn; sửa verifier provider và bốn gate PASS | Gate C | [x] |
| W4-14 | Smoke E2E offline và tương thích | [Biên bản](prior_integration_smoke.md), [receipt](integration_smoke.json): 8 context tổng hợp bốn regime/VI-EN, 6 replay thật; chỉ mock vision/Decision, paired/resume/flag off/budget/JSON và bốn gate PASS | W4-13 | [x] |
| W4-15 | Chạy bốn gate và kiểm phạm vi thay đổi | [Biên bản](integration_gate_validation.md), [gate](integration_gate_review.json), [hiệu năng](integration_performance_review.json): bốn gate mới PASS, hash/scope/budget, overhead riêng; benchmark bổ sung FAIL p95, rủi ro đã rà/bàn giao, retriever không đổi | W4-14 | [x] |
| W4-16 | Chốt W4, bàn giao điều kiện pilot W5 | 16 task có bằng chứng; hướng dẫn config/resume; gate giá/quota W5 và giới hạn nghiên cứu rõ | W4-01..15 | [ ] |

## Thứ tự và gate chuyển phase

1. W4-01 → 02 → 03 → 04: **Gate A PASS đặc tả**; đủ hợp đồng trước khi sửa runtime.
2. W4-05 → 06 → 07 → 08: **Gate B PASS** state/Decision/graph offline với verifier/retriever fixture.
3. W4-09 → 10 → 11 → 12: **Gate C PASS offline** PIT, dùng chung báo cáo và resume; khóa native Windows.
4. W4-13 → 14 → 15 → 16: **Gate D** đủ bốn gate và biên bản bàn giao.

Nếu task cần chia nhỏ khi triển khai, bổ sung mục con trong phase; giữ mã task
cha và phụ thuộc. Gate thất bại phải sửa nguyên nhân, cập nhật biên bản và chạy
lại phần bị ảnh hưởng; không đánh dấu PASS từ receipt W3.

## Checklist chốt tuần

- [ ] Flag tắt bảo toàn đường chạy cũ; cấu hình mới không thay nghĩa ablation cũ.
- [ ] Mọi context được chứng minh PIT trước query; prior `exit_date < cutoff`.
- [ ] Năm nhánh dùng cùng Full reports; không lặp upstream hoặc chia sẻ mutable state.
- [ ] BRPP ≤600 và toàn prompt backtest <6.500 ở đường runtime thật.
- [ ] Nhãn/P&L dùng engine thật: LONG Open(t+1)→Close(t+3), SHORT cash, phí hai chiều.
- [ ] Checkpoint có provenance/metadata đầy đủ; resume chỉ chạy phần còn thiếu.
- [ ] Compileall/unit/E2E/leakage PASS; smoke offline có receipt riêng.
- [ ] Bàn giao W5 với gate giá thô VCI/KBS, model PIT và quota; không tuyên bố OOS từ mock.

## Nhật ký tiến độ

### 2026-10-06 — W4-15 hoàn thành

- Nhánh `test/prior-integration-gate-review`, baseline `23a3246`; bổ sung công cụ
  đo/receipt và tài liệu, không sửa production, retriever, memory hoặc bank.
- Bốn gate mới PASS: compileall; **498 unit**
  (519.119 giây suite), **E2E** (31.784 giây),
  **93 leakage** (151.326 giây suite).
  **2427 file bảo vệ giữ hash**, bảy AST kinh tế/entry point legacy không đổi.
- Benchmark giữ nguyên phương pháp W3 (100 warm-up/1.000 mẫu mỗi mode/bước,
  bốn mode/hai scope, nearest-rank, không loại ngoại lai): **FAIL p95 retrieval <30 ms**.
  bayesian_regime 35.550 ms, random 30.915 ms, recent 31.740 ms, similarity 40.643 ms.
  Lần đầu Similarity 32,215 ms FAIL được giữ log/hash; lượt đầy đủ mới chạy
  tuần tự sau gate vẫn FAIL, lưu nguyên mẫu. Không nới ngưỡng hay thay thuật toán.
- Điều kiện phải nghiệm thu lại hiệu năng khi sửa retriever/copy/cache không
  kích hoạt: mã retriever, memory/copy và benchmark vẫn nguyên từ W3. W4-15
  hoàn tất rà rủi ro và bốn gate bắt buộc; không tuyên bố gate hiệu năng PASS.
  Cần kiểm lại khi giảm tải/đổi môi trường trước công bố số hiệu năng hoặc pilot.
- Sáu context replay nguồn thật: nạp bank/constructor retriever một lần;
  đo riêng cold load, prepare, verifier/checksum, adapter, formatter và graph
  Decision giả. Query nóng chặn nạp lại JSON/giá/model; vẫn giữ byte checksum.
- `runtime_budget_gate_passed=true` trong receipt mới, cap 4.000, BRPP ≤600,
  prompt <6.500; đóng băng hash template/version và bằng chứng runtime W4-14.
  Receipt lịch sử giữ nguyên. [Biên bản/CLI](integration_gate_validation.md),
  [receipt gate](integration_gate_review.json), [hiệu năng](integration_performance_review.json).
- **Phase D 3/4, W4 15/16**; tiếp theo **W4-16** đóng tuần/bàn giao.
  Gate D, giá OOS/pilot và hiệu quả đầu tư ngoài mẫu chưa nghiệm thu; không gọi LLM thật.

### 2026-10-06 — W4-14 hoàn thành

- Nhánh `test/prior-integration-smoke`, nền `1faeff1`; Conventional Commit
  `test(prior): verify offline integration smoke and legacy compatibility`.
- Thêm `scripts/verify_prior_integration.py` và bốn test; [biên bản/CLI](prior_integration_smoke.md),
  [receipt](integration_smoke.json). Production và E2E legacy giữ nguyên.
- 8 context tổng hợp × năm nhánh; bốn regime, VI/EN, K=0..3, empty/partial/complete.
  Upstream/charts/chỉ báo/Alpha/PIT/graph/checkpoint thật; chỉ giả lập vision và Decision.
  120 Decision continuous/đảo nhánh/resume và 64 Decision K=1/2; nhánh complete giữ field,
  resume chỉ chạy ba Decision thiếu, resume complete giữ byte checkpoint/không API.
- Flag off chạy bốn ablation và entry point cũ, không load bank/model. BRPP đúng 600,
  prompt 6.499 nhận/6.500 chặn trước LLM; max prompt context tổng hợp 4193, BRPP 363.
- Replay bổ sung 6 context thật, 30 nhánh/60 Decision giả; phủ bốn mã, BEAR 4 và
  CONSOLIDATION 2. Thiếu archive → BLOCKED replay; proof sai → lỗi, không giả nguồn.
- Chạy smoke riêng và bốn gate mới: compileall, **498 unit**, E2E legacy,
  **93 leakage PASS**. 2423 file bảo vệ và bảy AST kinh tế/legacy giữ nguyên;
  không đọc key, gọi API thật, fit, tải dữ liệu hoặc sinh lại bank.
- **Phase D 2/4, W4 14/16**. Tiếp theo **W4-15** rà phạm vi/overhead/gate;
  W4-16/Gate D và gate giá OOS/pilot còn mở.

### 2026-10-06 — W4-13 hoàn thành

- Nhánh `test/prior-pipeline-leakage`, baseline `af8c8ca`; thêm suite
  `tests/test_prior_pipeline_leakage.py` với **11 test mới**, tái sử dụng
  fixture nguồn/nhãn engine và các suite leakage hiện có.
- Kiểm public runner và graph thật trên hai provider PIT, hai scope, năm nhánh:
  40 ca graph equal/straddling/future; 60 call ngày sau→ngày trước;
  24 injection pool/selector/population và 12 mutation checkpoint băm lại.
  Giá query future làm đổi evaluation nhưng giữ prompt/Decision; sparse tin
  giữ NEUTRAL/coverage/lý do audit, không lọt sentinel future/undated.
- Phát hiện provider replay có thể trả hash train sai; bổ sung đối chiếu
  độc lập metadata/state với artifact và prefix, cache đủ hash/cutoff/prefix.
  Probe logic baseline nhận proof sai và gọi 5 Decision giả, bản sửa chặn với
  0 upstream/Decision mới. Giữ lifecycle fixed model và retrieval trên RAM.
- Bốn gate: compileall/**494 unit**/E2E/**93 leakage** PASS;
  [biên bản/coverage](pipeline_leakage_validation.md), [receipt](pipeline_leakage_review.json).
  **2.419 file bảo vệ** và bảy AST kinh tế/legacy giữ nguyên hash so baseline.
  Suite mới chặn socket/LLM SDK/fit/crawl, inference fixture; chưa gọi API/OOS.
- **Phase D 1/4, W4 13/16**. Tiếp theo **W4-14** smoke E2E riêng và
  tương thích; W4-14..16/Gate D và giá OOS còn mở. Overhead kiểm độc lập
  endpoint replay mới được ghi rõ để rà theo điều kiện W4-15.

### 2026-10-06 — W4-12 và Phase C hoàn thành

- Nhánh `feat/prior-branch-checkpoint-resume`, baseline `8e947d1`; thêm
  `core/prior_checkpoint.py`, `core/prior_run_lock.py` và `resume=True`
  tại API `run_prior_backtest()`. Giữ ma trận năm nhánh, P&L và đường legacy.
- Manifest và toàn plan durable trước API; shared Full durable trước Decision;
  input/prompt/attempt running durable trước transport, persist ngay nhánh valid.
  Resume seal lại nguồn PIT/replay retrieve/formatter/prompt offline, chỉ gọi
  Decision còn thiếu. Đổi key không đổi signature; config/nguồn/code/schema đổi bị chặn.
- OS handle lock Windows, owner UUID/host/boot/PID/start và recovery audit;
  khóa stale còn file không tự chặn. Finally đóng handle cả khi release lỗi.
  Dọn temp writer đã biết dưới run-dir khi giữ khóa, giữ file khác và archive.
- **22 test mới**, gồm **5 leakage**, **15 ranh giới crash** PASS; quota sau
  hai nhánh có upstream/Full mỗi loại một lần, 5 Decision valid + 1 lỗi,
  không gọi lại nhánh complete. Mất ghi response có thể lặp Decision còn thiếu.
  Upstream/Full mới có intent nhưng thiếu output durable phải dừng ambiguous.
- Bốn gate: compileall/**483 unit**/E2E/**82 leakage** PASS;
  [API/biên bản](prior_checkpoint_resume.md), [receipt](paired_checkpoint_review.json).
  **2.408 file bảo vệ** và bảy AST kinh tế/legacy giữ nguyên; kho 852,
  archive và receipt/spec cũ không đổi. Khóa kiểm native Windows; POSIX chỉ
  mock chọn backend. Chưa gọi API thật hoặc chạy kết quả OOS.
- **Phase C 4/4, W4 12/16, Gate C PASS offline**. Tiếp theo **W4-13** kiểm
  leakage toàn đường tích hợp; W4-13..16/Gate D và giá OOS còn mở.

### 2026-10-06 — W4-11 hoàn thành

- Nhánh `feat/prior-walk-forward-results`, baseline `a58d5d8`; thêm
  `core/prior_backtest.py` và API `BacktestEngine.run_prior_backtest()`.
  Adapter cấp config/giá/events bản sao từ RAM, giữ một kho/retriever mỗi run.
- Kiểm daily, 600 nến, entry/exit/volume/quyền, step≥3 và mọi artifact
  trong plan trước API đầu. Dùng W4-10 mỗi cutoff, giữ một upstream/Full,
  năm Decision tuần tự; giá tương lai chỉ dùng để đánh giá sau năm Decision.
- Ghi identity/point/result strict theo schema W4-04, atomic/hash; giữ raw
  text/tool_calls và response chuẩn hóa, UTC/UUID attempt, full metadata/
  stats/prefix và shared/query/prompt/source hashes. LONG dùng hàm round-trip,
  SHORT CASH; năm tài khoản dùng engine P&L cũ và common support complete.
- **16 test mới**, gồm **3 leakage** PASS: lịch prefix/fixed, lãi/lỗ/return
  đúng 0/CASH/lãi kép, schema/JSON/metadata, stop/callback, quota/output sai,
  artifact sai trong plan và kho đổi giữa hai điểm. Hai cutoff: upstream/
  Full mỗi loại hai lần, **10 retrieve/10 Decision**; không nạp/chấm lại kho.
- Bốn gate: compileall/**461 unit**/E2E/**77 leakage** PASS;
  [biên bản/API](prior_backtest_integration.md), [receipt](prior_backtest_review.json).
  **2.407 file bảo vệ** giữ hash; kho/archive/receipt trước và AST kinh tế/
  các entry point legacy được kiểm. Kiểm chứng fixture, chưa chạy API/OOS.
- **Phase C 3/4, W4 11/16**. Tiếp theo **W4-12**: persist shared/nhánh trước
  crash, OS lock và resume. W4-11 giữ file của điểm hoàn tất; chưa phục hồi
  nhánh đang dở. Gate C/D và giá thực thi OOS còn mở.

### 2026-10-06 — W4-10 hoàn thành

- Nhánh `feat/paired-prior-decisions`, baseline `7d44f44`; thêm API
  `BacktestEngine.run_prior_point()` và `PriorPointContext.prior_config` trả bản sao.
  Full builder nhận tùy chọn strict riêng; mặc định/ablation legacy giữ nghĩa.
- Kiểm PIT trước upstream, tạo ảnh không ghi file phụ; ba agent upstream một
  lần, Alpha/Sentiment Full một lần. Kiểm upstream không đổi snapshot/window
  trước Alpha. Shared seal rồi deep copy mới sang năm nhánh seed=42/same_symbol.
- Năm retrieve/format/Decision tuần tự, bốn khoảng nghỉ; Original K=0 rỗng,
  bốn prior cùng stats population. Output JSON giữ full bundle và metadata;
  không có runtime object/outcome query. Lỗi/stop dừng, không fallback hay tự
  lặp upstream; khóa RAM chặn song song cùng engine.
- **15 test mới**, ma trận hai provider × VI/EN **4 điểm/20 Decision**,
  text/structured, mutation/đảo thứ tự và ba ca leakage trước Full PASS.
  Bốn gate: compileall/**445 unit**/E2E/**74 leakage** PASS; [receipt](paired_prior_point_review.json)
  giữ hash **2.402 file bảo vệ**, kho/archive/receipt trước, AST kinh tế và các phương thức legacy.
- **Phase C 2/4, W4 10/16**. Tiếp theo **W4-11** vòng walk-forward/kết quả
  kinh tế; W4-12 checkpoint/resume, Gate C/D và giá OOS còn mở.

### 2026-10-06 — W4-09 hoàn thành

- Nhánh `feat/prior-point-in-time-context`, baseline `5530eba`; thêm
  `core/prior_context.py`, helper fixture và hai suite adapter/leakage.
- Nạp retriever/kho/QA một lần, kiểm byte manifest/CSV/evidence/events/tin/
  VNINDEX trước upstream; replay prefix verify-only hoặc model fixed train
  end ≤ freeze < cutoff. Model/scaler/calibration và full prefix được kiểm,
  không fit/crawl/API hoặc tự đổi provider.
- Seal năm Full reports và tín hiệu với source proof; Alpha bảng/đồng thuận,
  sparse sentiment và coverage trước cap hiển thị. Graph dùng callback kiểm
  nguồn trước retrieve và result trước formatter; deep copy, không outcome query.
- Journal COMPLETE giữ identity gốc, chữ ký input W2, episode/regime/hash;
  parser Trend viết tắt chỉ nhận report có biên bản đóng băng, không chạy mã cũ.
- **31 test mới, 128 ca hai provider/VI/EN/mode/K/text/structured**, và
  **6 replay nguồn/checkpoint thật** với Decision giả PASS. Bốn gate mới:
  compileall/**430 unit**/E2E/**71 leakage** PASS; [receipt](prior_context_review.json)
  ghi log/hash; **2.399 file bảo vệ** gồm kho/archive/receipt trước giữ nguyên byte.
- **Phase C 1/4, W4 9/16**. Tiếp theo **W4-10** dùng chung Full và năm
  Decision trong engine; W4-11/12, Gate C/D và giá OOS còn mở.

### 2026-10-06 — W4-08 hoàn thành

- Nhánh `feat/shared-reports-prior-graph`, baseline `740031a`; thêm
  `compile_full_preparation()` và `compile_report_decision()` trong `utils/graph_setup.py`.
  Giữ `compile_upstream()`, hai builder cũ, `include_alpha` và bốn ablation.
- Full chuẩn bị Alpha/Sentiment riêng; Prior Preparation sở hữu retrieve/format
  một lần, Decision tiêu thụ output ngay sau đó. Config khóa lúc compile;
  state thô lỗi/alias/outcome/stale result bị chặn trước lọc channel.
- Verifier kiểm context trước query, result trước formatter; callback nhận
  bản sao JSON riêng. Default enabled thiếu verifier vẫn dừng; không lưu cờ PASS.
  API async/stream chuyển tiếp đúng config/kwargs; checkpoint chưa triển khai.
- **13 test mới**, **128 ca graph thật** PASS; đủ tám channel, Original/empty/
  partial, bốn ablation, deep copy, lỗi nguồn/API/overflow. Năm nhánh fixture:
  upstream mỗi node một lần, Alpha/Sentiment một lần, Decision năm lần.
- Max prompt **6.264**, BRPP đủ 600 + reasoning **6.467**. Compileall/**399 unit**/
  E2E/**56 leakage** PASS; [receipt](graph_prior_integration_review.json) ghi log/hash
  và kiểm byte các file bảo vệ. Kho/archive/receipt trước giữ nguyên.
- **Phase B 4/4, W4 8/16, Gate B PASS offline graph/prompt với fixture**.
  Tiếp theo **W4-09** adapter xác minh nguồn PIT thật. Điều phối năm nhánh trong
  engine, checkpoint/resume, Gate C/D, pilot LLM và OOS còn mở.

### 2026-10-06 — W4-07 hoàn thành

- Nhánh `feat/decision-prior-prefix`, baseline `75584b2`; thêm
  `core/decision_prior.py`, hook verifier nguồn tại factory Decision và
  `tests/test_decision_prior_integration.py`. Chữ ký cũ/ablation/live giữ tương thích.
- Kiểm config/query/Full reports, JSON, context/bank proof, tasks PIT/scope và
  metadata/counts/scores/stats; source verifier thành công trước formatter W3.
  Prefix phải đúng formatter, ≤600; một lần trước `### [1]`, reasoning VI/EN 181 ký tự.
- Original enabled K=0 vẫn kiểm nguồn/context/metadata; prompt bằng disabled
  khi cùng báo cáo/daily, không prefix/reasoning/stats. Empty/partial giữ None,
  mẫu số, status/reason; output và projection verifier có bản sao riêng.
- **11 test mới PASS**, capture text/structured cho năm nhánh và K=0..3;
  lỗi nguồn/API/output không bị nuốt, input sai không gọi LLM, overflow không
  truncate hoặc chuyển cash. Guard `<6500` sau toàn bộ BRPP/hướng dẫn.
- Receipt đo **128 ca node thật** với verifier/LLM fixture, max **6.264**;
  BRPP đúng **600** + reasoning có max **6.467**, còn 33 đến ngưỡng bị chặn.
  Alias daily canonical=`1d`; fixture không là bằng chứng source/model PIT.
- Bốn gate PASS: compileall; **386 unit** (97,298 giây), **E2E**
  (15,4 giây pipeline), **56 leakage** (9,010 giây). **2.391 file bảo vệ giữ hash**;
  kho 852 episode và receipt/spec W3/Phase A/W4-05/06 nguyên byte.
- [Biên bản](decision_prior_integration.md), [receipt](decision_prior_integration_review.json).
  **Phase B 3/4, W4 7/16**; Gate B còn W4-08 graph. Default/graph vẫn chặn
  enabled chưa có verifier nguồn thật W4-09; retrieve/paired/checkpoint và
  pilot/OOS chưa nghiệm thu. Tiếp theo **W4-08** ranh giới chuẩn bị Full và Decision.

### 2026-10-06 — W4-06 hoàn thành

- Nhánh `feat/decision-runtime-prompt-budget`, baseline `c0ab80a`; cap riêng
  backtest trend/pattern/indicator 800, alpha 1.100, sentiment 500 (tổng 4.000).
  Giữ cap live 4.500, chữ ký helper cũ và logic distill đầu/cuối/heading.
- Guard prompt cuối **<6.500** sau builder/hướng dẫn/schema chuỗi, trước retry
  wrapper và vòng format retry. Overflow ném `ValueError`, không gọi LLM hoặc
  trả quyết định thay lỗi. Log ghi cap/report/prefix/prompt và đúng ngưỡng.
- **11 test ngân sách PASS (8 mới)**: node thật trên **192 ca** VI/EN/daily/
  bốn mã/tổ hợp báo cáo; giữ hợp đồng kinh tế/conflict, đầu/cuối và input.
  Builder thật tại 6.499/6.500 xác minh text và structured output; retry giữ
  prompt đã kiểm, live giữ cap cũ, báo cáo thiếu và tên mã dài được kiểm.
- Prompt lớn nhất ma trận **5.688**; bốn fixture mở rộng builder với BRPP thật
  **600 ký tự** có max **6.289**, còn 211 đến ngưỡng bị chặn. Chèn/reasoning
  production vẫn chờ W4-07, phải đo lại sau khi thay template.
- Bốn gate PASS: compileall; **375 unit** (103,910 giây), **E2E**
  (15,5 giây pipeline), **56 leakage** (9,035 giây). **2.388 file bảo vệ giữ hash**;
  kho 852 episode, receipts W3/Phase A/W4-05 nguyên byte.
- [Biên bản](runtime_prompt_budget.md), [receipt](runtime_prompt_budget_review.json)
  ghi hash/lệnh/log/ma trận/phạm vi. **Phase B 2/4, W4 6/16**; Gate B và gate
  budget toàn luồng prior còn mở. Tiếp theo **W4-07** chèn BRPP/reasoning;
  graph/PIT/paired/checkpoint/pilot và giá OOS còn các task/gate riêng.

### 2026-10-05 — W4-05 hoàn thành

- Nhánh `feat/prior-runtime-state-config`, baseline `f2906b9`; thêm
  `core/prior_config.py`, tám field optional trong schema graph production và
  guard state trước/sau node tại ba builder hiện có; giữ topology/chữ ký cũ.
- Parser tám key strict, default disabled; enum/K/seed/path theo policy,
  enabled Full/backtest/daily, Original K=0 vẫn enabled; ablation và cờ cũ giữ nghĩa.
- JSON native/finite và deep copy; helper query kiểm ngày ISO/regime/tín hiệu.
  Flag off không I/O kho; dữ liệu prior còn sót bị từ chối. Enabled tự khai
  provenance không đủ, dừng trước node đến khi có adapter PIT W4-09.
- **28 test mới PASS**, gồm policy/ví dụ khóa, path containment, off/Original,
  conflict/legacy, JSON/date/ownership, optional schema và channel graph thật.
  Probe schema enabled không là phép chạy prior production đã xác minh nguồn.
- Bốn gate mới PASS: compileall; **367 unit** (59,045 giây), **E2E**
  (pipeline 7,8 giây), **56 leakage** (5,773 giây). **2.384 file bảo vệ giữ hash**;
  259 file W4-01 còn nguyên, hai file runtime state/graph được sửa có chủ đích.
  Receipt/spec Phase A và kho 852 episode giữ nguyên byte.
- [Biên bản runtime](state_config_runtime.md), [receipt](state_config_runtime_review.json)
  ghi nguồn/lệnh/log/hash/phạm vi. **Phase B 1/4, W4 5/16**; Gate B còn mở.
  Tiếp theo **W4-06** cap/guard prompt; BRPP/graph nghiên cứu, PIT, retrieve,
  checkpoint và giá thực thi OOS chưa nghiệm thu.

### 2026-10-05 — W4-04 và Phase A hoàn thành

- Nhánh `docs/research-checkpoint-contract`, baseline `e3aa3f8`; khóa
  [contract kết quả/checkpoint](checkpoint_contract.md), schema/policy/ví dụ và receipt riêng.
- Ba loại envelope: run manifest, point checkpoint và result dẫn xuất; schema
  nghiên cứu riêng, giữ Full/No-Alpha/legacy reader khi flag tắt.
- Identity khóa config/plan/bank/nguồn/model/template/code; key và hash key
  không được lưu. Shared Full durable trước Decision, persist từng nhánh;
  resume không gọi lại branch complete, không đưa evaluation vào agent.
- Chốt OS lock giữ bằng handle; khóa còn file không tự chặn resume. Crash
  upstream/Full chưa có output durable phải dừng ambiguous; không tự lặp vision.
  Crash sau nhánh cuối chỉ evaluate/seal/rebuild result offline.
- **4 document mẫu**, **7 shape trạng thái**, **11 ca schema sai**, **5 projection
  retriever thật**, **8 mutation signature**, **3 probe atomic/strict reader** PASS.
  Decision là fixture; failpoint/lock/resume mới chưa triển khai, chờ W4-12.
- Bốn gate mới: compileall; **339 unit** (130,278 giây), **E2E** (17,6 giây),
  **56 leakage** (6,097 giây) PASS. 2.312 file giữ hash; kiểm lại 261 file
  bằng chứng W4-01. Receipt W4-01..03 giữ nguyên.
- **Gate A PASS_CONTRACTS_ONLY**, Phase A **4/4**, W4 **4/16**.
  Tiếp theo **W4-05** state/config validator; runtime budget/paired/checkpoint,
  Gate B/C/D, pilot LLM W5 và giá thực thi OOS 2023–2024 còn mở.

### 2026-10-05 — W4-03 hoàn thành

- Nhánh `docs/prior-provenance-contract`, baseline `545e34c`; khóa
  [provenance v1](provenance_contract.md), policy, ví dụ và receipt riêng.
- Chốt giá raw VCI/crosscheck KBS, hash snapshot/window/Alpha; tin dated ≤cutoff,
  coverage trước giới hạn hiển thị và NEUTRAL có lý do khi thiếu ba bài.
- Replay dùng artifact train-end=cutoff, readonly `verify_only=True`; OOS dùng
  model đóng băng train-end<cutoff, kiểm toàn prefix train và ba component.
  Model full-train `RESEARCH_ONLY/UNVERIFIED` chỉ dùng probe kỹ thuật.
- Năm context nguồn thật (bốn mã và biên bằng exit), hai ví dụ provenance đầy đủ;
  **14 probe API hiện có PASS**. **14 ca adapter chỉ là đặc tả** cho W4-09/13.
  Outcome query giữ ngoài state/retriever; lỗi nguồn dừng trước upstream,
  lỗi tín hiệu trước retrieve, lỗi pool/stats trước formatter/Decision.
- Compileall / **339 unit** (48,126 giây) / **E2E** / **56 leakage** (5,077 giây)
  PASS; 2.308 file nguồn/bằng chứng/archive giữ hash trước/sau gate.
- **Tiếp theo W4-04** khóa schema/signature/checkpoint. Tiến độ **3/16**,
  Phase A **3/4**; Gate A, adapter/provider OOS runtime và gate giá OOS còn mở.

### 2026-10-05 — W4-02 hoàn thành

- Nhánh `docs/prior-state-config-contract`, baseline `62a673a`; [contract](integration_contract.md)
  và policy/ví dụ khóa config/state, lỗi và ownership dữ liệu; chưa sửa runtime.
- Flag off không I/O nguồn mới; Original enabled K=0 vẫn query/validate. Prior
  enabled chỉ ablation Full trong backtest, cấu hình độc lập với ablation cũ.
  Daily nhận `1d`/`1 ngày`, canonical=`1d`; adapter mới từ chối `1 day`.
- Bảy ví dụ config và bốn projection W3 đã đối chiếu; prefix 0/338/190/237 ký tự,
  bảy probe query sai W3 PASS. Các ca config mới chờ validator W4-05.
- Compileall / **339 unit** (91,391 giây) / **E2E** (13,8 giây) / **56 leakage**
  (7,637 giây) PASS; [receipt](state_config_review.json) ghi hash/version/log.
- **Tiếp theo W4-03**: provenance và trình tự PIT. W4-04/checkpoint, Gate A,
  runtime integration/budget và giá OOS còn mở; tiến độ 2/16, Phase A 2/4.

### 2026-10-05 — W4-01 hoàn thành

- Kiểm đầu vào trên baseline `516d0ed`, nhánh `docs/prior-runtime-readiness`:
  99 file bằng chứng + 176 file nguồn bàn giao W3 khớp checksum; 852 record
  đúng schema/nhãn kinh tế, 852 cặp episode/signal, 217 prefix và staging khớp.
- Replay mới 32 context: **288 query + 288 lượt lặp**, BRPP max **373**, đủ
  mode/scope và Original. Không gọi LLM/mạng, fit model hoặc sinh episode.
- Bốn gate **compileall / 339 unit / E2E / 56 leakage PASS**; số liệu/lệnh/log/hash
  tại [receipt](input_readiness.json). Giữ 261 file bảo vệ trước/sau gate.
- [Biên bản](input_readiness.md) có luồng live/backtest, điểm nối, schema callback/
  web và khoảng trống resume nhánh; `.gitattributes` bảo toàn byte receipt W4.
- W4-02 tiếp tục khóa state/config; cap/guard runtime, provider PIT/OOS và
  gate giá thô 2023–2024 chưa PASS. **Phase A chưa hoàn thành.**

### 2026-10-05 — Lập kế hoạch

- Đã khảo sát bàn giao W3, state/graph/Decision, đường backtest ghép cặp và test hiện có.
- Chia 16 task vào bốn phase; khóa ranh giới W4 offline và pilot W5.
- Chưa triển khai task W4, chưa thay đổi runtime/kho/model hoặc mở gate giá OOS.
- Kiểm tra năm tài liệu: đủ 16 task/16 mục chi tiết duy nhất, liên kết hợp lệ,
  tất cả checklist triển khai đang mở; `git diff --check` PASS.
- Gate trước khi merge nhánh kế hoạch `docs/runtime-prior-integration-plan`:
  compileall PASS; **339/339 unit** (47,935 giây), E2E xác định **7,0 giây**,
  **56/56 leakage** (5,111 giây) PASS. Lệnh theo AGENTS.md và [Phase D](phase_d_validation_handoff.md).
- Đây là kiểm hồi quy cho thay đổi tài liệu trên runtime hiện có; không là
  nghiệm thu các task W4-05..15, runtime prior/budget hoặc dữ liệu OOS.
