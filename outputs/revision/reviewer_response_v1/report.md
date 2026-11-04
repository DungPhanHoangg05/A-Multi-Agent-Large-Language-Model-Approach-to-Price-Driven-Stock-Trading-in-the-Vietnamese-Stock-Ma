# Phản hồi reviewer và archive cuối — bản nội bộ

Đã viết lại [response hiện tại](../../../revision/response_to_reviewers.md) đủ **18 comments/87 yêu cầu con**, đối chiếu release cuối và metadata tác giả xác nhận ngày 05/11/2026. [Mapping](response_map.json) giữ câu trả lời thực, evidence hash, current source anchors và giới hạn từng yêu cầu. Đây là response draft có thể review, **không phải response đã nộp hoặc chứng nhận đóng comment**. Mọi `comment_closed=false`, locator PDF cuối vẫn null; 0/18 comments đóng.

Response bỏ số liệu/closure/page locators không còn hiện hành của các bản cũ. Bản response trước sửa được khóa nguyên byte tại [previous_response.zip](previous_response.zip), khớp SHA nguồn T29; không sửa manifest T29 để hợp thức hóa nguồn mới. Không chỉnh `paper/` trong task: đủ 46 files khớp snapshot T33. Mọi raw/labels/predictions/cache/runtime lịch sử giữ nguyên.

## Nội dung và thiếu sót đã nêu

- Primary 102 units, 25 UP/77 DOWN; Full/Base BA 52,96/49,71%, account means −0,797/−0,750%; không alpha/profitability/superiority claim. Constants, logistic, momentum, continuous hold và exposure có đúng support/denominators.
- Hai panels chín units/ba executions, factorial bundle/placebo/interaction, HAC và numeric family giữ riêng. Không pooled repeats hoặc lấy subgroup tốt thay main; 40 order deviations/chín cross-epoch groups vẫn nêu rõ.
- Native row-wise causal gate FAIL; chưa có financial-news labels/PIT authentication, full-grid repeated design hoặc fixed/random factors qua hosted LLM. Numeric controls và offline checks không lấp những yêu cầu thực nghiệm này.
- Attribution/indicator/custom/chart/target/execution/reference corrections nối current sources. R16 [14]/[21]/[22]/[23] vẫn thiếu reviewed-version identity; không invent DOI/number mapping. Source parsing không chứng nhận render typography.
- T33 đã xác nhận thứ tự và ORCID Phuong-Thai, giữ metadata còn lại; email/decision letter/route vẫn thiếu. T34 không đòi xác nhận lại các mục đã được chỉ dẫn.

## Gói nội bộ và quyền

`private_bundle.zip` có **542 members, 114.784.275 bytes**, gồm T22 base archive nguyên byte, T23 runtime/replay evidence, phân tích cuối, scientific companions, current source/response và source ZIP lịch sử riêng. [Allowlist](package_spec.json) và [index từng member](archive_index.json) xác định phạm vi; gói lớn giữ cục bộ/ignore, không phải đã publish qua Git. Cần copy cả thư mục release khi bàn giao nội bộ.

Bản Word nhận xét riêng và `source_comments.json` không trong gói; weights sentiment không trong gói, vẫn là sidecar T22 có hash. Không nhận đã kiểm lại weights lần này. Đây là archive nhiều lớp, không là checkout phẳng tự động chạy mọi producer cũ. [Runbook](../../../revision/archive_runbook.md) có lệnh check, copy/extract, rebuild vào đích mới và tùy chọn tác giả tự chạy lại clean replay offline. T34 không chạy clean replay lại.

[Rights](rights.json) giữ `public_release_authorized=false`, `pid=null`. Author additions, OHLCV/news/model/hosted-output permissions và bản public phù hợp chưa chốt. Tác giả tự publish khi có quyền, cung cấp PID thật; không upload, tạo record, liên hệ editor hoặc submit trong task. Không có DOI giả hay blanket MIT licence. Vì thiếu quyền/PID và final PDF locators, **T34 hoàn tất phần response/private package, còn public archive/PID và bản nộp cuối**.

## Kiểm tra theo phạm vi

[QA](qa.json) đối chiếu 87 câu trả lời, 133 Markdown links, source anchors và SHA evidence; đủ headings và unique IDs, không false closure. Source audit của receipts giữ riêng current/historical:

| Receipt | Current hashes | Historical references | Tổng |
|---|---:|---:|---:|
| T28 | 5.007 | 12 | 5.019 |
| T29 | 89 | 13 | 102 |
| T31 | 63 | 12 | 75 |
| T32 | 100 | 1 | 101 |
| T33 | 105 | 0 | 105 |

38 historical references chỉ trỏ đúng member/hash của paper ZIP T32 hoặc previous response ZIP; không fallback runtime/data. Nguồn không thuộc hai loại được phép này khác byte sẽ làm audit dừng. Checker cũ chỉ cho paper fallback sẽ từ chối response mới ở T29; dùng checker release mới thay vì sửa receipt cũ.

[Tám tests](tests.log) của công cụ archive PASS: round-trip/no-overwrite, source/container tamper, traversal/case alias, credential fixture, symlink, archive-only independence và closure guard. Chỉ biên dịch hai Python files mới bằng warnings-as-errors; không full unit/compileall/E2E/leakage, inference, scorer, refit hoặc bootstrap vì không đổi đường nghiên cứu/runtime/data. T22 archive check PASS, weights chưa kiểm; đối soát runtime T28 bằng metadata, không chạy lại 48 tests T28 hoặc mười tests/replay T23.

Gói 542 members đã tái build ở đích mới từ cùng allowlist và khớp nguyên byte; kiểm từng member giải nén trong bộ nhớ, safe paths, SHA/size và nested credential-pattern scan. Scan không thay quyền phân phối hoặc chứng nhận mọi secret đã được nhận ra. Checker có chế độ archive-only, không gọi đó là kiểm current sources của workspace khác.

```powershell
py -3.13 -X utf8 scripts/package_revision_response.py check
py -3.13 -X utf8 scripts/package_revision_response.py check --archive-only
```

T35 còn build/render hai PDFs, numbering và locator thật; không dùng QA nguồn/byte thay QA từng trang. Sau sửa nguồn ở T35 phải ghi phiên bản mới, không sửa manifest đã khóa này.
