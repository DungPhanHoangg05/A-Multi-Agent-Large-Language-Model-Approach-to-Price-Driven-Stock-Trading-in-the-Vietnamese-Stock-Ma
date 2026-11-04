# Bản ghi metadata tác giả

Đây là master record làm việc, trích từ nguồn bài tại commit `0d3e4309` và cập nhật theo phản hồi trực tiếp ngày **05/11/2026**: “thứ tự đúng, ORCID của Phương-Thai Nguyen là 0009-0006-2033-7788. Các phần còn lại như credit, funding,... giữ nguyên”. Thứ tự năm tác giả và ORCID của Phuong-Thai đã được người dùng xác nhận; các giá trị còn lại giữ theo nguồn hiện có theo chỉ dẫn. Không coi việc giữ nguyên là xác minh độc lập ownership của mọi ORCID hoặc hồ sơ đồng thuận riêng của mọi tác giả. Email và decision letter/route vẫn chưa được cung cấp.

## Tên, thứ tự và thông tin liên hệ

| Thứ tự trong `main.tex` | Tên đang ghi | ORCID đang ghi trong `main.tex` | Affiliation IDs | Corresponding đang ghi | Email |
|---|---|---|---|---|---|
| 1 | Hong-Viet Tran | 0000-0002-4675-2123 | 1 | Không gắn `corref` | Chưa có |
| 2 | Hoang-Dung Phan | 0009-0003-6859-0852 | 1 | Không gắn `corref` | Chưa có |
| 3 | Thanh-Tam Do Thi | 0000-0002-7594-276X | 1, 2 | Không gắn `corref` | Chưa có |
| 4 | Phuong-Thai Nguyen | 0009-0006-2033-7788 | 1 | Không gắn `corref` | Chưa có |
| 5 | Van-Tang Nguyen | 0009-0009-7266-2437 | 3 | Có, `cor1` | Chưa có |

Nguồn: [main.tex](../paper/main.tex), dòng 62–81. Cả năm tên/affiliations/corresponding marker ở [main_submit.tex](../paper/main_submit.tex) hiện nằm trong comments. Không có lệnh `\ead` ở hai entrypoints; không suy email từ tên hoặc đơn vị.

Reviewer R18 nêu hai cặp biến thể: **Do Thi Thanh-Tam / Thanh-Tam Do Thi** và **Tang-Van Nguyen / Van-Tang Nguyen**. Theo xác nhận thứ tự và chỉ dẫn giữ nguyên thông tin còn lại, nguồn bài tiếp tục dùng **Thanh-Tam Do Thi** và **Van-Tang Nguyen** như bảng trên. Chưa có khai báo given/family names riêng cho cổng nộp; không tự đảo tên theo quy ước ngôn ngữ.

Riêng Phuong-Thai Nguyen: nguồn T32 từng comment ORCID **0009-2063-7338-7789** trong submit, khác bản main và không khớp checksum. Theo xác nhận trực tiếp, đã đổi đúng một chuỗi ở `main_submit.tex` thành **0009-0006-2033-7788**, khớp bản main. Giữ nguyên comment author block, tên, thứ tự và các trường khác. Năm ORCID hiện tại khớp checksum offline; đây chỉ là kiểm tra số học, **không phải xác minh độc lập đăng ký hoặc ownership**. ZIP/manifest T32 vẫn giữ chuỗi cũ như bằng chứng lịch sử.

## Affiliations đang ghi

| ID | Organization nguyên văn | City | Country |
|---|---|---|---|
| 1 | Institute for Artificial Intelligence, University of Engineering and Technology, Vietnam National University | Hanoi | Vietnam |
| 2 | Faculty of Economic Information System and E-Commerce, Thuongmai University | Hanoi | Vietnam |
| 3 | Faculty of Technology and Data Science, Foreign Trade University | Hanoi | Vietnam |

Giữ nguyên tên đơn vị và mapping theo chỉ dẫn của người dùng; hiện không có địa chỉ bưu chính trong các block này. Không bổ sung địa chỉ hoặc đổi tên đơn vị bằng suy đoán.

## CRediT đang ghi

Giữ nguyên tên vai trò và mã viết tắt trong `main.tex`, dòng 127–135; bản submit có cùng nội dung trong comments. Thứ tự danh sách này không thay thế thứ tự tác giả ở title page.

| Tác giả | Nội dung nguyên văn sau tên |
|---|---|
| Hong-Viet Tran | Conceptualization (C); Methodology (M); Software (So); Validation (Va); Formal analysis (Fo); Data curation (D); Original draft preparation (O); Writing-review and editing (E); Project administration (P). |
| Hoang-Dung Phan | Methodology (M); Software (So); Formal analysis (Fo); Investigation (I); Resources (R); Data curation (D); Original draft preparation (O); Writing-review and editing (E); Visualization (Vi); Supervision (Su). |
| Thanh-Tam Do Thi | Methodology (M); Investigation (I); Data curation (D); Original draft preparation (O); Writing-review and editing (E); Supervision (Su). |
| Phuong-Thai Nguyen | Methodology (M); Investigation (I); Data curation (D); Original draft preparation (O); Visualization (Vi); Supervision (Su). |
| Van-Tang Nguyen | Conceptualization (C); Software (So); Validation (Va); Investigation (I); Original draft preparation (O); Project administration (P); Funding acquisition (Fu). |

Giữ nguyên phân công theo chỉ dẫn của người dùng. Chưa được cung cấp hồ sơ xác nhận riêng của cả năm tác giả; không suy hồ sơ đồng thuận từ việc tên xuất hiện trong LaTeX hoặc tự ghi đã thu đủ signatures.

## Funding và declaration đang ghi

[Acknowledgments](../paper/sections/acknowledgments.tex): “This research is funded by Foreign Trade University under research program number FTURP02-2026-08”. Hai entrypoints đều include section này. Conflict statement đang ghi “Authors state no conflict of interest.” ở cả hai bản. Giữ nguyên các statements theo phản hồi của người dùng; không xác minh độc lập tài trợ hoặc tạo declaration mới.

## Journal và route cần hồ sơ tác giả

Hai entrypoints có `\journal{Knowledge-Based Systems}`. File nhận xét reviewer cũng nhắc tên tạp chí; chưa tìm thấy decision letter hoặc quyết định cho phép nộp lại trong workspace. Không suy trạng thái revise/resubmit từ reviewer comments hoặc class `elsarticle`.

Tác giả cần cung cấp:

1. Journal đích và manuscript ID, nếu có.
2. Nội dung quyết định của editor, ngày quyết định, hạn sửa nếu có và yêu cầu nộp lại nguyên văn liên quan. Nếu chưa có letter, ghi rõ chưa có; không tự tạo bằng chứng.
3. Route cụ thể: revision của hồ sơ hiện tại, resubmission/new submission theo hướng dẫn editor, hoặc route khác được chỉ rõ.
4. Yêu cầu blind/nonblind, title page riêng, declaration/CRediT/funding và các file cần nộp theo letter/hướng dẫn áp dụng. Comment author block không đủ chứng nhận toàn bản đã anonymous; funding hiện vẫn xuất hiện ở bản submit.

Chưa áp dụng chính sách tạp chí dựa trên phỏng đoán. Khi có route, đối chiếu đúng hướng dẫn chính thức đang áp dụng; chưa build PDF, upload, liên hệ editor hoặc submit.

## Các trường còn thiếu

Email của corresponding author (và từng người nếu route yêu cầu), given/family fields khi cổng nộp yêu cầu, hồ sơ đồng thuận nếu cần, manuscript ID, decision letter và route blind/nonblind chưa được cung cấp. Chỉ dẫn “giữ nguyên” áp dụng các giá trị có sẵn, không biến các trường chưa có thành đã xác nhận. Không yêu cầu xác nhận lại thứ tự hoặc ORCID Phuong-Thai đã được chốt. T33 còn phần route/liên hệ; R18 còn response và locator PDF cuối tại T34/T35.

Nguồn bài sau sửa được khóa riêng tại [author_metadata_v1](../outputs/revision/author_metadata_v1/manifest.json); [sources.zip](../outputs/revision/author_metadata_v1/sources.zip) có đủ 46 paper files hiện tại. Giữ nguyên các source ZIP/manifest lịch sử; T32 là snapshot trước sửa metadata, không còn là toàn bộ current source. Không dùng checker current-source T32 để xác nhận ngược thay đổi mới; đối soát 101 references của T32 qua đúng hash/member trong ZIP T32 khi cần.

## Provenance của bản trích

SHA-256 dưới đây là **nguồn trước sửa metadata**, tính trên byte đọc trực tiếp tại T32. Riêng `paper/main_submit.tex` hiện đã đổi ORCID; hash cũ phải đối chiếu member trong `manuscript_rewrite_v1/sources.zip`, không gọi là current hash. File Word là tài liệu riêng đang untracked, chỉ đọc để đối chiếu R18; không đưa file này vào commit. Các locators là dòng nguồn T32, chưa phải vị trí PDF cuối.

| Nguồn | SHA-256 |
|---|---|
| `paper/main.tex` | `bcf115331f2f34a617f1ca6e515bf2dc6eb31a9c01aa249fb1ee254313f5c7df` |
| `paper/main_submit.tex` | `495201e29022dca547655cbeed9d56fe78dae8176d994993d87be7420c61ad7e` |
| `paper/sections/acknowledgments.tex` | `144503e0908506d64cd52bb99480fd3082c63bc63831e66299e237007f868e9c` |
| `outputs/revision/reviewer_crosswalk_v1/author_pending.json` | `f5f5b875bf6e621822c6e14c75b9acd17c41e7195764ce415ba3a18ae48f8808` |
| `outputs/revision/manuscript_rewrite_v1/manifest.json` | `fb73df6e8a28d3d69a73fcb70eec1e9ce2025e87374add60bde007ebb49b0440` |
| `Reviewer Comments for author.docx` | `614f6d6fee623ed1eb124019fed3489d432d93a1316a4b3714266d15c706f15a` |
