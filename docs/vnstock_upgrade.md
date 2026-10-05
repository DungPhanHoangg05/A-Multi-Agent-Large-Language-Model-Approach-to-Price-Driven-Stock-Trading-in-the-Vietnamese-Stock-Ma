# Biên bản nâng cấp Vnstock

## Hoàn thành ngày 26/09/2026

- [x] Trong runtime Python 3.13.5, nâng `vnstock 3.5.2` lên `4.0.9`, `vnai 2.4.8` lên `2.6.2`. Dependency liên quan `vnstock_ezchart` được pip nâng từ `0.0.3` lên `1.0.2`.
- [x] Ghim `vnstock==4.0.9` và `vnai==2.6.2` trong `requirements.txt`, thêm kho gói chính thức. [Lịch sử phiên bản Vnstock](https://vnstocks.com/docs/tai-lieu/lich-su-phien-ban) thông báo thay đổi cách phân phối từ 25/09/2026; kiểm tra trực tiếp kho gói khi nâng cấp xác nhận bản mới nhất là `4.0.9`.
- [x] Giữ hai nguồn VCI/KBS, kiểm tra tương thích `Quote`, `Listing` và `Company`.
- [x] Sửa đơn vị VN-Index: KBS ở bản mới trả chỉ số theo điểm, nên bỏ phép nhân 1.000 dành cho bản cũ trong `core/realtime_loader.py`. Giá cổ phiếu tiếp tục theo nghìn VND. Test hồi quy kiểm tra cả hai nguồn giữ nguyên giá chỉ số.
- [x] Hoàn tất bốn gate trước tích hợp.

## Cài đặt

```powershell
py -3.13 -m pip install -r requirements.txt
```

File requirements đã chứa `--extra-index-url https://vnstocks.com/api/simple`. Nếu chỉ nâng hai gói trong môi trường hiện có, dùng:

```powershell
py -3.13 -m pip install --upgrade --extra-index-url https://vnstocks.com/api/simple vnstock==4.0.9 vnai==2.6.2
```

## Bằng chứng kiểm tra

| Kiểm tra | Kết quả |
| --- | --- |
| `py -3.13 -m pip check` | Không có dependency hỏng |
| API lịch sử FPT của VCI/KBS | Có OHLCV, giá theo nghìn VND |
| API VN-Index của VCI/KBS | Cùng Close ngày 25/09/2026: **1.785,11 điểm**; không nhân thêm 1.000 |
| API danh mục của VCI/KBS | Trả danh sách không rỗng, có FPT |
| API hồ sơ FPT của VCI/KBS | Mỗi nguồn trả một bản ghi |
| `py -3.13 -X utf8 scripts/prepare_historical_data.py --verify-only` | 5 CSV và 4 dòng sửa nguồn hợp lệ |
| `py -3.13 -X utf8 scripts/train_regime_detector.py --verify-only` | Artifact/hash hợp lệ: 1.251 nến train, 1.052 hàng đặc trưng |
| `py -3.13 -m compileall agents core data_manager scripts tests utils` | Pass |
| `py -3.13 -X utf8 -m unittest discover -s tests -v` | 135 test pass |
| `py -3.13 scripts/run_end_to_end_test.py` | Toàn bộ kiểm tra pipeline pass |
| `py -3.13 -X utf8 -m unittest discover -s tests -p 'test_*leakage.py' -v` | 16 test pass |

## Phạm vi dữ liệu

Manifest dữ liệu lịch sử vẫn ghi `vnstock 3.5.2`, đúng phiên bản đã tạo snapshot đó. Không tải lại CSV hoặc fit lại HMM trong task này; các phiên bản dependency số học của artifact được giữ nguyên.

Tại thời điểm commit nâng cấp, gate giá Phase A còn bị chặn: OHLCV tải được và đúng đơn vị chưa đủ xác nhận cơ sở giá thực thi. Task tiếp theo đã [mở gate cho bộ giá thô riêng 2018–2022](plan/week2/phase_a_price_gate.md); kết quả này không thay provenance của snapshot trước nâng cấp.
