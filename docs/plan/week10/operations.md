# Vận hành cohort Bayesian ICL revision

Hướng dẫn cho CLI [`scripts/run_bic_icl.py`](../../../scripts/run_bic_icl.py),
đối chiếu mã đã nghiệm thu tại `258d650`, Python **3.13.5**.
[Tiến độ và bằng chứng W10](README.md) · [Protocol v1](method_protocol_v1.md) ·
[Bàn giao W11](../week11/README.md#đầu-vào-đã-bàn-giao-từ-w10)

## 1. Trạng thái bàn giao và các đường dẫn

Các lệnh offline bên dưới dùng được ngay trong workspace có đủ artifact.
Producer plan, runtime, loader, verifier và consumer release đã triển khai.
**W11-01 còn phải phát hành release development** gắn đúng upstream/request/
repeat sau kiểm nguồn. Hiện chưa có run hoặc release revision thật.
Người dùng chạy API sau bước đó; W10-08 chỉ chuẩn bị và kiểm offline.

| Artifact | Đường dẫn từ root | Vai trò |
| --- | --- | --- |
| Plan đã khóa | `outputs/bayesian_benchmark/bic_icl_v2/development_plan_v1.json` | 60 điểm development 2023, `VERIFIED_CACHE`, tiếng Việt |
| Run dự kiến | `outputs/bayesian_benchmark/bic_icl_v2/development_run_v1` | Một thư mục cho primary và cả ba repeat; hiện chưa tạo |
| Memory/index | `outputs/bayesian_benchmark/bic_icl_v2/memory_v1/` | 976 episode, cùng nguồn cho A/R/Numeric |
| Train/context | `outputs/bayesian_benchmark/bic_icl_v2/train_v1/`, `context_v1/` | Lambda=8, diagnostics và evidence/prompt offline |
| Receipt gate | `docs/plan/week10/validation_gates/revision_v1/technical_gates.json` | Consumer đọc bốn log đi kèm, bind 85 dependency/runtime |
| Source freeze | `docs/plan/week10/validation_gates/revision_v1/source_freeze.json` | Plan/nguồn/runtime và 271 tệp thuộc phạm vi gate |
| Bằng chứng nghiệm thu | `docs/plan/week10/validation_gates/revision_acceptance_v1.zip` | Source, log/inventory, metadata và fixture; không phải run thực nghiệm |
| Ledger provider chung | `outputs/oos_pilot/api_usage.json` | Lịch sử quota/HTTP dùng chung qua các namespace |

Memory, plan, nguồn W9 và phần lớn `outputs/` là **ignored**: clone Git riêng
không đủ để tái lập. Giữ workspace cùng archive W9, dữ liệu giá/quyền/tin,
model/scaler/index, cache tokenizer, ledger và response cache. Ledger path
tuyệt đối được bind vào run; chuyển máy/thư mục cần đối soát identity trước
khi tiếp tục. Kiểm checksum archive trước phục hồi vào vùng riêng.

## 2. Cấu hình được pin

| Thành phần | Giá trị từ plan/protocol |
| --- | --- |
| Decision và các agent văn bản | `openai/gpt-oss-20b`, temperature=0, max_tokens=2048, reasoning low/hidden |
| Agent ảnh | `qwen/qwen3.8-27b`, temperature=0, max_tokens=1024, reasoning none/hidden |
| Client | SDK max_retries=0, service_tier=`on_demand`; retry qua wrapper/transport hiện hữu |
| Input | `vi`, `1d`, window=45, `zscore_tanh`, alpha_weights=None |
| Chính sách | Risk OFF; schema Decision legacy; SHORT=CASH |
| Budget | BRPP≤600 ký tự; toàn prompt Decision<6.500; giữ distill/cap |

Đây là cấu hình nguồn đã khóa, chưa chứng nhận provider còn phục vụ model
hoặc còn quota. Preflight thực kiểm cả text/vision trước run. Model không
còn khả dụng phải dừng để xử lý revision và gate tương ứng; không thay
model, ngôn ngữ, seed hoặc prompt giữa cohort. Không cần sửa `.env` cho
bất kỳ lệnh offline nào; lệnh online đọc `GROQ_API_KEY` từ `--env-file`
(mặc định `.env`), sau đó mới fallback biến môi trường.

## 3. Kiểm offline trước API

Chạy từ root repository bằng PowerShell:

```powershell
py -3.13 -X utf8 scripts/run_bic_icl.py --help
py -3.13 -X utf8 scripts/run_bic_icl.py --prepare
py -3.13 -X utf8 scripts/run_bic_icl.py --dry-run
py -3.13 -X utf8 scripts/run_bic_icl.py --economic-fixture
```

`--prepare` ghi một lần; file đã có chỉ nhận đúng cùng payload, không ghi
đè hoặc đổi timestamp. Không chọn mode thì CLI mặc định dry-run.
Dry-run cache dựng lại đủ 60 packet, ma trận, coverage và mẫu repeat,
trả `status=PASS`, `decision_calls=0`, `fresh_requests_pending=false`.
Nó không ghi `context_lock.json` vào run; W11-01 còn phải đóng băng các
packet/request/lock thực được release tham chiếu. Fixture kinh tế trả
PASS cho bốn chuỗi LONG/CASH tổng hợp, không là kết quả development.

Kiểm receipt gate cùng source/runtime hiện tại:

```powershell
@'
from pathlib import Path
from core.bic_icl_protocol import CohortSources
from core.candidate_selection import read_technical_gates
from core.research_cohort import read_envelope
plan = read_envelope(Path("outputs/bayesian_benchmark/bic_icl_v2/development_plan_v1.json"))
CohortSources().validate(plan)
print(read_technical_gates(Path("docs/plan/week10/validation_gates/revision_v1/technical_gates.json"), plan)["status"])
'@ | py -3.13 -X utf8 -
```

Kết quả mong đợi: `PASS`. Việc đọc receipt xác minh bằng chứng W10-07;
không chạy lại compileall/unit/E2E/leakage. Nếu source/runtime khác thì
receipt cũ không áp dụng cho hành vi mới.

## 4. Khóa upstream và release tại W11-01

`--upstream` chỉ có hiệu lực khi **prepare plan**. Run/dry-run lấy policy
từ plan; truyền `--upstream FRESH_SHARED` cho run không đổi policy của plan.
Cache và fresh là lựa chọn cho **cả cohort**, khóa trước Decision.

| Policy | Quy trình |
| --- | --- |
| `VERIFIED_CACHE` hiện tại | Verifier kiểm Full/journal/source của đủ 60 upstream lịch sử; chỉ dùng upstream, không lấy action Decision cũ. Khóa packet/request/context/repeat rồi cấp release có digest context lock. |
| `FRESH_SHARED` nếu W11 chọn | Tạo plan mới `development_plan_fresh_v1.json` và run mới. Dry-run trả `fresh_requests_pending=true`, lock=null. Cấp release upstream-only (`decision_context_lock_sha256=null`), preflight, chạy `--lock-upstream`; sau đó verifier kiểm và cấp release Decision riêng có digest context lock. |

Nếu cần chuẩn bị phương án fresh, dùng tên mới ngay dưới namespace:

```powershell
py -3.13 -X utf8 scripts/run_bic_icl.py --prepare --upstream FRESH_SHARED --plan outputs/bayesian_benchmark/bic_icl_v2/development_plan_fresh_v1.json
py -3.13 -X utf8 scripts/run_bic_icl.py --dry-run --plan outputs/bayesian_benchmark/bic_icl_v2/development_plan_fresh_v1.json
```

Hai lệnh này là phương án có điều kiện, **chưa thực hiện khi bàn giao**.
Không ghi đè plan cache hoặc trộn hai nguồn theo outcome. `--lock-upstream`
cần release và preflight, chạy các stage Indicator/Pattern/Trend/Full có
journal; nó không phải lệnh offline. Nếu bị ngắt, chạy lại đúng plan/run
bằng `--lock-upstream --resume`. Sau khi lock-upstream tạo run, lần Decision
đầu dùng `--run --resume` để tiếp tục run đó.

Mẫu fresh sử dụng hai release theo từng giai đoạn: W11-01 cấp release
upstream trước preflight, rồi cấp release Decision sau khi verify lock.
Thay các đường dẫn dự kiến bằng artifact thực, thực hiện theo thứ tự:

```powershell
$planPath = 'outputs/bayesian_benchmark/bic_icl_v2/development_plan_fresh_v1.json'
$runPath = 'outputs/bayesian_benchmark/bic_icl_v2/development_run_fresh_v1'
$gatePath = 'docs/plan/week10/validation_gates/revision_v1/technical_gates.json'
$upstreamReleasePath = 'docs/plan/week11/development_upstream_release_v1.json'
$releasePath = 'docs/plan/week11/development_fresh_release_v1.json'

py -3.13 -X utf8 scripts/run_bic_icl.py --preflight --plan $planPath --output-dir $runPath --handoff $upstreamReleasePath --technical-gates $gatePath
py -3.13 -X utf8 scripts/run_bic_icl.py --lock-upstream --plan $planPath --output-dir $runPath --handoff $upstreamReleasePath --technical-gates $gatePath
# Chỉ chạy sau khi verifier đã khóa context và cấp release Decision.
py -3.13 -X utf8 scripts/run_bic_icl.py --run --resume --plan $planPath --output-dir $runPath --handoff $releasePath --technical-gates $gatePath
```

Release `bic_icl_development_release_v1` là envelope đã được producer/verifier
W11-01 kiểm, bind `plan_sha256` (digest payload), `technical_gates_sha256`
(hash byte receipt), `upstream_policy`, `code_sha256`, `runtime`,
`decision_context_lock_sha256` và `confirmation_allowed=false`.
Không tự viết JSON hoặc băm lại để vượt điều kiện nguồn/request. CLI hiện
**chưa có mode tạo release**, selection hoặc xác nhận 2025.

## 5. Preflight, primary và repeat sau release

Các lệnh trong mục này là mẫu vận hành **sau W11-01**. Biến `$releasePath`
phải trỏ tới artifact W11-01 thực sự phát hành; đường dẫn dưới đây là tên
dự kiến, chưa có file tương ứng. Giữ plan/run/ledger và credential cùng identity.

```powershell
$planPath = 'outputs/bayesian_benchmark/bic_icl_v2/development_plan_v1.json'
$runPath = 'outputs/bayesian_benchmark/bic_icl_v2/development_run_v1'
$gatePath = 'docs/plan/week10/validation_gates/revision_v1/technical_gates.json'
$releasePath = 'docs/plan/week11/development_release_v1.json'

py -3.13 -X utf8 scripts/run_bic_icl.py --preflight --plan $planPath --output-dir $runPath --handoff $releasePath --technical-gates $gatePath
py -3.13 -X utf8 scripts/run_bic_icl.py --run --plan $planPath --output-dir $runPath --handoff $releasePath --technical-gates $gatePath
```

Mẫu trên áp dụng cache với run chưa khởi tạo. Preflight tạo hai request nhỏ
text/vision, ghi quota/usage; cần PASS cùng credential và plan. `--run`
khởi tạo primary rồi mới gọi Decision. Lệnh kết thúc bình thường trả
`status=COMPLETE`, `repeat_id=0`, ghi `report_0.json`.
Kiểm primary trước repeat theo mục 6. Khi cần phục hồi primary:

```powershell
py -3.13 -X utf8 scripts/run_bic_icl.py --run --resume --plan $planPath --output-dir $runPath --handoff $releasePath --technical-gates $gatePath
```

Sau khi primary complete đã verify, chạy **từng lượt** r=1,2,3:

```powershell
py -3.13 -X utf8 scripts/run_bic_icl.py --run --resume --repeat-id 1 --plan $planPath --output-dir $runPath --handoff $releasePath --technical-gates $gatePath
py -3.13 -X utf8 scripts/run_bic_icl.py --run --resume --repeat-id 2 --plan $planPath --output-dir $runPath --handoff $releasePath --technical-gates $gatePath
py -3.13 -X utf8 scripts/run_bic_icl.py --run --resume --repeat-id 3 --plan $planPath --output-dir $runPath --handoff $releasePath --technical-gates $gatePath
```

Cả ba dùng cùng run root, upstream và mẫu 12 điểm đã khóa; các block nằm
ở `decision_blocks/1`, `/2`, `/3`, report tương ứng `report_1/2/3.json`.
Numeric chỉ ở primary. Duplicate Original có invocation độc lập mỗi
point/repeat. Tối đa 480 slot primary +324 slot repeat LLM; alias/shared-off
làm số HTTP thật nhỏ hơn, retry có thể làm số HTTP tăng. Dùng ledger để
đếm HTTP, không lấy số nhánh logic hoặc số lượt khoa học thay thế.

## 6. Verify và điều kiện nghiệm thu run

Chỉ dùng các lệnh sau khi run tương ứng đã có, giữ ledger tại đường dẫn
chung mặc định. Không cần `--handoff`, `--technical-gates` hoặc API key
cho verify. Cài transport từ chối mạng; metadata lock có thể được cập nhật.

```powershell
py -3.13 -X utf8 scripts/run_bic_icl.py --verify-only --plan $planPath --output-dir $runPath
py -3.13 -X utf8 scripts/run_bic_icl.py --verify-report --plan $planPath --output-dir $runPath
py -3.13 -X utf8 scripts/run_bic_icl.py --verify-only --repeat-id 1 --plan $planPath --output-dir $runPath
py -3.13 -X utf8 scripts/run_bic_icl.py --verify-report --repeat-id 1 --plan $planPath --output-dir $runPath
```

Lặp hai lệnh repeat verify với `--repeat-id 2`, rồi `3`.
Không truyền `--resume` khi verify; CLI từ chối tổ hợp đó.
`--verify-only` dựng lại trạng thái từ checkpoint/source/cache/ledger,
không tạo report mới. Run dở có thể trả `INCOMPLETE`: exit 0 riêng lẻ
không chứng nhận đủ dữ liệu. `--verify-report` còn so toàn payload report
đã lưu với kết quả dựng lại, không sửa hoặc ghi đè report sai/thiếu.

Primary đủ khi có 60 point đúng lịch, 12 FPT và 16/mã còn lại, đúng ma trận
đã khóa, mọi point có evaluation/common support và không unknown/error.
Repeat đủ khi mỗi r có 12 point, đúng sample/order/request, duplicate riêng,
không Numeric mới; primary vẫn nguyên byte sau cả ba lượt. W11 phân tích
và selection từ những artifact đã verify, không từ dòng console đơn lẻ.

## 7. Dừng, phục hồi và xử lý lỗi

| Tình huống | Cách tiếp tục |
| --- | --- |
| Ctrl+C, timeout hoặc mất kết nối | Giữ nguyên run/ledger/cache, chạy `--run --resume` cùng repeat ID. Wrapper phục hồi cùng UUID; response durable được dùng trước HTTP. |
| 429 giới hạn phút hoặc lỗi tạm thời | Transport chờ Retry-After/backoff đã khóa; không chạy thêm tiến trình để né quota. |
| Provider báo hết quota ngày | Dừng và giữ checkpoint, tiếp tục khi provider cho phép. Không reset ledger hay đổi namespace để tạo ngân sách mới. |
| Đổi credential khi cần | Giữ ledger/run, preflight lại cùng plan với credential mới, rồi resume; không sửa fingerprint/historical usage. |
| Unknown không có response durable | Recovery có thể retry cùng UUID và ghi audit; request trước có thể đã tới provider. Không cam kết exactly-once HTTP trong tình huống này. |
| Mất marker/cache, source/model/runtime/request khác hoặc schema sai | Dừng kiểm integrity; không xóa checkpoint, điền CASH, tạo lại marker hay sửa checksum để chạy tiếp. |
| Process khác giữ lock | Chờ tiến trình sở hữu kết thúc và kiểm trạng thái; không xóa lock khi nó còn hoạt động. |

CLI revision không có `--reconcile` hoặc `--authorize-replay` của runner
legacy. Không áp dụng các flag đó cho `run_bic_icl.py`. Report primary và
repeat ghi một lần; khi lỗi sau khi report đã lưu, giữ bằng chứng và xử lý
revision theo protocol nếu cần thay hành vi, không chọn kết quả mới thuận lợi.

## 8. Điểm bàn giao khoa học

Cache hiện có `task_enabled=true` về kỹ thuật, nhưng
`task_coverage_eligible=false`: chỉ ba điểm có ≥2 task, FPT=0. Ma trận dry-run
vẫn gồm tám nhánh LLM; coverage thiếu không tự biến thành lỗi budget hoặc
đủ điều kiện đề cử. W11 phải giữ bằng chứng này và ngưỡng ≥6, ≥1/mã.
R_task bị BLOCKED kỹ thuật mới loại cả ba ID trước rotation theo runtime.

W10-07 đã nghiệm thu bốn gate và dry-run/fixture; W10-08 không gọi API.
W11-01 khóa upstream/request/repeat và release development; W11-02/03 do
người dùng chạy primary/repeat. Xác nhận 2025 còn selection, source,
bootstrap/manifest/release riêng tại W11-05–07. Xem
[chương phương pháp](methodology_chapter.md) để giữ đúng estimand và giới hạn claim.
