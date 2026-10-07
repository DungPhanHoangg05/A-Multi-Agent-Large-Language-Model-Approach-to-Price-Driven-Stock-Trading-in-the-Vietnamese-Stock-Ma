# Phase D — Kiểm chứng tích hợp và bàn giao W5

**Trạng thái: W4-13..16 hoàn thành ngày 06/10/2026; Phase D 4/4. Gate D PASS kỹ thuật offline; cảnh báo p95 đã xử lý ngày 07/10/2026.**
[Biên bản tối ưu](retrieval_performance_resolution.md), [receipt bổ sung](retrieval_performance_resolution_review.json).
[Biên bản leakage](pipeline_leakage_validation.md), [receipt leakage](pipeline_leakage_review.json),
[biên bản smoke](prior_integration_smoke.md), [receipt smoke](integration_smoke.json),
[biên bản gate](integration_gate_validation.md), [receipt gate](integration_gate_review.json),
[hiệu năng](integration_performance_review.json), [checklist W4](README.md).
[Biên bản bàn giao](week_close_and_handoff.md), [receipt chốt](week_close_review.json).
Tiếp theo lập kế hoạch W5; gate giá/model/quota và pilot/OOS còn mở.
Đầu vào: Gate C. Nghiệm thu trên đường state → PIT adapter → retriever →
formatter → graph → Decision → checkpoint thực tế; chỉ thay inference bên
ngoài bằng LLM giả định xác định.

## W4-13 — Leakage trên toàn đường tích hợp

**Phụ thuộc:** Gate C. **Test:** `tests/test_prior_pipeline_leakage.py`.
Tái sử dụng `test_regime_leakage.py`, `test_bayesian_retriever_leakage.py`,
sentiment/alpha/execution-price/historical leakage đã có; không viết lại detector.

- [x] Giá/feature sau cutoff và snapshot sai ngày gây lỗi trước agent/retrieval;
  outcome query không xuất hiện trong signals/state/prompt.
- [x] Tin tương lai không được dùng, tin không ngày bị loại; kiểm metadata
  coverage và NEUTRAL không bị chuyển thành bằng chứng tích cực.
- [x] HMM/scaler/calibration train tương lai, state/feature/source/hash sai gây
  lỗi trước query; kiểm cả provider replay và model train cố định.
- [x] Prior exit bằng cutoff, chu kỳ vắt ngang và exit tương lai không nằm trong
  tasks, ranking, stats hoặc BRPP của bất kỳ mode/scope nào.
- [x] Thêm/sửa lịch sử chưa đóng không đổi IDs/scores/stats/prefix của query cũ;
  truy vấn ngày sau rồi ngày trước không tái dùng cache chứa lịch sử tương lai.
- [x] Nếu selector/provider bị can thiệp trả dữ liệu sai, validator phải ném
  ValueError/AssertionError; không silently skip, nới regime/scope hoặc trả empty.
- [x] Checkpoint giả/sửa cutoff/nguồn/model future không thể resume; kiểm spy
  chứng minh không có LLM call khi provenance/cutoff thất bại.

**Nghiệm thu:** bảng coverage ghi từng ca, mode và đường chạy; fixture nhãn
từ engine thật. [Receipt](pipeline_leakage_review.json) và suite PASS.

**Kết quả 06/10/2026:** 11 test mới; 40 graph ca biên hai provider/hai scope,
24 injection pool/selector/population, 12 mutation checkpoint băm lại. Provider
replay được đối chiếu độc lập với artifact/prefix; probe baseline nhận hash
train sai, bản sửa chặn trước upstream. Compileall/494 unit/E2E/93 leakage
PASS; [biên bản và coverage](pipeline_leakage_validation.md). Inference là
fixture, không mở gate OOS. W4-14..16 và Gate D còn mở.

## W4-14 — Smoke E2E offline và tương thích

**Phụ thuộc:** W4-13. **File chính:** `scripts/run_end_to_end_test.py`;
script riêng `scripts/verify_prior_integration.py`.

- [x] Giữ E2E legacy hiện có, bổ sung smoke runtime mới với mock text/vision LLM;
  PIT validation, retrieval, formatter, builder, graph và checkpoint chạy thật.
- [x] Smoke fixture tổng hợp tái lập từ Git: đủ bốn regime, năm nhánh, VI/EN,
  K=0..3, empty/partial, prefix/prompt boundary và điểm đủ ba phiên thực thi.
- [x] Replay kho thật nếu archive/proof local đầy đủ và đã xác minh: nhận bank/
  manifest/QA cố định, báo rõ số context/nhánh và độ phủ. Nếu thiếu archive,
  báo BLOCKED cho replay; không thay fixture thành quan sát thị trường thật.
- [x] Đối chiếu reports/IDs/stats/prefix giữa thứ tự nhánh và run/resume, call-count
  upstream/Full preparation, output kinh tế, JSON strict, hash trước/sau kiểm.
- [x] Flag off chạy bốn ablation và các entry point cũ, không nạp bank/model;
  không thay mã lỗi/output cũ để che regression.
- [x] Chặn network/LLM thật trong kiểm offline; receipt nêu rõ nguồn synthetic
  hay observed, phạm vi mock, config/version/hash, budget và giới hạn kết luận.

**Nghiệm thu:** [receipt](integration_smoke.json) PASS cho smoke bắt buộc
tái lập từ Git. Replay kho thật là bằng chứng bổ sung riêng; không hứa W4 PASS
cho phần replay chưa đủ nguồn, không suy ra lợi nhuận OOS từ mock.

**Kết quả 06/10/2026:** [Biên bản/CLI](prior_integration_smoke.md), 8 context
tổng hợp và 6 replay context thật/30 nhánh/60 Decision giả; production và E2E cũ
giữ nguyên. Bốn test mới; compileall/498 unit/E2E/93 leakage PASS.
Phase D 2/4, W4 14/16; W4-15..16/Gate D và giá OOS/pilot còn mở.

## W4-15 — Bốn gate và phạm vi thay đổi

**Phụ thuộc:** W4-14. Chạy tại thư mục gốc repo, ghi stdout/stderr/mã thoát
và thời gian; không dùng lại số test W3 làm kết quả W4.

```powershell
py -3.13 -m compileall agents core data_manager scripts tests utils
py -3.13 -X utf8 -m unittest discover -s tests -v
py -3.13 scripts/run_end_to_end_test.py
py -3.13 -X utf8 -m unittest discover -s tests -p 'test_*leakage.py' -v
```

- [x] Bốn gate PASS trên cùng phiên bản chuẩn bị merge; nếu fail sửa nguyên nhân
  và chạy lại gate liên quan. Không merge khi còn lỗi hoặc chưa có bằng chứng.
- [x] Kiểm hash kho/manifest/QA/model/receipt đóng băng trước/sau; `git diff --check`,
  liên kết tài liệu và scope thay đổi sạch, không key/output tạm lọt vào commit.
- [x] Kiểm cap/guard runtime đã PASS bằng receipt W4, không chỉ monkeypatch builder
  như W3. Lưu version/template và prompt max thực tế từ kiểm tích hợp.
- [x] Rà constructor/load một lần, retrieval trên RAM và overhead adapter/format
  riêng. Nếu thay retriever/copy/cache gây rủi ro hiệu năng, chạy lại benchmark
  W3 với cùng phương pháp, output receipt W4 mới và ngưỡng p95 retrieval <30 ms.
- [x] Không đặt thời gian thật trong unit assertions; cold load/format/orchestration
  không gộp thành số retrieval. Không mở tối ưu ngoài phạm vi khi gate đã đủ.

**Nghiệm thu:** [receipt](integration_gate_review.json) ghi commit/hash, lệnh,
log/hash, số test thực chạy, PASS và giới hạn; merge theo AGENTS.md.

**Kết quả 06/10/2026:** compileall/498 unit/E2E/93 leakage PASS mới; 2427 file giữ hash, bảy AST legacy
không đổi, default prior vẫn tắt. [Biên bản](integration_gate_validation.md),
[receipt hiệu năng](integration_performance_review.json): benchmark bổ sung **FAIL p95 <30 ms**;
cold load/verifier/adapter/formatter/graph đo riêng. Runtime budget PASS kỹ thuật
với cap/prefix/prompt và template/version hiện tại. Giữ cả hai lượt FAIL.
Retriever/memory/copy/benchmark không đổi; điều kiện phải nghiệm thu lại hiệu năng
khi sửa các phần này không kích hoạt. Task hoàn tất rà rủi ro; cảnh báo p95
cần kiểm lại khi giảm tải hoặc đổi môi trường trước công bố số đo/pilot.
Phase D 3/4, W4 15/16; W4-16/Gate D và giá OOS/pilot còn mở.

## W4-16 — Đóng tuần và bàn giao pilot

**Phụ thuộc:** W4-01..15. **Tài liệu:** [week_close_and_handoff.md](week_close_and_handoff.md).

- [x] Đối chiếu 16 task, contract, API/state/config, graph boundary, runtime caps,
  PIT/paired/checkpoint tests và receipts. Liệt kê bằng chứng còn BLOCKED riêng.
- [x] Ghi hướng dẫn bật/tắt prior, năm nhánh, daily timeframe, paths kho/QA,
  provider model, schema result và cách resume/đổi key/chẩn đoán signature mismatch.
- [x] Cập nhật README tuần, kế hoạch tổng và tiến độ repo; phân biệt W4 kỹ thuật
  hoàn tất với gate dữ liệu/pilot chưa PASS. Không bật mặc định prior khi đóng tuần.
- [x] Bàn giao W5 công việc CLI/pilot FPT 20 điểm, token/quota/format-error/call-count,
  log/checkpoint và điều kiện dừng; chỉ chạy LLM thật ở task W5 được yêu cầu.
- [x] Lập checklist mở gate giá kiểm định: chỉ vnstock/VCI và vnstock/KBS; giá thô
  OHLCV FPT/VCB/VNM/MWG và VNINDEX, lịch phiên/warm-up/exit đủ, không thiếu/trùng,
  source/adjustment/provenance nhất quán, manifest/hash và audit PASS. FPT pilot
  cần bộ FPT+VNINDEX; benchmark W6 cần đủ bốn mã.
- [x] Bàn giao điều kiện chốt provider/artifact PIT, ngân sách quota/key và sample dates
  trước pilot tại [biên bản W5](week_close_and_handoff.md#6-điều-kiện-mở-pilotoos--đang-blocked).
  Artifact/quota/ngày cụ thể chưa được xác nhận cho pilot khi gate OOS còn BLOCKED.
  Gate giá chưa mở hoặc thiếu model proof phải chặn pilot/OOS rõ ràng; không lấy
  CSV điều chỉnh W1 để tính nhãn hoặc dùng synthetic làm dữ liệu kiểm định.
- [x] Ghi giới hạn: kho 2020–2022, sentiment NEUTRAL, tỷ lệ thực nghiệm, Original
  khác cả stats/ví dụ; W4 offline không chứng minh hiệu quả đầu tư của mô hình.

**Nghiệm thu:** biên bản bàn giao liên kết đủ receipt và checklist 16/16.
`runtime_budget_gate_passed` chỉ chuyển true sau bằng chứng runtime W4;
trạng thái gate giá/OOS/pilot ghi theo kiểm chứng thực tế, không tự chuyển PASS.

## Gate D và cập nhật tiến độ

- [x] W4-13..16 hoàn thành, đủ bốn gate; deliverables runtime có hướng dẫn và bằng chứng.
- [x] Nhánh tích hợp local sau PASS; checkpoint/kho/key và file tạm không push kèm.
- [x] W5 có danh sách điều kiện mở pilot và giới hạn nghiên cứu rõ ràng.

Ghi nhật ký từng task tại đây và [README](README.md): ngày, commit, lệnh,
kết quả, receipt và phần còn mở. W4-13 đã có receipt riêng; các task còn lại
chỉ chốt sau kiểm chứng tương ứng.


**Kết quả W4-16 ngày 06/10/2026:** Compileall, **498 unit** (408.671 giây suite), **E2E** (28.010 giây), **93 leakage** (123.899 giây suite) PASS mới; **2431 file bảo vệ giữ hash**.
[Receipt](week_close_review.json) và [bàn giao](week_close_and_handoff.md) chốt 16/16 task.
Gate D PASS_OFFLINE_INTEGRATION_WITH_PERFORMANCE_WARNING; p95 vẫn FAIL,
không chuyển giá OOS/model/quota/pilot thành PASS. Prior mặc định tắt.


**Bổ sung 07/10/2026:** tối ưu retriever giữ guard/PIT/ownership; bốn mode p95 <30 ms, smoke mới và compileall/502 unit/E2E/93 leakage PASS. Đóng cảnh báo cho phiên bản/môi trường đo; giữ receipt và kết quả FAIL lịch sử. Gate giá/model/quota/CLI/pilot vẫn chưa PASS.
