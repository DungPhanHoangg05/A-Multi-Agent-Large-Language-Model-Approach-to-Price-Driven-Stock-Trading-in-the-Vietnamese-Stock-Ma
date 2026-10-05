# Hợp đồng provenance và point-in-time

**W4-03 — đặc tả khóa ngày 05/10/2026.** Phiên bản
`prior_provenance_v1`, thuộc [hợp đồng tích hợp v1](integration_contract.md).
Đây là đầu vào cho adapter W4-09 và bộ kiểm leakage W4-13; chưa cài validator
hay provider runtime mới. [Policy](provenance_policy.json),
[ví dụ và ca biên](provenance_examples.json), [biên bản](provenance_review.json).

## 1. Ranh giới và trách nhiệm

Caller cung cấp provider/model độc lập với tám key `prior_config` đã khóa.
Provider được khởi tạo và kiểm nguồn một lần trước vòng chạy; không truyền
đối tượng provider, DataFrame, model hoặc API key vào JSON provenance.
`prior_provenance` là bằng chứng để adapter đối chiếu với dữ liệu thật,
không phải lời khai mà adapter tin chỉ vì có hash hoặc cờ PASS.

| Thành phần | Nguồn / kiểm tra tái sử dụng | Trách nhiệm bổ sung khi triển khai |
| --- | --- | --- |
| Caller / price loader | `load_verified_execution_data`, manifest giá, evidence VCI, sự kiện quyền | Kiểm symbol, nguồn, đơn vị, schema, hash và phạm vi gate trước upstream; chỉ đưa snapshot PIT vào graph |
| Price snapshot | `raw_point_in_time_snapshot`, `validate_raw_frame`, `snapshot_payload` | Caller cắt archive; adapter từ chối snapshot đã nhận còn nến tương lai, lệch ngày, sai window/hash |
| News provider | `FrozenSentimentSnapshot`, `SentimentCache.get_at(strict_research_mode=True)` | Nạp cache đã đóng băng; lọc ngày/cửa sổ, ghi coverage; không gọi `preload()` để crawl khi cache chưa nạp |
| Replay regime | `PrefixRegimeProvider.get(cutoff, verify_only=True)` và `_validate_regime` của runner | Đối chiếu proof với artifact đúng ngày và archive VNINDEX; luôn bật `verify_only` |
| Fixed model OOS | `MarketRegimeDetector.load`, `classify_regime`, `build_regime_features`, `training_data_hash` | Provider mới kiểm biên đóng băng và hash toàn bộ prefix train; không áp điều kiện train-end bằng cutoff của replay |
| Shared Full / signals | `report_signal`, `normalize_signals`, signal journal và `validate_source` của smoke W3 | Kiểm hash/config/source của replay; fresh chạy Indicator→Pattern→Trend và Alpha/Sentiment đúng một lần, không gọi extractor để bù archive thiếu |
| Retriever | `BayesianPriorRetriever` constructor, `prepare_query`, `_assert_pool`, `retrieve` | Nạp bank/manifest/audit một lần; query chỉ nhận whitelist, giữ mọi metadata W3 |
| Formatter / Decision | `format_compact_prior_prefix`, distill/cap và retry wrapper hiện có | Chỉ chạy sau các hậu điều kiện PIT; W4-06/07 bổ sung guard cuối BRPP≤600 và prompt<6.500 |
| Evaluator / checkpoint | `compute_round_trip_net_return`, journal nguyên tử hiện có | Outcome test point chỉ ở evaluator; W4-04 khóa schema/signature/resume, W4-12 cài đặt |

Tái sử dụng validator không đồng nghĩa đã có validator tích hợp. Ví dụ
`validate_regime_state` chỉ kiểm state bảy trường; `_validate_regime` kiểm
ngày prefix nhưng không tự nạp artifact; `validate_source` của smoke cần
episode lịch sử và chưa là API adapter fresh/OOS. `raw_point_in_time_snapshot`
có chủ đích cắt archive; adapter phải phát hiện nến tương lai trong snapshot
được caller khai là PIT, không cắt lần nữa để che vi phạm.

## 2. Dạng `prior_provenance`

Enabled, kể cả Original K=0, bắt buộc có object với **đúng bảy key**:
`contract_version`, `context`, `prices`, `news`, `regime`, `signals`, `bank`.
Flag off giữ sentinel `None` theo W4-02 và không I/O nguồn mới.
Mọi trường dùng JSON gốc, số hữu hạn, ngày ISO EOD không giờ/múi giờ,
SHA-256 lowercase 64 ký tự. Key thừa hoặc thiếu bị `ValueError`.
Các key object con và ví dụ thật được ghi trong policy/examples.

Trường `*_rows`, `*_count`, `window_size`, `window_days`, `min_articles` là
`int` gốc (không nhận bool), counts không âm, rows/window dương.
`is_reliable` là bool gốc; schema/providers là list[str] đúng thứ tự đã khóa.
Mọi `*_sha256` là str; `*_path` là str theo policy đường dẫn; mọi `*_date`
là ngày ISO hợp lệ hoặc `None` tại đúng các field nullable trong policy.
`metadata`, `models`, `runtime`, `code_sha256`, `versions` giữ đầy đủ object
của nguồn tạo đã xác minh; không chấp nhận map tùy ý chỉ vì serialize được.
`signals` có origin checkpoint thì path/hash đều bắt buộc; origin shared fresh
thì cả hai là `None`. `frozen_model` chỉ bắt buộc cho fixed-model OOS.

| Object | Nội dung bắt buộc / ràng buộc |
| --- | --- |
| `context` | `symbol`, `as_of_date`, `time_frame="1d"`, `provider_mode` (`historical_prefix` hoặc `fixed_train_oos`); trùng state/caller, không lấy ngày cuối cũ làm ngày query mới |
| `prices` | Nguồn vnstock/VCI, crosscheck VCI/KBS; version đúng manifest, basis `UNADJUSTED_EXECUTION`, unit `thousand_VND`; manifest/CSV/evidence/events path và hash; schema OHLCV; snapshot/window/alpha-prefix hash, số hàng và endpoints |
| `news` | Path/hash snapshot tin đã đóng băng; hash toàn danh sách nguồn và danh sách visible có thứ tự; input/visible counts, số loại undated/future/outside-window; coverage, window=90, min_articles=3, reliability, model_used, neutral_reason |
| `regime` | VNINDEX manifest/CSV hash; hash prefix suy luận và feature; path/hash artifact; metadata đầy đủ từ loader, hash state; dates HMM/scaler/calibration; bằng chứng đóng băng OOS hoặc `None` cho replay |
| `signals` | Origin (`historical_signal_checkpoint` hoặc `shared_full`), checkpoint path/hash hoặc `None`; hash reports/năm tín hiệu chuẩn hóa/config; model config, runtime, code hashes của bên tạo báo cáo |
| `bank` | Ba path/hash bank/manifest/audit từ config đã chuẩn hóa; versions W3 từ constructor/metadata; không sao chép record outcome của query vào đây |

Path phải repo-relative POSIX, không `..`, URL/drive/UNC, backslash hay symlink
thoát repo. Nguồn ngoài repo phải được đóng băng vào vùng local của run trước
khi bắt đầu; không chứa credentials. Path archive trong ví dụ là tham chiếu
local (gitignored), không yêu cầu đẩy 852 journal lên Git.

Provenance ở state/checkpoint phục vụ kiểm toán; **không chèn vào prompt**.
Metadata nguồn toàn archive (kể cả hash hoặc số tin bị loại tương lai) chỉ dùng
định danh nguồn/resume; không dùng làm feature, ranking, stats hoặc nội dung
agent. State cho mỗi branch được deep-copy sau kiểm chứng; không đổi proof
bằng cách sửa nhãn regime hay cutoff trực tiếp.

## 3. Giá và đặc trưng tại ngày quyết định

- Nguồn hệ thống chỉ vnstock/VCI và vnstock/KBS. Bộ thực thi đã xác minh hiện
  dùng trường thô VCI làm primary, KBS để crosscheck; không tự thay KBS thành
  nguồn giá thực thi nếu chưa có evidence/normalizer/gate tương ứng.
- Nạp manifest PASS, hash CSV/evidence/events, tái dựng trường giá và đối chiếu
  bằng loader hiện có. OHLCV cho agent theo thứ tự
  `Datetime, Open, High, Low, Close, Volume`; bỏ `Reference/MatchPrice` khỏi
  agent snapshot nhưng giữ evidence/events hash cho evaluator.
- Snapshot không rỗng, ngày phiên duy nhất tăng dần/EOD, OHLC hợp lệ, finite;
  **max date = cutoff**, không có nến >cutoff. DataFrame attrs không đủ chứng
  minh symbol: phải đối chiếu item manifest/evidence và caller.
- Window vision là `snapshot.tail(window_size)` theo config chung, hash riêng;
  endpoint=cutoff. Alpha dùng prefix đã cắt, tối thiểu 600 nến; ở đường W2
  dùng tail 600, endpoints/hash ghi riêng. Mọi IC, normalization, lựa chọn
  factor và target dùng để ước lượng Alpha phải hoàn tất trong prefix đó;
  không truyền giá ngoài prefix cho Alpha để tính hiệu quả.
- Thống kê/features phải tính trên snapshot đã kiểm, không tính trên full
  archive rồi cắt output. Artifact feature có sẵn phải chứng minh input hash,
  config/code và endpoint; chỉ khai `feature_end_date` không đủ.
- Hash snapshot/window/alpha dùng `digest(snapshot_payload(frame))` hiện có.
  Fingerprint nguồn kết hợp symbol, timeframe, basis/unit, schema, version,
  manifest/CSV/evidence/events hashes; toàn bộ nhóm `prices` tham gia identity
  W4-04. Không dùng hash CSV đơn lẻ thay bằng chứng PIT.

Gate giá hiện chỉ phủ 2018–2022. CSV tín hiệu W1 kéo dài đến 2025 không là
evidence giá thực thi 2023–2024. Không nâng gate OOS bằng cách đổi chữ PASS
trong provenance. Gate đầy đủ dữ liệu phải được caller kiểm **trước upstream**.

## 4. Tin và coverage

Nguồn tin là snapshot scored đã nạp/đóng băng, đúng symbol. Provider phân loại
từng bài theo thứ tự: thiếu ngày → loại `undated`; có ngày sai ISO → lỗi nguồn;
ngày >cutoff → loại `future`; quá 90 ngày → loại `outside_window`; còn lại visible.
Bài đúng cutoff và đúng cutoff−90 ngày được giữ. Không lấy tin không ngày
hoặc tin tương lai để đủ ba bài. Bài nguồn tương lai bị lọc là bình thường;
**bài tương lai/không ngày trong output đã khai visible là vi phạm**, phải lỗi.
`FrozenSentimentSnapshot` từ chối ngày sai; `SentimentCache.get_at` hiện bỏ ngày
không parse được. Adapter W4-09 dùng kiểm nguồn strict trước cache, không dựa
vào việc cache bỏ qua lỗi để cấp proof hợp lệ.

Visible sắp giảm dần theo `(date_parsed, digest(article))` như snapshot W2;
hash/count tính trên **toàn bộ visible**, không trên `scored_articles[:15]`
được cache trả để hiển thị. Tổng input bằng visible cộng ba nhóm loại;
coverage min/max là `None` khi rỗng. Tất cả bài visible phải có nhãn/score
hợp lệ; đối chiếu `cutoff_date`, symbol, `n_articles_used`, `is_reliable`.

Khi visible<3: sentiment `NEUTRAL`, avg_score=0, reliability=false,
model_used=`neutral-insufficient-dated-history`, neutral_reason=
`INSUFFICIENT_DATED_HISTORY`. Giữ bài hợp lệ để audit, không đưa các nhãn
thưa vào Decision; không gọi sentiment LLM để lấp dữ liệu. Khi visible≥3:
model_used=`cached-historical`, reliability=true, neutral_reason=`None`;
sentiment vẫn có thể NEUTRAL nếu tổng hợp trung tính. Cache malformed/saihash
phải lỗi; caller muốn nguồn tin rỗng hợp lệ phải tạo snapshot rỗng rõ ràng và
ghi hash trước run, không biến lỗi đọc file thành rỗng.

## 5. Regime: hai provider có điều kiện riêng

State bằng `market_regime`, kiểm bảy field theo schema W1; source=VNINDEX,
as_of=cutoff, feature_end≤cutoff. Với daily query yêu cầu có phiên VNINDEX
tại cutoff nên **feature_end=cutoff**. Metadata/artifact phải được loader
xác minh trước classify; hash state chỉ ràng buộc với state, không thay
việc tính lại state từ artifact/prefix khi xác minh replay.

| Điều kiện | `historical_prefix` | `fixed_train_oos` |
| --- | --- | --- |
| Khoảng train | train_start≤train_end=cutoff | train_start≤train_end<cutoff |
| HMM/scaler/calibration | Cùng một artifact, ba end dates bằng metadata.train_end | Cùng một artifact đóng băng; ba end dates bằng metadata.train_end |
| Provider | Prefix ngày đó, `get(..., verify_only=True)` | Nạp artifact một lần, classify prefix PIT trên RAM, không fit/update |
| Đóng băng | `frozen_model=None` | `freeze_as_of_date`, artifact SHA và training-data SHA; train_end≤freeze_as_of_date<cutoff, cố định trước query đầu |
| Hash train | `training_data_hash(prefix)` bằng metadata | Prefix [train_start,train_end] trong lịch sử suy luận phải nguyên vẹn, cùng số hàng/endpoints/hash đã train |
| Tái sử dụng | `_validate_regime` + so proof với provider thật | Validator ngày riêng; không gọi `_validate_regime` lịch sử để áp equality |

VNINDEX input giữ toàn bộ prefix từ train_start đến cutoff, không chỉ tail
200: `classify_regime` cần xác minh toàn prefix train. Hash prefix suy luận
bằng `training_data_hash`; feature hash dùng `digest` trên object gồm
Datetime ISO và năm `FEATURE_COLUMNS` float nguyên bản theo thứ tự hiện có.
Input có nến tương lai/sai ngày/thiếu train-prefix phải lỗi trước classify.

Model, scaler, mapping latent, volatility quantiles, trend threshold và
fallback MULTI_FACTOR nằm trong cùng envelope. Artifact SHA phải khớp byte,
payload hash phải khớp thuật toán **`_payload_hash` của regime_detector**;
không dùng `_read_envelope` journal vì cách canonical JSON khác. Kiểm
parameters, runtime versions, finite arrays, calibration và source bằng
`MarketRegimeDetector.load` / `_validate_fitted`. Nếu có artifact tách rời
component trong tương lai phải version hợp đồng; không tự điền dates chung
cho một component chưa chứng minh nguồn.

Model full-train hiện tại kết thúc 2022-12-30, `price_basis_status=UNVERIFIED`,
`artifact_purpose=RESEARCH_ONLY`. Có thể dùng để probe kỹ thuật classify
PIT trên archive local; **không phải chứng nhận OOS trading**. Cấm dùng model
này cho query trước 2022-12-30. Ngày bằng train_end được detector hỗ trợ về
mặt kỹ thuật nhưng **không là OOS**, provider OOS từ chối equality.
Provider replay thiếu/corrupt artifact phải dừng; không chuyển sang full-model,
fit, tải dữ liệu hoặc sửa calibration trong query.
Provider prefix được phép đọc artifact đúng ngày trong bước kiểm nguồn trước
upstream và cache kết quả đã xác minh. `query_network_or_fit_or_json_io=false`
trong policy chỉ lời gọi retriever sau khi hoàn tất nguồn; không cấm đọc
artifact để chứng minh provenance trước lời gọi đó.

## 6. Báo cáo, tín hiệu và outcome

Sau nguồn PIT hợp lệ, Full shared có năm report không rỗng cùng cutoff:
Indicator/Pattern/Trend, Alpha và Sentiment. Chuẩn hóa đủ năm tín hiệu theo
`normalize_signals`, đối chiếu ba report directions, đồng thuận năm Alpha
factor và sentiment PIT. `reports_sha256`, `signals_sha256` cùng cấu hình/model/
code identity ràng buộc với kết quả shared; hash đúng nhưng input nguồn sai
vẫn bị từ chối. Checkpoint lịch sử phải COMPLETE, envelope/signature/source
khớp episode; tín hiệu replay giữ identity **lúc tạo**, không giả thành code/
model hiện tại. Shared fresh ghi identity thực chạy; cache khác context/config
không được tái sử dụng chỉ vì nhãn trùng.

Whitelist kwargs `retrieve`: symbol, as_of_date, current_regime (lấy từ state),
current_signals, mode, k, seed, scope. Không truyền `prior_provenance` trực tiếp
vào retriever. Các field `actual_direction`, `entry_date`, `exit_date`,
`entry_open`, `exit_close`, `net_return`, `outcome`, future prices của **test
point** bị cấm ở query/provenance/shared agent state. Historical task đã đóng
có outcome/entry/exit là nội dung hợp lệ của prior, sau lọc nghiêm ngặt.
Evaluator có thể tính nhãn riêng nhưng không nối ngược vào graph/signals.
Outcome dùng đúng engine Open(t+1)→Close(t+3), SHORT cash, phí hai chiều.

## 7. Trình tự kiểm chứng và điểm dừng

1. **Run init:** normalize config, kiểm Full/backtest/daily, nạp và xác minh
   nguồn giá/tin/model và bank; cấu hình disabled đi đường legacy theo W4-02.
2. **Trước upstream:** caller cắt nguồn; adapter kiểm snapshot/window/Alpha,
   visible tin, proof regime/state/hash và phạm vi gate; lập nguồn provenance.
   Lỗi ở bước này không gọi upstream, retriever, formatter hay Decision API.
3. **Shared preparation:** ba upstream một lần, Full Alpha/Sentiment một lần
   hoặc đọc shared đã xác minh; xác minh report/signal binding, hoàn tất
   provenance. Lỗi signals không gọi retriever/formatter/Decision API.
4. **Per branch:** deep-copy shared/proof; `retrieve` trên bank đã nạp; Original
   K=0 vẫn kiểm context/signals rồi nhận metadata disabled/k_zero của W3.
5. **Hậu điều kiện:** mọi prior exit<cutoff; population stats cùng scope/cutoff/
   regime, không dùng riêng K; giữ selection/counts/status/versions W3.
   Lỗi pool/metadata phải dừng trước formatter và Decision API.
6. **BRPP → Decision:** formatter từ tasks/stats đã kiểm; guard≤600, distill/cap,
   guard cuối<6.500, gọi qua retry wrapper. Không thêm proof/outcome vào prompt.
7. **Evaluator/checkpoint:** chấm quyết định ngoài agent input; lưu theo hợp
   đồng W4-04. Không đánh dấu complete hoặc tự tạo fallback khi lỗi nguồn.

`exit_date == cutoff` bị loại khỏi pool/stats/K như mọi prior chưa đủ điều kiện;
đây là lọc eligibility bình thường, không là lỗi bank. Nếu prior bằng/sau cutoff
lọt qua vào pool/selection/stats thì hậu điều kiện ném `ValueError/AssertionError`.
Empty/partial hợp lệ giữ stats và metadata, không đổi sang disabled.
Vi phạm schema/nguồn/cutoff ném `ValueError` hoặc `AssertionError`;
`FileNotFoundError/OSError` giữ nguyên khi đọc nguồn. Không catch rộng rồi
trả NEUTRAL/empty. Quota/transient API theo wrapper/checkpoint, không biến
thành tín hiệu hay quyết định giả.

## 8. Kiểm chứng và phần còn mở

Đối chiếu nguồn thật: FPT/MWG/VCB/VNM ngày 2022-12-27 và FPT ngày 2020-06-04.
Hai context FPT có projection đầy đủ `prior_provenance`; ba mã còn lại có
hash và biên bản binding nguồn. Tổng **14 probe API hiện có PASS**:

| Ca biên / lỗi | Kết quả thực tế |
| --- | --- |
| Snapshot thiếu nến cutoff | `raw_point_in_time_snapshot` → ValueError |
| Feature chứa nến tương lai / feature-end tương lai | `build_regime_features` / validator state → ValueError |
| Model train tương lai / replay train-end cũ / state khác cutoff | Validator proof prefix → ValueError (ba probe) |
| Tin tương lai trong proof visible | `validate_source` → ValueError |
| Thiếu prefix artifact readonly | `PrefixRegimeProvider.get(..., verify_only=True)` → ValueError; không tạo thư mục/model |
| Full-train dùng cho query sớm | `classify_regime` → ValueError |
| Prefix train bị thay / artifact sai hash | `classify_regime` / `load` → ValueError |
| Ngày tin không parse được | `FrozenSentimentSnapshot` → ValueError |
| Tin đúng cutoff/đúng biên 90 ngày; future/undated/quá cửa sổ | Chỉ giữ hai bài hợp lệ, NEUTRAL và unreliable |
| Prior exit bằng cutoff | Bị loại khỏi pool và stats của cả bốn mode; stats giữa các mode bằng nhau, query không I/O |

Probe fixed-model classify tại 2023-01-10 giữ nguyên metadata; chỉ kiểm khả
năng suy luận PIT từ archive, không xác minh giá thực thi hay kết quả trading.
Mẫu freeze date trong ví dụ là đặc tả, không phải bằng chứng đã đóng băng
model vào ngày lịch sử đó. 14 ca adapter mới trong examples **chưa thực thi**.

Gate chạy mới: compileall PASS; **339 unit PASS (48,126 giây)**,
**E2E xác định PASS (pipeline 7,0 giây)**, **56 leakage PASS (5,077 giây)**.
Receipt ghi lệnh, thời gian process, log/hash; 2.308 file nguồn/bằng chứng và
archive giữ nguyên hash trước/sau gate. Các gate hồi quy hiện tại không
nghiệm thu adapter hay năm branch runtime chưa triển khai.

Biên bản phân biệt **probe validator hiện có** và **ca đặc tả chờ adapter**.
Ví dụ replay có giá/tin/artifact/signal thật từ archive local; probe fixed-model
chỉ kiểm kỹ thuật, không dùng giá OOS để giao dịch. Ca news synthetic chỉ là
fixture lọc ngày, không là bài báo nghiên cứu. Bốn gate chạy mới theo AGENTS.

W4-03 hoàn thành khi policy/shape, hai provider, trách nhiệm, trình tự và các
ca bằng ngày/tương lai/thiếu ngày/snapshot lệch/model corrupt có bằng chứng
đối chiếu. W4-04 tiếp tục khóa schema/signature/checkpoint. **Gate A vẫn mở**;
provider OOS runtime, adapter tích hợp, call-count và guard thực chạy chưa PASS.
