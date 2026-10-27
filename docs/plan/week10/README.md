# Tuần 10 — Học Bayes từ prior tasks và target context

**Kế hoạch thay thế 27/10/2026; W10-01–02 DONE, 2/10 task DONE.
Protocol v1 đã khóa trước train; tiếp theo W10-03.**
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
