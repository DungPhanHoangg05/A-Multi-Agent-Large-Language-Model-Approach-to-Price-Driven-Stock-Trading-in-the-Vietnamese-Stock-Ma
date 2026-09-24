# Tuần 1 — đặc tả nghiên cứu và chuẩn bị dữ liệu

Kế hoạch này tách mục [Tuần 1](../plan.md#7-kế-hoạch-thực-hiện-chi-tiết-8-tuần-deliverables-matrix) thành các việc nhỏ. Mỗi ô chỉ được đánh dấu hoàn thành sau khi có đầu ra và bằng chứng kiểm tra. Cập nhật trạng thái ngay sau mỗi task trong bảng và ghi ngày, kết quả vào nhật ký bên dưới.

## Quy ước tiến độ

- `[x]`: hoàn thành và đã kiểm tra; `[ ]`: chưa hoàn thành.
- **Đang làm** và **Bị chặn** là trạng thái tạm thời, không tính là hoàn thành.
- Dữ liệu bị thiếu hoặc sai phải được truy nguyên; không nội suy nến hay sửa OHLC âm thầm.
- Các mốc 2018–2022 dùng huấn luyện và tạo memory; 2023–2024 là kiểm định ngoài mẫu; 2025 để dự phòng và khảo sát, không dùng để fit khi kiểm định 2023–2024.

## Checklist theo thứ tự phụ thuộc

| Mã | Task đủ nhỏ để kiểm tra | Đầu ra / điều kiện hoàn thành | Phụ thuộc | Trạng thái |
| --- | --- | --- | --- | --- |
| W1-01 | Đối chiếu kế hoạch với engine, loader, test hiện có và kiểm tra working tree | Ghi rõ hợp đồng $T+2.5$, điểm cắt thời gian, đường dẫn kế hoạch đã chuyển | — | [x] |
| W1-02 | Kiểm tra Python 3.13.5, `vnstock` và thử nguồn Daily EOD cho 5 mã | Ghi nguồn, phiên bản, số dòng và các lỗi nguồn phát hiện | W1-01 | [x] |
| W1-03 | Chốt quy ước dữ liệu: cột, đơn vị, khoảng ngày và tiêu chí chấp nhận | [Đặc tả phương pháp](../../methodology_spec.md) có phần hợp đồng dữ liệu | W1-01 | [x] |
| W1-04 | Viết script tải, chuẩn hóa, kiểm tra OHLCV và phiên giao dịch | `scripts/prepare_historical_data.py`; test nến trùng, giá sai, thiếu phiên đều pass | W1-02, W1-03 | [x] |
| W1-05 | Đối chiếu và xử lý 4 nến VN-Index sai OHLC từ nguồn VCI | Có nguồn KBS và nhật ký thay nguyên nến có thể tái lập; script tải chạy không lỗi | W1-04 | [x] |
| W1-06 | Tạo 5 CSV sạch 2018–2025 và manifest checksum | `data/historical/{VNINDEX,FPT,VNM,VCB,MWG}.csv` đủ phiên, không trùng/NaN/sai OHLC; `manifest.json` | W1-05 | [x] |
| W1-07 | Kiểm toán giá điều chỉnh/cổ tức/chia tách và tính tương thích PIT | Biên bản nguồn giá, rủi ro điều chỉnh tương lai, quy tắc dùng Open/Close cho nhãn | W1-06 | [x] |
| W1-08 | Định nghĩa schema `HistoricalTaskRecord` | JSON Schema và ví dụ hợp lệ; `exit_date < as_of_date` được yêu cầu khi truy xuất | W1-03 | [x] |
| W1-09 | Định nghĩa schema `MarketRegimeState` | JSON Schema với ngày, trạng thái, các đặc trưng và nguồn dữ liệu | W1-03 | [x] |
| W1-10 | Viết đặc tả phương pháp, thí nghiệm, leakage và tiêu chí đánh giá | `docs/methodology_spec.md`, đối chiếu đầy đủ các rào chắn P0 | W1-03, W1-08, W1-09 | [x] |
| W1-11 | Chạy compileall, toàn bộ unit test, E2E và test leakage | Cả 4 gate pass; ghi lệnh và kết quả vào nhật ký | W1-04, W1-10 | [x] |
| W1-12 | Rà soát đầu ra W1 và chốt checklist trong kế hoạch tổng | Chỉ đánh dấu toàn bộ W1 xong khi W1-06, W1-07, W1-11 hoàn thành | W1-05 đến W1-11 | [x] |

## Nhật ký tiến độ

### 2026-09-24

- **W1-01 hoàn thành**: `docs/plan.md` đã được chuyển sang `docs/plan/plan.md` trong working tree trước khi bắt đầu; giữ nguyên thay đổi đó. Engine dùng `compute_round_trip_net_return`, `point_in_time_df` và deep copy upstream cho các nhánh. `develop` đi trước `origin/develop` một commit, nên đã fetch và tạo nhánh riêng từ `develop` cục bộ.
- **W1-02 hoàn thành**: Python 3.13.5; `vnstock` 3.5.2. VCI trả 1.999 phiên cho từng mã từ 2018-01-02 đến 2025-12-31, không trùng ngày, không thiếu ô OHLCV, và bốn cổ phiếu không lệch lịch VN-Index. Kiểm tra sâu phát hiện **4 nến VN-Index sai quy tắc OHLC**: 2019-06-24, 2019-06-25, 2019-06-26, 2021-08-23. Chỉ kiểm tra số dòng là chưa đủ để tuyên bố dữ liệu sạch.
- **W1-03 hoàn thành**: quy ước cột `Datetime,Open,High,Low,Close,Volume`, lịch tham chiếu VN-Index, đơn vị giá và phân chia train/test ghi tại `docs/methodology_spec.md`.
- **W1-04 hoàn thành**: script chuẩn hóa từ VCI dừng với `ValueError` nếu gặp nến sai; 3 test kiểm tra đầu vào hợp lệ, ngày trùng/giá sai và phiên thiếu đều pass. Lần chạy dữ liệu thật dừng đúng tại VN-Index; chưa tạo CSV sạch.
- **W1-05 hoàn thành**: KBS cung cấp nến cùng ngày cho cả bốn lỗi VCI. Thay toàn bộ OHLCV của từng nến lỗi; lưu bản gốc VCI và bản thay KBS trong manifest. KBS được gọi với `floating=None`, VN-Index được đổi từ nghìn điểm sang điểm.
- **W1-08, W1-09, W1-10 hoàn thành**: hai JSON Schema và đặc tả phương pháp đã được tạo. Quy tắc `exit_date < as_of_date` phải được kiểm tra ở tầng ứng dụng vì JSON Schema chỉ xác nhận từng trường.
- Đã cập nhật hai ô schema và đặc tả trong `docs/plan/plan.md`; ô dữ liệu vẫn để mở.
- **W1-11 hoàn thành**: `py -3.13 -m compileall agents core data_manager scripts tests utils` pass; `py -3.13 -X utf8 -m unittest discover -s tests -v` pass **105/105**; `py -3.13 -X utf8 scripts/run_end_to_end_test.py` pass; `py -3.13 -X utf8 -m unittest discover -s tests -p "test_*leakage.py" -v` pass **8/8**. Hai schema parse JSON thành công. Gate này xác nhận hồi quy mã hiện có, **không** thay thế việc xác minh dữ liệu thật tại W1-05 đến W1-07.

### Bản ghi VN-Index cần đối chiếu

| Ngày | Open VCI | High VCI | Low VCI | Close VCI | Vấn đề |
| --- | ---: | ---: | ---: | ---: | --- |
| 2019-06-24 | 949,48 | 967,11 | 962,63 | 962,85 | Open < Low |
| 2019-06-25 | 949,48 | 963,23 | 960,06 | 960,13 | Open < Low |
| 2019-06-26 | 949,48 | 962,70 | 958,49 | 959,13 | Open < Low |
| 2021-08-23 | 1.329,43 | 1.326,07 | 1.298,86 | 1.298,86 | Open > High |

Các số trên là dữ liệu thô quan sát ngày 2026-09-24 từ VCI qua `vnstock` 3.5.2, **không phải giá đã được xác thực**. Giữ nguyên để so sánh với nguồn đối chiếu ở W1-05.

- **W1-06 hoàn thành**: năm CSV và manifest đã được tạo tại `data/historical/`. Mỗi mã có 1.999 phiên, 2018-01-02 đến 2025-12-31, không thiếu phiên so với VN-Index. `--verify-only` kiểm lại checksum và bốn nến đã thay nguồn thành công.
- **W1-07 hoàn thành phần kiểm toán**: [biên bản dữ liệu](data_audit.md) ghi rủi ro giá điều chỉnh ngược và kết luận **chưa dùng CSV để sinh nhãn kinh tế/P&L chính thức**. Việc xác minh giá thực thi hoặc hệ số điều chỉnh là gate đầu vào tuần 2, không được bỏ qua chỉ vì W1 đã có CSV sạch.
- **W1-11 kiểm thử lại và W1-12 hoàn thành**: `compileall` pass; toàn bộ **109/109 unit tests** pass; E2E xác định pass; **8/8 test leakage** pass. Checklist dữ liệu trong `docs/plan/plan.md` đã cập nhật. W1 có đủ đầu ra tài liệu, schema, CSV và manifest; giới hạn dùng giá lịch sử đã được ghi thành gate rõ ràng cho tuần 2.

## Bước kế tiếp

Trước khi tạo Memory Bank ở tuần 2, xác minh giá thực thi hoặc hệ số điều chỉnh theo từng thời điểm để bảo vệ nhãn kinh tế T+2.5. CSV W1 chỉ dùng cho đặc trưng kỹ thuật cho tới khi gate này đạt yêu cầu.
