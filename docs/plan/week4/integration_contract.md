# Hợp đồng state/config tích hợp prior — phiên bản 1

**W4-02 chốt ngày 05/10/2026 trên baseline `62a673a`.** Đây là đặc tả cho
W4-05..12, chưa cài parser/validator hoặc thay runtime. Đầu vào:
[W4-01](input_readiness.md), [API W3](../week3/retriever_api_contract.md),
[policy thống kê/BRPP](../week3/statistics_and_prefix_contract.md).
Policy máy đọc: [integration_policy.json](integration_policy.json);
ví dụ: [integration_examples.json](integration_examples.json);
kiểm chứng: [state_config_review.json](state_config_review.json).

W4-03 sẽ chốt nội dung/proof provenance và thứ tự PIT; W4-04 chốt schema
checkpoint. Các phần đó chưa được nghiệm thu chỉ vì state có trường để chứa chúng.

## 1. Cấu hình vào và cấu hình chuẩn hóa

Tham số mới là **`prior_config`**, tách khỏi `ablation_config`. Không thêm cờ
prior vào `ABLATION_CONFIGS`, không đổi nghĩa `include_alpha`. Config chuẩn hóa
có đúng tám key dưới đây; input `None` hoặc dict một phần được bổ sung default.
Dict input thừa key hoặc sai kiểu bị từ chối; không sửa object người gọi.

| Key | Kiểu Python gốc | Default | Validation |
| --- | --- | --- | --- |
| `enable_bayesian_prior` | bool | false | `type(value) is bool`; không nhận 0/1/chuỗi |
| `mode` | str | `bayesian_regime` | Đúng `bayesian_regime`, `random`, `recent`, `similarity` |
| `k` | int | 3 | 0..3; bool/float/NumPy scalar không hợp lệ |
| `seed` | int | 42 | 0..2^32−1; không bool/float/NumPy scalar |
| `scope` | str | `same_symbol` | Đúng `same_symbol` hoặc `pooled`; không fallback |
| `bank_path` | str | `data_manager/regime_memory_store.json` | Chuỗi tương đối repo root, không rỗng |
| `manifest_path` | str | `data_manager/regime_memory_store.manifest.json` | Như bank_path |
| `audit_path` | str | `docs/plan/week2/memory_bank_audit.json` | Như bank_path |

Path config v1 dùng dấu `/`, không URL, drive/UNC, dấu gạch chéo ngược, segment `.`/`..`
hoặc đường dẫn tuyệt đối. Khi bật, resolve từ repo root rồi xác minh vẫn trong
repo kể cả symlink; file tồn tại/đọc được và bank/manifest/QA/schema khớp nhau.
Không giả định ba path có cùng thư mục hoặc tên file tương ứng là đủ chứng minh.
`BayesianPriorRetriever` vẫn nhận `Path` ở API độc lập W3; giới hạn chuỗi tương
đối chỉ áp dụng cấu hình runtime mới để checkpoint tái lập giữa các máy.

Khi tắt, vẫn kiểm kiểu/enum/range/cú pháp các key được truyền nhưng **không
resolve filesystem, đọc kho hoặc đòi model/provenance mới**. Vì vậy config
disabled với path hợp lệ nhưng file chưa tồn tại là hợp lệ; config disabled
với `k=true` hoặc mode sai vẫn lỗi. Không dùng `bool("false")`, int coercion,
uppercase/trim enum hoặc tự clamp K để hợp thức hóa input.

```json
{
  "enable_bayesian_prior": false,
  "mode": "bayesian_regime",
  "k": 3,
  "seed": 42,
  "scope": "same_symbol",
  "bank_path": "data_manager/regime_memory_store.json",
  "manifest_path": "data_manager/regime_memory_store.manifest.json",
  "audit_path": "docs/plan/week2/memory_bank_audit.json"
}
```

Version contract là `prior_runtime_contract_v1` trong policy/receipt/signature
tích hợp; không thêm key version vào tám key config hoặc sửa metadata version W3.

## 2. Flag tắt, Original và ma trận năm nhánh

| Trường hợp | Flag | Mode/K | Trách nhiệm |
| --- | --- | --- | --- |
| Legacy (không truyền config, None hoặc flag false) | false | Default hoặc giá trị hợp lệ đã truyền | Không query prior, không yêu cầu kho/regime proof; giữ đường graph/output cũ |
| Original nghiên cứu | true | `bayesian_regime`, K=0 | Cùng context/Full reports; validate query và gọi retriever K=0; tasks=[], stats=None, prefix rỗng |
| Random | true | `random`, K=3 | Chọn từ pool PIT theo scope, stats cùng population regime |
| Recent | true | `recent`, K=3 | Như policy W3 |
| Similarity | true | `similarity`, K=3 | Như policy W3 |
| Bayesian | true | `bayesian_regime`, K=3 | Task cùng regime, ranking theo policy W3 |

Ma trận chuẩn có thứ tự `original`, `random`, `recent`, `similarity`, `bayesian`
(branch ID chữ thường). K=3/seed=42/same_symbol được đóng băng cho ma trận này;
runner không tự thay K/scope/seed sau khi nhìn outcome. API cấu hình một nhánh
vẫn nhận K=0..3, seed hợp lệ và pooled tường minh cho thí nghiệm riêng; không
gắn tên ma trận chuẩn vào một cấu hình đã đổi. Thay đổi cấu hình phải có signature
mới theo W4-04, không resume ghi đè vào run cũ.

**K=0 không đồng nghĩa tắt flag.** Trong ma trận, retriever đã được khởi tạo và
xác minh kho một lần cho cả run, kể cả Original. K=0 ở mode khác vẫn hợp lệ với
API đơn nhánh, nhưng không được tự đặt branch ID Original chuẩn của ma trận.

## 3. Tương tác với ablation và entry point cũ

- Prior disabled: giữ nguyên bốn ablation `full`, `alpha_only`, `sentiment_only`,
  `baseline`, xử lý config và `include_alpha` của legacy. Không siết parser cũ
  sang kiểu mới trong task prior, không đổi nhánh `no_alpha` từ baseline sang
  sentiment_only.
- Prior enabled: chỉ chấp nhận cấu hình ablation chuẩn **full**, hai cờ phải là
  bool Python `true`. `include_alpha=None/True` ánh xạ Full theo quy tắc cũ;
  `include_alpha=False` hoặc non-bool tường minh bị ValueError. Truyền đồng thời
  include_alpha và ablation_config vẫn lỗi như legacy.
- Enabled với alpha_only/sentiment_only/baseline/custom/extra ablation key bị
  ValueError trước init retriever/graph/API. Không tự bật lại module bị tắt,
  bỏ prior hoặc chạy 4×5 tổ hợp.
- Số/chuỗi đóng vai cờ Alpha/Sentiment chỉ được giữ theo semantics cũ trên
  đường disabled. Đường nghiên cứu enabled kiểm strict bool trước gọi resolver
  hiện có, tránh `bool("false")` biến thành Full.
- Tên/signature/return và callback của entry point cũ giữ tương thích. Tham số
  prior mới được thêm theo tên; không thay vị trí tham số cũ hoặc đổi tuple
  `_run_paired_point()` để chứa năm nhánh.
- Adapter nghiên cứu triển khai trong W4 backtest; live graph enabled chưa có
  contract nguồn live PIT ở W4, phải từ chối rõ. Live/legacy với flag false giữ
  hành vi cũ; thêm typed fields không có nghĩa bật prior trong web.

Đường enabled dùng toàn bộ Full reports đã chuẩn bị một lần. Mỗi nhánh nhận
bản sao sâu riêng. Chỉ Decision được gọi riêng; giữ wrapper retry/pacing hiện có.

## 4. State mới và một nguồn dữ liệu thống nhất

Các trường mới là optional/`NotRequired` ở schema base và schema graph thực tế,
để state legacy không cần thêm key. Tại biên chuẩn bị/Decision nghiên cứu, các
trường cần thiết trở thành **bắt buộc theo giai đoạn**, không dựa vào TypedDict
để thay validation runtime. Không đổi kiểu các field legacy trong W4-05.

| Field state | Kiểu đã khóa | Mặc định khi không có prior | Tác giả / thời điểm bắt buộc |
| --- | --- | --- | --- |
| `prior_config` | dict tám key ở §1 | Cấu hình disabled chuẩn hóa | Parser cấu hình; bắt buộc ở đường mới |
| `market_regime` | MarketRegimeState hoặc None | None | Provider context; trước query enabled |
| `current_signals` | dict năm nhãn chuẩn hoặc None | None | Bộ trích tín hiệu Full; trước query enabled |
| `prior_provenance` | dict JSON hoặc None | None | Caller/provider; nội dung bắt buộc chốt W4-03 |
| `prior_tasks` | list[HistoricalTaskRecord] | [] | Chỉ từ `retrieve().tasks`, trước Decision enabled |
| `prior_stats` | stats W3 hoặc None | None | Chỉ từ `retrieve().stats`, không tính từ selected K |
| `prior_metadata` | metadata W3 hoặc None | None | Chỉ từ `retrieve().metadata`, trước Decision enabled kể cả K=0 |
| `bayesian_prior_context` | str BRPP | Chuỗi rỗng | Chỉ từ formatter W3, trước Decision enabled |

Không tạo thêm `current_regime` top-level, `regime_name` top-level,
`selected_ids` top-level hoặc `prior_result` trùng nội dung. Query lấy regime
từ `market_regime.regime_name`; IDs/scores/status chỉ nằm trong prior_metadata.
Stats không nhét vào `bayesian_prior_context` dưới dạng dict; field này là chuỗi.
`market_regime` chính là state bảy trường W1, không bọc thêm metadata model ở đây.
Model/source proof thuộc prior_provenance theo W4-03.
Provider/model path được caller cung cấp độc lập theo hợp đồng W4-03, không thêm
model path hoặc đối tượng provider vào tám key `prior_config` đã khóa.

### MarketRegimeState và query

- Có đúng as_of_date, regime_id, regime_name, volatility_level, trend_strength,
  source_symbol, feature_end_date. Dùng `validate_regime_state()` hiện có.
- regime_id cố định theo tên: BULL=0, BEAR=1, CHOPPY=2, CONSOLIDATION=3;
  source_symbol=VNINDEX, volatility LOW/MEDIUM/HIGH, trend_strength hữu hạn ≥0.
- State ngày ISO đúng query; feature_end_date ≤as_of_date. Chuỗi enum hợp lệ
  chưa là proof nguồn; enabled thiếu proof hợp lệ phải bị chặn theo W4-03.
- Symbol query chỉ FPT/MWG/VCB/VNM, str Python gốc đúng case; không lấy từ nhãn
  outcome. Dùng stock_name là symbol str ở đường nghiên cứu hiện hữu, chưa sửa
  annotation dict cũ trong `IndicatorAgentState`.
- Query `as_of_date` là str YYYY-MM-DD. Adapter có thể chuyển Timestamp EOD
  không timezone từ snapshot nội bộ sang ISO sau xác minh; không nhận datetime
  có giờ/timezone hoặc tự cắt giờ của config/query do caller truyền.
- `current_signals` có đúng trend/pattern/alpha_consensus/indicator_consensus/
  sentiment, chuẩn hóa bằng `normalize_signals()` W3 trên bản sao. State chuẩn
  dùng BULLISH/BEARISH/NEUTRAL cho bốn kỹ thuật, POSITIVE/NEGATIVE/NEUTRAL cho tin.
  Pipeline nghiên cứu yêu cầu đủ năm signals kể cả Random/Recent/K=0 để mọi
  nhánh có cùng query đã ghi; API retriever độc lập vẫn giữ hỗ trợ None của W3.

### Kết quả trước Decision

`retrieve()` có đúng tasks/stats/metadata; adapter deep-copy ánh xạ vào state
theo bảng, formatter tạo prefix. Điều kiện:

1. Tasks đúng schema, không trùng ID, exit_date <cutoff, số lượng ≤K, đúng
   scope/pool; Bayesian K>0 còn cùng regime. selected_ids/thứ tự/scores/count
   khớp tasks, không sửa record để nhét score.
2. Metadata giữ toàn bộ version/hash/query/counts/effective seed/status/reason
   đã khóa ở W3; query metadata khớp config + market_regime + symbol/cutoff.
3. K=0: tasks=[], stats=None, status=disabled/reason=k_zero; eligible/matched/
   candidate=None, selected_count=0. Prefix rỗng nhưng metadata vẫn tồn tại.
4. K>0: stats object có đúng regime/population_count/metrics; bốn metric có
   numerator/denominator/rate, mẫu số 0 là None, count=matched_regime_count.
   Bốn prior mode cùng context/scope nhận cùng stats, không smoothing.
5. Empty/partial giữ status/reason/counts thật; prefix vẫn có stats kể cả
   tasks=[], population=0. Không tự coi empty là disabled hoặc trả cash fallback.
6. Prefix bằng đúng formatter của tasks/stats, ≤600 ký tự. Không chấp nhận
   prefix caller tự viết hoặc giữ lại prefix nhánh trước. Guard prompt cuối
   <6.500 tại W4-06/07 sau mọi hướng dẫn, trước `_invoke_with_retry`.

Khi flag false, fields mới có thể vắng mặt; nếu caller truyền thì dùng đúng
sentinel của bảng. Non-empty tasks/prefix hoặc stats/metadata/provenance/regime/
signals khác None ở state disabled phải ValueError tại biên mới để phát hiện
state nhánh cũ bị dùng nhầm. Parser không query kho để tự bịa metadata disabled.
Orchestrator tạo state mới/bản sao sạch cho mỗi điểm và nhánh.

## 5. JSON, ownership và dữ liệu cấm

- Config/result/metadata/provenance serializable bằng JSON strict: dict/list/
  str/int/float/bool/None Python gốc, số hữu hạn; không set/tuple/Path/NumPy scalar,
  NaN/Infinity hoặc JSON key trùng. Bool không đóng vai int/rate.
- Adapter trích từ NumPy/Pandas phải ép kiểu Python có kiểm hữu hạn; không dùng
  `to_json_compatible()` để biến NaN thành None cho counts/rates/state bắt buộc
  nhằm che dữ liệu lỗi. Validation input từ caller từ chối kiểu sai, không coercion.
- DataFrame point_in_time_df, sentiment store, LLM/graph và BaseMessage vẫn
  ở state nội bộ legacy; không serialize trực tiếp vào checkpoint JSON. Biên
  checkpoint có projection riêng chốt W4-04, không json.dump toàn LangGraph state.
- Priors được phép chứa outcome **lịch sử đã đóng**. Cấm đưa actual_direction,
  actual_pct_change, entry/exit tương lai, net return hoặc WIN/LOSS của **query**
  vào signals/state/prompt/provenance. Outcome đánh giá nằm ngoài agent input.
- Mỗi branch/result phải sở hữu bản sao sâu task/stats/metadata/provenance/
  reports/messages; mutating một nhánh không đổi branch khác hoặc kho.
- Key/token bí mật không nằm trong prior_config, provenance, metadata hoặc hash
  signature. Đổi API key không đổi định danh thí nghiệm/checkpoint.

## 6. Daily timeframe và horizon

Đường nghiên cứu mới chỉ nhận exact str **`1d` hoặc `1 ngày`**, chuẩn hóa thành
`time_frame="1d"` trước xây state/query/signature; language vi/en chỉ đổi hiển
thị, không đổi logic daily. Horizon luôn lookahead=3 và phí hiện có.

`1 day`, `1D`, chuỗi thừa khoảng trắng, intraday/tuần/tháng hoặc thiếu timeframe
ở biên nghiên cứu bị ValueError trước model/retriever/LLM. Không tự lấy default
`1 day` của BacktestEngine.run() cho nghiên cứu. Wrapper mới phải truyền daily
tường minh. Entry point legacy giữ default/alias cũ khi flag tắt; rủi ro default
đã ghi tại W4-01, không sửa global alias trong task đặc tả.

Đối với persisted query/as_of_date chỉ nhận ISO ngày hợp lệ; ngày thực tế
snapshot, symbol và feature/PIT còn phải được chứng minh theo W4-03.

## 7. Validation và lỗi tại các biên

| Biên | Kiểm bắt buộc | Lỗi / hành vi |
| --- | --- | --- |
| Config | exact type/key/enum/range/path syntax, không mutate | ValueError kể cả flag off và K=0 |
| Mode execution | enabled chỉ Full/backtest/daily; config legacy conflict | ValueError trước tạo graph/retriever/API |
| Khởi tạo enabled | resolved paths/checksum/QA/schema/version đúng | ValueError cho nguồn sai; FileNotFoundError/OSError giữ nguyên; không trả empty |
| Context enabled | symbol/cutoff/7 trường regime/signals và proof W4-03 | ValueError hoặc AssertionError cho invariant; trước retrieve |
| Kết quả | task/stat/metadata khớp query và cutoff | ValueError hoặc AssertionError; không bỏ qua record sai |
| Prefix/Decision | formatter đúng, ≤600; final prompt <6500 | ValueError trước API, không truncate prefix/fallback |
| LLM/output | Retry wrapper/format guard hiện có | Dừng điểm/nhánh với chẩn đoán, checkpoint W4-04/12 không complete |

Validation context và result ở K=0 vẫn chạy phần applicable; kiểm prior cutoff
với list rỗng là rỗng hợp lệ, không phải lý do bỏ kiểm context/QA. Missing lịch
sử hợp lệ là empty/partial; missing/sai artifact là lỗi nguồn.

## 8. Ví dụ và ca nghiệm thu bàn giao

File examples có: defaults/flag off/Original/Bayesian/empty/partial và input sai.
Projection tasks/stats/metadata/prefix được đối chiếu bằng retriever/formatter
thật trên kho đã QA; nguồn context lấy từ receipt W3 có hash được W4-01 xác minh.
Ví dụ empty ở trước kho là fixture có khai báo, không là quan sát thị trường.
Các ví dụ không cấp quyền chạy runtime/OOS vì provenance contract W4-03 chưa chốt.

- W4-05 kiểm default/input partial, wrong/unknown key, bool/int/NumPy, config
  off path không tồn tại, graph không mất field, alias include_alpha và Full only.
- W4-06/07 kiểm Original/empty/partial khác nhau, match metadata/prefix, query
  không chứa outcome, stale state và biên 600/6.499/6.500.
- W4-08..12 kiểm deep-copy, một Full preparation/năm Decision, signature
  config chuẩn hóa, typed state đi qua graph và resume đúng context.
- W4-13..15 kiểm provenance thật, zero-leakage, JSON strict và regression legacy.

**Giới hạn nghiệm thu W4-02:** contract/config/state và ví dụ thống nhất với
W3; chưa PASS validator runtime, Gate A, provider PIT/OOS, cap/guard tích hợp
hoặc checkpoint mới. Điều kiện nguồn chi tiết chuyển W4-03, checkpoint chuyển W4-04.

## 9. Kiểm chứng đặc tả

Trên baseline `62a673a`, đã kiểm **bảy ví dụ config**, **bốn projection** từ
retriever/formatter thật và **bảy probe query sai** với API W3 đã có. Độ dài
prefix Original/Bayesian/empty/partial lần lượt **0 / 338 / 190 / 237** ký tự.
Ví dụ config và các ca tích hợp không tương thích là kỳ vọng bàn giao W4-05,
chưa có parser runtime mới để chạy các ca đó.

Bốn gate mới PASS: compileall; **339/339 unit** (91,391 giây), E2E xác định
**13,8 giây**, **56/56 leakage** (7,637 giây). Lệnh, mã thoát, thời gian tiến
trình và hash log tại [receipt](state_config_review.json). Nguồn, kho/model và
receipt W2/W3/W4-01 giữ nguyên trước/sau kiểm chứng; không gọi API LLM thật.

JSON policy/examples được băm byte nguyên gốc; tài liệu Markdown được băm text
UTF-8 với newline chuẩn hóa qua `read_text()` để hash ổn định khi Git checkout
LF/CRLF. Những hash này ghi trạng thái contract W4-02, không ghi đè receipt trước.
