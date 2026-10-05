# Chốt W3 và bàn giao tích hợp W4

**Chốt ngày 05/10/2026: W3 hoàn thành 16/16 task, bốn phase PASS.** Phạm vi bàn giao là API retriever, thống kê regime,
formatter BRPP và bằng chứng kiểm chứng offline. Nghiệm thu cuối cùng ghi trong
[receipt chốt tuần](week_close_review.json); checklist tổng ở [README W3](README.md).

## 1. Deliverables

| Thành phần | Đầu ra / bằng chứng |
| --- | --- |
| Hợp đồng API v1 | [Query/result, K, seed, scope và lỗi](retriever_api_contract.md) |
| Luật chọn prior | [Phương pháp](prior_selection_method.md), [policy v1](prior_selection_policy.json) |
| Stats và BRPP | [Hợp đồng](statistics_and_prefix_contract.md), [policy](statistics_prefix_policy.json) |
| API đầy đủ | [BayesianPriorRetriever](../../../core/bayesian_retriever.py), [HistoricalMemory](../../../core/bayesian_memory.py) |
| Formatter | `format_compact_prior_prefix(tasks, stats)`, tối đa 600 ký tự, Original rỗng |
| Hành vi/zero-leakage | 104 test Bayesian trong bộ unit; 56 test leakage toàn hệ thống; [coverage](phase_d_validation_and_handoff.md) |
| Ngân sách prompt | [Receipt hiện tại](prompt_budget_review.json): 1.024 ca, dự phòng BRPP đủ 600 |
| Smoke PIT kho thật | [Receipt hiện tại](prior_smoke.json): 32 context, 288 query + 288 lượt lặp |
| Hiệu năng | [Lượt chốt sau chuyển thư mục](retrieval_benchmark_week_close.json), cùng phương pháp W3-14 |
| Tích hợp và tính nguyên vẹn | [Receipt chốt tuần](week_close_review.json), bốn gate và hash bằng chứng |

Kho phát hành vẫn là `data_manager/regime_memory_store.json`: **852 episode**,
SHA-256 `09b48c6192a092b562173e8b3b7eceb44025c6e02454093e34214a730a460949`.
Constructor đối chiếu manifest/QA/schema, giá và nhãn kinh tế trước khi dùng kho.
Mỗi query chạy trên RAM, có validation và bản sao độc lập; không đọc lại giá,
tính lại P&L hoặc gọi LLM.

## 2. API vào/ra dành cho W4

- Khởi tạo một retriever cho mỗi kho/config của tiến trình với `bank_path`,
  `manifest_path` và `audit_path=docs/plan/week2/memory_bank_audit.json`.
- Query nhận `symbol`, `as_of_date`, `current_regime`, `current_signals`,
  `mode`, `k`, `seed`, `scope`. Tín hiệu có đúng năm trường:
  `trend`, `pattern`, `alpha_consensus`, `indicator_consensus`, `sentiment`.
- Caller xác minh ngày snapshot/tin và provenance HMM/scaler trước query:
  feature/news/model train end không vượt cutoff; regime state đúng ngày query.
  Retriever chỉ nhận tên regime nên trách nhiệm này thuộc caller.
- `retrieve()` trả đúng `tasks`, `stats`, `metadata`. Mọi prior có
  `exit_date < as_of_date`; Bayesian còn cùng regime. Stats tính trên toàn population
  cùng regime/cutoff/scope, không lấy K làm mẫu số. Các tỷ lệ có counts hỗ trợ;
  mẫu số 0 là `None`, không là 0%.
- Formatter nhận tasks/stats đã được retriever xác minh; không tự chứng minh
  cutoff hoặc nguồn model từ một record độc lập. BRPP giữ nhãn LONG ròng sau phí,
  SHORT là tiền mặt và chú thích sentiment thiếu tin.
- Lưu toàn bộ metadata vào checkpoint: versions, bank hash, IDs/thứ tự/scores,
  requested K/selected count, seed/effective seed, scope, cutoff/regime,
  eligible/matched/candidate count, status/reason; lưu stats và prefix đã dùng.

### Cấu hình năm nhánh thí nghiệm

| Nhánh | `mode` truyền retriever | K | Stats / prefix |
| --- | --- | ---: | --- |
| Original | `bayesian_regime` | 0 | `None` / chuỗi rỗng |
| Random | `random` | 3 | Population cùng regime / BRPP |
| Recent | `recent` | 3 | Population cùng regime / BRPP |
| Similarity | `similarity` | 3 | Population cùng regime / BRPP |
| Bayesian | `bayesian_regime` | 3 | Population cùng regime / BRPP |

Mặc định nghiên cứu `scope="same_symbol"`, seed=42; pooled chỉ dùng trong cấu hình
thí nghiệm được chốt trước. Bốn nhánh prior nhận cùng stats khi cùng query/scope;
Original không nhận stats. K=0 vẫn kiểm input. Các nhánh này dùng cùng đầy đủ báo
cáo upstream; cấu hình chọn prior là trường riêng bên cạnh các ablation hiện có.

### Thiếu mẫu và lỗi

| Trạng thái | Hành vi bàn giao |
| --- | --- |
| `disabled/k_zero` | Tasks rỗng, stats None, prefix rỗng |
| `empty/no_eligible_history` | Không có lịch sử đã thoát trước cutoff |
| `empty/no_matching_regime` | Bayesian không có population đúng regime |
| `partial/insufficient_candidates` | Giữ số task hợp lệ hiện có; ghi selected count |
| `complete` | Đủ K, không khẳng định đủ độ tin cậy thống kê |
| Input/QA/cutoff/schema sai | Ném ValueError/AssertionError hoặc lỗi I/O tương ứng; dừng điểm, lưu chẩn đoán |

Không mở rộng scope/regime để bù mẫu, không bịa task hoặc biến lỗi dữ liệu thành
`empty`. Checkpoint chỉ đánh dấu điểm hoàn tất sau khi mọi nhánh hợp lệ đã lưu;
resume giữ cấu hình/hash/query và kết quả upstream đã xác minh.

## 3. Ví dụ replay offline bằng context đã xác minh

Chạy Python tại thư mục gốc repo sau khi smoke PASS. Ví dụ dùng context lịch sử
trong receipt, không suy ra regime của ngày hiện tại hoặc ngày kiểm định mới.
Các hash nguồn/archive của receipt được verifier kiểm trước khi phát hành.

```python
from pathlib import Path
from core.bayesian_memory import read_json
from core.bayesian_retriever import BayesianPriorRetriever, format_compact_prior_prefix
from core.regime_detector import validate_regime_state

root = Path.cwd()
smoke = read_json(root / "docs/plan/week3/prior_smoke.json")
assert smoke["status"] == "PASS" and all(smoke["checks"].values())
context = next(c for c in smoke["contexts"]
               if c["case_kind"] == "observed" and c["query"]["symbol"] == "FPT"
               and c["query"]["current_regime"] == "BEAR")
query, source = context["query"], context["source"]
state = source["regime_state"]
validate_regime_state(state)
assert state["as_of_date"] == query["as_of_date"]
assert state["regime_name"] == query["current_regime"]
assert state["feature_end_date"] <= query["as_of_date"]
assert source["model_train_end_date"] <= query["as_of_date"]

retriever = BayesianPriorRetriever(
    bank_path=root / "data_manager/regime_memory_store.json",
    manifest_path=root / "data_manager/regime_memory_store.manifest.json",
    audit_path=root / "docs/plan/week2/memory_bank_audit.json",
)
for mode in ("bayesian_regime", "random", "recent", "similarity"):
    result = retriever.retrieve(**query, mode=mode, k=3, scope="same_symbol")
    prefix = format_compact_prior_prefix(result["tasks"], result["stats"])
    assert len(prefix) <= 600
    assert all(t["exit_date"] < query["as_of_date"] for t in result["tasks"])
    print(mode, result["metadata"]["selected_ids"], len(prefix))

original = retriever.retrieve(**query, mode="bayesian_regime", k=0, scope="same_symbol")
assert original["tasks"] == [] and original["stats"] is None
assert format_compact_prior_prefix(original["tasks"], original["stats"]) == ""
```

Ở W4, thay phần đọc context receipt bằng state/tín hiệu PIT của đúng test point
và kiểm provenance thật trước query. Outcome của test point được giữ ngoài query.

## 4. Thứ tự triển khai W4 và điều kiện nghiệm thu

| Bước | File / công việc | Điều kiện nghiệm thu |
| --- | --- | --- |
| 1 | `agents/agent_state.py`: market regime, prior tasks, prior context và metadata | Kiểu Python gốc/JSON strict; input hiện tại không có nhãn tương lai |
| 2 | `utils/graph_setup.py`: flag prior/mode/K/scope/seed và truyền state | Original K=0; hành vi các ablation cũ được bảo toàn |
| 3 | `core/backtest_engine.py`: nạp retriever một lần, gọi tại cutoff | Giá/tin/model PIT; prior đã thoát; giữ Open(t+1)→Close(t+3), phí 0,25% và trượt 0,10% mỗi chiều |
| 4 | Upstream ghép cặp và checkpoint | Indicator→Pattern→Trend một lần/điểm; deep copy kết quả sang mọi nhánh; lưu IDs/hash/config/fallback để resume |
| 5 | `agents/decision_agent.py`: inject BRPP và ngân sách runtime | BRPP ≤600 trước báo cáo đầu; guard toàn prompt <6.500 sau mọi hướng dẫn |
| 6 | Tests tích hợp/state/prompt/paired/leakage | Original không prior, prefix đúng vị trí/một lần, cutoff lỗi gây dừng, không gọi lại upstream |

**Ngân sách bắt buộc bàn giao:** trend/pattern/indicator **800** ký tự mỗi báo cáo,
alpha **1.100**, sentiment **500**, tổng **4.000**. Phương án này dự phòng đủ
BRPP 600 cho prompt ghép tối đa 6.289 trên fixture đã kiểm. Cap cũ tổng 4.500
vượt trần khi ghép BRPP bão hòa; W4 phải áp dụng phương án này hoặc xác minh phương
án khác. Giữ `_distill_report`, `_cap_report`, nội dung hợp đồng kinh tế và
conflict gate; kiểm lại VI/EN và daily `1d`/`1 ngày` (lookahead=3).

Guard cuối `<6500` phải chạy sau toàn bộ phần thêm vào prompt và trước
`_invoke_with_retry`. Khi vượt trần phải báo lỗi cấu hình có chẩn đoán; không cắt
chuỗi BRPP, bỏ task hoặc gửi prompt vượt giới hạn. Runtime này chưa được tích hợp
trong W3; `runtime_budget_gate_passed=false` là điều kiện còn mở ở W4.

## 5. Giới hạn nghiên cứu và dữ liệu

- 852 episode phủ **2020–2022** do warm-up 600 phiên; không có 2018–2019 trong kho.
- 852/852 sentiment NEUTRAL vì thiếu tin lịch sử đủ độ tin cậy; sentiment không
  phân biệt similarity. Không kết luận reliability của LLM từ các tỷ lệ mẫu.
- Stats là tỷ lệ thực nghiệm theo population, không là xác suất thắng đã hiệu chuẩn.
  So sánh các nhánh prior giữ stats chung; so với Original có cả tác động stats/ví dụ.
- Giá thô VCI/KBS đã mở gate tạo kho; **gate giá kiểm định 2023–2024 còn mở**.
  Cần mở trước pilot/backtest chính thức; không dùng CSV điều chỉnh W1 tính nhãn.
- HMM/scaler toàn train dành cho minh họa hồi cứu; query lịch sử dùng prefix PIT.
- Smoke, benchmark và E2E fixture không là kết quả lợi nhuận ngoài mẫu; p95 áp dụng
  môi trường đo được ghi trong receipt, không bảo đảm mọi mẫu hoặc máy khác <30 ms.

## 6. Cấu trúc tài liệu và bằng chứng lịch sử

Theo thay đổi người dùng, tuần được đặt tại **`docs/plan/week<N>/`**; kế hoạch tổng
là `docs/plan/plan.md`. Quy ước đã ghi trong [AGENTS.md](../../../AGENTS.md) để các
tuần tiếp theo giữ cùng cấu trúc. W2/W3 được chuyển vào cây này; script/test/default
QA/output và liên kết Markdown đã cập nhật.

JSON receipt đã đóng băng được giữ nguyên byte khi chuyển. Các path bên trong
receipt cũ mô tả lần chạy lịch sử tại vị trí cũ; khi đối chiếu dùng ánh xạ
`docs/week2/`→`docs/plan/week2/`, `docs/week3/`→`docs/plan/week3/`, rồi vẫn so hash.
Đối với primary ngân sách/smoke cần refresh do code đường dẫn đã thay đổi, giữ bản
trước ở `prompt_budget_review_before_week_close.json` và
`prior_smoke_before_week_close.json`; kết quả mới dùng path/hash hiện tại.
Receipt benchmark W3-14/W3-15 giữ riêng, không sửa mẫu đo hoặc thay hash cũ để PASS.

## 7. Chạy lại kiểm chứng

Tại thư mục gốc repo, chạy tuần tự; dùng tên output benchmark chưa tồn tại:

```powershell
py -3.13 -X utf8 scripts/verify_prior_prompt_budget.py
py -3.13 -X utf8 scripts/verify_bayesian_prior.py
py -3.13 -X utf8 scripts/benchmark_bayesian_retriever.py --output docs/plan/week3/retrieval_benchmark_rerun_close.json
py -3.13 -m compileall agents core data_manager scripts tests utils
py -3.13 -X utf8 -m unittest discover -s tests -v
py -3.13 scripts/run_end_to_end_test.py
py -3.13 -X utf8 -m unittest discover -s tests -p 'test_*leakage.py' -v
```

Smoke/benchmark cần archive local đã đóng băng; thiếu/sai hash phải dừng kiểm chứng,
không gọi LLM, fit HMM hoặc sinh thêm episode để bù. Log gate nằm trong thư mục tạm
ghi trong receipt chốt; code/dữ liệu/bằng chứng trên Git đủ để đối chiếu kết quả,
archive và khóa API tiếp tục được quản lý ở máy chạy.

## 8. Kết quả nghiệm thu cuối

Compileall PASS, **339/339 unit** (gồm 104 Bayesian), E2E xác định PASS,
**56/56 leakage** PASS. Ví dụ replay offline đã chạy đúng bốn mode và Original.
Ngân sách/smoke và benchmark được chạy lại ở thư mục mới; p95 retrieval
Bayesian/Random/Recent/Similarity **15,483 / 13,874 / 13,981 / 17,621 ms**, đều <30 ms.
Chi tiết lệnh/mã thoát/thời gian/hash tại [receipt](week_close_review.json) và
[nhật ký Phase D](phase_d_validation_and_handoff.md). W3 sẵn sàng cho tích hợp W4;
runtime budget và kết quả giao dịch OOS vẫn chưa được nghiệm thu.
