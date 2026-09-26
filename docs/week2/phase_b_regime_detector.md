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

## W2-04 — cấu hình chốt trước fit

Chốt ngày 2026-09-26 trước khi chạy fit trên CSV thật. `hmmlearn==0.3.3`, `scikit-learn==1.7.2`; lưu phiên bản Python/NumPy/Pandas/SciPy cùng artifact để phát hiện khác môi trường. [Tài liệu hmmlearn](https://hmmlearn.readthedocs.io/en/0.3.3/api.html) phân biệt Viterbi, smoothing và posterior; ở ngày truy vấn chỉ lấy posterior **cuối chuỗi đã cắt** để không đưa quan sát tương lai vào bước backward.

| Thành phần | Giá trị cố định |
| --- | --- |
| HMM | Gaussian, 4 trạng thái, covariance `diag`, seed 42 |
| EM | tối đa 500 vòng, `tol=0.001`, `min_covar=0.001`, implementation `log`; các prior giữ mặc định hmmlearn 0.3.3 |
| Chuẩn hóa | `StandardScaler` fit trên đúng năm đặc trưng của tập train, không fit lại lúc suy luận |
| Train | input chỉ từ 2018-01-01 đến 2022-12-31, tối thiểu 300 hàng đặc trưng sau khởi động; không âm thầm cắt 2023+ |
| Lưu | JSON chứa tham số HMM/scaler, hash ngày và Close được dùng, cấu hình, phiên bản, thống kê và thời điểm cuối train; ghi nguyên tử |
| Tái lập | seed cố định, không sweep seed hoặc chọn cấu hình dựa trên kết quả 2023+; môi trường được ghi trong artifact |

Không refit trên một instance đã fit. Model train đầy đủ 2018–2022 chỉ được suy luận tại `as_of_date >= train_end_date`. Để phân loại episode trước `train_end_date`, phải tạo instance khác, fit **một lần** trên prefix 2018 đến ngày quyết định với cùng cấu hình; toàn bộ scaler, ngưỡng và ánh xạ cũng chỉ dùng prefix đó. Model đầy đủ không được dùng để gán regime PIT cho episode trong quá khứ.

### Ánh xạ và fallback chốt trước xem kết quả

ID kết quả cố định: 0 BULL, 1 BEAR, 2 CHOPPY, 3 CONSOLIDATION; tách khỏi ID latent của HMM. Dùng posterior train để tính trung bình có trọng số của từng đặc trưng. BULL là trạng thái có `distance_ma200` cao nhất, BEAR thấp nhất; hai trạng thái còn lại được xếp theo `volatility_20`, cao hơn là CHOPPY. Khi bằng nhau, dùng ID latent nhỏ hơn để phá hòa.

HMM được dùng khi EM thực sự dừng do gain trong `[0, tol)` trước trần 500 vòng, mỗi trạng thái có tỷ trọng posterior ít nhất 5%, mean MA200 của BULL dương và BEAR âm, khoảng cách hai mean ít nhất `0.5 * std_train(distance_ma200)`, và mean volatility của CHOPPY ít nhất 1,1 lần CONSOLIDATION. Nếu bất kỳ tiêu chí nào thất bại, lưu lý do và dùng fallback đa yếu tố đã chốt:

- Ngưỡng trend = median của `abs(distance_ma200)` trong train. Hai khoảng cách MA50/200 cùng dương và MA200 vượt ngưỡng → BULL; cùng âm và MA200 dưới âm ngưỡng → BEAR.
- Các trường hợp còn lại: volatility20 từ phân vị 2/3 train trở lên → CHOPPY; dưới ngưỡng → CONSOLIDATION.
- `volatility_level`: LOW dưới phân vị 1/3, HIGH từ phân vị 2/3 trở lên, MEDIUM ở giữa. `trend_strength = abs(mean(distance_ma20, distance_ma50, distance_ma200)) / max(volatility_20, 1e-12)`; không có đơn vị.

Fallback này dùng khoảng cách MA và biến động Close thay cho ví dụ ATR/ADX trong kế hoạch tổng; không bổ sung breadth chưa được xác thực. Tiêu chí được áp dụng tự động, không đổi ngưỡng sau khi xem regime hoặc hiệu quả giao dịch.

## W2-05 — model đóng băng và artifact

`MarketRegimeDetector.fit` kiểm tra toàn bộ input trước fit; nến ngoài 2018–2022 hoặc ít hơn 300 hàng đặc trưng bị từ chối. Instance đã fit/nạp không được refit. `save` lưu JSON qua file tạm và thay nguyên tử; không có pickle hoặc nạp mã thực thi. `load` kiểm tra checksum, format, shape/xác suất/covariance, scaler, phiên bản và hash train tùy chọn. `metadata` trả deep copy.

Lệnh `py -3.13 -X utf8 scripts/train_regime_detector.py` kiểm checksum CSV từ manifest W1, cắt khoảng train tường minh và lưu `data_manager/regime_model.json`; từ chối ghi đè artifact hiện có. Lệnh cùng script với `--verify-only` không refit, kiểm artifact với hash train hiện tại. Cắt khoảng ở runner không thay thế kiểm cutoff nghiêm ngặt trong `fit`.

Đã fit 1.251 nến, 1.052 hàng đặc trưng, 2018-01-02 đến 2022-12-30; hash ngày/Close train `dadb02d1c14a96d3d4b9ac906518afe45b5a67d77ba990b87e0452fec30a8be6`. Artifact ghi `price_basis_status=UNVERIFIED`, `artifact_purpose=RESEARCH_ONLY`; không chứng nhận giá PIT hay mở gate nhãn kinh tế.
