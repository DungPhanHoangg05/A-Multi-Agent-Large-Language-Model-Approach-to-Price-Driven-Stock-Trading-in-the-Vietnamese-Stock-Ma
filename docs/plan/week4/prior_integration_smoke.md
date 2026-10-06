# W4-14 — Smoke E2E offline và tương thích

**W4-14 hoàn thành ngày 06/10/2026; Phase D 2/4, W4 14/16.**
[Receipt smoke và bốn gate mới](integration_smoke.json); nhánh `test/prior-integration-smoke`.
Kế hoạch: [Phase D](phase_d_validation_handoff.md), [checklist W4](README.md).

## Phạm vi triển khai

Thêm `scripts/verify_prior_integration.py` và bốn test cho công cụ kiểm chứng.
Giữ nguyên E2E legacy `scripts/run_end_to_end_test.py`, các module production,
API cũ, bảy hàm kinh tế/entry point, kho 852 episode và bằng chứng đã đóng băng.

Smoke chạy loader/validator giá, model/regime, kho/QA, PIT adapter, chỉ báo,
ảnh K-line/trend, Alpha Selector, LangGraph, retriever/ranking/stats, formatter,
Decision builder, checkpoint/khóa OS/resume và đánh giá kinh tế thật.
Pattern/Trend dùng vision giả; Decision dùng binding structured và raw JSON
xác định, action trong hai response khớp nhau. Indicator backtest tự dựng
báo cáo Python, **không gọi LLM diễn giải**.

Network/DNS, requests/httpx, ChatGroq, fit detector và crawl bị chặn. Guard còn
đếm lần chạm để phát hiện trường hợp code bắt rồi bỏ qua lỗi ngoại vi.
Các lượt chạy dùng thư mục tạm; không đọc credentials hoặc thay checkpoint W2.

## Smoke bắt buộc tái lập từ Git

Tái dùng nguồn fixture tại `tests/prior_context_test_support.py`. Script dựng
OHLCV/evidence/manifest/tin/kho nhỏ riêng trong thư mục tạm; chuẩn hóa timestamp
gzip để các hash nguồn lặp lại ổn định. Bốn đường VNINDEX tổng hợp có xu hướng
tăng, giảm, biến động cao và đi ngang. Artifact tổng hợp khai không hội tụ,
`UNVERIFIED/RESEARCH_ONLY`; loader và detector thật kiểm prefix/train/calibration
rồi phân loại bằng fallback đã chốt. Không patch state regime hoặc chạy fit.

| Coverage | Kiểm chứng |
| --- | --- |
| 4 regime × VI/EN | 8 context; BULL, BEAR, CHOPPY, CONSOLIDATION |
| 5 nhánh public | Original/Random/Recent/Similarity/Bayesian; K=0/3, seed=42, same_symbol, Full, daily |
| Eligible 0/1/2/3 | Empty, partial và complete; giữ một episode chưa đóng để kiểm cutoff |
| K=1/2 bổ sung | 64 Decision qua graph thật, đủ bốn mode trên Full đã seal; không đổi ma trận public |
| Continuous/đảo nhánh/crash-resume | Reports, task IDs, stats, metadata, BRPP, prompt và output Decision khớp |
| Call-count | Mỗi lượt mới: Indicator 1, vision 2, Full/Alpha 1, Decision 5 |
| Resume | Ngắt sau `branch_complete:random`; chỉ 3 Decision còn thiếu, không chạy lại upstream/Full |
| Resume complete | 0 Decision mới; byte point checkpoint complete giữ nguyên |
| Kinh tế/JSON | Giá Open(t+1)/Close(t+3), LONG trừ phí/slippage hai chiều, SHORT cash; schema/hash và JSON finite |

Mỗi context có 15 Decision cho continuous/đảo nhánh/crash-resume; tổng 120,
cộng 64 Decision K=1/2. Checkpoint real ghi identity/manifest/shared/input/attempt
và từng nhánh, sau đủ năm nhánh mới chấm outcome bằng engine hiện có.
So sánh loại riêng UUID/timestamp/latency vận hành; các field khoa học giữ
nguyên. Hai nhánh complete giữ nguyên toàn bộ field, gồm attempts và response.

## Flag off và biên ngân sách

Smoke kiểm bốn ablation cũ qua `_run_ablation_variants()` và `set_graph()`,
cặp `_run_paired_point()`, alias `compile_decision(include_alpha=...)` và
`compile_report_decision(prior_off)`. Sau dựng fixture, guard cấm constructor
adapter/retriever, load bank/model trong đường runtime flag off. E2E legacy
kiểm thêm `BacktestEngine.run()` riêng trong bốn gate.

Formatter thật sinh BRPP **đúng 600 ký tự** bằng fixture ngân sách riêng;
builder/cap runtime giữ nguyên. VI/EN nhận prompt **6.499**, chặn **6.500**
trước LLM. Fixture padding và hook prefix ở phép đo biên chỉ kiểm ngân sách,
không được gọi là context thị trường PIT. Context end-to-end đã có kiểm nguồn
thật và không dùng hook này.

## Replay bổ sung từ dữ liệu quan sát

Xác minh lại kho 852 record, manifest/QA, giá thực thi VCI, snapshot tin,
VNINDEX/model prefix đúng ngày, run/episode/signals journal W2 và signature.
Tái dùng Full reports lịch sử, chạy retriever/formatter/graph/Decision giả mới;
không gọi lại vision hoặc Alpha của lượt sinh bank.

Sáu context: FPT/MWG/VCB/VNM ngày 2022-12-27, FPT ngày 2020-06-04 và
2022-03-04. Có 30 nhánh riêng, 60 Decision khi kiểm cả thứ tự đảo. Độ phủ
thực của replay này là **BEAR 4, CONSOLIDATION 2**, bốn mã; không tuyên bố
replay này phủ cả bốn regime. Bốn regime đủ trong smoke tổng hợp riêng.

Nếu thiếu archive/proof local, receipt ghi replay `BLOCKED` và đường dẫn thiếu;
smoke tổng hợp vẫn có trạng thái riêng. Checksum/provenance sai gây lỗi cả
verifier, không được đổi thành BLOCKED hoặc thay bằng fixture. Bốn test mới
kiểm nguồn tổng hợp tái lập/bốn regime, thiếu archive, proof sai và lỗi network
bị bắt rồi bỏ qua.

## Chạy lại bằng terminal

Từ thư mục gốc repo; chọn đường dẫn receipt mới chưa tồn tại:

```powershell
$smokeReceipt = Join-Path $env:TEMP ("prior-smoke-" + [guid]::NewGuid().ToString("N") + ".json")
py -3.13 -X utf8 scripts/verify_prior_integration.py --output $smokeReceipt
```

Clone chỉ có file Git, hoặc muốn chủ động chỉ kiểm smoke tổng hợp:

```powershell
py -3.13 -X utf8 scripts/verify_prior_integration.py --skip-observed
```

Không truyền `--output` thì chỉ kiểm và in tóm tắt, không ghi receipt mới.
Script từ chối ghi đè file đã tồn tại. Receipt ghi config/source/hash/version,
call-count, budget, phạm vi mock, kết quả tổng hợp và replay riêng.

## Kết quả nghiệm thu

| Lượt kiểm mới | Kết quả | Thời gian subprocess |
| --- | --- | --- |
| integration_smoke | PASS, mã thoát 0 | 229.375 giây |
| compileall | PASS, mã thoát 0 | 0.263 giây |
| unit | PASS, mã thoát 0 | 547.511 giây |
| e2e | PASS, mã thoát 0 | 31.182 giây |
| leakage | PASS, mã thoát 0 | 169.979 giây |

- **498 unit, 93 leakage**; bốn test mới đều xuất hiện PASS trong log unit.
- Context tổng hợp: max prompt **4193**, BRPP **363**; biên riêng 600/6499/6500 PASS.
- Replay bổ sung **PASS**, giữ hash kho/manifest/QA; bank SHA-256
  `09b48c6192a092b562173e8b3b7eceb44025c6e02454093e34214a730a460949`.
- **2423 file bảo vệ** giữ nguyên byte trước/sau, gồm nguồn/model/kho/archive/QA,
  receipt/spec cũ; bảy AST kinh tế/legacy giữ nguyên. Không sửa module production.
- Receipt ghi commit nền, nhánh, Python 3.13.5, hash code/log/nguồn, mock/config/provenance,
  stdout/stderr/mã thoát/thời gian. Log và snapshot danh sách file tại thư mục TEMP
  được ghi trong receipt; receipt trong Git giữ tóm tắt và hash, không chứa key/checkpoint tạm.
- Thời gian này là smoke/gate tổng hợp, **không phải p95 retrieval** hoặc benchmark pilot.

## Giới hạn và bước tiếp theo

Đây là nghiệm thu kỹ thuật offline; Decision giả không chứng minh hiệu quả đầu
tư hoặc độ chính xác ngoài mẫu. Tin W2 thiếu coverage vẫn NEUTRAL. Replay dùng
model prefix lịch sử; không mở gate giá OOS/pilot, không fit model mới hoặc sinh
lại bank. W4-15 tiếp tục rà phạm vi/hash/overhead và gate nghiệm thu; W4-16 mới
đóng tuần, bàn giao W5. Gate D chỉ đóng sau đủ các task tương ứng.
