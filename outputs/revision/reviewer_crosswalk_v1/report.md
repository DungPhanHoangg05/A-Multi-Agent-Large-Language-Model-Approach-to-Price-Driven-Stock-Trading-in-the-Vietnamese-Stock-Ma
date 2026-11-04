# Đối soát đủ nhận xét reviewer trước khi sửa bài

Đã đối soát **18/18 nhận xét, 87 yêu cầu con** từ DOCX gốc với evidence và source hiện hành. **0/18 comments đóng**, mọi locator PDF cuối còn pending; T29 không tự quyết định T30.

Nguồn DOCX: SHA-256 `614f6d6fee623ed1eb124019fed3489d432d93a1316a4b3714266d15c706f15a`; text nằm trong source_comments.json, paragraph/offset là vị trí XML, không trang Word/PDF. Không sửa/stage/upload DOCX. Review heading không ghi năm nên review_year=null.

Ma trận lịch sử có 43 dòng/11 nhận xét, thiếu R7, R8, R9, R10, R16, R17, R18. Các status addressed/closed, số liệu và trang cũ trong revision/reviewer_matrix.csv, response_to_reviewers.md và README giữ nguyên như lịch sử; không có giá trị đóng final comments.

crosswalk.json/CSV là bản phân tích T29: mỗi yêu cầu có anchor nguyên văn, evidence paths, giới hạn, action sửa bài/response và source locator hiện tại. Không phải response đã gửi hoặc checklist tiến độ mới.

| Reviewer | Yêu cầu con | Evidence và action còn chờ |
|---|---:|---|
| R1 | 7 | Main 102 units, 25 UP/77 DOWN; imbalance/CASH và common information-set limits; mean account return không là portfolio. Không alpha/profitability/superiority claim. Sửa nguồn/response/locator sau gate; chưa đóng. |
| R2 | 4 | 102 units/12 dates/sáu blocks; survivor/universe và historical contamination chưa xác minh, không prospective; strata post-inference, ít temporal clusters. Sửa nguồn/response/locator sau gate; chưa đóng. |
| R3 | 4 | Chỉ hai panels chín units, ba executions; không lặp mọi config/grid, không crossed upstream×Decision design. 40 order deviations/chín cross-epoch groups; served weights unknown. Sửa nguồn/response/locator sau gate; chưa đóng. |
| R4 | 5 | Base bỏ alpha lẫn sentiment; Full−Base là bundle. Một rank-vector donor/cutoff, không name-matched/exposure-matched; không semantic/causal information-effect certification. Sửa nguồn/response/locator sau gate; chưa đóng. |
| R5 | 5 | Intervals/HAC là diagnostics mẫu nhỏ, chưa hiệu chuẩn coverage/FWER. Daily ledger ratios theo convention; cycle schedules gapped không tự annualise. Sửa nguồn/response/locator sau gate; chưa đóng. |
| R6 | 3 | Fingerprint/byte-copy không chứng nhận nhãn branch, execution commit hoặc paired independence lịch sử. Không sửa/relabel raw để khớp giải thích. Sửa nguồn/response/locator sau gate; chưa đóng. |
| R7 | 8 | Legacy 180 records/177 identities, scorer unknown; missing không neutral. Tác giả xác nhận chưa có nhãn: domain tài chính/news PIT chưa validation, rescore không thay validation. Sửa nguồn/response/locator sau gate; chưa đóng. |
| R8 | 5 | Reused/modified/new-to-comparison không bằng scientific novelty. Prompt heuristic aggregation không là learned fusion, calibrated weights hoặc guaranteed conflict resolution. Sửa nguồn/response/locator sau gate; chưa đóng. |
| R9 | 6 | Package local/private; quyền chia sẻ/PID chưa có, submission snapshot/immutable hosted weights chưa xác minh. Current catalogue không chứng nhận model lịch sử. Sửa nguồn/response/locator sau gate; chưa đóng. |
| R10 | 6 | Native row-wise causal gate FAIL; native scores in-sample. Causal train-fit numeric controls không replay native LLM selector hoặc chữa frozen study; không fixed/random qua LLM. Sửa nguồn/response/locator sau gate; chưa đóng. |
| R11 | 2 | Giữ net target primary, SHORT=CASH; actual_prev_close legacy không xác thực decision Close. Không đổi label/raw để khớp nguồn bài. Sửa nguồn/response/locator sau gate; chưa đóng. |
| R12 | 4 | Missing/error vẫn nằm denominator năm; report text không là numeric state arrays. BB/ADX declared slots khác actual Indicator delivery; không phải volatility votes. Sửa nguồn/response/locator sau gate; chưa đóng. |
| R13 | 3 | Prototype/registry/current selected rank slot khác nhau; Volume OHLCV proxy không là signed order flow; không sửa formula frozen. Sửa nguồn/response/locator sau gate; chưa đóng. |
| R14 | 3 | Body theo Close/Open, khác bảng điện Close/reference; doji red không suy bearish. Kiểm pixel/template không xác thực VLM semantics; từ xanh Việt còn mơ hồ. Sửa nguồn/response/locator sau gate; chưa đóng. |
| R15 | 3 | Maturity chiều T+2 có điều kiện; daily OHLC không chứng nhận fill/limit-order/allocation/corporate actions/volume units. L=3 không được chứng minh optimal. Sửa nguồn/response/locator sau gate; chưa đóng. |
| R16 | 10 | T21 kiểm danh tính/claim của 41 entries; không invent DOI. Số [14]/[21]/[22]/[23] thuộc bản reviewer đọc, chưa gán tự động vào thứ tự BibTeX hiện tại. Sửa nguồn/response/locator sau gate; chưa đóng. |
| R17 | 6 | Chưa sửa nguồn hoặc build PDF trước T30; trang/figure/table numbering lịch sử không là locator hiện hành. Title không được hứa profitability/causal novelty. Sửa nguồn/response/locator sau gate; chưa đóng. |
| R18 | 3 | Không đoán tên chuẩn/thứ tự/ORCID/affiliation/CRediT/route nộp lại. Chỉ ghi observed values; chủ thể tác giả phải xác nhận tại T33. Sửa nguồn/response/locator sau gate; chưa đóng. |

## Các điểm phải mang qua T30–T35

Main cuối có 102 units, 25 UP/77 DOWN, 12 dates/sáu blocks. Hai panels repeats/factorial có chín units riêng, không lấy panel tốt thay main hoặc gộp old chart Decisions. Giữ 40 order deviations/chín cross-epoch groups. Nguồn hiện tại vẫn còn số 65/51,1 và các mô tả isolated alpha, fusion, proprietary, inverted chart, Sharpe và label schema cần sửa. Đây là đích sửa, không tuyên bố đã sửa.

Native row-wise causal gate FAIL; T28 detection tests PASS không sửa giới hạn đó. T08 đã chốt chưa có nhãn/domain/news PIT validation, nên bỏ claims phụ thuộc. T13 controls chỉ numeric train-fit; fixed/random qua LLM và causal factor contribution chưa được chứng minh.

R9: package nội bộ chưa có public rights/PID; historical catalogue/immutable weights chưa xác minh. Không coi current provider listing là model lịch sử, không invent DOI hoặc tự upload. R18: cần tác giả xác nhận master record; có observed Phuong-Thai ORCID mismatch giữa main và commented submit. author_pending.json chỉ nêu values cần xác nhận, không chọn canonical identity.

R16: T21 audit đủ 41 entries, gồm ba DOI sai identity và một herding entry chưa verified. Số references reviewer đọc không tự map bằng vị trí BibTeX hiện tại; kiểm title/citation/version khi sửa/build, thiếu DOI giữ unknown. Câu dẫn sai scope phải sửa hoặc bỏ cùng entry.

R17: sau T30 chọn outline/title ở T31; T32 đồng bộ hai entrypoints, shared sections, figures và bibliography một lượt, dời chi tiết Flask/tokenizer/API/full prompts về repo/supplement phù hợp. T34 trả lời từng yêu cầu sau thay đổi thực; T35 build/QA cả hai PDF và chốt locators mới. Không dùng trang PDF lịch sử. Ví dụ hyphen reviewer nêu không còn trong current sources; dấu ngoặc kép và double periods còn cần kiểm render, không mặc định vẫn lỗi hoặc đã hết lỗi.

## Chi tiết action theo nhận xét

### R1

Main 102 units, 25 UP/77 DOWN; imbalance/CASH và common information-set limits; mean account return không là portfolio. Không alpha/profitability/superiority claim.

- **R1.1 — Class balance theo mã và pooled.** (evidence_ready_manuscript_pending): Báo 25 UP/77 DOWN trên 102 units, support từng lớp/mã/cohort; legacy 180 giữ riêng. Evidence: [classification.csv](../../../outputs/revision/final_baselines_v1/classification.csv); [per_class.csv](../../../outputs/revision/final_baselines_v1/per_class.csv)
- **R1.2 — BA, MCC và precision/recall cả hai lớp cho Full/Base.** (evidence_ready_manuscript_pending): Dùng bảng cuối T24 với BA primary, null/NA và macro n_defined; không ưu tiên imbalance accuracy. Evidence: [classification.csv](../../../outputs/revision/final_baselines_v1/classification.csv); [per_class.csv](../../../outputs/revision/final_baselines_v1/per_class.csv); [report.md](../../../outputs/revision/final_baselines_v1/report.md)
- **R1.3 — Majority và always-CASH theo mã.** (evidence_ready_manuscript_pending): Majority fit purged train, tie rule cố định; CASH là constant baseline, không fit majority bằng test labels. Evidence: [baseline_contracts.json](../../../outputs/revision/final_baselines_v1/baseline_contracts.json); [classification.csv](../../../outputs/revision/final_baselines_v1/classification.csv)
- **R1.4 — Buy-and-hold và kinh tế so với CASH.** (evidence_ready_manuscript_pending): Tách continuous hold một position với per-cycle always-LONG; nêu phí, gaps và bình quân accounts riêng. Evidence: [financial.csv](../../../outputs/revision/final_baselines_v1/financial.csv); [baseline_contracts.json](../../../outputs/revision/final_baselines_v1/baseline_contracts.json)
- **R1.5 — Momentum và logistic cùng support/information inputs.** (evidence_ready_manuscript_pending): Báo momentum, logistic-price, matched numeric inputs và factor vote; nói representation khác chart/text/pretraining, không exact-information equivalence. Evidence: [baseline_contracts.json](../../../outputs/revision/final_baselines_v1/baseline_contracts.json); [report.md](../../../outputs/revision/final_baselines_v1/report.md)
- **R1.6 — Exposure/LONG propensity có thể giải thích lift.** (partial_explicit_limit): Báo LONG rate/exposure/recall; không đổi thua ít thành alpha hoặc khẳng định đã exposure-match causal effect. Evidence: [financial.csv](../../../outputs/revision/final_baselines_v1/financial.csv); [classification.csv](../../../outputs/revision/final_baselines_v1/classification.csv); [contrasts.csv](../../../outputs/revision/final_repeats_v1/contrasts.csv)
- **R1.7 — Đổi kết luận theo baselines mới.** (evidence_ready_manuscript_pending): Thay các số 65/51,1 và isolated-alpha claims ở cả entrypoints/introduction/results/conclusion bằng kết quả T04/T24 và scope exploratory. Evidence: [report.md](../../../outputs/revision/final_baselines_v1/report.md); [financial.csv](../../../outputs/revision/final_baselines_v1/financial.csv); [response_to_reviewers.md](../../../revision/response_to_reviewers.md)

### R2

102 units/12 dates/sáu blocks; survivor/universe và historical contamination chưa xác minh, không prospective; strata post-inference, ít temporal clusters.

- **R2.1 — Mở rộng LLM thật qua nhiều năm.** (partial_explicit_limit): Trình bày sáu blocks 2023H2–2026Q3, 102 units/12 ngày; không mô tả là full daily multi-year backtest. Evidence: [report.md](../../../outputs/revision/final_temporal_v1/report.md); [calendar_panel.csv](../../../outputs/revision/final_temporal_v1/calendar_panel.csv)
- **R2.2 — Regime tăng/giảm và bias CASH.** (evidence_ready_manuscript_pending): Nêu rule causal per-security trend, vol/liquidity thresholds train-only, class counts và exposure; không gọi index-regime policy validation. Evidence: [stratified_metrics.json](../../../outputs/revision/final_temporal_v1/stratified_metrics.json); [report.md](../../../outputs/revision/final_temporal_v1/report.md)
- **R2.3 — Inference giữ phụ thuộc cross-section.** (evidence_ready_manuscript_pending): Bỏ Wilcoxon symbols-independent làm chứng minh; whole-block paired resampling/HAC lags0/1/2 và caveat sáu clusters. Evidence: [panel_hac.csv](../../../outputs/revision/final_temporal_v1/panel_hac.csv); [report.md](../../../outputs/revision/final_temporal_v1/report.md)
- **R2.4 — Mẫu hiệu dụng không bằng số symbol×points.** (evidence_ready_manuscript_pending): Báo calendar alignment, sáu BHN exclusions, cohort overlap, purged folds; không nhân N bằng symbols/repeats. Evidence: [calendar_panel.csv](../../../outputs/revision/final_temporal_v1/calendar_panel.csv); [folds.csv](../../../outputs/revision/final_temporal_v1/folds.csv); [report.md](../../../outputs/revision/final_temporal_v1/report.md)

### R3

Chỉ hai panels chín units, ba executions; không lặp mọi config/grid, không crossed upstream×Decision design. 40 order deviations/chín cross-epoch groups; served weights unknown.

- **R3.1 — Giải thích defaults cùng tên nhưng outcomes khác.** (evidence_ready_manuscript_pending): Giữ audit cutoff/provenance legacy unknown, SDK T=1e−8 dù configured0, seed API absent; không gọi khác bảng là treatment effect. Evidence: [report.md](../../../outputs/revision/final_repeats_v1/report.md); [disagreement.csv](../../../outputs/revision/final_repeats_v1/disagreement.csv)
- **R3.2 — Lặp cấu hình thật và nói rõ support.** (partial_explicit_limit): Báo ba upstream executions B/AS và ba Decision repeats B/A/S/AS/P trên hai panels chín units riêng; mọi config legacy chưa được repeat. Evidence: [repeat_summary.csv](../../../outputs/revision/final_repeats_v1/repeat_summary.csv); [pairing.csv](../../../outputs/revision/final_repeats_v1/pairing.csv)
- **R3.3 — Mean/SD/range/disagreement.** (evidence_ready_manuscript_pending): Đưa per-execution distributions và contrasts, sample SD ddof1, không best run/ensemble hoặc gán panel SD cho main102. Evidence: [repeat_summary.csv](../../../outputs/revision/final_repeats_v1/repeat_summary.csv); [disagreement.csv](../../../outputs/revision/final_repeats_v1/disagreement.csv); [contrasts.csv](../../../outputs/revision/final_repeats_v1/contrasts.csv)
- **R3.4 — Inference đúng repeated support.** (evidence_ready_manuscript_pending): Nêu joint block/run draws và finite denominators, order/epoch deviations; không trừ SD để tách variance components. Evidence: [contrasts.csv](../../../outputs/revision/final_repeats_v1/contrasts.csv); [report.md](../../../outputs/revision/final_repeats_v1/report.md)

### R4

Base bỏ alpha lẫn sentiment; Full−Base là bundle. Một rank-vector donor/cutoff, không name-matched/exposure-matched; không semantic/causal information-effect certification.

- **R4.1 — Định nghĩa Base đúng bundle.** (evidence_ready_manuscript_pending): Đổi No-Alpha thành Base/B khi phù hợp; Full−Base gồm alpha+sentiment+prompt structure, không isolated alpha. Evidence: [audit.json](../../../outputs/revision/fusion_prompt_audit_v1/audit.json); [baseline_contracts.json](../../../outputs/revision/final_baselines_v1/baseline_contracts.json)
- **R4.2 — B/A/S/AS dùng đúng parent/support.** (evidence_ready_manuscript_pending): Báo factorial 9 units×5variants×3 repeats=135 Decisions sau sửa chart, khác main102 và legacy3symbols. Evidence: [pairing.csv](../../../outputs/revision/final_repeats_v1/pairing.csv); [contrasts.csv](../../../outputs/revision/final_repeats_v1/contrasts.csv)
- **R4.3 — Placebo cùng schema/headings.** (partial_explicit_limit): Nêu P giữ names/schema/missingness/current sentiment, thay scalar/signal/skill bằng một past train-only rank-vector donor. Evidence: [donors.csv](../../../outputs/revision/final_repeats_v1/donors.csv); [report.md](../../../outputs/revision/final_repeats_v1/report.md)
- **R4.4 — Không đồng nhất content integrity và semantic effect.** (partial_explicit_limit): Nêu wording/routing/exposure và rank mapping limits; không gọi AS−P là causal information attribution hoặc chứng minh model dùng số. Evidence: [audit.json](../../../outputs/revision/fusion_prompt_audit_v1/audit.json); [contrasts.csv](../../../outputs/revision/final_repeats_v1/contrasts.csv)
- **R4.5 — Diễn giải interaction và best-single gap.** (evidence_ready_manuscript_pending): Phân biệt AS−A−S+B với AS−max(A,S), giữ family/undefined và không khôi phục synergy claim. Evidence: [contrasts.csv](../../../outputs/revision/final_repeats_v1/contrasts.csv); [report.md](../../../outputs/revision/final_repeats_v1/report.md)

### R5

Intervals/HAC là diagnostics mẫu nhỏ, chưa hiệu chuẩn coverage/FWER. Daily ledger ratios theo convention; cycle schedules gapped không tự annualise.

- **R5.1 — Bootstrap và exact discordance khác nhau.** (evidence_ready_manuscript_pending): Giữ audit discordant n01/n10 legacy, whole-block/CBB sensitivity và null coverage; không suy CI exclusions thành significance. Evidence: [report.md](../../../outputs/revision/final_temporal_v1/report.md); [panel_hac.csv](../../../outputs/revision/final_temporal_v1/panel_hac.csv)
- **R5.2 — HAC/Newey–West số liệu thật.** (evidence_ready_manuscript_pending): Báo effect/SE/p theo lags0/1/2 trên fixed-universe dates, n_dates12/6, giới hạn irregular calendar/small sample. Evidence: [panel_hac.csv](../../../outputs/revision/final_temporal_v1/panel_hac.csv); [report.md](../../../outputs/revision/final_temporal_v1/report.md)
- **R5.3 — N/mẫu số Mean row.** (evidence_ready_manuscript_pending): Legacy nếu giữ ghi N180; bảng primary mới ghi N102, không đổi nhãn N mà giữ số liệu cũ. Evidence: [report.md](../../../outputs/revision/final_baselines_v1/report.md); [calendar_panel.csv](../../../outputs/revision/final_temporal_v1/calendar_panel.csv)
- **R5.4 — Sửa annualisation cycle/daily.** (evidence_ready_manuscript_pending): Thay Eq.account Sharpe và setup/table bằng tần suất ledger đúng; cycle schedules gapped giữ annualised ratios NA, không áp sqrt252/sqrt84 tùy tiện. Evidence: [report.md](../../../outputs/revision/final_contracts_v1/report.md); [risk_cycles.csv](../../../outputs/revision/final_contracts_v1/risk_cycles.csv)
- **R5.5 — Ít trades và caveat risk ratios.** (evidence_ready_manuscript_pending): Nêu n_days/n_cycles/n_orders/undefined, convention Sortino và few-trade limitation; không diễn giải Sharpe như deployable performance. Evidence: [risk_cycles.csv](../../../outputs/revision/final_contracts_v1/risk_cycles.csv); [financial.csv](../../../outputs/revision/final_baselines_v1/financial.csv)

### R6

Fingerprint/byte-copy không chứng nhận nhãn branch, execution commit hoặc paired independence lịch sử. Không sửa/relabel raw để khớp giải thích.

- **R6.1 — Audit reused/copied checkpoints.** (unverified_historical_branch_identity): Giải thích fingerprint trùng/copy và checkpoint provenance unknown; byte equality không chứng nhận experiment identity. Evidence: [report.json](../../../outputs/revision/legacy_lineage_v1/report.json); [comparisons.json](../../../outputs/revision/legacy_lineage_v1/comparisons.json)
- **R6.2 — Có xác nhận được branch labels cũ không.** (unverified_historical_branch_identity): Không xác nhận khi thiếu raw prompts/parents; bỏ ablation legacy khỏi evidence attribution, giữ làm provenance audit. Evidence: [report.json](../../../outputs/revision/legacy_lineage_v1/report.json); [comparisons.json](../../../outputs/revision/legacy_lineage_v1/comparisons.json)
- **R6.3 — Xử lý số -7,85/-7,38 trùng panels.** (evidence_ready_manuscript_pending): Nêu exact duplicates thay vì suy cùng economic return là proof độc lập; dùng final T04 paired actual raw thay kết luận legacy. Evidence: [comparisons.json](../../../outputs/revision/legacy_lineage_v1/comparisons.json); [pairing.csv](../../../outputs/revision/final_repeats_v1/pairing.csv)

### R7

Legacy 180 records/177 identities, scorer unknown; missing không neutral. Tác giả xác nhận chưa có nhãn: domain tài chính/news PIT chưa validation, rescore không thay validation.

- **R7.1 — Giải quyết 8180 vs180 và đơn vị bài/point.** (evidence_ready_manuscript_pending): Báo legacy180 records/177 unique identities, per-symbol counts và duplicates; không gọi 8180 là snapshot được chứng nhận. Evidence: [inventory.json](../../../outputs/revision/sentiment_inventory_v1/inventory.json); [summary.json](../../../outputs/revision/sentiment_inventory_v1/summary.json)
- **R7.2 — Số bài thật theo mã và cutoff.** (evidence_ready_manuscript_pending): Tách corpus records/unique URLs và article memberships theo windows với số cutoffs; không lấy20 testpoints thành20 validated articles. Evidence: [inventory.json](../../../outputs/revision/sentiment_inventory_v1/inventory.json); [coverage.json](../../../outputs/revision/sentiment_coverage_v1/coverage.json)
- **R7.3 — Mâu thuẫn counts/percentages provenance.** (evidence_ready_manuscript_pending): V/L/U lấy metadata đã ghi; legacy0 verified/0 lexicon/180 unknown, counts và tỷ lệ chung một mẫu số; không xác thực ngược scorer. Evidence: [summary.json](../../../outputs/revision/sentiment_inventory_v1/summary.json); [summary.json](../../../outputs/revision/sentiment_coverage_v1/summary.json)
- **R7.4 — Ít bài và unavailable.** (evidence_ready_manuscript_pending): Dùng >=3 distinct valid articles; đủ bài neutral khác missing. Strict legacy coverage0/180; phân biệt runtime legacy counts có duplicates với audit corrected rule. Evidence: [coverage.json](../../../outputs/revision/sentiment_coverage_v1/coverage.json); [summary.json](../../../outputs/revision/sentiment_coverage_v1/summary.json)
- **R7.5 — Hệ quả với Sentiment-only FPT legacy.** (evidence_ready_manuscript_pending): Không gọi S legacy là sentiment information effect khi input/availability/identity chưa xác minh; không thay cache rồi giữ outcomes cũ. Evidence: [coverage.json](../../../outputs/revision/sentiment_coverage_v1/coverage.json); [report.json](../../../outputs/revision/legacy_lineage_v1/report.json)
- **R7.6 — Dẫn ViSoBERT và phân biệt backbone/classifier.** (evidence_ready_manuscript_pending): Dẫn paper ViSoBERT đúng, ghi5CD-AI downstream checkpoint/revision, label mapping và score recipe; không dùng citation thay validation. Evidence: [scorer_tokenizer.json](../../../outputs/revision/sentiment_contract_v1/scorer_tokenizer.json); [reference_audit.json](../../../outputs/revision/reference_audit_v1/reference_audit.json)
- **R7.7 — Domain mismatch và thiếu financial labels.** (missing_domain_labels_claim_withdrawal): Nêu nguồn social-media và chưa independent validation trên Vietnamese financial news; bỏ financial-accuracy/domain-validity claims. Evidence: [scorer_tokenizer.json](../../../outputs/revision/sentiment_contract_v1/scorer_tokenizer.json); [summary.json](../../../outputs/revision/sentiment_contract_v1/summary.json)
- **R7.8 — PIT của tin không suy từ ngày parse được.** (missing_news_pit_validation): Ghi date-only+1 ngày/cutoff là quy tắc kỹ thuật; nội dung và availability lịch sử chưa được xác thực độc lập. Evidence: [summary.json](../../../outputs/revision/sentiment_inventory_v1/summary.json); [summary.json](../../../outputs/revision/sentiment_coverage_v1/summary.json)

### R8

Reused/modified/new-to-comparison không bằng scientific novelty. Prompt heuristic aggregation không là learned fusion, calibrated weights hoặc guaranteed conflict resolution.

- **R8.1 — Attribution từng component.** (evidence_ready_manuscript_pending): Mô tả Indicator/Pattern/Trend/Decision, shared state, chart/trendline reused/modified; new-to-comparison không là proof novelty. Evidence: [attribution.json](../../../outputs/revision/quantagent_attribution_v1/attribution.json); [provenance.json](../../../outputs/revision/quantagent_attribution_v1/provenance.json)
- **R8.2 — Đóng góp alpha/sentiment/evaluation có giới hạn.** (evidence_ready_manuscript_pending): Giữ domain adaptation/implementation/protocol/empirical comparison; bỏ novelty của graph, chart vision hoặc report aggregation vốn đã có upstream. Evidence: [attribution.json](../../../outputs/revision/quantagent_attribution_v1/attribution.json); [audit.json](../../../outputs/revision/fusion_prompt_audit_v1/audit.json)
- **R8.3 — MIT license và copyright.** (evidence_ready_manuscript_pending): Dẫn LICENSES/QuantAgent-MIT.txt và notice; không áp MIT tự động cho author additions/OHLCV/news/models. Evidence: [QuantAgent-MIT.txt](../../../LICENSES/QuantAgent-MIT.txt); [THIRD_PARTY_NOTICES.md](../../../THIRD_PARTY_NOTICES.md); [attribution.json](../../../outputs/revision/quantagent_attribution_v1/attribution.json)
- **R8.4 — Prompt HFT/K-line so với daily bars.** (evidence_ready_manuscript_pending): Nêu actual inherited wording và daily horizon mismatch, đưa full prompts về supplement/repo; không sửa frozen prompt để khớp hình. Evidence: [prompt_inventory.json](../../../outputs/revision/quantagent_attribution_v1/prompt_inventory.json); [audit.json](../../../outputs/revision/fusion_prompt_audit_v1/audit.json)
- **R8.5 — Định nghĩa fusion/representation/conflict/weighting.** (partial_explicit_limit): Ghi prompt-level condensed-report aggregation với precedence/conflict heuristics; không learned representation/calibrated weighting/guaranteed compliance. Evidence: [audit.json](../../../outputs/revision/fusion_prompt_audit_v1/audit.json)

### R9

Package local/private; quyền chia sẻ/PID chưa có, submission snapshot/immutable hosted weights chưa xác minh. Current catalogue không chứng nhận model lịch sử.

- **R9.1 — Archive prices/news/data snapshots.** (partial_explicit_limit): Trỏ snapshots mới đúng nguồn/version/hash, không nhận là authenticated submission caches/snapshot cũ. Evidence: [manifest.json](../../../outputs/revision/reproducibility_v1/manifest.json); [summary.json](../../../outputs/revision/sentiment_inventory_v1/summary.json)
- **R9.2 — Pin dependencies thay latest.** (evidence_ready_manuscript_pending): Dùng runtime/requirements receipts; phân biệt Windows pins với universal offline wheelhouse, không latest. Evidence: [manifest.json](../../../outputs/revision/reproducibility_v1/manifest.json); [report.json](../../../outputs/revision/final_regression_v1/report.json)
- **R9.3 — Lưu prompts, reports, responses, errors và chi phí.** (evidence_ready_manuscript_pending): Báo 649 attempts cuối: 615 success, 34 error; 120 Pattern replay giữ chi phí calls gốc, missing jobs=0. Usage lỗi và chi phí tiền chưa biết, không điền zero. Evidence: [manifest.json](../../../outputs/revision/reproducibility_v1/manifest.json); [report.json](../../../outputs/revision/final_cost_integrity_v1/report.json)
- **R9.4 — Đúng model identifier và hồ sơ catalogue provider.** (missing_historical_provider_attestation): Giữ aliases thực trong raw, 40 fingerprints và 91 requests thiếu epoch. Catalogue lịch sử và immutable weights chưa xác minh; cần hồ sơ provider từ tác giả nếu muốn xác nhận thêm, không tự probe API. Evidence: [report.json](../../../outputs/revision/final_cost_integrity_v1/report.json); [audit.json](../../../outputs/revision/fusion_prompt_audit_v1/audit.json)
- **R9.5 — PID và quyền công bố.** (missing_rights_and_pid_author): T34 tác giả chốt quyền và tự publish package phù hợp lấy PID thật; chưa có thì pending, không invent DOI hoặc coi private ZIP là public archive. Evidence: [rights.json](../../../outputs/revision/reproducibility_v1/rights.json); [manifest.json](../../../outputs/revision/reproducibility_v1/manifest.json)
- **R9.6 — Replay offline không fetch lại.** (evidence_ready_manuscript_pending): Dẫn T23 clean replay đã PASS từ saved predictions, không gọi đó là inference mới hoặc validation experimental replicability của hosted weights. Evidence: [metrics_qa.json](../../../outputs/revision/clean_replay_v1/metrics_qa.json); [manifest.json](../../../outputs/revision/reproducibility_v1/manifest.json)

### R10

Native row-wise causal gate FAIL; native scores in-sample. Causal train-fit numeric controls không replay native LLM selector hoặc chữa frozen study; không fixed/random qua LLM.

- **R10.1 — Frequency đủ registry denominator.** (evidence_ready_manuscript_pending): Đưa selection count/eligible denominator/510 slots, per-symbol/block, không chỉ chọn factors thắng. Evidence: [aggregate.json](../../../outputs/revision/alpha_selection_v1/aggregate.json)
- **R10.2 — IC sign stability và orientation.** (evidence_ready_manuscript_pending): Báo adjacent sign flips/support/zero/undefined và native in-sample scope; không gọi stable generalisable alpha. Evidence: [transitions.json](../../../outputs/revision/alpha_selection_v1/transitions.json); [aggregate.json](../../../outputs/revision/alpha_selection_v1/aggregate.json)
- **R10.3 — Fixed pre-specified control.** (partial_numeric_not_llm_control): Nêu locked fixed set trong numeric train-fit study historical exploratory; không preregistered và không native LLM fixed-set experiment. Evidence: [numeric_controls_protocol.json](../../../revision/numeric_controls_protocol.json); [summary.json](../../../outputs/revision/numeric_controls_v1/summary.json)
- **R10.4 — Random family và multiplicity.** (partial_numeric_not_llm_control): Báo đủ seeds/random distribution/23-hypothesis Holm family; không chọn seed tốt hoặc suy superiority; chưa random-factor study qua LLM. Evidence: [inference.json](../../../outputs/revision/numeric_controls_v1/inference.json); [summary.json](../../../outputs/revision/numeric_controls_v1/summary.json)
- **R10.5 — 21 exclusions có lý do từng mục.** (evidence_ready_manuscript_pending): Liệt kê 21 IDs theo catalogue; ba price/volume omissions chưa có lý do giữ unexplained, không gộp tất cả thành thiếu cross-sectional inputs. Evidence: [registry.json](../../../outputs/revision/alpha_registry_v1/registry.json); [summary.json](../../../outputs/revision/alpha_registry_v1/summary.json)
- **R10.6 — Bản dịch và operators của từng biểu thức giữ lại.** (partial_native_causal_fail): Cung cấp source, handler, operator, window, ties và normalization của 80 biểu thức giữ lại cùng năm custom factors; phân biệt surrogate/prototype. Giữ row-wise causal FAIL và bỏ claims phụ thuộc. T10 còn sáu metadata mismatch slots trên sáu units; giữ đúng handler thực dùng, công khai lỗi mô tả và không suy đã đo tác động riêng lên LLM outcomes. Evidence: [registry.json](../../../outputs/revision/alpha_registry_v1/registry.json); [summary.json](../../../outputs/revision/alpha_contract_v1/summary.json); [leakage.json](../../../outputs/revision/alpha_contract_v1/leakage.json)

### R11

Giữ net target primary, SHORT=CASH; actual_prev_close legacy không xác thực decision Close. Không đổi label/raw để khớp nguồn bài.

- **R11.1 — Sửa label trong state schema.** (evidence_ready_manuscript_pending): Đồng bộ Table B.10 với net Open[e]→Close[e+2], fee/slippage mỗi chân, return>0 là UP; gross là diagnostic riêng. Evidence: [targets.json](../../../outputs/revision/final_contracts_v1/targets.json); [target_schema.json](../../../revision/target_schema.json)
- **R11.2 — Alias actual_prev_close.** (evidence_ready_manuscript_pending): Đặt canonical fields entry_open/decision_close khác nhau; legacy unknown decision_close=null, không rename alias rồi gán semantic cũ chưa được xác minh. Evidence: [targets.json](../../../outputs/revision/final_contracts_v1/targets.json); [report.md](../../../outputs/revision/final_contracts_v1/report.md)

### R12

Missing/error vẫn nằm denominator năm; report text không là numeric state arrays. BB/ADX declared slots khác actual Indicator delivery; không phải volatility votes.

- **R12.1 — Biên và thứ tự ưu tiên RSI.** (evidence_ready_manuscript_pending): Table 1 khớp thứ tự bearish>=70, bullish<=30 rồi 55<=RSI<70; mô tả vùng 45–55 theo code và rounding. Evidence: [indicators.json](../../../outputs/revision/final_contracts_v1/indicators.json); [report.md](../../../outputs/revision/final_contracts_v1/report.md)
- **R12.2 — Phân loại năm indicators.** (evidence_ready_manuscript_pending): Bỏ volatility oscillators; mô tả momentum/trend indicators đúng năm actual votes. Evidence: [indicators.json](../../../outputs/revision/final_contracts_v1/indicators.json); [report.md](../../../outputs/revision/final_contracts_v1/report.md)
- **R12.3 — BB/ADX khai báo khác dữ liệu thực gửi.** (evidence_ready_manuscript_pending): State schema không khẳng định có forwarded numeric arrays; Indicator node chỉ trả report/messages. BB tính riêng trong alpha path, ADX không là vote thứ sáu/bảy. Evidence: [indicators.json](../../../outputs/revision/final_contracts_v1/indicators.json); [report.md](../../../outputs/revision/final_contracts_v1/report.md)
- **R12.4 — Đồng bộ Table 1, Appendix D và report summary.** (evidence_ready_manuscript_pending): Nêu cross được ưu tiên, dấu current inclusive/previous strict, missing/error vẫn là neutral trong denominator năm; plurality/ties/confidence là heuristic, không coi output LLM là numeric oracle. Evidence: [indicators.json](../../../outputs/revision/final_contracts_v1/indicators.json); [report.md](../../../outputs/revision/final_contracts_v1/report.md)

### R13

Prototype/registry/current selected rank slot khác nhau; Volume OHLCV proxy không là signed order flow; không sửa formula frozen.

- **R13.1 — Alpha_4 đảo dấu khi volume z-score âm.** (evidence_ready_manuscript_pending): Giải thích tanh((%B−0,5)×VolZ5×1,5): z âm đảo dấu, z=0 triệt tiêu; không sửa code để làm đúng câu cũ. Evidence: [report.md](../../../outputs/revision/final_contracts_v1/report.md); [summary.json](../../../outputs/revision/alpha_contract_v1/summary.json)
- **R13.2 — Bỏ mô tả confirming expansion/squeeze không có gate.** (evidence_ready_manuscript_pending): Mô tả tích có dấu và proxy, preprocessing prototype khác registry; selected slot 4 không nhất thiết là BFE. Evidence: [report.md](../../../outputs/revision/final_contracts_v1/report.md); [registry.json](../../../outputs/revision/alpha_registry_v1/registry.json)
- **R13.3 — Custom thay proprietary.** (evidence_ready_manuscript_pending): Đổi thuật ngữ xuyên suốt phần chính/appendix/captions; giữ nguồn adapted/custom và giới hạn không order-flow measurement. Evidence: [registry.json](../../../outputs/revision/alpha_registry_v1/registry.json); [report.md](../../../outputs/revision/final_contracts_v1/report.md)

### R14

Body theo Close/Open, khác bảng điện Close/reference; doji red không suy bearish. Kiểm pixel/template không xác thực VLM semantics; từ xanh Việt còn mơ hồ.

- **R14.1 — Phân biệt quy ước bảng điện và màu thân nến.** (evidence_ready_manuscript_pending): Bỏ câu green bearish/red bullish; nêu màu theo Close/Open: green tăng, red giảm, doji red. Bảng điện so với reference price là quy ước khác. Evidence: [chart_replay.json](../../../outputs/revision/final_cost_integrity_v1/chart_replay.json); [report.md](../../../outputs/revision/final_cost_integrity_v1/report.md)
- **R14.2 — Renderer, legend và PNG thực gửi.** (evidence_ready_manuscript_pending): Dẫn 204 PNG/102 units render lại khớp và 240 Vision requests/cache; support blue, resistance red, đúng legend. Legacy legend sai giữ riêng. Evidence: [chart_replay.json](../../../outputs/revision/final_cost_integrity_v1/chart_replay.json); [actual_images.csv](../../../outputs/revision/final_cost_integrity_v1/actual_images.csv); [report.json](../../../outputs/revision/final_cost_integrity_v1/report.json)
- **R14.3 — Đánh giá ảnh hưởng của chart tới inference.** (partial_semantic_limit): Dùng T04 corrected Trend và Decision rerun, với Pattern raw replay. Không nói semantic comprehension đã validated; từ xanh trong template Việt vẫn mơ hồ. Evidence: [report.md](../../../outputs/revision/final_cost_integrity_v1/report.md); [report.json](../../../outputs/revision/final_cost_integrity_v1/report.json)

### R15

Maturity chiều T+2 có điều kiện; daily OHLC không chứng nhận fill/limit-order/allocation/corporate actions/volume units. L=3 không được chứng minh optimal.

- **R15.1 — Settlement, maturity và ứng trước tiền.** (evidence_ready_manuscript_pending): Ghi shares sellable chiều T+2 có điều kiện phân bổ/khớp lệnh; phân biệt pending cash, advance fees, liquidated cash và wealth. Evidence: [sources.json](../../../outputs/revision/execution_evidence_v1/sources.json); [report.md](../../../outputs/revision/execution_final_v1/report.md)
- **R15.2 — Price limits, fill, liquidity và lot.** (evidence_ready_manuscript_pending): Nêu daily OHLC không chứng nhận fill; 12 sensitivities về cost/no-fill/delay/lot-cap là giả định/bounds. Giữ calendar/venue flags HVN, không tự sửa exclusions hoặc xác nhận fill. Evidence: [sample_audit.json](../../../outputs/revision/execution_evidence_v1/sample_audit.json); [report.md](../../../outputs/revision/execution_evidence_v1/report.md); [report.md](../../../outputs/revision/execution_final_v1/report.md)
- **R15.3 — L=3 là lựa chọn protocol.** (evidence_ready_manuscript_pending): Ba observed bars gồm entry, exit sau entry hai phiên; không suy optimal từ settlement hoặc khẳng định thắng các horizons khác. Evidence: [report.md](../../../outputs/revision/execution_final_v1/report.md); [targets.json](../../../outputs/revision/final_contracts_v1/targets.json)

### R16

T21 kiểm danh tính/claim của 41 entries; không invent DOI. Số [14]/[21]/[22]/[23] thuộc bản reviewer đọc, chưa gán tự động vào thứ tự BibTeX hiện tại.

- **R16.1 — Cite 101 Formulaic Alphas.** (evidence_ready_manuscript_pending): Dẫn Kakushadze đúng source/version tại catalogue/adaptations, không chỉ mention không citation. Evidence: [reference_audit.json](../../../outputs/revision/reference_audit_v1/reference_audit.json); [changes.csv](../../../outputs/revision/reference_audit_v1/changes.csv)
- **R16.2 — Dẫn ViSoBERT paper.** (evidence_ready_manuscript_pending): Thêm citation backbone đúng, phân biệt 5CD-AI classifier và giới hạn domain validation. Evidence: [reference_audit.json](../../../outputs/revision/reference_audit_v1/reference_audit.json); [scorer_tokenizer.json](../../../outputs/revision/sentiment_contract_v1/scorer_tokenizer.json)
- **R16.3 — Dẫn White Reality Check đúng vai trò.** (evidence_ready_manuscript_pending): Dẫn White 2000 khi nói data-snooping; không hàm ý đã thực hiện Reality Check nếu chỉ chạy Holm/numeric controls. Evidence: [reference_audit.json](../../../outputs/revision/reference_audit_v1/reference_audit.json); [changes.csv](../../../outputs/revision/reference_audit_v1/changes.csv)
- **R16.4 — Tác giả TradingAgents.** (evidence_ready_manuscript_pending): Sửa bốn tác giả Xiao/Sun/Luo/Wang cùng year/version; không coi tổ chức là tác giả cá nhân. Evidence: [reference_audit.json](../../../outputs/revision/reference_audit_v1/reference_audit.json); [changes.csv](../../../outputs/revision/reference_audit_v1/changes.csv)
- **R16.5 — LOB forecasting khác candlestick recognition.** (evidence_ready_manuscript_pending): Sửa phạm vi/key/câu dẫn Tsantekidis; không dùng LOB paper làm benchmark nhận diện candlestick images. Evidence: [reference_audit.json](../../../outputs/revision/reference_audit_v1/reference_audit.json); [changes.csv](../../../outputs/revision/reference_audit_v1/changes.csv)
- **R16.6 — Năm issue publication khác online first.** (evidence_ready_manuscript_pending): Sửa Deng issue 2017, tách mốc online 2016 và đồng bộ key/metadata. Evidence: [reference_audit.json](../../../outputs/revision/reference_audit_v1/reference_audit.json); [changes.csv](../../../outputs/revision/reference_audit_v1/changes.csv)
- **R16.7 — Xác minh reference [14] reviewer không tìm được.** (partial_historical_reference_number_mapping): T21 kiểm cả 41 entries: ba DOI sai danh tính phải bỏ, một herding entry chưa xác minh thay bằng nguồn riêng. Khi sửa/build phải map [14] theo bản reviewer đọc/câu dẫn, không suy từ thứ tự BibTeX hiện tại. DOI chưa xác minh giữ unknown. Evidence: [reference_audit.json](../../../outputs/revision/reference_audit_v1/reference_audit.json); [changes.csv](../../../outputs/revision/reference_audit_v1/changes.csv); [inventory.json](../../../outputs/revision/reference_audit_v1/inventory.json)
- **R16.8 — Xác minh reference [21] reviewer không tìm được.** (partial_historical_reference_number_mapping): T21 kiểm cả 41 entries: ba DOI sai danh tính phải bỏ, một herding entry chưa xác minh thay bằng nguồn riêng. Khi sửa/build phải map [21] theo bản reviewer đọc/câu dẫn, không suy từ thứ tự BibTeX hiện tại. DOI chưa xác minh giữ unknown. Evidence: [reference_audit.json](../../../outputs/revision/reference_audit_v1/reference_audit.json); [changes.csv](../../../outputs/revision/reference_audit_v1/changes.csv); [inventory.json](../../../outputs/revision/reference_audit_v1/inventory.json)
- **R16.9 — Xác minh reference [22] reviewer không tìm được.** (partial_historical_reference_number_mapping): T21 kiểm cả 41 entries: ba DOI sai danh tính phải bỏ, một herding entry chưa xác minh thay bằng nguồn riêng. Khi sửa/build phải map [22] theo bản reviewer đọc/câu dẫn, không suy từ thứ tự BibTeX hiện tại. DOI chưa xác minh giữ unknown. Evidence: [reference_audit.json](../../../outputs/revision/reference_audit_v1/reference_audit.json); [changes.csv](../../../outputs/revision/reference_audit_v1/changes.csv); [inventory.json](../../../outputs/revision/reference_audit_v1/inventory.json)
- **R16.10 — Xác minh reference [23] reviewer không tìm được.** (partial_historical_reference_number_mapping): T21 kiểm cả 41 entries: ba DOI sai danh tính phải bỏ, một herding entry chưa xác minh thay bằng nguồn riêng. Khi sửa/build phải map [23] theo bản reviewer đọc/câu dẫn, không suy từ thứ tự BibTeX hiện tại. DOI chưa xác minh giữ unknown. Evidence: [reference_audit.json](../../../outputs/revision/reference_audit_v1/reference_audit.json); [changes.csv](../../../outputs/revision/reference_audit_v1/changes.csv); [inventory.json](../../../outputs/revision/reference_audit_v1/inventory.json)

### R17

Chưa sửa nguồn hoặc build PDF trước T30; trang/figure/table numbering lịch sử không là locator hiện hành. Title không được hứa profitability/causal novelty.

- **R17.1 — Di chuyển chi tiết implementation khỏi bài.** (evidence_ready_manuscript_pending): T31/T32 đưa Flask, tokenizer, HF endpoint, API, logs và full prompts về repo/supplement phù hợp; main/appendix chỉ giữ phương pháp khoa học thiết yếu. Evidence: [manifest.json](../../../outputs/revision/reproducibility_v1/manifest.json); [report.json](../../../outputs/revision/final_regression_v1/report.json)
- **R17.2 — Gộp caveats và giảm appendix.** (evidence_ready_manuscript_pending): Chọn một mục limitations đủ ý, giữ qualification tại claims cần thiết; không chép toàn registry/audit vào appendix hoặc lặp cùng caveat mỗi section. Evidence: [response_to_reviewers.md](../../../revision/response_to_reviewers.md); [report.md](../../../outputs/revision/final_baselines_v1/report.md)
- **R17.3 — Dấu chấm đôi ở paragraph headings.** (evidence_ready_manuscript_pending): T32 kiểm dấu câu trong TeX paragraph headings, T35 kiểm render; không sửa source trước T30. Evidence: [inventory.json](../../../outputs/revision/reference_audit_v1/inventory.json)
- **R17.4 — Dùng dash thay hyphen tại câu liệt kê.** (historical_example_not_found_in_current_source): Chuỗi ví dụ sub-tasks-market không còn trong current paper sources; không ghi là T29 đã sửa. T32 kiểm dấu dash ở câu liệt kê tương ứng và T35 xác nhận trên bản render cuối. Evidence: [inventory.json](../../../outputs/revision/reference_audit_v1/inventory.json)
- **R17.5 — Dấu ngoặc kép Section 4.3.** (historical_example_requires_final_render_check): Section 4.3 hiện là Pattern Agent; cần đối chiếu văn bản đã viết lại với câu reviewer đọc và kiểm cặp dấu ngoặc kép trên cả hai PDF T35. Chưa build nên chưa xác nhận lỗi đã hết. Evidence: [inventory.json](../../../outputs/revision/reference_audit_v1/inventory.json)
- **R17.6 — Title khớp phạm vi decision support.** (evidence_ready_manuscript_pending): T31 chốt title trung tính về empirical decision support/historical evaluation, không hứa profitable trading hoặc novel causal fusion; đồng bộ entrypoints, highlights và conclusion. Evidence: [report.md](../../../outputs/revision/final_baselines_v1/report.md); [financial.csv](../../../outputs/revision/final_baselines_v1/financial.csv); [audit.json](../../../outputs/revision/fusion_prompt_audit_v1/audit.json)

### R18

Không đoán tên chuẩn/thứ tự/ORCID/affiliation/CRediT/route nộp lại. Chỉ ghi observed values; chủ thể tác giả phải xác nhận tại T33.

- **R18.1 — Các biến thể tên Thanh-Tam.** (missing_author_confirmation): T33 tác giả xác nhận tên chuẩn; giữ observed variants, không tự chọn dạng tên Việt/Anh. Evidence: [reviewer_matrix.csv](../../../revision/reviewer_matrix.csv)
- **R18.2 — Tên Van-Tang/Tang-Van.** (missing_author_confirmation): T33 tác giả xác nhận spelling/order; đồng bộ title page, manuscript, metadata và CRediT tại giai đoạn sửa bài. Evidence: [reviewer_matrix.csv](../../../revision/reviewer_matrix.csv)
- **R18.3 — Đồng bộ metadata giữa các versions.** (missing_author_confirmation): Ghi ORCID mismatch quan sát được trong author_pending; cần master record và route blind/nonblind do tác giả xác nhận, không tự gán ORCID ownership. Evidence: [response_to_reviewers.md](../../../revision/response_to_reviewers.md)

## QA và giới hạn kiểm tra

QA đối chiếu đủ 18 source spans và anchors nguyên văn; IDs, evidence paths, line locators, CSV/JSON và hashes được kiểm. Source/paper/DOCX trước-sau giữ nguyên. 5.019 hashes T28 khớp; 48 tests chỉ viện dẫn, không chạy lại. Không compile/unit/E2E/leakage/LaTeX/BibTeX/PDF vì task chỉ phân tích tài liệu, không đổi code/runtime/schema/inputs; không network/API.

Manifest khóa các nguồn/evidence trực tiếp và output mới; DOCX riêng có hash nhưng giữ file của tác giả untracked. Audit này chưa là archive public hoặc metadata đã xác nhận. Tiến độ chỉ cập nhật plan.md.
