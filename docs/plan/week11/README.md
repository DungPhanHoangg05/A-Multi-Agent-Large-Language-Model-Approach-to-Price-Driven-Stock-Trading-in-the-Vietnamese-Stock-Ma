# Tuần 11 — Kiểm định giá trị tăng thêm của MT-BICL

**Cập nhật 28/10/2026; 0/8 task DONE. W11-01 đã chuẩn bị manifest,
dry-run và preflight offline; chờ người dùng chạy API preflight thật trước
khi đóng task hoặc mở primary/repeat. W10-14 chỉ release development2023.**
[Kế hoạch tổng](../plan.md) · [W10](../week10/README.md) · [W12](../week12/README.md)

Lịch quản lý sau xác nhận quỹ giờ tại [W10-01](../week10/README.md#w10-01--inventory-và-khả-năng-thực-thi-27102026):
W11 dự kiến **02–05/11/2026**, tổng **4–8 giờ**. Chỉ thực hiện khi đủ gate
phụ thuộc; release và bắt đầu xác nhận chậm nhất 05/11, nếu không ghi NOT_RUN.

Một candidate Full_MT_BICL của **revision v2: teacher Beta-Bernoulli phân
cấp + learner distillation**, được chọn bằng quy tắc mới trước development.
V1 vẫn NO_MT_BICL_RELEASE; không sửa cờ cũ, không tái chọn checkpoint v1.
[Amendment W10](../week10/README.md#9-khắc-phục-nguyên-nhân-và-protocol-v2--28102026)
là thiết kế hiện hành. protocol_v1.json chỉ mô tả thí nghiệm đã đóng;
W10-09 đã khóa protocol v2; W10-14 đã cấp [release](../week10/development_release_v2.json),
SHA `8459cfc1a4e95dae7512bc3c236fe102764d6af13ce5a7d3d19e0ce67d805121`,
chỉ cho development2023 sau run manifest/API preflight. Nguồn/teacher/
student/runtime/prompt/schema/cohort đã freeze; W11-01 vẫn phải khóa
manifest cụ thể, thứ tự nhánh và 12 repeat point ID trước response đầu.
Release này không cho phép xác nhận2025, train hoặc refit. Chưa chạy API.

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
| W11-01 | Đối soát release v2; freeze source/teacher/student/cohort/matrix/order/repeat, dry-run và receipt | W10-14 | [ ] OFFLINE_READY — manifest/dry-run/preflight offline PASS; API thật NOT_RUN, chờ người dùng |
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
vẫn giữ. Bàn giao W10-14 chưa gọi development/API hoặc tăng tiến độ W11.
Lượt amendment README trước W11-01 chỉ sửa Markdown, đã kiểm diff/link/
đồng bộ dependency và không chạy lại suite theo AGENTS.md1.2. W11-01 có
mã mới nên kiểm theo phạm vi tại mục6. Quỹ giờ và mốc 05/11, 07/11, 10/11 giữ nguyên.

## 6. W11-01 — Khóa manifest và preflight development (28/10/2026)

**OFFLINE_READY; chưa DONE:** phần chuẩn bị do agent thực hiện đã xong;
API preflight thật vẫn **NOT_RUN** theo quy tắc vận hành của
[kế hoạch tổng](../plan.md): “API key do người dùng chạy; agent chuẩn bị/kiểm
offline.” Không tăng tiến độ thành 1/8, không mở W11-02 và không coi mock
HTTP hoặc Decision fixture là phản hồi LLM thật.

[Run manifest](development_run_manifest_v2.json) và
[receipt preflight](development_preflight_v2.json) khóa riêng nguồn W11,
receipt W10-14, teacher/student, runtime, model/options/schema và cohort.
Nguồn/spec/bằng chứng W10 giữ nguyên; không train, refit, student forward,
chạy account/P&L hoặc đọc outcome development/2025. P/projection MT-BICL
được dùng lại từ W10-13 sau đối soát hash episode/membership đã release;
`No_target` giữ p đã recompute với C rỗng, không thay bằng p Full.

Nguồn W11 neo commit `92d0137`; SHA-256 byte:

- Manifest: `eb154447af175cc740fea5fd5602fcc39cba33e5cbe128689539ad04bda05561`.
- Receipt: `60e9c5ee3cc0eed87b78bc8c75b49eb77b6a54209516b9b63cb3bba75d4b6abb`.

Dry-run đủ612 slot và96 journal, cold replay PASS. Prompt tối đa **4.949
ký tự <6.500**, prefix **494≤600**, reserve tối đa **4.603 token≤8.000**.
Có121 slot canonical trùng Original đủ điều kiện shared-off và491 fixture
invocation; đây không phải số HTTP thật của run chưa bắt đầu. Preflight
offline có bảy mock HTTP qua SDK/`_invoke_with_retry`/pacer/audit thật; kiểm
body/model/options/schema và response parser. Ledger tài khoản3974 request
giữ nguyên SHA `e73a87e2a45d73e76f63cdd58225c2de06b0df4e03ed09b91ad0f6f71c5c8796`;
không reset hoặc ghi counter ngân sách W10.

Đã kiểm đủ **60 upstream lịch sử** bằng code/runtime/config, hash nguồn,
snapshot PIT, bốn stage durable, Full bundle và journal. Cấu hình khớp
release nên khóa reuse nguyên trạng, không tạo vision mới. `A_reference`
được dựng lại từ các báo cáo/tín hiệu thật bằng producer/index W9; không
dùng prefix sinh từ reports fixture trong dry-run W10. Các nhánh/repeat
deep-copy cùng shared point. Support đồng thời K≥2,m≥2 **41/60**:
FPT6/MWG12/VCB12/VNM11; giữ đủ 10 point thiếu feature trong G=60.

Manifest giữ **360 primary +252 repeat =612 slot**. `j` là chỉ số point
toàn cohort sau sort(cutoff,symbol_order), không đánh lại chỉ số trên mẫu
12 point. Primary Original đầu, xoay năm nhánh còn lại j mod5; repeat
Original đầu, xoay sáu nhánh kể cả duplicate theo (3j+r−1) mod6, r=1..3.
Chạy hết primary rồi repeat1, repeat2, repeat3; không đổi action theo vote.

| Mã | Ngày đầu m=0 | Ngày đầu m=1..3 | Ngày đầu m≥4 |
| --- | --- | --- | --- |
| FPT | 2023-05-11 | 2023-10-30 (m=1) | 2023-04-12 (m=8) |
| MWG | 2023-07-31 | 2023-02-08 (m=3) | 2023-01-06 (m=8) |
| VCB | 2023-08-03 | 2023-02-08 (m=3) | 2023-01-06 (m=8) |
| VNM | 2023-01-06 | 2023-02-08 (m=2) | 2023-03-06 (m=8) |

Cả12 point chọn bằng context trước action, không cần fallback. Quy tắc
fallback trong code giữ ngày đầu của mọi stratum hiện hữu trước khi bù
ngày đầu chưa chọn cho stratum thiếu; mỗi mã luôn ba ID khác nhau.
Reuse chỉ khi canonical point/repeat/request/body/model/options/schema
khớp Original durable; **36 Original_duplicate gọi riêng**, không shared-off.
Unknown giữ UUID/reserve và dừng, không tự replay hoặc chuyển thành CASH.

Kiểm theo AGENTS.md1.2: **71 lượt kiểm thử PASS**, gồm module mới
`test_mt_bicl_v2_run_manifest`, hồi quy adapter/Decision và
`test_mt_bicl_tasks_leakage`; có12 ca adapter được loader lặp do module
Decision import lớp fixture. Bốn file Python mới biên dịch PASS. Phạm vi
này phủ lịch/repeat, serializer/schema/options, token reserve, transport/
ledger, durable journal/duplicate, live-preflight bằng inner HTTP giả,
raw-response integrity và PIT. Không chạy full suite, compileall toàn repo
hoặc E2E; gate W10 chỉ được đối soát trên nguồn/runtime nguyên vẹn.

Lệnh tái kiểm offline (không đọc key hoặc gọi mạng):

```powershell
py -3.13 -X utf8 scripts/prepare_mt_bicl_development.py verify
```

**Bước còn lại của W11-01 do người dùng chạy:**

```powershell
py -3.13 -X utf8 scripts/prepare_mt_bicl_development.py api-preflight
```

Lệnh này cold-check manifest/receipt/Git/source trước khi đọc key, gửi
control JSON cố định qua `_invoke_with_retry`/transport/quota dùng chung,
ghi intent UUID trước HTTP và bind raw response/cache/ledger. Không gửi
point thị trường hoặc gọi upstream/primary/repeat. Chỉ cần text/schema
preflight vì toàn60 upstream đã được xác minh để reuse; không kiểm vision
bằng lời gọi mới. Thành công lưu
`outputs/bayesian_benchmark/mt_bicl_v2/development2023/live_api_preflight.json`.
Lệnh lặp dùng receipt durable, không gửi lại khi đã PASS; unknown dừng giữ
bằng chứng. Sau receipt API thật PASS mới đối soát để đóng W11-01 và triển
khai W11-02. Script hiện chỉ chuẩn bị/verify/preflight, chưa là runner ma trận.
