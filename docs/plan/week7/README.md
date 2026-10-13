# Tuần 7 — Validation, chọn ứng viên và khóa giao thức benchmark

**Trạng thái: Phase A DONE / Gate A PASS; Phase B IN_PROGRESS, 5/16 task hoàn thành; Phase C/D TODO.**
Ngày lập: **12/10/2026**; cập nhật: **13/10/2026**. Tiếp theo **W7-06**.
[Kế hoạch tổng](../plan.md) · [Bàn giao W6](../week6/README.md)

## 1. Mục tiêu và đầu vào

W7 kiểm chứng các ứng viên trên train/development, đưa ra quyết định chọn
có thể tái lập và khóa giao thức trước benchmark 2024 ở W8. Hoàn thành kế
hoạch này chưa có nghĩa đã chạy validation hoặc tìm được ứng viên tốt hơn.

| Đầu vào đã có | Cách dùng trong W7 |
| --- | --- |
| W6 đóng 16/16, Gate A/B/C/D PASS; merge `0b24b38` | Mốc đối chiếu; compileall/E2E, 784 unit/146 leakage PASS |
| Bank 852 episode, model/proof theo cutoff; train report v2 | Kiểm PIT cuốn chiếu trên 651 query, bootstrap 2020; giữ nguyên bằng chứng W6 |
| Registry `prior_candidates_v1`, plan `research_cohort_plan_v3` | Sáu ứng viên C0, C1, C2, C3, C3_stats_only, C3_examples_only; năm đối chứng v1 |
| Plan development v1 đã prepare/dry-run | Đúng 60 điểm 2023: FPT 12, MWG/VCB/VNM 16 mỗi mã; chưa gọi Decision/API |
| Lịch W5: 64 điểm holdout 2024, 16/mã | Chỉ khóa manifest cuối sau quyết định lựa chọn; W8 mới thực thi |
| Numeric risk policy DEFERRED/OFF | Giữ OFF trong phạm vi W7; không thêm policy chặn LONG vào phép so sánh ICL |

Các artifact bắt đầu nằm trong `outputs/bayesian_benchmark/`:
`input_lock.json`, `smoke_plan.json`, `train_validation_v2.json`,
`prior_performance_v2.json`, `development_candidate_plan_v1.json`,
`price_features/train_validation_index_v1.json` và
`price_features/candidate_index_v1.json`. Đường dẫn/hash/cách verify đầy đủ
ở mục W6-16 của README W6. Artifact runtime gitignore; cần giữ nguồn local
đã khóa để tái lập. Không sao chép receipt sang tài liệu mới.

**Khoảng trống cần triển khai:** W7-05 đã có report v4 global/pairwise,
metric/coverage theo mã/regime và verifier; phân tích W7-06 và bộ lựa chọn
đầy đủ theo W6-04 còn chờ triển khai.
CLI ứng viên hiện chỉ nhận fixture/development_2023; cần consumer/validator
có version cho lựa chọn và manifest holdout. Không coi các tên artifact
dự kiến dưới đây là schema hoặc chức năng đã tồn tại.

### Khảo sát bàn giao W7-01

**Identity/nguồn PASS, 12/10/2026:** Python **3.13.5** và dependency runtime
khớp cả train report v2, performance report v2 và plan development v1.
Envelope/checksum byte khớp bàn giao W6-16; registry sáu ứng viên/risk OFF
khớp code hiện tại. So **55/57/54 mục code/schema/dependency** tương ứng
train/performance/plan bằng hash text LF; **1.992 nguồn ghim** khớp byte,
không có hash xung đột giữa các artifact. **2.317 file bằng chứng/artifact
W6 nguyên byte**, W6 vẫn 16/16 và Gate A/B/C/D PASS.

Report train giữ 852 replay, 651 query (329/322), bootstrap 201, 217 cutoff
model/proof, feature AVAILABLE=530/UNAVAILABLE=121; `decision_calls=0`,
`llm_performance=null`, `candidate_selection=null`. Đây là kiểm identity/
nguồn và nội dung bàn giao; replay đầy đủ HMM/purge/fold thuộc **W7-04**.
Plan development đúng lịch W5: FPT 12, MWG/VCB/VNM 16 mỗi mã; chưa có
`development_candidate_run_v1/cohort.json`. Holdout chỉ kiểm metadata lịch
64 điểm, không đọc bảng outcome/metric hoặc tạo manifest holdout mới.

| Thành phần | Producer → consumer/verifier hiện hữu | Đã có và việc W7 cần làm |
| --- | --- | --- |
| Train PIT | `core/train_pit_validation.py:run_train_validation` → `read_envelope`, `build_train_diagnostics` khi verify | Report v1/v2 có nguồn/fold/proof và chẩn đoán; W7-04 verify đúng v2/index, không dùng mặc định v1 trên code hiện tại |
| Feature/scaler/index | `core/pit_price_features.py`, `core/price_feature_index.py` → `PriorContextAdapter.load_price_feature_index`, retriever/quality gate | Producer/loader kiểm semantic và scaler theo fold đã có; giữ index lịch sử, chỉ sinh revision mới nếu identity thay đổi |
| Registry và plan | `core/candidate_cohort.py:registry/prepare_candidate_plan` → `validate_candidate_plan`, `core/research_cohort.py:validate_plan` | Sáu ứng viên, plan/identity v3 và 11 nhánh đã có; dùng nguồn/lịch W5 nguyên byte và ghim code/runtime hiện tại |
| Metric ghép cặp | `core/research_metrics.py:branch_metrics/candidate_report` → `run_cohort` tái dựng report từ checkpoint | Có common support đủ 11 nhánh theo mã, metric tài khoản, CASH, Δreturn từng mã và trung bình bốn mã; W7-03/05 bổ sung pairwise support, ΔMDD, exposure/coverage và tình trạng lỗi chi tiết |
| Prior-use/attribution | `core/prior_prompt.py:build_prior_request`, Decision → `candidate_cohort.py:_checked_response`, `research_metrics.py:action_attribution` | Có visible/retrieved IDs, raw response/trace và risk OFF; W7-06 bổ sung tổng hợp 11 nhánh, prior-off và subgroup cả stats/examples ready |
| Phân tích v1 | `scripts/analyze_prior_run.py:audit_points/analyze_run` | Có audit kinh tế/disagreement Original–Bayesian; không coi đây là phân tích sáu ứng viên hoặc selector W7, chỉ tái dùng phần phù hợp |
| Durable checkpoint | `run_cohort/candidate_point`, `PriorCheckpointStore`, `StageJournal` → verify/reconcile/resume | Có intent/raw/semantic/UUID replay và Full dùng chung; verify/reconcile chỉ dùng sau khi run đã có `cohort.json`, dry-run chưa tạo run |
| Hiệu năng | `core/prior_performance.py:benchmark` → `verify_report/run_performance` | Có raw samples, kiểm nguồn/semantic và guard hot I/O/refit; audit chỉ verify report v2, không đo lại hoặc sửa kết quả W6-15 |
| Quyết định lựa chọn | Chưa có producer/loader/verifier cho nomination hoặc selection binding | D đã có trong report nhưng chưa đủ eligibility/ΔMDD/tie-break/NOT_PROMOTED; W7-07 mới triển khai, chưa có candidate được chọn |
| Holdout ứng viên | CLI `--candidate-split` và `validate_candidate_plan` chỉ nhận fixture/development_2023 | Legacy plan v2 có holdout nhưng không thay được giao thức 11 nhánh có selection binding; W7-08 bổ sung phiên bản mới, không đổi v3 thành v2 để vượt guard |
| API guard | CLI `execute_cohort` → retry, `GroqPacer`, ledger và run lock hiện hữu | Chỉ preflight/run đọc key; giữ `request_admission_v2`/ledger chung. Khả dụng model/API chưa được xác nhận; người dùng kiểm ở W7-10 |

**Ràng buộc identity:** code/runtime W5 trong lock/checkpoint là lịch sử,
không ép bằng code hiện tại. Kế thừa parent/lock bằng checksum và validator
hiện hữu; report/plan mới ghim code mới. Sau sửa code ở Phase B, W7-09 phải
khóa plan/output mới nếu identity đổi; không resume bằng cách sửa hash cũ.

Kiểm thử hiện hữu để kế thừa gồm `test_candidate_cohort*`,
`test_candidate_fault_matrix.py`, `test_research_*`,
`test_train_pit_validation.py`, `test_train_pit_leakage.py` và
`test_prior_performance.py`. Những test này chưa thay thế oracle/biên
lựa chọn mới ở W7-03/07 hoặc chứng minh lợi ích đầu tư.

**Kết quả W7-01: DONE.** Dry-run production trên đủ **60 điểm development**
PASS; verifier performance v2 đối chiếu semantic toàn bộ **651 query**,
mẫu timing thô và nguồn PASS. Chạy offline với guard chặn đọc `.env` và
kết nối API; không tạo run, không đo lại hiệu năng hoặc sửa report lịch sử.
Không có blocker nguồn/identity; các khoảng trống implementation được giao
đúng task trong bảng trên. **Gate A chưa PASS**, còn W7-02–04.

Thay đổi chỉ gồm ba Markdown; code/test giữ nguyên mốc W6-16 và runtime
đã đối chiếu khớp. Kế thừa bốn gate của cùng mã nguồn: compileall/E2E,
**784 unit/146 leakage PASS**, không chạy lại suite cho audit tài liệu.
Checklist 1/16, liên kết, trạng thái ba tài liệu và `git diff --check` PASS.

## 2. Phạm vi và hợp đồng khóa trước chạy

### 2.1. Vai trò từng tập dữ liệu

- **Train 2020–2022:** 2020 làm bootstrap; replay 852 checkpoint, chẩn đoán
  651 query của fold 2021 (329) và 2022 (322). Kiểm HMM đúng prefix, scaler
  freeze theo fold, purge theo entry/exit thực; fit feature hợp lệ 166/428.
  Đây là validation kỹ thuật PIT cuốn chiếu, không có return Decision mới.
  Fit scaler nhận episode có exit trước đầu fold; purge chu kỳ vắt qua biên fold.
  Embargo truy xuất là exit<query, không thêm phiên embargo ngoài protocol.
  W7 không tự thêm 651 điểm LLM trên train. Nếu cần kết luận hiệu quả
  LLM theo fold train, phải đăng ký protocol/runner/mẫu riêng trước API;
  không dùng mock hoặc Decision lịch sử khác identity để tạo kết luận đó.
- **Development 2023:** chạy Decision thật trên đúng 60 điểm đã khóa,
  FPT 12, VNM/VCB/MWG 16 mỗi mã, đủ 11 nhánh mỗi điểm; dùng để phân tích
  và lựa chọn. Giữ embargo pilot/smoke, không bù ngày thiếu hoặc đổi ngày lỗi.
  Không gộp train vào D.
  Query thiếu feature/support vẫn trong lịch; fallback đúng contract là
  complete, lỗi/unknown giữ nguyên trạng thái. Pilot 20 và smoke 4 chỉ là
  kiểm vận hành; fixture/mock không vào mẫu hiệu quả hoặc tiêu chí lựa chọn.
- **Holdout 2024:** 64 điểm đã khóa; trước lựa chọn chỉ được kiểm metadata,
  checksum và lịch nguồn. Không tính/đọc bảng outcome, metric hoặc Decision
  2024 để chọn cấu hình. Fixture holdout dùng dữ liệu tổng hợp; W7 chỉ
  prepare/dry-run nguồn thật sau khi quyết định lựa chọn đã đóng băng.

Giữ LONG Open(t+1)→Close(t+3), SHORT=CASH, phí 0,25% và trượt giá 0,10%
mỗi chiều; mọi nhãn qua `compute_round_trip_net_return`. Giá/tin ≤cutoff,
prior exit<cutoff; thiếu ngày tin bị loại, vi phạm integrity phải ném lỗi.
Một upstream/Full mỗi điểm, deep-copy cho mọi nhánh; chỉ tái dùng checkpoint
khi toàn bộ identity/provenance phù hợp. Original giữ prompt/schema gốc.
BRPP≤600 ký tự, tổng prompt<6.500; mọi API qua retry/pacer/ledger hiện hữu.

#### Cấu hình validation khóa tại W7-02

Kế thừa `inputs` và lịch từ `input_lock.json` W5 qua plan development v1;
không lấy default mới từ môi trường. Plan tham chiếu hiện tại có SHA-256 byte
`0948f954a33d438370c7b2df59181b5df4d8a971b00b9acffc0347894ef2081c`.
Registry `prior_candidates_v1` có `canonical_hash` theo
`core/prior_backtest.py`:
`f35bd8120ca0f716772b68f164c427978b35718be6b14f8280615110434cb15b`.
Đây là mốc cấu hình; plan dùng chạy API được ghim lại code/runtime ở W7-09,
không sửa byte plan bàn giao để nhận code mới.

| Đầu vào | Giá trị cố định |
| --- | --- |
| Signal | `language=vi`, `time_frame=1d`, `window_size=45`; Alpha 600 nến, `norm_method=zscore_tanh`, `alpha_weights=null` |
| Text/Decision | `openai/gpt-oss-20b`, `temperature=0`, `max_tokens=2048`; client `reasoning_effort=low`, `reasoning_format=hidden` |
| Graph/vision | `qwen/qwen3.8-27b`, `temperature=0`, `max_tokens=1024`; client `reasoning_effort=none`, `reasoning_format=hidden` |
| Prior adapter | `enable_bayesian_prior=true`, `mode=bayesian_regime`, K=3, seed=42, `scope=same_symbol`; bank/manifest/audit giữ đường dẫn và hash W5 |
| Năm đối chứng v1 | Original K=0; random/recent/similarity/bayesian K=3, mode đúng ID; giữ prompt/schema/version v1 |
| C0 | Evidence v2, Beta(1,1), population≥20, similarity tín hiệu≥0,75, tuổi≤730 ngày; gate/prefix/Decision W5 |
| C1–C3 và hai ablation | Giữ profiles/version trong registry; `w_signal=0.5`, half-life=365 ngày, tuổi≤730 ngày, base similarity≥0,625, gap≥5 phiên; C1 giữ statistics/gate coupled, C2/C3 shrink=4 và split gate support≥5/width≤0,75 |
| Risk và nguồn PIT | Risk OFF; population ứng viên cùng mã/regime và exit<query; HMM/scaler theo cutoff/fold đã khóa, OOS dùng model/scaler cuối train, không fit bằng 2023/2024 |

Phiên bản feature/scaler/ranking, content mode và khác biệt reasoning giữ
đúng registry và bảng phương pháp W6-04. Ba C3 dùng cùng base evidence;
không đổi retrieval/readiness khi ẩn stats/examples. Prior không hiển thị
thì dùng request Original, vẫn lưu Decision riêng và báo disagreement.
Thứ tự 11 nhánh cố định ở mục 2.2; mỗi điểm chỉ một upstream/Full, deep-copy
sang các nhánh. Không tái dùng Decision W5 thay cho lượt ứng viên mới.

#### Quy tắc amendment và mở lượt chạy

- **Trước API:** W7-03 khóa hợp đồng metric/selection; W7-09 hoàn thiện
  implementation, bốn gate và plan/run identity mới. W7-10 do người dùng
  preflight rồi chạy đúng plan. Chưa xác nhận khả dụng API/model; nếu không
  khả dụng thì dừng, không tự thay model/options ở một nhánh hoặc một mã.
- **Sửa code vận hành trước chạy:** giữ cùng lịch/cấu hình phương pháp,
  kiểm hồi quy và ghi code/runtime/schema/index/config hash vào plan mới;
  giữ nguyên parent/lock/artifact cũ. Chỉ resume khi mọi identity phù hợp.
- **Đổi phương pháp/model/ngưỡng/mẫu:** ghi amendment ngay trong README
  trước lượt API mới: thời điểm, lý do, giá trị cũ→mới, giả thuyết/comparator,
  ảnh hưởng protocol và identity/output riêng. Giữ kết quả các lượt trước,
  công bố tổng số cấu hình đã thử; không gộp lượt khác cấu hình thành primary
  hoặc sửa hash checkpoint. Thay đổi sau xem development phải ghi rõ tính
  thăm dò; không tự đổi lịch 60 điểm hay nới eligibility để lấy PASS.
- **Giới hạn holdout:** outcome/metric/Decision 2024 không được dùng cho
  amendment/lựa chọn. Chỉ sau W7-12 mới khóa protocol/manifest 64 điểm và
  dry-run; W8 thực thi. Phát hiện lỗi nguồn phải dừng và ghi cách khôi phục,
  không bỏ ngày lỗi hoặc đổi mẫu dựa trên return.

**W7-02 DONE:** khóa phạm vi và cấu hình trên; chưa tạo schema runtime mới
vì consumer bổ sung thuộc Phase B. Protocol không chứng nhận hiệu quả LLM;
Gate A còn W7-03–04.

### 2.2. Ứng viên, thước đo và lựa chọn

Giữ nguyên registry, model/client options, K=3, seed=42, scope=same_symbol,
feature/ranking/shrink/gate của W6-04. Thứ tự nhánh:
`original → random → recent → similarity → bayesian → C0 → C1 → C2 → C3
→ C3_stats_only → C3_examples_only`. C0 là evidence W5, khác `bayesian` v1.

Primary development: **D(c)=mean_s[R_net(c,s)−R_net(Original,s)]**, đơn vị
điểm phần trăm, trung bình đều bốn mã. Tái dựng tài khoản trên đúng support
ghép cặp, theo ngày, vốn 50 triệu/mã; không trừ return của hai lịch khác
nhau hoặc gọi trung bình bốn mã là portfolio. Báo thêm ΔR từng mã, MDD cuối
chu kỳ/ΔMDD, balanced accuracy, LONG hit-rate, LONG/CASH, disagreement,
coverage và CASH reference. Thiếu lớp/không LONG giữ null; không annualize
Sharpe/Sortino chu kỳ. Định nghĩa và dấu ΔMDD giữ như W6-04.

Quy tắc lựa chọn kế thừa nguyên vẹn:

1. Candidate đủ gate kỹ thuật, **60 paired points**, prior thực hiển thị
   **≥6/60 và ít nhất một điểm mỗi mã** mới đủ điều kiện xét.
2. Đề cử cải thiện khi **D>0**, ΔR>0 ở **≥3/4 mã**, mean ΔMDD≤2 điểm phần
   trăm và không mã nào ΔMDD>5. Drawdown dương hơn nghĩa là xấu hơn.
3. Trong tập đạt: D lớn nhất; D cách D_max≤1e−9 điểm phần trăm thì chọn
   mean ΔMDD nhỏ hơn, rồi C0,C1,C2,C3,C3_stats_only,C3_examples_only.
4. Không ai đạt: giữ Original cho triển khai. Có thể khóa một ứng viên
   nghiên cứu **NOT_PROMOTED** từ tập đủ completion/exposure theo cùng thứ
   tự D/MDD/ID. Tập này rỗng thì chưa đủ khả thi, Gate C BLOCKED; không tự
   chọn ứng viên thiếu dữ liệu hoặc gọi Original là thành công của v2.

Primary cần đủ toàn ma trận; partial chỉ provisional, không promote.
Fallback hợp lệ vẫn là complete; lỗi/unknown không đổi thành CASH. Báo
global common support và support từng cặp. Ablation báo toàn cohort và tập
bổ sung **cả stats/examples ready**; ngoài tập này, chênh lệch còn gồm bật/
tắt contract. Trace tự báo cáo không chứng minh quan hệ nhân quả hoặc sự
tuân thủ prior. Cặp thành phần: C1−C0, C2−C1, C3−C2, C3−hai ablation;
mọi ứng viên mới báo thêm Δ so C0 và Original.

Không sweep đến khi có lời. Thay registry/ngưỡng/model cần amendment trước
run mới, lý do và hash riêng; giữ toàn bộ lượt trước, công bố tổng số cấu
hình đã thử. Active registry≤6 không có nghĩa tổng số thử≤6. Model không
khả dụng phải dừng, không âm thầm thay model ở một nhánh. Không có task
dự toán ngân sách hoặc lịch chạy API; guard/quota thực tế vẫn bắt buộc.

#### Hợp đồng report ghép cặp W7-03

Đây là đặc tả cho producer/verifier **W7-05–07**; report v3 hiện hữu chưa
có đủ các trường dưới. Khi triển khai phải tăng version, giữ reader của
bằng chứng cũ; chưa tạo JSON/schema runtime không có consumer.

Gọi P_s là lịch planned của mã s, C_b,s là các điểm của nhánh b có Decision,
nguồn và evaluation đã verify complete. **G_s=∩_b C_b,s** trên đủ 11 nhánh;
**S_a,b,s=C_a,s∩C_b,s** cho từng cặp. Lưu point ID/ngày theo thứ tự tăng và
count cho cả hai support. Mỗi cặp tái dựng **cả hai tài khoản** trên cùng S,
vốn 50 triệu/mã, giá/phí/lot theo engine; G dùng cho primary. Support rỗng
trả null, không tạo return 0; nhóm theo regime cũng dựng lại trên tập ngày
của nhóm, chỉ là mô tả, không cộng các return nhóm thành return toàn mã.

| Nhóm trường bắt buộc | Đơn vị, mẫu số và quy tắc |
| --- | --- |
| Identity | Version report/metric, cohort/split/matrix, execution mode; checksum plan, registry, code/runtime, nguồn/index/model và checkpoint dùng tính. Chỉ `development_2023` với Decision thật đủ điều kiện lựa chọn thực; fixture ghi rõ kiểm protocol |
| Completion | Theo mã/nhánh: `planned`, `complete`, `pending`, `failed`, `unknown` là count nguyên không âm; bốn trạng thái sau phân hoạch planned theo trạng thái durable hiện tại, không đếm lại các attempt lỗi đã phục hồi. `missing_result=planned−complete` là tổng thiếu kết quả, không cộng thêm lần nữa. Thiếu checkpoint/nguồn bắt buộc hoặc integrity sai phải ném lỗi, không đổi thành pending/CASH |
| Support | `global_common_support`, `pairwise_support`, count và các point bị loại kèm lý do. Complete/fallback chỉ được tính sau verifier; lượt retry không tăng số point. Pairwise đầy đủ không cứu primary thiếu G |
| Hiệu quả tài khoản | `total_return_pct=100×(E_final/50.000.000−1)`, `max_drawdown_pct=100×max(1−E_i/max_{j≤i}E_j)`; equity gồm vốn đầu và cuối mỗi chu kỳ, MDD≥0. Δreturn/ΔMDD là A−B, đơn vị điểm phần trăm; VND chỉ cho equity/P&L, không trộn với tỷ lệ |
| Nhãn/return chu kỳ | Point ID, cutoff, entry/exit ngày phiên; `net_return_long`, `cycle_net_return` và `period_returns` là số thập phân (0,01=1%), không phải %. Nhãn LONG giả định qua `compute_round_trip_net_return`; account return vẫn do engine vốn/lot/phí tính, không lấy tổng hoặc mean nhãn |
| Phân loại/action | LONG dự đoán UP, SHORT dự đoán DOWN/CASH; nhãn UP khi net LONG>0, bằng 0 là DOWN. Lưu confusion counts, `long_count`, `cash_count`; accuracy, balanced accuracy, LONG hit-rate, participation/cash rate đều [0,1]. Balanced accuracy=(recall_UP+recall_DOWN)/2; thiếu lớp=null/MISSING_CLASS, không LONG=null/NO_LONG; N=0: phân loại/tài khoản=null/NO_SUPPORT, risk giữ reason của version chu kỳ |
| Coverage/exposure | Theo mã/regime/nhánh: planned, complete, feature AVAILABLE/UNAVAILABLE, stats/examples ready, visible/off và reason counts. Coverage completion/visibility chia planned, visibility trên complete báo thêm mẫu số riêng; planned=0 trả null/NO_PLANNED. Readiness cần evidence đã verify; chưa có evidence ghi unknown, không gán UNAVAILABLE hoặc ready=false |
| Prior hiển thị | Đếm point complete có ít nhất một metric/example **thực xuất hiện trong prefix khớp Decision đã verify**, không dùng retrieved_k hoặc self-report `prior_use`; request chỉ dựng nhưng chưa có Decision không tăng exposure. Lưu retrieved/visible IDs, visible metric IDs, prefix/request/base evidence hash, fallback reason; C0 dùng evidence/prefix legacy đã kiểm. `prior_visible_count` mỗi point tối đa 1, stats_only vẫn có thể exposed dù visible_k=0 |
| Rủi ro/CASH | Sharpe/Sortino chu kỳ giữ `cycle_risk_metrics_v2`, không annualize, ddof=1 và downside trên toàn N; N<2 trả null/N_LT_2, nếu N≥2 và mẫu số≤1e−12 trả null/ZERO_DENOMINATOR. CASH reference trên chính support: return/MDD=0 khi N>0, không giả LONG hit-rate |
| Attribution | Raw action=executed action khi risk OFF; SHORT ánh xạ CASH. Giữ nhãn/return LONG giả định tách action; trace N/A khi contract không yêu cầu, thiếu trace bắt buộc là lỗi integrity. Không coi trace tự báo cáo là chứng cứ nhân quả |

**Primary:** chỉ COMPLETE khi G_s=P_s ở cả bốn mã (12/16/16/16), đủ 60 điểm
và đúng 11 nhánh. Mỗi candidate có ΔR_s và ΔMDD_s so Original trên G_s;
D và mean ΔMDD là trung bình đều **bốn mã**, không trọng số 12/16 hoặc
trung bình return từng cycle. Nếu thiếu bất kỳ điểm/nhánh: INCOMPLETE,
D primary=null; metric trên support quan sát ghi provisional, không dùng
chọn/promote. Giá trị dùng so ngưỡng/tie giữ độ chính xác đầy đủ, không làm
tròn trước lựa chọn; null/NaN/Infinity không được thay 0 hoặc dùng xếp hạng.
JSON chỉ dùng kiểu Python gốc/hữu hạn; point trùng/ngoài plan, count hoặc
support không khớp checkpoint đều là lỗi integrity, không âm thầm bỏ dòng.

**Các cặp khóa trước xem kết quả:** mười nhánh khác Original so Original;
C1/C2/C3/hai ablation so C0; C2−C1, C3−C2 và C3−C3_stats_only,
C3−C3_examples_only. Loại cặp trùng, giữ chiều A−B. Mỗi cặp báo ΔR/ΔMDD,
confusion/action counts và disagreement=count(action_A≠action_B)/|S|;
hai chiều LONG/CASH và CASH/LONG cộng bằng disagreement count. Cặp với
Original có subgroup candidate prior-off; cặp còn lại có subgroup cả hai
prior-off. Mỗi subgroup ghi support/mẫu số, không thay primary.

**Ablation nội dung:** tập T_s là các điểm trên G_s mà base evidence C3 đã
verify có **stats_ready AND examples_ready**, cùng base hash cho cả ba C3.
So ba C3 trên toàn G và riêng T; kiểm contract active ở cả ba trên T.
T rỗng → NO_SUPPORT, không bù từ tập chỉ một block ready. Coverage theo
regime lấy regime PIT ở ngày query, giữ nhóm không có mẫu/null và giới hạn
BEAR=0; không gán regime từ outcome hoặc dựng portfolio của các nhóm.

**Ca LONG khi bằng chứng bất lợi:** cờ mô tả cho từng metric đã hiển thị:
`Win.posterior_mean<0.5` hoặc một trong
`Trap/TrendFail/PatternFail.posterior_mean>0.5`; đúng 0.5 là trung tính.
Dùng mean đầy đủ từ evidence đã verify, chỉ metric visible và ready mới
được xét; metric ẩn/null là N/A. Win/Trap/TrendFail/PatternFail ánh xạ
`win_rate_long`, `bull_trap_rate`, `trend_false_bullish_rate`,
`pattern_false_bullish_rate`.
Báo point ID, metric/mean/support/interval, action, economic outcome và
count LONG trên tập có cờ, kèm mẫu số theo mã/candidate. Đây là ngưỡng mô tả
đăng ký trước phân tích, không thêm quality
gate, policy override hay yêu cầu model tuân theo prior.

#### Hợp đồng quyết định lựa chọn

W7-07 phải bind artifact quyết định với report/checkpoint/plan/registry/
source/code/runtime hash và version quy tắc này; verifier tái tính support,
metrics, eligibility và thứ tự, không chỉ nhận checksum tự khai. Không nhận
holdout hoặc fixture như bằng chứng nomination thực.

Eligibility cần gate kỹ thuật PASS, primary COMPLETE, đủ 60 paired points,
return/MDD dùng lựa chọn hữu hạn và visibility≥6/60 với ≥1 ở **mỗi mã**.
Balanced accuracy/LONG hit-rate null hợp lệ không làm candidate bị loại.
Báo từng điều kiện và reason; trên primary COMPLETE, visibility=0 ghi
NO_EXPOSURE, dưới ngưỡng hoặc thiếu mã ghi INSUFFICIENT_EXPOSURE.
D/ΔMDD không là điều kiện exposure. Trong tập eligible,
tập promote còn cần D>0, ΔR_s>0 ở≥3 mã, mean ΔMDD≤2 và max ΔMDD_s≤5.
Chọn D_max trong tập đang xét; **chỉ** các D_max−D≤1e−9 mới vào tie, sau đó
mean ΔMDD nhỏ nhất, rồi thứ tự ID đã khóa. Không nối chuỗi các tie lân cận;
không thêm tolerance MDD hoặc làm tròn D để tạo hòa.

| `nomination_status` | `research_candidate` | `deployment_choice` và gate |
| --- | --- | --- |
| PROMOTED | ID đứng đầu tập promote | Cùng ID; đây là đề cử development, chưa chứng minh lợi ích holdout |
| NOT_PROMOTED | ID đứng đầu tập eligible theo D/MDD/ID | Original; giữ kết quả bất lợi và ứng viên nghiên cứu để kiểm W8 |
| BLOCKED | null | Original chỉ là mặc định giữ nguyên; chưa mở Gate C/manifest holdout. Dùng khi primary thiếu, gate kỹ thuật chưa PASS hoặc eligible rỗng; ghi reason cụ thể |

#### Oracle số học cho fixture W7-05/07

Đây là kỳ vọng độc lập cho kiểm thử sau, **chưa là selector đã triển khai**.
Trừ dòng nêu khác, giả định gate PASS, đủ 60 điểm/11 nhánh, visibility theo
FPT/VNM/VCB/MWG là (1,1,2,2), ΔR=(4,2,1,−1) pp và ΔMDD=(5,1,1,1) pp;
chỉ một candidate được xét. Các vector giữ cùng thứ tự bốn mã.

| Ca | Đầu vào/thay đổi | Kỳ vọng |
| --- | --- | --- |
| O01 — Tài khoản | Equity cuối chu kỳ A=(50,55,44,52.8), B=(50,50,50,50), triệu VND, gồm vốn đầu | R_A=5,6%, MDD_A=20%; R_B=MDD_B=0; ΔR=5,6 pp, ΔMDD=20 pp. Không lấy mean return chu kỳ làm account return |
| O02 — Biên đạt | ΔR=(4,2,1,−1), ΔMDD=(5,1,1,1), visible=6 | D=1,5 pp, 3 mã dương, mean ΔMDD=2 pp, max=5; PROMOTED, nhận đúng biên 6/60, 2 và 5 |
| O03 — D=0 | ΔR=(1,1,1,−3) | D=0 dù 3 mã dương; NOT_PROMOTED, deployment Original |
| O04 — Thiếu mã dương | ΔR=(4,2,0,−1) | D=1,25 nhưng chỉ 2 mã dương; NOT_PROMOTED |
| O05 — Mean MDD vượt | ΔMDD=(5,1,1,1.0004) | Mean=2,0001; NOT_PROMOTED, không làm tròn thành 2 |
| O06 — Một mã MDD vượt | ΔMDD=(5.0004,0,0,0) | Mean=1,2501 nhưng max>5; NOT_PROMOTED |
| O07 — Exposure | Visible=(1,1,1,2), hoặc (0,2,2,2); trường hợp mọi point chỉ retrieved nhưng prefix rỗng | Hai trường hợp đầu INSUFFICIENT_EXPOSURE dù trường hợp hai đủ 6; trường hợp cuối NO_EXPOSURE. Nếu không còn eligible: BLOCKED, research_candidate=null |
| O08 — Unknown/missing | Một nhánh random unknown ở một point, các nhánh còn lại complete; hoặc thiếu checkpoint bắt buộc | G=59, cặp C0−Original có thể đủ 60 nhưng primary INCOMPLETE/D=null, BLOCKED; không đổi unknown thành CASH. Thiếu checkpoint bắt buộc phải ném lỗi |
| O09 — Thiếu lớp | Hai nhãn UP,UP; action LONG,SHORT | Accuracy=0,5; balanced accuracy=null/MISSING_CLASS; LONG hit-rate=1; participation=cash rate=0,5 |
| O10 — CASH/rỗng | Hai nhãn UP,DOWN, đều SHORT; hoặc N=0 | CASH: R=MDD=0, accuracy=balanced accuracy=0,5, hit-rate=null/NO_LONG, Sharpe/Sortino=null/ZERO_DENOMINATOR; null này không tự loại candidate đủ completion/exposure. N=0: phân loại/tài khoản=null/NO_SUPPORT, risk=null/N_LT_2 |
| O11 — Tie D/MDD/ID | C0: D=1.5/MDD=2; C1: D=1.5000000005/MDD=1; riêng hai ablation cùng D=1.5/MDD=1 | Trường hợp đầu chọn C1 trong tie quanh D_max; trường hợp hai chọn C3_stats_only theo ID |
| O12 — Không nối tie | C0/C1/C2 có D=1.5/1.5000000005/1.500000002; mean MDD=0/0/2, đều đạt | Chỉ C2 trong khoảng 1e−9 của D_max; chọn C2 dù MDD cao hơn |
| O13 — Không ai promote | Hai eligible C0/C1 có ΔR_s đều −0.1/−0.2 pp, MDD=0 | Research C0, NOT_PROMOTED, deployment Original; không đổi thành PROMOTED hoặc BLOCKED |
| O14 — Ready/visible | Base C3 chỉ stats ready; hoặc cả hai ready nhưng stats_only có visible_k=0; visible Win mean=0.49 so với 0.5 | Trường hợp đầu không vào T; trường hợp hai vào T và stats_only vẫn exposed nhờ metric. Cờ bất lợi chỉ bật cho Win=0.49 đã hiển thị, 0.5 trung tính |

**W7-03 DONE:** hợp đồng và oracle trên đã khóa cho Phase B. Kiểm số học,
đối chiếu hàm metric/trace hiện hữu, checklist/liên kết/hash PASS; chưa viết
selector hoặc đọc kết quả holdout. Gate A còn **W7-04**.

## 3. Checklist và phụ thuộc

| Phase | Task | Công việc | Phụ thuộc | Trạng thái |
| --- | --- | --- | --- | --- |
| A | W7-01 | Xác minh bàn giao và khoảng trống implementation | W6 đóng | [x] DONE |
| A | W7-02 | Khóa phạm vi train/development và protocol validation | 01 | [x] DONE |
| A | W7-03 | Đặc tả report ghép cặp và quy tắc lựa chọn | 02 | [x] DONE |
| A | W7-04 | Tái kiểm train PIT trên phiên bản bàn giao | 03 | [x] DONE |
| B | W7-05 | Hoàn thiện report common support và metric | Gate A | [x] DONE |
| B | W7-06 | Phân tích disagreement, prior-use và ablation | 05 | [ ] TODO |
| B | W7-07 | Bộ chọn ứng viên và artifact quyết định có verifier | 06 | [ ] TODO |
| B | W7-08 | Protocol/CLI holdout có ràng buộc lựa chọn | 07 | [ ] TODO |
| B | W7-09 | Hồi quy trước API và khóa run development | 08 | [ ] TODO |
| C | W7-10 | Người dùng chạy validation development bốn mã | Gate B | [ ] TODO |
| C | W7-11 | Đối soát và phân tích kết quả development | 10 | [ ] TODO |
| C | W7-12 | Quyết định ứng viên, cấu hình và risk OFF | 11 | [ ] TODO |
| D | W7-13 | Khóa ma trận và mục tiêu kiểm định W8 | Gate C | [ ] TODO |
| D | W7-14 | Khóa manifest holdout và dry-run offline | 13 | [ ] TODO |
| D | W7-15 | Nghiệm thu code/config/source cuối | 14 | [ ] TODO |
| D | W7-16 | Chốt W7 và bàn giao thực thi W8 | 15 | [ ] TODO |

### Phase A — Khóa thiết kế validation

#### W7-01 — Xác minh bàn giao và khoảng trống implementation

- **Làm:** kiểm Git/source/runtime/hash từ W6-16; đọc report train,
  performance, plan development và registry; lập bản đồ producer/consumer
  cho metric, selector, CLI, checkpoint và holdout.
- **Đầu ra:** cập nhật mục 1 và checklist này, chỉ rõ phần đã có/cần bổ sung.
- **Đạt khi:** nguồn/identity kiểm được, W6 vẫn 16/16, không đọc key hoặc
  sửa artifact lịch sử; phát hiện thiếu nguồn thì ghi BLOCKED cùng cách khôi phục.

#### W7-02 — Khóa phạm vi train/development và protocol validation

- **Làm:** chốt vai trò dữ liệu tại mục 2.1, 651 query kỹ thuật và 60 điểm
  LLM development; giữ 2024 ngoài chọn cấu hình. Ghim registry, model/options,
  thứ tự nhánh, economic contract và quy tắc amendment trước API.
- **Đầu ra:** protocol trong README; schema runtime chỉ thêm khi có consumer.
- **Đạt khi:** phân biệt rõ PIT diagnostics với hiệu quả LLM; không dùng
  mock/ca pilot làm mẫu validation, không tự thu hẹp hoặc mở rộng lịch đã khóa.

#### W7-03 — Đặc tả report ghép cặp và quy tắc lựa chọn

- **Làm:** xác định trường dữ liệu/đơn vị/null, global/pairwise support,
  coverage từng mã/regime, D/ΔMDD, tie-break và trạng thái lựa chọn tại mục 2.2.
  Khóa các cặp so sánh và tập stats+examples ready trước xem kết quả mới.
- **Đầu ra:** hợp đồng report/decision, bảng oracle số học nhỏ cho fixture.
- **Đạt khi:** quy tắc W6-04 được giữ đúng; oracle bao gồm missing/unknown,
  no-exposure, thiếu lớp, không LONG, tie và candidate không được promote.

#### W7-04 — Tái kiểm train PIT trên phiên bản bàn giao

- **Làm:** verify report train v2 đúng index/fold/model prefix, tái kiểm
  purge và mature prior; đối chiếu coverage/readiness trước development.
  Nếu identity đổi, sinh report phiên bản mới và giải thích diff.
- **Đầu ra:** report kiểm được; tóm tắt các chẩn đoán thay đổi trong README.
- **Đạt khi:** 852 replay/651 query đủ provenance; giữ 121 query barrier,
  C rỗng/null và nhóm không phơi nhiễm. Không dùng model cuối 2022 cho fold sớm.

##### Tái kiểm nguồn thật, 13/10/2026

**Verifier production PASS:** dựng lại **852/852 replay**, **651 query**,
**201** bootstrap và so bằng toàn bộ report v2 trên index W6 đã khóa.
Không dùng mặc định report v1 có code identity lịch sử:

```powershell
py -3.13 -X utf8 scripts/run_bayesian_ablation.py --verify-train --train-report outputs/bayesian_benchmark/train_validation_v2.json --train-index outputs/bayesian_benchmark/price_features/train_validation_index_v1.json
```

Code/runtime và **1.947 nguồn ghim** khớp report. **217** model/proof đúng
cutoff gồm 165 HMM và 52 MULTI_FACTOR fallback; verifier nạp artifact prefix
và tái tính scaler/calibration số học, không fit lại HMM hoặc dùng model
cuối 2022 thay cho các prefix sớm.

Audit độc lập trên report/bank xác nhận fit/purge theo exit thật: hai fold
2021/2022 có **197/526** episode fit trước lọc feature, **166/428** sau lọc,
**329/322** query. Mỗi fold purge **4** cycle (một/mã) có exit bằng ngày đầu
fold; mọi episode fit có exit<đầu fold. **6.515 lượt ID được chọn** qua sáu
candidate đều cùng mã/regime và exit<query; đây là lượt lặp giữa candidate,
không phải số episode độc lập. Tái đếm độc lập eligible/population từ bank
khớp cả 651 query × 6 candidate; verifier còn tái dựng evidence từ nguồn.

Diagnostics giữ nguyên bàn giao W6: feature **530/651**, **121** barrier
`CORPORATE_ACTION_WINDOW`; **263** query C rỗng giữ posterior/CrI null.
C3 stats/examples hiển thị **95/358**, cùng ready **76/651**; các count
candidate/fallback chi tiết giữ như W6-14, không đổi ngưỡng để tăng coverage.
Đây là readiness theo content mode trong diagnostics, chưa phải exposure
Decision thật dùng xét eligibility ở W7-03.
Giữ đủ **192** nhóm mã/fold/regime/candidate, tất cả có query; **92** nhóm
không hiển thị stats và **92** không hiển thị examples (gồm ablation),
không loại nhóm này khỏi báo cáo. Tin reliable **0/651** vẫn là giới hạn.

**9 kiểm thử train/PIT PASS** (gồm 3 leakage): entry/exit/index, model tương
lai/frozen, sửa nến tương lai, scaler/calibration, purge/nhóm rỗng/null,
report tự băm lại, thiếu provenance và CLI offline. Không có Decision hoặc
kết luận lợi ích LLM; nhóm NO_EXPOSURE tổng hợp vẫn được giữ trong fixture.

**W7-04 DONE:** không có thay đổi diagnostics hoặc identity cần revision;
giữ report v2/index, **2.317 file bằng chứng nguyên byte**. Verify chạy với
guard chặn `.env`/API; không sinh Decision, return LLM, selection hoặc đọc
outcome holdout. Chỉ ba Markdown thay đổi; code/test/runtime khớp W6-16,
kế thừa compileall/E2E, **784 unit/146 leakage PASS** của cùng mã nguồn,
không chạy lại toàn suite. Kiểm mới là verifier nguồn thật và 9 test nêu trên.

**Gate A PASS, 13/10/2026:** 01–04 DONE; đặc tả protocol/metric/quy tắc lựa
chọn đã khóa, train PIT PASS. Mở Phase B với **W7-05**; selector/report mới
còn chờ 05–09, chưa có candidate được chọn hoặc mở lượt API development.

### Phase B — Hoàn thiện công cụ và đóng băng code trước API

#### W7-05 — Hoàn thiện report common support và metric

- **Làm:** mở rộng `core/research_metrics.py` theo hợp đồng 03; tái dựng
  return/MDD trên cùng tập ngày, báo planned/complete/failed/unknown/fallback,
  global/pairwise support và metric theo mã, regime, candidate.
- **Đầu ra:** report có version và verifier tái tính từ checkpoint gốc.
- **Đạt khi:** oracle số học độc lập PASS; sửa outcome, support hoặc thứ tự
  ngày bị phát hiện; JSON native/finite, nhóm thiếu dữ liệu giữ null/reason.

##### Implementation report v4, 13/10/2026

**W7-05 DONE.** `research_cohort` nạp mọi slot đã verify, kể cả point
v1 chưa seal hoặc candidate chưa xong; đánh giá riêng từng Decision complete
bằng cùng economic engine. `research_metrics.research_report` nối sang
`core/paired_candidate_report.py`, giữ producer/reader legacy v2/v3.

- Report `research_report_v4` có G đủ 11 nhánh, S của **19 cặp** đã khóa,
  excluded point/reason, metrics và CASH reference trên cùng support theo
  mã/regime. Return/MDD và delta giữ đơn vị/độ chính xác W7-03; primary là
  trung bình đều bốn mã, partial giữ null/provisional.
- Count complete/pending/failed/unknown phân hoạch planned; retry đã phục
  hồi không đếm lại. Coverage tách readiness, visible/off, feature và lỗi;
  chưa có evidence giữ unknown, request chưa complete không tăng exposure.
  Readiness dùng gate của base evidence, visibility dùng content mode thực;
  stats_only vẫn exposed khi có metric visible dù không có example.
- Binding khóa plan/registry/code/runtime/model/index/nguồn và hash các
  checkpoint/journal dùng tính. Loader/verifier dựng lại từ checkpoint đã
  kiểm, so cả support/metric/thứ tự ngày; artifact tự băm lại không đủ.
  CLI mới `--verify-report --plan PLAN --output-dir RUN` kiểm cả report đã
  lưu và telemetry, offline không key/API. `--verify-only` vẫn dựng lại
  report từ checkpoint; report thiếu/stale cần đối soát, không tự ghi đè.
- Giữ nguyên artifact W6. Code identity đã đổi: plan/train/performance cũ
  thuộc checkout `a87091d`; không sửa hash để nhận code mới. W7-09 khóa
  plan/run và bằng chứng theo code cuối trước API; chưa tạo plan thật mới.

Disagreement/prior-use/ablation chi tiết thuộc W7-06, selector thuộc W7-07;
report v4 chưa phải quyết định lựa chọn hoặc bằng chứng hiệu quả LLM.

**Nghiệm thu:** compileall/E2E, **795 unit/148 leakage PASS**, không skip;
**14 test trọng tâm PASS**, gồm 11 test mới (2 leakage). Oracle xác nhận
equity 50→55→44→52,8 triệu: return 5,6%/MDD 20%; khi mất chu kỳ −20%,
G trả 32% còn cặp đủ S vẫn 5,6%, primary thiếu giữ null. Kiểm cả trung bình
đều mã, CASH/nhóm rỗng/null, stats_only, pending/failed/unknown, report tự
băm lại và CLI offline; 44 Decision/4 upstream, verify/resume không gọi lại
complete. **2.317 file bằng chứng nguyên byte**, chưa chạy API hoặc tạo
plan/run dữ liệu thật mới. **Gate B còn W7-06–09**, tiếp theo W7-06.

#### W7-06 — Phân tích disagreement, prior-use và ablation

- **Làm:** đối chiếu Original/C0/C1/C2/C3 và hai ablation; thống kê LONG
  khi bằng chứng bất lợi, action khi prior-off, retrieved/visible IDs và
  mức độ trace hợp lệ. Định nghĩa ca bất lợi bằng trường/ngưỡng đã khóa ở 03.
- **Đầu ra:** bảng toàn cohort và subgroup ready; danh sách ca có point ID
  để kiểm lại, gồm cả kết quả thuận lợi/bất lợi trên nhiều mã/ngày.
- **Đạt khi:** không chọn riêng ca FPT 20/02; không ép model theo prior,
  không thêm LLM judge hoặc suy ra nhân quả từ trace tự báo cáo.

#### W7-07 — Bộ chọn ứng viên và artifact quyết định có verifier

- **Làm:** triển khai eligibility, D/MDD/tie-break và fallback tại mục 2.2;
  bind quyết định với report/checkpoint/registry/code/runtime/source hashes.
  Tách ứng viên nghiên cứu được khóa với lựa chọn triển khai Original/v2.
- **Đầu ra:** producer/loader/verifier quyết định có version; đường output mới.
- **Đạt khi:** selector không nhận dữ liệu 2024; fixture kiểm các biên 6/60,
  đủ bốn mã, 60 paired, D=0, ΔMDD=2/5, tie 1e−9, NOT_PROMOTED và tập rỗng;
  tự băm lại quyết định giả không vượt được verifier semantic.

#### W7-08 — Protocol/CLI holdout có ràng buộc lựa chọn

- **Làm:** bổ sung phiên bản plan/identity/consumer cho holdout, yêu cầu
  quyết định đã verify và registry/model/economic contract đúng. Giữ ma
  trận 11 nhánh; gắn rõ primary candidate được chọn, các đối chứng/ablation.
  Kế thừa lịch W5 bằng checksum, không sửa validator v3 để nhận sai schema.
- **Đầu ra:** CLI/schema/checkpoint/report có version và fixture tổng hợp.
- **Đạt khi:** fixture bốn mã kiểm một Full/point, cap, durable/unknown/
  resume và source tampering PASS; không có selection hợp lệ thì chặn trước
  API. Chưa tạo/chạy manifest holdout nguồn thật hoặc xem outcome 2024.

#### W7-09 — Hồi quy trước API và khóa run development

- **Làm:** hoàn tất code từ 05–08, chạy bốn gate kỹ thuật và fault matrix;
  kiểm train/hiệu năng theo identity hiện tại. Khóa commit/code/runtime,
  prepare plan/output development mới và dry-run đủ bốn mã.
- **Đầu ra:** artifact development sẵn dùng và lệnh thực tế trong README
  cho prepare/dry-run/preflight/run/verify/reconcile/resume từng mã.
- **Đạt khi:** 60 ngày/11 nhánh đúng registry, old files nguyên byte;
  source/code/config sai chặn trước API. Report hiệu năng đúng identity,
  retrieval p95<30 ms theo protocol W6-15; prefix/feature/cold báo riêng.
  Đo lại khi phiên bản/điều kiện đo không còn phù hợp, giữ cả lượt FAIL.

**Gate B:** 05–09 DONE, bốn gate PASS, công cụ phân tích/lựa chọn/holdout đã
có consumer và fixture; plan development hiện tại dry-run PASS. Chốt code
trước API để tránh kết quả development mất khả năng verify sau đổi code.

### Phase C — Development thực và quyết định lựa chọn

#### W7-10 — Người dùng chạy validation development bốn mã

- **Làm:** người dùng tự chạy preflight text/vision, rồi FPT/MWG/VCB/VNM
  theo lệnh 09; dùng ledger chung, retry/pacer, checkpoint sau mỗi điểm.
  Agent kiểm offline kết quả được tạo; không tự đọc key/chạy API.
- **Đầu ra:** durable raw/trace/checkpoint của 60 điểm × 11 nhánh đã đăng ký.
- **Đạt khi:** đủ điểm/nhánh hợp lệ; quota/cooldown được resume đúng identity,
  unknown chỉ replay sau đối soát UUID/lý do. API chưa chạy thì task chờ
  người dùng, không đánh DONE bằng fixture hoặc bỏ điểm thiếu để đủ tỷ lệ.

#### W7-11 — Đối soát và phân tích kết quả development

- **Làm:** verifier semantic toàn run; tái tính report 05/06 và kiểm nguồn,
  prompt/evidence/raw action/executed action/nhãn kinh tế. Báo toàn bộ ứng
  viên, từng mã/regime, cặp thành phần, prior-off và ablation readiness.
- **Đầu ra:** report development đã verify, bảng D/ΔR/ΔMDD/exposure và lỗi.
- **Đạt khi:** common support toàn ma trận đủ 60; return dùng cùng ngày/
  vốn/phí; không missing bị đổi thành CASH. Partial giữ provisional và
  quay lại 10 xử lý, chưa dùng selector để promote.

#### W7-12 — Quyết định ứng viên, cấu hình và risk OFF

- **Làm:** chạy selector 07 trên report 11; ghi quyết định/promoted hoặc
  NOT_PROMOTED, lựa chọn triển khai, lý do và kết quả của mọi ứng viên.
  Ghim model/client/prompt/K/threshold/versions; risk giữ OFF.
- **Đầu ra:** artifact lựa chọn bất biến và phần kết quả gọn trong README.
- **Đạt khi:** verifier tái lập đúng eligibility/tie-break; không chỉnh ngưỡng
  sau xem kết quả để lấy ứng viên thắng. Nếu C0 được chọn, không gán lợi ích
  cho module retrieval/contract mới. Tập khả thi rỗng thì Gate C BLOCKED.

**Gate C:** 10–12 DONE; đủ development thật, selection kiểm được. Không cần
ứng viên thắng để thông qua nếu khóa được ứng viên nghiên cứu NOT_PROMOTED
đúng quy tắc; không gọi kết quả development là bằng chứng xác nhận cuối.

### Phase D — Khóa đánh giá xác nhận và bàn giao W8

#### W7-13 — Khóa ma trận và mục tiêu kiểm định W8

- **Làm:** bind ứng viên ở 12 vào ma trận 11 nhánh, K=3; primary là ứng viên
  đã khóa so Original trên 64 điểm. Ghi secondary so C0/cặp thành phần/
  ablation, hướng hiệu ứng và đơn vị phân tích trước đọc outcome holdout.
- **Đầu ra:** protocol đánh giá có version, nêu common support, missing,
  coverage, thước đo và giới hạn đa so sánh/phụ thuộc thời gian. Đặc tả
  McNemar/Wilcoxon/block-bootstrap theo mục tiêu tương ứng; chốt cách xử lý
  cụm ngày/mã, block, số lần resample, seed, mức CI và đa so sánh trước W8.
- **Đạt khi:** không đổi candidate theo 2024; không nhân đôi nhánh nếu
  primary chính là C0. Khóa kế hoạch kiểm định/CI W9 trước W8; sensitivity
  ngoài ma trận chính cần protocol riêng, chưa đăng ký thì ghi exploratory.

#### W7-14 — Khóa manifest holdout và dry-run offline

- **Làm:** dùng consumer 08 tạo manifest mới từ selection/protocol đã khóa,
  nguồn/lịch W5 64 điểm, scaler/model cuối train; ghim code/schema/runtime/
  registry/config và source hashes. Khóa output riêng khỏi mọi run cũ.
- **Đầu ra:** manifest holdout kiểm được, dry-run offline bốn mã.
- **Đạt khi:** đúng 16 điểm/mã, selection không phụ thuộc outcome 2024;
  metadata/nguồn sai bị chặn, không refit/tune trên holdout. Chưa chạy
  upstream/Decision, chưa xuất nhãn/return/equity của 2024 trong W7.

#### W7-15 — Nghiệm thu code/config/source cuối

- **Làm:** kiểm bốn gate, verifier manifest/selection/report, fault/resume
  và các hash sau merge; đối chiếu economic/PIT/paired/cap/risk OFF.
  Giữ các bằng chứng hiệu năng đúng phiên bản và runtime.
- **Đầu ra:** kết quả gate gọn trong README và artifact cuối bất biến.
- **Đạt khi:** không còn mismatch code/runtime/config hoặc lỗi integrity.
  Nếu sửa code sau lượt development, giữ checkout/identity cũ để verify;
  phải chứng minh thay đổi chỉ vận hành bằng parity hoặc chạy development
  mới nếu ảnh hưởng evidence/prompt/action/metric/lựa chọn. Không sửa hash
  checkpoint cũ để nhận code mới; manifest cuối phải được tạo lại tên mới.

#### W7-16 — Chốt W7 và bàn giao thực thi W8

- **Làm:** cập nhật checklist/plan tổng; bàn giao selection, protocol,
  manifest/output và lệnh thực CLI cho từng mã; cách xử lý dừng/unknown,
  verify/resume, vị trí kết quả và các hạn chế còn lại.
- **Đầu ra:** README này làm sổ bàn giao, không thêm receipt lặp lại.
- **Đạt khi:** 01–15 DONE, Gate A/B/C và bốn gate kỹ thuật PASS, manifest
  cuối kiểm được; đánh **16/16 DONE, Gate D PASS** để mở W8. Thiếu API hoặc
  lựa chọn chưa đủ điều kiện thì giữ đúng trạng thái chờ/BLOCKED của task.

**Gate D:** 13–16 DONE, selection/protocol/manifest bất biến và bàn giao
đủ cho người dùng tự chạy W8; chưa chạy benchmark 2024 trong W7.

## 4. Tổ chức implementation và kiểm thử

- Ưu tiên mở rộng `core/research_metrics.py`, `core/candidate_cohort.py`,
  `core/research_cohort.py`, `core/train_pit_validation.py` và
  `scripts/run_bayesian_ablation.py`. Selector có thể tách module nhỏ;
  không xây runner/API client mới nếu luồng hiện tại đáp ứng được.
- Đường runtime mới đặt dưới `outputs/bayesian_benchmark/`, tên có revision;
  mỗi schema/JSON mới phải có producer, loader, verifier và test consumer.
  README giữ checklist/phương pháp/kết quả; chưa tạo sẵn receipt/JSON rỗng.
- Mỗi task dùng branch riêng từ `develop`, commit Conventional Commits
  mô tả kỹ thuật, không có ký hiệu tuần. Merge sau bốn gate theo AGENTS.md:

```powershell
py -3.13 -m compileall agents core data_manager scripts tests utils
py -3.13 -X utf8 -m unittest discover -s tests -v
py -3.13 scripts/run_end_to_end_test.py
py -3.13 -X utf8 -m unittest discover -s tests -p "test_*leakage.py" -v
```

Kiểm riêng các biên lựa chọn, null/no-exposure, full/partial support, hai
thành phần prior không cùng ready, đảo/sửa nguồn, future model/scaler,
crash trước intent/sau durable, unknown/quota và đổi cấu hình giữa mã.
Fixture chỉ kiểm tính đúng; dữ liệu thật mới dùng để kết luận hiệu quả.

Các giới hạn phải theo sang W8/W9: BEAR OOS=0, tin reliable=0, FPT Q1 thiếu
bốn mẫu, 121/651 query train barrier và C3 stats/examples chỉ 95/358 query;
PIT hồi cứu không chứng nhận vintage provider hoặc kiến thức LLM lịch sử.
Giữ kết quả bất lợi, fallback/null, số lượt thử và giới hạn cỡ mẫu.

## 5. Nhật ký tiến độ

PLAN_READY là kế hoạch; chỉ đánh DONE task sau khi đủ tiêu chí của task đó.

| Ngày | Mốc | Kết quả | Tiếp theo |
| --- | --- | --- | --- |
| 12/10/2026 | Lập kế hoạch | PLAN_READY; 4 phase/16 task, 0/16 DONE. Đối chiếu bàn giao W6 và CLI thực; giữ registry/quy tắc lựa chọn, risk OFF, API do người dùng chạy. Chưa triển khai task hoặc chạy validation W7 | W7-01 |
| 12/10/2026 | W7-01 | DONE, 1/16; nguồn/runtime/registry/hash PASS, 1.992 nguồn và 2.317 file bằng chứng nguyên byte. Dry-run 60 điểm và verifier hiệu năng 651 query PASS offline; bản đồ module/khoảng trống ở mục 1. Gate A còn 02–04 | W7-02 |
| 12/10/2026 | W7-02 | DONE, 2/16; protocol mục 2.1 khóa vai trò 651 query train/60 điểm development/64 holdout, model/client/registry và amendment trước API. Đối chiếu cấu hình nguồn/code, checklist/liên kết/hash PASS; chỉ ba Markdown, kế thừa bốn gate W6-16 của cùng code/runtime. Gate A còn 03–04 | W7-03 |
| 12/10/2026 | W7-03 | DONE, 3/16; hợp đồng report/support/đơn vị/null, visibility, cặp/ablation/ca bất lợi và nomination tại mục 2.2; 14 oracle fixture kiểm số học/biên PASS. Chỉ ba Markdown; 2.317 file nguyên byte, cùng code/runtime kế thừa bốn gate W6-16. Gate A còn 04 | W7-04 |
| 13/10/2026 | W7-04 | DONE, 4/16; Phase A DONE / Gate A PASS. Verifier production dựng lại 852 replay/651 query, report v2 khớp đầy đủ; purge/mature/scaler/prefix và 9 test train/PIT (3 leakage) PASS. Diagnostics không đổi, 2.317 file nguyên byte; readiness chưa là exposure Decision, không API/holdout | W7-05 |
| 13/10/2026 | W7-05 | DONE, 5/16; Phase B IN_PROGRESS. Report v4 nối checkpoint partial, G/19 cặp S, metric/coverage theo mã/regime, binding và CLI verifier; giữ legacy v2/v3. Compileall/E2E, 795 unit/148 leakage PASS, không skip; 11 test mới, 14 trọng tâm PASS. 2.317 file nguyên byte; identity mới khóa ở 09 trước API, Gate B còn 06–09 | W7-06 |

Kiểm khi lập kế hoạch (12/10/2026): checklist/đánh số/phụ thuộc/liên kết và `git diff --check`.
Code/test không đổi so với mốc W6-16 đã qua bốn gate (784 unit/146 leakage);
kế thừa kết quả của cùng mã nguồn, không chạy lại suite cho thay đổi Markdown.
Đối chiếu 2.317 file bằng chứng/artifact nguyên byte; chưa mở Gate A của W7.
