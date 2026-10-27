# Tuần 11 — Kiểm định giá trị tăng thêm của MT-BICL

**Amendment 28/10/2026; 0/8 task DONE. Chờ release v2 tại W10-14.**
[Kế hoạch tổng](../plan.md) · [W10](../week10/README.md) · [W12](../week12/README.md)

Lịch quản lý sau xác nhận quỹ giờ tại [W10-01](../week10/README.md#w10-01--inventory-và-khả-năng-thực-thi-27102026):
W11 dự kiến **02–05/11/2026**, tổng **4–8 giờ**. Chỉ thực hiện khi đủ gate
phụ thuộc; release và bắt đầu xác nhận chậm nhất 05/11, nếu không ghi NOT_RUN.

Một candidate Full_MT_BICL của **revision v2: teacher Beta-Bernoulli phân
cấp + learner distillation**, được chọn bằng quy tắc mới trước development.
V1 vẫn NO_MT_BICL_RELEASE; không sửa cờ cũ, không tái chọn checkpoint v1.
[Amendment W10](../week10/README.md#9-khắc-phục-nguyên-nhân-và-protocol-v2--28102026)
là thiết kế hiện hành. protocol_v1.json chỉ mô tả thí nghiệm đã đóng;
W10-09 phải tạo protocol v2, W10-14 mới cấp release chạy. Chưa có release.

Bayesian posterior đúng dưới giả định teacher và student học gần teacher
không chứng minh lợi nhuận. Development phải đo việc thêm posterior/examples
có giúp Decision LLM, giữ cả kết quả bất lợi và đối chứng phương pháp W9.

## 1. Ma trận đối chứng đăng ký trước run

| ID | Nội dung | Câu hỏi |
| --- | --- | --- |
| Original | Không context Bayes/ICL, cùng base/schema/model/options | Có hơn hệ thống gốc? |
| A_reference | A_tp_pool trên bank/feature/selector tương thích W9 đã kiểm | Có hơn phương pháp đã có bằng chứng? |
| Plain_ICL | Cùng prior/target examples như Full, bỏ p/output learner | Learned Bayes có giá trị ngoài demonstrations? |
| Full_MT_BICL | p student v2 + prior tasks + target context/examples | Candidate duy nhất, teacher/weights/hash v2 đã khóa |
| No_target | Recompute learner với C rỗng, bỏ target examples | Target context có giá trị? |
| Stats_only | Cùng p Full, bỏ demonstrations/ID/summary nhãn ẩn | Demonstrations LLM có giá trị ngoài numeric? |
| Numeric_only | Offline: LONG nếu p student>0,5 và input hợp lệ, còn lại CASH có reason | Lợi ích chỉ từ numeric hay cần LLM ICL? |
| Teacher_only | Offline: LONG nếu p teacher>0,5; cùng membership/rule | Chẩn đoán approximation gap; không là candidate thay thế |

A giữ nguồn W9, Full dùng dense price task bank: Full−A so toàn phương
pháp, không quy riêng gain cho cơ chế Bayes. Plain/No_target/Stats dùng
cùng nguồn Full, chỉ khác thành phần đã nêu. Không fabricate historical
agent reports để A dùng dense bank. Base instruction mới nếu có áp cho
tất cả nhánh; Original run mới không là phát lại W9 nguyên byte.

Teacher_only chỉ là chẩn đoán bổ sung, không thêm LLM slot, không thay
family năm contrast xác nhận đã nêu ở W12 và không được promote sau outcome.
Báo p_teacher/p_student, KL/Δp, action disagreement và latency trên cùng G;
không gán teacher đúng về toán thành nhãn thị trường đúng. Full−Plain_ICL
đo giá trị output learner ngoài demonstrations; Full−Stats_only đo giá trị
examples. Không dùng hai contrast này để tuyên bố hosted LLM tự tính Bayes
hoặc distillation tốt hơn mọi mô hình numeric khác.

Thiếu feature: giữ reason và reuse Original khi canonical request sau
tắt context trùng hoàn toàn. K=0/m=0 hợp lệ trong miền train, báo strata;
không loại khỏi G hoặc bịa task. Lỗi API/integrity không đổi thành CASH.

## 2. Development đầy đủ và ghép cặp

Giữ 60 point 2023 FPT12/MWG16/VCB16/VNM16 đã xem. Verify identity upstream
lịch sử rồi deep-copy; nếu không tương thích, tạo mới một lần/point theo
rule khóa trước run. Không gọi vision riêng cho nhánh/repeat. Model/options,
teacher/π, tokenizer và weights khóa ở W10-14; bank streaming chỉ thêm
observation đã đóng, không fit lại π. Original đầu, năm nhánh LLM còn lại
xoay j mod5 theo ngày/mã.

Sáu LLM×60=360 slot primary, Numeric offline. Repeat 12 point, ba/mã,
chọn trước action: ngày đầu m=0, m=1..3, m≥4; thiếu stratum bù ngày đầu
chưa chọn, ghi reason. Ba lượt bổ sung ×12×(6+duplicate)=252 slot;
Original đầu, sáu nhánh còn lại xoay (3j+r−1) mod6. Không vote hoặc lấy
lượt đẹp; repeat không tăng N primary. Reuse chỉ khi body/model/options/
schema đúng point/repeat trùng và Original durable; ledger ghi HTTP thật.

Trước API: K≥2 và m≥2 đồng thời ở ≥30/60 và≥5/mã. Đây là gate support
để kiểm task/target, không dự đoán thắng. Thiếu thì INSUFFICIENT_CONTEXT;
dense bank phải giải quyết trước run, không đổi block theo return.

G đủ 60 point. D là mean ΔR bốn tài khoản 50 triệu, net/lot/compounding
theo engine. Không cộng cycle payoff hay chỉ giữ point action đổi. Báo
K/m/regime/quý/prior-off, CASH→LONG lẫn LONG→CASH, leave-one-change-out,
leave-one-symbol-out, drawdown, LONG rate và mọi nhóm bất lợi.

## 3. Nomination và mục tiêu cải thiện rõ rệt

Khóa trước action: đủ G/verify, D_Full−Original>0, ≥3/4 mã ΔR>0,
D_Full−A≥0, mean ΔMDD≤2 và max ΔMDD≤5 đpt. Chỉ Full được xét; không
promote ablation thắng thay Full. Báo mọi repeat/đổi dấu; không sửa rule.
MDD dùng độ lớn sụt giảm không âm; ΔMDD=MDD_Full−MDD_Original theo mã,
giá trị dương là xấu hơn. Guard áp dụng cùng định nghĩa ở xác nhận.

Mục tiêu thực tiễn **D≥+1,0 đpt**, CI xác nhận không chạm 0, ≥3/4 mã
tăng, guard MDD đạt. Đây là định nghĩa đề xuất cho “cải thiện rõ rệt”,
không phải mức paper bảo đảm. Development dương dưới 1 đpt vẫn có thể
nominate theo rule trên để kiểm chứng, chưa được gọi là cải thiện rõ rệt.
MDE trên train/dev đã xem phải báo; N=128 không mặc nhiên đủ power 80%.

**Điều kiện vào development v2:** technical + synthetic test mới PASS,
semantic/coverage/paired PASS và receipt W10-14. Không bắt buộc student
thắng base rate trên 2022 mới được đo whole-system, nhưng phải công bố mọi
metric bất lợi trước release. Không dùng empirical Bayes/teacher trực tiếp
thay student FAIL. Nếu chưa đạt cơ chế thì W11-02–07 không được chạy.

Gate dự báo và nomination đo hai việc khác nhau, không đổi sau kết quả.
Full trượt: W11-06/07 NOT_RUN, tiếp tục tổng kết. Một vòng development;
sửa bug đổi hành vi sau outcome ghi revision/exploratory, không mở vòng
mới trong hạn này để tìm kết quả thắng.

## 4. Xác nhận và streaming context đúng PIT

2025 dự kiến 128 point, 32/mã, tám/quý. Step3 neo phiên đầu năm, cycle
hoàn tất trong quý; N ngày hợp lệ/mã/quý chọn floor(j(N−1)/7), j=0..7.
N<8 BLOCKED. Audit giá/quyền/source và exposure của mọi revision trước
release. Không rõ independence: exploratory; không tráo sang phần 2024
đã xem hoặc hứa forward đủ mẫu trong vài ngày.

Prior bank và target context 2025 cập nhật từ cycle giá đã đóng **exit<query** bằng
rule máy khóa trước run. Nhãn độc lập action, không gradient/refit/scaler/
tune trong 2025. Point test trước đã đóng có thể vào context point sau
đúng cutoff: khai báo **prequential evaluation**, không IID và không biết
cả năm ngay đầu run. Không đọc y query trước inference hoặc append từ
report evaluation caller tùy ý đưa vào. Đường market-label được kiểm riêng.

Mọi nhánh cùng upstream/snapshot mỗi cutoff; No_target bỏ đúng C đã kiểm.
Weights/prompt/seed/selection và π teacher giữ nguyên. Không mở payoff 2025 khi chuẩn
bị metadata trước release. Benchmark hồi cứu PIT còn giới hạn tri thức
sau cutoff trong weights hosted LLM.

Sáu LLM×128=768 slot primary, repeat 252 slot theo rule development;
Numeric offline. Khóa manifest/order/repeat trước response. Không dừng
sớm khi gain đẹp, thêm call khi CI chưa đẹp hoặc giảm N cho kịp tiến độ.

## 5. Checklist W11

Thứ tự công việc trong quỹ giờ trên: freeze → development/verify → phân tích/
nomination → exposure/release/bắt đầu xác nhận và bàn giao. Đây là thứ tự
phụ thuộc, không là cam kết hoàn tất trong bốn ngày hoặc ước lượng tốc độ API.

| Task | Đầu ra / gate | Phụ thuộc | Trạng thái |
| --- | --- | --- | --- |
| W11-01 | Đối soát release v2; freeze source/teacher/student/cohort/matrix/order/repeat, dry-run và receipt | W10-14 | [ ] TODO — chờ release v2 |
| W11-02 | Người dùng chạy primary 360 và repeat 252 slot, không missing/unknown | 01 | [ ] TODO |
| W11-03 | Cold verify v2 source/π/teacher/student/request/ledger/PIT; rebuild account, Numeric/Teacher offline | 02 | [ ] TODO |
| W11-04 | Report G/strata/ablation/action/repeat và approximation gap; không đồng nhất accuracy với P&L | 03 | [ ] TODO |
| W11-05 | Khóa NOMINATED/NOT_NOMINATED theo rule trước run | 04 | [ ] TODO |
| W11-06 | Exposure/MDE, manifest 2025 và release xác nhận riêng | 05 đạt | [ ] TODO — có điều kiện |
| W11-07 | Người dùng bắt đầu xác nhận; checkpoint để W12 tiếp nhận | 06 | [ ] TODO — có điều kiện |
| W11-08 | Bàn giao trạng thái/identity, phương pháp và kết quả cho W12 | 01–07 chốt trạng thái | [ ] TODO |

Không kịp release/bắt đầu cuối W11 thì không mở run mới ở W12. Thời gian
còn lại hoàn thiện luận văn, không W13. Theo AGENTS.md 1.2 chỉ test đường
đổi và đối soát receipt đúng nguồn, không tự chạy toàn suite mỗi task.

Amendment này được lập theo yêu cầu sửa phương pháp ngày 28/10 sau W10-07;
không còn áp dụng lệnh dừng mọi nghiên cứu mới của recipe v1 cho v2. Các
lệnh cấm sửa bằng chứng, chọn bằng test và triển khai khi chưa có release
vẫn giữ. Chưa gọi development/API, chưa tăng tiến độ task W11. Chỉ sửa
Markdown; kiểm diff/link/đồng bộ dependency, không chạy lại suite theo
AGENTS.md 1.2. Quỹ giờ và mốc 05/11, 07/11, 10/11 giữ nguyên.
