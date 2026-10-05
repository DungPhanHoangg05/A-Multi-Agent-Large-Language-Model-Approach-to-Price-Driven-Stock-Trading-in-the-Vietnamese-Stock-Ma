# Phase B — retriever và thống kê

**Trạng thái: W3-05/W3-06 hoàn thành; W3-07..09 chưa thực hiện.** File nền đã có:
`core/bayesian_retriever.py`, `tests/test_bayesian_retriever.py`,
`tests/test_bayesian_statistics.py`.

Gate A đã PASS; dùng [API](retriever_api_contract.md),
[luật chọn prior](prior_selection_method.md) và
[stats/BRPP](statistics_and_prefix_contract.md) đã khóa. Gate B chưa đóng.

## W3-05 — kho và cutoff

- [x] Nạp/xác minh kho một lần bằng `HistoricalMemory`; giữ hash/version trong metadata.
- [x] Tái dùng `eligible()` hoặc index tương đương có cùng bất biến; lọc trước ranking
  và thống kê. Không đặt cache chỉ theo regime mà bỏ qua cutoff/scope/bank version.
- [x] Kiểm pool/population và cung cấp chốt `_validate_selection` cho bộ chọn ở task sau:
  ID duy nhất, record nguyên bản, cutoff/scope/regime, không vượt K; vi phạm ném lỗi.
- [x] Kết quả deep copy; pool/population không chia sẻ record mutable, sửa query trước
  không làm thay đổi query sau.
- [x] Test ngày bằng cutoff, chu kỳ vắt qua cutoff, pool rỗng, mã/ngày sai và K=0.

## W3-06 — recent và random

- [x] Recent xếp ngày exit và ID theo quy tắc Gate A, không lấy theo thứ tự file.
- [x] Random RNG cục bộ, seed theo query cố định; lấy không hoàn lại từ pool ổn định.
- [x] Test lặp query, đảo thứ tự gọi/record, K vượt số mẫu, không trùng ID; seed khác
  không bắt buộc luôn khác kết quả khi pool quá nhỏ.
- [x] Metadata nêu số mẫu thật và lý do thiếu K; không bù từ ngoài scope/cutoff.

## W3-07 — similarity

- [ ] Ánh xạ tín hiệu theo bảng khóa ở A; điểm nằm trong miền đã đặc tả.
- [ ] Không dùng outcome hoặc đặc trưng tính từ dữ liệu sau query; không fit embedding/scaler
  bằng dữ liệu OOS. Với metric so khớp tín hiệu, không cần gọi LLM/embedding API.
- [ ] Test điểm khớp hoàn toàn/một phần, trường hằng/không rõ và tie-break xác định.
- [ ] Đổi outcome của record trong fixture hợp lệ không được đổi ranking dựa trên tín hiệu.

## W3-08 — bayesian_regime

- [ ] Lấy cùng regime từ pool chung; dùng ranking đã chốt, không ưu tiên WIN sau khi
  nhìn nhãn và không tự đổi regime khi thiếu mẫu.
- [ ] Test bốn regime, regime thiếu/rỗng, K<3; trả score/IDs/lý do để kiểm toán.
- [ ] Đối chiếu với similarity trên cùng pool để chứng minh bộ lọc regime hoạt động đúng.

## W3-09 — thống kê

- [ ] Tính count/win-rate/trap và mẫu số riêng từ tập eligible cùng scope/regime.
- [ ] Không dùng K đã chọn làm đại diện độ tin cậy toàn regime; ghi population/selected
  counts riêng. Không dùng thống kê toàn kho cho cutoff lịch sử.
- [ ] Fixture nhỏ có WIN/LOSS/bullish/neutral, tính tay để so từng numerator/denominator.
- [ ] Kiểm n=0, không bullish, return bằng 0, JSON `null`, không NaN/NumPy scalar.
- [ ] Tái dùng quy tắc bullish/nhãn W2; không sửa record hoặc tính lại P&L bằng công thức mới.

**Gate B:** API bốn mode và stats có test xác định PASS, không có network/LLM,
input/result không bị mutate, metadata đủ cho Phase C và bàn giao W4.

## Kết quả và nhật ký

### 04/10/2026 — W3-05 hoàn thành

- Module `core/bayesian_retriever.py`: constructor khớp API, đối chiếu hash kho/schema,
  format/signature/QA PASS/counts/độ phủ, rồi `HistoricalMemory.load()` kiểm giá/P&L
  một lần. File thay đổi trong lúc nạp bị từ chối; toàn bộ alias cũng được kiểm.
- `prepare_query()` kiểm query, trả `eligible_tasks`, `regime_population`, metadata
  cutoff/scope/counts/hash/version trước ranking/stats. Không cache theo ngày/regime
  nên gọi ngày sau rồi ngày trước vẫn lọc đúng. Hai danh sách trả bản sao độc lập.
- `_assert_pool()`/`_validate_selection()` chặn ID trùng, record sửa so với snapshot,
  NumPy scalar thay giá trị Python, cutoff/scope/regime sai hoặc quá K.
- `retrieve(k=0)` trả đúng disabled/tasks rỗng/stats None/counts None; query sai vẫn
  ValueError. `retrieve(k>0)` hiện ném **NotImplementedError**, không giả kết quả
  empty/complete: ranking thuộc W3-06..08, stats thuộc W3-09. Đây là phạm vi task nền.
- [Receipt kho thật](retriever_foundation_review.json): 852 record, loader giá đúng
  một lần/FPT/MWG/VCB/VNM; hot query chặn JSON/CSV/giá vẫn PASS. Scope FPT có 211
  eligible/83 BULL, pooled có 852/337 BULL; cutoff exit đầu 04/06/2020 trả rỗng.
  Regime BULL của probe là fixture đầu vào, không khẳng định VN-Index tại 03/01/2023.
- 14 test mới (11 nền + 3 leakage) dùng validator/engine thật trên fixture giá trong
  thư mục tạm. Phát hiện và sửa alias giữa pool/population; không sửa bank/model W2.

Lệnh kiểm nền:

```powershell
py -3.13 -X utf8 -m unittest discover -s tests -p 'test_bayesian_retriever*.py' -v
```

Kết quả và gate tích hợp cuối cùng ghi tại README. **Gate B còn mở**; tiếp theo
W3-06 Recent/Random, rồi Similarity/Bayesian và stats theo thứ tự đã chốt.

### 05/10/2026 — W3-06 hoàn thành

- `_select_recent()` dùng exit giảm dần, ID tăng dần để phá hòa; không phụ thuộc
  thứ tự record trong file. `_select_random()` dùng payload/digest/RNG local chính
  xác theo policy v1, sample không hoàn lại từ pool sắp ID, giữ thứ tự draw.
- `select_prior_tasks(...)` có cùng chữ ký query, trả `tasks`, `regime_population`,
  `metadata`. Recent/Random hoạt động với K=1..3; K=0 disabled, pool rỗng empty,
  thiếu K partial. IDs/counts/score None/status/reason/effective_seed đúng hợp đồng.
- Bộ chọn gọi chốt hậu điều kiện W3-05; tasks/population là bản sao độc lập,
  không sửa input/kho và không đọc lại giá/JSON. Không tự đổi scope để đủ K.
- Tám test mới (bảy Recent/Random + một leakage) PASS: tie-break, seed/draw tham chiếu,
  thứ tự query/kho, global RNG, thêm lịch sử tương lai hợp lệ, empty/partial/K=0,
  bản sao và bộ chọn bị giả lập trả prior vi phạm cutoff/ID.
- [Receipt kho thật](recent_random_review.json): 16 query = bốn mã × hai scope ×
  hai mode; lặp query, biên exit, empty/partial và chặn I/O đều PASS trên 852 record.
  BULL là fixture context cho probe, không tuyên bố regime thực tế tại cutoff/OOS.
- Stats chưa được tính trong task này. `select_prior_tasks` là kết quả của bước
  chọn, **không phải** result retrieve hoàn chỉnh; `retrieve(K>0)` còn dừng tường minh
  đến khi stats W3-09 được tích hợp. Similarity/Bayesian tiếp tục ở W3-07/W3-08.

Lệnh kiểm tập trung:

```powershell
py -3.13 -X utf8 -m unittest discover -s tests -p 'test_bayesian_*.py' -v
```

22 test nền/chọn/leakage PASS. Gate tích hợp cuối ghi tại README; Gate B còn mở.
