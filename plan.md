# Kế hoạch xử lý phản biện và xây dựng lại bằng chứng cho bản thảo

Ngày lập: 01/11/2026. Nhánh khảo sát: `fix`.

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

**Đang thực hiện (01/11/2026):** bắt đầu bằng audit legacy offline và hai constant baselines; theo dõi phạm vi, lệnh chạy, bằng chứng và các dependency còn thiếu tại [revision/README.md](revision/README.md). Target/metric contract nằm tại [revision/target_contract.md](revision/target_contract.md). Chưa đóng R1 hoặc coi audit 180 điểm cũ là kết quả confirmatory mới.

**Việc cần làm**

- [ ] Tái tính class support, confusion matrix, accuracy, BA, MCC, macro-F1, precision/recall/F1 từng lớp cho mọi mã, fold, regime và repeat; phân biệt pooled và macro-average.
- [ ] Thêm constant DOWN/CASH, constant UP/always-LONG cycles, majority-class fit trên train, buy-and-hold thực sự, momentum cố định, logistic regression và một baseline factor-only không LLM. Phân biệt majority nhìn từ test chỉ dùng mô tả với majority được huấn luyện hợp lệ.
- [ ] Logistic có ít nhất hai cấu hình: chỉ indicator/OHLCV và cùng indicator + alpha + sentiment/missingness. Chuẩn hóa, imputation, chọn tham số, threshold chỉ fit trên train/validation. Baseline chỉ có giá và baseline cùng thông tin trả lời các câu hỏi khác nhau, phải ghi rõ.
- [ ] Báo tỷ lệ LONG, turnover, exposure, số lệnh, net return, daily drawdown và chi phí. Thêm control exposure tương đương được xác định từ train, để đánh giá lợi ích vượt hành vi giảm giao dịch.
- [ ] Nếu cần gọi “direction forecasting”, bổ sung target gross return riêng; giữ nguyên target net cho replication. Không đổi target sau khi thấy kết quả để tăng accuracy.
- [ ] Viết lại abstract/highlights/introduction/conclusion sau kết quả mới; bỏ suy luận “alpha lift = alpha information value” từ phép so sánh Full vs baseline bundle.

**Đầu ra:** bảng baseline đầy đủ, bảng confusion/imbalance và tài liệu định nghĩa target. **Đạt khi:** mọi baseline cùng lịch, chi phí và dữ liệu hợp lệ; không che việc thua cash hoặc baseline đơn giản; undefined metric được ghi NA với quy ước rõ ràng. **Sửa tại:** `utils/statistical_tests.py`, `core/backtest_engine.py`, runner baseline mới, sections 03/05/06/08 và front matter.

### R2 — Mẫu ngắn, một regime và phụ thuộc chéo [P1]

**Vấn đề:** 20 cutoff/mã chủ yếu từ giữa tháng 6 đến giữa tháng 9/2026. Chín mã có yếu tố thị trường chung và lịch gần nhau; không phải chín replication độc lập.

**Việc cần làm**

- [ ] Thu thập snapshot lịch sử nhiều năm, mục tiêu khả thi ban đầu **2020–2026**, kèm warm-up trước fold đầu. Chốt khoảng cụ thể sau kiểm tra coverage; chỉ dùng ngày đã có dữ liệu và label đã trưởng thành.
- [ ] Giữ chín mã để replication; mở rộng một universe có quy tắc point-in-time, chẳng hạn thành phần VN30 lịch sử hoặc tập thanh khoản định nghĩa trước. Không dùng thành phần chỉ số hiện tại để đại diện quá khứ; ghi delisting, listing date, missing/suspension và selection bias.
- [ ] Dùng rolling/expanding outer folds, inner validation theo thời gian; purge các mẫu có label span chạm tập test và fit lại toàn bộ preprocessing/selection trong train.
- [ ] Regime tăng/giảm/đi ngang, volatility và liquidity được gán bằng quy tắc chỉ dùng dữ liệu đã quan sát tại cutoff. Báo số cutoff, số phiên độc lập, class balance, exposure từng regime; không chỉ nêu tên năm.
- [ ] Resample block thời gian **đồng bộ cả panel mã và các nhánh**, giữ market shock chung. Lịch không trùng nhau phải join theo ngày lịch giao dịch và giữ missing mask, không ghép theo `test_id`.
- [ ] Tách backtest lịch sử với nguy cơ LLM đã biết dữ liệu khỏi đánh giá sau mốc đóng băng model/protocol. Multi-year với model mới không mặc nhiên sạch contamination. Model release date không tự chứng minh training cutoff, càng không bao phủ vision model hoặc aliases thay đổi.
- [ ] Bắt đầu prospective holdout từ phiên đầu tiên sau khi freeze; thời lượng dựa trên power/precision và độ đa dạng regime. Không hứa có nhiều năm dữ liệu prospective ngay trong vòng sửa này.

**Đầu ra:** `data_manifest`, `folds`, `regime_labels`, báo cáo panel và contamination. **Đạt khi:** có đánh giá qua nhiều trạng thái thị trường, độ bất định phù hợp phụ thuộc; tách rõ historical/exploratory và confirmatory. **Sửa tại:** loader, engine, runner mới, sections 05/06/07.

### R3 — Biến thiên giữa các lần chạy [P1]

**Vấn đề:** spread 15–20 pp giữa các bảng không nhỏ so với lift 13,9 pp; shared upstream không khử randomness của Decision Agent. Các bảng còn khác lịch nên chưa phải matched repeated runs.

**Việc cần làm**

- [ ] Tạo manifest so sánh toàn bộ cấu hình “default”: cutoff IDs, data hash, prompt hash, model/provider, token caps, temperature, code commit, fallback và order.
- [ ] Thiết kế hai tầng: **Decision-only repeats** trên upstream snapshot cố định (khởi điểm 10 repeat) và **end-to-end repeats** có tạo lại upstream (khởi điểm 5 repeat). Chốt R bằng pilot variance/budget trước final test, không coi 5/10 là bảo đảm đủ power.
- [ ] Mỗi repeat có run ID mới, không được resume checkpoint của repeat trước; chỉ resume các request chưa xong trong đúng run ID.
- [ ] Cân bằng/thay thứ tự gọi các variant giữa repeats, giữ model revision và cấu hình; lưu request ID/timestamp và mọi retry/fallback. Seed Python/NumPy không thay thế seed hay tính xác định của hosted API.
- [ ] Báo mean, SD, median/range, CI cho BA, MCC, accuracy, lift, return; disagreement rate theo cutoff và variance giữa upstream/decision.
- [ ] Khi inference, resample run ở đúng cấp cùng block thời gian; không biến 180 quyết định lặp R lần thành 180R thị trường độc lập. Nếu triển khai ensemble thì đánh giá ensemble riêng, không lấy kết quả tốt nhất trong R.

**Đầu ra:** bảng repeated-run trên cùng support, variance decomposition, request archive. **Đạt khi:** mọi cấu hình chính có phân bố kết quả, kết luận theo phân bố thay vì một run. **Sửa tại:** engine, robustness/ablation runners, thống kê và sections 05/06.

### R4 — Không tách alpha, sentiment và ảnh hưởng cấu trúc prompt [P0/P1]

**Vấn đề:** No-Alpha hiện bỏ cả alpha và sentiment. Hai nhánh khác cả thông tin, độ dài và cấu trúc prompt. Four-way hiện chỉ ba mã, provenance chưa được xác nhận.

**Việc cần làm**

- [ ] Đổi tên control lịch sử thành `No-factor/no-sentiment` hoặc `Base reports`; dùng `Full − Base` cho bundle effect.
- [ ] Chạy factorial 2×2 trên cùng universe/folds/repeats: B=(0,0), A=(1,0), S=(0,1), AS=(1,1). Khi diễn giải alpha trong môi trường có sentiment, so sánh **AS−S**; alpha khi không sentiment là **A−B**. Tương tự sentiment: AS−A và S−B.
- [ ] Thêm placebo giữ nguyên headings, schema, vị trí, phong cách và token budget: alpha hoán vị/lấy từ lịch sử đã có trước cutoff; random values có phân phối học từ train; thêm neutral/missing report cùng cấu trúc để tách missingness và nội dung.
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
- [ ] Tạo tập tin tài chính gán nhãn độc lập, khởi điểm 300–500 bài cân đối mã/thời kỳ/nhãn với ít nhất hai người có hướng dẫn rõ; adjudication, agreement và CI cho macro-F1/per-class recall. Chọn kích thước bằng precision mục tiêu; tách tập fine-tune/calibration khỏi test và ablation trading.
- [ ] Freeze model/tokenizer revision, truncation policy, mapping labels, fallback; rescore dữ liệu mới dưới provenance mới. Không sửa legacy-unknown thành ViSoBERT bằng suy đoán.

**Đầu ra:** article-level manifest, cutoff coverage table, domain evaluation và response giải thích 8180/180. **Đạt khi:** không còn count/percentage mâu thuẫn; sentiment claim bị giới hạn theo coverage và validation. **Sửa tại:** cache loader, sentiment agent/audit, tests coverage/leakage/ViSoBERT, sections 02/03/04/05 và phụ lục.

### R8 — Novelty, QuantAgent và ý nghĩa knowledge fusion [P1, attribution P0]

**Việc cần làm**

- [ ] Lập bảng provenance cấp component/file/prompt với commit upstream đã dùng: Indicator/Pattern/Trend/Decision, shared state, chart utilities, trendline fitting; phân loại reused, modified, new và mô tả thay đổi thực chất.
- [ ] Khôi phục đầy đủ MIT license/copyright notice của phần tái sử dụng, ghi attribution trong code/README/bài. Repository upstream hiện redirect sang QuantHarness [S1]; dùng commit/version lịch sử thích hợp, không diff tùy tiện với HEAD mới.
- [ ] Không nhận vision chart analysis và kiến trúc bốn agent gốc là novelty của bài này. Đóng góp mới có thể bảo vệ là alpha registry/selector, sentiment có cutoff, protocol đánh giá và cơ chế fusion nếu thực sự có.
- [ ] Sửa “high-frequency trading”, “K-line” gây hiểu nhầm thành daily-bar candlestick analysis và horizon cụ thể. Thay prompt phải version và chạy lại những kết quả chịu ảnh hưởng.
- [ ] Mô tả trung thực phiên bản hiện tại là prompt-level/late fusion của text reports; structured state và prompt concatenation chưa tự chứng minh có knowledge reasoning mới.
- [ ] Hướng tăng đóng góp cho KBS: biểu diễn từng evidence bằng schema gồm nguồn, cutoff, target/horizon, direction, độ tin cậy được kiểm chuẩn, missingness, provenance; phát hiện xung đột và xử lý bằng rule/weight học trên train. Xuất trace bằng evidence IDs, kiểm tra factual consistency thay vì coi lời giải thích của LLM là chứng minh đúng.
- [ ] So sánh concat hiện tại, equal vote/rule fusion, learned non-LLM fusion và fusion đề xuất trên cùng reports/repeats/token budget. Thêm QuantAgent-derived base, single LLM cùng evidence, và ablation vision nếu claim lợi ích multi-agent/multimodal. Báo cost/token/latency để biện minh độ phức tạp.

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
- [ ] So sánh dynamic top-5 với tập 5 factor cố định định trước, random eligible top-5 với nhiều seed, simple momentum/factor vote và không sign-flip. Random factor selection khác với placebo đổi giá trị factor ở R4.
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
3. Cơ chế fusion/multi-agent có lợi ích vượt concatenation, single LLM và deterministic/learned fusion không?
4. Những lợi ích đó bền qua folds/regimes/repeats và tạo giá trị sau phí trên ledger khả thi đến mức nào?

Chọn **BA là primary predictive metric**; MCC, per-class precision/recall, raw accuracy là secondary. Net return, daily MTM drawdown, exposure và trade count là economic metrics riêng. Chốt mức cải thiện có ý nghĩa thực tế trước final test bằng power/precision simulation, không lấy lift 13,9 pp cũ làm giả định chắc chắn.

Primary contrasts đề xuất: A−B; AS−S; true alpha−placebo tương ứng; Full−baseline non-LLM mạnh nhất **đã chọn bằng validation**. Áp family-wise control cho tập contrast này. Không chọn baseline mạnh nhất bằng final-test outcome rồi diễn giải p-value như đã đăng ký trước.

### 4.2. Matrix tối thiểu cần chạy

| Nhóm | Cấu hình | Phạm vi |
|---|---|---|
| Replication legacy | 9 mã, đúng cutoffs/chi phí/cấu hình lịch sử nếu khôi phục được | Chẩn đoán và đối chiếu reviewer, không tái dùng làm untouched test |
| Naive/economic | CASH, UP từng cycle, train-majority, buy-and-hold | Toàn bộ mã/folds/regimes; buy-and-hold có lịch giao dịch và corporate-action handling riêng rõ ràng |
| Non-LLM | Momentum, logistic cùng numeric features, factor-only vote/model | Cùng snapshot, horizon, chi phí, nested tuning |
| Factorial | B, A, S, AS | Cùng cutoffs và repeat IDs; không chỉ 3 mã |
| Placebo | Neutral/missing shell, causal shuffled/random alpha | Cùng headings/budget/coverage, nhiều seed đã định trước |
| Selection | Dynamic, fixed factors, random eligible factors, sign policy | Cùng selector training contract |
| Architecture | QuantAgent-derived base, single LLM, concat, explicit fusion; bỏ vision nếu claim vision | Validation để freeze; confirmatory contrasts chốt trước |
| Robustness | W=30/45/60, normalization/weights, horizon, chi phí, liquidity và regime | Phân biệt sensitivity với model selection; không chọn ô tốt nhất để làm headline |
| Variance | Fixed-upstream decision repeats + end-to-end repeats | Tất cả cấu hình dùng để đưa ra kết luận chính |

Để tiết kiệm chi phí: numerical baselines/alpha diagnostics chạy trước; upstream reports dùng chung trong phạm vi được phép; full grid tuning trên development set, final evaluation chỉ chạy cấu hình/contrast đã freeze. Không tiết kiệm bằng cách bỏ baseline hoặc repeats cần thiết rồi vẫn giữ claim mạnh.

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
- Report CI/effect size kèm số ngày, folds, mã và runs. Phân biệt uncertainty do market sample và do inference stochasticity. Không coi stock, folds chồng lấn hoặc repeats là độc lập tùy tiện.
- Nếu effect biến mất trước CASH, non-LLM hoặc placebo, nêu thẳng. Có thể xây dựng nghiên cứu về điều kiện thất bại/benchmark hoặc cơ chế tốt hơn rồi đánh giá trên holdout mới; không đổi mục tiêu sau hoc và gọi đó là confirmatory success.
- Predictive benefit không đủ để claim profitability; return dương vài mã không đủ để claim portfolio alpha. Kết luận phải khớp loại bằng chứng thực tế.

## 5. Lộ trình thực hiện theo dependency

Ước lượng bên dưới là thời gian làm việc, chưa gồm thời gian chờ dữ liệu, quota LLM hay prospective holdout. Không phải cam kết nộp trong một số tuần cố định. Owner là vai trò cần phân công, chưa phải người đã được chỉ định.

| Giai đoạn | Công việc / reviewer | Owner | Ước lượng | Điều kiện qua giai đoạn |
|---|---|---|---|---|
| G0 — Đóng băng và audit | Version submission, snapshot/hash, R6, R7, R9, R16 | Lead + data/software | 2–4 ngày | Có audit report; legacy nào verified/unverified được xác định; không dùng branch nghi vấn làm ground truth |
| G1 — Sửa hợp đồng tính toán | R5, R11–R15; paths/schema/metric/provenance | Software + quant | 3–6 ngày | Meaningful tests pass; raw-to-table replay nhất quán; date/settlement/labels rõ |
| G2 — Chuẩn bị nghiên cứu | Data nhiều năm, universe/folds, reference/attribution, sentiment labels, fusion design | Data + methods + NLP | 1–2 tuần, có thể lâu hơn | Data coverage report; protocol và primary contrasts freeze; model identity có evidence |
| G3 — Pilot development | Baselines, placebo, factorial, repeat variance; ước lượng call budget/power | Methods + software | 3–5 ngày | Chốt sample/repeat/cost, không dùng final-test outcome để quyết định |
| G4 — Chạy đánh giá khóa trước | R1–R4, R8, R10; end-to-end runs, holdout | Experiment owner | 1–3 tuần tùy tài nguyên | Complete manifest, errors có policy, đủ repeats/support, không cherry-pick |
| G5 — Phân tích và viết lại | R1–R18, dependency-aware statistics, all tables/figures | Quant + lead | 4–7 ngày | Claim–evidence matrix; tất cả numbers sinh từ artifacts, references đúng |
| G6 — Tái lập và nộp | Fresh environment replay, full PDF QA, response/cover letter/DOI | Người kiểm tra + corresponding author | 2–4 ngày | Qua checklist mục 8 và xác định được route nộp theo decision letter |

Dependency chính: **G0 → G1 → G2 → G3 → G4 → G5 → G6**. Metadata tác giả, reference audit và kiểm tra giấy phép có thể làm đồng thời với chuẩn bị dữ liệu. Prospective collection bắt đầu sau protocol freeze và có lịch hoàn thành riêng; không đánh tráo bằng backtest lịch sử.

### 5.1. Danh sách việc triển khai đầu tiên

- [ ] **T01** Tạo manifest/hash cho submitted PDF/TeX/comments và toàn bộ result/cache; xác định version chính thức của submission.
- [ ] **T02** Xuất independent audit 180 points: confusion/baselines/cycle return/NW và reproduction Table 7.
- [ ] **T03** Audit duplicate sequences và lineage toàn bộ checkpoint; giải quyết R6 trước khi dùng Table 9.
- [ ] **T04** Chạy lại coverage từ raw articles qua đúng availability rules; sửa script paths và generated CSV/TeX invariants.
- [ ] **T05** Sửa annualisation Sharpe/Sortino, canonical price fields/labels, daily equity và settlement contract.
- [ ] **T06** Sửa citations sai, provenance QuantAgent, text/prompt conventions và thống nhất source/build.
- [ ] **T07** Thêm immutable snapshot loader, request archive, full cache key và resume validation.
- [ ] **T08** Implement baselines cùng feature contract và nested temporal selector.
- [ ] **T09** Implement factorial/placebo/repeat runner và panel inference; simulation-check dưới null.
- [ ] **T10** Freeze protocol, data/folds, budget và power/precision criteria; mới bắt đầu confirmatory run.

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
- [ ] Repeats, regimes và holdout cho thấy effect không chỉ là một lần chạy hoặc giảm tỷ lệ LONG; kết quả âm cũng được trình bày.
- [ ] Claim alpha/sentiment riêng có four-way contrasts và coverage hợp lệ; novelty/fusion có provenance và comparator đúng.
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

Audit này đã đọc bản thảo/nhận xét, kiểm tra mã liên quan và tái tính các chẩn đoán nêu trên. Chưa chạy model mới, chưa khôi phục được raw responses lịch sử, chưa xác minh đầy đủ mọi reference hoặc mọi quy tắc giao dịch theo năm, và chưa xây dựng dữ liệu nhiều năm. Những phần đó là công việc cụ thể của kế hoạch, không phải kết quả đã hoàn thành. Lượt này chỉ tạo `plan.md`; không sửa kết quả nghiên cứu, bản thảo hay thực hiện nộp/publish.
