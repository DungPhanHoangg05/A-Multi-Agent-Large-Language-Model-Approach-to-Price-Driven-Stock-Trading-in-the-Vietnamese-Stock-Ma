# Phase C — Context PIT, năm nhánh ghép cặp và resume

**Trạng thái: W4-09..11 hoàn thành, Phase C 3/4 ngày 06/10/2026.**
[Biên bản/API adapter](prior_context_adapter.md), [receipt](prior_context_review.json),
[paired runtime](paired_prior_point.md), [receipt](paired_prior_point_review.json),
[walk-forward/kết quả](prior_backtest_integration.md), [receipt](prior_backtest_review.json),
[checklist W4](README.md). Gate C còn W4-12.
Đầu vào: hợp đồng Phase A và graph/Decision Phase B. W4 cài adapter/runtime;
CLI điều phối pilot `scripts/run_bayesian_ablation.py` thuộc W5.

## W4-09 — Adapter context và regime PIT

**Phụ thuộc:** Gate A, W4-05. **File khảo sát/tái sử dụng:**
`core/regime_detector.py`, `core/historical_runner.py`, `core/historical_signals.py`,
`core/backtest_engine.py`; adapter đã cài `core/prior_context.py`.

- [x] Nhận snapshot đúng symbol/cutoff/timeframe và proof giá/tin/regime từ provider;
  validate state/date/source/hash trước xây query. Không coi enum BULL/BEAR là proof.
- [x] Cài hai đường đã khóa: replay prefix đúng ngày và artifact train đóng băng
  trước query OOS. Tái sử dụng validator phù hợp, kiểm HMM/scaler/calibration và
  feature end. Không fit/tải dữ liệu trong retrieval hoặc tự đổi provider khi thiếu.
- [x] Chốt provenance thực tế đủ để xác minh model/source; file/hash/date tự khai
  không đối chiếu artifact thật phải bị từ chối ở chế độ nghiên cứu.
- [x] Xây `current_signals` từ báo cáo đã hoàn thành tại cutoff theo normalizer
  đã có; xử lý report thiếu/mẫu hướng theo hợp đồng, không dùng actual direction.
- [x] Cắt giá/feature và kiểm tin PIT trước khi agent dùng; bỏ tin không ngày,
  giữ coverage/lý do NEUTRAL. Mọi input tương lai đã lọt vào context gây lỗi.
- [x] Kiểm fixture model train tương lai, cutoff lệch, hash sai, feature/news
  tương lai; ca model train end <cutoff hợp lệ và prefix lịch sử đúng ngày.

**Nghiệm thu:** adapter trả context/signals/provenance JSON hợp lệ; input lỗi
dừng trước retrieve/Decision. Test dùng artifact nhỏ xác định, không fit HMM
hoặc dựa vào archive local trong unit suite.

## W4-10 — Chuẩn bị báo cáo chung và tách năm Decision

**Phụ thuộc:** Gate B, W4-09. **File chính:** `core/backtest_engine.py`,
`utils/graph_setup.py`, `tests/test_paired_protocol.py`.

- [x] Chạy Indicator → Pattern → Trend một lần cho mỗi test point; chuẩn bị
  Alpha/Sentiment Full một lần từ cùng snapshot/tin trước năm nhánh nghiên cứu.
- [x] Trích tín hiệu từ bộ Full cố định; gọi từng mode trên cùng query/cutoff,
  K/scope/seed đã khóa. Original dùng K=0; bốn prior mode có stats cùng population.
- [x] Deep-copy reports/state/tasks/stats/metadata sang từng nhánh; không để
  `messages`, prefix hoặc output nhánh trước ảnh hưởng nhánh sau.
- [x] Chỉ Decision chạy riêng từng nhánh; giữ retry/pacing hiện có, không vượt
  giới hạn TPM/RPM do bật song song. W4 không thay thuật toán rate guard/quota.
- [x] Giữ các nhánh Full/Baseline cũ đúng semantics Alpha/Sentiment của chúng;
  không ép Baseline nhận Full reports để tiện dùng chung.
- [x] Spy/counter kiểm một lần upstream và Full preparation, đúng năm Decision;
  cố ý sửa state một nhánh và đổi thứ tự nhánh để chứng minh các nhánh độc lập.

**Nghiệm thu:** tất cả prior branches có checksum Full reports/signals giống
nhau; stats bốn prior giống nhau, Original None/rỗng; call-count và mutation PASS.

## W4-11 — Backtest adapter và kết quả kinh tế

**Phụ thuộc:** W4-09, W4-10. **File chính:** `core/backtest_engine.py`;
`core/prior_backtest.py`, `core/prior_context.py` và các test integration/leakage.

- [x] Constructor/lifecycle nạp một retriever theo bank/config mỗi tiến trình;
  không đọc kho/giá hoặc tính lại nhãn kho trong từng query.
- [x] Gọi adapter trước Decision tại từng cutoff, dùng runtime năm nhánh từ W4-10.
  Bảo đảm outcome tương lai nằm ngoài state/prompt/query dù engine có toàn df
  để tính nhãn đánh giá sau đó.
- [x] Lưu cấu trúc kết quả nghiên cứu theo W4-04, toàn metadata/stats/prefix,
  hash reports chung và nguồn quyết định; không ghi nhánh lỗi thành SHORT thành công.
- [x] Dùng `compute_round_trip_net_return` và hợp đồng kinh tế hiện có:
  LONG Open(t+1)→Close(t+3), SHORT cash, fee=0,0025/slippage=0,001 hai chiều.
  Không dùng Close-to-Close hoặc tự thêm engine P&L khác cho prior variants.
- [x] Kiểm lịch phiên/boundary đủ entry/exit; adapter nghiên cứu daily horizon=3.
  Giữ tham số/return/callback/summary của đường Full/No-Alpha cũ tương thích.
- [x] Test điểm lời/lỗ/zero-return, SHORT cash, thiếu phiên, flag off và JSON
  serialization bằng OHLCV tổng hợp có nhãn tính từ engine thật.

**Nghiệm thu:** mock pipeline tạo đủ năm kết quả đúng schema; entry/exit/chi
phí và output cũ PASS, invalid source/output dừng điểm với chẩn đoán.

**Kết quả 06/10/2026:** [biên bản/API](prior_backtest_integration.md),
[receipt](prior_backtest_review.json); 16 test mới, compileall/461 unit/
E2E/77 leakage PASS. Lưu các điểm complete và summary partial;
checkpoint shared/nhánh đang dở và resume tiếp tục ở W4-12.

## W4-12 — Checkpoint và resume theo nhánh

**Phụ thuộc:** W4-04, W4-11. **File chính:** adapter backtest;
helper dự kiến `core/prior_checkpoint.py`, test `tests/test_prior_checkpoint.py`.

- [ ] Lưu envelope schema/signature/hash theo contract; ghi atomic và kiểm
  checksum/provenance khi đọc. Snapshot phục hồi không vượt cutoff.
- [ ] Persist Full reports/signals/proof trước Decision đầu, persist ngay từng
  nhánh valid; không cần đợi cả năm nhánh mới lưu tiến độ.
- [ ] Resume xác minh context/config/bank/versions, dùng reports và nhánh đã lưu;
  chỉ invoke Decision nhánh còn thiếu. Complete chỉ khi đủ năm nhánh hợp lệ.
- [ ] Lỗi LLM/quota/format/interrupt lưu trạng thái đang dở, giải phóng khóa
  sở hữu trong finally; không biến lỗi thành quyết định, không chạy lại upstream.
- [ ] Test khóa tiến trình sống/khóa chết, file dở/atomic failure, crash sau mỗi
  ranh giới và sau nhánh cuối trước complete; không ghi đè checkpoint hợp lệ cũ.
- [ ] Đổi key được resume khi mọi dữ liệu/config khác giữ nguyên; key không ghi
  trong file. Đổi bank/hash/config/version/cutoff phải từ chối rõ.
- [ ] Checkpoint legacy thiếu proof được đọc/giữ ở đường cũ theo contract;
  không được nhập vào nghiên cứu mới bằng cách tự dựng provenance thiếu.
- [ ] So sánh run liền và run ngắt/resume bằng LLM giả định xác định: IDs,
  stats/prefix, reports, Decision và kết quả kinh tế tương đương; bỏ qua timestamp.

**Nghiệm thu:** failpoint tests PASS, không trùng point/branch và không mất
metadata. Chưa chạy API thật để thử quota; lỗi quota được mô phỏng.

## Gate C và cập nhật tiến độ

- [ ] W4-09..12 PASS PIT, call-count, kinh tế và resume.
- [ ] Không tái gọi vision/Full preparation hoặc nhánh đã xong khi phục hồi.
- [ ] Error/empty/partial/complete phân biệt, metadata đầy đủ và JSON strict.

Ghi nhật ký từng task và cập nhật [README](README.md); receipt dự kiến
`paired_checkpoint_review.json` chứa ma trận ca kiểm, signature/hash và kết quả.
