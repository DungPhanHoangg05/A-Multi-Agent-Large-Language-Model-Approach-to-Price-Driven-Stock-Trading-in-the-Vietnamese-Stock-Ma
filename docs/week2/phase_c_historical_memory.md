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

B?n gate tr??c merge ng?y 27/09/2026: compileall PASS, **166 unit tests** PASS,
E2E PASS (13,4 gi?y; upstream m?t l?n m?i ?i?m), **25 leakage tests** PASS.

```powershell
py -3.13 -m compileall agents core data_manager scripts tests utils
py -3.13 -X utf8 -m unittest discover -s tests -v
py -3.13 scripts/run_end_to_end_test.py
py -3.13 -X utf8 -m unittest discover -s tests -p "test_*leakage.py" -v
```
