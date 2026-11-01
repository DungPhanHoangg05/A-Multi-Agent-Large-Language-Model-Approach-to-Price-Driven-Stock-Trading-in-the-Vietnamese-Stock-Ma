# Target và quy ước metric cho R1

## Phạm vi phiên bản đầu

Audit này replay chín JSON tại `outputs/backtest_result/` trên cùng lịch từng mã. Đây là kiểm toán descriptive/exploratory của 180 điểm legacy, không phải tập final test mới, không khôi phục được request/model/data snapshot lịch sử chỉ bằng việc tái tính số học.

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

Target dự kiến riêng là `label_gross = UP nếu gross_return > 0, ngược lại DOWN`. Chưa dùng target này để báo accuracy hoặc thay nhãn net trong audit. Cần freeze horizon, zero-return convention và contrasts trước đánh giá mới; mọi bảng dùng target nào phải ghi đúng tên target đó. Không chọn target sau khi xem outcome.

## Metrics phân loại

UP là lớp dương; prediction LONG ánh xạ UP, SHORT ánh xạ DOWN. Confusion matrix xuất khóa `tp/fn/tn/fp`; support UP=TP+FN và DOWN=TN+FP. Tỷ lệ trong JSON/CSV là 0–1; report Markdown đổi thành phần trăm, trừ MCC.

| Chỉ số | Định nghĩa |
|---|---|
| Accuracy | (TP+TN)/N |
| Balanced accuracy (primary dự kiến) | (Recall UP + Recall DOWN)/2 |
| MCC | (TP×TN−FP×FN)/sqrt((TP+FP)(TP+FN)(TN+FP)(TN+FN)) |
| Precision UP / Recall UP / F1 UP | TP/(TP+FP); TP/(TP+FN); 2TP/(2TP+FP+FN) |
| Precision DOWN / Recall DOWN / F1 DOWN | TN/(TN+FN); TN/(TN+FP); 2TN/(2TN+FP+FN) |
| Macro-F1 | (F1 UP + F1 DOWN)/2 |
| LONG rate | (TP+FP)/N |

Mẫu số bằng 0 cho `null` trong JSON, `NA` trong bảng/CSV. Không định nghĩa MCC=0 cho constant classifier. BA cần cả hai class recalls xác định. F1 của một lớp được tính trực tiếp từ confusion counts: lớp có support nhưng không prediction có F1=0 dù precision là NA; lớp vừa không support vừa không prediction có F1=NA, nên macro-F1 cũng NA. Empty support không nhận accuracy=0 hay accuracy=1.

**Support:** báo riêng support hợp lệ của từng nhánh và common support có prediction LONG/SHORT hợp lệ ở cả Full và Base reports. UNKNOWN/rỗng được đếm loại trừ; nhãn ngoài schema làm lỗi. So sánh chính dùng common support đồng nhất cho cả hai nhánh và hai constants. Failure-rate counts phải đọc cùng bảng kết quả; không âm thầm gộp lỗi thành CASH. Với tài khoản có prediction không hợp lệ, return của nhánh đó là NA thay vì compound trên các ngày còn lại.

**Pooled:** cộng confusion counts của tất cả observations rồi tính metric. **Macro-over-symbols:** trung bình đều metric từng mã trên support tương ứng, chỉ báo mean nếu tất cả mã có metric xác định; kèm `n_defined_symbols`. Trung bình accuracy chỉ trùng pooled trong trường hợp có cùng mẫu số từng mã. Pooled không có nghĩa 180 quan sát độc lập và không tạo portfolio return.

Runner chỉ nhóm theo `fold`, `regime`, `repeat_id` khi metadata có sẵn trong payload/point; ghi rõ các trường còn thiếu, không suy regime từ future returns. Các nhóm được xuất riêng theo từng mã và chiều metadata; đây chưa thay thế thiết kế outer folds, nhãn regime PIT hay repeated-run study. Không báo CI/p-value từ số cổ phiếu như các replication độc lập trong audit R1 này.

## Baselines và kinh tế

- `constant_down_cash`: luôn dự đoán DOWN/SHORT, không giao dịch, return và phí 0. Đây là constant định nghĩa trước; không gọi nó là majority model fit trên train.
- `constant_up_cycles`: luôn dự đoán UP/LONG, mua và bán lại **mỗi chu kỳ**, trả phí hai chiều mỗi lần. Không gọi nó là buy-and-hold.
- `full` và `base_reports_legacy`: đọc nguyên prediction cũ; tên mới của control chỉ phản ánh việc nhánh đó bỏ cả alpha và sentiment, không sửa key JSON lịch sử.

Return compound trên vốn của từng mã riêng biệt. `mean_independent_account_return_pct` là trung bình chín return tài khoản, không phải return một portfolio đồng bộ. Replay độc lập so sánh với return đã lưu theo sai số làm tròn; mọi sai lệch và cờ `correct_*` không khớp được liệt kê, không dùng cờ lưu làm ground truth phân loại.

`long_cycle_fraction` là số cycle LONG/N cycle; `order_count`=2×số cycle LONG; `gross_traded_notional_vnd` cộng quoted buy/sell notional trước phí/trượt giá. `traded_notional_over_initial_capital` lấy tổng đó chia vốn đầu kỳ, không phải turnover hằng ngày. Brokerage fees và slippage costs được tính riêng trên đường vốn compound.

`cycle_end_drawdown_pct` là sụt giảm so với đỉnh tại cuối các cycle, bao gồm vốn đầu kỳ. Daily exposure/turnover/drawdown là NA vì thiếu daily MTM và lịch/ledger đầy đủ. Không xuất Sharpe/Sortino ở audit R1 để tránh lặp lại vấn đề tần suất của R5.

Để tiếp tục R1 cần frozen train/validation/test OHLCV/calendar/features, labels đã trưởng thành và availability của alpha/sentiment. Sau đó mới fit majority, fixed momentum, hai logistic (price-only và matched information), factor-only và exposure control trên train/validation, purge label overlap, rồi đánh giá cùng folds/chi phí/support. Buy-and-hold thực sự cần một ledger vào đầu kỳ, giữ liên tục qua gap, corporate actions và daily equity. Không có dữ liệu đó thì không công bố số mới cho các baseline này.
