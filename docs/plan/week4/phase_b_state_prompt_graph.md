# Phase B — State, ngân sách prompt và graph

**Trạng thái: W4-05 hoàn thành, Phase B 1/4; W4-06..08 còn mở.** [Checklist W4](README.md).
Đầu vào: Gate A và các policy W3. Test mới dưới đây là tên dự kiến;
tái sử dụng test ablation/paired/token hiện có khi phù hợp.

## W4-05 — State/config và validator

**Phụ thuộc:** Gate A. **File chính:** `agents/agent_state.py`,
`utils/graph_setup.py`; helper cấu hình riêng chỉ thêm khi cần.

- [x] Thêm trường theo hợp đồng W4-02 vào đúng TypedDict mà graph thực tế dùng,
  bao gồm `BacktestAgentState`; tránh LangGraph lọc mất prior/provenance.
- [x] Cài parser/validator `prior_config` độc lập với `resolve_ablation_config`;
  default disabled, tên mode/scope/K/seed đúng policy đã khóa.
- [x] Chuẩn hóa dữ liệu JSON về scalar Python/ngày ISO, bản sao task/stats/metadata
  độc lập; giữ DataFrame và đối tượng runtime ngoài phần JSON checkpoint.
- [x] Đường flag off không đòi artifact mới hoặc đọc kho; không nhận prefix còn
  sót từ nhánh trước. Đường enabled không chấp nhận context chưa xác minh nguồn.
- [x] Test schema xuyên graph, flag off/Original, invalid bool/K/mode/scope,
  input thiếu, conflict config và deep copy bằng fixture nhỏ.

**Nghiệm thu 05/10/2026:** `tests/test_prior_runtime_config.py` **28 test PASS**;
bốn ablation cũ và `include_alpha` vẫn đúng hợp đồng. Compileall/**367 unit**/
E2E/**56 leakage** PASS; xem [biên bản](state_config_runtime.md) và
[receipt mới](state_config_runtime_review.json). Kho/spec/receipt Phase A giữ nguyên.

Enabled/Original được parser chấp nhận khi hợp lệ, nhưng graph production
dừng trước node nếu chưa có adapter xác minh nguồn PIT (W4-09). Kiểm
shape/ngày/tín hiệu không là xác minh nguồn. Caller nghiên cứu phải kiểm
state thô trước bộ lọc channel của LangGraph; graph nghiên cứu ở W4-08 còn mở.

## W4-06 — Cap/guard trên prompt runtime

**Phụ thuộc:** W4-05. **File chính:** `agents/decision_agent.py`,
`tests/test_backtest_token_budget.py`, `tests/test_bayesian_prompt_budget.py`.

- [ ] Áp dụng cap bàn giao: trend/pattern/indicator 800 mỗi báo cáo, alpha 1.100,
  sentiment 500 (tổng 4.000); giữ `_distill_report`, `_cap_report` và các trường
  tín hiệu/conflict gate/hợp đồng kinh tế được distill giữ lại.
- [ ] Chốt phạm vi cap theo hợp đồng: ưu tiên cấu hình backtest phù hợp; rà tác
  động nếu hằng cap dùng chung với đường live. Không hứa prompt giữ nguyên byte
  khi report dài bị cap mới; ghi thay đổi và kiểm hồi quy nội dung bắt buộc.
- [ ] Thêm guard `len(final_prompt) < 6500` ở đường backtest, sau BRPP và mọi
  hướng dẫn/schema được thêm vào chuỗi prompt, trước `_invoke_with_retry`.
- [ ] Prompt vượt trần báo lỗi độ dài/cấu hình có chẩn đoán; không gọi API, không
  truncate BRPP, xóa task hoặc trả quyết định cash để che lỗi.
- [ ] Kiểm VI/EN, daily `1d`/`1 ngày`, đủ/thiếu report, report bão hòa, Unicode,
  stock name dài, reserve BRPP đủ 600; biên 6.499 được phép, 6.500 bị chặn.
- [ ] Sửa log ngưỡng cũ 7.500 thành ngưỡng thực tế; ghi riêng cap report,
  prefix length và prompt length. Token/quota thực tế chưa được suy ra từ ký tự.

**Nghiệm thu:** builder/runtime thật với LLM giả định xác nhận không có call
trên input overflow; giữ fixture kinh tế/conflict, không chỉ sửa assertion cũ
cho test xanh. Receipt dự kiến `runtime_prompt_budget_review.json` ghi config,
matrix/hash và giá trị lớn nhất; không sửa receipt W3 thành runtime PASS.

## W4-07 — BRPP và hướng dẫn reasoning

**Phụ thuộc:** W4-06. **File chính:** `agents/decision_agent.py`;
test dự kiến `tests/test_decision_prior_integration.py`.

- [ ] Dùng `format_compact_prior_prefix(tasks, stats)` từ module W3; không tự
  tính lại thống kê hoặc xây template khác trong Decision Agent.
- [ ] Chèn BRPP trước báo cáo đầu tiên (`### [1]`), đúng một lần. Khi disabled/
  Original prefix rỗng, không để marker, stats hoặc instructions prior còn sót.
- [ ] Hướng dẫn dùng regime/stats như bối cảnh rồi đọc tín hiệu hiện tại; prior
  không là quyết định thay agent, không là posterior LLM đã hiệu chuẩn.
- [ ] Giữ counts/mẫu số/None và tình trạng thiếu tin; không biến missing thành 0%,
  thêm smoothing hoặc diễn giải WIN/LOSS lịch sử thành nhãn của query.
- [ ] Empty/partial hợp lệ giữ nguyên metadata; input/schema/provenance lỗi phải
  dừng. Guard BRPP ≤600 và guard tổng prompt vẫn chạy trên prompt cuối.
- [ ] Kiểm cả structured output và đường text hiện có: đều qua `_invoke_with_retry`;
  schema LONG/SHORT và format retry không đổi, lỗi API/output không bị nuốt.

**Nghiệm thu:** mock capture prompt ở node thật cho năm nhánh, VI/EN, K=0..3,
empty/partial và overflow; kiểm vị trí/đếm prefix, input không đổi và guard trước API.

## W4-08 — Ranh giới graph và tương thích

**Phụ thuộc:** W4-05, W4-07. **File chính:** `utils/graph_setup.py`.

- [ ] Truyền prior config/state qua graph; kiểm đủ key sau compile/invoke.
- [ ] Tạo ranh giới chuẩn bị Full (Alpha/Sentiment) và Decision riêng để caller
  W4-10 có thể dùng chung reports mà không kích hoạt Alpha mỗi nhánh. Giữ
  `compile_upstream()` cho Indicator → Pattern → Trend.
- [ ] Chốt node chuẩn bị prior sau khi đủ tín hiệu; chỉ một nơi chịu trách nhiệm
  retrieve/format để không gọi hai lần ở graph và engine. Caller xác minh PIT.
- [ ] Giữ `compile_decision()`/`set_graph()` và tham số cũ có hành vi hợp lệ khi
  prior disabled; cấu hình nghiên cứu Full không đổi `ABLATION_CONFIGS`.
- [ ] Tổ hợp chưa được đặc tả bị từ chối rõ, không lặng lẽ bỏ prior hoặc bật
  Alpha/Sentiment mà người dùng đã tắt.
- [ ] Test topology/thứ tự và số lần gọi node bằng mock, đủ bốn ablation cũ;
  nhánh mới vào Decision nhận đúng Full reports và prior metadata.

**Nghiệm thu:** node không chạy ngoài thứ tự, prior không mất khỏi state,
đường cũ PASS E2E xác định, API graph mới dùng được từ W4-10.

## Gate B và cập nhật tiến độ

- [ ] W4-05..08 PASS state/config, Decision runtime budget và graph compatibility.
- [ ] Prefix đúng vị trí/một lần; Original rỗng; tất cả API đi qua retry wrapper.
- [ ] Guard thực thi trước LLM, không chỉ kiểm prompt ghép thử bên ngoài runtime.

Ghi nhật ký từng task: ngày, nhánh/commit, file, lệnh/test, kết quả và giới hạn;
cập nhật [README](README.md). Gate B chưa đồng nghĩa tích hợp backtest/resume đã PASS.
