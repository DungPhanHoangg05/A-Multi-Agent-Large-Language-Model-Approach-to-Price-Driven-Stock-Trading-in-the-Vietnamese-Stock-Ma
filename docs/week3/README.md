# Tuần 3 — Bayesian Prior Retriever và BRPP

**Trạng thái: đã lập kế hoạch; chưa triển khai các task W3.**

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
| W3-01 | Kiểm tra đầu vào và ranh giới W3 | Biên bản hash/QA/852 record, khả năng tái dùng `eligible`, giới hạn và điểm bàn giao W4 | W2 hoàn thành | [ ] |
| W3-02 | Chốt API truy vấn và kết quả | Kiểu query/result, mode/K/seed/scope, metadata, lỗi đầu vào, empty/K=0 được đặc tả | W3-01 | [ ] |
| W3-03 | Chốt cách chọn prior và similarity | Bốn mode, chuẩn hóa tín hiệu, tie-break, seed theo query, thiếu mẫu; không xếp hạng bằng outcome | W3-02 | [ ] |
| W3-04 | Chốt thống kê và mẫu BRPP | Công thức/mẫu số, phạm vi thống kê, n=0, thiếu tin, mẫu K=0..3 và đơn vị đo ký tự | W3-02, W3-03 | [ ] |

## B. Retriever và thống kê

Chi tiết: [Phase B](phase_b_retriever_and_statistics.md).

| Mã | Task | Đầu ra / điều kiện hoàn thành | Phụ thuộc | Trạng thái |
| --- | --- | --- | --- | --- |
| W3-05 | Nạp kho, lọc PIT và bảo vệ dữ liệu | `BayesianPriorRetriever`, dùng kho xác minh, lọc trước ranking/stats, kết quả độc lập, kiểm cutoff đầu ra | W3-01..04 | [ ] |
| W3-06 | Cài `recent` và `random` | Thứ tự/tie-break ổn định, seed tái lập theo query, không trùng record, không phụ thuộc thứ tự gọi | W3-05 | [ ] |
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

### 2026-10-04

- Đã lập kế hoạch 16 task trong bốn phase, dựa trên W2 đã chốt và code hiện có.
  Đây là bước lập kế hoạch; chưa hoàn thành W3-01 hoặc triển khai module W3.
- Kiểm tra tài liệu: 16 mã task duy nhất, đủ năm file, liên kết nội bộ tồn tại,
  `git diff --check` PASS. Bốn gate codebase hiện có đều PASS trước tích hợp tài liệu;
  kết quả này không thay cho gate W3-15 sau khi triển khai.
