# Tuần 2 — phân loại chế độ thị trường và Historical Memory Bank

Tài liệu này chia [mục Tuần 2 của kế hoạch tổng](../plan/plan.md#7-kế-hoạch-thực-hiện-chi-tiết-8-tuần-deliverables-matrix) thành các task có đầu ra và điều kiện hoàn thành riêng. Phase A đã có [biên bản kiểm toán giá và quy tắc lấy mẫu](phase_a_data_and_sampling.md); các module regime và Memory Bank vẫn chờ thực hiện.

## Mục tiêu và điều kiện đầu vào

Cuối W2 cần có `core/regime_detector.py` phân loại bốn chế độ từ VN-Index, `data_manager/regime_memory_store.json` chứa **hơn 300** chu kỳ đã tất toán giai đoạn 2018–2022, và `outputs/vnindex_regimes_2018_2022.png`. Bản ghi phải khớp [schema W1](../plan/week1/historical_task_record.schema.json) và [đặc tả phương pháp](../methodology_spec.md).

**Gate dữ liệu bắt buộc:** [kiểm toán W1](../plan/week1/data_audit.md) xác nhận CSV sạch về nến và lịch, nhưng chưa xác nhận Open/Close là giá thực thi point-in-time. W2-01 phải xác minh giá thực thi hoặc hệ số điều chỉnh theo từng thời điểm **trước khi sinh bất kỳ nhãn kinh tế nào**. Nếu chưa đạt, tiếp tục các task regime độc lập; W2-11 đến W2-14 giữ trạng thái chưa hoàn thành. Không thay bằng lợi nhuận Close-to-Close hoặc gán nhãn từ giá chưa xác thực.

## Quy ước cập nhật tiến độ

- `[ ]` chưa xong; `[x]` chỉ dùng khi đủ đầu ra và bằng chứng kiểm tra. Ghi `Đang làm` hoặc `Bị chặn` cùng lý do nếu cần.
- Sau **mỗi task hoàn thành**, cập nhật ô trạng thái và thêm một dòng vào **Nhật ký tiến độ**: ngày, mã task, file/đầu ra, lệnh kiểm tra và kết quả. Không đánh dấu hoàn thành theo mức độ ước lượng.
- Mỗi task kỹ thuật làm trên nhánh riêng từ `develop` theo `AGENTS.md`; chỉ merge khi bốn gate bắt buộc đều pass. Commit message mô tả kỹ thuật, không chứa ký hiệu tuần/ngày tiến độ.
- Giữ nguyên hợp đồng `LONG` mua `Open(t+1)`, bán `Close(t+3)` sau ba phiên; `SHORT` giữ tiền mặt; phí 0,25% và trượt giá 0,10% ở cả hai chiều. Tín hiệu ở ngày $t$ chỉ được đọc dữ liệu có ngày `<= t`.

## A. Chốt dữ liệu và mẫu chu kỳ

| Mã | Task | Đầu ra / điều kiện hoàn thành | Phụ thuộc | Trạng thái |
| --- | --- | --- | --- | --- |
| W2-01 | Xác minh giá thực thi point-in-time và cơ chế điều chỉnh doanh nghiệp từ hai provider được phép | [Biên bản Phase A](phase_a_data_and_sampling.md) đối chiếu cổ tức/chia tách và API VCI/KBS; **gate giá bị chặn** vì chưa có giá thô hoặc hệ số điều chỉnh PIT; không phát hành nhãn | Kiểm toán W1 | [x] Kiểm toán xong; gate bị chặn |
| W2-02 | Chốt cách lấy mẫu chu kỳ 2018–2022 | [Quy tắc Phase A](phase_a_data_and_sampling.md) chốt $t$, $t+1$, $t+3$, bước 3, warm-up 600 nến, 868 chu kỳ ứng viên không nhãn trên bốn mã và giới hạn phủ năm | W2-01 cho nhãn; CSV W1 cho lịch | [x] |

## B. Market Regime Detector

| Mã | Task | Đầu ra / điều kiện hoàn thành | Phụ thuộc | Trạng thái |
| --- | --- | --- | --- | --- |
| W2-03 | Đặc tả và tính đặc trưng VN-Index theo ngày | [Đặc tả Phase B](phase_b_regime_detector.md), `build_regime_features` và 4 test công thức/khởi động/cutoff; không dùng breadth | CSV W1 | [x] |
| W2-04 | Chốt cấu hình Gaussian HMM và khả năng tái lập | [Cấu hình Phase B](phase_b_regime_detector.md): HMM 4 trạng thái, seed 42, scaler train-only, dependency ghim và tiêu chí fallback chốt trước fit | W2-03 | [x] |
| W2-05 | Cài đặt fit một lần và lưu artifact của HMM | `MarketRegimeDetector.fit/save/load`, runner offline và `data_manager/regime_model.json`: 1.251 nến train, 1.052 hàng đặc trưng, checksum và phiên bản được xác thực | W2-04 | [x] |
| W2-06 | Ánh xạ trạng thái HMM sang bốn tên regime | Quy tắc từ thống kê tập train thành `BULL`, `BEAR`, `CHOPPY`, `CONSOLIDATION` ổn định qua lần chạy; quyết định fallback đa yếu tố nếu HMM không đủ tách biệt được ghi bằng tiêu chí xác định trước | W2-05 | [ ] |
| W2-07 | Cung cấp API phân loại tại `as_of_date` | `get_market_regime`/`classify_regime` trả `regime_id`, `regime_name`, `volatility_level`, `trend_strength` và ngày cuối đặc trưng theo [schema W1](../plan/week1/market_regime_state.schema.json); JSON dùng kiểu Python gốc | W2-05, W2-06 | [ ] |
| W2-08 | Kiểm thử regime và cắt thời gian | Test thay dữ liệu sau $t$ không đổi kết quả tại $t$; test từ chối input vượt cutoff, thiếu warm-up, model/data không khớp và trạng thái/schema sai bằng `ValueError`/`AssertionError` | W2-07 | [ ] |

## C. Historical Memory Bank

| Mã | Task | Đầu ra / điều kiện hoàn thành | Phụ thuộc | Trạng thái |
| --- | --- | --- | --- | --- |
| W2-09 | Cài đặt cấu trúc lưu và xác thực `HistoricalTaskRecord` | `core/bayesian_memory.py` nạp/lưu JSON, ID duy nhất, đủ 5 tín hiệu, `as_of_date < entry_date < exit_date` theo phiên, kết quả kinh tế nhất quán; lưu nguyên tử và từ chối record sai | Schema W1, W2-02 | [ ] |
| W2-10 | Trích tín hiệu năm agent từ snapshot lịch sử | Indicator → Pattern → Trend chạy một lần cho mỗi $t$; Alpha và Sentiment chỉ dùng dữ liệu/tin tức `<= t`, bỏ tin không ngày; lưu tín hiệu và provenance, không gọi lại upstream cho cùng điểm | W2-02, W2-07 | [ ] |
| W2-11 | Tạo nhãn kinh tế cho chu kỳ đã tất toán | Dùng **chính** `compute_round_trip_net_return` của engine trên giá đã qua W2-01, tính `net_return_pct`, hướng, thắng/thua LONG; `SHORT` không mở vị thế; test đối chiếu entry/exit sau đúng ba phiên | W2-01, W2-02 | [ ] |
| W2-12 | Viết runner offline có thể tiếp tục | Script tạo episode kết hợp regime, tín hiệu và nhãn; checkpoint sau mỗi điểm, seed/cấu hình cố định, API LLM qua `_invoke_with_retry`, lỗi leakage dừng ngay, không lưu record nửa chừng | W2-09, W2-10, W2-11 | [ ] |
| W2-13 | Sinh Memory Bank 2018–2022 | `data_manager/regime_memory_store.json` có >300 episode hợp lệ trên bốn mã; không chứa quyết định/exit sau 2022, không có cặp chu kỳ cùng mã chồng lấn trái quy tắc W2-02 | W2-12 | [ ] |
| W2-14 | Kiểm toán Memory Bank | Kiểm schema, ID, ngày, số lượng theo mã/regime/năm, dấu P&L, độ phủ năm và không có giá trị NumPy trong JSON; mọi vi phạm ném ngoại lệ; xuất báo cáo QA có thể tái lập | W2-13 | [ ] |

## D. Biểu đồ và chốt tuần

| Mã | Task | Đầu ra / điều kiện hoàn thành | Phụ thuộc | Trạng thái |
| --- | --- | --- | --- | --- |
| W2-15 | Vẽ chế độ VN-Index 2018–2022 | `outputs/vnindex_regimes_2018_2022.png` có chú giải bốn regime, trục ngày/điểm rõ, không vẽ dữ liệu 2023+; kiểm tra ảnh bằng mắt trước khi dùng trong báo cáo | W2-07 | [ ] |
| W2-16 | Chạy bốn gate hồi quy và kiểm toán leakage | `compileall`, toàn bộ unit tests, E2E xác định và `tests/test_*leakage.py` đều pass; ghi số test và kết quả, không có đổi công thức P&L hay chạy lại upstream trong nhánh đối chứng | W2-08, W2-14, W2-15 | [ ] |
| W2-17 | Rà soát deliverables, cập nhật tiến độ và tích hợp | Đối chiếu đủ ba đầu ra W2, sửa trạng thái trong kế hoạch tổng, commit Conventional Commit và merge theo `AGENTS.md` sau khi W2-16 pass | W2-01 đến W2-16 | [ ] |

## Nhật ký tiến độ

### 2026-09-26

- **W2-05 hoàn thành**: `MarketRegimeDetector` fit một lần và ghi JSON nguyên tử; `scripts/train_regime_detector.py` fit dữ liệu thật và `--verify-only` đều pass (1.251 nến, 1.052 đặc trưng, train cuối 2022-12-30). `unittest discover -s tests -p test_regime_model.py -v` pass 5 test về refit, khoảng train, checksum, model/scaler và seed. Gate trước merge: compileall, 118 unit tests, E2E và 8 leakage tests đều pass.

- **W2-04 hoàn thành**: cấu hình bất biến trong `core/regime_detector.py`, ghim `hmmlearn==0.3.3` và `scikit-learn==1.7.2` trong `requirements.txt`; đã cài thành công wheel Python 3.13. Đặc tả chốt hyperparameters, mapping, fallback và yêu cầu `train_end_date <= as_of_date` trước fit dữ liệu thật. Gate trước merge: compileall, 113 unit tests, E2E và 8 leakage tests đều pass.

- **W2-03 hoàn thành**: `core/regime_detector.py`, `tests/test_regime_features.py` và [đặc tả Phase B](phase_b_regime_detector.md); `py -3.13 -X utf8 -m unittest discover -s tests -p test_regime_features.py -v` pass 4 test. Đặc trưng vector hóa, 200 phiên khởi động, input vượt cutoff bị từ chối. Gate trước merge: compileall, 113 unit tests, E2E và 8 leakage tests đều pass.

### 2026-09-24

- **W2-01 hoàn thành kiểm toán, gate giá bị chặn**: [biên bản Phase A](phase_a_data_and_sampling.md) ghi phản hồi `Quote.history` VCI/KBS, sự kiện FPT ngày 13/06 và 24/08/2022, giới hạn của giá điều chỉnh. Đã kiểm tra trực tiếp hai provider và mã nguồn `vnstock` 3.5.2; không sinh nhãn kinh tế.
- **W2-02 hoàn thành**: cùng biên bản chốt lịch 600 nến khởi động, bước 3 phiên; `py -3.13 -X utf8 scripts/prepare_historical_data.py --verify-only` pass 5 CSV và 4 dòng thay nguồn; kiểm tra lịch bằng Pandas/NumPy cho 217 chu kỳ ứng viên mỗi mã, tổng 868, không chồng lấn hoặc dùng nến 2023+. Đây là lịch ứng viên, chưa phải `HistoricalTaskRecord`.
- **Hồi quy Phase A**: `py -3.13 -m compileall agents core data_manager scripts tests utils` pass; `py -3.13 -X utf8 -m unittest discover -s tests -v` pass 109 test; `py -3.13 scripts/run_end_to_end_test.py` pass; `py -3.13 -X utf8 -m unittest discover -s tests -p 'test_*leakage.py' -v` pass 8 test. W2-16 vẫn chưa hoàn thành vì các task còn lại của W2 chưa thực hiện.
