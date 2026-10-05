# Phase C — BRPP và ngân sách prompt

**Trạng thái: W3-10 hoàn thành; W3-11/W3-12 chưa thực hiện. Gate C còn mở.**
Formatter nằm trong `core/bayesian_retriever.py`, test `tests/test_bayesian_prior_prefix.py`,
biên bản [formatter](prefix_formatter_review.json). Script `scripts/verify_bayesian_prior.py`
và `docs/week3/prior_smoke.json` còn dự kiến cho W3-12.

Template, schema metric và các trường hợp biên đã khóa tại
[W3-04](statistics_and_prefix_contract.md), [policy](statistics_prefix_policy.json).
Receipt Phase A kiểm mẫu tham chiếu ≤600, chưa thay test formatter/runtime hoặc
prompt ghép thực tế trong các task bên dưới.

**Điểm cần đối chiếu khi triển khai:** log E2E hiện tại ghi trần prompt compact
7.500 ký tự, cao hơn ràng buộc 6.500 trong `AGENTS.md`. W3 phải kiểm độ dài prompt
ghép thử thực tế, không lấy trần cũ làm tiêu chí PASS; W4 cần áp dụng ràng buộc
<6.500 tại runtime khi tích hợp BRPP.

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

- [ ] Kiểm `len(prefix) <= 600` cho K=1..3, các regime, số liệu cực trị hợp lệ,
  nhiều chữ số, tiếng Việt và input dài; với K>3 thực hiện đúng chính sách Gate A.
- [ ] Không âm thầm truncate: rút gọn theo template đã khóa hoặc từ chối nếu vẫn vượt trần.
- [ ] Kiểm việc render là xác định, không sửa tasks/stats; giá trị mơ hồ/NaN bị từ chối.
- [ ] Dùng builder compact hiện có của Decision để ghép thử báo cáo fixture + BRPP:
  tổng prompt phải **<6.500** ký tự; thử cả ngôn ngữ builder đang hỗ trợ.
- [ ] Giữ `_distill_report`, `_cap_report`; chỉ test/ngân sách bàn giao, chưa inject
  BRPP vào runtime Decision/graph/backtest. Nếu fixture hợp lệ vượt trần, ghi blocker
  và phương án xử lý cụ thể trước khi chốt W3/W4.

## W3-12 — smoke trên kho thật, offline

- [ ] Script nạp kho QA PASS, chọn truy vấn xác định trên bốn mã/bốn regime từ dữ liệu
  có sẵn; fixture/query lịch sử phải mang regime prefix PIT, không nhãn hồi cứu Panel A.
- [ ] Có cutoff trước episode đầu, cutoff bằng exit, query thiếu K và query sau cuối kho.
  Không suy ra regime thực tế của ngày giả định nếu chưa có snapshot xác minh.
- [ ] Chạy bốn mode, ghi bank hash/config/seed, IDs/dates, số mẫu, stats, score,
  lý do thiếu mẫu và prefix length; kiểm bằng cutoff ở từng task đầu ra.
- [ ] Không gọi upstream/LLM, fit lại HMM, sinh episode hoặc tải giá mới; không ghi đè
  kho/manifest W2. Receipt chỉ chứa dữ liệu nghiên cứu, không key/.env.
- [ ] Biên bản phân biệt smoke retrieval và benchmark giao dịch OOS; hạn chế dữ liệu
  vẫn được ghi rõ.

**Gate C:** prefix đủ nghĩa và ≤600, prompt ghép thử <6.500, smoke bốn mode PASS
với receipt tái lập. Chưa coi đây là hệ thống tích hợp W4.

## Kết quả và nhật ký

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
