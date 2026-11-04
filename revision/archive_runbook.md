# Archive phản hồi và bằng chứng cuối — nội bộ

Release `outputs/revision/reviewer_response_v1/` là **local private draft**, không phải archive public hoặc bản sẵn sàng nộp. `rights.json` giữ `public_release_authorized=false`, `pid=null`. Không có API/upload/provider probe trong các lệnh dưới đây. Chỉ dẫn giữ metadata của tác giả không cấp quyền phân phối dữ liệu/model/raw hosted outputs.

## Thành phần và phiên bản

`private_bundle.zip` là gói tổng hợp có index từng member. File lớn này giữ cục bộ và được ignore riêng; `package_spec.json`, `archive_index.json`, hashes, response mapping và QA được theo dõi trong Git. Không coi việc commit index là đã publish archive.

- Base `outputs/revision/reproducibility_v1/bundle.zip` giữ nguyên 4.844 members với nguồn/inputs/calls/parse/checkpoints lịch sử. Base là ZIP lồng riêng, không ghi đè code/input cũ bằng code mới.
- Runtime/metrics/isolation T23 giữ riêng tại `outputs/revision/clean_replay_v1/`, gồm NumPy runtime image đã khóa. Không có interpreter/wheelhouse cài mới; Python/stdlib vẫn dùng runtime sẵn có.
- Các outputs phân tích cuối, scientific companions S1–S4, nguồn bài sau metadata T33, response mới và code vận hành hiện tại nằm theo đường dẫn repository. Snapshot ZIP T32/T33 phân biệt nguồn lịch sử với current source. Các bảng cũ trong base không thay bảng cuối.
- `response_map.json` nối đủ 87 yêu cầu với câu trả lời, evidence hash và current source anchor. Locator PDF cuối vẫn null, mọi comment vẫn chưa được chứng nhận đóng. Bản response cũ khóa riêng tại `previous_response.zip`; không dùng page/closure cũ thay phiên bản mới.
- Bản Word nhận xét riêng và `source_comments.json` không được đưa vào gói. Gói vẫn chứa phản hồi và tài liệu nội bộ; không coi đây là bản đã anonymous hoặc có quyền phân phối.
- Weights sentiment 390 MB **không nằm trong gói**. Sidecar T22 `model_weights.zip` giữ tại máy tác giả, có hash trong manifest T22. Replay từ predictions không cần weights; chạy lại scorer/model forward không thuộc task. Không ghi đã tái kiểm sidecar weights trong lần đóng gói này.

Đây là archive nhiều lớp: root hiện tại có các công cụ và phân tích mới, còn raw input/replay base ở ZIP T22 riêng. Không nhận đây là một checkout phẳng có thể chạy mọi audit cũ mà không xét source version và đường dữ liệu. Index xác định chính xác bytes được phân phối nội bộ; không suy những file ngoài index đã nằm trong gói.

## Kiểm gói có sẵn

PowerShell tại root repository, Python 3.13.5:

```powershell
# Đối soát current sources, lịch sử đã chỉ định, response map và từng byte archive.
py -3.13 -X utf8 scripts/package_revision_response.py check

# Chỉ cần release đã copy và công cụ/core stdlib; không đòi dữ liệu workspace gốc.
# Chế độ này không chứng nhận current sources bên ngoài archive.
py -3.13 -X utf8 scripts/package_revision_response.py check --archive-only

Get-FileHash -Algorithm SHA256 outputs/revision/reviewer_response_v1/private_bundle.zip
```

Checker từ chối thay đổi sources/outputs/index, member thiếu/thừa/trùng, traversal/Windows aliases, symlink, hash sai và mẫu credentials. Scan patterns không đảm bảo nhận ra mọi loại secret hoặc thay việc xét quyền. `check` không chạy lại tám unit tests, clean replay, inference, bootstrap hoặc fit.

Sau T34, checker T32/T33 hoặc `verify_parents` cũ có thể từ chối current response/source vì chúng khóa phiên bản cũ. Không sửa receipt để làm chúng PASS. Checker mới lưu tham chiếu lịch sử cụ thể đến đúng ZIP/member/hash; mọi nguồn khác vẫn kiểm byte hiện tại. Nếu sửa bài ở T35, cần snapshot/QA phiên bản mới, không coi hash receipt T34 là chứng nhận layout mới.

## Copy và giải nén nội bộ

Copy **toàn bộ thư mục release**, gồm `private_bundle.zip` đang ignore, sang đích mới được phép. Kiểm hash/index trước khi giải nén; không giải nén đè nguồn nghiên cứu. Ví dụ tại root, đích `tmp/t34_private_extract_v1` phải chưa tồn tại:

```powershell
py -3.13 -X utf8 scripts/package_revision_response.py check --archive-only
if ($LASTEXITCODE -ne 0) { throw 'Archive không khớp' }
$archiveDestination = Join-Path (Get-Location) 'tmp/t34_private_extract_v1'
if (Test-Path -LiteralPath $archiveDestination) { throw 'Cần đích mới' }
Expand-Archive -LiteralPath outputs/revision/reviewer_response_v1/private_bundle.zip -DestinationPath $archiveDestination
```

Trong cây đã giải nén có thể kiểm base T22 mà không suy phiên bản mới đã chạy lại replay:

```powershell
Set-Location -LiteralPath $archiveDestination
py -3.13 -X utf8 scripts/package_revision_reproducibility.py check --package outputs/revision/reproducibility_v1
```

Nếu tác giả muốn **chạy lại** clean replay (không cần API), tại cây đã giải nén dùng output mới và runtime image T23. Đây là lệnh tùy chọn, **không được chạy thay trong T34**:

```powershell
py -3.13 -X utf8 scripts/run_revision_clean_replay.py build --package outputs/revision/reproducibility_v1 --runtime-release outputs/revision/clean_replay_v1 --output outputs/revision/clean_replay_author_v2
```

`--output` phải chưa tồn tại. Đầu ra là metrics/QA/isolation/manifest mới, không có hosted jobs; không gọi đây là inference/model validation hoặc kiểm thử semantic news/chart. Runtime/interpreter phải đáp ứng pins; không tự tải wheels/model khi thiếu.

## Rebuild từ allowlist đã khóa

Không ghi đè release đã có. Để tái tạo bytes bundle bằng cùng nguồn vào một thư mục mới tại root (ví dụ chưa tồn tại `outputs/revision/reviewer_response_rebuild_v1`):

```powershell
$archiveRebuild = 'outputs/revision/reviewer_response_rebuild_v1'
if (Test-Path -LiteralPath $archiveRebuild) { throw 'Cần release mới' }
New-Item -ItemType Directory -Path $archiveRebuild | Out-Null
Copy-Item -LiteralPath outputs/revision/reviewer_response_v1/package_spec.json -Destination (Join-Path $archiveRebuild 'package_spec.json')
py -3.13 -X utf8 scripts/package_revision_response.py build --release $archiveRebuild
if ($LASTEXITCODE -ne 0) { throw 'Build không khớp allowlist' }
$originalArchiveHash = (Get-FileHash -Algorithm SHA256 outputs/revision/reviewer_response_v1/private_bundle.zip).Hash
$rebuiltArchiveHash = (Get-FileHash -Algorithm SHA256 (Join-Path $archiveRebuild 'private_bundle.zip')).Hash
if ($originalArchiveHash -ne $rebuiltArchiveHash) { throw 'Bundle tái tạo khác bytes' }
```

Build chỉ tạo bundle/index từ allowlist; không tự tạo scientific results, manifest nghiệm thu hoặc PID. Nguồn thay đổi sẽ bị chặn, không dùng rebuild để hợp thức hóa phiên bản khác. Bộ nguồn/release được đánh dấu đúng bên trong gói; không sửa base/ZIP cũ.

## Điều kiện trước public archive

Tác giả còn phải quyết định quyền chia sẻ theo từng nhóm trong `rights.json`; khi cần loại/che dữ liệu, tạo **gói public phiên bản khác** với mapping/hash từ bản nguyên gốc và nêu rõ giới hạn replay. Không che nội dung rồi vẫn nhận là exact private package. Cần xét riêng author additions, OHLCV, news, model assets, raw hosted outputs và nội dung phản hồi/editorial.

Chỉ sau khi quyền và route được xác nhận, tác giả tự publish bằng tài khoản được phép, lấy PID thật và ghi phiên bản/hash chính xác. Chưa có thông tin archive account/record hay quyền nên không tạo record/upload command suy đoán, không tạo DOI placeholder. Sau publish cần cập nhật availability/response bằng PID thật và QA phiên bản mới. Còn phải build/render hai PDF để chốt page/line locators; không nộp bài hoặc đóng R9/R18 chỉ vì archive nội bộ đã kiểm bytes.
