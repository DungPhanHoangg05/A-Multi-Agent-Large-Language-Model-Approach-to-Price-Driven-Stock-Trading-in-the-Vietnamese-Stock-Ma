# Tuần 4 — Tích hợp prior vào hệ thống đa agent

**Đã chốt W4: 16/16 task, bốn gate kỹ thuật và pilot FPT 20 điểm/100 Decision PASS.**
Cảnh báo retrieval p95 đã xử lý ngày **07/10/2026**. Pilot hoàn thành sau ngoại lệ
chạy lại upstream riêng điểm 16 được người dùng xác nhận và ghi audit. Prior mặc định tắt.
[Kế hoạch tổng](../plan.md) · [Tuần 3](../week3/README.md)

## Luồng chính và vận hành

[Hướng dẫn API, checkpoint/resume và bàn giao W5](week_close_and_handoff.md)
là tài liệu vận hành duy nhất của tuần này.

- Mỗi điểm dùng một bộ báo cáo Full/upstream đã lưu; năm Decision dùng cùng bản sao.
- Adapter xác minh giá/tin/regime/model PIT, hỗ trợ historical prefix và fixed train OOS.
- Kinh tế giữ LONG Open(t+1) → Close(t+3), SHORT tiền mặt, phí/slippage hai chiều.
- Cap báo cáo tổng 4.000, BRPP ≤600; prompt cuối <6.500 ký tự, guard trước API.
- Checkpoint durable từng nhánh; resume kiểm identity và không gọi lại nhánh complete.

## Kết quả nghiệm thu mới nhất

Compileall, **521 unit**, **E2E**, **93 leakage** PASS trong lượt nghiệm thu cuối
07/10/2026. Pilot thật **20/20 điểm, 100/100 Decision structured**; `--verify-only`
PASS toàn schema/semantic/source/hash/PIT/prompt/economic checkpoint, không gọi API.
Smoke tích hợp trước đó gồm 8 context tổng hợp và 6 replay nguồn thật với Decision
giả; kiểm paired/resume/flag off và biên prompt 6.499 nhận/6.500 chặn.

| Mode | Baseline trước tối ưu p95 (ms) | Sau tối ưu p95 (ms) | Gate <30 ms |
| --- | ---: | ---: | --- |
| Bayesian Regime | 34,839 | 11,559 | PASS |
| Random | 30,070 | 10,837 | PASS |
| Recent | 29,015 | 10,927 | PASS |
| Similarity | 37,286 | 13,235 | PASS |

Giữ phương pháp W3: 100 warm-up, 1.000 mẫu/mode/bước, bốn mode/hai scope,
p95 nearest-rank, toàn bộ mẫu và oracle. Tối ưu lookup alias và copy pool đã
xác minh; guard/type/PIT/ownership giữ nguyên. PASS áp dụng phiên bản và máy
đã đo; không bảo đảm mọi máy/request <30 ms. Các receipt chi tiết trước/sau
nằm nguyên byte trong ZIP bằng chứng, gồm cả FAIL W4-15 và baseline mới.

## Checklist đã hoàn thành

### A — Hợp đồng tích hợp

| Task | Công việc | Trạng thái |
| --- | --- | --- |
| W4-01 | Kiểm tra bàn giao và các điểm nối runtime | [x] |
| W4-02 | Chốt state và cấu hình prior độc lập | [x] |
| W4-03 | Chốt provenance và thứ tự PIT | [x] |
| W4-04 | Chốt schema kết quả và resume | [x] |

### B — State, prompt và graph

| Task | Công việc | Trạng thái |
| --- | --- | --- |
| W4-05 | Cài state/config và validator | [x] |
| W4-06 | Áp dụng cap và guard prompt runtime | [x] |
| W4-07 | Chèn BRPP và hướng dẫn reasoning | [x] |
| W4-08 | Ghép graph với ranh giới chuẩn bị báo cáo | [x] |

### C — PIT, paired và checkpoint

| Task | Công việc | Trạng thái |
| --- | --- | --- |
| W4-09 | Cài adapter context/regime PIT | [x] |
| W4-10 | Tạo báo cáo chung cho năm nhánh | [x] |
| W4-11 | Ghép retriever vào backtest | [x] |
| W4-12 | Lưu và phục hồi tiến trình từng nhánh | [x] |

### D — Kiểm chứng và bàn giao

| Task | Công việc | Trạng thái |
| --- | --- | --- |
| W4-13 | Kiểm thử leakage toàn đường tích hợp | [x] |
| W4-14 | Smoke E2E offline và tương thích | [x] |
| W4-15 | Chạy bốn gate và kiểm phạm vi thay đổi | [x] |
| W4-16 | Chốt W4, bàn giao điều kiện pilot W5 | [x] |

## Điều kiện đã mở theo yêu cầu chốt W4

- [x] Mở gate giá/tin FPT+VNINDEX OOS 2023–2024 bằng nguồn riêng VCI/KBS.
- [x] Chốt model/freeze và kế hoạch 20 cutoff trước mọi API.
- [x] Chốt model/config/quota/pacing dùng chung; preflight text/vision thật PASS.
- [x] Viết và kiểm CLI nghiên cứu dry-run/preflight/verify/resume gọi API W4.
- [x] Nghiệm thu pilot FPT 20 điểm × 5 nhánh, 100 Decision; verifier offline PASS.

CLI `scripts/run_bayesian_ablation.py` đã triển khai; lệnh vận hành trong hướng dẫn
bàn giao. Pilot kiểm tính vận hành và quota; benchmark OOS chính thức W6 cần
kế hoạch mẫu bốn mã và ngân sách riêng trước khi chạy.

### Kết quả chốt gate W4

| Gate | Tiến độ ngày 07/10/2026 |
| --- | --- |
| Giá OOS | PASS: nguồn riêng `data/execution_prices_oos`, 2018–2024 gồm warm-up; 1.750 phiên/mã, 8 mẫu quyền VCI/KBS, 1.510/1.532 chu kỳ hợp lệ |
| Model/PIT | PASS train-only: tái lập HMM/scaler/calibration từ VNINDEX 2018–2022 khớp artifact; giữ nguyên metadata RESEARCH_ONLY/UNVERIFIED |
| Sample/tin | PASS PIT: khóa 20 cutoff FPT trước API, 05/01–03/04/2023, cách ≥3 phiên; cả 20 điểm thiếu tin hợp lệ nên giữ NEUTRAL có lý do |
| Quota | PASS trong phạm vi pilot: mỗi model 30 RPM/1.000 RPD/8.000 TPM/200.000 TPD; mọi cửa sổ RPM/TPM/RPD/TPD thực đều trong giới hạn, 0 HTTP 429; unknown request giữ toàn reserve |
| CLI/pilot | PASS: 20/20 common-support point, 100/100 Decision structured, verifier offline complete; paired năm nhánh dùng 20 shared bundle; 15 point/75 Decision cũ còn nguyên byte sau đối soát |

### Telemetry pilot và giới hạn vận hành

| Model | HTTP 200 / chưa rõ kết quả | Input / output token đã biết | TPD tối đa tính cả reserve | RPM / TPM reserve / RPD tối đa | HTTP p95 thành công |
| --- | ---: | ---: | ---: | ---: | ---: |
| `openai/gpt-oss-20b` | 103 / 0 | 178.591 / 15.627 | 194.218 | 1 / 7.641 / 103 | 2,094 giây |
| `qwen/qwen3.8-27b` | 43 / 1 | 90.826 / 5.673 | 102.034 | 1 / 5.535 / 44 | 2,047 giây |

Ledger có 147 request: 146 HTTP 200 (140 request hoàn thành pilot, 6 kiểm text/vision)
và 1 transport_error không có response/request ID; không có HTTP 429. Qwen dùng
96.499 token đã biết + 5.535 reserve chưa biết kết quả. HTTP p95 chỉ tính response
thành công, không gồm pacing/gián đoạn. BRPP thực dài nhất **369**, prompt **4.483**
ký tự, dưới cap 600/6.500. Tất cả 100 Decision đều `llm_structured`; không còn point
hoặc branch đang chạy/thất bại. Một attempt Decision bị guard token chặn trước HTTP
đã được giữ trong lịch sử và phục hồi sau khi chuẩn bị tokenizer có checksum.

GPT-OSS còn 5.782 token so với ngân sách ngày 200.000 của lượt này. Gate quota PASS
cho pilot đã đo; benchmark W6 cần chốt lịch/quota theo quy mô mới. Tin pilot toàn
NEUTRAL và mẫu chỉ đầu OOS 2023; chưa có kết luận tăng lợi nhuận ngoài mẫu.

Nguồn train, artifact và kho 852 episode giữ nguyên. Plan/snapshot tin/quota ledger
và checkpoint vận hành ở `outputs/oos_pilot/`, `outputs/pilot_fpt_run/`, được
gitignore; không tạo thêm Markdown nghiệm thu hoặc receipt chỉ lặp tiến độ.

## Bằng chứng và quy ước tài liệu

Các receipt từng task, nhật ký và lượt benchmark cũ được đóng gói nguyên byte
trong [implementation_evidence.zip](../implementation_evidence.zip), với tên
entry là đường dẫn gốc từ repo. ZIP chứa cả lượt FAIL và PASS; mở archive khi
cần đối chiếu chi tiết lịch sử. Các JSON còn rời ở tuần này là đầu vào của
code, schema hoặc fixture hồi quy; không xóa chúng theo đuôi file.

Cập nhật tiến độ tại README này sau mỗi task. Chỉ tách tài liệu cho một hướng
dẫn/phương pháp có nhu cầu đọc độc lập; không tạo thêm biên bản Markdown và
receipt JSON chỉ để nhắc lại cùng kết quả kiểm thử.

### Gián đoạn đã đối soát

Request Pattern tại FPT 16/03/2023 đã reserve 5.535 token nhưng không nhận được
response durable; quota vẫn tính toàn reserve này. Không có báo cáo hay request ID
để chứng minh request chưa được provider xử lý. Checkpoint giữ `upstream_started`;
resume tự động phải dừng `AMBIGUOUS_UPSTREAM`. Người dùng đã xác nhận: **“Chạy lại từ
điểm 16. Chạy đến khi hoàn thiện xong và pass hết W4”**. Đã lưu nguyên byte checkpoint
lỗi và audit tại `outputs/oos_pilot/reconciliation/`; chỉ điểm 16 được đưa về planned
để chạy lại upstream một lần. Cả 19 point khác, 75 Decision complete, nguồn/model/
config/plan/identity và quota ledger giữ nguyên, được đối chiếu checksum trước/sau.
Đây là ngoại lệ có xác nhận, không là chứng nhận exactly-once API ở điểm 16.
Usage trước resume: text 145.955 token; vision 71.853 token đã biết + 5.535 reserve
chưa biết kết quả. Đã hoàn thành bằng API runner công khai với cùng identity, transport
vẫn reserve input + toàn output và kiểm RPM/TPM/RPD/TPD trước từng request; không
dùng dự phòng toàn điểm 48.000 token để dừng sớm khi ngân sách thực còn đủ.
Điểm 16 và toàn bộ run đã được verifier offline nghiệm thu; không còn gate bị chặn.
WinError 5 trước Full tại điểm 15 đã phục hồi từ report upstream durable, không lặp
Pattern/Trend. Ngoại lệ point 16 vẫn được giữ rõ trong báo cáo, không xóa dấu lỗi cũ.

## Nhật ký tiến độ

- 07/10/2026: mở bộ giá OOS riêng bốn mã VCI/KBS, kiểm train-only model, khóa
  plan/quota và hoàn thành pilot 20/20 điểm, 100 Decision. Verifier offline,
  compileall, 521 unit, E2E và 93 leakage PASS. Đối soát point 16 theo xác nhận
  người dùng; 75 Decision cũ nguyên byte; source/model/bank/plan không đổi.
- 07/10/2026: gom tài liệu tuần từ 96 xuống 25 file rời (12 Markdown, 13 JSON
  cần cho code/test); 28 Markdown và 43 JSON dư thừa đã đóng gói trong một ZIP.
  Kiểm checksum archive/fixture và liên kết PASS; code, bank và dữ liệu không đổi.
  Compileall, 502 unit, E2E và 93 leakage PASS sau dọn tài liệu.
