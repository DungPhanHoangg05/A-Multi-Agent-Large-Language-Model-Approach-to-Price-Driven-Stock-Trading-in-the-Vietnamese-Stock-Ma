# Phase C — phát hành và kiểm toán Historical Memory Bank

**Ngày chốt: 04/10/2026. W2-13 và W2-14 hoàn thành.** Toàn bộ 852 điểm hợp lệ
đã được sinh bằng pipeline hiện có; bước phát hành và QA không gọi LLM, không
fit lại HMM và không sinh thêm episode. W2-15 đến W2-17 đã được chốt trong
[biên bản Phase D](phase_d_week_close.md).

## Đầu ra chính thức

| File | Nội dung |
| --- | --- |
| `data_manager/regime_memory_store.json` | 852 record đúng schema W1, nhãn dùng hàm P&L của engine |
| `data_manager/regime_memory_store.manifest.json` | Signature run, checksum kho, số lượng/độ phủ, model, archive tin và bằng chứng bộ đọc |
| `data_manager/regime_memory_store.parse_compat.json` | Ba báo cáo Trend có tên trường viết tắt; hash báo cáo, hướng và mã bộ đọc |
| [memory_bank_audit.json](memory_bank_audit.json) | QA có thể tái lập, trạng thái PASS, thống kê và giới hạn dữ liệu |

Hash SHA-256 của kho:
`09b48c6192a092b562173e8b3b7eceb44025c6e02454093e34214a730a460949`.
Signature run:
`e2f04ef08863e53570589c3a443be16759a7c9e3474074dfa284afcb816f173c`.

Các JSON phát hành được giữ nguyên byte qua Git bằng `.gitattributes`, tránh
đổi xuống dòng làm sai checksum. Kho, manifest, biên bản bộ đọc và QA được
theo dõi trong Git; staging và bản ZIP được bỏ qua bằng `.gitignore`.

## W2-13 — phát hành

`scripts/publish_historical_memory.py --require-complete` xác minh toàn bộ
journal bằng runner gốc, yêu cầu hơn 300 record, đủ bốn mã và không còn điểm
chưa sinh. `HistoricalMemory` xác minh lại schema, ID, giá thực thi, lịch
ba phiên, P&L và không chồng lấn trước khi ghi kho. Kho đích khác nội dung
bị từ chối ghi đè. Các bản ghi thử nghiệm chỉ nằm trong thư mục tạm của test.

Archive tin được đóng băng tại `outputs/historical_memory_run/inputs/news/`;
mã bộ đọc Trend đã dùng được lưu nguyên byte tại `inputs/compat/`, so SHA-256
với biên bản trước khi phát hành. Báo cáo gốc, signature và provenance của
852 episode giữ nguyên. API key không có trong artifact phát hành.

## W2-14 — kết quả kiểm toán

| Mã | 2020 | 2021 | 2022 | Tổng |
| --- | ---: | ---: | ---: | ---: |
| FPT | 51 | 81 | 79 | 211 |
| MWG | 50 | 82 | 81 | 213 |
| VCB | 50 | 83 | 82 | 215 |
| VNM | 50 | 83 | 80 | 213 |
| **Tổng** | **201** | **329** | **322** | **852** |

| Regime | Episode |
| --- | ---: |
| BULL | 337 |
| BEAR | 191 |
| CHOPPY | 248 |
| CONSOLIDATION | 76 |

QA đối chiếu đúng toàn bộ lịch 852 điểm hợp lệ trong 868 ứng viên; 16 điểm
loại vì quyền/tham chiếu được giữ theo gate giá Phase A. Kiểm schema W1 bằng
validator ứng dụng, kiểu JSON gốc, ID duy nhất, thứ tự/lịch ngày và không
chồng lấn. Mọi record được đối chiếu giá VCI đã xác minh với
`compute_round_trip_net_return`: LONG mua Open(t+1), bán Close(t+3), phí
0,25% và trượt giá 0,10% mỗi chiều; SHORT giữ tiền mặt.

Runner kiểm checksum journal/báo cáo, giá prefix, ngày tin và model/scaler/
mapping tại cutoff. QA đọc lại ba tín hiệu Trend/Pattern/Indicator từ báo
cáo gốc và kiểm đồng thuận Alpha từ đúng năm factor đã lưu. Ba báo cáo Trend
viết tắt có đủ bằng chứng bộ đọc; không suy đoán hướng từ diễn giải.

Có 344 nhãn `WIN_IF_LONG`, 508 nhãn `LOSS_IF_LONG`, 338 trường hợp bull trap.
Đây là thống kê nhãn giả định LONG của kho prior; chưa là kết quả giao dịch
của phương pháp Bayesian hoặc benchmark ngoài mẫu.

**Giới hạn phải giữ trong luận văn:**

- Dữ liệu đầu vào 2018–2022, nhưng warm-up 600 phiên đẩy ngày quyết định
  đầu đến 01/06/2020; ngày tất toán cuối 30/12/2022. Không có episode
  2018–2019, đúng lịch W2-02; không giảm warm-up hoặc bù dữ liệu tương lai.
- 0/852 episode có tin đủ độ tin cậy; cả 852 sentiment là NEUTRAL do cơ chế
  thiếu tin. Không gọi đây là bằng chứng thị trường trung tính hoặc kết luận
  về hiệu quả của Sentiment Agent.
- QA Phase C chưa mở gate giá thô kiểm định 2023–2024.

## Lệnh tái lập

Chạy tại thư mục gốc repo, với staging/bản sao lưu còn đầy đủ:

```powershell
py -3.13 -X utf8 scripts/publish_historical_memory.py --require-complete
py -3.13 -X utf8 scripts/audit_historical_memory.py
```

Lệnh phát hành lại cùng nội dung được phép. Lệnh audit xác minh kho chính
thức với journal và archive tin đã đóng băng, sau đó xuất QA JSON. Kho có
thể nạp độc lập bằng `HistoricalMemory` cùng bộ giá `data/execution_prices`;
QA đầy đủ cần thêm bằng chứng staging đã lưu trữ.

## Sao lưu và bảo toàn bằng chứng

Bản ZIP cục bộ:
`outputs/historical_memory_archives/historical_memory_852_20261004.zip`.
Đã xác minh từng file bên trong theo SHA-256: **2.124 file**, **7.237.279 byte**.
SHA-256 của ZIP:
`3e54b6e992a2f72861773fef92179a76cb8c71d940e857fdeed1f2cb4ab0bcb2`.
ZIP tạo bằng PowerShell, dùng để khôi phục thư mục `historical_memory_run`.
Giữ bản ZIP và staging cục bộ; không xóa bằng chứng gián đoạn trước khi
có bản sao lưu độc lập. Lần chốt Phase C này chưa xóa file tạm hay staging.

## Kiểm thử trước tích hợp

- Compileall: PASS.
- Toàn bộ unit tests: **235/235 PASS** (47,890 giây).
- E2E xác định: PASS (7,1 giây).
- Leakage suite: **38/38 PASS**.
- Chín test phát hành/QA gồm từ chối kho thiếu mã/thiếu điểm, ID trùng,
  scalar NumPy, archive tin sai hash và bằng chứng bộ đọc sai checksum.
- Phát hành dữ liệu thật: 852 hoàn thành, 0 còn lại; QA dữ liệu thật PASS.

Phase D đã hoàn thành: biểu đồ, bốn gate và rà soát deliverables được ghi trong
[biên bản chốt tuần](phase_d_week_close.md). Bước tiếp theo là W3: Bayesian Prior
Retriever và bộ định dạng tiền tố ngắn gọn.
