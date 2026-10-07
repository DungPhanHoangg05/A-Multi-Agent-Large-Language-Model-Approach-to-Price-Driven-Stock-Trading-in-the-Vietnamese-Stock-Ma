# Vận hành prior, checkpoint/resume và bàn giao W5

**W4 đã hoàn thành 16/16; Gate D offline và retrieval p95 PASS.** Cập nhật
07/10/2026; [tiến độ và kết quả nghiệm thu](README.md), [kế hoạch tổng](../plan.md).
Các receipt và bản bàn giao cũ được lưu nguyên byte trong
[ZIP bằng chứng](../implementation_evidence.zip). Prior mặc định tắt.
Gate giá OOS/model/quota/CLI/pilot vẫn chưa PASS.

## 1. API, cấu hình và đường chạy

Các API nằm tại [prior_config.py](../../../core/prior_config.py),
[prior_context.py](../../../core/prior_context.py),
[backtest_engine.py](../../../core/backtest_engine.py),
[prior_backtest.py](../../../core/prior_backtest.py),
[graph_setup.py](../../../utils/graph_setup.py).

### Tắt/bật prior

```python
from core.prior_config import normalize_prior_config

disabled = normalize_prior_config()
enabled = normalize_prior_config({
    "enable_bayesian_prior": True,
    "mode": "bayesian_regime",
    "k": 3,
    "seed": 42,
    "scope": "same_symbol",
    "bank_path": "data_manager/regime_memory_store.json",
    "manifest_path": "data_manager/regime_memory_store.manifest.json",
    "audit_path": "docs/plan/week2/memory_bank_audit.json",
})
```

- `disabled` dùng các entry point legacy; không khởi tạo `PriorContextAdapter`
  và không đọc nguồn prior mới. Không đưa prior/result còn sót vào state.
- `enabled` chỉ chạy Full/backtest/daily; `1d` và `1 ngày` được canonical về `1d`.
  Không tự bật prior qua UI/legacy entry point; dùng adapter và runner nghiên cứu.
- Tám field state: `prior_config`, `market_regime`, `current_signals`,
  `prior_provenance`, `prior_tasks`, `prior_stats`, `prior_metadata`,
  `bayesian_prior_context`. Outcome query chỉ thuộc lớp đánh giá sau Decision.
- Single-config API hỗ trợ K=0..3 và hai scope; runner năm nhánh khóa
  `same_symbol`, seed=42. Không đổi scope/seed/ma trận của run đang resume.

| Branch ID | Mode | K | Ý nghĩa |
| --- | --- | ---: | --- |
| `original` | `bayesian_regime` | 0 | Full reports, không BRPP/stats |
| `random` | `random` | 3 | Chọn ngẫu nhiên có seed cố định |
| `recent` | `recent` | 3 | Chu kỳ gần nhất đã tất toán |
| `similarity` | `similarity` | 3 | Tương đồng tín hiệu trên pool hợp lệ |
| `bayesian` | `bayesian_regime` | 3 | Population cùng regime và tương đồng tín hiệu |

Original không tương đương Baseline/No-Alpha cũ. Các prior branch thêm cả ví dụ
và thống kê; so sánh Original với Bayesian không tách riêng tác động từng thành phần.
Năm nhánh dùng deep-copy cùng Full reports; upstream/Full không chạy lại theo nhánh.

### Nguồn và provider

| Cấu hình adapter | Dùng cho | Điều kiện |
| --- | --- | --- |
| `historical_prefix` | Replay lịch sử | Artifact đúng cutoff, train end=cutoff, prefix/hash đúng; `verify_only=True`, thiếu thì dừng |
| `fixed_train_oos` | Pilot/OOS sau mở gate | `frozen_artifact_path`, `freeze_as_of_date`; train end ≤ freeze < cutoff, train end < cutoff; đủ proof toàn prefix và ba component |

Nguồn mặc định: `execution_dir="data/execution_prices"`,
`news_dir="outputs/historical_memory_run/inputs/news"`,
`vnindex_manifest_path="data/historical/manifest.json"`.
Đây là nguồn train/replay đã đóng băng, không tự coi phủ OOS. W5 dùng bộ nguồn
OOS mới, repo-relative, audit/hash riêng và chỉ rõ đường dẫn cho adapter.
Không ghi đè bank, nguồn hoặc archive train để mở gate OOS.

`signal_config` phải có đúng `models`, `window_size`, `norm_method`,
`alpha_weights`, `language`, `time_frame`; models giữ sáu field ID/temperature/
max_tokens của `agent_llm` và `graph_llm`. Engine và các client của `SetGraph`
phải khớp cấu hình này. `execution_mode="research"` kiểm client ChatGroq thật;
client giả chỉ dùng `offline_fixture`.

### Mẫu gọi runner sau khi W5 mở gate

Đây là đoạn nối API, không phải CLI có thể chạy ngay. Caller W5 phải chuẩn bị
`builder`, `signal_config`, bộ giá/tin/VNINDEX đã PASS, artifact/freeze đã kiểm
và tuple 20 cutoff đã chốt; các biến bên dưới là đầu vào của caller đó.

```python
from pathlib import Path
from core.backtest_engine import BacktestEngine
from core.prior_context import PriorContextAdapter

adapter = PriorContextAdapter(
    enabled,
    execution_dir=oos_execution_dir,
    news_dir=oos_news_dir,
    vnindex_manifest_path=oos_vnindex_manifest,
    provider_mode="fixed_train_oos",
    frozen_artifact_path=frozen_artifact_path,
    freeze_as_of_date=freeze_as_of_date,
    window_size=signal_config["window_size"],
    signal_config=signal_config,
)
engine = BacktestEngine({
    **signal_config["models"],
    "language": signal_config["language"],
    "alpha_norm_method": signal_config["norm_method"],
    "alpha_weights": signal_config["alpha_weights"],
})
result = engine.run_prior_backtest(
    "FPT", adapter=adapter, graph_builder=builder,
    output_dir=Path("outputs/pilot_fpt_run"),
    time_frame="1d", cutoffs=pilot_cutoffs, step=3,
    execution_mode="research", resume=False,
)
```

Plan có 600 nến warm-up, horizon ba phiên, step ≥3 phiên. Runner kiểm toàn
plan/context/entry/exit trước API đầu. Adapter/retriever được tạo một lần;
checksum byte nguồn vẫn được kiểm tại ranh giới graph; toàn graph có I/O
kiểm nguồn, còn truy xuất trên pool đã nạp chạy trong RAM.

## 2. Kết quả và resume

[Schema v1](research_checkpoint.schema.json) và [policy checkpoint](checkpoint_policy.json)
quy định định dạng lưu và điều kiện phục hồi.

| Artifact dưới run-dir | Vai trò |
| --- | --- |
| `run_manifest.json`, `identity.json` | Config/plan/nguồn/model/template/code/runtime và signature |
| `points/<SYMBOL>-<YYYY-MM-DD>.json` | Shared durable, branch input/attempt/raw/normalized response và evaluation riêng |
| `results.json` | Dẫn xuất từ common support các point đủ năm nhánh complete |
| `run.lock`, `run.owner.json`, `run.recovery.json` | OS handle lock, owner và audit nhận lại quyền chạy |

JSON strict/native/finite; envelope `{payload, sha256}` và verifier semantic
đều phải PASS. Evaluation không được phục hồi vào state agent. LONG vào
Open(t+1), ra Close(t+3); SHORT giữ cash. Fee 0,25% + slippage 0,10% mỗi chiều;
nhãn và P&L dùng `compute_round_trip_net_return`, metrics dùng engine hiện có.

Khi gián đoạn, khởi tạo client/engine/adapter cùng cấu hình và nguồn rồi gọi
cùng API/output-dir với `resume=True`. Không dùng script resume Memory Bank W2
để resume run năm nhánh. CLI `scripts/run_bayesian_ablation.py` **chưa có**, thuộc W5.

| Trạng thái durable | Hành động resume |
| --- | --- |
| `upstream_complete` | Dùng ba report đã lưu, tiếp tục Full |
| `shared_complete` | Phục hồi Full, chỉ chạy Decision còn thiếu |
| Branch `complete` | Bỏ qua lời gọi LLM của nhánh đó |
| Attempt `running` thiếu response durable | Giữ attempt cũ `unknown`, attempt mới cùng input |
| Đủ năm branch, chưa seal / results mất-hỏng | Evaluate/seal/rebuild offline từ point đã xác minh |
| `upstream_started` / `full_started` thiếu output durable | Dừng `AMBIGUOUS_UPSTREAM` / `AMBIGUOUS_FULL`, không tự lặp vision/Full |

### Đổi key và chẩn đoán lỗi

- Sau lỗi quota, giữ checkpoint; dừng run, thay key riêng trong môi trường
  client rồi khởi tạo client mới và resume. Key/hash key không thuộc identity;
  đổi key không cho phép bỏ cooldown hoặc bảo đảm quota dự án đã được phục hồi.
- Model/temperature/max_tokens, nguồn/bank, config/ngôn ngữ/date/plan,
  template/code/schema/runtime thay đổi thì không resume run cũ. Đối chiếu
  identity với đúng bản code và nguồn đã ghim; không sửa signature/hash để vượt guard.
  Cần thay các đầu vào khoa học thì dùng run-dir mới.
- JSON/schema/hash/proof sai: dừng trước API, rà file nguồn và manifest/point;
  không suy diễn nhánh lỗi thành SHORT. `results.json` là dẫn xuất; manifest
  và point hỏng không được tự dựng lại bằng kết quả summary.
- Khóa còn file không đồng nghĩa runner đang chạy: OS lock giữ bằng handle.
  Owner active/khác host/không xác minh được thì dừng; không xóa lock/kill owner.
- Response chưa ghi durable có thể phải gọi lại Decision còn thiếu; không
  cam kết exactly-once API từ xa. Attempt là một lần invoke graph, chưa là
  số request HTTP/retry; W5 phải đo riêng.

## 3. Ngân sách runtime và hiệu năng

- Cap báo cáo 4.000 ký tự: trend/pattern/indicator 800 mỗi loại, Alpha 1.100,
  sentiment 500. BRPP ≤600; prompt cuối gồm template/reasoning **<6.500**.
- Guard kiểm trước API; không cắt BRPP để che lỗi. Smoke kiểm prefix 600,
  prompt 6.499 nhận/6.500 chặn với runtime caps nguyên bản.
- [Kết quả mới nhất](README.md): bốn mode retrieval p95 10,837–13,235 ms,
  PASS <30 ms sau tối ưu lookup alias/copy pool. Kiểm snapshot/PIT/type/copy
  và output/ranking/stats/oracle giữ nguyên. Lượt W4-15 và baseline trước sửa
  FAIL vẫn được giữ nguyên byte trong [ZIP bằng chứng](../implementation_evidence.zip).
- Phương pháp 100 warm-up/1.000 mẫu/bước/mode, bốn mode/hai scope, nearest-rank;
  không bỏ ngoại lai, nới ngưỡng hoặc chọn lại lượt PASS. Formatter/adapter/
  graph/cold load đo riêng, không áp ngưỡng retrieval cho chúng.
- Sửa code retriever đổi fingerprint: không ép resume một run nghiên cứu
  ký bằng bản code khác. Artifact Memory Bank W2 giữ identity bên tạo.

## 4. Điều kiện mở pilot/OOS — đang BLOCKED

Các mục dưới đây là công việc trước API pilot đầu tiên, **không được đánh dấu
PASS từ việc đóng W4**. Pilot FPT cần FPT+VNINDEX; benchmark W6 cần đủ FPT/VCB/VNM/MWG.

### Gate dữ liệu giá và tin

- [ ] Thu thập chỉ qua **vnstock/VCI và vnstock/KBS**; ghi provider/library version,
  raw field map, đơn vị giá và thời điểm thu. Dùng VCI chính/KBS đối chiếu;
  không thêm nguồn ngoài hai provider được phép.
- [ ] Bộ OHLCV thô `UNADJUSTED_EXECUTION` phủ cutoff OOS 2023–2024 cần chọn,
  đủ lịch warm-up 600 phiên và entry/exit t+1/t+3; không thiếu/trùng phiên,
  ngày/volume/OHLC/schema hợp lệ, lịch FPT khớp VNINDEX.
- [ ] Đối chiếu corporate actions/quyền/tham chiếu và chính sách loại chu kỳ;
  source/adjustment/provenance nhất quán, không dùng CSV cổ phiếu W1 điều chỉnh
  để tính nhãn. Lưu evidence/events/calendar và checksum độc lập.
- [ ] Manifest và audit giá OOS PASS, loader xác minh được toàn bộ nguồn;
  không chỉ kéo dài `requested_end` của manifest train. Giá train 2018–2022
  PASS vẫn giữ riêng, không ghi đè archive/bank.
- [ ] Chốt snapshot tin có ngày ≤cutoff, cửa sổ/coverage/hash; thiếu ba bài hợp
  lệ giữ NEUTRAL có lý do. Không lấy tin hôm nay để bù sentiment lịch sử.

### Gate model, sample plan và quota

- [ ] Chọn `fixed_train_oos` cho pilot; artifact có train end ≤freeze<cutoff
  sớm nhất, prefix VNINDEX và proof HMM/scaler/calibration đã kiểm, hash/freeze
  cố định. Model full-train `RESEARCH_ONLY/UNVERIFIED` hiện có không tự đủ proof.
- [ ] Chốt **20 cutoff FPT** trước run, trong bộ nguồn PASS, tăng dần và cách
  ≥3 phiên, đủ warm-up/exit. Khóa file plan/hash; không chọn ngày theo outcome,
  prior stats hay dự báo đã thấy. Ngày cụ thể chưa chốt vì gate OOS đang BLOCKED.
- [ ] Chốt model IDs/temperature/max_tokens, VI/EN, window/norm/weights,
  seed=42/same_symbol và ma trận năm nhánh; cấu hình client khớp identity.
- [ ] Xác minh quota thực tế của tài khoản/project/model và ngân sách input +
  output tokens, RPM/TPM/daily limits trước chạy. Không lưu giá trị key/hash key.
  20 điểm cần 100 Decision hợp lệ, chưa tính upstream/retry/format retry.
- [ ] Cài/kiểm pacing chung cho mọi transport, dự phòng TPM kể cả vision/output,
  tôn trọng retry-after và dừng checkpoint khi hết quota. Nghỉ hiện có 10 giây
  giữa nhánh, 8 giây giữa điểm không bảo đảm không vượt TPM. Pacer W2 chưa được
  tự gắn vào CLI nghiên cứu; W5 cần nối và kiểm riêng.
- [x] Cảnh báo p95 đã xử lý trên bản tối ưu ngày 07/10/2026; giữ cả FAIL/PASS
  trong ZIP bằng chứng, không dùng kết quả này thay gate quota hoặc OOS.

## 5. Thứ tự triển khai W5

| Bước | Việc phải làm | Đầu ra / điều kiện chuyển bước |
| --- | --- | --- |
| 1 | Mở gate giá/tin FPT+VNINDEX OOS, giữ train archive | Bộ nguồn riêng, manifest/evidence/audit/hash PASS |
| 2 | Chốt artifact/freeze PIT và plan 20 cutoff | Model proof + plan/hash PASS trước mọi API |
| 3 | Chốt config, quota/pacing; đối chiếu p95 đã PASS | Cấu hình vận hành, giới hạn/dừng/retry và bằng chứng hiệu năng |
| 4 | Viết `scripts/run_bayesian_ablation.py` gọi API W4 | CLI dry-run/preflight/verify/resume; mock offline có call-count, schema và checkpoint PASS |
| 5 | Chạy pilot thật sau gates W5 | 20 common-support point, năm nhánh, 100 Decision hợp lệ; run-dir/checkpoint/log/telemetry |
| 6 | Rà pilot và điều kiện mở benchmark W6 | Báo cáo lỗi/token/latency/quota/resume và dữ liệu đủ bốn mã; không tự mở W6 khi còn thiếu |

Telemetry W5 cần đo input/output/total tokens thực (ghi thiếu nếu provider
không trả), thời gian từng request/điểm, call-count upstream/Full/Decision,
HTTP retry, 429/quota, lỗi format/parse, số branch complete/unknown và resume.
Provider request ID hiện chưa thu, không dựng ID giả; không dump credentials,
headers hoặc raw exception chứa request. Thống kê run invocation và HTTP
request riêng; nếu thêm telemetry ảnh hưởng code/schema thì version/run mới.

Dừng khi gate nguồn/model/identity/cutoff sai, prompt vượt cap, JSON/parse chưa
hợp lệ sau cơ chế retry hiện có, quota hết, nguồn đổi, lock/I/O lỗi hoặc user
stop. Giữ dữ liệu durable, không tiếp tục điểm sau để che điểm dở; chỉ đánh giá
common support đủ năm nhánh. Resume xác minh trước API và bỏ nhánh complete.

## 6. Giới hạn nghiên cứu và nội dung báo cáo giảng viên

Kho hiện có **852 episode**, quyết định 2020–2022 do warm-up, không đại diện
đủ 2018–2019. Sentiment toàn NEUTRAL vì thiếu tin lịch sử đáng tin cậy.
Stats là tỷ lệ thực nghiệm có mẫu số, không là xác suất posterior đã calibration.
Smoke synthetic và replay sáu context quan sát với Decision giả không phải
kết quả đầu tư OOS. Fixed model được kiểm kỹ thuật bằng fixture; OS lock được
kiểm native Windows, chưa nghiệm thu native Linux/filesystem chia sẻ.

Có thể báo cáo: đã tích hợp prior regime vào pipeline đa agent, bảo toàn kinh
tế T+2.5, kiểm PIT/paired/budget/checkpoint và hồi quy offline. Bước tiếp theo
là mở dữ liệu OOS, model proof, quota/CLI rồi pilot FPT 20 điểm; chưa có bằng
chứng tăng lợi nhuận ngoài mẫu. Cảnh báo retrieval p95 đã xử lý; hiệu năng
LLM/quota cần đo khi pilot.
