# Thống kê regime và BRPP — phiên bản 1

**W3-04 chốt ngày 04/10/2026; Phase A hoàn thành.**
[Policy](statistics_prefix_policy.json) đóng băng công thức/template cho W3-09..11;
Stats runtime và API retrieve đã triển khai ở W3-09; formatter runtime có ở W3-10,
W3-11 đã kiểm ngân sách/prompt ghép offline và ghi phương án cap bắt buộc bàn giao
W4; smoke kho thật W3-12 đã PASS, Phase C/Gate C offline hoàn thành.
Cap runtime hiện tại không đạt khi ghép BRPP bão hòa.
Biên bản thiết kế W3-04 vẫn là snapshot tham chiếu, tách với
[biên bản runtime Phase B](statistics_runtime_review.json).

## 1. Population và ý nghĩa nghiên cứu

Với K>0, lấy E sau `exit_date < as_of_date` và scope của query; lấy R là toàn bộ
record trong E cùng current_regime. **Mọi metric tính từ R, không từ K ví dụ.**
Giữ cùng stats cho Random/Recent/Similarity/Bayesian khi query/cutoff/scope/regime
giống nhau; chỉ cách chọn ví dụ khác nhau. Original K=0 nhận stats None/prefix rỗng.
Đối chứng có prior cũng nhận thống kê cùng regime: kết luận giữa bốn nhánh này
đánh giá cách chọn ví dụ trên cùng khối stats; so với Original bao gồm cả tác động
stats và ví dụ, không tuyên bố đã tách riêng hiệu ứng thống kê.

Đóng băng **tỷ lệ mẫu, không smoothing Beta/Laplace**, không ngưỡng minimum support.
Nếu n=1 vẫn trả tỷ lệ với count hỗ trợ, không gọi là xác suất đã hiệu chuẩn.
Không ước lượng độ tin cậy Sentiment/Alpha/Indicator hoặc posterior LLM từ kho này.
Không dùng outcome test point; không gộp record khác scope/regime để tăng mẫu số.

## 2. Công thức và schema metric

Gọi n=|R|, W là `result == WIN_IF_LONG`, L là `result == LOSS_IF_LONG`.
Return >0 là W; return ≤0 là L theo engine W2, kể cả đúng 0 sau phí.
B_T/B_P là Trend/Pattern chuẩn hóa BULLISH theo [W3-03](prior_selection_method.md).

| Key trong `stats.metrics` | Numerator | Denominator | Ý nghĩa |
| --- | --- | --- | --- |
| `win_rate_long` | số W | n | Tỷ lệ LONG giả định có lãi ròng sau phí |
| `bull_trap_rate` | số (B_T hoặc B_P) và L | số B_T hoặc B_P | Tỷ lệ trap có điều kiện trên tín hiệu bullish của ít nhất một agent |
| `trend_false_bullish_rate` | số B_T và L | số B_T | Tỷ lệ Trend bullish nhưng LONG ròng không lãi |
| `pattern_false_bullish_rate` | số B_P và L | số B_P | Tỷ lệ Pattern bullish nhưng LONG ròng không lãi |

Union dùng OR, không cộng hai count bullish gây đếm đôi. Numerator trap phải bằng
tổng `was_bull_trap` trong R; sai quan hệ này phải ném ValueError. False bullish
không được gọi là bằng chứng breakout giá thất bại khi chưa có nhãn breakout riêng.

Stats có đúng `regime: str`, `population_count: int`, `metrics: dict`.
Metrics có đúng bốn key trên; mỗi metric đúng ba trường:

```json
{"numerator": 2, "denominator": 3, "rate": 0.6666666666666666}
```

- Numerator/denominator là int Python gốc không âm, không bool; numerator ≤ denominator ≤ n.
- `rate` là float Python gốc trong [0,1], bằng numerator/denominator khi mẫu số >0;
  không làm tròn trong stats. Khi kiểm float dùng `abs_tol=1e-12`, rel_tol=0.
- Mẫu số 0 → numerator 0 và rate **None**; không 0%, NaN hoặc Infinity.
- Win denominator luôn bằng population_count; n bằng matched_regime_count trong metadata.
- Pool R rỗng → n=0, cả bốn metric 0/0/None. K=0 → stats None, không tính pool.
- Dữ liệu hiện tại chỉ có outcome W/L, không trường unknown; nhãn sai dừng xác minh,
  không bỏ khỏi mẫu số một cách âm thầm.

Kiểm quan hệ counts: trap numerator ≤ n−wins; số fail riêng mỗi agent ≤ trap
numerator ≤ tổng số fail hai agent. Mẫu số union phải nằm giữa mẫu số bullish lớn
nhất của hai agent và min(n, tổng hai mẫu số). Đây là điều kiện cần; kết quả thống
kê thật vẫn phải được tính/đối chiếu trên record, không suy lại từ các bất đẳng thức.

Thêm `statistics_version="regime_empirical_stats_v1"` và
`prefix_version="compact_brpp_v1"` vào metadata mọi mode/K trước triển khai.
API v1 giữ stats envelope ba trường; version nằm trong metadata/config/receipt.

## 3. Fixture tính tay

Trong cùng scope/regime và trước cutoff, giả sử bốn episode:

| Episode | Trend | Pattern | Kết quả | Trap |
| --- | --- | --- | --- | --- |
| a | BULLISH | NEUTRAL | W | false |
| b | BULLISH | BULLISH | L | true |
| c | BEARISH | BULLISH | L | true |
| d | NEUTRAL | NEUTRAL | W | false |

n=4: win=2/4=0,5; trap=2/3; TrendFail=1/2=0,5; PatternFail=2/2=1.
Chọn K=1/2/3 không thay các tỷ lệ này. Thêm một episode future ngoài cutoff không
đổi stats; record L với cả Trend/Pattern không bullish không phải trap.
Fixture không bullish vẫn có win-rate, ba mẫu số còn lại 0 → None.
Các ca tính tay đã được đối chiếu runtime ở `tests/test_bayesian_statistics.py`
trong W3-09; bộ hồi quy đầy đủ W3-13 còn chờ thực hiện.

## 4. Mẫu BRPP đã khóa

Chữ ký formatter giữ `format_compact_prior_prefix(tasks, stats) -> str`.
Tasks theo đúng thứ tự retriever, tối đa 3; stats theo schema trên, đã PIT bởi caller.
`tasks=[]`, `stats=None` trả **chuỗi rỗng** cho Original. Tasks không rỗng với
stats None là lỗi. `tasks=[]`, stats object là query K>0 không có ví dụ, vẫn render
khối stats/counts; không nhầm với Original. K=0 được phân biệt qua stats None.

Template compact, dùng tiếng Việt chuẩn hóa NFC:

```text
[BRPP v1] R={regime}; n={population_count}; k={selected_count}
LONGwin={win_rate_long}; Trap={bull_trap_rate}; TrendFail={trend_false_bullish_rate}; PatternFail={pattern_false_bullish_rate}
T/P/A/I:+ tăng,- giảm,0 trung tính; W/L=LONG ròng sau phí; SHORT=tiền mặt; S=thiếu tin.
{symbol}@{as_of_date} R={task_regime} T/P/A/I={signal_codes} {result_code} {net_return_text}
```

Ba dòng đầu một lần; dòng task lặp 0..3 lần, newline `\n`, không newline cuối.
R là regime; n là population stats; k là số ví dụ thực tế, không requested K.
Mỗi task dùng ngày **quyết định lịch sử**, không exit để mô tả snapshot tín hiệu;
IDs/entry/exit/provenance đầy đủ ở metadata/record, không nhồi vào prefix.
Ghi regime riêng mỗi task vì các mode đối chứng có thể chọn khác current_regime.

- T/P/A/I = Trend/Pattern/Alpha/Indicator; `+`, `-`, `0` là tăng/giảm/trung tính.
- W/L là nhãn **LONG giả định ròng sau phí**, không dự đoán của Decision và không
  phải lợi nhuận của SHORT. SHORT vẫn giữ tiền mặt. Không thêm kỳ vọng P&L bán khống.
- Mỗi rate render `numerator/denominator(percent%)`, percent=`rate*100` một chữ số
  thập phân bằng Python `.1f`, dấu chấm. Mẫu số 0 render đúng `0/0(N/A)`.
- Return dùng đơn vị phần trăm đã lưu; không nhân 100 lần nữa. Zero render `0.00%`.
  Nonzero dùng `+.2f` nếu 0,005 ≤ abs(return) <10.000; còn lại `+.2e`, giữ dấu và
  hai chữ số sau chấm. Nhãn W/L lấy từ outcome đã xác minh, không từ số đã làm tròn.
- Không render sentiment như tín hiệu NEUTRAL đáng tin. Policy v1 dành cho kho
  đã phát hành với 0/852 tin đáng tin, vì vậy bỏ S trong task và ghi **S=thiếu tin**
  một lần. Nếu đổi phiên bản kho có tin, phải chốt prefix version mới trước dùng,
  không giữ câu thiếu tin khi không còn đúng.
- Không có câu mệnh lệnh LONG/SHORT dựa vào stats, không diễn giải tỷ lệ mẫu thành
  xác suất thắng query. Decision vẫn cần tổng hợp tín hiệu hiện tại trong W4.

## 5. Trần và các trường hợp biên

Đơn vị `len(prefix)` là số Unicode code point của Python, gồm khoảng trắng/newline;
không phải byte, token hoặc độ dài UTF-16 JavaScript. BRPP **≤600**; prompt ghép
Decision **<6.500**, bao gồm prefix/newline, giữ distill/cap hiện có.

Không truncate ký tự hoặc bỏ task để vượt gate. Template compact và số scientific
giữ nghĩa; nếu input hợp lệ vẫn vượt 600, **ValueError**, ghi blocker/đổi version
trước tích hợp. Không clamp numerator, return hoặc tự biến None thành 0.
Formatter kiểm schema/kiểu/finite/counts, alias, len(tasks)≤3, W/L/dấu return/bull trap
và ID duy nhất; không đọc CSV hoặc tính lại P&L. Việc chứng minh cutoff/provenance
thuộc retriever/caller vì chữ ký formatter không có query cutoff.

Kiểm chứng thiết kế phải bao phủ: Original/K=0; K=1/2/3; không ví dụ với n=0;
không bullish với n>0; regime CONSOLIDATION dài nhất; dấu return sát 0; return hữu
hạn rất lớn; counts n=852. Counts lớn hơn kho thật có thể làm prefix vượt trần,
không cam kết mọi số nguyên tùy ý đều render dưới 600.

Độ dài các mẫu và thống kê kho thật được ghi tại
[statistics_prefix_review.json](statistics_prefix_review.json). Đây là kiểm mẫu
tham chiếu ở Phase A. Formatter/runtime và test lỗi cơ bản đã có ở W3-10 với
[receipt riêng](prefix_formatter_review.json). [Receipt W3-11](prompt_budget_review.json)
kiểm ngân sách/prompt ghép với cap bàn giao tổng 4.000: 1.024 ca và dự phòng BRPP
600 PASS, prompt lớn nhất 6.289. Cap runtime cũ tổng 4.500 cho prompt VI/EN
6.565/6.582 khi ghép prefix 397; W4 phải áp dụng phương án đã kiểm và guard prompt
cuối `<6500` sau mọi hướng dẫn. [Smoke W3-12](prior_smoke.json) PASS 288 query
và 288 lượt lặp với nguồn lịch sử prefix PIT/fixture biên được phân biệt rõ.
Gate C offline PASS; ngân sách runtime vẫn thuộc W4.

Mẫu đã tính: K=0 là 0 ký tự; empty n=0 là 188; K=1/2/3 trên fixture là
241/285/329; mẫu CONSOLIDATION, counts 852 và return scientific rất lớn là
397 ký tự. Không coi 397 là upper bound cho mọi input hợp lệ; formatter vẫn
phải kiểm trần từng lần. Ví dụ cùng population nhưng K thay đổi chỉ thay số dòng,
không thay counts/thống kê.

Tóm tắt kho thật ở receipt dùng scope **pooled** và cutoff 03/01/2023, nhóm lại
theo nhãn regime lịch sử: 344 WIN/852 và 338 trap đã đối chiếu QA W2.
Đây là thống kê mô tả của prior đã đóng, không phải regime thực tế ngày cutoff,
không cấu hình paired mặc định same_symbol và không là kết quả OOS.

## 6. Gate A và bàn giao Phase B

- W3-01: đầu vào/hash/QA/validator và API kho đã xác minh.
- W3-02: query/result/K/seed/scope/lỗi/thiếu mẫu đã khóa.
- W3-03: alias/score/bốn mode/tie-break/RNG và version đã khóa.
- W3-04: population/công thức/schema metric/zero-denominator/no smoothing/template
  và version đã khóa; không còn lựa chọn phương pháp mở trong Phase A.

W3-05 bắt đầu nạp kho, lọc PIT và bảo vệ dữ liệu theo các hợp đồng này. Bốn gate
codebase trước merge là gate tích hợp tài liệu, không thay test retriever/prefix
hoặc benchmark tốc độ W3-15 sau triển khai.

## 7. Bàn giao W3-09 sang Phase C

- `retrieve` trả đầy đủ tasks/stats/metadata cho cả bốn mode; formatter sẽ nhận
  `result["tasks"]`, `result["stats"]`. Original K=0 vẫn là []/None.
- Mọi tỷ lệ giữ nguyên numerator/denominator và float chưa làm tròn; mẫu số 0
  là None. Không có smoothing, threshold hoặc posterior LLM suy từ tỷ lệ mẫu.
- Thống kê runtime tái dùng nhãn kinh tế W2; không tính lại return hay thay đổi
  corpus. Population có lỗi cutoff/scope/regime/ID/nhãn trap phải dừng.
- [Biên bản runtime](statistics_runtime_review.json) kiểm bốn mode, hai scope,
  bốn mã, bốn regime và K=1..3; đối chiếu đúng thống kê kho thật đã khóa ở Phase A.
- W3-10/W3-11 đã kiểm schema/định dạng BRPP và ngân sách ghép thử; W3-12 đã smoke
  retrieval/formatter trên kho thật. Tốc độ p95 và bàn giao W4 thuộc Phase D.

## 8. Bàn giao formatter W3-10

```python
from core.bayesian_retriever import format_compact_prior_prefix

prefix = format_compact_prior_prefix(result["tasks"], result["stats"])
```

`result` phải đến từ query/PIT đã xác minh. Formatter kiểm cấu trúc/ngày/nhãn và
quan hệ counts, không truy cập kho/CSV hoặc tính lại nhãn kinh tế. V1 kiểm sentiment
task là NEUTRAL/alias để câu S=thiếu tin phù hợp kho đã chốt; dữ liệu tin thật khác
cần prefix version mới trước sử dụng. Guard >600 ném ValueError, không tự truncate.
W3-11 hoàn thành suite trần và prompt ghép với điều kiện bàn giao cap/guard W4
tại [Phase C](phase_c_prefix_and_budget.md). Chưa áp dụng cap mới vào runtime.
W3-12 đã smoke với nguồn query PIT; biên bản tại [Phase C](phase_c_prefix_and_budget.md).
