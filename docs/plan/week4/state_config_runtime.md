# W4-05 — State/config prior và validator runtime

**Phạm vi:** tám field optional, parser độc lập, kiểm shape JSON/context và
guard state trên graph hiện có. [Contract đã khóa](integration_contract.md)
và [policy](integration_policy.json) giữ nguyên; kiểm chứng mới ghi tại
[receipt runtime](state_config_runtime_review.json).

## Thay đổi

- `agents/agent_state.py`: khai báo `NotRequired` cho `prior_config`,
  `market_regime`, `current_signals`, `prior_provenance`, `prior_tasks`,
  `prior_stats`, `prior_metadata`, `bayesian_prior_context`. `BacktestAgentState`
  kế thừa cùng channel, không làm các field mới bắt buộc với input legacy.
- `core/prior_config.py`: parser tám key với default disabled; enum/range và
  kiểu Python gốc nghiêm ngặt, không dùng `bool("false")` hoặc chấp nhận bool
  thay int. Config partial/None trả bản sao, không sửa input.
- `validate_prior_execution`: enabled chỉ Full/backtest/daily `1d` hoặc
  `1 ngày` → `1d`; Original K=0 vẫn enabled. Conflict `ablation_config` và
  `include_alpha` giữ hành vi resolver cũ. Flag off giữ bốn ablation, coercion
  cũ và alias thời gian cũ.
- `resolve_prior_paths`: flag off chỉ kiểm cú pháp, không resolve/stat/đọc
  nguồn. Enabled yêu cầu ba đường dẫn file trong repo sau resolve, bao gồm
  containment của symlink. Hàm này **chưa nạp kho hoặc xác minh manifest/QA**.
- `copy_prior_json`: sao chép sâu dict/list và scalar Python finite; từ chối
  NumPy, NaN/Infinity, datetime, DataFrame, message và đối tượng runtime.
  Giữ outcome của task lịch sử trong bản sao; không ép giá trị lỗi thành None.
- `normalize_prior_query_context`: mã nghiên cứu/ngày ISO, shape regime,
  ngày regime bằng cutoff, feature-end ≤cutoff và đủ năm tín hiệu theo
  normalizer W3. Không suy tín hiệu từ diễn giải hay thêm outcome query.
  Kiểm shape này **không chứng minh nguồn PIT**.
- `normalize_prior_state`: input legacy không có prior giữ nguyên key; các
  field được cung cấp khi disabled chỉ nhận sentinel None/[]/chuỗi rỗng.
  Từ chối prefix/tasks/stats/provenance còn sót và alias trùng nguồn thông tin.
- `utils/graph_setup.py`: guard trước và sau từng node của ba builder hiện có;
  giữ topology và chữ ký cũ. Input sai bị chặn trước node; output prior sai
  bị chặn trước node kế tiếp. Các field hợp lệ được chuyển tiếp dù node chỉ
  trả report, mỗi lần có bản sao riêng.

## Ranh giới enabled và bước tích hợp tiếp

Config enabled và Original K=0 được parser/execution validator chấp nhận
khi đúng Full/daily/backtest. Graph production hiện tại từ chối enabled:
thiếu regime/signals/provenance báo thiếu input; dict tự khai PASS/hash cũng
không đủ, báo chưa có adapter xác minh nguồn PIT. Chưa có đường chạy enabled
hợp lệ trên graph legacy tại bước này; tránh âm thầm chạy Decision thiếu prior.

W4-08 xây ranh giới chuẩn bị Full/prior/Decision; W4-09 xác minh nguồn thật;
W4-10..12 ghép năm nhánh, retrieve và checkpoint. Guard tạm phải được thay
bằng ranh giới đã nghiệm thu khi triển khai các task đó. W4-05 không bật prior
vào live, không nạp retriever và không thay cap/prompt Decision.

Hàm kiểm input thô `normalize_prior_state` phải được caller nghiên cứu gọi
**trước** khi đưa vào graph: LangGraph chỉ giữ key đã khai báo trong schema.
Các alias/outcome ngoài schema có thể bị framework lọc trước node; guard node
không thay thế kiểm input thô. Caller này thuộc W4-08/09, chưa triển khai.

## Ví dụ parser offline

```python
from core.prior_config import normalize_prior_config, validate_prior_execution

disabled = normalize_prior_config()  # Không đọc kho.
original, full, timeframe = validate_prior_execution(
    {"enable_bayesian_prior": True, "k": 0},
    is_backtest=True,
    time_frame="1 ngày",
)
```

Ví dụ chỉ kiểm config, không chạy agent hoặc xác minh nguồn. Dữ liệu ngày
trong projection JSON phải là chuỗi ISO; caller tạo scalar Python trước khi
đưa vào validator, không truyền Pandas Timestamp/NumPy scalar vào JSON.
State runtime legacy vẫn giữ DataFrame/message; không serialize cả state đó
thành checkpoint. Projection checkpoint riêng thực hiện tại W4-12.

## Kiểm chứng

`tests/test_prior_runtime_config.py`: **28 test PASS** bằng fixture offline,
bao gồm bảy config mẫu và 19 config sai đã khóa, enum/range/types/path,
containment sau resolve, không I/O khi disabled, Original/conflict/ablation,
JSON deep copy, ngày/tín hiệu, field optional và graph production.

Probe schema enabled chỉ dùng StateGraph tối giản với TypedDict production
để kiểm channel; không là lần chạy enabled đã xác minh nguồn. Test production
đảm bảo input stale/unverified không gọi bất kỳ node agent nào. Regression
legacy và bốn gate ghi riêng trong receipt, không sửa receipt Phase A/W3.

Compileall PASS; **367 unit** (59,045 giây), **E2E offline** (7,8 giây pipeline),
**56 leakage** (5,773 giây) PASS. 2.384 file bảo vệ giữ hash trước/sau gate;
259 file bàn giao W4-01 nguyên byte, hai file state/graph có thay đổi runtime
được ghi riêng trong receipt. Không gọi LLM thật hoặc mở gate giá OOS.

**Gate B còn mở:** cap/guard `<6500`, chèn BRPP và graph nghiên cứu ở W4-06..08.
Giá thô OOS 2023–2024, provider/model PIT, checkpoint runtime và pilot W5 còn
cổng kiểm chứng riêng; kết quả fixture không là kết quả giao dịch.
