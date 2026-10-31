# Giai đoạn W12 — Xác nhận độc lập, định lượng đóng góp và bảo vệ

**Kế hoạch tiếp nối 31/10/2026; 0/8 task DONE. Không giới hạn thời gian.**
[Kế hoạch tổng](../plan.md) · [W10](../week10/README.md) · [W11](../week11/README.md)

W11-15 bàn giao v3 **NOT_NOMINATED**, xác nhận v3 **NOT_RUN**; receipt và
kết quả bất lợi tại [mục21 W11](../week11/README.md#21-w11-12--kiểm-toán-kinh-tế-phân-rã-và-nomination-v3-31102026).
W11-16 audit paper và thiết kế v4 tại [mục22 W11](../week11/README.md#22-w11-1516--đóng-v3-audit-cách-áp-dụng-paper-và-kế-hoạch-v4-31102026).
Không chuyển release v3 thành release v4; W12 chỉ xác nhận candidate v4
sau W11-24/25 đạt nomination và có protocol/release riêng.

Theo chỉ đạo mới, bỏ trần giờ, khung 5–10 giờ, hạn 12 tuần, các mốc 05/11,
07/11, 10/11 và quy tắc “hai ngày đầu phải khóa dữ liệu”. W11/W12 là tên
phase, không hạn lịch. Có thể chuẩn bị/chạy xác nhận mới trong W12 sau
khi đủ dependency. Thời gian chờ quota, resume hoặc thu thập cohort forward
không làm run tự hết hạn. Giữ PIT, T+2.5, retry/backoff, integrity và mẫu
đăng ký trước; không mở kết quả lặp lại để dừng khi CI vừa dương.

W11-17 đã khóa [protocol v4](../week11/protocol_v4.json) và verifier metadata
tại [mục23 W11](../week11/README.md#23-w11-17--khóa-protocol-conditional-mt-bicl-v4-31102026).
Chưa triển khai learner, train hoặc chạy API v4, chưa đọc payoff2025.
Protocol này chưa khóa N/block-length xác nhận hoặc cấp release W12.
W11-18 audit ngày01/11 có snapshot PIT nhưng **INSUFFICIENT_DATA**, chưa
nghiệm thu hoặc mở W11-19; [chi tiết](../week11/README.md#24-w11-18--dataset-pit-và-thiếu-hụt-đầu-vào-agent-01112026).
Nếu đường chạy cũ còn guard deadline, task triển khai sau này phải bỏ
cho namespace v4 và kiểm theo phạm vi; sửa README không thay hành vi CLI.

## 1. Exposure và cohort xác nhận

- W12-01 audit toàn bộ nguồn, log truy cập, train/calibration/retrieval,
  thử nghiệm và quyết định thiết kế trước khi chọn holdout. ≤2022 và2023
  đã dùng phát triển nhiều vòng;2024 có bằng chứng W9, không là test mới.
- 2025 chỉ được dùng nếu audit chứng minh chưa dùng outcome/đặc trưng hậu kỳ
  để chọn v4. Việc chưa chạy một CLI xác nhận không tự chứng minh độc lập.
  Nguồn giá đã đọc, truy vấn trước đây hoặc các vòng đã bỏ phải được khai báo.
- Nếu2025 không còn đủ độc lập, giữ nó là exploratory và dùng cohort
  forward bắt đầu **sau thời điểm khóa candidate/protocol**. Không đổi
  sang năm/mã có kết quả đẹp. Không hứa số mẫu mới có ngay; không deadline
  cho phép thu thập đủ mẫu thay vì hạ chuẩn kiểm định.
- Universe, lịch sampling, số cutoff, rule khi nghỉ giao dịch/quyền/thiếu
  feature và vốn/account khóa trước. Không đổi số mã hoặc thời gian nắm
  giữ để khuếch đại D. Bốn mã cũ là estimand chính; mã thêm nếu có là kiểm
  khả năng khái quát, báo riêng.
- Prior/target được cập nhật từ cycle đã đóng với exit<query; đây là
  prequential evaluation. Weights, calibration, policy, feature scaling,
  lựa chọn task và model/options giữ nguyên. Không gradient/refit giữa run.

## 2. Cỡ mẫu và khóa phân tích trước khi mở kết quả

**Không giữ128 point chỉ vì lịch cũ.** W12-02 ước lượng MDE/power bằng dữ
liệu development và cấu trúc phụ thuộc theo ngày/block; báo giả định và
độ bất định, không mặc định power80%. Chọn một cỡ mẫu/cohort trước run để
kiểm mục tiêu D≥1 đpt và rủi ro. Nếu thực tế chưa đủ mẫu, giữ INCOMPLETE
và thu thập tiếp đúng cohort; không bỏ ca thiếu hoặc tăng N sau khi xem CI.
Nếu cần thiết kế tuần tự, phải đăng ký alpha-spending/confidence sequence
trước; mặc định một lần phân tích cuối khi đủ mẫu đã khóa.

Primary: D=mean đều bốn account [R_Full_conditional_MT−R_Original], net
phí/lãi kép theo engine hiện có. Báo D theo mã, MDD, số LONG, hai chiều
sửa action, coverage/OOD/fallback và cost/latency. Accuracy chỉ là mô tả.
Không cộng cycle return hoặc gộp seed/repeat thành quan sát độc lập.

CI primary95% dùng paired block bootstrap trên ngày cutoff, giữ cùng cụm
mọi mã/nhánh. Rebuild account theo thứ tự resample đã định nghĩa, kiểm
bằng oracle; không cộng Δcycle. Độ dài block khóa từ dependency development
và độ nhạy trước holdout, không tự kế thừa L=4 cho cohort mới. Dùng10.000
draw, seed cố định trong protocol, báo mọi invalid và yêu cầu≥9.500 draw
hữu hạn; không sinh bù để cứu CI. Bootstrap điều kiện trên predictions
đã lưu, không bao phủ toàn bộ bất định training/provider. Không annualize
nếu thiết kế cohort không hỗ trợ diễn giải đó.

Ma trận v4 theo W11 mục22.5 có **8 secondary** Full−A_reference/Plain_ICL/
Target_only_K0/Pooled_context/No_target/No_agent_features/Numerical_MT/
Hierarchical_reference. Khóa family trước run, Bonferroni hai phía
CI(1−0,05/8)=**99,375%** mỗi contrast, cùng draws. Chỉ diễn giải kết quả
của family đã khóa; không bỏ comparator âm để giảm hiệu chỉnh.

Forecast report tách NLL/CRPS/calibration/coverage và decision report.
K0/pooled phải được train đối chứng tương ứng, giữ feature/data/capacity/
selection budget tương đương. Thay x hoặc prior trên synthetic có oracle
là kiểm cơ chế; không dùng synthetic PASS thay kiểm thị trường. Chỉ một
candidate từ W11, không chuyển sang ablation tốt nhất sau xác nhận.

## 3. Bằng chứng cần cho từng kết luận

| Bằng chứng xác nhận | Claim được phép |
| --- | --- |
| Primary CI95%>0 | Cấu hình Full cải thiện so Original trên cohort/protocol đã khóa |
| Thêm D≥1 đpt, ≥3/4 mã cũ tăng, mean ΔMDD≤2 và max≤5 đpt | Đạt mục tiêu cải thiện rõ rệt đã định nghĩa cho cohort này |
| Full−K0 và Full−pooled có CI đã hiệu chỉnh>0, kiểm cơ chế đạt | Có bằng chứng prior-task và cấu trúc multi-task đóng góp; không chỉ thêm model hoặc data |
| Full−No_target CI đã hiệu chỉnh>0 | Target context giúp thích ứng trong cấu hình này |
| Full−No_agent_features CI đã hiệu chỉnh>0 | Tín hiệu agent bổ sung giúp ngoài feature thị trường và a0 dùng chung |
| Full−Numerical_MT CI đã hiệu chỉnh>0 | Quyết định nền đa agent có ích ngoài predictor numeric thuần |
| Full hơn Plain_ICL | So sánh toàn phương pháp numeric advisor với ICL văn bản; không đồng nhất với proof hosted LLM tự làm Bayes |
| Learner gần reference, tốc độ tốt hơn trên cùng input | Hiệu quả xấp xỉ/inference trong miền đã kiểm; không chứng minh reference là truth thị trường |
| Chỉ forecast tốt hơn, P&L chưa tăng | Đóng góp dự báo; chưa chứng minh nâng cấp giao dịch |
| Full tăng nhưng K0/pooled chưa phân biệt | Có lợi ích hệ thống, chưa tách được đóng góp multi-task Bayesian ICL |
| CI qua0 hoặc cohort thiếu | Inconclusive/INCOMPLETE; không kết luận tương đương hoặc thắng |

Giữ kết quả v1/v2/v3 và W9 trong phạm vi gốc; không đổi tên W9 thành bằng
chứng của v4. Xác nhận fail phải được báo; nghiên cứu tiếp cần revision và
exposure mới, không xem chính holdout đã mở như test độc lập lần nữa.

## Checklist W12

| Task | Đầu ra / gate | Phụ thuộc | Trạng thái |
| --- | --- | --- | --- |
| W12-01 | Audit exposure/source và khóa holdout độc lập hoặc cohort forward | W11-25 có candidate nominated | [ ] TODO |
| W12-02 | Khóa cỡ mẫu, ma trận, repeat, CI/family/power, source và release xác nhận | 01 | [ ] TODO |
| W12-03 | Người dùng chạy xác nhận đủ cohort; checkpoint/resume không deadline | 02 | [ ] TODO |
| W12-04 | Cold verify, independent account oracle, bootstrap, ablation và robustness | 03 đủ mẫu | [ ] TODO |
| W12-05 | Khóa bảng/hình/claim và quyết định nghiên cứu; ghi cả failure/inconclusive | 04 | [ ] TODO |
| W12-06 | Phương pháp/kết quả/thảo luận, giới hạn mô hình/PIT/exposure/prequential | 05 | [ ] TODO |
| W12-07 | Checksum/restore/cài đặt, model/data card và kiểm theo source bàn giao | 06 | [ ] TODO |
| W12-08 | Hoàn thiện luận văn/slide, diễn tập và bản nộp theo bằng chứng | 07 | [ ] TODO |

Nếu W11 không nominate, 01–04 chưa được chạy; vẫn có thể viết phần phương
pháp và kết quả âm đã có. Không gọi đó là nghiệm thu hiệu quả v4 hoặc bắt
buộc dừng nghiên cứu vì hết tuần. Không tự bật candidate làm mặc định.

## Tham chiếu lịch sử và kiểm tra lần cập nhật

[Protocol v3](../week11/protocol_v3.json) từng đăng ký128 point, block L=4,
primary95%, family7 secondary99,285714%; xác nhận v3 NOT_RUN. Những thông
số đó chỉ phục vụ tái lập thiết kế cũ, không là protocol v4. Các ngày chót,
grant/counter giờ trong receipt cũ giữ như lịch sử, không còn áp dụng.

Chỉ sửa Markdown; kiểm diff/link/anchor, số liệu, checklist và hash nguồn.
Theo AGENTS.md1.2 không chạy lại unit/compileall/E2E/leakage suite cho
lượt này. Code/runtime/schema/JSON/evidence vẫn nguyên byte; root README
không dùng để ghi tiến độ.
