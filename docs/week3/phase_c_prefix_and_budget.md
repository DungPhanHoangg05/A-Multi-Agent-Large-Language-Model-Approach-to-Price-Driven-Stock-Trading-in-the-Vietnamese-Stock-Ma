# Phase C — BRPP và ngân sách prompt

**Trạng thái: chưa thực hiện.** Bắt đầu sau Gate B. Dự kiến formatter nằm trong
`core/bayesian_retriever.py`, test `tests/test_bayesian_prior_prefix.py`, smoke
`scripts/verify_bayesian_prior.py`, biên bản `docs/week3/prior_smoke.json`.

**Điểm cần đối chiếu khi triển khai:** log E2E hiện tại ghi trần prompt compact
7.500 ký tự, cao hơn ràng buộc 6.500 trong `AGENTS.md`. W3 phải kiểm độ dài prompt
ghép thử thực tế, không lấy trần cũ làm tiêu chí PASS; W4 cần áp dụng ràng buộc
<6.500 tại runtime khi tích hợp BRPP.

## W3-10 — định dạng compact

- [ ] Cài `format_compact_prior_prefix(tasks, stats)` theo template đã khóa.
- [ ] Có regime, số mẫu hỗ trợ, thống kê đúng mẫu số và tối đa ba ví dụ ngắn với
  tín hiệu/nhãn LONG ròng. IDs đầy đủ ở metadata, không bắt buộc nhồi toàn bộ provenance vào prompt.
- [ ] Dùng tên/code hướng có bảng chú giải; không cắt chuỗi tùy tiện làm mất dấu lợi nhuận,
  mẫu số, nhãn kết quả hoặc đổi SHORT thành bán khống.
- [ ] Thiếu mẫu ghi đúng số thực tế; K=0/Original trả prefix rỗng; n=0 không bịa thống kê.
- [ ] Cảnh báo thiếu tin thể hiện đúng nghĩa khi dùng sentiment; không diễn giải NEUTRAL
  trong kho là bằng chứng tin tức thị trường trung tính.

## W3-11 — giới hạn ký tự và prompt ghép thử

- [ ] Kiểm `len(prefix) <= 600` cho K=1..3, các regime, số liệu cực trị hợp lệ,
  nhiều chữ số, tiếng Việt và input dài; với K>3 thực hiện đúng chính sách Gate A.
- [ ] Không âm thầm truncate: rút gọn theo template đã khóa hoặc từ chối nếu vẫn vượt trần.
- [ ] Kiểm việc render là xác định, không sửa tasks/stats; giá trị mơ hồ/NaN bị từ chối.
- [ ] Dùng builder compact hiện có của Decision để ghép thử báo cáo fixture + BRPP:
  tổng prompt phải **<6.500** ký tự; thử cả ngôn ngữ builder đang hỗ trợ.
- [ ] Giữ `_distill_report`, `_cap_report`; chỉ test/ngân sách bàn giao, chưa inject
  BRPP vào runtime Decision/graph/backtest. Nếu fixture hợp lệ vượt trần, ghi blocker
  và phương án xử lý cụ thể trước khi chốt W3/W4.

## W3-12 — smoke trên kho thật, offline

- [ ] Script nạp kho QA PASS, chọn truy vấn xác định trên bốn mã/bốn regime từ dữ liệu
  có sẵn; fixture/query lịch sử phải mang regime prefix PIT, không nhãn hồi cứu Panel A.
- [ ] Có cutoff trước episode đầu, cutoff bằng exit, query thiếu K và query sau cuối kho.
  Không suy ra regime thực tế của ngày giả định nếu chưa có snapshot xác minh.
- [ ] Chạy bốn mode, ghi bank hash/config/seed, IDs/dates, số mẫu, stats, score,
  lý do thiếu mẫu và prefix length; kiểm bằng cutoff ở từng task đầu ra.
- [ ] Không gọi upstream/LLM, fit lại HMM, sinh episode hoặc tải giá mới; không ghi đè
  kho/manifest W2. Receipt chỉ chứa dữ liệu nghiên cứu, không key/.env.
- [ ] Biên bản phân biệt smoke retrieval và benchmark giao dịch OOS; hạn chế dữ liệu
  vẫn được ghi rõ.

**Gate C:** prefix đủ nghĩa và ≤600, prompt ghép thử <6.500, smoke bốn mode PASS
với receipt tái lập. Chưa coi đây là hệ thống tích hợp W4.

## Kết quả và nhật ký

Chưa có kết quả thực thi. Ghi mẫu prefix đã kiểm, độ dài tối đa, file receipt và lệnh chạy.
