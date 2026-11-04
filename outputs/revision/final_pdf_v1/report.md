# Build và QA hai PDF hiện hành

**PASS trong phạm vi T35.** [Main](main.pdf) có **22 trang vật lý**, [submit](main_submit.pdf) có **21 trang vật lý**, mỗi bản gồm một tờ highlights riêng không đánh số. Đã kiểm trực quan đủ **43 trang Poppler 110 dpi** và đối chiếu dữ liệu/refs/metadata. Không xác nhận anonymity theo journal, quyền public, PID hoặc khả năng nộp bài khi chưa có route/decision letter.

## Những gì đã sửa

- Escape phần trăm Williams %R để BibTeX không biến phần cuối entry thành comment; bảo vệ chữ hoa của acronym và tách ghi chú version khỏi arXiv ID. Ba tài nguyên không có năm dùng `n.d.` cùng ngày truy cập đã được audit, không gán năm publication bằng năm truy cập.
- Dùng font Latin Modern dạng vector, sửa glyph chỉ báo thành bold 1 cùng định nghĩa target, ngắt đoạn HAC dài và hiển thị repository bằng link ngắn giữ nguyên đích URL. Không đổi net/gross label hoặc số liệu.
- Nới khoảng cách sơ đồ để không chồng node/chữ, giữ nguyên roles/flow. Float có thể nằm gần lời dẫn; barriers giữ bảng chính trước appendix/references. Appendix đánh số **A.1/A.2/B.1/B.2**, sửa “Appendix Appendix …”.
- Footer trung tính ghi “Historical evaluation manuscript”, không tự nói bài đã được nộp tới journal. Sửa heading declaration khỏi chữ template “mandatory”; nội dung conflict/CRediT/funding/names/order/ORCID giữ nguyên. Không bật author block ở submit hoặc bổ sung email suy đoán.
- Cấu hình metadata/link PDF để ORCID/corref không gây warning hoặc trùng destination. Hai title metadata và abstract khoa học đồng nhất; các ORCID links ở title page main khớp source đã được chỉ dẫn.

## Kiểm chứng

[QA](qa.json) và [structure](pdf_structure.json) ghi **zero LaTeX/BibTeX warnings, undefined refs/citations, overfull boxes, missing glyph warnings hoặc Type3 fonts** ở final passes. Cả hai PDF có cùng **25 labels**, **18 cited keys/reference numbers**, **sáu bảng chính/bốn bảng appendix/ba hình**. Trang Highlights riêng giải thích chênh lệch trang vật lý và số trang nhìn thấy.

Mười table payload/captions/notes khớp nguyên byte nguồn trước T35, chỉ đổi placement option. 130 ô T2/T3 được tìm thấy trong từng PDF; macro headline, funding và ba PNG giữ nguyên byte. Ba ảnh nhúng khớp pixel nguồn ở cả hai PDF. [Visual review](visual_review.json) ghi từng trang và raster SHA; [rendered_pages.zip](rendered_pages.zip) giữ đủ 43 PNG đã render. Bản main có 19 trang raster khớp byte vòng kiểm trực quan trước; ba trang đổi glyph/reference đã được xem lại, submit được xem đủ 21 trang cuối.

Các log build thực nằm trong `build_logs/main/` và `build_logs/main_submit/`, gồm final log/BibTeX/aux/bbl/fls và tám command transcripts. Compile dùng `--disable-installer`; không tải package/model, gọi provider hoặc chạy inference. Nhắc bảo trì MiKTeX ở console được giữ trong transcript; đó không phải warning LaTeX/BibTeX hoặc lỗi tài liệu. [Runtime](latex_runtime.json) ghi công cụ dùng và Python/dependency metadata để phân biệt gate hệ thống cũ với build tài liệu mới.

## Locator và response

[Response hiện tại](../../../revision/response_to_reviewers.md) và [87 request locators](response_map.json) đã đồng bộ current source SHA, vị trí PDF thật của từng bản, table/figure numbers và rendered bounding boxes. Bản PDF không in số dòng; **không invent line numbers**. Physical page 2 là title/abstract không in số trang; từ physical page 3, số nhìn thấy nhỏ hơn một. Repository-only content, author block comment của submit và entry Deng không được cite được ghi rõ là **không có vị trí render**, không gán một trang giả.

Current bibliography [1]–[18] đã kiểm đúng hai bản; không đồng nhất chúng với [14]/[21]/[22]/[23] trong bản reviewer đọc mà chưa xác thực identity/version. Locators và QA nguồn/render không bổ sung nhãn tài chính, news PIT, native causal repair hoặc thí nghiệm LLM còn thiếu. Mọi `comment_closed=false`; quyết định nghiệm thu từng comment còn T36 và các giới hạn được nêu trong response.

## Bảo toàn phiên bản và bàn giao

[original_sources.zip](original_sources.zip) giữ **47 members trước T35**: 46 paper files T33 và response T34. [sources.zip](sources.zip) giữ **48 members cuối**: 47 paper files (thêm shared layout) và response hiện tại. Các source ZIP/receipts/raw/labels/predictions cũ giữ nguyên. Không sửa exporter/data producer đã freeze chỉ để tạo bản có style mới.

[Delivery](delivery.json) nối gói private T34 nguyên hash với delta T35 gồm nguồn, hai PDF, mapping và QA. **Gói T34 không chứa sửa layout/PDF T35**; khi bàn giao phải chuyển cả hai releases và bundle T34 đang giữ cục bộ, không gọi archive cũ là current manuscript. Public package/PID vẫn chưa có, tác giả tự xử lý khi quyền được xác nhận; chưa upload/publish/submit.

T35 chỉ đổi tài liệu LaTeX/BibTeX và response: không đổi Python/runtime nghiên cứu, dữ liệu đầu vào hoặc schema. Vì vậy không compile Python, chạy unit/E2E/leakage toàn hệ thống, không rerun bootstrap/fit/replay/API. Kiểm phù hợp là build hai cây LaTeX/BibTeX, source/data/hash/metadata đối soát, kiểm refs/citations và trực quan từng trang; không gán các gate hệ thống cũ thành đã chạy lại. Native causal gate vẫn FAIL. Email/decision letter/route, quyền public/PID và historical reference identities vẫn thiếu.
