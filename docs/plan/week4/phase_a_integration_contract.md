# Phase A — Khóa hợp đồng tích hợp

**Trạng thái: chưa thực hiện.** [Checklist W4](README.md).
Mục tiêu: chốt trách nhiệm của caller/graph/Decision/checkpoint trước khi sửa code.
Tài liệu đầu ra dự kiến: `integration_contract.md`, `input_readiness.json` và
`checkpoint_contract.md` trong thư mục tuần. Không tạo receipt PASS khi chỉ khảo sát.

## W4-01 — Kiểm tra bàn giao và điểm nối

**Phụ thuộc:** W3 hoàn thành. **Phạm vi:** khảo sát và kiểm chứng đầu vào.

- [ ] Đối chiếu kho/manifest với QA W2: 852 record, checksum, schema, nhãn kinh tế;
  ghi hash/version của code và bằng chứng W3 đang dùng.
- [ ] Đọc `agent_state.py`, `SetGraph.compile_upstream/compile_decision/set_graph`,
  `BacktestEngine._run_ablation_variants/_run_paired_point/run/_save`,
  `create_final_trade_decider` và các test paired/ablation/token hiện có.
- [ ] Vẽ luồng đang chạy: upstream chung → Alpha/Sentiment theo ablation → Decision;
  chỉ ra chỗ cần chuẩn bị Full một lần trước năm Decision nghiên cứu.
- [ ] Ghi schema output Full/No-Alpha, callback/web JSON và cách lưu tạm hiện tại;
  phân biệt lưu kết quả sau điểm với resume một nhánh đang dở.
- [ ] Ghi nguồn fixture có thể tái lập từ Git và nguồn replay cần archive local;
  thiếu archive phải báo thiếu, không gọi LLM hoặc tạo episode để bù.
- [ ] Đóng baseline từ commit nền và kết quả test, liệt kê gate giá 2023–2024 còn mở.

**Hoàn thành khi:** receipt đầu vào và bản đồ tích hợp ghi rõ cái đã có, cái còn
thiếu, baseline và phạm vi sửa. Không dùng checksum đơn lẻ làm bằng chứng PIT.

## W4-02 — Chốt state/config và tương thích

**Phụ thuộc:** W4-01. **Phạm vi:** đặc tả, chưa cài validator.

- [ ] Chốt trường mới: `market_regime` chứa state đầy đủ, `prior_tasks`,
  `bayesian_prior_context` (BRPP), stats/metadata/provenance; tên cuối cùng và
  kiểu được ghi trong hợp đồng, tránh hai trường chứa thông tin mâu thuẫn.
- [ ] Chốt `prior_config`: `enable_bayesian_prior=false`, mode/K/scope/seed,
  bank/manifest/audit paths; K=0..3 theo W3, seed=42, `same_symbol` mặc định.
- [ ] Khóa năm nhánh ở README; Original K=0 vẫn kiểm query khi chạy ma trận mới,
  không nạp kho/đòi model mới ở đường legacy khi flag tắt.
- [ ] Giữ `ABLATION_CONFIGS` và `include_alpha` tương thích; chốt xử lý tổ hợp
  prior + ablation ngoài ma trận Full (từ chối rõ hoặc hợp đồng riêng có test).
- [ ] Chốt input sai: mode/scope/kiểu bool/K/seed/ngày/state không hợp lệ phải
  lỗi rõ trước LLM. Phân biệt flag tắt với `empty` hợp lệ và lỗi nguồn.
- [ ] Chốt JSON: ngày ISO, Python scalar gốc, không NaN/Infinity; snapshot
  DataFrame trong state không được serialize trực tiếp vào checkpoint JSON.
- [ ] Khóa daily `1d`/`1 ngày` với horizon=3; khảo sát default `1 day` hiện có
  và chốt chuẩn hóa hoặc từ chối rõ ở adapter mới, không đổi âm thầm timeframe cũ.

**Hoàn thành khi:** có bảng kiểu/default/required/validation và ví dụ input/output
cho flag off, Original, Bayesian, empty/partial và input sai; không nới policy W3.

## W4-03 — Chốt provenance và trình tự PIT

**Phụ thuộc:** W4-01, W4-02. **Phạm vi:** hợp đồng provider/caller.

- [ ] Giá: `point_in_time_df` và mọi feature chỉ chứa nến ≤cutoff; ngày cuối
  snapshot khớp query. Chốt fingerprint nguồn giá/schema/symbol/timeframe.
- [ ] Tin: chỉ bài có ngày công bố ≤cutoff; bài không ngày bị loại; ghi hash
  và coverage. Thiếu tin hợp lệ trả NEUTRAL có lý do, không dựng tin giả.
- [ ] Regime: `as_of_date == cutoff`, `feature_end_date <= cutoff`, đúng VNINDEX,
  state hợp lệ và hash artifact/source. HMM/scaler/calibration train end ≤cutoff.
- [ ] Chốt hai đường provider: replay dùng prefix đã xác minh đúng ngày;
  OOS dùng artifact train đóng băng trước ngày query và feature PIT. Không áp
  quy tắc `train_end == cutoff` của prefix lịch sử cho model train cố định OOS.
- [ ] Đối chiếu `PrefixRegimeProvider`/validator/model W2 để chọn thành phần tái
  sử dụng. Artifact thiếu/sai/chứa train tương lai phải dừng, không lấy model
  toàn tập train để suy ra regime trước cuối train hoặc tự fit trong query.
- [ ] Query chỉ gồm tín hiệu chuẩn hóa có sẵn tại cutoff; không chứa actual
  direction, entry/exit tương lai, net return hay nhãn của chính test point.
- [ ] Khóa thứ tự: snapshot/provenance → báo cáo/tín hiệu chung → retriever →
  BRPP → Decision; nhãn đánh giá giữ ngoài state đưa vào agent/retriever.
- [ ] Prior đã đóng có `exit_date < cutoff`; stats cùng population hợp lệ.
  Vi phạm nguồn/cutoff phải ValueError/AssertionError trước formatter/API.

**Hoàn thành khi:** có bảng nguồn/validator/trách nhiệm và ca biên cùng ngày,
ngày tương lai, train end sai, feature end sai, undated news và snapshot lệch ngày.

## W4-04 — Chốt kết quả và checkpoint

**Phụ thuộc:** W4-02, W4-03. **Phạm vi:** schema và luật phục hồi.

- [ ] Chốt schema version riêng cho nghiên cứu; giữ result/summary cũ có thể đọc
  khi flag tắt. Không nhét năm nhánh vào hai trường Full/No-Alpha để mất nghĩa.
- [ ] Run signature gồm config chuẩn hóa, bank hash, version thuật toán/template,
  nguồn giá/tin/regime và định danh model/prompt. Không ghi API key vào signature/log.
- [ ] Mỗi điểm lưu cutoff/symbol/timeframe, nguồn PIT và fingerprint, reports,
  tín hiệu chung; quyết định rõ cách lưu/khôi phục state mà không chạy lại vision.
- [ ] Mỗi nhánh lưu tasks/stats/prefix, toàn metadata W3: IDs/thứ tự/scores,
  counts, K/seed/effective seed/scope/mode, status/reason và versions; thêm
  prompt length/hash, Decision/source/error và tiến độ nhánh.
- [ ] Lưu báo cáo chung trước Decision đầu tiên, lưu từng nhánh thành công ngay;
  điểm chỉ complete khi đủ năm nhánh hợp lệ. Tách planned/running/failed/complete
  của tiến trình khỏi empty/partial/complete của kết quả retrieval.
- [ ] Chốt ghi atomic/khóa và phục hồi sau interrupt/quota/disk error; không tự
  xóa khóa của tiến trình còn sống, không giữ khóa chết làm resume bị chặn mãi.
- [ ] Chốt resume đổi key nhưng giữ context/config; checkpoint khác hash/version/
  config hoặc schema cũ thiếu proof phải từ chối rõ hoặc có migration kiểm chứng,
  không tự điền metadata chưa từng được ghi.

**Hoàn thành khi:** schema mẫu và bảng chuyển trạng thái mô tả được crash trước
upstream, sau báo cáo chung, giữa nhánh, sau nhánh cuối và trước complete.

## Gate A và cập nhật tiến độ

- [ ] W4-01..04 đủ hợp đồng, ví dụ và biên bản; không còn quyết định ngầm về PIT,
  chiều ablation/prior, horizon, lưu báo cáo chung hoặc tương thích file cũ.
- [ ] Ranh giới W4 offline/W5 pilot và gate giá ngoài mẫu đã ghi rõ.

Sau mỗi task, thêm nhật ký theo mẫu: **ngày — mã task — nhánh/commit — file —
kiểm chứng — kết quả — phần còn mở**, rồi cập nhật [README](README.md).
