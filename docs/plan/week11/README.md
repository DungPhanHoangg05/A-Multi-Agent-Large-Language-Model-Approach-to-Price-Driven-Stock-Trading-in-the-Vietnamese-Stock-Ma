# Tuần 11 — Kiểm định giá trị tăng thêm của MT-BICL

**Cập nhật 29/10/2026; 4/8 task DONE. W11-04 report/replay PASS tại mục12.
G=60: D Full−Original=−0,024757 đpt; không kết luận accuracy tăng là P&L tăng.
Tiếp theo W11-05: khóa nomination theo rule đã đăng ký.**
[Kế hoạch tổng](../plan.md) · [W10](../week10/README.md) · [W12](../week12/README.md)

**Chạy mới hoặc tiếp tục sau khi ngắt/đổi key đều dùng:**

```powershell
py -3.13 -X utf8 scripts/continue_mt_bicl_development.py
```

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
Release này không cho phép xác nhận2025, train hoặc refit. API development
đã hoàn tất theo manifest/extension riêng; nghiệm thu tại mục10.

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

G đủ 60 point. D là mean ΔR bốn tài khoản 50 triệu, net/phí/lãi kép
theo engine đã khóa: cổ phiếu phân số, chưa áp dụng lô chẵn (làm rõ tại mục11).
Không cộng cycle payoff hay chỉ giữ point action đổi. Báo
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
| W11-01 | Đối soát release v2; freeze source/teacher/student/cohort/matrix/order/repeat, dry-run và receipt | W10-14 | [x] DONE — cold-check parent/runner và API preflight/raw/cache/ledger thật PASS |
| W11-02 | Người dùng chạy primary 360 và repeat 252 slot, không missing/unknown | 01 | [x] DONE —360/360 primary +252/252 repeat durable; audit/cache/ledger PASS, unknown0/pending0 |
| W11-03 | Cold verify v2 source/π/teacher/student/request/ledger/PIT; rebuild account, Numeric/Teacher offline | 02 | [x] DONE —cold replay PASS,32 account primary +108 repeat, Numeric/Teacher đủ60 point |
| W11-04 | Report G/strata/ablation/action/repeat và approximation gap; không đồng nhất accuracy với P&L | 03 | [x] DONE —đủ G60, mọi contrast/strata/repeat, sensitivity và KL/latency; report/hình replay PASS |
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

**Nghiệm thu API thật đã PASS tại mục8.** Mốc chuẩn bị28/10:
**OFFLINE_READY; chưa DONE**, phần chuẩn bị do agent thực hiện đã xong;
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

Verifier lạnh sau neo Git **PASS**: tái dựng toàn bộ lịch và612 canonical/
HTTP contract từ nguồn, đối soát120 file upstream cùng96 journal dry-run,
cold replay không invoke lại Decision, và replay bảy mock HTTP. Kiểm
323 nguồn/spec W10 không file nào đổi; diff và liên kết Markdown PASS.
Log kiểm thử cục bộ `outputs/bayesian_benchmark/mt_bicl_v2/preflight_scoped_tests.log`
có SHA `0c07253bfb26153cdb14606ea04dd4925482f32afc3f805d20da051e8edab8c8`.

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

**Lệnh API tại mốc chuẩn bị W11-01; hiện đã PASS, không cần chạy lại:**

```powershell
py -3.13 -X utf8 scripts/run_mt_bicl_development.py api-preflight
```

Lệnh này cold-check manifest/receipt/Git/source trước khi đọc key, gửi
control JSON cố định qua `_invoke_with_retry`/transport/quota dùng chung,
ghi intent UUID trước HTTP và bind raw response/cache/ledger. Không gửi
point thị trường hoặc gọi upstream/primary/repeat. Chỉ cần text/schema
preflight vì toàn60 upstream đã được xác minh để reuse; không kiểm vision
bằng lời gọi mới. Thành công lưu
`outputs/bayesian_benchmark/mt_bicl_v2/development2023/live_api_preflight.json`.
Lệnh lặp dùng receipt durable, không gửi lại khi đã PASS; unknown dừng giữ
bằng chứng. Sau receipt API thật PASS mới đối soát để đóng W11-01.
`prepare_mt_bicl_development.py` giữ nguyên source/receipt đã freeze; lệnh
API legacy của script đó có lỗi khóa đã xác định dưới đây. Dùng entrypoint
mới cho API; có thể chạy thẳng `run` ở mục7 để tự preflight rồi tiếp W11-02.

### 6.1. Tái nghiệm thu W11-01 (29/10/2026)

**PASS — W11-01 DONE.** Đối soát offline bằng `verify_extension`, verifier
continuation và `verify_live_preflight`: release W10-14, 323 nguồn/spec,
teacher/student/candidate, runtime, Git anchor, manifest/receipt và 612
canonical request còn đúng bản khóa. Toàn bộ 60 upstream, 120 file point/journal
và 96 journal dry-run giữ nguyên hash; 12 repeat ID/order và support 41/60
không đổi. Prompt tối đa 4.949<6.500 ký tự, prefix 494≤600, reserve 4.603 token.

API control thật HTTP 200, UUID `42972198-f7eb-4df8-87c1-daf8e26d1ae4`,
khớp model/options/schema, body, raw cache, response parser và ledger.
Control ở vị trí 3974 của ledger (đếm từ 0), trước HTTP scientific đầu ở 3975.
SHA-256 byte receipt API `live_api_preflight.json`:
`f03c5ae9316b3d99d25c8f0fbbf00930bef0cf7585d9fc686730bca9f443b72d`;
raw cache: `ff1a526e9604b3a88c99b5532751ffe010878a4e997bd8c7ad0184cfe0999864`.
Ba hash release/manifest/receipt chuẩn bị vẫn đúng các giá trị tại mục6.

Kiểm checkpoint hiện tại bằng `inspect_prefix` PASS: 612 complete,
360 primary +252 repeat, không pending/unknown. Có121 shared-off và36
Original_duplicate; 519 HTTP scientific gồm 491 HTTP 200, 26 HTTP 429 và hai
transport_error được giữ audit/reserve. Ledger toàn tài khoản 4.498 row,
SHA `6de7ea8d023a9530c99d1c334ae94f248ba3c8297b7418497503cb73481b56b5`;
hash cây 612 file slot (content hash của map tên file→SHA byte) là
`e49227da39a30a19e874214b0d75e3ac8a750f4657f40236c3d8edb9bf0c75fe`.
Đối chiếu trước/sau xác nhận ledger và slot không đổi trong lượt nghiệm thu.
Đây là snapshot hoàn tất chạy W11-02; nghiệm thu riêng W11-02 và bước
W11-03/account/P&L/nomination chưa thực hiện.

Chỉ sửa Markdown theo AGENTS.md1.2, không chạy lại compile/unit/E2E/leakage.
Viện dẫn đúng 71 lượt test và bốn file Python biên dịch PASS tại mục6;
log test còn nguyên SHA `0c07253bfb26153cdb14606ea04dd4925482f32afc3f805d20da051e8edab8c8`.
Không đọc key, gọi API, inference/train hoặc sửa receipt/bằng chứng đã khóa.
Diff/liên kết và số liệu nghiệm thu được đối soát trong lượt này.

## 7. W11-02 — Runner ghép cặp và sửa entrypoint preflight (29/10/2026)

**Mốc trước API: READY_FOR_USER_RUN; chưa DONE.** Tiến độ thật tại mục8.
Người dùng đã gửi log lệnh preflight
legacy dừng với `Owner khác host/signature hoặc metadata không xác minh được`.
Đối soát thực tế không có `live_api_preflight.json`, ledger vẫn3974 request
và SHA nền nguyên vẹn. Vì vậy chưa thể nghiệm thu W11-01 hoặc ghi đã chạy
development. Lỗi ở entrypoint: offline dùng signature cố định, API dùng
hash manifest nhưng cả hai khóa cùng `development2023/`; `PriorRunLock`
từ chối signature khác kể cả owner cũ đã released.

Entry point mới giữ nguyên source/manifest/receipt W10 và W11-01, không
xóa/sửa owner cũ hoặc nới kiểm host/OS lock. Các chế độ mới cùng dùng khóa
`development2023/operations/` với signature cố định; API còn giữ khóa ledger
tài khoản chung. Control request/model/options/schema và định dạng receipt
API vẫn nguyên. Đây là bổ sung vận hành **trước response development đầu**,
không là revision chọn lại candidate hoặc sửa phương pháp sau outcome.

[Extension runner](development_runner_v2.json) neo source commit `6a1cfde`,
SHA byte `5ebd7c2e4e0882abb704ce4a4b66dde27339c5301fba9fba9ba5ff9a656362ff`.
Khóa riêng ba file source/test mới, runtime, hash parent và snapshot đủ612
canonical request. Request được trích từ journal đã seal rồi so hash với
manifest; không lấy Decision fixture làm kết quả. Không đổi teacher/student,
p, upstream, cohort, order, repeat ID hoặc hợp đồng kinh tế/PIT.

Runner tạo identity và **đủ612 slot pending durable trước HTTP đầu**, giữ
lịch360 primary rồi252 repeat. Sau mỗi slot ghi intent/UUID hoặc response;
sau mỗi point ghi progress. `Original_duplicate` luôn gọi riêng. Shared-off
chỉ dùng Original complete cùng point/repeat và request nguyên vẹn. Mọi
HTTP qua `_invoke_with_retry`/transport/pacer/audit hiện hữu, thêm guard so
body thực với contract đã khóa trước network. Retry/format repair giữ cùng
scientific UUID; ledger đếm HTTP thật, không đổi số slot.

Resume bằng cùng lệnh `run`: slot complete không gọi lại; nếu ngắt sau
HTTP thành công nhưng trước checkpoint, chỉ khôi phục khi raw cache/UUID/
body/schema/audit khớp và parse lại được cùng Decision. Unknown thiếu raw
durable vẫn dừng giữ reserve/UUID, không tự gửi lại hoặc đổi thành CASH.
Mất slot sau ready, sai identity, lẫn fixture/research, sửa request/action/
cache hoặc có kết quả vượt khoảng pending/unknown đều dừng trước HTTP tiếp.

Kiểm theo phạm vi: **44 ca liên quan đạt**, gồm17 ca runner mới,14 ca
Decision và13 ca context leakage. Lượt đầu41/42 PASS; test guard còn lại
dùng messages rỗng nên nhận đúng lỗi schema trước lỗi model mong đợi.
Đã sửa fixture thành messages hợp lệ/model sai và retest riêng PASS; thêm
hai ca parent hash/runtime/upstream PASS. Không chạy lại41 ca đã PASS vì
logic của chúng không đổi. Ba Python mới biên dịch PASS; không full suite,
compileall toàn repo hoặc E2E. Gate W10/W11-01 được đối soát bằng hash,
runtime, Git và receipt đã PASS theo AGENTS.md1.2; không lặp612 fixture và
bảy mock HTTP cũ mỗi lần khởi động runner.

Dry-run runner trên canonical request thật **PASS360/360 primary +252/252
repeat**, unknown0, duplicate36, shared-off121 và491 fixture dispatch;
không có API thật/upstream/student forward hoặc P&L. Progress fixture ở
`development2023/runner_dry_run/progress.json` có SHA
`e61cb9869d2fd3942b3f6ada86ee676e67b7a77d133018c118e112a820b18396`,
identity `offline_fixture`. Đối soát323 nguồn/spec W10 và hai receipt
W11-01 nguyên byte; ledger tài khoản vẫn3974 request/SHA nền. Research
giữ612 slot pending, chưa có action hoặc unknown. Đây là bằng chứng kiểm
runner, không thay cho run thật W11-02.

**Lệnh ở mốc chuẩn bị runner; hiện dùng entrypoint mục9 để tự resume/đổi key:**

```powershell
py -3.13 -X utf8 scripts/run_mt_bicl_development.py run
```

Lệnh cold-check parent/extension/source/runtime/request/Git, giữ lock,
kiểm checkpoint trước khi đọc key. Nếu chưa có preflight, gửi control
request trước; chỉ sau API preflight thật PASS đúng credential mới gọi
primary/repeat. Không cần chạy lại lệnh preflight legacy bị lỗi. Khi đủ
612 slot, lệnh in `COMPLETE_AWAITING_W11_03`; không tính P&L, nomination,
Numeric/Teacher hoặc mở2025 trong runner này.

Kiểm trạng thái offline và chạy dry-run độc lập:

```powershell
py -3.13 -X utf8 scripts/run_mt_bicl_development.py status
py -3.13 -X utf8 scripts/run_mt_bicl_development.py dry-run
```

Artifact research ở `outputs/bayesian_benchmark/mt_bicl_v2/development2023/run/`;
`identity.json`, `ready.json`, `requests.json`, `slots/`, `http_cache/` và
`progress.json` phải giữ nguyên khi resume. Fixture dùng `runner_dry_run/`
với identity `offline_fixture`, không được migrate sang research. Ledger
tài khoản chung và ngân sách W10 không reset; không giảm N, lọc nhánh/mã,
vote repeat hoặc gọi upstream mới. Tại mốc chuẩn bị này chưa tăng tiến độ
W11-01/02 trước bằng chứng API thật; cập nhật nghiệm thu ở mục8.

## 8. Phục hồi request bị quota từ chối (29/10/2026)

Đây là mốc recovery tường minh trước yêu cầu resume một lệnh. Entry point
này còn ràng buộc key với preflight cũ; từ nay dùng mục9, không cần UUID.

API preflight thật **PASS**, UUID HTTP `42972198-f7eb-4df8-87c1-daf8e26d1ae4`;
verifier đã đối soát source/runtime/Git, parent/extension, body/schema/model,
raw response/cache và ledger. **W11-01 DONE**, không chạy lại các gate cũ
hoặc sửa receipt lịch sử. W11-02 chưa đủ mẫu để nghiệm thu.

Checkpoint thực tế có **139 complete, một unknown,472 pending**. Log point
cuối hiển thị138 nhưng Original của point tiếp đã durable, nên không lấy
log point làm số slot đã lưu. Unknown ở index139 (slot thứ140),
`VNM-2023-06-01 / No_target / repeat0`, scientific UUID
`25b3723b-c25c-4def-9d5d-d50e064d023d`. HTTP
`e07faa45-2b0e-4144-ade6-5092612733b1` trả429, chưa có response/cache200.
`last_stop.reason=PROVIDER_DAILY_QUOTA`; mốc thử lại sớm nhất provider ghi
`2026-10-28T19:13:06.481181Z`, tức **02:13:06 ngày29/10 giờ Việt Nam**.
Mốc đó không bảo đảm provider đã cấp quota; giữ admission/cooldown gốc.

Runner frozen vẫn dừng unknown khi chạy lại `run`. Vì vậy bổ sung
[recovery vận hành](development_recovery_v2.json), source commit `c4676cb`,
SHA byte `25aa9833c3fbbabc9fdab1dcde23176df2aefe250dfea46a5473cb13cf9dce85`.
Đây là sửa phục hồi sau partial run, không đổi prediction/action rule,
candidate, request/model/options/schema, teacher/student, cohort, order,
repeat hoặc nomination. Giữ source/receipt runner trước đó nguyên byte;
không mở thí nghiệm mới, đọc payoff hoặc chọn lại kết quả.

Chỉ lệnh người dùng chỉ rõ UUID mới được retry. Verifier yêu cầu toàn bộ
HTTP thuộc UUID đều là429 đã audit đúng body/slot, không có response mô
hình/cache thành công. Unknown do transport_error, HTTP khác, thiếu bằng
chứng hoặc sai audit vẫn dừng. Trước retry ghi authorization durable;
giữ **cùng UUID/request**, giữ mọi row/reserve cũ và append HTTP mới.
Sau response thành công mới cập nhật slot complete bằng raw cache/audit,
rồi chuyển về runner gốc để tiếp tục. Slot complete không gọi lại.

```powershell
py -3.13 -X utf8 scripts/resume_mt_bicl_development.py retry-rejected 25b3723b-c25c-4def-9d5d-d50e064d023d
```

Lệnh này tự tiếp tục `run` sau khi slot429 hoàn tất; không cần reset file
hoặc chạy lại từ đầu. Nếu provider lại từ chối429, giữ checkpoint/UUID và
thử lại theo cooldown; không xóa ledger hoặc reserve. Các dòng nghỉ chủ
động của pacer là hoạt động bình thường, không phải mất tiến độ.

Kiểm theo phạm vi: **8 test phục hồi PASS**, ba Python mới biên dịch PASS;
kiểm retry giữ UUID/reserve, complete không replay, ngắt vẫn giữ intent,
chặn HTTP/unknown/cache/audit không đủ điều kiện và phát hiện sửa row cũ.
Không đổi data/PIT/retrieval hoặc runtime dùng chung nên không chạy lại
leakage/full suite/E2E; viện dẫn gate cũ sau đối soát hash/runtime/receipt.
Agent chỉ chuẩn bị và kiểm offline, chưa gửi request retry thật.

## 9. Một lệnh chạy và tiếp tục, tự preflight khi đổi key (29/10/2026)

Yêu cầu mới của người dùng: “khi bị ngắt vì bất kì lý do gì thì chỉ cần
chạy 1 lệnh là chạy được tiếp”. Lỗi `Credential khác preflight` do các CLI
cũ yêu cầu key hiện tại khớp proof cũ. Entry point mới tự tạo proof cho key
hiện tại, giữ proof/ledger của key trước; không cần người dùng chạy riêng
preflight hoặc nhập UUID. `.env` có ưu tiên hơn biến môi trường như trước,
console chỉ báo nguồn key, không in giá trị key.

```powershell
py -3.13 -X utf8 scripts/continue_mt_bicl_development.py
```

Đây là lệnh cố định cho lần đầu, sau Ctrl+C, tắt terminal/máy, lỗi mạng,
quota hoặc đổi key. Nó tự kiểm source/runtime/request/Git và checkpoint,
khôi phục response durable hợp lệ trước, preflight key hiện tại khi cần,
tìm intent còn dở rồi retry **cùng UUID/body/model/options/schema**. Slot
complete không gọi lại; không lọc mã/ngày/nhánh hoặc đổi thứ tự612 slot.
Preflight cũng tự phục hồi nếu bị ngắt, có signature riêng để không bị
coi là scientific slot thừa. Key cũ và mới giữ proof riêng trong
`run/credential_preflights/`; đổi key không xóa usage hoặc reset quota
thực của cùng tài khoản provider.

Quota ngày có thời điểm reset thì chương trình tự chờ theo provider, chia
nhỏ thời gian chờ để vẫn ngắt được. Sau khi ngắt, chạy lại chính lệnh đó.
Key không hợp lệ, thiếu quyền hoặc quota reset sau hạn dữ liệu được báo
đúng nguyên nhân; sửa điều kiện ngoài rồi dùng cùng lệnh, không reset file.
Hash/request/schema sai hoặc cache đã đóng dấu bị mất/sửa vẫn dừng kiểm
integrity, không âm thầm bỏ qua. Response200 sai định dạng được giữ audit
và tiếp tục format repair; cache hoàn chỉnh nhưng thiếu dấu cuối do crash
chỉ được hoàn thiện dấu khi byte/body/audit khớp.

[Amendment vận hành](development_continuation_v2.json), source `c9b2d4f`,
SHA byte `4bcd0c931c453c9218cdc5dcdc19f24d7e5b3471ceab43d75d7b6ad126298db2`,
khóa ủy quyền tự retry unknown theo yêu cầu mới; không sửa source/receipt
W10, parent, runner hoặc recovery cũ. Giữ request/reserve cũ, append HTTP
mới và ghi authorization resume durable. Nếu response bị mất trước khi
durable, provider có thể đã xử lý request: cùng UUID không bảo đảm HTTP
exactly-once. Ledger giữ cả lần chưa rõ và lần retry; **scientific slot/N
primary/repeat không tăng**, không chọn lại kết quả đã complete. Đây là
amendment phục hồi sau partial run, không thay candidate/weights/context/
prompt, hợp đồng kinh tế/PIT, phương pháp hoặc mở vòng development mới.

Kiểm theo phạm vi: **24 test PASS** (14 mới,10 hồi quy transport/cache),
ba Python mới biên dịch PASS. Test tích hợp chạy lệnh mặc định với key mới
và unknown429, tự preflight rồi hoàn tất612 slot bằng SDK/MockTransport;
kiểm thêm interruption trước HTTP/trong preflight/sau raw response,
reserve/audit, chờ quota, format repair và chặn cache/request/action sai.
Không đổi market data/PIT/retrieval nên không chạy lại leakage/full suite/
E2E; đối soát hash/runtime và viện dẫn gate đã khóa. Agent chỉ kiểm offline,
chưa dùng key hoặc gửi API thật thay người dùng.

Cold-check entrypoint mới trên checkpoint thật PASS:139 complete, một
intent dở. Ledger4088 request và toàn bộ612 file slot giữ nguyên hash so
với trước thay đổi; source runner/recovery cũ nguyên byte. `--status` không
đọc key hoặc gửi HTTP; chưa thực hiện retry thật trong lượt sửa này.

## 10. W11-02 — Nghiệm thu ma trận development hoàn tất (29/10/2026)

**PASS — W11-02 DONE; 2/8 task hoàn tất.** Run research có identity/ready/
request snapshot đúng bản khóa và đúng 612 file slot. Đối soát trực tiếp
bằng `verify_extension`, verifier recovery/continuation, `runner.inspect`,
`validate_attempt` và `audit_response`; không lấy riêng log tiến độ làm bằng chứng.

- Primary: 360/360 slot, sáu nhánh mỗi nhánh đủ 60 point;
  FPT12/MWG16/VCB16/VNM16, không lọc điểm thiếu feature.
- Repeat: 252/252 slot, đúng 12 point đã khóa, ba point/mã, mỗi point
  ba lượt bổ sung với bảy nhánh. Mỗi nhánh có 36 slot; toàn bộ 36
  Original_duplicate có UUID/HTTP riêng. N primary giữ 60, không vote repeat.
- Cả 96 block point/repeat bắt đầu bằng Original; từng slot khớp thứ tự,
  canonical request, body/model/options/schema và manifest. Có 121 shared-off
  đúng Original durable cùng point/repeat; 491 slot còn lại có UUID riêng,
  mỗi slot đúng một HTTP200 và decision khớp raw response đã đóng dấu.
- Tổng 519 HTTP scientific: 491 HTTP200, 26 HTTP429, hai transport_error.
  Mọi row/token reserve và audit retry được giữ; không orphan/trùng HTTP UUID,
  không missing/unknown/pending trong checkpoint. `progress.json` khớp hoàn toàn
  số đếm tái dựng và trạng thái `COMPLETE_AWAITING_W11_03`.
- Bốn proof preflight theo credential và bốn authorization resume khớp
  policy/UUID/slot/body/cache/ledger. Preflight gốc hoặc proof tương ứng có
  trước HTTP scientific của credential đó; các row HTTP trước retry còn đúng
  hash đã ghi trong authorization. Sau ledger nền chỉ thêm 524 HTTP Decision
  (519 scientific +5 control), không gọi lại upstream/vision.

Ledger 4.498 row và cây 612 slot còn đúng hai hash tại mục6.1. SHA byte
`run/progress.json`: `98ddd0bcf81c255302937ff93e2fc8d9469ef2f5260b15e501c4d664a65ff8ac`.
Hash cây toàn bộ file trong `run/` (content hash của map đường dẫn tương đối→SHA byte):
`4e37d4809e4a0136766c53a3e46e62a811b0a316a95066ca7f121271bd936529`.
Đối chiếu trước/sau xác nhận toàn bộ cây run và ledger giữ nguyên trong
lượt nghiệm thu. Source/receipt/runtime W10, W11-01, runner, recovery và
continuation nguyên vẹn; không đọc key, gọi API hoặc sửa dữ liệu nghiên cứu.

Chỉ sửa tài liệu nên theo AGENTS.md1.2 không chạy lại unit/compile/E2E/leakage;
viện dẫn kiểm thử tại mục7–9 sau đối soát đúng nguồn/runtime: 44 lượt runner,
8 recovery và 24 continuation PASS, các file Python mới đã biên dịch PASS.
Diff, liên kết và số liệu được kiểm trong lượt này. Tại mốc nghiệm thu02,
W11-03 còn TODO; kết quả thực hiện tiếp theo được ghi tại mục11.

## 11. W11-03 — Cold verify và tái dựng tài khoản offline (29/10/2026)

**PASS — W11-03 DONE; 3/8 task hoàn tất.** Consumer mới `core/mt_bicl_v2_audit.py` và CLI
`scripts/verify_mt_bicl_development.py` giữ nguyên source/receipt và toàn bộ
run đã khóa. OS lock dùng chung với runner/ledger; socket mạng bị chặn,
không đọc key, gọi LLM, student forward, train/refit hoặc reset ngân sách.

Verifier đối chiếu snapshot W11-02, release/source/runtime/Git, teacher π,
candidate, toàn bộ UUID/raw response/cache/ledger và proof preflight/retry;
tái dựng 60 upstream/PIT/A_reference cùng 612 canonical request từ nguồn.
Mỗi nhãn prior/target được kiểm với giá thực thi và helper kinh tế, gồm
cycle streaming năm 2023 ngoài bank tĩnh cuối 2022, luôn yêu cầu exit<query.

Numeric giữ p full precision của student đã seal trên cùng episode;
Teacher được tính lại trên cùng D/C bằng π đã khóa, so oracle scalar độc
lập với sai số≤10⁻¹². Hai nhánh đều LONG chỉ khi p>0,5 và feature hợp lệ;
10 query thiếu feature giữ CASH kèm lý do, không loại khỏi G. Toàn bộ action
offline cố định trước bước evaluator mở giá query.

Tài khoản primary gồm tám nhánh×bốn mã, mỗi tài khoản khởi đầu 50 triệu;
repeat có tài khoản riêng trên ba point/mã/lượt, giữ cả Original_duplicate,
không trộn vào N primary. Dùng nguyên `compute_account_metrics`, đối soát
số dư lãi kép và MDD bằng phép tính độc lập. LONG vào Open(t+1), ra Close(t+3),
phí 0,25% và trượt giá 0,10% mỗi chiều; SHORT giữ CASH. Engine thực tế dùng
cổ phiếu phân số, **chưa mô phỏng lô chẵn**; không bổ sung rounding sau outcome.
Risk báo theo cycle, không dùng annualization mặc định cho cohort lấy mẫu thưa.

Report duy nhất tại `outputs/bayesian_benchmark/mt_bicl_v2/development2023/verification/accounts.json`,
ngoài cây `run/`; bind source commit/hash, runtime, manifest, toàn bộ cây run
và ledger. Lệnh mặc định dựng và lưu immutable; `--verify-only` tái dựng từ
nguồn rồi so toàn payload với report, không ghi lại checkpoint hoặc report.

```powershell
py -3.13 -X utf8 scripts/verify_mt_bicl_development.py --verify-only
```

Source neo commit `6ccc73c`; report đã dựng có SHA-256 byte
`fab7ebe0b2102a17487ed02d5c099a53671b696323a9d7ca377dec050544a348`.
Kết quả: 1.506 lượt nhãn context PASS, 50 AVAILABLE/10 thiếu feature,
96 block point/repeat; **32 tài khoản primary và108 tài khoản repeat**.
Numeric primary có1 LONG/59 CASH; Teacher primary có0 LONG/60 CASH,
giữ nguyên ngưỡng và mọi kết quả bất lợi. **Cold replay `--verify-only` PASS**:
tái dựng lại từ nguồn, toàn bộ payload khớp report đã lưu; hash report không đổi.
Ledger4.498 row và cây run còn đúng hash W11-02 tại mục10, không sửa checkpoint,
response hoặc bằng chứng cũ. Tại mốc này chưa thực hiện W11-04/05;
báo cáo W11-04 tiếp theo tại mục12, chưa nomination hoặc release2025.

Kiểm theo phạm vi AGENTS.md1.2: **84 ca riêng biệt PASS, gồm35 ca leakage**:
14 ca audit mới,23 account engine,12 adapter,13 task leakage,15 upstream/
news/context leakage và7 execution-price leakage. Lượt đầu60/61 PASS,
fixture mới thiếu cột Reference được sửa và retest PASS; thêm ca streaming
ngoài bank tĩnh và retest các caller kiểm nhãn sau sửa. Ba file Python mới
biên dịch PASS, chỉ biên dịch lại hai file thay đổi sau lần sửa cuối.
Không chạy full suite/compileall/E2E hoặc replay train/student cũ; các gate
nguồn/runtime đã khóa được đối soát, không ghi là chạy lại.

## 12. W11-04 — Báo cáo development, ablation và approximation gap (29/10/2026)

**PASS — W11-04 DONE; 4/8 task hoàn tất.** Consumer mới
`core/mt_bicl_v2_report.py` neo commit `994ba03`, chỉ dùng account report
W11-03 nguyên byte, manifest và ledger đã khóa. Đối soát nguồn/runtime/Git,
release/artifact, snapshot run và tái dựng cả 140 account gốc PASS; viện dẫn
cold replay/PIT W11-03 trên đúng hash, không chạy lại upstream/model/train/API.

[Report JSON đầy đủ](../../../outputs/bayesian_benchmark/mt_bicl_v2/development2023/analysis/report.json)
có SHA byte `ce4ac6b6c2f168ad8e88822236a38277ac46d812382414a691bcebfb8b89fb8d`;
[hình kết quả](../../../outputs/bayesian_benchmark/mt_bicl_v2/development2023/analysis/results.png)
có SHA `e51e886833119aaef0333c726017f835fa8812fc7ce7d2016e27a241ce5535af`.
Hình đã kiểm trực quan. Tái dựng `--verify-only` PASS: JSON khớp toàn payload,
PNG khớp byte. Account report, ledger4.498 row và cây run giữ nguyên hash W11-03.

### G và các contrast

G giữ đủ60 point FPT12/MWG16/VCB16/VNM16, kể cả10 query thiếu feature;
không excluded. Return và MDD dưới đây là mean đều bốn tài khoản50 triệu,
không return portfolio hoặc mean cycle. Accuracy tính trên60 nhãn net T+2.5.

| Nhánh | Mean return (%) | Mean MDD (%) | LONG/60 | Accuracy (%) |
| --- | ---: | ---: | ---: | ---: |
| Original | 4,464827 | 3,289574 | 18 | 63,3333 |
| A_reference | 3,863475 | 2,734120 | 15 | 61,6667 |
| Plain_ICL | 4,558348 | 2,857530 | 15 | 65,0000 |
| Full_MT_BICL | 4,440070 | 3,236194 | 17 | 65,0000 |
| No_target | 5,124525 | 2,953465 | 17 | 65,0000 |
| Stats_only | 4,145531 | 2,953465 | 17 | 61,6667 |
| Numeric_only | −0,231525 | 0,231525 | 1 | 58,3333 |
| Teacher_only | 0,000000 | 0,000000 | 0 | 60,0000 |

| Full so với | D (đpt) | Action khác/60 |
| --- | ---: | ---: |
| Original | −0,024757 | 5 |
| A_reference | +0,576596 | 6 |
| Plain_ICL | −0,118278 | 2 |
| No_target | −0,684455 | 4 |
| Stats_only | +0,294539 | 4 |
| Numeric_only | +4,671596 | 18 |
| Teacher_only (chẩn đoán) | +4,440070 | 17 |

Full accuracy cao hơn Original nhưng return mean thấp hơn. Full cũng kém
Plain_ICL và No_target trong development này; không thay candidate bằng
ablation thắng. Full−A là so toàn phương pháp khác bank, không tách riêng
hiệu ứng Bayes; các contrast không chứng minh hosted LLM tự tính Bayes.

| Mã | R Original (%) | R Full (%) | ΔR (đpt) | ΔMDD (đpt) |
| --- | ---: | ---: | ---: | ---: |
| FPT | 1,308248 | 1,308248 | 0,000000 | 0,000000 |
| MWG | 13,285611 | 17,509784 | +4,224173 | −2,693586 |
| VCB | 1,327621 | −0,433664 | −1,761285 | 0,000000 |
| VNM | 1,937829 | −0,624086 | −2,561915 | +2,480065 |

Chỉ1/4 mã có ΔR>0; mean ΔMDD=−0,053380 và max ΔMDD=+2,480065 đpt.
Đây là số liệu đầu vào cho W11-05, chưa phải receipt nomination.

### Strata, action và sensitivity

JSON giữ đủ K=0..3, m=0..8 cùng ba nhóm m, năm regime kể cả UNKNOWN,
bốn quý, trạng thái feature, support gate và prior-off của từng nhánh.
Mỗi subgroup dựng tài khoản mới trên đúng support; không cộng subgroup
thành D_G. Nhóm rỗng trả null/NO_SUPPORT; thiếu mã giữ D bốn tài khoản null
và báo mean theo các mã hiện hữu ở trường mô tả riêng.

| Nhóm | N | D Full−Original (đpt) |
| --- | ---: | ---: |
| K=0 / feature unavailable | 10 | 0,000000 |
| K=3 / available | 50 | −0,012581 |
| m=0 | 11 | 0,000000 |
| m=1..3 | 11 | −0,454117 |
| m≥4 | 38 | +0,409698 |
| BULL | 19 | +0,624326 |
| BEAR | 4 | −0,721529 |
| CHOPPY | 29 | 0,000000 |
| CONSOLIDATION | 8 | 0,000000 |
| Q1 | 12 | null — chỉ3 mã, không có FPT |
| Q2 | 16 | +0,317274 |
| Q3 | 16 | +0,274435 |
| Q4 | 16 | −0,721529 |
| K≥2,m≥2 đồng thời | 41 | +0,409698 |

K=1/2 và UNKNOWN rỗng; m=2/3 lần lượt N=1/2, chỉ1/2 mã nên D=null.
Prior-off canonical của A có24 point, bốn nhánh ICL có10 point/nhánh;
Full prior-off so Original D=0 đúng reuse durable. Không coi reuse là lời gọi
LLM độc lập hoặc dùng nhóm support41 để thay G60.

Full so Original có2 CASH→LONG,3 LONG→CASH,15 LONG→LONG và40 CASH→CASH.
Giữ cả năm action change, gồm ba ca thuận và hai ca bất lợi sau phí:

| Point | Original→Full | Δcycle (%) — chỉ mô tả | D khi hoàn nguyên action này (đpt) |
| --- | --- | ---: | ---: |
| MWG-2023-04-04 | LONG→CASH | +2,693586 | −0,816064 |
| MWG-2023-06-30 | LONG→CASH | +0,926101 | −0,296822 |
| VNM-2023-06-30 | CASH→LONG | −2,513213 | +0,615722 |
| VCB-2023-08-29 | CASH→LONG | +1,097742 | −0,295035 |
| VCB-2023-10-30 | LONG→CASH | −2,886117 | +0,693643 |

Leave-one-change-out chỉ hoàn nguyên Full về Original tại một action,
giữ toàn bộ G=60 và dựng lại tài khoản; không bỏ point. Leave-one-symbol-out
bỏ lần lượt FPT/MWG/VCB/VNM cho D=−0,033009/−1,441067/+0,554086/+0,820963 đpt.
JSON giữ sensitivity cho mọi contrast, không chỉ các ca thuận.

### Repeat, approximation và latency

Trên đúng12 point đã khóa, mọi lượt0/1/2/3 có D Full−Original/A/Plain/
No_target/Stats=0; Full−Numeric/Teacher=−0,442294 đpt ở cả bốn lượt.
Tám nhánh có0/72 bất đồng action giữa các cặp lượt; Original_duplicate
độc lập có0/36 bất đồng với Original cùng lượt. Đây là mẫu nhỏ với cặp
phụ thuộc và có shared-off; không vote, tăng N primary hoặc suy ra provider
luôn deterministic. Tài khoản sample12 không thay hay so trực tiếp với G60.

Trên50/60 point có feature: KL teacher||student mean **0,001229988453 nats**,
mean |Δp| **0,015684595799**, P95 |Δp| **0,053150920015**; giữ từng p full precision.
Có1 bất đồng action/50 cặp p hợp lệ (1/60 trên G): MWG-2023-06-30,
p_student=0,537359728940 so p_teacher=0,498016132686. Numeric LONG tại đây
mất0,926101% tài khoản MWG; Teacher giữ CASH. KL nhỏ không chứng minh nhãn
teacher đúng với thị trường hoặc lợi ích P&L. Thiếu feature giữ reason;
không clip p để giấu KL vô hạn, hit rate của nhánh không LONG trả null/NO_LONG.

Telemetry tách primary/repeat theo UUID/phase và giữ missing khác zero.
Primary có316 HTTP, repeat203 (519 tổng, gồm cả retry/lỗi); primary P95 HTTP
Original/A/Plain/Full/No_target/Stats lần lượt2,455670/2,272820/4,362338/
2,376105/2,861788/4,088031 giây. JSON giữ latency, pacing, token và invocation
elapsed riêng; không cộng timer lồng nhau hoặc coi HTTP là end-to-end.
Latency offline Numeric/Teacher **NOT_MEASURED**, không gán0 vì p được tái dùng.

Lệnh tái kiểm report/hình offline:

```powershell
py -3.13 -X utf8 scripts/report_mt_bicl_development.py --verify-only
```

Kiểm theo AGENTS.md1.2: **57 ca riêng biệt PASS** (18 report mới,14 audit,
23 account engine,2 report leakage). Lượt đầu56/57 PASS; fixture Full/Original
vô tình giống action đã sửa, chạy lại toàn18 ca report PASS. Ba Python mới
biên dịch PASS. Không đổi đường market/PIT/retrieval hoặc source đã khóa,
không chạy lại toàn suite/compileall/E2E; viện dẫn gate W11-03 trên đúng hash.
Diff/liên kết/số liệu và JSON/PNG replay PASS. W11-05 còn TODO;
`nomination=NOT_EVALUATED`, confirmation=false; chưa phát hành2025.
