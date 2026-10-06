# W4-08 — Ranh giới Full reports, prior và Decision

Ngày triển khai: **06/10/2026**. Nhánh `feat/shared-reports-prior-graph`,
baseline `740031a`. Phạm vi: LangGraph thật, verifier/retriever/LLM fixture offline.
Kết quả gate được ghi trong [receipt](graph_prior_integration_review.json).

## API và ownership

| Entry point | Topology | Trách nhiệm caller |
| --- | --- | --- |
| `compile_upstream()` | Indicator → Pattern → Trend | Kiểm nguồn trước upstream; chạy một lần mỗi điểm |
| `compile_full_preparation()` | Full Preparation (Alpha + Sentiment) | Truyền upstream backtest, prior disabled; lưu Full output một lần |
| `compile_report_decision()` disabled | Decision Maker | Truyền đủ năm Full reports; không truyền hook prior |
| `compile_report_decision(prior_config=…, prior_retriever=…, prior_source_validator=…)` enabled | Prior Preparation → Decision Maker | Chuẩn bị context PIT; deep-copy Full cho từng nhánh |

`compile_decision(include_alpha=None, ablation_config=None)` và `set_graph()`
giữ chữ ký, topology và bốn ablation cũ. `ABLATION_CONFIGS` giữ nguyên.
Các entry point cũ tiếp tục chặn prior enabled chưa có adapter; đường nghiên cứu
mới chỉ mở khi gắn cả hai callback tin cậy. Không tự bật lại module bị tắt.

Hai API mới trả `ValidatedBacktestGraph`, bọc **CompiledStateGraph thật**.
`invoke`, `ainvoke`, `stream`, `astream` kiểm input thô trước bộ lọc TypedDict,
chuyển tiếp config/kwargs, bao gồm `stream_mode`. Có `channels` và `get_graph()`
để kiểm schema/topology. Không cung cấp checkpointer hoặc `update_state` ở task này.

## Biên input và callback

Enabled chỉ nhận Full/backtest/daily (`1d` hoặc `1 ngày`, canonical `1d`).
Config được chuẩn hóa và khóa ở lúc compile; config state nếu có phải khớp.
State cần `market_regime`, `current_signals`, `prior_provenance` cùng năm báo cáo.
`prior_tasks=[]`, `prior_stats=None`, `prior_metadata=None`, prefix `""` là đầu vào
trước truy xuất, được khởi tạo nếu chưa có. Result hoặc prefix còn sót bị từ chối.
Field ngoài schema, alias, outcome query bị chặn **trước khi LangGraph lọc mất**.

`prior_source_validator(projection) -> None` nhận bản sao JSON riêng, không có
DataFrame, messages, provider hoặc key. Projection có tám prior field,
symbol/cutoff/regime/signals, timeframe, backtest, ablation và năm Full reports.
Verifier chạy **hai lần**:

1. Trước retrieve: result còn rỗng, kiểm nguồn context/signals/bank.
2. Sau retrieve: kiểm result với nguồn đã khóa, trước formatter/Decision.

Callback phải ném ngoại lệ khi nguồn sai; trả bool/object PASS bị từ chối.
Đây là dependency bằng mã tin cậy, không là cờ `verified` trong state.
Verifier fixture không chứng minh nguồn thật; adapter W4-09 phải kiểm file/hash,
giá/tin/model PIT và tín hiệu theo hợp đồng W4-03. Kiểm nguồn trước upstream
vẫn thuộc caller, vì graph mới nhận báo cáo đã sinh.

`prior_retriever(projection) -> {"tasks": …, "stats": …, "metadata": …}` nhận
bản sao JSON riêng, trả đúng ba key W3. Không trả prefix hoặc thay báo cáo/context.
Nạp `BayesianPriorRetriever` một lần thuộc caller W4-11; graph chỉ gọi callback
**một lần mỗi nhánh**, kể cả Original K=0. Không có retrieve ở engine song song
với graph. Caller dùng output của graph cho result/checkpoint.

Node **Prior Preparation** kiểm query/result, gọi verifier và formatter W3
**một lần**, cập nhật tám channel cùng timeframe/ablation chuẩn hóa. Decision
ngay sau đó nhận output đã chuẩn bị qua hook callable nội bộ `_prior_preparer`;
không retrieve/verify/format lại. Hook này chỉ được gắn bởi builder mới,
không dùng cho Decision độc lập và không được lưu trong JSON.
Factory Decision mặc định vẫn kiểm nguồn/prefix như W4-07.

Guard prompt cuối vẫn chạy tại Decision sau toàn bộ template/BRPP/reasoning,
trước `_invoke_with_retry`. Không đổi cap, kinh tế, retry, format retry hoặc fallback.
Original enabled giữ metadata nhưng không BRPP/instructions; prompt bằng disabled
khi reports và context prompt giống nhau.

## Kiểm chứng

- **13 test mới PASS** trong `tests/test_prior_graph_integration.py`.
- Ma trận **128 ca graph thật**: VI/EN, hai daily alias, bốn mode, K=0..3,
  text/structured. Mỗi ca retrieve=1, formatter=1, verifier=2, Decision API giả=1;
  đủ channel, reports nguyên vẹn, caller input không đổi.
- Năm nhánh fixture dùng cùng Full: Indicator/Pattern/Trend mỗi node một lần,
  Alpha/Sentiment một lần, Decision năm lần; metadata/task không chia sẻ mutable state.
- Bốn ablation và `include_alpha` giữ topology/số lần gọi cũ; off/Original,
  empty/partial, alias/outcome/config lỗi, nguồn lỗi trước query/sau result,
  task exit bằng cutoff, callback mutation, overflow/API lỗi, async/stream được kiểm.
- Bốn gate mới **PASS**: compileall; **399 unit** (101,292 giây),
  E2E xác định (pipeline 10,8 giây), **56 leakage** (8,114 giây).
  **2.393 file bảo vệ** giữ nguyên hash trước/sau gate; receipt ghi log/hash,
  budget và hash source. Max prompt ma trận **6.264**, BRPP đủ 600 + reasoning
  **6.467**, cùng kết quả W4-07 và vẫn dưới ngưỡng nghiêm ngặt 6.500.

## Gate B và bước tiếp theo

**Gate B PASS_OFFLINE_GRAPH_PROMPT_FIXTURES** có phạm vi
**state/prompt/graph offline với dependency fixture**.
Source PIT thật, năm nhánh trong engine, checkpoint/resume và gate giá OOS
chưa được nghiệm thu. Không gọi API thật, sinh episode, tải tin/giá hoặc fit model.
Kho 852 episode, archive và receipt trước task giữ nguyên byte.

Tiếp theo **W4-09**: cài adapter nguồn PIT thật và verifier theo W4-03,
trước khi W4-10 điều phối Full dùng chung và W4-11 ghép retriever vào engine.
