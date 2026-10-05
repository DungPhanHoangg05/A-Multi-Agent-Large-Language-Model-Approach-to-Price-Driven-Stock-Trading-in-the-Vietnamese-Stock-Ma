# Phase B — retriever và thống kê

**Trạng thái: W3-05..09 hoàn thành; Gate B PASS ngày 05/10/2026.** Các file đã có:
`core/bayesian_retriever.py`, `tests/test_bayesian_retriever.py`,
`tests/test_bayesian_statistics.py`.

Gate A đã PASS; dùng [API](retriever_api_contract.md),
[luật chọn prior](prior_selection_method.md) và
[stats/BRPP](statistics_and_prefix_contract.md) đã khóa. API retrieve đầy đủ và stats
đã nghiệm thu; Phase C tiếp tục formatter BRPP.

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

- [x] Ánh xạ tín hiệu theo bảng khóa ở A; điểm nằm trong miền đã đặc tả.
- [x] Không dùng outcome hoặc đặc trưng tính từ dữ liệu sau query; không fit embedding/scaler
  bằng dữ liệu OOS. Với metric so khớp tín hiệu, không cần gọi LLM/embedding API.
- [x] Test điểm khớp hoàn toàn/một phần, trường hằng/không rõ và tie-break xác định.
- [x] Đổi outcome của record trong fixture hợp lệ không được đổi ranking dựa trên tín hiệu.

## W3-08 — bayesian_regime

- [x] Lấy cùng regime từ pool chung; dùng ranking đã chốt, không ưu tiên WIN sau khi
  nhìn nhãn và không tự đổi regime khi thiếu mẫu.
- [x] Test bốn regime, regime thiếu/rỗng, K<3; trả score/IDs/lý do để kiểm toán.
- [x] Đối chiếu với similarity trên cùng pool để chứng minh bộ lọc regime hoạt động đúng.

## W3-09 — thống kê

- [x] Tính count/win-rate/trap và mẫu số riêng từ tập eligible cùng scope/regime.
- [x] Không dùng K đã chọn làm đại diện độ tin cậy toàn regime; ghi population/selected
  counts riêng. Không dùng thống kê toàn kho cho cutoff lịch sử.
- [x] Fixture nhỏ có WIN/LOSS/bullish/neutral, tính tay để so từng numerator/denominator.
- [x] Kiểm n=0, không bullish, return bằng 0, JSON `null`, không NaN/NumPy scalar.
- [x] Tái dùng quy tắc bullish/nhãn W2; không sửa record hoặc tính lại P&L bằng công thức mới.

**Gate B — PASS:** API bốn mode và stats có test xác định PASS, không có network/LLM,
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

### 05/10/2026 — W3-07 hoàn thành

- `_select_similarity()` dùng `signal_match_v1`: mỗi trường trend/pattern/alpha/indicator
  khớp đóng góp 0,25; NEUTRAL khớp vẫn tính điểm. Sentiment được kiểm alias nhưng có
  trọng số 0. Score là float Python trong {0; 0,25; 0,5; 0,75; 1}; không có threshold.
- Chọn từ toàn pool eligible theo scope, không lọc regime; thứ tự score giảm dần →
  exit giảm dần → ID tăng dần. Metadata giữ IDs/scores/counts/status/reason, effective
  seed None. Chỉ chuẩn hóa bản sao tín hiệu để tính điểm; task trả nguyên nội dung kho.
- Chín test mới PASS: các mức điểm, NEUTRAL, alias/NFC, sentiment hằng/khác, nhãn sai,
  ranking B,C,A tham chiếu, đảo thứ tự, empty/partial/K=0, không I/O hoặc mutate,
  record tương lai và hậu điều kiện. Fixture đổi LOSS thành WIN bằng giá hợp lệ và
  `compute_round_trip_net_return`, nạp lại qua validator thật: IDs/scores không đổi.
- Test leakage của bộ chọn đã mở rộng sang Similarity: exit bằng cutoff bị loại;
  query ngày sau rồi ngày trước vẫn đúng. Tổng 31 test Bayesian tập trung PASS.
- [Receipt kho thật](similarity_review.json): tám query = bốn mã × hai scope,
  kiểm ranking/score, lặp query, JSON float hữu hạn, cutoff và empty/partial. Query
  dùng tín hiệu/regime fixture; không suy ra trạng thái thị trường tại ngày query
  hoặc kết quả giao dịch OOS. Các receipt cũ là snapshot mã ở thời điểm task trước.
- `retrieve(K>0)` vẫn chờ stats W3-09; `select_prior_tasks` chỉ là bước chọn task.
  Gate tích hợp ghi tại README. Gate B còn mở; tiếp theo W3-08 rồi W3-09.

### 05/10/2026 — W3-08 hoàn thành

- `select_prior_tasks(mode="bayesian_regime")` dùng `regime_population` của
  `prepare_query`: lọc exit < cutoff, scope và cùng regime trước khi lấy K.
  Dùng chính `_select_similarity()` nên metric/tie-break/score 0/alias không lệch
  với nhánh Similarity. Không ưu tiên WIN, không suy regime từ outcome.
- Chốt `_validate_selection` xác nhận record nguyên bản, cutoff, scope, regime,
  ID duy nhất và số task ≤ K. Tasks/population/metadata là bản sao độc lập.
- K=0 disabled; pool chung rỗng empty/no_eligible_history; có lịch sử nhưng thiếu
  cùng regime empty/no_matching_regime; thiếu K partial/insufficient_candidates.
  Không đổi scope/regime để bù K. Candidate count bằng matched regime count;
  score là float Python, effective seed None. Seed vẫn được kiểm kiểu/miền.
- Chín test bộ chọn mới PASS: bốn regime, scope và K=1..3, score 0, query sai,
  empty/partial/K=0, ranking C,A,D theo ví dụ Gate A so với Similarity B,C,A,
  đảo thứ tự kho/query, seed không ảnh hưởng, không mutate/I/O và hậu điều kiện.
  Fixture đổi giá và nhãn LOSS thành WIN qua engine/validator thật giữ nguyên IDs/scores.
- Một leakage mới chặn pool giả lập đưa record tương lai cùng regime vào query;
  test cutoff của bộ chọn mở rộng sang cả bốn mode. Thêm record tương lai hợp lệ
  không đổi lựa chọn cũ. Tổng 41 test Bayesian tập trung PASS.
- [Receipt kho thật](bayesian_regime_review.json): 32 query Bayesian = bốn mã × hai
  scope × bốn regime, đối chiếu 32 query Similarity; cùng pool, cùng score/tie-break,
  lọc regime trước top K, metadata native JSON, lặp query và biên thiếu mẫu đều PASS.
  Chặn đọc JSON/CSV/giá trong hot query. Regime/signals là fixture; không gọi HMM,
  LLM hoặc suy luận trạng thái thị trường tại cutoff. Receipt cũ là snapshot task trước.
- Gate tích hợp ghi tại README. **Gate B còn mở**: bốn bộ chọn đã hoàn thành,
  `retrieve(K>0)` vẫn ném NotImplementedError vì chưa tích hợp stats W3-09.

### 05/10/2026 — W3-09 hoàn thành, đóng Phase B

- `_compute_statistics()` kiểm population nguyên bản/PIT/scope/regime/ID rồi tính
  win_rate_long, bull_trap_rate, trend_false_bullish_rate, pattern_false_bullish_rate.
  Bullish tái dùng `is_bullish` W2 trên nhãn chuẩn hóa; trap dùng union OR và LOSS,
  không đếm đôi Trend/Pattern. Kiểm nhãn was_bull_trap từng record; sai ném ValueError.
- Dùng WIN/LOSS đã xác minh qua engine khi nạp kho, không tính lại return hoặc sửa
  hợp đồng T+2.5. Tỷ lệ là numerator/denominator chưa làm tròn, không smoothing;
  mẫu số 0 giữ numerator 0/rate None. Count/rate đều là kiểu Python gốc hữu hạn.
- `retrieve` gọi bước chọn/pool một lần, giữ tasks/metadata và bổ sung stats từ
  toàn regime_population. K>0 luôn có stats object, kể cả không có mẫu; n phải
  khớp matched_regime_count. K=0 bỏ qua pool/stats và giữ đúng result disabled.
  Bốn mode và K=1..3 dùng chung stats khi cùng cutoff/scope/regime.
- 11 test stats mới PASS trên fixture giá không chồng chu kỳ, nhãn engine/validator
  thật: tham chiếu W3-04 (win 2/4, trap 2/3, TrendFail 1/2, PatternFail 2/2), scope,
  regime, K/mode, sample n=1, no-bullish, ròng đúng 0, alias, JSON null/native,
  không mutate/I/O, count mismatch, nhãn trap hoặc record sai bị chặn.
- Ba test leakage mới PASS: query ngày sau rồi ngày trước và biên exit; thêm lịch
  sử tương lai hợp lệ hoặc đổi giá/nhãn tương lai không đổi stats/IDs query cũ;
  population tương lai bị đưa vào sau bước chọn vẫn gây ValueError. Tổng 55 test
  Bayesian tập trung PASS. Không sửa corpus/model hay dữ liệu đầu vào W2.
- [Receipt runtime](statistics_runtime_review.json): 384 query chính = bốn mã × hai
  scope × bốn regime × bốn mode × ba K, cộng 128 query lặp và các biên empty/
  no_matching_regime/partial/disabled. Đối chiếu từng numerator/denominator/rate
  với phép tính độc lập và thống kê Phase A; toàn pooled = 852 record/344 WIN/338 trap.
  Chặn I/O JSON/CSV/giá trong hot query; không gọi HMM hoặc LLM. Tín hiệu/regime
  query là fixture, không tuyên bố trạng thái thị trường tại cutoff hay lợi nhuận OOS.
- Bốn gate tích hợp PASS (chi tiết README); Gate B PASS, API đầy đủ sẵn sàng cho
  **W3-10**. Chưa có formatter/prompt gate/p95 hoặc bàn giao tích hợp W4; Phase C/D
  tiếp tục theo thứ tự đã khóa. Các receipt cũ là snapshot lịch sử từng task.
