# Phase D — kiểm thử, hiệu năng và bàn giao W4

**Trạng thái: chưa thực hiện.** Bắt đầu sau Gate C.

## W3-13 — hành vi và zero-leakage

- [ ] Hợp nhất test truy vấn/mode/stats/prefix đã làm; bổ sung lỗi đầu vào và serializable.
- [ ] `tests/test_bayesian_retriever_leakage.py`: mọi mode loại `exit_date == cutoff`,
  `exit_date > cutoff` và episode bắt đầu trước nhưng kết thúc sau cutoff.
- [ ] Thêm/đổi record tương lai trong fixture hợp lệ không đổi IDs, stats hoặc prefix
  của query cũ; kiểm cả cache khi lần lượt gọi ngày sau rồi ngày trước.
- [ ] Sai hậu điều kiện từ nguồn eligible bị giả lập phải ném lỗi, không silently lọt prior.
- [ ] Tách query signals khỏi outcome; kiểm không thay state/record giữa các nhánh.
- [ ] Prefix không chứa nhãn kết quả của test point; thống kê không nhìn toàn kho
  khi cutoff lịch sử loại một phần record.

## W3-14 — benchmark retrieval

File dự kiến `scripts/benchmark_bayesian_retriever.py`, receipt
`docs/week3/retrieval_benchmark.json` và biên bản hiệu năng trong file này.

**Phép đo đề xuất khóa tại W3-01 trước khi chạy benchmark:**

- Dùng kho thật 852 record và query cố định bao phủ bốn mã/bốn regime, K=3;
  ghi nguồn regime của query. Cùng tập query/config cho mọi mode.
- Đo cold load/xác minh kho riêng; hot query gồm lọc eligible, ranking, thống kê,
  metadata và deep copy. Đo formatter riêng và end-to-end retrieval+format riêng.
- Dùng `perf_counter_ns`, 100 lượt warm-up/mode và ít nhất 1.000 lượt đo/mode;
  luân phiên query để không chỉ đo một điểm cache trúng. Ghi query count, cache và
  min/median/p95/max; đo tuần tự để tránh nhiễu tranh tài nguyên.
- **Gate retrieval:** p95 hot query **<30 ms ở từng mode**, không chỉ trung bình gộp.
  Không tính I/O nạp kho/LLM vào gate; vẫn báo thời gian cold load công khai.
- Ghi Python/dependency/CPU/OS, bank hash, seed/config, phương pháp percentile và ngày đo.
  Threshold không đặt làm unit test thời gian dễ chập chờn trên máy khác.

- [ ] Script/receipt tái lập, đủ bốn mode và môi trường.
- [ ] Nếu vượt ngưỡng: chỉ tối ưu nút chậm đã đo; không bỏ validation/cutoff/deep copy.
- [ ] Sau tối ưu chạy lại test liên quan và benchmark cùng phép đo; không đổi gate
  sau khi nhìn kết quả để báo PASS.

## W3-15 — gate tích hợp

Chạy tại thư mục gốc repo:

```powershell
py -3.13 -m compileall agents core data_manager scripts tests utils
py -3.13 -X utf8 -m unittest discover -s tests -v
py -3.13 scripts/run_end_to_end_test.py
py -3.13 -X utf8 -m unittest discover -s tests -p 'test_*leakage.py' -v
```

- [ ] Bốn gate PASS; ghi số test/thời gian/commit, không dùng kết quả W2 thay kết quả W3.
- [ ] Diff không đổi engine P&L, upstream ghép cặp, artifact kho/model hoặc cơ chế retry.
- [ ] Gate smoke/600 ký tự/6.500 ký tự/30 ms có bằng chứng trước merge.

## W3-16 — chốt và bàn giao

- [ ] Đủ module, formatter, unit/leakage tests, smoke, benchmark, đặc tả đã khóa.
- [ ] Ghi API/example cho W4: regime PIT và tín hiệu hiện tại vào query; tasks/stats,
  BRPP/IDs/hash/seed/fallback ra ngoài; Original K=0 không nhận prefix.
- [ ] Nêu rõ việc W4 cần làm: trường state, inject Decision, ablation flag, checkpoint
  metadata, paired upstream và chốt giới hạn prompt tại runtime.
- [ ] Giữ giới hạn tin/độ phủ/gate giá 2023–2024; W3 không phát hành kết quả lợi nhuận OOS.
- [ ] Cập nhật README W3, kế hoạch tổng và biên bản chốt; Conventional Commit/merge
  từ nhánh task vào `develop` sau đủ gate; không đưa mã tuần/ngày vào commit message.

## Kết quả và nhật ký

Chưa có kết quả thực thi. Điền bảng gate, receipt hiệu năng, giới hạn và commit khi hoàn thành.
