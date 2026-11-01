# Tiến độ xử lý phản biện

Kế hoạch chính: [../plan.md](../plan.md). Nhánh tích hợp của đợt phản biện: `fix`; luồng KLTN trên `develop` được quản lý riêng.

## R1 — đã có pipeline baseline và bản thảo sửa; chưa đóng bằng chứng

- [x] Thêm metrics hai lớp: support, confusion, accuracy, BA, MCC, macro-F1, precision/recall/F1 từng lớp và LONG rate; undefined dùng null/NA.
- [x] Replay offline Full, Base reports legacy, constant DOWN/CASH và constant UP/always-LONG cycles trên cùng lịch; xuất pooled, macro-over-symbols, common/own support và groups khi metadata thực có.
- [x] Định nghĩa [target net/gross và quy ước metric](target_contract.md); tách always-LONG cycles khỏi buy-and-hold và cycle-end khỏi daily drawdown.
- [x] Tạo manifest SHA-256 nguyên byte cho bằng chứng cục bộ hiện có, code replay và đầu ra; CLI kiểm tra hash và từ chối ghi đè bundle. Phiên bản submission vẫn **unverified**.
- [x] Có snapshot tái dựng, train/validation, majority/momentum/hai logistic/factor-only và daily ledger; giới hạn common-snapshot, Full-exposure và corporate-action được ghi riêng bên dưới.
- [ ] Đánh giá đầy đủ qua folds/regimes/repeats; daily exposure, turnover, drawdown và execution/settlement contract.
- [x] Sửa abstract/highlights/introduction/results/conclusion và response có location PDF đã kiểm chứng; **chưa đóng R1** do các yêu cầu bằng chứng còn thiếu.

### Phần triển khai tiếp theo đã hoàn thành

- [x] Kiểm kê **2.240 file và một archive** trong toàn bộ `outputs/`, kể cả thư mục ignored. Artifact: [r1_source_inventory.json](../outputs/revision/r1_source_inventory.json). Các request ở luồng KLTN thuộc protocol/thời kỳ khác, không đổi tên thành dữ liệu train legacy.
- [x] Khóa OHLCV VCI tải mới: **9 mã × 1.681 phiên**, từ 2020 đến 30/09/2026, có hash, phiên bản thư viện và ngày truy xuất. Đây là snapshot tái dựng, không xác nhận snapshot submission.
- [x] Chạy đủ chín mã: train-majority, momentum 20 phiên, hai logistic, factor-only vote, CASH, always-LONG, control ngẫu nhiên theo LONG rate của momentum trên train và continuous hold một lần mua/bán.
- [x] Imputation/standardisation chỉ fit train lúc chọn C/threshold bằng validation BA; refit train+validation đã trưởng thành sau selection. Purge label spans, kiểm tra future mutation, test distribution và scorer/availability. Năm factor có whole-series normalisation được chuyển đổi nhân quả **chỉ trong module baseline mới**, không sửa registry lịch sử.
- [x] Xuất **1.440 prediction records và 81 daily ledgers**, cùng support/confusion/per-class metrics theo mã, fold thực có, regime nhân quả và repeat ID 0. Không nhân bản run xác định thành nhiều repeats giả.
- [x] Có close MTM/daily-close drawdown, turnover, held-session/close exposure, số lệnh, phí và slippage cho snapshot mới. Continuous hold chỉ là price-series comparator, chưa xác nhận total-return/corporate actions/settlement.
- [x] Bảo toàn 28 file manuscript gốc nguyên byte tại [manuscript_original.zip](manuscript_original.zip); sửa hai front matters, sections 01/03/05/06/07/08, bốn bảng generated và [response R1](response_to_reviewers.md). Hai PDF build được, 42 trang/bản, không undefined references/citations; đã render và kiểm tra bảng R1 cùng toàn bộ bố cục. Đây là bản nháp R1, không phải xác nhận Gate nộp lại.
- [ ] **Chưa thể đóng R1:** 74/180 cycle có giá entry/exit mới khác legacy, trong đó hai nhãn đổi. Không có bảng head-to-head Full trên snapshot mới. Chưa xác minh comparator cùng report/feature/peer input và Full-exposure control từ train vì chưa khôi phục được bộ đầu vào/dự đoán train tương ứng từ `outputs/`/archive.

**Dependency cụ thể còn lại:** khôi phục đúng historical snapshot/report/request/Full-train artifacts, hoặc thực hiện một study chung snapshot sau khi giải quyết protocol/provenance của R2/R3/R6/R9. Không dùng nhãn test, tỷ lệ LONG test của Full hoặc kết quả của protocol KLTN khác để lấp chỗ thiếu. Mục đóng R1 trong kế hoạch giữ nguyên tiêu chuẩn, không đánh dấu PASS bằng kết quả tái dựng khác dữ liệu.

Milestone đầu không tải vendor data hoặc gọi LLM. Lượt tiếp theo chỉ truy xuất OHLCV công khai qua vnstock/VCI và probe KBS để kiểm tra chất lượng; không gọi LLM/API có phí. Artifacts lịch sử giữ nguyên byte; manuscript gốc đã có archive trước khi sửa. Tập legacy và tập tái dựng đều là bằng chứng khám phá, không gắn nhãn thành untouched confirmatory test.

## Vận hành offline

Từ repository root, Python 3.13.5 với NumPy/SciPy hiện có:

```powershell
py -3.13 -X utf8 scripts/audit_revision_baselines.py
py -3.13 -X utf8 scripts/audit_revision_baselines.py --verify outputs/revision/r1_legacy
```

Sau khi sửa manuscript, lệnh verify cũ với đường dẫn `paper/` hiện tại sẽ báo hash đổi đúng thiết kế. Dùng wrapper sau để đối soát nguyên bản trong ZIP và release mới:

```powershell
py -3.13 -X utf8 scripts/verify_revision_r1.py
py -3.13 -X utf8 scripts/build_revision_r1_tables.py
```

Đánh giá offline được khóa bởi [r1_protocol.json](r1_protocol.json) và môi trường [requirements-r1.txt](requirements-r1.txt). Không chạy lại khi chỉ sửa tài liệu. Nếu cần replay nghiên cứu, dùng output mới:

```powershell
py -3.13 -X utf8 scripts/evaluate_revision_baselines.py --output outputs/revision/r1_numeric_replay
```

Các release đang dùng: [prices manifest](../outputs/revision/r1_prices_v1/manifest.json), [numeric report](../outputs/revision/r1_numeric_v1/report.json), [summary](../outputs/revision/r1_numeric_v1/summary.csv), [classification](../outputs/revision/r1_numeric_v1/classification.json), [models](../outputs/revision/r1_numeric_v1/models.json), [reviewer matrix](reviewer_matrix.csv). Dữ liệu thô BHN có một OHLC contradiction ngày 13/09/2022; giữ nguyên file, chỉ dùng suffix hợp lệ bắt đầu 14/09/2022 cho feature/train (175 train, 34 validation). Tám mã còn lại có 399 train/36 validation. Tất cả giữ 20 test points.

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

### Kiểm tra lượt triển khai tiếp theo

- `test_revision_baseline_leakage.py`: **14 test PASS** (future mutation, train-only fit, label-span purge, availability/provenance, hash, quality suffix và daily ledger).
- `test_revision_baselines.py`: **16 test PASS** hồi quy metrics/replay cũ. Tổng lượt này **30 test PASS**; không gọi kết quả 8 significance tests của milestone trước là đã chạy lại.
- Biên dịch đúng các file Python mới/thay đổi: PASS. Không đổi core engine, agents, cache runtime hoặc dependencies dùng chung; không chạy toàn unit/E2E/leakage suite. Test leakage mới bao phủ đúng đường baseline và preprocessing mới.
- `verify_revision_r1.py`: **102 hash legacy qua archive**, **126 hash release số**, 1.440 prediction records và 81 ledgers PASS; ngày label exit trước split tiếp theo, số lệnh và final equity khớp daily CSV.
- Hai PDF build bằng pdflatex/BibTeX có tắt auto-installer, không thêm dependency TeX/Python. Còn một cảnh báo hbox 2,61pt ở front matter nhưng kiểm tra render không thấy cắt/chồng nội dung; package/bibliography metadata và scientific gates của R16–R18 chưa được đóng.
- Diff check PASS trên phần thay đổi; loại trừ whitespace có sẵn trong `elsarticle.cls`, `elsarticle-num.bst`, section 02 giữ nguyên và hai log build nguyên bản. Ba file nguồn này đã đối chiếu ZIP khớp từng byte; không strip whitespace của bằng chứng/vendor chỉ để làm đẹp diff. Manifest manuscript đối soát **45 hash** nguồn/PDF/log PASS.
- Chỉ sửa generated tables/layout sau numeric run; không thay grid hoặc chạy chọn seed/cấu hình lại theo test outcome. Mọi mean return mới vẫn âm trừ CASH/train-majority ở 0; không suy profitability hay alpha superiority.

PDF đã kiểm tra: [main](../outputs/revision/r1_manuscript_v1/main.pdf), [submission](../outputs/revision/r1_manuscript_v1/main_submit.pdf); [manifest nguồn/build/QA](../outputs/revision/r1_manuscript_v1/manifest.json). Tài liệu thư viện tham chiếu: [Vnstock Quote compatibility](https://www.vnstocks.com/docs/vnstock/chuyen-doi/lop-tuong-thich), [scikit-learn về data leakage và pipeline](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage). Không dùng catalogue hiện tại để suy provenance dữ liệu/model lịch sử.

Ảnh render và log thử nghiệm còn ở `tmp/r1_pdf_qa/` và `tmp/r1_*.log`; thao tác dọn các file này bị hệ thống duyệt tự động chặn (`blocked by policy`), nên giữ nguyên và không đưa vào release/commit. Log build cuối đã khóa cùng hai PDF; không cần chạy lại inference/baselines khi xem bản nháp.
