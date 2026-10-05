# Phase A — chốt hợp đồng truy xuất và phương pháp

**Trạng thái: W3-01 đến W3-04 hoàn thành ngày 04/10/2026; Gate A đã đóng.**
Các hợp đồng/phương pháp đã khóa; mọi thay đổi phải ghi lý do và phiên bản trước
khi dùng kết quả kiểm định 2023–2024. Chưa triển khai retriever runtime/Phase B.

## W3-01 — đầu vào

- [x] Đối chiếu kho với manifest/QA, schema và số 852; ghi hash, độ phủ theo mã/regime.
- [x] Kiểm tra `HistoricalMemory.load/eligible/records` để tái dùng xác minh và deep copy;
  xác định chi phí nạp một lần, không đọc CSV/kiểm giá lại trong mỗi query.
- [x] Ghi giới hạn warm-up, sentiment hằng và giá 2023–2024 chưa qua gate.
- [x] Chốt đầu ra W3 độc lập; tích hợp state/graph/Decision/backtest ở W4.

**Bằng chứng:** cập nhật mục kết quả cuối file, chỉ rõ hash và hàm được tái sử dụng.

## W3-02 — API

Đã chốt [hợp đồng API phiên bản 1](retriever_api_contract.md): khởi tạo từ kho,
manifest và QA đã xác minh; `retrieve(...)` nhận tham số theo tên. Regime/tín hiệu
do caller xác minh PIT; retriever kiểm cutoff prior, không tự fit HMM hoặc gọi upstream.

- [x] Khóa kiểu và validation: mã/ngày/regime/mode hợp lệ, K nguyên Python gốc 0..3,
  seed nguyên Python gốc 0..2^32−1; signals đủ năm trường khi dùng similarity/Bayesian với K>0.
- [x] Chốt `scope`: mặc định `same_symbol`; tùy chọn `pooled` bốn mã phải tường minh
  và dùng giống nhau cho cả bốn mode trong một thí nghiệm. Không tự mở rộng scope khi thiếu K.
- [x] Chốt result: `tasks`, `stats`, `metadata` (mode, scope, seed, cutoff, regime,
  bank hash, số eligible/cùng regime/selected, IDs, score, lý do thiếu mẫu).
- [x] K=0 trả tasks rỗng, stats None và pool counts None; Original không nhận BRPP hoặc thống kê. Pool rỗng
  là kết quả hợp lệ có lý do, đầu vào sai hoặc hậu điều kiện cutoff sai phải ném lỗi.
- [x] Không làm thay đổi input/record gốc hoặc chia sẻ object mutable giữa query;
  trả kiểu Python gốc có thể JSON serialize với `allow_nan=False`.

## W3-03 — luật chọn prior

Pool chung: kho hợp lệ → `exit_date < as_of_date` → scope đã chốt. Record không
đủ cutoff được loại bởi bộ lọc; nếu lọt vào kết quả/stats, ném `ValueError`/`AssertionError`.

Đã chốt [luật chọn prior](prior_selection_method.md) và
[cấu hình phiên bản 1](prior_selection_policy.json).

| Mode | Quy tắc đã chốt | Khi ít hơn K |
| --- | --- | --- |
| `recent` | `exit_date` giảm dần, tie-break `episode_id` tăng dần | Lấy số hiện có |
| `random` | Lấy không hoàn lại từ pool đã sắp ID; RNG cục bộ theo seed và query bằng hash ổn định, không dùng `hash()` Python | Lấy số hiện có |
| `similarity` | Điểm so khớp hướng tín hiệu; score giảm dần, rồi ngày exit giảm dần, rồi ID tăng dần | Lấy số hiện có |
| `bayesian_regime` | Lọc cùng regime, chọn similarity cao nhất, tie-break giống similarity | Giữ cùng regime, không bù khác regime |

- [x] Khóa bảng ánh xạ mỗi tín hiệu sang hướng chuẩn; dùng helper hiện có khi phù hợp,
  từ chối giá trị không rõ thay vì tự suy diễn hướng từ đoạn văn.
- [x] Similarity dùng tỷ lệ khớp của bốn trường Trend/Pattern/Alpha/Indicator,
  trọng số bằng nhau; sentiment không góp điểm vì cả kho thiếu tin. Nếu bổ sung tin,
  phải đổi phiên bản metric và kiểm tra lại trước thí nghiệm.
- [x] Không dùng return, WIN/LOSS, bull trap hoặc nhãn tương lai của query để chọn K.
- [x] Ghi metric/weight/seed/tie-break/scope vào cấu hình và receipt; không tuning trên OOS.

## W3-04 — thống kê và BRPP

Đã chốt [thống kê và BRPP](statistics_and_prefix_contract.md) cùng
[policy v1](statistics_prefix_policy.json). Population là **toàn bộ pool cùng regime
sau cutoff/scope**, không chỉ K ví dụ. Ghi cùng thống kê cho các nhánh prior đối chứng;
Original không nhận thống kê.

- [x] Win-rate LONG: `wins / n`, với wins là `WIN_IF_LONG`; đây là nhãn LONG giả định
  sau phí, không phải hit-rate lệnh LONG thực tế của Decision.
- [x] Bull trap có điều kiện: số bullish Trend hoặc Pattern nhưng LOSS chia cho số
  episode có ít nhất một trong hai tín hiệu bullish; union không đếm đôi, tử số khớp flag W2.
- [x] False bullish riêng Trend/Pattern: số bullish nhưng LOSS / số bullish của agent;
  không coi mọi LOSS là false breakout hoặc suy ra độ tin cậy của Sentiment Agent.
- [x] Mẫu số 0 → `null`/không đủ mẫu, không 0% và không NaN; luôn có count hỗ trợ.
- [x] Chốt không smoothing Beta/Laplace, không ngưỡng minimum support; giữ tỷ lệ mẫu
  và counts. Không gọi empirical rate là posterior hiệu chuẩn hoặc xác suất thắng query.
- [x] Khóa template, đơn vị `len(text)` (ký tự Unicode), làm tròn và n=0/K=0/K<3;
  không có dấu hiệu sentiment đáng tin khi dữ liệu thực tế thiếu tin.

**Gate A PASS:** bốn task trên đủ biên bản quyết định; scope, metric, thống kê,
đối chứng và template/version đã khóa. Đặc tả phương pháp đã cập nhật.

## Kết quả và nhật ký

### 04/10/2026 — W3-01 hoàn thành

Biên bản máy đọc được: [input_readiness.json](input_readiness.json).
Script tái kiểm: `scripts/verify_bayesian_inputs.py`; chỉ đọc đầu vào, ghi receipt,
không triển khai retriever, không gọi LLM, không fit HMM hoặc thay đổi kho.

#### Đối chiếu đầu vào

- Kho/manifest/QA cùng SHA-256:
  `09b48c6192a092b562173e8b3b7eceb44025c6e02454093e34214a730a460949`.
- Schema W1 khớp QA:
  `77954798615a5075ccca1c4f7817a33bc58eac1e398ec0460114bc46eca39148`.
- Signature run khớp manifest/QA:
  `e2f04ef08863e53570589c3a443be16759a7c9e3474074dfa284afcb816f173c`.
- `HistoricalMemory.load()` đã xác minh 852 record bằng validator W1 của ứng dụng:
  trường/kiểu JSON, ngày/lịch phiên, ID, không chồng lấn, giá thực thi và P&L engine.
  Audit gốc được chạy lại để kiểm thêm provenance/journal/model/tin/báo cáo.

| Độ phủ | Số episode |
| --- | ---: |
| FPT / MWG / VCB / VNM | 211 / 213 / 215 / 213 |
| BULL / BEAR / CHOPPY / CONSOLIDATION | 337 / 191 / 248 / 76 |
| Năm 2020 / 2021 / 2022 | 201 / 329 / 322 |
| Sentiment NEUTRAL | 852 |

Ngày quyết định đầu 01/06/2020; exit cuối 30/12/2022. Không có episode 2018–2019
vì warm-up 600 phiên. Tin đáng tin cậy vẫn 0/852; sentiment không có sức phân biệt
trong kho này. Gate giá VCI/KBS chỉ PASS giai đoạn tạo kho 2018–2022; kiểm định
2023–2024 cần gate riêng. Không dùng nến điều chỉnh W1 để tính lại nhãn kinh tế.

#### Quyết định tái sử dụng

| Hàm | Vai trò W3 | Bằng chứng |
| --- | --- | --- |
| `HistoricalMemory.load()` | Nạp/xác minh một lần lúc tạo retriever; không gọi lại trong mỗi query | Loader giá được gọi đúng một lần mỗi mã, tổng bốn lần |
| `HistoricalMemory.eligible(t, symbol)` | Pool đã lọc `exit_date < t`; scope cùng mã hoặc pooled được chốt ở W3-02 | Đối chiếu IDs tại bốn cutoff; loại toàn bộ chu kỳ chưa đóng vào exit đầu 04/06/2020 |
| `HistoricalMemory.records` | Bản sao dùng kiểm toán/khởi tạo index; tránh copy toàn kho lặp lại mỗi query | Sửa dữ liệu lồng nhau trong `records`/`eligible` không đổi kho gốc |
| `read_json`, `iso_date`, `validate_signals`, `is_bullish` | Tái dùng đọc JSON nghiêm ngặt và kiểm đầu vào/nhãn | Bảng hướng đầy đủ và luật similarity vẫn phải khóa ở W3-03 |

Trong phép kiểm truy vấn, việc đọc JSON qua kho và gọi loader giá bị chặn bằng
mock; truy vấn/`records` vẫn hoàn tất. Nguồn trả pool không được bỏ qua hậu điều kiện
cutoff khi xây retriever. `load()` không tự kiểm manifest/QA: lớp khởi tạo W3 phải
giữ bước đối chiếu checksum như verifier, không chỉ tin trạng thái PASS cũ.

Khảo sát trên Python 3.13.5: cold load khoảng **17.136 ms**; median của 100 lần
`eligible('2023-01-03', 'FPT')` khoảng **3,20 ms**. Đây là số đo khảo sát trong lúc
các kiểm tra khác cùng chạy, chưa phải gate <30 ms của retriever bốn mode. Cold load
gồm kiểm giá/P&L; hot query không đọc CSV hoặc kiểm giá lại. Giữ xác minh cold load,
chỉ cân nhắc index sau khi đo nút chậm, không bỏ validation để đạt tốc độ.

#### Ranh giới triển khai và phép đo đã chốt

- W3: module độc lập nhận regime PIT/tín hiệu hiện tại, trả tasks/stats/metadata,
  formatter BRPP, smoke offline, unit/leakage tests và benchmark.
- W4: nối state, inject Decision, ablation flag, gọi retriever trong backtest,
  checkpoint IDs/seed/hash/fallback và bảo toàn upstream một lần/điểm.
- Trần compact hiện tại ghi 7.500 ký tự trong log; W3 kiểm prompt ghép thử <6.500,
  W4 phải áp dụng trần đúng tại runtime. Không thay runtime trong W3-01.
- Khóa phép đo W3-14 theo [Phase D](phase_d_validation_and_handoff.md#w3-14--benchmark-retrieval):
  K=3, kho thật, bốn mode, 100 warm-up và ít nhất 1.000 lượt/mode, đo tuần tự,
  p95 hot retrieval <30 ms **từng mode**, cold load/formatter/end-to-end báo riêng.
  Scope/metric/query cụ thể được khóa ở W3-02/W3-03 trước đo, không sửa phép đo
  sau khi nhìn kết quả để báo PASS.

#### Lệnh kiểm chứng

```powershell
py -3.13 -X utf8 scripts/audit_historical_memory.py
py -3.13 -X utf8 scripts/verify_bayesian_inputs.py
```

Verifier mặc định ghi lại `docs/plan/week3/input_readiness.json`; timings có thể thay đổi
giữa các lần chạy. Hash mã verifier được tính từ văn bản UTF-8 chuẩn hóa newline.
Kết quả audit và verifier PASS, bốn gate tích hợp ghi trong nhật ký README.
**Tại thời điểm chốt W3-01, Gate A chưa đóng:** W3-02, W3-03, W3-04 còn chờ chốt hợp đồng/phương pháp.

### 04/10/2026 — W3-02 hoàn thành

- Đầu ra: [retriever_api_contract.md](retriever_api_contract.md), phiên bản API 1.
- Chốt chữ ký constructor/query, validation, K=0..3, seed, scope mặc định cùng mã
  và pooled tường minh; mọi mode paired phải dùng cùng scope/version kho.
- Chốt tasks nguyên schema W1, stats envelope, metadata/score/counts và bảng
  disabled/empty/partial/complete. Thiếu dữ liệu là kết quả có reason; input/bất biến
  sai là lỗi, không trả empty để che lỗi nạp kho/cutoff.
- Chốt trách nhiệm caller xác minh regime/tín hiệu PIT và result không mutate input/kho.
- Ghi ca nghiệm thu cho triển khai W3-05..13 và ví dụ K=0 minh họa, không dùng nhãn
  regime giả định làm chứng cứ dữ liệu thực tế.
- Đây là bước chốt hợp đồng: chưa tạo module retriever hoặc chạy các ca nghiệm thu
  thuật toán. W3-03 còn khóa ranking/metric/alias, W3-04 còn khóa metric stats/template.
- Bốn gate hồi quy hiện có được chạy trước tích hợp; kết quả ghi ở README.
  **Gate A còn mở vì W3-03/W3-04 chưa hoàn thành.**

### 04/10/2026 — W3-03 hoàn thành

- Đầu ra: [luật chọn prior](prior_selection_method.md),
  [policy v1](prior_selection_policy.json), [receipt kiểm chứng](selection_policy_review.json).
- Khóa NFC/strip/upper/exact alias theo từng miền tín hiệu; kiểm kê nhãn cả 852
  record PASS. Không tự đọc hướng từ báo cáo hoặc biến trường sai thành NEUTRAL.
- Khóa score tỷ lệ khớp bốn tín hiệu kỹ thuật, 0,25/trường; sentiment 0, không dùng
  outcome/return vào ranking. Bayesian lọc cùng regime rồi ranking giống Similarity.
- Khóa Recent theo exit giảm dần/ID tăng dần; Similarity theo score giảm dần rồi
  exit giảm dần/ID tăng dần; thiếu mẫu không đổi scope/regime.
- Khóa RNG cục bộ theo digest query, sample trên pool sắp ID, không dùng hash kho
  hoặc global RNG. Ví dụ tham chiếu ranking/random, đảo thứ tự pool, thêm record
  tương lai hợp lệ và không đổi global RNG đều PASS; không phải test runtime retriever.
- Bổ sung version metric/sampling và effective_seed dạng hex vào metadata API v1
  trước triển khai. Stats/version thống kê vẫn chờ W3-04.
- Bốn gate codebase trước tích hợp ghi tại README. **Gate A còn mở vì W3-04 chưa xong.**

### 04/10/2026 — W3-04 hoàn thành, đóng Gate A

- [Hợp đồng stats/BRPP](statistics_and_prefix_contract.md),
  [policy v1](statistics_prefix_policy.json), [receipt](statistics_prefix_review.json).
- Chốt population cùng scope/regime sau cutoff, stats chung bốn nhánh prior,
  bốn metric có numerator/denominator/rate, zero denominator=None, không smoothing
  hoặc minimum support. Original K=0 không nhận stats/prefix.
- Chốt template tiếng Việt NFC, rate một chữ số thập phân, return có dấu và
  scientific khi cần giữ dấu/độ dài; W/L vẫn lấy từ nhãn LONG ròng đã xác minh.
  Ghi thiếu tin một lần, không suy diễn Sentiment Agent đáng tin từ NEUTRAL.
- Fixture tính tay PASS (WIN 2/4, trap 2/3, TrendFail 1/2, PatternFail 2/2);
  n=0/không bullish và mẫu K=0..3 PASS. Mẫu dài nhất đã khảo sát 397 ký tự.
  Kho thật đối chiếu 344 WIN/852 và 338 trap, ghi rõ scope pooled/tóm tắt mô tả.
- Bổ sung statistics/prefix version vào metadata API; cập nhật đặc tả phương pháp,
  đầu vào Phase B/C và kế hoạch tổng. Bốn gate hồi quy ghi tại README.
- **Phase A hoàn thành, Gate A PASS.** W3-05..16 vẫn chưa thực hiện;
  bước tiếp theo W3-05 nạp kho/lọc PIT/bảo vệ dữ liệu, không có retriever runtime
  hoặc prompt ghép thực tế đã được báo PASS trong task chốt phương pháp này.
