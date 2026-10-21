# Tuần 10 — Hoàn thiện luận văn và bảo vệ

**Trạng thái: TODO, 0/5; đã nhận bàn giao W9 COMPLETE 6/6, Gate W9 PASS.** Deadline giữ nguyên; cập nhật 21/10/2026.
[Kế hoạch tổng](../plan.md) · [W9](../week9/README.md)

## Mục tiêu

Hoàn thiện luận văn từ phương pháp/bằng chứng đã khóa; không mở thêm vòng
tối ưu hoặc thay holdout. Dàn ý, chương hệ thống/phương pháp và khung bảng
được chuẩn bị trong W7–W8; W10 dành cho chương kết quả, rà soát và bảo vệ.

## Đầu vào đã nhận từ W9, 21/10/2026

[Bàn giao W9-06](../week9/README.md#w9-06--khóa-kết-quả-tái-lập-và-bàn-giao-21102026)
đã khóa 64 điểm/384 Decision của holdout 2024, kiểm report/bootstrap/publication
offline PASS và lưu bản `frozen_results_v1.zip` gồm 4.432 file nguồn/bằng chứng.
Checksum archive và ba lệnh kiểm tại README W9; run/ledger/archive được giữ
cục bộ trong thư mục ignored, cần đi cùng workspace và runtime, không chỉ Git.
Nguồn code/bằng chứng của bản lưu trữ ở mốc `cc16e7c`; tài liệu bàn giao quản lý
tiếp trong Git. Chưa hoàn tất task W10 nào hoặc nghiệm thu bốn gate W10-03.

| Phần cần viết/kiểm | Nguồn đã nhận |
| --- | --- |
| Phương pháp và phân tách 2023/2024 | [Protocol W9](../week9/README.md#protocol-thống-kê-đã-khóa-tại-w7-14), [selection development W8](../week8/README.md#w8-06--khóa-selection-development-20102026) |
| Kết quả, CI, ablation và hạn chế | [Thống kê W9-04](../week9/README.md#w9-04--bootstrap-và-kết-quả-thống-kê-holdout-21102026), [phân tích W9-05](../week9/README.md#w9-05--bảng-hình-và-phân-tích-giới-hạn-21102026) |
| Hình/bảng cho luận văn và slide | [Publication manifest](../../figures/holdout_v1/manifest.json), [catalog 5 hình/12 bảng](../week9/README.md#w9-05--bảng-hình-và-phân-tích-giới-hạn-21102026) |
| Tái lập, đóng gói và kiểm checksum | [Archive và lệnh offline W9-06](../week9/README.md#w9-06--khóa-kết-quả-tái-lập-và-bàn-giao-21102026) |

Primary A−Original **+2,025325 đpt**, CI95% **[0,135027; 4,211864]** hỗ trợ
kết quả dương trên cohort/protocol và Decision đã lưu; bốn secondary đều
inconclusive. Giữ VNM bất lợi, A prior-off 39/64 với 2/39 request giống nhưng
action khác, BEAR n=0, tin reliable 0/64 và trace legacy NOT_APPLICABLE.
Không suy cơ chế Bayes/nhân quả hoặc hiệu quả live; không dùng holdout chọn
lại cấu hình. Tái kiểm từ saved Decision không bảo đảm gọi lại LLM cùng response.
Deadline và deployment/risk OFF giữ nguyên; tiếp theo W10-01.

## Checklist

| Task | Công việc và tiêu chí hoàn thành | Trạng thái |
| --- | --- | --- |
| W10-01 | Chốt chương phương pháp: tách lý thuyết Bayes phân cấp, posterior số học, retrieval, ICL và policy; không tuyên bố LLM đã thực hiện Bayes hiệu chuẩn | [ ] TODO |
| W10-02 | Hoàn thiện kết quả: tách 2023 development khỏi 2024 xác nhận; trình bày mọi cấu hình thử, CI, ablation, kết quả bất lợi và dữ liệu thiếu | [ ] TODO |
| W10-03 | Kiểm tái lập code/data/runtime/config, hash và liên kết; hướng dẫn cài đặt/chạy/verify; bốn gate kỹ thuật cho mã bàn giao | [ ] TODO |
| W10-04 | Hoàn thiện Word/LaTeX/PDF và 25–30 slide; hình/bảng nhất quán với artifact đã verify | [ ] TODO |
| W10-05 | Diễn tập bảo vệ, rà câu hỏi về leakage, selection bias, sample size, attribution và giới hạn LLM; khóa bản nộp | [ ] TODO |

Nếu W9 incomplete hoặc ứng viên không vượt Original, trình bày đúng trạng
thái, phạm vi quan sát và giới hạn kết luận. Đóng góp hệ thống/PIT/retrieval
và bằng chứng thực nghiệm được phân biệt với ưu thế kinh tế chưa chứng minh.
Không chọn riêng mã thắng, không dùng p>0,05 để kết luận tương đương, không
gọi development đã tối ưu là test độc lập. Hướng sau deadline gồm mở rộng
memory, regime mềm, cross-symbol pooling và nhiều fold LLM nếu có cơ sở.

README gốc giữ tiếng Anh và hướng dẫn hệ thống, không đưa nhật ký tuần vào.
Tiến độ cập nhật ở đây và kế hoạch tổng; không tạo receipt theo từng task.
**Gate bàn giao:** luận văn/slide và hướng dẫn tái lập hoàn chỉnh, mọi claim
truy được về bằng chứng; không bắt buộc có lợi nhuận vượt trội để hoàn tất.
