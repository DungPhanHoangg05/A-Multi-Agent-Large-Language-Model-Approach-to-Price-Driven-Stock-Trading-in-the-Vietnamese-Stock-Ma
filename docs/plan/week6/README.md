# Tuần 6 — Cải thiện retrieval và cách Decision sử dụng bằng chứng

**Trạng thái: Phase A IN_PROGRESS, W6-01 DONE, 1/16 task hoàn thành.** Ngày lập/cập nhật: **10/10/2026**. Tiếp theo **W6-02**.
[Kế hoạch tổng](../plan.md) · [Bàn giao W5](../week5/README.md)

## 1. Mục tiêu và phạm vi

W6 tạo các ứng viên Bayesian v2 có thể kiểm chứng trên đường CLI chính:
truy xuất theo hoàn cảnh giá, thống kê điều kiện có support/uncertainty và
Decision có trace sử dụng bằng chứng. Hoàn thành W6 là hoàn thành code,
hợp đồng và kiểm thử; lợi ích đầu tư còn phải kiểm chứng ở W7–W9.

| Đầu vào W5 đã đóng | Cách sử dụng ở W6 |
| --- | --- |
| Commit đóng tuần `99d6cb1`; mốc code smoke `0286119` | Giữ checkout lịch sử để verify; mọi thay đổi identity dùng run mới |
| Bank 852 episode 2020–2022, model/proof train-only hồi cứu | Giữ nguyên bản gốc; kiểm riêng tính phù hợp theo từng cutoff/fold |
| 124 điểm chính: 60 development 2023, 64 holdout 2024; 4 smoke riêng | Kế thừa lịch/embargo; chưa chạy cohort chính trong W6 |
| Smoke v1 4/4 điểm, 20/20 Decision; 624 unit/105 leakage và E2E PASS | Mốc hồi quy, chưa là bằng chứng hiệu quả v2 |
| Retrieval v1 p95 9,642–12,127 ms; evidence v2 5,0475 ms trên máy đã giảm tải | So lại sau thay đổi, cùng protocol; ngưỡng retrieval <30 ms |
| BEAR OOS=0, tin reliable=0; FPT Q1 thiếu bốn mẫu | Công bố giới hạn; không bù mẫu/tin hoặc tạo regime giả |

**Phân hoạch:** dữ liệu train phục vụ bank 2020–2022; lịch sử trước đó chỉ
dùng khi cần warm-up/fit theo provenance đã kiểm. W6 kiểm kỹ thuật và tính
nhân quả trên train; W7 chọn ứng viên bằng train/development 2023; W8 đánh
giá xác nhận 2024. Không chọn tham số theo holdout, smoke hoặc ca FPT
20/02/2023. Không yêu cầu ứng viên phải thắng lợi nhuận để đóng gate kỹ thuật.

Mọi lượt dùng API key do **người dùng tự chạy** theo lệnh được bàn giao khi
CLI/plan tương ứng đã có. Agent làm code, kiểm offline và đối soát kết quả.
Không có task dự toán ngân sách hoặc lịch chạy API. Runtime vẫn giữ pacing,
quota, cooldown, ledger chung và đối soát attempt chưa rõ kết quả.

## 2. Các hợp đồng phải giữ

- LONG: Open(t+1)→Close(t+3); SHORT=CASH; phí môi giới 0,25% và trượt giá
  0,10% mỗi chiều. Nhãn dùng `compute_round_trip_net_return`.
- Giá/tin ≤cutoff, bỏ tin không ngày; prior `exit_date < cutoff`. Query
  feature/ranking không nhận outcome/P&L tương lai; vi phạm ném lỗi.
- Một upstream/Full cho mỗi điểm; deep-copy sang mọi nhánh. Giữ Original
  prompt và năm nhánh v1; không gọi thêm LLM để ép Decision theo prior.
- K≤3, BRPP≤600 ký tự, Decision prompt<6.500; giữ distill/cap. Chưa mở K=5.
- Giữ bank/model/manifest/calendar/checkpoint W4–W5 nguyên byte. Feature,
  scaler, fold model hoặc protocol mới có artifact/hash/version riêng.
- Giá chỉ dùng VCI/KBS qua nguồn có provenance; kiểm đơn vị, điều chỉnh giá,
  sự kiện quyền, warm-up và thiếu phiên trước khi tính feature. Không trộn
  lịch sử đã điều chỉnh hồi tố với giá raw mà không có hợp đồng rõ ràng.
- Chỉ thêm schema/config/fixture được code đọc; output runtime gitignore.
  README này là checklist và nhật ký chính, không tạo receipt theo từng task.

## 3. Checklist và thứ tự thực hiện

| Phase | Task | Công việc | Phụ thuộc | Trạng thái |
| --- | --- | --- | --- | --- |
| A | W6-01 | Xác minh bàn giao và xác định điểm tích hợp | W5 đóng | [x] |
| A | W6-02 | Audit dữ liệu feature và tính nhân quả theo fold | 01 | [ ] |
| A | W6-03 | Chốt hợp đồng feature/ranking/thống kê | 02 | [ ] |
| A | W6-04 | Đăng ký ứng viên, ablation và tiêu chí đánh giá | 03 | [ ] |
| B | W6-05 | Bộ trích xuất đặc trưng giá PIT | Gate A | [ ] |
| B | W6-06 | Scaler theo train/fold và auxiliary index | 05 | [ ] |
| B | W6-07 | Similarity kết hợp tín hiệu và giá | 06 | [ ] |
| B | W6-08 | Recency, đa dạng ví dụ và trace lựa chọn | 07 | [ ] |
| C | W6-09 | Thống kê điều kiện và shrink có kiểm chứng | Gate B | [ ] |
| C | W6-10 | Quality gate theo support/uncertainty | 09 | [ ] |
| C | W6-11 | Prompt/Decision contract và ablation nội dung | 10 | [ ] |
| C | W6-12 | CLI, protocol, identity và checkpoint ứng viên | 08, 11 | [ ] |
| D | W6-13 | Chốt phạm vi risk policy và cách quy kết tác động | Gate C | [ ] |
| D | W6-14 | Validation train PIT offline và chẩn đoán ứng viên | 13 | [ ] |
| D | W6-15 | Hồi quy, leakage, fault/resume và hiệu năng | 14 | [ ] |
| D | W6-16 | Chốt W6 và bàn giao validation W7 | 15 | [ ] |

Các task triển khai lần lượt theo phụ thuộc; chỉ mở phase sau khi gate trước
PASS. Quyết định phương pháp phải được ghi trước khi xem kết quả so sánh.

### Phase A — Chốt dữ liệu và thiết kế

#### W6-01 — Xác minh bàn giao và xác định điểm tích hợp

- **Làm:** kiểm input lock, smoke verifier và checksum nguồn/code/runtime ở
  mốc W5; lập bản đồ caller cho retriever, evidence, Decision, cohort và
  journal. Ghi API nào đã có, API nào cần thêm/version hóa.
- **Đầu ra:** cập nhật mục đầu vào và danh sách module ảnh hưởng trong README;
  dùng identity/checkpoint hiện hữu làm bằng chứng.
- **Đạt khi:** input 128/128, smoke 4/4–20 Decision verify được offline;
  có mốc hồi quy và cách kiểm lại lịch sử sau khi code đổi, không API.

##### Kết quả xác minh bàn giao — DONE/PASS, 10/10/2026

Input verifier **128/128 PASS**: 4 smoke, 60 development 2023, 64 holdout
2024. CLI dry-run, `--verify-only` và `--reconcile` PASS trên nguồn local
hiện có. Smoke bốn mã complete, **20/20 Decision v1**; report dựng lại khớp
bản lưu. Mỗi điểm có Indicator/Pattern/Trend/Full durable complete; không
còn attempt cần xử lý trong smoke. `primary_status=NOT_APPLICABLE` đúng
cho ma trận `smoke_v1`, chưa là nghiệm thu hiệu quả v2.

| Phạm vi kiểm | Kết quả |
| --- | --- |
| Input lock | 46/46 nguồn, 46/46 file code/schema/config, 23/23 mục runtime khớp; Python 3.13.5 |
| Identity smoke từng mã | 32/32 code, 12/12 nguồn, 8/8 mục runtime; hợp với binding cohort |
| Hợp các nguồn/code của lock và smoke | 47 đường nguồn khớp byte hash; 46 đường code khớp nội dung commit `0286119` sau chuẩn hóa newline |
| Cách đối chiếu checksum | Lock/cohort dùng byte SHA-256; `identity.code_sha256` con dùng UTF-8 text chuẩn hóa LF. Kiểm theo đúng phương pháp từng lớp, không ép hai loại hash bằng nhau |
| Audit input/smoke | 0 lần mở credential, 0 DNS/socket connect; transport verifier cấm HTTP |
| Gate hồi quy cho task | Compileall/E2E, 624 unit và 105 test leakage PASS, không skip; 122 file bảo vệ nguyên byte sau kiểm |

Metadata `LOCKED_OFFLINE_BUDGET_DEFERRED`/`gate_c=PENDING` trong lock là
trạng thái lúc tạo W5-12; quyết định bỏ W5-11 và nghiệm thu W5 ghi ở README
W5. Giữ byte/hash manifest, không đổi metadata cũ thành nhãn PASS.

##### Bản đồ caller và điểm mở rộng

| Luồng/API hiện có | Hành vi đang được kiểm | Điểm nối cho task sau |
| --- | --- | --- |
| `scripts/run_bayesian_ablation.py:execute_cohort` → `PriorBacktestRunner.run_cohort` → `core/research_cohort.py:run_cohort` | Kiểm plan/source/identity cả bốn mã trước API, ledger chung và chế độ offline | W6-12: plan/registry ứng viên mới; chưa có CLI chạy sáu cấu hình C0–C3/ablation |
| `PriorContextAdapter.prepare` → `PriorPointContext.agent_state` / `bind_full` / `restore_full_bundle` / `_query` trong `core/prior_context.py` | `agent_state()` cấp bản sao `point_in_time_df`; seal Full, whitelist query; source verifier ở adapter có kiểm file | W6-05/06/12: feature query/scaler/index, whitelist và provenance phiên bản riêng; không đưa `execution_data()`/evaluation vào query |
| `SetGraph.compile_report_decision` → `PriorPointContext.retrieve` → `BayesianPriorRetriever.retrieve` | Luồng v1 trả `tasks/stats/metadata`; graph kiểm nguồn và format prefix trước Decision | W6-07/08: thêm metric/policy riêng, giữ API v1 và `signal_match_v1` tái lập được |
| `research_cohort.v2_point` → `PriorPointContext.evidence_v2` → `BayesianPriorRetriever.retrieve_evidence` → `core/prior_evidence_v2.py` | Regime population, similarity tín hiệu, Beta–Binomial, quality gate, `format_evidence_prefix` | W6-07–10: feature/ranking, thống kê điều kiện/shrink và trạng thái stats/examples cần contract/version mới |
| `agents/decision_agent.py:create_final_trade_decider` với `_prior_preparer` / `_before_invoke` | Distill/cap → compact prompt → chèn BRPP → wrapper retry/structured parse; v2 dùng deep-copy Full | W6-11: contract/trace và ba chế độ nội dung; giữ Original prompt, cap và guard. Chưa có chế độ stats-only/examples-only |
| `research_input_lock.CODE_PATHS` / `validate_bound_plan`, `PriorBacktestRunner._identity`, cohort identity | Khóa code/config/runtime/source; child v1 và cohort có phiên bản riêng | W6-06/12: ghim module/index/scaler/fold/candidate mới; không sửa lock hay identity smoke đã chạy |
| `PriorCheckpointStore` / `CheckpointSession` + `StageJournal.invoke`; `research_cohort.v2_point` | V1 có branch intent/output và journal node; v2 có slot/attempt/prompt/evidence riêng, complete không replay | W6-12/15: checkpoint từng candidate, verifier dựng lại semantic và fault/resume; v2 không tự đi qua journal node như upstream |
| `core/research_metrics.py:research_report` / `branch_metrics` | Metric chu kỳ, common support và primary tham chiếu nhánh cố định `bayesian_v2` | W6-12.c: report theo candidate ID, giữ ΔR từng mã/trung bình bốn mã và pending ngoài mẫu chấm |
| `PriorRunLock`, `GroqPacer`, `research_invocation.invocation_scope` | Khóa OS/ledger, pacing, HTTP/format retry chung, lưu unknown/reserve | W6-12/15: kế thừa guard cho mọi candidate; không tạo client/runner bỏ qua guard |

Hot query của retriever khác bước kiểm nguồn ở adapter: benchmark retrieval
phải giữ rõ ranh giới này và báo chi phí feature/transform khi thêm ở W6.
Code hiện có chưa cung cấp feature giá/scaler/auxiliary index, trọng số
recency/ràng buộc diversity cho ranking v2, conditional shrink hoặc registry
nhiều ứng viên. Những phần đó thuộc
05–12; kiểm bàn giao này chưa thay cho audit tính nhân quả từng fold ở 02.

##### Lệnh kiểm và tái lập sau khi code đổi

Từ root, kiểm offline hiện trạng (không dùng key):

```powershell
py -3.13 -X utf8 scripts/prepare_research_inputs.py --verify
py -3.13 -X utf8 scripts/run_bayesian_ablation.py --plan outputs/bayesian_benchmark/smoke_plan.json --output-dir outputs/bayesian_benchmark/smoke_run --verify-only
py -3.13 -X utf8 scripts/run_bayesian_ablation.py --plan outputs/bayesian_benchmark/smoke_plan.json --output-dir outputs/bayesian_benchmark/smoke_run --reconcile
```

Mốc đóng W5 là `99d6cb1`, mốc code của smoke là `0286119`; code khảo sát tại
`333e0a0` vẫn khớp mốc smoke. Khi code/schema/config thay đổi, tạo checkout
độc lập ở thư mục mới để kiểm lịch sử:

```powershell
$w5ReviewRoot = Join-Path (Split-Path (Get-Location) -Parent) "kltn-w5-review-0286119"
git worktree add --detach "$w5ReviewRoot" 0286119
```

Giữ bản gốc, sao chép đúng byte các source được lock/identity dẫn chiếu và
`outputs/bayesian_benchmark/{input_lock.json,smoke_plan.json,calendar.json,
coverage.json,smoke_run/}`, cùng ledger/input/audit W4 và bank/model/QA.
Giữ journal/attempt; không mang metadata lock/owner/recovery đang hoạt động
sang máy/checkout khác. Phục hồi Python/dependency theo runtime identity,
đối chiếu byte hash nguồn và loại hash code đã ghi rồi chạy các lệnh trên
tại root checkout mới. Clone Git riêng không có runtime output đã gitignore.
Run ứng viên W6 dùng identity/output mới; không sửa fingerprint smoke để
nhận code mới. Quy trình chi tiết về quota/unknown nằm ở bàn giao W5.

#### W6-02 — Audit dữ liệu feature và tính nhân quả theo fold

- **Làm:** rà OHLCV train bốn mã, warm-up, giá raw/điều chỉnh, quyền và đơn vị;
  nối episode bằng ID/ngày. Rà ngày fit/freeze của HMM, scaler, alpha và
  cấu hình sinh báo cáo lịch sử cho từng fold dự kiến.
- **Đầu ra:** bảng coverage/thiếu nguồn và ma trận cutoff→nguồn đủ điều kiện;
  xác định adapter có thể tái lập hoặc artifact mới cần chuẩn bị.
- **Đạt khi:** phân biệt rõ fixture kỹ thuật với validation lịch sử có
  provenance nhân quả. Model fit hết 2022 hoặc cấu hình chọn bằng toàn train
  không được coi hợp lệ cho query trước ngày fit. Nếu báo cáo cũ bị ảnh hưởng,
  không chỉ thay nhãn regime rồi coi đã sửa leakage; phải có đường tái tạo
  đúng fold. Thiếu nguồn/proof cần thiết thì Gate A BLOCKED, không sửa bank gốc.

#### W6-03 — Chốt hợp đồng feature/ranking/thống kê

- **Làm:** định nghĩa chính xác nhóm feature gọn: momentum, volatility,
  khoảng cách MA; cửa sổ/đơn vị/điểm cuối, min-history, NaN và zero-variance.
  Chốt fit/transform theo fold, metric kết hợp, trọng số, tie-break và ngày
  tính tuổi. Định nghĩa population, tập điều kiện và mẫu số từng metric.
- **Đầu ra:** đặc tả tại README; schema/config chỉ thêm khi validator đọc.
  Gắn version feature/scaler/ranking/stats/prefix vào provenance.
- **Đạt khi:** có ví dụ tính tay và trường hợp biên; label không vào feature,
  scaler hoặc ranking. Shrink không đếm dữ liệu tập điều kiện hai lần qua
  hyperprior và likelihood; nếu dùng empirical Bayes phải ghi cách ước lượng
  và giới hạn diễn giải khoảng bất định. Không gọi win-rate là expected return.

#### W6-04 — Đăng ký ứng viên, ablation và tiêu chí đánh giá

- **Làm:** khóa danh sách hữu hạn trước thực nghiệm, cùng seed=42/K≤3/scope
  same_symbol. Mỗi ứng viên có giả thuyết, khác biệt so với đối chứng và config.
- **Danh sách dự kiến:** C0 = evidence W5; C1 = feature/ranking/recency/diversity
  mới; C2 = C1 +thống kê điều kiện/gate; C3 = C2 +Decision contract mới.
  C3 có hai ablation nội dung `stats_only`, `examples_only` bên cạnh
  `full_prior`. Tổng tối đa **6 cấu hình v2**, không chạy tích Descartes tham số;
  năm nhánh v1 vẫn là đối chứng riêng. W7 chốt ma trận chạy thực sau validation.
- **Đầu ra:** bảng registry/config và giả thuyết trong README; chỉ tách config
  runtime khi CLI ở 12 đọc. Thông số cụ thể được chốt tại task này sau audit
  nguồn, không diễn giải mặc định W5 là đã tối ưu.
- **Đạt khi:** từng thay đổi có phép so sánh kiểm soát; so paired trên common
  support, báo coverage/missing/error. Mục tiêu W6 là tính đúng/khả năng đo;
  chọn ứng viên và ngưỡng bằng development thuộc W7. Mở rộng danh sách phải
  ghi amendment trước chạy, không thử tiếp đến khi có kết quả thuận lợi.

Giữ hợp đồng đánh giá W5: Δ net return v2–Original theo từng mã và trung bình
đều bốn mã; báo kèm MDD, balanced accuracy, số giao dịch/CASH, bất đồng action
và coverage. Không annualize Sharpe/Sortino chu kỳ hoặc gộp pilot/smoke vào
mẫu chính. Kết quả validation W7 và holdout W8 được báo riêng.

**Điều kiện Gate A (chưa nghiệm thu):** 01–04 DONE; dữ liệu/provenance đủ cho phạm vi đã đăng ký, công thức
và phương pháp nhân quả có thể triển khai, chưa dùng outcome holdout.

### Phase B — Đặc trưng và truy xuất

#### W6-05 — Bộ trích xuất đặc trưng giá PIT

- **Làm:** extractor dùng cùng quy tắc giá cho episode/query, cắt ≤cutoff
  trước rolling; vector hóa. Trả vector, ngày dữ liệu, coverage và reason.
- **Đầu ra:** module feature dùng lại được, test tính tay/bất biến khi thêm
  nến tương lai/thiếu phiên/quyền/đơn vị; kết nối adapter hiện hành.
- **Đạt khi:** query không cần evaluator/giá thoát lệnh; future data không
  đổi vector; thiếu dữ liệu được báo theo contract, không tự điền từ tương lai.

#### W6-06 — Scaler theo train/fold và auxiliary index

- **Làm:** fit scaler chỉ trên phần train hợp lệ trước query/fold; phục vụ
  OOS bằng scaler đã khóa cuối train. Xây index episode→vector, không thêm
  cột vào bank 852 episode; nạp/kiểm hash một lần trước hot query.
- **Đầu ra:** producer/loader/validator cho artifact runtime, liên kết bank,
  source, feature/scaler version và fit cutoff; schema tối thiểu khi cần.
- **Đạt khi:** fold sớm không dùng scaler fit bằng fold muộn; ID thiếu/trùng,
  source sai hoặc dữ liệu không hữu hạn dừng rõ ràng. Round-trip JSON native,
  tái tạo cùng nguồn cho cùng hash; index không chứa query outcome.

#### W6-07 — Similarity kết hợp tín hiệu và giá

- **Làm:** thêm metric có version, giữ `signal_match_v1`; lọc PIT/symbol/regime
  trước xếp hạng, tính khoảng cách vector hóa và tie-break xác định.
- **Đầu ra:** entry point retriever mới và trace từng thành phần score;
  đường v1 vẫn tái lập được từ nguồn/config cũ.
- **Đạt khi:** kiểm ranking bằng oracle nhỏ, labels bị hoán đổi không đổi
  lựa chọn, query tương lai không làm cache ảnh hưởng query quá khứ; không
  I/O hoặc fit scaler trong hot query. Không tự fallback khi lỗi provenance.

#### W6-08 — Recency, đa dạng ví dụ và trace lựa chọn

- **Làm:** áp dụng luật tuổi/đa dạng ngày đã đăng ký, loại ví dụ quá giống
  nhau; ghi score trước/sau và lý do giữ/loại. K_eff có thể nhỏ hơn K.
- **Đầu ra:** policy chọn ví dụ và trace selected/excluded IDs; test trùng
  ngày, cạnh ngưỡng, tập rỗng, chỉ có một ví dụ và thứ tự dữ liệu đảo.
- **Đạt khi:** quyết định chọn không dùng WIN/LOSS; thay K hoặc diversity
  không âm thầm thay population của statistics. V1 không đổi, v2 xác định,
  trả lý do khi không đủ ví dụ thay vì bù bằng future/cross-symbol.

**Điều kiện Gate B (chưa nghiệm thu):** 05–08 DONE; feature/index/scaler/ranking chạy qua API production,
kiểm PIT và tính xác định PASS, bank/source gốc nguyên vẹn.

### Phase C — Bằng chứng và Decision trên CLI

#### W6-09 — Thống kê điều kiện và shrink có kiểm chứng

- **Làm:** thống kê regime+tín hiệu theo contract, phân biệt population,
  nhóm điều kiện và K ví dụ. Shrink theo quy tắc đã khóa; đếm một cycle một
  lần, kể cả nhiều agent cùng phát tín hiệu. Dùng outcome chỉ của prior đã đóng.
- **Đầu ra:** evidence version mới gồm raw counts, support, posterior,
  uncertainty, nguồn hyperprior và lý do fallback; validator tái tính từ nguồn.
- **Đạt khi:** đối chiếu ví dụ tính tay; n=0/1, thiếu lớp, tín hiệu xung đột,
  nhóm hiếm và equality exit=cutoff đúng. Không phát sinh support giả hoặc
  khẳng định posterior tỷ lệ lịch sử là xác suất LLM được hiệu chuẩn.

#### W6-10 — Quality gate theo support/uncertainty

- **Làm:** gate chất lượng theo ngưỡng đăng ký, tách trạng thái stats và
  examples để `stats_only` không bị vô hiệu chỉ vì K_eff=0. Định nghĩa rõ
  insufficient/disabled/ready và fallback về Original.
- **Đầu ra:** policy version, reason codes và trace đủ để tái dựng prompt.
- **Đạt khi:** test các phía của từng ngưỡng; K=0/prior disabled giữ Original
  đúng contract, không biến lỗi hệ thống thành thiếu evidence. Quality gate
  không tự đổi LONG thành CASH; policy giao dịch được xét riêng ở 13.

#### W6-11 — Prompt/Decision contract và ablation nội dung

- **Làm:** builder trình bày bằng chứng gọn; Decision đối chiếu tín hiệu hiện
  tại, support/uncertainty và ví dụ khi có. Lưu evidence hash/IDs, nguồn,
  raw action và lý do theo schema; lý do LLM là trace tự báo cáo, không tự
  chứng minh cơ chế nhân quả. Cài ba chế độ nội dung của C3.
- **Đầu ra:** prefix/prompt có version và validator; fixture đầy đủ, thiếu
  evidence, mâu thuẫn và văn bản dài. Không ép action mong muốn bằng retry.
- **Đạt khi:** BRPP≤600/prompt<6.500 ở mọi cấu hình; thiếu format dừng đúng
  wrapper/budget invocation hiện hành. Các ablation dùng cùng query/upstream,
  không vô tình bỏ block Original hoặc lộ evaluation/P&L query vào prompt.

#### W6-12 — CLI, protocol, identity và checkpoint ứng viên

- **12.a:** nối registry→feature/index→retriever→evidence→prompt vào CLI;
  producer plan mới kế thừa source/calendar nhưng version hóa code/config.
- **12.b:** checkpoint từng nhánh, durable response, identity và semantic
  verifier phải dựng lại score/count/prompt/action từ nguồn, không chỉ hash.
- **12.c:** report nhận candidate ID thay vì cố định một nhánh `bayesian_v2`;
  giữ metric chu kỳ không annualize, tách từng mã và common support. Không
  gộp nhiều ứng viên thành một kết quả hoặc chấm điểm các nhánh pending.
- **Đầu ra:** CLI prepare/dry-run/verify/reconcile/resume có thể chạy trên
  fixture; giữ five-branch v1 và C0, tách các ứng viên bằng ID/config hash.
- **Đạt khi:** bốn mã dùng một upstream/Full mỗi điểm; resume chỉ chạy phần
  thiếu, đổi config/model/index/fold bị chặn. Verify/dry-run không đọc key
  hoặc gọi mạng; journal/ledger/unknown được kế thừa. Không đổi fingerprint
  của smoke cũ. Chưa tạo executable plan holdout hoặc chạy API ở task này.

**Điều kiện Gate C (chưa nghiệm thu):** 09–12 DONE; đường CLI production chạy đủ cấu hình đã đăng ký trên
fixture, posterior/gate/prompt/trace/identity/paired/resume PASS.

### Phase D — Kiểm chứng và bàn giao

#### W6-13 — Chốt phạm vi risk policy và cách quy kết tác động

- **Mặc định:** chưa bật numeric risk gate trong W6; ghi quyết định cùng
  lý do, bảo đảm raw_action=executed_action khi không có policy. Task này
  bắt buộc chốt quyết định, không bắt buộc thêm policy giao dịch.
- **Nếu đưa vào phạm vi:** đăng ký ablation riêng trước đo, công thức/ngưỡng
  dựa train/development, policy hash và raw/executed/reason; không gộp cải
  thiện do chặn lệnh với lợi ích ICL. Thêm test tác động đúng một lớp.
- **Đạt khi:** report phân biệt rõ model action, policy action và nhãn kinh
  tế. Nếu hoãn thì ghi DEFERRED policy, task quyết định vẫn DONE; không coi
  policy chưa viết là tính năng đã triển khai. Không dùng ca pilot để ép luật.

#### W6-14 — Validation train PIT offline và chẩn đoán ứng viên

- **Làm:** chạy harness fold đã audit, purge/embargo theo ngày vào/thoát
  thực tế; fit model/scaler/hyperparameter trên prefix hợp lệ. Đánh giá
  coverage, support, khoảng cách, tuổi/đa dạng, gate và độ ổn định lựa chọn.
- **Đầu ra:** CLI/report đọc lại được, bảng chẩn đoán ngắn trong README;
  giữ tách kết quả observed với fixture/mock Decision. Không xếp hạng lợi
  nhuận LLM từ Decision giả; hướng dẫn người dùng nếu cần tái tạo bằng API.
- **Đạt khi:** tái lập được các fold hợp lệ và không có future leakage;
  các trường hợp thiếu provenance phải loại theo luật đăng ký và công bố
  mẫu số. Thiếu dữ liệu khiến phạm vi validation không khả thi thì BLOCKED,
  không dùng model toàn 2022 cho fold sớm để lấy PASS. W7 mới chọn ứng viên
  bằng validation hiệu quả, gồm development 2023 và các lượt API cần thiết.

#### W6-15 — Hồi quy, leakage, fault/resume và hiệu năng

- **Làm:** kiểm thay đổi feature/scaler/source giữa run, corrupted evidence,
  crash từng stage, malformed Decision, quota/cooldown/unknown, lock và atomic
  write. Chạy bốn gate kỹ thuật; kiểm Original/v1 không đổi hành vi.
- **Hiệu năng:** đo public API đầy đủ validation/deep-copy với 100 warm-up,
  1.000 mẫu mỗi mode/stage, p95 nearest-rank, cùng context/scope với baseline
  khi so v1. V2 thêm query đã đăng ký; báo riêng retrieval/prefix/kết hợp và
  chi phí nạp index/fit. Nếu tính feature/transform trước API retrieval, báo
  riêng phần đó và tổng đường query, không giấu chi phí vào bước chuẩn bị.
  Không cache đáp án hoặc bỏ outlier để đạt ngưỡng.
- **Đạt khi:** retrieval p95<30 ms, không I/O hot query; caps/JSON/PIT/paired/
  semantic/fault PASS; nguồn đóng băng nguyên byte. Máy quá tải phải ghi cả
  lượt đo và điều kiện đo lại, không sửa ngưỡng. Nếu FAIL thì chưa mở Gate D.

#### W6-16 — Chốt W6 và bàn giao validation W7

- **Làm:** cập nhật checklist/plan tổng, module/config đã có, giới hạn còn
  lại, danh sách ứng viên đã đăng ký và đường artifact/fold. Soạn lệnh đúng
  CLI thực tế cho prepare/dry-run/preflight/run/verify/resume từng mã để người
  dùng tự chạy phần API khi đủ điều kiện W7.
- **Đầu ra:** README này làm sổ bàn giao; không thêm receipt lặp lại. Giữ
  các kết quả không thuận lợi, quyết định hoãn risk policy và lỗi còn mở.
- **Đạt khi:** 01–15 DONE, Gate A/B/C và bốn gate kỹ thuật PASS; code v2 có
  trên luồng chính, train PIT kiểm được và bàn giao đủ, chưa chọn theo holdout.
  Đánh DONE task 16 để đóng **16/16 và Gate D**. W7 tiếp nhận validation/chọn
  ứng viên/khóa ma trận; W8 mới benchmark.

**Điều kiện Gate D (chưa nghiệm thu):** 13–16 DONE; đủ bằng chứng kỹ thuật và dữ liệu cho W7. Không dùng
smoke v1, fixture v2 hoặc kết quả chọn ứng viên làm bằng chứng thắng OOS.

## 4. Quản lý thay đổi và kiểm thử

Module dự kiến kế thừa: `core/bayesian_retriever.py`, `core/prior_evidence_v2.py`,
`core/research_cohort.py`, `core/research_input_lock.py`, `core/research_metrics.py`,
`core/prior_checkpoint.py`, `core/prior_stage_journal.py`, các builder Decision
và `scripts/run_bayesian_ablation.py`. Tên module feature/index mới chốt ở
01–03; không mở thêm runner độc lập nếu CLI hiện hữu có thể mở rộng rõ ràng.

Mỗi task dùng nhánh riêng từ `develop`; commit Conventional Commits theo
nội dung kỹ thuật, không có ký hiệu tuần. Trước merge chạy:

```powershell
py -3.13 -m compileall agents core data_manager scripts tests utils
py -3.13 -X utf8 -m unittest discover -s tests -v
py -3.13 scripts/run_end_to_end_test.py
py -3.13 -X utf8 -m unittest discover -s tests -p "test_*leakage.py" -v
```

Không đưa secret, response runtime hoặc toàn bộ index vào Git. Artifact
mới cần loader/schema/checksum và nơi lưu rõ ràng; thêm gitignore khi producer
được triển khai. Không sửa manifest lịch sử để nhận phiên bản mới.

## 5. Nhật ký tiến độ

Kết thúc task: cập nhật checkbox và một dòng kết quả/cách kiểm/việc còn vướng.
Dùng TODO, IN_PROGRESS, BLOCKED, DONE; PLAN_READY chưa phải triển khai DONE.

| Ngày | Phạm vi | Kết quả | Bước tiếp theo |
| --- | --- | --- | --- |
| 10/10/2026 | Lập kế hoạch W6 | PLAN_READY; 4 phase, 16 task, 0/16 triển khai. Kế thừa W5, thêm gate provenance theo fold và giới hạn danh sách ứng viên. Kiểm thay đổi tài liệu: compileall/E2E, 624 unit/105 leakage PASS; checklist/liên kết hợp lệ, 122 file bảo vệ nguyên byte. Không gọi API hoặc thay code/nguồn; các gate triển khai W6 chưa nghiệm thu | W6-01 |
| 10/10/2026 | W6-01 | DONE; 1/16 task. Input 128/128, smoke 4/4–20 Decision, report dựng lại/reconcile PASS offline; lock 46 nguồn/46 code/23 runtime, bốn child identity và code commit `0286119` khớp. Ghi bản đồ caller/API hiện có, điểm cần version hóa và cách tái lập checkout W5. Compileall/E2E, 624 unit/105 leakage PASS; 122 file nguyên byte, audit input/smoke 0 credential/network. Chỉ sửa tài liệu chính, không API hoặc receipt mới; Gate A chưa nghiệm thu | W6-02: audit nguồn feature và tính nhân quả theo fold |
