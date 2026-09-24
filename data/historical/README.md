# Dữ liệu Daily EOD cho nghiên cứu

Năm CSV trong thư mục này được tạo bằng:

```powershell
py -3.13 -X utf8 scripts/prepare_historical_data.py
py -3.13 -X utf8 scripts/prepare_historical_data.py --verify-only
```

`manifest.json` lưu phiên bản `vnstock`, thời điểm tải, checksum SHA-256 và bốn nến VN-Index được thay từ VCI sang KBS. Quy ước cột: `Datetime,Open,High,Low,Close,Volume`; giá cổ phiếu theo nghìn VND, VN-Index theo điểm.

Xem [biên bản kiểm toán](../../docs/plan/week1/data_audit.md) trước khi dùng. Bộ CSV đã kiểm tra nến và lịch phiên; trạng thái giá điều chỉnh lịch sử **chưa đủ để xác nhận nhãn kinh tế T+2.5**.
