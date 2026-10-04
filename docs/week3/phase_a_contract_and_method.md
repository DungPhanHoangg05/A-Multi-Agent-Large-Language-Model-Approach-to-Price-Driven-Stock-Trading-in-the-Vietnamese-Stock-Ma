# Phase A — chốt hợp đồng truy xuất và phương pháp

**Trạng thái: chưa thực hiện.** Các quy tắc dưới đây là đề xuất để khóa ở Phase A;
mọi thay đổi phải ghi lý do trước khi dùng kết quả kiểm định 2023–2024.

## W3-01 — đầu vào

- [ ] Đối chiếu kho với manifest/QA, schema và số 852; ghi hash, độ phủ theo mã/regime.
- [ ] Kiểm tra `HistoricalMemory.load/eligible/records` để tái dùng xác minh và deep copy;
  xác định chi phí nạp một lần, không đọc CSV/kiểm giá lại trong mỗi query.
- [ ] Ghi giới hạn warm-up, sentiment hằng và giá 2023–2024 chưa qua gate.
- [ ] Chốt đầu ra W3 độc lập; tích hợp state/graph/Decision/backtest ở W4.

**Bằng chứng:** cập nhật mục kết quả cuối file, chỉ rõ hash và hàm được tái sử dụng.

## W3-02 — API

Đề xuất `BayesianPriorRetriever.retrieve(...)` nhận `symbol`, `as_of_date`,
`current_regime`, `current_signals`, `mode`, `k=3`, `seed=42`, `scope`.
Regime là đầu vào đã xác minh PIT; retriever không tự fit HMM hoặc gọi upstream.

- [ ] Khóa kiểu và validation: mã/ngày/regime/mode hợp lệ, K nguyên không âm,
  giới hạn K hỗ trợ cho BRPP, seed nguyên, tín hiệu đủ cho mode cần similarity.
- [ ] Chốt `scope`: đề xuất mặc định cùng mã; tùy chọn pooled bốn mã phải tường minh
  và dùng giống nhau cho cả bốn mode trong một thí nghiệm. Không tự mở rộng scope khi thiếu K.
- [ ] Chốt result: `tasks`, `stats`, `metadata` (mode, scope, seed, cutoff, regime,
  bank hash, số eligible/cùng regime/selected, IDs, score, lý do thiếu mẫu).
- [ ] K=0 trả tasks rỗng; nhánh Original không nhận BRPP hoặc thống kê. Pool rỗng
  là kết quả hợp lệ có lý do, đầu vào sai hoặc hậu điều kiện cutoff sai phải ném lỗi.
- [ ] Không làm thay đổi record gốc; trả kiểu Python gốc có thể JSON serialize.

## W3-03 — luật chọn prior

Pool chung: kho hợp lệ → `exit_date < as_of_date` → scope đã chốt. Record không
đủ cutoff được loại bởi bộ lọc; nếu lọt vào kết quả/stats, ném `ValueError`/`AssertionError`.

| Mode | Đề xuất phải chốt | Khi ít hơn K |
| --- | --- | --- |
| `recent` | `exit_date` giảm dần, tie-break `episode_id` tăng dần | Lấy số hiện có |
| `random` | Lấy không hoàn lại từ pool đã sắp ID; RNG cục bộ theo seed và query bằng hash ổn định, không dùng `hash()` Python | Lấy số hiện có |
| `similarity` | Điểm so khớp hướng tín hiệu; score giảm dần, rồi ngày exit giảm dần, rồi ID tăng dần | Lấy số hiện có |
| `bayesian_regime` | Lọc cùng regime, chọn similarity cao nhất, tie-break giống similarity | Giữ cùng regime, không bù khác regime |

- [ ] Khóa bảng ánh xạ mỗi tín hiệu sang hướng chuẩn; dùng helper hiện có khi phù hợp,
  từ chối giá trị không rõ thay vì tự suy diễn hướng từ đoạn văn.
- [ ] Đề xuất similarity dùng tỷ lệ khớp của bốn trường Trend/Pattern/Alpha/Indicator,
  trọng số bằng nhau; sentiment không góp điểm vì cả kho thiếu tin. Nếu bổ sung tin,
  phải đổi phiên bản metric và kiểm tra lại trước thí nghiệm.
- [ ] Không dùng return, WIN/LOSS, bull trap hoặc nhãn tương lai của query để chọn K.
- [ ] Ghi metric/weight/seed/tie-break/scope vào cấu hình và receipt; không tuning trên OOS.

## W3-04 — thống kê và BRPP

Đề xuất thống kê từ **toàn bộ pool cùng regime sau cutoff/scope**, không chỉ K ví dụ.
Ghi cùng thống kê cho các nhánh prior đối chứng để khác biệt chính là cách chọn task;
phải khóa quy tắc này trước chạy pilot. Original không nhận thống kê.

- [ ] Win-rate LONG: `wins / n`, với wins là `WIN_IF_LONG`; đây là nhãn LONG giả định
  sau phí, không phải hit-rate lệnh LONG thực tế của Decision.
- [ ] Bull trap có điều kiện: số bullish Trend hoặc Pattern nhưng LOSS chia cho số
  episode có ít nhất một trong hai tín hiệu bullish; ghi thêm tổng số trap/n nếu dùng.
- [ ] False bullish riêng từng agent: số bullish nhưng LOSS / số bullish của agent;
  không coi mọi LOSS là false breakout hoặc suy ra độ tin cậy của Sentiment Agent.
- [ ] Mẫu số 0 → `null`/không đủ mẫu, không 0% và không NaN; luôn có count hỗ trợ.
- [ ] Nếu thêm Beta smoothing: khóa alpha/beta và công thức trước, lưu riêng tỷ lệ mẫu
  và ước lượng làm trơn. Không bắt buộc thêm smoothing để đạt W3; không gọi empirical rate
  là posterior hiệu chuẩn hay chứng minh LLM suy diễn Bayes.
- [ ] Khóa template, đơn vị `len(text)` (ký tự Unicode), làm tròn và n=0/K=0/K<3;
  không có dấu hiệu sentiment đáng tin khi dữ liệu thực tế thiếu tin.

**Gate A:** bốn task trên đủ biên bản quyết định; không còn lựa chọn mở ảnh hưởng
scope, metric, thống kê hoặc đối chứng. Cập nhật đặc tả phương pháp nếu cần.

## Kết quả và nhật ký

Chưa có kết quả thực thi. Điền ngày, quyết định đã khóa, file/commit và kiểm tra khi làm task.
