# Tuần 11 — Kiểm định giá trị tăng thêm của MT-BICL

**Cập nhật 30/10/2026: 9/15 task DONE (01–09).**
**W11-05 đã khóa v2 NOT_NOMINATED; confirmation v2 NOT_RUN** tại mục14.
Report mô tả giữ `NOT_EVALUATED` nguyên byte; quyết định máy ở receipt riêng.
**W11-07 SPEC_LOCK_PASS** tại mục15; ngân sách v3 mới18 giờ đã khóa.
**W11-08 DONE** tại mục16: đã triển khai bucket/context/utility/facts/policy v3,
kiểm thử offline PASS. **W11-09 OFFLINE_VALIDATION_PASS / REPLAY_MATCH** tại
mục17; tiếp theo W11-10 freeze/preflight, chưa cấp release/API v3.
[Kế hoạch tổng](../plan.md) · [W10](../week10/README.md) · [W12](../week12/README.md)

**Lệnh tái lập/tiếp tục của run v2 đã hoàn tất; không dùng để mở v3:**

```powershell
py -3.13 -X utf8 scripts/continue_mt_bicl_development.py
```

Lịch quản lý và khung phân bổ công việc tại [W10-01](../week10/README.md#w10-01--inventory-và-khả-năng-thực-thi-27102026):
W11 dự kiến **02–05/11/2026**, khung **4–8 giờ**. Người dùng xác nhận ngày
**29/10/2026: ngân sách thời gian chạy được reset**. Đợt v3 tính mới từ 0,
không khấu trừ giờ chạy v1/v2; chi tiết cập nhật tại mục13.4. Khung giờ công
việc và lịch 12 tuần giữ nguyên, không coi khung này là thời gian API đã đo.
Chỉ thực hiện khi đủ gate
phụ thuộc; release và bắt đầu xác nhận chậm nhất 05/11, nếu không ghi NOT_RUN.

Phạm vi lịch sử dưới đây: một candidate Full_MT_BICL của **revision v2: teacher Beta-Bernoulli phân
cấp + learner distillation**, được chọn bằng quy tắc mới trước development.
V1 vẫn NO_MT_BICL_RELEASE; không sửa cờ cũ, không tái chọn checkpoint v1.
[Amendment W10](../week10/README.md#9-khắc-phục-nguyên-nhân-và-protocol-v2--28102026)
là thiết kế của run v2 đã hoàn tất. protocol_v1.json chỉ mô tả thí nghiệm đã đóng;
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

Mục1–4 và các receipt mục6–12 giữ **protocol/kết quả v2**. Checklist mục5,
amendment mục13 và protocol khóa mục15 là thứ tự làm tiếp. Không sửa JSON đã khóa hoặc dùng
release v2 cho v3; không thay candidate bằng No_target sau khi thấy kết quả.

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
family năm contrast của v2 và không được promote sau outcome. Family v3
được đề xuất riêng tại mục13 và W12, chưa khóa thành protocol.
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
Theo kế hoạch v2, Full trượt thì hai task xác nhận cũ NOT_RUN. Một vòng development;
sửa hành vi sau outcome phải ghi revision/exploratory. Yêu cầu29/10 cho phép
lập vòng nghiên cứu v3 ở mục13; không đổi kết quả hoặc mở lại run v2.

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
| W11-05 | Khóa nomination v2 bằng consumer đúng source/report; kết luận theo rule cũ, confirmation v2 không chạy | 04 | [x] DONE —receipt NOT_NOMINATED, confirmation v2 NOT_RUN; source/report/rule/Git replay PASS |
| W11-06 | Audit quyết định/utility/target projection/facts và giới hạn repeat | 04 | [x] DONE — mục13; không đổi run hoặc promote ablation |
| W11-07 | Khóa protocol v3, ngân sách chạy mới sau reset, hypothesis/ma trận/cohort/stop trước implement/run | 05–06 | [x] DONE —SPEC_LOCK_PASS,18 giờ/64.800 giây từ0, schema/fixtures/order/repeat và Git/source replay PASS |
| W11-08 | Feature bucket PIT, context đầy đủ và utility posterior; fact packet/anchor/revision policy | 07 | [x] DONE —172 test theo phạm vi PASS, scalar MC/PIT/ablation/guard/counter; chưa validation thị trường/API |
| W11-09 | Offline validation 2021/2022, oracle utility/semantic/leakage/ablation/probe và kiểm support | 08 | [x] DONE —676 point/replay PASS, approximation đạt, Full support40/60 và12 interval âm;75 test/22 semantic groups PASS |
| W11-10 | Freeze v3 source/schema/model/manifest/repeat; dry-run, API preflight và release development riêng | 09 đạt | [ ] TODO — có điều kiện |
| W11-11 | Người dùng chạy một development v3 đầy đủ, checkpoint/ledger riêng | 10 | [ ] TODO — có điều kiện |
| W11-12 | Cold verify, rebuild account, decomposition và nomination v3 theo rule mới đã khóa | 11 | [ ] TODO — có điều kiện |
| W11-13 | Audit exposure/MDE, manifest xác nhận2025 và release v3 nếu nominate | 12 đạt | [ ] TODO — có điều kiện |
| W11-14 | Người dùng bắt đầu xác nhận trước hết05/11, giữ checkpoint | 13 | [ ] TODO — có điều kiện |
| W11-15 | Bàn giao COMPLETE/INCOMPLETE/NOT_RUN và claim cho W12 | 05–14 chốt trạng thái | [ ] TODO |

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
Diff/liên kết/số liệu và JSON/PNG replay PASS. Tại mốc W11-04, W11-05 còn TODO;
report giữ `nomination=NOT_EVALUATED`, confirmation=false. Receipt đóng v2 tại mục14.


## 13. W11-06 — Audit kinh tế và kế hoạch utility-aware Bayesian ICL (29/10/2026)

### 13.1. Kết luận theo bằng chứng

**V2 chưa chứng minh cải thiện hệ thống trên development này.** D âm và
1/4 mã tăng khiến không đạt hai điều kiện nomination; D so A và hai guard
MDD vẫn đạt. Report mô tả giữ `nomination=NOT_EVALUATED`; task05 đã tạo quyết
định máy riêng tại mục14, không sửa trường đó trong report. Không dùng chênh lệch nhỏ
này để kết luận mọi Bayesian ICL đều vô ích hoặc hai hệ thống tương đương.
Đây không chỉ là vấn đề gate quá chặt: ngay điều kiện return cao hơn hệ
thống gốc cũng chưa đạt. Nới tiêu chí accuracy hoặc số mã tăng không làm
D âm thành lợi ích kinh tế; cần sửa cách dùng thông tin trước vòng mới.

Accuracy39/60 so38/60 đếm đúng/sai bằng nhau; P&L chịu độ lớn gain/loss,
phí và lãi kép. Ba sửa đúng (hai lỗ MWG được tránh, một LONG VCB có lãi)
và hai sửa sai (LONG VNM lỗ, bỏ LONG VCB thắng) cho +1 nhãn đúng nhưng
D<0. Năm ca và leave-one-change-out đã giữ ở mục12; không cộng Δcycle
thành return tài khoản. Không lấy nhóm support41 hoặc riêng MWG thay G60.

Audit bổ sung từ request/decision/context nguyên byte:

| Phát hiện | Số liệu / ví dụ | Hàm ý có thể bảo vệ |
| --- | --- | --- |
| Posterior gần đúng đã tốt hơn giai đoạn W10-07 | KL teacher→student0,001230 trên50 point có feature | Không ưu tiên train lại student hoặc tăng seed chỉ để giảm KL |
| Teacher chủ yếu mô tả tần suất nền | p trong[0,231643;0,498016], mean0,387971 so tỷ lệ thắng0,38; corr(p,r_net)=0,023133 | Trung bình gần base rate không chứng minh calibration từng point hoặc khả năng chọn giao dịch |
| Không phân biệt tập đã được Original chọn | Trên50 point: Original LONG12 có mean p0,386608, hit50%, mean r+1,016719%; CASH38 có mean p0,388401, hit34,21%, mean r−0,634117% | Prior hiện tại chưa điều kiện đủ theo tín hiệu quyết định; đây là mô tả mẫu nhỏ, không test nhân quả |
| Target bị mất bối cảnh khi projection | VNM30/06: target3 thắng/8, nhưng chỉ hiện hai mẫu cuối đều y=1; p_student0,352111 | Hai ví dụ hiển thị dễ tạo ấn tượng khác toàn task; cần summary đầy đủ, không suy chắc chắn đây là nguyên nhân duy nhất |
| Có lỗi đọc dữ kiện trong lời giải thích | VCB30/10: MACD−0,6521 > Signal−0,7620, Full lại viết MACD dưới Signal và chuyển LONG→CASH | Đây là mâu thuẫn có thể kiểm trực tiếp; không chứng minh sửa lời giải thích sẽ luôn sửa action |
| Lỗi dữ kiện không chỉ ở Full | VCB29/08: Original nói MACD dưới Signal, trong khi−2,7649 >−3,0568 | Cần đối chứng sửa facts riêng, tránh quy lợi ích sửa prompt cho Bayes |
| Target có cả ích và hại | Full−No_target: bốn action khác, hai có lợi/hai bất lợi; D−0,684455 | Không loại mọi target hoặc đặt rule m≤3 OFF theo kết quả đã xem |
| Repeat chưa đo nhiễu ở các điểm làm đổi kết luận | Sample12 cũ có D=0 ở mọi lượt; không chứa năm action Full−Original thay đổi | Không dùng 0 bất đồng trên sample12 để khẳng định năm ca chính đều ổn định |

So Full với Plain: Full giữ LONG lỗ VCB30/03 (−1,553612%) nhưng mở LONG
thắng VCB29/08 (+1,097742%); accuracy bằng nhau, D Full−Plain=−0,118278.
So Full với No_target, lợi ích ở MWG28/04 và VCB29/08 không bù thiệt hại
VNM30/06 và bỏ LONG VCB30/10. Đây là ca chẩn đoán, không danh sách mã/ngày
được phép tạo ngoại lệ. W9 A vẫn là bằng chứng độc lập trong phạm vi cũ;
A_reference trên development này không đồng nhất return W9 holdout.

### 13.2. Phương án chọn: điều kiện hóa context và sửa quyết định theo utility

Giữ teacher/student đã khóa, không train model lớn hoặc quay lại NIG return.
V3 nghiên cứu **Bayesian ICL theo utility, có quyết định nền để đối chiếu**:
upstream một lần → dữ kiện định lượng xác minh → Fact_Anchor a0 → context
PIT cùng trạng thái tín hiệu → p/examples/utility → đề xuất sửa action.
Kết quả cuối chỉ đổi a0 khi qua rule được khóa trước; raw/final action tách rõ.

Phần áp dụng [paper MT-BICL](https://proceedings.mlr.press/v306/zhu26aj.html)
vẫn là learner học ánh xạ prior tasks + target observations thành predictive
posterior, thích ứng bằng context và không gradient tại test-time. Utility,
kiểm facts và policy sửa action là phần mở rộng ứng dụng; không tuyên bố
hosted Decision LLM tự học Bayes chỉ vì nhận prefix hoặc paper bảo đảm P&L.

Cơ sở lý luận: chất lượng quyết định cần xét hàm mất mát/utility, không chỉ
độ chính xác posterior; xem [Lacoste-Julien và cộng sự](https://proceedings.mlr.press/v15/lacoste_julien11a.html).
Thiết kế v3 dưới đây là thích ứng của khóa luận, chưa được các nguồn đó kiểm
trên hệ thống này và chưa có bằng chứng P&L tăng. Đóng góp phải được tách
khỏi việc sửa facts hoặc thêm bộ lọc numeric thuần.

**A. Context điều kiện theo tín hiệu, giữ cả task và target.**

- Bổ sung hai dấu PIT: MACD−Signal và Close−SMA20, tạo tối đa bốn bucket;
  exact-zero/missing là UNKNOWN. Dùng implementation indicator đã đối soát,
  không gán indicator từ lời giải thích LLM hoặc tính bằng giá sau cutoff.
- Historical cycles phải cùng bucket query mới được xếp vào context v3;
  rank theo regime/feature distance/độ mới như thứ tự đã khóa. Task vẫn là
  mã×block63; K≤3, mỗi prior2..8, target≤8 cùng block và cùng bucket.
  Không chọn theo y/r_net, không dùng action Original làm nhãn lịch sử.
- Rerender và recompute teacher/student cho membership mới; không tái dùng p
  từ context v2. π/weights/scaler/HMM giữ nguyên. Đây là thay retrieval,
  không tuyên bố student được huấn luyện thêm trên tín hiệu agent.
- Thiếu support giữ reason và a0; không mở rộng bucket theo outcome hoặc bịa
  historical agent reports. Audit mọi mã/regime/cold-start trên đủ G60.

**B. Prompt phải thể hiện toàn context, không chỉ vài ví dụ gần nhất.**

Mỗi P/T ghi tổng n, số thắng/thua và mean r_net của toàn membership; ví dụ
hiển thị tối đa một/prior và một/target, chọn theo feature distance rồi thời
điểm/ID, không theo label. Ghi rõ projection, tuổi/range và target m nhỏ.
Giữ p_student và định nghĩa y sau phí; có r_net ở exemplar thay vì chỉ bit0/1.
Toàn BRPP≤600, prompt<6.500; giữ distill/cap. Nếu không fit budget thì sửa
renderer trước release, không cắt phần bất lợi hoặc legend trong run.

**C. Utility từ payoff lịch sử đã đóng, không thay hàm P&L.**

Với G=độ lớn gain khi r_net>0, L=độ lớn loss khi r_net≤0:

    U_LONG = E[θ G − (1−θ)L | context], U_CASH = 0
    ΔU(a,a0) = (1[a=LONG] − 1[a0=LONG]) × U_LONG

Ví dụ minh họa độc lập: θ=0,4, gain4%, loss2% cho U=+0,4% dù θ<0,5.
Không dùng tỷ lệ gain/loss quan sát của G60 để khóa threshold. r_net đã trừ
phí/slippage hai chiều bằng engine; không trừ chi phí lần hai, không dùng
TP/SL do LLM viết làm payoff và không cộng U thành return tài khoản.

Đề xuất khóa ở W11-07: posterior θ của teacher Beta-Bernoulli hiện hữu,
condition trên membership mới; magnitude G/L từ các observation PIT duy
nhất trong D/C. [Bayesian bootstrap](https://people.eecs.berkeley.edu/~jordan/sail/readings/rubin.pdf)
dùng Dirichlet(1,…,1) riêng mỗi dấu; 4.096 draw với seed từ SHA-256 của
protocol+query ID, nhánh/repeat dùng common random numbers. Không dùng θ
latent của simulator hoặc nhãn query; một cycle chỉ xuất hiện một lần trong
mỗi thành phần likelihood. Cụ thể, lấy λ từ `lambda_posterior` của teacher,
rồi θ_target từ Beta(α_λ+s_target, β_λ+f_target); prior tasks chỉ cập nhật
mass λ, không cộng count prior vào target. Oracle phải đối chiếu mean θ
giải tích với `predict_counts(..., posterior=True)`. Mô hình giả định
magnitude chung trong context được chọn; sign likelihood và magnitude
likelihood tách riêng. Giữ zero return trong nhóm loss với magnitude 0.

Giữ ít nhất5 gain và5 loss observations, ít nhất hai prior tasks; thiếu thì
UTILITY_UNSUPPORTED và không sửa a0. Trả mean U, quantile10/90%, n+/n− và
reason. Đây là khoảng posterior **phụ thuộc giả định/support**, không là
CI dự báo có coverage đã bảo đảm; bootstrap không biết tail chưa quan sát,
serial dependence và selection có thể làm khoảng quá hẹp. Kiểm độ nhạy
bỏ từng task, giữ kết quả bất lợi; không chọn policy bằng sensitivity.

Utility này do teacher + magnitude posterior tính; student chỉ cung cấp
p điểm đã học. Không gọi U là output đã distill hoặc dùng KL nhỏ chứng minh
U đúng. Teacher/student gap trên membership mới phải được kiểm lại trước
release; nếu nguồn/contract đổi thì test phần liên quan, không đổi weights
để sửa riêng các case2023.

**D. Giữ quyết định nền khi bằng chứng sửa chưa đủ.**

- Fact_Anchor nhận cùng upstream với các nhánh, thêm numeric fact packet
  đáng tin: giá trị/quan hệ MACD−Signal, cảnh báo đối chiếu trend/pattern,
  alpha summary và horizon. Gắn fact ID, không thay thế bằng suy diễn LLM.
- Các revision nhận cùng a0 và fact packet; LLM trả đề xuất action cùng
  fact IDs/assertion enum, context reason và justification ngắn. Validator
  kiểm enum/citation với packet, không giả định đọc được mọi mâu thuẫn trong
  văn xuôi. Tách below-zero khỏi below-signal. Ghi đầy đủ phần chưa kiểm được.
- Proposed action=a0: giữ. Đổi action chỉ khi facts hợp lệ, support đủ và
  **Q10(ΔU)>0**. Không đạt: giữ a0 với reason, không đổi thành CASH mặc định.
  API/integrity/PIT lỗi vẫn dừng/resume, không biến thành policy abstention.
- Không có context hợp lệ: bypass revision, dùng a0 và ghi source binding;
  đây là policy bypass, không khai là cache hit/canonical request giống nhau.
  Nếu Fact_Anchor có assertion sai, dùng Original với reason riêng ở mọi
  nhánh anchored; nếu mất response hoặc lỗi integrity thì dừng.
- Gate/threshold này là đề xuất trước v3, chưa được tối ưu trên năm ca đã
  xem. Không đặt blacklist VCB/VNM, không sao chép No_target, không nới
  Q10 để ép đủ số action thay đổi. Đây là thay decision policy trong
  experiment mới; hợp đồng thực thi và vốn/account giữ nguyên.

### 13.3. Ma trận mới để không nhận nhầm công lao của Bayes

Đề xuất tại mốc audit v3, đã được khóa thành protocol ở mục15 trước implement/run.
Tám nhánh LLM tối đa:

| ID v3 | Nội dung | Đóng góp cần tách |
| --- | --- | --- |
| Original | Prompt/model/options đối chứng legacy cùng run mới | Hiệu quả toàn hệ thống |
| A_reference | Phương pháp W9, cùng upstream mới | Không bỏ đối chứng có bằng chứng cũ |
| Fact_Anchor | Dữ kiện kiểm được, không Bayes/examples | Lợi ích sửa lỗi dữ kiện |
| Plain_revision | a0 + cùng examples/summary, không p/U | Lợi ích ICL thường |
| Full_utility_ICL | a0 + p + examples + U + rule sửa action | Candidate duy nhất |
| No_utility | Như Full nhưng bỏ U và numeric veto; giữ facts/support | Lợi ích utility/rule sửa |
| No_target | Bỏ C/target summary, recompute toàn p/U, cùng rule | Đóng góp target |
| Stats_only | p/U/summary nhưng bỏ exemplars, cùng rule | Đóng góp demonstrations |

Mọi revision dùng cùng nguồn/retrieval/projection và cùng quy tắc eligibility;
No_target thay đúng C theo ablation, không reuse U Full. Bỏ C có thể làm
nhánh này thiếu support; báo riêng, không ép tập đủ support giống Full.
Plain_revision và No_utility dùng cùng support mask với Full nhưng không
nhận U hoặc numeric veto; vì vậy eligibility không thành nhiễu giữa các nhánh.
Utility_only offline
chọn LONG khi Q10(U)>0, còn lại CASH có reason, cùng G; giữ Numeric_only v2
là diagnostic nếu cần, không promote làm candidate. Full−Plain bao gồm
posterior/utility/policy, không đủ để kết luận riêng mạng distillation tạo gain.

Original/A/Fact_Anchor chạy trước; năm revision xoay j mod5, cùng deep-copy
upstream một lần. Không rerun vision để kiếm baseline khác. Request/schema
khác v2 phải namespace mới, không dùng cache v2 như response request mới.
Đối chiếu reuse upstream bằng nguồn/PIT/hash; mọi khác biệt prompt/phương pháp
Original-v3 so Original-v2 phải được công bố nếu phát sinh.

G60 giữ nguyên. Primary tối đa8×60=480 slot. Repeat12 chọn trước outcome v3:
năm point action-change v2 ở mục12 +bảy point còn lại có SHA-256 nhỏ nhất
của chuỗi `v3-repeat|point_id`; dedupe/sort trước run. Đây là mẫu chẩn đoán
có chủ đích sau exposure v2, không mẫu ngẫu nhiên để ước lượng noise toàn G.
Ba lượt bổ sung 12×(8+Original_duplicate)=324 slot; tổng tối đa 804, bypass
không phát HTTP nhưng phải có slot/reason. Mỗi lượt repeat vẫn chạy
Original/A/Fact_Anchor trước, sáu nhánh còn lại (năm revision và duplicate)
xoay (3j+r−1) mod6. Original_duplicate phải gọi độc lập bằng UUID riêng,
không dùng chung response/cache với Original. Không vote hoặc chọn lượt đẹp.
Repeat confirmation chọn 12 bằng K/m/feature trước outcome 2025, không theo
gain; task 07 khóa quy tắc và task 13 khóa ID trước response xác nhận đầu.
Xác nhận có tối đa 8×128+324=1.348 slot; preflight/budget tính cả pacing,
retry và kiểm chứng, không coi nominal slot là số HTTP hoặc thời gian đã đo.

Nomination v3 giữ D Full−Original>0, ≥3/4 mã ΔR>0, D Full−A≥0, mean ΔMDD≤2
và max≤5 đpt; **thêm D Full−Fact_Anchor>0** để tránh thắng chỉ nhờ sửa facts.
Chỉ Full được xét; không lấy nhánh ablation thắng. Development2023 là
exploratory/adaptive; không dùng CI ở đây làm kết quả xác nhận chính.

Nếu nominate, vẫn cần exposure audit trước xác nhận128 point2025. Primary
Full−Original CI95%; family7 secondary Full−A/Fact_Anchor/Plain_revision/
No_utility/No_target/Stats_only/Utility_only dùng Bonferroni
CI(1−0,05/7)=**99,285714%** mỗi contrast; cùng paired block bootstrap W12.
Muốn claim Bayesian ICL tăng thêm, cần contrast với Fact_Anchor/Plain;
muốn claim demonstrations có ích, cần Full−Stats_only. Không gán mọi gain
Full−Original cho Bayes. Mục tiêu rõ rệt ≥1 đpt và guard phân tán/rủi ro giữ.

### 13.4. Thứ tự thực hiện và các điểm dừng

- **05 DONE:** v2 NOT_NOMINATED bằng consumer tại mục14; xác nhận v2 NOT_RUN.
- **07 DONE:** khóa tại mục15; chốt hypothesis, source/protocol v3, feature/calculation/schema,
  evidence audit, threshold/seed/order và ngân sách chạy mới đã được reset.
  Ghi mốc reset, hạn mức và cách đo riêng cho v3; không yêu cầu đối soát số
  dư chạy v1/v2 như điều kiện cấp ngân sách mới. Không fit
  hoặc grid-search threshold trên2023. 2021/2022 đã xem chỉ để diagnostic
  kỹ thuật/giới hạn; không được gọi lại là validation độc lập.
- **08 DONE:** code utility, facts và renderer/anchor ở namespace mới; reuse
  core engine/weights, không sửa freeze v2. Test deterministic math/JSON,
  task/query exclusion, future append, sign/unit/fee, projection counts,
  low-support/bypass và raw/final action. Caller chọn test đúng đường đổi.
- **09 DONE:** kiểm offline toàn bộ membership/utility, giữ output bất lợi;
  kiểm thêm semantic fixture nhiều giá trị/dấu, không chỉ hai lỗi đã thấy.
  Oracle đối chiếu posterior mixture/expected utility độc lập, sign/unit/fee,
  counts/projection đầy đủ, ablation recompute, query exclusion/future append;
  tất cả kiểm tra hợp đồng áp dụng phải PASS. Trên context mới báo KL/Δp
  và kiểm lại ngưỡng cơ chế đã khóa (không chọn weights mới); lỗi approximation
  không được âm thầm đổi sang teacher point estimate trong prompt.
  Báo độ phủ đủ support, tỷ lệ interval U qua 0 và các trường hợp có thể đổi
  action theo từng mã/regime. Q10 là lựa chọn thận trọng đề xuất trước run,
  không phải ngưỡng tối ưu đã có bằng chứng; không dùng tỷ lệ được phép đổi
  action để hạ threshold sau khi thấy lợi suất. Nếu mọi point đều bypass thì dừng
  NO_ACTIONABLE_CONTEXT, không gọi API chỉ để tái tạo baseline. Thiếu nguồn
  numeric hoặc không bảo đảm PIT thì BLOCKED, không fallback feature bịa.
- **10–12:** một freeze/run/verify/nomination mới; user chạy API. Không reset
  ledger, không tự hồi sinh candidate sau failed gate. Chưa có kết quả v3.
- **13–15:** xác nhận có điều kiện, bắt đầu chậm nhất05/11; bàn giao W12.
  Hết07/11 khóa dữ liệu,08–10/11 viết/bảo vệ; vẫn12 tuần, không W13.

Ưu tiên công việc: facts/context → utility/policy → matched experiment;
không train GPU, đổi LLM hoặc sweep prompt trong vòng này.

**Ngân sách chạy sau reset — xác nhận của người dùng ngày29/10/2026:**

- Đợt v3 bắt đầu bộ đếm thời gian chạy mới từ **0**; không trừ thời gian
  train/pilot/development/verify của v1/v2 vào đợt này. Bỏ điều kiện phải
  còn số dư chạy cũ mới được triển khai v3; quyền reset đã được xác nhận.
- W11-07 ghi nhận hạn mức của đợt mới theo kế hoạch và cách đo; W11-10
  đối chiếu preflight cho tối đa 804 slot development và 1.348 slot xác
  nhận có điều kiện, tính cả pacing/retry/verification. Đây là dự toán
  cần đo, không tự suy ra thời gian chạy không giới hạn hoặc quota mới.
- Người dùng sau đó xác nhận **18 giờ chạy tổng cho v3**; grant máy tại
  [budget_v3.json](budget_v3.json), cách đo/phạm vi tại mục15. Không tự coi
  khung giờ công việc là grant API; đây là xác nhận chạy riêng của người dùng.
- Theo dõi chi phí phát sinh của v3 riêng; resume, retry và chuyển sang
  W12 tiếp tục cùng bộ đếm v3, không cấp lại ngân sách sau mỗi lần dừng.
  Ledger usage/API và bằng chứng v1/v2 giữ nguyên để tái lập; các ghi chú
  “không reset ngân sách” trong receipt cũ chỉ áp dụng cho đợt cũ.
- Giữ khung công việc W11 4–8 giờ, W12 5–10 giờ và các mốc 05/11, 07/11,
  10/11. Chỉ kết luận thiếu thời gian sau khi xét ngân sách chạy mới và
  thời gian lịch còn lại; không dùng giờ chạy v1/v2 để suy ra NOT_RUN v3.
  Nếu vẫn không kịp thì bàn giao đúng trạng thái; không giảm G hoặc bỏ
  comparator để kịp lịch. Reset không đổi tiêu chí nomination hay exposure.

### 13.5. Kiểm tra audit và amendment lần này

Chỉ sửa Markdown, đọc account/raw requests/decisions/context và tính thống
kê mô tả; không code/train/API, không sửa nomination trong artifact. Hash
report v2 `ce4ac6b6c2f168ad8e88822236a38277ac46d812382414a691bcebfb8b89fb8d`,
account `fab7ebe0b2102a17487ed02d5c099a53671b696323a9d7ca377dec050544a348`,
requests `ccfbe16fac9a69317fb0911206e32794550036e45c10025c920c9abbc1019673`.
Toàn2.597 file v2 (loại metadata OS lock) có aggregate SHA-256
`38a13803e834591af5b85f6cfa1df4a8709ec31135dd5347084e74257be9e157`.
Đối soát byte trước/sau và ledger API: PASS. Kiểm 108 liên kết nội bộ/anchor,
checklist 5/15, số liệu audit và diff: PASS. Theo AGENTS.md1.2 không
chạy lại unit/leakage/E2E/compileall cho amendment tài liệu; không ghi là
đã chạy lại57 test W11-04. W11-06 DONE là audit, không nghiệm thu v3.

Cập nhật reset ngân sách cùng ngày chỉ sửa kế hoạch và dependency ngân sách;
không ghi đè counter/ledger/runtime, không tạo release hoặc tăng tiến độ.
Kiểm diff/liên kết và hash bằng chứng theo phạm vi tài liệu; không chạy lại
unit/leakage/E2E/compileall theo AGENTS.md1.2.

## 14. W11-05 — Khóa nomination v2 (29/10/2026)

**PASS — W11-05 DONE; 6/15 task hoàn tất.** [Receipt máy](development_nomination_v2.json)
khóa **NOT_NOMINATED**, chỉ xét Full_MT_BICL theo rule v2 trước run.
`confirmation_v2.status=NOT_RUN`, `allowed=false`; không đề cử No_target,
ablation hoặc Teacher thay Full. Receipt này chỉ đóng v2, không cấp protocol,
ngân sách hoặc release v3; W11-07 tiếp tục theo amendment/reset đã xác nhận.

Consumer `core/mt_bicl_v2_nomination.py`, CLI
`scripts/nominate_mt_bicl_development.py`, source neo commit `40508d7`.
SHA-256 byte receipt:
`b2747759b0d368ebc045f3d0c7ffff0ddb9761959506271976cadf2fe1581d78`.
Đối soát report đúng SHA/version/source/runtime/Git và tái dựng report từ
account/manifest/ledger PASS; tính lại từ bốn tài khoản, kiểm contrast/D
khớp report. Rule lấy đúng `protocol_v2.json:development.nomination`,
không áp tiêu chí mới của v3 hoặc dùng accuracy/repeat thay lợi ích kinh tế.

| Điều kiện v2 | Giá trị thực | Rule | Kết quả |
| --- | ---: | --- | --- |
| G đầy đủ đã verify | 60 | Đủ60 và đúng mọi nhánh/mã | PASS |
| D Full−Original (đpt) | −0,024756891114 | >0 | FAIL |
| Số mã ΔR>0 | 1/4 | ≥3/4 | FAIL |
| D Full−A_reference (đpt) | +0,576595826683 | ≥0 | PASS |
| Mean ΔMDD (đpt) | −0,053380287250 | ≤2 | PASS |
| Max ΔMDD (đpt) | +2,480064667200 | ≤5 | PASS |

Hai reason máy là `D_Full_Original_gt_0` và `positive_symbols_at_least_3`.
Đây là không đạt rule đề cử trên development đã exposed, không là kết luận
mọi Bayesian ICL kém hoặc chênh lệch có ý nghĩa thống kê.

Report/account/requests và mọi JSON v2 cũ giữ nguyên byte, kể cả trường
`NOT_EVALUATED`. Receipt mới nằm ngoài namespace evidence v2. Kiểm trước/sau
đủ2.597 file v2, loại metadata OS lock, PASS; ledger4.498 request không đổi.
Receipt ghi rõ thuật toán hash cây: canonical JSON map đường dẫn tương đối
namespace→SHA byte, digest
`abee3ec568a76d58335c064c9253391e7dfcd70a55c3efe605c1f8c3ffc2f6a3`;
đây là binding có phương pháp riêng, không thay dấu aggregate lịch sử mục13.5.
Không đọc key/API, gọi lại model, sửa forecast/economics/PIT hoặc reset counter cũ.

```powershell
py -3.13 -X utf8 scripts/nominate_mt_bicl_development.py --verify-only
```

Kiểm theo AGENTS.md1.2: **34 test PASS** (16 nomination mới,18 hồi quy report),
ba Python mới biên dịch PASS. Phủ biên strict/inclusive, zero/NaN/bool/MDD,
G60/missing/repeat/nhánh, chống đổi rule/promote ablation, report/source sai,
receipt immutable và neo byte Git. Không đổi market/PIT/retrieval/engine nên
không chạy lại leakage/full suite/compileall/E2E; viện dẫn gate cũ trên đúng hash.
Tái dựng nomination và kiểm receipt `--verify-only` sau neo Git: **PASS**,
khớp toàn payload và byte Git HEAD. Diff, liên kết, checklist và số liệu PASS.

## 15. W11-07 — Khóa protocol utility-aware Bayesian ICL v3 (nghiệm thu 30/10/2026)

**PASS — W11-07 DONE; 7/15 task hoàn tất.** Đặc tả/grant được khóa29/10,
tái kiểm và hoàn tất nghiệm thu30/10. [Protocol v3](protocol_v3.json),
[schema wire/sidecar](utility_icl_v3.schema.json),
[fixtures đặc tả](protocol_fixtures_v3.json) và [grant18 giờ](budget_v3.json)
được neo source commit `4f88ce0`; [receipt khóa](protocol_lock_v3.json)
có `SPEC_LOCK_PASS`, next task08, tất cả cờ train/refit/API/release=false.

- SHA byte protocol: `1912d18145fcc0eb46563206a83cfbacf5420d48fd828d0f79abfb56fa0b7b48`.
- SHA byte receipt: `7b1c3e2cd1e976b483f19391fa47f1cb675bae65f9d629929c8d2ccc7a1ca2ec`.

Các lựa chọn ở mục13 đã thành thông số trước outcome v3. Giữ candidate
seed42/step3000, π/scaler/HMM/runtime và hợp đồng engine v2. Hai dấu dùng
`talib.MACD(12,26,9)` và Close−SMA20 trên đúng prefix45 nến PIT, float64
trước làm tròn; kiểm tương đương helper cũ ở round4/last28 trong bước09.
Zero/missing tạo UNKNOWN, không mở rộng bucket hoặc dùng lời giải thích LLM.
Membership phải cùng bucket, exit<query, rank không dùng y, K≤3 và m≤8;
thay membership phải recompute p/U, không lấy p của v2 cho context mới.

Utility dùng4.096 draw từ posterior teacher và magnitude Bayesian bootstrap,
K≥2, n_gain≥5, n_loss≥5; zero net thuộc loss với magnitude0. Student chỉ cung
cấp p điểm. Tách mean U giải tích, mean Monte Carlo và Q10/Q90; không gọi U
là output đã distill hoặc khoảng có coverage thị trường bảo đảm. Khóa seed
uint128 từ SHA-256 protocol/query/component, lưu seed dạng chuỗi JSON;
λ/θ dùng inverse CDF và mỗi observation có stream magnitude riêng, nên
No_target dùng cùng random numbers trên subset rồi renormalize, không reuse U.
Schema unsupported ghi0 draw/null thay vì giả đã sampling.

Đổi action chỉ khi facts/support hợp lệ và Q10(ΔU)>0: CASH→LONG dùng Q10(U),
LONG→CASH dùng −Q90(U); đúng0 không đổi. Không đủ bằng chứng giữ a0 kèm
reason, không mặc định CASH. Plain_revision/No_utility cùng Full support mask,
không nhận U/veto; Stats giữ p/U/summary, bỏ exemplar; No_target bỏ C và tính
lại p/U/support riêng. Facts enum/citation được đối soát, không tuyên bố đã
kiểm được mọi mâu thuẫn văn xuôi. Lỗi API/PIT/integrity vẫn dừng/resume.

G60 và bốn mã giữ nguyên, primary480 +repeat324=**804 slot tối đa**.
Original/A/Fact_Anchor trước, năm revision xoay j mod5; repeat thêm duplicate
độc lập, sáu nhánh xoay (3j+r−1) mod6, j là index toàn cohort. Mẫu12 gồm5
action-change v2 và7 SHA nhỏ nhất của `v3-repeat|point_id`, sort theo cohort:

```text
MWG-2023-04-04  FPT-2023-04-12  MWG-2023-04-28  VNM-2023-04-28
MWG-2023-06-30  VCB-2023-06-30  VNM-2023-06-30  VCB-2023-08-29
VNM-2023-09-29  VCB-2023-10-30  VNM-2023-10-30  VCB-2023-12-22
```

Đây là mẫu chẩn đoán có chủ đích sau exposure v2. Không vote/tăng N primary,
không dùng cache response v2 cho request v3. Xác nhận vẫn có điều kiện ở
128 point, tối đa **1.348 slot**, IDs chỉ khóa ở task13 sau exposure audit;
family7 Bonferroni CI99,285714%, primary CI95%, cùng bootstrap L4/10.000/
seed20261027. Nomination thêm Full>Fact_Anchor, giữ các guard kinh tế cũ.

**Ngân sách mới64.800 giây từ0** dùng chung validation/preflight/development/
xác nhận nếu release/verification; tính runtime CPU/GPU, source checks trong
run, pacing/retry/quota wait và checkpoint. Human authoring, compile/unit
fixture và spec-only metadata lint không là runtime thực nghiệm. Chưa chạy
thực nghiệm v3 nên counter chưa materialize, số tính phí hiện0; bước08 phải
tạo đúng một counter trước lệnh thực nghiệm đầu. Clean pause loại downtime;
crash chưa đóng tính gap bảo thủ, không reset khi resume hoặc chuyển W12.
Giữ mốc05/11 và07/11; grant không cấp quota API. Bước10 phải đo khả thi theo
remaining cap/calendar, không coi2.152 slot danh nghĩa là HTTP bound hoặc
hứa18 giờ đủ. Không dùng giờ v1/v2 để trừ grant này.

Đã khóa source/schema/fixture/parent receipt, hash π/weights/runtime và đủ
2.597 file v2 nguyên byte. Ledger4498 request nền được bind theo hash prefix:
sau release mới chỉ append, không sửa row/reserve hoặc reset usage. Namespace
`outputs/bayesian_benchmark/mt_bicl_v3/` tách riêng; chưa tạo ở bước07.
Nếu không có Full-supported interval nào Q10(U)>0 hoặc Q90(U)<0 thì bước09
dừng NO_ACTIONABLE_CONTEXT trước API; không hạ threshold hoặc ép action.
Gate approximation trên context mới giữ mean KL≤0,02/P95 |Δp|≤0,1,
không fallback teacher point estimate nếu student trượt.

```powershell
py -3.13 -X utf8 scripts/verify_mt_bicl_protocol_v3.py
```

**31 test PASS** (15 đặc tả/schema/ledger mới,16 hồi quy nomination v2),
ba Python mới biên dịch PASS. Khóa/tái kiểm CLI thực tế và byte Git PASS;
fixtures gồm dấu/unit/seed/order/support/JSON/citation, không phải nghiệm thu
implementation utility hoặc bằng chứng P&L. Không thay đường dữ liệu/PIT
trong bước này nên không rerun leakage/full suite/compileall/E2E; đối soát
gate cũ theo hash/runtime. Không đọc key, forward model, train, mở payoff2025
hoặc gọi API. Tiếp theo W11-08 triển khai đúng đặc tả đã khóa.

## 16. W11-08 — Triển khai bucket, utility và revision policy v3 (30/10/2026)

**PASS — W11-08 DONE; 8/15 task hoàn tất.** Source `282ea2d` thêm module v3,
không sửa code/schema/artifact v2 hoặc protocol/schema/grant đã khóa ở mục15.
Các cờ `SPEC_LOCK_PASS`, `utility_implementation_exists_at_lock=false` và
next task08 trong receipt07 mô tả thời điểm khóa, không phải trạng thái
implementation hiện tại hoặc release API. Checklist/tiến độ hiện tại ở đây.

| Module | Hành vi đã triển khai |
| --- | --- |
| [features](../../../core/mt_bicl_v3_features.py), [contracts](../../../core/mt_bicl_v3_contracts.py) | Facts float64 từ tail45 PIT, TA-Lib MACD12/26/9, SMA20; lọc cùng bucket trước TaskBuilder v2, giữ scaler/regime/rank cũ và centroid toàn tập đủ điều kiện; query không nhãn, proof/source/membership riêng |
| [utility](../../../core/mt_bicl_v3_utility.py), [context](../../../core/mt_bicl_v3_context.py) | Mixture λ theo từng task, θ target không pooled prior; bootstrap magnitude net4.096 draw/CRN; summary toàn membership và một exemplar/P/T; recompute No_target, masks/ablation đúng protocol |
| [policy](../../../core/mt_bicl_v3_policy.py), [decision](../../../core/mt_bicl_v3_decision.py) | Facts enum/citation, a0 có proof, raw/final riêng; Q10ΔU>0, zero giữ a0; bypass giữ đủ slot; Original/A giữ nguyên request legacy, schema/prompt anchored riêng; invocation qua retry wrapper cũ |
| [budget](../../../core/mt_bicl_v3_budget.py) | Một path/identity64.800 giây, khóa OS, checkpoint đơn điệu/UTC; resume/crash/clean pause/cap/deadline; mất counter không reset từ0 |

Bucket dùng hiệu MACD−Signal và Close−SMA20 trước rounding, zero/missing
UNKNOWN; phân biệt MACD âm nhưng vẫn trên Signal. Historical/query dùng
cùng hàm, chỉ hash OHLCV prefix nhìn thấy; appended future không đổi facts.
Membership lọc trước rank/cắt tám cycle, không chọn theo label, không fit
scaler mới bằng bucket. Sidecar giữ facts/raw/z/model-vector, centroid fit
IDs, scaler fit IDs/hash và toàn context; student vẫn dùng bốn chiều/
PAIRED_37. Lỗi nguồn/selected future, duplicate, overlap hoặc query label
raise, không chuyển thành lý do thiếu support.

Utility giữ zero return trong loss, magnitude0; dùng r_net đã tính bởi
engine, không trừ phí lần hai. Mean θ/U giải tích, mean MC, Q10/Q90 và MC SE
tách riêng. Lưu hash/full draw/seed/component và IDs phục vụ replay. Oracle
scalar dùng likelihood tích tuần tự độc lập, kiểm mean θ/U và từng draw
trong4.096 draw với tolerance1e−12; không dùng sai số mean MC làm gate ngẫu nhiên.
Đây vẫn là utility teacher+bootstrap dưới giả định sign/magnitude, không
phải U đã distill hoặc khoảng có coverage thị trường đã chứng minh.

No_target bỏ đúng C và tính lại p/U/support, giữ D/query; Stats giữ cùng
p/U/summary nhưng không chứa exemplar hoặc exemplar IDs. Plain_revision/
No_utility dùng mask Full, không nhận U/veto; Plain không nhận p. BRPP≤600,
fact card≤700, anchor card≤80 và prompt<6.500 được kiểm trước invocation.
Renderer anchored có hướng dẫn gọn riêng để năm report chạm cap vẫn qua
fixture; `_distill_report`/`_cap_report` và request Original/A giữ nguyên.
Overflow vẫn fail, không cắt counts/legend hoặc phần bất lợi trong run.

Fact_Anchor sai assertion dùng Original có source proof cho mọi revision;
thiếu support/bucket/feature giữ a0 có reason, không mặc định CASH. Reply
thiếu/lỗi API hoặc U/eligibility không nhất quán phải dừng, kể cả proposed=a0.
Validator chỉ chứng minh enum/citation/context reason, không mọi văn xuôi.
Utility_only dùng đúng Q10U>0; gate toàn context dừng NO_ACTIONABLE_CONTEXT
nếu không có interval Full-supported dương/âm nghiêm ngặt, trước API.

**172 test riêng biệt PASS:** 59 test `test_mt_bicl_v3_*.py` gồm44 mới và15
protocol đã có; 113 hồi quy đã loại test bị import trùng. Các module hồi quy:
`test_mt_bicl_tasks`, `test_mt_bicl_tasks_leakage`, `test_mt_bicl_v2_teacher`,
`test_mt_bicl_v2_teacher_leakage`, `test_mt_bicl_v2_adapter`,
`test_mt_bicl_v2_decision`, `test_backtest_token_budget`,
`test_paired_protocol`, `test_account_pnl`. Phạm vi phủ primitive được tái dùng,
P0 kinh tế/PIT/paired/token và hợp đồng mới; gồm30 test trong ba module
leakage. Khóa OS thật trong temp chặn phiên đồng thời, cho resume sau đóng;
fixture clock kiểm crash gap/cap/deadline/Ctrl+C và không reset khi đổi stage.
**12 file Python mới biên dịch PASS**; không chạy toàn suite/compileall/E2E
vì đường v3 tách riêng và đã chọn đúng caller/hợp đồng bị ảnh hưởng theo AGENTS1.2.

```powershell
py -3.13 -X utf8 -m unittest discover -s tests -p "test_mt_bicl_v3_*.py" -v
```

Đối soát spec/receipt/runtime/π/weights và cây2.597 evidence v2 nguyên byte
PASS bằng verifier07; aggregate vẫn `abee3ec568a76d58335c064c9253391e7dfcd70a55c3efe605c1f8c3ffc2f6a3`.
Ledger vẫn4.498 rows, SHA byte `6de7ea8d023a9530c99d1c334ae94f248ba3c8297b7418497503cb73481b56b5`.
Tests/compile là fixture kỹ thuật được grant loại khỏi runtime thực nghiệm;
chưa có namespace/counter v3 trong repository, thời gian thực nghiệm vẫn0.
W11-09 phải mở RuntimeBudget trước source checks/inference/validation đầu
tiên và dùng cùng counter ở mọi stage sau đó. Chưa forward weights thật,
fit model thực nghiệm, đọc payoff2025, gọi API hoặc có P&L v3.
Tiếp theo **W11-09**: kiểm nguồn thật, approximation/support/semantic và
diagnostic trên2021/2022 cùng context development mới; chưa được suy unit
PASS thành đạt gate thị trường hoặc release ở W11-10.

## 17. W11-09 — Validation offline utility v3 và cold replay (30/10/2026)

**PASS — W11-09 DONE; 9/15 task hoàn tất.** [Report](../../../outputs/bayesian_benchmark/mt_bicl_v3/offline_validation/report.json)
`OFFLINE_VALIDATION_PASS`, không failed gate; [cold proof](../../../outputs/bayesian_benchmark/mt_bicl_v3/offline_validation/replay.json)
`REPLAY_MATCH` đủ676 point và report. Source cuối `46bd268`,
[QA đang dùng](validation_checks_v3/46bd2683dbacd9e9d32fa3d91b140419983c935a.json)
neo75 test/22 semantic groups với đúng hash source. Không cấp quyền API.

- SHA byte report: `690db24e3c20d25dc446199899e4f6018a3142132db23546d2b1ad55c9d16334`.
- SHA byte cold proof: `507cc8497003106d92b3da99685df35a20a001bcd1ad56ce10bf81c6cef0fbcf`.

[Loader/cohort](../../../core/mt_bicl_v3_validation_inputs.py) dùng toàn bộ
lưới bank cũ có giá/quyền hợp lệ, không vắt block/split/năm, giữ cả query
thiếu feature; chỉ dùng metadata eligibility, không dùng giá trị nhãn query.
N=**310 diagnostic2021 +306 diagnostic2022 +60 development2023 =676**.
2021/2022 đã exposed, 2023 là adaptive development; đây không là validation
độc lập hoặc kiểm hiệu quả P&L. Bộ giá và VNINDEX được giới hạn đến2023;
không mở payoff2025. Weights seed42/step3000, π/scaler và tham số HMM cũ
giữ nguyên. HMM nạp lại JSON đúng proof/model hash cuối2020 hoặc historical
prefix tương ứng, không refit, không nạp model cuối2022 thay vào.

[Runner](../../../core/mt_bicl_v3_validation.py) kiểm độc lập toàn population
cùng bucket trước rank, centroid, target latest8, feature/scaler và
**9.877 lượt observation đã đóng** bằng helper net T+2.5; query label không
đi vào input. [Oracle](../../../core/mt_bicl_v3_oracle.py) dùng tích predictive
tuần tự và magnitude scalar/CRN độc lập, kiểm mean θ/U và **6.893.568 U draw**
thuộc Full/No_target/sensitivity có support. Sai số lớn nhất
**1,00697×10⁻¹³ <1×10⁻¹²**. MC mean/SE được báo riêng, không ép mean MC
khớp giải tích bằng một gate ngẫu nhiên. Context, prefix, seed/draw hash,
counts và sensitivity giữ full precision trong676 sidecar; cold replay
tái tính mọi point bằng weights frozen và so toàn payload/byte.

Gate approximation trên union Full/No_target: **1.108 context có feature**,
244 context unavailable vẫn giữ trong denominator báo cáo. Mean KL
**0,00040483868≤0,02**, P95 |Δp| **0,0286350419≤0,1**; không infinite KL,
không teacher point fallback. Phân nhóm năm/nhánh chỉ mô tả, không thêm gate
sau khi xem dữ liệu. Trên inputs2023 riêng có100 context available,
mean KL0,00045970893 và P95 |Δp|0,0243215741.

| Miền | Full đủ support | No_target đủ support | Full Q10U>0 | Full Q90U<0 | Full interval qua/chạm0 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Diagnostic2021, N310 | 190 | 174 | 8 | 40 | 142 |
| Diagnostic2022, N306 | 206 | 191 | 0 | 81 | 125 |
| Development2023, G60 | 40 | 37 | 0 | 12 | 28 |

Trong G60, Full support theo mã: **FPT3/12, MWG14/16, VCB13/16, VNM10/16**;
10 point thiếu query feature và10 thiếu magnitude support vẫn được giữ.
Plain_revision/No_utility/Stats giữ mask Full40; No_target tự recompute37.
Không phải NO_ACTIONABLE_CONTEXT vì có12 interval âm, phân bố FPT2/MWG5/
VCB3/VNM2. Chúng chỉ có thể cho phép LONG→CASH nếu a0/proposal/facts phù hợp;
không có bằng chứng utility cho CASH→LONG ở G60. Chưa có action LLM v3 thực
tế. Theo rule đã khóa, Utility_only trên G60 sẽ CASH; không đổi threshold
để tạo thêm LONG hoặc bỏ các điểm này khỏi report.

Sensitivity giữ đủ **1.659 context bỏ một prior task**,845 còn đủ support;
không bù task/rerank hoặc chọn policy bằng sensitivity. Chỉ **1/12** interval
âm G60 giữ âm ở mọi lượt bỏ task; các trường hợp khác qua0 hoặc unsupported.
Đây là giới hạn đáng kể của support/posterior, không bị che bằng kết quả
approximation nhỏ. Không suy interval là coverage thị trường đã bảo đảm.

```powershell
# QA fixture, không mở counter thực nghiệm
py -3.13 -X utf8 scripts/validate_mt_bicl_v3.py --contracts
# Một lệnh tự resume validation, dùng lại point durable
py -3.13 -X utf8 scripts/validate_mt_bicl_v3.py
# Tái dựng đầy đủ từ nguồn/weights frozen, dùng cùng counter
py -3.13 -X utf8 scripts/validate_mt_bicl_v3.py --verify-only
```

Kiểm theo phạm vi AGENTS1.2: **75 test PASS** (14 mới,59 v3 có sẵn và2 paired),
gồm17 test trong hai module leakage; **7 file Python mới biên dịch PASS**.
Không full suite/compileall/E2E vì code v3 tách riêng, các primitive P0 v2
nguyên byte và đã được kiểm đúng caller/hợp đồng. Socket bị chặn trong CLI;
không đọc key/client, gọi API, gradient/refit hoặc tính P&L query. QA cũ
theo source commit được giữ để truy vết hai lần dừng kỹ thuật trước point
đầu: placeholder event thiếu ngày và cấu hình CUBLAS. Adapter đã reuse
`_visible_events`, CLI đặt deterministic CUDA như runtime cũ; không đổi
economic/PIT rule. Không có point khoa học nào được chọn lại khi sửa hai lỗi.

Counter đã materialize trước source checks đầu tiên. Snapshot sau cold
replay: **888,773618 giây đã dùng**, **63.911,226382 giây còn lại** (≈17,75 giờ),
`active_since=null`; tính cả hai lần dừng kỹ thuật và hai lượt validation/
replay, không reset giữa chúng. Tham số/schema/spec/2.597 evidence v2 vẫn
được verifier đối soát nguyên byte; ledger vẫn4.498 request, SHA
`6de7ea8d023a9530c99d1c334ae94f248ba3c8297b7418497503cb73481b56b5`.
Tiếp theo **W11-10** freeze manifest/schema/client/prompt và preflight khả
thi theo quỹ/lịch còn lại trước release development. PASS ở đây không là
nomination hoặc xác nhận lợi ích kinh tế; các cờ release/API vẫn false.
