# W4-11 — Walk-forward năm nhánh và kết quả kinh tế

**Hoàn thành ngày 06/10/2026.** Nhánh `feat/prior-walk-forward-results`, baseline `a58d5d8`.
[Receipt kiểm chứng](prior_backtest_review.json), [checklist Phase C](phase_c_pit_paired_checkpoint.md).

## API và vòng đời

`BacktestEngine.run_prior_backtest()` nhận một adapter W4-09 và một
`SetGraph` đã khởi tạo. `core/prior_backtest.py` điều phối các cutoff và ghi
kết quả; không gọi `_init_graphs()` legacy hoặc đọc credentials.

```python
from pathlib import Path
from core.backtest_engine import BacktestEngine
from core.prior_context import PriorContextAdapter

# Caller đã tạo builder với các client đúng model/temperature/max_tokens.
adapter = PriorContextAdapter(prior_config, signal_config=signal_config)
engine = BacktestEngine({
    **signal_config["models"],
    "language": signal_config["language"],
    "alpha_norm_method": signal_config["norm_method"],
    "alpha_weights": signal_config["alpha_weights"],
})
result = engine.run_prior_backtest(
    "FPT", adapter=adapter, graph_builder=builder,
    output_dir=Path("outputs/prior_research_run"),
    time_frame="1d", n_tests=15, step=3,
)
```

- Adapter nạp kho/retriever/giá/tin một lần; runner dùng giá/events được
  sao chép từ RAM. Kiểm checksum vẫn đọc byte nguồn; không parse lại kho,
  nạp lại CSV hoặc tính lại nhãn kho ở mỗi query.
- Daily được canonical về `1d`; cần 600 nến lịch sử, horizon ba phiên,
  step ít nhất ba phiên. Plan mặc định dùng lịch walk-forward hiện có,
  giữ đúng `n_tests`, từ ngày sớm đến muộn. Có thể truyền `cutoffs` là tuple
  ngày ISO; khi đó tuple xác định plan thay cho `n_tests`.
- Kiểm giá entry/exit, volume, sự kiện quyền và chuẩn bị **mọi context**
  trước API đầu tiên. Prefix replay phải có đủ artifact đúng từng cutoff;
  provider fixed train giữ model/freeze đã kiểm, không tự fit hoặc đổi provider.
- Engine/config phải khớp Full đã khóa. `execution_mode="research"` kiểm
  các client `ChatGroq` và model/temperature/max_tokens; client giả chỉ được
  ghi `offline_fixture`. Ma trận giữ seed=42/scope=`same_symbol`.
- Tại mỗi cutoff, W4-10 tạo upstream/Full một lần, retrieve và Decision
  tuần tự cho Original K=0 và bốn prior K=3. Giữ nghỉ giữa nhánh/giữa điểm,
  retry/rate guard của hệ thống và stop event. Khóa RAM chặn hai run cùng engine.

## Giá thực thi và kết quả

Giá đầy đủ chỉ ở lớp đánh giá. State upstream là snapshot ≤cutoff;
query retriever chỉ có tám tham số đã khóa. Sau đủ năm Decision hợp lệ,
`evaluate_point()` lấy Open(t+1), Close(t+3), gọi
`compute_round_trip_net_return()` với fee=0,0025/slippage=0,001 mỗi chiều.
Return LONG >0 là UP; bằng/nhỏ hơn 0 là DOWN. SHORT thực thi CASH, return 0.

`summarize_points()` dùng `compute_account_metrics()` hiện có trên các
`TestPoint` nội bộ riêng cho từng nhánh: vốn 50 triệu VND, giá nhân 1.000,
LONG sử dụng tiền mặt rồi tất toán cuối chu kỳ. Output vẫn có năm branch ID,
không dùng tên ablation legacy. Chỉ các điểm **đủ năm nhánh complete** được
vào common support; accuracy là tỷ lệ 0..1. Chưa có điểm thì counts=0,
accuracy/account metrics=null.

| File trong thư mục output mới/rỗng | Nội dung |
| --- | --- |
| `identity.json` | Envelope của `$defs/identity`: plan/config/bank/nguồn/model/template/code/runtime, không chứa key |
| `points/<symbol>-<cutoff>.json` | Envelope `$defs/point` complete: projection PIT, source proof, shared Full, năm input/Decision/attempt và evaluation riêng |
| `results.json` | Envelope `$defs/result`, partial/complete, danh sách điểm/file SHA byte thực và năm summary |

Tất cả payload dùng schema W4-04 qua registry local, JSON native/finite,
SHA canonical `prior_checkpoint_canonical_json_v1` và atomic writer fsync/replace.
Giữ full tasks/stats/metadata/BRPP, source/query/shared/prompt hash và prompt
cuối <6.500 ký tự; BRPP ≤600. Schema source proof chỉ có năm nhóm nguồn;
signal proof nằm trong `shared.full_bundle.prior_provenance`.

`raw_response` giữ content API; structured tool call không có content được
serialize cùng content/tool_calls. `normalized_response` là output parser,
không thay thế raw thiếu. Attempt có UUID và UTC `Z`; latency đo toàn graph
Decision gồm chuẩn bị prior và retry. Chưa thu provider request ID: trường
đó là null. Attempt ở đây ghi **một lần invoke graph**, không phải từng HTTP retry.

Callback nhận bản sao `{completed, total, latest, partial}` sau khi kết quả
điểm đã ghi. Lỗi nguồn/LLM/output/đĩa truyền ra, không tạo nhánh SHORT thay lỗi.
Các file điểm complete và summary đã ghi trước lỗi được giữ. Dừng trước
điểm hoặc giữa hai điểm trả result partial; lỗi/dừng giữa nhánh chưa seal điểm.

## Tương thích và ranh giới bàn giao

- `run()`, return/callback/summary Full/No-Alpha, bốn ablation, các hàm
  kinh tế giữ AST. Đường legacy/flag off không tạo runner hoặc I/O kho mới.
  Constructor dùng config đã chuẩn hóa khi caller không truyền dictionary.
- Thư mục không rỗng bị từ chối, không tự ghi đè/chạy lại output. W4-11 lưu
  **điểm hoàn tất**, chưa lưu tiến độ nhánh/shared đang dở hoặc `run_manifest`.
  Đây chưa là API phục hồi; OS lock, durable intent và resume thuộc W4-12.
- Bộ kiểm chứng dùng file/model/LLM fixture; chưa là chạy LLM thật hoặc
  bằng chứng giao dịch OOS. Gate C còn W4-12 và gate giá OOS còn mở.

## Kiểm chứng

16 test mới gồm 13 integration/kinh tế và 3 leakage. Hai cutoff dùng
engine/adapter/provider/retriever/LangGraph thật, upstream/LLM/ảnh và factor
Alpha giả lập: mỗi upstream/Full hai lần, 10 retrieve và 10 Decision.
Kiểm thêm provider fixed train với lịch mặc định; raw text/structured tool
calls, metadata/schema/hash, lãi/lỗ/break-even/CASH/lãi kép, phiên thiếu,
volume/quyền, config sai, lỗi quota/output, callback ownership và partial.

Leakage kiểm evaluation chỉ sau năm Decision, snapshot/query không có outcome
tương lai, artifact sai ở điểm cuối chặn API đầu, kho đổi giữa hai điểm chặn
upstream tiếp theo. Bốn gate: compileall, **461 unit**, E2E offline,
**77 leakage** PASS. Receipt kiểm **2.407 file bảo vệ** giữ hash,
kho 852 episode/archive/receipt trước và AST kinh tế/legacy nguyên vẹn.

**Phase C 3/4, W4 11/16.** Tiếp theo W4-12; Gate C/D và giá OOS còn mở.
