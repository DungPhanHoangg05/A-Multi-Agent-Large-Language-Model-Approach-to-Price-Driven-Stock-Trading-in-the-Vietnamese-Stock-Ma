# Tuần 5 — Hoàn thiện vận hành và khóa kế hoạch benchmark bốn mã

**Trạng thái: đã lập kế hoạch; 0/16 task triển khai hoàn thành.**
Ngày lập: **07/10/2026**. Chưa triển khai code hoặc chạy API của W5.
[Kế hoạch tổng](../plan.md) · [Kết quả W4](../week4/README.md) ·
[Hợp đồng API/checkpoint hiện hành](../week4/week_close_and_handoff.md)

## 1. Mục tiêu và đầu vào

Pilot FPT và quota đã được nghiệm thu khi chốt W4. W5 dùng kết quả đó để
hoàn thiện đường chạy chính thức, xử lý các điểm yếu vận hành đã quan sát,
và khóa mẫu/lịch/ngân sách cho benchmark W6 trên **FPT, VNM, VCB, MWG**.

| Đầu vào đã hoàn thành ở W4 | Ý nghĩa đối với W5 |
| --- | --- |
| 20 điểm FPT, 100/100 Decision structured, verifier offline PASS | Giữ pilot làm bằng chứng vận hành; mẫu chỉ phủ 05/01–03/04/2023 |
| Compileall/E2E, 521 unit và 93 leakage PASS | Mốc hồi quy, không tự coi bản code W5 đã được kiểm thử |
| Giá thô OOS VCI/KBS bốn mã; model proof train-only hồi cứu | Tính lịch OOS đủ điều kiện trên nguồn đã khóa; giữ giới hạn của proof |
| Memory Bank 852 episode, quyết định 2020–2022 | Giữ bank/model/train nguyên vẹn; không bổ sung nhãn OOS vào prior |
| Retrieval p95 bốn mode 10,837–13,235 ms, dưới 30 ms | Giữ bằng chứng đã đo; chỉ đo lại khi thay đường retrieval hoặc môi trường |
| 146 HTTP 200, một transport_error chưa rõ kết quả, 0 HTTP 429 | Đối soát request/usage/reserve, giữ ngoại lệ upstream điểm 16 |
| Text 194.218 token; vision 102.034 gồm reserve unknown | Tính khả thi theo từng model; không suy ra benchmark lớn chắc chắn đủ quota |
| BRPP tối đa 369; prompt tối đa 4.483 ký tự | Cap hiện tại đủ cho pilot; tiếp tục kiểm cứng ở mọi điểm mới |

Giới hạn chủ tài khoản đã cung cấp cho **cả `openai/gpt-oss-20b` và
`qwen/qwen3.8-27b`**: **30 RPM / 1.000 RPD / 8.000 TPM / 200.000 TPD**.
ITPM/OTPM riêng chưa được cung cấp. Các con số này là đầu vào lập kế hoạch;
trước lượt chạy mới phải đối chiếu giới hạn tài khoản/model còn hiệu lực.
Đổi key trong cùng tổ chức không tạo ngân sách mới.

### Phạm vi đóng băng

- Mốc bàn giao code W4: commit `27b5907`; kết quả tại
  `outputs/pilot_fpt_run/`, input/ledger/audit tại `outputs/oos_pilot/`.
- Giữ nguyên bank `data_manager/regime_memory_store.json`, model
  `data_manager/regime_model.json`, train archive, VNINDEX và ZIP bằng chứng.
- Mọi thay đổi code/schema/config làm đổi identity phải dùng **run mới**.
  Lưu cách kiểm pilot bằng phiên bản W4 đã ghim; không sửa fingerprint để
  ép checkpoint cũ chạy với code W5.
- W5 chuẩn bị benchmark; W6 chạy ma trận chính thức; W7 làm kiểm định thống kê
  và sensitivity K. K=5 cần hợp đồng/phiên bản riêng vì hiện chỉ hỗ trợ K=0..3.

## 2. Quy tắc xuyên suốt

1. Giá chỉ từ **vnstock/VCI và vnstock/KBS**. LONG mua Open(t+1), bán
   Close(t+3); SHORT giữ tiền mặt; phí 0,25% và slippage 0,10% mỗi chiều.
   Nhãn/P&L dùng `compute_round_trip_net_return`.
2. Giá/tin ≤`as_of_date`; bỏ tin không có ngày. Prior phải có
   **`exit_date < as_of_date`**, lọc trước ranking/stats. HMM/scaler/calibration
   chỉ dùng train 2018–2022; proof hiện tại vẫn là hồi cứu.
3. Năm nhánh: Original K=0, Random/Recent/Similarity/Bayesian K=3,
   seed=42, same_symbol. Một bộ upstream/Full thành công dùng chung bằng
   deep-copy; không gọi lại vision theo nhánh.
4. Giữ `_distill_report`, `_cap_report`, BRPP ≤600 và prompt <6.500 ký tự;
   mọi API qua `_invoke_with_retry` và guard HTTP chung cho mọi đường gọi.
5. Upstream/Full đã gửi nhưng chưa biết kết quả: dừng để đối soát. Ngoại lệ
   replay điểm 16 ở W4 không cấp quyền tự động replay các lỗi tương lai.
6. Thiếu tin lịch sử giữ NEUTRAL kèm coverage/lý do; không lấy tin hiện tại
   bù quá khứ. Không coi pilot là bằng chứng Bayesian tăng lợi nhuận.

## 3. Checklist và thứ tự thực hiện

Task được thiết kế cho một lượt làm có đầu ra kiểm được; chuyển phase khi
gate tương ứng PASS. Ước lượng W5 khoảng **30–40 giờ làm việc chủ động**,
không gồm thời gian nghỉ quota. Điều chỉnh lịch theo gate thực tế.

| Phase | Task | Công việc | Phụ thuộc | Trạng thái |
| --- | --- | --- | --- | --- |
| A | W5-01 | Đối chiếu bàn giao và khóa bằng chứng pilot | W4 đã đóng | [ ] |
| A | W5-02 | Tổng hợp chất lượng và chỉ số pilot offline | 01 | [ ] |
| A | W5-03 | Chuẩn hóa báo cáo HTTP/token/thời gian | 01 | [ ] |
| A | W5-04 | Chốt hợp đồng vận hành và đánh giá W6 | 02, 03 | [ ] |
| B | W5-05 | Hoàn thiện chính sách dự phòng quota trước điểm | 04 | [ ] |
| B | W5-06 | Xử lý ghi checkpoint trên Windows/OneDrive | 04 | [ ] |
| B | W5-07 | Hoàn thiện phục hồi và đối soát upstream | 04, 06 | [ ] |
| B | W5-08 | Mở CLI cho plan bốn mã và run độc lập | 05, 06, 07 | [ ] |
| C | W5-09 | Kiểm coverage và lịch đủ điều kiện OOS | 04 | [ ] |
| C | W5-10 | Thiết kế lịch mẫu và tách pilot/smoke | 09 | [ ] |
| C | W5-11 | Tính ngân sách và lịch chạy khả thi | 03, 05, 10 | [ ] |
| C | W5-12 | Khóa input/plan và dry-run bốn mã | 08, 10, 11 | [ ] |
| D | W5-13 | Kiểm lỗi có chủ đích và paired/resume | 08, 12 | [ ] |
| D | W5-14 | Smoke vận hành thật giới hạn bốn mã | Gate A/B/C, 13 | [ ] |
| D | W5-15 | Nghiệm thu hồi quy và điều kiện mở W6 | 13, 14 | [ ] |
| D | W5-16 | Chốt W5, bàn giao lệnh và lịch W6 | 15 | [ ] |

### Phase A — Đọc đúng pilot và chốt yêu cầu (khoảng 1 ngày)

#### W5-01 — Đối chiếu bàn giao và khóa bằng chứng pilot

- **Làm:** kiểm nguồn/hash/config/identity, 20 checkpoint, 100 Decision và
  audit điểm 16 bằng verifier offline đúng phiên bản W4. Ghi vị trí dữ liệu
  và cách khôi phục môi trường W4 để kiểm lại sau khi code W5 thay đổi.
- **Đầu ra:** mục baseline được xác nhận tại README này; không sao chép cả
  output thành bộ receipt mới. Dữ liệu local thiếu thì ghi BLOCKED rõ lý do.
- **Đạt khi:** 20/20 common support; 15 point/75 Decision trước replay còn
  nguyên byte; unknown reserve và audit còn đầy đủ; không gọi API.

#### W5-02 — Tổng hợp chất lượng và chỉ số pilot offline

- **Làm:** dùng summary/verifier hiện có đối chiếu accuracy, LONG/SHORT,
  số giao dịch, P&L sau phí và drawdown của năm nhánh trên đúng cùng 20 điểm.
  Kiểm nguồn `llm_structured`, thiếu dữ liệu và coverage sentiment.
- **Đầu ra:** bảng mô tả pilot trong README; chỉ bổ sung công cụ export gọn
  nếu API summary hiện tại chưa đủ, không tạo lại nhãn/metric theo công thức khác.
- **Đạt khi:** bảng tái lập được từ checkpoint, có mẫu số và giới hạn
  đầu 2023/NEUTRAL/ngoại lệ replay; không chọn nhánh tốt nhất để đổi giao thức W6.

#### W5-03 — Chuẩn hóa báo cáo HTTP/token/thời gian

- **Làm:** tách graph invocation, HTTP attempt, HTTP thành công, format retry,
  transport unknown, preflight và replay. Tách input/output/actual/reserve
  từng model; thời gian HTTP, pacing, toàn điểm và retrieval trình bày riêng.
- **Đầu ra:** chức năng tổng hợp ledger có thể dùng lại cho W6; bảng gọn
  tại README, không dump prompt/ảnh/key hoặc tạo receipt cho từng request.
- **Đạt khi:** đối soát được 146 HTTP 200 + một unknown; text 194.218 và
  vision 102.034 charged; không biến unknown thành zero usage hoặc HTTP thành công.

#### W5-04 — Chốt hợp đồng vận hành và đánh giá W6

- **Làm:** chốt retry/dừng/resume, quy tắc identity, schema báo cáo,
  metric chính/phụ và cách tổng hợp theo mã. Tách phân tích mô tả pilot
  khỏi đánh giá chính thức; định nghĩa common support và xử lý điểm dở.
  Giữ tài khoản 50 triệu đồng cho từng mã; nếu báo cáo portfolio chung
  phải có quy tắc phân bổ riêng, không cộng equity để giả thành cùng một tài khoản.
- **Đầu ra:** cập nhật hướng dẫn vận hành hiện có khi cần; ghi quyết định
  tại README này. Giữ sensitivity K và kiểm định ý nghĩa thống kê ở W7.
- **Đạt khi:** lỗi không bị loại để làm đẹp accuracy; không đổi model/K/
  cost/scope giữa run; không gọi confidence chưa calibration là posterior.

**Gate A:** baseline kiểm được, bảng pilot/telemetry đối soát được và hợp
đồng W6 rõ ràng. Không yêu cầu pilot có lợi nhuận tốt hơn để PASS.

### Phase B — Hoàn thiện đường chạy dài (khoảng 2 ngày)

#### W5-05 — Hoàn thiện chính sách dự phòng quota trước điểm

- **Làm:** rà `core/groq_pacing.py` và CLI: guard trước điểm đang dự phòng
  sáu request text ×8.000 =48.000 token, có thể dừng sớm hơn nhu cầu thật.
  Chọn chính sách dự phòng minh bạch, cấu hình/version hóa cho run mới;
  giữ kiểm input + output cap tại từng HTTP request và reserve unknown.
- **Đầu ra:** policy và thông báo remaining/budget/resume rõ ràng; kiểm cache
  tokenizer trước run; ledger/OS lock dùng chung giữa các run cùng quota.
- **Đạt khi:** policy không cần workaround gọi runner ngoài CLI; giả lập
  biên RPM/TPM/RPD/TPD, quota đổi và cooldown đều an toàn. Không hứa tránh mọi 429.

#### W5-06 — Xử lý ghi checkpoint trên Windows/OneDrive

- **Làm:** tái hiện sharing violation/WinError 5; bổ sung retry ghi atomic
  có giới hạn cho đúng lỗi có thể phục hồi. Tránh reader giữ handle cản
  `os.replace`; hướng dẫn thư mục runtime local ngoài vùng đồng bộ nếu cần.
- **Đầu ra:** đường ghi/đọc ổn định và lỗi I/O có hướng xử lý; không nuốt
  lỗi quyền/đĩa đầy, không ghi đè checkpoint complete hoặc xóa lock đang sống.
- **Đạt khi:** fault test chứng minh file cũ hoặc file mới nguyên vẹn,
  không JSON nửa chừng; retry hết thì dừng giữ dữ liệu durable.

#### W5-07 — Hoàn thiện phục hồi và đối soát upstream

- **Làm:** phân biệt chưa gửi, đã nhận response durable và kết quả chưa rõ.
  Rà checkpoint từng bước Pattern/Trend/Full; bổ sung lưu response/stage
  tối thiểu nếu cần để dùng lại kết quả đã nhận thay vì gọi lại upstream.
- **Đầu ra:** quy trình/CLI đối soát có kiểm owner, identity, hash và audit;
  response cần phục hồi nằm trong checkpoint được bảo vệ, không trong telemetry.
- **Đạt khi:** dùng lại response đã lưu không tạo HTTP mới; tình trạng
  AMBIGUOUS dừng, chỉ replay sau xác nhận cụ thể. Không cam kết exactly-once API từ xa.

#### W5-08 — Mở CLI cho plan bốn mã và run độc lập

- **Làm:** tổng quát hóa CLI nghiên cứu hiện tại để đọc plan đã khóa,
  chọn mã, output/ledger, dry-run/preflight/run/verify/resume; chạy tuần tự
  có khóa quota chung. Dùng fixture plan trước khi có plan W6 chính thức.
- **Đầu ra:** một đường CLI chính cho bốn mã; tên cờ/lệnh thật được ghi
  sau triển khai, không thêm runner riêng cho từng mã hoặc dùng runner Memory Bank.
- **Đạt khi:** run mới tách pilot W4; complete không gọi lại; sai identity
  bị chặn; dry-run/verify không đọc `.env` hoặc gọi mạng, schema/JSON native hợp lệ.

**Gate B:** CLI tái lập được, quota/atomic I/O/resume có kiểm thử; W4 còn
kiểm được bằng phiên bản đã ghim. Prior mặc định vẫn tắt trong luồng thông thường.

### Phase C — Chốt mẫu và nguồn lực W6 (khoảng 1 ngày)

#### W5-09 — Kiểm coverage và lịch đủ điều kiện OOS

- **Làm:** tính riêng cutoff 2023–2024 cho từng mã trên archive giá thô
  OOS/VNINDEX: warm-up 600 phiên, t+1/t+3, corporate actions, lịch và tin PIT.
  Thống kê ứng viên/hợp lệ/loại theo nguyên nhân, năm/quý và regime PIT.
- **Đầu ra:** bảng coverage bốn mã và tập ngày đủ điều kiện dùng để lập plan;
  tái dùng audit hiện có, không tải lại/ghi đè nguồn đã khóa chỉ để tạo báo cáo.
- **Đạt khi:** không dùng 1.510 chu kỳ hợp lệ của cả archive 2018–2024
  làm cỡ mẫu OOS; mọi ngày chọn đều được adapter xác minh và có exit hợp lệ.

#### W5-10 — Thiết kế lịch mẫu và tách pilot/smoke

- **Làm:** đề xuất lịch cố định bao phủ bốn mã và cả 2023/2024; chọn theo
  lịch/eligibility trước API, cách ≥3 phiên theo hợp đồng. Chốt mục tiêu
  số điểm từng mã/quý, nguyên tắc loại và coverage chứ không chọn theo lợi nhuận.
- **Đầu ra:** lịch dự kiến benchmark và **bốn điểm smoke riêng, một điểm/mã**.
  Tách 20 ngày FPT pilot đã quan sát và các điểm smoke khỏi mẫu đánh giá chính;
  nếu báo cáo chúng thì ghi là tập kiểm thử vận hành/phân tích thăm dò.
- **Đạt khi:** không xem outcome/dự báo để chọn mẫu; không thay ngày lỗi
  bằng ngày dễ hơn. Mẫu rút gọn theo lịch là thay đổi phạm vi cần ghi rõ, không gọi toàn bộ OOS.

#### W5-11 — Tính ngân sách và lịch chạy khả thi

- **Làm:** với N điểm, dự kiến tối thiểu 5N Decision +2N vision =7N HTTP
  trong cấu hình pilot, cộng preflight/retry/format/replay/dự phòng. Tính
  token và giới hạn từng model theo telemetry; phân biệt chi phí kỳ vọng
  với reserve an toàn. Ledger local hiện dùng cửa sổ 61 giây và 24 giờ.
- **Đầu ra:** bảng cỡ mẫu → quota/ngày → số ngày/thời gian chạy; có
  ngân sách còn lại sau tác vụ khác cùng tổ chức và lịch nghỉ/resume.
- **Đạt khi:** phương án chọn đáp ứng quota và thời hạn W6. Nếu không đủ,
  báo BLOCKED kèm lựa chọn nâng quota/gia hạn/rút gọn mẫu trước khi khóa;
  không đổi key/model/K giữa run hoặc tự ghi PASS khả thi.

Để thấy quy mô: 194.218 token text/20 điểm pilot ≈9.711 token/điểm, gồm
chi phí kiểm model của lượt đó. Với 200.000 TPD, khoảng 20 điểm/ngày chỉ
là ước lượng trước dự phòng/tác vụ khác, không là cam kết năng lực.
W5-11 phải tính lại từ ledger và policy thật; chưa ấn định số điểm W6 ở bước lập kế hoạch.

#### W5-12 — Khóa input/plan và dry-run bốn mã

- **Làm:** sau khi phương án 10–11 được chốt, khóa ngày theo thứ tự,
  sources/checksums, snapshot tin, model/proof, bank, config, seed, scope,
  năm nhánh, code/schema/dependency và policy quota; tách smoke/benchmark.
- **Đầu ra:** manifest/plan máy đọc phục vụ CLI trong output runtime mới,
  dự kiến `outputs/bayesian_benchmark/`; sơ đồ bố trí thật ghi lại tại README.
  Chỉ giữ JSON cần cho execute/verify, không thêm bản sao receipt.
- **Đạt khi:** dry-run toàn bộ ngày chọn PASS nguồn/PIT/economic/identity
  và BRPP/cap cấu hình, không API. Prompt đầy đủ chỉ kiểm được khi có báo
  cáo thực và phải qua guard trước HTTP; không ghi PASS prompt chưa sinh.
  Plan không được thay sau khi đã thấy Decision của cohort đó.

**Gate C:** đủ coverage bốn mã/hai năm theo phương án đã chọn; mẫu, nguồn,
model, ngân sách và lịch được khóa trước run. Quota không đủ thì giữ gate BLOCKED.

### Phase D — Kiểm chứng đường vận hành và bàn giao (khoảng 1 ngày)

#### W5-13 — Kiểm lỗi có chủ đích và paired/resume

- **Làm:** kiểm bốn mã bằng mock cấm mạng: quota sát trần, 429/cooldown,
  response chưa rõ, crash sau response/atomic write, lock active/stale,
  đổi nguồn/identity, partial branch và malformed Decision.
- **Đầu ra:** test cho rủi ro thật của 05–08; bổ sung leakage equality
  `exit_date == as_of_date`, news tương lai/không ngày và model sai freeze.
- **Đạt khi:** không gọi lại phần durable, năm nhánh cùng shared hash,
  lỗi dừng đúng stage, không bỏ điểm khỏi plan; toàn bộ mô phỏng offline PASS.

#### W5-14 — Smoke vận hành thật giới hạn bốn mã

- **Làm:** khi người dùng yêu cầu triển khai task và các gate đủ, chạy
  preflight text/vision rồi tối đa **4 điểm ×5 nhánh =20 Decision** trên
  cohort smoke đã khóa ở 10–12. Giữ ledger/pacing/lock chung; dừng có kiểm soát khi hết quota.
- **Đầu ra:** checkpoint smoke riêng và verifier offline; không chạy lại
  pilot 20 FPT hoặc kích hoạt toàn benchmark trong task này.
- **Đạt khi:** 4/4 common support, 20/20 Decision hợp lệ, cap/PIT/economic
  PASS; usage/unknown có đối soát. Nếu chưa hoàn thành, ghi tiến độ/BLOCKED,
  không coi mock hoặc đổi model là thay thế nghiệm thu thật.

#### W5-15 — Nghiệm thu hồi quy và điều kiện mở W6

- **Làm:** chạy bốn gate AGENTS.md trên bản code chốt; rà checklist A/B/C,
  smoke, nguồn/model/hash, lịch/quota, giới hạn nghiên cứu và cách verify W4.
  Chỉ đo lại retrieval p95 nếu thay đường này/môi trường hoặc có hồi quy cụ thể.
- **Đầu ra:** kết quả nghiệm thu gọn tại README, số test thực tế/commit/
  lệnh kiểm; không tái dùng số 521 để gắn PASS cho bản W5 chưa kiểm.
- **Đạt khi:** compileall, toàn unit, E2E, toàn leakage PASS; không gate
  nguồn lực chưa giải quyết. Sẵn sàng vận hành không đồng nghĩa hiệu quả đầu tư đã chứng minh.

#### W5-16 — Chốt W5, bàn giao lệnh và lịch W6

- **Làm:** cập nhật checklist, kế hoạch tổng và hướng dẫn lệnh thật cho
  prepare/dry-run/preflight/run/verify/resume từng mã; ghi lịch quota,
  nơi lưu dữ liệu, xử lý dừng/unknown và trách nhiệm đối soát.
- **Đầu ra:** README này là sổ tiến độ chính; bổ sung hướng dẫn độc lập
  chỉ khi cần. Không tạo 16 biên bản task hoặc đẩy toàn bộ output lên GitHub.
- **Đạt khi:** 16/16 task và các gate PASS, manifest mẫu bất biến,
  lệnh có thể chạy lại. Bất kỳ gate nào còn BLOCKED thì chưa chốt W5 hoàn thành.

## 4. Gate kỹ thuật bắt buộc trước merge

```powershell
py -3.13 -m compileall agents core data_manager scripts tests utils
py -3.13 -X utf8 -m unittest discover -s tests -v
py -3.13 scripts/run_end_to_end_test.py
py -3.13 -X utf8 -m unittest discover -s tests -p "test_*leakage.py" -v
```

Mỗi task triển khai theo nhánh độc lập từ `develop`, commit Conventional
Commits theo nội dung kỹ thuật, không ghi ký hiệu tuần trong commit message.
Không merge khi gate bắt buộc FAIL.

## 5. Cập nhật tiến độ và quản lý file

- Kết thúc từng task: đánh dấu ở bảng mục 3, thêm một dòng nhật ký dưới đây
  gồm kết quả, cách kiểm, commit/đường dẫn đầu ra và việc còn vướng.
- Dùng `TODO`, `IN_PROGRESS`, `BLOCKED`, `DONE`; chỉ đánh `[x]` khi tiêu chí
  đạt đủ. Hoàn thành lập kế hoạch không tính là hoàn thành task triển khai.
- README và hướng dẫn dùng chung được Git theo dõi; checkpoint/ledger/news
  snapshot/response phục hồi để trong runtime output được gitignore.
  Giữ schema/fixture/manifest nguồn mà code cần theo quy tắc hiện hành.
- Không tạo JSON chỉ để nhắc lại PASS. Không xóa checkpoint/audit/reserve
  chưa đối soát; dọn file tạm chỉ sau khi xác minh không có owner đang chạy.

| Ngày | Phạm vi | Trạng thái / kết quả | Bước tiếp theo |
| --- | --- | --- | --- |
| 07/10/2026 | Lập kế hoạch W5 | PLAN_READY; 0/16 triển khai; kế thừa pilot W4 đã hoàn thành | Bắt đầu W5-01 |
| 07/10/2026 | Kiểm thay đổi tài liệu | Compileall/E2E, 521 unit/93 leakage PASS; đủ 16 task và liên kết nội bộ hợp lệ; không API | Gate triển khai W5 vẫn chờ thực hiện từng task |
