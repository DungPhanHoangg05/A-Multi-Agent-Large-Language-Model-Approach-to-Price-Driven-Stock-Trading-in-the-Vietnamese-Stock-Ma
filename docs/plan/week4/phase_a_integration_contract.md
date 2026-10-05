# Phase A — Khóa hợp đồng tích hợp

**Trạng thái: hoàn thành W4-01..04 ngày 05/10/2026 (4/4 task).
Gate A PASS đặc tả; bước tiếp theo W4-05.** [Checklist W4](README.md),
[receipt Gate A](checkpoint_review.json). Runtime/provider/resume chưa nghiệm thu.
Mục tiêu: chốt trách nhiệm của caller/graph/Decision/checkpoint trước khi sửa code.
Đầu ra: [state/config](integration_contract.md), [đầu vào](input_readiness.json),
[provenance](provenance_contract.md), [checkpoint](checkpoint_contract.md) và schema/
ví dụ/receipt trong thư mục tuần. PASS này nghiệm thu hợp đồng, không là runtime PASS.

## W4-01 — Kiểm tra bàn giao và điểm nối

**Phụ thuộc:** W3 hoàn thành. **Phạm vi:** khảo sát và kiểm chứng đầu vào.

- [x] Đối chiếu kho/manifest với QA W2: 852 record, checksum, schema, nhãn kinh tế;
  ghi hash/version của code và bằng chứng W3 đang dùng.
- [x] Đọc `agent_state.py`, `SetGraph.compile_upstream/compile_decision/set_graph`,
  `BacktestEngine._run_ablation_variants/_run_paired_point/run/_save`,
  `create_final_trade_decider` và các test paired/ablation/token hiện có.
- [x] Vẽ luồng đang chạy: upstream chung → Alpha/Sentiment theo ablation → Decision;
  chỉ ra chỗ cần chuẩn bị Full một lần trước năm Decision nghiên cứu.
- [x] Ghi schema output Full/No-Alpha, callback/web JSON và cách lưu tạm hiện tại;
  phân biệt lưu kết quả sau điểm với resume một nhánh đang dở.
- [x] Ghi nguồn fixture có thể tái lập từ Git và nguồn replay cần archive local;
  thiếu archive phải báo thiếu, không gọi LLM hoặc tạo episode để bù.
- [x] Đóng baseline từ commit nền và kết quả test, liệt kê gate giá 2023–2024 còn mở.

**Hoàn thành khi:** receipt đầu vào và bản đồ tích hợp ghi rõ cái đã có, cái còn
thiếu, baseline và phạm vi sửa. Không dùng checksum đơn lẻ làm bằng chứng PIT.

## W4-02 — Chốt state/config và tương thích

**Phụ thuộc:** W4-01. **Phạm vi:** đặc tả, chưa cài validator.

- [x] Chốt trường mới: `market_regime` chứa state đầy đủ, `prior_tasks`,
  `bayesian_prior_context` (BRPP), stats/metadata/provenance; tên cuối cùng và
  kiểu được ghi trong hợp đồng, tránh hai trường chứa thông tin mâu thuẫn.
- [x] Chốt `prior_config`: `enable_bayesian_prior=false`, mode/K/scope/seed,
  bank/manifest/audit paths; K=0..3 theo W3, seed=42, `same_symbol` mặc định.
- [x] Khóa năm nhánh ở README; Original K=0 vẫn kiểm query khi chạy ma trận mới,
  không nạp kho/đòi model mới ở đường legacy khi flag tắt.
- [x] Giữ `ABLATION_CONFIGS` và `include_alpha` tương thích; chốt xử lý tổ hợp
  prior + ablation ngoài ma trận Full (từ chối rõ hoặc hợp đồng riêng có test).
- [x] Chốt input sai: mode/scope/kiểu bool/K/seed/ngày/state không hợp lệ phải
  lỗi rõ trước LLM. Phân biệt flag tắt với `empty` hợp lệ và lỗi nguồn.
- [x] Chốt JSON: ngày ISO, Python scalar gốc, không NaN/Infinity; snapshot
  DataFrame trong state không được serialize trực tiếp vào checkpoint JSON.
- [x] Khóa daily `1d`/`1 ngày` với horizon=3; khảo sát default `1 day` hiện có
  và chốt chuẩn hóa hoặc từ chối rõ ở adapter mới, không đổi âm thầm timeframe cũ.

**Hoàn thành khi:** có bảng kiểu/default/required/validation và ví dụ input/output
cho flag off, Original, Bayesian, empty/partial và input sai; không nới policy W3.

## W4-03 — Chốt provenance và trình tự PIT

**Phụ thuộc:** W4-01, W4-02. **Phạm vi:** hợp đồng provider/caller.

- [x] Giá: `point_in_time_df` và mọi feature chỉ chứa nến ≤cutoff; ngày cuối
  snapshot khớp query. Chốt fingerprint nguồn giá/schema/symbol/timeframe.
- [x] Tin: chỉ bài có ngày công bố ≤cutoff; bài không ngày bị loại; ghi hash
  và coverage. Thiếu tin hợp lệ trả NEUTRAL có lý do, không dựng tin giả.
- [x] Regime: `as_of_date == cutoff`, `feature_end_date <= cutoff`, đúng VNINDEX,
  state hợp lệ và hash artifact/source. HMM/scaler/calibration train end ≤cutoff.
- [x] Chốt hai đường provider: replay dùng prefix đã xác minh đúng ngày;
  OOS dùng artifact train đóng băng trước ngày query và feature PIT. Không áp
  quy tắc `train_end == cutoff` của prefix lịch sử cho model train cố định OOS.
- [x] Đối chiếu `PrefixRegimeProvider`/validator/model W2 để chọn thành phần tái
  sử dụng. Artifact thiếu/sai/chứa train tương lai phải dừng, không lấy model
  toàn tập train để suy ra regime trước cuối train hoặc tự fit trong query.
- [x] Query chỉ gồm tín hiệu chuẩn hóa có sẵn tại cutoff; không chứa actual
  direction, entry/exit tương lai, net return hay nhãn của chính test point.
- [x] Khóa thứ tự: snapshot/provenance → báo cáo/tín hiệu chung → retriever →
  BRPP → Decision; nhãn đánh giá giữ ngoài state đưa vào agent/retriever.
- [x] Prior đã đóng có `exit_date < cutoff`; stats cùng population hợp lệ.
  Vi phạm nguồn/cutoff phải ValueError/AssertionError trước formatter/API.

**Hoàn thành khi:** có bảng nguồn/validator/trách nhiệm và ca biên cùng ngày,
ngày tương lai, train end sai, feature end sai, undated news và snapshot lệch ngày.

## W4-04 — Chốt kết quả và checkpoint

**Phụ thuộc:** W4-02, W4-03. **Phạm vi:** schema và luật phục hồi.

- [x] Chốt schema version riêng cho nghiên cứu; giữ result/summary cũ có thể đọc
  khi flag tắt. Không nhét năm nhánh vào hai trường Full/No-Alpha để mất nghĩa.
- [x] Run signature gồm config chuẩn hóa, bank hash, version thuật toán/template,
  nguồn giá/tin/regime và định danh model/prompt. Không ghi API key vào signature/log.
- [x] Mỗi điểm lưu cutoff/symbol/timeframe, nguồn PIT và fingerprint, reports,
  tín hiệu chung; quyết định rõ cách lưu/khôi phục state mà không chạy lại vision.
- [x] Mỗi nhánh lưu tasks/stats/prefix, toàn metadata W3: IDs/thứ tự/scores,
  counts, K/seed/effective seed/scope/mode, status/reason và versions; thêm
  prompt length/hash, Decision/source/error và tiến độ nhánh.
- [x] Lưu báo cáo chung trước Decision đầu tiên, lưu từng nhánh thành công ngay;
  điểm chỉ complete khi đủ năm nhánh hợp lệ. Tách planned/running/failed/complete
  của tiến trình khỏi empty/partial/complete của kết quả retrieval.
- [x] Chốt ghi atomic/khóa và phục hồi sau interrupt/quota/disk error; không tự
  xóa khóa của tiến trình còn sống, không giữ khóa chết làm resume bị chặn mãi.
- [x] Chốt resume đổi key nhưng giữ context/config; checkpoint khác hash/version/
  config hoặc schema cũ thiếu proof phải từ chối rõ hoặc có migration kiểm chứng,
  không tự điền metadata chưa từng được ghi.

**Hoàn thành khi:** schema mẫu và bảng chuyển trạng thái mô tả được crash trước
upstream, sau báo cáo chung, giữa nhánh, sau nhánh cuối và trước complete.

## Gate A và cập nhật tiến độ

- [x] W4-01..04 đủ hợp đồng, ví dụ và biên bản; không còn quyết định ngầm về PIT,
  chiều ablation/prior, horizon, lưu báo cáo chung hoặc tương thích file cũ.
- [x] Ranh giới W4 offline/W5 pilot và gate giá ngoài mẫu đã ghi rõ.

Sau mỗi task, thêm nhật ký theo mẫu: **ngày — mã task — nhánh/commit — file —
kiểm chứng — kết quả — phần còn mở**, rồi cập nhật [README](README.md).

## Nhật ký tiến độ

### 2026-10-05 — W4-04 / Gate A hoàn thành

- Nhánh `docs/research-checkpoint-contract`, baseline `e3aa3f8`;
  [contract](checkpoint_contract.md), [schema](research_checkpoint.schema.json),
  [policy](checkpoint_policy.json), [ví dụ](checkpoint_examples.json), [receipt](checkpoint_review.json).
- Khóa identity/envelope/projected state, result riêng và common support;
  giữ legacy reader, từ chối migration thiếu proof. Key nằm ngoài identity.
- Persist upstream reports rồi shared Full, từng branch valid; outcome ở
  evaluation riêng. Stage process khác status retrieval; complete đủ năm branch.
- Chốt atomic fsync/replace và OS lock/owner identity; crash ambiguous upstream/
  Full dừng để rà soát, Decision còn thiếu có thể retry cùng input/attempt mới.
- Bốn document mẫu và bảy trạng thái hợp schema; 11 rejection/8 signature
  mutation/3 atomic-reader probes PASS; năm retrieval thật giữ toàn metadata W3.
  Runtime failpoints/OS lock/resume mới vẫn là đặc tả cho W4-12.
- Compileall, 339 unit (130,278 giây), E2E (17,6 giây), 56 leakage (6,097 giây)
  PASS; 2.312 file nguồn/bằng chứng giữ hash, kiểm lại proof 261 file W4-01.
- **Gate A PASS_CONTRACTS_ONLY**, Phase A 4/4, W4 4/16. Bàn giao W4-05;
  không mở runtime prior/budget, pilot W5 hoặc gate giá thực thi OOS.

### 2026-10-05 — W4-03 hoàn thành

- Nhánh `docs/prior-provenance-contract`, baseline `545e34c`;
  [contract](provenance_contract.md), [policy](provenance_policy.json),
  [ví dụ/biên](provenance_examples.json), [receipt](provenance_review.json).
- Khóa object provenance bảy nhóm; giá raw VCI/KBS, schema/unit/hash và
  endpoints; tin dated/coverage/NEUTRAL; state/artifact/feature/ba component.
- Hai provider riêng: prefix train-end=cutoff readonly; fixed OOS train-end<cutoff
  và freeze trước query đầu. Không fit/download/sinh episode trong probe.
- Kiểm nguồn thật năm context/bốn mã; 14 probe validator hiện có PASS,
  14 ca adapter mới ghi rõ chưa thực thi. Prior bằng cutoff bị loại khỏi
  cả pool/stats; bốn mode giữ stats cùng population. Outcome query ở evaluator.
- Compileall, 339 unit (48,126 giây), E2E, 56 leakage (5,077 giây) PASS;
  2.308 file nguồn/archive/bằng chứng giữ nguyên hash trước/sau gate.
- Phase A 3/4, W4 3/16; W4-04 khóa checkpoint tiếp theo. Gate A,
  validator tích hợp/provider OOS runtime và gate giá 2023–2024 còn mở.

### 2026-10-05 — W4-02 hoàn thành

- Nhánh `docs/prior-state-config-contract`, baseline `62a673a`; [hợp đồng](integration_contract.md),
  [policy](integration_policy.json), [ví dụ](integration_examples.json), [receipt](state_config_review.json).
- Khóa tám key config/tám field state, native JSON, default disabled; Original
  enabled K=0 có metadata/query validation, khác đường legacy flag off không I/O mới.
- Enabled chỉ Full/backtest, cờ bool strict; năm branch ID cố định. Legacy giữ
  bốn ablation/include_alpha/output. Daily `1d`/`1 ngày` canonical=`1d`, horizon=3;
  adapter mới từ chối `1 day`, không sửa default/alias legacy.
- Bảy ví dụ config và bốn projection API W3, bảy probe lỗi W3 đã đối chiếu.
  Ca parser config mới chỉ là đặc tả cho W4-05, chưa có validator runtime.
- Compileall, 339 unit (91,391 giây), E2E (13,8 giây), 56 leakage (7,637 giây)
  PASS; runtime/kho/model/receipt cũ giữ nguyên. W4-03 chốt provenance/PIT,
  W4-04 chốt checkpoint; Gate A/runtime budget/OOS chưa PASS.

### 2026-10-05 — W4-01 hoàn thành

- Nhánh `docs/prior-runtime-readiness`, baseline `516d0ed`; [biên bản/bản đồ](input_readiness.md)
  và [receipt](input_readiness.json). Giữ byte kho, giá, model và bằng chứng W2/W3.
- Kiểm schema/nhãn 852 record bằng validator/engine thật; 852 episode/signal,
  217 artifact prefix và staging khớp. Replay 288 query + 288 lượt lặp PASS,
  BRPP tối đa 373; phân biệt 24 nguồn lịch sử và tám fixture biên.
- Bốn gate mới PASS: compileall, 339 unit (48,455 giây), E2E (7,0 giây),
  56 leakage (5,130 giây). Nguồn/bằng chứng so trước/sau gate giữ nguyên.
- Ghi đủ schema callback/web/Full/No-Alpha, resume điểm hoàn chỉnh của runner
  ablation và khoảng trống resume nhánh/backtest, cap/guard runtime, alias `1 day`.
- Chỉ cập nhật tài liệu/receipt và quy tắc byte JSON W4; bước tiếp theo W4-02.
  Gate A, provider OOS, runtime budget và giá 2023–2024 còn mở.
