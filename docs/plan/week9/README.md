# Tuần 9 — Benchmark holdout và phân tích thống kê

**Trạng thái: IN_PROGRESS, 4/6; W9-01–04 DONE, tiếp theo W9-05; Gate W8 PASS.** Giữ deadline 10 tuần; cập nhật 21/10/2026.
[Kế hoạch tổng](../plan.md) · [W8](../week8/README.md) · [W10](../week10/README.md)

## Phạm vi và đầu vào

Gate W8 PASS, selection/protocol/manifest mới đã khóa; cohort 2024 gồm
64 điểm, 16 điểm mỗi mã FPT/VNM/VCB/MWG. Không mở holdout trước khóa.
Dành khoảng 60% tuần cho chạy/đối soát và 40% cho thống kê/hình/bảng;
công cụ thống kê phải được chuẩn bị bằng fixture ở W8. Không phát triển ứng viên
mới trong tuần này; người dùng tự thực hiện preflight/API theo CLI đã kiểm.

## Protocol thống kê đã khóa tại W7-14

Áp dụng `improvement_protocol_v1` từ
[W8](../week8/README.md#protocol-cải-tiến-đã-khóa-tại-w7-14), hiệu lực
16/10/2026; amendment vận hành `improvement_protocol_v2` giữ phương pháp này.
[W8-07](../week8/README.md#w8-07--khóa-manifest-và-công-cụ-xác-nhận-holdout-20102026)
đã khóa manifest `improvement_bound_holdout_v1`, consumer bootstrap/fixture và
bốn gate kỹ thuật. [W8-08](../week8/README.md#w8-08--nghiệm-thu-và-bàn-giao-holdout-20102026)
đã nghiệm thu và khóa release; hướng dẫn preflight/run/resume/verify/bootstrap
ở liên kết này. W9-01 preflight PASS; W9-02 đã chạy đủ 384 Decision
trên 64 điểm. W9-03 đã kiểm toán semantic và consumer holdout offline PASS;
W9-04 đã khóa và verify bootstrap thật; W9 hiện 4/6 DONE, tiếp theo W9-05.
Các lệnh verify/bootstrap hiện hành ở
[phần W9-03](#w9-03--kiểm-toán-semantic-và-consumer-holdout-21102026).
Giữ đủ **64 point ID/ngày W5, 16/mã**, không chọn lại theo regime/outcome.
Ma trận xác nhận gồm `original, bayesian, C2, selected_full,
selected_stats_only, selected_examples_only`; ánh xạ selected bằng selection
W8 rồi gộp ID trùng trước API. Chỉ ứng viên đã chọn được xem outcome; không
chạy cả A/B để chọn lại. Ablation dùng evidence/schema của chính selected,
không thay C2 bằng C3. Nếu thiếu consumer/verifier thì gate BLOCKED.

Primary mỗi point/nhánh **một Decision**, repeat_id=0. Xếp point theo
(as_of_date, thứ tự mã FPT/MWG/VCB/VNM), j từ 0; xoay trái danh sách ID
đã gộp j mod M bước, M là số nhánh. Giữ model/options, retrieval seed=42,
risk OFF và upstream một lần/point như W8. Không lặp holdout để lấy lượt
thuận lợi. Selection/registry/protocol và danh sách ID/thứ tự thực tế phải
bind vào manifest trước preflight/API; manifest W8-07 đã lưu đủ các binding.
CLI `scripts/run_improvement_holdout.py` chặn online khi chưa có receipt
`improvement_holdout_release_v1` hợp lệ từ bàn giao W8-08. Release đã khóa,
Gate W8 PASS; người dùng có thể bắt đầu W9-01 theo hướng dẫn đã bàn giao.

**Estimand chính:** D=(1/4)Σ_s(R_selected,s−R_original,s), đơn vị điểm
phần trăm, R là return tài khoản từ vốn đầu 50 triệu trên lịch của từng mã,
giữ engine lot/phí và T+2.5. Không lấy mean cycle return thay D, không gọi D
là return portfolio. Hướng mong đợi D>0; báo ΔR và ΔMDD từng mã/mean/max,
ΔMDD>0 là rủi ro tăng. Common support G chỉ COMPLETE khi đủ 64 điểm ở
mọi nhánh đã khóa; thiếu nhánh/unknown thì primary INCOMPLETE, không loại
điểm lỗi hoặc điền CASH. Pairwise phần có được chỉ là mô tả, không thay G.

**CI chính:** circular moving-block bootstrap trên chuỗi ngày cutoff duy
nhất tăng dần trong G, **L=4 ngày cutoff liên tiếp**, không phải bốn phiên
thị trường. Mỗi cụm giữ mọi mã có point ngày đó và mọi nhánh; không tạo
point cho mã vắng. Dùng NumPy `Generator(PCG64(20261016))`, **10.000 lần**:
lấy ceil(n_dates/4) điểm bắt đầu uniform có hoàn lại trong [0,n_dates−1],
mỗi điểm lấy bốn cụm liên tiếp modulo n_dates, nối rồi cắt còn n_dates.
Cùng chuỗi index cho mọi nhánh và mọi contrast. Dựng lại tài khoản từng mã
từ vốn đầu theo thứ tự mẫu tổng hợp, cùng lot/giá entry-exit/phí engine;
không cộng R/MDD đã tính sẵn hoặc sắp mẫu lại theo ngày lịch gốc. Số cycle
mỗi mã có thể đổi khi resample cụm; phải báo phân phối count từng mã.

CI percentile hai phía 95% lấy quantile 0,025/0,975, `method=linear`, của
D hữu hạn. Draw thiếu mã hoặc metric không hữu hạn là INVALID, ghi lý do;
không sinh thêm draw để thay. Cần ≥9.500/10.000 draw hợp lệ, nếu thiếu thì
CI=BLOCKED/insufficient, giữ point estimate nhưng không claim xác nhận.
CI hoàn toàn >0 hỗ trợ hiệu ứng dương trên cohort/protocol này; CI chạm
hoặc qua 0 là inconclusive, không kết luận tương đương. CI điều kiện trên
method/Decision đã lưu; không bao gồm bất định training, provider hoặc
kiến thức LLM lịch sử. L=4 chọn trước outcome để giữ phụ thuộc cục bộ trong
lịch rút gọn; không khẳng định là block tối ưu. Kiểm L=2/8 với cùng seed,
10.000 draw mỗi L, chỉ độ nhạy mô tả, không đổi CI chính hoặc chọn CI đẹp nhất.

**Secondary cố định:** selected−C2, selected−Bayesian v1,
selected_full−selected_stats_only và selected_full−selected_examples_only.
Contrast trùng/đồng nhất ID bị gộp trước API (selected=C2 thì bỏ contrast
tự so); số contrast m được ghi vào manifest. Dùng cùng bootstrap, CI
percentile Bonferroni mức 1−0,05/m cho từng D, quantile 0,05/(2m) và
1−0,05/(2m). Đây là family secondary riêng, không thêm phép so sau outcome.
MDD, accuracy, LONG/CASH, exposure, bảng action 2×2, Q1–Q4/H1–H2,
leave-one-symbol-out và subgroup prior-off/ready là mô tả; có mẫu số/null.
Không dùng McNemar/Wilcoxon làm kiểm định xác nhận trong protocol này vì
không bảo đảm các cycle độc lập. Không lấy p-value danh nghĩa để bỏ qua
phụ thuộc hoặc thay primary. Sharpe/Sortino giữ quy ước chu kỳ đã có.

Full/stats/examples phải cùng base evidence và schema, khác content mode;
G mô tả hiệu ứng gồm cả visibility/fallback, T cùng ready mới xem thành
phần trên bằng chứng chung. Trace không xác nhận cơ chế suy luận. Calibration
chỉ dùng xác suất sự kiện hợp lệ theo diagnostics W8, confidence văn bản
không là p. Không chọn/promote lại theo holdout, kể cả secondary hoặc subgroup
đẹp hơn; kết quả âm và thiếu lực kiểm định vẫn là kết quả phải công bố.

## Checklist

| Task | Công việc và điều kiện hoàn thành | Phụ thuộc | Trạng thái |
| --- | --- | --- | --- |
| W9-01 | Kiểm manifest, môi trường và nguồn; preflight đúng model/options; khóa run identity | W8 PASS | [x] DONE — offline/identity và preflight text/vision PASS |
| W9-02 | Chạy bốn mã/ma trận đã khóa; checkpoint, ledger, retry; một upstream/point deep-copy mọi nhánh | 01 | [x] DONE — 384/384 Decision, 64/64 điểm; snapshot/report khớp |
| W9-03 | Verify semantic toàn run, PIT, P&L, common support, missing/unknown và checksum | 02 | [x] DONE — consumer CLI, PIT/P&L/support/checksum PASS |
| W9-04 | Tính primary ΔR/MDD và CI theo protocol; secondary/ablation và kiểm nhiều so sánh | 03 | [x] DONE — bootstrap/verifier/oracle PASS; primary CI dương, secondary inconclusive |
| W9-05 | Xuất bảng/biểu đồ, phân tích thất bại/coverage/prior-off và giới hạn | 04 | [ ] TODO |
| W9-06 | Khóa dữ liệu kết quả, kiểm tái lập và bàn giao chương kết quả W10 | 05 | [ ] TODO |

## W9-01 — Kiểm điều kiện preflight, 20/10/2026

**DONE — kiểm offline và preflight thật PASS.** Manifest,
release và receipt bốn gate khớp; kiểm toàn bộ 64 cutoff/PIT/scaler, 51 nguồn,
74 dependency/schema/fixture và runtime Python 3.13.5 PASS.
Tokenizer cache đúng hash; `.env` tồn tại, chưa đọc hoặc xác thực key trong
kiểm tra offline. Hai client thật được dựng với khóa giả và MockTransport
chặn mạng; validator xác nhận defaults/options/retry đúng protocol, không invoke.

| Vai trò | Model | Temperature / max_tokens | reasoning_effort / reasoning_format |
| --- | --- | --- | --- |
| Text | `openai/gpt-oss-20b` | 0.0 / 2048 | `low` / `hidden` |
| Vision | `qwen/qwen3.8-27b` | 0.0 / 1024 | `none` / `hidden` |

Đối chiếu identity theo đúng công thức runtime: plan, execution_mode=research,
ledger tuyệt đối trong workspace hiện tại, receipt gate, nguồn và upstream_reuse=false.
Digest run dự kiến: `45e0637eb572921932179147103e0bf3ef94d74a1d9428cf97b7e8f0aa59de6c`.
Chưa tạo `run/cohort.json`, slot hoặc thực hiện Decision; runtime sẽ khóa và
kiểm identity này khi bắt đầu W9-02. Plan/release/risk OFF giữ nguyên bản W8.

Người dùng đã chạy preflight thật thành công. Ledger có proof **PASS** gắn
đúng digest plan holdout `037b7e3088e1803e5e52261417e4313e996f41c8a28e0661d7acc5a02cbc09ff`;
audit request được đối chiếu offline với serializer text/ảnh đỏ 64×64 và
model/options đã khóa. Cả hai response HTTP 200 có fingerprint, usage hợp lệ,
cùng credential scope và amendment; không dùng proof development thay thế.

| Vai trò | Request ID | HTTP | Tổng token |
| --- | --- | --- | --- |
| Text | `3e8781d6-54d1-4a9d-a5db-2a85a915a4da` | 200 | 106 |
| Vision | `9688bc07-7c2f-4815-b4be-0685c7d60bc3` | 200 | 1316 |

Ledger có **2.502 request**, tăng đúng hai so với mốc kiểm offline; hash byte
ở thời điểm nghiệm thu: `a33e1a66ff067e7479f47bd637dbeefad895a197a54d729dc0648d9135f52b49`.
Digest proof preflight: `ae64a19a251ba3f294bee32183187a4d9d379ac3cb3780ee195697c116ca4f87`.
Kiểm lại các binding HTTP primary/repeat cũ và selection PASS; không có request
mới do bước nghiệm thu. Ledger sẽ tiếp tục được nối khi chạy W9-02, không reset.

**W9 đạt 1/6 DONE; tiếp theo W9-02** chạy đủ 64 điểm/sáu nhánh, 384 Decision.
Từ root (PowerShell), dùng đúng namespace/ledger đã khóa:

```powershell
py -3.13 -X utf8 scripts/run_improvement_holdout.py --run --resume --technical-gates docs/plan/week8/validation_gates/bound_holdout_v1/technical_gates.json
```

CLI dùng mặc định plan/release/output holdout, `.env` và ledger chung. Khi
đổi key, sửa `.env` rồi chạy lại chính lệnh trên; giữ plan/output/checkpoint,
CLI tự preflight key mới và phục hồi theo policy đã khóa. Tham khảo đầy đủ
[các lệnh verify/bootstrap và điều kiện hoàn tất](../week8/README.md#w8-08--nghiệm-thu-và-bàn-giao-holdout-20102026).
Chưa chạy Decision hoặc tính P&L/CI holdout trong W9-01.

Chỉ cập nhật README tuần/kế hoạch; không đổi code/test/schema/runtime/đầu vào,
không chạy lại compileall/unit/E2E/leakage theo AGENTS.md mục 1.2. Consumer
receipt W8-07 PASS đúng bản: compileall/E2E, 909 unit/168 leakage, không skip;
đây là kết quả đã chạy trước, không phải chạy lại W9. QA hash/link/diff và
3.382 file đã bảo vệ nguyên byte, gồm ledger sau preflight; nghiệm thu không
gọi thêm API hoặc thay dữ liệu khoa học.

## W9-02 — Nghiệm thu thực thi holdout, 21/10/2026

**DONE — người dùng chạy đủ 384/384 Decision**, 64/64 điểm, sáu nhánh theo
manifest; FPT/MWG/VCB/VNM mỗi mã 16 điểm × 6 nhánh = 96 Decision. Report
`improvement_holdout_report_v1` có `primary_status=COMPLETE`, common support
G=64, 16/mã, `repeat_id=0`; mọi slot đã complete, không còn planned/unknown.
Ma trận giữ `original, bayesian, C2, A_tp_pool, A_tp_pool_stats_only,
A_tp_pool_examples_only`, risk OFF; không phát sinh cấu hình hoặc lượt lặp mới.

Journal có **64/64 complete** ở từng stage indicator, pattern, trend và full;
mỗi stage/point và mỗi Decision/slot chỉ có **một attempt khoa học**. Upstream
được dùng chung cho các nhánh qua cùng shared proof; HTTP retry/fallback thuộc
attempt hiện hữu, không tính là lượt lặp nghiên cứu. Prompt Decision tối đa
**4.511 ký tự**, dưới ngưỡng 6.500.

Runtime đã khóa tái dựng toàn report từ source/PIT/scaler, shared,
evidence/prompt/request, checkpoint/raw response và HTTP audit. Đối chiếu
độc lập bằng `read_envelope` và digest toàn payload, nhận đúng version
`improvement_holdout_report_v1`, **PASS offline** với transport chặn mạng;
không chạy lại LLM. Report bind **51 nguồn,
74 dependency/schema/fixture, runtime và 908 mục checkpoint/HTTP audit**.
Run signature khớp digest dự kiến W9-01:
`45e0637eb572921932179147103e0bf3ef94d74a1d9428cf97b7e8f0aa59de6c`.
[Report local](../../../outputs/bayesian_benchmark/improvement_v1/holdout/run/report.json)
SHA-256 byte: `0a926be1e6da2803d56dd7a572a4d3eae7b8863cc3fcd02eea111df35cd7c23f`.
Digest payload khớp bản tái dựng: `5ba544abbd07b55f45dfd263d34687c41aac3d74c056e900f8d26d230f893aa4`.

**Lỗi consumer CLI ghi nhận ở W9-02, đã xử lý bằng entrypoint W9-03:** lệnh `--verify-report` nguyên bản
exit 1 ở `core/improvement_reports.py:172`: whitelist chỉ nhận report
development/repeat, chưa nhận version holdout. Không ghi lệnh này là PASS.
Lượt đối chiếu độc lập dùng nguyên runtime đã khóa, thay đúng bước đọc cuối
bằng kiểm envelope/version holdout và digest toàn payload; payload khớp bản
tái dựng. Giữ nguyên code/manifest/release/run. Consumer tương thích đã được
bổ sung và kiểm lại tại W9-03 bên dưới; không sửa checksum/report để ép PASS.

QA số lượng/lịch/identity/hash/link/diff PASS; **4.409 file khoa học/nguồn/code
được bảo vệ nguyên byte**, gồm report, checkpoint, ledger và bằng chứng cũ.
Chỉ cập nhật hai Markdown; không đổi code/test/runtime/schema/đầu vào, không
chạy lại compileall/unit/E2E/leakage theo AGENTS.md mục 1.2. Consumer receipt
bốn gate W8-07 PASS đúng binding (compileall/E2E, 909 unit/168 leakage);
đây là kết quả đã chạy ở W8-07, không phải chạy lại trong W9-02.

**W9 đạt 2/6 DONE, tiếp theo W9-03** kiểm toán semantic/PIT/P&L/common support,
missing và checksum. Chưa chốt W9-03 hoặc tạo bootstrap/CI W9-04, chưa kết luận
hiệu quả hay chọn/promote lại bằng holdout. Người dùng không cần gọi API thêm
để chốt W9-02; giữ nguyên toàn bộ run để đối soát/phân tích tiếp.

## W9-03 — Kiểm toán semantic và consumer holdout, 21/10/2026

**DONE — kiểm toán offline PASS, W9 đạt 3/6.** Bổ sung
[`verify_improvement_holdout.py`](../../../scripts/verify_improvement_holdout.py)
với consumer nhận đúng `improvement_holdout_report_v1`, kiểm envelope và
so digest **toàn payload** với report vừa tái dựng. Lệnh CLI mới đã chạy trên
run thật **exit 0**, dùng nguyên `run_holdout`/nguồn/PIT/scaler/shared/request/
raw response/HTTP audit và engine đã khóa; không đọc key hoặc cho phép mạng.
Không dùng callback/patch thay consumer khi vận hành.

Giữ nguyên byte **74 dependency frozen**, plan/release, run identity và toàn
bộ 384 Decision. CLI cũ tiếp tục dùng cho preflight/run/resume; từ mốc này
**verify-report/verify-only/bootstrap/verify-bootstrap dùng CLI offline mới**.
Không sửa hash manifest/receipt cũ để nhận code mới. Consumer riêng được bind
bằng hash nguồn trong receipt kiểm toán và phải khớp trước bootstrap.

**Semantic/PIT/P&L/common support:**

- Đủ 64 point ID/ngày W5, 16/mã, sáu nhánh, repeat_id=0; G=64, không nhánh
  planned/unknown/failed/missing. Shared upstream chung, request/schema/raw
  action và 908 binding checkpoint/HTTP audit được runtime đối chiếu lại.
- Đối chiếu độc lập đủ 64 chu kỳ với giá thực thi: Open(t+1) và Close(t+3),
  nhãn LONG qua `compute_round_trip_net_return`, phí 0,25% và trượt giá 0,10%
  **mỗi chiều**. Giữ SHORT=CASH, không short vị thế.
- Dựng lại **24 tài khoản mã × nhánh** bằng `compute_account_metrics`; toàn
  field tài khoản được report công bố khớp engine, gồm return/MDD/equity/
  period returns/cash/shares/P&L. Bốn CASH reference có return/MDD=0;
  mọi chu kỳ cuối giữ cash, shares=0. Không dùng mean cycle return thay return tài khoản.
- 64 snapshot giá/tin không vượt cutoff; **56 lần xuất hiện của 11 prior
  khác nhau** có exit<cutoff, cùng mã. Giá entry/exit và nhãn net-return của
  cả 11 prior cũng khớp hàm kinh tế. BRPP tối đa **441**, prompt tối đa **4.511** ký tự.

Receipt local
[`run/verification.json`](../../../outputs/bayesian_benchmark/improvement_v1/holdout/run/verification.json)
(`improvement_holdout_verification_v1`) bind hash consumer, runtime, plan,
release, gate, report và binding gốc. SHA-256 byte:
`9bb0868740de59972e3183f2e3c449b3f7cd81d559f7598c910ed020681db498`.
Report gốc giữ SHA byte
`0a926be1e6da2803d56dd7a572a4d3eae7b8863cc3fcd02eea111df35cd7c23f`;
digest payload `5ba544abbd07b55f45dfd263d34687c41aac3d74c056e900f8d26d230f893aa4`,
run signature `45e0637eb572921932179147103e0bf3ef94d74a1d9428cf97b7e8f0aa59de6c`.
**4.409 file đã có, gồm ledger và bằng chứng khoa học, nguyên byte** sau kiểm toán.

**Kiểm thử theo AGENTS.md 1.2:** chỉ thêm một consumer/CLI offline và test
riêng, không sửa module runtime, hợp đồng P0, schema/đầu vào/PIT/retrieval
hoặc phép tính kinh tế/bootstrap đã khóa. Biên dịch hai file mới và **44 test
trọng tâm PASS, không skip**: 9 consumer mới, 6 holdout, 7 bootstrap, 3 prior
backtest leakage, 7 execution-price leakage, 12 execution-price; tổng gồm
**11 ca leakage**. Không chạy lại toàn unit suite/E2E/compileall; consumer kiểm
receipt bốn gate W8-07 đúng 74 dependency/runtime PASS, không ghi là gate mới
của consumer. QA diff/link/hash PASS. Không thay 909 unit/168 leakage đã đóng băng.

Lệnh tái kiểm toàn report/receipt (offline, mặc định cũng là verify-report):

```powershell
py -3.13 -X utf8 scripts/verify_improvement_holdout.py --verify-report
```

**Tiếp theo W9-04** tính primary/secondary và CI bằng đúng bootstrap đã khóa:

```powershell
py -3.13 -X utf8 scripts/verify_improvement_holdout.py --bootstrap
py -3.13 -X utf8 scripts/verify_improvement_holdout.py --verify-bootstrap
```

Hai lệnh sau chưa chạy trên holdout thật ở W9-03; fixture đã kiểm định tuyến
và guard receipt. Chưa có bootstrap/CI hoặc kết luận hiệu quả holdout; không
chọn/promote lại ứng viên. Không cần chạy thêm API hoặc phát lại Decision.

## W9-04 — Bootstrap và kết quả thống kê holdout, 21/10/2026

**DONE — W9 đạt 4/6.** CLI offline `--bootstrap` tạo artifact thật và
`--verify-bootstrap` tái dựng/so toàn artifact **đều exit 0**. Status
`COMPLETE`, evidence `HOLDOUT_NOT_FOR_SELECTION`; 64 điểm/6 nhánh, **20 cụm
ngày cutoff**, không thay selection/model/ngưỡng/protocol hoặc phát lại LLM.

**Protocol giữ nguyên:** circular moving-block bootstrap L=4, sensitivity
L=2/8; PCG64 seed=20261016, 10.000 draw mỗi L, cùng chuỗi index cho mọi mã,
nhánh và contrast. Tái dựng tài khoản 50 triệu theo thứ tự mẫu, cổ phiếu lẻ,
phí/slippage hai chiều, SHORT=CASH. Percentile linear, primary CI95%; bốn
secondary dùng CI Bonferroni **98,75% mỗi contrast**. Không dùng độ nhạy để
chọn lại L; không đổi primary hoặc gộp các family sau outcome.

**Primary A_tp_pool−Original:** D=**+2,025325 điểm phần trăm**,
CI95% L=4 **[0,135027; 4,211864]**, **POSITIVE**. CI hoàn toàn >0 hỗ trợ
hiệu ứng dương của cấu hình/Decision đã lưu trên cohort/protocol này. D là
trung bình đều chênh return bốn tài khoản, không là return portfolio, không
chứng minh cơ chế Bayes trong LLM hoặc bảo đảm kết quả triển khai tương lai.

| Mã | R Original (%) | R A (%) | ΔR (đpt) | MDD Original (%) | MDD A (%) | ΔMDD (đpt) |
| --- | --- | --- | --- | --- | --- | --- |
| FPT | -0,428487 | 2,760508 | +3,188995 | 2,750320 | 1,067261 | -1,683060 |
| MWG | 1,935669 | 3,671459 | +1,735789 | 5,896955 | 3,729338 | -2,167616 |
| VCB | -1,176592 | 2,109204 | +3,285796 | 4,932028 | 1,771097 | -3,160931 |
| VNM | -6,472087 | -6,581366 | -0,109279 | 6,472087 | 6,581366 | +0,109279 |

ΔR dương ở 3/4 mã; **VNM vẫn bất lợi**. Mean ΔMDD=
**-1,725582**, max ΔMDD=**+0,109279** điểm phần trăm;
ΔMDD>0 là rủi ro tăng. MDD là mô tả theo protocol, không có CI MDD đăng ký.

**Bốn secondary, L=4; mọi CI chạm/cắt 0 nên chưa có xác nhận sau hiệu chỉnh:**

| Contrast | Point estimate (đpt) | CI98,75% Bonferroni (đpt) | Kết luận |
| --- | --- | --- | --- |
| A−C2 | +1,771525 | [-0,188367; 3,709173] | INCONCLUSIVE |
| A−Bayesian v1 | +2,396920 | [-0,557630; 5,452664] | INCONCLUSIVE |
| A full−stats-only | +0,895340 | [0,000000; 2,495990] | INCONCLUSIVE |
| A full−examples-only | -0,113927 | [-1,571356; 0,971189] | INCONCLUSIVE |

Không kết luận A vượt C2/v1 hoặc xác nhận riêng thành phần stats/examples;
CI full−stats-only có cận dưới đúng 0. Không diễn giải inconclusive thành
hai phương pháp tương đương hoặc không có hiệu ứng.

**Số draw và độ nhạy:** cả ba L đủ **10.000/10.000 hợp lệ**, không thiếu mã,
không metric nonfinite, không sinh bù draw; vượt yêu cầu tối thiểu 9.500.

| L | Vai trò | Draw hợp lệ / invalid | CI95% A−Original (đpt) | Kết luận |
| --- | --- | --- | --- | --- |
| 4 | Primary | 10.000 / 0 | [0,135027; 4,211864] | POSITIVE |
| 2 | Sensitivity | 10.000 / 0 | [0,244409; 4,007282] | POSITIVE |
| 8 | Sensitivity | 10.000 / 0 | [0,509659; 3,523131] | POSITIVE |

Số chu kỳ mỗi mã được giữ theo các cụm thực tế, không ép 16 hoặc tạo point
cho mã vắng. Dưới đây là min–max (mean); histogram đầy đủ ở artifact:

| L | FPT | MWG | VCB | VNM |
| --- | --- | --- | --- | --- |
| 4 | 11–20 (15,9683) | 10–20 (15,9884) | 11–20 (15,9785) | 11–20 (15,9957) |
| 2 | 10–20 (16,0080) | 10–20 (16,0047) | 10–20 (16,0102) | 10–20 (16,0224) |
| 8 | 12–20 (15,9821) | 12–20 (15,9823) | 12–20 (15,9807) | 12–20 (15,9917) |

**QA thống kê PASS:** oracle độc lập tạo từng block/draw theo protocol,
tính tài khoản bằng tích hệ số net LONG/CASH, kiểm đủ 30.000 draw. Index hash,
valid-mask hash, min/max/mean/histogram count từng mã khớp chính xác; point
estimate và mọi CI khớp, sai số cận CI tối đa **4.874e-14 đpt**.
Consumer sản xuất tái dựng bitwise các hash RNG/draw/CI từ cùng report và
đối chiếu toàn payload; file bootstrap nguyên byte qua lượt verify.

Artifact local [`run/bootstrap.json`](../../../outputs/bayesian_benchmark/improvement_v1/holdout/run/bootstrap.json),
version `improvement_bootstrap_v1`; SHA-256 byte:
`78ae445037f68fa0f8cca4638dc7bc3e7c24efb2854539e078478e46db919e57`.
Artifact bind plan/statistics, report digest/SHA byte, run signature,
74 dependency và runtime. Receipt W9-03 bind consumer kiểm toán vẫn hợp lệ.
**4.412 file đã có cùng ledger nguyên byte**; không API. Chỉ sửa hai Markdown
và sinh bootstrap từ producer hiện hữu; không đổi code/test/schema/runtime/
đầu vào. Theo AGENTS.md 1.2, không chạy lại compileall/unit/E2E/leakage;
kiểm source/hash, receipt bốn gate W8-07 và consumer W9-03 đúng binding,
CLI producer/verifier, oracle, số liệu/link/diff PASS. Không ghi gate/test cũ
là đã chạy lại ở W9-04.

Lệnh tái lập/kiểm từ root (offline, artifact write-once):

```powershell
py -3.13 -X utf8 scripts/verify_improvement_holdout.py --bootstrap
py -3.13 -X utf8 scripts/verify_improvement_holdout.py --verify-bootstrap
```

**Tiếp theo W9-05:** xuất bảng/hình và phân tích coverage, prior-off, failure
và các giới hạn; W9-06 mới đóng băng bàn giao. CI điều kiện trên method và
Decision đã lưu, không bao gồm bất định training/provider/LLM. Giữ nguyên
kết quả âm/inconclusive và trạng thái triển khai; không chọn/promote lại bằng holdout.

## Quy tắc thực thi và kết luận

LONG Open(t+1)→Close(t+3), SHORT=CASH, phí 0,25% và trượt giá 0,10% mỗi
chiều; nhãn qua hàm kinh tế dùng chung. Giá/tin≤cutoff, prior exit<cutoff;
không refit/tune bằng holdout. Giữ BRPP≤600, prompt<6.500, risk OFF,
retry/backoff và checkpoint. Unknown phải đối soát, không replay upstream
mù quáng, không đổi ngày lỗi hoặc điền CASH giả. Chỉ resume đúng identity.

Phân tích primary trên đủ common support đã khóa; thiếu nhánh/điểm thì
đánh incomplete, báo phần có được dưới nhãn mô tả. Không kéo dài sang W10
để thử thêm cấu hình; nếu API gián đoạn, ưu tiên phục hồi run đã khóa trong
W9 và báo phần thiếu trung thực. Không hạ gate hoặc dùng selection development
thay kết quả xác nhận. Mọi sửa lỗi ảnh hưởng method/action cần protocol và
run mới; nếu đã xem outcome, kết quả sau sửa là exploratory.

Báo ΔR từng mã và trung bình đều bốn mã (không gọi là return portfolio),
MDD, LONG/CASH, exposure, balanced accuracy, common support và uncertainty.
CI bootstrap theo block/cụm ngày và các kiểm phụ dùng đặc tả W7-14 đã bind ở W8;
không chọn block/kiểm định vì p-value đẹp. Sharpe/Sortino giữ quy ước chu kỳ,
không tự annualize bằng √252. Phân tích calibration chỉ khi có xác suất
sự kiện hợp lệ. Không đủ lực kiểm định thì báo inconclusive.

So sánh ứng viên với Original là primary; C2/v1 và ablation là secondary.
Báo cả mã/regime bất lợi, prior-off, readiness và trace NOT_USED; không suy
trace thành cơ chế Bayes trong LLM. Giữ các giới hạn BEAR=0/tin reliable=0
và FPT thiếu mẫu ở development nếu vẫn đúng; không giả định holdout có
coverage tương tự trước khi đo. Nêu hạn chế PIT hồi cứu và kiến thức LLM.

Đầu ra: artifact có version trong `outputs/bayesian_benchmark/`, bảng
LaTeX và hình khoa học tại `docs/figures/` (vector hoặc ≥300 DPI nếu raster).
README giữ tiến độ và đường dẫn/hash, không thêm receipt lặp lại. Gate W9
đóng khi đủ dữ liệu/verify/phân tích; nếu thiếu, bàn giao W10 với trạng thái
incomplete và giới hạn claim, không ghi benchmark PASS giả.
