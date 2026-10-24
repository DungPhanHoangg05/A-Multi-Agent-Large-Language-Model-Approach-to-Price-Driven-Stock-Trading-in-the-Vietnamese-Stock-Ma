# Tuần 10 — Xây dựng phiên bản Bayesian In-Context Learning hợp nhất

**Trạng thái: kế hoạch mới ngày 24/10/2026, 0/10 task triển khai DONE.**
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
| U10-01 | Audit source/exposure, benchmark A, footprint và compatibility | W9 | Nguồn W9 nguyên; 2025 PASS hoặc reason; chưa đọc payoff mới | [ ] TODO |
| U10-02 | Khóa protocol U-BICL, ma trận/claim/limits và fixture | 01 | Một candidate, không quét prompt; công thức/task/mode rõ | [ ] TODO |
| U10-03 | Memory/index revision từ upstream đã có | 02 | PIT/dedup/label/model/scaler/age; không Decision feature | [ ] TODO |
| U10-04 | Backbone A, thử pooling offline và khóa choice | 03 | Oracle/fold/loss/coverage; rule PASS thì nhận, không thì A | [ ] TODO |
| U10-05 | Task context/fallback/ranking và prompt | 03–04 | Label-blind, task support, budget 600/6500; thiếu đúng reason | [ ] TODO |
| U10-06 | Shared-off, instructions chung và journal/retry | 02 | Body/source/repeat binding; prior-off reuse; no hidden policy | [ ] TODO |
| U10-07 | CLI producer/loader/verifier/report | 05–06 | Request/output schema riêng, legacy không đổi, JSON native | [ ] TODO |
| U10-08 | Diagnostics, fixture failure/resume/leakage và bốn gate | 07 | Compileall/unit/E2E/leakage PASS đúng source/runtime | [ ] TODO |
| U10-09 | Dry-run 60 điểm, coverage/MDE và plan repeat | 08 | Lock source/schedule/model; không điều chỉnh theo outcome | [ ] TODO |
| U10-10 | Handoff vận hành và bản thảo phương pháp | 09 | CLI thật run/resume/verify; W11 chỉ chạy đúng release | [ ] TODO |

Module dự kiến: core/unified_bayes_memory.py, unified_bayes_statistics.py,
unified_bayes_context.py, unified_bayes_runtime.py, unified_bayes_reports.py;
scripts/run_unified_bayes.py; schema/fixtures cần thiết dưới W10. Tất cả là
đề xuất, chưa tồn tại. Tái dùng engine, HMM, feature, retry/pacer/ledger đã
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
