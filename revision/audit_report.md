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
