# Tuần 10 — Thiết kế và triển khai Bayesian ICL revision mới

**Trạng thái: IN PROGRESS, 1/8. W10-01 DONE; xác nhận 2025 BLOCKED.**
Kế hoạch 12 tuần, điều chỉnh ngày 21/10/2026.
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
| W10-01 | Audit exposure/giá 2025, split/mẫu, namespace `bic_icl_v2` | W9 | Hash W9 nguyên; eligibility/exposure PASS hoặc BLOCKED rõ lý do | [x] DONE — audit hoàn tất; xác nhận 2025 BLOCKED, chưa khóa ngày |
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
Chưa gate kỹ thuật nào của revision mới PASS; chưa có API/runtime mới.

QA ngày 21/10/2026: đối chiếu hash report/bootstrap/verification/archive W9,
số liệu publication và diff/liên kết. Đây là tài liệu, không đổi code/test/
runtime/schema/đầu vào; không chạy compileall/unit/E2E/leakage theo AGENTS.md
1.2, không ghi gate cũ thành gate mới. Hash nguồn và kết quả W9 giữ nguyên.

## W10-01 — Audit exposure, giá và mẫu xác nhận, 21/10/2026

**DONE về kiểm toán; gate xác nhận 2025 BLOCKED.** Khảo sát tại commit
`76218e2`, trên nhánh `docs/bic-icl-exposure-eligibility-audit`. Chỉ phân tích
bằng chứng hiện có, checksum, trường ngày và metadata; không tính payoff,
đọc action/return để chọn mẫu, tải thêm giá hoặc gọi API. Không có danh sách
128 ngày, manifest xác nhận hay quyền chạy xác nhận mới từ task này.

### Bằng chứng W9 và phạm vi exposure

Archive [W9-06](../week9/README.md#w9-06--khóa-kết-quả-tái-lập-và-bàn-giao-21102026)
đúng SHA-256 `1db2024a3a338cadcf72692287471f8a14feba49ce8a1b1a488b951896cfec70`.
Đọc lại đủ **4.432 entry**, không trùng/thiếu, đối chiếu từng hash với file
workspace: **4.432/4.432 khớp nguyên byte**. Sáu khóa plan/report/verification/
bootstrap/ledger/publication trong bảng W9-06 giữ nguyên. Không chạy lại
bootstrap hoặc dùng kết quả W9 để chọn phương pháp/mẫu mới.

Kiểm kê gồm **6.028 JSON** dưới `outputs/`, kể cả thư mục ignored, không lỗi
parse; trích trường ngày/khóa, không chấm nhãn hoặc so return. Kiểm thêm tám
CSV dưới `outputs/`, trường ngày của `record.csv`, code Python hiện hành và
tên tệp chứa `2025` trong lịch sử các ref Git local. Các archive lịch sử,
ảnh đã xuất, phiên UI ngoài workspace và lịch sử thao tác cá nhân không
chứng minh được việc chưa xem bằng lượt kiểm kê này.

| Nguồn / hoạt động | Bằng chứng quan sát được | Kết luận exposure |
| --- | --- | --- |
| Archive `data/historical/` | Đã tải năm mã đến 31/12/2025; script `prepare_historical_data.py` mặc định cùng ngày cuối | Dữ liệu 2025 đã hiện diện; không được gọi là chưa từng tiếp cận |
| HMM/bank và các script train/plot | Code cắt train đến 2022; bank 852 và artifact cũ nguyên hash; plot regime giới hạn 2018–2022 | Không thấy đường fit hiện hành dùng 2025; không suy thành chứng nhận chưa tune thủ công |
| Development/repeat/holdout W7–W9 | Không thấy cutoff query 2025 trong JSON đã kiểm; split đang khóa là 2023/2024 | Chưa thấy backtest Decision tại cutoff 2025 trong inventory này |
| Coverage cũ | Ngày entry/exit 2025 chỉ thuộc cutoff 27, 30, 31/12/2024; cả ba bị loại `CROSS_YEAR_EXECUTION` và `EXECUTION_CALENDAR_MISMATCH` ở mỗi mã | Metadata lịch giáp năm, không phải mẫu xác nhận hoặc outcome 2025 |
| Backtest legacy, ablation, robustness | 9/4/18 JSON; các cửa sổ/phiên thực thi được lưu nằm trong 2026. `data_start`/`data_end` bao trùm 2025 | Không thấy điểm chạy 2025, nhưng phạm vi dữ liệu đã nạp không chứng minh 2025 chưa được xem |
| News cache VNM trong historical run | Có `date_parsed` năm 2025; ngày tin khác ngày query; code PIT loại tin sau cutoff | Không dùng cache này làm bằng chứng chưa tiếp cận 2025 hoặc bổ sung tin cho xác nhận |
| Ledger và `record.csv` | Chuỗi `2025` trong ledger là phần UUID; `record.csv` có 45 nến từ 30/07 đến 05/10/2026 | Không coi trùng chuỗi UUID là ngày thử nghiệm |
| Người dùng / người tham gia, file ngoài repo và các bản sao không kiểm được | Chưa có xác nhận phạm vi đã xem return/action 2025 hoặc dùng 2025 chọn ngày/prompt/tune tại thời điểm ghi audit | **UNVERIFIED**, không mặc định là chưa xem khi không có report hoặc chưa có câu trả lời |

**Exposure tổng: UNVERIFIED → BLOCKED cho claim xác nhận 2025.** Xác nhận
của người tham gia phải nêu phạm vi và việc đã dùng dữ liệu để ra quyết định
thiết kế hay chưa; đối chiếu với inventory trên. Lời xác nhận bổ sung không
tự xóa dấu vết exposure trái ngược. Nếu đã dùng outcome 2025 để tune/chọn
ngày, giữ 2025 exploratory; không loại riêng các điểm đã xem để dựng lại
holdout theo kết quả. Không có report không phải bằng chứng độc lập.

### Giá thực thi, quyền và lịch 2025

Đối chiếu checksum **29 file CSV/evidence/events** được ba manifest tham
chiếu, cùng checksum byte của ba manifest. Bộ giá train và OOS đã PASS chỉ
được chấp nhận trong phạm vi cũ; không mở rộng gate cũ sang 2025.

| Manifest | Phạm vi / căn cứ | SHA-256 byte |
| --- | --- | --- |
| [`data/historical/manifest.json`](../../../data/historical/manifest.json) | 2018–2025, 1.999 nến/mã; ghi rõ giá thô và hệ số điều chỉnh chưa xác minh | `0c336ee95af3a016b608742f4355f05a4b99d3825bd2f557327d5df02c67719c` |
| [`data/execution_prices/manifest.json`](../../../data/execution_prices/manifest.json) | `UNADJUSTED_EXECUTION`, PASS đến 31/12/2022; 1.251 nến/mã | `e254273e7fb842cdf9fa60007ea7dcc5994ac7190975a5cf940e57852e52f09c` |
| [`data/execution_prices_oos/manifest.json`](../../../data/execution_prices_oos/manifest.json) | `UNADJUSTED_EXECUTION`, PASS đến 31/12/2024; 1.750 nến/mã | `bb70790062210ad983e5250dae650a3d355cad4d4ba57807411208a5ac9c00f4` |

Chưa có archive giá thô/evidence/Reference/events năm 2025 đã xác minh trong
`data/`. Vì vậy **price gate 2025 BLOCKED**, eligibility thực thi/PIT/quyền
**UNVERIFIED** ở cả bốn mã. Không lấy OHLC archive kỹ thuật thay giá thô;
không diễn giải thiếu event 2025 trong nguồn kết thúc 2024 thành không có
quyền. Hợp đồng kiểm giá tiếp tục theo
[`core/execution_prices.py`](../../../core/execution_prices.py): Open(t+1),
Close(t+3), volume dương cả ba phiên; loại quyền trong `(entry, exit]`, kể cả
barrier do Reference khác Close trước. Không tính nhãn để làm eligibility.

Đọc riêng cột `Datetime`: VNINDEX/FPT/VNM/VCB/MWG có lịch tăng dần, không
trùng và khớp nhau, **249 phiên 02/01–31/12/2025**. Tại cutoff đầu năm có
1.751 nến lịch sử, đủ số dòng warm-up trên archive; đây chưa là proof giá
thô hoặc feature PIT. Lưới step3 neo **02/01/2025**, giữ phase sau mọi loại
trừ, có **83 cutoff** mỗi mã. Đếm thuần lịch như sau:

| Quý | Phiên | Cutoff step3 | Cycle hoàn tất trong quý, trước kiểm giá/quyền | Cutoff loại do biên quý/năm |
| --- | ---: | ---: | ---: | --- |
| Q1 | 58 | 20 | 19 | 31/03/2025 |
| Q2 | 61 | 20 | 19 | 27/06/2025 |
| Q3 | 64 | 21 | 20 | 26/09/2025 |
| Q4 | 66 | 22 | 21 | 29/12/2025 |

**79 cycle/mã chỉ là trần thuần lịch, không là số đủ điều kiện.** Chưa biết
pool N sau kiểm giá, volume, quyền và PIT; chưa chọn tám điểm/quý. Giữ rule
đã đăng ký: lọc eligibility trước, lấy vị trí `floor(j*(N-1)/7)`, j=0..7;
N<8 ở bất kỳ mã/quý thì BLOCKED. Không neo lại step3 sau loại, giảm mẫu hoặc
chọn ngày thay sau outcome/API lỗi. Ngày, reason loại và hash nguồn chỉ khóa
khi đủ bằng chứng; W10-02 còn phải báo MDE/độ rộng CI từ train/dev.

### Split, namespace và bàn giao

| Tập | Vai trò khóa cho revision | Trạng thái ở W10-01 |
| --- | --- | --- |
| 2018–2022 / bank 2020–2022 | Train/diagnostics walk-forward, purge cycle vượt fold; giữ HMM/scaler và bank 852 | Nguồn cũ nguyên byte; chưa có gate mới cho thuật toán revision |
| 2023, 60 upstream | Development exploratory; query chỉ thấy record có exit<cutoff | Không tạo lại lịch hoặc gọi LLM trong audit |
| 2024, 64 upstream W9 | Kết quả xác nhận phiên bản cũ; nguồn memory revision theo rule tối đa 124 upstream 2023/2024 | Đã xem; không dùng chọn lambda/prompt theo return hoặc xác nhận revision |
| 2025, mục tiêu 128 điểm | Chỉ xác nhận sau exposure, giá/PIT/eligibility và protocol/power lock | **BLOCKED**, 0 ngày được khóa; không append cycle 2025 vào memory xác nhận |
| Forward sau lock | Phương án khi 2025 không xác minh được tính độc lập | Chưa có cohort/ngày; không lấy các run 2026 có sẵn làm forward sau lock |

Dành riêng namespace **`bic_icl_v2`**, gốc artifact dự kiến
`outputs/bayesian_benchmark/bic_icl_v2/` và version/identity riêng cho protocol,
nguồn memory/index, development, repeat và xác nhận. Chưa tạo runtime artifact
hoặc CLI; W10-02/06 sẽ khóa schema và tên cụ thể. Không ghi vào namespace
`improvement_v1`, registry/schema W8/W9 hoặc thay hash cũ. Ledger provider
hiện hữu giữ nguyên; namespace mới không được reset quota hoặc nhân bản HTTP
attempt khi reuse. A/R/Numeric phải bind cùng snapshot nguồn của query;
max source 31/12/2024 cho memory xác nhận, không refit scaler bằng 2025.

**Điều kiện mở lại xác nhận:** giải quyết exposure bằng bằng chứng/phạm vi
khai báo; có nguồn giá thô, quyền, đơn vị, provenance và PIT năm 2025 được
verify riêng; tính lại eligibility bốn mã/quý rồi khóa ngày/hash theo rule,
kèm protocol/power trước API. Thiếu điều kiện nào tiếp tục BLOCKED. Nếu
exposure không sạch, dùng forward sau lock hoặc ghi không có xác nhận mới;
revision giữ exploratory và luận văn vẫn dùng bằng chứng W9.

**QA và phạm vi kiểm thử:** diff/liên kết/số đếm/hash PASS; **6.636 file**
bằng chứng/nguồn cũ được băm trước và đối chiếu sau audit, gồm archive W9 và
ledger. Chỉ sửa README tuần và kế hoạch tổng; không đổi code/test/runtime/
schema/đầu vào. Theo AGENTS.md 1.2 không chạy compileall/unit/E2E/leakage;
không ghi gate W8-07 thành gate revision mới. **W10 1/8 DONE**, tiếp theo
**W10-02** thiết kế protocol với nhánh xác nhận BLOCKED nêu trên; không cần
chờ mở API để tiếp tục phần thiết kế offline.
