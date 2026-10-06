# W4-15 — Bốn gate, phạm vi thay đổi và hiệu năng

**Bốn gate bắt buộc PASS, có cảnh báo hiệu năng ngày 06/10/2026; nhánh `test/prior-integration-gate-review`.**
Phụ thuộc: [smoke W4-14](prior_integration_smoke.md). Theo dõi:
[Phase D](phase_d_validation_handoff.md), [checklist W4](README.md).

## Kết quả nghiệm thu mới ngày 06/10/2026

[Receipt gate](integration_gate_review.json) và [receipt hiệu năng](integration_performance_review.json)
lưu lệnh/log/hash, mẫu thời gian thô, cấu hình và giới hạn. Bốn gate chạy tuần tự
trên baseline `23a3246` cộng công cụ đo mới; production giữ nguyên.

| Gate | Kết quả | Thời gian toàn tiến trình (giây) |
| --- | --- | ---: |
| compileall | PASS | 0.208 |
| unit | PASS; 498 test | 537.491 |
| e2e | PASS | 31.784 |
| leakage | PASS; 93 test | 168.676 |

| Mode | p95 retrieval (ms) | Gate <30 ms |
| --- | ---: | --- |
| bayesian_regime | 35.550 | FAIL |
| random | 30.915 | FAIL |
| recent | 31.740 | FAIL |
| similarity | 40.643 | FAIL |

| Bước tích hợp riêng | p95 (ms) |
| --- | ---: |
| source_validator | 31.441 |
| adapter_retrieve | 41.135 |
| formatter | 0.141 |
| prepared_decision_node_mock | 2.457 |
| report_decision_graph_mock | 107.029 |

Cold adapter constructor **20344.948 ms**; retriever constructor=1, memory load=1. Sáu context prefix có 9 model load khi chuẩn bị/đối chiếu proof; không nạp lại ở phép đo nóng. Prepare/journal từng context và mọi mẫu thô nằm trong receipt.

**2427 file bảo vệ giữ hash**, bank 852 episode và receipt cũ nguyên byte; bảy AST kinh tế/entry point legacy không đổi. **`runtime_budget_gate_passed=true`** tại receipt mới; prompt synthetic max 4193, observed max 4423; biên BRPP 600/prompt 6.499 nhận/6.500 chặn được giữ từ runtime smoke hiện hành.

**Benchmark hiện tại FAIL**; không dùng số W3 để thay lượt mới. Mã retriever, memory/copy và phương pháp benchmark không đổi, điều kiện phải nghiệm thu lại p95 khi sửa các phần này trong checklist W4-15 không kích hoạt. Task hoàn tất rà rủi ro và bốn gate bắt buộc; cảnh báo p95 cần kiểm lại khi giảm tải/đổi môi trường trước công bố số hiệu năng hoặc pilot. Không tối ưu ngoài phạm vi khi gate bắt buộc đã đủ.

**Phase D 3/4, W4 15/16**. W4-16/Gate D và gate giá OOS/pilot còn mở; không suy ra chất lượng đầu tư hoặc độ trễ LLM thật từ kiểm offline.

## Phạm vi rà soát

Task này bổ sung công cụ `scripts/review_prior_integration_performance.py`,
receipt và tài liệu nghiệm thu. Rà danh sách file từ commit nền W4 và trên
task hiện tại; băm nguồn/QA/kho/model/archive/receipt/schema trước và sau gate.
Bảy AST hàm kinh tế/entry point legacy được so với nền đầu tuần, gồm
`compute_round_trip_net_return`, `compute_account_metrics`, `_get_actual_direction`,
`_run_ablation_variants`, `_run_paired_point`, `_parse_prediction`, `run`.

Retriever và memory giữ nguyên mã so với W3; thêm guard/copied state/model proof
trong adapter/graph W4 được rà riêng. Prior vẫn mặc định tắt. Không thay công
thức LONG/SHORT, phí, nhãn bank, scope/seed/ma trận so sánh, tải tin/giá hoặc fit
lại model. W4-16 và Gate D vẫn chờ biên bản đóng tuần/bàn giao.

## Ngân sách runtime

Đối chiếu receipt W4-14 với checksum code hiện tại; lưu hash template VI/EN,
hướng dẫn reasoning, formatter BRPP và phiên bản retriever/runtime.
Cap backtest tổng 4.000: trend/pattern/indicator 800 mỗi loại, Alpha 1.100,
sentiment 500. Prompt cuối phải `<6500`, BRPP `≤600`.

Smoke W4-14 dùng adapter/graph/source thật và LLM giả, không patch cap/builder;
fixture biên prefix riêng đạt 600, prompt 6.499 nhận/6.500 chặn trước LLM.
Receipt mới chỉ chuyển `runtime_budget_gate_passed=true` khi kiểm chứng này
cùng hash nguồn và gate hiện tại đạt. Không sửa trạng thái lịch sử trong
receipt W3 hoặc receipt W4 trước đó; gate giá/OOS/pilot là điều kiện riêng.

## Phương pháp đo

Gọi trực tiếp hàm `benchmark()` đang dùng ở W3, giữ nguyên script và receipts
cũ. Receipt mới nằm tại `docs/plan/week4/`: kho thật 852 episode, 16 context
PIT, bốn mã × bốn regime, bốn mode, hai scope, K=3, seed=42. Mỗi mode/bước
có 100 warm-up và 1.000 mẫu; `perf_counter_ns`, p95 nearest-rank, không loại
mẫu ngoại lai, không giảm số mẫu hoặc đổi ngưỡng. Ngưỡng xét **retrieval API
p95 <30 ms**; formatter và retrieval+format là hai phép đo riêng.

Cold load và chuẩn bị nguồn nằm ngoài timer retrieval. Mọi output được so
với smoke/oracle ngoài timer, giữ nguyên kiểm schema/snapshot/cutoff và copy.
JSON/giá/network/fit bị chặn ở query nóng trong phương pháp W3.

Phép đo bổ sung qua adapter dùng sáu context replay W4-14, báo cáo W2 đã được
xác minh, Decision structured giả; không gọi lại upstream/Alpha/vision:

| Bước | Timer bao gồm |
| --- | --- |
| Constructor adapter | Nạp/kiểm kho, manifest/QA, giá/tin/VNINDEX và pin nguồn |
| Prepare + journal | Cắt PIT, model prefix/suy luận/proof và kiểm run/episode/signals |
| Source validator | Copy projection, kiểm nguồn/shared và đọc byte checksum |
| Adapter retrieve | Copy projection/result, verifier/query, checksum và retrieval |
| Formatter | BRPP trên result thật đã xác minh |
| Prepared Decision node | Copy state, distill/cap/builder/guard, Decision giả và parse |
| Report → Decision graph | LangGraph, verifier/retrieval/formatter/Decision giả đầy đủ |

Có 6 warm-up và 120 mẫu mỗi bước bổ sung, luân phiên sáu context (20 mẫu/context).
Overhead này **không áp ngưỡng 30 ms của retrieval** và không gồm checkpoint/fsync,
upstream hoặc độ trễ LLM thật. Không đặt thời gian thật trong unit assertions.

Đếm constructor retriever và `HistoricalMemory.load()`; đường query sau chuẩn
bị cấm nạp lại JSON, giá, bank hoặc model. Kiểm byte checksum của adapter vẫn
giữ nguyên: graph có I/O xác minh byte, nên không gọi toàn graph là query chỉ
chạy trên RAM. Fixed-train nạp model một lần được kiểm bằng unit hiện có;
prefix replay nạp artifact theo endpoint, có thêm đối chiếu độc lập khi cache
proof chưa có endpoint. Không trộn số model load với số lần nạp bank.

## Lần đo đầu và điều kiện môi trường

Lượt đầu: Bayesian 27,646 ms, Random 25,252 ms, Recent 24,729 ms PASS;
Similarity **32,215 ms FAIL**. Mã retriever/memory không đổi; lúc khảo sát máy
có CPU khoảng 45%, chạy LeagueClient/Riot. Đây là quan sát tải nền, chưa đủ để
khẳng định nguyên nhân duy nhất của FAIL. Giữ log/hash lần này trong receipt
mới; không thay số đo bằng số cũ W3 hoặc xóa bằng chứng FAIL.

Profile riêng 30 query Similarity/pooled: chi phí chính là `_matches_snapshot`,
copy bản ghi và `normalize_signals`. Profile có overhead instrumentation,
**không dùng thời gian profile để xét p95**. Không thay thuật toán, bỏ validation,
nới cutoff/cap/threshold hoặc thay cấu hình nguồn để làm gate PASS. Đo lại tuần
tự sau bốn gate, khi không có suite test chạy cạnh tranh CPU.

## Chạy lại bằng terminal

Từ gốc repo, chọn receipt mới chưa tồn tại:

```powershell
py -3.13 -X utf8 scripts/review_prior_integration_performance.py --output docs/plan/week4/integration_performance_rerun.json
py -3.13 -m compileall agents core data_manager scripts tests utils
py -3.13 -X utf8 -m unittest discover -s tests -v
py -3.13 scripts/run_end_to_end_test.py
py -3.13 -X utf8 -m unittest discover -s tests -p 'test_*leakage.py' -v
```

Chạy tuần tự các phép đo để tránh tự tạo tải nền. Receipt giữ mẫu thô, môi
trường, timer, số lượt, coverage, config/hash/version và giới hạn. Receipt FAIL
cũng được lưu; CLI trả mã thoát 1 khi ngưỡng retrieval chưa đạt. Thiếu/sai
archive/proof phải dừng kiểm chứng, không thay bằng query synthetic.

## Giới hạn

Đây là nghiệm thu kỹ thuật offline. Tin W2 thiếu coverage vẫn NEUTRAL; bank
2020–2022, Decision giả, thống kê là tỷ lệ thực nghiệm. Thời gian phụ thuộc
máy/tải nền; không suy ra hiệu năng API thật hoặc hiệu quả đầu tư OOS.
W4-15 chốt bốn gate, ngân sách, hash/scope và rà rủi ro hiệu năng theo điều kiện
trong checklist; benchmark bổ sung vẫn FAIL. Không công bố ngưỡng p95 đã đạt
trên môi trường hiện tại hoặc dùng nghiệm thu này để mở pilot/OOS.
