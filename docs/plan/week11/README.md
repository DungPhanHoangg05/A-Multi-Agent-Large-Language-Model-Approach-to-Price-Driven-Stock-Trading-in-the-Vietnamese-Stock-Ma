# Tuần 11 — Development, kiểm đóng góp ICL và khóa xác nhận

**Trạng thái: TODO, 0/8; cập nhật 21/10/2026.**
[Kế hoạch tổng](../plan.md) · [W10](../week10/README.md) · [W12](../week12/README.md)

## Đầu vào và thời hạn

Chỉ bắt đầu API khi W10-07 PASS. Giữ HMM/model/options và risk OFF; bank
revision làm mới theo W10, cùng query snapshot cho A/R/Numeric;
người dùng tự chạy API bằng CLI sẽ được bàn giao, agent chuẩn bị/verify
offline. Không chạy lại W9 hoặc mở outcome xác nhận mới trong development.
Đầu W11 chạy/đối soát; giữa W11 repeat/analysis; cuối W11 khóa selection,
protocol, nguồn và release. Không kéo tối ưu sang W12.

## Diagnostics train trước LLM

Tái dùng query train có proof PIT, tách fold theo thời gian như hệ thống cũ;
fit mọi hyperparameter/model/scaler chỉ bằng dữ liệu trước query. So A và
R_pool trên giao query có posterior hợp lệ, giữ missing riêng; báo log loss,
Brier, reliability bins cố định [0;0,2;0,4;0,6;0,8;1], counts từng mã/fold,
raw/ready coverage và mức co. Không gán p=0,5 cho prediction thiếu.
Khóa lambda từ {2,4,8} theo W10; R_task dùng cùng posterior nên không nhận
công cải thiện calibration số học độc lập. Loss tốt không đủ chứng minh ICL.

## Ma trận development và ablation

60 point ID năm 2023 giữ nguyên; mọi nhánh dùng một upstream/point và
deep-copy. Trước API khóa toàn ma trận; không reuse action W8/W9 như đối chứng
mới. Có thể reuse upstream cũ chỉ khi verifier chứng minh identity tương
thích; nếu không, tạo upstream mới một lần cho mọi nhánh. Lựa chọn này phải
khóa trước run, không chọn upstream tạo kết quả thuận lợi.

| Nhánh | Nội dung | Vai trò |
| --- | --- | --- |
| Original | Không prior | Primary comparator |
| A_reference_shared_off | Phương pháp/prompt A, memory chung và wrapper shared-off mới | Đối chứng mạnh trên cùng nguồn, không phải run W9 bất biến |
| R_pool full/stats/examples | Cùng base evidence, chỉ khác content mode | Ứng viên 1 và hai ablation |
| R_task full/stats/examples | Cùng base evidence, chỉ khác content mode | Ứng viên 2 và hai ablation |
| Numeric_only | LONG nếu posterior mean>0,5 và stats ready, còn lại CASH theo policy định trước | Đối chứng số học, không gọi LLM và không là ứng viên ICL |

Numeric_only là heuristic xác suất, không tối ưu utility và không được gọi
là policy Bayes tối ưu kinh tế. Evidence không đủ theo rule là CASH có
reason; lỗi/missing execution vẫn là incomplete, không điền CASH.
Nếu R_task bị BLOCKED trước API thì bỏ cả ba nhánh của nó và ghi reason.
Request stats-only của hai R nếu hoàn toàn giống thì alias một Decision;
giữ ID logic và source reference, không đếm alias là quan sát độc lập.
Tối đa tám nhánh LLM × 60 = 480 slot logic, cộng Numeric_only offline.
Số HTTP thật thấp hơn khi shared-off/alias; manifest khai cả logic/request.

Original chạy trước; xoay trái danh sách nhánh LLM còn lại theo index point
trong thứ tự (ngày, FPT/MWG/VCB/VNM), j mod M. Duplicate chỉ ở repeat.
Giữ schema/model/options giống nhau; không thêm seed LLM chưa được hỗ trợ.

## Repeat và kiểm tác động của context

Khóa mẫu 12 point trước Decision: mỗi mã ba điểm, mỗi stratum một điểm từ
both-ready, one-block-ready, off của R_pool. Chọn ngày sớm nhất trong mỗi
stratum; stratum rỗng bù ngày sớm nhất chưa chọn của cùng mã và ghi thiếu
support. Chỉ dùng readiness/metadata PIT, không action/return. Ba lượt bổ
sung/request, r=1/2/3, namespace riêng, upstream giữ chung primary.

Lặp mọi nhánh LLM đang có và Original_duplicate; Original trước, các nhánh
còn lại xoay (3j+r−1) mod M. Tối đa 12×9×3=324 slot; Numeric_only tính
một lần. Giữ raw responses/canonical body/timestamp/attempt, không coi HTTP
retry là lượt khoa học. Repeat không nhập vào D primary và không chọn lượt
tốt nhất. Báo action disagreement với mẫu số, full−Original/A/stats/examples
theo từng lượt và mean; không coi ba cặp lượt là độc lập.

Phân tích full−stats và full−examples trên G toàn bộ, và T cả hai block
ready cùng base. Trace tham chiếu task ID chỉ là telemetry; không suy nó
thành cơ chế nội tại. Có thể thêm fixture đổi nhãn giả để kiểm renderer/
sensitivity offline; không đưa nhãn giả vào primary hoặc bank thật và
không dùng phản ứng fixture để chứng minh hiệu quả giao dịch.

## Selection và điểm dừng

Tập nomination chỉ R_pool/R_task đủ kỹ thuật; A là chuẩn so, ablation và
Numeric_only không được chọn vì return đẹp. Eligibility: đủ 60 point/common
support, metric hữu hạn, bốn gate PASS, prior visible≥6 và ≥1/mã; đủ repeat
đã verify. Candidate dùng task format phải có ≥6 điểm gồm hai task trở lên,
phân bố ≥1/mã; thiếu thì không đủ evidence multi-task, không giả coverage.

Promotable development: D_R−Original>0; ΔR>0 ở ≥3/4 mã; mean ΔMDD≤2,
max ΔMDD≤5 đpt; thêm D_R−A≥0 để không chọn bản kém đối chứng mạnh trên
development. Đây là rule mới trước API, không sửa selection W8. Trong tập
promotable chọn D_R−Original lớn nhất; tie≤1e−9 đpt chọn mean ΔMDD nhỏ hơn,
rồi R_pool trước R_task. Repeat là chẩn đoán bắt buộc, không chọn lại bằng
lượt thắng. Báo bất ổn kể cả candidate được chọn.

Nếu không có promotable, dừng claim nâng cấp kinh tế; không mở xác nhận chỉ
để cứu kết quả, giữ A/W9 làm kết quả nghiên cứu và Original mặc định. Tối đa
một vòng development; sửa lỗi làm đổi action sau đã xem outcome phải revision
riêng, không lấy run mới tốt hơn thay run cũ. Có thể hết thời gian thì dừng
với exploratory. Không gộp R_pool/R_task thành ứng viên thứ ba.

## Protocol xác nhận mới phải khóa trước outcome

Chỉ mở khi exposure/giá/mẫu W10-01 PASS và có candidate eligible/promotable.
N=128, 32/mã, ngày theo W10; không thay điểm hoặc giảm N sau outcome.
Sáu nhánh logic: Original, A_reference_shared_off, selected_full,
selected_stats_only, selected_examples_only, Numeric_only. Năm nhánh LLM:
tối đa 640 slot primary; Numeric_only offline; shared-off/alias đúng protocol.
Không chạy cả R để chọn lại trên xác nhận. Một primary Decision/point/nhánh.

Đăng ký thêm 12 point chẩn đoán readiness theo cùng rule development,
ba lượt bổ sung, năm nhánh LLM + duplicate: 216 slot. Khóa sample/requests
trước action, dùng cùng upstream primary; không nhập repeat vào primary.
Nếu không đủ 12 point theo ngày hợp lệ thì BLOCKED, không chọn theo return.
Repeat đo provider variability; không tự tạo CI tổng hợp từ mẫu nhỏ này.

- Primary: D=(1/4)Σ(R_selected,s−R_Original,s), tài khoản 50 triệu/mã,
  lot/phí/giá engine, không là return portfolio hay mean cycle.
- Secondary family bốn contrast: selected−A, full−stats, full−examples,
  full−Numeric_only. Tất cả cùng G; T readiness là mô tả, không thay family.
- Circular moving-block bootstrap trên cụm ngày cutoff, giữ mã/nhánh cùng
  cụm, dựng lại tài khoản trong từng draw. L=4, 10.000 draws,
  PCG64 seed=20261021, percentile linear. Primary CI95%; secondary
  Bonferroni CI98,75%; sensitivity L=2/8 không thay CI chính. ≥9.500 draw
  hữu hạn, không sinh bù. Thời gian/lô/quyền của cycle dùng nguồn đã khóa.
- Báo count từng mã/draw, invalid reasons, common support và overlap cycle;
  thiếu nhánh/unknown → INCOMPLETE, không bỏ điểm lỗi hoặc điền CASH.
- CIs điều kiện trên Decision đã lưu, không bao gồm hoàn toàn training/
  provider variability; repeat được báo riêng. Không dùng CI này để tuyên
  bố LLM deterministic hoặc prior là nguyên nhân duy nhất.
- D CI>0: hỗ trợ cấu hình tốt hơn Original trên cohort. Selected−A CI>0:
  mới hỗ trợ vượt bản hiện hữu. Full−stats CI>0: hỗ trợ giá trị tăng thêm
  của demonstrations trong protocol; full−examples CI>0: hỗ trợ phần stats.
  Cả hai không tự chứng minh suy luận Bayes bên trong LLM. CI qua/chạm 0:
  inconclusive, không kết luận tương đương hay không có tác dụng.

W11-07 bind protocol/matrix/sample/order/selection, source/model/runtime,
prefix/schema/scaler/bank và receipt gate. Chưa producer/verifier/fixture
bootstrap tương ứng thì không phát hành release. Không sửa W9/manifest cũ.

## Checklist

| Task | Công việc | Phụ thuộc | Điều kiện hoàn thành | Trạng thái |
| --- | --- | --- | --- | --- |
| W11-01 | Kiểm nguồn/gate, khóa development và repeat plan | W10 | Dry-run/identity/nguồn PASS, chưa API khi thiếu binding | [ ] TODO |
| W11-02 | Người dùng chạy primary development | 01 | Đủ ma trận, shared upstream, checkpoint/ledger, không unknown | [ ] TODO |
| W11-03 | Verify primary, chạy/verify ba repeat | 02 | Semantic/request/source PASS; không chọn response | [ ] TODO |
| W11-04 | Phân tích economics/coverage/loss/T/G/repeat/failure | 03 | Đủ cả nhóm bất lợi và missing; không suy trace thành cơ chế | [ ] TODO |
| W11-05 | Khóa selection hoặc STOP_NO_IMPROVEMENT | 04 | Rule và oracle độc lập khớp; không chọn ablation | [ ] TODO |
| W11-06 | Kiểm nguồn mới, công cụ report/bootstrap và bốn gate | 05 | Fixture oracle/PIT/canonical/reuse PASS đúng revision | [ ] TODO |
| W11-07 | Khóa manifest/release xác nhận hoặc BLOCKED | 06 | 128 điểm/sáu nhánh, repeat/protocol/exposure/hash trước outcome | [ ] TODO |
| W11-08 | Bàn giao run/resume/verify, khung chương và bảng | 07 | CLI thật; chốt không tối ưu tiếp W12; nhánh dừng có nội dung luận văn | [ ] TODO |

Nếu thiếu tập mới sạch hoặc không đạt selection, W11-06/07 ghi BLOCKED/
NOT_APPLICABLE đúng lý do, không đánh PASS giả. W12 vẫn hoàn thành luận văn
từ W9 và các kết quả exploratory mới, không kéo dài quá 12 tuần.
