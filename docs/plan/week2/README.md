# Tuần 2 — Regime và Historical Memory Bank

**Hoàn thành 17/17 task ngày 04/10/2026.**
[Kế hoạch tổng](../plan.md) · [Phương pháp nghiên cứu](../../methodology_spec.md)

## Đầu ra và giới hạn

- Bộ giá thô `data/execution_prices` 2018–2022: [gate giá đã mở](phase_a_price_gate.md).
  Lịch 868 ứng viên, 852 hợp lệ, 16 loại vì quyền/tham chiếu; warm-up 600 phiên.
- Gaussian HMM bốn trạng thái: [cấu hình và API](phase_b_regime_detector.md),
  artifact chính thức `data_manager/regime_model.json`; model prefix kiểm PIT.
- Kho `data_manager/regime_memory_store.json`: **852 episode**, quyết định
  2020–2022. [Phát hành, QA và cách chạy](phase_c_memory_generation.md),
  [audit máy đọc](memory_bank_audit.json). Sentiment toàn NEUTRAL vì thiếu tin.
- Biểu đồ tại `outputs/vnindex_regimes_2018_2022.png` và `.svg`; manifest cùng
  tên lưu provenance. Phân biệt nhãn hồi cứu train và 217 ngày regime PIT.
- Nghiệm thu W2: compileall/E2E, **235 unit/38 leakage PASS**. Đây là kết quả
  tại thời điểm đóng tuần; trạng thái hồi quy hiện tại xem [W4](../week4/README.md).
- Chưa mở gate giá thô OOS 2023–2024; kho prior không là kết quả giao dịch OOS.

## Checklist đã hoàn thành

### A — Dữ liệu và mẫu chu kỳ

| Task | Công việc | Trạng thái |
| --- | --- | --- |
| W2-01 | Xác minh giá thực thi point-in-time và cơ chế điều chỉnh doanh nghiệp từ hai provider được phép | [x] |
| W2-02 | Chốt cách lấy mẫu chu kỳ 2018–2022 | [x] |

### B — Regime

| Task | Công việc | Trạng thái |
| --- | --- | --- |
| W2-03 | Đặc tả và tính đặc trưng VN-Index theo ngày | [x] |
| W2-04 | Chốt cấu hình Gaussian HMM và khả năng tái lập | [x] |
| W2-05 | Cài đặt fit một lần và lưu artifact của HMM | [x] |
| W2-06 | Ánh xạ trạng thái HMM sang bốn tên regime | [x] |
| W2-07 | Cung cấp API phân loại tại `as_of_date` | [x] |
| W2-08 | Kiểm thử regime và cắt thời gian | [x] |

### C — Memory Bank

| Task | Công việc | Trạng thái |
| --- | --- | --- |
| W2-09 | Cài đặt cấu trúc lưu và xác thực `HistoricalTaskRecord` | [x] |
| W2-10 | Trích tín hiệu năm agent từ snapshot lịch sử | [x] |
| W2-11 | Tạo nhãn kinh tế cho chu kỳ đã tất toán | [x] |
| W2-12 | Viết runner offline có thể tiếp tục | [x] |
| W2-13 | Sinh Memory Bank 2018–2022 | [x] |
| W2-14 | Kiểm toán Memory Bank | [x] |

### D — Biểu đồ và chốt tuần

| Task | Công việc | Trạng thái |
| --- | --- | --- |
| W2-15 | Vẽ chế độ VN-Index 2018–2022 | [x] |
| W2-16 | Chạy bốn gate hồi quy và kiểm toán leakage | [x] |
| W2-17 | Rà soát deliverables, cập nhật tiến độ và tích hợp | [x] |

## Bằng chứng và quy ước tài liệu

Các receipt từng task, nhật ký và lượt benchmark cũ được đóng gói nguyên byte
trong [implementation_evidence.zip](../implementation_evidence.zip), với tên
entry là đường dẫn gốc từ repo. ZIP chứa cả lượt FAIL và PASS; mở archive khi
cần đối chiếu chi tiết lịch sử. Các JSON còn rời ở tuần này là đầu vào của
code, schema hoặc fixture hồi quy; không xóa chúng theo đuôi file.

Cập nhật tiến độ tại README này sau mỗi task. Chỉ tách tài liệu cho một hướng
dẫn/phương pháp có nhu cầu đọc độc lập; không tạo thêm biên bản Markdown và
receipt JSON chỉ để nhắc lại cùng kết quả kiểm thử.
