"""Kiểm hợp đồng scorer/tokenizer và sentiment trong prompt frozen, không inference."""

from __future__ import annotations

import ast
from collections import Counter
from datetime import datetime, timezone
from importlib.metadata import version
import inspect
import math
from pathlib import Path
import re

from agents.decision_agent import _distill_report
from core.revision72_data import REVISION, score_local
from core.revision72_run import checked, variant_state
from core.revision_audit import sha256_file
from core.revision_common_study import digest, read_json, write_json
from core.revision_minimal_bank import R1, collect
from core.revision_r4_factorial import actual_text, prompt_parts
from core.revision_sentiment_inventory import BANK, RUN, require, verify_release
from scripts.prepare_chart_r4 import native_prompt

OUTPUT = Path("outputs/revision/sentiment_contract_v1")
MODEL = "5CD-AI/Vietnamese-Sentiment-visobert"
SPECIALS = {"bos_token": "<s>", "eos_token": "</s>", "pad_token": "<pad>", "unk_token": "<unk>", "mask_token": "<mask>"}
MAPPING = {"0": "NEG", "1": "POS", "2": "NEU"}


def default_snapshot(revision: str) -> Path:
    """Chỉ trả đường dẫn local, không gọi Hub hoặc đọc token môi trường."""
    return Path.home() / f".cache/huggingface/hub/models--5CD-AI--Vietnamese-Sentiment-visobert/snapshots/{revision}"


def recipe_contract() -> dict:
    """Kiểm recipe thật bằng AST trước audit, không chạy score_local có bước tải card."""
    source = inspect.getsource(score_local)
    tree = ast.parse(source)
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    ctor = next(n for n in calls if isinstance(n.func, ast.Name) and n.func.id == "PreTrainedTokenizerFast")
    keywords = {k.arg: k.value for k in ctor.keywords}
    require({k: ast.literal_eval(keywords[k]) for k in SPECIALS} == SPECIALS, "Recipe đổi special tokens")
    require(ast.dump(keywords["tokenizer_file"], include_attributes=False) == ast.dump(ast.parse('str(location / "tokenizer.json")', mode="eval").body, include_attributes=False), "Recipe đổi tokenizer file")
    batch = next(n for n in calls if isinstance(n.func, ast.Name) and n.func.id == "tokenizer")
    require({k.arg: ast.literal_eval(k.value) for k in batch.keywords} == {"return_tensors": "pt", "padding": True, "truncation": True, "max_length": 256}, "Recipe đổi padding/truncation/max_length")
    model = next(n for n in calls if isinstance(n.func, ast.Attribute) and n.func.attr == "from_pretrained")
    require({k.arg: ast.literal_eval(k.value) for k in model.keywords} == {"local_files_only": True}, "Recipe không còn model local-only")
    expected = ast.parse("float(row[1] - row[0])", mode="eval").body
    require(any(ast.dump(n, include_attributes=False) == ast.dump(expected, include_attributes=False) for n in calls), "Recipe đổi score P(POS)-P(NEG)")
    return {"ast_digest": digest(ast.dump(tree, include_attributes=False)), "model": MODEL, "revision": REVISION,
            "mapping": MAPPING, "score": "P(POS)-P(NEG)", "label": "id2label[argmax(probabilities)], ties chọn index đầu",
            "max_length": 256, "batch_size": 8, "padding": True, "truncation": True, "special_tokens": SPECIALS,
            "model_input": "loại token_type_ids trước forward", "forward_executed_by_audit": False}


def validate_scores(scores: dict, audit: dict) -> list[dict]:
    """Đối soát 154 probabilities/labels/scores đã có, không sinh lại predictions."""
    require(scores["mapping"] == MAPPING and scores["revision"] == REVISION and scores["max_length"] == 256, "Scorer receipt sai mapping/revision/truncation")
    articles = {a["article_id"]: a for a in audit["articles"]}
    rows = []
    for key, value in scores["scores"].items():
        require(key in articles and articles[key]["eligible_source"], "Score không thuộc article đủ điều kiện")
        probabilities = value["probabilities"]
        require(len(probabilities) == 3 and all(math.isfinite(float(v)) and 0 <= float(v) <= 1 for v in probabilities), "Probability sai schema/range")
        total = sum(probabilities)
        require(abs(total - 1.0) <= 1e-5, "Probability không tổng bằng một trong sai số float32")
        expected = float(probabilities[1] - probabilities[0])
        error = abs(float(value["numeric_score"]) - expected)
        require(math.isfinite(error) and error <= 1e-7, "Score sai dấu hoặc mapping P(POS)-P(NEG)")
        label = MAPPING[str(max(range(3), key=lambda index: probabilities[index]))]
        require(value["label"] == label, "Label không khớp argmax/mapping đã khóa")
        rows.append({"article_id": key, "label": label, "numeric_score": float(value["numeric_score"]),
                     "probability_sum": float(total), "score_formula_absolute_error": float(error)})
    return rows


def verify_snapshot(snapshot: Path, scores: dict) -> list[dict]:
    """Kiểm đủ files được receipt khóa, không tải hoặc thay model/tokenizer."""
    require(snapshot.is_dir(), "Thiếu snapshot local; không được tải model thay thế")
    require(bool(re.fullmatch(r"[0-9a-f]{40}", scores["revision"])) and scores["revision"] == REVISION, "Revision không phải commit đã khóa")
    files = scores["files"]
    require(len(files) == 6 and {r["name"] for r in files} == {"config.json", "model.safetensors", "sentencepiece.bpe.model", "special_tokens_map.json", "tokenizer.json", "tokenizer_config.json"}, "Receipt thiếu/thừa model/tokenizer files")
    for row in files:
        require(sha256_file(snapshot / row["name"]) == row["sha256"], "Snapshot sai hash: " + row["name"])
    require(read_json(snapshot / "config.json")["id2label"] == MAPPING, "Config local khác label mapping")
    return files


def tokenizer_contract(snapshot: Path, audit: dict, scores: dict) -> tuple[dict, list[dict]]:
    """Tokenize đúng constructor/call của score_local; không nạp model hoặc forward."""
    from transformers import PreTrainedTokenizerFast
    tokenizer = PreTrainedTokenizerFast(tokenizer_file=str(snapshot / "tokenizer.json"), **SPECIALS)
    config = read_json(snapshot / "tokenizer_config.json")
    require(config["model_max_length"] == 256 and tokenizer.truncation_side == config["truncation_side"] == "right", "Tokenizer cap/truncation side đã đổi")
    require(tokenizer.padding_side == "right" and tokenizer.num_special_tokens_to_add(pair=False) == 2, "Tokenizer padding/special tokens đã đổi")
    require([tokenizer.bos_token_id, tokenizer.eos_token_id, tokenizer.pad_token_id, tokenizer.unk_token_id] == [0, 2, 1, 3], "Tokenizer special IDs đã đổi")
    articles = [a for a in audit["articles"] if a["article_id"] in scores["scores"]]
    rows = []
    for start in range(0, len(articles), 8):
        batch = articles[start:start + 8]
        encoded = tokenizer([a["text"] for a in batch], return_tensors="pt", padding=True, truncation=True, max_length=256)
        for i, article in enumerate(batch):
            full = tokenizer(article["text"], truncation=False)["input_ids"]
            active = encoded["input_ids"][i][encoded["attention_mask"][i].bool()].tolist()
            expected = full if len(full) <= 256 else full[:255] + [full[-1]]
            require(active == expected and len(active) <= 256, "Actual batch tokenizer khác truncation contract")
            rows.append({"article_id": article["article_id"], "full_tokens": len(full), "effective_tokens": len(active),
                         "truncated": len(full) > 256, "batch_padded_tokens": int(encoded["input_ids"].shape[1]),
                         "input_ids_digest": digest(active)})
    long_text = "tích cực tiêu cực trung tính " * 1000
    full = tokenizer(long_text, truncation=False)["input_ids"]
    truncated = tokenizer([long_text], return_tensors="pt", padding=True, truncation=True, max_length=256)["input_ids"][0].tolist()
    require(len(full) > 256 and truncated == full[:255] + [full[-1]], "Fixture dài không xác minh được right truncation 256")
    return {"constructor": "PreTrainedTokenizerFast(tokenizer_file=local tokenizer.json, explicit special tokens)",
            "explicit_max_length": 256, "constructed_model_max_length_unused": str(tokenizer.model_max_length),
            "truncation_side": tokenizer.truncation_side, "padding_side": tokenizer.padding_side,
            "special_tokens_added": 2, "scored_excerpts": len(rows), "max_excerpt_tokens": max(r["full_tokens"] for r in rows),
            "truncated_excerpts": sum(r["truncated"] for r in rows), "long_fixture_tokens_before": len(full), "long_fixture_tokens_after": len(truncated),
            "long_fixture_input_ids_digest": digest(truncated), "model_forward_executed": False}, rows


def inspect_prompt(prompt: str, asset: dict, variant: str, controlled: bool) -> dict:
    """Kiểm section thật, không nhận câu nhắc sentiment trong rules thành dữ liệu news."""
    require(len(prompt) < 6500, "Prompt vượt budget Decision")
    parts = prompt_parts(prompt)
    expected_present = variant in ("S", "AS", "P")
    require(("sentiment" in parts) == expected_present, "Variant sai presence sentiment section")
    if variant == "S": require("alpha" not in parts, "S chứa dữ liệu Alpha ngoài scope")
    missing = bool(asset["sentiment_data"]["is_unavailable"])
    expected = asset["sentiment_report"] if controlled else _distill_report("sentiment", asset["sentiment_report"], "vi")
    if expected_present:
        body = parts["sentiment"]
        require(body == expected.strip(), "Sentiment block khác asset/distillation thật")
        if missing:
            require("KHÔNG KHẢ DỤNG" in body and "không coi là trung tính" in body and "score=" not in body, "Missing bị mất marker hoặc gán score/neutral")
        else:
            require(int(asset["sentiment_data"]["verified_article_count"]) >= 3 and "score=" in body, "Available sentiment thiếu score/support")
    return {"has_sentiment_section": expected_present, "sentiment_missing_at_cutoff": missing,
            "sentiment_information_available": expected_present and not missing,
            "sentiment_block": parts.get("sentiment"), "prompt_chars": len(prompt), "prompt_digest": digest(prompt),
            "normalizer_is_reliable": bool(asset["sentiment_norm"]["is_reliable"]),
            "interpretation": "không có sentiment evidence" if not expected_present or missing else "có sentiment input; chưa chứng minh hiệu quả/validation tài chính"}


def audit_prompts(root: Path, manifest: dict, coverage: dict) -> tuple[dict, dict, set[Path]]:
    """Kiểm 375 prompts, raw hoàn chỉnh tại snapshot và S counterfactual offline."""
    run = root / RUN
    completed = collect(root, run, manifest)
    index = {r["job_id"]: r for r in completed}
    sources = {run / "manifest.json"}
    assets, rows, raw_rows = {}, [], []
    for job in manifest["jobs"]:
        unit = job["unit"]
        path = root / BANK / f"features/{unit['symbol']}_{unit['decision']}.json"
        if unit["id"] not in assets:
            assets[unit["id"]] = checked(path); sources.add(path)
        asset = assets[unit["id"]]
        result = inspect_prompt(job["prompt"], asset, job["context"]["variant"], job["phase"] == "factorial")
        proof = {"job_id": job["id"], "phase": job["phase"], "unit_id": unit["id"], "variant": job["context"]["variant"],
                 "realization": job["context"]["realization"], "repeat": job["context"]["repeat"], **result,
                 "completed_at_snapshot": job["id"] in index, "raw_request_ids_checked": []}
        if job["id"] in index:
            record_path = root / index[job["id"]]["path"]
            record = checked(record_path); sources.add(record_path)
            shard = record_path.parent.parent
            for artifact in record["call_hashes"]: sources.add(shard / artifact["path"])
            for attempt in record["request_ids"]:
                request_path = shard / f"calls/{attempt}.request.json"
                request = checked(request_path)
                require(actual_text(request) == job["prompt"], "Raw actual message khác frozen prompt")
                inspect_prompt(actual_text(request), asset, job["context"]["variant"], job["phase"] == "factorial")
                proof["raw_request_ids_checked"].append(attempt)
                raw_rows.append({"job_id": job["id"], "request_id": attempt, "request_path": request_path.relative_to(root).as_posix(),
                                 "request_file_sha256": sha256_file(request_path), "prompt_digest": result["prompt_digest"],
                                 "sentiment_missing_at_cutoff": result["sentiment_missing_at_cutoff"], "has_sentiment_section": result["has_sentiment_section"]})
                sources.add(request_path)
                receipt = shard / f"calls/{attempt}.response_digest.json"
                if receipt.exists(): sources.add(receipt)
        rows.append(proof)
    derived = []
    for row in coverage["release_cutoffs"]:
        if not row["coverage"]["sentiment_missing"]: continue
        job = next(j for j in manifest["jobs"] if j["phase"] == "main" and j["unit"]["id"] == row["id"] and j["context"]["variant"] == "AS")
        unit = job["unit"]; asset = assets[unit["id"]]
        shared = {"stock_name": unit["symbol"], "time_frame": "1 ngày", "language": "vi", "is_backtest": True}
        node_hashes = []
        for name, field in (("Indicator", "indicator_report"), ("Pattern", "pattern_report"), ("Trend", "trend_report")):
            path = root / R1 / f"shards/org{job['origin_org']}/nodes/{unit['id']}_r0_{name}.json"
            record = checked(path); sources.add(path)
            require(record["parent"]["asset_hash"] == asset["sha256"] and record["context"]["unit_id"] == unit["id"], "S builder dùng node sai asset/unit")
            shared[field] = record["state"][field]; node_hashes.append(record["sha256"])
        require(node_hashes == job["origin_parent"]["node_hashes"], "S builder sai upstream reports")
        donor_path = root / BANK / f"features/{unit['symbol']}_{unit['placebo_donor']}.json"
        donor = checked(donor_path); sources.add(donor_path)
        prompt = native_prompt(variant_state(shared, asset, donor, "S"))
        result = inspect_prompt(prompt, asset, "S", False)
        require(not result["sentiment_information_available"], "S thiếu tin không được coi là sentiment information effect")
        derived.append({"unit_id": unit["id"], "kind": "offline_native_S_builder_no_inference", "node_hashes": node_hashes, **result})
    summary = {"planned_prompts_checked": len(rows), "completed_jobs_observed": len(completed), "actual_raw_requests_checked": len(raw_rows),
               "sentiment_sections": sum(r["has_sentiment_section"] for r in rows),
               "sentiment_sections_missing_news": sum(r["has_sentiment_section"] and r["sentiment_missing_at_cutoff"] for r in rows),
               "sentiment_information_available_jobs": sum(r["sentiment_information_available"] for r in rows),
               "available_jobs_with_normalizer_flag_false": sum(r["sentiment_information_available"] and not r["normalizer_is_reliable"] for r in rows),
               "observed_raw_missing_sentiment_sections": sum(r["has_sentiment_section"] and r["sentiment_missing_at_cutoff"] for r in raw_rows),
               "missing_cutoff_native_S_diagnostics": len(derived),
               "factorial_S_jobs": sum(r["phase"] == "factorial" and r["variant"] == "S" for r in rows),
               "factorial_S_jobs_missing_news": sum(r["phase"] == "factorial" and r["variant"] == "S" and r["sentiment_missing_at_cutoff"] for r in rows),
               "max_prompt_chars": max(r["prompt_chars"] for r in rows),
               "by_phase": {phase: dict(Counter("missing" if r["sentiment_missing_at_cutoff"] else "available" for r in rows if r["phase"] == phase and r["has_sentiment_section"]))
                            for phase in ("main", "upstream", "factorial")}}
    return {"planned_prompt_evidence_masks": rows, "raw_requests_observed": raw_rows, "derived_S_missing_news": derived}, summary, sources


def run_audit(root: Path, output: Path, snapshot: Path | None = None) -> dict:
    """Xuất release T07 riêng; chỉ tokenize/read hashes, không model forward/API."""
    root, output = root.resolve(), output.resolve()
    require(output.is_relative_to(root / "outputs/revision") and output != root / "outputs/revision", "Output phải là release riêng dưới outputs/revision")
    require(not output.exists(), "Release đã có; dùng --check, không ghi đè")
    for name in ("sentiment_inventory_v1", "sentiment_coverage_v1"): verify_release(root, root / "outputs/revision" / name)
    manifest = checked(root / RUN / "manifest.json")
    for row in manifest["sources"]: require(sha256_file(root / row["path"]) == row["sha256"], "Nguồn queue đã đổi: " + row["path"])
    bank = root / BANK
    scores, audit = read_json(bank / "local_scores.json"), read_json(bank / "article_audit.json")
    snapshot = snapshot or default_snapshot(scores["revision"])
    files = verify_snapshot(snapshot, scores)
    versions = {name: version(name) for name in ("torch", "transformers", "tokenizers")}
    old = checked(root / R1 / "run_manifest.json")
    require(all(old["runtime"][name] == value for name, value in versions.items()), "Runtime tokenizer/scorer khác pins đã khóa")
    recipe = recipe_contract()
    card = bank / "model_card.md"
    require(sha256_file(card) == scores["model_card_sha256"], "Model card lưu local sai hash")
    require(all(re.search(rf"{i}\s*->\s*{label}", card.read_text(encoding="utf-8")) for i, label in enumerate(("Negative", "Positive", "Neutral"))), "Saved model card khác mapping")
    score_rows = validate_scores(scores, audit)
    tokenizer, token_rows = tokenizer_contract(snapshot, audit, scores)
    coverage_path = root / "outputs/revision/sentiment_coverage_v1/coverage.json"
    coverage = read_json(coverage_path)
    prompt_evidence, prompt_summary, sources = audit_prompts(root, manifest, coverage)
    for row in manifest["sources"]: require(sha256_file(root / row["path"]) == row["sha256"], "Nguồn queue đổi trong audit: " + row["path"])
    sources.update(bank / name for name in ("local_scores.json", "article_audit.json", "model_card.md"))
    sources.update((root / R1 / "run_manifest.json", coverage_path))
    sources.update(root / path for path in ("core/revision_sentiment_contract.py", "scripts/audit_sentiment_contract.py", "tests/test_revision_sentiment_contract.py",
                   "core/revision72_data.py", "core/revision_minimal_bank.py", "core/revision_minimal_run.py", "agents/decision_agent.py",
                   "core/revision_r4_factorial.py", "scripts/prepare_chart_r4.py"))
    for name in ("sentiment_inventory_v1", "sentiment_coverage_v1"):
        path = root / "outputs/revision" / name / "manifest.json"; sources.add(path)
        sources.update(root / r["path"] for r in read_json(path)["sources"])
    summary = {"result": "PASS", "scope": "T07 kiểm hợp đồng offline; không thay LLM inference hoặc domain validation T08",
               "observed_utc": datetime.now(timezone.utc).isoformat(), "recipe": recipe, "runtime": versions,
               "local_snapshot_files_matched": len(files), "saved_scores_validated": len(score_rows),
               "max_score_formula_absolute_error": max(r["score_formula_absolute_error"] for r in score_rows),
               "tokenizer": tokenizer, "prompts": prompt_summary,
               "limits": ["Hash files local khớp receipt rescore; không xác thực ngược scorer của 180 records legacy.",
                          "Không model forward/rescore/API; kiểm score bằng probabilities đã lưu và kiểm tokenizer bằng actual local files.",
                          "Native S tại các cutoffs thiếu tin chỉ là diagnostic prompt offline, không phải ablation inference.",
                          "Actual raw chỉ gồm checkpoints hoàn chỉnh quan sát được tại snapshot; jobs chưa xong không được coi là đã kiểm raw.",
                          "AS prompts có missing news không được dùng làm sentiment information-effect evidence; Full−Base vẫn là bundle contrast.",
                          "Normalizer >=8 khác availability >=3, không đổi prompt/input/freeze; cờ false không xóa score thật khi đủ ba bài."]}
    output.mkdir(parents=True)
    write_json(output / "summary.json", summary, True)
    write_json(output / "scorer_tokenizer.json", {"scores": score_rows, "tokenized_articles": token_rows}, True)
    write_json(output / "prompt_evidence.json", prompt_evidence, True)
    write_json(output / "manifest.json", {"schema_version": "sentiment_contract_v1", "queue_run_signature": manifest["sha256"],
               "frozen_source_hashes_checked_before_after": len(manifest["sources"]), "network_or_model_forward": False,
               "local_snapshot_revision": scores["revision"], "external_snapshot_files": files,
               "sources": [{"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)} for path in sorted(sources)],
               "outputs": [{"path": path.name, "sha256": sha256_file(path)} for path in sorted(output.iterdir())]}, True)
    return summary


def check_release(root: Path, output: Path, snapshot: Path | None = None) -> int:
    """Kiểm source/output và external local snapshot mà không chạy lại audit."""
    count = verify_release(root, output)
    manifest = read_json(output / "manifest.json")
    scores = {"revision": manifest["local_snapshot_revision"], "files": manifest["external_snapshot_files"]}
    verify_snapshot(snapshot or default_snapshot(scores["revision"]), scores)
    return count + len(scores["files"])
