# Phase B — bộ nhận diện chế độ VN-Index

## W2-03 — đặc trưng EOD

`core/regime_detector.py::build_regime_features(point_in_time_df, as_of_date)` nhận VNINDEX đã được cắt thời gian. Input có ngày lớn hơn cutoff, giá không dương/hữu hạn, ngày trùng/đảo thứ tự hoặc thiếu 200 phiên bị từ chối bằng `ValueError`; không tự bỏ nến lỗi.

Với giá đóng cửa `C[t]`, năm đặc trưng theo thứ tự cố định:

| Tên | Công thức | Đơn vị / khởi động |
| --- | --- | --- |
| `log_return` | `ln(C[t] / C[t-1])` | log tỷ lệ, không nhân 100 |
| `volatility_20` | độ lệch chuẩn mẫu (`ddof=1`) của 20 log-return gần nhất | biến động mỗi phiên, không annualize |
| `distance_ma20` | `C[t] / mean(C[t-19:t]) - 1` | tỷ lệ, 20 phiên |
| `distance_ma50` | `C[t] / mean(C[t-49:t]) - 1` | tỷ lệ, 50 phiên |
| `distance_ma200` | `C[t] / mean(C[t-199:t]) - 1` | tỷ lệ, 200 phiên |

Mọi cửa sổ kết thúc tại `t`, không dùng cửa sổ centered, bfill hay dữ liệu sau `t`. Loại đúng 199 hàng khởi động; năm đặc trưng còn lại phải hữu hạn. Không sử dụng breadth: bốn mã nghiên cứu không đại diện toàn HOSE. Trạng thái giá PIT chưa được xác minh ở Phase A vẫn là giới hạn sử dụng dữ liệu; phép cắt ngày không chứng nhận cơ sở giá.
