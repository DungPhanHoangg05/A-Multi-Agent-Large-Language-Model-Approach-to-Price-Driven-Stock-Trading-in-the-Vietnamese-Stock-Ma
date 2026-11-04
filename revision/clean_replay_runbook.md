# Replay metrics trong môi trường sạch

T23 dùng `bundle.zip` T22, venv mới `include-system-site-packages=false`, Python
3.13.5 `-I`, chỉ có NumPy 2.1.2 được copy từ runtime image đã khóa SHA-256.
Lần đầu image lấy từ distribution local và đối soát RECORD; không nhận wheel
stub rỗng là original wheel. Các lần sau dùng image đã archive. Không pip,
network, credential, author cache, hosted model hoặc sentiment weights.

Worker chỉ import stdlib/NumPy, có audit hook chặn đọc ngoài package/runtime,
ghi ngoài output, socket/DNS và subprocess. Hai deliberate local probes xác nhận
guard chặn được; không gửi request ra mạng. Môi trường con chỉ nhận các biến
Windows cần thiết và home/cache/temp trống; không kế thừa keys/proxy/PYTHONPATH.

Replay parse lại 375 raw Decision outputs và kiểm parent/prompt/checkpoint,
tính targets từ CSV giá, tái lập main/cohorts/gross metrics, fractional ledgers,
continuous hold riêng, repeats/factorial/disagreement, 10.000 bootstrap draws,
CI và descriptive interaction envelope. Tensors/weights được dựng lại bằng seed
đã khóa, so với NPZ; không dùng expected CI/outcomes làm đầu vào phép tính.
Numeric controls dùng saved predictions của mọi seed, không refit; T19 risk dùng
frozen wealth ledger, không chạy lại fill/settlement engine. Outputs T22 và mọi
historical artifacts giữ nguyên byte.

PowerShell tại root:

```powershell
# Hash-only, không tính lại
py -3.13 -X utf8 scripts/run_revision_clean_replay.py check

# Replay mới, chỉ dùng package và runtime image đã đóng; cần output CHƯA tồn tại
py -3.13 -X utf8 scripts/run_revision_clean_replay.py build --output outputs/revision/clean_replay_recheck_v1 --runtime-release outputs/revision/clean_replay_v1

# Chỉ khi chưa có runtime image: clone distribution NumPy local đúng pin/RECORD
py -3.13 -X utf8 scripts/run_revision_clean_replay.py build --output outputs/revision/clean_replay_new_v1
```

Không dùng system-site-packages hoặc cài fallback khi thiếu runtime image/pin.
Mỗi lần tạo thư mục tạm và venv mới; chỉ xuất release khi mọi so sánh PASS,
từ chối overwrite. Build không resume inference; metrics fail phải sửa nguyên
nhân và chạy lại output mới, không sửa expected values hoặc hash guards.

Đây là reproducibility từ artifacts đã lưu, không thực nghiệm LLM mới. Runtime
clone có provenance/hash riêng, còn interpreter/stdlib Python đã cài được dùng
chung; không chứng minh cài đặt độc lập từ original wheels, portability khác
OS/CUDA hoặc deterministic hosted-model inference. Model ID cấu hình/SDK/response
và fingerprint chỉ là metadata; immutable served revision vẫn unknown.

Không refit train/validation selection, rescore sentiment hoặc tái chứng nhận
native causal/PIT/domain validity. Quyền phân phối và PID vẫn chờ T34, R9 còn
cost/integrity T27 và response/locators cuối; không sửa nguồn bài trước T30.
