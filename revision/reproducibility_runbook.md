# Gói reproducibility nội bộ

Gói T22 khóa bytes từ final T04, scorer contract T07, numeric controls T13,
execution evidence T18, sensitivities T19 và final contracts T20. Đây là
**local private draft**, chưa có quyền phân phối công khai/PID. Không gọi API,
Hub, vendor, model forward hoặc upload để build/check/extract.

`bundle.zip` chứa source hiện hành, source ZIP lịch sử riêng, snapshots giá/tin,
numeric predictions/models, raw requests/responses/errors, parse/checkpoints,
rendered prompts và ảnh PNG rút nguyên byte từ image URIs. Không tạo lại ảnh
hoặc sửa nguyên bản requests. Bảng coverage và hashes xác định chính xác scope.
Các cache legacy chỉ xuất hiện nếu receipt khóa chúng, với vai trò bằng chứng;
không đọc cache khác theo glob hoặc làm nguồn thay thế khi thiếu dữ liệu.

Model sentiment khóa revision `d7738b85200272f10ba8b048d80236c8c582b581`.
Config và tokenizer nằm trong bundle; weights 390 MB trong `model_weights.zip`
cục bộ, không đưa vào Git. Sidecar này có hash/member receipt trong manifest và
cần được chuyển kèm nếu dựng lại toàn bộ model assets. Replay metrics từ saved
predictions không cần weights. Thiếu weights không được ghi là đã xác minh weights.
Không coi alias hosted text/vision là immutable served-weight revisions.

Runtime snapshot tách frozen receipts T04/T07 khỏi versions quan sát tại build.
Hai requirements files khóa direct/transitive packages theo markers Windows của
máy build; không là lock portable mọi OS/CUDA. Chưa có wheelhouse/interpreter
trong gói. Nếu dựng Python environment mới offline, cần chuẩn bị sẵn đúng wheels
trên máy được phép trước đó; không tự lấy mạng khi replay. T23 còn phải chứng minh
replay trong thư mục/môi trường sạch, không coi check hashes T22 thay kết quả đó.

PowerShell tại root, Python 3.13.5:

```powershell
# Check độc lập workspace/Hub/credentials, chỉ cần thư viện chuẩn Python
py -3.13 -X utf8 scripts/package_revision_reproducibility.py check

# Kiểm thêm weights sidecar đang giữ cục bộ
py -3.13 -X utf8 scripts/package_revision_reproducibility.py check --with-weights

# Đích mới; không ghi vào repo hoặc model cache đã có
py -3.13 -X utf8 scripts/package_revision_reproducibility.py extract --destination tmp/reproducibility_clean_v1

# Chỉ khi cần model assets: dùng đích mới khác
py -3.13 -X utf8 scripts/package_revision_reproducibility.py extract --with-weights --destination tmp/reproducibility_model_v1

# Build lại từ cùng nguồn vào release MỚI, snapshot đã có cục bộ
$scorerSnapshot = Join-Path $env:USERPROFILE '.cache/huggingface/hub/models--5CD-AI--Vietnamese-Sentiment-visobert/snapshots/d7738b85200272f10ba8b048d80236c8c582b581'
py -3.13 -X utf8 scripts/package_revision_reproducibility.py build --package outputs/revision/reproducibility_rebuild_v1 --snapshot $scorerSnapshot
```

Build/check dừng khi sai nguồn, hash, member set, đường dẫn ZIP, credential pattern,
model snapshot hoặc runtime dependency constraint. Không dump credential values,
không đọc `.env`, Hub token, SQLite quota, locks hoặc trạng thái workers. Việc scan
không thay đánh giá quyền chia sẻ hoặc khẳng định mọi loại secret đều được nhận ra.

T34 cần tác giả xác nhận license/quyền phân phối từng nhóm dữ liệu/model/source
và tự publish lấy PID thật. MIT notice chỉ bao phủ phần QuantAgent có nguồn;
không tự áp MIT cho dữ liệu, model weights hay mọi phần code bổ sung. Nếu phải che
nội dung để chia sẻ, tạo package public khác với mapping/hash nguyên bản và bản
đã che, không sửa nội bộ/frozen receipts hoặc ngụy nhận replay đầy đủ của bản public.

Không sửa `paper/`, PDF/source ZIP lịch sử, raw outcomes hoặc execution manifests.
OHLCV retrieval không xác thực snapshot submission; news PIT/domain validation,
native causal gate FAIL và order/epoch deviations vẫn phải công khai. Offline
replay chỉ kiểm tính tái tạo từ artifacts đã lưu, không chứng minh alpha/profitability.
