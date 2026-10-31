# Protocol Conditional MT-BICL Advisor v4

Đặc tả W11-17, ngày 31/10/2026. [Protocol máy](protocol_v4.json) là nguồn
tham số; [checklist](README.md#5-checklist-w11) quản lý tiến độ. Đây là khóa
thiết kế, chưa phải release train, development hay xác nhận. Namespace mới
`outputs/bayesian_benchmark/mt_bicl_v4/`; nguồn, receipt và kết quả v1–v3
giữ nguyên. W11-18 kiểm dữ liệu trước khi fit bất kỳ mô hình mới nào.

## 1. Giả thuyết và giới hạn

Learner học `q(r_net | x_query, D_prior, C_target)` từ episode thực, với
ranh giới task và loss trên target query. Giả thuyết cần kiểm: prior tasks
cung cấp thông tin ngoài target-only/pooled, dự báo đủ tốt để policy cải
thiện Original. Chưa có kết quả v4 hoặc bảo đảm gain. Student-t, feature
tài chính và policy sử dụng Original là thiết kế của đề tài.

[Paper §4/§5](https://arxiv.org/html/2606.20538v1) mô tả học predictive
distribution từ prior/target tasks; [công bố](https://proceedings.mlr.press/v306/zhu26aj.html)
không xác nhận hiệu quả của cấu hình giao dịch này. Bộ kiểm metadata trong
task này không chứng minh learner đã học Bayes hoặc thị trường có tín hiệu.

Không trần giờ, hạn lịch, counter elapsed hoặc charge khi crash/resume.
Không kế thừa guard thời gian v3. Quota/backoff, checkpoint, integrity,
registry hữu hạn, số bước optimizer và early stopping theo validation vẫn
giữ: đây là thiết kế học, không phải giới hạn thời gian vận hành. Không
tự tăng trial, seed hoặc cỡ mẫu đến khi thắng. API do người dùng chạy,
agent chuẩn bị/kiểm offline; không đọc credential trong verifier.

## 2. Dữ liệu, exposure và nhãn

Universe cố định FPT/MWG/VCB/VNM, không chọn thêm mã theo return. Lịch VNINDEX
neo 02/01/2018, query chỉ số `20+3*j`, cycle cùng block 63 phiên. Dùng đúng
nguồn giá thực thi thô VCI/nghìn VND và barrier quyền hiện có. Sampling
theo lịch/khả năng thực thi trước outcome; không loại query vì missing X.
W11-18 đóng danh sách ID, lý do thiếu, file nguồn và hash trước fit.

LONG mua Open(t+1), bán Close(t+3); SHORT=CASH; phí 0,25% và trượt giá
0,10% mỗi chiều. Nhãn `r_net` dạng fraction luôn từ
`compute_round_trip_net_return`; `y_sign=int(r_net>0)`. Không dùng label
Close-to-Close, không trừ phí lần hai. Mỗi mã một account 50 triệu, cổ
phiếu phân số như account đã nghiệm thu; không mở vị thế chồng lấp.

| Miền | Quyền dùng |
| --- | --- |
| 2018–2020 | Fit weights và hyperprior; train episode phải giữ PIT tại query |
| 2020/2021/2022 outer | OOF phát triển đã exposed, kiểm dự báo và policy; không là test độc lập |
| 2023 | G60 stress/development đã xem; không chọn hyperparameter/checkpoint/calibration/h |
| 2024 | W9/reference đã exposed, không xác nhận mới |
| 2025 | Đã kiểm nguồn, independence chưa chứng minh; chưa mở payoff hoặc release |
| Forward | W12 audit exposure và khóa cohort sau candidate; không deadline |

V1/v2/v3 không được đổi tên hoặc reset exposure. Hosted LLM có thể mang
tri thức hậu kỳ trong weights: PIT input không loại hết giới hạn đó.

## 3. X, task và hỗ trợ

Chín feature numeric: momentum5/20, sample volatility20, khoảng cách
SMA20, MACD histogram12/26/9 chia Close trên prefix45, volume tương đối20,
biên High–Low20 chia Close, momentum20/volatility20 của VNINDEX. Công thức
và xử lý zero volume được ghi trong JSON. Không dùng dấu bucket để lọc.

Agent X gồm trend, pattern, indicator consensus, alpha consensus và a0;
hai feature xung đột tính từ các category đã biết. Parser ba báo cáo đầu
dùng đúng `core.historical_signals.report_signal`; alpha dùng đa số năm
factor có provenance, a0 từ Original durable. Không suy agent X từ label,
không biến confidence chữ thành xác suất, không thêm feature sentiment
mới. Sentiment trong Original/Alpha vẫn phải có ngày và cutoff đúng.

Không bịa báo cáo còn thiếu. W11-18 audit coverage trước; nếu cần tạo
report, người dùng chạy API trên snapshot PIT, upstream một lần/point và
dùng chung. Adapter mới phải kiểm yêu cầu warmup của Alpha; không hạ
warmup hoặc tự thay signal để lấp lịch sử. Model/prompt/options ghim từ
baseline; đổi model cần amendment trước thu thập.

Scaler numeric mean/sample-std chỉ fit train prefix của đúng fold;
std floor `1e-8`, category one-hot và missing mask riêng. Khi dựng episode
train lịch sử, scaler/hyperprior không được nhìn sau query đó. Khi đánh
giá outer, dùng scaler fit train của fold cho toàn D/C/query; không dùng
z cũ từ scaler khác. Feature lịch sử kết thúc tại ngày lịch sử của nó.
Regime historical-prefix fit không sau đầu block và cutoff train fold;
UNKNOWN khi thiếu 499 phiên được phép, không thay bằng model fit tương lai.

Prior cùng mã, khác target block, cả block đã kết thúc trước query. Mọi
observation exit<query; D/C/query không trùng ID hoặc khoảng entry–exit.
Rank bằng khoảng cách numeric chuẩn hóa + phạt 0,25 nếu regime đã biết
khác nhau; tie theo exit mới nhất rồi ID. Chọn observations bằng distance,
không dùng y/r_net; target lấy observations đóng mới nhất trong block.
Nạp nhãn chỉ sau khi đóng membership. Không điều kiện 5 thắng/5 thua.

Train K∈{0,1,3,5,8}, M≤32, m∈0..32; runtime K tối đa3 và lấy K lớn nhất
đã train không vượt số task có thật (2 task → K1). Không lặp để đủ K/M/m.
K0/m0 hợp lệ; No_target recompute cùng learner với C rỗng đã nằm trong
miền train. Numeric input learner không bị ép vào giới hạn card 600 ký tự.

Missing required numeric/agent hoặc |z|>6 giữ đúng a0, vẫn giữ query trong
G. Regime UNKNOWN được phép. Lỗi PIT/source/API/integrity phải raise và
checkpoint, không thành fallback. W11-18 cần tối thiểu mỗi mã: 100 cycle
train/4 task, 30 cycle mỗi outer, agent hợp lệ≥70% từng outer và≥60 cycle
train. Inner fit có ngưỡng riêng 60 cycle/2 task/40 agent-valid, vì lịch
ngắn hơn. Thiếu thì `INSUFFICIENT_DATA`; không tự resplit hoặc thay
candidate bằng price-only. Coverage và drift báo cả theo fold/mã/regime.

## 4. Folds và registry trước outcome

| Outer | Fit weights tối đa | Inner dùng chọn cấu hình |
| --- | --- | --- |
| 2020 | 31/12/2019 | 2019H1 train≤2018; 2019H2 train≤30/06/2019 |
| 2021 | 31/12/2020 | 2020H1 train≤2019; 2020H2 train≤30/06/2020 |
| 2022 | 31/12/2020 | Hai inner 2020 như trên; không fit weights 2021 |

Purge mọi fit row có exit sau fit_end hoặc exit≥evaluation_start, kiểm
khoảng entry–exit chồng interval đánh giá. Không chỉ chia theo as_of.
Context outer được streaming khi mature, không gradient/refit/scaler lại.

**Làm rõ đề xuất W11-16:** bỏ việc dùng 2021 chọn checkpoint; mọi cấu hình,
checkpoint/step và calibration/h chọn bằng inner. 2021/2022 là outer report
và gate. Cấu hình cuối chọn chỉ bằng inner2020H1/H2, weights fit≤2020;
final steps là median best inner steps làm tròn. Không chọn bằng outer
hoặc G2023. Outer2022 cùng cutoff train2020 là chủ ý giữ hợp đồng final,
không gọi nó là refit đến2021. Mọi fold và seed đều phải báo.

Registry baseline: Student-t mean0; ridge α∈{0,1;1;10}; target-only
reference; HistGradientBoosting nhỏ leaf∈{7,15}, 100 iteration, các tùy
chọn còn lại cố định trong JSON. Scale predictive lấy từ train OOF, không
fit bằng residual outer. Base fit2018 dùng leave-task-block-out trong fit.
Mô hình có X numeric/regime và X đầy đủ được báo riêng; không chọn một
family khác sau khi thấy2023.

Reference phân cấp có `r_net~t5(phi(x)ᵀw_task,sigma_task)`, latent task
shrink về beta_regime, beta_regime shrink về beta_pool train. Tau multiplier
∈{0,1;1;10}; prior/scale và Gibbs Normal–Gamma được khóa trong JSON.
Bốn chain ×1.000 warmup +1.000 draw; kiểm rank split Rhat≤1,01,
bulk/tail ESS≥400, MCSE(mean)/predictive_sd≤0,02. Không đạt thì inference
unresolved; không tự thêm draw hoặc gọi đó là bằng chứng likelihood sai.
Đối soát Gaussian conjugate limit/scalar trước đo thị trường. Reference
không được gọi là truth thị trường.

Learner có hai capacity cố định (64×2 layer hoặc128×4), 4 heads,
mixture3 Student-t df5; causal/pad masks và marker prior/target. Mean,
scale>0 và weights softmax từ cùng head. Loss NLL chỉ target query; không
đưa query r vào input, không học label prior bằng auxiliary loss. Không
synthetic pretrain hoặc distillation teacher ở revision này. Synthetic
conditional chỉ kiểm cơ chế, với seed/intervention/threshold khóa trước.

LR∈{0,0003;0,001}; seeds42/137/271 dùng toàn bộ, trộn đều distributions,
không chọn seed thắng. AdamW/batch/regularization/step/patience trong JSON.
K0/pooled/no-agent được train đối chứng đúng cấu trúc, cùng capacity và
search budget; không chỉ cắt prefix gây OOD. Pooled giữ observations,
bỏ ranh giới task; no-agent bỏ toàn bộ agent X nhưng policy vẫn dùng a0.
Không mở rộng capacity hoặc registry khi kết quả ngoài inner không đẹp.

## 5. Metric, calibration, policy và gate

Metric forecast chính CRPS: mean đều ngày trong mã, đều bốn mã; aggregate
đều ba outer. Cùng 4.096 quantile cố định và oracle CRPS scalar; không
đếm episode resampling là thêm quan sát độc lập. Báo NLL, MAE, Brier/ECE,
PIT, coverage/width50/80/95 theo fold/mã/regime, mọi failure và support.
Missing/OOD forecast dùng chung price-only pooled baseline fit train để
chấm toàn G; báo common support riêng. Action missing/OOD luôn giữ a0.

Calibration chọn identity hoặc affine distribution `r_cal=b+a*r`, a>0,
fit/nested crossfit chỉ inner OOF với bounds/optimizer cố định. Identity
thắng tie. p(r>0) và mean lấy từ cùng calibrated distribution, không ghép
count model với magnitude model khác. Predictive return quantile không
được gọi là CI của expected utility.

Crossfit calibration theo thời gian: H1 dùng identity, H2 chỉ fit map từ
OOF H1; score lựa chọn không lấy map H2 áp ngược H1. Sau chọn, refit map
cuối trên OOF hai inner. Mỗi numeric family chọn map bằng cùng rule/budget;
h do Full chọn dùng chung Full/K0/pooled/no-target/no-agent/reference.

Policy đề xuất LONG khi μ_net>0, còn lại CASH; chỉ sửa a0 nếu
`(I[a=LONG]-I[a0=LONG])*μ_net > h`. h∈{0;0,001;0,0025} dạng fraction là
tolerance, không trừ thêm phí. Chọn h và map bằng regret tài khoản inner
so Original, dưới guard MDD; ties ưu tiên h nhỏ/identity. Risk guard
mean ΔMDD≤2 và max≤5 đpt mỗi fold. Final calibration fit inner2020 OOF;
không fit lại bằng outer. Q10-veto và Fact_Anchor v3 không nằm trong v4.
Card chỉ giải thích action đã tính, không có LLM thứ hai đổi action.

| Mốc | Điều kiện đi tiếp |
| --- | --- |
| W11-18 | Source/PIT/lineage/nhãn/overlap và mọi ngưỡng support PASS |
| W11-19 | Reference inference đạt; CRPS thấp hơn baseline thắng inner trên aggregate và≥2/3 outer |
| W11-20 | Mask/loss/PIT đúng; synthetic known-model interventions đạt threshold, không suy thành gain thị trường |
| W11-21 | Full CRPS hơn baseline/K0/pooled/No_target trên aggregate và≥2/3 outer từng contrast; D OOF Full−Original>0, MDD guard từng fold đạt |
| W11-22 | Adapter OFF=Original100%, P0/caller/retry/checkpoint/leakage đúng nguồn; freeze candidate/data/prompt/options/order/repeat và release riêng |
| W11-23 | Đủ mọi slot primary/repeat, không pending/unknown chưa giải quyết |
| W11-24 | Cold rebuild independent accounts và nomination đúng rule dưới đây |

Không có tín hiệu thì dừng pha, ghi diagnosis và cần revision mới trước
nghiên cứu tiếp. PASS kỹ thuật hoặc synthetic không thay gate thị trường.

## 6. Development, nomination và W12

G60 đã khóa ID ngay trong JSON, FPT12/MWG16/VCB16/VNM16. Original mới
durable cho mỗi block v4, cùng legacy prompt/schema/model/options; không
dùng action Fact_Anchor/raw proposal v3 để giả lập v4. Upstream lịch sử
chỉ reuse khi snapshot/identity/canonical đúng; bất tương thích phải xử lý
trước release, không tự gọi vision riêng cho nhánh. A_reference giữ W9
adapter; Plain_ICL cùng membership với Full, projection label-blind,
prefix≤600 và toàn prompt<6.500; không có numeric learner output.

| Nhánh | Quyết định |
| --- | --- |
| Original / A_reference / Plain_ICL | 3 nhánh LLM, cùng upstream; Original đầu |
| Full_conditional_MT | Candidate duy nhất: full learner + a0 + policy đã khóa |
| Target_only_K0 / Pooled_context | Learner train đối chứng + cùng a0/policy |
| No_target | Recompute Full với C rỗng |
| No_agent_features | Learner train/test bỏ agent X, cùng a0 ngoài policy |
| Numerical_MT | Full distribution, LONG iff μ>h, còn lại CASH; a0 chỉ dùng khi fallback, distribution Full vẫn có agent X |
| Hierarchical_reference | Reference cùng input và policy, chỉ chẩn đoán |

Primary 60×10=600 dòng action,180 slot LLM. Repeat12 point×3 lượt bổ
sung×(10+Original_duplicate)=396 dòng,144 slot LLM; tổng996 dòng/324 slot
LLM danh nghĩa, chưa tính control/retry. Không gọi API theo số numeric
models. Duplicate UUID độc lập, cùng canonical body; không vote hoặc gộp
repeat vào N primary. Mọi nhánh trong block dùng đúng a0 của block đó.

12 repeat ID sẽ được vật hóa trong manifest W11-22 trước response v4 đầu:
ba/mã, chọn subset thỏa cả hai hướng Original v3 nếu có, tối đa hóa số
strata m_v4∈{0,1..3,≥4}, tie tuple ngày/ID nhỏ nhất. Original v3 chỉ dùng
stratify mẫu đã exposed, không làm quyết định nền v4. Nếu một hướng không
tồn tại thì công bố non-estimable; báo hướng Original v4 thực tế, không
đổi sample sau response mới. m_v4 lấy từ dataset đã đóng W11-18, không
được chọn bằng outcome hoặc Full action. Lịch nhánh và duplicate theo JSON.

Nomination: đủ G/integrity; D Full−Original>0;≥3/4 mã tăng; Full−A≥0;
Full−K0>0; Full−pooled>0; mean ΔMDD≤2/max≤5 đpt so Original. D là mean
đều bốn account lãi kép, không cộng cycle return. Chỉ Full được xét, không
promote ablation hoặc seed/repeat. Không đạt: NOT_NOMINATED, confirmation
NOT_RUN; không sửa gate hoặc mở2025 để cứu kết quả.

W12-01 audit independence; W12-02 khóa cohort/power/N/block-length trước
outcome. N và block-length hiện null có chủ ý, không tự kế thừa128/L4.
Primary CI95%; family8 secondary CI99,375%, bootstrap10.000 draw/ít nhất
9.500 finite, seed20261031. Các tham số W12 chưa phải quyền chạy xác nhận.
Mục tiêu rõ rệt D≥1 đpt và CI95%>0 cùng dispersion/MDD guard, chưa là
claim v4. Báo kết quả âm/inconclusive và adaptive exposure đầy đủ.

## 7. Khóa nguồn và nghiệm thu spec

Protocol pin byte parent, baseline source, nguồn giá và prefix5.206 ledger
rows; cho append, cấm sửa/reset. Plan ban đầu đọc từ object Git78337a4,
không dùng README tiến độ mutable làm hash runtime. Lock ghi source commit
verifier/test và protocol đã commit; cold verify đối chiếu Git/byte/runtime.
Không ghi `.env`, không mở payoff2025, không fit/forward trong verifier.

```powershell
py -3.13 -X utf8 scripts/verify_mt_bicl_protocol_v4.py
```

Đây chỉ là replay **SPEC_LOCK_PASS**. Fixture metadata kiểm purge/PIT/ID/
độ dài và query label poison; chưa kiểm X thực, inference hoặc model v4.
Các gate test triển khai sau được đăng ký trong `required_tests` của JSON;
W11-18–25 vẫn TODO cho đến có bằng chứng riêng đúng source.
