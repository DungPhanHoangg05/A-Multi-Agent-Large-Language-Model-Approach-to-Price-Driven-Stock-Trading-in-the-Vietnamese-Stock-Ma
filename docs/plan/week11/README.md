# Tuần 11 — Kiểm định phiên bản hợp nhất và khóa kết quả nghiên cứu

**Trạng thái: kế hoạch mới ngày 24/10/2026, 0/10 task DONE.**
[Kế hoạch tổng](../plan.md) · [Thiết kế W10](../week10/README.md) · [W12](../week12/README.md)

## Mục tiêu và đối chứng

Trả lời ba câu hỏi riêng: U-BICL có ích so Original không; có tốt hơn A trên
cùng nguồn không; demonstrations và stats có đóng góp tăng thêm không.
Không lấy việc xóa revision cũ làm bằng chứng phương pháp mới chưa từng
chịu selection; 2023/2024 đã xem vẫn được khai báo. Chỉ một candidate U_full.
Không chọn U_stats/U_examples làm sản phẩm sau khi thấy chúng thắng.

| ID | Nội dung | Vai trò |
| --- | --- | --- |
| Original | Không prior, instructions/schema chung của run | Đối chứng hệ thống gốc trong protocol mới |
| A_reference | Thuật toán/evidence A, nguồn memory chung, shared-off mới | So U với phương pháp mạnh nhất đã có bằng chứng; không tái hiện W9 nguyên byte |
| U_full | Posterior đã khóa + context task/episode theo rule | Candidate duy nhất |
| U_stats | Cùng base evidence, chỉ stats | Đo lợi ích tăng thêm của demonstrations |
| U_examples | Cùng base evidence, chỉ examples/task context | Đo lợi ích tăng thêm của posterior stats |
| Numeric_only | Posterior mean>0,5 khi ready, còn lại CASH có reason | Đối chứng số học, không LLM, không candidate |

U_examples được phép hiển thị nhãn/cặp x→y và support nhóm cần hiểu task;
không hiển thị posterior/CrI hay recommendation từ stats. Summary tỷ lệ nhóm
là một phần demonstration, phải giữ nguyên giữa full/examples và mô tả rõ:
contrast đo block posterior, không có nghĩa loại mọi thông tin thống kê.
U_stats không chứa x→y, task IDs hoặc ví dụ ẩn. Cả ba dùng cùng evidence hash;
fallback visibility khác nhau theo block, phải báo G và T cùng ready riêng.

## A. Development và nomination trước xác nhận

Giữ 60 ngày 2023 đã khóa, FPT12/MWG16/VCB16/VNM16; không lấy ngày thuận lợi
khác. Năm nhánh LLM ×60=300 slot primary, Numeric tính offline. Original
đầu mỗi block; năm mã logic còn lại gồm Numeric nhưng chỉ bốn nhánh LLM
được xoay theo index j mod 4, điểm xếp (ngày, FPT/MWG/VCB/VNM). Cùng upstream
một lần/point và deep-copy; chỉ reuse upstream lịch sử khi identity verified,
nếu không thì tạo mới một lần cho cả ma trận trước Decision. Khóa cách này
trước run, không chọn upstream tạo lợi nhuận tốt.

Repeat development: 12 điểm, mỗi mã ba điểm chọn bằng readiness U_full
trước action: ngày đầu của both-ready, one-block-ready, off; stratum rỗng
bù ngày đầu chưa chọn của mã, ghi reason. Lặp ba lượt bổ sung, năm nhánh
LLM + Original_duplicate=216 slot; Original đầu, năm nhánh còn lại xoay
(3j+r−1) mod 5. Shared upstream/request primary, source Original theo repeat.
Không vote, chọn response hoặc nhập repeat vào D primary; retry HTTP không
phải repeat khoa học. Slot logic khác HTTP thật khi shared-off; báo cả hai.

Nomination yêu cầu: đủ 60 point, metric hữu hạn, bốn gate/primary/repeat
verify PASS; prior visible≥30/60 và ≥5/mã; examples visible≥12/60 và ≥2/mã
để thực sự kiểm ICL. Gate multi-task ở W10 quyết định mức claim, không giả
task coverage khi chỉ có episode fallback. Nếu thiếu coverage, report
insufficient evidence và dừng release; không hạ ngưỡng sau kết quả.

Gate kinh tế development: D_U−Original>0, ΔR>0 ở ≥3/4 mã, D_U−A≥0,
mean ΔMDD≤2 và max ΔMDD≤5 đpt. Các ngưỡng là rule lựa chọn, không kiểm
định thống kê xác nhận. Báo mọi nhóm xấu/repeat; không chọn bằng một repeat
thuận lợi. Không đạt thì không mở xác nhận để cứu kết quả hoặc chọn ablation;
chuyển sang hoàn thiện luận văn, ghi U chưa được chứng minh. Một vòng duy nhất;
sửa lỗi đổi hành vi sau outcome cần revision/exploratory riêng và công bố
lượt cũ, không ghi đè rồi coi là run đầu tiên.

## B. Xác nhận độc lập sau khóa

Dự kiến 2025: 128 điểm, 32/mã, tám/quý. Rebuild audit từ nguồn hợp lệ; không
tái dùng output revision đã rút làm execution plan. Giữ step3 neo phiên đầu
năm, cycle hoàn tất trong quý, loại quyền/thiếu giá theo rule nguồn; với N
ngày hợp lệ/mã/quý lấy floor(j*(N−1)/7), j=0..7. N<8 thì BLOCKED trước API,
không giảm N sau outcome. Giá thô/PIT/exposure audit và MDE simulation train/
dev phải có trước release; không coi N=128 đủ power một cách mặc định.

2025 đã từng có audit/khai báo trong lịch sử; xác minh có sử dụng mới để
tune hay không, không chứng nhận độc lập bằng cách xóa file. Không xác minh
được thì cohort chỉ exploratory, hoặc forward từ sau lock nếu đủ thời gian.
Không lấy phần 2024 còn lại để làm holdout mới. Không append outcome 2025
vào memory trong run xác nhận này. Không mở 2025 trước nomination/release.

Ma trận sáu ID như trên, năm nhánh LLM ×128=640 slot primary. Mẫu repeat
xác nhận 12 điểm bằng cùng rule readiness, ba lượt ×6=216 slot; lock mẫu và
thứ tự trước action. Numeric offline. HTTP thực tế thấp hơn số slot logic
nhờ reuse; không coi reuse/alias là số quan sát độc lập tăng thêm.

Nghiên cứu tối đa 300+216+640+216=1.372 slot Decision LLM logic, chưa tính
upstream/retry/preflight; đây là mô tả protocol, không là dự toán quota.
Người dùng tự chạy API; hoàn thành development không tự cấp release xác nhận.

## C. Phân tích và tiêu chí khẳng định hữu ích

Primary D=(1/4)Σ(R_U,s−R_Original,s), bốn tài khoản 50 triệu, cổ phiếu lẻ/
lot theo engine, net đầy đủ phí/slippage. Không mean cycle hoặc portfolio.
G chỉ COMPLETE khi mọi nhánh đủ 128 điểm; unknown/error/missing không CASH,
không bỏ điểm lỗi. T cùng stats/examples ready là subgroup mô tả, không thay G.

Circular moving-block bootstrap theo ngày cutoff duy nhất, giữ mọi mã/nhánh
cùng cụm; dựng lại tài khoản theo chuỗi resample. L=4, 10.000 draw,
PCG64 seed=20261024; percentile linear, CI95% primary, ≥9.500 finite draws,
không sinh bù invalid. Sensitivity L=2/8 mô tả, không chọn CI đẹp. Báo count
mã/draw và invalid reasons. Không cộng các Δcycle để thay account return.

Secondary family cố định: U_full−A_reference, U_full−U_stats,
U_full−U_examples, U_full−Numeric_only; Bonferroni CI98,75% từng contrast,
cùng draws/common support. Nếu ID/request alias thì công bố, không tăng mẫu.
MDD, accuracy/balanced accuracy, LONG/CASH, hit rate, regime/quý, LOSO,
prior-off/readiness, task/fallback strata đều mô tả; không chọn nhóm thắng
thay primary. Sharpe/Sortino giữ chu kỳ, không tự annualize √252.

| Bằng chứng | Claim được phép |
| --- | --- |
| Primary CI hoàn toàn >0 | U có ích hơn Original trên cohort/protocol và Decision đã lưu |
| Secondary U−A CI hoàn toàn >0 | Hợp nhất vượt phương pháp A trên cùng nguồn/protocol mới |
| Full−stats CI>0 sau hiệu chỉnh | Block demonstrations có đóng góp tăng thêm |
| Full−examples CI>0 sau hiệu chỉnh | Block posterior có đóng góp tăng thêm |
| CI chạm/qua 0 | Chưa đủ bằng chứng, không phải tương đương hoặc không có hiệu ứng |
| Chỉ Numeric thắng | Báo lợi ích của mô hình số; không gán công cho Bayesian ICL |

CI điều kiện trên saved Decision, chưa bao phủ training/provider uncertainty.
Repeat báo disagreement từng nhánh/Original-duplicate, contrast từng lượt và
mean, đủ mẫu số; các cặp phụ thuộc không là quan sát độc lập. Prior-off=0 do
reuse không chứng minh LLM ổn định. Nếu repeat đổi dấu hoặc duplicate nhiễu,
nêu rõ hạn chế tái lập dù CI primary dương; không claim live/deterministic.

## D. Khóa nghiệm thu và luận văn

| Task | Công việc | Phụ thuộc | Đầu ra/nghiệm thu | Trạng thái |
| --- | --- | --- | --- | --- |
| U11-01 | Dry-run/release development, nguồn/model/order/repeat | U10 | Bốn gate/source/prompt PASS; CLI đã kiểm | [ ] TODO |
| U11-02 | Người dùng chạy primary/repeat development | 01 | Slot đầy đủ, journal/reuse/ledger, không unknown | [ ] TODO |
| U11-03 | Verify/analysis và khóa nomination | 02 | Rule đã đăng ký, G/T/task/fallback/repeat đầy đủ; không chọn ablation | [ ] TODO |
| U11-04 | Exposure/giá mới, manifest và release xác nhận | 03 đạt | 128 điểm/matrix/seed/source/receipt khóa trước outcome | [ ] TODO |
| U11-05 | Người dùng chạy primary/repeat xác nhận | 04 | Đúng namespace/identity, không đổi phương pháp giữa run | [ ] TODO |
| U11-06 | Semantic/PIT/kinh tế/paired/reuse verification | 05 | Đủ G, không missing/unknown, nguồn/hash đúng | [ ] TODO |
| U11-07 | Bootstrap, ablation, noise và failure analysis | 06 | Primary/family/CI/rủi ro/mẫu số và kết quả bất lợi đầy đủ | [ ] TODO |
| U11-08 | Đóng băng evidence, bảng/hình và checksum | 07 | Run/response/HTTP/source/config/version tái lập, không key | [ ] TODO |
| U11-09 | Viết kết quả/thảo luận và phân loại claim | 03; 08 nếu có | Không trộn W9 với U; khai báo các vòng phát triển đã xem | [ ] TODO |
| U11-10 | Bàn giao W12, hướng dẫn verify và giới hạn | 09 | Quyết định research/deployment riêng; không tự bật mặc định | [ ] TODO |

Đầu W11 ưu tiên development, giữa tuần lock xác nhận nếu đạt, cuối tuần
phân tích. Nếu API kéo dài, W12 chỉ tiếp tục đúng run đã khóa và ưu tiên
bản nộp; không tối ưu thêm hoặc giảm mẫu cho kịp. Task xác nhận thiếu điều
kiện ghi NOT_RUN/BLOCKED, không PASS giả. Một thiết kế kiểm chứng được và
kết quả trung thực vẫn là đóng góp khóa luận; không thể hứa trước kết quả thắng.

Mã/runtime nâng cấp chưa có ở task lập kế hoạch. Khi triển khai dùng namespace
unified_bic_v1, producer/loader/verifier/schema riêng, không ghi vào W9 hoặc
ledger giả. Mọi thay đổi P0 chạy bốn gate; source freeze/version và CLI thật
được phát hành ở W10, không cung cấp lệnh giả để người dùng chạy ngay.
