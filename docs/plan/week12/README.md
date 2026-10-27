# Tuần 12 — Hoàn thiện kết quả và bảo vệ khóa luận

**Trạng thái: kế hoạch điều chỉnh 26/10/2026, 0/5 DONE; thời hạn vẫn 12 tuần.**
[Kế hoạch tổng](../plan.md) · [W10](../week10/README.md) · [W11](../week11/README.md) · [W9](../week9/README.md)

W10 đã triển khai U-BICL v1; U11-03 khóa NOT_NOMINATED. Theo yêu cầu mới,
[chuỗi U11-04–U11-11](../week11/README.md#d-checklist-thực-hiện-tuần-tự-hiện-hành)
triển khai kế hoạch R2 về payoff/ICL rồi tổng kết/bàn giao, không đổi kết
quả cũ. U11 hiện 5/11: U11-05 đã khóa protocol/kiểm payoff, gate FAIL ngày
27/10/2026. U11-06–09 NOT_RUN, R2 chưa development LLM/nomination/xác nhận;
tiếp theo U11-10 tổng hợp cả kết quả offline bất lợi. W12 bắt đầu checklist sau bàn giao
U11-11 (kể cả khi các bước xác nhận không được chạy). W12 ưu tiên
luận văn/tái lập/slide. Chỉ hai ngày làm việc đầu được hoàn tất/resume
xác nhận đã release và bắt đầu ở W11; không mở ma trận/run mới, tune hoặc
gia hạn sang W13. Hết ngày thứ hai khóa dữ liệu: thiếu mẫu thì INCOMPLETE,
không dùng mock, partial gain hoặc ước lượng nhãn chưa đóng làm kết quả chính.

| Task | Đầu ra và tiêu chí | Trạng thái |
| --- | --- | --- |
| U12-01 | Chốt trước cuối ngày thứ hai: W9 xác nhận cũ, v1 NOT_NOMINATED, R2 gate offline FAIL và development/xác nhận R2 NOT_RUN; không trộn cohort/revision | [ ] TODO |
| U12-02 | Hoàn thiện phương pháp/kết quả/thảo luận, đủ ablation/noise/failure, năm action đổi của v1 và provenance mọi vòng phát triển; không bỏ kết quả bất lợi | [ ] TODO |
| U12-03 | Kiểm tái lập/checksum/cài đặt/restore; viện dẫn receipt đúng source/runtime, test phần đổi nếu có; không tự chạy lại toàn suite; hướng dẫn offline và API | [ ] TODO |
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
