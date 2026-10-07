# QUY TẮC & RÀNG BUỘC PHÁT TRIỂN HỆ THỐNG DÀNH CHO CODING AGENT (AGENTS.MD)

Tài liệu này là **bộ quy tắc tối cao (Mandatory Directives)** bắt buộc mọi Coding Agent và AI Assistant phải tuân thủ nghiêm ngặt trong suốt quá trình nâng cấp hệ thống đa agent phục vụ Khóa luận Tốt nghiệp (KLTN):
**"Regime-Aware Multi-Task Bayesian In-Context Learning for Multi-Agent LLM Stock Trading"**.

Mục tiêu cốt lõi: **Nâng cấp tính năng mới mà tuyệt đối KHÔNG làm gãy vỡ, biến dạng hoặc suy giảm tính ổn định của hệ thống hiện tại.**

---

## 1. QUY TRÌNH PHÂN NHÁNH GIT & HỢP NHẤT (GIT WORKFLOW & BRANCHING)

### 1.1. Nhánh cơ sở và Nhánh tính năng
- **Nhánh `develop`** là nhánh tích hợp chính. Tuyệt đối **KHÔNG** commit hoặc đẩy mã trực tiếp lên nhánh `develop` hoặc `main`.
- Mỗi nhiệm vụ (task) kỹ thuật **BẮT BUỘC** phải được thực hiện trên một nhánh độc lập tách ra từ `develop`:
  ```bash
  git checkout develop
  git pull origin develop
  git checkout -b <branch-prefix>/<task-name>
  ```
- **Tiền tố tên nhánh hợp lệ**:
  - `feat/<tên-tính-năng>`: Thêm tính năng mới (ví dụ: `feat/regime-detector-hmm`, `feat/bayesian-retriever`).
  - `fix/<tên-lỗi>`: Sửa lỗi hệ thống (ví dụ: `fix/token-budget-distill`, `fix/leakage-temporal-cutoff`).
  - `test/<tên-kiểm-thử>`: Bổ sung bộ test mới (ví dụ: `test/regime-leakage-suite`).
  - `refactor/<tên-module>`: Tối ưu cấu trúc mã không làm đổi logic (ví dụ: `refactor/decision-prompt-builder`).
  - `docs/<tên-tài-liệu>`: Cập nhật tài liệu kỹ thuật (ví dụ: `docs/methodology-spec`).

### 1.2. Điều kiện Tiên quyết để Hợp nhất (Merge Criteria vào `develop`)
Chỉ được phép hợp nhất nhánh tính năng vào `develop` khi và chỉ khi vượt qua **toàn bộ 4 cổng kiểm soát (Gates)**:
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

## 3. CÁC RÀO CHẮN LIÊM CHÍNH DỮ LIỆU & HỢP ĐỒNG KINH TẾ (P0 DIRECTIVES)

Để bảo đảm giá trị khoa học của Khóa luận Tốt nghiệp trước Hội đồng chấm, Coding Agent phải tuân thủ các nguyên tắc bất di bất dịch:

### 3.1. Bảo toàn Hợp đồng Kinh tế $T+2.5$ (Economic Contract Invariance)
- **Không bao giờ thay đổi công thức tính P&L cốt lõi**:
  - Lệnh `LONG`: Mua tại giá $Open(t+1)$, tự động bán tất toán tại giá $Close(t+3)$ (sau đúng 3 phiên giao dịch).
  - Lệnh `SHORT`: Giữ toàn bộ $Cash$ (tiền mặt), tuyệt đối không mở vị thế bán khống cổ phiếu cơ sở Việt Nam.
  - Chi phí giao dịch: Áp dụng đầy đủ phí môi giới 0.25% và trượt giá 0.10% ở **cả 2 chiều MUA và BÁN** (xấp xỉ 0.70% một vòng quay vốn).
- **Hợp nhất nhãn kinh tế**: Nhãn của các tác vụ lịch sử (Historical Tasks trong Memory Bank) bắt buộc phải được sinh bằng chính hàm `compute_round_trip_net_return` trong `core/backtest_engine.py`. Cấm dùng lợi nhuận Close-to-Close $T+0$ cho prior tasks.

### 3.2. Chống Rò rỉ Dữ liệu Tương lai (Strict Point-in-Time & Zero-Leakage)
- **Nguyên tắc Cắt thời gian (Temporal Cutoff)**: Khi xử lý điểm kiểm định tại ngày $t_{\text{as\_of\_date}}$:
  - `point_in_time_df`: Chỉ chứa các nến có $\text{Datetime} \le t_{\text{as\_of\_date}}$.
  - `SentimentStore`: Chỉ lấy các bài báo có ngày công bố $\le t_{\text{as\_of\_date}}$. Loại bỏ mọi bài báo không có ngày (`date_parsed is None`).
  - `BayesianRetriever` / `HistoricalMemory`: Chỉ được phép truy xuất các chu kỳ lịch sử có $\text{exit\_date} < t_{\text{as\_of\_date}}$. Bất kỳ chu kỳ nào vắt ngang qua hoặc sau ngày $t_{\text{as\_of\_date}}$ đều phải bị loại bỏ lập tức.
- Mọi vi phạm về leakage phải ném ngoại lệ `ValueError` hoặc `AssertionError`, không bao giờ được âm thầm bỏ qua.

### 3.3. Bảo toàn Giao thức Ghép cặp (Paired Protocol Invariance)
- Pha Upstream (`Indicator Agent` $\rightarrow$ `Pattern Agent` $\rightarrow$ `Trend Agent`) chỉ được chạy **1 lần duy nhất** cho mỗi test point.
- Kết quả Upstream phải được deep-copy nguyên vẹn sang các nhánh so sánh đối chứng (Full, Baseline, Bayesian Prior...). Tuyệt đối không gọi lại LLM thị giác ở các nhánh đối chứng để tránh nhiễu ngẫu nhiên.

---

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
- **Thư mục kế hoạch theo tuần**: Đặt tài liệu, checklist và receipt của tuần tại `docs/plan/week<N>/`, cùng cây thư mục với `docs/plan/plan.md`. Các tuần tiếp theo tiếp tục dùng cấu trúc này theo thay đổi của người dùng; khi chuyển file phải cập nhật đường dẫn trong script, test và liên kết Markdown, giữ nguyên byte các bằng chứng đã đóng băng.
- **Giữ tài liệu gọn**: README của từng tuần là nơi cập nhật checklist và tiến độ. Chỉ tách Markdown khi cần hướng dẫn vận hành hoặc phương pháp độc lập; không tạo thêm biên bản/receipt theo từng task nếu chỉ lặp lại kết quả đã ghi. Giữ schema, QA và fixture JSON mà code/test đọc; bằng chứng lịch sử dư thừa được đóng gói nguyên byte trong `docs/plan/implementation_evidence.zip`.

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
  Đọc plan.md &          git checkout -b          Tuân thủ Clean          compileall,             Conventional Commit
  code liên quan          feat/<task-name>         Code & P0 rules         unittest, E2E           Merge vào develop
```

1. **Bước 1 - Khảo sát**: Đọc kỹ [docs/plan/plan.md](docs/plan/plan.md), kiểm tra các file mã nguồn liên quan và xác định phạm vi ảnh hưởng.
2. **Bước 2 - Tạo Branch**: Tạo nhánh mới từ `develop` theo quy ước `feat/...`, `fix/...`, `test/...`.
3. **Bước 3 - Lập trình**: Viết mã tối giản, module hóa cao, có đầy đủ type annotations và docstrings tiếng Việt.
4. **Bước 4 - Kiểm thử**: 
   - Chạy `py -3.13 -m compileall agents core data_manager scripts tests utils`.
   - Chạy `py -3.13 -X utf8 -m unittest discover -s tests -v`.
   - Chạy `py -3.13 scripts/run_end_to_end_test.py`.
5. **Bước 5 - Commit & Merge**: Commit với Conventional Commits (tuyệt đối không có `W1D1`), chuyển về `develop` và merge nhánh sau khi toàn bộ bài test đã pass.
