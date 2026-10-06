# W4-13 — Leakage toàn đường tích hợp

**Ngày:** 06/10/2026. **Nhánh:** `test/prior-pipeline-leakage`, baseline
`af8c8ca`. [Receipt](pipeline_leakage_review.json), [Phase D](phase_d_validation_handoff.md),
[checklist W4](README.md).

## Đường kiểm và nguồn bằng chứng

Thêm `tests/test_prior_pipeline_leakage.py`, **11 test mới**. Suite chạy loader
giá/model/kho, adapter PIT, sentiment snapshot, graph, orchestration Alpha,
retriever/ranking/stats, formatter/prompt builder, checkpoint/resume và đánh giá
kinh tế production. Nhãn mọi episode tổng hợp, kể cả MWG trong scope pooled,
được sinh bằng `compute_round_trip_net_return`.

Nguồn VCI/evidence/manifest, tin, VNINDEX, model và QA bank đều dựng trong
TemporaryDirectory. Các thành phần được giả lập: báo cáo Indicator/Pattern/Trend,
ảnh biểu đồ, phép tính factor Alpha và phản hồi Decision LLM. Socket/SDK LLM bị
chặn trong suite mới; fit và crawl cũng bị chặn. Đây là kiểm ranh giới dữ liệu và
quan hệ khoa học với inference xác định, không là kết quả thị trường/OOS.

Public `run_prior_backtest()` chạy ma trận five-way với `same_symbol` đã khóa.
Kiểm `pooled` dùng graph Decision cùng adapter/retriever thật; không đổi ma trận
nghiên cứu công bố. Hai provider đều dùng loader/suy luận thật trên model nhỏ
xác định: `historical_prefix` và `fixed_train_oos`.

## Coverage và thứ tự chặn

| Ca | Đường chạy / độ phủ | Bằng chứng / điểm chặn |
| --- | --- | --- |
| Snapshot future/stale/sai giá; VNINDEX future/mất prefix | Public runner, hai provider, 10 input sai | ValueError trước upstream/retrieve/LLM; chưa tạo output-dir |
| Input ở chart/Alpha/query/Decision | Public runner, hai provider × năm nhánh | Chart chỉ 45 nến PIT; Alpha nhận prefix tại cutoff với tail 600; Decision không có query outcome/evaluation/giá thực thi tương lai; đánh giá sau năm Decision |
| Tin future/undated/ngoài cửa sổ và sparse | Public runner, 2/18 bài hợp lệ × năm nhánh | Ba bài sentinel bị loại, coverage đếm đủ trước display 15; 2 bài giữ NEUTRAL, điểm 0/lý do audit, không đưa tiêu đề sparse vào prompt |
| Model future/scaler/calibration/hash | Public runner, hai provider × bốn mutation artifact | Băm lại artifact vẫn không qua loader/date/source; lỗi trước agent và output-dir |
| Provider trả proof sai | Public runner replay, sáu mutation | State date/feature date/train date/training hash/trend strength/artifact hash bị chặn trước upstream |
| Exit bằng cutoff/vắt ngang/future | Hai provider × hai ngày × hai scope × năm nhánh = **40 graph calls** | Tasks/ranking/score/selected IDs, population/denominator/rate và BRPP chỉ dùng episode đóng; Original K=0 rỗng |
| Thêm/sửa lịch sử chưa đóng | Hai provider × hai scope × năm nhánh, trước/sau | IDs/scores/seed/tasks/stats/BRPP/prompt/Decision giữ nguyên; hash toàn kho đổi được ghi đúng |
| Ngày sau rồi ngày trước | Hai provider, cùng adapter/retriever, **60 graph calls** | Ngày sau có pool lớn hơn; query cũ không tái dùng population/state/endpoint tương lai |
| Pool/selector/population bị can thiệp | Bốn mode × hai scope × ba vị trí = **24 ca** | ValueError trước formatter/LLM; không chuyển empty hoặc nới scope/regime |
| Giá/nhãn query future đổi | Hai public run cùng cutoff, năm nhánh | Snapshot quá khứ giữ byte; labels future từ engine; evaluation đổi, tasks/stats/BRPP/prompt/Decision giữ nguyên |
| Checkpoint tự băm lại chứa nguồn future | Resume hai provider × sáu mutation = **12 ca** | Cutoff/giá/tin/HMM/scaler/calibration sai bị chặn, không thêm upstream/Decision, không ghi đè point sai |

Các ca equal/straddling dùng lịch giữ vị thế không chồng lấn: tại ngày 643,
episode FPT ngày 641 vắt ngang; tại ngày 644 episode đó có exit bằng cutoff.
MWG ngày 642 bổ sung ca straddling trong pooled. Task chưa đóng bị loại khỏi
bằng chứng, không bị xem là nhãn âm hoặc bằng chứng NEUTRAL giả.

## Khe hở phát hiện và sửa

Adapter replay trước task kiểm ngày và hash artifact từ provider, nhưng chưa
đối chiếu độc lập metadata/state trả về với artifact và prefix đã ghim. Khi
provider bị can thiệp trả `training_data_sha256` khác artifact, proof này có
thể đi qua upstream và năm Decision fixture.

Sửa tối thiểu trong `core/prior_context.py`: loader detector hiện có kiểm hash
prefix thật; metadata và state suy luận được đối chiếu đầy đủ với output của
provider trước tạo point. Cache phép kiểm độc lập bằng tuple
`(artifact_sha256, cutoff, inference_prefix_sha256)`, không dùng state của ngày
sau cho ngày trước. Fixed-train giữ lifecycle nạp model một lần hiện có.
Mã verifier nằm trong run identity; checkpoint có hash code khác bị từ chối
theo hợp đồng W4-12, không tự migrate provenance.

Probe hồi quy nạp **riêng logic prepare baseline vào RAM** trên repo fixture,
không sửa file nguồn hoặc kho thật: baseline nhận proof sai và gọi 5 Decision
giả; bản sửa ném ValueError với **0 upstream/0 Decision mới**. Hash/probe và
coverage từng test có trong [receipt](pipeline_leakage_review.json).

Prefix replay có thêm một lần load/suy luận độc lập ở endpoint chưa có cache.
Retrieval/ranking/stats không đổi và vẫn dùng kho trên RAM. Rà overhead tổng
adapter/format và benchmark theo điều kiện W4-15; chưa suy ra hiệu năng pilot
từ thời gian unit suite.

## Kết quả và phần còn mở

- Compileall, **494 unit**, E2E legacy xác định và **93 leakage** PASS.
- Suite leakage đầy đủ tái sử dụng các kiểm regime, Alpha, sentiment, execution
  prices, historical labels/memory, retriever, paired và checkpoint đã có.
- **2.419 file bảo vệ**, gồm kho 852 episode, archive, manifest/QA/model,
  receipt/spec cũ, và bảy AST hàm kinh tế/legacy giữ nguyên trước/sau gate;
  chi tiết file/log/hash tại receipt.
- Không đọc hoặc lưu credentials, không gọi API thật, fit lại model, tải dữ liệu
  hoặc thay bank nhãn. Kết quả offline không mở gate giá OOS/pilot.

**W4-13 hoàn thành; Phase D 1/4, W4 13/16.** Tiếp theo **W4-14** smoke E2E
riêng và tương thích. W4-14..16/Gate D, replay smoke nguồn thật và pilot W5
vẫn cần các bằng chứng của task tương ứng.
