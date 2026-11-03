# Target, schema và quy ước metric cho revision

## Phạm vi hiện hành — D2-08

Ngày 03/11/2026: `utils/target_contract.py` và
[`target_schema.json`](target_schema.json) tách các outcome fields khỏi graph
inputs. Engine, robustness và ablation mới ghi `decision_close=C[e-1]`,
`entry_open=O[e]`, `exit_close=C[e+L-1]`, `gross_return`, `net_return`,
`label_net`, `label_gross`, indices/horizon và chi phí label. Return mới là
fraction dạng thập phân (1 = 100%); `actual_pct_change` vẫn là net percent và
`execution_pct_change` là gross percent trong aliases cũ. `label_net` là
primary; zero net hoặc gross đều DOWN. SHORT forecast ánh xạ DOWN nhưng
execution là CASH, không short sale và không phải label bằng zero.

Metadata này được tạo ở bước ghi evaluation record sau inference, không
đưa realised future prices/labels vào `IndicatorAgentState` hoặc prompt.
`net_return` là lợi nhuận ứng viên LONG theo target, không đồng nhất với
realised account return khi SHORT, no-fill, delay hoặc execution stress.
Chi phí sensitivity không thay `label_fee_each_side` và không relabel target.

Record mới ghi `label_contract_version=net_cycle_v1`; record legacy thiếu
provenance giữ `legacy_unverified` và canonical fields null, không lấy
`actual_prev_close` làm `decision_close`. Kiểm canonical records từ chối
thiếu field, giá/phí/return/label tự mâu thuẫn. Đây là validation số học,
không tự xác thực snapshot hay request lịch sử. Chỉ nguồn frame rõ ràng mới
được dùng để tạo canonical outcome, không migration suy đoán artifacts cũ.

Prompt nguồn và actual archived messages giữ nguyên. Chúng đã yêu cầu net
next-Open-to-target-Close sau fee 0,25% và slippage 0,10% mỗi chiều; token
`forecast_horizon=T+2.5` lịch sử là chuỗi hiển thị cho daily L=3, không chứng
nhận settlement. Graph-backed backtest mới chặn chi phí label khác các số
cố định đó trước API, cho đến khi version prompt/protocol riêng. Replay hoặc
execution sensitivity offline vẫn dùng được chi phí khác, không gọi là
classifier đã được elicited lại. `_distill_report`/`_cap_report` và builders
không đổi. Bản English trong appendix là illustrative rendering được sinh
từ compact builder, không giả nhận bản dịch/diễn giải là actual request.

Audit mới nằm tại `outputs/revision/target_contract_v1/`: 102 outcome records
khớp 918 net/gross labels, 600 legacy point records chỉ đối soát alias,
760 archived Decision attempts có net contract (486 R1, 274 R4; gồm smoke,
retry/errors, không gọi là 760 market observations/successes mới).
178/600 aliases bằng entry Open, nhưng decision Close legacy được giữ null
trên cả 600 records do chưa authenticated original snapshot. Bảy units có
label gross khác net; không đổi predictions, fit lại hoặc chọn target theo outcome.

Validator JSON Schema chỉ cần trong môi trường audit/test offline, đã pin
`jsonschema==4.24.0` ở `revision/requirements-r1.txt`; không đổi model runtime
hoặc cài/nâng cấp dependency trong task này.

## Phạm vi phiên bản đầu

Phiên bản audit ban đầu replay chín JSON tại `outputs/backtest_result/` trên cùng lịch từng mã. Các giới hạn dưới đây áp dụng cho legacy audit đó, không phủ nhận bank/ledgers mới đã bổ sung. Đây là kiểm toán descriptive/exploratory của 180 điểm legacy, không phải tập final test mới, không khôi phục được request/model/data snapshot lịch sử chỉ bằng việc tái tính số học.

## Target net giữ nguyên cho replication

Với giá chuẩn `entry_open = Open(e)` và `exit_close = Close(e+L−1)`:

```text
gross_return = exit_close / entry_open - 1
net_return = (exit_close / entry_open)
             * (1 - fee) * (1 - slippage)
             / ((1 + fee) * (1 + slippage)) - 1
label_net = UP nếu net_return > 0; ngược lại DOWN
```

Phí mặc định mỗi chiều là 0,0025 và trượt giá mỗi chiều là 0,001. CLI cho phép khai báo rõ giả định khác; runner từ chối kết quả nếu nhãn lưu không khớp giá chuẩn/chi phí đã chọn. Những tham số replay này không được coi là chứng nhận cấu hình của request lịch sử. Giao dịch LONG dùng toàn bộ vốn, fractional shares; SHORT giữ CASH, lãi suất tiền mặt 0. Thuế riêng, lot size, khả năng khớp lệnh và settlement chưa được mô phỏng trong replay legacy.

`window_end` chỉ là ngày cutoff của artifact; timestamp daily bar `07:00:00` không chứng minh giờ quyết định hay khớp lệnh. Runner chỉ đối soát thứ tự ngày `decision < entry <= exit`, chu kỳ không chồng lấn và test ID/cutoff không trùng. Chưa có daily trading calendar để chứng nhận chính xác L phiên cho mọi artifact.

Audit bắt buộc có `entry_open` và `exit_close`; không lấy `actual_prev_close` thay entry vì trường này có nghĩa legacy không đồng nhất. Không đổi nhãn hoặc artifacts gốc. Khi thiếu giá/nhãn hợp lệ, runner báo lỗi và không xuất bảng thay thế bằng giá suy đoán.

## Target gross nếu nghiên cứu direction forecasting

Target riêng là `label_gross = UP nếu gross_return > 0, ngược lại DOWN`. Gross chưa được dùng trong audit legacy ban đầu, nhưng release 102-unit R1 đã có secondary gross diagnostic trên đúng predictions elicited theo net contract. Diagnostic này không thay primary net target, không chứng minh model được hỏi hoặc tối ưu cho gross. Horizon/zero-return convention và support được giữ nguyên; không chọn target sau khi xem outcome.

## Metrics phân loại

UP là lớp dương; prediction LONG ánh xạ UP, SHORT ánh xạ DOWN. Confusion matrix xuất khóa `tp/fn/tn/fp`; support UP=TP+FN và DOWN=TN+FP. Tỷ lệ trong JSON/CSV là 0–1; report Markdown đổi thành phần trăm, trừ MCC.

| Chỉ số | Định nghĩa |
|---|---|
| Accuracy | (TP+TN)/N |
| Balanced accuracy (primary) | (Recall UP + Recall DOWN)/2 |
| MCC | (TP×TN−FP×FN)/sqrt((TP+FP)(TP+FN)(TN+FP)(TN+FN)) |
| Precision UP / Recall UP / F1 UP | TP/(TP+FP); TP/(TP+FN); 2TP/(2TP+FP+FN) |
| Precision DOWN / Recall DOWN / F1 DOWN | TN/(TN+FN); TN/(TN+FP); 2TN/(2TN+FP+FN) |
| Macro-F1 | (F1 UP + F1 DOWN)/2 |
| LONG rate | (TP+FP)/N |

Mẫu số bằng 0 cho `null` trong JSON, `NA` trong bảng/CSV. Không định nghĩa MCC=0 cho constant classifier. BA cần cả hai class recalls xác định. F1 của một lớp được tính trực tiếp từ confusion counts: lớp có support nhưng không prediction có F1=0 dù precision là NA; lớp vừa không support vừa không prediction có F1=NA, nên macro-F1 cũng NA. Empty support không nhận accuracy=0 hay accuracy=1.

**Support:** báo riêng support hợp lệ của từng nhánh và common support có prediction LONG/SHORT hợp lệ ở cả Full và Base reports. UNKNOWN/rỗng được đếm loại trừ; nhãn ngoài schema làm lỗi. So sánh chính dùng common support đồng nhất cho cả hai nhánh và hai constants. Failure-rate counts phải đọc cùng bảng kết quả; không âm thầm gộp lỗi thành CASH. Với tài khoản có prediction không hợp lệ, return của nhánh đó là NA thay vì compound trên các ngày còn lại.

**Pooled:** cộng confusion counts của tất cả observations rồi tính metric. **Macro-over-symbols:** phải đọc đúng policy từng release: audit legacy ban đầu chỉ báo mean nếu tất cả mã defined; release mới có thể báo mean trên defined symbols và luôn kèm denominator thực. Không gọi mean trên bốn mã có BA defined là mean đủ tám mã. Trung bình accuracy chỉ trùng pooled khi mẫu số từng mã bằng nhau. Pooled không có nghĩa các quan sát độc lập và không tạo portfolio return.

Runner chỉ nhóm theo `fold`, `regime`, `repeat_id` khi metadata có sẵn trong payload/point; ghi rõ các trường còn thiếu, không suy regime từ future returns. Các nhóm được xuất riêng theo từng mã và chiều metadata; đây chưa thay thế thiết kế outer folds, nhãn regime PIT hay repeated-run study. Không báo CI/p-value từ số cổ phiếu như các replication độc lập trong audit R1 này.

## Baselines và kinh tế

- `constant_down_cash`: luôn dự đoán DOWN/SHORT, không giao dịch, return và phí 0. Đây là constant định nghĩa trước; không gọi nó là majority model fit trên train.
- `constant_up_cycles`: luôn dự đoán UP/LONG, mua và bán lại **mỗi chu kỳ**, trả phí hai chiều mỗi lần. Không gọi nó là buy-and-hold.
- `full` và `base_reports_legacy`: đọc nguyên prediction cũ; tên mới của control chỉ phản ánh việc nhánh đó bỏ cả alpha và sentiment, không sửa key JSON lịch sử.

Return compound trên vốn của từng mã riêng biệt. `mean_independent_account_return_pct` là trung bình chín return tài khoản, không phải return một portfolio đồng bộ. Replay độc lập so sánh với return đã lưu theo sai số làm tròn; mọi sai lệch và cờ `correct_*` không khớp được liệt kê, không dùng cờ lưu làm ground truth phân loại.

`long_cycle_fraction` là số cycle LONG/N cycle; `order_count`=2×số cycle LONG; `gross_traded_notional_vnd` cộng quoted buy/sell notional trước phí/trượt giá. `traded_notional_over_initial_capital` lấy tổng đó chia vốn đầu kỳ, không phải turnover hằng ngày. Brokerage fees và slippage costs được tính riêng trên đường vốn compound.

`cycle_end_drawdown_pct` là sụt giảm so với đỉnh tại cuối các cycle, bao gồm vốn đầu kỳ. Daily exposure/turnover/drawdown là NA trong legacy replay ban đầu vì thiếu daily MTM phù hợp snapshot đó. Study mới đã có 510 daily ledgers riêng; D2-06 đối soát risk frequency, D2-07 bổ sung execution bounds mà không gán provenance mới cho legacy. Không dùng historical cycle ratios với sqrt(252) để lập luận đầu tư.

Bank R1 mới đã bổ sung frozen train/validation/test inputs và labels trưởng thành, train/validation-only baselines với purge, cùng daily price-series holding comparator. Exposure-matched controls, authenticated historical snapshots và total-return/corporate-action certification vẫn riêng. Không diễn giải continuous-hold price-only comparator thành total-return buy-and-hold hoặc dùng kết quả mới xác thực ngược submission.
