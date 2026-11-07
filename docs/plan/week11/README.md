# W11 — Đánh giá lại các cải tiến trên dữ liệu lịch sử chung

Cập nhật08/11/2026. Original và bốn nhóm cải tiến là Bayesian Prior v1,
Bayesian Prior v2/C2, Bayesian Prior A/B và MT-BICL.
[Kế hoạch tổng](../plan.md) · [Đặc tả đánh giá](historical_reevaluation_plan.md)

## Phạm vi hiện hành

Primary6 nhánh gồm Original_common, bayesian_v1, C2, A_tp_pool, B_semantic,
MT_BICL. Fact_Anchor là dependency bắt buộc của MT-BICL.
CORE4 gồm480 unit; EXTENDED gồm1.020 unit trên9 mã eligible,120 ngày cutoff,
6 time blocks. Các ablation/retrieval/repeats có lịch riêng trong kế hoạch.

Donor fix được đọc theo commit
`9efd23f4157e0d3ab8069fccab7dccf03439a714`.
Archive21 blob nguồn,9 CSV khớp hash và label bridge1.020 cycle.
Data/vendor quality và economic acceptance được báo riêng.
H02 đã hoàn tất audit; readiness cần phục hồi model/context và VNINDEX2026.
H03–H09 tiếp tục theo dependency.

## Checklist đánh giá lại

| Bước | Công việc | Trạng thái |
| --- | --- | --- |
| H01 | Audit donor, dữ liệu/PIT/exposure và kế hoạch bốn nhóm | [x] DONE |
| H02 | Source archive, candidate grid, label bridge và asset readiness | [x] DONE — audit hoàn tất, còn blocker |
| H03 | Protocol máy, registry, inference, families và budget chính xác | [ ] TODO |
| H04 | Adapter/harness trên dữ liệu chung và universe chín mã | [ ] TODO |
| H05 | Kiểm theo phạm vi, PIT/paired/economics/checkpoint | [ ] TODO |
| H06 | Freeze bank/runtime và smoke toàn registry | [ ] TODO |
| H07 | Collect primary, extension, ablation/retrieval và repeats | [ ] TODO |
| H08 | Cold analysis và uncertainty/multiplicity/strata/cost | [ ] TODO |
| H09 | Kết sổ bằng chứng, trạng thái và giới hạn | [ ] TODO |

## Kết quả các phương pháp đã ghi nhận

| Phương pháp | Kết quả |
| --- | --- |
| Bayesian Prior v1 | Pilot FPT20 có return−7,91%, Original−5,67%; accuracy50% so55% |
| Bayesian Prior v2/C2 | Development D+1,742822 đpt, chỉ2/4 mã tăng; NOT_PROMOTED |
| A_tp_pool | Holdout64 điểm D+2,025325 đpt, CI95%[0,135027;4,211864];3/4 mã tăng |
| B_semantic | Development D khoảng+1,455 đpt; không được chọn |
| MT-BICL | Development60 điểm D−5,313090 đpt, accuracy45% so65%; NOT_NOMINATED |

Các vòng dùng cohort/response riêng và Original ghép cặp trong từng vòng.
Kết quả đã lưu không phải kết quả áp dụng lại trên lưới1.020 unit.

## Kiểm tra và bàn giao

MT-BICL được tổ chức theo các module không đánh số phiên bản trong
`core/mt_bicl_*.py`; namespace `outputs/bayesian_benchmark/mt_bicl/`.
Student/teacher và dữ liệu dùng chung tiếp tục thuộc phương pháp hiện hành.
Các hợp đồng kinh tế/PIT/paired/prompt và quyền release vẫn được kiểm riêng.

Phạm vi kiểm của đợt hợp nhất gồm utility/oracle, prompt/facts/policy,
student frozen/query poison, bank/scaler/task/stream leakage, readiness
và hồi quy paired/prompt/token/callers. Biên dịch đúng các Python thay đổi.
Kết quả kiểm PASS gồm159 test riêng biệt trong16 module liên quan;106 test
MT-BICL được chạy lại PASS sau thay đổi nhãn schema cuối. Đã biên dịch36
Python thay đổi; thêm17 lượt kiểm loader/readiness PASS sau khi khóa manifest
mặc định với Git. Raw utility draw SHA đối soát với mốc trước dọn là
`e98d2e0d2dc10f0efe21cd2185f05316d81b62d9aa70f0ba8d2c8c36192b9a90`.
Các log nằm tại `outputs/bayesian_benchmark/mt_bicl/validation.log` và
`validation_mt_bicl.log`. Không chạy lại toàn suite/E2E theo AGENTS1.2.

Đã kiểm diff rỗng cho agents, engine, loader, Bayesian Prior, dữ liệu,
data_manager, utils và cấu hình gốc so mốc bắt đầu. Source/receipt donor và
lưới1.020 unit giữ nguyên byte. Phần dọn ledger đã loại519 request của
thí nghiệm bị bỏ; các nhóm request còn lại được giữ và tên nhánh MT-BICL
được đồng bộ. Readiness mới đã tạo và cold-verify PASS, registry6 nhánh có1 READY và5
BLOCKED_ASSET; model package0/2 component, VNINDEX2026 còn thiếu.
Label bridge1.020 cycle PASS; kinh tế giữ PENDING_EXECUTION_DATA.
Receipt tại `outputs/historical_reevaluation/manifests/asset_readiness.json`.
