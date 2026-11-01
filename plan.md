# Kế hoạch xử lý phản biện và xây dựng lại bằng chứng cho bản thảo

Ngày lập: 01/11/2026. Nhánh khảo sát: `fix`.

## 0. Phương án rút gọn có hiệu lực từ 02/11/2026

**Ưu tiên hiện hành: hoàn thiện phản biện với ít lượt LLM nhất có thể, dùng 5 key thuộc 5 org Groq do tác giả cung cấp.** Các mức 10 Decision repeats/5 end-to-end repeats và full grid cũ được thay bằng thiết kế ở mục này. Mục 3 vẫn giữ đầy đủ yêu cầu khoa học R1–R18; thứ tự, phạm vi thực nghiệm và ngân sách thực hiện theo mục 0, 4 và 5 đã cập nhật. Không phải mọi mở rộng được gợi ý ban đầu đều là yêu cầu của reviewer.

### 0.1. Vì sao R1 phát sinh 8.100 quyết định

`revision/r1_common_protocol.json` đã khóa study cũ chỉ có variant Full, chưa bao gồm factorial/placebo cho R4:

- 540 quyết định calibration train = 9 mã × 3 folds × 20 điểm, chỉ để fit control theo exposure của Full.
- 540 test units × (5 end-to-end + 10 Decision-only − 1 repeat chung) = 7.560 quyết định test.
- Tổng **8.100 quyết định Full**, ít nhất **14.580 API requests**: 540×3 calibration + 540×5×3 end-to-end + 540×9 Decision-only. Request retries/format repairs chưa nằm trong số tối thiểu.

**Không tiếp tục coi hoàn tất grid này là điều kiện đầu tiên để làm R1 hoặc các comment còn lại.** R1 trực tiếp yêu cầu baseline/metrics/class balance; 540 calibration Full, 10/5 repeats trên mọi điểm và full-grid architecture là chi phí do thiết kế triển khai thêm. Giữ chúng như lịch sử, không sửa protocol JSON đã khóa để ép run cũ thành study mới.

### 0.2. Phạm vi tối thiểu và phần được hoãn

| Bắt buộc để phản hồi có bằng chứng | Cách rút ngắn | Chỉ làm thêm khi giữ claim tương ứng |
|---|---|---|
| R1: baselines thật trên cùng input/target | Một lượt Full trên 540 test units có bank; numerical baselines không gọi LLM | Control matched-Full exposure cần calibration riêng |
| R2: thêm thời gian và regime, inference có phụ thuộc | Thêm 270 Full units ở ba block lịch sử; numerical baselines chạy rộng 2023–2026 | VN100/toàn thị trường, thị trường nước ngoài, prospective dài hạn |
| R3: nhiều lần chạy, báo dispersion | 3 Decision repeats trên panel 108 units; 3 end-to-end realizations cho B/AS trên 27 units | 10/5 repeats trên mọi điểm; không tăng số lần chỉ để đạt p-value |
| R4: factor/sentiment/placebo | B/A/S/AS và một placebo alpha có sentiment giữ nguyên, dùng chung reports | Nhiều placebo families, nhiều model/provider, nhiều loại fusion mới |
| R5/R6/R9: thống kê, lineage, reproducibility | Replay/metrics/hashes offline; archive mọi call mới | Chạy lại model chỉ để tính lại CI, Sharpe hoặc thay bảng |
| R7: coverage và domain validation | Audit offline; scorer pinned chạy local, tập nhãn tài chính gọn | Fine-tune mới hoặc crawl nhiều nguồn khi bài không nhận claim NLP mới |
| R8: novelty và attribution đúng | Mô tả prompt-level fusion, reused/new matrix và MIT notice | Phát triển một cơ chế Bayesian/fusion mới chỉ để làm bài có vẻ mới |
| R10: fixed/random factors và selection diagnostics | Tính trên numeric bank; bảng fixed/random của policy số | Fixed/random factors qua LLM nếu khẳng định dynamic selection cải thiện toàn pipeline |
| R11–R18: nhất quán, execution và bài viết | Sửa contract/prose/citations; numerical replay cho cost/horizon khả thi | Quét Cartesian W×horizon×weights×normalisation×model bằng LLM |

Hoãn một thí nghiệm phải đi cùng bỏ/thu hẹp claim mà thí nghiệm đó hỗ trợ. Bảng này **không tự đóng R nào**, và không tuyên bố một study nhỏ chắc chắn đủ power hoặc chắc chắn được accept. Riêng R2 cần cả kết quả của các block thêm, regime coverage thực và giới hạn lấy mẫu; có dữ liệu train nhiều năm chưa phải evaluation nhiều năm.

### 0.3. Thiết kế dùng chung và số lượt chính xác

Ký hiệu: B = không factor/không sentiment; A = factor-only; S = sentiment-only; AS = Full; P = cùng cấu trúc với AS, giữ sentiment, thay alpha bằng placebo nhân quả. Một **unit** là một mã tại một cutoff; repeat và variant không tạo thêm market unit độc lập.

1. **Tập rộng R1–R2: 810 units, mỗi unit một AS decision.** Giữ 540 units của lịch ba folds hiện tại (2025 Q4, 2026 Q2, 2026 Q3). Thêm ba block ở 2023 H2, 2024 H2, 2025 H1, mỗi block 10 ngày decision chung × 9 mã =270. Chọn 10 ngày cách 3 phiên theo lịch tham chiếu, có nhãn đã trưởng thành, vào đầu khoảng đã định; warm-up và universe hợp lệ chỉ xét dữ liệu quá khứ. Khóa danh sách trước inference; không chọn ngày theo accuracy/return hoặc nhìn tương lai để săn regime. Đây là tối đa **90 ngày decision** nếu lịch hiện tại khớp đồng bộ; báo số ngày thực, không tự đếm 810 replication độc lập.
2. **Panel lặp/attribution R3–R4: 108 units nằm trong 810.** Mỗi block lấy hai ngày decision, một ở đầu và một ở cuối block, cùng 9 mã: 6×2×9=108. Manifest phải khóa cutoffs trước khi xem output mới. Chạy B/A/S/AS/P, **3 Decision repeats** trên đúng cùng upstream/report/alpha/sentiment snapshot. AS repeat 0 lấy từ tập rộng, không gọi lại: thêm `108×(5×3−1)=1.512` quyết định. Tổng panel có 1.620 records nhưng chỉ 108 market units/12 ngày, CI phải phản ánh điều đó.
3. **Panel end-to-end R3: 27 units nằm trong panel 108.** Dùng ba ngày đã chọn từ ba block trải qua thời kỳ cũ/giữa/mới ×9 mã; chốt ID trước run. Tạo lại upstream **hai lần bổ sung**, mỗi lần chạy B và AS: thêm `27×2×2=108` decisions, `27×2×2=108` vision calls. Realization đầu đã nằm ở panel attribution; có 3 realizations cho từng B/AS, không gọi repeat 0 hai lần. Đây là sensitivity cho upstream variance, không chứng minh full-grid end-to-end robustness.
4. **Numerical baselines/factors/metrics:** dùng cùng units và train/validation/PIT contract; thêm đánh giá số trên lịch nhiều năm liên tục để mô tả market/regime coverage. Không gọi API, không làm artificial repeats cho model xác định. Train/validation không thêm Full inference mặc định.

| Hạng mục bắt buộc | Quyết định LLM mới, nếu chưa có artifact hợp lệ | Vision calls tối thiểu | Tổng API requests tối thiểu |
|---|---:|---:|---:|
| AS trên 540 units hiện có | 540 | 1.080 | 1.620 |
| AS trên 270 units mở rộng thời gian | 270 | 540 | 810 |
| B/A/S/AS/P, 3 repeats trên 108 units, trừ AS r0 đã có | 1.512 | 0 | 1.512 |
| Hai upstream realizations thêm, B/AS trên 27 units | 108 | 108 | 216 |
| **Tổng nghiên cứu cơ sở** | **2.430** | **1.728** | **4.158** |

**R1 đầu tiên giảm từ 8.100 xuống 540 quyết định**, không còn 540 Full calibration. Toàn gói cơ sở trả lời nhiều comment dùng 2.430 decisions, ít hơn 70% so với 8.100 của riêng study Full cũ; requests tối thiểu giảm khoảng 71,5% (14.580 →4.158). Đây là so sánh ngân sách thiết kế khác nhau, không khẳng định hai study cho bằng chứng thống kê tương đương.

- Dành tối đa **60 request attempts smoke/preflight inference** ngoài tập chấm điểm, dùng để kiểm tra model/quota/render/parse/archive và đo tokens/latency. Catalogue/preflight offline không cần suy luận. Smoke không được nhân bản thành research predictions.
- **Trần cơ sở đề xuất: 5.000 attempts cộng dồn toàn study/5 org**, bao gồm smoke và retries: 4.158+60=4.218 calls chuẩn, còn 782 attempts dự phòng. Nếu lỗi làm không đủ manifest trong trần này, dừng với trạng thái incomplete; không điền CASH và không nâng trần tự động.
- **Mở rộng R10 có điều kiện:** nếu giữ claim dynamic selector vượt fixed/random **trong LLM**, thêm hai variant fixed/random trên đúng 108 units×3 repeats =648 decisions, dùng lại upstream. Khi đó tổng 3.078 decisions, 4.806 research calls; cộng smoke tối đa 4.866 attempts chuẩn, trần đề xuất **5.800**. Random factor draw khóa theo unit; random-draw seed và Decision-repeat seed phải được phân biệt. Nhiều random draws cho phân phối selector chạy offline trước.
- Không tính tiết kiệm từ calls cũ trước audit. Ngân sách là từ zero verified inference; chỉ trừ số request thực sự được tái dùng hợp lệ, cùng role/cutoff/input/prompt/model/revision/branch. Calibration cũ không chuyển thành test hoặc repeat mới.
- Các phép đếm giả định Indicator/Alpha/Sentiment chuẩn bị offline và chỉ Pattern/Trend gọi vision, mỗi final decision một text call. Nếu implementation phát sinh report LLM, repair hoặc fallback thì dry-run/call instrumentation phải cộng vào dự toán trước freeze; không giả định chúng miễn phí.

**Điểm chặn sentiment:** protocol cũ coi mọi legacy-unknown scorer là missing và khóa peer set rỗng. Không chạy hàng nghìn factorial calls với S/AS chỉ có missing rồi nhận đó là bằng chứng sentiment. Trước freeze, audit raw text/availability; khi có đầu vào hợp lệ, score local bằng model revision cố định sang cache mới. Nếu không có đủ tin thật, vẫn có thể báo missingness experiment, nhưng R4 sentiment/R7 empirical contribution còn mở và claim sentiment hữu ích phải bỏ. Chi phí thu thập tin hoặc phục hồi raw text không thể giải quyết bằng thêm key.

### 0.4. Lập lịch 5 org Groq và dự toán thời gian

Theo [Groq rate limits](https://console.groq.com/docs/rate-limits) (kiểm tra 02/11/2026), quota áp dụng ở cấp organization; có RPM/RPD/TPM/TPD và có thể có ITPM/OTPM. Vì năm key thuộc năm org khác nhau, có thể phân phối các job được cấp quyền qua năm quota riêng. Không suy một key = một cấu hình quota giống nhau hoặc tốc độ luôn gấp năm.

**Việc triển khai tối thiểu, chưa được code trong lượt sửa kế hoạch này:**

- [ ] Dùng pool `org_1`…`org_5`, secrets chỉ ở môi trường cục bộ; manifest lưu alias org/project không chứa key. Xác nhận cùng model locked và quyền truy cập của từng org. Không dump `.env`, key hay credential hash vào artifacts.
- [ ] Mỗi org có limiter riêng theo model/quota bucket, cộng limiter toàn study. Khởi điểm một request đang xử lý/org; chỉ tăng concurrency nếu telemetry và quota cho phép. Dùng chung scheduler cho Pattern/Trend/Decision, không cấp cố định một org cho một treatment hoặc regime.
- [ ] Shard theo unit cân bằng block/mã; shuffle/counterbalance order variants và repeats bằng seed đã khóa. Lưu org alias với từng request và kiểm tra org có bị confound với variant/model không. Cùng upstream snapshot được mọi branch dùng qua parent hash, không tái tạo chỉ vì đổi org.
- [ ] Mọi call tiếp tục qua `_invoke_with_retry`; tôn trọng `retry-after`/reset, backoff và quota thực. Org/model chạm TPD được cooldown đến thời điểm hợp lệ; job chưa chạy có thể sang org khác còn quota, không spam org đang bị giới hạn. Lỗi account/permission/model mismatch phải điều tra, không che bằng đổi key.
- [ ] Dùng 5 process/worker cách ly client, chart paths, checkpoint shards và file tạm; một writer/aggregator cho global usage/manifest. Runner hiện chưa có contract này: **không chạy năm bản runner cũ cùng bank/run**, không đổi biến môi trường client chung giữa threads. Lock/atomic write chống hai worker ghi cùng unit.
- [ ] Dùng idempotency key cho unit/variant/repeat/node. Resume chỉ job thiếu; raw successful responses giữ nguyên. Reuse reports chỉ trong cùng realization; không cache final decision giữa các repeats.
- [ ] Giữ Decision prompt `<6.500` ký tự, `_distill_report`/`_cap_report`; đo số token thực chứ không coi ký tự là token. Giảm output cap chỉ sau smoke cho thấy không truncate/parse lỗi, rồi freeze và dùng đồng nhất. Không đổi model, prompt hoặc cap giữa chừng để chạy nhanh hơn.
- [ ] Meter attempts, input/output/cache tokens, duration, 429, fallback, successful decisions và coverage; progress hiển thị market units và variants/repeats riêng. Forecast ETA từ quota còn lại và p95 payload, không chỉ throughput token quảng cáo.

**Công thức ETA:** với quota bucket m, nhu cầu token `V_m`, năng lực tổng thực dùng của năm org `Q_m/ngày`, cận dưới quota-time là `V_m/Q_m`; lấy bottleneck trên các bucket, đồng thời xét RPM/RPD/ITPM/OTPM, p95 latency, dependency DAG và tải đang dùng của org. Nếu quota dùng chung giữa text/vision, cộng nhu cầu token trước khi chia; không tính cùng quota hai lần. Reset thực theo provider, không tự giả định đúng 00:00 giờ Việt Nam.

Ví dụ chỉ để dự toán, **không phải quota đã xác minh**: nếu cả năm org đều có vision TPD 200.000 chưa dùng, tổng là 1.000.000 token/ngày. Với 1.728 vision calls và 2.500–4.000 quota-token/call, riêng vision cần 4,32–6,91 triệu token, tương đương tối thiểu 4,3–6,9 quota-days. Text calls, retry và quota dùng chung có thể kéo dài hơn. Smoke phải thay các số giả định bằng telemetry; năm key không bảo đảm hoàn tất trong vài giờ.

Telemetry cục bộ đã đọc ngày 02/11/2026: 48 response vision thành công có median **2.424**, p95 **2.523 total tokens**; 23 response text có median **2.194**, p95 **2.964**. Đây là mẫu smoke/calibration hiện có, không phải output của profile mới và không chứng minh quota của bốn org còn lại. Nếu tạm dùng p95 này cho 1.728 vision +2.430 text calls, nhu cầu khoảng **4,36 triệu vision tokens và 7,20 triệu text tokens** trước retry. Nếu hai model cùng chia tổng 1 triệu token/ngày thì cận dưới khoảng **11,6 quota-days**; nếu bucket riêng thì tính bottleneck từng model. Đo lại profile mới vì placebo/sentiment/report length có thể khác; không ép ETA 5–10 ngày khi số đo không hỗ trợ.

Mục tiêu vận hành có điều kiện: **2–3 ngày làm việc để sửa phần thiếu, freeze và chuẩn bị bài; khoảng 5–10 ngày lịch cho gói nghiên cứu/biên tập nếu dữ liệu đủ và quota ví dụ đáp ứng**, cho chạy offline/citations/manuscript trong khi chờ API. Nếu ETA vượt ngân sách, giữ trần và thu hẹp claim/phạm vi công khai; không chọn kết quả tốt nhất hoặc bỏ silently những strata chạy chậm.

Batch API chỉ là phương án thay thế nếu model/plan thực có hỗ trợ và ETA tốt hơn. [Tài liệu Batch](https://console.groq.com/docs/batch) nêu cửa sổ xử lý bất đồng bộ 24 giờ đến 7 ngày; không mặc định đây là đường nhanh nhất, và không tự nâng gói.

### 0.5. Chuyển từ study cũ sang thiết kế rút gọn

- [ ] Kiểm tra status và checkpoint của run v3 tại thời điểm chuyển. Không suy receipt cũ “0 prediction” vẫn đúng sau khi người dùng resume; không tự dừng tiến trình khác chỉ vì chỉnh tài liệu.
- [ ] Khi chuyển triển khai, kết thúc run cũ ở checkpoint boundary theo quyền vận hành của task, giữ nguyên archive/hash và ghi lý do dừng là đổi ngân sách. Không xóa requests, `usage.json` hay lock của tiến trình còn hoạt động.
- [ ] Tạo protocol/bank/run ID mới cho thiết kế rút gọn; **không sửa `revision/r1_common_protocol.json` đã khóa**, không hạ repeats tại chỗ và gắn completion cho v3. Lượt này chỉ sửa Markdown, chưa có CLI thực thi profile mới.
- [ ] Reuse giá, numerical features, chart/report hoặc raw response chỉ khi provenance và input/AST/config hashes chứng minh cùng nội dung, có parent IDs và access hợp lệ. Những inputs thay sentiment/normalization/prompt cần feature/response mới; giữ artifacts gốc nguyên byte.
- [ ] Các baseline số đã có không phải chạy lại chỉ vì sửa plan. Chỉ tính bổ sung các block/variant/input đã đổi; các bảng R1 cũ và mới phải phân biệt dataset/protocol.
- [ ] Freeze subset/schedule, primary contrasts, estimand, failure/stop policy và cap trước inference mới. Baseline kết quả cũ đã được xem nên nghiên cứu vẫn là **historical exploratory revision**, không đổi nhãn thành confirmatory.
- [ ] Repeated-panel không đại diện tự động cho variance của toàn 810 units. Báo riêng broad one-pass và panel mean/SD/CI; 3 repeats chỉ là minimum khả thi, có thể thiếu precision. Không dừng sớm theo p-value; không tuyên bố hoàn tất reviewer khi dữ liệu còn thiếu.


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

### R1 — Baseline, mất cân bằng lớp và tuyên bố hiệu quả [P0]

**Vấn đề:** Full thua constant DOWN/CASH về accuracy và mean return. No-Alpha yếu hơn mức BA 50%; lợi thế trước control yếu chưa xác lập giá trị dự báo. Label hiện là “LONG có lãi sau phí”, không phải dấu biến động giá thuần túy.

**Trạng thái cập nhật 02/11/2026:** đã có audit legacy và numerical baseline releases; Full trên common snapshot còn incomplete, chuyển sang ngân sách mục 0. Theo dõi bằng chứng và dependency tại [revision/README.md](revision/README.md); target/metric contract tại [revision/target_contract.md](revision/target_contract.md). Chưa đóng R1 hoặc coi audit legacy là confirmatory evidence.

**Việc cần làm**

- [ ] Theo ngân sách rút gọn mục 0: R1 dùng 540 units × một Full run trên cùng input với baselines, sau khi integrity gate đạt; không chờ 540 Full calibration hoặc grid 10/5 repeats. Phân bố repeats được báo ở panel R3 và không suy rộng tùy tiện sang toàn tập R1.
- [ ] Tái tính class support, confusion matrix, accuracy, BA, MCC, macro-F1, precision/recall/F1 từng lớp cho mọi mã, fold, regime và repeat; phân biệt pooled và macro-average.
- [ ] Thêm constant DOWN/CASH, constant UP/always-LONG cycles, majority-class fit trên train, buy-and-hold thực sự, momentum cố định, logistic regression và một baseline factor-only không LLM. Phân biệt majority nhìn từ test chỉ dùng mô tả với majority được huấn luyện hợp lệ.
- [ ] Logistic có ít nhất hai cấu hình: chỉ indicator/OHLCV và cùng indicator + alpha + sentiment/missingness. Chuẩn hóa, imputation, chọn tham số, threshold chỉ fit trên train/validation. Baseline chỉ có giá và baseline cùng thông tin trả lời các câu hỏi khác nhau, phải ghi rõ.
- [ ] Báo tỷ lệ LONG, turnover, exposure, số lệnh, net return, daily drawdown và chi phí. Control exposure tương đương Full là mở rộng có điều kiện; mặc định không tạo 540 Full train calls chỉ để fit control này. Nếu dùng random control với tỷ lệ ấn định hoặc fit từ numeric train, ghi đúng tên, không gọi đó là matched-Full exposure. Câu hỏi prompt-induced CASH được kiểm tra trực tiếp bằng placebo, BA/per-class metrics và LONG rate ở R4.
- [ ] Nếu cần gọi “direction forecasting”, bổ sung target gross return riêng; giữ nguyên target net cho replication. Không đổi target sau khi thấy kết quả để tăng accuracy.
- [ ] Viết lại abstract/highlights/introduction/conclusion sau kết quả mới; bỏ suy luận “alpha lift = alpha information value” từ phép so sánh Full vs baseline bundle.

**Đầu ra:** bảng baseline đầy đủ, bảng confusion/imbalance và tài liệu định nghĩa target. **Đạt khi:** mọi baseline cùng lịch, chi phí và dữ liệu hợp lệ; không che việc thua cash hoặc baseline đơn giản; undefined metric được ghi NA với quy ước rõ ràng. **Sửa tại:** `utils/statistical_tests.py`, `core/backtest_engine.py`, runner baseline mới, sections 03/05/06/08 và front matter.

### R2 — Mẫu ngắn, một regime và phụ thuộc chéo [P1]

**Vấn đề:** 20 cutoff/mã chủ yếu từ giữa tháng 6 đến giữa tháng 9/2026. Chín mã có yếu tố thị trường chung và lịch gần nhau; không phải chín replication độc lập.

**Việc cần làm**

- [ ] Reuse snapshot **2020–30/09/2026** đã được đóng băng nếu hash/quality phù hợp, kèm warm-up trước fold đầu. Mục 0 mở rộng evaluation LLM thành sáu block 2023–2026 và numeric evaluation rộng; không tải lại dữ liệu chỉ để có một run ID mới. Chỉ dùng ngày có dữ liệu và label đã trưởng thành.
- [ ] Giữ chín mã trong gói tối thiểu để giảm triển khai/calls; mô tả rõ survivorship/purposive selection và không suy rộng toàn thị trường. Mở rộng VN30/VN100 là tùy chọn khi nhận claim external validity tương ứng; universe phải point-in-time, ghi listing/delisting/missing/suspension.
- [ ] Dùng rolling/expanding outer folds, inner validation theo thời gian; purge các mẫu có label span chạm tập test và fit lại toàn bộ preprocessing/selection trong train.
- [ ] Regime tăng/giảm/đi ngang, volatility và liquidity được gán bằng quy tắc chỉ dùng dữ liệu đã quan sát tại cutoff. Báo số cutoff, số phiên độc lập, class balance, exposure từng regime; không chỉ nêu tên năm.
- [ ] Resample block thời gian **đồng bộ cả panel mã và các nhánh**, giữ market shock chung. Lịch không trùng nhau phải join theo ngày lịch giao dịch và giữ missing mask, không ghép theo `test_id`.
- [ ] Tách backtest lịch sử với nguy cơ LLM đã biết dữ liệu khỏi đánh giá sau mốc đóng băng model/protocol. Multi-year với model mới không mặc nhiên sạch contamination. Model release date không tự chứng minh training cutoff, càng không bao phủ vision model hoặc aliases thay đổi.
- [ ] Prospective holdout là hướng bổ sung, không nằm trên critical path bản sửa ngắn hạn nếu chỉ giữ claim historical exploratory. Nếu vẫn nhận claim prospective validity thì phải chờ dữ liệu sau freeze, không dùng backtest thay thế. Báo rõ giới hạn contamination và số block/ngày thực của study rút gọn.

**Đầu ra:** `data_manifest`, `folds`, `regime_labels`, báo cáo panel và contamination. **Đạt khi:** có đánh giá qua nhiều trạng thái thị trường, độ bất định phù hợp phụ thuộc; tách rõ historical/exploratory và confirmatory. **Sửa tại:** loader, engine, runner mới, sections 05/06/07.

### R3 — Biến thiên giữa các lần chạy [P1]

**Vấn đề:** spread 15–20 pp giữa các bảng không nhỏ so với lift 13,9 pp; shared upstream không khử randomness của Decision Agent. Các bảng còn khác lịch nên chưa phải matched repeated runs.

**Việc cần làm**

- [ ] Tạo manifest so sánh toàn bộ cấu hình “default”: cutoff IDs, data hash, prompt hash, model/provider, token caps, temperature, code commit, fallback và order.
- [ ] Hai tầng theo mục 0: **3 Decision repeats trên 108 units cho B/A/S/AS/P**, **3 upstream realizations trên 27 units cho B/AS**. Một realization đầu được chia sẻ, không tính/call hai lần. Bỏ mặc định 10/5 trên mọi điểm; ghi rõ variance chỉ được đo trực tiếp ở panel đã chọn, 3 repeats chưa bảo đảm power/precision.
- [ ] Mỗi repeat có identity/checkpoint riêng trong study; chỉ resume requests còn thiếu của đúng repeat. Không sao final decision từ repeat trước. Manifest có parent reports để cho phép reuse upstream được chủ đích.
- [ ] Cân bằng/thay thứ tự gọi các variant giữa repeats, giữ model revision và cấu hình; lưu request ID/timestamp và mọi retry/fallback. Seed Python/NumPy không thay thế seed hay tính xác định của hosted API.
- [ ] Báo mean, SD, median/range, CI cho BA, MCC, accuracy, lift, return; disagreement rate theo cutoff và variance giữa upstream/decision.
- [ ] Khi inference, resample run ở đúng cấp cùng block thời gian; không biến 180 quyết định lặp R lần thành 180R thị trường độc lập. Nếu triển khai ensemble thì đánh giá ensemble riêng, không lấy kết quả tốt nhất trong R.

**Đầu ra:** bảng repeated-run trên cùng panel, sensitivity upstream/decision, request archive. **Đạt khi:** mọi cấu hình dùng cho attribution chính có phân bố 3 runs trên panel chung; broad one-pass và repeated-panel được tách rõ, kết luận không vượt precision/coverage của panel. Không gọi study này là full-grid variance decomposition. **Sửa tại:** engine, robustness/ablation runners, thống kê và sections 05/06.

### R4 — Không tách alpha, sentiment và ảnh hưởng cấu trúc prompt [P0/P1]

**Vấn đề:** No-Alpha hiện bỏ cả alpha và sentiment. Hai nhánh khác cả thông tin, độ dài và cấu trúc prompt. Four-way hiện chỉ ba mã, provenance chưa được xác nhận.

**Việc cần làm**

- [ ] Đổi tên control lịch sử thành `No-factor/no-sentiment` hoặc `Base reports`; dùng `Full − Base` cho bundle effect.
- [ ] Chạy factorial 2×2 trên **panel 108 units, đủ chín mã/sáu block, 3 repeats**: B=(0,0), A=(1,0), S=(0,1), AS=(1,1). Khi diễn giải alpha có sentiment, so sánh **AS−S**; alpha không sentiment là **A−B**. Tương tự sentiment: AS−A và S−B. Phân tích riêng strata sentiment available; không gọi missing-sentiment contrast là effect của tin tức.
- [ ] Placebo bắt buộc P giữ nguyên headings, schema, vị trí, phong cách/token budget và sentiment như AS, thay alpha bằng vector quá khứ từ training pool trước cutoff, seed khóa. Đây là một control family đủ trực tiếp cho R4; neutral/random-value families khác là tùy chọn. Availability mask phải giống treatment để placebo không có thêm thông tin về missingness.
- [ ] Không shuffle với giá trị từ tương lai của outer test; giữ cấu trúc tương quan factor hợp lý, lưu seed và permutation map. Giá trị placeholder không được tự mang tín hiệu tương lai.
- [ ] Kiểm tra alpha reasoning report không rò sentiment vào A; sentiment branch không rò factor vào S. Shared Indicator/Pattern/Trend phải cùng hash tại mỗi `(cutoff, repeat)`.
- [ ] Đăng ký trước contrast và multiplicity family. Bổ sung interaction factorial `M(AS) − M(A) − M(S) + M(B)`. Công thức “Synergy = Full − max(A,S)” hiện tại chỉ là improvement over best single component, không phải interaction chuẩn; nếu giữ thì đổi tên và tách hai đại lượng.

**Đầu ra:** matrix factorial + placebo, prompt diffs, contrast estimates/CI. **Đạt khi:** effect information có thể phân biệt với extra prompt và thiên hướng CASH; nếu placebo ngang alpha thật thì thu hẹp hoặc bỏ claim thông tin alpha. **Sửa tại:** graph/alpha/decision agents, ablation runner, sections 03/05/06.

### R5 — Khoảng tin cậy, Newey–West, N và annualisation [P0]

**Vấn đề:** bootstrap 20 điểm/block 5 rất ít thông tin; percentile CI khó tin khi chỉ một discordant pair. McNemar và bootstrap khác giả định nên bất đồng không tự chứng minh code sai, nhưng không được chọn kết quả thuận lợi. `N=20` ở hàng Mean gây hiểu sai; account Sharpe/Sortino dùng sai tần suất.

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

**Việc cần làm**

- [ ] Hash và đóng băng toàn bộ artifacts hiện tại. So sánh từng row: date, prediction, confidence, risk/reward, thời gian, errors, labels, equity, checkpoint timestamps và code commit; kiểm tra cả các mã/nhánh khác.
- [ ] Kiểm tra luồng save/load, biến mutable, deep-copy, cờ `enable_alpha_factors`/`enable_sentiment`, checkpoint key và mọi script tạo/chuyển đổi artifacts. Truy nguyên log gốc nếu có.
- [ ] Phân biệt reuse hợp lệ của **cùng control** trong alpha-only parameter sweep với reuse sai của một control dưới tên **treatment**. Reuse được phép phải có parent artifact ID.
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
- [ ] So sánh dynamic top-5 với tập 5 factor cố định định trước, random eligible top-5 với nhiều seed, simple momentum/factor vote và không sign-flip **bằng numeric policy trên cùng bank** trước, không gọi LLM cho từng candidate. Random factor selection khác placebo đổi giá trị factor ở R4. Nếu bài kết luận dynamic selection vượt fixed/random trong toàn pipeline LLM, chạy thêm 648 decisions như mục 0; numeric comparison không thay cho claim đó.
- [ ] Chọn trước multiplicity procedure phù hợp họ giả thuyết: Holm cho các contrast xác nhận; FDR cho khám phá factor; nếu claim tìm được strategy/factor vượt trội sau search thì dùng Reality Check/SPA/DSR thích hợp cùng toàn bộ candidate/trial returns. Không áp DSR lên accuracy hoặc gọi IC ranking là significance.
- [ ] Giữ nhật ký toàn bộ trial/config đã thử. Không bỏ multiplicity sang Future Work nếu vẫn nhận claim phát hiện factor hiệu quả.

**Đầu ra:** factor translation registry, selection diagnostics và fixed/random controls. **Đạt khi:** reviewer kiểm tra được 21 exclusions và mọi retained expression, đồng thời thấy lợi ích selector ngoài selection optimism. **Sửa tại:** `core/alpha_compare.py`, `utils/alpha_selector.py`, `agents/alpha_agent.py`, tests alpha, sections 03/04/06 và phụ lục.

### R11 — Label và trường actual_prev_close [P2, contract P0]

- [ ] Thay label log Close-to-Close trong Table B.10 bằng đúng net next-Open-to-target-Close của Eq. 4; đồng bộ equation, pseudocode, prompt, alpha target và JSON schema.
- [ ] Không rename toàn bộ legacy `actual_prev_close` một cách máy móc: ở benchmark FPT đã thấy nó bằng entry_open, nhưng checkpoint khác có giá trị khác entry_open. Tách rõ `decision_close`, `entry_open`, `exit_close`, `gross_return`, `net_return`, `label`; migration phải dựa vào snapshot hoặc đánh dấu legacy ambiguous.
- [ ] Tạo kiểm thử với overnight gap lớn, zero net return, chi phí hai chiều, holiday và incomplete horizon; kiểm tra label từ đúng giá.

**Đạt khi:** mọi field có một nghĩa duy nhất và không sửa lịch sử bằng suy đoán. **Sửa tại:** state schema, engine/serializers, phụ lục B, section 03.

### R12 — Indicator rules và thuật ngữ [P2]

- [ ] Table 1 dùng RSI bullish `<=30` hoặc `55<=RSI<70`; bearish `>=70` hoặc `30<RSI<=45`; trung tính phần còn lại. Ghi thứ tự ưu tiên như code, kiểm tra các biên 30/45/55/70 và crossover của các indicator khác.
- [ ] Đổi “five momentum and volatility oscillators” thành mô tả momentum/trend phù hợp.
- [ ] Xác định Bollinger Bands và ADX có được tính, truyền state hay dùng ở quyết định không; phân biệt schema fields có sẵn với năm indicator thực tế dùng cho consensus. Sửa Table B.10 hoặc mô tả supplementary features cho đúng.

**Đạt khi:** table, appendix, prompt và deterministic classifier cùng rule. **Sửa tại:** indicator agent, static utilities, sections 04 và phụ lục B/D.

### R13 — Alpha_4 và tên custom/proprietary [P2]

- [ ] Giải thích đúng `(%B−0.5)×VolZ5`: VolZ5 âm đảo dấu tín hiệu, VolZ5=0 triệt tiêu; `abs(VolZ)>0` không đồng nghĩa volume expansion.
- [ ] Ưu tiên giữ công thức để replication và sửa diễn giải thành tương tác signed volume. Nếu mục tiêu thật sự là confirmation, định nghĩa phiên bản mới, ví dụ gate `max(VolZ5,0)`, đăng ký trước và đánh giá riêng; không sửa công thức rồi giữ kết quả cũ.
- [ ] Đổi proprietary thành custom ở toàn bài; giải thích “order flow” chỉ là price/volume proxy nếu không có dữ liệu giao dịch/lệnh thực.

**Đạt khi:** có ví dụ/test VolZ âm/0/dương và không mâu thuẫn tên–cơ chế–kết quả. **Sửa tại:** alpha registry/agent nếu đổi formula, section 04, phụ lục C.

### R14 — Quy ước màu chart [P2; rerun có điều kiện]

- [ ] Đối chiếu style, hàm vẽ, chart archive và prompt; hiện code đặt up xanh/down đỏ nhưng comment và prose ngược nghĩa.
- [ ] Tạo chart fixture có các nến tăng/giảm biết trước, kiểm tra màu và legend. Nêu candle color dựa trên Close vs Open; màu bảng điện thường dựa trên giá tham chiếu, không đồng nhất hai khái niệm.
- [ ] Nếu chỉ sai chú thích/prose, sửa và cung cấp fixture; nếu ảnh hoặc prompt lịch sử thực sự đảo màu, đánh giá ảnh hưởng, version renderer/prompt và chạy lại mọi branch liên quan với shared charts.

**Đạt khi:** có bằng chứng hình ảnh kiểm tra đúng convention và provenance. **Sửa tại:** `utils/color_style.py`, chart utilities, prompts, section 04.4.

### R15 — Settlement, price limits và L=3 [P1]

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

### 4.2. Matrix tối thiểu cần chạy theo ngân sách rút gọn

| Nhóm | Cấu hình | Phạm vi |
|---|---|---|
| Legacy | Replay 180 points/receipts đã có | Offline, không rerun historical LLM hoặc gọi đây là untouched test |
| Naive/economic/non-LLM | CASH, UP cycles, train-majority, buy-and-hold, momentum, logistic, factor-only | Toàn bộ common units; bổ sung block mới, không tính lại phần đã khóa chỉ vì sửa Markdown |
| Broad Full | AS một run trên 540 units hiện có +270 units lịch sử mới | 810 decisions; cùng inputs/ledger với numeric baselines; có giới hạn lấy mẫu |
| Factorial + placebo | B/A/S/AS/P | Panel 108 units, 3 Decision repeats, AS r0 dùng lại broad run; cần sentiment coverage thật |
| Upstream variance | B và AS | Panel 27 units, 3 realizations gồm r0 đã có; báo như sensitivity |
| Selection | Dynamic/fixed/random factors, orientation/turnover/IC stability | Offline đầu tiên; 648 LLM calls tùy claim dynamic-selector superiority |
| Architecture | Base derived từ QuantAgent và concat hiện tại | Không thêm fusion/model mới trong gói cơ sở; thu hẹp claim novelty |
| Robustness | Cost/slippage/fill, regime, sign/normalisation diagnostics | Numeric replay/offline; đổi target/horizon chỉ là numeric sensitivity, không gọi forecast L=3 thành forecast L=5/10 |

Chỉ một default W=45, L=3 và model pair đã khóa cho LLM core. Khóa protocol/contrasts trước inference; **không chạy Cartesian sweep** W×normalisation×weights×horizon×model. Thay đổi hành vi để sửa lỗi phải version và áp dụng chung các branch. Không giảm token bằng bỏ evidence chỉ ở một branch; không lấy forecast cũ gắn sang horizon mới. Giá trị numeric sensitivity chỉ hỗ trợ đúng policy số đã đánh giá.

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
- Report CI/effect size kèm số ngày, folds, mã và runs. Broad 810-unit one-pass không có 3-run SD trên toàn mẫu; SD/CI theo repeats chỉ áp dụng panel 108, upstream sensitivity chỉ panel 27. Phân biệt uncertainty do market sample và do inference stochasticity. Không coi stock, folds chồng lấn hoặc repeats là độc lập tùy tiện. Panel chỉ 12 ngày (upstream 3 ngày) có uncertainty lớn, không coi số org hoặc repeats làm tăng số regime độc lập.
- Nếu effect biến mất trước CASH, non-LLM hoặc placebo, nêu thẳng. Có thể xây dựng nghiên cứu về điều kiện thất bại/benchmark hoặc cơ chế tốt hơn rồi đánh giá trên holdout mới; không đổi mục tiêu sau hoc và gọi đó là confirmatory success.
- Predictive benefit không đủ để claim profitability; return dương vài mã không đủ để claim portfolio alpha. Kết luận phải khớp loại bằng chứng thực tế.

## 5. Lộ trình thực hiện theo dependency

Lộ trình rút gọn kế thừa các phần đã triển khai trong `revision/README.md`; không làm lại G0/G1 hoặc toàn numerical suite nếu nguồn/code không đổi. Ước lượng là công sức cho phần còn thiếu; quota-time tính riêng ở mục 0. Owner là vai trò cần phân công, chưa phải người được chỉ định. Mục tiêu 5–10 ngày lịch chỉ áp dụng khi dữ liệu/provenance đủ và quota đáp ứng, không phải lời hứa accept hoặc deadline cố định.

| Giai đoạn | Công việc / reviewer | Owner | Ước lượng | Điều kiện qua giai đoạn |
|---|---|---|---|---|
| G0 — Đối soát và chuyển kế hoạch | Status/hash/lineage v3, gaps R6/R7/R9; tái dùng audit đã có | Lead + software | 0,5 ngày | Giữ raw cũ; xác định verified/unverified; có protocol mới riêng |
| G1 — Hoàn thiện đường chạy ngắn | Fix contract/ledger cần thiết; pool 5 org, shard/lock/limiter; factorial/repeats | Software + quant | 1–2 ngày | Tests đúng đường bị đổi PASS; không chạy cả suite vô cớ |
| G2 — Data/protocol/sentiment freeze | Thêm block, audit tin/local scorer, chọn panel; numeric controls | Data + methods + NLP | 0,5–1 ngày nếu nguồn đủ | Hash input/units/contrasts/caps khóa; sentiment gap khai báo; không tune theo output mới |
| G3 — Smoke hạn mức | Tối đa 60 attempts trên points ngoài evaluation; đo tokens/parse/quotas | Software | 0,5 ngày, phụ thuộc quota | ETA thực và caps; lỗi format/model trước khi dùng quota lớn |
| G4 — Shared evaluation | Broad AS, factorial/placebo, repeat sensitivity; bổ sung R10 nếu giữ claim | Experiment owner | Theo quota; ví dụ riêng vision 4,3–6,9 quota-days | Đủ manifest, không cherry-pick; completion theo profile mới |
| G5 — Bài viết và phân tích | R5/R8/R11–R18/citations làm khi chờ API; results hoàn thiện sau G4 | Quant + lead | 1–2 ngày công, phần lớn chồng lịch G4 | Claim–evidence matrix và bảng từ artifacts |
| G6 — Replay/QA/hồ sơ | Hash/replay release, PDF/response, author metadata/persistent ID | Người kiểm tra + corresponding author | 0,5–1 ngày sau kết quả | Qua gates áp dụng; route nộp đúng decision letter |

Dependency inference: **G0 → (G1/G2) → G3 → G4 → kết quả G5 → G6**. Reference audit, attribution, metadata tác giả, sửa prose và chuẩn bị response bắt đầu ngay sau G0, cùng thời gian chờ API. Prospective collection là nhánh riêng khi cần claim đó; không chờ nó nếu chỉ công bố historical exploratory evidence, và không gọi backtest là prospective.

### 5.1. Danh sách triển khai tiếp theo

- [ ] **FAST-01** Đối soát tiến độ và artifacts mới của v3, ghi chuyển scope ngân sách; không đụng usage/calls chưa commit của người dùng khi chỉ sửa tài liệu.
- [ ] **FAST-02** Tạo protocol mới với broad 810/panel108/upstream27, 3 repeats, core 5 variants, budget 5.000 attempts; không sửa JSON khóa cũ. Nếu giữ dynamic-selector LLM claim, đăng ký thêm 648 decisions/trần 5.800 trước run.
- [ ] **FAST-03** Implement pool 5 org, per-org/model limiter, shared global cap, isolated workers/checkpoints và atomic aggregator; tất cả calls dùng retry wrapper hiện có.
- [ ] **FAST-04** Gate sentiment/availability và lineage; bổ sung giá/features cho 270 units mới, numerical controls và fixed/random selection offline. Không trì hoãn toàn bộ prose/reference work vì đang thiếu LLM.
- [ ] **FAST-05** Smoke <=60 attempts, đo ETA và request forecast; freeze prompt/model/report contracts trước chấm điểm. Trần đạt mà incomplete thì báo thiếu evidence, không tự giảm số unit sau khi thấy outcome.
- [ ] **FAST-06** Chạy shared evaluation, reuse hợp lệ AS r0/upstream, tổng hợp broad và repeated-panel riêng; hoàn thiện response R1–R18 rồi kiểm Gate A/B/C.

Các task T01–T10 dưới đây là bản đồ công việc gốc để trace reviewer; **đối chiếu trạng thái đã làm trong `revision/README.md` trước khi thực hiện**, không khởi động lại toàn bộ:

- [ ] **T01** Tạo manifest/hash cho submitted PDF/TeX/comments và toàn bộ result/cache; xác định version chính thức của submission.
- [ ] **T02** Xuất independent audit 180 points: confusion/baselines/cycle return/NW và reproduction Table 7.
- [ ] **T03** Audit duplicate sequences và lineage toàn bộ checkpoint; giải quyết R6 trước khi dùng Table 9.
- [ ] **T04** Chạy lại coverage từ raw articles qua đúng availability rules; sửa script paths và generated CSV/TeX invariants.
- [ ] **T05** Sửa annualisation Sharpe/Sortino, canonical price fields/labels, daily equity và settlement contract.
- [ ] **T06** Sửa citations sai, provenance QuantAgent, text/prompt conventions và thống nhất source/build.
- [ ] **T07** Thêm immutable snapshot loader, request archive, full cache key và resume validation.
- [ ] **T08** Implement baselines cùng feature contract và nested temporal selector.
- [ ] **T09** Implement factorial/placebo/repeat runner và panel inference; simulation-check dưới null.
- [ ] **T10** Freeze protocol, data/folds, budget và power/precision criteria trước run mới; thiết kế rút gọn này là historical exploratory. Một confirmatory study thực sự cần holdout thích hợp chưa dùng để phát triển phương pháp.

## 6. Deliverables cần có sau khi hoàn thành kế hoạch

Các đường dẫn dưới đây là **đầu ra dự kiến**, chưa được tạo bởi lượt lập kế hoạch này.

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

Audit ban đầu ngày 01/11/2026 đã đọc bài/nhận xét và tính lại các chẩn đoán ở mục 1; trạng thái triển khai sau đó nằm ở `revision/README.md`. Bản cập nhật 02/11/2026 chỉ sửa tài liệu kế hoạch/ngân sách/runbook, không chạy inference, thay protocol JSON/runtime hoặc ghi lại kết quả nghiên cứu. Thiết kế rút gọn chưa được triển khai chỉ bằng việc sửa file này; không đọc các checklist như những kết quả đã hoàn thành.
