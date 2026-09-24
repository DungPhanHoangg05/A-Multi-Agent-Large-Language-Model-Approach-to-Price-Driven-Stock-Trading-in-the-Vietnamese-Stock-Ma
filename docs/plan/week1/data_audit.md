# Biên bản dữ liệu EOD 2018–2025

**Ngày kiểm tra:** 2026-09-24

**Nguồn được phép:** `vnstock` 3.5.2 với provider `VCI` và `KBS`.

## Kết quả nạp và làm sạch

`scripts/prepare_historical_data.py` dùng VCI làm nguồn chính. Khi nến VCI vi phạm quy tắc `Low <= Open, Close <= High`, script lấy **toàn bộ nến** cùng ngày từ KBS, kiểm tra lại quy tắc rồi ghi bản gốc và bản thay vào `data/historical/manifest.json`. KBS trả VN-Index theo nghìn điểm; loader đổi về điểm trước khi đối chiếu. KBS được gọi với `floating=None` để giữ độ chính xác gốc.

| Mã | Số phiên | Khoảng ngày | Trùng/ngày sai/NaN | Phiên thiếu so với VN-Index | Nến thay bằng KBS |
| --- | ---: | --- | ---: | ---: | ---: |
| VNINDEX | 1.999 | 2018-01-02–2025-12-31 | 0 | — | 4 |
| FPT | 1.999 | 2018-01-02–2025-12-31 | 0 | 0 | 0 |
| VNM | 1.999 | 2018-01-02–2025-12-31 | 0 | 0 | 0 |
| VCB | 1.999 | 2018-01-02–2025-12-31 | 0 | 0 | 0 |
| MWG | 1.999 | 2018-01-02–2025-12-31 | 0 | 0 | 0 |

Bốn ngày thay nguồn: `2019-06-24`, `2019-06-25`, `2019-06-26`, `2021-08-23`. Tất cả 5 CSV pass kiểm tra OHLC, giá dương, khối lượng không âm và lịch phiên. Lệnh `py -3.13 -X utf8 scripts/prepare_historical_data.py --verify-only` đọc lại CSV, kiểm tra checksum SHA-256, số dòng, lịch và đúng giá KBS trong manifest; kết quả: **5 CSV, 4 dòng thay nguồn hợp lệ**. Không có bước nội suy hoặc clipping giá.

Đối chiếu thêm trên 1.997 ngày chung của từng cổ phiếu, Close KBS so với VCI sai khác dưới 1% ở cả FPT, VNM, VCB, MWG. Đây là phép kiểm tra nhất quán tương đối giữa hai provider, **không chứng minh** rằng giá là giá khớp lệnh chưa điều chỉnh tại thời điểm lịch sử.

## Kiểm toán giá điều chỉnh và point-in-time

[Tài liệu Quote của Vnstock](https://www.vnstocks.com/docs/vnstock-data/du-lieu-giao-dich) mô tả lịch sử OHLCV của sản phẩm `vnstock_data` là giá đã điều chỉnh để phân tích kỹ thuật; đây là tài liệu của **sản phẩm khác** với gói `vnstock` 3.5.2 đang cài. Gói hiện dùng không công bố rõ trong kết quả `Quote.history` liệu từng Open/Close là giá giao dịch thô hay đã điều chỉnh theo sự kiện doanh nghiệp. Hai provider cho chuỗi cổ phiếu rất gần nhau, nhưng sự trùng khớp đó không xác nhận chế độ điều chỉnh hay snapshot as-of trong quá khứ.

**Quy tắc sử dụng:** bộ CSV W1 là dữ liệu OHLCV đã qua kiểm tra hình dạng và lịch, phù hợp để phát triển đặc trưng kỹ thuật và kiểm thử pipeline point-in-time theo ngày. **Chưa dùng các giá Open/Close này để phát hành nhãn kinh tế T+2.5 hoặc báo cáo P&L chính thức** cho đến khi đối chiếu được giá thực thi chưa điều chỉnh hoặc chuỗi hệ số điều chỉnh theo từng ngày sự kiện. Khi có nguồn giá thực thi, nhãn phải đi qua `compute_round_trip_net_return` của engine. Ngày `as_of_date` vẫn cắt mọi dữ liệu đầu vào; snapshot tải năm 2026 không chứng minh bản thân giá lịch sử là snapshot đã có tại năm 2018–2024.

Điều kiện này là gate đầu vào của việc tạo Memory Bank ở tuần 2. Không thể suy ra tính không rò rỉ của đặc trưng chỉ từ việc dữ liệu CSV không chứa ngày sau `as_of_date`: phép điều chỉnh ngược do sự kiện doanh nghiệp xảy ra sau `as_of_date` cũng cần được kiểm tra. Việc đối chiếu nguồn giá thực thi nằm ngoài phạm vi hai nguồn OHLCV mà người dùng đã giới hạn cho loader; nếu VCI/KBS không cung cấp giá thô hoặc hệ số lịch sử, không được tự coi giá điều chỉnh là giá thực thi.
