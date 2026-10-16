# Tuần 9 — Benchmark holdout và phân tích thống kê

**Trạng thái: TODO, 0/6.** Giữ deadline 10 tuần; cập nhật 16/10/2026.
[Kế hoạch tổng](../plan.md) · [W8](../week8/README.md) · [W10](../week10/README.md)

## Phạm vi và đầu vào

Gate W8 PASS, selection/protocol/manifest mới đã khóa; cohort 2024 gồm
64 điểm, 16 điểm mỗi mã FPT/VNM/VCB/MWG. Không mở holdout trước khóa.
Dành khoảng 60% tuần cho chạy/đối soát và 40% cho thống kê/hình/bảng;
công cụ thống kê phải được chuẩn bị bằng fixture ở W8. Không phát triển ứng viên
mới trong tuần này; người dùng tự thực hiện preflight/API theo CLI đã kiểm.

## Protocol thống kê đã khóa tại W7-14

Áp dụng `improvement_protocol_v1` từ
[W8](../week8/README.md#protocol-cải-tiến-đã-khóa-tại-w7-14), hiệu lực
16/10/2026; đây là đặc tả, chưa có manifest holdout hoặc công cụ mới.
Giữ đủ **64 point ID/ngày W5, 16/mã**, không chọn lại theo regime/outcome.
Ma trận xác nhận gồm `original, bayesian, C2, selected_full,
selected_stats_only, selected_examples_only`; ánh xạ selected bằng selection
W8 rồi gộp ID trùng trước API. Chỉ ứng viên đã chọn được xem outcome; không
chạy cả A/B để chọn lại. Ablation dùng evidence/schema của chính selected,
không thay C2 bằng C3. Nếu thiếu consumer/verifier thì gate BLOCKED.

Primary mỗi point/nhánh **một Decision**, repeat_id=0. Xếp point theo
(as_of_date, thứ tự mã FPT/MWG/VCB/VNM), j từ 0; xoay trái danh sách ID
đã gộp j mod M bước, M là số nhánh. Giữ model/options, retrieval seed=42,
risk OFF và upstream một lần/point như W8. Không lặp holdout để lấy lượt
thuận lợi. Selection/registry/protocol và danh sách ID/thứ tự thực tế phải
bind vào manifest trước preflight/API; W8-07 mới tạo manifest này.

**Estimand chính:** D=(1/4)Σ_s(R_selected,s−R_original,s), đơn vị điểm
phần trăm, R là return tài khoản từ vốn đầu 50 triệu trên lịch của từng mã,
giữ engine lot/phí và T+2.5. Không lấy mean cycle return thay D, không gọi D
là return portfolio. Hướng mong đợi D>0; báo ΔR và ΔMDD từng mã/mean/max,
ΔMDD>0 là rủi ro tăng. Common support G chỉ COMPLETE khi đủ 64 điểm ở
mọi nhánh đã khóa; thiếu nhánh/unknown thì primary INCOMPLETE, không loại
điểm lỗi hoặc điền CASH. Pairwise phần có được chỉ là mô tả, không thay G.

**CI chính:** circular moving-block bootstrap trên chuỗi ngày cutoff duy
nhất tăng dần trong G, **L=4 ngày cutoff liên tiếp**, không phải bốn phiên
thị trường. Mỗi cụm giữ mọi mã có point ngày đó và mọi nhánh; không tạo
point cho mã vắng. Dùng NumPy `Generator(PCG64(20261016))`, **10.000 lần**:
lấy ceil(n_dates/4) điểm bắt đầu uniform có hoàn lại trong [0,n_dates−1],
mỗi điểm lấy bốn cụm liên tiếp modulo n_dates, nối rồi cắt còn n_dates.
Cùng chuỗi index cho mọi nhánh và mọi contrast. Dựng lại tài khoản từng mã
từ vốn đầu theo thứ tự mẫu tổng hợp, cùng lot/giá entry-exit/phí engine;
không cộng R/MDD đã tính sẵn hoặc sắp mẫu lại theo ngày lịch gốc. Số cycle
mỗi mã có thể đổi khi resample cụm; phải báo phân phối count từng mã.

CI percentile hai phía 95% lấy quantile 0,025/0,975, `method=linear`, của
D hữu hạn. Draw thiếu mã hoặc metric không hữu hạn là INVALID, ghi lý do;
không sinh thêm draw để thay. Cần ≥9.500/10.000 draw hợp lệ, nếu thiếu thì
CI=BLOCKED/insufficient, giữ point estimate nhưng không claim xác nhận.
CI hoàn toàn >0 hỗ trợ hiệu ứng dương trên cohort/protocol này; CI chạm
hoặc qua 0 là inconclusive, không kết luận tương đương. CI điều kiện trên
method/Decision đã lưu; không bao gồm bất định training, provider hoặc
kiến thức LLM lịch sử. L=4 chọn trước outcome để giữ phụ thuộc cục bộ trong
lịch rút gọn; không khẳng định là block tối ưu. Kiểm L=2/8 với cùng seed,
10.000 draw mỗi L, chỉ độ nhạy mô tả, không đổi CI chính hoặc chọn CI đẹp nhất.

**Secondary cố định:** selected−C2, selected−Bayesian v1,
selected_full−selected_stats_only và selected_full−selected_examples_only.
Contrast trùng/đồng nhất ID bị gộp trước API (selected=C2 thì bỏ contrast
tự so); số contrast m được ghi vào manifest. Dùng cùng bootstrap, CI
percentile Bonferroni mức 1−0,05/m cho từng D, quantile 0,05/(2m) và
1−0,05/(2m). Đây là family secondary riêng, không thêm phép so sau outcome.
MDD, accuracy, LONG/CASH, exposure, bảng action 2×2, Q1–Q4/H1–H2,
leave-one-symbol-out và subgroup prior-off/ready là mô tả; có mẫu số/null.
Không dùng McNemar/Wilcoxon làm kiểm định xác nhận trong protocol này vì
không bảo đảm các cycle độc lập. Không lấy p-value danh nghĩa để bỏ qua
phụ thuộc hoặc thay primary. Sharpe/Sortino giữ quy ước chu kỳ đã có.

Full/stats/examples phải cùng base evidence và schema, khác content mode;
G mô tả hiệu ứng gồm cả visibility/fallback, T cùng ready mới xem thành
phần trên bằng chứng chung. Trace không xác nhận cơ chế suy luận. Calibration
chỉ dùng xác suất sự kiện hợp lệ theo diagnostics W8, confidence văn bản
không là p. Không chọn/promote lại theo holdout, kể cả secondary hoặc subgroup
đẹp hơn; kết quả âm và thiếu lực kiểm định vẫn là kết quả phải công bố.

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
CI bootstrap theo block/cụm ngày và các kiểm phụ dùng đặc tả W7-14 đã bind ở W8;
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
