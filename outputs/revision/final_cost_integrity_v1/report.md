# Chi phí và integrity cuối (T27)

Phạm vi: closure của release T04, phân tích offline; không gọi API, không sửa raw hoặc paper.

| Phạm vi | Attempts | Success | Errors | Prompt tokens quan sát | Completion tokens quan sát | Latency success tổng (s) |
|---|---:|---:|---:|---:|---:|---:|
| corrected_chart_source | 335 | 313 | 22 | 527699 | 166867 | 759.378047 |
| minimal_continuation | 194 | 182 | 12 | 293885 | 158161 | 375.304063 |
| pattern_replay_original_request | 120 | 120 | 0 | 241744 | 15708 | 227.996974 |
| closure_total | 649 | 615 | 34 | 1063328 | 340736 | 1362.679084 |
| corrected_chart_requests_excluding_replayed_pattern | 529 | 495 | 34 | 821584 | 325028 | 1134.682110 |

Các hàng scope có hàng tổng/chồng lắp; không cộng lại. Chi phí tiền: NA; usage/latency 34 errors: NA, không giả định bằng zero.

375/375 jobs, missing=0; 615 nhóm công việc, 24 nhóm retry, 34 attempts lỗi trước success. retry_groups.csv giữ ID, số attempts và cross-epoch; không coi time gap là sleep thực.

120 upstream realizations dùng chung cho 375 Decisions; Indicator deterministic không API, 120 Pattern replay +120 Trend calls thực. Xác minh 240 files Pattern với nguồn gốc byte, 194 reservations từ snapshot T04 (không mở SQLite).

Đối soát 240 Vision requests với cache và template Việt, render lại 204 PNG từ 102 cửa sổ giá đóng băng: byte/pixel, geometry/màu nến, support/resistance và legend đều khớp. Fixture có gap, 22 up/22 down/một doji. Xem fixture_pattern.png và fixture_trend.png.

execution_epochs.csv tách scope/epoch/provider/node/model; attempts.csv giữ aliases, fingerprints, seed và timestamps raw. Có 91 attempts không quan sát epoch/org, 40 fingerprints; immutable served-weight revision vẫn unknown. 40 paired order deviations và chín cross-epoch groups giữ nguyên.

Usage calls lỗi và latency lỗi không có raw; null, không zero. Latency là tổng/quantiles thời gian request thành công, không walltime hoặc sleep.
Pattern tokens/latency thuộc call gốc, không replay lookup. Mỗi request chỉ tính một lần dù shared nhiều Decisions; không là toàn bộ chi phí dự án/smoke/archive.
91 Pattern requests thiếu epoch/org; alias/fingerprint không xác minh immutable served weights. Không suy org từ shard hoặc ngân sách tiền từ token counts.
Fixture xác minh màu thân Close/Open: green #006340, red #A02128, doji red; không phải màu so previous Close hay forecast. Support blue #0000ff, Resistance red #ff0000, legend handles đúng.
Actual Vision dùng template Việt: từ xanh không phân biệt blue/green rõ bằng English. Kiểm pixel/template không xác thực cách VLM hiểu ngữ nghĩa. Không sửa hồi tố raw hoặc ảnh legacy có legend sai.
Chỉ whitelist cuối 375 jobs đầy đủ; không tuyên bố hoàn tất các grid legacy 474/270. R9/R14 còn response/locator/quyền public/PID T34, T30 chưa đạt.

Kiểm: `py -3.13 -X utf8 scripts/analyze_revision_final_costs.py check`. Build lại phải dùng `build --output outputs/revision/final_cost_integrity_replay_v1` chưa tồn tại. Không API/key/model probe; không overwrite release cũ.
