# Gate giá Phase A — đã mở cho tập Memory Bank

**Ngày kiểm toán giá:** 26/09/2026. **Hoàn tất các gate tích hợp:** 27/09/2026. **Phạm vi PASS:** giá thô FPT, VNM, VCB, MWG giai đoạn 2018–2022 và các chu kỳ ba phiên không vắt qua quyền doanh nghiệp. Runtime `vnstock 4.0.9`; chỉ dùng VCI/KBS.

## 1. Bằng chứng mới giải quyết điểm chặn

API công khai của Vietcap `https://iq.vietcap.com.vn/api/iq-insight-service/v1/company/{symbol}/price-history` trả **đồng thời**:

- Giá thô: `openPrice`, `highestPrice`, `lowestPrice`, `closePrice`, `referencePrice`, đơn vị VND.
- Giá điều chỉnh riêng: `openPriceAdjusted`, `highestPriceAdjusted`, `lowestPriceAdjusted`, `closePriceAdjusted`.
- `totalMatchVolume`, `tradingDate`, `ticker`, `matchPrice` và metadata phân trang.

Endpoint được xác định từ bundle công khai [Vietcap IQ](https://trading.vietcap.com.vn/vietcap-iq/main.js?v=71436c0503d0759b24742616d3cf3ff67c7d49d1), có đường dẫn `/company/{ticker}/price-history` và các tên trường `...Adjusted`. Đây là adapter REST bổ sung cho **cùng provider VCI** mà module `vnstock.explorer.vci.company` đang dùng; headers và API đối chiếu `Quote` lấy từ vnstock cộng đồng. Không yêu cầu gói tài trợ hoặc nguồn dữ liệu thứ ba. [Tài liệu giao dịch Vnstock](https://www.vnstocks.com/docs/vnstock-data/du-lieu-giao-dich) phân biệt lịch sử biểu đồ với thống kê giao dịch; nội dung này dùng để định hướng kiểm tra, kết luận gate dựa trên response thực tế đã lưu.

`core/execution_prices.py` chọn đúng trường thô, chia 1.000 **một lần** sang nghìn VND, kiểm tra OHLC/lịch/khối lượng. Không suy ngược giá thô từ CSV điều chỉnh hoặc từ tỷ lệ cổ tức. `matchPrice` là trường riêng, có thể khác `closePrice`; không dùng nó thay Close.

## 2. Artifact đã chốt

Thư mục [data/execution_prices](../../data/execution_prices/) chứa bốn CSV, bốn file `*.evidence.json.gz`, bốn file `*.events.json` và [manifest](../../data/execution_prices/manifest.json).

- Mỗi mã có **1.251 phiên**, tổng **5.004 nến**, lịch khớp VN-Index W1 trong 2018–2022.
- Evidence nén lưu các trường giá thô/điều chỉnh đã chọn từ response; receipt ghi URL, thời điểm tải, checksum response gốc, page/size/số dòng. CSV và evidence/sự kiện đều có SHA-256 trong manifest.
- API áp trần **1.000 dòng/trang**: tải hai trang mỗi mã, kiểm tổng 1.251 dòng. Không coi trang đầu là toàn bộ lịch sử.
- Sự kiện VCI `DIV,ISS,AIS,MA,MOVE,NLIS,OTHE,RETU,SUSP` được tải đầy đủ theo trang trong 2017–2023 để kiểm toán quyền sát biên; ledger này **không được đưa vào tín hiệu agent**.
- Cả bốn mã có hai bản ghi không có khớp lệnh, 23–24/01/2018; riêng VCB có năm ngày `matchPrice` khác Close. Manifest ghi rõ; không tự sửa nến hoặc điền giá. Mọi chu kỳ có phiên Volume bằng 0 trong khoảng nắm giữ đều bị từ chối. Không có trường hợp này trong lịch ứng viên bắt đầu tháng 06/2020.

## 3. Đối chiếu tám mẫu ngày quyền

Giá trong bảng là **VND/cổ phiếu** từ trường thô của VCI. `Close trước` là Close phiên liền trước ngày quyền. Mỗi mẫu đã đối chiếu OHLC biểu đồ của cả VCI/KBS và request giá thô kết thúc trước ngày quyền.

| Mã | Loại quyền | Ngày quyền | Close trước | Open ngày quyền | Close ngày quyền | Sai lệch Reference với công thức quyền |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| FPT | Cổ phiếu 20% và tiền mặt 1.000 | 2022-06-13 | 110.000 | 88.000 | 86.200 | 4,67 VND |
| FPT | Tiền mặt 1.000 | 2022-08-24 | 87.000 | 86.500 | 86.200 | 1 VND |
| VNM | Cổ phiếu và tiền mặt | 2020-09-29 | 128.300 | 110.000 | 109.200 | 6 VND |
| VNM | Tiền mặt 1.400 | 2022-12-22 | 79.700 | 79.300 | 77.000 | 3 VND |
| VCB | Cổ phiếu 27,6% và tiền mặt 1.200 | 2021-12-22 | 98.900 | 77.000 | 76.900 | 0,60 VND |
| VCB | Tiền mặt | 2020-12-21 | 98.900 | 98.900 | 98.900 | 1 VND |
| MWG | Cổ phiếu 100% | 2022-06-16 | 147.700 | 79.000 | 79.000 | 50 VND |
| MWG | Tiền mặt 1.000 | 2022-06-07 | 154.700 | 154.000 | 153.000 | 6 VND |

Kiểm tra Reference dùng `(Close trước - tổng cổ tức tiền mặt) / (1 + tổng tỷ lệ cổ phiếu)`, sai số tối đa một bước giá 100 VND cho các mẫu này. Công thức chỉ **đối chiếu ngày quyền**, không tái dựng hoặc sửa giá thực thi. Response gốc và tỷ lệ/tổng tiền từng mẫu nằm trong manifest. Hai nguồn biểu đồ có tỷ lệ thấp hơn 1 so với giá thô; OHLC trong cùng phiên cùng cơ sở tỷ lệ, xác nhận không được dùng trực tiếp làm giá khớp lệnh.

## 4. Quyền trong chu kỳ và phạm vi mở gate

Engine giữ nguyên mua Open(t+1), bán Close(t+3), phí 0,25% và trượt giá 0,10% hai chiều; SHORT giữ tiền mặt. Engine hiện chưa tính cổ tức, cổ phiếu nhận thêm hoặc quyền mua. Vì vậy gate chấp nhận **chỉ các chu kỳ không phát sinh quyền trong `(entry_date, exit_date]`**. Mua ngay ngày không hưởng quyền không tạo quyền cho người mua mới.

Ngày chặn là hợp của ngày `exrightDate` trong ledger và mọi ngày Reference khác Close phiên trước, để không bỏ sót thay đổi tham chiếu khi ledger thiếu sự kiện. Cả các sự kiện không rõ tác động cũng bị chặn bảo thủ. Khi gọi `execution_prices_for_cycle`, chu kỳ sai lịch, không có khớp hoặc vắt qua ngày chặn ném `ValueError`.

| Mã | Ứng viên ban đầu | Qua gate giá | Loại vì quyền/tham chiếu |
| --- | ---: | ---: | ---: |
| FPT | 217 | 211 | 6 |
| VNM | 217 | 213 | 4 |
| VCB | 217 | 215 | 2 |
| MWG | 217 | 213 | 4 |
| **Tổng** | **868** | **852** | **16** |

Giữ nguyên lịch, ID và mốc của 868 ứng viên; không dồn lịch hoặc chọn lại mốc để bù 16 trường hợp loại. Danh sách loại nằm trong manifest. Đây là điều kiện chất lượng **nhãn sau tất toán**, không là tín hiệu hay quyết định giao dịch biết trước tại t. Phase C phải báo số loại và áp cùng phạm vi cho các đối chứng; 852 chưa phải số Memory Bank hợp lệ vì còn các gate tín hiệu/schema/regime.

## 5. Point-in-time và giới hạn bằng chứng

`raw_point_in_time_snapshot` cắt hàng `<= t` trước kiểm tra giá, chỉ trả sáu cột OHLCV thô. Các cột `...Adjusted` và ledger toàn kỳ không đi vào snapshot. Khi thêm nến/quyền/điều chỉnh sau t, snapshot đã chọn không thay đổi. Kiểm tra API trên tám mẫu xác nhận OHLC thô ở request kết thúc trước ngày quyền giống cùng hàng trong request kéo dài qua quyền.

CSV W1 vẫn là snapshot đã điều chỉnh để giữ provenance; **Phase C phải dùng bộ giá thô mới cho tín hiệu cổ phiếu và entry/exit**, qua `load_verified_execution_data`, không ghép tín hiệu từ CSV điều chỉnh hồi tố với giá thô để rồi tuyên bố toàn bộ pipeline là PIT. Hàm nạp kiểm gate, hash và đối chiếu CSV với evidence thô.

Bằng chứng hiện xác nhận trường giá chưa điều chỉnh, công thức/ngày quyền, tính nhất quán prefix và thuật toán cutoff. Đây là dữ liệu lịch sử tải ngày 26/09/2026, không phải kho vintage chụp mỗi ngày từ 2018; không khẳng định đã loại mọi sửa sai lịch sử của provider. Gate chỉ mở tập 2018–2022 đã kiểm toán. Dữ liệu giá thô cho kiểm định 2023–2024 cần kiểm toán riêng trước benchmark. Artifact HMM/VN-Index và CSV W1 được giữ nguyên.

## 6. Tái lập

```powershell
# Xác minh bộ đã chốt hoàn toàn offline
py -3.13 -X utf8 scripts/verify_execution_price_gate.py --verify-only
py -3.13 -X utf8 -m unittest discover -s tests -p 'test_execution_price*.py' -v

# Thu thập một snapshot mới vào thư mục riêng, không ghi đè bản đã chốt
py -3.13 -X utf8 scripts/verify_execution_price_gate.py --download --output-dir data/execution_prices_refresh
```

Gate giá được tái tính từ CSV, evidence, sự kiện, lịch và tám mẫu; `PENDING`, thiếu mã, checksum sai, CSV sửa dù đã đổi hash, thiếu trang hoặc thiếu mẫu đều bị từ chối. Lỗi tải dừng với manifest PENDING; kết quả từng mã đã hoàn tất được checkpoint. Không tạo bất kỳ `net_return_pct`, nhãn hay Memory Bank nào trong task này.

## 7. Kết quả bốn gate trước tích hợp

| Lệnh | Kết quả |
| --- | --- |
| `py -3.13 -m compileall agents core data_manager scripts tests utils` | PASS |
| `py -3.13 -X utf8 -m unittest discover -s tests -v` | **154 test PASS** (19 test giá/cutoff/provenance mới) |
| `py -3.13 scripts/run_end_to_end_test.py` | Toàn bộ pipeline PASS |
| `py -3.13 -X utf8 -m unittest discover -s tests -p 'test_*leakage.py' -v` | **23 test PASS** |

Tái xác minh gate giá offline ngày 27/09 vẫn PASS 852/868 chu kỳ. `scripts/train_regime_detector.py --verify-only` xác nhận artifact HMM không đổi, hash `dadb02d1c14a96d3d4b9ac906518afe45b5a67d77ba990b87e0452fec30a8be6`. Không chỉnh engine P&L, graph upstream hoặc artifact HMM trong task này.
