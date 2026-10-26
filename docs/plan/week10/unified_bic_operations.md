# Vận hành development U-BICL đã khóa

Tài liệu bàn giao U10-10 cho U11-01/02 trên workspace hiện tại. Trạng thái
nghiệm thu và hash nguồn ở [README W10](README.md#u10-09--dry-run-coverage-mde-và-readiness-25102026).
**U11-01 đã chốt RELEASED_FOR_DEVELOPMENT ngày 26/10/2026**, với binding
nguồn/model/order/repeat và kiểm offline tại [README W11](../week11/README.md#u11-01--dry-run-và-release-development-26102026).
Lệnh dưới đây dùng CLI production đã kiểm ở U10-07–09. Người dùng có thể
thực hiện lần lượt verify offline, preflight và primary/repeat cho U11-02.
**U11-02 đã DONE: primary 300/300 và repeat 216/216 complete**, cold verifier
báo cáo cuối PASS; [nghiệm thu và hash bàn giao U11-03](../week11/README.md#nghiệm-thu-hoàn-tất-u11-02).
**U11-03 đã khóa NOT_NOMINATED** vì chỉ 2/4 mã tăng, dưới ngưỡng ≥3/4;
[quyết định nomination và phân tích](../week11/README.md#u11-03--kiểm-định-development-và-khóa-nomination-26102026).
Run hoàn tất chỉ cần verify/report offline; dừng nhánh xác nhận 2025 theo
protocol, tiếp theo viết kết quả U11-09.

## 1. Bộ bàn giao và trạng thái ban đầu

Trạng thái run khi bàn giao W10-10 dưới đây vẫn khớp kiểm offline U11-01;
quyết định release development hiện hành ở liên kết W11 phía trên.

Mở PowerShell tại root repository, dùng Python 3.13.5 và dependency đúng
runtime trong receipt. Giữ code/model/options/source đã khóa. Clone Git
chỉ có code/tài liệu/schema/fixture; các input/run/receipt ignored cần bản
local gốc khớp hash. Không tạo ledger trống hoặc thay fixture vào nguồn thật.
Run hiện tại còn binding với vị trí ledger trong workspace; giữ nguyên
đường dẫn khi resume, không đổi `--plan`, `--output-dir` hoặc `--ledger`.

| Thành phần | Đường dẫn từ root / vai trò |
| --- | --- |
| Plan | `outputs/bayesian_benchmark/unified_bic_v1/development/plan.json`; 60 primary, 12 điểm ×3 repeat; 96 block/516 slot LLM |
| Run | `outputs/bayesian_benchmark/unified_bic_v1/development/run`; journal durable, report dẫn xuất |
| Ledger chung | `outputs/oos_pilot/api_usage.json`; giữ toàn bộ lịch sử, không reset hoặc tạo ledger thay thế |
| Assessment | `outputs/bayesian_benchmark/unified_bic_v1/development/readiness/assessment.json`; source, coverage, repeat và MDE |
| Bridge | `outputs/bayesian_benchmark/unified_bic_v1/development/readiness/execution_readiness.json`; sáu field cho consumer CLI |
| Receipt hiện tại | Cả thư mục `outputs/bayesian_benchmark/unified_bic_v1/validation/20261025T220030_8658658ad88c4fe1ba8b33afe7e273de`; cần diagnostics, bốn log, technical receipt và audit cùng nhau |

Report lúc bàn giao là `INCOMPLETE`: mọi evaluation query còn null, các slot
LLM chưa có UUID/output/HTTP nghiên cứu; Numeric_only được ghi rõ offline.
Coverage dự kiến không phải common support đã chạy. `nomination_allowed`
và `confirmation_allowed` vẫn false. Các nhãn `PENDING_U10_09` trong plan
và `PENDING_U10_10_AND_U11_01` trong assessment là metadata snapshot; không
sửa JSON để cập nhật checklist. Trạng thái công việc ở README, release
development thuộc U11-01, nomination/xác nhận thuộc các task U11 tiếp theo.

## 2. Kiểm offline trước release hoặc resume

Đặt ba biến đường dẫn một lần trong phiên PowerShell:

```powershell
$validationAudit = "outputs/bayesian_benchmark/unified_bic_v1/validation/20261025T220030_8658658ad88c4fe1ba8b33afe7e273de/validation_audit.json"
$technicalGates = "outputs/bayesian_benchmark/unified_bic_v1/validation/20261025T220030_8658658ad88c4fe1ba8b33afe7e273de/technical_gates.json"
$executionReadiness = "outputs/bayesian_benchmark/unified_bic_v1/development/readiness/execution_readiness.json"
py -3.13 --version
# Mặc định cold verify: source/plan/request, audit/log, coverage/repeat/MDE và bridge.
py -3.13 -X utf8 scripts/prepare_unified_bayes_readiness.py --validation-audit $validationAudit
```

Kết quả cần có `Dry-run/readiness nguồn PASS`, HTTP/payoff query=0. Verifier
không đọc key/ledger, không ghi run hoặc tạo action. Nó tái dựng assessment;
bridge sáu field tự nó chỉ kiểm plan/request/technical receipt, không thay
verifier MDE. Khi cần chẩn đoán riêng, dùng các lệnh offline có thật sau:

```powershell
py -3.13 -X utf8 scripts/run_unified_bayes.py --dry-run
py -3.13 -X utf8 scripts/validate_unified_bayes.py --verify-audit $validationAudit
py -3.13 -X utf8 -c "from core.groq_pacing import tokenizer_cached; assert tokenizer_cached(), 'Thiếu tokenizer cache'; print('Tokenizer cache PASS')"
```

Dùng audit **220030** đã bàn giao, không lấy `validation/diagnostics.json`
của U10-08 làm diagnostics hiện tại hoặc chạy lại `--prepare` để ghi đè nó.
Không cần prepare/initialize lại các artifact đã có. Thiếu tokenizer cache,
nguồn hoặc receipt thì dừng và đối chiếu hướng dẫn môi trường/nguồn; không
giả cache, nới hash, đổi model hoặc tự sinh lại nguồn bằng dữ liệu mới.

U11-01 đã đối chiếu đầy đủ plan/model/source/order/repeat, assessment và
receipt/log bốn gate đúng code/runtime; xem [nghiệm thu release development](../week11/README.md#u11-01--dry-run-và-release-development-26102026).
Không chạy lại toàn suite vì code/runtime giữ nguyên. CLI kiểm technical
receipt/bridge; quyết định release nghiên cứu được ghi ở README W11.
Khi resume vẫn phải verify đúng bộ đã khóa. Xác nhận 2025 chờ U11-03/04.

## 3. Người dùng chạy API sau release development

CLI đọc `GROQ_API_KEY` từ `.env` local hoặc biến môi trường sau các guard.
Không đưa giá trị key vào lệnh, log, receipt hoặc Git. Giữ nguyên ba biến
đường dẫn ở mục 2; `--env-file ".env"` chỉ trỏ tới file local của người dùng.

### Preflight phi nghiên cứu

```powershell
py -3.13 -X utf8 scripts/run_unified_bayes.py --preflight --technical-gates $technicalGates --readiness $executionReadiness --env-file ".env"
```

Cần thông báo `Preflight model/options/schema PASS`. Prompt này kiểm model
Decision/options/schema, không tạo một điểm nghiên cứu hoặc kiểm model thị
giác bằng lời gọi mới. Development dùng upstream W8/W9 đã kiểm; repeats
không chạy lại vision. Preflight có UUID/signature riêng, không nhập vào
sample/telemetry nghiên cứu. Preflight đã complete dùng lại durable result;
nếu bị ngắt thì chạy lại **chính lệnh preflight**, không thêm `--resume`.

### Primary và report

```powershell
# Mở journal hiện hữu, giữ đúng receipt/readiness đã khóa bằng adapter vận hành.
py -3.13 -X utf8 tools/resume_unified_bayes.py --run --resume --env-file ".env"
# Ba lệnh sau offline; không truyền gate/readiness/env-file cho các mode này.
py -3.13 -X utf8 scripts/run_unified_bayes.py --verify-only
py -3.13 -X utf8 scripts/run_unified_bayes.py --report
py -3.13 -X utf8 scripts/run_unified_bayes.py --verify-report
```

Adapter chỉ mở run đã có cohort/journal và preflight complete. Nó dùng hai
đường receipt/readiness ở mục 2 làm mặc định, giữ mọi guard/dispatch của CLI
cũ; ghi hash adapter riêng trước Decision HTTP. Không dùng lại lệnh online
`scripts/run_unified_bayes.py --run --resume` cho run đã có slot tiến triển:
entrypoint cũ vẫn truyền `create=True`, dẫn đến lỗi identity khi cố khởi tạo
lại slot complete/unknown. Kernel mở journal với `create=False` đã có sẵn;
adapter bổ sung cách gọi đúng, không thay code/plan/receipt đã khóa.

`--run` cũng kiểm preflight; complete không phát lại HTTP. Sau primary cần
`primary=COMPLETE`, `repeat=INCOMPLETE`. Mọi nhánh/điểm phải đủ; lỗi hoặc
unknown không trở thành CASH. `--verify-only` dựng snapshot/journal/usage;
`--report` mới refresh report dẫn xuất, `--verify-report` so bản lưu với bản
tái dựng. Snapshot/report có thể tính payoff sau khi mọi nhánh LLM của điểm
đã complete; đó là pha đánh giá, không đưa nhãn vào prepared prompt.

### Ba repeat đã khóa và duplicate độc lập

```powershell
py -3.13 -X utf8 tools/resume_unified_bayes.py --run --resume --repeats --env-file ".env"
py -3.13 -X utf8 scripts/run_unified_bayes.py --verify-only
py -3.13 -X utf8 scripts/run_unified_bayes.py --report
py -3.13 -X utf8 scripts/run_unified_bayes.py --verify-report
```

`--repeats` chạy cả r=1,2,3, chỉ khi toàn primary complete; CLI không có cờ
chọn repeat thuận lợi. Cần primary/repeat đều COMPLETE sau bước này. Primary
giữ r=0, không vote hoặc trộn repeat vào mẫu chính. Duplicate luôn độc lập;
prior-off chỉ reuse Original cùng point/repeat khi toàn canonical body trùng.
Số HTTP thực khác 516 slot logic do shared-off, retry và preflight.

## 4. Dừng, ngắt và resume

| Tình huống | Cách xử lý trong cùng run |
| --- | --- |
| Ctrl+C/lỗi I/O giữa point | Giữ run, cache, journal và ledger; chạy lại đúng lệnh primary hoặc repeats với `--resume` |
| Unknown có response/cache durable | Kernel đối soát raw HTTP và phục hồi cùng UUID; không xóa response để gọi lại |
| Unknown chưa có response | Retry theo policy hiện hữu, cùng UUID và audit; có thể có HTTP mới, không tạo repeat khoa học mới |
| 429/503/transient | Wrapper/pacer giữ backoff/retry-after và admission ledger; nếu dừng thì resume cùng identity sau khi điều kiện cho phép |
| Auth/daily quota | Giữ checkpoint/usage, giải quyết credential/quota trong cùng binding; đổi key không reset usage hay quyền scientific attempt |
| Hai format attempt đều sai | Dừng để review lỗi; không xóa attempts, ép output thành CASH hoặc tự cho phép attempt thứ ba |
| Source/code/model/schema/receipt hoặc ledger integrity sai | Dừng, đối chiếu bản nguồn đã khóa; không sửa hash/JSON để verifier nhận dữ liệu khác |
| Report stale sau ngắt | Verify journal trước, rồi `--report`, sau đó `--verify-report`; report không thay journal làm nguồn tin |
| Khóa đang do process sống giữ | Không xóa lock hoặc chạy process thứ hai; giữ owner/handle và để runtime đối soát cơ chế khóa |

Sau khi `authorization.json` đã khóa, giữ **cùng** technical receipt và
readiness; CLI đối soát amendment với usage trước HTTP. Không chạy lại gate
để thay receipt trong run đang nghiên cứu, không reset/xóa ledger, chuyển run
hoặc đổi model để vượt lỗi. Thay đổi hành vi sau action phải review revision
và khai báo exploratory, không ghi đè rồi gọi là lượt đầu tiên.

Khi hết quota và cần dùng credential khác, thực hiện **từng bước**, chờ lệnh
trước kết thúc. Nếu tiến trình vẫn đang chờ/retry thì không mở tiến trình thứ
hai. Sau khi đã dừng:

1. Mở `.env` bằng trình soạn thảo local, sửa `GROQ_API_KEY` và lưu file.
   Không gửi key vào chat hoặc đặt giá trị key trong câu lệnh.
2. Nếu đang chạy primary, chỉ chạy một lệnh sau:

   ```powershell
   py -3.13 -X utf8 tools/resume_unified_bayes.py --run --resume --env-file ".env"
   ```

3. Nếu đang chạy repeat, dùng lệnh tương ứng có `--repeats` ở mục 3.
   Các slot complete được giữ nguyên; slot unknown phục hồi cùng UUID và
   audit. Đổi key không xóa usage cũ hoặc bảo đảm provider cấp quota mới.
4. Chỉ khi primary hoặc repeat kết thúc mới chạy lần lượt `--verify-only`,
   `--report`, `--verify-report` ở mục 3. Nếu dừng do lỗi integrity hoặc lỗi
   format đã hết attempts, giữ nguyên run để rà soát, không tạo run mới.

## 5. Đầu ra chuyển sang phân tích U11

Bàn giao nguyên run/HTTP cache/journal/authorization/preflight, ledger chung,
plan/source/input/readiness và cả thư mục validation đã dùng. `report.json`
phải vừa được refresh và verify; báo planned/complete/unknown và common
support thực, từng mã, G/T, prior-off, repeat/duplicate và failure. Trace ID
là telemetry; `nomination_allowed=false` trong report runtime không phải
field để sửa tay. Nomination U11-03 đã có producer/consumer riêng; kiểm lại
quyết định khóa mà không gọi API:

```powershell
py -3.13 -X utf8 tools/nominate_unified_bayes.py
```

Chỉ U_full được xét nomination theo protocol. Thiếu support hoặc trượt gate
kinh tế thì dừng release xác nhận; không chọn ablation thắng để thay ứng viên.
Giá thực thi 2025 đã PASS ở bước bổ sung nguồn, nhưng vẫn cần nomination,
exposure/independence audit, lịch và release U11-04. CLI bàn giao ở đây chỉ
chạy development; chưa có lệnh release/run xác nhận 2025 được phát hành.
Không đổi `--plan`/`--output-dir` hoặc đặt cờ tự nghĩ ra để mở năm khác.

## 6. Phạm vi chứng cứ

Các lệnh/flag được đối chiếu parser và code production. Run/resume/verify
đã được kiểm bằng SDK thật qua HTTP mock, failure/resume/leakage và lifecycle
nguồn thật trong U10-07–09; tại thời điểm bàn giao W10 chưa gọi API thật.
U11-02 đã có API thật và hoàn tất primary/repeat bằng adapter resume; nghiệm
thu cuối ở README W11, không gán các test W10 cho adapter mới. Task chốt chỉ
đổi tài liệu và kiểm offline, không chạy lại suite hoặc gọi API mới.
Bốn gate U10-09 là compileall, 1111 unit, E2E và 248 leakage PASS đúng nguồn/
runtime. U10-10 chỉ bàn giao tài liệu, giữ code/schema/input/runtime nguyên
byte nên viện dẫn gate đó, không ghi là đã chạy lại suite.
