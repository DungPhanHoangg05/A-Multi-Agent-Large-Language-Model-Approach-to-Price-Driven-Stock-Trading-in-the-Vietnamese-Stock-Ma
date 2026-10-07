# Tuần 4 — Tích hợp prior vào hệ thống đa agent

**Hoàn thành 16/16 task; bốn phase PASS kỹ thuật offline.** Cảnh báo retrieval
p95 đã xử lý ngày **07/10/2026**. Prior mặc định tắt; pilot/OOS chưa được mở.
[Kế hoạch tổng](../plan.md) · [Tuần 3](../week3/README.md)

## Luồng chính và vận hành

[Hướng dẫn API, checkpoint/resume và bàn giao W5](week_close_and_handoff.md)
là tài liệu vận hành duy nhất của tuần này.

- Full/upstream chạy một lần mỗi điểm; năm Decision dùng cùng bản sao báo cáo.
- Adapter xác minh giá/tin/regime/model PIT, hỗ trợ historical prefix và fixed train OOS.
- Kinh tế giữ LONG Open(t+1) → Close(t+3), SHORT tiền mặt, phí/slippage hai chiều.
- Cap báo cáo tổng 4.000, BRPP ≤600; prompt cuối <6.500 ký tự, guard trước API.
- Checkpoint durable từng nhánh; resume kiểm identity và không gọi lại nhánh complete.

## Kết quả nghiệm thu mới nhất

Compileall, **502 unit**, **E2E**, **93 leakage** và smoke tích hợp PASS ngày
07/10/2026. Smoke gồm 8 context tổng hợp và 6 replay nguồn thật với Decision
giả; kiểm paired/resume/flag off và biên prompt 6.499 nhận/6.500 chặn.

| Mode | Baseline trước tối ưu p95 (ms) | Sau tối ưu p95 (ms) | Gate <30 ms |
| --- | ---: | ---: | --- |
| Bayesian Regime | 34,839 | 11,559 | PASS |
| Random | 30,070 | 10,837 | PASS |
| Recent | 29,015 | 10,927 | PASS |
| Similarity | 37,286 | 13,235 | PASS |

Giữ phương pháp W3: 100 warm-up, 1.000 mẫu/mode/bước, bốn mode/hai scope,
p95 nearest-rank, toàn bộ mẫu và oracle. Tối ưu lookup alias và copy pool đã
xác minh; guard/type/PIT/ownership giữ nguyên. PASS áp dụng phiên bản và máy
đã đo; không bảo đảm mọi máy/request <30 ms. Các receipt chi tiết trước/sau
nằm nguyên byte trong ZIP bằng chứng, gồm cả FAIL W4-15 và baseline mới.

## Checklist đã hoàn thành

### A — Hợp đồng tích hợp

| Task | Công việc | Trạng thái |
| --- | --- | --- |
| W4-01 | Kiểm tra bàn giao và các điểm nối runtime | [x] |
| W4-02 | Chốt state và cấu hình prior độc lập | [x] |
| W4-03 | Chốt provenance và thứ tự PIT | [x] |
| W4-04 | Chốt schema kết quả và resume | [x] |

### B — State, prompt và graph

| Task | Công việc | Trạng thái |
| --- | --- | --- |
| W4-05 | Cài state/config và validator | [x] |
| W4-06 | Áp dụng cap và guard prompt runtime | [x] |
| W4-07 | Chèn BRPP và hướng dẫn reasoning | [x] |
| W4-08 | Ghép graph với ranh giới chuẩn bị báo cáo | [x] |

### C — PIT, paired và checkpoint

| Task | Công việc | Trạng thái |
| --- | --- | --- |
| W4-09 | Cài adapter context/regime PIT | [x] |
| W4-10 | Tạo báo cáo chung cho năm nhánh | [x] |
| W4-11 | Ghép retriever vào backtest | [x] |
| W4-12 | Lưu và phục hồi tiến trình từng nhánh | [x] |

### D — Kiểm chứng và bàn giao

| Task | Công việc | Trạng thái |
| --- | --- | --- |
| W4-13 | Kiểm thử leakage toàn đường tích hợp | [x] |
| W4-14 | Smoke E2E offline và tương thích | [x] |
| W4-15 | Chạy bốn gate và kiểm phạm vi thay đổi | [x] |
| W4-16 | Chốt W4, bàn giao điều kiện pilot W5 | [x] |

## Việc tiếp theo — W5

- [ ] Mở gate giá/tin FPT+VNINDEX OOS 2023–2024 bằng nguồn riêng VCI/KBS.
- [ ] Chốt model/freeze và kế hoạch 20 cutoff trước mọi API.
- [ ] Chốt model/config/quota/pacing dùng chung; kiểm budget token thực.
- [ ] Viết CLI nghiên cứu dry-run/preflight/verify/resume gọi API W4.
- [ ] Sau các gate trên mới chạy pilot FPT 20 điểm × 5 nhánh.

Chưa có kết quả giao dịch OOS. CLI `scripts/run_bayesian_ablation.py` chưa triển khai.

## Bằng chứng và quy ước tài liệu

Các receipt từng task, nhật ký và lượt benchmark cũ được đóng gói nguyên byte
trong [implementation_evidence.zip](../implementation_evidence.zip), với tên
entry là đường dẫn gốc từ repo. ZIP chứa cả lượt FAIL và PASS; mở archive khi
cần đối chiếu chi tiết lịch sử. Các JSON còn rời ở tuần này là đầu vào của
code, schema hoặc fixture hồi quy; không xóa chúng theo đuôi file.

Cập nhật tiến độ tại README này sau mỗi task. Chỉ tách tài liệu cho một hướng
dẫn/phương pháp có nhu cầu đọc độc lập; không tạo thêm biên bản Markdown và
receipt JSON chỉ để nhắc lại cùng kết quả kiểm thử.

## Nhật ký tiến độ

- 07/10/2026: gom tài liệu tuần từ 96 xuống 25 file rời (12 Markdown, 13 JSON
  cần cho code/test); 28 Markdown và 43 JSON dư thừa đã đóng gói trong một ZIP.
  Kiểm checksum archive/fixture và liên kết PASS; code, bank và dữ liệu không đổi.
  Compileall, 502 unit, E2E và 93 leakage PASS sau dọn tài liệu.
