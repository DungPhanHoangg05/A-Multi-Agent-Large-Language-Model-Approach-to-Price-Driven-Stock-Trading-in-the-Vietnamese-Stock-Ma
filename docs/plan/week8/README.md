# Tuần 8 — Cải tiến Bayesian ICL, validation và khóa xác nhận

**Trạng thái: COMPLETE, 8/8; W8-01–08 DONE, Gate W8 PASS; tiếp theo W9-01.**
Kế hoạch điều chỉnh 16/10/2026; cập nhật 20/10/2026; giữ deadline 10 tuần.
[Kế hoạch tổng](../plan.md) · [W7](../week7/README.md) · [W9](../week9/README.md)

## Mục tiêu và giới hạn

Cải thiện Bayesian ICL bằng một vòng có đối chứng, tối đa **hai cấu hình
phương pháp mới**. C2 NOT_PROMOTED/Original là mốc selection W7; selection
development W8 đã khóa A_tp_pool PROMOTED tại W8-06, chờ xác nhận holdout.
Không thay selection/report/checkpoint W7. Đầu vào là Gate D
mới của W7, report 60 điểm/11 nhánh và hồ sơ nguyên nhân W7-13.

Phân bổ dự kiến: 40% thời gian triển khai/kiểm offline, 35% validation và
phân tích, 25% khóa protocol/manifest/bàn giao. Đây là phân bổ công việc,
không yêu cầu dự toán hoặc lịch API. Đến phần khóa thì dừng tối ưu phương
pháp; lỗi integrity phải sửa hoặc chặn run, không bỏ gate để kịp deadline.

## Protocol cải tiến đã khóa tại W7-14

**Đặc tả `improvement_protocol_v1`, 16/10/2026.** Đây là quyết định phương
pháp trước API, chưa phải schema/registry/runner đã triển khai. Căn cứ là
[chẩn đoán W7-13](../week7/README.md#chẩn-đoán-development-và-kiểm-attribution-16102026):
11/60 stats ready, 8/60 cả hai ready và 3 bất đồng prior-off trên hai point.
W8-01 chỉ ánh xạ đặc tả này vào identity/version và kiểm khả năng thực thi;
không mở lại lựa chọn phương pháp hoặc sweep tham số theo return.
Sửa đặc tả phải có amendment/version và lý do trước API; nếu đã xem kết
quả thì công bố thay đổi và trạng thái exploratory, không ghi đè bản đã khóa.

| ID dành trước | Giả thuyết / thay đổi duy nhất | Đối chứng cô lập | Version dự kiến |
| --- | --- | --- | --- |
| `A_tp_pool` | Khớp cứng cả T/P/A/I làm thưa support; mở nhóm conditional sang khớp T/P, giữ co Bayes từ background rời nhau | C2 cùng query, retrieval, schema và cách trình bày; chỉ counts/posterior cùng mô tả điều kiện đổi | `conditional_tp_disjoint_beta_v1`, `compact_brpp_v3_tp_v1` |
| `B_semantic` | Ngữ nghĩa prefix có thể khó hiểu; trình bày rõ sự kiện, support và bất định | C2 cùng base evidence, visible IDs/counts/K, schema và chỉ dẫn ngoài prefix | `compact_brpp_semantic_v1` |

**A:** P giữ cùng mã/regime và exit<cutoff. C_A gồm episode có trend và
pattern bằng query, không dùng alpha/indicator để chia nhóm; B_A=P\C_A.
Giữ chính xác masks/numerator/denominator bốn metric của C2. Với mỗi
metric, s_C/n_C và s_B/n_B được đếm trên hai nhóm rời nhau;
m_B=(s_B+1)/(n_B+2), alpha_0=4m_B, beta_0=4(1−m_B), posterior
Beta(alpha_0+s_C, beta_0+n_C−s_C). n_C=0 vẫn mean/CrI=null;
n_B=0 dùng m_B=0,5. Không dùng P làm likelihood lần nữa. Counts nguyên,
mỗi cycle một lần; không weighted count, không học/sweep strength.
Template v3 chỉ đổi mô tả `C=khớp T/P/A/I` thành `C=khớp T/P` và version;
không đổi renderer ví dụ hoặc chỉ dẫn Decision. A kiểm khả năng tăng support
và chất lượng xác suất, không mặc định rằng nhóm rộng hơn có hiệu quả tốt hơn.

**B:** dùng nguyên evidence/gate C2, kể cả các block tắt. Render theo thứ tự
W/BT/TF/PF tương ứng `win_rate_long`, `bull_trap_rate`,
`trend_false_bullish_rate`, `pattern_false_bullish_rate`; metric không ready
ghi `N/A`, số mean/CrI làm tròn hai chữ số chỉ để hiển thị. Khung prefix:

```text
[BRPP v4] R={regime}; k={visible_k}; nP={population_count}; nC={conditional_count}
W={s}/{n}→{mean}[{lo},{hi}]; BT={...}; TF={...}; PF={...}
W=LONG ròng>0; BT/TF/PF=bẫy/sai tăng; tỷ lệ lịch sử khớp T/P/A/I.
Mean[CrI95%] plug-in, không P(query)/E(return); SHORT=CASH.
T/P/A/I:+ tăng,- giảm,0 trung tính; W/L=LONG ròng lịch sử.
{các dòng ví dụ giữ nguyên renderer và thứ tự C2}
```

Không có metric visible thì bỏ nP/nC và ba dòng thống kê, thay bằng
`Ví dụ lịch sử; không dự báo query; SHORT=CASH.`. Không có examples visible
thì bỏ dòng giải mã T/P/A/I và các dòng ví dụ. Không block nào visible thì
prefix rỗng. Giữ chỉ dẫn ngoài prefix và `TradeDecisionOutput` bảy field;
không thêm `prior_use`, không bắt model theo prior, không đổi risk policy.
Đây là thay đổi cách diễn đạt và bố cục chung; không quy riêng hiệu ứng cho
một từ hoặc một dòng. Dựng thử từ 29 evidence C2 visible cũ cho tối đa
453 ký tự; đây chỉ là QA bản nháp, chưa thay kiểm producer/token W8.

**Các hằng số:** cùng bank/index/scaler/model và lịch đã khóa; P≥20,
support conditional từng metric≥5, CrI width≤0,75, strength=4. Retrieval
giữ w_signal=0,5, half-life=365 ngày, max_age=730 ngày, similarity≥0,625,
gap≥5 phiên, K=3, seed=42, same_symbol. Không thay feature/corporate-action
guard để tăng coverage; không thêm regime mềm, cross-symbol, bank mới,
expected-return model, risk overlay hoặc A+B. BRPP≤600, prompt<6.500,
giữ distill/cap. Lỗi cấu trúc/PIT ném lỗi; thiếu support hợp lệ fallback
Original, giữ query trong mẫu. Mọi cấu hình thử đều được báo, kể cả kết quả âm.

## Checklist tuần 8

| Task | Công việc và đầu ra | Phụ thuộc | Trạng thái |
| --- | --- | --- | --- |
| W8-01 | Ánh xạ protocol W7-14 vào registry/version; kiểm khả năng thực thi, identity và audit byte prior-off | W7 Gate D | [x] DONE |
| W8-02 | Triển khai thay đổi tối thiểu, producer/loader/verifier và version mới; không sửa artifact cũ | 01 | [x] DONE |
| W8-03 | Kiểm posterior/PIT/fallback/token/paired; bốn gate kỹ thuật; khóa plan/output development mới | 02 | [x] DONE |
| W8-04 | Người dùng preflight/run/resume theo hướng dẫn; Decision thật trên 60 điểm, mọi nhánh chung upstream | 03 | [x] DONE — 660/660 primary, verifier report PASS |
| W8-05 | Chạy/verify đủ mẫu lặp nối primary đã nghiệm thu; phân tích ΔR/MDD/coverage/ablation/prior-off và độ ổn định | 04 | [x] DONE — 432/432 repeat, verifier và phân tích PASS |
| W8-06 | Khóa selection mới và lý do; giữ ngưỡng W6-04, báo mọi cấu hình đã thử | 05 | [x] DONE — A_tp_pool PROMOTED, selector/verifier PASS |
| W8-07 | Khóa ma trận, thống kê, manifest holdout 64 điểm; dry-run và kiểm công cụ phân tích bằng fixture | 06 | [x] DONE — 64 điểm/6 nhánh, manifest/dry-run/fixture và bốn gate PASS |
| W8-08 | Nghiệm thu bốn gate, hash nguồn/runtime và hướng dẫn chạy/verify/resume W9 | 07 | [x] DONE — release/hash/gate/hướng dẫn W9 PASS |

### W8-01 — Ánh xạ registry, capability và identity, 17/10/2026

**DONE, chỉ kiểm toán và ánh xạ.** Đầu vào [Gate D W7 PASS](../week7/README.md#bàn-giao-và-nghiệm-thu-16102026)
đã đối chiếu với code và artifact local. Không đổi đặc tả W7-14 ở trên hoặc
protocol W9. A/B vẫn **NOT_RUN**; các version dành trước dưới đây chưa là
schema/runtime được chấp nhận. Chưa mở gate API W8 hoặc holdout.

**Registry đích:** `improvement_candidates_v1`, tách khỏi
`prior_candidates_v1` sáu hồ sơ W7. Thứ tự primary giữ đúng 11 ID trong
protocol bên dưới; tập nomination chỉ `C2, A_tp_pool, B_semantic`.

| Hồ sơ đích | Base evidence / statistics | Gate / prefix | Decision / content mode |
| --- | --- | --- | --- |
| `original`, `bayesian` | Đường Original và Bayesian v1 hiện có, cùng shared bundle | Giữ request contract từng đường làm đối chứng | `decision_legacy_v1`, không thêm prior-use |
| `C2` | `prior_evidence_v3` / `conditional_disjoint_beta_v1`, khớp T/P/A/I | `split_quality_gate_v2` / `compact_brpp_v3` | `decision_legacy_v1` / `full_prior` |
| `A_tp_pool` | `improvement_prior_evidence_v1` / `conditional_tp_disjoint_beta_v1`, chỉ đổi partition C/B sang T/P | Cùng ngưỡng `split_quality_gate_v2` / `compact_brpp_v3_tp_v1` | `decision_legacy_v1` / `full_prior` |
| `B_semantic` | Nguyên base evidence/hash/statistics C2; không dựng nhóm mới | Cùng gate/visible IDs C2 / `compact_brpp_semantic_v1` | `decision_legacy_v1` / `full_prior` |
| `{C2,A_tp_pool,B_semantic}_stats_only`, `{C2,A_tp_pool,B_semantic}_examples_only` | Cùng base/hash với full tương ứng; sáu ID riêng | Cùng renderer/version của base, chỉ ẩn block theo content mode | `decision_legacy_v1` / `stats_only` hoặc `examples_only` |

`original_duplicate` chỉ là alias request Original trong repeat, không thuộc
11 ID primary hoặc tập nomination. Không mượn C3 cho ablation C2: C3 visible
dùng `decision_prior_use_v1`. Evidence A phải có discriminator/version riêng
và được tái dựng từ bank; không đổi nghĩa `prior_evidence_v3`/statistics C2.
Request revision `improvement_prior_request_v1` bind ID/base evidence,
content mode, visible IDs, prefix/version và query/source; hash base chung
không thay hash request riêng. C2/B giữ base evidence v3 nguyên vẹn trong
revision mới; parser/validator phải phân biệt evidence A với C2/B.

**Biên cần giữ khi làm A:** không sửa `SIGNAL_FIELDS` toàn cục thành T/P,
vì `core/prior_price_similarity.py` cũng dùng bốn field đó để chấm retrieval.
Chỉ chọn trường khớp partition tại producer thống kê A; selection/query
features/index/scaler và examples phải giống C2 trên cùng query. B giữ cả
statistics và selection C2; các mode chỉ đổi visibility/prefix theo đặc tả.

**Capability thực và biên cần triển khai:**

| Biên hiện tại | Khoảng trống đã đối chiếu | Revision / producer → loader/verifier đích |
| --- | --- | --- |
| `core/prior_conditional_statistics.py`, `core/prior_quality_gate.py` | Conditional chỉ khớp toàn bộ `SIGNAL_FIELDS`; config không có method selector. Quality producer luôn gọi statistics hiện tại | W8-02: producer A cùng masks/counts/hyperprior, version riêng; validator rebuild P/C_A/B_A và posterior, giữ C2. Tái dùng logic readiness, không đổi ngưỡng |
| `core/prior_prompt.py`, `agents/decision_agent.py` | Whitelist request chỉ C1/C2/C3 và ablation C3; renderer chỉ compat/v3; binding hard-code request v1/evidence v3 | W8-02: builder/validator/binding request revision, renderer A/B và ablation C2 legacy; kiểm B cùng base/visible IDs C2, prior-off prefix rỗng/schema legacy/prompt Original nguyên byte |
| `core/candidate_cohort.py`, `core/research_cohort.py` | Registry/plan v3 cố định sáu hồ sơ, thứ tự chạy theo mã; slot `(signature, point, candidate)` không có repeat ID | W8-02: prepare/validate `improvement_cohort_plan_v1`, registry mới; scheduler theo ngày/xoay nhánh, `improvement_run_identity_v1`, `improvement_decision_checkpoint_v1`; kiểm slot/order/resume và shared bundle |
| `core/prior_stage_journal.py`, `core/research_invocation.py`, `core/groq_pacing.py` | Durable/UUID có sẵn; ledger chưa lưu canonical body/schema hash, repeat ID hoặc request fingerprint để so lặp | W8-02: bind slot `(run, point, branch, repeat_id)` và transport audit vào attempt; `improvement_repeat_plan_v1` nối shared/request primary. Verify đủ ba lượt và duplicate, không replay upstream/complete; giữ retry/pacer/unknown |
| `core/paired_candidate_report.py`, `core/prior_disagreement_analysis.py`, `core/candidate_selection.py` | Report v5/matrix và ORDER sáu hồ sơ cố định; chưa có repeat/subgroup mới hoặc selector ba full-prior | W8-02: producer/read/verify `improvement_report_v1`, `improvement_repeat_report_v1`, `improvement_selection_v1`; `improvement_nomination_rules_v1` bind thứ tự C2/A/B, giữ nguyên ngưỡng và tie tolerance; report repeat không vào D primary |
| `core/train_pit_validation.py` | Replay PIT 852 episode/651 query có sẵn; summary cũ chưa có giao A/C2, Brier/log loss hoặc mean lãi/lỗ | W8-02: build/read/verify `improvement_train_diagnostics_v1`; dựng prior trước đọc nhãn query để scoring, báo giao/missing và raw/ready; không gọi Decision/LLM train |
| `scripts/run_bayesian_ablation.py`, `scripts/run_provider_validation.py`, `core/provider_quota.py` | Dispatch chỉ plan/identity cũ; provider entrypoint kiểm amendment gắn plan/code/gate W7 | W8-02–03: dispatch revision mới, producer/loader/verifier và policy/extension binding mới; dry-run, verify, lệnh vận hành thật sau gate. Không ép A/B vào CLI hay amendment cũ |
| `core/holdout_protocol.py`, `core/research_metrics.py`, `utils/statistical_tests.py` | Holdout v4 bind selection v1; bootstrap accuracy hiện có không dựng lại tài khoản bằng circular cụm ngày | W8-07: prepare/validate `improvement_bound_holdout_v1`, producer/loader/verifier thống kê `improvement_bootstrap_v1` và fixture W9. Chỉ sau selection W8; không dùng utility accuracy thay CI D |

Đường dẫn artifact theo [namespace W7-15](../week7/README.md#kiểm-nguồn-và-bản-đồ-tái-lập-16102026),
dưới `outputs/bayesian_benchmark/improvement_v1/`; chưa tạo namespace hoặc
JSON rỗng. Mỗi revision cần producer, loader semantic và verifier consumer;
`read_envelope` chỉ kiểm envelope/hash. W8-02 dùng [bản đồ test W7-15](../week7/README.md#kiểm-nguồn-và-bản-đồ-tái-lập-16102026)
để bổ sung ca thật; W8-03 phải có bốn gate mới trước API.

**Identity mới phải khóa:**

- Protocol/version và canonical hash của đối tượng đặc tả phương pháp đã
  ánh xạ từ W8/W9; không hash toàn bộ README có checklist thay đổi. Registry,
  matrix/content modes/schema, nomination rules, lịch 60 point và thứ tự
  xoay, mẫu repeat 12 point/ba lượt/duplicate, quy tắc report primary/repeat
  đều phải nằm trong binding; thay đổi phải tạo identity mới.
- Bank/index/scaler/model/fold/calendar/source hashes đã khóa; code phương
  pháp mới chuẩn hóa LF, extension provider/transport và runtime/dependencies
  có binding kiểm được. Giữ model/options, max_retries=0, kinh tế/PIT/risk OFF,
  token và ledger tài khoản chung; không reset ledger để tạo run mới.
- Primary repeat_id=0, repeat_id=1/2/3 tách namespace; shared bundle/projection
  và request contract phải nối được giữa các lượt. Lưu SHA-256 prompt UTF-8,
  canonical HTTP body gồm messages/response_format/model/options tại transport
  không kèm credential/header; lưu response fingerprint/thời điểm/attempt.
  Canonical JSON hash không được mô tả là hash byte HTTP thô.
- Tái dùng upstream W7 chỉ sau verifier tương thích source/model/options/
  projection. Chưa có verifier đó, vì vậy chưa phê chuẩn reuse; nếu không
  chứng minh được thì tạo upstream mới một lần/point cho toàn bộ nhánh.
  Mọi Decision primary chạy mới; không chép action W7. Khi code đã bind đổi,
  tái lập W7 bằng checkout/runtime cũ và ledger đúng đường dẫn, không vá hash.

**Audit prior-off từ bằng chứng thật:** đọc lại 60 point và 360 checkpoint
ứng viên được bind trong report W7; 202/202 prompt prior-off trùng byte UTF-8
Original cùng point/shared. Các đường này đều ghi `llm_structured`, không có
prior-use; request có prefix rỗng dùng `decision_legacy_v1`. Đối chiếu node
Decision hiện tại chọn `TradeDecisionOutput` bảy field cho contract legacy,
và builder dùng cùng model/options đã khóa; đây là kiểm contract theo code,
không thay bằng chứng HTTP body lịch sử chưa được lưu.

| Nhánh W7 | Prior-off / prompt trùng byte Original |
| --- | --- |
| C0 | 23/23 |
| C1 | 34/34 |
| C2 | 31/31 |
| C3 | 31/31 |
| C3_stats_only | 49/49 |
| C3_examples_only | 34/34 |
| Tổng | 202/202 |

Giữ cả ba bất đồng action: C1 và C2 tại `MWG-2023-07-05`,
C3_stats_only tại `VCB-2023-08-29`; không quy kết nguyên nhân provider hoặc
coi request cùng byte là bảo đảm response xác định. Revision W8 phải kiểm
lại off/disabled/K=0 và mode ẩn hết block bằng producer mới; kết quả W7 không
chứng nhận hành vi A/B chưa triển khai. Mẫu 12 point tính lại từ ngày/readiness
C2 khớp bảng đã khóa; phép xoay repeat cho mỗi vị trí bắt đầu đúng ba lần,
không dùng action/return để chọn mẫu.

**Nghiệm thu W8-01:** code/runtime/registry/amendment và hash nguồn/checkpoint
khớp plan/report W7; C2 vẫn NOT_PROMOTED, Original triển khai, risk OFF.
770 file nguồn/bằng chứng giữ nguyên byte, gồm 205 Python, 485 checkpoint
đã bind, plan/report/selection/ledger, README W7/W9 và log gate W7.
QA mapping/version, mẫu/thứ tự, checklist/liên kết/diff và byte prior-off PASS.
Chỉ sửa README W8 và kế hoạch tổng; không đổi code/test/runtime/schema/dữ liệu,
không gọi API hoặc mở outcome holdout. Không chạy compileall/unit/E2E/leakage
theo AGENTS.md mục 1.2; bốn gate W7-15 là bằng chứng cùng code/runtime
(859 unit/163 leakage, compileall/E2E PASS), không ghi là chạy lại W8-01.
Tiếp theo **W8-02** triển khai revision; W8 đạt **1/8**, Gate W8 chưa mở.

### W8-02 — Triển khai producer/loader/verifier cải tiến, 17/10/2026

**DONE.** Bản triển khai dựa trên checkout
`7d6761f`, giữ registry và artifact W7; chỉ thêm dispatch request revision
trong `core/prior_prompt.py` ở đường legacy. Các module mới:

| Module | Hành vi / consumer |
| --- | --- |
| `core/improvement_prior.py` | A khớp partition T/P với background rời nhau, giữ masks/strength/retrieval C2; B giữ base evidence C2 và render ngữ nghĩa. Producer/validator evidence và request revision; cả chín profile dùng schema legacy, fallback nguyên prompt Original |
| `core/improvement_protocol.py` | Registry 11 ID, rules ba full-prior, protocol canonical, plan producer/loader/validator; lịch xoay toàn cohort và mẫu repeat cố định. Pin plan development W7 nguyên byte, kiểm code/runtime/nguồn/index/calendar, warm-up/entry/exit trước API; tự băm lại parent không tạo provenance mới |
| `core/improvement_runtime.py` | Graph upstream/Full và journal hiện có, một bundle/point deep-copy; Decision primary mới, slot repeat_id=0/1/2/3, duplicate, intent/raw durable, resume phần thiếu và đối soát UUID. Repeat phải khớp request primary trước invocation |
| `core/improvement_transport.py` | Tái dùng pacer/retry provider; audit hash canonical body/schema/model/options trước HTTP, fingerprint nối response với raw message durable; không lưu credential/header, không gọi hash canonical là byte HTTP thô |
| `core/improvement_reports.py` | Report primary/repeat tách nhau, G/pairwise/null/coverage, subgroup/ablation/prior-off, tài khoản từng mã và mean ba repeat. Selector C2/A/B giữ ngưỡng/tie, fixture luôn BLOCKED; loader so toàn artifact với bản tái dựng |
| `core/improvement_diagnostics.py` | Replay train PIT rồi mới scoring nhãn kinh tế; giao posterior A/C2, Brier/log loss/raw-ready/missing và mean lãi/lỗ riêng. Producer/loader/verifier không gọi Decision, mean return có đơn vị fraction |
| `scripts/run_improvement.py` | CLI riêng, offline mặc định; prepare/dry-run/verify/report/selection/train/reconcile và primary/repeat. Chặn fixture online; source/identity/gate/tokenizer hợp lệ trước đọc key, giữ ledger chung và policy provider |

Không tái dùng upstream W7 ở revision này: tạo mới một lần cho primary,
repeat chỉ đọc bundle primary đã verify. Không chép action W7. Body audit
dùng serializer SDK đã ghim và được kiểm qua HTTP mock; retry/format repair
không tăng repeat_id. Bốn gate mới đã PASS; W8-03 vẫn phải kiểm/khóa plan
và hướng dẫn trên nguồn development thật. Client khóa cả defaults/kwargs
SDK, không nhận seed/stop hoặc tùy chọn sampling ngoài protocol.

Sáu module test mới kiểm công thức/masks/partition và cô lập A/B, null/PIT,
schema/token/fallback, scheduler/shared, missing/tamper/unknown/resume,
repeat/duplicate, SDK transport/429/fingerprint, selector và CLI không đọc
key khi offline. Fixture chỉ kiểm tính đúng, không là kết quả hiệu quả A/B.
**Nghiệm thu:** 26 test mới PASS trong toàn suite; fixture primary bốn point
có 44 Decision, ba lượt repeat có 144 Decision mới, verify/resume không gọi
lại upstream hoặc Decision complete. Đây không là Decision API hoặc bằng
chứng hiệu quả A/B trên development. Compileall, **885 unit**, E2E và
**167 leakage PASS**, không skip; 218 Python nguyên byte trong lượt gate.
Receipt [technical_gates.json](validation_gates/implementation_v1/technical_gates.json)
bind 68 file code/schema/config và runtime mới, đã qua consumer
`read_technical_gates`; SHA-256 byte:
`30bfecfebe80a1b7170760b0cd7f41a411f9b857dff78d993787acbecc14eb42`.
Log [compileall](validation_gates/implementation_v1/compileall.log),
[unit](validation_gates/implementation_v1/unit.log),
[E2E](validation_gates/implementation_v1/e2e.log),
[leakage](validation_gates/implementation_v1/leakage.log) giữ nguyên byte,
hash từng log nằm trong receipt được consumer kiểm thực.

769 file của mốc W8-01 giữ nguyên byte, gồm bằng chứng W7, ledger,
README W7/W9 và 204 Python cũ; chỉ `prior_prompt.py` thêm dispatch cho
request revision, không đổi registry/nhánh legacy. Đặc tả phương pháp,
development/repeat và W9 giữ nguyên; không vá binding hoặc receipt W7 để
nhận code mới. QA diff/liên kết/checklist/hash PASS. Chưa tạo namespace,
plan, diagnostics hoặc Decision development mới; A/B thực vẫn NOT_RUN,
C2 NOT_PROMOTED/Original/risk OFF giữ nguyên. Holdout/CI thuộc W8-07,
chưa triển khai ở task này. **W8 đạt 2/8**, tiếp theo **W8-03**; Gate W8 chưa mở.

### W8-03 — Kiểm hợp đồng và khóa development, 17/10/2026

Các hash và gate trong mục này ghi nhận mốc W8-03 trước lần reset bên dưới;
plan tại cùng đường dẫn đã được producer tạo mới theo revision W8-04.

**DONE.** Plan mới được producer `scripts/run_improvement.py --prepare`
tạo offline tại `outputs/bayesian_benchmark/improvement_v1/development/plan.json`.
Loader kiểm parent W7 nguyên byte, registry/protocol, 68 file code/schema/config,
runtime, nguồn/index/scaler và lịch 60 điểm (FPT 12, MWG/VCB/VNM mỗi mã 16).
Warm-up, cycle không chồng lấn, giá Open(t+1)/Close(t+3) và corporate-action
guard được kiểm trước API. Ma trận giữ 11 nhánh, risk OFF, nomination chỉ C2/A/B.

Plan bind 51 nguồn; SHA-256 byte
`87aba5ead1e8dc5d764821b523d218a9d2a14bb7f10dac192eb9da640b177900`.
Protocol canonical SHA-256
`3d282df4038c9a57d1a04c5e73c13a6a21d150953ab806a58cb1b7c44310d831`;
index giữ `outputs/bayesian_benchmark/price_features/candidate_index_v1.json`.
Prepare và dry-run nguồn/PIT trên plan thật đã PASS, không đọc key/gọi API.

Output primary dành riêng tại
`outputs/bayesian_benchmark/improvement_v1/development/run/`; repeat tại
`outputs/bayesian_benchmark/improvement_v1/repeats/run/`. Chưa tạo manifest,
slot hoặc report giả cho run thật. Runtime khởi tạo toàn bộ slot trước request
đầu tiên; không chuyển checkpoint/action W7 sang output mới. Plan repeat chỉ
được producer tạo sau khi primary COMPLETE và report khớp verifier; mẫu 12
điểm/ba lượt/thứ tự đã nằm trong protocol của plan primary từ trước API.
Holdout/CI và selection chưa mở ở W8-03.

**QA nguồn thật:** tái dựng cả 60 bundle Full W7 đã seal bằng adapter hiện tại,
chỉ dùng chúng làm đầu vào kiểm offline, không chuyển vào run W8. Cả bốn
metric A/C2 được đếm độc lập từ episode/mask/sự kiện kinh tế: P=C+B, C/B rời
nhau, đúng mã/regime và exit<cutoff; partition A chỉ khớp T/P, C2 khớp T/P/A/I.
Posterior mean khớp công thức strength=4, C rỗng giữ null. A giữ selection
C2; B giữ nguyên evidence/hash C2; renderer C2 giữ nguyên. Request semantic
validator và hook Decision kiểm cả chín profile, schema legacy bảy field,
không thay shared projection và không invoke LLM. **312/312 fallback prompt
trùng byte UTF-8 Original**, bao gồm các mode ẩn hết block. BRPP dài nhất
**494** ký tự, prompt dài nhất **4.671**, đều dưới trần đã khóa.

| Base trên bundle W7 dùng cho QA | Stats visible | Examples visible | Full visible | Max BRPP / prompt full |
| --- | ---: | ---: | ---: | ---: |
| C2 | 11/60 | 26/60 | 29/60 | 486 / 4.504 |
| A_tp_pool | 34/60 | 26/60 | 36/60 | 494 / 4.671 |
| B_semantic | 11/60 | 26/60 | 29/60 | 453 / 4.492 |

Các số trên chỉ chứng nhận producer/rendering với nguồn lịch sử, không là
coverage của primary W8 chưa chạy hoặc bằng chứng A tốt hơn C2. Mẫu repeat
12 điểm khớp lịch đã khóa; phép xoay 36 block cho mỗi nhánh bắt đầu đúng ba
lần. Kiểm paired/upstream một lần, deep-copy, resume complete không gọi lại,
disabled/K=0, null, tamper và future-outcome poisoning thuộc suite kỹ thuật.

**Diagnostics train:** producer offline tạo
`outputs/bayesian_benchmark/improvement_v1/train/diagnostics.json`,
replay 852 chu kỳ và scoring 651 query 2021–2022 sau khi dựng prior theo fold
PIT/bootstrap 2020; Decision/LLM=0. SHA-256 byte
`9c912f3b783237ff8a50de75d3eedc84c9c21388b61cb722b97ea9779b62722c`.
Verifier `--verify-train` đã tái dựng toàn artifact từ nguồn và **PASS**, file
diagnostics giữ nguyên byte. Giao hữu hạn gồm 388 query;
loss dưới đây dùng đúng cùng giao, không điền xác suất cho C rỗng, chỉ clip
khi tính log loss. Raw/ready là riêng metric `win_rate_long`, không là số
Decision thực đã thấy prior.

| Base | Posterior raw / ready trên 651 query | Missing | Brier trên giao 388 | Log loss trên giao 388 |
| --- | ---: | ---: | ---: | ---: |
| C2 | 388 / 95 | 263 | 0,2559820151274865 | 0,7078615982760118 |
| A_tp_pool | 598 / 355 | 53 | 0,2536196029464497 | 0,702105267513154 |

Artifact giữ tám nhóm fold/mã, IDs giao/missing, support và loss đầy đủ.
A có cả Brier/log loss cao hơn C2 tại MWG 2021, MWG 2022 và VCB 2022; không
đổi cấu hình theo loss tổng hoặc nhóm thuận lợi. Nhãn LONG ròng có 254 chu kỳ
lãi, mean **0,0254886434693516**, và 397 chu kỳ lỗ, mean
**−0,02512957748148189**; zero=0, đơn vị fraction, đã tính phí/trượt giá hai
chiều. Đây là mô tả nhãn lịch sử, không là expected-return policy hoặc
calibration xác suất LLM. B giữ posterior C2, không có gain số học độc lập.

**Gate kỹ thuật:** compileall, **885 unit**, E2E và **167 leakage PASS**,
không skip. Log mới tại
[compileall](validation_gates/development_lock_v1/compileall.log),
[unit](validation_gates/development_lock_v1/unit.log),
[E2E](validation_gates/development_lock_v1/e2e.log),
[leakage](validation_gates/development_lock_v1/leakage.log).
Đây là lượt chạy mới theo yêu cầu W8-03, không dùng receipt W8-02 thay kết quả.

Receipt [technical_gates.json](validation_gates/development_lock_v1/technical_gates.json)
bind 68 file code/schema/config và runtime, đã qua `read_technical_gates`;
SHA-256 byte
`bc33ec1ae43e6d220255ff7d089ee51d60f40bdf4bbdf6f09a04cd6ef58227d8`.
218 Python giữ nguyên byte trong suốt lượt gate; 776 file đã bảo vệ, gồm
nguồn/bằng chứng W7, ledger, README W7/W9, AGENTS/root README và receipt
W8-02, nguyên byte. QA diff/liên kết/checklist/hash PASS; đặc tả phương pháp,
development/repeat và protocol W9 giữ nguyên. **W8 đạt 3/8**, tiếp theo
**W8-04** do người dùng preflight/run/resume primary và repeat theo hướng dẫn.
A/B thực vẫn **NOT_RUN**, giữ C2 NOT_PROMOTED/Original/risk OFF; chưa selection
W8, manifest hoặc outcome holdout. Gate W8 chưa mở.

### W8-04 — Reset và sửa phục hồi vận hành, 17/10/2026

Mục này ghi nhận trạng thái tại mốc reset 17/10/2026; kết quả nghiệm thu
primary sau lượt chạy thật được cập nhật riêng bên dưới.

Theo yêu cầu người dùng, đã **xóa toàn bộ 786 file development cũ**, gồm
plan/run, point, slot, journal, manifest và response/checkpoint đã chạy;
không lưu bản sao hoặc tái sử dụng Decision/upstream cũ. Namespace repeat
cũ không tồn tại. Nguồn và bằng chứng W7, diagnostics train đã khóa và ledger
tài khoản chung được giữ nguyên. Xóa output không đặt lại quota phía provider.
Tại mốc reset, revision mới bắt đầu **0/660 primary, 0/432 repeat**, chưa có
API, selection hoặc holdout; lúc đó W8-04 chưa DONE và W8 đạt **3/8**.

Đây là amendment vận hành theo yêu cầu sau khi đã chạy một phần development:
`improvement_protocol_v2`, `improvement_cohort_plan_v2`,
`improvement_run_identity_v2`, retry `resilient_invocation_v1`. Kết quả mới
vẫn là exploratory, không thay bản đã khóa hoặc chọn giữ điểm cũ thuận lợi.
Chỉ đổi cách chờ/retry/phục hồi; giữ A/B/C2, lịch 60 điểm, ma trận 11 nhánh,
mẫu repeat/ba lượt/duplicate, model/schema/options, retrieval, prompt/token,
PIT, T+2.5, risk OFF và nomination. Receipt cũ không thay cho gate code mới.

Lỗi kết nối/timeout, HTTP 408/425/500/502/503/504 được tự thử lại cùng UUID/body,
backoff 2–60 giây; TPM/RPM chờ theo retry-after rồi tiếp tục. Không còn dừng
do trần ba HTTP hoặc 120 giây chờ của revision cũ. Từng HTTP thực vẫn lưu
audit/usage riêng; retry không tăng repeat_id. Nếu request trước chưa rõ kết
quả và chưa có response durable, revision này cho phép gửi lại tự động theo
ủy quyền mới của người dùng; provider có thể đã xử lý/ghi quota request trước.
Mạng mất kéo dài sẽ tiếp tục chờ; có thể dùng Ctrl+C để dừng và giữ checkpoint.

HTTP 200 được lưu response/hash vào `run/http_cache/` trước khi trả về SDK.
Sau gián đoạn, dùng response đúng UUID/body đã lưu, hoàn tất checkpoint còn
thiếu và bỏ qua node/Decision complete. Không tự gọi lại upstream complete
cho nhánh so sánh. Mất/sai cache đã xác nhận, sai nguồn/checkpoint/schema,
key không hợp lệ hoặc cấu hình lỗi vẫn phải dừng; lỗi toàn vẹn không được
biến thành retry vô hạn hay kết quả giả.

Hết quota ngày do provider báo thì dừng giữ checkpoint. Đổi `GROQ_API_KEY`
trong `.env` rồi chạy lại cùng lệnh; CLI tự kiểm preflight theo key/plan và
tiếp tục, không cần authorize từng UUID. Key mới cùng tài khoản/tổ chức có
thể vẫn chung quota. Nếu quota dừng ngay preflight trước khi tạo cohort,
`--run --resume` cũng tự khởi tạo run mới sau khi preflight PASS.

Plan mới được prepare/dry-run offline, bind **51 nguồn và 69 code/schema/config**;
SHA-256 byte
`f9745d946d81cb008e0a747f8367fe0c85a5fbd989e7148bde997227d651831e`.
Protocol canonical SHA-256
`62050a5b3e895b842fb4693bb87780652c59365184009b9fa78cbbd6750a067c`.
Đối chiếu protocol cũ xác nhận chỉ version/retry/recovery đổi; 773 file đã
bảo vệ nguyên byte, gồm nguồn/bằng chứng W7, ledger, AGENTS/root README và
receipt lịch sử. Diagnostics revision mới đặt riêng tại
`outputs/bayesian_benchmark/improvement_v1/train/diagnostics_resilient_v1.json`,
không ghi đè `diagnostics.json` của W8-03; SHA-256 byte
`c32993c726888f2fee3f9650f307db9afcb67145b4af40242bb49659bdbb23c9`.
Producer và verifier toàn artifact từ nguồn đều **PASS offline**, 852 replay/
651 query, Decision=0. So với report W8-03 chỉ đổi `code_sha256` và
`protocol_sha256`; posterior, coverage, loss, fold/mã và mọi dữ liệu còn lại
giữ nguyên.

**Bốn gate mới PASS:** compileall, **896 unit**, E2E và **167 leakage**,
không skip; gồm 10 test HTTP mock phục hồi và một test tích hợp resume mới.
Receipt [technical_gates.json](validation_gates/resilient_restart_v1/technical_gates.json)
bind 69 code/schema/config và runtime, đã qua consumer `read_technical_gates`;
SHA-256 byte
`1537a3986f9d24547f226e8c2ffeb98d4d43ac0583a83d719a053326d674638c`.
Log [compileall](validation_gates/resilient_restart_v1/compileall.log),
[unit](validation_gates/resilient_restart_v1/unit.log),
[E2E](validation_gates/resilient_restart_v1/e2e.log),
[leakage](validation_gates/resilient_restart_v1/leakage.log) giữ nguyên byte.
220 Python nguyên byte trong suốt lượt gate; QA cuối kiểm đủ 773 file bảo vệ,
plan/protocol/gate, diagnostics, liên kết và namespace mới sạch đều PASS.
Ở mốc sửa phục hồi 17/10, agent không gọi API thật hoặc tạo điểm chạy giả;
người dùng tiếp tục chạy W8-04 bằng CLI đã khóa.

### W8-04 — Nghiệm thu primary development, 19/10/2026

**DONE.** Người dùng đã chạy đủ **660/660 Decision trên 60/60 điểm**, 11
nhánh/điểm; FPT 12 điểm/132 Decision, MWG/VCB/VNM mỗi mã 16 điểm/176 Decision.
Không còn planned/unknown. Mỗi slot có đúng một attempt khoa học complete,
không có authorization replay thủ công. Bốn stage indicator/pattern/trend/full
đều complete 60/60, mỗi stage/điểm có một attempt; các nhánh dùng chung
upstream theo paired protocol. Decision cuối lưu lúc **15:09:07, 19/10/2026**
(Asia/Saigon).

`scripts/run_improvement.py --verify-report` đã **PASS offline**: tái dựng
nguồn/PIT, shared/evidence/request/prompt, hợp đồng HTTP/schema/model/options,
raw response và toàn bộ report từ checkpoint; không gọi API mới. Report
`outputs/bayesian_benchmark/improvement_v1/development/run/report.json`
giữ `primary_status=COMPLETE`, `selection_evidence_status=DEVELOPMENT`;
gắn 52 nguồn, 69 file code/schema/config và 1.452 mục checkpoint/HTTP audit.
SHA-256 byte report:
`80f707e0f4ee62c384724085249f748e2e82cf6517ccf892ccb97b1603317314`.
Run signature:
`9e23b5896fc4ee129c6f9d9b7018a1703987958745bfbdcddb7737a2dfeb544a`.

Prompt tối đa **4.671** ký tự, BRPP tối đa **494**, giữ trần <6.500/≤600.
Ledger của run giữ 780 HTTP 200, 4 transport_error, 15 HTTP 429 và 1 HTTP 523;
các lỗi lịch sử còn nguyên audit, mọi slot cuối cùng đều complete. HTTP retry
được ghi nhận là phục hồi kỹ thuật trong cùng attempt khoa học.

**Bàn giao W8-05:** producer `--prepare-repeat` đã PASS offline và tạo
`outputs/bayesian_benchmark/improvement_v1/repeats/plan.json`; SHA-256 byte
`bb429128c4f13297635778cf044d5a3a89639d4a7b1e6d2c2e507fba190d9b1b`.
Plan nối đúng primary signature/report, giữ mẫu 12 điểm đã đăng ký, ba điểm/mã,
4 S/4 E_ONLY/4 OFF, ba lượt 1/2/3 và 12 nhánh gồm `original_duplicate`:
**432 Decision repeat**, tách khỏi primary. Tại mốc bàn giao 19/10 chưa tạo
run repeat hoặc gọi API repeat. Kết quả nghiệm thu và phân tích sau lượt chạy
thật ngày 20/10 được ghi tại mục W8-05 bên dưới.

QA cuối kiểm toàn bộ 660 slot, shared/journal, 1.452 binding checkpoint/HTTP,
hash nguồn/code, plan repeat, checklist/liên kết và **1.994 file bảo vệ nguyên
byte** đều PASS; report primary, ledger, bằng chứng W7 và gate cũ giữ nguyên.

Không chạy lại compileall/unit/E2E/leakage: task không đổi code/test/schema,
runtime, cấu hình hoặc nguồn nghiên cứu; chỉ nghiệm thu report, chuẩn bị plan
repeat bằng producer đã khóa và cập nhật hai Markdown. Receipt bốn gate
`resilient_restart_v1` (896 unit/167 leakage, compileall/E2E PASS) được consumer
kiểm đúng code/runtime hiện tại, không ghi nhận là đã chạy lại. Phân tích hiệu
quả/độ ổn định thuộc W8-05; selection W8-06 chưa tạo, holdout W9 chưa mở.
Giữ C2 NOT_PROMOTED/Original là trạng thái đã khóa từ W7, risk OFF.

### W8-05 — Nghiệm thu repeat và phân tích development, 20/10/2026

**DONE.** Đủ **432/432 Decision repeat**, 144 mỗi lượt 1/2/3, 36 block
point/lượt trên mẫu cố định 12 điểm × 12 nhánh; không planned/unknown. Decision
cuối lưu lúc **11:47:14, 20/10/2026** (Asia/Saigon). CLI `--verify-report`
repeat đã **PASS offline**, gồm tái kiểm primary 660 Decision, nguồn/PIT,
shared/request/model/schema/options, raw response và report repeat. Report
`outputs/bayesian_benchmark/improvement_v1/repeats/run/report.json` có
`status=COMPLETE`, `in_primary=false`, gắn 896 mục checkpoint/HTTP audit;
SHA-256 byte:
`db08fbb381d3837614b0cf6f00e6078c179d13f4a01d49fafb818562cf5cf9e2`.
Run signature:
`f248864ee3366d1e8728331b7a7488702110c907f4df4a108e2dc72adf2c4437`.

432 request repeat khớp prompt UTF-8, hash body canonical và contract primary;
`original_duplicate` khớp Original. Mỗi slot có một attempt khoa học complete;
repeat dùng shared primary, không có thư mục points/responses hoặc gọi upstream
mới. Ledger repeat giữ 432 HTTP 200, 4 HTTP 429 và 2 transport_error.
Primary report giữ nguyên SHA-256 đã nghiệm thu ở W8-04. QA đối chiếu lại tài
khoản từ action/return đã seal, coverage, cặp action và contrast với report;
**2.862 file bảo vệ nguyên byte**, ledger và bằng chứng W7 giữ nguyên.

**Primary 60 điểm.** Bảng dưới là ΔR và ΔMDD so Original, đơn vị điểm phần
trăm; D là mean đều ΔR của bốn tài khoản độc lập, không phải return portfolio.
Làm tròn ba chữ số chỉ để hiển thị; report giữ số gốc. Return Original lần
lượt FPT/MWG/VCB/VNM là 1,308% / 1,917% / 1,328% / 0,147%. MDD Original là
5,124% / 2,694% / 4,022% / 3,053%; LONG 17/60, SHORT giữ CASH.

| Nhánh | ΔR FPT | ΔR MWG | ΔR VCB | ΔR VNM | D | Mean ΔMDD | LONG/60 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| original | +0.000 | +0.000 | +0.000 | +0.000 | +0.000 | +0.000 | 17 |
| bayesian | +0.000 | +7.931 | +0.000 | -0.771 | +1.790 | +0.515 | 19 |
| C2 | -2.042 | +0.000 | -2.842 | +3.153 | -0.433 | -0.763 | 13 |
| A_tp_pool | +0.000 | +9.433 | +1.039 | +1.791 | +3.066 | -0.679 | 16 |
| B_semantic | +0.000 | +9.433 | -2.842 | -0.771 | +1.455 | +0.187 | 17 |
| C2_stats_only | +0.000 | +0.000 | +0.000 | +1.791 | +0.448 | -0.433 | 16 |
| C2_examples_only | +0.000 | +1.771 | -2.842 | +1.791 | +0.180 | -0.433 | 16 |
| A_tp_pool_stats_only | +0.000 | +1.771 | +0.000 | +1.791 | +0.891 | -0.433 | 17 |
| A_tp_pool_examples_only | -2.042 | +11.368 | +0.000 | +1.791 | +2.779 | -0.433 | 17 |
| B_semantic_stats_only | -0.374 | +11.368 | +0.000 | +1.791 | +3.196 | -0.433 | 19 |
| B_semantic_examples_only | +0.000 | +11.368 | -2.842 | +0.000 | +2.132 | +0.000 | 18 |

A có ΔR dương tại MWG/VCB/VNM, FPT bằng 0; mean ΔMDD −0,679, max ΔMDD 0.
B chịu ΔR âm ở VCB/VNM và mean ΔMDD +0,187; C2 có D âm. Báo cả sáu ablation;
chúng không thuộc tập nomination C2/A/B, kể cả khi D của ablation cao hơn full.

**Coverage và ablation.** Stats/examples/both đếm điểm có readiness tương ứng;
visible đếm Decision thấy ít nhất một block. F/M/V/N là FPT/MWG/VCB/VNM.

| Base | Stats/60 | Examples/60 | Both/60 | Visible/60 | Off/60 | Visible F/M/V/N |
| --- | --- | --- | --- | --- | --- | --- |
| C2 | 11 | 26 | 8 | 29 | 31 | 5 / 7 / 8 / 9 |
| A_tp_pool | 34 | 26 | 24 | 36 | 24 | 7 / 10 / 9 / 10 |
| B_semantic | 11 | 26 | 8 | 29 | 31 | 5 / 7 / 8 / 9 |

A tăng stats ready 11→34 và both ready 8→24; examples giữ 26. Visible chỉ
tăng 29→36 vì nhiều điểm đã có examples. Đây là coverage của evidence, không
là xác suất LLM hiệu chuẩn hoặc bằng chứng model đã làm theo prior.
G là đủ 60 điểm; T là tập stats và examples cùng ready của từng base. Mỗi
tài khoản nhóm dựng lại từ vốn đầu; T của các base khác nhau, không so chúng
như cùng mẫu. Bảng giữ cả nhóm bất lợi và số điểm theo mã.

| Full−ablation | G: mean ΔR | T: n F/M/V/N | T: ΔR F/M/V/N |
| --- | --- | --- | --- |
| C2−stats | -0.881 | 1 / 2 / 2 / 3 | +0.000 / +0.000 / +0.000 / +0.000 |
| C2−examples | -0.613 | 1 / 2 / 2 / 3 | +0.000 / -1.722 / +0.000 / +0.000 |
| A_tp_pool−stats | +2.175 | 4 / 7 / 6 / 7 | +0.000 / -1.722 / +1.015 / +0.000 |
| A_tp_pool−examples | +0.286 | 4 / 7 / 6 / 7 | +0.000 / -1.722 / +1.015 / +0.000 |
| B_semantic−stats | -1.741 | 1 / 2 / 2 / 3 | +0.000 / -1.722 / +0.000 / +0.000 |
| B_semantic−examples | -0.677 | 1 / 2 / 2 / 3 | +0.000 / -1.722 / +0.000 / +0.000 |

Trên T, A full−stats và full−examples cùng có mean đều bốn mã **−0,177**;
gain G không được quy riêng cho stats/examples ngoài common support. C2/B
full−examples trên T đều âm tại MWG, ba mã còn lại bằng 0.

**Nhóm thời gian và leave-one-symbol-out.** Các ô Q/H là mean đều ΔR của
bốn tài khoản nhóm so Original, không ghép return các nhóm. LOSO giữ nguyên
nhánh rồi bỏ một mã, không chọn lại ứng viên.

| Base | Q1 | Q2 | Q3 | Q4 | H1 | H2 | LOSO bỏ F/M/V/N |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C2 | — | -0.510 | +0.000 | -0.722 | +0.253 | -0.722 | +0.104 / -0.577 / +0.370 / -1.628 |
| A_tp_pool | — | +0.000 | +2.314 | +0.000 | +0.686 | +2.325 | +4.088 / +0.943 / +3.741 / +3.491 |
| B_semantic | — | -0.628 | +2.314 | -0.722 | -0.187 | +1.603 | +1.940 / -1.204 / +2.887 / +2.197 |

Q1 mean giữ null vì FPT không có điểm; ΔR Q1 theo F/M/V/N là C2:
null/0/0/+3,053; A: null/0/+0,984/+1,734; B: null/0/0/+1,734. A tập trung
gain tại MWG trong Q3/H2; khi bỏ MWG, D còn +0,943. B chuyển âm khi bỏ MWG.
Không dùng subgroup thuận lợi để đổi primary hoặc cấu hình.

**Prior-off và giới hạn attribution.** Ô là số action bất đồng/số cặp so
Original trên điểm không có block prior visible. Bayesian có 0/0 (null).

| Nhánh−Original | Primary | Repeat 1 | Repeat 2 | Repeat 3 |
| --- | --- | --- | --- | --- |
| bayesian | 0/0 (null) | 0/0 (null) | 0/0 (null) | 0/0 (null) |
| C2 | 2/31 | 0/4 | 0/4 | 0/4 |
| A_tp_pool | 2/24 | 0/4 | 0/4 | 0/4 |
| B_semantic | 2/31 | 0/4 | 0/4 | 0/4 |
| C2_stats_only | 1/49 | 0/8 | 0/8 | 0/8 |
| C2_examples_only | 1/34 | 0/5 | 0/5 | 0/5 |
| A_tp_pool_stats_only | 1/26 | 0/5 | 0/5 | 1/5 |
| A_tp_pool_examples_only | 3/34 | 0/5 | 0/5 | 0/5 |
| B_semantic_stats_only | 3/49 | 1/8 | 0/8 | 1/8 |
| B_semantic_examples_only | 1/34 | 0/5 | 0/5 | 0/5 |

Primary có **16/312 cặp prior-off bất đồng** dù prompt trùng byte UTF-8 và
contract/hash body canonical trùng Original; không khẳng định byte HTTP wire
khi chưa lưu request thô. Khi cả hai prior cùng off, A−C2 bất đồng 2/24,
B−C2 2/31. Các cặp dùng chung point/Original nên không là quan sát độc lập.

Trong ba điểm A khác Original, MWG-2023-07-05 (LONG thay CASH) và
VNM-2023-03-30 (CASH thay LONG) đều prior-off; chỉ VCB-2023-02-08 (CASH
thay LONG) có prior visible. Vì thế không quy toàn bộ D +3,066 cho Bayesian
prior. B cũng có hai thay đổi prior-off và hai thay đổi prior-on; hai thay
đổi prior-on bỏ một LONG có lãi tại VCB-2023-10-30 và thêm một LONG lỗ tại
VNM-2023-06-30. Kết quả thuận lợi/bất lợi đều giữ trong report cases.

**Độ ổn định trên 12 điểm repeat.** Mỗi request có 36 cặp lượt (1,2)/(1,3)/
(2,3), 12 cặp trong mỗi stratum S/E_ONLY/OFF đã chọn từ readiness W7; không
đổi strata theo A/B mới. Đây là các cặp phụ thuộc, không tính như 36 mẫu độc lập.

| Nhánh | Cặp lượt/36 | S/12 | E_ONLY/12 | OFF/12 |
| --- | --- | --- | --- | --- |
| original | 4/36 | 2/12 | 2/12 | 0/12 |
| bayesian | 0/36 | 0/12 | 0/12 | 0/12 |
| C2 | 2/36 | 2/12 | 0/12 | 0/12 |
| A_tp_pool | 0/36 | 0/12 | 0/12 | 0/12 |
| B_semantic | 2/36 | 0/12 | 2/12 | 0/12 |
| C2_stats_only | 6/36 | 4/12 | 2/12 | 0/12 |
| C2_examples_only | 0/36 | 0/12 | 0/12 | 0/12 |
| A_tp_pool_stats_only | 0/36 | 0/12 | 0/12 | 0/12 |
| A_tp_pool_examples_only | 0/36 | 0/12 | 0/12 | 0/12 |
| B_semantic_stats_only | 2/36 | 0/12 | 2/12 | 0/12 |
| B_semantic_examples_only | 0/36 | 0/12 | 0/12 | 0/12 |
| original_duplicate | 0/36 | 0/12 | 0/12 | 0/12 |

Original−duplicate cùng lượt bất đồng **0/12, 0/12, 2/12**; tổng 2/36.
Hai cặp ở lượt 3: MWG-2023-06-30 (S, CASH/LONG) và VCB-2023-08-29
(E_ONLY, LONG/CASH). A giữ action qua ba lượt (0/36); C2_stats_only có 6/36.
Quan sát biến thiên ngay ở request giống nhau giới hạn diễn giải attribution;
không suy nguyên nhân từ model fingerprint, thời điểm hoặc key.

**Contrast repeat.** Mỗi lượt dựng lại bốn tài khoản ba điểm/mã từ vốn đầu;
các ô là mean ΔR bốn mã, cột cuối mean ba lượt. Mẫu 12 điểm và repeat giữ
riêng, không nhập vào D primary, không chọn lượt tốt nhất.

| Cặp | Lượt 1 | Lượt 2 | Lượt 3 | Mean 3 lượt |
| --- | --- | --- | --- | --- |
| bayesian−original | -0.620 | -0.620 | -1.127 | -0.789 |
| C2−original | -0.299 | -0.620 | -0.806 | -0.575 |
| A_tp_pool−original | +0.000 | +0.000 | -0.507 | -0.169 |
| B_semantic−original | -0.620 | -0.620 | -0.507 | -0.582 |
| C2_stats_only−original | +0.562 | +0.330 | -0.233 | +0.220 |
| C2_examples_only−original | +0.000 | +0.000 | -0.507 | -0.169 |
| A_tp_pool_stats_only−original | +0.000 | +0.000 | -0.507 | -0.169 |
| A_tp_pool_examples_only−original | +0.000 | +0.000 | -0.507 | -0.169 |
| B_semantic_stats_only−original | +0.274 | +0.000 | -0.507 | -0.078 |
| B_semantic_examples_only−original | +0.000 | +0.000 | -0.507 | -0.169 |
| A_tp_pool−C2 | +0.299 | +0.620 | +0.299 | +0.406 |
| B_semantic−C2 | -0.321 | +0.000 | +0.299 | -0.008 |
| C2−C2_stats_only | -0.861 | -0.950 | -0.573 | -0.795 |
| C2−C2_examples_only | -0.299 | -0.620 | -0.299 | -0.406 |
| A_tp_pool−A_tp_pool_stats_only | +0.000 | +0.000 | +0.000 | +0.000 |
| A_tp_pool−A_tp_pool_examples_only | +0.000 | +0.000 | +0.000 | +0.000 |
| B_semantic−B_semantic_stats_only | -0.894 | -0.620 | +0.000 | -0.505 |
| B_semantic−B_semantic_examples_only | -0.620 | -0.620 | +0.000 | -0.413 |

A−C2 dương cả ba lượt, mean +0,406; B−C2 đổi dấu, mean −0,008. Tuy vậy
A−Original mean −0,169 và A full−stats/full−examples đều 0 cả ba lượt.
Repeat chưa chứng minh A vượt Original hoặc tách được hiệu ứng thành phần.
Không đặt thêm ngưỡng thắng cho trace, chạy lượt thứ tư hoặc tune A/B.

Diagnostics train đã verify ở W8-03/revision phục hồi vẫn giữ nguyên: giao
388/651 query, Brier C2/A là 0,255982/0,253620, log loss 0,707862/0,702105;
A vẫn bất lợi tại MWG 2021/2022 và VCB 2022. Đây là xác suất sự kiện lịch sử,
không là calibration LLM hoặc mô hình expected return.

**Bàn giao W8-06.** Đủ primary/repeat và phân tích đã khóa; còn chạy selector
theo rule/eligibility cố định và ghi lý do. Chưa tạo selection W8, chưa mở
holdout hoặc CI xác nhận; giữ Original triển khai/C2 NOT_PROMOTED từ W7,
risk OFF. Không thay phương pháp/registry/schema/model/token/kinh tế/PIT.
Task chỉ phân tích bằng chứng và sửa hai Markdown, không chạy lại compileall,
unit, E2E hoặc leakage suite theo AGENTS.md 1.2. Verifier mới và QA số liệu/
hash/link PASS; receipt 896 unit/167 leakage cùng code/runtime được consumer
kiểm, không ghi là đã chạy lại. W8 đạt **5/8 DONE**, tiếp theo **W8-06**.

#### Lệnh vận hành primary và bàn giao repeat

Chạy từ root repository bằng Python 3.13.5. Các đường dẫn dưới đây dành cho
revision này; giữ nguyên file plan, receipt, code/runtime và ledger chung khi
resume. `.env` chứa `GROQ_API_KEY` do người dùng quản lý và được ưu tiên hơn
biến môi trường. **Người dùng tự chạy API; agent chỉ chạy các chế độ offline.**

```powershell
$taskPlan = "outputs/bayesian_benchmark/improvement_v1/development/plan.json"
$taskRun = "outputs/bayesian_benchmark/improvement_v1/development/run"
$taskGates = "docs/plan/week8/validation_gates/resilient_restart_v1/technical_gates.json"
$taskLedger = "outputs/oos_pilot/api_usage.json"
$taskRepeatPlan = "outputs/bayesian_benchmark/improvement_v1/repeats/plan.json"
$taskRepeatRun = "outputs/bayesian_benchmark/improvement_v1/repeats/run"

# Offline: dựng lại binding nguồn/PIT, không đọc key hoặc gọi mạng.
py -3.13 -X utf8 scripts/run_improvement.py --dry-run --plan $taskPlan

# API: tự preflight khi cần; primary 60 điểm, 11 nhánh, upstream một lần/điểm.
py -3.13 -X utf8 scripts/run_improvement.py --run --plan $taskPlan --output-dir $taskRun --technical-gates $taskGates --ledger $taskLedger

# API: sau quota, đổi key trong .env rồi chạy lệnh này; tự resume cả unknown.
# Có thể dùng lại nguyên lệnh --run phía trên; CLI tự nhận output đã khởi tạo.
py -3.13 -X utf8 scripts/run_improvement.py --run --resume --plan $taskPlan --output-dir $taskRun --technical-gates $taskGates --ledger $taskLedger

# Offline: kiểm checkpoint, raw response, request/body audit và report.
py -3.13 -X utf8 scripts/run_improvement.py --verify-only --plan $taskPlan --output-dir $taskRun --technical-gates $taskGates --ledger $taskLedger
py -3.13 -X utf8 scripts/run_improvement.py --verify-report --plan $taskPlan --output-dir $taskRun --technical-gates $taskGates --ledger $taskLedger

# Offline: chuẩn bị khi chưa có plan repeat, sau primary COMPLETE và report hợp lệ.
py -3.13 -X utf8 scripts/run_improvement.py --prepare-repeat --plan $taskPlan --output-dir $taskRun --repeat-plan $taskRepeatPlan --technical-gates $taskGates --ledger $taskLedger

# API: người dùng chạy ba lượt bổ sung, mỗi lượt 12 điểm x 12 nhánh;
# dùng nguyên shared/request primary, không gọi lại upstream.
py -3.13 -X utf8 scripts/run_improvement.py --run --plan $taskRepeatPlan --output-dir $taskRepeatRun --technical-gates $taskGates --ledger $taskLedger

# API: tiếp tục repeat bị ngắt; không mở lượt khoa học thứ tư.
py -3.13 -X utf8 scripts/run_improvement.py --run --resume --plan $taskRepeatPlan --output-dir $taskRepeatRun --technical-gates $taskGates --ledger $taskLedger

# Offline: nghiệm thu repeat trước phân tích W8-05/selection W8-06.
py -3.13 -X utf8 scripts/run_improvement.py --verify-report --plan $taskRepeatPlan --output-dir $taskRepeatRun --technical-gates $taskGates --ledger $taskLedger
```

`--verify-only` có thể trả report INCOMPLETE hợp lệ. W8-04 nghiệm thu primary
khi đủ 660 Decision complete, không pending/unknown và report qua verifier.
W8-05 cần thêm đủ 432 Decision repeat complete cùng phân tích; thiếu repeat
vẫn chặn nghiệm thu W8-05 và selection W8-06, không giảm yêu cầu protocol.
Khi bị ngắt, giữ cả checkpoint/journal/ledger/http_cache
và chạy lại `--run --resume`; revision mới tự xử lý unknown theo policy đã
khóa, không cần reconcile/authorize UUID thủ công. Không xóa lock của tiến
trình còn sống, slot hoặc ledger. Thay key tự kích hoạt preflight theo
credential scope; preflight/retry/format repair không tăng repeat_id.

Nếu clone chưa có artifact local, chuẩn bị lại plan từ parent W7 đã khóa bằng
lệnh dưới; producer chỉ chấp nhận đúng nguồn/code/runtime và không ghi đè
artifact khác nội dung. Diagnostics train có producer/verifier riêng, không
cần key. Cả hai output nằm ngoài Git; hash nghiệm thu được ghi tại mục này.

```powershell
py -3.13 -X utf8 scripts/run_improvement.py --prepare --parent outputs/bayesian_benchmark/development_candidate_plan_v2.json --plan $taskPlan
py -3.13 -X utf8 scripts/run_improvement.py --train --train-report outputs/bayesian_benchmark/improvement_v1/train/diagnostics_resilient_v1.json
py -3.13 -X utf8 scripts/run_improvement.py --verify-train --train-report outputs/bayesian_benchmark/improvement_v1/train/diagnostics_resilient_v1.json
```

### W8-06 — Khóa selection development, 20/10/2026

**DONE.** Producer CLI `--select` đã **PASS offline**, tái dựng primary
660/660 Decision và repeat 432/432 Decision cùng nguồn/PIT/shared/request/HTTP
audit và report. Consumer production `read_selection` đã đọc lại artifact,
tái tính expected bằng `selection_artifact` trên report/gate vừa được verify
và so toàn bộ nội dung **PASS**.
Đối chiếu số học độc lập từ metric tài khoản, common support và visibility
khớp toàn bộ eligibility, ΔR/ΔMDD, promotion, ranking và lý do của ba ứng viên.
Không gọi API mới; repeat chỉ là điều kiện nghiệm thu và chẩn đoán, không
tham gia D/ranking primary.

**Quyết định đã khóa:** `research_candidate=A_tp_pool`,
`nomination_status=PROMOTED`, `deployment_choice=A_tp_pool`,
`selection_evidence_status=DEVELOPMENT`, `risk_policy=OFF`.
PROMOTED là đạt quy tắc đề cử development đã đăng ký, chưa phải bằng chứng
xác nhận holdout hoặc thay cấu hình mặc định của ứng dụng. Selection W7
vẫn giữ C2 NOT_PROMOTED/Original nguyên byte; lựa chọn W8 là artifact riêng.

Đơn vị các Δ là điểm phần trăm; số dưới đây làm tròn sáu chữ số để hiển thị,
selector dùng số gốc. D là mean đều bốn tài khoản, không là return portfolio.

| Full-prior | D | Mean ΔMDD | Max ΔMDD | ΔR>0 | Visible | Eligible | Promotable |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C2 | -0.432833 | -0.763146 | +0.000000 | 1/4 | 29/60 | Có | Không |
| A_tp_pool | +3.065755 | -0.679482 | +0.000000 | 3/4 | 36/60 | Có | Có |
| B_semantic | +1.454881 | +0.186613 | +0.746453 | 1/4 | 29/60 | Có | Không |

Cả ba đủ 60 paired points (FPT/MWG/VCB/VNM: 12/16/16/16), metric hữu hạn,
bốn gate kỹ thuật PASS đúng code/runtime; visible đều ≥6 và ít nhất một
điểm mỗi mã. Visible theo FPT/MWG/VCB/VNM của C2/B là 5/7/8/9, A là 7/10/9/10.
A đạt đủ D>0, ΔR>0 ở ≥3/4 mã, mean ΔMDD≤2 và max ΔMDD≤5. ΔR của A theo
bốn mã là +0,000000 / +9,433012 / +1,039182 / +1,790826; FPT bằng 0 không
được tính là mã cải thiện. C2 không đạt `POSITIVE_MEAN_RETURN` và
`POSITIVE_AT_LEAST_3_SYMBOLS`; B không đạt `POSITIVE_AT_LEAST_3_SYMBOLS`.

Giữ nguyên ngưỡng W6-04; `improvement_nomination_rules_v1` chỉ đổi version
và tập ứng viên sang C2/A/B. Tập eligible xếp `A_tp_pool, B_semantic, C2`;
tập promotable chỉ có `A_tp_pool`, được ưu tiên khi chọn. Tie xét trong
1e−9 điểm phần trăm quanh D_max, rồi mean ΔMDD nhỏ hơn, rồi thứ tự cố định
C2/A/B; lần này không có tie. Không nới ngưỡng hoặc mở vòng tối ưu thứ hai.
Toàn bộ 11 nhánh đã thử và kết quả âm, gồm Original, Bayesian v1, ba full-prior
và sáu ablation, vẫn báo tại [W8-05](#w8-05--nghiệm-thu-repeat-và-phân-tích-development-20102026).
Sáu ablation không tham gia nomination, kể cả B_semantic_stats_only có D cao hơn A.

**Giới hạn được giữ cùng quyết định.** Development 2023 vẫn exploratory;
A−Original trên mẫu repeat có mean −0,169020 điểm phần trăm, A−C2 +0,405712,
và A full−stats/full−examples đều 0 trên ba lượt. Có 16/312 cặp prior-off
bất đồng dù cùng prompt/body canonical, cùng 2/36 cặp Original−duplicate
bất đồng. Hai điểm A khác Original khi prior-off, MWG-2023-07-05 và
VNM-2023-03-30, góp phần lớn vào gain primary. Vì vậy không quy toàn bộ
D của A cho prior hoặc gọi đó là hiệu ứng thành phần đã cô lập. Giữ đầy đủ
Q/H/LOSO, ablation T và loss train bất lợi tại W8-05; không dùng chẩn đoán
để sửa nomination, đổi mẫu, thêm lượt lặp hoặc chọn lại theo subgroup.

Artifact local bất biến:
[`development/run/selection.json`](../../../outputs/bayesian_benchmark/improvement_v1/development/run/selection.json),
schema `improvement_selection_v1`, namespace riêng khỏi W7. SHA-256 byte:
`cd46ad855ccda8f95a7694e21c34e08c993f6ea110ddc38bab9db4018857b387`.
Envelope tự kiểm hash payload; consumer tái dựng report và so toàn bộ selection,
không tin ranking/hash tự khai. Binding kế thừa primary run signature,
plan/protocol/registry/model/options/runtime, 52 nguồn, 69 code/schema/config,
1.452 mục checkpoint/HTTP audit, report canonical/file và receipt bốn gate.
Primary report giữ SHA-256
`80f707e0f4ee62c384724085249f748e2e82cf6517ccf892ccb97b1603317314`;
repeat report đã verify trước selection giữ SHA-256
`db08fbb381d3837614b0cf6f00e6078c179d13f4a01d49fafb818562cf5cf9e2`.
Selection không tự thêm binding repeat; CLI bắt buộc nối đúng primary plan/run
và verify repeat COMPLETE. Các hash ở đây ghi nhận cả điều kiện nghiệm thu đó.

Task này nghiệm thu bằng một lượt producer đầy đủ, consumer artifact và
oracle độc lập. Vòng CLI `--verify-selection` thứ hai đã chủ động dừng vì
lặp lại kiểm toán nguồn; không ghi là vòng đó PASS, không có lỗi integrity
hoặc gọi API. Hash của mọi bằng chứng có trước và selection vẫn giữ nguyên.

Tái lập toàn bộ từ root khi cần, không cần key hoặc gọi mạng; `--select` chỉ
tạo mới hoặc chấp nhận lại đúng nội dung, không ghi đè quyết định khác.
`--verify-selection` là đường CLI kiểm lại cả nguồn/report trước consumer:

```powershell
$selectionArgs = @(
  "--plan", "outputs/bayesian_benchmark/improvement_v1/development/plan.json",
  "--output-dir", "outputs/bayesian_benchmark/improvement_v1/development/run",
  "--repeat-plan", "outputs/bayesian_benchmark/improvement_v1/repeats/plan.json",
  "--repeat-dir", "outputs/bayesian_benchmark/improvement_v1/repeats/run",
  "--technical-gates", "docs/plan/week8/validation_gates/resilient_restart_v1/technical_gates.json",
  "--ledger", "outputs/oos_pilot/api_usage.json"
)
py -3.13 -X utf8 scripts/run_improvement.py --select @selectionArgs
if ($LASTEXITCODE -ne 0) { throw "Chưa khóa được selection; dừng trước holdout." }
py -3.13 -X utf8 scripts/run_improvement.py --verify-selection @selectionArgs
if ($LASTEXITCODE -ne 0) { throw "Selection chưa hợp lệ; dừng trước holdout." }
```

**Kiểm tra và bàn giao.** QA hash/nguồn/số liệu/checklist/liên kết và diff PASS;
2.862 file có trước được bảo vệ nguyên byte, gồm primary/repeat, W7, train,
code/runtime, gate/log và ledger. Chỉ thêm selection local cùng hai Markdown;
không đổi code/test/schema/cấu hình runtime hoặc dữ liệu đầu vào. Không chạy
lại compileall/unit/E2E/leakage theo AGENTS.md 1.2; consumer đã kiểm receipt
hiện hành 896 unit/167 leakage cùng compileall/E2E PASS đúng binding, không
ghi là đã chạy lại suite. Các hợp đồng kinh tế/PIT/paired/token giữ nguyên.

W8 đạt **6/8 DONE**, tiếp theo **W8-07**: ánh xạ selection A vào ma trận
`original, bayesian, C2, A_tp_pool, A_tp_pool_stats_only, A_tp_pool_examples_only`,
triển khai/kiểm consumer thống kê bằng fixture và khóa manifest 64 điểm.
Đây mới là đầu vào bàn giao; chưa tạo manifest/run hoặc đọc outcome holdout,
chưa mở Gate W8/W9. W8-08 còn nghiệm thu bốn gate và hướng dẫn vận hành.

### W8-07 — Khóa manifest và công cụ xác nhận holdout, 20/10/2026

**DONE.** Manifest `improvement_bound_holdout_v1` đã khóa đủ **64 điểm
2024, 16/mã**, lấy nguyên lịch W5; sáu nhánh, **384 Decision dự kiến**,
repeat_id=0. CLI mới `--prepare` và `--dry-run` **PASS offline**, kiểm
nguồn/PIT/scaler/warm-up/horizon và lịch không chồng lấn. Chưa tạo run,
Decision, P&L hoặc CI thật của holdout; không gọi API hoặc đọc key.

| Nhánh đã khóa | Vai trò |
| --- | --- |
| `original` | Đối chứng chính |
| `bayesian` | Bayesian v1 |
| `C2` | Đối chứng phương pháp |
| `A_tp_pool` | Primary kế thừa selection W8-06 |
| `A_tp_pool_stats_only` | Ablation chỉ thống kê của A |
| `A_tp_pool_examples_only` | Ablation chỉ ví dụ của A |

Giữ thứ tự trên, xoay trái j mod 6 theo lịch (cutoff, FPT/MWG/VCB/VNM),
không thêm B hoặc chọn lại sau outcome. Primary A−Original; bốn secondary
cố định là A−C2, A−Bayesian v1, A−A_stats_only và A−A_examples_only.
Manifest lưu đủ ID/ngày, thứ tự từng point, ma trận, contrast/m=4, protocol,
registry, index/scaler, model/options, nguồn, code/runtime và selection.

**Consumer mới, giữ nguyên 69 dependency development.** Thêm bốn file:

- `core/improvement_holdout.py`: producer/loader manifest, kiểm seal byte
  selection/primary/repeat đã nghiệm thu, mọi checkpoint/HTTP audit và
  nguồn/gate; tái tính eligibility/ranking từ report đã seal. Không coi hash
  tự khai là provenance và không replay prompt/API development đã nghiệm thu.
- `core/improvement_holdout_runtime.py`: journal/Decision/transport hiện có,
  upstream một lần/point và deep-copy, resume cùng slot/UUID. Report
  `improvement_holdout_report_v1` giữ G/S, missing/unknown, metric tài khoản,
  CASH reference, Q/H/regime/LOSO, prior-off, T cùng ready và case cho bootstrap;
  incomplete không được điền CASH hoặc nhận primary COMPLETE.
- `core/improvement_bootstrap.py`: producer/loader/verifier
  `improvement_bootstrap_v1`, tái dựng tài khoản theo thứ tự mẫu tổng hợp.
- `scripts/run_improvement_holdout.py`: CLI riêng, offline mặc định;
  online kiểm nguồn/code/runtime/bốn gate và receipt bàn giao trước đọc key.
  Không sửa CLI, checkpoint, report hoặc selection W7/development/repeat.

**Thống kê giữ đúng đặc tả trước outcome.** Bootstrap circular trên cụm
ngày cutoff duy nhất, cùng mẫu cho mọi mã/nhánh/contrast; block chính L=4,
độ nhạy L=2/8, PCG64(20261016), **10.000 draw mỗi L**. Giữ mọi mã hiện diện
trong cụm, không tạo point cho mã vắng hoặc sắp lại ngày gốc. Mỗi draw dựng
bốn tài khoản từ 50 triệu, dùng đúng phép tính cổ phiếu lẻ/toàn vốn, giá và
phí hai chiều của engine; không lấy mean cycle return thay return tài khoản.
Thiếu bất kỳ mã hoặc metric nhánh không hữu hạn thì draw INVALID, có lý do
và phân phối số cycle/mã, không sinh draw thay thế. Cần ≥9.500 draw hợp lệ;
thiếu thì CI BLOCKED/null. CI chính percentile 95%, `method=linear`;
secondary Bonferroni 98,75% với m=4. Độ nhạy không thay CI chính; CI chạm
hoặc qua 0 là inconclusive, không chứng minh tương đương hoặc chọn lại A/B.

**Fixture và kiểm thử.**
[`improvement_bootstrap_v1.json`](fixtures/improvement_bootstrap_v1.json)
giữ 12 point/ba cụm ngày đồng thời bốn mã, oracle tích net-return độc lập,
RNG theo từng draw và CI ba L. Kiểm tái dựng trên chính `compute_account_metrics`
với thứ tự tổng hợp/cycle lặp, LONG/CASH và cổ phiếu lẻ; kiểm dedup C2/m=3,
mẫu thiếu mã, biên 9.499/9.500, CI zero, nhãn giả, cycle vượt split và CI tự
băm lại. Fixture chỉ kiểm protocol, không là hiệu quả LLM/CI holdout thật.
**13 test mới PASS**, gồm bootstrap, manifest/runtime/CLI và một test leakage.
Ca tích hợp xác nhận sáu nhánh, một upstream, token/schema legacy, resume
complete không gọi thêm LLM, gián đoạn dùng lại UUID và sửa artifact bị chặn.

**Bốn gate mới PASS**, không skip: compileall, **909 unit**, E2E,
**168 leakage**. Receipt
[`technical_gates.json`](validation_gates/bound_holdout_v1/technical_gates.json)
bind **74 dependency/schema/fixture** (69 cũ + bốn module/CLI mới + fixture);
**227 file Python giữ nguyên byte trong lượt gate**. Consumer receipt PASS,
không dùng receipt 896 unit cũ thay cho code mới. SHA-256 byte receipt:
`1be5eb3490e2c31d1a04e5a38bf7ffa732ef22d4a891fdf5b9ba26a08292b012`.
Manifest local bất biến
[`holdout/plan.json`](../../../outputs/bayesian_benchmark/improvement_v1/holdout/plan.json),
SHA-256 byte:
`6b6760768fe98731e64e1e518ffbc351db29a41397f46bfad0d3a19d96956944`.
Selection vẫn `cd46ad855ccda8f95a7694e21c34e08c993f6ea110ddc38bab9db4018857b387`;
primary/repeat, ledger và **3.366 file có trước giữ nguyên byte**.
QA nguồn/hash/lịch/số liệu/liên kết/diff PASS; không đổi phương pháp/ngưỡng,
kinh tế/PIT/paired, BRPP≤600/prompt<6.500 hoặc risk OFF.

Các lệnh offline tái lập manifest và fixture từ root:

```powershell
py -3.13 -X utf8 scripts/run_improvement_holdout.py --prepare
py -3.13 -X utf8 scripts/run_improvement_holdout.py --dry-run
py -3.13 -X utf8 -m unittest discover -s tests -p "test_improvement_bootstrap.py" -v
py -3.13 -X utf8 -m unittest discover -s tests -p "test_improvement_holdout*.py" -v
```

**Bàn giao W8-08:** đối chiếu receipt/code/runtime/hash, hoàn thiện hướng dẫn
preflight/run/verify/resume W9 và tạo receipt `improvement_holdout_release_v1`
ở `holdout/release.json` sau nghiệm thu. CLI có sẵn `--release`, `--preflight`,
`--run --resume`, `--verify-only`, `--verify-report`, `--bootstrap` và
`--verify-bootstrap`; **chưa chạy release/preflight/API ở task này**.
Giữ ledger `outputs/oos_pilot/api_usage.json`; đổi key trong `.env` rồi dùng
lại `--run --resume` cùng plan/output/gate, không reset hoặc chạy lại điểm complete.
Chưa có release hợp lệ thì CLI chặn online trước đọc key, kể cả đã có manifest.
W8 đạt **7/8 DONE**, tiếp theo **W8-08**; Gate W8 và W9 chưa mở.

### W8-08 — Nghiệm thu và bàn giao holdout, 20/10/2026

**DONE — W8 hoàn tất 8/8, Gate W8 PASS.** Đã đối chiếu selection development,
manifest, nguồn, code/runtime và receipt bốn gate hiện hành. Producer
`--release` kiểm lại lịch/PIT/scaler của 64 điểm rồi khóa receipt bàn giao
`improvement_holdout_release_v1`; chưa preflight, gọi API, tạo run hoặc tính
P&L/CI holdout. W9 sẵn sàng bắt đầu W9-01, vẫn **0/6 task hoàn tất**.

Manifest giữ **64 điểm năm 2024, 16/mã, sáu nhánh và 384 Decision dự kiến**:
`original, bayesian, C2, A_tp_pool, A_tp_pool_stats_only,
A_tp_pool_examples_only`. Thứ tự xoay, một upstream/point, repeat_id=0,
primary A−Original và bốn secondary giữ đúng bản khóa W8-07. Không chọn lại
ứng viên, tune tham số hoặc thêm lượt lặp theo outcome holdout. A PROMOTED
chỉ là selection development; chưa kết luận hiệu quả xác nhận hay attribution.

**Bằng chứng nghiệm thu:** consumer kiểm receipt và byte/hash cả bốn log
**PASS**: compileall, **909 unit**, E2E, **168 leakage**, không skip; đây là
kết quả đã chạy ở W8-07 trên cùng 74 dependency/schema/fixture và runtime.
Không chạy lại suite/compileall ở W8-08 theo AGENTS.md mục 1.2 vì chỉ đổi ba
Markdown và tạo receipt từ producer hiện hữu; code/test/schema/runtime và
đầu vào giữ nguyên. QA đối chiếu nguồn/selection/report/checkpoint/HTTP audit,
69 dependency development, 64 ngày W5/thứ tự nhánh, chữ ký release, log/hash,
liên kết, cú pháp PowerShell và diff **PASS**. **3.380 file được bảo vệ
nguyên byte**, gồm plan, receipt/log gate và ledger; giữ toàn bộ các run cũ.

| Artifact local | SHA-256 byte |
| --- | --- |
| [Manifest](../../../outputs/bayesian_benchmark/improvement_v1/holdout/plan.json) | `6b6760768fe98731e64e1e518ffbc351db29a41397f46bfad0d3a19d96956944` |
| [Receipt bốn gate](validation_gates/bound_holdout_v1/technical_gates.json) | `1be5eb3490e2c31d1a04e5a38bf7ffa732ef22d4a891fdf5b9ba26a08292b012` |
| [Release bàn giao](../../../outputs/bayesian_benchmark/improvement_v1/holdout/release.json) | `b61ebdbf46f0d65b10e7fa8cdec207fa201a1e18eeee454679d512c8c3380f9e` |

Release bind cả SHA byte manifest, digest payload
`037b7e3088e1803e5e52261417e4313e996f41c8a28e0661d7acc5a02cbc09ff`,
SHA receipt gate, code/runtime và risk OFF. Plan/release/output là artifact
local trong thư mục ignored, cần giữ cùng workspace. Nếu di chuyển máy,
phải mang đủ nguồn/bằng chứng/cache và đúng runtime; chỉ checkout Git chưa
đủ. CLI kiểm nguồn/identity trước key; có sai khác thì dừng để đối soát.

**Lệnh W9 từ root repository (PowerShell).** Chạy khối khai báo này mỗi khi
mở terminal mới; các lệnh tiếp theo dùng chung đúng identity/path:

```powershell
$holdoutArgs = @(
    '--plan', 'outputs/bayesian_benchmark/improvement_v1/holdout/plan.json',
    '--output-dir', 'outputs/bayesian_benchmark/improvement_v1/holdout/run',
    '--technical-gates', 'docs/plan/week8/validation_gates/bound_holdout_v1/technical_gates.json',
    '--handoff', 'outputs/bayesian_benchmark/improvement_v1/holdout/release.json',
    '--ledger', 'outputs/oos_pilot/api_usage.json',
    '--env-file', '.env'
)
```

W9-01: người dùng đặt `GROQ_API_KEY` trong `.env`, chạy dry-run offline rồi
preflight thật. Chỉ chuyển sang run khi lệnh trước kết thúc thành công:

```powershell
py -3.13 -X utf8 scripts/run_improvement_holdout.py --dry-run @holdoutArgs
py -3.13 -X utf8 scripts/run_improvement_holdout.py --preflight @holdoutArgs
```

W9-02: chạy primary; có thể dùng `--resume` ngay từ đầu:

```powershell
py -3.13 -X utf8 scripts/run_improvement_holdout.py --run --resume @holdoutArgs
```

TPM/RPM và lỗi transport/HTTP tạm thời thuộc policy đã khóa được tự chờ/retry;
quota ngày dừng giữ checkpoint. Khi đổi key, sửa `.env` rồi chạy lại **chính
lệnh run/resume trên**; CLI ưu tiên key trong file, tự preflight key mới và
phục hồi cùng UUID/request, tái dùng response durable nếu có. Giữ nguyên
plan/output/gate/release/ledger; không xóa checkpoint, reset hoặc phát lại
điểm complete. Không chạy đồng thời hai runner dùng ledger chung. Lỗi
integrity/schema/key không hợp lệ cần xử lý đúng nguyên nhân trước resume.

W9-03: sau run hoàn tất, kiểm offline toàn checkpoint và report (không gọi
API). Cần **primary_status=COMPLETE, G=64, đủ 384 Decision**, không thiếu
nhánh/unknown; `--verify-only` khi đang dở chỉ phục vụ kiểm phần có được:

```powershell
py -3.13 -X utf8 scripts/run_improvement_holdout.py --verify-only @holdoutArgs
py -3.13 -X utf8 scripts/run_improvement_holdout.py --verify-report @holdoutArgs
```

W9-04: chỉ khi report đủ mẫu và verify PASS mới khóa/kiểm bootstrap offline:

```powershell
py -3.13 -X utf8 scripts/run_improvement_holdout.py --bootstrap @holdoutArgs
py -3.13 -X utf8 scripts/run_improvement_holdout.py --verify-bootstrap @holdoutArgs
```

Các file `run/report.json` và `run/bootstrap.json` write-once, được consumer
đối chiếu với kết quả tái dựng. Bootstrap giữ L=4, độ nhạy 2/8, 10.000 draw,
PCG64 seed=20261016; CI cần ít nhất 9.500 draw hợp lệ, thiếu thì BLOCKED,
không sinh bù. W9-05/06 mới phân tích, vẽ hình và đóng băng kết quả theo
[checklist W9](../week9/README.md#checklist); không dùng fixture hoặc
selection development thay dữ liệu xác nhận thật.

## Protocol development và tiêu chí chọn

Giữ nguyên 60 point ID/ngày 2023 từ plan development v2 (FPT 12, ba mã còn
lại 16); đây là **exploratory**, không là validation độc lập. Thứ tự nhánh
cơ sở gồm 11 ID:
`original, bayesian, C2, A_tp_pool, B_semantic, C2_stats_only, C2_examples_only,
A_tp_pool_stats_only, A_tp_pool_examples_only, B_semantic_stats_only,
B_semantic_examples_only`. Sáu nhánh content-mode là ablation đăng ký,
không là sáu phương pháp mới hay ứng viên để chọn theo return. Các ablation
C2 dùng schema legacy, không mượn C3 có schema tự báo prior-use.

Mọi nhánh dùng cùng upstream một lần/point và deep-copy. Tái dùng upstream
W7 chỉ khi verifier chứng minh nguồn/model/options/projection tương thích;
nếu không, tạo upstream mới một lần/point cho toàn bộ nhánh. **Toàn bộ
Decision primary chạy mới cùng identity**, không chép action cũ; bằng chứng
W7 chỉ là đối chiếu lịch sử. Model agent giữ `openai/gpt-oss-20b`, temp=0,
max_tokens=2048, reasoning_effort=low, reasoning_format=hidden; vision
`qwen/qwen3.8-27b`, temp=0, max_tokens=1024, reasoning_effort=none,
reasoning_format=hidden. Không thêm seed LLM; retrieval seed=42 không là
seed sinh Decision. Max_retries client=0, retry qua wrapper/pacer đã kiểm.

Primary mỗi point/nhánh có **một Decision hoàn tất**, repeat_id=0. Xếp point
theo (as_of_date, thứ tự mã FPT/MWG/VCB/VNM), đánh j từ 0; thứ tự nhánh là
xoay trái danh sách 11 ID j mod 11 bước. Resume giữ nguyên thứ tự/attempt;
HTTP retry hoặc sửa format không phải lượt lặp khoa học.

**Mẫu lặp 12 point, ba lượt bổ sung/request**, repeat_id=1/2/3, namespace
riêng sau khi đủ primary; không chọn lượt tốt nhất hoặc nhập repeat vào D.
Chọn bằng readiness C2 W7 đã verify, không dùng action/return/mean: mỗi mã
ba strata rời nhau S=stats ready (bất kể examples), E_ONLY=chỉ examples
ready, OFF=không block ready. Trong mỗi pool xếp ngày tăng; lấy đầu pool S,
trung vị dưới E_ONLY (chỉ số floor((n−1)/2)), cuối pool OFF.

| Mã | S: đầu (rank/pool) | E_ONLY: trung vị dưới (rank/pool) | OFF: cuối (rank/pool) |
| --- | --- | --- | --- |
| FPT | FPT-2023-06-27 (1/2) | FPT-2023-10-04 (2/3) | FPT-2023-12-22 (7/7) |
| MWG | MWG-2023-06-30 (1/2) | MWG-2023-03-06 (3/5) | MWG-2023-12-22 (9/9) |
| VCB | VCB-2023-03-06 (1/2) | VCB-2023-08-29 (3/6) | VCB-2023-12-22 (8/8) |
| VNM | VNM-2023-01-06 (1/5) | VNM-2023-06-30 (2/4) | VNM-2023-12-19 (7/7) |

Giữ cả mẫu đã có bất đồng VCB, nhưng không chọn vì bất đồng; không thêm
MWG-2023-07-05 riêng vì biết action. Strata lịch sử không đổi theo readiness
A/B mới. Lặp cả 11 nhánh và `original_duplicate` (bản sao request Original
nguyên byte, chỉ ID checkpoint khác). Xếp 12 point theo quy tắc trên, j=0..11;
ở lượt r=1..3 xoay trái danh sách 12 ID, duplicate đặt cuối danh sách cơ sở,
(3j+r−1) mod 12 bước. Mỗi vị trí bắt đầu xuất hiện ba lần trong 36 block;
upstream giữ chung với primary, không chạy lại vision. Giữ request cố định
qua ba lượt cùng point/nhánh; schema/model/options giống nhau ở mọi nhánh.
Audit hash UTF-8 prompt và canonical HTTP body (messages/response_format/
model/options) tại transport, loại credential/header khỏi artifact; byte
HTTP thô chỉ được khẳng định nếu thực sự đã lưu/đối chiếu. Lưu response
fingerprint, thời điểm và attempt để chẩn đoán, không coi là biến can thiệp.

Báo số action bất đồng trên ba cặp lượt (1,2)/(1,3)/(2,3) mỗi request,
original−duplicate cùng lượt và prior-off−original, đủ mẫu số/strata.
Các cặp phụ thuộc, không gọi là quan sát độc lập. So A−C2, B−C2, full−stats,
full−examples từng lượt và trung bình ba lượt; dựng tài khoản mẫu 12 point
riêng từ vốn đầu. Không gộp với 60 điểm hoặc dùng repeat để đổi nomination.
Không đặt ngưỡng thắng cho trace; thiếu repeat thì chẩn đoán INCOMPLETE,
chưa kết luận tách được nhiễu Decision. Không thay mẫu hay chạy lượt thứ tư.

Primary D là trung bình đều ΔR tài khoản bốn mã so Original. Giữ eligibility
của W6-04: đủ 60 điểm ghép cặp, metric hữu hạn, bốn gate PASS, prior visible
ít nhất 6 điểm và ít nhất một điểm mỗi mã. Promotion: D>0, ΔR>0 ở ít nhất
3/4 mã, trung bình ΔMDD≤2 và tối đa ΔMDD≤5 điểm phần trăm; tie-break kế thừa
selector cũ: tie trong 1e−9 điểm phần trăm quanh D_max, rồi mean ΔMDD nhỏ
hơn, rồi thứ tự ID cố định `C2, A_tp_pool, B_semantic`. Tập xét nomination
là ba full-prior này, C2 là đối chứng có thể giữ lại; ablation không tham gia.
Ưu tiên tập đạt promotion, nếu rỗng chọn D cao nhất trong tập eligible và
ghi NOT_PROMOTED/Original triển khai. Không làm tròn trước xét ngưỡng.
Selection mới cần schema/validator tương ứng, không ép ID mới vào selector
hoặc registry cũ; selection W7 không đổi nhãn theo run mới.

Kiểm phụ cố định: Q1–Q4 và H1/H2 theo cutoff, dựng tài khoản mỗi nhóm từ
vốn đầu; leave-one-symbol-out là mean ΔR trên ba mã còn lại, không chọn lại
ứng viên; prior-off xét từng nhánh, cả hai off khi so hai prior; ablation
trên G đầy đủ và T cả stats/examples ready của base tương ứng. Báo nhóm
rỗng với null, không đổi primary theo subgroup thắng.

Diagnostics train giữ 651 query/2021–2022 và bootstrap 2020 theo fold PIT,
không gọi LLM train. A/C2 dùng sự kiện y=1 khi LONG ròng>0 do hàm kinh tế
chung; so Brier và log loss (clip p vào [1e−6,1−1e−6] chỉ khi tính loss)
trên giao query có cả hai posterior hữu hạn, báo giao/missing từng mã/fold
và coverage raw/ready riêng. Không điền p=0,5 khi C rỗng. Loss tổng là mean
query trên giao, kèm từng fold/mã; không gọi đây là xác suất LLM hiệu chuẩn.
Đo mean lãi khi thắng/mean lỗ khi thua và support riêng bằng nhãn net LONG,
không trình chúng như mô hình expected return hoặc policy. B giữ xác suất
C2 nên không có gain calibration số học độc lập. Không sửa A/B theo loss
hoặc coverage sau chạy; kết quả bất lợi vẫn đưa vào báo cáo.

Ablation stats-only/examples-only/full dùng cùng base evidence và request
contract, khác nội dung hiển thị có version. Báo common support/readiness;
khác biệt ngoài tập cùng ready không được quy riêng cho stats hoặc examples.
Self-report prior-use chỉ là telemetry, không chứng minh nhân quả.

## Khóa xác nhận và điểm dừng

Một vòng cố định A/B; dừng khi hoàn tất đánh giá hai cấu hình hoặc hết W8, mốc nào
đến trước. Không ghép A+B, thêm cấu hình thay thế hoặc tối ưu theo return.
Nếu A/B bị chặn kỹ thuật trước API, ghi NOT_RUN/BLOCKED và lý do, không
đổi tham số để lấy cấu hình thắng; ma trận rút gọn phải khóa amendment trước
API, giữ đối chứng/ablation C2; với M ID thực tế xoay primary j mod M,
repeat (3j+r−1) mod (M+1), duplicate đặt cuối. Mẫu 12 point và ba lượt giữ nguyên.
Nếu không có ứng viên mới eligible, C2 chỉ được bàn giao sau tái kiểm
eligibility/binding phù hợp; không dùng dữ liệu thiếu để báo primary COMPLETE.
Không có ứng viên promotable thì Original triển khai. Lỗi integrity chưa sửa
chặn gate; không dùng mock thay hiệu quả thật. Sửa lỗi ảnh hưởng action sau
đã xem kết quả phải có revision riêng và ghi exploratory, không lấy lượt tốt nhất.

Ma trận W9 tối thiểu: Original, Bayesian v1, C2, ứng viên được chọn và
stats-only/examples-only tương ứng nếu đủ contract; gộp ID trùng trước chạy.
Nếu fallback C2 thì đặc tả ablation C2 riêng hoặc ghi không đủ khả năng
cô lập thành phần; không dùng ablation C3 để gọi là ablation C2.
Mọi nhánh cần schema/runner/verifier trước khóa; rút nhánh secondary chỉ
trước API và ghi lý do, không rút sau thấy return. Không mở sensitivity
K=5, risk overlay, model search hoặc replay LLM train trong lịch này.

Primary/secondary, CI và missing xử lý theo
[protocol thống kê W9 đã khóa](../week9/README.md#protocol-thống-kê-đã-khóa-tại-w7-14).
W8-07 hiện thực và kiểm công cụ bằng fixture, bind đặc tả/version/hash vào
manifest trước outcome; không chọn lại block/test vì CI hoặc p-value đẹp.

Giữ 64 điểm holdout 2024, 16/mã; tạo manifest/output mới bind selection,
protocol, code/schema/runtime/model/scaler/nguồn. Không đọc outcome để chọn
cấu hình. Bốn gate theo AGENTS.md, verifier và dry-run PASS mới bàn giao W9.
Giữ T+2.5, PIT, risk OFF, một upstream/point deep-copy, BRPP≤600 và prompt
<6.500 ký tự. Mọi API qua retry/pacer/checkpoint; người dùng tự chạy.

**Gate W8:** 8/8 DONE, selection và manifest kiểm được. Không đồng nghĩa
Bayesian ICL đã thắng; hiệu quả xác nhận còn chờ W9. README này giữ checklist
và kết quả gọn; artifact runtime có revision, không tạo receipt trùng lặp.
