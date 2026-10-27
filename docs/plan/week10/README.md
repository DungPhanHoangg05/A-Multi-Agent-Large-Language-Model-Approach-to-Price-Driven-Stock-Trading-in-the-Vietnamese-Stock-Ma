# Tuần 10 — Học Bayes từ prior tasks và target context

**Kế hoạch thay thế 27/10/2026; W10-01–07 DONE, 7/10 task DONE.
W10-07 đã nghiệm thu đánh giá; gate cơ chế FAIL — NO_MT_BICL_RELEASE.**
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

Simulator logistic hữu hạn đã khóa tại [protocol W10-02](#w10-02--khóa-protocol-trước-train-27102026): 16 hyper-state λ và 64 vector
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

Một kiến trúc, ba seed **17/42/73**, không ensemble. AdamW lr=3e−4, effective
batch128, **10.000 optimizer step/seed**, checkpoint mỗi 1.000 step.
Benchmark proxy 100 step W10-01 đã đo; W10-06 phải kiểm 100 step pipeline thật
trước train, không giữ weights preflight. Tổng train tối đa 12 giờ; chỉ giảm
physical batch vì VRAM trước cả ba seed, dùng accumulation giữ effective batch.
Runtime torch 2.11.0+cu128, RTX 5060 Laptop đã kiểm. Giữ Python
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
| W10-01 | Inventory giá/quyền/exposure/W9; benchmark GPU và xác nhận quỹ thời gian còn lại | Bắt đầu | [x] DONE — inventory/benchmark PASS; quỹ 14–28 giờ, khả thi toàn bộ còn có điều kiện |
| W10-02 | Khóa protocol/claim/split/seed/simulator/model/ma trận/gate trước train | 01 | [x] DONE — protocol v1, bảng simulator, fixture và verifier đã khóa; chưa release train/API |
| W10-03 | Dense cycle bank, bốn feature/scaler PIT và nhãn engine; missing có reason | 02 | [x] DONE — 1.235 cycle hợp lệ/1.640 ứng viên, support giá PASS; chưa release train |
| W10-04 | Task builder, prior/target/query rời; streaming và projection fixture | 03 | [x] DONE — metadata PIT, disjoint membership, stream và packing/projection; support development 41/60 PASS |
| W10-05 | Simulator, oracle enumeration độc lập và no-pooling control | 02–04 | [x] DONE — oracle độc lập PASS; khóa 5.000 test/5.000 cặp, chuẩn bị dữ liệu preflight |
| W10-06 | Train ba seed; chọn checkpoint bằng 2021, seal artifacts | 05 | [x] DONE — preflight GPU PASS, đủ 30.000 step/30 checkpoint; seed42 step1000 được chọn bằng 2021, seal/verify PASS |
| W10-07 | Mechanism gate/synthetic test, validation 2022/calibration/baselines | 06 | [x] DONE — đánh giá/replay/integrity đầy đủ; cơ chế FAIL cả ba seed, NO_MT_BICL_RELEASE |
| W10-08 | Adapter/prefix/paired/shared-off/retry/checkpoint; test đường đổi | 04; 07 cơ chế đạt | [ ] BLOCKED — candidate không đạt gate cơ chế W10-07 |
| W10-09 | Dry-run 60 điểm/coverage và 24 semantic probe tổng hợp trước run thật | 08 | [ ] BLOCKED — phụ thuộc 08 và gate cơ chế chưa đạt |
| W10-10 | Source/runtime/model/tokenizer freeze; CLI run/resume/verify; release development | 09 | [ ] BLOCKED — không release candidate đã FAIL cơ chế |

Đã có `core/mt_bicl_{bank,scaler,regimes,stream,tasks,context,simulator,oracle,oracle_reference,batches}.py`
cùng CLI dựng/kiểm bank, task/context và corpus oracle. Learner và CLI train/resume/seal
đã nghiệm thu trên GPU. Đánh giá mechanism/validation đã hoàn tất nhưng gate
cơ chế FAIL; adapter/run/release bị chặn cho candidate này. Reuse
engine, giá PIT, HMM, retry/pacer/ledger đã kiểm; không restore toàn revision
cũ vào namespace mới. Test: future append/scaler/mask/query-label, optimizer
frozen tại test, oracle, prompt cap, paired/unknown/resume và JSON native.
Theo AGENTS.md 1.2, chọn test đường đổi, không tự chạy toàn suite mỗi task.

## 8. Thời hạn và dọn cây hiện hành

W10–W12 là ba mốc thay thế trong hạn 12 tuần, không cộng thêm ba tuần từ
ngày viết lại. W10-01 phải chốt quỹ thời gian thực; không đủ train/tích hợp/
kiểm chứng thì ghi giới hạn khả thi và hoàn thiện luận văn. API key chỉ
do người dùng chạy; agent chuẩn bị và kiểm offline.

Lịch ngày và quỹ giờ đã chốt tại [W10-01](#w10-01--inventory-và-khả-năng-thực-thi-27102026)
thay lịch tương đối tham chiếu sau đây. Phân bổ đề xuất trong năm ngày của W10: ngày 1 inventory/protocol;
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

## W10-01 — Inventory và khả năng thực thi, 27/10/2026

**DONE — đã kiểm inventory/benchmark và nhận xác nhận quỹ thời gian thực tế.**
Hoàn tất task kiểm toán khả thi không có nghĩa toàn bộ MT-BICL đã triển khai
hoặc chắc chắn hoàn thành thực nghiệm trong quỹ giờ còn lại.
Nhánh `feat/mt-bicl-resource-inventory` tách từ `develop` đã đồng bộ tại
`83c838f`. Hai công cụ offline mới tạo [inventory máy đọc](resource_inventory.json)
và [kết quả đo GPU](gpu_benchmark.json), để W10-02 dùng khi khóa protocol.
Không gọi LLM/API, sinh nhãn thị trường mới, khôi phục revision đã dừng,
fit HMM hoặc train candidate trong bước này.

### Giá, quyền và khả năng dùng lịch sử sớm

Đã chạy lại verifier nguồn hiện hành, không chỉ đọc cờ PASS trong manifest:

| Nguồn | Inventory và kết quả xác minh |
| --- | --- |
| `data/execution_prices` | Bốn mã, mỗi mã 1.251 phiên, 02/01/2018–30/12/2022; CSV/evidence/quyền/checksum/lịch và tám mẫu quyền PASS; lịch legacy 852/868 hợp lệ |
| `data/execution_prices_oos` | Bốn mã, mỗi mã 1.750 phiên đến 31/12/2024; cùng gate PASS, lịch legacy 1.510/1.532 hợp lệ |
| `data/historical` | Năm CSV, mỗi mã 1.999 phiên đến 31/12/2025; checksum/lịch và bốn nến VNINDEX thay nguồn PASS. Cổ phiếu adjusted không thay giá thực thi thô |
| Giá thô 2025 trong archive retired | Mỗi mã 1.999 phiên, gồm 249 phiên năm 2025. CSV/evidence/acquisition/events khớp hash; tái dựng trường raw khớp CSV, prefix 1.750 phiên và events khớp nguyên nguồn OOS |

Nguồn 2025 ở `retired_20261027/outputs/bayesian_benchmark/unified_bic_v1/inputs/execution_prices_2025/`
trong `implementation_evidence.zip`; chưa nhập vào namespace MT-BICL hoặc
cấp release. Kiểm byte/raw/prefix này chưa thay verifier mẫu quyền 2025
và audit trước xác nhận W11-06. Không tải lại nguồn hoặc coi self-seal cũ
là chứng minh gate hiện hành. Toàn bộ **1.051 entry** trong manifest retired
đã đối soát SHA-256 và số byte; archive không thay đổi.

Không thiếu phiên so với VNINDEX ở hai bộ raw hiện hành. Cả bốn mã có
Volume=0 ngày 23–24/01/2018; không điền giá/khối lượng. Số ngày chặn trong
2018–2022 FPT/VNM/VCB/MWG lần lượt 16/15/6/14, hợp sự kiện quyền với gap
Reference. Feature loại cửa sổ có barrier; nhãn loại quyền trong `(entry,exit]`
và phiên giữ lệnh không có khớp. Hai điều kiện được đếm riêng, không cộng
các nhóm loại có thể giao nhau.

Lưới **thăm dò**, query từ index 20 của lịch giá chung, step=3, giữ 21 phiên
feature liên tục và loại cycle vắt năm, cho support đồng thời giá/feature:

| Mã | 2018 | 2019 | 2020 | Train ≤2020 | Chọn checkpoint 2021 | Validation 2022 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| FPT | 49 | 60 | 63 | 172 | 59 | 58 |
| VNM | 56 | 63 | 63 | 182 | 63 | 65 |
| VCB | 65 | 76 | 74 | 215 | 76 | 78 |
| MWG | 57 | 64 | 67 | 188 | 61 | 67 |
| Tổng | 227 | 263 | 267 | 757 | 259 | 268 |

Mỗi mã có bốn cycle vắt năm bị loại. Đây **chưa phải bank, lịch khóa hoặc
số episode train cuối cùng**; chưa kiểm block63, HMM, K/m, phân tách task
và purge theo protocol. Không dùng nhãn để chọn neo hoặc tăng support.

Điểm cần giải quyết trước train: primitive HMM cần MA200 và tối thiểu 300
hàng feature, tương đương **499 phiên raw**; lịch hiện có chỉ đủ số hàng
từ **30/12/2019**, chưa bảo đảm fit hội tụ. Vì vậy có giá/feature 2018–2019
không đồng nghĩa có regime PIT ở đầu từng block. W10-02 phải khóa policy
missing/reason hoặc phạm vi episode hợp lệ; không gán ngược bằng HMM cuối
2022, không coi 757 là số train có regime hoàn chỉnh. Giữ split dự kiến,
không tự chuyển validation 2022 vào train để bù thiếu.

### Exposure và bằng chứng W9

Giữ phân loại: ≤2022 đã dùng nhiều vòng; 2023 adaptive development; 2024
đã xem W9, không là xác nhận mới. Kế thừa khai báo người dùng ở Git
`4d34bc4:docs/plan/week10/exposure_inventory_v2.json`: “Xác nhận kết quả
2025 chưa được dùng để lựa chọn hoặc điều chỉnh phương pháp.” Đã đối
chiếu trực tiếp nội dung Git và lưu hash trong inventory, không yêu cầu
khai báo lại nội dung đã xác nhận.

Quét **6.033 JSON** dưới `outputs` kể cả ignored và mọi JSON của 1.051 entry
retired không thấy ngày query 2025 trong các trường `as_of_date/query_date/
query_cutoff/query_cutoff_date`. Có nguồn giá/quyền 2025 đã được kiểm; không
đồng nhất việc kiểm nguồn với chạy Decision hoặc xem payoff xác nhận.
Hai thư mục tạm bị sandbox từ chối đã kiểm lại ngoài sandbox: không còn
lỗi đọc, không có JSON bổ sung. Kiểm tra này không chứng minh hoạt động
ngoài workspace, ảnh/UI, ngày lưu trong khóa khác hoặc dữ liệu đã xóa chưa
từng được xem: `unseen_outcomes_proven=false`, `confirmation_allowed=false`.
W11-06 vẫn phải cập nhật exposure trước release; không rõ independence
thì chỉ exploratory.

Hash plan/report/verification/bootstrap/publication manifest và frozen ZIP
W9 đều khớp binding [W9-06](../week9/README.md#w9-06--khóa-kết-quả-tái-lập-và-bàn-giao-21102026).
Ledger dùng chung hiện có **3.974 request**; toàn bộ **3.036 request W9**
khớp nguyên payload trong frozen ZIP. Hash ledger hiện tại khác mốc W9
vì đã dùng tiếp ở revision sau; không reset hoặc ghi đè bằng ledger W9.
Hash hiện tại `e73a87e2a45d73e76f63cdd58225c2de06b0df4e03ed09b91ad0f6f71c5c8796`.
Inventory khóa hash nguồn/raw/runtime liên quan để đối soát, không sửa
receipt hoặc gọi lại consumer toàn W9 chỉ để cập nhật checklist.

### Benchmark GPU và điều kiện thời gian

Python **3.13.5**, torch **2.11.0+cu128**, CUDA **12.8**, driver **592.15**,
RTX 5060 Laptop **8.150 MiB**, compute capability 12.0. Không đổi dependency.
Decoder proxy hai lớp/hidden128/head4/FF256, AdamW lr=3e−4, FP32, không AMP/
TF32; 275.201 tham số. Batch128, 69 token theo packing thử hai token x/y
mỗi observation và marker task; tối đa 24 prior +8 target +query. Che y
query, causal mask, loss tại chín vị trí target/query, không loss ở prior.
10 warm-up và **100 step đo** forward/backward/optimizer có CUDA synchronize:

| Phép đo | Kết quả |
| --- | ---: |
| Mean / median / P95 step | 7,625 / 7,522 / 8,377 ms |
| Peak allocated / reserved | 163,18 / 184 MiB |
| Tổng 100 step đã đo | 0,762 giây |
| Ngoại suy compute 3 seed ×10.000 step | 0,06354 giờ, khoảng 3,81 phút |
| Loss/weights hữu hạn, OOM | PASS, không OOM |

Đây chỉ là proxy shape/capacity với tensor giả preallocated, không là
simulator/oracle/tokenizer đã khóa hay tốc độ pipeline train thật. Không
gồm data loader, sinh episode, oracle, validation, checkpoint, HMM và
tích hợp/kiểm chứng. Không dùng ngoại suy này để chốt tổng thời gian hoặc
thay bằng chứng cơ chế. W10-02 khóa packing/step sau xem chi phí pipeline;
giữ trần train ba seed ≤12 giờ, không coi benchmark là chọn checkpoint.

**Quỹ thời gian đã xác nhận ngày 27/10/2026:** người dùng cho biết “Có thể
thực hiện trong 2 tuần nữa, mỗi ngày khoảng 1-2 giờ”. Quy đổi 14 ngày là
**14–28 giờ**, lấy **14 giờ** làm mức phân bổ cơ sở; 14 giờ tăng thêm chỉ
có khi thực tế dành được hai giờ/ngày. Không mặc định có thời gian máy chạy
không giám sát ngoài quỹ này. Trần train ≤12 giờ là giới hạn kỹ thuật tối đa,
không phải 12 giờ đã được dành riêng hoặc được cộng thêm vào quỹ giờ.

Để vận hành, chọn cửa sổ **28/10–10/11/2026**, bắt đầu ngày sau khi xác nhận;
10/11 là mốc kết thúc công việc dự kiến từ “hai tuần nữa”, không khẳng định
là hạn nộp chính thức của trường. W10/W11/W12 là các mốc công việc được
phân bổ trong cửa sổ này, không cộng thêm ba tuần:

| Mốc | Khoảng ngày | Quỹ cơ sở / tối đa | Điều kiện dừng |
| --- | --- | --- | --- |
| W10 còn lại | 28/10–01/11 | 5 / 10 giờ | Ưu tiên protocol, bank/tasks, oracle và kiểm cơ chế; chỉ release nếu đủ mọi gate W10-10 |
| W11 | 02/11–05/11 | 4 / 8 giờ | Chỉ development khi W10 đạt; xác nhận phải đủ gate, release và bắt đầu chậm nhất 05/11 |
| W12 hai ngày đầu | 06/11–07/11 | 2 / 4 giờ | Chỉ hoàn tất/resume run đã bắt đầu; khóa COMPLETE/INCOMPLETE/NOT_RUN cuối 07/11 |
| W12 phần còn lại | 08/11–10/11 | 3 / 6 giờ | Luận văn, tái lập và bản nộp theo bằng chứng có được; không mở run mới |
| Tổng | 14 ngày | 14 / 28 giờ | Không kéo dài để tìm kết quả thuận lợi |

**Kết luận khả thi: có điều kiện, rủi ro cao về tổng khối lượng.** GPU chạy
được backbone proxy, nhưng chưa đo pipeline thật và chưa có ước lượng đủ
cho bank/HMM/oracle, tích hợp, API, kiểm chứng và viết luận văn. Quỹ 14–28 giờ
không đủ bằng chứng để cam kết hoàn thành toàn bộ W10–W12 hoặc viết mới toàn
bộ luận văn. W10-02 được tiếp nhận để khóa protocol và phạm vi trước train;
không coi kết luận này là release train/API hoặc bỏ gate. Nếu không kịp
W10-10 hoặc nomination/release W11, ghi NOT_RUN cho thực nghiệm phụ thuộc,
giữ kết quả bất lợi/thiếu và dùng thời gian còn lại hoàn thiện luận văn.
W10-01 DONE vì đã xác định giới hạn khả thi, không vì candidate đã PASS.

### Tái lập và kiểm tra theo phạm vi

```powershell
# Tái lập toàn inventory từ nguồn thật, archive và Git; không cần key.
py -3.13 -X utf8 scripts/audit_mt_bicl_resources.py --check
# Benchmark mới phải có đường dẫn mới để giữ nguyên phép đo đã lưu.
py -3.13 -X utf8 scripts/benchmark_mt_bicl_gpu.py --output outputs/bayesian_benchmark/mt_bicl_gpu_repeat.json
py -3.13 -m py_compile scripts/audit_mt_bicl_resources.py scripts/benchmark_mt_bicl_gpu.py tests/test_mt_bicl_resource_audit.py
py -3.13 -X utf8 -m unittest discover -s tests -p test_mt_bicl_resource_audit.py -v
py -3.13 -X utf8 -m unittest discover -s tests -p 'test_execution_price*.py' -v
py -3.13 -X utf8 -m unittest discover -s tests -p test_pit_price_features_leakage.py -v
```

**Kiểm tra mới: inventory `--check` PASS; biên dịch ba file PASS; 31 test PASS,
không skip; UTF-8/JSON/liên kết/diff/hash PASS.** Chọn theo đường audit giá/quyền/PIT được dùng lại: sáu test mới
về history sớm, barrier, future append, thiếu phiên, purge năm và nhận
diện exposure; 19 test giá thực thi (gồm bảy leakage) và sáu leakage feature.
Suite dùng fixture tạm gặp PermissionError Windows trong sandbox; kiểm
lại đúng suite ngoài sandbox, không sửa test để bỏ kiểm tra. Chỉ biên dịch
ba file Python mới. Không chạy toàn suite/E2E/compileall hoặc train candidate
vì không đổi engine, đường Decision, scaler/HMM, prompt/retry hoặc dữ liệu
nguồn đã khóa. Các gate W9 là bằng chứng lịch sử, không ghi thành lượt chạy mới.
`.gitattributes` giữ nguyên byte hai JSON và LF của hai script có hash,
tránh `core.autocrlf=true` làm sai binding khi merge/checkout trên Windows.

**Lần chốt quỹ thời gian:** chỉ sửa Markdown kế hoạch/checklist, giữ nguyên
code/test/runtime, hai JSON inventory/benchmark và bằng chứng W9/ledger.
Đối soát diff, liên kết/anchor, UTF-8, số ngày/quỹ giờ và hash nguồn liên quan
**PASS**; không chạy
lại compile/unit/E2E/leakage theo AGENTS.md 1.2. Kết quả 31 test và benchmark
ở trên thuộc lượt triển khai kỹ thuật trước đó, không phải lượt chạy mới.

## W10-02 — Khóa protocol trước train, 27/10/2026

**DONE — đặc tả đã khóa, implementation/gate MT-BICL chưa nghiệm thu.**
Nhánh `docs/mt-bicl-protocol` tách từ `develop` tại `f2fcf24`. Nguồn máy đọc
là [protocol_v1.json](protocol_v1.json), SHA-256 byte
`da5cb873aa86d15ba5c0d4d50f3d65ea9da810b62b5a32b3ba819534858432fd`.
Verifier ghim hash này trong source, kiểm binding của
[simulator_v1.json](simulator_v1.json), [protocol_fixtures_v1.json](protocol_fixtures_v1.json)
và hai artifact W10-01; không chấp nhận tự sửa payload rồi self-seal.
JSON là nguồn tham số chuẩn; thay đổi phương pháp phải version mới trước
train, giữ lịch sử/exposure, không sửa v1 để hợp thức hóa kết quả.

### Phạm vi claim, dữ liệu và regime thiếu

Ba câu hỏi giữ riêng: learner học cơ chế trong simulator; dự báo thị trường
có ích; tài khoản cải thiện. Không dùng KL synthetic hoặc p để khẳng định
lợi nhuận. Theo [paper §4](https://arxiv.org/html/2606.20538v1) và
[training step của tác giả](https://raw.githubusercontent.com/martianmartina/multi-task-bayesian-icl/main/src/models/multi_task_implicit_model.py),
prior/target được phân vai và loss đặt tại target. Bản thích ứng này dùng
hai token X/Y thay input ghép x_t/y_(t−1), simulator hữu hạn và nhãn kinh tế
riêng; không tuyên bố sao chép mọi chi tiết hoặc kết quả paper.

Giữ train **2018–2020**, chọn checkpoint bằng **2021**, báo validation
**2022**, development đã xem **2023**, reference đã xem **2024** và xác nhận
có điều kiện **2025**. Không đổi split để cứu kết quả. Cycle lấy query tại
index `20+3j` của VNINDEX neo **02/01/2018**, task `symbol:blockNNNN` với
index chia nguyên 63. Query/entry/exit phải cùng block và cùng partition;
cycle cắt biên bị loại có reason, không dồn lịch hoặc bù theo nhãn.
Nhãn `int(r_net>0)` dùng helper engine; r_net dạng fraction, giữ sidecar.

Scaler cho episode train chỉ fit các feature của cycle train đã đóng
`exit<query` trên bốn mã, không dùng nhãn hoặc phần train sau query. Cuối
train fit scaler bằng các cycle train hợp lệ rồi đóng băng từ 2021; std=0
dùng scale=1, model/distance clip z vào [−4,4], giữ raw/z đầy đủ ở sidecar.
HMM train dùng prefix ở đầu block; query dùng model đầu block trên prefix
đến query. Dưới 499 phiên: **UNKNOWN/INSUFFICIENT_REGIME_HISTORY**, giữ cycle
giá hợp lệ, không coi UNKNOWN–UNKNOWN là cùng regime. Lỗi fit/integrity khác
phải dừng, không đổi thành missing. Từ 2021 dùng model cuối 2020 đóng băng;
metadata task cũ không bị gán lại bằng model học sau đầu block. Không nạp
artifact HMM cuối 2022 vào đường MT-BICL.

Prior tối đa ba block cũ cùng mã, 2–8 cycle/block; centroid dùng mọi cycle
đã đóng, rank ưu tiên regime khớp đã biết → Euclidean distance → độ mới → ID.
Cycle chọn theo distance, cutoff giảm dần rồi ID, trình bày theo thời gian.
C là tối đa tám cycle mới nhất trong current block, exit<query. ID và khoảng
entry–exit rời nhau; future candidate bị lọc trước rank, membership đã chọn
có vi phạm phải raise. Không dùng y để rank hoặc ép đủ K/m. Trước train cần
≥100 cycle và ≥4 block có hai cycle/mã, selection 2021 ≥40 cycle/mã; thiếu
thì STOP_INSUFFICIENT_TRAIN_SUPPORT, không chuyển 2022 vào train.

### Simulator, tokenizer và lịch train

Bảng 16 tâm là các dấu ±1 của bốn hệ số, bias=0. Mỗi tâm sinh bốn vector
w với nhiễu Normal(0;0,55²), PCG64 seed **20261027**; bảng 64×5 trong JSON
là nguồn chuẩn. p(λ)=1/16, p(w|λ) là softmax của khoảng cách bình phương
với τ=0,75; x là Normal(0,1) bốn chiều clip [−4,4], y Bernoulli logistic.
λ/w bị ẩn. Oracle phải cộng marginal từng prior task riêng, cập nhật λ từ C
và normalize joint một lần; không dùng shared-w pooling thay oracle.

Fixture đối chứng có hai task trái nhãn tại cùng x, C/query cố định:
p hierarchical **0,7097017325468633**, shared-w pooling **0,6128674607386324**.
Đã đối chiếu số học log-space và tuyến tính, tolerance 1e−12. Các observation
giống giá trị vẫn có ID riêng và nhân likelihood riêng. Đây là expected
fixture, chưa thay oracle production độc lập và toàn gate W10-05/07.

Tokenizer dùng sáu số `[x1,x2,x3,x4,label_value,label_missing]`, ba role
PRIOR/TARGET/QUERY. Marker `[0,0,0,0,−1,1]`; X không có y hiện tại, Y chỉ
chứa nhãn cycle đã đóng; query không có token Y. Tối đa **69 token**,
causal mask và right-padding mask; loss chỉ ở X target/query, không ở
prior, Y, marker hoặc PAD. Decoder hai lớp/hidden128/head4/FF256, ReLU,
dropout0,1, Linear numeric/role/position, Bernoulli head: **275.201 tham số**,
FP32, không AMP/TF32. Đây là một kiến trúc, không ensemble.

Ba seed **17/42/73**, AdamW lr=3e−4, weight_decay=0,01, clip grad-norm=1,
10.000 optimizer step/seed, effective batch128, synthetic:market **1:1**.
Physical batch chỉ chọn trước train bằng preflight OOM: 128/64/32 và
accumulation 1/2/4; không đổi sau xem metric. Checkpoint mỗi 1.000 step,
không early-stop theo kết quả. Seed/stream riêng cho bảng, train, sampling,
permutation, diagnostic, test và prior-swap đã ghim trong JSON. Synthetic
test/pairs có IDs 0–4999 và recipe cố định; W10-05 sinh và seal byte trước
train, không xem test để chọn checkpoint hoặc điều chỉnh tham số.

Chọn theo key `(round(macro log loss,12), round(macro Brier,12), step,
seed order)`, macro đều bốn mã trên cùng query 2021. Báo checkpoint riêng
mỗi seed và candidate chung; không chọn bằng P&L hoặc 2022. Baseline số:
Laplace base-rate train, logistic L2 C=1, learned no-prior/no-target và
finite shared-w pooling. Pooling thị trường là một baseline với giả định
mô hình, không là market Bayes ground truth hoặc ablation cùng learned
weights. Calibration cố định mười bin, giữ bin rỗng/null và bảng r_net/gain/
loss theo bin; không suy expected return hay chỉnh threshold theo kết quả.

### Ma trận và gate đã đăng ký

Giữ sáu LLM **Original/A_reference/Plain_ICL/Full_MT_BICL/No_target/Stats_only**
và **Numeric_only** offline; Full là candidate duy nhất. Model/options hiện
hành đã ghim từ plan W9; common instruction/schema triển khai W10-08 và khóa
byte W10-10 trước response mới. A giữ nguồn W9; Full−A so toàn phương pháp.
No_target giữ D/x, bỏ C và recompute p; Stats_only giữ p Full, bỏ toàn
demonstrations; Plain_ICL bỏ p, giữ cùng membership/projection Full.
LLM thấy tối đa hai exemplar/prior và hai target mới nhất; q=rint(2z),
p hiển thị ba chữ số thập phân, sidecar giữ full precision. Toàn BRPP≤600,
prompt<6.500; quá ngưỡng dừng, không cắt nhãn/legend hoặc âm thầm giảm ví dụ.

| Gate | Điều kiện đã khóa; hiện chưa phải kết quả PASS |
| --- | --- |
| Kỹ thuật/cơ chế | PIT/kinh tế/mask/JSON đúng; oracle độc lập; 5.000 synthetic test có mean KL≤0,02 nat, P95 absolute error≤0,10 |
| Thay prior | 5.000 cặp giữ C/x; ≥200 cặp có abs(Δoracle)≥0,05, dấu Δmodel khớp ≥90%; Δmodel=0 là không khớp; thiếu cặp INCONCLUSIVE, không sinh bù |
| Market validation | Báo mọi seed/baseline trên 2022, không ghi PASS cho metric bất lợi; cơ chế đạt mới đủ điều kiện kiểm giá trị context trong development |
| Support development | K≥2 và m≥2 đồng thời ≥30/60 point, ≥5/mã; thiếu INSUFFICIENT_CONTEXT, không API |
| Development/nomination | Lịch 60 point giữ nguyên trong JSON, 360 primary +252 repeat slot; đủ G, D>0, ≥3 mã tăng, Full−A≥0, mean/max ΔMDD≤2/5 đpt |
| Xác nhận | Chỉ sau nomination/exposure/giá/quyền/MDE/release; 128 point, bootstrap L=4/10.000 draw/seed20261027, CI95% primary và CI99% cho năm secondary |
| Claim kinh tế | D≥1 đpt, CI primary>0, ≥3 mã tăng, guard MDD đạt; secondary quyết định claim thành phần, không suy từ synthetic |

Upstream một lần/point, deep-copy các nhánh/repeat; shared-off chỉ khi
canonical request trùng và Original durable. Giữ wrapper retry/backoff,
checkpoint/UUID/unknown reserve và SHORT=CASH. Snapshot hash ledger W10-01
không cấm ledger sống append sau release; verifier bảo vệ từng request W9
trong frozen ZIP, run verifier sau này phải bind request của chính run đó.
Không reset ledger hoặc đổi lỗi API/integrity thành CASH. Tất cả release
train/Decision/xác nhận vẫn **false** ở khóa đặc tả này. Trần train 12 giờ
không cộng thêm vào quỹ 14–28 giờ; quá cap/lịch thì INCOMPLETE/NOT_RUN, giữ
mốc release/start 05/11 và khóa dữ liệu 07/11, không hạ gate.

### Kiểm tra và bàn giao

```powershell
py -3.13 -X utf8 scripts/verify_mt_bicl_protocol.py
py -3.13 -X utf8 -m unittest discover -s tests -p test_mt_bicl_protocol.py -v
py -3.13 -m py_compile scripts/verify_mt_bicl_protocol.py tests/test_mt_bicl_protocol.py
```

**Verifier nguồn/runtime/khóa PASS; chín test mới PASS, không skip; hai file
Python mới biên dịch PASS.** Đã kiểm bảng latent/mass, số token/tham số,
lịch/slot, fixture và đối chiếu số học pooling. 24 fixture hợp đồng và 24 ID
semantic probe là đầu vào kiểm triển khai sau, không ghi là đã chạy test
learner hoặc đã thực hiện probe LLM. Test âm kiểm đổi split/self-seal,
latent/fixture/nhãn query, code/CSV lệch hash, sửa request W9; test append
ledger hợp lệ tránh khóa nhầm lifecycle sống. `.gitattributes` giữ byte JSON
và LF script. Diff/link/anchor/UTF-8/hash **PASS**; hai JSON W10-01 và byte
ledger/bằng chứng W9 giữ nguyên.

Phạm vi này thêm đặc tả/fixture và verifier offline, không đổi đường giá/PIT/
retrieval/Decision/kinh tế hiện hữu. Vì vậy chỉ chạy suite mới và biên dịch
hai file mới; không chạy lại toàn unit/E2E/compileall hoặc suite leakage
production không đổi. Bằng chứng 31 test W10-01 và gate W9 là lịch sử,
không tính là lượt chạy mới. Không train, gọi API/LLM, sinh payoff 2023/2025
hoặc thay bằng chứng/ledger W9. **Tiếp theo W10-03**, dựng dense bank/scaler/
nhãn engine và báo support thực tế theo protocol đã khóa.

## W10-03 — Dense bank, feature và scaler PIT, 27/10/2026

**DONE — đường giá/feature/nhãn/scaler offline đã kiểm; chưa train learner.**
Nhánh `feat/mt-bicl-dense-bank` tách từ `develop` tại `cfc8906`. Thêm
`core/mt_bicl_bank.py`, `core/mt_bicl_scaler.py` và CLI
`scripts/build_mt_bicl_bank.py`; không sửa primitive đã khóa hoặc khôi phục
module của revision dừng. Dùng duy nhất bộ raw 2018–2022 đã kiểm checksum/
evidence/quyền và lịch VNINDEX; CLI chặn sinh nhãn sau 2022 hoặc ghi output
ra ngoài namespace mới. Protocol v1 và các artifact W10-01/02 giữ nguyên byte.

### Kết quả trên nguồn thật

Giữ **1.640 ứng viên**, 410/mã, query `20+3j`, block63 neo VNINDEX gốc.
**1.235 cycle AVAILABLE**, 405 EXCLUDED; không đổi ID/neo sau khi loại.
AVAILABLE ở đây yêu cầu đồng thời feature, giá thực thi, block và split hợp lệ:

| Mã | Train ≤2020 | Chọn checkpoint 2021 | Validation 2022 | Block train có ≥2 cycle | Train thiếu scaler prefix |
| --- | ---: | ---: | ---: | ---: | ---: |
| FPT | 166 | 56 | 54 | 12 | 2 |
| MWG | 182 | 59 | 64 | 12 | 2 |
| VCB | 207 | 73 | 75 | 12 | 2 |
| VNM | 176 | 60 | 63 | 12 | 2 |
| Tổng | 731 | 248 | 256 | — | 8 |

Mọi mã đạt ngưỡng giá/feature trước train: ≥100 cycle train, ≥4 block train
có hai cycle và ≥40 cycle selection. Đây **chưa phải gate K/m, regime hoặc
cơ chế**, không là bằng chứng dự báo/lợi nhuận. Metadata HMM và membership
prior/target thuộc W10-04; không dùng model cuối 2022 để lấp regime sớm.

Reason giữ riêng, có thể giao nhau: **319** cửa sổ feature vắt quyền/Reference,
**76** cycle cắt block, **26** chu kỳ giữ lệnh vắt quyền và **8** cycle cắt biên
split. Không cộng các nhóm này thành số EXCLUDED. Bank purge biên partition
2020/2021 và 2021/2022; cycle qua năm nhưng vẫn trong train 2018–2020 không
tự bị loại. Vì vậy số thật không dùng trực tiếp số thăm dò W10-01 vốn loại
mọi biên năm và chưa purge block.

Feature tính theo NumPy sliding windows; đối chiếu **toàn bộ 1.640** coverage/
reason/vector với `extract_pit_price_features`, tolerance tuyệt đối 1e−12.
Nhãn **1.531 cycle đủ điều kiện nhãn** đã đối chiếu độc lập bằng
`execution_prices_for_cycle` và `compute_round_trip_net_return`, đúng
Open(t+1)/Close(t+3), phí/slippage hai chiều. Một số cycle có nhãn nhưng
feature thiếu: giữ outcome ở sidecar, không đưa vào tập AVAILABLE hoặc fit
scaler. r_net là fraction, y=`int(r_net>0)`; không dùng Close-to-Close,
action/confidence/report hoặc gọi LLM tạo historical reports.

### Scaler và các trường hợp thiếu

Scaler prefix dùng feature của cycle train AVAILABLE với **exit<query**,
không đọc outcome. Đã lưu audit **227 ngày query train**, count/max exit,
hash tập ID và hash scaler; API `fit_scaler` trả toàn bộ fit ID/mean/variance/
scale cho episode caller. Hai query đầu **27/02 và 02/03/2018** có fit_count=0:
cycle cũ nhất đóng đúng query thứ hai nên chưa được dùng. Cả bốn mã có hai
cycle `SCALER_NO_CLOSED_HISTORY`, tổng tám; không dùng scaler tương lai để bù.
Sau gate scaler prefix còn **723 cycle train** có thể tạo episode; support
task/context thực tế vẫn phải kiểm tiếp ở W10-04.

Scaler cuối train dùng **731** cycle, cutoff **31/12/2020 inclusive**,
exit thực tế từ **02/03/2018 đến 29/12/2020**. Mean/variance ddof=0, std=0
dùng scale=1; giữ raw/z đầy đủ và model vector clip [−4,4]. Fit ID hash
`25893eaad08b599103e7f4f1121c99e237d0eb8b6c008fa3a5e617e141f83f90`.
Không refit bằng 2021/2022. Khi biến đổi prior/target quá khứ, caller truyền
ngày query episode để dùng cùng scaler; API từ chối scaler hoặc feature
vượt cutoff. Không coi auxiliary target loss là dự báo PIT độc lập ở ngày C.

### Artifact và tái lập

Artifact local [dense_bank_v1.json](../../../outputs/bayesian_benchmark/mt_bicl_v1/inputs/dense_bank_v1.json)
gồm toàn bộ ứng viên/reason, full-precision feature/outcome, frozen scaler,
prefix audit và source/code/runtime identity; **3.309.372 byte**.
SHA-256 byte: `0c2abb43dd338ce12f63213260bad241ef0c6a9e315299ed631274d06da334dc`.
Payload SHA-256 canonical: `45b93e103e390b114da5cd661e29cc52da9f4968dc2a0b01af6fa4cf29fc9681`.
Thư mục outputs này ignored; giữ cùng workspace hoặc dựng lại bằng nguồn
đã khóa và CLI. Không cần receipt JSON/Markdown riêng lặp lại README.

```powershell
# Dựng mới khi artifact chưa tồn tại; không ghi đè bằng chứng đã lưu.
py -3.13 -X utf8 scripts/build_mt_bicl_bank.py
# Cold-rebuild toàn bộ từ nguồn và đối chiếu cả payload/identity, không tin self-seal.
py -3.13 -X utf8 scripts/build_mt_bicl_bank.py --check
py -3.13 -X utf8 -m unittest discover -s tests -p 'test_mt_bicl_bank*.py' -v
py -3.13 -X utf8 -m unittest discover -s tests -p 'test_execution_price*.py' -v
py -3.13 -X utf8 -m unittest discover -s tests -p 'test_pit_price_features*.py' -v
py -3.13 -m py_compile core/mt_bicl_bank.py core/mt_bicl_scaler.py scripts/build_mt_bicl_bank.py tests/mt_bicl_bank_support.py tests/test_mt_bicl_bank.py tests/test_mt_bicl_bank_leakage.py
```

**Kiểm thử theo phạm vi: 23 test mới +19 execution price +28 PIT feature =
70 PASS**, không skip; trong đó **21 leakage** (8 mới, 7 giá, 6 feature).
Sáu file Python mới biên dịch PASS. Suite cũ dùng fixture Temp Windows được
chạy thẳng ngoài sandbox do lỗi quyền đã xác định ở W10-01/02; không bỏ test
hoặc sửa suite. Tạo artifact và **`--check` cold-rebuild toàn payload/identity
PASS**; source/W9/ledger, năm JSON khóa cũ, link/anchor/UTF-8/diff/hash PASS.
Test mới kiểm nhãn
helper, barrier/volume/missing, block/split, JSON native, scaler ddof/clip,
future append/query-label independence và lỗi PIT phải raise.

Phạm vi mới là dữ liệu bank và scaler, nên chọn đúng suite giá/feature và
leakage liên quan; không chạy toàn unit/E2E/compileall hoặc fit HMM/train/GPU/
LLM. Mọi kiểm tra này khác gate learner/cơ chế/kinh tế còn chờ W10-05–W12.
Giữ nguyên byte nguồn/W9/ledger và default Original/risk OFF. **Tiếp theo
W10-04**: task metadata, prior/target/query rời nhau, streaming và projection.

## W10-04 — Task/context, streaming và projection, 27/10/2026

**DONE — đầu vào task/context đã kiểm, chưa có learner hoặc response LLM.**
Nhánh `feat/mt-bicl-task-context` tách từ `develop` tại `cb9fffe`; lần hoàn
thiện tiếp tục trên nhánh này sau ngắt, không tạo lại bank W10-03. Thêm
`mt_bicl_regimes/stream/tasks/context` và CLI `build_mt_bicl_tasks.py`;
giữ nguyên protocol v1, primitive và toàn bộ bằng chứng cũ.

### Metadata và membership

Task theo mã/block63; metadata regime nằm ở đầu block. Block 0–7 chưa đủ
499 phiên, giữ **UNKNOWN/INSUFFICIENT_REGIME_HISTORY**, không gán ngược bằng
artifact cuối 2022. Bốn model prefix train và một model cuối 2020 được fit
trong namespace mới, dùng nguyên tham số/calibration của primitive:

| Cutoff fit | Số phiên prefix | Phương pháp phân loại đã kiểm |
| --- | ---: | --- |
| 08/01/2020 | 505 | HMM |
| 14/04/2020 | 568 | MULTI_FACTOR theo fallback đã khóa |
| 14/07/2020 | 631 | MULTI_FACTOR theo fallback đã khóa |
| 12/10/2020 | 694 | HMM |
| 31/12/2020 | 752 | HMM, đóng băng cho query từ 2021 |

Cache model dùng một CPU thread khi dựng/kiểm lại, không đổi dependency hoặc
HMM parameters. Metadata task cũ không bị ghi lại bằng model mới. Hash tham
số/model/scaler/calibration phải giữ nguyên qua inference; lỗi fit khác
thiếu lịch sử phải raise. Scaler cuối 2020 chỉ được tính khi bắt đầu query
từ 2021, không đọc feature train tương lai khi dựng query train sớm.

Builder chỉ nhận nhãn qua `MarketStream`, lọc **exit<query** trước rank.
Prior tối đa ba task trước target cùng mã, mỗi task 2–8 cycle; centroid tính
trên mọi cycle hợp lệ đã đóng của task. Rank ưu tiên regime khớp đã biết,
distance, độ mới và ID; không đọc y để chọn. Target là tám cycle mới nhất
trong đúng block hiện tại. Query không chứa y/outcome. Validator từ chối
trùng ID, sai mã/block, future membership/model/scaler hoặc giao khoảng
entry–exit; giữ K=0/m=0 hợp lệ và reason, không áp lại trần tuổi 730 ngày.

### Streaming và coverage nguồn thật

Stream giữ bank W10-03 nguyên vẹn, nối cycle trực tiếp từ raw OOS đã kiểm
khi **exit<query**. Không có API nhận nhãn từ report/evaluation caller.
Query cùng ngày dùng chung view; tiến thời gian idempotent, lùi thời gian
phải tạo replay mới. Replay incremental và cold replay khớp trong test;
disk checkpoint/unknown/retry thuộc W10-08. Nguồn stream hiện mở đến 2024,
chặn query 2025 cho tới khi có nguồn/release riêng.

Đã dựng **1.235 query bank** với split riêng: train 731 (723 AVAILABLE,
tám thiếu scaler prefix giữ reason), selection 248 và validation 256.
Gate development không được áp nhầm cho các partition bank: ở đó ghi
NOT_APPLICABLE. Có 96 metadata task, 228 scaler được dedupe theo hash và
405 lượt audit view. Toàn bộ **324 feature/303 nhãn streaming mới** đã đối
chiếu với primitive PIT và helper thực thi/kinh tế; không sinh y query
development hoặc payoff 2025.

| Mã | Point giữ nguyên | Feature/scaler AVAILABLE | Đồng thời K≥2, m≥2 | Thiếu feature do quyền/Reference |
| --- | ---: | ---: | ---: | ---: |
| FPT | 12 | 7 | 6 | 5 |
| MWG | 16 | 15 | 12 | 1 |
| VCB | 16 | 15 | 12 | 1 |
| VNM | 16 | 13 | 11 | 3 |
| Tổng | 60 | 49 | 41 | 11 |

**Gate support PASS:** 41≥30, từng mã ≥5. Giữ đủ 60 point, cả 11 trường hợp
UNAVAILABLE và các nhóm cold-start/m nhỏ; không bỏ điểm để tăng mẫu số sẵn
sàng. Strata K/m theo mã, regime và quý nằm trong artifact. Đây chỉ là
support đầu vào, không là gate cơ chế, kết quả dự báo/kinh tế hoặc release
development; dry-run tích hợp và 24 semantic probe còn thuộc W10-09.

### Packing/projection và artifact

Packing khớp fixture chín token đã khóa và case đủ ba task/tám target
**69 token**: marker phân task, causal-mask contract, query Y chỉ là nhãn
loss bên ngoài input. Label C/Y không đi vào vị trí X tương ứng. Mask thực
trên learner và gate synthetic vẫn chờ W10-05–07. No_target bỏ đúng C,
giữ D/x và yêu cầu caller recompute p; Plain bỏ p, Stats bỏ demonstrations.

LLM projection giữ tối đa hai exemplar/prior và hai target mới nhất, đủ
legend/q/nhãn; sidecar giữ precision/ID/membership. Prefix thực tế dài tối
đa **246 ký tự** với **p=NA**, chỉ là fixture chưa có learner inference.
Test worst-case vẫn giữ đủ tám exemplar dưới 600 ký tự; prompt 6.499 được
nhận, 6.500 bị từ chối. Kiểm prompt đầy đủ qua Decision/distill/cap và
canonical shared-off thực tế vẫn thuộc W10-08, không tính đã tích hợp ở đây.

Artifact local [task_context_v1.json](../../../outputs/bayesian_benchmark/mt_bicl_v1/inputs/task_context_v1.json),
**68.037.981 byte**, SHA-256 byte
`4fca2146fbc03f4f74762a5a6b4d44c184b4b4244c3cb28d5dfda68d93fa0c57`;
payload canonical `4bc67ca7843b61928a0ed67b18b845777c2ec42ad5f01d76e2bfbe7f8080a4f7`.
Artifact chứa model prefix mới, metadata/scaler/ID, episode/packing/fixture,
split và supervised query target tách khỏi input, coverage và stream audit.
Development không có supervised query target; mọi flag train/Decision vẫn
false. Outputs ignored: giữ cùng workspace hoặc dựng lại offline; không
thêm receipt task rời chỉ lặp lại báo cáo này.

```powershell
# Chỉ tạo mới khi chưa có artifact; không ghi đè bằng chứng đã lưu.
py -3.13 -X utf8 scripts/build_mt_bicl_tasks.py
# Cold-rebuild cả bank nguồn, HMM/task/context/stream và so toàn payload/identity.
py -3.13 -X utf8 scripts/build_mt_bicl_tasks.py --check
py -3.13 -X utf8 -m unittest discover -s tests -p 'test_mt_bicl_tasks*.py' -v
py -3.13 -X utf8 -m unittest discover -s tests -p 'test_mt_bicl_bank*.py' -v
py -3.13 -X utf8 -m unittest discover -s tests -p test_regime_model.py -v
py -3.13 -X utf8 -m unittest discover -s tests -p test_regime_leakage.py -v
py -3.13 -m py_compile core/mt_bicl_regimes.py core/mt_bicl_stream.py core/mt_bicl_tasks.py core/mt_bicl_context.py scripts/build_mt_bicl_tasks.py tests/mt_bicl_tasks_support.py tests/test_mt_bicl_tasks.py tests/test_mt_bicl_tasks_leakage.py
```

**Kiểm tra theo phạm vi W10-04: 27 test mới +23 bank/scaler +6 model regime
+8 regime leakage = 64 PASS**, trong đó **29 leakage**; tám file Python mới
biên dịch PASS. Lần hoàn thiện xác nhận lại 27 test và compile; 37 test hồi
quy đã PASS trong cùng lượt W10-04 trước ngắt trên source/runtime giữ nguyên,
không ghi là vừa chạy lại. Suite regime dùng Temp Windows chạy ngoài sandbox
theo lỗi quyền đã xác định. Không chạy toàn unit/E2E/compileall hoặc gọi
LLM; chỉ chọn đường giá/scaler/HMM/retrieval/mask/projection bị tác động.
**Cold-rebuild toàn payload/identity PASS**; diff/link/anchor/UTF-8/hash PASS.
Năm JSON khóa, bank W10-03, primitive, W9 và ledger giữ nguyên byte.
Joblib có traceback dò CPU qua WMIC trong sandbox; lệnh vẫn exit 0 và kết
quả model/context cold-rebuild khớp, không đổi dependency để bỏ cảnh báo.
**Tiếp theo
W10-05**: simulator/oracle độc lập và control không pooling; chưa train learner.

## W10-05 — Simulator, oracle độc lập và batch preflight, 27/10/2026

**DONE — oracle hữu hạn đã kiểm độc lập; chưa có learner hoặc kết quả cơ chế
của learner.** Nhánh `feat/mt-bicl-simulator-oracle` tách từ `develop` tại
`f41fd6b`. Giữ nguyên byte protocol, coefficient table, fixture và toàn bộ
nguồn/bằng chứng đã khóa; không gọi LLM/API hoặc chạy optimizer.

### Simulator và hai cách tính Bayes

Simulator đọc đúng bảng 16 λ/64 w và seed W10-02; mỗi prior task có w_k
riêng, target có w_* riêng dưới cùng λ. K=0..3, m=0..8, n_k=2..8 và thứ tự
draw x/y đúng recipe. PCG64/SeedSequence địa chỉ hóa bằng stream/model seed/
episode ID, cho random-access/resume; train chỉ seed 17/42/73, các corpus
test/diagnostic/preflight dùng model_seed=0. Latent và nhãn query ở sidecar,
schema predictor chỉ nhận prior/target/query; ID trùng bị từ chối, cùng x/y
với ID khác nhau vẫn tạo các likelihood factor riêng.

`FiniteBayesOracle` dùng NumPy/log-space, marginal từng w_k rồi chuẩn hóa
joint (λ,w_*) đúng một lần; C cập nhật cả λ. `EnumerationOracle` tự tính
p(w|λ), likelihood và chuẩn hóa bằng vòng lặp scalar/math.fsum, không dùng
matrix hoặc kernel likelihood của oracle chính. Cách tham chiếu liệt kê
λ/w_* và marginal w_k riêng theo từng task; không duyệt tích Descartes
khổng lồ của mọi w_k khi K=3. Một test độc lập khác duyệt **đủ 65.536
cấu hình latent (λ,w₁,w*)** cho K=1 và khớp oracle.

Control shared-w pooling dùng p(w)=Σλp(λ)p(w|λ), cập nhật chung bằng D+C.
Fixture khóa cho **hierarchical p=0,7097017325468643**, pooled
**p=0,6128674607386324**, khớp tolerance 10⁻¹². Đổi thứ tự task không đổi
oracle; chia lại cùng observation giữa task có thể đổi hierarchical p,
trong khi pooling giữ nguyên. Đây là phép kiểm ranh giới task trên
simulator, không là ground truth hoặc kết quả hiệu quả thị trường.

### Corpus cố định và dữ liệu preflight

Khóa đúng **5.000 synthetic test**, ID 0..4999, cùng **5.000 cặp thay prior**,
pair ID 0..4999, theo stream đã đăng ký. Mỗi cặp giữ nguyên C/x/ID target,
chỉ thay prior A→B; nhãn query chung nằm ngoài input. Đã so **20.002 dự báo**
độc lập: hierarchical và pooled trên mọi test, hai phía mọi cặp, hai control.
Sai khác lớn nhất p **5,629×10⁻¹⁴**, log p₁ **7,794×10⁻¹⁴**, log p₀
**7,669×10⁻¹⁴**, đều dưới 10⁻¹². K test 0/1/2/3 lần lượt
1.196/1.297/1.276/1.231; m=0 có 539 episode, đủ mọi m đến 8.

Có **3.740/5.000 cặp** thỏa |Δoracle|≥0,05, vượt tối thiểu 200:
**support SUFFICIENT**, không sinh bù hoặc đổi ngưỡng. Learner chưa được
đối chiếu KL/P95/sign agreement: `learner_mechanism_status=NOT_RUN_NO_MODEL`.
Không dùng corpus này để chọn checkpoint/seed hoặc tối ưu learner.

`TrainingBatchSource` cấp effective batch128, interleave **64 synthetic +64
market**; ID=64×step+i, synthetic train/preflight có stream riêng. Market
uniform mã rồi query train hợp lệ, không dùng y/r_net để sampling; tập thật
có FPT164/MWG180/VCB205/VNM174, tổng **723** query. Drop K giữ top K, drop m
giữ m mới nhất, m=0 bỏ hết C; prior permutation dùng stream riêng với domain
0 synthetic/1 market, target giữ thứ tự. Numeric packing hai miền khớp cùng
hợp đồng tối đa 69 token, query y chỉ ở external loss label.

Đã dựng và băm **100 batch preflight dữ liệu thật**, lưu hash từng step và
batch đầu. Trạng thái `DATA_PREPARED_OPTIMIZER_NOT_RUN`: chưa đo 100 optimizer
step với learner/GPU hoặc kiểm mask thực trên mô hình. W10-06 phải làm
preflight đó, bỏ weights preflight và kiểm cap 12 giờ trước train ba seed.
Không coi proxy W10-01 hoặc chuẩn bị dữ liệu ở đây là phép đo pipeline train.

### Artifact và kiểm tra theo phạm vi

Artifact local [synthetic_oracle_v1.json](../../../outputs/bayesian_benchmark/mt_bicl_v1/inputs/synthetic_oracle_v1.json),
**76.993.897 byte**, SHA-256 byte
`9f82873fc054788ba6bcc97c79edec4388bcda2c66c097ac763d8000ed2c1f66`;
payload canonical `99ece910145e395a712bf897582744d7d232cd83431c73f6c17caf3d03cfce82`.
Gồm input/sidecar/oracle/control, corpus test/cặp, identity nguồn/runtime,
thống kê và batch preflight. Outputs ignored, có CLI dựng lại; không thêm
receipt Markdown riêng. CLI từ chối ghi đè; `--check` cold-rebuild so toàn
payload/identity, không tự cập nhật checksum để nhận nguồn đã đổi.

```powershell
# Chỉ tạo mới khi chưa có artifact.
py -3.13 -X utf8 scripts/prepare_mt_bicl_oracle.py
py -3.13 -X utf8 scripts/prepare_mt_bicl_oracle.py --check
py -3.13 -X utf8 -m unittest discover -s tests -p 'test_mt_bicl_oracle*.py' -v
py -3.13 -X utf8 -m unittest discover -s tests -p 'test_mt_bicl_tasks*.py' -v
py -3.13 -X utf8 -m unittest discover -s tests -p test_mt_bicl_protocol.py -v
py -3.13 -m py_compile core/mt_bicl_simulator.py core/mt_bicl_oracle.py core/mt_bicl_oracle_reference.py core/mt_bicl_batches.py scripts/prepare_mt_bicl_oracle.py tests/test_mt_bicl_oracle.py tests/test_mt_bicl_oracle_leakage.py
```

**28 test mới +27 task/context +9 protocol =64 PASS**, gồm **26 leakage**.
Sau đổi fixture batch sang dữ liệu PIT tự dựng đã chạy lại đúng 28 test mới;
36 test hồi quy PASS ở cùng lượt task, source/runtime không đổi. Unit test
không phụ thuộc artifact ignored; CLI kiểm riêng byte artifact thật và mã
dựng nó. Bảy file Python mới biên dịch PASS. Chọn phạm vi oracle/sampling/
packing/PIT và hợp đồng protocol; không sửa engine, scaler, HMM hoặc adapter,
không chạy toàn suite/E2E/compileall. **Cold-rebuild corpus/identity PASS**;
diff/link/UTF-8/hash PASS. Năm JSON khóa, bank/task-context cũ, nguồn W9 và
ledger giữ nguyên byte. **Tiếp theo W10-06:** learner/mask, preflight thật,
train ba seed và chọn checkpoint bằng 2021; chưa release development.

## W10-06 — Learner, train/resume và seal, 27/10/2026

**DONE — nghiệm thu ngày 28/10/2026: preflight GPU, ba seed đủ step và
seal/verify PASS.** Kết quả cơ chế/validation 2022 còn thuộc W10-07.
Nhánh `feat/mt-bicl-learner-training` tách từ `develop` tại `46bd5bc`.
Mã merge tại `6642fbc`; người dùng đã chạy GPU và seal trong workspace.
Nghiệm thu chỉ cập nhật tài liệu, giữ nguyên code/runtime/input và artifact
training đã khóa. W10 hiện **6/10 DONE**.

### Mã đã triển khai và kiểm tra

`MTBiCLLearner`: hai lớp causal, hidden128/4 heads/FF256, **275.201 tham số**,
FP32, dropout0,1; không AMP/TF32. Pad phải đến 69, mask tương lai và key padding
trên model thật. BCEWithLogits mean tại X target/query của từng episode rồi
mean effective batch128; prior/Y/marker/PAD không có loss. Microbatch chia
liên tiếp, accumulation giữ đúng mean trước clip norm1 và AdamW đã khóa.

CLI tái dùng nguyên sampler W10-05: 64 synthetic +64 market/step, train chỉ
**723 query ≤2020**, selection **248 query năm 2021**, không tối ưu trên
corpus test hoặc 2022. Checkpoint mỗi 1.000 step, đủ 10 checkpoint/seed,
**10.000 optimizer step cho từng seed 17→42→73**; không early stopping bằng
metric. Chọn checkpoint riêng mỗi seed và candidate chung theo macro log
loss đều mã, Brier tie-break, step tăng dần, thứ tự seed đã khóa; không P&L.

Preflight production đo 100 optimizer step gồm data generation/packing và
forward/backward, đo thêm selection/checkpoint I/O, bỏ toàn bộ weights.
Chỉ CUDA OOM trước train cho phép chuyển physical batch128→64→32, accumulation
1→2→4; giữ một physical batch cho cả ba seed/resume. Dự toán dùng P95 thời
gian step, chi phí selection/checkpoint/replay seal và dự phòng 25%; vượt cap/
lịch thì `INCOMPLETE_NO_CANDIDATE`. Đây là policy kiểm quỹ giờ, không đổi model,
ngưỡng khoa học hoặc số step đã đăng ký.

Source/runtime/input hash và GPU được đối soát khi chạy. Checkpoint gồm model,
optimizer, step và RNG Python/NumPy/torch/CUDA, load bằng `weights_only=True`.
Resume snapshot ghi file mới trước đổi pointer atomic; mốc 1.000 step bất biến,
checkpoint orphan phải khớp toàn state replay mới được dùng. Resume tự động
lưu mỗi 100 step và tại pause. Khóa OS ngăn hai writer; không cần xóa file lock
để resume. `seal` kiểm đủ ba seed/30 mốc và **replay cả 30 checkpoint trên 2021**
trước chọn/export model; sửa dự báo rồi tự rehash JSON không vượt được replay.
`verify` đối soát lại hash/index/nhãn/metrics/weights, không chạy lại optimizer.
Candidate giữ `mechanism_status=NOT_RUN`, `development_allowed=false`; W10-07
còn phải kiểm cơ chế và báo validation 2022 trước các bước tích hợp.

**Kiểm tra theo phạm vi: 28 test mới +28 oracle/sampler +27 task/context +9
protocol +8 atomic I/O +6 OS lock =106 PASS**, gồm **37 test trong các suite
leakage**. Đã kiểm causal bằng tác động lên logit, gradient đúng vị trí,
accumulation, resume bit-identical có dropout/AdamW/RNG, pause/resume, cap,
hash/path và transaction lỗi. Một test điều phối đủ 30.000 bước bằng **mock
optimizer/source trên CPU**, tạo fixture 30 checkpoint rồi kiểm replay/seal;
fallback CUDA OOM cũng dùng mock. Chúng không phải train/preflight GPU thật.
Bảy file Python mới biên dịch PASS. CLI `check-inputs` trên artifact thật PASS;
nguồn/runtime/ba artifact/W9 được đối soát. Không sửa code cũ hoặc dependency,
không chạy toàn unit/E2E/compileall, không LLM/API. Suite I/O/OS lock chạy ngoài
sandbox do hạn chế Windows Temp đã xác định. Năm JSON khóa, ba input artifact
và ledger giữ nguyên byte; chưa có output production `training_v1/` ở lúc bàn giao.
Khối PowerShell bên dưới đã kiểm cú pháp, truyền tham số, thứ tự và dừng khi
lỗi/pause bằng `py` mock; không dùng phép kiểm lệnh đó để gọi GPU thật.

### Lệnh PowerShell đã dùng từ đầu đến cuối

Chạy tại máy có Python 3.13.5/CUDA/runtime đã khóa; không cần cài lại dependency.
Các input W10-03–05 đã có trong workspace hiện tại. Chạy tuần tự, hàm wrapper
dừng chuỗi khi có lỗi hoặc pause, không chuyển sang seed kế tiếp khi chưa đủ step.
Run hiện đã nghiệm thu; dùng `py -3.13 -X utf8 scripts/train_mt_bicl.py verify`
để đối soát lại artifact. Khối dưới lưu quy trình đã dùng trước khi đóng băng.

```powershell
Set-Location -LiteralPath 'C:\Users\Legion\OneDrive\Tài liệu\GitHub\A-Multi-Agent-Large-Language-Model-Approach-to-Price-Driven-Stock-Trading-in-the-Vietnamese-Stock-Ma'
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$env:CUBLAS_WORKSPACE_CONFIG = ':4096:8'

function Invoke-MtBicl {
    py -3.13 -X utf8 scripts/train_mt_bicl.py @args
    if ($LASTEXITCODE -ne 0) {
        throw "MT-BICL dừng với mã $LASTEXITCODE; kiểm thông báo trước khi tiếp tục."
    }
}

Invoke-MtBicl check-inputs
Invoke-MtBicl preflight
Invoke-MtBicl train --seed 17 --resume
Invoke-MtBicl train --seed 42 --resume
Invoke-MtBicl train --seed 73 --resume
Invoke-MtBicl seal
Invoke-MtBicl verify
```

`--resume` dùng được từ lượt đầu; seed đã COMPLETE được kiểm và bỏ qua, không
train lại. Preflight đã PASS cùng identity được tái dùng. Có thể chạy từng
dòng train vào các phiên khác nhau; mỗi seed phải COMPLETE trước seed kế tiếp.
Muốn tạm dừng: **Ctrl+C một lần, đợi thông báo đã pause/lưu checkpoint**; mã
thoát **3** là pause, **1** là lỗi và **0** là hoàn thành bước. Chạy lại phần
setup/hàm ở terminal mới rồi cùng dòng `train --seed ... --resume`.

Nếu chỉ muốn chạy tối đa 90 phút một phiên, thay dòng train của seed đang làm bằng:

```powershell
Invoke-MtBicl train --seed 17 --resume --session-minutes 90
```

Đổi `17` thành seed đang chạy; lặp cùng dòng đến khi đủ 10.000 step. Pause
không đổi số step hoặc chọn checkpoint theo kết quả. Tổng **12 giờ active dùng
chung** gồm preflight, generation, train, selection/checkpoint và seal replay;
pause sạch không tính thời gian nghỉ. Nếu tiến trình chết cứng/đóng terminal,
khoảng từ session chưa đóng đến phục hồi được tính bảo thủ vào cap vì không
xác định được thời điểm chết; ưu tiên Ctrl+C/pause tự động. Hết cap/lịch giữ
INCOMPLETE, không xóa state để chạy lại hoặc tự giảm kiến trúc/step.

Đầu ra ignored tại `outputs/bayesian_benchmark/mt_bicl_v1/training_v1/`:
`preflight.json`, `state.json`, `seed17/`, `seed42/`, `seed73/`,
`candidate_v1.json` và weights export. Kết quả nghiệm thu/hash thật ở dưới;
learner chưa được tuyên bố đạt gate cơ chế.

### Nghiệm thu artifact thật, 28/10/2026

**PASS trong phạm vi W10-06.** Đã chạy lại đúng CLI `verify`, exit 0:
source/runtime/input, 30 checkpoint/30 file selection, ba resume cuối,
tập ID/nhãn 2021, macro metric/tie-break và weights export đều khớp.
`state=SEALED_TRAINING_ONLY`, cả ba seed `COMPLETE`, session đã đóng.
Kiểm tra bổ sung trực tiếp **30 checkpoint**: weights FP32/275.201 tham số,
30 optimizer parameter-state với counter đúng mốc 1.000…10.000, CUDA RNG
một GPU. Mỗi seed đã thực hiện đủ 10.000 optimizer step dù checkpoint được
chọn có thể sớm hơn; resume cuối khớp toàn bộ model/optimizer/RNG mốc 10.000.

Preflight thật **100 step PASS** trên **RTX 5060 Laptop GPU/CUDA12.8**,
physical/effective batch **128/128**, accumulation1, không OOM hoặc đổi batch.
Mean **0,194152 giây/step**, P95 **0,203230 giây/step**, peak allocated
**231,996 MiB**, weights preflight không giữ lại. Tổng wall time active đã
ghi nhận **11.821,577 giây ≈3 giờ 17 phút**, gồm preflight/train/selection/
checkpoint/seal, dưới trần chung 12 giờ. Không train thêm hoặc chạy lại
preflight trong lượt nghiệm thu này.

Selection gồm **248 query năm 2021**: FPT56/MWG59/VCB73/VNM60, cùng tập cho
mọi checkpoint/seed; train giữ **723 query ≤2020**. Bảng dưới là kết quả
chọn checkpoint bằng 2021, chưa phải báo cáo validation 2022 hoặc lợi nhuận.

| Seed | Step đã train | Checkpoint tốt nhất theo 2021 | Macro log loss | Macro Brier |
| --- | ---: | ---: | ---: | ---: |
| 17 | 10.000 | 1.000 | 0,677123565515 | 0,241949247453 |
| **42** | **10.000** | **1.000 — candidate chung** | **0,667663202309** | **0,237225674654** |
| 73 | 10.000 | 2.000 | 0,688423335712 | 0,247448530732 |

Seal hiện hữu ghi nhận replay **đủ 30 checkpoint trên 2021** trước export.
Nghiệm thu đối soát seal/hash/identity trên source/runtime nguyên vẹn và các
counter/tensor nêu trên; không chạy lại replay GPU hoặc suy diễn rằng vừa
train lại. Identity canonical của training:
`82e56fc3bb865282b5c790fb97700df482aa6e4fceff2cf8904c19469a6581a3`.

SHA-256 byte của các artifact chính trong
`outputs/bayesian_benchmark/mt_bicl_v1/training_v1/`:

| Artifact | Byte | SHA-256 |
| --- | ---: | --- |
| [preflight.json](../../../outputs/bayesian_benchmark/mt_bicl_v1/training_v1/preflight.json) | 6.509 | `31be2d8e2f8e2dea9fcfe2f10e9481e59ad753313f8fedbfea17b83335606a67` |
| [state.json](../../../outputs/bayesian_benchmark/mt_bicl_v1/training_v1/state.json) | 51.924 | `1764965dd94b71a35f024e78f1b2edd9a3bf74653a1d017efaa0444b381db927` |
| [candidate_v1.json](../../../outputs/bayesian_benchmark/mt_bicl_v1/training_v1/candidate_v1.json) | 47.158 | `3f963fb7e4fa0e70311b78b40c4ac91a2e329b4c1c518825157e38736a4613fa` |
| [seed42/checkpoint-01000.pt](../../../outputs/bayesian_benchmark/mt_bicl_v1/training_v1/seed42/checkpoint-01000.pt) | 3.353.353 | `701898d560ff8f78d09ee12a4c1ea9de5f4ead093205882d54826dcfe80fdb69` |
| [candidate-0f2975ed61c94b34ad31ef7c82a56e7e.pt](../../../outputs/bayesian_benchmark/mt_bicl_v1/training_v1/candidate-0f2975ed61c94b34ad31ef7c82a56e7e.pt) | 1.111.305 | `c6c2864a9a6e2bdf54fa79554b1b337a080889fc3bad0a5db7335c865c3e002a` |

Đã băm/đối soát **67 file chứng cứ được manifest tham chiếu**, tổng
**113.212.584 byte**; giữ nguyên byte trước/sau nghiệm thu. Metadata khóa OS
là nhật ký vận hành, không thuộc 67 file đóng băng. Năm JSON đặc tả, ba input
bank/context/oracle, bằng chứng W9 và ledger dùng chung cũng giữ nguyên.

Theo AGENTS.md 1.2, lượt này chỉ sửa tài liệu và phân tích artifact: **không
chạy lại unit/leakage/E2E/compileall hoặc biên dịch Python**. Viện dẫn đúng
**106 test PASS, 37 leakage** đã kiểm ở lượt triển khai, trên source/runtime
khớp identity; không gọi là kết quả vừa chạy lại. CLI verifier lần đầu bị
sandbox chặn đọc boot Windows; chạy lại đúng lệnh ngoài sandbox đã PASS,
không thay code, dependency hoặc artifact để vượt kiểm tra.

Sau nghiệm thu training, W10-07 kiểm KL/P95/prior-swap và validation 2022.
Seal training giữ nguyên `mechanism_status=NOT_RUN`, `development_allowed=false`
tại thời điểm khóa; kết quả đánh giá sau đó ở mục W10-07 bên dưới. Nghiệm thu
training không đồng nghĩa đạt cơ chế hoặc được phát hành development/Decision LLM.

## W10-07 — Mechanism gate và validation, 28/10/2026

**DONE — nghiệm thu đánh giá/replay/integrity ngày 28/10/2026; gate cơ chế
FAIL, NO_MT_BICL_RELEASE.** Hoàn thành task đánh giá không có nghĩa learner
đạt cơ chế. W10 hiện **7/10 DONE**, W10-08–10 bị chặn cho candidate này.
Nhánh `feat/mt-bicl-mechanism-validation` từ `develop`
tại `a13ef1d`; giữ nguyên byte trainer/model, protocol, corpus và 67 artifact
training đã nghiệm thu; mã evaluator merge tại `2203048`. Không train thêm
hoặc dùng kết quả test để sửa mô hình/ngưỡng trong lượt nghiệm thu.

Evaluator giữ candidate **seed42 step1000**, đồng thời báo seed17 step1000
và seed73 step2000 theo selection 2021. Mỗi seed đọc đúng 5.000 synthetic
test và 5.000 cặp đã khóa; không chọn lại seed/checkpoint theo synthetic/2022.
Tính float64 Bernoulli **KL oracle||model từ log probabilities ổn định**,
không clip; P95 dùng `numpy.quantile(.95, method='linear')`. Gate giữ mean
KL≤0,02 nat, P95 absolute error≤0,10. Prior-swap giữ C/x/ID target, denominator
theo |Δoracle|≥0,05 (corpus có 3.740 cặp), cần ≥200 và sign agreement≥90%.
Đổi denominator bị từ chối; delta model=0 không tính đúng dấu oracle khác 0.
Control pooling báo model/oracle/pooled và khoảng cách, không thêm threshold
để phát hành ngoài protocol. Báo support/error theo K/m cả cold-start.

Validation chung **256 query năm 2022**, frozen scaler/HMM, PIT exit<query;
giữ coverage/exclusion reasons của bank. Full/No_prior/No_target dùng cùng
weights của từng seed; bỏ đúng component rồi tính lại p. Base rate Laplace
và logistic fit **731 cycle train hợp lệ** bằng scaler cuối 2020; khác với
**723 query learner** vì tám cycle thiếu scaler historical-prefix vẫn dùng
được khi fit baseline với scaler cuối train. Công bố đủ fit IDs/scaler hash/
coef/intercept, không dùng label validation để fit. Logistic không hội tụ
phải báo lỗi, chỉ single-class train được dùng hằng Laplace đã đăng ký.
Naive pooling dùng finite shared-w simulator, không là ground truth thị trường.

Report giữ raw logits, macro/per-symbol Brier/log loss, calibration **10 bin
[left,right), bin cuối gồm 1**, cả bin trống count0/null; K/m marginal/joint
support, runtime, r_net đầy đủ theo p-bin, mean gain/loss và toàn bộ danh sách
cycle thắng/thua đã sắp theo mức gain/loss. r_net là fraction, p không là ER.
Clip chỉ log loss thị trường ở [10⁻⁶,1−10⁻⁶], không clip KL hoặc calibration.
So Full với từng baseline bằng delta hai metric; kết quả bất lợi giữ
`WORSE_BOTH`/`MIXED_OR_TIE`, không ghi market performance PASS từ việc đã có report.
2022 đã có exposure nên không gọi là holdout độc lập.

Inference dùng `eval`/`inference_mode`, che nhãn query, không optimizer; băm
tensor và kiểm gradient trước/sau. Journal riêng theo baseline/seed, atomic
và OS lock; Ctrl+C chờ hết stage rồi lưu, resume bỏ qua stage đã khớp hash.
Verifier tính lại metric từ raw logits; `--replay` dựng lại baseline bằng
chính train và replay inference từ checkpoint đã khóa để đối chiếu raw logits,
không update learner. Receipt `replay_verification.json` gắn hash index/report/
source/GPU; không sửa seal hoặc budget training cũ.

**Kiểm tra theo phạm vi: 16 test mới +60 hồi quy =76 PASS**, gồm **49 test
trong các suite leakage**. Hồi quy gồm 11 model/causal, 28 oracle/sampler,
13 task leakage và 8 bank/scaler leakage. Test mới dùng fixture tự dựng:
KL cực trị không bị clipping, P95, denominator/zero delta, calibration/r_net,
không chọn lại candidate, baseline train-only/single-class/convergence,
query-label/future/duplicate, frozen inference và journal/replay chặn tự rehash
dự báo sai. Năm file Python mới biên dịch PASS. CLI `check-inputs` trên receipt/
corpus/task-context thật PASS; chưa fit baseline hoặc inference trên test/
validation thật. Không sửa dependency, chạy toàn suite/E2E/compileall hoặc
gọi LLM/API. Test journal Windows Temp chạy ngoài sandbox theo hạn chế quyền
đã xác định; mọi kết quả test CPU không thay kết quả mechanism GPU thật.
Đối soát đủ 67 file training, source trainer, đặc tả và ledger: giữ nguyên
so với nghiệm thu W10-06. Khối PowerShell bên dưới đã kiểm cú pháp/tham số/
thứ tự/dừng khi pause bằng `py` mock, không gọi GPU để kiểm khối lệnh.

### Lệnh PowerShell đánh giá đã dùng từ đầu đến cuối

Chạy cùng runtime/GPU đã dùng train, không chạy lại các lệnh preflight/train/
seal của W10-06. Các lệnh dưới chỉ tạo namespace `evaluation_v1/` mới.
Run đã nghiệm thu; lệnh đối soát hiện tại là
`py -3.13 -X utf8 scripts/evaluate_mt_bicl.py verify`. Khối dưới lưu quy trình
đã dùng, gồm replay GPU đã hoàn tất và có receipt.

```powershell
Set-Location -LiteralPath 'C:\Users\Legion\OneDrive\Tài liệu\GitHub\A-Multi-Agent-Large-Language-Model-Approach-to-Price-Driven-Stock-Trading-in-the-Vietnamese-Stock-Ma'
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$env:CUBLAS_WORKSPACE_CONFIG = ':4096:8'

function Invoke-MtBiclEval {
    py -3.13 -X utf8 scripts/evaluate_mt_bicl.py @args
    if ($LASTEXITCODE -ne 0) {
        throw "Đánh giá dừng với mã $LASTEXITCODE; kiểm thông báo trước khi tiếp tục."
    }
}

Invoke-MtBiclEval check-inputs
Invoke-MtBiclEval run --resume
Invoke-MtBiclEval verify --replay
```

Muốn pause, Ctrl+C một lần và đợi stage được lưu; mã thoát3. Trong terminal
mới chạy lại setup/hàm rồi `Invoke-MtBiclEval run --resume`, cuối cùng
`Invoke-MtBiclEval verify --replay`. Mã1 là lỗi kỹ thuật; mã0 chỉ xác nhận
report/integrity hoàn tất, **không có nghĩa cơ chế PASS**. Gate FAIL hoặc
INCONCLUSIVE vẫn lưu đủ báo cáo và giữ `NO_MT_BICL_RELEASE`, không đổi seed,
threshold hoặc thay âm thầm model. `development_allowed=false` trong mọi
report bước này; gate đạt mới tiếp tục các điều kiện tích hợp W10-08–10.

Output ignored: `outputs/bayesian_benchmark/mt_bicl_v1/evaluation_v1/` gồm
`index.json`, `baseline.json`, `seed17.json`, `seed42.json`, `seed73.json`,
`report.json`, `replay_verification.json` và metadata khóa OS. Kết quả thật và
hash nghiệm thu ở dưới; không kết luận lợi ích hệ thống hoặc kinh tế từ việc
báo cáo đã hoàn tất.

### Nghiệm thu đánh giá thật, 28/10/2026

**Integrity/replay PASS; gate cơ chế FAIL.** Đã chạy đúng CLI `verify`, exit0,
đối soát source/runtime/input/training receipt, raw logits, metric, index và
receipt `INFERENCE_REPLAY_MATCH` gắn đúng report/hash/GPU. Receipt xác nhận
người dùng đã replay inference/fit baseline train-only bằng mã đã khóa;
lượt nghiệm thu không chạy lại GPU replay, optimizer hoặc fit baseline.
`index.status=COMPLETE`, `technical_status=PASS`,
`market_reporting_status=COMPLETE_NOT_A_PERFORMANCE_GATE`.

Đối chiếu bổ sung bằng phép tính scalar độc lập trên raw logits và oracle
đã khóa: KL dùng `math.fsum`/logsigmoid, P95 nội suy tuyến tính từ danh sách
sai số đã sort, numerator prior-swap theo dấu Δp. Cả ba seed khớp report trong
10⁻¹², denominator cố định **3.740/5.000 cặp**; mỗi seed đủ 5.000 test.

| Seed / checkpoint chọn bằng 2021 | Mean KL (nat), ngưỡng ≤0,02 | P95 absolute error, ngưỡng ≤0,10 | Khớp dấu, ngưỡng ≥90% | Cơ chế |
| --- | ---: | ---: | ---: | --- |
| 17 / 1.000 | 0,091474276411 | 0,385156293483 | 1.837/3.740 =49,117647% | FAIL |
| **42 / 1.000 — candidate** | **0,097592527938** | **0,398684777570** | **1.845/3.740 =49,331551%** | **FAIL** |
| 73 / 2.000 | 0,092478448739 | 0,384683743530 | 1.856/3.740 =49,625668% | FAIL |

Candidate vẫn seed42/step1000 đã chọn trước bằng 2021; không chuyển sang seed
khác hoặc đổi checkpoint bằng test. Fixture pooling: model **0,450375781969**,
oracle **0,709701732547**, pooled **0,612867460739**; model không gần oracle
hơn pooled trên fixture này. Đây là diagnostic, không bổ sung gate mới.

Validation **256/328 cycle ứng viên**: FPT54/MWG64/VCB75/VNM63; 72 cycle
EXCLUDED. Reason counts 55 corporate-action window, 6 corporate-action holding,
16 cross-block holding có thể giao nhau, không cộng thành số loại duy nhất.
Mọi nhánh/seed giữ cùng 256 query. Baseline train731; Laplace rate
**0,401091405184**, logistic hội tụ sau **14 iteration** trên cùng scaler
cuối 2020. Không dùng kết quả 2022 để chọn hoặc fit lại candidate.

| Phương pháp / seed | Macro log loss 2022 | Macro Brier 2022 |
| --- | ---: | ---: |
| Full 17 | 0,690833616179 | 0,248863357047 |
| **Full 42 — candidate** | **0,683505992786** | **0,245025235530** |
| Full 73 | 0,689912331630 | 0,248276217514 |
| Base rate | 0,667347378601 | 0,237205159013 |
| Logistic | 0,679045486760 | 0,242852774485 |
| No_prior 42 | 0,685012049739 | 0,245360216154 |
| No_target 42 | 0,675990443276 | 0,241166489690 |
| Naive pooling | 0,755699582201 | 0,275776302878 |

Full candidate **kém base rate, logistic và No_target ở cả hai metric**;
tốt hơn No_prior và naive pooling. Các đối chiếu là mô tả trên validation
2022 đã có exposure, không là bằng chứng lợi nhuận hoặc lý do đổi candidate.
Report giữ đủ No_prior/No_target của cả ba seed, metric từng mã và raw logits.

Calibration candidate có bốn bin khác rỗng; sáu bin còn lại giữ count0/null:

| Bin p | N | Mean p | Tỷ lệ y=1 | Mean r_net (fraction) |
| --- | ---: | ---: | ---: | ---: |
| [0,2;0,3) | 10 | 0,272159 | 0,300000 | −0,015868 |
| [0,3;0,4) | 80 | 0,358040 | 0,462500 | −0,003847 |
| [0,4;0,5) | 159 | 0,444574 | 0,358491 | −0,006154 |
| [0,5;0,6) | 7 | 0,531495 | 0,142857 | −0,037583 |

Tổng observed rate **98/256 =0,3828125**; mean r_net mọi cycle
**−0,006671986726**, mean positive gain **0,027514864821**, mean nonpositive
loss **−0,027876489585**. Đây là nhãn cycle giữ nguyên hợp đồng engine, không
là return tài khoản/action của candidate. K khả dụng=3 ở cả 256 query;
m=0 có32, m=8 có117, đủ strata m=0..8 trong report. Không suy ER từ p.

Đã đối soát **7 file evaluation, 4.104.608 byte**; raw logits/reports/receipt
giữ nguyên trước/sau nghiệm thu, không gồm metadata khóa OS. Identity:
`184ed2f68f9dad7f2e177ffe4037f3d9d14289302b3adea56d763e0b0543603a`.
SHA-256 byte trong `outputs/bayesian_benchmark/mt_bicl_v1/evaluation_v1/`:

| Artifact | Byte | SHA-256 |
| --- | ---: | --- |
| [index.json](../../../outputs/bayesian_benchmark/mt_bicl_v1/evaluation_v1/index.json) | 7.283 | `ffaf067f9b32cdb62fe7e4e3695c352f0413d52c1ada7ba056e3cf8b19719637` |
| [baseline.json](../../../outputs/bayesian_benchmark/mt_bicl_v1/evaluation_v1/baseline.json) | 43.928 | `92ec62c2bdd282ebbcd62722edb00cbb114631e4405a2711fd9f6948fb202914` |
| [seed17.json](../../../outputs/bayesian_benchmark/mt_bicl_v1/evaluation_v1/seed17.json) | 480.809 | `04aae684eee3a32073b871f467083105b8a2cdd57be110106b49e9f4edfc919a` |
| [seed42.json](../../../outputs/bayesian_benchmark/mt_bicl_v1/evaluation_v1/seed42.json) | 485.193 | `0423502327213ebd67a5ea2764423fe6cd426f0f15b2add35201011e609b5023` |
| [seed73.json](../../../outputs/bayesian_benchmark/mt_bicl_v1/evaluation_v1/seed73.json) | 486.649 | `3734bb18fb44e188b6febd1670e9a5ef0d30a9daf33c507a821e5b50dcf95fd7` |
| [report.json](../../../outputs/bayesian_benchmark/mt_bicl_v1/evaluation_v1/report.json) | 2.600.022 | `861efa6d09e92fd2cbace21bd8f2175256e6c7a721bf731f67c737115c9de9aa` |
| [replay_verification.json](../../../outputs/bayesian_benchmark/mt_bicl_v1/evaluation_v1/replay_verification.json) | 724 | `116d8ad86761d34863ef700f2f899b84b3bc4763c88fa773c2816619e631af49` |

Theo AGENTS.md 1.2, chỉ sửa tài liệu/phân tích artifact nên không chạy lại
unit/leakage/E2E/compileall hoặc biên dịch Python. Viện dẫn **76 test PASS,
49 leakage** từ lượt triển khai trên code/runtime nguyên vẹn; không gọi là
test vừa chạy lại. Verifier chạy ngoài sandbox để đọc boot Windows cho OS
lock theo hạn chế đã xác định. Đặc tả, ba input, 67 file training, W9 và ledger
giữ nguyên; không ghi đè receipt cũ, train bổ sung hoặc gọi LLM/API.

**Kết luận phát hành: NO_MT_BICL_RELEASE; development_allowed=false,
decision_calls_allowed=false.** W10-07 DONE về thực hiện/đối soát phép đánh
giá, không PASS về cơ chế. W10-08–10 và development/xác nhận phụ thuộc bị chặn
cho candidate này; không tự hạ ngưỡng, chọn lại seed/checkpoint hoặc thay model
để đi tiếp. Synthetic test/prior-swap và kết quả 2022 nay đã xem; mọi nghiên
cứu sửa phương pháp sau kết quả này phải khai báo exposure, giữ nguyên bằng
chứng revision hiện tại và đăng ký protocol/version mới trước train theo quy
tắc amendment, không coi đây là test chưa từng xem.
