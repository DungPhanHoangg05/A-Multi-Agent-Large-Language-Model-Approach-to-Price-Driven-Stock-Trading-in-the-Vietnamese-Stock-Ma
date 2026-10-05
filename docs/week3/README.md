# Tuần 3 — Bayesian Prior Retriever và BRPP

**Trạng thái: Phase A hoàn thành, W3-05/W3-06 hoàn thành; W3-07 đến W3-16 chưa thực hiện. Phase B đang triển khai.**

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
| W3-07 | Cài `similarity` | So khớp tín hiệu theo đặc tả, xử lý trường hằng/không rõ, ranking xác định và score có thể kiểm toán | W3-03, W3-05 | [ ] |
| W3-08 | Cài `bayesian_regime` | Lọc cùng regime từ pool chung rồi xếp hạng theo đặc tả; K thiếu có lý do, không bù khác regime | W3-06, W3-07 | [ ] |
| W3-09 | Tính thống kê theo regime | Count/win/trap/mẫu số theo cutoff; fixture kiểm tay, JSON Python gốc; tách pool khỏi K ví dụ | W3-04, W3-05 | [ ] |

## C. Tiền tố và ngân sách prompt

Chi tiết: [Phase C](phase_c_prefix_and_budget.md).

| Mã | Task | Đầu ra / điều kiện hoàn thành | Phụ thuộc | Trạng thái |
| --- | --- | --- | --- | --- |
| W3-10 | Định dạng BRPP compact | `format_compact_prior_prefix(tasks, stats)` cùng schema nội bộ, giữ tín hiệu/nhãn/phí đúng nghĩa | W3-08, W3-09 | [ ] |
| W3-11 | Kiểm tra 600 ký tự và prompt ghép | Test K=0..3, dữ liệu dài, tiếng Việt, n=0; BRPP ≤600; prompt ghép thử <6.500; không sửa pipeline W4 | W3-10 | [ ] |
| W3-12 | Smoke offline trên kho thật | Biên bản bốn mode, IDs/stats/seed/hash/cutoff/độ dài; không fit HMM hoặc gọi LLM | W3-06..11 | [ ] |

## D. Leakage, hiệu năng và bàn giao

Chi tiết: [Phase D](phase_d_validation_and_handoff.md).

| Mã | Task | Đầu ra / điều kiện hoàn thành | Phụ thuộc | Trạng thái |
| --- | --- | --- | --- | --- |
| W3-13 | Kiểm thử hành vi và zero-leakage | Suite retriever/stats/prefix, `test_bayesian_retriever_leakage.py`; cả ranking/stats/prefix chống dữ liệu tương lai | W3-05..12 | [ ] |
| W3-14 | Benchmark retrieval tái lập | Script, receipt JSON và biên bản: đủ bốn mode, p95 <30 ms từng mode, cold load tách riêng | W3-12, W3-13 | [ ] |
| W3-15 | Chạy bốn gate trước tích hợp | Compileall, toàn bộ unit tests, E2E và leakage PASS; ghi số test/thời gian/lệnh | W3-13, W3-14 | [ ] |
| W3-16 | Chốt deliverables và bàn giao W4 | API/docs/example/benchmark đủ; cập nhật kế hoạch tổng, Conventional Commit/merge sau gate | W3-01..15 | [ ] |

## Thứ tự triển khai đề xuất

1. Chốt Phase A trước khi viết thuật toán; xử lý mọi điểm chưa quyết định ở A.
2. Làm W3-05 → W3-06 → W3-07 → W3-08 → W3-09, kèm test từng phần.
3. Làm W3-10 → W3-11 → W3-12 để kiểm ngữ nghĩa và độ dài trên kho thật.
4. Làm W3-13 → W3-14 → W3-15 → W3-16; sửa lỗi rồi chạy lại gate bị ảnh hưởng.

## Checklist chốt tuần

- [ ] Bốn chế độ dùng cùng pool hợp lệ trước bộ lọc/xếp hạng riêng của từng mode.
- [ ] Mọi prior và thống kê đều từ `exit_date < as_of_date`, không dùng nhãn query.
- [ ] K=3, seed/scope/metric được đóng băng, thiếu mẫu có metadata rõ ràng.
- [ ] BRPP ≤600 ký tự; prompt ghép thử <6.500 ký tự.
- [ ] Retrieval p95 <30 ms từng mode theo phép đo đã chốt.
- [ ] Unit tests, E2E và leakage PASS; API độc lập sẵn sàng cho W4.

## Nhật ký tiến độ

### 2026-10-05

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
