# Phase A — kiểm toán cơ sở giá và chốt lịch chu kỳ

**Ngày kiểm toán:** 2026-09-24. **Phạm vi:** `vnstock` 3.5.2, chỉ `VCI` và `KBS`; năm quyết định/tất toán không vượt 2022. Dữ liệu đầu vào là năm CSV và manifest của [kiểm toán W1](../week1/data_audit.md). Kết quả dưới đây là quy tắc và số lượng **chu kỳ ứng viên chưa có nhãn**, không phải Memory Bank.

## W2-01 — cơ sở giá thực thi

**Cập nhật 26/09/2026:** [Gate giá đã mở](phase_a_price_gate.md) bằng bộ giá thô VCI riêng, kiểm tra tám mẫu quyền trên VCI/KBS. Lịch 868 ứng viên giữ nguyên; 852 qua điều kiện giá, 16 loại vì quyền/tham chiếu. Phần kiểm toán 24/09 bên dưới được giữ làm lịch sử bằng chứng; CSV cổ phiếu W1 không trở thành giá thô sau khi mở gate.

`Quote.history` trong bản `vnstock` 3.5.2 của cả VCI và KBS chỉ trả OHLCV; chữ ký hàm không có tùy chọn giá thô/đã điều chỉnh hoặc lịch sử hệ số điều chỉnh. `get_all=True` của KBS trong khoảng kiểm tra vẫn chỉ trả sáu cột OHLCV. Hai nguồn gần trùng nhau, nhưng sự đồng thuận này không chứng minh đó là giá có thể khớp lệnh tại thời điểm lịch sử. [Tài liệu chính thức của Vnstock Data](https://www.vnstocks.com/docs/vnstock-data/du-lieu-giao-dich) nêu `Quote.history` là giá đã điều chỉnh để phân tích kỹ thuật; đó là **gói `vnstock_data` khác** với gói đang dùng, nên không lấy mô tả này làm xác nhận trực tiếp cho CSV W1.

Đối chiếu sự kiện qua `Company(symbol='FPT', source='VCI')._fetch_events(event_codes='DIV,ISS', from_date='20180101', to_date='20221231', page=0, size=500)` và `Quote.history` của cả hai nguồn:

| Sự kiện VCI | Ngày công bố / không hưởng quyền | CSV W1 gần sự kiện | Kiểm tra KBS cùng ngày | Kết luận |
| --- | --- | --- | --- | --- |
| FPT: cổ tức cổ phiếu 20% và tiền mặt 1.000 VND | 2022-06-02 / 2022-06-13 | Close 10/06 = 50,07; Open 13/06 = 48,50 (nghìn VND) | Close 10/06 = 50,080; Open 13/06 = 48,535 | Hai chuỗi tương đồng; không có giá khớp lệnh thô cùng ngày để xác định hệ số đã áp dụng. |
| FPT: cổ tức tiền mặt 1.000 VND | 2022-07-27 / 2022-08-24 | Close 23/08 = 47,95; Open 24/08 = 48,23 | Close 23/08 = 47,984; Open 24/08 = 48,263 | Hai nguồn tiếp tục gần nhau, chưa biết cách điều chỉnh hồi tố của từng provider. |

Giá 10/06 trước quyền và 13/06 sau quyền không thể tự suy ra giá thô chỉ từ hai nến: biến động thị trường và tác động quyền cùng tồn tại. Lịch sự kiện có `public_date`, `exright_date`, `value_per_share` và `exercise_ratio`, nhưng không phải chuỗi hệ số điều chỉnh hằng ngày; một số sự kiện còn có ngày công bố muộn hơn ngày quyền. Vì vậy không suy ngược tùy ý giá thực thi từ tỷ lệ quyền.

**Quyết định gate:** Chưa xác minh được Open(t+1)/Close(t+3) là giá thực thi point-in-time chưa điều chỉnh, cũng chưa có chuỗi hệ số PIT để dựng lại chúng. W2-01 đã hoàn tất việc kiểm toán và **gate giá vẫn bị chặn**. W2-11 đến W2-14 không được gán nhãn, tạo Memory Bank hay báo cáo P&L chính thức từ các CSV này. Đối với nhãn sau khi mở gate, lấy **giá khớp lệnh thô** Open của phiên vào và Close của phiên ra trên cùng đơn vị, gọi đúng `core.backtest_engine.compute_round_trip_net_return`, giữ phí 0,25% và trượt giá 0,10% ở cả hai chiều; `SHORT` giữ tiền mặt. Nếu provider chỉ cấp chuỗi điều chỉnh, cần chứng minh công thức/hệ số theo từng sự kiện và kiểm tra lại ngày quyền trước khi dùng. Tín hiệu tại ngày $t$ chỉ nhận dữ liệu/tin đã công bố `<= t`; sự kiện có `public_date > t` hoặc thiếu ngày công bố không được đưa vào snapshot tại $t$.

Việc cắt hàng CSV theo ngày chỉ bảo đảm **lịch thời gian**, chưa bảo đảm giá trong các hàng đó là ảnh chụp có sẵn ở ngày $t$: điều chỉnh hồi tố sau $t$ có thể sửa cả những hàng trước $t$. Các task regime có thể phát triển thuật toán và thử nghiệm pipeline trên CSV W1, nhưng chưa được tuyên bố là kết quả point-in-time đã xác thực nếu chưa giải quyết cơ sở giá này.

**Điều kiện mở gate:** Có giá thô VCI/KBS hoặc hệ số điều chỉnh theo phiên và bằng chứng cách áp dụng; kiểm tra tối thiểu một ngày chia cổ phiếu và một ngày cổ tức tiền mặt trên cả bốn mã có sự kiện; đối chiếu đúng giá vào/ra và quyền phát sinh trong chu kỳ; kiểm tra rằng dữ liệu đầu vào tại $t$ không thay đổi khi thêm thông tin công bố sau $t$. Nếu không lấy được từ hai provider đã cho phép, phải báo lại giới hạn nguồn trước khi sinh nhãn.

## W2-02 — lịch chu kỳ cố định

Gọi `d[i]` là phiên giao dịch thứ `i` của **cùng một mã**, chỉ lấy phần CSV từ 2018-01-01 đến 2022-12-31. Lịch của FPT, VNM, VCB, MWG trùng đúng lịch VNINDEX trong phần này. Mỗi mã có 1.251 nến. Chọn `end_idx = 600 + 3k` với `k = 0, 1, ...` và `end_idx + 2 < 1251`:

- `as_of_date = d[end_idx - 1]`: quyết định sau khi có nến ngày $t$; toàn bộ tín hiệu và regime chỉ đọc `d[0:end_idx]` và dữ liệu có ngày công bố `<= t`.
- `entry_date = d[end_idx]`: mua `Open(t+1)` khi nhãn được phép tính.
- `exit_date = d[end_idx + 2]`: bán `Close(t+3)` sau đúng ba phiên giao dịch.
- Bước 3 giữ các khoảng nắm giữ của cùng mã không chồng lấn; mốc quyết định kế tiếp có thể đúng ngày thoát trước đó **sau đóng cửa**. Khi truy xuất prior tại ngày đó, điều kiện vẫn là `exit_date < as_of_date`, nên chu kỳ vừa thoát cùng ngày chưa được thấy.

Giữ nguyên mức tối thiểu `ALPHA_HISTORY_CANDLES = 600` của `core/backtest_engine.py`; con số này cũng vượt warm-up MA200. Cửa sổ phân tích 45 nến của backtest lấy từ phần lịch sử đã cắt tại $t$. Với `lookahead=3`, `step=3`, lịch này khớp `build_walk_forward_end_indices(total=1251, n_tests=217, window_size=45, step=3, lookahead=3)`. Không dùng hàng 2023+ để đủ lịch sử hoặc để hoàn tất một chu kỳ bắt đầu cuối 2022.

| Mã | Ứng viên | Quyết định đầu / vào / ra | Quyết định cuối / vào / ra | Theo năm quyết định 2020 / 2021 / 2022 |
| --- | ---: | --- | --- | --- |
| FPT | 217 | 2020-06-01 / 06-02 / 06-04 | 2022-12-27 / 12-28 / 12-30 | 51 / 84 / 82 |
| VNM | 217 | như FPT | như FPT | 51 / 84 / 82 |
| VCB | 217 | như FPT | như FPT | 51 / 84 / 82 |
| MWG | 217 | như FPT | như FPT | 51 / 84 / 82 |
| **Tổng** | **868** | | | **204 / 336 / 328** |

**Giới hạn độ phủ:** CSV bắt đầu 2018-01-02, nên 600 nến khởi động đẩy điểm quyết định đầu tới 2020-06-01. Không có episode năm 2018–2019 trong lịch hiện tại. Đây là 868 **ứng viên**, chưa khẳng định có >300 bản ghi hợp lệ sau khi kiểm tra giá, tín hiệu, sự kiện và schema. Nếu luận văn cần episode ở cả năm 2018–2019, phải bổ sung ít nhất 600 phiên trước 2018 từ VCI/KBS, kiểm toán nguồn và chốt lại lịch trước khi sinh Memory Bank. Không giảm warm-up hay dùng dữ liệu tương lai để lấp khoảng trống.

## Cách tái lập kiểm tra

1. `py -3.13 -X utf8 scripts/prepare_historical_data.py --verify-only` xác thực checksum, nến và lịch của năm CSV.
2. Đọc phần 2018–2022, xác nhận 1.251 ngày giống nhau trên năm mã; tạo dãy `range(600, 1251 - 2, 3)` và xác nhận 217 mốc/mã, ngày đầu/cuối như bảng.
3. Với từng mốc xác nhận `as_of_date < entry_date < exit_date <= 2022-12-31`, 600 nến tiền quyết định, và `entry_date` của mốc kế tiếp sau `exit_date` của mốc trước trong cùng mã. Không tính lợi nhuận ở bước này.

**Kết quả kiểm tra hồi quy trên nhánh tài liệu:** `compileall` pass; `unittest discover` pass 109 test; `scripts/run_end_to_end_test.py` pass; `unittest discover -p 'test_*leakage.py'` pass 8 test. Các gate này kiểm tra hệ thống hiện có, không mở gate giá lịch sử.
