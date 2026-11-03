# Audit bằng chứng legacy và thống kê phụ thuộc

Phạm vi D1-16, ngày 03/11/2026; dependency S0 của `plan.md`. Đây là audit
legacy, không phải thực nghiệm LLM mới hoặc xác nhận snapshot submission.
**D1-16 hoàn tất đối soát; R6 chưa được đóng chỉ bằng audit này.** Attribution
component/QuantAgent, license và novelty thuộc D2-13, không được suy từ tên branch.

## Bằng chứng và cách tái lập

Release mới: [manifest](../outputs/revision/legacy_lineage_v1/manifest.json),
[tổng hợp](../outputs/revision/legacy_lineage_v1/report.json),
[66 streams với từng row](../outputs/revision/legacy_lineage_v1/streams.json),
[573 comparisons](../outputs/revision/legacy_lineage_v1/comparisons.json),
[lịch sử file](../outputs/revision/legacy_lineage_v1/git_history.json).
SHA-256 khóa nguyên byte 47 artifacts hiện có trong ba cây
`outputs/backtest_result/`, `outputs/robustness/`, `outputs/ablation/`, gồm
JSON, CSV và PNG; không ghi lại artifacts đó. Trong đó 30 JSON có test points:
9 benchmark, 18 robustness và 3 ablation. Tổng 66 streams ×20 rows =1.320
records biến thể; đây không phải 1.320 quan sát thị trường độc lập.

```powershell
py -3.13 -X utf8 scripts/audit_revision_lineage.py --check
```

Lệnh kiểm tra hash nguồn/outputs và tái tính toàn bộ audit, không gọi API.
Tạo release khác bằng `--output outputs/revision/<run_id_moi>`; mặc định từ
chối ghi đè thư mục đã có. `null` biểu thị thiếu trường, không tính hai giá trị
thiếu là bằng chứng trùng. Schema và từng row giữ prediction, correct,
confidence, risk/reward, elapsed time, error/source/fallback, label, giá/ngày
entry/exit và các trường equity/tài khoản đã lưu. Ablation không lưu equity
từng row; chỉ giữ summary gốc riêng, không tự dựng equity để bổ sung lineage.

Ghép theo **symbol và cutoff thật**. So toàn bộ 573 cặp streams cùng mã,
kể cả trong một artifact; báo cả support chung và ngày chỉ có ở mỗi bên.
Chỉ gọi trùng toàn chuỗi nếu hai bên có đủ cùng toàn bộ 20 cutoff và cùng
prediction. Không ghép theo test index, accuracy làm tròn hoặc tên default.
Các trường cùng hiện diện được đếm riêng số bằng nhau; khác biệt và thiếu
trường vẫn giữ trong `streams.json` để kiểm lại từng row.

## Kết quả duplication

Có **20 cặp** trùng toàn chuỗi prediction, không phải 20 nguồn inference độc lập:

| Nhóm | Cặp | Đối soát |
|---|---:|---|
| Control trong sweep norm/weights | 12 | Mỗi mã FPT/VNM có ba scenario mỗi sweep; ba cặp/sweep/mã. Prediction, confidence, risk/reward, elapsed time và equity đều trùng 20/20. Phù hợp thiết kế shared control; thiếu parent request/artifact ID nên chưa xác thực thực thi. |
| FPT Alpha-only với control weights | 3 | Cùng chuỗi với default/equal_weight/ic_heavy, vốn dùng chung control. Mỗi cặp prediction/correct trùng 20/20; confidence 12/20, risk/reward 8/20, elapsed time 1/20. |
| FPT Sentiment-only với control norm | 3 | Cùng chuỗi với minmax/rank/zscore_tanh. Mỗi cặp prediction/correct trùng 20/20; confidence 15/20, risk/reward 7/20, elapsed time 0/20. |
| FPT Full w45 với Full weights/ic_heavy | 1 | Prediction/correct 20/20; confidence 16/20, risk/reward 7/20, elapsed time 0/20. |
| VNM Full norm/zscore_tanh với Full weights/ic_heavy | 1 | Prediction/correct 20/20; confidence 14/20, risk/reward 4/20, elapsed time 0/20. |

Tám cặp ngoài shared-control group có cùng label và entry/exit đã lưu trên
20 cutoff. Với hai cặp Full, equity cũng trùng 20/20; equity dưới cùng quyết
định/giá là đại lượng dẫn xuất, không chứng minh cùng request. Tất cả tám cặp
có `llm_structured` và error/fallback rỗng, nhưng các chuỗi tự khai này không
thay raw response. Sáu cặp FPT treatment/control quy về hai control gốc,
không được đếm thành sáu phát hiện độc lập. Không thấy cặp trùng toàn chuỗi
nào khác trong 553 cặp còn lại, kể cả VCB và sáu mã benchmark còn lại.
Không dùng phát biểu đó để chứng nhận những nhánh không trùng đã chạy đúng.

**Kết luận:** nguyên nhân `unknown`. Không có căn cứ chọn giữa reuse, sai
gán branch, conversion ngoài Git hoặc inference độc lập tình cờ cùng chuỗi.
Confidence/risk/reward/thời gian khác nhau bác bỏ nhận định rằng toàn bộ
decision record giống hệt; chúng cũng không chứng minh hai request độc lập.

## Lịch sử mã và hợp đồng save/load

Release giữ sáu source blobs nguyên byte dưới `historical_sources/`: runner
robustness, engine và graph setup tại `cc7153ea`; runner ablation, engine và
graph setup tại `c9371886`. Đây là **phiên bản trong lịch sử repository**,
không phải chứng nhận đúng source đã chạy vào timestamp ghi trong JSON.
`git_history.json` lưu full commit IDs và SHA của blob sớm nhất còn giữ cho
từng artifact. Cả 31 JSON hiện tại có nội dung JSON bằng bản Git sớm nhất;
byte có thể khác line ending, được báo riêng, không sửa để làm hash khớp.
38 JSON/CSV khớp blob Git khi chỉ so sánh sau bỏ khác biệt CRLF/LF; đây là
phép so trong bộ nhớ, không thay hash byte gốc. Manifest khóa byte workspace
hiện có, không phải gói tái lập fresh-checkout của R9: checkout trả về blob LF
khác SHA đã khóa sẽ bị verifier từ chối, cần cung cấp đúng byte nguồn trước
khi kiểm lại. Auditor không âm thầm chấp nhận source khác hash chỉ vì JSON bằng nhau.
Không có thay đổi nội dung JSON trong lịch sử còn giữ giải thích được hai
trùng lặp FPT ban đầu. Lịch sử Git không loại trừ thao tác chưa từng commit.

- `core/run_robustness.py::run_shared_alpha_sweep`: deepcopy base config và
  upstream, gọi baseline một lần/cutoff, sau đó gọi Full từng scenario và ghi
  cùng control vào các checkpoint norm/weights. Hành vi này giải thích vì sao
  control được kỳ vọng trùng giữa scenario, nhưng không cung cấp parent ID.
  Window sweep là các lần chạy riêng, không mặc định cùng upstream/control.
- `_load_checkpoint_points`: kiểm symbol, khoảng ngày, prefix/test ID và
  prediction/error; khi resume sweep còn kiểm cutoff/label/prediction control
  chung. Không khóa data-content hash, full config/scenario, prompt, served
  model revision, code/schema hoặc repeat. Tên file có scenario không thay
  cho kiểm tra nội dung. Khoảng ngày bằng nhau không chứng minh snapshot bằng nhau.
- `scripts/run_ablation_matrix.py::load_checkpoint`: kiểm symbol, n_tests,
  window_size, step và hai mốc dữ liệu; prefix cần đủ bốn variants hợp lệ.
  Cũng thiếu full content/prompt/model/code/repeat identity. `_checkpoint_payload`
  ghi seed/protocol/variants và updated_at, không có raw prompt/response hay
  parent request. Seed 42 được lưu không chứng minh hosted inference có seed.
- `core/backtest_engine.py::_run_ablation_variants`: mỗi variant deepcopy
  shared upstream, gắn `ABLATION_CONFIGS[variant]`, rồi invoke graph tương ứng;
  graph setup tách alpha/sentiment theo flags. Runner lấy `states[variant]`,
  parse và lưu dưới đúng tên variant; source đã lưu không có phép đọc control
  từ robustness để gán thành treatment ablation. Summary flags là khai báo,
  chưa xác thực flags/prompt thực sự của từng historical call.
- Save JSON ghi parsed points/summary; checkpoint hoàn tất có thể được resume
  mà không sinh request mới. Không có call-level timestamp/hash trong các rows;
  started_at/ended_at/updated_at là metadata cấp artifact. Elapsed time không
  phải timestamp request. Không tìm thấy raw request/response, rendered prompt
  hoặc log liên kết call trong ba cây legacy đã khóa. Các script/nguồn trong
  Git được khảo sát không đủ truy ngược execution commit hoặc conversion ngoài Git.

Không sửa runner legacy/runtime của các study đã khóa trong D1-16. Không
retrofit hashes hoặc parent IDs vào checkpoint cũ. Đường study mới đã có
archive/rendered prompt, context, variant/repeat/realization và parent identity;
tham chiếu evidence đã chốt tại
[R3](../outputs/revision/r3_repeats_v1/manifest.json) và
[R4 corrected](../outputs/revision/r4_final_v1/manifest.json), không gán lineage
của study mới cho study cũ và không ghi là đã chạy lại verifier của chúng.

## Quyết định sử dụng và nghiệm thu phạm vi

Bảng four-way legacy trong `paper/sections/06_backtest_results.tex`, đoạn
`tab:disentangled_ablation`, đã ghi rõ **unverified / traceability only / not
confirmatory attribution evidence**. Giữ nguyên bảng và PDF release R4 đã khóa;
không dùng số legacy để khẳng định alpha/sentiment contribution. Panel corrected
R4 với 270 decisions mới là bằng chứng riêng, không phải phục hồi request cũ.
R6 còn cần phản hồi đầy đủ và đối chiếu vị trí bản thảo/PDF trong task chốt
comment; D1-16 chỉ đóng yêu cầu audit và chuyển giao các unknown rõ ràng.
D2-13 có thể dùng audit này làm dependency, nhưng upstream QuantAgent commit,
reuse/modified/new và license vẫn phải đối soát riêng.

Kiểm tra mới: 9 unit tests của auditor (join/support, missing, treatment/control,
nhãn/ngày trùng, four-way fields, hash tamper); chỉ biên dịch auditor và test mới.
Kiểm actual-data hashes và tái tính toàn bộ release ở process mới. Không chạy
toàn unit/E2E/leakage suite vì không đổi engine, prompt, PIT/retrieval, metrics,
runtime, inputs hoặc predictions. Các gate cũ không được báo là chạy lại.
Sáu source blobs lịch sử giữ nguyên trailing whitespace và byte Git gốc;
`.gitattributes` miễn riêng whitespace check cho các bản lưu này, pin LF cho
hai Python của auditor để checkout Windows không làm sai source hash.

## Thống kê phụ thuộc — D2-05

Ngày 03/11/2026, dependency D2-03 đã hoàn tất. Đặc tả
[r5_statistics_policy.json](r5_statistics_policy.json) được khóa trước chạy
phân tích bổ sung; việc thêm phương pháp diễn ra **sau inference**, không gọi
là preregistration hoặc confirmatory. Release riêng tại
[dependent_statistics_v1](../outputs/revision/dependent_statistics_v1/manifest.json).
Không gọi LLM, đổi prediction/label, fit classifier hoặc sửa helper thống kê
legacy. Annualisation engine vẫn là D2-06; R5 chưa đóng bởi D2-05.

### Estimands và support

- Legacy: 180 paired points, chín mã ×20, 53 cutoff dates khác nhau; **không
  có cutoff chung cho cả chín mã**. Pooled accuracy và equal-symbol macro
  accuracy trùng vì cùng 20 points/mã; không có 180 independent replications.
  Bảng mới ghi hai hướng discordance và exact two-sided conditional binomial
  diagnostic, với giả định independent discordant pairs chưa được xác thực.
  Full-only/Base-only pooled =32/7; pooled exact p=0,0000703 chỉ là diagnostic
  với independence giả định, không phải bằng chứng general significance.
- Study mới: chín classifiers trên cùng 102 units. Giữ pooled accuracy/BA
  theo unit, không trộn equal-symbol macro. Ba cohort báo riêng:
  all-102 (12 dates/sáu blocks), common-eight 96 (12/sáu) và recent-nine 54
  (sáu/ba). Chúng chồng lấn, không cộng support thành mẫu mới.
- HAC cross-section dùng correctness difference AS−B, mean theo ngày với
  trọng số mỗi mã cố định 1/8 hoặc 1/9 trong hai cohort chữ nhật. Không HAC
  chuỗi flatten 180 rows legacy, không gọi 102-unit cohort có universe thay
  đổi là fixed-nine-symbol date series. BA giữ là estimand primary cho
  bootstrap; HAC accuracy chỉ so với accuracy, không diễn giải p-value
  accuracy thành kiểm định BA hoặc return.

### Newey–West và undefined

Tái dùng nguyên `newey_west_mean_test`: Bartlett kernel, autocovariance mẫu
số n, SE=sqrt(LRV/n), tham chiếu t(n−1), không small-sample correction. Chín
legacy p-value tái lập đúng với lag tự động 2, nay xuất cả statistic/SE/lag.
Ví dụ MWG p=0,04927 nhưng exact McNemar p=0,125; không chọn kết quả thuận lợi,
không gọi một p dưới 0,05 giữa nhiều phép thử là chứng minh hiệu quả.

Wrapper mới từ chối nonfinite input thay vì bỏ ngày; n<2 hoặc SE gần zero
cho statistic/p/CI `null` (`NA` trong bảng), không kế thừa p=1 của helper để
diễn giải như xác nhận null. Không đổi schema/hành vi helper cho caller cũ.

Cross-section common-eight: accuracy gap +5,208 pp, SE 3,296–3,595 pp, p
0,142–0,175 trên lags 0/1/2; recent-nine: +3,704 pp, SE 2,982–3,381 pp, p
0,269–0,323. Chỉ có 12 hoặc sáu dates. Lag là **selected-date index** có
calendar gaps không đều, không phải consecutive daily/trading-session lag.
t reference chưa được hiệu chuẩn cho sample này; không gán significance.

### Block sensitivity và null simulations

Giữ nguyên intervals whole-block R1/R2 và joint block×paired-execution
intervals R3/R4. Bổ sung circular study-block bootstrap, 10.000 draws, seed
20261103, lengths 1/2/3. Mỗi draw giữ đồng bộ hai cutoff trong block, mọi mã,
eligibility mask và cả chín classifiers. Length đo bằng **study block** theo
thứ tự thời gian đã đăng ký; wrap và dependence qua những block cách xa nhau
là giả định sensitivity, không khẳng định stationarity. Xuất đủ tám contrasts
AS−control ×hai metrics ×ba lengths ×ba cohorts =144 rows, không chọn length
hoặc cohort theo outcome.

All-102 AS−B BA gap +0,545 pp, CBB intervals theo lengths 1/2/3 lần lượt
[−5,908;+7,866], [−4,871;+7,500], [−2,564;+3,728] pp; cả ba chứa zero. Đây
không thay interval primary R1 [−5,908;+8,000] pp. Recent-nine length 3 lấy
nguyên cả ba blocks nên interval bằng point estimate; artifact gắn
`degenerate_full_cohort`, không dùng khoảng zero-width đó làm bằng chứng precision.
Mọi draw mất class được báo riêng n_defined/n_undefined, không điền zero.

Null DGP đã khóa gồm ba scenarios (AR phi/common variance share =0/0,
0,6/0,7 và 0,9/0,9); mỗi scenario 1.000 panels độc lập, geometry 12 selected
dates/chín mã/sáu blocks, mask BHN thiếu sáu dates đầu. Hai arms exchangeable,
Gaussian stationary AR với shared market, arm-specific common và idiosyncratic
factors, truth riêng có marginal 30% UP. Không fit DGP lên outcome thật.
Mỗi panel/length có 1.000 draws, cùng thuật toán pooled BA/accuracy và cùng
mask/variant pairing như sensitivity thật.

Ở length 1, BA zero-coverage conditional trên defined panels là **85,00%**
(Wilson MC 95% [82,65%;87,08%]) khi độc lập; **63,85%** (993/1.000 panels
có BA defined) khi phụ thuộc vừa; **41,34%** (803/1.000 defined) khi phụ thuộc
mạnh. Xuất đầy đủ 18 scenario/length/metric rows, mọi class-loss draw và MC
intervals. Các Wilson intervals condition trên bootstrap-weight bank cố định;
chúng không cộng thêm uncertainty của finite bootstrap Monte Carlo. Coverage
thấp ngay dưới null là bằng chứng giới hạn của các khoảng percentile sample
nhỏ, **không phải chứng nhận coverage 95% của dữ liệu thật**, không hiệu chỉnh
hoặc chọn khoảng thật sau khi nhìn simulation. Không suy coverage của repeat
panels R3/R4 từ DGP không có repeat layer này.

### Bàn giao và kiểm tra

Release có 13 outputs: policy/report, legacy discordance/HAC, date scores,
144 block sensitivity rows (JSON/CSV), 18 null rows (JSON/CSV) và bốn bảng TeX
`legacy_discordance`, `block_sensitivity`, `panel_hac`, `null_coverage`.
Các bảng dùng số liệu từ cùng source và NA đúng hợp đồng; đã build standalone
bốn trang tại đúng bề ngang A4/margins bản thảo, render và kiểm trực quan đủ
bốn bảng, không tràn/cắt/overlap. Không chèn bảng hoặc build lại PDF R4 đã khóa;
phần tích hợp bản thảo/response cuối thuộc task tiếp theo.

```powershell
py -3.13 -X utf8 -m unittest discover -s tests -p test_revision_dependent_statistics.py -v
py -3.13 -X utf8 scripts/analyze_revision_statistics.py --check
```

11 tests mới PASS: oracle Bartlett/discordance, degeneracy/NA, mask/pairing,
class loss, symbol-replication invariance, shared draws, null arm-swap và
probability contract. Chỉ compile ba Python mới. Tái lập toàn bộ outputs ở
process mới với seed/hash/runtime đã khóa; source hashes bảo toàn inputs và
helpers cũ. Không chạy unit toàn hệ thống, E2E hoặc leakage vì không đổi
engine/runtime dependency, PIT/retrieval/prompt, ledger hoặc contracts cũ.
Thông tin runtime Python/NumPy/SciPy được lưu và kiểm lại, không gọi API.

## Annualisation và risk contract — D2-06

Ngày 03/11/2026; dependency D2-05 đã hoàn tất. [Release riêng](../outputs/revision/account_annualisation_v1/manifest.json)
khóa sáu outputs và nguồn/runtime. Không gọi API, thay prediction/label hoặc
dựng lại daily ledger. `before_sources.zip` giữ nguyên ba source files tại
commit `c801af51` trước sửa; commit này chỉ là baseline code của task, không
được gán thành execution commit của legacy inference.

### Thay đổi runtime và caller

`utils/account_risk.py` tách phép tính ratio khỏi chu kỳ mua/bán. Các điểm
mới từ engine, robustness và ablation ghi `entry_bar_index`/`exit_bar_index`
theo chính frame đã chạy. Chỉ công bố annualised cycle ratio khi daily bars
có bước đều S, span L=S và ít nhất hai cycles. Hệ số là sqrt(252/S), tức
sqrt(84) khi S=L=3; không suy phiên giao dịch từ chênh lệch ngày lịch, vì
weekend/holiday làm calendar gap khác bar gap. Lịch có cash gap S>L, index
thiếu/không đều hoặc timeframe chưa hỗ trợ trả ratio null, kèm reason; muốn
annualise các trường hợp đó phải dùng ledger/tần suất được xác thực riêng.

Giữ cách tính numerator và denominator của runtime cũ để tách riêng sửa
tần suất: mean tất cả period returns, kể cả zero của CASH, risk-free/MAR=0,
SD population (ddof=0). Trường `sortino_ratio` tiếp tục là **Sortino-like
negative-subset SD diagnostic**: mean return / population SD của tập return
âm, không phải downside RMS/lower partial moment. Metadata ghi rõ quy ước;
không đổi tên thành canonical Sortino hoặc âm thầm thay denominator. Không
downside, chỉ một negative return, constant returns hay variance <=1e-12:
ratio không xác định → null trong JSON, NA trong CSV/bảng, không zero/Infinity.

Partial/final summaries và bốn ablation variants dùng cùng helper; CSV
robustness/ablation xuất metadata dưới dạng JSON hợp lệ và NA cho ratio thiếu.
Resume checkpoint cũ thiếu bar index vẫn giữ quyết định đã có, nhưng không
retrofit provenance để tạo ratio annualised. Các schema cũ giữ tên trường
và bổ sung metadata, với ratio nay nullable theo hợp đồng undefined. Thay đổi
0→null cho CASH/constant là có chủ ý; tests bao phủ caller và serialization.

P&L, fees, shares, wealth, hit rate, average trade, target và parser không đổi:
AST đối soát đoạn mua/bán/cập nhật point, cost validation, net-return formula,
drawdown và các phương thức inference/parse với source trước task đều khớp.
68 tests trong account/risk/ablation/robustness/significance/revision-baselines
PASS, gồm oracle sqrt(3), population SD, weekend, schedule gap/missing index,
cash/zero-variance, partial/final, CSV JSON/NA, resume và AST tamper. MDD của
engine vẫn **cycle-end drawdown including initial wealth**, không được gọi
là daily-close MDD; metadata ghi đúng basis.

### Hai nguồn return được đối soát riêng

1. **Legacy benchmark:** 18 accounts (Full/Base của chín mã), 20 cycles/account.
   [Bảng](../outputs/revision/account_annualisation_v1/cycle_risk_table.tex) và
   [CSV](../outputs/revision/account_annualisation_v1/legacy_cycle_ratios.csv)
   giữ stored ratios, tái tính sai số tần suất sqrt(252) từ return đã lưu, rồi
   xuất cột **conditional declared S=L=3** với sqrt(84). Không lấy stored
   ratio đã làm tròn chia sqrt(3), mà tính từ period returns lưu (vốn đã làm
   tròn tới 8 chữ số ở thang percent). Ví dụ BHN Full −3,63 → −2,093 chỉ có
   ý nghĩa dưới giả định đó. Full chỉ có 1–7 LONG cycles/mã; CMG và HVN có
   denominator downside suy biến, nên Sortino conditional là NA thay zero
   đã lưu. Không dùng các tỷ lệ này để chứng minh profitability/alpha.
2. **Daily MTM:** đọc đúng 102 LLM ledgers ở analysis cộng 408 numeric/holding
   ledgers ở bank; kiểm hash nguồn và net return khớp economics cho đủ **510
   accounts**. Return đầu tính so với initial capital đã khóa, các return
   sau từ equity hiện tại/equity phiên trước −1; giữ nguyên mọi zero-return
   CASH gap, không lọc riêng ngày giao dịch/LONG. Annualisation sqrt(252)
   áp dụng trên return **observed daily vendor bars**, không trên sparse
   cycle returns. Có 268 Sharpe và 234 negative-subset Sortino defined;
   denominator còn lại là null/NA. Daily drawdown được dẫn nguyên từ ledger.
   Không ghép accounts thành portfolio, không giả định market/calendar hay
   execution đã được exchange chứng nhận.

[Calendar crosscheck](../outputs/revision/account_annualisation_v1/calendar_crosscheck.csv)
phân biệt sự hiện diện cục bộ với provenance của input legacy. So entry/exit
trên snapshot giá hiện có thấy mismatch theo thứ tự BHN/CMG/FPT/HVN/MBB/MWG/
VCB/VJC/VNM: **20/1/20/1/1/20/9/0/2** trên 20 cycles/mã. BHN có span 3/4 bars,
steps 3/4/5 khi map timestamps sang calendar này; tám mã còn lại đều 3/3.
Đây là bất nhất giữa snapshots, không đủ căn cứ chỉ ra snapshot nào đã tạo
legacy inference hoặc chỉnh lại giá/nhãn. Ngay cả VJC khớp giá/ngày cũng không
có call/input provenance để xác nhận snapshot đầy đủ. Vì vậy cột
`authenticated_annualised_*` của cả 18 legacy accounts giữ null; conditional
sqrt(84) không bị gán thành kết quả đã xác thực. Không chỉ chia mù mọi con
số sqrt(252) trong repository; alpha-selection diagnostic riêng không đổi.

### Nghiệm thu và giới hạn

```powershell
py -3.13 -X utf8 scripts/audit_account_annualisation.py --check
```

Lệnh kiểm nguồn/runtime/output hashes và tái tính outputs nguyên byte; source
ZIP và nguyên 510 ledgers được giữ. Chỉ compile chín Python thay đổi. Không
chạy toàn suite/E2E/leakage vì không đổi đường giá/PIT/retrieval/prompt/labels;
scoped tests trực tiếp bao phủ hợp đồng kinh tế và các caller. Engine source
đã đổi nên gate/runtime receipt cũ vẫn là lịch sử của source cũ, không được
báo là đã nghiệm thu runtime mới; các source archive trước task được bảo toàn.
Bảng annualisation đã build standalone và render QA một trang, không tràn/cắt.
Paper/PDF R4 không được ghi lại trong task này; formula/wording/locators của
R5 còn phải đồng bộ ở task manuscript. D2-06 done không đồng nghĩa R5 đã đóng.

## Execution sensitivities — D2-07

Ngày 03/11/2026, dependency D2-06 đã xong. [Policy](r15_execution_policy.json)
khóa đủ 12 scenarios trước tính lượt sensitivity bổ sung; đây là phân tích
sau inference, không confirmatory. [Release](../outputs/revision/execution_sensitivity_v1/manifest.json)
giữ predictions/label net/cutoff/L=3, không gọi API hay sửa engine/ledger cũ.
510 accounts =51 symbol–block scopes ×chín classifiers và continuous-hold
price comparator. Reference tái lập net return, daily-close drawdown, orders,
brokerage fees và slippage cho cả 510 records đã khóa. Tổng 6.120 scenario
accounts không phải 6.120 độc lập hay market units mới; support vẫn 102 units,
918 classifier predictions, mean return tính trên 51 accounts/variant,
không portfolio. Continuous hold có một vòng mua/bán qua hai cutoff anchors,
khác always-LONG mỗi cycle.

### Settlement, ứng trước và thời điểm event

[Thông báo VSD ngày 19/08/2022](https://vsdc.vn/vi/ad/152750), kiểm tra ngày
03/11/2026, nêu mốc hiệu lực 29/08/2022, thanh toán T+2 vào buổi trưa và phân
bổ cho khách trước 13h để giao dịch buổi chiều. Nguồn này hỗ trợ thiết kế
assumption sau 2022, không xác nhận đầy đủ mọi rule/broker/venue/date trong
giai đoạn 2023–2026. Calendar trong code vẫn là **observed vendor bars**,
không được đổi nhãn thành official exchange/settlement calendar.

Ledger event phân biệt open/close. Cổ phiếu mua tại e chỉ bán close từ e+2
trong các scenarios stock_lag=2; tiền từ sale có T+2 afternoon release, nên
không chi tại open của chính ngày đó. Tiền pending vẫn là receivable asset
trong wealth, nhưng không buying power. Daily rows tách settled/pending cash,
settled/unsettled shares và stock MTM, bảo toàn wealth=cash+receivable+stock.
Không lấy chênh lệch ba ngày lịch thay ba sessions. Các event records có
`date`, `phase`, `timezone=Asia/Ho_Chi_Minh`, `clock_time=null`; timestamp
07:00 trong bar legacy không bị gán thành giờ khớp lệnh thật.

On-demand advance chuyển receivable thành cash khi có BUY trước maturity,
trừ phí và xóa đúng claim đó để không đếm hai lần. Auto advance chuyển mọi
sale proceeds ngay khi bán, kể cả chưa cần mua tiếp. Cả hai dùng rate giả định
15%/năm ACT/365 cho số ngày lịch tới T+2 observed-session date; không trình bày
như báo giá broker. Không có maturity date trong snapshot thì giữ pending,
ghi unavailable thay vì tự tạo ngày/fee. Các unit fixtures có cycles sát nhau
kiểm tiền bị chặn, cùng-ngày settlement không chi tại open, weekend và phí
ứng trước. Đây là bằng chứng kỹ thuật, không thêm empirical market units.

**Kết quả trên mẫu thật:** hai cutoffs/account cách nhau 57 observed sessions,
vì vậy pending_t2 và advance_on_demand đều có cùng return reference trong
tolerance số học, không có on-demand fee. Không dùng kết quả này để nói
settlement không quan trọng trong backtest 3-session spacing. Auto advance
vẫn thu phí cho mọi sale: Full mean return từ −0,884135% xuống −0,923465%.

### Chi phí, fill và capacity bounds

Scenarios per-leg fee/slippage: lower=0,10%/0,05%; reference=0,25%/0,10%;
higher=0,50%/0,30%. Một stress riêng cộng sell charge 10bp, **không nhận đó là
thuế suất lịch sử đã xác minh**. Tất cả 510 fixed-fill accounts được kiểm
return ordering higher-cost <=reference<=lower-cost. Không chỉnh prediction
hoặc nhãn net theo cost mới để tăng accuracy; các kết quả mới chỉ là kinh tế.

No-fill proxy dùng zero-volume hoặc flat OHLC bar; đây là **ex-post fill
feasibility screen**, không phải signal đã biết tại open, cũng không xác nhận
ceiling/floor lock hay suspension. Missing venue/reference-price/queue data
ngăn chứng nhận fills từ OHLCV. Một scenario hủy BUY nếu proxy chặn; scenario
delayed cho retry BUY tối đa hai bars, exit không trước stock maturity. SELL
bị chặn thì giữ shares, thử lại tới common tail; không đổi thành CASH hoặc
gán proceeds ở target date chưa bán được. Các scenarios cùng horizon báo cáo:
last planned exit +5 observed bars, cắt tại snapshot end. Residual shares
được MTM và báo riêng, không trừ phí thanh lý tưởng tượng.

Lot100/cap1pct scenario dùng whole lots 100 và planning cap 1% trailing
20-bar mean Volume **shift(1)**. Cap này là hạn mức kế hoạch theo ADV quá khứ,
không phải chứng minh realized participation 1% hay fills thực; Volume unit
được giả định là shares và giá snapshot nhân 1000 thành VND như engine.
Không dùng volume ngày hiện tại để retroactively chọn partial-fill size.
Exit vượt planning capacity giữ nguyên whole position, không tự suy partial
fills. Các giả định units/lot/venue cần đối chiếu riêng trước execution claim.
Combined thêm high-cost/sell-charge, pending, delay/proxy và lot/cap. Có một
continuous-hold account còn residual stock trong mỗi scenario lot/cap và
combined; các account Full/Base đều flat ở terminal. Scenario all_entries_missed
giữ prediction nhưng mọi BUY không fill, nên wealth=CASH 0%.

Full mean net account returns: reference −0,884%; lower-cost −0,707%;
higher-cost −1,279%; no-fill proxy −0,812%; delayed proxy −0,845%;
lot/cap −0,753%; combined −1,154%. Tất cả có fills vẫn âm. Việc ít lỗ hơn
khi bỏ một trade không chứng minh dự báo tốt hơn hoặc alpha. Scenario
envelope không phải guaranteed mathematical worst/best case: mất fill có thể
bỏ lãi hoặc né lỗ. B/Full, mọi controls và continuous hold đều được xuất,
không chọn scenario thuận lợi để thay reference đã khóa.

### Đầu ra, kiểm tra và phần còn mở

Bảy outputs: policy/report JSON, 6.120 account results, 120 scenario×variant
summary rows, 8.420 events, 394.560 daily states (CSV gzip xác định mtime=0)
và một bảng TeX Full/Base từ cùng source. Daily state và event logs có khóa
scenario/symbol/fold/variant; fills nối đúng unit ID. Undefined clock time
ghi null/NA, không giả millisecond execution timestamps. Bảng đã build
standalone A4 đúng bề ngang bản thảo, render và kiểm trực quan không tràn/cắt.

```powershell
py -3.13 -X utf8 -m unittest discover -s tests -p test_revision_execution.py -v
py -3.13 -X utf8 scripts/analyze_revision_execution.py --check
```

27 tests mới và liên quan PASS: 13 execution tests, 14 baseline PIT/daily-ledger
tests. Bao phủ reference equivalence, pending/advance conservation, stock
maturity, missing settlement date, proxy/delay/residual, whole lots, lagged
capacity, future-poison invariance và snapshots fail-closed. Chỉ compile ba
Python mới, đối soát hashes/runtime và tái lập mọi output nguyên byte ở process
mới. Không chạy toàn unit suite/E2E hoặc gọi API; shared engine, original
ledger helper, frozen prices, labels, raw responses và receipts không đổi.

D2-07 done là hoàn tất sensitivity được kế hoạch yêu cầu, **R15 vẫn mở** cho
official calendars, venue/date bands/auction/queue, actual fills, Volume units,
broker rates/statutory taxes, corporate actions và L=5/10 evidence ngoài gói
đã khóa. Manuscript/response hoàn chỉnh và PDF locators cũng chưa được chốt;
không gán kết quả sensitivity thành execution certification hoặc profitability.


## D2-08 — Hợp đồng nhãn, schema và appendix (03/11/2026)

`utils/target_contract.py` và `revision/target_schema.json` định nghĩa
`net_cycle_v1`: decision Close C[e-1], entry Open O[e], target Close C[e+L-1],
gross/net return dạng fraction, hai labels với zero = DOWN, indices/horizon
và phí label. Engine, shared robustness và ablation ghi outcomes sau inference;
không thêm chúng vào graph inputs. Checkpoint/metrics từ chối canonical
records thiếu hoặc tự mâu thuẫn; legacy vẫn `legacy_unverified`, không suy
cutoff từ alias. Execution stress không relabel target. Graph-backed runs
với phí khác prompt cố định 0,25%/0,10% mỗi chiều bị chặn trước khởi tạo
client; offline stress vẫn được phép. Công thức target/alpha và builder không đổi.

`outputs/revision/target_contract_v1/` giữ bảy outputs và khóa 822 sources.
Tái tính từ đúng frozen frame cho 102 units khớp net/gross labels của 918
predictions; bảy units khác nhãn gross/net. Audit 30 legacy JSON có 600 point
records: 178 aliases bằng entry Open, nhưng decision Close cả 600 vẫn null
vì thiếu authenticated original snapshot. Không sửa giá/label/prediction/cache
lịch sử. Có net contract hai chiều trong 486 R1 và 274 R4 actual archived
Decision attempts (gồm smoke, retry/errors; không phải 760 successes hoặc
market observations độc lập). SHA-256 prompt source khớp R4. Không gọi API mới.

Appendix bỏ label log Close-to-Close sai và fictional input fields, tách
selected runtime state khỏi evaluation schema. English Decision example sinh
từ compact builder chỉ là minh họa; actual Vietnamese requests lưu riêng.
Token legacy `T+2.5` cho daily L=3 không chứng nhận settlement. Canonical
returns là fractions; aliases `actual_pct_change`/`execution_pct_change` vẫn
lần lượt là net/gross percent, khác realised executed-account return.

`outputs/revision/target_manuscript_v1/` có hai PDF, hai logs và source ZIP
(71 files), khóa 73 source/5 output hashes. Build pdflatex, bibtex, hai lượt
pdflatex cuối cho mỗi entrypoint; cả hai có 63 physical pages. Appendix B.1
physical pp50–51 (printed pp48–49), selected state Table C.36 physical p55
(printed p53), target Table C.37 physical p56 (printed p54). Trang 1–49 giữ
extracted layout text của R4, ngoại trừ cross-reference F.38 thành F.39 ở p18;
R1–R4 page locators giữ nguyên. Render/visual main pp50–63 và submit pp50–56
PASS; không undefined references/citations, duplicate anchors hay tràn body/
table. Chỉ còn warning footer elsarticle 2,61049pt đã tồn tại. PDF/ZIP/logs R4
cũ nguyên byte; phần manuscript R5/R15 còn riêng.

96 tests trong chín modules liên quan PASS: target contract (11), account
PnL/risk, paired protocol, ablation/robustness checkpoint, alpha-target,
prompt/token và baseline PIT/leakage. Assertions mới kiểm metadata qua các
caller và xác nhận outcomes không vào fake decision graph. Bao phủ gap,
zero, phí hai chiều, holiday, incomplete horizon, JSON/native types, legacy,
cost stress không relabel và canonical tampering. Lỗi shadow biến trong
assertion test ablation mới được sửa; cả ba ablation tests chạy lại PASS.
Chỉ compile chín Python đã đổi; không chạy toàn suite/E2E do phạm vi không
đòi hỏi, không viện dẫn gate cũ cho runtime mới. `jsonschema==4.24.0` chỉ pin
audit/test offline đang có; không cài/nâng dependency.

Fresh-process `PYTHONHASHSEED=17` audit `--check` kiểm 829 hashes và tái sinh
bảy outputs nguyên byte. Gói manuscript đối soát 78 hashes và mỗi entry ZIP
với source bytes. R11 có thay đổi, artifact, manuscript locator và supporting
response: addressed trong phạm vi label/fields với legacy provenance unknown
công khai, không xác nhận ngược submission/model revision hoặc khả năng sinh lời.


## D2-09 — Indicator rules và custom Alpha_4 (03/11/2026)

Phạm vi là prose, schema description, hình pipeline và bằng chứng biên;
không sửa module runtime, công thức, toolkit, prompt hay đầu vào thí nghiệm.
Chín nguồn indicator/alpha/state/Decision/registry/toolkit/graph/i18n/selector
khớp SHA-256 R4. Giới hạn kiểm tra này chỉ áp dụng cho chín file được nêu,
không tuyên bố toàn runtime hiện tại là phiên bản R4 cũ.

Table 1 và Appendix E theo đúng ưu tiên classifier: RSI >=70 bearish,
<=30 bullish, 55–70 bullish và 30–45 bearish với endpoints tường minh.
Vùng 45<RSI<55 so giá trị hiện tại với giá trị retained thứ ba từ cuối,
không mặc định neutral. Mỗi list lọc nonfinite và round bốn chữ số trước
phân loại nên không gọi các retained samples là nến liền nhau khi thiếu dữ
liệu. MACD crossover ưu tiên hơn histogram, equality không phải previous
cross, histogram bằng nhau giữ hướng. Stochastic cross ưu tiên extreme;
fallback giữa vùng giữ nguyên equality/zero-D truthiness legacy. Williams
threshold ưu tiên trend; ROC strict ±0,5% và equality neutral. Missing/error
neutral vẫn ở denominator năm; không coi đó là neutral market evidence.
Consensus là directional plurality, tie MIXED; confidence không phải xác suất.

Chạy toolkit thật trên OHLCV tổng hợp xác nhận chỉ năm compute tools được
gọi, node chỉ trả `indicator_report`/`messages`, không ghi mảng numeric kể cả
năm indicator. BB/ADX là declared slots, không là hai votes phụ; BB được
tính riêng ở alpha, ADX không được node Indicator gọi/forward. Report counts
được tạo bằng Python; backtest không gọi Indicator LLM, live prompt yêu cầu
copy count nhưng không chứng nhận model tuân thủ hoàn hảo.

Alpha_4 giữ `tanh((%B-0.5)*VolZ5*1.5)`: z âm đảo dấu, z=0 hoặc %B=0,5
triệt tiêu. Không có gate band-width squeeze, temporal crossing hay positive
volume expansion. Prototype threshold ±0,10 strict trước display rounding;
registry có sample-SD preprocessing khác prototype population-SD/rounded
features, được kiểm riêng bằng NumPy array oracle. Không đồng nhất mọi giá
trị hai implementation. Tên/interpretation legacy còn nguyên trong metadata/
prompts và được audit xuất rõ, không dùng các câu “confirmed by volume” để
thay nghĩa công thức. Custom thay proprietary ở TeX, Figure 1 dùng vector
LaTeX mới; PNG lịch sử không bị sửa. Flow/liquidity/pressure chỉ là OHLCV
proxy, không có signed trades/order book/queue/institutional-flow inputs.

Release `outputs/revision/indicator_alpha_rules_v1/` có ba outputs, 13 source
hashes (16 hashes cả outputs). Fixture JSON gồm 67 indicator, năm consensus,
11 prototype và ba registry cases, tổng 86 synthetic cases. Chúng là oracle
số học/branch, không phải market observations hoặc predictive-performance
mới. Bảy unit tests PASS, gồm fixture mismatch fail-closed, nguồn R4, tính
tái lập, signed examples và toolkit/report-only path. Chỉ compile hai Python
mới. Không chạy lại full suite/E2E/leakage vì không đổi runtime/data/PIT/
retrieval; không dùng test thay bằng chứng LLM thực nghiệm.

Release `outputs/revision/indicator_alpha_manuscript_v1/` có hai PDF, hai
build logs và source ZIP 70 files, khóa 72 source/5 output hashes. Build
pdflatex/bibtex/hai lượt pdflatex cuối mỗi entrypoint; main 65 physical pages,
submit 64. Locators physical: Table 1 main14/submit13; custom prose/Table 2
p15, vector Figure 1 p16 cả hai; state C.36 main56/submit55; Alpha_4 main58–59/
submit57–58; signed Table D.38 main59/submit58; classifier Appendix E main59–60/
submit58–59. Manifest có mapping printed/physical labels cho các nội dung cũ
và mới; không tái gán locators của archived release vào PDF hiện tại.

Render/visual main pp5–17/56–62 và submit pp13–16/55–61 PASS. Không clipping,
body/table overflow, undefined references/citations hay duplicate anchors;
chỉ còn footer overfull 2,61049pt elsarticle cũ. Text PDF không còn proprietary.
Sources sections 01/05/06/07/08 khớp bản trước, không đổi kết quả/claims thực
nghiệm. Các gói cũ được kiểm nguyên output hashes, không chỉnh artifacts.
Fresh-process `PYTHONHASHSEED=17 --check` tái lập ba audit outputs; gói mới
đối soát 77 hashes và 70 ZIP entries. R12/R13 có thay đổi, artifact, manuscript
locators và response. Việc chứng minh alpha/novelty, registry selection R10,
chart R14 và execution R15 vẫn là phạm vi riêng.
