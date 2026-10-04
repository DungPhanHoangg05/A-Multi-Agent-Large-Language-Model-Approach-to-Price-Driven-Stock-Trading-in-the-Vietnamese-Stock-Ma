# Phase B — retriever và thống kê

**Trạng thái: chưa thực hiện.** Bắt đầu sau Gate A. File dự kiến:
`core/bayesian_retriever.py`, `tests/test_bayesian_retriever.py`,
`tests/test_bayesian_statistics.py`.

## W3-05 — kho và cutoff

- [ ] Nạp/xác minh kho một lần bằng `HistoricalMemory`; giữ hash/version trong metadata.
- [ ] Tái dùng `eligible()` hoặc index tương đương có cùng bất biến; lọc trước ranking
  và thống kê. Không đặt cache chỉ theo regime mà bỏ qua cutoff/scope/bank version.
- [ ] Kiểm lại mọi task đầu ra: ID duy nhất, thuộc pool, exit trước query; kiểm cả
  tập dùng thống kê. Vi phạm phải ném lỗi.
- [ ] Kết quả deep copy; sửa kết quả query trước không làm thay đổi query sau.
- [ ] Test ngày bằng cutoff, chu kỳ vắt qua cutoff, pool rỗng, mã/ngày sai và K=0.

## W3-06 — recent và random

- [ ] Recent xếp ngày exit và ID theo quy tắc Gate A, không lấy theo thứ tự file.
- [ ] Random RNG cục bộ, seed theo query cố định; lấy không hoàn lại từ pool ổn định.
- [ ] Test lặp query, đảo thứ tự gọi/record, K vượt số mẫu, không trùng ID; seed khác
  không bắt buộc luôn khác kết quả khi pool quá nhỏ.
- [ ] Metadata nêu số mẫu thật và lý do thiếu K; không bù từ ngoài scope/cutoff.

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

Chưa có kết quả thực thi. Sau từng task điền file, lệnh test, số test và kết quả.
