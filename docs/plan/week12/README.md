# W12 — Xác nhận độc lập và bàn giao

[Kế hoạch tổng](../plan.md) · [Tiến độ W11](../week11/README.md) ·
[Kế hoạch đánh giá](../week11/historical_reevaluation_plan.md)

Hệ thống giữ Original, Bayesian Prior v1, Bayesian Prior v2/C2,
Bayesian Prior A/B và MT-BICL. Giai đoạn hiện hành đánh giá lại trên
dữ liệu historical đã exposed; chưa có release xác nhận forward.

## Điều kiện mở xác nhận

- Hoàn tất registry/common support và cold analysis trong W11.
- Khóa candidate bằng rule được đăng ký trước, giữ toàn bộ kết quả âm.
- Audit exposure, source/model/options, point-in-time và execution data.
- Khóa cohort tương lai sau freeze, đơn vị cluster, power/precision,
  protocol và N trước response đầu.
- Báo risk/exposure, chi phí, missing support và khả năng khớp lệnh.

Repeats không tăng N thị trường và kết quả historical không cấp
bằng chứng prospective. Bàn giao giữ source/runtime/data/model hashes,
raw requests/responses, checkpoints, labels và report tái lập.
