# Kế hoạch hoàn thiện hệ thống theo 18 nhận xét reviewer

**Thứ tự: hoàn thiện hệ thống → đủ kết quả thật → kiểm chứng → sửa bài một lần → phản hồi reviewer.** Mục tiêu là hoàn thiện phần kỹ thuật và bằng chứng trong **48–72 giờ tiếp theo**, giảm số API calls cần thiết. Đối soát ngày 03/11/2026 theo `Reviewer Comments for author.docx`; thời gian chờ quota, nhãn người, tác giả/PID phải báo riêng, không tự coi đã xong.

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
| Sửa legend Trend; dữ liệu hiện có | [Chart audit](outputs/revision/chart_convention_v1/manifest.json). Đủ 10 smoke, 120 research Trend groups. T01a đã xác minh **187/204** Decisions chính, **2/36** upstream bổ sung và **4/135** của panel chung bằng raw/message/model/parameters/parent. Hai checkpoint R4 ngoài scope đã chuyển vào archive ngoài repo theo yêu cầu tác giả; xem [catalog dọn file](outputs/revision/revision_minimal_v1/cleanup.json). Không tạo lại Pattern/Trend/smoke thành công. |

### Ngân sách rút gọn: khoảng 182 Decisions mới

Năm org × (20 Full +20 Base)/ngày = **200 Decisions/ngày theo ước lượng tác giả**. 600 Decisions tương đương ba ngày năng lực danh nghĩa; sáu ngày chỉ là kịch bản còn 100/ngày, không phải thời gian bắt buộc. Snapshot trước dọn file có 549 Decisions còn thiếu theo thiết kế cũ. Scope mới loại 367 jobs chưa chạy và hai executions đã có khỏi phần bắt buộc; tám file của hai executions đó đã archive nguyên byte ngoài repo rồi xóa theo yêu cầu tác giả, không sửa manifests lịch sử.

| Hạng mục bắt buộc | Tổng scope mới | Checkpoint đã verify để reuse | Cần thêm |
|---|---:|---:|---:|
| 102 điểm × B/AS, realization 0/repeat 0 | 204 | 187 | **17** |
| Upstream chín điểm, thêm hai realizations × B/AS | 36 | 2 | **34** |
| Panel chung repeats + factorial/placebo: chín điểm × B/A/S/AS/P × ba repeats | 135 | 4 | **131** |
| **Tổng** | **375** | **193** | **182** |

- **Bỏ rerun 234 Decisions panel R1 rút gọn.** Panel R4 đủ giá trị phục vụ đồng thời R3 và R4; không cần hai panel repeats cùng mục đích, không hạ repeats xuống một.
- **Không cần hoàn tất cả 270 Decisions R4.** Chọn chín điểm bằng metadata: round-robin mã xếp chữ cái; trong mã theo ngày tăng dần, lấy từ 18 điểm sentiment đã khóa. Không dùng accuracy, prediction hoặc thứ tự hoàn thành để chọn.
- Panel cố định: **BHN 23/09/2026; FPT 23/09/2026; HVN 01/04/2026; MBB 01/04/2026; MWG 23/09/2026; VCB 24/06/2026; VJC 01/04/2026; VNM 19/12/2025; HVN 24/06/2026**. Phủ tám mã, ba block gần đây, bốn ngày; không đại diện chín mã/sáu block. Bốn checkpoint R4 có thể reuse: B/repeat 0 tại VCB, VJC, VNM, MBB trong panel này.
- Upstream chín điểm giữ danh sách đã khóa; main giữ đủ 102 điểm/sáu block. Broad main dùng prompt R1 rút gọn; factorial/repeat dùng prompt R4 đủ giá trị: báo riêng, không gộp metrics hoặc suy variance R4 cho cả main. Không bù thiếu bằng kết quả trước sửa chart.
- Đây là **amendment giảm ngân sách sau một phần inference**, chỉ hỗ trợ historical exploratory; không gọi preregistered confirmatory. Khóa scope/repeats/contrasts trước calls tiếp theo. Run cũ giữ incomplete/superseded; không sửa mẫu số 474/270 trong manifest lịch sử hoặc đánh dấu complete giả.
- Reuse đã PASS kiểm message/model/parameters/input/parent và raw hashes cho đủ 193 records; không sao chép final decision thành repeat. **182 là successes cần thêm, không phải attempts**. [Manifest mới](outputs/revision/revision_minimal_v1/manifest.json) đã khóa 375 jobs, panel/contrasts, 369 jobs bị loại và provenance; [dry-run](outputs/revision/revision_minimal_v1/dry_run.json) liệt kê đúng 182 jobs còn thiếu. Không thay whitelist/code/input đã freeze khi resume.
- Không thêm vision/smoke mặc định: corrected upstream đã có, model/prompt không đổi. Nếu verify phát hiện thiếu/hỏng, báo số calls bổ sung và giao lệnh cho tác giả trước.
- Dự toán **182 successes +khoảng 20% retry =219 attempts**. Ở 200 Decisions/ngày: khoảng 1,1 ngày năng lực, bố trí **hai cửa sổ quota**; ở 100/ngày: khoảng 2,2 ngày. Token/reset thực tế quyết định; đây không phải SLA. Không mua quota/đổi model/cắt prompt để đạt số ngày.
- Giữ [provider-only policy](revision/r1_provider_policy.json), không tái áp cap nội bộ. **Giới hạn scope bằng whitelist jobs**, không chạy đến một con số rồi chọn kết quả. Năm key đã cấu hình; queue dùng shared locks, một request/key xuyên các nguồn run.

### Tổ chức để rút ngắn thời gian

1. **0–6 giờ:** T01a–T01d khóa scope, thêm adapter riêng và tests, bàn giao lệnh cho tác giả. Không chạy tiếp hai grid đầy đủ trong lúc chờ adapter.
2. **6–48 giờ:** tác giả chạy queue rút gọn; Codex làm T05–T18/T21 và chuẩn bị package offline trong lúc chờ. T08/T33/quyền publish/PID hỏi sớm; không đợi API xong mới bắt đầu việc độc lập.
3. **48–72 giờ:** khi đủ calls, làm T04/T19–T30, kiểm package; chỉ sau gate mới sửa bài T31–T36. Có thể phân tích phần đã đủ trước, không chốt contrast thiếu cặp. Nếu quota/evidence chưa đủ thì báo đúng thiếu sót, không tăng scope hoặc điền predictions.

Không thêm LLM fixed/random controls, sweep, horizon/model mới vào đường bắt buộc. R10 làm numeric controls; claim cần ngoài scope phải bỏ hoặc giữ yêu cầu mở. Sentiment domain validation/PID/metadata thiếu không được ghi đã giải quyết để đạt deadline.

## 3. Task còn lại theo thứ tự

Làm từ trên xuống. Khi chờ tác giả/API, có thể làm task offline độc lập phía sau. **Không thay nguồn/runtime đã freeze của run đang dở.** Nếu sửa input inference: tách phiên bản, xác định jobs chịu ảnh hưởng và đưa lệnh mới cho tác giả; không bỏ hash guard để resume.

### A. Hoàn tất bằng chứng bằng queue API rút gọn

| ID | Việc cần làm | Điều kiện hoàn thành | Trạng thái / dependency |
|---|---|---|---|
| T01 | Tái dùng audit integrity/resume đã xong. | [Audit](outputs/revision/chart_resume_audit_v1/report.json), [manifest](outputs/revision/chart_resume_audit_v1/manifest.json) PASS ở snapshot trước calls mới. Không chạy lại toàn audit chỉ để cập nhật plan. | Xong trong scope đã khóa; phần mới ở T01a |
| T01a | Kiểm calls/checkpoints mới, khóa amendment/whitelist 375 jobs. | Main 204 +upstream 36 +R4 135; xác minh reuse 193 records hiện có hoặc cập nhật số thật; origin/hash/exclusions đầy đủ. Chọn panel chỉ bằng metadata. | **PASS**; [manifest](outputs/revision/revision_minimal_v1/manifest.json), reuse 187+2+4; thiếu 17+34+131 |
| T01b | Thêm adapter/CLI riêng chỉ chạy whitelist, xuất release mới. | Không sửa runtime frozen/manifests/counters cũ; reuse parser/retry/archive/node cache, giữ đúng model/messages. Jobs ngoài whitelist không được gọi; raw reuse có provenance. | **PASS**; [bank](core/revision_minimal_bank.py), [queue](core/revision_minimal_run.py), [CLI](scripts/run_revision_minimal.py); release `revision_minimal_v1` |
| T01c | Test offline adapter/resume/lock/quota. | Dry-run đúng missing jobs; raw tamper/mismatch fail; không lặp calls thành công; khóa key xuyên nguồn run; interrupt/resume và retries đếm đúng. Không viết lại engine. | **PASS**; 47 tests, [log](outputs/revision/revision_minimal_v1/validation.log), [dry-run 182 jobs](outputs/revision/revision_minimal_v1/dry_run.json); chỉ biên dịch bốn Python files mới |
| T01d | Bàn giao lệnh đã kiểm thử cho tác giả. | CLI mục 4 executable, paths/version/counts đúng; không còn worker grid cũ; source checks PASS. | **PASS**; `prepare/verify/dry-run/status` đã chạy offline, network/credentials/SDK bị chặn; verify sau cleanup vẫn PASS; API attempts mới =0 |
| T02 | **Tác giả** chạy phần main/upstream của queue. | Main đủ 204, upstream bổ sung đủ 36; hiện thiếu 17+34=51 successes. Không chạy panel R1 234 Decisions. | Chờ tác giả; T01d PASS; dùng lệnh chung mục 4 |
| T03 | **Tác giả** chạy panel chung R3/R4 trong cùng queue. | Đủ 135 Decisions: chín điểm ×năm variants ×ba repeats; hiện thiếu 131. Corrected reports đã có, không cần chờ main xong. | Chờ tác giả; T01d PASS; cùng queue T02 |
| T04 | Verify, khóa và phân tích release rút gọn riêng. | Đủ 375 research executions; scope/source/parent/raw/failures và reuse khớp. Không đóng hai run cũ hoặc đè analysis cũ, không ghi `paper/`. | Chưa làm; sau T02/T03 |

Phạm vi kiểm tra T01c: `test_revision_minimal` (16), `test_revision_72h.DesignTests/QuotaTests` (14), `test_revision_r4_factorial.PromptLeakageTests/ArchiveResumeTests` (8), `test_prepare_chart_r4` (1), `test_chart_rerun` (4), `test_revision_r2_leakage.RegimeLeakageTests` (4). Bao phủ đúng đường adapter → native prompt/parser/retry/archive/cache/lease và PIT/donor được tái dùng; có callback/serializer ChatGroq thật với transport giả lập quota, không network. Không chạy toàn suite/E2E hoặc biên dịch lại code frozen vì không đổi các module đó. T01a khôi phục parent/input đủ 120 research upstream groups, dựng lại prompts và kiểm 193 checkpoint/raw; SHA-256 nguồn/runtime được khóa ở manifest mới. `analyze` chỉ xuất inventory cho T04, chưa phải metrics/baseline/contrasts cuối.

Theo yêu cầu dọn các điểm không còn dùng: đã xóa hai checkpoint R4 của `MBB_f2026_q2_1613` (B/A, repeat 0) và sáu raw files đi kèm, sau khi xác minh ZIP nguyên byte ngoài repo ở `C:/Users/Legion/.codex/archives/revision-minimal-20261103/chart-excluded-904b838a4662.zip`. [Catalog](outputs/revision/revision_minimal_v1/cleanup.json) giữ hash ZIP/từng file; manifest lịch sử không sửa, audit T01 trước đó vẫn là snapshot trước calls mới và cleanup, không tuyên bố kiểm lại được toàn snapshot đó bằng cây file hiện tại. Những nguồn còn được manifest/tests/audit sử dụng được giữ lại; không xóa dữ liệu cần để tái lập hoặc sửa lịch sử Git.

### B. Sentiment — R7 và phần sentiment của R4

| ID | Việc cần làm | Điều kiện hoàn thành | Trạng thái / dependency |
|---|---|---|---|
| T05 | Sửa audit coverage dùng đúng loader/runtime; tái dùng article audit. | Đúng paths; record khác test point; unique theo mã/toàn corpus, duplicates, ngày, URL/content hash và scorer provenance rõ. | **PASS**; [summary](outputs/revision/sentiment_inventory_v1/summary.json), [inventory](outputs/revision/sentiment_inventory_v1/inventory.json), [hash nguồn/đầu ra](outputs/revision/sentiment_inventory_v1/manifest.json); CLI audit độc lập, giữ nguyên nguồn freeze T02/T03 |
| T06 | Xuất coverage từ một nguồn, tách legacy và release mới. | V+L+U=total; percentage khớp count; date-only khả dụng ngày kế tiếp, cửa sổ 90 ngày, >=3 bài hợp lệ. Missing khác neutral; coverage từng cutoff/mã và peer availability rõ. | **PASS**; [coverage từng cutoff](outputs/revision/sentiment_coverage_v1/coverage.json), [summary](outputs/revision/sentiment_coverage_v1/summary.json), [hash nguồn/đầu ra](outputs/revision/sentiment_coverage_v1/manifest.json); main 23/102, upstream 3/9, panel chung 9/9 |
| T07 | Kiểm thử coverage/cutoff/scorer và kiểm prompt thật khi thiếu tin. | Mapping/tokenizer/truncation pinned, tests đúng đường dùng PASS; S ở điểm thiếu tin không được coi là sentiment evidence. | Chưa làm; sau T06 |
| T08 | Chốt domain validation và nguồn tin với tác giả. | Nếu giữ claim chất lượng tài chính: cần nhãn độc lập, hai người, agreement/adjudication, macro-F1/per-class và uncertainty. Nếu chưa có: ghi chưa validation, social-media domain/PIT chưa xác thực và bỏ claim phụ thuộc. Rescore không thay validation. | Chờ tác giả; không chặn T09–T29 |

T05 dùng [CLI mới](scripts/audit_sentiment_inventory.py) và [module inventory](core/revision_sentiment_inventory.py): legacy cache đọc bằng `SentimentCache._load_from_disk` với `cache_dir` tường minh, benchmark lấy đúng `outputs/backtest_result/`; không gọi `preload`, crawler hoặc scorer. Script coverage cũ tìm nhầm `backtest_result/` và gắn kiểm tra bài LaTeX ở `ESWA/`; file đó cùng runtime đã nằm trong freeze của queue đang chạy nên giữ nguyên, thay bằng entrypoint audit độc lập. CSV coverage cũ có counts scorer không khớp percentages; không sửa CSV lịch sử hoặc dùng nó làm nguồn mới. T06 sẽ xuất coverage/cutoff và tỷ lệ từ inventory/runtime đã xác định.

Kết quả T05: chín mã ×20 cache records =**180 records**, mỗi mã có 20 identities; toàn corpus có **177 identities/URL/content hashes**, ba duplicate aliases xuyên mã. Đây khác **180 test points legacy**, **102 market units** và **375 executions** của scope mới. Cả 180 records legacy thiếu scorer provenance, ghi `unknown`; không suy từ score/confidence hoặc cấu hình backend hiện tại. Article audit đã khóa có 23 identities/25 records lệch ngày theo kiểm tra URL, chưa phải kiểm chứng PIT độc lập. Local rescore cũ có **154 identities**, frozen news có **155 symbol–article records/154 identities**; tách riêng hoàn toàn với scorer legacy. Inventory giữ source/index, ngày raw/ngày loader thực nhận, URL raw/normalized hashes, content hash và aliases; không đổi cache/news/prompt.

Kiểm T05: **15 tests PASS** (`test_revision_sentiment_inventory`:10; `test_sentiment_coverage`:2; `test_sentiment_leakage`:3); chỉ `py_compile` ba file Python mới. CLI đã xuất inventory khi chặn network/đọc credentials/preload/rescore; `--check` đối soát 35 source/output hashes PASS. Đối soát **2.331 nguồn frozen của T02/T03 trước/sau đều khớp**, không khóa/dừng worker, không chạm raw/checkpoint/ledger đang ghi và không sửa `paper/`. Không chạy toàn suite/E2E vì chỉ thêm audit offline và tests; T07–T08 chưa được đánh dấu hoàn tất.

Lệnh T05 offline đã kiểm thử: `py -3.13 -X utf8 scripts/audit_sentiment_inventory.py --check`. Lệnh không có `--check` tạo release mới độc quyền (mặc định `outputs/revision/sentiment_inventory_v1/` đã tồn tại); dùng `--output outputs/revision/<release_mới>/` nếu cần snapshot khác, không ghi đè lịch sử.

T06 dùng [module coverage](core/revision_sentiment_coverage.py) và [CLI độc lập](scripts/audit_revision_sentiment_coverage.py), lấy counts/provenance từ cùng inventory T05; không dùng CSV cũ làm đầu vào. Xuất riêng 180 cutoffs legacy và 102 cutoffs release mới, có membership article IDs, V/L/U counts/percentages, số identities có score hợp lệ, missing/neutral và peers từng cutoff/mã. V/L/U legacy là **0/0/180** records (unknown 100%); frozen news **155/0/0** symbol–article records hoặc **154/0/0** identities (ViSoBERT 100% theo provenance rescore, chưa phải financial-domain validation). Mẫu số zero ghi `null`; V+L+U=total, tỷ lệ tính trực tiếp từ cùng counts.

| Support coverage release mới | Có ít nhất ba bài hợp lệ / cutoffs | Tỷ lệ pooled | Missing | Peers được runtime cung cấp |
|---|---:|---:|---:|---|
| Main | 23/102 | 22,55% | 79 | Không khả dụng |
| Upstream chín điểm đã khóa | 3/9 | 33,33% | 6 | Không khả dụng |
| Panel chung R3/R4 | 9/9 | 100% | 0 | Không khả dụng |

Main theo mã: BHN 1/6, CMG 0/12, FPT 1/12, HVN 4/12, MBB 4/12, MWG 1/12, VCB 3/12, VJC 4/12, VNM 5/12. Macro không trọng số theo chín mã là 22,22%, khác pooled 23/102 vì BHN có support nhỏ hơn; không nhân repeats/API executions vào mẫu số cutoff. Cả 102 signed sentiment assets khớp membership/count/missing/score/report của `FrozenSentiment`; `score=null` khi thiếu, không biến normalized zero thành sentiment neutral. Runtime không cung cấp related peers, không lấy alias hoặc cache mã khác làm peer evidence. Normalizer legacy vẫn có cờ `is_reliable` dùng ngưỡng tám bài: 9/102 main, 1/9 upstream, 4/9 panel; ghi riêng với availability >=3, giữ nguyên inputs/prompt đã freeze để T07 đối chiếu tiếp.

Replay legacy bằng `SentimentCache.get_at` thật trên cache hiện có giữ nguyên same-day và neutral fallback lịch sử: 116/180 cutoffs có >=3 records theo runtime cũ, nhưng **không cutoff nào đủ score có provenance để làm sentiment evidence**; không diễn giải đây là không có bài báo. Có 29 lượt article–cutoff cùng ngày được legacy nhận; diagnostic date-only chuyển khả dụng sang ngày kế tiếp, cửa sổ inclusive [cutoff EOD−90d, cutoff EOD]. Đây là audit cache hiện có, không xác nhận ngược cache/peer payload của execution lịch sử, không sửa artifacts cũ.

Kiểm T06: **29 tests PASS** (`test_revision_sentiment_coverage`:12; `test_revision_sentiment_inventory`:10; `test_sentiment_coverage`:2; `test_sentiment_leakage`:3; hai tests sentiment provenance/cutoff của `test_revision_baseline_leakage`). Bao phủ min-three, biên 90 ngày/timezone/available_at, duplicate/conflicting identities, V/L/U/percentages/mẫu số zero, missing khác neutral, pooled/macro, legacy replay và signed asset mismatch. Chỉ `py_compile` ba Python files mới; không chạy toàn suite/E2E vì không đổi runtime inference. T05 hashes vẫn PASS; T06 `--check` đối soát 145 source/output hashes PASS; 2.331 nguồn queue frozen trước/sau vẫn nguyên. Lần xuất thật chặn network, mở `.env`, preload/scoring; không gọi API, không dừng/khóa worker và không ghi `paper/`. Lệnh offline: `py -3.13 -X utf8 scripts/audit_revision_sentiment_coverage.py --check`; muốn snapshot khác dùng `--output outputs/revision/<release_mới>/`, không ghi đè release hiện có. T07/T08 còn mở.

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
| T26 | Xuất repeats và factorial/placebo cuối — R3/R4. | Mean/SD/range/disagreement đúng panel chung chín điểm/upstream chín điểm; contrasts B/A/S/AS/P và interaction cùng parent/support. Full−Base là bundle effect; placebo giữ schema/missingness, donor train-only. Không gộp trước/sau sửa chart. | Chưa làm; sau T04/T07 |
| T27 | Tổng hợp chi phí/integrity — R9/R14. | Calls/tokens/latency/errors/retries thật, tách Pattern replay/calls mới, execution epochs và thiếu jobs. Chart màu/legend/prompt khớp fixture/raw inputs cuối. | Chưa làm; sau T04 |
| T28 | Kiểm tra hồi quy đúng phạm vi thay đổi. | Pairing/isolation, PIT/purge, prompt <6.500 ký tự, node resume, raw tamper, quota/retry, metrics/ledger có evidence phù hợp. Không dùng mocks thay LLM thật, không tự chạy API/toàn suite. | Chưa làm; sau phần kỹ thuật T05–T27; T08 ghi rõ nhánh đã chọn |
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

**Chưa chạy tiếp hai lệnh grid cũ** `run_chart_rerun.py run --all` và `run-r4 --all`: chúng vẫn nhắm 474/270, chưa hiểu whitelist mới. Không sửa manifests để ép runner nhận grid nhỏ. Nếu worker cũ đang chạy, tác giả dừng có checkpoint trước khi chuyển; Codex không tự kill tiến trình hoặc gọi API.

**T01a–T01d đã PASS.** Adapter đã triển khai, freeze và kiểm thử offline; không còn worker grid cũ tại preflight. Chạy PowerShell tại root repo. **Một lệnh `run --all` chạy cả T02 và T03**, dùng năm worker/ledger chung; không mở hai queue riêng.

```powershell
# Offline: kiểm freeze/reuse trước khi tác giả chạy
py -3.13 -X utf8 scripts/run_revision_minimal.py verify

# API T02 + T03 — CHỈ TÁC GIẢ TỰ CHẠY; một queue, năm worker
py -3.13 -X utf8 scripts/run_revision_minimal.py run --all

# Offline: xem tiến độ; có thể dùng sau khi queue tạm dừng
py -3.13 -X utf8 scripts/run_revision_minimal.py status

# Offline: sau khi đủ 375, verify rồi xuất inventory phục vụ T04
py -3.13 -X utf8 scripts/run_revision_minimal.py verify
py -3.13 -X utf8 scripts/run_revision_minimal.py analyze
```

Đầu ra `outputs/revision/revision_minimal_v1/`; manifest signature `904b838a466290d9c8aa73245a6285e813b4f7c90d280355d3b2847ed9933fab`. Hiện có 193/375 executions hợp lệ, cần **182 successes mới** (T02:51, T03:131), không thêm vision/smoke. Queue phân shard theo độ dài prompt trước calls rồi trộn jobs T02/T03; mọi shard mượn key theo org availability, dùng ledger chung và khóa key tại cả nguồn run cũ. Không phân key cố định theo treatment, không bắt R4 chờ main. Mỗi response/repeat có identity riêng; đủ whitelist thì dừng. `prepare` đã chạy và gọi lại chỉ kiểm freeze hiện có; không xóa manifest/checkpoints/ledger để chuẩn bị lại.

Hết quota: giữ inputs/code/checkpoints, đợi reset hợp lệ rồi tác giả chạy lại đúng `run --all`; không reset counters/đổi model/fallback CASH. Lỗi hash/schema dừng để xử lý, không bypass. `prepare/verify/status/analyze` phải offline, không ghi `paper/`.

**Kiểm tra danh sách 182 jobs thiếu, không gọi API:**

```powershell
py -3.13 -X utf8 scripts/run_revision_minimal.py dry-run
```

`dry-run --output <đường-dẫn-file-mới.json>` xuất đầy đủ job IDs/contexts; không ghi đè file cũ. Không dùng status grid cũ hoặc mẫu số 474/270 để nghiệm thu scope mới. Nếu artifact lỗi khiến cần thêm calls, dừng để cập nhật task/budget/version; không tự mở rộng nghiên cứu hoặc sửa freeze để bypass.
