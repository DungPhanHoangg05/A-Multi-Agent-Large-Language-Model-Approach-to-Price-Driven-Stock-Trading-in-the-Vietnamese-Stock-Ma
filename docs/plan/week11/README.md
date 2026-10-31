# Tuần 11 — Kiểm định giá trị tăng thêm của MT-BICL

**Hiện hành 01/11/2026: 15/25 task DONE; 2 NOT_RUN; 1 IN_PROGRESS; 7 TODO.**
W11-15 bàn giao v3 và W11-16 audit phương pháp hoàn tất bằng tài liệu tại
mục22. **W11-17 SPEC_LOCK_PASS** tại mục23. **W11-18 IN_PROGRESS**:
snapshot đầu còn `INSUFFICIENT_DATA` tại mục24. Theo yêu cầu mới, phương án
tiếp nối là **v4.1: ngân hàng định lượng có mask + panel256 điểm LLM**, tại
[mục26](#26-w11-18--phương-án-256-điểm-llm-trong-35-ngày-01112026).
Bốn key có quota độc lập, tổng khoảng80 điểm/ngày do người dùng xác nhận.
Mục tiêu riêng W11-18 là3–5 ngày; cần khóa amendment và triển khai trước.
**Lệnh mục25 vẫn thu thập1.640 điểm; chưa có CLI chạy panel256.** Không
tiếp tục toàn grid để thực hiện phương án rút gọn. Release/spec v4 giữ
nguyên byte, không được coi là đã cho phép v4.1 hoặc đã qua readiness.
Chưa mở W11-19, train predictor hoặc gọi API từ agent trong lượt này.
**Các giai đoạn còn lại không giới hạn thời gian:** không trần giờ, hạn ngày, giới hạn 12 tuần
hoặc điều kiện NOT_RUN vì đến 05/11, 07/11, 10/11. W11/W12 là tên giai đoạn.
Các cap/deadline trong receipt và thiết kế v1–v3 bên dưới là lịch sử, không
chi phối kế hoạch mới. Cutoff PIT, horizon kinh tế và backoff API vẫn áp dụng.

**Trạng thái các vòng đã chạy:**
**W11-05 đã khóa v2 NOT_NOMINATED; confirmation v2 NOT_RUN** tại mục14.
Report mô tả giữ `NOT_EVALUATED` nguyên byte; quyết định máy ở receipt riêng.
**W11-07 SPEC_LOCK_PASS** tại mục15; grant18 giờ là bản khóa lịch sử.
**Chỉ đạo mới31/10: bỏ giới hạn bộ đếm giờ**, áp dụng qua amendment tại mục20;
counter cũ giữ làm bằng chứng, không còn chặn chạy/resume.
**W11-08 DONE** tại mục16: đã triển khai bucket/context/utility/facts/policy v3,
kiểm thử offline PASS. **W11-09 OFFLINE_VALIDATION_PASS / REPLAY_MATCH** tại
mục17. **W11-10 DONE — RELEASED_DEVELOPMENT_2023_ONLY** tại mục18;
**W11-11 DONE —804/804 slot và cold replay vận hành PASS** tại mục19.
**W11-12 DONE — v3 NOT_NOMINATED** tại mục21; Full−Original=−5,313090 đpt,
accuracy45% so Original65%; không cấp release xác nhận2025.
[Kế hoạch tổng](../plan.md) · [W10](../week10/README.md) · [W12](../week12/README.md)

**Lệnh tái lập/tiếp tục của run v2 đã hoàn tất; không dùng để mở v3:**

```powershell
py -3.13 -X utf8 scripts/continue_mt_bicl_development.py
```

Lịch/quỹ giờ tại [W10-01](../week10/README.md#w10-01--inventory-và-khả-năng-thực-thi-27102026)
đã được thay thế bởi chỉ đạo bỏ giới hạn thời gian. Công việc tiếp nối theo
dependency và bằng chứng ở mục22, không theo số giờ đã dùng hoặc ngày chót.

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

Mục1–4 và mục6–21 giữ **thiết kế/kết quả lịch sử v2/v3**. Checklist mục5
và amendment mục26 là thứ tự làm tiếp; mục22–25 giữ nguồn thiết kế v4. Không sửa JSON đã khóa hoặc dùng
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

Task01–14 giữ nguyên kết quả đã chạy; 13/14 NOT_RUN do nomination v3 FAIL,
không phải hết thời gian. Task15 đóng bàn giao v3; 16–25 là hướng nghiên cứu
mới. DONE của audit/kế hoạch không phải nghiệm thu code hoặc hiệu quả v4.

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
| W11-10 | Freeze v3 source/schema/model/manifest/repeat; dry-run, API preflight và release development riêng | 09 đạt | [x] DONE — freeze/dry-run804/replay/control thật/source/PIT/feasibility PASS; release2023 neo Git |
| W11-11 | Người dùng chạy một development v3 đầy đủ, checkpoint/ledger riêng | 10 | [x] DONE —804/804 (480 primary+324 repeat),133 bypass; raw/cache/ledger/source/PIT/cold replay PASS;0 pending/unknown |
| W11-12 | Cold verify, rebuild account, decomposition và nomination v3 theo rule mới đã khóa | 11 | [x] DONE — account/report/decomposition/cold replay PASS; v3 NOT_NOMINATED theo rule đã khóa |
| W11-13 | Audit exposure/MDE, manifest xác nhận2025 và release v3 nếu nominate | 12 đạt | [ ] NOT_RUN — điều kiện nomination v3 không đạt, không phát hành release xác nhận |
| W11-14 | Người dùng bắt đầu xác nhận trước hết05/11, giữ checkpoint | 13 | [ ] NOT_RUN — v3 NOT_NOMINATED, không có release xác nhận |
| W11-15 | Bàn giao v3 NOT_NOMINATED, xác nhận NOT_RUN và toàn bộ kết quả bất lợi | 05–14 chốt trạng thái | [x] DONE — mục22; bàn giao tài liệu, không tạo release |
| W11-16 | Audit paper → teacher/simulator → learner → policy; phân biệt lỗi áp dụng và giới hạn dữ liệu | 12/15 | [x] DONE — mục22; chỉ phân tích bằng chứng có sẵn |
| W11-17 | Khóa protocol v4, exposure, feature/task/likelihood, folds, registry và tiêu chí từng pha | 16 | [x] DONE — SPEC_LOCK_PASS; 24 test metadata/PIT, source/runtime/ledger và cold replay PASS; mục23 |
| W11-18 | Amendment v4.1; ngân hàng numeric có mask, panel256 Original thật, cold audit hai tập dữ liệu | 17 và amendment18a | [ ] IN_PROGRESS — kế hoạch3–5 ngày tại mục26; chưa triển khai/release256 |
| W11-19 | Baseline và Bayes có điều kiện; kiểm tín hiệu trên rolling folds trước distillation/LLM integration | 18 | [ ] TODO |
| W11-20 | Meta-train learner v4 bằng prior/target có quan hệ x→return; loss target, cơ chế và kiểm shift | 19 đạt | [ ] TODO |
| W11-21 | OOF calibration trên ngân hàng numeric; h/decision trên panel, K0/pooled/Complete_case_MT và khóa candidate | 20 | [ ] TODO |
| W11-22 | Tích hợp shadow dùng Original durable; kiểm off=Original, economics/PIT/retry; freeze development | 21 đạt | [ ] TODO |
| W11-23 | Development v4 ghép cặp đủ ma trận/cohort và repeat đã khóa | 22 | [ ] TODO |
| W11-24 | Cold audit, phân rã forecast/policy, nomination và toàn bộ trường hợp bất lợi | 23 | [ ] TODO |
| W11-25 | Bàn giao candidate/receipt/exposure cho W12; hoặc chốt chưa đạt và giả thuyết cần nghiên cứu | 24 | [ ] TODO |

W12 được chuẩn bị và chạy xác nhận sau W11-25 khi đủ điều kiện khoa học;
không còn deadline bắt đầu hoặc khóa dữ liệu theo lịch cũ. Theo AGENTS.md 1.2 chỉ test đường
đổi và đối soát receipt đúng nguồn, không tự chạy toàn suite mỗi task.

Amendment này được lập theo yêu cầu sửa phương pháp ngày 28/10 sau W10-07;
không còn áp dụng lệnh dừng mọi nghiên cứu mới của recipe v1 cho v2. Các
lệnh cấm sửa bằng chứng, chọn bằng test và triển khai khi chưa có release
vẫn giữ. Bàn giao W10-14 chưa gọi development/API hoặc tăng tiến độ W11.
Lượt amendment README trước W11-01 chỉ sửa Markdown, đã kiểm diff/link/
đồng bộ dependency và không chạy lại suite theo AGENTS.md1.2. W11-01 có
mã mới nên kiểm theo phạm vi tại mục6. Các mốc giờ/ngày cũ đã bị thay thế
cho công việc tiếp nối theo chỉ đạo31/10 ở đầu tài liệu và mục22.

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

## 18. W11-10 — Freeze và preflight development v3 (30/10/2026)

**PASS — W11-10 DONE; RELEASED_DEVELOPMENT_2023_ONLY.** Source mới
`18b769bbc937e739235209bb9b7d828b115c6ee1` tách riêng serializer, journal,
transport, freeze/preflight và hai CLI v3; không sửa code/schema/weights
đã khóa của v2 hoặc W11-08/09. LangChain cần tên cho schema anchored:
adapter thêm metadata `title=UtilityICLReplyV3`, giữ nguyên mọi property,
enum và constraint. Original/A dùng nguyên schema legacy; serializer
đối chiếu body Original trên cả60 upstream với manifest v2 trước freeze.

[Manifest v3](development_manifest_v3.json) khóa source/runtime/candidate,
snapshot60 point, template hai trạng thái a0, body/token bound, thứ tự96
block và804 slot (480 primary,324 repeat;36 Original_duplicate độc lập).
Khi anchor hợp lệ, tối đa671 slot đủ điều kiện HTTP và ít nhất133 slot
bypass theo support đã khóa; anchor sai có thể tăng bypass. Không bỏ slot,
không sử dụng response v2 làm kết quả v3. Prompt lớn nhất4.949 ký tự,
reserve lớn nhất4.882 token/request, bao gồm output và padding hash động;
mỗi body thực tế vẫn phải qua serializer/guard và kiểm bound trước HTTP.
Utility_only lưu offline, không phát sinh request LLM.

Manifest byte SHA
`b3437959cddb76f6c26e8ef92224931e296e92f6fb01e1cff5545799e6f7493c`,
snapshot content SHA
`b19e25ea6733fd4316ece2b1182e6bcd78785b8105108db6a92b57bcdd131635`.
Dry-run đủ804 slot và cold replay804 slot **PASS**,671 HTTP giả lập,
133 bypass, **0 HTTP thật/0 upstream mới/0 model forward**. Fixture dùng
namespace riêng, identity cấm promote sang research; replay từ raw/cache/
ledger không invoke lần hai. Bằng chứng máy tại
`outputs/bayesian_benchmark/mt_bicl_v3/development2023/freeze/`:
`input_snapshot.json`, `dry_run.json`, `offline_preflight.json`.
Dry-run receipt byte SHA
`d91f8ee0941e91ae3f7ff3b978c36c32371f7d47ff4270055753bbb165ba4b49`.
CLI `verify` sau neo manifest Git **PASS**: tái đối soát source/snapshot,
validation/upstream/PIT và các bằng chứng khóa cũ, không inference/HTTP.
Counter sau lượt này: **1.252,942398 giây đã dùng**, **63.547,057602 giây
còn lại (≈17,65 giờ)**, `active_since=null`; không reset từ W11-09.
Ledger vẫn4.498 request, byte SHA
`6de7ea8d023a9530c99d1c334ae94f248ba3c8297b7418497503cb73481b56b5`;
2.597 evidence v2 giữ nguyên. Tại mốc offline này chưa có control thật
hoặc release receipt; kết quả nghiệm thu sau control ở cuối mục18.

Preflight offline dùng3.897 latency HTTP thành công đã có, P95≈4,719 giây,
sliding61 giây/8.000TPM/30RPM và reserve input+output bảo thủ. Dự toán
development gồm dự phòng verification≈**41.742,64 giây (11,60 giờ)**;
stress804 HTTP≈13,85 giờ, repair format ở mọi invocation≈22,96 giờ.
Dự toán development+xác nhận1.348 slot ở prompt cost hiện tại lớn nhất≈
**124.838,56 giây (34,68 giờ)**, **không fit quỹ18 giờ còn lại** theo giả
định này. Đây là dự toán bảo thủ cho2025 chưa mở, không phải kết quả
prompt/support2025; W11-13 phải đo lại nếu nominate. Không hứa hoàn tất
xác nhận hoặc cấp thêm giờ, không cắt comparator/mẫu để khớp cap. Quota
ngày do provider quyết định; retry/quota wait chưa biết bị hard cap chặn.
Status của snapshot offline là `AWAITING_LIVE_CONTROLS`; không dùng lịch
sử latency thay cho preflight thật hoặc coi dự toán nominal là bảo đảm runtime.

Kiểm thử theo AGENTS1.2: **99 test riêng biệt PASS** (19 mới,80 hồi quy
đúng đường gọi), gồm17 test trong hai module leakage v3 và8 test paired;
**9 file Python mới biên dịch PASS**. Phạm vi gồm schema/body SDK, policy,
budget, PIT/reuse source, retry/transport/checkpoint và paired; không chạy
full suite, compileall toàn cây hoặc E2E toàn hệ thống. Sau khi thêm hai
guard recovery cuối, chạy lại13 test recovery; không ghi cộng lượt chạy
lại vào số test riêng biệt. Bằng chứng gate cũ chỉ được viện dẫn cho
source/runtime nguyên byte, không coi là đã chạy lại toàn hệ thống.

Journal ghi intent/UUID trước HTTP, lưu raw cache/audit trước complete;
resume đọc durable trước khi cần credential. Slot complete không replay;
slot unknown tự phục hồi hoặc retry **cùng UUID**, giữ toàn bộ row/reserve
cũ. Mất/sửa identity, ready, slot, cache, body, source hoặc ledger gây dừng.
Key khác tự chạy control theo scope hash trước HTTP mới, không reset quota.
HTTP429 phút tự chờ; quota ngày có reset time thì chỉ chờ khi vừa cap/lịch,
không vừa hoặc thiếu reset time thì dừng giữ checkpoint. Mọi stage dùng
counter18 giờ cũ; sạch Ctrl+C loại downtime, crash gap vẫn tính bảo thủ.

Lệnh người dùng cho control trước release và tiếp tục run sau release:

```powershell
py -3.13 -X utf8 scripts/continue_mt_bicl_v3.py
```

Trước khi có release Git, lệnh chỉ chạy bốn probe synthetic: schema legacy
và anchored, mỗi schema có prompt ngắn/dài đại diện. Không dùng point/nhãn
cohort hoặc dự báo thị trường. Giai đoạn control đã hoàn tất và nghiệm thu
bên dưới. Hiện đã có release; dùng cùng lệnh theo mục19 để chạy hoặc
resume development2023, không nhập UUID hoặc xóa file. Chưa có quyền
confirmation2025 hoặc train.
Phân công **“10–12 … user chạy API”** tại mục13.4 vẫn áp dụng; agent chỉ
chuẩn bị, chạy giả lập chặn socket và nghiệm thu bằng chứng, không đọc key.

CLI offline do agent dùng: `scripts/prepare_mt_bicl_v3.py prepare` để
freeze/dry-run, `verify` để đối soát source/snapshot/Git, và `release` sau
control thật/feasibility PASS. Manifest phải neo Git trước control; receipt
release phải neo Git trước primary. Không cấp release từ mock hoặc chỉ từ
ước lượng quota/ngân sách. Thời gian xác nhận1.348 slot mới là dự toán,
phải tái kiểm ở W11-13; không đổi cap/mẫu/ma trận nếu không đủ quỹ.

**Nghiệm thu control thật và release,30/10/2026:** bốn probe
`legacy_short`, `legacy_long`, `anchored_short`, `anchored_long` đều
complete, HTTP200, mỗi probe đúng một request/UUID. Cold audit kiểm
serializer/body, schema/action/horizon/fact assertions, raw response hash,
durable cache, ledger và credential scope **PASS**; ready receipt byte SHA
`96133e5a4622f5d052eda0df9ce63261b9da8d2aabdde648fbfcee97d5510450`.
Tổng usage4.619 token (4.184 input,435 output), latency1,048–1,207 giây.
Ledger4.502 request: giữ nguyên4.498 row nền, chỉ thêm đúng bốn control,
không HTTP thừa/retry hoặc response development. Ledger byte SHA tại
nghiệm thu `93f70c4566445deb04b1ebd00d59821cbb218321d95c9e310541adc7d3eb6f84`.

CLI `release` chặn socket đã tái đối soát source/runtime/weights/spec,
validation/upstream60 point/PIT và v2 evidence; control raw/ledger PASS,
profile `DEVELOPMENT_FEASIBLE`. Kiểm thêm804 hash journal dry-run và
fixture ledger nguyên byte. [Release v3](development_release_v3.json)
byte SHA `f2c5b4b93a2be54127fd6ea5cd992890ce351be4b07b46dc2f157c8e7170602e`,
chỉ cho development2023 và Decision mới. Manifest vẫn nguyên byte với
`primary_allowed=false`; quyền chạy lấy từ receipt release riêng đã neo
Git, không sửa cờ lịch sử. Confirmation/training/candidate substitution
vẫn false. Không tăng cap hoặc đổi phương pháp sau control.

Sau nghiệm thu: counter **1.476,968315 giây đã dùng**, **63.323,031685 giây
còn lại (≈17,59 giờ)**, `active_since=null`. Profile gồm3.901 latency
thành công, P95≈4,719 giây; development≈11,60 giờ, combined xác nhận bảo
thủ≈34,68 giờ vẫn không fit phần quỹ còn lại theo giả định đó. Giới hạn
retry/quota ngày và điều kiện tái đo xác nhận ở trên giữ nguyên.
Đây là nghiệm thu receipt/bằng chứng, không sửa code/test/schema/runtime:
đối soát hash/Git và viện dẫn đúng99 test/9 Python PASS tại source `18b769b`;
không chạy lại unit/compileall/E2E hoặc leakage suite theo AGENTS1.2.

## 19. W11-11 — Chạy development v3 đã release

**PASS — W11-11 DONE,31/10/2026;11/15 task hoàn tất.** Đủ **804/804 slot
complete**:480/480 primary và324/324 repeat, **0 pending/unknown/missing**.
Ma trận đủ8 nhánh×60 primary và9 nhánh×12 point×3 repeat.671 slot có
response thật,133 slot bypass đúng support mask; không bỏ point/nhánh.
36 Original_duplicate có cùng canonical request với Original của block,
nhưng UUID độc lập và HTTP200 riêng. Control không được tính vào804 slot.

Lệnh vận hành giữ để tái lập/resume cùng run đã hoàn tất:

```powershell
py -3.13 -X utf8 scripts/continue_mt_bicl_v3.py
```

Lần này lệnh đã được phép chạy development2023 theo release đã neo Git:
60 point/480 primary và12 point×3 repeat/324 slot, giữ đủ bypass. Dữ liệu
và thứ tự lấy nguyên manifest; upstream được reuse, không gọi lại vision.
Journal research ở `outputs/bayesian_benchmark/mt_bicl_v3/development2023/run/research/`;
raw HTTP cache ở `run/http_cache/`, ledger dùng chung chỉ append. Cùng
credential đã PASS không gọi lại bốn control; credential khác tự preflight
trước request mới, giữ nguyên mọi usage/reserve/UUID cũ.

Console báo `Đã lưu .../804 slot v3` theo point/repeat. Các dòng `[Quota]`
nghỉ chủ động là pacing bình thường; không mở thêm tiến trình cùng lúc.
Nếu bị ngắt, Ctrl+C hoặc hết quota, **chạy lại cùng lệnh** khi có thể tiếp
tục; không xóa cache/checkpoint/counter/lock hoặc nhập UUID. Durable/complete
được đối soát trước key/API, unknown còn dở retry cùng UUID. Giới hạn bộ
đếm18 giờ đã bỏ theo mục20; lỗi integrity hoặc hạn lịch riêng vẫn dừng
giữ bằng chứng. Quota do provider quyết định, pacing/backoff giữ nguyên.

Hoàn tất khi console báo `Đủ 804/804 slot v3; chờ W11-12 kiểm định, chưa P&L.`
Đã nghiệm thu kết quả người dùng; tiếp theo W11-12 cold verify/rebuild
accounts/decomposition/nomination. Chưa đánh giá P&L hoặc accuracy
development ở W11-11, chưa cấp quyền xác nhận2025. Giữ hạn bắt đầu
05/11 và data stop07/11; không còn trần số giờ thực thi. Dự toán11,60 giờ
là giá trị trước run, không phải cam kết khi provider giới hạn quota/retry.

**Đối soát nghiệm thu:** CLI `--verify-only` chạy chặn network, trên bản
sao journal, trả `UNBOUNDED_RESUME_VERIFIED:804/804;HTTP=0`, không còn slot
cần dispatch. Source/schema/weights/manifest/release/amendment/Git, PIT và
upstream60/60, canonical body/UUID/raw cache/fact-anchor/final policy đều
PASS. Mỗi671 UUID scientific nối đúng một HTTP200; toàn bộ692 scientific
HTTP ID nối đúng journal và duy nhất.21 lần lỗi gồm19 HTTP429 và2 transport
error vẫn giữ nguyên row/reserve/audit, không còn row unknown trong run.

Ledger **5.206 row** =4.498 row nền +692 research +16 control. Bốn scope
credential đều cold audit4 control HTTP200 PASS; từng scope hoàn tất
preflight trước HTTP research đầu.687 raw cache file nối đúng671 research
và16 control HTTP200, không cache thừa/thiếu. Usage research đã ghi nhận
1.391.314 token (1.275.787 input,115.527 output), không suy ra chi phí của
transport error thiếu usage. Prefix4.990 row và568 complete trước amendment,
counter lịch sử64.800 giây, source khoa học và các artifact cha nguyên byte.

Run signature
`43613b0f9d9f527775f8046f7881a367ce44987a7c2648c7647e17a1ee1cf6ea`;
hash cây tính từ map tên file→byte SHA, JSON canonical sorted:

- 804 slot journal: `7ae447b17b5079a1344edb5c5db972fe598ad8b440e329511d10136b7704ce03`.
- 687 raw cache: `e0d880143995ecdf64c48926d02c0232f84bf5453e1133c71afe0b6cddc7cccb`.
- Ledger byte SHA: `b89c5f7eff547a73f44136e5b60372c0ce5b9680fc47a02eddde13a42fd1e956`.
- `run/research/progress.json`: `ebf129d61dfc0b857e36fb9c6a4debbe1fa20b5d4f101edf9a5b9001c192d029`.

Progress giữ `COMPLETE_AWAITING_AUDIT` cho bước kiểm định kinh tế W11-12;
đây là hoàn tất chạy và nghiệm thu vận hành, chưa là nomination hoặc bằng
chứng tăng lợi nhuận. Không tính P&L/query outcome, mở2025 hoặc gọi API mới.
Lượt chốt chỉ sửa tài liệu; theo AGENTS1.2 kiểm diff/link/hash và cold replay
thực, viện dẫn53 test/3 Python PASS tại source vận hành `8782c1e` nguyên
byte, không chạy lại unit/full suite/compileall/E2E/leakage suite.

## 20. Bỏ giới hạn bộ đếm thời gian theo chỉ đạo31/10/2026

Người dùng yêu cầu: **“loại bỏ hoàn toàn phần giới hạn bộ đếm này. để
người dùng chạy tự do”**. [Chính sách vận hành mới](runtime_policy_v3.json)
thay thế trần18 giờ và việc tính gap crash trong đường chạy/resume hiện
hành. Không tăng quota provider hoặc cấp quyền thực nghiệm khác. Các
grant/receipt/protocol/weights lịch sử giữ nguyên byte; những đoạn mô tả
cap18 giờ ở mục13–18 là bằng chứng trước amendment, không còn là giới hạn
runtime hiện hành. Counter cũ không bị reset, hạ số hoặc ghi tiếp; giữ
nguyên snapshot64.800 giây đã tính trước thay đổi.

Nguyên nhân dừng cũ: phiên chưa đóng từ20:40:33 ngày30/10 tới10:03:47
ngày31/10 (+07) bị tính phí crash bảo thủ29.315,702322 giây, hết phần
grant còn lại. Amendment bỏ cơ chế này; không trừ lại hoặc sửa log quá khứ.
Mốc kế hoạch05/11 và data stop07/11 độc lập với bộ đếm, giữ nguyên.

Entry point giữ nguyên lệnh, tải đúng CLI đã release từ object Git được
kiểm SHA và dùng session không đếm giờ cùng verifier vận hành mới.
Chỉ entrypoint được phép thay theo source receipt mới; tám file source
khác trong manifest, source validation/protocol, model/schema/prompt,
thứ tự/cohort/repeat, journal signature và chính sách raw/final action
giữ nguyên. Các bước vận hành tiếp theo dùng `RuntimeSession`/verifier
mới; CLI frozen cũ chỉ dùng tái lập lịch sử tại đúng source cũ.

Chính sách khóa prefix4.990 row ledger và hash568 slot complete trước
amendment; mọi row/reserve/complete cũ phải nguyên vẹn, chỉ append/chạy
phần còn thiếu. Slot tiếp theo là **569** (index568),
`VCB-2023-10-30`, repeat1, `Stats_only`; giữ UUID
`c43c09a7-6efb-40fe-8054-ccf2996d0fc5`. Không gọi lại568 slot hoàn tất.

Kiểm theo AGENTS1.2: **53 test PASS** (10 mới,43 hồi quy trực tiếp),
gồm7 test leakage/PIT; **3 file Python thay đổi biên dịch PASS**. Phạm vi
gồm counter đã đầy vẫn chạy, gap qua đêm/Ctrl+C, chờ25 giờ không bị cap18,
khóa OS, UUID/reserve/cache, body guard, source override đúng một entrypoint
và PIT. Không full suite/compileall/E2E; không API thật/key/P&L hoặc2025.
Lệnh đối soát offline mới, dùng bản sao journal và dừng trước request thiếu:

```powershell
py -3.13 -X utf8 scripts/continue_mt_bicl_v3.py --verify-only
```

Kết quả thực tế31/10: **UNBOUNDED_RESUME_VERIFIED,568/804,HTTP=0**;
tái đối soát upstream/PIT60/60 và raw/cache/policy của complete prefix
trên bản sao journal, dừng đúng slot569/cùng UUID trước credential/API.
Ledger giữ4.990 row, counter cũ nguyên byte, không reset hoặc ghi thêm.
Source mới `8782c1e`, chính sách byte SHA
`02a44d216f0adb29cccd860b11f556baa175627d1e5c40dc7ca9c8291e5107d4`;
counter lịch sử byte SHA
`e9ea478072c97fa0931d45c0048b2f964e9e48d3b60ee6f847ae687f0c654878`.

## 21. W11-12 — Kiểm toán kinh tế, phân rã và nomination v3 (31/10/2026)

**PASS kỹ thuật; v3 NOT_NOMINATED.** [Receipt máy](development_nomination_v3.json)
khóa quyết định riêng; report mô tả giữ `NOT_EVALUATED` để không ghi đè
bằng chứng trước consumer nomination. Chỉ Full_utility_ICL được xét,
không promote ablation, không vote repeat hoặc thay G60/threshold sau kết quả.

Source `04a2e05` thêm audit/account, report/decomposition, consumer
nomination và CLI offline. Đối soát804 slot/raw/UUID/body/cache/control,
PIT/upstream60 point trước, sau đó cố định mọi action final/offline/diagnostic
**trước khi mở payoff2023**.944 occurrence nhãn context được kiểm lại bằng
giá/quyền và `compute_round_trip_net_return`, strict exit<query. Không gọi
API/model, gradient/refit hoặc dùng payoff2025.188 account được tái dựng:
36 primary+120 repeat cho9 nhánh thật/offline và32 account diagnostic
raw/facts-only; mỗi account dùng engine T+2.5,50 triệu/mã, phí0,25% và
slippage0,10% mỗi chiều, SHORT=CASH, cổ phiếu phân số như hợp đồng cũ.

Artifacts tại `outputs/bayesian_benchmark/mt_bicl_v3/development2023/`:
`verification/accounts.json`, `analysis/report.json`, `analysis/results.png`.
G60 giữ đủ10 feature-unavailable và20 point Full không support; Full support40,
No_target recompute như snapshot trước run. Báo mọi K/m/bucket/regime/quý,
strata thiếu mã giữ D null, không dùng subgroup thay primary.

| Nhánh | Mean return 4 account (%) | Accuracy dấu net (%) | LONG/60 | Mean MDD (%) |
| --- | ---: | ---: | ---: | ---: |
| Original | 5,1313 | 65,00 | 15 | 2,2922 |
| A_reference | 3,9936 | 61,67 | 15 | 2,9123 |
| Fact_Anchor | −1,6897 | 43,33 | 50 | 10,0388 |
| Plain_revision | −0,2809 | 46,67 | 50 | 8,0845 |
| Full_utility_ICL | −0,1818 | 45,00 | 47 | 8,0663 |
| No_utility | 0,9433 | 48,33 | 51 | 8,4024 |
| No_target | −1,6897 | 43,33 | 50 | 10,0388 |
| Stats_only | −0,6967 | 45,00 | 49 | 9,0915 |
| Utility_only | 0,0000 | 60,00 | 0 | 0,0000 |

Accuracy tính đúng dấu lợi nhuận LONG sau phí trên60 point, khác hit-rate
lệnh LONG và khác return tài khoản; Utility_only60% là luôn CASH trên mẫu
có36/60 nhãn DOWN, không chứng minh khả năng dự báo. D là mean đều bốn
Δreturn tài khoản, không mean cycle, tổng lợi nhuận hoặc portfolio chung.

| Mã | Original return (%) | Full return (%) | Full−Original (đpt) |
| --- | ---: | ---: | ---: |
| FPT | 3,6807 | 6,9931 | 3,3124 |
| MWG | 16,4215 | −11,2057 | −27,6272 |
| VCB | −1,5148 | 2,8321 | 4,3469 |
| VNM | 1,9378 | 0,6534 | −1,2844 |

Rule nomination đã khóa: **D Full−Original=−5,313090<0**; chỉ **2/4 mã**
tăng (<3); **Full−A=−4,175356<0**; mean ΔMDD=**5,774045>2** và max ΔMDD=
**12,228105>5** đpt. Chỉ guard mới **Full−Fact_Anchor=+1,507930>0** đạt
cùng G60 đầy đủ. Năm guard kinh tế không đạt; không được lấy accuracy,
nhánh No_utility hoặc repeat thuận lợi để đổi quyết định.

Phân rã return account khép đúng tổng −5,313090 đpt:

- Fact_Anchor−Original: **−6,821021 đpt**, tỷ trọng LONG tăng15→50/60.
- Full raw proposal−Fact_Anchor: **+2,181424 đpt**.
- Guard facts/context trên Full raw: **0 đpt** ở primary này.
- Utility veto trên cùng raw proposals: **−0,673494 đpt**;5 tác động bất
  lợi,2 có lợi,53 không đổi/zero. Full thực tế hơn Plain0,099157 đpt nhưng
  kém No_utility1,125114 đpt; không đồng nhất mọi gain với Bayes.

Đây là counterfactual từ saved actions/payoff, không là tác động nhân quả
thuần của prompt/Bayes: các nhánh có response LLM độc lập. Giữ toàn bộ raw,
a0/final/reason/Q10 trong cases; Full có30 KEEP,7 veto,3 accepted change,
20 bypass (10 missing-feature,10 unsupported), không giấu phần bất lợi.
Sensitivity hoàn nguyên từng action và bỏ từng mã có trong report, giữ G.

Trên cùng12 point repeat, D Full−Original lần lượt r0/r1/r2/r3=
**+0,193323/−0,700933/−0,528206/−0,464985 đpt**; account reset trên sample,
không so trực tiếp với G60. Original_duplicate khác Original1/36 lần;
72 cặp phụ thuộc/nhánh chỉ mô tả, không nhân N hoặc vote. Development đã
exposed/adaptive; không dùng CI để nominate. Bootstrap xác nhận vẫn cần
release riêng và không được gọi từ kết quả này.

Kiểm theo AGENTS1.2: **77 test riêng biệt PASS** (24 mới,53 hồi quy đúng
caller;5 test mới trong module leakage), **5 Python mới biên dịch PASS**.
Ba lỗi fixture ban đầu (Reference và thứ tự ngày khi giả năm) đã sửa trước
phân tích thị trường; không sửa source/run/tham số sau mở payoff. Không
full suite/compileall/E2E; test tập trung economics, PIT, materialize trước
outcome, decomposition, MDD, strict-zero/Full−A/Fact_Anchor, repeat/paired,
immutability và consumer không promote ablation.

```powershell
py -3.13 -X utf8 scripts/analyze_mt_bicl_v3.py
py -3.13 -X utf8 scripts/analyze_mt_bicl_v3.py --verify-only
```

Receipt/source/report/account/hash và hình đều được cold rebuild bằng lệnh
thứ hai, không tin cờ PASS tự khai; hình đã kiểm trực quan. Hash byte:

- Accounts: `4ecc5a30061013232b5e4098bacc1643e02786bebc1ff3003ea73c57eaa38120`.
- Report: `ac92ebe91c62e76e3d05668c5d72b85dded6c125e25bc8abad444a90e87ad3d9`.
- Hình PNG: `06553a51825ae39084fa8315266bbc43b35b4f7359fd77465ab5a855e8f363ec`.
- Nomination: `aeb0bb41fc54b33fb152145ddf48a1773a4017e460fbfd2a549bae26b49897d0`.

Ledger prefix5.206 row, run804/cache687, v2 evidence2.597 file, model/runtime,
manifest/release và counter lịch sử nguyên vẹn. Consumer cho phép append
ledger sau prefix đã khóa, không reset row/reserve hoặc reseal run.
**Confirmation v3 NOT_RUN**, quyền xác nhận/training/substitution vẫn false;
W11-13/14 không chạy do không đạt nomination. Bước bàn giao còn W11-15;
không tự sửa recipe, mở lại training hoặc dùng2025 để cứu kết quả.

## 22. W11-15/16 — Đóng v3, audit cách áp dụng paper và kế hoạch v4 (31/10/2026)

### 22.1. Phạm vi và kết luận

Theo yêu cầu mới, lượt này **chỉ phân tích và cập nhật Markdown**. Không sửa
Python/test/config/schema, không train, gọi API, chạy model hoặc mở outcome2025.
V3 giữ NOT_NOMINATED; W11-13/14 giữ NOT_RUN. W11-15 bàn giao đủ receipt,
report, decomposition và giới hạn ở mục21 sang W12. Không đổi nhánh thắng.

Bỏ mọi trần giờ và deadline lịch cho công việc tiếp nối, kể cả hạn 12 tuần,
05/11 bắt đầu, 07/11 khóa dữ liệu và 10/11 hoàn tất. W11/W12 chỉ là tên
giai đoạn để giữ cây tài liệu. Các số giờ/ngày trong receipt cũ không còn
là điều kiện dừng kế hoạch mới. PIT/exit<query, horizon T+2.5, quota/backoff,
checkpoint và việc khóa mẫu trước kiểm định vẫn là hợp đồng khoa học/vận hành.
Không giới hạn thời gian không có nghĩa thử đến khi thắng: mọi revision,
candidate và lần xem kết quả phải được ghi nhận, holdout chỉ mở theo protocol.

**Chẩn đoán:** v3 thất bại cả dự báo lẫn cách tích hợp. Cần thay bài toán mà
learner học và đường ra quyết định; tăng seed, nới Q10 hay đổi vài câu prompt
không xử lý đầy đủ. Phương án v3 trước đây đã đặt một quyết định nền mới
chưa chứng minh tương đương vào giữa hệ thống, đồng thời giữ teacher không
phụ thuộc đặc trưng. Đó là hai lựa chọn thiết kế cần sửa, không phải lỗi
do người dùng chạy sai hoặc chỉ do gate nomination quá chặt.

### 22.2. Điều gì đã được quan sát, điều gì mới là giả thuyết?

Số liệu đọc từ account/report v3, primary G60; không trộn Original của v2
(4,464827%) với Original của v3 (5,131315%). Model/API có biến thiên giữa run.

| Bằng chứng | Kết luận giới hạn |
| --- | --- |
| Original 5,131315%; Full −0,181775%; D −5,313090 đpt; accuracy 65%→45% | Không đạt ngay lợi ích so hệ thống gốc, không thể giải quyết bằng đổi nhãn gate |
| Fact_Anchor −1,689706%; 35 CASH→LONG, 0 LONG→CASH so Original; LONG 15→50/60 | Anchor là thay chính sách lớn; không phải chỉ thêm một bảng dữ kiện trung tính |
| Phân rã: −6,821021 anchor +2,181424 raw revision +0 fact guard −0,673494 utility veto | Tác hại lớn nhất nằm trước Bayesian revision; veto cũng làm kém trên mẫu này |
| 20 point không support: Full LONG16, Original LONG6, khác10 action | “Không đủ Bayesian context” vẫn đổi hệ thống vì fallback về anchor mới; cần off=Original thực sự |
| Full support40/60, FPT3/12; 0 interval dương,12 âm,28 qua0; chỉ1/12 âm bền qua mọi leave-one-task | Tín hiệu utility chủ yếu yếu/nhạy membership; gate chỉ có khả năng sửa LONG→CASH, không tạo cơ hội mua mới |
| Teacher chỉ nhận count; simulator sinh y độc lập x; approximation union KL≈0,000405 | PASS cơ chế hiện tại chứng minh học gần một mô hình tần suất, không chứng minh học quan hệ tín hiệu→lợi nhuận |
| U được tính từ teacher và bootstrap magnitude; p_student chỉ đi vào prompt | Phần điều khiển numeric của v3 không do learner học phân phối payoff; không quy gain của U cho distillation |

20 point không support có D nhóm +0,142816 đpt khi dựng account riêng;
không phải mọi thay đổi ở nhóm này đều gây lỗ. Vấn đề là mất tính đối chứng
và fallback, không chọn nhóm bất lợi để kể chuyện. Không cộng D subgroup
vào D toàn bộ vì đường vốn/lãi kép khác nhau.

Ví dụ `MWG-2023-01-06`: Fact_Anchor chép đúng MACD dưới Signal, dưới0 và
Close dưới SMA20, nhưng trả LONG với lý do **mua khi vượt kháng cự44**.
Engine lại mua vô điều kiện tại Open phiên kế tiếp. Full raw muốn SHORT,
Q10 guard giữ lại LONG của anchor. Các enum đúng không chứng minh logic
action đúng hoặc điều kiện mua tương lai đã xảy ra. Receipt không sai khi
ghi fact-check PASS: checker chỉ kiểm citation/enum, không kiểm toàn ngữ nghĩa.

Trong [renderer v3](../../../core/mt_bicl_v3_decision.py), `build_anchored_prompt`
lấy phần reports từ legacy, thay đầu prompt, hướng dẫn và schema. So với
[compact prompt gốc](../../../agents/decision_agent.py), chuỗi `CONTRACT`
mới giữ lịch/phí nhưng không còn nguyên câu “nếu không đủ bù phí ... chọn
SHORT”; `PRIORITY` cũng rút gọn. Đây là thay đổi xác nhận được từ source.
Chưa có ablation để kết luận riêng câu bị bỏ gây toàn bộ 35 LONG mới;
schema, salience của facts và phản hồi LLM đều có thể góp phần.

### 22.3. Đối chiếu paper với implementation

[Paper §4, §5.2 và §5.5](https://arxiv.org/html/2606.20538v1) học dự báo
`p(y_query | x_query, C_target, D_prior)`: task có latent riêng, prior tasks
cung cấp thông tin về phân phối latent; loss đặt trên target. Thử nghiệm
ERA5 cũng học từ dữ liệu thực. Paper báo cả tình huống shift mà thêm prior
làm kém; không bảo đảm lợi ích trên mọi miền.
[Mã huấn luyện tác giả](https://raw.githubusercontent.com/martianmartina/multi-task-bayesian-icl/main/src/train_multi_task.py)
chọn data module linear/logistic và checkpoint theo validation loss, không
huấn luyện một hosted chat LLM bằng cách chèn xác suất vào prompt.

Các hàng dưới là **đánh giá implementation của khóa luận**, không là yêu
cầu phải sao chép mọi kích thước/optimizer của paper:

| Thành phần trong hệ thống | Phần hợp lý | Phần chưa phù hợp cần thay |
| --- | --- | --- |
| Prior tasks riêng, target riêng, che query y, causal mask | Giữ cấu trúc học theo context và PIT | Không đủ nếu likelihood không dùng x_query |
| `BetaBernoulliTeacher.predict` | Posterior count có thể đúng toán dưới mô hình đã chọn | Bốn feature chỉ được validate; thay x nhưng giữ count không đổi teacher p. Learner được thưởng khi bỏ qua thông tin giá |
| `BetaTaskSimulator` + soft query loss | Cách kiểm distillation có thể tái lập | Nhãn được lấy bằng Bernoulli(θ_task) độc lập feature; dữ liệu thật chỉ fit π và cung cấp x, không dạy quan hệ x→y |
| Task mã×63 phiên, K≤3, M/m≤8 | Dễ kiểm lineage/cutoff | Chưa chứng minh task cùng phân phối prior; bucket hai dấu mất độ lớn tín hiệu, làm support thưa; không được coi block63 là latent thật |
| Utility θ×gain−(1−θ)×loss | Dùng đúng payoff sau phí | Pool magnitude qua task và giả định tách sign/magnitude có thể che khác biệt thị trường; posterior toán đúng không khắc phục sai mô hình |
| Student p + chat LLM + teacher veto | Có đối chứng từng nhánh và log raw/final | Ba bộ ra quyết định không cùng mục tiêu; p_student không quyết định U, action còn phụ thuộc một anchor mới |
| Assertion schema | Bắt sai số/enum và giữ JSON hợp lệ | Chép lại đúng facts không kiểm được “mua có điều kiện” hay cách tổng hợp bằng chứng; không thay validation kinh tế |
| Synthetic PASS → development | Phân biệt được approximation error | Thiếu cổng kiểm tín hiệu có điều kiện trên dữ liệu thị trường trước khi chi phí API tăng |

Retrieval hiện tại **có** dùng feature/regime, nên toàn pipeline vẫn điều
kiện hóa gián tiếp qua membership. Điểm thiếu ở đây là likelihood và
learner không học quan hệ x_query→return khi D/C cố định; không khẳng
định mọi phương pháp đếm có retrieval đều vô ích. Tác hại của từng yếu
tố cần được tách bằng ablation, không suy nhân quả từ một bảng return.

Nguồn đọc: [teacher](../../../core/mt_bicl_v2_teacher.py),
[simulator](../../../core/mt_bicl_v2_simulator.py),
[student](../../../core/mt_bicl_v2_student.py),
[utility](../../../core/mt_bicl_v3_utility.py),
[policy](../../../core/mt_bicl_v3_policy.py),
[bucket](../../../core/mt_bicl_v3_features.py).
Khác paper không tự động là lỗi; nhưng bỏ sự phụ thuộc x→y làm nhiệm vụ học
khác mục tiêu lựa chọn giao dịch. Ngược lại, thay sang regression tùy ý như
oracle v1/NIG cũ cũng không đủ: phải kiểm mô hình trên thị trường trước.

### 22.4. Hướng v4: learner dự báo có điều kiện, Original làm quyết định nền

Tên làm việc: **Conditional MT-BICL Advisor**. Candidate duy nhất là
`Full_conditional_MT`; chưa có code, weights, protocol JSON hoặc release v4.

Luồng dự kiến:

    upstream PIT chạy một lần → Original durable a0
                  ↓                  ↓
        numeric/agent features + prior tasks + target context
                  ↓
        learner v4 → predictive net return → calibration/policy đã khóa
                  ↓
        final action + reason/provenance; thiếu support → đúng a0

**A. Dữ liệu mang thông tin mà hệ thống đang sử dụng.**

- Nhãn gốc luôn là `r_net` của `compute_round_trip_net_return`; y_sign được
  suy từ r_net>0. Giữ Open(t+1)/Close(t+3), SHORT=CASH, chi phí hai chiều,
  vốn/account hiện tại. Không thay label bằng đúng/sai lời giải thích.
- X thị trường liên tục: momentum/volatility/volume tương đối, khoảng cách
  SMA và MACD−Signal đã chuẩn hóa, trạng thái thị trường/regime PIT.
  X agent: hướng Trend/Pattern, mức đồng thuận alpha, xung đột và a0;
  chỉ lấy structured output hoặc parser xác minh từ report thật. Confidence
  “Cao” là category, không tự đổi thành xác suất0,8.
- W11-18 kiểm coverage trước. Historical agent reports thiếu phải được
  tạo từ snapshot PIT với model/prompt khóa, upstream một lần/point rồi
  dùng chung; người dùng chạy API. Không suy agent feature từ r_net hoặc
  dùng LLM đọc giá tương lai để viết lại báo cáo. Model weights hosted
  có tri thức hậu kỳ là giới hạn của benchmark hồi cứu, phải công bố.
- Tập price-only dùng để kiểm tín hiệu trước; candidate có agent features
  chỉ được khóa khi dữ liệu lịch sử đó tồn tại. Thiếu đầu vào lúc inference
  giữ a0 và reason, không âm thầm thay model hoặc bỏ query khỏi G.
- Chọn universe/calendar/nguồn giá, xử lý quyền và survivorship trước
  labels đánh giá; có thể mở rộng lịch sử hoặc mã theo coverage, không chọn
  mã thắng. Vẫn báo riêng bốn mã FPT/MWG/VCB/VNM để nối với hệ thống gốc.
  Báo số cycle/task/ngày thực sự duy nhất và overlap; sinh nhiều episode
  từ cùng bank không làm tăng số quan sát thị trường độc lập. Dùng learning
  curve trên train/OOF để chọn capacity và nhu cầu thêm dữ liệu, không sao
  chép quy mô transformer của paper vào bank nhỏ rồi kỳ vọng tự tổng quát.

**B. Task và retrieval nhất quán giữa train và test.**

- Bắt đầu từ mã×block63 không chồng lấn để có đối chứng với bank cũ;
  block length là hyperparameter thiết kế, không khẳng định stationary.
  Các task chỉ chia sẻ meta-prior có điều kiện theo regime/đặc trưng thị
  trường; kiểm bằng posterior predictive và held-out task performance.
  Prior mặc định từ lịch sử cùng mã như `TaskBuilder` hiện tại; borrowing
  khác mã chỉ là cấu hình đăng ký riêng sau kiểm shared-prior, không tự
  trộn để đạt K. Dữ liệu pooled để fit hyper-prior vẫn báo theo mã/regime.
- Bỏ lọc cứng theo hai dấu và điều kiện phải có5 thắng/5 thua. Dùng x liên
  tục, khoảng cách/regime mềm theo tham số fit train; không cần hai dấu
  outcome cùng hiện diện mới dự báo. Missing/OOD được quyết định bằng
  provenance, miền feature và support đã khóa, không bằng nhãn query.
- D/C không trùng episode; prior task không là target task; mọi cycle
  phải exit<query. Train query cũng phải tuân thủ đúng cutoff này. Giữ
  timestamp, ID, missing mask, source hash và metadata regime từng prefix.
- Dự kiến train hỗn hợp K∈{0,1,3,5,8}, M≤32, m≤32; runtime không dùng độ dài
  ngoài miền đã train. Chọn membership theo rule không dùng y/r_net. Nếu
  dữ liệu không đủ, dùng K/m nhỏ đã train và báo support, không lặp mẫu.
  Giới hạn numeric context này độc lập BRPP: không ép toàn input learner
  vào600 ký tự. Card giải thích vẫn BRPP≤600, prompt Decision<6.500.

**C. Likelihood phải dùng x và dự báo độ lớn return.**

Đề xuất reference phân cấp, cần kiểm và khóa ở W11-17/19:

    λ ~ hyper-prior fit chỉ trên train
    (w_task, σ_task) | λ, regime ~ prior có shrinkage
    r_net | x, w_task, σ_task ~ Student-t(ν, w_taskᵀφ(x), σ_task)
    q(r_query | x_query, C, D) = tích phân posterior theo λ và latent task

φ(x) ban đầu là feature chuẩn hóa + intercept; không mở mạng feature lớn
trước khi baseline tuyến tính có tín hiệu. Student-t là thích ứng của đề
tài cho return, không phải kết luận của paper. Đây là **regression có
điều kiện và partial pooling**, khác NIG mean-return không điều kiện đã
FAIL. Không lấy U v3 hoặc một oracle ngẫu nhiên làm truth thị trường.

W11-19 so với zero-return, pooled ridge/probabilistic regression, mô hình
target-only và reference phân cấp trên cùng X/cohort. Reference inference
cần đối soát scalar/conjugate fixture; với MCMC báo convergence/ESS và
Monte Carlo error, không chỉ số draw. Không gọi reference là oracle của
thị trường. Nếu không có tín hiệu OOF ngoài baseline thì sửa dữ liệu/task/
likelihood bằng revision có ghi nhận trước, chưa chạy thêm ma trận LLM.
Một baseline phi tuyến nhỏ có thể nằm trong registry để phân biệt quan hệ
phi tuyến với thiếu tín hiệu; linear/reference thất bại không chứng minh
mọi learner đều không thể học. Không chọn oracle vì dễ đạt KL synthetic.

**D. Meta-training đúng bài toán dự báo; tách cơ chế và chất lượng thị trường.**

- Learner nhỏ học `(D_prior, C_target, x_query) → q(r_net)` với marker task,
  causal mask và loss chỉ trên target query/prefix có label đã che. Đề xuất
  head mixture Student-t với mean/scale/weights hợp lệ để biểu diễn PPD;
  không chỉ distill một xác suất count. Kiến trúc/head/miền độ dài khóa
  trước train; tăng capacity phải là cấu hình đăng ký, không đổi sau test.
- Dùng episode thị trường thật để học NLL target. Synthetic có quan hệ x→r
  dùng kiểm cơ chế/pretraining theo meta-prior fit train; không dùng x thật
  ghép nhãn ngẫu nhiên độc lập x. Pretraining/real-data adaptation và mọi
  loss weight phải được khai báo; không coi fine-tuning là thích ứng không
  gradient tại test-time. Khi test chỉ conditioning, weights giữ nguyên.
- Kiểm có can thiệp: giữ D/C đổi x_query; giữ x/C đổi prior; tăng target
  evidence; phá ranh giới task thành pooled; prior không liên quan; hoán vị
  thứ tự prior và shift regime. So response với reference trên synthetic
  biết mô hình, không đòi mọi feature change đều phải đổi action.
- Thực nghiệm thị trường báo NLL/CRPS, calibration xác suất r>0, MAE,
  coverage kèm độ rộng interval, riêng từng regime/mã/fold. Phân biệt
  predictive interval của return với bất định về mean; không lấy Q10
  predictive return làm CI của expected utility.
- Chọn checkpoint bằng rolling validation; báo tất cả seed, không chọn
  seed thắng2023. Ít nhất ba fold có purge theo thời điểm nhãn hoàn tất,
  scaler/prior/feature selection fit phần train từng fold. ≤2022 đã xem
  vẫn là development OOF, không đổi tên thành xác nhận độc lập. 2023 là
  stress/development đã exposed; không dùng để chọn hyperparameter v4.

**E. Tích hợp không thay quyết định nền và không giao lại số học cho LLM.**

- a0 là response Original durable, giữ nguyên prompt/schema/model/options.
  Không có Fact_Anchor mới trong đường candidate. Bayesian OFF hoặc đầu
  vào không hợp lệ theo policy phải bằng đúng Original trên100% point.
  Lỗi API/integrity/PIT vẫn raise/checkpoint, không chuyển thành fallback.
- Learner tạo phân phối return; từ đó lấy mean net μ và xác suất r>0 từ
  cùng một phân phối. Calibration dùng OOF; không ghép p của model này với
  magnitude bootstrap của model khác rồi gọi đó là output learner.
- Policy sửa action dự kiến: `ΔEU(a,a0)=(I[a=LONG]−I[a0=LONG])*μ_net`.
  Chỉ sửa khi ΔEU vượt biên h≥0 đã chọn trong inner OOF, support/OOD hợp
  lệ và kiểm rủi ro đạt. h là tolerance quyết định, không trừ phí lần nữa.
  Bắt đầu bằng đối chứng h=0; nếu dùng vùng giữ a0 thì chọn theo regret/
  risk OOF trong registry hữu hạn, không dựa năm ca hoặc return2023.
- Bỏ Q10-veto v3 ở revision mới vì chưa được calibration cho quyết định;
  không sửa ngưỡng/kết quả v3. Báo lợi ích và chi phí cơ hội của cả hai
  chiều sửa, tỷ lệ giữ a0, OOD, missing và độ nhạy calibration.
- Không gọi LLM thứ hai để tạo raw action mới rồi “cứu” bằng veto. Card
  bằng chứng chỉ giải thích action đã tính; nếu cần LLM diễn giải, trường
  action không được đổi. Tín hiệu “mua nếu vượt...” không được thực thi
  thành LONG vô điều kiện. Hợp đồng P&L và vốn không thay đổi.

### 22.5. Ma trận kiểm đóng góp, điều kiện đi tiếp và hạn chế claim

Trọng tâm của paper là **learner học từ prior/target**, không phải số ví dụ
văn bản trong prompt chat. Vì vậy K=0/pooled là đối chứng chính của cơ chế;
Plain_ICL vẫn hữu ích cho so hệ thống nhưng không thay được các đối chứng đó.

| Nhánh/kiểm định v4 | Nội dung khóa trước run | Mục đích |
| --- | --- | --- |
| Original | Response legacy, nguồn a0 dùng chung | Hiệu quả tăng thêm toàn hệ thống |
| A_reference | Phương pháp W9, cùng upstream/cohort mới | So phương pháp có bằng chứng trước |
| Plain_ICL | Legacy prompt + context cùng membership, không numeric learner | So ICL văn bản; cùng giới hạn prompt |
| Full_conditional_MT | Learner đầy đủ + a0 + policy đã khóa | Candidate duy nhất |
| Target_only_K0 | Learner cùng capacity được train K=0; cùng X/C/policy | Đóng góp prior tasks; không chỉ cắt prefix gây OOD |
| Pooled_context | Cùng observations nhưng bỏ ranh giới prior/target, train tương ứng | Đóng góp cấu trúc phân cấp |
| No_target | Full learner C rỗng trong miền đã train; recompute distribution | Đóng góp target evidence |
| No_agent_features | X giá/regime, bỏ agent features ở train và test; cùng a0 | Giá trị thông tin agent ngoài action nền |
| Numerical_MT | Full distribution, policy net thuần không dùng a0 | Phần lợi ích có cần quyết định nền đa agent? |
| Hierarchical_reference | Reference phân cấp trên cùng input; cùng policy | Approximation/speed, không candidate thay thế |

Kiểm off=Original là kiểm hợp đồng, không cần nhánh LLM độc lập. Forecast
ablations chạy numeric trên cùng baseline durable; không nhân số API theo
số model. Không trộn return của các nhánh đã chạy ở các phiên khác nhau.
Nếu nhánh có feature thiếu, giữ query và fallback như protocol; báo common
support bổ sung, không chọn giao điểm thuận lợi thay estimand toàn cohort.

**Tiêu chí trước chi phí tích hợp:** W11-19/21 phải có predictive signal
OOF hơn baseline và bằng chứng prefix/target giúp trên các fold giữ thời
gian. Khóa metric chính CRPS, báo NLL/calibration và return decision song
song; chọn bằng inner folds, đánh giá outer folds. Không gọi đây là test
độc lập. Nếu learner chỉ khớp oracle nhưng không cải thiện dữ liệu thật,
ghi đúng điểm nghẽn và nghiên cứu lại foundation trước API development.

Đề xuất khóa ở17: ít nhất ba outer fold; tính CRPS theo mean đều ngày/mã,
baseline thắng được xác định chỉ bằng inner folds. Mô hình có điều kiện
phải giảm CRPS tổng OOF so baseline được chọn và cải thiện ở đa số outer
fold, không chỉ một regime. Trước22, Full learner còn phải hơn K0/pooled
theo cùng quy tắc và policy có Δreturn OOF dương so Original với guard
rủi ro đã khóa. Báo mọi fold/calibration/coverage và bất định; đây là
tiêu chí phát triển mới, chưa là bằng chứng xác nhận hoặc bảo đảm power.
Purge dựa trên khoảng entry–exit chồng lên fold đánh giá, không chỉ chia
theo ngày as_of; dữ liệu context mature tại mỗi query vẫn được dùng theo
PIT đã khóa, không đưa nhãn chưa hoàn tất vào feature/scaler/fit.

**Nomination v4 đề xuất, phải khóa tại17:** đủ G/integrity, D Full−Original>0,
≥3/4 mã cũ tăng, Full−A≥0, mean ΔMDD≤2 và max≤5 đpt; thêm D Full−K0>0 và
Full−pooled>0 trên development đã khóa để không nominate một mô hình có
gain nhưng chưa thấy lợi ích multi-task. Full−Fact_Anchor không còn là gate
vì anchor đó không thuộc candidate mới. Đây là rule mới trước v4, không
đổi kết quả NOT_NOMINATED v3. W12 mới kiểm claim bằng CI độc lập; mục tiêu
“rõ rệt” vẫn D≥1 đpt, CI95% primary>0, phân tán/rủi ro đạt trên cohort khóa.

W11-23 có repeat định trước theo strata và cả hai chiều action nền; giữ
Original_duplicate độc lập để đo noise. Không vote, không tăng N theo seed/
repeat, không tái chọn candidate bằng kết quả tốt nhất. W11-24 phân rã
Original→forecast policy→fallback/calibration, không dùng raw proposal v3
để tính “v4 giả lập”: raw v3 đã condition trên anchor khác.

### 22.6. Đầu ra theo task và nghiệm thu

| Task | Artifact dự kiến khi thực hiện sau này | Điều kiện hoàn tất |
| --- | --- | --- |
| 17 | Protocol v4 trong W11: data/exposure, task/X/y, registry, folds, metrics, policy, test/matrix | Không còn tham số quyết định kết quả được chọn sau mở cohort; source/baseline binding rõ |
| 18 | Dataset/feature/task manifest, PIT provenance, coverage/missing/overlap và drift audit | Không fabricated agent data; đủ fold, mọi train/target/query cutoff hợp lệ |
| 19 | Baseline/reference OOF report và posterior predictive checks | Tách model misspecification khỏi inference error; ghi cả failure, đủ tín hiệu mới sang20 |
| 20 | Learner weights/training manifest, seed/checkpoint và synthetic mechanism report | Query mask/target loss/PIT đúng; feature/prior/target interventions có oracle đối chiếu |
| 21 | OOF calibration/ablation/policy report, một candidate khóa | Prefix/target có giá trị, support/OOD/fallback rõ; không chọn bằng2023/holdout |
| 22 | Adapter/shadow receipt, new namespace/source/manifest và release development | off=Original; không thay engine/base prompt; P0 và test caller/leakage áp dụng PASS |
| 23 | Paired development đủ cohort/matrix/repeat, raw/cache/ledger | Người dùng chạy API; no missing/unknown, không lọc ca xấu |
| 24 | Cold accounts, decomposition, nomination và claim boundary | Đối chiếu independent consumer; NOT_NOMINATED nếu không đủ rule, không promote ablation |
| 25 | Handoff source/weights/data/exposure và trạng thái cho W12 | Nominate mới mở release xác nhận; thất bại có diagnosis, không chạy lại tới khi thắng |

Không có task nào dừng do hết giờ hoặc ngày chót. Early stopping theo
validation/convergence, registry hữu hạn và cỡ mẫu khóa để tránh chọn lọc
kết quả vẫn cần. Nếu revision v4 thất bại, chỉ mở revision tiếp với giả
thuyết và exposure cập nhật; không sử dụng holdout đã mở như holdout mới.
Nguồn phương pháp mới phải ở namespace riêng, không sửa receipt/source
v1–v3; các yêu cầu triển khai ở bảng này **chưa thực hiện trong lượt hiện tại**.

### 22.7. Kiểm tra tài liệu và bằng chứng

Nguồn chính: v3 report SHA `ac92ebe91c62e76e3d05668c5d72b85dded6c125e25bc8abad444a90e87ad3d9`,
accounts SHA `4ecc5a30061013232b5e4098bacc1643e02786bebc1ff3003ea73c57eaa38120`,
nomination SHA `aeb0bb41fc54b33fb152145ddf48a1773a4017e460fbfd2a549bae26b49897d0`.
Baseline ledger5.206 row SHA `b89c5f7eff547a73f44136e5b60372c0ce5b9680fc47a02eddde13a42fd1e956`.
Đối soát diff, link/anchor, checklist, số liệu và hash nguồn trước/sau;
theo AGENTS.md1.2 không chạy unit/compileall/E2E/leakage suite cho task chỉ
sửa tài liệu. Không viện dẫn77 test cũ thành test mới hoặc tuyên bố v4 PASS.

QA tài liệu:146 link/anchor nội bộ, UTF-8, số task, phép tính CI secondary,
decomposition và số point fallback đều PASS. Chỉ ba Markdown thay đổi.
Hash trước/sau của2.597 file v2 và3.684 file v3 giữ nguyên (loại metadata
OS lock); aggregate v3 `8ec3f9888b46bb0056af52119a5db9b58d54d8b6717c67d163bcc094b0815454`.
Protocol/runtime policy/nomination JSON và ledger giữ nguyên byte.

## 23. W11-17 — Khóa protocol Conditional MT-BICL v4 (31/10/2026)

**DONE / SPEC_LOCK_PASS**. [Protocol máy](protocol_v4.json),
[đặc tả phương pháp](conditional_advisor_v4.md) và
[receipt khóa nguồn](protocol_lock_v4.json) xác định thiết kế trước dataset/
fit/run v4. Candidate duy nhất `Full_conditional_MT`, Original durable làm
nền; namespace mới `outputs/bayesian_benchmark/mt_bicl_v4/`. Chưa cấp quyền
train, fit reference, gọi Decision/development hoặc xác nhận. Không có
trần giờ, deadline lịch, counter elapsed hay crash-gap charge cho v4.

- Khóa universe bốn mã, feature numeric liên tục và agent category có
  provenance thật, nhãn net engine; D/C/query disjoint, exit<query, cùng
  mã×block63, selection không dùng label. Không dùng bucket/sign-count
  support của v3; missing/OOD giữ a0 và vẫn giữ point trong G.
- Ba outer2020/2021/2022; cutoff weights2019/2020/2020. Inner2019H1/H2
  hoặc2020H1/H2 chọn cấu hình, checkpoint/calibration/h. Final chỉ chọn
  inner2020, weights≤2020; **làm rõ và thay đề xuất chọn checkpoint2021
  tại mục22**. 2021/2022 chỉ report/gate outer,2023 chỉ stress/development.
- Registry baseline, reference regression Student-t phân cấp, Gibbs
  diagnostics, hai capacity learner/ba seed, head/loss/mask, synthetic
  interventions và policy đã cụ thể trong JSON. W11-19/21 phải có signal
  CRPS OOF ngoài baseline/K0/pooled/No_target trước tích hợp; không coi
  oracle/synthetic PASS là bằng chứng kinh tế.
- Distribution→calibration→mean/p(r>0) thống nhất; thay action chỉ khi
  ΔEU>h chọn inner, không trừ thêm phí hoặc dùng Q10-veto. OFF=a0 100%;
  lỗi integrity/PIT/API raise/checkpoint. P&L, vốn và fractional shares
  giữ hợp đồng account đã nghiệm thu.
- G2023 giữ60 ID (FPT12/MWG16/VCB16/VNM16),10 nhánh:600 primary +396
  repeat/duplicate=996 dòng action;180+144=324 slot LLM danh nghĩa, chỉ
  Original/A_reference/Plain_ICL cần LLM. Control/retry tính riêng. W11-22
  vật hóa12 repeat ID bằng rule strata/hướng a0 lịch sử đã khóa trước
  response v4 đầu; không dùng a0/anchor/raw v3 làm baseline v4.
- Nomination Full: đủ G/integrity, D−Original>0,≥3/4 mã tăng, D−A≥0,
  D−K0>0, D−pooled>0, mean ΔMDD≤2/max≤5 đpt. Chỉ một candidate, không
  vote repeat/promote ablation. W12 vẫn0/8, chưa release hoặc mở payoff2025;
  N/block-length chờ audit/power W12, family8 secondary CI99,375% đã khóa.

Nguồn spec/verifier/test commit `a6cd8b71822bde2eeea74dafeef98a51542bbd7b`.
Protocol SHA `ce868c6373548b207bc6d7d0a03bdb2c291bbcb95f47f0f33e3a3918cc8ccdf9`;
receipt SHA `493559d45f4cd80c23439025b3e5addf880a073f7f81c1f697e8373c48b22908`.
Binding gồm8 parent artifact,18 baseline source và15 file nguồn; runtime
Python3.13.5/các package đã ghim khớp. Prefix ledger5.206 request giữ nguyên,
cho append sau này, không sửa/reset; byte SHA vẫn
`b89c5f7eff547a73f44136e5b60372c0ce5b9680fc47a02eddde13a42fd1e956`.
Plan gốc lấy object Git `78337a4`, không hash README tiến độ mutable.

Kiểm tra theo AGENTS.md1.2: **24 test mới PASS** (15 protocol/receipt và9
metadata PIT/purge), bốn Python mới `py_compile` PASS; freeze và cold replay
Git/source/runtime/parent/input/ledger PASS, network bị chặn. Các fixture
metadata chưa thay kiểm dataset/model/inference v4. Không đổi caller legacy
hoặc đường dữ liệu đang chạy nên không chạy lại toàn unit suite, compileall,
E2E hoặc viện dẫn gate v3 thành gate v4. Diff/link/checklist/hash được đối
soát; không train, forward model hoặc gọi API. W11-18–25 vẫn TODO.
QA tài liệu:154 link/anchor nội bộ và checklist15 DONE/2 NOT_RUN/8 TODO
PASS. Cây v2 2.597 file khớp snapshot nomination; v3 đủ804 slot/687 raw
cache khớp hash nghiệm thu, progress/source analysis/counter cũ giữ byte.

```powershell
py -3.13 -X utf8 scripts/verify_mt_bicl_protocol_v4.py
```

Lệnh chỉ tái kiểm `SPEC_LOCK_PASS`, không chạy dataset/train/API. Bước tiếp
theo **W11-18** xây manifest dữ liệu và audit coverage/PIT; thiếu agent thật
hoặc support không đạt thì báo `INSUFFICIENT_DATA`, không tự thay cấu hình
đã khóa hoặc mở cohort xác nhận.

## 24. W11-18 — Dataset PIT và thiếu hụt đầu vào agent (01/11/2026)

**IN_PROGRESS / INSUFFICIENT_DATA — chưa nghiệm thu W11-18, chưa mở W11-19.**
Công cụ dữ liệu offline đã triển khai/kiểm và snapshot đã khóa bằng
[manifest](dataset_manifest_v4.json), [coverage](coverage_v4.json).
PASS kỹ thuật không được đổi thành DATA_READY_PASS: cả40 check thiếu
agent support vẫn FAIL theo đúng protocol W11-17, không nới ngưỡng.

Nguồn tool/test commit `8d01634fc4f1ec6c3ec103be501f16a54870e848`.
Namespace `outputs/bayesian_benchmark/mt_bicl_v4/data/` có observations,
labels sidecar riêng,7 fold outer/inner, train prefix scaler/membership,
7 artifact regime và danh sách thiếu đầu vào `agent_requirements.json`.
Manifest ràng buộc8 source mới,15 nguồn giá đã khóa,1.705 file cache/
episode/manifest lịch sử và14 artifact dữ liệu/coverage/regime. Receipt
đã commit, cold replay đối chiếu object Git, không chấp nhận tự reseal.

| Bằng chứng | Kết quả |
| --- | --- |
| Grid query2018–2022 | 1.640,410/mã; giữ missing X và mọi lý do không thể gán nhãn |
| Nhãn net có thể kiểm toán | 1.523: FPT376/MWG382/VCB385/VNM380; đúng engine Open(t+1)/Close(t+3), phí hai chiều |
| Cycle có nhãn và đủ9 numeric | 888; không coi chúng là cohort độc lập mới |
| Task mã×block63 | 80 task có≥2 cycle có nhãn |
| Báo cáo agent lịch sử thật | 852; giữ hash raw report, episode cross-binding, PIT giá/tin và parser/factor proof |
| Cycle đủ đầu vào Full | 0; thiếu Original durable trong nguồn lịch sử đã khảo sát |
| Query có<600 nến Alpha | 772; phiên grid đầu đủ600 là01/06/2020 cho cả4 mã |
| Query thiếu report lịch sử | 788; không bịa report hoặc suy signal từ label |
| Cache chưa chứng minh tương thích mã prompt khóa | 852; SHA nguồn4 agent khác baseline, không tự coi thay code là cùng request |
| Report Trend parser hiện tại không đọc được | 3; giữ raw/UNKNOWN/reason, không lấy nhãn có sẵn thay parser |

Numeric tính rolling vector hóa theo công thức v4, sample std ddof1,
MACD12/26/9 riêng prefix45. Barrier giá thô/quyền được kiểm theo cửa sổ
feature;684 query có reason corporate-action feature window,32 thiếu
prefix45. Đây là lý do thiếu X, không xóa query khỏi grid. Tổng888 là
**joint numeric + label hợp lệ**; không đồng nhất với1.523 nhãn khả dụng.
Các lý do label riêng:26 holding qua quyền,76 qua block,16 qua năm,
có giao nhau; không cộng reason thành số cycle loại.

Mỗi fold có scaler train riêng; train query dùng scaler prefix trước
query, không dùng scaler cuối2020 cho2018/2019. D/C chọn bằng numeric/
regime trước khi dùng sidecar label, cùng mã, disjoint IDs/entry–exit và
exit<query. Đã audit2.644 context/membership (gồm lặp qua fold/prefix),
không tính chúng thành2.644 quan sát thị trường độc lập. Báo K/m, regime,
missing và standardized drift từng fold/mã trong coverage.

Regime là feature: fit đúng7 prefix≤2020 trong namespace mới; thiếu499
phiên trả UNKNOWN. Cold replay chỉ load tham số/training hash đã khóa,
**không refit**. Chưa fit Bayesian reference, learner, calibration hoặc
policy; không tính P&L/accuracy để chọn thiết kế. Không mở outcome2023/2025.

**Thiếu hụt phải xử lý trước nghiệm thu:**

1. Warmup Alpha là ràng buộc cấu trúc: nguồn hiện tại bắt đầu02/01/2018,
   nên chạy thêm API trên cùng nguồn cũng không tạo được agent cho các
   inner sớm. Cần source/exposure amendment riêng để bổ sung giá thực thi
   thô trước2018 chỉ cho warmup, giữ nhãn/train/evaluation trong miền đã
   đăng ký. Tại grid query đầu, cần thêm ít nhất579 phiên trước neo để
   đạt600 nến. Không ghi đè nguồn/receipt cũ hoặc tự lùi split/cutoff.
2. Audit tương đương canonical input/prompt của852 report trước khi reuse;
   nếu không chứng minh được thì tạo report mới từ snapshot PIT theo model/
   prompt/options đã khóa. Có source SHA khác chưa chứng minh chính nội
   dung prompt đã đổi, nhưng cũng chưa đủ bằng chứng cho phép reuse.
3. Bổ sung Original durable và report còn thiếu qua lượt thu thập **do
   người dùng chạy**, với release collection riêng, raw/UUID/ledger,
   upstream một lần/point và resume. Snapshot này chưa cấp API collection
   hoặc train; `agent_requirements.json` chỉ là danh sách thiếu, không phải
   response hay release giả. Sau bổ sung, cần snapshot/revision dữ liệu
   mới giữ nguyên bản thiếu hụt này, và kiểm lại mọi gate support.

**Kiểm tra theo phạm vi:**77 test PASS =26 dữ liệu mới +24 protocol v4
+19 execution-price +8 regime-leakage; tám Python mới `py_compile` PASS.
QA độc lập trên1.640 row/1.523 label/2.644 membership kiểm lịch t+1/t+3,
công thức scalar bốn hệ số phí/slippage, y_sign, purge, scaler prefix và
D/C overlap PASS. Cold rebuild X/label/fold/lineage/coverage byte-identical,
chỉ load regime, không network. Không đổi caller/runtime legacy nên không
chạy toàn unit suite/compileall/E2E. Merge công cụ audit có kiểm kỹ thuật
PASS; **không phải merge candidate/release hoặc nghiệm thu dữ liệu đầy đủ**.
QA158 link/anchor, checklist15 DONE/2 NOT_RUN/1 IN_PROGRESS/7 TODO và
hash trước/sau1.705 input agent cùng14 artifact đều PASS.

Manifest SHA `1d0681a7e0af1140748f3753568ab9b28cb8c1eb007e071dc51cc25e135293ee`;
coverage SHA `c93cdc845691f5e35f4109f20a5deb12e1abb3e903acb397602a2bbe82bbc7fe`.
Protocol v4 SHA vẫn `ce868c6373548b207bc6d7d0a03bdb2c291bbcb95f47f0f33e3a3918cc8ccdf9`;
lock spec `493559d45f4cd80c23439025b3e5addf880a073f7f81c1f697e8373c48b22908`.
Ledger vẫn5.206 request, byte SHA
`b89c5f7eff547a73f44136e5b60372c0ce5b9680fc47a02eddde13a42fd1e956`;
không có API mới, không ghi counter/nguồn/bằng chứng v1–v3.

```powershell
py -3.13 -X utf8 scripts/prepare_mt_bicl_v4_data.py --verify-only
```

Lệnh chỉ cold audit snapshot hiện tại và vẫn báo `INSUFFICIENT_DATA`;
chạy lại không tạo agent/a0 còn thiếu. W11 giữ15/25 DONE, W12 giữ0/8.

## 25. W11-18 — Release bổ sung warmup/agent/Original (01/11/2026)

**Phạm vi vận hành cũ:** release dưới đây vẫn khóa1.640 điểm. Kế hoạch
rút gọn mới ở mục26 chưa được triển khai; không dùng lệnh này như runner256.

**IN_PROGRESS — công cụ/release đã sẵn sàng; chờ thu thập thật và cold nghiệm
thu dữ liệu.** Chỉ đạo hoàn thiện W11-18 cho phép bổ sung nguồn warmup và
thu thập agent/Original trong miền đã đăng ký. [Release collection](data_completion_release_v4.json)
khóa source `49787ce1d504dcda4aa4036b561b9eda9d4f9e23`,8 source mới,
37 dependency,3 receipt cha và4 snapshot tin. SHA release:
`e4420086d6c16d0d46332c22283f762f061b6dd18ad9bfb844c2787d23f25004`.
Release chỉ cho **người dùng** tải warmup và chạy collection2018–2022;
không cấp train/reference fit, development2023 hoặc confirmation2025.
Protocol/receipt/snapshot đầu và bằng chứng v1–v3 giữ nguyên byte.

Hai điểm đã xử lý trước khi gọi API:

- Coverage agent được tính riêng trên cycle có nhãn hợp lệ, không phụ thuộc
  việc numeric cũng đầy đủ. Báo thêm joint numeric+agent; ngưỡng agent70%
  và mọi ngưỡng support theo fold giữ nguyên. Missing numeric/reason vẫn
  giữ trên grid; không xóa query để làm tăng tỷ lệ. Bản coverage mục24 giữ
  nguyên làm bằng chứng lịch sử, revision mới dùng phép tính đã sửa.
- Audit AST của852 report chứng minh prompt/postprocessing4 agent tương
  đương sau khi loại đúng adapter retry đã biết. Tuy nhiên thiếu raw HTTP/
  options durable và Original nên **0 report đủ điều kiện tự reuse** cho
  release mới. Không kết luận prompt đổi chỉ vì SHA code khác; cache cũ
  được giữ, collection mới khóa canonical input/options và raw response.

Warmup lấy giá thực thi thô VCI từ01/01/2015 đến15/01/2018, cần ít nhất579
phiên trước neo02/01/2018. Toàn bộ hàng overlap trả về, tối thiểu5 hàng,
phải khớp OHLCV/Reference nguồn2018 đã khóa; sai nguồn/điều chỉnh giá thì
dừng trước LLM. Chỉ nối hàng trước neo, không ghi đè giá cũ. Warmup cung
cấp đủ600 nến Alpha và cửa sổ agent đầu kỳ; không thêm nhãn/query train
trước2018, không đổi numeric/scaler/context/label đã khóa. Mỗi mã tải xong
được lưu để resume; nguồn đã seal mất file hoặc đổi hash thì dừng đối soát.

**Lệnh người dùng chạy tại thư mục gốc repo:**

```powershell
py -3.13 -X utf8 scripts/continue_mt_bicl_v4_data.py
```

Lệnh tự kiểm release → tải/đối soát warmup → chuẩn bị tokenizer có kiểm
SHA →3 probe synthetic cho scope credential → thu thập1.640 point → audit
coverage revision mới. `GROQ_API_KEY` trong `.env` chỉ đọc khi còn cần HTTP
LLM sau bước replay cache. Không in key hoặc đọc key khi kiểm offline.
Indicator và Alpha/Full giữ đúng cách tính Python của baseline; Pattern,
Trend và Original gọi LLM, danh nghĩa4.920 lượt nghiên cứu, cộng probe và
retry thực tế. Không thêm lời gọi LLM vào agent vốn tính xác định.

Upstream lưu một lần/point, Original dùng deep-copy báo cáo đó với prior
rỗng; prompt/schema/model/options khóa trong release. Mọi lời gọi qua
wrapper retry, pacer/ledger chung và raw cache. Không phân tích P&L để
chọn lại cấu hình trong bước thu thập.

**Bị ngắt thì chạy lại đúng lệnh trên.** Point complete được xác minh và
bỏ qua; stage chưa xong replay durable cache trước khi đọc key/gọi HTTP,
giữ UUID, reserve và checkpoint. Đổi key có chủ ý tạo3 probe cho scope
mới, không sửa dòng ledger cũ. Hết quota thì chờ reset/backoff của provider,
có thể Ctrl+C rồi chạy lại; **không trần giờ hoặc deadline**. Nếu HTTP đã
thành công nhưng response chưa kịp lưu durable, resume có thể phát sinh
HTTP vật lý trùng với cùng UUID; giữ mọi bằng chứng cũ, không biến thành
repeat vote hoặc quan sát khoa học mới. Lỗi integrity phải đối soát, không
tự ghi đè bằng chứng để tiếp tục.

Raw/cache/probe/checkpoint nằm trong
`outputs/bayesian_benchmark/mt_bicl_v4/data_completion/`, gồm `warmup/`,
`http_cache/`, `controls/`, `resume_events/` và
`points/<point_id>/{stages,original,complete}.json`. Sau đủ1.640 point,
revision tại `outputs/bayesian_benchmark/mt_bicl_v4/data_r2/` có
`observations.json`, `coverage.json`, `manifest.json`; nhãn, fold và
lineage số học kế thừa snapshot gốc với hash ràng buộc. Không sửa namespace
`data/` đã khóa. Runner ghi `AWAITING_AGENT_COLD_ACCEPTANCE`; **không tự
đánh dấu W11-18 DONE hoặc mở W11-19** kể cả khi đủ point. Nếu support vẫn
thiếu thì giữ `INSUFFICIENT_DATA`, không hạ ngưỡng.

**Kiểm tra theo phạm vi:**85 test riêng biệt PASS theo nhóm:27 test mới
(coverage/warmup10, collection9, collection leakage8),58 hồi quy trực tiếp
(recovery10, transport5, execution-price12+leakage7, protocol15+leakage9).
Tám file Python mới biên dịch PASS. Test dùng HTTP giả và clock giả, kiểm
đường graph/SDK/pacer thực, retry cùng UUID sau gián đoạn, cache mất trước
seal, quota, đổi key, control lỗi, PIT và chạy lại toàn lệnh không đọc key.
Không đổi caller/runtime cũ; không chạy toàn unit suite/compileall/E2E
toàn hệ thống theo quy tắc kiểm tra phạm vi trong AGENTS.md.

```powershell
py -3.13 -X utf8 scripts/continue_mt_bicl_v4_data.py --verify-only
```

Kiểm offline release/source PASS, hiện trả `WAITING_USER_WARMUP_AND_API`;
chưa có tải warmup hoặc API thật trong lượt triển khai này. Ledger vẫn5.206
request, SHA `b89c5f7eff547a73f44136e5b60372c0ce5b9680fc47a02eddde13a42fd1e956`.
Sau khi người dùng chạy xong, cold kiểm raw/UUID/ledger/source/PIT và mọi
gate support mới quyết định DATA_READY_PASS/nghiệm thu. Checklist vẫn
15 DONE/2 NOT_RUN/1 IN_PROGRESS/7 TODO; W12 vẫn0/8. QA161 link/anchor,
checklist và6 hash receipt/ledger liên quan PASS; diff không lỗi khoảng trắng.

### Sửa probe và chẩn đoán HTTP400 sau lượt người dùng đầu tiên

Warmup đã tải/đối soát xong; ledger thêm đúng2 HTTP synthetic: text200 và
vision400 tại `CONTROL_V4_vision`, model `qwen/qwen3.8-27b`. Chưa có HTTP
nghiên cứu hoặc Original; point đầu chỉ có checkpoint chuẩn bị. HTTP400
là request bị provider từ chối; chưa có bằng chứng đây là lỗi quota/key.
Transport cũ chỉ giữ hash response lỗi, không giữ message nên **không thể
kết luận chính xác nguyên nhân400 cũ**. Ảnh synthetic8×8 là điểm đáng nghi;
model vẫn được Groq công bố hỗ trợ vision tại [tài liệu chính thức](https://console.groq.com/docs/vision).

Bản sửa source `599facd` có [amendment vận hành](data_collection_hotfix_v4.json)
riêng; không reseal release cha, không đổi model/options/request nghiên cứu,
identity collection, cohort, warmup hoặc trần giờ. `vision_r2` dùng PNG RGB
224×224 với intent synthetic mới; file/UUID probe8×8 cũ giữ nguyên. Text
đã PASS được tái kiểm raw/ledger và bỏ qua, không gọi lại. Không dùng cùng
UUID cho hai body ảnh khác nhau. UUID nghiên cứu chưa hoàn tất vẫn giữ.

Transport mới lưu code/type/param/message đã lọc credential/data URL/token
dài cùng body SHA, model, point và UUID tại `data_completion/http_errors/`,
đồng thời in dòng `[Provider HTTP ...]` trước khi pacer dừng. Không đổi body
HTTP, retry hoặc quota policy. Nếu còn400, cần đối chiếu thông báo provider
mới; không tự thử đổi model/key/options. Tiếp tục bằng đúng lệnh ở mục25.

Kiểm tra bản sửa:23 test PASS =6 test probe/diagnostic/amendment mới +9
collection +8 collection-leakage;5 Python thay đổi biên dịch PASS. HTTP
hoàn toàn giả lập; kiểm lỗi400 có bằng chứng, giữ nguyên probe/text/ledger
cũ khi chuyển sang ảnh224×224, không gọi lại complete, cùng UUID nghiên
cứu, quota, đổi scope credential, PIT và replay offline. Không chạy toàn
suite vì không sửa economics/PIT/runtime dùng chung. Gate85 test của bản
trước chỉ viện dẫn cho phần giữ nguyên, không coi là đã chạy lại toàn bộ.

Ledger thật sau triển khai vẫn5.208 dòng, byte SHA
`739cd0d6df421ef4e39f840cb896b05aab4509b0bb8883592692a0df4dfd2a60`.
Warmup seal SHA `fd4e649ed3ebe3b52bd0b03f9a2be15aa42a2977049e80b5595081e0a2b93cc4`;
identity SHA `f607ae46e4a22eb8b477d0768f5bded49b42a99c1eb6ba3e00b0602f46879263`.
Agent không đọc key/gọi API thật; W11-18 vẫn IN_PROGRESS chờ thu thập.
Amendment SHA `d989e04c5cfa111b93371630ff2bf86f7762e3da867944d9abf8e2f311f4846a`.
Kiểm `--verify-only` trên checkpoint thật PASS: bốn mã đều749 nến warmup
trước2018, overlap10 PASS; trả `WAITING_USER_API`,0 point complete. Không
đọc key hoặc gọi HTTP. QA162 link/anchor, checklist và5 hash release/
amendment/ledger/identity/warmup PASS; ledger và identity giữ nguyên byte.

## 26. W11-18 — Phương án 256 điểm LLM trong 3–5 ngày (01/11/2026)

**PLAN_ONLY — thay đổi thiết kế dự kiến, chưa đổi code/protocol máy hoặc
cấp release mới.** Người dùng xác nhận4 quota độc lập, khoảng20 điểm/key/
ngày, tổng80 điểm/ngày. Chỉ mục tiêu thời gian W11-18 được khôi phục theo
yêu cầu này; không áp deadline cho train, development hoặc xác nhận W12.
Không xóa dữ liệu/receipt cũ hoặc đổi trạng thái `INSUFFICIENT_DATA` bằng
tài liệu. Làm tuần tự18a–18f dưới đây rồi mới mở19–25.

### 26.1. Vì sao cần đổi thiết kế thu thập

Một điểm collection hiện có3 HTTP nghiên cứu: Pattern, Trend, Original;
Indicator và Alpha tính Python. Bốn key đã được tính trong80 điểm/ngày,
nên1.640/80=**20,5 ngày quota**, không thể chia thêm cho4 lần nữa. Tối ưu
chạy đồng thời chỉ giảm chờ, không giảm tổng quota cần dùng.

V4 ràng buộc agent X/a0 của **mọi observation D/C/query** với learner.
Vì vậy thiếu Original lịch sử làm nghẽn cả học dự báo, dù nhãn net và giá
đã có. Paper học predictive distribution từ datasets prior/target; không
đòi mỗi cặp (x,y) phải được tạo bằng hosted LLM. Tách dữ liệu học khỏi
quyết định nền LLM là một thích ứng của đề tài, vẫn cần kiểm cơ chế và
giá trị giao dịch. [Paper gốc](https://proceedings.mlr.press/v306/zhu26aj.html).

Audit chỉ đọc metadata/mask, không mở return để chọn mẫu, cho thấy:

| Dữ liệu snapshot v4 | Số lượng / ý nghĩa |
| --- | --- |
| Grid / có nhãn engine | 1.640 / 1.523; giữ toàn bộ ID và lý do không có nhãn |
| Đủ cả9 numeric + nhãn | 888; không được gọi1.523 là1.523 mẫu complete-case |
| Có momentum5 và2 feature VNINDEX + nhãn | 1.459; có thể nghiên cứu learner nhận mask cho6 feature còn lại |
| Trong1.459, thiếu ít nhất1 feature tùy chọn | 571; không phải571 điểm được tạo mới hoặc được sửa giá |
| Có nhãn nhưng thiếu feature lõi | 64; giữ để báo coverage/fallback, không lấp bằng số suy từ outcome |
| Report legacy đủ điều kiện tự reuse theo release mới | 0;852 report cũ thiếu raw/options durable hoặc Original |

Snapshot đầu tính agent coverage chung với numeric; **mục25 đã sửa phép
tính này** trong `corrected_coverage`. Không kết luận release hiện hành
bất khả thi vì gate agent70%. Tuy nhiên joint input vẫn chỉ888 điểm:
VNM outer2020 có38/78=48,72% complete numeric, kể cả thu thập đủ agent.
Thu thập thêm LLM không sửa được feature bị mask do cửa sổ qua ngày quyền.
V4.1 xử lý hai vấn đề riêng: bỏ nhu cầu LLM trên D/C và học với missing
mask có kiểm định, thay vì giữ yêu cầu mọi feature đều đầy đủ.

### 26.2. Kiến trúc v4.1: Bayesian học numeric, Original ở policy

Candidate dự kiến vẫn tên logic `Full_conditional_MT`, nhưng protocol và
namespace phải mang revision **v4_1**, không ghi đè v4. Learner/reference/
baseline nhận cùng9 feature numeric, mask và regime PIT; **không nhận**
Pattern/Trend/Indicator/Alpha category, a0 hoặc conflict agent trong X.
Không chèn agent X chỉ ở query vì train/context không có cùng phân phối.

`D_prior + C_target + x_query/mask → predictive r_net → calibration`
kết hợp `upstream dùng chung → Original durable a0` tại policy hiện có.
Giữ task symbol×block63, nhãn engine, target loss, prior/target markers,
K/M/m và weights cutoff; test-time thích ứng bằng context, không gradient.
Hệ thống vẫn là đa agent được advisor Bayesian hỗ trợ. Claim mới không
bao gồm “learner khai thác báo cáo agent trong lịch sử”. Có lợi ích hệ
thống hay đóng góp multi-task phải được kiểm bằng các đối chứng riêng.

**Hợp đồng missingness phải khóa trước fit:**

1. Giữ nguyên9 công thức, raw source, mask và nhãn của snapshot. Feature
   lõi là momentum5, index_momentum20, index_volatility20. Chỉ observation
   có nhãn, đủ3 feature lõi mới vào fit/D/C. Không mở lại nhãn qua quyền,
   không back-adjust giá, không lấy warmup agent để âm thầm đổi numeric.
2. Sáu feature khác được thiếu có chủ ý: chuẩn hóa phần quan sát được,
   điền0 sau chuẩn hóa và đưa mask riêng vào reference/learner/baseline.
   Giá trị0 với mask=1 không được diễn giải là feature thật. Scaler từng
   chiều chỉ fit giá trị quan sát được trong train prefix đúng fold;
   thiếu2 giá trị để ước lượng một chiều thì chiều đó unavailable, không
   mượn thống kê tương lai. Giữ floor std1e-8; OOD xét chiều quan sát.
3. Retrieval dùng khoảng cách trên giao các chiều cùng quan sát, tối
   thiểu3 chiều lõi; chuẩn hóa theo số chiều đó. Cộng0,25×tỷ lệ9 mask khác
   nhau và phạt regime0,25 như cũ. Rank/tie/exit<query/disjoint giữ nguyên;
   task centroid mỗi chiều chỉ dùng phần quan sát, nhãn nạp sau membership.
   Khóa công thức này trong amendment, không chọn lại penalty bằng outer.
4. Query thiếu lõi, scaler không hợp lệ hoặc OOD vẫn giữ a0. Forecast
   toàn grid dùng fallback chung đã khóa và báo support riêng. Lỗi
   PIT/source/API/integrity phải raise; không đổi thành missing thông thường.
5. Mô hình có mask phải được train/evaluate đúng miền này. Synthetic
   kiểm mask không làm lộ label, prior/query interventions và oracle với
   giả định missingness khai báo; không coi zero-fill là tích phân Bayes
   chính xác hoặc giả định missing hoàn toàn ngẫu nhiên trên thị trường.

Đây là giả thuyết phương pháp mới, không gọi1.459 điểm là đã nghiệm thu.
Mask có thể mang thông tin về lịch quyền/thiếu dữ liệu và làm mô hình
overfit; phải báo kết quả theo mask, độ dài context và mã. Đối chứng
`Complete_case_MT` chỉ dùng observation đủ9 numeric và fallback a0 khi
query thiếu; cùng ngân sách chọn model, dùng để đo tác động của thay đổi.

### 26.3. Panel256: mẫu LLM cố định, ngân hàng học không bị cắt còn256

Giữ toàn grid2018–2022 để audit/dự báo; fit/query nào hợp lệ tuân thủ
fold/cutoff cũ. Chỉ thu thập Original và upstream thật trên panel sau:

| Năm | Điểm/mã | Tổng | Vai trò |
| --- | --- | --- | --- |
| 2019 | 8 mỗi nửa năm =16 | 64 | Inner chọn policy cho outer2020 |
| 2020 | 8 mỗi nửa năm =16 | 64 | Inner chọn policy cuối; cũng là outer2020 với mô hình OOF khác |
| 2021 | 16 | 64 | Outer đánh giá policy, không chọn cấu hình |
| 2022 | 16 | 64 | Outer đánh giá policy, không fit weights2021/2022 |
| **Tổng duy nhất** | **64/mã** | **256** | Không cộng lại point được dùng ở nhiều vai trò |

Lịch chọn cố định: trong từng `year × symbol × half_year`, lấy các ID
`label_eligible` của snapshot, sắp ngày/ID tăng. Với n phần tử, chọn8 vị
trí **zero-based** `floor((j+0.5)*n/8), j=0..7`. Half-year theo as_of_date;
giữ purge train/evaluation theo exit như fold hiện tại. Pool này chỉ dùng
metadata khả năng tính nhãn, không đọc r_net, sign, action, độ tự tin hay
điểm bất đồng. Không lọc theo numeric coverage để làm panel đẹp hơn.
Nếu stratum thiếu8 thì `INSUFFICIENT_PANEL`, không chuyển quota sang mã
khác. Danh sách phải được vật hóa/hash trước response nghiên cứu mới.

Đối soát chỉ đọc trên snapshot hiện tại: đủ256 ID khác nhau,155 complete
numeric và248 có feature lõi. Tám query thiếu lõi vẫn thu Original và giữ
trong panel, Full fallback đúng a0. Hash dự kiến của ID sắp tăng, UTF-8,
nối bằng LF và có LF cuối:
`a2ee95af8d2bc817a495c1fa26cae37a70dacafe2dad36c0fd364d6fd3e2145c`.
Đây là kiểm tra khả thi, chưa là manifest/release chạy API.

Panel là **lịch giao dịch thưa đăng ký riêng**, không đại diện mặc nhiên
cho return của toàn grid. Tái dựng4 account trên lịch panel; giữa các
điểm giữ cash khi đã tất toán, không annualize hoặc nhân return theo tỷ
lệ1.640/256. Không gán CASH/Original giả cho điểm chưa gọi LLM. Báo D/MDD
và số thay đổi trên panel; forecast CRPS/NLL báo trên grid hợp lệ đầy đủ,
cùng fallback và common support. Panel chỉ dùng phát triển, không thay
G60 development hoặc cohort/power W12. Nửa năm32 điểm là ít cho policy:
giữ h∈{0;0,001;0,0025}, không thêm tuner hoặc chia nhỏ policy theo mã.

### 26.4. Gate và downstream phải đổi minh bạch

- **Hai hợp đồng dữ liệu riêng.** Numeric giữ tối thiểu100 cycle/4 task
  mỗi mã cho outer fit; inner60 cycle/2 task; outer evaluation30 cycle/mã.
  Đếm lại trên observation đủ feature lõi và task có≥2 cycle, không đếm
  mọi label thành input hợp lệ. Khóa yêu cầu coverage lõi≥70% trên nhãn
  từng outer/mã; đây là coverage numeric của revision mới, không phải
  kết quả PASS gate agent70% cũ.
- Audit metadata cho thấy fit nhỏ nhất: inner2019H1 FPT67 cycle/4 task;
  outer2020 FPT138/8; fit≤2020 cho outer2021/2022 FPT212/12. Evaluation
  outer nhỏ nhất69; tỷ lệ lõi nhỏ nhất69/75=92% (FPT2022). Cần rebuild
  scaler/membership, kiểm drift/OOD và leakage mới trước DATA_READY_PASS.
- **Panel yêu cầu256/256 Original durable và upstream đúng lineage**,
  không còn yêu cầu agent≥60/40 trên ngân hàng train không dùng agent X.
  HTTP failure/unknown chưa giải quyết là INCOMPLETE, không loại ID, dùng
  cache852 thay thế hoặc bịa quyết định. Schema action Original vẫn giữ.
- W11-19/20 so baseline/reference/learner trên dữ liệu numeric có mask,
  không chỉ panel. Giữ registry/seeds/inference diagnostic/CRPS gate và
  kiểm cơ chế. Baseline/K0/pooled phải cùng feature, mask và cơ hội chọn
  cấu hình; reference tuyến tính có mask không được coi là oracle thị trường.
- W11-21 fit candidate map identity/affine trên dense inner OOF; H1 dùng
  identity, H2 chỉ dùng map fit H1 như cũ. Chọn map/h bằng regret tài khoản
  **panel inner** với guard MDD; final refit map chỉ trên inner2020 OOF.
  Ngoài panel không có a0 để chấm regret. Giữ các cutoff2019/2020, không
  chọn hyperparameter bằng2021/2022 hoặcG2023. Full CRPS phải hơn baseline/
  K0/pooled/No_target trên aggregate và≥2/3 outer; D OOF panel>0 và guard
  MDD từng fold vẫn phải đạt. Không hạ các ngưỡng hiệu quả để tiết kiệm API.
- Outer2020 dùng model/policy chọn từ2019; cùng các điểm2020 có thể làm
  inner cho outer2021/2022 với predictions khác. Khóa artifact theo fold,
  không tái dùng prediction/fit sau2020 cho outer2020; không tính hai vai
  trò thành các quan sát độc lập. Original durable cùng input có thể reuse.
- W11-22–25 vẫn giữ G60, paired upstream, repeat, nomination và cold oracle.
  Đổi **No_agent_features → Complete_case_MT** trong amendment: Full v4.1
  đã không dùng agent X, nên giữ no-agent sẽ là so sánh trùng. Numerical_MT
  dùng cùng distribution nhưng policy không dùng a0 trừ fallback. Giữ10
  nhánh,996 dòng action/324 slot Decision LLM danh nghĩa ở development;
  upstream/control/retry tính riêng. Các chi phí này **ngoài W11-18**.
- W12 giữ8 secondary, CI99,375%, thay claim agent-feature bằng claim về
  xử lý missingness khi đối chứng tương ứng đạt. Full hơn Original mới
  là lợi ích hệ thống; hơn K0/pooled mới giúp tách đóng góp multi-task.
  Full hơn Numerical_MT chỉ kiểm giá trị a0/policy, không chứng minh tác
  dụng của từng agent. Không dùng panel256 làm kết quả chính khóa luận.

### 26.5. Ngân sách thực tế và lựa chọn thay thế

| Phương án | Điểm LLM / HTTP nghiên cứu | Thời gian tại80 điểm/ngày | Đánh giá |
| --- | --- | --- | --- |
| Thu đủ v4 hiện tại | 1.640 /4.920 | 20,5 ngày quota | Không đạt yêu cầu3–5 ngày |
| Chỉ cắt v4 còn256, giữ nguyên feature/gate | 256 /768 | 3,2 ngày quota | Thiếu agent trên D/C, không được tiếp tục như v4 đã đủ dữ liệu |
| **V4.1 numeric có mask + panel256** | **256 /768** | **3,2 ngày lý tưởng;4 ngày ở64 điểm/ngày** | Chọn làm kế hoạch tiếp nối; cần amendment/code mới |
| Nâng quota cùng model | 1.640 /4.920 | Cần≥328 điểm/ngày để xong5 ngày, chưa dự phòng | Giữ thiết kế cũ nhưng cần quota/chi phí được xác minh; chưa mua dịch vụ |
| Batch/provider/model khác | Chưa khóa | Chưa đủ bằng chứng bảo đảm3–5 ngày | Không đưa vào đường chạy chính |

Panel giảm**84,39%** HTTP nghiên cứu, từ4.920 còn768; không đổi token cap,
model hoặc số agent mỗi điểm. Có tối thiểu12 probe cho4 scope nếu mỗi
scope cần3 probe, cộng retry/unknown recovery thực tế. Không tính probe
thành mẫu khoa học. Ước lượng80 điểm/ngày là năng lực người dùng báo, không
phải quota đã đo cho từng loại request; cần telemetry điểm complete/ngày.

[Groq Batch](https://console.groq.com/docs/batch) công bố cửa sổ xử lý
24 giờ–7 ngày và quota riêng; bảng model kiểm ngày01/11 không liệt kê
vision model đang ghim `qwen/qwen3.8-27b`. Vì vậy chưa thể hứa “đổi sang
Batch là xong trong24h”. Prompt cache cũng không bảo đảm bỏ được mọi nút
thắt RPD/TPD/vision. Giữ model/options hiện tại để không thay baseline.
[Rate limits của Groq](https://console.groq.com/docs/rate-limits) áp theo
tổ chức; ở đây dùng xác nhận của người dùng rằng4 scope độc lập, không
coi mọi bộ4 key bất kỳ đều nhân quota lên4.

Lịch mục tiêu5 ngày gồm1 ngày chuẩn bị và4 ngày chạy, mỗi ngày**16 điểm/
key ×4 =64 điểm**, dự phòng20% so80. Nếu chuẩn bị đã xong, có thể chạy
80/80/80/16 điểm qua4 cửa sổ ngày. Mốc3 ngày chỉ đạt khi có cache đủ điều
kiện hoặc throughput cao hơn, không hứa256 điểm trong đúng3 ngày ở80/ngày.
Ngày5 là hạn mục tiêu thu thập/cold audit, không phải lý do bỏ các điểm lỗi
để ghi DONE. Nếu provider lỗi kéo dài hoặc triển khai quá1 ngày thì báo
ETA mới và phần còn thiếu; tuyệt đối không bảo đảm tối đa5 ngày vô điều kiện.

Chọn **một coordinator ghi ledger/checkpoint**, chia danh sách thành4
shard64 ID theo round-robin của danh sách đã sắp, bind scope credential
được phép trước run. Coordinator chạy các scope tuần tự ở ranh giới point;
không cần4 process đồng thời trên journal hiện tại. Nếu đổi key thủ công,
ghi resume/scope và probe theo release. Mọi lần gọi vẫn qua retry/pacer,
tuân thủ TPM/RPM/RPD/TPD, không vòng qua quota của một scope đã hết.
Tăng concurrency chỉ làm sau khi có cơ chế một writer và kiểm lock/resume;
không xóa lock hoặc nhân4 tiến trình CLI cũ.

### 26.6. Các bước thực hiện tiếp trong W11-18

| Bước | Công việc và đầu ra bắt buộc | Điều kiện hoàn tất |
| --- | --- | --- |
| **18a — khóa amendment** | Tạo protocol/lock v4_1, parent SHA v4; feature lõi/mask/retrieval, panel rule/ID/hash, hai loại metric, ma trận mới; namespace mới | Không fit/API trước spec lock; v4 receipt nguyên byte; model/options/economics/PIT không đổi |
| **18b — ngân hàng offline** | Dựng scaler per-feature, D/C và fold theo mask; audit1.640 ID/1.523 label/1.459 candidate core; materialize panel256 trước đọc action mới | Nhãn nguyên byte; split/purge/lineage và gate numeric trên input thật PASS, không chỉ metadata |
| **18c — runner panel và preflight** | Collector nhận đúng manifest256, một writer/4 scope; tái dùng warmup đã seal; raw cache/UUID/resume; xử lý vision400 bằng diagnostic hiện có | Probe đúng model thành công trước research; kế hoạch slot768+controls; không còn hard-code bắt đủ1.640 cho revision mới |
| **18d — người dùng thu thập** | Thu256 Original+upstream,16 điểm/scope/ngày dự kiến; kiểm cache hợp lệ trước HTTP; báo complete/remaining và ETA hằng ngày | Không thay ID/model vì lỗi; không gọi A/Plain/repeat ở bước data; không xem P&L để dừng sớm |
| **18e — cold acceptance** | Đối chiếu raw/HTTP/body/UUID/source/warmup/PIT; xác minh ngân hàng numeric và panel riêng; audit pipeline upstream một lần và a0 thật | Đủ256/256, numeric gate PASS, không unknown; receipt mới DATA_READY_PASS mới cho mở19 |
| **18f — đồng bộ downstream** | Khóa baseline/reference/learner feature schema, calibration panel, Complete_case_MT, counts/family/claim W11–W12 | Không consumer nào dùng gate/manifest v4 như v4.1; W11-18 mới được đánh DONE |

Các kiểm thử **khi triển khai**: poison label/future bar không đổi X/
membership; không dùng missing value làm số thật; source mask/observed
scaling/PIT; shared-core distance và disjoint D/C; panel deterministic/
không thay theo action/return; đủ256 không đòi1.640;3 HTTP/point, replay
không đọc key/gọi lại durable; lock/scope quota/backoff/unknown recovery;
OFF/missing=Original. Chỉ chạy test liên quan và leakage đúng đường đổi,
không chạy toàn suite do đổi kế hoạch.

**Kiểm tra lượt lập kế hoạch:** chỉ sửa3 Markdown (README W11, W12 và
plan tổng), không sửa Python/test/config/schema/JSON hoặc gọi API. Kiểm
diff, link/anchor, số liệu chọn mẫu và hash so HEAD; không chạy compileall,
unit/E2E/leakage theo AGENTS.md1.2 vì không có thay đổi hành vi. Nguồn audit:
[coverage v4](coverage_v4.json), [protocol v4](protocol_v4.json),
[release collection](data_completion_release_v4.json) và implementation
`core/mt_bicl_v4_data.py`, `core/mt_bicl_v4_completion.py` tại `b8405a4`.
Observations SHA `7efd564cda16adb105343cfd9709e7c659d24b8b7a67460de544a532b15c32fa`;
folds SHA `88fc0a70b3138bbf989d2c2f7be0a4974163d072a95eed287980f3b5623ff51c`.
QA tài liệu:164 liên kết/anchor nội bộ,12 hash nguồn/bằng chứng và checklist
PASS; diff không lỗi khoảng trắng. Các gate runtime cũ chỉ được viện dẫn,
không coi kiểm tài liệu này là đã chạy lại test hoặc nghiệm thu v4.1.
W11 giữ15 DONE/2 NOT_RUN/1 IN_PROGRESS/7 TODO; W12 giữ0/8. Chưa có kết quả
forecast, nomination hoặc lợi nhuận của v4.1.
