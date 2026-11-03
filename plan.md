# Kế hoạch hoàn thiện hệ thống theo 18 nhận xét reviewer

**Thứ tự: hoàn thiện hệ thống → đủ kết quả thật → kiểm chứng → sửa bài một lần → phản hồi reviewer.** Đây là danh sách việc còn lại, đối soát ngày 03/11/2026 theo `Reviewer Comments for author.docx`.

## 1. Quy tắc thực hiện

- Codex làm code, kiểm thử offline và phân tích dữ liệu đã có. **Mọi bước gọi API, kể cả Free, smoke, kiểm tra model và retry, chỉ do tác giả tự chạy.** Codex đưa lệnh cụ thể, đầu ra dự kiến và cách resume; không tự khởi động worker.
- Tiến độ chỉ cập nhật tại `plan.md`. Task có trạng thái, dependency và điều kiện xong; thêm link bằng chứng khi hoàn thành. Không thêm nhật ký hoặc lịch sử sửa kế hoạch.
- **Chưa sửa `paper/`, xuất bảng vào `paper/generated/` hoặc build PDF trước T30.** Phân tích hệ thống xuất vào `outputs/revision/<release>/`; kiểm tra tác dụng phụ của script trước khi chạy.
- Nguồn LaTeX đã khôi phục theo [bản lưu trước sửa](revision/manuscript_original.zip). Đây là điểm xuất phát để sửa sau cùng, không phải bài đã đáp ứng reviewer. PDF/response/locators cũ chỉ là tham khảo, không xác nhận đóng comment cho nguồn hiện tại.
- Giữ nguyên code đã sửa đúng, raw calls, predictions, caches và releases đã khóa. Không làm lại task đã có evidence; không ghép run trước/sau sửa chart thành một study.
- Verifier bản thảo cũ có thể không khớp `paper/` sau khôi phục; kiểm phiên bản đó bằng source ZIP đã lưu. Không sửa manifest lịch sử hoặc chạy lại finalizer để chèn các bảng vừa gỡ. Kiểm thử hệ thống không phụ thuộc bản thảo cần được giữ tách biệt.
- Làm trên task branch từ `fix`, kiểm tra đúng phạm vi rồi commit/merge/xóa nhánh local. Không tự push/publish/submit.
- Không thêm Bayesian/KLTN, model mới, sweep hoặc chọn seed/kết quả đẹp. Kết luận theo bằng chứng, kể cả khi Full không hơn CASH/baseline; không cam kết accept.

## 2. Phần đã có để tái sử dụng

| Phần đã có | Bằng chứng và giới hạn |
|---|---|
| Bank 102 điểm, sáu block, 12 ngày; baseline số; runner năm org, archive/checkpoint | [Bank](outputs/revision/r1_72h_bank_v2/manifest.json), [protocol](revision/r1_72h_protocol.json). Không dựng lại grid 540/8.100 hoặc tính calibration cũ vào evaluation. |
| 474 research Decisions +10 smoke; 102 cặp B/AS; repeats 18 điểm, upstream 9 điểm | [Analysis](outputs/revision/r1_72h_run_v2/analysis/manifest.json). R1–R3 đã có bằng chứng; kết luận cuối cần cập nhật theo chart rerun. |
| R4 đủ 270 Decisions mới với đủ giá trị factor, factorial/placebo | [Bank R4](outputs/revision/r4_value_bank_v1/manifest.json), `outputs/revision/r4_value_run_v1/`. Giữ riêng prompt rút gọn R1 và prompt đủ giá trị R4. |
| Audit branch trùng, thống kê phụ thuộc, annualisation và execution sensitivities | [Lineage](outputs/revision/legacy_lineage_v1/manifest.json), [statistics](outputs/revision/dependent_statistics_v1/manifest.json), [risk](outputs/revision/account_annualisation_v1/manifest.json), [execution](outputs/revision/execution_sensitivity_v1/manifest.json). Tái dùng và áp dụng đúng release cuối. |
| Target/schema, indicator và Alpha_4 đã audit/test | [Target](outputs/revision/target_contract_v1/manifest.json), [indicator/alpha](outputs/revision/indicator_alpha_rules_v1/manifest.json). R11–R13 còn cần đồng bộ vào bài sau cùng. |
| Article audit và local rescore | [Article audit](outputs/revision/r1_72h_bank_v2/article_audit.json), [scores](outputs/revision/r1_72h_bank_v2/local_scores.json): 180 records, 177 identities, 154 excerpts rescore; chưa xác thực nội dung PIT và chất lượng tài chính bằng người. |
| Sửa legend Trend; rerun đang dở | [Chart audit](outputs/revision/chart_convention_v1/manifest.json). Đủ 10 smoke, 120 research Trend groups; **138/474** research Decisions và R4 **6/270**. Còn **336+264=600** Decision successes, chưa tính retries. Không tạo lại Pattern/smoke đã thành công. |

Năm biến `GROQ_ORG_1_API_KEY`…`GROQ_ORG_5_API_KEY` đã được tác giả cấu hình. [Policy hiện hành](revision/r1_provider_policy.json): provider-only, một request/key tại một thời điểm, checkpoint khi hết provider khả dụng. Không khôi phục cap/deadline nội bộ cũ; không hứa hoàn tất 600 quyết định trong thời gian cố định chỉ từ số key.

## 3. Task còn lại theo thứ tự

Làm từ trên xuống. Khi chờ tác giả/API, có thể làm task offline độc lập phía sau. **Không thay nguồn/runtime đã freeze của run đang dở.** Nếu sửa input inference: tách phiên bản, xác định jobs chịu ảnh hưởng và đưa lệnh mới cho tác giả; không bỏ hash guard để resume.

### A. Hoàn tất lượt chạy đã sửa chart

| ID | Việc cần làm | Điều kiện hoàn thành | Trạng thái / dependency |
|---|---|---|---|
| T01 | Kiểm tra source/runtime hashes, checkpoints, raw lineage hai run chart và worker trùng. | Đúng run/bank, số jobs thiếu rõ; không API, không sửa manifest cũ. | **Hoàn tất — PASS**; [audit](outputs/revision/chart_resume_audit_v1/report.json), [hash nguồn/đầu ra](outputs/revision/chart_resume_audit_v1/manifest.json), [jobs thiếu](outputs/revision/chart_resume_audit_v1/missing_jobs.json) |
| T02 | **Tác giả** chạy tiếp 336 Decisions tập chính, dùng lệnh mục 4. | `chart_r1_run_v1` đủ 474 research +10 smoke; đủ 102 cặp và repeats. Không lấy run cũ lấp thiếu. | Chờ tác giả; T01 đã PASS |
| T03 | **Tác giả** chạy tiếp 264 Decisions R4, dùng lệnh mục 4. | `chart_r4_run_v1` đủ 270/270; đúng Trend mới, donor/variants/repeats đã khóa. | Chờ tác giả; sau T02 |
| T04 | Verify, khóa kết quả mới và phân tích offline. | Raw/parent/input hashes, completion và failures nhất quán; xuất release riêng, không ghi vào `paper/` hoặc đè release cũ. | Chưa làm; sau T03 |

**Đối soát T01 lúc 21:05 ngày 03/11/2026 (Asia/Saigon):** Python 3.13.5 và dependency pins khớp; 54 source/input records của tập chính, 209 của R4 và 110 file trong source ZIP khớp SHA-256. [Mã audit offline](outputs/revision/chart_resume_audit_v1/audit.py) kiểm tra 1.948 file trước/sau, giữ nguyên byte artifacts; 10 lock files cũng giữ nguyên. Không sửa nguồn inference, inputs, manifest cũ hoặc `paper/`; không gọi API/đọc credentials. Không chạy lại unit/E2E/leakage suite vì chỉ phân tích bằng chứng hiện có và thêm công cụ audit độc lập; chạy trực tiếp audit để kiểm hash/runtime/lineage, dựng lại prompt và đối chiếu ledger, cùng hai lệnh status offline ở mục 4. Biên dịch riêng `audit.py` bằng `py_compile` và kiểm diff/liên kết/hash đầu ra đều PASS.

| Shard lưu trữ | Tập chính đã có / còn thiếu | R4 đã có / còn thiếu |
|---|---|---|
| org1 | 31 / 64 | 1 / 59 |
| org2 | 24 / 72 | 1 / 59 |
| org3 | 27 / 67 | 1 / 59 |
| org4 | 25 / 69 | 1 / 44 |
| org5 | 31 / 64 | 2 / 43 |
| **Tổng research Decisions** | **138 / 336** (mục tiêu 474) | **6 / 264** (mục tiêu 270) |

- Tập chính có thêm **10/10 smoke**, hash năm smoke receipts và artifacts đều khớp; **67/102 cặp B/AS chính** đã đủ. Kiểm tra 375 node checkpoints, khôi phục parent/input của 125 upstream groups (120 research +5 smoke), dựng lại 148 prompt Decision và replay prediction từ raw. R4 giữ nguyên panel/donor/order/repeats, dựng lại đủ 90 prompts từ corrected reports và kiểm sáu checkpoint hiện có; không gộp outcome với run cũ.
- Raw tập chính: **140 Pattern attempts tái dùng** (125 responses +15 errors), 405 file copy khớp origin; **284 attempts mới** (273 responses +11 errors). R4: **10 attempts mới** (6 responses +4 errors). Ledger chỉ đọc khớp đúng các attempts mới; không request chưa có response/error, raw orphan, request ID trùng giữa hai run hay checkpoint `.tmp`. Raw Decision prompts lớn nhất lần lượt 3.807 và 4.067 ký tự, đều <6.500.
- Hai ảnh chụp tiến trình không có worker inference; cả **10 khóa OS** lấy được và đã nhả, không live lease. Đây là trạng thái tại thời điểm audit, cần kiểm lại trước resume; không suy từ `status.json` cũ rằng worker còn chạy. **Hai run có ledger/khóa riêng**, không khóa pool key xuyên run: chỉ chạy T02 rồi T03, không chạy song song. Quota hiện tại, provider org và immutable model revision vẫn chưa xác minh qua network. T01 không thay gate nghiệm thu kết quả T04 hoặc đóng R1–R18.

### B. Sentiment — R7 và phần sentiment của R4

| ID | Việc cần làm | Điều kiện hoàn thành | Trạng thái / dependency |
|---|---|---|---|
| T05 | Sửa audit coverage dùng đúng loader/runtime; tái dùng article audit. | Đúng paths; record khác test point; unique theo mã/toàn corpus, duplicates, ngày, URL/content hash và scorer provenance rõ. | Chưa làm |
| T06 | Xuất coverage từ một nguồn, tách legacy và release mới. | V+L+U=total; percentage khớp count; date-only khả dụng ngày kế tiếp, cửa sổ 90 ngày, >=3 bài hợp lệ. Missing khác neutral; coverage từng cutoff/mã và peer availability rõ. | Chưa làm; sau T05 |
| T07 | Kiểm thử coverage/cutoff/scorer và kiểm prompt thật khi thiếu tin. | Mapping/tokenizer/truncation pinned, tests đúng đường dùng PASS; S ở điểm thiếu tin không được coi là sentiment evidence. | Chưa làm; sau T06 |
| T08 | Chốt domain validation và nguồn tin với tác giả. | Nếu giữ claim chất lượng tài chính: cần nhãn độc lập, hai người, agreement/adjudication, macro-F1/per-class và uncertainty. Nếu chưa có: ghi chưa validation, social-media domain/PIT chưa xác thực và bỏ claim phụ thuộc. Rescore không thay validation. | Chờ tác giả; không chặn T09–T29 |

### C. Alpha registry và selector — R10

| ID | Việc cần làm | Điều kiện hoàn thành | Trạng thái / dependency |
|---|---|---|---|
| T09 | Xuất registry từ code thật: 101 WorldQuant IDs và năm custom. | Đối chiếu 80 retained/21 excluded; mỗi mục có lý do, công thức gốc/triển khai và code pointer. Sai lệch phải ghi, không sửa số cho khớp prose. | Chưa làm |
| T10 | Kiểm chứng translations quan trọng bằng fixtures. | Operator/window/warm-up/ties/NaN, rank surrogate/neutralisation, volume thật/proxy và đơn vị có đặc tả; fixtures/leakage tests PASS. Giữ công thức Alpha_4. | Chưa làm; sau T09 |
| T11 | Xuất selection diagnostics trên cutoffs đã khóa. | Eligible denominator, frequency, IC sign stability, overlap/rank stability, turnover và proxy/missingness theo mã/block; không fit test. | Chưa làm; sau T10 |
| T12 | Khóa thiết kế numeric controls trước chạy. | Fixed set, random eligible sets/seeds, no-sign-flip và dynamic top-5 cùng support/target/cost; train/validation đã purge; không chọn theo test outcomes. | Chưa làm; sau T11 |
| T13 | Chạy controls offline và xử lý multiplicity. | Báo mọi seed/trial và dispersion; điều chỉnh đúng họ giả thuyết. Numeric evidence không phải ablation toàn pipeline LLM. | Chưa làm; sau T12 |
| T14 | Chốt kết luận selector. | Có bảng fixed/random/dynamic với numeric scope rõ. Nếu vẫn claim LLM dynamic vượt controls: cần protocol/budget và lệnh API bổ sung cho tác giả. Thiếu evidence thì bỏ claim, yêu cầu chưa đủ vẫn mở. | Chưa làm; sau T13 |

### D. Phương pháp, attribution và khả năng tái lập

| ID | Việc cần làm | Điều kiện hoàn thành | Trạng thái / dependency |
|---|---|---|---|
| T15 | Chốt cách xử lý branch legacy không xác minh được — R6. | Dùng audit 47 artifacts; chỉ rõ chuỗi bị loại khỏi attribution chính. Request/flags/model unknown không bị ghi thành đã xác nhận; evidence mới không xác thực ngược legacy. | Chưa làm |
| T16 | Đối chiếu QuantAgent ở commit nguồn phù hợp — R8. | Component/file/prompt phân loại reused/modified/new; đủ MIT notice/copyright và attribution; chưa rõ ghi unknown. | Chưa làm |
| T17 | Chốt mô tả fusion và nguồn prompt — R8. | Phân biệt nối báo cáo với knowledge representation/conflict resolution thật; bỏ novelty thiếu cơ chế/evidence. Giải thích prompt high-frequency/K-line legacy khác daily bars; không sửa prompt freeze rồi gán kết quả cũ cho prompt mới. | Chưa làm; sau T16 |
| T18 | Hoàn tất căn cứ execution — R15. | Calendar/venue/date, T+2 shares/cash, limit-open/no-fill, lot/volume units, taxes/fees, ứng trước và corporate actions được đối chiếu nguồn chính thức. Daily OHLCV không chứng minh fill/queue; phần thiếu ghi assumptions/bounds. | Chưa làm |
| T19 | Áp dụng execution sensitivities vào predictions chart cuối. | Tái dùng 12 scenarios; reference khớp, settled/pending cash đúng, bar timestamp khác fill time. Giải thích L=3, không claim tối ưu; chỉ thêm horizon study nếu cần giữ claim đó. | Chưa làm; sau T04/T18 |
| T20 | Đối soát target/risk/indicator contracts trên release cuối — R5/R11–R13. | Net Open-to-Close primary, gross riêng; giải thích actual_prev_close legacy, không đoán dữ liệu. Daily/cycle frequency, gaps, null/NA, rules biên đúng bản sửa đã test; chỉ kiểm lại phần bị đổi. | Chưa làm; sau T04/T19 |
| T21 | Audit toàn bộ references — R16. | Kiểm BibTeX keys/câu dẫn với publisher/DOI/arXiv; nguồn 101 Alphas/ViSoBERT/White đầy đủ; sửa TradingAgents/Deng/LOB trong bảng đề xuất; citation không xác minh được phải thay hoặc bỏ. Chưa sửa `.bib`/bài. | Chưa làm |
| T22 | Đóng gói reproducibility — R9. | Snapshot OHLCV/news, model/tokenizer, prompts/charts/raw responses/parse/retries, dependency/runtime pins và checksums đủ; không secrets. Quyền chia sẻ rõ, không gọi dữ liệu tái dựng là snapshot submission. | Chưa làm; sau T04 |
| T23 | Replay ở môi trường sạch, không network. | Tái tạo metrics không ignored cache/đường dẫn máy tác giả/fetch live. Phân biệt offline replay với inference mới và model ID cấu hình/response với immutable revision chưa biết. | Chưa làm; sau T22 |

### E. Chốt bằng chứng toàn hệ thống

| ID | Việc cần làm | Điều kiện hoàn thành | Trạng thái / dependency |
|---|---|---|---|
| T24 | Xuất baseline/metrics cuối — R1. | Full/Base, CASH, train-majority, always-LONG, momentum, hai logistic, factor vote và hold đúng support. Có per-symbol/pooled/macro, class counts, BA primary, MCC/per-class, LONG rate; hold khác always-LONG. | Chưa làm; sau T04/T20 |
| T25 | Cập nhật temporal/regime/dependence — R2/R5. | Tám mã chung/sáu block, chín mã/ba block mới, BHN exclusion; 102 units/12 dates, repeats không là ngày độc lập. Tái dùng bootstrap/HAC/null audit; lag/SE/p, discordance, undefined và giới hạn mẫu nhỏ rõ. | Chưa làm; sau T24 |
| T26 | Xuất repeats và factorial/placebo cuối — R3/R4. | Mean/SD/range/disagreement đúng panel 18/upstream 9; contrasts B/A/S/AS/P và interaction cùng parent/support. Full−Base là bundle effect; placebo giữ schema/missingness, donor train-only. Không gộp trước/sau sửa chart. | Chưa làm; sau T04/T07 |
| T27 | Tổng hợp chi phí/integrity — R9/R14. | Calls/tokens/latency/errors/retries thật, tách Pattern replay/calls mới, execution epochs và thiếu jobs. Chart màu/legend/prompt khớp fixture/raw inputs cuối. | Chưa làm; sau T04 |
| T28 | Kiểm tra hồi quy đúng phạm vi thay đổi. | Pairing/isolation, PIT/purge, prompt <6.500 ký tự, node resume, raw tamper, quota/retry, metrics/ledger có evidence phù hợp. Không dùng mocks thay LLM thật, không tự chạy API/toàn suite. | Chưa làm; sau T05–T27 |
| T29 | Đối soát đủ 18 nhận xét từ DOCX gốc. | Mỗi yêu cầu con có evidence, giới hạn và action viết bài dự kiến; thiếu tác giả/PID/domain validation ghi riêng. R1–R4/R11–R13 cần đồng bộ bài, không đóng bằng PDF cũ. | Chưa làm; sau T28 |
| T30 | **Gate bắt đầu sửa nguồn bài.** | Hoàn tất phần hệ thống/bằng chứng áp dụng của T01–T29; không còn lỗi code/dữ liệu/inference chưa xử lý. Thiếu sót bắt buộc phải giải quyết; giới hạn không thể khắc phục phải công khai và bỏ claim phụ thuộc, không tự ghi thỏa reviewer. | Chưa đạt |

### F. Sửa bản thảo sau cùng, chỉ sau T30

| ID | Việc cần làm | Điều kiện hoàn thành | Trạng thái / dependency |
|---|---|---|---|
| T31 | Chốt outline gọn, chọn bảng/hình — R17. | Bài chính giữ phương pháp/kết quả/giới hạn; appendix chỉ chi tiết phương pháp cần tra cứu. Registry đầy đủ, audit từng mã, raw prompts/logs/tests/Flask/tokenizer/API routing để repository/supplement phù hợp. Không chép mọi audit vào appendix. | Chờ T30 |
| T32 | Sửa đồng bộ LaTeX một lượt — R1–R17. | Target/indicators/custom alpha/chart/baseline/statistics/attribution/references/execution khớp release cuối; abstract/highlights/title/conclusion không claim quá evidence; caveats giải thích đầy đủ một chỗ. | Chờ T31 |
| T33 | Tác giả xác nhận metadata và route nộp lại — R18. | Master record tên/thứ tự/ORCID/affiliation/email/CRediT đã xác nhận; xử lý tên/ORCID lệch; kiểm decision letter/quyền nộp lại. Có thể thu thập sớm, không tự đoán. | Chờ tác giả |
| T34 | Response đủ R1–R18 và archive — R9. | Action/evidence/locator/giới hạn từng yêu cầu. Tác giả tự publish lấy PID thật khi có quyền chia sẻ; Codex chuẩn bị package/lệnh, không tự gọi API upload. Thiếu PID giữ pending. | Chờ T32/T33 |
| T35 | Build/QA hai PDF và chốt locators. | Không undefined refs/citations; tables/totals/captions/figures đúng release; main/submission nhất quán. Kiểm trực quan appendix, bỏ trùng và chi tiết vận hành; không tăng độ dài để chứa mọi artifact. | Chờ T34 |
| T36 | Nghiệm thu, commit/merge và bàn giao. | Comment chỉ đóng khi đủ thay đổi/evidence/vị trí bài/response. Thiếu gì ghi đúng; merge `fix`, xóa task branch local; không push/submit. | Chờ T35 |

## 4. Lệnh API dành riêng cho tác giả

Chạy PowerShell tại root repo sau T01. **Codex không chạy các lệnh API bên dưới.** Hai run đã chuẩn bị và smoke đủ; không chạy lại `prepare` hoặc xóa checkpoints.

**T02 — tiếp tục tập chính đã sửa chart:**

```powershell
py -3.13 -X utf8 scripts/run_chart_rerun.py run --all
```

Đầu ra `outputs/revision/chart_r1_run_v1/`; mục tiêu 474 research +10 smoke, hiện thiếu 336 research Decisions. Năm worker dùng pool năm org Free, tái dùng responses hợp lệ.

**T03 — sau khi T02 hoàn tất, tiếp tục panel R4:**

```powershell
py -3.13 -X utf8 scripts/run_chart_rerun.py run-r4 --all
```

Đầu ra `outputs/revision/chart_r4_run_v1/`; mục tiêu 270 Decisions, hiện thiếu 264. Không chạy song song hai lệnh nghiên cứu này. Khi tất cả provider hết quota: giữ nguyên inputs/code/checkpoints, đợi quota khả dụng rồi chạy lại đúng lệnh còn dở. Lỗi hash/schema/integrity phải dừng để xử lý; không bypass verifier, đổi model hoặc điền CASH.

**Kiểm tra tiến độ offline — Codex được phép chạy:**

```powershell
py -3.13 -X utf8 scripts/run_chart_rerun.py status
py -3.13 -X utf8 scripts/run_revision_r4.py status --bank outputs/revision/chart_r4_bank_v1 --run outputs/revision/chart_r4_run_v1
```

Lệnh `run_revision_72h.py smoke/run` và R4 mặc định trỏ study cũ đã đủ dữ liệu; không dùng để chạy lại. Nếu task khác cần API mới: phải có CLI đã kiểm thử, protocol/input/version và số jobs dự kiến; ghi lệnh chính xác vào task để tác giả tự chạy, không tự mở rộng thí nghiệm.
