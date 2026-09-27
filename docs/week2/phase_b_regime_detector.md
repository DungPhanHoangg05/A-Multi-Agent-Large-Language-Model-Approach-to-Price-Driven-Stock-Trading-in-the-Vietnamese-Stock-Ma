# Phase B — bộ nhận diện chế độ VN-Index

**Cập nhật 26/09/2026 sau Phase B:** [Gate giá Phase A](phase_a_price_gate.md) đã mở bằng bộ giá thô cổ phiếu VCI riêng. Các ghi nhận gate bị chặn bên dưới mô tả thời điểm triển khai Phase B. Artifact HMM và CSV VN-Index giữ nguyên; điều kiện model prefix cho episode trước cuối train vẫn bắt buộc.

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

## W2-06 — kết quả calibration trên train

HMM hội tụ sau 41 vòng, gain cuối 0,00082354. Ánh xạ latent 0–3 lần lượt `[BULL, CHOPPY, CONSOLIDATION, BEAR]`; tỷ trọng posterior train lần lượt 32,84%, 23,54%, 32,54%, 11,09%. Các tiêu chí W2-04 đều đạt nên artifact dùng `classification_method=HMM`, `fallback_reasons=[]`. Đây là thống kê calibration, không phải kết quả walk-forward hay kết quả giao dịch.

Artifact format 2 thêm mapping và quyết định fallback. Loader có thể chuyển format 1 của W2-05 sang calibration theo đúng quy tắc đã chốt, không refit HMM/scaler. Khi nạp format 2, mapping/fallback phải khớp kết quả tính lại từ thống kê train; dữ liệu bị sửa sẽ bị từ chối. Khi các phân vị biến động đều bằng 0, giá phẳng được xem là CONSOLIDATION với biến động LOW, tránh coi không biến động là CHOPPY.

## W2-07 — API theo ngày quyết định

```python
from core.regime_detector import MarketRegimeDetector

detector = MarketRegimeDetector.load("data_manager/regime_model.json")
state = detector.get_market_regime("2023-01-10")
# Có thể truyền archive VNINDEX làm đối số thứ hai để tránh đọc CSV mỗi lần.
# Với snapshot đã cắt: detector.classify_regime(snapshot, "2023-01-10").
```

`get_market_regime` là API archive: cắt hàng theo ngày **trước** kiểm tra giá, tính đặc trưng và lấy posterior. `classify_regime` là API snapshot: từ chối ngay input có nến sau cutoff. Cả hai đòi hỏi model đã fit/nạp, `train_end_date <= as_of_date` và toàn bộ prefix train trong lịch sử truy vấn có đúng hash. Vì vậy không ghép model vào lịch sử mã khác, lịch thiếu phiên, giá train bị sửa hoặc snapshot bỏ phần khởi động.

Kết quả chỉ chứa bảy trường schema W1; ID/name có ánh xạ cố định, scalar Python gốc, ngày định dạng ISO và `feature_end_date <= as_of_date`. Ngày nghỉ trả ngày phiên cuối thật, không tạo nến giả. `validate_regime_state` kiểm cả schema và tính nhất quán ID/name, ngày cutoff. Posterior HMM được lấy ở cuối chuỗi đã cắt, không decode toàn archive rồi lấy lại một hàng quá khứ. Model, scaler, mapping và ngưỡng không thay đổi trong suy luận.

Model đầy đủ hiện từ chối truy vấn trước 2022-12-30. Khi Phase C làm episode 2020–2022, cần fit/cache model prefix bằng cùng cấu hình trên dữ liệu chỉ đến ngày quyết định, không dùng artifact đầy đủ cho những ngày đó. Các kết quả trên CSV hiện vẫn là nghiên cứu do gate cơ sở giá còn chặn.

## W2-08 — kiểm toán thời gian và hồi quy

Các test nằm trong `tests/test_regime_features.py`, `test_regime_model.py`, `test_regime_mapping.py`, `test_regime_api.py` và `test_regime_leakage.py`. Test model còn kiểm tra artifact của đặc trưng gần hằng số: StandardScaler đặt scale bằng 1 trong ngưỡng sai số float64, không phải lúc nào cũng bằng căn phương sai. Bộ leakage chuyên biệt kiểm:

- Sửa toàn bộ giá sau cutoff thành NaN, Infinity hoặc giá cực lớn không thay đổi endpoint HMM; fallback cũng giữ nguyên khi giá tương lai bị sửa.
- Snapshot còn nến tương lai, model/scaler/calibration đã fit sau cutoff hoặc train ngoài 2018–2022 đều bị từ chối.
- Fit hai prefix giống nhau dù archive sau cutoff khác nhau cho cùng HMM, scaler, mapping, ngưỡng và kết quả; truy vấn nhiều ngày không đổi tham số đã đóng băng.
- Thiếu khởi động, thiếu/sửa hàng train, metadata calibration/hội tụ sai, tham số không hữu hạn hoặc scalar NumPy ở JSON đều gây `ValueError`.

Kiểm tra này chứng minh hợp đồng thời gian của thuật toán trên dữ liệu cung cấp, không chứng nhận rằng provider chưa điều chỉnh hồi tố giá lịch sử. Gate giá Phase A vẫn giữ nguyên. Cấu hình HMM, fallback và tiêu chí chất lượng không được chỉnh sau khi quan sát kết quả fit thật.

### Gate cuối Phase B ngày 2026-09-26

| Lệnh | Kết quả |
| --- | --- |
| `py -3.13 -m compileall agents core data_manager scripts tests utils` | Pass |
| `py -3.13 -X utf8 -m unittest discover -s tests -v` | Pass 135 test (26 test regime mới) |
| `py -3.13 scripts/run_end_to_end_test.py` | Pass, giữ hợp đồng kinh tế và upstream ghép cặp |
| `py -3.13 -X utf8 -m unittest discover -s tests -p 'test_*leakage.py' -v` | Pass 16 test |
| `py -3.13 -X utf8 scripts/train_regime_detector.py --verify-only` | Hash/model/scaler/calibration của artifact thật hợp lệ |

Các task W2-03 đến W2-08 được làm trên sáu nhánh riêng từ `develop`; từng nhánh qua bốn gate trước khi tích hợp. Phase C (Memory Bank) và Phase D (biểu đồ/chốt tuần) chưa thực hiện; không đánh dấu W2-16 hay W2-17 hoàn thành chỉ vì Phase B đã pass hồi quy.
