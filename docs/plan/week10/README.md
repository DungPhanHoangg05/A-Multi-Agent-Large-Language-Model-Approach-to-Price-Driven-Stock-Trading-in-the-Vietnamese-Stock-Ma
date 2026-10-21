# Tuần 10 — Thiết kế và triển khai Bayesian ICL revision mới

**Trạng thái: TODO, 0/8. Kế hoạch 12 tuần, điều chỉnh ngày 21/10/2026.**
[Kế hoạch tổng](../plan.md) · [W9](../week9/README.md) · [W11](../week11/README.md) · [W12](../week12/README.md)

## Xuất phát và phạm vi

W1–W9 giữ nguyên kết quả. W10 chuyển sang thiết kế/triển khai; W11 chạy
development và khóa xác nhận; W12 xác nhận, phân tích và hoàn thiện luận văn.
Năm task luận văn W10 cũ chưa thực hiện được chuyển sang W12-04–07;
không đánh dấu DONE. Tên module/schema/CLI mới dưới đây là **dự kiến**, chưa
phải công cụ đã triển khai. Không thay mặc định triển khai hoặc risk OFF.

W9 đã xác nhận A−Original **+2,025325 đpt**, CI95% **[0,135027; 4,211864]**
trên 64 điểm/384 Decision. Bốn secondary inconclusive; A prior-off 39/64,
2/39 request giống nhưng action khác; cả stats/examples ready chỉ 10 điểm;
BEAR=0 và tin reliable=0/64. Vì vậy cần củng cố giá trị của ICL và độ phủ,
không coi phiên bản hiện tại hoàn toàn thất bại hoặc bảo đảm revision sẽ thắng.
Nguồn đầy đủ: [W9-04–06](../week9/README.md#w9-04--bootstrap-và-kết-quả-thống-kê-holdout-21102026).

## Đóng góp khóa luận và giới hạn

[Zhu, Oermann, Cho, ICML 2026](https://proceedings.mlr.press/v306/zhu26aj.html)
huấn luyện transformer trên chuỗi prior/target tasks để học dự báo Bayes.
Hệ thống này dùng LLM hosted có sẵn; thêm prefix không chứng minh mô hình
được huấn luyện theo phương pháp đó. Định vị là **thích ứng Bayesian ICL
cho giao dịch: posterior số học minh bạch + tác vụ lịch sử có nhãn trong
context + Decision LLM**, kiểm bằng đối chứng. Không tuyên bố tái hiện đầy
đủ amortized hierarchical Bayes hay confidence LLM được hiệu chuẩn.

| Yêu cầu | Hiện thực cần có | Bằng chứng |
| --- | --- | --- |
| Bayesian | Prior/likelihood/posterior của sự kiện LONG ròng>0 | Oracle, counts, bất định, PIT, calibration ngoài thời gian |
| ICL | Đưa cặp đặc trưng–nhãn lịch sử trước target/query, không cập nhật trọng số LLM | Request/hash/example IDs; full so stats-only/examples-only |
| Multi-task | Nhóm lịch sử có định danh riêng và nhiều cycle mỗi nhóm | Schema nhóm mới; không đổi tên một cycle thành dataset nhiều quan sát |
| Regime-aware | Regime PIT tham gia phân hoạch prior và retrieval | Coverage và phân tích theo regime, không suy BEAR từ mẫu rỗng |
| Giá trị kinh tế | LLM quyết định theo T+2.5, engine không đổi | ΔR/MDD ghép cặp; mô hình số chỉ là đối chứng |

## Thiết kế: tối đa hai ứng viên

Pipeline: dữ liệu PIT → upstream dùng chung → posterior và retrieval →
BRPP → Decision LLM → engine hiện hữu. Hai full-prior candidates là
`R_pool` và `R_task`; ablation không là ứng viên để chọn theo return.
Giữ model/options, schema Decision legacy, distill/cap và risk OFF.

### P0 — Prior-off và nhiễu Decision

Original chạy trước và lưu durable theo point/repeat. Khi candidate không
có prior và **toàn request canonical** giống Original, checkpoint tham chiếu/
deep-copy quyết định Original cùng point/repeat, ghi `decision_origin`, source
hash và reason; không gọi LLM lại, không giả HTTP attempt. Request khác thì
không reuse chỉ vì prefix rỗng. Resume không phát lại Original/upstream complete.
Missing/error không thành CASH; ledger chỉ đếm HTTP thật.

Áp dụng wrapper cho A đối chứng, đặt ID `A_reference_shared_off`: evidence,
prompt và model A giữ nguyên nhưng execution protocol mới, không gọi đây là
W9 chạy lại nguyên trạng. Original đầu block cố định; các nhánh còn lại xoay
theo point/repeat. Duplicate Original độc lập chỉ dùng chẩn đoán; không vote,
thay primary hoặc chọn response thuận lợi. Prior-off disagreement=0 là bất
biến do reuse, không phải bằng chứng LLM deterministic. Không sửa W9 hồi tố.

### R_pool — Empirical Bayes phân cấp cùng mã

Giữ nguyên bank gốc 852 episode và HMM/scaler hiện hữu. Tạo bank revision
append-only theo chính sách làm mới bên dưới; A/R/Numeric dùng cùng snapshot
nguồn của query. Với query, phân hoạch rời nhau sau lọc exit_date < cutoff:

- C: cùng mã/regime, khớp Trend/Pattern.
- B1: cùng mã/regime, không thuộc C.
- B2: cùng mã, regime khác.

Với s là số LONG ròng>0, n là support, mô hình đề xuất:

```text
m2 = (s2 + 1) / (n2 + 2)
m1 = (s1 + lambda*m2) / (n1 + lambda)
theta_C | D ~ Beta(sC + lambda*m1, nC-sC + lambda*(1-m1))
```

Mỗi cycle chỉ thuộc một nhóm; C không bị tính lại trong hyperprior.
n2=0 cho m2=0,5 với reason thiếu background; không giả có quan sát.
Đây là **empirical Bayes plug-in**: CrI có điều kiện trên hyperprior, không
bao gồm toàn bộ bất định m1/m2 hoặc phụ thuộc giữa cycle.

Chỉ thử lambda ∈ {2,4,8} offline theo fold train. Chọn mean log loss trên
query support chung, Brier tie-break rồi lambda nhỏ hơn; không dùng return
2024. R_pool/R_task dùng cùng lambda đã khóa. Gate riêng: nC≥5, n1+n2≥20,
CrI95% width≤0,75; không đủ thì stats off, không trình background như đã có
conditional evidence. Báo coverage raw/ready, tuổi, số cụm thời gian và tỷ
trọng prior lambda/(nC+lambda); raw n không là effective sample size.
Diagnostics theo cụm kiểm độ nhạy; không tự thu hẹp CrI để qua gate.

R_pool giữ selector từng cycle hiện hữu, K≤3. Prefix phiên bản mới báo scope,
nC, posterior và khoảng; không có policy ngoài LLM tự chặn LONG.

### Memory làm mới có giới hạn, bắt buộc trước xác nhận 2025

Selector hiện hữu có max_prior_age_days=730. Bank kết thúc 2022 không còn
ví dụ đủ tuổi cho 2025; không tăng trần tuổi theo return. Revision mới nhập
**tối đa 124 điểm lịch sử đã khóa** từ 60 checkpoint upstream 2023 và 64
checkpoint upstream 2024, không gọi LLM sinh thêm bank. Chỉ dùng upstream
thật tại cutoff, không dùng action/justification/confidence Decision làm
đặc trưng prior. Nhãn tính bằng hàm kinh tế chung trên giá thô đã verify;
không chọn record theo lãi/lỗ.

Adapter phải chứng minh schema/signal/model provenance tương thích, entry/
exit và feature PIT; không chứng minh được thì loại với reason, không đoán
từ Decision. Bank mới union theo episode ID/source, không nhân đôi cycle.
Version, provenance, số nhập/loại và snapshot hash riêng; không sửa bank 852,
index/scaler hoặc checkpoint W9 nguyên bản. Index mới bind scaler cũ đúng
train, không refit bằng 2025; compatibility không đạt thì BLOCKED.

Rule như nhau ở development/xác nhận: record chỉ khả dụng khi exit<query;
query 2023 không thấy record 2024 hoặc cycle chưa đóng, query tự nó luôn bị
loại. Giá/feature/task grouping cutoff trước ranking. 2024 đã xem được khai
báo là **nguồn lịch sử cho revision mới**, không là holdout của revision;
không dùng 2024 chọn lambda/prompt theo return. Không append cycle 2025 trong
cohort xác nhận, kể cả đã đóng; snapshot nguồn tối đa 2024-12-31 khóa trước
run. Dữ liệu sau cutoff trong file không được vào evidence; kiểm future
append invariance bắt buộc. Đây là cập nhật dữ liệu tự động có rule, không
chọn lại phương pháp theo outcome.

A_reference_shared_off dùng cùng nguồn làm mới: đây là **A với memory và
execution revision mới**, không phải cấu hình W9 bất biến. R−A cô lập phần
phương pháp trên nguồn chung; không quy gain do memory refresh cho pooling/
task format. W9 báo riêng. Nếu cache không đủ tương thích/coverage, chặn
xác nhận ICL mới thay vì gọi thêm API hàng loạt hoặc gọi stats-only là đã
chứng minh demonstrations. Báo tuổi/max-age và coverage trước khi khóa.

### R_task — Nhiều tác vụ lịch sử trong context

Posterior giữ nguyên R_pool; chỉ đổi demonstrations. Task định nghĩa bởi
`(symbol, regime, block_20_sessions)`. Block 20 phiên VNINDEX không chồng
lấp, neo bằng lịch train đã bind, không neo lại theo query. Mỗi task chứa
hai cycle PIT khác nhau; chọn theo khoảng cách feature/tín hiệu với query,
không đọc nhãn để xếp hạng hoặc cân bằng thắng/thua. Loại overlap entry–exit
trong demonstrations; tie-break ID cố định.

Chọn tối đa ba task cùng mã/regime theo khoảng cách centroid feature đã
chuẩn hóa train-only, rồi ngày gần, rồi ID. Centroid không dùng return.
Giữ bộ lọc tuổi≤730 ngày và min_similarity=0,625 hiện hữu trước tạo nhóm;
không mở rộng scope/tuổi để đủ nhóm. Trace ghi riêng lý do thiếu nhóm.
Task thiếu hai cycle bị loại; không bịa ví dụ. Có thể trùng population thống
kê nhưng không cộng các ví dụ lần nữa vào posterior.

Schema mới phân biệt `k_tasks≤3`, `examples_per_task=2`, `k_episodes≤6`;
không đổi nghĩa legacy `k=3` (ba cycle). **BRPP vẫn ≤600 ký tự, prompt
<6.500 ký tự**. Template giữ legend, task boundary, x→y, tín hiệu T/P và
return ròng từng cycle theo %. Full feature, ID và nhãn nằm trong sidecar.
Không gọi tỷ lệ/return lịch sử là xác suất/expected return query.

W10-05 phải chứng minh trường hợp biên 3×2 đủ ngữ nghĩa trong 600 ký tự.
Nếu không đạt, R_task BLOCKED **trước API**, chỉ xét R_pool; không tự cắt
nhãn/nhóm hoặc tăng trần. Đây là thích ứng task theo miền, không tự chứng
minh latent task hoặc suy luận nội tại của LLM giống paper.

### Ngoài phạm vi vòng này

Không ghép A+B, quét K/model, fine-tune transformer, đổi HMM/regime mềm,
cross-symbol pooling, mở rộng bank hàng nghìn lời gọi LLM, backfill tin hoặc
thêm risk overlay. Chưa thêm expected-utility policy: báo mean lãi/lỗ lịch
sử để chẩn đoán; xác suất thắng tăng không bảo đảm lợi nhuận tăng. Mô hình
payoff đầy đủ là hướng sau, không trừ phí hai lần hoặc thay ICL bằng rule.

## Dữ liệu và xác nhận mới

| Tập | Vai trò | Rào chắn |
| --- | --- | --- |
| Bank 2020–2022 | Fit và diagnostics walk-forward | Train trước query, purge exit vượt biên, model/scaler đúng prefix từng fold |
| 2023, 60 điểm | Development/chọn R_pool hoặc R_task | Đã xem, luôn exploratory |
| 2024, W9 | Xác nhận phiên bản cũ; failure analysis và nguồn memory mới theo rule | Đã ảnh hưởng thiết kế mới, không xác nhận revision mới hoặc chọn lambda |
| 2025, dự kiến 128 điểm | Xác nhận mới nếu exposure audit PASS | Giá thô/quyền/PIT/provenance và chưa dùng tune phải kiểm được |
| 2025 không sạch | Forward paper cohort sau lock, hoặc không có xác nhận mới | Không ép đủ mẫu trong W12; dùng W9 cho luận văn, revision mới exploratory |

W10-01 lập inventory việc code/report/người dùng đã xem return/action hoặc
dùng 2025 để chọn ngày/tune. Không có report không chứng minh chưa xem;
không xác minh được thì UNVERIFIED. Archive giá 2018–2025 không bảo đảm giá
thô 2025 đạt hợp đồng. Trước lock chỉ kiểm metadata/lịch/eligibility, không
đọc payoff để chọn mẫu; không dùng phần 2024 còn lại làm holdout mới.

Lịch 2025: 32 điểm/mã, tám/quý, 128 tổng; step3 neo phiên đầu năm, cycle
hoàn tất trong quý, loại quyền/thiếu giá theo rule hiện hữu. Với pool N ngày
hợp lệ mỗi mã/quý, lấy vị trí `floor(j*(N-1)/7), j=0..7`. N<8 thì BLOCKED,
không hạ cỡ mẫu sau outcome. Khóa ngày/loại trừ/hash trước API. 128 là mục
tiêu coverage, chưa bảo đảm power; W10-02 simulation trên train/dev báo MDE
và độ rộng CI dự kiến, không dùng payoff 2025 để chọn n.

## Checklist

| Task | Công việc / đầu ra | Phụ thuộc | Nghiệm thu | Trạng thái |
| --- | --- | --- | --- | --- |
| W10-01 | Audit exposure/giá 2025, split/mẫu, namespace `bic_icl_v2` | W9 | Hash W9 nguyên; eligibility/exposure PASS hoặc BLOCKED rõ lý do | [ ] TODO |
| W10-02 | Khóa giả thuyết, task semantics, estimand/matrix/MDE/protocol | 01 | Phân biệt Bayes/ICL/policy; fallback và mẫu khóa trước API | [ ] TODO |
| W10-03 | Shared-off wrapper, duplicate/checkpoint/recovery | 02 | Reuse đúng point/repeat/request; ledger thật, prior-off=Original | [ ] TODO |
| W10-04 | Adapter memory đã lưu, R_pool, gate và diagnostics train | 02 | Nguồn tương thích/dedup; partition/oracle/PIT PASS; lambda khóa; báo loss bất lợi | [ ] TODO |
| W10-05 | R_task grouping/selector/renderer | 04 | Label-blind, overlap, 3×2 trong 600; BLOCKED nếu không đạt | [ ] TODO |
| W10-06 | Producer/loader/verifier/CLI và fixture kinh tế | 03–05 | Một upstream, schema riêng, JSON native, horizon và hai ngôn ngữ nhất quán | [ ] TODO |
| W10-07 | Bốn gate, source freeze, dry-run development/repeat | 06 | Compileall/unit/E2E/leakage PASS đúng code/runtime | [ ] TODO |
| W10-08 | Hướng dẫn API/resume/verify và chương phương pháp | 07 | CLI thật, model pin/risk OFF; bàn giao W11 | [ ] TODO |

## Module và kiểm thử dự kiến

| Phần | Tệp mới dự kiến / tái dùng | Kiểm tra |
| --- | --- | --- |
| Protocol | `core/bic_icl_protocol.py`, schema tại `docs/plan/week10/` | Version/hash/exposure lock; không sửa registry W8/W9 |
| Bayes | `core/bic_icl_statistics.py`, nhãn engine chung | Counts/n=0/oracle/PIT, future append invariance, JSON native |
| Memory revision | `core/bic_icl_memory.py`, adapter upstream/checkpoint cũ | Không dùng Decision làm feature; provenance/compatibility/dedup/source snapshot/cutoff |
| Task/context | `core/bic_icl_tasks.py`, `core/bic_icl_prompt.py`, feature/scaler cũ | Đổi nhãn không đổi rank/ID, overlap, budget, schema |
| Runtime | `core/bic_icl_runtime.py`, `scripts/run_bic_icl.py`, retry/ledger/journal cũ | Crash/resume/unknown, shared-off, upstream một lần |
| Report | `core/bic_icl_reports.py`, engine/metric/bootstrap hiện hữu có version | Support, alias không tạo mẫu mới, cluster/repeat, không đổi W9 |

P0/liên module phải đủ bốn gate AGENTS.md; retrieval/pooling/task phải có
leakage suite. Không sửa hash W9 để nhận code mới: tái lập W9 bằng checkout/
archive cũ riêng khi cần; manifest mới bind revision mới. Không trộn refactor
verifier vào nâng cấp thuật toán nếu chưa profiling và test tương đương.

## Điểm dừng và QA kế hoạch

Hết W10, R_task chưa đạt thì loại trước API; R_pool cũng chưa đạt thì dừng
nâng cấp và hoàn thiện luận văn bằng W9. Không mở ứng viên thứ ba hoặc hạ
gate. Viết chương phương pháp trong W10, khung bảng/hình trong W11 để giữ W12.
Chưa gate nào của revision mới PASS; không có API/runtime mới ở task lập plan.

QA ngày 21/10/2026: đối chiếu hash report/bootstrap/verification/archive W9,
số liệu publication và diff/liên kết. Đây là tài liệu, không đổi code/test/
runtime/schema/đầu vào; không chạy compileall/unit/E2E/leakage theo AGENTS.md
1.2, không ghi gate cũ thành gate mới. Hash nguồn và kết quả W9 giữ nguyên.
