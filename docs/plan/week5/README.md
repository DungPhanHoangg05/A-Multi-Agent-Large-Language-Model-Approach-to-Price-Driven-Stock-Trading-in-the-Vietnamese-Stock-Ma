# Tuần 5 — Hoàn thiện vận hành và nền tảng Bayesian v2

**Trạng thái: Phase A PASS; 4/16 task hoàn thành — W5-01–04 DONE. Tiếp theo W5-05, Phase B.**
Ngày lập: **07/10/2026**; cập nhật **08/10/2026**. Đã kiểm/tổng hợp offline,
thêm CLI audit và chốt hợp đồng v2; triển khai runtime v2 bắt đầu ở Phase B.
[Kế hoạch tổng](../plan.md) · [Kết quả W4](../week4/README.md) ·
[Hợp đồng API/checkpoint hiện hành](../week4/week_close_and_handoff.md)

## 1. Mục tiêu và đầu vào

Pilot FPT và quota đã được nghiệm thu khi chốt W4. W5 dùng kết quả đó để
hoàn thiện đường chạy chính thức, xử lý các điểm yếu vận hành đã quan sát,
và triển khai nền tảng Bayesian v2 trên **FPT, VNM, VCB, MWG**. Lộ trình
được mở rộng thành **10 tuần**: W6 cải thiện thuật toán, W7 kiểm chứng và
khóa phiên bản, W8 benchmark, W9 thống kê, W10 luận văn. Bốn phase và
16 mã task W5 được giữ; W5-01–04 DONE, triển khai nền tảng v2 vẫn còn TODO.

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
- Năm nhánh v1 của W4 được giữ nguyên để tái lập. Bayesian v2 phải có
  contract/config/identity mới; không đổi tên hoặc ghi đè nhánh Bayesian cũ.
  W5 khóa phân hoạch dữ liệu và kế hoạch nguồn lực; W7 khóa cấu hình ứng viên
  và ma trận cuối trước benchmark W8. K=5 chưa được hỗ trợ và không là gate W5.

### Baseline W4 đã đối chiếu tại W5-01

Kiểm ngày **07/10/2026** bằng `--verify-only`: **complete, 20/20 điểm**.
Code/schema đang dùng khớp cả **31/31 checksum** trong identity và nội dung
commit W4 `27b5907` sau chuẩn hóa newline; **12/12 nguồn** khớp checksum byte.
Python và bảy package trong runtime identity khớp hoàn toàn. Thay đổi tài
liệu sau W4 không làm đổi code/config/source của pilot.

| Đối tượng | SHA-256 đã đối chiếu |
| --- | --- |
| Run signature, khớp identity/manifest/result/audit | `52b6792b872bb8b8f35862d96c458b4234510ffc8c90174686697d8d96cfd33a` |
| Payload plan đã khóa | `f9bf7d234b7c5fd56ea5d30d3fb1f72b5723a38899a1ea6fe0c44f4d1ef91025` |
| Byte `outputs/pilot_fpt_run/results.json` | `e5ee99899bd7dbd3de5ec8292f7bb6b68c50ed30bb9a3bd627be016caa6ad5a0` |

- Cả **20 checkpoint** `complete/shared_complete`, **100/100 nhánh complete**,
  Decision có nguồn `llm_structured`; cùng năm nhánh/seed/scope đã khóa.
  Verifier dựng lại prior/input/prompt/P&L từ nguồn để kiểm semantic, không
  chỉ kiểm envelope hash. Chế độ này dùng MockTransport cấm HTTP và key giả
  nội bộ. Lượt kiểm bổ sung có audit hook chặn mở `.env`/`.env.*`, DNS và
  socket connect cũng PASS: **0 credential-open attempt, 0 network attempt**.
  Kết quả này áp dụng snapshot pilot hiện tại; W5-08 cần kiểm thêm snapshot
  đủ tin vì `sentiment_agent.py` có nạp dotenv khi được import ở đường sentiment.
- Audit tại `outputs/oos_pilot/reconciliation/FPT-2023-03-16.json` có
  envelope hợp lệ, action `USER_AUTHORIZED_REPLAY_OF_UNKNOWN_UPSTREAM_ONCE`,
  status `APPLIED` và completion `VERIFIED_COMPLETE`. Signature/plan/hash
  kết quả cuối khớp. Backup `FPT-2023-03-16.before-replay.json` còn nguyên
  byte và payload hash, giữ stage `upstream_started` của lần chưa rõ kết quả.
- **15 checkpoint trước điểm 16** khớp byte hash trong audit, bảo toàn
  **75 Decision**. Bốn điểm sau replay đã chuyển từ planned sang complete;
  không đòi chúng khớp hash của bản planned trước khi chạy.
- Ledger vẫn có đúng record unknown được audit dẫn chiếu:
  `4718a59f-5d2a-4a62-9ac1-ba21d22f9a54`, model `qwen/qwen3.8-27b`,
  `transport_error`, reserve **5.535**, không có total_tokens/request ID.
  Giữ nguyên ngoại lệ replay; không suy ra provider chưa xử lý request cũ.

**Vị trí cần giữ:** `outputs/pilot_fpt_run/{identity.json,run_manifest.json,
results.json,points/}` và `outputs/oos_pilot/{inputs/,api_usage.json,
reconciliation/}`. Chúng là dữ liệu local gitignore; clone Git riêng không
khôi phục được pilot. SHA nguồn/code/runtime chi tiết đã có trong identity,
không tạo thêm JSON hoặc sao chép receipt vào thư mục kế hoạch.

Sau kiểm verifier/audit và hồi quy, **97/97 file đã chụp checksum còn nguyên
byte**: checkpoint/kết quả, input, audit/backup, ledger, nguồn train/OOS,
code/schema/dependency và ZIP bằng chứng. Metadata `run.owner.json`,
`run.recovery.json`, `run.lock` phục vụ khóa được verifier cập nhật theo
quy trình hiện hành khi cần; chúng không là dữ liệu khoa học đóng băng.

#### Kiểm lại pilot sau khi code W5 thay đổi

Lượt W5-01 dùng môi trường hiện tại vì 31 file được ghim khớp W4. Khi chúng
thay đổi, tạo checkout độc lập của W4 ở **thư mục mới** để kiểm lịch sử:

```powershell
$w4ReviewRoot = Join-Path (Split-Path (Get-Location) -Parent) "kltn-w4-review-27b5907"
git worktree add --detach "$w4ReviewRoot" 27b5907
```

1. Giữ bản gốc; sao chép nguyên byte các input/ledger/audit và file nghiên
   cứu của pilot nêu trên vào đúng đường dẫn tương đối trong worktree.
   Không sao chép lock/owner/recovery; verifier tạo metadata khóa riêng.
2. Đối chiếu 12 đường dẫn `identity.payload.sources.files`. File Git checkout
   có thể khác newline với archive ban đầu; nếu khác hash, phục hồi **byte
   nguồn gốc đã khóa** tại đúng path trong worktree rồi kiểm lại. Giữ cả bộ
   `data/execution_prices_oos/` vì verifier kiểm manifest bốn mã.
3. Dùng Python **3.13.5** và các version dưới đây. Nếu tạo venv mới, cài
   requirements ở commit W4 rồi ghim các version đã ghi; requirements hiện
   không phải lock đầy đủ mọi phụ thuộc. Chỉ coi môi trường phục hồi hợp lệ
   khi verifier và các gate hồi quy PASS, không chỉ vì cài package thành công.

| Nhóm | Version đã xác minh trên máy |
| --- | --- |
| Runtime identity khoa học | numpy 2.1.2; pandas 2.3.3; scipy 1.16.1; TA-Lib 0.6.8 |
| Runtime identity graph/LLM | langgraph 1.0.10; langchain-core 1.2.17; langchain-groq 1.1.2 |
| Model/nguồn | hmmlearn 0.3.3; scikit-learn 1.7.2; vnstock 4.0.9; vnai 2.6.2 |
| Client/tokenizer và hỗ trợ | httpx 0.28.1; tiktoken 0.12.0; Pillow 11.0.0; groq 0.37.1; langchain 1.2.10; python-dotenv 1.2.2 |

Chạy tại root worktree với interpreter đã xác minh:

```powershell
py -3.13 -X utf8 scripts/run_bayesian_ablation.py --verify-only
```

Nếu dùng venv, thay `py -3.13` bằng interpreter của venv. Verifier phải trả
`Pilot complete: 20/20 điểm`; identity mismatch thì dừng để phục hồi đúng
nguồn/môi trường. Phiên bản W4 được giữ riêng; run W5 mới ký bằng code mới.
Tồn tại file lock không đồng nghĩa runner đang chạy: owner/OS lock được
validator kiểm, không cần xóa file lock thủ công.

### Chất lượng và chỉ số pilot — W5-02

Đối chiếu ngày **07/10/2026** bằng API `PriorBacktestRunner.run(...,
verify_only=True)` và `summarize_points`: result dựng lại khớp toàn bộ payload
đã lưu, summary tính từ 20 checkpoint khớp chính xác `results.json.summary`.
API hiện có đủ đầu ra; không thêm script export hoặc receipt.

**Cùng mẫu:** FPT, 20 cutoff 05/01–03/04/2023, exit 10/01–06/04/2023;
19 điểm Q1 và một điểm Q2/2023. Nhãn kinh tế có **6 UP, 14 DOWN**;
UP nghĩa là return LONG sau phí >0, DOWN là ≤0, theo engine hiện hành.
Regime PIT: **BULL 6, CHOPPY 12, CONSOLIDATION 2**.

| Nhánh | N | Đúng/N | Accuracy | LONG / SHORT | LONG có lãi / giao dịch | LONG hit-rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Original K=0 | 20 | 11/20 | 55,00% | 5 / 15 | 1/5 | 20,00% |
| Random K=3 | 20 | 8/20 | 40,00% | 8 / 12 | 1/8 | 12,50% |
| Recent K=3 | 20 | 9/20 | 45,00% | 7 / 13 | 1/7 | 14,29% |
| Similarity K=3 | 20 | 10/20 | 50,00% | 6 / 14 | 1/6 | 16,67% |
| Bayesian K=3 | 20 | 10/20 | 50,00% | 6 / 14 | 1/6 | 16,67% |

Mỗi nhánh có tài khoản riêng **50.000.000 VND**. Một LONG là một vòng
BUY_SELL Open(t+1) → Close(t+3); SHORT giữ CASH. Phí 0,25% và slippage
0,10% mỗi chiều; nhãn/return dùng `compute_round_trip_net_return`, tài khoản
dùng `compute_account_metrics`. Số giao dịch bằng LONG count; hit-rate
có mẫu số là số LONG thực thi, accuracy có mẫu số là cả 20 điểm.

| Nhánh | Equity cuối (VND) | P&L (VND) | Return sau phí | Max drawdown |
| --- | ---: | ---: | ---: | ---: |
| Original | 47.164.521 | -2.835.479 | -5,67% | 5,67% |
| Random | 44.660.682 | -5.339.318 | -10,68% | 10,68% |
| Recent | 45.838.189 | -4.161.811 | -8,32% | 8,32% |
| Similarity | 45.952.943 | -4.047.057 | -8,09% | 8,09% |
| Bayesian | 46.043.617 | -3.956.383 | -7,91% | 7,91% |

VND làm tròn đến đồng, tỷ lệ đến hai chữ số; dữ liệu đầy đủ giữ nguyên trong
checkpoint. MDD là mức giảm dương từ peak trên **21 mốc equity** gồm vốn
đầu và 20 lần đóng chu kỳ; chưa phản ánh drawdown giữa các phiên trong vị thế.
Cuối mỗi nhánh là CASH, final_shares=0.

**Chất lượng dữ liệu/kết quả:** đủ 20/20 common support và 100/100 Decision
`llm_structured`, mọi nhánh complete/error rỗng; không có điểm thiếu bị loại
hoặc Decision lỗi được thay bằng CASH. Cả năm input mỗi điểm cùng shared hash.
Fallback reason của cả 100 Decision là chuỗi rỗng. Lịch sử còn **100 attempt
complete và một attempt failed đã phục hồi**; ngoại lệ upstream điểm 16
vẫn giữ audit/reserve ở baseline W5-01.

**Coverage sentiment:** cả 20 điểm có 0 bài hợp lệ trong cửa sổ 90 ngày,
0/20 điểm reliable theo ngưỡng ba bài; tín hiệu đều NEUTRAL với lý do
`INSUFFICIENT_DATED_HISTORY`. Snapshot FPT có input_count=0, không đủ tin
để đánh giá đóng góp sentiment. Giá/entry/exit, schema, nguồn, PIT và prompt
đã qua verifier; không có dữ liệu kinh tế bị điền mặc định để đủ mẫu.

**Diễn giải:** cả năm nhánh lỗ trên pilot này. Bayesian thấp hơn Original
5 điểm phần trăm accuracy và khoảng 2,24 điểm phần trăm return. Tỷ trọng
nhãn DOWN là 70%, cần đọc accuracy cùng mất cân bằng nhãn và số giao dịch.
Mẫu nhỏ, chỉ đầu 2023, thiếu tin và có replay được xác nhận; chưa chứng minh
ưu thế đầu tư hoặc ý nghĩa thống kê. Giữ pilot/ma trận v1 nguyên vẹn; đề xuất
v2 được đánh giá ở run mới, không chỉnh lại kết quả này cho đẹp hơn.

W5-04 đã chốt cách báo cáo Sharpe/Sortino trước benchmark W8: engine hiện nhân
`sqrt(252)` trên return theo chu kỳ, nên cần rà annualization cho lịch cách
ba phiên. W5-02 giữ metric engine nguyên vẹn, chưa diễn giải hai tỷ số này
như thước đo rủi ro năm hoặc thực hiện kiểm định W9. Báo cáo mới dùng tỷ số
theo chu kỳ và annualized=null theo hợp đồng W5-04 bên dưới.

### Chẩn đoán Bayesian và hướng cải thiện — cập nhật kế hoạch 07/10/2026

Đọc trực tiếp action/evaluation/prior trong 20 checkpoint: **19/20 quyết
định Bayesian giống Original**, chỉ một điểm khác. Không phải cả 20 điểm
đều suy giảm sau khi thêm prior.

| Điểm khác biệt | Original | Bayesian v1 | Kết quả kinh tế |
| --- | --- | --- | --- |
| FPT, cutoff 20/02/2023, CHOPPY | SHORT → CASH | LONG → BUY_SELL | Open 21/02=82,8; Close 23/02=81,4; LONG ròng **−2,3766%**, nhãn DOWN |

Một giao dịch thua thêm này giải thích accuracy 55% →50% và return
−5,6710% →−7,9128%: chênh **−2,2418 điểm phần trăm**, khoảng 1,12 triệu
đồng trên vốn 50 triệu. Đây là quy kết từ action/P&L đã lưu, không phải
bằng chứng về cơ chế suy luận bên trong LLM hoặc kết luận Bayes luôn kém hơn.

**Prior đã có cảnh báo:** population CHOPPY FPT gồm 62 episode đã đóng,
LONG thắng 25/62 (40,3%), bull trap 27/43 (62,8%). Ba ví dụ được chọn có
score=1, cùng tín hiệu Trend/Pattern/Indicator BULLISH và Alpha BEARISH
với query, nhưng đều LONG thua: 01/03/2022 −0,16%, 21/02/2022 −1,77%,
11/02/2022 −0,37%. Chúng cách query khoảng một năm. Decision vẫn LONG;
phần justification đã lưu không đối chiếu định lượng cảnh báo này. Vì
n=62 và score=1, chỉ tăng ngưỡng số mẫu hoặc similarity **không tự sửa ca này**.

| Quan sát trong code/kết quả | Giới hạn và hành động dự kiến |
| --- | --- |
| `regime_empirical_stats_v1` là tỷ lệ mẫu, không smoothing; prompt ghi rõ chưa là posterior LLM hiệu chuẩn | V2 thêm posterior số học và bất định của thống kê lịch sử; không gọi confidence LLM là xác suất đã hiệu chuẩn |
| Stats tính từ toàn population cùng regime; ranking chỉ so bốn nhãn rời rạc với trọng số 0,25 | W6 kiểm thống kê điều kiện theo tín hiệu và đặc trưng giá PIT; cùng nhãn không đảm bảo cùng hoàn cảnh giá |
| Không có ngưỡng similarity; 26/60 ví dụ pilot có score<1 | W5 thêm kiểm chất lượng bằng chứng; W6 đánh giá độ mới và độ đa dạng mà không chọn theo WIN/LOSS |
| Prefix hợp lệ vẫn dẫn đến LONG ở ca cảnh báo | Cần truy vết bằng chứng/khuyến nghị/quyết định, thử cách trình bày và chính sách quyết định ở W6–W7; không đặt luật riêng ép 20/02 phải SHORT |
| 20 điểm một mã, 0 bài tin hợp lệ; cả năm nhánh lỗ | Mở rộng validation có kiểm soát, báo cáo cả giữ tiền mặt và mất cân bằng nhãn; không coi thiếu tin là lỗi parser hoặc nguyên nhân đã chứng minh |

Nghiên cứu về ICL cho thấy lựa chọn ví dụ ảnh hưởng kết quả trên tác vụ NLP
([Liu và cộng sự, 2022](https://aclanthology.org/2022.deelio-1.10/)); vai trò
nhãn/ví dụ cũng phụ thuộc tác vụ và cách xây context
([Min và cộng sự, 2022](https://aclanthology.org/2022.emnlp-main.759/)). Đây là
cơ sở để thử retrieval/prefix, **không chứng minh** cơ chế hay lợi nhuận cho
mô hình giao dịch hiện tại.

#### Phạm vi code v2 bắt buộc trong W5

1. **W5-03 — DONE:** đã thêm phân tích action bất đồng và trace
   support/score/tuổi prior/coverage từ checkpoint, tái lập được ca trên;
   kết quả/lệnh audit ở mục telemetry bên dưới.
2. **W5-04 — DONE:** khóa hợp đồng v2, tiêu chí đánh giá và phân hoạch: 2018–2022
   train/validation cuốn chiếu theo thời gian; 2023 phát triển/thăm dò;
   **2024 đánh giá xác nhận**, không dùng outcome/dự báo 2024 để chọn phiên bản.
3. **W5-08.a–d:** mở CLI hiện có, triển khai thống kê Beta–Binomial,
   kiểm chất lượng prior và prefix v2 có metadata; dùng fixture/mock offline.
   Đường chính sửa tại retriever, Decision builder và prior runner hiện có,
   module phụ chỉ thêm khi thật sự cần; không tạo runner riêng từng tính năng.
4. **W5-13/15:** kiểm công thức/biên/khả năng tái lập/caps/leakage/identity
   và đường không đọc credential; W5-14 vẫn là smoke vận hành v1 bốn điểm,
   không dùng nó để chứng nhận v2 tăng lợi nhuận.

W6 mới triển khai retrieval giàu đặc trưng, thống kê điều kiện và cơ chế
Decision sử dụng bằng chứng; W7 chọn/khóa ứng viên bằng validation. Nếu
ứng viên không cải thiện, vẫn báo cáo kết quả và đóng phần kỹ thuật khi
đủ gate; không lặp điều chỉnh trên 2024 để đạt mục tiêu lợi nhuận.

#### Tái lập bảng từ API hiện có

Tại root repo đúng phiên bản/môi trường W4 đã kiểm ở trên:

```powershell
py -3.13 -X utf8 scripts/run_bayesian_ablation.py --verify-only
if ($LASTEXITCODE -ne 0) { throw "Verifier chưa PASS; dừng đối chiếu bảng" }
@'
import json
from pathlib import Path
from core.prior_backtest import canonical_hash, summarize_points
base = Path("outputs/pilot_fpt_run")
result = json.loads((base / "results.json").read_text(encoding="utf-8"))["payload"]
points = [json.loads((base / entry["path"]).read_text(encoding="utf-8"))["payload"] for entry in result["point_files"]]
summary = summarize_points(points)
assert canonical_hash(summary) == canonical_hash(result["summary"])
for name, item in summary.items():
    metrics = item["account_metrics"]
    print(name, item["sample_count"], item["correct_count"], item["accuracy"],
          item["long_count"], item["short_count"], metrics["hit_rate_pct"],
          metrics["final_equity_vnd"], metrics["total_pnl_vnd"],
          metrics["total_return_pct"], metrics["max_drawdown_pct"])
'@ | py -3.13 -X utf8 -
```

### Telemetry và audit paired — W5-03

Triển khai một CLI phân tích dùng chung:
[`scripts/analyze_prior_run.py`](../../../scripts/analyze_prior_run.py).
API summary trước đây chỉ có metric tài khoản; CLI này bổ sung đối soát
ledger/attempt/trace mà không sửa các file code đang được identity W4 ghim.
Không tạo receipt JSON/Markdown, không ghi vào run hoặc thay khóa.

```powershell
py -3.13 -X utf8 scripts/analyze_prior_run.py --reconciliation-dir outputs/oos_pilot/reconciliation
```

API `analyze_run(output_dir, ledger_path, reconciliation_dir=...)` trả dữ
liệu JSON native để dùng lại. Kiểm envelope/schema/hash của identity,
manifest/result/point, toàn common support, shared pairing, nhãn/P&L qua
engine và summary; kiểm backup/15 điểm cũ/reserve khi có audit replay.
Đây là audit trên checkpoint đã lưu; verifier semantic phiên bản W4 vẫn
cần dùng theo hướng dẫn mục baseline, không coi audit là thay thế verifier.

#### HTTP và token đã đối soát

| Model | HTTP attempt / 200 / unknown | Input đã báo | Output đã báo | Total đã báo | Reserve còn giữ | Charged v1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `openai/gpt-oss-20b` | 103 / 103 / 0 | 178.591 | 15.627 | 194.218 | 0 | **194.218** |
| `qwen/qwen3.8-27b` | 44 / 43 / 1 | 90.826 | 5.673 | 96.499 | **5.535** | **102.034** |

- **147 attempt, 146 HTTP 200, 0 HTTP 429**, một `transport_error` không
  có usage/request ID. Total vision chỉ là 43 response có usage; request
  chưa rõ kết quả vẫn giữ reserve, không được tính như gọi miễn phí.
- Tổng reserve đặt trước qua các request: text **440.256**, vision
  **229.552** token. Đây không phải usage thực hoặc reserve đang chiếm quota:
  response có total_tokens dương đã được thay bằng usage trong phép charged.
  Audit tái lập policy v1 `total_tokens or reserved_tokens`; trường hợp
  provider báo total=0 vẫn phân biệt actual=0 nhưng charged còn reserve,
  không âm thầm thay cách tính của guard trong task này.
- **100 HTTP** ghép chắc chắn vào cửa sổ attempt Decision; **hai request
  preflight** có ID còn được ledger dẫn chiếu. **Bốn request trước manifest**
  chưa có nhãn durable; **41 request trong run ngoài cửa sổ Decision** chưa
  có role/point ID. Lịch sử W4 ghi sáu preflight, nhưng audit không tự gán
  bốn request đầu bằng heuristic số token. Scope bảng là **toàn ledger
  được cung cấp**, không tự coi mọi request là chi phí riêng của Decision.
- Checkpoint giữ **100 attempt Decision complete +một failed**, 100 Decision
  hợp lệ; failed trước HTTP có cửa sổ không gắn request. Không có HTTP thêm
  trong cửa sổ Decision. Ledger chưa có counter riêng cho format retry,
  nên field này là `null`, không tuyên bố mọi graph có zero format retry.
- Có **20 shared point và 20 Full bundle durable**; invocation upstream/Full
  chính xác không được ghi riêng. Kiểm được một audit replay upstream đã
  áp dụng, không biến stage hoặc replay thành bảo đảm exactly-once provider.

#### Thời gian: phân biệt số đo và phần chưa có

| Số đo | N | Tổng (giây) | P95 (giây) | Phạm vi |
| --- | ---: | ---: | ---: | --- |
| HTTP text 200 | 103 | 122,358 | 2,093 | Cả preflight trong ledger |
| HTTP vision 200 | 43 | 62,814 | 2,038 | Chỉ response thành công |
| HTTP vision gồm unknown | 44 | 5.590,235 | 2,131 | Unknown có latency 5.527,421 giây; giữ riêng outlier |
| Graph Decision hoàn tất | 100 | 4.047,129 | 52,017 | Gồm chuẩn bị/nghỉ/HTTP trong graph, không chỉ HTTP |
| Cửa sổ attempt Decision | 101 | 4.041,266 | 51,960 | Timestamp start/finish gồm một failed |
| Span Decision đầu →cuối từng điểm | 20 | 5.045,516 | 253,683 | Không là thời gian toàn điểm, thiếu đầu upstream |

P95 nội suy tuyến tính; median graph Decision **50,767 giây**, median span
**245,198 giây**. Span toàn ledger **14.249,359 giây** gồm khoảng ngắt/resume
và request trước run; không là thời gian CPU hay pacing. Các tổng trên có
phạm vi chồng nhau, **không cộng lại** làm tổng thời gian chạy.
Latency HTTP là elapsed transport đã ghi, không là thời gian xử lý GPU;
latency của unknown không chứng minh provider đã xử lý request bao lâu.

**Pacing, retrieval và thời gian toàn điểm của pilot: chưa có timer riêng,
trả `null`.** Không lấy graph−HTTP hoặc khoảng trống timestamp để khẳng
định thời gian nghỉ quota. Receipt p95 retrieval W4 vẫn giữ nguyên ở mục
đầu; đó là benchmark riêng, không là latency retrieval của từng pilot point.
W5-04 đã chốt role/point/attempt/preflight và timer riêng cho run phiên
bản mới bên dưới; phần đo runtime thuộc Phase B, không thêm telemetry ngược
vào checkpoint W4 đã đóng băng.

#### Trace quyết định và kiểm tính bất biến

Audit xuất metadata của **đủ 20 điểm**, không chỉ ca thua; CLI in gọn ca
bất đồng duy nhất **FPT-2023-02-20, SHORT →LONG**, LONG ròng **−2,376584%**,
chênh return tài khoản **−2,241809 điểm phần trăm**. Population=62,
requested/selected K=3/3, ba score=1; tuổi từ ngày quyết định prior là
**356/364/374 ngày**, tin 0, không reliable. Các metric lịch sử/query signals,
ngày exit và tuổi exit cũng có trong API; tuổi tính theo ngày lịch tại query.

Lý do structured được tham chiếu bằng field/độ dài/SHA-256 và vị trí
`branches.<branch>.decision.normalized_response` trong checkpoint; không
in prompt/raw response/nội dung tự do vào báo cáo. Không suy đoán suy luận
ẩn hoặc dùng outcome query cho selection. Lỗi pairing, sai return/nhãn,
exit_date ≥cutoff, thiếu checkpoint hoặc run dở đều dừng bằng lỗi.

Kiểm CLI với audit hook cấm mở `.env`/`.env.*`, DNS/socket: **0 credential
attempt, 0 network attempt**. Verifier semantic W4 kiểm lại riêng PASS,
**20/20 điểm**; **82/82 file** bảo vệ code/schema/input/checkpoint/ledger/
audit/backup/bank/model/ZIP khớp byte trước và sau. Metadata lock/owner/
recovery của verifier không thuộc tập đóng băng. Nghiệm thu: **15 test mới**,
compileall/E2E, **536 unit/93 leakage PASS**; không tạo receipt mới.

### Hợp đồng vận hành và đánh giá — W5-04, chốt 08/10/2026

**Phạm vi quyết định:** đặc tả `research_evaluation_contract_v2` cho các
run mới. W5-04 chốt hợp đồng; code posterior/gate/telemetry/metric v2 còn
phải triển khai ở 05–08 và kiểm ở 13–15. V1 và số liệu W4/W5-02/03 được
đọc bằng phiên bản đã ghim. Không tạo schema JSON chưa có consumer; khi
triển khai, mở schema/validator hiện có theo version và kiểm fixture.

#### Vận hành, dừng và resume

| Tình huống | Hành vi bắt buộc của run mới | Đầu việc triển khai |
| --- | --- | --- |
| Dry-run/verify/audit | Không nạp credential hoặc mạng; kiểm plan, source, signature và version trước thực thi | 08.a, 13 |
| Trước HTTP | Mọi đường gọi qua `_invoke_with_retry` và transport guard chung; lưu reservation durable trước gửi, có role/attempt ID | 05, 07, 08 |
| RPM/TPM cần nghỉ | Pacing chủ động, sleep mỗi lần ≤30 giây; tính lại quota sau mỗi lần nghỉ, ghi thời gian thực đã nghỉ | 05 |
| HTTP 429 xác định bị từ chối | Giữ usage/reserve và retry-after; chỉ retry nếu tổng chờ cho invocation ≤120 giây và còn quota. Backoff tối thiểu 5×2^(j−1) giây cho retry thứ j; lấy max với retry-after +1 giây | 05, 07 |
| Hết RPD/TPD, một request vượt TPM, hoặc chờ >120 giây | Dừng có kiểm soát, ghi reason/resume_not_before_utc nếu biết; không tự lặp invocation để vượt trần chờ | 05 |
| Usage thực vượt reserve | Ghi usage thật và giữ response đã nhận; dừng trước request tiếp theo để rà estimator/policy, không làm mất chi phí hoặc gọi lại response thành công | 05, 07 |
| Timeout/disconnect/5xx không rõ đã xử lý | Dừng AMBIGUOUS, giữ reserve unknown. Không tự gửi lại upstream/Full; Decision cũng cần đối soát trạng thái trước một attempt mới | 07 |
| Đã nhận response nhưng chưa checkpoint hoàn tất | Lưu response durable; parse/khôi phục từ response đó, không gọi lại HTTP. I/O retry hữu hạn cho lỗi có thể phục hồi; hết retry thì dừng | 06, 07 |
| Decision đã nhận nhưng không hợp lệ về format | Parse deterministic trước; tối đa một format repair có gọi LLM, input khoa học giữ nguyên, ghi attempt riêng. Hết ngân sách thì FAILED; không đổi thành CASH hoặc retry đến khi có action mong muốn | 07, 08 |
| Hash/schema/PIT/economic/cap sai; HTTP 400/401/403 | Dừng ngay, không retry bằng backoff; lỗi liêm chính là ValueError/AssertionError | 05–08, 13 |
| Owner/OS lock còn sống | Chặn runner thứ hai; không xóa lock thủ công. Khóa quota dùng chung cho các run trong cùng phạm vi tài khoản | 05–07 |
| Nhánh complete / điểm complete | Tái dùng nguyên byte; các nhánh còn thiếu nhận deep-copy cùng shared bundle | 07, 08 |

Ngân sách tự retry được chốt **tối đa ba HTTP attempt/invocation**, bao gồm
format repair nếu có; không nhân ba ở cả wrapper, SDK và format fallback.
Repair có invocation con nhưng dùng chung `budget_root_invocation_id` và
ngân sách ba attempt của invocation gốc, không mở thêm ba attempt riêng.
SDK đặt `max_retries=0`. Quota/policy được kiểm trước từng attempt; 120 giây
là tổng chờ quota/backoff của invocation, không chỉ từng sleep. Upstream có
response lỗi format phải dừng để kiểm response đã lưu; không tự tạo graph
upstream mới. Invocation mới khi resume phải có parent/reason và điều kiện
chờ đã thỏa; không reset lịch sử quota/attempt để né ngân sách. Replay unknown
cần xác nhận cụ thể và audit; ngoại lệ W4 không là quyền replay chung.

Identity dùng canonical JSON hữu hạn và SHA-256; khóa cohort/lịch/matrix,
source/model/bank, code/schema/runtime, template/caps, metric/gate/retry/quota
policy và tham số. Đổi bất kỳ yếu tố khoa học này tạo **run mới**; không sửa
signature cũ. Key được nạp khi tạo client, không lưu key/hash key trong identity
hoặc telemetry; đổi key cùng tổ chức vẫn dùng ledger cũ. Quan sát giới hạn
provider thấp hơn chỉ được siết guard/dừng, không nới vượt giới hạn đã khóa.
Nâng giới hạn sử dụng hoặc đổi model cần config/run mới; lịch sử unknown giữ lại.
Giá trị quota chủ tài khoản đã cung cấp vẫn là đầu vào, phải kiểm trước run thật.

#### Dữ liệu và chọn phiên bản

- **2018–2022:** dữ liệu train/model và bank đóng băng; validation cuốn
  chiếu 2020–2022 dùng `historical_prefix` tại từng cutoff. Tham số fit bằng
  phần quá khứ của fold; loại mọi episode có exit_date ≥cutoff. Không fit
  scaler/HMM cuối 2022 rồi dùng đánh giá query 2020/2021.
- **2023:** development/thăm dò, bao gồm pilot đã quan sát. Smoke vận hành
  chọn tại đây, tách riêng khỏi cohort so sánh development. Không thêm nhãn
  2023 vào bank 852 episode trong giao thức này.
- **2024:** holdout xác nhận. W5-09/10 kiểm lịch/eligibility/coverage; outcome
  chỉ evaluator được đọc sau Decision. Không dùng lợi nhuận, nhãn, dự báo
  hay thống kê thắng/thua 2024 để chọn mẫu/ứng viên. Cohort khóa ở W5-12;
  phiên bản, giả thuyết, ma trận và ngân sách khóa ở W7 trước lượt chạy holdout.
- Nếu phát hiện cohort đã được xem outcome để tuning, ghi nhận exposure,
  hạ claim thành exploratory và chốt lại thiết kế trước API; không tự gọi
  một tập đã dùng lựa chọn là holdout. Mọi giao dịch holdout phải có entry/exit
  thuộc 2024; loại cutoff cuối năm thiếu exit theo lịch, không theo return.

Năm nhánh v1 tiếp tục dùng cho smoke W5. V2 là `bayesian_v2`, chỉ mở ma trận
v1+v2 khi runner/schema mới được kiểm. Original giữ cùng reports/template;
một upstream/Full bundle thành công cho mỗi point, deep-copy cho tất cả nhánh.
Cỡ mẫu và ma trận cuối còn thuộc W5-10/11 và W7, chưa được chứng nhận khả thi
chỉ vì Phase A PASS. Cùng lịch từng mã giữa các nhánh, cách cutoff ≥3 phiên.

#### Metric, common support và annualization

Schema báo cáo dự kiến có `report_version=paired_research_report_v2`, `run_signature`, `cohort_id`,
`split` (`train_validation`/`development`/`holdout`), `matrix`, `metric_version`,
`planned_count`, `complete_count`, `pending_point_ids`, `status`, `by_symbol`,
`primary`, `coverage`, `limitations`. Status `COMPLETE` chỉ khi đủ mọi điểm
và nhánh trong plan. Điểm dở giữ nguyên trong mẫu số planned, không điền
action/return=0. Bảng common support tạm có thể in với nhãn `PROVISIONAL`,
nhưng primary xác nhận phải `null`/`INCOMPLETE` đến khi đủ plan; không âm thầm
loại các ngày lỗi hoặc thay ngày dễ hơn. Analyzer v1 hiện chỉ nhận complete.
Với smoke v1 không có v2, `primary=null`, `primary_status=NOT_APPLICABLE`;
vẫn có thể COMPLETE về vận hành. Holdout xác nhận bắt buộc có Original và
bayesian_v2 trong matrix. Primary không áp dụng không được ghi là bằng zero.

| Metric đã chốt | Định nghĩa và xử lý biên |
| --- | --- |
| Primary từng mã | ΔR = R_bayesian_v2 − R_original, đơn vị điểm phần trăm; R lấy tài khoản engine sau phí trên cùng cohort |
| Primary bốn mã | Trung bình đều bốn ΔR (trọng số 1/4), chỉ khi cả bốn mã COMPLETE; là trung bình so sánh theo mã, không là return portfolio |
| Tài khoản/P&L | Mỗi mã ×nhánh có vốn riêng 50 triệu; LONG Open(t+1) →Close(t+3), SHORT CASH, phí/slippage hai chiều. Nhãn dùng `compute_round_trip_net_return`; tài khoản dùng engine |
| Accuracy / balanced accuracy | Accuracy đúng/N; balanced accuracy=(recall UP +recall DOWN)/2. Thiếu một lớp thì balanced accuracy=null kèm reason, không bỏ lớp thiếu |
| LONG hit-rate / participation | LONG có return ròng >0 /số LONG; không có LONG thì hit-rate=null. Participation=LONG/N; CASH=SHORT/N; N=0 thì tỷ lệ=null |
| MDD | Mức giảm dương lớn nhất trên equity đầu vốn và các mốc đóng chu kỳ; ghi `valuation_basis=cycle_close`, không gọi là MDD intraday hoặc daily mark-to-market |
| Tham chiếu CASH | Return/P&L/MDD=0, cuối kỳ 50 triệu, participation=0, accuracy theo nhãn DOWN; hit-rate/Sharpe/Sortino=null. Đây là chính sách tham chiếu, không là action thay thế cho lỗi LLM |
| Theo mã/regime | Ghi N/số LONG/missing đầy đủ. Pooled accuracy là micro đúng/tổng N; macro là trung bình metric từng mã, ghi số mã hợp lệ. Primary không tự bỏ mã thiếu |
| Confidence | Giữ nhãn chữ gốc, không đổi Cao/Vừa/Thấp thành số để tính Brier. Posterior của tỷ lệ lịch sử không tự trở thành xác suất dự báo query |

**Quyết định annualization:** engine v1 lấy `std(period_returns, ddof=0)`
và `sqrt(252)`; Sortino lấy std của riêng các return âm. Vì chuỗi này là
return chu kỳ và lịch chọn có thể thưa, **không dùng hai field v1 làm tỷ số
rủi ro năm trong báo cáo chính thức**. Giữ số v1 trong kết quả lịch sử với
nhãn `legacy_engine_metric`; không sửa công thức P&L hoặc ghi lại pilot.

Metric report mới `cycle_risk_metrics_v2` dùng chuỗi r_i theo các chu kỳ
đã hoàn tất của cùng cohort, **bao gồm zero khi CASH**, target/risk-free=0:

- `sharpe_cycle = mean(r) / std(r, ddof=1)`.
- `downside_deviation_cycle = sqrt(mean(min(r_i, 0)^2))` với mẫu số là
  toàn bộ N chu kỳ; `sortino_cycle = mean(r) / downside_deviation_cycle`.
- N<2 hoặc mẫu số ≤1e−12: tỷ số `null` và `INSUFFICIENT_SAMPLE` hoặc
  `ZERO_DENOMINATOR`; không xuất infinity hoặc zero giả. Đơn vị `cycle`,
  `annualization_factor=null`, `sharpe_annualized=null`, `sortino_annualized=null`.
- Không thay √252 bằng √84 cho lịch thưa/khác nhau giữa mã. Nếu cần metric
  năm, phải đặc tả và kiểm riêng chuỗi equity định giá mỗi phiên cùng cash
  gap; ngoài phạm vi W5 hiện tại. Các tỷ số chu kỳ là chỉ số phụ có giới hạn
  về phụ thuộc thời gian, không quyết định chọn phiên bản bằng một pilot nhỏ.

Kiểm định/CI thực hiện ở W9: so sánh chính v2–Original, báo ΔR từng mã và
trung bình bốn mã; block bootstrap bảo toàn ghép cặp và cụm cùng ngày giữa
mã. So sánh phụ với v1/Random/Recent/Similarity và sensitivity phải ghi riêng,
chốt điều chỉnh nhiều so sánh ở W7. Kết quả không ý nghĩa hoặc kém hơn vẫn
được công bố; gate kỹ thuật không yêu cầu return dương hoặc p<0,05.

#### Hợp đồng evidence và gate v2

| Nhóm | Fields / ràng buộc chốt cho W5-08 |
| --- | --- |
| Version | `evidence_contract_version=prior_evidence_v2`, `statistics_version=regime_beta_binomial_v2`, `gate_version=prior_quality_gate_v1`, `prefix_version=compact_brpp_v2`; thay ý nghĩa field/công thức phải đổi version |
| Provenance | `symbol`, `as_of_date`, `regime`, `population_scope=same_symbol_same_regime_pit`, `bank_sha256`, `config_sha256`, `evidence_sha256`; SHA từ payload canonical hữu hạn, evidence hash không tự chứa chính nó |
| Population | `eligible_count`, `population_count`, `quality_candidate_count`, `selected_ids`, `selected_scores`; lọc PIT trước mọi ranking/stats; population là toàn kho hợp lệ cùng mã/regime, không lấy K làm n |
| Từng tỷ lệ | `metric_id`, `success_count=s`, `support_count=n`, `raw_rate`, `prior_alpha`, `prior_beta`, `posterior_alpha`, `posterior_beta`, `posterior_mean`, `credible_interval`, `status`; int native 0≤s≤n |
| Interval | Object `level=0.95`, `method=equal_tailed_beta`, `lower`, `upper`; finite trong [0,1], lower≤upper. Không gọi interval lịch sử là forecast interval |
| Selection/gate | `requested_k`, `effective_k`, `status`, `reason_codes`, tuổi ngày lịch từ prior as_of_date tới query và exit_age; 0≤effective_k≤requested_k≤3, số task/IDs/score phải khớp |
| Trạng thái gate | `READY`, `DISABLED`, `INSUFFICIENT_EVIDENCE`; reason enum `PRIOR_DISABLED`, `NO_HISTORY`, `LOW_SUPPORT`, `NO_QUALITY_CANDIDATE`. Lỗi cấu trúc/leakage không phải insufficient evidence |

Định nghĩa s/n giữ đúng v1: LONGwin là WIN_IF_LONG/toàn population; Trap là
LOSS khi Trend hoặc Pattern bullish/đếm hợp Trend hoặc Pattern bullish;
TrendFail và PatternFail
là LOSS khi agent tương ứng bullish/đếm agent bullish. Mỗi cycle đếm một lần
trong mỗi metric, không cộng các metric thành các quan sát độc lập.
Ứng viên ban đầu **α=β=1**; khi n>0, posterior Beta(α+s, β+n−s), interval
lấy quantile 0,025 và 0,975, metric status=OBSERVED. Khi n=0: raw/posterior/interval trả null,
status=NO_HISTORY, giữ α/β để truy vết; không trình bày prior rỗng như đã có
dữ liệu. Metric có n=0 không tự làm gate toàn population FAIL; prefix hiển
thị N/A cho tỷ lệ đó. `posterior_mean` chỉ ước lượng tỷ lệ lịch sử dưới giả
định Bernoulli; các cycle phụ thuộc nên interval chưa được bảo đảm calibration.

Config ứng viên kỹ thuật ban đầu, chưa được xác nhận tăng hiệu quả:
`min_population_count=20`, `min_similarity=0.75`,
`max_prior_age_days=730`, `requested_k=3`, `seed=42`, `scope=same_symbol`.
Đây là điểm xuất phát để triển khai/validation, không suy ra tối ưu từ pilot;
ngưỡng thay đổi chỉ qua run development mới rồi khóa ở W7. Score hiện dùng
signal_match_v1; đổi metric ở W6 phải version/config riêng.
Validator yêu cầu α/β hữu hạn >0, min_population_count và max_prior_age_days
là int ≥1, min_similarity hữu hạn trong [0,1], requested_k là int 0..3;
bool không được dùng thay int. raw_rate=s/n và posterior phải khớp counts.

Gate kiểm population≥20 và lọc candidate có score≥0,75, tuổi≤730; equality
được nhận. Giữ thứ tự ranking/tie-break xác định hiện có, lấy tối đa K trong
candidate đạt. K=0 →DISABLED; không có history/thiếu support/không candidate
đạt →INSUFFICIENT_EVIDENCE, effective_k=0 và prefix rỗng như Original, nhưng
Decision attempt riêng. Khi có 1–2 candidate tốt, dùng đúng 1–2 thay vì bù
ví dụ kém; ghi effective_k thật. effective_k là kết quả của gate đã khóa,
không thay requested_k/config giữa run. Khi nhiều reason, lưu theo thứ tự NO_HISTORY,
LOW_SUPPORT, NO_QUALITY_CANDIDATE; DISABLED có ưu tiên cao nhất.
Stats vẫn từ population trước lọc chất lượng; luôn ghi cả hai count để tránh
hiểu n là số ví dụ đủ mới. W6 thay population điều kiện phải version riêng.

News coverage chỉ là diagnostic khi tin thiếu; không tự tắt prior do toàn
bank hiện NEUTRAL. Không chọn ví dụ theo WIN/LOSS hoặc outcome query, không
ép SHORT theo win-rate<50%. Ca FPT n=62/score=1 vẫn có thể qua gate này;
cách Decision sử dụng bằng chứng còn thuộc W6–W7. BRPP≤600, prompt<6.500;
prefix quá cap dừng để sửa formatter/config, không âm thầm xóa uncertainty
hay thay K giữa run. Các metadata đầy đủ ở checkpoint, prefix chỉ tóm tắt.

#### Telemetry của run mới

Contract `research_telemetry_v2` mở rộng ledger/checkpoint hiện có, không
tạo một file/receipt cho mỗi request hoặc span. Counter được dựng từ ID
duy nhất của record durable; resume không cộng lại event đã lưu.

| Record | Fields và ý nghĩa |
| --- | --- |
| Liên kết | `run_signature`, `cohort_id`, `session_id`, `point_id`, `branch_id`, `invocation_id`, `budget_root_invocation_id`, `attempt_id`, `http_attempt_id`, `parent_attempt_id`; point/branch=null chỉ cho preflight hoặc stage chưa có nhánh, phải có stage giải thích |
| Vai trò | `stage` trong preflight/upstream/full/decision; `role` trong probe_text/probe_vision/indicator/pattern/trend/alpha/sentiment/decision. Ghi ở caller, không đoán từ model/token/timestamp |
| Invocation | `started_at_utc`, `finished_at_utc`, `status` started/complete/failed/unknown; mỗi lần vào graph ghi một invocation, HTTP retry/format repair có parent riêng, không lấy HTTP count thay graph count |
| HTTP | `model`, `status_code` nullable, `outcome_status` reserved/complete/rejected/unknown/cancelled_before_send, provider request ID nullable; reserve input/output, actual input/output/total nullable, charged và usage_basis; headers quota đã allowlist |
| Preflight/repair/replay | Lịch sử append có `purpose`, parent và ID; không ghi đè chỉ giữ preflight cuối. Format repair và replay phải phân loại rõ; replay tham chiếu audit xác nhận |
| Thời gian | `http_elapsed_seconds`, `pacing_seconds`, `backoff_seconds`, `inter_branch_wait_seconds`, `retrieval_seconds`, `point_active_seconds`, `point_wall_span_seconds`; numeric finite ≥0 hoặc null kèm missing_reason/coverage |

Đo elapsed bằng monotonic trong cùng session; UTC phục vụ đối soát, không
thay elapsed nếu đồng hồ đổi. HTTP bắt đầu sau pacing và kết thúc khi đọc
xong response/lỗi; pacing đo sleep thực trong guard, backoff đo sleep retry,
inter-branch wait đo chờ giữa nhánh. Retrieval chỉ bao quanh truy xuất đã
lọc PIT, tách với HTTP. Point active là tổng các đoạn monotonic hoạt động
qua session; point wall span từ lần bắt đầu đầu tiên đến hoàn tất, gồm thời
gian dừng/resume. Crash mất timer kết thúc thì đoạn đó là unknown và active
tổng chưa đầy đủ; không dùng zero hoặc lấy wall span làm active. Timer stage
có thể bao nhau, chỉ cộng các đoạn không chồng theo cùng định nghĩa.

JSON dùng Python native, allow_nan=False; thống kê có count/missing_count,
sum/median/p95/max (p95 nội suy tuyến tính). Không có số đo thì null; có đo
và không nghỉ thì 0. Usage thiếu/unknown giữ reserve bảo thủ; zero usage đã
xác nhận phải được phân biệt với missing, cách charged gắn policy/version
(v1 vẫn theo ledger cũ). Request reserved nhưng chưa có bằng chứng hủy trước
send được coi là unknown, không tự hoàn quota. Không lưu prompt/ảnh/auth
header/key/hash key vào telemetry; response durable chỉ ở checkpoint được bảo vệ.

#### Phân công thực thi và Gate A

| Task nhận hợp đồng | Tiêu chí kiểm chính trước khi DONE |
| --- | --- |
| W5-05 | Guard/quota/retry policy có version, pacing/backoff đo thật, shared ledger; biên 429/120 giây/daily/quota thay đổi |
| W5-06/07 | Atomic I/O, response durable/reconciliation và history ID; unknown không replay tự động, resume không đếm trùng |
| W5-08.a | Identity/CLI/schema v2, telemetry và report metric cycle v2; CASH/N<2/zero denominator/thiếu lớp/partial có semantics đúng |
| W5-08.b–d | Posterior, count/interval, gate/config/prefix/caps theo contract ở trên; lỗi PIT vẫn fail loud |
| W5-09–12 | Coverage, cohort split/lịch/mẫu số và quota trước API; holdout/model-proof khóa đúng |
| W5-13–15 | Fault/paired/zero-leakage, timer/usage missing/zero/retry, 4 gate hồi quy và smoke v1 giới hạn |

**Gate A PASS ngày 08/10/2026:** baseline, bảng pilot, ledger/audit và các
quyết định contract trên đã chốt. Compileall/E2E, **536 unit/93 leakage PASS**;
82 file khoa học/code/nguồn/ZIP khớp baseline W5-03. W5-04 chỉ sửa tài liệu,
không gọi API hoặc tính lại kết quả đầu tư. Gate này không chứng nhận code v2 đã có,
không mở benchmark và không yêu cầu Bayesian phải thắng. Checklist Phase B
và nghiệm thu runtime v2 tiếp tục TODO cho đến khi triển khai/kiểm thực tế.

## 2. Quy tắc xuyên suốt

1. Giá chỉ từ **vnstock/VCI và vnstock/KBS**. LONG mua Open(t+1), bán
   Close(t+3); SHORT giữ tiền mặt; phí 0,25% và slippage 0,10% mỗi chiều.
   Nhãn/P&L dùng `compute_round_trip_net_return`.
2. Giá/tin ≤`as_of_date`; bỏ tin không có ngày. Prior phải có
   **`exit_date < as_of_date`**, lọc trước ranking/stats. HMM/scaler/calibration
   chỉ dùng phần train có trước query; validation 2020–2022 dùng model/scaler
   `historical_prefix` đã fit đến cutoff, không dùng artifact cuối 2022 để
   dự báo năm 2020/2021. Artifact cuối 2022 chỉ dành cho query OOS sau freeze.
3. Năm nhánh: Original K=0, Random/Recent/Similarity/Bayesian K=3,
   seed=42, same_symbol. Một bộ upstream/Full thành công dùng chung bằng
   deep-copy; không gọi lại vision theo nhánh. Đây là ma trận v1 và smoke W5;
   thêm nhánh `bayesian_v2` phải version hóa runner/schema/plan ở W6–W7.
4. Giữ `_distill_report`, `_cap_report`, BRPP ≤600 và prompt <6.500 ký tự;
   mọi API qua `_invoke_with_retry` và guard HTTP chung cho mọi đường gọi.
5. Upstream/Full đã gửi nhưng chưa biết kết quả: dừng để đối soát. Ngoại lệ
   replay điểm 16 ở W4 không cấp quyền tự động replay các lỗi tương lai.
6. Thiếu tin lịch sử giữ NEUTRAL kèm coverage/lý do; không lấy tin hiện tại
   bù quá khứ. Không coi pilot là bằng chứng Bayesian tăng lợi nhuận.

## 3. Checklist và thứ tự thực hiện

Task được thiết kế cho một lượt làm có đầu ra kiểm được; chuyển phase khi
gate tương ứng PASS. Ước lượng W5 khoảng **40–50 giờ làm việc chủ động**,
không gồm thời gian nghỉ quota. Điều chỉnh lịch theo gate thực tế.

| Phase | Task | Công việc | Phụ thuộc | Trạng thái |
| --- | --- | --- | --- | --- |
| A | W5-01 | Đối chiếu bàn giao và khóa bằng chứng pilot | W4 đã đóng | [x] |
| A | W5-02 | Tổng hợp chất lượng và chỉ số pilot offline | 01 | [x] |
| A | W5-03 | Báo cáo HTTP/token/thời gian và bất đồng quyết định | 01, 02 | [x] |
| A | W5-04 | Chốt vận hành, hợp đồng v2 và phân hoạch đánh giá | 02, 03 | [x] |
| B | W5-05 | Hoàn thiện chính sách dự phòng quota trước điểm | 04 | [ ] |
| B | W5-06 | Xử lý ghi checkpoint trên Windows/OneDrive | 04 | [ ] |
| B | W5-07 | Hoàn thiện phục hồi và đối soát upstream | 04, 06 | [ ] |
| B | W5-08 | CLI bốn mã và nền tảng evidence/prefix v2 | 05, 06, 07 | [ ] |
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
  đầu 2023/NEUTRAL/ngoại lệ replay; không sửa giao thức/kết quả pilot v1.

#### W5-03 — Báo cáo HTTP/token/thời gian và bất đồng quyết định

- **Làm:** tách graph invocation, HTTP attempt, HTTP thành công, format retry,
  transport unknown, preflight và replay. Tách input/output/actual/reserve
  từng model; thời gian HTTP, pacing, toàn điểm và retrieval trình bày riêng.
- **Bổ sung code:** chức năng audit checkpoint tại công cụ phân tích hiện có:
  đối chiếu action Original/v1, return engine, regime, population/K, score,
  tuổi prior, news coverage và lý do structured đã lưu. Không suy đoán chain
  of thought, không tạo nhãn mới. Trace phục vụ chẩn đoán, không dùng outcome
  query để chọn prior hoặc lọc mẫu.
- **Đầu ra:** chức năng tổng hợp ledger/audit có thể dùng lại; bảng gọn
  tại README, không dump prompt/ảnh/key hoặc tạo receipt cho từng request.
- **Đạt khi:** đối soát được 146 HTTP 200 + một unknown; text 194.218 và
  vision 102.034 charged; tái lập 1/20 bất đồng và chênh return của pilot.
  Không biến unknown thành zero usage hoặc HTTP thành công.

#### W5-04 — Chốt vận hành, hợp đồng v2 và phân hoạch đánh giá

- **Làm:** chốt retry/dừng/resume, quy tắc identity, schema báo cáo,
  metric chính/phụ và cách tổng hợp theo mã. Tách phân tích mô tả pilot
  khỏi đánh giá chính thức; định nghĩa common support và xử lý điểm dở.
  Chốt contract telemetry cho run mới: role/point/attempt/preflight,
  invocation counter và timer HTTP/pacing/retrieval/toàn điểm đo riêng;
  giữ `null`/coverage cho số đo không có, không migrate dữ liệu v1 bằng ước đoán.
  Giữ tài khoản 50 triệu đồng cho từng mã; nếu báo cáo portfolio chung
  phải có quy tắc phân bổ riêng, không cộng equity để giả thành cùng một tài khoản.
- **Bổ sung:** chốt fields/version cho posterior lịch sử, support, interval,
  requested/effective K, reason và hash config; phân hoạch train/2023/2024
  như mục chẩn đoán. Primary là chênh return ròng paired với Original;
  báo cáo MDD, balanced accuracy, LONG hit-rate/số giao dịch, tỷ lệ CASH,
  confidence chưa hiệu chuẩn và benchmark giữ tiền mặt. Rà annualization
  trên đúng khoảng thời gian kinh tế; sửa metric là phiên bản mới, không đổi P&L.
- **Đầu ra:** cập nhật hợp đồng hiện có khi cần; ghi quyết định tại README
  này. Khóa protocol cuối ở W7; sensitivity K/kiểm định thống kê ở W9.
- **Đạt khi:** lỗi không bị loại để làm đẹp accuracy; không đổi model/K/
  cost/scope giữa run; không gọi confidence chưa calibration là posterior.
  Chọn tham số bằng train/2023, không dùng 2024; gate kỹ thuật không yêu cầu
  Bayesian phải thắng hoặc p-value phải nhỏ.

**Gate A: PASS (08/10/2026).** Baseline kiểm được, bảng pilot/telemetry đối
soát được, hợp đồng v2/phân hoạch/metric/telemetry đã chốt tại mục 1. Runtime
v2 còn TODO; tiếp tục W5-05. Không yêu cầu pilot có lợi nhuận tốt hơn để PASS.

### Phase B — Đường chạy dài và nền tảng v2 (khoảng 2–3 ngày)

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

#### W5-08 — CLI bốn mã và nền tảng evidence/prefix v2

- **Làm:** tổng quát hóa CLI nghiên cứu hiện tại để đọc plan đã khóa,
  chọn mã, output/ledger, dry-run/preflight/run/verify/resume; chạy tuần tự
  có khóa quota chung. Dùng fixture plan trước khi có plan benchmark W8.
- **Đầu ra:** một đường CLI chính cho bốn mã; tên cờ/lệnh thật được ghi
  sau triển khai, không thêm runner riêng cho từng mã hoặc dùng runner Memory Bank.
- **Đạt khi:** run mới tách pilot W4; complete không gọi lại; sai identity
  bị chặn; dry-run/verify không đọc `.env` hoặc gọi mạng, schema/JSON native hợp lệ.

**Các bước nhỏ, đều TODO; không mở thêm mã task ngoài 16 task hiện tại:**

| Bước | Triển khai và đầu ra | Tiêu chí đạt |
| --- | --- | --- |
| W5-08.a | CLI/identity/schema tách v1/v2, telemetry và report metric chu kỳ theo W5-04; giữ verifier W4 bằng checkout đã ghim | Dry-run/verify cấm key/mạng kể cả đủ tin; không resume sai identity; kiểm CASH/N<2/zero denominator/thiếu lớp/partial và timer missing/zero |
| W5-08.b | Thống kê Beta–Binomial tại retriever: với s LONG thắng trong n chu kỳ, posterior Beta(α+s, β+n−s), mean=(α+s)/(α+β+n); trả counts và interval 95% | Fixture có kết quả số biết trước; n=0 báo thiếu bằng chứng; α,β>0 version hóa, mặc định ứng viên 1,1, chỉ chọn bằng train/2023 |
| W5-08.c | Kiểm chất lượng prior trước prefix: support, score, tuổi, coverage; metadata `requested_k`, `effective_k`, status/reason | Ngưỡng cố định theo config, không đọc outcome query; khi bằng chứng hợp lệ nhưng không đủ chất lượng thì K_eff=0/prefix rỗng, ghi lý do; leakage/schema hỏng vẫn ném lỗi |
| W5-08.d | Formatter/builder v2 phân biệt tín hiệu query, thống kê lịch sử và ví dụ; thêm support/uncertainty/evidence hash vào checkpoint | BRPP ≤600, prompt <6.500; K_eff=0 tạo prompt như Original nhưng Decision attempt riêng; không thêm retry LLM để ép đồng thuận prior |

Interval trên là bất định của mô hình tỷ lệ lịch sử với giả định Bernoulli,
chưa là xác suất dự báo query hay calibration của LLM. Chu kỳ/agent có thể
phụ thuộc; một cycle chỉ là một quan sát, không đếm bốn agent thành bốn
mẫu độc lập. W6–W7 cần kiểm out-of-time và W9 kiểm độ nhạy bằng block bootstrap.
Ngưỡng chất lượng không phải luật ra lệnh: không tự ép SHORT khi win-rate
<50%, và không tuyên bố gate sửa được ca n=62/score=1.

**Gate B:** CLI tái lập được, quota/atomic I/O/resume có kiểm thử; W4 còn
kiểm được bằng phiên bản đã ghim; 08.a–d PASS offline, có version/hash/trace.
Prior mặc định vẫn tắt trong luồng thông thường; v2 chưa được chứng minh có lợi hơn.

### Phase C — Phân hoạch dữ liệu và nguồn lực W6–W8 (khoảng 1 ngày)

#### W5-09 — Kiểm coverage và lịch đủ điều kiện OOS

- **Làm:** tính riêng cutoff 2023–2024 cho từng mã trên archive giá thô
  OOS/VNINDEX: warm-up 600 phiên, t+1/t+3, corporate actions, lịch và tin PIT.
  Thống kê ứng viên/hợp lệ/loại theo nguyên nhân, năm/quý và regime PIT.
- **Đầu ra:** bảng coverage bốn mã và tập ngày đủ điều kiện dùng để lập plan;
  tái dùng audit hiện có, không tải lại/ghi đè nguồn đã khóa chỉ để tạo báo cáo.
- **Đạt khi:** không dùng 1.510 chu kỳ hợp lệ của cả archive 2018–2024
  làm cỡ mẫu OOS; mọi ngày chọn đều được adapter xác minh và có exit hợp lệ.

#### W5-10 — Thiết kế lịch mẫu và tách pilot/smoke

- **Làm:** lập cohort riêng cho 2023 phát triển và 2024 xác nhận trên bốn mã;
  giữ phạm vi giá 2023–2024 nhưng không gọi cả hai năm là test chưa quan sát.
  W5-09/10 chỉ kiểm eligibility/lịch 2024, không dùng outcome/dự báo 2024 để
  hiệu chỉnh thuật toán. Chọn theo
  lịch/eligibility trước API, cách ≥3 phiên theo hợp đồng. Chốt mục tiêu
  số điểm từng mã/quý, nguyên tắc loại và coverage chứ không chọn theo lợi nhuận.
- **Đầu ra:** lịch dự kiến benchmark và **bốn điểm smoke riêng, một điểm/mã**.
  Tách 20 ngày FPT pilot đã quan sát và các điểm smoke khỏi mẫu đánh giá chính;
  nếu báo cáo chúng thì ghi là tập kiểm thử vận hành/phân tích thăm dò.
  Chọn smoke trong cohort 2023; kết quả 2023 sau phát triển luôn là thăm dò.
  Kiểm cả việc vô tình dùng giá entry/exit 2024 để lựa chọn ứng viên: giá
  tương lai chỉ cho evaluator/eligibility, không cho feature/retrieval/Decision.
- **Đạt khi:** không xem outcome/dự báo để chọn mẫu; không thay ngày lỗi
  bằng ngày dễ hơn. Mẫu rút gọn theo lịch là thay đổi phạm vi cần ghi rõ, không gọi toàn bộ OOS.

#### W5-11 — Tính ngân sách và lịch chạy khả thi

- **Làm:** với N điểm, dự kiến tối thiểu 5N Decision +2N vision =7N HTTP
  trong cấu hình pilot, cộng preflight/retry/format/replay/dự phòng. Tính
  token và giới hạn từng model theo telemetry; phân biệt chi phí kỳ vọng
  với reserve an toàn. Ledger local hiện dùng cửa sổ 61 giây và 24 giờ.
  Dự toán riêng candidate v2/validation: nếu W7 khóa ma trận sáu nhánh
  (năm v1 +bayesian_v2), mức tối thiểu là **6N text +2N vision =8N HTTP**;
  ablation/validation/preflight tính riêng, không lấy chi phí năm nhánh làm sáu.
- **Đầu ra:** bảng cỡ mẫu → quota/ngày → số ngày/thời gian chạy; có
  ngân sách còn lại sau tác vụ khác cùng tổ chức và lịch nghỉ/resume.
- **Đạt khi:** phương án chọn đáp ứng quota/thời hạn W6–W8. Nếu không đủ,
  báo BLOCKED kèm lựa chọn nâng quota/gia hạn/rút gọn mẫu trước khi khóa;
  không đổi key/model/K giữa run hoặc tự ghi PASS khả thi.

Để thấy quy mô: 194.218 token text/20 điểm pilot ≈9.711 token/điểm, gồm
chi phí kiểm model của lượt đó. Với 200.000 TPD, khoảng 20 điểm/ngày chỉ
là ước lượng trước dự phòng/tác vụ khác, không là cam kết năng lực.
W5-11 phải tính lại từ ledger và policy thật; chưa ấn định số điểm benchmark
hoặc coi hai tuần bổ sung tự động đủ quota.

#### W5-12 — Khóa input/plan và dry-run bốn mã

- **Làm:** sau khi phương án 10–11 được chốt, khóa ngày theo thứ tự,
  sources/checksums, snapshot tin, model/proof, bank, config, seed, scope,
  phân hoạch/cohort smoke v1, code/schema/dependency và policy quota.
  Mẫu holdout 2024 khóa ở W5, bản cấu hình ứng viên/ma trận benchmark khóa
  riêng tại W7 sau validation; đổi identity thì tạo run mới, không chỉnh plan đã chạy.
- **Đầu ra:** manifest/plan máy đọc phục vụ CLI trong output runtime mới,
  dự kiến `outputs/bayesian_benchmark/`; sơ đồ bố trí thật ghi lại tại README.
  Chỉ giữ JSON cần cho execute/verify, không thêm bản sao receipt.
- **Đạt khi:** dry-run toàn bộ ngày chọn PASS nguồn/PIT/economic/identity
  và BRPP/cap cấu hình, không API. Prompt đầy đủ chỉ kiểm được khi có báo
  cáo thực và phải qua guard trước HTTP; không ghi PASS prompt chưa sinh.
  Plan không được thay sau khi đã thấy Decision của cohort đó.

**Gate C:** đủ coverage bốn mã/hai năm theo phương án đã chọn; mẫu, nguồn,
model, ngân sách và lịch cohort được khóa trước run; chỉ W7 chốt protocol
ứng viên cuối. Quota không đủ thì giữ gate BLOCKED.

### Phase D — Kiểm chứng đường vận hành và bàn giao (khoảng 1 ngày)

#### W5-13 — Kiểm lỗi có chủ đích và paired/resume

- **Làm:** kiểm bốn mã bằng mock cấm mạng: quota sát trần, 429/cooldown,
  response chưa rõ, crash sau response/atomic write, lock active/stale,
  đổi nguồn/identity, partial branch và malformed Decision.
- **Đầu ra:** test cho rủi ro thật của 05–08; bổ sung leakage equality
  `exit_date == as_of_date`, news tương lai/không ngày và model sai freeze.
  Với v2, kiểm posterior biết trước, score/tuổi/support sát biên, K_eff=0,
  tập rỗng, label query không vào ranking, cycle không bị đếm trùng,
  cap/JSON/hash/resume và dry-run đủ tin vẫn cấm credential/mạng.
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
  Nghiệm thu code v2 bằng offline fixtures/trace, không lấy smoke v1 làm
  bằng chứng hiệu quả v2. Đo p95 lại khi thay retrieval/statistics tại 08.
  Chỉ đo lại retrieval p95 nếu thay đường này/môi trường hoặc có hồi quy cụ thể.
- **Đầu ra:** kết quả nghiệm thu gọn tại README, số test thực tế/commit/
  lệnh kiểm; không tái dùng số 521 để gắn PASS cho bản W5 chưa kiểm.
- **Đạt khi:** compileall, toàn unit, E2E, toàn leakage PASS; không gate
  nguồn lực chưa giải quyết. Sẵn sàng vận hành không đồng nghĩa hiệu quả đầu tư đã chứng minh.

#### W5-16 — Chốt W5, bàn giao lệnh và lịch W6

- **Làm:** cập nhật checklist, kế hoạch tổng và hướng dẫn lệnh thật cho
  prepare/dry-run/preflight/run/verify/resume từng mã; ghi lịch quota,
  nơi lưu dữ liệu, xử lý dừng/unknown và trách nhiệm đối soát.
  Bàn giao contract/implementation v2 cho W6; W7 chọn/khóa ứng viên,
  W8 mới chạy benchmark. Ghi rõ code đã có và ý tưởng còn chờ kiểm chứng.
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
| 07/10/2026 | W5-01 | DONE: verifier offline 20/20; 100 Decision; 31 code/12 source/runtime khớp W4; 15 point/75 Decision cũ, audit và reserve 5.535 nguyên vẹn; 97 file không đổi. Compileall/E2E, 521 unit/93 leakage PASS | W5-02; baseline và cách kiểm lại W4 ở mục 1 |
| 07/10/2026 | W5-02 | DONE: result/summary dựng lại khớp payload đã lưu; bảng năm nhánh cùng 20 điểm, nhãn/coverage/Decision có mẫu số đầy đủ; 97 file bất biến không đổi. Compileall/E2E, 521 unit/93 leakage PASS; không LLM hoặc thay đổi công thức/ma trận | W5-03; rà annualization ở W5-04 |
| 07/10/2026 | Điều chỉnh lộ trình theo pilot | PLAN_UPDATED: 1/20 action khác Original, ca FPT 20/02 giải thích chênh return; giữ bốn phase/16 task và 2 DONE, thêm code audit/posterior/gate/prefix vào task còn TODO. Lộ trình 10 tuần, tách 2023 development/2024 holdout; compileall/E2E, 521 unit/93 leakage PASS; không API hoặc sửa pilot | W5-03 rồi W5-04; W6–W7 cải thiện/validation, W8–W10 benchmark/thống kê/luận văn |
| 07/10/2026 | W5-03 | DONE: CLI/API audit readonly; 146 HTTP 200 +một unknown; charged text 194.218/vision 102.034, reserve 5.535 giữ nguyên; 100 attempt complete +một failed; 1/20 bất đồng, chênh return −2,241809 điểm phần trăm. Timer v1 thiếu ghi null, không đoán pacing/role; verifier pilot 20/20, audit hook 0 credential/network, 82 file bất biến. 15 test mới; compileall/E2E, 536 unit/93 leakage PASS | W5-04: contract vận hành/v2, metric/phân hoạch và telemetry run mới |
| 08/10/2026 | W5-04 | DONE, Gate A PASS: chốt research_evaluation_contract_v2, retry/resume/identity, split train/2023/2024, primary theo mã và trung bình bốn mã, cycle-risk metric không annualize, evidence/gate/prefix và telemetry v2. Gắn yêu cầu với 05–08/13–15; code v2 vẫn TODO. Compileall/E2E, 536 unit/93 leakage PASS; 82 file khớp baseline, không API hoặc thêm receipt | W5-05: triển khai policy quota/pacing theo hợp đồng |
