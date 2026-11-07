# Kế hoạch đánh giá lại trên dữ liệu lịch sử từ nhánh fix

Cập nhật08/11/2026. Hệ thống gồm Bayesian Prior v1, Bayesian Prior v2 với
đại diện C2, Bayesian Prior cải tiến A/B và MT-BICL.
[Checklist hiện hành](README.md#checklist-đánh-giá-lại) quản lý H01–H09.
H01/H02 đã hoàn tất audit; readiness còn blocker, H03–H09 chưa triển khai.

## 1. Phạm vi và registry

Hệ gốc Original là đối chứng chung. Mọi phương pháp giữ trong report kể cả
khi kết quả âm hoặc không đạt nomination. Mỗi phiên bản có namespace và
hash source/model/input/prompt riêng; cùng dữ liệu và ngân sách inference.

| Nhóm phiên bản | Primary | Thành phần được giữ |
| --- | --- | --- |
| Bayesian Prior v1 | `bayesian_v1` | Memory Bank, regime retrieval, agent signals và BRPP |
| Bayesian Prior v2 | `C2` | Conditional statistics, shrinkage, split readiness và ranking |
| Bayesian Prior cải tiến A/B | `A_tp_pool`, `B_semantic` | Partition T/P và renderer tương ứng |
| MT-BICL | `MT_BICL` | Student/teacher frozen, bucket context, facts, posterior utility và veto |

Primary có **6 nhánh**, gồm Original và5 cải tiến. Fact_Anchor là dependency
bắt buộc của MT-BICL trên toàn lưới. Các cấu hình nội bộ khác của Bayesian
Prior vẫn phục vụ kiểm thử hợp đồng; chúng không thêm phiên bản primary.

MT-BICL dùng các module `core/mt_bicl_*.py`, schema
`mt_bicl.schema.json`, cấu hình `mt_bicl_protocol.json` và model manifest
`mt_bicl_model.json` trong thư mục tuần này. Các thành phần teacher/student,
task/scaler/regime và shared prompt thuộc một phương pháp MT-BICL hiện hành.

## 2. Nguồn fix đã kiểm tra

Nguồn donor là `9efd23f4157e0d3ab8069fccab7dccf03439a714`. Import chọn
lọc bằng Git blob vào `outputs/historical_reevaluation/inputs/fix/`, giữ
donor commit, blob OID, SHA256 và byte count. Archive hiện có21 blob nguồn.

| Nguồn trong fix | Hợp đồng cần tái dùng |
| --- | --- |
| `scripts/freeze_revision_prices.py`, `r1_prices_v1/manifest.json` | Snapshot giá, hashes, thời điểm tải và adjustment |
| `core/revision_baselines.py` | Kiểm OHLC, suffix BHN, nhãn net và purge |
| `core/revision_common_study.py` | Shared state, prefix query và frozen sentiment |
| `core/revision72_data.py` | Sáu khối lịch sử, lịch102 unit và news availability |
| `core/revision_r2_panel.py` | Kiểm ngày thật, warmup và label maturity |
| `core/revision_minimal_bank.py` | Parent/hash và điều kiện cache reuse |
| `sentiment_inventory_v1/summary.json`, `sentiment_coverage_v1/summary.json` | Scorer provenance và coverage |
| `chart_convention_v1/report.json`, `r4_final_v1/manifest.json` | Convention ảnh và đủ factor rows trong prompt |
| `final_temporal_v1/contamination.json` | Exposure lịch sử và scope exploratory |
| `utils/target_contract.py`, `core/revision_execution_final.py` | Entry/exit, label net và ledger |

Các đường output rút gọn trong bảng nằm dưới `outputs/revision/`.
Các tên A/B của factorial fix phải có mapping độc lập với A_tp_pool/B_semantic.

### Giá và lịch

Snapshot VCI/vnstock tải01/11/2026 có9 mã BHN, CMG, FPT, HVN, MBB, MWG,
VCB, VJC, VNM, mỗi mã1.681 dòng từ02/01/2020 tới30/09/2026. Đã kiểm9/9
CSV từ Git khớp manifest. Snapshot là chuỗi vendor tải hồi cứu; adjustment
và ledger quyền/cổ tức chưa được chứng nhận đầy đủ.

BHN có OHLC mâu thuẫn ngày13/09/2022. Giữ raw, dùng suffix từ14/09/2022,
bỏ673 dòng prefix theo policy fix. BHN thiếu600 nến sạch ở ba khối đầu.
Eligibility dựa input/warmup, không dựa lợi nhuận.

| Khối | Train tới | Test start | Số mã |
| --- | --- | --- | ---: |
| b2023_h2 | 31/03/2023 | 03/07/2023 | 8 |
| b2024_h2 | 31/03/2024 | 01/07/2024 | 8 |
| b2025_h1 | 30/09/2024 | 02/01/2025 | 8 |
| f2025_q4 | 30/06/2025 | 01/10/2025 | 9 |
| f2026_q2 | 31/12/2025 | 01/04/2026 | 9 |
| f2026_q3 | 31/03/2026 | 01/07/2026 | 9 |

Validation nằm sau train và mọi label phải exit trước test. Tên khối h2
là ID donor; các cutoff thực của hai khối này nằm trong quý III.

### Tin và LLM

Cache legacy có180 record/177 identity;155 record qua kiểm nguồn/ngày.
Scorer lịch sử của180 record đều unknown. Fix chấm lại154 identity bằng
ViSoBERT revision `d7738b85200272f10ba8b048d80236c8c582b581`,
mapping0 NEG/1 POS/2 NEU, tạo155 membership bài–mã.
Date-only khả dụng từ ngày sau, cửa sổ90 ngày, tối thiểu3 bài.

Trên102 cutoff có23 đủ ngưỡng bài và79 missing; downstream normalizer chỉ
đánh dấu9 reliable. H04 phải đối soát count/score/mask qua cả hai lớp.
Archived publication content chưa được chứng nhận PIT đầy đủ.

Indicator/Alpha backtest tính bằng Python, Pattern/Trend dùng vision.
Fix có sửa convention ảnh và lỗi nén làm mất factor rows. Mỗi prompt cần
kiểm đủ tên, giá trị và mask của5 factor rows, cùng ảnh và parent state.

Toàn bộ thời điểm giá/nhãn đều trước inference của fix. Dữ liệu lịch sử
đã exposed và served-weight revision chưa được xác minh; kết quả historical
mới được phân loại exploratory. Cohort forward cần release riêng.

## 3. Cohort và dữ liệu chung

Giữ102 anchor donor để kiểm mapping. Mở rộng mỗi scope thành20 cutoff,
`decision_i=first_decision+3*i`, i=0..19. Audit đã đối soát **51 scope,
1.020 unit và120 ngày cutoff**,51/51 endpoint khớp donor, đủ target t+3.

- **CORE4 primary** gồm FPT/MWG/VCB/VNM,6 khối,480 unit. Macro đều bốn mã
  trong block, rồi đều sáu block.
- **EXTENDED secondary** gồm1.020 unit của9 mã eligible. Báo riêng540 unit
  của năm mã bổ sung và mask BHN. Hai cohort có giao nhau.
- Lỗi API/code là pending/error. Thiếu support prior/utility giữ ID và dùng
  fallback đúng recipe đã khóa. Kết quả chỉ COMPLETE khi đủ toàn bộ G.

Stride3 có thể cho exit trước trùng ngày decision sau; vị thế sau vào Open
phiên kế tiếp. Ledger kiểm `previous_exit < next_entry`; retrieval kiểm
`exit_date < query_date`. Adapter cần test boundary này vì audit decision
span của fix chặt hơn khi chạm ngày.

Mọi query thấy nến≤t, tin available≤t và observation exit<t. D/C/query rời
nhau, chronological, không lặp observation ở nhiều task. Lưu membership IDs,
max exit, scaler/model hashes, K/m, OOD và fallback reason.
Query outcome chỉ đọc sau forecast/checkpoint durable.

Availability pool mở rộng theo logical cutoff t cho mọi phương pháp.
Outcome của test trước chỉ vào memory query sau khi exit<t; training/selection
của model đóng trước test. Teacher/student giữ weights đã chọn. HMM giữ
recipe KLTN và prefix decoding; regime SMA/volatility/liquidity của fix là
strata mô tả riêng. Schema và input encoding của MT-BICL giữ bốn feature,
K≤3, m≤8; adapter chín mã cần parity trên bốn mã và kiểm OOD trên năm mã mới.

Labels sinh bằng `compute_round_trip_net_return`, đối chiếu độc lập
`target_fields` của fix. LONG vào Open(t+1), đóng Close(t+3), SHORT giữ CASH;
phí0,25% và slippage0,10% cả hai chiều, fractional shares và risk OFF.

## 4. Asset và data readiness

[Readiness máy](../../../outputs/historical_reevaluation/manifests/asset_readiness.json)
được tạo/cold-verify bằng `scripts/prepare_historical_assets.py`.
Gói model MT-BICL có candidate tensor và teacher pi pin hash; nạp qua
`core.mt_bicl_adapter.StudentAdapter`. Thiếu hoặc sai hash thì dừng trước
prediction, không tự train hoặc dùng teacher thay student.

H02 cần phục hồi đúng gói model, VNINDEX2026 và dữ liệu context/retrieval.
Các source/data guards còn hard-code bốn mã cần adapter universe tường minh
trong H04. Model/scaler chỉ dùng dữ liệu được recipe cho phép trước test.

Snapshot vendor đang mang `VENDOR_SERIES_LIMITED`; economic acceptance giữ
`PENDING_EXECUTION_DATA`. Kiểm quyền/chia tách/cổ tức, đơn vị giá/volume,
lịch và từng holding span trên9 mã. Đối chiếu theo ngày với execution source
hiện có; mọi splice hoặc dataset revision phải có provenance và dùng đồng
bộ mọi phương pháp. Không sửa nhãn riêng một nhánh để thay kết quả.

Kết quả đã lưu của MT-BICL có D=−5,313090 đpt so Original và
NOT_NOMINATED trên development60 điểm. Đây là kết quả cũ của phương pháp,
không là kết quả lưới1.020 điểm. Dữ liệu raw/report cũ thiếu một phần; kết
luận của lượt áp dụng lại phải có receipt và cold replay mới.

## 5. Inference và repeats

Đề xuất Decision `openai/gpt-oss-20b`, vision `qwen/qwen3.8-27b`,
temperature cấu hình0 và max_tokens960 cho cả hai. Lưu metadata thực, gồm
trường hợp SDK chuyển temperature thành1e-8. Đây là common contract mới.

Preflight kiểm schema, longest prompts, quota ITPM/OTPM/RPM/RPD/TPD và năm
organization `GROQ_ORG_1_API_KEY`…`GROQ_ORG_5_API_KEY`.
Log scope HMAC; API qua `_invoke_with_retry`, reserve đúng output budget,
backoff theo provider, checkpoint durable. Đổi options cần revision mới
đồng bộ panel; không đổi model/key ngầm.

Upstream chạy một lần/unit/realization, deep-copy sang mọi nhánh. Giữ
`_distill_report`, `_cap_report`, BRPP≤600 ký tự với K=3, prompt<6.500.
Reuse chỉ khi source/prefix/news/renderer/model/options/schema/payload và
parent hashes cùng contract. Cache2048/1024 của donor không được mặc định
coi tương đương contract960.

Chạy3 Decision executions mỗi unit trên upstream realization0, báo cả ba
và mean metric; không vote hoặc chọn best. Original chạy trước, Fact_Anchor
sau để resolve a0/proof, rồi MT-BICL revision. Các nhánh khác counterbalance.

Panel upstream chọn1 unit/scope bằng metadata/hash,51 unit. Thêm
realization1/2 và3 Decision repeats trên mỗi realization; mọi nhánh vẫn dùng
cùng upstream trong realization. Không đếm repeats thành N thị trường.

| Hạng mục nominal trước bypass/reuse | Công thức | Calls |
| --- | --- | ---: |
| Primary và Fact_Anchor | 1.020×7×3 | 21.420 |
| Ablation102 anchor | 102×10×3 | 3.060 |
| random/recent/similarity | 102×3×3 | 918 |
| Original_duplicate độc lập | 102×3 | 306 |
| Upstream panel bổ sung | 51×2×7×3 | 2.142 |
| Tổng Decision | Tổng năm dòng trên | 27.846 |
| Vision query/panel | 2×(1.020+51×2) | 2.244 |
| Vision historical bank | 2×H | Chốt H trong H03 |

Tổng nominal **30.090+2H research calls**, chưa gồm smoke/control/retry/
rejected/unknown. H là số historical upstream duy nhất còn cần dựng.
H03 phải chốt H, token/cost/RAM/quota và tính khả thi trước release.

Mười ablation LLM gồm stats/examples của C2/A/B và Plain_revision,
No_utility, No_target, Stats_only của MT-BICL. Fact_Anchor đã có trên toàn
lưới. Utility-only, student/teacher numeric và CASH/always-LONG chạy offline.
MT-BICL giữ utility4096 draws và common random streams; No_target phải
recompute posterior/student theo membership đã bỏ C.

## 6. Đo hiệu quả và uncertainty

Tài khoản reset50 triệu/mã/block/nhánh/repeat. Primary mỗi repeat tính
`D_j=mean_6_blocks(mean_4_symbols(R_j-R_Original))`, đơn vị đpt, rồi lấy
mean ba repeat. EXTENDED macro đều block rồi đều mã eligible trong block.
Không nối equity qua khoảng trống giữa sáu block.

Báo return/D, MDD/ΔMDD daily MTM và cycle-end riêng, LONG rate, exposure,
turnover, phí, số trade, confusion, accuracy, BA, MCC, macro-F1 và recall
hai lớp. Undefined giữ null. Strata gồm mã/block/regime/quý/K/m/missingness/
sentiment support, facts/utility support, OOD, latency và API cost.

Probability Brier/log loss/calibration chỉ cho đầu ra số có event contract
net-return-positive; confidence văn bản không là xác suất.
Đối chứng numeric gồm train-majority, momentum, logistic/factor cùng cutoff,
CASH/always-LONG cycles và continuous hold có ledger riêng.
Exposure-matched random chỉ fit trên train/calibration trước test.

Báo MT-BICL−Fact_Anchor/Plain/No_utility/No_target/Stats/Utility và phân rã
raw→facts→veto, cùng student−teacher gap. Bayesian full−stats/examples và
retrieval controls dùng cùng evidence. Giữ mọi contrast bất lợi.

Bootstrap10.000 draw seed20261107 trên whole time block, giữ toàn bộ mã,
method/repeat cùng block. Cùng draw indices cho mọi contrast.
Family primary gồm **5 contrast cải tiến−Original trên CORE4**.
Với draw b, `T_b=max_j(abs(D*_jb-D_j))`; CI đồng thời dùng
`D_j +/- quantile_0.95(T)`, quantile linear. BA có family riêng.
H03 khóa oracle cho ties, constant/null contrast và support thiếu.

Sáu block còn phụ thuộc thị trường; intervals historical là sensitivity có
điều kiện. Báo leave-one-block/symbol-out và từng repeat.
Mục tiêu precision đề xuất là half-width1 đpt cho D và3 đpt cho BA; mẫu cố
định chưa đạt thì LOW_PRECISION, không thêm mẫu chỉ để đổi dấu CI.
Candidate historical mang scope exploratory. Xác nhận độc lập cần cohort
forward/power/cluster plan và release khóa trước response đầu.

## 7. Checklist triển khai

| Bước | Đầu ra và điều kiện hoàn tất |
| --- | --- |
| H01 | Audit donor/source, registry và kế hoạch bốn nhóm hiện hành |
| H02 | Asset/data readiness, candidate grid, label bridge và blocker cụ thể |
| H03 | Protocol máy, IDs/folds, inference/options, repeats, families và budget H |
| H04 | Adapter/harness sáu primary, shared graph/history và symbol/OOD |
| H05 | Tests trực tiếp, PIT/leakage, economics/paired/retry/checkpoint và oracle |
| H06 | Freeze bank/runtime và smoke longest prompts/toàn registry |
| H07 | Collect CORE4, extension, ablation/retrieval và repeats đúng ma trận |
| H08 | Cold analysis/accounts/uncertainty/strata/cost |
| H09 | Receipt, README và bằng chứng với phạm vi kết luận đúng |

Namespace dữ liệu mới là `outputs/historical_reevaluation/`.
Model/runtime MT-BICL dùng `outputs/bayesian_benchmark/mt_bicl/`.
Cấu hình hiện hành ở trạng thái SPEC_ONLY; API/training release chưa cấp.

Kiểm H05 bao gồm future/query-y poison, exit==query, suffix index, symbol/
OOD, strict net label, full factor rows, cache contract, unknown retries,
immutable model fingerprint và bootstrap oracle. Compile đúng file Python
thay đổi; các gate nguồn cũ chỉ được viện dẫn khi hash/phạm vi còn phù hợp.
