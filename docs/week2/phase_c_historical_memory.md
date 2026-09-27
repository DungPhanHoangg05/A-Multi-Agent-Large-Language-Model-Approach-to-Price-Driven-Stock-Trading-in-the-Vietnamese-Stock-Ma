# Phase C — kho lịch sử và tín hiệu agent

## W2-09 — lưu và xác thực chu kỳ

`core/bayesian_memory.py` cung cấp `HistoricalMemory.add/load/save/eligible` và
`validate_historical_task_record`. File kho là danh sách các record theo đúng
[schema W1](../plan/week1/historical_task_record.schema.json), không thêm provenance
vào record. `records` và kết quả truy vấn đều là bản sao sâu.

- Loader mặc định chỉ dùng `load_verified_execution_data` với `data/execution_prices`;
  CSV, evidence và sự kiện phải đúng checksum. Có thể tiêm loader cho kiểm thử.
- Từ chối trường thiếu/thừa, ngày không đúng ISO, tín hiệu thiếu/rỗng, số không hữu
  hạn, NumPy scalar, khóa JSON trùng, ID trùng, cùng điểm quyết định hoặc khoảng
  nắm giữ cùng mã chồng lấn.
- Lịch phiên phải đúng `Open(t+1)` và `Close(t+3)`, không có phiên mất thanh khoản
  hay quyền trong `(entry, exit]` theo gate giá.
- Lợi nhuận không làm tròn: `100 * compute_round_trip_net_return(entry, exit)`;
  sai lệch cho phép tối đa `1e-8` điểm phần trăm. Hướng `UP`/`WIN_IF_LONG` khi
  lợi nhuận ròng dương, còn lại `DOWN`/`LOSS_IF_LONG`, kể cả bằng không.
- Chốt `was_bull_trap`: Trend **hoặc** Pattern có nhãn tăng và lợi nhuận ròng
  không dương. Nhãn tăng chuẩn là `BULLISH` (chấp nhận các alias BULL, UP, TĂNG,
  TĂNG GIÁ). Không suy đoán chiều tăng từ từ khóa trong báo cáo.
- Nạp/thêm xác thực toàn bộ trước khi đổi state. Lưu xác thực lại dữ liệu rồi ghi
  file tạm cùng thư mục, `flush`, `fsync`, `os.replace`; lỗi giữ file cũ và dọn tạm.
- Truy vấn chỉ trả `exit_date < as_of_date`. Chu kỳ tương lai/đang nắm giữ được
  loại bởi điều kiện truy vấn; ngày truy vấn sai ném `ValueError`.

```python
from core.bayesian_memory import HistoricalMemory

memory = HistoricalMemory()
memory.load("data_manager/regime_memory_store.json")
prior_tasks = memory.eligible("2023-01-03", symbol="FPT")
```

Ví dụ trên áp dụng sau W2-13. W2-09 chưa tạo kho >300 episode; W2-11 vẫn cần
bộ sinh nhãn, W2-12 cần runner ghép episode và W2-14 cần kiểm toán toàn bộ kho.

### Kiểm thử W2-09

`tests/test_historical_memory.py` có 10 test; `tests/test_historical_memory_leakage.py`
có 2 test. Các fixture dùng chu kỳ và giá VCI thật đã xác minh; không dùng nhãn
close-to-close hay giá cổ phiếu W1.

Bốn gate trước merge ngày 27/09/2026: compileall PASS, **166 unit tests** PASS,
E2E PASS (13,4 giây; upstream một lần mỗi điểm), **25 leakage tests** PASS.

```powershell
py -3.13 -m compileall agents core data_manager scripts tests utils
py -3.13 -X utf8 -m unittest discover -s tests -v
py -3.13 scripts/run_end_to_end_test.py
py -3.13 -X utf8 -m unittest discover -s tests -p "test_*leakage.py" -v
```

## W2-10 — trích tín hiệu từ snapshot lịch sử

`core/historical_signals.py` cung cấp `HistoricalSignalExtractor.extract(symbol,
as_of_date)` và `from_graph_builder`. Factory tái sử dụng `SetGraph.compile_upstream`
cho Indicator → Pattern → Trend, rồi gọi Alpha node ở chế độ nghiên cứu nghiêm ngặt.
Sentiment được tính từ cache tin đã chấm điểm, qua `FrozenSentimentSnapshot`.
Không có Decision Agent trong bước trích đặc trưng này.

### Đầu vào và cutoff

- Mặc định đọc giá bằng loader xác minh VCI của gate A. Cắt **trước** kiểm tra giá,
  chỉ truyền sáu cột OHLCV; không đưa Reference, MatchPrice, entry/exit hay outcome
  cho agent. Cần ít nhất 600 nến kết thúc đúng ngày quyết định.
- Indicator/Pattern/Trend nhận cửa sổ 45 nến mặc định. Alpha nhận cùng prefix đầy
  đủ để tuyển chọn/tính năm factor trên tối đa 600 nến. State và báo cáo upstream
  được sao chép sâu trước khi chuyển cho Alpha.
- Tạo ảnh trong bộ nhớ bằng `write_artifacts=False`; không ghi đè các file ảnh/CSV
  dùng chung tại thư mục gốc khi xử lý các điểm lịch sử.
- Chỉ đọc `sentiment_cache_<symbol>.json` có đúng mã và cấu trúc; không crawl khi
  file thiếu. Tin có ngày trong `[t - 90 ngày, t]` mới được tổng hợp; tin không
  ngày và tin ngoài cửa sổ bị loại. Ngày sai định dạng ném `ValueError`.
- Dưới ba bài hợp lệ: giữ chính sách strict research hiện có, trả `NEUTRAL`,
  `news_is_reliable=false`, ghi số bài và lý do `neutral-insufficient-dated-history`.
  Đây là tín hiệu trung tính do thiếu độ phủ tin, không được coi là sentiment
  lịch sử đáng tin cậy. W2-14 phải kiểm toán tỷ lệ thiếu phủ trước khi dùng kết quả.
- Alpha strict mode không che lỗi sentiment, tuyển chọn hoặc tính factor. Chế độ
  mặc định của các caller hiện tại được giữ nguyên; extractor bật strict mode.

### Tín hiệu và provenance

Kết quả là bundle độc lập, chưa phải `HistoricalTaskRecord`:

| Trường tín hiệu | Nguồn | Nhãn lưu |
| --- | --- | --- |
| `trend` | Trường Hướng xu hướng / Trend direction trong báo cáo đã chuẩn hóa | BULLISH, BEARISH, NEUTRAL |
| `pattern` | Trường Thiên lệch dự báo / Directional bias | BULLISH, BEARISH, NEUTRAL |
| `indicator_consensus` | Đồng thuận Python trong báo cáo Indicator | BULLISH, BEARISH, NEUTRAL; HỖN HỢP → NEUTRAL |
| `alpha_consensus` | So số factor TĂNG với GIẢM trong đúng năm `alpha_results` | BULLISH, BEARISH; bằng nhau → NEUTRAL |
| `sentiment` | Nhãn tổng hợp cache tin trong snapshot | POSITIVE, NEGATIVE, NEUTRAL |

Từ chối trường hướng thiếu/trùng, mẫu chưa điền, hướng không xác định, báo cáo
rỗng, thiếu năm factor, ID factor trùng hoặc nhãn factor sai; không gọi LLM thêm
để suy đoán tín hiệu. Giữ toàn bộ năm báo cáo để kiểm toán cách rút nhãn.

`provenance` ghi mã/ngày, provider/đơn vị/cơ sở giá, SHA-256 prefix giá và tin,
ngày đầu/cuối/số nến, khoảng 600 nến Alpha, tất cả ngày tin được dùng, độ phủ tin,
backend sentiment, model/nhiệt độ/token, cửa sổ/normalization/weights, phiên bản
Python/dependencies, hash mã nguồn và báo cáo, cùng năm factor thực tế. Scalar
NumPy được chuyển sang kiểu Python; NaN/Infinity không được lưu. API key không
được đưa vào provenance.

### Checkpoint và xử lý gián đoạn

Mỗi `(symbol, t)` có một JSON và khóa `.lock` riêng trong thư mục caller chọn:

1. `UPSTREAM_STARTED` được lưu trước khi gọi graph.
2. `UPSTREAM_COMPLETE` lưu báo cáo trước khi đọc nhãn và chạy Alpha/Sentiment.
3. `COMPLETE` chứa bundle tín hiệu/provenance; ghi nguyên tử kèm checksum.

Chạy lại điểm đã hoàn thành trả bundle đã lưu, không gọi upstream hay Alpha.
Lỗi Alpha có thể tiếp tục từ `UPSTREAM_COMPLETE`; upstream vẫn chỉ chạy một lần.
Khác prefix/cấu hình/mã nguồn/runtime hoặc checksum lỗi bị từ chối trước khi gọi
lại graph. Lock ngăn hai tiến trình cùng xử lý một điểm. Nếu tiến trình bị ngắt
giữa upstream, phải rà soát lock và checkpoint dở dang; hệ thống không tự chạy
lại thị giác khi chưa có báo cáo hoàn chỉnh đã lưu.

```python
from core.historical_signals import HistoricalSignalExtractor
from default_config import DEFAULT_CONFIG
from utils.graph_setup import SetGraph
from utils.graph_util import TechnicalTools

# Hai LLM phải được cấu hình đúng model/nhiệt độ/token ghi trong model_config.
builder = SetGraph(agent_llm, graph_llm, TechnicalTools())
extractor = HistoricalSignalExtractor.from_graph_builder(
    builder, "outputs/historical_signals", model_config=DEFAULT_CONFIG,
)
bundle = extractor.extract("FPT", "2020-06-01")
signals = bundle["agent_signals"]
```

W2-10 chưa fit thêm regime, ghép nhãn hay sinh kho >300 bản ghi. W2-12 phải dùng
model/scaler/calibration prefix có `train_end_date <= t`, theo W2-07; không đưa
artifact fit hết 2022 vào episode năm 2020. Provenance nằm ở bundle/checkpoint,
còn record W1 chỉ nhận năm trường `agent_signals` khi ghép với regime/nhãn.

### Kiểm thử W2-10

`tests/test_historical_signals.py` có 12 test, bao gồm graph/agent/Alpha Selector
và giá VCI thật với LLM giả lập xác định; ảnh vẫn được tạo bằng mã sản phẩm.
`tests/test_historical_signals_leakage.py` có 7 test về cutoff, thay giá/tin tương
lai, bản sao state, khởi động 600 nến, truyền lỗi và từ chối kết quả rò rỉ.
Toàn bộ fixture/checkpoint thử nghiệm nằm trong thư mục tạm, không phát hành
tín hiệu LLM giả lập vào Memory Bank nghiên cứu.

Bốn gate trước merge ngày 27/09/2026: compileall PASS, **185 unit tests** PASS,
E2E PASS (13,2 giây; upstream một lần mỗi điểm), **32 leakage tests** PASS.
Các lệnh tái lập dùng cùng bốn lệnh ở phần W2-09 phía trên.
