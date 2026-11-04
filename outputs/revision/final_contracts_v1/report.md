# Target, risk và indicator contracts trên release cuối

Đối soát T20 dùng final T04 và sensitivity T19, giữ nguyên predictions, nhãn, code/runtime và mọi artifact lịch sử. Đây là phân tích bằng chứng sau inference, không tạo quan sát thị trường độc lập, không fit hoặc gọi API, không sửa `paper/`. [report.json](report.json) ghi số lượng, provenance và phạm vi kiểm tra; [manifest.json](manifest.json) khóa các nguồn/đầu ra. R5 còn phần temporal/dependence tại T25; R11–R13 còn phải đồng bộ bài/response/locators hiện hành sau T30.

## Target primary và aliases legacy

[targets.json](targets.json) có đúng **102 outcomes**, đối soát cả net/gross labels trên **918 prediction rows**. Với cutoff index `d`, decision price là `Close[d]`, entry là `Open[d+1]`, target exit là `Close[d+3]`; ba bars gồm entry, exit cách entry hai phiên. Giữ quality suffix của snapshot T04, không dùng index CSV raw thay index phân tích. Cả 102 canonical outcomes khớp schema `net_cycle_v1`, validator và đại số độc lập:

```text
gross = exit_close / entry_open - 1
net = (exit_close / entry_open) × (1−0.0025)(1−0.001)
                                  / ((1+0.0025)(1+0.001)) − 1
label = UP nếu return > 0, ngược lại DOWN
```

Returns canonical là fractions; `actual_pct_change` legacy là net percent, `execution_pct_change` là gross percent. Net có **25 UP/77 DOWN**, gross có **32 UP/70 DOWN**; **bảy units** khác nhãn. Gross giữ vai trò diagnostic trên predictions đã elicited theo net, không thay primary hoặc coi model đã được hỏi lại cho gross. **65/102 units** có entry Open khác decision Close; không thay entry bằng Close-to-Close, kể cả các điểm hai giá tình cờ bằng nhau. Zero thuộc DOWN; horizon thiếu không được rút ngắn. `net_return` là outcome ứng viên LONG, không là account return của SHORT/CASH, no-fill hoặc delay.

Giá/nhãn là evaluation outcomes sau inference, không được đưa vào graph inputs. Đã đọc **375 actual successful Decision requests** của final T04: tất cả có net-cost contract 0,25% fee và 0,10% slippage mỗi chân; không sửa builder/prompt để khớp mô tả. T19 thay chi phí/thanh toán/fill assumptions riêng, không relabel target. Bất kỳ so sánh gross hoặc execution nào cũng không thêm API jobs.

Tái dùng [audit 600 legacy point records](../target_contract_v1/legacy_field_audit.csv): **178 aliases `actual_prev_close` bằng entry Open**, nhưng **0/600 decision Close được authenticated**. Giữ canonical decision Close `null` trên cả 600; không suy nghĩa lịch sử từ sự bằng nhau số học, current frame hoặc source mới. Target audit cũ còn khớp **829 source/output hashes**; đây là bằng chứng công thức/schema và alias disposition, không xác thực ngược snapshot submission hoặc execution commit.

## Risk frequency, gaps và undefined

[risk_daily.csv](risk_daily.csv) có **6.804 account rows**: T04 **684** accounts/31.977 daily returns, T19 **6.120** account executions/394.560 daily returns. T04 tách main 510, upstream 54, factorial 120; T19 giữ cả 12 scenarios ×510. Counts là các đường ledger, không phải từng ấy market observations độc lập hoặc portfolio. Mỗi tài khoản có anchor vốn đầu kỳ 50 triệu VND; daily return là `wealth[t]/wealth[t−1]−1`, giữ ngày mua đầu tiên, mọi CASH gap, pending receivable và residual MTM. Đối soát return/drawdown với account summaries và tập ngày với calendar T18; không dựng lại lịch hay equity từ predictions trong bước này.

Risk ratios được tái tính từ ledger đã lưu và kiểm bằng oracle `math.fsum`/`statistics.pstdev` độc lập với NumPy helper. Annualisation dùng **252 sessions/năm như một quy ước**, không phải số phiên thực tế của mỗi năm, không tự lấy chênh ngày lịch hoặc số trades làm tần suất. Sharpe dùng mean/population SD (`ddof=0`), risk-free bằng 0. Sortino giữ convention legacy là **population SD của subset daily returns âm**, MAR=0; không gọi nó là downside RMS/lower-partial-moment chuẩn. Mẫu số không có hoặc ≤1e−12 cho `null` trong JSON, **NA trong CSV**, không điền 0/Infinity.

| Release | Accounts | Sharpe defined | Sortino defined | SD suy biến/zero |
|---|---:|---:|---:|---:|
| T04 | 684 | 345 | 296 | 339 |
| T19 | 6.120 | 2.910 | 2.518 | 3.210 |

T19 có tail tối đa năm observed bars, giới hạn cuối snapshot; thêm các ngày CASH zero có thể thay risk ratio dù terminal return giữ nguyên. CSV do đó giữ cả risk trên toàn cửa sổ và các trường `common_window_*` cắt ở ngày exit cuối T04. **510/510 reference accounts** khớp risk T04 trên cùng cửa sổ, không gán thay đổi do tail thành hiệu quả execution. T19 còn hai residual-stock executions và bốn pending-cash executions theo receipt đã khóa; wealth không đồng nhất liquidated cash.

[risk_cycles.csv](risk_cycles.csv) đối soát riêng **510 main cycle schedules**: **459** classifier accounts có hai cycles cách 57 observed sessions nhưng mỗi cycle chỉ dài ba bars, nên `irregular_or_gapped_cycles`; **51** continuous-hold accounts chỉ có một cycle, nên `insufficient_schedule`. Tất cả annualised cycle Sharpe/Sortino là **NA**, có thể giữ unannualised ratios khi mẫu số đủ. Không dùng sqrt(252), sqrt(84) hoặc sqrt(252/57) cho các cycle series này. sqrt(252/S) chỉ được hỗ trợ cho lịch cycles ngày đều, liền nhau và spans=S có provenance; đây không phải lịch main T04. Ratios của 18 tài khoản legacy trong audit cũ vẫn chỉ có sqrt(84) conditional, authenticated ratios `null` do thiếu snapshot/bar-index provenance.

Receipt `account_annualisation_v1` có **553 source/output hashes**: **548** khớp file hiện tại; **năm source hashes** khác do target/schema bổ sung sau đó. Đã tìm đúng byte cả năm trong Git tại `5b8770f951ce6c9011eacba587cf84fbf0cb1fd3`, kèm blob OID/SHA-256 trong `report.json`. Đây là commit chứa source, **không phải chứng nhận execution commit**. Không sửa manifest cũ hoặc báo 553 hashes khớp runtime hiện tại. AST của năm hàm risk/summary vẫn giống hệt: `compute_variant`, `_compute_partial`, `_build_summary`, `_summary_to_result`, `summarize_symbol`; phần khác là metadata/canonical validation. Vì vậy chạy lại đúng **12 account-risk và 11 target-contract tests: 23 PASS**, không mở toàn suite.

## Indicator delivery và quy tắc biên

[indicators.json](indicators.json) giữ replay **102 cửa sổ 45 bars** tới đúng cutoff, **120 Indicator nodes** (102 realization 0 và 18 upstream realizations bổ sung), cùng đối chiếu **375 actual Decision requests**. Năm toolkit computations và report rendering deterministic khớp nguyên text của cả 120 node caches; các nodes không có model request IDs/call hashes và chỉ trả `indicator_report`/`messages`. Sau `_distill_report`/`_cap_report`, Indicator section khớp đúng cả 375 actual requests. Đã chặn model/network trong replay; không chạy lại Pattern/Trend/Decision, không coi arithmetic replay là LLM evidence mới.

| Quy tắc | Hành vi phải giữ trong mô tả bài |
|---|---|
| Đọc dữ liệu | Lọc None/nonfinite, giữ zero và round bốn chữ số trước classify; retained samples không nhất thiết là nến liên tiếp khi thiếu dữ liệu. |
| MACD | Cross có previous strict/current inclusive được ưu tiên; sau đó xét dấu và chiều histogram. Histogram không là chỉ số của Stochastic. |
| RSI | ≥70 bearish; ≤30 bullish; 55≤RSI<70 bullish; 30<RSI≤45 bearish. Vùng 45<RSI<55 so current với retained thứ ba từ cuối, không mặc định neutral. |
| ROC | >+0,5% bullish, <−0,5% bearish; equality neutral sau rounding. |
| Stochastic | Cross ưu tiên hơn vùng cực trị; sau đó ≥80 bearish, ≤20 bullish. Fallback giữa vùng giữ equality/zero-D truthiness legacy; không tự sửa trong diễn giải. |
| Williams %R | ≥−20 bearish, ≤−80 bullish; giữa vùng xét xu hướng retained samples khi đủ dữ liệu. |
| Summary | Năm votes; missing/error vẫn là neutral trong denominator năm, không là bằng chứng thị trường neutral. Directional plurality, tie MIXED; confidence là heuristic, không xác suất đã calibration. |

Chín source/runtime files của [indicator/alpha receipt](../indicator_alpha_rules_v1/manifest.json), fixtures và ba outputs vẫn khớp tổng **16 hashes**. Tái dùng kết quả **67 indicator, năm consensus, 11 prototype Alpha_4 và ba registry cases** đã kiểm trước đó; không ghi là chạy lại fixture suite. BB/ADX là declared slots nhưng không là hai votes bổ sung hoặc mảng numeric được Indicator node forward; BB có tính riêng trong alpha path.

Custom Alpha_4 BFE vẫn là `tanh((%B−0.5)×VolZ5×1.5)`: z âm đảo dấu; z=0 hoặc %B=0,5 triệt tiêu; không có gate squeeze/band-width expansion hoặc order-flow measurement. Strict ±0,10 dùng trước display rounding. Prototype dùng preprocessing population-SD/rounded tech vars, registry có sample-SD riêng; không khẳng định mọi giá trị hai đường bằng nhau. **`id=4` trong selected top-5 report là thứ tự trình bày, không nhận diện cố định BFE**. Giữ giới hạn native selector causal đã ghi ở T10–T14; T20 không chữa causal fail hoặc suy synthetic fixtures chứng minh alpha/profitability. Tên flow/liquidity/pressure chỉ là OHLCV proxies, chưa có signed trades/order book.

## Phạm vi nghiệm thu

Không đổi source Python, schema vận hành, runtime, giá, nhãn, prediction hoặc cấu hình; không cần compile, E2E hoặc leakage suite. Hai modules tests được chạy lại vì receipt risk cũ khác caller/schema hiện hành, không để cập nhật checklist. Target/indicator/T17 receipts kiểm hash, không chạy producer cũ có nhánh xuất `paper/`. Parents T04 **3.524**, T19 **54**, T18 **24 hashes PASS**; T17 **635 hashes PASS**. R5/R11–R13 không tự đóng bằng locators/PDF lịch sử; sửa nguồn bài và response sau gate hệ thống.

Lệnh hash-only offline cho release T20:

```powershell
py -3.13 -X utf8 -c "from pathlib import Path; from scripts.audit_revision_lineage import verify; print(verify(Path('outputs/revision/final_contracts_v1')))"
```
