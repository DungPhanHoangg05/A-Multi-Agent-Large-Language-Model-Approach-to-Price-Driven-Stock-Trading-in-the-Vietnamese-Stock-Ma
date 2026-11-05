# Đặc tả bố cục bản thảo và bảng hình

> **Chỉ dẫn hiện hành về bản thảo (05/11/2026):** giữ nguyên tên tác giả đặt: **Enhancing Multi-Agent Large Language Models for Stock Trading through Quantitative Alpha Integration**. Giữ ký hiệu, bố cục equation/align, phân rã agent, thuật toán và toàn bộ cấu trúc khoa học của bài gốc; chỉ sửa thành phần toán học khi hợp đồng triển khai hoặc comment reviewer bắt buộc. Bản thảo phải tự chứa đầy đủ từ abstract/highlights/introduction đến phương pháp/results/discussion/conclusion/appendix/references; các câu trả lời và lịch sử sửa dành cho response/repository. Highlights nêu đóng góp tích hợp, phương pháp và phát hiện thực nghiệm có bằng chứng, không thay bằng checklist audit. Các lựa chọn tên/rút gọn trước đó ở dưới chỉ là lịch sử, đã được chỉ dẫn này thay thế. Tiến độ nằm tại `plan.md`.

> **Chỉ dẫn biên tập hiện hành (05/11/2026):** theo phản hồi trực tiếp của tác giả, giữ khung bài gốc và sửa tại chỗ để đáp ứng reviewer. Quyết định cũ về bỏ tiểu mục/ba sơ đồ chi tiết, rút còn ba figures và appendix hai phần không còn là đặc tả cho bản hiện hành. Giữ tám sections gốc, các tiểu mục khoa học và vai trò từng agent; khôi phục sơ đồ Alpha/Decision/walk-forward bằng phiên bản đúng hợp đồng đã audit. Các số liệu/claims sai phải được sửa, không khôi phục theo bản cũ. Phần dưới là căn cứ của T31 lịch sử, không phải lý do tiếp tục cắt khung bài. Tiến độ và nghiệm thu bản phục hồi nằm trong `plan.md`.

Đặc tả này chốt nội dung cho lần sửa nguồn T32 theo gate T30 `PASS_FOR_BOUNDED_MANUSCRIPT_WORK`. Phạm vi là **historical exploratory evaluation**, có audit lỗi và giới hạn; native causal gate vẫn **FAIL**. Đây là hướng dẫn biên tập, không phải bản thảo đã sửa, response đã gửi hoặc xác nhận đủ điều kiện nộp bài. Tiến độ nằm tại [plan.md](../plan.md).

Title được chọn cho cả hai entrypoints:

**Multi-Agent LLM Decision Support for Vietnamese Equities: A Historical Evaluation**

Không giữ “Enhancing”, “Stock Trading” hoặc “knowledge fusion” như một tuyên bố superiority, profitability hay novelty. Phần khoa học giữa main/submission phải giống nhau; names, ORCID, affiliations, CRediT và blind/nonblind route chờ xác nhận T33, không tự sửa theo phỏng đoán.

## Phạm vi kết luận và front matter

Abstract nhắm khoảng 180–220 từ: câu hỏi đánh giá; implementation cụ thể và reconstructed historical inputs; main 102 units/12 dates/sáu blocks; class imbalance và baseline comparison; contrasts/repeats có giới hạn; kết quả kinh tế âm và vấn đề chưa giải quyết. Số 65,0%/51,1% của study cũ không là headline cuối. BA là primary metric; Full−Base là bundle contrast. Không dùng một câu caveat cuối abstract để giữ causal/superiority claims ở đầu.

Bốn highlights định hướng nội dung, viết lại thành câu ngắn ở T32:

- Frozen calls support an auditable historical LLM evaluation.
- Class-aware baselines contextualize results on 102 market units.
- Repeated executions expose variability and ordering limitations.
- Negative account returns limit economic and deployment claims.

Keywords: multi-agent LLM; Vietnamese equities; historical evaluation; class imbalance; reproducibility. Đây là lựa chọn biên tập nội bộ, không tuyên bố đã đáp ứng yêu cầu journal chưa được tác giả xác nhận.

Không tạo graphical abstract riêng ở bước mặc định. Nếu route T33 bắt buộc có, tái dùng Figure 1 đúng scope; không vẽ thêm một architecture khác hoặc lặp nội dung trong bài chính.

## Outline và ngân sách nội dung

Giữ tám source sections đang được cả hai entrypoints gọi để giảm thay đổi không cần thiết. Được đổi headings và cấu trúc bên trong, không giữ các phương trình/đoạn cũ chỉ để giữ số thứ tự. Khoảng **5.750 từ prose gồm abstract** là mục tiêu biên tập, không tính bibliography, tables, captions và equations; số trang thực phải kiểm ở T35, không ép bằng font nhỏ.

| Section mới | Source hiện tại | Từ mục tiêu | Nội dung phải giữ |
|---|---|---:|---|
| 1. Introduction | `01_introduction.tex` | 450 | Câu hỏi và đóng góp ở mức implementation/protocol/evaluation; kết quả không chứng minh alpha/profitability hoặc learned fusion |
| 2. Related work | `02_related_work.tex` | 350 | Ba nhóm ngắn: LLM/chart-agent attribution; factor selection/data-snooping; Vietnamese sentiment và evaluation. Áp citation/claim actions T21, bỏ references sai danh tính |
| 3. Forecasting task and signal construction | `03_problem_formulation.tex` | 900 | Decision/entry/exit/net target; native selector thực dùng và causal defect; sentiment recipe/availability. Chỉ giữ equations cần tái hiểu phương pháp |
| 4. Implemented multi-agent system | `04_system_architecture.tex` | 650 | Năm vai trò thực chạy, Indicator deterministic, actual reports/prompt aggregation, Base bundle removal, compact/five-row families và reused components; Figure 1/3 |
| 5. Historical evaluation protocol | `05_experimental_setup.tex` | 900 | Scope/amendment, quality exclusions, chronological train/validation/purge, baseline definitions, repeats/factorial/donor, metrics/dependence, conditional execution; Table 1/Figure 2 |
| 6. Results | `06_backtest_results.tex` | 1.500 | Theo thứ tự main classification → economics → repeats/factorial → temporal/dependence → auxiliary numeric controls. Tables 2–6; không chọn panel/seed có lợi |
| 7. Discussion and limitations | `07_limitations.tex` | 650 | Gộp causal/PIT/domain, sampling/dependence/order/epochs, representation/exposure/semantic, execution và reproducibility limits thành các nhóm; future work cụ thể, không hứa kết quả |
| 8. Conclusion | `08_conclusion.tex` | 150 | Trả lời câu hỏi theo kết quả quan sát, giới hạn và việc chưa đáp ứng; không phục hồi claims đã bỏ |

Section 3 nêu causal FAIL và thiếu validation ngay khi mô tả phương pháp. Section 7 giải thích hệ quả một lần; captions chỉ nhắc qualification cần để đọc đúng bảng, không lặp cả danh sách caveats. L=3 là ba observed bars gồm entry, không optimal horizon. Daily risk conventions được mô tả ngắn; bỏ annualised cycle Sharpe/Sortino khỏi main tables vì schedule gapped và ít trades, không thay chúng bằng cách annualise khác.

## Sáu bảng chính

Các captions dưới đây là nội dung đã chọn để triển khai ở T32. IDs T1–T6 là design IDs; số Table cuối do LaTeX sinh sau khi bố trí. Dữ liệu, masks và expected row counts nằm trong [layout.json](../outputs/revision/manuscript_blueprint_v1/layout.json).

**T1 — Evaluation scope and prompt variants.** Section 5; hai panels. Panel A có ba rows main/upstream/factorial với units, symbols, dates, blocks, classes và executions. Main: 102 units, 204 Decisions; upstream: 9 units ×2 variants ×3 realizations =54 Decisions, trong đó 18 r0 đã thuộc main, chỉ 36 bổ sung; factorial: 9 units ×5 variants ×3 repeats =135 Decisions. Union là **375**, không cộng 204+54+135. Panel B có B/A/S/AS/P, sections present và prompt family; Base không alpha lẫn sentiment. Ghi main compact khác factorial explicit five-row, placebo giữ schema/current sentiment và dùng một past train-only rank vector. Caption: *Evaluation scopes and prompt variants in the frozen historical study. Shared main/upstream executions are counted once.*

**T2 — Main class-aware comparison.** Section 6.1; Panel A đủ **chín classifiers**, cùng N=102 và support 25 UP/77 DOWN: Full, Base, CASH, train-majority, always-LONG cycles, momentum-20, logistic-price, logistic-matched-market-inputs, fixed factor vote. Columns: accuracy, BA, MCC, UP precision/recall, DOWN precision/recall, LONG rate. Panel B đủ chín rows macro-by-symbol BA và MCC, mỗi metric có n_defined/9. BA primary, proportions đổi % nhất quán; MCC giữ scale; undefined NA, không zero. Appendix A3 cho Full/Base theo mã; scientific supplement S1 cho **mọi baseline theo từng mã và từng lớp**. Caption: *Class-aware performance on the same 102 historical market units. Macro summaries weight symbols equally and retain undefined denominators.*

**T3 — Account outcomes and exposure.** Section 6.2; **mười strategies**, gồm chín classifiers và continuous hold. Columns: mean account net return%, mean daily-close drawdown%, mean calendar held-session fraction%, mean order count; mỗi row có 51 symbol–block accounts. Không gọi là portfolio. Held-session fraction gồm CASH gaps, khác LONG rate/target-session exposure. Hold có một purchase/sale qua gaps, không là always-LONG cycles, classification NA; total-return/corporate actions chưa xác minh. Caption: *Account outcomes under the fractional reference ledger. Means summarize 51 separate symbol–block accounts per strategy and do not establish executable portfolio returns.*

**T4 — Repeats, factorial and placebo.** Section 6.3; Panel A có **bảy rows**: hai upstream variants và năm factorial variants, mỗi row là ba executions. Columns: accuracy mean(SD), BA mean(SD), BA min–max, mean pairwise disagreement%, mean account return mean(SD). Panel B có **tám contrast rows**: upstream AS−B riêng, cùng bảy factorial contrasts B/A/S/AS/P và interaction. Báo BA mean/SD/range, conditional percentile interval và descriptive family envelope nếu có; giữ finite/undefined counts. Không thêm best-single gap thành contrast thứ tám của factorial; nếu nhắc thì giải thích bằng một câu. Order deviations 40/cross-epoch 9 và panels khác support phải hiện rõ. Caption: *Execution variability and paired contrasts on two distinct nine-unit panels. Repeated executions do not add independent market dates.*

**T5 — Temporal scope and dependence.** Section 6.4; Panel A đủ **ba overlapping cohorts** all_102/common-eight_96/recent-nine_54, n_dates/blocks, Full/Base BA, ΔBA và primary whole-block interval từ T25. Panel B đủ **ba observed trend strata**, kèm UP/DOWN support, Full/Base BA và LONG rates; train-only threshold recipe cho vol/turnover nêu ở Section 5, các strata đầy đủ trong S4. Không sinh interval mới cho từng regime hoặc chọn cohort/stratum đẹp. HAC là **accuracy contrast**, khác BA; nêu trong một đoạn ngắn, đủ lags0/1/2 cho cả hai fixed-universe panels, effect/SE/p ở S4. Caption: *Overlapping temporal cohorts and observed trend strata. Small-block intervals and calendar-aligned HAC diagnostics are descriptive rather than calibrated significance tests.*

**T6 — Auxiliary numeric selector controls.** Section 6.5; tách khỏi LLM results. Panel A có **bốn rows**: `fixed_custom5`, `dynamic_train_top5`, `dynamic_train_top5_no_flip` và toàn bộ random20 family summary; BA/accuracy/MCC cùng n_trials, SD/range cho random family, không lấy một seed. Panel B đủ **ba primary contrasts** trong design T12/T13: dynamic−fixed, dynamic−random-family, dynamic−no-flip; ΔBA, descriptive interval, exact p và Holm p trên **toàn family 23**, không sửa family thành ba tests. Native selection frequency/IC-sign diagnostics nêu ngắn với mẫu số 102 cutoffs/510 slots; đầy đủ 85 factors và 21 exclusions ở repository. Caption: *Train-fit numeric selector controls using separate causal adapters. These auxiliary results neither repeat the native LLM selector experiment nor repair its row-wise causal defect.*

## Ba hình chính

**F1 — Implemented data and decision flow.** Một vector schematic ở Section 4. Thể hiện frozen OHLCV/news, deterministic Indicator, numerical alpha/sentiment path, Pattern/Trend vision, shared reports và Decision. Ghi Base bỏ bundle, actual prompt-level heuristic aggregation; không vẽ learned-fusion/causal/guaranteed-conflict-resolution module. Phân biệt graph roles với số API calls; Alpha/Indicator backtest không có LLM reasoning calls. Thay ba pipeline images cũ bằng một sơ đồ đúng implementation; full retry/checkpoint/API routing để repository. Caption: *Implemented information flow and shared-report comparison. Aggregation uses prompt instructions rather than a learned fusion module.*

**F2 — Evaluation calendar and eligibility.** Một grid đủ 12 dates ×9 tickers =108 cells, phân sáu blocks; 102 eligible và sáu BHN exclusions. Đánh UP/DOWN/NA bằng ký hiệu đọc được khi in, không mã hoá kết quả Full để chọn hình thuận lợi. Calendar gaps theo selected dates, không làm như daily continuous backtest. Ghi hai panels repeats chỉ là subsets, không tăng market-date count. Caption: *Selected historical decision dates and eligibility across nine equities. Missing BHN cells remain excluded rather than being filled with CASH predictions.*

**F3 — Actual chart inputs.** Hai panels Pattern/Trend của **CMG_b2023_h2_872**, ngày 03/07/2023: chọn bằng **earliest main decision date, rồi symbol/unit ID theo thứ tự chữ cái**, không theo accuracy/outcomes. Trích nguyên PNG bytes từ chart cache/request đã audit T27, không vẽ lại rồi gọi là actual input. Bố trí bằng LaTeX, giữ nguyên file ảnh; caption giải thích Close>Open green, Close<Open red, doji red, support blue/resistance red. Không dùng chart fixture tổng hợp như ví dụ thị trường hoặc tuyên bố VLM hiểu màu đúng. Caption: *Actual Pattern and corrected Trend inputs at the first chronologically eligible main unit. Candle bodies compare Close with Open; the trend legend maps blue to support and red to resistance.*

Không dùng chín stock backtest PNG legacy hoặc graphs có số liệu trước sửa chart trong main/appendix. Giữ byte files lịch sử; bỏ includes không có nghĩa xoá bằng chứng. Không tạo forest plot hoặc return chart chỉ để lặp tables đã đủ đọc.

## Appendix ngắn và scientific supplements

Appendix nhắm khoảng 4–6 trang ở layout đọc được; đây là mục tiêu nội bộ, không phải page limit journal. Nếu tràn, rút prose trùng và trỏ tới supplement, không giảm font để nhét full registry/logs.

- **Appendix A — Signal definitions and implementation distinctions.** Table A1 có năm indicator rules đúng priority/boundaries/rounding/missing denominator. Table A2 có năm custom factor definitions, phân biệt native registry handler với prototype/fallback khi khác; nêu signed-volume Alpha_4, selected rank slot khác factor identity và metadata mismatches. Giữ phần algebra cần hiểu, chuyển full Python listings/state-schema/operator catalogue ra repository.
- **Appendix B — Additional account and symbol results.** Table A3 có 18 Full/Base rows theo chín mã, class support/accuracy/BA/MCC/UP–DOWN recall. Table A4 có đủ 12 execution scenarios, Base/Full mean return, Full Δreference, residual stock/pending cash counts; hỗ trợ 51 accounts, giữ mọi scenario và assumptions. Không chứng nhận fills hay xem all-missed là mathematical worst bound.

Scientific supplements là các bảng có giá trị đọc độc lập, khác gói logs/raw:

| ID | Nội dung | Nguồn đã có |
|---|---|---|
| S1 | Đủ81 symbol×classifier rows, class support và precision/recall/F1 cả hai lớp; pooled/macro với n_defined | T24 classification/per_class/macro; hold là account strategy riêng, không classifier thứ mười |
| S2 | Đủ21 variant–execution rows, disagreements, toàn bộ 48 contrast×metric rows và conditional denominators | T26, không chọn best run hoặc bỏ undefined draws |
| S3 | Đủ23 numeric strategies, 20 random trials/dispersion,23-hypothesis family và retained/excluded factor pointers | T12/T13; numeric evidence riêng với native in-sample diagnostics T11 |
| S4 | Full calendar/cohort/regime tables, đủ sáu HAC rows, tất cả block-length sensitivities/leave-one-block-out | T25; không đưa144/189-row audits vào appendix |

T32 phải cung cấp tên file/link companion tables rõ ràng để yêu cầu per-symbol của R1 không biến mất khi rút bài. Public availability/PID còn chờ quyền và publication T34; không viết “publicly archived” hoặc DOI giả trước khi có. Không tạo thêm scientific outcomes, fit, bootstrap hoặc LLM calls để điền các bảng này.

## Nội dung chỉ để repository hoặc private reproducibility package

Giữ ngoài article appendix: 80 retained/21 excluded expression registry đầy đủ, all85 handlers/operator contracts, per-cutoff selection/IC metadata, raw prompts/images/messages/responses/errors/retry/cost logs, full state schema, tokenizer/model files, Flask JSON serialization, Hugging Face endpoint routing, quotas/locks/checkpoints, requirements/wheel/runtime details và exhaustive integrity receipts. Việc trỏ tới package không biến nội dung private thành public; raw reviewer DOCX/text không tự đưa vào public companion.

Trong main chỉ giữ model aliases đúng raw, configured/observed temperature, lack of hosted seed/immutable revision, recipe/provenance và availability statement ngắn. Chi phí quan sát 615 successes/34 errors và Pattern replay 120 có thể tóm tắt bằng một đoạn; full accounting nằm T27, unknown billing/usage lỗi giữ unknown. Không thêm một bảng implementation runtime dài thay bảng khoa học.

## Quy tắc triển khai và kiểm chứng

1. T32 sửa cả hai entrypoints/shared sections/bibliography/figures theo cùng content contract. T21 quản lý reference identity và câu dẫn; số citations reviewer đọc phải đối chiếu, không map theo thứ tự BibTeX hiện tại.
2. T29 crosswalk 87 yêu cầu vẫn là nguồn hành động; [coverage.json](../outputs/revision/manuscript_blueprint_v1/coverage.json) ánh xạ từng ID sang section/table/supplement hoặc dependency T33/T34/T35. Ánh xạ không đóng reviewer hoặc xác nhận metadata/PID/domain validation.
3. Chỉ chuyển/reshape/format dữ liệu đã khóa, dùng full source precision rồi làm tròn để trình bày; percentage points khác percentages. Không thay predictions, labels, source snapshots hoặc manifests; all undefined giữ null/NA.
4. Native causal FAIL phải hiện ở phương pháp, hệ quả ở discussion; không giấu ở một footnote supplement. Bỏ claims causal/unbiased/superiority/profitability/financially validated/novel learned fusion trong abstract/highlights/title/conclusion và câu dẫn.
5. T32 kiểm nguồn/citation/numeric contracts; T35 build/render cả hai PDFs, kiểm readability, citations, table/figure numbering, appendix length và current locators. Không coi outline hoặc source anchors ở đây là PDF QA đã đạt.
6. Trước khi sửa ở T32, lưu source ZIP của 30 `paper/` files trong release bản thảo mới và kiểm từng member/hash với snapshot T29/T31. Sau khi sửa, đối soát nguồn lịch sử bằng đúng ZIP/member/hash; không sửa manifest cũ hoặc báo source cũ vẫn bằng current source. Không áp ngoại lệ này cho raw/model/prediction inputs bị thay đổi.

Phân tích T31 chỉ tạo đặc tả, lựa chọn và QA nguồn. Không sửa `paper/`, không build PDF, gọi API, chạy lại tests, statistics, model hoặc scorer. Các receipt và bytes lịch sử được giữ nguyên.
