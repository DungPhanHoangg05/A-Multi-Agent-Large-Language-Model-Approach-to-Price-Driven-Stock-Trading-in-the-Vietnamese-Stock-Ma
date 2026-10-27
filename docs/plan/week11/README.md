# Tuần 11 — Kiểm định phiên bản hợp nhất và khóa kết quả nghiên cứu

**Trạng thái: U11-05 DONE ngày 27/10/2026; 5/11 task DONE. Gate payoff R2 FAIL; U11-06–09 NOT_RUN. Tiếp theo: U11-10.**
[Kế hoạch tổng](../plan.md) · [Thiết kế W10](../week10/README.md) · [W12](../week12/README.md)

Development đã **RELEASED_FOR_DEVELOPMENT** theo [nghiệm thu U11-01](#u11-01--dry-run-và-release-development-26102026).
**U11-02 đã hoàn tất 300/300 slot primary và 216/216 slot repeat**;
[nghiệm thu cuối](#nghiệm-thu-hoàn-tất-u11-02) trên run thật PASS, không còn
slot planned/unknown. **U11-03 đã khóa NOT_NOMINATED**: chỉ 2/4 mã tăng so
Original, dưới ngưỡng ≥3/4 dù D dương; xem [quyết định và phân tích](#u11-03--kiểm-định-development-và-khóa-nomination-26102026).
Dừng nhánh xác nhận v1 theo protocol. Theo yêu cầu ngày 26/10/2026,
[kế hoạch cải thiện có giới hạn](#kế-hoạch-bổ-sung-sau-u11-03-26102026)
được gộp vào **U11-04–U11-11**, thực hiện lần lượt theo
[checklist duy nhất](#d-checklist-thực-hiện-tuần-tự-hiện-hành). Không còn
checklist task bổ sung riêng; deadline vẫn W12. Chưa cấp nomination hoặc
release 2025 cho R2. Các mục A–C dưới đây giữ protocol v1 để tham chiếu;
thiết kế R2 và checklist hiện hành là căn cứ cho công việc tiếp theo.

**Cập nhật 27/10/2026:** U11-05 đã khóa protocol và đo đủ 647 query train;
396 điểm common support, đủ tám ô fold/mã. Gate payoff **FAIL**, nên R2 dừng
trước development LLM theo đúng điểm dừng đã đăng ký. U11-06–09 NOT_RUN,
không tính DONE; tiếp theo U11-10 tổng hợp W9, v1 và R2 offline.

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

## D. Checklist thực hiện tuần tự hiện hành

Giữ U11-01–03 đã hoàn tất. Từ U11-04 trở đi thay bằng chuỗi công việc R2
và tổng kết nghiên cứu, không khởi động lại nhánh xác nhận v1 đã dừng.

| Task | Công việc | Phụ thuộc | Đầu ra/nghiệm thu | Trạng thái |
| --- | --- | --- | --- | --- |
| U11-01 | Dry-run/release development, nguồn/model/order/repeat | U10 | Bốn gate/source/prompt PASS; CLI đã kiểm | [x] DONE — release development; cold verify và hash gate W10 PASS, chưa API thật |
| U11-02 | Người dùng chạy primary/repeat development | 01 | Slot đầy đủ, journal/reuse/ledger, không unknown | [x] DONE — 300 primary +216 repeat complete, source/journal/ledger/report verify PASS |
| U11-03 | Verify/analysis và khóa nomination | 02 | Rule đã đăng ký, G/T/task/fallback/repeat đầy đủ; không chọn ablation | [x] DONE — NOT_NOMINATED: chỉ 2/4 mã tăng; source/consumer/oracle PASS |
| U11-04 | Hoàn tất audit 60 point và năm action đổi của v1; reason/trace, payoff/age/conflict, đối chiếu nguồn | 03 đã khóa kết quả | Phân biệt quan sát và giả thuyết nguyên nhân; giữ nguyên evidence, phần đọc sơ bộ chưa tính DONE | [x] DONE — đủ 60 điểm/năm thay đổi, nguồn/trace/payoff/tuổi đã đối soát; xem audit bên dưới |
| U11-05 | Khóa protocol R2 và kiểm mô hình payoff trên train PIT | 04 | Gate offline/support đạt mới tiếp tục; trượt hoặc thiếu support thì dừng trước development LLM | [x] DONE — protocol/code khóa trước đo; 647 query/396 common; gate FAIL, consumer/oracle/test PASS |
| U11-06 | Renderer/payoff/CLI/verifier namespace mới, fixture/12 probe, test phạm vi và dry-run coverage | 05 đạt gate offline | Prompt/semantic/PIT/reuse/coverage PASS; U11-04–06 tối đa hai ngày làm việc, chưa đủ kỹ thuật thì không chạy development | [ ] NOT_RUN — gate payoff U11-05 FAIL; chưa renderer/probe hoặc development R2 |
| U11-07 | Người dùng chạy development R2 60 điểm và repeat; verify/analysis/khóa nomination | 06 nghiệm thu | Một cấu hình/một vòng; giữ rule v1 và R2−v1>0, ghi cả kết quả bất lợi | [ ] NOT_RUN — dừng trước development LLM; không nomination R2 |
| U11-08 | Exposure audit, MDE, manifest và release xác nhận R2 riêng | 07 NOMINATED | Đủ 128 điểm/matrix/seed/source/receipt, exposure PASS và kịp trước cuối W11; thiếu điều kiện thì NOT_RUN | [ ] NOT_RUN — không nomination R2 nên không mở release xác nhận |
| U11-09 | Người dùng chạy xác nhận R2; verify/CI/ablation và đóng băng evidence/bảng/hình/checksum | 08 RELEASED | Đúng run/identity, đủ support, primary/family/repeat; bắt đầu cuối W11, hai ngày đầu W12 chỉ hoàn tất/resume | [ ] NOT_RUN — không release, API/xác nhận R2=0 |
| U11-10 | Viết kết quả/thảo luận và phân loại claim cho W9, v1 và R2 | 04–09 đã chốt DONE/NOT_RUN/BLOCKED/INCOMPLETE kèm lý do | Không trộn cohort/revision; khai báo mọi vòng đã xem, không bỏ kết quả bất lợi | [ ] TODO — task tiếp theo; R2 chỉ có bằng chứng offline |
| U11-11 | Bàn giao W12, hướng dẫn verify và giới hạn | 10 | Trạng thái mỗi revision rõ; research/deployment riêng, không tự bật mặc định | [ ] TODO |

Thứ tự bình thường: **04 → 05 → 06 → 07 → 08 → 09 → 10 → 11**.
Gate không đạt hoặc hết thời hạn: chốt kết quả của task đã thực hiện, ghi
NOT_RUN/BLOCKED cho các bước thử nghiệm phụ thuộc chưa thể chạy, rồi tiếp
tục U11-10 → U11-11. NOT_RUN không tính DONE; không cần mở xác nhận để
hoàn tất checklist. Chi tiết phương pháp và điểm dừng ở phần R2 bên dưới.

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
thật. Giữ `tools/` và receipt adapter cùng run khi bàn giao evidence
(U11-11 trong checklist hiện hành).
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

## U11-03 — Kiểm định development và khóa nomination (26/10/2026)

**DONE — NOT_NOMINATED / STOP_NO_CONFIRMATION_RELEASE.** D_U−Original
dương nhưng chỉ **2/4 mã tăng**, không đạt rule ≥3/4. Không đổi ngưỡng,
nominate ablation hoặc mở 2025 để cứu kết quả. Đây là quyết định lựa chọn
trên development đã xem, chưa phải kết luận thống kê xác nhận về hiệu ứng.

### Gate và kết quả primary

[Protocol v1](../week10/unified_bic_protocol_v1.json) giữ nguyên byte/rule trước
outcome; chỉ U_full được xét. G đủ 60/60, mọi nhánh/300 primary/216 repeat
và 96 evaluation complete, finite return/MDD của sáu nhánh trên bốn tài
khoản, nguồn/PIT/paired/receipt/readiness/primary/repeat đều verify PASS.

Lợi nhuận là tài khoản riêng 50 triệu theo engine, net đủ phí/slippage.
R dùng %, các Δ và D dùng **điểm phần trăm**; số hiển thị làm tròn sáu
chữ số, gate dùng precision gốc:

| Mã | N | R Original, % | R U_full, % | ΔR U−Original | ΔR U−A | ΔMDD U−Original |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| FPT | 12 | 1,308248 | 0,933949 | −0,374299 | 0,000000 | 0,000000 |
| MWG | 16 | 11,350163 | 11,757221 | +0,407058 | +0,407058 | +1,312807 |
| VCB | 16 | 2,366803 | 2,439937 | +0,073133 | +1,112315 | +0,984316 |
| VNM | 16 | 1,937829 | 1,937829 | 0,000000 | −1,362504 | 0,000000 |
| Trung bình đều bốn mã | 60 | — | — | **+0,026473** | **+0,039217** | **+0,574281** |

| Điều kiện đã khóa | Quan sát | Gate |
| --- | --- | --- |
| Nguồn/runtime/bốn gate và primary/ba repeat verify | PASS, đúng cohort và code đã khóa | PASS |
| G=60 và finite return/MDD mọi nhánh | 60/60, đủ bốn mã | PASS |
| Prior visible≥30, ≥5/mã | 51/60; FPT/MWG/VCB/VNM=9/14/13/15 | PASS |
| Examples visible≥12, ≥2/mã | 41/60; 5/13/12/11 | PASS |
| D_U−Original>0 | +0,026473 đpt | PASS |
| ΔR>0 ở≥3/4 mã | **2/4: MWG, VCB; VNM bằng 0** | **FAIL** |
| D_U−A≥0 | +0,039217 đpt | PASS |
| Mean ΔMDD≤2; max≤5 đpt | 0,574281; 1,312807 | PASS |

Primary descriptive contrasts Full−stats **+0,935474**, Full−examples
**+0,383759**, Full−Numeric **+2,444624 đpt**; không có CI xác nhận trong
task này. Các contrast không thay điều kiện nomination U_full và chưa
chứng minh riêng đóng góp nhân quả của demonstrations/posterior.

### G/T, task/fallback và các nhóm bất lợi

| Nhóm | N | D_U−Original, đpt |
| --- | ---: | ---: |
| G toàn bộ | 60 | +0,026473 |
| T stats/examples cùng ready | 36 | −0,246090 |
| Chỉ stats ready | 10 | 0,000000 |
| Chỉ examples ready | 5 | null — MWG không có support |
| Prior U_full off | 9 | 0,000000 do reuse |
| Có ≥2 task visible | 34 | +0,425859 |
| Context mode task | 41 | +0,033185 |
| Context mode episode_fallback | 0 | null |
| Context mode off | 19 | 0,000000 |

Hai phân hoạch readiness và context mode riêng; hàng multi-task giao nhau
với task/T, không cộng N giữa các nhóm để tăng mẫu. Mode off của context
chỉ tắt demonstrations, khác prior U_full off khi cả hai block tắt. Gate
coverage multi-task PASS: 34 điểm có ≥2 task, theo mã 3/11/10/10, đạt ≥12
và ≥2/mã. Đây là mức support của thiết kế, không cứu gate kinh tế hoặc
chứng minh cơ chế Bayes bên trong LLM. Nhóm thiếu mã giữ D=null, không
điền lợi nhuận 0 hoặc đổi mẫu số đều bốn tài khoản.

Mọi regime/quý được giữ trong artifact. BULL 11 điểm D=0; BEAR không có
support; CHOPPY 26 điểm **+0,357652**; CONSOLIDATION 23 điểm **−0,379080**.
Q1 có 12 điểm nhưng thiếu FPT nên D=null; Q2/Q3/Q4 đều 16 điểm, lần lượt
**−0,342129 / +0,749196 / −0,092366 đpt**. Không chọn nhóm dương thay G.

### Repeat và duplicate

Các lượt dưới đây dùng **cùng mẫu 12 điểm**, ba điểm/mã và cùng request/
upstream; r=0 là primary trên mẫu này, khác G toàn bộ 60 điểm:

| Lượt | D Full−Original | D Full−A |
| --- | ---: | ---: |
| r=0 trên 12 điểm | −0,249962 | −0,329743 |
| r=1 | −0,249962 | −0,329743 |
| r=2 | 0,000000 | −0,329743 |
| r=3 | −0,249962 | −0,329743 |
| Mean ba lượt bổ sung | **−0,166642** | **−0,329743** |

Full−stats và Full−examples bằng 0 trong cả ba repeat; Full−Numeric bằng
−1,176170 đpt mỗi lượt. Không vote/chọn r=2 hoặc nhập repeat vào primary.
D âm trên mẫu 12 đã có ở r=0; không gán khác biệt với G 60 điểm chỉ cho
nhiễu LLM khi hai mẫu khác nhau.

Original bất đồng **2/36 cặp giữa các repeat** và **1/36 cặp primary-vs-repeat**;
A_reference/U_full/U_stats/U_examples đều 0/36 ở hai phép so đó. Duplicate
độc lập so Original: r=1 **0/12**, r=2 **1/12**, r=3 **0/12**. Các cặp phụ
thuộc được giữ mẫu số, không tính là quan sát độc lập. Prior-off=0 do reuse
không chứng minh provider deterministic; không claim ổn định live từ mẫu nhỏ.

### Producer/consumer, khóa quyết định và bàn giao

[CLI nomination offline](../../../tools/nominate_unified_bayes.py),
[schema riêng](../../../tools/unified_bayes_nomination_v1.schema.json) và
[test bổ sung](../../../tools/test_nominate_unified_bayes.py) nằm trong
`tools/`, giữ nguyên code/test/schema/runtime execution W10 đã đóng băng.
Producer cold tái dựng source/plan/request, diagnostics/PIT, assessment/
readiness và bốn gate, mở journal hiện hữu qua adapter rồi rebuild report
từ ledger/cache. Consumer mặc định làm lại cùng đường nguồn và so toàn bộ
artifact; tự reseal JSON không thay được rule/metric/decision. Chỉ khóa
U_full, không có cờ API, model hoặc threshold.

```powershell
# Producer write-once đã chạy, không sửa plan/run/report hoặc reset ledger.
py -3.13 -X utf8 tools/nominate_unified_bayes.py --prepare
# Consumer mặc định cold verify, không key/mạng/giá 2025.
py -3.13 -X utf8 tools/nominate_unified_bayes.py
```

Artifact local ignored:
`outputs/bayesian_benchmark/unified_bic_v1/development/nomination/selection.json`,
**555.678 byte**, SHA-256 byte
`37439b49ebab656b5af5f5cb4f761e7428ac1e293c8fa529d56c002ad883d912`.
Bind hash byte input/report/receipt/plan, digest checkpoint/HTTP/source và
runtime; code/test/schema phân tích có map hash text LF riêng, ổn định qua
CRLF Git trên Windows. Không sửa `nomination_allowed=false` của report
runtime cũ; quyết định có producer/consumer riêng, `research_candidate=null`,
`nomination_allowed=false`, `confirmation_allowed=false`, risk OFF.

**Nghiệm thu:** 23 ca rule/report/consumer và ba ca guard code cuối PASS
(24 ca khác nhau), gồm biên zero/precision/coverage/MDD, metric hữu hạn,
future cutoff/exit, fixture, source/ledger/code drift, tự reseal và dừng
trước ghi khi guard lỗi. Biên dịch hai file Python mới PASS; không chạy
toàn suite theo AGENTS.md 1.2. Bốn gate U10-09 và 13 ca adapter chỉ được
viện dẫn cho đúng code cũ; không gán các test đó cho code phân tích mới.
Prepare/cold consumer nguồn thật PASS khi chặn mạng/credential/giá 2025;
oracle NumPy độc lập khớp **1.046 kiểm tra** nhãn LONG net, tài khoản/MDD,
mean bốn mã trên G/T/task/regime/quý và mọi repeat. Nguồn, protocol,
Decision/report/cache/ledger cũ giữ nguyên byte: **1.313/1.319 file nguồn/
evidence được bảo vệ không đổi**, sáu metadata owner/recovery của khóa
run/journal/preflight được cập nhật và đã released. Chỉ thêm artifact
nomination riêng; không thêm HTTP, sửa response hoặc thay outcome cũ.

Tại bàn giao v1, checklist cũ đạt **3/10**, các bước xác nhận **NOT_RUN**;
v1 không được mở xác nhận 2025 hoặc đổi ứng viên sau outcome. Từ lần gộp
kế hoạch 26/10/2026, checklist hiện hành là **3/11**, tiếp theo **U11-04**
audit cho R2; viết kết quả và bàn giao mang số **U11-10/U11-11**. Việc đổi
số task không đổi quyết định NOT_NOMINATED hay bằng chứng đã khóa của v1.

## Kế hoạch bổ sung sau U11-03 (26/10/2026)

**Hiệu lực:** yêu cầu mới cho phép lên kế hoạch một revision nghiên cứu
tiếp theo trong thời hạn 12 tuần. Quyết định v1 NOT_NOMINATED và protocol
v1 giữ nguyên; đoạn kết U11-03 phía trên mô tả bàn giao của v1. R2 không
phải chạy lại v1 để đổi kết quả, không tự được release và chưa có mã/runtime.
Không xóa kết quả bất lợi, hạ rule ≥3/4 hoặc chọn ablation làm candidate.
Nhánh xác nhận v1 giữ trạng thái NOT_RUN trong lịch sử. Công việc tiếp
theo gộp vào U11-04–U11-09; tổng kết/bàn giao là U11-10/U11-11. Chỉ dùng
checklist ở mục D; tại lúc lập kế hoạch có **3/11** DONE. Sau audit U11-04,
tiến độ khi đó **4/11**. U11-05 ngày 27/10/2026 đã hoàn tất với gate FAIL,
tiến độ hiện hành **5/11**, dừng U11-06–09; W12 vẫn phải hoàn thành.

### 1. Chẩn đoán đã có và điều chưa thể kết luận

Đọc lại selection, plan và report đã khóa, không gọi LLM hoặc mở payoff
2025. Không chỉ thiếu một mã tăng: gain trung bình +0,026473 đpt quá nhỏ
để xem là lợi ích vững chắc. Mục tiêu mới phải sửa cơ chế tạo quyết định,
không tìm một thay đổi nhỏ đủ làm mã thứ ba dương.

| Quan sát từ primary v1 | Ý nghĩa cho bước tiếp theo |
| --- | --- |
| U_full khác Original 5/60 action; cả năm CASH→LONG, không LONG→CASH | 55 action không đổi; cần kiểm chất lượng thay đổi quyết định và khả năng tránh lỗ, không tối đa hóa số lần prior visible |
| Năm lệnh thêm có 2 lãi, 3 lỗ net | Gain bị triệt tiêu; chưa chứng minh do posterior, ví dụ hay nhiễu request |
| U_full khác A 4/60; khác stats 5/60; khác examples 2/60 | Ablation kinh tế dựa trên rất ít thay đổi; không lấy contrast dương làm bằng chứng cơ chế đủ mạnh |
| Prior 51/60, stats 46/60, examples 41/60, ≥2 task 34/60 | Coverage đã đạt; tăng K hoặc giảm ngưỡng không phải ưu tiên có căn cứ |
| Trên 46 điểm stats-ready: mean p=0,364384; tỷ lệ thắng net=0,369565; Brier=0,226423; log loss=0,648615 | Mean gần nhau không chứng minh calibration có điều kiện hoặc lợi ích kinh tế; chưa có cơ sở kết luận toàn bộ Bayes sai |
| 42/46 posterior mean≤0,5; Numeric_only chỉ LONG 4/60 | Ép theo p>0,5 có thể bỏ cơ hội; xác suất thắng không chứa độ lớn lãi/lỗ |
| U_full có trích ID ở 1/51 điểm prior-visible; bốn trong năm action đổi không trích ID | Cần đọc nội dung thực; thiếu citation không chứng minh LLM bỏ qua prior, có citation cũng không chứng minh suy luận Bayes |
| Repeat U ổn định trên 12 điểm, nhưng kết quả mẫu này đã âm ở primary | Không chọn repeat tốt hoặc tăng vote để cứu gain; chưa phải bằng chứng lỗi chủ yếu do ngẫu nhiên provider |

Năm thay đổi dưới đây chỉ mô tả payoff từng cycle, **không cộng thành D
tài khoản**; D phải dựng lại tài khoản bằng engine với thứ tự/lot/compounding:

| Điểm | LONG net, % | Ghi chú |
| --- | ---: | --- |
| VCB-2023-02-08 | −1,015155 | p=0,396; hai exemplar net âm; justification chủ yếu nói tín hiệu kỹ thuật |
| MWG-2023-04-28 | −1,349148 | p=0,523 với CrI rộng; prior không đảm bảo thắng |
| MWG-2023-08-29 | +1,738163 | p=0,325 và ba exemplar âm nhưng lệnh có lãi; cấm suy ra hard veto p<0,5 từ vài ca lỗ |
| VCB-2023-08-29 | +1,097742 | Chỉ examples ready; không được coi raw posterior bị ẩn là evidence LLM đã thấy |
| FPT-2023-11-23 | −0,369465 | Giá tăng nhưng net sau phí âm; cần tách đúng hướng giá và lợi ích giao dịch |

Đây là phần đọc sơ bộ khi lập kế hoạch, được hoàn tất bằng
[audit U11-04](#u11-04--audit-quyết-định-development-v1-26102026) bên dưới.
Đây là phân tích hậu nghiệm trên development đã xem. Các giả thuyết còn
phải kiểm: prior thiếu thông tin payoff; cách diễn đạt làm LLM chú trọng
tín hiệu tăng hơn bất định; lệch giữa population stats và examples; tuổi
memory hoặc conditional signal ít khả năng dự báo. Không kết luận nguyên
nhân chỉ từ năm ca, và không tạo rule riêng cho FPT/VNM/CONSOLIDATION.

### 2. Revision R2 được đề xuất: Bayes về payoff và ICL có đối chiếu

**Giữ:** memory/scaler/regime, partition C/B1/B2, posterior thắng λ=8,
selector label-blind, block90, tối đa ba task/exemplar, engine, upstream
chung, retry/checkpoint và Original mặc định. Không fine-tune, thay model,
thêm agent, ensemble, risk overlay hay mở rộng ngân sách prompt. Nguyên
nhân coverage đã được xử lý ở v1; mở lại các phần này sẽ làm mất khả năng
quy trách nhiệm trong thời gian còn lại.

**Thay đổi A — thêm độ lớn payoff có bất định, không hard veto theo p.**
Về toán học, E(r_net)=p·E(r_net|r_net>0)+(1−p)·E(r_net|r_net≤0).
Vì vậy p<0,5 vẫn có thể có mean dương. Tất cả r_net lấy từ cùng hàm
kinh tế hiện hành; không trừ phí hai lần, không dùng target giá/R:R do LLM
viết làm nhãn hoặc thay giá Open(t+1)/Close(t+3).

Chỉ thử **một mô hình payoff offline**: Normal–Inverse-Gamma cho r_net
trong C, với prior empirical Bayes từ B=B1∪B2 cùng mã, rời C và đúng PIT.
Mô hình nhẹ có posterior/predictive dạng Student-t; công thức theo
[Murphy, mục Normal–Inverse-Gamma](https://www.cs.ubc.ca/~murphyk/Papers/bayesGauss.pdf).
Giả định Gaussian cho cycle return là xấp xỉ cần kiểm; Student-t predictive
do bất định tham số không tự giải quyết phụ thuộc thời gian hoặc regime shift.

Đặc tả khởi điểm cố định, đơn vị return dạng tỷ lệ: κ0=4, α0=2,
m0=mean(r_B), β0=max(var_sample(r_B),10^−6); cần nB≥20, nC≥5 và gate
stats v1 đạt. Với n=nC, x̄=mean(r_C), S=Σ(r_C−x̄)^2:
κn=κ0+n; mn=(κ0m0+n·x̄)/κn; αn=α0+n/2;
βn=β0+S/2+κ0n(x̄−m0)^2/(2κn). μ có Student-t bậc 2αn, location mn,
scale sqrt(βn/(αnκn)); predictive r thêm hệ số (κn+1) dưới căn.
Không dùng scale predictive làm CrI của mean. Var floor chỉ giữ số học,
không là threshold giao dịch; không quét κ, α, floor sau khi xem return.

Gate offline trên 647 query train 2021–2022 đã purge của U10-04, theo
fold/PIT và common support: MAE không xấu hơn cả dự báo zero lẫn m0,
tốt hơn ít nhất một; không mã nào MAE xấu hơn m0 quá 0,1 đpt; mean NLL
predictive không xấu hơn prior predictive; coverage khoảng predictive
90% ít nhất 85%, báo thêm độ rộng và theo mã/fold. Đây là ngưỡng tiếp tục
nghiên cứu được đề xuất trước phép đo, không là kiểm định xác nhận hay
chứng nhận model đúng. Không đủ support thì gate inconclusive, không PASS.
Không cắt outlier hoặc thay fold vì lỗi lớn; stress outlier/dependence và
case n nhỏ phải báo. Trượt gate thì **dừng R2 trước API**, không thử thêm
family/model để tìm một phương án thắng.

Trong prefix, gọi mn là **mean net lịch sử có shrinkage**, kèm CrI95%
của mean và support; chưa gọi là expected return query đã hiệu chuẩn.
Không nhân posterior p và payoff thành một phân phối giả khi chưa có
mô hình chung. Không dùng mean/CrI làm override action; Numeric_payoff
offline dùng mn>0 khi payoff ready, còn lại CASH, chỉ là đối chứng số học.

**Thay đổi B — đưa evidence vào một cấu trúc dễ đối chiếu.** Giữ nguyên
base prompt/instruction/schema v1 cho mọi nhánh mới; chỉ thay prefix R2.
Thay ký hiệu khó đọc bằng nhãn ngắn rõ nghĩa: tỷ lệ thắng net/support,
mean net/CrI nếu ready, task và x→y đã chọn, rồi yêu cầu đối chiếu bằng
chứng thuận/nghịch trong evidence_for/evidence_against/justification sẵn có.
Nói rõ TP/SL hoặc target giá không là cơ chế thoát lệnh của backtest.
LLM vẫn quyết định LONG/CASH; không ép đồng ý prior, không ép thay action
để đủ 3/4 mã. Missing payoff không là zero; tắt block với reason.

BRPP≤600, toàn prompt<6500, giữ đủ ba task ở case biên. Không bỏ ví dụ
thua, không gộp các nhóm khác nhau hoặc thêm outcome query để rút ngắn.
ID/support/đơn vị phải giải mã được; sidecar lưu đầy đủ provenance. Không
thay bank hoặc retrieval cùng lúc với renderer/payoff để tránh lẫn nguyên nhân.

Kiểm 12 tình huống tổng hợp đã khóa (dấu/đơn vị, p thấp nhưng payoff dương,
p cao nhưng payoff âm, CrI qua 0, missing, mâu thuẫn task/current signal),
không là thí nghiệm lợi nhuận. Parser/oracle phải đúng; probe LLM do người
dùng chạy một lượt sau freeze chỉ kiểm không bịa số/ID hoặc cơ chế thoát.
Nếu lỗi số liệu/semantics, sửa lỗi và công bố, không chọn response tốt;
sửa template sau development thật là revision mới ngoài vòng này.

Tài liệu [Zhao et al.](https://proceedings.mlr.press/v139/zhao21c.html) cho
thấy few-shot nhạy với prompt/ví dụ/thứ tự trong các tác vụ của họ; đó là
lý do kiểm độ nhạy ở đây, không phải bằng chứng rằng calibration của họ
sẽ tăng lợi nhuận hệ thống này. Không áp content-free calibration vào
confidence dạng chữ rồi gọi là xác suất. Theo
[paper nền](https://proceedings.mlr.press/v306/zhu26aj.html), transformer
được huấn luyện trên prior/target tasks; R2 vẫn là ứng dụng Bayesian
evidence-conditioned ICL trên hosted LLM, không tái tạo việc huấn luyện đó.

### 3. Một vòng kiểm chứng mới, không đổi kết quả v1

Namespace dự kiến unified_bic_r2, manifest/schema/verifier riêng; không
sửa cờ selection.json, receipt hoặc code được v1 khóa. Runtime mới tái
dùng adapter ổn định khi hash/hợp đồng tương thích. Đường nguồn/payoff/
prompt/reuse thay đổi phải có test trọng tâm và leakage liên quan; viện
dẫn gate cũ đúng phạm vi, không tự chạy lại toàn suite theo AGENTS.md 1.2.

Ma trận đăng ký trước run, chỉ **R2_full** được xét:

| Nhánh | Đối chứng nhằm trả lời |
| --- | --- |
| Original | Không prior, cùng base request v1 |
| A_reference | A trên cùng memory/protocol mới |
| U_v1_reference | Exact template v1, chạy trong cùng đợt để đo cải thiện so v1 |
| R2_full | Prefix dễ đối chiếu + posterior thắng + payoff đủ gate + task examples |
| R2_no_payoff | Prefix/selection y như R2, bỏ đúng block payoff; kiểm lợi ích độ lớn lãi/lỗ |
| R2_no_examples | Giữ stats/payoff, bỏ demonstrations và task summary; kiểm lợi ích ICL |
| Numeric_payoff | Offline, không LLM, không candidate |

Development vẫn đủ 60 điểm 2023, sáu nhánh LLM=360 slot primary. Khóa
12 điểm repeat và ba lượt bổ sung trước action: giữ danh sách v1 để không
chọn lại theo outcome; sáu nhánh cộng Original_duplicate=252 slot repeat.
Original đầu, năm nhánh còn lại xoay theo index; repeat xoay sáu nhánh kể
cả duplicate. Upstream một lần/point, không gọi lại vision; chỉ reuse cache
upstream sau kiểm identity. Response Decision v1 cũ chỉ tham khảo lịch sử,
không ghép vào nhánh đối chứng mới vì thời điểm/provider có thể đổi.
Shared-off chỉ reuse khi canonical request đúng point/repeat trùng hoàn toàn.

Giữ nomination D>0, ≥3/4 mã tăng, D_R2−A≥0, coverage/multi-task và guard
MDD v1. Bổ sung D_R2−U_v1>0 để không gọi revision mới là cải thiện khi
chỉ bằng v1; đo/payoff visible≥30/60 và≥5/mã trước API để không đánh giá
một block gần như luôn tắt. Không bổ sung rule theo tên mã hoặc loại riêng
năm point đã biết. Phải báo số action đổi, cả CASH→LONG và LONG→CASH,
payoff của các thay đổi, leave-one-change-out/leave-one-symbol-out và repeat;
không chọn phân tích nhạy cảm thuận lợi làm nomination mới.

Đây vẫn là **development đã dùng thích nghi nhiều lần**, không phải
xác nhận độc lập dù qua gate. Chỉ sau nomination và release R2 riêng mới
được dùng 2025: tái audit exposure của mọi lượt đã chạy, không chỉ v1;
giá/coverage PASS không đồng nghĩa outcome chưa từng dùng để tune.
Không rõ exposure thì báo exploratory và kết thúc trong W12, không hứa
forward đủ mẫu trong vài ngày. Không dùng phần 2024 còn lại làm holdout mới.

Nếu đủ điều kiện, xác nhận giữ 128 điểm/32 mỗi mã và rule lịch v1, cùng
snapshot exit≤31/12/2024, không append outcome 2025. Khóa đủ sáu nhánh
LLM, primary và repeats trước outcome. Primary R2−Original, CI95% theo
bootstrap đã định (10.000 draw, L=4, cùng cutoff/mã); secondary family có
**năm** contrast R2−A/v1/no_payoff/no_examples/Numeric, Bonferroni CI99%
từng contrast. Không giữ CI98,75% của family bốn contrast cũ. MDE/coverage
trước release; không giảm N, đổi seed hoặc cắt nhánh sau khi thấy kết quả.

Primary xác nhận dương mới hỗ trợ lợi ích kinh tế; contrast với A/v1 mới
hỗ trợ ưu thế so phương pháp tương ứng. Full−no_examples dương mới hỗ trợ
đóng góp thêm của demonstrations; payoff hoặc Numeric thắng riêng không
được gọi là ICL thắng. Không có ý nghĩa thống kê thì ghi inconclusive;
không tăng số call/rerun hoặc nới tiêu chuẩn để ép kết luận.

### 4. Checklist và thời hạn cứng trong W11–W12

Không khởi động lại một tuần đã dùng. Ưu tiên dưới đây phải vừa phần thời
gian thực tế còn lại; nếu thiếu thời gian thì giảm phạm vi nghiên cứu mới,
không giảm chuẩn nghiệm thu hay kéo dài sang W13.

Thực hiện theo [checklist U11-04–U11-11](#d-checklist-thực-hiện-tuần-tự-hiện-hành),
không duy trì bảng task riêng ở phần này. U11-04–06 tối đa hai ngày làm
việc; U11-07 một vòng development; U11-08/09 xác nhận có điều kiện;
U11-10 tổng hợp kết quả rồi U11-11 bàn giao. Hết ngày làm việc thứ hai W12
khóa dữ liệu/bản thảo: run thiếu mẫu là INCOMPLETE, không lấy partial gain
làm kết quả chính. Phần còn lại W12 chỉ tái lập, hoàn thiện hình/bảng,
slide và bảo vệ. Không mở thêm candidate hoặc tuning sau mốc này.

**Phương án nộp luôn có:** W9 A là bằng chứng xác nhận tích cực đã có
(với đúng giới hạn cohort/secondary); v1 là kết quả âm về gate lựa chọn;
R2 nếu chạy là nghiên cứu tiếp nối. v1 vẫn được trình bày đầy đủ trong
kết quả/thảo luận, chỉ không dùng để tuyên bố ưu thế xác nhận. Nếu R2 chưa
đủ chứng cứ, đóng góp khóa luận gồm ứng dụng Bayes/ICL có đối chứng, hệ
thống PIT/tái lập và phân tích giới hạn, không sửa nhãn để gọi là thành công.

### 5. Kiểm tra cho lần cập nhật kế hoạch này

Chỉ sửa tài liệu, đọc/đối chiếu artifact hiện hữu, không thay code, schema,
runtime, dữ liệu hoặc gọi API. Theo AGENTS.md 1.2 không chạy compileall,
unit/E2E/leakage suite và không ghi là đã chạy lại các gate cũ. Hash byte
nguồn phân tích để đối chiếu sau sửa tài liệu:

| Nguồn dưới outputs/bayesian_benchmark/unified_bic_v1/development | SHA-256 |
| --- | --- |
| nomination/selection.json | 37439b49ebab656b5af5f5cb4f761e7428ac1e293c8fa529d56c002ad883d912 |
| run/report.json | 5f691d4813b2c19965170f774486073840c3776248d2e452b837a725e511cd18 |
| plan.json | 4bb127868e40c6cf04fb7b9a51425f520a29e95adaaa994c1ae942a36b7ddc35 |

Sổ usage dùng chung giữ hash e73a87e2a45d73e76f63cdd58225c2de06b0df4e03ed09b91ad0f6f71c5c8796.
Các số liệu mới phía trên được tính trực tiếp từ 60 row repeat_id=0 và
posterior trong plan; chưa chạy lại cold consumer có thể cập nhật lock.
Đối chiếu byte hash, số liệu, liên kết/anchor, UTF-8 và diff là kiểm tra
áp dụng cho lần lập kế hoạch, **đều PASS**; diff chỉ gồm ba tài liệu
plan.md, README W11 và README W12. Đây là QA của lần lập kế hoạch R2,
không coi đó là nghiệm thu các task triển khai.

Lần gộp checklist tiếp theo cùng ngày chỉ đổi thứ tự/mã task, phụ thuộc,
tiến độ và liên kết điều hành ở plan.md, README W11/W12 và hướng dẫn vận
hành v1. Kiểm tra diff/liên kết, chuỗi 01–11 duy nhất, ba DONE/tám TODO
và hash nguồn nêu trên đều PASS; không chạy suite vì không đổi
code/runtime/dữ liệu. Task tiếp theo là U11-04, chưa thực hiện task này.

## U11-04 — Audit quyết định development v1 (26/10/2026)

**DONE.** Đã đọc đủ `evidence_for`, `evidence_against`, `justification` và
trace của **60 phản hồi primary U_full**, đối chiếu action của Original,
A, stats, examples; đọc nguyên canonical prompt và hai phản hồi Original/
U_full của **cả năm điểm đổi action**. Đây là audit hậu nghiệm để xác định
điều cần kiểm ở U11-05, không phải một phép thử R2 hoặc nomination mới.
v1 giữ **NOT_NOMINATED**, nhánh xác nhận v1 NOT_RUN; R2 chưa có gate payoff,
development, nomination hoặc release xác nhận.

### Phạm vi, phương pháp và nguồn audit

Nguồn chính là `development/plan.json`, `run/report.json`,
`nomination/selection.json` và `inputs/memory_index_v1.json` dưới
`outputs/bayesian_benchmark/unified_bic_v1/`. Dùng đúng 60 row
`repeat_id=0`, không nhập 36 block repeat vào primary. Đối chiếu theo
`requests[point_id].packets[branch]`, `u_evidence`, `report.points` và
`memory.records[episode_id]`; giữ nguyên prompt, output, alias và ID nguồn.
Hash plan/report/selection/ledger ở bảng cuối phần kế hoạch vẫn là binding
gốc, không cập nhật chúng để khớp kết quả audit.

Sidecar phân tích cục bộ mới
`development/audit/decision_audit.json` (**835.379 byte**,
SHA-256 `ef3c98c21b3ff606493311c6a23f6f6397975495f28e2d4784a26997bb2a3046`)
lưu đủ 60 nhận xét, năm bộ output/prefix/trace mỗi điểm, hash body/prompt,
upstream provenance, gate/reason/exclusion counts, payoff/tuổi C/B1/B2 và
ID/tuổi/nhãn từng exemplar. Đây là **đầu ra audit ignored**, không phải
input R2 hoặc receipt release; cần giữ cùng bộ outputs khi bàn giao.
README này giữ kết luận và bảng đọc được, không tạo thêm biên bản task.

Payoff nhóm được tính từ `outcome.net_return_pct` có sẵn của đúng các ID
C/B1/B2; đối soát n, s, partition rời, cùng mã và `exit_date < query`.
Đối soát 60 payoff query với `compute_round_trip_net_return(entry_open,
exit_close)` và 300 cặp action/evaluation: SHORT=CASH/return=0,
LONG=BUY_SELL/net theo hợp đồng. Không cộng cycle return thành chênh lệch
tài khoản. D vẫn là **+0,026473 đpt** đã khóa ở U11-03, với lot, thứ tự và
compounding của engine; không tính lại D từ bảng năm cycle.

Chỉ đánh dấu thông tin là **visible** khi có trong canonical prefix hoặc
base prompt thực gửi. Posterior tắt và mean payoff tính thêm chỉ nằm trong
sidecar audit, không được coi là dữ liệu LLM đã thấy. Tuổi dưới đây là ngày
lịch từ cutoff episode tới cutoff query, không phải số phiên. Các nhận xét
giải thích là đọc nội dung phản hồi, không quan sát suy luận nội tại.

### Quan sát đủ 60 điểm

U_full có **21 LONG/39 CASH**, Original **16 LONG/44 CASH**. Cả **5/60**
khác biệt đều CASH→LONG: **2 cycle lãi, 3 cycle lỗ**; không có LONG→CASH.
So với A/stats/examples lần lượt khác **4/5/2** action. Các số này đo đổi
action trên cohort đã xem, không là hiệu quả nhân quả của từng block.

Prior visible **51/60**; stats **46/60**, examples **41/60**; 9 điểm U_full
off dùng lại đúng response Original/body cùng point/repeat. Có **90 lượt
exemplar** trên 41 điểm, tuổi **24–726**, trung bình **393,177778 ngày**.
Đây là lượt xuất hiện, có lặp ID giữa query. Trần 730 ngày chỉ áp selector
examples; thống kê C/B1/B2 vẫn dùng toàn population PIT, có lịch sử cũ hơn.
Không gọi sự khác biệt population/tuổi này là lỗi leakage hoặc sửa tuổi/K
theo outcome. **23/90** exemplar có cặp Trend/Pattern khác query: selector
task của v1 không buộc mọi representative thuộc C, nên không lấy mean/tỷ
lệ task hay vài exemplar thay cho thống kê C. Trace chọn giữ cả `PRIOR_TOO_OLD`, feature unavailable,
similarity, conflict và task-support/rank-limit; không bỏ các điểm tắt.

U_full trích ID ở **1/51** điểm visible (VCB-2023-08-29), không có unknown
ID. Đọc nội dung thấy **6/51** phản hồi nhắc rõ prior/lịch sử:
VCB-2023-03-06, MWG-2023-06-30, VNM-2023-06-30, FPT-2023-08-29,
VCB-2023-08-29, MWG-2023-10-30. Ví dụ MWG-2023-06-30 nhắc đúng
mean=0,539, FPT-2023-08-29 nhắc mean=0,465; action cả hai vẫn giống
Original. VNM-2023-06-30 nói tới hai ví dụ âm nhưng không trích ID. Vì vậy
thiếu ID không đồng nghĩa bỏ prior; lời nhắc prior cũng không chứng minh
đó là nguyên nhân action. Trong năm action đổi, chỉ VCB-2023-08-29 nhắc
prior rõ ràng và có ID.

Theo định nghĩa mô tả cố định, **21/60** input có Trend và alpha tổng hợp
trái dấu (cả hai phải BULLISH/BEARISH); **10/60** có Trend trái dấu
MACD−Signal mới nhất. Đây là xung đột bằng chứng đầu vào, không tự là lỗi
Decision. `indicator_consensus` của nhiều chỉ báo không đồng nhất với dấu
của một MACD. Base prompt có thứ tự ưu tiên và cảnh báo đối chiếu; các
phản hồi thường chọn Trend/Pattern/MACD, nhưng không đủ bằng chứng để
kết luận thay renderer chắc chắn sửa lợi nhuận.

<details>
<summary>Bảng audit đủ 60 điểm primary, giữ cả điểm bất lợi và prior tắt</summary>

Thứ tự action: **Original/A_reference/U_full/U_stats/U_examples**;
L=LONG, C=CASH (output gốc vẫn ghi SHORT). S=stats visible, E=examples
visible, OFF=U_full không prior. Cột net là **LONG giả định của từng cycle,
%**, kể cả khi action thực là CASH; không phải lợi nhuận đã thực hiện của
mọi nhánh. Nhận xét tóm tắt lý do U_full phát biểu, không khẳng định lý do
đó đúng hoặc đủ gây ra action.

| Điểm | Action O/A/U/S/E | Visible | LONG net % | Nhận xét reason/trace sau đối chiếu |
| --- | --- | --- | ---: | --- |
| MWG-2023-01-06 | C/C/C/C/C | SE | -2.078356 | Đi ngang, MACD yếu; giữ CASH. |
| VCB-2023-01-06 | L/L/L/L/L | OFF | -1.507717 | Trend/MACD tăng; prior tắt, dùng lại Original. |
| VNM-2023-01-06 | L/C/L/L/L | S | -1.318974 | Trend/MACD tăng lấn alpha giảm; không nhắc prior. |
| MWG-2023-02-08 | C/C/C/C/C | SE | -4.946986 | Xu hướng giảm lấn MACD trên Signal. |
| VCB-2023-02-08 | C/L/L/L/L | SE | -1.015155 | Đổi sang LONG: Trend/MACD tăng lấn alpha giảm; không đối chiếu prior âm. |
| VNM-2023-02-08 | C/C/C/C/C | SE | -1.352586 | Xu hướng/MACD giảm lấn alpha tăng. |
| MWG-2023-03-06 | C/C/C/C/C | SE | -0.697557 | Xu hướng và MACD giảm; giữ CASH. |
| VCB-2023-03-06 | C/C/C/C/C | SE | +0.930352 | Nhắc 1/5 của T1; không phải support C=13. |
| VNM-2023-03-06 | C/C/C/C/C | SE | +0.087443 | Lo phí, đi ngang; diễn giải MACD giảm dù histogram dương. |
| MWG-2023-03-30 | C/C/C/C/C | OFF | +2.522367 | Xu hướng yếu; prior tắt, dùng lại Original. |
| VCB-2023-03-30 | L/L/L/L/L | OFF | -1.553612 | Trend/V-shape tăng; prior tắt, dùng lại Original. |
| VNM-2023-03-30 | C/C/C/C/C | OFF | -1.756783 | Đi ngang/MACD yếu; prior tắt, dùng lại Original. |
| MWG-2023-04-04 | L/L/L/L/L | OFF | -2.693586 | Đáy đôi/MACD tăng; prior tắt, dùng lại Original. |
| VCB-2023-04-04 | C/C/C/C/C | OFF | -3.172049 | Alpha giảm lấn MACD tăng; prior tắt, dùng lại Original. |
| VNM-2023-04-04 | C/C/C/C/C | S | -0.028403 | Trend/MACD giảm; gọi alpha giảm trái tổng hợp 5/5 tăng. |
| FPT-2023-04-12 | C/C/C/C/C | OFF | -1.563207 | Đi ngang lấn MACD tăng; prior tắt, dùng lại Original. |
| MWG-2023-04-28 | C/C/L/L/L | SE | -1.349148 | Đổi sang LONG: breakout/đáy đôi lấn MACD âm; không bàn alpha 4 giảm. |
| VCB-2023-04-28 | L/L/L/L/L | SE | +2.612525 | Trend/V-shape/MACD tăng; không đối chiếu p thấp. |
| VNM-2023-04-28 | C/C/C/C/C | SE | -0.130114 | Xu hướng/MACD giảm; cách viết short position cần hiểu CASH. |
| FPT-2023-05-11 | L/L/L/L/L | OFF | +2.057366 | Trend/box/MACD tăng; prior tắt, dùng lại Original. |
| FPT-2023-06-01 | L/L/L/L/L | S | +1.443095 | Trend/MACD tăng; stats-only, không đối chiếu p thấp. |
| MWG-2023-06-01 | L/L/L/L/L | SE | +5.217798 | Trend/V-shape/MACD tăng; đề xuất stop-loss không phải cơ chế engine. |
| VCB-2023-06-01 | C/C/C/C/C | E | +4.695867 | Đi ngang/alpha giảm; lo phí dù MACD tăng. |
| VNM-2023-06-01 | C/C/C/C/C | SE | -0.397549 | Trend/MACD giảm; không nhắc prior. |
| FPT-2023-06-27 | L/L/L/L/L | SE | -2.288214 | Trend tăng lấn MACD/alpha giảm; dự báo net>0,7% chưa là outcome. |
| MWG-2023-06-30 | L/L/L/L/L | SE | -0.926101 | Nhắc mean=0,539 làm bằng chứng LONG; action vẫn như Original. |
| VCB-2023-06-30 | C/C/C/C/C | SE | +1.288492 | Đi ngang/MACD yếu; giữ CASH. |
| VNM-2023-06-30 | C/C/C/L/C | SE | -2.513213 | Nhắc hai ví dụ net âm; action vẫn như Original. |
| FPT-2023-07-05 | C/C/C/C/C | OFF | -0.033770 | Trend/MACD giảm; diễn giải thu lãi từ bán khống sai hợp đồng CASH. |
| MWG-2023-07-05 | L/L/L/L/L | SE | +9.255568 | Breakout/alpha tăng lấn MACD âm; không nhắc prior. |
| VCB-2023-07-05 | C/C/C/C/C | SE | -0.113997 | Đi ngang/alpha giảm; giữ CASH. |
| VNM-2023-07-05 | C/C/C/C/C | E | +2.427842 | Trend/alpha giảm lấn MACD tăng; giữ CASH. |
| FPT-2023-07-31 | L/L/L/L/L | S | -2.901700 | Trend/MACD tăng; stats-only, không nhắc prior. |
| MWG-2023-07-31 | C/C/C/C/C | S | -3.267306 | Đi ngang/alpha giảm lấn MACD tăng. |
| VCB-2023-08-03 | C/C/C/C/C | S | -0.697557 | Trend/MACD giảm; stats-only, không nhắc prior. |
| VNM-2023-08-03 | C/C/C/C/C | S | +2.041821 | Trend/alpha giảm; MACD death cross. |
| FPT-2023-08-29 | L/L/L/L/L | S | +3.138160 | LONG với mean=0,465; alpha chỉ 2/5 giảm, không ép theo p. |
| MWG-2023-08-29 | C/C/L/C/C | SE | +1.738163 | Đổi sang LONG: breakout lấn histogram âm; không đối chiếu ba ví dụ lỗ. |
| VCB-2023-08-29 | C/C/L/C/L | E | +1.097742 | Đổi sang LONG: nhắc T1/T2 nhưng số là E1/E2; stats bị ẩn. |
| VNM-2023-08-29 | L/L/L/L/L | S | +3.300334 | Trend/đáy đôi/MACD tăng lấn alpha giảm. |
| FPT-2023-09-29 | C/C/C/C/C | SE | -1.654433 | Đi ngang/MACD yếu; giữ CASH. |
| MWG-2023-09-29 | C/C/C/C/C | SE | -7.116346 | Trend/đỉnh đôi giảm; diễn giải thu lãi từ bán khống sai hợp đồng CASH. |
| VCB-2023-09-29 | C/C/C/C/C | SE | -1.609634 | Trend/MACD giảm; từ shorting mơ hồ, engine vẫn CASH. |
| VNM-2023-09-29 | C/C/C/C/C | SE | -0.429895 | Trend/MACD giảm; giữ CASH. |
| FPT-2023-10-04 | C/C/C/L/C | SE | +2.298638 | Đi ngang/alpha giảm lấn pattern breakout. |
| MWG-2023-10-04 | C/C/C/C/C | SE | -4.578113 | Trend/MACD/alpha giảm; giữ CASH. |
| VCB-2023-10-04 | C/C/C/C/C | SE | -2.314108 | Trend/MACD/alpha giảm; giữ CASH. |
| VNM-2023-10-04 | C/C/C/C/C | SE | -1.233602 | Trend/MACD/alpha giảm; giữ CASH. |
| FPT-2023-10-30 | C/C/C/C/C | S | +3.853319 | Trend/MACD giảm; stats-only, không nhắc prior. |
| MWG-2023-10-30 | C/C/C/C/C | SE | -9.054693 | Nhắc lịch sử dễ lỗ; không viện dẫn ID hoặc số cụ thể. |
| VCB-2023-10-30 | L/L/L/L/L | E | +2.886117 | Trend/MACD tăng; examples-only, không nhắc prior. |
| VNM-2023-10-30 | C/C/C/C/C | SE | +3.689885 | Trend/MACD giảm; short (cash) đúng hợp đồng. |
| FPT-2023-11-23 | C/L/L/L/C | SE | -0.369465 | Đổi sang LONG: Trend/MACD tăng lấn alpha/pattern warning; net âm sau phí. |
| MWG-2023-11-23 | C/C/C/L/C | SE | -0.435545 | Trend giảm lấn MACD tăng; shorting không phải lợi nhuận CASH. |
| VCB-2023-11-23 | C/C/C/C/C | SE | -0.349127 | Trend/MACD/alpha xung đột; giữ CASH. |
| VNM-2023-11-23 | C/C/C/C/C | SE | -0.842313 | Trend/Pattern giảm; phát biểu shorting không có lợi chưa đúng ngữ nghĩa CASH. |
| VNM-2023-12-19 | C/C/C/C/C | SE | +0.191719 | Trend/MACD giảm; tránh short trade là diễn giải mơ hồ. |
| FPT-2023-12-22 | C/C/C/C/C | E | +1.395224 | Đi ngang/MACD yếu; examples-only, không nhắc prior. |
| MWG-2023-12-22 | L/L/L/L/L | SE | +0.474845 | Trend/MACD tăng lấn alpha giảm; không nhắc prior. |
| VCB-2023-12-22 | C/C/C/C/C | SE | +1.511892 | Trend/MACD/alpha giảm; SHORT được mô tả giữ vốn. |

</details>

### Năm thay đổi: payoff, tuổi, xung đột và giới hạn giải thích

Mean C dưới đây là **mean net thô hậu nghiệm**, không phải posterior mean
payoff R2, không nằm trong prefix v1. p/CrI là xác suất thắng lịch sử dạng
plug-in, không P(query). Với VCB-2023-08-29, stats không đủ support nên p
raw không hiển thị; không gán hành vi điểm đó cho posterior bị ẩn.

| Điểm | Stats visible: p [CrI95%] | C: thắng/n; mean net % audit | Exemplar net % (tuổi ngày, theo E1/E2/E3) | LONG net % query |
| --- | --- | --- | --- | ---: |
| VCB-2023-02-08 | 0,396 [0,221;0,586] | 8/18; −0,560968 | −4,049014 (64); −2,648141 (582) | −1,015155 |
| MWG-2023-04-28 | 0,523 [0,299;0,743] | 5/10; −0,219692 | +2,398733 (402) | −1,349148 |
| MWG-2023-08-29 | 0,325 [0,179;0,491] | 8/25; −0,333977 | −1,471342 (449); −1,426115 (567); −2,888052 (622) | +1,738163 |
| VCB-2023-08-29 | Tắt: LOW_CONDITIONAL_SUPPORT | 0/3; −1,669796 | +0,241791 (399); −1,808774 (714) | +1,097742 |
| FPT-2023-11-23 | 0,485 [0,323;0,648] | 14/27; −0,086374 | +2,049942 (352); +0,377145 (637) | −0,369465 |

- **VCB-2023-02-08:** Original cho alpha giảm lấn momentum; U_full đảo
  trọng số phát biểu, ưu tiên Trend/MACD tăng. Prompt có alpha 3/5 giảm,
  cả hai exemplar lỗ và hai task thắng 1/5, 3/13. U_full không viện dẫn hay
  đối chiếu các số lịch sử. Giá thực thi 93,8→93,5 cho cycle âm. A/stats/
  examples cũng LONG, nên không quy riêng thay đổi này cho demonstrations.
- **MWG-2023-04-28:** Original lo MACD âm/alpha giảm và phí; U_full nhấn
  breakout/đáy đôi và target 42. Prompt có cảnh báo Trend thị giác mâu thuẫn
  SMA/độ dốc, alpha 4/5 giảm; MACD −0,2214 dưới Signal −0,0989. Chỉ một
  exemplar dương, task thắng 7/11, trong khi C mean âm dù p>0,5. Exemplar
  và C không phải cùng summary population. Không có lời giải đối chiếu
  prior; cycle thực 38,1→37,85 âm. p>0,5 không bảo đảm lợi nhuận dương.
- **MWG-2023-08-29:** Original chọn CASH do MACD âm; U_full chọn LONG dựa
  breakout/target 56, gọi MACD dưới Signal là bullish momentum rồi vẫn
  ghi histogram âm ở evidence_against. Nguồn MACD 0,4634<0,8611 và
  histogram −0,3977 đang bớt âm, nên phải phân biệt mức và xu hướng cải
  thiện; không kết luận một từ “bullish” tự chứng minh lỗi tính chỉ báo.
  Alpha 4/5 giảm, cả ba exemplar âm, CrI p có cận trên 0,491. U_full không
  đối chiếu prior; chỉ full LONG, A/stats/examples CASH. Cycle thực lại
  lãi 53→54,3. Ca này bác cách suy ra hard veto p<0,5 từ riêng ca lỗ.
- **VCB-2023-08-29:** Stats tắt vì nC=3; chỉ hai ví dụ/task hiển thị.
  Original nói MACD dưới Signal, nhưng số thật là −2,7649>−3,0568;
  U_full nói đúng quan hệ, viện dẫn T1/T2 với +0,24%/−1,81%. Đây là payoff
  **E1/E2**, không phải mean của hai task; ID có thật nhưng scope giải
  thích chưa rõ. “Recent weakness” không có ngày hiển thị: hai episode
  thực đã 399/714 ngày. Trend thị giác tăng có warning, Pattern giảm có
  warning, alpha 3/5 tăng. Full/examples LONG và body trùng khi stats tắt;
  hai slot vẫn được gọi riêng, response trùng không làm tăng số point
  kiểm định độc lập. Cycle thực lãi 88,5→90,1.
- **FPT-2023-11-23:** Original ưu tiên alpha giảm/lack of breakout, U_full
  ưu tiên Trend/MACD tăng dù có alpha 4/5 giảm và pattern warning. Hai
  exemplar dương nhưng hai task thắng chỉ 1/5, 4/10; C mean thô âm. C có
  tuổi 86–1.249 ngày, hai exemplar 352/637 ngày; không phải cùng population
  đã lọc tuổi. U_full không giải thích prior. Entry/exit 90,8→91,1 tăng
  **+0,330396% gross** nhưng net **−0,369465%** sau phí/slippage. Không thay
  nhãn net bằng nhãn đúng hướng giá để gọi cycle thắng.

### Phát hiện nội dung và đầu vào cho U11-05

Có lỗi hoặc điểm mơ hồ trong **phản hồi**, cần phân biệt với lỗi runtime:
VNM-2023-04-04 gọi alpha xác nhận giảm dù prompt ghi 5/5 tăng;
VCB-2023-03-06 lấy tỷ lệ 1/5 của T1 nói chung là prior long success trong
khi C thực là 1/13; VCB-2023-08-29 dùng T thay cho E khi nói payoff cycle.
Đây là các ví dụ có nguồn đối chiếu cụ thể, không phải ước lượng tỷ lệ
hallucination toàn provider. Cảnh báo/input xung đột cũng đã có sẵn ở
upstream v1, không được quy mọi lỗi diễn giải cho block Bayes.

FPT-2023-07-05, MWG-2023-09-29 và MWG-2023-11-23 có lời giải gắn SHORT
với thu lợi từ giá giảm/bán khống; MWG-2023-06-01 còn khuyên stop-loss.
Engine vẫn thực thi CASH cho SHORT và Open(t+1)→Close(t+3) cho LONG,
không TP/SL. Đặc biệt FPT-2023-07-05 **prior off/shared Original**, cho
thấy ngữ nghĩa này đã có ngoài prefix U. Không sửa response/action, gọi
lại LLM hoặc sửa engine để làm lời giải khớp sau khi biết outcome.

Audit hỗ trợ **kiểm** hai giả thuyết đã đề xuất: xác suất thắng thiếu độ
lớn lãi/lỗ; cấu trúc prefix/đối chiếu chưa làm rõ population, ID và bất định.
Mean C âm ở cả năm điểm, kể cả p>0,5 ở MWG-2023-04-28; một số exemplar
dương không đại diện mean C. Nhưng nếu veto theo mean C âm ở năm điểm
này thì cũng bỏ hai cycle lãi: đây **không phải** bằng chứng rule veto hoặc
payoff R2 sẽ thắng. Tuổi memory, tín hiệu có điều kiện yếu, prompt chung và
noise provider vẫn là giả thuyết cạnh tranh; 5 thay đổi/60 không đủ phân
rã nguyên nhân. Repeat giữ kết quả/giới hạn U11-03, không chọn lượt tốt.

**Bàn giao U11-05:** giữ mô hình payoff/parameter và gate offline đề xuất
trong kế hoạch; khóa protocol R2 trước phép đo, dùng đúng 647 query train
PIT/fold/common support, báo cả outlier/phụ thuộc/n nhỏ. Chưa tính hoặc
tuyên bố gate đó PASS ở U11-04. Không dùng bảng 60 điểm này để chọn mẫu,
threshold, đổi bank/retrieval, thêm rule riêng từng mã, hoặc biến dữ liệu đã
xem thành holdout. R2 chỉ tiếp tục nếu gate/support đáp ứng; chưa mở 2025.

### Kiểm tra và đóng task

Đối soát **376 hash nguồn**, 60 dòng bảng với sidecar, đủ 60 payoff query/
300 action-evaluation, ID/visibility/shared-off, tuổi/partition/n/s **PASS**.
Oracle NumPy độc lập **180 nhóm C/B1/B2 PASS**, kiểm mean/median, win/nonwin
và đẳng thức mean theo xác suất thắng thực nghiệm; kiểm cả nhóm trống/null,
không thay p thực nghiệm bằng posterior. Checklist duy nhất đủ 01–11,
**bốn DONE/bảy TODO**; liên kết/anchor mới, UTF-8 và `git diff --check` PASS.

Cold consumer `tools/nominate_unified_bayes.py` **PASS** trên nguồn thật:
`NOT_NOMINATED; positive_symbols=2/4; D=0.026473168; API=0;
confirmation_allowed=false`. Tái dựng và đối soát kernel/source/runtime,
receipt/readiness, journal/cache/ledger/report và selection đã khóa; không
chỉ tin self-seal. Lượt trong sandbox dừng ở `host_boot` vì không đọc được
boot Windows; lượt ngoài sandbox hoàn tất với audit hook chặn
`socket.connect/getaddrinfo`, `.env*` và `execution_prices_2025`.
Snapshot **983 file cũ** của namespace v1 và ledger: **977 nguyên byte**,
chỉ sáu metadata owner/recovery của run/journal/preflight được consumer
cập nhật; cả ba owner đã `released`. Plan, protocol, selection, Decision
journal, cache, report, receipt và ledger không đổi. Chỉ thêm sidecar audit
mới trong namespace này; nguồn W8/W9 trong map 376 hash vẫn nguyên vẹn.

Task chỉ đổi **ba Markdown** trong Git và thêm một đầu ra phân tích ignored;
không đổi code/test/schema/runtime, source input, prompt, action, protocol
hoặc ledger v1. Theo AGENTS.md 1.2, **không chạy compileall, unit, E2E hay
leakage suite**; không ghi là đã chạy lại bốn gate. Các số gate W10 vẫn là
receipt lịch sử gắn đúng nguồn/runtime; đây là kiểm tra audit và consumer,
không là nghiệm thu runtime R2 chưa có. **U11 đạt 4/11**, tiếp theo
**U11-05** khóa protocol R2 và gate payoff trên train PIT.

## U11-05 — Protocol R2 và gate payoff train PIT (27/10/2026)

**DONE; kết quả nghiên cứu: gate payoff FAIL, R2 dừng trước development LLM.**
Đây là kết quả hợp lệ của phép kiểm đã đăng ký, không phải lỗi thực thi hoặc
nomination thất bại. U11-06–09 **NOT_RUN** theo rule dừng, không tính DONE;
tiếp theo U11-10 viết kết quả/thảo luận. v1 vẫn NOT_NOMINATED, W9 giữ kết
quả riêng; R2 chưa có renderer/probe LLM, development, nomination hoặc xác nhận.

### Khóa trước phép đo và phạm vi triển khai

[Protocol R2](unified_bic_r2_protocol_v1.json) commit **`cb71279`** trước khi
tính gate; digest canonical SHA-256
**`55cea533fe0854776d1d9bd2b0f1d138fdb71a9ec8895f1e9a14a90c8062afa0`**.
Đây là hash JSON canonical, ổn định qua LF/CRLF, không phải hash byte file.
Code/test commit **`0705421`** sau kiểm thử, cũng trước phép đo thật.
Không thay protocol/parameter/rule sau outcome.

Một mô hình NIG duy nhất, đơn vị return **tỷ lệ**: κ0=4, α0=2,
m0=mean(B1∪B2), β0=max(sample variance B, 10⁻⁶); cần nB≥20, nC≥5 và
gate stats v1 ready. Giữ nguyên công thức ở phần thiết kế, λ=8, memory/
partition/retrieval, engine và model LLM. `pool_8` trong protocol là ID
posterior diagnostics, tương ứng choice v1 `hierarchical_pool`, λ=8;
`inherited_sections` giữ cấu hình lịch sử, `reselect_lambda=false` khóa
việc không chọn lại các lambda. CrI95% dùng scale mean; PI90% dùng scale
predictive lớn hơn hệ số √(κn+1). Công thức đã đối chiếu
[Murphy §6](https://www.cs.ubc.ca/~murphyk/Papers/bayesGauss.pdf) và quy ước
`loc/scale` của [SciPy 1.16.1 Student-t](https://docs.scipy.org/doc/scipy-1.16.1/reference/generated/scipy.stats.t.html).

Protocol còn khóa ma trận sáu LLM + Numeric_payoff, 360 primary/252 repeat,
12 ID repeat v1, một candidate R2_full, rule nomination v1 cộng R2−v1>0,
coverage payoff, xác nhận có điều kiện và family năm contrast CI99%.
Đó là đăng ký thiết kế có điều kiện, **không phải** các run đã thực hiện.
Template/12 probe và release xác nhận dự kiến là khóa riêng ở U11-06/08;
chúng không được tạo vì gate U11-05 trượt.

Triển khai mới nằm riêng tại
[module payoff](../../../tools/unified_bayes_r2_payoff.py),
[producer/consumer offline](../../../tools/prepare_unified_bayes_r2_payoff.py)
và [test số học/gate](../../../tools/test_unified_bayes_r2_payoff.py),
[test PIT/leakage](../../../tools/test_unified_bayes_r2_payoff_leakage.py).
Không sửa code/schema/receipt đã đóng băng của v1. Consumer tái dựng kết
quả từ nguồn và rule, không tin nhãn PASS/FAIL hoặc self-seal của JSON.
Prepare write-once giữ cùng identity; không có cờ gọi API hoặc đổi tham số.

### Train PIT, support và kết quả gate

Dùng đúng **647 query** U10-04: 325 train_2021 và 322 train_2022; bốn query
cuối 2021 vắt exit qua biên năm tiếp tục bị purge, không dùng lại mẫu 651.
Tái dựng IDs/calendar t+1/t+3, partition cùng mã/rời nhau/exit<query,
n/s, posterior λ=8 và readiness rồi đối chiếu snapshot U10-04 đã khóa.
Tín hiệu/regime/scaler và provenance HMM historical-prefix được tái dùng
từ snapshot đã kiểm, không refit hoặc chạy lại upstream. Tạo evidence
trước khi đọc target query; **647 target và 852 nhãn prior train** được
đối soát bằng `HistoricalOutcomeGenerator`/hàm kinh tế engine hiện hành.

Primary scoring dùng cùng giao **396/647** cho NIG, zero, m0 và prior
predictive. Có đủ tám ô fold/mã dưới đây; support hợp lệ nên verdict là
**FAIL**, không phải INCONCLUSIVE. Rule support được khóa trước phép đo:
mỗi ô phải có ít nhất một row, từng row đạt nB/nC/readiness và metric hữu
hạn. Đây không là chứng nhận power hoặc số quan sát độc lập.

| Fold | FPT common/planned | MWG | VCB | VNM | Tổng |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2021 | 38/80 | 47/81 | 43/82 | 49/82 | 177/325 |
| 2022 | 59/79 | 54/81 | 57/82 | 49/80 | 219/322 |
| Tổng | 97/159 | 101/162 | 100/164 | 98/162 | 396/647 |

**251 row không ready đều có nC<5**, giữ nguyên trong report với reason và
metric null. `LOW_CONDITIONAL_SUPPORT` và `V1_STATS_NOT_READY` cùng gắn
251 row; 53 row còn `MISSING_PAYOFF_POSTERIOR` do C rỗng. Đây là reason
chồng nhau, không cộng thành số query bị loại. Không đổi ngày/nhãn, cắt
outlier, điền missing bằng zero hoặc chấm các baseline trên mẫu khác.

MAE và width dưới đây đổi từ tỷ lệ sang **% return** để đọc; rule tính bằng
precision gốc. NLL dùng density theo đơn vị tỷ lệ, có thể âm, **thấp hơn
tốt hơn**; không so NLL khác đơn vị hoặc loại hằng số density.

| Panel | Common | MAE NIG | MAE zero | MAE m0 | NLL NIG/prior | PI90% coverage | Width90% |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| Tất cả | 396 | 2,698528 | 2,660456 | 2,615347 | −1,815169 / −1,935797 | 81,818182% | 9,823727 |
| 2021 | 177 | 2,449047 | 2,412784 | 2,369764 | −1,876060 / −2,028495 | 81,920904% | 8,981428 |
| 2022 | 219 | 2,900164 | 2,860628 | 2,813833 | −1,765955 / −1,860876 | 81,735160% | 10,504489 |
| FPT | 97 | 2,923071 | 2,852774 | 2,843525 | −1,600473 / −1,799789 | 81,443299% | 10,359974 |
| MWG | 101 | 3,314022 | 3,237010 | 3,232707 | −1,592503 / −1,700375 | 76,237624% | 10,472132 |
| VCB | 100 | 2,510829 | 2,540633 | 2,475747 | −1,884726 / −1,975539 | 81,000000% | 9,593763 |
| VNM | 98 | 2,033471 | 1,998164 | 1,895689 | −2,186179 / −2,272490 | 88,775510% | 8,859354 |

**Cả sáu check đều FAIL:** MAE NIG cao hơn zero **0,038073 đpt** và m0
**0,083181 đpt**, không cải thiện strict ít nhất một baseline; VNM tăng
MAE so m0 **0,137782 đpt**, vượt guard 0,1; mean NLL tăng **0,120628**;
coverage PI90% chỉ **324/396=81,818182%**, dưới 85%. MAE NIG của VCB thấp
hơn zero vẫn không cứu được gate toàn mẫu hoặc thay candidate/estimand.

### Outlier, phụ thuộc, n nhỏ và giới hạn

Report giữ đủ panel tám fold/mã, width, top 10 absolute error và top 10
NLL, cụm 90 phiên, lag-1 theo fold/mã và chín stress tổng hợp đã đăng ký.
Stress gồm nC=0..5, thay một quan sát bằng −50%/+50%, và quan sát lặp
giống nhau; chỉ kiểm độ nhạy/số học, không sửa dữ liệu gate.

| nC | Planned/common | MAE NIG (% return) | PI90% coverage |
| --- | ---: | ---: | ---: |
| 0–4 | 251/0 | null | null |
| 5–9 | 171/171 | 2,497809 | 83,625731% |
| 10–19 | 139/139 | 3,047716 | 81,294964% |
| ≥20 | 86/86 | 2,533247 | 79,069767% |

MWG-2022-11-15 có target net **+18,740368%**, absolute error NIG
**19,855757%**, không bị loại. FPT-2021-01-25 có target **−13,790768%**,
NLL NIG/prior **11,331816/3,761816**; PI90% width chỉ **7,007918**. Đây
là quan sát sai số/tail của mô hình này, không tự chứng minh một nguyên
nhân duy nhất. Lag-1 target theo tám ô từ **−0,312342 đến +0,165969**,
residual từ **−0,280122 đến +0,187427**; các pool lịch sử còn được dùng lại
giữa query. Không dùng lag nhỏ hoặc Student-t để tuyên bố độc lập/ESS=n.

Train 2021/2022 đã được dùng chọn λ của v1; gate R2 là kiểm tra nghiên
cứu tiếp nối đã đăng ký, **không phải xác nhận độc lập**. Các xấp xỉ
Gaussian/empirical Bayes và conditional signal này chưa đạt điều kiện
tiếp tục; không suy ra mọi Bayes/ICL đều vô ích. Không thử family, κ/α,
floor hoặc conditional grouping khác sau kết quả này trong vòng R2.

### Artifact, kiểm tra và bàn giao

Artifact ignored duy nhất mới:
`outputs/bayesian_benchmark/unified_bic_r2/offline/payoff_gate_v1.json`,
**5.272.093 byte**, SHA-256 byte
**`ef6130b85974604482c157b3ce70899a0470e4f6ef06453cd4f2d54def8136d8`**.
Gắn protocol, **1.835 hash nguồn**, runtime và hash text LF riêng của bốn
file code/test; lưu đủ 647 row, evidence/membership/prediction/target,
support/reason, metric/panel/diagnostics và `development_allowed=false`.
Protocol không ghi đè trạng thái snapshot v1; report FAIL không là cờ release.

Producer `--prepare` và consumer mặc định đều hoàn tất trên nguồn thật;
consumer tái dựng đúng report/FAIL. Có audit hook từ trước import, chặn
mạng, `.env*`, giá 2025 và đường Decision development v1. **API=0**,
không đọc ledger để gọi API, không refit hoặc mở xác nhận. Lệnh kiểm offline:

```powershell
py -3.13 -X utf8 tools/prepare_unified_bayes_r2_payoff.py
```

**Kiểm tra kỹ thuật PASS:** 29 test mới (19 số học/gate/consumer +10 PIT),
7 test `test_unified_bayes_statistics_leakage.py` của primitive tái dùng,
biên dịch đúng bốn file Python mới. Test kiểm scale mean/predictive,
variance floor, n nhỏ/missing/overflow, density oracle, biên gate strict,
same-support, source/self-seal, self/equal-exit/future/foreign poison và
purge t+1/t+3. Oracle CDF/PPF dùng sai số 10⁻¹⁰; đây không phải epsilon
của gate. Fixture tạm cần chạy ngoài sandbox do ACL TemporaryDirectory;
không thay rule hoặc dữ liệu để xử lý quyền file.

Oracle độc lập trên nguồn thật **7.096 đối soát PASS**: partition PIT từ
metadata, NIG theo tổng bình phương chưa centered, scale, Student-t log
density viết riêng, metric của 396 row common và aggregate. Producer đã
đối soát đủ 852 nhãn train bằng engine. **984 file v1/ledger cũ nguyên byte**,
gồm selection/plan/report/journal/cache/receipt/metadata khóa và audit
U11-04; không cập nhật khóa v1 khi kiểm R2. Diff/liên kết/UTF-8/hash và
checklist 01–11 với **5 DONE/4 NOT_RUN/2 TODO** PASS.

Theo AGENTS.md 1.2, chỉ kiểm đường payoff/PIT mới và primitive liên quan,
**không chạy lại toàn unit suite, compileall codebase hoặc E2E**. Gate
W10 vẫn chỉ bao phủ code v1 đã khóa, không thay nghiệm thu bổ sung này.
**U11 đạt 5/11**, U11-06–09 NOT_RUN; chuyển **U11-10** tổng hợp W9/v1/R2
offline, không gọi R2 NOT_NOMINATED hoặc báo lợi nhuận LLM R2 chưa chạy.
