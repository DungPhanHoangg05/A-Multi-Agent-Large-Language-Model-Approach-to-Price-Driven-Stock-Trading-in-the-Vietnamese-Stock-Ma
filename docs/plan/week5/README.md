# Tuần 5 — Hoàn thiện vận hành và nền tảng Bayesian v2

**Trạng thái: W5 HOÀN THÀNH — 15/15 task trong phạm vi DONE, Phase A/B/C/D PASS (10/10/2026). Đã chốt vận hành và bàn giao W6; W5-11 đã bỏ theo yêu cầu.**
Ngày lập: **07/10/2026**; cập nhật **10/10/2026**. Đã kiểm/tổng hợp offline,
triển khai CLI cohort/evidence/gate/prefix v2, audit OOS, khóa input/lịch và dry-run bốn mã.
[Kế hoạch tổng](../plan.md) · [Kết quả W4](../week4/README.md) ·
[Hợp đồng API/checkpoint hiện hành](../week4/week_close_and_handoff.md)

## 1. Mục tiêu và đầu vào

Pilot FPT và quota đã được nghiệm thu khi chốt W4. W5 dùng kết quả đó để
hoàn thiện đường chạy chính thức, xử lý các điểm yếu vận hành đã quan sát,
và triển khai nền tảng Bayesian v2 trên **FPT, VNM, VCB, MWG**. Lộ trình
được mở rộng thành **10 tuần**: W6 cải thiện thuật toán, W7 kiểm chứng và
khóa phiên bản, W8 benchmark, W9 thống kê, W10 luận văn. Bốn phase và
15 task trong phạm vi W5; bỏ W5-11, giữ nguyên mã task còn lại để không
làm sai tham chiếu. W5-01–10 và W5-12–16 DONE;
nền tảng v2 đã có kiểm fixture;
hiệu quả v2 còn cần validation và benchmark.

| Đầu vào đã hoàn thành ở W4 | Ý nghĩa đối với W5 |
| --- | --- |
| 20 điểm FPT, 100/100 Decision structured, verifier offline PASS | Giữ pilot làm bằng chứng vận hành; mẫu chỉ phủ 05/01–03/04/2023 |
| Compileall/E2E, 521 unit và 93 leakage PASS | Mốc hồi quy, không tự coi bản code W5 đã được kiểm thử |
| Giá thô OOS VCI/KBS bốn mã; model proof train-only hồi cứu | Tính lịch OOS đủ điều kiện trên nguồn đã khóa; giữ giới hạn của proof |
| Memory Bank 852 episode, quyết định 2020–2022 | Giữ bank/model/train nguyên vẹn; không bổ sung nhãn OOS vào prior |
| Retrieval p95 bốn mode 10,837–13,235 ms, dưới 30 ms | Giữ bằng chứng đã đo; chỉ đo lại khi thay đường retrieval hoặc môi trường |
| 146 HTTP 200, một transport_error chưa rõ kết quả, 0 HTTP 429 | Đối soát request/usage/reserve, giữ ngoại lệ upstream điểm 16 |
| Text 194.218 token; vision 102.034 gồm reserve unknown | Giữ telemetry và reserve để guard từng request khi chạy thật |
| BRPP tối đa 369; prompt tối đa 4.483 ký tự | Cap hiện tại đủ cho pilot; tiếp tục kiểm cứng ở mọi điểm mới |

Giới hạn chủ tài khoản đã cung cấp cho **cả `openai/gpt-oss-20b` và
`qwen/qwen3.8-27b`**: **30 RPM / 1.000 RPD / 8.000 TPM / 200.000 TPD**.
ITPM/OTPM riêng chưa được cung cấp. Các con số này là cấu hình guard khi
chạy thật; không còn bước dự toán ngân sách hoặc số ngày chạy trong plan.
**Mọi thao tác dùng API key do người dùng tự chạy.** Agent chuẩn bị code,
kiểm offline và cung cấp lệnh theo từng bước; đọc/kiểm kết quả offline sau run.

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
  W5 khóa phân hoạch dữ liệu và input/guard; W7 khóa cấu hình ứng viên
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
  phiên bản, giả thuyết và ma trận khóa ở W7 trước lượt chạy holdout.
- Nếu phát hiện cohort đã được xem outcome để tuning, ghi nhận exposure,
  hạ claim thành exploratory và chốt lại thiết kế trước API; không tự gọi
  một tập đã dùng lựa chọn là holdout. Mọi giao dịch holdout phải có entry/exit
  thuộc 2024; loại cutoff cuối năm thiếu exit theo lịch, không theo return.

Năm nhánh v1 tiếp tục dùng cho smoke W5. V2 là `bayesian_v2`, chỉ mở ma trận
v1+v2 khi runner/schema mới được kiểm. Original giữ cùng reports/template;
một upstream/Full bundle thành công cho mỗi point, deep-copy cho tất cả nhánh.
Cỡ mẫu/ngày kiểm định thuộc W5-10/12, ma trận cuối thuộc W7. Cùng lịch từng
mã giữa các nhánh, cách cutoff ≥3 phiên. Bỏ dự toán không thay các guard API.

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
| W5-09, 10, 12 | Coverage, cohort split/lịch/mẫu số và input/plan dry-run; holdout/model-proof khóa đúng |
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
| B | W5-05 | Hoàn thiện chính sách dự phòng quota trước điểm | 04 | [x] |
| B | W5-06 | Xử lý ghi checkpoint trên Windows/OneDrive | 04 | [x] |
| B | W5-07 | Hoàn thiện phục hồi và đối soát upstream | 04, 06 | [x] |
| B | W5-08 | CLI bốn mã và nền tảng evidence/prefix v2 | 05, 06, 07 | [x] |
| C | W5-09 | Kiểm coverage và lịch đủ điều kiện OOS | 04 | [x] |
| C | W5-10 | Thiết kế lịch mẫu và tách pilot/smoke | 09 | [x] |
| C | W5-12 | Khóa input/plan và dry-run bốn mã (offline) | 08, 10 | [x] |
| D | W5-13 | Kiểm lỗi có chủ đích và paired/resume | 08, 12 | [x] |
| D | W5-14 | Smoke vận hành thật giới hạn bốn mã | Gate A/B/C, 13 | [x] |
| D | W5-15 | Nghiệm thu hồi quy và điều kiện mở W6 | 13, 14 | [x] |
| D | W5-16 | Chốt W5, bàn giao vận hành và thứ tự triển khai W6 | 15 | [x] |

W5-11 đã bỏ khỏi phạm vi ngày 09/10/2026 theo yêu cầu người dùng, không
tính vào mẫu số tiến độ hoặc điều kiện chuyển phase. “Lịch mẫu/cohort” là
ngày dữ liệu cần kiểm định, vẫn giữ để bảo đảm thiết kế nghiên cứu; “lịch
chạy” là dự toán thời gian/ngày dùng API, đã bỏ.

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
Bayesian v2 đã triển khai/kiểm fixture tại W5-08; W5-05–08 hoàn thành.
Không yêu cầu pilot có lợi nhuận tốt hơn để PASS.

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

**Triển khai 08/10/2026:** CLI `scripts/run_bayesian_ablation.py` nhận
`--quota-policy`, mặc định `request_admission_v2`. Trước điểm, policy này
kiểm còn ≥1 request và ≥8.000 token/ngày cho **từng model**, thay cho
6 request/48.000 text và 2 request/16.000 vision của `whole_point_v1`.
Đây là kiểm điều kiện bắt đầu, chưa trừ quota và **không bảo đảm đủ toàn
điểm**. Mỗi HTTP vẫn reserve input + output cap trước gửi, giữ unknown,
kiểm RPM/TPM/RPD/TPD; hết quota giữa điểm thì dừng giữ checkpoint. Không
tự chạy lại upstream khi kết quả chưa rõ; đối soát/resume ở W5-07.

- Cả hai lựa chọn đi qua CLI, cùng ledger `outputs/oos_pilot/api_usage.json`
  và khóa OS `outputs/oos_pilot/runtime/`. Ledger chỉ được nạp **sau khi
  có khóa**, tránh ghi đè usage mới bằng bản đọc trước khóa. Đổi key hoặc
  output-dir không tạo quota mới. CLI hiện vẫn dùng plan pilot đã khóa;
  CLI bốn mã/cohort mới thuộc W5-08.a.
- Policy nằm trong `identity.versions.quota_policy`, do đó đổi policy
  trên checkpoint hiện có bị từ chối trước LLM. Schema hiện hữu thêm field
  tùy chọn có enum, vẫn đọc identity cũ không có field; không sửa manifest
  hoặc bằng chứng W4. Run với code mới cần thư mục mới; không dùng policy
  flag để vượt kiểm code hash của pilot cũ.
- Cache `o200k_base` được kiểm checksum trước run/preflight, trước đọc key
  và HTTP. Thiếu/hỏng thì dừng và hướng dẫn chạy
  `py -3.13 scripts/prepare_groq_tokenizer.py`. Dry-run in trạng thái cache;
  verify-only không cần key/cache và không gọi mạng.
- Pacing nghỉ mỗi lượt ≤30 giây, tính lại quota sau mỗi lượt; tổng nghỉ
  cho một lần reserve không quá 120 giây. Thời gian nghỉ thực đo bằng
  monotonic, lưu `pacing_seconds` trên ledger và request; lượt dừng vẫn giữ
  thời gian đã nghỉ. `last_stop` chứa reason/model/policy, remaining/budget
  khi thiếu quota, `resume_not_before_utc` khi tính được. Quota ngày dùng
  cửa sổ trượt 24 giờ, token/request phút dùng 61 giây.
- HTTP429 vẫn **dừng có kiểm soát**, lưu reserve và cooldown trước khi
  thoát; v2 cộng 1 giây vào retry-after, dùng giá trị lớn hơn giữa header
  và message. Không tự gửi lại HTTP ở W5-05. Retry có ngân sách chung
  ba attempt/120 giây xuyên format repair và response durable là W5-07/08;
  không coi timer reserve hiện tại là toàn bộ telemetry invocation v2.
- Header provider báo giới hạn thấp hơn cấu hình hoặc dữ liệu quota sai
  thì dừng; giới hạn cao hơn không tự tăng ngân sách. RPD remaining=0
  dùng reset header nếu hợp lệ, thiếu thì giữ mốc bảo thủ 24 giờ. Quota
  durable khác `MODEL_LIMITS` cũng bị từ chối, cần rà cấu hình cho run mới.
  Usage thực vượt reserve được ghi lại và response thành công vẫn về
  caller để checkpoint; chặn HTTP kế tiếp kể cả sau resume để rà estimator.

Quy ước header được đối chiếu với [Groq Rate Limits](https://console.groq.com/docs/rate-limits):
`*-requests` là RPD, `*-tokens` là TPM, quota theo tổ chức. Bộ giới hạn
30 RPM/1.000 RPD/8.000 TPM/200.000 TPD giữ đúng đầu vào đã chốt; không tự
nới theo key mới. Nếu tài khoản có ITPM/OTPM riêng, phải bổ sung policy
trước live run. W5-05 chỉ kiểm thử offline, không xác nhận quota tài khoản
hiện tại hoặc chạy lại pilot.

Kiểm tra cấu hình mới không gọi LLM:

```powershell
py -3.13 -X utf8 scripts/run_bayesian_ablation.py --dry-run --quota-policy request_admission_v2
```

**Nghiệm thu DONE:** dry-run thực tế PASS 20 cutoff FPT và cache tokenizer;
compileall, E2E, **546 unit test/93 test leakage PASS**. Có 10 test mới
cho biên quota/cooldown, thời gian nghỉ, quota đổi, cache/khóa/CLI,
usage vượt reserve và identity policy khi resume. 49 artifact
dữ liệu/bank/model/checkpoint/ledger/audit/ZIP trong baseline giữ nguyên
SHA-256. Không gọi API LLM, không tạo thêm receipt. Tiếp theo W5-06.

#### W5-06 — Xử lý ghi checkpoint trên Windows/OneDrive

- **Làm:** tái hiện sharing violation/WinError 5; bổ sung retry ghi atomic
  có giới hạn cho đúng lỗi có thể phục hồi. Tránh reader giữ handle cản
  `os.replace`; hướng dẫn thư mục runtime local ngoài vùng đồng bộ nếu cần.
- **Đầu ra:** đường ghi/đọc ổn định và lỗi I/O có hướng xử lý; không nuốt
  lỗi quyền/đĩa đầy, không ghi đè checkpoint complete hoặc xóa lock đang sống.
- **Đạt khi:** fault test chứng minh file cũ hoặc file mới nguyên vẹn,
  không JSON nửa chừng; retry hết thì dừng giữ dữ liệu durable.

**Triển khai 08/10/2026:** `atomic_write_json` serialize và ghi/fsync đúng
một lần, đóng handle file tạm rồi mới thay thế checkpoint. Chỉ bước
`os.replace` và dọn file tạm riêng của lần ghi được retry khi `winerror`
là 5/32/33; tối đa 5 attempt, nghỉ 0,05 → 0,10 → 0,20 → 0,40 giây
(0,75 giây cho mỗi thao tác). Không retry serialize, ghi nội dung, fsync,
đĩa đầy hoặc lỗi quyền không có mã Windows được cho phép. WinError 5
cũng có thể là lỗi quyền thật: hết số lần thử vẫn trả nguyên ngoại lệ,
không đổi ACL, không xóa file đích để ép ghi. Mã lỗi đối chiếu
[Microsoft Win32](https://learn.microsoft.com/en-us/windows/win32/debug/system-error-codes--0-499-).

- File đích giữ nguyên byte cho tới khi replace thành công; retry không
  chạy lại agent. Lỗi dọn file tạm không che lỗi gốc; exception note cho
  biết file còn sót. Không tự nâng file tạm thành checkpoint. Nếu tiến
  trình chết hoặc thư mục đích vẫn bị khóa, giữ trạng thái durable cũ và
  đối soát theo W5-07; không hứa khôi phục response chưa được lưu.
- `read_json` dùng `Path.read_text`, đóng handle trước khi parse/trả về.
  Test Windows thật mở reader không chia sẻ DELETE, tái hiện lỗi replace,
  đóng reader trong backoff và xác minh JSON mới nguyên vẹn. Không giữ
  reader mở xuyên suốt run; khóa OS của runner vẫn giữ đúng vòng đời cũ.
- Thông báo `PERSISTENCE` hướng dẫn kiểm quyền, dung lượng và handle;
  không xóa lock còn sống. Checkpoint complete vẫn bất biến khi resume.

**Vận hành khi OneDrive liên tục khóa file:** dừng runner trước, kiểm
checkpoint/owner; ưu tiên checkout toàn bộ workspace vào ổ local ngoài
vùng đồng bộ (ví dụ `C:\KLTN\project`). Chuyển dữ liệu và runtime bằng
bản sao đã đối chiếu checksum, bao gồm **ledger quota, preflight, checkpoint
và audit**, giữ đúng code/config của run đang phục hồi. Không chạy đồng
thời hai bản workspace hoặc tạo ledger trống để reset quota. Riêng
`--output-dir` local chỉ chuyển checkpoint, ledger chung hiện vẫn ở
`outputs/oos_pilot/` trong workspace; chưa làm toàn bộ runtime thoát OneDrive.
Không sửa byte pilot W4 để hợp với code mới; run mới dùng thư mục mới.

**Nghiệm thu DONE:** compileall/E2E, **555 unit test/93 test leakage PASS**.
Thêm 9 test cho lỗi tạm thời/hết retry, đĩa đầy, ghi dở/fsync/serialize,
cleanup không che lỗi gốc, handle Windows thật và retry checkpoint không
lặp agent/không sửa complete khi resume. 49 artifact dữ liệu/bằng chứng
giữ nguyên SHA-256. Fault test chạy trong thư mục tạm, không gọi API hoặc
can thiệp tiến trình OneDrive thật. Khôi phục response từng stage và đối
soát AMBIGUOUS tiếp tục thuộc W5-07.

#### W5-07 — Hoàn thiện phục hồi và đối soát upstream

- **Làm:** phân biệt chưa gửi, đã nhận response durable và kết quả chưa rõ.
  Rà checkpoint từng bước Pattern/Trend/Full; bổ sung lưu response/stage
  tối thiểu nếu cần để dùng lại kết quả đã nhận thay vì gọi lại upstream.
- **Đầu ra:** quy trình/CLI đối soát có kiểm owner, identity, hash và audit;
  response cần phục hồi nằm trong checkpoint được bảo vệ, không trong telemetry.
- **Đạt khi:** dùng lại response đã lưu không tạo HTTP mới; tình trạng
  AMBIGUOUS dừng, chỉ replay sau xác nhận cụ thể. Không cam kết exactly-once API từ xa.

**Triển khai 08/10/2026:** run mới qua CLI bật
`identity.versions.stage_recovery=agent_stage_journal_v1`. Mỗi point có
một journal `responses/<point_id>.json` trong checkpoint, dùng envelope/hash,
run signature, point ID và source hash; không ghi response vào quota ledger.
Journal lưu output **node agent** Indicator/Pattern/Trend/Full, gồm báo cáo,
message có kiểu và dữ liệu Full cần khôi phục, không pickle đối tượng runtime.
Đây là consumer thực phục vụ resume, không phải receipt bổ sung theo task.

- Trước node: ghi intent với UUID và input hash. Node chưa có intent là
  chưa bắt đầu; intent chưa có output durable là **unknown** (kể cả có thể
  chưa gửi HTTP). Chỉ chuyển complete sau khi output hợp lệ được ghi atomic.
- Resume dựng lại graph từ source PIT đã kiểm, đối chiếu input hash rồi
  trả output node complete từ journal. Node đó không gọi agent/HTTP lại;
  chỉ node chưa bắt đầu mới thực thi. Sau Full, vẫn deep-copy shared bundle
  sang năm nhánh theo giao thức cũ. Checkpoint complete và history không bị xóa.
- Kiểm toàn journal và quan hệ stage/báo cáo với checkpoint trước agent;
  thiếu file ở point đã bắt đầu, sai hash/source/identity, node sai thứ tự
  hoặc khác input đều dừng. Run legacy không có version này giữ cách dừng
  AMBIGUOUS cũ, không tự tạo output hoặc migrate bằng chứng W4.
- Đối soát dùng khóa OS của run và kiểm identity/schema/hash/source hiện
  hành; output console chỉ có node/attempt/status, không in báo cáo/message.
  Xác nhận replay phải chọn UUID unknown cuối cùng và lý do. Audit ghi ngay
  vào attempt đó; lúc chạy tiếp tạo UUID mới, giữ attempt unknown và chi phí
  quota cũ. Không xác nhận lại complete, UUID sai, hoặc point đã complete.

Ví dụ cho **run mới đã bật journal**, giữ nguyên code/config/quota policy:

```powershell
py -3.13 -X utf8 scripts/run_bayesian_ablation.py --reconcile --output-dir outputs/research_new_run
# Chỉ sau khi người vận hành đã đối soát và quyết định chấp nhận gọi lại node:
py -3.13 -X utf8 scripts/run_bayesian_ablation.py --reconcile --output-dir outputs/research_new_run --authorize-replay UUID_ATTEMPT --replay-reason "Da doi soat va chap nhan replay node nay"
py -3.13 -X utf8 scripts/run_bayesian_ablation.py --run --resume --output-dir outputs/research_new_run
```

`--reconcile` không đọc key, không cần cache tokenizer và dùng transport cấm
mạng. Nó không tự chạy agent; xác nhận replay và chạy tiếp là hai bước riêng.
Không dùng lý do chứa API key hoặc thông tin tài khoản.

**Giới hạn:** đây là journal tại biên output node, chưa phải WAL từng HTTP
response. Nếu tiến trình chết sau HTTP nhưng trước output node durable,
hoặc giữa các lời gọi nội bộ của Full, trạng thái vẫn unknown; không tự
parse lại raw HTTP hay cam kết exactly-once. Replay được xác nhận có thể
gọi lại các request nội bộ của node, nên phải tính thêm quota. Ngân sách
retry chung với format repair và telemetry từng HTTP còn thuộc W5-08.a;
W5-07 không bật retry transport mới hoặc nới giới hạn LLM.

**Nghiệm thu DONE:** compileall/E2E, **562 unit test/93 test leakage PASS**.
Bảy test mới bao phủ crash sau từng output node, unknown Pattern/Full,
audit replay, sai hash/input/identity, thiếu journal, khóa OS đang sống,
message round-trip và CLI cấm key/mạng. 49 artifact dữ liệu/bằng chứng
giữ nguyên SHA-256. Các fault test dùng fixture offline; không replay pilot
W4 hoặc xác nhận attempt thật thay người vận hành. Tiếp theo W5-08.

#### W5-08 — CLI bốn mã và nền tảng evidence/prefix v2

- **Làm:** tổng quát hóa CLI nghiên cứu hiện tại để đọc plan đã khóa,
  chọn mã, output/ledger, dry-run/preflight/run/verify/resume; chạy tuần tự
  có khóa quota chung. Dùng fixture plan trước khi có plan benchmark W8.
- **Đầu ra:** một đường CLI chính cho bốn mã; tên cờ/lệnh thật được ghi
  sau triển khai, không thêm runner riêng cho từng mã hoặc dùng runner Memory Bank.
- **Đạt khi:** run mới tách pilot W4; complete không gọi lại; sai identity
  bị chặn; dry-run/verify không đọc `.env` hoặc gọi mạng, schema/JSON native hợp lệ.

**W5-08.a–d: DONE (09/10/2026); các hạng mục dưới đây nằm trong W5-08:**

| Bước | Triển khai và đầu ra | Tiêu chí đạt |
| --- | --- | --- |
| W5-08.a | CLI/identity/schema tách v1/v2, telemetry và report metric chu kỳ theo W5-04; ngân sách retry chung HTTP/format repair; giữ verifier W4 bằng checkout đã ghim | Dry-run/verify cấm key/mạng kể cả đủ tin; không resume sai identity; tối đa 3 attempt/120 giây chờ cho invocation gốc; kiểm CASH/N<2/zero denominator/thiếu lớp/partial và timer missing/zero |
| W5-08.b | Thống kê Beta–Binomial tại retriever: với s LONG thắng trong n chu kỳ, posterior Beta(α+s, β+n−s), mean=(α+s)/(α+β+n); trả counts và interval 95% | Fixture có kết quả số biết trước; n=0 báo thiếu bằng chứng; α,β>0 version hóa, mặc định ứng viên 1,1, chỉ chọn bằng train/2023 |
| W5-08.c | Kiểm chất lượng prior trước prefix: support, score, tuổi, coverage; metadata `requested_k`, `effective_k`, status/reason | Ngưỡng cố định theo config, không đọc outcome query; khi bằng chứng hợp lệ nhưng không đủ chất lượng thì K_eff=0/prefix rỗng, ghi lý do; leakage/schema hỏng vẫn ném lỗi |
| W5-08.d | Formatter/builder v2 phân biệt tín hiệu query, thống kê lịch sử và ví dụ; thêm support/uncertainty/evidence hash vào checkpoint | BRPP ≤600, prompt <6.500; K_eff=0 tạo prompt như Original nhưng Decision attempt riêng; không thêm retry LLM để ép đồng thuận prior |

Interval trên là bất định của mô hình tỷ lệ lịch sử với giả định Bernoulli,
chưa là xác suất dự báo query hay calibration của LLM. Chu kỳ/agent có thể
phụ thuộc; một cycle chỉ là một quan sát, không đếm bốn agent thành bốn
mẫu độc lập. W6–W7 cần kiểm out-of-time và W9 kiểm độ nhạy bằng block bootstrap.
Ngưỡng chất lượng không phải luật ra lệnh: không tự ép SHORT khi win-rate
<50%, và không tuyên bố gate sửa được ca n=62/score=1.

**Triển khai 08–09/10/2026 — nghiệm thu DONE:**

- **08.a:** CLI hiện hữu nhận `--plan`, `--symbol` (lặp lại được) và
  `--ledger`; bỏ `--symbol` để chạy tuần tự FPT/VNM/VCB/MWG. Plan envelope
  `research_cohort_plan_v2` khóa `cohort_id`, `split` (`fixture`,
  `development_2023`, `holdout_2024`), `matrix` (`smoke_v1` hoặc
  `research_v2`), `symbol_cutoffs`, `evidence_config` đầy đủ và `inputs`
  theo hợp đồng nguồn/model/limits của pilot. Không tự chọn ngày hoặc
  ngưỡng trong CLI. Fixture không được gọi API thật; lịch benchmark sẽ
  được khóa ở W5-09–12/W7, chưa tạo một plan benchmark giả cho W5-08.
- Cùng `PriorBacktestRunner.run_cohort()` kiểm schema/hash/lịch toàn bộ
  plan trước chạy. Root identity ghim code v2, plan, bốn identity v1 và
  đường ledger. Năm nhánh v1 nằm tại `v1/<symbol>/`; nhánh thứ sáu
  `bayesian_v2` dùng lại Full đã seal tại `v2/<point_id>.json`. Không gọi
  lại upstream để thêm v2. Khởi tạo slot toàn plan; mất checkpoint,
  sai source/config/code hoặc attempt unknown đều không tự chạy lại.
  `--reconcile` trả UUID/metadata; replay cụ thể cần `--authorize-replay`
  và `--replay-reason`, có lịch sử audit. Không dùng output-dir pilot W4.
- Policy `invocation_budget_v2` dùng chung **tối đa 3 HTTP và 120 giây
  nghỉ** cho node/Decision, kể cả format repair. SDK vẫn `max_retries=0`;
  HTTP 429 đã từ chối mới có retry hữu hạn, timeout/5xx dừng. Ledger giữ
  UUID invocation, UUID HTTP, checkpoint attempt, point/branch/role,
  provider request ID, usage và pacing; không chứa request/prompt/key.
  HTTP latency dùng monotonic; missing và zero tách biệt, p95 nội suy
  tuyến tính. Timer invocation và tổng nghỉ được ghi cả khi dừng trước
  admission HTTP; không cộng timer Decision lồng thêm vào HTTP/pacing.
- `research_report_v2` tái dùng tài khoản/phí/P&L engine, tính rủi ro
  `cycle_risk_metrics_v2` từ `period_returns` thật, không annualize.
  Có CASH reference, balanced accuracy, participation, hit-rate và lý do
  null. Primary là trung bình đều Δreturn v2−Original theo điểm phần trăm
  của **đủ bốn tài khoản**, không là portfolio; thiếu mã/điểm trả
  `INCOMPLETE`, smoke v1 trả `NOT_APPLICABLE`. Chỉ lấy điểm đủ mọi nhánh.
- **08.b–c:** API `BayesianPriorRetriever.retrieve_evidence()` trả toàn
  population cùng mã/regime/PIT, counts, Beta posterior/CrI95% và gate
  version hóa. α=β=1; support≥20, score≥0,75, tuổi≤730 ngày, K≤3;
  không dùng outcome query. n=0 trả null; support/quality thiếu trả
  `INSUFFICIENT_EVIDENCE`, K_eff=0; K_eff=1/2 vẫn hợp lệ nếu đủ support.
  Ranking giữ score↓, exit↓, ID↑. Schema/counts/hash/PIT sai ném lỗi.
- **08.d:** prefix `compact_brpp_v2` giữ counts và bất định của lịch sử,
  không gọi posterior là xác suất query. Builder vẫn distill/cap, BRPP
  ≤600 ký tự và prompt <6.500. K_eff=0 tạo đúng prompt Original nhưng
  gọi Decision riêng; không thêm lần gọi để ép đồng thuận. Evidence,
  config/bank/shared hash, prompt và response nằm trong checkpoint v2.
  Verify đối chiếu cả action trong response gốc; tính lại envelope hash
  không làm một response mâu thuẫn trở thành checkpoint hợp lệ.
- Import sentiment không còn tự nạp `.env`; entrypoint trực tuyến chịu
  trách nhiệm nạp credential. Fixture đủ ba bài tin kiểm đường dry-run
  không đọc key hoặc kết nối mạng.

**Lệnh vận hành smoke theo plan thật đã khóa ở W5-12:** xem
[hướng dẫn từng bước W5-14](#cách-tự-chạy-w5-14-bằng-terminal). Các lệnh
preflight/run/resume có gọi API do người dùng tự thực hiện sau W5-13.
Plan benchmark development/holdout chỉ phát hành sau khi khóa protocol W7.

Thêm `--symbol FPT` để chạy riêng một mã, vẫn giữ nguyên plan bốn mã và
primary chưa hoàn tất. Ledger mặc định vẫn là
`outputs/oos_pilot/api_usage.json`; đổi key/output-dir không xóa quota.
Nếu chuyển ledger sang ổ local, sao chép nguyên lịch sử và khóa đường đó
ngay từ run mới; đổi đường ledger khi resume bị chặn bởi identity.
Không chạy đồng thời checkout W4 cũ và runtime mới trên cùng tài khoản.
Response đã durable được tái sử dụng; mất điện trước khi lưu response vẫn
là unknown cần đối soát, không cam kết exactly-once phía provider.

**Bằng chứng nghiệm thu:** compileall/E2E PASS; **578 unit test PASS**
(16 test mới), **93 test leakage PASS**. Bao phủ bốn mã, common support,
gate-off giữ prompt Original, posterior/gate/PIT/caps, UUID replay,
mất checkpoint và sửa response dù tính lại hash, quota/retry/format repair,
timer zero/missing và dry-run đủ tin cấm credential/mạng. Pilot W4 kiểm
bằng checkout `27b5907`: **complete 20/20**, có audit hook chặn `.env`,
DNS/socket; worktree tạm đã dọn sau kiểm. **49 artifact đóng băng giữ
nguyên SHA-256**. Không gọi Groq, không chạy benchmark hoặc dùng holdout
để chọn ngưỡng. Tiếp theo **W5-09: coverage và lịch đủ điều kiện OOS**.

**Gate B: PASS (09/10/2026).** CLI tái lập được, quota/atomic I/O/resume có kiểm thử; W4 còn
kiểm được bằng phiên bản đã ghim; 08.a–d PASS offline, có version/hash/trace.
Prior mặc định vẫn tắt trong luồng thông thường; v2 chưa được chứng minh có lợi hơn.

### Phase C — Phân hoạch dữ liệu và khóa input W6–W8 (khoảng 1 ngày)

#### W5-09 — Kiểm coverage và lịch đủ điều kiện OOS

- **Làm:** tính riêng cutoff 2023–2024 cho từng mã trên archive giá thô
  OOS/VNINDEX: warm-up 600 phiên, t+1/t+3, corporate actions, lịch và tin PIT.
  Thống kê ứng viên/hợp lệ/loại theo nguyên nhân, năm/quý và regime PIT.
- **Đầu ra:** bảng coverage bốn mã và tập ngày đủ điều kiện dùng để lập plan;
  tái dùng audit hiện có, không tải lại/ghi đè nguồn đã khóa chỉ để tạo báo cáo.
- **Đạt khi:** không dùng 1.510 chu kỳ hợp lệ của cả archive 2018–2024
  làm cỡ mẫu OOS; mọi ngày chọn đều được adapter xác minh và có exit hợp lệ.

**DONE (09/10/2026); audit dữ liệu và các gate hồi quy PASS.**

Triển khai `core/oos_coverage.py` và mở CLI audit hiện có. Lệnh tái lập offline:

```powershell
py -3.13 -X utf8 scripts/verify_execution_price_gate.py --oos-coverage
```

Đọc nguyên nguồn `data/execution_prices_oos/`, VNINDEX, model cố định đã
khóa trước 2023, bank QA và snapshot tin trong `outputs/oos_pilot/inputs/`.
Warm-up **600 nến cổ phiếu**, **200 nến VNINDEX** theo adapter; kiểm đúng
Open(t+1)/Close(t+3), volume cả ba phiên và quyền trong `(entry, exit]`.
Cutoff/entry/exit phải cùng năm như validator cohort. Mọi cutoff đủ warm-up,
kể cả ngày bị loại vì thực thi, được `adapter.prepare` kiểm PIT/regime/tin.
Lỗi nguồn/model/leakage dừng audit; không đổi thành ngày loại để bỏ qua.

**1.996 ứng viên hằng ngày → 1.944 hợp lệ, 52 loại; 1.996/1.996 có proof PIT.**
Nguyên nhân ưu tiên không đếm trùng: 28 ngày quyền, 24 ngày vượt ranh giới
năm (ba cutoff cuối mỗi năm/mã). Không thiếu warm-up/lịch hoặc volume trong
nguồn này. Các reason phụ được giữ riêng trong từng record.

| Mã | 2023 hợp lệ /249 | 2024 hợp lệ /250 | Tổng hợp lệ /499 | Loại quyền | Loại vượt năm | Hợp lệ lưới cũ /165 |
| --- | --- | --- | --- | --- | --- | --- |
| FPT | 240 | 241 | 481 | 12 | 6 | 162 |
| VNM | 242 | 241 | 483 | 10 | 6 | 163 |
| VCB | 244 | 247 | 491 | 2 | 6 | 163 |
| MWG | 244 | 245 | 489 | 4 | 6 | 162 |

Các ô dưới đây là **số hợp lệ**; cột ứng viên là mẫu số cho từng mã/quý:

| Quý | Ứng viên/mã | FPT | VNM | VCB | MWG |
| --- | --- | --- | --- | --- | --- |
| 2023Q1 | 59 | 59 | 59 | 59 | 59 |
| 2023Q2 | 62 | 59 | 62 | 62 | 62 |
| 2023Q3 | 63 | 60 | 61 | 61 | 61 |
| 2023Q4 | 65 | 62 | 60 | 62 | 62 |
| 2024Q1 | 59 | 59 | 57 | 59 | 59 |
| 2024Q2 | 61 | 59 | 61 | 61 | 59 |
| 2024Q3 | 64 | 64 | 62 | 64 | 64 |
| 2024Q4 | 66 | 59 | 61 | 63 | 63 |

Regime do model train-only suy luận từ prefix VNINDEX kết thúc đúng cutoff;
các ô bốn mã là số hợp lệ, không dùng outcome/dự báo query để phân nhóm:

| Regime PIT | Ứng viên/mã | FPT | VNM | VCB | MWG |
| --- | --- | --- | --- | --- | --- |
| BULL | 148 | 147 | 144 | 146 | 146 |
| BEAR | 0 | 0 | 0 | 0 | 0 |
| CHOPPY | 129 | 127 | 129 | 129 | 129 |
| CONSOLIDATION | 222 | 207 | 210 | 216 | 214 |

**Giới hạn coverage:** BEAR không xuất hiện trong giai đoạn/model này; không
thêm ngày hoặc đổi model để tạo đủ bốn regime. Bốn snapshot tin đều rỗng:
**0/1.944 ngày có tin đủ tin cậy**, 1.944 ngày dùng neutral strict PIT; đây
là thiếu dữ liệu tin, không phải quan sát sentiment trung tính thực tế.

**Artifact dùng tiếp:** `outputs/bayesian_benchmark/coverage.json`, envelope
`oos_coverage_v1`, checksum 24 file nguồn, bảy file code và proof/state hash từng ngày,
entry/exit, reason, coverage năm/quý/regime/tin. File runtime được gitignore;
không tạo receipt Markdown/JSON theo task. Ghi nguyên tử, cùng nội dung
không ghi lại; khác identity phải chọn đường dẫn mới trong thư mục runtime.

**Phân biệt mẫu số:** lưới ba phiên cũ có **650/660** chu kỳ OOS đủ điều kiện
sau kiểm cùng năm; **1.510** là số hợp lệ trên cả archive 2018–2024. Tập
1.944 ngày ở đây có thể chồng lấn và gồm ngày pilot đã quan sát, **chưa là
lịch benchmark**. W5-10 chọn lịch cách ≥3 phiên và tách pilot/smoke; 2023
là development thăm dò, 2024 chỉ kiểm eligibility/lịch ở bước này.

**Kiểm audit thật:** cấm đọc `.env`, DNS/socket, LLM và fit model bằng audit
hook/mock; checksum nguồn/code và proof đầy đủ PASS. Đã sửa lựa chọn mã
CLI từ HPG sang VNM, thống nhất FPT/VNM/VCB/MWG với dữ liệu thật.

**Nghiệm thu:** compileall/E2E PASS; **590 unit test** (12 test mới),
**96 test leakage PASS**; **49 artifact đóng băng nguyên SHA-256**.
Không gọi API, không sinh outcome query, không refit/tải/ghi đè nguồn.
W5-09 DONE; lịch mẫu và khóa plan được hoàn thành tiếp ở W5-10/12.

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

**DONE (09/10/2026); lịch thực, PIT/thực thi và gate hồi quy PASS.**

Bộ chọn `core/cohort_calendar.py` dùng coverage W5-09 đã ghim checksum,
kiểm lại lịch/eligibility từ nguồn và inventory 20 checkpoint pilot. Chỉ băm
byte checkpoint pilot để giữ provenance, không parse Decision/evaluation
hoặc đọc kết quả chạy để chọn ngày. Lệnh tái lập offline:

```powershell
py -3.13 -X utf8 scripts/run_bayesian_ablation.py --design-calendar
```

**Phương pháp khóa cho thiết kế:**

1. Neo lưới ba phiên tại phiên VNINDEX đầu mỗi năm; không đổi phase sau khi
   loại ngày quyền/thiếu volume hoặc qua ranh giới quý.
2. Loại 20 cutoff FPT pilot và mọi chu kỳ cùng mã có phiên giữ lệnh giao nhau
   với pilot. Với dữ liệu này, loại thêm **42 chu kỳ FPT 2023** do giao nhau.
3. Chọn smoke đầu tiên còn hợp lệ trên lưới 2023 cho từng mã; tách cutoff
   và các phiên giữ lệnh của smoke khỏi pool mẫu chính cùng mã.
4. Mỗi mã/quý đặt mục tiêu 4 điểm, chọn thứ hạng ngày cách đều trên pool còn
   hợp lệ, gồm hai đầu. Nếu chỉ chọn một điểm thì lấy giữa; thiếu mẫu giữ
   shortfall, không bù từ quý khác. Không dùng regime/tin/outcome/forecast
   để xếp hạng; coverage regime/tin chỉ thống kê sau chọn.
5. Sau API, ngày lỗi giữ nguyên trong mẫu số planned để resume/đối soát,
   không thay bằng ngày khác. Đổi mục tiêu lấy mẫu phải tạo thiết kế
   mới trước API, ghi rõ phạm vi; `--points-per-quarter` chỉ thuộc chế độ thiết kế.

**Phạm vi dự kiến: 124 điểm chính +4 smoke**, mục tiêu danh nghĩa 128 điểm
chính. Development 2023 có **60** điểm (FPT 12, ba mã còn lại 16/mã),
holdout 2024 có **64** điểm (16/mã). FPT Q1/2023 không còn ngày sau embargo
pilot: shortfall **4**, không coi 20 điểm đã quan sát là mẫu chính hoặc lấp
chỗ thiếu bằng quý khác. Đây là mẫu rút gọn theo lịch, không gọi toàn bộ OOS.

| Quý | Mục tiêu/mã | FPT | VNM | VCB | MWG |
| --- | --- | --- | --- | --- | --- |
| 2023Q1 | 4 | 0 | 4 | 4 | 4 |
| 2023Q2 | 4 | 4 | 4 | 4 | 4 |
| 2023Q3 | 4 | 4 | 4 | 4 | 4 |
| 2023Q4 | 4 | 4 | 4 | 4 | 4 |
| 2024Q1 | 4 | 4 | 4 | 4 | 4 |
| 2024Q2 | 4 | 4 | 4 | 4 | 4 |
| 2024Q3 | 4 | 4 | 4 | 4 | 4 |
| 2024Q4 | 4 | 4 | 4 | 4 | 4 |

**Bốn smoke riêng — chỉ kiểm vận hành/thăm dò, không gộp mẫu đánh giá chính:**

| Mã | Cutoff smoke | Entry | Exit |
| --- | --- | --- | --- |
| FPT | 2023-04-07 | 2023-04-10 | 2023-04-12 |
| VNM | 2023-01-03 | 2023-01-04 | 2023-01-06 |
| VCB | 2023-01-03 | 2023-01-04 | 2023-01-06 |
| MWG | 2023-01-03 | 2023-01-04 | 2023-01-06 |

Spacing ≥3 phiên được giữ xuyên quý; entry/exit cùng năm với cutoff. Tách
exposure theo `(symbol, cutoff)` và các phiên thực thi cùng mã. Cả **128/128**
điểm chính/smoke đã được adapter xác minh lại proof PIT và giá t+1/t+3,
không sinh nhãn lợi nhuận query. Development luôn là thăm dò; ở bước này
2024 chỉ kiểm lịch/eligibility, không đọc outcome/dự báo để chọn mẫu.

**Coverage sau chọn:** 2023 có BULL 11 / CHOPPY 26 / CONSOLIDATION 23;
2024 có BULL 20 / CHOPPY 6 / CONSOLIDATION 38. BEAR=0, tin reliable=0
vẫn là giới hạn nguồn, không thêm ngày/đổi model để bù regime hoặc sentiment.

**Đầu ra dùng tiếp:** `outputs/bayesian_benchmark/calendar.json` (gitignore),
`cohort_calendar_v1`: lịch development/holdout/smoke, exposure pilot,
target/available/selected/shortfall từng quý, exclusion counts, metadata
entry/exit/proof và checksum **45 file nguồn**. Thiết kế có checksum producer
riêng, ghi nguyên tử/không ghi đè identity khác; W5-09 coverage giữ nguyên byte.
Trạng thái khi tạo là `DRAFT_PENDING_QUOTA_AND_INPUT_LOCK`,
`is_execution_plan=false`. Giữ nguyên byte calendar lịch sử; W5-12 đã
khóa input/plan, W7 sẽ khóa phiên bản/ma trận. Trạng thái tiến độ hiện hành
theo README này; dự toán quota đã bỏ khỏi phạm vi.

**Kiểm lịch thật:** cấm credential, DNS/socket, LLM, refit và parse
Decision/evaluation pilot; nguồn/calendar/proof/thực thi PASS. Test tập trung
PASS cho spacing qua quý, shortfall/embargo, JSON/checksum đổi giữa đọc/ghi,
CLI offline và ngày chọn bất biến khi đổi regime/tin/development eligibility.

**Nghiệm thu:** compileall/E2E, **600 unit test** (10 test mới) và
**99 test leakage PASS**; test tập trung sau cập nhật guard checksum PASS.
**49 artifact đóng băng và coverage W5-09 nguyên byte**; không API/refit,
không chọn theo outcome/dự báo. W5-10 DONE; khóa input tiếp ở W5-12.

#### W5-12 — Khóa input/plan và dry-run bốn mã

- **Làm:** sau khi lịch mẫu W5-10 được chốt, khóa ngày theo thứ tự,
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

**DONE/PASS (09/10/2026); đây là task offline, dry-run và gate hồi quy PASS.**

“Offline” nghĩa là kiểm trên dữ liệu/model đã lưu tại máy, không đọc API
key, gọi Groq, sinh upstream/Decision mới hoặc tính outcome query. Đây là
toàn bộ phạm vi W5-12. Kiểm model/API thật và prompt từ báo cáo thật thuộc
W5-14; không cần chạy 128 điểm qua LLM để nghiệm thu W5-12.

| Điều kiện PASS W5-12 | Kết quả đã có |
| --- | --- |
| Lịch bốn mã tách pilot/smoke/development/holdout, có entry/exit đủ điều kiện | 4 smoke +60 development +64 holdout; shortfall đã công bố |
| Nguồn, model/proof, bank, tin, code/schema/runtime và config được ghim; sai hash/identity bị chặn | Manifest và binding plan PASS |
| Mọi ngày chọn qua adapter PIT, giữ hợp đồng Open(t+1)/Close(t+3), SHORT=CASH và phí/slippage | 128/128 PASS, không tạo nhãn query |
| Cấu hình cap BRPP≤600, prompt<6.500; CLI nhận đúng plan, không dùng key/mạng | Cap cấu hình và smoke CLI dry-run PASS |
| Compileall, unit, E2E, leakage và bảo toàn nguồn/bằng chứng | 609 unit/101 leakage, compileall/E2E PASS; 51 artifact bảo vệ nguyên byte |

Sau khi bỏ W5-11, các điều kiện trên đủ để đóng W5-12 và Gate C. PASS ở
đây xác nhận chuẩn bị dữ liệu/plan, chưa xác nhận lượt chạy API hoặc hiệu
quả đầu tư. Các task W5-13–16 tiếp tục giữ tiêu chí riêng.

Producer `core/research_input_lock.py` và CLI `scripts/prepare_research_inputs.py`
tái lập selection từ coverage, đối chiếu nguyên byte calendar W5-10, rồi
kiểm lại **128/128 điểm** bằng adapter và nguồn thực thi thật. Phạm vi giữ
**4 smoke +60 development 2023 +64 holdout 2024**; shortfall FPT Q1/2023
đã ghi ở W5-10. Chỉ kiểm giá Open(t+1)/Close(t+3) để xác nhận eligibility;
không tính nhãn query, gọi upstream/Decision hoặc refit model.

Chỉ thêm hai JSON runtime trong cây hiện có, đều gitignore:

```text
outputs/bayesian_benchmark/
  coverage.json     # audit W5-09, giữ nguyên byte
  calendar.json     # thiết kế W5-10, giữ nguyên byte
  input_lock.json   # khóa nguồn, cả ba cohort và kết quả dry-run
  smoke_plan.json   # plan năm nhánh có binding tới input_lock.json
  smoke_run/        # dành cho task smoke thật; chưa tạo/chạy ở W5-12
```

`input_lock.json` ghim **46 nguồn**, **46 file code/schema/cấu hình** và
**23 mục runtime/dependency**, gồm Python 3.13.5, requirements, model/proof
train-only, bank/QA, giá VCI/KBS, snapshot tin, seed=42, scope=same_symbol,
client options, retry 3 HTTP/120 giây, policy `request_admission_v2` và
đường ledger chung `outputs/oos_pilot/api_usage.json`. Ledger là dữ liệu
usage thay đổi khi chạy nên chỉ khóa đường dẫn, không đóng băng byte ledger
trong manifest. Hợp đồng phí 0,25% +trượt giá 0,10% mỗi chiều và SHORT=CASH
giữ nguyên.

Plan smoke dùng schema `research_cohort_plan_v2` hiện hành. Validator kiểm
hash manifest, code/runtime/nguồn và plan base trước runner; đổi ngày, model,
config hoặc seed rồi băm lại plan vẫn bị chặn. Runner kiểm cả policy và
ledger đã khóa. Tạo artifact bằng ghi nguyên tử độc quyền; chạy lại chỉ
nhận đúng identity cũ, không ghi đè plan khác hoặc khóa hồi tố sau run.

Development/holdout được khóa **dữ liệu/lịch**, chưa xuất executable plan
cho benchmark. `benchmark_protocol=PENDING_W7`; ngưỡng evidence mặc định
chỉ là cấu hình kỹ thuật, chưa được validation chọn làm ứng viên cuối.
Thay code/config ở W6–W7 cần identity/run mới, kế thừa đúng lịch holdout;
không sửa input lock hoặc smoke plan đã chạy.

Lệnh chuẩn bị và kiểm lại offline:

```powershell
py -3.13 -X utf8 scripts/prepare_research_inputs.py --prepare
py -3.13 -X utf8 scripts/prepare_research_inputs.py --verify
py -3.13 -X utf8 scripts/run_bayesian_ablation.py --plan outputs/bayesian_benchmark/smoke_plan.json --output-dir outputs/bayesian_benchmark/smoke_run --dry-run
```

Cap cấu hình PASS: K≤3, BRPP≤600 ký tự, cap báo cáo backtest tổng 4.000
ký tự và prompt <6.500. **Prefix và full prompt thực chưa sinh** vì chưa
chạy upstream; manifest ghi `NOT_GENERATED_NO_UPSTREAM`, không coi đây là
nghiệm thu prompt/API/model hoặc hiệu quả Bayesian. Guard kiểm prefix/prompt
thực trước từng HTTP khi chạy sau này.

Manifest và dòng console của producer hiện giữ trạng thái tại thời điểm
tạo: `LOCKED_OFFLINE_BUDGET_DEFERRED`, `budget_status=DEFERRED_BY_USER`,
`gate_c=PENDING`. Đây là metadata lịch sử, không phải kết luận tiến độ
hiện hành sau khi bỏ W5-11; không sửa byte/hash để đổi nhãn nghiệm thu.
Validator dùng chúng kiểm identity, không yêu cầu bảng dự toán để chạy
smoke. README này ghi quyết định thay đổi phạm vi: **W5-12 DONE, Gate C
PASS**; benchmark cuối vẫn chờ protocol W7.

**Nghiệm thu:** compileall/E2E, **609 unit test** (9 test mới) và
**101 test leakage PASS**; test tập trung PASS sau bổ sung khóa dependency/
code suy luận và kiểm đường dẫn. Prepare/verify thực 128/128 và CLI smoke
dry-run PASS, audit hook ghi **0 credential-open /0 DNS-connect attempt**;
LLM/refit/evaluator query bị chặn. **51 artifact được bảo vệ nguyên byte**
(49 artifact lịch sử +coverage/calendar); chỉ thêm hai JSON runtime cần
cho luồng chính. Tiếp theo W5-13 kiểm lỗi/paired/resume.

**Gate C: PASS (09/10/2026, phạm vi đã bỏ W5-11).** Coverage và giới hạn
nguồn đã công bố; lịch mẫu, nguồn/model/config/identity được khóa, dry-run
toàn bộ điểm PASS. Không còn điều kiện dự toán ngân sách/lịch chạy. Chỉ
W7 chốt protocol ứng viên cuối; smoke thật vẫn phải qua W5-14.

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

**DONE/PASS offline (09/10/2026).** Bổ sung 15 test cho cohort/evidence
trên fixture có nguồn giá, model/proof, bank/QA và checkpoint thật trong thư
mục tạm. Các phép lọc PIT, ranking, posterior, builder prompt, validator và
runner dùng code production; client LLM giả, cấm đọc key/kết nối mạng,
không chạy smoke thật hoặc benchmark.

| Rủi ro / điều kiện | Kiểm chứng |
| --- | --- |
| Quota ngày hết hoặc cooldown 1.000 giây ở mã thứ hai | `test_research_fault_recovery.py`: dừng trước upstream MWG; FPT complete nguyên byte, cả ba mã pending còn trong plan; đồng hồ giả qua cửa sổ rồi resume đủ 4/4, không xóa usage/unknown |
| Crash sau từng node durable và sau ba nhánh MWG | Bốn biên Indicator/Pattern/Trend/Full; ba nhánh đã complete giữ nguyên input/prompt/attempt; tổng upstream đúng một lần/point, 20 Decision v1 |
| Mất response trước durable; lỗi WinError 32 trước intent | Unknown chặn toàn cohort đến khi fixture xác nhận đúng UUID; giữ attempt/audit cũ. Atomic replace hết 5 retry không gửi Decision tương ứng, resume phần chưa gửi an toàn |
| Decision sai format; checkpoint/nguồn của mã chưa chọn bị sửa | Không đổi lỗi thành CASH hoặc tính điểm dở vào common support; VNM sai vẫn chặn trước agent dù chỉ chọn MWG; không bỏ điểm khỏi plan |
| Khóa OS active/released; response v2 durable trước crash | Active chặn, released tái dùng; v2 cùng shared hash v1, tổng 24 Decision fixture, resume/verify không lặp response complete |
| Biên support/score/tuổi, K_eff=0/partial và mẫu số chu kỳ | `test_research_evidence_v2.py`: n=3 so với ngưỡng 3/4, score 0,75 và số float kế tiếp, tuổi 31/30 ngày; loại ví dụ không đổi population/posterior; một cycle Trend/Pattern bullish chỉ đếm một lần |
| Exit bằng cutoff/future, pool bị chèn chu kỳ chưa đóng | `test_research_evidence_leakage.py`: loại trước stats/ranking; evidence sửa rồi băm lại vẫn bị từ chối |
| Tin tương lai/không ngày, outcome query, model/freeze sai | Bốn mã ×6 Decision fixture chỉ dùng tin có ngày ≤cutoff; query evidence whitelist không có nhãn/evaluation; model học sau cutoff hoặc freeze ≥query dừng trước upstream |
| HTTP 429/retry/format repair, lock stale và identity/cap/JSON | Tái chạy suite `test_research_invocation.py`, `test_groq_pacing.py`, `test_prior_stage_recovery.py`, `test_prior_checkpoint*.py`, cùng test CLI/input lock hiện có; mock transport/đồng hồ giả, không ngủ theo quota thật |

Các guard mới được kiểm cả số lần bị gọi khi cleanup, để một ngoại lệ
key/mạng bị nuốt cũng làm test FAIL. Test CLI dry-run đủ ba tin hợp lệ,
posterior biết trước, tập lịch sử rỗng, K=0 và cap tiếp tục được giữ từ
suite hiện có. Kết quả này là kiểm thử vận hành bằng fixture, chưa thay
nghiệm thu API/model thật của W5-14.

**Nghiệm thu:** compileall/E2E, **624 unit test** và **105 test leakage
PASS**. Nhóm tập trung 20 test PASS (15 mới +5 evidence có sẵn). **53
artifact** và **47 file code/schema/config đã khóa giữ nguyên SHA-256**;
không sửa code chạy chính, bank/model/giá/tin hoặc manifest/plan W5-12.
Mọi run fixture dùng thư mục tạm và được dọn bởi test; không tạo `smoke_run`
thật hoặc receipt JSON/Markdown mới. Tiếp theo **W5-14**, người dùng tự
thực hiện các bước terminal dưới đây; Phase D chưa đóng trước smoke thật.

#### W5-14 — Smoke vận hành thật giới hạn bốn mã

- **Làm:** sau W5-13 và Gate A/B/C PASS, hướng dẫn người dùng tự chạy
  preflight text/vision rồi **4 điểm ×5 nhánh =20 Decision** trên
  cohort smoke đã khóa ở 10–12. Giữ ledger/pacing/lock chung; dừng có kiểm soát khi hết quota.
- **Đầu ra:** checkpoint smoke riêng và verifier offline; không chạy lại
  pilot 20 FPT hoặc kích hoạt toàn benchmark trong task này.
- **Đạt khi:** 4/4 common support, 20/20 Decision hợp lệ, cap/PIT/economic
  PASS; usage/unknown có đối soát. Nếu chưa hoàn thành, ghi tiến độ/BLOCKED,
  không coi mock hoặc đổi model là thay thế nghiệm thu thật.

##### Cách tự chạy W5-14 bằng terminal

**Chỉ thực hiện bước gọi API sau khi W5-13 PASS.** Chạy từng bước từ thư
mục gốc repository. Agent không chạy các lệnh dùng API key thay người dùng.

1. Kiểm lại W5-12 offline; chỉ tiếp tục khi cả hai lệnh PASS:

   ```powershell
   py -3.13 -X utf8 scripts/prepare_research_inputs.py --verify
   py -3.13 -X utf8 scripts/run_bayesian_ablation.py --plan outputs/bayesian_benchmark/smoke_plan.json --output-dir outputs/bayesian_benchmark/smoke_run --dry-run
   ```

   Dòng nhắc ngân sách/Gate C pending là metadata cũ đã giải thích ở W5-12;
   kết quả kỹ thuật cần kiểm là input 128/128 và dry-run plan PASS. Lỗi hash,
   nguồn, runtime hoặc PIT phải xử lý trước bước tiếp theo, không sửa hash
   để ép chạy.

2. Tự đặt `GROQ_API_KEY` trong `.env`, không gửi key trong chat. Chuẩn bị
   tokenizer; lệnh này có thể tải cache công khai, không gọi Groq/dùng key:

   ```powershell
   py -3.13 -X utf8 scripts/prepare_groq_tokenizer.py
   ```

3. **Có dùng API key/quota:** kiểm text và vision đúng plan. Chỉ chạy smoke
   khi preflight PASS:

   ```powershell
   py -3.13 -X utf8 scripts/run_bayesian_ablation.py --plan outputs/bayesian_benchmark/smoke_plan.json --output-dir outputs/bayesian_benchmark/smoke_run --preflight
   ```

4. **Có dùng API key/quota:** chạy bốn điểm smoke đã khóa. Đây là lần chạy
   mới, không chạy lại pilot FPT và không chạy 124 điểm benchmark:

   ```powershell
   py -3.13 -X utf8 scripts/run_bayesian_ablation.py --plan outputs/bayesian_benchmark/smoke_plan.json --output-dir outputs/bayesian_benchmark/smoke_run --run
   ```

   Nếu thư mục đã có tiến độ, dùng lệnh resume ở bước 5, không xóa checkpoint.
   Có thể thêm `--symbol FPT` cho lượt đầu và `--symbol VNM`, `VCB`, `MWG`
   cho các lượt `--run --resume` tiếp theo; vẫn dùng đúng plan/thư mục chung.

5. Nếu bị quota/cooldown, giữ ledger/checkpoint và theo mốc nghỉ runner
   thông báo. Khi đã đủ điều kiện tiếp tục, tự chạy **có API key/quota**:

   ```powershell
   py -3.13 -X utf8 scripts/run_bayesian_ablation.py --plan outputs/bayesian_benchmark/smoke_plan.json --output-dir outputs/bayesian_benchmark/smoke_run --run --resume
   ```

   Nếu báo response `unknown`/`ambiguous` hoặc `Decision chưa rõ` (kể cả
   attempt đã FAILED vì sai format), đối soát offline trước:

   ```powershell
   py -3.13 -X utf8 scripts/run_bayesian_ablation.py --plan outputs/bayesian_benchmark/smoke_plan.json --output-dir outputs/bayesian_benchmark/smoke_run --reconcile
   ```

   Dừng quota trước khi tạo attempt có thể resume sau cooldown. Nếu đã
   có attempt mà runner chặn replay, đổi key hoặc chạy lại lệnh không thay
   bước đối soát. Không tự xóa ledger/lock/reserve hoặc cho phép replay
   unknown/failed. Gửi log đã che thông tin nhạy cảm để xác định stage cần xử lý.

6. Sau khi smoke chạy xong, kiểm offline, không dùng key/gọi API:

   ```powershell
   py -3.13 -X utf8 scripts/run_bayesian_ablation.py --plan outputs/bayesian_benchmark/smoke_plan.json --output-dir outputs/bayesian_benchmark/smoke_run --verify-only
   ```

   Chỉ đóng W5-14 khi verifier xác nhận **4/4 điểm, đủ 20 Decision hợp lệ**,
   cùng shared upstream, cap/PIT/economic PASS và usage/unknown được đối soát.
   Chạy dở hoặc preflight PASS riêng chưa đủ để đóng W5-14.

##### Kết quả nghiệm thu W5-14 — DONE, 10/10/2026

Người dùng đã chạy preflight và smoke thật; agent kiểm `--verify-only`
và `--reconcile` offline. Nguồn tại `outputs/bayesian_benchmark/smoke_run/`,
plan `outputs/bayesian_benchmark/smoke_plan.json`, ledger chung
`outputs/oos_pilot/api_usage.json`. Không tạo receipt hoặc sao chép response
vào Git. Run signature:
`16ac88a4c62d79a3bc628e70fc8d90300980456207d7f3fc22360f241d49aa9c`.

| Mã | Cutoff | Common support | Decision structured |
| --- | --- | ---: | ---: |
| FPT | 07/04/2023 | 1/1 | 5/5 |
| MWG | 03/01/2023 | 1/1 | 5/5 |
| VCB | 03/01/2023 | 1/1 | 5/5 |
| VNM | 03/01/2023 | 1/1 | 5/5 |

- **4/4 điểm, 20/20 Decision**, tất cả `complete/llm_structured`; mỗi node
  Indicator/Pattern/Trend/Full có một attempt complete, năm nhánh cùng shared hash.
  Semantic verifier dựng lại input/prompt/Decision/P&L và nguồn PIT PASS;
  report dựng lại khớp payload đã lưu, không còn điểm pending hoặc attempt
  chưa rõ của smoke cần replay.
- Preflight text/vision HTTP 200 đúng hash plan. Riêng smoke có **28 HTTP 200**
  (4 Pattern +4 Trend +20 Decision), không có HTTP lỗi hoặc thiếu usage.
  Text **38.691 token**, vision **16.687 token**, tổng **55.378**; không cộng
  preflight hoặc request W4 vào chi phí smoke. Unknown/reserve cũ của W4 giữ nguyên.
- Prompt thực tối đa **4.438 ký tự <6.500**; prefix **370 ≤600**. Đã đo
  pacing trên đủ 28 request: tổng **1.043,070 giây**, p95 **60,129 giây**;
  đây là nghỉ chủ động theo quota, tách khỏi HTTP p95 **1,093 giây**.
- Audit offline: không mở credential hoặc gọi DNS/socket connect;
  checkpoint/report/ledger giữ nguyên byte. `primary_status=NOT_APPLICABLE`
  đúng với `smoke_v1`; bốn điểm này không chứng minh hiệu quả Bayesian v2
  hoặc thay thế benchmark 124 điểm. Không cần chạy thêm API/resume cho W5-14.

#### W5-15 — Nghiệm thu hồi quy và điều kiện mở W6

- **Làm:** chạy bốn gate AGENTS.md trên bản code chốt; rà checklist A/B/C,
  smoke, nguồn/model/hash, lịch mẫu/guard, giới hạn nghiên cứu và cách verify W4.
  Nghiệm thu code v2 bằng offline fixtures/trace, không lấy smoke v1 làm
  bằng chứng hiệu quả v2. Đo p95 lại khi thay retrieval/statistics tại 08.
  Chỉ đo lại retrieval p95 nếu thay đường này/môi trường hoặc có hồi quy cụ thể.
- **Đầu ra:** kết quả nghiệm thu gọn tại README, số test thực tế/commit/
  lệnh kiểm; không tái dùng số 521 để gắn PASS cho bản W5 chưa kiểm.
- **Đạt khi:** compileall, toàn unit, E2E, toàn leakage PASS; smoke W5-14
  đủ tiêu chí, không còn gate kỹ thuật chưa giải quyết. Không yêu cầu dự toán
  ngân sách/lịch chạy. Sẵn sàng vận hành không đồng nghĩa hiệu quả đầu tư đã chứng minh.

##### Nghiệm thu W5-15 — DONE/PASS, 10/10/2026

Bản code kiểm: `fd1fa66`, gồm test fault/evidence ở `f376eb1`.
Task nghiệm thu chỉ cập nhật tài liệu; không sửa code/schema/config đã khóa.
Đã chạy lại bốn lệnh tại mục 4 trên Python 3.13.5:

| Gate | Kết quả thực tế |
| --- | --- |
| Compileall toàn codebase | PASS |
| Unit discover toàn bộ | **624/624 PASS**, 1.128,558 giây; không skip/failure/error |
| E2E xác định | PASS: graph, Decision/Alpha/Sentiment, P&L/phí, JSON, ảnh và runtime/memory |
| Leakage discover riêng | **105/105 PASS**, 215,704 giây; không skip/failure/error |

- Rà lại Gate A/B/C và xác minh input lock **128/128**: 4 smoke,
  60 development 2023, 64 holdout 2024; nguồn/model/runtime, ngày/entry/exit,
  seed/scope/policy và binding plan khớp. Không tạo nhãn/query outcome cho
  mẫu chính. Metadata pending/ngân sách trong manifest là snapshot đã
  đóng băng ở W5-12; checklist hiện hành áp dụng phạm vi đã bỏ W5-11.
- Kiểm lại smoke bằng semantic verifier, report dựng lại khớp kết quả;
  bằng chứng thực ở mục W5-14. Code v2 được nghiệm thu bằng các fixture/trace
  trong bộ unit: posterior/counts/CrI, support/score/tuổi/K_eff, cap/Original
  khi gate tắt, sáu Decision dùng chung Full, retry, durable response,
  quota/unknown/lock/atomic I/O và chống leakage. Không coi smoke v1 là
  thực nghiệm hiệu quả v2 hoặc đã chạy benchmark sáu nhánh.
- Hướng dẫn kiểm W4 bằng worktree tại commit `27b5907` còn hợp lệ:
  **31/31 file code đã ghim** khớp nội dung Git sau chuẩn hóa newline,
  **12/12 nguồn** còn khớp hash byte. Khi kiểm pilot cũ dùng phiên bản W4;
  không ép identity W4 sang code W5. Sau bốn gate, **122/122 file bảo vệ**
  nguyên byte, gồm 47 code/schema/config đã khóa, nguồn, bank/model,
  lịch/input/plan, pilot/smoke/checkpoint/ledger/audit và ZIP bằng chứng.

**Gate retrieval <30 ms PASS sau khi giảm tải máy.** Giữ cả lượt đầu FAIL
và lượt đo lại sau khi người dùng tạm đóng tác vụ nặng. Hai lượt cùng code,
method/context/query, nguồn và runtime; không chọn lại mẫu. Đã chạy
`scripts.benchmark_bayesian_retriever.benchmark(warmup=100, samples=1000)`:
16 context lịch sử PIT đã khóa, hai scope, 32 query/mode, luân phiên tuần tự;
đồng hồ `perf_counter_ns`, p95 nearest-rank `ceil(.95*N)`. Đo retrieval,
formatter và chuỗi kết hợp riêng; giữ toàn bộ mẫu, validation/deep-copy,
oracle ngoài timer, không cache kết quả hoặc loại outlier. Môi trường Python,
OS/CPU và bốn dependency trong receipt khớp lượt đo W4.

| Mode v1 | p95 lượt có tải (ms), FAIL | p95 đo lại tổng hợp (ms) | p95 đo lại same_symbol (ms) | Gate đo lại <30 ms |
| --- | ---: | ---: | ---: | --- |
| Bayesian | 35,252 | 10,566 | 2,921 | PASS |
| Random | 36,221 | 9,831 | 2,709 | PASS |
| Recent | 33,934 | 9,642 | 2,598 | PASS |
| Similarity | 42,224 | 12,127 | 3,289 | PASS |

- Khi đo, TFT/League đang tiêu thụ nhiều CPU; hai snapshot cách nhau hai giây
  cho thấy riêng TFT dùng khoảng 8,5–9,3 CPU-giây. Chẩn đoán 100 query pooled
  ghi CPU/wall khoảng 0,751; một hot query không phát sinh audit event.
  Số đo lại thấp hơn phù hợp với ảnh hưởng tải/scheduling. Ngưỡng và số mẫu
  giữ nguyên, priority/affinity mặc định, đủ validation/deep-copy; code và
  manifest nguyên byte. Gate PASS áp dụng máy/cấu hình/tải của lượt đo lại,
  không bảo đảm p95 <30 ms khi máy đang chạy tác vụ nặng.
- Đường evidence v2 được đo riêng bằng API công khai trên **20 context**
  (16 lịch sử đã khóa +4 shared query smoke, chỉ lấy symbol/cutoff/regime/signals),
  scope cùng mã/cùng regime/PIT, cùng 100 warm-up/1.000 mẫu mỗi giai đoạn.
  Lượt đo lại: p95 retrieval **5,0475 ms**, prefix **1,2018 ms**, chuỗi kết hợp
  **6,3819 ms**. Lượt có tải giữ nguyên: **22,204 / 7,708 / 30,985 ms** tương ứng.
  Đầu ra/selected IDs/counts/posterior/prefix khớp tham chiếu ở mọi lượt;
  query/expected không đổi, hot query bị chặn I/O và không gọi LLM.
  Ngưỡng 30 ms của bảng trên áp cho retrieval, không áp lại cho chuỗi kết hợp.
- Mẫu chi tiết và log chỉ ở thư mục tạm `kltn-research-acceptance` của máy;
  đã giữ bản `performance_v1_busy.json`/`performance_v2_busy.json` và
  `performance_v1_idle.json`/`performance_v2_idle.json`, không thêm JSON
  vào Git. Audit input/smoke/performance không mở credential,
  DNS hoặc socket connect. **122/122 file bảo vệ vẫn nguyên byte** sau đo.

Để đo lại v1 offline từ root sau khi giảm tải, dùng API benchmark sẵn có,
chỉ in console, không tạo thêm receipt trong repository:

```powershell
py -3.13 -X utf8 -c "from scripts.benchmark_bayesian_retriever import benchmark; r=benchmark(warmup=100,samples=1000); print({m:v['retrieval']['summary']['p95_ms'] for m,v in r['modes'].items()}); raise SystemExit(0 if r['status']=='PASS' else 1)"
```

Phép đo lại đủ mẫu PASS, nguồn/checkpoint còn nguyên vẹn; **W5-15 DONE**.
Bốn gate hồi quy của cùng task vẫn áp dụng: code/schema/config đã kiểm
không đổi; lượt tiếp tục này chỉ đo lại p95 và sửa tài liệu.
Các giới hạn BEAR OOS=0, tin reliable=0, FPT Q1 thiếu bốn mẫu và model proof
train-only hồi cứu vẫn phải giữ khi bàn giao. V2 chưa có bằng chứng hiệu quả
đầu tư; protocol ứng viên chờ W7, benchmark chờ W8. **Nghiệm thu kỹ thuật
để mở W6 PASS**; đây là đầu vào cho phần chốt tuần và bàn giao W5-16 bên dưới.
Không cần chạy thêm API để nghiệm thu W5-15.

#### W5-16 — Chốt W5, bàn giao vận hành và thứ tự triển khai W6

- **Làm:** cập nhật checklist, kế hoạch tổng và hướng dẫn lệnh thật cho
  prepare/dry-run/preflight/run/verify/resume từng mã để người dùng tự chạy;
  ghi nơi lưu dữ liệu, xử lý dừng/unknown và trách nhiệm đối soát.
  Bàn giao contract/implementation v2 cho W6; W7 chọn/khóa ứng viên,
  W8 mới chạy benchmark. Ghi rõ code đã có và ý tưởng còn chờ kiểm chứng.
- **Đầu ra:** README này là sổ tiến độ chính; bổ sung hướng dẫn độc lập
  chỉ khi cần. Không tạo 16 biên bản task hoặc đẩy toàn bộ output lên GitHub.
- **Đạt khi:** 15/15 task trong phạm vi và các gate PASS, manifest mẫu bất biến,
  lệnh có thể chạy lại. Bất kỳ gate nào còn BLOCKED thì chưa chốt W5 hoàn thành.

**DONE/PASS (10/10/2026), Gate D PASS.** Chốt **15/15 task**, cả bốn phase
PASS. Lượt W5-16 chạy lại compileall, **624 unit test**, E2E và **105 test
leakage**, tất cả PASS, không skip. Kiểm input **128/128**, CLI dry-run,
verifier smoke **4/4 điểm, 20/20 Decision** và reconcile offline PASS;
report dựng lại khớp bản lưu. **122/122 file bảo vệ nguyên byte**, gồm nguồn,
manifest/plan, checkpoint, ledger/audit và code/schema/config đã khóa.
Audit các lệnh input/smoke ghi **0 credential-open /0 network attempt**.
Kế thừa phép đo p95 PASS ở W5-15 vì code/môi trường không đổi; task này chỉ
sửa ba Markdown chính, không tạo receipt hoặc gọi API. W6 đủ điều kiện
lập kế hoạch chi tiết và triển khai theo bàn giao dưới đây.

##### Vận hành từ trạng thái đã hoàn thành

Smoke hiện **complete: 4/4 điểm, 20/20 Decision v1**. Bây giờ chỉ cần kiểm
offline khi đối soát hoặc phục hồi máy; không cần gọi API thêm để đóng W5.
Chạy từ root repository với Python 3.13.5:

```powershell
$cohortPlan = "outputs/bayesian_benchmark/smoke_plan.json"
$cohortOutput = "outputs/bayesian_benchmark/smoke_run"
$sharedLedger = "outputs/oos_pilot/api_usage.json"
py -3.13 -X utf8 scripts/prepare_research_inputs.py --verify
py -3.13 -X utf8 scripts/run_bayesian_ablation.py --plan $cohortPlan --output-dir $cohortOutput --ledger $sharedLedger --dry-run
py -3.13 -X utf8 scripts/run_bayesian_ablation.py --plan $cohortPlan --output-dir $cohortOutput --ledger $sharedLedger --verify-only
py -3.13 -X utf8 scripts/run_bayesian_ablation.py --plan $cohortPlan --output-dir $cohortOutput --ledger $sharedLedger --reconcile
```

Verifier phải trả complete, bốn điểm common support và năm nhánh mỗi điểm;
reconcile không còn attempt cần xử lý. `primary_status=NOT_APPLICABLE` là đúng
cho `smoke_v1`; đây chưa phải benchmark v2. Nếu muốn đối soát từng mã, thêm
`--symbol FPT`, `--symbol MWG`, `--symbol VCB` hoặc `--symbol VNM` vào lệnh
`--verify-only`; validator vẫn kiểm identity/nguồn của cả cohort.

Các bước prepare/preflight/run/resume đã có ở
[hướng dẫn terminal W5-14](#cách-tự-chạy-w5-14-bằng-terminal). Quy tắc dùng lại:

| Bước | Khi nào dùng | Điều kiện |
| --- | --- | --- |
| `prepare_research_inputs.py --prepare` | Chuẩn bị lần đầu khi chưa có input lock/plan | Giữ nguyên calendar/nguồn đã khóa; máy phục hồi cần bản gốc, không dựng lại bằng nguồn mới |
| `--dry-run` | Trước run hoặc sau phục hồi môi trường | Input/PIT/code/runtime PASS; hiện có 128 điểm đã khóa |
| `--preflight` | Người dùng chuẩn bị một run cần API | Hai model HTTP 200, đúng plan hash; có dùng key/quota |
| `--run --symbol FPT` | Chỉ lượt đầu của thư mục run mới, đúng plan/identity | Chưa có tiến độ; không áp dụng lại cho smoke hiện đã complete |
| `--run --resume --symbol <mã>` | Tiếp tục mã còn thiếu trong cùng run | Giữ output/plan/ledger/policy; không gọi lại nhánh complete |
| `--verify-only`, `--reconcile` | Sau dừng, trước resume, khi nghiệm thu | Offline; report lưu từ lần run trước có thể chưa phản ánh điểm vừa lỗi |

Ví dụ **chỉ dành cho người dùng tự chạy khi run cùng identity còn thiếu**,
sau preflight PASS và xử lý nguyên nhân dừng; hiện cả bốn mã đã xong:

```powershell
py -3.13 -X utf8 scripts/run_bayesian_ablation.py --plan $cohortPlan --output-dir $cohortOutput --ledger $sharedLedger --run --resume --symbol FPT
py -3.13 -X utf8 scripts/run_bayesian_ablation.py --plan $cohortPlan --output-dir $cohortOutput --ledger $sharedLedger --run --resume --symbol MWG
py -3.13 -X utf8 scripts/run_bayesian_ablation.py --plan $cohortPlan --output-dir $cohortOutput --ledger $sharedLedger --run --resume --symbol VCB
py -3.13 -X utf8 scripts/run_bayesian_ablation.py --plan $cohortPlan --output-dir $cohortOutput --ledger $sharedLedger --run --resume --symbol VNM
```

Đổi code/model/config ở W6 cần **plan/identity/output mới**, chưa có lệnh
benchmark dùng được từ smoke plan này. Giữ ledger chung cho cùng tài khoản;
đổi key không mặc nhiên đặt lại quota tổ chức. Không có bước tính ngân sách
hoặc dự toán lịch chạy API trong bàn giao.

Mốc code W5 đã nghiệm thu: **`0286119`**; W5-16 chỉ sửa tài liệu. Sau khi code
W6 thay đổi, kiểm smoke lịch sử bằng checkout độc lập của mốc này, phục hồi
đúng nguồn/runtime từ identity theo cách đã hướng dẫn cho W4 ở mục baseline.
Không sửa fingerprint của smoke để nhận code mới.

##### Dữ liệu cần giữ và xử lý khi dừng

| Vị trí | Nội dung / trách nhiệm bảo toàn |
| --- | --- |
| `outputs/bayesian_benchmark/{coverage.json,calendar.json,input_lock.json,smoke_plan.json}` | Lịch 124 điểm chính +4 smoke, source/code/runtime hash; giữ nguyên byte |
| `outputs/bayesian_benchmark/smoke_run/` | `cohort.json`, `report.json`, `v1/<mã>/{identity.json,run_manifest.json,results.json,points/,responses/}`; journal/attempt là cơ sở resume |
| `outputs/oos_pilot/{api_usage.json,reconciliation/,inputs/}` và `outputs/pilot_fpt_run/` | Ledger chung, audit/backup ngoại lệ W4, pilot 20 điểm/100 Decision; giữ unknown reserve 5.535 token |
| `data_manager/`, `data/execution_prices_oos/` và các nguồn liệt kê trong input lock | Bank 852 episode, manifest/model/proof, QA, giá VCI/KBS, snapshot tin và train archive đúng checksum |
| `docs/plan/implementation_evidence.zip` | Bằng chứng lịch sử đóng gói, không sửa byte |

Runtime output được gitignore; clone Git riêng không đủ khôi phục nghiên cứu.
Người dùng lưu bản sao an toàn của **toàn bộ nguồn được identity dẫn chiếu,
plan/checkpoint/journal/ledger/audit** khi không có runner đang ghi. Khi chuyển
máy, phục hồi runtime/dependency rồi verify; metadata lock/owner/recovery được
quản lý bởi cơ chế khóa, không dùng bản sao owner đang chạy làm bằng chứng khóa.

1. **Quota/cooldown:** giữ nguyên checkpoint/ledger, chờ mốc runner báo; người
   dùng tự resume. Pacing chủ động khác với thời gian HTTP; không bỏ guard để
   hết chờ. Không xóa usage/reserve hoặc đổi mẫu khi quota chặn.
2. **Unknown/FAILED/malformed Decision:** chạy reconcile offline, đọc stage,
   UUID và output durable. Chỉ tiếp tục tự động phần chưa gửi hoặc đã durable
   hợp lệ. Replay attempt không rõ kết quả cần người dùng xác nhận đúng UUID
   và lý do qua `--reconcile --authorize-replay ... --replay-reason ...` sau
   đối soát; giữ audit và chi phí cũ. Không biến lỗi thành CASH.
3. **Lock/PERSISTENCE/hash/runtime:** dừng, kiểm owner OS và lỗi ghi; sự tồn tại
   file lock không chứng minh runner còn sống. Không xóa khóa/checkpoint hay
   sửa hash để ép resume; khôi phục đúng nguồn/môi trường hoặc tạo run mới.
4. **Phân công:** người dùng giữ key, tự preflight/run/resume và quyết định
   replay; agent kiểm offline, chẩn đoán stage/identity, sửa code trên nhánh
   riêng và chạy gate. Hỗ trợ Windows/OneDrive đã kiểm; chưa nghiệm thu khóa
   trên Linux hoặc filesystem dùng chung.

##### Bàn giao kỹ thuật W6

| Nền tảng đã có và kiểm thử ở W5 | Việc W6 phải bổ sung/kiểm chứng |
| --- | --- |
| `core/bayesian_retriever.py`, `core/prior_evidence_v2.py`: retrieval tín hiệu, Beta–Binomial, quality gate, prefix v2 | Đặc trưng giá PIT +scaler train-only, auxiliary index/hash riêng; recency/diversity không chọn theo WIN/LOSS; so với `signal_match_v1` |
| Evidence có population/support/uncertainty và ví dụ K≤3 riêng | Thống kê điều kiện regime+tín hiệu, shrink có luật; không coi K=3 hay bốn agent là bốn quan sát độc lập |
| `core/research_cohort.py`: Decision v2 riêng, dùng chung Full/upstream với v1, fixture resume/semantic PASS | Contract Decision đối chiếu bằng chứng, trace và ứng viên stats-only/examples-only/full prior; protocol/schema/identity mới cho CLI thật |
| `core/groq_pacing.py`, `core/research_invocation.py`, `core/prior_stage_journal.py`, `core/prior_checkpoint.py`, `core/prior_run_lock.py` | Kế thừa request admission/retry/durable/lock; kiểm hồi quy, paired/PIT/caps/p95 khi thêm ứng viên |

Thứ tự triển khai: **chốt danh sách ứng viên nhỏ → đặc trưng/ranking → thống kê
điều kiện → Decision/trace → tích hợp protocol và kiểm thử**. Nếu thêm risk
gate số học, tách ablation và lưu `raw_action`/`executed_action`/reason/policy
hash; không ghi công cải thiện của risk gate cho riêng ICL. Bank/model đã
khóa và công thức Open(t+1)→Close(t+3), SHORT=CASH, phí hai chiều giữ nguyên.

**Điều kiện bàn giao tiếp:** W6 có code CLI v2, fixture/validation train PIT,
trace và bốn gate PASS; W7 dùng train 2020–2022/development 2023 để chọn và
khóa ứng viên; **W8 mới benchmark xác nhận 2024** theo lịch đã khóa. Chưa mở
holdout để chọn tham số hoặc chạy 124 điểm trong W5-16. BEAR OOS=0, tin
reliable=0, FPT Q1 thiếu bốn mẫu và model proof train-only hồi cứu là giới
hạn còn hiệu lực. Smoke v1 và fixture v2 chứng minh vận hành, chưa chứng minh
Bayesian v2 cải thiện lợi nhuận. Chi tiết phạm vi tiếp theo ở
[kế hoạch tổng, mục Tuần 6](../plan.md).

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

Nhật ký dưới đây giữ kết luận tại thời điểm ghi; dòng điều chỉnh phạm vi
cuối cùng và checklist mục 3 xác định tiến độ hiện hành.

| Ngày | Phạm vi | Trạng thái / kết quả | Bước tiếp theo |
| --- | --- | --- | --- |
| 07/10/2026 | Lập kế hoạch W5 | PLAN_READY; 0/16 triển khai; kế thừa pilot W4 đã hoàn thành | Bắt đầu W5-01 |
| 07/10/2026 | Kiểm thay đổi tài liệu | Compileall/E2E, 521 unit/93 leakage PASS; đủ 16 task và liên kết nội bộ hợp lệ; không API | Gate triển khai W5 vẫn chờ thực hiện từng task |
| 07/10/2026 | W5-01 | DONE: verifier offline 20/20; 100 Decision; 31 code/12 source/runtime khớp W4; 15 point/75 Decision cũ, audit và reserve 5.535 nguyên vẹn; 97 file không đổi. Compileall/E2E, 521 unit/93 leakage PASS | W5-02; baseline và cách kiểm lại W4 ở mục 1 |
| 07/10/2026 | W5-02 | DONE: result/summary dựng lại khớp payload đã lưu; bảng năm nhánh cùng 20 điểm, nhãn/coverage/Decision có mẫu số đầy đủ; 97 file bất biến không đổi. Compileall/E2E, 521 unit/93 leakage PASS; không LLM hoặc thay đổi công thức/ma trận | W5-03; rà annualization ở W5-04 |
| 07/10/2026 | Điều chỉnh lộ trình theo pilot | PLAN_UPDATED: 1/20 action khác Original, ca FPT 20/02 giải thích chênh return; giữ bốn phase/16 task và 2 DONE, thêm code audit/posterior/gate/prefix vào task còn TODO. Lộ trình 10 tuần, tách 2023 development/2024 holdout; compileall/E2E, 521 unit/93 leakage PASS; không API hoặc sửa pilot | W5-03 rồi W5-04; W6–W7 cải thiện/validation, W8–W10 benchmark/thống kê/luận văn |
| 07/10/2026 | W5-03 | DONE: CLI/API audit readonly; 146 HTTP 200 +một unknown; charged text 194.218/vision 102.034, reserve 5.535 giữ nguyên; 100 attempt complete +một failed; 1/20 bất đồng, chênh return −2,241809 điểm phần trăm. Timer v1 thiếu ghi null, không đoán pacing/role; verifier pilot 20/20, audit hook 0 credential/network, 82 file bất biến. 15 test mới; compileall/E2E, 536 unit/93 leakage PASS | W5-04: contract vận hành/v2, metric/phân hoạch và telemetry run mới |
| 08/10/2026 | W5-04 | DONE, Gate A PASS: chốt research_evaluation_contract_v2, retry/resume/identity, split train/2023/2024, primary theo mã và trung bình bốn mã, cycle-risk metric không annualize, evidence/gate/prefix và telemetry v2. Gắn yêu cầu với 05–08/13–15; code v2 vẫn TODO. Compileall/E2E, 536 unit/93 leakage PASS; 82 file khớp baseline, không API hoặc thêm receipt | W5-05: triển khai policy quota/pacing theo hợp đồng |
| 08/10/2026 | W5-05 | DONE: request_admission_v2 qua CLI, khóa policy vào identity; guard HTTP giữ reserve, dừng/cooldown có reason và mốc resume; đo pacing, kiểm cache trước run, đọc ledger sau khóa OS. Compileall/E2E, 546 unit/93 leakage và dry-run 20 cutoff PASS; 49 artifact bất biến, không API. Retry xuyên invocation/format repair còn thuộc 07/08 | W5-06: atomic I/O trên Windows/OneDrive |
| 08/10/2026 | W5-06 | DONE: retry replace/cleanup có giới hạn cho WinError 5/32/33, không ghi/fsync lại hoặc che lỗi gốc; hướng dẫn PERSISTENCE/runtime local. Test handle Windows thật và checkpoint retry không lặp agent/không sửa complete. Compileall/E2E, 555 unit/93 leakage PASS; 49 artifact bất biến, không API hoặc thêm receipt | W5-07: response durable và đối soát upstream |
| 08/10/2026 | W5-07 | DONE: journal output Indicator/Pattern/Trend/Full gắn identity/input/source; phục hồi output durable không lặp node, unknown chặn trước agent. CLI reconcile offline và xác nhận UUID/lý do có audit, giữ unknown/chi phí cũ. Compileall/E2E, 562 unit/93 leakage PASS; 49 artifact bất biến. Journal ở biên node, không cam kết exactly-once HTTP | W5-08: CLI bốn mã, retry/telemetry và nền tảng Bayesian v2 |
| 09/10/2026 | W5-08.a–d | DONE: CLI cohort bốn mã, identity/checkpoint/report v2; posterior Beta–Binomial, quality gate, prefix và Decision độc lập dùng chung Full; retry HTTP/format repair chung 3 lượt/120 giây, telemetry invocation. Compileall/E2E, 578 unit/93 leakage PASS; verifier W4 20/20, 49 artifact bất biến. Phase B PASS; không API/benchmark/holdout tuning | W5-09: coverage và lịch OOS |
| 09/10/2026 | W5-09 | DONE: audit 1.996 ngày OOS, adapter PIT xác minh 1.996/1.996; 1.944 hợp lệ, 28 loại quyền +24 vượt năm. Lưới cũ 650/660, không dùng 1.510 toàn archive làm cỡ mẫu OOS. Runtime coverage gitignore, bảng năm/quý/regime/tin trong README; BEAR=0, tin reliable=0. Compileall/E2E, 590 unit/96 leakage PASS; 49 artifact bất biến, không API/refit/outcome query | W5-10: chọn lịch ≥3 phiên, tách pilot/smoke và development/holdout |
| 09/10/2026 | W5-10 | DONE: lịch step3 neo đầu năm, mục tiêu 4 điểm/mã/quý; 124 chính (60 development/64 holdout) +4 smoke riêng, adapter xác minh 128/128. Loại 20 cutoff pilot và 42 chu kỳ FPT giao phiên giữ lệnh; FPT Q1 thiếu 4, không bù quý khác. Calendar draft gitignore, checksum 45 nguồn; không outcome/forecast/API/refit. Compileall/E2E, 600 unit/99 leakage PASS; guard checksum kiểm tập trung, 49 artifact và coverage bất biến | W5-11: tính ngân sách/quota cho lịch dự kiến; W5-12 khóa input/plan |

| 09/10/2026 | W5-11 | TẠM HOÃN theo yêu cầu: chưa nghiệm thu ngân sách/thời hạn, không đánh DONE/PASS quota; bỏ mã dự toán dở, không API hoặc budget runtime. Giữ 10/16 task hoàn thành | W5-12: chỉ phần khóa nguồn/lịch và dry-run offline; Gate C còn pending |

| 09/10/2026 | W5-12 | DONE phần offline: khóa input/lịch 4 smoke +60 development +64 holdout, prepare/verify thực 128/128 và CLI smoke dry-run PASS. Hai JSON runtime gitignore; 46 nguồn/46 code-schema-config/23 runtime, binding plan và policy/ledger chung. Compileall/E2E, 609 unit/101 leakage PASS; 51 artifact nguyên byte, audit 0 credential/DNS-connect. Prompt thực chưa sinh; W5-11 tạm hoãn, Gate C pending | W5-13: kiểm lỗi/paired/resume offline; protocol benchmark cuối chờ W7 |

| 09/10/2026 | Điều chỉnh phạm vi và làm rõ W5-12 | PLAN_UPDATED: bỏ W5-11 và điều kiện dự toán/lịch chạy khỏi W5–W8; giữ ngày dữ liệu/cohort và guard runtime. W5-12 DONE toàn bộ phạm vi offline; Gate C PASS theo tiêu chí mới, 11/15 task. Các lượt dùng API key do người dùng tự chạy theo hướng dẫn W5-14. Kiểm lại 128/128 và CLI dry-run PASS, audit 0 credential/network; compileall/E2E, 609 unit/101 leakage PASS. 53 artifact gồm manifest/plan giữ nguyên byte; chỉ sửa ba Markdown | W5-13 offline; sau đó người dùng tự chạy preflight/smoke W5-14 |

| 09/10/2026 | W5-13 | DONE offline: thêm 15 test cho fault/resume cohort bốn mã, biên quality/posterior và leakage evidence v2; 20 test tập trung PASS. Compileall/E2E, 624 unit/105 leakage PASS. Giữ output/nhánh durable và shared hash; quota/cooldown, unknown, atomic intent, malformed Decision, lock và nguồn mã chưa chọn được kiểm. 53 artifact/47 code-schema-config đã khóa bất biến; không key/API hoặc sửa code chạy chính. Cập nhật hướng dẫn đối soát attempt FAILED; 12/15 task | W5-14: người dùng tự chạy preflight và smoke v1 4 điểm/20 Decision, rồi verifier offline |

| 10/10/2026 | W5-14 | DONE: người dùng chạy smoke thật 4/4 điểm, 20/20 Decision structured; verifier/reconcile offline PASS, report dựng lại khớp. Preflight đúng plan; smoke 28 HTTP 200, usage đủ 55.378 token, không attempt chưa rõ. Shared/PIT/economic PASS, prompt/prefix tối đa 4.438/370; checkpoint/ledger không đổi khi kiểm, không key/API từ agent; 13/15 task | W5-15: bốn gate hồi quy, rà nguồn/giới hạn và p95 |

| 10/10/2026 | W5-15 | BLOCKED ở p95: compileall/E2E, 624 unit/105 leakage PASS; input 128/128, smoke 4/4 và 20 Decision xác minh lại. 122 file/47 code-schema-config nguyên byte; W4 31 code ở commit ghim/12 nguồn khớp. Benchmark v1 đủ mẫu khi TFT/League có tải cho p95 33,934–42,224 ms, FAIL <30; giữ toàn bộ mẫu. Evidence retrieval v2 p95 22,204 ms; không key/API hoặc sửa code/fingerprint. Giữ tiến độ 13/15 | Người dùng giảm tải máy, đo lại cùng protocol; chưa đánh DONE/mở W6 |

| 10/10/2026 | W5-15 tiếp tục sau giảm tải | DONE/PASS: cùng code/mẫu/protocol/runtime, bốn mode v1 p95 10,566/9,831/9,642/12,127 ms đều <30; evidence v2 retrieval/prefix/kết hợp 5,0475/1,2018/6,3819 ms. Giữ cả mẫu FAIL/PASS ở TEMP, 122 file/47 code-schema-config nguyên byte; bốn gate của cùng task (624 unit/105 leakage, compileall/E2E) vẫn hợp lệ vì code không đổi. Không key/API hoặc thêm receipt vào Git; 14/15 task | W5-16: chốt W5 và bàn giao W6 |
| 10/10/2026 | W5-16 | DONE, W5 CLOSED: 15/15 task, Phase A/B/C/D PASS. Bàn giao lệnh từng mã, dữ liệu/khôi phục/unknown và phạm vi W6 trong README này; cập nhật kế hoạch tổng/README gốc. Chạy lại compileall/E2E, 624 unit/105 leakage PASS; input 128/128, smoke 4/4–20 Decision, reconcile và report khớp; 122 file nguyên byte, audit offline 0 credential/network. Chỉ sửa ba Markdown, không API hoặc receipt mới | Lập plan chi tiết W6 trong `docs/plan/week6/`; cải thiện retrieval/Decision, W7 validation/khóa ứng viên, W8 benchmark |
