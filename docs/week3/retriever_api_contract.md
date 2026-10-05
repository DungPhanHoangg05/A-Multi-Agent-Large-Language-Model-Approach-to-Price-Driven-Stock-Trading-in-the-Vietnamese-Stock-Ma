# Hợp đồng API Bayesian Prior Retriever — phiên bản 1

**Chốt ngày 04/10/2026 cho W3-02.** Đây là đặc tả để triển khai từ W3-05,
Module nền W3-05, bốn bộ chọn W3-06..08 và stats/retrieve W3-09 đã triển khai.
Luật ranking/chuẩn hóa tín hiệu đã được chốt tại
[W3-03](prior_selection_method.md) ngày 04/10/2026;
công thức/schema metric và template BRPP đã chốt tại [W3-04](statistics_and_prefix_contract.md).

## 1. Khởi tạo và chữ ký

Chữ ký Python dự kiến, mọi tham số truy vấn truyền theo tên:

```python
BayesianPriorRetriever(
    *,
    bank_path: str | Path,
    manifest_path: str | Path,
    audit_path: str | Path,
)

retrieve(
    *,
    symbol: str,
    as_of_date: str,
    current_regime: str,
    current_signals: dict[str, str] | None = None,
    mode: str = "bayesian_regime",
    k: int = 3,
    seed: int = 42,
    scope: str = "same_symbol",
) -> dict[str, object]
```

Khởi tạo đối chiếu hash kho/schema/signature với manifest và QA PASS, rồi gọi
`HistoricalMemory.load()` một lần. Ba path bắt buộc giúp không vô tình đọc một
kho khác mà vẫn dùng QA cũ; ví dụ triển khai dùng các path W2 đã phát hành.
Lỗi nạp kho dừng khởi tạo, không trả một retriever rỗng giả thành công.
Các hàm truy vấn chỉ đọc dữ liệu đã xác minh trong RAM; không gọi loader/network/LLM.

## 2. Kiểu và validation truy vấn

| Tham số | Hợp đồng |
| --- | --- |
| `symbol` | Chuỗi Python gốc, đúng một trong `FPT`, `MWG`, `VCB`, `VNM`; không tự uppercase/trim |
| `as_of_date` | Chuỗi Python gốc đúng `YYYY-MM-DD`, ngày lịch hợp lệ qua `iso_date()`; không nhận datetime, timezone hoặc chuỗi ngày rút gọn |
| `current_regime` | Chuỗi Python gốc đúng `BULL`, `BEAR`, `CHOPPY`, `CONSOLIDATION` |
| `mode` | Chuỗi Python gốc đúng `bayesian_regime`, `random`, `recent`, `similarity` |
| `k` | `type(k) is int`, **0 ≤ K ≤ 3**; từ chối bool, float, NumPy scalar và K>3, không tự cắt K |
| `seed` | `type(seed) is int`, **0 ≤ seed ≤ 2^32−1**; mặc định 42, ghi trong metadata cả bốn mode; luật tạo RNG ở W3-03 |
| `scope` | Chuỗi Python gốc, `same_symbol` (mặc định) hoặc `pooled` |
| `current_signals` | `None` hoặc dict Python gốc có đúng năm trường schema W1, mỗi giá trị là chuỗi Python gốc không rỗng sau strip; không thay thế bằng báo cáo văn bản |

Năm trường tín hiệu: `trend`, `pattern`, `alpha_consensus`, `indicator_consensus`,
`sentiment`. Nếu truyền dict, luôn kiểm cấu trúc qua `validate_signals()` kể cả
K=0. Với K>0, `similarity` và `bayesian_regime` **bắt buộc có current_signals**;
`random`/`recent` cho phép None. K=0 cho phép None ở mọi mode.
Nếu có signals, chuẩn hóa/kiểm alias theo W3-03 ở mọi mode/K; schema chuỗi
không đủ để khẳng định nhãn đó có nghĩa hợp lệ. Không sửa tín hiệu gốc.

Validation kiểu/enum chạy trước nhánh K=0: truy vấn sai không được bỏ qua chỉ vì
không cần prior. Không nhận outcome/return/nhãn tương lai của query làm tham số.

**Hợp đồng PIT của caller:** `current_regime` phải lấy từ trạng thái đã xác minh
đúng ngày `as_of_date`; năm tín hiệu chỉ dùng dữ liệu đến ngày này. Một chuỗi tên
regime không đủ tự chứng minh provenance, nên retriever không tuyên bố đã kiểm
model/scaler cutoff từ riêng tham số này. W4 phải validate `MarketRegimeState`,
ngày snapshot và provenance trước khi gọi. Retriever kiểm cutoff của mọi prior.

## 3. Scope và tập dữ liệu chung

1. Lọc kho theo `exit_date < as_of_date`.
2. `same_symbol`: giữ đúng mã query. `pooled`: giữ cả bốn mã đã được phép trong kho;
   `symbol` query vẫn bắt buộc hợp lệ và được ghi trong metadata.
3. Tập sau hai bước là **eligible pool chung** cho cả bốn mode. Bayesian tiếp tục
   lọc cùng regime trước ranking; các mode đối chứng xếp hạng/chọn từ pool chung.
4. Thống kê lấy dữ liệu đã qua cutoff/scope, với tập cùng regime được ghi bằng
   `population_count`. Công thức/tên metric đã khóa ở W3-04.

**Chốt cấu hình nghiên cứu mặc định:** `scope="same_symbol"`, K=3, seed=42.
`pooled` là lựa chọn tường minh cho thí nghiệm cấu hình khác, không fallback tự động.
Trong một bộ paired comparison, scope/K/seed và version kho phải giống nhau ở các
nhánh prior. Original là K=0. Không đổi scope sau khi nhìn kết quả kiểm định để
tìm cấu hình tốt hơn; ghi scope trong cấu hình thí nghiệm và checkpoint.

## 4. Cấu trúc kết quả

Top-level có đúng ba trường: `tasks`, `stats`, `metadata`.

### `tasks: list[HistoricalTaskRecord]`

- Mỗi task giữ nguyên tất cả trường [schema W1](../plan/week1/historical_task_record.schema.json),
  không nhét score vào record. IDs không trùng; cùng thứ tự với `metadata.selected_ids`.
- Mỗi `exit_date < as_of_date`; thuộc scope/pool đã chốt, và cùng regime khi mode Bayesian.
- `len(tasks) <= k`; không bù dữ liệu ngoài pool hoặc bịa ví dụ để đủ K.
- Ranking quyết định thứ tự trong list; thuật toán và tie-break đã khóa tại W3-03.

### `stats: dict | None`

- K=0: **None**, không tính hoặc gửi thống kê cho Original.
- K>0: object có đúng `regime`, `population_count`, `metrics`.
  `regime` bằng `current_regime`; `population_count` là số eligible record cùng
  scope/regime, không phải số task đã chọn; `metrics` là dictionary theo đặc tả W3-04.
- Kho rỗng/số mẫu thống kê 0 vẫn trả object với count 0 và các tỷ lệ không xác định
  là None theo W3-04; không dùng 0% thay cho thiếu mẫu, không có NaN/Infinity.
- `metrics` có đúng `win_rate_long`, `bull_trap_rate`, `trend_false_bullish_rate`,
  `pattern_false_bullish_rate`; mỗi item đúng `numerator: int`, `denominator: int`,
  `rate: float | None` theo W3-04. Không smoothing; không tự dùng dictionary tùy ý.

### `metadata: dict`

| Trường | Kiểu / ý nghĩa |
| --- | --- |
| `api_contract_version` | int, hiện là 1 |
| `sampling_version`, `metric_version` | str, `prior_sampling_v1` và `signal_match_v1` đã khóa ở W3-03 |
| `statistics_version`, `prefix_version` | str, `regime_empirical_stats_v1` và `compact_brpp_v1` đã khóa ở W3-04 |
| `effective_seed` | str hex SHA-256 64 ký tự ở random K>0, kể cả pool rỗng; còn lại None |
| `bank_sha256` | str, SHA-256 kho đã xác minh khi khởi tạo |
| `symbol`, `as_of_date`, `current_regime`, `mode`, `scope` | str, giữ đúng query đã kiểm |
| `requested_k`, `seed` | int, giữ đúng query đã kiểm |
| `eligible_count` | int hoặc None; số pool sau cutoff/scope, trước bộ lọc regime |
| `matched_regime_count` | int hoặc None; số eligible cùng regime, bằng stats.population_count khi K>0 |
| `candidate_count` | int hoặc None; Bayesian dùng matched count; ba mode khác dùng eligible count |
| `selected_count` | int, bằng len(tasks) |
| `selected_ids` | list[str], bằng IDs của tasks theo đúng thứ tự |
| `selected_scores` | list[dict], mỗi item đúng `episode_id`, `score`; thứ tự trùng selected_ids |
| `status` | str: `disabled`, `empty`, `partial`, `complete` |
| `reason` | None hoặc str: `k_zero`, `no_eligible_history`, `no_matching_regime`, `insufficient_candidates` |

`selected_scores.score` là float Python hữu hạn trong [0,1] cho similarity/Bayesian;
recent/random dùng None, không giả định một score chất lượng. Score cụ thể đã khóa ở W3-03.
Metadata version sampling/metric/statistics/prefix đã bổ sung trước triển khai;
thay đổi hợp đồng đã chốt phải ghi rõ phiên bản tương thích.

## 5. K=0, thiếu mẫu và lỗi

| Điều kiện sau validation | tasks / stats | status / reason | Counts |
| --- | --- | --- | --- |
| K=0 | `[]` / None | `disabled` / `k_zero` | eligible/matched/candidate=None; selected=0 |
| K>0, eligible pool rỗng | `[]` / object count 0 | `empty` / `no_eligible_history` | eligible/matched/candidate=0 |
| K>0, Bayesian không có cùng regime | `[]` / object count 0 | `empty` / `no_matching_regime` | eligible>0, matched/candidate=0 |
| 0 < số candidate < K | Lấy số hiện có / stats từ population | `partial` / `insufficient_candidates` | Đếm đúng tập thực tế |
| Số candidate ≥ K | Đủ K / stats từ population | `complete` / None | Không đồng nghĩa đủ độ tin cậy thống kê |

K=0 không tạo pool hoặc stats: counts None có nghĩa **không tính**, không phải kho
không có mẫu. Truy vấn vẫn yêu cầu retriever đã khởi tạo từ kho hợp lệ. Formatter
phải trả prefix rỗng, W4 không inject prior hoặc stats vào Original.

Input sai, record/result sai schema, hash/QA sai, duplicate ID hoặc hậu điều kiện
cutoff/scope/regime bị vi phạm → `ValueError` (hoặc `AssertionError` cho bất biến nội bộ).
Lỗi đường dẫn/đọc file được phép giữ `OSError`/`FileNotFoundError`; không đổi thành
`empty`. Chu kỳ chưa tất toán bị loại ở bước eligible là hành vi bình thường;
nếu nó lọt vào tasks hoặc population thống kê thì ném lỗi.

## 6. Bảo toàn dữ liệu và ví dụ

Result là object/list Python gốc, số hữu hạn; `json.dumps(..., allow_nan=False)` phải
thành công. Input tín hiệu không bị sửa; tasks/stats/metadata không có tham chiếu
mutable đến kho hoặc giữa các lần query. Việc sửa record lồng nhau trong result
không được đổi kết quả query sau hoặc state upstream.

Ví dụ **hợp đồng K=0**, không phải output của module đã triển khai:

```json
{
  "tasks": [],
  "stats": null,
  "metadata": {
    "api_contract_version": 1,
    "sampling_version": "prior_sampling_v1",
    "metric_version": "signal_match_v1",
    "statistics_version": "regime_empirical_stats_v1",
    "prefix_version": "compact_brpp_v1",
    "effective_seed": null,
    "bank_sha256": "09b48c6192a092b562173e8b3b7eceb44025c6e02454093e34214a730a460949",
    "symbol": "FPT",
    "as_of_date": "2023-01-03",
    "current_regime": "BULL",
    "mode": "bayesian_regime",
    "scope": "same_symbol",
    "requested_k": 0,
    "seed": 42,
    "eligible_count": null,
    "matched_regime_count": null,
    "candidate_count": null,
    "selected_count": 0,
    "selected_ids": [],
    "selected_scores": [],
    "status": "disabled",
    "reason": "k_zero"
  }
}
```

BULL ở ví dụ là giá trị minh họa, không khẳng định regime thực tế ngày 03/01/2023.
Không thực hiện giao dịch hoặc vượt gate giá từ ví dụ query này.

## 7. Ca nghiệm thu bàn giao cho W3-05..13

- Query sai mã/ngày/enum, K=-1/4/True/3.0, seed=-1/True, dict thiếu/thừa/rỗng → lỗi.
- K>0 similarity/Bayesian với signals=None → lỗi; recent/random với None → hợp lệ.
- K=0 với query hợp lệ → disabled/None stats và counts None; query sai vẫn lỗi.
- Scope same_symbol không lẫn mã; pooled vẫn chỉ chứa bốn mã; không tự mở rộng scope.
- Biên `exit_date == as_of_date` không vào tasks/population; hậu điều kiện sai → lỗi.
- Empty/partial/complete khớp bảng trên; score/IDs/counts khớp tasks, JSON native.
- Sửa input/result không đổi kho/state/query khác; seed và cấu hình được ghi đúng.

Các ca này là tiêu chí kiểm thử cho triển khai, chưa được báo PASS ở W3-02.

## 8. Phạm vi triển khai W3-05

Constructor và validation/cutoff/bản sao đã có. `prepare_query(...)` có cùng query
signature như retrieve, là API chuẩn bị bổ sung cho Phase B, trả đúng ba trường:
`eligible_tasks` (pool chung sau cutoff/scope), `regime_population` (cùng regime),
`metadata` (query/hash/version và counts). Hai danh sách là bản sao độc lập.
Không có stats/ranking/selected IDs trong kết quả chuẩn bị; không coi đây là
result retrieve hoàn chỉnh hoặc gửi trực tiếp vào formatter.

K=0: prepare trả hai list rỗng và counts None; retrieve trả result disabled đúng
hợp đồng. Tại thời điểm W3-05, retrieve K>0 dừng NotImplementedError để chờ bộ chọn
và stats. Từ W3-09, retrieve K>0 đã hoạt động theo mục 10; query/data sai vẫn
ValueError. Formatter và tích hợp W4 thuộc các task tiếp theo.

## 9. Phạm vi triển khai W3-06..08

`select_prior_tasks(...)` có cùng query signature, trả đúng `tasks`,
`regime_population`, `metadata`: task đã chọn, population PIT để tính stats sau,
và metadata chọn đầy đủ. Cả bốn mode hoạt động với K>0;
K=0 hoạt động với mọi mode sau validation.
Không dùng kết quả chọn thay result retrieve vì chưa có trường stats đã tính.
Recent/Random không phụ thuộc current_regime hoặc signals để ranking; population
vẫn cùng regime query theo hợp đồng thống kê. Effective seed Random K>0 kể cả
empty là hex digest đúng policy; Recent/Similarity/Bayesian/K=0 dùng None.
Similarity trả score float theo `signal_match_v1` trong metadata, dùng toàn pool
eligible cùng scope và không lọc regime. Giữ nguyên tín hiệu thô của task đã chọn;
chỉ bản sao chuẩn hóa tham gia tính điểm. Sentiment vẫn được kiểm alias dù trọng số 0.

Bayesian dùng `regime_population` đã lọc PIT/scope/cùng regime trước ranking,
rồi gọi cùng `_select_similarity()` và chốt hậu điều kiện. Không có threshold,
không bù từ regime hoặc mã khác; thiếu K trả partial/insufficient_candidates.
Pool chung rỗng trả empty/no_eligible_history; pool chung có record nhưng không
có regime phù hợp trả empty/no_matching_regime. `candidate_count` bằng
`matched_regime_count`, độc lập với K. Score không phải xác suất thắng; thống kê
thực nghiệm và result retrieve K>0 được tích hợp ở W3-09.

## 10. Phạm vi triển khai W3-09 — API đầy đủ của Phase B

`retrieve(...)` gọi bước chọn một lần, rồi tính stats trên toàn `regime_population`;
không dựng lại pool, không đọc lại file/giá và không tính lại P&L. K>0 trả đúng ba
trường `tasks`, `stats`, `metadata`; K=0 trả tasks rỗng/stats None và metadata disabled,
không gọi eligible hoặc tính stats. `prepare_query` và `select_prior_tasks` vẫn là
hai API trung gian riêng, không thay cho result retrieve.

`_compute_statistics` kiểm lại population nguyên bản/PIT/scope/regime/ID trước
aggregation, dùng nhãn WIN/LOSS đã xác minh và bullish chuẩn hóa theo policy/W2.
Trap là union Trend/Pattern bullish và LOSS, kiểm đúng với was_bull_trap từng record.
Count population phải bằng matched_regime_count; sai quan hệ ném ValueError.
Stats giống nhau giữa bốn mode/K=1..3 nếu cùng query/cutoff/scope/regime, không smoothing.
Pool rỗng hoặc regime không có mẫu vẫn trả stats object với 0/0/None cho bốn metric;
nhánh đối chứng có thể có tasks khác regime trong khi population stats rỗng.

[Receipt runtime](statistics_runtime_review.json) đối chiếu kho thật và counts/mẫu số;
chưa là phép đo p95, formatter BRPP hoặc kết quả giao dịch OOS.

## 11. Formatter W3-10

Hàm module `format_compact_prior_prefix(tasks, stats) -> str` nhận hai trường của
result retrieve, theo [hợp đồng BRPP](statistics_and_prefix_contract.md).
[]/None trả rỗng; stats object luôn render khối thống kê, kể cả tasks rỗng/n=0.
Task giữ thứ tự, ngày quyết định và regime riêng; n là population, k là số ví dụ.
Schema/nhãn/counts/ID sai hoặc prefix vượt 600 gây ValueError; không đọc giá/P&L.
Chữ ký không có query cutoff, nên trách nhiệm PIT/provenance vẫn thuộc retriever/caller.
V1 dùng câu S=thiếu tin cho kho đã phát hành; task sentiment ngoài NEUTRAL/alias
cần phiên bản mới. [Receipt formatter](prefix_formatter_review.json) kiểm fixture;
[receipt W3-11](prompt_budget_review.json) kiểm suite/prompt ghép offline. Cap báo
cáo hiện tại tổng 4.500 cho prompt ghép bão hòa VI/EN 6.565/6.582, không đạt
`<6500`. Cap bàn giao tổng 4.000 dự phòng BRPP đủ 600 cho prompt tối đa 6.289;
W4 phải áp dụng cap đã kiểm và guard prompt cuối sau mọi hướng dẫn thêm vào.
Runtime Decision chưa thay đổi; smoke kho thật W3-12 còn pending.
