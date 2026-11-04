# Baselines và metrics cuối (T24)

Primary: net target; 102 units, 25 UP/77 DOWN, 12 selected dates, sáu historical blocks. Mọi classifier có đúng common support; BA primary, các tỷ lệ JSON/CSV thang 0–1.

| Strategy | N | Accuracy % | BA % | MCC | LONG % | Mean account return % |
|---|---:|---:|---:|---:|---:|---:|
| Full | 102 | 65.6863 | 52.9610 | 0.0601 | 23.5294 | -0.7970 |
| Base | 102 | 60.7843 | 49.7143 | -0.0054 | 28.4314 | -0.7495 |
| CASH | 102 | 75.4902 | 50.0000 | NA | 0.0000 | 0.0000 |
| Train-majority | 102 | 75.4902 | 50.0000 | NA | 0.0000 | 0.0000 |
| Always-LONG cycles | 102 | 24.5098 | 50.0000 | NA | 100.0000 | -2.9997 |
| Momentum 20 | 102 | 49.0196 | 47.3247 | -0.0461 | 48.0392 | -1.6362 |
| Logistic price | 102 | 67.6471 | 55.6104 | 0.1138 | 23.5294 | -0.6831 |
| Logistic matched inputs | 102 | 60.7843 | 52.4156 | 0.0444 | 32.3529 | -1.1050 |
| Factor vote | 102 | 51.9608 | 51.9740 | 0.0340 | 49.0196 | -1.4568 |

Continuous hold price-only: classification NA; 51 accounts, mean account return -2.1275%, held-session fraction 1.0000. Always-LONG cycles là comparator khác, không thay hold hoặc gán 102 classifier observations cho hold.

Full−Base BA = 3.2468 percentage points. Full thấp hơn logistic-price về BA; mọi mean return khác CASH/train-majority trong bảng đều âm. Đây không phải evidence superiority, alpha hoặc profitability.

Pooled gộp confusion cells theo units; macro là trung bình không trọng số của metrics từng mã, kèm n_planned/n_defined. BA/MCC/F1 undefined giữ null/NA, không ép zero. CASH/train-majority có accuracy 77/102 nhờ imbalance, BA 0.5, MCC undefined. Train-majority coincides with CASH trên test không có nghĩa đã fit từ test majority.

Mean return là bình quân 51 symbol/block accounts với các cửa sổ lịch khác nhau, không portfolio return hoặc total-return index. Reference ledger chưa chứng nhận executable fills, settlement/tax/dividend realism; sensitivities T19 giữ riêng. Risk n_defined/mean_given_defined có denominator riêng; Sortino negative-subset SD legacy, không RMS.

Giữ giới hạn study historical exploratory: native row-wise causal T10 FAIL, news PIT/domain validation chưa xác thực, 40 paired groups lệch order và chín cross-epoch groups. Numeric train-fit không chứng nhận ngược native inputs; hosted immutable revisions chưa biết. Không gộp repeats vào main 102 hoặc trộn study trước/sau sửa chart.

## Artifacts

- [Classification pooled/symbol/block](classification.csv), [per-class](per_class.csv), [macro](macro.csv), [headline](main_comparison.csv).
- [Financial aggregation](financial.csv), [510 main accounts](accounts.csv), [stored logistic fits](model_settings.csv), [contracts](baseline_contracts.json), [metrics JSON](metrics.json).
- Cohorts all_102/common_eight_96/recent_nine_54 chồng lấn, không cộng thành observations độc lập; temporal/regime/dependence thuộc T25.

Chỉ thêm bảng phân tích, không inference/refit/sửa predictions hoặc paper. T04/T20/T23 parent hashes khớp; không chạy lại toàn suite/E2E/leakage vì không đổi producer/feature/PIT/ledger. Tests chỉ kiểm support, hold, undefined và CSV. R1 còn bài/response/locators sau T30; chưa đóng reviewer.

## Tái xuất offline

```powershell
py -3.13 -X utf8 scripts/export_revision_final_baselines.py check
py -3.13 -X utf8 scripts/export_revision_final_baselines.py build --output outputs/revision/final_baselines_recheck_v1
```
