# Tối ưu retrieval và xử lý cảnh báo p95

**PASS ngày 07/10/2026**, nhánh `refactor/prior-retrieval-performance`, nền `2033af6`.
Task bổ sung sau [đóng W4](week_close_and_handoff.md); W4 vẫn 16/16 task.
Các receipt W4-15/W4-16 giữ nguyên trạng thái lịch sử. Kết quả mới tại
[retrieval_performance_resolution_review.json](retrieval_performance_resolution_review.json).

## Kết quả nghiệm thu ngày 07/10/2026

[Receipt xử lý cảnh báo](retrieval_performance_resolution_review.json),
[baseline trước sửa](integration_performance_before_optimization_20261007.json),
[benchmark sau sửa](integration_performance_optimized_20261007.json),
[smoke bản tối ưu](integration_smoke_optimized_20261007.json).

| Mode | Baseline p95 (ms) | Sau sửa p95 (ms) | Giảm đo được | Gate <30 ms |
| --- | ---: | ---: | ---: | --- |
| bayesian_regime | 34.839 | 11.559 | 66.8% | PASS |
| random | 30.070 | 10.837 | 64.0% | PASS |
| recent | 29.015 | 10.927 | 62.3% | PASS |
| similarity | 37.286 | 13.235 | 64.5% | PASS |

Compileall, **502 unit** (434.801 giây suite), **E2E** (15.269 giây), **93 leakage** (99.993 giây suite) PASS. **2432 file bảo vệ giữ hash**; bảy AST kinh tế/legacy nguyên vẹn. Bốn test mới bổ sung vào 498 test hiện có.

Smoke mới: 8 context tổng hợp/bốn regime/VI-EN, K=0..3, paired/đảo nhánh/resume, 6 replay quan sát thật với Decision giả, budget boundary và flag off PASS. Toàn bộ query/context/IDs/metadata trong benchmark trước/sau khớp; output từng mẫu sau sửa khớp oracle/smoke W3 đã đóng băng.

Profile cùng 30 query: snapshot guard **109.170 lần cả trước và sau**; copy tổng quát **150 → 90 lần**, hai bước copy pool chuyển sang copy ba dict sau kiểm snapshot. Đây là số call, không dùng thời gian profile để xét p95.

**Cảnh báo p95 đã được đóng cho phiên bản/môi trường đo này.** W4 giữ 16/16; Gate D kỹ thuật offline và gate hiệu năng PASS. Receipt W4-15/W4-16 vẫn ghi trạng thái lịch sử có cảnh báo; receipt bổ sung này là bằng chứng xử lý mới. Gate giá OOS/model/quota/CLI/pilot vẫn BLOCKED hoặc chưa thực hiện.

## Phạm vi và nguyên nhân được đo

Profile mới trước sửa trên 30 query Similarity/pooled FPT 2022-12-27:
`_matches_snapshot`, `copy_historical_records` và `normalize_signals` là ba chi
phí chính. Profile có instrumentation, không lấy thời gian profile xét gate.
Baseline mới trên cùng phương pháp vẫn FAIL; tải CPU quan sát khoảng 6% tại
một thời điểm khảo sát, không kết luận tải nền là nguyên nhân duy nhất.

Mã thay đổi chỉ ở [bayesian_retriever.py](../../../core/bayesian_retriever.py).
Memory loader, schema, chọn mẫu/ranking/seed, thống kê, formatter, adapter và
kinh tế giữ nguyên. Không gọi LLM, tải nguồn, fit model hoặc thay bank/archive.

## Các thay đổi

1. Biên dịch bảng alias cố định thành lookup nhãn → hướng một lần lúc import;
   từ chối nhãn thuộc nhiều hướng. Mỗi lần `normalize_signals` vẫn kiểm đủ năm
   trường, kiểu chuỗi gốc, Unicode NFC/strip/upper và alias đúng miền.
   Lookup không chứa dữ liệu lịch sử, cutoff, ranking hay kết quả query.
2. `prepare_query` dùng `_copy_verified_pool` ngay sau các `_assert_pool`.
   Snapshot đã xác minh đầy đủ shape, kiểu và giá trị, gồm hai dict con với lá
   bất biến. Sao chép riêng record/signals/outcome cho từng pool, tránh lặp
   kiểm kiểu mọi lá lần nữa trong bước copy. Loader và các copy khác giữ nguyên.
3. Bỏ lời gọi `bool()` dư trong so sánh lá snapshot; phép bằng và kiểm kiểu
   chính xác vẫn giữ nguyên, nhánh lỗi vẫn trả bool Python gốc.

Mọi kiểm pool trước chọn, kiểm selected và kiểm population trước tính stats
vẫn chạy. Cutoff vẫn `exit_date < as_of_date`, không bỏ validation hoặc đưa
cache kết quả từ query sau sang query trước. Không giảm mẫu hay nới ngưỡng.

## Kiểm chứng hành vi

[Test mới](../../../tests/test_bayesian_retrieval_optimization.py) kiểm toàn bộ
alias/Unicode/case/whitespace; từ chối alias sai, NumPy và bool giả kiểu;
source bị mượn vẫn được copy độc lập; hai pool không chia sẻ dict con;
thứ tự key và query lặp giữ kết quả. Các test Bayesian/leakage hiện có kiểm
future/equal-exit, selector/population bị can thiệp, native JSON, K=0..3,
empty/partial và seed/IDs/stats/BRPP. Không đặt ngưỡng thời gian thật trong unit.

## Phương pháp benchmark

Dùng nguyên script/phương pháp W3 thông qua công cụ W4, chạy tuần tự trước
và sau sửa: 852 record, 16 context PIT, bốn mode/hai scope, K=3/seed=42,
100 warm-up và 1.000 mẫu/mode/bước, `perf_counter_ns`, p95 nearest-rank.
Giữ toàn bộ mẫu, kiểm output với smoke/oracle đã đóng băng ngoài timer.
Ngưỡng **retrieval API p95 <30 ms** xét từng mode; cold load, formatter và
overhead adapter/checksum/graph đo riêng. Query nóng chặn JSON/giá/network/fit.

```powershell
py -3.13 -X utf8 scripts/review_prior_integration_performance.py --output docs/plan/week4/integration_performance_new_run.json
```

Chọn tên mới chưa tồn tại; CLI từ chối ghi đè và lưu cả FAIL với mã thoát 1.
Baseline/FAIL cũ không được xóa hoặc thay bằng kết quả PASS mới.

## Phạm vi kết luận và vận hành

Chỉ đóng cảnh báo p95 khi bốn mode đạt trên lượt nghiệm thu cùng phiên bản
chuẩn bị merge và bốn gate compileall/unit/E2E/leakage PASS. Kết quả áp dụng
cho môi trường/phương pháp đo, không bảo đảm mọi máy hoặc mọi request <30 ms.

Prior vẫn mặc định tắt; cap BRPP ≤600 và prompt <6.500 giữ nguyên. Chỉnh mã
retriever làm thay fingerprint code: không ép resume run nghiên cứu ký bằng
bản code khác. Artifact W2/historical reports tiếp tục được đọc theo identity
bên tạo và nguồn đã xác minh; không đóng dấu lại bằng code mới.

Gate giá OOS/model/quota, CLI và pilot W5 vẫn chưa PASS. Tối ưu tốc độ retrieval
không là bằng chứng đầu tư ngoài mẫu hoặc khả năng tránh mọi lỗi API/quota.
