# Vận hành thực nghiệm R1 trên snapshot chung

Protocol: [r1_common_protocol.json](r1_common_protocol.json). Study này thay thế **phép so sánh** đang thiếu bằng một thực nghiệm mới; không sửa prediction/label legacy, không tự nhận đã khôi phục snapshot submission. Chưa có kết quả Full nếu chưa hoàn tất inference thật.

## Thiết kế đã khóa trước khi chạy

| Fold | Train decision đến | Validation từ | Test decision từ |
|---|---|---|---|
| f2025_q4 | 30/06/2025 | 01/07/2025 | 01/10/2025 |
| f2026_q2 | 31/12/2025 | 01/01/2026 | 01/04/2026 |
| f2026_q3 | 31/03/2026 | 01/04/2026 | 01/07/2026 |

- Chín mã, 20 test/fold/mã: **540 test units**. Lịch lấy theo phiên vendor quan sát được, bước 3 và target Open kế tiếp → Close phiên thứ ba; không dùng outcome để chọn cutoff.
- Full và numeric baselines nhận cùng window 45 nến và payload alpha/sentiment của từng cutoff. Dynamic alpha tính đúng prefix tối đa 600 nến bằng node hiện tại. Numeric comparator gồm OHLCV theo vị trí và chính selected-alpha values/metrics, không lấy embedding báo cáo LLM. So sánh thông tin thị trường này không đồng nghĩa hai mô hình có cùng biểu diễn/kiến thức đã học.
- Mọi train label exit trước validation decision đầu, mọi validation label exit trước test đầu. Chỉ fit preprocessing trên train lúc chọn C/threshold bằng validation BA, refit train+validation sau selection. Thứ tự tie/grid giữ nguyên protocol.
- **540 Full-calibration units:** 20 train points cuối mỗi mã/fold, tách khỏi test. Control exposure dùng LONG rate của các Full-calibration này và seed cố định; không ép số LONG cho bằng test. Q ước lượng từ 20 điểm có độ bất định lớn và có thể đổi theo regime.
- Năm end-to-end repeats tạo lại upstream. Mười Decision-only repeats dùng đúng upstream/alpha snapshot của end-to-end repeat 0; Decision-only repeat 0 chính là decision đó, không gọi thêm hoặc coi là hai market observations.
- Indicator và Alpha trong backtest là pha Python xác định, không gọi LLM. Full bình thường cần Pattern + Trend + Decision: 3 requests. Vì vậy tối thiểu **14.580 requests**, cho **8.100 Full decision records** gồm calibration và repeats. Verifier/format/provider retries có thể tăng số calls.
- Đây là historical exploratory study trên snapshot đã biết. Không có prospective holdout, không đảm bảo model training cutoff, không coi folds hoặc repeats là các market samples độc lập. Gán regime theo gap close/SMA60 nhân quả của từng mã, không tự nhận market-wide regime.
- Calendar/corporate actions/dividends/settlement/fills chưa được chứng nhận. Ledger giữ cùng giả định fractional, cash tái dùng ngay, phí/slippage hai chiều cho mọi biến thể. Continuous hold là price-only comparator, không tự gọi là total-return account thực thi được.

## Ngân hàng offline

```powershell
py -3.13 -X utf8 scripts/run_revision_common_study.py prepare
py -3.13 -X utf8 scripts/run_revision_common_study.py features --workers 4
py -3.13 -X utf8 scripts/run_revision_common_study.py preflight
```

`prepare` từ chối ghi đè bank. Manifest khóa source data, code, protocol, runtime versions và nội dung tin đã lọc. `features` chỉ tính toán CPU, có checkpoint từng điểm và khóa OS tránh hai tiến trình cùng ghi; `--workers` là worker số học, không phải agent LLM. Receipt cuối ghi hash toàn bộ feature files. Mỗi điểm chứa selected-alpha numeric state và báo cáo deterministic; typed AIMessage trong pha này là đối tượng chứa báo cáo do code tạo, **không phải response API hoặc prediction Full**.

Không ghi model outputs giả để hoàn tất bank. Tin thiếu provenance scorer là unavailable/missing, không neutral. Không crawl/rescore hoặc tự chọn peer công ty. Peer set rỗng được khóa chung cho cả Full và comparator.

## Chạy API thật theo đợt

Key đặt riêng ở `.env` qua biến `GROQ_API_KEY`, không đưa vào Git/chat/manifest. `preflight` chỉ in có/không, không in key. `run` xác nhận hai model đã khóa có trong catalogue của tài khoản trước mọi request inference; không tự đổi model nếu thiếu. Model alias không chứng minh immutable weight revision; lưu identity/usage thực mà response trả về.

```powershell
# Smoke đường API, tối đa 100 attempts cộng dồn; chưa phải hoàn tất study.
py -3.13 -X utf8 scripts/run_revision_common_study.py run --max-requests 100

# Ví dụ resume cùng run: tăng trần cộng dồn, không khởi động repeat mới.
py -3.13 -X utf8 scripts/run_revision_common_study.py run --max-requests 500
```

`--max-requests` bắt buộc và là **trần tổng attempts của run**, không phải số calls bổ sung mỗi lệnh. Không có budget mặc định vô hạn. Mức 100 chỉ là smoke/calibration ban đầu; toàn grid cần tối thiểu 14.580 calls và có thể cần trần cao hơn cho retry. Các model text/vision có output caps 2.048/1.024; tính phí thực theo provider, không suy mức phí từ số request. Request archive ảnh/messages có thể lớn; không xóa trong lúc chạy.

Mọi invoke đi qua retry wrapper. SDK internal retries tắt để archive và counter thấy mỗi attempt. Provider `retry after` được giữ bằng deadline trước lần gọi tiếp theo, kể cả trên 60 giây. Prompt Decision từ 6.500 ký tự trở lên bị chặn trước network; giữ `_distill_report`/`_cap_report` hiện có. Messages (kể cả ảnh), schema/parameters, response dạng SDK, timing, usage, errors và parent IDs được lưu; đây không phải bản sao HTTP wire. Attempt UUID do archive tạo; provider IDs chỉ có khi SDK trả về; serialized client chứa credential không được dump. Key được redact nếu provider nhắc lại.

Full dừng nếu thiếu chart, thiếu response thật của một upstream hoặc parse không ra LONG/SHORT. Không thay bằng SHORT/CASH. Ready-state được khóa trước Decision để resume sau khi hết budget không phải tạo lại reports; mọi fold/role/kind/repeat có checkpoint riêng. Completion chỉ ghi khi đủ grid và hash tất cả artifacts. Đã hoàn tất thì không gọi lại inference. Thay code/data/protocol/runtime sau khi khóa làm resume thất bại; không gán checkpoint cũ sang treatment/repeat khác.

## Phân tích

Baseline số có thể chạy trước khi có Full:

```powershell
py -3.13 -X utf8 scripts/evaluate_revision_common_numeric.py
```

Release này ghi rõ thiếu Full và Full-train exposure control; không dùng control momentum cũ thay thế. Khi inference thật đã hoàn tất:

```powershell
py -3.13 -X utf8 scripts/run_revision_common_study.py analyze
```

Analyzer kiểm tra source/feature hashes, ready parents, node traces và replay prediction từ raw response. Chỉ sau đó mới dùng Full-calibration để tạo exposure control, fit matched logistic, xuất confusion/per-class metrics, daily MTM/fees/turnover/exposure, và phân bố 5/10 repeats. Khoảng binomial của calibration LONG rate chỉ là diagnostic với giả định IID; không phải interval bảo đảm dưới phụ thuộc thời gian, không là CI hiệu quả dự báo hoặc exposure tương lai.

Không gộp tất cả repeats thành số thị trường độc lập, không chọn seed/repeat tốt nhất, không đưa p-value superiority từ các fold phụ thuộc vào kết luận. Sửa bản thảo và chốt R1 chỉ sau khi có đủ kết quả thật cùng kiểm tra các giới hạn còn lại. Các unit tests dùng LLM giả trong temp directory chỉ kiểm tra hợp đồng phần mềm; không phải bằng chứng thực nghiệm.

## Lượt smoke và khóa lại bank

Bank/run `v1` là smoke bị dừng sau 2 response vision thật, chưa có prediction Full: guard cũ đã nhầm yêu cầu Indicator phải gọi LLM. Source trước sửa được bảo toàn trong `r1_common_bank_v1/source_snapshot.zip`. Runner hiện dùng bank/run/output `v2`. Lịch, runtime, giá, tin và AST hàm sinh feature không đổi; [feature_reuse.json](../outputs/revision/r1_common_bank_v2/feature_reuse.json) ghi kiểm tra và nguồn. Chỉ bank ID/self-hash của feature đổi, không sửa feature/market-input hash. Không chuyển response smoke sang run mới. Script `refreeze_revision_common_bank.py` là thao tác chuyển phiên bản một lần, từ chối ghi đè bank đích.
