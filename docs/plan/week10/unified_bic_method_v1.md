# Protocol phương pháp U-BICL v1

Đặc tả `unified_bic_protocol_v1`, khóa rule ngày 24/10/2026 từ audit tại
`0abd1ac`. [Protocol JSON](unified_bic_protocol_v1.json) chứa hằng số, nguồn
và lịch development; [fixture tổng hợp](fixtures/unified_bic_contract_v1.json)
chứa input/expected để các module sau kiểm bằng oracle. Đây là đặc tả,
**không phải execution plan, source freeze cuối hoặc release API**.
Tiến độ/QA/hash được quản lý tại [README W10](README.md#u10-02--khóa-protocol-và-fixture-24102026).

JSON và tài liệu cùng là hợp đồng; mâu thuẫn phải dừng để sửa version trước
execution. U10-04 khóa kết quả chọn backbone, U10-05/06 khóa renderer/common
instruction, U10-09 khóa source/request/repeat thực tế bằng hash. Các bước
đó hiện thực rule dưới đây, không mở thêm vòng tìm phương pháp. Đổi rule
sau khi thấy outcome phải khai báo revision và kết quả thăm dò, giữ lượt cũ.

## 1. Câu hỏi, ứng viên và giới hạn

Chỉ **U_full** được đề cử. Giả thuyết chính: context kết hợp posterior và
demonstrations giúp Decision LLM tăng return tài khoản so Original; so A
trên cùng nguồn kiểm lợi ích tăng thêm của toàn phương pháp hợp nhất.
Full−stats đo block demonstrations; full−examples đo block posterior.
Summary s/n trong demonstrations vẫn hiện ở examples-only, nên contrast
sau không có nghĩa loại mọi thông tin thống kê khỏi context.

[Zhu, Oermann và Cho](https://proceedings.mlr.press/v306/zhu26aj.html) huấn
luyện transformer trên các prior/target task cho suy luận Bayes phân cấp.
U-BICL dùng LLM hosted không huấn luyện lại: Bayes số học được tính ngoài
LLM, demonstrations điều kiện hóa context, LLM tự chọn LONG/SHORT. Đây là
thích ứng phương pháp; trace/citation ID không chứng minh Bayes nội tại,
confidence dạng chữ không là xác suất đã hiệu chuẩn.

| ID logic | Context và vai trò |
| --- | --- |
| Original | Không prior; common instruction/schema mới giống các nhánh LLM khác |
| A_reference | Evidence/selector/prefix A_tp_pool legacy, memory chung và shared-off mới |
| U_full | Backbone đã chọn và task/episode context; candidate duy nhất |
| U_stats | Cùng base evidence U, chỉ posterior/support/CrI; không task/exemplar ID hoặc x→y |
| U_examples | Cùng base evidence U, chỉ demonstrations và s/n; không posterior/CrI |
| Numeric_only | Backbone U; mean>0,5 khi win_rate_long ready thì LONG, còn lại SHORT=CASH |

A_reference giữ cả các metric A hiện hữu; posterior mục tiêu của U là
**win_rate_long**, y=1[r_net>0]. U−A không cô lập riêng pooling hoặc wording.
Numeric là đối chứng ngưỡng xác suất, không là candidate ICL, expected-utility
policy hoặc Bayes-optimal trading. Không đưa Numeric vào lời gọi LLM/vote.
Một candidate/một vòng development, không quét prompt/model/K; không
fine-tune, cross-symbol pooling, soft regime, ensemble hoặc risk overlay.

## 2. Nguồn, nhãn và thời gian

Bank gốc 852 record giữ nguyên. Memory mới nhập tối đa 124 upstream đã kiểm
từ W8/W9 (60 query 2023, 64 query 2024), dedup ID và cycle `(symbol, cutoff)`.
Không dùng Decision/action/justification/confidence làm feature, không gọi
LLM sinh bank. Record không tương thích bị loại với reason; checksum/PIT/
economic integrity sai phải ném ValueError/AssertionError, không im lặng bỏ.

LONG mua Open(t+1), bán Close(t+3) theo phiên; SHORT giữ CASH. Phí 0,25% và
slippage 0,10% mỗi chiều; nhãn chỉ qua `compute_round_trip_net_return`, net
fraction trong tính toán, nhân 100 khi hiển thị %. Không trừ phí lần hai.
Giá nguồn là nghìn VND, nhân 1.000 khi dựng tài khoản VND theo engine.
Giá/tin≤query cutoff; bỏ tin không ngày. Prior phải có exit<cutoff trước
đọc outcome/ranking/stats; self-match và cycle vắt qua cutoff bị loại.
Ứng viên tương lai bị lọc đúng rule; nếu còn xuất hiện trong evidence đã
khai PIT thì phải ném lỗi. Không đổi các artifact/hash legacy để nhận U.

2020 chỉ khởi động lịch sử; chọn λ bằng query train 2021/2022 đã khóa,
HMM historical_prefix đúng ngày, scaler fit cycle đóng trước đầu fold;
purge cycle vắt biên và query có exit sau cuối fold.
Lịch score mới có **647 query**: 325 năm 2021 và 322 năm 2022. Bốn query
31/12/2021 có exit 06/01/2022 bị purge khỏi score 2021; không chép nguyên
mẫu số 651 của diagnostics legacy hoặc sửa kết quả cũ. Retrieval cuốn chiếu
vẫn chỉ thấy cycle đã đóng trước từng query, scaler không refit trong fold.
2023 exploratory; 2024 đã xem, chỉ là kết quả W9 và nguồn lịch sử, không tune
λ/prompt U.
OOS giữ HMM và scaler fit train tới 30/12/2022; index/version mới cấp scope
2025 mà không refit bằng OOS. Xác nhận dùng snapshot memory exit≤31/12/2024,
không append outcome 2025 trong run. Stats lấy mọi observation PIT hợp lệ;
age/similarity/feature filters chỉ áp examples, không xóa observation stats.

2025 hiện **BLOCKED: MISSING_VERIFIED_2025_EXECUTION_SOURCE**. Khai báo
exposure lịch sử không biến thành chứng nhận chưa từng xem hoặc release.
Sau nomination mới được phát hành xác nhận khi giá thô/quyền/prefix/lịch/
exposure độc lập và công cụ kiểm đều PASS. Chỉ chọn ngày bằng eligibility,
không đọc payoff; step3 neo phiên đầu 2025, cycle hoàn tất trong quý,
N≥8/mã/quý, lấy floor(j*(N−1)/7), j=0..7. Thiếu điều kiện giữ exploratory
hoặc forward sau lock; không giảm 128 điểm, lấy phần 2024 còn lại hoặc xóa
output để coi là holdout mới. MDE/coverage planning thuộc U10-09/U11.

## 3. Posterior và rule chọn pooling

Sau PIT, cùng mã: C cùng regime khớp Trend/Pattern; B1 cùng regime ngoài C;
B2 khác regime. Ba tập rời nhau; P=C∪B1, B của A chính là B1. Với s/n là
success/support, A dùng mB=(s1+1)/(n1+2), posterior
Beta(sC+4*mB, nC−sC+4*(1−mB)). Hierarchical candidate offline dùng:

```text
m2 = (s2+1)/(n2+2)
m1 = (s1+lambda*m2)/(n1+lambda)
posterior = Beta(sC+lambda*m1, nC-sC+lambda*(1-m1))
lambda ∈ {2,4,8}
```

nC=0: posterior mean/CrI=null với NO_CONDITIONAL_HISTORY, không điền 0,5.
n2=0 cho m2=0,5; n1=0 cho m1=m2 với reason thiếu background, không giả n>0.
CrI95% equal-tailed Beta plug-in không tích phân toàn bộ bất định hyperprior/
phụ thuộc cycle. Báo nC/n1/n2, prior weight λ/(nC+λ), tuổi, số cụm thời gian;
raw n không là effective sample size hoặc xác suất query đã calibrated.

Chấm trên giao **raw posterior hữu hạn của A và cả ba λ**, trước ready gate,
query train ngoài thời gian; không dùng 2023/2024/2025. Mỗi query có trọng số
bằng nhau, gộp hai fold; báo riêng fold/mã và IDs/mẫu số. Brier dùng p gốc,
log loss clip p vào [1e−6,1−1e−6]. Chọn tuple (mean log loss, mean Brier, λ)
tăng dần bằng giá trị đầy đủ, không làm tròn trước gate/tie-break.

Chỉ nhận λ đã chọn khi cả mean loss không xấu hơn A, ít nhất một tốt hơn;
Brier mỗi mã tăng≤0,01 và tổng ready count trên toàn query train không giảm.
Không có common posterior ở bất kỳ ô fold×mã nào hoặc thiếu diagnostics thì
gate không PASS. Nếu trượt dùng **A**, không thử nhận λ đứng sau hoặc thêm λ.
U10-04 phải lưu choice/reasons/nguồn/diagnostics/version trước LLM; chưa có
choice thì chặn release, không mặc định là đã nhận pooling.

Stats ready A: |P|≥20, nC≥5, width≤0,75. Pooling ready: n1+n2≥20, nC≥5,
width≤0,75. Numeric dùng đúng gate win_rate_long; p=0,5 hoặc evidence thiếu
hợp lệ trả CASH có reason, lỗi nguồn/execution không được đổi thành CASH.
Examples ready giữ |P|≥20 và có representative đủ điều kiện; không yêu cầu
stats ready. Stats thiếu không xóa examples và ngược lại.

## 4. Task, ranking và fallback xác định

Lịch VNINDEX neo phiên train đầu 02/01/2018, index phiên từ 0. Block của
episode = floor(index(cutoff)/90), task ID=`symbol|regime|bNNNN`; không neo
lại theo query hoặc khi append. Task chỉ cùng mã/regime query; membership
gồm mọi cycle đã đóng PIT, tuổi cutoff≤730 ngày trong block. Summary s/n
tính trên **toàn membership này**, kể cả record thiếu feature hoặc dưới
ngưỡng similarity; hiển thị raw support≥2, không ép hai exemplar/task.

Representative cần feature/scaler hợp lệ và base similarity≥0,625. Giữ bốn
tín hiệu T/P/Alpha/Indicator và bốn chiều giá chuẩn hóa hiện hữu:
S=tỷ lệ khớp bốn tín hiệu, d=RMS distance, base=0,5*S+0,5/(1+d),
score=base*2^(−age/365). “Similarity đại diện tốt nhất” dùng score sau recency;
không dùng s/n, return hoặc action để xếp hạng. Không cần centroid/outcome.

Lặp greedy tối đa ba nhóm: mỗi nhóm support≥2 còn lại đề cử representative
tốt nhất không xung đột với đại diện đã chọn; sắp (-score, tuổi tăng,
task ID, episode ID), lấy đầu. Các đại diện có khoảng cách cutoff≥5 phiên
và interval entry–exit đóng không overlap. Nếu đại diện tốt nhất xung đột,
thử đại diện kế trong nhóm trước lần xếp nhóm tiếp theo. Membership/summary
không bị thay vì diversity. Một nhóm khả dụng vẫn là mode `task` với K=1;
không bù thêm episode lẻ cho đủ ba nhóm.

Không có nhóm đủ support/representative thì `context_mode=episode_fallback`:
top≤3 cycle theo selector A nguyên rule (score giảm, exit mới trước, ID tăng,
gap≥5 phiên). Không có cycle hợp lệ hoặc examples gate trượt thì mode `off`.
Mode chỉ mô tả examples; stats vẫn có thể on khi mode off. Không chọn mode
bằng outcome/action. Summary trình bày lại evidence, không cộng counts vào
posterior; sidecar giữ full membership, ID, cutoff, score và lý do loại.
Mode của base demonstrations được giữ trong evidence; projection stats-only
không đưa mode, ID hoặc nội dung examples vào prompt.

Multi-task support đạt khi ≥12/60 development có ≥2 task visible và ≥2/mã.
Không đạt vẫn đo estimand U với fallback đã khóa; không claim multi-task
đã kiểm đủ support, không sửa block theo return để qua gate.

## 5. Prompt và thực thi ghép cặp

Một renderer family, chỉ khác field visibility của nhánh và mode. Thứ tự:
regime/horizon → posterior/support/CrI nếu ready → task hoặc episode x→y
nếu ready → bất định/SHORT=CASH. ID ngắn có legend và ánh xạ duy nhất sidecar.
Task có n, s/n và một cặp T/P→net return%; episode fallback có nhãn mode.
BRPP≤600 và toàn prompt<6.500 ký tự, tính Unicode code point; giữ distill/cap.
Không cắt nhãn/legend hoặc đổi budget khi ca biên không vừa; phải sửa kỹ thuật
trước lock renderer và kiểm đủ ba nhóm, không chọn wording bằng return.

Common instruction/schema giống nhau cho năm nhánh LLM, version mới; horizon
Open(t+1)→Close(t+3) rõ theo phiên. Đối chiếu prior với tín hiệu hiện tại;
LONG khi p<0,5 hoặc CASH khi p>0,5 cần giải thích căn cứ, không ép agreement.
Dùng các chuỗi evidence_for/evidence_against/justification legacy, không thêm
field probability/trace bắt buộc hoặc retry vì không đồng ý prior. Trace ID
chỉ telemetry, không dùng promotion. A_reference giữ prefix evidence A.

Primary xếp point (ngày, FPT/MWG/VCB/VNM), j từ 0. Original đầu; xoay trái
[A_reference,U_full,U_stats,U_examples] j mod 4; Numeric tính offline.
Repeat: mỗi mã chọn ba ngày đầu theo strata both-ready, one-block-ready, off
của U_full trước action; thiếu stratum bù ngày sớm nhất chưa chọn, lưu reason.
Chọn hết strata có quan sát trước, sau đó bù các strata thiếu theo thứ tự trên.
Ba lượt r=1..3, Original đầu; xoay trái [A_reference,U_full,U_stats,U_examples,
Original_duplicate] (3j+r−1) mod 5, j là index toàn mẫu 12 điểm theo cùng thứ
tự ngày/mã. Repeat xác nhận dùng rule tương tự, khóa trước primary action.

Một upstream/point, deep-copy và giữ request primary cho repeats; policy
cache W8/W9 đã compatible được khóa cho development, không tự fallback fresh
giữa run. Nguồn đổi/incompatible phải dừng release để review, không chọn lại
upstream theo outcome. Xác nhận nếu được release dùng upstream fresh một lần
mỗi point, hoàn tất khóa readiness/repeat/request trước primary action.
Original lưu durable trước nhánh khác. Prior-off chỉ
reuse cùng point/repeat khi canonical body/model/options/schema trùng toàn bộ,
ghi decision_origin=shared_original và source hash; không giả HTTP. Nếu khác
thì invoke đúng request, báo reason. Whitelist alias stats-only **rỗng** trong
v1; không gộp nhánh vì cùng action. Duplicate luôn invoke độc lập, kể cả body
giống Original; không vote hoặc lấy response thuận lợi.

Mọi invoke qua retry wrapper; giữ backoff/retry-after, ledger chung, checkpoint
mỗi point và từng stage/slot. Unknown dùng durable response nếu có, nếu không
giữ UUID và audit retry theo policy hiện hữu; integrity lỗi phải dừng. Không
replay complete, bỏ điểm lỗi, thay model giữa run hoặc chuyển error thành CASH.

## 6. Nomination, thống kê và claim

Development giữ đủ 60 điểm FPT12/MWG16/VCB16/VNM16. Nomination chỉ U_full khi
common support đủ mọi nhánh, metrics hữu hạn, primary/ba repeat verify và bốn
gate đúng source/runtime PASS; prior visible≥30/60 và ≥5/mã; examples visible
≥12/60 và ≥2/mã. D_U−Original>0, ΔR>0 ở≥3/4 mã, D_U−A≥0, mean ΔMDD≤2,
max ΔMDD≤5 đpt. Đây là rule lựa chọn trên development đã xem, không là test
xác nhận. Không đạt thì STOP/không release, không nominate ablation hoặc
chạy 2025 để cứu kết quả; multi-task claim gate riêng không thay gate này.

Primary D=(1/4)Σ_s(R_U,s−R_Original,s), bốn tài khoản riêng 50 triệu theo
engine fractional/full-cash round-trip. G phải đủ mọi nhánh/điểm, không điền
CASH cho missing. T cùng stats/examples ready chỉ là subgroup mô tả.
Xác nhận nếu được release: circular moving-block bootstrap theo ngày cutoff
duy nhất tăng dần, giữ mọi mã/nhánh cùng cụm; L=4, 10.000 draws,
Generator(PCG64(20261024)). Lấy ceil(n_dates/L) starts uniform có hoàn lại,
nạp lại generator cùng seed cho từng L, không nối RNG state giữa các L;
nối block modulo, cắt n_dates; dựng lại tài khoản theo thứ tự tổng hợp,
không sắp lại ngày gốc hoặc cộng cycle return. Cùng index cho mọi contrast.
Missing mã/nonfinite ở bất kỳ nhánh làm draw invalid; cần≥9.500 hợp lệ,
không sinh bù. Percentile linear, sensitivity L=2/8 chỉ mô tả.

| Kết quả trên xác nhận đủ điều kiện | Claim tối đa |
| --- | --- |
| Primary CI95% có cận dưới>0 | Hữu ích hơn Original trên cohort/protocol và saved Decision |
| U−A CI98,75% có cận dưới>0 | Hơn phương pháp A trên cùng nguồn/protocol |
| Full−stats / full−examples CI98,75% có cận dưới>0 | Đóng góp tăng thêm của block tương ứng |
| CI chạm/qua 0 | INCONCLUSIVE, không suy tương đương/không hiệu ứng |
| Chỉ Numeric thắng | Lợi ích mô hình số; không quy cho ICL |

Family secondary cố định bốn contrast U−A/U−stats/U−examples/U−Numeric,
Bonferroni 0,05/4, không đổi family theo alias/subgroup. CI điều kiện saved
Decision, không bao gồm mọi training/provider uncertainty. Development,
repeat, MDD/LONG-CASH/calibration/subgroup/LOSO/prior-off/task modes là mô tả;
repeat đổi dấu hoặc duplicate nhiễu phải nêu, không chọn lượt tốt nhất.
Không suy hiệu quả live, tính nhân quả riêng từng cơ chế hoặc provider
deterministic từ CI và shared-off. W9 báo riêng và giữ mọi kết quả bất lợi.
