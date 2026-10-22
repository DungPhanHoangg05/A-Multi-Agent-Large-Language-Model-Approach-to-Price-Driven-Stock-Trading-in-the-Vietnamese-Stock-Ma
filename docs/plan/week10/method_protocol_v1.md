# Protocol phương pháp Bayesian ICL v1

Version: `bic_icl_method_protocol_v1`. Khóa ngày 22/10/2026, trước API
revision. Đây là đặc tả nghiên cứu cho W10–W12, độc lập checklist tiến độ;
chưa là schema/runtime/manifest hoặc release cho phép chạy. Sửa ngữ nghĩa
sau lock phải phát hành version mới và ghi tác động, không ghi đè v1.
Hash chuẩn hóa LF/UTF-8 được pin tại [README W10](README.md).

## 1. Giả thuyết, đối tượng và giới hạn

Đối tượng là bốn mã FPT/MWG/VCB/VNM, trên lịch đã khóa, Decision LLM hosted
và hợp đồng LONG T+2.5. Thích ứng miền từ
[Zhu, Oermann, Cho (ICML 2026)](https://proceedings.mlr.press/v306/zhu26aj.html):
paper huấn luyện transformer để học predictive inference qua chuỗi task;
revision này tính posterior ngoài LLM rồi đưa thống kê/ví dụ vào context.
Không nhận là tái hiện amortized hierarchical Bayes hoặc chứng minh cơ chế
suy luận bên trong LLM. Confidence của LLM không là posterior đã hiệu chuẩn.

| Thành phần | Định nghĩa khóa | Cách kiểm / giới hạn |
| --- | --- | --- |
| Bayesian | Beta posterior của sự kiện LONG ròng >0, empirical Bayes cùng mã | Oracle counts/partition/CrI/PIT; CrI có điều kiện trên hyperprior plug-in |
| ICL | Ví dụ lịch sử x→y xuất hiện trước query, không cập nhật trọng số LLM | Request và sidecar chứng minh nội dung; full so stats/examples trên cùng base |
| Multi-task | Nhóm `(symbol, regime, block_20_sessions)` với hai cycle/task | Task ID/boundary, không gọi một cycle là một dataset nhiều quan sát |
| Policy | LLM giữ quyền chọn LONG/SHORT; Numeric_only là heuristic riêng | Không có risk overlay hoặc chặn LONG theo posterior trong nhánh LLM |

Giả thuyết chính: `H0: D_selected−Original ≤ 0`, `H1: D > 0`; bằng chứng
xác nhận dùng CI hai phía 95% có cận dưới >0. Bốn giả thuyết phụ đo
selected−A, full−stats, full−examples, full−Numeric_only; giữ family riêng
và Bonferroni. Full−stats kiểm giá trị tăng thêm của demonstrations;
full−examples kiểm phần statistics. Cả hai không chứng minh LLM thực hiện
Bayes. CI qua/chạm 0 là inconclusive, không là tương đương.

## 2. Nguồn, split và hợp đồng kinh tế

| Tập | Vai trò và điều kiện |
| --- | --- |
| Bank 852 episode 2020–2022 | Giữ nguyên byte; 2020 bootstrap, query train 2021/2022 theo fold PIT hiện có |
| 2023 | Giữ nguyên 60 point ID: FPT=12, MWG/VCB/VNM=16; development exploratory duy nhất |
| 2024 | Đã xem và ảnh hưởng thiết kế; chỉ kết quả W9 riêng và nguồn upstream revision, không chọn lambda hoặc xác nhận lại |
| 2025 | Giữ nguyên 128 điểm/41 cutoff tại input audit v2, 32/mã, tám/quý; chỉ mở sau selection/gate/release |
| Forward | Nếu exposure mất điều kiện, đăng ký cohort sau lock riêng; không dùng run 2026 có sẵn giả làm forward |

W10-01 đã PASS giá/lịch/exposure theo khai báo và inventory local, không
chứng minh chưa từng xem outcome. Pin byte input audit v2
`9f1c2fed3a8955107ecb63f83da7651fd3a3f17c6e9a964c4ab5092d2c4a75f8`.
Không sửa receipt này để giả rằng protocol/candidate/release đã hoàn tất.
Consumer sau phải bind thêm các điều kiện đó bằng artifact riêng.

LONG mua Open(t+1), bán Close(t+3); SHORT=CASH. Phí 0,25% và slippage
0,10% mỗi chiều, qua `compute_round_trip_net_return`; không trừ phí lần
nữa khi ghép return. Engine hiện hữu dùng cổ phiếu lẻ, toàn bộ cash,
50.000.000 VND/mã, price_multiplier=1000; không tự thêm làm tròn lô 100.
Ước lượng D là trung bình đều bốn chênh return tài khoản, đơn vị đpt:
`D = sum_s (R_selected,s − R_Original,s)/4`. Không là mean cycle hoặc
return của một portfolio tái cân bằng. MDD tính từ equity path cùng engine.

Giữ lưới 2025 step=3 neo phiên đầu năm, cycle đóng trong quý; rank tám
ngày/quý là `floor(j*(N−1)/7), j=0..7` sau loại quyền/thiếu giá. N<8 hoặc
lỗi một nhánh → BLOCKED/INCOMPLETE; không thay điểm, giảm mẫu hay điền CASH.
Tập ngày cụ thể phải kế thừa nguyên `calendar.selected` của audit v2.

## 3. Memory và posterior

Memory revision là union bank gốc với tối đa 124 upstream point đã khóa
(60 năm 2023, 64 năm 2024), dedup bằng cycle ID và provenance nguồn; không
chọn record theo outcome hoặc gọi LLM sinh bank. Compatibility kiểm schema,
signal/model/options, feature PIT và giá thô/quyền; không chứng minh được
thì loại có reason. Không lấy Decision action/confidence/justification làm
feature. Nhãn cycle từ hàm kinh tế chung. Query phải cắt giá/tin≤cutoff,
bỏ tin không ngày; chỉ cycle `exit_date < cutoff` mới vào mọi bước.
Không append cycle 2025 vào memory xác nhận, kể cả đã đóng.

A/R/Numeric dùng cùng bank/index/source snapshot theo query. HMM/scaler
train-only; train query dùng đúng prefix HMM và scaler fold đã purge.
Index revision cần miền query 2025 riêng với scaler kết thúc 2022 giống
nguyên tham số đã khóa; không sửa hoặc bỏ validator miền 2023/2024 legacy,
không refit bằng 2023–2025. Thiếu nguồn/proof là lỗi integrity, không là
prior-off thông thường. Future append invariance là kiểm bắt buộc.

Phân hoạch trên các cycle cùng mã đã qua PIT, không áp similarity/tuổi
examples vào counts statistics; ba tập rời nhau, không nhân trọng số:

- C: cùng regime query và khớp **Trend/Pattern**; không điều kiện Alpha/Indicator.
- B1: cùng regime nhưng không thuộc C.
- B2: regime khác; không pooling chéo mã.

Với `s_i=sum(1[net_return_long>0])`, `n_i` là số cycle của tập i:

```text
m2 = (s2+1)/(n2+2)
m1 = (s1+lambda*m2)/(n1+lambda)
a = sC + lambda*m1
b = nC-sC + lambda*(1-m1)
p = a/(a+b); CrI95 = [Beta.ppf(.025,a,b), Beta.ppf(.975,a,b)]
```

`n2=0` cho m2=0,5 với reason thiếu background, không giả support. Counts
n=0 vẫn được ghi; posterior thuần số có thể tính nhưng không trình như
conditional evidence đã quan sát. Chỉ metric `win_rate_long` dùng pooling
mới; không tự suy posterior mới cho các metric trap/error legacy.
CrI không gồm toàn bộ bất định hyperprior hoặc phụ thuộc giữa cycle.

Stats ready khi `nC≥5`, `n1+n2≥20`, CrI width≤0,75, so trước làm tròn.
Examples là block riêng: population cùng mã/regime `nC+n1≥20`, feature/
scaler AVAILABLE, có ví dụ đủ điều kiện (R_task có ít nhất một task đủ hai
cycle). Full hiển thị từng block ready; stats-only/examples-only chỉ giấu
block tương ứng, giữ base/IDs/counts/ranking. Hai block off mới là prior-off.
Không dùng posterior mean làm gate evidence của nhánh LLM.

Lambda chỉ thuộc {2,4,8}; R_pool/R_task dùng cùng lambda. W10-04 tái dùng
651 query train và proof fold hiện có, lọc trước ranking/scoring; cả ba
lambda được đánh giá trên cùng giao posterior hữu hạn với A. Không có
posterior giữ missing, không gán p=0,5. Mean log loss theo query, clip p
vào [1e−6,1−1e−6]; tie tolerance 1e−12, rồi Brier, rồi lambda nhỏ hơn.
Giao rỗng → BLOCKED. Báo counts/loss từng lambda, fold/mã và raw/ready,
reliability bins [0;.2;.4;.6;.8;1]; không lọc theo readiness riêng từng lambda.

Chọn lambda cuối dùng train kết thúc 2022 trước development 2023. Loss trên
train dùng chọn lambda là chẩn đoán có selection bias, không là ước lượng
không chệch của calibration OOS; không trình lambda đã chọn bằng toàn train
như một lựa chọn online có sẵn ở query 2021. HMM/scaler/thống kê của mỗi
prediction vẫn đúng prefix; báo tất cả lambda để tránh giấu bước chọn.

## 4. Demonstrations, task và ngân sách

R_pool giữ selector từng cycle: K≤3, w_signal=0,5, half-life=365 ngày,
max age=730 ngày tính từ as_of_date, min_similarity=0,625, min gap=5 phiên,
seed metadata=42, scope same_symbol/same_regime. Bốn feature là
momentum_5, momentum_20, volatility_20, ma_distance_20, chuẩn hóa bằng
scaler train của query. Ranking/recency/tie ID giữ selector legacy; loại
entry–exit overlap, không bù bằng cycle khác regime hoặc ví dụ giả.

R_task giữ posterior R_pool; chỉ demonstrations thay đổi. Neo block vào
VNINDEX **2018-01-02** của lịch đã bind: `block_id=floor(session_index/20)`
với index0 tại ngày neo. Không neo lại theo query, regime hoặc năm.
Task ID gồm symbol/regime/block_id của **as_of_date** cycle; task chỉ dùng
cycle đủ PIT/tuổi/similarity và feature hữu hạn. Centroid là mean bốn vector
đã chuẩn hóa train của các cycle đủ điều kiện trong task, không dùng nhãn.

Xếp task theo khoảng cách RMS centroid–query tăng, ngày as_of mới nhất của
task giảm, rồi task ID tăng. Trong mỗi task, duyệt rank cycle legacy để
lấy hai cycle thỏa gap/không overlap, tie ID cố định; task không đủ hai bị
loại. Duyệt task đã xếp, giữ diversity/không overlap trên toàn demonstrations;
nhóm không còn đủ hai bị bỏ, tiếp tục task kế tiếp. Tối đa ba task/sáu cycle;
không cân bằng thắng/thua hoặc chọn task theo return. Các ví dụ không được
cộng lại vào posterior; overlap với population statistics không là quan sát mới.

Context phải giữ legend x=T/P, y gồm nhãn LONG thắng/thua và return ròng %,
task boundary và x→y mỗi cycle. Return hiển thị hai chữ số thập phân;
nhãn thắng/thua lấy dấu số gốc, không suy từ số % đã làm tròn. ID/feature/
nhãn gốc và ordering đầy đủ trong sidecar. BRPP≤600 ký tự; toàn prompt
Decision<6.500; distill/cap giữ nguyên. W10-05 cần fixture biên 3×2, hai
ngôn ngữ và return lớn/nhỏ/zero; không đạt thì R_task BLOCKED trước API,
loại cả full/stats/examples của nó, không cắt nhãn hoặc nâng trần.

## 5. Request, ma trận và repeat

Giữ agent `openai/gpt-oss-20b`, graph `qwen/qwen3.8-27b`, temperature=0,
max_tokens agent/graph=2048/1024; tiếng Việt, window45, daily1d,
norm=zscore_tanh, alpha_weights=None. Agent reasoning low/hidden; graph
none/hidden; SDK max_retries=0, service_tier=on_demand như plan W8 đã khóa.
Tên model ở đây kế thừa cấu hình nguồn, không là xác nhận provider vẫn
phục vụ; preflight người dùng phải kiểm capability/quota trước run.
Không thêm seed LLM chưa được hỗ trợ hoặc fallback model giữa cohort.
Risk OFF, schema Decision legacy, retry wrapper/backoff/ledger/UUID/checkpoint
hiện hữu; không reset quota khi đổi namespace hoặc tạo HTTP attempt giả.

Original chạy đầu mỗi point/repeat, response durable trước các nhánh.
Upstream một lần/point, deep-copy cho mọi nhánh và repeat. Khi prior-off và
**toàn canonical request** (messages/model/options/schema) giống Original,
reuse cùng point/repeat với source hash/origin/reason. Request khác thì gọi
riêng qua wrapper. Stats-only hai R giống toàn request thì alias một Decision;
giữ ID logic/source reference, không nhận alias thành mẫu độc lập. Duplicate
Original dùng invocation độc lập để chẩn đoán, không alias hoặc vote.

| Pha | Thứ tự logic cố định trước xoay | Nomination / số slot tối đa |
| --- | --- | --- |
| Development | Original, A_reference_shared_off, R_pool_full, R_pool_stats_only, R_pool_examples_only, R_task_full, R_task_stats_only, R_task_examples_only, Numeric_only | Chỉ hai full R; 8 LLM×60=480 +60 Numeric offline |
| Xác nhận | Original, A_reference_shared_off, selected_full, selected_stats_only, selected_examples_only, Numeric_only | Chỉ một selected; 5 LLM×128=640 +128 Numeric offline |

A là A_tp_pool giữ evidence/prompt nhưng dùng memory và shared-off revision
mới, không gọi là W9 chạy lại nguyên trạng. Numeric_only LONG khi p>0,5 và
stats ready, còn lại CASH với reason hợp lệ; p=0,5 → CASH. Lỗi/missing
execution không thành CASH. Không là Bayes utility tối ưu hoặc ứng viên ICL.

Point sort `(ngày, FPT/MWG/VCB/VNM)`; index j từ0. Original cố định trước,
xoay trái các nhánh LLM còn lại `j mod M` (M không tính Original/Numeric).
Nếu R_task BLOCKED trước API thì bỏ cả ba ID và khóa M mới trước run.
Không reuse action W8/W9 làm đối chứng mới. W11-01 chỉ reuse upstream nếu
verifier chứng minh identity tương thích **cho cả cohort**; không đạt thì
tạo một upstream mới/point cho mọi nhánh, khóa lựa chọn trước Decision.

Mẫu repeat 12 point: mỗi mã ba điểm, lần lượt earliest both-ready,
one-block-ready, off của R_pool; stratum rỗng bù ngày sớm nhất chưa chọn
cùng mã, ghi reason. Chỉ metadata/readiness PIT, không action/return.
Ba lượt bổ sung r=1/2/3, giữ primary upstream, thêm Original_duplicate.
Original trước, các nhánh LLM khác kể cả duplicate xoay
`(3*j+r−1) mod M`, j theo thứ tự mẫu repeat sau sort ngày/mã; Numeric offline
tính một lần. Development≤12×9×3=324, xác nhận≤12×6×3=216 slot LLM;
retry không là lượt khoa học. Repeat không nhập D primary, không chọn lượt
tốt nhất; báo disagreement với mẫu số và các contrast mỗi lượt/mean.

## 6. Selection, suy luận và điểm dừng

Eligibility candidate: đủ 60 point/common support, metric hữu hạn, bốn gate
PASS trên code/runtime hiện tại; prior visible≥6 điểm và≥1/mã; repeat đầy đủ
đã verify. R_task thêm≥6 điểm có≥2 task,≥1/mã. Promotable khi
D_R−Original>0, ΔR>0 ở≥3/4 mã, mean ΔMDD≤2 và max ΔMDD≤5 đpt,
D_R−A≥0. Trong tập promotable chọn D lớn nhất; tie≤1e−9 đpt chọn mean
ΔMDD nhỏ hơn, rồi R_pool. A/ablation/Numeric không tham gia nomination.

Chỉ một vòng development 2023, tối đa hai full R. Không promotable →
STOP_NO_IMPROVEMENT, không mở xác nhận để cứu kết quả; W9 vẫn là kết quả
phiên bản cũ, Original mặc định. R_task không khả thi trước API → chỉ R_pool;
R_pool cũng không đạt kỹ thuật → dừng revision, dùng W9 hoàn thiện luận văn.
Sửa lỗi sau xem outcome tạo revision riêng và giữ run cũ, không chọn run thắng.

Xác nhận giữ sáu nhánh logic, G=128 đầy đủ. Primary D_selected−Original;
secondary family đúng bốn contrast ở mục1. Circular moving-block bootstrap
theo **cụm cutoff date**, giữ mask mã và mọi nhánh cùng draw, dựng lại tài
khoản theo thứ tự draw; không sort lại ngày gốc hoặc đổi sang mean cycle.
10.000 draw, PCG64 seed=20261021, L=4; L=2/8 là sensitivity. Quantile linear;
CI primary95%, secondary98,75%; ≥9.500 draw hữu hạn không thiếu mã, không
sinh bù. Báo count từng mã/draw, invalid reasons và overlap. T both-ready
chỉ mô tả, không thay G hoặc family. CI điều kiện trên Decision/method đã
lưu, không bao gồm đầy đủ training/provider variability; repeat báo riêng.

## 7. Power audit trước outcome

N=128/32 mỗi mã và mask 41 cutoff giữ nguyên. Mục đích là báo MDE80 và độ
rộng CI dự kiến dưới proxy, không chứng nhận đủ power cho R chưa triển khai,
không đặt hoặc sửa ngưỡng MDE sau nhìn số. Không chọn N/candidate/λ/renderer
theo power; không có kiểm định kinh tế mới từ lượt phân tích này.

Nguồn nhiễu đăng ký trước tính: ba contrast C2/A_tp_pool/B_semantic so
Original từ Decision primary 2023 đã lưu, và Numeric A−C2 trên từng fold
train 2021/2022 (LONG nếu ready và p>0,5, còn lại CASH hợp lệ). Giữ cả năm
proxy, không chọn variance nhỏ. Chỉ ngày có đủ bốn mã cùng nguồn mới làm
donor joint: development7, train76/76 sau khi purge bốn cycle cuối2021
đóng sang2022 (trước purge fold2021 có77 ngày joint). Báo các ngày/record
bị thiếu theo lịch, không điền return thiếu bằng0. Numeric train không là
Decision LLM; purge của phân tích không sửa diagnostics gốc651 query.

Mỗi proxy dùng 10.000 draw circular theo donor date, L=2/4/8. Stream
`PCG64(SeedSequence([20261021, source_code, L]))`, source_code0 cho ba
contrast development cùng draw, 1/2 cho train2021/2022. Mỗi draw dài41,
áp nguyên mask 2025 với32 cycle/mã. Resample **cả tuple mã/nhánh**; ghép
growth factors sau phí thành vốn như engine, không cộng lợi nhuận cycle.

Đặt `Z = D_draw − mean(D_draw)`, quantile linear q. Với alpha=.05 hoặc
.0125, mô hình planning là dịch vị trí của distribution tài khoản:
`lower(δ)=δ+Z+q(alpha/2)`. Báo width `q(1−alpha/2)−q(alpha/2)`,
`MDE80=max(0,−q(alpha/2)−q(.2))`, tỷ lệ lower>0 tại δ=0/2/5/10/20 đpt
và Monte Carlo SE. Noise suy biến → UNINFORMATIVE, không gọi MDE0 là power.
Không có draw hữu hạn≥9.500 → BLOCKED, không sinh bù.

Đây là xấp xỉ location-shift cho percentile CI, không là simulation nested
với sampling/provider/training đầy đủ hoặc kết quả chính xác của kiểm định
xác nhận. Tỷ lệ tại δ=0 là chẩn đoán xấp xỉ, không khẳng định Type I error.
Giữ covariance donor nhưng không tái tạo autocorrelation/gap của lịch2025;
donor7 ngày 2023 và vòng L8 trên7 ngày đặc biệt yếu. Numeric train khác
phân phối LLM R. Báo toàn bộ proxy/block, main L4 và giới hạn; không dùng
envelope nhỏ/lớn như bound toán học của power R. Đủ audit không có nghĩa
đủ power; kết quả rộng/inconclusive vẫn giữ N và kết luận đúng giới hạn.

## 8. Bàn giao và điều kiện phát hành

W10-03 triển khai shared-off/alias/duplicate/recovery; W10-04 memory,
posterior/oracle/lambda và scaler revision; W10-05 task/renderer; W10-06
producer/loader/verifier/CLI ánh xạ đúng v1 vào protocol canonical/schema
riêng. Không hash README tiến độ như phương pháp. Code/spec/matrix/nguồn/
model/runtime/client/scaler/bank/prefix/schema/receipt phải được bind trước API.
W10-07 đủ bốn gate và dry-run; W11-01 khóa request/upstream/repeat metadata;
W11-05 selection; W11-06/07 kiểm lại nguồn, công cụ/bootstrap và release.

Không phát hành xác nhận khi thiếu bất kỳ exposure/giá/mẫu/protocol/power
audit/technical gate/candidate/manifest/release. Quyền thực hiện không thay
các bằng chứng này. Người dùng tự chạy API theo hướng dẫn sẽ được bàn giao.
Không thay W9, deploy default, economic contract hoặc mở ứng viên thứ ba.
