# Bản thảo giữ tên, ký hiệu và cấu trúc của tác giả

Theo chỉ dẫn trực tiếp ngày 05/11/2026, nguồn hiện hành trong `paper/` giữ tên **Enhancing Multi-Agent Large Language Models for Stock Trading through Quantitative Alpha Integration**. Việc đổi tên và rút gọn mạnh ở các bản trước là lựa chọn biên tập không còn áp dụng. Bản này là bài báo đầy đủ, tự chứa nội dung khoa học; response nằm riêng tại `revision/response_to_reviewers.md`.

## Nội dung được giữ và sửa

[Đối chiếu cấu trúc](structure_comparison.json) kiểm đủ 61 đầu mục gốc: tám sections chính, các phần phương pháp/từng agent, kết quả, giới hạn, kết luận, appendix và tài liệu tham khảo. Giữ sáu figures, mười tables, một thuật toán và 18 cited keys. Các sơ đồ đã sửa đúng hợp đồng thực nghiệm vẫn được giữ; không đưa lại sơ đồ hay kết quả legacy sai.

[Đối chiếu công thức](formula_comparison.json) ghi đủ 24 khối equation/align của phần Problem Formulation. Mười tám khối khớp nguyên bản sau chuẩn hóa LF, gồm OHLCV/window, time contract, net-return target với nhãn +1/-1, IC, composite/top-five và các công thức sentiment. Sáu khối giữ môi trường/ký hiệu/bố cục gốc nhưng có sửa khoa học cần thiết:

- Hai diagnostics dùng signal đã định hướng IC như triển khai thực tế.
- Phân rã agent phân biệt history với chart window và context aggregate/count/missingness thực nhận.
- Lịch kiểm định dùng các ngày eligible thực, thay grid đều S=3/N=20 không còn đúng.
- Comparator là Base bỏ cả factor và sentiment; chênh lệch không được gọi là tác động alpha riêng.
- Sharpe/MDD tài khoản dùng daily-close wealth và anchor, tránh annualize sai chu kỳ rời rạc.

Thuật toán dùng lại `algorithm2e` với ruled/vlined/linesnumbered. Hai entrypoints dùng cùng năm keywords từ bản main gốc; submit gốc có thêm keyword Vietnamese stock market, nay được thống nhất với main. Tên/thứ tự tác giả, ORCID đã xác nhận, affiliations, funding, CRediT và conflict statement giữ nguyên so với bản trước task.

Abstract, năm highlights, bốn contributions và conclusion trình bày phương pháp tích hợp tín hiệu định lượng/ngôn ngữ Việt, xây dựng tín hiệu single-asset, thiết kế so sánh shared-report và phát hiện về phân loại/kinh tế. Không thay đóng góp bằng checklist audit; cũng không thêm claim mới về learned fusion, causal alpha, superiority hoặc profitability chưa được bằng chứng hỗ trợ.

## Kiểm tra và phiên bản

[Main](main.pdf) có **34 trang**, [submit](main_submit.pdf) **35 trang vật lý**, gồm highlights sheet. [QA](qa.json), [structure](pdf_structure.json), [visual review](visual_review.json) và [69 ảnh trang](rendered_pages.zip) ghi kiểm tra cả hai bản cuối: không undefined refs/cites, warning, overfull, missing glyph, Type3 hoặc chữ vượt trang. Bốn underfull spacing notices trong mỗi PDF thuộc bảng giữ nguyên, đã xem đọc được. Appendix F xuất hiện trước hai bảng thuộc phần đó, không bị float ngược lên phần trước.

Mười table sources/captions/notes và cả 16 PNG giữ nguyên byte; 130 numeric cells được tìm thấy trong mỗi PDF. Ba PNG được nhúng khớp pixel với nguồn. Đã xem từng trang của cả hai bản cuối, không dùng kết quả xem candidate lỗi thay cho bản giao.

[Response map](response_map.json) nối đủ 87 requests tới nguồn và vị trí PDF mới, đồng thời ghi đúng việc giữ tên theo yêu cầu tác giả ở R17.6. Không suy việc có câu trả lời thành reviewer chấp thuận.

[Parent verification](parent_verification.json) kiểm 92 references T35a: **81 current +11 historical members** khớp trước task trong `before_sources.zip`. Kiểm tiếp đủ 5.169 references T35 và 59 historical references bằng đúng hash/archive/member, không fallback dữ liệu/runtime. Các PDF/source ZIP/manifest cũ giữ nguyên phiên bản lịch sử. Checker current-source của release cũ không dùng để xác nhận nguồn đã sửa này.

`sources.zip` có 52 members: 50 paper files, response và blueprint. `before_sources.zip` lưu đúng 52 nguồn trước task. `build_commands.json`, `build_logs/` và `latex_runtime.json` ghi lệnh build tắt installer, executable/input hashes và renderer. Bàn giao nghiên cứu đầy đủ vẫn cần private bundle T34 và các delta có tham chiếu; PDF mới không được coi là đã có trong bundle cũ.

Chỉ sửa LaTeX/tài liệu, không đổi code/runtime/schema hoặc dữ liệu nghiên cứu nên không chạy Python unit/E2E/leakage/full suite. Kiểm áp dụng là LaTeX/BibTeX, visual QA, metadata, source/data/hash và locators. Không API, inference, scorer, fit hoặc bootstrap mới. Native causal gate vẫn FAIL; domain/news PIT/hosted-control shortfalls, public rights/PID và email/editorial route còn thiếu. **0 comments đóng**, chưa publish hoặc submit. Tiến độ chỉ đặt trong `plan.md`.
