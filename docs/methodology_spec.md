# Đặc tả phương pháp nghiên cứu

**Đề tài:** Regime-Aware Multi-Task Bayesian In-Context Learning for Multi-Agent LLM Stock Trading

**Phiên bản đặc tả:** 2026-09-24

**Phạm vi:** Dữ liệu Daily EOD, VN-Index và FPT/VNM/VCB/MWG. Đây là hợp đồng triển khai cho các tuần tiếp theo; kết quả kinh tế chỉ được công bố sau khi dữ liệu và bốn gate kiểm thử đạt yêu cầu.

## 1. Câu hỏi và đơn vị quan sát

Mục tiêu là kiểm tra liệu ba chu kỳ giao dịch đã tất toán trong cùng chế độ thị trường có giúp Decision Agent ra quyết định $T+2.5$ tốt hơn zero-shot và ba cách chọn prior đối chứng hay không. Một **test point** là quyết định sau khi đóng cửa phiên $t$ cho một mã. Năm agent tạo tín hiệu tại $t$ từ dữ liệu có sẵn đến $t$; nhãn kết quả chỉ được biết sau phiên $t+3$.

Hai cấp thông tin không được trộn lẫn: `MarketRegimeState` mô tả VN-Index tại $t$; `HistoricalTaskRecord` mô tả một chu kỳ cổ phiếu đã hoàn tất trước $t$. Ánh xạ từ prior task của bài báo sang chu kỳ giao dịch là **thích ứng của đề tài**, không phải bằng chứng rằng LLM thực hiện suy diễn Bayes đúng nghĩa hay một posterior được hiệu chuẩn. Hiệu quả phải được kiểm nghiệm bằng thí nghiệm đối chứng.

## 2. Dữ liệu và phân chia thời gian

| Thành phần | Quy ước |
| --- | --- |
| Vũ trụ | VN-Index; FPT, VNM, VCB, MWG |
| Tần suất | Daily EOD theo phiên giao dịch, múi giờ Việt Nam |
| Khoảng thu thập | 2018-01-01 đến 2025-12-31, bao gồm hai đầu nếu có giao dịch |
| Huấn luyện regime và tạo memory | 2018-01-01 đến 2022-12-31 |
| Kiểm định ngoài mẫu | 2023-01-01 đến 2024-12-31 |
| Năm 2025 | Lưu để tái lập và khảo sát sau; không tham gia fit, chuẩn hóa, chọn tham số hoặc tạo prior cho kiểm định 2023–2024 |
| CSV chuẩn | `Datetime,Open,High,Low,Close,Volume`, ngày ISO, thứ tự tăng; giá cổ phiếu theo nghìn VND, chỉ số theo điểm |
| Nguồn W1 | `vnstock` 3.5.2: VCI là nguồn chính, KBS thay nguyên nến khi VCI sai OHLC; manifest ghi phiên bản, thời điểm lấy, checksum SHA-256 và từng dòng thay |

Script `scripts/prepare_historical_data.py` loại bản ghi nằm ngoài khoảng yêu cầu, sắp ngày và đổi tên cột. Nó **không** tự điền phiên thiếu, xóa ngày trùng, nội suy giá hay ép giá Open vào khoảng High–Low. Điều kiện chấp nhận: ngày hợp lệ và duy nhất; 5 giá trị số hữu hạn; Open/High/Low/Close dương; Volume không âm; High là cực đại và Low là cực tiểu hợp lệ trong nến; lịch bốn cổ phiếu khớp VN-Index. Lịch phiên VN-Index là đối chiếu thực nghiệm cho bốn mã này, không phải giả định mọi cổ phiếu luôn giao dịch. Nếu có ngừng giao dịch hợp lệ, phải ghi ngoại lệ theo từng mã/ngày với nguồn chứng minh trước khi sửa quy tắc.

**Kết quả W1:** bản tải VCI có 1.999 ngày/mã. Bốn nến VN-Index vi phạm OHLC vào 2019-06-24, 2019-06-25, 2019-06-26 và 2021-08-23 đã được thay bằng nguyên nến KBS cùng ngày. Cả bản gốc và bản thay nằm trong `data/historical/manifest.json`; năm CSV đã pass kiểm tra offline. [Biên bản dữ liệu](plan/week1/data_audit.md) ghi phạm vi của phép kiểm toán điều chỉnh giá: hiện chưa đủ căn cứ xem Open/Close trong CSV là giá thực thi chưa điều chỉnh. Không dùng CSV để sinh nhãn kinh tế cho Memory Bank đến khi có giá thực thi hoặc hệ số điều chỉnh phù hợp từng thời điểm.

## 3. Giao thức thời gian và nhãn kinh tế

Gọi $t$ là ngày nến cuối được thấy. `point_in_time_df` phải có `Datetime <= as_of_date = t`. Quyết định `LONG` mua tại `Open(t+1)` và đóng vị thế tại `Close(t+3)`, tức ba phiên thực thi. `SHORT` trong schema quyết định hệ thống hiện tại có nghĩa **giữ tiền mặt**, không mở vị thế bán khống. Phí môi giới 0,25% và trượt giá 0,10% áp dụng cho cả chiều mua lẫn chiều bán. Không được đổi hợp đồng này khi thêm prior.

Mọi nhãn `net_return_pct` của prior task phải lấy từ `100 * core.backtest_engine.compute_round_trip_net_return(entry_open, exit_close, fee=0.0025, slippage=0.001)`. `actual_direction = "UP"` và `result = "WIN_IF_LONG"` khi lợi nhuận ròng **lớn hơn 0**; ngược lại là `DOWN` và `LOSS_IF_LONG`. Không dùng Close-to-Close cùng ngày hoặc return trước phí. `entry_date` là ngày $t+1$, `exit_date` là ngày $t+3$; record chỉ đủ điều kiện thành prior khi `exit_date < current_as_of_date`. Việc hai chu kỳ chồng lấn phải được tính tới trong kiểm định thống kê.

`was_bull_trap` chỉ được gắn sau khi thống nhất quy tắc vận hành ở tuần tạo memory: tín hiệu Trend/Pattern mang hướng tăng tại $t$ nhưng LONG ròng không có lãi ở $t+3$. Giữ cả tín hiệu gốc lẫn nhãn kinh tế để kiểm toán. Nếu tín hiệu của một agent thiếu, không suy diễn thay; record phải bị loại và ghi lý do.

## 4. Schema và kiểm tra quan hệ

- [HistoricalTaskRecord](plan/week1/historical_task_record.schema.json): `episode_id`, mã, ngày quyết định/vào/ra, regime, tín hiệu năm agent, hướng thực tế và kết quả LONG sau phí. Giá trị lưu JSON phải là kiểu Python gốc, không chứa NumPy scalar.
- [MarketRegimeState](plan/week1/market_regime_state.schema.json): ngày quyết định, ID 0–3, nhãn trạng thái, mức biến động, độ mạnh xu hướng, nguồn VN-Index và ngày cuối dùng để tạo đặc trưng. Tên bốn regime chuẩn hóa là `BULL`, `BEAR`, `CHOPPY`, `CONSOLIDATION`; các tên ví dụ trong kế hoạch tổng như `BEAR_CRASH` phải được ánh xạ rõ trước khi tạo memory.

JSON Schema kiểm tra hình dạng và kiểu từng trường. Các bất biến xuyên trường phải có code và test riêng: `as_of_date < entry_date < exit_date` theo thứ tự **phiên**; `feature_end_date <= as_of_date`; khi truy xuất `record.exit_date < current_as_of_date`; `actual_direction` và `result` khớp dấu của `net_return_pct`; `episode_id` duy nhất. Vi phạm phải ném `ValueError` hoặc `AssertionError`.

## 5. Regime và truy xuất prior

Gaussian HMM bốn trạng thái được fit **một lần** trên VN-Index 2018–2022. Chuẩn hóa đặc trưng, ngưỡng và phép gán nhãn trạng thái cũng chỉ dùng tập này. Các đặc trưng dự kiến: log-return, độ biến động 20 phiên, khoảng cách MA20/MA50/MA200 và độ rộng thị trường. Nếu breadth chỉ tính từ bốn mã nghiên cứu, phải gọi rõ là **proxy của bốn mã**, không gọi là độ rộng toàn HOSE. Nến tại $t$ có thể dùng sau khi đóng cửa $t$; mọi nến sau $t$ bị cấm trong nhận diện regime. Trong kiểm định 2023–2024, áp dụng tham số HMM đã đóng băng, chỉ cung cấp chuỗi giá đến ngày truy vấn.

Triển khai Phase B dùng năm đặc trưng Close, chưa dùng breadth; [cấu hình và fallback đã chốt](week2/phase_b_regime_detector.md). Model đầy đủ trên 2018–2022 chỉ dùng từ ngày cuối train trở đi. Với nhãn regime point-in-time cho episode lịch sử trước ngày cuối train, mỗi model prefix phải fit một lần chỉ đến ngày quyết định (cùng cấu hình), và scaler/mapping/ngưỡng cũng chỉ học prefix đó. API từ chối `train_end_date > as_of_date`; không coi nhãn retrospective từ model toàn tập train là nhãn online. Việc cắt ngày và kiểm model cutoff không mở gate cơ sở giá chưa được xác minh của Phase A.

Retriever lọc theo `exit_date < current_as_of_date` trước mọi phép xếp hạng. Bayesian regime prior chọn tối đa $K=3$ chu kỳ đã đóng và có regime phù hợp; khi số bản ghi ít hơn $K$, dùng số hiện có và ghi lại số lượng, không kéo bản ghi tương lai vào để đủ mẫu. So sánh với Random, Recent và Similarity trên **cùng tập prior hợp lệ**. Seed của Random phải cố định và lưu trong kết quả. Cách đo similarity và mọi ngưỡng phải chốt trên tập 2018–2022. Prefix BRPP dài tối đa 600 ký tự cho $K=3$; prompt Decision Agent trong backtest dưới 6.500 ký tự sau khi ghép báo cáo.

## 6. Giao thức so sánh và đánh giá

Mỗi test point chạy `Indicator → Pattern → Trend` một lần. Deep copy nguyên state upstream sang năm nhánh: Original $K=0$, Random $K=3$, Recent $K=3$, Similarity $K=3$, Bayesian Regime $K=3$. Alpha/Sentiment/Decision được điều khiển theo cấu hình từng nhánh, nhưng cùng dữ liệu đầu vào, cùng mốc thời gian và cùng chi phí giao dịch. Lưu `symbol`, `as_of_date`, `regime_name`, `prior_episode_ids`, dự đoán, confidence, lý do fallback, prompt length và kết quả tài khoản theo nhánh. Mỗi điểm được checkpoint sau khi hoàn tất để chạy tiếp mà không thay seed hoặc lặp upstream.

Chỉ số chính: độ chính xác hướng, hit-rate LONG, lợi nhuận ròng tài khoản, Sharpe, Sortino và max drawdown. Brier Score chỉ báo cáo nếu confidence được ánh xạ thành xác suất bằng quy tắc đã chốt **trước** kiểm định; không tự tạo xác suất sau khi xem kết quả. McNemar dùng cho đúng/sai ghép cặp; Wilcoxon cho return ghép cặp; block bootstrap 95% CI xử lý phụ thuộc thời gian do chu kỳ chồng lấn. Phân tích riêng giai đoạn chuyển regime và các điểm có đồng thuận agent thấp. Báo cáo cả số quan sát hợp lệ, số loại bỏ và lý do, cùng khoảng tin cậy, không chỉ p-value.

## 7. Điều kiện chuyển sang thực nghiệm

Trước pilot hoặc benchmark: dữ liệu sạch có manifest; trạng thái giá thực thi và điều chỉnh theo thời điểm phải được xác minh để sinh nhãn; schema/quan hệ ngày được test; `compileall`, toàn bộ unit tests, E2E xác định và test leakage đều pass. Bộ CSV W1 đã đạt kiểm tra nến/lịch, nhưng **chưa mở gate tạo nhãn kinh tế**. Khi nguồn giá thực thi còn bất định, dừng tạo nhãn/memory thay vì xuất kết quả trông có vẻ hợp lệ.
