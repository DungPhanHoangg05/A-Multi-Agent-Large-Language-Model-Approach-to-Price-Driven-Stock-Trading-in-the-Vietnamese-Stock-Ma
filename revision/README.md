# Tiến độ xử lý phản biện

Kế hoạch chính: [../plan.md](../plan.md). Nhánh tích hợp của đợt phản biện: `fix`; luồng KLTN trên `develop` được quản lý riêng.

**Tiến độ hiện hành:** [R1 đã chốt ngày 03/11/2026](../plan.md#r1-progress), xem [response](response_to_reviewers.md) và [release bản thảo](../outputs/revision/r1_manuscript_v2/manifest.json). Các mục bên dưới là nhật ký lịch sử của những lần triển khai trước, không phải checklist hiện tại.

## Dọn working tree sau khi chốt R1 — 03/11/2026

Theo yêu cầu tác giả, đã đưa 278 file phát sinh chưa commit của study dở `r1_common_run_v3` ra ngoài repo và lưu usage 117 attempts trước khi khôi phục usage đã commit. Lệnh xóa bị kiểm duyệt tự động chặn với lý do `blocked by policy`, nên các file được chuyển tới `%LOCALAPPDATA%/CodexCleanup/R1OldRun_20261103T024222/`, không tuyên bố đã xóa vật lý. Sáu file lịch sử đã commit của run cũ giữ nguyên; các số đếm 23 calibration/117 attempts bên dưới và trong kế hoạch là lịch sử, không phải checkpoint còn sẵn để resume trong working tree.

Ignore đúng 37 file runtime của run R1 đã chốt: locks, quota SQLite, status/usage và work/cache. Raw calls, nodes, decisions, charts đã khóa, completion markers và analysis/manuscript release vẫn được Git theo dõi. Chỉ thay quy tắc Git và dọn file cục bộ; kiểm ignore cả trường hợp dương/âm, diff và hash release. Không chạy unit/E2E/leakage suites vì không đổi code, runtime khoa học hoặc đầu vào.

## Điều chỉnh ngân sách ngày 02/11/2026 — chỉ thay đổi tài liệu

**Ưu tiên mới:** [phương án rút gọn trong kế hoạch](../plan.md#0-phương-án-rút-gọn-có-hiệu-lực-từ-02112026), thay yêu cầu hoàn tất 8.100 decisions của study Full cũ. Những số 5/10 repeats, 8.100 decisions, 14.580 requests và lệnh resume trần 30.000 ở phần lịch sử bên dưới mô tả **protocol cũ**, không là ngân sách mặc định mới.

- [x] Xác định nguồn chi phí: 540 calibration Full +540×14 test decisions; calibration exposure và lặp dày toàn grid không phải điều kiện bắt đầu R1.
- [x] Chốt thiết kế kế hoạch: R1 đầu tiên 540 Full decisions; gói chung **2.430 decisions/4.158 research requests**, smoke <=60 attempts, trần đề xuất **5.000 attempts** gồm retry. Không gọi đây là nghiên cứu đã chạy hoặc đủ power mặc định.
- [x] Đặc tả pool **5 org Groq**: limiter theo org/model, balanced allocation, isolated workers/shards, shared global cap, parent hashes, retry/cooldown và bảo vệ secrets. Không cam kết tốc độ gấp năm khi chưa đo quota.
- [x] Tách bắt buộc với tùy claim: numerical baselines/fixed-random, panel repeated/factorial/placebo, multi-year blocks, integrity/citations bắt buộc; Full-exposure calibration, fusion mới, VN100, Cartesian sweeps và prospective dài hạn khỏi critical path nếu không nhận claim tương ứng.
- [ ] Implement profile mới, scheduler 5 org và tests đúng phạm vi; tạo protocol/bank/run mới. `r1_common_protocol.json`, code/runtime và source artifacts hiện **chưa thay đổi** bởi lượt này.
- [ ] Kiểm tra status thực v3 và thực hiện chuyển study ở checkpoint boundary khi triển khai. Lượt sửa tài liệu thấy usage/call files mới chưa commit; giữ nguyên, không stage hoặc coi receipt dừng cũ là status realtime.
- [ ] Gate sentiment: verified-unknown vẫn missing; cần input text/availability và scorer local pinned cho nhánh sentiment thực. Nếu thiếu, khai báo comment/claim còn mở thay vì chạy factorial rỗng rồi đóng R4/R7.

Kiểm tra áp dụng cho task này: đối chiếu arithmetic/budget, đủ R1–R18, liên kết tài liệu, diff/whitespace, hash protocol và diff code/runtime. **Không chạy compileall, unit, E2E hoặc leakage suite**, vì chỉ sửa ba Markdown (`plan.md`, README này, runbook), không thay code/test/schema/runtime/input/protocol khóa. Không ghi gate cũ là đã chạy lại; mọi lần triển khai FAST sau đó phải test đường ảnh hưởng theo AGENTS.md.

Kết quả kiểm tra tài liệu: **PASS** UTF-8, code fences, liên kết local, đủ R1–R18, công thức 2.430 decisions/4.158 requests và trần attempts; diff whitespace PASS. SHA-256 protocol cục bộ giữ nguyên `b39c3b859b8f92e3df8ec4baba571d5e6599369f7f7c0ac7ecc97d13f3a6b13b`, Git blob cũng khớp HEAD. Không so bytes CRLF của working tree với bản LF trong Git để kết luận sai rằng protocol đã đổi. Thay đổi `usage.json` và call artifacts có sẵn ngoài task được giữ nguyên, không đưa vào commit tài liệu.

Phần bên dưới giữ tiến độ và kết quả lịch sử. [Runbook](r1_common_runbook.md) đã đánh dấu rõ lệnh cũ và điều kiện chuyển profile; chưa có CLI chạy gói rút gọn.

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

**Dependency cụ thể còn lại:** study mới chung snapshot bên dưới đang chạy; không phải khôi phục snapshot submission. Không dùng nhãn test, tỷ lệ LONG test của Full hoặc kết quả của protocol KLTN khác để lấp chỗ thiếu. Mục đóng R1 trong kế hoạch giữ nguyên tiêu chuẩn; R2/R3/R6/R9 và tính khả thi thực thi vẫn cần nghiệm thu riêng.

Milestone đầu không tải vendor data hoặc gọi LLM. Lượt tiếp theo chỉ truy xuất OHLCV công khai qua vnstock/VCI và probe KBS để kiểm tra chất lượng; không gọi LLM/API có phí. Artifacts lịch sử giữ nguyên byte; manuscript gốc đã có archive trước khi sửa. Tập legacy và tập tái dựng đều là bằng chứng khám phá, không gắn nhãn thành untouched confirmatory test.

## Lịch sử study chung snapshot trước điều chỉnh ngân sách 02/11/2026

- [x] Khóa [protocol](r1_common_protocol.json), ba folds, chín mã, **540 test units trên 60 ngày decision**, 540 Full-calibration units lấy từ train đã purge. Đây là historical exploratory study, chưa phải confirmatory/prospective holdout.
- [x] Tính đúng **3.038 feature snapshots** bằng Alpha node Python hiện tại; 225 cột OHLCV và 432 cột selected-alpha/sentiment/missingness. Logistic matched nhận cùng thông tin thị trường dạng số; không giả định cùng biểu diễn hoặc kiến thức của LLM. [Bank v3](../outputs/revision/r1_common_bank_v3/manifest.json), [receipt features](../outputs/revision/r1_common_bank_v3/features_complete.json).
- [x] Chạy baseline số đủ 27 symbol/fold: **3.780 predictions, 216 daily ledgers**, support net **166 UP/374 DOWN**. [Report](../outputs/revision/r1_common_numeric_v3/report.json), [summary](../outputs/revision/r1_common_numeric_v3/summary.csv), [classification/regimes](../outputs/revision/r1_common_numeric_v3/classification.json), [model selection](../outputs/revision/r1_common_numeric_v3/models.json). Toàn bộ **224 hash** nguồn/đầu ra đã đối soát; kết quả số không đổi khi khóa lại bank sau smoke.
- [x] Runner có archive request/response SDK, khóa nguồn/runtime, checkpoint theo fold/role/repeat, trần request cộng dồn, guard prompt <6.500 ký tự, retry theo provider và replay quyết định từ raw response. API key đã được cấu hình cục bộ; không đưa vào Git hoặc archive.
- [ ] **Full đã gọi API thật nhưng dừng do quota ngày**, chưa đủ grid và chưa có kết quả head-to-head. Calibration chạy trước test; sau đó 5 end-to-end và 10 Decision-only repeats, tổng **8.100 Full decisions**, tối thiểu **14.580 requests**. Control exposure chỉ tạo từ Full calibration train sau khi đủ dữ liệu; không dùng tỷ lệ LONG test.
- [ ] Chỉ cập nhật bảng Full/bản thảo/response và xét đóng R1 sau khi inference/analysis đầy đủ. Chưa sửa các PDF đã khóa chỉ dựa trên vài checkpoint calibration.

| Baseline | Pooled accuracy | Pooled BA | Pooled MCC | Mean net return của 27 tài khoản |
|---|---:|---:|---:|---:|
| CASH / train-majority | 69,26% | 50,00% | NA | 0,00% |
| Always-LONG cycles | 30,74% | 50,00% | NA | −15,33% |
| Momentum 20 | 52,78% | 49,49% | −0,009 | −7,56% |
| Logistic OHLCV | 61,30% | 52,96% | 0,061 | −3,49% |
| Logistic matched market inputs | 57,59% | 51,29% | 0,025 | −5,90% |
| Factor-only vote | 51,11% | 51,64% | 0,030 | −6,21% |

Pooled classification có mẫu số 540 cho mỗi baseline; mean return là trung bình symbol/fold, không phải return một portfolio chung. Continuous hold price-only có mean return −2,23%, không có prediction/classification. Mọi comparator có giao dịch đều có mean return âm trong phép tổng hợp này; không suy alpha/profitability. Regime là gap close/SMA60 nhân quả của từng mã; folds, mã và repeats phụ thuộc nhau. BHN có 32 train points ở fold đầu, phải giữ giới hạn support nhỏ này.

Smoke `v1` dừng sau hai response vision, **chưa có Full decision**, do guard mới nhầm yêu cầu Indicator gọi LLM. Indicator và Alpha backtest thực tế dùng Python xác định. Giữ bank/run smoke riêng, source 49 file trong [archive](../outputs/revision/r1_common_bank_v1/source_snapshot.zip); bank `v2` chỉ sửa guard/count, không đổi lịch/features/selection theo outcome. [Receipt tái dùng feature v2](../outputs/revision/r1_common_bank_v2/feature_reuse.json) kiểm nguồn archive, AST các hàm feature, lịch, runtime, giá và tin; chỉ đổi bank ID/self-hash, không chuyển response sang run mới. Bản baseline số `v1` trung gian còn cục bộ, không phải release hiện hành.

Lượt chạy gặp 429 ở vision ITPM 7.000 rồi TPD 200.000; v3 đã sửa đọc khoảng chờ ghép và dừng ngay khi hết quota ngày. Controller Windows đã chờ lượt smoke rồi resume run v2 với trần 30.000 attempts cộng dồn; đã dừng do quota ngày, không còn tiến trình nền chạy. Bản controller hiện hành nhắm run v3 và chỉ tự chạy analyzer khi inference đủ grid. Controller dừng khi có lỗi cần xem xét; không đổi model/protocol, không mua/nâng gói và không retry vòng ngoài vô hạn. Raw run v2 được khóa tại [stopped receipt](../outputs/revision/r1_common_run_v2/stopped_receipt.json): 12 calibration, 0 test; trong đó hai calibration có cả hai vision nodes dùng text fallback của agent gốc. Đây là smoke chẩn đoán, không phải tập kết quả Full chính thức. Không chuyển các prediction này sang run v3. Cần quota vision đủ cho grid; completion của worker vẫn cần scientific review trước khi đóng R1.

```powershell
py -3.13 -X utf8 scripts/status_revision_common_study.py
```

Hướng dẫn chạy/resume và giới hạn: [r1_common_runbook.md](r1_common_runbook.md). Lượt đầu 24 test PASS; sau sửa quota, chạy lại **17 common-study tests PASS**, cộng 5 alpha-leakage và 3 token-budget tests đã PASS trước đó, bao phủ **25 tests**. Common-study suite gồm native deterministic Indicator, replay chống sửa prediction, retry interval ghép phút/giây và TPD BaseException xuyên callback/retry proxy; biên dịch các Python mới PASS. Các tests dùng fake model chỉ ở temp fixture, không tính là kết quả thực nghiệm. Controller đã qua parse PowerShell và kiểm tra khóa trên tiến trình thật; pha inference/analyze chưa thể hoàn tất do quota ngày. Không chạy toàn suite vì chỉ thêm runner nghiên cứu riêng, giữ nguyên engine/agents/runtime/dependencies hiện có.

Hash bằng chứng cũ vẫn PASS: 102 legacy qua archive, 126 numeric, 45 manuscript nguồn/PDF/log. Không thay byte artifacts cũ. Không dùng tests thay cho Full evidence.

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

### Dừng quota và phiên bản thực thi hiện hành

Groq trả HTTP 429 `tokens per day (TPD): Limit 200000`; đây là hạn mức của tài khoản/model trong lần chạy, không phải giả định về mọi gói Groq. Parser guard mới hiểu cả `18m10.368s`, `1h2m3s`, số giây và milliseconds. Khi TPD cạn, archive lỗi rồi ném StudyStop trước text fallback/retry tiếp; không tạo prediction để lấp thiếu. Log nền tương lai ép PYTHONIOENCODING=utf-8; log v2 giữ nguyên cả encoding gốc.

Bank v3 giữ nguyên 3.038 feature values/market-input hashes, lịch, protocol và selection; khóa lại code guard trước mọi test inference. Bổ sung hash helper audit/CSV/sentiment và versions thư viện chart/serialization. Source trước sửa v2 nằm trong [source_snapshot.zip](../outputs/revision/r1_common_bank_v2/source_snapshot.zip). Chỉ feature số được tái dùng, không tái gán prediction/checkpoint cũ. [Feature reuse v3](../outputs/revision/r1_common_bank_v3/feature_reuse.json) ghi nguồn và kiểm tra. Release số v2 và metadata tái dùng v2 tham chiếu helper cũ đã có trong archive v2; dùng archive đó khi đối soát source lịch sử, không so hash với CLI v3 hiện hành.

Người dùng chọn giữ quota hiện có, đợi quota phục hồi rồi tự chạy tiếp bằng terminal. Không khởi động lại worker nền. Run v3 đã kiểm tra bằng API thật: đúng **1 attempt**, lỗi TPD với thời gian chờ parse được **714,528 giây**, **0 prediction**, dừng trước fallback/retry. [Receipt dừng ban đầu v3](../outputs/revision/r1_common_run_v3/stopped_receipt.json) lưu usage snapshot riêng để không bị thay đổi khi resume. Thời gian đó là phản hồi tại thời điểm lỗi, không phải cam kết reset theo giờ lịch. Lệnh API và bước phân tích nằm trong runbook; cần hoàn thành toàn grid trước khi cập nhật bản thảo.

Đối soát hiện hành (không gọi API): `py -3.13 -X utf8 scripts/verify_revision_common_study.py`. Script kiểm bank v3 trực tiếp, đối chiếu nguồn lịch sử qua archive đúng hash, cả ba feature receipts, hai release số v2/v3, ba receipt dừng và replay calibration chẩn đoán. Đây là kiểm tra integrity, không đóng Full/R1.

Diff check phần code/tài liệu/releases mới PASS; giữ nguyên CRLF của hai artifacts gốc `r1_common_run_v2/worker_20261101T170916Z.log` và `worker_status.json`, loại riêng chúng khỏi whitespace check. Hash của chúng trong stopped receipt vẫn PASS; không strip hoặc sửa encoding bằng chứng để xóa cảnh báo whitespace.
