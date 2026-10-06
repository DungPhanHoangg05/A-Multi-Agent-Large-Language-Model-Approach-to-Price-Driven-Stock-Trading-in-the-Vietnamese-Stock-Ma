# W4-09 — Adapter nguồn và tín hiệu point-in-time

**Hoàn thành ngày 06/10/2026.** Nhánh `feat/prior-point-in-time-context`,
baseline `5530eba`. [Receipt](prior_context_review.json),
[checklist Phase C](phase_c_pit_paired_checkpoint.md),
[contract đã khóa](provenance_contract.md).

## Phạm vi và thứ tự xử lý

`core/prior_context.py` cung cấp `PriorContextAdapter` và `PriorPointContext`.
Adapter nạp kho/retriever một lần, kiểm manifest/QA và file nguồn; từng điểm
được kiểm trước upstream, sau đó gắn bộ Full với nguồn trước retrieve/Decision.

1. Constructor ghim SHA-256 byte thật của kho/manifest/QA, giá CSV/evidence/
   events, snapshot tin và VNINDEX. Giá dùng loader thô W2 đã nghiệm thu,
   `vnstock/VCI`, crosscheck `VCI/KBS`, `UNADJUSTED_EXECUTION`, nghìn VND.
2. `prepare(symbol, cutoff)` cắt archive hoặc đối chiếu snapshot caller khai
   PIT với nguồn đã kiểm. Snapshot có đúng sáu cột OHLCV, phiên cuối đúng
   cutoff, đủ 600 nến Alpha; window và prefix train giữ hash riêng.
3. Kiểm regime với một trong hai provider bên dưới. Snapshot tin loại bài
   thiếu ngày, tương lai, ngoài 90 ngày; ngày sai ISO gây lỗi nguồn.
4. `agent_state()` cấp bản sao giá/window/store cho upstream và Full. Prior
   chưa bật ở bước này. `bind_full()` kiểm input, năm report, năm Alpha và
   sentiment thực tế, rồi seal context/signals/provenance JSON cho graph.
5. Graph W4-08 dùng `point.verify_source` trước query và sau result;
   `point.retrieve` gọi retriever W3 một lần, giữ bản sao canonical để kiểm
   tasks/stats/metadata. Formatter và Decision vẫn thuộc graph hiện có.

Proof trước Full có sáu nhóm, chưa có `signals`, không được nhập vào Decision.
Shared sau seal có đủ bảy nhóm theo policy W4-03. Mọi output đều là bản sao;
caller thay metadata, reports, ngày hoặc tín hiệu bị từ chối. Outcome của
query không được đưa vào shared/projection/query. Prior đã đóng chu kỳ vẫn
giữ outcome theo API W3 và điều kiện `exit_date < cutoff`.

## Hai provider

| Provider | Kiểm nguồn và thời gian | Hoạt động |
| --- | --- | --- |
| `historical_prefix` | Artifact đúng ngày, train end = cutoff, full prefix/hash và state tính lại đúng | `PrefixRegimeProvider.get(..., verify_only=True)`; thiếu artifact dừng |
| `fixed_train_oos` | Artifact cố định, train end ≤ freeze < cutoff; train end < cutoff; đủ prefix train | Nạp model một lần, classify trên RAM; tham số HMM/scaler/calibration giữ nguyên |

Loader regime hiện có kiểm payload hash, cấu hình, runtime, tham số hữu hạn
và calibration. Ba component end dates lấy từ artifact chung đã xác minh.
Manifest VNINDEX W1 dùng `interval=1D`, fixture cũng kiểm ký hiệu này; query
và proof dùng canonical `1d`. Không tự chuyển provider khi thiếu nguồn.

Giá thực thi thật mới có gate 2018–2022. Adapter từ chối cutoff ngoài phạm vi
manifest: provider frozen được kiểm bằng fixture kỹ thuật có train end nhỏ
hơn cutoff, **chưa có kết quả giao dịch OOS 2023–2024**.

## Tín hiệu và journal W2

- Ba hướng lấy từ trường duy nhất trong Indicator/Pattern/Trend bằng parser
  W2, chuẩn hóa W3. Thiếu trường, hướng mẫu hoặc nhiều trường gây lỗi.
- Alpha phải có năm ID riêng, bảng report khớp hướng từng factor; tổng hợp
  report khớp đa số tăng/giảm (hòa → NEUTRAL). Sentiment report/data khớp
  snapshot tin PIT; coverage/hash tính trên toàn bộ visible trước cap hiển thị 15.
- Visible <3 giữ NEUTRAL và lý do `INSUFFICIENT_DATED_HISTORY`, không gọi
  sentiment LLM để bổ sung tin thiếu. Tin đã khai visible có ngày tương lai
  hoặc thiếu ngày phải lỗi.
- Full mới ghi model/config/runtime và hash code thực chạy; cấu hình phải
  được khóa trước run và caller phải dùng đúng model/node đã khai.
- `load_shared_checkpoint(run_dir)` chỉ đọc journal COMPLETE của replay:
  kiểm envelope, run signature của bank, episode, regime/source, reports,
  tín hiệu, model/config và identity code/runtime lúc tạo. Chữ ký signal W2
  tính trên input trước khi thêm `reports_sha256`/`alpha_factors`; reader giữ
  đúng quy tắc này, đối chiếu thêm reports upstream với Full đã hoàn thành.
- Trend viết tắt chỉ được nhận khi đúng digest/rule/hướng trong biên bản
  parse compatibility đã đóng băng. Kiểm hash file parser gốc; không thực thi
  mã lịch sử, không đổi reports hoặc đóng dấu code hiện tại lên journal cũ.

## Điểm nối cho W4-10/11

```python
# signal_config chứa models/window/norm/weights/language/time_frame đã khóa.
adapter = PriorContextAdapter(prior_config, signal_config=signal_config)
point = adapter.prepare(symbol, cutoff)
upstream_state = upstream.invoke(point.agent_state())
full_state = full_preparation.invoke(upstream_state)
shared = point.bind_full(full_state)
decision_graph = graph_builder.compile_report_decision(
    prior_config=shared["prior_config"],
    prior_retriever=point.retrieve,
    prior_source_validator=point.verify_source,
)
result = decision_graph.invoke(shared)
```

Đây là điểm nối API; điều phối upstream/chart/Full một lần và năm nhánh trong
engine thuộc W4-10/11. Mỗi nhánh đổi mode/K trên bản sao shared, giữ nguyên
bank/context/reports. Journal replay chỉ đọc có thể thay hai bước tạo reports
bằng `point.load_shared_checkpoint("outputs/historical_memory_run")`.

Verifier kiểm lại byte nguồn đã ghim trước khi agent/graph dùng; nguồn thay
đổi gây lỗi, không cập nhật hash để hợp thức hóa. Callback không parse JSON,
load model/retriever, crawl hoặc fit; kiểm byte nguồn được thực hiện ở ranh
giới verifier, ngoài lời gọi `BayesianPriorRetriever.retrieve` trên RAM.

## Kiểm chứng

- **31 test mới**: 16 adapter và 15 leakage, fixture file/model nhỏ xác định,
  dùng loader/provider/retriever/graph thật; chặn fit/crawl. Ma trận **128 ca**
  gồm hai provider × VI/EN × bốn mode × K=0..3 × text/structured Decision giả.
- Kiểm future/stale/wrong symbol, thiếu prefix, model train tương lai/freeze
  sai ngày, hash/schema/gate giá, nguồn thay đổi, scope result và bản sao;
  lỗi dừng trước retriever hoặc LLM theo ranh giới tương ứng.
- Replay **6 checkpoint thật**, bốn mã tại 2022-12-27, FPT tại 2020-06-04 và
  2022-03-04; giữ identity cũ, kiểm cả query rỗng và Trend viết tắt đã ghi
  biên bản. Decision dùng LLM giả, không phải dự báo hay backtest mới.
- Bốn gate: compileall, **430 unit**, E2E offline, **71 leakage** PASS;
  receipt lưu lệnh/log/hash, source proof; **2.399 file bảo vệ giữ nguyên byte**.

**W4 đạt 9/16, Phase C 1/4.** Tiếp theo W4-10 chuẩn bị Full một lần/năm
Decision; W4-11 kết quả engine, W4-12 checkpoint/resume còn mở. Gate C/D và
gate giá ngoài mẫu tiếp tục theo checklist.
