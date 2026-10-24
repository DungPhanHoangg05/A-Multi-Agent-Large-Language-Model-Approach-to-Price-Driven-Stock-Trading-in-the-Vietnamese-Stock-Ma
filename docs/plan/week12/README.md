# Tuần 12 — Hoàn thiện kết quả và bảo vệ khóa luận

**Trạng thái: kế hoạch điều chỉnh 24/10/2026, 0/5 DONE.**
[Kế hoạch tổng](../plan.md) · [W10](../week10/README.md) · [W11](../week11/README.md) · [W9](../week9/README.md)

W10 triển khai một phiên bản Bayesian ICL hợp nhất; W11 development và xác
nhận có gate. W12 hoàn thiện luận văn/tái lập/slide. Nếu run xác nhận W11
chưa xong chỉ resume đúng manifest; không tune hoặc mở ma trận mới. Thiếu
mẫu thì INCOMPLETE, không dùng mock/ước lượng nhãn chưa đóng để ghi PASS.

| Task | Đầu ra và tiêu chí | Trạng thái |
| --- | --- | --- |
| U12-01 | Chốt trạng thái run và claim: W9 xác nhận cũ, development U và xác nhận U nếu có; tách các cohort | [ ] TODO |
| U12-02 | Hoàn thiện chương phương pháp/kết quả/thảo luận, đủ ablation/noise/failure và provenance các vòng đã xem | [ ] TODO |
| U12-03 | Kiểm tái lập/checksum/cài đặt/restore riêng; bốn gate mã bàn giao, hướng dẫn offline và API | [ ] TODO |
| U12-04 | Bản Word/LaTeX/PDF và 25–30 slide; số liệu/CI/hình/đơn vị khớp artifact | [ ] TODO |
| U12-05 | Diễn tập phản biện và khóa bản nộp; giải thích Bayes/ICL/PIT/selection và giới hạn | [ ] TODO |

Không gán gain do memory, prompt chung hoặc shared-off cho riêng Bayes/ICL;
không dùng trace làm bằng chứng suy luận nội tại. CI saved Decision không
bao gồm toàn bộ noise provider; dữ liệu hồi cứu PIT không loại tri thức
sau cutoff trong trọng số LLM. Nêu giới hạn bốn mã, regime/tin thiếu, tuổi
memory, task coverage và các nhóm xấu. Nếu hợp nhất không vượt A, vẫn giữ
kết quả W9 với đúng phạm vi; không gọi xóa revision cũ là chưa thử bao giờ.

Lợi ích nghiên cứu được chia thành hệ thống đúng/tái lập, ứng dụng Bayes
và ICL có đối chứng, rồi bằng chứng kinh tế. Gate kỹ thuật không thay CI;
CI qua 0 là chưa đủ bằng chứng, không phải tương đương. Không tự bật U làm
mặc định chỉ vì development tốt. Báo cáo kết quả bất lợi là điều kiện liêm
chính nghiên cứu, không phải lý do sửa mẫu/ngưỡng sau outcome.

Root README giữ giới thiệu/hướng dẫn tiếng Anh, tiến độ ở docs/plan. Giữ
T+2.5, phí/slippage, SHORT=CASH, PIT, upstream một lần, BRPP≤600/prompt<6500,
retry/checkpoint và Python 3.13.5. API do người dùng thực hiện; deadline vẫn
12 tuần, không tiếp tục search vô hạn để bảo đảm thắng.
