# Tuần 7 — Validation, chọn ứng viên và bàn giao cải tiến Bayesian ICL

**Trạng thái: Phase A/B/C DONE / Gate A/B/C PASS, 14/16 task hoàn thành; Phase D IN_PROGRESS.**
Ngày lập: **12/10/2026**; cập nhật: **16/10/2026**. Tiếp theo **W7-15**.
[Kế hoạch tổng](../plan.md) · [Bàn giao W6](../week6/README.md)

## Điều chỉnh kế hoạch ngày 16/10/2026

Theo yêu cầu tiếp tục cải thiện Bayesian ICL, **Phase D chưa thực hiện được
thay thế** bằng chẩn đoán và bàn giao W8. Giữ nguyên nghiệm thu W7-01–12, Gate A/B/C
PASS, C2 NOT_PROMOTED và Original triển khai; không sửa selection cũ.
Giữ **10 tuần**: W8 cải tiến/validation và khóa cấu hình; W9 benchmark
kết hợp thống kê; W10 luận văn/bảo vệ. Mọi mô tả khóa holdout tại W7-14 hoặc benchmark W8 bên dưới thuộc
thiết kế trước điều chỉnh; Phase D mới và mục 5.5 kế hoạch tổng có hiệu lực.
Consumer holdout hiện hữu vẫn được giữ, chỉ hoãn tạo manifest thật đến cuối W8.
Chi tiết: [W8](../week8/README.md), [W9](../week9/README.md).

## 1. Mục tiêu và đầu vào

W7 kiểm chứng các ứng viên trên train/development, đưa ra quyết định chọn
có thể tái lập; Phase D mới bàn giao cải tiến W8 trước benchmark 2024 ở W9. Hoàn thành kế
hoạch này chưa có nghĩa đã chạy validation hoặc tìm được ứng viên tốt hơn.

| Đầu vào đã có | Cách dùng trong W7 |
| --- | --- |
| W6 đóng 16/16, Gate A/B/C/D PASS; merge `0b24b38` | Mốc đối chiếu; compileall/E2E, 784 unit/146 leakage PASS |
| Bank 852 episode, model/proof theo cutoff; train report v2 | Kiểm PIT cuốn chiếu trên 651 query, bootstrap 2020; giữ nguyên bằng chứng W6 |
| Registry `prior_candidates_v1`, plan `research_cohort_plan_v3` | Sáu ứng viên C0, C1, C2, C3, C3_stats_only, C3_examples_only; năm đối chứng v1 |
| Plan development v1 đã prepare/dry-run | Đúng 60 điểm 2023: FPT 12, MWG/VCB/VNM 16 mỗi mã; chưa gọi Decision/API |
| Lịch W5: 64 điểm holdout 2024, 16/mã | Chỉ khóa manifest cuối sau quyết định lựa chọn; W9 mới thực thi |
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
| Quyết định lựa chọn | `candidate_selection_v1` có producer/loader/verifier, bind report/checkpoint/nguồn/gate | Chưa có nomination development thật; fixture luôn BLOCKED / NOT_APPLICABLE |
| Holdout ứng viên | Protocol v4 có selection binding, checkpoint riêng và report v6; v3 vẫn chỉ fixture/development | Chưa tạo manifest holdout thật; chỉ chuẩn bị sau Gate C ở W7-14 |
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
  dry-run theo kế hoạch mới cuối W8; W9 thực thi. Phát hiện lỗi nguồn phải dừng và ghi cách khôi phục,
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
| NOT_PROMOTED | ID đứng đầu tập eligible theo D/MDD/ID | Original; giữ kết quả bất lợi và ứng viên nghiên cứu để kiểm W9 |
| BLOCKED | null | Original chỉ là mặc định giữ nguyên; chưa mở Gate C/manifest holdout. Dùng khi primary thiếu, gate kỹ thuật chưa PASS hoặc eligible rỗng; ghi reason cụ thể |

#### Oracle số học cho fixture W7-05/07

Đây là kỳ vọng độc lập đã khóa ở W7-03, dùng kiểm report/bộ chọn W7-05/07;
không là kết quả nomination bằng dữ liệu thật.
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
| B | W7-06 | Phân tích disagreement, prior-use và ablation | 05 | [x] DONE |
| B | W7-07 | Bộ chọn ứng viên và artifact quyết định có verifier | 06 | [x] DONE |
| B | W7-08 | Protocol/CLI holdout có ràng buộc lựa chọn | 07 | [x] DONE |
| B | W7-09 | Hồi quy trước API và khóa run development | 08 | [x] DONE |
| C | W7-10 | Người dùng chạy validation development bốn mã | Gate B | [x] DONE |
| C | W7-11 | Đối soát và phân tích kết quả development | 10 | [x] DONE |
| C | W7-12 | Quyết định ứng viên, cấu hình và risk OFF | 11 | [x] DONE |
| D | W7-13 | Chẩn đoán nút thắt và kiểm attribution | Gate C | [x] DONE |
| D | W7-14 | Khóa protocol vòng cải tiến | 13 | [x] DONE |
| D | W7-15 | Kiểm nguồn và khả năng tái lập | 14 | [ ] TODO |
| D | W7-16 | Bàn giao triển khai cải tiến W8 | 15 | [ ] TODO |

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

##### Implementation phân tích prior, 13/10/2026

Report `research_report_v5` bổ sung `prior_disagreement_analysis_v1` từ
checkpoint đã verify, theo toàn cohort, từng mã và từng regime PIT:

- **19 cặp** có bảng action 2×2 và disagreement/mẫu số. Subgroup prior-off
  dùng nhánh A khi so Original, cả A/B ở các cặp khác; retrieved riêng lẻ
  không là exposure, unknown/pending không được coi CASH. Tài khoản và
  Δreturn/ΔMDD của subgroup được dựng lại trên cùng support từng mã.
- Ba C3 được so trên G và T **stats_ready AND examples_ready**; kiểm cùng
  base hash/readiness và contract active trên T. T rỗng giữ NO_SUPPORT/null;
  cohort chỉ gộp count, không ghép tài khoản của các mã thành portfolio.
- Giữ mọi ca complete với point ID/ngày/mã/regime, raw action, economic
  outcome, retrieved/visible IDs, hash và trace. Cờ bất lợi xét mean đầy đủ
  của metric visible/ready theo ngưỡng 03; ghi support/CrI và LONG trên tập
  có cờ. Metric ẩn/null và tỷ lệ v1 không có posterior giữ N/A.
- Trace bắt buộc thiếu/sai IDs là lỗi integrity; contract legacy giữ N/A.
  NOT_USED hợp lệ và được giữ nguyên, không ép hướng hoặc thêm LLM judge.
  Trace hợp lệ chỉ xác nhận schema/IDs, không chứng minh model dùng prior.
- `--verify-report` tái dựng cả phân tích, phát hiện sửa count, support,
  metric hoặc trace rồi tự băm lại; reader giữ version v2/v3/v4. Module mới
  được ghim vào code identity; artifact W6 và plan cũ giữ nguyên.

**W7-06 DONE:** compileall/E2E, **805 unit/148 leakage PASS**, không skip;
**20 kiểm thử trọng tâm PASS**, toàn suite gồm **10 test mới** về phân tích.
Oracle kiểm disagreement hai chiều, prior-off/unknown, ngưỡng 0,5 đầy đủ,
metric ẩn/N/A, support điều kiện và trace thiếu/sai. Tài khoản ba chu kỳ
return 5,6% được dựng lại thành 32% trên T bỏ chu kỳ −20%; giữ ca thuận/bất
lợi ở cả bốn mã/ba ngày, không chỉ một pilot. Checkpoint/CLI verify và
resume không gọi lại Decision complete; report tự băm lại vẫn bị chặn khi
sửa phân tích. **2.317 file bằng chứng nguyên byte**, chưa chạy API/
development thật, chọn ứng viên hoặc đọc outcome holdout.
**W7 đạt 6/16; Gate B còn W7-07–09**, tiếp theo W7-07.

#### W7-07 — Bộ chọn ứng viên và artifact quyết định có verifier

- **Làm:** triển khai eligibility, D/MDD/tie-break và fallback tại mục 2.2;
  bind quyết định với report/checkpoint/registry/code/runtime/source hashes.
  Tách ứng viên nghiên cứu được khóa với lựa chọn triển khai Original/v2.
- **Đầu ra:** producer/loader/verifier quyết định có version; đường output mới.
- **Đạt khi:** selector không nhận dữ liệu 2024; fixture kiểm các biên 6/60,
  đủ bốn mã, 60 paired, D=0, ΔMDD=2/5, tie 1e−9, NOT_PROMOTED và tập rỗng;
  tự băm lại quyết định giả không vượt được verifier semantic.

##### Implementation bộ chọn, 13/10/2026

`core/candidate_selection.py` tạo `candidate_selection_v1` theo
`development_nomination_rules_v1`, giữ nguyên ngưỡng tại mục 2.2:

- Tái đếm G từ trạng thái đủ 11 nhánh, kiểm lịch 12/16/16/16 và exposure
  từ prefix/visible IDs của Decision complete. D/ΔMDD lấy từ hai tài khoản
  từng mã, trung bình đều bốn mã; không dùng cached D hoặc retrieved count.
  Mỗi candidate có conditions/reasons riêng; null phân loại/risk hợp lệ
  không làm candidate mất eligibility.
- Xếp riêng tập eligible/promote; tie chỉ quanh D_max, sau đó MDD/ID.
  NOT_PROMOTED vẫn giữ research candidate, deployment Original; BLOCKED
  giữ null/Original. Fixture/mock chỉ có `fixture_protocol_result`, artifact
  cấp trên luôn BLOCKED/NOT_APPLICABLE, không dùng đề cử thật.
- Binding gồm rule/report/file/checkpoint/plan/registry/code/runtime/
  source/index/model/gate hashes. CLI dựng lại report từ nguồn/checkpoint,
  kiểm semantic report rồi tái tính toàn quyết định; tự băm lại artifact
  sửa eligibility, status, ngưỡng hoặc binding vẫn bị chặn.
- Hai chế độ offline `--select-candidate` / `--verify-selection` dùng
  `--plan PLAN --output-dir RUN`, tùy chọn `--technical-gates GATES` và
  `--selection-output candidate_selection_v1.json`. Output tương đối trong
  RUN, bất biến/idempotent, không ghi đè quyết định khác. Nếu report/gate
  thay đổi, dùng đường quyết định mới; không sửa hash để nhận run cũ.
- Receipt gate có payload `gate_version=research_technical_gates_v1`, `code_sha256`,
  `runtime`, `checks` đủ compileall/unit/e2e/leakage. Mỗi check có status,
  exit_code và log path/hash; path tương đối với receipt. PASS cần exit 0,
  log thành công (unit/leakage không skip), đúng code/runtime của report.
  Thiếu receipt → NOT_VERIFIED/BLOCKED; gate FAIL/NOT_RUN → BLOCKED;
  log/hash/identity sai là lỗi integrity. W7-09 khóa receipt theo code cuối,
  không gán PASS từ log thuộc checkout khác.

**23 kiểm thử trọng tâm PASS**, gồm 22 test mới (4 leakage): các biên lựa
chọn, tie không nối chuỗi, NOT_PROMOTED, thiếu lớp/không LONG, nguồn thiếu/
unknown, holdout cutoff/entry/exit, giả mạo artifact và CLI không key/HTTP.
**W7-07 DONE:** compileall/E2E, **827 unit/152 leakage PASS**, không skip.
Oracle nhận đúng biên 6/60, D=1,5/mean ΔMDD=2/max=5; D=0, MDD vượt biên,
thiếu mã dương giữ NOT_PROMOTED; no-exposure/thiếu gate/primary giữ BLOCKED.
Kiểm cả tie 1e−9 không nối chuỗi, null hợp lệ và NOT_PROMOTED giữ ứng viên
nghiên cứu/Original deployment. CLI verify tái dựng nguồn và phát hiện
quyết định/report tự băm lại; các chế độ select/verify không key/HTTP,
không gọi lại Decision complete. **2.317 file bằng chứng nguyên byte**.
Chưa đề cử candidate bằng development thật, chạy API hoặc mở manifest
holdout. **W7 đạt 7/16; Gate B còn W7-08–09**, tiếp theo W7-08.

#### W7-08 — Protocol/CLI holdout có ràng buộc lựa chọn

- **Làm:** bổ sung phiên bản plan/identity/consumer cho holdout, yêu cầu
  quyết định đã verify và registry/model/economic contract đúng. Giữ ma
  trận 11 nhánh; gắn rõ primary candidate được chọn, các đối chứng/ablation.
  Kế thừa lịch W5 bằng checksum, không sửa validator v3 để nhận sai schema.
- **Đầu ra:** CLI/schema/checkpoint/report có version và fixture tổng hợp.
- **Đạt khi:** fixture bốn mã kiểm một Full/point, cap, durable/unknown/
  resume và source tampering PASS; không có selection hợp lệ thì chặn trước
  API. Chưa tạo/chạy manifest holdout nguồn thật hoặc xem outcome 2024.

**Consumer:** `core/holdout_protocol.py` khóa schema `research_cohort_plan_v4`,
matrix `selection_bound_holdout_v1` và identity v4. Selection binding gồm
plan/run development, selection và receipt gate theo checksum, cùng ledger.
Verifier dựng lại development v3 từ checkpoint bằng transport cấm mạng,
đối chiếu toàn report/selection/gate trước API. Plan giữ registry/model/index,
hợp đồng kinh tế và lịch holdout **64 điểm W5** nguyên checksum; validator
v3 vẫn chỉ nhận fixture/development. Thiếu selection, BLOCKED hoặc identity/
nguồn khác đều chặn holdout thật. NOT_PROMOTED giữ research candidate làm
primary nghiên cứu, deployment vẫn Original.

CLI prepare dùng `--prepare --plan DEVELOPMENT --holdout-plan NEW
--development-run RUN --technical-gates RECEIPT --output-dir HOLDOUT_RUN`, đọc selection đã khóa
trong RUN (tên mặc định `candidate_selection_v1.json`; đổi bằng
`--selection-output`). Các chế độ dry-run/preflight/run/verify-report/
reconcile/resume tiếp tục dùng `--plan` v4 và output riêng. Prepare chỉ
ghi plan, không tạo manifest; **chỉ chuẩn bị plan thật ở W7-14 sau Gate C**.

Checkpoint candidate có version `holdout_candidate_slot_v1` /
`holdout_candidate_decision_v1`, vẫn tái dùng journal upstream đã kiểm.
Report v6 công bố selection binding, primary cố định, control/ablation và
`HOLDOUT_NOT_FOR_SELECTION`; selector development không nhận v6. Fixture
chỉ dùng C3 cố định để kiểm protocol, giữ nomination BLOCKED /
`NOT_APPLICABLE`, không thay thế selection thật và không đổi thành 2024.

**W7-08 DONE:** compileall/E2E, **837 unit/156 leakage PASS**, không skip.
**10 fixture mới (4 leakage)** và 9 hồi quy report PASS: bốn mã/44 Decision,
một Full/point, cap, crash sau durable, unknown/replay đúng UUID, source/
selection/report tự băm lại và CLI không key/HTTP. Kiểm byte checkpoint/
report/selection loại riêng audit owner/phục hồi khóa OS vốn thay đổi sau
mỗi lần verify. **200 file Python khớp bản kiểm thử; 2.317 file bằng chứng
nguyên byte**. Chưa chạy API, đề cử development thật, tạo manifest hoặc xem
outcome holdout thật. **W7 đạt 8/16; Gate B còn W7-09**, tiếp theo W7-09.

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

##### Artifact và điều kiện nghiệm thu

Production/test giữ nguyên từ commit `5bd4cfc`, Python **3.13.5**; không
đổi registry/K=3/seed=42/model/client/economic contract. Train v3 tạo và
verify đủ **852 replay/651 query**; so với v2 chỉ khác `code_sha256`, giữ
nguyên nguồn, fold/scaler, 121 barrier, 263 C rỗng/null và các nhóm không
phơi nhiễm. Readiness chưa phải exposure hoặc hiệu quả Decision thật.

Plan development v2 prepare/dry-run **4/4 mã PASS**, giữ **60 điểm/11 nhánh**:
FPT 12, MWG/VCB/VNM 16 mỗi mã. Sáu ca tự băm lại plan sai code/runtime/
registry/model/lịch/nguồn đều chặn trước key/API; tokenizer cache hợp lệ.
Output mới trống, chưa khởi tạo `cohort.json` hoặc chạy Decision.

**Hiệu năng:** giữ cả lượt v3 mặc định **FAIL** và lượt v4 **PASS trên
worker P-core**. Trên i7-14650HX này, CPU Sets cho class 1 ở logical 0–15;
worker v4 ghim mask `0xFFFF`, thay cho mask mặc định `0xFFFFFF`. Chỉ affinity
của worker thay đổi, không đổi power plan toàn máy, priority, code/dữ liệu,
warm-up/mẫu/ngưỡng, không bỏ outlier hoặc cache đáp án. Đây là điều kiện
đo được kiểm soát, không phải cải tiến thuật toán hoặc chứng nhận p95 ở
mọi cấu hình máy. Cách diễn giải CPU class/affinity theo
[Microsoft CPU Sets](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-system_cpu_set_information)
và [process affinity](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setprocessaffinitymask).
Giữ [log mặc định FAIL](validation_gates/performance_default_fail.log) và
[log v4 có mask worker](validation_gates/performance_controlled.log) để
đối chiếu điều kiện đo; report JSON giữ nguyên schema producer hiện hữu.

Cùng **651 query**, same_symbol, **100 warm-up/1.000 mẫu** mỗi mode/stage;
p95 nearest-rank. Ngưỡng **<30 ms chỉ áp dụng retrieval**. Producer và
verifier v4 **PASS**, kiểm toàn nguồn/semantic/percentile từ mẫu thô;
verifier không đo lại hoặc ghi report. Bốn gate mới **PASS**, không skip:
compileall, **837 unit/156 leakage**, E2E. [Receipt kỹ thuật](validation_gates/technical_gates_v1.json)
được consumer kiểm theo code/runtime và SHA-256 của cả bốn log; SHA byte
receipt `7515ec6b195a2557f218e00028c169fb70d865ad68d2ce7f9a178df4cc3766a4`.
Audit sau kiểm thử: **200 file Python** đúng bản đã chạy, **2.317 file cũ**
và **bốn artifact mới** nguyên byte. **W7-09 DONE / Gate B PASS; W7 đạt 9/16.**
Chưa gọi API, chạy Decision, đề cử ứng viên hoặc tạo manifest holdout thật.

| Cấu hình | Retrieval v3 mặc định ms | Retrieval v4 P-core ms | Prefix v4 ms | Retrieval+prefix v4 ms | Feature RAM+retrieval+prefix v4 ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| Bayesian v1 | 5,372 | 3,463 | 0,064 | 3,145 | 3,393 |
| C0 | 11,340 | 6,328 | 1,777 | 7,838 | 6,934 |
| C1 | 33,898 | 21,039 | 30,692 | 49,798 | 89,646 |
| C2 | 30,683 | 21,675 | 29,451 | 45,155 | 69,261 |
| C3 | 31,625 | 14,593 | 21,297 | 40,951 | 85,128 |
| C3_stats_only | 33,124 | 21,074 | 28,683 | 43,740 | 85,215 |
| C3_examples_only | 31,880 | 17,808 | 23,982 | 41,566 | 78,660 |

Baseline legacy 16 context/hai scope có p95 retrieval v3 **23,315–29,419 ms**,
v4 **14,630–18,207 ms**, đều PASS; không gộp với v1 cùng 651 query trong
bảng. Feature extractor RAM v4 p95 **47,525 ms**. Cold tách riêng: adapter
**10,459 s**, index load/semantic rebuild **27,940 s**, tái tạo/fit index
độc lập **27,164 s**, chuẩn bị nguồn tổng **67,491 s**, parity trước timer
**63,063 s**. Không I/O/refit/LLM trong hot query; Decision=0.

Các artifact runtime dưới `outputs/bayesian_benchmark/` thuộc gitignore;
giữ cùng nguồn local. SHA-256 byte đã khóa:

| Artifact | SHA-256 |
| --- | --- |
| `train_validation_v3.json` | `233d41ab74bbb2b60bef9ec60ec5b13cf3eaac38d6d0f158d75e6751431dee62` |
| `development_candidate_plan_v2.json` | `e0c32d272d93bd7b3fa87c08c6a70b4851d2cdcbd620675976b4e9c8f7e95960` |
| `prior_performance_v3.json` — FAIL mặc định | `32f328e06d907fdc404f6c9afb8cc475fbbd64eb4ecf79692b9ed954842b9c08` |
| `prior_performance_v4.json` — PASS P-core | `e80560da6d8af18cfd63ba849de73b4c40b035095c033380d601a8be7f33e801` |

Khi cần tái đo, dùng tên mới và không chạy unit/gate đồng thời. Lệnh sau
chỉ tái lập điều kiện **máy này** (P-core 0–15); máy khác cần kiểm CPU Sets
trước, không mặc định dùng cùng mask. `start /b /wait /affinity` áp mask
cho worker, không mở cửa sổ mới ([Microsoft start](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/start)).

```powershell
cmd /d /c 'start "" /b /wait /affinity FFFF py -3.13 -X utf8 scripts/run_bayesian_ablation.py --benchmark-prior --performance-report outputs/bayesian_benchmark/prior_performance_v5.json'
py -3.13 -X utf8 scripts/run_bayesian_ablation.py --verify-performance --performance-report outputs/bayesian_benchmark/prior_performance_v5.json
```

##### Lệnh development theo bản đóng băng

Chạy từ gốc repository. Dùng tên artifact mới; các bản W6/v1/v2 lịch sử
giữ nguyên byte. Đổi code/nguồn/model cần khóa lại plan/output và gate;
không sửa checksum để tiếp tục run cũ. API/model chỉ được người dùng xác
nhận bằng preflight ở W7-10. Risk policy giữ OFF.

```powershell
$trainReport = "outputs/bayesian_benchmark/train_validation_v3.json"
$trainIndex = "outputs/bayesian_benchmark/price_features/train_validation_index_v1.json"
$performanceReport = "outputs/bayesian_benchmark/prior_performance_v4.json"
$candidatePlan = "outputs/bayesian_benchmark/development_candidate_plan_v2.json"
$candidateRun = "outputs/bayesian_benchmark/development_candidate_run_v2"
$priceIndex = "outputs/bayesian_benchmark/price_features/candidate_index_v1.json"
$technicalGates = "docs/plan/week7/validation_gates/technical_gates_v1.json"
$ledger = "outputs/oos_pilot/api_usage.json"

py -3.13 -X utf8 scripts/run_bayesian_ablation.py --verify-train --train-report $trainReport --train-index $trainIndex
py -3.13 -X utf8 scripts/run_bayesian_ablation.py --verify-performance --performance-report $performanceReport
py -3.13 -X utf8 scripts/run_bayesian_ablation.py --prepare --plan outputs/bayesian_benchmark/smoke_plan.json --candidate-plan $candidatePlan --candidate-split development_2023 --price-index $priceIndex --output-dir $candidateRun
py -3.13 -X utf8 scripts/run_bayesian_ablation.py --dry-run --plan $candidatePlan --output-dir $candidateRun
$cohortArgs = @("--plan", $candidatePlan, "--output-dir", $candidateRun, "--ledger", $ledger, "--quota-policy", "request_admission_v2")
```

Các lệnh trên offline. Prepare chỉ tạo/đối chiếu plan; không tạo cohort
manifest hoặc gọi Decision. Receipt `$technicalGates` được selector đọc
ở W7-12; chưa chạy selector khi development chưa đủ 60 điểm thật.

**Người dùng thực hiện ở W7-10 sau Gate B PASS.** Cần tokenizer cache đúng
checksum và key riêng trong `.env`; nếu thiếu cache, chạy
`py -3.13 scripts/prepare_groq_tokenizer.py` trước. Giữ ledger chung khi
đổi key. Chạy từng lệnh, chỉ sang mã tiếp theo sau exit code 0:

```powershell
py -3.13 -X utf8 scripts/run_bayesian_ablation.py --preflight @cohortArgs
if ($LASTEXITCODE -ne 0) { throw "Preflight chưa PASS; chưa chạy development." }

# Chỉ lượt đầu khi chưa có cohort.json dùng lệnh không --resume.
py -3.13 -X utf8 scripts/run_bayesian_ablation.py --run --symbol FPT @cohortArgs
if ($LASTEXITCODE -ne 0) { throw "FPT dừng; kiểm verify/reconcile rồi resume FPT." }
py -3.13 -X utf8 scripts/run_bayesian_ablation.py --run --resume --symbol MWG @cohortArgs
if ($LASTEXITCODE -ne 0) { throw "MWG dừng; kiểm verify/reconcile rồi resume MWG." }
py -3.13 -X utf8 scripts/run_bayesian_ablation.py --run --resume --symbol VCB @cohortArgs
if ($LASTEXITCODE -ne 0) { throw "VCB dừng; kiểm verify/reconcile rồi resume VCB." }
py -3.13 -X utf8 scripts/run_bayesian_ablation.py --run --resume --symbol VNM @cohortArgs
if ($LASTEXITCODE -ne 0) { throw "VNM dừng; kiểm verify/reconcile rồi resume VNM." }

py -3.13 -X utf8 scripts/run_bayesian_ablation.py --verify-only @cohortArgs
py -3.13 -X utf8 scripts/run_bayesian_ablation.py --verify-report @cohortArgs
```

Khi đã có `cohort.json`, mọi lượt chạy tiếp cần `--resume`. Verify và
reconcile không gọi API, kiểm toàn cohort kể cả mã không được chọn.
Nếu dừng trước khi ghi report cuối, dùng verify-only/reconcile trước;
verify-report chỉ PASS khi report đã lưu khớp checkpoint hiện tại.

```powershell
py -3.13 -X utf8 scripts/run_bayesian_ablation.py --verify-only @cohortArgs
py -3.13 -X utf8 scripts/run_bayesian_ablation.py --reconcile @cohortArgs
# Chỉ thay UUID sau khi đã đối soát attempt thực và quyết định cho replay.
py -3.13 -X utf8 scripts/run_bayesian_ablation.py --reconcile --authorize-replay "UUID_DA_DOI_SOAT" --replay-reason "Lý do đối soát attempt thực" @cohortArgs
# Sau đối soát, chỉ chạy lệnh resume của mã cần hoàn tất.
py -3.13 -X utf8 scripts/run_bayesian_ablation.py --run --resume --symbol FPT @cohortArgs
py -3.13 -X utf8 scripts/run_bayesian_ablation.py --run --resume --symbol MWG @cohortArgs
py -3.13 -X utf8 scripts/run_bayesian_ablation.py --run --resume --symbol VCB @cohortArgs
py -3.13 -X utf8 scripts/run_bayesian_ablation.py --run --resume --symbol VNM @cohortArgs
```

Unknown giữ reserve, không tự replay. Chờ hết quota/cooldown, giữ ledger,
lock và lịch gốc; response complete được tái dùng. Không đổi plan/code
sau API nếu chưa có amendment và lượt kiểm lại phù hợp.

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

##### Amendment vận hành 15/10/2026 — quota ngày do provider quyết định

**Yêu cầu người dùng:** bỏ admission ngày tự tính trong ledger; khi key hết
quota thì đổi key và resume cùng lượt. Thay đổi này thay thế đề xuất phân
quota theo organization trước đó. Mốc kiểm tra trước cutover: **FPT 9/12,
9/60 điểm đủ 11 nhánh, 99/660 Decision**, chưa có report cuối. Không dùng
return/holdout để chọn thay đổi; **tại thời điểm amendment, W7-10 giữ IN_PROGRESS**,
không tăng số task DONE. Kết quả hoàn tất ngày 16/10 được ghi bên dưới.

- `core/provider_quota.py` và `scripts/run_provider_validation.py` là phần
  mở rộng vận hành riêng. **200 file Python cũ giữ nguyên**, gồm CLI/pacer/
  validator nghiên cứu; không đổi checksum plan/identity/checkpoint để né
  verifier. Entrypoint mới thay riêng factory quota một cách tường minh và
  kiểm amendment trước khi đọc key; runner/graph/prompt vẫn là bản đã khóa.
- Policy `provider_daily_quota_v1` không phát `DAILY_QUOTA` từ ngân sách
  RPD/TPD local. Ledger tổng vẫn giữ toàn usage; số dư local chỉ tham khảo.
  Groq quyết định quota thực qua header/HTTP, vẫn có quyền từ chối request.
  Các key cùng organization vẫn chia sẻ giới hạn phía
  [Groq](https://console.groq.com/docs/rate-limits); không cam kết key mới
  luôn có quota. Không tự đổi model/limits hoặc xoay key trong tiến trình.
- Cooldown và pacing phút theo fingerprint SHA-256 có domain riêng của key;
  không lưu key thô. Giữ trần token/request, ba HTTP/120 giây nghỉ chung,
  backoff/429, khóa ledger/run, checkpoint, PIT, kinh tế và paired protocol.
  Key mới tự preflight text/vision đúng plan; cùng key dùng lại proof PASS.
- Ledger cũ không ghi organization/key; không gán lại hay giả lập lịch sử.
  Request mới thêm `credential_scope`, `daily_policy` và
  `operational_amendment_sha256`. Toàn bộ request trước cutover được băm,
  checkpoint/response complete cũ được giữ nguyên byte. Request sau cutover
  thiếu audit hoặc sửa/xóa usage cũ làm verifier amendment dừng.
- Replay có audit đúng UUID chỉ tự thực hiện khi mọi HTTP của attempt là
  **429 đã từ chối**, khớp run/point, hoặc có stop trước HTTP được chứng minh
  là `PROVIDER_DAILY_QUOTA`. Chỉ dùng đường reconcile gốc; không tự replay
  `transport_error`, response 200 bị mất hoặc lỗi chưa rõ kết quả.
- `provider_quota_amendment.json` trong run-dir khóa plan/cohort/ledger,
  nguồn mở rộng, runtime, receipt bốn gate mới và bằng chứng trước cutover.
  Mã phương pháp/model/lịch/registry/K/seed/metric/risk OFF không đổi;
  không chạy lại upstream hoặc Decision complete. Holdout chưa được mở.

**Kiểm thử mở rộng:** 22 test trọng tâm, **859 unit/163 leakage**, compileall
và E2E **PASS**, không skip. 205 file Python đúng bản đã kiểm; 200 file gốc
và 493 file runtime trước thay đổi nguyên byte. 2.314 bằng chứng lịch sử tĩnh
nguyên byte; ledger/metadata khóa đã thay đổi hợp lệ sau các lượt API của
người dùng. Receipt SHA-256 `1b1bf0196305dbb96b7a1ce63cc15e79da9ea35a97296c0371d31f6036f6cac4`.
Receipt dùng riêng
[`technical_gates_provider_v1.json`](validation_gates/technical_gates_provider_v1.json);
receipt W7-09 giữ nguyên. Nguồn mở rộng có hash riêng trong amendment,
không được giả là đã nằm trong code map nghiên cứu cũ.
Amendment cục bộ đã tạo và verify offline, khóa **72 file complete**
và **309 request lịch sử**; không gọi API thật.
Plan/cohort/checkpoint cũ giữ nguyên hash, không replay upstream hoặc Decision complete.

**Lệnh thay thế cho lượt đang chạy:** dùng duy nhất entrypoint mới kể từ
cutover, kể cả verify/reconcile/report/selection. Không dùng lại lệnh run
cũ vì policy cũ vẫn tính quota ngày local. Chạy từ gốc repo:

```powershell
$cliPath = "scripts/run_provider_validation.py"
$runDir = "outputs/bayesian_benchmark/development_candidate_run_v2"
$cohortArgs = @(
    "--plan", "outputs/bayesian_benchmark/development_candidate_plan_v2.json",
    "--output-dir", $runDir,
    "--ledger", "outputs/oos_pilot/api_usage.json",
    "--quota-policy", "request_admission_v2"
)

# Chỉ tạo một lần sau bốn gate PASS; chạy lại chỉ đối chiếu amendment đã khóa.
py -3.13 -X utf8 $cliPath --prepare-amendment @cohortArgs
if ($LASTEXITCODE -ne 0) { throw "Amendment chưa hợp lệ; chưa chạy API." }

py -3.13 -X utf8 $cliPath --verify-only @cohortArgs
if ($LASTEXITCODE -ne 0) { throw "Checkpoint/amendment chưa hợp lệ." }

# Key mới được đọc từ .env và tự preflight trước khi chạy tiếp bốn mã.
py -3.13 -X utf8 $cliPath --run --resume @cohortArgs
if ($LASTEXITCODE -ne 0) { throw "Run đã dừng; đọc nguyên nhân trước khi tiếp tục." }
```

Khi Groq báo hết quota: đợi tiến trình thoát, đổi `GROQ_API_KEY` trong `.env`,
rồi chạy lại **cùng lệnh `--run --resume`**; không xóa ledger/checkpoint và
không prepare plan mới. Nếu lỗi truyền tải/unknown chưa rõ kết quả, chạy
`--verify-only`, `--reconcile`, đối soát attempt và dùng
`--reconcile --authorize-replay UUID --replay-reason LY_DO` trước resume.
Không dùng vòng lặp authorize mọi unknown. Sai integrity/runtime/source,
model không khả dụng hoặc header limit thay đổi thì dừng để kiểm tra.

Sau khi đủ bốn mã:

```powershell
py -3.13 -X utf8 $cliPath --verify-only @cohortArgs
if ($LASTEXITCODE -ne 0) { throw "Checkpoint/amendment chưa hợp lệ." }
py -3.13 -X utf8 $cliPath --verify-report @cohortArgs
if ($LASTEXITCODE -ne 0) { throw "Report chưa hợp lệ." }
```

Chỉ chốt 10 khi report `primary_status=COMPLETE`, đủ FPT 12 và MWG/VCB/VNM
16 điểm mỗi mã, không còn missing/failed/unknown. Receipt kỹ thuật mới
được dùng cho selector ở 12; không lấy report partial để promote.

##### Kết quả validation development, 16/10/2026

**W7-10 DONE.** Người dùng đã hoàn tất run
`outputs/bayesian_benchmark/development_candidate_run_v2`. Verifier offline
qua entrypoint provider kiểm amendment/nguồn/runtime/checkpoint và tái dựng
report **PASS**: `research_report_v5`, `primary_status=COMPLETE`, execution
mode `research`, đúng **60/60 điểm, 660/660 Decision** trên đủ 11 nhánh.
FPT **12/12**, MWG/VCB/VNM **16/16** mỗi mã; mọi nhánh có pending/failed/
unknown/missing_result **0**. Fallback hợp lệ vẫn complete, không thay lỗi
thành CASH. Upstream Pattern/Trend có đúng **60 response 200 mỗi agent**;
Decision có **660 response 200**, giữ giao thức paired và risk OFF.

Lịch sử HTTP của run vẫn giữ **793 attempt: 780 response 200, 7 HTTP 429,
6 transport_error**; không xóa attempt đã phục hồi hoặc gọi chúng là lỗi
checkpoint hiện tại. Telemetry ghi **1.533.468 token** trên 780 response có
usage; 13 attempt còn lại thiếu usage, không coi là 0. Agent chỉ kiểm
offline, không đọc `.env` hoặc gọi thêm API. Holdout 2024 chưa mở.

Report đã lưu tại
[`report.json`](../../../outputs/bayesian_benchmark/development_candidate_run_v2/report.json),
SHA-256 file `57026e012e3fa6032ad81bbe6100af580fd0a59900f3d1f9370fdb32941ed1c8`;
binding khóa **485 file checkpoint**. Giữ nguyên report/plan/cohort/ledger/
amendment và bằng chứng đã complete. **W7 đạt 10/16**, tiếp theo W7-11;
Gate C còn đối soát/phân tích và quyết định W7-12.

#### W7-11 — Đối soát và phân tích kết quả development

- **Làm:** verifier semantic toàn run; tái tính report 05/06 và kiểm nguồn,
  prompt/evidence/raw action/executed action/nhãn kinh tế. Báo toàn bộ ứng
  viên, từng mã/regime, cặp thành phần, prior-off và ablation readiness.
- **Đầu ra:** report development đã verify, bảng D/ΔR/ΔMDD/exposure và lỗi.
- **Đạt khi:** common support toàn ma trận đủ 60; return dùng cùng ngày/
  vốn/phí; không missing bị đổi thành CASH. Partial giữ provisional và
  quay lại 10 xử lý, chưa dùng selector để promote.

##### Kết quả đối soát và phân tích, 16/10/2026

**W7-11 DONE.** `--verify-only` và `--verify-report` qua entrypoint provider
**PASS offline**; verifier dựng lại nguồn/PIT, shared upstream, evidence,
prefix/prompt, raw response/action, execution và nhãn kinh tế rồi so toàn
report v5, kể cả phân tích v1 của W7-06 và telemetry. Common support G đủ
**60 điểm/11 nhánh**; toàn bộ **19 cặp** có S=60, không loại điểm hoặc đổi
missing thành CASH. Mỗi tài khoản dùng đúng ngày/support, vốn 50 triệu,
lot/phí engine và `compute_round_trip_net_return`; SHORT giữ CASH, risk OFF.
Report giữ nguyên SHA-256 đã ghi ở W7-10; không cần sửa code hay tạo thêm
artifact phân tích trùng với report đã có consumer/verifier. Prompt dài nhất
trong 660 Decision là **4.581 ký tự** (đính chính tại W7-13: 4.534 là mức
tối đa của sáu ứng viên), prefix dài nhất **486 ký tự** (v3 của C2/C3);
đều dưới trần <6.500 và ≤600, giữ nguyên distill/cap.

**Hiệu quả toàn ma trận.** ΔR/D/mean ΔMDD bên dưới là điểm phần trăm so
Original; D và mean ΔMDD là trung bình đều bốn tài khoản, không phải portfolio.
Visible đếm Decision có metric/example thực hiển thị, mẫu số 60; LONG/CASH
là count trên 60 điểm. Số hiển thị làm tròn bốn chữ số; report giữ đủ độ chính xác.

| Nhánh | ΔR FPT | ΔR MWG | ΔR VCB | ΔR VNM | D | Mean ΔMDD | Visible/60 | LONG/CASH |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| original | +0.0000 | +0.0000 | +0.0000 | +0.0000 | +0.0000 | +0.0000 | 0/60 | 14/46 |
| random | +0.0000 | +11.5627 | -1.0392 | +0.0000 | +2.6309 | -0.1958 | 60/60 | 16/44 |
| recent | +0.0000 | +10.4158 | -1.0392 | +0.0000 | +2.3441 | +0.2461 | 60/60 | 18/42 |
| similarity | +0.0000 | +11.5627 | -1.0392 | +0.0000 | +2.6309 | -0.1958 | 60/60 | 16/44 |
| bayesian | +0.0000 | +8.8874 | +0.0731 | -2.5619 | +1.5997 | +1.1943 | 60/60 | 21/39 |
| C0 | +0.0000 | +0.8188 | -3.8816 | +1.3625 | -0.4251 | -0.0837 | 37/60 | 15/45 |
| C1 | +0.0000 | +10.4158 | -3.8816 | +0.0000 | +1.6336 | +0.2461 | 26/60 | 17/43 |
| C2 | +0.0000 | +8.4803 | -2.8715 | +1.3625 | +1.7428 | -0.3297 | 29/60 | 14/46 |
| C3 | -0.3743 | +1.7880 | -1.0392 | -2.5619 | -0.5468 | +0.8661 | 29/60 | 18/42 |
| C3_stats_only | +0.0000 | +0.8188 | +1.1237 | +0.0000 | +0.4856 | +0.0000 | 11/60 | 17/43 |
| C3_examples_only | -0.3743 | -0.9527 | -3.8816 | -2.5619 | -1.9426 | +0.8661 | 26/60 | 17/43 |

Original có R_net/MDD (%) theo FPT, MWG, VCB, VNM lần lượt
**1,3082/5,1235; 2,8698/2,6936; 2,3668/3,0379; 1,9378/1,3190**.
CASH reference R/MDD=0 trên cùng support; LONG hit-rate=null/NO_LONG.
C2 có D lớn nhất trong sáu ứng viên, nhưng ΔR>0 chỉ ở MWG/VNM (2/4);
C1 tăng chủ yếu ở MWG (1/4). C3 âm ở 3/4 mã. Không đổi ngưỡng, loại kết quả
bất lợi hoặc kết luận hiệu quả xác nhận từ development; selection thuộc W7-12.

**Drawdown/exposure từng mã.** Mỗi ô ghi ΔMDD (điểm phần trăm); visible/planned.

| Ứng viên | FPT | MWG | VCB | VNM |
| --- | ---: | ---: | ---: | ---: |
| C0 | +0.0000; 7/12 | +0.0000; 10/16 | +0.9843; 10/16 | -1.3190; 10/16 |
| C1 | +0.0000; 4/12 | +0.0000; 7/16 | +0.9843; 8/16 | +0.0000; 7/16 |
| C2 | +0.0000; 5/12 | +0.0000; 7/16 | +0.0000; 8/16 | -1.3190; 9/16 |
| C3 | +0.0000; 5/12 | +0.0000; 7/16 | +0.9843; 8/16 | +2.4801; 9/16 |
| C3_stats_only | +0.0000; 2/12 | +0.0000; 2/16 | +0.0000; 2/16 | +0.0000; 5/16 |
| C3_examples_only | +0.0000; 4/12 | +0.0000; 7/16 | +0.9843; 8/16 | +2.4801; 7/16 |

**Phân loại.** Mỗi ô ghi balanced accuracy / LONG hit-rate, thang [0,1].
Các mẫu số/confusion counts, participation và reason/null giữ trong `stocks` của report.

| Nhánh | FPT | MWG | VCB | VNM |
| --- | ---: | ---: | ---: | ---: |
| original | 0.5833 / 0.6000 | 0.6545 / 0.6667 | 0.5317 / 0.5000 | 0.5333 / 0.5000 |
| random | 0.5833 / 0.6000 | 0.7545 / 0.7500 | 0.4762 / 0.4000 | 0.5333 / 0.5000 |
| recent | 0.5833 / 0.6000 | 0.8091 / 0.6667 | 0.4762 / 0.4000 | 0.5333 / 0.5000 |
| similarity | 0.5833 / 0.6000 | 0.7545 / 0.7500 | 0.4762 / 0.4000 | 0.5333 / 0.5000 |
| bayesian | 0.5833 / 0.6000 | 0.7636 / 0.5714 | 0.5476 / 0.5000 | 0.4833 / 0.3333 |
| C0 | 0.5833 / 0.6000 | 0.7091 / 0.6000 | 0.4048 / 0.2500 | 0.5833 / 1.0000 |
| C1 | 0.5833 / 0.6000 | 0.8091 / 0.6667 | 0.4048 / 0.2500 | 0.5333 / 0.5000 |
| C2 | 0.5833 / 0.6000 | 0.7091 / 0.6000 | 0.4603 / 0.3333 | 0.5833 / 1.0000 |
| C3 | 0.5000 / 0.5000 | 0.7545 / 0.7500 | 0.4762 / 0.4000 | 0.4833 / 0.3333 |
| C3_stats_only | 0.5833 / 0.6000 | 0.7091 / 0.6000 | 0.6032 / 0.6000 | 0.5333 / 0.5000 |
| C3_examples_only | 0.5000 / 0.5000 | 0.6091 / 0.5000 | 0.4048 / 0.2500 | 0.4833 / 0.3333 |

**Regime PIT.** BULL có 11 điểm (2/3/3/3 theo FPT/MWG/VCB/VNM),
CHOPPY 26 (5/7/7/7), CONSOLIDATION 23 (5/6/6/6); BEAR=0, metric
null/NO_SUPPORT ở mọi nhánh. Bảng ghi trung bình đều ΔR trên tài khoản
dựng lại riêng cho từng regime, kèm visible/N. Không cộng return các regime
để suy ra return toàn cohort. Chi tiết ΔMDD/action/coverage từng mã/regime
ở `stocks.<symbol>.regimes` trong report đã verify.

| Nhánh | BULL: ΔR; visible/11 | CHOPPY: ΔR; visible/26 | CONSOLIDATION: ΔR; visible/23 |
| --- | ---: | ---: | ---: |
| original | +0.0000; 0/11 | +0.0000; 0/26 | +0.0000; 0/23 |
| random | -0.2315; 11/11 | -0.2611; 26/26 | +3.1581; 23/23 |
| recent | -0.2315; 11/11 | +0.1734; 26/26 | +2.3803; 23/23 |
| similarity | -0.2315; 11/11 | -0.2611; 26/26 | +3.1581; 23/23 |
| bayesian | -0.8515; 11/11 | +0.4529; 26/26 | +2.0012; 23/23 |
| C0 | +0.0982; 11/11 | -0.5408; 26/26 | +0.0000; 0/23 |
| C1 | -0.2315; 5/11 | -0.5408; 21/26 | +2.3803; 0/23 |
| C2 | +0.0982; 7/11 | -0.7215; 22/26 | +2.3803; 0/23 |
| C3 | -0.6200; 7/11 | +0.0782; 22/26 | +0.0000; 0/23 |
| C3_stats_only | -0.2315; 4/11 | +0.7169; 7/26 | +0.0000; 0/23 |
| C3_examples_only | -0.8515; 5/11 | -1.0706; 21/26 | +0.0000; 0/23 |

**Cặp thành phần và prior-off.** ΔR/ΔMDD là trung bình đều bốn mã
của A−B trên S; hai cột cuối là count bất đồng/mẫu số. Khi so Original,
prior-off xét nhánh A; các cặp còn lại xét cả A/B. Mười cặp so Original đã
có ΔR/ΔMDD ở bảng đầu; disagreement lần lượt theo thứ tự nhánh (bỏ Original)
là **4,4,4,7,5,5,4,4,3,5 trên 60**. Prior-off tương ứng là
**0/0,0/0,0/0,0/0,0/23,1/34,1/31,0/31,1/49,0/34**;
0/0 giữ null/NO_SUPPORT.

| A−B | Mean ΔR | Mean ΔMDD | Bất đồng/S | Bất đồng/prior-off |
| --- | ---: | ---: | ---: | ---: |
| C1−C0 | +2.0586 | +0.3297 | 2/60 | 1/23 |
| C2−C0 | +2.1679 | -0.2461 | 3/60 | 1/23 |
| C3−C0 | -0.1218 | +0.9498 | 5/60 | 0/23 |
| C3_stats_only−C0 | +0.9107 | +0.0837 | 4/60 | 0/23 |
| C3_examples_only−C0 | -1.5176 | +0.9498 | 4/60 | 0/23 |
| C2−C1 | +0.1093 | -0.5758 | 3/60 | 0/31 |
| C3−C2 | -2.2897 | +1.1958 | 8/60 | 1/31 |
| C3−C3_stats_only | -1.0325 | +0.8661 | 5/60 | 0/31 |
| C3−C3_examples_only | +1.3958 | +0.0000 | 3/60 | 0/31 |

C1/C2 khác Original tại **MWG-2023-07-05** dù prior-off; tài khoản
subgroup MWG dựng lại cho ΔR **+9,5212 điểm phần trăm**. C3_stats_only khác
Original khi prior-off tại **VCB-2023-08-29**, ΔR subgroup VCB **+1,1237**.
Không gán những chênh lệch này cho nội dung prior; prompt/contract và biến
thiên LLM còn là giới hạn. Các subgroup không thay primary hoặc chứng minh nhân quả.

**Ablation readiness.** Cả ba C3 cùng base evidence hash; T có
**8/60 điểm: FPT 1, MWG 2, VCB 2, VNM 3** và contract active ở cả ba.
T gồm FPT-2023-06-27; MWG-2023-06-30/2023-08-29;
VCB-2023-03-06/2023-09-29; VNM-2023-02-08/2023-09-29/2023-11-23.
T là subgroup mô tả PROVISIONAL, không phải primary thiếu dữ liệu.
Trên G, C3−stats_only bất đồng **5/60**, C3−examples_only **3/60**;
riêng T lần lượt **1/8**, **2/8**. Tài khoản T được dựng lại từ vốn đầu:

| Mã (N_T) | R C3 / stats_only / examples_only (%) | ΔR C3−stats / C3−examples | ΔMDD C3−stats / C3−examples |
| --- | ---: | ---: | ---: |
| FPT (1) | -2.2882 / -2.2882 / -2.2882 | +0.0000 / +0.0000 | +0.0000 / +0.0000 |
| MWG (2) | +1.7382 / +0.7960 / -0.9261 | +0.9422 / +2.6643 | -0.9261 / -0.9261 |
| VCB (2) | +0.0000 / +0.0000 / +0.0000 | +0.0000 / +0.0000 | +0.0000 / +0.0000 |
| VNM (3) | +0.0000 / +0.0000 / +0.0000 | +0.0000 / +0.0000 | +0.0000 / +0.0000 |

Ngoài T, khác biệt bao gồm cả bật/tắt contract, không cô lập riêng
stats/examples. T nhỏ và hiệu ứng trong T tập trung ở MWG; chưa suy ra lợi ích tổng quát.

**Ca bất lợi và trace.** LONG trên tập có metric visible/ready bị cờ bất lợi
(mean đầy đủ, ngưỡng 0,5 đã khóa) lần lượt: C0 **7/34**, C1 **3/24**,
C2 **1/8**, C3 **3/8**, stats_only **3/8**; examples_only **0/0, null**
vì không hiển thị posterior metric. Các nhánh v1 cũng N/A, không gán cờ từ tỷ lệ v1.
Danh sách dưới giữ mọi point có LONG bất lợi ở sáu ứng viên; net LONG là nhãn
kinh tế thập phân đổi sang %, khác return tài khoản có lot:

| Point ID | Nhánh LONG khi có cờ | Net LONG (%) |
| --- | --- | ---: |
| FPT-2023-06-27 | C0, C1 | -2.2882 |
| FPT-2023-07-31 | C0, C2, C3, C3_stats_only | -2.9017 |
| FPT-2023-08-29 | C0 | +3.1382 |
| MWG-2023-08-29 | C0, C1, C3, C3_stats_only | +1.7382 |
| VCB-2023-01-06 | C0 | -1.5077 |
| VCB-2023-02-08 | C0, C1 | -1.0152 |
| VNM-2023-01-06 | C3, C3_stats_only | -1.3190 |
| VNM-2023-08-29 | C0 | +3.3003 |

Report giữ cả ca thuận lợi/CASH, metric/mean/support/CrI, retrieved/visible IDs,
request/prefix/base hash và outcome tại `prior_analysis.branches.<id>.cases`.
Trace bắt buộc hợp lệ **C3 29/29**, stats_only **11/11**, examples_only
**26/26**; C3 và examples_only đều tự báo NOT_USED, stats_only có
**9 NOT_USED/2 SUPPORTS**. Một số ca NOT_USED nói không có metric dù prefix
đã hiển thị: giữ nguyên raw response, không diễn giải trace thành bằng chứng
model đã dùng prior hoặc sửa prompt sau xem kết quả.

**Nghiệm thu:** compileall/E2E và **859 unit/163 leakage PASS**, không skip.
Không đổi code/config/runtime; report/checkpoint/ledger và bằng chứng nguồn
được đối chiếu hash nguyên byte. Các giới hạn FPT thiếu bốn điểm Q1,
BEAR=0, tin reliable=0 và PIT hồi cứu tiếp tục áp dụng. **W7 đạt 11/16**;
tiếp theo **W7-12**, chưa chạy selector/promote hoặc mở holdout 2024.

#### W7-12 — Quyết định ứng viên, cấu hình và risk OFF

- **Làm:** chạy selector 07 trên report 11; ghi quyết định/promoted hoặc
  NOT_PROMOTED, lựa chọn triển khai, lý do và kết quả của mọi ứng viên.
  Ghim model/client/prompt/K/threshold/versions; risk giữ OFF.
- **Đầu ra:** artifact lựa chọn bất biến và phần kết quả gọn trong README.
- **Đạt khi:** verifier tái lập đúng eligibility/tie-break; không chỉnh ngưỡng
  sau xem kết quả để lấy ứng viên thắng. Nếu C0 được chọn, không gán lợi ích
  cho module retrieval/contract mới. Tập khả thi rỗng thì Gate C BLOCKED.

##### Quyết định development đã khóa, 16/10/2026

**W7-12 DONE / Gate C PASS.** Selector production qua entrypoint provider
đã tái dựng và kiểm report/checkpoint/nguồn/gate, tạo artifact
`candidate_selection_v1` theo `development_nomination_rules_v1`; reader
`--verify-selection` tái lập toàn bộ eligibility, metric, ranking và binding
**PASS offline**. Giữ nguyên registry/ngưỡng/model/lịch, không tune sau kết quả.

- **Ứng viên nghiên cứu: C2, NOT_PROMOTED.** D=**+1,742822012197792** điểm
  phần trăm, mean ΔMDD=**−0,32974346212500116**, max ΔMDD=**0**; chỉ
  MWG/VNM cải thiện (**2/4 mã**), không đạt yêu cầu ≥3/4 để promote.
- **Lựa chọn triển khai: Original** (`deployment_choice=original`);
  numeric risk tiếp tục **DEFERRED/OFF**, `risk_policy=OFF`.
- Sáu ứng viên đều đủ gate/completion/60 paired/metric hữu hạn và exposure
  ≥6/60, ≥1 ở mỗi mã; **tập promote rỗng**. Khóa C2 từ tập eligible theo D
  lớn nhất, không gọi đây là ứng viên được promote hoặc bằng chứng hiệu quả holdout.

Đơn vị D/ΔMDD là điểm phần trăm; bảng làm tròn, artifact giữ đủ độ chính xác.

| Ứng viên | Visible/60 | D | Mã ΔR>0/4 | Mean / max ΔMDD | Eligible | Lý do không promote |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| C0 | 37/60 | −0,4251 | 2/4 | −0,0837 / +0,9843 | Có | D≤0; thiếu 3 mã dương |
| C1 | 26/60 | +1,6336 | 1/4 | +0,2461 / +0,9843 | Có | Thiếu 3 mã dương |
| C2 | 29/60 | +1,7428 | 2/4 | −0,3297 / 0 | Có | Thiếu 3 mã dương |
| C3 | 29/60 | −0,5468 | 1/4 | +0,8661 / +2,4801 | Có | D≤0; thiếu 3 mã dương |
| C3_stats_only | 11/60 | +0,4856 | 2/4 | 0 / 0 | Có | Thiếu 3 mã dương |
| C3_examples_only | 26/60 | −1,9426 | 0/4 | +0,8661 / +2,4801 | Có | D≤0; thiếu 3 mã dương |

Thứ tự eligible: **C2 → C1 → C3_stats_only → C0 → C3 → C3_examples_only**.
Sáu D khác nhau quá 1e−9 nên không cần phân xử tie; quy tắc quanh D_max,
sau đó mean ΔMDD/ID vẫn giữ nguyên. Mọi ứng viên đều đạt hai giới hạn MDD.
Ngưỡng đề cử tiếp tục là D>0, ≥3 mã ΔR>0, mean ΔMDD≤2, max ΔMDD≤5;
không làm tròn metric trước xét ngưỡng hoặc dùng đối chứng v1 thay registry.

**Cấu hình đã ghim cho C2.** Toàn bộ giá trị nằm trong plan development v2,
registry và code/runtime/source hashes đã bind vào selection; mục 2.1 giữ
cấu hình chung. Các giá trị chính:

| Thành phần | Giá trị đã khóa |
| --- | --- |
| Text/Decision | `openai/gpt-oss-20b`; temperature=0, max_tokens=2048; `reasoning_effort=low`, `reasoning_format=hidden` |
| Graph/vision | `qwen/qwen3.8-27b`; temperature=0, max_tokens=1024; `reasoning_effort=none`, `reasoning_format=hidden` |
| Signal/prior | `vi`, `1d`, 45 nến; `zscore_tanh`, alpha_weights=null; K=3, seed=42, scope=`same_symbol` |
| Profile C2 | `prior_evidence_v3` / `conditional_disjoint_beta_v1` / `split_quality_gate_v2` / `compact_brpp_v3` / `decision_legacy_v1`; content=`full_prior` |
| Retrieval | w_signal=0,5; half-life=365 ngày; max_age=730 ngày; min_similarity=0,625; min_gap=5 phiên |
| Statistics/quality | shrink_strength=4; population≥20, conditional≥5, interval_width≤0,75 |
| Feature/index/scaler | `pit_price_features_v1`, `raw_segment_21_v1`, `episode_price_index_v1`, `symbol_fold_standard_v1` |
| Ranking/diversity | `signal_price_recency_v1`, `session_gap_v1` |
| Prompt/kinh tế/risk | BRPP≤600, tổng prompt<6.500, giữ distill/cap; LONG Open(t+1)→Close(t+3), SHORT=CASH, phí/trượt giá hai chiều; risk OFF |

Artifact bất biến tại
[`candidate_selection_v1.json`](../../../outputs/bayesian_benchmark/development_candidate_run_v2/candidate_selection_v1.json),
SHA-256 file **82f5926ac44f1d9263ac49d0bc2cbb2f11066db11a9e842f009bfca4588592a4**. Selection bind rules/report/file/
485 checkpoint/plan/registry/code/runtime/source/index/model và receipt gate;
report giữ SHA-256 `57026e012e3fa6032ad81bbe6100af580fd0a59900f3d1f9370fdb32941ed1c8`.
Receipt provider đã khóa ở W7-10 giữ hash
`1b1bf0196305dbb96b7a1ce63cc15e79da9ea35a97296c0371d31f6036f6cac4`.

Kiểm lại artifact từ gốc repo, dùng đúng entrypoint sau amendment:

```powershell
$selectionArgs = @(
    "--plan", "outputs/bayesian_benchmark/development_candidate_plan_v2.json",
    "--output-dir", "outputs/bayesian_benchmark/development_candidate_run_v2",
    "--ledger", "outputs/oos_pilot/api_usage.json",
    "--quota-policy", "request_admission_v2",
    "--technical-gates", "docs/plan/week7/validation_gates/technical_gates_provider_v1.json",
    "--selection-output", "candidate_selection_v1.json"
)
py -3.13 -X utf8 scripts/run_provider_validation.py --verify-selection @selectionArgs
if ($LASTEXITCODE -ne 0) { throw "Selection chưa hợp lệ; dừng trước holdout." }
```

**Kiểm chứng:** selector/reader semantic PASS và oracle số học độc lập khớp
6/6 eligible, 0/6 promote, toàn thứ tự và reason. Code/test/runtime không đổi;
kế thừa bốn gate W7-11 (**859 unit/163 leakage, compileall/E2E PASS**, không
skip), kiểm receipt/log/code/runtime đúng identity và **801 file nguồn/bằng
chứng nguyên byte**. Chỉ thêm selection, không ghi lại report/checkpoint/ledger.
Không gọi API hoặc dùng outcome 2024. **W7 đạt 12/16**, Phase C DONE;
tiếp theo **W7-13** chẩn đoán coverage/attribution theo Phase D điều chỉnh.

**Gate C PASS (16/10/2026):** 10–12 DONE; đủ development thật, selection kiểm được. Không cần
ứng viên thắng để thông qua nếu khóa được ứng viên nghiên cứu NOT_PROMOTED
đúng quy tắc; không gọi kết quả development là bằng chứng xác nhận cuối.

### Phase D — Chẩn đoán và bàn giao cải tiến (thay thế kế hoạch chưa chạy)

#### W7-13 — Chẩn đoán nút thắt và kiểm attribution

- **Làm:** đọc report đã verify; lập funnel population→conditional→ready→visible
  →action theo mã/regime; phân biệt thiếu support, feature, interval và cap.
  Kiểm các request prior-off có cùng byte/schema/model/options hay không.
- **Đầu ra:** bảng giả thuyết trong README, trỏ case/hash nguồn, phân biệt
  bằng chứng đã thấy với nguyên nhân chưa kiểm. Không gọi thêm API.
- **Đạt khi:** giải thích được mẫu 8/60, các ca prior-off bất đồng và trace
  NOT_USED mà không suy trace thành bằng chứng nhân quả; chưa đọc holdout.

##### Chẩn đoán development và kiểm attribution, 16/10/2026

**W7-13 DONE.** Đối chiếu report v5 đã verify với 360 checkpoint ứng viên
và 60 point v1; chỉ phân tích development 2023. Giữ nguyên report/selection,
registry, ngưỡng và runtime. Nguồn là
[`report.json`](../../../outputs/bayesian_benchmark/development_candidate_run_v2/report.json),
SHA-256 `57026e012e3fa6032ad81bbe6100af580fd0a59900f3d1f9370fdb32941ed1c8`;
`binding.checkpoint_sha256` chứa hash đầy đủ của từng checkpoint bên dưới.
Không tạo artifact phân tích trùng report hoặc mở outcome holdout 2024.

**Funnel C2/C3 theo mã/regime.** P là số cycle PIT cùng mã/regime;
C là cycle khớp đồng thời T/P/A/I, khác số ví dụ K. `P≥20` và `C≥5`
đếm **query** đạt ngưỡng, không cộng cycle lặp lại qua các query.
S/E là số query stats/examples ready; T=S∩E; V=S∪E là query có prior
thực hiển thị. Hai đường stats/examples tách độc lập, không phải mọi ví dụ
đều phải qua C≥5. C2 và ba C3 có cùng base evidence ở đủ 60/60 điểm.
Các cột LONG đếm action trên **V**, CASH=V−LONG; không phải số action thay
đổi do prior hoặc toàn bộ LONG trên 60 điểm.

| Mã / regime | N | P mỗi query | C min–max | P≥20 | C≥5 / S | E | T | V | LONG C2 / C3 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| FPT / BULL | 2 | 83 | 6–20 | 2 | 2 / 2 | 1 | 1 | 2 | 2 / 2 |
| FPT / CHOPPY | 5 | 62 | 0–4 | 5 | 0 / 0 | 3 | 0 | 3 | 0 / 1 |
| FPT / CONSOLIDATION | 5 | 19 | 0–1 | 0 | 0 / 0 | 0 | 0 | 0 | 0 / 0 |
| MWG / BULL | 3 | 84 | 0–10 | 3 | 1 / 1 | 2 | 1 | 2 | 1 / 0 |
| MWG / CHOPPY | 7 | 62 | 0–8 | 7 | 1 / 1 | 5 | 1 | 5 | 0 / 1 |
| MWG / CONSOLIDATION | 6 | 19 | 0–4 | 0 | 0 / 0 | 0 | 0 | 0 | 0 / 0 |
| VCB / BULL | 3 | 85 | 0–2 | 3 | 0 / 0 | 1 | 0 | 1 | 0 / 0 |
| VCB / CHOPPY | 7 | 63 | 1–5 | 7 | 2 / 2 | 7 | 2 | 7 | 0 / 2 |
| VCB / CONSOLIDATION | 6 | 19 | 0–1 | 0 | 0 / 0 | 0 | 0 | 0 | 0 / 0 |
| VNM / BULL | 3 | 85 | 1–15 | 3 | 1 / 1 | 1 | 0 | 2 | 0 / 2 |
| VNM / CHOPPY | 7 | 61 | 0–10 | 7 | 4 / 4 | 6 | 3 | 7 | 1 / 1 |
| VNM / CONSOLIDATION | 6 | 19 | 0–1 | 0 | 0 / 0 | 0 | 0 | 0 | 0 / 0 |
| **Tổng** | **60** | **19–85** | **0–20** | **37** | **11 / 11** | **26** | **8** | **29** | **4 / 9** |

BEAR không có query, giữ N=0/metric=null. Theo FPT/MWG/VCB/VNM,
S=2/2/2/5, E=4/7/8/7, T=1/2/2/3 và V=5/7/8/9, khớp W7-11.
Trong 60 điểm có **8 cả hai, 3 chỉ stats, 18 chỉ examples, 31 không có block**.
T gồm đúng tám point đã liệt kê ở W7-11; 3 điểm chỉ stats là
FPT-2023-07-31, VNM-2023-01-06 và VNM-2023-08-29: cả ba thiếu query
feature do `CORPORATE_ACTION_WINDOW`. Vì thế T=8 không phải chỉ có tám
Decision nhận prior, cũng không phải tám ví dụ trong một prompt; K vẫn bằng 3.

**Nút thắt đã quan sát.** Cả 23 query CONSOLIDATION có P=19 nên bị chặn
population; 37 query còn lại đủ P nhưng chỉ 11 đủ conditional support.
26 query đủ P mà stats chưa ready đều có C từ 0 đến 4. Trên **240 ô metric**
(60×4), 31 READY, 209 thiếu conditional support; trong các ô thiếu support
có 131 không có conditional history, 92 cũng thiếu population và 8 có
CrI rộng >0,75. Các reason chồng lấp, không cộng thành số query. Không có
ô bị loại **chỉ** vì khoảng rộng, không có ô support≥5 bị khoảng rộng chặn.

Examples: 60/60 scaler AVAILABLE; query feature AVAILABLE 50/60,
10/60 UNAVAILABLE đều do corporate action window. Trong 37 query đủ P,
26 examples ready; 11 còn lại gồm **7 thiếu query feature + 4 có feature
nhưng không còn ví dụ đạt điều kiện**. Bốn ca sau là FPT-2023-10-30,
MWG-2023-10-30/2023-11-23 và VCB-2023-01-06; trace giữ các lý do
`PRIOR_FEATURE_UNAVAILABLE`, `PRIOR_TOO_OLD`, `BELOW_MIN_SIMILARITY`.
Ba query thiếu feature còn lại đã nằm trong 23 query P<20; không đếm hai lần.
Trên 60 query, trace ghi 539 lượt candidate thiếu feature, 934 quá tuổi,
1.599 dưới similarity, 68 `K_LIMIT`, 15 `SESSION_GAP_TOO_SMALL`;
đây là lượt episode-query với reason có thể chồng lấp, không phải episode
độc lập. K/diversity giới hạn số ví dụ, không giải thích ca không còn ví dụ
đạt điều kiện. C0 hiển thị 37/60; C1 ghép gate với examples nên 26/60;
C2/C3 tách block phục hồi 3 query chỉ stats thành V=29/60.

**Cap không gây mất block trong run này.** Prefix dài nhất C2/C3=486≤600,
prompt dài nhất toàn run=4.581<6.500 (Bayesian v1, VNM-2023-07-05);
4.534 là mức tối đa của sáu ứng viên, đính chính phạm vi số liệu W7-11.
Builder v3 ném lỗi khi prefix vượt
trần, không âm thầm cắt K/metric; không thấy lỗi cap trong 660 Decision
complete. Report hiện tại vẫn được distill/cap trước ghép prompt; chưa có
đối chứng để kết luận phần report bị rút gọn không ảnh hưởng suy luận.

**Kiểm request prior-off.** So UTF-8 của `candidates/<id>/<point>.json:prompt`
với `v1/<symbol>/points/<point>.json:branches.original.input.prompt.text`:

| Nhánh | Prior-off | Prompt trùng byte Original | Cùng đường structured legacy | Bất đồng action |
| --- | ---: | ---: | ---: | ---: |
| C0 | 23 | 23 | 23 | 0 |
| C1 | 34 | 34 | 34 | 1 |
| C2 | 31 | 31 | 31 | 1 |
| C3 | 31 | 31 | 31 | 0 |
| C3_stats_only | 49 | 49 | 49 | 1 |
| C3_examples_only | 34 | 34 | 34 | 0 |
| **Tổng lượt so** | **202** | **202** | **202** | **3** |

Ở cả 202 lượt, output ghi `llm_structured`. Code đã khóa chọn
`TradeDecisionOutput`, `method=json_schema`, `include_raw=True`; C1–C3
prior-off có prefix rỗng và `decision_contract_version=decision_legacy_v1`.
Schema có 7 field cũ, không thêm `prior_use`. Factory dùng cùng agent LLM:
`openai/gpt-oss-20b`, temperature=0, max_tokens=2048, reasoning_effort=low,
reasoning_format=hidden, max_retries=0; không đăng ký seed Decision.
Đối chiếu nguồn tại `agents/decision_agent.py:create_final_trade_decider`,
`core/prior_prompt.py:build_prior_request` và
`scripts/run_bayesian_ablation.py:make_builder`, cùng plan/runtime đã verify.
Internal request hash vẫn khác vì candidate/content/source binding khác;
những field này không tự động thành nội dung HTTP gửi model.

Ba bất đồng tập trung ở **hai point**: C1/C2 LONG còn Original SHORT tại
MWG-2023-07-05; stats_only LONG còn Original SHORT tại VCB-2023-08-29.
Hash prompt lần lượt là
`cf501d8e78e4823138fd959fa4326f5006766ad96194124276a53f015e86ed73` và
`5913366288cffe0d1fed66283427459a40e232cf354fd9ee4e71a3affb32510e`.
MWG C1/C2 cùng 1.602 prompt tokens nhưng response fingerprint lần lượt
`fp_ef00694abe` / `fp_a8c584dda7`; VCB stats_only có 1.634 prompt tokens,
fingerprint `fp_d3e146e1a5`. Đây là metadata response đã lưu, không phải
bằng chứng fingerprint gây đổi action. Checkpoint Original không lưu đủ
metadata response này và không lưu nguyên HTTP request body/header.
**Kết luận audit:** prompt trùng byte, schema/model/options phía client
cùng cấu hình; chưa thể chứng nhận toàn HTTP request nguyên byte hoặc
xác định nguyên nhân phía provider. 3/202 là mô tả các lượt so phụ thuộc,
không phải ước lượng nhiễu nền độc lập. Cần phép lặp cùng request đã đăng ký
ở W7-14/W8 trước quy kết hiệu ứng prior; không gán lợi ích prior cho ba ca này.

**Trace NOT_USED.** C3=29/29, examples_only=26/26 NOT_USED;
stats_only=9/11 NOT_USED và 2/11 SUPPORTS. C3 có 11/29 ca metric visible
mà vẫn NOT_USED; stats_only có 9 ca tương tự. FPT-2023-07-31 có cả bốn
metric visible/ready, nhưng reason tự khai là “Không có dữ liệu metric phù
hợp để áp dụng”; MWG-2023-06-30 cũng có stats/examples ready mà tự báo
không có prior phù hợp. Schema chỉ kiểm enum/IDs/visibility, không kiểm
được trung thực của reason hay quá trình suy luận. NOT_USED có thể là
bác bằng chứng, hiểu sai hoặc self-report không đáng tin; chưa phân biệt
được các khả năng này. Giữ raw response và mọi action, không sửa trace,
ép dùng prior hoặc coi NOT_USED là bằng chứng nhân quả model bỏ qua prefix.

**Case kiểm lại.** Liên kết trỏ file bất biến; cột hash là 12 ký tự đầu
SHA-256, hash đầy đủ đã đối chiếu với binding của report.

| Case / checkpoint | SHA-256 đầu | Quan sát phục vụ chẩn đoán |
| --- | --- | --- |
| [C1 MWG-2023-07-05](../../../outputs/bayesian_benchmark/development_candidate_run_v2/candidates/C1/MWG-2023-07-05.json) | `66b1bb8a186a` | Prior-off, prompt trùng Original nhưng action khác |
| [C2 MWG-2023-07-05](../../../outputs/bayesian_benchmark/development_candidate_run_v2/candidates/C2/MWG-2023-07-05.json) | `f8b83df3ec5c` | P=19, C=1, retrieved=2 nhưng visible=0 |
| [stats_only VCB-2023-08-29](../../../outputs/bayesian_benchmark/development_candidate_run_v2/candidates/C3_stats_only/VCB-2023-08-29.json) | `cf9a051d5bab` | C=1 nên stats tắt, schema legacy; action khác Original |
| [C3 FPT-2023-06-27](../../../outputs/bayesian_benchmark/development_candidate_run_v2/candidates/C3/FPT-2023-06-27.json) | `e9f024d50e74` | P=83, C=6, cả hai ready; NOT_USED |
| [C3 FPT-2023-07-31](../../../outputs/bayesian_benchmark/development_candidate_run_v2/candidates/C3/FPT-2023-07-31.json) | `1710afae846e` | Stats ready, feature thiếu; reason phủ nhận metric visible |
| [C2 MWG-2023-11-23](../../../outputs/bayesian_benchmark/development_candidate_run_v2/candidates/C2/MWG-2023-11-23.json) | `4405892c89f9` | Feature query có, không còn ví dụ đạt điều kiện |

**Giả thuyết bàn giao cho W7-14, chưa phải kết luận nguyên nhân.**

| Giả thuyết | Bằng chứng đã thấy | Phần chưa kiểm / phép kiểm cần khóa |
| --- | --- | --- |
| Biến thiên Decision/provider lẫn hiệu ứng prior | 3 bất đồng prior-off trên 202 lượt prompt giống nhau; contract tắt về legacy | Lặp cùng request, thứ tự nhánh/seed định trước; so phân phối action trước quy kết hiệu ứng |
| Support điều kiện thưa do khớp cứng T/P/A/I | 37 đủ P nhưng 11 stats ready; toàn CONSOLIDATION P=19 | Partial pooling/độ ổn định xác suất ngoài thời gian; chưa chứng minh lọc cứng gây giảm return, không hạ gate sau xem kết quả |
| Feature/age/similarity hạn chế examples | 7 query đủ P thiếu feature và 4 query không còn ví dụ đạt điều kiện | Kiểm retrieval/feature PIT và ablation giữ posterior/prompt chung; không bỏ corporate-action guard để tăng coverage |
| Truyền đạt/ngữ nghĩa prior hoặc self-report chưa hiệu quả | Metric visible nhưng NOT_USED, reason đôi khi không khớp prefix | Cùng schema và bằng chứng khi ablation prompt; trace chỉ phụ trợ, action/metric ghép cặp mới đánh giá tác động |
| Khoảng tin cậy/cap là nút thắt chính | 8 ô CrI rộng đều thiếu support; không lỗi cap | Chưa thấy bằng chứng đây là bottleneck độc lập; không ưu tiên nới interval/token để giải thích run cũ |

**Kiểm tra theo phạm vi:** thay đổi chỉ `AGENTS.md` và tài liệu kế hoạch;
không đổi code/test/runtime/schema/dữ liệu. Chạy verifier report production
offline, đối chiếu số đếm/funnel/prompt và hash nguồn; `git diff --check`
và liên kết nội bộ PASS. Không chạy lại compileall/unit/E2E/leakage suite
theo mục 1.2 AGENTS.md mới; gate W7-11 là bằng chứng lịch sử của cùng
code/runtime, không báo thành test vừa chạy. Đối chiếu 597 file thuộc
code/source/checkpoint binding cùng report/selection/amendment/ledger
nguyên byte trong phiên phân tích. **W7 đạt 13/16**; tiếp theo **W7-14**
khóa protocol một vòng cải tiến, chưa tạo manifest hoặc chạy holdout.

#### W7-14 — Khóa protocol vòng cải tiến

- **Làm:** khóa một vòng cải tiến/tối đa hai cấu hình mới theo mục 5.5 plan tổng;
  dừng tối ưu cuối W8, không mở vòng thử mới theo return. Định trước đối chứng,
  mẫu lặp, số lần lặp, metric, thứ tự nhánh/seed, eligibility và điểm dừng.
- **Đầu ra:** đặc tả trong README W8/W9; giữ lịch 60 điểm development và
  64 điểm holdout. Mẫu lặp chọn theo lịch/coverage, không theo lãi/lỗ.
- **Đạt khi:** mỗi thay đổi gắn giả thuyết/ablation; 2023 được ghi exploratory;
  không nới promotion hoặc mở outcome 2024. Chưa tạo manifest holdout.

##### Protocol cải tiến đã khóa, 16/10/2026

**W7-14 DONE.** `improvement_protocol_v1` được đặc tả tại
[README W8](../week8/README.md#protocol-cải-tiến-đã-khóa-tại-w7-14) và
[README W9](../week9/README.md#protocol-thống-kê-đã-khóa-tại-w7-14).
Hai cấu hình mới dành trước: `A_tp_pool` chỉ mở conditional từ T/P/A/I
sang T/P với background rời nhau/strength=4; `B_semantic` giữ evidence C2
và đổi ngữ nghĩa/bố cục prefix. Không ghép A+B, không hạ P≥20/C≥5/CrI≤0,75,
không sửa retrieval/K/model/options, schema Decision legacy hoặc promotion.

Đã khóa ma trận 11 nhánh với ablation C2/A/B, nomination full-prior
C2/A/B và tie-break; giữ 60 điểm development exploratory/64 holdout W5.
Mẫu lặp 12 point chọn bằng ngày/readiness C2, ba lượt bổ sung, có Original
duplicate cùng request; thứ tự xoay nhánh định trước. Lượt lặp tách khỏi
primary và selection. W9 khóa một primary selected−Original, bootstrap
cụm ngày L=4/10.000 draw/PCG64 seed=20261016/CI95%, family secondary có
Bonferroni và quy tắc missing/invalid. Dừng một vòng/hai cấu hình hoặc hết
W8; không tune lại theo return hoặc outcome 2024.

**Phạm vi nghiệm thu:** đây là task khóa đặc tả, chưa hiện thực schema,
registry, producer/loader/verifier hoặc tạo manifest mới; W8 vẫn 0/8,
W9 vẫn 0/6. Rà nguồn implementation, tái dựng 12 point/rank/pool bằng
metadata readiness (không đọc nhãn để chọn), kiểm xoay nhánh và token bản
nháp B trên evidence cũ. Số liệu/liên kết/diff và 597 hash nguồn/bằng chứng
PASS. Không gọi API/đọc outcome holdout, không chạy lại compileall/unit/E2E/
leakage suite cho thay đổi Markdown theo AGENTS.md mục 1.2. Gate D vẫn chờ
15–16; **W7 đạt 14/16**, tiếp theo **W7-15** kiểm nguồn/khả năng tái lập.

#### W7-15 — Kiểm nguồn và khả năng tái lập

- **Làm:** đối chiếu hash report/selection/checkpoint/runtime cũ; xác định
  module cần mở rộng và test PIT/paired/fallback/token. Chuẩn bị namespace
  revision mới, không sửa hash cũ để nhận code mới.
- **Đạt khi:** tái lập được mốc C2, bốn gate kỹ thuật PASS; phân biệt rõ
  schema dự kiến với producer/loader/verifier hiện có. Không nhận dữ liệu
  mock hoặc diagnostics train làm bằng chứng hiệu quả Decision.

#### W7-16 — Bàn giao triển khai cải tiến W8

- **Làm:** chốt phạm vi, phụ thuộc, checklist và hướng dẫn người dùng chạy
  API sau khi code/protocol mới đã kiểm. Giữ risk OFF và Original triển khai.
- **Đạt khi:** 13–15 DONE, Gate A/B/C và bốn gate kỹ thuật PASS; bàn giao
  W8 có giả thuyết, tiêu chí dừng và đường dẫn bằng chứng. Không đánh DONE
  chỉ vì đã soạn kế hoạch; mọi kết quả mới phải có artifact thật.

**Gate D mới:** 13–16 DONE mở W8 cải tiến; không cấp phép chạy holdout.
Gate khóa manifest/xác nhận chuyển sang cuối W8. W7 hiện **14/16**.

## 4. Tổ chức implementation và kiểm thử

- Ưu tiên mở rộng `core/research_metrics.py`, `core/candidate_cohort.py`,
  `core/research_cohort.py`, `core/train_pit_validation.py` và
  `scripts/run_bayesian_ablation.py`. Selector có thể tách module nhỏ;
  không xây runner/API client mới nếu luồng hiện tại đáp ứng được.
- Đường runtime mới đặt dưới `outputs/bayesian_benchmark/`, tên có revision;
  mỗi schema/JSON mới phải có producer, loader, verifier và test consumer.
  README giữ checklist/phương pháp/kết quả; chưa tạo sẵn receipt/JSON rỗng.
- Mỗi task dùng branch riêng từ `develop`, commit Conventional Commits
  mô tả kỹ thuật, không có ký hiệu tuần. Kiểm tra theo phạm vi tại mục 1.2
  AGENTS.md; task thuần tài liệu không cần chạy suite. Các mốc W7-15/16
  vẫn yêu cầu đủ bốn gate kỹ thuật theo tiêu chí nghiệm thu đã định:

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
| 13/10/2026 | W7-08 | DONE, 8/16; protocol v4 bắt buộc selection đã verify, lịch W5 giữ checksum, 11 nhánh và report v6 gắn primary/control/ablation. Compileall/E2E, 837 unit/156 leakage PASS; 200 file Python đúng bản kiểm thử, 2.317 file bằng chứng nguyên byte. Chỉ fixture, chưa manifest holdout thật; Gate B còn 09 | W7-09 |
| 13/10/2026 | W7-09 | DONE, 9/16; Gate B PASS. Train v3 852 replay/651 query, plan development v2 60 điểm/11 nhánh và dry-run bốn mã PASS; sáu ca integrity chặn trước API. Retrieval v4 P-core p95 6,328–21,675 ms PASS, giữ v3 mặc định FAIL. Bốn gate mới PASS (837 unit/156 leakage), receipt/log đúng code/runtime; 200 Python, 2.317 bằng chứng cũ và bốn artifact mới nguyên byte. Chưa API/Decision/selection/manifest holdout thật | W7-10 |

| 15/10/2026 | W7-10 | IN_PROGRESS, 9/16 task DONE; amendment provider_daily_quota_v1 bỏ admission ngày local, giữ ledger tổng và 99 Decision trước cutover. Key mới tự preflight; cooldown theo fingerprint, quota thực do Groq; replay quota bị từ chối qua audit UUID, transport_error vẫn thủ công. 859 unit/163 leakage, compileall/E2E PASS; 205 Python đúng bản kiểm, 200 Python gốc và 493 runtime cũ nguyên byte. Amendment đã verify offline; chưa chạy thêm API | Tiếp tục API development |
| 16/10/2026 | W7-10 | DONE, 10/16; người dùng hoàn tất 60/60 điểm, 660/660 Decision thật trên 11 nhánh. Verifier provider/checkpoint/report PASS offline; không missing/pending/failed/unknown. Giữ 793 HTTP attempt lịch sử, report hash và 485 checkpoint binding; không thêm API/holdout. Compileall/E2E, 859 unit/163 leakage PASS | W7-11 |
| 16/10/2026 | W7-11 | DONE, 11/16; tái dựng semantic toàn run và report v5 PASS, G/S đủ 60 trên 11 nhánh/19 cặp. Bảng D/ΔR/ΔMDD/exposure/phân loại theo mã/regime, prior-off, T=8 và mọi ca LONG bất lợi đã đối chiếu; giữ trace NOT_USED và giới hạn quy kết. Compileall/E2E, 859 unit/163 leakage PASS, không skip; 801 file nguồn/bằng chứng nguyên byte. Chưa selection hoặc mở holdout | W7-12 |
| 16/10/2026 | W7-12 | DONE, 12/16; Phase C DONE / Gate C PASS. Selection production và verifier offline khóa C2 NOT_PROMOTED, triển khai Original, risk OFF; 6 eligible/0 promote, C2 chỉ 2/4 mã dương. Oracle độc lập khớp metric/ranking/reason, giữ toàn bộ model/client/prompt/K/ngưỡng/versions. Kế thừa bốn gate cùng code/runtime W7-11; 801 hash cũ và artifact lựa chọn nguyên byte | W7-13 |
| 16/10/2026 | Điều chỉnh kế hoạch | Giữ 12/16; thay Phase D chưa chạy bằng chẩn đoán/bàn giao cải tiến; giữ 10 tuần, cải tiến/khóa W8, benchmark/thống kê W9; selection cũ nguyên trạng | W7-13 |
| 16/10/2026 | W7-13 | DONE, 13/16; funnel development theo mã/regime: P đủ 37, stats 11/examples 26/cả hai 8/visible 29. Audit 202 prior-off prompt trùng byte/schema legacy/model/options client, giữ 3 bất đồng trên 2 point và giới hạn HTTP/trace. Verifier report, số đếm/hash/liên kết/diff PASS; chỉ tài liệu, không chạy lại suite theo AGENTS.md mới. Giữ C2 NOT_PROMOTED/Original/risk OFF, không API hoặc outcome holdout | W7-14 |
| 16/10/2026 | W7-14 | DONE, 14/16; đặc tả improvement_protocol_v1 tại W8/W9 khóa A_tp_pool/B_semantic, ma trận/ablation, 12 point×3 lượt bổ sung, thứ tự/seed, metric/eligibility/CI và điểm dừng. Ngưỡng kinh tế/PIT/quality/promotion giữ nguyên; chỉ Markdown, QA tài liệu/hash PASS, không chạy lại suite/API hoặc tạo manifest holdout | W7-15 |

Kiểm khi lập kế hoạch (12/10/2026): checklist/đánh số/phụ thuộc/liên kết và `git diff --check`.
Code/test không đổi so với mốc W6-16 đã qua bốn gate (784 unit/146 leakage);
kế thừa kết quả của cùng mã nguồn, không chạy lại suite cho thay đổi Markdown.
Đối chiếu 2.317 file bằng chứng/artifact nguyên byte; chưa mở Gate A của W7.
