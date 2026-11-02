# Chạy R1 theo profile revision_72h

Tiến độ và điều kiện đóng R1 nằm trong [plan.md](../plan.md). Tài liệu này chỉ hướng dẫn vận hành. Profile mới không chạy 540 calibration hay grid 8.100 cũ và không chuyển 23 calibration cũ thành test.

## Đầu vào đã chuẩn bị

- Bank: `outputs/revision/r1_72h_bank_v2/`; 102 market units, sáu block, 12 ngày decision. BHN chỉ có ba fold mới; tám mã còn lại đủ sáu block.
- Corpus audit: 180 records, 177 URL/text identities; 154 excerpts đủ điều kiện date/URL/content consistency được rescore local. Scores, model/tokenizer hashes và model card nằm trong bank. Giữ nguyên mọi cache legacy.
- Mapping `0=NEG, 1=POS, 2=NEU` đối chiếu [model card tại revision pinned](https://huggingface.co/5CD-AI/Vietnamese-Sentiment-visobert/blob/d7738b85200272f10ba8b048d80236c8c582b581/README.md). Dùng nguyên tokenizer.json pinned qua PreTrainedTokenizerFast, CPU eval, max length 256, score P(POS)−P(NEG). Không gọi Groq để rescore.
- Date-only khả dụng từ ngày kế tiếp, cửa sổ 90 ngày, tối thiểu ba bài dedup. Publication/content PIT vẫn là giả định chưa được chứng nhận độc lập; social-domain scorer chưa được validation tài chính bằng người. Không coi missing là neutral, peer set rỗng.
- Coverage đủ panel 18 nên gate **factorial B/A/S/AS/P** được khóa. Panel và donor train-only nằm trong bank manifest; không chọn lại theo prediction.
- Baseline cùng 102 units: 714 predictions, 408 daily ledgers. Reuse price/factor predictions/fits trên 27 symbol/fold cũ sau kiểm input; fit fold lịch sử và matched-input model có sentiment mới. Numeric rộng ở study cũ không trở thành LLM evidence mới.
- Runtime/run: `outputs/revision/r1_72h_run_v2/`. Run manifest khóa source/runtime/input hashes, T0/deadline và shard allocation trước API. [Execution protocol](r1_72h_protocol.json) là hợp đồng hiện hành: hai cutoff/scope, không calibration/exposure control; các trường template cũ còn trong bank chỉ phục vụ tái sử dụng numeric inputs, không điều khiển lịch API.

## Lệnh bạn cần chạy bằng API key thật

Chạy ở root repo, Python 3.13. Các biến `GROQ_ORG_1_API_KEY` … `GROQ_ORG_5_API_KEY` đã có trong `.env`; không cần cấu hình lại hoặc gửi key qua chat. Biến môi trường của terminal có ưu tiên hơn `.env`. Năm key khác nhau không tự chứng minh năm org: mapping org do tác giả xác nhận; provider identity/quota chỉ được coi là đã biết nếu response cung cấp.

Smoke ngoài evaluation, một cặp B/AS mỗi org:

```powershell
py -3.13 -X utf8 scripts/run_revision_72h.py smoke --all
```

Lệnh tạo năm process. Mỗi org chạy hai vision requests rồi hai Decision requests, tối thiểu 20 LLM calls tổng. Có repair/retry thì vẫn tính vào caps chung. Catalogue check read-only kiểm quyền truy cập hai model đã khóa; không chứng minh quota cả ngày đủ. Khi đủ năm `smoke_complete.json`, mới chạy nghiên cứu:

```powershell
py -3.13 -X utf8 scripts/run_revision_72h.py run --all
```

Khi quota chặn, giữ nguyên bank/run/code và đợi provider cho phép rồi chạy lại đúng lệnh đang dở. Có thể resume riêng một org bằng `--org 1` thay cho `--all`; không chạy hai worker cùng org. Mọi variant của một unit ở cùng shard và cùng upstream realization. Charts/temp/checkpoint/client tách theo org.

Responses SDK đã lưu được replay qua cùng parser khi node chưa checkpoint; node hoàn tất được reuse. Format repair tạo attempt mới, không lặp lại response lỗi định dạng trong cùng lần chạy. Không dùng text fallback thay vision, không tự đổi model, không điền CASH khi lỗi. Quota ngày hoặc lỗi provider làm shard pause có archive; lần resume tôn trọng reset đã lưu trong SQLite.

## Caps và điểm dừng

- Nghiên cứu: **474 decisions, 240 vision calls, 714 LLM calls tối thiểu**. Smoke thêm 10 decisions/20 calls; tổng tối thiểu 734 calls.
- Tối đa **200 LLM attempts/org**, **1.000 toàn study**, **600 Decision attempts** tổng và **40 Decision attempts/org trong rolling 24 giờ**. Bao gồm smoke/repair/failed attempts. Caps tổng không reset sau mỗi lệnh hoặc mỗi ngày.
- Pacing tối thiểu 30 giây/model/org cùng reset provider; không bảo đảm tránh mọi 429 nếu org còn có workload khác. Mỗi org chỉ một request đang xử lý.
- T0 và deadline T0+60h được khóa trong `run_manifest.json`; dừng để dành thời gian phân tích. Không sửa manifest/quota.sqlite3 hoặc đổi output nhằm lách cap/deadline. Không mua quota hoặc đổi model.
- Allocation LPT dựa trên tải unit đã biết trước outcome, thay phân bổ round-robin nháp trong bank. Tải dự kiến kể smoke: 97/98/96/96/97 decisions theo org; mỗi org còn dư so với 120 attempts qua ba cửa sổ 24h. Số org/repeats không làm tăng số quan sát thị trường độc lập.

## Lệnh offline

```powershell
py -3.13 -X utf8 scripts/run_revision_72h.py status
py -3.13 -X utf8 scripts/run_revision_72h.py verify
```

Status đếm market units, cặp B/AS hoàn tất, variants/repeats, attempts/errors và tokens SDK trả về; worker event cuối không phải khẳng định process vẫn sống. Verifier kiểm source/input hashes và raw-response lineage; PASS integrity không đóng R1.

Sau khi inference đủ grid:

```powershell
py -3.13 -X utf8 scripts/run_revision_72h.py analyze
```

Analyzer cần đủ 102 cặp thật. Trước T0+60h còn thiếu panel thì yêu cầu resume; sau deadline có thể phân tích các cặp đầy đủ nhưng giữ panel thiếu là incomplete. Không ghi đè analysis release có sẵn.

Đầu ra: Full/Base/non-LLM trên cùng target/lịch/cost, confusion/per-class/pooled/macro/regime/cohorts, LONG rate, daily ledger, gross diagnostic riêng, bootstrap sáu block joint cross-section 10.000 lần seed 20261102, repeat/upstream dispersion đúng panel, calls/tokens/errors/latency và bảng TeX. Mean return trên 51 symbol-block accounts không phải portfolio chung; ledger fractional/immediate cash chưa chứng nhận settlement/total return. Bootstrap ít block chỉ có tính mô tả.

Sau đó cần kiểm tra release, cập nhật manuscript/response/PDF locators mới để đóng R1. Các model-call tests dùng fake trong thư mục temp không phải bằng chứng thực nghiệm; không có kết quả Full mới trước bước API ở trên.

## Chỉ khi cần tái dựng offline

Các bước `prepare`, `assets`, `numeric`, `freeze` đã được thực hiện trên máy này, không cần chạy lại. Chúng từ chối ghi đè dữ liệu đã khóa. Muốn tái dựng một study khác cần đường dẫn bank/run mới và lập protocol phù hợp trước inference; không chỉnh lịch/seed theo outcome của study này.
