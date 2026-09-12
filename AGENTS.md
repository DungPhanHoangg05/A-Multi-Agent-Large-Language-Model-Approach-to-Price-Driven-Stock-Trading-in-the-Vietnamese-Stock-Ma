# AGENTS.md — Quy chuẩn Thực thi Dành cho AI Coding Agents

Tài liệu này là **bộ quy tắc bắt buộc** cho bất kỳ AI Coding Agent nào tham gia phát triển, sửa lỗi, chạy thực nghiệm hoặc đồng bộ bài báo trong repository này. Mọi hành vi vi phạm quy tắc dưới đây đều bị coi là không đạt tiêu chuẩn (FAILED).

---

## 1. NGUYÊN TẮC CỐT LÕI (CORE PRINCIPLES)

1. **Source of Truth duy nhất:**
   - Mọi nhiệm vụ, thứ tự ưu tiên, yêu cầu kỹ thuật và tiêu chí nghiệm thu đều nằm trong file [`plan/FINAL_COMPLETION_PLAN.md`](file:///plan/FINAL_COMPLETION_PLAN.md).
   - Tuyệt đối không tự suy đoán kiến trúc mới, không tự ý thay đổi mục tiêu task, không thêm tính năng nằm ngoài kế hoạch đã phê duyệt.

2. **Chế độ Single-Agent Tuần tự:**
   - Dự án được thực thi bởi **1 Agent duy nhất theo trình tự tuyến tính (linear sequence)**.
   - Thực hiện từng task một theo đúng thứ tự: `TASK-01` → `TASK-02` → ... → `TASK-13`. Không nhảy cóc, không làm dở dang nhiều task cùng lúc.

3. **Zero Hallucination (Tuyệt đối không bịa đặt):**
   - Không bịa đặt tên hàm, tham số API của bên thứ ba (`vnstock`, `langchain`, `langgraph`, `TA-Lib`, `scipy`, `groq`).
   - Luôn kiểm tra trực tiếp mã nguồn hiện tại hoặc tài liệu API chính thức trước khi gọi hàm.
   - Khi gặp lỗi, đọc đầy đủ traceback, phân tích nguyên nhân gốc rễ trong code thay vì phỏng đoán mò.

4. **Zero Over-Engineering (Không phức tạp hóa):**
   - Chỉ chỉnh sửa đúng phạm vi file và hàm được chỉ định trong task.
   - Không tự ý tái cấu trúc (refactor) các module hoạt động bình thường nếu không phục vụ mục tiêu sửa lỗi hoặc tối ưu hóa đã ghi trong task.
   - Không cài thêm thư viện ngoài danh sách `requirements.txt` trừ khi có yêu cầu bắt buộc và đã kiểm tra tính tương thích.

5. **Tính đúng đắn Dữ liệu & Tài chính (Financial Correctness First):**
   - **Tuyệt đối không để xảy ra rò rỉ dữ liệu (Lookahead Bias / Future Data Leakage):** Mọi phép tính toán chỉ báo, chọn lọc alpha, nạp sentiment tại điểm kiểm tra $e$ chỉ được phép nhìn dữ liệu kết thúc tại $d = e - 1$.
   - **Tách biệt rõ ràng giữa Phân loại và Thực thi:**
     - Nhiệm vụ phân loại (Directional Accuracy): Đánh giá nhãn nhị phân `LONG` / `SHORT` so với hướng giá thực tế.
     - Nhiệm vụ thực thi kinh tế (Account Return): Tuân thủ luật cấm bán khống cổ phiếu cơ sở tại Việt Nam; lệnh `SHORT` chuyển thành giữ tiền mặt (`CASH`, return = 0%).
     - Lợi nhuận tài khoản phải tính theo **lãi kép gộp (compounded equity curve)**, trừ đủ $0.35\%$ chi phí vòng lộn ($0.25\%$ phí + $0.10\%$ trượt giá) cho mỗi lệnh `LONG` thực thi.

6. **Môi trường Thực thi Chuẩn (Python 3.13):**
   - Hệ thống có nhiều phiên bản Python. Môi trường đầy đủ gói thư viện (`pandas`, `numpy`, `TA-Lib`, `vnstock`, `langchain`, `torch`) là **Python 3.13**.
   - Mọi lệnh chạy script, kiểm thử, backtest bắt buộc dùng tiền tố:  
     `py -3.13 <lệnh>` hoặc `C:\Users\Legion\AppData\Local\Programs\Python\Python313\python.exe <lệnh>`.

---

## 2. QUY TRÌNH GIT VÀ QUẢN LÝ NHÁNH (GIT WORKFLOW)

Mọi thay đổi mã nguồn bắt buộc phải tuân theo quy trình nhánh nghiêm ngặt:

```
develop (nhánh chính)
   │
   ├── git checkout -b task/TASK-01-fix-alpha-leakage
   │      └── Thực hiện code + Unit test pass 100%
   │
   ├── git checkout develop && git merge --no-ff task/TASK-01-fix-alpha-leakage
   │      └── Xóa branch: git branch -d task/TASK-01-fix-alpha-leakage
   │
   └── git checkout -b task/TASK-02-paired-shared-reports
          └── ...
```

### Quy tắc bất biến:
1. **KHÔNG BAO GIỜ commit trực tiếp lên nhánh `develop` hoặc `main`:**
   - Mọi dòng code mới phải được viết trên nhánh task riêng biệt.
2. **Quy ước đặt tên nhánh:**
   - Format: `task/<TASK-ID>-<slug-ngan-gon>`
   - Ví dụ:
     - `task/TASK-01-fix-alpha-leakage`
     - `task/TASK-02-paired-shared-reports`
     - `task/TASK-04-compounded-account-pnl`
3. **Cổng kiểm soát trước khi Merge (Merge Gate):**
   Chỉ được phép merge vào `develop` khi thỏa mãn TOÀN BỘ 4 điều kiện sau:
   - [ ] Mã nguồn sửa đổi đúng phạm vi của task, không phát sinh lỗi phụ.
   - [ ] Chạy lệnh test/command tương ứng được ghi trong task và **PASS 100%**.
   - [ ] Kiểm tra `git status` và `git diff` sạch sẽ, không để lại file rác, file tạm, cache nháp.
   - [ ] Đạt đầy đủ tất cả các tiêu chí nghiệm thu (Acceptance Criteria) của task đó.
4. **Lệnh Merge chuẩn:**
   ```bash
   git checkout develop
   git merge --no-ff task/<TASK-ID>-<slug> -m "feat: complete <TASK-ID> - <mô tả ngắn>"
   git branch -d task/<TASK-ID>-<slug>
   ```

---

## 3. QUY TRÌNH THỰC HIỆN MỘT TASK (AGENT SOP)

Mỗi khi nhận một task mới, Agent phải thực hiện tuần tự theo 7 bước:

```
[BƯỚC 1: Đọc & Hiểu Task]
    │  Tra cứu TASK-ID trong plan/FINAL_COMPLETION_PLAN.md
    │  Nắm vững: Objective, Current Issue, File/Function, Test command, Acceptance Criteria.
    ▼
[BƯỚC 2: Khởi tạo Nhánh Git]
    │  git checkout develop
    │  git pull (nếu có remote)
    │  git checkout -b task/<TASK-ID>-<slug>
    ▼
[BƯỚC 3: Khảo sát Code & Viết Test]
    │  Dùng view_file/grep_search kiểm tra chính xác các dòng code cần sửa.
    │  Xây dựng hoặc cập nhật test case để kiểm chứng lỗi hiện tại (tái hiện lỗi trước khi sửa).
    ▼
[BƯỚC 4: Chỉnh sửa Tối thiểu & Chính xác]
    │  Dùng replace_file_content / multi_replace_file_content để sửa đúng phạm vi.
    │  Không sửa lan man sang các hàm khác.
    ▼
[BƯỚC 5: Chạy Test Xác minh]
    │  Chạy lệnh test quy định bằng py -3.13.
    │  Nếu fail: phân tích traceback và sửa tiếp.
    │  Nếu pass: xác nhận đúng output mong đợi (Expected Output).
    ▼
[BƯỚC 6: Merge vào Nhánh develop]
    │  git add <các file sửa đổi>
    │  git commit -m "fix/feat: <TASK-ID> <nội dung ngắn>"
    │  git checkout develop
    │  git merge --no-ff task/<TASK-ID>-<slug>
    │  git branch -d task/<TASK-ID>-<slug>
    ▼
[BƯỚC 7: Cập nhật Trạng thái Plan]
       Đánh dấu hoàn thành task trong plan/FINAL_COMPLETION_PLAN.md.
       Chuyển sang task tiếp theo theo đúng thứ tự tuyến tính.
```

---

## 4. QUY CHUẨN NGÔN NGỮ VÀ BÀI BÁO (LANGUAGE & LATEX GUIDELINES)

1. **Mã nguồn Python:**
   - Comments, docstrings, và log in ra console giữ phong cách tiếng Việt rõ ràng, dễ hiểu cho nhà đầu tư Việt Nam (đồng nhất với codebase hiện tại).
   - Biến số, tên hàm, tên lớp bắt buộc dùng tiếng Anh chuẩn mực (`snake_case` cho hàm/biến, `PascalCase` cho class).

2. **Tài liệu Bài báo (`ESWA/`):**
   - Toàn bộ văn bản trong thư mục `ESWA/` bắt buộc viết bằng **tiếng Anh học thuật chuẩn mực (Academic English)**, phù hợp với tiêu chuẩn của tạp chí *Expert Systems with Applications* (Elsevier).
   - Giữ nguyên cấu trúc định dạng của class `elsarticle.cls`.
   - Khi chỉnh sửa bảng biểu, kiểm tra căn lề, độ rộng cột (`\columnwidth` hoặc `\textwidth`), không để tràn lề (overfull hbox).
   - Đảm bảo trích dẫn tài liệu tham khảo chính xác qua BibTeX trong `references.bib`.

---

## 5. DANH MỤC CẤM (ZERO TOLERANCE RESTRICTIONS)

- ❌ **CẤM** commit trực tiếp vào `develop` hoặc `main` mà không qua task branch.
- ❌ **CẤM** đẩy code khi chưa chạy test kiểm chứng bằng `py -3.13`.
- ❌ **CẤM** bỏ qua các lỗi lọt dữ liệu tương lai (Data Leakage) hoặc sửa test để pass giả tạo.
- ❌ **CẤM** bịa số liệu thực nghiệm trong bài báo; mọi số liệu trong bảng phải trích xuất từ file JSON/CSV kết quả thật.
- ❌ **CẤM** để lại các ghi chú nháp ("pending regeneration", "legacy sum", "unresolved issue") trong bản nộp cuối cùng.
- ❌ **CẤM** xóa bỏ các phần kiểm định rủi ro hoặc che giấu kết quả âm; tính trung thực khoa học là ưu tiên số 1.
