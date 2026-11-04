# Bản ghi metadata tác giả để xác nhận

Đây là bản trích từ nguồn bài tại commit `0d3e4309`, **chưa phải master record được tác giả xác nhận**. Mọi giá trị dưới đây là quan sát trong repository, không chứng nhận danh tính, quyền sở hữu ORCID, đồng thuận tác giả hoặc quyền nộp lại. Bản ghi dùng để nhận thông tin chuẩn trước khi đồng bộ title page, manuscript và hệ thống nộp bài.

## Tên, thứ tự và thông tin liên hệ

| Thứ tự trong `main.tex` | Tên đang ghi | ORCID đang ghi trong `main.tex` | Affiliation IDs | Corresponding đang ghi | Email |
|---|---|---|---|---|---|
| 1 | Hong-Viet Tran | 0000-0002-4675-2123 | 1 | Không gắn `corref` | Chưa có |
| 2 | Hoang-Dung Phan | 0009-0003-6859-0852 | 1 | Không gắn `corref` | Chưa có |
| 3 | Thanh-Tam Do Thi | 0000-0002-7594-276X | 1, 2 | Không gắn `corref` | Chưa có |
| 4 | Phuong-Thai Nguyen | 0009-0006-2033-7788 | 1 | Không gắn `corref` | Chưa có |
| 5 | Van-Tang Nguyen | 0009-0009-7266-2437 | 3 | Có, `cor1` | Chưa có |

Nguồn: [main.tex](../paper/main.tex), dòng 62–81. Cả năm tên/affiliations/corresponding marker ở [main_submit.tex](../paper/main_submit.tex) hiện nằm trong comments. Không có lệnh `\ead` ở hai entrypoints; không suy email từ tên hoặc đơn vị.

Reviewer R18 nêu hai cặp biến thể: **Do Thi Thanh-Tam / Thanh-Tam Do Thi** và **Tang-Van Nguyen / Van-Tang Nguyen**. Cần tác giả cung cấp cách viết chuẩn, cách tách given/family names khi cổng nộp yêu cầu và thứ tự cuối; không tự đảo tên theo quy ước ngôn ngữ.

Riêng Phuong-Thai Nguyen: bản submit đang comment ORCID **0009-2063-7338-7789**, khác bản main. Kiểm tra chữ số cuối offline cho thấy chuỗi submit không khớp checksum; năm chuỗi trong cột ORCID main khớp checksum. Đây chỉ là kiểm tra số học, **không xác minh đăng ký hoặc ownership**. Không tự đổi chữ số cuối của chuỗi lỗi thành ORCID mới hoặc chọn chuỗi main làm giá trị chuẩn. Cần tác giả cung cấp ORCID thực của người này; nếu không dùng ORCID, tác giả phải xác nhận rõ.

## Affiliations đang ghi

| ID | Organization nguyên văn | City | Country |
|---|---|---|---|
| 1 | Institute for Artificial Intelligence, University of Engineering and Technology, Vietnam National University | Hanoi | Vietnam |
| 2 | Faculty of Economic Information System and E-Commerce, Thuongmai University | Hanoi | Vietnam |
| 3 | Faculty of Technology and Data Science, Foreign Trade University | Hanoi | Vietnam |

Cần xác nhận tên đơn vị chính thức và mapping từng tác giả; hiện không có địa chỉ bưu chính trong các block này. Không bổ sung địa chỉ hoặc đổi tên đơn vị bằng suy đoán.

## CRediT đang ghi

Giữ nguyên tên vai trò và mã viết tắt trong `main.tex`, dòng 127–135; bản submit có cùng nội dung trong comments. Thứ tự danh sách này không thay thế thứ tự tác giả ở title page.

| Tác giả | Nội dung nguyên văn sau tên |
|---|---|
| Hong-Viet Tran | Conceptualization (C); Methodology (M); Software (So); Validation (Va); Formal analysis (Fo); Data curation (D); Original draft preparation (O); Writing-review and editing (E); Project administration (P). |
| Hoang-Dung Phan | Methodology (M); Software (So); Formal analysis (Fo); Investigation (I); Resources (R); Data curation (D); Original draft preparation (O); Writing-review and editing (E); Visualization (Vi); Supervision (Su). |
| Thanh-Tam Do Thi | Methodology (M); Investigation (I); Data curation (D); Original draft preparation (O); Writing-review and editing (E); Supervision (Su). |
| Phuong-Thai Nguyen | Methodology (M); Investigation (I); Data curation (D); Original draft preparation (O); Visualization (Vi); Supervision (Su). |
| Van-Tang Nguyen | Conceptualization (C); Software (So); Validation (Va); Investigation (I); Original draft preparation (O); Project administration (P); Funding acquisition (Fu). |

Cần tác giả xác nhận phân công hiện hành và đồng thuận của cả năm người đối với danh sách, thứ tự, đóng góp và bản sửa. Không suy đồng thuận từ việc tên đã xuất hiện trong LaTeX.

## Funding và declaration đang ghi

[Acknowledgments](../paper/sections/acknowledgments.tex): “This research is funded by Foreign Trade University under research program number FTURP02-2026-08”. Hai entrypoints đều include section này. Conflict statement đang ghi “Authors state no conflict of interest.” ở cả hai bản. Đây là statements có sẵn cần tác giả xác nhận còn đúng, không phải xác nhận mới của Codex.

## Journal và route cần hồ sơ tác giả

Hai entrypoints có `\journal{Knowledge-Based Systems}`. File nhận xét reviewer cũng nhắc tên tạp chí; chưa tìm thấy decision letter hoặc quyết định cho phép nộp lại trong workspace. Không suy trạng thái revise/resubmit từ reviewer comments hoặc class `elsarticle`.

Tác giả cần cung cấp:

1. Journal đích và manuscript ID, nếu có.
2. Nội dung quyết định của editor, ngày quyết định, hạn sửa nếu có và yêu cầu nộp lại nguyên văn liên quan. Nếu chưa có letter, ghi rõ chưa có; không tự tạo bằng chứng.
3. Route cụ thể: revision của hồ sơ hiện tại, resubmission/new submission theo hướng dẫn editor, hoặc route khác được chỉ rõ.
4. Yêu cầu blind/nonblind, title page riêng, declaration/CRediT/funding và các file cần nộp theo letter/hướng dẫn áp dụng. Comment author block không đủ chứng nhận toàn bản đã anonymous; funding hiện vẫn xuất hiện ở bản submit.

Chưa áp dụng chính sách tạp chí dựa trên phỏng đoán. Khi có route, đối chiếu đúng hướng dẫn chính thức đang áp dụng; chưa build PDF, upload, liên hệ editor hoặc submit.

## Mẫu trả lời xác nhận

Tác giả có thể trả lời bằng văn bản, sửa các giá trị cần đổi hoặc xác nhận rõ từng nhóm:

- **Danh sách/thứ tự/tên:** xác nhận năm dòng trong bảng hoặc cung cấp danh sách chuẩn, gồm given/family names nếu cần.
- **ORCID:** xác nhận từng người; cung cấp riêng giá trị đúng của Phuong-Thai Nguyen hoặc xác nhận không hiển thị ORCID.
- **Affiliations/liên hệ:** xác nhận ba đơn vị và mapping; xác nhận corresponding author, email liên hệ và email từng người nếu route yêu cầu.
- **CRediT/đồng thuận/declarations:** xác nhận nội dung trên hoặc cung cấp bản sửa; xác nhận đã có đồng thuận mọi tác giả.
- **Route:** journal/manuscript ID, quyết định editor và yêu cầu blind/nonblind; nếu còn thiếu hồ sơ thì nêu rõ phần thiếu.

Chỉ sau câu trả lời đủ căn cứ mới lập master record được xác nhận và đồng bộ hai nguồn bài. Giữ nguyên các source ZIP/manifest lịch sử; sửa metadata sau đó cần phiên bản nguồn mới và QA T35, không sửa receipt T32 để che thay đổi.

## Provenance của bản trích

SHA-256 tính trên byte nguồn đọc trực tiếp. File Word là tài liệu riêng đang untracked, chỉ đọc để đối chiếu R18; không đưa file này vào commit. Các locators là dòng nguồn T32, chưa phải vị trí PDF cuối.

| Nguồn | SHA-256 |
|---|---|
| `paper/main.tex` | `bcf115331f2f34a617f1ca6e515bf2dc6eb31a9c01aa249fb1ee254313f5c7df` |
| `paper/main_submit.tex` | `495201e29022dca547655cbeed9d56fe78dae8176d994993d87be7420c61ad7e` |
| `paper/sections/acknowledgments.tex` | `144503e0908506d64cd52bb99480fd3082c63bc63831e66299e237007f868e9c` |
| `outputs/revision/reviewer_crosswalk_v1/author_pending.json` | `f5f5b875bf6e621822c6e14c75b9acd17c41e7195764ce415ba3a18ae48f8808` |
| `outputs/revision/manuscript_rewrite_v1/manifest.json` | `fb73df6e8a28d3d69a73fcb70eec1e9ce2025e87374add60bde007ebb49b0440` |
| `Reviewer Comments for author.docx` | `614f6d6fee623ed1eb124019fed3489d432d93a1316a4b3714266d15c706f15a` |
