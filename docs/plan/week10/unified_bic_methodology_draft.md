# Bản thảo phương pháp nghiên cứu U-BICL

Bản thảo diễn giải hệ thống đã triển khai offline và thiết kế kiểm định
đã đăng ký, dùng cho chương phương pháp KLTN. Các rule chi tiết ở
[protocol v1](unified_bic_method_v1.md) và
[protocol JSON](unified_bic_protocol_v1.json); quy trình chạy ở
[hướng dẫn vận hành](unified_bic_operations.md). Bản thảo không đổi protocol,
không bổ sung candidate, không trình bày kế hoạch như kết quả thực nghiệm.

## 1. Câu hỏi nghiên cứu và cách thích ứng

Nghiên cứu kiểm tra liệu evidence Bayes lịch sử cùng demonstrations có giúp
Decision LLM cải thiện kết quả kinh tế so với không có prior và A_tp_pool
trên cùng nguồn/protocol hay không. Cơ sở tham khảo là
[Zhu, Oermann và Cho (2026)](https://proceedings.mlr.press/v306/zhu26aj.html):
công trình huấn luyện transformer trên chuỗi prior/target tasks để thực hiện
dự đoán Bayes phân cấp theo hướng amortized. Trong đề tài này, LLM hosted
không được huấn luyện lại theo cơ chế đó. Posterior được code tính bên ngoài,
demonstrations điều kiện hóa context, còn LLM tự chọn hành động.

U-BICL vì vậy là một phương pháp Bayesian evidence-conditioned ICL cho giao
dịch. Việc LLM viện dẫn ID hay đồng ý posterior không chứng minh suy luận
Bayes nội tại. Posterior lịch sử không được diễn giải trực tiếp thành xác
suất query đã hiệu chuẩn, expected return hoặc utility tối ưu. Chỉ U_full
là candidate được đăng ký; Numeric_only là đối chứng số học.

## 2. Dữ liệu, đơn vị quan sát và exposure

Mỗi test point là một mã/cutoff sau khi đóng cửa phiên t. Dữ liệu Daily EOD
của VN-Index và FPT/MWG/VCB/VNM được xử lý theo lịch phiên. HMM và feature
scaler ngoài mẫu giữ phần train kết thúc 30/12/2022. Khi chấm query train,
HMM dùng historical prefix đúng cutoff và scaler của fold đã freeze trước
query; cycle vắt biên bị purge.

| Giai đoạn | Vai trò và giới hạn |
| --- | --- |
| 2018–2022 | Nguồn train/memory; 2020 khởi động lịch sử, 2021/2022 chọn pooling ngoài thời gian |
| 2023 | Development exploratory đã xem: 60 điểm, FPT12/MWG16/VCB16/VNM16, 21 cutoff khác nhau |
| 2024 | W9 đã xem và nguồn upstream lịch sử được khai báo; không dùng làm xác nhận U-BICL hoặc tune prompt/λ |
| 2025 | Tập xác nhận dự kiến 128 điểm, chỉ sau nomination và audit/release U11; chưa có kết quả U-BICL |

Memory revision có 976 record: 852 record gốc và 124 upstream W8/W9 đã kiểm.
Không nhập Decision/action/confidence/justification vào feature lịch sử.
Việc thêm record 2023/2024 vào snapshot không cho phép query 2023 đọc tương
lai: eligibility lọc metadata cùng mã, `exit_date<cutoff` và loại self-match
trước khi đọc nhãn. Nguồn giá/tin trong query chỉ tới cutoff; bài không có
ngày hoặc công bố sau cutoff bị loại. Evidence khai PIT mà còn future/self
phải ném lỗi thay vì âm thầm cho qua.

Nguồn được ràng buộc bằng hash, provenance và runtime; không suy independence
từ việc xóa output hoặc thay kế hoạch. Giá thực thi 2025 đã được bổ sung và
PASS; các nhãn BLOCKED vì thiếu giá trong snapshot protocol ban đầu là lịch
sử. Điều đó không thay thế audit exposure/independence, lịch và release xác
nhận sau nomination. Xác nhận dùng memory exit≤31/12/2024 và không append
outcome 2025 trong run.

## 3. Nhãn và hợp đồng kinh tế

LONG mua tại Open(t+1), bán Close(t+3) theo phiên; SHORT giữ CASH. Với phí
môi giới f=0,0025 và slippage s=0,001 mỗi chiều:

```text
r_net = Close(t+3)*(1-s)*(1-f) / [Open(t+1)*(1+s)*(1+f)] - 1
y = 1[r_net > 0]
```

Nhãn lịch sử và evaluator dùng `compute_round_trip_net_return` trong
`core/backtest_engine.py`; không dùng Close-to-Close hoặc trừ phí lần hai.
Giá nguồn nghìn VND được nhân 1.000 khi dựng tài khoản VND. Bốn tài khoản
riêng khởi đầu 50 triệu, thực hiện fractional/full-cash round-trip theo
engine hiện hữu. Điểm thiếu/error không được đổi thành CASH; Numeric_only
thiếu stats thì CASH là policy đối chứng đã đăng ký, khác lỗi execution.

## 4. Posterior có điều kiện và pooling

Trong các cycle cùng mã đã đóng trước cutoff, C cùng regime và khớp Trend/
Pattern; B1 cùng regime ngoài C; B2 khác regime. Ba tập rời nhau. Với s là
số LONG ròng dương và n là support, backbone đã khóa λ=8 tính:

```text
m2 = (s2+1)/(n2+2)
m1 = (s1+lambda*m2)/(n1+lambda)
alpha = sC+lambda*m1
beta = nC-sC+lambda*(1-m1)
posterior = Beta(alpha,beta), nếu nC>0
```

Nếu nC=0, posterior mean/CrI null với reason, không điền 0,5. n2=0 cho m2=0,5
và n1=0 cho m1=m2, kèm reason thiếu background. CrI95% equal-tailed là Beta
plug-in, không tích phân hết bất định hyperprior/phụ thuộc cycle. Raw support
không là effective sample size. Stats không dùng age/feature filters của
examples để loại quan sát hợp lệ.

λ được chọn một lần từ {2,4,8} trên 647 query train đã purge: 325 năm 2021,
322 năm 2022. Chấm equal-query trên giao raw posterior hữu hạn của A và cả
ba λ, trước ready gate; xếp tuple log loss, Brier, λ bằng precision đầy đủ.
Chỉ nhận winner khi cả loss không xấu hơn A, ít nhất một tốt hơn, Brier tăng
mỗi mã≤0,01 và ready count không giảm, đủ common support mọi fold×mã.
Trượt thì dùng A, không thử nhận runner-up. U10-04 đã nhận λ=8 trước LLM.

Pooling stats ready khi n1+n2≥20, nC≥5, CrI width≤0,75. A_reference giữ rule
|C∪B1|≥20, nC≥5, width≤0,75 và các metric A legacy. Gate stats/examples tách
biệt: thiếu stats không xóa demonstrations và ngược lại.

## 5. Context nhiều task và lựa chọn không dựa vào nhãn

Task là nhóm cùng mã/regime và block 90 phiên, neo từ phiên 02/01/2018,
không neo lại theo query. Membership gồm cycle đã đóng PIT, tuổi cutoff≤730
ngày trong block; summary n và s/n dùng toàn membership, kể cả record thiếu
feature hoặc dưới ngưỡng similarity. Task cần support≥2 và tối đa ba nhóm
được đại diện; không ép đủ K=3 hoặc hai exemplar/task.

Representative có feature/scaler hợp lệ và base similarity≥0,625. S là tỷ
lệ khớp T/P/Alpha/Indicator, d là RMS distance bốn chiều giá đã chuẩn hóa:

```text
base = 0.5*S + 0.5/(1+d)
score = base*2^(-age_days/365)
```

Greedy chọn representative tốt nhất của từng nhóm còn lại không xung đột
với nhóm đã chọn; tie-break theo score giảm, tuổi tăng, task ID, episode ID.
Cutoff cách≥5 phiên và interval entry–exit đóng không overlap. Nếu đại diện
đầu xung đột thì thử đại diện kế của nhóm trước lần xếp hạng tiếp theo.
Outcome không tham gia ranking; nhãn/success chỉ trình bày sau selection.

Không có task đủ điều kiện thì dùng episode_fallback theo selector A; không
có ví dụ/gate examples trượt thì off với reason. Examples gate giữ |C∪B1|≥20
và có representative. Một task vẫn có mode task, nhưng không được mô tả là
đã đủ coverage multi-task. Gate claim đòi≥12/60 điểm có≥2 task và≥2/mã.

Một base evidence chung được chiếu thành stats-only, examples-only hoặc
full. BRPP≤600, toàn prompt<6500 ký tự Unicode; giữ distill/cap. Cùng common
instruction, schema Decision legacy và model/options cho mọi nhánh LLM;
khác block context. ID E/T có legend và sidecar ánh xạ duy nhất. Stats-only
không nhận exemplar/task ID ẩn. LLM được yêu cầu đối chiếu tín hiệu hiện tại
với prior và giải thích lựa chọn mâu thuẫn, không bị ép action theo mean.

## 6. Đối chứng, ghép cặp và repeat

| Nhánh | Nội dung/vai trò |
| --- | --- |
| Original | Không prior; cùng common instruction/schema |
| A_reference | Evidence/selector/prefix A_tp_pool trên memory chung |
| U_full | Posterior đã chọn và task/episode demonstrations; candidate duy nhất |
| U_stats | Cùng base, chỉ block posterior/support/CrI |
| U_examples | Cùng base, demonstrations và summary s/n; không block posterior/CrI |
| Numeric_only | mean>0,5 khi stats ready thì LONG, còn lại CASH; không gọi LLM |

Upstream được chạy/reuse verified một lần mỗi point và deep-copy cho các
nhánh. Development khóa cache W8/W9, không fresh fallback giữa run. Original
lưu durable đầu mỗi point/repeat. Nhánh prior-off chỉ reuse khi toàn body/
model/options/schema trùng Original cùng point/repeat và prefix rỗng; không
tạo UUID/HTTP giả. Nhánh có prior vẫn độc lập dù tình cờ cùng body/action;
whitelist alias stats-only rỗng. Original_duplicate luôn độc lập.

Primary sắp ngày rồi FPT/MWG/VCB/VNM, Original đầu và xoay bốn nhánh prior
j mod 4. Numeric offline. Repeat chọn ba điểm/mã trước action: ngày đầu của
both-ready, one-block-ready, off; lấy hết strata có sẵn rồi bù ngày sớm chưa
chọn và ghi reason. Ba lượt r=1..3 xoay năm nhánh còn lại, gồm duplicate,
(3j+r−1) mod 5; giữ request/upstream primary. Tổng 300 slot LLM primary và
216 repeat, không phải số HTTP thực. Repeat không vote hoặc cộng vào mẫu
primary. Các cặp bất đồng repeat/duplicate phụ thuộc, không là mẫu độc lập.

Kernel giữ retry-after/backoff, ledger chung, checkpoint/UUID và audit.
Unknown có response durable được phục hồi; nếu cần HTTP mới thì vẫn cùng
UUID theo policy. Complete không replay; integrity lỗi dừng. Cơ chế này giữ
paired protocol, không chứng minh provider deterministic dù temperature=0.

## 7. Estimand, nomination và kiểm định được đăng ký

Primary D là trung bình đều delta return của bốn tài khoản riêng:

```text
D = (1/4) * sum_s [R(U_full,s) - R(Original,s)]  # đơn vị đpt
```

G đòi đủ mọi nhánh/điểm, không bỏ missing hoặc điền CASH. T cùng stats và
examples ready là subgroup mô tả, không thay G. Development đã xem chỉ dùng
nomination: đủ primary/ba repeat verified, metrics hữu hạn, bốn gate hiện
tại, prior visible≥30/60 và≥5/mã, examples≥12/60 và≥2/mã; D_U−Original>0,
≥3/4 mã tăng, D_U−A≥0, mean ΔMDD≤2 và max ΔMDD≤5 đpt. Chỉ xét U_full.
Trượt thì không chạy xác nhận để cứu kết quả hoặc nominate ablation thắng.

Sau nomination và release đủ điều kiện, xác nhận dự kiến 128 điểm/32 mỗi
mã/tám mỗi quý. Lịch chỉ theo eligibility, step3 neo phiên đầu 2025, cycle
kết thúc trong quý; N≥8/mã/quý và lấy floor(j*(N−1)/7), j=0..7. Không đọc
payoff để chọn ngày hoặc giảm mẫu sau outcome. Đây còn là công việc U11.

Phân tích xác nhận đăng ký circular moving-block bootstrap theo cutoff
date, giữ các mã/nhánh cùng cụm; L=4, 10.000 draw, PCG64 seed=20261024.
Reset cùng seed từng L; nối block modulo, cắt đúng n_dates và dựng lại tài
khoản theo thứ tự tổng hợp, không sắp lại ngày gốc/cộng cycle returns. Draw
thiếu mã/nonfinite invalid; cần≥9.500 hợp lệ, không sinh bù. CI percentile
linear 95% cho U−Original; Bonferroni family bốn contrast U−A/U−stats/
U−examples/U−Numeric dùng CI98,75%, cùng resampling indices. L=2/8 là sensitivity.
Sharpe/Sortino giữ metric chu kỳ v2, không annualize √252.

CI primary có cận dưới>0 mới hỗ trợ hữu ích hơn Original trên cohort đủ
điều kiện; CI U−A>0 sau hiệu chỉnh mới hỗ trợ hơn A. Hai ablation đo đóng
góp block tương ứng, không cô lập mọi cơ chế; examples-only vẫn có s/n.
CI qua 0 là inconclusive, không là tương đương; chỉ Numeric thắng không
được quy cho ICL. CI điều kiện saved Decision, không bao trùm training/
provider uncertainty. W9 được báo riêng, không cộng gain các phiên bản.

## 8. Planning, bằng chứng hiện có và phần còn chờ

MDE U10-09 dùng 647 query train, complete-case 152 cụm đủ bốn mã/608 row,
không lấy Decision/outcome development mới. Proxy LONG=0,5, flip đối xứng,
action chung giữa mã và location shift terminal D là giả định planning.
54 scenario báo calibration gộp/từng năm, L=4/2/8, bất đồng 0,10/0,25/0,50;
5.000 path và swap antithetic cho 10.000 draw. MDE80=q97,5%−q20% của null,
không phải power LLM quan sát hoặc bootstrap CI nêu ở mục 7. Layout 128
giả định chưa là lịch 2025; không chứng nhận đủ power hoặc chỉnh N theo MDE.

Các số sau là nghiệm thu kỹ thuật, không phải hiệu quả kinh tế: memory 976,
λ=8 khóa train, 41/60 mode task và 19 off, 34/60 có ≥2 task; prior U_full 51/60,
examples 41/60, prompt tối đa 4570 và prefix 518 ký tự (U tối đa 406). U10-09
đã qua compileall, 1111 unit, E2E, 248 leakage; source/SDK/receipt và oracle
MDE/repeat được đối soát. Các file/hash/số liệu chi tiết ở README W10.

Tại bàn giao W10 chưa có API/preflight thật, primary/repeat LLM hoặc payoff
query U-BICL mới; observed common support=0, report planned INCOMPLETE.
Nomination, release development/xác nhận và kiểm định thống kê thật còn ở
U11. Chương kết quả chỉ được bổ sung sau verified run; kết quả bất lợi,
insufficient evidence và giới hạn exposure/noise đều phải được công bố.

Tài liệu [đặc tả phương pháp gốc](../../methodology_spec.md) và kết quả W9
giữ vai trò lịch sử. Khi viết luận văn dùng rõ phiên bản U-BICL này, tránh
ghép thiết kế hoặc gain của các vòng đã rút thành một thí nghiệm duy nhất.
