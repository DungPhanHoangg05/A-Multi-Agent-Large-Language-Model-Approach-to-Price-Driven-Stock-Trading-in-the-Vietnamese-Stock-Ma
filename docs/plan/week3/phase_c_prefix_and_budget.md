# Phase C — BRPP và ngân sách prompt

**Trạng thái: W3-10/W3-11/W3-12 hoàn thành; Phase C/Gate C offline PASS. Ngân sách runtime tích hợp vẫn thuộc W4.**
Formatter nằm trong `core/bayesian_retriever.py`, test `tests/test_bayesian_prior_prefix.py`,
biên bản [formatter](prefix_formatter_review.json). W3-11 có test
`tests/test_bayesian_prompt_budget.py`, script `scripts/verify_prior_prompt_budget.py`
và [receipt ngân sách](prompt_budget_review.json). W3-12 có script
`scripts/verify_bayesian_prior.py`, test `tests/test_bayesian_prior_smoke.py`
và [receipt smoke kho thật](prior_smoke.json).

Template, schema metric và các trường hợp biên đã khóa tại
[W3-04](statistics_and_prefix_contract.md), [policy](statistics_prefix_policy.json).
Receipt Phase A kiểm mẫu tham chiếu ≤600, chưa thay test formatter/runtime hoặc
prompt ghép thực tế trong các task bên dưới.

**Blocker tích hợp đã xác minh ở W3-11:** cap báo cáo hiện tại tổng 4.500 cho
prompt ghép BRPP 397 ký tự dài 6.565 VI / 6.582 EN; không đạt `<6500`.
Log trần 7.500 hiện tại không phải guard theo `AGENTS.md`. Phương án cap tổng
4.000 đã PASS offline, chưa áp dụng runtime. W4 phải áp dụng cap này (hoặc kiểm
chứng phương án thay thế) và guard `<6500` sau khi thêm toàn bộ hướng dẫn/BRPP.

## W3-10 — định dạng compact

- [x] Cài `format_compact_prior_prefix(tasks, stats)` theo template đã khóa.
- [x] Có regime, số mẫu hỗ trợ, thống kê đúng mẫu số và tối đa ba ví dụ ngắn với
  tín hiệu/nhãn LONG ròng. IDs đầy đủ ở metadata, không bắt buộc nhồi toàn bộ provenance vào prompt.
- [x] Dùng tên/code hướng có bảng chú giải; không cắt chuỗi tùy tiện làm mất dấu lợi nhuận,
  mẫu số, nhãn kết quả hoặc đổi SHORT thành bán khống.
- [x] Thiếu mẫu ghi đúng số thực tế; K=0/Original trả prefix rỗng; n=0 không bịa thống kê.
- [x] Cảnh báo thiếu tin thể hiện đúng nghĩa khi dùng sentiment; không diễn giải NEUTRAL
  trong kho là bằng chứng tin tức thị trường trung tính.

## W3-11 — giới hạn ký tự và prompt ghép thử

- [x] Kiểm `len(prefix) <= 600` cho K=1..3, các regime, số liệu cực trị hợp lệ,
  nhiều chữ số, tiếng Việt và input dài; với K>3 thực hiện đúng chính sách Gate A.
- [x] Không âm thầm truncate: rút gọn theo template đã khóa hoặc từ chối nếu vẫn vượt trần.
- [x] Kiểm việc render là xác định, không sửa tasks/stats; giá trị mơ hồ/NaN bị từ chối.
- [x] Dùng builder compact hiện có của Decision để ghép thử báo cáo fixture + BRPP:
  VI/EN **<6.500** với cap bàn giao 4.000; cap cũ 4.500 không đạt khi ghép BRPP.
- [x] Giữ `_distill_report`, `_cap_report`; chỉ test/ngân sách bàn giao, chưa inject
  BRPP vào runtime Decision/graph/backtest. Nếu fixture hợp lệ vượt trần, ghi blocker
  và phương án xử lý cụ thể trước khi chốt W3/W4.

## W3-12 — smoke trên kho thật, offline

- [x] Script nạp kho QA PASS, chọn truy vấn xác định trên bốn mã/bốn regime từ dữ liệu
  có sẵn; fixture/query lịch sử phải mang regime prefix PIT, không nhãn hồi cứu Panel A.
- [x] Có cutoff trước episode đầu, cutoff bằng exit, query thiếu K và query sau cuối kho.
  Không suy ra regime thực tế của ngày giả định nếu chưa có snapshot xác minh.
- [x] Chạy bốn mode, ghi bank hash/config/seed, IDs/dates, số mẫu, stats, score,
  lý do thiếu mẫu và prefix length; kiểm bằng cutoff ở từng task đầu ra.
- [x] Không gọi upstream/LLM, fit lại HMM, sinh episode hoặc tải giá mới; không ghi đè
  kho/manifest W2. Receipt chỉ chứa dữ liệu nghiên cứu, không key/.env.
- [x] Biên bản phân biệt smoke retrieval và benchmark giao dịch OOS; hạn chế dữ liệu
  vẫn được ghi rõ.

**Gate C:** prefix đủ nghĩa và ≤600, prompt ghép thử <6.500 với ngân sách bàn giao
đã kiểm, smoke bốn mode PASS với receipt tái lập. Chưa coi đây là hệ thống tích hợp
W4; cap cũ không được tái sử dụng nguyên trạng khi inject BRPP.
**Kết luận W3-12: Gate C offline PASS** theo các bằng chứng W3-10/11/12; không
chuyển `runtime_budget_gate_passed` thành true hoặc đóng điều kiện bàn giao W4.

## Kết quả và nhật ký

### 05/10/2026 — W3-12 hoàn thành, Phase C/Gate C offline PASS

- `scripts/verify_bayesian_prior.py` nạp kho/manifest/QA/schema đã chốt, đối chiếu
  signature archive W2 và checksum canonical records; validator/engine thật kiểm
  nhãn kinh tế với giá thực thi đã xác minh. Cold load giá một lần mỗi mã.
- 16 context chính: lấy episode mới nhất từng cặp mã/regime, không chọn bằng
  outcome. Tám context lịch sử biên: ngày bằng exit đầu (**2020-06-04**) và ngày
  có population cùng mã/regime thiếu K (**2020-06-12**). Đối chiếu envelope episode,
  tín hiệu COMPLETE, model/scaler/calibration prefix và artifact hash; chỉ nạp
  model có sẵn với `verify_only=True`, không fit lại. Snapshot giá/Alpha và ngày
  tin không vượt cutoff; báo cáo khớp checksum. Outcome của query không gửi vào API.
- Tám context fixture: trước episode đầu (**2020-05-31**) và sau exit cuối
  (**2022-12-31**) trên bốn mã. Regime CHOPPY và năm tín hiệu NEUTRAL cố định cho
  kiểm module; không dùng tín hiệu episode để suy ra trạng thái ngày giả định,
  không gán provenance prefix lịch sử cho fixture.
- **32 context; 288 query + 288 lượt lặp**: bốn mode × hai scope × K=3 cho mọi
  context; thêm Original K=0 cho 16 context chính ở hai scope. Bộ tham chiếu độc
  lập lọc `exit_date < cutoff`, tính counts bằng tập ID và đối chiếu thứ tự/score/
  seed Random. Stats luôn dùng toàn population PIT/cùng regime, không K ví dụ.
- **176 complete / 64 empty / 16 partial / 32 disabled**. Biên bằng exit loại
  toàn bộ episode chưa đóng; cùng mã thiếu K không bù mã khác, pooled chỉ hoạt
  động khi được yêu cầu. Empty vẫn render n=0/N/A; Original prefix rỗng. BRPP
  lớn nhất **373 ký tự trong các query đã kiểm**, không thay upper bound 600.
- Input không đổi, query lặp nhận cùng IDs/stats/prefix. Chặn socket kết nối mạng,
  `fit`, trích tín hiệu và runner sinh episode; chặn đọc JSON/giá trong query.
  Hash mọi file bằng chứng được dùng giữ nguyên trước/sau smoke. Receipt chứa
  query/config/versions/seed, nguồn PIT, IDs/dates, counts/score/stats/BRPP,
  hash kho/manifest/QA/giá/model/checkpoint và mã verifier.
- Sáu test mới PASS: kiểm coverage/cutoff/scope/n=0/Original/partial, nguồn lịch
  sử so với fixture, model/tin tương lai/báo cáo sửa/hash giá và kết quả sai cutoff/
  counts bị từ chối. Unit tests dùng kho/receipt đã commit và payload lỗi giả lập;
  không đòi archive local trong clone mới. Smoke thực tế được chạy bằng CLI.
- [Receipt](prior_smoke.json) **PASS**, liên kết hash với receipt ngân sách W3-11
  và kiểm nguồn của receipt đó còn khớp. **Gate C offline PASS**; W4 phải áp dụng
  cap/guard đã bàn giao, chưa inject runtime. W3-13..16 chưa thực hiện; p95 chưa đo.
  Kho 2020–2022/thiếu tin và gate giá kiểm định 2023–2024 vẫn giữ giới hạn; đây
  không phải bằng chứng hiệu quả giao dịch hoặc benchmark OOS.

Tái lập tại gốc repo (cần archive W2 đầy đủ cùng giá/VN-Index đã đóng băng):

```powershell
py -3.13 -X utf8 scripts/verify_bayesian_prior.py
py -3.13 -X utf8 -m unittest discover -s tests -p 'test_bayesian_prior_smoke.py' -v
```

Archive gồm run manifest, episodes, signals và regimes trong
`outputs/historical_memory_run/`, vốn bị gitignore; phải giữ bản sao nghiên cứu để
tái lập. Thiếu/sai bằng chứng dừng với lỗi, không chạy upstream/HMM để tạo thay thế.
Bốn gate tích hợp W3-12 PASS: compileall; **318/318** unit tests (96,853 giây);
E2E xác định (13,7 giây); **46/46** leakage tests (6,645 giây). Hash nguồn và 76
file bằng chứng còn khớp receipt; liên kết Markdown và `git diff --check` PASS.
Nhánh `test/offline-prior-smoke` commit/merge sau gate theo `AGENTS.md`.

### 05/10/2026 — W3-11 hoàn thành

Chín test mới và script đo dùng formatter/builder compact thật; ghép BRPP ngay
trước báo cáo đầu tiên. K=0/Original không thêm ký tự. Fixture daily `1d` và
`1 ngày` đều xác nhận T+2.5 / ba phiên, LONG mua Open rồi bán Close, SHORT giữ
tiền mặt và đầy đủ phí/trượt giá. Không chạy node Decision hoặc gọi API.

| Báo cáo | Cap hiện tại | Cap bàn giao đã kiểm |
| --- | ---: | ---: |
| Trend | 900 | 800 |
| Pattern | 900 | 800 |
| Indicator | 900 | 800 |
| Alpha | 1.200 | 1.100 |
| Sentiment | 600 | 500 |
| Tổng | 4.500 | 4.000 |

- Báo cáo fixture bão hòa làm rõ blocker: BRPP 397 + cap hiện tại cho prompt
  VI **6.565**, EN **6.582**, đều không đạt `<6500`. Không sửa pipeline để xử lý
  trong W3-11; phương án W4 dùng cùng hàm distill/cap với ngân sách trong bảng.
- Phương án đo bằng cap patch tạm thời rồi khôi phục: **1.024 ca** = hai ngôn ngữ
  × hai alias daily × bốn mã × bốn cấu hình Alpha/Sentiment × bốn regime × K=0..3.
  Prefix lớn nhất trong ma trận 397, prompt lớn nhất **6.086**.
- Fixture counts 26 chữ số và return hữu hạn cực lớn tạo BRPP **đúng 600**:
  prompt VI `1d`/`1 ngày` là 6.268/6.272; EN là 6.285/**6.289**. Còn 211 ký tự
  đến mốc 6.500, tức chỉ thêm tối đa 210 ký tự nếu các thành phần khác giữ nguyên.
  Không cam kết hướng dẫn mới W4 sẽ vừa ngân sách; phải đo và guard prompt cuối.
  Counts 27 chữ số làm vượt 600 bị từ chối, không bỏ ví dụ để vượt gate.
- Kiểm số sát 0/zero/âm/dương, n=0 và không bullish/N/A, nhãn mơ hồ/NaN/K>3,
  alias tiếng Việt NFD/NFC và ID rất dài. Renderer xác định, input không thay đổi.
  Fixture structured kiểm nhánh distill theo heading, giữ kết luận ở cuối báo cáo;
  nguyên trạng `_distill_report`, `_cap_report` và cap runtime sau phép đo.
- [Receipt](prompt_budget_review.json) có hash nguồn và trạng thái
  **PASS_WITH_REQUIRED_W4_HANDOFF**, `runtime_budget_gate_passed=false`.
  Điều kiện trước chạy W4: áp dụng cap đã kiểm hoặc kiểm chứng ngân sách khác;
  guard `len(final_prompt) < 6500` **sau mọi hướng dẫn được thêm**; giữ nguyên
  BRPP hoặc báo lỗi, không truncate/bỏ ví dụ. Độ dài là code point Python,
  không phải phép đo token/TPM.
- Bốn gate: compileall PASS; **312/312** unit tests PASS (94,466 giây);
  E2E xác định PASS (12,4 giây); **46/46** leakage tests PASS (5,660 giây).
  Task hoàn thành phần kiểm chứng/bàn giao; **Gate C chưa đóng**, còn W3-12.
  Receipt là fixture ngân sách, chưa smoke kho thật, fit HMM hoặc backtest OOS.

Lệnh tái lập:

```powershell
py -3.13 -X utf8 -m unittest discover -s tests -p 'test_bayesian_prompt_budget.py' -v
py -3.13 -X utf8 scripts/verify_prior_prompt_budget.py
```

Lệnh bốn gate tích hợp đã chạy:

```powershell
py -3.13 -m compileall agents core data_manager scripts tests utils
py -3.13 -X utf8 -m unittest discover -s tests -v
py -3.13 scripts/run_end_to_end_test.py
py -3.13 -X utf8 -m unittest discover -s tests -p 'test_*leakage.py' -v
```

### 05/10/2026 — W3-10 hoàn thành

- `format_compact_prior_prefix(tasks, stats)` là hàm module trong
  `core/bayesian_retriever.py`. K=0 ([]/None) trả rỗng; stats object với tasks rỗng
  vẫn có header/counts/rates. Tối đa ba task, thứ tự giữ nguyên; mỗi task ghi ngày
  quyết định và regime riêng, không nhầm ngày exit hoặc regime thống kê.
- Template đúng W3-04: T/P/A/I là code +/-/0 với chú giải; W/L là LONG ròng sau phí,
  SHORT là tiền mặt. Count n lấy từ stats, k từ số ví dụ thật. Rate giữ numerator/
  denominator, mẫu số 0 hiện 0/0(N/A); percentage chỉ làm tròn khi render.
- Return đã là phần trăm, không nhân 100 lần nữa; dấu và nhãn W/L được giữ đúng,
  ròng bằng 0 là LOSS/0.00%. Scientific dùng đúng ngưỡng đã khóa cho số sát 0/lớn.
  Ghi S=thiếu tin một lần; v1 chỉ chấp nhận sentiment NEUTRAL/alias của kho thiếu tin,
  task có POSITIVE/NEGATIVE bị từ chối vì cần phiên bản prefix tương ứng dữ liệu tin.
- Validation kiểm schema/enum/ngày ISO/alias, counts/rate hữu hạn Python gốc,
  quan hệ win/trap/bullish, sign/result/direction/trap và ID duy nhất. Không đọc giá,
  tính lại P&L hoặc xác nhận PIT/provenance; caller phải dùng retriever đã xác minh.
  Render NFC, newline chuẩn, không sửa input; quá 600 ký tự ném ValueError, không
  truncate hay tự bỏ ví dụ. Đây là guard runtime cơ bản; suite/prompt ghép W3-11 còn mở.
- 13 test formatter mới PASS; tổng 68 test Bayesian tập trung PASS. Đối chiếu exact
  text K=0..3, n=0, không bullish, zero-return, ngữ nghĩa/regime/order, alias/NFC,
  lỗi schema/NaN/NumPy/nhãn/mẫu số/ID/thiếu stats, return scientific và overflow.
  Formatter nhận được result của bốn mode trên fixture giá đã qua engine/validator thật.
- [Receipt formatter](prefix_formatter_review.json) PASS mười mẫu tham chiếu, lớn nhất
  **397 ký tự trong các mẫu đã kiểm**, không tuyên bố đây là upper bound của mọi input.
  Receipt chỉ dùng fixture render; chưa là smoke kho thật, prompt ghép hoặc backtest OOS.
  Các receipt trước giữ nguyên như snapshot lịch sử của task đó.
- Các gate tích hợp cuối cùng ghi tại README. **Gate C còn mở**; tiếp theo W3-11,
  rồi W3-12. Formatter chưa inject vào Decision/graph/backtest; tích hợp thuộc W4.

Lệnh kiểm formatter:

```powershell
py -3.13 -X utf8 -m unittest discover -s tests -p 'test_bayesian_prior_prefix.py' -v
```
