# Tuần 10 — Học Bayes từ prior tasks và target context

**Amendment 28/10/2026: W10-01–10 DONE, 10/14 task DONE; tiếp theo W10-11.
Teacher v2.1 hội tụ ở vòng237, oracle/corpus đã kiểm; learner chưa train.
Candidate v1 vẫn FAIL / NO_MT_BICL_RELEASE; chưa release development.**
[Kế hoạch tổng](../plan.md) · [W11](../week11/README.md) · [W12](../week12/README.md)

Mục tiêu: một bộ dự báo **Multi-Task Bayesian ICL (MT-BICL)** nhỏ học từ
các nhiệm vụ trước và các ví dụ đã đóng của nhiệm vụ hiện tại, rồi cung
cấp xác suất dự báo/context cho Decision LLM. Giữ hệ thống đa agent và
Original mặc định. Đo riêng ba mức: học được cơ chế, dự báo có ích, tài
khoản cải thiện. Tên phương pháp hoặc synthetic test không chứng minh lợi nhuận.

Mục 1–6 giữ đặc tả v1 để đối chiếu với bằng chứng đã khóa. **Phương án
hiện hành là mục 9**, thay recipe/loss/selection cho revision mới; không sửa
protocol_v1.json hoặc biến FAIL cũ thành PASS. W10-08–14 trong checklist
thay các task tích hợp 08–10 chưa chạy; receipt W10-01–07 vẫn là lịch sử v1.

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
| W10-08 | Audit nguyên nhân từ raw logits, curve 2021 và oracle trên thị trường; phân biệt sự kiện/giả thuyết | 07 | [x] DONE — mục 9, không nghiệm thu learner |
| W10-09 | Khóa amendment/protocol v2, teacher, tokenizer/loss, selection, RNG và ngân sách trước fit/train | 08 | [x] DONE — đặc tả khóa; sau đó người dùng cấp thêm10 giờ W10 v2, active≤4 giờ trong quỹ này; chưa fit/train |
| W10-10 | Teacher Beta-Bernoulli phân cấp, fit hyper-prior train-only, oracle độc lập và prior-predictive audit | 09 | [x] DONE — amendment1.000 vòng khóa trước fit; hội tụ237, PPC/corpus/oracle đầy đủ; giữ bất lợi PPC |
| W10-11 | Sửa packing/loss; kiểm small-set fit, causal/gradient và pilot chẩn đoán có giới hạn | 10 | [ ] TODO — dùng teacher v2.1 đã khóa; chưa release train lớn |
| W10-12 | Train/distill ba seed; selection có điều kiện cơ chế; đánh giá mới và báo thị trường | 11 | [ ] TODO |
| W10-13 | Adapter/paired/retry/checkpoint, dry-run 60 điểm và semantic probe; test đường đổi | 12 đạt cơ chế/technical | [ ] TODO — có điều kiện |
| W10-14 | Freeze teacher/student/runtime/protocol, verifier lạnh và release development v2 | 13 | [ ] TODO — có điều kiện |

V1 giữ nguyên core/mt_bicl_* và artifact đã khóa. V2 dùng module/schema/
namespace riêng; không đổi hằng hash hoặc phục hồi candidate FAIL qua CLI cũ.
Reuse engine/PIT/retry/ledger theo hợp đồng; test đường đổi theo AGENTS.md 1.2.

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

## 9. Khắc phục nguyên nhân và protocol v2 — 28/10/2026

### W10-08 — Audit nguyên nhân: DONE

**Không có bằng chứng đây chỉ là gate quá chặt.** Các ngưỡng 0,02/0,10/90%
là lựa chọn của nghiên cứu, không phải định lý của paper; nhưng kết quả hiện
tại còn kém cả dự báo hằng trên synthetic. Nới ngưỡng tới mức cho v1 đi tiếp
sẽ làm mất ý nghĩa phép kiểm. Thiết kế v1 do kế hoạch trước đề xuất chưa phù
hợp ở cả mục tiêu huấn luyện lẫn liên hệ giữa simulator và thị trường.

Tính lại từ raw logits/oracle, không optimizer hoặc chọn lại candidate:

| Phép kiểm | Seed 17 | Seed 42 | Seed 73 |
| --- | ---: | ---: | ---: |
| KL oracle→learner | 0,091474 | 0,097593 | 0,092478 |
| P95 sai số xác suất | 0,385156 | 0,398685 | 0,384684 |
| Khớp dấu prior-swap, N=3.740 | 49,1176% | 49,3316% | 49,6257% |
| SD xác suất learner trên 5.000 episode | 0,037944 | 0,039176 | 0,038114 |
| Tương quan p learner với p oracle | 0,038402 | 0,016695 | 0,024502 |

Đối chứng **p=0,5**: KL **0,089548931451**, P95 **0,383296048154**;
SD p oracle **0,203054**. Với seed42, median |Δp| khi đổi prior là **0,012003**,
so oracle **0,156546** trên cùng 3.740 cặp; tương quan hai Δp chỉ **0,005528**.
Đây là dấu hiệu learner chưa khai thác đúng context; không khẳng định mọi
trọng số đều hằng hoặc đã chứng minh một dòng code cụ thể sai.

| Nguyên nhân / bằng chứng | Mức kết luận | Cách sửa |
| --- | --- | --- |
| Selection chỉ tối ưu log loss 2021, chọn step1.000/1.000/2.000; không có điều kiện cơ chế | Xác nhận từ recipe và candidate | Chỉ xét checkpoint đạt synthetic validation trước khi xếp hạng thị trường |
| Trộn loss synthetic:market=1:1 trên cùng weights; chỉ 723 query train/48 task, 43 task có ≥8 query | Thiết kế xác nhận; gradient conflict/chạy tắt theo miền là giả thuyết | Tách fit prior thị trường khỏi học suy luận; student dùng teacher loss, không BCE market trộn vào backbone |
| Log loss 2021 từ step1.000→10.000: 17: 0,67712→1,14399; 42: 0,66766→1,12266; 73: 0,69346→1,19218 | Generalization xấu dần đã quan sát; chưa đủ để quy toàn bộ cho overfit | Không chỉ tăng step; kiểm learning curve riêng cơ chế và thị trường |
| X/Y tách thành token, position tuyệt đối, hai lớp; loss trung bình mọi target prefix | Khác thiết kế paper; chưa chứng minh lỗi mask hay đây là nguyên nhân duy nhất | Paired observation token, query bị che nhãn; pilot nhỏ kiểm học và gradient |
| Oracle logistic ngẫu nhiên dự báo thị trường còn kém learner | Xác nhận bằng phép tính bổ sung dưới đây | Đổi mô hình nhiệm vụ/prior; không distill oracle cũ rồi mặc định có ích |

**Đối chiếu teacher với thị trường đã xem:** giữ membership/scaler và không
fit thêm, gọi FiniteBayesOracle.predict trên input D/C/x; tính macro đều mã.
Phép tính NumPy độc lập từ bảng latent cho cùng kết quả, và khớp 100 oracle
synthetic đầu tiên với sai số 0 ở precision đang dùng.

| Oracle v1, chỉ chẩn đoán | N | Macro log loss | Macro Brier |
| --- | ---: | ---: | ---: |
| 2021 | 248 | 0,731295602319 | 0,263917441501 |
| 2022 | 256 | 0,788869994931 | 0,288754288428 |

Trên 2022, base rate là **0,667347378601 / 0,237205159013**. Vì vậy sửa
approximation error là cần thiết nhưng chưa đủ; không dùng oracle logistic
v1 làm đường thay thế phát hành hoặc coi oracle là chân lý của thị trường.
Chưa đánh giá cơ chế cả 30 checkpoint; không suy FAIL của ba checkpoint đã
chọn thành FAIL của mọi checkpoint. Việc chọn lại bằng test cũ vẫn bị cấm.

### 9.1. Quyết định phương pháp: nhiệm vụ đơn giản hơn, prior gắn thị trường

Candidate duy nhất đề xuất: **MT-BICL-v2 với teacher Beta-Bernoulli phân cấp
và learner distillation**, sau đó Decision LLM đọc p + task examples.
Kế thừa cấu trúc retrieval/regime và đối chứng A của W9; không gán gain W9
cho model mới. Bốn feature giá dùng để chọn context theo query, không ép
ước lượng năm hệ số logistic riêng cho mỗi block chỉ có khoảng 7–20 query.

Theo [paper §4 và Appendix C](https://arxiv.org/html/2606.20538v1), transformer
được train trên prior/target tasks; synthetic checkpoint chọn bằng validation
cùng phân phối, khác seed. Token của tác giả ghép x hiện tại với y trước đó.
V2 giữ ý tưởng conditioning và kiểm prior-swap; **đổi likelihood sang
Beta-Bernoulli, dùng soft teacher và paired observation là thích ứng riêng**,
không tuyên bố tái lập thí nghiệm logistic hoặc công thức huấn luyện gốc.

PASS trên họ Beta-Bernoulli mới không phải PASS trên bài toán logistic v1.
Không so trực tiếp KL hai họ rồi kết luận model đã tốt hơn; đây là đổi giả
thuyết/mô hình nhiệm vụ có khai báo. Giá trị hệ thống vẫn phải qua cùng
benchmark kinh tế và đối chứng W11–W12, không đổi tiêu chí để hợp kết quả.

Mô hình giả định: λ=(μ,κ), θ_k|λ~Beta(μκ,(1−μ)κ), y_ki|θ_k~Bernoulli(θ_k).
Mỗi prior block có θ riêng; target có θ_* riêng. Dùng cùng bank, block63,
cutoff, nhãn r_net>0 và retrieval v1. Query feature ảnh hưởng membership;
trong teacher, count thắng/thua là sufficient statistics, không có hệ số x.
Đây là giả định exchangeability trong tập ví dụ được chọn, phải công bố và
kiểm trên thị trường, không khẳng định đúng cho mọi regime.

Đề xuất khóa trước fit: grid μ={0,2;0,4;0,6;0,8}, κ={2;8;32;128}, 16 trạng
thái. Fit π(λ) bằng marginal likelihood của **các block train duy nhất**,
không lặp mỗi query thành một task độc lập. Chỉ cycle AVAILABLE có exit≤2020;
không lấy nhãn 2021/2022 để fit, không đổi grid theo metric validation.
EM khởi tạo uniform, Dirichlet α=2, tối đa 200 vòng, dừng khi max |Δπ|<1e−10;
phải ghi hội tụ, membership và posterior-predictive checks. Grid/recipe là
đề xuất đã khóa tại W10-09 bên dưới; không sửa simulator_v1.json.

Với s/f là số thắng/thua và α=μκ, β=(1−μ)κ:

    L_k(λ) = B(α+s_k, β+f_k) / B(α,β)
    π(λ|D,C) ∝ π(λ) × ∏k L_k(λ) × L_target(λ)
    p(y*=1|D,C) = Σλ π(λ|D,C) × (α+s_target)/(α+β+m)

Tính log-beta/log-space; target cũng cập nhật λ. Oracle độc lập đối chiếu
bằng tích xác suất tuần tự, không gọi lại cùng hàm để tạo expected. Giữ
no-prior, no-target và naive pooling **shared θ** để kiểm khác biệt. Fit π
là empirical Bayes offline; inference tại cutoff chỉ conditioning, không
refit π từ 2021–2025. Oracle chính xác cho giả định này, không cho thị trường.

### 9.2. Sửa learner và loss thay vì tăng tài nguyên mù quáng

- Hai lớp hidden128, heads4, FF256; pre-LN/GELU, dropout0. Một architecture,
  seed17/42/73, không ensemble hoặc chọn mô hình bằng P&L.
- Mỗi observation đã biết là một token (x,y,mask); thêm ranh giới/role/task
  slot. Query là (x,0,missing=1), không mang y thật. Tối đa 37 token với
  24 prior +8 target +4 marker +1 query. Prior order được permutation;
  target giữ thứ tự. Query đọc context hợp lệ, không nhãn tương lai.
- Loss chỉ tại query: cross-entropy với **q posterior teacher từ đúng D/C/x**.
  Không dùng θ/λ thật hoặc xác suất từ latent làm teacher label. Soft loss
  giảm nhiễu Bernoulli và không ưu tiên quá mức target prefix ít ví dụ.
- Student train trên synthetic sinh từ teacher đã fit train-only. x lấy từ
  feature train (giữ tương quan), độc lập với latent θ trong simulator;
  K/m và độ dài gồm cả cold-start. Nhãn Bernoulli sinh theo θ, posterior q
  tính lại chỉ từ observations. Không đưa BCE của 723 market query vào
  backbone theo tỷ lệ 1:1; nhãn thật đã dùng ở bước fit hyper-prior.
- AdamW lr3e−4, warmup250 rồi cosine về3e−5; batch128, tối đa5.000 step/seed,
  checkpoint250. Đo pipeline gồm teacher/cache trước cấp quyền train; trần train mới
  **4 giờ tổng**, bao gồm pilots, generation, validation và seal. Không đủ
  ngân sách thì INCOMPLETE; không nhân 4 giờ cho mỗi seed.
- Hai pilot cố định seed17, tối đa500 step/case, chỉ diagnostic: packing cũ
  và paired packing cùng soft teacher/synthetic-only. So tiny-set fit,
  gradient và validation; không dùng pilot để lựa cấu hình theo 2022.
  Tiny-set32 episode phải overfit q tới mean KL<1e−3; không đạt thì kiểm
  gradient/mask/optimizer trước train lớn. Đây là sanity check, không gate
  generalization hoặc bằng chứng thị trường; weights pilot bị bỏ.

Không khẳng định packing gây FAIL cho đến khi có pilot. Nếu sửa bug phát
hiện trong pilot, ghi revision và chỉ chạy lại test đường bị đổi; không
thay ngưỡng đã biết để cho model qua.

### 9.3. Selection và gate đúng cấp độ

W10-09 đã đăng ký stream train/diagnostic/synthetic-validation/test/prior-swap
mới, manifest và seed trước train. Synthetic v1 và 2022 đã xem giữ trạng thái
exposed; stream mới chỉ là kiểm held-out của revision, không xóa tính thích
nghi của toàn nghiên cứu. Không dùng test mới để chọn checkpoint.

1. **Kỹ thuật:** oracle độc lập, PIT/kinh tế/mask/gradient/serialization,
   frozen inference và source/runtime/hash PASS. Lỗi phải dừng.
2. **Synthetic validation:** 5.000 episode và 5.000 cặp swap riêng. Chỉ
   checkpoint có KL≤0,02, P95≤0,10, sign≥90% trên |Δoracle|≥0,05 và ít nhất
   200 cặp eligible mới vào tập chọn. Không có checkpoint đủ điều kiện:
   NO_ELIGIBLE_CHECKPOINT, không lấy checkpoint log loss thị trường thấp nhất.
3. **Chọn candidate:** trong tập đủ điều kiện trên, macro log loss 2021,
   Brier tie-break rồi step và seed theo thứ tự khóa. Báo cả ba seed và
   đường cong; không đánh đồng checkpoint cuối với checkpoint tốt nhất.
4. **Synthetic test mới:** chỉ mở sau seal selection, cùng ngưỡng trên;
   FAIL giữ NO_MT_BICL_RELEASE_V2, không thay seed/checkpoint. Prior-swap
   phải giữ C/x cố định và báo Δp amplitude/correlation, không chỉ sign.
5. **Thị trường 2022:** báo teacher, student, base rate, logistic, no-prior,
   no-target và pooling, cùng support; đối chiếu student−teacher để tách
   lỗi approximation khỏi lỗi giả định. Brier/NLL bất lợi không được ghi
   PASS nhưng không thay thế phép đo giá trị context trong Decision LLM.
6. **Development:** chỉ sau kỹ thuật/cơ chế và W10-13/14 PASS. Đây là run
   có đối chứng để tìm hiểu lợi ích toàn hệ thống, không chứng nhận trước
   lợi nhuận. Nếu chỉ examples hoặc numeric thắng thì claim đúng thành phần.

Giữ ngưỡng cơ chế **0,02/0,10/90%**, không nới theo kết quả v1. Báo constant
và context-blind controls trên cùng corpus mới để phát hiện PASS do teacher
quá phẳng. Thiếu cặp swap: INCONCLUSIVE, không thay sampler sau khi thấy
student. Quy tắc sampling/corpus (gồm stress case) khóa trước inference.
Không ép action theo p hoặc coi p là expected return; giữ hợp đồng kinh tế.

### 9.4. Bàn giao, thời gian và nghiệm thu thay kế hoạch

W10-09 khóa schema/protocol mới; W10-10–12 tạo bằng chứng thực thi; W10-13
chuẩn bị adapter/CLI/dry-run; W10-14 là release duy nhất sang W11. Các cờ
training/development/decision_calls tách riêng, mặc định false đến đúng gate.
V2 không kế thừa PASS hoặc quyền release từ v1; pipeline cũ vẫn tái lập được.

Phân bổ đề xuất trước khoản bổ sung: cửa sổ28/10–10/11, quỹ14–28 giờ. W10 đến01/11,
trần10 giờ: khoảng1 giờ protocol,2 giờ teacher/oracle,2 giờ learner/pilot,
3 giờ train/evaluate,2 giờ integration/release (train nằm trong trần4 giờ
riêng, không cộng ra ngoài tổng). Đây là dự toán cần đối soát tại W10-09.
Không reset quỹ giờ khi đổi revision: training v1 đã ghi 3,284 giờ active;
phải đối soát phần đã dùng và thời gian vận hành còn lại trước cấp budget v2.
Tại lúc đề xuất, trần10 giờ/4 giờ chưa phải số giờ được cấp. Sau W10-09,
người dùng đã cấp riêng thêm10 giờ như cập nhật bên dưới; không lấy dự toán
GPU thay ước lượng công sức tích hợp/kiểm thử/viết luận văn.
Không đủ thời gian thì ghi NOT_RUN, không bỏ gate hoặc chuyển việc nặng sang
phần viết luận văn. W11 phải release/bắt đầu xác nhận trước hết05/11;
W12 khóa dữ liệu hết07/11, kết thúc công việc dự kiến10/11, không W13.

Lượt 28/10 này chỉ đổi Markdown và phân tích bằng chứng: không sửa code,
protocol/schema/runtime, không train GPU, không gọi API. Không chạy lại
unit/leakage/E2E/compileall theo AGENTS.md1.2. Kiểm link/anchor/diff, số liệu
raw và hash trước/sau. 77 file input/training/evaluation (bỏ metadata OS lock)
có aggregate SHA-256 `93f8f3eb3c60984c10453ab9934e42d9f8eb189c2cff835a2645cfa0119346ab`;
report gốc `861efa6d09e92fd2cbace21bd8f2175256e6c7a721bf731f67c737115c9de9aa`.
Tại lượt sửa kế hoạch, W10-08 DONE là audit; W10-09–14 chưa thực hiện.
Kết quả khóa W10-09 được cập nhật ngay bên dưới. Sửa kế hoạch chưa có
nghĩa learner đã được sửa hoặc có bằng chứng cải thiện giao dịch.

## W10-09 — Khóa amendment v2 trước fit/train, 28/10/2026

**DONE về khóa đặc tả; chưa fit teacher, sinh corpus, pilot hoặc train.**
Nhánh `docs/mt-bicl-revision-protocol` từ `develop` tại `10d4509`, đã
`pull --ff-only`. V1 vẫn **FAIL/NO_MT_BICL_RELEASE**; giữ nguyên nguồn và
77 file input/training/evaluation. Không đổi hash/verifier hoặc quyền v1.

### Bản khóa máy đọc

| File | Nội dung khóa |
| --- | --- |
| [protocol_v2.json](protocol_v2.json) | Teacher, tokenizer/loss, model/optimizer, selection/gate, schema, budget và hợp đồng kế thừa |
| [corpus_manifest_v2.json](corpus_manifest_v2.json) | Recipe/seed/ID, IID/stress/swap và thời điểm được mở test; chưa materialize |
| [training_membership_v2.json](training_membership_v2.json) | **731 cycle/48 block** train duy nhất và thứ tự pool feature, scaler hash; chưa fit |
| [protocol_fixtures_v2.json](protocol_fixtures_v2.json) | Năm ví dụ toán với π uniform **không phải π đã fit**, token fixture và 24 ca hợp đồng |

SHA-256 byte protocol:
`00fa160c4fd25aacaf789ba011721f3e03d1b03b9b020cb298a93ca94ddedb40`.
Protocol bind ba JSON phụ, source v1 và 77 file cũ; verifier mới ghim hash
trong source, từ chối self-seal, file thêm/thiếu hoặc sửa logits/weights cũ.
Namespace `outputs/bayesian_benchmark/mt_bicl_v2/`, module `core/mt_bicl_v2_*`.
Fit/train/development/Decision/execution đều **false**; recipe không thay
bằng chứng W10-10–12 hoặc release W10-14. Giữ split, retrieval, scaler/HMM,
engine, ma trận LLM, projection, P0 và dependency v1.

### Các lựa chọn đã chốt

- **Teacher:** grid16 theo μ-major/κ-minor ở mục9.1, MAP-EM trên **48 block**,
  toàn bộ cycle AVAILABLE/train/exit≤2020, không lặp block theo query.
  Gồm cả tám cycle thiếu scaler prefix khi làm query v1. Responsibility
  từ π×L_block; M-step `(Σ responsibility+1)/(48+16)`. Uniform init,
  float64/log-space, tối đa200 vòng, max|π_next−π_old|<10⁻¹⁰ sau M-step;
  không hội tụ STOP, không fallback. Oracle W10-10 dùng tích predictive
  tuần tự độc lập; target cũng cập nhật λ. Prior-predictive1.000 replicate
  giữ kích thước task thật, báo mean/variance rate, toàn thắng/thua,
  quantile và khoảng95%; không tune grid hoặc refit sau2020.
- **Student:** observation `[x1,x2,x3,x4,y,0]`, marker `[0,0,0,0,−1,1]`,
  query `[x1,x2,x3,x4,0,1]`; ba role, bốn task slot (prior theo thứ tự trình
  bày, target/query slot3), causal/right-padding, tối đa37 token. Hai lớp128/
  head4/FF256, pre-LN/GELU/dropout0, final LayerNorm, **271.873 tham số FP32**.
  Soft cross-entropy **chỉ query**, q detach từ đúng D/C; không y query,
  latent thật hoặc BCE market. Feature synthetic lấy cả vector từ pool731
  train-scale, độc lập latent/label, không dùng outcome của cycle nguồn.
- **Pilot/train:** hai pilot seed17, tiny-set32, tối đa500 step/case, packing
  X/Y69 có task slot và paired37 với cùng soft query loss; chỉ paired cần
  mean KL<10⁻³ cuối pilot. Không đạt dừng audit, không tăng step/tune2022;
  bỏ weights. Ba seed17/42/73 đủ5.000 step/seed nếu budget cho phép, không
  early-stop theo metric; AdamW3e−4, warmup250 rồi cosine về3e−5, batch128,
  checkpoint250 (**60 checkpoint**). Physical128/64/32, accumulation1/2/4
  chỉ chọn bằng OOM preflight trước train, chung mọi seed. Thiếu step giữ
  INCOMPLETE, không seal candidate. Công thức LR/step/RNG/resume nằm trong JSON.
- **RNG/corpus:** PCG64 seed2026102801…2026102810 lần lượt train, diagnostic,
  synthetic-validation, synthetic-test, validation-swap, test-swap, pilot-tiny,
  prior-predictive, permutation, preflight. SeedSequence tách model seed,
  episode ID và component domain; primitive/thứ tự draw đã ghi. Mỗi stream
  validation/test/swap có5.000 ID: 4.500 generative K0–3/m0–8/n2–8 và500
  stress cố định theo ID (K1/3, n8, m0/1/2/4/8, prior toàn0/toàn1, C xen kẽ).
  Báo IID/stress riêng; gate dùng đủ5.000. Swap giữ mọi x/C/query, chỉ đổi
  prior labels; stress lấy bù nhãn. Không sinh bù hoặc đổi sampler sau kết quả.
  Seal corpus sau fit/oracle và **trước optimizer**. Builder được kiểm oracle
  test độc lập; không forward/xem metric student test trước selection seal.
- **Selection:** chỉ checkpoint đạt cả KL≤0,02/P95≤0,10/swap≥90% trên validation
  và technical mới eligible; xếp macro log loss2021, Brier (round12), step,
  seed17/42/73. Không có eligible: `NO_ELIGIBLE_CHECKPOINT`, không export/
  mở test/fallback market-best. Seal đủ60 checkpoint/report trước test mới;
  FAIL giữ `NO_MT_BICL_RELEASE_V2`, không chọn lại. Seed thiếu eligible giữ
  NOT_RUN. Báo amplitude/correlation Δp, constant và context-blind student
  (D=C=[] cùng query). Constant đạt cả KL/P95 hoặc swap eligible<200 thì
  INCONCLUSIVE, không release. Market2022 exposed, cùng256 query: teacher/
  student/baselines/ablations/pooling, student−teacher, calibration/r_net;
  bất lợi báo đúng trạng thái. Không so KL hai họ rồi suy lợi ích thị trường.

`contracts` khóa envelope/schema version của teacher, corpus, checkpoint,
selection seal, evaluation và budget receipt; JSON chỉ kiểu Python gốc,
số hữu hạn. W10-10–14 phải triển khai và kiểm hành vi tương ứng, chưa được
ghi PASS chỉ từ fixture/recipe này.

### Ngân sách và điều kiện trước fit/train

**Cập nhật sau khóa, 28/10/2026:** người dùng trả lời **“ok thêm 10 giờ cũng
được”**. Ghi nhận **10 giờ bổ sung dành cho phần W10 v2 còn lại kể từ xác
nhận này**, ngoài quỹ cũ; không suy ngược tổng giờ đã dùng hoặc trừ lại chi
phí v1 vào khoản mới. [budget_v2.json](budget_v2.json) lưu nguyên lời xác
nhận, binding protocol và hạn mức. **Active train/pilot≤4 giờ chung, nằm
trong10 giờ**, không cộng thành14 giờ; phạm vi gồm cả generation/cache,
preflight, validation/checkpoint và seal/replay như protocol. Công sức
triển khai/kiểm thử/teacher/integration cũng tính trong10 giờ, mỗi khoảng
thời gian chỉ tính một lần. Không điều chuyển phần W11/W12/viết luận văn
của quỹ cũ. Tổng đã dùng và dự trữ cũ chưa được báo: giữ null, không ghi0.

Khoản bổ sung thay điều kiện chờ đối soát quỹ cũ cho **quyền ngân sách**;
không sửa protocol đã khóa hoặc tự cấp release kỹ thuật. W10-10 có thể
tiếp tục triển khai teacher trong phần được cấp; trước GPU vẫn phải đủ
teacher/oracle, paired pilot, preflight và kế toán chi phí thực chứng minh
ba seed nằm trong phần active còn lại. Giữ mốc01/11,05/11,07/11,10/11 và
mọi gate. **Chưa fit/train/API trong lượt ghi nhận này.**

Receipt có SHA-256 canonical payload
`52b7d54ba31f6c02f12c304877a36dbe1958337152f6f77d957644064c128cf4`.
Lượt cập nhật chỉ sửa kế hoạch/receipt và thuộc tính giữ byte JSON: kiểm
schema trường bắt buộc, hash, hạn mức4/10 giờ, liên kết/diff và verifier
đặc tả thật; không chạy lại unit/leakage/E2E/compileall vì không đổi code,
runtime hoặc đường thực thi (AGENTS.md1.2). Viện dẫn29 test từ W10-09,
không ghi vừa chạy lại. Protocol/manifest/fixture/membership,77 file v1,
nguồn và ledger giữ nguyên; receipt chưa là output của consumer ngân sách
W10-10–12, không tự tuyên bố release kỹ thuật.

Phần dưới lưu **snapshot tại thời điểm khóa, trước xác nhận bổ sung**, không
còn là lý do chặn ngân sách hiện hành:

Quỹ tổng **14–28 giờ** không reset. V1 đã dùng tối thiểu **3,283772 giờ
active**; chưa biết công sức đã dùng cho code/test/vận hành. Phần tổng còn
lại chỉ có **trần trên10,716228–24,716228 giờ**, không là giờ được bảo đảm.
Trần W10 cũ+mới10 giờ cho v2 trần trên **6,716228 giờ**, chưa trừ các việc
khác. Dự toán v2 thêm10 giờ ở mục9.4 **vượt trần trên này**: chưa chứng minh
khả thi, không tự lấy giờ W11/luận văn để bù.

Khóa trần active v2 **14.400 giây chung**, gồm hai pilot, preflight,
generation/cache cho train, ba seed, validation/checkpoint và seal/replay;
không nhân4 giờ theo seed. **Budget cấp hiện tại=0 giây fit/0 giây train**,
`PENDING_ACTUAL_SPENT_AND_REMAINING_ACCOUNTING`. Đã hỏi người dùng giờ thực
đã dùng/còn lại; chưa trả lời không phải đồng ý cấp budget. Trước fit W10-10
phải có receipt đối soát, dành giờ W11/W12/viết luận văn và phân bổ W10;
trước optimizer phải đo pipeline thật, chứng minh cả ba seed nằm trong
phần được cấp≤4 giờ. Receipt cấp quyền không sửa byte protocol. Giữ mốc
01/11, release/start xác nhận05/11, data-stop07/11, kết thúc10/11. Không
khả thi thì NOT_RUN/INCOMPLETE, không kéo dài hoặc giảm gate/seed/step.

### Kiểm tra theo phạm vi và lệnh chỉ đọc

Verifier trên nguồn/runtime thật **PASS**: 77 file v1 nguyên byte, membership/
scaler khớp. Fixture π uniform kiểm bằng số hữu tỉ: conflicting-tasks cho
hierarchical **0,840054346236**, shared-θ pooling **0,588817448218**; chưa là
teacher fit hoặc prior-predictive audit. Chọn test protocol mới/cũ và bank
leakage theo đường membership được dùng; không chạy toàn suite/E2E/compileall,
GPU/API hoặc sửa engine/LLM/PIT runtime. **29 test PASS, không skip**: 12 test
v2 mới, 9 hồi quy protocol v1 và 8 bank leakage; hai test mới còn kiểm trực
tiếp future append/mislabeled train và ID trùng. Hai file Python mới biên
dịch PASS; verifier CLI thật, UTF-8/link/checklist/diff/hash PASS. Bank leakage
dùng quyền ngoài sandbox cho thư mục tạm Windows như các lượt trước; không
sửa test để né kiểm tra. Đối soát trước/sau đủ **77 file/265.658.442 byte**
nguyên vẹn; ledger/nguồn giá/W9 vẫn khớp verifier kế thừa. Các gate v1 là
bằng chứng lịch sử, không được ghi thành PASS teacher/student v2.

Khối sau chạy từ đầu đến cuối, chỉ đối soát; **không cần chạy GPU**. CLI
kiểm snapshot protocol nên vẫn in `budget cấp=0`; khoản cấp sau khóa nằm
riêng tại `budget_v2.json`, không sửa snapshot để thay thông báo này:

```powershell
Set-Location -LiteralPath 'C:\Users\Legion\OneDrive\Tài liệu\GitHub\A-Multi-Agent-Large-Language-Model-Approach-to-Price-Driven-Stock-Trading-in-the-Vietnamese-Stock-Ma'
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'

py -3.13 -X utf8 scripts/verify_mt_bicl_protocol_v2.py
if ($LASTEXITCODE -ne 0) {
    throw "Kiểm protocol v2 không đạt; dừng trước fit/train."
}
```

## W10-10 — Teacher Beta–Bernoulli và kiểm oracle, 28/10/2026

**Amendment v2.1 đã được người dùng yêu cầu, đăng ký trước lần fit mới:**
[protocol_v2_1.json](protocol_v2_1.json), SHA-256
`16f31de4f3d3a24d36b059ae1929001b618f3805a7fb95a2cd8d969bae3a8952`.
Chỉ đổi `teacher.fit.max_iterations` từ200 lên1.000; giữ tolerance<10⁻¹⁰,
uniform init, grid, dữ liệu, RNG, gate và hạn mức. Namespace kết quả mới
`teacher_v2_1/`; source và hai artifact STOP200 bên dưới giữ nguyên byte
để còn tái lập được. Dùng chung đồng hồ active v2, không cấp thêm4 giờ.
Khóa amendment bằng commit trước production fit; chưa có kết quả v2.1
tại lượt đăng ký này. Kết quả200 vòng dưới đây là lịch sử, không bị sửa.

**Lượt v2 trước amendment: đã chạy fit CPU thật nhưng task còn INCOMPLETE.**
Nhánh `feat/hierarchical-beta-teacher` từ `develop` tại `c6c1328`, đã pull
trước triển khai. Tuân thủ protocol v2 và grant10 giờ đã khóa; không thay
grid, 200 vòng, tolerance, RNG hoặc bằng chứng v1 sau khi thấy kết quả.

### Phần đã triển khai và kiểm

- Teacher log-beta/log-space: normalize λ một lần sau D và C; predictive
  θ target theo count. No-prior/no-target qua bỏ đúng component, pooling
  shared-θ qua gộp toàn bộ count. π cố định/read-only, không dùng x/y query/
  latent để tính posterior. Nhãn train đối soát trực tiếp helper kinh tế.
- Oracle scalar độc lập nhân predictive từng observation, không import
  grid/likelihood hoặc helper log-beta từ teacher. Năm fixture uniform ×hai
  cách hierarchical/pooling khớp ≤10⁻¹²; kiểm thêm π không đều, nhãn cực trị,
  permutation và tác động ranh giới task trong unit test. Đây chưa là kiểm
  toàn corpus của teacher đã fit.
- Sampler random-access theo manifest, pool731 vector nguyên vẹn từ train,
  x độc lập latent/label, query y và θ/λ ở sidecar. Swap giữ mọi x/C/query/ID,
  chỉ đổi prior labels; stress theo ID cố định. Chưa materialize corpus thật.
- Producer/CLI theo stage immutable, journal/resume, OS lock chung namespace
  và đồng hồ active14.400 giây dùng chung cho các stage/seed. Hard crash tính
  bảo thủ gap; pause sạch giữ stage đã commit. Không cho reset budget khi
  mất state hoặc counter thấp hơn lịch sử phiên. Replay so toàn payload,
  chặn sửa dự báo rồi tự rehash cả stage/index.
- Prior-predictive1.000 replicate đúng size task, seed/domain riêng,
  mean theo cycle, variance task ddof0, quantile tuyến tính và khoảng95%.
  **Code và fixture PASS, audit production chưa chạy** vì EM không hội tụ.

Mã mới: `core/mt_bicl_v2_teacher.py`, `mt_bicl_v2_reference.py`,
`mt_bicl_v2_simulator.py`, `mt_bicl_v2_io.py`, `mt_bicl_v2_preparation.py` và
`scripts/prepare_mt_bicl_teacher.py`. Không sửa module v1, engine, HMM,
retrieval, LLM/prompt/retry hoặc dependency.

### Kết quả fit thật và quyết định dừng

Đúng **731 cycle/48 block train duy nhất**, gồm293 nhãn thắng/438 thua;
không đọc nhãn2021/2022 để fit. Uniform init, MAP-EM/Dirichlet α=2,
float64, đúng **200 vòng**. Objective MAP (bỏ hằng số) từ
**−570,846838602530** lên **−556,576205335550**; objective gần ổn định
không thay điều kiện hội tụ trên π.

| Điều kiện | Kết quả | Trạng thái |
| --- | ---: | --- |
| Max \|π_next−π_old\| <10⁻¹⁰ trong≤200 vòng | **1,755550427252×10⁻⁹** tại vòng200 | **Chưa đạt** |
| Oracle fixture uniform/kiểm math và pipeline bằng CPU fixture | PASS | Kỹ thuật |
| Production prior-predictive / fixed validation/test/swap corpus | NOT_RUN | Dừng sau EM |
| Learner/pilot/GPU/LLM/development | NOT_RUN | Không release |

Artifact giữ `STOP_TEACHER_NONCONVERGENCE_NO_UNIFORM_FALLBACK`,
`converged=false`. π lưu trong chẩn đoán **không phải teacher được phép
dùng**, không fallback uniform, thêm vòng hoặc nới tolerance. Đây chưa là
kết luận teacher/model v2 kém về thị trường; phép fit chưa qua điều kiện
đã đăng ký. Muốn thay giới hạn EM cần amendment mới trước thực thi tiếp,
giữ nguyên artifact này và khai báo outcome đã thấy.

**Integrity/replay PASS, trạng thái khoa học vẫn STOP.** CLI `verify --replay`
đã tái dựng đúng toàn bộ fit/fixture, in `replay=PASS` và trả **mã2** có chủ
đích cho EM chưa hội tụ. Kiểm bổ sung scalar độc lập đủ200 vòng: likelihood
theo tích tuần tự, normalization/M-step bằng `math.fsum`; max sai khác π
**2,38143×10⁻¹⁴**, sai khác delta cuối **1,66533×10⁻¹⁶**, max sai khác
objective **2,27374×10⁻¹³**. Không chạy thêm vòng201 hoặc fit phương án khác.

Hai file khoa học frozen trong namespace ignored
`outputs/bayesian_benchmark/mt_bicl_v2/teacher_v2/`:

| File | Byte | SHA-256 |
| --- | ---: | --- |
| [teacher_fit.json](../../../outputs/bayesian_benchmark/mt_bicl_v2/teacher_v2/teacher_fit.json) | 65.805 | `68aa75cd988ded5dab75d7dd0653a230aa8ad8717884a489638120bbda4547e0` |
| [index.json](../../../outputs/bayesian_benchmark/mt_bicl_v2/teacher_v2/index.json) | 2.601 | `af2160eb6f5499afa63570ce19f24c01769e9566f5461cea841636f61c48b057` |

Identity canonical:
`06849185216cc40706a51c7f86f4c51bb2fa8db1ad685c85b88aeecea9597595`.
`active_budget_v2.json` là state vận hành chung, không đóng băng như hai
file trên; snapshot sau fit+replay **0,183225 giây active**, không phải tổng
thời gian triển khai/kiểm thử/import/đối soát thuộc quỹ10 giờ. Công việc
trước khi có đồng hồ chưa biết giữ unknown, không coi toàn quỹ còn nguyên.
Đồng hồ công việc đo từ sau khi tạo nhánh tới mốc QA ghi **1.227,546 giây
≈20 phút28 giây**; đây là phần chi phí10 giờ đã quan sát, bao gồm active
nêu trên, không cộng hai lần. Chưa bao gồm khảo sát trước nhánh và phần
hoàn tất sau mốc QA; không dùng làm tổng chi phí trọn vẹn hoặc reset quỹ.

### Kiểm tra theo phạm vi và lệnh tái kiểm

**51 test PASS, không skip:** 22 test mới (7 leakage), 21 hồi quy protocol
v1/v2 và8 bank leakage; tổng **15 test trong các suite leakage**. Biên dịch
đúng9 file Python mới PASS; CLI `check-inputs`, source/runtime/grant,
hash/link/diff/UTF-8 PASS. Journal/Windows Temp và CLI OS lock chạy ngoài
sandbox do quyền thư mục tạm/đọc boot đã xác định. Không chạy toàn suite,
E2E hoặc compileall; không GPU/API. Protocol/ba artifact/grant/ledger cùng
77 file v1 giữ nguyên. Test sampler/journal/PPC dùng fixture không thay
production corpus/oracle/PPC còn NOT_RUN.

Không cần chạy GPU. Bộ lệnh kiểm từ đầu đến cuối (mã2 là kết quả STOP
đã lưu, mã1 lỗi kỹ thuật, mã3 pause; không được đổi mã2 thành PASS teacher):

```powershell
Set-Location -LiteralPath 'C:\Users\Legion\OneDrive\Tài liệu\GitHub\A-Multi-Agent-Large-Language-Model-Approach-to-Price-Driven-Stock-Trading-in-the-Vietnamese-Stock-Ma'
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$PSNativeCommandUseErrorActionPreference = $false

py -3.13 -X utf8 scripts/prepare_mt_bicl_teacher.py check-inputs
if ($LASTEXITCODE -ne 0) { throw "Input teacher v2 không hợp lệ." }

py -3.13 -X utf8 scripts/prepare_mt_bicl_teacher.py verify
if ($LASTEXITCODE -eq 2) {
    Write-Host 'Integrity đã kiểm; teacher vẫn STOP do EM chưa hội tụ. Không chạy W10-11.'
} elseif ($LASTEXITCODE -ne 0) {
    throw "Kiểm teacher v2 gặp lỗi kỹ thuật."
}
```

Lượt thực thi đã dùng `run --resume` rồi `verify --replay`; không cần chạy
lại fit. Replay hiện chỉ tái dựng200 vòng cùng dữ liệu/source, không mở
corpus hoặc chạy optimizer. **Tại mốc STOP200, W10 đạt9/14 DONE và chặn W10-11;
trạng thái hiện hành sau amendment ở dưới.**

### Hoàn thiện bằng amendment v2.1, 28/10/2026

**W10-10 DONE về teacher/oracle/audit; chưa nghiệm thu learner hoặc hiệu quả
thị trường.** Amendment [protocol_v2_1.json](protocol_v2_1.json) được khóa
trước fit bằng commit `ab59534` (bản UTF-8 cuối), SHA-256
`16f31de4f3d3a24d36b059ae1929001b618f3805a7fb95a2cd8d969bae3a8952`.
Chỉ nâng trần200→1.000; giữ uniform init, tolerance<10⁻¹⁰, grid/Dirichlet,
train membership, RNG/sampler, gate và ngân sách. Hai file STOP200 và toàn
bộ source v2 giữ nguyên, CLI cũ vẫn đối soát được; không warm-start từ π
chưa hội tụ. Đây là amendment sau quan sát solver, không reset exposure.

Fitter/caller mới tại `core/mt_bicl_v21_teacher.py`,
`core/mt_bicl_v21_preparation.py`, `scripts/prepare_mt_bicl_teacher_v21.py`;
helper toán/oracle/sampler/PPC/budget dùng nguyên v2. Code loader kiểm hash
amendment trong đúng commit trước khi fit, chỉ áp dụng một delta số vòng;
schema/namespace kết quả mang v2.1. Không sửa byte protocol v2 hoặc grant.

**Fit thật:** đúng731 cycle/48 block (293 thắng/438 thua), hội tụ tại
**vòng237**, max|Δπ|=**9,827133551354×10⁻¹¹ <10⁻¹⁰**. Trace0…200
**trùng từng giá trị** với lần STOP cũ. Scalar EM độc lập dùng tích predictive/
`math.fsum` chạy đúng237 vòng: max sai khác π **2,36755×10⁻¹⁴**, sai khác
delta cuối **3,88578×10⁻¹⁶**. Không thử recipe, init hoặc grid khác.

Audit prior-predictive **1.000 replicate** đã hoàn tất. Giữ rõ các bất lợi:

| Thống kê train task | Quan sát | Khoảng95% prior-predictive | Đối chiếu |
| --- | ---: | --- | --- |
| Mean rate theo cycle | 0,400821 | [0,369357;0,496683] | Trong khoảng |
| Variance rate theo task | 0,014235 | [0,030019;0,067176] | **Dưới khoảng** |
| Quantile5% rate task | 0,240441 | [0;0,207778] | **Trên khoảng** |
| Median rate task | 0,381944 | [0,341667;0,500000] | Trong khoảng |
| Quantile95% rate task | 0,571429 | [0,666667;0,975000] | **Dưới khoảng** |
| Task toàn thắng / toàn thua | 0 /0 | [0;0,0625] /[0;0,083333] | Trong khoảng |

Teacher sinh phân phối task rộng hơn quan sát train; audit này **không xác
nhận giả định mô hình phù hợp thị trường**. Protocol đã quy định PPC là
diagnostic, không gate release theo metric thị trường; giữ bất lợi, không
đổi grid/π để làm đẹp audit. W10-12 vẫn phải báo teacher/student−teacher/
baselines trên2022, trước mọi claim về lợi ích.

Đã seal sáu corpus cố định: diagnostic1.000, tiny-set32, validation5.000,
validation-swap5.000 cặp, test5.000, test-swap5.000 cặp. Mỗi validation/test/
swap giữ4.500 generative+500 stress. Oracle hierarchical và shared-θ pooling
đối chiếu scalar cho **62.074 dự báo** (gồm10 fixture uniform), max sai khác
p/logp1/logp0 lần lượt **1,99840×10⁻¹⁴ /7,10543×10⁻¹⁴ /5,15143×10⁻¹⁴**,
đều dưới10⁻¹². Swap eligible cố định theo |Δoracle|≥0,05:
**1.984/5.000 validation, 2.106/5.000 test**, đủ≥200, không sinh bù.

Đối chứng hằng dùng p=Σπμ=**0,432570852318** trên validation có mean KL
**0,037753805359**, P95 error **0,290391830834**, không đạt các ngưỡng0,02/
0,10; teacher không phẳng theo phép kiểm này. Lượt audit đã xem oracle và
control hằng của corpus, kể cả test; **chưa có student, student forward
hoặc metric student test**. Không thay recipe/seed/gate sau audit. Test
student và test-swap vẫn chỉ được forward sau seal selection W10-12.

Tám file khoa học frozen tại namespace ignored
`outputs/bayesian_benchmark/mt_bicl_v2/teacher_v2_1/`, tổng **181.572.585 byte**:

| File | SHA-256 |
| --- | --- |
| [teacher_fit.json](../../../outputs/bayesian_benchmark/mt_bicl_v2/teacher_v2_1/teacher_fit.json) | `7a89978336d1307d2b65a8a9712a26792451900f78351ba8bf03bf5ee277dc78` |
| [diagnostic.json](../../../outputs/bayesian_benchmark/mt_bicl_v2/teacher_v2_1/diagnostic.json) | `7b6435e3839c1953ef2e7e1ad3feb2dcabd2f51fed8c26b83d89a8c2a915caf2` |
| [pilot_tiny.json](../../../outputs/bayesian_benchmark/mt_bicl_v2/teacher_v2_1/pilot_tiny.json) | `91b1908f2253241593bb6ea97167f9ff84a75eb90d22db8bf7128c73bd087b2d` |
| [synthetic_validation.json](../../../outputs/bayesian_benchmark/mt_bicl_v2/teacher_v2_1/synthetic_validation.json) | `b5a761f7ac6b41cae4eb5a6af2fa8a57dbdf033c068b5fca40566eb5cb8d8721` |
| [validation_swap.json](../../../outputs/bayesian_benchmark/mt_bicl_v2/teacher_v2_1/validation_swap.json) | `8e5ee3dcb60a5125b480a01a1ff607cfe39f2c7ddfab87bfd5130146bdfd43ac` |
| [synthetic_test.json](../../../outputs/bayesian_benchmark/mt_bicl_v2/teacher_v2_1/synthetic_test.json) | `f19db2a4678098fd5a7196d1b2789f202deedbfec45133e73501721a0de2bbec` |
| [test_swap.json](../../../outputs/bayesian_benchmark/mt_bicl_v2/teacher_v2_1/test_swap.json) | `06432c5f0a4fd783c70adc1b019cd4acea5428a35242cb2cd28d14d5bbc739d1` |
| [index.json](../../../outputs/bayesian_benchmark/mt_bicl_v2/teacher_v2_1/index.json) | `a1e20a1fe4036a6fc660b25302908efcac92cf08c241233b36284c9fbc18ed83` |

Identity canonical:
`9b8487a9736fd33412c839cd2285b95ae6e205715fd67b9efd7e9cbd5664bba8`.
Index `COMPLETE_TEACHER_ORACLE_ONLY`; training/development/Decision=false.
Giữ chung `active_budget_v2.json` và OS lock rootv2, không reset phần cũ.
**Cold replay CPU PASS, CLI exit0:** dựng lại toàn bộ teacher/237 vòng EM,
PPC1.000 replicate và sáu corpus; so toàn payload với artifact đã khóa.
Snapshot ngân sách sau fit+replay là **254,885267 giây active chung**,
đã bao gồm0,183225 giây của lượt STOP200, còn dưới14.400 giây. Đây không
phải tổng công sức quỹ10 giờ. Đồng hồ công việc lượt amendment tới mốc QA
ghi **800,025 giây ≈13 phút20 giây**, bao gồm active trong lượt này;
cộng lower bound1.227,546 giây lượt trước là≥**2.027,571 giây** đã quan sát,
chưa gồm các khoảng chưa đo và hoàn tất sau QA; không tính active hai lần.

**Kiểm tra theo phạm vi:32 test PASS**, gồm6 test amendment/caller mới,
18 teacher/sampler/leakage v2 và8 bank leakage; **15 trong các suite leakage**.
Biên dịch đúng4 file Python mới PASS. Prereg/hash/CLI check-inputs/UTF-8/
link/checklist/diff PASS; không chạy toàn suite/E2E/compileall. Windows Temp/
OS lock cần quyền ngoài sandbox như trước. Không GPU, optimizer hoặc API;
77 file v1, hai file STOP200, source cũ, protocol/manifest/grant/ledger
nguyên byte. Kết quả51 test của lượt v2 phía trên là lịch sử, không cộng
thành số test vừa chạy lại trong lượt amendment này.

Không cần chạy GPU. Lệnh tái kiểm hiện hành từ đầu đến cuối:

```powershell
Set-Location -LiteralPath 'C:\Users\Legion\OneDrive\Tài liệu\GitHub\A-Multi-Agent-Large-Language-Model-Approach-to-Price-Driven-Stock-Trading-in-the-Vietnamese-Stock-Ma'
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$env:PYTHONUTF8 = '1'

py -3.13 -X utf8 scripts/prepare_mt_bicl_teacher_v21.py check-inputs
if ($LASTEXITCODE -ne 0) { throw 'Input teacher v2.1 không đạt.' }

py -3.13 -X utf8 scripts/prepare_mt_bicl_teacher_v21.py verify
if ($LASTEXITCODE -ne 0) { throw 'Kiểm teacher v2.1 không đạt; dừng trước W10-11.' }
```

Lượt producer đã dùng `run --resume`, nghiệm thu bằng `verify --replay`;
không cần fit lại. Lệnh replay CPU tái dựng cùng teacher/PPC/sáu corpus,
không update model và được tính vào active budget. W10-11 dùng đúng teacher
v2.1/converged và corpus đã khóa này, chưa mở student test hoặc train lớn.

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
