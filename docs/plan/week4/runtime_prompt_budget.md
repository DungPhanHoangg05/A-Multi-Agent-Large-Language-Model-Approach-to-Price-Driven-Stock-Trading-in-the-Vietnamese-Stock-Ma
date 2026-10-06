# W4-06 — Cap báo cáo và guard prompt Decision runtime

**Phạm vi:** Decision backtest, report cap và prompt cuối trước API. Cấu hình
bàn giao tại W3 được đưa vào node thật; [receipt mới](runtime_prompt_budget_review.json)
ghi ma trận runtime, hash, bốn gate và giới hạn nghiệm thu.

## Ngân sách và đường chạy

| Báo cáo | Cap backtest | Cap live giữ nguyên |
| --- | ---: | ---: |
| Trend | 800 | 900 |
| Pattern | 800 | 900 |
| Indicator | 800 | 900 |
| Alpha | 1.100 | 1.200 |
| Sentiment | 500 | 600 |
| Tổng payload tối đa | **4.000** | **4.500** |

`agents/decision_agent.py` dùng `_BACKTEST_REPORT_CHAR_LIMITS` khi
`is_backtest` bật. `_REPORT_CHAR_LIMITS` và default của các helper giữ cap
live cũ; script đo bàn giao W3 tiếp tục tái hiện cấu hình cũ. `_distill_report`
và `_cap_report` nhận bộ cap theo lời gọi, không sửa global trong lúc chạy.

Giữ cơ chế rút gọn theo heading: Indicator lấy phần hội tụ, Alpha lấy bảng
số và consensus, Sentiment lấy bảng tổng hợp. Cap tiếp tục giữ đầu/cuối
báo cáo, không thêm suy luận tín hiệu. Các báo cáo backtest dài được rút ngắn
thêm 100/100/100/100/100 ký tự; nội dung dài không còn giữ nguyên byte.

Node dựng prompt compact theo ngôn ngữ/horizon, bao gồm báo cáo, hợp đồng
kinh tế, conflict gate và schema/hướng dẫn JSON trong chuỗi prompt. Sau khi
dựng xong, `_guard_backtest_prompt` yêu cầu **`len(prompt) < 6500`** trước
vòng format retry và `_invoke_with_retry`. 6.499 được gọi LLM, 6.500 bị
`ValueError`; lỗi ngân sách không bị coi là lỗi output để retry hoặc trả CASH.

Cả text và structured output dùng cùng chuỗi đã kiểm; retry format giữ
nguyên prompt. Schema structured của provider nằm ngoài chuỗi prompt;
giới hạn ký tự không là số token, TPM hay tổng payload HTTP của provider.
Runtime live giữ builder/cap cũ; guard này áp dụng cho backtest.

Log mới ghi cap từng báo cáo, độ dài report được đưa vào prompt, prefix và
độ dài prompt cuối; ngưỡng 7.500 cũ được thay bằng `<6500`. Prefix production
hiện bằng 0 vì W4-07 chưa chèn BRPP. Tham số `prefix_length` của guard dành
cho bước đó; mọi phần được builder thêm vào đều nằm trong kiểm độ dài cuối.

## Kiểm chứng offline

`tests/test_backtest_token_budget.py`: **11 test PASS**, gồm **8 test mới**:

- Ma trận **192 ca**: VI/EN × `1d`/`1 ngày` × bốn mã × bốn tổ hợp báo cáo
  Alpha/Sentiment × ngắn/bão hòa/có heading distill; input giữ nguyên.
- Kiểm cap backtest/live, đầu/cuối báo cáo, loại bỏ chi tiết bỏ đi; hợp đồng
  Open/Close, LONG/SHORT/CASH, phí hai chiều và conflict gate còn đủ.
- Báo cáo thiếu/rỗng không tạo section Alpha/Sentiment.
- Builder thật với tên mã kéo dài đưa prompt đến đúng 6.499/6.500; cả hai
  đường text/structured bị chặn trước wrapper/API tại 6.500.
- Template mở rộng giả định thêm 600 hoặc 2.000 ký tự: dự phòng 600 PASS,
  overflow 2.000 dừng trước API sau khi đã dựng prompt hoàn chỉnh.
- Log đúng độ dài/ngưỡng; format retry dùng prompt đã kiểm; live giữ cap cũ.

Receipt còn đo bốn ca VI/EN/daily với **BRPP thật dài đúng 600 ký tự** từ
formatter W3, chèn bằng fixture mở rộng builder và gọi node Decision thật
với LLM giả định. Đây là đo dự phòng ngân sách; W4-07 mới triển khai chèn BRPP
và reasoning production, W4-08/09 mới nối graph và xác minh nguồn PIT.

Ma trận node thật có prompt lớn nhất **5.688 ký tự**. Bốn ca dự phòng BRPP
600 có độ dài **6.268/6.272 (VI)** và **6.285/6.289 (EN)** cho `1d`/`1 ngày`;
ca lớn nhất còn 211 ký tự đến ngưỡng bị chặn. W4-07 phải đo lại sau khi thêm
hướng dẫn reasoning prior, không suy rằng headroom này tự bảo đảm template mới.

Bốn gate ngày 06/10/2026 PASS: compileall, **375 unit** (103,910 giây),
**E2E offline** (15,5 giây pipeline), **56 leakage** (9,035 giây). Receipt ghi
lệnh, exit code, thời gian process riêng và hash log. **2.388 file bảo vệ**
giữ hash trước/sau gate, gồm kho/archive và các bằng chứng đã nghiệm thu.

Giữ receipt W3/Phase A/W4-05 nguyên byte. Guard runtime của W4-06 được nghiệm
thu riêng; **Gate B và gate budget toàn luồng prior còn mở** đến khi W4-07/08
hoàn thành. Pilot/token/quota, checkpoint, giá OOS và kết quả giao dịch có
các gate riêng ở các task tiếp theo.
