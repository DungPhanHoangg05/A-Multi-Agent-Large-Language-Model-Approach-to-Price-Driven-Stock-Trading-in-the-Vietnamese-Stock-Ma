# Tuần 7 — Validation, chọn ứng viên và khóa giao thức benchmark

**Trạng thái: Phase A IN_PROGRESS; 1/16 task hoàn thành, Phase B/C/D TODO.**
Ngày lập/cập nhật: **12/10/2026**. Tiếp theo **W7-02**.
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

**Khoảng trống cần triển khai:** báo cáo hiện tại có metric theo candidate
và common support nhưng chưa phải bộ lựa chọn đầy đủ theo quy tắc W6-04.
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
  W7 không tự thêm 651 điểm LLM trên train. Nếu cần kết luận hiệu quả
  LLM theo fold train, phải đăng ký protocol/runner/mẫu riêng trước API;
  không dùng mock hoặc Decision lịch sử khác identity để tạo kết luận đó.
- **Development 2023:** chạy Decision thật trên đúng 60 điểm đã khóa,
  đủ 11 nhánh mỗi điểm; dùng để phân tích và lựa chọn. Giữ embargo pilot/
  smoke, không bù ngày thiếu hoặc đổi ngày lỗi. Không gộp train vào D.
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

## 3. Checklist và phụ thuộc

| Phase | Task | Công việc | Phụ thuộc | Trạng thái |
| --- | --- | --- | --- | --- |
| A | W7-01 | Xác minh bàn giao và khoảng trống implementation | W6 đóng | [x] DONE |
| A | W7-02 | Khóa phạm vi train/development và protocol validation | 01 | [ ] TODO |
| A | W7-03 | Đặc tả report ghép cặp và quy tắc lựa chọn | 02 | [ ] TODO |
| A | W7-04 | Tái kiểm train PIT trên phiên bản bàn giao | 03 | [ ] TODO |
| B | W7-05 | Hoàn thiện report common support và metric | Gate A | [ ] TODO |
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

**Gate A:** 01–04 DONE, protocol/metric/selection đã khóa, train PIT PASS;
chưa mở lượt API development.

### Phase B — Hoàn thiện công cụ và đóng băng code trước API

#### W7-05 — Hoàn thiện report common support và metric

- **Làm:** mở rộng `core/research_metrics.py` theo hợp đồng 03; tái dựng
  return/MDD trên cùng tập ngày, báo planned/complete/failed/unknown/fallback,
  global/pairwise support và metric theo mã, regime, candidate.
- **Đầu ra:** report có version và verifier tái tính từ checkpoint gốc.
- **Đạt khi:** oracle số học độc lập PASS; sửa outcome, support hoặc thứ tự
  ngày bị phát hiện; JSON native/finite, nhóm thiếu dữ liệu giữ null/reason.

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

Kiểm khi lập kế hoạch (12/10/2026): checklist/đánh số/phụ thuộc/liên kết và `git diff --check`.
Code/test không đổi so với mốc W6-16 đã qua bốn gate (784 unit/146 leakage);
kế thừa kết quả của cùng mã nguồn, không chạy lại suite cho thay đổi Markdown.
Đối chiếu 2.317 file bằng chứng/artifact nguyên byte; chưa mở Gate A của W7.
