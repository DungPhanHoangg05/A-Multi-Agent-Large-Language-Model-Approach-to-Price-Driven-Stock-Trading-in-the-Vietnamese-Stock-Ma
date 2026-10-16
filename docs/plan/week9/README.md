# Tuần 9 — Benchmark holdout và phân tích thống kê

**Trạng thái: TODO, 0/6.** Giữ deadline 10 tuần; cập nhật 16/10/2026.
[Kế hoạch tổng](../plan.md) · [W8](../week8/README.md) · [W10](../week10/README.md)

## Phạm vi và đầu vào

Gate W8 PASS, selection/protocol/manifest mới đã khóa; cohort 2024 gồm
64 điểm, 16 điểm mỗi mã FPT/VNM/VCB/MWG. Không mở holdout trước khóa.
Dành khoảng 60% tuần cho chạy/đối soát và 40% cho thống kê/hình/bảng;
công cụ thống kê đã chuẩn bị bằng fixture ở W8. Không phát triển ứng viên
mới trong tuần này; người dùng tự thực hiện preflight/API theo CLI đã kiểm.

## Checklist

| Task | Công việc và điều kiện hoàn thành | Phụ thuộc | Trạng thái |
| --- | --- | --- | --- |
| W9-01 | Kiểm manifest, môi trường và nguồn; preflight đúng model/options; khóa run identity | W8 PASS | [ ] TODO |
| W9-02 | Chạy bốn mã/ma trận đã khóa; checkpoint, ledger, retry; một upstream/point deep-copy mọi nhánh | 01 | [ ] TODO |
| W9-03 | Verify semantic toàn run, PIT, P&L, common support, missing/unknown và checksum | 02 | [ ] TODO |
| W9-04 | Tính primary ΔR/MDD và CI theo protocol; secondary/ablation và kiểm nhiều so sánh | 03 | [ ] TODO |
| W9-05 | Xuất bảng/biểu đồ, phân tích thất bại/coverage/prior-off và giới hạn | 04 | [ ] TODO |
| W9-06 | Khóa dữ liệu kết quả, kiểm tái lập và bàn giao chương kết quả W10 | 05 | [ ] TODO |

## Quy tắc thực thi và kết luận

LONG Open(t+1)→Close(t+3), SHORT=CASH, phí 0,25% và trượt giá 0,10% mỗi
chiều; nhãn qua hàm kinh tế dùng chung. Giá/tin≤cutoff, prior exit<cutoff;
không refit/tune bằng holdout. Giữ BRPP≤600, prompt<6.500, risk OFF,
retry/backoff và checkpoint. Unknown phải đối soát, không replay upstream
mù quáng, không đổi ngày lỗi hoặc điền CASH giả. Chỉ resume đúng identity.

Phân tích primary trên đủ common support đã khóa; thiếu nhánh/điểm thì
đánh incomplete, báo phần có được dưới nhãn mô tả. Không kéo dài sang W10
để thử thêm cấu hình; nếu API gián đoạn, ưu tiên phục hồi run đã khóa trong
W9 và báo phần thiếu trung thực. Không hạ gate hoặc dùng selection development
thay kết quả xác nhận. Mọi sửa lỗi ảnh hưởng method/action cần protocol và
run mới; nếu đã xem outcome, kết quả sau sửa là exploratory.

Báo ΔR từng mã và trung bình đều bốn mã (không gọi là return portfolio),
MDD, LONG/CASH, exposure, balanced accuracy, common support và uncertainty.
CI bootstrap theo block/cụm ngày và các kiểm phụ dùng tham số đã khóa W8;
không chọn block/kiểm định vì p-value đẹp. Sharpe/Sortino giữ quy ước chu kỳ,
không tự annualize bằng √252. Phân tích calibration chỉ khi có xác suất
sự kiện hợp lệ. Không đủ lực kiểm định thì báo inconclusive.

So sánh ứng viên với Original là primary; C2/v1 và ablation là secondary.
Báo cả mã/regime bất lợi, prior-off, readiness và trace NOT_USED; không suy
trace thành cơ chế Bayes trong LLM. Giữ các giới hạn BEAR=0/tin reliable=0
và FPT thiếu mẫu ở development nếu vẫn đúng; không giả định holdout có
coverage tương tự trước khi đo. Nêu hạn chế PIT hồi cứu và kiến thức LLM.

Đầu ra: artifact có version trong `outputs/bayesian_benchmark/`, bảng
LaTeX và hình khoa học tại `docs/figures/` (vector hoặc ≥300 DPI nếu raster).
README giữ tiến độ và đường dẫn/hash, không thêm receipt lặp lại. Gate W9
đóng khi đủ dữ liệu/verify/phân tích; nếu thiếu, bàn giao W10 với trạng thái
incomplete và giới hạn claim, không ghi benchmark PASS giả.
