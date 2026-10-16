# Tuần 8 — Cải tiến Bayesian ICL, validation và khóa xác nhận

**Trạng thái: TODO, 0/8.** Kế hoạch điều chỉnh 16/10/2026; giữ deadline 10 tuần.
[Kế hoạch tổng](../plan.md) · [W7](../week7/README.md) · [W9](../week9/README.md)

## Mục tiêu và giới hạn

Cải thiện Bayesian ICL bằng một vòng có đối chứng, tối đa **hai cấu hình
phương pháp mới**. C2 NOT_PROMOTED là mốc nghiên cứu; Original vẫn là lựa
chọn triển khai. Không thay selection/report/checkpoint W7. Đầu vào là Gate D
mới của W7, report 60 điểm/11 nhánh và hồ sơ nguyên nhân W7-13.

Phân bổ dự kiến: 40% thời gian triển khai/kiểm offline, 35% validation và
phân tích, 25% khóa protocol/manifest/bàn giao. Đây là phân bổ công việc,
không yêu cầu dự toán hoặc lịch API. Đến phần khóa thì dừng tối ưu phương
pháp; lỗi integrity phải sửa hoặc chặn run, không bỏ gate để kịp deadline.

## Protocol cải tiến đã khóa tại W7-14

**Đặc tả `improvement_protocol_v1`, 16/10/2026.** Đây là quyết định phương
pháp trước API, chưa phải schema/registry/runner đã triển khai. Căn cứ là
[chẩn đoán W7-13](../week7/README.md#chẩn-đoán-development-và-kiểm-attribution-16102026):
11/60 stats ready, 8/60 cả hai ready và 3 bất đồng prior-off trên hai point.
W8-01 chỉ ánh xạ đặc tả này vào identity/version và kiểm khả năng thực thi;
không mở lại lựa chọn phương pháp hoặc sweep tham số theo return.
Sửa đặc tả phải có amendment/version và lý do trước API; nếu đã xem kết
quả thì công bố thay đổi và trạng thái exploratory, không ghi đè bản đã khóa.

| ID dành trước | Giả thuyết / thay đổi duy nhất | Đối chứng cô lập | Version dự kiến |
| --- | --- | --- | --- |
| `A_tp_pool` | Khớp cứng cả T/P/A/I làm thưa support; mở nhóm conditional sang khớp T/P, giữ co Bayes từ background rời nhau | C2 cùng query, retrieval, schema và cách trình bày; chỉ counts/posterior cùng mô tả điều kiện đổi | `conditional_tp_disjoint_beta_v1`, `compact_brpp_v3_tp_v1` |
| `B_semantic` | Ngữ nghĩa prefix có thể khó hiểu; trình bày rõ sự kiện, support và bất định | C2 cùng base evidence, visible IDs/counts/K, schema và chỉ dẫn ngoài prefix | `compact_brpp_semantic_v1` |

**A:** P giữ cùng mã/regime và exit<cutoff. C_A gồm episode có trend và
pattern bằng query, không dùng alpha/indicator để chia nhóm; B_A=P\C_A.
Giữ chính xác masks/numerator/denominator bốn metric của C2. Với mỗi
metric, s_C/n_C và s_B/n_B được đếm trên hai nhóm rời nhau;
m_B=(s_B+1)/(n_B+2), alpha_0=4m_B, beta_0=4(1−m_B), posterior
Beta(alpha_0+s_C, beta_0+n_C−s_C). n_C=0 vẫn mean/CrI=null;
n_B=0 dùng m_B=0,5. Không dùng P làm likelihood lần nữa. Counts nguyên,
mỗi cycle một lần; không weighted count, không học/sweep strength.
Template v3 chỉ đổi mô tả `C=khớp T/P/A/I` thành `C=khớp T/P` và version;
không đổi renderer ví dụ hoặc chỉ dẫn Decision. A kiểm khả năng tăng support
và chất lượng xác suất, không mặc định rằng nhóm rộng hơn có hiệu quả tốt hơn.

**B:** dùng nguyên evidence/gate C2, kể cả các block tắt. Render theo thứ tự
W/BT/TF/PF tương ứng `win_rate_long`, `bull_trap_rate`,
`trend_false_bullish_rate`, `pattern_false_bullish_rate`; metric không ready
ghi `N/A`, số mean/CrI làm tròn hai chữ số chỉ để hiển thị. Khung prefix:

```text
[BRPP v4] R={regime}; k={visible_k}; nP={population_count}; nC={conditional_count}
W={s}/{n}→{mean}[{lo},{hi}]; BT={...}; TF={...}; PF={...}
W=LONG ròng>0; BT/TF/PF=bẫy/sai tăng; tỷ lệ lịch sử khớp T/P/A/I.
Mean[CrI95%] plug-in, không P(query)/E(return); SHORT=CASH.
T/P/A/I:+ tăng,- giảm,0 trung tính; W/L=LONG ròng lịch sử.
{các dòng ví dụ giữ nguyên renderer và thứ tự C2}
```

Không có metric visible thì bỏ nP/nC và ba dòng thống kê, thay bằng
`Ví dụ lịch sử; không dự báo query; SHORT=CASH.`. Không có examples visible
thì bỏ dòng giải mã T/P/A/I và các dòng ví dụ. Không block nào visible thì
prefix rỗng. Giữ chỉ dẫn ngoài prefix và `TradeDecisionOutput` bảy field;
không thêm `prior_use`, không bắt model theo prior, không đổi risk policy.
Đây là thay đổi cách diễn đạt và bố cục chung; không quy riêng hiệu ứng cho
một từ hoặc một dòng. Dựng thử từ 29 evidence C2 visible cũ cho tối đa
453 ký tự; đây chỉ là QA bản nháp, chưa thay kiểm producer/token W8.

**Các hằng số:** cùng bank/index/scaler/model và lịch đã khóa; P≥20,
support conditional từng metric≥5, CrI width≤0,75, strength=4. Retrieval
giữ w_signal=0,5, half-life=365 ngày, max_age=730 ngày, similarity≥0,625,
gap≥5 phiên, K=3, seed=42, same_symbol. Không thay feature/corporate-action
guard để tăng coverage; không thêm regime mềm, cross-symbol, bank mới,
expected-return model, risk overlay hoặc A+B. BRPP≤600, prompt<6.500,
giữ distill/cap. Lỗi cấu trúc/PIT ném lỗi; thiếu support hợp lệ fallback
Original, giữ query trong mẫu. Mọi cấu hình thử đều được báo, kể cả kết quả âm.

## Checklist tuần 8

| Task | Công việc và đầu ra | Phụ thuộc | Trạng thái |
| --- | --- | --- | --- |
| W8-01 | Ánh xạ protocol W7-14 vào registry/version; kiểm khả năng thực thi, identity và audit byte prior-off | W7 Gate D | [ ] TODO |
| W8-02 | Triển khai thay đổi tối thiểu, producer/loader/verifier và version mới; không sửa artifact cũ | 01 | [ ] TODO |
| W8-03 | Kiểm posterior/PIT/fallback/token/paired; bốn gate kỹ thuật; khóa plan/output development mới | 02 | [ ] TODO |
| W8-04 | Người dùng preflight/run/resume theo hướng dẫn; Decision thật trên 60 điểm, mọi nhánh chung upstream | 03 | [ ] TODO |
| W8-05 | Verify toàn primary và đủ mẫu lặp; phân tích ΔR/MDD/coverage/ablation/prior-off và độ ổn định | 04 | [ ] TODO |
| W8-06 | Khóa selection mới và lý do; giữ ngưỡng W6-04, báo mọi cấu hình đã thử | 05 | [ ] TODO |
| W8-07 | Khóa ma trận, thống kê, manifest holdout 64 điểm; dry-run và kiểm công cụ phân tích bằng fixture | 06 | [ ] TODO |
| W8-08 | Nghiệm thu bốn gate, hash nguồn/runtime và hướng dẫn chạy/verify/resume W9 | 07 | [ ] TODO |

## Protocol development và tiêu chí chọn

Giữ nguyên 60 point ID/ngày 2023 từ plan development v2 (FPT 12, ba mã còn
lại 16); đây là **exploratory**, không là validation độc lập. Thứ tự nhánh
cơ sở gồm 11 ID:
`original, bayesian, C2, A_tp_pool, B_semantic, C2_stats_only, C2_examples_only,
A_tp_pool_stats_only, A_tp_pool_examples_only, B_semantic_stats_only,
B_semantic_examples_only`. Sáu nhánh content-mode là ablation đăng ký,
không là sáu phương pháp mới hay ứng viên để chọn theo return. Các ablation
C2 dùng schema legacy, không mượn C3 có schema tự báo prior-use.

Mọi nhánh dùng cùng upstream một lần/point và deep-copy. Tái dùng upstream
W7 chỉ khi verifier chứng minh nguồn/model/options/projection tương thích;
nếu không, tạo upstream mới một lần/point cho toàn bộ nhánh. **Toàn bộ
Decision primary chạy mới cùng identity**, không chép action cũ; bằng chứng
W7 chỉ là đối chiếu lịch sử. Model agent giữ `openai/gpt-oss-20b`, temp=0,
max_tokens=2048, reasoning_effort=low, reasoning_format=hidden; vision
`qwen/qwen3.8-27b`, temp=0, max_tokens=1024, reasoning_effort=none,
reasoning_format=hidden. Không thêm seed LLM; retrieval seed=42 không là
seed sinh Decision. Max_retries client=0, retry qua wrapper/pacer đã kiểm.

Primary mỗi point/nhánh có **một Decision hoàn tất**, repeat_id=0. Xếp point
theo (as_of_date, thứ tự mã FPT/MWG/VCB/VNM), đánh j từ 0; thứ tự nhánh là
xoay trái danh sách 11 ID j mod 11 bước. Resume giữ nguyên thứ tự/attempt;
HTTP retry hoặc sửa format không phải lượt lặp khoa học.

**Mẫu lặp 12 point, ba lượt bổ sung/request**, repeat_id=1/2/3, namespace
riêng sau khi đủ primary; không chọn lượt tốt nhất hoặc nhập repeat vào D.
Chọn bằng readiness C2 W7 đã verify, không dùng action/return/mean: mỗi mã
ba strata rời nhau S=stats ready (bất kể examples), E_ONLY=chỉ examples
ready, OFF=không block ready. Trong mỗi pool xếp ngày tăng; lấy đầu pool S,
trung vị dưới E_ONLY (chỉ số floor((n−1)/2)), cuối pool OFF.

| Mã | S: đầu (rank/pool) | E_ONLY: trung vị dưới (rank/pool) | OFF: cuối (rank/pool) |
| --- | --- | --- | --- |
| FPT | FPT-2023-06-27 (1/2) | FPT-2023-10-04 (2/3) | FPT-2023-12-22 (7/7) |
| MWG | MWG-2023-06-30 (1/2) | MWG-2023-03-06 (3/5) | MWG-2023-12-22 (9/9) |
| VCB | VCB-2023-03-06 (1/2) | VCB-2023-08-29 (3/6) | VCB-2023-12-22 (8/8) |
| VNM | VNM-2023-01-06 (1/5) | VNM-2023-06-30 (2/4) | VNM-2023-12-19 (7/7) |

Giữ cả mẫu đã có bất đồng VCB, nhưng không chọn vì bất đồng; không thêm
MWG-2023-07-05 riêng vì biết action. Strata lịch sử không đổi theo readiness
A/B mới. Lặp cả 11 nhánh và `original_duplicate` (bản sao request Original
nguyên byte, chỉ ID checkpoint khác). Xếp 12 point theo quy tắc trên, j=0..11;
ở lượt r=1..3 xoay trái danh sách 12 ID, duplicate đặt cuối danh sách cơ sở,
(3j+r−1) mod 12 bước. Mỗi vị trí bắt đầu xuất hiện ba lần trong 36 block;
upstream giữ chung với primary, không chạy lại vision. Giữ request cố định
qua ba lượt cùng point/nhánh; schema/model/options giống nhau ở mọi nhánh.
Audit hash UTF-8 prompt và canonical HTTP body (messages/response_format/
model/options) tại transport, loại credential/header khỏi artifact; byte
HTTP thô chỉ được khẳng định nếu thực sự đã lưu/đối chiếu. Lưu response
fingerprint, thời điểm và attempt để chẩn đoán, không coi là biến can thiệp.

Báo số action bất đồng trên ba cặp lượt (1,2)/(1,3)/(2,3) mỗi request,
original−duplicate cùng lượt và prior-off−original, đủ mẫu số/strata.
Các cặp phụ thuộc, không gọi là quan sát độc lập. So A−C2, B−C2, full−stats,
full−examples từng lượt và trung bình ba lượt; dựng tài khoản mẫu 12 point
riêng từ vốn đầu. Không gộp với 60 điểm hoặc dùng repeat để đổi nomination.
Không đặt ngưỡng thắng cho trace; thiếu repeat thì chẩn đoán INCOMPLETE,
chưa kết luận tách được nhiễu Decision. Không thay mẫu hay chạy lượt thứ tư.

Primary D là trung bình đều ΔR tài khoản bốn mã so Original. Giữ eligibility
của W6-04: đủ 60 điểm ghép cặp, metric hữu hạn, bốn gate PASS, prior visible
ít nhất 6 điểm và ít nhất một điểm mỗi mã. Promotion: D>0, ΔR>0 ở ít nhất
3/4 mã, trung bình ΔMDD≤2 và tối đa ΔMDD≤5 điểm phần trăm; tie-break kế thừa
selector cũ: tie trong 1e−9 điểm phần trăm quanh D_max, rồi mean ΔMDD nhỏ
hơn, rồi thứ tự ID cố định `C2, A_tp_pool, B_semantic`. Tập xét nomination
là ba full-prior này, C2 là đối chứng có thể giữ lại; ablation không tham gia.
Ưu tiên tập đạt promotion, nếu rỗng chọn D cao nhất trong tập eligible và
ghi NOT_PROMOTED/Original triển khai. Không làm tròn trước xét ngưỡng.
Selection mới cần schema/validator tương ứng, không ép ID mới vào selector
hoặc registry cũ; selection W7 không đổi nhãn theo run mới.

Kiểm phụ cố định: Q1–Q4 và H1/H2 theo cutoff, dựng tài khoản mỗi nhóm từ
vốn đầu; leave-one-symbol-out là mean ΔR trên ba mã còn lại, không chọn lại
ứng viên; prior-off xét từng nhánh, cả hai off khi so hai prior; ablation
trên G đầy đủ và T cả stats/examples ready của base tương ứng. Báo nhóm
rỗng với null, không đổi primary theo subgroup thắng.

Diagnostics train giữ 651 query/2021–2022 và bootstrap 2020 theo fold PIT,
không gọi LLM train. A/C2 dùng sự kiện y=1 khi LONG ròng>0 do hàm kinh tế
chung; so Brier và log loss (clip p vào [1e−6,1−1e−6] chỉ khi tính loss)
trên giao query có cả hai posterior hữu hạn, báo giao/missing từng mã/fold
và coverage raw/ready riêng. Không điền p=0,5 khi C rỗng. Loss tổng là mean
query trên giao, kèm từng fold/mã; không gọi đây là xác suất LLM hiệu chuẩn.
Đo mean lãi khi thắng/mean lỗ khi thua và support riêng bằng nhãn net LONG,
không trình chúng như mô hình expected return hoặc policy. B giữ xác suất
C2 nên không có gain calibration số học độc lập. Không sửa A/B theo loss
hoặc coverage sau chạy; kết quả bất lợi vẫn đưa vào báo cáo.

Ablation stats-only/examples-only/full dùng cùng base evidence và request
contract, khác nội dung hiển thị có version. Báo common support/readiness;
khác biệt ngoài tập cùng ready không được quy riêng cho stats hoặc examples.
Self-report prior-use chỉ là telemetry, không chứng minh nhân quả.

## Khóa xác nhận và điểm dừng

Một vòng cố định A/B; dừng khi hoàn tất đánh giá hai cấu hình hoặc hết W8, mốc nào
đến trước. Không ghép A+B, thêm cấu hình thay thế hoặc tối ưu theo return.
Nếu A/B bị chặn kỹ thuật trước API, ghi NOT_RUN/BLOCKED và lý do, không
đổi tham số để lấy cấu hình thắng; ma trận rút gọn phải khóa amendment trước
API, giữ đối chứng/ablation C2; với M ID thực tế xoay primary j mod M,
repeat (3j+r−1) mod (M+1), duplicate đặt cuối. Mẫu 12 point và ba lượt giữ nguyên.
Nếu không có ứng viên mới eligible, C2 chỉ được bàn giao sau tái kiểm
eligibility/binding phù hợp; không dùng dữ liệu thiếu để báo primary COMPLETE.
Không có ứng viên promotable thì Original triển khai. Lỗi integrity chưa sửa
chặn gate; không dùng mock thay hiệu quả thật. Sửa lỗi ảnh hưởng action sau
đã xem kết quả phải có revision riêng và ghi exploratory, không lấy lượt tốt nhất.

Ma trận W9 tối thiểu: Original, Bayesian v1, C2, ứng viên được chọn và
stats-only/examples-only tương ứng nếu đủ contract; gộp ID trùng trước chạy.
Nếu fallback C2 thì đặc tả ablation C2 riêng hoặc ghi không đủ khả năng
cô lập thành phần; không dùng ablation C3 để gọi là ablation C2.
Mọi nhánh cần schema/runner/verifier trước khóa; rút nhánh secondary chỉ
trước API và ghi lý do, không rút sau thấy return. Không mở sensitivity
K=5, risk overlay, model search hoặc replay LLM train trong lịch này.

Primary/secondary, CI và missing xử lý theo
[protocol thống kê W9 đã khóa](../week9/README.md#protocol-thống-kê-đã-khóa-tại-w7-14).
W8-07 hiện thực và kiểm công cụ bằng fixture, bind đặc tả/version/hash vào
manifest trước outcome; không chọn lại block/test vì CI hoặc p-value đẹp.

Giữ 64 điểm holdout 2024, 16/mã; tạo manifest/output mới bind selection,
protocol, code/schema/runtime/model/scaler/nguồn. Không đọc outcome để chọn
cấu hình. Bốn gate theo AGENTS.md, verifier và dry-run PASS mới bàn giao W9.
Giữ T+2.5, PIT, risk OFF, một upstream/point deep-copy, BRPP≤600 và prompt
<6.500 ký tự. Mọi API qua retry/pacer/checkpoint; người dùng tự chạy.

**Gate W8:** 8/8 DONE, selection và manifest kiểm được. Không đồng nghĩa
Bayesian ICL đã thắng; hiệu quả xác nhận còn chờ W9. README này giữ checklist
và kết quả gọn; artifact runtime có revision, không tạo receipt trùng lặp.
