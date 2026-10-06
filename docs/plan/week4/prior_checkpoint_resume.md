# W4-12 — Checkpoint và resume từng nhánh

**Ngày:** 06/10/2026. **Nhánh:** `feat/prior-branch-checkpoint-resume`,
baseline `8e947d1`. [Receipt](paired_checkpoint_review.json),
[contract đóng băng](checkpoint_contract.md), [Phase C](phase_c_pit_paired_checkpoint.md).

## Phạm vi triển khai

- `core/prior_checkpoint.py`: reader strict, manifest, planned points, stage/
  attempt, ghi từng nhánh, semantic verifier và results dẫn xuất.
- `core/prior_run_lock.py`: OS handle lock, owner UUID/host/boot/PID/creation
  time, recovery audit và giới hạn path trong run-dir.
- `core/backtest_engine.py`, `core/prior_backtest.py`: nối checkpoint vào vòng
  năm Decision; giữ P&L và ma trận Original/Random/Recent/Similarity/Bayesian.
- `core/prior_context.py`: phục hồi shared Full từ nguồn PIT và seal lại tín
  hiệu/provenance trước dùng. Không cấp evaluation cho agent.
- `utils/graph_setup.py`, `agents/decision_agent.py`: callback nhận bản sao
  state và prompt sau guard `<6500`, trước lần transport đầu. Graph vẫn sở hữu
  retrieval/formatter. Log retry Decision dùng thông báo cố định tránh in key/request.

## Thứ tự ghi và nguồn phục hồi

| Ranh giới | Ghi durable trước bước tiếp |
| --- | --- |
| Khởi tạo | Manifest `initialized=false`, identity và mọi point planned; kiểm toàn plan rồi `initialized=true` trước API đầu |
| Trước upstream | Stage `upstream_started` |
| Sau upstream | Ba báo cáo và `upstream_complete` |
| Trước Full preparation | Stage `full_started` |
| Sau Full | Bundle reports/signals/Alpha/sentiment/proof, shared hash và `shared_complete` |
| Trước Decision từng nhánh | Config/tasks/stats/full metadata/BRPP/query/prompt/hash, UUID attempt `running` |
| Sau Decision valid | Raw response và normalized response, latency, attempt `complete`; ghi ngay nhánh trước nhánh tiếp |
| Sau đủ năm nhánh | Evaluation từ engine, seal point complete; summary/results common support |

Writer dùng temp tên riêng cùng thư mục, flush/fsync và replace atomic của
`core.bayesian_memory.atomic_write_json`. RAM chỉ tiến sau khi replace thành công;
lỗi I/O dừng API. Revision tăng theo commit. Point complete và nhánh complete
được giữ nguyên khi resume.

Các artifact nằm dưới `output_dir`:

```text
run_manifest.json   # Envelope identity/plan/initialized
identity.json       # Artifact identity tương thích API
points/<SYMBOL>-<YYYY-MM-DD>.json
results.json        # Dẫn xuất từ các point complete đã kiểm
run.lock            # OS lock, giữ bằng handle suốt run
run.owner.json      # Owner/released, không chứa credentials
run.recovery.json   # Audit khi nhận lại quyền sở hữu
```

## Cách dùng API

Các tham số W4-11 giữ nguyên; bổ sung `resume: bool = False`:

```python
result = engine.run_prior_backtest(
    symbol,
    adapter=adapter,
    graph_builder=builder,
    output_dir=output_dir,
    cutoffs=cutoffs,
    step=3,
    execution_mode="research",
    resume=True,
)
```

Lần đầu dùng run-dir mới/rỗng và `resume=False`. Khi tiến trình dừng, khởi tạo
engine/client mới với cùng adapter/config/model/nguồn/plan và dùng cùng run-dir,
`resume=True`. Đổi API key ở cấu hình client được phép: identity không chứa key
hoặc hash key. CLI điều phối nghiên cứu thuộc W5.

Resume xác minh toàn manifest/point trước bất kỳ API nào. Reader từ chối JSON
trùng key, NaN/Infinity, thiếu field, schema/checksum sai và file điểm thừa/mất
sau initialized. Input đã lưu được replay offline qua retriever, formatter và
prompt builder thật; so đúng tasks/IDs/order/scores/population/stats/BRPP/query/
prompt với nguồn hiện tại. Envelope tự băm lại không đủ để vượt kiểm chứng.
Raw action phải phù hợp response chuẩn hóa; evaluation phải đúng engine.

Identity khóa phiên bản/config/plan/bank/giá/tin/model/template/code/schema.
Thay đổi những thành phần này bị chặn trước API. Output legacy hoặc W4-11 chỉ
có identity/điểm complete mà thiếu manifest không được tự nhập vào run mới;
reader legacy hiện có vẫn được bảo toàn. Receipt/spec/kho lịch sử không bị sửa.

## Quy tắc xử lý gián đoạn

- `upstream_complete`: dùng ba báo cáo durable, tiếp tục Full một lần.
- `shared_complete`: phục hồi bundle và chỉ Decision của nhánh còn thiếu.
- Attempt `running` không có response durable: lưu attempt cũ `unknown`,
  UUID mới với cùng input; attempt failed được giữ trong lịch sử.
- Sau nhánh cuối nhưng chưa seal: evaluate/seal/rebuild offline, không gọi LLM.
- `results.json` mất/hỏng: dựng lại từ point đã xác minh; manifest/point hỏng
  phải dừng để rà soát.
- `upstream_started` hoặc `full_started` chưa có output durable: dừng
  `AMBIGUOUS_UPSTREAM`/`AMBIGUOUS_FULL`, không tự gọi lại vision/Full.
- Quota/format/interrupt không trở thành SHORT thành công. Lỗi persist chỉ
  chứa code/thông báo Việt cố định/retry hint, không lưu raw exception hoặc key.

Nếu remote đã trả nhưng ghi response lên đĩa thất bại, lần resume có thể gọi
lại **Decision còn thiếu**. Không cam kết exactly-once cho API từ xa; nhánh
complete trên đĩa được bỏ qua. Wrapper retry/backoff/pacing hiện có vẫn áp dụng.

## Khóa và file tạm

Windows khóa byte 0 bằng `msvcrt`; handle giữ đến finally. File `run.lock` còn
tồn tại sau run không tự gây lỗi khóa. Owner `released` được nhận lại kể cả PID
cũ còn sống; owner chết/PID tái sử dụng được phục hồi có audit. Owner active
còn sống nhưng mất handle, khác host, metadata sai hoặc không xác minh được
liveness phải dừng. Không xóa lock, không kill tiến trình sở hữu.

Release kiểm UUID trước ghi owner; đóng handle kể cả khi ghi metadata lỗi.
Path absolute/parent/symlink vượt run-dir bị chặn. Sau preflight dưới OS lock,
chỉ dọn temp của writer theo tên artifact đã biết và hậu tố ngẫu nhiên tám ký
tự trong run-dir. File tạm không thuộc writer và nguồn/archive giữ nguyên.

## Kiểm chứng và giới hạn

- **22 test mới**: 17 checkpoint/lock và 5 leakage; fault injection tại **15
  ranh giới** durable, quota, KeyboardInterrupt và atomic replace failure.
- Run ngắt/resume bằng LLM xác định tương đương run liền về reports, selected
  IDs/stats/prefix, Decision và kinh tế; UUID/timestamp/latency có thể khác.
- Ca quota sau hai nhánh: upstream/Full mỗi loại một lần; 5 Decision valid và
  1 lời gọi lỗi, không gọi lại hai nhánh complete. Ca mất ghi response có 6
  Decision valid do một response chưa durable phải gọi lại.
- Mutation checkpoint băm lại nhưng sai cutoff/outcome/prior exit/metadata/
  scores/stats/prefix/prompt/config/query/raw action/attempt/evaluation bị chặn
  trước API; state phục hồi không chứa evaluation/errors/attempts/outcome query.
- Khóa hai tiến trình và owner chết được kiểm **native Windows**. Backend
  POSIX dùng `flock` theo descriptor được kiểm bằng mock chọn backend; chưa
  tuyên bố nghiệm thu filesystem chia sẻ hoặc native Linux.
- Bốn gate mới: compileall, **483 unit**, E2E xác định, **82 leakage** PASS;
  log/hash và kiểm byte nguồn/bằng chứng ghi tại [receipt](paired_checkpoint_review.json).
  **2.408 file bảo vệ** và bảy AST hàm kinh tế/legacy giữ nguyên so baseline.

**Phase C 4/4, W4 12/16, Gate C PASS offline.** W4-13..16/Gate D và gate giá
OOS tiếp tục mở. Chưa gọi API LLM thật, chạy pilot hoặc backtest đầu tư ngoài mẫu.
