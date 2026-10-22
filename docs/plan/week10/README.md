# Tuần 10 — Thiết kế và triển khai Bayesian ICL revision mới

**Trạng thái: IN PROGRESS, 5/8. W10-01–05 DONE; task/context đạt nghiệm thu kỹ thuật offline, R_task chưa đủ coverage đề cử trên cache; chưa có CLI cohort/release xác nhận.**
Kế hoạch 12 tuần, điều chỉnh ngày 21/10/2026.
[Kế hoạch tổng](../plan.md) · [W9](../week9/README.md) · [W11](../week11/README.md) · [W12](../week12/README.md)

## Xuất phát và phạm vi

W1–W9 giữ nguyên kết quả. W10 chuyển sang thiết kế/triển khai; W11 chạy
development và khóa xác nhận; W12 xác nhận, phân tích và hoàn thiện luận văn.
Năm task luận văn W10 cũ chưa thực hiện được chuyển sang W12-04–07;
không đánh dấu DONE. Các phần chưa ghi rõ đã triển khai dưới đây vẫn là
**dự kiến**. Chưa có CLI cohort revision. Không thay mặc định triển khai hoặc risk OFF.

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
tiêu coverage, chưa bảo đảm power; [power audit W10-02](#w10-02--khóa-protocol-và-power-audit-22102026)
đã báo MDE/độ rộng CI proxy trên train/dev, không dùng payoff 2025 để chọn n.

## Checklist

| Task | Công việc / đầu ra | Phụ thuộc | Nghiệm thu | Trạng thái |
| --- | --- | --- | --- | --- |
| W10-01 | Audit exposure/giá 2025, split/mẫu, namespace `bic_icl_v2` | W9 | Hash W9 nguyên; eligibility/exposure PASS hoặc BLOCKED rõ lý do | [x] DONE — giá/lịch 128 điểm và exposure PASS theo khai báo + inventory; chờ protocol/release |
| W10-02 | Khóa giả thuyết, task semantics, estimand/matrix/MDE/protocol | 01 | Phân biệt Bayes/ICL/policy; fallback và mẫu khóa trước API | [x] DONE — protocol v1 và 30 scenario power planning; không chứng nhận đủ power |
| W10-03 | Shared-off wrapper, duplicate/checkpoint/recovery | 02 | Reuse đúng point/repeat/request; ledger thật, prior-off=Original | [x] DONE — 32 test mới, 978 unit/204 leakage và compileall/E2E PASS |
| W10-04 | Adapter memory đã lưu, R_pool, gate và diagnostics train | 02 | Nguồn tương thích/dedup; partition/oracle/PIT PASS; lambda khóa; báo loss bất lợi | [x] DONE — memory 976, lambda=8; 38 test mới, 1.016 unit/215 leakage và compileall/E2E PASS |
| W10-05 | R_task grouping/selector/renderer | 04 | Label-blind, overlap, 3×2 trong 600; BLOCKED nếu không đạt | [x] DONE — 40 test mới, 1.056 unit/227 leakage và compileall/E2E PASS; coverage cache chưa đủ đề cử |
| W10-06 | Producer/loader/verifier/CLI và fixture kinh tế | 03–05 | Một upstream, schema riêng, JSON native, horizon và hai ngôn ngữ nhất quán | [ ] TODO |
| W10-07 | Bốn gate, source freeze, dry-run development/repeat | 06 | Compileall/unit/E2E/leakage PASS đúng code/runtime | [ ] TODO |
| W10-08 | Hướng dẫn API/resume/verify và chương phương pháp | 07 | CLI thật, model pin/risk OFF; bàn giao W11 | [ ] TODO |

## Module và kiểm thử dự kiến

| Phần | Tệp mới dự kiến / tái dùng | Kiểm tra |
| --- | --- | --- |
| Protocol | `core/bic_icl_protocol.py`, schema tại `docs/plan/week10/` | Version/hash/exposure lock; không sửa registry W8/W9 |
| Shared Decision | `core/bic_icl_decisions.py` đã triển khai tại W10-03 | Canonical shared-off/stats alias, duplicate độc lập, raw/ledger/source receipt, resume cùng UUID |
| Bayes | `core/bic_icl_statistics.py` đã nghiệm thu W10-04 | Counts/n=0/oracle/PIT, future append invariance, JSON native |
| Memory revision | `core/bic_icl_memory.py` đã nghiệm thu W10-04 | Không dùng Decision làm feature; provenance/compatibility/dedup/source snapshot/cutoff |
| Chuẩn bị offline | `core/bic_icl_diagnostics.py`, `scripts/prepare_bic_icl_memory.py` | Rebuild memory/index/train và verify bất biến; không là CLI cohort/Decision |
| Task/context | `core/bic_icl_tasks.py`, `core/bic_icl_prompt.py` đã nghiệm thu W10-05; feature/scaler cũ | Label-blind, centroid/overlap, budget 3×2, schema/alias legacy |
| Preflight context offline | `scripts/prepare_bic_icl_context.py`, fixture JSON tại tuần 10 | Verify snapshot W10-04; rebuild 60 context, hai template ngôn ngữ, không gọi Decision |
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
Chưa có runtime Decision revision mới; bốn gate cho công cụ audit W10-01
không thay nghiệm thu W10-07 sau triển khai thuật toán.

QA kế hoạch ban đầu ngày 21/10/2026: đối chiếu hash report/bootstrap/verification/archive W9,
số liệu publication và diff/liên kết. Đây là tài liệu, không đổi code/test/
runtime/schema/đầu vào; không chạy compileall/unit/E2E/leakage theo AGENTS.md
1.2, không ghi gate cũ thành gate mới. Hash nguồn và kết quả W9 giữ nguyên.

## W10-01 — Audit exposure, giá và mẫu xác nhận, 21/10/2026

**DONE; giá thô, lịch 128 điểm và exposure PASS.** Exposure được cập nhật bằng
khai báo làm rõ của người dùng và snapshot inventory local; đây chưa là
release cho phép chạy xác nhận. Inventory ban đầu tại `76218e2`, merge audit tại
`65fa4ca`; sau yêu cầu bổ sung của người dùng, nhánh
`feat/bic-icl-confirmation-input-audit` thêm công cụ tải/verify giá công khai
và lịch khả thi trong namespace riêng. Không gọi LLM, tính payoff hoặc đọc
action/return 2025 để chọn mẫu. Có lịch 128 điểm mã–ngày đã bind nguồn/hash; đây chưa
phải manifest/release cho phép chạy xác nhận.

### Bằng chứng W9 và phạm vi exposure

Archive [W9-06](../week9/README.md#w9-06--khóa-kết-quả-tái-lập-và-bàn-giao-21102026)
đúng SHA-256 `1db2024a3a338cadcf72692287471f8a14feba49ce8a1b1a488b951896cfec70`.
Đọc lại đủ **4.432 entry**, không trùng/thiếu, đối chiếu từng hash với file
workspace: **4.432/4.432 khớp nguyên byte**. Sáu khóa plan/report/verification/
bootstrap/ledger/publication trong bảng W9-06 giữ nguyên. Không chạy lại
bootstrap hoặc dùng kết quả W9 để chọn phương pháp/mẫu mới.

Kiểm kê ban đầu gồm **6.028 JSON** dưới `outputs/`, kể cả thư mục ignored, không lỗi
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
| Người dùng / người tham gia, file ngoài repo và các bản sao không kiểm được | Ban đầu trả lời **“Không chắc hoặc không thể xác minh”**; sau đó làm rõ: **“Xác nhận kết quả 2025 chưa được dùng để lựa chọn hoặc điều chỉnh phương pháp.”** | **PASS trong phạm vi khai báo không dùng outcome để chọn/tune và inventory local**; không chứng nhận chưa từng xem hoặc kiểm toán độc lập mọi hoạt động ngoài workspace |

**Exposure hiện tại PASS**, basis `PARTICIPANT_DECLARATION_AND_LOCAL_INVENTORY`.
Khai báo làm rõ tại [`exposure_inventory_v2.json`](exposure_inventory_v2.json)
bind hash bản [`v1`](exposure_inventory_v1.json) và review, không xóa lịch sử
UNVERIFIED. Snapshot mới rà **6.033 JSON**, gồm cả thư mục ignored và metadata
nguồn giá mới, không phát hiện ngày query 2025 trong các trường cutoff/window/
data_end. Các audit lịch/metadata có định danh riêng được tách khỏi query
thực nghiệm. Không có report chỉ là một phần bằng chứng; quyết định PASS còn
dựa vào xác nhận không dùng outcome để lựa chọn/điều chỉnh phương pháp.

`unseen_outcomes_proven=false`: không suy lời xác nhận này thành chưa từng
xem outcome. Hoạt động ngoài workspace được khai báo, chưa kiểm toán độc lập.
Query 2025 trái ngược, nguồn đổi checksum, khai báo thiếu hoặc thừa nhận dùng
outcome đều chặn PASS; chỉ sửa cờ trạng thái hoặc băm lại không đủ. Nếu sau này
phát hiện đã dùng 2025 chọn/tune, giữ 2025 exploratory và chuyển sang forward
sau lock hoặc báo không có xác nhận mới; không loại riêng điểm đã xem theo
kết quả. Replay kiểm đúng snapshot tại thời điểm rà soát, không công bố rằng
đã kiểm mọi file/hoạt động phát sinh về sau.

### Giá thực thi, quyền và lịch 2025

Đối chiếu checksum **29 file CSV/evidence/events** được ba manifest tham
chiếu, cùng checksum byte của ba manifest. Bộ giá train và OOS đã PASS chỉ
được chấp nhận trong phạm vi cũ; không mở rộng gate cũ sang 2025.

| Manifest | Phạm vi / căn cứ | SHA-256 byte |
| --- | --- | --- |
| [`data/historical/manifest.json`](../../../data/historical/manifest.json) | 2018–2025, 1.999 nến/mã; ghi rõ giá thô và hệ số điều chỉnh chưa xác minh | `0c336ee95af3a016b608742f4355f05a4b99d3825bd2f557327d5df02c67719c` |
| [`data/execution_prices/manifest.json`](../../../data/execution_prices/manifest.json) | `UNADJUSTED_EXECUTION`, PASS đến 31/12/2022; 1.251 nến/mã | `e254273e7fb842cdf9fa60007ea7dcc5994ac7190975a5cf940e57852e52f09c` |
| [`data/execution_prices_oos/manifest.json`](../../../data/execution_prices_oos/manifest.json) | `UNADJUSTED_EXECUTION`, PASS đến 31/12/2024; 1.750 nến/mã | `bb70790062210ad983e5250dae650a3d355cad4d4ba57807411208a5ac9c00f4` |
| [Manifest giá revision](../../../outputs/bayesian_benchmark/bic_icl_v2/inputs/execution_prices_2025/manifest.json) | Snapshot mới 2018–2025, PASS; 1.999 nến/mã, prefix giá cũ không đổi, thêm 249 nến thô 2025/mã | `320fd13d734c0a552adb186918e1dca6ac1f3a5f578a46451fb9310874ef1bcf` |

**Sửa kết luận audit ban đầu:** phạm vi giá của manifest OOS kết thúc 2024,
nhưng chính các file events cũ **đã có quyền 2025**: FPT bốn ngày,
VNM/VCB/MWG mỗi mã hai ngày. Không cần tải lại hoặc sửa các file quyền.
Nguồn mới nối prefix raw 2018–2024 đã verify với raw VCI 2025, sao chép
events nguyên byte vào snapshot mới. Đối chiếu toàn CSV với trường thô VCI,
đơn vị nghìn VND, lịch VNINDEX và prefix cũ PASS. Có tám mẫu kiểm toán
VCI/KBS, hai loại quyền/mã, tính lại Reference và kiểm prefix request.
Sáu mẫu ở 2025; mẫu chia cổ phiếu VNM là 29/09/2020, MWG là 16/06/2022;
không gọi cả tám mẫu là quyền 2025. Không lấy OHLC archive kỹ thuật thay giá
thô. Hợp đồng kiểm giá tiếp tục theo
[`core/execution_prices.py`](../../../core/execution_prices.py): Open(t+1),
Close(t+3), volume dương cả ba phiên; loại quyền trong `(entry, exit]`, kể cả
barrier do Reference khác Close trước. Không tính nhãn để làm eligibility.
Đây là xác minh dữ liệu hồi cứu và prefix thô, không phải chứng nhận vintage
đã lưu trực tiếp tại từng ngày 2025 hoặc nghiệm thu adapter memory W10-04.

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

**79 cycle/mã là trần thuần lịch.** Sau kiểm nguồn, volume, quyền, warm-up,
entry/exit đúng phiên và biên quý, pool đủ điều kiện trên lưới là:

| Mã | Q1 | Q2 | Q3 | Q4 | Tổng pool | Số ngày chọn |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| FPT | 19 | 18 | 20 | 21 | 78 | 32 |
| VNM | 19 | 19 | 20 | 20 | 78 | 32 |
| VCB | 18 | 19 | 20 | 20 | 77 | 32 |
| MWG | 19 | 19 | 20 | 21 | 79 | 32 |

Giữ rule đã đăng ký: lọc eligibility trước, lấy vị trí
`floor(j*(N-1)/7)`, j=0..7; **128/128 điểm mã–ngày trên 41 cutoff khác nhau**,
không quý thiếu tám điểm. Không coi 128 điểm là 128 cụm ngày độc lập.
Không neo lại step3 sau loại, giảm mẫu hoặc chọn ngày thay sau outcome/API
lỗi. Lịch daily/selected, reason loại và hash nguồn được lưu trong audit;
**is_execution_plan=false, confirmation_allowed=false**. Đặc tả và MDE/
độ rộng CI từ train/dev đã được khóa riêng tại W10-02 bên dưới; audit
đầu vào không tự chuyển thành execution plan hoặc release API.

### Split, namespace và bàn giao

| Tập | Vai trò khóa cho revision | Trạng thái ở W10-01 |
| --- | --- | --- |
| 2018–2022 / bank 2020–2022 | Train/diagnostics walk-forward, purge cycle vượt fold; giữ HMM/scaler và bank 852 | Nguồn cũ nguyên byte; chưa có gate mới cho thuật toán revision |
| 2023, 60 upstream | Development exploratory; query chỉ thấy record có exit<cutoff | Không tạo lại lịch hoặc gọi LLM trong audit |
| 2024, 64 upstream W9 | Kết quả xác nhận phiên bản cũ; nguồn memory revision theo rule tối đa 124 upstream 2023/2024 | Đã xem; không dùng chọn lambda/prompt theo return hoặc xác nhận revision |
| 2025, 128 điểm | Lịch khả thi đã bind nguồn; exposure đủ điều kiện theo khai báo + inventory | Giá/lịch/exposure **PASS**, chờ protocol/power/candidate/release; không append cycle 2025 vào memory xác nhận |
| Forward sau lock | Phương án khi 2025 không xác minh được tính độc lập | Chưa có cohort/ngày; không lấy các run 2026 có sẵn làm forward sau lock |

Dành riêng namespace **`bic_icl_v2`**, gốc artifact
`outputs/bayesian_benchmark/bic_icl_v2/` và version/identity riêng cho protocol,
nguồn memory/index, development, repeat và xác nhận. Đã có CLI audit input
riêng và đặc tả v1; chưa có runtime Decision/release xác nhận, W10-06 sẽ
ánh xạ đặc tả vào schema/consumer tương ứng. Không ghi vào namespace
`improvement_v1`, registry/schema W8/W9 hoặc thay hash cũ. Ledger provider
hiện hữu giữ nguyên; namespace mới không được reset quota hoặc nhân bản HTTP
attempt khi reuse. A/R/Numeric phải bind cùng snapshot nguồn của query;
max source 31/12/2024 cho memory xác nhận, không refit scaler bằng 2025.

**Điều kiện phát hành xác nhận:** giữ nguồn giá/lịch/exposure hiện tại qua
verifier, khóa protocol/power, có candidate đủ điều kiện và release trước
API. Thiếu điều kiện nào chưa cho chạy xác nhận. Nếu
exposure không sạch, dùng forward sau lock hoặc ghi không có xác nhận mới;
revision giữ exploratory và luận văn vẫn dùng bằng chứng W9.

**QA lượt audit ban đầu:** diff/liên kết/số đếm/hash PASS; **6.636 file**
bằng chứng/nguồn cũ được băm trước và đối chiếu sau audit, gồm archive W9 và
ledger. Chỉ sửa README tuần và kế hoạch tổng; không đổi code/test/runtime/
schema/đầu vào. Theo AGENTS.md 1.2 không chạy compileall/unit/E2E/leakage;
không ghi gate W8-07 thành gate revision mới. **W10 1/8 DONE**, tiếp theo
**W10-02** thiết kế protocol; ở lượt ban đầu exposure còn BLOCKED. Không cần
chờ mở API để tiếp tục phần thiết kế offline.

### Công cụ và tái lập phần bổ sung

[`scripts/audit_bic_icl_inputs.py`](../../../scripts/audit_bic_icl_inputs.py)
dùng helper giá hiện hữu, không sửa 74 dependency đã khóa của W9. `--download`
chỉ lấy giá công khai, checkpoint theo mã; `--review-exposure` đóng băng
inventory cho khai báo; `--build` lưu audit v2 một lần;
`--verify` tái dựng toàn payload và đối chiếu envelope/hash, hoàn toàn offline.
Không ghi đè audit khi code/nguồn thay đổi; không đưa missing thành CASH.

```powershell
# Chỉ dùng khi cần thu thập hoặc resume nguồn mới; không gọi LLM/API key.
py -3.13 -X utf8 scripts/audit_bic_icl_inputs.py --download
# Đóng băng inventory rà soát; chạy lại chỉ chấp nhận cùng snapshot.
py -3.13 -X utf8 scripts/audit_bic_icl_inputs.py --review-exposure
# Khóa lịch, nguồn và khai báo exposure trong input_audit_v2.json.
py -3.13 -X utf8 scripts/audit_bic_icl_inputs.py --build
# Tái lập cả giá, quyền, lịch 128 điểm và gate exposure từ nguồn đã lưu.
py -3.13 -X utf8 scripts/audit_bic_icl_inputs.py --verify
```

Artifact lịch sử [input_audit.json](../../../outputs/bayesian_benchmark/bic_icl_v2/input_audit.json),
version `bic_icl_v2_input_audit_v1`, bind 15 nguồn và năm file code;
SHA-256 byte `2af54c962840645cc0b2b09c91a75346c8fcaaa17340228d6b3d108040229fe5`,
digest payload `cabd2425edcc31ac713bdadf595d5afa95e5eb2e6bf00b23021e4906c611bda3`.
Giữ nguyên byte v1 và khai báo v1; tái lập consumer v1 tại commit `8fd9156`.
CLI hiện tại mặc định build/verify artifact v2, không ghi đè v1.

Artifact mới [input_audit_v2.json](../../../outputs/bayesian_benchmark/bic_icl_v2/input_audit_v2.json),
version `bic_icl_v2_input_audit_v2`, bind 18 nguồn và năm file code;
SHA-256 byte `9f1c2fed3a8955107ecb63f83da7651fd3a3f17c6e9a964c4ab5092d2c4a75f8`,
digest payload `a82e5403eaf8a59671554314f896ae5ac2a15e0178990db7eddb367f4d2c66cb`.
`status=PASS`, `input_eligible=true`, `blocking_reasons=[]`;
`confirmation_allowed=false`, `is_execution_plan=false`, còn
`FROZEN_METHOD_AND_POWER_PROTOCOL` và `ELIGIBLE_CANDIDATE_AND_RELEASE`.
Lịch/128 điểm giống nguyên payload v1, không chọn lại mẫu theo khai báo.

Review [exposure_review_v2.json](../../../outputs/bayesian_benchmark/bic_icl_v2/exposure_review_v2.json)
pin 6.033 JSON và trường ngày, SHA-256 byte
`233401b3cb7d1116197bd1480d48070d4da65581ac477836a8227f37454645aa`.
Archive [exposure_sources_v2.zip](../../../outputs/bayesian_benchmark/bic_icl_v2/exposure_sources_v2.zip)
giữ nguyên byte đủ 6.033 JSON, 408.877.450 byte gốc/67.658.394 byte ZIP;
SHA-256 `f142c8741f901fd02ad247e305f18444f58e371ed7a5a037e1aac5961ff3846b`.
Loader kiểm SHA archive, tên/entry/hash từng nguồn và trích lại ngày query
trước khi xét khai báo. Review chỉ lưu hash/ngày; archive giữ byte nguồn,
không chấm action/return để chọn mẫu.

Replay `--verify` dùng archive, nên ledger tăng hợp lệ sau lock vẫn tái lập
được audit cũ. `--review-exposure` rà inventory live hiện tại và từ chối ghi
đè nếu khác snapshot; khi cần rà thời điểm mới phải tạo phiên bản review mới.
Archive complete nhưng chưa ghi receipt có thể phục hồi khi còn khớp nguồn;
nguồn/archive hỏng không được nhận PASS hoặc âm thầm bỏ qua.
Nguồn/raw/audit trong `outputs/bayesian_benchmark/bic_icl_v2/` là ignored,
phải giữ cùng workspace; clone Git chỉ có công cụ, test và khai báo exposure.
Không thay checksum W9 để nhận code mới. Không có lệnh chạy Decision hoặc
phát hành xác nhận trong task này.

**Phạm vi QA bổ sung:** đây là thay đổi công cụ và đường dữ liệu/PIT, áp
dụng đủ bốn gate AGENTS.md 1.2 trên Python 3.13.5. Unit/leakage được chia
theo nguyên module vào bốn tiến trình độc lập, giữ thứ tự trong module;
đối chiếu multiset test ID với `unittest discover`, giữ cả bội số có sẵn,
không bỏ ca hoặc giảm suite. Các tệp mới có quy tắc giữ byte khi checkout
để checksum audit không đổi do chuyển LF/CRLF.

CLI `--build`, `--verify` và chạy lại `--download` trên nguồn complete đã
PASS: complete chỉ verify offline, không tải lại hoặc đổi timestamp/hash.
Oracle riêng dựng eligibility/rank từ lịch, volume, quyền và Reference,
khớp đủ 128 điểm và mọi pool quý; CSV snapshot bắt đầu bằng nguyên byte
CSV 2018–2024 cũ. Các kiểm tra mới gồm horizon/biên quý/overlap, thiếu
phiên, quyền tại entry/exit, Reference gap, payoff-blind ranking, future
append invariance, JSON native, namespace containment, exposure và resume.

**Nghiệm thu nguồn giá v1 tại `8fd9156` PASS:** compileall toàn codebase, **937 unit/180
leakage**, E2E xác định; không lỗi hoặc skip. Inventory của cả hai suite
khớp đầy đủ discovery trên đúng code cuối, gồm **12 test mới** tại
[`test_bic_icl_input_audit_leakage.py`](../../../tests/test_bic_icl_input_audit_leakage.py).
CLI verify thật exit 0; oracle lịch/rank, liên kết, diff, checksum audit và
source PASS. **6.636 file cũ**, trong đó archive W9 đủ 4.432 entry và ledger,
giữ nguyên byte; snapshot giá mới cũng giữ nguyên byte prefix CSV cũ.
Không có nhãn/Decision 2025 hoặc HTTP LLM mới. Đây là gate của công cụ audit
input v1; W10-07 phải nghiệm thu lại sau triển khai thuật toán/runtime.
Đây là kết quả của v1, không ghi thành gate đã chạy cho consumer v2.

**Đối soát exposure v2:** bổ sung chín ca, module hiện có **21 test trọng tâm
PASS**. Kiểm khai báo thiếu/mâu thuẫn, cờ mở release, query 2025, sửa nguồn
hoặc lịch sử, inventory rỗng, traversal, ledger tăng sau lock và khôi phục
archive complete còn thiếu receipt. CLI `--build`/`--verify` thật exit 0;
**6.651 file cũ nguyên byte**, lịch 128 điểm không đổi, 18 source/5 code hash
khớp audit, liên kết/diff/checksum tài liệu PASS. Không gọi LLM hoặc sinh
nhãn kinh tế 2025 trong lượt này.

**Nghiệm thu consumer v2 PASS:** compileall toàn codebase, **946 unit/189
leakage**, E2E xác định trên Python 3.13.5; không lỗi, skip hoặc expected
failure. Multiset test ID của cả hai suite khớp đầy đủ discovery, gồm đủ
21 ca module audit. Gate chạy trên đúng byte code/khai báo đã bind trong
audit v2, có kiểm lại identity cuối lượt; không dùng gate v1 thay thế.
W10-01 chốt gate đầu vào tại mốc **1/8**; không thay release xác nhận.

## W10-02 — Khóa protocol và power audit, 22/10/2026

**DONE, W10 2/8.** Đặc tả độc lập
[`method_protocol_v1.md`](method_protocol_v1.md), version
`bic_icl_method_protocol_v1`, đã khóa trước phép mô phỏng. Hash SHA-256
UTF-8 sau chuẩn hóa LF:
`e9c8410bed048733d1ad3faa296a200409c91bfd8be72557d98639ecd8e8313b`.
Không hash README tiến độ làm phương pháp; thay ngữ nghĩa sau lock phải
version mới. Module/schema/producer/runtime tương ứng vẫn thuộc các task
triển khai tiếp theo, chưa có manifest cho phép API revision.

Protocol khóa sự kiện LONG ròng>0, partition C/B1/B2 và posterior plug-in,
lambda {2,4,8} chỉ chọn train, readiness độc lập hai block, task 20 phiên
neo 02/01/2018, centroid/rank không đọc nhãn, 3×2/600 ký tự và fallback.
Phân biệt Bayes số học, ICL trong context và Numeric heuristic; giữ schema,
model/options/risk OFF, engine cổ phiếu lẻ hiện hữu. Khóa matrix/nomination,
canonical shared-off/alias/duplicate, rotation/repeat, estimand tài khoản,
bootstrap/family CI và điểm dừng. Không sửa registry hoặc phương pháp W9.

**Power planning, không là chứng nhận power:** 10.000 draw/scenario,
PCG64/seed 20261021, L=4 chính/L=2/8 sensitivity, mask 41 cutoff/128 điểm,
32/mã nguyên audit v2. Giữ năm proxy đã đăng ký: C2/A/B−Original từ
Decision 2023 và Numeric A−C2 trên mỗi fold train. Development chỉ có bảy
ngày joint; train có 76/76 sau purge bốn cycle cuối 2021 đóng sang 2022.
Không dùng payoff 2025, không chọn proxy variance nhỏ hoặc đổi N theo số.

| Proxy | Ngày donor joint | Width CI95% dự kiến (đpt) | MDE80 (đpt) |
| --- | ---: | ---: | ---: |
| Decision 2023 C2−Original | 7 | 4,93 | 4,08 |
| Decision 2023 A_tp_pool−Original | 7 | 26,21 | 17,27 |
| Decision 2023 B_semantic−Original | 7 | 29,15 | 19,03 |
| Numeric train 2021 A−C2 | 76 | 14,00 | 10,39 |
| Numeric train 2022 A−C2 | 76 | 22,07 | 17,50 |

Toàn bộ **30 scenario** (năm proxy×ba L×hai mức CI) được giữ trong bundle.
CI98,75% tại L4 có width 5,67–37,38/MDE80 4,08–21,84 đpt; sensitivity
CI95% L2 có MDE 4,06–22,52, L8 có 3,19–18,93. Không chọn L8 vì hẹp hơn;
L8 vòng quanh chỉ bảy donor 2023 đặc biệt yếu. MDE là xấp xỉ location-shift
ở cấp tài khoản, không là gain kỳ vọng của R hoặc power của kiểm định mới.
Tỷ lệ interval dương tại δ=0 ở L4/CI95% dao động 0,21–7,45%: không dùng mô
hình xấp xỉ này chứng nhận calibration/Type I error. MC SE chỉ mô tả sai số
Monte Carlo, không gồm sai số donor/ngoại suy/provider. N=128 giữ nguyên;
audit hoàn tất không đồng nghĩa đủ power, kết quả xác nhận có thể inconclusive.

**Nguồn và tái lập:** report/plan development và diagnostics train khớp nguyên
byte ba entry tương ứng trong archive W9. SHA byte nguồn lần lượt:
`80f707e0f4ee62c384724085249f748e2e82cf6517ccf892ccb97b1603317314`,
`f9745d946d81cb008e0a747f8367fe0c85a5fbd989e7148bde997227d651831e`,
`c32993c726888f2fee3f9650f307db9afcb67145b4af40242bb49659bdbb23c9`.
Audit đầu vào 2025 giữ byte/hash đã ghi ở W10-01.

Bundle [power_audit_v1.zip](../../../outputs/bayesian_benchmark/bic_icl_v2/protocol_v1/power_audit_v1.zip)
có bảy entry gồm script phân tích/oracle, pins và toàn bộ kết quả, SHA byte
`4d87aa0c33a0729e05abfc67fb4196fe1c436cd3d58387c1db324fac8488c7e8`.
Đây là bằng chứng phân tích ignored, cần giữ cùng workspace với nguồn;
không là code ứng dụng/schema execution hoặc release. Từ root repo:

```powershell
$powerReplayDir = Join-Path $env:TEMP ('bic-icl-power-' + [guid]::NewGuid())
Expand-Archive -LiteralPath outputs/bayesian_benchmark/bic_icl_v2/protocol_v1/power_audit_v1.zip -DestinationPath $powerReplayDir
py -3.13 -X utf8 "$powerReplayDir/power_audit.py" . "$powerReplayDir/power_audit.json" --check
py -3.13 -X utf8 "$powerReplayDir/power_oracle.py" .
```

**QA W10-02 PASS:** replay từ bundle khớp toàn payload; oracle độc lập kiểm
30 scenario/576 tài khoản draw, nội suy quantile và power curve. Đối soát
240 valuation development, 16 tài khoản source với report và 651 nhãn train
qua hàm kinh tế chung. Sau purge còn 647 cycle train được xét metadata;
608 cycle trên 152 ngày joint làm donor, không điền return thiếu.
Hash/link/diff/source PASS, **6.664 file cũ nguyên byte**. Chỉ ba Markdown
được quản lý trong Git và bằng chứng phân tích riêng; không đổi code/test/
runtime/config/schema hoặc dữ liệu execution đầu vào. Theo AGENTS.md mục 1.2
không chạy compileall/unit/E2E/leakage cho task thuần đặc tả/phân tích này,
không ghi gate W10-01 như đã chạy lại. Không gọi API/LLM hoặc tạo payoff 2025.
Tiếp theo **W10-03** triển khai shared-off/duplicate/checkpoint/recovery.

## W10-03 — Shared Decision và phục hồi, 22/10/2026

**DONE; W10 3/8.** Module mới
[`core/bic_icl_decisions.py`](../../../core/bic_icl_decisions.py) cung cấp
`DecisionBlock`, `branch_order` và `shared_stage_scope`; giữ code/runtime
W9 nguyên byte. Đây là component cho runner W10-06, chưa có producer
memory/R_pool/R_task hoặc CLI/release chạy cohort thật.

| Biên | Hành vi đã triển khai |
| --- | --- |
| Request | Khóa toàn danh sách trước HTTP; tái dựng canonical body bằng serializer SDK thật, gồm messages/model/options/schema/tools; so prompt<6.500 và prefix≤600 |
| Shared-off | Original đầu block, response durable trước nhánh khác; prefix rỗng và toàn contract giống mới reuse; `decision_origin=shared_original`, source branch/hash, không tạo attempt/HTTP giả |
| Stats alias | Chỉ cặp R_pool/R_task stats-only cùng canonical request và cùng base evidence; giữ ID logic nhưng một source response. Full không alias vì tình cờ giống prompt |
| Duplicate/repeat | Duplicate luôn invocation/UUID riêng; mỗi repeat có Original mới. Receipt pin byte state primary đã verify, cùng matrix/request/prefix/base/shared; chỉ xoay thứ tự theo protocol, không lấy response primary làm repeat |
| Upstream | Một journal/point dùng chung primary/repeat; callback vào graph/journal hiện hữu, deep-copy state/output. Node complete được dùng lại, mất journal/marker sau bắt đầu phải dừng |
| Durable | Identity/state/ready riêng; intent atomic trước SDK, raw/normalized trước evaluation. Alias chỉ trỏ nguồn complete cùng point/repeat; mất state sau lock không được tạo lại bằng `create=True` |
| Recovery | Dùng ResilientTransport/pacer/retry wrapper hiện hữu; cùng UUID khi retry/format repair/resume. Cache response durable dùng lại sau restart, kiểm hash/header/body trước SDK. Quota ngày giữ unknown, không điền CASH |
| Verifier | Tái kiểm toàn block và ledger disk trước HTTP tiếp theo, kể cả source alias; tự băm lại checkpoint không thay body/response thực. Thay cutoff, source, code, client options hoặc primary receipt đều bị chặn |

`DecisionBlock.run` nhận shared bundle JSON đã seal, danh sách request
đã render (`branch_id`, `prompt`, `prefix`, `base_evidence_sha256`) theo
thứ tự đã khóa, cùng callback `verify_sources`. Renderer/evidence semantic,
manifest/code/runtime toàn cohort và release sẽ do W10-04–07/W11 cấp;
component không coi hash tự khai là đủ bằng chứng retrieval/PIT. Missing/
unknown không là quyết định CASH. Fixture chỉ dùng HTTP mock ngoài workspace;
run thật chỉ nhận thư mục con namespace `bic_icl_v2`, không ghi vào W9.

Checkpoint nằm tại `decision_blocks/<repeat>/<point>/identity.json`,
`state.json`, `ready.json`; journal tại `shared_stages/<point>/journal.json`.
`verify_only=True` tái lập/so trạng thái, không gọi Decision mới. Source
reference và HTTP audit dùng để phân biệt slot logic, Decision vật lý và
HTTP retry; alias không là quan sát độc lập. Hai nhánh sau alias vẫn nhận
bản sao output riêng, không cùng một đối tượng state có thể bị sửa chéo.

**Kiểm thử trọng tâm:**
[`test_bic_icl_decisions.py`](../../../tests/test_bic_icl_decisions.py) và
[`test_bic_icl_decisions_leakage.py`](../../../tests/test_bic_icl_decisions_leakage.py),
fixture SDK/HTTP mock tại [`bic_icl_fixture.py`](../../../tests/bic_icl_fixture.py).
**32 ca PASS**: prior-off giống/khác request; stats alias/base; duplicate;
khác point/lượt; repeat sai primary; ledger append; 429/format repair/quota;
crash trước HTTP, sau durable response và trước persist alias; init orphan;
khóa OS; cache hỏng sau restart; rehash state/identity/marker/raw; mất ledger/
checkpoint; query outcome/future feature; horizon và JSON native.

```powershell
py -3.13 -X utf8 -m unittest discover -s tests -p "test_bic_icl_decisions*.py" -v
```

Do thay đổi paired protocol/retry/checkpoint P0, áp dụng đủ bốn gate
AGENTS.md mục 1.2. Hai suite chạy trên bốn process, phân công động theo
nguyên module và giữ thứ tự trong module; đối chiếu multiset test ID với
`unittest discover`, không bỏ bội số/test hoặc skip. Identity UTF-8/LF của
code/test/phương pháp giữ nguyên trong lượt gate và sau checkout; checksum
nguồn/bằng chứng cũ vẫn đối chiếu theo byte gốc.

**Nghiệm thu PASS trên Python 3.13.5:** compileall toàn codebase, **978 unit
test/204 leakage**, E2E xác định; không lỗi, skip hoặc expected failure.
Đủ 125 module unit/35 module leakage, hai multiset ID khớp discovery. Có
**32 test mới** (17 ca wrapper/recovery, 15 ca integrity), toàn bộ SDK qua
HTTP mock; không dùng gate W10-01 thay lượt này. Identity LF **242 file**
giữ nguyên suốt gate; **6.666 file cũ nguyên byte**, gồm ledger, archive W9,
input audit v2 và method protocol v1. Diff/liên kết/hash/source PASS.

Log, inventory, runtime và công cụ chạy gate được đóng trong
[`validation_gates/shared_decisions_v1.zip`](validation_gates/shared_decisions_v1.zip),
184 entry/554.629 byte; SHA-256 byte
`0c5d09604443fcf3d5f2a12115f7df38f4bcfcaa18c6383015b8de50b43c8a8b`.
ZIP lưu log/inventory của bản code đã nghiệm thu. W10-07 vẫn phải
nghiệm thu lại toàn revision sau
triển khai memory/posterior/task/runner; component gate không là release.
Không gọi HTTP/LLM thật, tạo nhãn 2025 hoặc thay mặc định triển khai.
Tiếp theo **W10-04**: adapter memory đã lưu, R_pool và diagnostics train.

## W10-04 — Memory revision, R_pool và lambda train, 22/10/2026

**DONE; W10 4/8.** Bốn module/công cụ mới:
[`bic_icl_memory.py`](../../../core/bic_icl_memory.py),
[`bic_icl_statistics.py`](../../../core/bic_icl_statistics.py),
[`bic_icl_diagnostics.py`](../../../core/bic_icl_diagnostics.py),
[`prepare_bic_icl_memory.py`](../../../scripts/prepare_bic_icl_memory.py).
Đây là producer offline và component posterior/selector cho W10-05–06;
chưa có renderer R_task hoặc CLI cohort gọi Decision revision.

**Memory:** đối chiếu byte với archive W9 đã khóa, đọc đúng 60 point 2023 và
64 point 2024; kiểm plan/model/options, source PIT, Full seal và bốn stage
journal complete. Tín hiệu lấy từ upstream; nhãn do hàm kinh tế chung sinh
sau seal. Không dùng action/confidence/justification Decision làm feature.
Nhập **124/124**, loại 0, dedup 0; union có **976 episode**, giữ nguyên bank
852. Metadata từng bản ghi giữ source/shared/journal hash và signal identity;
thiếu nguồn là lỗi integrity, không chuyển thành prior-off.

Index revision riêng kế thừa nguyên tham số ba fold scaler cũ. Fold
`confirmation_2025` dùng đúng scaler OOS kết thúc 2022, không gọi fit mới,
không đổi validator miền 2023/2024 legacy. **103/124** feature nhập thêm
AVAILABLE; **21** cửa sổ có quyền giữ UNAVAILABLE, không điền vector để đủ
demonstrations. Counts statistics vẫn giữ các cycle này sau lọc PIT.
Không nhập cycle 2025; `exit_date < query` áp trước partition/rank, cả query
tự nó và record năm sau đều bị loại. A/R dùng cùng bank/index/selector;
Numeric sẽ nhận cùng posterior khi tích hợp runner.

**R_pool:** phân hoạch rời C/B1/B2, cùng mã; C khớp T/P, B1 phần còn lại cùng
regime, B2 khác regime. Giữ counts, IDs, tuổi, cụm tháng, prior weight và CrI
plug-in; n=0 ghi rõ thiếu quan sát, không gọi raw n là effective sample size.
Stats gate dùng nC≥5, n1+n2≥20 và width≤0,75 trước làm tròn. Examples gate
riêng, population cùng regime≥20, feature/scaler sẵn có và có ví dụ hợp lệ;
giữ selector K≤3, tuổi≤730, similarity≥0,625, gap≥5 phiên/không overlap.
Full/stats/examples là các view cùng base, không chạy lại retrieval theo view.
Verifier dựng lại evidence, không chỉ nhận artifact đã tự băm lại.

**Lambda train khóa bằng loss:** replay **651 query**, hai fold đã purge và
**166 cutoff HMM/scaler/calibration prefix** của các query; đối chiếu A với
diagnostics cũ đã đóng băng. Cả ba lambda chấm trên cùng **598 query** có
posterior hữu hạn với A, không lọc riêng theo readiness. 53 query thiếu A
không được điền 0,5 để scoring. R có thể tính posterior số học khi nC=0,
ghi `NO_CONDITIONAL_HISTORY` và stats off; đây không là conditional evidence
đã quan sát. Loss clip [1e−6,1−1e−6], tie 1e−12, Brier rồi lambda nhỏ hơn.

| Phương pháp | Log loss chung | Brier chung | Stats ready / 651 |
| --- | ---: | ---: | ---: |
| A reference | 0,69645620 | 0,25078170 | 355 |
| R, lambda=2 | 0,70995949 | 0,25573325 | 399 |
| R, lambda=4 | 0,69371112 | 0,24954020 | 399 |
| **R, lambda=8 — chọn** | **0,68332577** | **0,24496989** | **399** |

R2 bất lợi so A; VCB/train2021 với lambda=8 cũng bất lợi về log loss
(0,63908462 so 0,63354190), không giấu subgroup. Report giữ đủ ba lambda,
từng fold/mã/regime, năm reliability bin [0;.2;.4;.6;.8;1], raw/ready/missing,
LONG lãi/lỗ/zero và leave-one-query-quarter-out để mô tả độ nhạy theo cụm.
Không chọn lại lambda theo sensitivity hoặc return 2023/2024/2025. Chọn bằng
toàn train có selection bias, không là lựa chọn online đã có tại query 2021
hoặc chứng nhận calibration OOS/LLM. PIT hồi cứu không chứng nhận vintage
provider/kiến thức LLM; chưa có kết quả kinh tế của Decision revision.

**Tái lập offline từ root:**

```powershell
py -3.13 -X utf8 scripts/prepare_bic_icl_memory.py --kind memory --destination outputs/bayesian_benchmark/bic_icl_v2/memory_v1
py -3.13 -X utf8 scripts/prepare_bic_icl_memory.py --kind memory --destination outputs/bayesian_benchmark/bic_icl_v2/memory_v1 --verify
py -3.13 -X utf8 scripts/prepare_bic_icl_memory.py --kind train --destination outputs/bayesian_benchmark/bic_icl_v2/train_v1
py -3.13 -X utf8 scripts/prepare_bic_icl_memory.py --kind train --destination outputs/bayesian_benchmark/bic_icl_v2/train_v1 --verify
```

Hai thư mục có receipt code/runtime/output hash riêng; build ghi một lần,
verify dùng lại producer đầy đủ và không đổi byte/timestamp output. Cả bốn
lệnh build/verify memory/train thật đều exit 0, không đổi artifact khi verify.
**38 test mới PASS** trong bốn module `test_bic_icl_memory`,
`test_bic_icl_memory_leakage`, `test_bic_icl_statistics`, `test_bic_icl_preparation`.
Oracle độc lập PASS nhãn của 124 cycle, 103 vector mới, scaler cũ và
**1.953 posterior**, Beta CDF sai số tối đa 3,109e−15; loss/support khớp report.
Không API/LLM thật, payoff 2025 hoặc thay economic/risk/default runtime.

Do thay đổi đường dữ liệu/retrieval/PIT P0, áp dụng đủ bốn gate AGENTS.md 1.2
trên Python 3.13.5: **compileall toàn codebase, 1.016 unit test, E2E xác định
và 215 leakage PASS**, không lỗi, skip hoặc expected failure. Hai suite chia
nguyên module vào bốn process, giữ thứ tự trong module; đủ **129 module unit,
36 module leakage**, đối chiếu multiset test ID khớp discovery, không bỏ bội số.
Identity LF của **251 file** giữ nguyên suốt gate; **6.671 tệp cũ nguyên byte**,
gồm bank 852, W9, protocol/power và input audit v2. Diff/hash/liên kết PASS.
W10-07 vẫn phải nghiệm thu lại toàn revision sau task/renderer/runner;
gate component này chưa là release. Tiếp theo **W10-05** R_task/renderer.

Artifact mới và log/inventory/oracle/runtime/công cụ QA được đóng nguyên byte
trong [`validation_gates/memory_pool_v1.zip`](validation_gates/memory_pool_v1.zip),
**204 entry / 1.929.694 byte**, SHA-256 byte
`0a92be91d26364762cd8b324676254500a5ba6f1e9067f085537360b87a00dc6`.
Manifest trong ZIP kiểm từng entry. Hai receipt nguồn cho bước sau:
`memory_v1/receipt.json` SHA byte
`20fee102b8fb797f6eb3eb376fa25b5a892e31bf38dac7e690c39481b5cfbd19`;
`train_v1/receipt.json` SHA byte
`90c15847b3f052128d72e0308c5916ee095f4da0c91fff776015ca40249feede`.
Các đường receipt ở dưới `outputs/bayesian_benchmark/bic_icl_v2/`; ZIP giữ
cả memory/index/diagnostics và receipt ở đúng đường tương đối đó.

## W10-05 — Task selector và context, 22/10/2026

**DONE; W10 5/8.** Triển khai
[`bic_icl_tasks.py`](../../../core/bic_icl_tasks.py),
[`bic_icl_prompt.py`](../../../core/bic_icl_prompt.py) và preflight offline
[`prepare_bic_icl_context.py`](../../../scripts/prepare_bic_icl_context.py).
R_task đạt nghiệm thu grouping/renderer; coverage đề cử chưa đạt trên cache
upstream hiện có. Chưa chọn candidate hoặc phát hành xác nhận.

**Selector:** task `(symbol, regime, floor(session_index/20))`, index0
VNINDEX **02/01/2018**, không neo lại theo query. Lọc exit<query, cùng mã/
regime, tuổi≤730, similarity≥0,625 và feature/scaler AVAILABLE trước grouping.
Centroid dùng toàn bộ vector đủ điều kiện trong nhóm, không đọc nhãn.
Xếp nhóm theo RMS centroid–query, ngày mới nhất giảm, rồi ID tăng.
Trong nhóm, lấy cặp cố định theo rank cycle legacy, gap≥5 phiên và không
overlap entry–exit; khi cặp xung đột với demonstrations đã nhận, loại cả
nhóm và tiếp tục nhóm kế. Tối đa **3 task × 2 cycle**, không thay cặp theo
nhãn hoặc cân bằng thắng/thua. Sidecar giữ toàn bộ qualification, centroid,
rank, pair, IDs và reason loại; API grouping thuần từ chối outcome/label.

**Context:** posterior/counts/lambda=8 giữ nguyên R_pool W10-04, không cộng
demonstrations lần nữa. Stats/examples gate độc lập; examples cần population
cùng regime≥20 và ít nhất một cặp hợp lệ. Full/stats/examples là view của
cùng evidence; hai stats-only giữ cùng prefix/prompt/base hash để wrapper
W10-03 alias, prior-off giữ đúng canonical Original. Renderer giữ boundary
G1/G2/G3, x=T/P và y=W/L theo dấu return gốc, return ròng % hai số thập phân.
Zero là L/+0,00%; return dương/âm rất nhỏ vẫn giữ W/L trước làm tròn.
Không đổi schema/model/template/distill/cap legacy. BRPP>600 chặn cả ba
nhánh của candidate trước API; không cắt nhãn/nhóm để qua trần.

[`context_budget_fixture_v1.json`](context_budget_fixture_v1.json) là dữ
liệu tổng hợp kiểm renderer, không là quan sát thị trường. Fixture đủ 3×2,
return lớn/nhỏ/zero và report dài: **VI 300 ký tự BRPP / 6.147 prompt**,
**EN 297 / 6.162**, đều ≤600 và <6.500. Preflight nguồn thật khôi phục đúng
**60 upstream 2023**, không sinh lại upstream/Decision: tối đa **256 ký tự
BRPP / 4.432 prompt**, kiểm 720 prompt của hai method × ba view × hai
template ngôn ngữ. EN dùng cùng báo cáo nguồn VI qua template EN để kiểm
ngân sách, không là cohort tiếng Anh hoặc kết quả Decision tiếng Anh.

**Coverage R_task trên cache, sau gate hiển thị:**

| Mã | Query | Có prior | Examples ready | Có ≥2 task |
| --- | ---: | ---: | ---: | ---: |
| FPT | 12 | 9 | 3 | 0 |
| MWG | 16 | 14 | 6 | 1 |
| VCB | 16 | 10 | 3 | 1 |
| VNM | 16 | 15 | 9 | 1 |
| Tổng | 60 | 48 | 21 | 3 |

Trạng thái **INSUFFICIENT_CACHED_UPSTREAM_COVERAGE**: rule đề cử cần ≥6 điểm
có ≥2 task và ≥1/mã; hiện chỉ 3 và FPT=0. Raw selection được ghi riêng,
không đếm nhóm bị gate ẩn. Đây là giới hạn metadata, chưa là đánh giá return
hoặc nomination cuối; kiểm lại với upstream lock W11, không nới lọc, neo
lại lịch, tune prompt theo return hay gọi thêm LLM để tạo bank.

**Tái lập offline từ root**, cần snapshot memory/train W10-04 cùng workspace:

```powershell
py -3.13 -X utf8 scripts/prepare_bic_icl_context.py --destination outputs/bayesian_benchmark/bic_icl_v2/context_v1
py -3.13 -X utf8 scripts/prepare_bic_icl_context.py --destination outputs/bayesian_benchmark/bic_icl_v2/context_v1 --verify
```

Loader đối chiếu nguyên byte năm artifact với ZIP W10-04 đã pin độc lập,
kiểm source/code/runtime/receipt; lambda không được chọn lại. Build ghi một
lần, verify dựng lại semantic rồi so toàn evidence/prefix/prompt, không
chấp nhận chỉ tự băm lại artifact. Hai lệnh thật exit 0, verify giữ nguyên
byte/timestamp. Digest report
`b94fa9a7c48e41f3bdd4653f3699ec06d1f5ccb1a0fd36e257ef83c87e4ad3fe`;
receipt SHA-256 byte
`50e579d7cae554ad1af0717a06f077b7029b272ae00d81aa55ad781c6387f0eb`.
Artifact ở namespace ignored; ZIP nghiệm thu giữ cả preflight/receipt để
tái lập, không ghi đè memory/train, W9 hoặc phương pháp đã khóa.

**QA trên Python 3.13.5:** 40 test mới; oracle độc lập kiểm qualification,
rank, **150 centroid, 26 cặp được chọn và 720 prompt** trên nguồn thật PASS.
HTTP mock kiểm serializer/schema SDK, stats alias và shared-off không tạo
attempt giả. Vì thay đổi retrieval/PIT/prompt P0, chạy đủ bốn gate:
**compileall toàn codebase, 1.056 unit, E2E xác định và 227 leakage PASS**;
không lỗi, skip hoặc expected failure. Hai suite chia nguyên module vào bốn
process, giữ thứ tự trong module; đủ 134 module unit/37 module leakage,
multiset ID khớp discovery, giữ cả bội số có sẵn. Identity UTF-8/LF của
**261 file** không đổi; **6.686 tệp cũ nguyên byte**. Diff/hash/liên kết PASS.

Bằng chứng cuối tại
[`validation_gates/task_context_v1.zip`](validation_gates/task_context_v1.zip),
**206 entry / 2.076.413 byte**, SHA-256 byte
`08a8c943ddba8919eacb46fdb13426ffabe8c7d5d1ebd178ca0cfe2551dd8fd3`.
Manifest kiểm hash từng entry, gồm gate/inventory/runtime, CLI, oracle,
fixture tổng hợp và hai artifact context mới. Không API/LLM thật hoặc
payoff/action 2025; `confirmation_allowed=false`. W10-07 phải nghiệm thu
lại toàn revision sau tích hợp runner; component gate này chưa là release.
Tiếp theo **W10-06**: producer/loader/verifier/CLI cohort và fixture kinh tế.
