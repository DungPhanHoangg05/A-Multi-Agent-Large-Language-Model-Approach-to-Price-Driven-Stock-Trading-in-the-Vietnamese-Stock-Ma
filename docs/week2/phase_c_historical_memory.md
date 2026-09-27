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

## W2-11 — bộ sinh nhãn kinh tế

`core/historical_outcomes.py` cung cấp `HistoricalOutcomeGenerator.generate`.
Loader mặc định xác minh bộ giá thô VCI; nhãn dùng đúng `Open(t+1)` và `Close(t+3)`
theo lịch phiên, qua cùng kiểm tra quyền/thanh khoản của gate A. `settled_as_of`
phải từ ngày thoát trở đi (sau đóng cửa); chu kỳ chưa tất toán bị từ chối trước
khi đọc giá nhãn.

Hàm gọi **chính** `compute_round_trip_net_return` của engine với phí `0.0025` và
slippage `0.001` ở cả hai chiều. `net_return_pct` giữ nguyên độ chính xác float,
không làm tròn. Net dương → `UP`/`WIN_IF_LONG`; net bằng không hoặc âm →
`DOWN`/`LOSS_IF_LONG`. Bull trap áp dụng quy tắc đã chốt W2-09: Trend hoặc Pattern
tăng nhưng LONG không có lợi nhuận ròng dương. Nhãn luôn là kết quả giả định LONG;
không suy ra lợi nhuận bán khống từ `BEARISH` hoặc `SHORT`, không mở vị thế.

```python
from core.historical_outcomes import HistoricalOutcomeGenerator

outcome = HistoricalOutcomeGenerator().generate(
    "FPT", "2020-06-01", "2020-06-02", "2020-06-04", signals,
    settled_as_of="2022-12-31",
)
```

Tám test kinh tế kiểm hàm engine/chi phí, tăng giá nhưng lỗ sau phí, bull trap,
net bằng không, lịch phiên, quyền/thanh khoản, JSON gốc và giá VCI thật trên bốn
mã; hai test leakage kiểm chu kỳ chưa tất toán và biến đổi giá sau ngày thoát.
W2-11 chỉ tạo bộ sinh nhãn, chưa phát hành nhãn hàng loạt hoặc Memory Bank.

Bốn gate trước merge ngày 27/09/2026: compileall PASS, **195 unit tests** PASS,
E2E PASS (13,7 giây), **34 leakage tests** PASS. Dùng bốn lệnh tái lập đã ghi ở W2-09.

## W2-12 — runner offline và tiếp tục từ checkpoint

`scripts/run_historical_memory.py` dùng `core/historical_runner.py` để ghép ba
thành phần W2-09/10/11. Giá và tin chỉ đọc từ dữ liệu/cache offline; tạo tín hiệu
thị giác vẫn gọi API Groq khi chạy chế độ sinh episode thật. `--plan-only` và
`--verify-only` không cần API key, không gọi LLM hoặc fit thêm model.

### Lịch chạy và model prefix

- Lịch giữ warm-up 600 nến, bước 3, quy tắc loại quyền/thanh khoản của gate A,
  chỉ nhận quyết định và ngày thoát trong 2018–2022. Thứ tự cố định theo
  `(as_of_date, symbol)`. Toàn bộ lịch có 868 ứng viên, 852 hợp lệ, 16 bị loại.
- `PrefixRegimeProvider` xác minh VN-Index W1 bằng manifest/checksum VCI/KBS.
  Mỗi ngày quyết định chỉ fit HMM/scaler/calibration trên prefix `2018-01-01..t`,
  cùng cấu hình Phase B và seed 42; artifact tại `regimes/VNINDEX-t.json`.
  Bốn mã có cùng ngày dùng lại một artifact. Khi tiếp tục, loader kiểm hash train,
  phiên bản và metadata rồi nạp model; không refit artifact đã có.
- Model đầy đủ `data_manager/regime_model.json` fit hết 2022 không được dùng cho
  episode năm 2020. `train_end_date` phải đúng ngày quyết định; feature và state
  không được vượt cutoff. Cơ sở giá VN-Index vẫn mang trạng thái nghiên cứu
  `UNVERIFIED` của Phase B; giá cổ phiếu và nhãn chỉ dùng bộ giá VCI đã mở gate A.
- Model LLM/nhiệt độ/token theo cấu hình hệ thống; temperature cố định 0, seed
  chạy 42. Phản hồi LLM được giữ bằng checkpoint. Mọi request của runner, kể cả
  dự phòng văn bản, đi qua `utils/historical_api._invoke_with_retry` qua adapter
  `RetryingLLM`: backoff cấp số nhân, chờ đủ `retry after X seconds` hoặc
  `try again in XmYs`. Chờ dài được chia đoạn tối đa 60 giây. Lỗi
  `ValueError`/`AssertionError` không được retry tại adapter.

### Thứ tự tạo episode và cấu trúc journal

1. Kiểm regime prefix trước khi gọi agent.
2. W2-10 trích/lấy lại năm tín hiệu đã checkpoint, chỉ nhận giá/tin `<= t`.
3. W2-11 tính outcome từ giá entry/exit trong đầu vào riêng, sau khi đã có tín
   hiệu. State upstream không nhận outcome, ngày vào/thoát hoặc giá tương lai.
4. Xác thực schema/ID/lịch/P&L của record, artifact regime, checksum tín hiệu,
   prefix giá, cutoff Alpha/tin và checksum báo cáo.
5. Ghi episode hoàn chỉnh nguyên tử, rồi xuất lại kho từ các episode đã xác thực.
   Lỗi dừng run ngay; record nửa chừng không vào journal/kho.

Thư mục staging mặc định `outputs/historical_memory_run` chứa:

| Đường dẫn | Vai trò |
| --- | --- |
| `run_manifest.json` | Cấu hình bất biến, lịch, hash giá/sự kiện/tin/VN-Index, mã nguồn, runtime và signature |
| `regimes/VNINDEX-YYYY-MM-DD.json` | HMM/scaler/calibration fit đúng prefix |
| `signals/SYMBOL-YYYY-MM-DD.json` | Checkpoint upstream và bundle W2-10 |
| `episodes/SYMBOL-YYYY-MM-DD.json` | Record W1 hoàn chỉnh và provenance regime/tín hiệu, kèm checksum/signature |
| `memory.json` | Danh sách record W1 đã hoàn thành, nạp được bằng `HistoricalMemory` |

Khi tiếp tục, runner xác minh lại manifest, mọi episode đã hoàn thành, model và
checkpoint tín hiệu; chỉ chạy điểm chưa có episode. Thay dữ liệu/cấu hình/mã
nguồn/runtime, journal có khoảng trống hoặc file ngoài lịch đều bị từ chối.
Hash archive tin đóng băng cả cache của run; cập nhật cache cần phiên chạy riêng.
JSON tín hiệu vẫn chỉ tổng hợp tin hợp lệ tại cutoff của từng điểm.

Gián đoạn sau khi episode đã lưu nhưng trước khi `memory.json` được xuất:
runner chấp nhận kho chậm đúng một episode, phục hồi từ journal đã xác thực rồi
tiếp tục, không gọi upstream lại. Kho khác nội dung journal bị từ chối ghi đè.
`--verify-only` báo lỗi khi kho cần phục hồi; chạy tiếp chế độ thường để phục hồi.
`run.lock` ngăn hai runner đồng thời; khóa còn lại sau process bị dừng đột ngột
phải được rà soát trước khi bỏ. Upstream dở dang vẫn áp dụng quy tắc W2-10, không
tự gọi lại thị giác khi chưa lưu được báo cáo hoàn chỉnh.

### Lệnh dùng

```powershell
# Chỉ kiểm dữ liệu và lịch, không tạo artifact hoặc gọi API.
py -3.13 -X utf8 scripts/run_historical_memory.py --plan-only

# Sinh một điểm mới vào staging; cần GROQ_API_KEY trong môi trường hoặc .env.
py -3.13 -X utf8 scripts/run_historical_memory.py --max-new-points 1

# Chạy cùng lệnh để tiếp tục, bỏ qua episode đã hoàn thành.
py -3.13 -X utf8 scripts/run_historical_memory.py --max-new-points 1

# Kiểm journal/kho; lặp lại cùng symbols/start/end nếu run dùng phạm vi riêng.
py -3.13 -X utf8 scripts/run_historical_memory.py --verify-only
```

`--max-new-points` giới hạn **số episode mới trong lần gọi hiện tại**, không đổi
lịch/signature. `--symbols`, `--start`, `--end` chốt phạm vi cho một thư mục run;
ngày `--end` là ngày tất toán muộn nhất. Để đổi phạm vi dùng `--output-dir` khác.
W2-13 sẽ chạy sinh kho >300 episode và phát hành vào
`data_manager/regime_memory_store.json`; W2-12 chưa tạo file nghiên cứu chính thức.

### Kiểm thử W2-12

Chín test runner, bốn test leakage và ba test retry. Kiểm thử tích hợp chạy hai
episode FPT/MWG cùng ngày bằng giá VCI, HMM/scaler/calibration, graph, ảnh,
Alpha Selector và nhãn engine thật; chỉ phản hồi LLM được giả lập. Kiểm tra fit
HMM một lần, upstream một lần mỗi điểm, tiếp tục không sinh trùng và kho nạp
được bằng `HistoricalMemory`. Các test gián đoạn/model tương lai/tin tương lai
kiểm tra không có episode nửa chừng. Toàn bộ output thử nghiệm nằm trong thư
mục tạm; không đưa tín hiệu LLM giả lập vào kho nghiên cứu.

Bốn gate trước merge ngày 27/09/2026: compileall PASS, **211 unit tests** PASS,
E2E PASS (13,0 giây), **38 leakage tests** PASS. Dùng bốn lệnh tái lập ở W2-09.
Lệnh CLI `--plan-only` đã chạy trên bộ dữ liệu thật: **868 ứng viên, 852 hợp lệ,
16 bị loại**, bốn điểm đầu có ngày quyết định 2020-06-01 và thoát 2020-06-04.
Không tạo thư mục run hay file `data_manager/regime_memory_store.json` trong
lần triển khai W2-12; các journal tích hợp thử nghiệm đã được dọn cùng thư mục tạm.
