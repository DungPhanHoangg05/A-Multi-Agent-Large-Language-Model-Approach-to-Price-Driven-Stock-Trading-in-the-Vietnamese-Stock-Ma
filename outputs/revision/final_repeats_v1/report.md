# Repeats, factorial và placebo cuối (T26)

Chỉ final T04 sau sửa chart; tái kiểm toàn bộ actual raw/checkpoints/parent/prompt, không trộn Decision outcomes trước sửa chart. Không gọi API/inference, không đổi frozen source/prompts hoặc lựa chọn executions.

| Panel | Units/execution | Symbols | Dates | Blocks | UP/DOWN | Variants | Executions | Decisions |
|---|---:|---:|---:|---:|---|---|---:|---:|
| upstream | 9 | 9 | 3 | 3 | 2/7 | B/AS | 3 | 54 |
| factorial | 9 | 8 | 4 | 3 | 2/7 | B/A/S/AS/P | 3 | 135 |

Upstream 54 Decisions gồm 18 main r0 dùng chung và 36 executions bổ sung, không là 54 calls mới. Hai panels có support/prompt family khác nhau; không chọn panel BA cao thay main 102 hoặc trừ hai SD để nhận diện variance components. Mean return là bình quân symbol/block accounts riêng (upstream chín, factorial tám mỗi variant/execution), không portfolio return.

| Panel | Variant | BA mean % | Sample SD (pp) | BA min–max % | Mean account return % |
|---|---|---:|---:|---|---:|
| upstream | B | 90.4762 | 10.9109 | 78.5714–100.0000 | 0.3714 |
| upstream | AS | 95.2381 | 4.1239 | 92.8571–100.0000 | 0.4955 |
| factorial | B | 28.5714 | 7.1429 | 21.4286–35.7143 | -1.6995 |
| factorial | A | 19.0476 | 4.1239 | 14.2857–21.4286 | -2.0339 |
| factorial | S | 14.2857 | 0.0000 | 14.2857–14.2857 | -2.3418 |
| factorial | AS | 19.0476 | 10.9109 | 7.1429–28.5714 | -2.2282 |
| factorial | P | 30.9524 | 4.1239 | 28.5714–35.7143 | -1.4154 |

## Contrasts factorial

| Contrast | BA mean (pp) | SD (pp) | Conditional percentile interval (pp) | Descriptive family envelope (pp) | Defined/draws |
|---|---:|---:|---|---|---|
| AS-B | -9.5238 | 10.9109 | [-22.2222, 9.5238] | [-37.1429, 18.0952] | 6986/10000 |
| A-B | -9.5238 | 4.1239 | [-20.3704, 14.2857] | [-37.1429, 18.0952] | 6986/10000 |
| AS-S | 4.7619 | 10.9109 | [-6.6667, 24.0741] | [-22.8571, 32.3810] | 6986/10000 |
| S-B | -14.2857 | 7.1429 | [-29.6296, 10.0000] | [-41.9048, 13.3333] | 6986/10000 |
| AS-A | 0.0000 | 12.3718 | [-20.0000, 11.1111] | [-27.6190, 27.6190] | 6986/10000 |
| AS-P | -11.9048 | 14.8690 | [-28.5714, 4.7619] | [-39.5238, 15.7143] | 6986/10000 |
| interaction | 14.2857 | 14.2857 | [-16.6667, 38.8889] | [-13.3333, 41.9048] | 6986/10000 |

Interaction AS−A−S+B = 14.2857 pp; AS−max(A,S) gap of means = 0.0000 pp. Đây là hai estimands khác nhau; best-single diagnostic không thêm thành contrast thứ tám hoặc làm cơ sở chọn branch/seed.

BA family có 6986 joint finite và 3014 mất class trên 10.000 draws; max-deviation radius 27.6190 pp. Có 7/7 family envelopes chứa zero; chưa hiệu chuẩn simultaneous coverage/FWER, không suy p-value, synergy hoặc chứng minh không có effect. Undefined giữ null/NA, không zero. Mọi factorial mean account return âm; upstream mean dương không chứng minh profitability trên main/support khác.

## Pairing và placebo

Tái kiểm 375 jobs/147 paired groups: actual upstream reports/rules và full factorial scalar/signal/donor content khớp assets. Donor chín units thuộc purged train, label exit trước validation, giữ current factor names, rank-slot schema/deep missingness và current sentiment; một predetermined donor vector/cutoff, không là placebo distribution hoặc name-matched covariance. Normalizer is_reliable=false không tự nghĩa thiếu sentiment: availability dựa actual report và số bài/scorer provenance, không domain/PIT validation.

Successful-call order khác planned listing ở main 3/102, upstream 10/18, factorial 27/27; tổng 40 groups. Cross-epoch groups main ba/upstream hai/factorial bốn, tổng chín. Không sửa order, bỏ outcomes hoặc gọi bù; hosted immutable revisions unknown, alias/configured temperature không chứng nhận served weights/determinism. Source Pattern reuse nguyên input theo protocol không là gộp old Decision outcomes.

Giữ native row-wise causal T10 FAIL, news PIT/domain validity và fill/settlement limits. Main/upstream compact alpha khác explicit five-row factorial; Full−Base là bundle contrast, AS−P không tự định danh causal information effect, scalar integrity không chứng minh semantic compliance. Repeat disagreement/SD chỉ mô tả ba executions trên panel nhỏ, không SD của main 102 hoặc variance decomposition.

## Artifacts

- [Mean/SD/range](repeat_summary.csv), [per-execution metrics](executions.csv), [per-class](per_class.csv), [disagreement](disagreement.csv), [variant intervals](variant_intervals.csv).
- [Contrasts](contrasts.csv), [BA family](ba_family.json), [best-single diagnostic](best_single_diagnostic.json), [full panel metrics](panels.json).
- [189 actual predictions](predictions.csv), [unit support](support.csv), [donor chronology/mask](donors.csv), [pairing/order](pairing.csv), [parent lineage](lineage.csv), [accounts](accounts.csv).
- [Protocol](protocol.json), [QA](report.json), [manifest](manifest.json). R3/R4 còn sửa bài/response/locators sau T30.

Kiểm theo phạm vi: repeat identity/undefined/statistics, factorial prompt/leakage/donor/statistics/resume và final table estimands. Không full suite/E2E; không đổi producer/selection/inputs hoặc ghi paper. Parent bytes và frozen sources được kiểm lại; T23 independent replay vẫn là bằng chứng riêng, không ghi đã chạy lại ở đây.

```powershell
py -3.13 -X utf8 scripts/export_revision_final_repeats.py check
py -3.13 -X utf8 scripts/export_revision_final_repeats.py build --output outputs/revision/final_repeats_recheck_v1
```
