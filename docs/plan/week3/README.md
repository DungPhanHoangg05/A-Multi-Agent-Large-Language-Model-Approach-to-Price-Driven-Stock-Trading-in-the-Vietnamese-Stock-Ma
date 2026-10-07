# Tuần 3 — Bayesian Prior Retriever và BRPP

**Hoàn thành 16/16 task ngày 05/10/2026.**
[Kế hoạch tổng](../plan.md) · [Tuần 2](../week2/README.md) · [Tuần 4](../week4/README.md)

## Luồng chính

1. Khởi tạo `BayesianPriorRetriever` với bank, manifest và audit W2 đã xác minh.
2. Lọc `exit_date < as_of_date` và scope trước chọn prior; K=0..3, mặc định
   K=3/seed=42/same_symbol. Bốn mode: Random, Recent, Similarity, Bayesian Regime.
3. Thống kê trên toàn population cùng regime/scope/cutoff; Original K=0 trả
   tasks rỗng, stats None và prefix rỗng. Formatter BRPP ≤600 ký tự.

Tài liệu dùng khi lập trình hoặc viết luận văn:

- [API/query/result và xử lý lỗi](retriever_api_contract.md).
- [Similarity, ranking và seed](prior_selection_method.md).
- [Công thức thống kê và template BRPP](statistics_and_prefix_contract.md).
- [Phương pháp nghiên cứu chung](../../methodology_spec.md).

Constructor kiểm kho 852 episode/giá/P&L; mỗi query có validation và bản sao
độc lập. Caller xác minh giá/tin/model PIT trước gọi retriever. Không coi tỷ lệ
mẫu là posterior đã calibration; sentiment thiếu tin không cho tín hiệu tin cậy.

## Kiểm chứng

W3 đóng với compileall/E2E, **339 unit (104 Bayesian)/56 leakage PASS**, smoke
288 query + 288 lượt lặp/32 context. Benchmark chốt W3 đạt p95 <30 ms cả bốn
mode. [W4](../week4/README.md) ghi phép đo mới sau tối ưu và trạng thái hiện tại.
`prior_smoke.json`, `prompt_budget_review.json`, `selection_policy_review.json`
và `statistics_prefix_review.json` được giữ rời vì script/test đọc trực tiếp.

## Checklist đã hoàn thành

### A — Hợp đồng và phương pháp

| Task | Công việc | Trạng thái |
| --- | --- | --- |
| W3-01 | Kiểm tra đầu vào và ranh giới W3 | [x] |
| W3-02 | Chốt API truy vấn và kết quả | [x] |
| W3-03 | Chốt cách chọn prior và similarity | [x] |
| W3-04 | Chốt thống kê và mẫu BRPP | [x] |

### B — Retriever và thống kê

| Task | Công việc | Trạng thái |
| --- | --- | --- |
| W3-05 | Nạp kho, lọc PIT và bảo vệ dữ liệu | [x] |
| W3-06 | Cài `recent` và `random` | [x] |
| W3-07 | Cài `similarity` | [x] |
| W3-08 | Cài `bayesian_regime` | [x] |
| W3-09 | Tính thống kê theo regime | [x] |

### C — Prefix và ngân sách

| Task | Công việc | Trạng thái |
| --- | --- | --- |
| W3-10 | Định dạng BRPP compact | [x] |
| W3-11 | Kiểm tra 600 ký tự và prompt ghép | [x] |
| W3-12 | Smoke offline trên kho thật | [x] |

### D — Kiểm chứng và bàn giao

| Task | Công việc | Trạng thái |
| --- | --- | --- |
| W3-13 | Kiểm thử hành vi và zero-leakage | [x] |
| W3-14 | Benchmark retrieval tái lập | [x] |
| W3-15 | Chạy bốn gate trước tích hợp | [x] |
| W3-16 | Chốt deliverables và bàn giao W4 | [x] |

## Bằng chứng và quy ước tài liệu

Các receipt từng task, nhật ký và lượt benchmark cũ được đóng gói nguyên byte
trong [implementation_evidence.zip](../implementation_evidence.zip), với tên
entry là đường dẫn gốc từ repo. ZIP chứa cả lượt FAIL và PASS; mở archive khi
cần đối chiếu chi tiết lịch sử. Các JSON còn rời ở tuần này là đầu vào của
code, schema hoặc fixture hồi quy; không xóa chúng theo đuôi file.

Cập nhật tiến độ tại README này sau mỗi task. Chỉ tách tài liệu cho một hướng
dẫn/phương pháp có nhu cầu đọc độc lập; không tạo thêm biên bản Markdown và
receipt JSON chỉ để nhắc lại cùng kết quả kiểm thử.
