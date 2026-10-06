# W4-07 — BRPP và hướng dẫn reasoning tại Decision

**Phạm vi:** node Decision thật với LLM và verifier fixture offline;
[receipt](decision_prior_integration_review.json) ghi ma trận, budget, hash và
bốn gate mới. Graph nghiên cứu, adapter PIT và retrieve/checkpoint backtest
tiếp tục ở W4-08..12.

## Prefix và prompt

- `core/decision_prior.py` kiểm config/query, Full reports, JSON, provenance
  context/bank và metadata/tasks/stats tại biên Decision. Source verifier
  phải chạy thành công trước khi gọi `format_compact_prior_prefix` W3.
- Formatter được gọi đúng một lần tại node; Decision không tính lại stats,
  smoothing hoặc thay template BRPP. Prefix phải bằng state đã chuẩn bị,
  tối đa 600 ký tự; prefix caller tự viết hoặc còn sót bị từ chối.
- `agents/decision_agent.py` chèn nguyên prefix một lần trước `### [1]`, rồi
  hướng dẫn prior VI/EN dài **181 ký tự**. Hướng dẫn yêu cầu đọc regime/tỷ lệ
  mẫu trước tín hiệu hiện tại, giữ n/N và N/A, W/L là lịch sử đã đóng. Prior
  chỉ là bối cảnh, không quyết định hoặc posterior LLM đã hiệu chuẩn.
- Disabled/Original prefix rỗng, không thêm marker, stats hoặc hướng dẫn prior
  vào prompt. Original vẫn enabled: context/Full reports/metadata K=0 và
  source verifier đều phải hợp lệ; không biến K=0 thành bỏ validation.
- Empty/partial giữ nguyên tasks/stats/metadata, kể cả tỷ lệ None và lý do
  thiếu mẫu. BRPP giữ mẫu số và `S=thiếu tin`; không đổi missing thành 0%.
- Guard `<6500` của W4-06 chạy trên prompt cuối sau BRPP và hướng dẫn. Log
  ghi độ dài prefix thật. Prompt vượt ngưỡng dừng trước wrapper/API; không
  truncate prefix, bỏ task hoặc trả quyết định cash để che lỗi.
- Cả structured và text tiếp tục qua `_invoke_with_retry`; schema nhị phân,
  hai lần format retry và kinh tế/conflict gate cũ giữ nguyên. Lỗi chuẩn bị
  prior nằm ngoài vòng format retry; lỗi nguồn/API/output được trả ra.
- Output node giữ tám field prior trên bản sao JSON riêng; sửa task/stats/
  metadata của output hoặc projection verifier không làm đổi input nhánh.

## Giao diện xác minh nguồn và giới hạn hiện tại

```python
create_final_trade_decider(llm, *, prior_source_validator=None)
```

Tham số cũ `llm` giữ nguyên. Tham số mới là **hàm tin cậy của caller**, không
phải flag state hoặc key của `prior_config`. Hàm nhận bản sao projection JSON:
tám field prior, symbol/cutoff/daily, Full ablation và năm report. Không đưa
DataFrame, message, provider/model hoặc secret vào projection đó.

Verifier phải đối chiếu provenance, nguồn giá/tin/model/signals/kho, selected
tasks và population stats với artifact thật theo contract W4-03; thành công
trả None, sai ném ngoại lệ. `True`/dict tự khai PASS không là kết quả hợp lệ.
Callback không được sửa projection để "chữa" dữ liệu; node dùng bản sao đã
kiểm, không nhận dữ liệu thay thế từ callback.

**W4-09 chưa có adapter nguồn thật.** Mặc định enabled thiếu verifier bị chặn
trước formatter/API; graph legacy vẫn dùng guard W4-05 chặn enabled. W4-08
mới nối ranh giới graph, W4-09 mới cung cấp verifier từ adapter. Không bật
enabled bằng callback rỗng trong nghiên cứu thật.

Verifier trong test chỉ so projection với fixture đã biết. Các fixture dùng
shape provenance đã khóa nhưng báo cáo/tasks tổng hợp; không chứng minh
snapshot giá, model PIT hoặc hash tín hiệu của một run thật. Receipt ghi rõ
phạm vi này; test node thành công không mở gate nguồn, graph, pilot hoặc OOS.

## Kiểm chứng

`tests/test_decision_prior_integration.py`: **11 test mới PASS**:

- Original/Random/Recent/Similarity/Bayesian, VI/EN, K=0..3, text/structured;
  capture prompt tại API, thứ tự/đếm prefix, formatter/verifier/wrapper một lần.
- Original giống prompt disabled; disabled không gọi verifier/formatter;
  state prior còn sót bị từ chối ở node thật.
- Thiếu field/config/query/Full report, metadata/scores/IDs/counts/stats sai,
  task exit bằng cutoff, NaN và provenance sai dừng trước API.
- Source verifier thiếu/lỗi dừng trước formatter/API, kể cả Original; verifier
  trả bool/dict bị từ chối. Projection và output có ownership độc lập.
- Empty/partial giữ N/A/None, counts/status/reason; API/output lỗi không trả CASH.
- BRPP 600 với reasoning qua node thật; prefix sai/601 và prompt đúng 6.500
  bị chặn, builder đã có BRPP không nhận prefix thứ hai.

Receipt đo cả hai alias daily, chuẩn hóa enabled thành `1d`; ma trận và ca
prefix 600 có hash prompt riêng. Receipt/spec W3/Phase A/W4-05/06 giữ nguyên;
nghiệm thu nguồn và Gate B vẫn là các bước tiếp theo.

**128 ca** VI/EN × hai alias daily × bốn mode × K=0..3 × text/structured có
prompt max **6.264**. Bốn ca BRPP thật dài 600 + reasoning max **6.467**;
guard còn 33 ký tự đến ngưỡng bị chặn 6.500. Budget này thuộc template hiện tại,
mọi hướng dẫn mới tiếp tục phải qua guard và kiểm lại.

Bốn gate PASS: compileall; **386 unit** (97,298 giây), **E2E**
(15,4 giây pipeline), **56 leakage** (9,010 giây). **2.391 file bảo vệ** giữ
hash trước/sau gate. Receipt phân biệt `decision_node_budget_passed` với
budget/BRPP graph và PIT toàn luồng còn mở; không đổi receipt cũ thành PASS mới.
