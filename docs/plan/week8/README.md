# Tuần 8 — Cải tiến Bayesian ICL, validation và khóa xác nhận

**Trạng thái: TODO, 0/8.** Kế hoạch điều chỉnh 16/10/2026; giữ deadline 10 tuần.
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

## Hai hướng cải tiến cần quyết định tại W7-14

| Hướng | Phạm vi tối thiểu | Điều kiện giữ trong vòng thử |
| --- | --- | --- |
| A — Bằng chứng Bayes | Từ C2, sửa một nút thắt thống kê hoặc retrieval đã được audit; giữ Decision contract để cô lập thay đổi | Cải thiện chất lượng dự báo/độ tin cậy ngoài thời gian, không chỉ tăng số prior visible |
| B — Cách Decision dùng prior | Giữ evidence C2, làm rõ ý nghĩa posterior/support/uncertainty và ví dụ trong BRPP; giữ schema action, risk OFF | Prompt hợp lệ và ablation cho thấy tác động action có thể đo, không suy từ trace NOT_USED |

Không tự ghép A+B thành cấu hình thứ ba sau khi xem return. Nếu audit cho
thấy chỉ một hướng có cơ sở thì triển khai một hướng. Các ID/version cụ thể
được khóa trước API, không coi tên A/B ở đây là schema đã tồn tại.

Với hướng A, ưu tiên kiểm thống kê hiện có trước khi thêm mô hình: định nghĩa
y=1 khi LONG ròng T+2.5>0; kiểm conditional support, khoảng bất định,
trùng lặp và phụ thuộc episode. Nếu dùng partial pooling, tách rõ prior
population với likelihood conditional để tránh đếm dữ liệu hai lần; fit
strength bằng train, không tối ưu trên holdout. Weighted count phải công bố
effective sample size và bản chất xấp xỉ, không gọi CrI là đã hiệu chuẩn.
Tỷ lệ thắng không thay kỳ vọng return; đo thêm độ lớn lãi/lỗ sau phí, không
thêm policy chặn LONG vào phép so sánh ICL.

Nếu nút thắt thuộc retrieval, sửa ranking/đa dạng thời gian trên đặc trưng PIT,
giữ K=3; không chọn ví dụ theo nhãn thắng/thua. Regime mềm, cross-symbol
pooling, mở rộng bank và mô hình phức tạp chỉ là hướng sau deadline trừ khi
đã có implementation kiểm chứng và được chọn thay một trong hai cấu hình.
Không hạ quality gate chỉ để đạt coverage. Không có support thì fallback
Original đúng hợp đồng và giữ điểm đó trong mẫu đánh giá.

## Checklist tuần 8

| Task | Công việc và đầu ra | Phụ thuộc | Trạng thái |
| --- | --- | --- | --- |
| W8-01 | Khóa tối đa hai cấu hình, giả thuyết, comparator, metric và mẫu lặp; audit byte prior-off | W7 Gate D | [ ] TODO |
| W8-02 | Triển khai thay đổi tối thiểu, producer/loader/verifier và version mới; không sửa artifact cũ | 01 | [ ] TODO |
| W8-03 | Kiểm posterior/PIT/fallback/token/paired; bốn gate kỹ thuật; khóa plan/output development mới | 02 | [ ] TODO |
| W8-04 | Người dùng preflight/run/resume theo hướng dẫn; Decision thật trên 60 điểm, mọi nhánh chung upstream | 03 | [ ] TODO |
| W8-05 | Verify toàn run; phân tích ΔR/MDD/coverage/ablation/prior-off và độ ổn định | 04 | [ ] TODO |
| W8-06 | Khóa selection mới và lý do; giữ ngưỡng W6-04, báo mọi cấu hình đã thử | 05 | [ ] TODO |
| W8-07 | Khóa ma trận, thống kê, manifest holdout 64 điểm; dry-run và kiểm công cụ phân tích bằng fixture | 06 | [ ] TODO |
| W8-08 | Nghiệm thu bốn gate, hash nguồn/runtime và hướng dẫn chạy/verify/resume W9 | 07 | [ ] TODO |

## Protocol development và tiêu chí chọn

Giữ 60 điểm 2023 (FPT 12, ba mã còn lại 16); đây là development đã được xem,
mọi cải tiến là exploratory. So Original, Bayesian v1, C2 và ứng viên mới
trên cùng upstream. Chỉ tái dùng upstream cũ khi verifier chứng minh đầy đủ
identity/provenance tương thích; nếu không, run mới dùng một upstream/point
cho toàn bộ đối chứng. Không trộn Decision khác identity thành một primary.

Đăng ký trước API một mẫu lặp phân tầng theo mã/coverage, chọn không dựa vào
return, với ba lần Decision/request. Dùng mẫu này đo bất đồng nền của
Original/prior-off và hiệu ứng prior; báo riêng, không lấy lượt tốt nhất
hoặc gộp lượt lặp vào primary 60 điểm. Giữ model/options cố định, ghi thứ tự
nhánh; temperature=0 không được coi là đảm bảo tất định.

Primary D là trung bình đều ΔR tài khoản bốn mã so Original. Giữ eligibility
của W6-04: đủ 60 điểm ghép cặp, metric hữu hạn, bốn gate PASS, prior visible
ít nhất 6 điểm và ít nhất một điểm mỗi mã. Promotion: D>0, ΔR>0 ở ít nhất
3/4 mã, trung bình ΔMDD≤2 và tối đa ΔMDD≤5 điểm phần trăm; tie-break kế thừa
selector cũ. Selection mới cần schema/validator tương ứng, không ép ID mới
vào registry cũ. Đăng ký trước phân tích theo thời gian, leave-one-symbol-out,
prior-off và subgroup stats/examples cùng ready; không đổi primary theo
subgroup thắng. Brier/log loss chỉ dùng xác suất sự kiện định nghĩa hợp lệ;
confidence văn bản của LLM không là posterior probability.

Ablation stats-only/examples-only/full dùng cùng base evidence và request
contract, khác nội dung hiển thị có version. Báo common support/readiness;
khác biệt ngoài tập cùng ready không được quy riêng cho stats hoặc examples.
Self-report prior-use chỉ là telemetry, không chứng minh nhân quả.

## Khóa xác nhận và điểm dừng

Cuối W8 dừng phát triển phương pháp. Nếu chưa có ứng viên mới eligible,
giữ C2 NOT_PROMOTED làm ứng viên nghiên cứu, Original triển khai; nếu có
eligible nhưng không đạt promotion, giữ nhãn NOT_PROMOTED. Không ép có
kết quả dương. Lỗi kỹ thuật chưa giải quyết thì gate BLOCKED, báo rõ ảnh
hưởng cỡ mẫu/deadline; không dùng mock thay hiệu quả thật.

Ma trận W9 tối thiểu: Original, Bayesian v1, C2, ứng viên được chọn và
stats-only/examples-only tương ứng nếu đủ contract; gộp ID trùng trước chạy.
Nếu fallback C2 thì đặc tả ablation C2 riêng hoặc ghi không đủ khả năng
cô lập thành phần; không dùng ablation C3 để gọi là ablation C2.
Mọi nhánh cần schema/runner/verifier trước khóa; rút nhánh secondary chỉ
trước API và ghi lý do, không rút sau thấy return. Không mở sensitivity
K=5, risk overlay, model search hoặc replay LLM train trong lịch này.

Khóa primary/secondary, hướng hiệu ứng, đơn vị phân tích, missing/common
support và phương pháp CI trước mở outcome. Block bootstrap giữ cụm ngày
giữa mã và ghép cặp nhánh, dựng lại metric tài khoản; độ dài block chọn từ
train/development, khóa seed/số lần resample/mức CI 95%. McNemar/Wilcoxon
chỉ là kiểm phụ với giả định được nêu; xử lý nhiều so sánh bằng phương pháp
đăng ký trước, không diễn giải p>0,05 thành tương đương.

Giữ 64 điểm holdout 2024, 16/mã; tạo manifest/output mới bind selection,
protocol, code/schema/runtime/model/scaler/nguồn. Không đọc outcome để chọn
cấu hình. Bốn gate theo AGENTS.md, verifier và dry-run PASS mới bàn giao W9.
Giữ T+2.5, PIT, risk OFF, một upstream/point deep-copy, BRPP≤600 và prompt
<6.500 ký tự. Mọi API qua retry/pacer/checkpoint; người dùng tự chạy.

**Gate W8:** 8/8 DONE, selection và manifest kiểm được. Không đồng nghĩa
Bayesian ICL đã thắng; hiệu quả xác nhận còn chờ W9. README này giữ checklist
và kết quả gọn; artifact runtime có revision, không tạo receipt trùng lặp.
