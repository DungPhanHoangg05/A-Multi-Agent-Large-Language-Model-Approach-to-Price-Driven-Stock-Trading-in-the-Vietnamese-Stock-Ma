# Bản sửa giữ khung bản thảo gốc

Theo phản hồi trực tiếp của tác giả ngày 05/11/2026, bản hiện hành giữ khung bài cũ và sửa nội dung tại chỗ theo reviewer. T31–T32 đã rút quá mạnh cấu trúc và hình minh họa; bản PDF T35 chỉ là phiên bản lịch sử của quyết định biên tập đó.

Nguồn hiện hành là `paper/main.tex` và `paper/main_submit.tex`, dùng chung các sections. Hai PDF tại release này đều có **31 trang vật lý**, tính cả trang highlights. Không có PDF hiện hành trong `paper/`; build được thực hiện ở thư mục tạm riêng để tránh trộn sản phẩm sinh với nguồn.

## Cấu trúc và hình

[Đối chiếu cấu trúc](structure_comparison.json) nối đủ **61 đầu mục** của `revision/manuscript_original.zip` tới bản hiện hành, không bỏ đầu mục nào. Giữ tám sections gốc, sáu tiểu mục Related works, bảy tiểu mục Problem Formulation, Overview và năm vai trò agent, các phần setup/results/limitations/future work/broader impact. Phần results đặt ablation trước robustness để giữ thứ tự sáu bảng cuối; các kết quả cũ không được đưa lại như kết quả hiện hành.

Appendix giữ các chủ đề gốc: prompt contracts từng vai trò, ý nghĩa shared state, năm custom formulas, năm indicator rules/consensus và reproducibility. Các giải thích này được sửa theo đường backtest thực chạy; chúng không được gọi là full/verbatim prompts hay complete populated runtime schema. Full code, raw prompts/logs và hướng dẫn Flask/tokenizer/endpoint/API vẫn ở repository/private package. Tên proprietary và tên công thức khác handler được sửa, không phục hồi lỗi để giữ nguyên tiêu đề.

Sáu figures hiện hành gồm overview, Alpha pipeline, actual chart pair, Decision pipeline, eligibility calendar và walk-forward. Ba sơ đồ chi tiết được phục hồi bằng LaTeX vector với thông số/hợp đồng đúng bằng chứng: không peer sentiment quan sát giả, không prompt cap 7.500, không grid đều S=3/N=20 cũ. Sơ đồ hệ thống vốn ở graphical abstract được trình bày thành Figure 1 trong phần architecture, không lặp hai lần. Bốn PNG sơ đồ gốc và chín PNG backtest legacy giữ nguyên byte; chín PNG legacy không được include trong nguồn gốc đã lưu và không được dùng thay kết quả cuối.

## Kiểm tra áp dụng

[QA](qa.json), [cấu trúc PDF](pdf_structure.json), [visual review](visual_review.json) và [62 raster pages](rendered_pages.zip) ghi kết quả:

- Build từng entrypoint bằng pdflatex, BibTeX và hai lượt pdflatex cuối, đều tắt installer. Logs/aux thực ở `build_logs/`. Không undefined refs/cites, overfull, missing glyph hoặc Type3 font; không span vượt trang. Có bốn underfull spacing notices mỗi PDF trong p-columns của bảng giữ nguyên; đã xem đọc được, không chồng/chặn chữ. Không tuyên bố log không có mọi thông báo.
- Đủ sáu figures, mười tables, một algorithm và 18 cited keys. Tables C.1/D.1/F.1/F.2 thay numbering appendix cũ. Mọi nội dung/caption/notes của mười table sources giữ nguyên byte; 130 numeric cells được tìm thấy trong mỗi PDF. Ba ảnh actual Pattern/Trend/calendar nhúng khớp pixel nguồn.
- Đã xem main 31 trang và submit 31 trang. Main 1–12 khớp raster byte với candidate ngay trước đã xem; main 13–31 và toàn bộ submit được xem ở bản cuối. Sơ đồ được sửa khoảng cách sau khi phát hiện chồng chữ ở candidate, không bàn giao candidate đó.
- Hai entrypoints, abstract, references, conclusion, funding/CRediT/ORCID đã xác nhận giữ nguyên byte từ T35. Cả 16 PNG hiện có giữ nguyên byte. Tất cả 61 đầu mục cũ có mapping; 87 requests/18 comments có current source hashes và vị trí PDF thực trong [response map](response_map.json).

[Parent verification](parent_verification.json) kiểm đủ **5.169 references T35 =5.158 current +11 historical source members** trong `before_sources.zip`, cùng 59 inherited historical references. Chỉ paper/response/blueprint được bridge sang đúng source trước task, không miễn hash runtime hoặc dữ liệu. PDF/source ZIP/manifest các releases cũ không bị ghi đè. T35 checker cũ không còn xác nhận toàn bộ current manuscript; receipt cũ vẫn đúng cho đúng phiên bản của nó.

Task chỉ đổi LaTeX/tài liệu/response, không đổi Python, runtime nghiên cứu, schema hay dữ liệu. Không chạy unit/E2E/leakage/full suite, inference, scorer, refit hoặc statistical resampling mới. Kiểm tra phù hợp là build/visual/source/number/hash; không gán suite cũ thành mới chạy. Các helper build/QA tạm không nằm trong runtime hoặc source release.

## Phạm vi bàn giao

`before_sources.zip` có 49 members (paper/response T35 và blueprint trước task). `sources.zip` chứa nguồn paper/response/blueprint hiện hành. Manifest mới khóa sources/outputs và các nguồn kiểm tra trực tiếp; parent receipt giữ closure đầy đủ, tránh chép lại hàng nghìn rows không đổi. Bàn giao khoa học gồm private bundle T34, delta T35 lịch sử và delta hiện hành này; không có upload, publish hay submit.

Việc giữ khung không phục hồi claims bị audit bác bỏ. Native causal gate vẫn FAIL; thiếu financial-news/PIT/semantic validation, một số hosted controls, quyền public/PID, email/decision letter/route vẫn được ghi đúng trong response. Không xác nhận reviewer đã chấp thuận hoặc đóng comment: **0/18 comments đóng**. Tiến độ và task tiếp theo chỉ ghi tại `plan.md`.
