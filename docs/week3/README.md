# Tuần 3 — Bayesian Prior Retriever và BRPP

**Trạng thái: Phase A/B/C hoàn thành, Gate A/B/C PASS cho API và kiểm chứng offline. W3-13/W3-14/W3-15 hoàn thành: bốn gate tích hợp và bằng chứng offline trên phiên bản sau tối ưu đều PASS. Tiếp theo W3-16 chốt/bàn giao; Phase D chưa chốt. W4 phải áp dụng cap đã kiểm và guard prompt cuối cùng; chưa PASS ngân sách runtime tích hợp.**

Kế hoạch chi tiết cho [W3 trong kế hoạch tổng](../plan/plan.md), tiếp nối
[biên bản chốt W2](../week2/phase_d_week_close.md). Mỗi task xử lý một phần có thể
kiểm tra độc lập; thực hiện theo phụ thuộc, không đánh dấu xong chỉ vì đã viết code.

## Mục tiêu và phạm vi

- `core/bayesian_retriever.py`: API độc lập, bốn chế độ `bayesian_regime`,
  `random`, `recent`, `similarity`, mặc định K=3, truy xuất point-in-time.
- Thống kê theo regime với mẫu số rõ ràng; không diễn giải tỷ lệ mẫu là xác suất
  thành công đã được hiệu chuẩn của LLM.
- `format_compact_prior_prefix(tasks, stats)`: BRPP tối đa 600 ký tự cho K=3.
- Unit tests, leakage tests và benchmark retrieval dưới 30 ms theo phép đo chốt trước.

W3 chuẩn bị API và kiểm thử prompt ghép thử bằng hàm hiện có. Tích hợp vào state,
Decision Agent, LangGraph và backtest thuộc W4; pilot/API LLM thuộc W5.

## Đầu vào đã có và giới hạn

| Đầu vào | Trạng thái / cách dùng |
| --- | --- |
| `data_manager/regime_memory_store.json`, manifest và biên bản bộ đọc | 852 episode đã QA, giữ nguyên schema và nhãn kinh tế |
| `docs/week2/memory_bank_audit.json` | PASS; hash kho phải khớp trước khi dùng |
| `core/bayesian_memory.py` | Tái sử dụng validator, bản sao dữ liệu và `eligible()` với cutoff nghiêm ngặt |
| `core/regime_detector.py`, model | Nhận regime PIT đã xác minh; model toàn tập train không được dùng cho ngày trước cuối train |
| `docs/methodology_spec.md`, schema W1 | Hợp đồng nghiên cứu và cấu trúc record |

Kho phủ 2020–2022 vì warm-up 600 phiên; đủ bốn mã/bốn regime, nhưng sentiment đều
NEUTRAL do thiếu tin. Không coi sentiment hằng là thông tin phân biệt khi đo similarity.
Gate giá thô kiểm định 2023–2024 chưa mở: W3 vẫn làm được với kho đóng băng và fixture
offline; smoke truy xuất không phải benchmark giao dịch ngoài mẫu.

## Quy tắc theo dõi

- `[ ]` chưa xong; `[x]` chỉ khi đầu ra và kiểm tra đều đạt. Nếu bị chặn, ghi lý do.
- Sau mỗi task: cập nhật bảng bên dưới, checklist trong tài liệu phase và nhật ký
  gồm ngày, file/commit, lệnh kiểm tra, kết quả và giới hạn còn lại.
- Nhánh riêng từ `develop` theo `AGENTS.md`; commit mô tả kỹ thuật, không có mã tuần.
  Merge chỉ sau bốn gate PASS. Giữ nguyên P&L, cutoff, distill/cap và upstream ghép cặp.
- Tên file/module/test trong kế hoạch là đầu ra dự kiến, chưa tồn tại chỉ vì được liệt kê.

## A. Chốt hợp đồng và phương pháp

Chi tiết: [Phase A](phase_a_contract_and_method.md).

| Mã | Task | Đầu ra / điều kiện hoàn thành | Phụ thuộc | Trạng thái |
| --- | --- | --- | --- | --- |
| W3-01 | Kiểm tra đầu vào và ranh giới W3 | [Biên bản Phase A](phase_a_contract_and_method.md#04102026--w3-01-hoàn-thành), [receipt](input_readiness.json): hash/QA/852 record PASS; cutoff/deep copy/không I/O mỗi query xác minh; ranh giới W4 và phép đo khóa | W2 hoàn thành | [x] |
| W3-02 | Chốt API truy vấn và kết quả | [Hợp đồng API v1](retriever_api_contract.md): kiểu query/result, bốn mode, K=0..3, seed, scope cùng mã/pooled, metadata/counts/score, lỗi và thiếu mẫu đã chốt | W3-01 | [x] |
| W3-03 | Chốt cách chọn prior và similarity | [Luật chọn prior](prior_selection_method.md), [policy v1](prior_selection_policy.json): bốn mode, alias/NFC, score bốn trường, tie-break, seed theo query; thiếu mẫu giữ pool, không ranking bằng outcome | W3-02 | [x] |
| W3-04 | Chốt thống kê và mẫu BRPP | [Hợp đồng stats/BRPP](statistics_and_prefix_contract.md), [policy](statistics_prefix_policy.json): bốn metric có counts, mẫu số 0=None, không smoothing; template/600 ký tự/K=0..3/thiếu tin đã khóa | W3-02, W3-03 | [x] |

## B. Retriever và thống kê

Chi tiết: [Phase B](phase_b_retriever_and_statistics.md).

| Mã | Task | Đầu ra / điều kiện hoàn thành | Phụ thuộc | Trạng thái |
| --- | --- | --- | --- | --- |
| W3-05 | Nạp kho, lọc PIT và bảo vệ dữ liệu | `core/bayesian_retriever.py`: constructor/prepare_query/K=0, chốt pool/selection/cutoff; 14 test nền/leakage và [probe kho thật](retriever_foundation_review.json) PASS; [phạm vi](phase_b_retriever_and_statistics.md) | W3-01..04 | [x] |
| W3-06 | Cài `recent` và `random` | `select_prior_tasks`: thứ tự/tie-break/seed/draw đúng policy, metadata empty/partial/complete; tám test mới và [probe kho thật](recent_random_review.json) PASS ([Phase B](phase_b_retriever_and_statistics.md)) | W3-05 | [x] |
| W3-07 | Cài `similarity` | `signal_match_v1`, ranking score/exit/ID, metadata score float; chín test mới, leakage và [probe kho thật](similarity_review.json) PASS ([Phase B](phase_b_retriever_and_statistics.md)) | W3-03, W3-05 | [x] |
| W3-08 | Cài `bayesian_regime` | Chọn population cùng regime bằng ranking Similarity; metadata empty/partial/complete, mười test mới và [probe kho thật](bayesian_regime_review.json) PASS ([Phase B](phase_b_retriever_and_statistics.md)) | W3-06, W3-07 | [x] |
| W3-09 | Tính thống kê theo regime | Bốn metric trên toàn population PIT, API `retrieve` đầy đủ; fixture tính tay/zero-return/null/native JSON, 14 test mới và [probe kho thật](statistics_runtime_review.json) PASS; Gate B PASS | W3-04, W3-05 | [x] |

## C. Tiền tố và ngân sách prompt

Chi tiết: [Phase C](phase_c_prefix_and_budget.md).

| Mã | Task | Đầu ra / điều kiện hoàn thành | Phụ thuộc | Trạng thái |
| --- | --- | --- | --- | --- |
| W3-10 | Định dạng BRPP compact | Formatter/schema/nhãn/mẫu số theo policy, guard ≤600, 13 test mới và [receipt mẫu](prefix_formatter_review.json) PASS; ngân sách W3-11 và smoke W3-12 đã kiểm | W3-08, W3-09 | [x] |
| W3-11 | Kiểm tra 600 ký tự và prompt ghép | Chín test mới; [receipt](prompt_budget_review.json) kiểm 1.024 ca VI/EN, biên BRPP đúng 600; prompt bàn giao tối đa 6.289. Cap cũ vượt trần khi ghép BRPP; phương án cap 4.000 và guard cuối cùng bàn giao W4, chưa sửa runtime ([Phase C](phase_c_prefix_and_budget.md)) | W3-10 | [x] |
| W3-12 | Smoke offline trên kho thật | `scripts/verify_bayesian_prior.py`, [receipt](prior_smoke.json): 32 context, 288 query và 288 lượt lặp, đủ bốn mode/hai scope, nguồn prefix PIT và các biên; BRPP tối đa 373, sáu test mới PASS; Gate C offline PASS ([Phase C](phase_c_prefix_and_budget.md)) | W3-06..11 | [x] |

## D. Leakage, hiệu năng và bàn giao

Chi tiết: [Phase D](phase_d_validation_and_handoff.md).

| Mã | Task | Đầu ra / điều kiện hoàn thành | Phụ thuộc | Trạng thái |
| --- | --- | --- | --- | --- |
| W3-13 | Kiểm thử hành vi và zero-leakage | Mười leakage + hai behavior test mới, fixture nhãn từ engine thật; suite 95 test Bayesian, kiểm cả ranking/stats/BRPP, nguồn sai gây lỗi trước formatter; [biên bản và bảng coverage](phase_d_validation_and_handoff.md) | W3-05..12 | [x] |
| W3-14 | Benchmark retrieval tái lập | `scripts/benchmark_bayesian_retriever.py`, [receipt](retrieval_benchmark.json), [biên bản/profile](phase_d_validation_and_handoff.md): 32 query/mode, 100 warm-up và 1.000 mẫu/mode/giai đoạn; p95 15,809 / 14,812 / 14,179 / 18,239 ms PASS; cold load riêng, giữ hai lượt FAIL và tối ưu bản sao/so snapshot | W3-12, W3-13 | [x] |
| W3-15 | Chạy bốn gate trước tích hợp | [Receipt chốt](integration_gate_review.json), [biên bản](phase_d_validation_and_handoff.md): compileall, 339 unit, E2E, 56 leakage PASS; refresh ngân sách/smoke và [benchmark](retrieval_benchmark_integration.json), hash dữ liệu/code không đổi | W3-13, W3-14 | [x] |
| W3-16 | Chốt deliverables và bàn giao W4 | API/docs/example/benchmark đủ; cập nhật kế hoạch tổng, Conventional Commit/merge sau gate | W3-01..15 | [ ] |

## Thứ tự triển khai đề xuất

1. Chốt Phase A trước khi viết thuật toán; xử lý mọi điểm chưa quyết định ở A.
2. Làm W3-05 → W3-06 → W3-07 → W3-08 → W3-09, kèm test từng phần.
3. Làm W3-10 → W3-11 → W3-12 để kiểm ngữ nghĩa và độ dài trên kho thật.
4. Làm W3-13 → W3-14 → W3-15 → W3-16; sửa lỗi rồi chạy lại gate bị ảnh hưởng.

## Checklist chốt tuần

- [x] Bốn chế độ dùng cùng pool hợp lệ trước bộ lọc/xếp hạng riêng của từng mode.
- [x] Mọi prior và thống kê đều từ `exit_date < as_of_date`, không dùng nhãn query.
- [x] K=3, seed/scope/metric được đóng băng, thiếu mẫu có metadata rõ ràng.
- [x] BRPP ≤600 ký tự; prompt ghép thử <6.500 với cấu hình bàn giao đã kiểm. Cap runtime cũ chưa đủ khi ghép BRPP; W4 phải áp dụng phương án và guard cuối cùng.
- [x] Retrieval p95 <30 ms từng mode theo phép đo đã chốt; [receipt kho thật](retrieval_benchmark.json), đầy đủ mẫu thô và môi trường.
- [x] Unit tests, E2E và leakage PASS; API độc lập đã kiểm trên phiên bản sau tối ưu. Bàn giao chính thức ở W3-16, cap/guard runtime ở W4.

## Nhật ký tiến độ

### 2026-10-05 — W3-15

- **Bốn gate chốt PASS** trên commit nền `5e720ab`: compileall; **339/339** unit
  (56,360 giây, gồm 104 Bayesian); E2E xác định **7,0 giây**;
  **56/56** leakage (5,196 giây). [Receipt](integration_gate_review.json) ghi
  lệnh, mã thoát, thời gian thực toàn tiến trình, hash log/nguồn/bằng chứng.
- Chạy lại kiểm ngân sách và smoke sau tối ưu W3-14, giữ bản trước trong
  [ngân sách cũ](prompt_budget_review_before_integration.json) và
  [smoke cũ](prior_smoke_before_integration.json). Ngân sách chỉ đổi hash nguồn;
  context/đầu ra smoke giữ nguyên: 288 query + 288 lượt lặp, BRPP tối đa 373.
  Prompt bàn giao tối đa 6.086, dự phòng đủ BRPP 600 tối đa 6.289 (<6.500).
- [Benchmark chốt](retrieval_benchmark_integration.json) cùng phép đo W3-14:
  p95 Bayesian/Random/Recent/Similarity **15,522 / 13,823 / 13,912 / 18,299 ms**,
  cả bốn <30 ms. Giữ receipt W3-14 như kết quả lịch sử; không gộp hoặc chọn mẫu
  tốt nhất giữa các lượt. Cold load/formatter/toàn chuỗi vẫn được báo riêng.
- Hash toàn bộ file đã track trong code/data/outputs và bằng chứng được đối chiếu
  trước/sau gate. Task chỉ cập nhật tài liệu/receipt, không sửa runtime, nhãn P&L,
  upstream, retry, kho/model hoặc `.env`. Nhánh `test/prior-integration-gates`
  tích hợp sau gate; tiếp theo **W3-16**, chưa chốt Phase D hoặc runtime W4.

### 2026-10-05 — W3-14

- **Hoàn thành benchmark** trên kho thật 852 episode: 16 context quan sát PIT,
  hai scope thành 32 query/mode, K=3/seed=42; đo tuần tự ba giai đoạn, không gọi LLM.
  P95 retrieval Bayesian/Random/Recent/Similarity lần lượt
  **15,809 / 14,812 / 14,179 / 18,239 ms**, đều <30 ms.
- Giữ [baseline FAIL](retrieval_benchmark_baseline.json),
  [lượt sao chép FAIL](retrieval_benchmark_copy.json), [profile](retrieval_profile.json)
  và [receipt cuối PASS](retrieval_benchmark.json). Tối ưu sao chép sâu schema phẳng
  và so snapshot sau profile; giữ validation/cutoff/kiểu dữ liệu/bản sao độc lập.
- Thêm chín test phép đo/copy/snapshot, không đặt ngưỡng thời gian thật trong unit test.
  Bốn gate task PASS: compileall, **339/339** unit (gồm **104** Bayesian),
  E2E **7,0 giây**, leakage **56/56**.
  Chi tiết môi trường, kết quả gate tích hợp và lệnh chạy lại ở [Phase D](phase_d_validation_and_handoff.md).
- W3-15/W3-16 chưa chốt; W4 còn cap/guard runtime. Receipt ngân sách/smoke cũ
  giữ như snapshot: khi chạy lại smoke đầy đủ cần refresh kiểm ngân sách trước
  do hash module đã thay đổi. Benchmark mới đã đối chiếu output hiện tại với
  oracle và smoke cũ, archive/kho/giá/model không đổi.

### 2026-10-05

- **W3-13 hoàn thành — Phase D đang triển khai**: mở rộng test leakage toàn pipeline,
  thêm `test_bayesian_prior_behavior.py` và fixture chung sinh nhãn bằng engine
  T+2.5 thật. Mười test leakage mới kiểm bốn mode/hai scope: equal/straddling/future,
  thêm/sửa lịch sử chưa đóng, ngày sau → trước, source/selector/population sai gây
  ValueError trước BRPP, tách query khỏi outcome và bản sao nhánh độc lập.
- Hai test behavior kiểm 56 input sai kể cả K=0 trước đọc pool và 256 tổ hợp
  mode/scope/regime/K=0..3 với JSON strict/kiểu Python gốc/input không đổi/no I/O.
  Suite hợp nhất **95 test Bayesian**; [coverage và lệnh tái lập](phase_d_validation_and_handoff.md).
  Sửa nhãn **đã đóng** được phép đổi stats/BRPP, nhưng IDs/scores/seed không ranking
  theo WIN; sửa chu kỳ chưa đóng không được đổi bằng chứng query cũ.
- **Gate tích hợp W3-13**: compileall PASS, 330/330 unit tests PASS (48,346 giây),
  E2E xác định PASS (7,2 giây), 56/56 leakage tests PASS (5,360 giây); suite
  Bayesian 95/95 PASS (3,854 giây). Nhánh `test/prior-zero-leakage-suite` tích hợp
  sau gate; hash receipt W3-11/12, liên kết và `git diff --check` được kiểm trước commit.
  Runtime và các receipt/kho/model giữ nguyên. **W3-14..16 còn mở**; chưa đo p95,
  chưa chốt Phase D hoặc áp dụng cap/guard prompt vào runtime W4.

- **W3-12 hoàn thành — Phase C/Gate C offline PASS**: script smoke trên kho thật
  đã QA 852 episode; 16 context lịch sử phủ bốn mã/bốn regime, tám context lịch sử
  kiểm exit bằng cutoff/thiếu K, tám fixture biên trước/sau kho. Query lịch sử có
  artifact HMM/scaler/calibration prefix đúng ngày và checksum tín hiệu/giá/tin;
  fixture dùng tín hiệu/regime cố định, không suy ra trạng thái thị trường ngày đó.
- [Receipt smoke](prior_smoke.json): **288 query + 288 lượt lặp**, bốn mode/hai scope,
  K=3 và Original K=0. Counts/stats/ranking/score/seed khớp tham chiếu độc lập trên
  population PIT; 176 complete, 64 empty, 16 partial, 32 disabled. Prefix lớn nhất
  **373 ký tự**; input và file bằng chứng giữ nguyên. Chặn mạng, fit/sinh episode,
  đọc JSON/giá trong query; cold load nạp giá đúng một lần/mã.
- Sáu test mới kiểm receipt/kho đã commit và lỗi nguồn/query; unit suite không
  phụ thuộc archive local vốn bị gitignore. CLI tái lập smoke cần archive W2
  `outputs/historical_memory_run/` đầy đủ, thiếu/sai hash gây lỗi, không tự tạo lại.
  **Gate tích hợp W3-12**: compileall PASS, 318/318 unit tests PASS (96,853 giây),
  E2E xác định PASS (13,7 giây), 46/46 leakage tests PASS (6,645 giây).
  Hash nguồn/bằng chứng, liên kết Markdown và `git diff --check` PASS;
  nhánh `test/offline-prior-smoke` tích hợp sau gate.
- Gate C giữ điều kiện W3-11: cap bàn giao tổng 4.000 đã kiểm, guard prompt cuối
  `<6500` còn phải áp dụng ở W4. Smoke không đo p95 hoặc kết quả giao dịch OOS.
  **Tiếp theo W3-13**, rồi benchmark W3-14 và chốt W3-15/W3-16.

- **W3-11 hoàn thành — kiểm chứng và bàn giao ngân sách**: `tests/test_bayesian_prompt_budget.py`
  có chín test mới PASS; `scripts/verify_prior_prompt_budget.py` dùng formatter,
  `_distill_report`/`_cap_report` và builder compact VI/EN thật, không gọi LLM.
  Kiểm K=0..3, bốn regime, số cực trị/nhiều chữ số, Unicode/NFC/ID dài, n=0,
  không bullish, biên đúng 600 và overflow từ chối; input và cap runtime được bảo toàn.
- [Receipt ngân sách](prompt_budget_review.json) ghi **PASS_WITH_REQUIRED_W4_HANDOFF**:
  cap cũ tổng 4.500 cho prompt ghép 6.565 VI / 6.582 EN, không đạt trần. Phương án
  cap tổng 4.000 kiểm 1.024 ca, lớn nhất 6.086; dự phòng đầy đủ BRPP 600 cho prompt
  lớn nhất **6.289 ký tự**. Đây là fixture offline, chưa áp dụng vào Decision runtime.
  W4 phải dùng cap đã kiểm và guard `<6500` sau mọi hướng dẫn được thêm.
- **Gate tích hợp W3-11**: compileall PASS, 312/312 unit tests PASS (94,466 giây),
  E2E xác định PASS (12,4 giây), 46/46 leakage tests PASS (5,660 giây).
  Nhánh `test/prior-prefix-prompt-budget` tích hợp sau gate; hash receipt và
  `git diff --check` được kiểm trước commit. **Gate C còn mở** vì W3-12 chưa smoke
  retrieval/formatter trên kho thật; chưa có kết quả giao dịch OOS hoặc tích hợp W4.

- **W3-10 hoàn thành**: hàm module `format_compact_prior_prefix` có template BRPP v1,
  header n/k, bốn rate với counts/N/A, code T/P/A/I, nhãn W/L của LONG sau phí,
  SHORT tiền mặt và ghi rõ S=thiếu tin. Giữ thứ tự/ngày quyết định/regime từng task;
  percentage không nhân 100 lần nữa, return sát 0/lớn dùng scientific đúng policy.
- Validation schema/alias/NFC/ngày/ID/nhãn/counts/rate Python gốc hữu hạn; quá 600
  ký tự gây ValueError, không truncate hoặc bỏ ví dụ. []/None Original trả rỗng;
  stats object/n=0 vẫn render header/rates. Input không bị sửa, không đọc CSV/P&L.
- 13 test formatter mới PASS; tổng 68 test Bayesian tập trung PASS. [Receipt](prefix_formatter_review.json)
  khớp mười mẫu tham chiếu Phase A, dài nhất trong các mẫu là 397 ký tự; có test lỗi
  kiểu/schema/nhãn/NaN/NumPy/counts/duplicate/K>3, overflow và result retriever bốn mode.
- **Gate tích hợp W3-10**: compileall PASS, 303/303 unit tests PASS (92,341 giây),
  E2E xác định PASS (13,4 giây), 46/46 leakage tests PASS (6,569 giây). Hash receipt,
  liên kết Markdown và `git diff --check` PASS; tích hợp nhánh `feat/compact-prior-prefix`
  sau gate. **Gate C còn mở**: W3-11 kiểm ngân sách/prompt ghép <6.500; W3-12 smoke
  retrieval/formatter trên query PIT. Receipt hiện tại là fixture render, chưa là
  smoke kho thật hoặc benchmark giao dịch OOS.

- **W3-09 hoàn thành — Phase B/Gate B PASS**: `retrieve` trả đầy đủ tasks/stats/metadata
  ở cả bốn mode; stats dùng toàn population cùng scope/regime đã PIT, không phải K
  ví dụ. Bốn metric giữ counts và float không làm tròn; mẫu số 0 → None, không smoothing.
  K=0 không tạo pool hoặc tính stats; thống kê và kết quả là object Python gốc độc lập.
- 14 test mới (11 stats + ba leakage), tổng 55 test Bayesian tập trung PASS: fixture
  tính tay 2/4, 2/3, 1/2, 2/2; union không đếm đôi, no-bullish/zero-return/empty/K=0,
  scope/regime/K/mode, hậu điều kiện, không mutate/I/O và đổi outcome tương lai hợp lệ.
- [Receipt runtime](statistics_runtime_review.json) PASS 384 query chính và 128 query
  lặp trên 32 context (bốn mã × hai scope × bốn regime), bốn mode, K=1..3. Stats
  khớp biên bản Phase A; pooled có 852 record, 344 WIN, 338 trap. Context của probe
  là fixture, không là regime hiện tại hoặc kết quả giao dịch OOS.
- **Gate tích hợp W3-09**: compileall PASS, 290/290 unit tests PASS (60,778 giây),
  E2E xác định PASS (8,7 giây), 46/46 leakage tests PASS (5,133 giây). Receipt/hash,
  liên kết Markdown và `git diff --check` được kiểm trước tích hợp nhánh
  `feat/regime-empirical-statistics`. Tiếp theo W3-10 BRPP compact; trần prompt,
  smoke formatter, p95 và bàn giao W4 vẫn thuộc các task còn lại.

- **W3-08 hoàn thành**: Bayesian lọc cùng regime từ pool PIT/scope trước top K,
  tái dùng `_select_similarity()` và chốt hậu điều kiện cutoff/scope/regime/ID/K.
  Metadata trả score float, candidate count bằng matched count, effective seed None.
  Thiếu K giữ mẫu hiện có; phân biệt no_eligible_history và no_matching_regime.
- Chín test bộ chọn mới và một leakage mới PASS; tổng 41 test Bayesian tập trung
  PASS. Kiểm bốn regime, không bù mã/regime, ranking C,A,D so với Similarity B,C,A,
  score 0, query đảo thứ tự, bản sao và fixture đổi nhãn kinh tế hợp lệ.
- [Receipt kho thật](bayesian_regime_review.json) đối chiếu 32 query Bayesian với
  32 query Similarity trên 852 episode; kiểm cùng pool/score/tie-break và biên
  empty/no_matching_regime/partial khi chặn I/O JSON/CSV/giá. Tín hiệu và regime
  query là fixture kiểm module, không phải trạng thái thị trường hoặc backtest OOS.
- **Gate tích hợp W3-08**: compileall PASS, 276/276 unit tests PASS (83,354 giây),
  E2E xác định PASS (13,3 giây), 43/43 leakage tests PASS (6,307 giây). Hash mã
  trong receipt, liên kết Markdown và `git diff --check` PASS. Nhánh
  `feat/regime-prior-selection` tích hợp sau gate. Bốn bộ chọn đã có;
  **Gate B còn mở**, cần W3-09 tính stats và hoàn thiện `retrieve(K>0)` trước Phase C.

- **W3-07 hoàn thành**: Similarity so khớp bốn tín hiệu kỹ thuật với trọng số đều;
  sentiment trọng số 0, alias/NFC được kiểm nghiêm ngặt. Chọn pool PIT cùng scope,
  phá hòa score/exit/ID; score 0 vẫn hợp lệ, không ranking bằng outcome/regime.
- Chín test Similarity mới PASS; test cutoff của bộ chọn mở rộng sang Similarity.
  Tổng 31 test Bayesian tập trung PASS, gồm fixture đổi nhãn kinh tế hợp lệ nhưng
  IDs/scores không đổi. [Receipt](similarity_review.json) kiểm tám query trên 852
  episode, empty/partial và không đọc lại JSON/CSV/giá khi query.
- **Gate tích hợp W3-07**: compileall PASS, 266/266 unit tests PASS, E2E xác định
  PASS (13,4 giây), 42/42 leakage tests PASS (5,923 giây). Hash mã trong receipt
  và `git diff --check` PASS; nhánh `feat/signal-similarity-selection` tích hợp
  sau gate. Gate B còn mở: tiếp theo W3-08 Bayesian, W3-09 stats và retrieve K>0;
  context của probe là fixture.

- **W3-06 hoàn thành**: Recent xếp exit giảm dần/ID tăng dần; Random sample không
  hoàn lại bằng RNG local và seed query SHA-256 đúng policy. `select_prior_tasks`
  trả tasks/population/metadata selected IDs/scores None/effective seed/status/reason;
  không mở scope để bù K. Tám test mới PASS, tổng 22 test Bayesian tập trung PASS.
- [Probe kho thật](recent_random_review.json) PASS 16 query trên 852 record:
  bốn mã × hai scope × hai mode; lặp query, biên exit, empty/partial, không I/O
  JSON/CSV/giá và không đổi global RNG. Regime probe là fixture, không kết quả OOS.
- **Gate tích hợp W3-06**: compileall PASS, 257/257 unit tests PASS (46,861 giây),
  E2E xác định PASS (7,3 giây), 42/42 leakage tests PASS (4,275 giây).
  Hash mã trong receipt, liên kết và `git diff --check` PASS. Nhánh
  `feat/recent-random-prior-selection`, tích hợp sau gate. Gate B còn mở;
  W3-07/W3-08 thêm Similarity/Bayesian, W3-09 tính stats và hoàn thiện retrieve K>0.

### 2026-10-04

- **W3-05 hoàn thành**: `core/bayesian_retriever.py` xác minh kho/manifest/QA/schema,
  nạp giá/P&L một lần, chuẩn bị pool/population PIT, bảo vệ ID/record/cutoff/scope,
  query validation và K=0. [Receipt kho thật](retriever_foundation_review.json) PASS
  852 record, nạp giá một lần/mã, không I/O query, bản sao độc lập và cutoff exit đầu.
  14 test mới nền/leakage PASS; lỗi chia sẻ record giữa pool/population đã được sửa.
- **Gate tích hợp W3-05**: compileall PASS; 249/249 unit tests PASS (96,389 giây),
  E2E xác định PASS (14,0 giây), 41/41 leakage tests PASS (6,748 giây).
  Hash mã trong receipt, liên kết nội bộ và `git diff --check` PASS.
  Nhánh `feat/bayesian-retriever-foundation`, tích hợp sau gate. Gate B còn mở;
  retrieve K>0 chưa có ranking/stats và dừng tường minh, tiếp theo W3-06.

- **W3-04 hoàn thành; Gate A PASS**: [hợp đồng stats/BRPP](statistics_and_prefix_contract.md),
  [policy v1](statistics_prefix_policy.json) và [receipt](statistics_prefix_review.json)
  khóa population cùng scope/regime, bốn metric có counts, denominator 0=None,
  không smoothing/minimum support; stats chung bốn nhánh prior, Original không nhận prior.
  Template NFC/600 ký tự/K=0..3/return scientific/thiếu tin đã chốt. Fixture tính tay
  PASS, mẫu khảo sát dài nhất 397 ký tự; thống kê mô tả kho khớp 344 WIN và 338 trap.
- **Gate tích hợp W3-04**: compileall PASS; 235/235 unit tests PASS (87,619 giây),
  E2E xác định PASS (8,3 giây), 38/38 leakage tests PASS (4,195 giây).
  Hash policy/receipt, counts/độ dài mẫu, JSON ví dụ API, liên kết nội bộ và
  `git diff --check` PASS. Nhánh `docs/prior-statistics-prefix`, tích hợp sau gate.
  Phase A đã hoàn thành; Phase B/C/D chưa thực hiện, tiếp theo W3-05.

- **W3-03 hoàn thành**: [luật chọn prior](prior_selection_method.md),
  [policy v1](prior_selection_policy.json) và [receipt](selection_policy_review.json)
  chốt bốn mode, alias/NFC, score bốn trường 0,25/trường, sentiment 0, tie-break,
  seed SHA-256 theo query và thiếu mẫu không mở scope/regime. Kiểm kê toàn bộ 852
  episode, ranking tham chiếu, Random theo seed/đảo pool/thêm ứng viên tương lai,
  hash policy và JSON ví dụ API PASS. Không triển khai retriever runtime.
- **Gate tích hợp W3-03**: compileall PASS; 235/235 unit tests PASS (89,889 giây),
  E2E xác định PASS (13,3 giây), 38/38 leakage tests PASS (5,528 giây),
  `git diff --check` và liên kết nội bộ PASS. Nhánh `docs/prior-selection-method`,
  tích hợp sau bốn gate. Gate A còn mở; tiếp theo W3-04 chốt thống kê/BRPP.

- **W3-02 hoàn thành**: [hợp đồng API v1](retriever_api_contract.md) chốt constructor/query,
  validation kiểu Python gốc, K=0..3, seed=42 mặc định, scope `same_symbol`/`pooled`,
  tasks/stats/metadata, counts/score/status/reason, thiếu mẫu và trách nhiệm PIT.
  Đã đối chiếu schema W1, API kho và đặc tả phương pháp; JSON ví dụ K=0, liên kết
  nội bộ và `git diff --check` PASS. Chưa triển khai module hoặc các test thuật toán.
- **Gate tích hợp W3-02**: compileall PASS; 235/235 unit tests PASS (90,278 giây),
  E2E xác định PASS (13,1 giây), 38/38 leakage tests PASS (5,720 giây).
  Tài liệu trên nhánh `docs/bayesian-query-contract`, tích hợp sau gate.
  Gate A còn mở: tiếp tục W3-03/W3-04.

- **W3-01 hoàn thành**: `scripts/verify_bayesian_inputs.py` và [receipt](input_readiness.json)
  PASS 852 record, hash kho/schema/signature và độ phủ khớp manifest/QA; nạp giá đúng
  một lần/mã, cutoff nghiêm ngặt, deep copy và không I/O JSON/giá trong query PASS.
  Audit gốc chạy lại PASS. [Biên bản Phase A](phase_a_contract_and_method.md#04102026--w3-01-hoàn-thành)
  ghi chi phí nạp một lần, giới hạn dữ liệu, ranh giới W4 và phép đo W3-14 đã khóa.
- **Gate tích hợp W3-01**: compileall PASS; 235/235 unit tests PASS (65,681 giây),
  E2E xác định PASS (13,0 giây), 38/38 leakage tests PASS (5,592 giây).
  Không triển khai retriever/formatter hoặc khóa các lựa chọn của W3-02..04;
  Gate A còn mở. Thay đổi trên nhánh `docs/bayesian-input-readiness`, tích hợp sau gate.

- Đã lập kế hoạch 16 task trong bốn phase, dựa trên W2 đã chốt và code hiện có.
  Đây là bước lập kế hoạch; chưa hoàn thành W3-01 hoặc triển khai module W3.
- Kiểm tra tài liệu: 16 mã task duy nhất, đủ năm file, liên kết nội bộ tồn tại,
  `git diff --check` PASS. Bốn gate codebase hiện có đều PASS trước tích hợp tài liệu;
  kết quả này không thay cho gate W3-15 sau khi triển khai.
