# Hồi quy theo phạm vi cuối (T28)

Kết quả: **PASS_SCOPED_REGRESSION**, 48/48 tests, 0 failures, 0 errors, 0 skips.

Case IDs và lý do phạm vi nằm trong cases.json; log chạy mới là tests.log. Không chạy toàn suite hoặc dùng số tests cũ làm kết quả chạy mới.

Đối soát 21 receipts nguồn/đầu ra T05–T27 và bundle T22. Tái kiểm actual raw: 375 jobs/147 paired groups, prompt max=4187 <6500; 40 order mismatches/chín cross-epoch groups giữ nguyên.

T16: một source non-runtime .gitattributes đã thêm đúng ba eol rules T18; snapshot gốc giữ nguyên trong historical_gitattributes.bin, hash khớp receipt và Git blob. Không ghi hash gốc thành hash current; không sửa manifest cũ hoặc bypass hash cho code/runtime.

Mock tests kiểm hành vi code; bằng chứng LLM thật là raw T04, không phải mocks.
Tests guard phát hiện native row-wise causal FAIL không chứng nhận zero-leakage. News PIT/domain validation vẫn thiếu theo T08.
Không chạy lại toàn unit suite/E2E/compileall, bootstrap, render chart, scorer hoặc baseline trên market data; chỉ kiểm receipts và ca hợp đồng được chọn.
T16 receipt .gitattributes là source lịch sử, CLI verify T16 hiện tại sẽ từ chối hash này. T28 kiểm nguyên blob Git và đúng ba eol rules bổ sung T18; các source/runtime/license còn lại khớp.
T22 kiểm bundle/metadata; không kiểm lại weights sidecar hoặc chạy lại clean replay T23. Alias/fingerprint không là immutable hosted revision.
T28 không đóng R1–R18 hoặc đạt T30; T29 còn đối soát nhận xét, các giới hạn causal/PIT/order/epoch/quyền public/PID phải chuyển sang bài/response.

Kiểm hash-only: `py -3.13 -X utf8 scripts/check_revision_regression.py check`.
Muốn chạy lại dùng `build --output outputs/revision/final_regression_recheck_v1` chưa tồn tại. Không gọi API hoặc đọc .env.
