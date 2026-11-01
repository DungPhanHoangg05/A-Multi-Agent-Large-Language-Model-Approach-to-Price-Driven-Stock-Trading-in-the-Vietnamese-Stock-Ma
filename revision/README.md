# Tiến độ xử lý phản biện

Kế hoạch chính: [../plan.md](../plan.md). Nhánh tích hợp của đợt phản biện: `fix`; luồng KLTN trên `develop` được quản lý riêng.

## R1 — bắt đầu bằng audit legacy

- [x] Thêm metrics hai lớp: support, confusion, accuracy, BA, MCC, macro-F1, precision/recall/F1 từng lớp và LONG rate; undefined dùng null/NA.
- [x] Replay offline Full, Base reports legacy, constant DOWN/CASH và constant UP/always-LONG cycles trên cùng lịch; xuất pooled, macro-over-symbols, common/own support và groups khi metadata thực có.
- [x] Định nghĩa [target net/gross và quy ước metric](target_contract.md); tách always-LONG cycles khỏi buy-and-hold và cycle-end khỏi daily drawdown.
- [x] Tạo manifest SHA-256 nguyên byte cho bằng chứng cục bộ hiện có, code replay và đầu ra; CLI kiểm tra hash và từ chối ghi đè bundle. Phiên bản submission vẫn **unverified**.
- [ ] Bổ sung frozen train/validation/test OHLCV/calendar, features PIT và daily equity; majority train, momentum, hai logistic, factor-only, exposure-matched control, buy-and-hold thật.
- [ ] Đánh giá đầy đủ qua folds/regimes/repeats; daily exposure, turnover, drawdown và execution/settlement contract.
- [ ] Sau bằng chứng mới, sửa abstract/highlights/introduction/results/conclusion và response có location đã kiểm chứng. **Chưa đóng R1.**

Không chạy LLM/API hoặc tải vendor data ở milestone này. Giữ nguyên artifacts lịch sử và manuscript; chưa có dữ liệu train/daily snapshot được khóa để hoàn thành các baseline còn lại một cách hợp lệ. Tập dữ liệu legacy là bằng chứng khám phá, không được tái gắn nhãn thành untouched confirmatory test.

## Vận hành offline

Từ repository root, Python 3.13.5 với NumPy/SciPy hiện có:

```powershell
py -3.13 -X utf8 scripts/audit_revision_baselines.py
py -3.13 -X utf8 scripts/audit_revision_baselines.py --verify outputs/revision/r1_legacy
```

Lần đầu xuất bundle mới tại `outputs/revision/r1_legacy/`: `report.json`, `classification.csv`, `economics.csv`, `README.md`, `manifest.json`. Bundle tồn tại thì runner từ chối ghi đè; dùng `--output-dir outputs/revision/<run_id_moi>` cho lần replay khác. Khi một mã có nhiều JSON đầu vào, chọn một release rõ ràng trong thư mục riêng qua `--result-dir`; runner không tự chọn file mới nhất.

Manifest ghi hash cả manuscript/reviewer/cache cục bộ nếu có; những file đang untracked/ignored không vì thế được phát hành hoặc chứng nhận thuộc submission. Fresh checkout thiếu các file này sẽ fail verify với thông báo đúng file thiếu. Metric replay chỉ cần chín result JSON đã theo dõi trong Git; có thể sinh bundle mới từ checkout đó và ghi nhận inventory thực có. Hash HEAD tại generation là mốc Git đang có; hash từng file mới/sửa là định danh code replay chính xác, kể cả lúc chưa commit. README tiến độ này không thuộc snapshot khóa để có thể tiếp tục cập nhật kết quả kiểm tra; target contract, kế hoạch tại thời điểm audit và code replay thuộc manifest.

Inventory chỉ lấy artifacts phản biện trong backtest_result, robustness/clean_a20, ablation/clean_a20, sentiment_coverage, paper và chín sentiment caches; không lấy outputs ignored của luồng KLTN. `paper/main.pdf` được nhắc trong khảo sát trước hiện **không có trên đĩa**, được ghi ở `missing_expected_sources`; chưa xác minh phiên bản submission chính thức. `record.csv` cục bộ không có dataset/symbol/provenance contract nên không tự coi là train snapshot cho R1.

`manifest.json` là inventory kiểm tra integrity, không phải chữ ký xác thực nguồn gốc; snapshot submission chính thức và quyền chia sẻ vẫn cần tác giả xác nhận. Không thêm manuscript/reviewer/ignored caches vào commit task chỉ vì chúng có trong inventory.

## Kiểm tra và kết quả

Phạm vi kiểm tra: metrics thống kê mới, replay kinh tế độc lập so với engine, hợp đồng giá/label/cutoff, common support/undefined, hash và chống ghi đè; hồi quy bộ significance vì cùng module utility được mở rộng. Không thay inference, loader PIT, prompt, retry/checkpoint hoặc runtime/dependencies nên không chạy toàn bộ unit/E2E/leakage suite. Các test cutoff/overlap ở audit kiểm tra hợp đồng replay, không chứng nhận dữ liệu lịch sử sạch leakage.

Kết quả kiểm tra ngày 01/11/2026, runtime Python **3.13.5**, NumPy **2.1.2**, SciPy **1.16.1**:

| Lệnh | Kết quả |
|---|---|
| `py -3.13 -X utf8 -m unittest discover -s tests -p test_revision_baselines.py -v` | PASS, 16 test |
| `py -3.13 -X utf8 -m unittest discover -s tests -p test_significance.py -v` | PASS, 8 test |
| `py -3.13 -m py_compile utils/statistical_tests.py core/revision_audit.py scripts/audit_revision_baselines.py tests/test_revision_baselines.py` | PASS; file thay đổi sau đó được biên dịch lại đúng phạm vi |
| `py -3.13 -X utf8 scripts/audit_revision_baselines.py` | PASS, 9 mã/180 điểm/53 ngày cutoff phân biệt |
| `py -3.13 -X utf8 scripts/audit_revision_baselines.py --verify outputs/revision/r1_legacy` | PASS, 102 hash nguồn/đầu ra |
| `git diff --check` | PASS |

Kết quả sinh tự động: [bảng audit](../outputs/revision/r1_legacy/README.md), [classification CSV](../outputs/revision/r1_legacy/classification.csv), [economics CSV](../outputs/revision/r1_legacy/economics.csv), [JSON đầy đủ](../outputs/revision/r1_legacy/report.json), [manifest](../outputs/revision/r1_legacy/manifest.json).

Full có accuracy 65,00%, BA 55,01%, MCC 0,113; Base reports có accuracy 51,11%, BA 44,44%, MCC −0,108; constant DOWN/CASH có accuracy 68,89%, BA 50,00%, MCC NA. Replay giá chuẩn cho mean return Full −1,6833% (hiển thị −1,68%), còn mean phần trăm đã làm tròn trong summary cũ −1,6856% (hiển thị −1,69%). Giữ riêng hai nguồn số, không sửa artifacts cũ. Không suy superiority hoặc significance từ kết quả này.

Manifest thử nghiệm có phạm vi rộng được giữ cục bộ tại `outputs/revision/r1_legacy_draft/`, chưa đưa vào release/commit; chỉ bundle `r1_legacy/` nêu trên là bằng chứng của milestone này. Thuộc tính Git được ghim riêng cho code/bundle mới để giữ byte qua checkout Windows; không chuẩn hóa lại artifacts lịch sử. Chưa chạy lại toàn hệ thống vì không thay đường inference/PIT/runtime như đã nêu ở trên.
