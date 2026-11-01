# Audit R1 — kết quả legacy

Đây là đối soát khám phá từ outputs đã lưu, chưa phải thực nghiệm confirmatory hoặc đóng R1.

Có 9 mã, 180 điểm và 53 ngày quyết định phân biệt. Các mã không được coi là những replication thị trường độc lập.

Target UP: LONG có lãi sau phí từ entry_open đến exit_close; DOWN gồm hòa vốn và lỗ. SHORT giữ CASH. Base reports là pred_no_alpha lịch sử, bỏ cả alpha và sentiment.

## Phân loại pooled trên common support

| Variant | N | TP/FN/TN/FP | Accuracy % | BA % | MCC | Macro-F1 % | LONG % |
|---|---:|---|---:|---:|---:|---:|---:|
| full | 180 | 16/40/101/23 | 65.00 | 55.01 | 0.113 | 54.96 | 21.67 |
| base_reports_legacy | 180 | 15/41/77/47 | 51.11 | 44.44 | -0.108 | 44.53 | 34.44 |
| constant_down_cash | 180 | 0/56/124/0 | 68.89 | 50.00 | NA | 40.79 | 0.00 |
| constant_up_cycles | 180 | 56/0/0/124 | 31.11 | 50.00 | NA | 23.73 | 100.00 |

Per-class support/precision/recall/F1 và support riêng nằm trong classification.csv/report.json. Tỷ lệ JSON/CSV ở thang 0–1; bảng Markdown chuyển sang %. Undefined là null/NA, không ép về 0. macro_over_symbols là trung bình đều theo mã, khác pooled; chỉ có mean khi mọi mã xác định.

## Tài khoản theo từng mã

| Mã | Variant | LONG cycles | Số lệnh | Net return % | Cycle-end drawdown % |
|---|---|---:|---:|---:|---:|
| BHN | full | 4 | 8 | -4.20 | 4.80 |
| BHN | base_reports_legacy | 10 | 20 | -5.76 | 8.31 |
| BHN | constant_down_cash | 0 | 0 | 0.00 | 0.00 |
| BHN | constant_up_cycles | 20 | 40 | -5.15 | 9.75 |
| CMG | full | 1 | 2 | -2.66 | 2.66 |
| CMG | base_reports_legacy | 2 | 4 | -5.60 | 5.60 |
| CMG | constant_down_cash | 0 | 0 | 0.00 | 0.00 |
| CMG | constant_up_cycles | 20 | 40 | -30.43 | 30.43 |
| FPT | full | 4 | 8 | -1.56 | 6.30 |
| FPT | base_reports_legacy | 8 | 16 | -10.37 | 10.37 |
| FPT | constant_down_cash | 0 | 0 | 0.00 | 0.00 |
| FPT | constant_up_cycles | 20 | 40 | -13.09 | 18.93 |
| HVN | full | 3 | 6 | 2.89 | 5.27 |
| HVN | base_reports_legacy | 9 | 18 | -15.64 | 20.06 |
| HVN | constant_down_cash | 0 | 0 | 0.00 | 0.00 |
| HVN | constant_up_cycles | 20 | 40 | -28.82 | 34.66 |
| MBB | full | 6 | 12 | 5.21 | 3.50 |
| MBB | base_reports_legacy | 9 | 18 | -7.78 | 9.89 |
| MBB | constant_down_cash | 0 | 0 | 0.00 | 0.00 |
| MBB | constant_up_cycles | 20 | 40 | -16.28 | 17.18 |
| MWG | full | 7 | 14 | 0.39 | 1.92 |
| MWG | base_reports_legacy | 9 | 18 | -6.42 | 8.17 |
| MWG | constant_down_cash | 0 | 0 | 0.00 | 0.00 |
| MWG | constant_up_cycles | 20 | 40 | -15.64 | 19.42 |
| VCB | full | 4 | 8 | -8.34 | 8.92 |
| VCB | base_reports_legacy | 5 | 10 | -10.49 | 10.49 |
| VCB | constant_down_cash | 0 | 0 | 0.00 | 0.00 |
| VCB | constant_up_cycles | 20 | 40 | -19.56 | 20.89 |
| VJC | full | 3 | 6 | -6.05 | 6.05 |
| VJC | base_reports_legacy | 3 | 6 | -6.26 | 6.26 |
| VJC | constant_down_cash | 0 | 0 | 0.00 | 0.00 |
| VJC | constant_up_cycles | 20 | 40 | -21.55 | 21.55 |
| VNM | full | 7 | 14 | -0.85 | 3.40 |
| VNM | base_reports_legacy | 7 | 14 | -7.51 | 7.51 |
| VNM | constant_down_cash | 0 | 0 | 0.00 | 0.00 |
| VNM | constant_up_cycles | 20 | 40 | -8.67 | 9.48 |

Trung bình return các tài khoản độc lập (không phải một portfolio chung):

- full: -1.68%.
- base_reports_legacy: -8.43%.
- constant_down_cash: +0.00%.
- constant_up_cycles: -17.69%.

## Giả định và giới hạn

- Return chính được tái tính từ giá chuẩn chưa làm tròn; trung bình return đã làm tròn trong summary legacy nằm riêng ở mean_stored_rounded_account_return_pct và có thể làm tròn khác ở chữ số cuối. Không sửa summary gốc để khớp số mới.
- Phí mỗi chiều 0.0025; trượt giá mỗi chiều 0.001. Đây là giả định replay công khai, không chứng nhận cấu hình request lịch sử.
- Fractional shares, toàn bộ vốn mỗi LONG, bán cuối chu kỳ, tiền tái dùng ngay; chưa xử lý settlement, lot size, thuế riêng, corporate actions hoặc khả năng khớp lệnh.
- Always-LONG cycles đóng/mở và trả phí mỗi chu kỳ; không phải buy-and-hold. CASH ở mức lãi suất 0 và không giao dịch.
- LONG cycle fraction và traded notional/initial capital có định nghĩa riêng; daily exposure/turnover/drawdown là NA vì thiếu daily snapshot và ledger.
- Không fit majority trên nhãn test. Chưa có frozen train/validation features để chạy majority, momentum, hai logistic, factor-only và exposure-matched control hợp lệ.
- api_error_flag_counts theo mã được giữ riêng; common support định nghĩa theo prediction parse hợp lệ, không tự bỏ prediction hợp lệ chỉ vì có cờ error. Failure policy confirmatory chưa freeze.
- Group metadata còn thiếu: fold, regime, repeat_id. Không suy regime/fold/repeat từ outcome hoặc tên file.
- Có hash không chứng minh đây là snapshot submission chính thức; không dùng audit này để suy significance hoặc attribution alpha.
- Sai lệch cờ correct/return lưu so với tái tính: 0; xem legacy_discrepancies trong report.json.
