# Phase D — biểu đồ và chốt deliverables

**Ngày chốt: 04/10/2026. W2-15, W2-16 và W2-17 hoàn thành.**

## W2-15 — biểu đồ VN-Index

Đã xuất [PNG 300 DPI, 4.200 × 2.400 pixel](../../../outputs/vnindex_regimes_2018_2022.png),
[SVG](../../../outputs/vnindex_regimes_2018_2022.svg) và
[manifest/checksum](../../../outputs/vnindex_regimes_2018_2022.manifest.json).
Đã kiểm tra ảnh trực quan: tiêu đề, trục, tiếng Việt và chú giải đủ bốn regime
không bị cắt hoặc chồng nhau; chỉ hiển thị 2018–2022.

- **Panel A:** đường giá 1.251 phiên VN-Index; 1.052 nhãn hồi cứu từ HMM/scaler
  đã fit trên toàn bộ tập train 2018–2022, 199 phiên đầu là vùng khởi động.
  Posterior này dùng thông tin cả tập train, chỉ dành cho minh họa hồi cứu;
  không dùng làm nhãn point-in-time hoặc thay nhãn trong Memory Bank.
- **Panel B:** 217 ngày quyết định của 852 episode đã QA, dùng đúng nhãn PIT
  của model prefix lưu trong kho. Cùng ngày phải có cùng regime VN-Index.
  Kho không có episode 2018–2019 vì warm-up 600 phiên.

Script xác minh checksum CSV W1, hash train của model, trạng thái PASS và hash
kho của QA trước khi vẽ. Không fit lại HMM, không gọi LLM và không sửa nhãn kho.
Số lượng nhãn hồi cứu khác nhãn PIT vì hai panel có phương pháp và phạm vi khác nhau.

| Regime | Phiên hồi cứu | Ngày quyết định PIT |
| --- | ---: | ---: |
| BULL | 347 | 86 |
| BEAR | 115 | 48 |
| CHOPPY | 247 | 64 |
| CONSOLIDATION | 343 | 19 |

Lệnh tái tạo tại thư mục gốc repo:

```powershell
py -3.13 -X utf8 scripts/plot_vnindex_regimes.py
```

Manifest ghi SHA-256 của train, kho, PNG và SVG. Git giữ nguyên byte SVG/manifest
để không làm sai checksum khi checkout. Khi vẽ lại, manifest được cập nhật theo
file mới; metadata xuất SVG có thể khiến checksum khác dù nội dung hình tương đương.

## W2-16 — bốn gate và kiểm toán kho

| Kiểm tra | Lệnh | Kết quả |
| --- | --- | --- |
| Biên dịch | `py -3.13 -m compileall agents core data_manager scripts tests utils` | PASS |
| Unit tests | `py -3.13 -X utf8 -m unittest discover -s tests -v` | 235/235 PASS, 43,477 giây |
| E2E xác định | `py -3.13 scripts/run_end_to_end_test.py` | PASS, 7,2 giây |
| Zero-leakage | `py -3.13 -X utf8 -m unittest discover -s tests -p 'test_*leakage.py' -v` | 38/38 PASS, 3,930 giây |
| Kho thực tế | `py -3.13 -X utf8 scripts/audit_historical_memory.py` | PASS 852 episode |

Giữ nguyên engine P&L, hợp đồng LONG Open(t+1)/Close(t+3), SHORT giữ tiền mặt,
phí và slippage hai chiều. Không sửa pipeline upstream hoặc giao thức ghép cặp.
Không có lời gọi LLM mới trong bước chốt này.

## W2-17 — đối chiếu đầu ra và tiến độ

| Deliverable trong kế hoạch tổng | Bằng chứng | Trạng thái |
| --- | --- | --- |
| Module regime độc lập kèm test | `core/regime_detector.py`, `data_manager/regime_model.json`, [Phase B](phase_b_regime_detector.md), gate trên | Hoàn thành |
| Memory Bank đúng schema, hơn 300 chu kỳ | `data_manager/regime_memory_store.json`: 852 episode; manifest/bộ đọc; [QA](memory_bank_audit.json) và [Phase C](phase_c_memory_generation.md) | Hoàn thành |
| Biểu đồ VN-Index 2018–2022 | PNG/SVG/manifest ở trên, script tái tạo, kiểm tra ảnh trực quan | Hoàn thành |

Đã cập nhật [bảng task](README.md) và [kế hoạch tổng](../plan.md).
Thay đổi được thực hiện trên nhánh `feat/regime-chart-week-close` từ `develop`,
commit theo Conventional Commits và tích hợp sau khi bốn gate PASS.

**Phạm vi kết luận:** W2 hoàn thành các deliverables kỹ thuật; chưa có kết quả
benchmark Bayesian ngoài mẫu. Toàn bộ 852 sentiment NEUTRAL do thiếu tin đáng tin
cậy; gate giá thô kiểm định 2023–2024 chưa mở. Các giới hạn này phải giữ khi viết luận văn.

**Bước tiếp theo:** W3 — Bayesian Prior Retriever với bốn chế độ lấy mẫu, cutoff
`exit_date < as_of_date`, thống kê Bayes và BRPP tối đa 600 ký tự; chưa triển khai
W3 trong bước chốt này.
