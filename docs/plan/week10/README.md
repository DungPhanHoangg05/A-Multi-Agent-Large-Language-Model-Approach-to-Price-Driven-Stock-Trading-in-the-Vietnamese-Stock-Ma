# Tuần 10 — Học Bayes từ prior tasks và target context

**Kế hoạch thay thế 27/10/2026; MT-BICL chưa triển khai, 0/10 task DONE.**
[Kế hoạch tổng](../plan.md) · [W11](../week11/README.md) · [W12](../week12/README.md)

Mục tiêu: một bộ dự báo **Multi-Task Bayesian ICL (MT-BICL)** nhỏ học từ
các nhiệm vụ trước và các ví dụ đã đóng của nhiệm vụ hiện tại, rồi cung
cấp xác suất dự báo/context cho Decision LLM. Giữ hệ thống đa agent và
Original mặc định. Đo riêng ba mức: học được cơ chế, dự báo có ích, tài
khoản cải thiện. Tên phương pháp hoặc synthetic test không chứng minh lợi nhuận.

## 1. Thay đổi về phương pháp

Thiết kế mới bổ sung target context theo thời gian và một mô hình được
huấn luyện để đọc ranh giới prior/target. Chèn thống kê vào hosted LLM
không tự tạo năng lực này. Gate một mô hình payoff cũng không thay phép
kiểm toàn hệ thống. Lịch sử thử nghiệm nằm trong [gói bằng chứng](../implementation_evidence.zip),
manifest retired_20261027/manifest.json; không phải checklist hiện hành.
Thay kế hoạch không reset dữ liệu đã xem, xem khai báo exposure ở plan.md.

Theo [paper §4–5](https://arxiv.org/html/2606.20538v1), input gồm prior
datasets, target context và query; transformer học với loss tại target.
Paper kiểm thay prior khi giữ target cố định và đối chiếu naive pooling.
Ở đây thích ứng cấu trúc đó cho y=LONG net có lãi, không tuyên bố tái lập
mọi kết quả hoặc quy mô paper. [Mã tác giả](https://github.com/martianmartina/multi-task-bayesian-icl)
là nguồn đối chiếu tokenizer/mask/loss, không thay nguyên runtime hiện hữu.

## 2. Dense PIT bank và định nghĩa nhiệm vụ

- x gồm momentum_5, momentum_20, volatility_20, ma_distance_20 từ primitive
  PIT hiện hữu. y=1[r_net>0], r_net dùng compute_round_trip_net_return với
  Open(t+1)/Close(t+3), phí/slippage hai chiều; giữ r_net đầy đủ ở sidecar.
  Không dùng action/confidence/justification Decision làm feature.
- Dựng lịch step=3 từ giá thô/quyền của bốn mã đến 2022; tận dụng 2018–2019
  nếu audit xác nhận có dữ liệu hợp lệ. Không giả định ngày đầu/số mẫu trước
  inventory; không nội suy quanh quyền hoặc trộn adjusted/raw. Nhãn lịch sử
  tạo bằng giá, không cần gọi LLM để dựng thêm historical agent reports.
- Task = mã × block63 phiên VNINDEX không chồng lấp, neo lịch train cố định.
  Regime là metadata tại đầu block; không dùng điểm đảo chiều biết sau này
  để chia task. Cấu hình chính chỉ truy xuất prior cùng mã.
- Target C_t: tối đa tám cycle gần nhất trong block hiện tại, exit<query;
  cho phép m=0..8 và báo cold-start. Không lấy block khác rồi gọi là target.
- Prior D1…DK: tối đa ba block trước target, mỗi block tối đa tám cycle,
  ít nhất hai cycle/block. Rank: cùng regime đầu block với regime PIT hiện
  tại trước, centroid-distance train-scaled tăng dần, độ mới, task ID.
  Chọn cycle bằng distance với x query, rồi cutoff/ID; không nhìn nhãn.
- Prior/target/query rời ID và entry–exit. Centroid chỉ dùng cycle đã đóng.
  Thiếu dữ liệu giữ reason; không ép đủ K hoặc cân bằng thắng/thua.
  Tuổi là diagnostics/thứ tự, không áp lại trần 730 ngày để che mất support.
  Không gọi tăng coverage là tăng độ chính xác.

Scaler/weights chỉ dùng train đến 2020; 2021 chọn checkpoint, 2022 báo cáo
validation, 2023 development đã xem. Nếu không đủ dữ liệu đến 2020, chốt
lại split trước train, không chuyển 2022 vào train sau khi xem kết quả.
Tách split bằng exit_date, loại cycle vắt qua ranh giới. Regime cho query
train phải dùng historical prefix; artifact cho validation/test fit đến
2020 rồi đóng băng, không dùng HMM cuối 2022 gán lại regime train sớm hơn.
Trong development/xác nhận, bank được nối thêm cycle giá đã đóng theo
cutoff: block cũ có thể thành prior của block sau, block hiện tại tạo C.
Không refit weights/scaler/HMM, không học từ action hay report đánh giá.
Metadata/source snapshot mới namespace riêng; không nhận self-seal thay
verification. Audit K/m theo mã/regime/quý trước bất kỳ response Decision.

## 3. Bayes tham chiếu kiểm được cơ chế

Đề xuất simulator logistic hữu hạn: 16 hyper-state λ và 64 vector
w=(bias,b1,…,b4) cố định bằng seed; p(w|λ) chuẩn hóa quanh tâm tương ứng;
y|x,w~Bernoulli(sigmoid(w·[1,x])). Mỗi episode lấy λ rồi các w_k riêng
cho prior tasks và w_* cho target. Người học không thấy λ/w. Bảng hệ số,
p(λ), p(w|λ), phân phối x và seed khóa ở W10-02, không dùng 2023–2025.
Hữu hạn hóa latent là thiết kế riêng để oracle khả thi, khác paper gốc.

    p(λ,w*|D1…DK,C) ∝ p(λ) × ∏k[Σwk p(wk|λ)L(Dk|wk)] × p(w*|λ)L(C|w*)
    p(y*=1|x*,D,C) = Σλ,w* sigmoid(w*·[1,x*]) × p(λ,w*|D,C)

Tính log-space, normalize joint một lần; C cũng cập nhật λ. Oracle
enumeration độc lập kiểm m=0, permutation và duplicate; không gộp prior
thành observation của target. Oracle chỉ đúng cho simulator đã biết,
không được gọi là ground truth Bayes của thị trường.

## 4. Learner nhỏ có giới hạn tài nguyên

Decoder causal hai lớp, hidden128, bốn attention head, FF256; input numeric
x/y, PRIOR/TARGET/QUERY và missing-mask; đầu ra Bernoulli logit. Che nhãn
query; loss chỉ ở target theo causal shift. Random thứ tự prior khi train,
target giữ thứ tự. Train K=0..3, m=0..8 để ablation trong miền đã học.

Một kiến trúc, ba seed cố định, không ensemble. AdamW lr=3e−4, batch128,
tối đa 10.000 step/seed; benchmark 100 step trước khi khóa step ở W10-02.
Tổng train tối đa 12 giờ; chỉ giảm batch vì VRAM trước train thật. Máy hiện
thấy torch 2.11.0+cu128 và RTX 5060 Laptop, chưa đo tốc độ. Giữ Python
3.13.5, ghi runtime/seed/checkpoint/hash; không tự nâng dependency chung.
Tách môi trường train nếu cần, không làm thay runtime baseline.

Batch synthetic và thị trường PIT tỷ lệ 1:1. Không gán synthetic là giao
dịch thật. Train thị trường đến 2020; chọn checkpoint/seed bằng mean log
loss 2021 đều theo mã, Brier tie-break; báo cả ba seed. Không chọn theo
P&L. Validation 2022 giữ nguyên cấu hình, không refit bằng 2023/2024/2025.
2022 đã được xem trong lịch sử nghiên cứu nên không là holdout độc lập.

Baseline numeric: base rate train, logistic thường cùng x, no-prior,
no-target và naive pooling. Báo Brier/log loss, calibration bins cố định,
runtime, độ nhạy m/K. Confidence dạng chữ của LLM không là xác suất model.
Xác suất thắng không tối ưu trực tiếp lợi nhuận: giữ bảng r_net theo bin p,
mean gain/loss và các ca thắng nhỏ/thua lớn trên validation, không suy ra
expected return từ p. Khóa bin trước xem kết quả; không chỉnh threshold
Numeric_only hoặc ép Decision mua vì accuracy tốt.

## 5. Gate đúng câu hỏi, không thay bằng gate hồi quy payoff

**Bắt buộc trước development:** PIT/kinh tế/mask/serialization đúng, p hữu
hạn; oracle đúng; synthetic test riêng 5.000 episode khóa trước train:
mean KL(oracle||model)≤0,02 nat, P95 |p_model−p_oracle|≤0,10.
Thay prior giữ C/x cố định: dấu Δp khớp oracle≥90% trên cặp có
|Δoracle|≥0,05, báo mẫu số; thiếu cặp thì inconclusive. So naive pooling
trên fixture khác latent để kiểm ranh giới task. Ngưỡng này là tiêu chí
đề xuất, không là mức paper bảo đảm. Không đạt cơ chế thì không phát hành
candidate dưới tên MT-BICL hoặc thay âm thầm bằng model số khác.

**Validation thị trường:** báo đầy đủ baseline/seed trên 2022. Brier/log
loss chưa tốt là kết quả bất lợi, không được ghi PASS. Một development
hệ thống đăng ký trước vẫn được phép nếu gate kỹ thuật/cơ chế đạt để đo
giá trị tăng thêm của context. Không dùng MAE của mô hình return khác
để chặn phép kiểm này, không yêu cầu numeric p>0,5 phải thắng LLM trước.

**Kinh tế:** chỉ W11/W12 đo được. Không override action theo p. Nếu chỉ
Numeric thắng thì claim numeric; không quy cho demonstrations hoặc LLM.
Các kết quả bất lợi và độ nhạy được giữ nguyên, không quét thêm architecture.

## 6. Tích hợp Decision và ngân sách prompt

Upstream một lần → x/prior/target PIT → learner → prefix → Decision →
engine cũ. Learner đọc tối đa 24 observation prior +8 target; LLM thấy
tối đa hai exemplar/prior task và hai target gần nhất, kèm K/m/support/p.
Projection ít ví dụ hơn phải công bố, không gọi là toàn context.

P1/P2/P3 biểu diễn task (x→y), T là context gần đây, Q chưa có nhãn.
Hiển thị bốn feature chuẩn hóa/lượng tử hóa cố định, legend rõ; sidecar
giữ full precision/ID/hash/membership. Toàn BRPP≤600, prompt<6500, giữ
distill/cap. Test case ba task đủ ví dụ, không cắt nhãn/legend để vừa.

Base instruction/schema chung mọi nhánh của run mới. Decision đối chiếu
tín hiệu hiện tại, prior và target trong evidence_for/evidence_against/
justification hiện có; không ép đồng ý prior. p dự báo y net>0, không là
expected return/R:R. TP/SL do LLM viết không thay thời gian thoát cố định.
Citation chỉ telemetry. Prior-off reuse chỉ khi canonical request trùng.

## 7. Checklist W10

| Task | Đầu ra / điều kiện hoàn thành | Phụ thuộc | Trạng thái |
| --- | --- | --- | --- |
| W10-01 | Inventory giá/quyền/exposure/W9; benchmark GPU và xác nhận quỹ thời gian còn lại | Bắt đầu | [ ] TODO |
| W10-02 | Khóa protocol/claim/split/seed/simulator/model/ma trận/gate trước train | 01 | [ ] TODO |
| W10-03 | Dense cycle bank, bốn feature/scaler PIT và nhãn engine; missing có reason | 02 | [ ] TODO |
| W10-04 | Task builder, prior/target/query rời; streaming và projection fixture | 03 | [ ] TODO |
| W10-05 | Simulator, oracle enumeration độc lập và no-pooling control | 02–04 | [ ] TODO |
| W10-06 | Train ba seed; chọn checkpoint bằng 2021, seal artifacts | 05 | [ ] TODO |
| W10-07 | Mechanism gate/synthetic test, validation 2022/calibration/baselines | 06 | [ ] TODO |
| W10-08 | Adapter/prefix/paired/shared-off/retry/checkpoint; test đường đổi | 04; 07 cơ chế đạt | [ ] TODO |
| W10-09 | Dry-run 60 điểm/coverage và 24 semantic probe tổng hợp trước run thật | 08 | [ ] TODO |
| W10-10 | Source/runtime/model/tokenizer freeze; CLI run/resume/verify; release development | 09 | [ ] TODO |

Module dự kiến core/mt_bicl_{tasks,oracle,model,context,runtime,reports}.py,
scripts/train_mt_bicl.py và scripts/run_mt_bicl.py; chưa tồn tại. Reuse
engine, giá PIT, HMM, retry/pacer/ledger đã kiểm; không restore toàn revision
cũ vào namespace mới. Test: future append/scaler/mask/query-label, optimizer
frozen tại test, oracle, prompt cap, paired/unknown/resume và JSON native.
Theo AGENTS.md 1.2, chọn test đường đổi, không tự chạy toàn suite mỗi task.

## 8. Thời hạn và dọn cây hiện hành

W10–W12 là ba mốc thay thế trong hạn 12 tuần, không cộng thêm ba tuần từ
ngày viết lại. W10-01 phải chốt quỹ thời gian thực; không đủ train/tích hợp/
kiểm chứng thì ghi giới hạn khả thi và hoàn thiện luận văn. API key chỉ
do người dùng chạy; agent chuẩn bị và kiểm offline.

Phân bổ đề xuất trong năm ngày làm việc của W10: ngày 1 inventory/protocol;
ngày 2–3 bank/tasks/oracle; ngày 4 train/validation; ngày 5 adapter/dry-run/
freeze. Nếu mốc kỹ thuật trễ, dùng phần thời gian development còn lại để
hoàn tất nhưng giữ điểm dừng W12 ngày hai; không bỏ gate để bù tiến độ.

Mã/tài liệu/kết quả revision cũ được lưu nguyên byte trong
implementation_evidence.zip, retired_20261027/, base commit 23067b2,
rồi gỡ khỏi cây hiện hành. Giữ Git và usage chung; restore vào checkout
riêng, không đè ledger. W9/hệ thống gốc giữ nguyên. Nghiệm thu dọn dẹp
không tính DONE cho task W10 mới.

**Kiểm tra lần thay kế hoạch:** gỡ 62 file tracked (52 Python) và 984 file
output riêng của revision cũ; 1.051 file nguồn/bằng chứng đã lưu kèm
SHA-256. Đối soát tất cả entry, giữ nguyên 88 entry có sẵn trong archive;
ledger dùng chung và ba hash report/bootstrap/frozen archive W9 không đổi.
Kiểm link/anchor/UTF-8/checklist/diff và AST import còn lại PASS.

Kiểm thử phạm vi hệ thống giữ lại: test_bayesian_retriever.py **11 PASS**,
test_prior_backtest_leakage.py **3 PASS**, test_backtest_token_budget.py
**11 PASS**. Hai suite dùng thư mục tạm gặp lỗi/kẹt quyền Windows trong
sandbox, đã chạy lại đúng suite ngoài sandbox và PASS. Không gọi API,
không chạy toàn suite/E2E; không compile Python vì chỉ xóa module độc lập,
không sửa file Python còn lại. Kết quả này không phải nghiệm thu MT-BICL.
