# Chi tiết triển khai nằm ngoài bản thảo

Tài liệu này giữ các chi tiết vận hành trước đây xuất hiện trong appendix. Nó mô tả khả năng của repository, không chứng nhận các backends đều được dùng trong study frozen. Phạm vi và lệnh API do tác giả tự chạy nằm tại [plan.md](../plan.md); Codex không chạy provider/model probe, inference hoặc upload.

## JSON và web interface

Flask có thể nhận kết quả chứa NumPy/Pandas scalars từ indicator, statistics hoặc backtest. [utils/json_util.py](../utils/json_util.py) chuyển chúng sang kiểu Python/JSON tương thích, xử lý cấu trúc lồng nhau và nonfinite theo hợp đồng hiện hành. Không sửa prediction/label để tránh lỗi serialization. [Test web JSON](../tests/test_web_json_serialization.py) kiểm các đường liên quan; không coi khả năng serialize là bằng chứng validity của forecast.

Runtime chuẩn là Python 3.13.5 theo `.python-version`; requirements và runtime snapshots được khóa trong gói reproducibility. Root [README](../README.md) mô tả cài đặt và UI. Demo/live paths khác đường research frozen; không dùng UI live để dựng lại một historical input bị thiếu.

## Sentiment backends và tokenizer

[agents/sentiment_agent.py](../agents/sentiment_agent.py) hỗ trợ `VISOBERT_BACKEND=auto/local/endpoint/lexicon`. `auto` chọn Dedicated Endpoint khi có `HF_INFERENCE_ENDPOINT_URL`, nếu không dùng local; các fallback phải được ghi provenance. Đây là route runtime chung, không phải xác nhận backend của cache lịch sử. Không đưa key, token hoặc endpoint credentials vào artifacts/logs.

Local path dùng tokenizer/model assets đã có, truncation tối đa256 tokens; tokenizer construction, special tokens, padding/truncation và tensor inputs được audit riêng tại [scorer contract](../outputs/revision/sentiment_contract_v1/scorer_tokenizer.json). Gói có model revision/file hashes; weights sidecar không tự được suy là đã kiểm nếu chỉ replay metrics. [Runbook reproducibility](reproducibility_runbook.md) phân biệt verify/extract có hoặc không weights; [clean replay](clean_replay_runbook.md) mô tả môi trường offline.

Study này dùng saved scores và FrozenSentiment: aggregate có half-life30 ngày, tối thiểu ba valid article identities, peers unavailable; normalizer reliability>=8 khác availability>=3. `is_reliable=false`, score missing và score neutral không phải cùng trạng thái. Việc sửa metadata mới không xác nhận ngược scorer/availability của legacy180 records. Việc rescore/tokenizer test không thay financial-domain labels hoặc xác thực PIT content.

## Prompts, checkpoints và chi phí

Raw actual messages, inline PNGs, responses/errors, parse/checkpoint parents, model aliases, SDK parameters, execution epochs và fingerprints được giữ trong release/package riêng. Không dùng template hiện tại thay prompt thực đã gửi hoặc suy immutable hosted revision từ alias/fingerprint. [T27 accounting](../outputs/revision/final_cost_integrity_v1/report.md) phân biệt Pattern replay với calls mới, unknown fields và actual retries; replay lookup không có chi phí token của một call mới.

Prompt guards giữ Decision dưới6.500 ký tự; report distillation/capping, callback archive, exponential backoff, quota state và atomic checkpoints phải được giữ đúng phiên bản. Runner resume bỏ qua successes có context/parent/raw hợp lệ, không gọi lại để chọn outcome khác. [Scope-specific tests](../outputs/revision/final_regression_v1/cases.json) và [log](../outputs/revision/final_regression_v1/tests.log) là bằng chứng phần mềm đã chạy trước đây, không thay LLM experiment mới hoặc global causal certification.

Khi manuscript sources đã được sửa, receipts lịch sử phải đối chiếu với đúng source ZIP/member/hash. Chỉ source `paper/` được bridge sang ZIP đã khóa; runtime, raw, labels và model/input mutations không được miễn hash guard. [Generator T32](../scripts/build_revision_manuscript.py) chỉ tạo tables/figures/companions từ saved evidence; nó không chạy model, refit, bootstrap hoặc final PDF build.

## Registry và dữ liệu bổ sung

[Registry](../outputs/revision/alpha_registry_v1/registry.json) giữ80 retained expressions,21 exclusions, năm custom definitions và source/operator differences; [causal audit](../outputs/revision/alpha_contract_v1/leakage.json) giữ counterexamples native FAIL. Full code/state schemas/per-cutoff diagnostics thuộc repository, không chép toàn bộ vào article appendix. Scientific companions S1–S4 được tổ chức riêng tại [manuscript release](../outputs/revision/manuscript_rewrite_v1/supplement/README.md), gồm đủ baseline-by-symbol, repeats, numeric family và temporal diagnostics.

Public distribution rights/PID và author metadata vẫn pending. Không tự đưa raw review text hoặc private inputs vào public package, không ghi package nội bộ là public archive. Đây là hướng dẫn vận hành độc lập; tiến độ chỉ ở `plan.md`.
