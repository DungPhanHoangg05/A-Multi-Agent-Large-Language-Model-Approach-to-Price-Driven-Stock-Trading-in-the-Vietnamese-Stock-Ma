# Tuần 12 — Xác nhận, định lượng đóng góp và bảo vệ

**Đồng bộ amendment29/10/2026; 0/6 task DONE. Thời hạn vẫn12 tuần.**
[Kế hoạch tổng](../plan.md) · [W10](../week10/README.md) · [W11](../week11/README.md)

Lịch quản lý theo [quỹ giờ đã xác nhận tại W10-01](../week10/README.md#w10-01--inventory-và-khả-năng-thực-thi-27102026):
W12 dự kiến **06–10/11/2026**, tổng **5–10 giờ**. Khóa dữ liệu cuối **07/11**;
08–10/11 dành luận văn/tái lập/bản nộp. Đây là phân bổ công việc, không xác
nhận hạn nộp chính thức hoặc bảo đảm đủ giờ viết mới toàn bộ luận văn.

Hai ngày làm việc đầu chỉ hoàn tất/resume xác nhận đã release và bắt đầu
ở W11. Hết ngày hai khóa dữ liệu, kể cả INCOMPLETE; không mở candidate,
tune hoặc giảm N. Phần còn lại dành luận văn, tái lập và bảo vệ.
V2 không đạt rule nomination; không mở xác nhận cho v2. Amendment v3 ở
[W11 mục13](../week11/README.md#13-w11-06--audit-kinh-tế-và-kế-hoạch-utility-aware-bayesian-icl-29102026)
chưa được khóa thành protocol; W11-07 phải đăng ký thông số bên dưới trước
run, W11-13/14 mới có thể release/bắt đầu xác nhận. Protocol v1/v2 và kết quả
cũ giữ nguyên, không thay cờ release bằng việc sửa Markdown.

## Phân tích xác nhận khóa trước run

Primary v3 D=mean đều bốn tài khoản [R_Full_utility_ICL−R_Original], net
theo engine cổ phiếu phân số đã khóa, không thêm lô chẵn sau outcome.
Circular moving-block bootstrap ngày cutoff duy nhất, giữ mọi mã/nhánh
cùng cụm: L=4, 10.000 draw, PCG64 seed=20261027, percentile linear CI95%;
≥9.500 draw hữu hạn, không sinh bù invalid. Dựng lại tài khoản từ action/
payoff lưu theo resample, không cộng Δcycle. L=2/8 chỉ sensitivity.
Với context prequential, CI này điều kiện trên saved predictions, không
tái tạo đường học hoặc toàn bộ bất định training/provider; không CI live.

Family v3 gồm7 secondary: Full−A/Fact_Anchor/Plain_revision/No_utility/
No_target/Stats_only/Utility_only. Bonferroni CI(1−0,05/7)=99,285714% mỗi
contrast, cùng draws/common support; Full là Full_utility_ICL. Family5 của
v2 chỉ giữ để tái lập, không áp nhầm vào ma trận v3. Thiếu support
giữ null; không chọn nhóm/repeat thuận lợi thay G. Model seed/LLM repeat
báo riêng, không nhân thành số quan sát độc lập.

| Bằng chứng | Claim được phép |
| --- | --- |
| Primary CI>0 | Hệ thống MT-BICL cải thiện trên cohort/protocol xác nhận |
| Thêm D≥1 đpt, ≥3/4 mã tăng, guard MDD đạt | Đạt mục tiêu thực tiễn “cải thiện rõ rệt” |
| Full−Fact_Anchor CI>0 | Context/Bayes/policy thêm giá trị ngoài sửa dữ kiện |
| Full−Plain_revision CI>0 | Posterior/utility/policy thêm giá trị ngoài cùng demonstrations; chưa tách riêng distillation |
| Full−No_utility CI>0 | Utility và rule sửa action thêm giá trị |
| Full−No_target CI>0 | Target context thêm giá trị trong cấu hình này |
| Full−Stats_only CI>0 | Demonstrations trong Decision thêm giá trị ngoài numeric output |
| Chỉ Utility_only thắng | Đóng góp numeric, chưa chứng minh LLM ICL |
| CI qua 0 hoặc run thiếu | Inconclusive/INCOMPLETE, không tuyên bố tương đương hoặc thắng |

Synthetic mechanism đạt nhưng thị trường không tăng: báo đúng hai mức.
Nếu chỉ W9 có hiệu ứng xác nhận, giữ đúng phạm vi, không đổi tên thành
MT-BICL. Giải trình mọi vòng đã xem/lựa chọn thích nghi; archive không xóa exposure.

## Checklist W12

| Task | Đầu ra / gate | Phụ thuộc | Trạng thái |
| --- | --- | --- | --- |
| W12-01 | Hoàn tất/resume run được phép; khóa COMPLETE/INCOMPLETE/NOT_RUN trước cuối ngày hai | W11-15 | [ ] TODO |
| W12-02 | Cold verify/account oracle/bootstrap/secondary/noise/strata | 01 đủ mẫu, nếu không ghi NOT_RUN xác nhận | [ ] TODO |
| W12-03 | Khóa bảng/hình/claim; tách synthetic/validation/development/xác nhận | 01–02 chốt trạng thái | [ ] TODO |
| W12-04 | Phương pháp/kết quả/thảo luận, hạn chế selection/PIT/prequential | 03 | [ ] TODO |
| W12-05 | Checksum/restore/cài đặt; receipt và test đúng phạm vi mã bàn giao | 04 | [ ] TODO |
| W12-06 | Word/LaTeX/PDF, 25–30 slide, diễn tập và khóa bản nộp | 05 | [ ] TODO |

Không chạy toàn suite chỉ để cập nhật checklist; không tự bật model mới
làm mặc định. Root README giữ tiếng Anh, tiến độ ở docs/plan.

Đồng bộ29/10 chỉ sửa dependency/ma trận/claim theo kế hoạch W11 mới; không
đổi gate kinh tế, lịch hoặc artifact xác nhận. Chưa chạy xác nhận2025.
