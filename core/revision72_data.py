"""Khóa lịch rút gọn, audit tin và feature số cho profile revision_72h."""

from __future__ import annotations

from collections import defaultdict
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timezone
import io
from pathlib import Path
import re
from typing import Any

import numpy as np
import pandas as pd

from core.revision_audit import DEFAULT_SYMBOLS, sha256_file
from core.revision_baselines import load_prices, samples, sentiment_features
from core.revision_common_study import (FrozenSentiment, digest, market_features, pack_state,
    point_state, read_json, write_json)

REVISION = "d7738b85200272f10ba8b048d80236c8c582b581"
CARD_URL = f"https://huggingface.co/5CD-AI/Vietnamese-Sentiment-visobert/resolve/{REVISION}/README.md"
OLD_BLOCKS = (("b2023_h2", "2023-07-01", "2023-03-31"),
              ("b2024_h2", "2024-07-01", "2024-03-31"),
              ("b2025_h1", "2025-01-02", "2024-09-30"))
UPSTREAM = {"b2023_h2": ("CMG", "FPT", "HVN"), "f2025_q4": ("BHN", "MBB", "MWG"),
            "f2026_q3": ("VCB", "VJC", "VNM")}
FALLBACK = {"b2023_h2": ("CMG", "FPT", "HVN"), "b2024_h2": ("MBB", "MWG", "VCB"),
    "b2025_h1": ("VJC", "VNM", "CMG"), "f2025_q4": ("BHN", "FPT", "HVN"),
    "f2026_q2": ("BHN", "MBB", "MWG"), "f2026_q3": ("VCB", "VJC", "VNM")}


def schedules(frames: dict, old: dict) -> list[dict]:
    """Lấy đầu/cuối lịch cũ và sáu cutoff cũ theo ngày, không dùng outcome chọn mẫu."""
    protocol = old["protocol"]
    result = []
    for item in old["schedule"]:
        result.append({**item, "test": [item["test"][0], item["test"][-1]], "calibration": []})
    for symbol in DEFAULT_SYMBOLS:
        if symbol == "BHN":
            continue
        frame = frames[symbol]
        candidates = samples(frame, {**protocol, "warmup_sessions": 599})
        for block, start, train_end in OLD_BLOCKS:
            first = int(np.flatnonzero(frame["date"].to_numpy() >= start)[0])
            test = [first, first + 57]
            validation = candidates.loc[(candidates["date"] > train_end) & (candidates["exit_date"] < frame["date"].iloc[first])]
            train = candidates.loc[(candidates["date"] <= train_end) & (candidates["exit_date"] < validation["date"].iloc[0])]
            if len(train) < 20 or len(validation) < 10 or min(test) < 599 or max(test) + 3 >= len(frame):
                raise ValueError("Support không đủ cho lịch lịch sử đã khóa")
            result.append({"symbol": symbol, "fold": block, "train": train["decision"].astype(int).tolist(),
                "validation": validation["decision"].astype(int).tolist(), "test": test, "calibration": [],
                "last_train_label_date": str(train["exit_date"].iloc[-1]),
                "first_validation_date": str(validation["date"].iloc[0]),
                "last_validation_label_date": str(validation["exit_date"].iloc[-1]),
                "first_test_date": str(frame["date"].iloc[first])})
    if sum(len(s["test"]) for s in result) != 102:
        raise ValueError("Lịch không đủ 102 units")
    return sorted(result, key=lambda s: (s["first_test_date"], s["symbol"]))


def audit_articles(root: Path) -> dict:
    """Dedup URL/nội dung, giữ aliases; không xác nhận snapshot PIT hoặc scorer legacy."""
    records, groups, sources = [], {}, []
    for symbol in DEFAULT_SYMBOLS:
        path = root / f"sentiment_cache_{symbol}.json"
        sources.append({"path": path.name, "sha256": sha256_file(path)})
        for index, item in enumerate(read_json(path)["scored_articles"]):
            text = (str(item.get("title", "")) + " " + str(item.get("content", ""))).strip()
            text = " ".join(text.split())
            url = str(item.get("url", "")).split("?")[0].rstrip("/")
            date = item.get("date_parsed")
            match = re.search(r"188(\d{6})\d+", url)
            date_ok = bool(date and re.fullmatch(r"\d{4}-\d{2}-\d{2}", date))
            if match and date_ok:
                date_ok = datetime.strptime(match.group(1), "%y%m%d").date().isoformat() == date
            key = digest({"url": url, "text": text})
            record = {"symbol": symbol, "index": index, "article_id": key, "url": url,
                "date_parsed": date, "text_hash": digest(text), "legacy_scorer": "unknown"}
            records.append(record)
            if key not in groups:
                groups[key] = {"article_id": key, "url": url, "text": text, "date_parsed": date,
                    "date_consistent": date_ok, "symbols": [], "source_pit": "publication_date_assumption_not_certified"}
            groups[key]["symbols"] = sorted(set(groups[key]["symbols"] + [symbol]))
    urls = defaultdict(set)
    for item in groups.values():
        urls[item["url"]].add(digest(item["text"]))
    for item in groups.values():
        item["eligible_source"] = bool(item["text"] and item["url"].startswith("https://cafef.vn/")
            and item["date_consistent"] and len(urls[item["url"]]) == 1)
    return {"sources": sources, "n_records": len(records), "n_unique": len(groups),
        "records": records, "articles": sorted(groups.values(), key=lambda a: a["article_id"]),
        "limitations": "dedup and date consistency only; not independently archived publication content or financial-domain validation"}


def score_local(audit: dict, destination: Path) -> dict:
    """Rescore cache local pinned, ánh xạ model card 0 NEG/1 POS/2 NEU; không Groq."""
    import requests
    import torch
    from transformers import AutoModelForSequenceClassification, PreTrainedTokenizerFast
    location = Path.home() / f".cache/huggingface/hub/models--5CD-AI--Vietnamese-Sentiment-visobert/snapshots/{REVISION}"
    config = read_json(location / "config.json")
    if config["id2label"] != {"0": "NEG", "1": "POS", "2": "NEU"}:
        raise ValueError("Mapping local khác model card")
    response = requests.get(CARD_URL, timeout=30)
    response.raise_for_status()
    card = response.text
    if not all(re.search(rf"{i}\s*->\s*{label}", card) for i, label in enumerate(("Negative", "Positive", "Neutral"))):
        raise ValueError("Chưa đối chiếu được mapping với model card pinned")
    with (destination / "model_card.md").open("x", encoding="utf8", newline="\n") as handle:
        handle.write(card)
    torch.set_num_threads(4)
    # Nạp đúng tokenizer.json pinned, tránh AutoTokenizer tự chuyển đổi vocab
    # không tương thích với bản transformers local. Không sửa tokenizer artifacts.
    tokenizer = PreTrainedTokenizerFast(tokenizer_file=str(location / "tokenizer.json"),
        bos_token="<s>", eos_token="</s>", pad_token="<pad>", unk_token="<unk>", mask_token="<mask>")
    model = AutoModelForSequenceClassification.from_pretrained(location, local_files_only=True).eval()
    articles = [a for a in audit["articles"] if a["eligible_source"]]
    scores = {}
    for start in range(0, len(articles), 8):
        batch = articles[start:start + 8]
        inputs = tokenizer([a["text"] for a in batch], return_tensors="pt", padding=True, truncation=True, max_length=256)
        with torch.inference_mode():
            probs = model(**{k: v for k, v in inputs.items() if k != "token_type_ids"}).logits.softmax(-1).cpu().numpy()
        for article, row in zip(batch, probs):
            scores[article["article_id"]] = {"numeric_score": float(row[1] - row[0]),
                "probabilities": [float(v) for v in row], "label": config["id2label"][str(int(row.argmax()))]}
        print(f"Rescore local {min(start + 8, len(articles))}/{len(articles)}", flush=True)
    return {"revision": REVISION, "model_card_url": CARD_URL, "model_card_sha256": sha256_file(destination / "model_card.md"),
        "files": [{"name": p.name, "sha256": sha256_file(p)} for p in sorted(location.iterdir()) if p.is_file()],
        "scores": scores, "max_length": 256, "mapping": config["id2label"],
        "limitations": "new local inference on cached excerpts; not financial-domain validation or proof of original PIT content"}


def news_from_scores(audit: dict, scores: dict) -> dict:
    """Một bài duy nhất/mã; date-only chỉ khả dụng từ ngày kế tiếp."""
    news = {s: [] for s in DEFAULT_SYMBOLS}
    for article in audit["articles"]:
        score = scores.get("scores", {}).get(article["article_id"])
        if not score or not article["eligible_source"]:
            continue
        for symbol in article["symbols"]:
            news[symbol].append({"article_id": article["article_id"], "date_parsed": article["date_parsed"],
                "available_at": (pd.Timestamp(article["date_parsed"]) + pd.Timedelta(days=1)).isoformat(),
                "numeric_score": score["numeric_score"], "scorer": "visobert", "scorer_revision": REVISION})
    return news


def make_jobs(units: list[dict], panel: list[str]) -> list[dict]:
    """Khóa lịch job cân bằng org/block; treatment luôn cùng shard, thứ tự được đảo."""
    jobs = []
    for position, unit in enumerate(units):
        variants = ["B", "AS"] if position % 2 == 0 else ["AS", "B"]
        jobs.append({"unit_id": unit["id"], "org": position % 5 + 1, "realization": 0,
            "decisions": [{"variant": v, "repeat": 0} for v in variants], "phase": "main"})
    for unit in units:
        org = next(j["org"] for j in jobs if j["unit_id"] == unit["id"])
        if unit["id"] in panel:
            variants = ["B", "A", "S", "AS", "P"] if unit["gate"] == "factorial" else ["B", "AS", "P"]
            for repeat in range(3):
                ordered = variants[repeat:] + variants[:repeat]
                todo = [v for v in ordered if repeat != 0 or v not in ("B", "AS")]
                jobs.append({"unit_id": unit["id"], "org": org, "realization": 0,
                    "decisions": [{"variant": v, "repeat": repeat} for v in todo], "phase": "panel"})
        if unit["upstream"]:
            for realization in (1, 2):
                jobs.append({"unit_id": unit["id"], "org": org, "realization": realization,
                    "decisions": [{"variant": v, "repeat": 0} for v in (("B", "AS") if realization == 1 else ("AS", "B"))], "phase": "upstream"})
    return jobs


def prepare(root: Path, bank: Path, rescore: bool = True) -> dict:
    """Khóa mới riêng; không sửa protocol/features/artifacts lịch sử."""
    if bank.exists():
        raise FileExistsError("Bank đã tồn tại; không ghi đè")
    old = read_json(root / "outputs/revision/r1_common_bank_v3/manifest.json")
    protocol = {**old["protocol"], "profile": "revision_72h", "end_to_end_repeats": 3,
        "decision_only_repeats": 3, "full_calibration_points": 0, "bootstrap_seed": 20261102,
        "bootstrap_repeats": 10000, "per_org_attempt_cap": 200, "total_attempt_cap": 1000,
        "decision_attempt_cap": 600, "per_org_decisions_24h": 40, "deadline_hours": 60,
        "failure_policy": "archive and stop shard; no fallback model or synthetic prediction; resume node cache under identical hashes",
        "sentiment_policy": "new pinned local scores on deduplicated cache; date-only next day; publication/content PIT unverified; no peers"}
    frames, _ = load_prices(root / protocol["price_snapshot"], protocol["price_quality_policy"])
    schedule = schedules(frames, old)
    bank.mkdir(parents=True)
    audit = audit_articles(root)
    write_json(bank / "article_audit.json", audit, True)
    try:
        scores = score_local(audit, bank) if rescore else {"scores": {}, "reason": "rescore explicitly unavailable"}
    except Exception as exc:
        scores = {"scores": {}, "reason": f"local scorer unavailable: {type(exc).__name__}: {exc}"}
    write_json(bank / "local_scores.json", scores, True)
    news = news_from_scores(audit, scores)
    write_json(bank / "news.json", news, True)
    units = []
    for item in schedule:
        for index in item["test"]:
            date = str(frames[item["symbol"]]["date"].iloc[index])
            coverage = sentiment_features(pd.Series([date]), news[item["symbol"]]).iloc[0]
            units.append({"id": f"{item['symbol']}_{item['fold']}_{index}", "symbol": item["symbol"], "fold": item["fold"],
                "decision": index, "date": date, "verified_articles": int(coverage["verified_article_count"]),
                "upstream": item["symbol"] in UPSTREAM.get(item["fold"], ()) and index == item["test"][-1]})
    panel = []
    for rank in range(3):
        for symbol in sorted(DEFAULT_SYMBOLS):
            eligible = sorted([u for u in units if u["symbol"] == symbol and u["verified_articles"] >= 3], key=lambda u: u["date"])
            if rank < len(eligible) and len(panel) < 18:
                panel.append(eligible[rank]["id"])
    gate = "factorial" if len(panel) == 18 else "fallback"
    if gate == "fallback":
        panel = [u["id"] for u in units if u["symbol"] in FALLBACK.get(u["fold"], ()) and
                 u["decision"] == next(s["test"][-1] for s in schedule if s["symbol"] == u["symbol"] and s["fold"] == u["fold"])]
    for unit in units:
        unit["gate"] = gate
        scope = next(s for s in schedule if s["symbol"] == unit["symbol"] and s["fold"] == unit["fold"])
        rng = np.random.default_rng(20261102 + int(digest(unit["id"])[:8], 16))
        unit["placebo_donor"] = int(rng.choice(scope["train"]))
    jobs = make_jobs(units, panel)
    for job in jobs:
        job["id"] = digest(job)[:20]
    required = sum(len(j["decisions"]) for j in jobs)
    assert required == (474 if gate == "factorial" else 366)
    smoke = []
    for org in range(1, 6):
        scope = schedule[org - 1]
        smoke.append({"id": f"smoke_org{org}", "symbol": scope["symbol"], "fold": scope["fold"],
            "decision": scope["validation"][-1], "date": str(frames[scope["symbol"]]["date"].iloc[scope["validation"][-1]]),
            "org": org, "gate": gate, "placebo_donor": scope["train"][-1]})
    manifest = {"schema_version": "revision_72h_v1", "protocol": protocol, "schedule": schedule, "units": units,
        "panel": panel, "gate": gate, "jobs": jobs, "smoke": smoke, "n_decisions": required,
        "research_min_calls": 240 + required, "smoke_min_calls": 20,
        "news_hash": digest(news), "old_bank_manifest_hash": sha256_file(root / "outputs/revision/r1_common_bank_v3/manifest.json"),
        "runtime": old["runtime"], "article_sources": audit["sources"],
        "created_utc": datetime.now(timezone.utc).isoformat()}
    manifest["bank_id"] = digest(manifest)
    write_json(bank / "manifest.json", manifest, True)
    print(f"Đã khóa {len(units)} units, gate={gate}, {required} decisions; không gọi Groq.", flush=True)
    return manifest


_ASSET_CONTEXT: dict[str, Any] = {}


def _asset_init(root: str, bank: str, manifest: dict) -> None:
    """Mỗi worker chỉ tính toán CPU; source alpha cũ phải khớp receipt trước đó."""
    root, bank = Path(root), Path(bank)
    frames, _ = load_prices(root / manifest["protocol"]["price_snapshot"], manifest["protocol"]["price_quality_policy"])
    _ASSET_CONTEXT.update(root=root, bank=bank, manifest=manifest, frames=frames,
        sentiment=FrozenSentiment(read_json(bank / "news.json")))


def _asset_point(point: tuple[str, int]) -> None:
    """Reuse alpha/raw window đã kiểm hash, cập nhật sentiment mới và bỏ mọi LLM output cũ."""
    from agents.alpha_agent import create_alpha_agent, _normalize_sentiment_scores
    from core.revision_common_study import restore_state
    c = _ASSET_CONTEXT
    symbol, index = point
    initial = point_state(c["frames"][symbol], symbol, index, c["manifest"]["protocol"], c["sentiment"])
    previous = c["root"] / f"outputs/revision/r1_common_bank_v3/features/{symbol}_{index}.json"
    if previous.exists():
        record = read_json(previous)
        if digest({k: v for k, v in record.items() if k != "sha256"}) != record["sha256"]:
            raise ValueError("Feature lịch sử bị sửa")
        alpha = restore_state(record["alpha_state"], initial)
        factors = alpha["sentiment_data"]["alpha_results"]
        tech = alpha["sentiment_data"]["tech_vars"]
        origin = {"path": previous.relative_to(c["root"]).as_posix(), "sha256": sha256_file(previous)}
    else:
        with redirect_stdout(io.StringIO()):
            alpha = create_alpha_agent(None, True, True)(initial)
        factors = alpha["sentiment_data"]["alpha_results"]
        tech = alpha["sentiment_data"]["tech_vars"]
        origin = {"path": None, "reason": "new historical cutoff; exact Alpha node on PIT prefix"}
    data, report = c["sentiment"].get_sentiment_at(symbol, str(c["frames"][symbol]["date"].iloc[index]))
    norm = _normalize_sentiment_scores(data)
    alpha["sentiment_data"] = {**data, "sentiment_norm": norm, "alpha_results": factors, "tech_vars": tech}
    features = market_features(initial, alpha)
    asset = {"symbol": symbol, "decision": index, "bank_id": c["manifest"]["bank_id"],
        "features": features, "alpha_factors": factors, "tech_vars": tech,
        "alpha_report": alpha["alpha_report"], "sentiment_report": report,
        "sentiment_data": data, "sentiment_norm": norm, "origin": origin,
        "market_input_hash": digest({"window": initial["kline_data"], "features": features})}
    asset["sha256"] = digest(asset)
    path = c["bank"] / f"features/{symbol}_{index}.json"
    if path.exists():
        if read_json(path) != asset:
            raise ValueError("Asset resume khác hash")
    else:
        write_json(path, asset, True)


def assets(root: Path, bank: Path, workers: int = 4) -> None:
    """Khóa feature/train/validation và report ngoài evaluation, không phát sinh LLM calls."""
    from concurrent.futures import ProcessPoolExecutor
    from core.revision_common_study import verify_features
    from core.revision_call_archive import StudyLock
    old_bank = root / "outputs/revision/r1_common_bank_v3"
    old = read_json(old_bank / "manifest.json")
    verify_features(old_bank, old)
    for source in old["sources"]:
        if source["path"].startswith(("agents/", "utils/", "core/alpha_compare")) and sha256_file(root / source["path"]) != source["sha256"]:
            raise ValueError("Không reuse alpha khi nguồn tính alpha đã đổi")
    manifest = read_json(bank / "manifest.json")
    points = {(s["symbol"], i) for s in manifest["schedule"] for role in ("train", "validation", "test") for i in s[role]}
    points |= {(s["symbol"], s["decision"]) for s in manifest["smoke"]}
    with StudyLock(bank / "assets.lock"):
        with ProcessPoolExecutor(max_workers=workers, initializer=_asset_init, initargs=(str(root), str(bank), manifest)) as pool:
            for n, _ in enumerate(pool.map(_asset_point, sorted(points)), 1):
                if n % 100 == 0 or n == len(points):
                    print(f"Assets số {n}/{len(points)}", flush=True)
        receipt = {"bank_id": manifest["bank_id"], "n_points": len(points),
            "files": [{"path": p.relative_to(bank).as_posix(), "sha256": sha256_file(p)} for p in sorted((bank / "features").glob("*.json"))]}
        path = bank / "assets_complete.json"
        if path.exists() and read_json(path) != receipt:
            raise ValueError("Receipt asset đã đổi")
        if not path.exists():
            write_json(path, receipt, True)
