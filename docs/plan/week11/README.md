# Tuần 11 — Kiểm định phiên bản hợp nhất và khóa kết quả nghiên cứu

**Trạng thái: U11-02 DONE ngày 26/10/2026, 2/10 task DONE.**
[Kế hoạch tổng](../plan.md) · [Thiết kế W10](../week10/README.md) · [W12](../week12/README.md)

Development đã **RELEASED_FOR_DEVELOPMENT** theo [nghiệm thu U11-01](#u11-01--dry-run-và-release-development-26102026).
**U11-02 đã hoàn tất 300/300 slot primary và 216/216 slot repeat**;
[nghiệm thu cuối](#nghiệm-thu-hoàn-tất-u11-02) trên run thật PASS, không còn
slot planned/unknown. Tiếp theo **U11-03** verify/analysis và xét nomination
theo rule đã khóa. Nomination/xác nhận 2025 vẫn chưa được cấp.

## Mục tiêu và đối chứng

Trả lời ba câu hỏi riêng: U-BICL có ích so Original không; có tốt hơn A trên
cùng nguồn không; demonstrations và stats có đóng góp tăng thêm không.
Không lấy việc xóa revision cũ làm bằng chứng phương pháp mới chưa từng
chịu selection; 2023/2024 đã xem vẫn được khai báo. Chỉ một candidate U_full.
Không chọn U_stats/U_examples làm sản phẩm sau khi thấy chúng thắng.

| ID | Nội dung | Vai trò |
| --- | --- | --- |
| Original | Không prior, instructions/schema chung của run | Đối chứng hệ thống gốc trong protocol mới |
| A_reference | Thuật toán/evidence A, nguồn memory chung, shared-off mới | So U với phương pháp mạnh nhất đã có bằng chứng; không tái hiện W9 nguyên byte |
| U_full | Posterior đã khóa + context task/episode theo rule | Candidate duy nhất |
| U_stats | Cùng base evidence, chỉ stats | Đo lợi ích tăng thêm của demonstrations |
| U_examples | Cùng base evidence, chỉ examples/task context | Đo lợi ích tăng thêm của posterior stats |
| Numeric_only | Posterior mean>0,5 khi ready, còn lại CASH có reason | Đối chứng số học, không LLM, không candidate |

U_examples được phép hiển thị nhãn/cặp x→y và support nhóm cần hiểu task;
không hiển thị posterior/CrI hay recommendation từ stats. Summary tỷ lệ nhóm
là một phần demonstration, phải giữ nguyên giữa full/examples và mô tả rõ:
contrast đo block posterior, không có nghĩa loại mọi thông tin thống kê.
U_stats không chứa x→y, task IDs hoặc ví dụ ẩn. Cả ba dùng cùng evidence hash;
fallback visibility khác nhau theo block, phải báo G và T cùng ready riêng.

## A. Development và nomination trước xác nhận

Giữ 60 ngày 2023 đã khóa, FPT12/MWG16/VCB16/VNM16; không lấy ngày thuận lợi
khác. Năm nhánh LLM ×60=300 slot primary, Numeric tính offline. Original
đầu mỗi block; năm mã logic còn lại gồm Numeric nhưng chỉ bốn nhánh LLM
được xoay theo index j mod 4, điểm xếp (ngày, FPT/MWG/VCB/VNM). Cùng upstream
một lần/point và deep-copy; chỉ reuse upstream lịch sử khi identity verified,
nếu không thì tạo mới một lần cho cả ma trận trước Decision. Khóa cách này
trước run, không chọn upstream tạo lợi nhuận tốt.

Repeat development: 12 điểm, mỗi mã ba điểm chọn bằng readiness U_full
trước action: ngày đầu của both-ready, one-block-ready, off; stratum rỗng
bù ngày đầu chưa chọn của mã, ghi reason. Lặp ba lượt bổ sung, năm nhánh
LLM + Original_duplicate=216 slot; Original đầu, năm nhánh còn lại xoay
(3j+r−1) mod 5. Shared upstream/request primary, source Original theo repeat.
Không vote, chọn response hoặc nhập repeat vào D primary; retry HTTP không
phải repeat khoa học. Slot logic khác HTTP thật khi shared-off; báo cả hai.

Nomination yêu cầu: đủ 60 point, metric hữu hạn, bốn gate/primary/repeat
verify PASS; prior visible≥30/60 và ≥5/mã; examples visible≥12/60 và ≥2/mã
để thực sự kiểm ICL. Gate multi-task ở W10 quyết định mức claim, không giả
task coverage khi chỉ có episode fallback. Nếu thiếu coverage, report
insufficient evidence và dừng release; không hạ ngưỡng sau kết quả.

Gate kinh tế development: D_U−Original>0, ΔR>0 ở ≥3/4 mã, D_U−A≥0,
mean ΔMDD≤2 và max ΔMDD≤5 đpt. Các ngưỡng là rule lựa chọn, không kiểm
định thống kê xác nhận. Báo mọi nhóm xấu/repeat; không chọn bằng một repeat
thuận lợi. Không đạt thì không mở xác nhận để cứu kết quả hoặc chọn ablation;
chuyển sang hoàn thiện luận văn, ghi U chưa được chứng minh. Một vòng duy nhất;
sửa lỗi đổi hành vi sau outcome cần revision/exploratory riêng và công bố
lượt cũ, không ghi đè rồi coi là run đầu tiên.

## B. Xác nhận độc lập sau khóa

Dự kiến 2025: 128 điểm, 32/mã, tám/quý. Rebuild audit từ nguồn hợp lệ; không
tái dùng output revision đã rút làm execution plan. Giữ step3 neo phiên đầu
năm, cycle hoàn tất trong quý, loại quyền/thiếu giá theo rule nguồn; với N
ngày hợp lệ/mã/quý lấy floor(j*(N−1)/7), j=0..7. N<8 thì BLOCKED trước API,
không giảm N sau outcome. Giá thô/PIT/exposure audit và MDE simulation train/
dev phải có trước release; không coi N=128 đủ power một cách mặc định.

2025 đã từng có audit/khai báo trong lịch sử; xác minh có sử dụng mới để
tune hay không, không chứng nhận độc lập bằng cách xóa file. Không xác minh
được thì cohort chỉ exploratory, hoặc forward từ sau lock nếu đủ thời gian.
Không lấy phần 2024 còn lại để làm holdout mới. Không append outcome 2025
vào memory trong run xác nhận này. Không mở 2025 trước nomination/release.

Ma trận sáu ID như trên, năm nhánh LLM ×128=640 slot primary. Mẫu repeat
xác nhận 12 điểm bằng cùng rule readiness, ba lượt ×6=216 slot; lock mẫu và
thứ tự trước action. Numeric offline. HTTP thực tế thấp hơn số slot logic
nhờ reuse; không coi reuse/alias là số quan sát độc lập tăng thêm.

Nghiên cứu tối đa 300+216+640+216=1.372 slot Decision LLM logic, chưa tính
upstream/retry/preflight; đây là mô tả protocol, không là dự toán quota.
Người dùng tự chạy API; hoàn thành development không tự cấp release xác nhận.

## C. Phân tích và tiêu chí khẳng định hữu ích

Primary D=(1/4)Σ(R_U,s−R_Original,s), bốn tài khoản 50 triệu, cổ phiếu lẻ/
lot theo engine, net đầy đủ phí/slippage. Không mean cycle hoặc portfolio.
G chỉ COMPLETE khi mọi nhánh đủ 128 điểm; unknown/error/missing không CASH,
không bỏ điểm lỗi. T cùng stats/examples ready là subgroup mô tả, không thay G.

Circular moving-block bootstrap theo ngày cutoff duy nhất, giữ mọi mã/nhánh
cùng cụm; dựng lại tài khoản theo chuỗi resample. L=4, 10.000 draw,
PCG64 seed=20261024; percentile linear, CI95% primary, ≥9.500 finite draws,
không sinh bù invalid. Sensitivity L=2/8 mô tả, không chọn CI đẹp. Báo count
mã/draw và invalid reasons. Không cộng các Δcycle để thay account return.

Secondary family cố định: U_full−A_reference, U_full−U_stats,
U_full−U_examples, U_full−Numeric_only; Bonferroni CI98,75% từng contrast,
cùng draws/common support. Nếu ID/request alias thì công bố, không tăng mẫu.
MDD, accuracy/balanced accuracy, LONG/CASH, hit rate, regime/quý, LOSO,
prior-off/readiness, task/fallback strata đều mô tả; không chọn nhóm thắng
thay primary. Sharpe/Sortino giữ chu kỳ, không tự annualize √252.

| Bằng chứng | Claim được phép |
| --- | --- |
| Primary CI hoàn toàn >0 | U có ích hơn Original trên cohort/protocol và Decision đã lưu |
| Secondary U−A CI hoàn toàn >0 | Hợp nhất vượt phương pháp A trên cùng nguồn/protocol mới |
| Full−stats CI>0 sau hiệu chỉnh | Block demonstrations có đóng góp tăng thêm |
| Full−examples CI>0 sau hiệu chỉnh | Block posterior có đóng góp tăng thêm |
| CI chạm/qua 0 | Chưa đủ bằng chứng, không phải tương đương hoặc không có hiệu ứng |
| Chỉ Numeric thắng | Báo lợi ích của mô hình số; không gán công cho Bayesian ICL |

CI điều kiện trên saved Decision, chưa bao phủ training/provider uncertainty.
Repeat báo disagreement từng nhánh/Original-duplicate, contrast từng lượt và
mean, đủ mẫu số; các cặp phụ thuộc không là quan sát độc lập. Prior-off=0 do
reuse không chứng minh LLM ổn định. Nếu repeat đổi dấu hoặc duplicate nhiễu,
nêu rõ hạn chế tái lập dù CI primary dương; không claim live/deterministic.

## D. Khóa nghiệm thu và luận văn

| Task | Công việc | Phụ thuộc | Đầu ra/nghiệm thu | Trạng thái |
| --- | --- | --- | --- | --- |
| U11-01 | Dry-run/release development, nguồn/model/order/repeat | U10 | Bốn gate/source/prompt PASS; CLI đã kiểm | [x] DONE — release development; cold verify và hash gate W10 PASS, chưa API thật |
| U11-02 | Người dùng chạy primary/repeat development | 01 | Slot đầy đủ, journal/reuse/ledger, không unknown | [x] DONE — 300 primary +216 repeat complete, source/journal/ledger/report verify PASS |
| U11-03 | Verify/analysis và khóa nomination | 02 | Rule đã đăng ký, G/T/task/fallback/repeat đầy đủ; không chọn ablation | [ ] TODO |
| U11-04 | Exposure/giá mới, manifest và release xác nhận | 03 đạt | 128 điểm/matrix/seed/source/receipt khóa trước outcome | [ ] TODO |
| U11-05 | Người dùng chạy primary/repeat xác nhận | 04 | Đúng namespace/identity, không đổi phương pháp giữa run | [ ] TODO |
| U11-06 | Semantic/PIT/kinh tế/paired/reuse verification | 05 | Đủ G, không missing/unknown, nguồn/hash đúng | [ ] TODO |
| U11-07 | Bootstrap, ablation, noise và failure analysis | 06 | Primary/family/CI/rủi ro/mẫu số và kết quả bất lợi đầy đủ | [ ] TODO |
| U11-08 | Đóng băng evidence, bảng/hình và checksum | 07 | Run/response/HTTP/source/config/version tái lập, không key | [ ] TODO |
| U11-09 | Viết kết quả/thảo luận và phân loại claim | 03; 08 nếu có | Không trộn W9 với U; khai báo các vòng phát triển đã xem | [ ] TODO |
| U11-10 | Bàn giao W12, hướng dẫn verify và giới hạn | 09 | Quyết định research/deployment riêng; không tự bật mặc định | [ ] TODO |

Đầu W11 ưu tiên development, giữa tuần lock xác nhận nếu đạt, cuối tuần
phân tích. Nếu API kéo dài, W12 chỉ tiếp tục đúng run đã khóa và ưu tiên
bản nộp; không tối ưu thêm hoặc giảm mẫu cho kịp. Task xác nhận thiếu điều
kiện ghi NOT_RUN/BLOCKED, không PASS giả. Một thiết kế kiểm chứng được và
kết quả trung thực vẫn là đóng góp khóa luận; không thể hứa trước kết quả thắng.

Runtime/producer/loader/verifier/schema namespace `unified_bic_v1` đã bàn giao
ở W10; không ghi vào W9 hoặc ledger giả. Kiểm thử khi sửa code theo phạm vi
tại [AGENTS.md mục 1.2](../../../AGENTS.md#12-điều-kiện-tiên-quyết-để-hợp-nhất-merge-criteria-vào-develop).
Mốc release đối soát bốn gate trên đúng code/runtime đã khóa; không chạy lại
toàn suite khi chỉ đổi tài liệu và các binding đó còn nguyên vẹn.

## U11-01 — Dry-run và release development (26/10/2026)

**Quyết định: RELEASED_FOR_DEVELOPMENT**, chỉ áp dụng cohort 2023 và một
candidate U_full đã khóa. Release được ghi tại README này, không phải cờ
JSON mới hoặc authorization API đã thực thi. CLI production vẫn kiểm nguồn,
technical receipt/readiness, tokenizer và preflight trước primary. Người dùng
thực hiện các bước online của U11-02; chưa nomination hoặc release xác nhận.

### Bộ nguồn và phiên bản được phát hành

Giữ nguyên bộ local trong `outputs/bayesian_benchmark/unified_bic_v1/` và
ledger chung `outputs/oos_pilot/api_usage.json`, theo [bảng đường dẫn runbook](../week10/unified_bic_operations.md#1-bộ-bàn-giao-và-trạng-thái-ban-đầu).
Các artifact ignored không đi cùng clone Git sạch; không prepare/initialize
lại để thay bằng nguồn khác. Mốc Git trước task là
`dcd9f32892590bf58263031becc64e9122add436`; code/runtime không đổi ở U11-01.
Cold loader tái dựng **60 upstream W8/W9 và 300 canonical request** từ nguồn
đã kiểm. Reuse đúng một upstream/point, deep-copy sang các nhánh/repeat;
không tạo upstream mới hoặc dùng Decision lịch sử làm feature.

Các hash dưới đây là **SHA-256 byte file**, trừ dòng ghi rõ digest semantic:

| Binding | SHA-256 |
| --- | --- |
| `development/plan.json` — 16.334.413 byte | `4bb127868e40c6cf04fb7b9a51425f520a29e95adaaa994c1ae942a36b7ddc35` |
| Digest semantic plan, dùng trong receipt/bridge | `f4af6edec9683bdc5b13ff7d1a604222783050573b47e58fdff8a2f7c73b3f59` |
| `inputs/execution_contract_v1.json` | `9d7ef5d43b7ebde1cd697aa1417730184600d38d815969ca92b15a4623f1abd0` |
| `development/readiness/assessment.json` | `6464e0f7b93315d00461b1806bc7cd0aa9fe5348b463a549916c2dec5655379d` |
| `development/readiness/execution_readiness.json` | `9c3504e1b503add9e4e82a239d627239e10c61f2d171a6e9686d6cf5e10e28d1` |
| Digest semantic schedule | `39befcf6e68f6cd2389fd4024b43da3291683c267f0d2271aca680209b3d0591` |

Digest semantic dùng `core.historical_signals.digest`, khác hash byte của
envelope. **358 nguồn**, **22 file execution code/schema**, **308 file
code/test/fixture/schema/config trong audit** và runtime Python **3.13.5**
đều khớp binding đã khóa. Receipt/audit hiện hành là bộ
`validation/20261025T220030_8658658ad88c4fe1ba8b33afe7e273de/`:
`technical_gates.json` có hash byte
`9921725569add0115cd482de02c6ab990cec18948e71fd17322f6abfe86c4d29`,
`validation_audit.json` có hash byte
`5f7b08e72f3d7c5df46114546b8b18b1ac90cbfc6cd888004311092f4e1d6019`.
Verifier đối soát cả diagnostics và bốn log thực, không chỉ đọc nhãn PASS.

Decision giữ `openai/gpt-oss-20b`, temperature=0, max_tokens=2048,
reasoning_effort=`low`, reasoning_format=`hidden`, service_tier=`on_demand`,
n=1/stream=false và schema `TradeDecisionOutput` chung. SDK max_retries=0;
retry đi qua wrapper/pacer đã khóa. Model upstream trong provenance là
`qwen/qwen3.8-27b`, temperature=0, max_tokens=1024; development chỉ reuse
upstream đã kiểm, không gọi lại vision. **Tokenizer cache PASS**; các tên
model/options là identity của run, khả năng gọi provider hiện tại vẫn cần
preflight phi nghiên cứu do người dùng chạy.

### Cohort, thứ tự và repeat trước action

Giữ **60 điểm / 21 cutoff**, FPT=12, MWG/VCB/VNM=16; năm nhánh LLM và
Numeric_only offline. Primary xếp theo (ngày, FPT/MWG/VCB/VNM), Original
đầu, xoay `[A_reference, U_full, U_stats, U_examples]` theo j mod 4.
Repeat giữ đúng 12 điểm sau, chọn ngày đầu từng stratum readiness trước
action; đủ ba strata/mã nên không cần fill:

| Mã | both_ready | one_block_ready | off |
| --- | --- | --- | --- |
| FPT | 2023-06-27 | 2023-06-01 | 2023-04-12 |
| MWG | 2023-01-06 | 2023-07-31 | 2023-03-30 |
| VCB | 2023-02-08 | 2023-06-01 | 2023-01-06 |
| VNM | 2023-02-08 | 2023-01-06 | 2023-03-30 |

Sắp lại mẫu repeat theo cùng (ngày, mã), j=0..11; r=1,2,3. Original đầu,
xoay `[A_reference, U_full, U_stats, U_examples, Original_duplicate]` theo
(3j+r−1) mod 5. Tổng **96 block, gồm 300 slot primary + 216 slot repeat**;
Numeric_only 96 block offline, không tính là slot LLM. Oracle độc lập trên
plan khớp đủ mẫu/lý do chọn, thứ tự 96 block và model/options của 300 body.
Shared-off chỉ reuse Original durable cùng point/repeat khi body trùng;
duplicate luôn độc lập. Không vote hoặc nhập repeat vào primary.

Coverage dự kiến, chưa là common support của LLM đã chạy:

| Mã | Điểm | Prior U_full visible | Examples visible | Có ≥2 task |
| --- | ---: | ---: | ---: | ---: |
| FPT | 12 | 9 | 5 | 3 |
| MWG | 16 | 14 | 13 | 11 |
| VCB | 16 | 13 | 12 | 10 |
| VNM | 16 | 15 | 11 | 10 |
| Tổng | 60 | 51 | 41 | 34 |

Cả ba gate coverage dự kiến PASS theo rule đã đăng ký. Context có 41 task/
19 off, chưa dùng episode fallback. Prefix tối đa toàn ma trận **518/600**
(U_full **406/600**); prompt tối đa **4.570<6.500**. Cold diagnostics kiểm
PIT/partition/membership/alias, cùng Full/base/instruction và ngân sách prompt;
assessment tái dựng coverage/repeat/MDE từ train, không dùng payoff query.

### Kiểm tra và bàn giao U11-02

Đã chạy PASS các lệnh production offline sau trên nguồn thật:

```powershell
$validationAudit = "outputs/bayesian_benchmark/unified_bic_v1/validation/20261025T220030_8658658ad88c4fe1ba8b33afe7e273de/validation_audit.json"
py -3.13 -X utf8 scripts/run_unified_bayes.py --dry-run
py -3.13 -X utf8 scripts/prepare_unified_bayes_readiness.py --validation-audit $validationAudit
py -3.13 -X utf8 scripts/run_unified_bayes.py --verify-report
py -3.13 -X utf8 -c "from core.groq_pacing import tokenizer_cached; assert tokenizer_cached(), 'Thiếu tokenizer cache'; print('Tokenizer cache PASS')"
```

Readiness/source/prompt và report đã lưu khớp bản tái dựng. **516 journal
slot vẫn planned**, attempts rỗng/output null; **96 evaluation null**,
primary/repeat INCOMPLETE, observed LLM common support=0, HTTP nghiên cứu=0.
Chưa tạo `authorization.json` hoặc `preflight.json`. Metadata snapshot
`PENDING_U10_09`/`PENDING_U10_10_AND_U11_01` giữ nguyên byte; trạng thái
release hiện hành nằm ở README này, không sửa snapshot để đổi tiến độ.

Task chỉ đổi tài liệu/quy định kiểm thử, không đổi code/test/schema/config/
runtime/input. Theo AGENTS.md 1.2, **không chạy lại compileall/unit/E2E/
leakage toàn hệ thống**. Viện dẫn gate **U10-09** đã PASS: compileall,
**1111/1111 unit**, E2E và **248/248 leakage**; đã đối soát lại code/runtime/
source/receipt/log, không ghi là chạy lại. Kiểm diff/UTF-8/liên kết/hash PASS;
**6.822/6.826 file outputs cũ nguyên byte**, gồm W9, ledger, plan, Decision
journal, report/readiness/receipt U10. Bốn file metadata khóa
`run.owner.json`/`run.recovery.json` tại run và `run/journal/` được CLI
`--verify-report` cập nhật theo cơ chế mở/nhả khóa; owner đều `released`,
lịch sử recovery được giữ tiếp. Không thêm/xóa file outputs hoặc tạo
receipt lặp lại theo task.

Người dùng tiếp tục [mục 2–4 runbook](../week10/unified_bic_operations.md#2-kiểm-offline-trước-release-hoặc-resume):
verify offline, preflight, primary `--run --resume`, verify/report, rồi ba
repeat `--run --resume --repeats` và verify/report. Giữ đúng receipt/bridge/
plan/run/ledger khi resume. Preflight lỗi phải dừng, giữ journal/usage và
identity; không đổi model hoặc bỏ điểm để chạy tiếp. **U11 đạt 1/10**,
tiếp theo **U11-02**; nomination/xác nhận và mặc định/risk OFF giữ nguyên.

## U11-02 — Primary/repeat và phục hồi sau quota (26/10/2026)

**DONE ngày 26/10/2026.** Primary/repeat và cold verifier báo cáo cuối đều
COMPLETE/PASS; [nghiệm thu hoàn tất](#nghiệm-thu-hoàn-tất-u11-02) ghi số liệu
và hash bàn giao U11-03.

**Lịch sử xử lý lỗi resume:** snapshot tại lúc vá entrypoint có preflight
complete, **157 slot primary complete**, **1 slot unknown**, **358 slot
planned** (gồm 216 repeat). Slot unknown là
`VNM-2023-07-05 / r=0 / A_reference`; giữ UUID/attempts/cache và mọi output
cũ. Số liệu U11-01 phía trên là snapshot trước khi bắt đầu API, không phải
trạng thái hiện hành. Chưa phân tích để chọn phương pháp hoặc nominate.

Nguyên nhân lỗi `Input/plan đã khóa với identity khác; cần run mới`:
entrypoint online cũ luôn truyền `CohortRun(..., create=True)`, khiến
`ExecutionJournal` so slot đã tiến triển với planned ban đầu. Không phải
identity nghiên cứu đổi theo key. Kiểm thử W10 đã mở handle tiếp theo với
`create=False`; đường online CLI sau restart chưa được kiểm đúng tình huống
này. Giữ nguyên lỗi/lượt chạy cũ để công bố, không khởi tạo lại run.

Adapter vận hành mới [tools/resume_unified_bayes.py](../../../tools/resume_unified_bayes.py)
chỉ thay cách mở handle sang đường `create=False` sẵn có. Parser/source,
authorize, tokenizer, credential, provider quota, retry/UUID, canonical body,
paired protocol và report vẫn do CLI/kernel cũ thực hiện. Không đổi model,
prompt, kết quả hoặc protocol sau outcome. Default offline không đọc key/
gọi HTTP; online bắt buộc `--run --resume` và preflight cũ complete. Hai đường
gate/readiness mặc định đúng bộ U11-01, không cần dựng lại biến PowerShell.

Khi người dùng chạy online lần đầu bằng adapter, nó ghi receipt vận hành
`development/run/resume_entrypoint_v1.json` gắn hash byte adapter, run
signature, plan, execution code và runtime. Receipt này được kiểm lại cùng
mọi guard kernel trước HTTP/retry; không sửa hoặc thay authorization/receipt
bốn gate. Adapter và test đi kèm ở `tools/` được nghiệm thu bổ sung riêng,
ngoài cây code/test nguồn đã đóng băng của W10; không coi gate W10 là test
đã chạy cho code adapter mới. Đây là sửa cách mở checkpoint, giữ cùng run
và công bố can thiệp vận hành trước khi tiếp tục.

Sau khi tiến trình cũ dừng và người dùng đã lưu key mới vào `.env`, chạy
**một lệnh**, chờ kết thúc; nếu lại dừng vì quota thì sau khi giải quyết
credential/quota chạy lại đúng lệnh này:

```powershell
py -3.13 -X utf8 tools/resume_unified_bayes.py --run --resume --env-file ".env"
```

Primary COMPLETE mới chuyển ba repeat với `--repeats`; từng lệnh verify/
report theo [runbook](../week10/unified_bic_operations.md#4-dừng-ngắt-và-resume).
Giữ ledger/cache/journal và các slot complete, không đổi key khi tiến trình
cũ vẫn sống. Agent chỉ chuẩn bị/kiểm offline và HTTP mock, không dùng key
hoặc gọi API thật để chạy tiếp thay người dùng.

**Kiểm tra theo phạm vi PASS:** chín ca mới trong
[tools/test_resume_unified_bayes.py](../../../tools/test_resume_unified_bayes.py),
gồm tái hiện lỗi cũ, đổi credential sau quota với ledger tổng/cùng UUID,
restart CLI online thật qua biên source/credential/HTTP mock, không replay
complete/repeat, không tạo slot mất và chặn adapter/receipt đổi. Bốn ca cũ
liên quan auth/quota/partial resume/durable preflight cũng PASS: **13 ca**
tổng cộng. Biên dịch đúng hai file Python mới PASS; không chạy toàn suite,
E2E hoặc leakage do không đổi đường dữ liệu/PIT, prompt hay kernel kinh tế.
Scope validation W10 vẫn đúng **308 file**, runtime và receipt/bốn log còn
khớp; chỉ viện dẫn gate cũ cho đúng code cũ, adapter có các test riêng trên.

Ở thời điểm nghiệm thu bản vá, lệnh
`py -3.13 -X utf8 tools/resume_unified_bayes.py --verify-only` trên run
thật PASS, primary/repeat vẫn INCOMPLETE. Ledger, cache, 516 Decision slot,
plan, authorization/preflight và mọi nguồn cũ nguyên byte; chỉ bốn metadata
owner/recovery của khóa run/journal được verifier cập nhật, owner released.
Lần kiểm offline bản vá chưa tạo receipt adapter hoặc HTTP mới trên run
thật. Giữ `tools/` và receipt adapter cùng run khi đóng băng evidence U11-08.
Nghiệm thu hoàn tất dưới đây dựa trên kết quả API thật do người dùng chạy,
không dùng test mock thay kết quả nghiên cứu.

### Nghiệm thu hoàn tất U11-02

Người dùng đã hoàn tất primary, ba repeat và chuỗi verify/report trên cùng
run đã khóa. Agent chạy lại **một cold verifier báo cáo**:

```powershell
py -3.13 -X utf8 tools/resume_unified_bayes.py --verify-report
```

Kết quả **`Snapshot/report PASS: primary=COMPLETE, repeat=COMPLETE`**.
Verifier tái dựng source/plan/request, đọc toàn journal/ledger/cache và
đối chiếu report lưu trên đĩa; không đọc key hoặc phát HTTP mới. Đối soát
riêng lịch/UUID/reuse/receipt/common support và hash nguồn cũng PASS:

| Bằng chứng | Primary | Repeat | Tổng |
| --- | ---: | ---: | ---: |
| Block đã có evaluation | 60 | 36 | 96 |
| Slot LLM complete | 300 | 216 | 516 |
| Slot invoked có output/UUID riêng | 248 | 156 | 404 |
| Slot reuse Original cùng point/repeat | 52 | 60 | 112 |
| Slot planned/unknown/missing | 0 | 0 | 0 |

Common support primary đủ **FPT=12, MWG=16, VCB=16, VNM=16**, không loại
điểm lỗi. Numeric_only được tính offline đủ 96 block, không tăng số slot
LLM. Mẫu repeat giữ 12 điểm, ba điểm/mã và đủ r=1,2,3; mỗi lượt đủ
3 điểm/mã. Nhánh Original_duplicate có **12/12 cặp mỗi lượt, 36/36 tổng**,
UUID khác Original; các nhánh đều đủ **36/36 cặp so giữa các repeat**.
Repeat/duplicate giữ riêng, không vào primary hoặc tạo thêm quan sát độc
lập. Slot từng unknown tại `VNM-2023-07-05 / r=0 / A_reference` đã complete,
giữ UUID và recovery audit cũ.

Ledger của signature nghiên cứu có **411 lượt HTTP ghi nhận**: **404 HTTP
200, 3 HTTP 429 và 4 transport_error**, không tính preflight riêng. Mỗi
invoked slot có đúng một HTTP 200 được lưu/đối soát; lịch sử retry và lỗi
không bị xóa. Số slot logic 516 bao gồm 112 reuse, không đồng nghĩa 516
HTTP hoặc quan sát độc lập. Usage đo được **756.574 token** trên 404 lượt
thành công; bảy lượt không có usage giữ null/reserve theo policy, không
điền 0. Không còn unknown ở slot nghiên cứu không có nghĩa xóa bất định
của các lượt HTTP lỗi trong ledger.

Các binding bàn giao hiện tại, **SHA-256 byte file**:

| Artifact | SHA-256 |
| --- | --- |
| `development/run/report.json` — 4.733.971 byte | `5f691d4813b2c19965170f774486073840c3776248d2e452b837a725e511cd18` |
| `development/run/resume_entrypoint_v1.json` | `6cfc14af04836714bfd71e64d14b3f65dc790337ed4335e39bacc15ce8cc5da2` |
| Ledger chung `outputs/oos_pilot/api_usage.json` | `e73a87e2a45d73e76f63cdd58225c2de06b0df4e03ed09b91ad0f6f71c5c8796` |

Plan byte/digest, cohort signature, authorization, preflight, source,
model/options, schedule và mẫu repeat vẫn đúng khóa U11-01. Receipt adapter
khớp byte code hiện hành; scope W10 **308 file**, runtime và receipt/bốn log
vẫn khớp. Bàn giao nguyên plan/run/HTTP cache/journal/receipt adapter,
authorization/preflight, ledger và bộ validation cho U11-03; các artifact
ignored cần được giữ cùng workspace, không tạo receipt lặp lại chỉ để ghi
checklist.

**Phạm vi task chốt thuần tài liệu:** không sửa code/test/schema/config/
runtime/input hoặc gọi API thật. Theo AGENTS.md 1.2, không chạy lại
compileall/unit/E2E/leakage; viện dẫn đúng gate U10-09 và **13 ca kiểm tra
adapter đã PASS** của bản vá, không ghi là chạy lại. Diff/UTF-8/liên kết/
hash được kiểm; chỉ metadata owner/recovery của khóa được verifier cập
nhật, Decision/cache/ledger/report và bằng chứng cũ giữ nguyên byte trong
lần chốt.

**U11 đạt 2/10**, chuyển **U11-03** để kiểm định/phân tích đầy đủ và xét
nomination duy nhất U_full. `nomination_allowed=false`,
`confirmation_allowed=false` trong report giữ nguyên; hoàn tất thực thi
không tự cấp nomination, release 2025 hoặc bật risk/mặc định hệ thống.
