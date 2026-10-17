# Tuần 8 — Cải tiến Bayesian ICL, validation và khóa xác nhận

**Trạng thái: IN_PROGRESS, 3/8; W8-01–03 DONE, tiếp theo W8-04.**
Kế hoạch điều chỉnh 16/10/2026; cập nhật 17/10/2026; giữ deadline 10 tuần.
[Kế hoạch tổng](../plan.md) · [W7](../week7/README.md) · [W9](../week9/README.md)

## Mục tiêu và giới hạn

Cải thiện Bayesian ICL bằng một vòng có đối chứng, tối đa **hai cấu hình
phương pháp mới**. C2 NOT_PROMOTED là mốc nghiên cứu; Original vẫn là lựa
chọn triển khai. Không thay selection/report/checkpoint W7. Đầu vào là Gate D
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
| W8-04 | Người dùng preflight/run/resume theo hướng dẫn; Decision thật trên 60 điểm, mọi nhánh chung upstream | 03 | [ ] TODO |
| W8-05 | Verify toàn primary và đủ mẫu lặp; phân tích ΔR/MDD/coverage/ablation/prior-off và độ ổn định | 04 | [ ] TODO |
| W8-06 | Khóa selection mới và lý do; giữ ngưỡng W6-04, báo mọi cấu hình đã thử | 05 | [ ] TODO |
| W8-07 | Khóa ma trận, thống kê, manifest holdout 64 điểm; dry-run và kiểm công cụ phân tích bằng fixture | 06 | [ ] TODO |
| W8-08 | Nghiệm thu bốn gate, hash nguồn/runtime và hướng dẫn chạy/verify/resume W9 | 07 | [ ] TODO |

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

#### Lệnh vận hành W8-04 và kiểm offline sau run

Chạy từ root repository bằng Python 3.13.5. Các đường dẫn dưới đây dành cho
revision này; giữ nguyên file plan, receipt, code/runtime và ledger chung khi
resume. `.env` chứa `GROQ_API_KEY` do người dùng quản lý. **Người dùng tự chạy
hai lệnh preflight/run có API; agent chỉ chạy các chế độ offline.**

```powershell
$taskPlan = "outputs/bayesian_benchmark/improvement_v1/development/plan.json"
$taskRun = "outputs/bayesian_benchmark/improvement_v1/development/run"
$taskGates = "docs/plan/week8/validation_gates/development_lock_v1/technical_gates.json"
$taskLedger = "outputs/oos_pilot/api_usage.json"
$taskRepeatPlan = "outputs/bayesian_benchmark/improvement_v1/repeats/plan.json"
$taskRepeatRun = "outputs/bayesian_benchmark/improvement_v1/repeats/run"

# Offline: dựng lại binding nguồn/PIT, không đọc key hoặc gọi mạng.
py -3.13 -X utf8 scripts/run_improvement.py --dry-run --plan $taskPlan

# API: người dùng kiểm hai model/options/schema với key đang dùng.
py -3.13 -X utf8 scripts/run_improvement.py --preflight --plan $taskPlan --output-dir $taskRun --technical-gates $taskGates --ledger $taskLedger

# API: primary 60 điểm, 11 nhánh, upstream mới một lần/điểm.
py -3.13 -X utf8 scripts/run_improvement.py --run --plan $taskPlan --output-dir $taskRun --technical-gates $taskGates --ledger $taskLedger

# API: chỉ dùng khi tiếp tục output đã khởi tạo; không chạy lại slot complete.
py -3.13 -X utf8 scripts/run_improvement.py --run --resume --plan $taskPlan --output-dir $taskRun --technical-gates $taskGates --ledger $taskLedger

# Offline: kiểm checkpoint, raw response, request/body audit và report.
py -3.13 -X utf8 scripts/run_improvement.py --verify-only --plan $taskPlan --output-dir $taskRun --technical-gates $taskGates --ledger $taskLedger
py -3.13 -X utf8 scripts/run_improvement.py --verify-report --plan $taskPlan --output-dir $taskRun --technical-gates $taskGates --ledger $taskLedger

# Offline, chỉ sau primary COMPLETE và report hợp lệ.
py -3.13 -X utf8 scripts/run_improvement.py --prepare-repeat --plan $taskPlan --output-dir $taskRun --repeat-plan $taskRepeatPlan --technical-gates $taskGates --ledger $taskLedger

# API: người dùng chạy ba lượt bổ sung, mỗi lượt 12 điểm x 12 nhánh;
# dùng nguyên shared/request primary, không gọi lại upstream.
py -3.13 -X utf8 scripts/run_improvement.py --run --plan $taskRepeatPlan --output-dir $taskRepeatRun --technical-gates $taskGates --ledger $taskLedger

# API: tiếp tục repeat bị ngắt; không mở lượt khoa học thứ tư.
py -3.13 -X utf8 scripts/run_improvement.py --run --resume --plan $taskRepeatPlan --output-dir $taskRepeatRun --technical-gates $taskGates --ledger $taskLedger

# Offline: nghiệm thu repeat trước phân tích W8-05/selection W8-06.
py -3.13 -X utf8 scripts/run_improvement.py --verify-report --plan $taskRepeatPlan --output-dir $taskRepeatRun --technical-gates $taskGates --ledger $taskLedger
```

`--verify-only` có thể trả report INCOMPLETE hợp lệ; chỉ nhận hoàn tất khi
primary đủ 660 Decision complete, không pending/unknown, và repeat đủ 432
Decision complete. Khi bị ngắt, giữ cả checkpoint/journal/ledger. Với attempt
unknown, chạy `--reconcile` offline cùng plan/output/gates/ledger tương ứng để
xem UUID/trạng thái attempt, rồi đối chiếu HTTP audit trong ledger. Chỉ sau
đối soát cụ thể mới dùng
`--authorize-replay <UUID> --replay-reason "<lý do đối soát>"` cùng
`--reconcile`; lệnh này ghi authorization, không gọi API. Sau đó người dùng
chạy `--run --resume`. Không xóa lock của tiến trình còn sống, xóa slot, reset
ledger hoặc tự đổi model/key để bỏ cooldown. Thay key tự kích hoạt preflight
theo credential scope; preflight/retry/format repair không tăng repeat_id.

Nếu clone chưa có artifact local, chuẩn bị lại plan từ parent W7 đã khóa bằng
lệnh dưới; producer chỉ chấp nhận đúng nguồn/code/runtime và không ghi đè
artifact khác nội dung. Diagnostics train có producer/verifier riêng, không
cần key. Cả hai output nằm ngoài Git; hash nghiệm thu được ghi tại mục này.

```powershell
py -3.13 -X utf8 scripts/run_improvement.py --prepare --parent outputs/bayesian_benchmark/development_candidate_plan_v2.json --plan $taskPlan
py -3.13 -X utf8 scripts/run_improvement.py --train --train-report outputs/bayesian_benchmark/improvement_v1/train/diagnostics.json
py -3.13 -X utf8 scripts/run_improvement.py --verify-train --train-report outputs/bayesian_benchmark/improvement_v1/train/diagnostics.json
```

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
