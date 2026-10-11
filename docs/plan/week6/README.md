# Tuần 6 — Cải thiện retrieval và cách Decision sử dụng bằng chứng

**Trạng thái: Phase A/B DONE, Gate A/B PASS; Phase C IN_PROGRESS, W6-01–11 DONE, 11/16 task hoàn thành.** Ngày lập: **10/10/2026**; cập nhật: **11/10/2026**. Tiếp theo **W6-12**.
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
| A | W6-02 | Audit dữ liệu feature và tính nhân quả theo fold | 01 | [x] |
| A | W6-03 | Chốt hợp đồng feature/ranking/thống kê | 02 | [x] |
| A | W6-04 | Đăng ký ứng viên, ablation và tiêu chí đánh giá | 03 | [x] |
| B | W6-05 | Bộ trích xuất đặc trưng giá PIT | Gate A | [x] DONE |
| B | W6-06 | Scaler theo train/fold và auxiliary index | 05 | [x] DONE |
| B | W6-07 | Similarity kết hợp tín hiệu và giá | 06 | [x] DONE |
| B | W6-08 | Recency, đa dạng ví dụ và trace lựa chọn | 07 | [x] DONE |
| C | W6-09 | Thống kê điều kiện và shrink có kiểm chứng | Gate B | [x] DONE |
| C | W6-10 | Quality gate theo support/uncertainty | 09 | [x] DONE |
| C | W6-11 | Prompt/Decision contract và ablation nội dung | 10 | [x] DONE |
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
Tại mốc bàn giao W6-01, code chưa cung cấp feature giá/scaler/auxiliary index, trọng số
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

##### Kết quả audit — DONE, 11/10/2026

**Nguồn giá đủ cho triển khai feature PIT hồi cứu.** Bốn bộ giá VCI thô
`data/execution_prices/` đều có **1.251 phiên, 02/01/2018–30/12/2022**,
khớp lịch VNINDEX; checksum CSV/evidence/events và phép dựng lại trường thô
PASS. Prefix train của `data/execution_prices_oos/` bằng bộ train. Giá
provider là VND, loader chia 1.000 đúng một lần; agent/feature dùng nghìn
VND, volume là số cổ phiếu, VNINDEX là điểm. CSV cổ phiếu W1 trong
`data/historical/` chưa xác minh cơ sở điều chỉnh, **không dùng thay nguồn
feature/nhãn thô**. VNINDEX W1 vẫn là nguồn HMM riêng, có bốn sửa nến KBS
được manifest ghi nhận; metadata model giữ `RESEARCH_ONLY/UNVERIFIED`.

| Mã | Episode 2020 / 2021 / 2022 | Tổng | Lookback chứa mốc quyền/tham chiếu: 20 / 50 / 200 phiên |
| --- | ---: | ---: | ---: |
| FPT | 51 / 81 / 79 | 211 | 45 / 111 / 211 |
| MWG | 50 / 82 / 81 | 213 | 39 / 99 / 213 |
| VCB | 50 / 83 / 82 | 215 | 13 / 33 / 166 |
| VNM | 50 / 83 / 80 | 213 | 45 / 115 / 213 |

Các episode có ID/ngày nối đúng journal, snapshot dài **600–1.248 phiên**,
đủ lookback 20/50/200/600 về số hàng; 45 phiên hiển thị và 600 phiên Alpha
giữ nguyên. Không có episode 2018–2019; ngày quyết định
01/06/2020–27/12/2022, tất toán cuối 30/12/2022. Mỗi mã có hai phiên volume
0 (23–24/01/2018) trong warm-up; không đổi thành volume giả hoặc bỏ ngày.

Đếm mốc bằng `corporate_action_barriers` trên **(đầu lookback, cutoff]**,
gồm ex-right và chênh Reference/Close trước đó: đây là cảnh báo cơ sở giá,
chưa là số feature bị loại. Gate nhãn chỉ loại quyền trong `(entry, exit]`
và không bảo đảm lookback tín hiệu liên tục. **W6-03 phải chốt xử lý mốc đã
xảy ra, coverage/reason và zero-volume trước extractor**; W6-05 kiểm cùng
chính sách cho episode/query. Không dùng chuỗi điều chỉnh hồi tố hoặc quyền
sau cutoff để sửa feature, không âm thầm nối lại cửa sổ sau khi bỏ phiên.

##### Ma trận cutoff và provenance có thể tái sử dụng

| Phạm vi | Nguồn hợp lệ | Điều kiện và phần còn cần chuẩn bị |
| --- | --- | --- |
| Warm-up 2018–05/2020 | OHLCV thô và VNINDEX prefix | Không có prior episode; chưa dùng làm validation hiệu quả |
| Replay 852 query 2020–2022 | 852 signal checkpoint + 852 episode, 217 HMM prefix | HMM/scaler/mapping/calibration kết thúc đúng ngày query; giá/Alpha/tin ≤query. Chỉ prior có exit<query; không dùng model toàn 2022 |
| Fold dự kiến 2021 | Prefix bank đã tất toán trước 04/01/2021; query 04/01–31/12/2021 | **197 fit / 329 query**, purge 4 cycle exit=04/01; exit cuối fit 29/12/2020. Fit theo mã FPT/MWG/VCB/VNM: 50/49/49/49 |
| Fold dự kiến 2022 | Prefix bank đã tất toán trước 06/01/2022; query 06/01–27/12/2022 | **526 fit / 322 query**, purge 4 cycle exit=06/01; exit cuối fit 31/12/2021. Fit theo mã: 131/131/132/132 |
| Development 2023 / holdout 2024 | Giá OOS đã khóa; HMM toàn train kết thúc 30/12/2022, freeze 31/12/2022 | Dùng proof train-only hồi cứu hiện có; scaler feature/index/config W6 cần phiên bản mới. Không đọc outcome OOS để chọn tham số tại task này |

Hai fold theo năm là **phạm vi dự kiến để đăng ký ở 03–04**, không phải
report validation đã chạy. 201 episode 2020 làm bootstrap, 651 query
2021–2022 làm chẩn đoán train; không gọi 852 điểm replay là 852 mẫu validation
độc lập. Purge theo ngày exit thực tế, equality bị loại; bốn cycle bị purge
ở mỗi biên có thể vào prior sau khi đã exit<query, không loại vĩnh viễn.
Số fit/query là trần coverage của lịch trước gate lookback/feature ở 03;
không cam kết scaler sẽ nhận đủ số hàng đó sau khi xử lý quyền và NaN.
Trước lọc regime/quality, số prior cùng mã ở fold 2021 là FPT 50–130,
MWG 49–130, VCB 49–131, VNM 49–131; fold 2022 lần lượt 131–209,
131–211, 132–213, 133–211. Đây chưa là support nhóm điều kiện.

- **HMM hiện có:** `PrefixRegimeProvider.get(..., verify_only=True)` chỉ
  nạp artifact đúng cutoff, kiểm train hash và phân loại cuối prefix. Có
  thể giữ giao thức expanding PIT: HMM/scaler HMM/calibration dùng giá đến
  query theo luật cố định; không coi đây là HMM đóng băng ở đầu năm. Nếu
  đăng ký giao thức frozen-fold khác thì tạo artifact/proof riêng.
- **Alpha hiện có:** cấu hình chung 852 checkpoint khớp run gốc: window=45,
  `zscore_tanh`, `alpha_weights=None` → trọng số IC/accuracy/Sharpe
  0,40/0,35/0,25; top 5 tuyển lại trên 600 nến ≤query, nhãn tuyển chọn ba
  phiên cuối chưa đóng là NaN. Đây là adaptation theo prefix, không phải
  danh sách Alpha đã fit hết 2022 rồi áp ngược về 2020. Normalization dùng
  toàn cửa sổ hiện biết; metric tuyển chọn là diagnostic trong cửa sổ,
  **không là hiệu quả walk-forward của Alpha**, không dùng làm feature PIT
  cho từng hàng quá khứ. Chưa có kiểm barrier quyền trong metric Alpha;
  giữ hạn chế đối chứng này, thay đổi selector cần protocol/bank mới.
- **Báo cáo:** extractor cắt giá/tin trước upstream, không truyền regime
  vào Indicator/Pattern/Trend/Alpha; báo cáo đã lưu không phụ thuộc HMM
  toàn train. Đường `PriorContextAdapter.prepare` →
  `load_shared_checkpoint` có thể kiểm/replay cùng cấu hình nguồn gốc.
  Nếu đổi window, Alpha, giá, model/prompt hoặc thêm đầu vào regime thì
  phải tạo report/episode mới với identity riêng; không chỉ đổi regime
  trong bank rồi gọi đó là sửa leakage. Phần dùng API do người dùng chạy.
- **Artifact còn thiếu, thuộc 05–06/12/14:** extractor feature, scaler
  feature riêng từng fold fit từ prefix eligible, auxiliary index gắn ID,
  fold/config/hyperprior provenance và harness. Không lấy scaler HMM năm
  2022 làm scaler feature cho fold sớm. Với scaler/hyperprior cần nhãn,
  fit chỉ dùng exit<first query; adaptation trong fold phải đăng ký rõ.

##### Cách kiểm và giới hạn diễn giải

Audit W2 nguyên bản tại commit **`f743b94`** (20/20 code hash khớp run)
PASS **852/852**, lịch 868 ứng viên/16 loại, nhãn engine và provenance.
Verifier W2 trên code hiện tại dừng đúng vì **8/20 file code đã đổi**;
dữ liệu/lịch/config/runtime vẫn khớp, không sửa fingerprint để ép PASS.
Tái lập bằng checkout mốc này, runtime đã ghim và staging/bank nguyên byte,
theo cách checkout độc lập ở W6-01. Khi chạy CLI audit, truyền `--run-dir`
và `--bank` đến bản gốc, `--output` đến thư mục tạm; không ghi đè QA W2.

Artifact không ghi timestamp freeze từ năm 2020; cấu hình/code và LLM được
đóng băng cho nghiên cứu hồi cứu năm 2026. Giá cũng tải hồi cứu, không có
vintage mỗi ngày; không chứng nhận cấu hình đã tồn tại hay provider/LLM
chưa biết tương lai vào năm giao dịch. Phạm vi có thể kiểm là **PIT theo
dữ liệu cấp cho thuật toán**, chưa là backtest triển khai thực tại thời điểm
lịch sử. 0/852 tin reliable vẫn là thiếu dữ liệu, không là sentiment thị
trường trung tính. Không dùng fixture/mock để bù các hạn chế này.

Replay qua adapter production **852/852 PASS**, không gọi lại upstream;
15 file code và cấu hình/runtime tín hiệu đồng nhất trong toàn bộ checkpoint.
**217/217** artifact prefix hợp lệ: 165 HMM, 52 fallback MULTI_FACTOR theo
luật đã khóa. Mean/variance/scale tái tính bằng StandardScaler trên đúng
feature prefix khớp cả 217 artifact (rtol/atol 1e-12), không refit HMM.
Tái tính đủ năm Alpha tại **16 điểm** (đầu/cuối kho, đầu 2021/2022 của bốn
mã) khớp giá trị/hướng/metric đã lưu; **4/4** ca sửa giá sau cutoff không
đổi kết quả. Các audit có guard credential/network: **0 attempt**.

Có thể kiểm lại đường replay hiện tại từ root, không tạo receipt:

```powershell
@'
import json
from pathlib import Path
from core.prior_context import PriorContextAdapter
adapter = PriorContextAdapter({"enable_bayesian_prior": True})
records = json.loads(Path("data_manager/regime_memory_store.json").read_text("utf-8"))
for record in records:
    point = adapter.prepare(record["symbol"], record["as_of_date"])
    shared = point.load_shared_checkpoint("outputs/historical_memory_run")
    assert shared["current_signals"] == record["agent_signals"]
    assert shared["market_regime"]["regime_name"] == record["regime"]
print(f"Replay PASS: {len(records)} checkpoint")
'@ | py -3.13 -X utf8 -
```

Compileall/E2E, **624 unit và 105 test leakage PASS**, không skip;
**2.281 file bảo vệ nguyên byte**, code production/test không đổi. Chỉ
cập nhật ba Markdown chính; kết quả audit/log tạm ở TEMP, không tạo receipt
trong repo hoặc gọi API.
**Kết luận:** nguồn/proof đủ cho phạm vi triển khai PIT hồi cứu; chưa
nghiệm thu harness/validation hay feature scaler chưa viết. Gate A còn
chờ 03–04 chốt chính sách quyền, phạm vi và đăng ký cấu hình.

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

##### Hợp đồng đã chốt — DONE, 11/10/2026

Đây là đặc tả đã chốt để triển khai ở 05–12; kết quả code/kiểm thử được ghi
tại từng task, **chốt hợp đồng chưa là validation hiệu quả**. C0 giữ nguyên công thức/version W5; C1 thay retrieval với hồ sơ
tương thích W5, C2/C3 dùng thống kê điều kiện/gate tách bên dưới. Bảng W6-04
ghi bộ version chính xác cho từng ứng viên và ngưỡng trước thực nghiệm;
không điều chỉnh công thức theo outcome development/holdout.

**1. Feature `pit_price_features_v1` và chính sách `raw_segment_21_v1`.**
Mỗi episode dùng giá tại chính `as_of_date` của episode; query dùng cutoff
query. Cắt nguồn đã xác minh xuống ≤cutoff **trước** rolling/kiểm quyền.
Gọi `C_0,…,C_20` là 21 Close liên tiếp trên lịch VNINDEX, `C_20` đúng cutoff,
`r_j = ln(C_j/C_(j−1))`, j=1…20. Thứ tự vector cố định:

| Feature | Công thức | Đơn vị |
| --- | --- | --- |
| `momentum_5` | `C_20/C_15 − 1` | Tỷ lệ thập phân, 0,05 = 5% |
| `momentum_20` | `C_20/C_0 − 1` | Tỷ lệ thập phân |
| `volatility_20` | `sqrt(mean((r_j − mean(r))²))`, ddof=0 | Log-return mỗi phiên; không annualize |
| `ma_distance_20` | `C_20/mean(C_1,…,C_20) − 1` | Tỷ lệ thập phân |

Không MA200, giá tuyệt đối, volume, nhãn, P&L hoặc tin thiếu vào vector.
Giá nghìn VND theo loader hiện hữu; đổi đồng loạt VND↔nghìn VND không đổi
feature trong sai số tuyệt đối 1e−12. Không tự đoán/chia lại đơn vị khi nạp.
Giữ nguyên phiên volume=0 và báo `zero_volume_count`; nó không tham gia
công thức, không chứng nhận giá đó có thể khớp lệnh. Gate giá thực thi riêng
vẫn giữ nguyên cho nhãn/evaluator.

- Đủ **21 phiên liên tiếp**, không bỏ hàng rồi nối cửa sổ. Thiếu đầu lịch sử:
  `INSUFFICIENT_HISTORY`; thiếu phiên/cutoff: `MISSING_SESSION`/`MISSING_CUTOFF`.
  Không nội suy, forward-fill, bù bằng mã khác hoặc dùng một phần vector.
- Dùng union mốc của `corporate_action_barriers` đã xảy ra ≤cutoff: ngày
  ex-right và `abs(Reference[t]−Close[t−1]) > 0,00001` nghìn VND.
  Có mốc trong **(ngày C_0, cutoff]** → `CORPORATE_ACTION_WINDOW` và vector
  `null`. Mốc đúng C_0 được phép vì mọi giá dùng đều từ cơ sở sau mốc;
  mốc đúng cutoff bị loại. Không dùng quyền tương lai hoặc điều chỉnh hồi tố.
- Các trường hợp coverage trên trả `UNAVAILABLE`, vector `null`, reason và
  khoảng ngày/số phiên thực có. Hash/đơn vị/nguồn sai, ngày trùng/đảo,
  giá OHLC/Reference không hữu hạn hoặc không dương, NaN trong nguồn có hàng,
  volume sai hay kết quả tính không hữu hạn → `ValueError`; không chuyển
  lỗi nguồn thành coverage thấp. Mốc/số phiên phụ trợ không vào vector.

Kiểm coverage bằng lịch/ngày và barrier trên train, không đọc lợi nhuận:

| Mã | Feature hợp lệ / tổng episode | Thiếu do barrier | Fit hợp lệ fold 2021 / 2022 |
| --- | ---: | ---: | ---: |
| FPT | 160 / 211 | 51 | 41 / 101 |
| MWG | 172 / 213 | 41 | 42 / 104 |
| VCB | 201 / 215 | 14 | 47 / 123 |
| VNM | 166 / 213 | 47 | 36 / 100 |

Tổng **699/852** có feature, **153** thiếu do barrier; hai tập fit có
**166/428** hàng hợp lệ. Khác audit cửa sổ 20 hàng ở 02 vì momentum/volatility
20 lợi suất cần **21 giá**. Đây là coverage đầu vào, chưa là số ví dụ đủ
regime/similarity/gate. Episode thiếu feature vẫn giữ trong bank và population
thống kê nếu đủ PIT; không loại khỏi mẫu đánh giá để làm đẹp kết quả.

**2. Scaler `symbol_fold_standard_v1`, index `episode_price_index_v1`.**
Fit riêng từng mã, gộp mọi regime, trên feature hợp lệ của episode đã đóng
`exit_date < first_query_date` của fold. Fold 2021 bắt đầu 04/01/2021,
fold 2022 bắt đầu 06/01/2022; 2020 chỉ bootstrap. Mỗi mã cần ≥2 hàng fit;
không đủ → `SCALER_UNAVAILABLE`, không mượn fold/mã khác. Với từng chiều,
`mu=mean(x)`, `variance=mean((x−mu)²)`, `scale=sqrt(variance)` nếu variance>0,
ngược lại scale=1 và ghi `zero_variance=true`; `z=(x−mu)/scale`. Giữ đủ bốn
chiều, không clipping/refit vì query lệch phân phối. Giá cố định cho vector
0, volatility=0 hợp lệ; chiều cố định lúc fit vẫn có thể khác ở query.

Scaler đóng băng suốt fold; không thêm query hoặc episode mới đóng vào fit.
OOS dùng scaler fit trên episode hợp lệ có exit≤30/12/2022, đóng băng
31/12/2022, không refit bằng 2023/2024. HMM/scaler HMM giữ giao thức riêng:
prefix expanding đúng cutoff trong train, model train đóng băng cho OOS.
Thống kê ở mục 4 là expanding PIT theo công thức cố định, không gọi đó là
hyperprior đã đóng băng đầu fold.

Index phụ lưu vector **chưa scale** theo episode ID và cutoff của episode;
cả query lẫn prior được transform bằng **cùng scaler của fold query**.
Không sửa bank, không fit mỗi episode, không lấy vector của episode tại ngày
query. Index có thể chứa các episode về sau, nhưng retrieval phải lọc
exit<query trước ranking/statistics; fit scaler cũng chỉ nhận prefix hợp lệ.
Nạp/kiểm hash/semantic nguồn một lần trước vòng query, cache theo identity;
hot query không I/O/fit. Thiếu ID, ID trùng, sai vector/source hoặc dùng scaler
sai fold ném lỗi; `UNAVAILABLE` có reason đã xác minh là trạng thái khác.
`SCALER_UNAVAILABLE` phải có proof fit<2 hàng; thiếu artifact bắt buộc hoặc
không kiểm được fit provenance là lỗi hệ thống, không là coverage thấp.

**3. Ranking `signal_price_recency_v1`, diversity `session_gap_v1`.**
Lọc same_symbol, cùng regime và exit<query trước tính score. Giữ chuẩn hóa
bốn trường v1: trend, pattern, alpha_consensus, indicator_consensus. Sentiment
không tham gia metric này; tin thiếu không được diễn giải là bằng chứng trung
tính của thị trường. Trường thiếu/giá trị ngoài vocabulary là lỗi.
Với query/prior đều có feature và scaler hợp lệ:

```text
S = số trường tín hiệu bằng nhau / 4
d = sqrt(mean((z_prior − z_query)²))         # bốn chiều
P = 1 / (1 + d)
base_score = w_signal*S + (1 − w_signal)*P
age_days = (query_date − prior.as_of_date).days
exit_age_days = (query_date − prior.exit_date).days
recency = 2 ** (−age_days / half_life_days)
rank_score = base_score * recency
```

Mốc cấu hình phương pháp: `w_signal=0,5`, `half_life_days=365`,
`max_prior_age_days=730`, `min_gap_sessions=5`, K≤3, seed=42. Tất cả là
tham số có hash; 04 đăng ký chúng cùng ngưỡng `min_similarity` trước chạy,
chưa là tối ưu thực nghiệm. Lọc tuổi `age_days≤max_prior_age_days` và
`base_score≥min_similarity` (không áp ngưỡng lên score đã nhân recency).
Tuổi tính bằng ngày lịch từ ngày ra tín hiệu, không từ ngày load/cache;
exit_age chỉ chẩn đoán, luôn >0. Không làm tròn trước so sánh.

Sắp `rank_score` giảm → `exit_date` giảm → `episode_id` tăng. Duyệt thứ tự
này, giữ ứng viên nếu khoảng cách **chỉ số phiên trên cùng lịch VNINDEX**
giữa ngày ra tín hiệu của nó và từng ví dụ đã giữ ≥5, đến khi đủ K hoặc hết
tập. Equality ở ngưỡng được nhận, không thêm ngẫu nhiên để bù K; K_eff≤K.
Trace gồm S/d/P/base/age/recency/rank, ID giữ/loại và reason. Filter feature,
similarity, tuổi và diversity chỉ tác động examples; không đổi population
thống kê. Hoán vị WIN/LOSS/net-return của prior không đổi scaler, score,
thứ tự hoặc IDs; chỉ phần thống kê/nội dung nhãn sau chọn được thay đổi.

**4. Thống kê `conditional_disjoint_beta_v1`.**
Định nghĩa các tập bằng ID duy nhất, tính lại tại mỗi query từ lịch sử đã đóng:

- **P:** toàn bộ same_symbol, same_regime, exit<query. Không lọc theo K,
  feature, tuổi, khoảng cách, diversity hoặc outcome.
- **C:** phần P có **đúng cả bốn tín hiệu** bằng query theo vocabulary v1.
  Tín hiệu xung đột vẫn là một tuple hợp lệ; không gộp các tuple chỉ vì
  chúng có cùng số trường khớp. **B=P\C**, C∩B=∅, |P|=|C|+|B|.
- Với từng metric, áp mask mẫu số xuống P/C/B **trước** đếm success.
  Một episode góp tối đa một quan sát cho từng metric; không cộng support
  của bốn metric hoặc của hai agent thành cỡ mẫu mới.

| Metric | Mask mẫu số | Success |
| --- | --- | --- |
| `win_rate_long` | Mọi episode trong tập | `WIN_IF_LONG` |
| `bull_trap_rate` | Trend bullish **hoặc** Pattern bullish, union một lần | `LOSS_IF_LONG` |
| `trend_false_bullish_rate` | Trend bullish | `LOSS_IF_LONG` |
| `pattern_false_bullish_rate` | Pattern bullish | `LOSS_IF_LONG` |

Dùng `is_bullish`/nhãn đã xác minh hiện hữu; không tái định nghĩa break-even
hoặc bull trap. Ghi raw success/support/rate riêng cho P, C, B; mẫu số 0
trả rate=null. Các tỷ lệ là lịch sử theo hợp đồng LONG có phí, không phải
expected net return hoặc xác suất query/LLM đã được hiệu chuẩn.

Với mỗi metric, gọi `(s_C,n_C)` và `(s_B,n_B)` là counts sau mask:

```text
p_background = (s_B + 1) / (n_B + 2)
alpha_prior = shrink_strength * p_background
beta_prior = shrink_strength * (1 − p_background)
alpha_post = alpha_prior + s_C
beta_post = beta_prior + n_C − s_C
mean_post = alpha_post / (alpha_post + beta_post)
CrI95 = [Beta.ppf(0.025, alpha_post, beta_post),
         Beta.ppf(0.975, alpha_post, beta_post)]
```

`shrink_strength=4` là mốc phương pháp hữu hạn/dương, ghi vào config;
04 đăng ký cùng các tham số trên. Background là phần bù của nhóm điều kiện,
**không dùng counts của P rồi cộng C lần nữa**. Counts B ước lượng mean
hyperprior, chuyển thành đúng bốn pseudo-observation, không cộng thêm n_B
vào likelihood. n_B=0 → p_background=0,5, prior Beta(2,2),
`FIXED_SYMMETRIC_PRIOR`; n_C=0 → `NO_CONDITIONAL_HISTORY`, posterior/interval
đưa ra evidence=null, không coi pseudo-support là quan sát hoặc tự đổi C.
Counts nguồn vẫn đủ để kiểm chứng. n_C=1 hoặc chỉ có một lớp vẫn tính nếu
nguồn hợp lệ, readiness phải xét support/width đã đăng ký.

Đây là **empirical Bayes với background PIT**, khoảng Beta là khoảng
plug-in có điều kiện trên hyperprior đã ước lượng: không bao hàm sai số
ước lượng background, phụ thuộc thời gian giữa cycle hoặc sai số regime.
Không gọi nó là chứng nhận coverage tần suất 95%/khoảng dự báo lợi nhuận.
Các metric được shrink riêng theo background sau mask; bốn posterior không
là một phân phối chung để cộng/nhân thành xác suất hay điểm giao dịch.
Outcome chỉ đọc sau lọc PIT để đếm thống kê/hiển thị ví dụ; query outcome
không có trong API feature/scaler/ranking/statistics/prompt.

**5. Readiness, version và provenance.** Dùng evidence
`prior_evidence_v3`, gate `split_quality_gate_v2`, prefix `compact_brpp_v3`
cho C2/C3; C1 dùng hồ sơ tương thích ở 04. Tên nhánh ứng viên vẫn
`bayesian_v2`. C0 giữ evidence v2,
statistics `regime_beta_binomial_v2`, gate/prefix W5. Không đổi ý nghĩa
artifact có version cũ. Ghi toàn bộ feature/price-policy/scaler/index/
ranking/diversity/statistics/evidence/gate/prefix version ở trên, config
hash và code/runtime identity; bank/manifest/CSV/events/calendar hash;
query/episode cutoff; fold ID, sorted fit IDs/hash/count, max fit exit,
mu/variance/scale/zero-mask và scaler/index hash; regime proof/model hash.
Identity mới phải tách checkpoint/cache, không resume lẫn protocol.

- `stats_ready` theo từng metric: support C≥`min_conditional_count` và
  CrI width≤`max_interval_width`, đồng thời |P|≥`min_population_count`.
  Stats block READY nếu có ít nhất một metric ready; metric thiếu/không
  đạt ghi N/A/reason, không đưa posterior không đạt vào prompt như đã đạt.
- `examples_ready`: |P|≥`min_population_count`, feature/scaler hợp lệ và
  sau similarity/age/diversity còn ≥1 ví dụ. Không bắt buộc stats_ready.
  Feature query `UNAVAILABLE` hoặc fit scaler<2 hàng có proof → examples
  off có reason; stats vẫn xét counts độc lập. K_eff=0 do coverage không
  tự tắt `stats_only`; artifact thiếu/sai luôn ném lỗi như mục2.
- Prior disabled hoặc **K=0 là tắt toàn prior** theo giao thức hiện hữu;
  `stats_only` dùng requested_K>0 nhưng bỏ examples khi dựng prefix.
  `full_prior` dùng từng block ready, `examples_only` chỉ examples,
  `stats_only` chỉ stats; không block nào phù hợp → prefix rỗng/Original.
  Threshold fields trên phải có số cụ thể trong registry 04 trước code/run;
  không lấy posterior_mean>0,5 làm gate hoặc tự đổi action. Lỗi integrity/
  leakage luôn ném lỗi, không fallback Original như thiếu support.
- Prefix≤600 ký tự và prompt<6.500: trình bày block theo template version,
  ghi rõ support/mean/khoảng của tỷ lệ lịch sử; không lộ query outcome.
  Kiểm trần trước gọi LLM, không âm thầm cắt counts/interval hoặc đổi K.
  Template/trace/boundary gates phải được test ở 10–12; task này chưa
  nghiệm thu khả năng tất cả block vừa trần hoặc JSON schema runtime.

**6. Ví dụ tính tay và ca biên cho triển khai.**

- 21 Close gồm 20 giá 100 và cuối 110: momentum5=momentum20=0,1;
  r gồm 19 số 0 và ln(1,1), volatility=`ln(1,1)*sqrt(19)/20`
  ≈0,0207723721; MA20=100,5, distance=19/201≈0,0945273632.
  Giá cố định → cả bốn feature=0; nhân tất cả giá 1.000 giữ kết quả.
- Scaler chiều có fit [1,3] → mu=2, variance=1, scale=1, query4→z=2.
  Fit [2,2] → variance=0, scale=1, query3→z=1; không chia 0 hoặc bỏ chiều.
- Khớp 3/4 tín hiệu và chênh z=[1,0,0,0] → S=0,75, d=0,5,
  P=2/3, base=17/24. Tuổi365, half-life365 → rank=17/48≈0,3541667.
  Tuổi730 nhận nếu đủ similarity;731 loại. Hai ngày cách4 phiên loại
  khi xét diversity, cách5 nhận. Score bằng nhau dùng exit rồi ID.
- Metric win: C có3 WIN/4, B có8 WIN/20 → p_background=9/22,
  prior Beta(18/11,26/11), posterior Beta(51/11,37/11), mean=51/88
  ≈0,579545; CrI95≈[0,249194;0,872546]. Raw C=0,75; raw P=11/24.
  n_C+n_B=24, không dùng raw P làm background rồi cộng C. Query tuple
  Trend bullish/Pattern bearish → pattern denominator C=0 và N/A;
  Trend và Pattern cùng bullish vẫn chỉ một quan sát trong bull-trap union.
- Thiếu1 phiên, thiếu cutoff, chưa đủ21, barrier ở C_0/cutoff, volume0,
  NaN, giá sai đơn vị và scaler thiếu/sai fold xử lý đúng mục1–2.
  exit=query bị loại; exit trướcquery nhận. Thêm/sửa giá, quyền, episode
  **sau cutoff** không đổi kết quả PIT; outcome prior hoán vị chỉ đổi stats.
  Không có P/C/B, chỉ1 prior, tuple xung đột, zero variance và đảo thứ tự
  nguồn phải có oracle/boundary test ở các task triển khai tương ứng.

**Kiểm chứng task:** đã đối chiếu coverage 699/852 và fit166/428 bằng
nguồn train đã xác minh; **17 đối chiếu công thức PASS** bằng NumPy/SciPy
độc lập, chưa là test implementation mới. Compileall/E2E, **624 unit và
105 test leakage PASS**, không skip. Bốn gate giới hạn BLAS/OpenMP/NumExpr
một luồng riêng trong tiến trình kiểm thử; chưa đo lại p95. **2.281 file bảo
vệ nguyên byte**, code production/test không đổi. Không đọc outcome OOS,
không gọi API, không thêm schema/config chưa có consumer; chỉ sửa ba Markdown
chính, log/đối chiếu số học ở TEMP.
Trạng thái tại mốc 03: Gate A **chưa nghiệm thu**, chờ 04 đăng ký ứng viên và ngưỡng.

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

##### Registry đã đăng ký — DONE, 11/10/2026

**`prior_candidate_registry_v1`**, đăng ký trước implementation/thực nghiệm
mới. Bảng này là nguồn phương pháp; 12 mới xuất config runtime đầy đủ,
validator và hash, không thêm JSON chưa có mã đọc ở task 04.

| Candidate ID | Nội dung | So sánh kiểm soát / giả thuyết |
| --- | --- | --- |
| `C0` | Evidence/prefix/Decision W5, `full_prior` | C0–Original: mốc Bayesian v2 W5 với quality gate, giữ cả kết quả bất lợi |
| `C1` | C0 + feature/scaler/ranking giá, recency và diversity của 03 | C1–C0: nhóm thay đổi retrieval có tạo ví dụ phù hợp hơn không; chưa tách tác động từng thành phần |
| `C2` | Retrieval C1 + conditional shrink, split gate, prefix thống kê mới; reasoning Decision W5 | C2–C1: nhóm thay đổi statistics/gate/cách ghi counts có ích không; chưa quy riêng lợi ích cho shrink |
| `C3` | C2 + contract Decision đối chiếu prior và trace sử dụng, `full_prior` | C3–C2: contract sử dụng prior có cải thiện quyết định không, gồm tác động schema/instruction mới |
| `C3_stats_only` | C3, chỉ đưa stats ready vào prompt | C3–C3_stats_only: tác động thêm examples khi stats được giữ nguyên |
| `C3_examples_only` | C3, chỉ đưa examples ready vào prompt | C3–C3_examples_only: tác động thêm stats khi examples được giữ nguyên |

Đúng **6 cấu hình**, cùng family `bayesian_v2`, phân biệt bằng candidate ID
và config hash. Năm nhánh v1 `original/random/recent/similarity/bayesian`
giữ riêng, không tính vào sáu cấu hình hoặc coi `bayesian` v1 là C0.
Thứ tự nhánh cố định: năm v1 theo thứ tự trên → C0 → C1 → C2 → C3 →
C3_stats_only → C3_examples_only. Báo thứ tự/thời điểm gọi; không quy mọi
khác biệt từ một lượt LLM thành hiệu ứng nhân quả riêng của thành phần.

**Cấu hình đầy đủ về phương pháp.** Mọi trường dưới là giá trị bắt buộc,
không cho `.env` hoặc CLI override riêng một nhánh sau khi khóa plan.
`N/A` nghĩa là thành phần không được dùng, không tự nhận default mới.

| Trường | C0 | C1 | C2, C3 và hai ablation |
| --- | --- | --- | --- |
| `enable_bayesian_prior / requested_k / seed / scope` | true / 3 / 42 / same_symbol | Như C0 | Như C0 |
| Population | same_symbol, same_regime, exit<query | Như C0 | Như C0; C là tuple đúng cả bốn tín hiệu, B=P\C |
| Feature / scaler / index | N/A | Bốn feature, 21 giá; scaler riêng mã/fold, fit≥2, ddof=0, zero-scale=1; theo 03 | Như C1 |
| `w_signal / half_life_days / min_gap_sessions` | N/A / N/A / N/A | 0.5 / 365 / 5 | Như C1 |
| `min_similarity` | 0.75 trên S của v1 | **0.625 trên base_score** | Như C1 |
| `max_prior_age_days` | 730 ngày từ as_of_date | 730 | 730 |
| Tie-break | S giảm, exit giảm, ID tăng | rank_score giảm, exit giảm, ID tăng; greedy diversity theo 03 | Như C1 |
| `min_population_count` | 20 | 20 | 20 |
| Statistics / prior | Toàn P; Beta(1,1) + counts P | Như C0 | Nhóm C; background B, `shrink_strength=4` theo 03 |
| `min_conditional_count / max_interval_width` | N/A / N/A | N/A / N/A | **5 / 0.75** cho từng metric |
| Interval | Equal-tailed Beta 95% | Như C0 | Equal-tailed Beta plug-in 95% theo 03 |
| Gate | READY khi P≥20 và còn ví dụ quality; stats/examples bật cùng nhau | Như C0, quality theo retrieval mới | Stats và examples độc lập theo 03; so sánh ≥support, ≤width |
| `content_mode` | full_prior | full_prior | C2/C3: full_prior; hai ablation đúng hậu tố ID |
| Numeric action policy | Tắt; raw_action=executed_action theo ánh xạ SHORT=CASH | Như C0 | Như C0 |

Ngưỡng 0.625 được chọn từ `0.5×0.75 + 0.5×(1/(1+1))`: khớp 3/4
tín hiệu và RMS z-distance=1 nằm đúng biên nhận. Nó cũng có thể nhận mức
khớp tín hiệu thấp hơn nếu giá rất gần; không diễn giải thành luật bắt buộc
khớp ≥3/4. Support 5, width 0.75 và population 20 là mốc kỹ thuật hạn chế
nhóm quá ít/không chắc chắn, **chưa được chứng minh tối ưu hoặc hiệu chuẩn**.
Không sweep trọng số, cửa sổ, K, tuổi, diversity hoặc ngưỡng trong W6.

**Version và cách giữ phép so sánh.** Tên version mới là hợp đồng sẽ được
consumer triển khai, chưa là chứng nhận artifact/runtime đã tồn tại.

| Hồ sơ | Evidence / statistics | Gate / prefix | Decision |
| --- | --- | --- | --- |
| C0 | `prior_evidence_v2` / `regime_beta_binomial_v2` | `prior_quality_gate_v1` / `compact_brpp_v2` | Hồ sơ W5 `decision_legacy_v1` |
| C1 | `prior_evidence_v3` / `regime_beta_binomial_v2` | `population_coupled_gate_v1` / `compact_brpp_v2_compat` | Như C0 |
| C2 | `prior_evidence_v3` / `conditional_disjoint_beta_v1` | `split_quality_gate_v2` / `compact_brpp_v3` | Như C0, reasoning prior v2 W5 |
| C3 và hai ablation | Như C2 | Như C2; content_mode có hash riêng | `decision_prior_use_v1` khi có block prior hiển thị |

C1 giữ nguyên công thức posterior toàn P, template prefix và reasoning W5:
với cùng stats/tasks, chuỗi prefix phải bằng W5 nguyên byte. Evidence/score
validator mới nhận retrieval mới bằng version riêng; không sửa nghĩa của
schema W5 hoặc dán version cũ lên artifact mới. C2 đổi serializer để ghi
đúng n_P/n_C, support từng metric và khoảng điều kiện, giữ reasoning W5;
thay đổi layout cần thiết thuộc nhóm thay đổi C2. C3 chỉ thêm yêu cầu đối chiếu
bằng chứng và trace tự báo cáo, không ép đồng ý prior hoặc gọi thêm vòng LLM.

Ba cấu hình C3 tính **cùng base evidence**: population/counts/posterior,
ranked/selected IDs và readiness không đổi theo content_mode. Dùng chung
`base_evidence_sha256`; binding candidate/config/prompt/checkpoint có hash
riêng. Trace tách `retrieved_k`/`visible_k`, `visible_metric_ids` và
`visible_example_ids`; stats_only có visible_k=0 dù retrieved_k có thể>0.
LLM chỉ được viện dẫn thành phần đã hiển thị; trace không tự chứng minh
LLM thực sự dùng prior. Các metric không ready là N/A, không đưa posterior
không đạt vào prompt. Ablation bỏ block khỏi prompt, không âm thầm đổi pool,
K, gate hoặc bù bằng thành phần bị ẩn.

K=0/tắt prior, hoặc content_mode không có block ready → prompt và schema
Decision đúng Original; C3 không còn chỉ dẫn/field prior trong request đó.
Sidecar ghi prior không hiển thị. Mỗi candidate vẫn có Decision attempt
riêng như W5, dùng cùng Full; cùng prompt/temperature=0 chưa bảo đảm action
trùng Original. Báo bất đồng action riêng ở tập prior-off. C0/C1 gate
coupled là hồ sơ đối chứng; readiness ở mục 5 của 03 áp dụng C2/C3.

**Các đầu vào/giao thức khóa chung.** Kế thừa byte nguồn, lịch, model options
từ `outputs/bayesian_benchmark/input_lock.json` của W5, SHA-256 byte:
`a92bc3025b1e307da4554ccd1de53957f436ff2b185f86c52371c8eae8fb767d`.
Language=vi, timeframe=1d, window=45; Alpha 600 nến, zscore_tanh,
alpha_weights=None theo 02. Text `openai/gpt-oss-20b`, temperature=0,
max_tokens=2048; graph `qwen/qwen3.8-27b`, temperature=0, max_tokens=1024;
client_options lấy đúng subtree đã khóa. Đây là cấu hình lịch sử đã kiểm,
chưa kiểm khả dụng API tại ngày chạy W7. Đổi model/options phải amendment
và run identity mới trước API, không trộn model giữa các candidate.

Một upstream/Full mỗi điểm, deep-copy cho mọi nhánh; cùng báo cáo đã
distill/cap, bank 852 episode, nguồn giá/tin và economic engine. LONG t+1→t+3,
SHORT=CASH, phí/slippage hai chiều giữ nguyên. Giữ retry/pacer/ledger và
budget invocation W5, BRPP≤600, tổng prompt<6.500; kiểm caps trước request.
Identity mới ghim registry/config đã resolve, versions của 03/bảng trên,
fold/fit IDs/index/scaler/proof, model/client/runtime/code và lịch. Chuẩn
bị/verify không đọc key; API do người dùng tự chạy với lệnh thực ở 12/16.
Không sửa input lock, bank, smoke/pilot checkpoint hoặc tạo executable
plan holdout ở 04; C0 mới cũng không resume vào output W5 đã khóa.

**Phân hoạch và tiêu chí nghiệm thu.**

- **W6, Gate A:** 01–04 DONE, nguồn đủ cho phạm vi PIT hồi cứu; registry
  hữu hạn, công thức/threshold/version/comparator đã chốt. Gate B/C/D và
  lợi ích đầu tư chưa nghiệm thu. Bốn gate hồi quy phải PASS trước merge.
- **W6-14, train offline:** fold 2021 có 197 fit trước lọc feature/329 query;
  fold 2022 có 526 fit/322 query; fit feature hợp lệ 166/428 theo 03, giữ 651
  query dự kiến. HMM expanding prefix đúng query, scaler freeze theo fold,
  chỉ prior exit<query. Báo coverage feature, conditional support/width,
  readiness, score/tuổi/diversity và counts theo mã/fold/regime/candidate.
  Mock Decision chỉ kiểm luồng tích hợp, không xếp hạng return LLM. Zero coverage
  ghi NO_EXPOSURE; thiếu nguồn/proof bắt buộc làm validation không khả thi
  thì BLOCKED. Không thay ngưỡng để lấy PASS hoặc dùng full 2022 cho fold sớm.
- **W7, development:** đúng 60 điểm năm 2023 đã khóa (FPT 12, VNM/VCB/MWG 16
  mỗi mã), cùng embargo pilot/smoke của W5; không bù ngày thiếu/lỗi. W7
  chọn trong registry và khóa protocol trước 2024. Mọi chỉnh ngưỡng/candidate
  là amendment có lý do, comparator, phiên bản/config hash và thời điểm
  trước lượt chạy mới; kết quả trước/sau giữ riêng, công bố số cấu hình đã
  thử. Thêm ứng viên phải thay thế ID có ghi lịch sử để active registry≤6;
  không tuyên bố giới hạn sáu cho tổng số thử nếu đã có amendment.
- **W8, holdout:** 64 điểm 2024 (16/mã), dùng scaler/model cuối train và
  candidate/protocol W7 đã khóa; không chọn/ngắt mẫu theo return, không
  refit/tune bằng outcome 2024. Pilot 20 và smoke 4 chỉ là bằng chứng vận hành;
  development luôn thăm dò. Khả năng PIT là hồi cứu, giữ giới hạn vintage/
  kiến thức LLM đã ghi ở 02; không gọi đó là triển khai live trong quá khứ.

**Paired support và thước đo.** Báo số planned, complete, pending, failed,
unknown, prior-off, active-stats/examples của từng mã/candidate. Query thiếu
feature/support vẫn trong planned, fallback hợp lệ là điểm complete; lỗi
integrity/LLM không phải CASH. Báo global common support của toàn ma trận
và support riêng cho từng cặp so sánh; không so Δ của hai tập ngày khác
nhau, không bỏ điểm lỗi hoặc thay ngày. Primary chỉ COMPLETE khi đủ mọi
điểm đã đăng ký ở cả bốn mã cho ma trận đánh giá; partial là provisional,
không dùng để chọn/promote candidate. Report ở 12 phải tái dựng tài khoản trên
chính tập paired theo thứ tự ngày và cùng 50 triệu/mã; không lấy hai return
từ hai lịch khác nhau rồi trừ. Các ablation báo toàn cohort; phân tích chỉ
đổi nội dung dùng tập **cả stats và examples ready** để giữ contract C3
active ở cả ba nhánh. Ngoài tập đó, so sánh còn gồm tác động bật/tắt contract
do fallback; không gọi là hiệu ứng riêng của examples/stats. Tập điều kiện
sau chỉ là phân tích bổ sung, không thay primary toàn cohort.

Primary `D(c)=mean_s(R_net(c,s)−R_net(Original,s))`, đơn vị điểm phần trăm,
trung bình đều bốn mã, không giả portfolio. Báo kèm ΔR từng mã, MDD tại cuối
chu kỳ và ΔMDD, balanced accuracy (thiếu lớp=null), LONG hit-rate (không LONG
=null), số LONG/CASH, action disagreement, coverage và CASH reference.
Sharpe/Sortino chu kỳ không annualize; không cộng bốn posterior thành score.

**Quy tắc đề cử W7 đăng ký ban đầu:** chỉ xét candidate đủ gate kỹ thuật,
đủ 60 paired points và prior thực hiển thị ở ≥10% planned (≥6/60, ít nhất
một điểm mỗi mã). Đề cử cải thiện khi D>0, ΔR>0 ở≥3/4 mã và mean ΔMDD≤2
điểm phần trăm, không mã nào ΔMDD>5 (dương là drawdown xấu hơn). Đây là
ngưỡng lựa chọn phát triển, chưa là bằng chứng thống kê. Trong tập đạt,
chọn D lớn nhất; các D cách D_max không quá 1e−9 điểm phần trăm thì chọn
mean ΔMDD nhỏ hơn, sau
đó thứ tự C0,C1,C2,C3,C3_stats_only,C3_examples_only. Nếu không ai đạt,
giữ Original làm lựa chọn triển khai, báo kết quả bất lợi; W7 vẫn có thể
khóa một ứng viên nghiên cứu để kiểm W8 từ tập đủ completion/exposure trên,
xếp theo D/MDD/thứ tự ID như trên, gắn NOT_PROMOTED. Nếu tập đó rỗng thì
báo chưa đủ khả thi, chưa khóa ứng viên cải thiện. Không gọi lựa chọn này
là nâng cấp đã chứng minh. Không bắt buộc p-value
nhỏ để đóng W6; kiểm định/sensitivity và ảnh hưởng chọn nhiều ứng viên
thuộc W9, không dùng holdout để cứu kết quả development.
Nếu C0 được chọn thì giữ cấu hình W5, không gán lợi ích cho module W6 mới.
Ứng viên mới phải báo thêm Δ so với C0 và các cặp đã đăng ký để kết luận
phần nâng cấp nào có tác dụng, ngoài primary so với Original.

**Kiểm task 04:** đối chiếu C0 với defaults/formatter W5 và lock hiện có;
registry **6/6**, defaults/version C0, ngưỡng/biên số học, lock/model options
và checklist **4/16 PASS**. Compileall/E2E, **624 unit và 105 test leakage
PASS**, không skip; BLAS/OpenMP/NumExpr một luồng riêng cho các tiến trình
gate, chưa đo lại p95. **2.281 file bảo vệ nguyên byte**, production/test
không đổi. Chỉ sửa ba Markdown chính, log/đối chiếu ở TEMP; không đọc outcome
OOS, gọi API hoặc thêm schema/config chưa có consumer. Đây là kiểm đặc tả
và hồi quy hiện hữu; hành vi các profile mới còn phải kiểm ở 05–15.

**Gate A: PASS (11/10/2026), phạm vi thiết kế/PIT hồi cứu.** 01–04 DONE;
nguồn/provenance đã audit, hợp đồng và sáu cấu hình có comparator/ngưỡng/
version rõ ràng trước implementation. Chưa dùng outcome holdout để thiết kế;
feature/index/scaler/gate/prompt/CLI mới còn phải nghiệm thu ở 05–12,
validation và hồi quy/p95 ở 14–15. Không phải PASS lợi nhuận hoặc đóng W6.

### Phase B — Đặc trưng và truy xuất

#### W6-05 — Bộ trích xuất đặc trưng giá PIT

- **Làm:** extractor dùng cùng quy tắc giá cho episode/query, cắt ≤cutoff
  trước rolling; vector hóa. Trả vector, ngày dữ liệu, coverage và reason.
- **Đầu ra:** module feature dùng lại được, test tính tay/bất biến khi thêm
  nến tương lai/thiếu phiên/quyền/đơn vị; kết nối adapter hiện hành.
- **Đạt khi:** query không cần evaluator/giá thoát lệnh; future data không
  đổi vector; thiếu dữ liệu được báo theo contract, không tự điền từ tương lai.

##### Triển khai và kiểm chứng — DONE, 11/10/2026

- Module [core/pit_price_features.py](../../../core/pit_price_features.py)
  cung cấp `extract_pit_price_features(frame, events, trading_calendar,
  as_of_date, source=...)`. Episode/query gọi cùng hàm tại cutoff riêng;
  không có tham số nhãn, entry/exit hoặc evaluator. Bốn phép tính NumPy theo
  thứ tự W6-03, 21 phiên trên lịch VNINDEX; không tự đổi đơn vị giá.
- Kết quả JSON gốc có `feature_version`, `price_policy_version`,
  `feature_columns`, `vector`, `feature_end_date`, `status`, `reasons` và
  `coverage` (số phiên cần/thực có, ngày đầu/cuối, phiên thiếu, barrier,
  zero-volume). `AVAILABLE` mới có vector; `UNAVAILABLE` trả `null` cùng
  reason đã chốt. Ngày/nguồn/đơn vị/OHLCV/Reference hoặc phép tính lỗi ném
  `ValueError`; không chuyển lỗi toàn vẹn thành thiếu coverage.
- [PriorContextAdapter](../../../core/prior_context.py) có
  `price_features(symbol, as_of_date)` kiểm checksum giá/evidence/events và
  lịch đã ghim, trả thêm symbol/provenance nguồn. `PriorPointContext` gọi
  `price_features()` tại cutoff của điểm. Feature không cần seal Full,
  600 nến Alpha hay inference HMM; đủ 21 phiên là có thể tính. Hàm thuần
  chỉ xét prefix, còn adapter vẫn bảo vệ byte toàn bộ nguồn đã khóa;
  file nguồn bị sửa phải ném lỗi dù sửa ở phần tương lai.
- Kiểm thử tại [test_pit_price_features.py](../../../tests/test_pit_price_features.py)
  và [test_pit_price_features_leakage.py](../../../tests/test_pit_price_features_leakage.py):
  **28 test mới PASS**, gồm sáu test leakage. Có ví dụ tính tay/giá cố định/
  tăng hình học, đơn vị ×1.000, volume=0, phiên thiếu/cutoff, biên quyền và
  Reference, nguồn lỗi, JSON, bất biến tương lai và callback adapter.
- Audit offline trên bank train **852/852** khớp bảng W6-03: **699** có
  feature, **153** `CORPORATE_ACTION_WINDOW`; tập fit hợp lệ **166/428**
  theo hai fold. Bất biến tương lai PASS cả FPT/MWG/VCB/VNM; không gọi mạng.
- Chưa đưa feature vào state/prompt/ranking hoặc thay version W5. Producer
  scaler/index thuộc W6-06; W6-12 mới khóa identity CLI chứa module mới.
  Không tạo artifact/receipt trong repo và không sửa bank/model/manifest.
- Gate toàn hệ thống: compileall/E2E, **652 unit/111 leakage PASS**, không
  skip. Lượt unit đầu có một timeout 60 giây ở test lock cũ; kiểm riêng
  PASS trong 11 giây, sau đó chạy lại cả 652 test PASS, giữ nguyên test và
  timeout. **2.280 file** bảo vệ nguyên byte; `core/prior_context.py` là
  file tích hợp được sửa có chủ đích, kiểm bằng test hồi quy. Code được
  đối chiếu checksum với đúng bản chạy bốn gate; API do người dùng tự chạy
  ở các task sau, W6-05 hoàn toàn offline. **Gate B vẫn chờ 06–08**.

#### W6-06 — Scaler theo train/fold và auxiliary index

- **Làm:** fit scaler chỉ trên phần train hợp lệ trước query/fold; phục vụ
  OOS bằng scaler đã khóa cuối train. Xây index episode→vector, không thêm
  cột vào bank 852 episode; nạp/kiểm hash một lần trước hot query.
- **Đầu ra:** producer/loader/validator cho artifact runtime, liên kết bank,
  source, feature/scaler version và fit cutoff; schema tối thiểu khi cần.
- **Đạt khi:** fold sớm không dùng scaler fit bằng fold muộn; ID thiếu/trùng,
  source sai hoặc dữ liệu không hữu hạn dừng rõ ràng. Round-trip JSON native,
  tái tạo cùng nguồn cho cùng hash; index không chứa query outcome.

##### Triển khai và kiểm chứng — DONE, 11/10/2026

- [core/price_feature_index.py](../../../core/price_feature_index.py) có
  producer `build_price_feature_index`, writer `save_price_feature_index`,
  loader/validator `load_price_feature_index` và cache `PriceFeatureIndex`.
  Index `episode_price_index_v1` lưu vector **thô tại cutoff riêng của từng
  episode**, coverage/reason cùng ID/mã/cutoff/exit; không nhận outcome,
  entry/exit price hoặc tín hiệu LLM, không thêm cột vào bank.
- Scaler `symbol_fold_standard_v1` fit riêng bốn mã, theo đúng biên 04/01/2021,
  06/01/2022 và OOS cuối train tại mục W6-03. Artifact ghi danh sách ID fit,
  count, min/max exit, cutoff/rule/freeze, mean/variance/scale/zero-mask;
  mỗi scaler có hash riêng khi truy xuất. Chiều có variance=0 dùng scale=1;
  fit<2 trả `SCALER_UNAVAILABLE` có proof, không mượn mã/fold khác.
- Envelope khóa feature/price-policy/scaler/index/fold, runtime và hash code
  text LF; provenance gồm byte hash bank/manifest/QA, CSV/evidence/events và
  lịch VNINDEX. Loader kiểm envelope/byte hash nếu được cấp, **tái tính toàn
  bộ vector và scaler từ nguồn đã xác minh**, đối chiếu chính xác trước khi
  trả cache. Sửa vector/fit ID/count/source/code rồi băm lại vẫn bị từ chối.
  Schema được kiểm trong producer/loader; không cần file schema rời chưa có
  consumer. Writer ghi nguyên tử một lần; identity khác phải dùng path mới.
- [PriorContextAdapter](../../../core/prior_context.py) cung cấp
  `build_price_feature_index()` / `load_price_feature_index()` trước vòng
  query và `scaled_price_features(index, symbol, as_of_date)` khi chuẩn bị
  feature. `PriorPointContext.scaled_price_features(index)` dùng đúng cutoff
  của điểm. Biên adapter kiểm checksum/extract nguồn như W6-05; **hot
  retrieval** chỉ dùng `index.transform_query`, `index.prior_features` và
  `index.closed_episode_ids` trên RAM, không I/O/fit/extract. Query/prior dùng
  cùng scaler theo fold query. ID lạ/trùng, sai mã/fold hoặc exit≥query ném
  `ValueError`; population vẫn giữ episode `UNAVAILABLE`.
- OOS dùng cache đã build/load từ adapter train. Khi nối cache vào adapter
  OOS, kiểm một lần bank/đơn vị và hash nội dung prefix train của bốn mã,
  lịch cùng ngày quyền; không yêu cầu manifest archive OOS giống manifest
  train. Giá từ 2023/2024 không vào fit. Ngày quyền ISO tại 00:00:00 và nhiều
  sự kiện cùng phiên được giữ theo quy tắc extractor; không sửa nguồn.
- Artifact local duy nhất tại
  `outputs/bayesian_benchmark/price_features/index.json` (**đã gitignore**).
  Nội dung hash `2ec70b4274cf7980c8193ec78d5a05b9be1602bbab163cff84b306dfb3241e07`;
  byte SHA-256 `8a769b577bb4e11b9319f662791417407da7729e3aa895e4a89c2ba6945202a1`.
  Có thể tái tạo bằng producer từ nguồn train đã kiểm; đổi code/runtime/
  nguồn phải tạo artifact/path mới, không ghi đè hoặc sửa hash lịch sử.
- Audit production offline build→save→load PASS **852/852**, hash tái tạo
  khớp; tám query thực tế và prefix train/OOS bốn mã PASS, 0 kết nối mạng.
  Các fit ID đều thỏa biên strict/inclusive; mean/variance được tái tính
  độc lập. Coverage và count fit:

| Mã | Episode | Có feature | Thiếu do quyền | Fit 2021 | Fit 2022 | Fit OOS |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| FPT | 211 | 160 | 51 | 41 | 101 | 160 |
| MWG | 213 | 172 | 41 | 42 | 104 | 172 |
| VCB | 215 | 201 | 14 | 47 | 123 | 201 |
| VNM | 213 | 166 | 47 | 36 | 100 | 166 |
| **Tổng** | **852** | **699** | **153** | **166** | **428** | **699** |

- Kiểm thử tại [test_price_feature_index.py](../../../tests/test_price_feature_index.py)
  và [test_price_feature_index_leakage.py](../../../tests/test_price_feature_index_leakage.py):
  **19 test mới PASS**, gồm **5 leakage**; tính tay ddof=0/zero-scale,
  purge equality, freeze fold/OOS, cùng scaler cho query/prior, không clip,
  thiếu feature/scaler có proof, JSON native, round-trip, write-once,
  rehashed tamper, source lỗi và bảo toàn Full/v1. Sửa/thêm giá tương lai
  không đổi feature cũ/tập fit sớm; không nhận outcome. Mock cấm đọc file,
  extract/refit trong cache PASS; 100 lượt query+population trên dữ liệu
  thật mất tổng 0,1848 giây, **không thay phép nghiệm thu p95 ở W6-15**.
- Bốn gate toàn hệ thống **PASS**: compileall/E2E, **671 unit/116 leakage**,
  không skip; code khớp bản chạy gate, **2.280 file** bảo vệ nguyên byte.
  Không gọi API hoặc sửa bank/model/manifest/checkpoint/ledger cũ. Chỉ tạo
  một artifact runtime đã gitignore, không thêm Markdown/receipt/schema
  rời. Ranking/recency/diversity còn thuộc 07–08; CLI/identity mới thuộc 12.
  **Gate B vẫn chờ 07–08**, chưa phải nghiệm thu ranking hay validation v2.

#### W6-07 — Similarity kết hợp tín hiệu và giá

- **Làm:** thêm metric có version, giữ `signal_match_v1`; lọc PIT/symbol/regime
  trước xếp hạng, tính khoảng cách vector hóa và tie-break xác định.
- **Đầu ra:** entry point retriever mới và trace từng thành phần score;
  đường v1 vẫn tái lập được từ nguồn/config cũ.
- **Đạt khi:** kiểm ranking bằng oracle nhỏ, labels bị hoán đổi không đổi
  lựa chọn, query tương lai không làm cache ảnh hưởng query quá khứ; không
  I/O hoặc fit scaler trong hot query. Không tự fallback khi lỗi provenance.

##### Triển khai và kiểm chứng — DONE, 11/10/2026

- [core/prior_price_similarity.py](../../../core/prior_price_similarity.py)
  triển khai `signal_price_scores` bằng NumPy trên bốn chiều. Metric
  `signal_price_similarity_v1`: `S=matches/4`, `d=sqrt(mean((z_prior-z_query)²))`,
  `P=1/(1+d)`, `base=w_signal*S+(1-w_signal)*P`; mặc định `w_signal=0.5`.
  Alias tín hiệu dùng đúng normalizer v1; sentiment không tham gia S.
  Giá/query/prior đều phải có feature/scaler hợp lệ, kể cả khi w=0 hoặc 1.
- API production mới `BayesianPriorRetriever.rank_price_candidates(index,
  symbol, as_of_date, current_regime, current_signals, query_features,
  w_signal=0.5)` lọc **same_symbol / same_regime / exit<query trước score**.
  Xếp base giảm → exit giảm → ID tăng, version `base_similarity_ranking_v1`.
  Kết quả trả `ranked_tasks`, toàn `regime_population`, `trace`, `metadata`;
  đây là thứ tự nền **BASE_SIMILARITY / policy_complete=false**. Tuổi,
  recency, ngưỡng similarity, diversity và K_eff thuộc W6-08; chưa phải
  `signal_price_recency_v1` hoặc output evidence C1 hoàn chỉnh.
- Cache index được đối chiếu bank hash và toàn bộ ID/mã/cutoff/exit một lần
  theo identity. Mỗi query còn kiểm pool đúng PIT và đầy đủ so với index,
  rồi transform query/prior bằng cùng scaler của fold query. Khoảng cách
  chạy vector hóa, không I/O/fit/extract hoặc copy lại toàn index trong hot
  ranking. Query feature phải đến từ extractor tin cậy; biên adapter kiểm
  nguồn trước khi gọi API thuần, không dùng `execution_data()`.
- `PriorPointContext.rank_price_candidates(projection, index, w_signal=...)`
  kiểm Full đã seal, nguồn/projection và feature tại đúng cutoff, không gọi
  lại upstream. Query whitelist không nhận outcome/giá thoát. Sai source,
  thiếu ID, sai fold/cutoff, pool bị tiêm/sót record hoặc NaN/overflow ném
  lỗi; không chuyển lỗi toàn vẹn thành thiếu coverage hoặc fallback v1.
- Trace từng episode có S/d/P/base, cutoff/exit, status/reason và reason
  feature. Query thiếu feature, prior thiếu feature hoặc scaler fit<2 có
  proof thì score giá/base là `null`, không được xếp hạng; các episode đó
  vẫn thuộc population thống kê. Metadata ghim metric/ranking/feature/
  price-policy/scaler/index, bank/index/scaler hash, fold/fit/freeze cùng
  config/hash. Kết quả trả bản sao sở hữu, không làm đổi cache hoặc Full.
- [15 test mới](../../../tests/test_prior_price_similarity.py), gồm
  [5 test leakage](../../../tests/test_prior_price_similarity_leakage.py),
  PASS: oracle nhỏ S=3/4, d=1/2, P=2/3, base=17/24; zero distance, alias/
  sentiment, trọng số biên, finite/type/shape, tie-break, population thiếu
  feature/scaler, wrong bank/ID/source và callback Full. Tiêm hoán vị cả
  WIN/LOSS/net-return trên snapshot RAM không đổi score/thứ tự; không xuất
  bank sai kinh tế. Query tương lai rồi quá khứ và sửa giá tương lai không
  đổi ranking cũ. Bốn mode v1 và evidence W5 tái lập nguyên kết quả.
- Audit production offline trên **651/651 query train** (FPT160/MWG163/
  VCB165/VNM163) PASS: **530** query có feature, **121** thiếu do quyền;
  oracle độc lập khớp thứ tự và score của **16.061 cặp** được chấm trong
  **24.448 cặp population**, sai số tối đa `2.22e-16`. Số cặp chỉ dùng
  đối chiếu ranking, không dùng làm cỡ mẫu hiệu quả. Bốn query cũ chạy lại
  sau query tương lai vẫn khớp; 100 hot query mất tổng **0,3719 giây** khi
  mock cấm I/O/refit, không thay nghiệm thu p95 ở W6-15. **0 kết nối mạng**.
- Audit tái tạo/round-trip index theo code adapter mới **chỉ trong TEMP**;
  index W6-06, bank/model/manifest/checkpoint/ledger cũ giữ nguyên byte.
  Index đã khóa bằng code cũ không được nạp với identity mới; run mới phải
  build/load bằng path riêng qua API W6-06. W6-12 sẽ khóa module mới vào
  identity/CLI. Không tạo thêm Markdown/schema/receipt/runtime JSON trong
  repo. Compileall/E2E, **686 unit/121 leakage PASS**, không skip; 2.282
  file bảo vệ nguyên byte, code/test khớp byte đã kiểm. **Gate B còn chờ W6-08**.

#### W6-08 — Recency, đa dạng ví dụ và trace lựa chọn

- **Làm:** áp dụng luật tuổi/đa dạng ngày đã đăng ký, loại ví dụ quá giống
  nhau; ghi score trước/sau và lý do giữ/loại. K_eff có thể nhỏ hơn K.
- **Đầu ra:** policy chọn ví dụ và trace selected/excluded IDs; test trùng
  ngày, cạnh ngưỡng, tập rỗng, chỉ có một ví dụ và thứ tự dữ liệu đảo.
- **Đạt khi:** quyết định chọn không dùng WIN/LOSS; thay K hoặc diversity
  không âm thầm thay population của statistics. V1 không đổi, v2 xác định,
  trả lý do khi không đủ ví dụ thay vì bù bằng future/cross-symbol.

##### Triển khai và kiểm chứng — DONE, 11/10/2026

- [core/prior_example_selection.py](../../../core/prior_example_selection.py)
  triển khai `signal_price_recency_v1` / `session_gap_v1`, kế thừa base
  ranking W6-07. Cấu hình mặc định đã đăng ký: w=0.5, half-life=365 ngày,
  tuổi tối đa=730 ngày, base≥0.625, gap≥5 phiên, K=3 và seed=42; có config/hash.
  API phương pháp cho phép cấu hình hợp lệ để kiểm ablation; W6-12 sẽ khóa
  đúng cấu hình của từng candidate trên CLI, không dùng `.env` để đổi nhánh.
- `PriceExampleSelector(index, calendar)` gắn lịch VNINDEX đã kiểm với
  index; kiểm ngày gốc, thứ tự, duy nhất và hash prefix train. Adapter cấp
  lịch từ nguồn đã xác minh, cache selector theo index identity. Hash lịch
  trong result chỉ lấy prefix ≤query; tuổi tính từ `as_of_date`, exit-age
  chỉ chẩn đoán. Không dùng ngày lịch thay số phiên trong diversity.
- API `BayesianPriorRetriever.select_price_examples(selector, symbol,
  as_of_date, current_regime, current_signals, query_features, config=None)`
  trả `tasks`, toàn `regime_population`, `trace`, `metadata`. Lọc tuổi/base
  trước xếp rank=base×recency giảm → exit giảm → ID tăng; greedy kiểm gap
  với **từng ví dụ đã chọn**, equality được nhận. Không làm tròn trước so
  ngưỡng; không bù K bằng tín hiệu đơn lẻ, future hoặc cross-symbol.
- Trace mọi ID của P có S/d/P/base/age/exit-age/session/recency/rank,
  thứ tự xét/chọn và reason: thiếu feature/scaler, `PRIOR_TOO_OLD`,
  `BELOW_MIN_SIMILARITY`, `SESSION_GAP_TOO_SMALL` kèm ID xung đột, `K_LIMIT`.
  Metadata có selected/excluded/base-ranked/ranked IDs, K_eff, counts/reason
  khi thiếu ví dụ và provenance W6-07/lịch/config. Tuổi/gap/K/feature/similarity
  không làm đổi P hoặc scaler. Policy chỉ nhận trace không chứa outcome;
  nhãn được ghép vào nội dung sau chọn. Chưa tính statistics/gate/prefix C1.
- `PriorPointContext.select_price_examples` kiểm shared Full đã seal,
  nguồn và index trước feature/policy, giữ K/seed đúng cấu hình nhánh. Cache
  không I/O/refit/copy lại toàn index ở hot retrieval; Full/upstream và kết
  quả v1/evidence W5 giữ nguyên. Lỗi lịch/source/PIT/provenance ném lỗi.
- [13 test mới](../../../tests/test_prior_example_selection.py), gồm
  [5 test leakage](../../../tests/test_prior_example_selection_leakage.py),
  PASS: ví dụ rank=17/48 sau 365 ngày; biên tuổi730/731, base=.625 và số
  sát dưới, gap4/5 phiên, trùng ngày, tie-break, K-limit, tập rỗng/một ví dụ,
  thiếu query/scaler, dữ liệu đảo, oracle độc lập và callback production.
  Hoán vị cả WIN/LOSS/net-return chỉ đổi nội dung; K/gap/tuổi/quality không
  đổi P, query/giá/lịch tương lai không đổi lựa chọn quá khứ. Hot query bị
  mock cấm I/O/refit/copy index vẫn PASS.
- Audit production **651/651 query train** (FPT160/MWG163/VCB165/VNM163)
  khớp oracle độc lập S/d/P/base/recency/thứ tự/selected IDs; max error base
  `2.22e-16`. P giữ **24.448** cặp, **16.061** được chấm, **2.149** qua tuổi/
  similarity, **1.021** lượt ví dụ được chọn. K_eff=0/1/2/3 có lần lượt
  **221/86/97/247 query**; không bù K hoặc đổi ngưỡng để tăng coverage.
  Đây là kiểm tính đúng trên train, chưa là bằng chứng hiệu quả đầu tư.
  Bốn query quá khứ chạy lại sau tương lai vẫn khớp; 100 hot query tổng
  **0,5772 giây** khi cấm I/O/refit, không thay phép đo p95 W6-15. Không API/
  mạng; tái tạo/round-trip index audit chỉ trong TEMP, giữ index W6-06 cũ.
- Bốn gate toàn hệ thống **PASS**: compileall/E2E, **699 unit/126 leakage**,
  không skip; **2.286 file bảo vệ nguyên byte**, code/test khớp byte đã kiểm.
  Không tạo Markdown/schema/receipt/runtime JSON mới trong repo.

**Gate B PASS, 11/10/2026:** 05–08 DONE; feature/index/scaler/ranking và policy
chọn ví dụ chạy qua API production/adapter Full đã seal. Oracle train, PIT,
độc lập outcome/population, tính xác định và bốn gate hồi quy PASS;
bank/source/index cũ nguyên byte. Đây là gate kỹ thuật của Phase B; thống kê,
quality gate, prefix/Decision và identity/CLI ứng viên thuộc W6-09–12,
validation/p95 đầy đủ thuộc Phase D. Chưa chứng nhận hiệu quả đầu tư C1.

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

##### Triển khai và kiểm chứng — DONE, 11/10/2026

- [core/prior_conditional_statistics.py](../../../core/prior_conditional_statistics.py)
  triển khai `conditional_disjoint_beta_v1`. API
  `BayesianPriorRetriever.conditional_statistics(symbol, as_of_date,
  current_regime, current_signals, config=None)` chỉ nhận query đã whitelist;
  config riêng chỉ có trường `shrink_strength`, mặc định 4; W6-12 khóa
  cấu hình candidate trên CLI. Không nhận K, feature, tuổi,
  quality/diversity hoặc outcome query; không đổi thống kê v1/evidence W5.
- P là toàn bộ same_symbol/same_regime/exit<query từ bank đã kiểm. Kiểm
  cả eligible/P đủ ID so với snapshot bank, không chỉ kiểm các record còn
  lại. C khớp đúng bốn tín hiệu đã normalize; B=P\C. Sentiment không vào
  tuple, tín hiệu xung đột vẫn giữ nguyên tuple. Canonical ID bảo đảm kết
  quả xác định khi đảo thứ tự hoặc chạy query tương lai rồi quá khứ.
- Tái dùng masks/nhãn kinh tế của `_compute_statistics` trên P/C/B;
  raw success/support/rate của từng metric được ghi riêng. Union Trend OR
  Pattern bullish chỉ đếm mỗi cycle một lần; kiểm counts P=C+B. Episode
  thiếu feature hoặc không được chọn làm ví dụ vẫn tham gia statistics.
- `conditional_metric` lấy mean background `(s_B+1)/(n_B+2)`, chuyển thành
  đúng bốn pseudo-observation rồi cộng likelihood **chỉ từ C**. B rỗng dùng
  `FIXED_SYMMETRIC_PRIOR`; C rỗng sau mask dùng `NO_CONDITIONAL_HISTORY`,
  posterior/mean/interval=null, vẫn giữ đủ raw counts và hyperprior nguồn.
  Cỡ mẫu một hoặc chỉ một lớp vẫn tính; không thêm support từ prior.
- Result gắn `prior_evidence_v3`, stage `CONDITIONAL_STATISTICS`, groups/IDs/
  counts, normalized query, bank/population/config/evidence hash, hyperprior
  source, posterior và CrI95% plug-in có width. Đây là tỷ lệ lịch sử theo
  hợp đồng LONG có phí, chưa là xác suất LLM/query được hiệu chuẩn hoặc
  khoảng dự báo return. Quality/readiness/prefix thuộc W6-10–11; chưa là
  full evidence C2 hoặc runner/identity mới của W6-12.
- `validate_conditional_statistics(result, retriever)` tái dựng toàn bộ từ
  nguồn PIT rồi so canonical digest; phát hiện counts/partition/mean/source/
  config/type/field bị sửa kể cả khi caller băm lại artifact. Không tự nhận
  nguồn hợp lệ chỉ nhờ hash do artifact khai. `PriorPointContext` có callback
  kiểm Full đã seal, projection và file nguồn; không gọi lại upstream,
  không đọc evaluator hoặc đòi feature/index để tính thống kê.
- [14 test mới](../../../tests/test_prior_conditional_statistics.py), gồm
  [5 test leakage](../../../tests/test_prior_conditional_statistics_leakage.py),
  PASS: ví dụ C=3/4, B=8/20 → mean=51/88, posterior mass=8; khoảng Beta(3,2)
  đối chiếu CDF đa thức độc lập; empty/one/class/masks/alias/conflict/rare,
  zero denominator, finite/type, artifact tự băm lại và callback production.
  Chặn equal/future exit, pool thiếu/trùng và outcome/K query; không đọc
  outcome tương lai, K/quality/feature không đổi statistics. Hot query mock
  cấm I/O/refit/example selection vẫn PASS; kết quả trả bản sao sở hữu.
- Audit production **651/651 query train** (FPT160/MWG163/VCB165/VNM163)
  PASS counts/partition/hyperprior/posterior và validator tái tính nguồn.
  P/C/B có **24.448/1.335/23.113** cặp qua các query; không coi tổng cặp
  lặp lịch sử này là cỡ mẫu hiệu quả. Có **263 query C rỗng**. Số query có
  posterior quan sát Win/Trap/TrendFail/PatternFail lần lượt **388/255/193/248**;
  các query còn lại giữ null theo mask, không tự mở rộng nhóm điều kiện.
  Kiểm CDF độc lập của biên CrI có sai số tối đa **2,11e-15**; bốn query
  cũ chạy lại sau tương lai vẫn khớp. 100 hot query tổng **0,7486 giây**
  khi cấm I/O/example selection; không thay phép đo p95 W6-15.
- Audit **0 kết nối mạng**, không API hoặc Markdown/schema/receipt/runtime
  JSON mới trong repo; kết quả audit chỉ trong TEMP. Bốn gate toàn hệ thống
  **PASS: compileall/E2E, 713 unit/131 leakage**, không skip; **2.289 file
  bảo vệ nguyên byte**, code/test khớp byte đã kiểm. Lượt unit đầu chạy đủ
  713 test, một lỗi
  `test_dead_child_owner_recovered_without_deleting_lock_file`: subprocess
  timeout60s. Chạy riêng ca này PASS trong 14,808s; chạy lại đầy đủ 713 test
  **PASS trên nguyên code**, giữ log lượt đầu trong TEMP, không skip hoặc
  đổi timeout. **Gate C còn chờ W6-10–12**.

#### W6-10 — Quality gate theo support/uncertainty

- **Làm:** gate chất lượng theo ngưỡng đăng ký, tách trạng thái stats và
  examples để `stats_only` không bị vô hiệu chỉ vì K_eff=0. Định nghĩa rõ
  insufficient/disabled/ready và fallback về Original.
- **Đầu ra:** policy version, reason codes và trace đủ để tái dựng prompt.
- **Đạt khi:** test các phía của từng ngưỡng; K=0/prior disabled giữ Original
  đúng contract, không biến lỗi hệ thống thành thiếu evidence. Quality gate
  không tự đổi LONG thành CASH; policy giao dịch được xét riêng ở 13.

##### Kết quả triển khai — DONE/PASS, 11/10/2026

- `core/prior_quality_gate.py` ghép statistics W6-09 và selection W6-08 qua
  `BayesianPriorRetriever.quality_evidence(...)`;
  `PriorPointContext.quality_evidence(projection, index, gate_version=...)`
  kiểm Full đã seal và nguồn/index, không gọi lại upstream hay đọc outcome query.
- `split_quality_gate_v2`: P≥20, support C từng metric≥5, CrI width≤0,75;
  nhận dấu bằng, không làm tròn. Stats READY nếu ≥1 metric đạt; examples
  READY nếu P≥20, feature/scaler hợp lệ và còn ≥1 ví dụ quality/diversity.
  Thiếu examples không tắt stats. `population_coupled_gate_v1` của C1 giữ
  Beta(1,1) trên P và tắt cả hai block khi thiếu examples; C0/v1/W5 giữ API cũ.
- Evidence v3 giữ statistics/selection cùng proof, trạng thái
  `READY/INSUFFICIENT_EVIDENCE/DISABLED`, reason từng metric/block và
  `base_evidence_sha256`. Ba `content_views` ghi retrieved/visible K và IDs
  trên cùng base, chỉ hiển thị metric ready; mode không có block ready ghi
  fallback Original. K=0/prior off bỏ cả hai producer và không cần index/feature.
  Posterior chưa đạt chỉ nằm ở sidecar; builder prompt thuộc W6-11.
- Validator tái tính từ nguồn, chặn cả artifact tự băm lại. Thiếu/sai artifact,
  pool thiếu/trùng/future hoặc nguồn bị đổi ném lỗi; không đổi thành thiếu support.
  Gate không xét mean>0,5 hoặc sửa action. Không thêm config override ngưỡng,
  CLI, risk policy, API run hay Markdown/JSON receipt theo task.
- **16 test mới PASS**, gồm **4 leakage**: các phía biên 20/5/0,75,
  metric masks/null, stats/examples độc lập, C1, visibility/fallback, disabled,
  nguồn Full và corruption/PIT. Fixture đủ support dùng nhãn engine thật;
  quyền chặn feature query vẫn giữ stats READY với K_eff=0. Đây là nghiệm thu
  kỹ thuật, coverage train thuộc W6-14. **Bốn gate toàn hệ thống PASS:
  compileall/E2E, 729 unit/135 leakage**, không skip. **2.292 file bảo vệ
  nguyên byte**, code/test khớp byte đã kiểm. **Gate C còn chờ W6-11–12**.

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

##### Kết quả triển khai — DONE/PASS, 11/10/2026

- `core/prior_prompt.py`: `build_prior_request(evidence, candidate_id,
  retriever, selector=..., query_features=...)` tái kiểm nguồn qua validator
  W6-10, rồi dựng prefix và request có version/hash. C0 giữ đường W5;
  C1 `compact_brpp_v2_compat` bằng byte template W5 khi cùng stats/tasks;
  C2/C3 `compact_brpp_v3` ghi n_P/n_C, counts/support, mean/CrI plug-in và
  N/A cho metric chưa đạt. Chỉ ví dụ đã đóng được render, có episode ID
  chuẩn để model viện dẫn; không đưa evaluation/P&L query vào prompt.
- Ba C3 dùng cùng base evidence/hash; request hash riêng cho content mode.
  `full_prior/stats_only/examples_only` lấy đúng block/IDs ready, không
  đổi ranking/counts/K hoặc bù bằng block bị ẩn. Thiếu block phù hợp,
  K=0/prior off → prefix rỗng, prompt/schema Original nguyên byte; sidecar
  vẫn ghi reason, retrieved/visible K và IDs. Stats-only K_eff=0 vẫn dùng
  stats nếu đủ điều kiện. C1/C2 giữ reasoning W5; C3 thay riêng chỉ dẫn prior
  và thêm field JSON, giữ nguyên báo cáo/distill/cap và hợp đồng kinh tế.
- `agents/decision_agent.py` nhận `_prior_request` qua hook nội bộ đã kiểm
  nguồn. `TradeDecisionPriorOutput/PriorUseOutput` chỉ bật ở C3 có prior
  hiển thị: metric/example IDs, `SUPPORTS/CONFLICTS/MIXED/NOT_USED`, lý do.
  Chặn IDs ẩn/trùng/N/A, thiếu trace/field sai. Model được bác/không dùng
  prior; action LONG/SHORT giữ nguyên, không retry để ép đồng thuận.
  `prior_decision_trace_v1` trả request/base hash, nguồn bank/index/scaler/
  fold/calendar, visibility, raw action và self-report; trace này không
  chứng minh cơ chế nhân quả. Lưu durable/checkpoint thuộc W6-12.
- `validate_prior_request` rebuild từ evidence và nguồn; node kiểm binding
  với query Full/prefix trước LLM. Hook nguồn phải xác minh mỗi invocation;
  hash tự khai không thay semantic validator khi đọc artifact. Text và
  structured đều dùng `_invoke_with_retry`, tối đa hai lần sửa format trong
  cùng invocation budget hiện hữu. Integrity/leakage ném lỗi, không fallback.
- **16 test mới PASS**, gồm **4 leakage**; matrix sáu cấu hình, vi/en,
  short/saturated/structured reports và hai route LLM fixture, ba ablation,
  conflict/NOT_USED, thiếu evidence, nguồn Full và artifact tự băm lại.
  Kiểm BRPP đủ **600**, chặn **601**, prompt **6.499 PASS / 6.500 chặn trước
  LLM**; regime tên dài, bốn metric ready/ba ví dụ vẫn đủ trần. Không API,
  schema JSON hoặc Markdown/receipt rời mới. **Bốn gate toàn hệ thống PASS:
  compileall/E2E, 745 unit/139 leakage**, không skip. **2.294 file bảo vệ
  nguyên byte**, bốn file code/test khớp byte đã kiểm. **Gate C còn chờ W6-12**.

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
và `scripts/run_bayesian_ablation.py`. Feature được triển khai tại
`core/pit_price_features.py`, scaler/index tại `core/price_feature_index.py`
và base similarity tại `core/prior_price_similarity.py`, policy tuổi/diversity
tại `core/prior_example_selection.py`, kết nối
`core/prior_context.py` qua W6-05–08. Không mở thêm runner độc lập
nếu CLI hiện hữu có thể mở rộng rõ ràng.
Thống kê điều kiện W6-09 nằm tại `core/prior_conditional_statistics.py`,
có API retriever và callback point riêng; W6-10 ghép statistics/selection
và quality gate tại `core/prior_quality_gate.py`. W6-11 có prefix/request
tại `core/prior_prompt.py`, schema/trace tại `agents/decision_agent.py`.
CLI/protocol/identity và checkpoint ứng viên còn thuộc W6-12.

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
| 11/10/2026 | W6-02 | DONE; 2/16 task. Bank audit mốc `f743b94` và replay production 852/852 PASS; 217 scaler prefix, 16 điểm Alpha tái tính và 4 ca sửa tương lai PASS offline. Ghi coverage giá/quyền, ma trận cutoff và giới hạn PIT hồi cứu. Compileall/E2E, 624 unit/105 leakage PASS, không skip; 2.281 file nguyên byte, audit 0 credential/network, không API hoặc receipt mới. Gate A chờ 03–04 | W6-03: chốt feature/ranking/thống kê và chính sách quyền |
| 11/10/2026 | W6-03 | DONE; 3/16 task. Chốt feature 21 phiên và barrier quyền, scaler theo mã/fold, ranking tín hiệu+giá/recency/diversity, thống kê điều kiện có background P\C và readiness stats/examples độc lập. Coverage 699/852, fit166/428; 17 đối chiếu công thức PASS. Compileall/E2E, 624 unit/105 leakage PASS, không skip; 2.281 file nguyên byte. Chỉ ba Markdown, không API/code/schema mới; Gate A chưa nghiệm thu | W6-04: đăng ký ứng viên, ablation và ngưỡng chất lượng |
| 11/10/2026 | W6-04 | DONE; 4/16 task, Gate A PASS trong phạm vi thiết kế/PIT hồi cứu. Registry 6/6, C0/default/version, ngưỡng/biên số học, lock/model options và checklist PASS; chốt comparator, ablation, common support và tiêu chí đề cử W7. Compileall/E2E, 624 unit/105 leakage PASS, không skip; 2.281 file nguyên byte. Chỉ ba Markdown, không API/code/schema mới; các gate triển khai còn TODO | W6-05: extractor feature giá PIT, mở Phase B |
| 11/10/2026 | W6-05 | DONE; 5/16 task, Phase B IN_PROGRESS. Extractor bốn feature/21 phiên PIT dùng chung episode/query, callback adapter/point, coverage/reason và JSON gốc; 28 test mới PASS, gồm 6 leakage. Audit 852/852 khớp 699 hợp lệ/153 barrier, fit 166/428 và bất biến tương lai bốn mã. Compileall/E2E, 652 unit/111 leakage PASS, không skip; 2.280 file bảo vệ nguyên byte. Không API/artifact mới; Gate B chờ 06–08 | W6-06: scaler theo mã/fold và auxiliary index |
| 11/10/2026 | W6-06 | DONE; 6/16 task. Producer/loader/cache index phụ đủ 852 episode, 699 vector hợp lệ/153 barrier; scaler riêng mã/fold fit 166/428, OOS freeze 699 hàng train. Round-trip/hash/semantic và prefix train/OOS bốn mã PASS; query/prior dùng cùng scaler, hot cache không I/O/refit. 19 test mới gồm 5 leakage; compileall/E2E, 671 unit/116 leakage PASS, không skip. 2.280 file bảo vệ nguyên byte; một index runtime gitignore, không API hoặc Markdown/schema/receipt mới. Gate B chờ 07–08 | W6-07: similarity kết hợp tín hiệu và giá |
| 11/10/2026 | W6-07 | DONE; 7/16 task. Base ranking tín hiệu+giá vector hóa, trace S/d/P/base, callback Full đã seal và source/index/scaler binding; giữ nguyên v1/evidence W5. Audit 651/651 query train, 16.061 cặp được chấm khớp oracle độc lập, max error 2.22e-16; label/future/cache và hot no-I/O/refit PASS. 15 test mới gồm 5 leakage; compileall/E2E, 686 unit/121 leakage PASS, không skip. 2.282 file bảo vệ nguyên byte; index audit chỉ trong TEMP, không API/receipt mới. Gate B chờ 08 | W6-08: recency, diversity và trace chọn ví dụ |
| 11/10/2026 | W6-08 | DONE; 8/16 task, Phase B DONE / Gate B PASS. Policy recency/tuổi/base/gap phiên/K xác định, trace giữ/loại và callback Full đã seal; giữ population/scaler và v1. Audit 651/651 query train khớp oracle, 2.149 cặp qua quality/tuổi, 1.021 lượt ví dụ được chọn; K_eff=0/1/2/3: 221/86/97/247. 13 test mới gồm 5 leakage; compileall/E2E, 699 unit/126 leakage PASS, không skip. 2.286 file bảo vệ nguyên byte; artifact audit chỉ trong TEMP, không API/receipt mới. Thống kê/quality gate/CLI thuộc Phase C | W6-09: thống kê điều kiện và shrink có kiểm chứng |
| 11/10/2026 | W6-09 | DONE; 9/16 task, Phase C IN_PROGRESS. Thống kê P/C/B rời nhau, masks hiện hữu, empirical Bayes strength4 và CrI plug-in; validator tái tính từ nguồn và callback Full đã seal. Audit 651/651 query train PASS, 263 query C rỗng giữ null; counts P/C/B=24.448/1.335/23.113, max CDF error2,11e-15. 14 test mới gồm 5 leakage; compileall/E2E, 713 unit/131 leakage PASS, không skip. Unit lượt đầu timeout60s ở test khóa cũ; chạy riêng và chạy lại toàn bộ nguyên code PASS, giữ log đầu TEMP. 2.289 file bảo vệ nguyên byte, không API/receipt mới. Gate C chờ 10–12 | W6-10: quality gate theo support/uncertainty |
| 11/10/2026 | W6-10 | DONE; 10/16 task. Gate tách stats/examples đúng ngưỡng 20/5/0,75, C1 giữ population Beta và gate ghép cặp; evidence v3 có reason/visibility/fallback và validator tái tính nguồn. K=0/prior off bỏ producer, integrity/PIT ném lỗi, không sửa action. 16 test mới gồm 4 leakage; compileall/E2E, 729 unit/135 leakage PASS, không skip; 2.292 file bảo vệ nguyên byte. Không API/receipt mới; Gate C chờ 11–12 | W6-11: prefix/Decision contract và ablation nội dung |
| 11/10/2026 | W6-11 | DONE; 11/16 task. Prefix/request có version, hash và validator nguồn; ba C3 chung base evidence, visibility đúng content mode. C1 tương thích byte template W5, C2 giữ reasoning W5; C3 thêm trace IDs/assessment/lý do, không ép action. Thiếu block/K=0/prior off giữ prompt/schema Original. 16 test mới gồm 4 leakage; caps 600/601 và 6.499/6.500 PASS; compileall/E2E, 745 unit/139 leakage PASS, không skip; 2.294 file bảo vệ nguyên byte. Không API/receipt mới; Gate C chờ 12 | W6-12: CLI/protocol/identity và checkpoint ứng viên |
