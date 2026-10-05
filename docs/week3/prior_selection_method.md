# Luật chọn prior và similarity — phiên bản 1

**Chốt W3-03 ngày 04/10/2026.** Cấu hình đóng băng tại
[prior_selection_policy.json](prior_selection_policy.json), tương thích
[hợp đồng API v1](retriever_api_contract.md). Nền W3-05, Recent/Random W3-06 và
Similarity W3-07 đã có; Bayesian W3-08 còn chờ triển khai.
Không chọn tham số bằng kết quả kiểm định 2023–2024.

## 1. Tập hợp và thứ tự xử lý

1. Khởi tạo từ kho/manifest/QA đã xác minh. Kiểm nhãn của năm trường bằng bảng
   alias dưới đây; nhãn không rõ phải ném `ValueError`, không bỏ record hoặc tự gán NEUTRAL.
2. Với query, kiểm kiểu/enum/K/seed/scope theo W3-02. Nếu có `current_signals`,
   kiểm đủ trường và chuẩn hóa đúng bảng ở mọi mode, kể cả K=0. None được phép
   đúng các trường hợp W3-02; K>0 similarity/Bayesian bắt buộc có signals.
3. K=0 kết thúc theo hợp đồng disabled, không xếp hạng/tạo pool/stats.
4. K>0: lọc `exit_date < as_of_date`, rồi scope. Đây là pool chung E của bốn mode.
   Lập tập R = các record trong E có regime đúng query để tính matched count/stats.
5. Chọn candidate, ranking và tối đa K theo mode. Kiểm IDs/cutoff/scope/regime
   đầu ra và toàn bộ population thống kê. Vi phạm hậu điều kiện phải ném lỗi.

Outcome trong prior là nhãn đã tất toán dùng cho thống kê/BRPP về sau; **không đọc
outcome để tính score, ưu tiên WIN hoặc chọn ví dụ bull trap**. Không nhận outcome
query làm input, không gọi LLM/embedding, không fit scaler hoặc chỉnh trọng số OOS.

## 2. Chuẩn hóa tín hiệu

Mỗi giá trị phải là chuỗi Python gốc; áp dụng `unicodedata.normalize('NFC', value)`
→ `strip()` → `upper()` → so khớp **toàn bộ chuỗi** với alias. Không tìm từ khóa
trong báo cáo, không tự xóa dấu, thay dấu gạch hoặc gộp khoảng trắng ở giữa chuỗi.

| Trường | Alias được phép | Nhãn chuẩn |
| --- | --- | --- |
| Trend/Pattern/Alpha/Indicator | BULLISH, BULL, UP, TĂNG, TĂNG GIÁ | BULLISH |
| Trend/Pattern/Alpha/Indicator | BEARISH, BEAR, DOWN, GIẢM, GIẢM GIÁ | BEARISH |
| Trend/Pattern/Alpha/Indicator | NEUTRAL, TRUNG TÍNH, TRUNG_TÍNH | NEUTRAL |
| Sentiment | POSITIVE, TÍCH CỰC | POSITIVE |
| Sentiment | NEGATIVE, TIÊU CỰC | NEGATIVE |
| Sentiment | NEUTRAL, TRUNG TÍNH, TRUNG_TÍNH | NEUTRAL |

Ví dụ `" tăng "` → BULLISH, Unicode dấu tổ hợp được chuẩn NFC; `"xu hướng tăng"`,
`"BULLISH (0.8)"`, `"TĂNG/GIẢM"`, nhãn trống hoặc báo cáo dài → lỗi.
POSITIVE không được dùng như nhãn Trend; BULLISH không được dùng như nhãn Sentiment.
Giữ nguyên tín hiệu gốc trong HistoricalTaskRecord; dùng bản chuẩn hóa riêng để
ranking, không ghi đè record/upstream. Alias tăng khớp `is_bullish()` trong W2;
`validate_signals()` được tái dùng kiểm cấu trúc nhưng chưa thay được kiểm alias.

Kiểm kê **toàn bộ kho thật 852 episode**, không dựa trên một vài bản ghi:

| Trường | BULLISH | BEARISH | NEUTRAL |
| --- | ---: | ---: | ---: |
| trend | 393 | 241 | 218 |
| pattern | 505 | 309 | 38 |
| alpha_consensus | 269 | 481 | 102 |
| indicator_consensus | 343 | 365 | 144 |
| sentiment | Không áp dụng | Không áp dụng | 852 |

Tất cả nhãn hiện có được bảng alias chấp nhận. Không có lý do loại record hoặc
gán tín hiệu thiếu khi áp dụng cấu hình này.

## 3. Similarity

Đóng băng `metric_version="signal_match_v1"`:

```text
score(record, query) = 0.25 × (
    [trend_record == trend_query] +
    [pattern_record == pattern_query] +
    [alpha_record == alpha_query] +
    [indicator_record == indicator_query]
)
```

So sánh **nhãn đã chuẩn hóa**; các dấu ngoặc vuông là indicator 0 hoặc 1.
Score Python float hữu hạn, thuộc {0.0, 0.25, 0.5, 0.75, 1.0}. NEUTRAL là nhãn
hợp lệ và khớp NEUTRAL đóng góp 0,25, không coi nó là trường thiếu. Bốn trường
đều phải có nhãn hợp lệ; không tự đổi mẫu số hoặc trọng số khi một trường sai.

Sentiment có trọng số **0** vì cả kho không có tin đáng tin và đều NEUTRAL; vẫn
kiểm nhãn và giữ sentiment trong record. Không tự tăng trọng số khi gặp query
POSITIVE/NEGATIVE. Thêm dữ liệu tin/trọng số khác phải tạo metric version mới
trước thí nghiệm, không sửa cấu hình đã dùng sau khi xem kết quả.

Không dùng khoảng cách ngày, giá, return hoặc regime trong chính score. Ngày chỉ
phá hòa; regime chỉ lọc candidate của Bayesian. Đây là phép so khớp tín hiệu rời rạc,
không phải xác suất thắng hoặc cosine similarity từ embedding.

## 4. Bốn chế độ và phá hòa

| Mode | Candidate | Thứ tự chọn và thứ tự tasks trả ra | Score metadata |
| --- | --- | --- | --- |
| recent | E | exit_date giảm dần → episode_id tăng dần; lấy đầu min(K, count) | None |
| random | E | Pool sắp ID tăng dần → lấy không hoàn lại theo mục 5; giữ thứ tự draw | None |
| similarity | E | score giảm dần → exit_date giảm dần → episode_id tăng dần; lấy đầu min(K, count) | score ở mục 3 |
| bayesian_regime | R | Cùng ranking/tie-break với similarity | score ở mục 3 |

ID so theo thứ tự chuỗi Python; ngày ISO nên thứ tự chuỗi tương đương thứ tự ngày.
Không dùng thứ tự JSON gốc để phá hòa. Bayesian không có same-regime record thì
empty/no_matching_regime, không bù từ E; thiếu K trả số hiện có và reason của W3-02.
Không thêm threshold score: cả score 0 vẫn là candidate nếu cutoff/scope hợp lệ.
Chỉ dùng một record mỗi episode; không cố bảo đảm đủ mã trong scope pooled.

### Ví dụ ranking tổng hợp (không phải record thật)

Query BULL, bốn hướng kỹ thuật lần lượt BULLISH/BULLISH/BEARISH/NEUTRAL; giả sử E
có các record đã tất toán sau, K=3:

| ID | Exit | Regime | Bốn hướng viết tắt (+/−/0) | Score |
| --- | --- | --- | --- | ---: |
| A | 2021-01-04 | BULL | +,+,−,0 | 1.0 |
| B | 2021-01-07 | BEAR | +,+,−,0 | 1.0 |
| C | 2021-01-07 | BULL | +,+,−,0 | 1.0 |
| D | 2021-01-08 | BULL | +,−,−,0 | 0.75 |

Recent → D,B,C; Similarity → B,C,A; Bayesian → C,A,D.
Ví dụ kiểm riêng score, tie-break ID và lọc regime; không suy ra regime thực tế
VN-Index hoặc hiệu quả giao dịch từ các dòng tổng hợp này.

Random tham chiếu với symbol FPT, as_of_date 2021-01-11, same_symbol, seed 42,
K=3 và pool A..D → **A,B,D**. Digest seed:
`032d323c2c461e03f5c55914deea672c49d291cb662faa25f0ba374792b23778`.
Biên bản kiểm kê và ví dụ: [selection_policy_review.json](selection_policy_review.json).

## 5. Random tái lập theo query

Đóng băng `sampling_version="prior_sampling_v1"`, runtime chuẩn Python 3.13.5.
Không gọi global `random.seed()`, không dùng `hash()` Python hoặc RNG dùng chung.

```python
seed_payload = {
    "sampling_version": "prior_sampling_v1",
    "seed": seed,
    "symbol": symbol,
    "as_of_date": as_of_date,
    "scope": scope,
}
seed_bytes = json.dumps(
    seed_payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
).encode("utf-8")
effective_seed = int.from_bytes(hashlib.sha256(seed_bytes).digest(), "big")
rng = random.Random(effective_seed)
ordered_candidates = sorted(eligible, key=lambda record: record["episode_id"])
tasks = rng.sample(ordered_candidates, min(k, len(ordered_candidates)))
```

Thuật toán này đã triển khai trong `_select_random()` ở W3-06; stats và result
retrieve hoàn chỉnh còn chờ W3-09.
Không đưa `bank_sha256`, outcome, signals, regime, mode hoặc K vào seed_payload:
thêm/đổi record tương lai hợp lệ ngoài E không được đổi draw của query cũ.
Hash kho vẫn lưu để kiểm toán; không dùng nó làm nguồn ngẫu nhiên cho query.
Pool hợp lệ thay đổi thì sample có thể đổi; không cam kết giữ sample khi thêm
record mới có exit trước cutoff. Đổi K cũng không cam kết sample prefix giống nhau.

Khóa thuật toán `random.Random.sample` của runtime chuẩn; nếu đổi Python làm thay
draw tham chiếu, phải kiểm fixture và phiên bản trước chạy tiếp thí nghiệm.
Seed khác không bắt buộc luôn khác IDs khi pool nhỏ; tái lập kiểm bằng cùng
seed/query/pool và version, không bằng khẳng định mọi seed đều tạo kết quả khác.

## 6. Cấu hình, metadata và nghiệm thu

Metadata bổ sung vào API v1 **trước triển khai**:

- `sampling_version`: `prior_sampling_v1` cho mọi mode/K.
- `metric_version`: `signal_match_v1` cho mọi mode/K, mô tả cấu hình được đóng băng.
- `effective_seed`: chuỗi hex SHA-256 64 ký tự của seed_bytes với mode random và
  K>0 (kể cả pool rỗng); các trường hợp khác None. Chuỗi tránh mất chính xác số lớn
  khi đọc checkpoint bằng công cụ JavaScript; RNG dùng int chuyển từ chính digest đó.

Ba trường này có trong cấu hình/receipt/checkpoint và JSON ví dụ API đã cập nhật;
thống kê/template đã khóa riêng tại [W3-04](statistics_and_prefix_contract.md).
Khi triển khai, các ca cần PASS:

1. Canonical/alias/NFC đúng; nhãn mơ hồ/sai miền lỗi; không mutate record hoặc signals.
2. Score 0/0,25/0,5/0,75/1, neutral match đúng, sentiment khác không đổi score.
3. Ranking ví dụ trên; đảo thứ tự record không đổi IDs/score/thứ tự trả về.
4. Random lặp query và đảo thứ tự gọi vẫn giữ IDs; không đổi global RNG state.
5. Record tương lai hợp lệ bị loại trước mọi ranking; thay outcome hợp lệ không
   đổi lựa chọn. Không đưa hash kho vào seed để gây đổi draw do record tương lai.
6. Empty/K<3/K=0 đúng API; không tự mở scope/khác regime để bù mẫu.

Kiểm chứng W3-03 là kiểm kê nhãn, rà soát cấu hình và tính ví dụ tham chiếu;
Recent/Random W3-06 và Similarity W3-07 đã được kiểm thử runtime tại Phase B.
Similarity dùng `_select_similarity()`: điểm bốn trường, phá hòa exit/ID, giữ score 0
và bỏ qua outcome khi ranking. Bayesian W3-08 và bộ hồi quy W3-13 còn chờ thực hiện.
