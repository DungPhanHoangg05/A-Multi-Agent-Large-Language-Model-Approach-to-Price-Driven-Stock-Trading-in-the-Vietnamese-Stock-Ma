# Kế hoạch xử lý phản biện và xây dựng lại bằng chứng cho bản thảo

Ngày lập: 01/11/2026. Nhánh khảo sát: `fix`.

**Nơi cập nhật tiến độ hiện hành:** trực tiếp trong `plan.md`; R1–R4 đã được xử lý ngày **03/11/2026** tại [mục R1](#r1-progress), [mục R2](#r2-progress), [mục R3](#r3-progress) và [mục R4](#r4-progress). `revision/README.md` giữ vai trò nhật ký lịch sử; không tạo thêm file tiến độ hoặc dùng số đếm cũ ở đó làm trạng thái hiện tại.

## 0. Kế hoạch 72 giờ — năm org Groq Free, có hiệu lực 02/11/2026

**Trạng thái 03/11/2026: R1–R4 đã đóng trong phạm vi historical exploratory đã nêu ở từng mục.** Đủ **474/474 research decisions, 102/102 cặp B/AS**, panel Decision **18/18** và upstream **9/9**, thêm 10 smoke ngoài evaluation. [Analysis đã khóa](outputs/revision/r1_72h_run_v2/analysis/manifest.json), [release bản thảo cuối R1](outputs/revision/r1_manuscript_v2/manifest.json), [response](revision/response_to_reviewers.md). Lượt R4 riêng đã đủ 270/270 corrected-value decisions; R5–R18 vẫn đánh giá riêng; không gọi đây là hồ sơ đã sẵn sàng nộp lại. **T0 lịch sử = 2026-11-02T11:31:24.452715+07:00**; các mốc/cap cũ bên dưới là dự toán lịch sử, đã được policy mới thay thế.

**Cập nhật vận hành theo yêu cầu tác giả 02/11/2026:** bỏ toàn bộ cap nội bộ (40 Decision/org/24h, 200 attempts/org, 600 Decision, 1.000 attempts toàn study) và bỏ tự dừng theo T0+60h. Những con số này ở các phần kế hoạch/manifest cũ chỉ còn là lịch sử dự toán. Policy hiện hành là [provider-only pool](revision/r1_provider_policy.json): dùng mọi key còn khả dụng cho model cần chạy, chờ rate-limit ngắn, chỉ pause các job khi không còn provider dùng được; các job khác có input cache/model khả dụng vẫn tiếp tục. Dừng bình thường khi đủ 474 research decisions. Lỗi integrity/schema/config được báo riêng, không điền prediction. Không đổi model/prompt/output-token caps/units/variants/repeats/donor hoặc target theo outcome.

### 0.1. Năng lực và ngân sách

Tác giả xác nhận mỗi org Free chạy khoảng **20 Full +20 Base reports mỗi ngày**: 5×3×40=**600 quyết định** trong ba cửa sổ quota đủ. Đây là ước tính, không phải số API requests hoặc quota token đã xác minh. Quota còn lại thực tế và reset của từng org quyết định năng lực dùng được. Không mua quota hoặc đổi model để đạt deadline.

| Hạng mục | Decisions mới | Vision calls | API calls tối thiểu |
|---|---:|---:|---:|
| Tập chính 102 điểm × B/AS | 204 | 204 | 408 |
| Panel 18 điểm × B/A/S/AS/P × 3 repeats, trừ B/AS r0 | 234 | 0 | 234 |
| Panel upstream 9 điểm × 2 realizations bổ sung × B/AS | 36 | 36 | 72 |
| **Nghiên cứu tối đa** | **474** | **240** | **714** |
| Smoke ngoài evaluation, một cặp/org | 10 | 10 | 20 |
| **Tổng trước retry** | **484** | **250** | **734** |

Dự phòng **116 quyết định tương đương (~19,3%)** so với năng lực 600; không dùng để sweep/cherry-pick. Trần nội bộ: **200 API attempts/org/toàn study**, tổng **1.000**; **600 Decision attempts** toàn study, tối đa **40/org trong cửa sổ 24 giờ** kể cả smoke/retry. Trần nội bộ không thay limiter/token quota của provider. Mọi retry/repair đều phải được tính trước network; hết quota ngày thì checkpoint và chờ hợp lệ, không fallback model hoặc điền CASH.

### 0.2. Lịch 102 điểm và các panel

Một market unit là một mã tại cutoff. B=không alpha/không sentiment; A=alpha-only; S=sentiment-only; AS=Full; P=Full với alpha placebo nhân quả, giữ sentiment và cấu trúc prompt. Control lịch sử No-Alpha được gọi **Base reports**, vì bỏ cả alpha và sentiment.

- **54 điểm:** 9 mã × ba fold 2025 Q4/2026 Q2/2026 Q3 × cutoff thứ 1 và 20 trong lịch đã khóa.
- **48 điểm lịch sử:** 8 mã (không BHN) × ba block 2023 H2/2024 H2/2025 H1 × hai cutoff. Lấy phiên đầu từ 01/07/2023, 01/07/2024, 02/01/2025 và phiên cách 57 phiên giao dịch. Train kết thúc tương ứng 31/03/2023, 31/03/2024, 30/09/2024; validation bắt đầu ngày kế tiếp, purge trước test. Giữ W=45, L=3, lịch sử alpha 600 phiên.
- BHN không đủ lịch sử hợp lệ ở ba block cũ sau quality cutoff 14/09/2022; không giảm warm-up/sửa giá để lấp thiếu. Báo riêng universe tám mã chung qua sáu block và chín mã ở ba fold mới; báo pooled/macro và support thực.
- **Factorial panel 18:** chỉ chọn unit có >=3 bài hợp lệ trong 90 ngày sau audit/rescore pinned. Round-robin mã theo thứ tự tên, trong mỗi mã theo thời gian tăng dần, tối đa ba unit/mã. Khóa danh sách trước inference; không tuyên bố đủ chín mã/sáu block nếu coverage không hỗ trợ.
- **Upstream panel 9:** CMG/FPT/HVN ở cutoff cuối block 2023; BHN/MBB/MWG ở cutoff cuối 2025 Q4; VCB/VJC/VNM ở cutoff cuối 2026 Q3. B/AS r0 dùng lại tập chính; hai realizations sau tạo upstream mới, không nhân bản final decision.
- Placebo lấy vector alpha từ train trước cutoff, seed **20261102**, giữ schema/missingness và donor mapping. Alpha report không được rò sentiment; S không được nhận alpha.

**Gate trước inference:** nếu thiếu scorer pinned, nguồn tin hợp lệ hoặc không đủ 18 điểm sentiment, khóa nhánh dự phòng **B/Full/P ×3 repeats**. Tổng dự phòng **366 decisions/240 vision/606 research calls**; thêm smoke thành 376 decisions/626 calls. Không chạy factorial sentiment rỗng và không đóng R4 sentiment/R7 domain validation. Tập dự phòng lấy cutoff cuối từng block, lần lượt: `2023: CMG/FPT/HVN; 2024: MBB/MWG/VCB; 2025 H1: VJC/VNM/CMG; 2025 Q4: BHN/FPT/HVN; 2026 Q2: BHN/MBB/MWG; 2026 Q3: VCB/VJC/VNM`.

Không bảo đảm có hai người gán nhãn trong 72 giờ. Rescore local chỉ tạo provenance mới, không xác nhận chất lượng tài chính hoặc biến cache legacy thành snapshot PIT xác thực. Không đổi score cũ. Đánh giá numeric rộng hơn chạy offline, không gọi nó là LLM multi-year evidence.

### 0.3. Đường chạy và interface

Tạo profile `revision_72h`, protocol/bank/run mới; entrypoint riêng có `prepare`, `smoke`, `run`, `status`, `analyze`, `verify`. Dùng năm process/org riêng biệt; mỗi process có chart/temp/checkpoint riêng, một request đang xử lý. Phân shard cân bằng tải/block, không theo treatment. Secrets qua `GROQ_ORG_1_API_KEY`…`GROQ_ORG_5_API_KEY`; không lưu key hoặc hash key trong Git/artifacts.

Reuse bốn nhánh ablation, parser, retry/archive hiện có. Checkpoint có profile/input hash/variant/repeat/realization; parent upstream dùng chung đúng realization. Resume chỉ requests còn thiếu; archive response thành công phải tồn tại trước khi cho phép dùng lại. Freeze model/prompt/caps và tất cả inputs trước evaluation. Giữ `_distill_report`, `_cap_report`, Decision prompt <6.500 ký tự. Không chạy năm instance runner cũ trên cùng directory.

Trước nghiên cứu, smoke một cặp ngoài evaluation/org, archive hai vision và hai Decision responses. Status mới đếm riêng market units, variants, repeats, attempted requests, failures, tokens và coverage. Mục tiêu mỗi ngày khoảng **34 điểm chính +6 panel +3 upstream**, tối đa 158 research decisions; lịch cố định trước outcome, backlog không làm thay mẫu. Dừng inference T0+60h để dành 12h cuối cho phân tích/QA.

### 0.4. Phân tích và giới hạn kết luận

BA primary; MCC/per-class secondary; economic metrics riêng. Bootstrap mô tả **10.000** lần, seed **20261102**, resample nguyên block cùng cross-section/variants; ghi số block/ngày thật và resamples undefined. Khoảng 12 ngày của tập chính và panel nhỏ không mặc nhiên đủ power/significance. Không coi variants/repeats là market observations mới. Giữ target net cho replication; gross là target riêng đã định nghĩa.

Bàn giao hệ thống, bằng chứng thực thu được, bản thảo và response đủ 18 comment. Comment thiếu input/human validation/PID/author confirmation giữ pending. R8 cần đóng góp phù hợp thực tế, không chỉ đổi tên fusion. Không thêm fixed/random LLM variants, model/fusion mới, Bayesian/KLTN, grid W/horizon, Full-exposure calibration hoặc training mới trong 72 giờ; thu hẹp claim cần các thử nghiệm đó.

### 0.5. Bảo toàn lịch sử và chuyển giao

Grid cũ 8.100 Full decisions/14.580 calls và phương án trung gian 2.430 decisions/4.158 calls đã được thay bằng mục 0 hiện hành. Các protocol/bank/run cũ vẫn giữ nguyên byte. `revision/r1_common_protocol.json` không bị hạ repeats tại chỗ. **23 calibration v3 không tính vào 102 cặp mới.** Chỉ reuse giá/features/reports có cùng provenance/input/config hashes; tạo output riêng khi thay contract.

Tiến độ duy nhất ở `plan.md`; `revision/README.md` và runbook cũ là lịch sử. Ngày 02/11/2026 đã kiểm tra cục bộ đủ **năm biến `GROQ_ORG_1_API_KEY`…`GROQ_ORG_5_API_KEY`, năm giá trị khác nhau**; tác giả xác nhận thuộc năm org Free. Không in/lưu key và chưa gọi API để kiểm tra hiệu lực, org identity hoặc quota còn lại. Thiếu key không còn là blocker; smoke vẫn phải chờ runner/tests mới. Không có worker Python revision cũ được thấy trong lần kiểm kê tiến trình; receipt cũ không dùng làm trạng thái realtime.

**Đối soát các lần sửa trước:** `2bc5be2` đã thêm audit/metrics legacy; `d9d21b4` đã thêm snapshot, temporal baselines, daily ledger và sửa bản thảo nháp; `935e1cb` đã có bank chung/runner Full/archive; `81f11a4` đã sửa quota-day stop và retry interval. `7ad30c3`, `2bd9d66`, `3846ad2` chỉ cập nhật kế hoạch/tiến độ, không chứng minh profile mới đã triển khai. Bốn decision variants/shared upstream có sẵn trong `utils/graph_setup.py` và `core/backtest_engine.py`; runner nghiên cứu cũ vẫn chỉ chạy Full/grid cũ.

**Lượt này giữ kết quả thay đổi ở `plan.md`:** phần module/output nháp tạo trước khi tác giả làm rõ phạm vi đã được gỡ, không đưa vào baseline triển khai hoặc ghi là task hoàn thành. Thử chuẩn bị sentiment local đã dừng ở kiểm tra label mapping, chưa tạo score mới hợp lệ; không dùng lần thử này để đóng D1-05 hay R7. Không chạy Groq, không khởi động worker nghiên cứu mới.

## 1. Mục tiêu và đánh giá hiện trạng

Mục tiêu là tạo một bản thảo đủ chặt chẽ về phương pháp, bằng chứng và khả năng tái lập để có cơ hội được chấp nhận tại tạp chí Q1 đang nhắm tới. Đây là kế hoạch sửa nghiên cứu sau reject, không chỉ sửa cách viết. Không thể bảo đảm accept; kết luận cuối cùng phải theo kết quả kiểm chứng, kể cả khi hệ thống không vượt baseline.

Tệp reviewer chứa **một reviewer, 18 comment: 10 major và 8 minor**, tiêu đề “Reviewer 1 - Initial submission, October 24”. Chưa có thư quyết định của editor, manuscript ID, thời hạn hoặc điều kiện cho phép nộp lại. `paper/main.tex` và `paper/main_submit.tex` khai báo **Knowledge-Based Systems (KBS)**; dùng đây làm đích dự kiến, cần đối chiếu hồ sơ submission trước khi nộp. Không suy diễn reject thành lời mời revision và không coi nhãn Q1 là thay thế cho yêu cầu về đóng góp khoa học.

**Kết luận chính:** chưa đủ căn cứ giữ tuyên bố “alpha cải thiện dự báo một cách có ý nghĩa” theo cách trình bày hiện tại. Ưu tiên phải là: kiểm toán nguồn gốc kết quả → sửa target/metric/data contract → thiết kế lại thực nghiệm có baseline, placebo và repeated runs → kiểm định có phụ thuộc thời gian/thị trường → viết lại đóng góp và kết luận.

### 1.1. Nguồn đã đọc và đối chiếu

- `Reviewer Comments for author.docx`: toàn bộ 18 comment; nội dung ở phần thân Word, không có ảnh nhúng hay phần comments riêng cần giải mã.
- `paper/main.pdf`: 40 trang PDF; đối chiếu nội dung trích xuất, bảng kết quả và bảng sentiment bằng bản render.
- `paper/main.tex`, `paper/main_submit.tex`, toàn bộ 8 section nội dung, `appendices.tex`, `references.bib`.
- Chín JSON trong `outputs/backtest_result/`; checkpoint robustness và ablation trong `outputs/*/clean_a20/`; CSV sentiment coverage.
- Các điểm mã nguồn liên quan trong `core/backtest_engine.py`, `core/run_robustness.py`, `scripts/run_ablation_matrix.py`, `scripts/analyze_sentiment_coverage.py`, `scripts/verify_latex_tables.py`, `utils/statistical_tests.py`, `utils/graph_setup.py`, `utils/graph_util.py`, `utils/color_style.py`, cùng README, requirements và gitignore.
- Chín `sentiment_cache_{SYMBOL}.json` có trên máy nhưng bị `.gitignore` bỏ qua; không được Git theo dõi. Sự tồn tại cục bộ không chứng minh reviewer có quyền truy cập hay chúng chính là snapshot của lần chạy công bố.
- Tra cứu nguồn chính thức cho model Groq, QuantAgent, ViSoBERT, TradingAgents, metadata DOI và quy tắc thanh toán; nguồn cụ thể ở mục 9.

### 1.2. Các phát hiện đã kiểm chứng trực tiếp

Các số dưới đây được tính lại từ 180 test point hiện có, không phải kết quả thực nghiệm mới.

| Chỉ số pooled | Full | No-Alpha hiện tại | Luôn DOWN/CASH |
|---|---:|---:|---:|
| Accuracy | 65,00% | 51,11% | 68,89% |
| Balanced accuracy | 55,01% | 44,44% | 50,00% |
| MCC | 0,113 | -0,108 | Không xác định do dự đoán một lớp |
| Số LONG | 39 | 62 | 0 |
| Precision UP/LONG | 41,03% | 24,19% | Không xác định |
| Recall UP | 28,57% | 26,79% | 0,00% |
| Precision DOWN | 71,63% | 65,25% | 68,89% |
| Recall DOWN | 81,45% | 62,10% | 100,00% |
| Mean return của 9 tài khoản độc lập | -1,69% | -8,43% | 0,00% |

Confusion matrix theo thứ tự TP/FN/TN/FP: Full = **16/40/101/23**, No-Alpha = **15/41/77/47**. Tổng nhãn UP/DOWN = **56/124**. Full có thêm 25 dự đoán đúng so với control: 24 từ DOWN và 1 từ UP; đây là mô tả cơ chế thay đổi kết quả, chưa chứng minh nguyên nhân là thông tin alpha. Mean return trên là trung bình chín tài khoản, không phải return của một portfolio chung.

| Mã | Accuracy luôn DOWN | Accuracy Full | Return Full | Return luôn LONG từng chu kỳ, tính lại |
|---|---:|---:|---:|---:|
| BHN | 55% | 55% | -4,20% | -5,15% |
| CMG | 80% | 75% | -2,66% | -30,44% |
| FPT | 65% | 65% | -1,56% | -13,09% |
| HVN | 65% | 70% | +2,89% | -28,82% |
| MBB | 70% | 70% | +5,21% | -16,29% |
| MWG | 65% | 70% | +0,39% | -15,64% |
| VCB | 75% | 65% | -8,34% | -19,56% |
| VJC | 75% | 60% | -6,05% | -21,55% |
| VNM | 70% | 55% | -0,85% | -8,67% |

Luôn LONG mỗi chu kỳ chịu chi phí mua/bán nhiều lần; **không được gọi đó là buy-and-hold**. Số return ở cột cuối dùng entry/exit đã lưu và công thức phí của bài.

Các vấn đề về tính nhất quán cần xử lý trước khi chạy tiếp:

1. **Phiên bản bản thảo lệch nhau.** PDF vẫn có tiêu đề “A Multi-Agent Large Language Model Approach to Price-Driven Stock Trading in the Vietnamese Stock Market”; nguồn TeX có tiêu đề “Enhancing Multi-Agent Large Language Models for Stock Trading through Quantitative Alpha Integration”. Hàng All ở bảng E.12 trong PDF là `0/0/180`, trong TeX là `180/0/0`. Không được dùng số trang/reference của một bản để trả lời cho bản khác.
2. **R7 cần đính chính có bằng chứng.** Các cache hiện có thực sự chứa 20 article records/mã, tổng 180, tất cả parse được ngày và đều thiếu provenance scorer. Việc `total_articles = test_points = 20` tự nó không chứng minh script đếm nhầm. CSV hiện tại vẫn sai vì counts V/L/U là `20/0/0` trong khi percentages là `0/0/100`. Script hiện tại đếm `len(scored_articles)` và phân loại legacy thành unknown; vì vậy phải truy vết CSV cũ, không giả định sửa một dòng đếm là xong. Con số 8180 reviewer nhắc không xuất hiện ở đoạn tương ứng trong nguồn hiện có; cần lấy đúng bản đã nộp để xác định lịch sử sửa.
3. **R6 nghiêm trọng hơn trùng số làm tròn.** FPT Alpha-only trùng **20/20 dự đoán trên cùng cutoff** với No-Alpha của weighting/default; FPT Sentiment-only trùng **20/20** với No-Alpha của normalisation/zscore_tanh. Chưa có raw prompts/responses để xác nhận reuse, gán nhãn sai hay ngẫu nhiên trùng. Không kết luận gian lận; tạm coi bảng ablation chưa đủ provenance để chứng minh attribution.
4. **R3 có thêm nhiễu do lịch đánh giá.** Benchmark FPT dùng `data_end=2026-09-15`, còn robustness/ablation dùng `2026-09-18`; cutoff đầu lần lượt 18/06 và 23/06. Không được dùng spread giữa các bảng làm ước lượng thuần run-to-run variance, nhưng vẫn bắt buộc làm repeated runs trên đúng cùng snapshot.
5. **R14 có thể chủ yếu là lỗi mô tả.** `utils/color_style.py` đặt `up="#006340"` (xanh), `down="#A02128"` (đỏ); comment Python và mô tả trong bài lại đảo nghĩa. Phải xác minh renderer/prompt thực tế trước khi đổi màu hoặc quyết định chạy lại vision.
6. **Sharpe và Sortino cùng bị ảnh hưởng.** Engine nhân cả hai với `sqrt(252)` trên cycle returns. Với `S=L=3`, độ lớn bị nhân thừa khoảng `sqrt(3)`. Giá trị âm trở nên âm quá mức, không phải luôn “đẹp hơn”.
7. **Citation có lỗi thật.** Ba DOI gắn với các mục nghiên cứu alpha/Vietnam trỏ đến bài khác; một DOI chưa xác minh được. Chi tiết R16. Đây là vấn đề độ tin cậy học thuật, không chỉ định dạng.
8. **Model ID không nên tự ý sửa.** Tài liệu Groq hiện tại xác nhận `qwen/qwen3.8-27b` tồn tại và nhận ảnh. Điều này không chứng minh model đó đã thực sự chạy trong tháng 9/2026; vẫn cần log request/response lịch sử.

## 2. Thứ tự ưu tiên và nguyên tắc chốt kết quả

- **P0 — chặn sử dụng kết quả/nộp lại:** nguồn gốc branch/checkpoint, phiên bản submission, integrity dữ liệu/label/metric, references sai, baseline và attribution sai, thiếu lưu vết.
- **P1 — cần để trả lời major và bảo vệ đóng góp:** multi-year/multi-regime, repeated runs, placebo/factor controls, dependence-aware inference, sentiment validation, novelty/fusion.
- **P2 — hoàn thiện bản nộp:** diễn đạt, công thức/bảng, tài liệu kỹ thuật, tên tác giả, build/format. Một số P2 phải sửa trước chạy lại nếu làm thay đổi prompt hoặc đầu vào.

Giữ nguyên artifacts lịch sử trong vùng chỉ đọc và gắn hash. Không sửa dự đoán lịch sử để khớp lời giải thích; khi không xác minh được phải ghi rõ, loại khỏi bằng chứng xác nhận và chạy lại với protocol mới. Không tăng số lần chạy cho đến khi có p < 0,05; không chọn seed, giai đoạn, mã hoặc checkpoint tốt nhất sau khi xem kết quả.

Một comment chỉ đóng khi có **thay đổi cụ thể + artifact kiểm chứng + vị trí trong bản thảo + câu trả lời reviewer**. Viết thêm limitation không đóng được yêu cầu thực nghiệm của reviewer.

## 3. Ma trận xử lý toàn bộ comment

Các mục dưới đây giữ tiêu chí bằng chứng của reviewer; ô chưa đóng không có nghĩa phải triển khai lại toàn bộ thành phần đã có. Danh sách thực thi ở mục 5 đã bỏ việc hoàn tất và chỉ ghi phần bổ sung còn thiếu, dựa trên tiến độ R1 và đối soát mục 0.5.

<a id="r1-progress"></a>

### R1 — Baseline, mất cân bằng lớp và tuyên bố hiệu quả [P0]

**Vấn đề:** Full thua constant DOWN/CASH về accuracy và mean return. No-Alpha yếu hơn mức BA 50%; lợi thế trước control yếu chưa xác lập giá trị dự báo. Label hiện là “LONG có lãi sau phí”, không phải dấu biến động giá thuần túy.

**Trạng thái đối soát 03/11/2026: đã đóng R1.** Full thật và baselines đã được so sánh trên cùng **102 units/12 ngày/sáu block**, không ghép legacy với giá tái dựng. Đủ **474 research decisions +10 smoke**, 102 cặp chính, panel 18/9 và mọi repeats đã khóa. Full accuracy **62,75%**, BA **48,31%**, MCC **−0,035**; CASH accuracy **75,49%**, logistic giá BA **55,61%**. Mean net return của Full **−0,8841%** trên 51 tài khoản mã–block, CASH **0%**; không tuyên bố predictive superiority, isolated alpha/sentiment value hoặc profitability. Các mục nền/legacy bên dưới giữ vai trò lịch sử; trạng thái hiện hành được chốt ở R1.3–R1.5 và phần nghiệm thu cuối mục này.

**Đã hoàn thành và có artifact**

- [x] Khóa [target/metric contract](revision/target_contract.md): target net cho replication; `SHORT` là CASH; always-LONG từng cycle khác continuous buy-and-hold; undefined metric là `null`/`NA`.
- [x] Audit **9 mã/180 điểm legacy**: support, confusion, accuracy, BA, MCC, macro-F1, precision/recall/F1 hai lớp, LONG rate, pooled/macro và replay kinh tế. Full accuracy **65,00%**, BA **55,01%**, MCC **0,113**; CASH accuracy **68,89%**. Đây là audit kết quả lịch sử, chưa phải so sánh Full với baseline mới cùng snapshot. Bằng chứng: [report](outputs/revision/r1_legacy/report.json), [classification](outputs/revision/r1_legacy/classification.csv), [manifest](outputs/revision/r1_legacy/manifest.json).
- [x] Có [snapshot giá tái dựng](outputs/revision/r1_prices_v1/manifest.json) **9 mã × 1.681 phiên, 2020–30/09/2026** và [release numeric ban đầu](outputs/revision/r1_numeric_v1/report.json) **1.440 predictions/81 daily ledgers**. Giá entry/exit khác legacy ở **74/180** cycle, trong đó **2 nhãn đổi**; không ghép các kết quả này với legacy Full thành bảng head-to-head. Snapshot submission vẫn `unverified`.
- [x] Khóa [common bank v3](outputs/revision/r1_common_bank_v3/manifest.json) và [feature receipt](outputs/revision/r1_common_bank_v3/features_complete.json): **3.038 feature snapshots**, **540 test units = 9 mã × 3 folds × 20 điểm**, trên **60 ngày decision**; folds 2025 Q4, 2026 Q2, 2026 Q3. Có 225 cột OHLCV và 432 cột alpha/sentiment/missingness; missing sentiment chưa được xác minh không trở thành bằng chứng sentiment hợp lệ.
- [x] Chạy đủ baseline số trên bank v3: CASH, always-LONG cycles, train-majority, momentum 20, logistic OHLCV, logistic cùng thông tin thị trường dạng số, factor-only vote và continuous hold price-only. Có **3.780 prediction records/216 daily ledgers** cho 27 cặp mã/fold; **166 UP/374 DOWN** trên 540 units. Imputation/standardisation, C/threshold dùng train/validation theo thời gian và purge label overlap. Bằng chứng: [report](outputs/revision/r1_common_numeric_v3/report.json), [classification/regimes](outputs/revision/r1_common_numeric_v3/classification.json), [model selection](outputs/revision/r1_common_numeric_v3/models.json), [summary/ledger metrics](outputs/revision/r1_common_numeric_v3/summary.csv).
- [x] Có metrics LONG rate, turnover, exposure, số lệnh, net return và daily-close drawdown cho baseline số. Ledger hiện dùng fractional shares/cash tái sử dụng ngay; continuous hold là comparator giá, **chưa xác nhận total return, corporate actions hoặc khả năng thực thi/settlement**. Không dùng kết quả này để đóng R15.
- [x] Có runner cũ với request/response archive, checkpoint, source/runtime hashes, retry/quota guard và prompt guard; đã dùng API thật. Năng lực này là nền để sửa đường chạy mới, **chưa phải pool 5 org hoặc runner theo ngân sách rút gọn**.
- [x] Đã sửa abstract/highlights/introduction/methods/results/conclusion và [response R1 nháp](revision/response_to_reviewers.md), bảo toàn manuscript gốc trong [archive](revision/manuscript_original.zip). [Hai PDF và manifest bản nháp](outputs/revision/r1_manuscript_v1/manifest.json) có 42 trang/bản; locators đã ghi: highlights trang vật lý 2, abstract 3, §5.5 trang 20–21, Tables 7–8 trang 23, Tables 10–11 trang 25, conclusion trang 28. Bản nháp này dùng audit/numeric ban đầu, **chưa chứa bảng Full trên common bank v3 hoặc kết quả kế hoạch mới**.

**Checkpoint thực tế của study cũ — không tính vào 102 cặp test mới**

| Chỉ báo tại lần đối soát | Giá trị và cách diễn giải |
|---|---|
| Run đang được kiểm kê | [r1_common_run_v3](outputs/revision/r1_common_run_v3/run_manifest.json); cùng bank v3 ở trên |
| API attempts đã ghi | **117** request files: **71 response + 46 error**; đây không phải 117 quyết định |
| Decision checkpoints | **23 calibration/e2e, 0 test**; không đổi role calibration thành test hoặc gán sang profile mới |
| Completion | Chưa có `inference_complete.json` hoặc `analysis_manifest.json`; chưa có Full head-to-head |
| Output của status CLI | Vẫn báo `n_decisions_required=8100`, cap cũ 30.000 và `blocked_daily_vision_quota`; các giá trị này thuộc protocol/receipt cũ, không phải ngân sách mới |
| Trạng thái tiến trình | Không suy worker đang chạy/đã dừng từ receipt lịch sử: không có `worker_status.json` hiện hành; lượt cập nhật tài liệu này không khởi động, dừng hoặc resume worker |

Đếm checkpoint bằng `scripts/status_revision_common_study.py` và đối chiếu file thực; đây là kiểm kê tiến độ, chưa replay/xác nhận khoa học 23 calibration mới. Receipt dừng ban đầu v3 ghi 1 attempt/0 prediction chỉ phản ánh thời điểm trước khi resume. Baseline report vẫn ghi thiếu `full` và `full_train_exposure_control`; trong hai variant thiếu này, theo mục 0 **Full là bắt buộc**, còn control matched-Full exposure là tùy claim, không bắt quay lại 540 calibration calls.

**Triển khai hiện hành — đối soát sau kiểm thử offline 02/11/2026**

Bank mới [r1_72h_bank_v2](outputs/revision/r1_72h_bank_v2/manifest.json): 102 units/sáu block/12 ngày, 2.856 assets; audit 180 records/177 URL-text identities, rescore 154 excerpts đủ date/URL consistency bằng tokenizer/model pinned. Publication/content PIT và chất lượng tài chính vẫn chưa được chứng nhận độc lập; không đóng R7. Gate factorial đủ 18 points, panel upstream 9.

[Numeric mới](outputs/revision/r1_72h_bank_v2/numeric/report.json): 714 predictions/408 daily ledgers, 420 hash nguồn/outputs PASS. Reuse price/factor fits/predictions ở 27 scope cũ đã kiểm OHLCV; refit matched inputs do sentiment thay đổi và các block lịch sử mới.

[Run manifest](outputs/revision/r1_72h_run_v2/run_manifest.json) khóa 50 hash source/input và runtime trước API. Allocation theo tải unit, không theo treatment/outcome; dự kiến 97/98/96/96/97 decisions kể smoke theo org, nằm trong ba cửa sổ cap 40. Mỗi process có charts/temp/client/checkpoint riêng, SQLite shared caps, cache node/response thật, không fallback model/CASH.

**Checks lượt chuẩn bị ban đầu (lịch sử):** 14 test profile mới PASS (design/PIT/donor/state isolation, global/org/rolling caps, native agents+parser với fake calls trong temp, raw replay/tamper/recovery, format repair, bootstrap/panel/export); 8 four-way +14 baseline-leakage/daily-ledger +3 token-budget tests PASS. Biên dịch đúng sáu file Python mới PASS. Tổng bao phủ 39 tests; không chạy full suite/E2E vì không sửa engine/agents/runtime dependencies hiện có. Model-card check HTTP và rescore CPU local có thực hiện; **tại thời điểm chuẩn bị ban đầu chưa gọi Groq**; sau đó tác giả đã chạy smoke/inference và dữ liệu hiện hành được đối soát ở cuối kế hoạch. Bản numeric development/failed-export giữ cục bộ, không phát hành; release numeric cuối có source hash hiện hành khớp.

Timebox runner/tích hợp vượt 90 phút do bổ sung checkpoint từng node/SDK replay, xử lý SQLite lock trên Windows và QA pipeline numeric/export; tổng chuẩn bị offline khoảng T0+4,5h, vẫn trước gate T0+12h. Smoke/inference do tác giả chọn tự chạy terminal; không dùng fake-model tests thay evidence.

**Lệnh cần tác giả chạy bằng API thật** (cùng repo root, năm key đã có, không cần đổi setup):

```powershell
py -3.13 -X utf8 scripts/run_revision_72h.py smoke --all
py -3.13 -X utf8 scripts/run_revision_72h.py run --all
```

Năm smoke đã hoàn tất, hiện chỉ cần resume bằng lệnh run. Pool tự dùng key còn quota; khi không còn key khả dụng cho các job còn lại, đợi provider reset rồi chạy lại run; bộ đếm giữ nguyên và không còn cap nội bộ. Lệnh theo dõi/verify/analyze không gọi API nằm trong [runbook](revision/r1_72h_runbook.md). Mốc deadline lịch sử giữ trong manifest gốc nhưng không còn tự dừng theo yêu cầu tác giả. Original manifest/checkpoints không sửa; operational amendment khóa code/policy mới riêng.

**Các bước R1 đã hoàn thành — chốt 03/11/2026**

- [x] **R1.1 — Chuyển profile (D1-07/08/11/12):** đã tạo protocol/bank/run riêng, pool/limiter/caps/shards/node checkpoints và tests ở trên. Rà process cũ không thấy worker revision; không sửa protocol cũ, không stage usage/calls của tác giả. Network smoke năm org đã PASS; không gọi lại smoke sau thay đổi policy quota.
- [x] **R1.2 — Freeze input và smoke (D1-04/05/06/13/14):** Input audit/scoring/gate, feature/donor contracts, runtime freeze và một cặp smoke thật mỗi org đã PASS; org identity do tác giả xác nhận, quota cả ngày vẫn không được suy từ smoke. Chỉ reuse giá/features/baseline khi hash và contract còn khớp. Nếu sửa scorer/input, tạo release numeric tương ứng trên cùng 102 units trước so sánh. Chốt missing/failure policy, model/prompt, lịch, contrasts và ngân sách trước evaluation; smoke nằm ngoài evaluation và trong trần chung.
- [x] **R1.3 — Chạy paired study:** đủ **474/474 research decisions**, gồm 204 main, 234 panel bổ sung và 36 upstream bổ sung; **102/102 cặp B/AS**, panel 18 units ×5 variants ×3 repeats và upstream 9 units ×2 variants ×3 realizations đầy đủ, không tính lặp realization nền. Năm smoke PASS/10 decisions nằm ngoài evaluation. Có inference/shard completion markers và replay 484 decisions thật PASS.
- [x] **R1.4 — Hoàn thiện bảng Full–baseline:** [analysis](outputs/revision/r1_72h_run_v2/analysis/manifest.json) có 918 predictions, 189 metric groups, common support/input/label hashes, confusion/per-class/pooled/macro/symbol/block/regime/cohorts, 510 economic accounts/ledgers và gross diagnostic tách biệt. [Bảng theo mã](outputs/revision/r1_manuscript_v2/baseline_by_symbol.csv) đủ 90 dòng, [hai lớp mọi nhóm](outputs/revision/r1_manuscript_v2/per_class_all_groups.csv) 378 dòng. Bootstrap đồng bộ sáu block/10.000 lần seed 20261102; Full–Base BA +0,55 pp, descriptive CI [−5,91;+8,00]. Panel dispersion chỉ áp dụng 18/9 units, không gán sang 102 points.
- [x] **R1.5 — Hoàn thiện claim và hồ sơ:** hai front matters, sections 01/03/05/06/07/08 và appendix đã cập nhật số liệu thật, giữ kết quả âm; [response](revision/response_to_reviewers.md) và [matrix](revision/reviewer_matrix.csv) ghi rõ phạm vi đóng. [Main PDF](outputs/revision/r1_manuscript_v2/main.pdf) **51 trang**, [submission PDF](outputs/revision/r1_manuscript_v2/main_submit.pdf) **52 trang**; locators vật lý cùng nhau: §5.6 p21–22, §6.1 p23–25, Tables 7–10 p24–25, conclusion p32, Appendix A/Tables A.18–A.23 p33–38. Logistic dùng cùng bank thông tin dạng số, không gọi là cùng chart/text/tri thức LLM; không fit exposure control bằng test và không giữ claim cần Full-exposure calibration.

**Nghiệm thu R1:** đã có Full thật/baselines cùng snapshot/target/lịch/cost, metrics đầy đủ, artifact kiểm chứng, bản thảo cuối và response. **PASS** replay 484 real decisions, 3.752 hash nguồn/đầu ra analysis+numeric (source numeric trước amendment đối soát đúng archive), 918 predictions/189 groups/510 ledger returns và order counts, 32 hash đầu ra legacy/manuscript gốc. Exporter mới `scripts/finalize_revision_r1.py --check` tái tạo đúng 7 TeX files/2 CSV; scoped compile đúng file này PASS. Hai PDF build sạch undefined references/citations/multiply-defined labels; đã render và kiểm bố cục, bảng/locators. Chỉ còn overfull 2,61pt ở footer elsarticle đã kiểm không clipping. PDF page anchors đã sửa thành duy nhất, pixel/layout các trang đã QA giữ nguyên. Diff whitespace áp dụng source/tài liệu, cho phép CRLF của raw artifacts và loại trừ hai log compiler nguyên byte (native log có khoảng trắng cuối dòng). Không chạy full unit/E2E/leakage suites: code inference, target, input, paired protocol và runtime đã khóa giữ nguyên; chỉ thêm exporter offline, kiểm trực tiếp toàn bộ outputs chịu ảnh hưởng. Không gọi API hoặc rerun baseline.

Verifier legacy cũ `verify_revision_r1.py` so cả `plan.md` lịch sử với file kế hoạch hiện hành nên không được dùng làm gate nguồn hiện hành: nó dừng ở hash `plan.md` đã thay qua các task trước. Lượt này kiểm độc lập 4 output legacy +28 nguồn manuscript trong ZIP nguyên bản; không ghi verifier cũ là PASS hay sửa receipt lịch sử.

Original run/analysis manifests và artifacts giữ nguyên byte, kể cả status `pending_manuscript` tại lúc generator chạy; [manifest bản thảo R1](outputs/revision/r1_manuscript_v2/manifest.json) ghi nghiệm thu sau cùng và giữ archive source bản nháp trước sửa. **R1 đóng theo kết quả historical exploratory và claim đã thu hẹp**, không xác nhận snapshot submission, immutable hosted weights, publication/content PIT, sentiment domain validity hoặc settlement. Không tự đóng R2–R18 hay đảm bảo accept. Các lần nghiệm thu/biên dịch cũ bên dưới là lịch sử, không ghi là đã chạy lại.

**Kết quả đối soát lịch sử ở lượt cập nhật R1 trước đó:** `scripts/verify_revision_common_study.py` **PASS**: ba bank/feature receipts, hai numeric releases v2/v3, ba receipt dừng và replay calibration chẩn đoán v2; không phải nghiệm thu Full/R1. Đối soát thêm **4 hash đầu ra legacy**, **45 hash nguồn/đầu ra manuscript**, số đếm, 19 liên kết được thêm, UTF-8/cấu trúc Markdown và diff whitespace: **PASS**. Chỉ sửa tài liệu nên không chạy compileall, unit, E2E hoặc leakage suite, không gọi API và không ghi lại artifacts nghiên cứu. Các kết quả test/PDF QA trước đây được viện dẫn như lịch sử, không ghi là đã chạy lại.

<a id="r2-progress"></a>

### R2 — Mẫu ngắn, một regime và phụ thuộc chéo [P1]

**Trạng thái 03/11/2026: đã xử lý R2 trong phạm vi historical exploratory của kế hoạch.** Đã tái dùng toàn bộ LLM evidence R1 thật, bổ sung audit độc lập về thời gian, regime, missingness, preprocessing, phụ thuộc và contamination; không gọi lại API, không fit lại classifier, không chọn mẫu/checkpoint theo kết quả. Khoảng thời gian dài hơn không được diễn giải thành mẫu độc lập lớn hơn hoặc prospective validity.

- [x] **Snapshot và maturity:** tái dùng [snapshot 2020–30/09/2026](outputs/revision/r1_prices_v1/manifest.json), chín mã ×1.681 raw sessions; giữ nguyên 673 prefix rows BHN bị loại khỏi view phân tích sau OHLC lỗi. Audit [data_manifest](outputs/revision/r2_panel_v1/data_manifest.json) và [folds.csv](outputs/revision/r2_panel_v1/folds.csv) xác minh warm-up, label exits và đúng sáu block 2023–2026. Mọi test label trưởng thành chậm nhất **28/09/2026**; không tải lại giá hoặc sửa dữ liệu.
- [x] **Universe và giới hạn suy rộng:** giữ chín mã purposive/survivor-biased; listing/delisting, point-in-time constituent và suspension registry ghi `unknown`/`unverified`, không tự xác nhận. BHN chỉ đủ ba block mới. Không nhận claim market-wide/VN30/VN100 hoặc cho zero-volume là xác nhận suspension. Đây là giới hạn đã công bố, không phải đã xây dựng một universe PIT đầy đủ.
- [x] **Folds và fit chronology:** đủ **51 symbol–fold scopes**, 32–318 train/18–21 validation samples, ít nhất 600 history sessions tại first train cutoff; label exit strictly trước split kế tiếp. Tái tính imputer/scaler từ đúng train+validation đã trưởng thành khớp cả hai stored logistic fits ở mọi scope. C/threshold theo validation procedure đã khóa; classifier không refit. Selector LLM vẫn là adaptive causal 600-session policy đã khóa, không được gọi là nested factor-discovery validation; R10 còn riêng.
- [x] **Regimes và exposure:** [regime_labels.csv](outputs/revision/r2_panel_v1/regime_labels.csv) đủ 102 units: **33 bull/35 bear/34 sideways**, là context từng mã theo SMA60, không gán năm thành market regime. Volatility 20 phiên và turnover proxy Close×Volume có threshold median fit chỉ trên train của mã/fold; đây là **strata mô tả bổ sung sau inference**, không phải preregistered strategy hoặc order-book liquidity. [Metrics](outputs/revision/r2_panel_v1/stratified_metrics.json) và [exposure](outputs/revision/r2_panel_v1/exposure_by_regime.csv) có support/ngày/classes và exposure kiểm từ ledger trong ba target sessions/unit; không gọi đó là calendar portfolio exposure.
- [x] **Phụ thuộc và missing calendar:** [prediction_panel.csv](outputs/revision/r2_panel_v1/prediction_panel.csv) join theo **ngày ×mã ×variant**, đủ **972 slots =918 predictions +54 missing**, tương ứng 108 date-symbol slots/102 eligible/6 BHN excluded; NA không biến thành CASH. Có **12 decision dates/36 target-calendar dates/306 symbol-target sessions**, không giả định là độc lập. [Dependence](outputs/revision/r2_panel_v1/dependence.json) bootstrap toàn block giữ các mã/ngày/variants/mask đồng bộ, 10.000 lần seed 20261102; main intervals khớp nguyên bản R1. Cohort 8 mã/6 block N=96 và 9 mã/3 block N=54 báo riêng, không gộp; leave-one-block-out Full–Base BA từ **−2,20 đến +2,75 pp**. Không dùng Wilcoxon giữa mã làm bằng chứng suy rộng; ba/sáu cluster chỉ hỗ trợ khoảng mô tả.
- [x] **Contamination:** [contamination.json](outputs/revision/r2_panel_v1/contamination.json) ghi **0 units/labels sau protocol freeze 02/11/2026**. Archive có hai model names và 41 fingerprint strings nhưng không có authenticated served-weight revision/training exclusion. Không suy release date hoặc fingerprint là bằng chứng không memorise; cả text và vision đều có nguy cơ. Không đổi lịch sử thành confirmatory/clean holdout.
- [x] **Prospective scope và hồ sơ:** không giữ claim prospective validity, market-wide superiority hay mẫu đã đủ power. Prospective holdout là bước nghiên cứu độc lập về sau, cần protocol/model identity khóa trước các outcome mới. Đã cập nhật sections 05/06/07, conclusion, front matters và appendix; [response R2](revision/response_to_reviewers.md) giữ nguyên nguyên văn reviewer và [matrix](revision/reviewer_matrix.csv) ghi đúng giới hạn. [Release bản thảo R2](outputs/revision/r2_manuscript_v1/manifest.json) khóa source/PDF/locators sau QA; release R1 giữ nguyên, nguồn R1 trước sửa được đối soát qua `sources.zip` của chính release đó.

**Bằng chứng và nghiệm thu:** [R2 release](outputs/revision/r2_panel_v1/manifest.json) gồm policy, data/universe manifest, folds, calendar mask, regimes, target sessions, metrics/exposure, block/cohort/leave-one-out sensitivities, contamination và bốn bảng TeX. Bảy tests mới về future mutation, train-only thresholds, missing/degenerate history, purge, calendar join và correlated-symbol resampling PASS; scoped compile ba file Python mới PASS. Replay 484 real R1 decisions và 3.752 source/output hashes PASS; 51 preprocessing audits PASS; return/order của 510 ledgers và target-session exposure của 459 classifier-ledgers được đối soát. `py -3.13 -X utf8 scripts/analyze_revision_r2.py --check` tái lập release/bảng offline; không dùng unit tests thay actual LLM evidence. Hai PDF R1+R2 đã build/render QA: **53/54 trang vật lý**, §5.7 p23, §6.2 p27, Appendix A.1/Table A.24 p39 và Tables A.25–A.27 p40; không undefined references/citations hoặc duplicate labels/page anchors, không body/table overflow. Không chạy full suite/E2E vì không đổi engine, inference, target, input, dependency hoặc runtime đã khóa. R2 không đóng R3–R18 hoặc chứng nhận submission-ready; nhỏ mẫu, survivorship và unknown contamination vẫn được công bố như giới hạn thực chất.


<a id="r3-progress"></a>

### R3 — Biến thiên giữa các lần chạy [P1]

**Trạng thái 03/11/2026: đã xử lý trên hai panel lịch sử đã khóa; không nhận full-grid variance decomposition hoặc lợi thế ổn định.** Shared upstream không khử biến thiên Decision. Spread giữa các bảng legacy còn lẫn khác lịch và thiếu provenance, nên không được dùng làm matched repeated runs.

- [x] Audit cấu hình default W=45, zscore_tanh, weights=null/default: cutoff/asset/data/actual-prompt hashes, frozen source hashes, model aliases, SDK temperature/caps, provider key-slot, timestamp, retry/error, fallback và call order. Exact model-run Git commit và immutable served weights ghi unknown/unverified. Inventory 24 dòng/12 artifacts legacy ghi hai họ lịch/endpoints cho mỗi FPT/VCB/VNM; không suy cùng input từ tên default.
- [x] Tái lập **18 units × B/A/S/AS/P ×3 Decision executions** trên upstream cố định (6 UP/12 DOWN, tám mã, năm ngày, ba block) và **9 units ×B/AS ×3 upstream realizations** (2 UP/7 DOWN, chín mã, ba ngày, ba block). Chỉ một unit chồng lấp, dùng lại hai B/AS r0 calls theo thiết kế; union **322 unique Decision executions, 132 node records, 88 successful vision requests**. Broad 102-unit one-pass giữ riêng.
- [x] Mỗi execution có successful raw request ID/context/parent riêng; 90 fixed-upstream unit–variant groups giữ cùng actual prompt hash qua ba calls. Không copy final response để tạo repeat; dự đoán giống nhau với ID riêng vẫn hợp lệ. Kiểm cả missing/duplicate identity và upstream pairing.
- [x] **98/98** planned within-job orders khớp timestamp thực. r1/r2 xoay variant order; r0 B/AS dùng main pair sớm hơn A/S/P. Quota pauses/provider routing/time còn gây nhiễu, không nhận counterbalance hoàn chỉnh. Toàn bộ **756 attempts/734 successes/22 errors** được giữ. Declared T=0 được client langchain-groq 1.1.2 đổi thành **1e-8** ở mọi attempt metadata; không phải wire capture/weight attestation hoặc bảo đảm xác định. Không có hosted seed được cung cấp trong caller đã khóa.
- [x] Báo per-execution và mean/sample-SD/median/range/conditional descriptive CI cho accuracy, BA, MCC, macro-F1, LONG rate, return và paired contrasts; disagreement theo 108 cutoff–variant groups. Decision Full–Base BA: **mean +5,56 pp, SD 14,63 pp, median +4,17, range [−8,33,+20,83], interval [−9,56,+23,08]**. Full BA 30,56% (SD 10,49 pp), mean account return −1,544% (SD 0,679 pp), disagreement 22,22%. Upstream Full BA 97,62% (SD 4,12 pp), Full–Base +7,14 pp (SD 0), interval [0,+14,29]; panel này khác support, không suy rộng hoặc trừ SD để tách variance components.
- [x] **10.000 joint whole-block × paired execution-index resamples**, seed 20261102; mean per-execution statistic, không coi 3N là thị trường độc lập. Procedure CI thêm sau inference, không nhận preregistered precision. BA có 9.612/10.000 draws defined ở Decision và 6.986/10.000 ở upstream; còn lại undefined, không điền zero. Mọi run được giữ, không chọn best seed/checkpoint, không dùng ensemble thay main result. Return là mean của 13/9 symbol–block accounts mỗi execution, chỉ panel cycles, không phải pooled portfolio.

**Bằng chứng và nghiệm thu:** [R3 analysis](outputs/revision/r3_repeats_v1/manifest.json) khóa 16 artifacts, gồm config/request/lineage/order/legacy inventory, per-run metrics, 249 account ledgers, report và bốn bảng TeX. [Bản thảo R1–R3](outputs/revision/r3_manuscript_v1/manifest.json): hai PDF 58 trang, §5.8 p24, §6.3 pp28–29, L4 p34, conclusion p35; Appendix A.2 pp43–45 trong main và pp42–44 trong submit; Tables A.28–A.31 tương ứng pp44–45/43–44. [Response R3](revision/response_to_reviewers.md) giữ nguyên comment và trả lời từng giới hạn. R1/R2 release cũ giữ nguyên byte, nguồn lịch sử đối chiếu qua source ZIP.

**Kiểm tra đúng phạm vi:** 10 targeted tests mới và compile ba file Python mới PASS; replay 484 real decisions, 3.752 source/output hashes, 918 numerical predictions, 189 metric groups và 510 daily ledgers PASS. `py -3.13 -X utf8 scripts/analyze_revision_r3.py --check` tái tạo byte-identical 16 artifacts/bốn TeX ở tiến trình khác, PYTHONHASHSEED=17. Build/render QA toàn bộ hai PDF PASS; không undefined references/citations/duplicate anchors, chỉ footer elsarticle 2,61pt kế thừa không clipping. Không gọi API, đổi engine/inference/target/input/dependency hoặc chạy lại full suite/E2E; test mới bao phủ thống kê và provenance đọc offline.

**Giới hạn đóng mục:** Ba executions/ba block mỗi panel chưa đủ precision/power; upstream panel không crossed 3×3 và chỉ có Decision repeat 0 trên upstream mới nên không định danh từng thành phần phương sai. Không lặp toàn bộ legacy hyperparameter sweeps; kết luận ổn định/tối ưu dựa vào các bảng đó đã rút lại, R6 vẫn riêng. Không xác thực immutable weights, clean prospective sample hoặc superiority. R4 được nghiệm thu riêng bên dưới; R5–R18 chưa đóng.

<a id="r4-progress"></a>

### R4 — Không tách alpha, sentiment và ảnh hưởng cấu trúc prompt [P0/P1]

**Trạng thái 03/11/2026: đã đóng trong phạm vi repaired historical exploratory panel.** Đủ **270/270 fresh Decision executions, 274 attempts, 270 successes, 4 JSON/schema rejections được retry; 0 vision calls mới**. Bản thảo/response đã có kết quả thật, không còn chờ API. Việc đóng R4 xác nhận thực hiện control/audit và thu hẹp claim; không xác nhận giá trị thông tin alpha độc lập, sentiment benefit hoặc profitability.

- [x] Dùng **Base reports**, Full−Base là bundle/report contrast. Đổi `Synergy` legacy thành **best-single gap**; interaction chuẩn là `M(AS)−M(A)−M(S)+M(B)`. Không lấy provenance chưa xác minh của legacy ablation để suy attribution.
- [x] Completed factorial B/A/S/AS/P ×3 trên đúng **18 units, tám mã, năm ngày, ba block, 6 UP/12 DOWN** mỗi execution. Khóa sẵn cùng unit list, source/runtime pins và seven-contrast BA family trước calls mới. Tất cả units có >=3 local-scored articles; availability gate không thay PIT/news-domain validation. Không gọi đây là prospective confirmation.
- [x] **162/162 actual alpha-bearing successful prompts có đủ năm numeric rows**, được parse độc lập và so từng value/signal/IC/accuracy/score với treatment hoặc donor đã khóa. **54/54** groups giữ shared upstream text/parent/rules; A/AS cùng alpha, S/AS/P cùng sentiment; A không có sentiment section, S không có alpha section. AS/P chỉ khác alpha content, giữ headings/names/schema/placement/sentiment/budget; độ dài 3.244–4.228 ký tự, không nhận exact token-length matching.
- [x] Donor whole-rank-vector thuộc train purged, label exit trước validation; mapping seed 20261102 + unit-ID hash tái lập, deep availability masks/schema đúng. **84/90 donor rank slots khác tên factor**: control perturb cả values/signals/skill fields theo rank, không bảo toàn covariance theo named factor hoặc cô lập từng scalar. Không dùng outer-test/future values để shuffle hoặc dựng baseline huấn luyện.
- [x] Tất cả **270 successes là responses mới, ID riêng**, không copy từ R1/R3 hoặc old compressed panel, không model/CASH fallback. **54/54 within-group successful-call orders** khớp jobs đã khóa. Bốn `json_validate_failed` đều ở S jobs được giữ nguyên, không lấy failed generations làm prediction; phân bố điều kiện theo eventual schema-valid outputs. Client metadata của cả 274 attempts giữ model `openai/gpt-oss-20b`, SDK T=1e-8 và output cap 2.048; immutable served weights vẫn unverified.
- [x] Báo per-execution, mean/sample-SD/median/range, per-class support/recall, equal-symbol macro với denominator thực, paired contrasts, LONG exposure và 195 panel-account executions/daily ledgers. **Full BA 44,44% (SD 2,41 pp), accuracy 53,70%, MCC −0,121; mean net return −0,670%**. CASH references: BA 50%, accuracy 66,67%, return 0. **AS−P BA +6,94 pp (SD 4,81; pointwise interval [2,08;12,82]), joint seven-contrast envelope [−6,55;20,44]**. Interaction +6,94 (SD 6,36; pointwise [−8,97;16,67]). Mean AS−B +15,28; A−B +11,11; AS−S +18,06; S−B −2,78; AS−A +4,17 pp. Không diễn giải pointwise interval dương thành significance sau multiplicity.
- [x] **10.000 joint block/run draws**, seed 20261102; 9.612 jointly finite BA/388 undefined draws. Joint max-deviation radius **13,49 pp**, không nhận calibrated simultaneous coverage/FWER. Không coi repeats là market observations độc lập, không chọn best-run/seed/checkpoint hoặc ensemble. **UP recall của cả 15 variant–execution groups đều 16,67%**; Full/P DOWN recall 72,22%/58,33%, LONG 24,07%/33,33%. BA gap chỉ đến từ ít DOWN errors trên support này, không thêm đúng profitable-UP cycles hay alpha độc lập với exposure.
- [x] Giữ nguyên old compressed artifacts: 264 alpha-bearing prompts của study 474 decisions vẫn thiếu rows, không relabel thành corrected input. AS−P/interaction cũ −2,78 pp giữ riêng trong bảng lịch sử; không pool hai study hoặc coi thay đổi trước/sau là causal repair effect. **R4 đóng bằng actual corrected evidence + disclosure/claim scope, không bằng code/test hoặc rút claim đơn thuần.**

**Bằng chứng đã khóa:** [native analysis](outputs/revision/r4_value_run_v1/analysis/manifest.json) tái lập bốn outputs metrics/lineage/accounts/daily; [R4 final audit](outputs/revision/r4_final_v1/manifest.json) khóa 11 artifacts (274-attempt inventory, actual paired-content/order checks, 15 per-execution rows, class/macro distributions, class/exposure contrasts, disagreement và ba TeX). [Bank trước inference](outputs/revision/r4_value_bank_v1/manifest.json), [audit cũ](outputs/revision/r4_audit_v1/manifest.json) và [bản thảo pending lịch sử](outputs/revision/r4_manuscript_v1/manifest.json) giữ nguyên byte. Toàn bộ raw requests/responses/errors/digests và 270 checkpoints được Git bảo toàn; quota DB/locks/usage tiếp tục ignore.

**Bản thảo/response cuối:** [release R4 v2](outputs/revision/r4_manuscript_v2/manifest.json), main/submit **62/63 trang vật lý**. Cả hai: abstract p3, §5.9 pp25–26, §6.4 p31, limitations pp36–37, conclusion pp38–39, Appendix A.3 pp48–49. Table A.32 giữ old compressed contrasts; A.33 corrected metrics p48, A.34 corrected contrasts/joint envelope và A.35 actual-call audit p49. [Response R4](revision/response_to_reviewers.md) giữ nguyên comment và giải thích giới hạn của thông tin, exposure, order, covariance và finite-draw intervals. R5–R18 không được đóng bởi task này.

**Kiểm tra áp dụng:** bốn targeted tests mới và compile hai file finalizer/test mới PASS, kiểm scalar actual độc lập với prompt hash, sai model/caps/context, thiếu/duplicate rows. Mười hai tests của runner/PIT/interaction/resume đã PASS ở mốc trước, source/runtime 576 pins giữ nguyên nên viện dẫn, không ghi là chạy lại. Actual-data verification replay **270** successful responses, **274** attempts, **54** paired groups/orders và **195** account executions; fresh-process PYTHONHASHSEED=17 tái lập native analysis + 11 final artifacts/ba TeX byte-identical. Hai PDF build/render QA PASS; không undefined citations/references/duplicate anchors hoặc table/body overflow; chỉ footer elsarticle 2,61pt kế thừa. Không gọi API trong lượt chốt, không sửa frozen engine/inference/input/target hoặc chạy full suite/E2E.

**Lệnh đối soát offline** (không gọi network hoặc sinh prediction):

```powershell
py -3.13 -X utf8 scripts/run_revision_r4.py verify
py -3.13 -X utf8 scripts/run_revision_r4.py analyze
py -3.13 -X utf8 scripts/finalize_revision_r4.py --check
```

Không cần chạy thêm API để nghiệm thu phạm vi R4 này. Lệnh `run --all` là lệnh lịch sử, không phải bước tiếp theo. Thông báo mã thoát 3 cũ không tự chứng minh quota: đã quan sát năm worker cũ giữ locks và tiếp tục tăng tiến độ trong khi một lượt chạy trùng bị chặn; không xóa lock/checkpoint hoặc suy cap nội bộ từ số 130.

### R5 — Khoảng tin cậy, Newey–West, N và annualisation [P0]

**Vấn đề:** bootstrap 20 điểm/block 5 rất ít thông tin; percentile CI khó tin khi chỉ một discordant pair. McNemar và bootstrap khác giả định nên bất đồng không tự chứng minh code sai, nhưng không được chọn kết quả thuận lợi. `N=20` ở hàng Mean gây hiểu sai; account Sharpe/Sortino dùng sai tần suất.

**D2-05 hoàn tất ngày 03/11/2026:** [đặc tả](revision/r5_statistics_policy.json),
[audit](revision/audit_report.md#thống-kê-phụ-thuộc--d2-05),
[release](outputs/revision/dependent_statistics_v1/manifest.json). Tái tính
discordance/exact diagnostic và NW statistic/SE/lag/p cho chín mã legacy;
pooled support =180, 53 dates, không có common-date rectangle đủ chín mã nên
không tạo pooled HAC từ 180 rows. Fixed-universe date-level HAC mới báo đủ
lags 0/1/2 cho common-eight 96 units/12 dates và recent-nine 54/sáu dates.
CBB lengths 1/2/3 giữ toàn cross-section/mask/variants, đủ 144 contrasts/metric
rows; primary R1/R2 và block×repeat R3/R4 giữ nguyên. Null audit có ba DGP
đã khóa, mỗi DGP 1.000 panels, 1.000 draws/length; BA coverage length 1 chỉ
85,00%/63,85%/41,34% conditional trên defined panels. Không coi là calibrated
95% CI, không chọn length theo outcome. Có 13 outputs/bốn TeX tables đã
build/render QA; 11 tests mới, scoped compile ba Python và hash/reproduction
PASS. Không API hoặc sửa runtime/PIT/prompt/ledger cũ trong D2-05. **R5 còn mở** cho
chốt bản thảo/response sau D2-06 bên dưới; phương pháp bổ sung là
post-inference sensitivity, không gọi confirmatory.

**D2-06 hoàn tất ngày 03/11/2026:** [release](outputs/revision/account_annualisation_v1/manifest.json),
[audit](revision/audit_report.md#annualisation-và-risk-contract--d2-06).
Engine/robustness/ablation mới chỉ dùng `sqrt(252/S)` khi có bar indices
chứng minh daily cycles đều, liền nhau S=L (S=3 → sqrt(84)); thiếu provenance,
lịch không đều/gap/khung chưa hỗ trợ hoặc mẫu số suy biến trả null/NA.
Giữ SD population/downside negative-subset SD legacy, risk-free/MAR=0 và
drawdown cycle-end có nhãn; không đổi P&L/fees/labels/parser (AST đối chiếu PASS).
Đối soát nguyên 510 daily ledgers, gồm CASH gaps và initial anchor, tính risk
với sqrt(252); 268 Sharpe/234 Sortino defined, không dựng ledger mới. Tỷ lệ
legacy 18 accounts xuất riêng với giả định S=L=3, không xác thực snapshot
lịch sử: giá hiện tại có mismatch và BHN calendar spans/steps không đều.
68 scoped tests PASS, compile chín Python thay đổi, source/runtime/hash replay
PASS; bảng mới đã build/render QA. Nguồn trước sửa giữ trong ZIP, artifacts
cũ giữ nguyên. R5 vẫn mở cho manuscript/response/PDF locators; không nhận
gate cũ bao phủ runtime mới hoặc claim profitability từ risk ratio.

**Việc cần làm**

- [ ] Với benchmark cũ, trình bày discordant counts, exact McNemar như chẩn đoán với giả định độc lập cần nêu; bỏ tuyên bố significant chung từ Wilcoxon 9 mã và CI nhỏ mẫu. Tăng số bootstrap đơn thuần không chữa thiếu dữ liệu.
- [ ] Với mẫu mở rộng, chọn trước panel block bootstrap (ví dụ stationary/circular block) và kiểm tra block-length sensitivity, coverage bằng mô phỏng dưới null có tự tương quan và yếu tố thị trường. Dùng cùng estimand/giả định cho test và CI.
- [ ] Báo Newey–West statistic, SE, lag, p-value. Chuỗi chênh lệch theo ngày sau khi tổng hợp cross-section với trọng số cố định là một sensitivity hữu ích; HAC riêng từng mã không tự giải quyết pooled cross-sectional dependence.
- [ ] Các p-value Newey–West **đã lưu** lần lượt BHN/CMG/FPT/HVN/MBB/MWG/VCB/VJC/VNM: 0,2605 / 0,3161 / 0,0963 / 0,0765 / 0,0884 / 0,0493 / 0,0954 / 1,0000 / 0,4494. Đây là giá trị legacy cần tái tính/ghi assumptions, không chọn riêng MWG để tuyên bố significance; còn multiplicity.
- [ ] Bảng summary ghi `N_total=180`, `n_symbols=9`, `N_per_symbol=20`, thêm số ngày/cụm thời gian. Mean accuracy và pooled accuracy chỉ trùng ở đây vì kích thước bằng nhau.
- [ ] Với equally spaced cycle returns dùng annualisation `sqrt(252/S)`; khi S=L=3 là `sqrt(84)`. Nếu dùng daily mark-to-market equity thì `sqrt(252)` trên **daily returns**. Chu kỳ không đều phải dùng lịch thật; không thay mù mọi `252` thành `252/L`.
- [ ] Sửa cả Sortino và các report/tests liên quan; ghi risk-free convention, SD convention, cash intervals. Khi không giao dịch/không có variance, ratio phải NA hoặc quy ước rõ, không ngầm xem 0 là hiệu quả đầu tư.
- [ ] Báo 1–7 LONG trades/mã trong benchmark cũ; bỏ Sharpe khỏi luận điểm chính hoặc để phụ lục mô tả. MDD tính ở cycle-end bỏ sót sụt giảm trong thời gian giữ: bổ sung daily MTM hoặc đổi tên thành cycle-end drawdown.

**Đầu ra:** statistic specification, bảng thống kê tái tính, kiểm thử frequency/null/dependence. **Đạt khi:** cùng dữ liệu cho cùng metric, số tổng hợp có mẫu số rõ, không còn annualisation sai. **Sửa tại:** `core/backtest_engine.py`, `utils/statistical_tests.py`, tests account/significance và sections 03/05/06.

### R6 — Trùng branch và checkpoint [P0 — làm trước thực nghiệm lớn]

**Vấn đề:** đã xác nhận trùng toàn bộ chuỗi 20 prediction ở hai cặp FPT được nêu trong mục 1.2. Summary khớp arithmetic không chứng minh branch đã chạy đúng.

**D1-16 hoàn tất audit ngày 03/11/2026:** [báo cáo](revision/audit_report.md),
[release/hash](outputs/revision/legacy_lineage_v1/manifest.json): 47 artifacts,
30 point JSON, 66 streams/1.320 variant rows; 573 cặp cùng mã có 20 cặp trùng
prediction đủ 20 cutoff. Trong đó 12 cặp phù hợp thiết kế shared control nhưng
thiếu parent ID; tám cặp còn lại gồm sáu treatment/control FPT quy về hai control,
một Full/Full FPT và một Full/Full VNM. Confidence/RR/time không trùng hoàn toàn;
root cause, actual request/flags/prompt/model revision và execution commit legacy
vẫn `unknown`/`unverified`. Cả 31 JSON có nội dung bằng bản Git sớm nhất còn giữ;
hash byte hiện tại và Git blob được ghi riêng, không chuẩn hóa artifacts cũ.
Đã khảo sát save/load, deepcopy, variant mapping và sáu source blobs lịch sử.
**R6 vẫn mở** cho phản hồi/đối chiếu nghiệm thu comment; bảng legacy đã giới hạn
traceability, không dùng làm attribution confirmatory. R4 corrected là evidence
mới riêng, không xác thực ngược legacy. D2-13 vẫn pending.
Kiểm tra mới: 9 tests auditor, compile hai Python mới và hash/tái lập release
PASS; không chạy lại toàn suite/E2E/leakage vì runtime/PIT/prompt không đổi.

**Việc cần làm**

- [x] Hash và đối soát artifacts legacy hiện có trên cả chín mã, từng row/field và metadata/Git history; missing equity/request timestamp/execution commit ghi null/unknown, không điền từ cấu hình hiện tại. Xem release D1-16.
- [x] Khảo sát save/load, deepcopy, flags, checkpoint key và variant mapping ở source lịch sử đã khóa; không có log/request liên kết trong ba cây legacy, conversion ngoài Git chưa thể xác minh.
- [x] Tách 12 cặp intended shared control khỏi tám cặp trùng chưa xác minh; legacy thiếu parent ID nên không chứng nhận reuse hợp lệ chỉ từ source hoặc prediction giống nhau.
- [ ] Thiết kế cache key bao gồm data-content hash, full config, prompt template, branch, code/schema version, model revision, cutoff và repeat; từ chối resume thiếu hoặc khác hash. Chỉ so `data_start/data_end` không đủ để khóa snapshot.
- [ ] Archive actual rendered prompt, reports đầu vào, raw response và parsed decision cho từng call; replay parser/metrics độc lập.
- [ ] Nếu không đủ bằng chứng xác nhận legacy branches, ghi rõ không thể xác minh, bỏ bảng 9 khỏi confirmatory evidence và chạy lại toàn bộ ablation từ đầu. Không sửa label thủ công hoặc viện lý do “trùng ngẫu nhiên” khi thiếu log.

**Đầu ra:** báo cáo audit/checkpoint lineage, regression tests chống nhầm nhánh, ablation mới. **Đạt khi:** từng prediction truy được đến đúng input/request/response và flags; các duplication được giải thích hoặc kết quả bị thay thế minh bạch. **Sửa tại:** engine, hai runners, JSON schema và tests pairing/ablation/robustness.

### R7 — Sentiment count, provenance, thiếu tin và domain shift [P0/P1]

**Việc cần làm**

- [ ] Kiểm toán từng cache và đối chiếu với snapshot dùng cho submission: raw records, unique articles trong từng mã/toàn corpus, dated/undated, scored/unscored, duplicates, availability, scorer V/L/U. Không cộng một bài dùng ở nhiều cutoff thành nhiều unique articles.
- [ ] Ghi sự khác nhau giữa “180 cache records” và “180 test points”. Chín cache cục bộ hiện có tổng 180 records, 180 parseable dates, V/L/U=`0/0/180`; số unique xuyên mã và provenance thời điểm tạo còn phải audit.
- [ ] Chạy lại script từ raw cache, kiểm tra invariant V+L+U=total và phần trăm=count/total. Sửa paths: script đang trông `backtest_result/` và `ESWA/`, trong khi tài liệu khảo sát nằm `outputs/backtest_result/` và `paper/`. Tạo CSV/TeX cùng một nguồn, không sửa số bằng tay.
- [ ] Dùng đúng bộ lọc runtime `available_at` với timezone và date-only next-day rule, score validity, 90-day window và ngưỡng **>=3**. Audit hiện đếm ngày publication và ngưỡng >=8, chưa đo đúng availability của S_decay.
- [ ] Chẩn đoán theo date-only trên cache hiện tại cho số cutoff có <3 bài: BHN **16/20**, CMG **20/20**, FPT **17/20**, MWG **11/20**; các mã còn lại 0/20. Với date-only next-day rule, MWG thành 12/20. Đây là count diagnostic, không phải chứng nhận pipeline đã sử dụng đúng dữ liệu/scorer; phải tính lại trên production loader và score-valid records.
- [ ] Báo riêng target sentiment availability và related-company availability, số peer hợp lệ, coverage và cơ chế chọn peer tại cutoff. Khóa peer list hoặc ghi lại cách chọn có point-in-time data; không để LLM dùng quan hệ công ty biết từ tương lai.
- [ ] Không gán missing=neutral. Khi sentiment unavailable, so sánh nhánh S với missing-context placebo để tách prompt/noise; không dùng FPT Sentiment-only làm bằng chứng sentiment có thông tin nếu tin không có.
- [ ] Trích dẫn riêng ViSoBERT gốc và model card 5CD-AI. Model card mô tả dữ liệu social/comment/review, không xác nhận chất lượng trên tin tài chính Việt Nam [S3–S4].
- [ ] Tạo tập tin tài chính gán nhãn độc lập, ngân sách ban đầu **200 bài** phân tầng mã/thời kỳ, ít nhất hai người với hướng dẫn rõ; adjudication, agreement và CI cho macro-F1/per-class recall. Nếu class support thiếu, ghi uncertainty hoặc mở rộng trước kết luận, không chọn theo prediction để tăng F1. Không fine-tune mới trong gói tối thiểu; 300–500 bài/domain adaptation là mở rộng khi cần claim chất lượng sentiment mạnh hơn. Không coi 200 là chứng minh đủ power.
- [ ] Freeze model/tokenizer revision, truncation policy, mapping labels, fallback; rescore dữ liệu mới dưới provenance mới. Không sửa legacy-unknown thành ViSoBERT bằng suy đoán.

**Đầu ra:** article-level manifest, cutoff coverage table, domain evaluation và response giải thích 8180/180. **Đạt khi:** không còn count/percentage mâu thuẫn; sentiment claim bị giới hạn theo coverage và validation. **Sửa tại:** cache loader, sentiment agent/audit, tests coverage/leakage/ViSoBERT, sections 02/03/04/05 và phụ lục.

### R8 — Novelty, QuantAgent và ý nghĩa knowledge fusion [P1, attribution P0]

**Việc cần làm**

- [ ] Lập bảng provenance cấp component/file/prompt với commit upstream đã dùng: Indicator/Pattern/Trend/Decision, shared state, chart utilities, trendline fitting; phân loại reused, modified, new và mô tả thay đổi thực chất.
- [ ] Khôi phục đầy đủ MIT license/copyright notice của phần tái sử dụng, ghi attribution trong code/README/bài. Repository upstream hiện redirect sang QuantHarness [S1]; dùng commit/version lịch sử thích hợp, không diff tùy tiện với HEAD mới.
- [ ] Không nhận vision chart analysis và kiến trúc bốn agent gốc là novelty của bài này. Đóng góp mới có thể bảo vệ là alpha registry/selector, sentiment có cutoff, protocol đánh giá và cơ chế fusion nếu thực sự có.
- [ ] Sửa “high-frequency trading”, “K-line” gây hiểu nhầm thành daily-bar candlestick analysis và horizon cụ thể. Thay prompt phải version và chạy lại những kết quả chịu ảnh hưởng.
- [ ] Mô tả trung thực phiên bản hiện tại là prompt-level/late fusion của text reports; structured state và prompt concatenation chưa tự chứng minh có knowledge reasoning mới.
- [ ] Gói tối thiểu bổ sung evidence IDs/source/cutoff/missingness và mô tả trung thực prompt-level fusion; không phát triển mới Bayesian/conflict-resolution architecture trên critical path. Hướng schema có calibrated reliability, learned weighting và conflict resolution là mở rộng nghiên cứu nếu bằng chứng hiện tại chưa tạo đóng góp đủ rõ cho KBS.
- [ ] B là QuantAgent-derived comparator theo các sửa đổi đã khai báo; dùng B/A/S/AS/P để đánh giá đóng góp gia tăng. Single LLM, learned fusion và ablation vision chỉ bắt buộc nếu giữ claim kiến trúc/fusion/vision vượt trội; khi đó đăng ký budget bổ sung trước run. Không nhận novelty ở các thành phần tái sử dụng; báo cost/token/latency thực của gói tối thiểu.

**Đầu ra:** contribution/provenance matrix, đặc tả fusion, fusion ablation. **Đạt khi:** hoặc cơ chế mới có bằng chứng giá trị, hoặc thu hẹp claim thành empirical protocol/benchmark và đánh giá lại fit KBS. Đổi tên thành “knowledge fusion” không đủ đóng comment. **Sửa tại:** agents/state/decision, README/notice, sections 01/02/04/06/08.

### R9 — Reproducibility và model identity [P0]

**Việc cần làm**

- [ ] Lưu OHLCV snapshot cùng vendor, timestamp, timezone, đơn vị giá, điều chỉnh corporate actions, trading calendar và SHA-256. Không fetch live trong đường chạy reproduction.
- [ ] Đóng gói cache tin, publication/availability, URL/content hash, scorer/tokenizer revision và processed scores. Nếu bản quyền ngăn phát hành full text, cung cấp phần được phép, truy cập kiểm soát và hướng dẫn tái tạo; không gọi release là fully reproducible khi đầu vào thiết yếu không truy cập được.
- [ ] Pin dependency và Python/OS/native TA-Lib bằng lockfile hoặc môi trường tái tạo. `latest` và `vnstock>=3.0.0` không phải pin.
- [ ] Mọi call lưu prompt nguyên bản tiếng Việt, bản report sau condensation, chart bytes/hash, raw response, structured parse, request ID, timestamp, effective model/parameters, retry/error/fallback; không chỉ final decision. Prompt tiếng Anh rút gọn trong phụ lục không thay thế artifact thực tế.
- [ ] Xác nhận model ID với catalogue chính thức; hiện `qwen/qwen3.8-27b` hợp lệ [S2]. Phân biệt ID được cấu hình, ID response trả về và immutable revision. Nếu nhà cung cấp không cung cấp revision, nói rõ không bảo đảm exact hosted replay; bổ sung model open-weight pinned nếu khả thi.
- [ ] Công bố hai mức: offline replay tái tạo metrics từ archived outputs; rerun inference đo phân bố kết quả. Unit tests/mock LLM không chứng minh đã tái tạo empirical results.
- [ ] Dựng release có version, README lệnh chạy, data/artifact manifests, checksums, bảng/hình sinh tự động; archive trên Zenodo hoặc nơi cấp persistent identifier. Không điền DOI giả hoặc nói “provided” khi chưa truy cập được.
- [ ] Kiểm tra fresh checkout ở môi trường sạch, không phụ thuộc ignored caches hoặc đường dẫn máy tác giả. Phân biệt bằng chứng của phiên bản code hiện tại với log của run tháng 9.

**Đầu ra:** reproducibility package và persistent ID thực, fresh-environment reproduction report. **Đạt khi:** người khác tái lập được mọi con số trong bài từ artifact đã phát hành và hiểu rõ giới hạn rerun LLM. **Sửa tại:** loaders, runners, requirements/lock, docs, availability statements.

### R10 — Alpha selection, multiplicity và translation [P1]

**Việc cần làm**

- [ ] Xuất bảng đủ 101 WorldQuant IDs: 80 retained, 21 excluded, lý do từng loại; thêm 5 custom =85. Với retained, ghi công thức gốc, công thức triển khai, operator/window/warm-up/tie policy, NaN handling, rank/time-series surrogate, industry/neutralisation thay thế và code pointer.
- [ ] Kiểm tra registry thật, không suy từ lời mô tả “80+5”. Thêm numerical fixtures cho các translation quan trọng; kiểm tra dùng volume thật hay range proxy và tính nhất quán đơn vị. Báo tỷ lệ proxy/missing, làm sensitivity loại các trường hợp đó.
- [ ] Inner time-ordered calibration xác định normalization, IC sign, ranking và hyperparameters; outer test đánh giá toàn bộ selector không nhìn tương lai. Purge label overlap và yêu cầu label đã trưởng thành. Không dùng outer outcomes để chọn lại top-5 hoặc sign.
- [ ] Báo selection frequency trên **eligible cutoffs**, eligibility count, IC sign stability, Jaccard overlap/rank stability qua cutoff, IC decay theo horizon, autocorrelation/turnover theo mã/regime.
- [ ] So sánh dynamic top-5 với tập 5 factor cố định định trước, random eligible top-5 với nhiều seed, simple momentum/factor vote và không sign-flip **bằng numeric policy trên cùng bank** trước, không gọi LLM cho từng candidate. Random factor selection khác placebo đổi giá trị factor ở R4. Không giữ claim dynamic selection vượt fixed/random trong toàn pipeline LLM trong gói 72 giờ; numeric comparison chỉ hỗ trợ policy số.
- [ ] Chọn trước multiplicity procedure phù hợp họ giả thuyết: Holm cho các contrast xác nhận; FDR cho khám phá factor; nếu claim tìm được strategy/factor vượt trội sau search thì dùng Reality Check/SPA/DSR thích hợp cùng toàn bộ candidate/trial returns. Không áp DSR lên accuracy hoặc gọi IC ranking là significance.
- [ ] Giữ nhật ký toàn bộ trial/config đã thử. Không bỏ multiplicity sang Future Work nếu vẫn nhận claim phát hiện factor hiệu quả.

**Đầu ra:** factor translation registry, selection diagnostics và fixed/random controls. **Đạt khi:** reviewer kiểm tra được 21 exclusions và mọi retained expression, đồng thời thấy lợi ích selector ngoài selection optimism. **Sửa tại:** `core/alpha_compare.py`, `utils/alpha_selector.py`, `agents/alpha_agent.py`, tests alpha, sections 03/04/06 và phụ lục.

### R11 — Label và trường actual_prev_close [P2, contract P0]

- [x] Thay label log Close-to-Close trong Table B.10 bằng đúng net next-Open-to-target-Close của Eq. 4; đồng bộ equation, pseudocode, prompt, alpha target và JSON schema.
- [x] Không rename toàn bộ legacy `actual_prev_close` một cách máy móc: ở benchmark FPT đã thấy nó bằng entry_open, nhưng checkpoint khác có giá trị khác entry_open. Tách rõ `decision_close`, `entry_open`, `exit_close`, `gross_return`, `net_return`, `label`; migration phải dựa vào snapshot hoặc đánh dấu legacy ambiguous.
- [x] Tạo kiểm thử với overnight gap lớn, zero net return, chi phí hai chiều, holiday và incomplete horizon; kiểm tra label từ đúng giá.

**Đạt khi:** mọi field có một nghĩa duy nhất và không sửa lịch sử bằng suy đoán. **Sửa tại:** state schema, engine/serializers, phụ lục B, section 03.

**Đối soát 03/11/2026:** D2-08 hoàn tất; R11 addressed với giới hạn provenance tường minh. [Audit](outputs/revision/target_contract_v1/manifest.json): 102 units/918 labels, 600 legacy records và 760 archived Decision attempts. Canonical outcomes chỉ ghi sau inference; legacy decision Close null. [Bản thảo mới](outputs/revision/target_manuscript_v1/manifest.json): Appendix B.1 physical pp50–51, Tables C.36/C.37 physical pp55–56 trong cả hai PDF. 96 scoped tests, compile chín file, hash/runtime replay và PDF QA PASS; original snapshot/served-model provenance vẫn unknown. Các phần R5/R15 còn lại không được đóng thay.

### R12 — Indicator rules và thuật ngữ [P2]

- [x] Table 1 dùng RSI bullish `<=30` hoặc `55<=RSI<70`; bearish `>=70` hoặc `30<RSI<=45`; vùng `45<RSI<55` xét xu hướng ba giá trị hợp lệ (bằng nhau/thiếu dữ liệu mới neutral). Ghi thứ tự ưu tiên như code, kiểm tra các biên 30/45/55/70 và crossover của các indicator khác.
- [x] Đổi “five momentum and volatility oscillators” thành mô tả momentum/trend phù hợp.
- [x] Xác định Bollinger Bands và ADX có được tính, truyền state hay dùng ở quyết định không; phân biệt schema fields có sẵn với năm indicator thực tế dùng cho consensus. Sửa Table B.10 hoặc mô tả supplementary features cho đúng.

**Đạt khi:** table, appendix, prompt và deterministic classifier cùng rule. **Sửa tại:** indicator agent, static utilities, sections 04 và phụ lục B/D.

### R13 — Alpha_4 và tên custom/proprietary [P2]

- [x] Giải thích đúng `(%B−0.5)×VolZ5`: VolZ5 âm đảo dấu tín hiệu, VolZ5=0 triệt tiêu; `abs(VolZ)>0` không đồng nghĩa volume expansion.
- [x] Ưu tiên giữ công thức để replication và sửa diễn giải thành tương tác signed volume. Nếu mục tiêu thật sự là confirmation, định nghĩa phiên bản mới, ví dụ gate `max(VolZ5,0)`, đăng ký trước và đánh giá riêng; không sửa công thức rồi giữ kết quả cũ.
- [x] Đổi proprietary thành custom ở toàn bài; giải thích “order flow” chỉ là price/volume proxy nếu không có dữ liệu giao dịch/lệnh thực.

**Đạt khi:** có ví dụ/test VolZ âm/0/dương và không mâu thuẫn tên–cơ chế–kết quả. **Sửa tại:** alpha registry/agent nếu đổi formula, section 04, phụ lục C.

**Đối soát 03/11/2026 — D2-09:** R12/R13 addressed trong phạm vi mô tả implementation và boundary evidence. [Audit](outputs/revision/indicator_alpha_rules_v1/manifest.json): 67 indicator cases, 5 consensus, 11 prototype Alpha_4 và 3 registry oracles (86 synthetic cases); 7 tests/compile hai Python mới/hash replay PASS. Chín runtime/prompt sources nguyên byte R4; công thức, predictions và market inputs không đổi. [Bản thảo mới](outputs/revision/indicator_alpha_manuscript_v1/manifest.json): Table 1 physical main p14/submit p13; custom prose/Table 2 p15 và Figure 1 p16 cả hai; Alpha_4 main pp58–59/submit pp57–58; Table D.38 main p59/submit p58; Appendix E main pp59–60/submit pp58–59. Schema C.36 main p56/submit p55. Hai PDF render/QA PASS. Các locators cũ vẫn thuộc frozen releases tương ứng; mapping hiện hành trong manifest. Không suy synthetic examples thành alpha/inference evidence hoặc đóng thay R10/R14/R15.

### R14 — Quy ước màu chart [P2; rerun có điều kiện]

- [x] Đối chiếu style, hàm vẽ, chart archive và prompt; hiện code đặt up xanh/down đỏ nhưng comment và prose ngược nghĩa.
- [x] Tạo chart fixture có các nến tăng/giảm biết trước, kiểm tra màu và legend. Nêu candle color dựa trên Close vs Open; màu bảng điện thường dựa trên giá tham chiếu, không đồng nhất hai khái niệm.
- [ ] Nếu chỉ sai chú thích/prose, sửa và cung cấp fixture; nếu ảnh hoặc prompt lịch sử thực sự đảo màu, đánh giá ảnh hưởng, version renderer/prompt và chạy lại mọi branch liên quan với shared charts.

**Đạt khi:** có bằng chứng hình ảnh kiểm tra đúng convention và provenance. **Sửa tại:** `utils/color_style.py`, chart utilities, prompts, section 04.4.

**Chart rerun — T0 = 2026-11-03T10:25:06.441703+00:00**. Đây là mốc freeze run riêng sau sửa legend; không thay T0 hoặc receipts R1/R4 lịch sử. Tiếp tục provider-only trên năm org Free theo policy đã duyệt, không cap nội bộ/không mua quota. Audit tái lập 214 PNG nguyên byte/pixel, đối soát 270 actual image requests và phát hiện 107 Trend legends gắn sai artists. Renderer `static_legend_handles_v2`, prompt `trend_blue_en_v2`; R14/D2-10 còn partial cho đến khi paired rerun và phân tích đủ.

**Checkpoint 03/11/2026 sau khi pool dừng:** [audit](outputs/revision/chart_convention_v1/manifest.json) và [bản thảo](outputs/revision/chart_manuscript_v1/manifest.json) đã có; 78 scoped tests/compile chín Python PASS. [R1 run mới](outputs/revision/chart_r1_run_v1/run_manifest.json): 15 calls cho đủ 10/10 smoke decisions; đủ 120 research Trend groups, **138/474 research Decision** (148 cả smoke), raw/lineage replay PASS. **284 attempts mới**, không tính 140 Pattern attempts được copy/replay nguyên byte. [R4 bank mới](outputs/revision/chart_r4_bank_v1/manifest.json) khóa 90 native-derived prompts/270 jobs từ ba reports actual, không cần prediction giả: **6/270 checkpoints** từ 10 attempts, raw replay PASS. Workers dừng với checkpoint khi không còn provider phù hợp/quota TPD; chưa phân tích hiệu năng trên run dở. Còn ít nhất 600 Decision successes, cộng retries nếu có. `R14` và `D2-10` giữ **partial**, không coi unit tests hay 214 image replays là empirical closure. `scripts/run_chart_rerun.py run --all` và `run-r4 --all` dùng tuần tự khi quota khả dụng; source/runtime phải khớp freeze. Source ZIP 110 files nằm trong R1 runtime_history để bảo toàn phiên bản thực nghiệm khi code về sau thay đổi. Không mua quota, không khôi phục cap/deadline nội bộ.

### R15 — Settlement, price limits và L=3 [P1]

**D2-07 hoàn tất execution sensitivities ngày 03/11/2026:**
[policy](revision/r15_execution_policy.json),
[audit](revision/audit_report.md#execution-sensitivities--d2-07),
[release](outputs/revision/execution_sensitivity_v1/manifest.json).
Khóa 12 scenarios sau inference, giữ 918 predictions/102 units, L=3 và labels
gốc; đủ 6.120 scenario-account executions từ 510 accounts. Reference tái lập
510 economics records; pending cash, on-demand/auto advance, cost/sell-charge,
no-fill/delay proxy, lot/cap và combined bounds báo riêng. Daily state tách
settled/pending cash, settled/unsettled shares; execution events có phase và
timezone, clock_time null, không dùng 07:00 bar timestamp làm fill time.
Mẫu chính cách 57 observed sessions nên pending/on-demand không đổi return;
không suy thành bằng chứng fast-reuse settlement an toàn. Full mean return
vẫn âm ở mọi scenario có fills (lower/higher cost: −0,707%/−1,279%; combined
−1,154%); all-missed=CASH 0%, không phải predictive improvement. Có 8.420
events/394.560 daily rows, không xem là market observations mới. 27 tests
scoped execution/PIT/daily-ledger, compile ba Python mới, hash/reproduction
và standalone table render QA PASS. Engine/ledgers/runtime cũ nguyên byte;
không gọi API. **R15 vẫn mở**: calendar/venue/date rules, queues/price limits,
Volume units/broker rates/taxes, corporate actions, horizon L=5/10 và final
manuscript/response/PDF locators chưa được chứng nhận bằng task này.

- [ ] Dùng trading calendar, entry ở open e và exit ở close e+2 cho L=3. Kiểm tra khả năng bán buổi chiều T+2 theo quy định có hiệu lực trong từng giai đoạn; thông báo VSD năm 2022 hỗ trợ mốc đó [S8], nhưng nghiên cứu nhiều năm phải xử lý các chế độ trước/sau thay đổi.
- [ ] Giải thích L=3 là horizon được chọn phù hợp với giả định settlement ở giai đoạn tương ứng, không có nghĩa “ba ngày lịch” hoặc horizon tối ưu. Đăng ký sensitivity L=3/5/10 với lịch S và mẫu so sánh hợp lệ; L ngắn hơn cần tách task dự báo khỏi giao dịch có thể thực hiện.
- [ ] Ghi quy tắc venue/date cho trần-sàn, auction/open, suspended/zero-volume, lot size, taxes/fees và fill feasibility. Không mặc định khớp ở open chỉ vì có OHLCV; daily bar không đủ chứng minh hàng chờ có thanh khoản.
- [ ] Chạy conservative no-fill/delayed-fill scenario cho limit-locked sessions, slippage/cost sensitivity và participation cap có căn cứ. Không suy ra partial fills chính xác từ daily OHLCV.
- [ ] Bổ sung cash settlement: bán cuối e+2 không tự đảm bảo tiền settled có thể dùng ngay open chu kỳ kế tiếp. Mô hình pending cash hoặc cơ chế ứng trước với phí; `S>=L` chỉ tránh overlap cổ phiếu, không tự giải quyết settlement tiền.
- [ ] Timestamp `07:00:00` trong JSON daily bar không được coi là thời điểm khớp market open/close; tách bar timestamp và execution event time, timezone rõ ràng.

**Đạt khi:** ledger, labels và cash/stock availability nhất quán; assumptions còn lý tưởng hóa được báo như bounds. **Sửa tại:** execution/ledger, tests account/calendar, sections 03/05/07.

### R16 — References thiếu, sai nội dung hoặc DOI không khớp [P0]

**Đã xác minh thêm:** đánh số references giữa reviewer, PDF và TeX không giống nhau, nên audit theo BibTeX key/title/DOI, không xóa mù các mục [14], [21], [22], [23].

| BibTeX key | Kết quả đối chiếu | Xử lý |
|---|---|---|
| `kang2021singleasset` | DOI `10.1016/j.eswa.2020.114236` thuộc bài meta-evaluation của Wang, Ma, Liu, không phải single-stock alpha [S6a] | Loại citation hiện tại; tìm nguồn thực sự hỗ trợ hoặc bỏ claim |
| `vo2019efficiency` | DOI `10.3390/jrfm12020100` thuộc bài financial structure/economic growth ở Pakistan [S6b] | Không giữ như bằng chứng market efficiency Việt Nam |
| `truong2020technical` | DOI `10.21511/imfi.17(4).2020.02` thuộc bài cash level/GCC của Alshammari [S6c] | Thay nguồn phù hợp hoặc bỏ claim |
| `pham2021herding` | Crossref lookup DOI hiện trả 404; chưa xác minh được title–author–venue | Tra publisher/author record; nếu không xác minh được thì loại, không tự tạo DOI |
| `tradingagents2024` | arXiv nêu Yijia Xiao, Edward Sun, Di Luo, Wei Wang [S5] | Sửa author và version/year tương ứng bản thực sự trích |
| `deng2016rltrading` | Metadata volume 28(3), pp.653–664 là March 2017 [S7] | Sửa publication year; không suy năm từ chuỗi DOI |
| `tsantekidis2017candlestick` | Title là limit-order-book forecasting | Sửa câu dẫn sang LOB hoặc thay bằng nghiên cứu candlestick thực |

- [ ] Cite WorldQuant/101 Formulaic Alphas ở đúng đoạn giới thiệu và formula translation; entry BibTeX có sẵn không đồng nghĩa citation xuất hiện đúng chỗ.
- [ ] Cite ViSoBERT ở phương pháp/NLP và model card 5CD-AI riêng; cập nhật venue EMNLP/DOI theo ACL.
- [ ] Thêm nguồn White’s Reality Check nếu giữ lời nhắc/phương pháp; xác minh title, year, DOI từ publisher trước khi thêm.
- [ ] Audit **toàn bộ** references, bao gồm các bài năm 2026: DOI/arXiv resolve được, tác giả/năm/venue đúng, paper thực sự hỗ trợ câu trích dẫn. Không giới hạn ở bốn số reviewer nêu.
- [ ] Tạo `reference_audit.csv`: key, cited claim, metadata nguồn chính thức, verified URL, status, action; check uncited/undefined keys sau build.

**Đạt khi:** không còn tài liệu không xác minh được hoặc DOI của bài khác, không còn claim thiếu bằng chứng. **Sửa tại:** `paper/references.bib`, related work và các đoạn trích dẫn toàn bài.

### R17 — Trình bày, dư thừa và title [P2]

- [ ] Chuyển Flask JSON serialization, endpoint routing, tokenizer loading, installation/retry implementation sang docs; giữ trong bài những chi tiết tác động phương pháp/reproducibility như model revision, token limits, fallback rate và protocol.
- [ ] Gom caveats trùng thành limitations có tham chiếu ngắn, tránh lặp claim “significant” hoặc “auditable” khi chưa có bằng chứng.
- [ ] Sửa double periods ở paragraph headings, dash, opening quotations ở section 4.3, tiếng Anh và tên thuật ngữ.
- [ ] Title dự kiến nếu kết quả hỗ trợ: **Evaluating Quantitative Evidence in Multi-Agent Decision Support for Vietnamese Equities**. Chốt title sau kết quả; không dùng title để né việc bổ sung evidence.
- [ ] Một nguồn scientific content cho main và submission; build clean, kiểm tra figures/captions/table totals/equation numbers/refs trên PDF. Đồng bộ graphical abstract và highlights với kết luận.
- [ ] Kiểm tra riêng `main_submit.tex`: options cho itemize có package hỗ trợ tương ứng, macros liên kết, anonymity và disclosure theo yêu cầu tạp chí; không cho rằng PDF cũ chứng minh source hiện tại build được.

**Đạt khi:** bản PDF mới đúng source/version, không lỗi bố cục/references và không claim vượt bằng chứng. **Sửa tại:** toàn bộ `paper/`, repository docs.

### R18 — Tên tác giả và metadata [P2]

- [ ] Lập author master record: họ/tên chuẩn do tác giả xác nhận, thứ tự, ORCID, affiliation, corresponding author/email và CRediT.
- [ ] Đồng bộ title page, main/submission TeX, PDF metadata, cover letter, response letter và submission system; đặc biệt Thanh-Tam Do Thi/Do Thi Thanh-Tam và Van-Tang Nguyen/Tang-Van Nguyen.
- [ ] Kiểm tra ORCID cả các khối đang comment: hai file hiện có ORCID khác nhau cho Phuong-Thai Nguyen. Không suy tên chuẩn hoặc ORCID chỉ từ trật tự tên Việt.

**Đạt khi:** các tác giả xác nhận metadata duy nhất và bản submission dùng đúng master record. Đây là thông tin cần từ nhóm tác giả, không chặn các công việc audit độc lập.

## 4. Thiết kế thực nghiệm thống nhất trước khi triển khai

### 4.1. Câu hỏi nghiên cứu và estimand

1. Alpha thật có tăng predictive skill so với base, placebo và factor-only model không, khi giữ sentiment và upstream cố định?
2. Sentiment có thêm thông tin khi có đủ tin hợp lệ và classifier được kiểm tra trong domain không?
3. Alpha/sentiment đóng góp gì khi giữ nguyên kiến trúc prompt-level fusion? So sánh một cơ chế fusion mới với single LLM/learned fusion chỉ thuộc nhánh mở rộng khi nhận claim đó.
4. Những lợi ích đó bền qua folds/regimes/repeats và tạo giá trị sau phí trên ledger khả thi đến mức nào?

Chọn **BA là primary predictive metric**; MCC, per-class precision/recall, raw accuracy là secondary. Net return, daily MTM drawdown, exposure và trade count là economic metrics riêng. Chốt mức cải thiện có ý nghĩa thực tế trước final test bằng power/precision simulation, không lấy lift 13,9 pp cũ làm giả định chắc chắn.

Primary contrasts đề xuất: A−B; AS−S; true alpha−placebo tương ứng; Full−baseline non-LLM mạnh nhất **đã chọn bằng validation**. Áp family-wise control cho tập contrast này. Không chọn baseline mạnh nhất bằng final-test outcome rồi diễn giải p-value như đã đăng ký trước.

### 4.2. Ma trận thực nghiệm trong 72 giờ

| Thành phần | Phạm vi | Bằng chứng |
|---|---|---|
| Numeric baselines | Cùng 102 units và evaluation số rộng hơn | Không gọi LLM; input/target/cost/support khớp |
| Paired broad | B/AS, 102 units, một run | 204 decisions; tám mã chung/sáu block và chín mã/ba fold báo riêng |
| Attribution/repeats | 18 units ×3 repeats; 5-way hoặc 3-way đã chọn trước run | 234 hoặc 126 decisions thêm; shared upstream, không fake repeats |
| Upstream sensitivity | B/AS, 9 units ×3 realizations | Thêm 36 decisions/36 vision; không suy variance toàn grid |
| Selection/execution | Fixed/random numeric controls, registry, cost/fill/calendar | Offline; bỏ claim đòi fixed/random LLM hoặc execution certification chưa có |

Giữ W=45, L=3, model pair đã khóa; không Cartesian sweep, không đổi model/cap giữa study. Sentiment gate, failure policy, lịch, contrast, cap và source hashes phải khóa trước evaluation. Hoàn thành chạy không tự đóng comment.

### 4.3. Data và run contract

Mỗi observation có khóa `(dataset_version, symbol, decision_timestamp, horizon, fold, run_id, repeat_id, variant)`; mỗi artifact có content hash và parent IDs. Lưu các loại sau:

- Data snapshot: prices, trading calendar, adjustment/action log, news records, available_at và scorer provenance.
- Feature snapshot: indicator values, eligible alpha set, fitted transforms/orientations, scores/top-5, sentiment availability và related-company context.
- Upstream snapshot: numeric payloads, chart bytes/hash, actual reports, verifier flags, provider/model/token metadata.
- Decision record: final input messages đã gửi, raw output, parse result, structured evidence, timing/retries/errors và flags của branch.
- Evaluation record: immutable label, expected/actual fills, fees/slippage/tax, settled/pending cash/stock, daily equity, failure policy.

Freeze policy cho API failures và missing data trước run: công bố failure rate theo branch; báo kết quả common-support và sensitivity theo policy xử lý failures. Không loại các ngày khó theo outcome hoặc âm thầm đổi sang fallback model mà vẫn gắn cùng model label.

### 4.4. Inference và quyết định khoa học

- Resample nguyên block ngày với toàn bộ cross-section, variants và paired reports; thêm cấp repeat đúng thiết kế. Primary estimand là hiệu quả trên universe cố định; suy rộng toàn thị trường cần universe/sample design khác.
- Report CI/effect size kèm số ngày, folds, mã và runs. Broad 102-unit paired one-pass không có 3-run SD trên toàn mẫu; SD/CI theo repeats chỉ áp dụng panel 18, upstream sensitivity chỉ panel 9. Phân biệt uncertainty do market sample và do inference stochasticity. Không coi stock, folds chồng lấn hoặc repeats là độc lập tùy tiện. Tập chính khoảng 12 ngày và upstream 3 ngày có uncertainty lớn; số ngày panel attribution phụ thuộc gate đã freeze, không coi số org hoặc repeats làm tăng số regime độc lập.
- Nếu effect biến mất trước CASH, non-LLM hoặc placebo, nêu thẳng. Có thể xây dựng nghiên cứu về điều kiện thất bại/benchmark hoặc cơ chế tốt hơn rồi đánh giá trên holdout mới; không đổi mục tiêu sau hoc và gọi đó là confirmatory success.
- Predictive benefit không đủ để claim profitability; return dương vài mã không đủ để claim portfolio alpha. Kết luận phải khớp loại bằng chứng thực tế.

## 5. Triển khai theo task nhỏ và dependency

Danh sách dưới đây **chỉ còn phần cần thực hiện**. D1-01 (khảo sát) và D1-02 (sửa kế hoạch) đã xong nên được bỏ khỏi bảng chờ; giữ ID các task còn lại để không mất tham chiếu. `S0` là đầu vào đã đối soát ở mục 0.5/R1, không phải một task mới. `pending` có nghĩa là chưa làm phần bổ sung được mô tả, dù nền tảng tái sử dụng đã có.

**Không làm lại trong 72 giờ:**

- Không audit lại 180 điểm từ đầu, tải lại snapshot 9 mã, dựng lại bộ metrics hoặc triển khai lại các baseline đã có; tái dùng releases ở R1 và chỉ tính phần input/fold/contract thay đổi.
- Không viết lại bốn nhánh ablation/shared upstream, archive/retry/prompt guard hoặc daily MTM ledger; chỉ bổ sung tích hợp, placebo, per-org caps, identity mới và checkpoint còn thiếu.
- Không lặp bước sửa bản thảo R1 ban đầu hoặc build lại PDF cũ chỉ để cập nhật checklist; chỉ cập nhật nội dung chịu ảnh hưởng bởi kết quả mới và các comment còn mở.
- Không cấu hình lại năm key, hoàn tất grid 8.100, chạy 540 calibration, thêm Full-exposure control, fixed/random LLM sweep hoặc domain validation có hai người khi chưa có nhân lực. Các phần này đã xong, đã hoãn hoặc không thuộc gói hiện hành; bỏ khỏi critical path.

Trạng thái dùng `pending`, `in_progress`, `done`, `partial`, `blocked`; chỉ `done` khi đủ điều kiện và bằng chứng. Task thường 20–60 phút; runner/tests có thể 60–90 phút. Nếu vượt timebox, ghi nguyên nhân và ảnh hưởng tại dòng task. Khi triển khai sau này, API chạy nền trong lúc làm offline; lượt hiện tại không chạy những task này.

**Ngày 1:** khóa thiết kế, runner, tests/smoke và bắt đầu inference. Nếu T0+12h chưa PASS tests/smoke, không chạy đường chưa kiểm chứng; ghi nguy cơ thiếu evidence.

**Ngày 2:** lô 2 và sửa metric/ledger/labels/registry/provenance/citations. Không thêm sweep/model/training hoặc fixed/random LLM calls.

**Ngày 3:** dừng inference T0+60h, phân tích/bản thảo/response/PDF/package; thiếu job báo incomplete, không kéo dài hoặc điền prediction.

| ID | Task | Dependency | Trạng thái | Bằng chứng hiện tại | Điều kiện hoàn thành |
|---|---|---|---|---|---|
| D1-03 | Chốt manifest 102 điểm từ lịch có sẵn | S0 | done | [102 units/schedule](outputs/revision/r1_72h_bank_v2/manifest.json), purge/BHN exclusions đã test | 54+48 points; purge; BHN exclusion; reuse lịch ba fold hiện có |
| D1-04 | Bổ sung article-level dedup/provenance audit | S0 | done | [article audit](outputs/revision/r1_72h_bank_v2/article_audit.json): 180 records/177 identities; không xác thực PIT content | Unique liên mã, hashes và availability; không lặp source inventory toàn outputs |
| D1-05 | Xác minh mapping rồi rescore local <=90 phút | D1-04 | done | [local scores](outputs/revision/r1_72h_bank_v2/local_scores.json): 154 excerpts, mapping/card/tokenizer/weights pinned; domain validation vẫn mở | Đối chiếu model card, pin tokenizer/mapping; tạo scores mới hoặc báo unavailable |
| D1-06 | Chọn sentiment gate và panel | D1-03/05 | done | Gate factorial, 18 qualified units; panel upstream 9 và donor map đã khóa trước API | 5-way hoặc 3-way khóa trước output |
| D1-07 | Khóa protocol mới | D1-06 | done | [Execution protocol](revision/r1_72h_protocol.json) + bank/runtime/run riêng; không sửa common protocol v3 | Units/variants/repeats/model/caps/failure policy |
| D1-08 | Bổ sung profile runner 72h trên helper hiện có | D1-07 | done | scripts/run_revision_72h.py đủ prepare/assets/freeze/smoke/run/status/analyze/verify/numeric; 474 decisions/714 research calls | Dry-run 474/366; không chạy calibration; không viết lại core engine |
| D1-09 | Tích hợp bốn nhánh có sẵn vào runner mới | D1-08 | done | Reuse ABLATION_CONFIGS, native nodes/parser; variant isolation/shared-parent tests PASS | Archive từng branch; kiểm isolation A/S và same-parent pairing |
| D1-10 | Placebo train-only | D1-09 | done | Seed 20261102, donor trong train purged, cùng schema/mask/headings, tests PASS | Donor/mask/schema hợp lệ, mapping tái lập |
| D1-11 | Năm process/org, isolated shards | D1-08 | done | Năm child process + org locks; charts/temp/shards riêng; load 97/98/96/96/97 kể smoke | Không ghi đè client/chart/temp/checkpoint |
| D1-12 | Mở rộng caps/identity/node resume/status | D1-09/11 | done | Pool provider-only thay caps cũ theo tác giả; lease/OS lock, node/raw replay, 19 profile tests lịch sử PASS | Caps 5 org; identity variant/repeat/realization; tái dùng node/response thành công |
| D1-13 | Test phần thay đổi và caller bị ảnh hưởng | D1-10/12 | done | 14 profile +8 four-way +14 leakage/ledger +3 token-budget PASS; scoped compile PASS | Bổ sung ca mới, chạy đúng phần chịu ảnh hưởng; không lặp toàn suite |
| D1-14 | Smoke thật một cặp/org | D1-13 | done | Năm smoke markers/10 decisions thật đã replay; quota capacity/org identity không được suy đoán | 2 vision+2 Decision/org; xác nhận model/quota/tokens, không sửa key setup |
| D1-15 | Freeze runtime, chạy lô 1 | D1-14 | done | Runtime/amendment giữ nguyên; đã đủ 474/474 research decisions | Source/input hashes cố định; jobs đăng ký |
| D1-16 | Hoàn thiện audit duplication/lineage legacy | S0 | done | [Audit](revision/audit_report.md), [manifest](outputs/revision/legacy_lineage_v1/manifest.json): 47 artifacts/66 streams/573 cặp; 12 intended-control +8 unverified duplicates; 9 tests/compile/hash replay PASS | Audit đủ các nhánh/mã; request/branch root cause unknown được bàn giao rõ, không suy provenance; R6/D2-13 chưa đóng |
| D2-01 | Kiểm lô 1/quota | D1-15 | done | Đã đối soát 384 attempts/8 errors và provider resets; bỏ cap nội bộ theo tác giả | Coverage/failure/shard; không đổi mẫu theo outcome |
| D2-02 | Chạy lô 2/resume | D2-01 | done | Đã resume đủ các jobs, không gọi lại node/response thành công | Không lặp request thành công/repeats giả |
| D2-03 | Tái dùng baseline, bổ sung input/fold cho 102 points | D1-07 | done | [numeric release](outputs/revision/r1_72h_bank_v2/numeric/manifest.json): 714 predictions/408 ledgers/420 hashes PASS | Trích subset còn khớp; refit/recompute chỉ fold, scorer hoặc input đã đổi |
| D2-04 | Bổ sung numeric coverage lịch sử còn thiếu | D2-03 | done | R2 audit đủ 102 LLM units/6 block, common cohorts/mask, regime/exposure; N=540 numeric cũ vẫn riêng | Mở rộng support/regime; không tải lại giá, không gán là LLM evidence |
| D2-05 | Bổ sung NW/bootstrap phụ thuộc và bảng mới | D2-03 | done | [Release](outputs/revision/dependent_statistics_v1/manifest.json): legacy discordance/NW, fixed-universe HAC, 144 CBB rows/18 null rows/bốn bảng; 11 tests/compile/hash replay PASS | Giữ helpers và primary/repeat intervals; denominator/NA/degenerate rõ; không claim calibrated coverage; annualisation chuyển D2-06 |
| D2-06 | Sửa/đối soát annualisation còn lệch | D2-05 | done | [Release](outputs/revision/account_annualisation_v1/manifest.json): cycle frequency/NA contract, 510 stored daily ledgers, 18 conditional legacy accounts; 68 scoped tests/compile/AST/hash replay PASS | Daily/cycle phân biệt; không dựng ledger lại hoặc đoán provenance; manuscript/R5 closure còn riêng |
| D2-07 | Execution sensitivities R15 | D2-06 | done | [Release](outputs/revision/execution_sensitivity_v1/manifest.json): 12 scenarios/6.120 accounts; reference 510 khớp; 27 tests/compile/hash replay/table QA PASS | Pending/advance/cost/no-fill bounds có denominator và state riêng; source predictions/labels nguyên; R15 execution certification/manuscript còn mở |
| D2-08 | Đồng bộ label/schema/bản thảo phần còn lệch | D2-03 | done | [Audit](outputs/revision/target_contract_v1/manifest.json): 102 units/918 labels, 600 legacy records, 760 Decision attempts; 96 tests/compile/hash replay PASS; [hai PDF + sources](outputs/revision/target_manuscript_v1/manifest.json) QA PASS | Canonical outcomes ngoài graph inputs; primary net giữ nguyên; legacy decision Close null; prompt source/request không đổi; R11 addressed với giới hạn provenance |
| D2-09 | Đồng bộ indicator/custom-alpha prose R12/R13 | S0 | done | [Audit](outputs/revision/indicator_alpha_rules_v1/manifest.json): 86 fixtures/7 tests/compile/hash replay PASS; [hai PDF và source](outputs/revision/indicator_alpha_manuscript_v1/manifest.json) QA PASS | RSI/crossover/fallback khớp classifier; supplementary slots khác report thực; Alpha_4 signed-volume giữ nguyên; custom và OHLCV flow proxy rõ; R12/R13 addressed |
| D2-10 | Bổ sung đối chứng chart/prompt R14 | S0 | partial | 214 ảnh legacy tái lập nguyên byte/pixel; 270 actual requests khớp cache; phát hiện/sửa legend handles ở 107 Trend charts; 78 scoped tests PASS | Fixture, code và disclosure đã có; run riêng dùng pool Free provider-only để tái tạo shared Trend/all affected branches; chưa đóng R14 trước empirical rerun |
| D2-11 | Registry/selector R10 | D2-03 | pending | — | Retained/excluded; fixed/random numeric/stability |
| D2-12 | Xuất coverage từ audit/score đã khóa | D1-04/05 | pending | Count diagnostic cũ có sẵn nhưng không thay verified availability | Một nguồn CSV/TeX; missing khác neutral; domain validation còn mở |
| D2-13 | Attribution/novelty R8 | D1-16 | pending | — | Reused/modified/new; MIT; claim phù hợp |
| D2-14 | Hoàn tất reference audit ngoài các lỗi đã biết | S0 | pending | Mục R16 đã xác minh một số DOI/citations sai | Tái dùng đối chiếu đúng; rà phần chưa xác minh và sửa prose/bib |
| D3-01 | Lô 3/retry trước deadline | D2-02 | done | 474 research +10 smoke; 756 attempts/734 responses/22 errors; không thay mẫu theo outcome | Chạy đến đủ jobs hoặc provider pool hết quota; deadline cũ chỉ là lịch sử |
| D3-02 | Khóa result release | D3-01 | done | Inference completion + immutable analysis manifest; 484 raw-decision replay PASS | Raw/parents/completion/failures nhất quán |
| D3-03 | Bảng Full/Base/non-LLM | D3-02/D2-03 | done | 102 common units; Tables 7–9, 918 predictions/510 accounts; R1 closed | Cùng input/target/cost/support |
| D3-04 | Bảng repeats/upstream | D3-02 | done | Panels 18/9 complete, mean/SD/range/disagreement đúng support; Table 10 | Mean/SD/range/disagreement đúng panel |
| D3-05 | Bảng factorial/placebo | D3-02 | done | R4 repaired 270 real decisions/274 attempts; complete value delivery, seven contrasts/interaction và bounded claims đã chốt riêng | Contrasts/support hợp lệ; Full-Base là bundle effect |
| D3-06 | Chi phí hệ thống | D3-02 | done | system_costs.json: 756 attempts, 734 responses, 22 errors, token/latency thật; không suy billing | Tokens/calls/retries/latency/coverage thật |
| D3-07 | Cập nhật bản thảo nháp bằng kết quả mới | D3-03/04/05/06 | partial | Đã cập nhật toàn bộ nội dung R1 bằng release thật; các sửa R2–R18 còn riêng | Chỉ bổ sung/thay phần có bằng chứng mới; giữ kết quả âm |
| D3-08 | Đồng bộ front matter với release cuối | D3-07 | partial | Abstract/highlights/intro/conclusion R1 đồng bộ kết quả âm; metadata/claims comment khác chưa nghiệm thu | Cập nhật số liệu/title/claim chịu ảnh hưởng, không làm lại bản sửa ban đầu |
| D3-09 | Hoàn thiện response từ R1 draft đến đủ R1-R18 | D3-08 +offline audits | partial | Response R1 đã chốt và có locators PDF mới; R2–R18 vẫn pending | Bổ sung R2-R18, cập nhật R1/locators; không nhận thiếu evidence là complete |
| D3-10 | Metadata tác giả R18 | Tác giả xác nhận | pending | — | Không suy tên/ORCID; chưa xác nhận giữ pending |
| D3-11 | Build/QA hai PDF của release mới | D3-09/10 | partial | Release R1 main 51/submission 52 pages đã build/render QA; chưa chứng nhận R18/submission-ready | Chỉ build nguồn đã đổi; kiểm refs/layout/totals/locators mới |
| D3-12 | Mở rộng offline replay/package cho profile mới | D3-02 | partial | R1 offline replay/export/source ZIP/package đã hoàn tất; archive PID/fresh environment của R9 còn riêng | Tái lập bảng mới không API, đủ input; không viết lại verifier lịch sử |
| D3-13 | Chốt tiến độ trong plan.md | D3-11/12 | partial | R1 đã đóng trong plan.md; các comment còn lại giữ nguyên trạng thái | Done/partial/blocked và comment còn mở |
| D3-14 | Commit/merge/bàn giao | Checks đúng phạm vi | partial | Bàn giao R1 trên nhánh task riêng, merge fix và xóa local theo workflow; không push/submit; tổng kế hoạch chưa hoàn tất | Merge fix, xóa nhánh task local; không push/submit |

### 5.1. Kiểm thử và nghiệm thu

- Pairing/state isolation: shared upstream/chart hash; alpha không rò sang S, sentiment không rò sang A.
- Temporal: purge, donor train-only, tin available_at, source/feature reuse; chạy leakage tests đúng đường mới.
- Checkpoint/integrity: identity có variant/repeat/realization; từ chối nguồn/prompt/model khác; raw response/parent bị sửa phải fail; không fallback CASH.
- Quota: TPD stop, retry interval/repair đếm đủ, caps năm org và một request/org; ngắt sau upstream không gọi lại response thành công.
- Metrics: support/pooled/macro/NA, daily/cycle frequency và gaps; smoke thật không thay kiểm chứng khoa học.
- Chỉ compile Python thay đổi và chạy suites liên quan paired/ablation/common-study/token/leakage/significance/account theo phạm vi. Không chạy toàn bộ suite cho mỗi task tài liệu.
- Nhánh task tách từ fix; chỉ stage file thuộc task, Conventional Commit, merge sau checks PASS và xóa nhánh đã merge. Không stage usage/calls của người dùng hoặc sửa artifacts lịch sử.

### 5.2. Giới hạn bàn giao

R1 ưu tiên bảng thật trên 102 paired units; R2/R3 có multi-block/repeats nhưng giới hạn mẫu nhỏ. R4 sentiment chỉ đóng khi gate và evidence đủ; R7 chưa có hai người gán nhãn nên domain validation không được hứa hoàn tất. R8 thu hẹp novelty đúng thực tế. R9/R18 thiếu PID, tác giả xác nhận hoặc route nộp lại phải giữ pending. Bàn giao sau 72h có thể là bản sửa có bằng chứng và danh sách thiếu chính xác, không đánh dấu mọi reviewer đã thỏa để kịp lịch.

## 6. Deliverables cần có sau khi hoàn thành kế hoạch

Các đường dẫn dưới đây là danh mục đầu ra cần có khi hoàn thành; phần đã tồn tại và phạm vi còn thiếu của R1 được ghi trực tiếp tại [tiến độ R1](#r1-progress). Các artifact/manifest/response phục vụ bằng chứng, không thay `plan.md` làm nơi cập nhật tiến độ và không cần tạo file tiến độ riêng.

| Đầu ra | Nội dung / comment được đóng |
|---|---|
| `revision/audit_report.md` | Source versions, metric recomputation, checkpoint duplications, unknowns; R3/R5/R6/R7/R9 |
| `revision/reviewer_matrix.csv` | R1–R18, subrequirement, task, owner, status, evidence artifact, manuscript locator, response |
| `revision/protocol.md` + configs | Frozen hypotheses, baselines, target, folds, regimes, repeats, inference, failure/stop policy |
| `revision/data_manifest.json` | Dataset/model/config hashes, provenance, access terms, timestamps, data coverage |
| `revision/factor_registry.csv` | 101 source expressions, retained/excluded mapping + 5 custom, exact transformations |
| `revision/reference_audit.csv` | Claim/title/author/year/DOI/source verification; R16 |
| `revision/component_provenance.md` | QuantAgent reuse vs modifications vs new work, licenses, pinned upstream version |
| `outputs/revision/<run_id>/` | Immutable per-call/per-cutoff results, ledgers, summary metrics và CI |
| `paper/generated/` | LaTeX tables và figures sinh tự động từ selected frozen release |
| Revised manuscript + marked changes | Title/abstract/highlights/results/conclusion phản ánh bằng chứng mới |
| `revision/response_to_reviewers.md` | Point-by-point response đủ 18 comment và mọi subrequirement |
| Versioned archive + persistent ID | Data/code/prompts/responses/processed evidence theo quyền chia sẻ; offline replay report |

## 7. Cách viết response letter và xử lý hồ sơ reject

Mỗi comment giữ nguyên nội dung gốc trong response, sau đó trả lời theo cấu trúc:

1. **Assessment:** xác nhận vấn đề hoặc đính chính giới hạn bằng bằng chứng.
2. **Action:** mô tả thay đổi đã thực hiện, không viết lời hứa chung.
3. **Evidence:** số liệu mới, test hoặc artifact ID; trình bày cả kết quả không thuận lợi.
4. **Location:** section/table/appendix và page/line đã kiểm chứng từ PDF cuối.
5. **Residual limitation:** điều gì vẫn chưa làm được và claim đã thu hẹp ra sao.

Các điểm cần phản hồi đặc biệt:

- **R1:** thừa nhận cash baseline làm thay đổi cách diễn giải 65%; không bảo vệ bằng “vẫn hơn No-Alpha”.
- **R3:** nêu ngày/data hashes khác nhau giữa bảng, đồng thời bổ sung đúng repeated-run study; không dùng lệch snapshot làm lý do bỏ repeats.
- **R6:** cung cấp audit duplication và điều tra provenance; nếu không thể xác minh phải thay kết quả, không chỉ khẳng định branch đúng.
- **R7:** giải thích 20 article records thực tồn tại/caches bị ignore, sửa counts/provenance/availability; không kết luận reviewer sai chỉ vì local cache có file.
- **R9:** dẫn catalogue Groq xác nhận tên hiện hành, nhưng không trình bày như bằng chứng thay cho logs lịch sử.
- **R14:** cung cấp style/fixture và prompt evidence để phân biệt sai prose với ảnh sai.
- **R16:** thừa nhận và thay citations không khớp; không chỉ sửa DOI sang một URL khác vẫn không hỗ trợ claim.

Corresponding author cần bổ sung decision letter và submission metadata để quyết định: revision được mời, reject-and-resubmit được phép, hay chỉ được gửi mới sau khi hỏi editor. Chuẩn bị cover letter nêu substantive redesign, không chỉ “all comments addressed”. Nếu editor không cho nộp lại, chuyển target là quyết định riêng của nhóm tác giả; không mặc định đổi tạp chí trong kế hoạch này.

## 8. Tiêu chí sẵn sàng nộp lại

### Gate A — Integrity và reproducibility, bắt buộc

- [ ] Tất cả R1–R18 và subrequirements có evidence/response/manuscript location; không còn mục chỉ trả lời “future work” cho yêu cầu bắt buộc.
- [ ] Không còn branch provenance chưa giải quyết trong tập kết quả chính; checkpoint reuse hợp lệ được giải thích.
- [ ] Data/label/execution/metric thống nhất; coverage count/percentage/TeX khớp; sai lệch legacy được ghi lại.
- [ ] References được xác minh toàn bộ, upstream attribution/license đầy đủ, tên/ORCID được tác giả xác nhận.
- [ ] Fresh checkout tái tạo tables/figures từ release được cung cấp; raw model outputs và prompts có archive.
- [ ] PDF cuối build từ đúng source; main/submission/graphical abstract cùng title/numbers, không undefined refs/citations hay bảng vỡ.

### Gate B — Bằng chứng cho claim, không phải chỉ checklist kỹ thuật

- [ ] Claim predictive improvement dựa trên BA/MCC và contrasts đã freeze so với naive/non-LLM/placebo, có uncertainty phù hợp; không dựa riêng accuracy cao trong lớp DOWN chiếm ưu thế.
- [ ] Broad multi-block và repeated-panel cho biết effect/uncertainty trong đúng support đã đánh giá; báo rõ nếu không tách được effect khỏi randomness hoặc thay đổi tỷ lệ LONG. Giữ kết quả âm; prospective/untouched holdout chỉ được claim khi thực sự có, không phải gate mặc định của historical exploratory revision.
- [ ] Claim alpha/sentiment riêng có four-way contrasts/placebo và coverage hợp lệ; novelty/fusion có provenance và comparator đúng. Nếu S/AS chỉ chứa missing tin, comment yêu cầu sentiment evidence vẫn mở. Nếu giữ claim dynamic selection vượt fixed/random trong LLM, numeric controls đơn thuần chưa đóng được yêu cầu đó.
- [ ] Claim economic value chỉ dùng khi net ledger sau giả định thực thi rõ ràng thực sự hỗ trợ; không suy từ directional skill.

Nếu Gate B không đạt, vẫn có thể hoàn thành việc trả lời reviewer một cách trung thực, nhưng **chưa đủ để giữ kết luận ưu việt hiện tại**. Chọn giữa thu hẹp thành nghiên cứu đánh giá/giới hạn có đóng góp rõ hoặc thiết kế phương pháp mới và đánh giá trên holdout mới. Không thay tiêu chuẩn sau khi xem kết quả để đánh dấu pass.

### Gate C — Hồ sơ và quyết định của nhóm tác giả

- [ ] Có route nộp hợp lệ theo decision letter; xác nhận journal/category/year nếu tiếp tục mục tiêu Q1.
- [ ] Corresponding author duyệt metadata, claim, limitations, data-access terms và response đầy đủ.
- [ ] Archive identifier tồn tại và kiểm tra truy cập thành công; paper không có placeholder DOI hay claim “public” sai.

## 9. Nguồn ngoài đã kiểm tra và các giới hạn của audit này

Ngày truy cập 01/11/2026; các nguồn hiện hành không thay thế snapshot/log tháng 9/2026.

- **S1:** [Repository QuantAgent, hiện chuyển sang QuantHarness](https://github.com/Y-Research-SBU/QuantAgent). Xác nhận lineage/architecture và MIT; phải đối chiếu commit lịch sử được tái sử dụng.
- **S2:** [Groq Images and Vision](https://console.groq.com/docs/vision). Có model ID `qwen/qwen3.8-27b` và hỗ trợ image input; chỉ xác minh catalogue hiện tại.
- **S3:** [ViSoBERT tại ACL Anthology](https://aclanthology.org/2023.emnlp-main.315/). Xác nhận tác giả, venue và social-media domain.
- **S4:** [Model card 5CD-AI/Vietnamese-Sentiment-visobert](https://huggingface.co/5CD-AI/Vietnamese-Sentiment-visobert). Mô tả pretraining/fine-tuning social content/comment/review và label mapping.
- **S5:** [TradingAgents, arXiv:2412.20138](https://arxiv.org/abs/2412.20138). Xác nhận bốn tác giả và version history.
- **S6a:** [Metadata Crossref của DOI 10.1016/j.eswa.2020.114236](https://api.crossref.org/works/10.1016/j.eswa.2020.114236) và [trang bài tại ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0957417420309556). Title thuộc meta-evaluation, khác citation alpha trong bản thảo.
- **S6b:** [Bài gốc JRFM trên máy chủ publisher](https://mdpi-res.com/d_attachment/jrfm/jrfm-12-00100/article_deploy/jrfm-12-00100.pdf). DOI 10.3390/jrfm12020100 thuộc nghiên cứu Pakistan.
- **S6c:** [Bài gốc tại Business Perspectives](https://businessperspectives.org/index.php/journals?controller=pdfview&item_id=14175&task=download). DOI 10.21511/imfi.17(4).2020.02 thuộc nghiên cứu GCC/cash level.
- **S7:** [Metadata Crossref của bài Deng và cộng sự](https://api.crossref.org/works/10.1109/TNNLS.2016.2522401). Publication metadata của volume/issue được trích là 2017.
- **S8:** [Thông báo VSD về thời gian thanh toán T+2 năm 2022](https://vsdc.vn/vi/ad/152750). Dùng làm mốc lịch sử; execution study phải kiểm tra quy định có hiệu lực đúng từng thời kỳ.

Audit ban đầu ngày 01/11/2026 đã đọc bài/nhận xét và tính lại các chẩn đoán ở mục 1. Tiến độ hiện hành được cập nhật trực tiếp tại R1 trong `plan.md`; `revision/README.md` giữ lịch sử các lượt trước. Lượt rà soát phạm vi ngày 02/11/2026 chỉ giữ thay đổi trong `plan.md`; phần code/output nháp vừa tạo ngoài phạm vi đã gỡ. Chưa có inference Groq, protocol/bank/run hoặc kết quả mới của profile 72 giờ. Kiểm tra tài liệu PASS: 42 task/dependencies, đủ R1–R18, ngân sách, liên kết, UTF-8/Markdown, số đếm run cũ, hash protocol nguyên vẹn và diff; không chạy compile/unit/E2E/leakage suites vì không giữ thay đổi code/runtime. Không ghi các checks lịch sử là đã chạy lại. Checklist đã hoàn thành chỉ áp dụng đúng phạm vi và artifact được nêu.

### Đối soát thay đổi quota/provider pool ngày 02/11/2026

Đã snapshot 1.713 raw/checkpoint artifacts trước đổi policy và archive 50 source/input files đúng hash trong `outputs/revision/r1_72h_run_v2/runtime_history/`. [Operational amendment](outputs/revision/r1_72h_run_v2/execution_amendment.json) giữ original run signature, sources/runtime và audit scope mới; `run_manifest.json`, mọi prediction và model-input contract cũ giữ nguyên byte. AST các helper numeric/target/bootstrap/panel và variant-state/allocation được đối chiếu nguyên vẹn. Không reset quota counters hoặc gọi lại API đã có response hợp lệ.

Pool có lease SQLite + khóa OS theo key, mỗi key một request đang xử lý trên toàn năm home workers. Home shard lưu trữ vẫn giữ nguyên; `provider_org` và `execution_epoch` được archive cho request mới. Hết quota một key thì mượn key khác; ITPM/RPM ngắn thì chờ/retry; worker bỏ qua job model đang hết quota để thực hiện job dùng cache/model còn quota, rồi kiểm lại các job chờ. Provider failures vẫn đếm trước network, lỗi JSON được thử lại có archive, không fallback model/CASH. Analyze báo epochs/cặp vượt epoch và usage theo provider để không che thay đổi lịch thực thi.

Kiểm tra scoped mới: **19 tests profile PASS**, compile đúng các Python thay đổi PASS. Offline verifier replay **185 decisions thật = 10 smoke +175 research PASS**, 1.713 artifacts trước migration vẫn đúng hash. Không gọi API mới, không rerun baseline hoặc đổi hyperparameters. Tác giả tiếp tục bằng đúng `py -3.13 -X utf8 scripts/run_revision_72h.py run --all`; không cần đợi cap nội bộ sang ngày mới, không cần smoke lại. R1 vẫn mở chờ đủ dữ liệu, bảng cuối và manuscript/response.

Diff check code/tài liệu PASS; snapshot nguyên byte `runtime_history/before_provider_only.json` có CRLF và được loại riêng khỏi whitespace check, giữ SHA đã khóa. Không chuẩn hóa lại byte của bằng chứng chỉ để xóa cảnh báo. Chỉ stage code/policy/amendment/source snapshot của task; không stage usage/calls của tác giả.
