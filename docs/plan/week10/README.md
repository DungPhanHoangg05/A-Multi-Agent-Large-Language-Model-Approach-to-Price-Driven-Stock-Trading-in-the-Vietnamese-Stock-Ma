# Tuần 10 — Xây dựng phiên bản Bayesian In-Context Learning hợp nhất

**Trạng thái: 5/10 task DONE, cập nhật 24/10/2026; đã audit nguồn, khóa protocol, memory/index, backbone và context/renderer U-BICL v1.**
Giá thực thi 2025 đã PASS; pooling λ=8 khóa offline và bốn gate hồi quy PASS.
Context/renderer đã khóa và bốn gate U10-05 PASS; runtime U-BICL còn TODO,
xác nhận chưa có release và vẫn cần các gate U10/U11.
[Kế hoạch tổng](../plan.md) · [W9 đã xác nhận](../week9/README.md) · [W11](../week11/README.md) · [W12](../week12/README.md)

## Mục tiêu và điểm xuất phát

Xây dựng **Unified Bayesian In-Context Learning (U-BICL)**: một phương pháp
hợp nhất lấy A_tp_pool làm nền, sử dụng có chọn lọc retrieval, posterior,
bất định và demonstrations để cải thiện Decision LLM. Đây là ứng viên mới,
chưa triển khai/chưa được xác nhận, không mặc định là phiên bản mạnh nhất.
Không thay LLM bằng policy số rồi gọi phần thắng đó là đóng góp ICL.

A ở W9 có D=+2,025325 đpt so Original, CI95% [0,135027; 4,211864], tăng ở
3/4 mã, mean ΔMDD=−1,725582 đpt. Bốn secondary chưa xác nhận ưu thế; 2/39
cặp prior-off khác action dù request giống. Các kết quả này được giữ nguyên.
Phiên bản kết hợp phải chứng minh lợi ích tăng thêm trên cùng nguồn/protocol,
không cộng các gain từ những lượt chạy khác nhau để ước tính gain hợp nhất.

Theo yêu cầu thay thế ngày 24/10/2026, mã/tài liệu và task của revision đã
kết thúc trước đây được rút khỏi cây phát triển hiện hành. Việc lập lại plan
không làm 2023/2024 thành dữ liệu chưa xem, không làm các thử nghiệm trước
đó chưa từng xảy ra. Lịch sử Git ở mốc 4d34bc4 lưu provenance khi cần giải
trình nghiên cứu; không viết lại lịch sử hoặc sửa bằng chứng W9.

## Kết hợp gì và vì sao

| Thành phần | Nguồn ý tưởng | Vai trò trong U-BICL | Mức bằng chứng / điều kiện nhận |
| --- | --- | --- | --- |
| Prior theo Trend/Pattern | A_tp_pool | Backbone xác suất lịch sử có điều kiện | A có primary holdout dương; không chứng minh riêng từng chi tiết A |
| Similarity giá, recency, diversity | C1/C2 | Lấy ví dụ tương đồng, tránh trùng thời gian | Có triển khai kiểm PIT; vẫn cần ablation kinh tế của hệ thống hợp nhất |
| Gate tách stats/examples | C2 | Giữ block có evidence, không ép hai block cùng tồn tại | Coverage/trace kiểm được; không hạ ngưỡng vì return |
| Prefix rõ đơn vị và bất định | B_semantic | Giảm mơ hồ về LONG/CASH, lịch sử và dự báo | Chỉ là giả thuyết; B không có bằng chứng thắng ổn định |
| Đối chiếu prior với tín hiệu hiện tại | C3 | Yêu cầu viện dẫn evidence ID hợp lệ và giải thích mâu thuẫn | Trace là telemetry, không chứng minh LLM làm Bayes nội tại |
| Memory PIT và shared-off | Bài học vận hành các vòng trước | Tăng độ mới nguồn, loại biến thiên giả ở nhánh không có prior | Lợi ích kỹ thuật; không gán cho cải thiện kinh tế |
| Context nhiều task có support | Hướng multi-task ICL | Tóm tắt nhóm lịch sử và cặp x→y đại diện | Phải có nhiều quan sát mỗi task; không ép nhóm hiếm hoặc giả coverage |

Không nhập mọi cơ chế mặc định. Mỗi thành phần đi qua gate offline; chốt
một cấu hình U-BICL trước development LLM. Không ensemble/vote nhiều Decision,
không quét prompt/model/K để lấy return đẹp. Bayesian v1/C0/B/C3 vẫn là
nguồn tham khảo lịch sử, không nhân bản tất cả vào ma trận mới.

## 1. Hợp đồng học thuật và kiến trúc

Theo [paper gốc](https://proceedings.mlr.press/v306/zhu26aj.html), mô hình
được huấn luyện trên prior/target tasks. Ở đây LLM hosted không được huấn
luyện lại theo paper: đóng góp là **Bayesian evidence-conditioned ICL cho
giao dịch**, với posterior số học, task context và thí nghiệm loại thành
phần. Không tuyên bố tái tạo đầy đủ amortized hierarchical Bayes.

Luồng: nguồn giá/tin PIT → upstream một lần → memory đã kiểm → posterior
và task retrieval → context ngắn → Decision LLM → engine T+2.5 hiện hữu.
Ba lớp phải tách: ước lượng xác suất bằng code; học từ demonstrations trong
context; quyết định kinh tế của LLM. Mọi lớp có version/provenance riêng.

## 2. Memory theo thời gian, không sinh thêm lịch sử bằng Decision

- Giữ bank gốc 852 record nguyên byte. Adapter mới nhập tối đa 124 upstream
  đã có của 60 điểm 2023 và 64 điểm 2024 từ nguồn W8/W9, không phụ thuộc
  output revision đã rút và không gọi thêm LLM để dựng bank.
- Chỉ đọc upstream thật, không dùng action/justification/confidence Decision
  làm feature. Kiểm model/schema/signal semantics; record không tương thích
  bị loại rõ reason, không suy đoán hoặc tự đổi nhãn để đủ mẫu.
- Nhãn LONG ròng lấy từ compute_round_trip_net_return với giá thô đã kiểm;
  dedup theo episode/source identity, không chọn record vì có lãi. Bank/index
  mới namespace riêng, scaler fit train-only; không ghi đè bank/model W9.
- Query 2023 chỉ thấy cycle exit<query; không thấy 2024 dù cùng nằm trong
  file. Xác nhận 2025 dùng snapshot tối đa 2024-12-31, không append outcome
  2025 giữa run. Chặn query tự truy xuất chính nó và future append leakage.
- Giữ max age 730 ngày, half-life 365 và các filter hiện hữu làm mặc định.
  Bank chỉ tới 2022 không đủ ví dụ cho 2025; audit độ mới trước khóa, không
  tăng tuổi tùy tiện để qua coverage. Metadata thiếu không được coi là zero.
- Mọi đối chứng A/U/Numeric dùng cùng source snapshot khi so trong run mới.
  A đối chứng là phương pháp A trên nguồn chung, không phải W9 bất biến.

## 3. Bayesian backbone và gate nhận pooling

Mặc định dùng thống kê A: C cùng mã/regime và Trend/Pattern; B là phần còn
lại cùng mã/regime, C∩B rỗng. Với y=1[r_net>0], mB=(sB+1)/(nB+2):

```text
theta | D ~ Beta(sC + 4*mB, nC-sC + 4*(1-mB))
```

Bayes tạo xác suất lịch sử và CrI95%, không là confidence LLM. nC=0 trả
missing conditional evidence, không biến prior mean thành dự báo đã quan sát.
Posterior tính trên toàn population hợp lệ, không chỉ ba ví dụ top retrieval.

Chỉ một biến thể pooling được xét **offline**, không một candidate LLM mới:
B1 cùng regime ngoài C, B2 khác regime cùng mã, ba nhóm rời nhau. m2=(s2+1)/
(n2+2), m1=(s1+λ*m2)/(n1+λ), posterior Beta(sC+λ*m1,nC−sC+λ*(1−m1)).
λ∈{2,4,8}; chọn trên train walk-forward bằng log loss, Brier tie-break,
rồi λ nhỏ hơn. Không đưa record C lại vào prior; không pool chéo mã.

Nhận pooling khi trên giao raw posterior ngoài thời gian: cả mean log loss
và Brier không xấu hơn A, ít nhất một metric tốt hơn; không mã nào có Brier
tăng >0,01; ready coverage không giảm. Rule khóa trước diagnostics; nếu
trượt thì dùng A, không tiếp tục thêm λ. Đánh giá/fit theo fold PIT, purge
cycle vượt biên; nói rõ đây là chọn hyperparameter trên train, không là test.
CrI plug-in không tích phân toàn bộ bất định hyperprior/phụ thuộc cycle.

Gate stats của backbone A giữ population≥20, nC≥5, width≤0,75. Nếu pooling
được nhận, gate thay population bằng nB1+nB2≥20, vẫn nC≥5/width≤0,75;
version và rule khóa trước LLM. Báo n mỗi tầng, prior weight, tuổi, số cụm
thời gian; không gọi raw n là effective sample size. Thiếu stats không xóa
examples đã đủ điều kiện và ngược lại.

## 4. Context có nhiệm vụ, không ép sáu ví dụ vào mẫu thưa

Một task = (mã, regime, block 90 phiên VNINDEX không chồng lấp), neo từ
lịch train đã bind. Task có ít nhất hai cycle đã đóng; trong phần chọn
đại diện loại overlap entry–exit. Khác với block ngắn, block 90 phiên nhằm
tăng support; đây là giả thuyết mới, không được gọi là đã chứng minh tốt hơn.
Các record nhóm đều cùng cutoff; centroid/feature không dùng outcome.

Giữ ranking similarity tín hiệu/giá, min_similarity=0,625, tuổi≤730,
đa dạng khoảng cách ≥5 phiên. Xếp nhóm bằng similarity đại diện tốt nhất,
sau đó tuổi đại diện rồi task ID; chọn tối đa ba nhóm, mỗi nhóm một cycle
đại diện x→y và summary s/n của toàn nhóm PIT. Không xếp nhóm bằng s/n hoặc
return, không ép cân bằng thắng/thua. Task summary không cộng thêm counts
vào posterior vì đó là trình bày lại evidence, không mẫu độc lập mới.

Context typed rõ task ID, n, s/n, x(T/P)→net return% đại diện. Full group
membership ở sidecar; không gọi một exemplar đơn lẻ là nhiều quan sát.
K_tasks tối đa 3, exemplar tối đa 3, budget như cũ. Không có nhóm đủ support
thì chuyển sang top≤3 cycle theo selector A với context_mode=episode_fallback,
ghi rõ không phải multi-task. Không có ví dụ hợp lệ thì examples off.
Không chọn mode theo outcome hay action, chỉ metadata/support PIT.

Gate mô tả multi-task: ≥12/60 development có ≥2 task visible, ≥2/mã. Nếu
không đạt, vẫn đo U-BICL với fallback nhưng không claim multi-task đã được
kiểm đủ support; không sửa block theo return để qua gate. Báo cả coverage
task/episode_fallback/off; estimand kinh tế bao gồm chính sách fallback này.

## 5. Prefix và Decision có căn cứ

Một template duy nhất: regime/query horizon → posterior/support/CrI →
task hoặc episode x→y → nhắc bất định/SHORT=CASH. BRPP≤600, toàn prompt
<6.500 ký tự; giữ _distill_report/_cap_report. Không giấu provenance bằng
thay ID thiếu định nghĩa; ID ngắn trong prompt phải ánh xạ duy nhất sidecar.

Decision phải xem prior như bằng chứng tham khảo, đối chiếu với tín hiệu
hiện tại, nêu căn cứ nếu chọn LONG khi prior thấp hoặc CASH khi prior cao.
Không ép đồng ý prior; không cộng/trừ tay posterior theo sentiment/LLM.
Vẫn schema legacy; dùng evidence_for/evidence_against/justification hiện có,
không thêm self-reported probability hoặc field bắt buộc làm lệch đối chứng.
Các nhánh LLM dùng cùng instruction chung và schema; khác đúng block context.
Trace ID chỉ là telemetry, không dùng để promote.

Test biên đủ ba nhóm và CrI/đơn vị/legend; không cắt nhãn hoặc tăng budget
để chạy. Kiểm horizon rõ Open(t+1)→Close(t+3) theo ngày phiên; prompt/báo cáo
không được dùng T→T+2 mơ hồ về cutoff. Nếu cần sửa instruction chung phải
version cho mọi nhánh mới, không sửa artifact/contract W9.

## 6. Shared-off, retry và ổn định

Original chạy trước mỗi point/repeat, lưu durable. Nhánh prior-off chỉ reuse
khi toàn canonical body/model/options/schema khớp; source reference/deep-copy
đúng point/repeat, decision_origin=shared_original. Không gọi lại, không tạo
HTTP giả. Alias stats-only chỉ khi request/evidence identity đúng và có
whitelist protocol. Full không alias vì tình cờ có cùng action.

Duplicate Original độc lập chỉ chẩn đoán noise; không vote/lấy lượt đẹp nhất.
Một upstream/point deep-copy cho mọi nhánh, repeats không chạy lại vision.
Giữ _invoke_with_retry, backoff, ledger, checkpoint/unknown recovery hiện hữu.
Không xóa usage cũ khỏi ledger dùng chung khi rút revision; key không vào log.
Reuse đảm bảo prior-off cùng action bằng thiết kế, không chứng minh provider
deterministic. Thiếu/error execution không được chuyển thành CASH.

## 7. Phạm vi mô hình và dữ liệu

Giữ model/provider/options hiện hữu sau preflight; không quét model, fine-tune,
soft regime, cross-symbol hay risk overlay trong vòng này. Numeric_only là
đối chứng posterior mean>0,5 khi stats ready, thiếu evidence thì CASH theo
policy đã khóa; không phải Bayes-optimal utility và không là candidate ICL.
Mean lãi/lỗ lịch sử chỉ diagnostics; chưa có payoff model calibrated thì
không gọi là expected return query hoặc trừ phí lần hai.

2020–2022 train/fold; 2023 development đã xem; 2024 W9 là xác nhận bản cũ
và nguồn lịch sử được khai báo cho revision mới. Không dùng 2024 tune prompt/
λ hoặc chứng minh revision mới. 2025 là tập xác nhận dự kiến: kiểm lại giá
thô/quyền/coverage và exposure từ lịch sử Git/nguồn W9, không tự coi việc
xóa output là xóa exposure. Khai báo trước về 2025 là thông tin lịch sử,
phải đối chiếu có sử dụng thêm kể từ đó; không yêu cầu xác nhận lại vô cớ.
Không chứng minh được independence thì chỉ exploratory/forward sau lock.

## Checklist W10

| Task | Công việc / đầu ra | Phụ thuộc | Gate hoàn thành | Trạng thái |
| --- | --- | --- | --- | --- |
| U10-01 | Audit source/exposure, benchmark A, footprint và compatibility | W9 | Nguồn W9 nguyên; 2025 PASS hoặc reason; chưa đọc payoff mới | [x] DONE — nguồn/124 upstream PASS; đã bổ sung giá 2025 PASS trong namespace riêng |
| U10-02 | Khóa protocol U-BICL, ma trận/claim/limits và fixture | 01 | Một candidate, không quét prompt; công thức/task/mode rõ | [x] DONE — protocol v1, sáu nhánh/một candidate và 88 ca fixture đã kiểm |
| U10-03 | Memory/index revision từ upstream đã có | 02 | PIT/dedup/label/model/scaler/age; không Decision feature | [x] DONE — 976 record; scaler train-only, CLI nguồn thật và bốn gate PASS |
| U10-04 | Backbone A, thử pooling offline và khóa choice | 03 | Oracle/fold/loss/coverage; rule PASS thì nhận, không thì A | [x] DONE — λ=8 PASS/LOCKED trên train; oracle/CLI và bốn gate PASS |
| U10-05 | Task context/fallback/ranking và prompt | 03–04 | Label-blind, task support, budget 600/6500; thiếu đúng reason | [x] DONE — 34/60 có ≥2 task; BRPP tối đa 406/600; nguồn/oracle/CLI và bốn gate PASS |
| U10-06 | Shared-off, instructions chung và journal/retry | 02 | Body/source/repeat binding; prior-off reuse; no hidden policy | [ ] TODO |
| U10-07 | CLI producer/loader/verifier/report | 05–06 | Request/output schema riêng, legacy không đổi, JSON native | [ ] TODO |
| U10-08 | Diagnostics, fixture failure/resume/leakage và bốn gate | 07 | Compileall/unit/E2E/leakage PASS đúng source/runtime | [ ] TODO |
| U10-09 | Dry-run 60 điểm, coverage/MDE và plan repeat | 08 | Lock source/schedule/model; không điều chỉnh theo outcome | [ ] TODO |
| U10-10 | Handoff vận hành và bản thảo phương pháp | 09 | CLI thật run/resume/verify; W11 chỉ chạy đúng release | [ ] TODO |

Đã có core/unified_bayes_memory.py, unified_bayes_statistics.py,
unified_bayes_diagnostics.py, unified_bayes_context.py và unified_bayes_prompt.py.
Các module tiếp theo dự kiến: unified_bayes_runtime.py, unified_bayes_reports.py;
scripts/run_unified_bayes.py; schema/fixtures cần thiết dưới W10.
Runtime và CLI chạy U-BICL chưa tồn tại. Tái dùng engine, HMM, feature, retry/pacer/ledger đã
kiểm; không sửa hash cũ để cho verifier legacy nhận code khác.

Tests phải phủ partition/oracle/n=0/future append/query self-match, độ tương
thích nguồn/JSON, label-shuffle invariant ranking, task fallback/budget,
shared-off/duplicate/resume/unknown, metric engine. P0/liên module chạy đủ
bốn gate, không chỉ test renderer. Không tạo unit test chỉ để xác nhận chuỗi
Markdown. API chỉ do người dùng chạy sau bàn giao CLI đã kiểm.

## Điểm dừng và tính khả thi

Một cấu hình hợp nhất, một vòng development; nếu pooling trượt dùng A,
task thưa dùng episode fallback theo rule đã khóa. Hết W10 không đạt gate
kỹ thuật thì không chạy API hoặc gọi mock là hiệu quả. Không nối thêm tuần
để thử vô hạn; W12 vẫn nộp luận văn với kết quả đã có và giới hạn trung thực.
Tổng hợp các thành phần có thể tạo tương tác bất lợi; cần W11 chứng minh,
không suy hiệu quả từ tên phiên bản hoặc tổng gain các bảng lịch sử.

## U10-01 — Kiểm toán nguồn, exposure và compatibility, 24/10/2026

**DONE — hoàn tất audit offline trên mốc `ff7d14f`.** W9 và nguồn upstream
đủ điều kiện làm đầu vào cho bước khóa protocol; chưa xây memory/index hoặc
chạy U-BICL. Gate xác nhận 2025 **BLOCKED**, reason
`MISSING_VERIFIED_2025_EXECUTION_SOURCE`; đây là lý do được phép tại gate
U10-01, không chặn thiết kế offline U10-02. Không tính payoff mới, đọc
action/return 2025, tải nguồn mới hoặc gọi API trong task này.

### Nguồn W9 và benchmark A

Đọc lại đủ **4.432 entry** của archive W9, kiểm tên duy nhất/CRC và SHA-256
archive. **4.431 file local khớp byte**; ngoại lệ duy nhất là ledger dùng
chung đã được nối bởi revision trước. So trực tiếp với bản trong archive:
3.036 HTTP record, 2.827 invocation và 29 recovery event của W9 đều giữ
nguyên; hiện tương ứng 3.562/3.339/38. Không reset ledger hoặc loại usage
của revision đã rút. Các metadata khóa OS không thuộc archive khoa học.

| Nguồn đã đối chiếu | SHA-256 byte |
| --- | --- |
| [Archive W9](../../../outputs/bayesian_benchmark/improvement_v1/holdout/frozen_results_v1.zip), 64.258.053 byte | `1db2024a3a338cadcf72692287471f8a14feba49ce8a1b1a488b951896cfec70` |
| [Report W9](../../../outputs/bayesian_benchmark/improvement_v1/holdout/run/report.json) | `0a926be1e6da2803d56dd7a572a4d3eae7b8863cc3fcd02eea111df35cd7c23f` |
| [Bootstrap W9](../../../outputs/bayesian_benchmark/improvement_v1/holdout/run/bootstrap.json) | `78ae445037f68fa0f8cca4638dc7bc3e7c24efb2854539e078478e46db919e57` |
| [Bank gốc, 852 record](../../../data_manager/regime_memory_store.json) | `09b48c6192a092b562173e8b3b7eceb44025c6e02454093e34214a730a460949` |
| [HMM đóng băng](../../../data_manager/regime_model.json) | `58a8bccb11466177114017aeb648d934106629c1598ac96bd0bde9e5d5263ebd` |
| [Index giá legacy](../../../outputs/bayesian_benchmark/price_features/candidate_index_v1.json) | `4f9242edcca9627437a6e37c81931d45621d48006ebd3f87a8d35952c20fb785` |
| [Ledger hiện tại](../../../outputs/oos_pilot/api_usage.json), khác snapshot W9 do append | `bfab9b5cf3dfbdacedb2aaf76879b1361ecf8e373d98991f18aa2761ed213348` |

Kiểm **69 dependency development/74 dependency holdout** theo hash LF của
plan và Python **3.13.5 cùng 22 package** khớp runtime đã khóa. Benchmark A
được đối chiếu với report/bootstrap/publication đã lưu, không chạy lại LLM
hoặc dùng W9 chọn thêm phương pháp:

| Chỉ tiêu A_tp_pool trên W9 | Kết quả giữ nguyên |
| --- | --- |
| Common support / nhánh / Decision | 64 điểm, 16/mã; sáu nhánh, 384 Decision |
| D A−Original / CI95% L=4 | +2,025325 đpt / [0,135027; 4,211864] |
| ΔR từng mã FPT/MWG/VCB/VNM | +3,188995 / +1,735789 / +3,285796 / −0,109279 đpt |
| Mean/max ΔMDD | −1,725582 / +0,109279 đpt |
| Stats / examples / cả hai / prior visible | 22 / 13 / 10 / 25 trên 64 điểm |
| Prior-off / action khác dù canonical request giống | 39 / 2 |
| Bốn secondary L=4, CI98,75% | Đều INCONCLUSIVE |

Đây là kết quả có điều kiện trên cohort/Decision đã lưu; không chứng minh
riêng pooling, demonstrations hoặc Bayes nội tại. BEAR=0, tin reliable=0/64
và trace legacy N/A tiếp tục được giữ tại [giới hạn W9](../week9/README.md#w9-05--bảng-hình-và-phân-tích-giới-hạn-21102026).
A_reference của run mới phải dùng cùng nguồn/instructions/shared-off với U;
không so U trên memory mới với W9 rồi quy chênh lệch cho phương pháp.

### Compatibility của upstream và các chỗ phải thích ứng

Chỉ nạp `improvement_v1/{development,holdout}/plan.json`, `run/cohort.json`,
`run/points/` và `run/responses/` đã khớp byte archive W9. Hai cohort cùng
signal config/options và `execution_mode=research`. Dùng `shared_point`
với `verify_only=True`, `restore_full_bundle`, `verify_source` và transform
feature của index hiện hữu; không nạp Decision làm feature hoặc sinh nhãn.
Schema point/journal lần lượt `improvement_shared_point_v1` và
`agent_stage_journal_v1`; kiểm run signature, source proof, shared/journal
hash, output durable và bốn stage complete đúng một attempt khoa học/stage.

| Nguồn | FPT | MWG | VCB | VNM | Tương thích / loại |
| --- | ---: | ---: | ---: | ---: | --- |
| Development 2023 | 12 | 16 | 16 | 16 | 60 / 0 |
| Holdout W9 2024 | 16 | 16 | 16 | 16 | 64 / 0 |

**124/124 PASS**, không trùng `(symbol, as_of_date)` với nhau hoặc bank gốc;
496 stage complete. Tín hiệu T/P/Indicator/Alpha/Sentiment được parser
hiện hữu tái dựng từ năm report, năm Alpha factor và tin PIT, khớp bundle;
không đoán từ action/justification/confidence. Regime có 61 CONSOLIDATION,
31 BULL, 32 CHOPPY, không BEAR. Cutoff từ 06/01/2023, cutoff mới nhất
26/12/2024 ở cả bốn mã; mọi cycle đóng chậm nhất 31/12/2024. **976 chỉ là
trần 852+124 khả thi**, chưa là bank đã phát hành hoặc coverage U-BICL.

Model provenance của bank và hai nguồn khớp: text `openai/gpt-oss-20b`,
temperature=0/max_tokens=2048, effort=low; vision `qwen/qwen3.8-27b`,
temperature=0/max_tokens=1024, effort=none; reasoning_format=hidden cả hai.
Window=45, daily, tiếng Việt, `zscore_tanh`, alpha_weights=null. Đây là
identity nguồn, chưa chứng nhận model/provider còn gọi được; preflight thật
vẫn thuộc bàn giao vận hành sau này.

- Backbone tham chiếu ở `core/improvement_prior.py`: C khớp T/P, B=P∖C,
  mB=(sB+1)/(nB+2), strength=4; nC=0 giữ thiếu conditional evidence.
  Stats lấy toàn population PIT, không lấy counts từ top ba ví dụ.
- Selector hiện hữu giữ tuổi theo **as_of_date**, max=730 ngày, half-life=365,
  min_similarity=0,625, gap≥5 phiên; stats/examples gate tách block. Bank gốc
  có cutoff cuối 27/12/2022: ví dụ mới nhất đã **737 ngày** ở 02/01/2025,
  nên mọi ví dụ gốc trượt tuổi trong 2025; không suy stats cũng bị age-filter.
- `build_price_feature_index` legacy chỉ nhận exit≤30/12/2022;
  `PriceFeatureIndex.scaler` chỉ có fold train_2021/train_2022/oos_2023_2024.
  U10-03 cần namespace/version index riêng để nhập 2023/2024 và dùng scaler
  train-only cho 2025; không sửa index/fold/hash W9 để lách hợp đồng cũ.
- Chưa kiểm support block 90 phiên, task coverage, pooling gate, budget biên
  hoặc shared-off U. Các phần đó thuộc U10-02–08; audit compatible không thay
  producer/verifier/PIT/dedup/nhãn qua engine và test future-append của U10-03.

### Exposure và điều kiện năm 2025

Khai báo lịch sử tại `4d34bc4:docs/plan/week10/exposure_inventory_v2.json`
ghi: **“Xác nhận kết quả 2025 chưa được dùng để lựa chọn hoặc điều chỉnh
phương pháp.”** Basis `PARTICIPANT_DECLARATION_AND_LOCAL_INVENTORY`,
`unseen_outcomes_proven=false`, `confirmation_allowed=false`. Lịch sử
`docs/plan/week11/README.md` cùng mốc ghi revision đã STOP trước manifest/
release/xác nhận 2025. Hai commit sau mốc đó chỉ rút revision/lập kế hoạch
mới; không xem việc rút output là xóa exposure hoặc yêu cầu khai báo lại.

Inventory mới rà **6.074 JSON** toàn workspace, gồm **6.028 JSON dưới
outputs ignored**, không lỗi parse; trích ngày cấu trúc/query/window và
danh sách lịch, không phân tích action/payoff. Không thấy query/cutoff 2025.
Kiểm thêm tám CSV outputs và ngày `record.csv` (45 nến 30/07–05/10/2026);
CSV summary không có ngày không được coi là bằng chứng chưa xem. Các dấu
2025 quan sát được là phạm vi archive, ngày tin/quyền và entry/exit giáp năm
của cutoff 2024 bị loại, không phải run xác nhận. UUID chứa `2025` không là
ngày. Không kiểm toán được mọi hoạt động ngoài workspace, ảnh/UI hoặc archive
ngoài W9; không có report không chứng minh chưa từng xem payoff.

**Exposure: kế thừa PASS trong phạm vi khai báo lịch sử + inventory local,
không phát hiện sử dụng mới trái khai báo; không chứng nhận độc lập tuyệt
đối. Giá/lịch đủ điều kiện xác nhận: BLOCKED tại nguồn hiện tại.**

| Nguồn giá hiện có | Phạm vi và kết luận |
| --- | --- |
| `data/historical/manifest.json`, hash `0c336ee95af3a016b608742f4355f05a4b99d3825bd2f557327d5df02c67719c` | Archive 2018–2025; giá điều chỉnh, không thay giá thực thi thô |
| `data/execution_prices/manifest.json`, hash `e254273e7fb842cdf9fa60007ea7dcc5994ac7190975a5cf940e57852e52f09c` | Giá thô đã kiểm chỉ đến 31/12/2022 |
| `data/execution_prices_oos/manifest.json`, hash `bb70790062210ad983e5250dae650a3d355cad4d4ba57807411208a5ac9c00f4` | Giá thô đã kiểm chỉ đến 31/12/2024; events đã có quyền 2025 |
| Snapshot giá 2025 của revision đã rút | Namespace cũ không còn trên đĩa lúc audit; không có source raw/evidence/manifest 2025 để tái kiểm, không dùng kết quả PASS cũ thay nguồn thật |

Chỉ đọc `Datetime` của năm CSV archive: lịch cùng **249 phiên**, 02/01–
31/12/2025, tăng dần/không trùng. Step3 neo 02/01 có 83 cutoff/mã; trần
cycle đóng trong quý là Q1/Q2/Q3/Q4=19/19/20/21, tổng **79/mã trước kiểm
giá/quyền**. Events OOS có bốn ngày quyền FPT và hai ngày/mã còn lại trong
2025, nhưng thiếu giá/Reference/volume 2025 để kiểm eligibility đầy đủ.
**Chưa tái lập pool hợp lệ hoặc chọn/khóa 128 điểm**; không dùng các pool/
ngày đã sinh bởi revision rút. Trước release U11 phải có snapshot giá thô/
evidence/quyền/prefix/checksum đạt gate, rebuild lịch theo rule đã đăng ký
và rà exposure phát sinh. Thiếu nguồn/independence thì chỉ exploratory hoặc
forward sau lock theo kế hoạch; không dùng OHLC điều chỉnh tính nhãn.

### Footprint, ranh giới và kiểm tra hoàn thành

Bank/HMM/index gốc lần lượt **472.955 / 5.478 / 686.295 byte**; ledger hiện
**11.918.358 byte**. Chỉ kiểm kích thước/hash, không sao chép hoặc sửa nguồn.

| Nhánh lưu trữ dưới `improvement_v1/` | Số file | Byte |
| --- | ---: | ---: |
| development | 1.565 | 101.800.347 |
| holdout, gồm archive W9 | 1.032 | 117.311.054 |
| repeats | 868 | 53.155.050 |
| train | 2 | 2.243.427 |
| Tổng, loại chín file metadata khóa OS | 3.467 | 274.509.878 |

Namespace `bic_icl_v2` không còn tại thời điểm U10-01; đoạn bàn giao dọn
revision bên dưới mô tả thời điểm trước đó, không phải inventory hiện tại.
Không tạo lại output, memory/index hoặc execution plan đã rút. Protocol U10-02
sẽ khóa namespace/version mới; không ghi vào `improvement_v1` hoặc đổi hash cũ.

Phạm vi thay đổi chỉ README tuần và kế hoạch tổng; không thêm receipt task,
schema, code, test, runtime hoặc đầu vào. Theo **AGENTS.md 1.2 không chạy lại
compileall/unit/E2E/leakage suite**; gate sau dọn revision ghi bên dưới là
bằng chứng cũ, không phải gate mới của U-BICL. Lượt mới chạy
`py -3.13 -X utf8 scripts/verify_improvement_holdout.py --verify-report`
**exit 0**: tái dựng toàn report/384 Decision từ nguồn/checkpoint/HTTP audit
và engine cũ, consumer/receipt/binding khớp; transport chặn mạng. Bootstrap/
publication đối chiếu byte archive và số liệu đã lưu, không chạy lại producer.
**4.366 file** trong phạm vi bảo vệ giữ nguyên byte, không mất file; bốn file
owner/recovery của hai khóa OS được verifier cập nhật đúng vòng đời, owner
đã released. Ledger, report/bootstrap/archive, nguồn/code/schema/runtime
nguyên byte trong task. QA hash/archive/runtime/số liệu/liên kết/diff PASS.
**U10 đạt 1/10; tiếp theo U10-02**, chưa mở xác nhận hoặc cấp quyền gọi API.

## U10-02 — Khóa protocol và fixture, 24/10/2026

**DONE — khóa `unified_bic_protocol_v1`**, namespace `unified_bic_v1`, từ
nguồn/audit tại `0abd1ac`. [Phương pháp độc lập](unified_bic_method_v1.md),
[đặc tả máy đọc](unified_bic_protocol_v1.json) và
[fixture tổng hợp](fixtures/unified_bic_contract_v1.json) là hợp đồng cho
U10-03–09; chưa là mã chạy, execution plan hoặc release API.

Khóa sáu nhánh Original/A_reference/U_full/U_stats/U_examples/Numeric_only,
chỉ U_full được nominate. Một vòng development/một renderer family, không
quét prompt/model/K. A_reference giữ thuật toán/evidence/prefix A trên cùng
nguồn; ba projection U dùng cùng base evidence, Numeric dùng đúng posterior
U và ready gate. Chỉ khác block visibility, giữ common instruction/schema
cho mọi nhánh LLM; không quy toàn contrast U−A cho riêng pooling hoặc prompt.

Đã làm rõ C/B1/B2 rời nhau, công thức A/pooling, nC=0, gate nhận λ trên raw
posterior train và fallback A khi trượt; không thử λ đứng sau để cứu gate.
Hai fold có **647 query score (325/322)** sau purge bốn cycle cutoff
31/12/2021 đóng 06/01/2022; giữ diagnostics 651 query legacy nguyên trạng.
Chưa tính loss diagnostics hoặc chọn λ trong task này.

Task neo lịch VNINDEX 02/01/2018, block90 không chồng lấp, support≥2 từ full
membership PIT/tuổi hợp lệ; representative theo similarity sau recency,
gap≥5 phiên và không overlap, tối đa ba nhóm/ba exemplar. Membership/summary
không thay vì ranking; label-shuffle không đổi selector. Mode task có thể
chỉ một nhóm; thiếu nhóm dùng episode_fallback, thiếu ví dụ thì off, stats
độc lập. Không cộng counts summary vào posterior hoặc gọi một exemplar là
nhiều quan sát độc lập. Khóa claim gate ≥12/60 điểm có ≥2 task, ≥2/mã.

Chọn cache W8/W9 đã kiểm cho development, một upstream/point và deep-copy;
Original đầu, repeat/readiness/order và shared-off cùng point/repeat/body/
model/options/schema rõ. Whitelist alias stats-only rỗng; duplicate độc lập,
không vote. Khóa nomination/primary/family secondary/seed/MDD guard/limits;
2025 vẫn BLOCKED thiếu nguồn giá thô, không có ngày chọn hoặc release mới.
Backbone choice, wording renderer/common instruction và source/request lock
cụ thể lần lượt thuộc U10-04, U10-05/06 và U10-09 trước LLM.

| Artifact khóa | SHA-256 |
| --- | --- |
| `unified_bic_protocol_v1.json`, canonical JSON | `c392c92cd6b1b6c49672adeb4ada5cf47b902e3cb4c2bef41aca5cb5857abfda` |
| `fixtures/unified_bic_contract_v1.json`, canonical JSON | `f4a0a49d3be7af76c8acfcf7dbeed8ed47b112c7781d7317c91ba0ea11ee1e30` |
| `unified_bic_method_v1.md`, UTF-8/LF | `021d45333d7e5d7647c51014640aae90da7b9f1210568e5c27b9af78815d0632` |

Canonical JSON dùng `core.prior_backtest.canonical_hash`: sort_keys=True,
ensure_ascii=False, separators=(',', ':'), allow_nan=False; không băm byte
indent/newline. Fixture bind đúng digest protocol; source anchor dùng byte
SHA-256 của 12 nguồn có sẵn. Metadata/hash không tự cấp release hoặc cho
consumer legacy nhận schema mới.

**QA mới: 88 ca oracle tổng hợp PASS**, đối chiếu Beta bằng Decimal/CDF,
nhãn kinh tế bằng engine hiện hữu, partition/gate/tie-break, task support/
diversity/label-shuffle/fallback, visibility/Numeric, budget biên, shared-off,
order/repeat, nomination/CI và bootstrap indices bằng vòng lặp độc lập.
Hai fold/lịch 60 điểm/12 source anchor và binding protocol-fixture khớp;
không dùng payoff 2025, outcome development mới hoặc gọi API. Fixture là
expected contract cho code/test sau này, không chứng minh implementation U
hoặc provider đã PASS. Thiếu các test production/PIT/resume và bốn gate
U10-08 thì chưa mở development API.

Phạm vi là tài liệu phương pháp và JSON đặc tả/fixture chưa có consumer
runtime; không đổi code/test/config/schema đang chạy hoặc input legacy.
Theo AGENTS.md 1.2 không chạy compileall/unit/E2E/leakage suite; chỉ kiểm
oracle/JSON/hash/số liệu/liên kết/diff và bảo toàn nguồn. Không tạo receipt
task riêng hoặc ghi gate cũ thành gate U mới. QA chín liên kết/anchor, ba
digest và staged diff PASS; **4.374 file** code/nguồn/evidence cũ nguyên byte,
gồm ledger, archive W9 và root README; không thay metadata khóa OS.
**U10 đạt 2/10**, tiếp theo
**U10-03** triển khai memory/index đúng protocol đã khóa.

## Bổ sung nguồn giá 2025, 24/10/2026

**Gate giá 2025 PASS — đã xử lý `MISSING_VERIFIED_2025_EXECUTION_SOURCE`.**
Tự thu thập từ cùng VCI bằng headers vnstock 4.0.9, không cần người dùng
cung cấp file, API key hoặc khai báo exposure lại. Chỉ kiểm dữ liệu/quyền/
lịch; không gọi LLM, tính nhãn/return 2025 hoặc chọn ngày theo outcome.
U10 vẫn **2/10 DONE**; bổ sung này chưa thực hiện memory/index U10-03.

[`prepare_unified_execution_prices.py`](../../../scripts/prepare_unified_execution_prices.py)
là công cụ input độc lập. Giữ verifier legacy giới hạn 2024 nguyên byte;
snapshot mới ở `outputs/bayesian_benchmark/unified_bic_v1/inputs/execution_prices_2025/`.
Mỗi mã giữ prefix 1.750 nến đã kiểm tới 2024 và nối **249 nến thô 2025**,
tổng 1.999 nến/mã. Chỉ lấy trường raw VCI, nghìn VND; không suy ngược từ
OHLC điều chỉnh. Events sao chép nguyên byte từ nguồn OOS đã có quyền 2025.

Đối chiếu tám mẫu raw/adjusted VCI/KBS và Reference theo quyền, prefix REST
kết thúc trước ngày quyền khớp chuỗi mở rộng. **Sáu mẫu thuộc 2025**; mẫu
chia cổ phiếu VNM là 29/09/2020, MWG là 16/06/2022. Không coi cả tám là
quyền 2025 hoặc gọi snapshot hồi cứu là vintage được lưu tại từng ngày.
Đếm trên lưới step3 neo 02/01/2025, chỉ cycle hoàn tất trong quý, volume
dương và không vắt quyền trong (entry, exit]; không đổi công thức engine:

| Mã | Q1 | Q2 | Q3 | Q4 | Pool hợp lệ | Nến mới |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| FPT | 19 | 18 | 20 | 21 | 78 | 249 |
| MWG | 19 | 19 | 20 | 21 | 79 | 249 |
| VCB | 18 | 19 | 20 | 20 | 77 | 249 |
| VNM | 19 | 19 | 20 | 20 | 78 | 249 |

Không quý nào thiếu tám cycle theo rule nguồn, nhưng **chưa chọn/khóa 128
điểm** hoặc phát hành xác nhận. Manifest giữ `is_execution_plan=false`,
`confirmation_allowed=false`, selected_dates=null. BLOCKED do thiếu giá
trong U10-01/protocol v1 là trạng thái tại lần khóa trước bổ sung này;
giữ nguyên byte ba artifact protocol/phương pháp/fixture U10-02. Source
availability mới phải được producer/release sau bind bằng manifest thực,
không tự sửa hash/cờ protocol cũ hoặc mở API vì giá đã PASS.

[Manifest snapshot](../../../outputs/bayesian_benchmark/unified_bic_v1/inputs/execution_prices_2025/manifest.json)
SHA-256 byte:
`fd63f4f13d15992ba0f2b692ad9b625fee8e766c670b0e5ab10a6595d64c547f`.
**17 file, 1.374.421 byte**, gồm CSV/evidence/events/acquisition từng mã
và manifest bind bốn file code LF, parent OOS và lịch VNINDEX. Artifact
thuộc outputs ignored; cần giữ cùng workspace, clone Git không có dữ liệu.

```powershell
# Nguồn đã có: kiểm toàn bộ hoàn toàn offline.
py -3.13 -X utf8 scripts/prepare_unified_execution_prices.py --verify-only
# Chỉ khi cần thu thập/tiếp tục snapshot chưa đủ; giữ phần đã kiểm.
py -3.13 -X utf8 scripts/prepare_unified_execution_prices.py --download
```

**Kiểm tra mới PASS:** biên dịch hai file Python mới; **31 test trọng tâm
(12 mới)** về giá/PIT/leakage, prefix, quyền, phase lịch và nguồn; CLI tải
thật, verify-only và resume thật đều exit 0. Resume được kiểm với mạng bị
chặn, không HTTP và giữ nguyên byte 17 artifact. Hai thử âm trên bản sao
tạm (sửa CSV rồi tự băm, sửa prefix evidence rồi tự băm) đều bị từ chối.
**4.377 file cũ nguyên byte**, gồm ledger, archive/report W9, ba artifact
protocol U10-02 và root README. QA hash/số liệu/liên kết/diff PASS.

Phạm vi là utility input riêng và test, chưa đổi data path/config/runtime,
PIT/retrieval hoặc hợp đồng kinh tế đang chạy; không sửa dependency frozen
W9. Theo AGENTS.md 1.2 chạy compile/test trọng tâm có leakage, không chạy
toàn compileall/unit/E2E/leakage suite. Đây là gate nguồn giá, không thay
bốn gate implementation U10-08, nomination hoặc release U11.

## U10-03 — Memory/index từ upstream đã kiểm, 24/10/2026

**DONE — memory/index và bốn gate hồi quy PASS.** Triển khai riêng tại
[`core/unified_bayes_memory.py`](../../../core/unified_bayes_memory.py) và
[`scripts/prepare_unified_bayes_memory.py`](../../../scripts/prepare_unified_bayes_memory.py).
Giữ nguyên bank 852 record, HMM, index và dependency W9; không gọi LLM,
đọc Decision làm feature hoặc sinh nhãn 2025. Chưa triển khai/chọn pooling,
task ranking, renderer hoặc runtime U-BICL; các phần đó thuộc U10-04 trở đi.

Memory mới gồm **976 record = 852 gốc + 60 upstream 2023 + 64 upstream 2024**,
không có record bị loại ở nguồn thật. Theo mã FPT/MWG/VCB/VNM lần lượt
**239/245/247/245**. Upstream được phục hồi qua `shared_point(verify_only=True)`,
kiểm point/journal/bundle/source seal, đúng một attempt mỗi stage, dựng lại
tín hiệu từ report/Alpha/tin PIT và kiểm HMM train-only. Plan/cohort/point/
journal khớp archive W9; nguồn tin ngoài archive được bind qua plan đã khóa
và point proof. Code LF và runtime của hai cohort phải khớp dependency W8/W9.

Producer chỉ nhận projection upstream theo whitelist, cấm trường Decision
kể cả trong object con. Nhãn nhập được sinh lại qua
`HistoricalOutcomeGenerator` → `compute_round_trip_net_return`, đúng
Open(t+1)/Close(t+3), phí/slippage hai chiều. Dedup theo ID và `(symbol, cutoff)`;
bản trùng giữ reason, bản mâu thuẫn hoặc khoảng nắm giữ chồng lấn ném lỗi.
Model/options/signal semantics không tương thích được loại với reason;
checksum, PIT, giá/quyền hoặc nhãn sai luôn ném ValueError/AssertionError.

Index version `unified_episode_price_index_v1` dùng bốn feature PIT hiện hữu.
Fold train giữ strict exit trước đầu fold; scope `oos_2023_2025` chỉ mở năm
query, giữ nguyên toàn bộ scaler fit từ train exit≤30/12/2022, không dùng
record 2023/2024 để refit. Metadata giữ vị trí cutoff từ lịch neo 02/01/2018.
Query lọc metadata `exit<cutoff` trước đọc outcome, loại self-match; evidence
đã khai PIT còn future/sửa nhãn phải lỗi. Stats giữ cả record thiếu feature
và quá tuổi; age≤730 theo ngày cutoff chỉ lọc pool examples. Không có I/O,
trích lại feature, fit hoặc sinh nhãn trong hot query.

Snapshot chỉ có exit≤31/12/2024 và không có API append outcome 2025.
Loader tái dựng toàn bộ semantic từ nguồn đã kiểm, không tin cờ PASS hoặc
checksum tự reseal. Artifact mới là input, giữ `is_execution_plan=false`,
`confirmation_allowed=false`; không thay release U11.

[Snapshot memory/index](../../../outputs/bayesian_benchmark/unified_bic_v1/inputs/memory_index_v1.json)
gồm **1 file, 2.861.153 byte**, bind **355 file nguồn** và code/runtime riêng.
SHA-256 byte:
`adbe4051575665e28688b1ed3213bb54bd6272bd29715dc2b2d887c46e8df5b9`.
Artifact thuộc outputs ignored; clone Git không có snapshot này. Có 802 vector
AVAILABLE và 174 UNAVAILABLE được giữ trong population; scaler OOS fit theo
mã FPT/MWG/VCB/VNM là 160/172/201/166 record train. Toàn bộ 852 feature row
gốc, 12 scaler fold×mã và train material khớp index W9 nguyên giá trị.
Kiểm query feature tại 02/01 và 31/12/2025 dùng đúng scaler train; VNM ở
02/01 giữ UNAVAILABLE theo cửa sổ quyền, các ca còn lại AVAILABLE. Pool
theo tuổi, cộng mọi regime, là 124 cycle đầu năm và 64 cycle cuối năm;
đây chưa là support sau similarity, task grouping hoặc readiness gate.
CLI verify thật đã PASS khi chặn HTTP/socket, file Decision/key/ledger và
giá thô 2025; giữ nguyên byte snapshot và 4.513 file cũ được bảo vệ.

```powershell
# Dựng một lần; chạy lại chỉ nhận đúng artifact đã khóa.
py -3.13 -X utf8 scripts/prepare_unified_bayes_memory.py --prepare
# Mặc định cũng là verify-only, tái kiểm nguồn và semantic hoàn toàn offline.
py -3.13 -X utf8 scripts/prepare_unified_bayes_memory.py --verify-only
```

Kiểm thử mới dùng nguồn tổng hợp, gồm future append, self/equal-exit,
poison future outcome, scaler/fold, age 730/731, missing feature, economic
oracle, model/options, Decision contamination, dedup/overlap, source/protocol
tamper và sửa label/scaler/metadata/source rồi tự reseal.

**Nghiệm thu trên Python 3.13.5, đúng code mới:** compileall PASS;
**961/961 unit test PASS** (gồm **24 test mới** của memory, ngoài 12 test
nguồn giá đã có); E2E PASS; **188/188 leakage test PASS**, không vi phạm.
CLI prepare/verify thật PASS; kiểm sau unit/E2E và sau toàn bộ gate giữ
nguyên byte 4.513 file cũ và snapshot. QA số liệu/hash/liên kết/UTF-8/diff
PASS. Sau các gate chỉ cập nhật tài liệu; không đổi code/runtime hoặc nguồn.
**U10 đạt 3/10**, tiếp theo **U10-04** backbone A và kiểm pooling offline
trên 647 query train đã khóa; chưa chạy diagnostics hoặc chọn λ ở U10-03.

## U10-04 — Backbone A và khóa pooling offline, 24/10/2026

**DONE — hierarchical pooling λ=8 PASS/LOCKED theo rule đã khóa;
oracle/CLI nguồn thật và bốn gate hồi quy đầy đủ PASS.** Triển khai riêng
[`core/unified_bayes_statistics.py`](../../../core/unified_bayes_statistics.py),
[`core/unified_bayes_diagnostics.py`](../../../core/unified_bayes_diagnostics.py)
và [`scripts/prepare_unified_bayes_pooling.py`](../../../scripts/prepare_unified_bayes_pooling.py).
Không đổi engine, A/W9, nguồn hoặc memory/index U10-03. Không gọi LLM;
đây là chọn hyperparameter trên train, chưa chứng minh hiệu quả U-BICL.

Stats chia metadata cùng mã có **exit<query** thành C (cùng regime/T/P),
B1 (cùng regime ngoài C), B2 (khác regime); ba nhóm rời nhau, phủ toàn
population PIT. Không lọc theo tuổi, feature, similarity hoặc top-K.
A_reference giữ nguyên cả bốn metric/mask legacy trên nguồn chung; U dùng
`win_rate_long`. A giữ strength=4; pooling tính đúng m2/m1 và Beta ở mục 3,
λ∈{2,4,8}. C rỗng giữ posterior/CrI null, tầng background rỗng ghi reason.
Evidence ghi n/s, IDs, prior weight, tuổi và số cụm 90 phiên; raw n không là
ESS. Readiness A giữ population≥20, pooling giữ nB1+nB2≥20; cả hai cần
nC≥5 và width≤0,75. Stats chưa ready vẫn được chấm nếu có raw posterior.

Replay **647 query train = 325 năm 2021 + 322 năm 2022**. Purge bốn cycle
31/12/2021 đóng ngày 06/01/2022; không sửa diagnostics legacy 651 query.
Kiểm lại shared checkpoint/tín hiệu nguồn và **165 historical-prefix HMM**
đúng ngày query; scaler chỉ fit cycle exit trước đầu fold và giữ nguyên
suốt fold, không fit HMM mới hoặc refit scaler OOS. Cả bốn posterior được
tạo trước đọc target query. Nhãn được sinh lại bằng engine LONG
Open(t+1)→Close(t+3), phí/slippage hai chiều và đối chiếu memory đã kiểm.
Nguồn 2023/2024 chỉ kiểm integrity snapshot, không tham gia loss/chọn λ;
không đọc target hoặc giá thực thi 2025.

Loss dùng **cùng 594 raw posterior hữu hạn** của A và cả ba λ, trước gate
readiness; 53 query C rỗng được ghi missing ID, không điền xác suất 0,5.
Mỗi query có trọng số bằng nhau; Brier dùng xác suất thô, chỉ log loss
clip [10⁻⁶; 1−10⁻⁶]. Coverage ready dưới đây có mẫu số **toàn bộ 647**.

| Backbone | Mean log loss | Mean Brier | Ready / 647 |
| --- | ---: | ---: | ---: |
| A_tp_pool | 0,697884896091 | 0,251467777052 | 352 |
| Pool λ=2 | 0,711699161861 | 0,256553589594 | 396 |
| Pool λ=4 | 0,695111998748 | 0,250213464794 | 396 |
| **Pool λ=8** | **0,684461149017** | **0,245519049601** | **396** |

Xếp hạng bằng số đầy đủ (log loss, Brier, λ): **8 → 4 → 2**; chỉ xét gate
cho λ đứng đầu, không thử runner-up nếu trượt. λ=8 giảm cả hai mean loss,
ready tăng 44 và cả tám ô fold×mã đều có raw common. Số common theo
FPT/MWG/VCB/VNM là **143/144/155/152**; ΔBrier pool−A lần lượt
**−0,002759690 / −0,011322706 / −0,002105476 / −0,007776909**.
Không mã nào tăng quá 0,01; gate PASS, reason rỗng. Đây không phải payoff
hoặc kết quả xác nhận ngoài mẫu.

[Diagnostics](../../../outputs/bayesian_benchmark/unified_bic_v1/inputs/pooling_diagnostics_v1.json)
và [choice](../../../outputs/bayesian_benchmark/unified_bic_v1/inputs/backbone_choice_v1.json)
gồm **2 file, 4.849.990 byte**, bind **1.833 nguồn**, memory/index, code LF,
Python 3.13.5 và 22 package. SHA-256 byte lần lượt:

- Diagnostics (4.847.054 byte): `575b650ceb88b7c69bdbe73786b1240d0a9f0bcc60b820f186b7486535993dca`.
- Choice (2.936 byte): `32d0115b4f65bbd376d2f06ad7abee5f8004bff283d28580cc7a1759daaaa8e4`.

Choice giữ `status=LOCKED`, `choice=hierarchical_pool`, `lambda=8`,
`gate_status=PASS`, bind cả byte lẫn payload diagnostics và source hash.
Hai artifact là input ignored; clone Git không có chúng. Protocol/fixture
U10-02 vẫn nguyên byte: `PENDING_U10_04` là snapshot trước diagnostics;
choice riêng ghi kết quả thực tế cho context/producer tiếp theo. Không sửa
snapshot để giả release; `is_execution_plan=false` và
`confirmation_allowed=false` vẫn giữ. Context/runtime/dry-run và release
xác nhận thuộc các task sau.

U10-05 lấy backbone U từ choice đã kiểm và dùng posterior `pool_8` tương
ứng; A_reference tiếp tục dùng A và bốn metric cũ trên cùng memory. Loader
không suy choice từ snapshot `PENDING_U10_04`, không chọn lại λ theo OOS.

```powershell
# Dựng một lần; chạy lại phải khớp artifact đã khóa, hỗ trợ tiếp tục sau report.
py -3.13 -X utf8 scripts/prepare_unified_bayes_pooling.py --prepare
# Mặc định cũng là verify-only, tái dựng nguồn và toàn bộ 647 query.
py -3.13 -X utf8 scripts/prepare_unified_bayes_pooling.py --verify-only
```

**23 test mới PASS**: oracle fixture posterior/partition/gate/rank, bốn
mask A, C rỗng, PIT/target poison, future append, hot query không I/O,
common intersection/coverage, loss weighting/clipping, winner trượt không
thử tiếp và evidence sửa rồi tự reseal. Oracle độc lập trên nguồn thật
khớp cả 647 partition/posterior/gate/target và 594 common/loss/choice.
CLI prepare và verify thật PASS khi chặn HTTP/socket, Decision, key,
ledger và giá thực thi 2025. Kiểm prepare lặp/tiếp tục sau report và bốn
ca âm sửa posterior/choice/tự reseal/định dạng artifact đều PASS;
**6.579 file cũ nguyên byte**, gồm bank, nguồn, bằng chứng W9, protocol,
memory U10-03, ledger và root README. Artifact mới cũng nguyên byte.

**Nghiệm thu trên Python 3.13.5, đúng code mới:** compileall PASS;
**984/984 unit test PASS** (gồm 23 test U10-04 mới); E2E PASS;
**195/195 leakage test PASS**, không vi phạm. Tái kiểm sau unit/E2E và sau
toàn bộ gate giữ nguyên byte 6.579 file cũ và hai artifact mới. QA số liệu,
hash, liên kết, UTF-8 và diff PASS. Sau khóa diagnostics chỉ cập nhật tài
liệu, không đổi code/runtime/nguồn để chọn lại λ. **U10 đạt 4/10**,
tiếp theo **U10-05** task context/fallback/ranking và prompt.

## U10-05 — Task context, fallback, ranking và renderer, 24/10/2026

**DONE — task context/fallback/ranking và renderer đã khóa; prepare/verifier
cold nguồn thật, oracle độc lập và bốn gate hồi quy đầy đủ PASS.** Triển khai riêng
[`core/unified_bayes_context.py`](../../../core/unified_bayes_context.py),
[`core/unified_bayes_prompt.py`](../../../core/unified_bayes_prompt.py) và
[`scripts/prepare_unified_bayes_context.py`](../../../scripts/prepare_unified_bayes_context.py).
Giữ nguyên code/runtime, protocol/fixture và artifact U10-02–04. Cold loader
chỉ nhận choice/diagnostics U10-04 đúng byte đã khóa, kiểm lại nguồn, code,
runtime và memory/index; không hardcode một choice chưa kiểm hoặc chọn lại λ.

Task ID `symbol|regime|bNNNN` neo lịch VNINDEX 02/01/2018, block=floor(index/90).
Membership gồm toàn cycle cùng mã/regime đã đóng **exit<query**, tuổi cutoff
≤730 ngày; summary s/n giữ cả member thiếu feature hoặc dưới similarity.
Representative dùng bốn tín hiệu và bốn feature giá đã scale train-only,
base≥0,625, score=base×2^(−age/365). Greedy ≤3 nhóm support≥2, thứ tự
(-score, tuổi, task ID, episode ID); thử representative kế tiếp khi xung đột
gap<5 phiên hoặc interval entry–exit đóng overlap. Diversity không đổi
membership/summary, không cộng summary vào posterior.

Một nhóm hợp lệ vẫn là mode `task`; không bù episode để đủ ba task. Không
có task hợp lệ thì `episode_fallback`, giữ thứ tự selector A: score giảm,
exit mới trước, ID tăng và gap≥5 phiên. Population<20 hoặc không còn ví dụ
thì mode `off`, có reason và trace loại. Gate stats/examples độc lập;
feature query thiếu tắt examples nhưng giữ population/posterior. Selector
thuần chỉ nhận metadata/score, không nhận outcome hoặc Decision; nhãn chỉ
dùng cho summary và T/P→net return% sau khi mode/representative đã chọn.

Một base evidence dùng chung cho U_full/U_stats/U_examples. Projection
U_stats không có mode, membership hoặc ID examples; U_examples có summary
s/n và ví dụ nhưng không có posterior/CrI. Prefix giữ horizon
**Open(t+1)→Close(t+3) theo phiên**, mean/CrI95% plug-in/support/prior weight
nếu ready, legend T/P và ID ngắn, % LONG ròng lịch sử và SHORT=CASH. Sidecar
ánh xạ T1–T3/E1–E3 duy nhất về task/cycle và toàn membership; các ID đầy đủ
không được đưa thay legend vào prompt. Không có block visible thì prefix
rỗng nguyên vẹn; renderer không cắt K, legend hoặc nhãn để né ngân sách.

`UnifiedBayesContext.render` tái dựng semantic trên RAM trước projection;
loader sau này phải dùng biên này. Adapter chịu trách nhiệm cấp query feature
từ extractor/nguồn đã kiểm; `transform_query` kiểm schema/cutoff/source/scaler,
sidecar bind hash feature. Verifier artifact tái trích feature từ nguồn thật,
không tin vector do bên ngoài khai. Hot query không I/O, fit, trích lại feature
hoặc sinh nhãn query. Future/self bị lọc trước đọc outcome; evidence khai PIT
còn future hoặc bị sửa semantic rồi tự reseal phải lỗi.
Cold loader vẫn tái kiểm integrity toàn snapshot, gồm nhãn lịch sử 2023/2024;
context không lấy nhãn của chính query để làm feature, summary hoặc ranking.

BRPP≤600 và prompt<6.500 Unicode code point, đúng các biên 600/6499 và
601/6500. Kiểm đủ ba task, regime dài nhất, counts/return lớn, từng visibility,
VI/EN với report bão hòa và reserve đủ 600; giữ nguyên `_distill_report` và
`_cap_report`. `assemble_prompt` chỉ chèn nguyên block trước report đầu;
instruction chung, schema/invocation/shared-off được tích hợp tại U10-06,
không sửa Decision Agent hoặc contract W9 trong U10-05.
Probe với horizon hiện hữu và report bão hòa giữ đủ reserve 600 đạt
**6.269 ký tự VI / 6.286 EN**; prefix nguồn thật tối đa 406 cho prompt
6.075/6.092. Đây là base hiện hữu; U10-06 vẫn phải kiểm lại tổng prompt
sau khi thêm instruction chung mới.

```powershell
# Khóa context/renderer offline từ 60 upstream development có sẵn.
py -3.13 -X utf8 scripts/prepare_unified_bayes_context.py --prepare
# Mặc định cũng là verify-only; dựng lại nguồn/feature/context/prefix.
py -3.13 -X utf8 scripts/prepare_unified_bayes_context.py --verify-only
```

Prepare trên 60 upstream development nguồn thật PASS khi chặn HTTP/socket,
key, ledger, file Decision và giá thực thi 2025. Mode **task=41, off=19,
episode_fallback=0**; fallback được kiểm bằng fixture tổng hợp, không ép
mode trên nguồn thật. Trong 41 điểm task, **34 có ≥2 task visible**,
FPT/MWG/VCB/VNM **3/11/10/10**, đạt gate support ≥12/60 và ≥2/mã.
U_full/U_stats/U_examples có prefix visible **51/46/41**; cả hai block ready
36, chỉ stats 10, chỉ examples 5, cả hai off 9. Đây là coverage context,
không thay gate nomination, runtime dry-run U10-09 hoặc hiệu quả LLM.
Verifier cold dựng lại toàn bộ nguồn/feature/60 context/prefix PASS, giữ
nguyên byte artifact đã khóa và 6.587 file cũ.

[Renderer/context lock](../../../outputs/bayesian_benchmark/unified_bic_v1/inputs/renderer_contract_v1.json)
gồm **1 file, 4.286.929 byte**, bind **357 nguồn trực tiếp**, choice U10-04
và qua choice tái kiểm 1.833 nguồn backbone; code LF/runtime được khóa riêng.
SHA-256 byte: `7536eca3079db8769b4de8b4bcfbdd82b3ad521ea3a89131fb0c27bc1321f635`.
Artifact input ignored giữ full evidence/membership và ba projection của
60 điểm; clone Git không có file này. BRPP tối đa **406/600 ký tự** trên
nguồn thật. `status=LOCKED`, `common_instruction_status=PENDING_U10_06`,
`is_execution_plan=false`, `confirmation_allowed=false`; protocol U10-02
vẫn nguyên byte, không cập nhật snapshot để giả release.

Oracle riêng tính lại score, age, block, greedy/fallback, membership/s/n và
visibility từ snapshot U10-03, khớp đủ 60 điểm. So bản nháp trước sửa verifier
chỉ khác hash code CLI; context/prefix/mode nguyên giá trị. Kiểm prepare lặp,
verify và bốn ca sửa mode/prefix/membership/kiểu counts rồi reseal đều PASS;
**6.587 file cũ nguyên byte**, gồm artifact U10-02–04, W9, ledger và root README.

Test mới phủ fixture block/task/visibility/budget, summary member không đủ
feature, tráo nhãn không đổi ranking/mode, thử representative kế, interval
đóng overlap, tie-break fallback, age/similarity biên, thiếu query feature,
future append/self/equal-exit/target poison, Decision/nhãn lồng trong feature,
hot query và context sửa rồi tự reseal. Regression artifact còn kiểm counts
đổi integer→float sau reseal: prepare và verify phải phân biệt theo digest
JSON, không dùng phép bằng Python cho semantic. Bản nháp trước sửa verifier
được giữ nguyên byte ngoài namespace input; không đổi rule hoặc template.

**Nghiệm thu trên Python 3.13.5, đúng code cuối:** 24 test trọng tâm PASS;
compileall PASS; **1008/1008 unit test PASS** (24 test U10-05 mới);
E2E PASS; **204/204 leakage test PASS**, không vi phạm. Sau unit/E2E và sau
toàn bộ gate, 6.587 file cũ cùng renderer lock vẫn nguyên byte. QA nguồn,
số liệu, hash, liên kết, UTF-8 và diff PASS. Sau khi khóa context/prefix chỉ
cập nhật tài liệu, không đổi code/runtime/nguồn hoặc rule theo outcome.
**U10 đạt 5/10**, tiếp theo **U10-06** shared-off, instruction chung và
journal/retry; chưa gọi LLM U-BICL hoặc phát hành xác nhận.

## Bàn giao thay thế kế hoạch và dọn revision cũ

Đã gỡ 74 tệp được Git theo dõi của revision cũ, gồm 37 tệp Python và các
schema, fixture, báo cáo, bằng chứng riêng W10–W11. Không đổi mã legacy,
W9 hoặc mặc định hệ thống. Kế hoạch tổng và W10–W12 đã đồng bộ; đây không
phải hoàn thành các task U10/U11/U12 hoặc triển khai U-BICL.

Đối chiếu SHA-256 xác nhận report, bootstrap và frozen_results_v1.zip của
holdout W9 cùng outputs/oos_pilot/api_usage.json nguyên byte. Kiểm tra
liên kết/anchor mới, UTF-8, số task và git diff --check đạt; không còn
tham chiếu mã revision đã gỡ trong source và tài liệu đang theo dõi.

Do có gỡ mã liên module, đã chạy lại đủ bốn gate trên Python 3.13.5:
compileall PASS; unit 925/925 PASS (1.957,646 giây); E2E PASS (6,8 giây);
leakage riêng 168/168 PASS (543,364 giây). Đây là kiểm tra hệ thống còn lại
sau dọn revision, không phải bằng chứng kỹ thuật/kinh tế của U-BICL chưa
triển khai. Sau các gate chỉ bổ sung ghi nhận này, không đổi code/runtime.

Thư mục ignored outputs/bayesian_benchmark/bic_icl_v2 còn 896 tệp,
165.457.756 byte. Bộ kiểm tra phê duyệt tự động từ chối thao tác xóa với
thông báo “blocked by policy”, không cung cấp lý do chi tiết. Thư mục này
chưa được xóa và không là đầu vào của kế hoạch mới. Lịch sử Git vẫn giữ
provenance; không sửa lịch sử usage hoặc coi dữ liệu đã xem là chưa xem.
