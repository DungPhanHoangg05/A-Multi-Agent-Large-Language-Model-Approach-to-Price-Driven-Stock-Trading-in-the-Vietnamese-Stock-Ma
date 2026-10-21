# Tuần 12 — Xác nhận độc lập, luận văn và bảo vệ

**Trạng thái: TODO, 0/7; cập nhật 21/10/2026.**
[Kế hoạch tổng](../plan.md) · [W10](../week10/README.md) · [W11](../week11/README.md) · [W9 đã khóa](../week9/README.md)

## Phạm vi và phân bổ thời gian

Chỉ chạy xác nhận revision mới khi W11 release PASS, đủ điều kiện exposure,
giá và selection. Dùng đầu W12 cho run/verify; phần còn lại thống kê, khóa
bằng chứng, hoàn thiện bản viết đã chuẩn bị W10–W11 và bảo vệ. Không thêm
ứng viên, tune prompt/ngưỡng, đổi model hoặc kéo dài deadline để tìm thắng.
Nếu không đủ thời gian/dữ liệu thì report INCOMPLETE, không hạ cỡ mẫu hoặc
gate. Forward cohort không thể đủ trưởng thành trong W12 vẫn là kế hoạch
sau khóa luận; không lấy dự báo chưa có exit làm nhãn.

## Checklist

| Task | Công việc | Phụ thuộc | Nghiệm thu | Trạng thái |
| --- | --- | --- | --- | --- |
| W12-01 | Người dùng preflight/run/resume primary và repeat đã khóa | W11 release | 128 điểm/sáu nhánh logic; HTTP/checkpoint đúng identity, không chọn lại | [ ] TODO |
| W12-02 | Verify semantic/PIT/paired/kinh tế/request/reuse | 01 | Common support đủ; zero unknown; missing không CASH; prior-off reuse truy được | [ ] TODO |
| W12-03 | Bootstrap, repeat diagnostics, bảng/hình và freeze | 02 | Primary/family/seed/L đúng plan; tất cả kết quả âm/inconclusive được giữ | [ ] TODO |
| W12-04 | Chương phương pháp và kết quả | W9, W10–11; 03 nếu có | Tách rõ W9 xác nhận cũ, development mới, xác nhận mới hoặc thiếu; claim đúng tầng | [ ] TODO |
| W12-05 | Tái lập/đóng gói/hướng dẫn và bốn gate mã bàn giao | 04 | Code/data/runtime/hash/release; restore riêng; mọi gate áp dụng PASS | [ ] TODO |
| W12-06 | Hoàn thiện Word/LaTeX/PDF và 25–30 slide | 04–05 | Hình/bảng khớp artifact; tham chiếu/đơn vị/số mẫu chính xác | [ ] TODO |
| W12-07 | Diễn tập phản biện và khóa bản nộp | 06 | Giải thích Bayes/ICL, selection/PIT, prior-off/noise và giới hạn; đủ deliverable | [ ] TODO |

W12-01–03 có thể NOT_RUN/BLOCKED nếu W11 không phát hành release; ghi rõ lý
do và tiếp tục 04–07 bằng bằng chứng W9. Không có xác nhận mới không đồng
nghĩa không hoàn thành luận văn. Không đánh gate thực nghiệm PASS khi thiếu.

## Quy tắc kết luận và triển khai

| Quan sát | Kết luận được phép | Hành động |
| --- | --- | --- |
| Primary CI>0, secondary selected−A CI>0 | Revision tốt hơn Original và A trên cohort/protocol mới | Báo repeat/rủi ro/coverage; đề xuất release riêng, không tự bật mặc định |
| Primary CI>0, selected−A inconclusive | Có bằng chứng vượt Original, chưa chứng minh nâng cấp vượt A | Giữ kết quả; không gọi revision là ưu việt hơn A |
| Full−stats CI>0 sau hiệu chỉnh | Demonstrations có đóng góp tăng thêm trong protocol | Nêu evidence common support/noise; không suy LLM làm Bayes nội tại |
| Full−examples CI>0 sau hiệu chỉnh | Stats có đóng góp tăng thêm trong protocol | Không coi là xác nhận riêng mọi chi tiết mô hình |
| D dương nhưng CI qua 0 | Ước lượng thuận lợi, chưa đủ bằng chứng | Không tuyên bố tương đương hoặc tăng mẫu sau khi xem CI |
| Âm, thiếu mẫu, không có holdout sạch | Revision chưa chứng minh cải thiện | Giữ Original mặc định, công bố thất bại/giới hạn, dùng W9 đúng phạm vi |

Mục tiêu khóa luận là áp dụng Bayesian ICL có thể kiểm chứng và đánh giá
trung thực, không bắt buộc lợi nhuận phải tăng. W9 vẫn có kết quả primary
dương đã xác nhận; không xóa nó vì revision mới thất bại. Chứng cứ phải tách
Bayes số học, demonstrations, LLM policy và kết quả kinh tế. Nếu chỉ mô hình
số thắng thì báo đóng góp đó, không gán công cho ICL. Calibration chỉ chấm
xác suất sự kiện hợp lệ; confidence văn bản không thay xác suất.

## Nội dung luận văn và bảo vệ

- Phương pháp: công thức empirical Bayes/giả định độc lập/plug-in uncertainty;
  task definition và thích ứng từ paper; PIT, selection, paired/reuse và kinh tế.
- Kết quả: W9 (2024) tách khỏi vòng 2023 mới và cohort mới; đủ cấu hình đã
  thử, CI/family, counts, coverage, action disagreement, VNM/nhóm bất lợi.
- Giới hạn: bốn mã, lịch lấy mẫu, regime thiếu, tin thiếu, trọng số LLM có
  thể biết thông tin sau cutoff, hồi cứu không là live prospective; CI điều
  kiện saved Decision và repeat không bao phủ mọi biến thiên provider.
- Tái lập: archive cũ nguyên byte; revision mới namespace/archive/hash riêng;
  không chứa key; Git clone không thay bản sao nguồn/cache ignored. Verify
  saved Decision không đồng nghĩa gọi lại LLM sẽ có cùng response.
- Hướng sau: expected utility có payoff model/uncertainty và đối chứng riêng,
  soft regime/cross-symbol chỉ khi có cơ sở, mở rộng prospective và nhiều mã.

Năm task W10 cũ chuyển: phương pháp→W12-04; kết quả→W12-04; tái lập→W12-05;
định dạng/slide→W12-06; bảo vệ→W12-07. Viết phương pháp bắt đầu ở W10-08,
khung bảng/chương ở W11-08, không dồn toàn bộ việc viết vào cuối W12.

Giữ T+2.5, SHORT=CASH, phí/slippage hai chiều, PIT exit<cutoff, upstream
một lần/deep-copy, BRPP≤600/prompt<6.500, retry/checkpoint và Python 3.13.5.
Mọi API do người dùng chạy. Root README chỉ giới thiệu/hướng dẫn tiếng Anh;
tiến độ ở docs/plan. Gate bàn giao yêu cầu artifact/luận văn/slide/tái lập và
claim đúng bằng chứng; không yêu cầu tạo kết quả thắng bằng mọi giá.
