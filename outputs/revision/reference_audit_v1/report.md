# Đối chiếu references và câu dẫn

Audit ngày 04/11/2026 bao phủ **41 BibTeX entries, 37 keys được dẫn, 40 lệnh citation và 45 lần dùng key** trong hợp các file được gọi từ `main.tex` và `main_submit.tex`. Shared sections được đếm một lần theo vị trí nguồn, không nhân đôi giữa hai entrypoints. Không có key thiếu định nghĩa hoặc trùng trong bibliography. Bốn entry chưa được cite là Kakushadze, ViSoBERT, Qwen3 và gpt-oss.

Đây là bảng đề xuất cho lần sửa bài sau T30. Nguồn `.tex`, `.bib`, PDF, runtime và artifacts thực nghiệm giữ nguyên. R16 còn cần thay đổi trong bản thảo, response và locators của bản cuối; audit này không tự đóng R16.

## Kết quả và quyết định

| Hành động chính | Số entries / 41 | Ý nghĩa |
|---|---:|---|
| `retain` | 20 | Giữ danh tính nguồn đã đối chiếu; có thể bổ sung URL/version/edition. Câu dẫn vẫn phải đúng phạm vi bằng chứng. |
| `correct` | 11 | Sửa metadata, key, version hoặc loại publication. |
| `add_citation` | 3 | Entry đang có cần được dẫn tại câu tương ứng: 101 Alphas, ViSoBERT, gpt-oss. |
| `remove` | 4 | Ba DOI sai danh tính và Qwen3 chưa dùng/không chứng nhận alias model thực chạy. |
| `replace` | 3 | Pham herding chưa xác minh; edition Wilder chưa khóa; Williams title/year chưa xác minh. Nguồn thay ghi riêng. |

Các nhóm trên loại trừ nhau theo **hành động chính**, không phải đếm tổng số lỗi. Giữ entry không đồng nghĩa giữ mọi câu đang dẫn entry đó. [Bảng 41 mục](changes.csv) có locator và hành động câu dẫn; [JSON đầy đủ](reference_audit.json) giữ nguyên fields gốc, fields đề xuất, giới hạn và nguồn chính thức từng mục.

Các sửa đổi có ảnh hưởng lớn:

- `kang2021singleasset`: DOI `10.1016/j.eswa.2020.114236` là bài đánh giá chuyên gia xét duyệt dự án khoa học/công nghệ. Bỏ entry và claim về single-stock adaptations đang dựa vào nó; không thay metadata thành bài khác chủ đề. [Elsevier](https://www.sciencedirect.com/science/article/pii/S0957417420309556).
- `vo2019efficiency`: DOI `10.3390/jrfm12020100` là bài về financial structure, misery index và tăng trưởng tại Pakistan. Bỏ entry và clause weak-form efficiency Việt Nam. [MDPI](https://www.mdpi.com/1911-8074/12/2/100).
- `truong2020technical`: DOI `10.21511/imfi.17(4).2020.02` là bài về cash level/corporate performance tại GCC. Bỏ entry và claim technical trading dưới price limits đang dựa vào nó. Quy định execution T18 chỉ dùng làm nguồn quy định, không thay nghiên cứu hiệu quả giao dịch. [Publisher](https://businessperspectives.org/publishing-policies2/cash-level-and-corporate-performance-evidence-from-the-gulf-cooperation-council-countries).
- `pham2021herding`: DOI trả 404 và chưa xác minh được tổ hợp title/authors/year gốc. Thay bằng **bài khác** của Vo và Phan Dang có institutional record; chỉ dùng metadata conference/preprint đã xác minh, không gán journal issue/DOI chưa khóa. Viết lại theo mẫu 299 công ty HOSE giai đoạn 2005–2015, bỏ kết luận literature-wide “none employs LLM-based agents”. [UEH](https://digital.lib.ueh.edu.vn/handle/UEH/56589).
- TradingAgents có bốn tác giả Xiao, Sun, Luo, Wang; sửa attribution Tauric Research và tên trong câu dẫn thành TradingAgents. Giữ năm first posting 2024, ghi rõ reviewed revision v7 năm 2025. [arXiv v7](https://arxiv.org/abs/2412.20138v7).
- Tsantekidis dùng **limit order book**, không phải candlestick images; đổi key đề xuất thành `tsantekidis2017lob`, loại `inproceedings`, và viết lại câu dẫn. Deng thuộc **issue tháng 3/2017**, dù online năm 2016; đổi năm/key và tách hai mốc. [IEEE LOB](https://ieeexplore.ieee.org/abstract/document/8010701/metrics), [IEEE Deng](https://ieeexplore.ieee.org/abstract/document/7407387).
- Pin QuantAgent **v3** năm 2025 để giữ đúng tên và nguồn comparator T16; URL unversioned hiện chỉ sang QuantHarness/v4. Bỏ claim chart vision/đa agent vắng ở prior systems theo T16/T17. [QuantAgent v3](https://arxiv.org/abs/2509.09995v3).
- FutureX thiếu **Yixiao Tian** trong danh sách gốc: đề xuất đủ 31 tác giả. Tách PredictionMarketBench khỏi mô tả live trials vì đây là historical backtesting framework; prediction-market/future-event benchmarks không chứng nhận stock-order execution. [FutureX v3](https://arxiv.org/abs/2508.11987v3), [PredictionMarketBench v1](https://arxiv.org/abs/2602.00133v1).

## Nguồn cần dẫn và bổ sung

101 Alphas có metadata publisher đầy đủ: Wilmott 2016(84), 72–81, DOI `10.1002/wilm.10525`. ArXiv v3 ghi journal-ref 72–80; bảng đề xuất ưu tiên pagination publisher và ghi lại khác biệt. Thêm cite tại câu 101 expressions, đồng bộ registry **15 custom +70 adaptations** theo T09, không mô tả là thực thi nguyên vẹn 101 công thức. [Wiley](https://onlinelibrary.wiley.com/doi/abs/10.1002/wilm.10525), [arXiv v3](https://arxiv.org/abs/1601.00991v3).

ViSoBERT được đề xuất dẫn theo EMNLP 2023, 5191–5207, DOI `10.18653/v1/2023.emnlp-main.315`. Dùng tên đầy đủ theo paper thay vì tự chuyển các tên rút gọn trên author index. Mô tả đúng kiến trúc XLM-R và pretraining social media tiếng Việt. Nguồn classifier fine-tuned **5CD-AI/Vietnamese-Sentiment-visobert** là một mục riêng; model card không xác nhận hiệu lực trên tin tài chính Việt Nam hoặc revision của cache lịch sử. [ACL Anthology](https://aclanthology.org/2023.emnlp-main.315/), [classifier card](https://huggingface.co/5CD-AI/Vietnamese-Sentiment-visobert).

White đang được nhắc tên mà chưa có entry/cite. Bổ sung **Halbert White (2000), Econometrica 68(5), 1097–1126, DOI `10.1111/1468-0262.00152`**. Dùng issue September 2000; platform online date 2003 không thay năm issue. Đây là future method, không nói study đã chạy Reality Check hoặc đồng nhất với exact null/Holm ở T14. [Wiley article](https://onlinelibrary.wiley.com/doi/10.1111/1468-0262.00152), [issue](https://onlinelibrary.wiley.com/toc/14680262/2000/68/5).

[Năm mục bổ sung/thay thế](additions.json) gồm White, classifier card, TA-Lib RSI, TA-Lib WILLR và Vo/Phan Dang. Hai docs TA-Lib thay nguồn implementation tại RSI/Williams %R khi edition sách chưa xác minh; không kết luận các sách là giả. Lane được sửa title thành “Lane’s Stochastics” theo archive publisher tháng 5/1984; pagination chưa kiểm ghi unknown thay vì bịa. Publication year của live docs/model card không rõ được để `null`, dùng access date khi chuyển sang bibliography. [RSI](https://ta-lib.github.io/ta-doc/indicator/RSI.htm), [WILLR](https://ta-lib.github.io/ta-doc/indicator/WILLR.htm), [Lane archive](https://technical.traders.com/archive/display2.asp?mo=MAY&yr=1984).

## Giới hạn phương pháp và bàn giao

Đối chiếu danh tính và câu dẫn bằng publisher/DOI/arXiv, official docs, author/institutional records; không dùng kết quả aggregator làm nguồn xác minh. Có **60 lần tải HTML** và **51 primary URLs** liên quan quyết định. [Registry](sources.json) lưu metadata đã lọc, thời điểm, status, URL redirect, hash khi tải được, và ghi nhận từng mục. HTTP 200 không tự chứng minh metadata; HTTP 202/403/420, timeout hoặc challenge không được coi là full-text verification. Với publisher chặn tải, indexed primary content được đối chiếu và giới hạn ghi rõ. Hash HTML chỉ nhận diện lần tải; raw HTML trong `tmp/` không được đóng gói thành archive công khai. Không tuyên bố đã đọc toàn văn mọi nguồn.

Không suy DOI tồn tại là câu dẫn đúng. Lo được giữ cho phương pháp nhận diện mẫu phi tham số, không phải hybrid rules; Harvey cho multiplicity, không phải factor decay/capacity; Hurst cho trend following. FinGPT/BloombergGPT, Tetlock/FinBERT, chart benchmarks và survey được thu hẹp theo dữ liệu/phương pháp của từng nguồn. Citation nền không chứng nhận actual frozen prompts có CoT, causal visual grounding, PIT news, zero leakage hoặc profitability; những quyết định T04/T08/T10/T14/T16/T17 vẫn áp dụng.

T29 dùng bảng này làm checklist nội dung; **T32 sau gate T30** mới áp dụng fields, key renames và citation rewrites vào hai cây bài. Cần chuyển các ký tự đặc biệt trong JSON sang escaping BibTeX/TeX đúng cách, không chép máy móc `%`, `&` hoặc Unicode name vào style không hỗ trợ. T34/T35 kiểm response R16, bibliography build và locators của bản cuối. Các locator trong audit là **file/line trước sửa**, không là locator nghiệm thu cuối.

## Kiểm tra

QA xác nhận đủ 41 entries, 45 lần dùng key, năm nguồn bổ sung, không key thiếu/trùng, mọi citation location có hành động ở mục tương ứng, không replacement thất lạc hoặc proposed key trùng. JSON hữu hạn, CSV dùng `NA` cho trường không áp dụng; local links tồn tại. **19 nguồn và tám outputs =27 hashes** được khóa trong [manifest](manifest.json), có self-digest; [QA](qa.json) ghi phép kiểm cụ thể. Nguồn bài/bibliography và các parent manifests không đổi byte.

Không chạy compile/unit/E2E/leakage suite: chỉ tạo phân tích JSON/CSV/Markdown và cập nhật kế hoạch, không đổi code/test/runtime/schema đầu vào. Không gọi API/inference hoặc build PDF. Kiểm hash offline:

```powershell
py -3.13 -X utf8 -c "from pathlib import Path; from scripts.audit_revision_lineage import verify; print(verify(Path('outputs/revision/reference_audit_v1')))"
```
