# W4-10 — Full dùng chung và năm Decision trong engine

**Hoàn thành ngày 06/10/2026.** Nhánh `feat/paired-prior-decisions`,
baseline `7d44f44`. [Receipt](paired_prior_point_review.json),
[checklist Phase C](phase_c_pit_paired_checkpoint.md).

## Luồng đã triển khai

`BacktestEngine.run_prior_point(point, graph_builder=builder)` nhận context
đã kiểm từ W4-09 và builder/model do caller khởi tạo với cấu hình đã khóa.
Đường này không tự đọc key, preload tin hoặc gọi `_init_graphs()` legacy.

1. Kiểm đủ năm branch ID duy nhất, seed=42 và scope=`same_symbol` trước upstream.
   `PriorPointContext.prior_config` trả bản sao để kiểm ma trận, không cấp quyền
   sửa cấu hình adapter. Kiểm lại byte nguồn qua `agent_state()`.
2. Tạo ảnh nến/trend một lần từ window PIT, `write_artifacts=False`; thiếu ảnh
   hoặc lỗi tạo ảnh dừng. Chạy Indicator → Pattern → Trend đúng một lần.
3. Trước Alpha, kiểm upstream giữ nguyên symbol/cutoff/window/config/giá;
   đọc lại store tin đã xác minh từ context. Nến/window tương lai hoặc nguồn
   thay đổi bị chặn trước Full, không sửa input sai để tiếp tục.
4. `compile_full_preparation(strict_research_mode=True)` chạy Alpha và
   sentiment một lần. Lỗi nguồn/Alpha được truyền ra; không dùng fallback
   kỹ thuật để tạo kết quả nghiên cứu. API cũ mặc định giữ `False`.
5. `bind_full()` seal reports/signals/proof. Mỗi Decision nhận deep copy mới
   từ shared, không nhận messages/ảnh/DataFrame hoặc output nhánh trước.
6. Chạy tuần tự năm graph Prior Preparation → Decision; mỗi nhánh retrieve
   và format một lần. Giữ retry wrapper và khoảng nghỉ giữa nhánh của engine;
   khoảng nghỉ có thể bị ngắt bởi stop event. Kiểm lại source/output trước
   khi nhận nhánh hoàn thành; bốn prior modes có stats cùng population.

| Branch ID | Mode | K |
| --- | --- | ---: |
| `original` | `bayesian_regime` | 0 |
| `random` | `random` | 3 |
| `recent` | `recent` | 3 |
| `similarity` | `similarity` | 3 |
| `bayesian` | `bayesian_regime` | 3 |

Original vẫn kiểm nguồn và retrieve K=0, không có tasks/stats/BRPP. Các prior
còn lại giữ status/counts/reason của retriever, kể cả empty hoặc partial.
Mặc định chạy theo thứ tự bảng; `branch_order` chỉ nhận một hoán vị đủ năm ID.

## API và output

```python
from core.backtest_engine import BacktestEngine
from core.prior_context import PriorContextAdapter

# builder dùng đúng model/config đã ghi trong signal_config.
adapter = PriorContextAdapter(prior_config, signal_config=signal_config)
engine = BacktestEngine({"language": signal_config["language"]})
point = adapter.prepare(symbol, cutoff)
paired = engine.run_prior_point(point, graph_builder=builder)
```

Output JSON native/finite có:

- `shared`: Full reports/signals/proof chung, prior result chưa truy xuất.
- `full_bundle`: sáu key theo contract W4-04: reports, current_signals,
  market_regime, prior_provenance, alpha_factors, sentiment_data. Giữ kết quả
  Alpha/sentiment để caller checkpoint ở W4-12; không có nhãn đánh giá query.
- `shared_seconds`: thời gian tạo shared, tách khỏi thời gian từng Decision.
- `branches`: mỗi ID có `state` (shared và prior result/Decision/prompt của
  nhánh), `elapsed_seconds`. Không chứa messages, ảnh, DataFrame, store hoặc key.

Caller tạo adapter/builder một lần cho run; W4-11 sẽ nối API này vào vòng
walk-forward và kết quả kinh tế. Mỗi engine giữ khóa một điểm đang chạy;
gọi song song cùng engine bị từ chối. Điểm đã bắt đầu (symbol, cutoff) không
được tự chạy lại upstream/Full trên engine đó, kể cả sau lỗi/stop. Lỗi
không bị chuyển thành SHORT, không chạy thêm nhánh sau lỗi. Đây là guard
trên RAM; cơ chế persist/resume giữa tiến trình thuộc W4-12.

## Tương thích và kiểm chứng

- Giữ nguyên đường `_run_ablation_variants()`, `_run_paired_point()`, `run()`
  và bốn ablation cũ. Baseline không được nhận Full Alpha/Sentiment.
- **15 test mới**: 12 paired và 3 leakage. Dùng engine, adapter, nguồn file,
  provider, retriever, LangGraph và node Alpha thật; đầu ra tính Alpha được
  fixture hóa, upstream/LLM/ảnh dùng giả định xác định. Không fit/crawl/API.
- Spy xác nhận **Indicator/Pattern/Trend/Alpha/Sentiment mỗi loại một lần**,
  **5 retrieve, 5 format, 5 Decision LLM, 4 khoảng nghỉ** cho một điểm.
- Ma trận hai provider × VI/EN: **4 điểm/20 Decision** PASS; kiểm thêm text/
  structured, mutation input/output, đảo thứ tự, thiếu/lỗi chart/upstream/
  sentiment, quota giả, stop và guard chạy lại/song song.
- Ba ca leakage mới chặn snapshot/window tương lai hoặc tin thay đổi sau
  upstream trước Full. Các suite PIT/prior/kinh tế/ablation cũ tiếp tục PASS.
- Bốn gate: compileall, **445 unit**, E2E offline, **74 leakage** PASS.
  Receipt kiểm **2.402 file bảo vệ giữ hash** và AST của các hàm kinh tế/legacy giữ nguyên.

**Phase C 2/4, W4 10/16.** Tiếp theo W4-11: điều phối nhiều cutoff, schema
kết quả và đánh giá bằng engine thật; W4-12: checkpoint/resume từng nhánh.
Gate C/D và giá thực thi OOS 2023–2024 còn mở.
