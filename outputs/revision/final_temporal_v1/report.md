# Temporal, regime và dependence cuối (T25)

Chỉ main T04 realization 0/repeat 0 trên cùng T24; không trộn old chart study hoặc tăng N bằng repeats. 102 units/12 selected dates/sáu historical blocks, không là 102 market replications độc lập.

| Cohort | Units | Symbols | Dates | Blocks |
|---|---:|---:|---:|---:|
| all_102 | 102 | 9 | 12 | 6 |
| eight_symbols_six_blocks | 96 | 8 | 12 | 6 |
| nine_symbols_three_recent_blocks | 54 | 9 | 6 | 3 |

Grid 12 dates ×9 symbols có 108 market cells: 102 eligible, sáu BHN cells early blocks thiếu vì valid-suffix/warm-up. Prediction grid chín classifiers: 972 cells, 918 eligible, 54 NA; không backfill CASH. Cohorts chồng lấn, không cộng N.

## Dependence

| Cohort | Lag | Mean accuracy difference | SE | HAC p |
|---|---:|---:|---:|---:|
| common_eight_96 | 0 | 0.031250 | 0.026042 | 0.255346 |
| common_eight_96 | 1 | 0.031250 | 0.023146 | 0.204107 |
| common_eight_96 | 2 | 0.031250 | 0.020172 | 0.149610 |
| recent_nine_54 | 0 | 0.092593 | 0.040713 | 0.072051 |
| recent_nine_54 | 1 | 0.092593 | 0.047112 | 0.106554 |
| recent_nine_54 | 2 | 0.092593 | 0.045710 | 0.098654 |

all_102 Full-only/Base-only correct = 9/4; discordant 13, exact diagnostic p=0.266846 (giả định independent discordances chưa được chứng nhận).

common_eight_96 Full-only/Base-only correct = 7/4; discordant 11, exact diagnostic p=0.548828 (giả định independent discordances chưa được chứng nhận).

recent_nine_54 Full-only/Base-only correct = 7/2; discordant 9, exact diagnostic p=0.179688 (giả định independent discordances chưa được chứng nhận).

HAC là accuracy difference theo ngày trên universe cố định 1/8 hoặc 1/9; lags 0/1/2 đếm selected-date order, không phiên giao dịch liên tiếp. SE/CI/p dùng Bartlett/t(df=dates−1), chỉ sensitivity với 12 hoặc sáu ngày; zero variance cho null/NA. Không pooled HAC cho all_102 vì universe thay đổi ở BHN.

Primary whole-block intervals T04 giữ nguyên; CBB bổ sung đầy đủ tám contrasts ×BA/accuracy ×ba lengths ×ba cohorts. Length đo bằng study blocks (wrap circular), không trading-day length. Recent cohort chỉ ba blocks: length=3 luôn lấy toàn bộ block set nên interval suy biến, không chứng minh precision. Sáu leave-one-block-out chỉ sensitivity, không chọn giai đoạn đẹp.

Tái dùng 18 rows null audit đã khóa, không mô phỏng lại. Zero coverage conditional trong DGP stylized nằm [0.366127, 0.882000], không đạt chứng nhận 95% coverage thị trường; không chọn length hoặc hiệu chỉnh interval thật theo kết quả này. Wilson MC intervals/defined/undefined đầy đủ tại nguồn cũ.

Legacy 180 records/chín mã/53 dates và zero date chung cho cả chín mã giữ trong audit legacy riêng; exact/NW diagnostics cũ không là final effect hoặc pooled HAC. Provenance legacy vẫn unverified theo T15.

## Regime và provenance

Tái tính 102 contexts và kiểm 51 purged folds, khớp labels/medians/folds R2 cũ; không fit lại classifier/preprocessor. Trend = Close/SMA60−1, bull >2%, bear <−2%, còn lại sideways; vol = SD20 returns ddof=1; liquidity proxy = MA20(Close×Volume) theo vendor units. High/low dùng median chỉ trên purged train; ngưỡng suy biến/thiếu lịch sử là unknown. Đây là post-inference descriptive strata, không regime-aware policy confirmatory hoặc chứng nhận PIT/corporate-action-adjusted universe.

Báo đủ observed strata/cohorts/variants, class supports và null metrics. Exposure đối soát trên ba target sessions/unit từ final daily ledger, không là exposure calendar/portfolio có gaps. Toàn bộ labels đã trưởng thành trước freeze cuối; historical points có thể bị model training contamination/memorization, không có untouched prospective holdout được xác nhận. Immutable hosted revisions, news PIT/domain validity và native row-wise causal gate vẫn chưa đạt; không suy alpha/profitability từ subgroup/CI/p.

## Artifacts

- [Temporal date/block](temporal_metrics.csv), [calendar panel](calendar_panel.csv), [regime contexts](regime_labels.csv), [purged folds](folds.csv).
- [Stratified metrics](stratified_metrics.json), [regime table](regime_metrics.csv), [target exposure](target_sessions.csv).
- [Primary/cohort/leave-block diagnostics](primary_dependence.json), [CBB](block_sensitivity.csv), [HAC](panel_hac.csv), [date scores](date_scores.csv), [discordance](discordance.csv).
- [Null/legacy reuse](null_reuse.json), [contamination scope](contamination.json), [report](report.json), [hashes](manifest.json).

Chỉ thêm analysis độc lập, không API/inference/refit hoặc sửa paper/frozen outcomes. Kiểm tests theo phạm vi: regime/PIT leakage, dependent-statistics regressions và final cohort/HAC wiring; không full suite/E2E/null simulation rerun. R2/R5 còn bài/response/locators sau T30.

```powershell
py -3.13 -X utf8 scripts/analyze_revision_final_dependence.py check
py -3.13 -X utf8 scripts/analyze_revision_final_dependence.py build --output outputs/revision/final_temporal_recheck_v1
```
