# Bản sửa nguồn bài theo evidence cuối

Đã viết lại tám sections, abstract/highlights/title, appendix và bibliography theo scope historical exploratory của T30/T31. Hai entrypoints chia sẻ nội dung khoa học; tokens names/ORCID/affiliation/funding giữ nguyên, không suy author confirmation. Native row-wise causal gate vẫn **FAIL**, domain/news PIT validation và quyền public/PID vẫn thiếu. **Không comment nào được đóng và chưa có PDF/locators cuối.**

Title mới: *Multi-Agent LLM Decision Support for Vietnamese Equities: A Historical Evaluation*. Abstract187 từ, gồm amendment sau partial inference. Headline dùng BA Full52,96%, Base49,71%, logistic-price55,61%; Full return−0,797%, Base−0,750%. Không giữ số65/51,1 cũ hoặc kết luận isolated alpha, superiority, profitable trading, novel learned fusion. Methods công khai native causal defect, in-sample ranking/orientation và metadata mismatch; numeric controls có causal adapters là study riêng.

## Nội dung và artifacts

- Sáu bảng chính, bốn bảng appendix từ saved source rows, không refit/resample. Per-class/macro/undefined, hold khác cycles, exposure/calendar gaps, both repeat panels, seven factorial contrasts, cả23-hypothesis family và12 execution scenarios được giữ đúng support.
- Ba hình: flow code-native đúng roles; calendar đủ108 market cells/102 eligible/sáu BHN exclusions; hai actual CMG PNG giữ nguyên bytes từ T27, chọn theo date/symbol trước outcomes. Calendar PNG đã kiểm trực quan. Flow/whole-page typesetting còn chờ T35.
- [Scientific companions S1–S4](supplement/README.md) giữ đủ mọi baseline theo mã/lớp, repeats/contrasts, numeric/random family và temporal/regime/HAC diagnostics. Không đưa logs/raw prompts/full registry/tokenizer/Flask/API routing vào appendix; [implementation notes](../../../revision/implementation_notes.md) và repository lưu chi tiết vận hành.
- Bibliography áp T21: corrected metadata/key/version/claim scope, bỏ ba DOI sai identity và Qwen entry không dùng, thay các nguồn chưa xác minh theo audited replacements; thêm historical VSD settlement source từ T18. Có40 entries/18 cited keys, zero undefined cites; unused corrected entries không tự trở thành citations. [Citation actions](citation_actions.json) giữ lineage41 entries gốc. Số references reviewer đọc không tự map theo thứ tự BibTeX hiện tại, final numbering còn T35.
- [Changes](changes.json) nối87 yêu cầu con tới current source anchors và giới hạn/dependencies. Đó là thay đổi nguồn hoặc công khai thiếu sót, không phải reviewer closure/response đã gửi. R18 metadata còn T33; R9 rights/PID còn T34; native causal validation và fixed/random qua LLM chưa được bổ sung.

## Bảo toàn nguồn và QA

[Original sources](original_sources.zip) có30 members đúng byte/hash T29/T31 trước sửa; [current sources](sources.zip) có46 paper files đúng version mới. Chín legacy stock plots và các pipeline PNG cũ giữ nguyên, chỉ bỏ includes. Không sửa runtime/raw/labels/predictions/manifests lịch sử. Parent receipts sau sửa được kiểm bằng current bytes nếu khớp, hoặc đúng archived paper member/hash; ngoại lệ không áp cho runtime/data. Các verifiers cũ chỉ nhìn current paper có thể từ chối thay đổi được phép này; không gọi source lịch sử là current source.

[QA](qa.json) PASS ở mức source/data: title/abstract/highlights đồng bộ, braces/environments cân bằng, zero undefined refs/cites/input targets, đủ10 bảng/3 figures,130 instrumented numeric cells khớp raw source queries, contrast endpoints/row counts và actual PNG hashes khớp. Tái sinh artifact-only bằng final exporter tạo **31 outputs khớp byte**, không chạm current paper hoặc gọi model. Đây không phải chạy lại inference/clean-replay metrics T23. JSON numeric undefined là null, TeX/CSV là NA; audit còn giữ source CSV literals để truy vết.

[Tám tests](tests.log) đã chạy cho scale/MCC/NA/nonfinite, interval/misaligned columns, archive bridge, runtime tamper, output/path/hash guards. Hai Python files mới biên dịch với warnings-as-errors; không chạy toàn unit/E2E/leakage vì không đổi inference/feature/economic producers. Frozen runtime/source contracts được đối soát với T28; archive bridge giữ bằng chứng paper cũ. Log là transcript của lần chạy quan sát qua exec, không giả thành một suite chạy lại sau đó.

**Chưa chạy pdflatex/BibTeX hoặc QA từng trang.** T35 phải build/render main và submission, kiểm fonts/float widths/appendix length/citations/numbering rồi chốt locators. Hiện không khẳng định page layout đã PASS hoặc manuscript sẵn sàng nộp. T33/T34 vẫn cần tác giả xác nhận metadata/route/quyền public/PID; Codex không upload/submit hoặc gọi API.

## Kiểm offline và tái sinh

Tại root:

```powershell
py -3.13 -X utf8 scripts/build_revision_manuscript.py --check

# Chỉ nếu cần tái sinh tables/assets: đích mới, archive gốc giữ nguyên.
New-Item -ItemType Directory outputs/revision/manuscript_source_recheck_v1
Copy-Item outputs/revision/manuscript_rewrite_v1/original_sources.zip outputs/revision/manuscript_source_recheck_v1/original_sources.zip
py -3.13 -X utf8 scripts/build_revision_manuscript.py --release outputs/revision/manuscript_source_recheck_v1 --artifact-only
```

Artifact-only ghi dưới release mới, không overwrite paper hiện tại. Không dùng generator để refit hoặc thay dữ liệu. Sau T33/T35 nếu nguồn paper thay đổi, giữ receipt/version này và tạo version mới thay vì sửa hash guard. Tiến độ chỉ trong `plan.md`.
