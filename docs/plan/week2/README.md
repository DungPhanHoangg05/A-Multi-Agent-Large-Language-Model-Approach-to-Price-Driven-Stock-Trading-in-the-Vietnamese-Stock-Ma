# Tuần 2 — phân loại chế độ thị trường và Historical Memory Bank

Tài liệu này chia [mục Tuần 2 của kế hoạch tổng](../plan.md#7-kế-hoạch-thực-hiện-chi-tiết-8-tuần-deliverables-matrix) thành các task có đầu ra và điều kiện hoàn thành riêng. Phase A đã có [biên bản kiểm toán giá và quy tắc lấy mẫu](phase_a_data_and_sampling.md); Phase B đã có [bộ nhận diện regime, artifact và kiểm thử](phase_b_regime_detector.md). Phase C đã hoàn thành W2-09 đến W2-14: pipeline lịch sử, kho chính thức 852 episode và [biên bản phát hành/QA](phase_c_memory_generation.md). Phase D đã hoàn thành biểu đồ, bốn gate và rà soát deliverables trong [biên bản chốt tuần](phase_d_week_close.md). **W2 hoàn thành ngày 04/10/2026.**

## Mục tiêu và điều kiện đầu vào

Cuối W2 cần có `core/regime_detector.py` phân loại bốn chế độ từ VN-Index, `data_manager/regime_memory_store.json` chứa **hơn 300** chu kỳ đã tất toán giai đoạn 2018–2022, và `outputs/vnindex_regimes_2018_2022.png`. Bản ghi phải khớp [schema W1](../week1/historical_task_record.schema.json) và [đặc tả phương pháp](../../methodology_spec.md).

**Gate dữ liệu:** [Gate giá Phase A](phase_a_price_gate.md) đã PASS ngày 26/09/2026 cho bộ giá thô VCI 2018–2022, đối chiếu VCI/KBS: 852/868 chu kỳ ứng viên đủ cơ sở giá, 16 chu kỳ bị loại vì quyền/tham chiếu. Phase C dùng `data/execution_prices` cho tín hiệu cổ phiếu và giá vào/ra, qua loader xác minh; CSV cổ phiếu W1 không được dùng để sinh nhãn. W2-13/W2-14 đã hoàn thành ngày 04/10/2026. Episode phủ 2020–2022 do 600 phiên khởi động; toàn bộ sentiment NEUTRAL do thiếu tin đáng tin cậy. Gate này chưa mở dữ liệu giá thô kiểm định 2023–2024.

## Quy ước cập nhật tiến độ

- `[ ]` chưa xong; `[x]` chỉ dùng khi đủ đầu ra và bằng chứng kiểm tra. Ghi `Đang làm` hoặc `Bị chặn` cùng lý do nếu cần.
- Sau **mỗi task hoàn thành**, cập nhật ô trạng thái và thêm một dòng vào **Nhật ký tiến độ**: ngày, mã task, file/đầu ra, lệnh kiểm tra và kết quả. Không đánh dấu hoàn thành theo mức độ ước lượng.
- Mỗi task kỹ thuật làm trên nhánh riêng từ `develop` theo `AGENTS.md`; chỉ merge khi bốn gate bắt buộc đều pass. Commit message mô tả kỹ thuật, không chứa ký hiệu tuần/ngày tiến độ.
- Giữ nguyên hợp đồng `LONG` mua `Open(t+1)`, bán `Close(t+3)` sau ba phiên; `SHORT` giữ tiền mặt; phí 0,25% và trượt giá 0,10% ở cả hai chiều. Tín hiệu ở ngày $t$ chỉ được đọc dữ liệu có ngày `<= t`.

## A. Chốt dữ liệu và mẫu chu kỳ

| Mã | Task | Đầu ra / điều kiện hoàn thành | Phụ thuộc | Trạng thái |
| --- | --- | --- | --- | --- |
| W2-01 | Xác minh giá thực thi point-in-time và cơ chế điều chỉnh doanh nghiệp từ hai provider được phép | [Gate giá đã mở](phase_a_price_gate.md): 5.004 nến thô VCI, 8 mẫu quyền đối chiếu VCI/KBS, checksum/evidence/prefix và chính sách loại chu kỳ có quyền; chưa phát hành nhãn | Kiểm toán W1 | [x] Gate giá PASS cho tập 2018–2022 |
| W2-02 | Chốt cách lấy mẫu chu kỳ 2018–2022 | [Quy tắc Phase A](phase_a_data_and_sampling.md) chốt $t$, $t+1$, $t+3$, bước 3, warm-up 600 nến, 868 chu kỳ ứng viên không nhãn trên bốn mã và giới hạn phủ năm | W2-01 cho nhãn; CSV W1 cho lịch | [x] |

## B. Market Regime Detector

| Mã | Task | Đầu ra / điều kiện hoàn thành | Phụ thuộc | Trạng thái |
| --- | --- | --- | --- | --- |
| W2-03 | Đặc tả và tính đặc trưng VN-Index theo ngày | [Đặc tả Phase B](phase_b_regime_detector.md), `build_regime_features` và 4 test công thức/khởi động/cutoff; không dùng breadth | CSV W1 | [x] |
| W2-04 | Chốt cấu hình Gaussian HMM và khả năng tái lập | [Cấu hình Phase B](phase_b_regime_detector.md): HMM 4 trạng thái, seed 42, scaler train-only, dependency ghim và tiêu chí fallback chốt trước fit | W2-03 | [x] |
| W2-05 | Cài đặt fit một lần và lưu artifact của HMM | `MarketRegimeDetector.fit/save/load`, runner offline và `data_manager/regime_model.json`: 1.251 nến train, 1.052 hàng đặc trưng, checksum và phiên bản được xác thực | W2-04 | [x] |
| W2-06 | Ánh xạ trạng thái HMM sang bốn tên regime | Mapping train-only, ID chuẩn và fallback đa yếu tố có lý do trong artifact; HMM dữ liệu thật đạt tiêu chí đã chốt | W2-05 | [x] |
| W2-07 | Cung cấp API phân loại tại `as_of_date` | `get_market_regime` cắt archive trước suy luận; `classify_regime` kiểm snapshot, hash train và ngày fit; trả đúng schema W1 bằng kiểu Python gốc | W2-05, W2-06 | [x] |
| W2-08 | Kiểm thử regime và cắt thời gian | `tests/test_regime_leakage.py` cùng test features/model/mapping/API kiểm cutoff của dữ liệu lẫn model/scaler/calibration, hash, warm-up, schema và JSON | W2-07 | [x] |

## C. Historical Memory Bank

| Mã | Task | Đầu ra / điều kiện hoàn thành | Phụ thuộc | Trạng thái |
| --- | --- | --- | --- | --- |
| W2-09 | Cài đặt cấu trúc lưu và xác thực `HistoricalTaskRecord` | `core/bayesian_memory.py` nạp/lưu JSON, ID duy nhất, đủ 5 tín hiệu, `as_of_date < entry_date < exit_date` theo phiên, kiểm P&L và lưu nguyên tử; [bằng chứng Phase C](phase_c_historical_memory.md) | Schema W1, W2-02 | [x] |
| W2-10 | Trích tín hiệu năm agent từ snapshot lịch sử | `core/historical_signals.py` dùng graph hiện có, snapshot thô VCI và tin `<= t`; năm tín hiệu/báo cáo/provenance, checkpoint upstream một lần; [bằng chứng Phase C](phase_c_historical_memory.md#w2-10--trích-tín-hiệu-từ-snapshot-lịch-sử) | W2-02, W2-07 | [x] |
| W2-11 | Tạo nhãn kinh tế cho chu kỳ đã tất toán | `core/historical_outcomes.py` dùng hàm engine, giá VCI xác minh, Open(t+1)/Close(t+3), phí/slippage và bull trap; [bằng chứng Phase C](phase_c_historical_memory.md#w2-11--bộ-sinh-nhãn-kinh-tế) | W2-01, W2-02 | [x] |
| W2-12 | Viết runner offline có thể tiếp tục | `scripts/run_historical_memory.py`, regime prefix, journal nguyên tử/tiếp tục, seed/cấu hình cố định, LLM qua retry/backoff; [bằng chứng và lệnh dùng](phase_c_historical_memory.md#w2-12--runner-offline-và-tiếp-tục-từ-checkpoint) | W2-09, W2-10, W2-11 | [x] |
| W2-13 | Sinh Memory Bank 2018–2022 | `data_manager/regime_memory_store.json`, manifest và biên bản bộ đọc: 852/852 episode trên bốn mã, journal/P&L/cutoff/checksum xác minh; [phát hành](phase_c_memory_generation.md) | W2-12 | [x] |
| W2-14 | Kiểm toán Memory Bank | `scripts/audit_historical_memory.py`, [QA JSON](memory_bank_audit.json) và [biên bản](phase_c_memory_generation.md): schema/ID/lịch/P&L/provenance/độ phủ PASS; ghi rõ thiếu episode 2018–2019 và tin lịch sử | W2-13 | [x] |

## D. Biểu đồ và chốt tuần

| Mã | Task | Đầu ra / điều kiện hoàn thành | Phụ thuộc | Trạng thái |
| --- | --- | --- | --- | --- |
| W2-15 | Vẽ chế độ VN-Index 2018–2022 | PNG 300 DPI, SVG và manifest/checksum; phân biệt nhãn hồi cứu với 217 ngày PIT, đủ chú giải/trục, không có 2023+; đã kiểm tra ảnh trực quan ([biên bản](phase_d_week_close.md#w2-15--biểu-đồ-vn-index)) | W2-07 | [x] |
| W2-16 | Chạy bốn gate hồi quy và kiểm toán leakage | Compileall PASS, 235/235 unit tests PASS, E2E PASS, 38/38 leakage tests PASS; QA kho thực tế PASS 852 episode ([bằng chứng](phase_d_week_close.md#w2-16--bốn-gate-và-kiểm-toán-kho)) | W2-08, W2-14, W2-15 | [x] |
| W2-17 | Rà soát deliverables, cập nhật tiến độ và tích hợp | Đủ ba đầu ra W2, kế hoạch tổng đã cập nhật; Conventional Commit và tích hợp theo `AGENTS.md` sau bốn gate PASS ([đối chiếu](phase_d_week_close.md#w2-17--đối-chiếu-đầu-ra-và-tiến-độ)) | W2-01 đến W2-16 | [x] |

## Nhật ký tiến độ

### 2026-10-04

- **W2-15 hoàn thành**: `py -3.13 -X utf8 scripts/plot_vnindex_regimes.py` xuất PNG 300 DPI/SVG/manifest; 1.251 phiên giá, 1.052 nhãn hồi cứu và 217 ngày PIT từ 852 episode đã QA. Đã kiểm tra ảnh trực quan; ghi rõ khác biệt hồi cứu/PIT và vùng warm-up.
- **W2-16 hoàn thành**: compileall PASS, 235/235 unit tests PASS (43,477 giây), E2E PASS (7,2 giây), 38/38 leakage tests PASS (3,930 giây); chạy lại audit kho thực tế PASS 852 episode. Không sửa engine P&L hoặc giao thức upstream.
- **W2-17 hoàn thành**: đủ module regime/test/artifact, Memory Bank/manifest/QA và biểu đồ; cập nhật kế hoạch tổng, [biên bản chốt Phase D](phase_d_week_close.md) và tích hợp sau bốn gate. Toàn bộ W2 hoàn thành; bước tiếp theo W3.

- **W2-13 hoàn thành**: khôi phục và tích hợp script phát hành, chạy `py -3.13 -X utf8 scripts/publish_historical_memory.py --require-complete` PASS 852/852. Kho chính thức cùng manifest và biên bản bộ đọc nằm trong `data_manager/`; archive tin và mã bộ đọc được đóng băng trong staging. Thêm ignore staging/bản ZIP; giữ nguyên bằng chứng gốc.
- **W2-14 hoàn thành**: `py -3.13 -X utf8 scripts/audit_historical_memory.py` PASS toàn bộ journal và kho phát hành; đối chiếu tín hiệu/báo cáo/factor Alpha, ba trường Trend viết tắt, P&L, lịch và cutoff. Độ phủ: 201/329/322 episode năm 2020/2021/2022; đủ bốn regime; 0 episode có tin đủ độ tin cậy. [Bằng chứng và lệnh tái lập](phase_c_memory_generation.md). Phase D chưa chốt.
- **Gate tích hợp Phase C**: compileall PASS, 235/235 unit tests PASS, E2E PASS (7,1 giây), 38/38 leakage tests PASS. Bản ZIP cục bộ đã xác minh checksum từng file, đủ 2.124 file; staging và ZIP được ignore, kho chính thức/manifest/QA được theo dõi trong Git. W2-16 vẫn mở vì biểu đồ W2-15 chưa có.

### 2026-10-03

- **Gate bản sửa**: compileall, toàn bộ unit tests, E2E xác định và 38 leakage tests PASS.

- **W2-13 sửa định dạng Trend để tiếp tục**: checkpoint `FPT @ 2022-03-04` đã lưu upstream nhưng báo cáo dùng `Hướng xu: Tăng` thay cho `Hướng xu hướng: Tăng`. Thêm bộ đọc tương thích vào `scripts/run_paced_historical_memory.py`: ưu tiên parser gốc, chỉ nhận một trường viết tắt có hướng rõ ràng; từ chối trường trùng, mẫu hướng hoặc giá trị mơ hồ. Không sửa báo cáo hay mã nguồn đã nằm trong chữ ký run. Mỗi lần dùng quy tắc mới ghi `report_parse_compat.json` với hash báo cáo, nhãn, phiên bản quy tắc và hash mã bộ đọc; cần giữ file này khi kiểm toán/phát hành kho. Năm test mới kiểm trường sai/mơ hồ, checksum biên bản và tiếp tục checkpoint không chạy upstream trùng. Đã hoàn tất điểm FPT từ báo cáo lưu với lời gọi LLM mới bị chặn; staging tăng từ 577 lên 578/852, còn 274. Chưa chốt W2-13.

### 2026-10-01

- **Kiểm chứng bản khôi phục**: `--help` hoạt động; compileall, toàn bộ unit tests, E2E xác định và 38 leakage tests PASS. Không gọi LLM thật khi kiểm tra.

- **Khôi phục lệnh tiếp tục Memory Bank**: đưa lại `scripts/resume_historical_memory.py` và `scripts/run_paced_historical_memory.py` từ commit `1c82c51` của nhánh `feat/historical-memory-bank`, cùng các test key/checkpoint/TPM. Lệnh dùng: `py -3.13 -X utf8 scripts/resume_historical_memory.py`; đọc lại key trong `.env` giữa các đợt, nghỉ mặc định 75 giây giữa các lời gọi LLM, dừng ở lỗi đầu tiên và lưu cooldown. Đây là khôi phục công cụ điều phối; W2-13 vẫn cần sinh và kiểm toán kho trước khi chốt.

### 2026-09-27

- **W2-12 hoàn thành**: `core/historical_runner.py`, `scripts/run_historical_memory.py`, `utils/historical_api.py` và 16 test mới (9 runner + 4 leakage + 3 retry). Pipeline tích hợp hai episode bằng giá/HMM/graph/Alpha/nhãn thật với LLM giả lập; tiếp tục không fit/chạy upstream trùng, phục hồi lỗi xuất kho từ journal và chặn dữ liệu/model tương lai. `--plan-only` xác nhận 868 ứng viên, 852 hợp lệ, 16 loại; không ghi artifact hoặc gọi API. Compileall, 211 unit tests, E2E và 38 leakage tests đều pass. [Chi tiết và lệnh dùng](phase_c_historical_memory.md#w2-12--runner-offline-và-tiếp-tục-từ-checkpoint). Chưa sinh kho nghiên cứu >300 episode; W2-13/W2-14 vẫn chờ.

- **W2-11 hoàn thành**: `core/historical_outcomes.py`, 8 test nhãn và 2 test leakage. Kiểm hàm P&L dùng chung, lịch ba phiên, chi phí, quyền/thanh khoản và giá VCI thật trên cả bốn mã; chu kỳ chưa tất toán bị từ chối. Compileall, 195 unit tests, E2E và 34 leakage tests đều pass. [Chi tiết](phase_c_historical_memory.md#w2-11--bộ-sinh-nhãn-kinh-tế). Chưa sinh nhãn hàng loạt hoặc Memory Bank.

- **W2-10 hoàn thành**: `core/historical_signals.py`, Alpha strict mode và 19 test mới (12 tín hiệu/checkpoint + 7 leakage). Tái sử dụng graph và Alpha Selector thật trên giá VCI đã xác minh với LLM giả lập trong kiểm thử; checkpoint giữ upstream một lần, lưu năm tín hiệu/báo cáo/provenance và độ tin cậy tin. Compileall, 185 unit tests, E2E và 32 leakage tests đều pass. [Chi tiết](phase_c_historical_memory.md#w2-10--trích-tín-hiệu-từ-snapshot-lịch-sử). Chưa chạy sinh tín hiệu hàng loạt hoặc tạo kho >300 episode; W2-11 đến W2-14 vẫn chờ.

- **W2-09 hoàn thành**: `core/bayesian_memory.py` nạp/lưu nguyên tử, kiểm schema W1, giá VCI xác minh, T+3, P&L dùng hàm engine, ID/chồng lấn và cutoff truy vấn. 12 test mới pass; compileall, 166 unit tests, E2E và 25 leakage tests đều pass. [Chi tiết và giới hạn](phase_c_historical_memory.md). Chưa sinh Memory Bank; W2-11 đến W2-14 vẫn chờ.

- **W2-01 hoàn tất tích hợp gate giá**: tái xác minh offline bộ giá thô ngày 26/09, giữ 852 chu kỳ qua gate và danh sách 16 chu kỳ bị loại. Compileall, 154 unit tests, E2E và 23 leakage tests đều pass; [biên bản gate](phase_a_price_gate.md) ghi bằng chứng và lệnh tái lập. Phase C/D vẫn chưa thực hiện.

### 2026-09-26

- **W2-01 mở gate giá**: `core/execution_prices.py`, `scripts/verify_execution_price_gate.py`, `data/execution_prices` và [biên bản gate](phase_a_price_gate.md). `--verify-only` PASS bốn mã/5.004 nến/tám mẫu quyền; 852/868 chu kỳ qua gate, 16 trường hợp có quyền/tham chiếu bị loại có lý do. Bộ test giá/cutoff/provenance pass 19 test. Phase C chưa sinh nhãn hoặc Memory Bank; sẽ dùng snapshot thô mới. Kết quả bốn gate tích hợp ghi ở cuối biên bản gate.

- **Nâng cấp dependency hoàn thành**: `vnstock 4.0.9`, `vnai 2.6.2`, kho gói chính thức trong `requirements.txt`; sửa loader KBS để giữ nguyên VN-Index theo điểm. API lịch sử/danh mục/hồ sơ VCI/KBS hoạt động; compileall, 135 unit tests, E2E và 16 leakage tests đều pass. CSV/model cũ vẫn xác minh hợp lệ; gate giá W2-01 tiếp tục bị chặn. Xem [biên bản và lệnh tái lập](../../vnstock_upgrade.md).

- **W2-08 hoàn thành**: `tests/test_regime_leakage.py` pass 8 test (`py -3.13 -X utf8 -m unittest discover -s tests -p test_regime_leakage.py -v`). Đổi giá tương lai thành NaN/Infinity/giá cực lớn không đổi endpoint; model prefix và fallback giữ tính nhân quả; từ chối model tương lai, snapshot chưa cắt, thiếu train/warm-up, metadata sai và NumPy scalar. Đã sửa và thêm test hồi quy cho artifact với đặc trưng gần hằng số. Runner `--verify-only` tiếp tục pass artifact thật. Gate trước merge: compileall, 135 unit tests, E2E và 16 leakage tests đều pass; [lệnh tái lập](phase_b_regime_detector.md#w2-08--kiểm-toán-thời-gian-và-hồi-quy). W2-16 vẫn chờ toàn bộ deliverables W2.

- **W2-07 hoàn thành**: API archive và snapshot trong `core/regime_detector.py`, kèm `validate_regime_state`; `unittest discover -s tests -p test_regime_api.py -v` pass 4 test schema/JSON, ngày nghỉ, hash prefix và model fit sau cutoff. Đã bổ sung quy tắc model prefix cho episode lịch sử vào đặc tả phương pháp. Gate trước merge: compileall, 126 unit tests, E2E và 8 leakage tests đều pass.

- **W2-06 hoàn thành**: ánh xạ latent `[BULL, CHOPPY, CONSOLIDATION, BEAR]`, HMM hội tụ sau 41 vòng (gain 0,00082354), cả bốn trạng thái đạt tiêu chí; không kích hoạt fallback trên artifact thật. `unittest discover -s tests -p test_regime_mapping.py -v` pass 4 test mapping/phá hòa/tiêu chí fallback. Đã bổ sung calibration vào artifact, giữ nguyên tham số HMM đã fit. Gate trước merge: compileall, 122 unit tests, E2E và 8 leakage tests đều pass.

- **W2-05 hoàn thành**: `MarketRegimeDetector` fit một lần và ghi JSON nguyên tử; `scripts/train_regime_detector.py` fit dữ liệu thật và `--verify-only` đều pass (1.251 nến, 1.052 đặc trưng, train cuối 2022-12-30). `unittest discover -s tests -p test_regime_model.py -v` pass 5 test về refit, khoảng train, checksum, model/scaler và seed. Gate trước merge: compileall, 118 unit tests, E2E và 8 leakage tests đều pass.

- **W2-04 hoàn thành**: cấu hình bất biến trong `core/regime_detector.py`, ghim `hmmlearn==0.3.3` và `scikit-learn==1.7.2` trong `requirements.txt`; đã cài thành công wheel Python 3.13. Đặc tả chốt hyperparameters, mapping, fallback và yêu cầu `train_end_date <= as_of_date` trước fit dữ liệu thật. Gate trước merge: compileall, 113 unit tests, E2E và 8 leakage tests đều pass.

- **W2-03 hoàn thành**: `core/regime_detector.py`, `tests/test_regime_features.py` và [đặc tả Phase B](phase_b_regime_detector.md); `py -3.13 -X utf8 -m unittest discover -s tests -p test_regime_features.py -v` pass 4 test. Đặc trưng vector hóa, 200 phiên khởi động, input vượt cutoff bị từ chối. Gate trước merge: compileall, 113 unit tests, E2E và 8 leakage tests đều pass.

### 2026-09-24

- **W2-01 hoàn thành kiểm toán, gate giá bị chặn**: [biên bản Phase A](phase_a_data_and_sampling.md) ghi phản hồi `Quote.history` VCI/KBS, sự kiện FPT ngày 13/06 và 24/08/2022, giới hạn của giá điều chỉnh. Đã kiểm tra trực tiếp hai provider và mã nguồn `vnstock` 3.5.2; không sinh nhãn kinh tế.
- **W2-02 hoàn thành**: cùng biên bản chốt lịch 600 nến khởi động, bước 3 phiên; `py -3.13 -X utf8 scripts/prepare_historical_data.py --verify-only` pass 5 CSV và 4 dòng thay nguồn; kiểm tra lịch bằng Pandas/NumPy cho 217 chu kỳ ứng viên mỗi mã, tổng 868, không chồng lấn hoặc dùng nến 2023+. Đây là lịch ứng viên, chưa phải `HistoricalTaskRecord`.
- **Hồi quy Phase A**: `py -3.13 -m compileall agents core data_manager scripts tests utils` pass; `py -3.13 -X utf8 -m unittest discover -s tests -v` pass 109 test; `py -3.13 scripts/run_end_to_end_test.py` pass; `py -3.13 -X utf8 -m unittest discover -s tests -p 'test_*leakage.py' -v` pass 8 test. W2-16 vẫn chưa hoàn thành vì các task còn lại của W2 chưa thực hiện.
