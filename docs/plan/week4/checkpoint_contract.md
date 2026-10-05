# Hợp đồng kết quả và checkpoint nghiên cứu

**W4-04 — khóa đặc tả, hoàn tất Phase A.** Phiên bản
`prior_research_checkpoint_v1`, identity `prior_run_identity_v1`.
[Schema](research_checkpoint.schema.json), [policy](checkpoint_policy.json),
[ví dụ](checkpoint_examples.json), [receipt/Gate A](checkpoint_review.json).
Kế thừa nguyên trạng [state/config](integration_contract.md) và
[provenance PIT](provenance_contract.md). W4-11/12 triển khai kết quả/resume;
W4-04 chỉ đặc tả, ví dụ và kiểm chứng offline.

## 1. Tách kết quả cũ và nghiên cứu

Flag off giữ `TestPoint`, `BacktestSummary`, callback/web và Full/No-Alpha
hiện tại; không đọc checkpoint nghiên cứu hay đòi nguồn prior mới. Năm nhánh
nghiên cứu có ID cố định `original/random/recent/similarity/bayesian`, cùng
Full reports, K=0/3/3/3/3, seed=42, scope=same_symbol. Không ánh xạ năm nhánh
vào `pred_full/pred_no_alpha`; Original Full không là Baseline cũ.

Đường nghiên cứu đọc schema mới qua reader riêng. File legacy/four-way được
giữ cho reader legacy; **không có migration tự động** sang nghiên cứu vì thiếu
reports/proof/hash cần thiết. Không tự dựng metadata hoặc chạy vision để bù.
Một cấu hình đơn lẻ khác ma trận chuẩn cần version protocol/schema riêng;
schema này nghiệm thu đúng ma trận năm nhánh, không nới W4-02 single-config API.

## 2. File, envelope và chữ ký

```text
outputs/<research-run>/
  run_manifest.json         # identity + kế hoạch điểm, trước mọi API
  run.lock                  # khóa OS giữ bằng handle, không dùng tồn tại file làm khóa
  run.owner.json            # metadata chủ khóa, không tham gia identity
  points/<symbol>-<date>.json
  results.json              # kết quả dẫn xuất, không là nguồn resume
```

Manifest, mỗi point và result dùng `{payload, sha256}`; payload có
`schema_version`, `document_type` (`run_manifest/point_checkpoint/research_result`),
`run_signature`. Schema Draft 2020-12 cung cấp ba nhánh và `$defs`; schema W1
regime/task được resolve **local qua registry**, không truy cập `$id` qua mạng.
JSON reader phải từ chối duplicate key, NaN/Infinity; lớp semantic phải từ
chối NumPy/bool giả int, ngày sai hoặc không EOD trước khi serialize.

Hash mới **`prior_checkpoint_canonical_json_v1`**:
SHA-256 UTF-8 của `json.dumps(value, sort_keys=True, ensure_ascii=False,
separators=(",", ":"), allow_nan=False)`, trên JSON native đã kiểm.
`sha256=hash(payload)`; `run_signature=hash(identity)`.
Không đổi thuật toán digest snapshot/journal W2, training hash hay model
payload hash đã khóa. Hash bytes file và hash text code/newline được phân biệt.
Các path nguồn/provenance/snapshot_ref là repo-relative như W4-03;
`point_files.path` riêng là run-dir-relative. Reader resolve trong đúng root
tương ứng, từ chối absolute/parent/symlink thoát root. Không ghép đường dẫn
nguồn với thư mục output hoặc nhầm hash envelope với hash byte file.

### Identity bất biến

| Nhóm | Nội dung tham gia signature |
| --- | --- |
| Versions | Contract state/provenance/checkpoint/identity, hash algorithm, retriever sampling/metric/stats/prefix, state projection và prompt pipeline |
| Protocol/matrix | Five-way Full shared PIT; đúng thứ tự ID, mỗi prior_config đã normalize; ablation Full với hai bool true |
| Run config | Symbol, canonical 1d, language, window/step/lookahead, Alpha norm/weights, phí/slippage/capital/multiplier, execution_mode research/offline_fixture |
| Bank | Ba path/hash bank/manifest/audit; so lại với constructor và provenance |
| Sources | Manifest/CSV/evidence/events giá, snapshot tin đóng băng, VNINDEX manifest/CSV, toàn artifact index theo cutoff hoặc fixed-model freeze/hash/training hash |
| Models/templates/code | Model IDs, temperature/max_tokens, backend/structured-output schema hash; hai template hashes, code hashes chuẩn hóa text, versions thư viện thực chạy |
| Point plan | Thứ tự `point_id`, symbol/cutoff/timeframe và `source_sha256` của từng điểm; số điểm là độ dài plan |

`source_sha256=hash(source_proof)`, object gồm `context/prices/news/regime/bank`
theo các nhóm W4-03, chưa có signals. Full `prior_provenance` chỉ hoàn tất sau
shared reports và giữ `signals` đúng W4-03; không điền signals=None để lách
hợp đồng. Replay ghi identity bên tạo reports từ journal cũ, đồng thời identity
code/model của caller hiện tại ở manifest; không giả reports cũ là sinh mới.

Credentials lấy riêng lúc tạo client. **Không ghi key, hash key, `.env`, header
Authorization, raw exception chứa request, URL có token** vào identity/state/log.
Đổi key giữ signature; đổi model/config/ngôn ngữ/template/code/schema/bank/
nguồn/date/plan phải signature khác và từ chối resume. Timestamp, PID/host,
đường dẫn output, latency và pacing/cooldown vận hành không tham gia identity.
Đổi pacing chỉ điều chỉnh tốc độ gọi, không thay đầu vào hoặc hợp đồng khoa học.

## 3. Point checkpoint và phục hồi state

Mỗi point có revision tăng sau mỗi commit durable; point_id=`<symbol>-<cutoff>`,
context daily; `source_proof`, `source_sha256`, `agent_projection`, `shared`,
đúng năm `branches`, `evaluation`, status và error. Source và plan phải khớp
manifest, không chỉ so ngày đầu/cuối như runner ablation cũ.

`agent_projection` whitelist: stock_name, as_of_date, window_end_date, time_frame,
language, is_backtest=true, `snapshot_ref` gồm path/hash CSV đã đóng băng,
snapshot hash/endpoints/rows/schema. Không dump LangGraph state/DataFrame,
BaseMessage/model/provider hay ảnh base64. Giá đầy đủ giữ ở nguồn local;
reader nạp/xác minh một lần, cắt PIT rồi so snapshot hash trước tái dựng
`point_in_time_df` và `kline_data=tail(window_size)`. Thiếu hoặc thay nguồn
phải lỗi; không tải mới. Ảnh và lịch sử chat không cần phục hồi cho Decision.

`shared` gồm stage, ba `upstream_reports` hoặc None, `full_bundle` hoặc None,
`shared_sha256` hoặc None. Full bundle chứa đúng năm reports, current_signals,
market_regime, prior_provenance, alpha_factors và sentiment_data JSON.
`shared_sha256=hash(full_bundle)`; đối chiếu hash reports/signals/state trong
provenance. Upstream reports được persist ngay khi hoàn tất ba agent, trước
Full Alpha/Sentiment; Full bundle persist **trước Decision đầu tiên**.

Khi phục hồi: xây state mới từ projection + nguồn PIT + deep-copy Full bundle,
`messages=[]`, prior fields ban đầu sentinel; không copy toàn point payload.
`evaluation`, process/errors/attempts không đi vào agent. Mỗi branch nhận
prior_config/tasks/stats/metadata/prefix riêng; không tái chạy upstream/Full
preparation khi shared_complete đã xác minh.

## 4. Branch checkpoint

| Trường | Nội dung / validation |
| --- | --- |
| `status` | planned/running/failed/complete: trạng thái tiến trình, không là retrieval status |
| `input` | None khi chưa chuẩn bị; sau đó chứa prior_config, shared_sha256, query_sha256, prior_tasks/stats/metadata, bayesian_prior_context, prompt |
| `prior_metadata` | Toàn object W3, **không lọc field**: versions/bank/query/mode/scope/K/seed/effective_seed/counts/IDs/order/scores/status/reason |
| `prompt` | text chính xác sau distill/cap/BRPP và mọi hướng dẫn, char_count, SHA-256 UTF-8 text; ≤6.499, BRPP≤600; không cắt tùy ý khi resume |
| `attempts` | Danh sách logical Decision invocation: UUID, started/finished UTC, status running/failed/complete/unknown và sanitized error; transport retry nằm trong wrapper hiện có |
| `decision` | None hoặc action LONG/SHORT, confidence/R:R, raw/normalized response, decision_source/fallback_reason, request ID nếu có, latency |
| `error` | None hoặc code, thông báo tiếng Việt đã làm sạch, retryable, retry_after_seconds; không lưu nguyên exception/credential |

Persist retrieval/input/prompt và attempt running **trước** Decision API.
`query_sha256=hash(whitelist kwargs retrieve)` gồm current_signals/context/config.
Chỉ branch complete nếu input/proof/metadata/prefix/prompt và output hợp lệ,
attempt cuối complete, error=None. K=0 vẫn có metadata disabled/k_zero,
tasks=[], stats=None, prefix="". Empty/partial retrieval có thể có branch complete
khi Decision hợp lệ. Sparse tin NEUTRAL không phải branch error.

Decision parser hiện có giữ nguồn gốc (`llm_structured`, JSON/text recovery...);
recovery chỉ hợp lệ nếu parser chứng minh action từ output LLM. Không cho
default/fallback SHORT hoặc UNKNOWN trở thành complete. Source `fixture` chỉ
cho execution_mode=offline_fixture, không cho research; mock prediction không
là kết quả giao dịch LLM. Quota/format/source/interrupt không sinh prediction.

Trước mỗi attempt và khi resume, formatter/retriever có thể tính lại **offline**
để so tasks/stats/metadata/prefix/prompt đúng versions, không overwrite khác biệt.
Nhánh complete đã durable giữ nguyên; không invoke lại, không đổi order/seed.
Running bị ngắt với chưa có response durable đánh dấu attempt unknown; có
thể gọi lại **Decision còn thiếu** cùng input, attempt ID mới. Không thể bảo
đảm provider chỉ tính phí một lần khi remote đã trả nhưng local chưa lưu;
checkpoint chỉ bảo đảm không gọi lại branch complete đã commit.

## 5. Tiến trình, crash và complete

Point process dùng planned/running/failed/complete, riêng với `shared.stage`.
Tất cả point planned phải durable trước manifest.initialized=true và trước API.
Manifest initialized=false cho phép tiếp tục khởi tạo chưa gọi API; initialized=true
mà point file mất là lỗi integrity, không coi là điểm chưa chạy để gọi lại.

| Ranh giới durable khi crash | Resume / lời gọi được phép |
| --- | --- |
| Init chưa initialized | Xác minh identity; hoàn tất point planned; cấm API cho đến initialized=true |
| planned, shared.not_started | Kiểm nguồn; persist upstream_started rồi mới invoke upstream một lần |
| upstream_started, chưa có ba reports durable | **AMBIGUOUS_UPSTREAM**: dừng để rà soát; không tự gọi lại vision hay tạo report giả |
| upstream_complete | Dùng ba report đã lưu; chạy Full preparation một lần sau persist full_started |
| full_started, chưa có Full bundle durable | **AMBIGUOUS_FULL**: dừng để rà soát; không lặp Full preparation; giữ upstream đã có |
| shared_complete, chưa Decision | Xác minh source/shared; chỉ chuẩn bị/call các branch còn thiếu |
| Giữa các branch / quota / interrupt | Giữ complete; failed/running chưa complete được retry Decision theo wrapper với cùng input, không chạy upstream |
| Decision remote trả, ghi branch durable thất bại | Dừng; file cũ còn nguyên; retry Decision có thể lặp remote, ghi attempt unknown; không coi response mất là complete |
| Branch cuối durable, chưa evaluation/point complete | Không gọi LLM; tính evaluation bằng engine, commit point complete |
| Point complete, chưa results.json | Dựng lại results/summary offline từ point đã seal; không API |

Không tự reset stage ambiguous về not_started. Muốn giải quyết cần báo cáo
nguồn/call record đã lưu đủ để đối chiếu và nhập bằng công cụ reconciliation
có audit/version riêng; W4-12 chưa cấp một cờ force-rerun upstream mặc định.
Wrapper retry trong cùng một invocation tuân AGENTS; không đồng nghĩa được
khởi chạy lại cả upstream sau crash không rõ kết quả.

Point complete khi cả năm branches complete, shared_complete, hashes/PIT
hợp lệ và evaluation đúng engine. `evaluation` chứa entry/exit, giá thực thi,
net_return_long, actual_direction và mỗi branch correct/executed_action/
cycle_net_return; nó nằm **ngoài** Full bundle/provenance/query. LONG vào
Open(t+1), thoát Close(t+3), SHORT cash/return=0; phí .0025, slippage .001 mỗi chiều.
Hai trường net return này là tỷ lệ dạng fraction; outcome của historical task
vẫn giữ `net_return_pct` dạng phần trăm theo schema W1. Summary `accuracy` là
fraction 0..1; các metric tài khoản có hậu tố `_pct` giữ đơn vị phần trăm của engine.
Không dùng Close-to-Close. Lịch thiếu phiên/sự kiện quyền chưa hỗ trợ phải lỗi
hoặc đã được loại tường minh trong run plan/gate, không chấm thành loss.

Results có planned_point_ids, completed_point_ids, `point_files` (point_id,
path và SHA-256 byte của từng point complete đã seal) và summary cho năm
branches trên **cùng common support**, status partial/complete. Reader nghiên
cứu resolve/kiểm các tham chiếu local để trả đầy đủ năm branch và shared bundle;
không sao chép lại dữ liệu nguồn vào mỗi result. Complete
chỉ khi đủ toàn plan. Summary lưu sample_count, đúng/sai/action counts, accuracy
và account metrics từ engine; không tính trên riêng các branch thành công của
point còn dở. Khi chưa có point complete: mọi sample/action/correct count=0,
accuracy=None và account_metrics=None; không hiển thị tỷ lệ 0% như một kết quả
đã quan sát. Results là dẫn xuất, bị hỏng có thể dựng lại; point/manifest hỏng
thì dừng, không tự bỏ qua để xuất PASS. Seal point complete không chỉnh sửa.

## 6. Atomic write, khóa và lỗi đĩa

Tái sử dụng `core.bayesian_memory.atomic_write_json`: temp tên riêng **cùng
thư mục**, strict JSON, flush+fsync rồi os.replace; chỉ nhận durable sau replace
thành công. Reader kiểm envelope/schema/hash/semantic trước sử dụng; mọi bước
call tiếp theo phụ thuộc commit durable trước đó. Không dùng `_save` backtest
cũ vì nuốt lỗi I/O; không dùng `.tmp` tên cố định của runner ablation cho writer mới.
IO error phải ném lại, ngừng API; không tăng revision/status ở RAM rồi báo thành
công. File cũ hợp lệ giữ nguyên nếu replace fail. Temp mồ côi không là checkpoint;
chỉ dọn temp theo prefix dưới đúng run-dir khi đã giữ khóa, không xóa nguồn/archive.

Khóa nghiên cứu là **OS advisory lock trên byte 0 của run.lock**, handle giữ
suốt vòng chạy; Windows dùng `msvcrt.locking`, nền tảng khác cần backend tương
đương có test. run.owner.json chứa host_id, boot_id, PID, process_start_time,
owner UUID, acquired_at và run_signature. File lock còn tồn tại không nghĩa
runner đang chạy. OS tự nhả handle khi process chết; không unlink run.lock.
Metadata còn có `owner_state=active/released` và `released_at` (UTC hoặc None).
Released hợp lệ cho phép tái nhận khóa dù process server cũ vẫn sống; không
nhầm một lần chạy đã kết thúc bình thường với writer active mất OS lock.

- Lock busy → dừng; không xóa khóa kể cả tuổi file lớn.
- Lock available → giữ OS lock rồi so owner cùng host/boot/PID/start-time;
  owner đã released, đã chết hoặc PID tái sử dụng được thay metadata bằng owner UUID mới,
  ghi recovery record. Không gửi signal/terminate theo PID cũ.
- Owner active thuộc tiến trình khác vẫn sống nhưng không giữ OS lock, metadata malformed,
  host khác hoặc không xác định được liveness → dừng rõ để rà soát; không đoán dead.
- finally khi còn giữ handle, ghi released/released_at nếu owner UUID còn khớp,
  rồi đóng handle sở hữu; lỗi ghi metadata vẫn phải nhả handle và báo lỗi rõ.
  Không xóa metadata/khóa của writer khác. Lock trên filesystem sync/network
  không là distributed lock: chỉ hỗ trợ một máy local; không chạy đồng thời
  hai máy trong thư mục OneDrive chung. Không tuyên bố fsync chống mọi lỗi phần cứng.

Quota/rate-limit lưu branch failed với input nguyên vẹn và delay sanitized,
nhả handle; đổi key rồi resume không cần thay identity. Không tự sleep hàng
trăm giây trong checkpoint layer; policy retry/pacing của wrapper vẫn áp dụng.
SIGINT trước khi ghi được error để lại running durable; reader xử lý unknown
attempt/stage theo bảng, không yêu cầu exception handler luôn ghi thành công.

## 7. Validator và tương thích

Schema kiểm shape/types/enums/required/stage cơ bản. Semantic W4-12 phải kiểm
signature/envelope, số điểm/unique IDs/order, date/PIT/source, branch/config
mapping, native types, counts/rates/selected order/scores, recompute prefix,
shared/query/prompt hashes, prompt-length và evaluation bằng engine. Không
cấp PASS chỉ vì schema pass; hash envelope có thể được tính lại sau khi sửa
nội dung sai nên không thay validation quan hệ.

Run signature khác hoặc schema không hỗ trợ → ValueError trước API; source
thiếu → FileNotFoundError/OSError; vi phạm PIT → ValueError/AssertionError.
Không migrate legacy thiếu proof. Dữ liệu placeholder/synthetic phải khai
execution_mode=offline_fixture; adapter nghiên cứu phải kiểm gate thật trước upstream.

## 8. Gate A và bàn giao

Kiểm chứng mới trên baseline `e3aa3f8`:

- Bốn document mẫu (manifest/point/result/partial rỗng), bảy shape trạng thái
  và 11 ca schema sai PASS; resolve schema W1 local, không gọi mạng.
- Năm projection retriever thật giữ toàn tasks/stats/metadata, bốn prior mode
  cùng population, Original K=0; prompt fixture 3.892–4.241 ký tự.
- Tám mutation identity (bank/config/model/template/nguồn/cutoff/code/language)
  đổi signature; schema từ chối field API key. Không thử key thật.
- Ba probe writer/reader hiện có: replace failure giữ file cũ và dọn temp sở hữu,
  duplicate key và NaN bị từ chối. Ca OS lock/crash mới chưa chạy runtime.
- Compileall PASS; **339 unit (130,278 giây)**, **E2E xác định (17,6 giây)**,
  **56 leakage (6,097 giây)** PASS. Hash 2.312 file nguồn/bằng chứng/archive
  giữ nguyên; đối chiếu lại 261 file đã khóa trong receipt W4-01.

Receipt mới xác minh schema/ví dụ, projection năm retrieval thật từ bank,
chữ ký và ca đổi nguồn/config/template so với đổi credentials; đối chiếu
atomic writer/strict reader hiện có trong temp-dir. Ca crash/lock của runtime
mới là **đặc tả chờ W4-12**, không là failpoint integration PASS.

Gate A chỉ đóng khi W4-01..04 có contract/receipt nhất quán, ví dụ/ca biên
đã kiểm, đủ bốn gate mới và ranh giới W4 offline/W5 pilot được giữ. Các receipt
W4-01..03 ghi trạng thái tại thời điểm cũ (Gate A=false) được giữ nguyên;
receipt W4-04 ghi quyết định Gate A hiện tại, không sửa bằng chứng đã đóng băng.
W4-05 tiếp tục state/config validator; provider/paired/resume runtime, guard
prompt thật và gate giá thực thi OOS vẫn chưa nghiệm thu.
