# Tuần 4 — Tích hợp prior vào LangGraph và backtest

**Trạng thái: Phase A hoàn thành 4/4 task; Phase B hoàn thành W4-05..08 (4/4),
tiến độ W4 8/16 ngày 06/10/2026. Gate A PASS đặc tả, Gate B PASS offline graph/prompt
với verifier/retriever fixture. [State/config](integration_contract.md),
[provenance/PIT](provenance_contract.md), [kết quả/checkpoint](checkpoint_contract.md),
[receipt/Gate A](checkpoint_review.json), [state/config runtime](state_config_runtime_review.json).
[cap/guard runtime](runtime_prompt_budget_review.json), [BRPP tại Decision](decision_prior_integration_review.json).
[graph/Full reports](graph_prior_integration_review.json). Tiếp theo W4-09;
Gate C/D, nguồn PIT thật, engine năm nhánh/checkpoint và giá OOS còn mở.**
Tài liệu này tiếp nối [bàn giao W3](../week3/week_close_and_handoff.md) và
[kế hoạch tổng](../plan.md). Checklist bên dưới chỉ đánh dấu hoàn thành khi
đầu ra và kiểm chứng của task đều đạt.

## Mục tiêu và ranh giới

Đưa retriever, thống kê và BRPP đã nghiệm thu vào luồng quyết định thật, có
kiểm chứng point-in-time (PIT), ngân sách prompt, báo cáo dùng chung và resume.
Hệ thống phải giữ các entry point, bốn ablation cũ và hợp đồng kinh tế hiện có.

- W4: state/config, provenance regime, Decision/graph, backtest adapter,
  checkpoint và kiểm thử tích hợp offline.
- W5: CLI điều phối nghiên cứu, pilot FPT bằng LLM thật và đo token/quota.
- W6: benchmark giao dịch ngoài mẫu 2023–2024 sau khi đủ gate dữ liệu.

W4 không sinh lại kho, fit lại toàn bộ model, tải giá/tin, gọi API LLM thật hoặc
chạy pilot. Fixture offline phục vụ kiểm chứng kỹ thuật, không là kết quả đầu tư.
Các module/test/receipt ghi là **dự kiến** chỉ được tạo ở task triển khai tương ứng.

## Đầu vào và điểm còn mở

| Đầu vào | Hiện trạng / việc W4 phải làm |
| --- | --- |
| Kho 852 episode, manifest, QA W2 | Đã PASS; giữ nguyên byte/nhãn. SHA-256 kho `09b48c6192a092b562173e8b3b7eceb44025c6e02454093e34214a730a460949` |
| `BayesianPriorRetriever.retrieve()` | Tasks/stats/metadata hoàn chỉnh; constructor nạp một lần, query trên RAM |
| Hợp đồng và policy W3 | K=0..3; seed=42; mặc định `same_symbol`; bốn mode và fallback đã khóa |
| `format_compact_prior_prefix()` | BRPP ≤600 ký tự, K=0 rỗng; caller phải chứng minh nguồn regime/snapshot |
| Decision runtime | Cap cũ tổng 4.500 chưa đủ khi ghép BRPP; cần cap tổng 4.000 và guard cuối `<6500` |
| Graph/backtest hiện tại | Upstream ba agent đã dùng chung; graph Decision còn chạy Alpha/Sentiment theo nhánh; chưa có năm nhánh prior/checkpoint tương ứng |
| Model/regime | Có artifact train và archive prefix PIT; phải chọn provider đúng ngày, không chỉ truyền tên regime |
| Giá thô kiểm định 2023–2024 | Chưa mở gate; không chặn tích hợp offline, bắt buộc mở trước pilot/OOS |

Kho phủ 2020–2022 do warm-up 600 phiên. Sentiment của 852 episode đều NEUTRAL
do thiếu tin; giữ trọng số sentiment bằng 0 trong similarity. Stats là tỷ lệ
thực nghiệm, không là xác suất thắng đã hiệu chuẩn của LLM.

## Cấu hình so sánh cần giữ

| Nhánh nghiên cứu | Mode retriever | K | Báo cáo / stats |
| --- | --- | ---: | --- |
| Original | `bayesian_regime` | 0 | Full dùng chung; không stats, BRPP rỗng |
| Random | `random` | 3 | Full dùng chung; stats cùng population regime |
| Recent | `recent` | 3 | Full dùng chung; stats cùng population regime |
| Similarity | `similarity` | 3 | Full dùng chung; stats cùng population regime |
| Bayesian | `bayesian_regime` | 3 | Full dùng chung; stats cùng population regime |

`prior_config` là chiều cấu hình riêng với `ablation_config` cũ (`full`,
`alpha_only`, `sentiment_only`, `baseline`). Flag prior mặc định tắt. Ma trận
nghiên cứu W4 dùng `full`; không tự nhân thành 4×5 nhánh. So sánh với Original
có cả tác động stats và ví dụ; không quy toàn bộ thay đổi cho thuật toán chọn K.

## Quy tắc theo dõi

- `[ ]` chưa hoàn thành; `[x]` chỉ sau khi đầu ra và kiểm chứng task đều đạt.
- Sau mỗi task cập nhật dòng trong bảng, checklist ở phase và nhật ký: ngày,
  nhánh/commit, file, lệnh, kết quả, giới hạn còn lại. Task bị chặn ghi rõ điều kiện.
- Mỗi task trên nhánh riêng từ `develop`; commit/merge theo [AGENTS.md](../../../AGENTS.md).
  Bốn gate phải PASS trước merge; không đưa mã tuần vào commit message.
- Tài liệu/receipt tuần đặt tại `docs/plan/week4/`; log/checkpoint chạy tại
  `outputs/`, không lưu key, dữ liệu tạm hoặc kho sao chép trong tài liệu.
- Receipt W2/W3 đã đóng băng giữ nguyên; kiểm chứng mới dùng receipt W4 riêng.

## A. Khóa hợp đồng tích hợp

Chi tiết: [Phase A](phase_a_integration_contract.md).

| Mã | Task | Đầu ra / điều kiện hoàn thành | Phụ thuộc | Trạng thái |
| --- | --- | --- | --- | --- |
| W4-01 | Kiểm tra bàn giao và các điểm nối runtime | [Bản đồ/biên bản](input_readiness.md), [receipt](input_readiness.json): 852 record và archive/QA/hash PASS; replay 288 query + 288 lượt lặp, bốn gate mới PASS | W3 hoàn thành | [x] |
| W4-02 | Chốt state và cấu hình prior độc lập | [Contract v1](integration_contract.md), [policy](integration_policy.json), [ví dụ](integration_examples.json), [receipt](state_config_review.json): tám config/tám field, Full only, daily chuẩn, bốn gate PASS; chưa cài validator runtime | W4-01 | [x] |
| W4-03 | Chốt provenance và thứ tự PIT | [Contract](provenance_contract.md), [policy](provenance_policy.json), [ví dụ](provenance_examples.json), [receipt](provenance_review.json): hai provider, nguồn/shape/thứ tự PIT, 5 replay context và 14 probe hiện có, bốn gate PASS; chưa cài adapter | W4-01, W4-02 | [x] |
| W4-04 | Chốt schema kết quả và resume | [Contract](checkpoint_contract.md), [schema](research_checkpoint.schema.json), [policy](checkpoint_policy.json), [ví dụ](checkpoint_examples.json), [receipt](checkpoint_review.json): identity không chứa key, lưu từng nhánh, xử lý crash/khóa; bốn gate PASS, Gate A đóng đặc tả | W4-02, W4-03 | [x] |

## B. State, prompt và graph

Chi tiết: [Phase B](phase_b_state_prompt_graph.md).

| Mã | Task | Đầu ra / điều kiện hoàn thành | Phụ thuộc | Trạng thái |
| --- | --- | --- | --- | --- |
| W4-05 | Cài state/config và validator | [Biên bản](state_config_runtime.md), [receipt](state_config_runtime_review.json): tám field optional, parser strict, JSON/context, guard off/enabled, 28 test mới và bốn gate PASS | Gate A | [x] |
| W4-06 | Áp dụng cap và guard prompt runtime | [Biên bản](runtime_prompt_budget.md), [receipt](runtime_prompt_budget_review.json): cap backtest 4.000; guard cuối <6.500, 192 ca + dự phòng 600, text/structured boundary và bốn gate PASS | W4-05 | [x] |
| W4-07 | Chèn BRPP và hướng dẫn reasoning | [Biên bản](decision_prior_integration.md), [receipt](decision_prior_integration_review.json): formatter W3, prefix một lần + reasoning, Original rỗng, empty/partial, node offline và bốn gate PASS | W4-06 | [x] |
| W4-08 | Ghép graph với ranh giới chuẩn bị báo cáo | [Biên bản/API](graph_prior_integration.md), [receipt](graph_prior_integration_review.json): Full riêng, Prior Preparation → Decision; 128 ca graph, bốn ablation/async/stream và bốn gate PASS | W4-05, W4-07 | [x] |

## C. PIT, ghép cặp và checkpoint

Chi tiết: [Phase C](phase_c_pit_paired_checkpoint.md).

| Mã | Task | Đầu ra / điều kiện hoàn thành | Phụ thuộc | Trạng thái |
| --- | --- | --- | --- | --- |
| W4-09 | Cài adapter context/regime PIT | Chứng minh nguồn trước retrieve; đúng cutoff, model và snapshot; không nhãn query | Gate A, W4-05 | [ ] |
| W4-10 | Tạo báo cáo chung cho năm nhánh | Ba agent upstream một lần/điểm; Full Alpha/Sentiment dùng chung, deep copy và call-count PASS | Gate B, W4-09 | [ ] |
| W4-11 | Ghép retriever vào backtest | Nạp kho một lần; năm kết quả có metadata/prefix; giữ kinh tế và output cũ | W4-09, W4-10 | [ ] |
| W4-12 | Lưu và phục hồi tiến trình từng nhánh | Ghi atomic; crash/quota/interrupt không mất báo cáo/nhánh đã xong; đổi hash/config bị chặn | W4-04, W4-11 | [ ] |

## D. Nghiệm thu tích hợp và bàn giao

Chi tiết: [Phase D](phase_d_validation_handoff.md).

| Mã | Task | Đầu ra / điều kiện hoàn thành | Phụ thuộc | Trạng thái |
| --- | --- | --- | --- | --- |
| W4-13 | Kiểm thử leakage toàn đường tích hợp | Giá/tin/model/prior/ranking/stats/prefix/checkpoint không lọt tương lai, lỗi trước API | Gate C | [ ] |
| W4-14 | Smoke E2E offline và tương thích | Luồng thật + LLM giả định xác định; năm nhánh, flag off, budget/paired/resume và JSON PASS | W4-13 | [ ] |
| W4-15 | Chạy bốn gate và kiểm phạm vi thay đổi | Compile/unit/E2E/leakage PASS; hash nguồn, receipt, ngân sách runtime và rủi ro hiệu năng đã rà | W4-14 | [ ] |
| W4-16 | Chốt W4, bàn giao điều kiện pilot W5 | 16 task có bằng chứng; hướng dẫn config/resume; gate giá/quota W5 và giới hạn nghiên cứu rõ | W4-01..15 | [ ] |

## Thứ tự và gate chuyển phase

1. W4-01 → 02 → 03 → 04: **Gate A PASS đặc tả**; đủ hợp đồng trước khi sửa runtime.
2. W4-05 → 06 → 07 → 08: **Gate B PASS** state/Decision/graph offline với verifier/retriever fixture.
3. W4-09 → 10 → 11 → 12: **Gate C** PIT, dùng chung báo cáo và resume PASS.
4. W4-13 → 14 → 15 → 16: **Gate D** đủ bốn gate và biên bản bàn giao.

Nếu task cần chia nhỏ khi triển khai, bổ sung mục con trong phase; giữ mã task
cha và phụ thuộc. Gate thất bại phải sửa nguyên nhân, cập nhật biên bản và chạy
lại phần bị ảnh hưởng; không đánh dấu PASS từ receipt W3.

## Checklist chốt tuần

- [ ] Flag tắt bảo toàn đường chạy cũ; cấu hình mới không thay nghĩa ablation cũ.
- [ ] Mọi context được chứng minh PIT trước query; prior `exit_date < cutoff`.
- [ ] Năm nhánh dùng cùng Full reports; không lặp upstream hoặc chia sẻ mutable state.
- [ ] BRPP ≤600 và toàn prompt backtest <6.500 ở đường runtime thật.
- [ ] Nhãn/P&L dùng engine thật: LONG Open(t+1)→Close(t+3), SHORT cash, phí hai chiều.
- [ ] Checkpoint có provenance/metadata đầy đủ; resume chỉ chạy phần còn thiếu.
- [ ] Compileall/unit/E2E/leakage PASS; smoke offline có receipt riêng.
- [ ] Bàn giao W5 với gate giá thô VCI/KBS, model PIT và quota; không tuyên bố OOS từ mock.

## Nhật ký tiến độ

### 2026-10-06 — W4-08 hoàn thành

- Nhánh `feat/shared-reports-prior-graph`, baseline `740031a`; thêm
  `compile_full_preparation()` và `compile_report_decision()` trong `utils/graph_setup.py`.
  Giữ `compile_upstream()`, hai builder cũ, `include_alpha` và bốn ablation.
- Full chuẩn bị Alpha/Sentiment riêng; Prior Preparation sở hữu retrieve/format
  một lần, Decision tiêu thụ output ngay sau đó. Config khóa lúc compile;
  state thô lỗi/alias/outcome/stale result bị chặn trước lọc channel.
- Verifier kiểm context trước query, result trước formatter; callback nhận
  bản sao JSON riêng. Default enabled thiếu verifier vẫn dừng; không lưu cờ PASS.
  API async/stream chuyển tiếp đúng config/kwargs; checkpoint chưa triển khai.
- **13 test mới**, **128 ca graph thật** PASS; đủ tám channel, Original/empty/
  partial, bốn ablation, deep copy, lỗi nguồn/API/overflow. Năm nhánh fixture:
  upstream mỗi node một lần, Alpha/Sentiment một lần, Decision năm lần.
- Max prompt **6.264**, BRPP đủ 600 + reasoning **6.467**. Compileall/**399 unit**/
  E2E/**56 leakage** PASS; [receipt](graph_prior_integration_review.json) ghi log/hash
  và kiểm byte các file bảo vệ. Kho/archive/receipt trước giữ nguyên.
- **Phase B 4/4, W4 8/16, Gate B PASS offline graph/prompt với fixture**.
  Tiếp theo **W4-09** adapter xác minh nguồn PIT thật. Điều phối năm nhánh trong
  engine, checkpoint/resume, Gate C/D, pilot LLM và OOS còn mở.

### 2026-10-06 — W4-07 hoàn thành

- Nhánh `feat/decision-prior-prefix`, baseline `75584b2`; thêm
  `core/decision_prior.py`, hook verifier nguồn tại factory Decision và
  `tests/test_decision_prior_integration.py`. Chữ ký cũ/ablation/live giữ tương thích.
- Kiểm config/query/Full reports, JSON, context/bank proof, tasks PIT/scope và
  metadata/counts/scores/stats; source verifier thành công trước formatter W3.
  Prefix phải đúng formatter, ≤600; một lần trước `### [1]`, reasoning VI/EN 181 ký tự.
- Original enabled K=0 vẫn kiểm nguồn/context/metadata; prompt bằng disabled
  khi cùng báo cáo/daily, không prefix/reasoning/stats. Empty/partial giữ None,
  mẫu số, status/reason; output và projection verifier có bản sao riêng.
- **11 test mới PASS**, capture text/structured cho năm nhánh và K=0..3;
  lỗi nguồn/API/output không bị nuốt, input sai không gọi LLM, overflow không
  truncate hoặc chuyển cash. Guard `<6500` sau toàn bộ BRPP/hướng dẫn.
- Receipt đo **128 ca node thật** với verifier/LLM fixture, max **6.264**;
  BRPP đúng **600** + reasoning có max **6.467**, còn 33 đến ngưỡng bị chặn.
  Alias daily canonical=`1d`; fixture không là bằng chứng source/model PIT.
- Bốn gate PASS: compileall; **386 unit** (97,298 giây), **E2E**
  (15,4 giây pipeline), **56 leakage** (9,010 giây). **2.391 file bảo vệ giữ hash**;
  kho 852 episode và receipt/spec W3/Phase A/W4-05/06 nguyên byte.
- [Biên bản](decision_prior_integration.md), [receipt](decision_prior_integration_review.json).
  **Phase B 3/4, W4 7/16**; Gate B còn W4-08 graph. Default/graph vẫn chặn
  enabled chưa có verifier nguồn thật W4-09; retrieve/paired/checkpoint và
  pilot/OOS chưa nghiệm thu. Tiếp theo **W4-08** ranh giới chuẩn bị Full và Decision.

### 2026-10-06 — W4-06 hoàn thành

- Nhánh `feat/decision-runtime-prompt-budget`, baseline `c0ab80a`; cap riêng
  backtest trend/pattern/indicator 800, alpha 1.100, sentiment 500 (tổng 4.000).
  Giữ cap live 4.500, chữ ký helper cũ và logic distill đầu/cuối/heading.
- Guard prompt cuối **<6.500** sau builder/hướng dẫn/schema chuỗi, trước retry
  wrapper và vòng format retry. Overflow ném `ValueError`, không gọi LLM hoặc
  trả quyết định thay lỗi. Log ghi cap/report/prefix/prompt và đúng ngưỡng.
- **11 test ngân sách PASS (8 mới)**: node thật trên **192 ca** VI/EN/daily/
  bốn mã/tổ hợp báo cáo; giữ hợp đồng kinh tế/conflict, đầu/cuối và input.
  Builder thật tại 6.499/6.500 xác minh text và structured output; retry giữ
  prompt đã kiểm, live giữ cap cũ, báo cáo thiếu và tên mã dài được kiểm.
- Prompt lớn nhất ma trận **5.688**; bốn fixture mở rộng builder với BRPP thật
  **600 ký tự** có max **6.289**, còn 211 đến ngưỡng bị chặn. Chèn/reasoning
  production vẫn chờ W4-07, phải đo lại sau khi thay template.
- Bốn gate PASS: compileall; **375 unit** (103,910 giây), **E2E**
  (15,5 giây pipeline), **56 leakage** (9,035 giây). **2.388 file bảo vệ giữ hash**;
  kho 852 episode, receipts W3/Phase A/W4-05 nguyên byte.
- [Biên bản](runtime_prompt_budget.md), [receipt](runtime_prompt_budget_review.json)
  ghi hash/lệnh/log/ma trận/phạm vi. **Phase B 2/4, W4 6/16**; Gate B và gate
  budget toàn luồng prior còn mở. Tiếp theo **W4-07** chèn BRPP/reasoning;
  graph/PIT/paired/checkpoint/pilot và giá OOS còn các task/gate riêng.

### 2026-10-05 — W4-05 hoàn thành

- Nhánh `feat/prior-runtime-state-config`, baseline `f2906b9`; thêm
  `core/prior_config.py`, tám field optional trong schema graph production và
  guard state trước/sau node tại ba builder hiện có; giữ topology/chữ ký cũ.
- Parser tám key strict, default disabled; enum/K/seed/path theo policy,
  enabled Full/backtest/daily, Original K=0 vẫn enabled; ablation và cờ cũ giữ nghĩa.
- JSON native/finite và deep copy; helper query kiểm ngày ISO/regime/tín hiệu.
  Flag off không I/O kho; dữ liệu prior còn sót bị từ chối. Enabled tự khai
  provenance không đủ, dừng trước node đến khi có adapter PIT W4-09.
- **28 test mới PASS**, gồm policy/ví dụ khóa, path containment, off/Original,
  conflict/legacy, JSON/date/ownership, optional schema và channel graph thật.
  Probe schema enabled không là phép chạy prior production đã xác minh nguồn.
- Bốn gate mới PASS: compileall; **367 unit** (59,045 giây), **E2E**
  (pipeline 7,8 giây), **56 leakage** (5,773 giây). **2.384 file bảo vệ giữ hash**;
  259 file W4-01 còn nguyên, hai file runtime state/graph được sửa có chủ đích.
  Receipt/spec Phase A và kho 852 episode giữ nguyên byte.
- [Biên bản runtime](state_config_runtime.md), [receipt](state_config_runtime_review.json)
  ghi nguồn/lệnh/log/hash/phạm vi. **Phase B 1/4, W4 5/16**; Gate B còn mở.
  Tiếp theo **W4-06** cap/guard prompt; BRPP/graph nghiên cứu, PIT, retrieve,
  checkpoint và giá thực thi OOS chưa nghiệm thu.

### 2026-10-05 — W4-04 và Phase A hoàn thành

- Nhánh `docs/research-checkpoint-contract`, baseline `e3aa3f8`; khóa
  [contract kết quả/checkpoint](checkpoint_contract.md), schema/policy/ví dụ và receipt riêng.
- Ba loại envelope: run manifest, point checkpoint và result dẫn xuất; schema
  nghiên cứu riêng, giữ Full/No-Alpha/legacy reader khi flag tắt.
- Identity khóa config/plan/bank/nguồn/model/template/code; key và hash key
  không được lưu. Shared Full durable trước Decision, persist từng nhánh;
  resume không gọi lại branch complete, không đưa evaluation vào agent.
- Chốt OS lock giữ bằng handle; khóa còn file không tự chặn resume. Crash
  upstream/Full chưa có output durable phải dừng ambiguous; không tự lặp vision.
  Crash sau nhánh cuối chỉ evaluate/seal/rebuild result offline.
- **4 document mẫu**, **7 shape trạng thái**, **11 ca schema sai**, **5 projection
  retriever thật**, **8 mutation signature**, **3 probe atomic/strict reader** PASS.
  Decision là fixture; failpoint/lock/resume mới chưa triển khai, chờ W4-12.
- Bốn gate mới: compileall; **339 unit** (130,278 giây), **E2E** (17,6 giây),
  **56 leakage** (6,097 giây) PASS. 2.312 file giữ hash; kiểm lại 261 file
  bằng chứng W4-01. Receipt W4-01..03 giữ nguyên.
- **Gate A PASS_CONTRACTS_ONLY**, Phase A **4/4**, W4 **4/16**.
  Tiếp theo **W4-05** state/config validator; runtime budget/paired/checkpoint,
  Gate B/C/D, pilot LLM W5 và giá thực thi OOS 2023–2024 còn mở.

### 2026-10-05 — W4-03 hoàn thành

- Nhánh `docs/prior-provenance-contract`, baseline `545e34c`; khóa
  [provenance v1](provenance_contract.md), policy, ví dụ và receipt riêng.
- Chốt giá raw VCI/crosscheck KBS, hash snapshot/window/Alpha; tin dated ≤cutoff,
  coverage trước giới hạn hiển thị và NEUTRAL có lý do khi thiếu ba bài.
- Replay dùng artifact train-end=cutoff, readonly `verify_only=True`; OOS dùng
  model đóng băng train-end<cutoff, kiểm toàn prefix train và ba component.
  Model full-train `RESEARCH_ONLY/UNVERIFIED` chỉ dùng probe kỹ thuật.
- Năm context nguồn thật (bốn mã và biên bằng exit), hai ví dụ provenance đầy đủ;
  **14 probe API hiện có PASS**. **14 ca adapter chỉ là đặc tả** cho W4-09/13.
  Outcome query giữ ngoài state/retriever; lỗi nguồn dừng trước upstream,
  lỗi tín hiệu trước retrieve, lỗi pool/stats trước formatter/Decision.
- Compileall / **339 unit** (48,126 giây) / **E2E** / **56 leakage** (5,077 giây)
  PASS; 2.308 file nguồn/bằng chứng/archive giữ hash trước/sau gate.
- **Tiếp theo W4-04** khóa schema/signature/checkpoint. Tiến độ **3/16**,
  Phase A **3/4**; Gate A, adapter/provider OOS runtime và gate giá OOS còn mở.

### 2026-10-05 — W4-02 hoàn thành

- Nhánh `docs/prior-state-config-contract`, baseline `62a673a`; [contract](integration_contract.md)
  và policy/ví dụ khóa config/state, lỗi và ownership dữ liệu; chưa sửa runtime.
- Flag off không I/O nguồn mới; Original enabled K=0 vẫn query/validate. Prior
  enabled chỉ ablation Full trong backtest, cấu hình độc lập với ablation cũ.
  Daily nhận `1d`/`1 ngày`, canonical=`1d`; adapter mới từ chối `1 day`.
- Bảy ví dụ config và bốn projection W3 đã đối chiếu; prefix 0/338/190/237 ký tự,
  bảy probe query sai W3 PASS. Các ca config mới chờ validator W4-05.
- Compileall / **339 unit** (91,391 giây) / **E2E** (13,8 giây) / **56 leakage**
  (7,637 giây) PASS; [receipt](state_config_review.json) ghi hash/version/log.
- **Tiếp theo W4-03**: provenance và trình tự PIT. W4-04/checkpoint, Gate A,
  runtime integration/budget và giá OOS còn mở; tiến độ 2/16, Phase A 2/4.

### 2026-10-05 — W4-01 hoàn thành

- Kiểm đầu vào trên baseline `516d0ed`, nhánh `docs/prior-runtime-readiness`:
  99 file bằng chứng + 176 file nguồn bàn giao W3 khớp checksum; 852 record
  đúng schema/nhãn kinh tế, 852 cặp episode/signal, 217 prefix và staging khớp.
- Replay mới 32 context: **288 query + 288 lượt lặp**, BRPP max **373**, đủ
  mode/scope và Original. Không gọi LLM/mạng, fit model hoặc sinh episode.
- Bốn gate **compileall / 339 unit / E2E / 56 leakage PASS**; số liệu/lệnh/log/hash
  tại [receipt](input_readiness.json). Giữ 261 file bảo vệ trước/sau gate.
- [Biên bản](input_readiness.md) có luồng live/backtest, điểm nối, schema callback/
  web và khoảng trống resume nhánh; `.gitattributes` bảo toàn byte receipt W4.
- W4-02 tiếp tục khóa state/config; cap/guard runtime, provider PIT/OOS và
  gate giá thô 2023–2024 chưa PASS. **Phase A chưa hoàn thành.**

### 2026-10-05 — Lập kế hoạch

- Đã khảo sát bàn giao W3, state/graph/Decision, đường backtest ghép cặp và test hiện có.
- Chia 16 task vào bốn phase; khóa ranh giới W4 offline và pilot W5.
- Chưa triển khai task W4, chưa thay đổi runtime/kho/model hoặc mở gate giá OOS.
- Kiểm tra năm tài liệu: đủ 16 task/16 mục chi tiết duy nhất, liên kết hợp lệ,
  tất cả checklist triển khai đang mở; `git diff --check` PASS.
- Gate trước khi merge nhánh kế hoạch `docs/runtime-prior-integration-plan`:
  compileall PASS; **339/339 unit** (47,935 giây), E2E xác định **7,0 giây**,
  **56/56 leakage** (5,111 giây) PASS. Lệnh theo AGENTS.md và [Phase D](phase_d_validation_handoff.md).
- Đây là kiểm hồi quy cho thay đổi tài liệu trên runtime hiện có; không là
  nghiệm thu các task W4-05..15, runtime prior/budget hoặc dữ liệu OOS.
