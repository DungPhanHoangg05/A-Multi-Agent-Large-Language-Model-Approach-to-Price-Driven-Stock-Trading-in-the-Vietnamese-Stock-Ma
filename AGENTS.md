# QUY TẮC & RÀNG BUỘC PHÁT TRIỂN HỆ THỐNG DÀNH CHO CODING AGENT (AGENTS.MD)

Tài liệu này quy định quy trình phát triển và bảo toàn bằng chứng nghiên cứu. Hướng dẫn trực tiếp của người dùng được ưu tiên khi thay đổi phạm vi công việc. Luồng nâng cấp hệ thống đa agent phục vụ Khóa luận Tốt nghiệp (KLTN) có tên:
**"Regime-Aware Multi-Task Bayesian In-Context Learning for Multi-Agent LLM Stock Trading"**.

Mục tiêu cốt lõi: **Nâng cấp tính năng mới mà tuyệt đối KHÔNG làm gãy vỡ, biến dạng hoặc suy giảm tính ổn định của hệ thống hiện tại.**

---

## 1. QUY TRÌNH PHÂN NHÁNH GIT & HỢP NHẤT (GIT WORKFLOW & BRANCHING)

### 1.1. Chọn kế hoạch, nhánh tích hợp và nhánh task
- **Luồng phản biện bản thảo:** đọc [plan.md](plan.md) ở root, dùng nhánh tích hợp `fix`, nơi chứa phiên bản mã và artifacts được kế hoạch khảo sát. Tài liệu tiến độ/bằng chứng đặt trong `revision/`, kết quả mới đặt trong `outputs/revision/<run_id>/`.
- **Luồng KLTN:** dùng `develop` và `docs/plan/plan.md` khi làm việc thuộc kế hoạch đó. Không tự trộn hai luồng hoặc chuyển mã sang nhánh khác chỉ để thỏa quy ước.
- Không commit trực tiếp trên nhánh tích hợp `fix`, `develop` hoặc `main`. Trước khi tạo nhánh, kiểm tra status, giữ nguyên thay đổi có sẵn của người dùng; fetch và chỉ cập nhật nhánh tích hợp bằng fast-forward. Không reset hoặc force-push.
- Mỗi task phải thực hiện trên nhánh độc lập tách từ đúng nhánh tích hợp:
  ```bash
  git checkout <integration-branch>
  git pull --ff-only origin <integration-branch>
  git checkout -b <branch-prefix>/<task-name>
  ```
- **Tiền tố tên nhánh hợp lệ**:
  - `feat/<tên-tính-năng>`: Thêm tính năng mới (ví dụ: `feat/regime-detector-hmm`, `feat/bayesian-retriever`).
  - `fix/<tên-lỗi>`: Sửa lỗi hệ thống (ví dụ: `fix/token-budget-distill`, `fix/leakage-temporal-cutoff`).
  - `test/<tên-kiểm-thử>`: Bổ sung bộ test mới (ví dụ: `test/regime-leakage-suite`).
  - `refactor/<tên-module>`: Tối ưu cấu trúc mã không làm đổi logic (ví dụ: `refactor/decision-prompt-builder`).
  - `docs/<tên-tài-liệu>`: Cập nhật tài liệu kỹ thuật (ví dụ: `docs/methodology-spec`).
- Có thể dùng `perf/` hoặc `chore/` đúng phạm vi. Git không cho đồng thời nhánh `fix` và `fix/...`; khi nhánh tích hợp là `fix`, chọn tiền tố hợp lệ khác, ví dụ `feat/revision-baselines`.
- Chỉ stage file thuộc task; không dùng `git add .` khi có file ngoài phạm vi. Không tự push/publish nếu task không yêu cầu.

### 1.2. Điều kiện tiên quyết để hợp nhất vào nhánh tích hợp
Trước khi hợp nhất, phải chọn kiểm tra theo phạm vi ảnh hưởng của task; **không bắt buộc chạy kiểm thử cho mọi task**:
- **Chỉ sửa tài liệu, checklist hoặc phân tích bằng chứng có sẵn**, không đổi code, test, cấu hình runtime, schema hay dữ liệu đầu vào: không cần chạy compileall, unit test, E2E hoặc leakage suite. Kiểm tra diff, liên kết, số liệu và hash nguồn liên quan; ghi rõ lý do không chạy suite trong README tuần hoặc báo cáo hoàn thành.
- **Thay đổi code hoặc hành vi chạy**: chỉ chạy lại test liên quan trực tiếp đến code thay đổi và các caller/hợp đồng bị ảnh hưởng; chỉ biên dịch các file Python thay đổi. Ghi rõ các module/test được chọn và lý do bao phủ đủ phạm vi. Không chạy toàn bộ unit suite, compileall toàn codebase hoặc E2E toàn hệ thống cho mỗi lần sửa code.
- **Thay đổi liên module, hợp đồng P0** (kinh tế, PIT/leakage, paired protocol, prompt/token, retry/checkpoint) **hoặc dependency/runtime dùng chung**: chọn các test tích hợp/hồi quy của đúng đường chạy bị ảnh hưởng, không tự động mở rộng thành toàn suite. Khi đổi đường dữ liệu/PIT/retrieval, bắt buộc chạy các test leakage liên quan. Chỉ chạy lại sau thay đổi mới hoặc khi còn lỗi/lo ngại chưa được giải quyết trong phạm vi đó.
- **Mốc nghiệm thu/release yêu cầu bốn gate**: nếu code/test/schema/config/runtime được receipt khóa vẫn nguyên vẹn, kiểm lại hash nguồn/runtime/log/receipt và viện dẫn đúng kết quả đã PASS; không chạy lại toàn suite chỉ để cập nhật checklist. Nếu có thay đổi, kiểm thử lại phần bị ảnh hưởng và ghi rõ kết quả mới cùng giới hạn của gate cũ. Chỉ chạy hồi quy toàn hệ thống khi người dùng yêu cầu rõ việc chạy lại toàn bộ.
- Chỉ merge khi mọi kiểm tra áp dụng đều PASS; không dùng kết quả cũ để thay cho kiểm tra hành vi đã đổi. Task thuần tài liệu có thể viện dẫn gate cũ nếu code/runtime giữ nguyên, nhưng không ghi là đã chạy lại.

**Bốn gate tham chiếu cho nghiệm thu toàn hệ thống (không tự động chạy lại; áp dụng quy tắc theo phạm vi ở trên):**
1. **Gate 1 - Biên dịch toàn bộ codebase không lỗi**:
   ```powershell
   py -3.13 -m compileall agents core data_manager scripts tests utils
   ```
2. **Gate 2 - Chạy pass 100% bộ Unit Tests hiện có và mới**:
   ```powershell
   py -3.13 -X utf8 -m unittest discover -s tests -v
   ```
3. **Gate 3 - Chạy pass kiểm thử hồi quy đầu-cuối E2E xác định**:
   ```powershell
   py -3.13 scripts/run_end_to_end_test.py
   ```
4. **Gate 4 - Đảm bảo Zero-Leakage**: Bộ test dò rỉ dữ liệu `tests/test_*leakage.py` không có bất kỳ vi phạm nào.

### 1.3. Merge và dọn nhánh local sau mỗi chức năng
- Sau khi kiểm tra áp dụng đều PASS, commit trên nhánh task rồi chuyển về đúng nhánh tích hợp để merge; ưu tiên `git merge --ff-only <task-branch>` khi phù hợp. Không merge đè thay đổi chưa commit của người dùng.
- **Sau mỗi chức năng/task đã merge thành công, bắt buộc xóa ngay nhánh local của task bằng `git branch -d <task-branch>`.** Kiểm tra `git merge-base --is-ancestor <task-branch> HEAD` trước khi xóa. Nếu upstream của nhánh task khác nhánh tích hợp, bỏ upstream của chính nhánh đã merge trước khi chạy `-d`.
- Không dùng `-D`, không xóa nhánh chưa merge, nhánh của người dùng hay nhánh tích hợp. Không suy yêu cầu xóa local thành xóa remote. Nếu chưa merge được thì giữ nhánh và báo lý do.

---

## 2. QUY CHUẨN COMMIT MESSAGE (CONVENTIONAL COMMITS)

### 2.1. Định dạng Bắt buộc
Mọi thông điệp commit **BẮT BUỘC** phải tuân thủ chuẩn Conventional Commits với cấu trúc:
```text
<type>(<scope>): <mô tả ngắn gọn bằng tiếng Anh hoặc tiếng Việt>

[optional body: mô tả chi tiết lý do và thay đổi kỹ thuật]
```

### 2.2. Các tiền tố (Prefix) Hợp lệ
- `feat:` Thêm một tính năng mới cho hệ thống.
- `fix:` Sửa một lỗi phát sinh trong mã nguồn hoặc kiểm thử.
- `docs:` Chỉ thay đổi tài liệu (Markdown, docstrings).
- `test:` Thêm các ca kiểm thử mới hoặc hiệu chỉnh bài test.
- `refactor:` Tái cấu trúc mã nguồn mà không sửa lỗi hay thêm tính năng.
- `perf:` Cải tiến mã nhằm tăng tốc độ thực thi hoặc giảm tiêu thụ RAM.
- `chore:` Cập nhật cấu hình phụ trợ, file `.gitignore`, dependencies.

### 2.3. RÀNG BUỘC CẤM TUYỆT ĐỐI (Strictly Forbidden in Commit Messages)
- **CẤM TUYỆT ĐỐI đưa ký hiệu tiến độ thời gian vào commit message**: Không được sử dụng các tiền tố hay cụm từ như `W1D1`, `W1D2`, `Week 1`, `W2D3`, `Tuần 1`, `Ngày 2`, v.v.
- Commit message phải phản ánh **nội dung kỹ thuật thực sự** của thay đổi.
- **Ví dụ SAI**:
  - `git commit -m "W1D2: hoàn thành regime detector"` ❌
  - `git commit -m "Week 2: fix bug backtest"` ❌
- **Ví dụ ĐÚNG**:
  - `git commit -m "feat(regime): implement Gaussian HMM detector on VN-Index history"` ✔️
  - `git commit -m "fix(decision): resolve token budget overflow in compact prompt"` ✔️
  - `git commit -m "test(leakage): add strict temporal cutoff test for prior tasks"` ✔️
  - `git commit -m "docs(plan): add 2-month KLTN master implementation plan"` ✔️

---

## 3. BẢO TOÀN BẰNG CHỨNG VÀ HỢP ĐỒNG NGHIÊN CỨU

- Giữ nguyên byte artifacts lịch sử, gắn SHA-256 và ghi nguồn/phiên bản; tạo đầu ra mới riêng biệt. Không sửa prediction, label hoặc cache cũ để khớp diễn giải.
- Thiếu provenance ghi `unknown`/`unverified`; không gán cache hiện có thành snapshot submission hoặc suy model lịch sử từ cấu hình hiện tại. Không tự xác nhận phiên bản submission nếu thiếu hồ sơ.
- R1–R18 chỉ đóng khi có thay đổi, artifact kiểm chứng, vị trí bản thảo và response. Code/unit test không thay cho bằng chứng thực nghiệm LLM. Phân biệt audit legacy, pilot và confirmatory.
- Target net giữ nguyên cho replication; target gross nếu cần phải định nghĩa riêng. `SHORT` là CASH trong ledger long-only. Always-LONG từng cycle khác buy-and-hold.
- Metrics phải có mẫu số, class support, pooled/macro và common support rõ ràng. Undefined ghi `null` trong JSON, `NA` trong bảng; không xuất NaN/Infinity. Không coi accuracy cao hoặc thua ít hơn control là chứng minh alpha/profitability.
- Majority, exposure control, preprocessing, selection và threshold/hyperparameters chỉ fit trên train/validation theo thời gian, purge label overlap; không dùng nhãn test để tạo baseline huấn luyện.
- Tuân thủ dependency và protocol freeze trước confirmatory runs. Không chọn seed/checkpoint/giai đoạn tốt nhất sau khi nhìn outcome; không tự gọi API có phí để thay đầu vào còn thiếu.

## 4. QUY TẮC QUẢN TRỊ TOKEN & TỐC ĐỘ GỌI LLM (TOKEN BUDGET & API GUARD)

### 4.1. Ngân sách Token Ngặt nghèo cho Prompt
- Groq API có giới hạn tốc độ (TPM/RPM). Để tránh mã lỗi `HTTP 429` và hiện tượng "Lost in the Middle":
  - Giữ nguyên cơ chế rút gọn báo cáo `_distill_report` và cắt trần `_cap_report`.
  - Khối **Bayesian Regime Prior Prefix (BRPP)** chèn thêm vào prompt của Decision Agent **không được vượt quá 600 ký tự** (cho $K=3$).
  - Tổng kích thước toàn bộ prompt gửi cho Decision Agent trong backtest **phải dưới 6,500 ký tự** (ngưỡng an toàn tuyệt đối).

### 4.2. Xử lý Lỗi & Retry Thông minh
- Mọi lời gọi API LLM phải đi qua hàm wrapper `_invoke_with_retry`.
- Sử dụng Exponential Backoff và bắt đúng thời gian yêu cầu chờ trong thông báo lỗi của Groq (`retry after X seconds`).
- Luôn hỗ trợ cơ chế lưu checkpoint trung gian sau mỗi test point để có thể phục hồi ngay lập tức nếu tiến trình bị ngắt quãng.

---

## 5. TIÊU CHUẨN LẬP TRÌNH & HIỆU NĂNG MÃ NGUỒN

### 5.1. Môi trường & Ngôn ngữ
- **Runtime chuẩn**: Python **3.13.5** (đã ghim trong `.python-version`). Không sử dụng các tính năng không tương thích phiên bản này.
- **Ngôn ngữ diễn giải**: Toàn bộ chú thích mã (comments), docstrings, nhật ký ghi log trên console và giải thích kỹ thuật phải viết bằng **tiếng Việt chuẩn mực, rõ ràng**. Tên hàm, tên biến, tên lớp và schema JSON giữ nguyên bằng tiếng Anh chuẩn.
- **Vị trí tài liệu**: Luồng phản biện dùng `plan.md` và `revision/`; luồng KLTN dùng `docs/plan/plan.md` và `docs/plan/week<N>/` khi cây kế hoạch đó tồn tại. Không tạo cây tuần giả cho task phản biện. Khi chuyển file phải cập nhật đường dẫn script/test/Markdown, giữ nguyên byte bằng chứng đã đóng băng.
- **Giữ tài liệu gọn**: Checklist/tiến độ phản biện đặt ở `revision/README.md`, luồng KLTN đặt ở README tuần. Chỉ tách Markdown khi cần hướng dẫn vận hành hoặc phương pháp độc lập; không tạo thêm receipt theo task nếu chỉ lặp kết quả đã ghi. Giữ schema, QA và fixture JSON mà code/test đọc; không tự di chuyển/đóng gói bằng chứng lịch sử ngoài phạm vi task.
- **README.md tổng (Root README)**: Viết 100% bằng tiếng Anh chuẩn, đóng vai trò tài liệu giới thiệu hệ thống, kiến trúc, cài đặt, kiểm thử và hướng dẫn vận hành. Không ghi tiến độ/checklist/biên bản thực nghiệm vào root README. Tiến độ nằm tại kế hoạch và tài liệu đúng luồng. Nội dung bản thảo tiếng Anh vẫn viết bằng tiếng Anh.

### 5.2. Tối ưu hóa Vector hóa (Vectorization First)
- Cấm lặp `for` theo từng dòng trên Pandas DataFrame (`iterrows()`, `itertuples()` chậm chạp).
- Tận dụng các phép tính vector hóa của NumPy, rolling windows của Pandas, hoặc vectorized math operations.

### 5.3. Tính Toàn vẹn Kiểu dữ liệu & JSON Serialization
- Tránh để kiểu dữ liệu `numpy.bool_`, `numpy.float64`, hoặc `numpy.int64` rò rỉ vào dictionary trả về cho LangGraph state hoặc Web interface.
- Luôn ép kiểu nguyên bản (`bool()`, `float()`, `int()`, `_safe()`) trước khi lưu trữ hoặc serialization để tránh làm sập bộ mã hóa JSON của Flask.

---

## 6. QUY TRÌNH 5 BƯỚC THỰC HIỆN TỪNG TASK CHO CODING AGENT

Khi nhận bất kỳ yêu cầu phát triển nào, Coding Agent phải thực hiện tuần tự:

```text
[Bước 1: Khảo sát] ──► [Bước 2: Tạo Branch] ──► [Bước 3: Lập trình] ──► [Bước 4: Kiểm thử] ──► [Bước 5: Commit & Merge]
  Đọc plan.md &          git checkout -b          Tuân thủ Clean          Kiểm tra                Conventional Commit
  code liên quan          feat/<task-name>         Code & P0 rules         theo phạm vi            Merge & xóa local
```

1. **Bước 1 - Khảo sát**: Đọc kế hoạch đúng luồng ở mục 1.1, kiểm tra code, status và bằng chứng liên quan; xác định phạm vi ảnh hưởng.
2. **Bước 2 - Tạo Branch**: Tạo nhánh task từ đúng nhánh tích hợp theo mục 1.1.
3. **Bước 3 - Lập trình**: Viết mã tối giản, module hóa cao, có đầy đủ type annotations và docstrings tiếng Việt.
4. **Bước 4 - Kiểm tra theo phạm vi**: Áp dụng mục 1.2; chỉ chạy test và biên dịch Python liên quan đến thay đổi, ghi phạm vi/kết quả hoặc lý do không chạy. Task thuần tài liệu không cần chạy suite; mốc cần bốn gate đối soát receipt/code/runtime đã khóa, không tự động chạy lại toàn bộ.
5. **Bước 5 - Commit, Merge & Dọn nhánh**: Commit với Conventional Commits, chuyển về nhánh tích hợp và merge sau khi mọi kiểm tra áp dụng PASS; xóa ngay nhánh local đã merge bằng `git branch -d` theo mục 1.3, rồi báo kết quả và giới hạn còn lại.
