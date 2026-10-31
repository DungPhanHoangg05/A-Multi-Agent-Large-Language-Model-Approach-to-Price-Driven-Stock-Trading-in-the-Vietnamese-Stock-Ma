"""Đọc báo cáo agent thật đã có; phân biệt lineage hợp lệ với tương thích candidate."""

from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
from typing import Any

import pandas as pd

from core.historical_signals import digest, report_signal, snapshot_payload
from core.mt_bicl_v4_protocol import read

SIGNAL_DIR = Path("outputs/historical_memory_run/signals")
EPISODE_DIR = Path("outputs/historical_memory_run/episodes")
MANIFEST = Path("outputs/historical_memory_run/run_manifest.json")
PROMPT_SOURCES = tuple("agents/" + name + "_agent.py" for name in ("indicator", "pattern", "trend", "alpha"))
CATEGORIES = ("trend", "pattern", "indicator_consensus", "alpha_consensus", "original_action")


def file_sha(path: Path) -> str:
    """Băm byte file để pin cache gốc trong manifest mới, không sửa cache."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def envelope(path: Path) -> dict[str, Any]:
    """Cache cũ dùng digest JSON có khoảng trắng; không thay bằng hash canonical mới."""
    value = read(path.read_bytes())
    if set(value) != {"payload", "sha256"} or digest(value["payload"]) != value["sha256"]:
        raise ValueError("Cache agent sai checksum: " + path.name)
    return value["payload"]


def inventory(root: Path) -> dict[str, str]:
    """Chỉ nguồn lịch sử≤2022 đã định danh; không tìm report bằng payoff hoặc nhãn."""
    paths = [root / MANIFEST]
    for directory in (SIGNAL_DIR, EPISODE_DIR):
        paths.extend(p for p in sorted((root / directory).glob("*.json")) if p.stem[4:8] <= "2022")
    return {p.relative_to(root).as_posix(): file_sha(p) for p in paths if p.is_file()}


def agent_row(root: Path, row: dict[str, Any], frame: pd.DataFrame,
              config: dict[str, Any]) -> dict[str, Any]:
    """Không suy a0 từ đồng thuận; cache prompt cũ giữ nguồn thật nhưng không dùng cho Full."""
    identifier, cutoff = row["episode_id"], row["as_of_date"]
    result = {"categories": dict.fromkeys(CATEGORIES, "UNKNOWN"),
              "observed_legacy_categories": {}, "conflicts": [None, None],
              "status": "UNAVAILABLE", "reasons": ["NO_DURABLE_ORIGINAL"], "source": None}
    if row["alpha_history_rows"] < 600:
        result["reasons"].append("ALPHA_WARMUP_LT600")
    path = root / SIGNAL_DIR / (identifier + ".json")
    if not path.exists():
        result["reasons"].append("NO_HISTORICAL_AGENT_REPORT")
        return result
    checkpoint = envelope(path)
    if checkpoint["stage"] != "COMPLETE":
        raise ValueError("Cache agent lịch sử chưa complete")
    record = checkpoint["result"]
    proof = record["provenance"]
    if (record["symbol"] != row["symbol"] or record["as_of_date"] != cutoff
            or proof["symbol"] != row["symbol"] or proof["as_of_date"] != cutoff
            or proof["price_end_date"] != cutoff or proof["alpha_end_date"] != cutoff
            or any(d > cutoff for d in proof["news_dates"])):
        raise ValueError("Provenance giá/tin của agent vi phạm PIT")
    if proof["price_rows"] < 600 or row["alpha_history_rows"] < 600:
        raise ValueError("Agent được tạo khi nguồn không đủ600 nến")
    if proof["reports_sha256"] != digest(record["reports"]):
        raise ValueError("Báo cáo agent khác hash provenance")
    episode_path = root / EPISODE_DIR / (identifier + ".json")
    episode = envelope(episode_path)
    if episode["provenance"]["signal_checkpoint_sha256"] != file_sha(path):
        raise ValueError("Cache report không khớp episode nguồn")
    prefix = frame.loc[frame["Datetime"] <= cutoff].copy()
    source_compatible = (proof["price_sha256"] == digest(snapshot_payload(prefix))
                         and proof["config"] == config
                         and proof["price_basis"] == "UNADJUSTED_EXECUTION"
                         and proof["price_source"] == "VCI" and proof["price_unit"] == "thousand_VND")
    prompt_mismatch = [name for name in PROMPT_SOURCES if proof["code_sha256"].get(name)
                       != hashlib.sha256((root / name).read_text(encoding="utf-8").encode("utf-8")).hexdigest()]
    observed = {}
    for key, report, labels in (("trend", "trend_report", ("Hướng xu hướng", "Trend direction")),
            ("pattern", "pattern_report", ("Thiên lệch dự báo", "Directional bias")),
            ("indicator_consensus", "indicator_report", ("Đồng thuận chủ đạo", "Dominant consensus"))):
        try:
            observed[key] = report_signal(record["reports"][report], labels)
        except ValueError:
            observed[key] = "UNKNOWN"
            result["reasons"].append("UNPARSEABLE_" + key.upper())
        if observed[key] != "UNKNOWN" and observed[key] != record["agent_signals"][key]:
            raise ValueError("Nhãn agent lưu sẵn khác parser report thật")
    factors = proof["alpha_factors"]
    if len(factors) != 5 or len({x["id"] for x in factors}) != 5:
        raise ValueError("Alpha thiếu năm factor duy nhất")
    directions = [x["signal"] for x in factors]
    if any(d not in ("TĂNG", "GIẢM", "TRUNG TÍNH") for d in directions):
        raise ValueError("Alpha factor sai category")
    pos, neg = directions.count("TĂNG"), directions.count("GIẢM")
    observed["alpha_consensus"] = "BULLISH" if pos > neg else ("BEARISH" if neg > pos else "NEUTRAL")
    if observed["alpha_consensus"] != record["agent_signals"]["alpha_consensus"]:
        raise ValueError("Alpha consensus không khớp năm factor nguồn")
    if not source_compatible:
        result["reasons"].append("LEGACY_PRICE_OR_CONFIG_INCOMPATIBLE")
    if prompt_mismatch:
        result["reasons"].append("LEGACY_AGENT_PROMPT_SOURCE_INCOMPATIBLE")
    if source_compatible and not prompt_mismatch:
        result["categories"].update(observed)
    result["observed_legacy_categories"] = observed
    result["source"] = {"path": path.relative_to(root).as_posix(), "sha256": file_sha(path),
                        "episode_path": episode_path.relative_to(root).as_posix(),
                        "episode_sha256": file_sha(episode_path), "prompt_mismatch": prompt_mismatch,
                        "price_config_compatible": source_compatible,
                        "reports_sha256": proof["reports_sha256"], "news_dates": deepcopy(proof["news_dates"])}
    cats = result["categories"]
    result["conflicts"] = [None if "UNKNOWN" in (cats[a], cats[b]) else int(cats[a] != cats[b])
                           for a, b in (("trend", "pattern"), ("indicator_consensus", "alpha_consensus"))]
    return result
