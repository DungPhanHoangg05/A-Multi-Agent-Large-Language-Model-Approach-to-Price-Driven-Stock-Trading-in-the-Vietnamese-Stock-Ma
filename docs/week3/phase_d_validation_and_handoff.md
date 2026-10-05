# Phase D — kiểm thử, hiệu năng và bàn giao W4

**Trạng thái: W3-13 hoàn thành; W3-14/W3-15/W3-16 chưa thực hiện.** Gate C offline
đã PASS; tiếp theo benchmark W3-14, Phase D chưa chốt.
Smoke [receipt](prior_smoke.json) không thay benchmark p95 hoặc gate runtime W4.

## W3-13 — hành vi và zero-leakage

- [x] Hợp nhất test truy vấn/mode/stats/prefix đã làm; bổ sung lỗi đầu vào và serializable.
- [x] `tests/test_bayesian_retriever_leakage.py`: mọi mode loại `exit_date == cutoff`,
  `exit_date > cutoff` và episode bắt đầu trước nhưng kết thúc sau cutoff.
- [x] Thêm/đổi record tương lai trong fixture hợp lệ không đổi IDs, stats hoặc prefix
  của query cũ; kiểm cả cache khi lần lượt gọi ngày sau rồi ngày trước.
- [x] Sai hậu điều kiện từ nguồn eligible bị giả lập phải ném lỗi, không silently lọt prior.
- [x] Tách query signals khỏi outcome; kiểm không thay state/record giữa các nhánh.
- [x] Prefix không chứa nhãn kết quả của test point; thống kê không nhìn toàn kho
  khi cutoff lịch sử loại một phần record.

## W3-14 — benchmark retrieval

File dự kiến `scripts/benchmark_bayesian_retriever.py`, receipt
`docs/week3/retrieval_benchmark.json` và biên bản hiệu năng trong file này.

**Phép đo đề xuất khóa tại W3-01 trước khi chạy benchmark:**

- Dùng kho thật 852 record và query cố định bao phủ bốn mã/bốn regime, K=3;
  ghi nguồn regime của query. Cùng tập query/config cho mọi mode.
- Đo cold load/xác minh kho riêng; hot query gồm lọc eligible, ranking, thống kê,
  metadata và deep copy. Đo formatter riêng và end-to-end retrieval+format riêng.
- Dùng `perf_counter_ns`, 100 lượt warm-up/mode và ít nhất 1.000 lượt đo/mode;
  luân phiên query để không chỉ đo một điểm cache trúng. Ghi query count, cache và
  min/median/p95/max; đo tuần tự để tránh nhiễu tranh tài nguyên.
- **Gate retrieval:** p95 hot query **<30 ms ở từng mode**, không chỉ trung bình gộp.
  Không tính I/O nạp kho/LLM vào gate; vẫn báo thời gian cold load công khai.
- Ghi Python/dependency/CPU/OS, bank hash, seed/config, phương pháp percentile và ngày đo.
  Threshold không đặt làm unit test thời gian dễ chập chờn trên máy khác.

- [ ] Script/receipt tái lập, đủ bốn mode và môi trường.
- [ ] Nếu vượt ngưỡng: chỉ tối ưu nút chậm đã đo; không bỏ validation/cutoff/deep copy.
- [ ] Sau tối ưu chạy lại test liên quan và benchmark cùng phép đo; không đổi gate
  sau khi nhìn kết quả để báo PASS.

## W3-15 — gate tích hợp

Chạy tại thư mục gốc repo:

```powershell
py -3.13 -m compileall agents core data_manager scripts tests utils
py -3.13 -X utf8 -m unittest discover -s tests -v
py -3.13 scripts/run_end_to_end_test.py
py -3.13 -X utf8 -m unittest discover -s tests -p 'test_*leakage.py' -v
```

- [ ] Bốn gate PASS; ghi số test/thời gian/commit, không dùng kết quả W2 thay kết quả W3.
- [ ] Diff không đổi engine P&L, upstream ghép cặp, artifact kho/model hoặc cơ chế retry.
- [ ] Gate smoke/600 ký tự/6.500 ký tự/30 ms có bằng chứng trước merge.

## W3-16 — chốt và bàn giao

- [ ] Đủ module, formatter, unit/leakage tests, smoke, benchmark, đặc tả đã khóa.
- [ ] Ghi API/example cho W4: regime PIT và tín hiệu hiện tại vào query; tasks/stats,
  BRPP/IDs/hash/seed/fallback ra ngoài; Original K=0 không nhận prefix.
- [ ] Nêu rõ việc W4 cần làm: trường state, inject Decision, ablation flag, checkpoint
  metadata, paired upstream và chốt giới hạn prompt tại runtime. Theo
  [receipt W3-11](prompt_budget_review.json), cap cũ tổng 4.500 vượt trần khi ghép
  BRPP: phải áp dụng cap bàn giao tổng 4.000 (hoặc kiểm chứng phương án khác) và
  guard `<6500` sau toàn bộ hướng dẫn. Không lấy PASS offline làm PASS runtime.
- [ ] Giữ giới hạn tin/độ phủ/gate giá 2023–2024; W3 không phát hành kết quả lợi nhuận OOS.
- [ ] Cập nhật README W3, kế hoạch tổng và biên bản chốt; Conventional Commit/merge
  từ nhánh task vào `develop` sau đủ gate; không đưa mã tuần/ngày vào commit message.

## Kết quả và nhật ký

### 05/10/2026 — W3-13 hoàn thành

**Đầu ra:** mở rộng `tests/test_bayesian_retriever_leakage.py` thêm mười test
`BayesianPriorPipelineLeakageTests`; thêm hai test trong
`tests/test_bayesian_prior_behavior.py`. Fixture chung `tests/bayesian_test_support.py`
có hai mã/tám record, giá và lịch phiên giả lập, nhãn sinh bằng
`compute_round_trip_net_return`; constructor vẫn chạy schema/validator kinh tế thật.
Không sửa code runtime, kho/model, P&L hoặc cơ chế gọi LLM.

#### Phạm vi kiểm chứng

| Yêu cầu | Bằng chứng trong test mới |
| --- | --- |
| Exit bằng cutoff, vắt ngang và sau cutoff | `test_equal_exit_straddling_and_future_query_are_excluded_from_final_evidence`: bốn mode × hai scope × K=1..3, đối chiếu cả tasks/stats/BRPP; n=0/N/A tại exit đầu |
| Thêm tương lai không đổi query cũ | `test_valid_future_append_does_not_change_ids_stats_scores_seed_or_prefix`: record mới qua validator thật; chỉ hash kho đổi |
| Sửa tương lai hợp lệ không đổi query cũ | `test_valid_future_price_signal_regime_and_outcome_changes_leave_old_prefix_unchanged`: sửa giá sau cutoff, tín hiệu/regime của chu kỳ chưa đóng, sinh lại nhãn bằng engine; kiểm cả bốn mode/hai scope |
| Ngày sau rồi ngày trước | `test_late_queries_then_early_queries_cannot_reuse_future_stats_or_prefix`: query sau có nhiều history hơn; query cũ nhận lại nguyên bundle, không dùng pool/stats/prefix ngày sau |
| Source/bộ chọn/population sai phải gây lỗi | Ba test `test_poisoned_eligible_sources_fail_before_prefix_in_every_mode_and_scope`, `test_corrupt_selectors_cannot_inject_a_future_task_into_prefix`, `test_poisoned_statistics_population_fails_after_selection_before_prefix`: future/equal/duplicate/unknown ID/NaN/scope/regime/nhãn sai → ValueError **trước formatter**, không lọc âm thầm |
| Query không cung cấp outcome | `test_query_outcome_and_query_id_cannot_appear_in_prior_evidence`: query có WIN ở tương lai nhưng bị loại; prior cùng mã chỉ 1/2 WIN, ngày/ID query không vào prefix hoặc selected IDs |
| Cách ly nhánh và input | `test_branch_mutations_do_not_change_shared_query_bank_or_other_bundles`: cùng object tín hiệu cho các nhánh; sửa tasks/stats/metadata nhánh trả về không đổi query, kho, nhánh khác hoặc lần truy vấn mới |
| Không ranking bằng nhãn | `test_past_labels_change_evidence_but_never_select_winners_by_outcome`: đổi giá/nhãn **đã đóng** hợp lệ thì stats/BRPP đổi, nhưng IDs/scores/seed giữ nguyên; không đòi evidence bất biến khi lịch sử đã biết thay đổi |
| Validation và JSON toàn pipeline | Hai test behavior: 56 cấu hình input sai bị từ chối trước truy cập pool, kể cả K=0; 256 tổ hợp mode/scope/regime/K=0..3 serialize JSON strict bằng kiểu Python gốc, không I/O query hoặc sửa input |

Các test cũ giữ nguyên; dùng `unittest discover` để hợp nhất suite, không copy hoặc
viết lại test thuật toán. Phạm vi các file và số test method:

| File `tests/` | Số test | Phạm vi |
| --- | ---: | --- |
| `test_bayesian_retriever.py` | 11 | Kho/QA/query/pool/hậu điều kiện nền |
| `test_bayesian_recent_random.py` | 7 | Thứ tự/seed/RNG/thiếu mẫu/metadata |
| `test_bayesian_similarity.py` | 9 | Score/alias/tie-break/không ranking bằng outcome |
| `test_bayesian_regime_selection.py` | 9 | Population cùng regime/scope và bộ chọn Bayesian |
| `test_bayesian_statistics.py` | 11 | Counts/mẫu số/null/zero-return/deep copy |
| `test_bayesian_prior_prefix.py` | 13 | Template/schema/nhãn/600/NFC/lỗi formatter |
| `test_bayesian_prompt_budget.py` | 9 | Biên 600/prompt VI-EN/ngân sách bàn giao W4 |
| `test_bayesian_prior_smoke.py` | 6 | Receipt kho thật/nguồn PIT/biên/từ chối bằng chứng sai |
| `test_bayesian_retriever_leakage.py` | 18 | Tám test nền và mười test toàn pipeline |
| `test_bayesian_prior_behavior.py` | 2 | Validation/JSON toàn pipeline |
| **Tổng** | **95** | Unit/API độc lập và kiểm chứng offline |

Lệnh chạy suite hợp nhất:

```powershell
py -3.13 -X utf8 -m unittest discover -s tests -p 'test_bayesian*.py' -v
```

**Kết quả W3-13:** suite **95/95** test Bayesian PASS (3,854 giây); cả bốn gate
tích hợp task PASS:

| Gate | Kết quả |
| --- | --- |
| Compileall `agents core data_manager scripts tests utils` | PASS |
| Unit tests toàn hệ thống | **330/330 PASS**, 48,346 giây |
| E2E xác định | **PASS**, 7,2 giây |
| `test_*leakage.py` toàn hệ thống | **56/56 PASS**, 5,360 giây |

Lệnh bốn gate là khối trong mục W3-15 phía trên; kết quả này là lượt tích hợp
**W3-13**, chưa đánh dấu W3-15 hoàn thành. Hash nguồn/bằng chứng receipt W3-11/12,
liên kết Markdown và `git diff --check` được kiểm trước commit.
Nhánh `test/prior-zero-leakage-suite` tích hợp sau gate. Phải chạy lại gate chốt
tuần sau benchmark W3-14 và mọi tối ưu cần thiết. Chưa có phép đo p95 hoặc bàn giao
chốt W3-16; ngân sách runtime W4/gate giá kiểm định 2023–2024 và giới hạn thiếu tin
vẫn còn. Các receipt trước được giữ nguyên vì code/corpus được chúng xác minh không đổi.
